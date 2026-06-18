# WU-CLI-ACTIVITY-01 PR Review Fix — AgentCodex

## Scope

- PR: https://github.com/noho/dayu-agent-r/pull/149
- Review artifacts:
  - `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`
  - `docs/reviews/wu-cli-activity-01-pr-review-ds-20260618.md`

## Changes

- Extracted duplicated async task cleanup helper from `prompt.py` and `interactive.py` into `dayu.cli.agent_entrypoint.cancel_and_await_task(...)`.
- Updated `README.md` to document `prompt --detail / --no-detail`, including default `--no-detail` behavior and one command example.
- Recorded DS-observed pre-existing smoke-test failures as a deferred residual in `docs/host/issues-implementation-control.md`.
- PR body will be updated after this fix commit is pushed so the GitHub description matches the full PR scope.

## Validation

- `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q`
  - 114 passed, 3 third-party edgar deprecation warnings
- `python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `rg -n "def _cancel_and_await_task|_cancel_and_await_task" dayu/cli`
  - no matches

## Residual Risk

- PR body scope update is pending until after push.
- DS identified two pre-existing smoke failures on `main`; tracked as `WU-CLI-ACTIVITY-01-PR-R1` and not treated as a WU-CLI-ACTIVITY-01 blocker.
