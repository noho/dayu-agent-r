# WU-CLI-ACTIVITY-01 Interactive Composer Async Fix

## Root Cause

`dayu-cli interactive` runs inside `asyncio.run(...)`. The TTY composer called
`PromptSession.prompt(...)`, and prompt_toolkit starts its own event loop for that
synchronous API. In a running event loop this fails with:

```text
asyncio.run() cannot be called from a running event loop
```

## Fix

- Changed `InteractiveComposer.read(...)` to an async protocol.
- Changed `PromptToolkitInteractiveComposer.read(...)` to await
  `PromptSession.prompt_async(...)`.
- Changed `InputReaderComposer.read(...)` to keep the old input reader semantics
  behind the same async interface.
- Updated interactive REPL to `await effective_composer.read(...)`.
- Added a regression test that replaces the prompt_toolkit session with a fake
  object whose synchronous `prompt(...)` raises, proving the TTY composer uses
  `prompt_async(...)`.

## Validation

- `pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py -q`
  - Result: 30 passed, 3 third-party edgar deprecation warnings.
- `pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py tests/cli/test_run_keys.py -q`
  - Result: 66 passed, 3 third-party edgar deprecation warnings.
- `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q`
  - Result: 18 passed, total coverage 90.25%.
- `python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors.
- `git diff --check`
  - Result: clean.
