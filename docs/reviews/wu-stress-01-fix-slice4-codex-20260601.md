# WU-STRESS-01 Slice 4 Focused Fix Artifact

## Scope

- Applied the controller adjudication fixes for Slice 4 only.
- Did not modify production code, Host design/control docs, commits, push, PR, or Slice 5 behavior.
- Changed files:
  - `tests/host/stress_support.py`
  - `tests/host/test_host_production_stress.py`
  - `docs/reviews/wu-stress-01-implementation-slice4-codex-20260601.md`
  - `docs/reviews/wu-stress-01-fix-slice4-codex-20260601.md`

## Fixes

- Made the `RUN_LOST` count-level dedupe proof explicit in Chinese docstrings:
  - `terminal_event_count_for_runs()` now documents why `RUN_LOST` is counted separately from `terminal_events_for_runs()`.
  - `Slice4SchedulerLivenessDiagnostics.terminal_dedupe_ok` documents the two-layer proof.
- Removed unused `InspectableStressWorkerFactory.wait_accepted_run`.
- Moved Slice 4 terminal count ownership into `tests/host/stress_support.py`, so the test file no longer duplicates DB filename or terminal event type constants.
- Added `run_lost_event_count()` to avoid copying the `RUN_LOST` event type constant into the test file.
- Changed `verify_lane_released()` to accept an explicit `lane_db_path` and updated the call site to pass `options.lane_db_path`.
- Documented the stale heartbeat threshold as a test diagnostic used only after the stress helper creates stale evidence; it does not replace Host recovery policy.
- Clarified `_is_terminal_status()` as Host public Run terminal semantics, including `LOST`, separate from `HostEventKind` / `HostTerminalStatus` terminal observation semantics.

## Validation

Passed:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
python -m pyright dayu/ tests/ utils/
```

Observed results:

- Slice 4 targeted stress: `1 passed, 3 deselected`.
- Full Host production stress file: `4 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.

The required regression command:

```bash
pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
```

hit the known isolated failure mentioned by the controller:

- `tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`
- failure mode: lane acquire timeout drove the seeded Run to `FAILED` instead of the assertion's expected `RUNNING`.
- command result: `1 failed, 74 passed`.

Single-test rerun evidence:

```bash
pytest tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering -q
```

passed with `1 passed`.

## Residual Risks

- The Slice 4 stress remains deterministic and bounded, not a randomized fuzz or long-duration soak.
- The liveness stale diagnostic is intentionally test-scoped; production recovery truth remains startup scanner classification plus durable EventLog facts.
- `RUN_LOST` still has no public `HostTerminalStatus`, so the proof intentionally stays split between public terminal observations and EventLog count diagnostics.

## Tiny Docstring Follow-up

- Updated `InspectableStressWorkerFactory` class docstring so it only describes the current aggregate diagnostics: accepted handle count, worker cancel count, and handle close count.
- No production code, control doc, commit, push, PR, or Slice 5 work was performed.

Validation for this follow-up:

```bash
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
python -m pyright dayu/ tests/ utils/
```

Observed results:

- Slice 4 targeted stress: `1 passed, 3 deselected`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
