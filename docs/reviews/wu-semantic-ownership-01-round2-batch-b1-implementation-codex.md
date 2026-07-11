# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B1 Implementation

## Scope

- Gate: implementation/fix。
- Batch: B1 - Fins path/document identity, HKEX completeness, rebuild_processed effectiveness, atomic JSON。
- Non-goals observed: 未处理 same-ticker batch owner、download/upload overwrite 原子替换、Batch C/D/E；未提交、未 push、未修改 control doc。

## Changed Files

- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_processed_core.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`
- `dayu/fins/README.md`
- `tests/README.md`

## Fixed Findings

- `145711-05`: fixed. Fins storage now owns `_normalize_document_id(...)` and reuses it across source, processed, blob handle, rejected filing artifact, download rejection registry, manifest upsert/remove, and path construction. Invalid `document_id` values containing path separators fail before path traversal, cross-ticker reads, or delete side effects.
- `145711-15`: fixed. HKEX title search now parses rows with a page completeness contract. If an explicit total proves more rows exist, or a full 100-row page lacks a total, `HkexnewsDiscoveryTruncatedError` is raised instead of treating the result as complete.
- `145711-16`: fixed. SEC, CNInfo, and HKEXNews persisted-summary production adapters now consume `rebuild_processed=True` by marking existing processed artifacts for `written_document_ids` as `reprocess_required`, while preserving OLD local `rebuild=False` because that flag means local meta/manifest rebuild.
- `150304-09`: fixed. `_write_json` now uses explicit same-directory `os.replace(temp_path, path)` after fsync, followed by directory fsync.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_runtime.py tests/fins/test_sec_pipeline_download.py tests/fins/test_fins_read_runtime.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `192 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.
- Source scans:
  - `_write_json` no longer uses `Path.replace`; remaining `dayu/fins/storage/local_file_store.py:78` is blob/object store write, not JSON owner.
  - No remaining silent `rebuild_processed` ignore wording in production adapter code.
  - Storage direct document path joins are restricted to normalized document IDs or already-filtered child names.

## README Decision

- Updated `dayu/fins/README.md` because `dayu/fins/` storage and production download adapter stable boundaries changed.
- Updated `tests/README.md` because `tests/fins/` gained owner-level coverage for document ID path validation, HKEX truncation, and production adapter `rebuild_processed` behavior.

## Residual Risk

- HKEX pagination is still not implemented because no stable next-page protocol is present in the current downloader owner. The current behavior fails closed when completeness cannot be proven.
- `dayu/fins/storage/local_file_store.py` still uses `Path.replace` for non-JSON blob/object writes; this is outside `150304-09` atomic JSON scope and outside Batch B1 target.

## Stop Status

Batch B1 implementation/fix complete. Did not start Batch B2/C/D/E.
