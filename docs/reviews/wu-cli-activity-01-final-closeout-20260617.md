# WU-CLI-ACTIVITY-01 Final Closeout

## Scope

- Work unit: `WU-CLI-ACTIVITY-01`
- Issue: GitHub Issue #144
- Branch: `wu-cli-activity-01`
- Design source: `docs/host/design.md`, `docs/engine/design.md`
- Plan: `docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md`

## Accepted Commits

- Plan: `012fee0a`
- Slice A Host public activity event contract: `992a641d`
- Slice B Service activity callback: `152292da`
- CLI slices C/D/E/F activity renderer, composer, run keys, docs/tests: `1a6f4bb2`

## Delivered

- `watch_session_events(session_id)` now preserves Host public event identity with `event_class`, `event_type`, and safe `activity`.
- Host activity projection is driven by EventLog facts and Host-owned tool display metadata, not Tool Trace, logs, or CLI internals.
- Service entrypoint runtime exposes typed `EntrypointActivity` callback and forwards only Host public activity or bounded local watcher diagnostics.
- `dayu-cli prompt` and `dayu-cli interactive` render TTY activity to stderr while keeping final answers on stdout.
- Running-state Ctrl+T toggles activity visibility; Esc requests cancel; Ctrl+C cancel / repeated Ctrl+C local exit semantics are covered.
- Interactive composer supports Ctrl+J multiline draft insertion, Ctrl+R history search, Ctrl+C draft clear / exit, and Ctrl+X Ctrl+E external editor.

## Reviews

- Slice A review / re-review passed.
- Slice B review / fix / re-review passed.
- CLI review / fix / targeted re-review passed.
- Aggregate deepreview passed:
  - `docs/reviews/deepreview-wu-cli-activity-01-aggregate-mimo-20260617-153030.md`
  - `docs/reviews/deepreview-wu-cli-activity-01-aggregate-ds-20260617-151950.md`

## Final Validation

- `pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q`
  - Result: 179 passed, 3 third-party edgar deprecation warnings.
- `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q`
  - Result: 17 passed; total coverage 89.53%.
- `python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors.
- `git diff --check`
  - Result: clean.

## Residual Risk

- No open residual risk remains for this work unit.
- Known low residual: Esc is recognized as a single byte in running state, so terminal escape sequences that begin with ESC can be interpreted as cancel. This is recorded as accepted behavior for the current requirement.
- Manual real-terminal smoke was not run; pseudo-terminal tests cover cbreak read and terminal mode restoration.

## Closeout

Local work unit gate is complete and ready for draft PR creation when requested.
