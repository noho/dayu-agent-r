# WU-LIFE-03 Active Cancel Watchdog And Post-cancel Timeout Plan

## Goal / Motivation / Success Signal

Goal: 为 GitHub Issue #91 / #87 umbrella 下的 Host-level active cancel watchdog 形成 code-generation-ready plan。Host 接受 active cancel 后，durable truth 不再依赖 worker、Engine、provider 或 tool cooperative 返回；超时后必须通过 Host-owned timeout closeout 或 diagnostic 收敛。

Motivation: 当前 Host 已有 active cancel durable transition 与 best-effort propagation，但 active worker 不返回时，Run 可能长期停在 `CANCELLING`。这是 Host lifecycle correctness 缺口，不是 provider kill 能力缺口。第一性原理上，用户 cancel 被 Host 接受后，Session active slot 不能无限被不可确认 worker 占用；Host durable truth 必须能在 bounded time 内给出可恢复、可订阅、可诊断的收口结果。

Success signal:

- active `RUNNING` Attempt 被 cancel 后，即使 worker stream 不结束、provider 不返回、worker task 不响应 token，Host 也会在 post-cancel timeout 后写入 terminal closeout。
- timeout closeout 与 cooperative `run_cancelled`、final answer、failure、awaiting/suspend 的 late race 遵守 first-committer-wins，不重复、不互相矛盾。
- `cancel_run` replay 和 `cancel_session_runs` replay 不重复追加 `CANCEL_REQUESTED` / `RUN_CANCELLING`，但仍能重放 active cancel propagation。
- scheduler / Host close 仍只是本地 runtime lifecycle，不被设计成用户 cancel 或 active cancel timeout closeout。
- WU-TOOLS-CANCEL-01 可以消费本 plan 固定的 Run / Attempt terminal 与 diagnostic contract，不需要重新裁决 Host terminal policy。

## Non-goals / Scope Boundary

- 不实现 provider-specific kill API。
- 不设计 tool/provider execution capsule。
- 不做 subprocess / process-group / sandbox hard kill 策略；这些归 WU-TOOLS-CANCEL-01。
- 不替代 WU-WAIT-04 的 UI / Service awaiting E2E smoke。
- 不创建第二套 watchdog runtime；必须复用或最小扩展 Host lifecycle watchdog / supervisor 方向。
- 不让 Engine 拥有 Session / Run / Attempt lifecycle，不修改 Engine public contract。
- 不把 scheduler close / Host opener close 伪装成用户 cancel、Run failure 或 active cancel timeout。
- 不新增 Service-facing cancel API；`cancel_run` / `cancel_session_runs` 的 public shape 保持不变。
- 不在 Host SQLite write transaction 内执行 worker/provider I/O、等待 task、sleep 或 hard kill。

## Design Document Alignment

Host design alignment:

- `docs/host/design.md` 规定 Host 是 Session / Run / Attempt / EventLog / cancel / recovery / replay 的治理真源，Engine 只执行单次 `AgentRunRequest`。
- Run 状态 `CANCELLING` 的语义是 Host 已接受取消请求，正在等待 active Attempt 收口或超时升级。
- active cancel path 固定为 append `CANCEL_REQUESTED` + `RUN_CANCELLING`，commit 后向 WorkerProxy 传播 cancel；terminal fact 已提交后 late cancel 不能改写 terminal。
- cancel 与 suspend / awaiting 同时发生时，由 Host ingest 事务提交顺序决定；cancel 已提交后，late suspend / awaiting candidate 不得把 Run 推入 `WAITING`。
- 设计真源明确：未引入 watchdog 强化治理前，active Attempt 超时无法确认时旧 Attempt 进入 `LOST`；若 cancel 已 durable accepted 且 terminal fact 未抢先提交，Host 不得继续用户目标，Run 应按 policy 收口到 `CANCELLED` 或 `LOST`。
- Host opener close 只停止当前 handle 持有的本地执行环境，不等于用户 cancel；scheduler close 不应成为 active cancel timeout closeout。
- active worker cancel registry 由 composition root 显式共享，不使用模块级 mutable singleton。

Engine design alignment:

- `docs/engine/design.md` 规定 Engine 不拥有 Session / Run lifecycle，不持久化 Host 状态，不恢复旧 Agent / Runner。
- Engine 只观察 run-local `CancellationToken`，在可中断边界产出 `run_cancelled`；如果 provider / tool / stream 卡住，Engine 可能无法返回 terminal event。
- 取消和恢复都不会复用旧 Agent 或旧 Runner；如果后续继续用户目标，必须由 Host / Service 构造新的 request。WU-LIFE-03 cancel timeout 后不得继续用户目标，也不得创建正常 recovery Attempt。
- Runner / ToolExecutor 的 cooperative cancellation 不是 Host durable terminal truth 的前置条件。

## First-principles Judgment And Direct Code Evidence

Judgment: work unit 动机成立，且严重性没有被高估。当前缺口是 Host durable truth 在 active cancel 已接受后仍依赖 worker event stream 结束或产出 terminal；这违反 “Host 强约束 lifecycle truth” 目标。但修复范围必须限制在 Host-level timeout closeout 与 diagnostic contract，不能扩大到 provider hard kill。

Direct code evidence:

- `dayu/host/command.py` 已在 `cancel_run` / `cancel_session_runs` commit 后调用 `_propagate_active_cancel_targets(...)`，通过 `ActiveWorkerRegistry` 传播 active cancel。
- `dayu/host/dispatch.py::ActiveWorkerRegistry` 只保存进程内 active worker handle，`cancel(...)` / `cancel_all(...)` 只调用 Host cancellation token 与 `LocalWorkerHandle.on_cancel(reason)`，明确是 best-effort propagation，不是 durable truth。
- `dayu/host/dispatch.py::_consume_worker_events(...)` 只在 worker 产出 terminal、clean EOF、stream error 或 ingest exception 时调用 ingest / closeout；worker/provider 卡住时该 coroutine 可能一直等待 `anext(events)`。
- `dayu/host/durable/run_transition.py::request_active_attempt_cancel_in_transaction(...)` 已实现 `RUNNING -> CANCELLING`，并且 Run 已 `CANCELLING` 时不重复追加 `RUN_CANCELLING`。
- `dayu/host/durable/run_transition.py::active_cancel_closeout_in_transaction(...)` 已支持 cooperative `run_cancelled` 后写 `ATTEMPT_CANCELLED` + `RUN_CANCELLED`，但输入要求 Engine event ref / requested / accepted / finished timestamps，不能直接表达 watchdog timeout。
- `dayu/host/durable/state.py::cancel_cancelling_run_row(...)` 已有 CAS 将 `RunStatus.CANCELLING` 收口为 `CANCELLED` 的 row helper；缺口是 watchdog-owned transition helper 与 timeout payload。
- `dayu/host/engine_ingest.py::_close_active_cancel(...)` 要求存在 `RUN_CANCELLING` payload 中的 `cancel_request_event_id`，缺失时只写 rejected diagnostic，证明 active cancel closeout 需要绑定已接受 cancel fact。
- `dayu/host/durable/run_transition.py::_invalid_terminal_precondition(...)` 当前只允许普通 terminal closeout 从 `RunStatus.RUNNING` 进入终态；`final_answer` / `run_failed` after `RUN_CANCELLING` 不应被实现放宽为成功或失败终态。
- `dayu/host/engine_ingest.py::_validate_waiting_confirmation(...)` 当前只在 `RunStatus.WAITING` + `AttemptStatus.SUSPENDED` 且存在 Host accepted wait refs 时确认 `run_suspended` / `tool_awaiting`；`CANCELLING` 下的 awaiting/suspend 只能是 diagnostic/rejected confirmation。
- `dayu/host/recovery.py::StartupRecoveryScanner` 当前会扫描 `RUNNING` / `CANCELLING`；clean close 后 owner `STOPPED` 会形成 positive orphan proof，而 `CANCELLING` 不可 recovery，现有路径会进入 `RUN_LOST`。WU-LIFE-03 必须显式调整 enabled-watchdog 场景的 recovery/watchdog 分工。
- `tests/host/test_active_cancel_dispatch.py` 与 `tests/host/test_public_cancel_smoke.py` 覆盖 cooperative active cancel 后 public terminal 可见；`tests/host/test_public_cancel_session_runs.py` 覆盖 session active cancel replay 不重复 facts。
- 现有测试没有覆盖 non-cooperative worker 卡住后的 post-cancel timeout closeout，这是本 work unit 必补的验证缺口。

Root cause: 逻辑上，Host 已把 cancel intent durable 化，但 active cancel closeout trigger 仍在 worker event consumption path；数据上，`RUN_CANCELLING` fact 没有被 Host background runtime 按 timeout policy 扫描并 CAS 收口。正确修复应把 timeout closeout 作为 Host lifecycle watchdog / supervisor 的已提交事实追平动作，而不是改变 worker/provider cancellation path。

## Affected Files / Modules

Implementation may touch:

- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `dayu/host/command.py` only if option wiring or shared registry handoff requires a narrow change.
- `dayu/host/recovery.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_startup_recovery.py` or the existing recovery test module that owns `StartupRecoveryScanner` behavior.
- `tests/host/test_engine_ingest_mapping.py`

Files to read but not necessarily modify:

- `docs/host/design.md`
- `docs/engine/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- root `README.md`

This plan gate only writes this artifact. Implementation must not treat this list as permission to make README changes automatically; README trigger checks are described below.

## Contract / Schema / State-machine / Public-interface Changes

Durable schema: no table, index, column, or schema version change is required. Timeout policy can be construction-time config; timeout closeout can be represented by existing EventLog terminal events plus payload fields.

Host public API: no new command method and no change to `cancel_run(...)` / `cancel_session_runs(...)` request or response shape.

OpenHost construction-time interface: add one narrowly scoped timeout policy field only if implementation cannot reuse an existing Host local execution policy owner. Preferred shape:

- `OpenHostOptions.active_cancel_timeout_seconds: float | None`
- `HostLocalExecutionOptions.active_cancel_timeout_seconds: float | None`

Semantics: `None` disables background timeout closeout for test/special assembly; positive finite number enables timeout. The field is construction-time Host runtime policy, not per-run override. It must validate as positive finite float when not `None`.

Watchdog scan interval interface: do not add a second public interval field unless existing assembly makes it impossible to reuse an existing Host runtime interval. Preferred owner is existing `dispatch_poll_interval_seconds`; tests should mostly call the deterministic tick method directly. If a loop-level override is necessary, it must remain construction-time Host runtime policy and must validate as positive finite float. The scan interval only bounds detection latency after the timeout threshold has elapsed; it must not change the timeout threshold itself.

Public event / read API: no new user-facing HostEvent kind is required. Watchers should observe existing cancelled terminal projection when timeout closeout writes `RUN_CANCELLED`.

EventLog event types: no new canonical terminal type is required. Use existing:

- `ATTEMPT_CANCELLED`
- `RUN_CANCELLED`

Optional diagnostic event: do not add a new canonical event type unless implementation evidence shows terminal payload cannot carry enough diagnostic. Preferred design is to include timeout diagnostic fields in existing terminal payloads and logs.

Payload compatibility: timeout payload fields are additive diagnostic fields on existing terminal events. They must not replace existing payload fields or EventLog reason fields consumed by read/projection/outbox/watch paths. Public cancelled projection and Run snapshots must keep the same user-facing terminal shape as cooperative cancel.

State-machine change:

- Existing: `RUNNING + Attempt RUNNING -> CANCELLING`, then cooperative Engine event can close to `CANCELLED`.
- New timeout path: `CANCELLING + current Attempt RUNNING + active cancel timeout elapsed + no terminal refs -> Attempt CANCELLED + Run CANCELLED`.
- Timeout closeout is a first-committer-wins CAS. If any terminal closeout, awaiting/suspend, lost closeout, or cooperative cancel wins first, watchdog observes CAS miss / invalid state and writes no second terminal fact.
- Timeout closeout after durable cancel means Host policy chooses `CANCELLED`, not `LOST`, for this work unit. Reason: user cancel intent is durable accepted, Host must not continue user goal, and timeout here means provider/worker non-cooperation rather than unknown user-request failure. `LOST` remains recovery/orphan positive-proof policy for unavailable owner or unrecoverable facts.

Run / Attempt terminal policy:

- Post-cancel timeout writes `AttemptStatus.CANCELLED` and `RunStatus.CANCELLED`.
- `RUN_CANCELLED.reason.reason` and `ATTEMPT_CANCELLED.reason.reason` use stable reason `active_cancel_timeout`.
- Terminal payload must include at least: `run_id`, `terminal_attempt_id`, `attempt_terminal_event_id`, `dispatch_record_id`, `cancel_request_event_id`, `reason`, `timeout_seconds`, `cancel_requested_at`, `timed_out_at`, `watchdog_owner`, `worker_lifecycle_signal`, `last_observed_worker_event_index` when available, and `last_accepted_event_id` when available.
- `dispatch_record_id` comes from the existing dispatch record lookup by `attempt_id`, matching the cooperative `active_cancel_closeout_in_transaction(...)` pattern; do not invent a registry-only or payload-only source.
- If exact worker event index is unavailable without widening registry state, use `null` for optional fields and do not invent fake values.

LLM-facing text: no prompt, tool schema, memory, compact, evidence, or tool message content should change. Diagnostic payload is Host-readable and may contain ids as references; if later projected to LLM-facing material, it must be rewritten into business-readable semantics under AGENTS.md LLM-facing constraints.

## Implementation Decisions

Watchdog owner:

- Owner is Host background lifecycle supervisor direction under #87, implemented as a minimal active-cancel watch target owned by dispatch/open_host runtime.
- Do not create a separate global watchdog runtime, module singleton, or Service-owned loop.
- Preferred code shape is a small Host-owned supervisor/tick component in `dayu/host/dispatch.py` or a narrowly named Host lifecycle module if existing dispatch module becomes unwieldy. It receives transaction runner, EventLogStore, wakeup port, timeout policy, deterministic UTC now provider, and id generation through construction.
- Watchdog scan source is durable SQL state: scan current `CANCELLING` runs with current `RUNNING` Attempt and accepted dispatch record. Do not introduce an in-memory tracking set for cancelling runs; cancel commit wakeup is only a latency optimization.

Timeout config owner:

- Construction-time Host runtime option owns the timeout. It is not Engine `AgentPolicy`, not provider config, and not per-run request payload.
- Default value should be conservative and production-safe when open_host is used from packaged defaults. If existing tests require deterministic fast timeout, tests should pass explicit small values.
- If config loader later maps `host_runtime.json`, that mapping belongs to a later implementation/config phase unless current code already maps all OpenHostOptions fields there.

Watchdog scheduling model:

- Use a deterministic `tick(now)` method plus hybrid runtime loop.
- `tick(now)` performs one SQL scan and zero or more timeout closeouts; focused tests call this directly without sleeping.
- Runtime loop wakes immediately after `cancel_run` / `cancel_session_runs` commits or replays an active cancel target, and also runs a periodic fallback scan using the configured interval.
- The periodic fallback is required so a lost wakeup or crash between commit and wakeup cannot leave `CANCELLING` suspended until another cancel command.
- Default interval owner is existing Host local execution `dispatch_poll_interval_seconds` unless implementation introduces a narrower construction-time watchdog interval for a concrete reason. Tests may override the interval for loop tests, but timeout correctness tests should drive `tick(now)` directly.
- Interval controls detection latency only. Timeout eligibility is computed from durable `RUN_CANCELLING` / linked `CANCEL_REQUESTED` UTC timestamp plus the injected/current Host UTC clock.

Clock policy:

- Watchdog and timeout helper tests must use an injectable UTC now provider; do not depend on real sleeps or wall-clock races.
- Production comparison uses durable UTC event timestamps written in EventLog and current Host UTC time from the now provider.
- Cross-instance UTC clock skew can make reopen timeout detection slightly early or late; this is a bounded residual risk owned by Host lifecycle watchdog runtime tuning under #87, not a reason to change the terminal policy.

Timeout closeout terminal choice:

- Use `RUN_CANCELLED` / `ATTEMPT_CANCELLED`, not `RUN_LOST` / `ATTEMPT_LOST`, because cancel intent is known and accepted. Host is not claiming the worker physically stopped; it is declaring the user-visible Run cancelled and quarantining later output through first-committer-wins ingest.
- Do not create recovery Attempt after timeout closeout. Continuing the user goal after user cancel would violate cancel semantics.

Diagnostic payload:

- Timeout closeout uses an independent `ActiveCancelTimeoutCloseoutInput` and independent `active_cancel_timeout_closeout_in_transaction(...)`; it must not extend or overload `ActiveCancelCloseoutInput`, because timeout closeout has no Engine `engine_event_ref`, `accepted_at`, or `finished_at`.
- Reuse existing row CAS helpers (`cancel_running_attempt_row(...)`, `cancel_cancelling_run_row(...)`) and existing dispatch record lookup by attempt id, but build timeout-specific `ATTEMPT_CANCELLED` / `RUN_CANCELLED` EventLog requests and payloads.
- For timeout closeout, add fields listed in contract section. `watchdog_owner` should be a stable text such as `host.active_cancel_watchdog`; `worker_lifecycle_signal` should be `active_cancel_timeout`.
- Do not expose provider/tool hard-kill status. WU-TOOLS-CANCEL-01 may later add richer execution-boundary diagnostics, but it must not redefine this Host terminal policy.

Late terminal handling:

- Cooperative `run_cancelled` before timeout: accepted by existing active cancel closeout; watchdog later sees terminal state and does nothing.
- `final_answer` after `RUN_CANCELLING`: reject as late terminal after active cancel, append only rejected diagnostic such as `late_terminal_after_active_cancel`, and write no `ATTEMPT_SUCCEEDED` / `RUN_SUCCEEDED`. Do not rely on a later CAS failure to express this policy.
- `run_failed` after `RUN_CANCELLING`: reject as late terminal after active cancel, append only rejected diagnostic such as `late_terminal_after_active_cancel`, and write no `ATTEMPT_FAILED` / `RUN_FAILED`. Recoverable failure must not trigger recovery or continue the user goal after durable cancel.
- `run_suspended` / `tool_awaiting` after `RUN_CANCELLING`: reject/diagnose as waiting confirmation without Host accepted wait refs; write no wait record, no `RUN_WAITING`, no `ATTEMPT_SUSPENDED`, and do not move Run to `WAITING`.
- Worker terminal after timeout closeout: rejected as terminal already closed; no new canonical terminal fact.

Recovery scanner and watchdog ordering:

- When active cancel watchdog is enabled, watchdog owns all `CANCELLING` runs that have durable `RUN_CANCELLING` / `CANCEL_REQUESTED` facts. `StartupRecoveryScanner` must skip/defer those runs to watchdog and must not convert them to `LOST` before timeout policy is applied.
- Startup/reopen sequence with watchdog enabled:
  1. Construct the watchdog with the same transaction runner / EventLogStore / wakeup port / clock used by Host runtime.
  2. Run one deterministic watchdog startup tick before `StartupRecoveryScanner.scan()` so already timed-out `CANCELLING` runs close as `CANCELLED`.
  3. Run `StartupRecoveryScanner.scan()` with a policy/dependency that defers remaining `CANCELLING` runs with accepted cancel facts to watchdog, even when owner liveness is `STOPPED`.
  4. Start the watchdog runtime loop so not-yet-timed-out deferred runs are closed by a later tick.
- Clean-close-reopen owner `STOPPED`: if watchdog is enabled, a `CANCELLING` run with accepted cancel facts must stay under watchdog ownership and close to `CANCELLED` once timeout is elapsed; recovery must not write `ATTEMPT_LOST` / `RUN_LOST` for it.
- Crash/inconclusive orphan: if watchdog is enabled, the same timeout policy applies. Inconclusive or still-live owner proof may make recovery skip the run, but watchdog may still close it as `CANCELLED` after timeout because user cancel was durable accepted.
- Watchdog disabled (`active_cancel_timeout_seconds is None`): recovery keeps existing ownership for startup orphan policy. Positive orphan proof may close `CANCELLING` as `LOST`, and inconclusive owner proof may leave it `CANCELLING`; this is an explicit special/test assembly opt-out, not production default behavior.

Session cancel replay:

- Existing `cancel_session_runs` replay must continue to avoid duplicate facts.
- Replay while Run is still `CANCELLING` should still propagate cancel through `ActiveWorkerRegistry`.
- Replay after timeout closeout should return terminal `CANCELLED` snapshot and not propagate cancel to an unregistered / terminal worker.

Scheduler close boundary:

- Scheduler close may cancel active in-process tasks and call `ActiveWorkerRegistry.cancel_all("scheduler_close")` as local cleanup, but it must not append `RUN_CANCELLED`, `RUN_FAILED`, `RUN_LOST`, or timeout closeout facts.
- If Host closes before timeout fires, reopening Host with watchdog enabled scans existing `CANCELLING` runs and applies timeout based on durable `RUN_CANCELLING` / `CANCEL_REQUESTED` timestamps; recovery must not consume those runs first.

Why this is not over-designed:

- It adds one Host-owned watch target over an existing durable state (`CANCELLING`) and existing terminal facts.
- It does not introduce provider registry, kill API, execution capsule, lease/fencing, new public commands, new EventLog taxonomy, or schema tables.
- It keeps timeout policy at construction-time Host runtime boundary, matching existing scheduler / wait poller assembly style.
- It relies on CAS and existing first-committer-wins semantics instead of inventing a new reconciliation protocol.

## Implementation Slices

### Slice 1: Durable Timeout Closeout Contract And Race Tests

Objective: Add the internal state-machine helper and focused durable/ingest tests that make post-cancel timeout terminal policy explicit without starting a background loop.

Allowed files/modules:

- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_engine_ingest_mapping.py`

Exact changes:

- Add a typed internal input dataclass, e.g. `ActiveCancelTimeoutCloseoutInput`, with complete Chinese docstring and strictly typed fields.
- Implement `active_cancel_timeout_closeout_in_transaction(...)` as a distinct helper; do not overload `active_cancel_closeout_in_transaction(...)`.
- Reuse `cancel_running_attempt_row(...)` and `cancel_cancelling_run_row(...)` for CAS terminal mutation.
- Lookup `dispatch_record_id` with the existing dispatch-record-by-attempt reader; fail closed if no accepted dispatch record exists.
- Read latest `RUN_CANCELLING` and require a valid `cancel_request_event_id`. If missing or malformed, return rejected/invalid state or raise structured durable error according to existing transition helper style; do not write partial terminal facts.
- Append `ATTEMPT_CANCELLED` then `RUN_CANCELLED` with reason `active_cancel_timeout` and timeout payload fields.
- Add replay behavior only for same terminal status if needed by tests. Do not accept mismatched terminal pairs.
- Add or tighten ingest preconditions so `final_answer` and `run_failed` after `RUN_CANCELLING` are rejected with diagnostic and write no canonical terminal facts. Keep `run_cancelled` accepted only through active cancel closeout.
- Ensure active cancel closeout preconditions absorb/reject late terminal candidates after timeout closeout.

State transitions:

- Input state: `RunStatus.CANCELLING`, `AttemptStatus.RUNNING`, `run.current_attempt_id == attempt_id`, dispatch record worker accepted, terminal refs unset.
- Output state: `RunStatus.CANCELLED`, `AttemptStatus.CANCELLED`, terminal refs set.
- CAS miss / invalid state: no new EventLog terminal facts.

Tests:

- `test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts`: seeds active Run, requests active cancel, invokes timeout helper, asserts `ATTEMPT_CANCELLED` + `RUN_CANCELLED`, Run/Attempt statuses, payload fields, and reason.
- `test_active_cancel_timeout_closeout_requires_cancelling_run`: active `RUNNING` without cancel fact is rejected and writes no terminal facts.
- `test_active_cancel_timeout_closeout_first_committer_wins_after_cooperative_cancel`: cooperative cancel closes first; timeout helper writes no second terminal.
- `test_active_cancel_timeout_closeout_rejects_after_succeeded_terminal`: final terminal closes first; timeout helper writes no second terminal.
- `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic`: active cancel wins first; late `final_answer` writes no success terminal and records rejected diagnostic.
- `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic`: active cancel wins first; late `run_failed` writes no failure terminal and records rejected diagnostic.
- `test_late_worker_terminal_after_timeout_is_rejected_as_terminal_closed`: worker terminal after timeout returns rejected diagnostic / no canonical terminal duplicate.
- `test_late_awaiting_after_cancel_does_not_move_to_waiting`: add or keep ingest mapping coverage proving late `run_suspended` / `tool_awaiting` after `RUN_CANCELLING` only writes waiting rejected diagnostic and cannot move Run to `WAITING`.

Completion signal:

- Focused durable transition and ingest tests pass.
- No public API or schema changes are required by this slice.

Stop condition:

- Stop if the helper cannot determine `cancel_request_event_id` from existing EventLog facts without adding durable columns or changing `RUN_CANCELLING` payload contract. That would require design-source update.
- Stop if tests show Host design is insufficient to choose `CANCELLED` vs `LOST`; do not invent another terminal policy.

### Slice 2: Host Lifecycle Watchdog Integration And Public Behavior

Objective: Wire the timeout helper into Host background lifecycle supervision so non-cooperative active cancel converges without worker/provider cooperation.

Allowed files/modules:

- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `dayu/host/command.py` only for narrow shared-registry or option wiring if required.
- `dayu/host/recovery.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_startup_recovery.py` or the existing recovery test module that owns `StartupRecoveryScanner` behavior.

Exact changes:

- Add validated construction-time timeout option if not already available from an existing local execution policy.
- Add a Host-owned active cancel watchdog tick/loop. Minimal acceptable shape:
  - use a SQL query over durable current `CANCELLING` runs with current `RUNNING` Attempt and accepted dispatch record; do not maintain an in-memory tracking set;
  - compute elapsed time from latest `RUN_CANCELLING` or linked `CANCEL_REQUESTED` timestamp;
  - if elapsed < timeout, do nothing;
  - if elapsed >= timeout, call the Slice 1 timeout closeout helper in a short write transaction;
  - after successful terminal closeout, wake queue promotion and projection just like other terminal closeouts.
- Implement the watchdog as a reusable deterministic tick method plus runtime loop. Tests must be able to invoke tick with injected UTC now without sleeping.
- Runtime loop must support cancel-commit wakeup and periodic fallback scan. Reuse `dispatch_poll_interval_seconds` as default interval owner unless a narrower construction-time watchdog interval is introduced with validation and tests.
- Register active cancel watchdog under existing Host lifecycle/scheduler/open_host runtime. Do not create a module global loop.
- On `cancel_run` / `cancel_session_runs` commit that produces or replays an active cancel target, wake the watchdog in addition to best-effort active registry propagation.
- Ensure startup/reopen path handles already `CANCELLING` runs before recovery can mark them `LOST`: enabled watchdog runs one startup tick before recovery scan, and recovery scan defers accepted-cancel `CANCELLING` runs to watchdog.
- If watchdog is disabled, leave startup recovery's existing `CANCELLING` orphan behavior in place and document the opt-out in tests.
- Ensure `HostDispatchScheduler.close()` does not run timeout closeout as part of close. It can stop the loop and release local resources only.

State transitions:

- With watchdog enabled, `CANCELLING` remains active until cooperative cancel wins, timeout closeout wins, or an earlier terminal already committed before cancel. Recovery positive orphan policy must not close accepted-cancel `CANCELLING` runs before watchdog policy.
- With watchdog disabled, existing recovery positive orphan behavior remains the owner for orphan `CANCELLING` runs.
- Timeout closeout releases active slot and triggers normal queued promotion.
- After timeout terminal, late worker output must not mutate canonical Run / Attempt terminal truth.

Tests:

- `test_active_cancel_watchdog_times_out_non_cooperative_worker`: start active worker whose event stream hangs after cancel, call cancel, trigger watchdog/tick or use small timeout, assert Run becomes `CANCELLED` and Attempt `CANCELLED` without worker terminal.
- `test_active_cancel_timeout_promotes_queued_run`: queued follow-up is promoted after timeout closeout releases active slot.
- `test_active_cancel_watchdog_noops_before_timeout`: cancel active Run, tick before timeout, assert still `CANCELLING` and no terminal facts.
- `test_active_cancel_watchdog_zero_cancelling_runs_noops`: SQL scan handles empty result without errors.
- `test_active_cancel_watchdog_multiple_cancelling_runs_closes_each_eligible_run`: SQL scan handles multiple eligible `CANCELLING` runs and does not depend on an in-memory set.
- `test_active_cancel_watchdog_reopen_closes_existing_cancelling_run`: clean-close Host while active Run is `CANCELLING`, reopen with watchdog enabled after timeout, owner liveness is `STOPPED`, assert Run closes `CANCELLED` and not `LOST`.
- `test_active_cancel_watchdog_reopen_defers_not_yet_timed_out_cancelling_run`: clean-close/reopen before timeout, recovery scanner defers accepted-cancel `CANCELLING` to watchdog and writes no `RUN_LOST`.
- `test_startup_recovery_watchdog_disabled_keeps_existing_cancelling_orphan_policy`: with watchdog disabled, recovery remains owner; positive orphan proof may close `CANCELLING` as `LOST` or inconclusive proof may leave it `CANCELLING`.
- `test_active_cancel_watchdog_reopen_crash_inconclusive_eventually_closes_cancelled`: crash/inconclusive owner proof does not block enabled watchdog timeout closeout.
- `test_cancel_session_replay_repropagates_before_timeout_without_new_facts`: preserve existing replay behavior while still `CANCELLING`.
- `test_cancel_session_replay_after_timeout_does_not_append_or_propagate`: replay after timeout returns terminal snapshot and does not create new cancel facts.
- `test_scheduler_close_does_not_write_active_cancel_timeout_terminal`: closing scheduler/Host while active Run is `CANCELLING` writes no `RUN_CANCELLED` by close itself; timeout closeout only occurs through watchdog tick/loop policy.
- Public smoke: watch session events sees `HostEventKind.CANCELLED` after timeout closeout; `get_run` / public projection returns cancelled Run snapshot without depending on new diagnostic fields.

Completion signal:

- Non-cooperative active cancel converges in deterministic focused tests.
- Existing cooperative cancel tests still pass.
- Public watch sees cancelled terminal from timeout closeout.
- Scheduler close tests prove close boundary remains separate from cancel timeout.
- Recovery tests prove clean-close-reopen with enabled watchdog cannot convert accepted cancel to `LOST` before watchdog policy.

Stop condition:

- Stop if integrating watchdog requires a second independent runtime outside existing Host scheduler/open_host lifecycle.
- Stop if deterministic tests cannot use an injectable UTC now provider and direct tick entry point; do not sleep real timeout longer than focused test budget.
- Stop if implementation requires provider/tool kill API; that belongs to WU-TOOLS-CANCEL-01.

## Tests / Validation Commands And Expected Assertions

Plan-only gate validation:

```bash
git diff --check
```

Implementation focused validation should run after code changes:

```bash
source .venv/bin/activate
pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py -q
pyright
git diff --check
```

Expected assertions:

- timeout closeout writes exactly one `ATTEMPT_CANCELLED` and one `RUN_CANCELLED`.
- timeout closeout payload includes cancel request ref, timeout seconds, timeout timestamp, watchdog owner, and lifecycle signal.
- no duplicate terminal facts under cooperative cancel / timeout / late terminal races.
- final answer, failure, and suspended/awaiting after `RUN_CANCELLING` follow the explicit reject/diagnostic rules above.
- non-cooperative worker timeout releases active slot and promotes queued Run.
- watchdog SQL scan handles zero, one, and multiple `CANCELLING` runs.
- clean-close-reopen owner `STOPPED` with enabled watchdog closes accepted cancel as `CANCELLED`, not `LOST`.
- public watcher/projection/outbox paths tolerate additive timeout payload fields.
- `cancel_session_runs` replay does not append facts and preserves repropagation before timeout.
- scheduler close writes no user cancel or timeout terminal facts.
- pyright reports no new or expanded type errors.

## Docs Decision

This plan artifact is the only file to modify in the current plan gate.

Implementation README/design trigger decision:

- `docs/host/design.md`: implementation should check whether the existing cancel section is already sufficient. If code introduces `active_cancel_timeout_seconds` or a new timeout payload contract not already described, update Host design source before or with implementation; otherwise no design update is required.
- `dayu/host/README.md`: implementation touches `dayu/host/`; read its Agent update constraints and update only if Host runtime options, lifecycle behavior, or public diagnostics change for readers.
- `tests/README.md`: implementation touches `tests/host/`; read constraints and update only if test organization or required validation entry points change.
- root `README.md`: no expected update unless user-visible CLI/Web/WeChat workflow, install/config command, log location, or final-user troubleshooting changes. This WU is Host internal lifecycle hardening, so root README likely does not need update.

## Risks / Open Questions

Blocking open questions: none. Host design and Issue #91 scope are sufficient to choose watchdog owner, timeout config owner, terminal policy, late race behavior, replay behavior, scheduler close boundary, and diagnostic payload direction.

Residual risks:

- Risk: timeout `CANCELLED` does not physically stop provider/tool work; old side effects may continue outside Host. Owner / destination: WU-TOOLS-CANCEL-01.
- Risk: timeout default value needs production tuning across providers and local/remote worker backends. Owner / destination: Host runtime config follow-up under GitHub Issue #87 if packaged defaults prove insufficient.
- Risk: timeout detection compares durable UTC event timestamps from one Host instance with current UTC time from another instance after reopen; clock skew may make detection early or late by the skew amount. Owner / destination: Host lifecycle watchdog runtime tuning under GitHub Issue #87.
- Risk: disabling active cancel watchdog is an explicit special/test assembly opt-out; orphaned `CANCELLING` runs can still follow recovery `LOST` / inconclusive behavior instead of timeout `CANCELLED`. Owner / destination: Host runtime assembly policy under GitHub Issue #87.
- Risk: richer diagnostic for exact blocked boundary, such as HTTP request abort vs tool subprocess hang, is not available from Host-only timeout. Owner / destination: WU-TOOLS-CANCEL-01 and Tool Trace diagnostics lane #70 / #34 / #119 / #71.
- Risk: WU-WAIT-04 still needs product-level E2E confirmation of user-visible cancel recovery. Owner / destination: WU-WAIT-04 after WU-LIFE-03 and WU-TOOLS-CANCEL-01.

## Completion Report Format

Implementation / review agents should report:

- artifact path
- plan decision: ready / blocked
- proposed slice count and rationale
- validation run
- blocking open questions
- residual risks with owner / destination

Plan decision for this artifact: ready.
