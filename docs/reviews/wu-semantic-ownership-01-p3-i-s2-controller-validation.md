# WU-SEMANTIC-OWNERSHIP-01 P3-I S2 controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Slice: `S2 - CLI Terminal Cursor After Successful Render`
- Gate: controller validation before code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`

## Controller scope audit

S2 changed only the CLI display-delivery boundary and focused CLI tests:

- `dayu/cli/session_execution.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`

No Host, Service, Engine, Outbox/read-model/projection, S1 public entrypoint, or README files were changed.

## Validation

Commands run by controller:

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q
```

Result: `97 passed, 3 warnings`.

```bash
source .venv/bin/activate && pytest tests/cli -q
```

Result: `291 passed, 3 warnings`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed with no output.

Warnings are third-party `edgar` deprecation warnings already present in this test environment.

## Behavior audit

- Prompt path:
  - `terminal is None` still returns local keyboard interrupt and does not advance cursor.
  - `FAILED`, `CANCELLED`, and `LOST` terminal results are rendered, then cursor is advanced, then renderer-owned exit code is returned.
- Interactive startup reconnect:
  - Each terminal result is rendered, then cursor is advanced, then non-success renderer exit code can stop startup.
- Interactive turn:
  - Terminal result is rendered through the selected renderer/view, then cursor is advanced, then non-success renderer exit code can end the REPL.
  - `turn_index` advances only after cursor persistence for continuing turns.
- Cursor write failures remain uncaught local CLI delivery persistence failures.

## Propagation audit

- Fact producer: Host / Service terminal facts (`terminal_status`, `terminal_event_id`, `event_sequence`, final answer/error/cancel/lost details) remain unchanged.
- Projection owner: CLI renderers still own stdout/stderr and process exit-code mapping.
- Local delivery owner: `dayu.cli.session_execution` now writes `dayu.cli.session_terminal_cursor` after successful terminal rendering for every terminal status received by CLI.
- Reconnect consumer: startup reconnect reads the saved cursor and seen event ids to avoid redisplaying already rendered terminal items.
- User-visible output: terminal status, final answer, error message, cancel reason, lost diagnostic, and exit code remain renderer/Host facts; cursor advancement does not rewrite them.

## Residual risk

- If cursor persistence fails after render, the already rendered terminal can reappear on a later reconnect. This is the accepted local-delivery tradeoff from the plan and is preferable to hiding a failed cursor write.
- This slice only handles terminal results the CLI actually receives and renders. It does not change whether Host/Service emit a terminal result for a given `RUN_LOST` scenario.

## Decision

S2 is ready for AgentMiMo and AgentDS code review.
