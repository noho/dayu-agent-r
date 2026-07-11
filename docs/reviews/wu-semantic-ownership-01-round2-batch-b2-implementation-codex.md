# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B2 Implementation

## Scope

- Gate: implementation/fix.
- Batch: B2 - Fins storage overwrite and same-ticker batch ownership.
- Fixed accepted findings: `145711-02`, `145711-03`, `145711-04`.
- Non-goals honored: no HKEX pagination work, no Batch C/D/E work, no large `ingestion_runtime` split, no commit/push/control-doc update.

## Changes

- Added explicit `owner_token` and `owner_scope_id` to `BatchToken`.
- Made filesystem batch staging owner-aware: same ticker active staging can only be read/written/committed/rolled back by the creating owner scope; non-owner task access fails fast.
- Exposed the same storage-core batch operations through `SourceDocumentRepositoryProtocol` and `FsSourceDocumentRepository`, so source/blob replacement flows can use one storage owner boundary.
- Changed runtime document download persistence to wrap reset/create/blob/final meta/reprocess marking in a single source batch.
- Removed SEC/CN ticker-level filings clear from overwrite download paths.
- Changed SEC single-filing download to batch staging, file writes, final meta, and reprocess marking; failed/skipped/cancelled paths rollback the staging.
- Guarded SEC stale cleanup so empty/no-target results do not delete existing filings.
- Changed upload overwrite so SEC/CN facades no longer delete old documents before conversion; `DoclingUploadService` resets and replaces only after new materials are built and cancellation is checked, inside a storage batch.
- Updated Fins and tests README contract descriptions.

## Tests / Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py::test_same_ticker_batch_fails_fast_across_independent_repository_cores tests/fins/test_fins_storage_provider.py::test_same_ticker_active_batch_rejects_non_owner_task_on_shared_core tests/fins/test_fins_ingestion_runtime.py::test_store_downloaded_document_overwrite_failure_rolls_back_target_scope tests/fins/test_docling_upload_service.py::test_execute_upload_overwrite_cancel_after_conversion_keeps_previous_document tests/fins/test_docling_upload_service.py::test_execute_upload_overwrite_final_failure_keeps_previous_document -q` passed.
- `source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q` passed.
- `source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py -q` passed.
- `source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_upload_batch.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py -q` passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` passed with `0 errors`.
- `git diff --check` passed.

## README Decision

- Updated `dayu/fins/README.md` because `dayu/fins/` storage, download, and upload owner contracts changed.
- Updated `tests/README.md` because related Fins tests were added/updated.

## Residual Risk

- No residual risk for `145711-02`, `145711-03`, or `145711-04`.
- HKEX pagination/truncation, production adapter `rebuild_processed` beyond touched paths, portable replacement semantics, and Batch C/D/E findings remain outside Batch B2.

## Stop Status

Batch B2 implementation/fix stops here. No commit, push, PR, or control-doc update was performed.
