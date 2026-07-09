# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: implementation review adjudication and fix
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-review-ds.md`

## Review Verdicts

- AgentMiMo: `pass-with-findings`
- AgentDS: `pass-with-findings`

No blocking finding was reported. Controller accepted two low-severity findings for current fix because both were small, same-owner, and reduced semantic drift without expanding P2-A scope.

## Findings Adjudication

| Finding | Source | Controller decision | Resolution |
|---|---|---|---|
| session generic `HostApiError` catch does not use full helper | MiMo F-1 | Not accepted for current fix | It is not a `HostApiError` presentation path and does not duplicate Host error code/message mapping. No current P2-A owner-boundary bug. |
| tests call `session_execution` private state-machine helpers | MiMo F-2 / DS F3 | Not accepted for current fix | Same-owner implementation tests do not recreate the original cross-command private import bug. Reviewers agreed this is acceptable residual test coupling. |
| `session.py` depends on prompt/interactive usage error classes | DS F1 | Accepted | Added CLI public `CliUsageError` base and changed `session.py` to catch the public base for prompt/interactive compatible usage errors. |
| CLI cancellation path constructs `FinsResultSummary` | DS F2 | Accepted | Replaced local cancel summary with CLI-private `_CliDirectLocalExit`, carrying only `exit_code`. CLI no longer constructs Fins business DTO for local cancellation. |
| prompt/interactive submit-stage `HostApiError` lacks direct integration test | DS residual | Not accepted for current fix | Existing session-resume submit error tests cover the submit-side HostApiError mapping. Prompt/interactive create-stage tests cover entry command presentation. No accepted P2-A gap. |
| `_resume_host_error_message` uses `host_api_error_context` rather than full formatter | DS info | Not accepted for current fix | It intentionally adds selector/session context while reusing the shared HostApiError core formatter. No duplicate Host code/message owner. |

## Fix Summary

- Added `dayu.cli.errors.CliUsageError` as CLI public usage-error base.
- Changed `CliCommandUsageError`, `CliInteractiveUsageError`, and `CliSessionUsageError` to inherit `CliUsageError`.
- Changed `session.py` top-level handling to catch `CliSessionUsageError` for session-local usage errors and `CliUsageError` for compatible prompt/interactive resume usage errors, without importing prompt/interactive exception classes.
- Changed Fins direct local SIGINT path from a fabricated `FinsResultSummary(CANCELLED, ...)` to CLI-private `_CliDirectLocalExit(exit_code=EXIT_KEYBOARD_INTERRUPT)`.
- Updated Fins direct tests to assert local cancellation is a CLI local exit, while terminal result races still return real `FinsResultSummary`.

## Validation After Fix

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_import_boundary.py`
  - Result: `129 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `source .venv/bin/activate && pytest tests/cli/test_runtime_display.py tests/cli/test_arg_parsing.py tests/cli/test_session_terminal_cursor.py tests/cli/test_activity_renderer.py tests/service/test_fins_direct.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py`
  - Result: `156 passed, 3 warnings`

## Next Gate

Dispatch AgentMiMo and AgentDS implementation re-review. Re-review must confirm DS F1 and DS F2 are closed and that no new P2-A blocking finding was introduced by the review fix.
