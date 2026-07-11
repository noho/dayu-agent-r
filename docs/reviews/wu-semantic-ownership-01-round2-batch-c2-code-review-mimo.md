# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Code Review (MiMo)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD`
- Timestamp: 20260711-182455
- Included scope:
  - `dayu/host/dispatch.py` — scheduler close / CancelledError closeout, drain retry exhausted requeue, promotion backoff requeue, wake_queue_promotion close-idempotent
  - `dayu/host/admission.py` — session cancel replay injected EventLogStore, _promote_after_release DELEGATED_TO_GOVERNANCE
  - `dayu/host/durable/run_transition.py` — cancel_recovering CAS + current_attempt_id, STARTING+worker_accepted race narrowing, PromotionSkipReason.DELEGATED_TO_GOVERNANCE, _dispatch_record_has_worker_accept_fact
  - `dayu/host/durable/state.py` — cancel_recovering_run_row CAS + current_attempt_id
  - `dayu/host/engine_ingest.py` — cancellation terminal requested_at from committed CANCEL_REQUESTED.occurred_at
  - `dayu/host/recovery.py` — dispatch_wakeup_port check before deferring to watchdog
  - `dayu/host/tool_runtime.py` — durable accept diagnostic on duplicate governance failure
  - 8 test files: 14 targeted tests + full 275 suite pass
- Excluded scope: Batch D/E, wait expiry/supervisor, OpenAI retry off-by-one

## Focus Area Verification

### F1: scheduler close / CancelledError / recovery fallback close CANCELLING runs

**Verdict: PASS**

- `_consume_worker_events` (dispatch.py:3871-3895): `CancelledError` handler checks `cancellation_token.is_cancelled()`，尝试 ingest `_cancelled_eof_candidate` 产生 durable RUN_CANCELLED terminal facts。失败时 fallback 到 `_safe_close_worker_lost`。
- `close()` (dispatch.py:2486-2536): 先 `_active_registry.cancel_all()` 设置 cancellation token，再 cancel active tasks。CancelledError 被 `_suppress_task_cancel` 吞掉。
- `_cancelled_eof_candidate` (dispatch.py:4042-4082): `requested_at` 从 `cancellation_token.requested_at()` 取，fallback 到 `observed_at`。ingest 层（engine_ingest.py:1425-1450）从 committed CANCEL_REQUESTED event 取 `occurred_at` 作为权威 `requested_at`。
- `recovery.py:289-303`: `defer_accepted_cancel_to_watchdog` 为 True 时必须同时有 `dispatch_wakeup_port is not None` 才 defer；否则 recovery 执行 fallback closeout。
- 测试覆盖: `test_scheduler_close_writes_active_cancel_closeout_terminal`, `test_scan_defers_accepted_cancel_cancelling_to_watchdog_when_enabled`, `test_scan_accepted_cancel_without_scheduler_uses_recovery_fallback`

### F2: dispatch first durable write retry exhausted does not lose current dequeued record

**Verdict: PASS**

- `drain_once` (dispatch.py:2468-2472): `try/except HostTransactionRetryExhaustedError` — requeue `self._queue.put_nowait(record)` 后 re-raise。
- `_mark_waiting_for_lane` (dispatch.py:2863) 在 `_dispatch_one` 的 try/except 块**之前**调用，因此 `HostTransactionRetryExhaustedError` 逃逸到 `drain_once` 的 catch。
- 测试覆盖: `test_dispatch_first_durable_retry_exhausted_requeues_current_record` — 验证 queue.qsize==1 且 record identity 不变。

### F3: promotion transient exceptions requeue/backoff session wakeup

**Verdict: PASS**

- `_promotion_drain_loop` (dispatch.py:2791-2838): RuntimeError / HostTransactionRetryExhaustedError / Exception 均调用 `_requeue_promotion_after_backoff`。
- `_requeue_promotion_after_backoff` (dispatch.py:2840-2854): `loop.call_later(dispatch_poll_interval_seconds, ...)` 重新投递。检查 `self._closed` 防止关闭后投递。
- 测试覆盖: `test_wake_queue_promotion_requeues_after_transient_exception` — 第一次失败后 recovered.wait() 验证第二次执行。

### F4: cancel predispatch RUNNING+STARTING+WORKER_ACCEPTED race

**Verdict: PASS**

- `request_active_attempt_cancel_in_transaction` (run_transition.py:2847-2872): 读取 dispatch_record，检查 `_dispatch_record_has_worker_accept_fact`。若 STARTING + worker accepted，调用 `mark_attempt_running_row` 收窄为 RUNNING，再检查 `attempt.status != AttemptStatus.RUNNING`。
- `_dispatch_record_has_worker_accept_fact` (run_transition.py:5528-5544): 检查 worker_accepted_at / worker_accept_event_id / worker_accept_event_sequence 非 None，cancelled_event_id / cancelled_event_sequence 为 None。
- 测试覆盖: `test_cancel_run_starting_worker_accepted_enters_active_cancel` — 验证 Run 进入 CANCELLING，Attempt 收窄为 RUNNING。

### F5: cancellation terminal requested_at from committed CANCEL_REQUESTED event

**Verdict: PASS**

- `engine_ingest.py:1450`: `requested_at=cancel_requested.occurred_at`（committed CANCEL_REQUESTED canonical fact 的 occurred_at），不再使用 `format_utc_timestamp(data.requested_at)`（Engine token propagation wall clock）。
- `read_cancel_requested_event_from_run_link` 从 Run 的 durable link 读取 committed event。
- 测试覆盖: `test_run_cancelled_requested_at_uses_cancel_requested_event_time` — 验证 payload["requested_at"] 等于 CANCEL_REQUESTED event time 而非 Engine data.requested_at。

### F6: durable tool accept remains authoritative on duplicate governance failure

**Verdict: PASS**

- `tool_runtime.py:3719-3739`: `record_accepted` 调用包裹在 try/except 中。失败时仅 emit `duplicate_accepted_index_failed` diagnostic，不改变 return True（durable accept outcome 不变）。
- 测试覆盖: `test_duplicate_accepted_index_failure_keeps_durable_accept_outcome` — mock `record_accepted` raise RuntimeError，验证 outcome.value == {"secret": "accepted"} 且 diagnostic reason_code == "duplicate_accepted_index_failed"。

### F7: cancel_recovering_run_row CAS includes current_attempt_id

**Verdict: PASS**

- `state.py:4184-4216`: SQL WHERE 增加 `AND current_attempt_id = ?`，参数传入 `current_attempt_id`。
- `run_transition.py:2587-2593`: 调用前检查 `run.current_attempt_id is None` 返回 `INVALID_STATE`。
- 测试覆盖: `test_cancel_recovering_run_row_cas_requires_current_attempt` — 错误 attempt_id 返回 CAS_LOST，正确 attempt_id 返回 UPDATED。

### F8: _promote_after_release reports truthful owner-level reason

**Verdict: PASS**

- `admission.py:4451-4458`: `skip_reason=PromotionSkipReason.DELEGATED_TO_GOVERNANCE` 替代 `ACTIVE_RUN_EXISTS`。
- `run_transition.py:117`: 新增 `DELEGATED_TO_GOVERNANCE` enum member。
- 测试覆盖: `test_promote_after_release_reports_delegated_to_governance` — 验证 `result.skip_reason is PromotionSkipReason.DELEGATED_TO_GOVERNANCE`。

### F9: session cancel replay uses injected EventLogStore

**Verdict: PASS**

- `admission.py:4220-4240`: `_active_cancelling_targets_for_session_replay` 新增 `event_log_store: EventLogStore` 参数，替换 `EventLogStore()` 内联构造。
- 调用链: `_idempotent_session_cancel_result` (admission.py:4096) -> `_active_cancelling_targets_for_session_replay` 使用注入的 store。
- 测试覆盖: `test_cancel_session_replay_uses_injected_event_log_store` — 自定义 `_CountingEventLogStore` 统计 `read_event_by_id_count >= 1`。

### F10: No Batch D/E scope creep, no compatibility shim, no weak typing/docstring violations

**Verdict: PASS**

- 所有修改文件在 Batch C2 scope 内，未触及 Batch D/E deferred 项。
- 无兼容性 re-export / wrapper / facade。
- 所有新增/修改函数有完整中文 docstring（参数、返回值、异常）。
- pyright: 0 errors, 0 warnings, 0 informations。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Compaction/memory projection**: implementation artifact 记录了 `tests/host/test_dispatch_scheduler.py` 中 2 个 compaction / memory projection 断言失败（`test_proactive_compaction_recovery_tier2_degrades_previous_view`、`test_reactive_compact_request_uses_latest_previous_view`），不在 Batch C2 范围内，属 Batch D。
- **promotion backoff 无退避上限**: `_requeue_promotion_after_backoff` 使用固定 `dispatch_poll_interval_seconds` 延迟，无指数退避或最大重试次数。当前可接受因为 scheduler close 会终止循环，但如果 promotion 持久失败会持续消耗资源。
- **CancelledError 中 ingest 的 CancelledError 传播**: `_consume_worker_events` 的 CancelledError handler 中 `except Exception` 不捕获 CancelledError（BaseException 子类）。这是正确行为但未被测试覆盖。
- **Batch D/E 未覆盖**: Engine/Host public contract、Fins typing 等 deferred 项未触及。

## Conclusion

Batch C2 的 9 个 accepted findings 实现正确，语义所有权修复到位。所有 14 个针对性测试和 275 个完整套件通过，pyright 0 errors。无 correctness 或 semantic ownership 缺陷。
