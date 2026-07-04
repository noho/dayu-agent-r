# WU-WAIT-03 Residual Risk Reconciliation

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Trigger: final closeout follow-up after user challenged whether residual risks were actually recorded in the total-control table and whether they are genuine current-WU residuals.
- Total-control table: `docs/host/issues-implementation-control.md` / `Residual Risk / 遗留问题追踪`

## Correction

The final closeout wording "remaining risks are recorded" was imprecise. Before this reconciliation, the items were recorded in the PR body, Issue comment, and final closeout artifact, but not in the total-control residual-risk table. The total-control document explicitly says residual risks must not remain only in review artifacts, implementation reports, or GitHub comments, so this needed correction.

## Decisions

| Item | Decision | Rationale |
|---|---|---|
| Provider lifecycle cleanup remains best-effort and provider-specific | closed-as-design-constraint | GitHub Issue #92 explicitly says not every provider must support physical cancel, and Host cancellation correctness must not depend on external cancel success. WU-WAIT-03 implemented typed `Applied` / `Unsupported` / `Noop` outcomes and Fins best-effort ABANDON cleanup. This is not an unresolved current-WU risk. |
| Poller-disabled deployments do not execute external lifecycle adapter actions | deferred-with-owner | Current Host support is intentionally behind production wait poller configuration. WU-WAIT-04 is the dependent production-grade awaiting E2E smoke that must validate Service / composition behavior after #89 / #90 / #92. |
| Running Fins operations observe cancellation only at checkpoints | deferred-with-owner | Python cannot forcibly stop arbitrary provider blocking I/O safely. Current WU implemented cooperative cancel observation and artifact preservation. Stronger provider-specific preemption belongs to Fins provider/runtime owners if operational evidence requires it. |
| Future provider adapters using `CANCEL` or `REVOKE` may need action-level durable diagnostics | closed-as-future-guardrail | No current adapter returns `CANCEL` or `REVOKE`; Fins currently returns `ABANDON`. This is a future design guardrail, not a present residual risk. |
| GitHub PR checks are not configured for branch `phase/wu-wait-03-issue-92` | closed-as-repo-infra-note | This matches the repository's current draft PR pattern and is not a WU-WAIT-03 product/runtime residual. Local validation remains the gate evidence. |

## Total-control Updates

- Removed `WU-TOOLS-01-F01-02-R2` from the active residual-risk table because WU-WAIT-03 consumed and closed that transferred item by defining the external lifecycle adapter contract and implementing Fins best-effort ABANDON cleanup.
- Added `WU-WAIT-03-R1` for production poller composition validation, deferred to WU-WAIT-04.
- Added `WU-WAIT-03-R2` for Fins provider/runtime stronger-than-cooperative cancellation if operational evidence requires it.

## Result

After this reconciliation, no WU-WAIT-03 residual risk remains unclassified. Active residual risks that genuinely remain after the current WU are present in the total-control table with stable IDs, status, owners, and next actions.
