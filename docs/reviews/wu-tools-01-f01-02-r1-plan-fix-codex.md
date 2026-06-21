# WU-TOOLS-01-F01-02-R1 Plan Fix — Codex

## Metadata

- Work unit: `WU-TOOLS-01-F01-02-R1`
- Gate: fix after plan review
- Plan artifact: `docs/host/wu-tools-01-f01-02-r1-plan.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-plan-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r1-plan-fix-codex.md`

## Changed Plan Sections

- `## 6. Contract / Schema / State-machine / Public-interface Changes`
  - Tightened accepted-wait activation failure behavior.
  - Clarified rejected / timeout / stale / pre-accept cancellation behavior for prepared-but-unaccepted observations.
- `## 7. Implementation Decisions`
  - Rewrote activation failure handling so Fins activation is the primary owner of terminal observation state.
  - Added explicit same-lock requirement for `activate_observation(handle)` and `cancel_observation(handle)`.
  - Added `Prepared-but-unaccepted observations` subsection.
  - Added note that separate `WaitActivationRegistry` is an intentional construction-time boundary choice.
- `## 8. Small Implementation Slices`
  - Slice 1 exact allowed changes now explicitly allow Host test fixture / harness extension for `wait_activation_registry` and spy/stub activation adapters.
  - Slice 1 expected assertions now require fixture-injected spy/stub activation verification.
  - Slice 2 exact allowed changes now require same-lock activation state checks and terminal failed/lost recording for submit failure and unexpected activation exceptions.
  - Slice 2 expected assertions now include deterministic cancel/activate ordering coverage and unexpected activation exception terminal-state coverage.

## Controller Finding Status

| Finding | Final status | Evidence in updated plan |
|---|---|---|
| C-F01 activation terminal guarantee / lock-order | 已修复 | Section 6 accepted-wait activation failure now requires terminal `FAILED` or `LOST`; Section 7 requires activation and cancellation to coordinate through the same observation lock, check cancellation / terminal / submitted under that lock, mark submitted under that lock, and make ToolRuntime catch only a safety net; Slice 2 validation requires deterministic cancel/activate ordering and unexpected activation exception terminal-state coverage. |
| C-F02 Slice 1 allowed test fixture changes | 已修复 | Slice 1 exact allowed changes explicitly allow extending Host test fixture / harness construction to inject `wait_activation_registry` and spy/stub activation adapters. |
| C-F03 prepared-but-unaccepted observation behavior | 已修复 | Section 7 adds `Prepared-but-unaccepted observations`: no activation, no durable cleanup ledger, no public cleanup contract, no new Host wait state, harmless process-local orphan semantics, and only optional narrowly scoped best-effort process-local abandon if an existing handle path is already available. |
| C-F04 unified registry alternative | 已修复 | Section 7 `Why this is not overdesigned` now notes separate `WaitActivationRegistry` is intentional construction-time Host wiring and avoids adding executable provider behavior to public wait binding metadata. The controller rejected the unified-registry change, so no design change was made. |

## Exact Plan Text Summary of Fixes

- Accepted wait + activation failure now says Fins activation is the primary owner for terminal observable state, and every activation failure path after Host accept must leave an identifiable prepared observation terminal `FAILED` or `LOST`.
- Activation failure handling now says ToolRuntime exception catch is only a bounded-diagnostic safety net, not the mechanism responsible for making Fins observations terminal.
- `activate_observation(handle)` and `cancel_observation(handle)` now must use the same observation lock. Activation must check cancellation state, terminal status and submitted flag under that lock, and mark submitted under that lock before submit.
- Prepared-but-unaccepted observations after accept rejected, timeout, stale execution or pre-accept cancellation now have explicit process-local orphan semantics and must not trigger durable cleanup or public contract expansion.
- Slice 1 now explicitly permits Host test fixture injection of `wait_activation_registry` and spy/stub activation adapters for exact call-count assertions.
- Slice 2 now requires deterministic cancel/activate ordering coverage and unexpected activation exception coverage proving the observation cannot remain indefinitely `PENDING`.
- The separate `WaitActivationRegistry` is documented as a deliberate boundary choice, not an accidental duplicate registry pattern.

## Validation Performed

- Read plan artifact, both plan review artifacts, and controller adjudication.
- Re-read the edited plan sections after patching.
- Checked that all controller accepted findings have explicit plan text coverage.
- Did not run tests or pyright because this gate only changed documentation and the user allowed plan-fix validation by document review.

## Residual Risks / Open Questions

- No blocking open questions remain for plan-fix.
- Production poller scheduling / backoff / fencing / retry remains outside this WU and owned by GitHub Issue #90.
- External provider physical cancel / revoke / abandon remains outside this WU and owned by GitHub Issue #92.
- Callback endpoint / auth / replay remains outside this WU and owned by GitHub Issue #89.
- Process-local observation loss on Host restart remains consistent with the current lightweight observation design and is owned by later wait hardening work where applicable.

## Stop State

- Plan-fix artifact written.
- Plan artifact updated.
- No production code, tests, control docs, design docs, README, commit, push or PR actions were performed.
