# WU-LIFE-01 + WU-LIFE-02 Slice B Implementation Report

## Scope

- Role: gateflow implementation worker.
- Controller: AgentController.
- Gate: implementation.
- Accepted plan commit: `975b9ba`.
- Accepted Slice A commit: `b8f4568`.
- Plan artifact: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`.
- Slice: Slice B - Scheduler close / cancel_all lifecycle matrix + focused close-window tests.

## Modified Files

- `tests/host/test_dispatch_scheduler.py`
  - Added `_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` with scenario id, close window, expected close action, expected durable mutation, expected resource cleanup, and coverage classification.
  - Added deterministic helpers for cancel-all after-register, lane-wait close, and close-cancellation retry windows.
  - Added close terminal fact assertion helper.
  - Added focused tests for `ActiveWorkerRegistry.cancel_all` snapshot semantics, non-empty dispatch queue close, lane-wait / pre-worker close, and close cancellation retry cleanup.
  - Extended promotion close coverage to prove tracked promotion task cancellation does not drain queued promotion work or write terminal facts.
- `docs/reviews/wu-life-01-02-implementation-sliceB-codex-20260601.md`
  - This implementation report.

## Tests Added Or Updated

- Added `test_scheduler_close_lifecycle_matrix_covers_slice_b_windows`.
- Added `test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel`.
- Added `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal`.
- Added `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact`.
- Added `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`.
- Updated `test_scheduler_close_cancels_tracked_promotion_task` to include queued promotion work and terminal fact assertions.

## Production Code Changes

- None.
- Tests-first execution did not prove a scheduler close or `cancel_all` production bug. Existing scheduler close behavior already supports retry after outer cancellation, fails closed after close, avoids close-created terminal facts, and leaves pending local queues to recovery / later dispatch paths.

## Validation

All commands were run after `source .venv/bin/activate`.

- `pytest tests/host/test_dispatch_scheduler.py -q`
  - Passed: `54 passed`.
- `pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q`
  - Passed: `20 passed`.
- `python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`.

## README And Doc Sync

- No README changes.
- `tests/README.md` was checked by trigger rule: this slice adds focused regression tests but does not change test layering, commands, markers, conventions, or maintenance rules.
- No package README is in scope because no production code, public API, schema, state-machine, CLI, configuration, or architecture boundary changed.

## Contract / Schema / State-Machine / Public Interface Changes

- Durable schema changes: none.
- EventLog type changes: none.
- Host public API changes: none.
- Public cancel command changes: none.
- Run / Attempt state-machine changes: none.
- Durable terminal semantics changes: none.

## Residual Risks

- The close cancellation retry test uses deterministic monkeypatch barriers around `LaneController.close`; it proves scheduler retry semantics at that cleanup boundary, not every possible cancellation instruction boundary inside scheduler close.
- The lane-wait close test uses a deterministic blocked acquire replacement to hit the pre-worker window; it proves scheduler close does not convert that window into worker startup timeout terminal facts.
- Stress / fuzz / soak close coverage remains out of scope per plan.

## Stop Conditions Hit

- None.
- No test required Host public close guarantee, durable terminal semantics, public cancel semantics, schema, EventLog, Run / Attempt state-machine, or unauthorized file changes.
- No test depended on nondeterministic sleep / race construction.
- No fix required lease, fencing, global registry closed state, or other new lifecycle abstraction.
