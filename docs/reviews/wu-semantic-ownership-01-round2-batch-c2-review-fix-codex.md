# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Review Fix

## Scope

- Gate: `review-fix`
- Agent: AgentCodex
- Batch: C2 - Host dispatch / promotion / cancellation / tool accept lifecycle owner
- Fixed accepted findings only:
  - `DS-C2-01`
  - `DS-C2-02`
- Not touched: Batch D/E, public contract redesign, Fins typing/read-runtime, async DB actor, process-backed tool timeout, God module split, OpenAI retry off-by-one.

## Motivation And Owner Decision

- `DS-C2-01` 成立。`request_active_attempt_cancel_in_transaction` 中的内层 defensive check 位于 `_dispatch_record_has_worker_accept_fact(...)` 已经证明 `dispatch_record` 与 `worker_accepted_at` 存在之后，是不可达分支。修复应在 durable transition owner 内完成，避免 state-machine path 保留误导性死代码。
- `DS-C2-02` 成立。synthetic cancelled EOF candidate 的 `RunCancelledData.requested_at` 属于取消请求业务事实，不应由 Host cancellation token 的传播时间生产。修复应在 dispatch producer 边界读取 committed `CANCEL_REQUESTED` canonical fact，并继续让 ingest closeout 使用同一 durable source of truth。

## Fixed Review Findings

### DS-C2-01

修复位置：`dayu/host/durable/run_transition.py`

- 删除不可达的 `dispatch_record is None or dispatch_record.worker_accepted_at is None` runtime branch。
- 将 bool helper 改为 `_dispatch_record_worker_accepted_at(...) -> str | None`，只有完整 worker accept durable fact 且未 direct cancel 时返回 accepted 时间。
- `request_active_attempt_cancel_in_transaction` 使用该返回值完成类型收窄，再调用 `mark_attempt_running_row(...)`。

### DS-C2-02

修复位置：`dayu/host/dispatch.py`

- 新增 `_ReadCommittedCancelRequestedAtOperation` 与 `_read_committed_cancel_requested_at(...)`，从 Run typed cancel link 读取 committed `CANCEL_REQUESTED.occurred_at`。
- `_consume_worker_events` 在 StopAsyncIteration 和 CancelledError synthetic cancel closeout 路径中，先读取 canonical cancel request time，再构造 `_cancelled_eof_candidate(...)`。
- `_cancelled_eof_candidate(...)` 不再读取 `cancellation_token.requested_at()`；其 `RunCancelledData.requested_at` 只接收 committed cancel request time。
- 若 canonical cancel request fact 缺失，不合成带错误业务时间的 candidate。

## Tests And Validation

通过：

```bash
source .venv/bin/activate && pytest \
 tests/host/test_active_cancel_dispatch.py::test_cancel_run_starting_worker_accepted_enters_active_cancel \
 tests/host/test_active_cancel_dispatch.py::test_scheduler_close_writes_active_cancel_closeout_terminal \
 tests/host/test_engine_ingest_mapping.py::test_run_cancelled_requested_at_uses_cancel_requested_event_time -q
```

结果：`3 passed in 0.37s`

```bash
source .venv/bin/activate && pytest \
 tests/host/test_active_cancel_dispatch.py::test_cancel_run_starting_worker_accepted_enters_active_cancel \
 tests/host/test_active_cancel_dispatch.py::test_scheduler_close_writes_active_cancel_closeout_terminal \
 tests/host/test_dispatch_scheduler.py::test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent \
 tests/host/test_dispatch_scheduler.py::test_dispatch_first_durable_retry_exhausted_requeues_current_record \
 tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_requeues_after_transient_exception \
 tests/host/test_engine_ingest_mapping.py::test_run_cancelled_requested_at_uses_cancel_requested_event_time \
 tests/host/test_recovery_scan.py::test_scan_defers_accepted_cancel_cancelling_to_watchdog_when_enabled \
 tests/host/test_recovery_scan.py::test_scan_accepted_cancel_without_scheduler_uses_recovery_fallback \
 tests/host/test_toolruntime_executor.py::test_duplicate_accepted_index_failure_keeps_durable_accept_outcome \
 tests/host/test_public_cancel_session_runs.py::test_cancel_session_runs_includes_recovering_without_fail_closed \
 tests/host/test_public_cancel_session_runs.py::test_cancel_run_recovering_replay_is_idempotent_per_run_id \
 tests/host/test_run_attempt_transitions.py::test_cancel_recovering_run_row_cas_requires_current_attempt \
 tests/host/test_admission_queue.py::test_promote_after_release_reports_delegated_to_governance \
 tests/host/test_admission_queue.py::test_cancel_session_replay_uses_injected_event_log_store -q
```

结果：`14 passed in 0.48s`

```bash
source .venv/bin/activate && pytest \
 tests/host/test_active_cancel_dispatch.py \
 tests/host/test_engine_ingest_mapping.py \
 tests/host/test_recovery_scan.py \
 tests/host/test_toolruntime_executor.py \
 tests/host/test_public_cancel_session_runs.py \
 tests/host/test_run_attempt_transitions.py \
 tests/host/test_admission_queue.py -q
```

结果：`275 passed in 9.05s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过，无输出。

## README Check

已按触发规则检查 `dayu/host/README.md` 与 `tests/README.md` 的更新约束。本次 review-fix 只修 Host 内部 durable transition / dispatch synthetic cancel candidate 的 owner 语义，并补充测试断言；不改变用户入口、公开 API、命令参数、运行流程、稳定开发接口或测试分层说明，因此未更新 README。

## Residual Risk

- 如果 active cancel path 缺失 committed `CANCEL_REQUESTED` link，dispatch producer 现在不会合成 `RUN_CANCELLED` candidate，避免写入错误 `requested_at` 语义。该缺失 link 场景本身是 durable cancel 前置异常，不属于本次两个 accepted findings 的正常路径。
- 既有 controller validation 记录的两个非 C2 `tests/host/test_dispatch_scheduler.py` compaction / memory projection 断言失败仍未处理，继续归属 Batch D / 非 C2 范围。

## No Commit / Push

未执行 commit、push、PR 或 merge。
