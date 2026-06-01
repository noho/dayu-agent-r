# WU-DUR-01-02 Slice 2 Code Review Controller Adjudication

## Gate

- Gate: code review controller adjudication
- Work unit: WU-DUR-01 + WU-DUR-02
- Slice: Slice 2 - Internal WAL Maintenance Primitive And Read-stale Proof
- Implementation artifact: `docs/reviews/wu-dur-01-02-implementation-slice2-codex-20260601.md`
- Reviews:
  - `docs/reviews/wu-dur-01-02-code-review-slice2-mimo-20260601.md`
  - `docs/reviews/wu-dur-01-02-code-review-slice2-ds-20260601.md`

## Controller Decision Summary

Slice 2 implementation direction is accepted. MiMo found no issue. DS found two low-severity diagnostic-message precision issues. Both are accepted because this slice's explicit purpose includes WAL maintenance diagnostics, and the fix is a narrow string-level improvement that does not alter public API, control flow, transaction semantics, or checkpoint correctness boundaries.

## Finding Decisions

### DS-C2-A - accepted

Decision: Accepted.

Reason: A WAL file stat failure after a successful checkpoint is operationally different from checkpoint PRAGMA failure. Keeping the same error message weakens the diagnostic value this slice is adding.

Required fix: Use a distinct `HostDurableError` message for WAL file size stat failure, such as `Host durable WAL checkpoint failed to read WAL file size`.

### DS-C2-B - accepted

Decision: Accepted.

Reason: A malformed checkpoint row is not the same as no row. Since this is defensive diagnostic code, the error should describe the actual failure boundary.

Required fix: Use a distinct `HostDurableError` message for unexpected checkpoint result shape, such as `Host durable WAL checkpoint returned unexpected result shape`.

## Deferred / Rejected Items

- TRUNCATE basic coverage is deferred. The current plan required PASSIVE diagnostic observability and failure behavior; adding TRUNCATE coverage is not necessary to close the current risk signal.
- Shared EventLog test helper extraction is rejected for this slice. The duplicated helpers are local test fixtures and extracting them now would introduce unnecessary cross-test coupling.
- Adding actual Python type names to `_checkpoint_int` failures is deferred as nonessential defensive diagnostic polish.

## Next Gate

Fix required for DS-C2-A and DS-C2-B, then focused re-review by MiMo and DS.

## Stop Status

adjudication-complete
