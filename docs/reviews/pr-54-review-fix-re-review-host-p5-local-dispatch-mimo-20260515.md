# PR 54 Review Fix Re-Review: Host Phase 5 Local Dispatch

## Verdict

**PASS** — 全部 controller accepted items 已修复，3 项 residual gaps 均不阻塞 PR。

## Scope

- Re-review agent: AgentMiMo
- Input artifacts:
  - `docs/reviews/pr-54-review-20260515-1056.md`
  - `docs/reviews/pr-54-review-20260515-1102.md`
  - `docs/reviews/pr-54-review-controller-adjudication-20260515.md`
  - `docs/reviews/pr-54-review-fix-host-p5-local-dispatch-codex-20260515.md`
- Verification method: 3 parallel subagents (A1 dispatch/lane, A2 engine ingest, A3-A5 RunInputBuilder/tests/options) + independent test run + pyright

## Verification Results

### A1. Dispatch / lane / worker lifecycle consistency

| # | Item | Status | Evidence |
|---|------|--------|----------|
| A1.1 | Lane/worker timeout orphan dispatch record | **FIXED** | `_closeout_worker_startup_timeout` 调用 `cancel_starting_dispatch_record_row`（dispatch.py:783-828），测试 `test_lane_acquire_timeout_closes_starting_attempt_failed`（:505）、`test_worker_startup_timeout_closes_starting_attempt_failed`（:402）断言 dispatch_record.status==CANCELLED |
| A1.2 | worker.accept() 非 TimeoutError 异常释放 lane + closeout | **FIXED** | `except Exception` 分支（dispatch.py:641-646）用 try/finally 保证 lane release。测试 `test_worker_accept_exception_closes_failed_and_cancels_dispatch`（:436）用 `_FailingAcceptWorker` 验证 |
| A1.3 | CancelledError 释放 lane token | **FIXED** | `except asyncio.CancelledError`（dispatch.py:503-505）调用 `_safe_release_lane_token`。consume finally block（dispatch.py:919-926）也无条件释放 |
| A1.4 | handle.close/cancel 异常不阻断其它清理 | **FIXED** | `_safe_cancel_worker_handle`、`_safe_close_worker_handle`、`_safe_release_lane_token` 均包裹 try/except。测试 `test_scheduler_close_suppresses_handle_close_exception`（:621）验证 |
| A1.5 | ingestor.ingest() 异常收口为 worker lost | **PARTIALLY FIXED** | 代码正确（dispatch.py:900-909），`close_worker_lost(worker_lifecycle_signal="ingest_exception")`。机制已单元测试（test_engine_ingest_mapping.py:618）。**缺 scheduler 级集成测试**：无测试构造 `ingestor.ingest()` 自身抛异常的场景 |
| A1.6 | CANCELLED dispatch -> CAS_LOST（非 INVALID_STATE） | **FIXED** | state.py:2294-2302 fallback 检查 CANCELLED。测试 `test_cancel_starting_dispatch_record_absorbs_already_cancelled`（:931） |
| A1.7 | CANCELLING/RECOVERING 纳入 active CAS_LOST | **FIXED** | state.py:2949-2955 包含 CANCELLING 和 RECOVERING。测试 parametrized with CANCELLING/RECOVERING（:985） |
| A1.8 | _is_dispatchable_recheck 接受 PENDING/WAITING_FOR_LANE | **FIXED** | dispatch.py:953-954 双条件判断。测试 `test_pending_dispatch_can_direct_mark_dispatching_after_lane_recheck`（:371） |

### A2. Engine ingest idempotency / lifecycle mapping

| # | Item | Status | Evidence |
|---|------|--------|----------|
| A2.1 | RUN_SUSPENDED/TOOL_AWAITING 首次+重复处理，无噪声 diagnostic | **FIXED** | `_duplicate_terminal_event_ids` 返回 3 个事件 ID（DIAGNOSTIC+ATTEMPT_FAILED+RUN_FAILED）。测试 `test_run_suspended_fails_waiting_path_and_duplicate_is_idempotent`（:290）、`test_tool_awaiting_fails_waiting_path_and_duplicate_is_idempotent`（:324） |
| A2.2 | close_worker_lost 重复检测使用 ATTEMPT_LOST/RUN_LOST | **FIXED** | `_duplicate_terminal_event_ids` 对 `_REASON_WORKER_LOST_BEFORE_TERMINAL` 返回 LOST 事件 ID（engine_ingest.py:1268-1285）。测试 `test_worker_lost_closeout_uses_lost_event_ids_and_duplicate`（:608） |
| A2.3 | PROVIDER_PROTOCOL_ERROR/preview/late terminal/run_cancelled_without_active_cancel/unsupported 测试 | **FIXED** | 6 个新测试覆盖所有路径（test file:463-672） |
| A2.4 | TOOL_CALL_REQUESTED/TOOL_RESULT_ACCEPTED 作为 PREVIEW 处理 | **FIXED** | `_is_preview_event`（engine_ingest.py:1672-1673）包含两者。`_preview_payload` 有结构化 payload 提取。测试 `test_tool_call_requested_and_result_accepted_are_preview`（:496） |
| A2.5 | 可恢复 RUN_FAILED diagnostic + closeout 事务原子性 | **FIXED** | 同一 write transaction 内原子执行（engine_ingest.py:393-422）。测试 `test_run_failed_recoverable_true_is_diagnostic_then_failed`（:227） |

### A3. RunInputBuilder message semantics

| # | Item | Status | Evidence |
|---|------|--------|----------|
| A3.1 | 失败/取消/丢失 Run 不留孤立 UserMessage | **FIXED** | `_successful_run_message_pair`（run_input.py:941-961）要求 user+assistant 双端非 None 才返回对。测试 `test_continuity_skips_unsuccessful_prior_runs`（:200-235）验证 |
| A3.2 | system message 不泄漏 attempt_id/execution_id | **FIXED** | scene message 仅含 operation_kind/execution_target/queue_policy/policy_snapshot_ref/tools=disabled（run_input.py:555-585） |
| A3.3 | no-tool executor cancellation-token 合规 | **FIXED** | build 时传入 `cancellation_token=attempt_snapshot.cancellation_token`（run_input.py:705） |

### A4. Test gaps

| # | Item | Status | Evidence |
|---|------|--------|----------|
| A4.1 | dispatch record 四状态 nullability 非法组合 | **FIXED** | test_state_schema.py:608-674 覆盖 PENDING/WAITING_FOR_LANE/DISPATCHING/CANCELLED 四种非法字段组合 |
| A4.2 | dispatch exception/timeout/close cleanup | **FIXED** | 7 个新测试覆盖 timeout、exception、EOF、stream crash、close suppression（test_dispatch_scheduler.py:402-621） |
| A4.3 | cancel_session_runs Phase 5 集成覆盖 | **FIXED** | 7 个测试覆盖 queued/active worker/idempotency/unsupported（test_public_cancel_session_runs.py:327-477 + test_active_cancel_dispatch.py:469） |

### A5. HostLocalExecutionOptions root-cause

| # | Item | Status | Evidence |
|---|------|--------|----------|
| A5.1 | create_host_command_handle 对非空 local_execution fail-fast | **FIXED** | `if options.local_execution is not None: raise ValueError(...)`（command.py:207-211）。测试 `test_factory_rejects_local_execution_without_hidden_scheduler`（test_command_handle.py:356-389） |
| A5.2 | public contract 测试覆盖 valid shape/typed field 错误/worker_factory=None | **FIXED** | 4 个测试（test_public_contracts.py:462-493）覆盖有效构造、runner_spec/runner_options/agent_policy 类型错误、worker_factory=None |

## Residual Gaps

### R1. A1.5 缺 scheduler 级 ingest_exception 集成测试（低风险）

- 代码路径正确：`dispatch.py:900-909` 在 `ingestor.ingest()` 抛异常时调用 `close_worker_lost(worker_lifecycle_signal="ingest_exception")`
- 单元测试已覆盖 `close_worker_lost` 机制（test_engine_ingest_mapping.py:618）
- 缺少：scheduler `_consume_worker_events` 中 `ingestor.ingest()` 自身抛异常的端到端测试
- 风险评估：低。代码路径与 stream exception 路径（已测试，:590）共享相同的 `close_worker_lost` + finally 清理逻辑，区别仅在于 `worker_lifecycle_signal` 字符串值不同

### R2. 1102 Finding 5: RunInputBuilder 两次独立读事务违反快照一致性（中风险，不阻塞）

- 状态：**未修复**（controller adjudication 未要求当前 PR 修复）
- `load_current_run_facts`（run_input.py:316）和 `load_session_continuity`（run_input.py:411）仍使用独立 `run_read` 事务
- 实际损害有限：continuity query 使用 `attempt.started_event_sequence` 做上界过滤，新事件会被 WHERE 子句排除
- 建议：后续 cleanup 中合并为同一读事务

### R3. 1102 Finding 7: cancel 信号在 worker 注册前到达时丢失（中风险，不阻塞）

- 状态：**未修复**（controller adjudication 已将 active cancel watchdog 归 deferred-with-owner）
- `ActiveWorkerRegistry.cancel()` 在 worker 未注册时返回 False，`_propagate_active_cancel_targets` 不检查返回值
- durable CANCELLING 状态仍为真源，Engine 最终通过 `CancellationToken` 观察取消
- 建议：后续 Phase 补充 cancel watchdog 或 retry 机制

## 运行的命令

```bash
# 完整 host 测试套件
pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_run_input_builder.py tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py tests/host/test_public_contracts.py \
  tests/host/test_command_handle.py tests/host/test_public_cancel_session_runs.py \
  tests/host/test_phase5_local_execution_integration.py \
  tests/host/test_active_cancel_dispatch.py -q
# 结果: 124 passed

# pyright 类型检查
python -m pyright dayu/host tests/host
# 结果: 0 errors, 0 warnings, 0 informations
```

## 结论

Controller adjudication 中 A1-A5 全部 accepted items 已验证通过。3 项 residual gaps 均为低/中风险且不阻塞 PR：A1.5 缺 ingest_exception 集成测试（低风险，机制正确）、1102 F5 读事务一致性（中风险，实际损害有限）、1102 F7 cancel 竞态（中风险，deferred-by-design）。
