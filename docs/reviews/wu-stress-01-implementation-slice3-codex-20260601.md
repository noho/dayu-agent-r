# WU-STRESS-01 Slice 3 Implementation Artifact

## Scope

- Role: AgentCodex, Slice 3 implementation specialist.
- Slice: Sustained watch stress with slow consumer and reconnect.
- Constraints honored: no production code changes, no `pyproject.toml`, no root README, no Host design/control doc changes, no commit, no push, no PR.

## Changed Files

- `tests/host/stress_support.py`
  - Added watch stress helpers:
    - `consume_terminals`
    - `close_host_event_iterator`
    - `read_latest_event_sequence`
    - `read_event_log_count`
    - `read_session_terminal_sequences`
  - Reused and kept the existing `compute_watch_lag`.
  - Extended `DeterministicStressWorkerFactory` with `enqueue_run_behavior` so tests can assign the next accepted run behavior without relying on run id before public submit returns.

- `tests/host/test_host_production_stress.py`
  - Added `test_sustained_watch_slow_consumer_reconnect_stress`.
  - Added Slice 3 typed diagnostics and local helper functions for public submit/cancel/wait, lag sampling, outbox gap proof, and terminal coverage checks.

- `docs/reviews/wu-stress-01-implementation-slice3-codex-20260601.md`
  - This implementation artifact.

## Implemented Plan Items

- Created a sustained watch stress scenario with 3 sessions and 18 deterministic runs.
- Mixed terminal outcomes across final, failed, and cancelled runs.
- Kept primary session watchers attached for the full scenario and consumed them slowly to create measurable watch lag.
- Attached a secondary watcher, consumed initial terminals, closed it, submitted additional terminal runs during the disconnect window, then reattached and verified a newly submitted terminal was observable.
- Did not require public watcher replay across the disconnect gap.
- Proved disconnect-window terminal facts using primary watcher coverage, public `get_run` terminal snapshots, public outbox read, and durable terminal diagnostics.
- Implemented consumer cancel verification in the required four steps:
  - fresh EventLog count before consumer cancel;
  - consumer task cancel;
  - public `get_run` confirms the active run remains non-terminal and worker handle received no cancel;
  - fresh EventLog count remains unchanged, then releasing the worker produces a normal succeeded terminal.
- Built `HostStressSummary` with `watch_lag_samples`, terminal duplicate count, scheduler drain, and failure boundary diagnostics.
- Asserted `terminal_duplicate_count == 0`.
- Asserted final watch lag drains to `0` and max lag remains below the final EventLog sequence.

## Validation

Commands run with `source .venv/bin/activate`:

- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q`
  - Result: passed, `1 passed, 2 deselected`.
- `pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q`
  - Result: passed, `20 passed`.
- `python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.

Additional checks:

- `python -m compileall -q tests/host/stress_support.py tests/host/test_host_production_stress.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Docs Decision

- `tests/README.md` was not changed.
- Reason: Slice 3 did not change the stress marker, stress command, default exclusion policy, or test-running contract. The required command already existed from earlier slices.

## Plan Gaps

- No public watcher replay cursor was added or required.
- Reconnect semantics remain limited to observing terminals submitted after the second attach, consistent with the accepted plan and current public contract.
- The disconnect-window proof uses public outbox plus durable diagnostics rather than a replayed watch stream, also consistent with the accepted plan.

## Residual Risks

- The stress scenario is deterministic and intentionally small. It validates the Host watch/reconnect/cancel invariants under sustained local pressure, but it is not a randomized fuzz or slow-disk stress test.
- Watch lag is diagnostic, not a production SLO. The test asserts bounded lag and final drain for this scenario only.

## Stop Status

- Slice 3 implementation complete.
- No stop condition triggered.
- No Slice 4 or Slice 5 implementation performed.
