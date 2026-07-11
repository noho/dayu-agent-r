# WU-SEMANTIC-OWNERSHIP-01 P3-I S2 Fix Report

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-I`
- Slice: `S2 CLI Terminal Cursor After Successful Render`
- Findings fixed:
  - DS-F1: interactive `terminal is None` path lacked explicit cursor non-advancement assertion.
  - DS-F2: cursor write failure propagation path lacked tests.

## Changes

- `tests/cli/test_interactive_command.py`
  - Added `CliTerminalCursorError` import and a test helper that raises cursor persistence failure from `session_execution.advance_cli_terminal_cursor`.
  - Added startup reconnect cursor write failure propagation test.
  - Added interactive turn cursor write failure propagation test.
  - Extended `test_interactive_repl_returns_130_on_second_sigint` to assert cursor remains at `OutboxTerminalCursor(event_sequence=0)` with no seen terminal ids.

- `tests/cli/test_prompt_command.py`
  - Added `CliTerminalCursorError` import and a test helper that raises cursor persistence failure from `session_execution.advance_cli_terminal_cursor`.
  - Added prompt cursor write failure propagation test.

## Propagation Audit

- Host/Service terminal facts remain unchanged and are still consumed as the source of truth.
- CLI render still happens before cursor persistence.
- Cursor persistence failure remains uncaught by prompt, startup reconnect, and interactive turn paths; the local CLI delivery persistence error wins over returning the renderer exit code.
- `terminal is None` remains a local interrupt path without a terminal event; no cursor advancement occurs.
- Durable cursor state and rendered terminal facts stay derived from the same terminal event id and event sequence.

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q`
  - Result: `100 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli -q`
  - Result: `294 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Residual Risk

- Cursor write failure after render may cause the same already-rendered terminal to be shown again on a later reconnect. This is the planned local delivery trade-off and remains preferable to silently pretending the delivery cursor was persisted.
