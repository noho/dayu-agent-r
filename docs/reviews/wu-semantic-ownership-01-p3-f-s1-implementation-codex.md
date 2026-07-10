# WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Implementation Report

## Completion State

ready-for-code-review

## Files Changed

- `dayu/fins/domain/document_models.py`
- `dayu/fins/domain/tool_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/README.md`
- `tests/README.md`
- `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_sec_pipeline_download.py`

## Source Finding / Plan Item Coverage

- Added storage-facing `FinsSourceProvider` with `sec_edgar`, `cninfo`, `hkexnews`, and `user_upload`.
- Added `SourceDocumentProvenance` and repository projection method `get_source_document_provenance(...)`.
- Added `stage_source_document(...)` to the source repository protocol and filesystem core/repository as the S1 skeleton contract for later blob acknowledgement slices. S1 does not wire blob write enforcement or SEC/upload staging sequencing.
- SEC download source meta now writes `source_provider=sec_edgar`.
- CN/HK source meta still consumes the existing candidate provider field, but parses it through `FinsSourceProvider` before persistence.
- Docling upload source meta now writes `source_provider=user_upload` centrally.
- `Citation` now supports optional `source_provider`; `to_dict()` omits it only when `None`.
- `SourceType` now includes exact LLM-facing values `SEC_EDGAR`, `CNINFO`, `HKEXNEWS`, `UPLOADED`, and `SUPPLEMENTARY`.
- `FinsReadRuntime._build_citation(...)` now uses `source_kind` only to route repository reads, then derives `source_type` and `source_provider` from repository provenance. It no longer classifies citations from `document_id.startswith("fil_")` or from `ingest_method` alone.

## Owner Boundary and Propagation Audit

- Producer: SEC/CN/HK/upload pipelines write `source_provider` into source meta at source document creation/update time.
- Validator: `SourceDocumentProvenance.from_meta(...)` and `SourceDocumentRepositoryProtocol.get_source_document_provenance(...)` parse and validate `ingest_method`, `source_provider`, `source_kind`, and `ingest_complete`.
- Persistence: filesystem source repository stores the same provider value in source `meta.json`; completed source meta missing or carrying an invalid provider fails closed when provenance is requested.
- Staging contract: source repository owns `stage_source_document(...)` and writes/reuses `ingest_complete=False` source meta with valid provenance fields; blob acknowledgement and workflow sequencing remain deferred to S2.
- Projection: `FinsReadRuntime._build_citation(...)` calls source repository provenance and maps `FinsSourceProvider` to LLM-facing `Citation.source_type` / `Citation.source_provider`.
- LLM-facing output: all read-runtime citation call sites still route through `_build_citation(...)`; `_build_citation` scan shows one helper definition and all citation construction call sites using that helper.

## Tests and Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py`
  - Passed: `71 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py`
  - Passed: `5 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Passed.
- Source scan: `rg -n 'startswith\("fil_"\)|startswith\('\''fil_'\''\)' dayu/fins/tools dayu/fins/pipelines`
  - One remaining match: `dayu/fins/pipelines/sec_rebuild_workflow.py:253`, classified as SEC accession reconstruction during rebuild, not citation/provenance source classification.
- Source scan: `rg -n 'def _build_citation|_build_citation\(' dayu/fins/tools/read_runtime.py`
  - One helper definition and existing citation call sites route through `_build_citation(...)`.
- Fixture scan: completed source meta fixture under `tests/fins/fixtures/aapl_xbrl/.../meta.json` was migrated to include `source_provider=sec_edgar`.
- Coverage attempt:
  - `pytest ... --cov=...` failed during pytest collection with pandas/numpy import error: `ImportError: cannot load module more than once per process`, followed by pandas reporting `Unable to import required dependency numpy`.
  - The same affected tests pass without pytest-cov. No coverage percentage was measured in this environment.

## README Decision

- `dayu/fins/README.md` was updated because `dayu/fins/` public storage/read-runtime semantics changed and the README constraints allow current implemented architecture/contract facts.
- `tests/README.md` was updated because `tests/fins/` coverage now includes source provenance projection and citation provider output.

## Residual Risks / Deferred Items

- S2 still owns blob acknowledgement enforcement and SEC/upload workflow staging-before-blob sequencing.
- The filesystem staging skeleton has a narrow idempotency/conflict check sufficient for the S1 contract handoff, but it is not yet exercised as the blob repository guard.
- Coverage was not measured because pytest-cov triggers a local numpy/pandas import failure during collection; ordinary pytest and pyright validation passed.
