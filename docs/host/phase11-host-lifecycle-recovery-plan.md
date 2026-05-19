# Phase 11 Host Lifecycle / Recovery / Multi-process Hardening Handoff Plan

## Gate

当前 gate：Phase 11 handoff implementation-ready plan generation。

本 artifact 只供 implementation agent 使用：不修改 `dayu/` 源码、不修改 tests、不提交、不 push、不创建 PR、不进入 implementation gate。

## Goal / Motivation

目标是实现 Host startup recovery scan、positive orphan proof、已接受 Prompt 的崩溃恢复、RECOVERING dispatch、graceful shutdown lifecycle 与必要的多进程 hardening，并保持 P10.5 已冻结的 ordinary local multi-turn public contract 不变。

动机成立。P10.5 已证明真实 Service 可通过 `open_host(options)`、session acquisition、public command 与 `watch_session_events(session_id)` 完成普通本地多轮闭环，但 P10.5 明确不证明 crash recovery。当前直接证据显示：

- `docs/host/design.md` §27 要求 Host startup recovery scan，且 `RUNNING` / `CANCELLING` 只有 positive orphan proof 成立后才能 `ATTEMPT_LOST`。
- `dayu/host/open_host.py` 当前打开 durable store、scheduler、admission service 后直接 ready，没有 startup recovery scan。
- `dayu/host/dispatch.py` 当前 `_register_dispatch_host_instance(...)` 只注册 `process_start_token=f"dispatch-{host_handle_id}"` 的诊断 row，没有持续 heartbeat task，也没有 close 时 mark stopping / stopped。
- `dayu/host/durable/liveness.py` 当前 `_REGISTER_RUNNING_SOURCE_STATUSES` 包含 `STOPPING`，同一 instance 可由 repeated register 从 `stopping` 回刷为 `running`；这会削弱 lifecycle monotonic diagnostic。
- `dayu/host/durable/run_transition.py` 已有 reactive context recovery helper，但 startup orphan closeout 所需的 `ATTEMPT_LOST -> RUN_RECOVERING / RUN_LOST` 事务 helper 尚未接入。
- `dayu/host/admission.py` / `dayu/host/command.py` 当前把 `RECOVERING` cancel 明确留给 Phase 11。

第一性原理判断：Phase 11 的核心不是“看到 heartbeat stale 就恢复”，而是把 durable truth、进程存活证据和 CAS 状态迁移合在一起，证明旧 owner 已不可能继续治理该 Attempt。没有 positive orphan proof 时，正确行为是 suspect diagnostic，不误杀、不接管。

## Non-goals

- 不修改 Engine 代码；如 implementation 发现必须改 Engine，立即停下并作为 Blocking Question For Controller。
- 不引入 lease / fencing / takeover，不恢复旧 Engine / Agent / Runner / provider request。
- 不让 RemoteStub / EngineWorker append EventLog、关闭 Attempt、更新 Run 或执行 recovery。
- 不让 projection、memory snapshot、audit、trace、tool trace、outbox、timeline、RunResult 或 projection checkpoint 成为 recovery truth。
- 不把 heartbeat stale、dispatching、dispatcher instance、lane token、lane claim、watcher 存在性或当前进程不可控制当作 positive orphan proof。
- 不保证 exactly-once 远程物理执行，不强杀远程 worker，不设计 RemoteProxy wire protocol。
- 不改变 P10.5 public API；不新增 public recovery command、public recovery policy option 或 alternate startup API。
- 不实现 production watch push / notification 机制；保留现有 `watch_session_events` public contract。
- 不做宽泛 God module cleanup、ToolRuntime cleanup、durable layering cleanup 或 README 全量改写。

## Direct Evidence

- `docs/host/design.md` §1：Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / steer / replay / memory / tool governance 真源；Engine 只执行单次 `AgentRunRequest`。
- `docs/host/design.md` §2：Recovery 是唯一负责 Host startup scan、旧 Attempt `LOST` 收口和可恢复 Run 新 Attempt 创建的模块；Attempt Dispatch、RemoteStub、EngineWorker 不得生成治理事实。
- `docs/host/design.md` §9 / §10：多进程一致性依赖 SQLite transaction、unique constraint、CAS-style state transition 与 EventLog ordering；EventLog append 与 Run / Attempt state index 更新必须同事务。
- `docs/host/design.md` §17：`dispatching` 与 `dispatcher_instance_id` 只是诊断和重复派发抑制，不是 lease / fencing；Host recovery scan 遇到 `dispatching + STARTING` 也必须具备 positive orphan proof 才能 `LOST`。
- `docs/host/design.md` §27：`ACCEPTED` / `QUEUED` / `WAITING` startup 原地保留；`RUNNING` / `CANCELLING` 只有 positive orphan proof 成立才进入 `ATTEMPT_LOST`；`RECOVERING` 创建新 Attempt / 新 `execution_id`。
- `docs/host/design.md` §27.1：已 durable append `USER_INPUT_ACCEPTED` 且未 final answer 的 prompt，重启后应基于 canonical facts 重建 messages 并最终产出 answer，或结构化 `FAILED` / `LOST`。
- `docs/host/implementation-control.md` Phase 11：P11 必须接入同一 `open_host(...)` / session acquisition / `watch_session_events(...)` / public command contract，不能要求真实 Service 改走另一套恢复入口。
- `docs/host/implementation-control.md` 追踪区：runtime lane close/acquire race、Host crash recovery E2E、`cancel_session_runs` RECOVERING、Phase 2 stopping 回刷均归 Phase 11。

## Affected Files / Modules

允许修改：

- `dayu/host/recovery.py`：新增 Recovery coordinator、startup scan、classifier orchestration、policy defaults。
- `dayu/host/recovery_process.py` 或同等 Host-internal module：新增本机 pid/process probe；不得放入 Engine。
- `dayu/host/durable/liveness.py`：收紧 lifecycle transition，补 heartbeat / stopped 相关 helper 测试所需边界。
- `dayu/host/durable/state.py`：新增 active Attempt lost、RUNNING/CANCELLING -> RECOVERING / LOST、RECOVERING -> CANCELLED / LOST 所需 CAS row helper。
- `dayu/host/durable/run_transition.py`：新增 startup recovery closeout、recovery dispatch、RECOVERING cancel / lost transition 的 EventLog + state index 同事务 helper。
- `dayu/host/dispatch.py`：Host instance identity、heartbeat lifecycle、startup recovery wake / dispatch integration、graceful close ordering。
- `dayu/host/open_host.py`：在 public opener ready 前接入 startup recovery scan；不新增 public API。
- `dayu/host/admission.py`、`dayu/host/command.py`：接入 `RECOVERING` cancel 与 `cancel_session_runs` 语义。
- `dayu/runtime/lane.py`：只允许修 close/acquire race、stale cleanup、active count invariant；不得引入 Host truth。
- `tests/host/*`、`tests/runtime/*`、`tests/README.md`、`dayu/host/README.md`：对应测试与文档同步。

禁止修改：

- `dayu/engine/**`。
- `dayu/service/**`、`dayu/ui/**`，除非 controller 另开 work unit。
- `dayu/fins/**`。
- P10.5 public API surface：`open_host(options)`、public handle methods、request/snapshot 语义、`watch_session_events` contract。

## Contract / Schema / State-machine / Public-interface Changes

Public interface:

- 不新增 public API，不新增 public `OpenHostOptions` 字段。
- `open_host(options)` 的 startup side effect 扩展为：打开 Host 后自动执行 internal recovery scan，然后继续使用既有 scheduler / public commands / watcher。
- `watch_session_events(session_id)` 必须能看到 recovery 提交的普通 Host events；不引入 recovery 专用 stream。

Schema:

- 默认不新增 schema 字段。第一版 recovery attempt count 通过 EventLog 中同一 Run 的 `RUN_STARTED` 且 `start_reason=recovery` 计数得到。
- 若 implementation 证明 EventLog 计数无法可靠表达上限，必须先停下交 Controller；不得自行新增 schema 或 public migration policy。

State machine:

- Startup scan 保持 `ACCEPTED`、`QUEUED`、`WAITING` 原状态；只触发 scheduler / wait observation，不写 recovery facts。
- `RUNNING` / `CANCELLING` + positive orphan proof：
  - recoverable and not cancelled：`ATTEMPT_LOST` -> `RUN_RECOVERING`，Attempt `LOST`，Run `RECOVERING`。
  - canonical facts 缺失、已取消、超过自动 startup recovery 上限或 policy 放弃：`ATTEMPT_LOST` -> `RUN_LOST`，Attempt `LOST`，Run `LOST`。
- `RECOVERING` + 未取消 + recovery dispatch count 未超限：`RUN_STARTED(start_reason=recovery)` -> 新 Attempt row `STARTING` -> `ATTEMPT_STARTED` -> pending dispatch record。
- `RECOVERING` + 已取消或 cancel command：`CANCEL_REQUESTED` -> `RUN_CANCELLED`；不创建 Attempt，不传播 WorkerProxy。
- `RECOVERING` + recovery dispatch count 已超限：`RUN_LOST`，reason 必须结构化，例如 `startup_recovery_dispatch_limit_exceeded`。

EventLog / state index ordering:

- Positive orphan closeout recoverable path 必须在一个 write transaction 内按顺序 append `ATTEMPT_LOST`、`RUN_RECOVERING`，并同事务更新 Attempt terminal refs、Run status / current attempt refs。
- Unrecoverable path 必须在一个 write transaction 内按顺序 append `ATTEMPT_LOST`、`RUN_LOST`，并同事务更新 Attempt terminal refs、Run terminal refs。
- Recovery dispatch 必须在一个 write transaction 内 append `RUN_STARTED(start_reason=recovery)`、更新 Run `RUNNING` / current Attempt、insert new Attempt `STARTING`、append `ATTEMPT_STARTED`、insert dispatch record `pending`。
- `RUN_STARTED(start_reason=recovery)` 不表示旧 Attempt recovered；它只表示同一 Run 创建了新 Attempt。

## Implementation Decisions

1. 收紧 host instance lifecycle：`STOPPING` 不允许被 repeated `register_current_instance(...)` 回刷为 `RUNNING`。`register` 对同一 id 只允许插入新 row 或刷新仍为 `RUNNING` 的同 identity row；`STOPPING` / `STOPPED` / `CRASHED_SUSPECTED` 均结构化 lifecycle conflict。
2. Host instance heartbeat 是当前 opener / scheduler 的 lifecycle diagnostic，不是 owner lease。heartbeat task 只能刷新自己的 row；close 先 mark stopping，关闭 scheduler / lane / workers 后 best-effort mark stopped。
3. 第一版 process probe 只把“heartbeat stale + pid 不存在”作为 portable positive orphan proof。若 pid 存在但无法从本机进程证据证明启动指纹 mismatch，输出 inconclusive diagnostic；不得误杀。若实现能在当前平台可靠读取 process created_at / boot id，可额外支持 pid reused mismatch，但必须作为 probe capability，不得作为必需路径。
4. Positive orphan classifier 输入必须是 durable candidate + process evidence + policy time，输出 typed union：
   - `PositiveOrphanProof`：可进入 CAS closeout。
   - `OwnerStillLive`：owner heartbeat 未 stale 或 pid evidence 仍 live。
   - `OrphanProofInconclusive`：缺 dispatch owner、缺 liveness row、heartbeat stale 但 pid evidence 不足、process probe unavailable、durable identity mismatch 无法证明。
5. Classifier 不写数据库。所有写入必须在 Recovery transition helper 内做 CAS recheck：重新读取 Run / Attempt / dispatch record / host instance row，确认状态、attempt id、execution id、owner_host_instance_id、heartbeat stale 与 policy input 仍一致。
6. Suspect owner 只记录 diagnostic event 或 structured log。若写 EventLog diagnostic，event_class 必须是 `diagnostic`，不得更新 Run / Attempt index，不得被 Recovery 再读作 truth。
7. Recovery dispatch 复用现有 dispatch scheduler 和 RunInputBuilder。Recovery coordinator 只创建新 Attempt / pending dispatch，并 wake scheduler；真正 `AgentRunRequest.messages` 仍由 dispatch path 的 `RunInputBuilder` 从 canonical EventLog facts、payload descriptors、compact artifacts、memory provider protocols 重建。
8. `CANCELLING` orphan 不自动恢复执行。由于 durable cancel fact 表达用户停止意图，positive orphan proof 后以 `ATTEMPT_LOST + RUN_LOST` 收口，reason 说明 `cancel_in_flight_attempt_lost`；不得创建新 Attempt 继续回答。
9. Graceful shutdown 不写 `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED`、`RUN_LOST` 或伪造 terminal fact。只有 worker 已产出且被 ingest 确认的 terminal event 可以正常提交。
10. 每个 Run 最多一次 automatic startup recovery dispatch。计数以 committed EventLog canonical fact 为准，不使用 memory/projection。

## Implementation Slices

### Slice 1. Host Instance Lifecycle And Process Proof

Allowed files:

- `dayu/host/durable/liveness.py`
- `dayu/host/recovery_process.py` 或 `dayu/host/recovery.py`
- `dayu/host/dispatch.py`
- `tests/host/test_host_instance_liveness.py`
- new `tests/host/test_recovery_orphan_classifier.py`

Exact changes:

- 将 `_REGISTER_RUNNING_SOURCE_STATUSES` 收紧为仅 `RUNNING`。
- 更新 repeated register tests：`STOPPING -> RUNNING` 旧断言删除，改为 lifecycle conflict；保留 RUNNING repeated register 幂等刷新。
- 新增 typed process probe：
  - `ProcessEvidence(pid: int, exists: bool, observed_start_token: str | None, observed_boot_id: str | None, probe_error_code: str | None)`
  - `ProcessLivenessProbe` Protocol 或 concrete class，默认用 stdlib pid-exists probe；不使用 `Any` / `object`。
- 新增 positive orphan classifier dataclass / union，覆盖 stale threshold、missing owner、pid missing、pid live/inconclusive、pid reused mismatch capability。
- `HostDispatchScheduler.open(...)` 生成真实 per-process `HostInstanceIdentity`：`host_instance_id` 仍可用 `host_handle_id`，但 `process_start_token` 必须和 `host_instance_id` 分开生成，使用 `uuid4().hex` 或等效 stdlib 高熵随机值，不得使用 timestamp、handle id、pid 或这些值派生出的 token，也不得继续使用 `dispatch-{host_handle_id}` 这类可预测占位。
- Scheduler lifecycle 增加 heartbeat background task；周期必须小于 recovery stale threshold，close 时取消并 mark stopping / stopped。
- Heartbeat loop 必须捕获并输出 structured diagnostic logging。单次 refresh 异常可按 policy 继续重试；若 heartbeat task fatal exit，必须 best-effort 将当前 scheduler 自己的 host instance 标记为 `STOPPING`，不得标记或修改其它 host instance row。

Validation:

```bash
source .venv/bin/activate
pytest tests/host/test_host_instance_liveness.py tests/host/test_recovery_orphan_classifier.py -q
python -m pyright dayu/host tests/host
```

### Slice 2. Startup Recovery Scan Classification And CAS Closeout

Allowed files:

- `dayu/host/recovery.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/event_log.py` only if a narrow typed read helper is needed
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`

Exact changes:

- Add startup scanner that reads non-terminal Runs and classifies:
  - `ACCEPTED`: keep, schedule accepted-run wake.
  - `QUEUED`: keep, schedule queue promotion check.
  - `WAITING`: keep, no Attempt creation; optional wait observation wake if existing adapter supports it.
  - `WAITING` recovery 若 adapter observation 不可用、adapter 不支持重挂、或 wake 失败，必须走 diagnostic-only fallback：记录 structured diagnostic log 或 `event_class=diagnostic` 的 EventLog 事件；不得推进 Run / Attempt 状态，不得创建 Attempt，不得把 diagnostic 再读作 recovery truth。
  - `RUNNING`: classify current Attempt / dispatch record / owner proof.
  - `CANCELLING`: classify current Attempt / dispatch record / owner proof; positive proof goes `LOST`, not recovery dispatch.
  - `RECOVERING`: evaluate cancel/limit and either dispatch or `LOST`.
- Add transition helper for positive orphan closeout:
  - `StartupOrphanCloseInput` with run id, attempt id, execution id, dispatch record id, owner instance id, occurred_at, event ids, reason.
  - recoverable path appends `ATTEMPT_LOST` then `RUN_RECOVERING`.
  - lost path appends `ATTEMPT_LOST` then `RUN_LOST`.
- CAS recheck must compare Run status/current attempt, Attempt status/execution id, dispatch record attempt/execution/owner/status, host instance heartbeat row.
- Add typed EventLog recovery dispatch count helper in the durable/EventLog boundary: helper must filter by `run_id` and canonical `RUN_STARTED` events, and only count events whose payload has `start_reason=recovery`. It must not count projection/read-model rows, diagnostic events, old Attempt snapshots, or non-canonical payload text matches outside the typed event codec.
- Ensure projection lag does not affect classification tests: tests must disable / lag projection and assert recovery decisions use EventLog / state rows only.

Validation:

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q
python -m pyright dayu/host tests/host
```

### Slice 3. RECOVERING Dispatch And RunInputBuilder Integration

Allowed files:

- `dayu/host/recovery.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_open_host_runtime.py`

Exact changes:

- Add `start_recovery_run_with_starting_attempt_in_transaction(...)` usage for startup recovery path if existing helper satisfies ordering; otherwise adjust helper without changing reactive context behavior.
- Recovery coordinator creates new Attempt id / execution id / dispatch record id and commits `RUN_STARTED(start_reason=recovery)` + `ATTEMPT_STARTED` + pending dispatch record.
- After commit, wake existing `HostDispatchScheduler.wake_dispatch(...)`; do not call WorkerProxy from Recovery.
- Verify dispatch path uses RunInputBuilder to rebuild messages from canonical facts for the same Run, not from old Attempt snapshot, memory projection lag, or read model.
- If current `RunInputBuilder` cannot rebuild recovery messages only from canonical EventLog facts and payload descriptors, Slice 3 may perform necessary typed hardening inside `RunInputBuilder` / dispatch-path ownership so the dispatched `AgentRunRequest.messages` are derived from canonical facts. Do not treat projection, memory snapshot, read model, audit, trace, outbox, timeline, `RunResult`, or projection checkpoint as truth. If this hardening needs files outside Slice 3 allowed files, stop and return to Controller before editing them.
- `open_host.__aenter__` must run startup recovery scan before logging ready / returning public handle. It may create pending dispatch and wake scheduler; it must not require Service to call a recovery command.
- Add integration test: seed or crash a Run after `USER_INPUT_ACCEPTED` / before final answer, reopen with `open_host(options)`, observe final answer through `watch_session_events`.
- Add late old execution test if local harness can emit late event: old execution_id events after new Attempt must be rejected from canonical facts.

Validation:

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_dispatch.py tests/host/test_run_input_builder.py tests/host/test_open_host_runtime.py -q
python -m pyright dayu/host tests/host
```

### Slice 4. RECOVERING Cancel, Graceful Shutdown, And Public Contract Preservation

Allowed files:

- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/test_watch_session_events.py`

Exact changes:

- `cancel_run` on `RECOVERING` before recovery dispatch commits: append `CANCEL_REQUESTED` + `RUN_CANCELLED`; no Attempt terminal, no WorkerProxy cancel.
- `cancel_session_runs` must include RECOVERING in session-scope cancel target set. It must not fail-closed merely because a RECOVERING Run exists.
- Idempotency replay for RECOVERING cancel must return same result and not cancel later new Runs.
- Idempotency scope is explicit and unchanged: `cancel_run` is scoped by `(run_id, client_request_id)`; `cancel_session_runs` is scoped by `(session_id, client_request_id)`. For `cancel_session_runs`, per-run result stability applies only to Runs included in the original session-scope command result and must not affect later newly created Runs in the same session.
- Graceful shutdown:
  - public handle close sets closed gate first;
  - scheduler close stops promotion / dispatch / lane waits / active worker tasks;
  - mark host instance stopping / stopped best-effort;
  - does not append user cancel or terminal facts unless normal ingest already accepted terminal.
- Existing watchers after handle close may end according to P10.5 accepted behavior; do not change to a new public lifecycle error without Controller decision.

Validation:

```bash
source .venv/bin/activate
pytest tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q
python -m pyright dayu/host tests/host
```

### Slice 5. Multi-process Recovery And Runtime Lane Hardening

Allowed files:

- `dayu/host/recovery.py`
- `dayu/host/dispatch.py`
- `dayu/runtime/lane.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/runtime/test_lane.py` or existing runtime lane test module
- `tests/host/public_smoke_support.py` only for shared public smoke helpers

Exact changes:

- Add multi-process harness for:
  - live second process not harmed: process A owns active Attempt and heartbeats; process B opens same DB, scans, records no `ATTEMPT_LOST`, does not create new Attempt.
  - crash after `USER_INPUT_ACCEPTED` before final answer: killed owner pid + stale heartbeat -> restart produces answer through public Host event stream.
  - projection lag: stop / lag projection, recovery still uses durable EventLog / Run / Attempt / dispatch rows.
- Fix runtime lane close/acquire race if reproduced:
  - `LaneController.close()` must wake pending acquire and prevent new claims.
  - close/acquire concurrent tests assert no acquire hang and active claim count invariant.
  - stale claim cleanup remains runtime capacity cleanup only; no Host recovery truth.
- Test helper hardening enters only where needed for recovery multiprocess/public smoke readability. Prefer one shared `tests/host/recovery_support.py` for process harness and recovery seed helpers. Do not start broad test architecture rewrite.

Validation:

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q
pytest tests/host -q
python -m pyright dayu/host dayu/runtime tests/host tests/runtime
```

## Deferred From This Phase

- Watch polling performance / replacing 20ms polling with push notification: deferred to later public lifecycle / production watch scale owner. Phase 11 only verifies recovery events remain visible through existing watch contract.
- Existing watcher close behavior change to mandatory `HostClosedError`: deferred because it is public lifecycle behavior change and not required for recovery correctness.
- Broad cross-module private helper cleanup: deferred except recovery-specific shared helper extraction.
- Durable bootstrap DDL atomicity, after-commit multi-error aggregation, audit/outbox terminal delivery, purge retention cleanup, RemoteProxy orphan execution reconciliation: deferred to their existing owners.
- PID reused fingerprint positive proof on platforms where stdlib probe cannot prove start-token mismatch: classifier returns inconclusive; optional platform-specific proof requires review evidence.

## Tests / Validation Commands

Per slice commands are listed above. Phase acceptance must also run:

```bash
source .venv/bin/activate
pytest tests/host -q
pytest tests/runtime -q
python -m pyright dayu/host dayu/runtime tests/host tests/runtime
git diff --check
```

If runtime tests directory does not exist yet, implementation may create focused runtime lane tests under the existing runtime test convention; otherwise use the existing lane test module path.

Coverage expectations:

- Unit: orphan proof classifier, host instance lifecycle, recovery transition ordering, recovery dispatch count.
- Integration: accepted prompt crash recovery, RECOVERING dispatch, RECOVERING cancel, graceful shutdown no fake facts.
- Multi-process: live owner not harmed, killed owner recovers after stale threshold, projection lag not truth.
- Public path: final answer visible through `watch_session_events`, no alternate recovery public API.

## Docs Decision

Implementation must update docs after tests pass:

- `dayu/host/README.md`: add stable Host recovery semantics, startup scan, positive orphan proof boundary, graceful shutdown vs cancel distinction.
- `tests/README.md`: add recovery / multi-process test harness conventions, projection-lag truth rule, runtime lane race test scope if touched.
- Root `README.md`: update only if user-facing CLI / command usage changes. This plan expects no root README change.
- `dayu/README.md`: update only if implementation changes layer boundaries or public contract. This plan expects no layer-boundary change.
- `docs/host/design.md` / `docs/host/implementation-control.md`: do not change during implementation unless a blocking design issue is discovered and Controller decides.

## Review Gates

- Plan review: at least two independent reviewers must verify this plan against `docs/host/design.md` §1 / §2 / §10 / §17 / §27 / §27.1 and `implementation-control.md` Phase 11.
- Per-slice code review: each slice must include implementation artifact, focused tests, pyright result, docs decision, residual risk.
- Aggregate deepreview before ready-to-open-draft-PR: must cover recovery truth source, CAS ordering, multi-process safety, public API preservation, no Engine changes, no lease/fencing/takeover.
- Any review finding that implies public API, schema, Engine contract, state-machine, persistent truth, or user-visible recovery behavior change must be escalated to Controller.

## Stop Conditions

Stop and ask Controller if any of the following occurs:

- Implementation appears to require modifying `dayu.engine`.
- Recovery cannot be implemented without adding public API / `OpenHostOptions` fields.
- A schema change becomes necessary for recovery count, owner identity, or diagnostics.
- Positive orphan proof cannot be obtained without treating heartbeat stale, lane token, dispatching, projection, memory, audit, trace or outbox as truth.
- Classifier would kill / recover a Run while owner pid is live and startup fingerprint mismatch is not directly proven.
- Recovery dispatch needs to call WorkerProxy directly from Recovery instead of creating pending dispatch for Attempt Dispatch.
- Recovery message rebuild requires `RunInputBuilder` hardening outside Slice 3 allowed files.
- Tests require asserting projection / memory / read model as recovery truth.
- Multi-process live-owner-not-harmed test fails.
- Graceful shutdown would need to append fake user cancel / terminal fact to pass tests.

## Risks / Open Questions

Blocking Questions For Controller: none.

Non-blocking risks:

- Portable pid-reuse proof is limited. First version should only produce positive proof for pid-missing unless platform process start evidence is directly available.
- Internal stale threshold default affects recovery latency. This plan avoids public API change; production tuning may later require a public/internal policy discussion.
- Recovery E2E with real process kill can be timing-sensitive. Tests should use deterministic stale heartbeat setup or bounded waits without weakening production classifier.
- Existing `RunInputBuilder` may need small typed provider hardening to rebuild from canonical facts when projection is lagging; it must not fall back to memory/read model truth.
- Lane close/acquire fixes touch `dayu.runtime`; review must verify runtime remains layer-neutral and does not import Host.

## Completion Report Format

Implementation agent final report must include:

```text
Artifact:
- implementation artifact path

Changed:
- files/modules changed
- state-machine / lifecycle behavior changed
- public API changed: yes/no
- schema changed: yes/no
- Engine changed: no

Verified:
- focused pytest commands and results
- full affected test command and result
- pyright command and result
- git diff --check result

Docs:
- README files updated or explicit no-op reason

Residual risks:
- remaining risks with owner / deferred phase

Conclusion:
- HANDOFF_IMPLEMENTED or BLOCKED, with blocking question count
```

## Conclusion

HANDOFF_READY.
