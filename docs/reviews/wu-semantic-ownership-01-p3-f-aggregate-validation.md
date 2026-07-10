# WU-SEMANTIC-OWNERSHIP-01 P3-F Aggregate Validation

## Scope

- Work unit: `P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership`
- Accepted slice commits:
  - S1 source repository provenance and citation projection: `42ea9c21`
  - S2 blob acknowledgement and explicit staging source contract: `3b2779e4`
  - S3 Fins wait adapter deadline/expiry consumption: `edf303a4`
  - S4 company metadata freshness semantics: `22683a8e`

## Result

P3-F is ready for aggregate deepreview.

## Commands Run

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q`
  - Result: `256 passed, 3 warnings in 11.29s`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed with no output.
- `source .venv/bin/activate && rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests`
  - Result: zero matches; `rg` exit code `1`.
- `rg -n "startswith\\(\\\"fil_\\\"\\)|startswith\\('fil_'\\)" dayu/fins/tools dayu/fins/pipelines`
  - Result: only `dayu/fins/pipelines/sec_rebuild_workflow.py:253`, classified as SEC accession reconstruction, not citation/provenance classification.
- `rg -n "stage_source_document\\(|get_source_document_provenance\\(|_existing_company_meta_is_fresh|_wait_boundary_lost\\(" dayu/fins tests/fins`
  - Result: owner-boundary helpers and tests only.

## Propagation Audit

1. Source provenance:
   - Producers persist `source_provider`, `ingest_method`, and explicit `ingest_complete`.
   - Source repository validates provenance through `SourceDocumentProvenance`.
   - Citation projection derives LLM-facing provider/type from repository provenance and rejects incomplete source documents.
2. Blob acknowledgement:
   - Source repository owns completed/staging acknowledgement.
   - Blob repository refuses `SourceHandle` writes without source meta.
   - Upload and SEC paths stage before blob writes.
3. Wait timeout:
   - Host wait record owns `deadline_at` / `expires_at`.
   - Fins adapter consumes those fields using Host callback precedence and no longer uses `created_at` age.
4. Company metadata freshness:
   - Upload freshness is owned by `upload_company_meta.py` and uses `RESOLVER_VERSION`.
   - `updated_at` remains audit time; read runtime does not refresh or infer freshness.

## Residual Risks

- Multi-process TOCTOU between source-meta check and blob write remains accepted by the P3-F plan.
- No-boundary transient unavailable remains not-ready until Host cancellation/close or future Host-owned boundary.
- Coverage percentage remains unmeasured because local pytest-cov collection is blocked by the existing numpy/pandas issue; focused behavioral tests and pyright passed.
