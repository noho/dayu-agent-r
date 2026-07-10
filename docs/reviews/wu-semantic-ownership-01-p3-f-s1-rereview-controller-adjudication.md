# WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Re-review Controller Adjudication

## Scope

- Slice: `P3-F S1 source repository provenance and citation projection`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-rereview-ds.md`

## Verdict

Accepted. P3-F S1 has no remaining accepted code-review finding.

## Finding Closure

| Finding | Controller decision | Re-review result |
| --- | --- | --- |
| `P3-F-S1-CR-F01` duplicate citation meta reads / cache regression | Accepted fix required | Closed by MiMo and DS |
| `P3-F-S1-CR-F02` `ingest_complete` fail-closed and incomplete citation projection | Accepted fix required | Closed by MiMo and DS |
| `P3-F-S1-CR-F03` staging stable-field conflict semantics | Accepted fix required | Closed by MiMo and DS |

Both reviewers returned PASS and found no new material defects.

## Controller Notes

- The optional `meta` parameter on `get_source_document_provenance(...)` is accepted as an owner-boundary preserving optimization: repository provenance parsing remains the validation owner, while read runtime avoids a duplicate source meta read.
- `SourceDocumentProvenance.from_meta(...)` now treats missing `ingest_complete` as a malformed source meta fact rather than silently upgrading it to completed.
- `_build_citation(...)` rejects incomplete source documents before citation serialization, preventing staging source meta from reaching LLM-facing output.
- Staging stable-field matching now has one `internal_document_id` owner and detects omitted stable values when an existing staging meta contains a non-empty value.

## Validation Basis

Controller validation passed:

- `79 passed, 3 warnings` for targeted Fins tests.
- pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.
- source scans for citation routing and `fil_` prefix classification passed with only the known SEC rebuild accession reconstruction match.

## Residual Risk

- S2 still owns blob acknowledgement and workflow sequencing around `stage_source_document(...)`.
- Local coverage measurement remains blocked by the existing pytest-cov / numpy-pandas collection issue; this does not block S1 acceptance because targeted behavior tests and pyright passed.
