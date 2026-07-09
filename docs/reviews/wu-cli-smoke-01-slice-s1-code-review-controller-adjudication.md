# WU-CLI-SMOKE-01 Slice S1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: Slice S1 code review
- Date: 2026-07-06
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-slice-s1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/code-review-20260706-170636.md` (AgentMiMo)
  - `docs/reviews/code-review-20260706-170940.md` (AgentDS)

## Review Summary

AgentMiMo reported no material finding. It confirmed the fix is limited to CLI-local `_run_interactive_repl(...)` state, preserves the running-state Host public cancel path, covers first idle Ctrl+C non-exit, second consecutive idle Ctrl+C exit, and normal submitted-input reset, and keeps README / tests README in sync.

AgentDS reported one low-severity contract-compliance finding about typing-level reset not being directly observable from `_run_interactive_repl(...)` without changing the composer protocol or prompt-toolkit key binding. AgentDS also concluded the actual terminal UX remains correct and aligned with Codex / Claude Code because prompt-toolkit clears non-empty draft input internally before any empty-prompt `KeyboardInterrupt` reaches the REPL.

## Findings Adjudication

| Finding | Source | Controller decision | Reason | Required action |
|---|---|---|---|---|
| No material issue | AgentMiMo | accepted as pass | Review evidence directly follows the changed code path, tests, README sync, and design boundaries. | None. |
| F01 idle-interrupt typing-level reset contract gap | AgentDS | rejected-with-reason as current code defect; tracked as manual UX evidence point | The accepted plan deliberately forbids changing `InteractiveComposer` protocol or prompt-toolkit key binding unless direct evidence proves the existing boundary false. The implementation artifact provides the direct evidence required by the plan: `_run_interactive_repl(...)` cannot observe raw typing before `composer.read(...)` returns or raises. The plan validation section also allows covering the feasible observable reset boundary when raw typing cannot be observed. Current code preserves the user-visible non-empty draft behavior through prompt-toolkit's existing clear-buffer path and fixes the reproduced empty-prompt one-Ctrl+C exit. | No code fix in Slice S1. Include the raw-typing sequence as an optional observation inside the existing manual real-interactive evidence before final closeout if the user wants to inspect it. |

## Accepted Slice Decision

Slice S1 is accepted for commit after controller validation is rerun. No AgentCodex fix gate is required.

## Residual Risk

- Real provider `dayu-cli prompt` evidence remains manual before final closeout.
- Real provider `dayu-cli interactive` running-state Ctrl+C evidence remains manual before final closeout.
- Optional real Fins download / process evidence remains user-controlled external-network validation.
- PTY-level Ctrl+C evidence currently lives under `workspace/tmp/wu-cli-smoke-01-auto/`; maintained regression coverage is provided by focused CLI tests, while the PTY helper is work-unit evidence rather than a permanent test entry.
