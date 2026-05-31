# Phase 15 P15-S3 Code Review Controller Adjudication

- **Gate**: Phase 15 S3 code review adjudication
- **Date**: 2026-05-29
- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- **Implementation artifact**: `docs/reviews/phase15-s3-implementation-codex-20260529.md`
- **Review artifacts**:
  - `docs/reviews/phase15-s3-code-review-mimo-20260529.md`
  - `docs/reviews/phase15-s3-code-review-ds-20260529.md`

## Scope Decision

P15-S3 scope is limited to wiring `purge_session` through the public command path and proving read-after-purge fail-closed behavior. It must not add audit JSONL writing, new public error codes, new public readers, new `OpenHostOptions` fields, or Engine / Service / UI / Fins changes.

Both reviews confirm the implementation stays within this scope:

- `dayu.host.command.purge_session(...)` now checks the closed handle first, builds a stable semantic digest from request/path context, calls the S2 durable purge helper in a write transaction, and maps durable errors to existing `HostApiErrorCode` values.
- `dayu.host.open_host._PublicHostHandle.purge_session(...)` forwards to the command facade without changing `OpenHostOptions`.
- Tests cover closed empty Session purge and replay, open Session rejection, read/retry/replay/watch after purge returning existing fail-closed errors, and closed-handle behavior.

## Findings Adjudication

| Finding | Decision | Reason |
| --- | --- | --- |
| MiMo review PASS / 0 findings | Accepted | No blocking or non-blocking code issue identified. |
| DS Finding 1: `HostIdempotencyConflictError` mapped through generic durable fallback | Accepted as non-issue | The mapping reaches existing `IDEMPOTENCY_CONFLICT` and matches existing command error mapping convention. No S3 change required. |
| DS Finding 2: `read_api.py` unchanged and relies on row deletion | Accepted as intended design | Read API must not reconstruct from tombstone/projection/audit. Natural missing-row `NOT_FOUND` is the correct S3 behavior. |
| DS Finding 3: tests use local Protocol + cast for concrete opener purge method | Accepted as test-scope compromise | P15-S3 must not reshape the `Host` Protocol. Tests only need to exercise concrete opener wiring. |
| DS Finding 4: S4 audit invariant and fail-before-success risk | Accepted as S4 handoff risk | S3 intentionally passes `audit_record_ref=None`. S4 must close this by appending purge audit JSONL before public success and avoiding an observable audit-pending successful tombstone path. |
| DS Finding 5: context JSON helper return type narrowed | Accepted as non-issue | More precise internal type; pyright confirms no type regression. |

## Controller Decision

No S3 fix pass is required. Proceed to controller local validation and S3 accepted slice commit.

S4 handoff must explicitly include the accepted risk from DS Finding 4: audit append and tombstone write must be organized so `purge_session` cannot return success unless the purge audit JSONL line ref/digest is known and stored with the tombstone. A two-phase audit/write sequence that leaves a successful tombstone without audit evidence is not acceptable for P15 release-blocking scope.
