# WU-WAIT-02 Plan Review Controller Adjudication

## Scope

- Work unit: `WU-WAIT-02`
- Gate: `plan review`
- Plan artifact: `docs/host/wu-wait-02-production-poller-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260701-135815.md` by AgentDS
  - `docs/reviews/plan-review-20260701-140124.md` by AgentMiMo

## Decision

Plan review result is `pass-with-risks`. The plan is structurally aligned with Host / Engine design boundaries and the 3-slice split is accepted. A plan-fix gate is required before plan re-review because both reviewers found actionable specification gaps in the durable claim / close lifecycle semantics.

## Finding Adjudication

| Finding | Source | Severity | Controller decision | Required plan-fix action |
|---|---:|---:|---|---|
| Terminal resolve must explicitly clear poll claim fields | AgentDS F01 | High | accepted | Add Slice 1 exact implementation step to update `_mark_wait_record_terminal_row` or equivalent terminal wait mutation so `poll_claim_id`, `poll_claim_owner_id`, `poll_claimed_at`, and `poll_claim_expires_at` are cleared on resolved / failed / lost terminal transitions; add the test assertion. |
| Claim acquisition atomicity / read-then-claim race underspecified | AgentMiMo F01, AgentDS F02 | Medium | accepted | Specify atomic claim acquisition as `UPDATE ... WHERE` / equivalent statement where eligibility and claim set are in the same write operation, and define CAS rowcount 0 as claim conflict: skip adapter call, increment diagnostics, do not release a claim that was never acquired. |
| Missing adapter indefinite retry lacks explicit policy | AgentDS F03 | Medium | accepted | Plan-fix must choose an explicit current-WU policy. It may add a bounded terminal policy, or deliberately keep capped-delay indefinite retry to avoid false terminalization, but must record diagnostics, operator visibility, and residual owner / destination if not terminalizing. |
| Claim batch size semantics unclear | AgentMiMo F02 | Low | accepted | Clarify batch claim semantics: either single-row claim repeated up to limit, or per-row isolated CAS attempts within a batch; avoid all-or-nothing ambiguity. |
| Close drain timeout behavior unclear | AgentMiMo F03 | Low | accepted | Clarify what `close()` does after `close_drain_timeout_seconds` fires, and how durable store close is prevented while a background task / thread can still touch the store. |
| Backoff attempts drift on claim takeover | AgentDS F04 | Low | accepted | Document the tradeoff: per-wait backoff is shared across poller instances, may reach max delay faster after repeated crash/takeover, and this is bounded / intentional unless plan chooses a reset rule. |
| Abandon CAS race after status change unclear | AgentDS F05 | Low | accepted | Specify abandon CAS rowcount 0 behavior: treat as skipped / conflict, do not assume abandon success, and rely on a later eligible round if the wait is still cancelled. |

## Accepted Plan Shape

- Claim/backoff on the wait record remains accepted as the preferred design over a separate claim table or runtime-only state.
- The three implementation slices remain accepted:
  1. Durable poll claim and backoff primitive.
  2. Backoff-aware poller supervisor and lifecycle.
  3. `open_host` integration, public construction wiring, docs, and final validation.
- No review finding requires expanding this work unit into Engine changes, UI event iteration, physical cancel / revoke / abandon, or generic lease / Attempt takeover.

## Residual Risks

All residual risks must remain classified after plan-fix:

- Sync adapter calls cannot be forcibly killed by Python: owner `WU-WAIT-02 Slice 2`, destination lifecycle tests and adapter bounded-call documentation.
- Full external job revoke / cancel remains out of scope: owner `WU-WAIT-03 / GitHub Issue #92`.
- UI / Service production-grade awaiting E2E smoke remains out of scope: owner `WU-WAIT-04`.
- Missing adapter repeated retry must have explicit current-WU policy and, if not terminalized, residual owner / destination.

## Next Gate

Proceed to plan-fix gate with AgentCodex. The fix must edit only `docs/host/wu-wait-02-production-poller-plan.md` unless it discovers a blocking design-source mismatch and reports back.
