# Gateflow Implementation Artifact: Host Phase 8 P8-S3 Minimal Read Model / Repair

## Gate

- Work unit: Host Phase 8 Projection Core / Event Stream
- Gate: P8-S3 implementation
- Approved plan: `docs/host/phase8-projection-core-event-stream-plan.md`
- Baseline accepted slice: `c891792`
- Branch: `feat/host-phase8-projection-core-event-stream`

## Scope

Implemented only P8-S3 minimal RunResult / Session timeline read model and internal repair helper.

Non-goals kept:

- No public timeline facade.
- No command path, Engine, runtime, Service, UI or Fins changes.
- No public command method for repair.
- No custom SQLite connection in repair.
- No commit, push, PR or review gate.

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/read_model.py`
- `dayu/host/_event_payload.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_import_boundary.py`
- `dayu/host/README.md`
- `tests/README.md`

## Implemented Plan Items

- Added `host_run_results` and `host_session_timeline_items` fresh schema DDL, indexes and schema version bump.
- Added durable row codecs and transaction-scoped store helpers for RunResult and Session timeline items.
- Added `MinimalReadModelProjectionConsumer` using existing `ProjectionConsumer` / `ProjectionRunner`.
- Mapped terminal facts `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, `RUN_LOST` into minimal RunResult.
- Mapped `USER_INPUT_ACCEPTED` and Run lifecycle / terminal canonical facts into Session timeline items.
- Preserved repeated `USER_INPUT_ACCEPTED` rows by event identity; no display text based merge.
- Added typed payload helper for optional payload text. Missing `display_text` maps to SQL `NULL`; invalid typed value fails projection.
- Added internal `repair_minimal_read_models(...)` with `ProjectionRepairResult`.
- Repair uses injected `HostTransactionRunner` and `ProjectionRunner`; `reset_checkpoint=True` performs a short reset transaction before replay.
- Public read truth boundaries remain unchanged: `get_run` still reads durable Run truth, and `stream_run_events` remains EventLog-backed.

## Validation

Passed:

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```

Results:

- `71 passed`
- `pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed

## Documentation Decision

- Updated `dayu/host/README.md` because Host durable projection / minimal read model boundaries changed.
- Updated `tests/README.md` because `tests/host/test_projection_read_model.py` is a new Host test file and the focused Host projection command changed.

## Residual Risks

- Public `get_run` intentionally remains durable-state based and does not yet surface RunResult summary refs. This is allowed by P8-S3 and preserves current public read truth boundaries.
- Repair batching is implemented through the existing `ProjectionRunner.run_once(..., limit=batch_size)` contract. The existing runner commits per scanned EventLog row; P8-S3 did not allow modifying `dayu/host/projection.py`.
- Timeline item kinds are intentionally minimal (`user_input`, `run_lifecycle`, `run_terminal`) and are not a UI transcript contract.

## Stop Status

P8-S3 implementation complete. Stopped before code review, commit, push or PR as requested.
