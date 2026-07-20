# WU-SEMANTIC-OWNERSHIP-01 P3-F S2 Controller Validation

## Scope

- Slice: `P3-F S2 - Blob acknowledgement and explicit staging source contract`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-implementation-codex.md`
- Accepted S1 dependency: `42ea9c21`

## Motivation Check

The S2 motivation remains current. Before this slice, `store_file(SourceHandle, ...)` could write a durable blob based only on handle path data. That permits a blob to exist without source meta acknowledgement, provenance, or membership owner. The correct repair boundary is the source repository plus blob repository write boundary, not read-runtime filtering or downstream tests.

## Controller Result

Ready for independent code review by AgentMiMo and AgentDS.

## Evidence Checked

- `FsDocumentBlobRepository.store_file(SourceHandle, ...)` now calls `_get_handle_meta(handle)` before building the store key or writing bytes.
- Source repository final commit now accepts existing incomplete staging meta as the same source id only when staging stable facts are preserved.
- Upload create path calls source repository staging before first blob write.
- SEC stream and legacy non-stream paths call `stage_downloaded_filing_source_document(...)` before downloader `store_file` callbacks.
- Incomplete source meta continues to be excluded from read-runtime list/citation surfaces.
- CN workflow tests passed without broad rewrite.

## Commands Run

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py -q`
  - Result: `66 passed, 3 warnings in 7.26s`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed with no output.
- Source scans:
  - `stage_downloaded_filing_source_document|stage_source_document|store_file` in Fins storage/pipelines/tests.
  - `def store_file|isinstance(handle, SourceHandle)|_get_handle_meta` in `_fs_blob_core.py`.
  - incomplete source/citation exclusion scan for `ingest_complete=False` and `fil_incomplete`.

## Propagation Audit

1. SEC/upload producers construct source identity and source meta facts.
2. Source repository persists acknowledgement first as `ingest_complete=False` staging meta.
3. Blob repository refuses `SourceHandle` writes when source meta is absent.
4. Final source commit upgrades the same source id to `ingest_complete=True` and full file membership when stable facts match.
5. Read runtime continues to exclude incomplete staging meta from LLM-facing citation output.

## Residual Risk

- Coverage percentage was not measured; focused behavioral tests and pyright passed.
- S3 wait deadline/expiry and S4 company metadata freshness remain outside S2.
