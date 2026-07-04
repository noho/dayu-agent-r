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
| Poller-disabled deployments do not execute external lifecycle adapter actions | merged-into-WU-WAIT-04 | Current Host support is intentionally behind production wait poller configuration. This is not a separate residual-risk item because WU-WAIT-04 is already the dependent production-grade awaiting E2E smoke that must validate Service / composition behavior after #89 / #90 / #92. |
| Tool/provider operations observe cancellation only at checkpoints | classified-as-separate-follow-up-WU | Python cannot forcibly stop arbitrary provider blocking I/O safely. This is a cross-tool provider/runtime hardening topic, not a Fins-only #92 residual. The ordered follow-up lane handles Host-level timeout semantics in `WU-LIFE-03`, then tool/provider interruptible execution boundary and escalation in `WU-TOOLS-CANCEL-01`, before WU-WAIT-04 production smoke. The intended user-visible outcome is immediate-cancel behavior: Host returns to an interactive state quickly and stale tool/provider results cannot pollute the cancelled Run. |
| Future provider adapters using `CANCEL` or `REVOKE` may need action-level durable diagnostics | closed-as-future-guardrail | No current adapter returns `CANCEL` or `REVOKE`; Fins currently returns `ABANDON`. This is a future design guardrail, not a present residual risk. |
| GitHub PR checks are not configured for branch `phase/wu-wait-03-issue-92` | closed-as-repo-infra-note | This matches the repository's current draft PR pattern and is not a WU-WAIT-03 product/runtime residual. Local validation remains the gate evidence. |

## Total-control Updates

- Removed `WU-TOOLS-01-F01-02-R2` from the active residual-risk table because WU-WAIT-03 consumed and closed that transferred item by defining the external lifecycle adapter contract and implementing Fins best-effort ABANDON cleanup.
- Merged the would-be `WU-WAIT-03-R1` production poller composition validation into the existing WU-WAIT-04 work unit instead of keeping a duplicate residual-risk row.
- Added follow-up work unit `WU-TOOLS-CANCEL-01` for cross-tool provider/runtime stronger-than-cooperative interruption after WU-LIFE-03; this is not recorded as a WU-WAIT-03 residual risk.

## Result

After this reconciliation, no WU-WAIT-03 residual risk remains unclassified or active. The production poller composition validation is tracked by WU-WAIT-04 itself, not by a duplicate residual-risk row. Stronger-than-cooperative interruption for blocking tool/provider runtime calls is tracked as ordered follow-up work after WU-LIFE-03, not as a WU-WAIT-03 remainder.
