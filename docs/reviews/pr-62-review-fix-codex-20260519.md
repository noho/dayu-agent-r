# PR 62 Review Fix — AgentCodex

## Changed Files

- `tests/host/public_smoke_support.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/README.md`
- `docs/reviews/phase10-5-aggregate-deepreview-controller-adjudication-20260518.md`
- `docs/reviews/phase10-5-aggregate-rereview-controller-adjudication-20260518.md`
- `docs/reviews/phase10-5-slice6-implementation-codex-20260518.md`
- `docs/reviews/pr-62-review-fix-codex-20260519.md`

No production code was changed.

## Fix Summary

PR62-F1:

- Removed duplicated `_event_type_count` / `_wait_for_event_type_count` implementations from public smoke files.
- Replaced lifecycle / replay correctness assertions with public `get_run(...)` snapshots and worker observable assertions.
- Centralized the remaining `ATTEMPT_RUNNING` wait in `public_smoke_support.py` as `wait_for_diagnostic_event_type_count(...)`, with a Chinese comment stating it is only a test synchronization primitive, not a correctness assertion.
- Changed `test_public_cancel_session_runs.py` event count helper away from direct SQLite `event_log` SQL to existing `EventLogStore` reads for its lower-level command-facade idempotency checks.

PR62-F2:

- Removed `create_host_command_handle` usage from `test_public_steer.py` and `test_public_resolve_wait_resume.py`.
- Added `AwaitingThenFinalWorkerFactory`, waiting mock tool options, and `wait_for_public_waiting_run(...)` in `public_smoke_support.py`.
- WAITING smoke setup now goes through `open_host(options)` + public `submit_followup(...)` + ToolRuntime awaiting accept path, then verifies public `submit_followup(steer)` / `resolve_wait(...)` behavior.

PR62-F3:

- Removed trailing whitespace from the committed review artifacts reported by `git diff --check main...HEAD`.
- Current working tree diff is whitespace-clean by `git diff --check` and `git diff --check main`.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_retry_replay.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py -q`
  - `22 passed in 0.70s`
- `source .venv/bin/activate && pytest tests/host/test_package_exports.py -q`
  - `8 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/host -q`
  - `696 passed, 1 skipped in 45.60s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed
- `git diff --check main`
  - passed
- `git diff --check main...HEAD`
  - still reports the pre-existing committed trailing whitespace, because this handoff explicitly forbids committing and that command compares `main` to committed `HEAD`, not to the current working tree.

## Remaining Risks

- The exact required `git diff --check main...HEAD` command cannot become clean until the whitespace cleanup is included in a commit. The current uncommitted working tree is clean relative to `main`.
- `wait_for_public_waiting_run(...)` reads the active wait record id after public `get_run(...)` observes `WAITING`, because the public HostEvent / RunSnapshot surface does not expose `wait_id`. The helper is confined to public smoke support and is not used as a correctness assertion.
