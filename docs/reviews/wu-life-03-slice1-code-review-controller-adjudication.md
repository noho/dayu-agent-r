# WU-LIFE-03 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: WU-LIFE-03 Active cancel watchdog and post-cancel timeout
- Gate: Slice 1 code review
- Implementation artifact: `docs/reviews/wu-life-03-slice1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/code-review-20260704-112548.md`
  - `docs/reviews/code-review-20260704-112608.md`

## Overall Decision

Slice 1 code review does not pass yet. The implementation is directionally correct and validation passed, but accepted findings require a focused fix before re-review.

## Finding Adjudication

### S1-CR-F01: duplicated `RUN_CANCELLING` cancel request parser

- Sources:
  - `docs/reviews/code-review-20260704-112548.md` Finding 01.
  - `docs/reviews/code-review-20260704-112608.md` Finding 01.
- Decision: accepted.
- Reason: Both reviewers cite direct duplicate logic between `engine_ingest.py` and `run_transition.py`. Project constraints require repeated logic to be extracted when it carries the same semantic contract. The extra `parse_utc_timestamp` call in the new helper also creates a behavior difference and unclear intent.
- Required fix:
  - Consolidate the parser into one implementation.
  - Keep the helper internal to Host implementation and avoid adding a public export.
  - Make timestamp validation intent explicit if retained, or remove the dead parse call.
  - Ensure cooperative active cancel and timeout closeout paths use the same extraction semantics.

### S1-CR-F02: `cancel_requested_at` format consistency

- Source: `docs/reviews/code-review-20260704-112608.md` Finding 02.
- Decision: accepted.
- Reason: Timeout payload should not rely on raw database string format when adjacent timestamp fields are normalized through `format_utc_timestamp`.
- Required fix:
  - Normalize `cancel_requested_at` through `parse_utc_timestamp` and `format_utc_timestamp`, or otherwise make the existing invariant explicit and tested. Preferred fix is normalization.

### S1-CR-F03: optional diagnostic fields not tested with non-null values

- Source: `docs/reviews/code-review-20260704-112608.md` Finding 03.
- Decision: accepted.
- Reason: The accepted plan requires these fields when available. A non-null test is cheap and prevents payload regression.
- Required fix:
  - Add or extend a test to pass non-null `last_observed_worker_event_index` and `last_accepted_event_id`, then assert both timeout terminal payloads include them.

### S1-CR-F04: malformed `RUN_CANCELLING` payload timeout path lacks direct test

- Source: `docs/reviews/code-review-20260704-112548.md` Finding 02.
- Decision: accepted.
- Reason: The fail-closed path is part of Slice 1's explicit contract. It should be locked by a direct durable transition test.
- Required fix:
  - Add a direct test for malformed or missing `cancel_request_event_id` in `RUN_CANCELLING` payload.
  - Assert `INVALID_STATE` and no `ATTEMPT_CANCELLED` / `RUN_CANCELLED` timeout facts are written.

### S1-CR-F05: timeout self-replay lacks direct test

- Source: `docs/reviews/code-review-20260704-112548.md` Finding 03.
- Decision: accepted.
- Reason: Watchdog retry/replay is a key Slice 2 caller behavior. The Slice 1 helper should prove same-timeout replay is idempotent.
- Required fix:
  - Add a direct timeout self-replay test or extend the happy path to call timeout closeout twice.
  - Assert second call returns the expected idempotent status and writes no duplicate terminal facts.

## Deferred / Residual Items

- Validation helper negative tests for every invalid field are not required in this fix unless needed by the accepted findings. Existing validation helpers and pyright cover the main contract. Owner/destination: future hardening only if implementation churn touches the validation shape.
- Watchdog caller behavior for CAS-lost exceptions remains Slice 2 scope.
- Provider/tool physical interruption remains WU-TOOLS-CANCEL-01.

## Next Gate

Proceed to fix. AgentCodex should make a focused code/test fix and update/create `docs/reviews/wu-life-03-slice1-fix-codex.md`, then run the focused tests, pyright, and `git diff --check`.
