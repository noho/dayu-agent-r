# WU-CLI-ACTIVITY-01 CLI implementation artifact

## Gate / scope

- Gate: implementation for remaining CLI slices C/D/E/F.
- Agent: AgentCodex.
- Plan: `docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md`.
- Accepted commits in context: plan `012fee0a`, Slice A `992a641d`, Slice B `152292da`.

Implemented scope:

- CLI activity renderer.
- Prompt submit path consuming Service activity callback.
- Interactive composer wrapper with multiline insertion, history search, external editor binding, and input-state Ctrl+C behavior.
- Interactive submit path consuming Service activity callback.
- README trigger checks and validation cleanup.

Non-goals kept:

- No Host / Engine public contract changes.
- No Host durable internals, EventLog payload, Tool Trace, payload ref / digest, or ToolBundle access from CLI.
- No commit, push, PR, code review, or deepreview gate.

## Changed files

- `dayu/cli/activity.py`
- `dayu/cli/composer.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `tests/cli/test_activity_renderer.py`
- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/README.md`
- `docs/reviews/wu-cli-activity-01-cli-implementation-codex.md`

## Implementation decisions

- Added `CliActivityRenderer`, enabled by default only when stderr is TTY. This keeps non-TTY stderr free of live activity noise and preserves stdout for final answers.
- Renderer consumes only Service `EntrypointActivity` DTOs, dedupes by activity dedupe key, ignores older event sequences, supports hidden state, and emits bounded cancel diagnostics.
- Prompt and interactive submit paths now pass `on_activity=renderer.record` to `submit_entrypoint_turn_and_wait(...)`.
- Existing SIGINT cancel paths now emit bounded renderer cancel messages when the renderer is enabled.
- Added `dayu.cli.composer` as a CLI-only prompt_toolkit wrapper. Command code depends on an `InteractiveComposer` protocol, not prompt_toolkit internals.
- TTY interactive input uses `PromptToolkitInteractiveComposer`; non-TTY and tests use `InputReaderComposer` around the existing input reader.
- Composer key bindings:
  - Ctrl+J inserts a newline into the current draft.
  - Ctrl+R starts prompt_toolkit history search for the current buffer.
  - Ctrl+C clears non-empty drafts and exits with `KeyboardInterrupt` on empty drafts.
  - Ctrl+X Ctrl+E opens prompt_toolkit's external editor; startup failure is bounded to stderr.
- Interactive final answer rendering still happens after the per-run renderer closes, keeping each turn's terminal output readable before the next prompt.

## README decision

- Read `dayu/README.md` Agent update constraints. No update was needed because this implementation does not change cross-package architecture or stable public boundary; it implements CLI-internal consumption of the existing Service activity callback.
- Read `dayu/service/README.md`. No update was needed because no Service code changed in this gate.
- Updated `tests/README.md` because new CLI renderer/composer tests and prompt/interactive activity assertions were added.

## Tests / validation

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py -q`
  - Result: 85 passed, 3 existing third-party edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov-fail-under=80 -q`
  - Result: 10 passed, 3 existing third-party edgar deprecation warnings.
  - Coverage: `dayu/cli/activity.py` 87%, `dayu/cli/composer.py` 94%, total 89%.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings, 0 informations. Pyright reported a newer version is available.
- `git diff --check`
  - Result: clean.

## Residual risks

- Automated tests validate prompt_toolkit key binding behavior through focused handler tests, but no manual TTY smoke was run in a real terminal.
- The running-state visibility toggle is implemented as renderer state and covered at renderer level; this pass does not add a raw-terminal key listener for prompt/interactive running state. The current cancel integration remains SIGINT-based, matching existing command architecture.
- Dynamic stderr rendering is intentionally line-oriented rather than full-screen. This avoids terminal control complexity but is less polished than a future TTY-specific dynamic region.
