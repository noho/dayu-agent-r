# WU-LIFE-01 + WU-LIFE-02 Recovery / Scheduler Lifecycle Plan

## Gate / Role

- **Gate**: WU-LIFE-01 + WU-LIFE-02 joint planning gate
- **Controller**: AgentController
- **Role**: planning specialist；只写 code-generation-ready plan，不实现代码，不做 review，不提交，不 push，不创建 PR。
- **Branch**: `feat/host-life-recovery-scheduler-hardening`
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Discussion / code inspection artifact**: `docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md`
- **Controller adjudication artifact**: `docs/reviews/wu-life-01-02-discussion-controller-adjudication-20260601.md`
- **Plan output**: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`

## Goal / Motivation

本 work unit 的目标是把 Host recovery lifecycle 与 scheduler close / `cancel_all` lifecycle 的剩余风险转化为可执行、可验证、可 review 的 proof matrix 和 focused regression tests。默认实现路径是测试与证明补强，不预设 recovery 或 scheduler close 生产逻辑重写。

动机成立，但严重性不应被扩大：

- `docs/host/design.md` 第 27 节已经明确 Host startup recovery 只基于 durable truth 与 positive orphan proof；旧 Attempt 不 takeover；恢复必须创建新 Attempt；`ACCEPTED` / `QUEUED` / `WAITING` startup scan 不得被推进到 `RECOVERING`。
- 同一设计节明确 projection checkpoint、read model、audit、tool trace、outbox、memory snapshot lag 都不是 recovery truth；需要 fresh durable truth 的 recovery / scheduler / governance decision 必须使用新的短事务。
- Host opener close 语义已经裁决为 handle lifecycle，不是用户 cancel。close 后 API fail-fast；close 自身不得写 `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED`、`RUN_LOST` 等伪装用户意图或确认失败的 terminal canonical fact。
- discussion/code inspection 证明现有代码已经具备 startup scan、positive orphan proof、open_host startup recovery、scheduler close、active worker cancel、lane close、close 后 fail-fast 等机制。真实风险集中在 proof matrix 缺失、scanner still-live / inconclusive 集成证明缺口、`WAITING` startup diagnostic-only 用户可见语义缺口、close 中途取消、queue 非空不无限 drain、`cancel_all` 快照窗口和 close window 不写 terminal fact 的 focused tests 不足。

因此本 plan 的第一性原理判断是：当前最佳实践不是重写 Host recovery / scheduler close，而是用矩阵化证据收敛现有语义，并只在新增 tests-first 证明 reason 不可区分、diagnostic payload 不足、状态转换不稳定、资源泄漏或 terminal fact 误写时，允许最小生产修复。

## Non-goals / Scope Boundary

- 不修改 durable schema，不新增 / 修改表、索引、column、CHECK、FK，不 bump schema version。
- 不新增或修改 EventLog event type，不改 canonical fact 语义。
- 不修改 Host public API、Service-facing API、`open_host()` contract、public dataclass 或 `dayu.host` public exports。
- 不修改 Run / Attempt 状态机，不改变 `WAITING` durable 语义。
- 不让 close 写用户 cancel、failed 或 lost terminal fact；close 仍是本地 handle / scheduler lifecycle。
- 不实现旧 Attempt / Engine / Agent / Runner / provider request takeover。
- 不引入 lease、fencing、remote ownership、global registry closed state 或通用 lifecycle framework，除非 tests-first 直接证明现有边界无法满足设计真源且 controller 接受 scope 变更。
- 不把 close 设计成 drain-until-empty；dispatch / promotion 的 durable pending 状态由下一次 open 的 recovery / promotion / dispatch 解释。
- 不把 projection checkpoint、read model、memory snapshot、audit、tool trace、outbox 或 stress summary 提升为 recovery truth。
- 不扩大为 stress / fuzz / soak；`tests/host/test_host_production_stress.py` 只作为现有非默认 stress evidence，不进入本 work unit 默认 validation。
- 不把 RR-DUR-01 的真实多进程 projection checkpoint CAS race 纳入 implementation scope。
- Planning specialist 本轮只允许创建或更新本 plan artifact；implementation agent 后续只能按 slice allowed files 工作。

## Direct Evidence Summary

### Recovery 生产代码证据

- `dayu/host/open_host.py::_OpenHostContextManager.__aenter__` 在 scheduler 打开后、public Host ready 前构造 `StartupRecoveryScanner(..., dispatch_wakeup_port=scheduler, recovery_owner_host_instance_id=scheduler.host_instance_id).scan()`，证明 public opener startup recovery 已接入。
- `dayu/host/recovery.py::StartupRecoveryScanner.scan()` 在单个 `transaction_runner.run_write()` operation 内读取 `read_non_terminal_runs()` 并分类；commit 后才 wake dispatch / queue promotion，没有把 projection 或长 read transaction 当 recovery truth。
- `dayu/host/recovery.py::StartupRecoveryScanner._classify_run()` 对 `ACCEPTED` / `QUEUED` 只追加 promotion wake；对 `WAITING` 返回 `WAITING_DIAGNOSTIC_ONLY`，reason 为 `waiting_adapter_observation_unavailable`，不创建 Attempt、不推进 `RECOVERING`。
- `dayu/host/recovery.py::StartupRecoveryScanner._classify_active_or_cancelling()` 只有 `PositiveOrphanProof` 才进入 `_close_positive_orphan()`；`OwnerStillLive` 返回 `OWNER_STILL_LIVE`，`OrphanProofInconclusive` 返回 `ORPHAN_INCONCLUSIVE`。
- `dayu/host/recovery_process.py::classify_orphan_candidate()` 对 missing owner、missing liveness、recent heartbeat、probe error、pid live without identity proof 返回 still-live / inconclusive；只有 stopped owner、stale + pid missing、pid reused start token mismatch、boot id mismatch 等 positive proof 才允许 recovery closeout。
- `dayu/host/recovery.py::_close_positive_orphan()` positive orphan 且 recoverable 时通过 `close_startup_orphan_attempt_in_transaction()` 写 `ATTEMPT_LOST` + `RUN_RECOVERING`，随后创建新 Attempt / execution / dispatch；`CANCELLING` orphan 以 `cancel_in_flight_attempt_lost` 收口为 `RUN_LOST`。
- `dayu/host/recovery.py::_classify_recovering()` 通过 EventLog 统计 recovery dispatch 次数，超过 `recovery_dispatch_limit` 后以 `startup_recovery_dispatch_limit_exceeded` 收口为 `RUN_LOST`。
- `dayu/host/engine_ingest.py` 与 `tests/host/test_recovery_dispatch.py` 已证明 recovery 新 Attempt 创建后，旧 execution late terminal event 被 reject，不进入 canonical facts。

### Scheduler close / cancel_all 生产代码证据

- `dayu/host/open_host.py::Host.close()` 先置 `_closed = True`，再 `await self._scheduler.close()`，最后在 `finally` 中执行 projection catch-up 与 command handle close；重复 close 直接 return。
- `dayu/host/open_host.py::_raise_if_closed()` 被 public Host API 入口调用，close 后 public API fail-fast。
- `dayu/host/dispatch.py::HostDispatchScheduler.wake_dispatch()`、`wake_queue_promotion()`、`run_queue_promotion()`、`drain_once()` 在 `_closed` 为真时抛 `RuntimeError("HostDispatchScheduler is closed")`。
- `dayu/host/dispatch.py::HostDispatchScheduler.close()` 先置 `_closed = True`，best-effort mark host instance stopping，取消 heartbeat / dispatch drain / promotion drain task，调用 `ActiveWorkerRegistry.cancel_all("scheduler_close")`，取消 active tasks，关闭 lane controller，清理 duplicate governance registry，best-effort mark stopped。
- `dayu/host/dispatch.py::ActiveWorkerRegistry.cancel_all()` 在锁内复制当前 entries tuple 后释放锁并逐个传播取消；这是快照取消语义，不关闭 registry，也不阻止后续 register。
- `dayu/host/dispatch.py::_consume_worker_events()` 在 `finally` 中 unregister active worker、close handle、release lane token；close 取消 active task 后依赖该 finally 收口资源。
- `dayu/host/dispatch.py::_consume_worker_events()` 对 clean EOF 只有在 `cancellation_token.is_cancelled() and not self._closed` 时才映射为 cancelled closeout；scheduler close 期间 `_closed=True`，close 自身不应把 active worker EOF 伪装为 user cancel。
- `dayu/host/dispatch.py` 的 lane acquire close path 在 `self._closed` 为真时返回 skipped，不写 worker startup timeout terminal fact。

### 已有测试证据

- `tests/host/test_recovery_orphan_classifier.py` 覆盖 owner / liveness / process evidence classifier 的 still-live、inconclusive、positive proof 分支。
- `tests/host/test_recovery_scan.py` 覆盖 RUNNING positive orphan 进入 `RECOVERING` 且不依赖 projection lag、`WAITING` diagnostic-only、CANCELLING orphan 写 `ATTEMPT_LOST` / `RUN_LOST`、`ACCEPTED` / `QUEUED` 不写 recovery fact 只 wake promotion、`RECOVERING` 超过 dispatch limit 后 LOST、Session row 缺失时不凭残留 Run row 写 recovery facts。
- `tests/host/test_recovery_dispatch.py` 覆盖 positive orphan startup scan 创建新 Attempt / execution / dispatch 并 wake、旧 execution late final answer reject、orphan closeout 后 recovery dispatch invalid-state 时留下 `RECOVERING_READY`。
- `tests/host/test_open_host_runtime.py` 覆盖 public `open_host` startup recovery：interrupted Run 和 graceful close 后 Run 均在 reopen 时创建新 Attempt 并通过 watch 观察最终 answer；也覆盖 scheduler close 抛错时 command handle 仍 close、projection 仍 flush。
- `tests/host/test_recovery_multiprocess.py` 覆盖 live owner 不误杀、owner crash 后 public Host event stream 可观察恢复 final answer、projection lag 下仍以 durable EventLog / Run / Attempt / dispatch rows 恢复。
- `tests/host/test_public_lifecycle_smoke.py` 覆盖 host close 幂等、close 后 public API 抛 `HostClosedError`、host close 不关闭 open Session、不写 terminal facts、reopen 后 Run 仍为 RUNNING。
- `tests/host/test_dispatch_scheduler.py` 覆盖 close 不被 active handle cancel / close 异常打断、close 只发 cancel 且 handle close 由 active task finally 执行一次、close during active events 释放 lane / registry / handle、promotion task 被 close 取消、wake methods after close fail、close 幂等、durable retry exhausted requeue 不写 terminal closeout、worker startup timeout reason、clean EOF / stream error closeout、terminal 后关闭 stream 不读 late event。
- `tests/host/test_public_cancel_session_runs.py` 覆盖 `cancel_session_runs` 的 QUEUED / pre-dispatch / active worker / WAITING / RECOVERING 子集、幂等重放、空集不写 EventLog，证明 public cancel 是用户意图，与 scheduler close lifecycle cancel 分离。

## Contract / Schema / State-machine / Public-interface Changes

默认 **none**：

- **Durable schema**: none。
- **EventLog event type / payload contract**: none。
- **Host public API / Service-facing behavior**: none。
- **Run / Attempt state machine**: none。
- **`WAITING` durable semantics**: none。
- **Close terminal fact boundary**: none；close 不写 cancel / failed / lost terminal facts。
- **Recovery truth source**: none；仍只使用 durable Run / Attempt / EventLog / dispatch / wait / payload / liveness truth，不使用 projection / read model / memory lag。

必须停止并回报 controller 的 contract stop condition：

- 新增测试证明必须改变 `WAITING` startup recovery 语义、close user-visible behavior、Host public API、EventLog fact、Run / Attempt 状态机或 durable schema 才能满足验收。
- 新增测试证明 scheduler close 中途取消需要改变 public lifecycle guarantee，而不是在现有 close contract 下做最小 cleanup hardening。
- 新增测试证明 recovery scanner 依赖 projection / read model / stale long read transaction 才能工作，或 production governance path 持有长 read transaction 做 fresh truth decision。
- 任何修复需要新增 lease / fencing / remote ownership / global registry closed state 等新抽象。

## Implementation Decisions

### Plan-Level Decisions

- Implementation agent 必须 tests-first：先补 proof matrix 与 focused tests；只有测试直接失败且失败对应本计划 stop condition 允许的最小生产修复，才修改生产代码。
- Proof matrix 用测试参数矩阵和清晰测试名承载，不新增单独 machine-readable schema。若需要 human-readable mapping，可在测试文件顶部或 helper 常量中用私有 tuple/dataclass 表达，避免 runtime schema 或 docs-only truth。
- 所有新增 test helper 默认放在对应 test module 的模块级私有 helper；禁止无必要嵌套函数 / 嵌套类，禁止 broad `Any` / untyped signatures。
- 若需要触碰生产代码，优先修改当前 owner 函数内部的 cleanup / diagnostic / reason 稳定性，不新增公共 facade / wrapper / compatibility layer。
- RR-DUR-04 只进入 proof matrix：逐项证明 recovery、queue promotion、dispatch recheck、active cancel、scheduler close、worker event ingest、compaction 外部调用不使用长 read transaction 或 projection lag 作为 governance truth。除非测试或直接代码证据证明某路径违规，否则不改生产代码。
- RR-DUR-01 在本 work unit 关闭，不进入 scope：recovery scanner 不依赖 projection checkpoint；现有 recovery projection-lag 测试与 deterministic checkpoint CAS 测试足以证明该风险不是 WU-LIFE recovery lifecycle 前置条件。

### Slice A Implementation Decisions: Recovery Lifecycle Proof

Implementation agent 应在 `tests/host/test_recovery_scan.py` 增加 scanner-level focused tests：

- owner still-live integration：构造 RUNNING Run + current Attempt + dispatch record + owner liveness，使用 fake process probe / current policy 让 `StartupRecoveryScanner._classify_active_or_cancelling()` 返回 `OWNER_STILL_LIVE`，断言不写 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`、Run / Attempt / dispatch row 不变、reason 可区分，例如 `owner_heartbeat_recent` 或 `owner_pid_live_without_identity_proof`。
- orphan inconclusive integration：构造同类 RUNNING Run，模拟 missing liveness / process probe error / stale heartbeat alone 中至少一个 scanner 路径，断言 decision 为 `ORPHAN_INCONCLUSIVE`，不写 terminal / recovery facts，reason 可区分，例如 `owner_liveness_missing`、`process_probe_error` 或 stale-only 对应 reason。
- `WAITING` public/read semantics：优先放在 `tests/host/test_recovery_scan.py` 做 durable read 证明；若现有 public fixture 足够轻量，可放在 `tests/host/test_open_host_runtime.py` 增加 public-path test。必须断言 startup scan/reopen 后 Run 仍为 `WAITING`、current attempt 不新增、EventLog 不追加 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`，action reason 为 `waiting_adapter_observation_unavailable`。
- RR-DUR-04 recovery proof：在新增或现有 recovery matrix test 中明确 `StartupRecoveryScanner.scan()` 使用短 write transaction，projection lag 不影响 RUNNING positive orphan / RECOVERING dispatch limit 的事实已由现有 tests 覆盖；不重复已有 projection-lag tests，除非 matrix 需要引用 helper 常量。

Implementation agent 应在 `tests/host/test_recovery_scan.py` 或 `tests/host/test_recovery_dispatch.py` 增加 recovery lifecycle matrix 常量，至少覆盖本计划测试矩阵中 Slice A 的场景，标注 `existing coverage` / `new coverage` / `non-goal`。该常量只服务测试可读性，不进入生产代码。

只有以下 tests-first failure 才允许最小生产修复：

- scanner still-live / inconclusive 实际写了 `ATTEMPT_LOST`、`RUN_RECOVERING` 或 `RUN_LOST`；
- reason 相同导致 owner still-live、inconclusive、positive orphan、WAITING diagnostic-only 无法区分；
- `WAITING` startup scan 创建新 Attempt 或改变 Run 状态；
- recovery scan 依赖 projection checkpoint / read model / memory lag；
- recovery dispatch limit 不是基于 canonical EventLog truth。

允许的最小生产修改范围仅限：

- `dayu/host/recovery.py`
- `dayu/host/recovery_process.py`
- `dayu/host/durable/run_transition.py`，仅当 closeout reason / payload 真源必须稳定且直接由 failing test 证明。
- 禁止修改 `dayu/host/api.py`、durable schema、EventLog type 定义或 public opener contract。

### Slice B Implementation Decisions: Scheduler Close / cancel_all Lifecycle

Implementation agent 应在 `tests/host/test_dispatch_scheduler.py` 增加 close-window focused tests：

- close non-drain dispatch queue：构造 scheduler 与 pending dispatch queue 非空，调用 `scheduler.close()`，断言 close 不处理剩余 in-memory queue、不写 `RUN_CANCELLED` / `RUN_FAILED` / `RUN_LOST` / `ATTEMPT_LOST`，durable dispatch / Run 状态保持可由 next open recovery / dispatch 解释；close 后 wake / drain fail closed。
- close non-drain promotion task / queue：构造 tracked promotion task 或 pending promotion 场景，close 取消 promotion task，断言不无限 drain、不写 terminal facts、不吞掉 durable truth。若现有 `_promotion_drain_task` tests 可扩展，应只补断言，不复制大 fixture。
- `cancel_all` snapshot after-register：直接测试 `ActiveWorkerRegistry.cancel_all()`。使用记录型 fake handle / token；在第一个 entry 的 cancel hook 中注册第二个 entry，断言本次 `cancel_all("scheduler_close")` 只取消快照中的 first entry，不取消后注册 second entry；再单独调用 `cancel_all()` 可取消 second entry。该测试只证明快照语义，不要求给 registry 增加 closed 状态。
- close during lane wait / pre-worker window：构造 dispatch 已排队或 lane wait 中，close 取消 drain task / lane controller，断言 lane wait 被释放或跳过，不写 worker startup timeout terminal fact；Run / Attempt / dispatch record 保持非 terminal 或设计允许的 pending/cancelled diagnostic 状态。
- close cancellation window：用 deterministic barrier / monkeypatch 让 `HostDispatchScheduler.close()` 停在 mark stopping 之后、active cancel 之前或 lane close 之前，从外层取消 close task。断言后续再次 `await scheduler.close()` 能完成 cleanup，`_closed` 保持 true，active task / registry / lane controller / duplicate governance registry 最终无泄漏，且没有 terminal facts 由 scheduler close 自身写入。

如果 close cancellation window test 暴露当前 `HostDispatchScheduler.close()` 在外层 cancellation 后无法 retry cleanup，允许在 `dayu/host/dispatch.py::HostDispatchScheduler.close()` 做最小生产修复：

- 保持 `_closed = True` 的 fail-closed gate。
- 允许 close cleanup 具有可重入 / retryable 行为，例如在 `_close_cleanup_done` 为 false 时重复执行未完成 cleanup。
- 必须避免把 `asyncio.CancelledError` 吞掉成成功 close；外层取消可以传播，但下一次 close 必须能完成 cleanup。
- 不得在 close 中写 durable terminal fact，不得 drain-until-empty，不得新增 public API。

只有以下 tests-first failure 才允许最小生产修复：

- close 或外层取消导致 active task / active registry / lane token / lane wait / promotion task 稳定泄漏；
- close window 写入 `RUN_CANCELLED` / `RUN_FAILED` / `RUN_LOST` / `ATTEMPT_LOST` 等 terminal fact；
- close 后 wake / drain 不 fail closed；
- `cancel_all` 声称快照语义但实际取消后注册 entry，或 reason 无法区分 scheduler close 与 user cancel；
- queue 非空 close 会无限 drain 或处理不应由 close 处理的 pending work。

允许的最小生产修改范围仅限：

- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`，仅当 public handle close retry / finally cleanup 的 failing test 直接指向 opener close boundary。
- 禁止修改 `dayu/host/api.py`、durable schema、EventLog type 定义、public cancel command 或 state-machine owner，除非 controller 先接受 design stop condition。

## Testing Matrix

### Slice A: Recovery Lifecycle Matrix

| 场景 | 期望 decision / durable mutation | Coverage |
|---|---|---|
| `ACCEPTED` startup scan | `ACCEPTED_WAKE`；只 wake queue promotion，不创建 Attempt，不写 recovery fact | existing coverage: `tests/host/test_recovery_scan.py` |
| `QUEUED` startup scan | `QUEUE_PROMOTION_CHECK`；只 wake queue promotion，不写 recovery fact | existing coverage: `tests/host/test_recovery_scan.py` |
| `WAITING` startup scan low-level | `WAITING_DIAGNOSTIC_ONLY`；reason `waiting_adapter_observation_unavailable`；Run 保持 `WAITING`，不创建 Attempt | existing coverage: `tests/host/test_recovery_scan.py` |
| `WAITING` startup scan public/read semantics | reopen / scan 后用户可见仍是等待 resolution，不创建 recovery Attempt，不写 terminal / recovery facts | new coverage: `tests/host/test_recovery_scan.py` 或 `tests/host/test_open_host_runtime.py` |
| `RUNNING` positive orphan with projection lag | `RUN_RECOVERING`；写 `ATTEMPT_LOST` + `RUN_RECOVERING`；projection lag 不参与 truth | existing coverage: `tests/host/test_recovery_scan.py` |
| `RUNNING` owner heartbeat recent | `OWNER_STILL_LIVE`；不写 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST` | new coverage: scanner-level integration in `tests/host/test_recovery_scan.py`; classifier existing in `tests/host/test_recovery_orphan_classifier.py` |
| `RUNNING` pid live without identity proof | `OWNER_STILL_LIVE` 或 classifier-defined still-live；不写 recovery / terminal facts | new coverage: scanner-level integration; classifier existing |
| `RUNNING` process probe error | `ORPHAN_INCONCLUSIVE`；不写 recovery / terminal facts；reason 可区分 | new coverage: scanner-level integration; classifier existing |
| `RUNNING` missing current Attempt / dispatch record | `ORPHAN_INCONCLUSIVE`；不写 recovery / terminal facts | existing or new if matrix finds no direct test in `tests/host/test_recovery_scan.py` |
| `CANCELLING` positive orphan | 写 `ATTEMPT_LOST` + `RUN_LOST`，reason `cancel_in_flight_attempt_lost`，不继续用户目标 | existing coverage: `tests/host/test_recovery_scan.py` |
| `RECOVERING` under dispatch limit | 创建新 Attempt / execution / dispatch；wake dispatch；`RUN_STARTED(start_reason=recovery)` | existing coverage: `tests/host/test_recovery_dispatch.py` |
| `RECOVERING` over dispatch limit with projection lag | `RUN_LOST`；reason `startup_recovery_dispatch_limit_exceeded`；limit 基于 EventLog | existing coverage: `tests/host/test_recovery_scan.py` |
| old execution late terminal after recovery new Attempt | reject late terminal，不进入 canonical facts | existing coverage: `tests/host/test_recovery_dispatch.py` |
| live owner multiprocess | 不误杀 live owner，不写 `RUN_RECOVERING` | existing coverage: `tests/host/test_recovery_multiprocess.py` |
| owner crash multiprocess public event stream | reopen 后 public stream 可观察 recovered final answer | existing coverage: `tests/host/test_recovery_multiprocess.py` |
| startup timeout / dispatch failure / stream failure reason | 纳入 matrix 映射；不重复 recovery tests，除非 reason 不可区分 | existing coverage: `tests/host/test_dispatch_scheduler.py`; matrix mapping only |
| stress repeated crash / recovery / terminal dedupe | 不进入默认 validation；只作为非默认 stress evidence | non-goal for this work unit |
| RR-DUR-01 true multiprocess projection checkpoint CAS race | recovery 不依赖 projection checkpoint；不纳入 implementation scope | non-goal; closed by evidence |
| RR-DUR-04 long read transaction governance scan | recovery / scheduler governance 使用短事务与 durable truth；不预设生产改动 | new coverage as proof matrix mapping; code evidence first |

### Slice B: Scheduler Close / cancel_all Matrix

| 场景 | 期望 decision / durable mutation | Coverage |
|---|---|---|
| Host close idempotent | repeat close no-op；public API fail-fast | existing coverage: `tests/host/test_public_lifecycle_smoke.py`, `tests/host/test_dispatch_scheduler.py` |
| Host close 不关闭 open Session / 不写 terminal facts | Session 保持 open；RUNNING 不变；不写 close-created terminal facts | existing coverage: `tests/host/test_public_lifecycle_smoke.py` |
| scheduler close active worker | token cancel reason `scheduler_close`；handle close once；registry unregister；lane release | existing coverage: `tests/host/test_dispatch_scheduler.py` |
| scheduler close suppresses active handle cancel / close exception | close 不被 active handle cleanup 异常打断 | existing coverage: `tests/host/test_dispatch_scheduler.py` |
| wake methods after close | `wake_dispatch` / `wake_queue_promotion` / `run_queue_promotion` / `drain_once` fail closed | existing coverage plus add `drain_once` if missing in `tests/host/test_dispatch_scheduler.py` |
| promotion task close | tracked promotion task cancelled and awaited | existing coverage: `tests/host/test_dispatch_scheduler.py` |
| dispatch queue non-empty close | close 不 drain-until-empty，不处理 pending queue，不写 terminal facts | new coverage: `tests/host/test_dispatch_scheduler.py` |
| promotion queue / task non-empty close | close 取消 tracked task，不无限 drain，不写 terminal facts | new coverage or extend existing promotion close test |
| `cancel_all` snapshot after-register | 本次 `cancel_all` 只取消锁内快照 entries；后注册 entry 等待后续 close gate / retry | new coverage: direct `ActiveWorkerRegistry` unit test in `tests/host/test_dispatch_scheduler.py` |
| worker started but not durable accepted / active registered | close gate / task cancellation / lane release 稳定，不写 terminal fact | new coverage if fixture can deterministically hit window; otherwise stop and report if not deterministic |
| lane wait / pre-worker close | close skips / releases lane wait，不写 worker startup timeout terminal fact | new coverage: `tests/host/test_dispatch_scheduler.py` |
| close 中途被外层取消 | cancellation 可传播；下一次 close 能完成 cleanup，无 active / lane / registry leak，无 terminal fact | new coverage: `tests/host/test_dispatch_scheduler.py`; likely strongest hardening signal |
| worker clean EOF during scheduler close | `_closed=True` 时不映射为 user cancel terminal fact | existing code evidence; add focused assertion only if current tests cannot prove terminal fact boundary |
| public `cancel_session_runs` user intent | user cancel 与 scheduler close lifecycle cancel 分离 | existing coverage: `tests/host/test_public_cancel_session_runs.py` |
| close drain-until-empty / graceful all-work completion | close 不承担该语义 | non-goal |
| global closed state for `ActiveWorkerRegistry` | 不引入，除非 tests-first 证明 close gate 无法覆盖 | non-goal by default |
| stress / fuzz close soak | 不进入默认 validation | non-goal |

## Small Implementation Slices

### Slice A: Recovery Lifecycle Proof Matrix + Focused Recovery Tests

**Objective**

补齐 WU-LIFE-01 recovery lifecycle proof matrix 与 scanner-level focused tests，证明 still-live / inconclusive 不写 recovery facts，`WAITING` startup recovery 保持 diagnostic-only，RR-DUR-04 纳入 proof matrix 但不触发 production rewrite。

**Allowed files / modules**

- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_dispatch.py`，仅当 matrix 需要把 recovery dispatch existing coverage 映射到测试常量或补极小断言。
- `tests/host/test_open_host_runtime.py`，仅当选择 public-path `WAITING` 语义测试且 durable-level test 不足。
- `tests/host/test_recovery_orphan_classifier.py`，仅当 matrix 发现 classifier reason 缺口；默认不改。
- `dayu/host/recovery.py`，仅 tests-first 失败证明 scanner decision / reason / mutation 错误时最小修复。
- `dayu/host/recovery_process.py`，仅 tests-first 失败证明 classifier reason / classification 错误时最小修复。
- `dayu/host/durable/run_transition.py`，仅 tests-first 失败证明 closeout payload / reason 真源错误时最小修复。
- `docs/reviews/wu-life-01-02-implementation-sliceA-*.md`，implementation report path 由 controller 分配。

**Exact changes**

- 在 `tests/host/test_recovery_scan.py` 增加 recovery lifecycle matrix 常量，字段至少包括：scenario id、Run status、owner proof / dispatch condition、expected decision、expected durable mutation、expected reason、coverage classification。
- 增加 scanner still-live integration test，覆盖 owner heartbeat recent 或 pid live without identity proof；断言 action decision / reason、EventLog event counts、Run / Attempt / dispatch row 不变。
- 增加 scanner inconclusive integration test，覆盖 process probe error 或 missing liveness；断言 action decision / reason、EventLog event counts、Run / Attempt / dispatch row 不变。
- 增加 `WAITING` startup diagnostic-only 用户可见语义测试：低层 durable read 或 public reopen/read 任选最窄稳定路径；断言 Run 仍 `WAITING`、Attempt 未新增、无 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`。
- 将 RR-DUR-04 作为 matrix row：标注 recovery scanner 使用短 write transaction，projection lag existing tests 已覆盖，不新增 production code。
- 如果现有 tests 已覆盖某 matrix row，不重复测试，只在 matrix 标注 existing coverage，并在 assertion 名称 / 注释中指向现有 module。

**Non-goals**

- 不新增 production recovery API。
- 不改变 `WAITING` 状态、Run / Attempt 状态机、EventLog event type。
- 不实现 remote takeover / lease / fencing。
- 不把 stress suite 纳入默认 validation。

**Tests / validation commands**

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q
pytest tests/host/test_recovery_multiprocess.py -q
python -m pyright dayu/ tests/ utils/
```

若 Slice A 没有触碰 multiprocess/public path，可把 `tests/host/test_recovery_multiprocess.py` 标为 secondary validation；若触碰 `open_host` public WAITING path，则额外运行：

```bash
source .venv/bin/activate
pytest tests/host/test_open_host_runtime.py -q
```

**Completion signal**

- Recovery lifecycle matrix 每个 row 都标注 existing coverage / new coverage / non-goal。
- 新增 scanner still-live / inconclusive tests 通过，且证明不写 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`。
- `WAITING` diagnostic-only 语义有 focused regression，证明不创建 recovery Attempt。
- RR-DUR-04 在 matrix 中有明确 proof row，未被误扩成 production rewrite。
- pyright 通过，或若触及已有 pyright 报错，implementation report 明确无新增 / 扩散并给出 controller 需裁决项。

**Stop condition**

- 新增测试证明 recovery scanner 会基于 heartbeat stale alone、projection/read model 或 inconclusive proof 写 recovery / terminal facts。
- 新增测试证明现有 reason / diagnostic 无法区分 still-live、inconclusive、positive orphan、WAITING diagnostic-only。
- 需要改变 durable schema、EventLog event type、public Host API、Run / Attempt 状态机或 `WAITING` durable 语义。
- 无法构造 deterministic test，只能依赖 sleep/race 运气证明核心场景。

### Slice B: Scheduler Close / cancel_all Lifecycle Matrix + Focused Close-window Tests

**Objective**

补齐 WU-LIFE-02 scheduler close / `cancel_all` lifecycle matrix 与 close-window focused tests，证明 close 不无限 drain、不写 terminal facts、`cancel_all` 是快照取消语义、close 中途取消后可 retry cleanup 且无资源泄漏。

**Allowed files / modules**

- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_open_host_runtime.py`，仅当 opener close finally / scheduler close exception path 需要补 public boundary。
- `tests/host/test_public_lifecycle_smoke.py`，仅当需要补 public close terminal fact assertion；默认不改。
- `dayu/host/dispatch.py`，仅 tests-first 失败证明 close cleanup / cancel_all / close-window terminal fact boundary 错误时最小修复。
- `dayu/host/open_host.py`，仅 tests-first 失败证明 Host opener close retry/finally cleanup boundary 错误时最小修复。
- `docs/reviews/wu-life-01-02-implementation-sliceB-*.md`，implementation report path 由 controller 分配。

**Exact changes**

- 在 `tests/host/test_dispatch_scheduler.py` 增加 scheduler close lifecycle matrix 常量，字段至少包括：scenario id、window、expected close action、expected durable mutation、expected resource cleanup、coverage classification。
- 增加 direct `ActiveWorkerRegistry.cancel_all()` snapshot test：第一个 entry 的 cancel propagation 中注册第二个 entry，断言本次 cancel count / token reason 只覆盖 first entry；第二次 `cancel_all()` 才覆盖 second entry。
- 增加 dispatch queue non-empty close test：queue 中存在 pending dispatch 时 close 不 drain、不写 terminal facts；close 后 wake / drain fail closed。
- 扩展或新增 promotion close test：promotion task / queue 非空时 close 取消 tracked task，不无限 drain、不写 terminal facts。
- 增加 lane wait / pre-worker close test：close 取消 lane wait 或让 drain path skipped，不写 worker startup timeout terminal fact；资源最终释放。
- 增加 close cancellation retry cleanup test：使用 deterministic barrier/monkeypatch 在 close cleanup 中途取消 close task，随后再次调用 close；断言 cleanup done、active registry empty、active tasks done、lane controller closed、duplicate governance registry cleared、terminal EventLog count 不变。
- 若 close cancellation retry cleanup test 暴露当前生产缺陷，只在 `HostDispatchScheduler.close()` 做可重入 cleanup hardening；外层 `CancelledError` 不应被吞成成功 close，但后续 close 必须能补完 cleanup。

**Non-goals**

- 不把 close 改成 drain-until-empty。
- 不让 scheduler close 写用户 cancel / failed / lost terminal facts。
- 不修改 public cancel command。
- 不新增 global `ActiveWorkerRegistry.closed` 状态，除非 tests-first 证明必要且 controller 接受。
- 不新增 public close API 或 close timeout option。

**Tests / validation commands**

```bash
source .venv/bin/activate
pytest tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
```

若 Slice B 只修改 `tests/host/test_dispatch_scheduler.py` 且不触碰 public opener，可把第二条 pytest 作为 regression validation；若触碰 `dayu/host/open_host.py`，第二条必须运行。

**Completion signal**

- Scheduler close / `cancel_all` matrix 每个 row 都标注 existing coverage / new coverage / non-goal。
- `cancel_all` snapshot test 通过，语义与 plan 一致。
- close queue / promotion non-drain tests 通过，且没有 scheduler-close-created terminal facts。
- close cancellation retry cleanup test 通过；若做了 production hardening，能证明外层 cancellation 后第二次 close 完成 cleanup。
- close 后 wake / drain fail closed 覆盖完整。
- pyright 通过，或若触及已有 pyright 报错，implementation report 明确无新增 / 扩散并给出 controller 需裁决项。

**Stop condition**

- close cancellation window 需要改变 Host public close guarantee、durable terminal semantics 或 public cancel semantics。
- close queue/promotion non-drain 场景无法 deterministic 构造，只能依赖 timing race。
- 修复需要 durable schema、EventLog event type、Run / Attempt 状态机或 public API 变化。
- 修复需要引入 lease/fencing/global registry closed state 等超出本 plan 的新抽象。

## README / Doc Sync Decision

本 planning turn 不修改 README、control doc 或 design doc。

后续 implementation gate 的 README 触发规则：

- 若只新增 / 更新 tests 与 review artifacts，且不改变 Host public contract、测试运行入口、marker、目录约定或稳定开发说明：不更新 `dayu/host/README.md`，不更新 `tests/README.md`。
- 若生产代码修复改变 Host close / recovery 的稳定开发说明，但不改变 public API：检查 `dayu/host/README.md` 是否已有对应 lifecycle / recovery 表述；只有当前 README 与代码事实不一致时同步更新。
- 若新增稳定测试入口、marker、命令或测试分层约定：更新 `tests/README.md`。
- 若改变 public Host API、durable schema、EventLog event type、Run / Attempt 状态机、`WAITING` 语义或 close terminal fact boundary：立即停止，先回 controller 做 design / scope 裁决；不得在 implementation slice 内用 README 直接吸收 contract change。

## Review Gates

Plan review 必须检查：

- plan 是否默认 tests/proof-first，而不是预设生产重写；
- Slice A / Slice B file ownership 是否清晰且互不混淆；
- 每个场景是否标注 existing coverage / new coverage / non-goal；
- production code allowed changes 是否被 tests-first failure 严格触发；
- stop conditions 是否覆盖 contract/schema/state-machine/public-interface 风险；
- RR-DUR-01 是否明确 closed / out of scope，RR-DUR-04 是否进入 proof matrix 但不预设代码改动；
- README/doc sync decision 是否符合 AGENTS.md 固定职责。

Implementation review 必须逐 slice 进行：

- Slice A review 聚焦 recovery matrix、scanner still-live / inconclusive、WAITING diagnostic-only、RR-DUR-04 proof row、是否误改生产 recovery contract。
- Slice B review 聚焦 scheduler close matrix、`cancel_all` snapshot、close non-drain、close cancellation retry cleanup、close 不写 terminal facts、是否误改 user cancel / public API。
- 任一 slice 若有 production code change，review 必须先确认对应 failing test 证据真实存在，再审查修复是否最小且不越界。

Aggregate deepreview 必须在两个 slices 完成后执行，重点核对：

- WU-LIFE-01 / WU-LIFE-02 是否仍满足 `docs/host/design.md` 第 27 节与 Host opener close 语义；
- 没有引入 durable schema、EventLog type、public API、Run / Attempt 状态机变更；
- 没有把 projection/read model/memory lag/stress summary 当 recovery truth；
- close 不写 terminal facts，close 不无限 drain，close 中途取消有可解释 cleanup 语义；
- README/doc sync decision 已按实际变更执行或明确不需要。

## Handoff Criteria

Plan handoff-ready 条件：

- 本 artifact 已创建在 `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`。
- 无 blocking open question。
- 两个 implementation slices 均有 allowed files、exact changes、non-goals、validation commands、completion signal、stop condition。
- 测试矩阵覆盖 existing / new / non-goal 标注。
- RR-DUR-01 / RR-DUR-04 scope 已明确。
- Contract / schema / state-machine / public-interface default none 与 stop condition 已明确。

Implementation handoff criteria for each slice：

- Controller 只派发当前 slice，不让 implementation agent 自行合并未来 slice，除非 controller 明确授权。
- Implementation agent 必须先按 slice 增加 focused tests / matrix，再根据 failing evidence 决定是否触碰 allowed production files。
- Implementation agent completion report 必须列出 modified files、tests run、pyright result、README/doc sync decision、residual risks / uncovered areas。

## Risks / Open Questions

Blocking questions: none。

Residual risks / watch items：

- Close cancellation retry cleanup 可能暴露真实生产缺陷；若失败可在 `HostDispatchScheduler.close()` 内做最小可重入 cleanup hardening，但不得吞掉外层 cancellation 或改变 public close contract。
- Worker started but not durable accepted / active registered window 需要 deterministic fixture。若无法稳定构造，不应写 timing-sensitive test；implementation agent 必须停止并报告 controller，而不是用 sleep/race 测试。
- RR-DUR-04 当前是 proof matrix owner，不是 production rewrite owner。只有直接代码或测试证据显示 governance decision 使用长 read transaction / projection lag 作为 truth，才允许进入 fix。
- `tests/host/test_recovery_multiprocess.py` 可能较慢；Slice A 应尽量把新增 regression 放在 deterministic unit/integration tests，multiprocess 只作 regression validation。

## Completion Report Format For Implementation Agent

每个 slice 完成后，implementation agent 必须用以下格式回报 controller：

```text
WU-LIFE-01/02 Slice <A|B> Completion Report

Scope implemented:
- <简述完成的 matrix / focused tests / minimal production fix>

Modified files:
- <path>: <变更类型与原因>

Tests added or updated:
- <test function / matrix scenario>: <证明的语义>

Production code changes:
- none
或
- <path>::<function>: <failing test 证据> -> <最小修复说明>

Validation:
- source .venv/bin/activate && <pytest command>: pass/fail
- source .venv/bin/activate && python -m pyright dayu/ tests/ utils/: pass/fail

README/doc sync:
- not needed: <原因>
或
- updated <README path>: <原因>

Contract/schema/state-machine/public-interface changes:
- none
或
- STOPPED: <需要 controller 裁决的问题>

Residual risks / uncovered areas:
- none
或
- <risk>: <owner / suggested next action>

Stop conditions hit:
- none
或
- <stop condition and evidence>
```

如果任一 validation fail，implementation agent 不得把 slice 标为 complete；必须给出 failure evidence、已尝试的最小修复、剩余 blocker 和是否需要 controller 裁决。
