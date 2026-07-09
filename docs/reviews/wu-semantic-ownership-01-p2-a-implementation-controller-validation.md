# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: implementation validation before review
- Accepted plan commit: `38477f63`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-codex.md`

## Motivation Check

P2-A remains valid.

- `session resume` previously imported prompt / interactive private helpers, so existing-session execution composition had no CLI public owner.
- Fins direct CLI previously manufactured a local missing-result failure event even though Service owns normal missing-result fallback.
- CLI `HostApiError` presentation and exit-code mapping were split across session / prompt / interactive paths.

The implementation addresses those root causes at CLI public helper, Service/CLI contract boundary, and CLI presentation boundary respectively.

## Owner Boundary Check

- `dayu.cli.session_execution` now owns existing-session runtime prepare, Host submit/watch/cancel composition, startup reconnect, REPL execution composition, and command execution identity.
- `dayu.cli.commands.prompt` and `dayu.cli.commands.interactive` retain command-local parameter validation, Session ensure/create, and context slot construction.
- `RuntimeDisplayController` remains the owner of thinking/activity cleanup lifecycle; `session_execution` calls it but does not replace its display semantics.
- Service remains the owner of normal Fins direct missing-result fallback; CLI now raises `FinsDirectStreamContractViolation` when the Service stream contract is broken.
- `dayu.cli.host_api_errors` owns only CLI stderr text and exit-code mapping for `HostApiError`.

## Static Checks

- AST import-boundary test added for `session.py` imports from prompt / interactive command modules.
- Controller scan found no CLI `_missing_result_event` or CLI fake missing-result failure RESULT.
- Controller scan found no new `Any`, `object`, `hasattr`, `getattr`, `type: ignore`, or pyright suppression in touched production CLI files.
- Remaining `_missing_result_event` symbols are in Service/Fins upstream owners, not CLI downstream presentation.

## Validation Commands

- `source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py`
  - Result: `128 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli/test_import_boundary.py`
  - Result: `1 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `source .venv/bin/activate && pytest tests/cli/test_runtime_display.py tests/cli/test_arg_parsing.py tests/cli/test_session_terminal_cursor.py tests/cli/test_activity_renderer.py tests/service/test_fins_direct.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py`
  - Result: `156 passed, 3 warnings`

## README Check

- `tests/README.md` was updated because CLI test coverage facts changed.
- Root `README.md`, `dayu/README.md`, `dayu/host/README.md`, `dayu/engine/README.md`, and `dayu/fins/README.md` were not triggered by this implementation.

## Review Focus

Reviewers should specifically verify:

- The shared `session_execution` module is a real semantic owner, not a facade over prompt / interactive command modules.
- Tests that still exercise `dayu.cli.session_execution` private state-machine helpers are acceptable as same-owner implementation tests and do not reintroduce the original cross-command private import problem.
- `session resume` context slot construction remains command-semantic and does not cause prompt / interactive slot drift.
- `HostApiError` exit-code policy matches the accepted plan, especially explicit session id `NOT_FOUND` vs label TOCTOU `NOT_FOUND`.
- Fins direct missing-result behavior no longer projects a fake business failure fact from CLI.

## Controller Verdict

Implementation is ready for AgentMiMo / AgentDS review.
