# WU-SEMANTIC-OWNERSHIP-01 P3-F S2 Code Review Controller Adjudication

## Scope

- Slice: `P3-F S2 - Blob acknowledgement and explicit staging source contract`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s2-code-review-ds.md`

## Verdict

Fix gate required before S2 acceptance.

## Accepted Findings

### P3-F-S2-CR-F01 - Remove overwritten SEC `source_handle` assignment

- Source: DS finding 1; MiMo residual note.
- Severity: Low.
- Decision: accepted.
- Reasoning: `run_download_single_filing_stream(...)` constructs a `SourceHandle` and then immediately overwrites it with `stage_downloaded_filing_source_document(...)`. The first assignment is dead code. It does not affect runtime correctness because both handles have the same identity, but it obscures the S2 owner boundary: the valid pre-blob handle should visibly come from source repository acknowledgement or an already completed source meta branch.
- Required fix:
  - Remove the dead `SourceHandle(...)` assignment in `dayu/fins/pipelines/sec_download_filing_workflow.py`.
  - Do not change staging behavior or test expectations.
  - Re-run focused SEC/storage/upload tests, pyright, and `git diff --check`.

## Rejected Findings

None.

## Accepted-Pass Notes

Both reviewers confirmed the material S2 owner boundary is correct:

- Blob repository refuses ownerless `SourceHandle` writes before bytes are written.
- Upload and SEC stream/legacy paths stage before blob writes.
- Completion preserves staging stable facts.
- CN workflow did not regress.
- No downstream/read-runtime special casing was added.
