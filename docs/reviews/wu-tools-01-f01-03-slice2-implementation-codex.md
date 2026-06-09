# WU-TOOLS-01-F01-03 Slice 2 Implementation

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 2: Migrate SEC Downloader And SEC Download Runtime`
- Scope completed: SEC downloader、SEC download workflow、SEC runtime adapter、DefaultFinsRuntime SEC adapter registration、SEC downloader/pipeline/runtime tests。
- Explicit non-goals preserved: no CN/HK download, no upload provider/runner/workflow, no CLI entrypoint, no commit, no edit to `docs/host/issues-implementation-control.md`。

## OLD Import Tracing Evidence

Direct OLD source roots used:

- `/Users/leo/workspace/dayu-agent/dayu/fins/downloaders/sec_downloader.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/sec_download_workflow.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/sec_download_filing_workflow.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/sec_pipeline.py`
- `/Users/leo/workspace/dayu-agent/tests/fins/test_sec_downloader.py`
- `/Users/leo/workspace/dayu-agent/tests/fins/test_sec_pipeline_download.py`
- `/Users/leo/workspace/dayu-agent/tests/fins/test_sec_pipeline_download_stream.py`

Migrated modules from direct SEC download workflow/test imports:

- `download_events.py`: OLD `sec_download_workflow.py` and `sec_download_filing_workflow.py` import `DownloadEvent` / `DownloadEventType`.
- `sec_download_workflow.py`: OLD SEC pipeline download entrypoint delegates to this workflow.
- `sec_download_filing_workflow.py`: OLD download workflow calls single-filing stream boundary.
- `sec_download_persistence.py`: OLD single-filing workflow delegates file entry, rejected artifact, and reprocess marker persistence here.
- `sec_download_source_upsert.py`: OLD single-filing workflow imports `upsert_downloaded_filing_source_document`.
- `sec_download_state.py`: OLD pipeline imports rejection registry, SEC cache, skip/fingerprint helpers.
- `sec_download_event_mapping.py`: OLD pipeline imports file result and filing event mapping helpers.
- `sec_download_diagnostics.py`: OLD pipeline imports insufficient filings and XBRL warning helpers.
- `sec_form_utils.py`: OLD pipeline and filing collection import form/date/window helpers.
- `sec_filing_collection.py`: OLD pipeline imports filing table collection and 6-K candidate classification.
- `sec_6k_rules.py`: OLD filing collection, persistence, and primary-document repair import 6-K rules.
- `sec_6k_primary_document_repair.py`: OLD single-filing workflow imports 6-K primary-document repair.
- `sec_sc13_filtering.py`: OLD pipeline imports SC13 direction filtering, browse-edgar retry, and constants covered by OLD tests.
- `sec_company_meta.py`: OLD pipeline imports SEC alias extraction/merge and company meta upsert.
- `sec_safe_meta_access.py`: OLD pipeline imports safe meta access and document-version helper.

Additional direct-evidence modules:

- `sec_fiscal_fields.py`: OLD `sec_download_persistence.py` directly imports `_infer_download_fiscal_fields`; OLD pipeline tests also patch `sec_fiscal_fields` for fiscal inference behavior.
- `sec_rebuild_workflow.py`: OLD `test_sec_pipeline_download.py` directly covers `download(rebuild=True)`, and OLD `sec_pipeline.py` imports `sec_rebuild_workflow` for that download rebuild path. This is download rebuild, not process/upload migration.

Not migrated:

- OLD CN/HK downloader modules.
- OLD upload modules (`sec_upload_workflow`, upload event modules, Docling upload service).
- OLD process modules (`sec_process_workflow`, snapshot/export helpers).
- OLD ingestion service / job manager / CLI facade.

Boundary scan result: no migrated production SEC module imports `dayu.log`, `dayu.workspace_paths`, `dayu.engine`, `dayu.host`, CN/HK downloader modules, upload workflow modules, or process workflow modules.

## What Changed

Production:

- Added `dayu/fins/downloaders/sec_downloader.py` from OLD SEC downloader logic, with narrow adaptation:
  - `dayu.log` -> `dayu.fins._log`
  - `SEC_USER_AGENT_ENV` defined as an explicit typed module constant.
  - SEC default sleep/timeout/retry/rate-limit values annotated as typed constants.
  - SEC throttle state path now derives from `workspace_root / ".dayu/sec_throttle"`.
- Added SEC download pipeline support modules under `dayu/fins/pipelines/`, preserving OLD download behavior for selection, form windows, cache, skip/overwrite, 6-K, SC13, rejection registry, and rebuild-local-meta download path.
- Added narrow `dayu/fins/pipelines/sec_pipeline.py`:
  - exposes SEC download facade and stream aggregation only;
  - omits upload/process/CLI surfaces;
  - builds a synchronous `SecDownloadAdapter` implementing `FinsSourceDownloadAdapter`.
- Closed the controller preflight typing gap:
  - replaced migrated OLD weak JSON annotations with `JsonValue`, JSON mapping/list guard helpers, `TypedDict`, and narrow type aliases;
  - typed SEC filing workflow boundaries as `FilingRecord` instead of generic JSON;
  - typed internal file download results separately from JSON event payloads because download aggregation temporarily carries `FileObjectMeta`;
  - replaced test fake escape hatches with concrete fake types, narrow callbacks, and typed JSON helpers;
  - no `Any` or type `object` annotations remain in the Slice 2 SEC production/test files scanned below.
- Updated `FinsSourceDownloadAdapterRequest` with overwrite, rebuild marker, and `FinsJobCancellationChecker`.
- Updated `FinsSourceDownloadAdapterResult` to allow `persisted_summary` for adapters whose migrated workflow writes through repositories internally.
- Updated runtime download execution to accept persisted summaries without double-writing documents/rejections.
- Registered the same SEC adapter for `(source="sec", market="US")` and `(source="auto", market="US")` in `DefaultFinsRuntime.get_ingestion_runtime()`.
- Narrowed `dayu/fins/downloaders/__init__.py` to export SEC only, avoiding CN/HK imports before their slice.

Tests/docs:

- Added OLD-derived SEC downloader tests and SEC pipeline download/stream tests.
- Updated ingestion runtime tests for default SEC adapter registration and changed unsupported source coverage to a truly unknown source.
- Updated `dayu/fins/README.md` and `tests/README.md` because their update constraints cover current Fins runtime capability and Fins test coverage.

## Slice 2 Invariants

- SEC-only boundary: satisfied. No CN/HK downloader or workflow migrated; downloader package no longer imports CN/HK names.
- No upload: satisfied. Narrow `sec_pipeline.py` does not import upload workflow, upload event modules, Docling upload service, or upload company-meta helpers.
- No process: satisfied. Narrow `sec_pipeline.py` does not import process workflow or snapshot/export helpers.
- OLD downloader business logic preserved: satisfied by copying OLD `sec_downloader.py` and adapting only imports/constants/path helper/logging.
- OLD SEC workflow behavior preserved: satisfied by migrating OLD download workflow/helper modules and keeping filtering/download/6-K/SC13/rejection/cache logic in those modules.
- Sync adapter protocol preserved: satisfied. `FinsSourceDownloadAdapter.download(...)` remains synchronous; OLD async stream is bridged through the migrated synchronous `SecPipeline.download(...)` aggregation running in the Fins background job thread.
- `auto` + US deterministic SEC route: satisfied by registering `(auto, US)` to the same SEC adapter instance as `(sec, US)`.
- Workspace root source: satisfied. SEC throttle/cache paths are derived from `DefaultFinsRuntime.workspace_root` / pipeline workspace root only.
- Repository-only writes: satisfied. SEC workflow writes source meta/files, rejected filing artifacts, rejection registry, and processed reprocess markers through `dayu.fins.storage` repositories.
- Cooperative cancellation: satisfied. Runtime passes `_RuntimeJobCancellationChecker` into adapter request, and SEC pipeline passes it through OLD `cancel_checker` workflow boundary.
- Explicit SEC User-Agent/rate defaults: satisfied by typed constants and `test_sec_downloader_explicit_sec_defaults_are_stable`.
- OLD weak typing adaptation: satisfied. JSON-like payloads use `JsonValue` / JSON guards / typed result structures; non-JSON boundaries use `FilingRecord`, `FileObjectMeta`, protocols, callbacks, or concrete fake types.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `111 passed, 7 warnings`
  - Warnings: existing pytest unknown `unit` marker warnings in migrated downloader tests and edgartools deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output.
- Targeted Slice 2 type-signature scan:
  - Command: `rg -n "\bAny\b|\bobject\b" dayu/fins/downloaders dayu/fins/pipelines tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py`
  - Result: no matches.

## README Decision

- `dayu/fins/README.md`: updated. The Slice changes alter current `dayu.fins` capability: default runtime now has SEC/US production download adapter and `(auto, US)` deterministic SEC registration.
- `tests/README.md`: updated. The Slice adds SEC downloader and SEC pipeline tests and extends ingestion runtime test coverage.
- `docs/host/issues-implementation-control.md`: not modified per task instruction.

## Residual Risks / Blockers

- No blocker.
- Live SEC network behavior is not exercised by tests; tests remain deterministic and fixture/fake based. This is accepted for Slice 2 validation because required tests are network-free.
- CN/HK download remains unsupported until later slices.
- Production upload runner/provider remains unsupported until later slices.
