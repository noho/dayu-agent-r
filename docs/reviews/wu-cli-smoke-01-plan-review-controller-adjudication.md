# WU-CLI-SMOKE-01 Plan Review Controller Adjudication

## Gate

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: plan review
- Plan artifact: `docs/host/wu-cli-smoke-01-dayu-cli-core-usability-plan.md`
- Auto-validation artifact: `docs/reviews/wu-cli-smoke-01-auto-validation-codex.md`
- Plan review artifacts:
  - `docs/reviews/plan-review-20260706-163952.md`
  - `docs/reviews/plan-review-20260706-164108.md`
- Controller decision: fix required before accepted plan commit

## Summary

Both reviewers concluded `pass-with-risks` and reported no blocking finding. The plan is directionally sound, but several plan-level ambiguities would force the implementation agent to guess terminal UX semantics or over-edit the input composer boundary. These findings are accepted as current plan fixes.

## Finding Adjudication

| Finding | Source | Decision | Controller rationale | Required fix |
|---|---|---|---|---|
| Plan does not define exact idle Ctrl+C counter reset semantics | MiMo F1, DS F02 | accepted | The WU exists specifically because generic Agent terminal UX must align with Codex / Claude Code. The implementation agent must not guess whether prompt redisplay resets the counter. | Update the plan to define: first idle Ctrl+C at an empty prompt does not exit; it records an exit-pending interrupt and returns to a clean prompt. A second consecutive idle Ctrl+C exits. The pending-exit state resets when the user performs non-interrupt input activity such as typing/submitting a prompt, EOF handling, or entering a running Run state. Prompt redisplay alone does not reset the pending-exit state. |
| Plan implies composer protocol changes may be preferred | MiMo F2, DS F01 | accepted | Code evidence shows the composer already has a documented `KeyboardInterrupt` boundary for empty-buffer Ctrl+C. Changing the composer protocol would expand scope and risk breaking existing non-empty-buffer behavior. | Update the plan to say implementation should not change `InteractiveComposer` protocol or prompt_toolkit key binding unless new direct evidence proves the boundary is false. Default fix target is `_run_interactive_repl` input-loop handling. |
| Plan does not make second Ctrl+C validation concrete enough | MiMo F3 | accepted | The success signal requires both first Ctrl+C non-exit and second consecutive Ctrl+C exit. Existing probe only proves the failure half. | Update validation commands and expected assertions to require PTY coverage for first idle Ctrl+C non-exit, second consecutive idle Ctrl+C exit, and reset after normal input activity where feasible. |
| Ctrl+C exit diagnostic output is unspecified | MiMo open question | rejected-with-reason | This is low-value UX detail for current scope. Existing top-level behavior exits with code 130 without a required user-facing message; changing output text is not necessary to fix the root cause. | No plan fix required unless implementation changes output behavior. |
| Multiline input behavior is unclear | DS open question | rejected-with-reason | Current composer is `multiline=False`; this is not current behavior surface. | No plan fix required. |

## Residual Risks

| Risk | Classification | Owner / destination |
|---|---|---|
| Real provider running-state Ctrl+C UX remains manually validated | deferred-with-owner | MANUAL-02 in `docs/reviews/wu-cli-smoke-01-goal-confirmation.md`; user supplies real environment evidence later in this WU. |
| Optional real Fins download/process remains manual | deferred-with-owner | MANUAL-03 in `docs/reviews/wu-cli-smoke-01-goal-confirmation.md`; user supplies credentials/network evidence if available. |

## Next Gate

Enter `fix` gate. AgentCodex must update only the plan / validation artifact as needed to close accepted plan-review findings. No production code, tests, README, commit, push, PR, or implementation is allowed in this fix gate.
