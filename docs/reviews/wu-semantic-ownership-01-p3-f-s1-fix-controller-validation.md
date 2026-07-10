# WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Fix Controller Validation

## Scope

- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-controller-adjudication.md`
- Accepted findings:
  - `P3-F-S1-CR-F01` duplicate citation meta reads / cache regression
  - `P3-F-S1-CR-F02` fail-closed `ingest_complete` handling and incomplete citation projection
  - `P3-F-S1-CR-F03` staging stable-field conflict semantics

## Validation Result

Controller accepts the fix as ready for independent re-review.

## Evidence

- `SourceDocumentProvenance.from_meta(...)` now requires `meta["ingest_complete"]`; missing values fail closed.
- `FinsReadRuntime._build_citation(...)` resolves `source_kind`, reads source meta through `_get_source_meta_cached_by_kind(...)`, passes that same meta into repository provenance parsing, and rejects `provenance.ingest_complete is False`.
- `get_source_document_provenance(...)` keeps provenance parsing under the source repository contract and only accepts the optional `meta` parameter to avoid duplicate reads.
- `_STAGING_STABLE_META_FIELDS` no longer duplicates `internal_document_id`; `_staging_stable_fields_match(...)` now compares stable field value presence and value symmetrically while treating empty string as absent.
- Tests now cover:
  - provider-owned provenance projection
  - missing provider / invalid provider / missing `ingest_complete`
  - incomplete source meta refusing citation projection
  - repeated staging conflict when a previous stable field is omitted
  - single cached source meta read for repeated citation construction

## Commands Run

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py tests/fins/test_docling_upload_service.py -q`
  - Result: `79 passed, 3 warnings in 7.63s`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed with no output.
- `rg -n "startswith\\(\\\"fil_\\\"\\)|startswith\\('fil_'\\)" dayu/fins/tools dayu/fins/pipelines`
  - Result: only `dayu/fins/pipelines/sec_rebuild_workflow.py:253`, classified as SEC accession reconstruction, not source classification.
- `rg -n "def _build_citation|_build_citation\\(" dayu/fins/tools/read_runtime.py`
  - Result: one helper definition and all citation call sites route through `_build_citation(...)`.

## Propagation Audit

1. Producer truth remains in source meta written by SEC / CN / upload pipelines.
2. Repository provenance remains the validation owner for `source_provider`, `ingest_method`, and `ingest_complete`.
3. Citation projection derives LLM-facing source type/provider from repository provenance, not `document_id` prefix or local read-runtime guessing.
4. Incomplete staging meta is blocked before citation serialization and cannot enter LLM-facing read/list/search output through `_build_citation(...)`.

## Residual Risk

- S2 still owns blob acknowledgement enforcement and production workflow sequencing around `stage_source_document(...)`.
- Coverage measurement remains unavailable because the local pytest-cov/numpy-pandas collection issue is still outside this fix; ordinary pytest and pyright passed.
