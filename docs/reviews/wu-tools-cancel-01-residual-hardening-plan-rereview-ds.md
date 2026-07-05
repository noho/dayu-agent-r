# WU-TOOLS-CANCEL-01 Residual Hardening Plan — Plan Re-Review (DS)

## Re-Review Metadata

- **Reviewed target**: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md` (post plan-fix)
- **Fix artifact**: `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-fix-codex.md`
- **Prior DS review**: `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-ds.md`
- **Prior MiMo review**: `docs/reviews/plan-review-20260705-141254.md`
- **Re-review date**: 2026-07-05
- **Scope**: targeted re-review — confirm whether all prior review findings (DS F1–F5, MiMo F01–F05) are resolved in the updated plan. No implementation, no code modification.

## Finding Status Matrix

### DS Review Findings (my prior review)

| ID | Severity | Description | Status | Evidence |
|----|----------|-------------|--------|----------|
| F1-DS | 中 | S1 wiring path omits `DeclaredToolExecutionCapsuleFactory` | **CLOSED** | Updated plan S1 line 161: explicit chain `HostToolingOptions` → `ToolRuntimeBuildRequest` → `DefaultToolRuntimeFactory.create_tool_runtime(...)` → `DeclaredToolExecutionCapsuleFactory.__init__(...)` → `DeclaredToolExecutionCapsuleFactory.create_capsule(...)` → `_declared_capsule_for_execution(...)` → `ProcessBackedToolExecutionCapsule(...)` |
| F2-DS | 中 | S2 smoke design overclaims real browser cleanup proof | **CLOSED** | Updated plan line 24: "no surviving synthetic nested child process in the tested cancellation/timeout path. Real Chromium process tree cleanup is only claimed if a browser-binary-backed optional/manual smoke runs in the environment." S2B lines 225-226: optional live browser smoke, skipped if binaries unavailable |
| F3-DS | 低 | S3 grep-test scope narrower than duplicated constants | **CLOSED** | Updated plan S3 line 267: "prevent any local `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, or `_WEB_PROCESS_*` envelope constants from reappearing after migration, not only `*_STATUS_FIELD`" |
| F4-DS | 低 | `ProcessBackedToolTarget` docstring stale after hint contract change | **CLOSED** | Updated plan S1 line 158: "Update `ProcessBackedToolTarget.__call__` docstring to include optional `hint` in the failed envelope shape." Contract decisions line 112 same directive |
| F5-DS | 低 (defer) | Web cold-start and S2 process-group cleanup interaction unexplored | **DEFERRED-WITH-OWNER** | Updated plan residual risks line 331: "Web process cold-start remains deferred as performance-only unless S2B evidence shows child process group ownership instability or survivor processes that weaken cancellation robustness." Ownership remains with future cold-start phase |

### MiMo Review Findings (`plan-review-20260705-141254.md`)

| ID | Severity | Description | Status | Evidence |
|----|----------|-------------|--------|----------|
| F01-MiMo | 中 | Playwright cleanup "reuse or mirror" is unresolved design decision | **CLOSED** | Updated plan S2A line 129: "`InterruptibleProcessHandle` and the Playwright raw `multiprocessing.Process` path must call the same primitives; do not duplicate process-group logic in Web code." S2B line 223: "Replace Playwright raw process cleanup's direct terminate/kill helper with calls to the shared runtime process-group cleanup primitive." |
| F02-MiMo | 低 | Grace policy defaults defer tuning without guidance | **CLOSED** | Updated plan line 117: "S2B must measure or otherwise assert SIGTERM-to-exit behavior for the nested/Playwright smoke and adjust the named defaults upward if the current values are insufficient." |
| F03-MiMo | 低 | `_validate_grace_seconds` doesn't validate NaN/infinity | **CLOSED** | Updated plan line 118: "Negative values, `float("nan")`, `float("inf")`, and `float("-inf")` fail fast. The lower-level runtime `_validate_grace_seconds` path must enforce the same finite/non-bool/non-negative contract." S1 tests lines 168-169 explicitly enumerate `bool`, negative, NaN, inf, -inf rejection cases for both policy fields and runtime validation |
| F04-MiMo | 低 | `os.setsid` race window acknowledged but not designed around | **CLOSED** | Updated plan line 130: "Signal the direct child PID first, then use process-group signaling only after confirming `os.getpgid(child_pid)` is available and differs from the current/parent process group. If pgid lookup fails, the child has exited, or the child pgid is unavailable/unchanged, fall back to direct-child cleanup and record the limitation." |
| F05-MiMo | 低 | S2 scope could be tightened by splitting Playwright smoke to S3 | **CLOSED** | Updated plan splits S2 into S2A (runtime process-group cleanup primitive, lines 178-206) and S2B (Playwright cleanup smoke, lines 207-239). S2B prerequisite: "S2A shared primitive exists, or S2A has explicitly classified process-group cleanup as unsupported/fallback on the current OS." |

## Post-Fix Plan Structural Assessment

### Positive Changes

1. **S2A/S2B split** resolves the S2 coupling concern cleanly. S2A delivers the layer-neutral primitive; S2B validates it from the Playwright side. S2B's stop condition (line 238) correctly gates on S2A's outcome.

2. **Explicit wiring path** (S1 line 161) now names every class in the chain. An implementation agent can trace from `HostToolingOptions` to `ProcessBackedToolExecutionCapsule` without guessing.

3. **Safe signaling strategy** (line 130) specifies direct-PID-first-then-pgid, eliminating the parent-self-kill race. The fallback path (unavailable/unsafe pgid → direct-child-only) is explicit and test-observable.

4. **Grace tuning validation** (line 117) ties default value validation to measured S2B evidence rather than leaving it as an open implementation guess.

5. **Hardcoded constant removal** (line 163) now has explicit grep-validation in both S1 tests (line 171) and S4 validation (line 319).

### Potential New Issues Found: None

The updated plan introduces exactly zero new risks that exceed the prior review baseline. Specific areas checked:

| Check | Result |
|-------|--------|
| 5 slices within control doc budget? | Yes — control doc line 145: "中型跨 contract / provider / projection work：3-5 个 implementation slices" |
| S2A/S2B dependency correctly expressed? | Yes — S2B line 219: prerequisite is "S2A shared primitive exists, or S2A has explicitly classified process-group cleanup as unsupported/fallback" |
| New file `test_smoke_web_ci.py` in S2B allowed files? | Conditional ("only if") — line 215. Doesn't force smoke layer change. |
| Cross-slice test scope: S1 tests runtime validation but `interruptible_process.py` is S2A? | Acceptable — S1 tests `ProcessCapsuleInterruptPolicy` field validation (policy-layer); S2A fixes `_validate_grace_seconds` (runtime-layer). S1 line 169 says "for `_validate_grace_seconds` or its replacement" — the S2A change updates the runtime function; the S1 policy test covers the contract the runtime function must also meet. |
| Any regression on architecture constraints? | No — all AGENTS.md checks remain satisfied: no Any/object/untyped, no reverse dependency, `dayu.runtime` stays layer-neutral. |
| Envelope contract docstring update? | Covered — S1 line 158 and contract decision line 112. |

## Open Questions

None. All 10 prior findings are closed or deferred-with-owner. No new material gaps introduced by the fix.

## Residual Risks (post-fix)

| Risk | Tracking |
|------|----------|
| Real Chromium process-tree cleanup remains environment-dependent | S2B optional live browser smoke; residual risks line 330 |
| AAPL XBRL fixture network dependency | S3 stop condition; residual risks line 332 |
| Web cold-start + process-group interaction | Deferred to future phase; residual risks line 331 |
| Windows process-group cleanup | Unsupported/fallback; residual risks line 333 |

## Plan Re-Review Conclusion

**Verdict: PASS**

All 10 prior review findings (5 DS + 5 MiMo) are resolved:
- 9 findings **CLOSED** — each with direct plan-text evidence.
- 1 finding (F5-DS: Web cold-start interaction) **DEFERRED-WITH-OWNER** — correctly tracked in plan residual risks, ownership belongs to future cold-start phase.

The updated plan is code-generation-ready. Slices are well-isolated with explicit dependencies and stop conditions. Wiring paths, validation cases, and signaling strategies are now specific enough for an implementation agent to execute without guessing.

No new blocking findings. No residual architecture violations.

### Controller-Facing Summary

```text
READY_FOR_CONTROLLER
Artifact: docs/reviews/wu-tools-cancel-01-residual-hardening-plan-rereview-ds.md
Verdict: PASS
Prior findings closed: 9 (F1-DS, F2-DS, F3-DS, F4-DS, F01-MiMo, F02-MiMo, F03-MiMo, F04-MiMo, F05-MiMo)
Prior findings deferred-with-owner: 1 (F5-DS)
New findings: 0
Blocking open question: None
```
