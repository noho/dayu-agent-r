# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Code Review Controller Adjudication

## Scope

- Batch: C1 - Host wait expiry / supervisor / claim-release owner.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-controller-validation.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-ds.md`

## Accepted Review Findings

- `DS-C1-01`: accepted. Boundary rejection is a Host wait-owner decision, not an adapter or resolve error. Durable `poll_last_outcome` and poll counters must expose that owner-level semantic directly.
- `C1-REVIEW-01`: accepted. `WaitCallbackAdapterStatus.STALE_CALLBACK` became unreachable after callback deadline ownership moved to `resolve_wait`; keeping it as a public status would preserve a false contract.
- `DS-C1-02`: accepted. Self-close is a control-flow signal and should use a typed exception rather than string matching.
- `C1-REVIEW-02` / `DS-C1-03`: accepted. Recoverable round errors and fatal supervisor failures are different diagnostics facts and must not share `fatal_errors`.

## Rejected Or Deferred Findings

- None.

## Controller Decision

Batch C1 requires a review-fix gate before acceptance.

## Required Fix Scope

- Add an explicit Host wait boundary-rejection outcome/counter owned by `wait_adapter`.
- Remove unreachable `STALE_CALLBACK` status and update tests/consumers.
- Replace self-close message matching with a typed internal exception.
- Add a recoverable round-error diagnostics field and keep `fatal_errors` for terminal supervisor failure only.

