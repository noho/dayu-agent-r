# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E - Web And Document Tool Egress, Resource Caps, Diagnostics, And Oracles`
- Gate: plan review adjudication
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-ds.md`

## Review Summary

Both reviewers returned `pass-with-risks` with zero blocking questions. Both reviewers verified that all 10 accepted R3-E findings have direct code evidence and plausible current-scope owners.

Controller accepts the plan architecture direction, but requires plan fixes before implementation. The fixes are concrete plan contract gaps, not optional implementation notes.

## Findings Adjudication

| Controller ID | Source findings | Decision | Required plan correction |
|---|---|---|---|
| R3-E-PF-01 | MiMo-01 | accepted | Fix incorrect design/source references. Replace wrong `docs/host/design.md` line citations with accurate design/code source references or remove line-specific claims that are not in design truth. |
| R3-E-PF-02 | MiMo-02 + DS-02 | accepted | Add a concrete S1 peer-proof implementation strategy for requests/urllib3 2.6.3, including how approved addresses reach the transport, how TLS SNI/cert hostname remains original host, how connect retry behaves, and a validation/test that retry does not re-resolve or leave the approved address set. |
| R3-E-PF-03 | DS-01 | accepted | Split S2 or otherwise make blast-radius ownership explicit. Controller prefers splitting current S2 into separate owner slices for Web resource/challenge/search and Web diagnostic/smoke oracle, even if R3-E becomes 4 slices, because OOM/resource, provider outcome, secret persistence, and CI oracle failures are distinct blast radii. If the plan keeps 3 slices, it must explicitly record accepted risk and explain why controller should override blast-radius guidance. |
| R3-E-PF-04 | MiMo-03 + DS-03 | accepted | Specify Playwright DOM/text preflight APIs and tests. The plan must forbid `page.content()` / `outerHTML` as the preflight size check and must state exactly what lightweight APIs are allowed, what they guarantee, and what remains residual browser-process risk. |
| R3-E-PF-05 | MiMo-04 + DS-04 | accepted | Correct cleanup promises. Add storage-state atomic write plus startup cleanup, and classify SIGKILL cleanup limits for storage state and bounded source temp files as residuals with owner/destination. Do not claim cleanup is guaranteed under SIGKILL. |
| R3-E-PF-06 | MiMo-05 | accepted | Specify the parent-owned smoke fixture request ledger: lifecycle, in-memory vs persistent scope, sentinel generation, expected digest source, and required negative controls. |
| R3-E-PF-07 | MiMo-06 + DS open question | accepted | Define DuckDuckGo known result shape, explicit no-results marker, malformed-item threshold, and challenge/login shape drift criteria. |
| R3-E-PF-08 | MiMo-07 | accepted | Define WebResourceBudget provider JSON path and include a minimal full-object example. |

No reviewer finding is rejected. No finding is deferred.

## Controller Notes

- R3-E remains current-scope despite security-sensitive egress/resource findings. It is not a broad tool-security framework WU.
- The plan may exceed the optimization document's preferred 1-3 slices if the reason is a directly evidenced distinct failure blast radius. R3-E is high risk; avoiding cross-contamination between resource, diagnostic, oracle, and document review gates is more important than minimizing gate count.
- Implementation must not start until `R3-E-PF-01` through `R3-E-PF-08` are fixed and re-reviewed.

## Next Gate

Plan-fix by AgentCodex, then plan re-review by AgentMiMo and AgentDS.
