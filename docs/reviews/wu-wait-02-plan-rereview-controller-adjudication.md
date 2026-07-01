# WU-WAIT-02 Plan Re-Review Controller Adjudication

## Scope

- Work unit: `WU-WAIT-02`
- Gate: `plan re-review`
- Plan artifact: `docs/host/wu-wait-02-production-poller-plan.md`
- Plan-fix artifact: `docs/reviews/wu-wait-02-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/plan-review-20260701-141039.md` by AgentDS
  - `docs/reviews/plan-review-20260701-141200.md` by AgentMiMo

## Decision

Plan re-review passes. Both reviewers verified all seven controller-accepted findings as fixed and reported no new material blockers or blocking open questions.

## Finding Final Status

| Accepted finding | Final status | Evidence |
|---|---|---|
| Terminal resolve must explicitly clear poll claim fields | fixed | Plan now requires updating `_mark_wait_record_terminal_row` or equivalent terminal wait mutation and adds explicit test assertions. |
| Claim acquisition atomicity / read-then-claim race underspecified | fixed | Plan now requires atomic `UPDATE ... WHERE` / equivalent claim write and defines rowcount 0 as claim conflict. |
| Missing adapter indefinite retry lacks explicit policy | fixed | Plan chooses capped-delay indefinite retry for this work unit, requires diagnostics/operator visibility, and records owner/destination. |
| Claim batch size semantics unclear | fixed | Plan defines independent per-row claim attempts and rejects all-or-nothing batch ambiguity. |
| Close drain timeout behavior unclear | fixed | Plan defines timeout as operator-visibility threshold and states `close()` must not return while the poller can touch the durable store. |
| Backoff attempts drift on claim takeover | fixed | Plan documents shared per-wait backoff drift as bounded and intentional. |
| Abandon CAS race after status change unclear | fixed | Plan defines abandon CAS rowcount 0 as skipped/conflict without false abandon success. |

## Residual Risks

The remaining risks are classified and have owners / destinations:

- Synchronous adapter calls cannot be forcibly killed by Python: owner `WU-WAIT-02 Slice 2`.
- Durable backoff resets require explicit implementation: owner `WU-WAIT-02 Slice 1`.
- Missing adapter uses capped-delay indefinite retry in this work unit: owner `WU-WAIT-02 Slice 1`; future terminal provider-failure policy, if needed, goes to `WU-WAIT-03` or provider lifecycle work.
- Shared per-wait backoff can reach max delay faster after repeated crash / takeover: owner `WU-WAIT-02 Slice 1`.
- Full external job revoke / cancel remains out of scope: owner `WU-WAIT-03 / GitHub Issue #92`.
- UI / Service production-grade awaiting E2E smoke remains out of scope: owner `WU-WAIT-04`.

## Next Gate

Proceed to accepted plan commit, then implementation Slice 1.
