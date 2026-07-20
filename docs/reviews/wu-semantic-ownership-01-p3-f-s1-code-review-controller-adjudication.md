# WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F`
- Slice: `S1 source repository provenance and citation projection`
- Reviewed artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-ds.md`
- Controller decision: fix gate required before S1 can be accepted.

## Motivation Check

The findings are real and correctly scoped. S1 introduced provenance as the source document truth used by citation projection. That means the relevant owner boundary is:

- Producer: SEC / CN / upload pipelines write `source_provider`, `ingest_method`, `ingest_complete`, and source meta.
- Validator / persistence owner: source document repository parses and validates source meta into `SourceDocumentProvenance`.
- Projection owner: `FinsReadRuntime._build_citation` derives LLM-facing citation fields from repository provenance.
- User / LLM visible surface: read/list/search tool citation output.

The fix must stay at repository provenance parsing or citation projection, not at individual downstream tools.

## Accepted Findings

### P3-F-S1-CR-F01 - Remove duplicate source meta reads in citation projection

- Sources:
  - MiMo finding 001
  - DS finding 1
- Severity: Medium
- Decision: accepted.
- Reasoning: `_build_citation` reads the same `meta.json` once via `get_source_meta(...)` and again through `get_source_document_provenance(...)`. It also bypasses the existing runtime `_meta_cache`. Correctness is intact, but S1 regressed the shared citation projection path for all read tools.
- Required fix:
  - Reuse one source meta read per citation construction.
  - Preserve repository-owned provenance parsing; do not recreate provider classification in read runtime.
  - Prefer a typed helper on the provenance model or repository side so `_build_citation` can parse provenance from already-read meta without a second repository read.
  - Keep all citation call sites routed through `_build_citation`.

### P3-F-S1-CR-F02 - Fail closed for missing or incomplete ingest state

- Sources:
  - MiMo finding 002
  - MiMo finding 003
  - DS finding 2
- Severity: Low
- Decision: accepted.
- Reasoning: `ingest_complete` is a source meta truth. Treating a missing value as complete weakens fail-closed behavior, and allowing `ingest_complete=False` through `_build_citation` leaves a downstream projection path that can expose staging documents if an upstream filter regresses.
- Required fix:
  - `SourceDocumentProvenance.from_meta(...)` must require `ingest_complete` explicitly, with a clear failure on missing or non-boolean values.
  - `_build_citation` must refuse `provenance.ingest_complete is False` by raising `FileNotFoundError`.
  - Add regression coverage for incomplete source meta refusing citation projection.

### P3-F-S1-CR-F03 - Tighten staging stable-field conflict semantics

- Sources:
  - MiMo finding 004
  - DS finding 3
- Severity: Low
- Decision: accepted.
- Reasoning: S1 introduced `stage_source_document` and `_staging_stable_fields_match`; S2 will build on this owner boundary. Leaving ambiguous repeated-request matching in the skeleton creates a fragile contract exactly where S2 needs a strong source-document staging invariant.
- Required fix:
  - Remove duplicated `internal_document_id` comparison from the stable field loop or the explicit check; use one source of truth for that field.
  - Do not treat omitted stable fields as proof of a match when the persisted staging meta contains a value for that stable field.
  - Add or update focused repository tests if existing S1/S2 tests do not already cover the conflict behavior.

## Rejected Or Deferred Findings

None. All material MiMo / DS findings are accepted into the S1 fix gate.

## Required Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py tests/fins/test_docling_upload_service.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`
- Source scans:
  - citation call sites still route through `_build_citation`
  - no `document_id.startswith("fil_")` provenance classification in read runtime
  - incomplete source meta cannot project citation

## Propagation Audit Requirement

The fix report must explicitly confirm:

1. Source meta still originates from pipeline / upload producers.
2. Repository provenance parsing is the only validation owner for `source_provider` and `ingest_complete`.
3. Citation derives source type/provider from that provenance truth.
4. Incomplete staging meta is not projected into LLM-facing citation output.
