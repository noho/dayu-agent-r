# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Code Review Controller Adjudication

## Scope

- Batch: C2 - Host dispatch / promotion / cancellation / tool accept lifecycle owner.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-controller-validation.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-ds.md`

## Accepted Review Findings

- `DS-C2-01`: accepted. The defensive check inside `request_active_attempt_cancel_in_transaction` is unreachable after `_dispatch_record_has_worker_accept_fact(...)` already proved the same facts. Keeping it would preserve dead code in a state-machine path.
- `DS-C2-02`: accepted. `_cancelled_eof_candidate` still populates `RunCancelledData.requested_at` from token propagation time while the ingest owner later repairs it from committed `CANCEL_REQUESTED`. Even though durable output is correct, producer-side wrong semantics should be removed.

## Rejected Or Deferred Findings

- None.

## Controller Decision

Batch C2 requires a low-risk review-fix gate before acceptance.

## Required Fix Scope

- Remove the unreachable defensive check or replace it with a type-narrowing pattern that does not imply a reachable runtime branch.
- Ensure the synthetic cancelled EOF candidate does not carry token propagation time as business `requested_at`. The candidate should either receive the canonical committed cancel request time or make the value explicitly non-authoritative in a way that no downstream consumer can mistake for the business fact.

