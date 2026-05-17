# P9.5 Plan Review Controller Adjudication

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Gate: implementation-ready handoff plan review.
- Plan artifact: `docs/host/p9-5-pre-p10-hardening-plan.md`.
- Review artifacts:
  - `docs/reviews/p9-5-plan-review-mimo-20260517.md`
  - `docs/reviews/p9-5-plan-review-ds-20260517.md`
- Design truth: `docs/host/design.md`.
- Control truth: `docs/host/implementation-control.md`.
- Date: 2026-05-17.

## Verdict

Plan review is accepted with required plan fix before accepted plan commit.

Both reviewers found zero whole-plan blocking findings. The controller accepts the shared conclusion that the plan motivation is real and properly scoped: P9.5 should reduce pre-P10 infrastructure noise without moving Host governance into Engine, runtime, projection, read models, or logs.

However, the controller accepts AgentDS F1 and F2 as required plan-fix items because S14 is not yet sufficiently code-generation-ready. P9.5 is allowed to proceed only after the plan clarifies those S14 instructions and re-review confirms the fix.

## Finding Adjudication

| Source | Finding | Controller decision | Required action |
| --- | --- | --- | --- |
| AgentDS | F1: S14 `current_goal` first-write-wins is underspecified | Accepted | Fix plan before accepted plan commit. Define current code owner/path, write path, enforcement strategy, and targeted validation expectation. |
| AgentDS | F2: S14 legacy `SessionContinuityProvider` parameters are underspecified | Accepted | Fix plan before accepted plan commit. Identify module/path, legacy parameter behavior, bypass mechanism, and remove-vs-tighten decision rule. |
| AgentDS | F3: S10/S14 share `test_resolve_wait_command.py` | Accepted as non-blocking | Add dispatch/plan guidance that later slices must not weaken prior slice assertions and must report fixture refactors. |
| AgentDS | F4: S15 should audit existing logs before adding new logs | Accepted as non-blocking | Add S15 instruction to audit existing logs first. |
| AgentDS | F5: S11 private-module test dependency risk | Accepted as non-blocking | Add S11 stop condition/guidance that behavior tests or documented public entry are preferred; no test-only private re-export. |
| AgentMiMo | F-01: slice dependencies are implicit | Accepted as non-blocking | Add dependency/dispatch-order guidance in plan or controller dispatch state. |
| AgentMiMo | F-02: S15 logger acquisition mode unspecified | Accepted as non-blocking | Add guidance to follow existing project logger pattern, defaulting to module-level `logging.getLogger(__name__)` where local code already uses that pattern. |
| AgentMiMo | F-03: S14 `current_goal` ambiguity | Duplicate of DS F1 | Covered by DS F1 required plan fix. |
| AgentMiMo | F-04: S6 unknown enum test layer ambiguity | Accepted as non-blocking | Clarify S6 tests should distinguish DB CHECK rejection from Python mapping fail-closed behavior. |
| AgentMiMo | F-05: slice commit organization unspecified | Accepted as non-blocking | Add controller/git strategy guidance: high-risk slices remain separate accepted commits; adjacent low-risk slices may be combined only with explicit controller decision. |
| AgentMiMo | F-06: directly evidenced parser defect standard unspecified | Accepted as non-blocking | Add S2 evidence standard: existing failing test, direct code evidence, provider protocol behavior, or official provider documentation; theory-only fixes are out of scope. |
| AgentMiMo | F-07: pyright baseline unspecified | Accepted as non-blocking | Add S0 baseline pyright check and handling rule for pre-existing errors. |
| AgentMiMo | F-08: S11 extraction granularity risk | Accepted as non-blocking | Add S11 guidance to extract only where it removes real coupling; not every listed owner must become a module. |

## Controller Rationale

The review findings are judged against `docs/host/design.md` and first principles:

- P9.5 must preserve Host as the canonical owner of lifecycle, EventLog, ToolRuntime accept, dispatch governance, memory projection, and public API error semantics.
- A plan that leaves S14 underspecified would push memory semantic design into implementation, which violates the handoff-ready requirement and risks accidental snapshot-history work.
- Low-risk clarity improvements should be written into the plan because they reduce coordination risk across 19 slices without changing architecture.
- No finding justifies expanding P9.5 into P10 Context Governance, P11 recovery, P12 discovery, P13 sinks, P14 remote execution, or P15 purge/retention.

## Required Plan Fix Scope

The fix agent must update only `docs/host/p9-5-pre-p10-hardening-plan.md` unless it discovers a blocking inconsistency in this adjudication.

Required fixes:

- Clarify S14 `current_goal` ownership, write path, enforcement direction, and tests.
- Clarify S14 `SessionContinuityProvider` legacy parameter ownership, bypass mechanism, remove-vs-tighten decision rule, and tests.
- Add non-blocking guidance accepted above for dependencies, logger pattern, S6 test layering, S10/S14 shared test ownership, S11 extraction/test dependency, S15 log audit, S2 direct-evidence threshold, S0 pyright baseline, and slice commit strategy.

Stop conditions for the fix agent:

- The fix would require changing `docs/host/design.md`.
- The fix would introduce P10+ semantics or alter P9.5 scope.
- The fix cannot identify current S14 code ownership from direct repository evidence.

## Next Gate

Next gate: P9.5 plan fix, then plan re-review by AgentMiMo and AgentDS. Accepted plan commit is not allowed until re-review confirms the accepted findings are fixed.
