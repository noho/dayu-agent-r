# WU-CLI-FINS-OBS-01 S1 Fix

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S1-fins-job-event-contract`
- Gate: fix
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-s1-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260615-183010.md`
  - `docs/reviews/code-review-20260615-183203.md`
- Adjudication: `docs/reviews/wu-cli-fins-obs-01-s1-code-review-adjudication-20260615-183453.md`

## Accepted Findings Fixed

- `MiMo-001`: added non-terminal `JOB_RUNNING` append failure coverage. The test forces `append_job_event(...)` to raise `OSError` for `JOB_RUNNING`, verifies the job still reaches `SUCCEEDED`, verifies the sidecar converges with `JOB_QUEUED` and `JOB_SUCCEEDED`, and verifies bounded WARN fields are emitted.
- `DS-F002`: removed `FinsIngestionJobEventAppend`, `FinsIngestionJobEventRecord`, and `FinsIngestionJobEventType` from `dayu.fins.ingestion_runtime.__all__`. The canonical public import path remains `dayu.fins.ingestion_events`.
- `DS-F003`: updated `dayu/fins/README.md` and `tests/README.md` under their README update constraints with only landed S1 facts.

## Files Changed

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-fins-obs-01-s1-fix-codex.md`

## Implementation Summary

- Kept runtime behavior unchanged.
- Added a focused regression test for non-terminal event sidecar append failure.
- Narrowed `ingestion_runtime.__all__` to runtime-owned public symbols while leaving internal imports from `dayu.fins.ingestion_events` intact.
- Documented `FinsIngestionRuntime.read_job_events(...)`, the ingestion job event sidecar, status versus observation event semantics, bounded payload expectations, and the new test coverage facts.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed, `48 passed, 3 warnings`.
  - Warnings: existing edgar deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.

## README Updates Performed

- `dayu/fins/README.md`: added current public event/read contract facts and current sidecar semantics.
- `tests/README.md`: added current `tests/fins/test_fins_ingestion_runtime.py` coverage for event sidecar sequence/read/payload/WARN paths.

## Deferred / Rejected Findings Not Touched

- Deferred S2 sequence lookup performance work was not changed.
- Rejected empty payload WARN log formatting was not changed.
- Terminal duplicate idempotency hardening was not implemented.

## Residual Risks / Uncovered Areas

- Event sidecar sequence lookup scalability remains covered by later approved slice S2 before high-frequency progress events.
- S2 payload construction behavior remains a later-slice review concern because S1 status events use empty payloads.
- No terminal duplicate idempotency defense was added, matching adjudication.

## Completion Status

- Status: `ready-for-rereview`.
