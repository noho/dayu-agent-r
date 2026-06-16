# WU-CLI-FINS-DIAG-01 Implementation — Codex

## Gate Metadata

- Gate: implementation
- Work unit: `WU-CLI-FINS-DIAG-01`
- Scope: close `WU-CLI-FINS-OBS-01-R3` and `WU-CLI-FINS-OBS-01-R5`
- Design truth: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- Date: 2026-06-16

## First-Principles Judgment

R3 and R5 are valid residuals.

- R5 root cause was runtime logging channel policy: `dayu.runtime.log` installed its marker handler on stdout, so CLI diagnostics shared the command-result/UI channel.
- R3 root cause was presentation-layer over-redaction: `dayu/cli/output.py` treated absolute paths as secrets, although this work unit's sensitive-data policy only treats resolved API keys / known secrets as concrete secrets.
- Fins direct diagnostic logs were too sparse for troubleshooting because `_log_fins_direct_event_received(...)` only logged operation, event type and result status.

This implementation intentionally does not change issue #144 activity UI, issue #145 session management, Engine/provider diagnostic redaction, diagnostic artifacts, Host durable/EventLog/Tool Trace contracts, or `dayu/fins/direct_events.py`.

## Changed Files

### Runtime / CLI Diagnostic Stream

- `dayu/runtime/log.py`
  - Added `stream: TextIO | None = None` to `configure(...)` and `set_level_from_flags(...)`.
  - Default diagnostic stream is current `sys.stderr`.
  - Kept explicit stream override.
  - Renamed private marker value from `dayu.runtime.log:stdout` to `dayu.runtime.log:diagnostic`.
- `dayu/cli/main.py`
  - CLI composition root now explicitly passes `stream=sys.stderr`.

### Fins Output Policy

- `dayu/cli/output.py`
  - Removed presentation-layer absolute path redaction from `_safe_text_value(...)`.
  - Kept bounded text truncation and JSON string rendering.
  - Did not change `dayu/fins/direct_events.py` path validation.

### Fins Direct Diagnostics

- `dayu/cli/commands/fins.py`
  - Enriched VERBOSE diagnostics with bounded operation, event type, ticker, document label, progress stage, result status and message.
  - Enriched DEBUG diagnostics with bounded filing kind, progress counts, result title, error kind, exit code and result details.
  - Logs still pass scalar strings to logging; no raw event object, raw payload, job id, sidecar cursor, durable cursor or artifact ref is logged.

### Tests

- `tests/runtime/test_log.py`
  - Updated marker expectation and stderr assertions.
  - Added stream override regression.
- `tests/cli/test_arg_parsing.py`
  - Verifies CLI main passes `sys.stderr` to runtime log assembly.
- `tests/cli/test_prompt_command.py`
  - Added `--verbose` / `--debug` stdout cleanliness regression.
- `tests/cli/test_interactive_command.py`
  - Added `--verbose` / `--debug` stdout cleanliness regression.
- `tests/cli/test_fins_commands.py`
  - Updated verbose/debug diagnostics to stderr.
  - Verifies stdout remains Fins progress/result UI.
  - Verifies absolute POSIX and Windows paths remain visible while long values are truncated.
  - Verifies enriched diagnostics include bounded useful summaries and omit job/sequence/cursor/artifact identifiers.

### Docs

- `dayu/README.md`
  - Recorded the implemented runtime/CLI stderr diagnostic channel and stdout UI/result channel boundary.
- `tests/README.md`
  - Updated CLI/runtime test coverage descriptions.
- `docs/host/issues-implementation-control.md`
  - Removed R3/R5 from active residuals and recorded `WU-CLI-FINS-DIAG-01` as completed in the current control state.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q
```

Result: 120 passed, 3 warnings. Warnings are edgar dependency deprecations.

Passed:

```bash
source .venv/bin/activate && pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/output.py dayu/cli/commands/fins.py tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
```

Result: 0 errors, 0 warnings, 0 informations.

## README Decision

- `dayu/README.md` updated because runtime/CLI logging channel behavior is a cross-package logging contract.
- `tests/README.md` updated because CLI/runtime tests changed their documented coverage.
- No `dayu/engine/README.md`, `dayu/host/README.md`, `dayu/fins/README.md` or `dayu/config/README.md` update was needed because no production code in those package boundaries changed.

## Residual Risks

- Engine/provider diagnostic redaction remains broader than the current R3 user裁决. Classification: assigned to a later Engine/provider diagnostic work unit because this implementation deliberately did not change provider diagnostic payload contracts.
- Prompt/interactive activity readability remains outside this work unit. Classification: tracked by existing issue #144.
- CLI session management remains outside this work unit. Classification: tracked by existing issue #145.
- Fins event messages/details are trusted to remain free of resolved API key values through upstream event construction and existing diagnostic secret policy. Classification: residual assumption retained; no direct code evidence in this implementation showed resolved API keys entering Fins direct event fields.

## Completion Status

Implementation gate completed locally. No commit, push, PR, diagnostic artifact feature, Host durable/EventLog/Tool Trace change, Engine/provider redaction change, or `direct_events.py` change was performed.
