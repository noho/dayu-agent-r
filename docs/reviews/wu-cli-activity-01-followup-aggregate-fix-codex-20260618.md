# WU-CLI-ACTIVITY-01 Follow-up Aggregate Fix — AgentCodex

## Scope

- Aggregate review artifacts:
  - `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`
  - `docs/reviews/ds-aggregate-wu-cli-activity-01-followup-20260618-081532.md`
- Fix scope: non-blocking low findings from AgentMiMo aggregate review.

## Changes

- Added `test_read_events_after_matching_limit_covers_last_matching_row` to lock the `read_events_after_matching(...)` branch where matching rows fill the page and `covered_event_sequence` must stop at the last matching row.
- Added `test_runner_clears_failure_when_covered_cursor_advances_without_match` to verify that ProjectionRunner clears an existing projection failure when it advances checkpoint through a no-match covered cursor.
- Removed obsolete `CONTENT_DELTA` / `REASONING_DELTA` filtering from `dayu/host/read_api.py`; these rows are no longer durably emitted by Host ingest.
- Updated `memory_repair._validate_batch_size` docstring from scan-budget wording to page-size wording.

## Validation

- `pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_memory_repair.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q`
  - 120 passed
- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q`
  - 348 passed
- `python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## Residual Risk

- No known blocking residual risk.
