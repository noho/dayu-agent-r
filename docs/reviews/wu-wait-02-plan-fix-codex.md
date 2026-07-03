# WU-WAIT-02 Plan Fix Report

## Scope

- Gate: `plan-fix`
- Work unit: `WU-WAIT-02 / GitHub issue-90`
- Plan artifact fixed: `docs/host/wu-wait-02-production-poller-plan.md`
- Review inputs:
  - `docs/reviews/plan-review-20260701-135815.md`
  - `docs/reviews/plan-review-20260701-140124.md`
  - `docs/reviews/wu-wait-02-plan-review-controller-adjudication.md`

## Changed Plan Sections

- `Durable State Helpers`: added atomic claim acquisition invariant.
- `Poll Loop Lifecycle / Close drain`: clarified timeout behavior and durable-store close safety.
- `Backoff Policy`: documented shared per-wait backoff tradeoff and missing-adapter retry policy.
- `Slice 1 / Exact changes`: added atomic claim acquisition, claim conflict behavior, batch semantics, and terminal claim-field clearing step.
- `Slice 1 / Data flow / state transitions`: replaced read-then-claim wording with atomic claim write flow.
- `Slice 1 / Error handling`: added claim-acquisition conflict and abandon-CAS conflict behavior.
- `Slice 1 / Tests`: added explicit claim-field clearing, claim-conflict, missing-adapter, and abandon-CAS assertions.
- `Slice 2 / Error handling` and `Slice 2 / Tests`: clarified close drain timeout behavior and coverage.
- `Residual Risks`: added missing-adapter indefinite retry and shared per-wait backoff drift risks.

## Finding Resolution Map

| Accepted finding | Status | Plan-fix action |
|---|---|---|
| Terminal resolve must explicitly clear poll claim fields | fixed | Slice 1 now requires updating `_mark_wait_record_terminal_row` or equivalent terminal mutation to clear `poll_claim_id`, `poll_claim_owner_id`, `poll_claimed_at`, and `poll_claim_expires_at` on resolved / failed / lost transitions. Tests now assert those four fields are cleared. |
| Claim acquisition atomicity / read-then-claim race underspecified | fixed | Plan now requires an atomic `UPDATE ... WHERE` / equivalent write where eligibility and claim-field assignment happen in the same statement. `rowcount == 0` / no returned row is defined as claim conflict: skip adapter call, increment diagnostics, continue, and do not release an unacquired claim. |
| Missing adapter indefinite retry lacks explicit policy | fixed | Current-WU policy is capped-delay indefinite retry, not terminalization, to avoid false terminalizing temporary deployment/configuration gaps. Plan now requires wait-row last outcome/error metadata plus runtime diagnostics/operator visibility, and records residual owner/destination. |
| Claim batch size semantics unclear | fixed | Plan now defines `claim_batch_size` as repeated single-row claim attempts up to `limit`, or per-row isolated CAS attempts inside one write transaction. Successful row claims are returned independently; the batch is not all-or-nothing. |
| Close drain timeout behavior unclear | fixed | Plan now states the timeout is an operator-visibility threshold. `close()` logs/records the timeout, keeps waiting, and must not return while a poll task/thread can still touch the durable store; `open_host` can close the durable store only after `poller.close()` returns. |
| Backoff attempts drift on claim takeover | fixed | Plan now documents shared per-wait backoff across poller instances, the crash/takeover drift tradeoff, and why it is bounded by `backoff_max_delay_seconds` and intentional. |
| Abandon CAS race after status change unclear | fixed | Plan now defines abandon CAS `rowcount == 0` as skipped/conflict: do not assume abandon success, do not mark `poll_abandoned_at`, and rely on a later eligible round if the wait is still cancelled. |

## Validation

Command run:

```bash
git diff --check -- docs/host/wu-wait-02-production-poller-plan.md docs/reviews/wu-wait-02-plan-fix-codex.md
```

Result: passed with no output.

## Residual Risks After Fix

- Missing adapter still retries indefinitely with capped delay in this WU. Owner: WU-WAIT-02 Slice 1 for diagnostics; future owner WU-WAIT-03 or provider lifecycle work if terminal provider-failure policy is needed.
- Close drain timeout does not forcibly kill synchronous adapter code. Owner: WU-WAIT-02 Slice 2; safety choice is to keep durable store open and wait until the poll path stops.
- Shared per-wait backoff may reach max delay faster after repeated crash / claim-expiry / takeover cycles. Owner: WU-WAIT-02 Slice 1; bounded by `backoff_max_delay_seconds`.
- Full external job revoke/cancel remains out of scope for WU-WAIT-03.
- UI / Service production-grade awaiting E2E smoke remains out of scope for WU-WAIT-04.

## Blocking Open Questions

None.

## Stop Conditions

No stop condition was hit. No accepted finding required changing Host design source before the plan text could be fixed.
