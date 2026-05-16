# Code Review — Host Phase 7 P7-S4 WAITING Cancel, Late Result Diagnostic, Poll, Engine Confirmation

## Scope

- Mode: current changes
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: HEAD
- Output file: docs/reviews/host-phase7-code-review-s4-ds-20260516.md
- Implementation notes: docs/reviews/host-phase7-implementation-s4-wait-cancel-late-poll-20260516.md
- Included scope:
  - `dayu/host/admission.py` — WAITING cancel in cancel_run/cancel_session_runs
  - `dayu/host/durable/run_transition.py` — cancel_waiting_run_in_transaction, CancelWaitingRunInput
  - `dayu/host/durable/state.py` — cancel_active_wait_records_for_run, cancel_waiting_run_row, read_wait_records_for_poll_observation
  - `dayu/host/waiting.py` — late result diagnostic, _reject_late_result, _LateRejectResult
  - `dayu/host/wait_adapter.py` — WaitPoller, WaitPollAdapter, WaitPollAdapterRegistry
  - `dayu/host/engine_ingest.py` — _confirm_waiting_engine_event replaces _diagnostic_then_failed_waiting
  - `dayu/host/_event_payload.py` — wait_late_result_rejected_payload
  - `tests/host/test_wait_cancel_late_result.py` — 4 tests (WAITING cancel × 2, late diagnostic, RESOLVED/FAILED no-diagnostic)
  - `tests/host/test_wait_adapter_polling.py` — 3 tests (ready → resolve, not-ready, cancelled → abandon)
  - `tests/host/test_engine_ingest_mapping.py` — 2 updated tests (run_suspended/tool_awaiting diagnostic-only)
  - `dayu/host/README.md` / `tests/README.md` — 同步 WAITING cancel、late diagnostic、poller、Engine confirmation
- Excluded scope:
  - Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
  - P7-S1/S2/S3 committed changes, plan/design/control docs
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项验证

#### 1. cancel_run / cancel_session_runs WAITING 分支复用同一 transition

- **cancel_run WAITING**: `admission.py` `_CancelRunOperation` 新增 `_cancel_waiting()`（`admission.py:1182-1243`），检测 `run.status == WAITING`（`admission.py:968-972`）后调用 `cancel_waiting_run_in_transaction(...)`。与 queued/pre-dispatch/active-worker 分支并列，不修改其他分支的调度逻辑。
- **cancel_session_runs WAITING**: `_CancelSessionRunsOperation._cancel_one_run()` 新增 `if target.waiting: return self._cancel_waiting_target(...)` 分支（`admission.py:1436-1437`），其中 `_cancel_waiting_target()`（`admission.py:1542-1572`）调用相同的 `cancel_waiting_run_in_transaction(...)`。
- **session target 判定**: `_session_cancel_target_for_run()` 对 WAITING Run 检查 `current_attempt_id is not None`、读取 Attempt 与 dispatch_record，仅当 `attempt.status == SUSPENDED` 时设置 `waiting=True`（`admission.py:2323-2341`）。非 SUSPENDED 返回 `None` → 外层按 unsupported non-terminal 拒绝。
- **回归验证**: queued 分支（`run.status == QUEUED`）仍在 line 965、pre-dispatch 分支（`dispatch_record + ATTEMPT_STARTING`）仍在 line 975、active-worker 分支（`CANCELLING` 或 ATTEMPT_RUNNING）未改动。`_SupportedSessionCancelTarget` 新增 `waiting: bool` 字段（`admission.py:1295`），现有构造全部显式传 `waiting=False`。
- **取消效果**: 两种入口都不创建 resume Attempt；test `test_cancel_run_cancels_waiting_run_without_resume_attempt` 断言 `RESUME_REQUESTED` 和 `ATTEMPT_STARTED` 不在 event_types 中；test `test_cancel_session_runs_cancels_waiting_run` 断言 active_run_id 变为 None。
- **结论**: 正确，无回归。

#### 2. cancel_waiting_run_in_transaction CAS/事务/EventLog 顺序

- **事务内执行顺序**（`run_transition.py:1312-1398`）：
  1. `_validate_cancel_waiting_input` 输入校验
  2. `read_run_by_id` + 前置检查 `run.status == WAITING and run.current_attempt_id is not None`
  3. `read_attempt_by_id` + 前置检查 `attempt.status == SUSPENDED` + `active_waits` 非空
  4. `append_event(CANCEL_REQUESTED)` → `cancel_request_event`
  5. `cancel_active_wait_records_for_run(...)` — 批量 CAS `WAITING → CANCELLED`，rowcount 校验（`state.py:2174`）
  6. 若 step 5 非 UPDATED → `_raise_after_event_append_mutation_failure` → 事务回滚
  7. `append_event(RUN_CANCELLED)` — payload 携带 `wait_ids`、`waiting_cancelled: true`
  8. `cancel_waiting_run_row(...)` — CAS `WAITING → CANCELLED`（`state.py:2629-2691`），WHERE 条件含 `terminal_event_id IS NULL` 等三个 terminal NULL 守卫
  9. `_require_run_mutation_updated` → 非 UPDATED 则 raise
- **cancel_active_wait_records_for_run CAS 逻辑**（`state.py:2110-2181`）：
  - 先 `read_active_wait_records_for_run` 获取 before_rows
  - 若 before_rows 为空：检查是否存在任何 wait record（`_read_wait_record_count_for_run`）；若存在则为 INVALID_STATE（active waits 已被其它事务所关闭），否则 NOT_FOUND
  - `UPDATE host_wait_records SET status=CANCELLED WHERE run_id=? AND status=WAITING`
  - `result.rowcount == len(before_rows)` → UPDATED；否则 CAS_LOST
- **事务原子性**: CANCEL_REQUESTED event append 若在 DB mutation 失败后已写入，因在同一 `run_write` lambda 内，raise 导致整个事务回滚，event 不会半提交。
- **结论**: EventLog 事实在 DB mutation 之前 append，同一事务保证全或无，CAS 保护正确。

#### 3. late result diagnostic

- **终态 wait 处理**（`waiting.py:583-642`）：
  - `wait_record.status in (RESOLVED, FAILED, LOST)` → 调用 `_replay_terminal_resolution_or_none`
  - 同 key 同 digest → 返回幂等重放结果；同 key 异 digest → `IDEMPOTENCY_CONFLICT`
  - `record is None`（不同 key）：
    - `RESOLVED / FAILED` → 直接 `raise HostApiError(INVALID_STATE)`，**不写 diagnostic**（`waiting.py:636-640`）
    - `LOST` → `_reject_late_result(WAIT_LOST)`，**写入 diagnostic**
  - 此分支顺序符合 controller 抽查修正结论
- **CANCELLED wait**: 直接 `_reject_late_result(WAIT_CANCELLED)`，写入 diagnostic（`waiting.py:643-648`）
- **WAITING wait + terminal owner Run**: `_reject_late_result(RUN_TERMINAL)`（`waiting.py:663-669`）
- **非 WAITING 且非终态/CANCELLED**: `_reject_late_result(INVALID_WAIT_STATE)`（`waiting.py:656-661`）
- **`_reject_late_result` 幂等**（`waiting.py:783-847`）：
  - 使用独立 `wait_late_rejection` scope（scope_kind=`"wait_late_rejection"`, scope_id=wait_id）
  - digest 包含 wait_id、run_id、idempotency_key、source、observed_at、wait_status、rejection_reason、outcome_kind、outcome_digest、outcome
  - 同 key 同 digest → 返回 `_LateRejectResult`，不追加第二个 diagnostic event
  - 同 key 异 digest → `IDEMPOTENCY_CONFLICT`
  - 无现有记录 → 写 `WAIT_LATE_RESULT_REJECTED` DIAGNOSTIC 事件 + 幂等记录
- **晚到结果返回**: `_LateRejectResult` 从 transaction 返回后，`resolve_wait()` 将其转为 `HostApiError(INVALID_STATE)`（`waiting.py:575-580`）
- **测试验证**: `test_late_result_after_cancel_writes_bounded_diagnostic` 断言 diagnostic 仅 1 条、重放不追加、冲突返回 IDEMPOTENCY_CONFLICT 且不追加事件；`test_different_key_after_resolved_or_failed_does_not_write_late_diagnostic` 断言 RESOLVED/FAILED 不同 key 不写 diagnostic 且 EventLog 不变。
- **结论**: 诊断写入条件有界，幂等有界，RESOLVED/FAILED 不同 key 正确拒绝不写 diagnostic。

#### 4. WaitPoller 只读快照 + transaction 外 adapter 调用

- **数据读取**: `WaitPoller.poll_once()` 通过 `run_read` 调用 `read_wait_records_for_poll_observation`（`wait_adapter.py:295-297`），该 helper（`state.py:1507-1536`）只返回 `resume_policy=poll AND status IN (WAITING, CANCELLED)` 的 wait records。读取在独立 read transaction 中完成。
- **adapter 调用**: 在 `run_read` 结束后，poller 逐 record 调用 adapter（`wait_adapter.py:310-340`）：
  - `CANCELLED` → `adapter.abandon_wait(record)` → 计数 `abandoned`，**不调用 resolve_wait**
  - `WAITING` → `adapter.poll_wait(record)` → 若 `RuntimeError` 则计数 `adapter_errors` 并 continue
  - `WaitPollReady` / `WaitPollLost` → 构造 `ResolveWaitRequest(source=POLL, idempotency_key=poll-<digest>, outcome=poll_result.outcome)` → `self._resolver.resolve_wait(record.wait_id, request)`（进入新 write transaction）
  - `WaitPollNotReady` → 计数 `not_ready`，继续
- **adapter 调用在 transaction 外**: adapter 的 `poll_wait` 和 `abandon_wait` 调用不在任何 Host transaction 内，满足设计约束。
- **resolve_wait 调用**: 通过 `WaitResolvePort` Protocol 注入（测试中使用 `_PublicCommandResolver` 包装 public `resolve_wait` 函数），不走短路径直接写 durable。
- **idempotency_key 稳定性**: `_poll_idempotency_key()`（`wait_adapter.py:365-377`）使用 `sha256(source="poll", wait_id=wait_id)` 派生，对同一 wait 始终相同。
- **测试验证**: `test_poll_adapter_ready_result_resolves_wait` 断言 ready 后 wait record 变为 RESOLVED；`test_poll_adapter_not_ready_leaves_wait_active` 断言 WAITING 不变且 adapter.poll_count==1；`test_cancelled_poll_wait_is_abandoned_without_resolve` 断言 cancelled 后只调用 abandon 不调用 poll_wait 且 wait 保持 CANCELLED。
- **结论**: 正确。

#### 5. EngineEvent ingest TOOL_AWAITING / RUN_SUSPENDED confirmation

- **入口变更**: `engine_ingest.py` `_ingest_one` 中 `RUN_SUSPENDED` 和 `TOOL_AWAITING` 的处理从 `_diagnostic_then_failed_waiting` 改为 `_confirm_waiting_engine_event`（`engine_ingest.py:457-465`）。
- **`_confirm_waiting_engine_event` 行为**（`engine_ingest.py:721-773`）：
  1. 计算 `reason`：若 Run 是 `WAITING` 且 Attempt 是 `SUSPENDED` → `"waiting_event_confirmation"`；否则 → `"waiting_event_without_host_accepted_refs"`
  2. 构造 diagnostic event_id → 检查已存在 → 若 DUPLICATE 直接返回
  3. 追加 payload 中 run_status/attempt_status 字段
  4. `append_event(ENGINE_EVENT_DIAGNOSTIC, class=DIAGNOSTIC, reason=... )` — 仅写 diagnostic
  5. 返回 `EngineIngestResult(status=ACCEPTED, terminal_closeout=False, promotion_triggered=False)`
  - **不创建 wait record**，**不写 RUN_FAILED/ATTEMPT_FAILED**，**不推进 Run/Attempt 状态**
- **late rejection 豁免**: `_late_rejection_reason()`（`engine_ingest.py:1179-1185`）对 `RUN_SUSPENDED/TOOL_AWAITING` 事件在 Run `WAITING` + Attempt `SUSPENDED` 时返回 `None`（不拒绝），允许 confirmation diagnostic 写入而不被当作 late event。
- **duplicate event IDs 清理**: `_duplicate_terminal_event_ids()`（`engine_ingest.py:1397`）删除 `RUN_SUSPENDED/TOOL_AWAITING` 的 ATTEMPT_FAILED/RUN_FAILED 事件 ID 生成，不再为这些事件类型生成 terminal closeout 事件 ID。
- **测试验证**: `test_run_suspended_only_writes_diagnostic_and_duplicate_is_idempotent` 断言只有 `ENGINE_EVENT_DIAGNOSTIC`、无 `ATTEMPT_FAILED/RUN_FAILED`、Run/Attempt 保持 RUNNING；`test_tool_awaiting_only_writes_diagnostic_and_duplicate_is_idempotent` 同理。
- **结论**: 正确，Engine awaiting/suspended 事件不再创建 wait state 或失败收口。

#### 6. README / tests 事实一致性

- **dayu/host/README.md**:
  - Public Wait Command Path 节新增 WAITING cancel 与 late result diagnostic 描述（`README.md:+74`）
  - 新增最小 WaitPoller / WaitPollAdapter 契约说明（`README.md:+76`）
  - ToolRuntime 未实现列表：移除已完成的 `wait cancellation`、`wait adapter poller`（`README.md:107`）
  - EngineEvent ingest 描述合并为 Phase 5/7，补充 awaiting confirmation diagnostic 行为（`README.md:126`）
  - Phase 7 foundation 描述扩展为 wait record / resolve / cancel / poll（`README.md:127`）
  - 未实现列表：移除 `WAITING cancel`，保留 `callback endpoint 与 poller 后台调度循环`（`README.md:183-184`）
  - 测试覆盖描述补充 WAITING cancel、late diagnostic、poller、Engine confirmation（`README.md:198`）
- **tests/README.md**:
  - 新增 P7-S4 测试运行命令（`tests/README.md:+47`）
  - public run/wait API 覆盖描述新增 WAITING cancel（`tests/README.md:90`）
  - durable foundation 覆盖描述新增 WAITING cancel、poller、Engine confirmation diagnostic（`tests/README.md:93`）
- **结论**: 文档与当前代码事实一致。

#### 7. 越界修改检查

- `git diff HEAD --name-only` 仅包含 `dayu/host/` 下 7 个文件、`tests/host/` 下 3 个文件、`tests/README.md`、`docs/` 下若干文件。
- 未修改：`dayu/engine/`、`dayu/contracts/`（除新增 import 引用已有类型）、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、recovery、outbox、audit、tool trace read-model。
- `wait_adapter.py` 新增 import（`ResolveWaitLostOutcome`、`RunSnapshot` 等）均来自 `dayu.host.api` 或 `dayu.host.durable`，方向正确。
- **结论**: 无越界修改。

## Open Questions

1. **WAITING Run + 非 SUSPENDED Attempt 在 session cancel 中的处理**: `_session_cancel_target_for_run()`（`admission.py:2322-2323`）对 WAITING Run 的 Attempt 非 SUSPENDED 时返回 `None`，而不是 `INTERNAL_ERROR`。返回 `None` 会导致外层抛出 `UNSUPPORTED_OPERATION`（错误消息暗示 WAITING 在支持范围内但 target 为空）。此状态在当前 invariant 下不可达（WAITING 与 SUSPENDED 在同一事务内推进），但若数据损坏则错误消息会产生误导。是否值得为防御性编程增加显式 INTERNAL_ERROR 检查？

2. **Poller 的 observed_at 与幂等**: `_poll_idempotency_key()` 不包含 `observed_at`，但 `_wait_resolution_digest` 包含。poll 每次轮询使用 `clock.now()`，若同一 wait 在不同轮次返回相同 ready 结果（前次 resolve_wait 未成功提交），第二次调用的 digest 因 observed_at 不同会触发 IDEMPOTENCY_CONFLICT。这是否是 poller 的预期行为？当前 poller 在 `resolve_wait` 成功后 wait record 变为 RESOLVED 不再被 `read_wait_records_for_poll_observation` 返回，所以此场景仅在 resolve_wait 的 write transaction 内部抛出 CAS_LOST 或 INVALID_STATE 后 wait 仍为 WAITING 时才可能出现。

3. **`_reject_late_result` 返回的 HostApiError code**: 所有 late result 统一返回 `INVALID_STATE`，caller 只能通过 message 文本区分具体拒绝原因（wait_cancelled / wait_lost / run_terminal / invalid_wait_state）。如果上层需要根据拒绝类型做不同处理，当前 API 不提供机器可读的区分方式。这是否满足 P7-S4 的 API 设计目标？

## Residual Risk

- **Poller 后台调度循环**: 当前 `WaitPoller` 仅提供 `poll_once()` 单轮入口，无调度循环、退避策略、并发 in-flight fencing。归后续 harden 或 Phase 11 lifecycle。
- **Adapter 错误重试**: `poll_once()` 对 adapter `RuntimeError` 仅计数 `adapter_errors`，不重试，不记录具体失败的 wait_id。生产环境中 adapter 瞬时故障的 wait 可能被遗漏，依赖下一轮 poll 重试。归 poller hardening。
- **RUN_TERMINAL / INVALID_WAIT_STATE late diagnostic 测试缺口**: `_reject_late_result` 的 `RUN_TERMINAL` 和 `INVALID_WAIT_STATE` 分支未被直接测试。当前测试覆盖 CANCELLED 后的 late result (`WAIT_CANCELLED`)，RESOLVED/FAILED/LOST 已覆盖。剩余两个分支对应极端 corner case（WAITING wait + terminal owner Run，或未知 wait status），其触发条件在正常流程中几乎不可达。
- **cancel vs resolve 竞态压力测试**: 与 P7-S3 一致，IMMEDIATE transaction 下 CAS_LOST 不可触发。并发 cancel-vs-resolve 的 first-committer-wins 场景归 P7-S4 后的 hardening。

## Test Coverage Assessment

| 文件 | 测试 | 覆盖路径 |
|------|------|----------|
| test_wait_cancel_late_result.py | cancel_run WAITING | cancel + 不创建 resume Attempt |
| test_wait_cancel_late_result.py | cancel_session_runs WAITING | session-scope cancel 复用 transition |
| test_wait_cancel_late_result.py | late result after cancel | diagnostic 写 1 次 + 重放 + 冲突 |
| test_wait_cancel_late_result.py | RESOLVED/FAILED 不同 key | 不写 diagnostic |
| test_wait_adapter_polling.py | ready → resolve | poll → resolve_wait → RESOLVED |
| test_wait_adapter_polling.py | not-ready | wait 保持 WAITING |
| test_wait_adapter_polling.py | cancelled abandon | abandon 调用 + 无 poll |
| test_engine_ingest_mapping.py | run_suspended | 仅 diagnostic + 无 state change |
| test_engine_ingest_mapping.py | tool_awaiting | 仅 diagnostic + 无 state change |

## Conclusion

PASS。7 个审查重点逐项验证通过：cancel_run/cancel_session_runs WAITING 分支正确复用同一 transition，不创建 resume Attempt，queued/pre-dispatch/active-worker cancel 无回归；cancel_waiting_run_in_transaction 的 CAS/事务/EventLog 顺序正确；late result diagnostic 仅在 CANCELLED/LOST/terminal owner Run 时写入，RESOLVED/FAILED 不同 key 不写 diagnostic，wait_late_rejection 幂等有界；WaitPoller 只读快照、transaction 外调用 adapter、ready/lost 走 resolve_wait、cancelled 只 abandon；EngineEvent ingest 对 TOOL_AWAITING/RUN_SUSPENDED 只写 diagnostic confirmation，不创建 wait state，不失败已 WAITING Run；README/tests 与当前事实一致；无越界修改。
