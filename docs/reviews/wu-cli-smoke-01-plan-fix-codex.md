# WU-CLI-SMOKE-01 Plan Fix

## Gate

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: fix after plan review
- Agent: AgentCodex
- Date: 2026-07-06
- Plan artifact fixed: `docs/host/wu-cli-smoke-01-dayu-cli-core-usability-plan.md`
- Controller adjudication: `docs/reviews/wu-cli-smoke-01-plan-review-controller-adjudication.md`

## Scope

This fix gate only updated the plan artifact. It did not modify production code, tests, README files, the control doc, raw smoke evidence, commits, pushes, PR state, or any next-gate artifact.

## Findings Fixed

| Finding | Final status | Fix summary |
|---|---|---|
| F1: idle Ctrl+C counter semantics not exact | fixed | The plan now defines the exact idle contract: first empty-prompt Ctrl+C records an exit-pending interrupt and redisplays a clean prompt without exiting; second consecutive empty-prompt Ctrl+C exits; prompt redisplay alone does not reset pending exit; non-interrupt input activity resets it. |
| F2: composer protocol change ambiguity | fixed | The plan now states the default fix target is `_run_interactive_repl` input-loop handling and explicitly forbids changing `InteractiveComposer` protocol or prompt-toolkit key binding unless new direct code evidence proves the current boundary is false. |
| F3: second Ctrl+C validation not concrete | fixed | The validation section now requires concrete PTY scenarios for first idle Ctrl+C non-exit, second consecutive idle Ctrl+C exit, and reset after normal input activity where feasible. Manual real-provider running-state validation remains user-owned evidence. |

## Plan Changes

- Added the exact two-step idle Ctrl+C counter contract to success signals and state-machine requirements.
- Added composer boundary evidence so implementation agents do not infer that composer protocol changes are preferred.
- Narrowed likely production targets to `dayu/cli/commands/interactive.py` by default, with composer or shared SIGINT changes allowed only after contradictory direct evidence.
- Replaced the prior implementation decision that preferred typed composer protocol changes with `_run_interactive_repl` input-loop handling.
- Replaced the old open question about counter reset behavior with the controller-adjudicated contract.
- Expanded validation commands and assertions into named PTY scenarios covering first, second, and reset behavior.

## Validation

Required validation for this fix gate:

```bash
source .venv/bin/activate && git diff --check
source .venv/bin/activate && pyright
```

Results are recorded in the completion report for this gate.

## Residual Risk

No new plan-level residual risk was introduced by this fix. The existing manual real-provider running-state Ctrl+C evidence remains deferred to the user-owned validation path already recorded in the goal confirmation and controller adjudication.
