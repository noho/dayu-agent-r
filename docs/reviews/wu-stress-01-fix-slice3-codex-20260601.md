# WU-STRESS-01 Slice 3 Fix Artifact

## Changed Files

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `docs/reviews/wu-stress-01-fix-slice3-codex-20260601.md`

## Fixes

- Replaced all Slice 3 post-submit `set_run_behavior(...)` usage with pre-submit scripted behavior via `_submit_scripted_followup(...)`.
- Adjusted the Slice 3 scenario ordering so scripted failed runs are submitted only when the next accept belongs to that run, avoiding cross-session consumption of queued behavior.
- Updated `DeterministicStressWorkerFactory.behavior_for_run` docstring to document lookup order: explicit run behavior, pre-submit next-accept behavior, then default behavior.
- Updated `close_host_event_iterator` docstring to state that the helper mirrors recovery test cleanup semantics but is stress-local, not a compatibility wrapper and not a production lifecycle abstraction.
- Replaced hard-coded reconnect/gap thresholds with named constants:
  - `_SLICE3_SECONDARY_FIRST_TERMINAL_COUNT`
  - `_SLICE3_SECONDARY_RECONNECT_TERMINAL_COUNT`
  - `_SLICE3_DISCONNECT_GAP_RUN_COUNT`
  - `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT`
- Reworked gap diagnostics:
  - `outbox_gap_coverage_ok` checks only Outbox coverage and maps to `failure_boundary="projection"`.
  - `disconnect_gap_terminal_truth_ok` checks primary watcher, public snapshot, durable terminal observation and Outbox coverage for the disconnect-window runs.
- Reworked watch lag diagnostics to preserve per-session samples in `Slice3WatchDiagnostics.watch_lag_samples_by_session`.
- Flattened watch lag samples only when populating `HostStressSummary.watch_lag_samples`.
- Changed per-session lag measurement to terminal-count watermarks so one session's global EventLog sequence gaps do not inflate another session's lag.
- Removed redundant `tuple([...])` forms in the Slice 3 path.

## Validation

Commands run with `source .venv/bin/activate`:

- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q`
  - Result: passed, `1 passed, 2 deselected`.
- `pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q`
  - Result: passed, `20 passed`.
- `python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.

Additional check:

- `git diff --check`
  - Result: passed.

## Residual Risks

- The stress scenario remains deterministic and intentionally bounded. It proves the accepted Slice 3 watch/reconnect/cancel invariants but is not randomized fuzzing.
- Per-session watch lag is a test diagnostic based on terminal-count watermarks, not a production replay cursor or public watch SLO.

## Final Focused Fix

- Updated `consumer_cancel_ok` docstring so it describes the actual diagnostics predicate: EventLog count stability and absence of worker cancel notification. The public `get_run` non-terminal check and release-to-terminal check remain explicit assertions in the test body.
- Added `expected_reconnect_run_id` to `Slice3WatchDiagnostics` and made `reconnect_ok` require the secondary reconnect watcher to observe that exact Run id.
- Added an explicit assertion immediately after collecting `secondary_reconnect_events` that the reconnect watcher observed `reconnect_run_id`.
- Tracked `primary_watchers_closed` so primary watchers are closed once in the normal path, and the `finally` block only performs fallback cleanup for watchers not already closed.
- Replaced the cross-session lag bound with `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION`.

## Final Focused Fix Validation

Commands run with `source .venv/bin/activate`:

- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q`
  - Result: passed, `1 passed, 2 deselected`.
- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`
  - Result: passed, `3 passed`.
- `pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q`
  - Result: passed, `20 passed`.
- `python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
