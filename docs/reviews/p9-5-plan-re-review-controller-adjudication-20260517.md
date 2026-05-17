# P9.5 Plan Re-Review Controller Adjudication

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Gate: plan fix re-review.
- Plan artifact: `docs/host/p9-5-pre-p10-hardening-plan.md`.
- Controller plan review adjudication: `docs/reviews/p9-5-plan-review-controller-adjudication-20260517.md`.
- Re-review artifacts:
  - `docs/reviews/p9-5-plan-re-review-mimo-20260517.md`
  - `docs/reviews/p9-5-plan-re-review-ds-20260517.md`
- Design truth: `docs/host/design.md`.
- Control truth: `docs/host/implementation-control.md`.
- Date: 2026-05-17.

## Verdict

Plan re-review is accepted. P9.5 implementation-ready handoff plan is approved for accepted plan commit and subsequent implementation dispatch.

Both AgentMiMo and AgentDS confirmed:

- all controller-accepted plan-review findings are fixed;
- S14 `current_goal` and `SessionContinuityProvider` instructions are now code-generation-ready;
- non-blocking accepted guidance was integrated into the plan;
- no new blocking finding was introduced by the plan fix.

## Accepted Fix Verification

| Area | Controller decision |
| --- | --- |
| S14 `current_goal` first-write-wins | Fixed. Plan now identifies `dayu/host/memory.py`, the memory projection write path, `_pinned_state_with_user_input(...)`, first-write-wins enforcement direction, targeted tests, and non-goals. |
| S14 `SessionContinuityProvider` | Fixed. Plan now identifies `dayu/host/run_input.py`, `DurableSessionContinuityProvider`, the RunInputBuilder bypass mechanism, remove-vs-tighten decision rule, cleanup boundary, tests, and stop condition. |
| Shared test ownership | Fixed. Plan now states later slices must preserve prior-slice assertions and report shared fixture refactors. |
| S15 logging | Fixed. Plan now requires auditing existing logs first and following existing module-level logger patterns. |
| S11 ToolRuntime extraction | Fixed. Plan now limits extraction to real coupling, forbids test-only private re-export, and prefers behavior tests through documented public entries. |
| Slice dependency and commit strategy | Fixed. Plan now states sequential default dispatch, explicit dependency notes, and controller-owned commit strategy. |
| S2 direct evidence | Fixed. Plan now defines direct evidence and excludes theory-only parser fixes. |
| S6 test layering | Fixed. Plan now separates DB CHECK tests from Python mapping fail-closed tests. |
| S0 pyright baseline | Fixed. Plan now records a pre-S1 pyright baseline and limits handling of pre-existing errors. |

## Residual Risks

The following residual risks remain accepted and tracked in the plan:

- S13 may require controller裁决 if no existing typed public error detail can express size-limit failures.
- S16 may discover documented public exports that are misplaced; public-interface movement must stop for controller裁决.
- S5 may require fresh schema version bump; legacy migration remains forbidden.
- S11 ToolRuntime extraction must remain narrow and stop if it becomes semantic refactor.
- S14 must reassign any snapshot-history coupling outside P9.5.

These risks are not blockers because each has a concrete stop condition and owner path in the plan.

## Next Gate

Next gate: accepted plan commit. After the commit is created and recorded, P9.5 enters implementation dispatch starting with S0 Controller Preflight And Scope Lock.
