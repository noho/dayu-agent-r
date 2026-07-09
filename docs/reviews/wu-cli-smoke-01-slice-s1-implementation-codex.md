# WU-CLI-SMOKE-01 Slice S1 Implementation

## Gate

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: implementation
- Slice id: `S1`
- Slice objective: fix `dayu-cli interactive` idle terminal interrupt behavior and add regression validation.
- Agent: AgentCodex
- Date: 2026-07-06
- Completion status: implemented and validated; not staged, not committed, not pushed.

## Files Changed

- `dayu/cli/commands/interactive.py`
- `tests/cli/test_interactive_command.py`
- `README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-smoke-01-slice-s1-implementation-codex.md`

## Root Cause Evidence

The approved plan's reproduced failure was valid. Direct code evidence showed `_run_interactive_repl(...)` caught `EOFError` from `InteractiveComposer.read(...)` but did not catch `KeyboardInterrupt`. The composer boundary already raises `KeyboardInterrupt` only for empty-draft Ctrl+C, while non-empty Ctrl+C is handled inside prompt-toolkit by clearing the draft. Because `_run_interactive_repl(...)` did not classify the empty-prompt interrupt, it escaped to `run_interactive_command(...)`, which maps `KeyboardInterrupt` to the existing keyboard interrupt exit code.

No evidence required changing `InteractiveComposer`, prompt-toolkit key bindings, Service, Host, Engine, durable schema, EventLog semantics, Fins storage, or wait lifecycle.

## Behavior Implemented

- Added CLI-local idle input interrupt state inside `_run_interactive_repl(...)`.
- First `KeyboardInterrupt` from an empty `dayu>` prompt records exit-pending state, continues the loop, and causes the prompt to be read and displayed again.
- Prompt redisplay alone does not reset the pending state.
- Second consecutive empty-prompt `KeyboardInterrupt` returns the existing `EXIT_KEYBOARD_INTERRUPT`.
- EOF, blank-line input, and normal submitted input reset the pending state.
- Running-state cancellation remains Service/Host owned through the existing `CliSigintMonitor` and `cancel_entrypoint_run_and_wait(...)` path.
- `_run_interactive_repl(...)` cannot observe raw typing inside prompt-toolkit before the composer returns a submitted line or raises `KeyboardInterrupt` / `EOFError`. Covering raw typing reset would require changing the `InteractiveComposer` protocol or prompt-toolkit key binding, which S1 was instructed not to do without contradictory boundary evidence. This implementation therefore covers the observable reset boundary: submitted normal input resets the pending state.

## Tests And Validation

- `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/cli/test_interactive_composer.py -q`
  - Result: pass, `36 passed, 3 warnings`.
- `source .venv/bin/activate && python workspace/tmp/wu-cli-smoke-01-auto/probe_interactive_ctrl_c.py`
  - Result: pass evidence.
  - Summary: `prompt_seen=True`, `exited_after_first_ctrl_c=False`, `exited_after_second_ctrl_c=True`, `decision=pass`.
  - This existing `workspace/tmp` probe is evidence for this work unit only. It is not a maintained regression path because it lives under `workspace/tmp` and was not added to `utils/` or `tests/`.
- `source .venv/bin/activate && pytest tests/cli tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_fins_direct.py -q`
  - Result: pass, `236 passed, 3 warnings`.
- `source .venv/bin/activate && python utils/smoke_host_public_awaiting_entrypoint.py --workspace-root workspace/tmp/wu-cli-smoke-01-auto/fresh-workspace --keep-workspace`
  - Result: pass.
  - Output included existing diagnostic `dispatch.worker_events.clean_eof_without_terminal ...` and required pass marker `SMOKE PASS Host public awaiting entrypoint`.
- `source .venv/bin/activate && git diff --check`
  - Result: pass.
- `source .venv/bin/activate && pyright`
  - Result: pass, `0 errors, 0 warnings, 0 informations`.

## README Decision

- `README.md` was updated because the fix changes user-visible `dayu-cli interactive` terminal behavior and the root README is the final user manual.
- `tests/README.md` was updated because this slice added CLI regression coverage and the tests README records current test layering and coverage.

## Residual Risks / Manual Evidence

- Real provider `dayu-cli prompt` validation remains manual because it requires user-owned provider configuration.
- Real provider `dayu-cli interactive` running-state Ctrl+C during an accepted live run remains manual. Existing unit tests still prove accepted-run cancellation calls the Host public cancel path.
- Optional real Fins download/process remains manual because this slice intentionally avoided external network/provider validation.
- Raw typing before submit is not directly observed by `_run_interactive_repl(...)`; it remains a documented boundary of the current composer protocol rather than a Host/Service risk.

## Status

Slice S1 implementation is complete. No commit, push, PR, merge, review gate, or later gate action was performed.
