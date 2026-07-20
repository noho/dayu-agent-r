# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Re-Review Controller Adjudication

## Scope

- Batch: C2 - Host dispatch / promotion / cancellation / tool accept lifecycle owner.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-implementation-codex.md`
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-controller-adjudication.md`
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-codex.md`
- Review-fix validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-rereview-ds.md`

## Re-Review Result

Both re-reviewers reported `0` findings.

Accepted review findings closed:

- `DS-C2-01`: closed. The unreachable defensive branch was removed; worker accept evidence now narrows through `_dispatch_record_worker_accepted_at(...) -> str | None`.
- `DS-C2-02`: closed. Synthetic cancelled EOF candidates now derive `requested_at` from committed `CANCEL_REQUESTED.occurred_at`; token propagation time is no longer written into the business field.

## Controller Decision

Batch C2 is accepted and ready for accepted slice commit.

## Residual Risk

- If a CANCELLING Run lacks a committed `CANCEL_REQUESTED` link, dispatch producer now avoids synthesizing a wrong cancel candidate. That abnormal durable-state gap remains outside the normal cancel path.
- Two non-C2 compaction / memory projection test failures remain assigned to Batch D / non-C2 follow-up.
- Batch D/E remain untouched.

