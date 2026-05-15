# Gateflow Fix Artifact: Host P5-S4 EngineEvent Ingest B1

- **Gate**: Host Phase 5 P5-S4 EngineEvent Ingest Mapping And Terminal Closeout fix
- **Source finding**: MiMo B1 blocking
- **Status**: fixed

## Finding

Terminal candidate duplicate replay returned `EngineIngestStatus.DUPLICATE` with `terminal_closeout=True`, but did not trigger `wake_queue_promotion`. If the original terminal closeout wakeup failed or was not consumed, duplicate replay could not retry the required same-session queue promotion check.

## Root Cause

`EngineEventIngestor.ingest()` and worker lifecycle closeout paths only triggered promotion wakeup for `terminal_closeout=True` plus `ACCEPTED`. Duplicate terminal replay was treated as an inert idempotency result even though the durable terminal facts already exist and the design requires terminal closeout success to make promotion retryable.

## Fix

- Added a shared terminal promotion retry path in `EngineEventIngestor`.
- `terminal_closeout=True` with either `ACCEPTED` or `DUPLICATE` now calls `wake_queue_promotion(session_id)` and returns `promotion_triggered=True`.
- Applied the same behavior to normal EngineEvent terminal ingest and worker lifecycle closeout helpers used by clean EOF / worker lost paths.
- Added regression coverage for:
  - duplicate `final_answer` candidate retrying promotion wakeup;
  - duplicate clean EOF lifecycle closeout retrying promotion wakeup.

## Changed Files

- `dayu/host/engine_ingest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `docs/reviews/gateflow-fix-host-p5-s4-engine-event-ingest-20260515.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q`
  - Passed: `10 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Passed: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Passed

## Residual Risk

- No additional residual risk introduced by this fix. The broader P5-S4 residual risks remain as recorded in the implementation artifact.
