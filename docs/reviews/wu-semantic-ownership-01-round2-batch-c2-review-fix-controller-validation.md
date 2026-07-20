# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Review Fix Controller Validation

## Scope

- Batch: C2 - Host dispatch / promotion / cancellation / tool accept lifecycle owner.
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-codex.md`
- Accepted review findings fixed:
  - `DS-C2-01`
  - `DS-C2-02`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py::test_cancel_run_starting_worker_accepted_enters_active_cancel tests/host/test_active_cancel_dispatch.py::test_scheduler_close_writes_active_cancel_closeout_terminal tests/host/test_engine_ingest_mapping.py::test_run_cancelled_requested_at_uses_cancel_requested_event_time -q`
  - Result: `3 passed`.
- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py::test_cancel_run_starting_worker_accepted_enters_active_cancel tests/host/test_active_cancel_dispatch.py::test_scheduler_close_writes_active_cancel_closeout_terminal tests/host/test_dispatch_scheduler.py::test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent tests/host/test_dispatch_scheduler.py::test_dispatch_first_durable_retry_exhausted_requeues_current_record tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_requeues_after_transient_exception tests/host/test_engine_ingest_mapping.py::test_run_cancelled_requested_at_uses_cancel_requested_event_time tests/host/test_recovery_scan.py::test_scan_defers_accepted_cancel_cancelling_to_watchdog_when_enabled tests/host/test_recovery_scan.py::test_scan_accepted_cancel_without_scheduler_uses_recovery_fallback tests/host/test_toolruntime_executor.py::test_duplicate_accepted_index_failure_keeps_durable_accept_outcome tests/host/test_public_cancel_session_runs.py::test_cancel_session_runs_includes_recovering_without_fail_closed tests/host/test_public_cancel_session_runs.py::test_cancel_run_recovering_replay_is_idempotent_per_run_id tests/host/test_run_attempt_transitions.py::test_cancel_recovering_run_row_cas_requires_current_attempt tests/host/test_admission_queue.py::test_promote_after_release_reports_delegated_to_governance tests/host/test_admission_queue.py::test_cancel_session_replay_uses_injected_event_log_store -q`
  - Result: `14 passed`.
- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py tests/host/test_toolruntime_executor.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py -q`
  - Result: `275 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.

## Controller Decision

Batch C2 review-fix is ready for re-review.

## Residual Risk

- Existing non-C2 compaction / memory projection failures documented in Batch C2 implementation artifact remain outside this fix.
- Batch D/E remain untouched.

