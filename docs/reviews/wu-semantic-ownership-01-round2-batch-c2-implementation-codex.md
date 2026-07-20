# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Implementation

## Scope

本次只实现 Batch C2: Host dispatch / promotion / cancellation / tool accept lifecycle owner 修复。

未修改 Batch D public contract、Batch E Fins typing/read-runtime、async DB actor、process-backed tool timeout、God module 拆分等 deferred / out-of-scope 项。OpenAI retry off-by-one 属于 Batch A，本次未触碰。

## Owner Decisions

- Scheduler / promotion / dispatch 拥有当前 work-item 的 ack、requeue、terminal closeout 语义；当前 dispatch record 在 durable retry exhausted 后不得从内存队列丢失。
- Recovery 不能依赖未注入或未运行的 scheduler watchdog；无 scheduler wakeup port 时，recovery 自己执行 fallback closeout。
- cancellation terminal payload 的 `requested_at` 由 committed `CANCEL_REQUESTED` canonical fact 派生，不使用 Engine token propagation wall clock。
- durable tool accept fact 是重复治理的权威真源；duplicate accepted index 更新失败只能产生诊断，不能推翻已接受结果或触发 side-effect tool 重执行。
- admission / run transition CAS 必须包含当前 Attempt identity；RECOVERING cancel 不再接受缺失 `current_attempt_id` 的状态。
- helper path 使用 DI 注入的 `EventLogStore`，不自行构造 store。

## Files Changed

- `dayu/host/dispatch.py`
- `dayu/host/admission.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/recovery.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_toolruntime_executor.py`

README 检查：已按触发规则检查 `dayu/host/README.md` 与 `tests/README.md`。本批修改为 Host 内部 owner lifecycle 语义与测试覆盖，不改变用户入口、命令参数、公开 contract 或 README 目标读者需要的新流程，因此未更新 README。

## Fixed Findings

- `143658-01/02/04/05`: scheduler close / `CancelledError` / recovery 路径现在对 active cancelling closeout 有 durable terminal owner；scheduler close 后的 promotion wakeup 不再把已完成 terminal closeout 降级为 lost。
- `145711-06`: dispatch first durable write retry exhausted 时当前 dequeued record 会被 requeue，再让上层 closeout / retry owner 处理。
- `145711-07`: promotion transient exception、durable retry exhausted 和 unexpected exception 后会 backoff requeue session wakeup，避免 accepted / queued Run 因单次 wakeup 丢失而永久停滞。
- `144330-03`: RUNNING Run + STARTING Attempt + dispatch worker accepted fact 的竞态窗口按 active worker cancel 处理，并先把 Attempt 收窄为 RUNNING。
- `144159-03`: active cancel terminal payload `requested_at` 改为来自 committed `CANCEL_REQUESTED.occurred_at`。
- `150304-04 / 144330-19`: durable tool accept 后 duplicate governance accepted index 失败只发 `duplicate_accepted_index_failed` 诊断，结果仍以 durable accept 为准。
- `150304-11`: `cancel_recovering_run_row` CAS 增加 `current_attempt_id`，transition 层拒绝没有 current Attempt 的 RECOVERING cancel。
- `150304-12`: `_promote_after_release` 释放 active slot 后返回 `DELEGATED_TO_GOVERNANCE`，不再谎报 `ACTIVE_RUN_EXISTS`。
- `150304-13`: session cancel replay 的 active cancelling target helper 使用注入的 `EventLogStore`。

## Validation

通过：

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

结果：`14 passed in 0.48s`。

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

结果：`275 passed in 9.03s`。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## Residual Risk

- 曾尝试运行包含整文件 `tests/host/test_dispatch_scheduler.py` 的大 focused 集合，除 C2 相关测试外出现 2 个 compaction / memory projection 断言失败：
  - `test_proactive_compaction_recovery_tier2_degrades_previous_view`
  - `test_reactive_compact_request_uses_latest_previous_view`
- 这两个失败位于 context compaction / memory projection 路径，不属于 Batch C2 的 dispatch / promotion / cancellation / tool accept lifecycle owner 修复；本批未修改 compaction 语义，未扩展到 Batch D/E 或其它 deferred 项。

## No Commit / Push

未执行 commit、push、PR 或 merge。
