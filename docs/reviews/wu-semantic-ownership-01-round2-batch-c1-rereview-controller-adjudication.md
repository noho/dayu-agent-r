# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Re-Review Controller Adjudication

## Scope

- Batch: C1 - Host wait expiry / supervisor / claim-release owner.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-implementation-codex.md`
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-controller-adjudication.md`
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-codex.md`
- Review-fix validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-rereview-ds.md`

## Re-Review Result

Both re-reviewers reported `0` findings.

Accepted review findings closed:

- `DS-C1-01`: closed. Host boundary rejection now has durable `BOUNDARY_REJECTED` outcome and `boundary_rejections` counter; `adapter_errors` is not incremented by pre-adapter boundary rejection.
- `C1-REVIEW-01`: closed. Unreachable `WaitCallbackAdapterStatus.STALE_CALLBACK` and Service mapping were removed.
- `DS-C1-02`: closed. Supervisor self-close now uses `_WaitPollerSelfCloseError` typed exception.
- `C1-REVIEW-02` / `DS-C1-03`: closed. Recoverable `round_errors` and fatal supervisor `fatal_errors` are separate diagnostics facts.

## Controller Decision

Batch C1 is accepted and ready for accepted slice commit.

## Residual Risk

- Expired waits still remain `WAITING` with retry/backoff after Host boundary rejection. A terminal expired policy would be a separate Host wait policy work item.
- Abandon `CAS_LOST` when another poller has already claimed the wait is protected by CAS but lacks a dedicated concurrency regression test.
- Batch C2 remains untouched.

