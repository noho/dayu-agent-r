# WU-CLI-FINS-OBS-01 S2 Code Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S2-fins-runtime-progress-events`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-s2-implementation-codex.md`
- Review artifacts:
  - AgentMiMo: `docs/reviews/code-review-20260615-190033.md`
  - AgentDS: `docs/reviews/code-review-20260615-190232.md`

## Review Conclusions

- AgentMiMo: `PASS-WITH-FINDINGS`
- AgentDS: `PASS-WITH-FINDINGS`

Both reviewers found no blocking correctness issue in the S2 production behavior. The accepted action item is a test coverage fix for implemented progress branches.

## Accepted Findings

### S2-FIX-01 progress branch test coverage

- Source findings:
  - AgentMiMo finding 1: download/upload `completed_with_failures` progress branches lack direct tests.
  - AgentDS `DS-S2-F01`: download/upload `completed_with_failures` and preprocess `document_failed` / `document_not_supported` progress branches lack direct tests.
- Decision: accepted.
- Required fix:
  - Add focused tests in `tests/fins/test_fins_ingestion_runtime.py` for:
    - `download.completed_with_failures` when a download summary has `failed_count > 0`.
    - `upload.completed_with_failures` when an upload summary has failed status.
    - `preprocess.document_failed` when document preprocessing raises a general exception.
    - `preprocess.document_not_supported` when document preprocessing raises the unsupported branch.
  - Do not change production semantics unless a test reveals a real implementation defect.
- Required validation:
  - `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`

## Deferred / Rejected Findings

### S2-DEFER-01 preprocess completed skipped_count semantics

- Source finding: AgentDS `DS-S2-F02`.
- Decision: deferred with owner to later Service / CLI consumer slice if the consumer needs separate aggregate counters.
- Rationale: `FinsPreprocessResultSummary.skipped_count` already counts unsupported documents as skipped in the job summary. S2 only projects existing summary semantics into observation-only progress. Changing it in this slice would alter production summary semantics beyond the accepted plan.
- Required action now: none.

### S2-DEFER-02 preprocess progress event record snapshot

- Source finding: AgentMiMo finding 2 and AgentDS open question Q2.
- Decision: accepted as non-actionable residual note for future pause/resume or richer cancellation progress work.
- Rationale: current S2 emits progress only for running jobs, so the entry record status and latest running status are equivalent for the emitted events. This matches existing event append patterns and has no current behavior impact.
- Required action now: none.

## Controller Decision

S2 enters fix gate for `S2-FIX-01` only. After AgentCodex applies the focused test fix and validates tests / pyright, run dual re-review scoped to the accepted finding.
