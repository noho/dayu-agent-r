# WU-TOOLS-01-F01 S1 Implementation - Shared Fins Runtime Foundation

## Gate Metadata

- Gate: implementation only.
- Work unit: `WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools`.
- Slice: `S1 - Shared Fins Runtime Foundation`.
- Accepted plan commit: `27f91192`.
- Starting HEAD noted by user: `8aac7881`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md`.
- Scope guard: only S1 was implemented. No code review, fix gate, commit, push, PR, control document update, Host/Engine/Service/config/provider/README change was performed.

## Scope And Non-goals

Implemented:

- Added Fins-owned typed download/preprocess request shapes, result-summary shapes, job status enum, operation enum, durable job record and job start shape.
- Added a Fins-owned job store protocol and filesystem implementation for job records only.
- Added a workspace-derived job store path: `<workspace_root>/.dayu/fins_ingestion/jobs`.
- Added atomic plus locked JSON record writes using a workspace job-store lock file and atomic replace.
- Extended `DefaultFinsRuntime.create(workspace_root=...)` to assemble read repositories, `FinsToolService` and `FinsIngestionRuntime` from the same storage repository set.
- Added `DefaultFinsRuntime.get_ingestion_runtime()` with the same lazy locked pattern as `get_tool_service()`.
- Preserved read provider and read `FinsToolService` behavior.

Not implemented:

- No download/preprocess tool providers.
- No `include_ingestion_tools` behavior change.
- No Host wait adapter or Service assembly wiring.
- No real download pipeline, preprocess pipeline, upload, CLI or source-specific network adapter.
- No Host durable schema, Engine contract, config or README change.

## Changed Files

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md`

## Key Types, Functions And Data Flow

New key types:

- `FinsDownloadRequest`
- `FinsPreprocessRequest`
- `FinsDownloadResultSummary`
- `FinsPreprocessResultSummary`
- `FinsIngestionOperationKind`
- `FinsIngestionJobStatus`
- `FinsIngestionJobRecord`
- `FinsIngestionJobStart`
- `FinsIngestionJobStore`
- `FsFinsIngestionJobStore`
- `FinsIngestionRuntime`

Call path implemented:

```text
DefaultFinsRuntime.create(workspace_root=...)
-> build_fs_repository_set(...)
-> FsCompanyMetaRepository / FsSourceDocumentRepository / FsProcessedDocumentRepository
-> FinsToolService lazy assembly via get_tool_service()
-> FsFinsIngestionJobStore.from_workspace_root(workspace_root)
-> FinsIngestionRuntime lazy assembly via get_ingestion_runtime()
```

Runtime start path:

```text
FinsIngestionRuntime.start_download(request)
-> dayu.fins.ticker_normalization.normalize_ticker(request.ticker)
-> build bounded request summary
-> persist queued FinsIngestionJobRecord
-> return FinsIngestionJobStart
```

```text
FinsIngestionRuntime.start_preprocess(request)
-> dayu.fins.ticker_normalization.normalize_ticker(request.ticker)
-> build bounded request summary
-> persist queued FinsIngestionJobRecord
-> return FinsIngestionJobStart
```

Job store behavior:

- Record files are JSON-compatible and bounded.
- Record writes are guarded by `<job_store>/.store.lock`, then written to a unique temp file, `fsync`ed, atomically replaced and directory-`fsync`ed.
- `request_cancel(job_id)` maps active jobs to `cancelling` with `cancellation_requested=True`.
- Terminal jobs (`succeeded`, `failed`, `cancelled`) are returned unchanged and never move back to active.

## Shared Runtime Preservation

S1 makes `DefaultFinsRuntime` the explicit Fins assembly root without introducing a Python singleton. Two runtime instances created for the same `workspace_root` are separate Python objects, but derive the same filesystem job store path and can read each other's records. This keeps tool providers, future Service wiring and future CLI as adapters over the same Fins business runtime instead of duplicating ticker normalization or job-state rules.

Ticker normalization is called through `dayu.fins.ticker_normalization.normalize_ticker`; no suffix parsing, market inference or company-id logic was added outside the public ticker normalization module.

Financial document repositories remain the existing `dayu.fins.storage` protocol implementations. The new job store persists only Fins governance records and does not store source document bodies, processed payloads, raw provider payloads or raw filesystem document paths.

## Validation

Command:

```text
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py
```

Result:

```text
17 passed, 3 warnings
```

Warnings were third-party `edgar` deprecation warnings.

Command:

```text
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright also printed a version-available notice (`1.1.409 -> 1.1.410`), not a type failure.

## Residual Risks And Owners

- Covered by later approved slice: `start_download` and `start_preprocess` only persist queued records and do not execute real pipelines. Owners: F01 S2 and S3.
- Covered by later approved slice: no tool provider or Host waiting adapter exists yet for download/preprocess awaiting tools. Owners: F01 S4 and S5.
- Assigned to later work unit or explicit future owner: real SEC/CN/HK network download adapters remain outside S1 and outside the approved fake-start foundation.
- Covered by current slice tests: workspace-scoped job store sharing, queued record persistence, ticker normalization path, cross-instance read, cancellation transition, terminal non-regression and record leak boundaries.

No unclassified residual risk remains for S1.

## Completion Status

S1 implementation is complete within the approved scope. No stop condition was hit:

- No Host/Engine/Service/config/README change was required.
- Strict typing was satisfied without `Any`, `object`, untyped params or untyped returns in the new S1 contracts.
- Job store safety did not require Host durable schema or an external dependency.
- No real download/preprocess pipeline was needed.

No commit, push, PR, code review gate, fix gate, deepreview gate or control document update was performed.
