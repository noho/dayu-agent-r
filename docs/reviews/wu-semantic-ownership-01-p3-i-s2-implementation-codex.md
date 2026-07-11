# WU-SEMANTIC-OWNERSHIP-01 P3-I S2 implementation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-I`
- Slice: `S2 - CLI Terminal Cursor After Successful Render`
- Gate: implementation
- Agent: Codex
- Artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`

## First-principles judgment

The motivation is valid. Host and Service already own the terminal facts: status,
terminal event id, event sequence, final answer, error, cancellation and lost
diagnostics. The defect is in the CLI delivery watermark owner: the CLI had already
rendered a terminal but advanced the workspace-local cursor only when renderer exit
code was `0`. That conflated local display delivery with process exit policy and
allowed rendered `FAILED`, `CANCELLED`, and `LOST` terminals to be shown again after
reconnect.

The fix belongs in `dayu.cli.session_execution`, immediately after the render call
returns. It does not belong in Host, Service, outbox, read-model or projection
dedupe.

## Changed files

- `dayu/cli/session_execution.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`

`tests/README.md` was read and not changed. The existing CLI section already covers
CLI terminal cursor store semantics; this slice only adds non-success status cases
inside the same test layer.

## Implementation

- `execute_prompt_on_session(...)` now keeps `terminal is None` as local keyboard
  interrupt with no cursor advancement, then renders the terminal, advances the CLI
  terminal cursor unconditionally after render returns, and finally returns the
  renderer-owned exit code.
- `_run_existing_session_startup_reconnect(...)` now renders each startup terminal,
  advances the cursor after render returns, and only then returns a non-success
  renderer exit code.
- `_run_interactive_repl(...)` now renders through the existing renderer or
  `InteractiveRunView`, advances the cursor after render returns, and only then
  decides whether to return a non-success renderer exit code. `turn_index` advances
  only after cursor advancement on continuing turns.
- No Host or Service terminal status fact was changed. `FAILED`, `CANCELLED`, and
  `LOST` remain their original Host terminal statuses.
- Cursor write exceptions are not caught. They propagate as local CLI delivery
  persistence failures and do not rewrite Host terminal status.

## Tests

Added regression coverage:

- Prompt existing-session path parameterized for `FAILED`, `CANCELLED`, and `LOST`;
  asserts renderer exit code remains policy-owned and cursor records
  `terminal_event_id` / `event_sequence`.
- Prompt local interrupt before accepted Run id; asserts `terminal is None` returns
  local keyboard interrupt and cursor remains empty.
- Interactive startup reconnect parameterized for `FAILED`, `CANCELLED`, and `LOST`;
  asserts cursor advances before renderer exit code drives return.
- Interactive existing-session turn parameterized for `FAILED`, `CANCELLED`, and
  `LOST`; asserts cursor advances after rendering. `FAILED` / `CANCELLED` continue
  to EOF with success, while `LOST` returns failure.

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q`
  - Result: `97 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli -q`
  - Result: `291 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

Warnings are existing third-party `edgar` deprecation warnings from the test
environment.

## Propagation audit

- Fact producer: Host terminal result contains `terminal_status`,
  `terminal_event_id`, and `event_sequence`.
- Service projection: `dayu.service.entrypoint_runtime` continues to return
  `EntrypointRunTerminalResult` without mutating terminal facts.
- CLI display: `dayu.cli.output` or `InteractiveRunView` renders the terminal and
  returns renderer-owned exit code.
- CLI local persistence: `dayu.cli.session_execution` now advances
  `dayu.cli.session_terminal_cursor` after successful render for all terminal
  statuses received by the CLI.
- Reconnect consumer: future interactive startup reconnect reads the cursor and
  `seen_terminal_event_ids` to avoid redisplaying terminals already delivered by
  this CLI process.
- User-visible output: stdout/stderr and exit code remain determined by renderer
  policy. Cursor advancement does not alter Host status, final answer, error,
  cancel reason, lost diagnostic or renderer mapping.

## Residual risks and blockers

- No current-slice blocker remains.
- If cursor persistence fails after render, the exception propagates and the already
  rendered terminal may be displayed again on a later reconnect. This is the planned
  local-delivery tradeoff and is safer than silently losing cursor write failure.
- This slice only handles terminal results that the CLI receives and renders. It
  does not change whether Host or Service produce a terminal result for a given
  `RUN_LOST` scenario.
