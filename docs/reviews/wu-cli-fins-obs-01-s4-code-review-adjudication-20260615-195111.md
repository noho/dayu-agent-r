# WU-CLI-FINS-OBS-01 S4 Code Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S4-cli-fins-live-ui`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-s4-implementation-codex.md`
- Review artifacts:
  - AgentMiMo: `docs/reviews/code-review-20260615-194943.md`
  - AgentDS: `docs/reviews/code-review-20260615-193940.md`

## Review Conclusions

- AgentMiMo: `PASS-WITH-FINDINGS`
- AgentDS: `PASS`

No blocking behavior issue was found. The controller accepts the shared low-severity dead-code finding. The controller also converts MiMo's path-redaction residual risk into a required S4 fix because S4 owns CLI rendering and the approved plan requires bounded output that does not leak absolute paths.

## Accepted Findings

### S4-FIX-01 remove obsolete direct terminal renderer

- Source findings:
  - AgentMiMo `001`.
  - AgentDS low-severity note: unreferenced public dead code.
- Decision: accepted.
- Required fix:
  - Remove `render_fins_direct_terminal_result(...)` and its `__all__` export, unless a direct current caller is found.
  - Do not reintroduce compatibility wrappers or unused public API.

### S4-FIX-02 strengthen embedded absolute path redaction

- Source finding:
  - AgentMiMo residual risk on `_ABSOLUTE_PATH_PATTERN` not matching absolute paths embedded after `=` or other non-whitespace separators.
- Decision: accepted as required defense-in-depth fix.
- Required fix:
  - Update CLI output redaction so absolute paths embedded in text such as `path=/tmp/a`, `key=/Users/a/b`, or `error=C:\tmp\a` are redacted.
  - Add focused tests for progress payload, terminal summary, or failure message rendering that would previously leak embedded absolute paths.
  - Keep output bounded and do not expand S4 into upstream runtime payload changes.

## Deferred / Non-actions

- Stream ending without terminal remains a low-risk residual: `_consume_fins_direct_events(...)` raises `RuntimeError`, and the CLI top-level error path returns failure. No required S4 fix.
- `_FakeFinsDirectService.wait_for_terminal` remains intentionally present in tests for negative assertion that the old path is not called. No required fix.
- S5 logging assembly remains out of scope.

## Required Validation

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q`
- `source .venv/bin/activate && python -m pyright dayu/cli/commands/fins.py dayu/cli/output.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py`
- `git diff --check`

## Controller Decision

S4 enters fix gate for `S4-FIX-01` and `S4-FIX-02`. After AgentCodex applies the focused fixes and validation passes, run scoped re-review against these accepted findings.
