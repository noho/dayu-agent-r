# WU-TOOLS-01-F01-03 Slice 4 Implementation - AgentCodex

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 4: Migrate Upload Service And Production Upload Runtime`
- Objective: migrate production SEC/CN upload workflow into `FinsIngestionRuntime.start_upload(...)` through `FinsUploadRunner`, while preserving OLD upload business behavior and keeping runtime responsible only for job lifecycle.
- Non-goals preserved: no upload tool/provider, no wait adapter/provider assembly, no CLI, no Host/Engine public contract change, no GitHub Issue update, no process/rebuild migration.

## OLD Direct Import Tracing Evidence

Direct tracing was performed against `/Users/leo/workspace/dayu-agent`:

- `dayu/fins/pipelines/docling_upload_service.py` imports:
  - stdlib file/hash/json/mimetype helpers
  - `dayu.fins.domain.document_models`
  - `dayu.fins.domain.enums.SourceKind`
  - `dayu.fins.storage` repository protocols
  - `dayu.fins.ticker_normalization`
  - Docling conversion boundary
- `dayu/fins/pipelines/sec_upload_workflow.py` directly imports:
  - `docling_upload_service`
  - `upload_filing_events`
  - `upload_material_events`
  - `upload_company_meta`
  - `upload_progress_helpers`
  - SEC downloader / storage protocols / ticker normalization
- OLD `sec_pipeline.py` directly imports `sec_upload_workflow`, `DoclingUploadService`, upload event modules, and upload company-meta helpers for upload facade methods.
- OLD `cn_pipeline.py` directly imports `DoclingUploadService`, `build_cn_filing_ids`, `build_material_ids`, `derive_report_kind`, `normalize_cn_fiscal_period`, upload event modules, upload progress helpers, and upload company-meta helpers for CN/HK upload facade methods.
- OLD `cn_pipeline.py` upload methods do not reject HK market; they use the same CN/HK facade after ticker normalization. Therefore this Slice keeps HK upload supported through the migrated CN/HK facade instead of inventing an unsupported branch.

Migrated modules are limited to the direct upload dependency chain above. Process, rebuild, CLI, provider, and tool modules were not migrated.

## What Changed

- Added migrated upload support modules:
  - `dayu/fins/pipelines/docling_upload_service.py`
  - `dayu/fins/pipelines/sec_upload_workflow.py`
  - `dayu/fins/pipelines/upload_company_meta.py`
  - `dayu/fins/pipelines/upload_filing_events.py`
  - `dayu/fins/pipelines/upload_material_events.py`
  - `dayu/fins/pipelines/upload_progress_helpers.py`
- Extended `SecPipeline` with narrow upload facade methods:
  - `upload_filing`
  - `upload_filing_stream`
  - `upload_material`
  - `upload_material_stream`
- Extended `CnPipeline` with the same CN/HK upload facade methods.
- Added `ProductionFinsUploadRunner` in `dayu/fins/service_runtime.py`:
  - US filing/material requests route to SEC upload workflow.
  - CN/HK filing/material requests route to CN/HK upload facade.
  - The runner maps pipeline results into `FinsUploadResultSummary`.
- Registered the production upload runner in `DefaultFinsRuntime.get_ingestion_runtime()`.
- Added `overwrite` to `FinsUploadFilingRequest` and `FinsUploadMaterialRequest`, and persisted it in upload request summary.
- Updated README facts in `dayu/fins/README.md` and `tests/README.md`.

## Invariants

- OLD upload action semantics are preserved:
  - `auto` resolves to create/update based on existing source meta.
  - `delete` does not require files.
  - same source fingerprint without overwrite maps to skipped.
  - overwrite resets the current source document before replacement.
- OLD ID semantics are preserved:
  - SEC filing IDs use `fil_sec_...`.
  - CN/HK filing IDs use `fil_cn_...`.
  - material IDs use stable `mat_...`.
- File/blob/source writes go through `SourceDocumentRepositoryProtocol` and `DocumentBlobRepositoryProtocol`.
- Ticker routing uses `dayu.fins.ticker_normalization.normalize_ticker`.
- `FinsIngestionRuntime` remains lifecycle-only; upload business rules live behind `FinsUploadRunner` and pipeline/upload service boundaries.
- Cooperative cancellation is passed from runtime runner into upload workflow/service checkpoints. In-flight Docling is not physically interrupted, matching the Slice non-goal.
- HK upload is not invented: OLD CN pipeline upload facade provides direct evidence for the shared CN/HK path.

## Tests Added / Updated

- Added:
  - `tests/fins/test_docling_upload_service.py`
  - `tests/fins/test_docling_upload_service_integration.py`
  - `tests/fins/test_sec_pipeline_upload_filing_stream.py`
  - `tests/fins/test_sec_pipeline_upload_material_stream.py`
- Updated:
  - `tests/fins/test_cn_pipeline.py` with CN upload filing/material coverage.
  - `tests/fins/test_fins_ingestion_runtime.py` with DefaultFinsRuntime production SEC/CN upload job coverage.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `58 passed, 1 skipped, 3 warnings`
  - Skipped test: real Docling upload integration requires `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`.
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright reported only a newer version notice.
- `git diff --check`
  - Result: passed.
- Targeted type scan over touched production/test files:
  - `rg -n "\bAny\b|\bobject\b" ...`
  - Result: no matches.
- Boundary scan over touched production files:
  - scanned for Host/Engine/UI/CLI/tool/provider imports and upload provider/tool symbols.
  - Result: no matches.

## README Decision

- `dayu/fins/README.md` updated because `DefaultFinsRuntime` now has a production upload runner instead of only unsupported upload runtime.
- `tests/README.md` updated because new Fins upload service/pipeline/runtime test coverage landed.

## Residual Risks / Blockers

- No blocker.
- Crash recovery for daemon-thread upload jobs and partial artifacts remains tracked by existing Issue 129 / WAIT follow-ups, as classified by the accepted plan.
- Upload tool/provider/wait adapter and upload path allowlist validation remain covered by later Slice 5.
- Real Docling integration remains opt-in to avoid making default CI depend on heavyweight third-party runtime behavior.
