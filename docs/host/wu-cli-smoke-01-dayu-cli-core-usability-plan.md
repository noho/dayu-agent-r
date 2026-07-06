# WU-CLI-SMOKE-01 dayu-cli Core Usability Plan

## Gate

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Type: immediate residual work unit / smoke and behavior validation
- Current gate: plan
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Goal artifact: `docs/reviews/wu-cli-smoke-01-goal-confirmation.md`
- Auto-validation artifact: `docs/reviews/wu-cli-smoke-01-auto-validation-codex.md`

## Goal / Motivation / Success Signal

Goal: harden `dayu-cli` core usability with a small real-environment smoke and targeted fixes for behavior failures proven by the smoke.

The work unit is valid. `dayu-cli` is a user-facing local entrypoint, and the current evidence shows broad command paths are usable but one important terminal behavior is not: `interactive` exits on the first Ctrl+C while idle at the input prompt.

Success signals:

- Real CLI smoke evidence remains reproducible under `workspace/tmp/wu-cli-smoke-01-auto/`.
- `dayu-cli interactive` matches generic Agent terminal UX where applicable: first Ctrl+C in idle input state returns to a clean interactive prompt, second Ctrl+C exits.
- Idle input Ctrl+C has an exact two-step counter contract: the first Ctrl+C at an empty prompt records an exit-pending interrupt and redisplays a clean prompt without exiting; the second consecutive idle Ctrl+C exits. Prompt redisplay alone does not reset the pending-exit state.
- During a submitted run, first Ctrl+C requests Host cancel through public Service/Host APIs, and second Ctrl+C requests local exit while cancellation is pending.
- Fresh workspace commands do not create nested `workspace/workspace/.dayu` or `workspace/workspace/portfolio`.
- CLI continues to keep UI stdout/stderr separate from explicit debug log files.
- Focused tests, `git diff --check`, and `pyright` pass.

## Expectation Sources

Generic Agent terminal UX expectations:

- For generative Agent terminal behavior, align with Codex / Claude Code level behavior where the Dayu design does not define a stricter rule.
- Idle interactive input should not terminate on the first Ctrl+C; it should clear/cancel the current input attempt and return to a usable prompt.
- A second Ctrl+C after an interrupt request may exit locally.
- User-facing output should be actionable and should not expose traceback-style internals for normal interrupt/use errors.

Dayu-specific design-truth expectations:

- `docs/host/design.md` fixes `UI -> Service -> Host -> Engine`; CLI is UI, Service maps product entrypoints, Host owns Session / Run / Attempt / EventLog / cancel truth, Engine owns a single `AgentRunRequest`.
- CLI must not construct Engine requests, mutate Host durable internals, or bypass Service/Host public APIs to fake success.
- Run cancellation must use Host public cancel semantics, not local-only stopgaps, once a Run exists.
- Fins direct commands are Service-bound direct streams and must not be disguised as Host Runs.

If later implementation discovers a Dayu-specific behavior that is not derivable from these design docs and code evidence, stop and return a blocking question to the phaseflow controller.

## Non-goals / Scope Boundary

Non-goals:

- Do not implement `dayu-cli write`.
- Do not add Web, GUI, or WeChat entrypoints.
- Do not change Host / Engine public contracts, durable schema, EventLog semantics, or wait lifecycle unless direct evidence proves the CLI behavior cannot be fixed truthfully without that design change.
- Do not fake real CLI behavior with only mocks.
- Do not perform live model/provider or external filing download validation without user-owned configuration and low-risk approval.

Allowed implementation scope for the next gate:

- `dayu/cli/**` for terminal UX, command behavior, and CLI-only signal state.
- `tests/cli/**` for focused regression coverage.
- Focused `tests/service/**` only if a Service public entrypoint boundary must be proven.
- `utils/` only for smoke script adjustment if the validation harness itself needs a stable reusable entry.
- README files only if their own update constraints say the changed user-visible CLI behavior belongs there.

## Design Alignment

The plan keeps the fix in CLI UI state management unless new evidence proves otherwise. That aligns with Dayu layering: idle input has no Host Run to cancel, so repairing idle Ctrl+C by mutating Host state would be the wrong layer. Running-state cancellation already has a Service/Host public path and must remain rooted there.

The plan does not introduce a generic CLI framework, smoke platform, signal daemon, or new Host state. It only closes the concrete behavior gap demonstrated by the smoke and preserves existing public boundaries.

## Direct Code Evidence

- `dayu/cli/main.py:73` parses CLI args, opens logging, dispatches command runners, and catches top-level `KeyboardInterrupt`.
- `dayu/cli/commands/interactive.py:505` catches `EOFError` while reading input but does not catch or classify input-state `KeyboardInterrupt`.
- `dayu/cli/commands/interactive.py:541` implements running-state submit handling with a `CliSigintMonitor`.
- `dayu/cli/commands/interactive.py:740` waits for Host cancel terminal or second SIGINT after a Run exists.
- `dayu/cli/composer.py` already documents `KeyboardInterrupt` as the empty-draft interrupt signal for `InteractiveComposer`, while prompt-toolkit key binding clears non-empty input locally and raises `KeyboardInterrupt` only from an empty prompt.
- `dayu/cli/agent_entrypoint.py:56` installs an asyncio SIGINT handler for run-state monitoring only.
- `dayu/cli/commands/fins.py:1` documents the Fins direct command as a CLI UI adapter over `FinsDirectCommandService`.

Root cause hypothesis for the reproduced failure: idle input state and running state use different SIGINT ownership. Running state has a two-step cancellation state machine, but idle input allows `input` / the composer stack to raise `KeyboardInterrupt`, which escapes to command/top-level handling and exits with 130. The implementation gate must confirm this against the actual composer path before editing.

## Validation Evidence

From `docs/reviews/wu-cli-smoke-01-auto-validation-codex.md`:

- Help surface for top-level, Agent commands, session, and Fins direct commands: pass.
- Fresh workspace init with explicit debug log path: pass.
- Path regression scan after init and after smoke commands: pass; no nested `.dayu` or `portfolio` under `workspace/workspace`.
- Public awaiting smoke through public contracts: pass.
- Fins low-risk CLI-Service boundary checks: pass.
- Existing focused tests: `234 passed`.
- Interactive idle Ctrl+C PTY probe: fail; first Ctrl+C exits process after prompt is visible.

## Affected Files / Modules

Likely production files:

- `dayu/cli/commands/interactive.py`
- `dayu/cli/composer.py` only if new direct code evidence proves the current `InteractiveComposer` `KeyboardInterrupt` boundary is false.
- `dayu/cli/agent_entrypoint.py` only if new direct evidence proves a shared CLI SIGINT primitive is required without adding Host semantics.

Likely tests:

- `tests/cli/test_interactive_command.py`
- `tests/cli/test_interactive_composer.py`
- A focused PTY-style regression test or smoke helper if unit injection cannot prove terminal behavior.

Artifacts:

- Update `docs/reviews/` implementation/fix artifacts in later gates as required by phaseflow.
- Keep raw smoke output under `workspace/tmp/`.

## Contract / Schema / State-machine / Public-interface Changes

Expected: none for Host, Engine, durable schema, EventLog, Fins storage, or Service public contracts.

CLI-local state-machine change is expected:

- Add an idle input interrupt state alongside the existing running-state interrupt path.
- First idle Ctrl+C at an empty prompt must clear/cancel the current input attempt, record an exit-pending idle interrupt, redisplay a clean prompt, and continue the REPL without exiting.
- Second consecutive idle Ctrl+C at an empty prompt must exit locally with the existing keyboard interrupt exit code.
- Prompt redisplay caused by the first idle Ctrl+C does not reset the exit-pending state. This is intentional: two consecutive empty-prompt Ctrl+C inputs mean local exit.
- The exit-pending idle interrupt state must reset when the user performs non-interrupt input activity, including submitting a prompt, EOF handling, or entering a running Run state. Typing-level reset is part of the user-visible contract; if implementation cannot observe raw typing from `_run_interactive_repl` without changing the composer protocol or prompt-toolkit key binding, stop and return direct evidence to the controller instead of silently weakening the contract.

If implementation discovers the running-state cancel path is also broken, the fix must repair the Service/Host cancel state machine root cause. Do not add a local-only stopgap that merely hides stale output or kills the process.

## Implementation Decisions

1. Treat idle input Ctrl+C as CLI UI behavior, not Host cancel behavior, because no Run exists yet.
2. Preserve existing running-state cancellation through `cancel_entrypoint_run_and_wait`.
3. Default fix target is `_run_interactive_repl` input-loop handling around the existing `InteractiveComposer.read(...)` boundary.
4. Do not change the `InteractiveComposer` protocol or prompt-toolkit key binding unless new direct code evidence proves the current boundary is false. The current evidence says the composer already raises `KeyboardInterrupt` for empty-prompt Ctrl+C and clears non-empty input internally.
5. Catch and classify idle-input `KeyboardInterrupt` narrowly enough that running-state cancellation remains owned by `CliSigintMonitor` and Service/Host cancel APIs.
6. Keep signal handling deterministic and testable through injected composer/input reader where possible.
7. Keep PTY smoke as evidence for terminal reality; do not rely only on injected unit tests for the UX oracle.

## Implementation Slices

One implementation slice is sufficient.

Slice S1: `interactive` terminal interrupt hardening and smoke regression.

- Input: current CLI code and auto-validation artifact.
- Output: idle Ctrl+C first-interrupt behavior fixed, running-state cancel behavior preserved, tests and real CLI validation updated.
- Allowed files: `dayu/cli/**`, `tests/cli/**`, narrowly scoped `utils/` if a reusable smoke helper is needed, README only if triggered by local README constraints.
- Validation: focused CLI tests, PTY idle Ctrl+C smoke, public awaiting smoke, Fins low-risk smoke, `git diff --check`, `pyright`.

This follows the control doc Slice principle because the work is one semantic closed loop: CLI terminal usability. Splitting by file would add gate cost without reducing behavioral risk.

## Tests / Validation Commands

Required implementation validation:

```bash
source .venv/bin/activate && pytest tests/cli tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_fins_direct.py -q
source .venv/bin/activate && python workspace/tmp/wu-cli-smoke-01-auto/probe_interactive_ctrl_c.py --scenario first-idle-ctrl-c
source .venv/bin/activate && python workspace/tmp/wu-cli-smoke-01-auto/probe_interactive_ctrl_c.py --scenario second-consecutive-idle-ctrl-c
source .venv/bin/activate && python workspace/tmp/wu-cli-smoke-01-auto/probe_interactive_ctrl_c.py --scenario reset-after-normal-input-activity
source .venv/bin/activate && python utils/smoke_host_public_awaiting_entrypoint.py --workspace-root workspace/tmp/wu-cli-smoke-01-auto/fresh-workspace --keep-workspace
source .venv/bin/activate && git diff --check
source .venv/bin/activate && pyright
```

Expected assertions:

- PTY scenario `first-idle-ctrl-c` sees `dayu>`, sends one Ctrl+C at an empty prompt, records `exited_after_first_ctrl_c=False`, and observes a clean prompt redisplay.
- PTY scenario `second-consecutive-idle-ctrl-c` sees `dayu>`, sends two consecutive empty-prompt Ctrl+C inputs with no intervening user input activity, records first Ctrl+C non-exit, and records second Ctrl+C local exit with the existing keyboard interrupt exit code.
- PTY scenario `reset-after-normal-input-activity` proves reset after normal input activity where feasible. Preferred coverage is first idle Ctrl+C non-exit, then a non-interrupt user activity such as typed/submitted input or EOF handling, then a later idle Ctrl+C is treated as a new first interrupt rather than an exit. If raw typing cannot be observed without changing `InteractiveComposer` protocol or prompt-toolkit binding, the implementation gate must document that direct evidence and still cover the feasible observable reset boundary.
- Existing run-state tests still prove `cancel_entrypoint_run_and_wait` is called after a Run id is accepted.
- No nested workspace path regression appears after smoke commands.
- Fins low-risk command validation remains free of live external download.

Manual validation still required:

- User-run `dayu-cli prompt` against configured provider.
- User-run `dayu-cli interactive` with a real accepted run and Ctrl+C during generation/tool execution.

## Docs Decision

This plan gate does not modify README files. During implementation, inspect the relevant README update constraints before changing docs. If no README currently documents Ctrl+C semantics or interactive terminal behavior, tests and review artifacts may be sufficient; if a user-facing CLI behavior section exists, update it narrowly.

## Risks / Open Questions

- The PTY probe currently proves idle input behavior only. Running-state cancellation still needs a real configured provider or a controlled public-entrypoint runner to prove terminal UX end to end.
- Prompt-toolkit or terminal control sequences can make PTY checks brittle if they assert raw bytes too strictly; the smoke should assert behavior and stable prompt markers, not full transcript.
- Current composer evidence indicates multiline input is not part of the active behavior surface; do not expand this WU into multiline editor semantics without new direct evidence.
- Blocking question for controller only if implementation evidence contradicts this plan's fixed contract: first idle Ctrl+C at an empty prompt records exit-pending state, prompt redisplay alone does not reset it, second consecutive idle Ctrl+C exits, and non-interrupt user input activity resets it.

## Completion Report Format

Implementation closeout should report:

- Files changed.
- Behavior fixed, including idle Ctrl+C and any running-state evidence.
- Validation commands and pass/fail summary.
- Raw smoke artifact paths.
- README decision and whether any README was updated.
- Remaining manual evidence or residual risk with owner/destination.
