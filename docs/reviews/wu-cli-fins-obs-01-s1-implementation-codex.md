# WU-CLI-FINS-OBS-01 S1 Implementation Artifact

## Slice ID / Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: `implementation`
- Slice: `S1-fins-job-event-contract`
- Scope implemented: Fins 自有 ingestion job event contract、store append/read API、filesystem JSONL sidecar、runtime 状态事件追加，以及对应 Fins runtime 测试。
- Scope intentionally not entered: S2 runtime progress helper、S3 Service subscription、S4 CLI live UI、S5 logging / CLI audit、review、commit、push、PR。

## Files Changed

- `dayu/fins/ingestion_events.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `docs/reviews/wu-cli-fins-obs-01-s1-implementation-codex.md`

## Implementation Summary

- Added `FinsIngestionJobEventType`, `FinsIngestionJobEventAppend`, `FinsIngestionJobEventRecord`, and bounded JSON-compatible payload validation.
- Event type docs/helpers explicitly separate status transition events from observation/progress events. `PROGRESS` and `CANCEL_REQUESTED` are not implemented as job state transitions.
- Extended `FinsIngestionJobStore` with `append_job_event` and `read_job_events`.
- Implemented `FsFinsIngestionJobStore` sidecar persistence at `<job_id>.events.jsonl`.
- Event sequence allocation uses the existing `.store.lock` `RuntimeFileLock` path shared with job record operations. No independent sidecar lock was introduced.
- Added `FinsIngestionRuntime.read_job_events(...)`.
- Runtime now appends:
  - `JOB_QUEUED` after queued job record creation.
  - `JOB_RUNNING` or `JOB_CANCELLED` after running claim.
  - `CANCEL_REQUESTED` after an active job is marked cancelling.
  - `JOB_SUCCEEDED` / `JOB_FAILED` / `JOB_CANCELLED` after terminal save.
- Event append does not mutate job status. Job record save/claim methods remain the status truth.
- Runtime event append failures log bounded WARN and do not roll back terminal records. Store API still fails fast for invalid event payload.

## Tests / Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed, `47 passed, 3 warnings`.
  - Warnings are existing `edgar` deprecation warnings from dependencies.
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.

## README Decision

- Read `dayu/fins/README.md` Agent update constraints before implementation.
- S1 introduces a public Fins ingestion event contract that likely belongs in the README's current-code Fins ingestion runtime contract section.
- README was not updated because this slice's explicit allowed files exclude README and the user explicitly listed README under `Do not modify`.
- Residual doc-sync item: when README updates are allowed, add only landed facts about `FinsIngestionRuntime.read_job_events(...)` and Fins ingestion job event sidecar semantics.

## Residual Risks / Uncovered Areas

- S1 only emits coarse status events. Runtime-owned `PROGRESS` event emission is intentionally deferred to S2.
- Service-facing event projection and terminal fallback are intentionally deferred to S3.
- CLI event consumption, cancel UX, and log assembly are intentionally deferred to later slices.
- README doc sync remains pending due to this slice's file modification constraints.

## Completion Status

`ready-for-review`
