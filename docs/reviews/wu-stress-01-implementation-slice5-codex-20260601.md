# WU-STRESS-01 Slice 5 Implementation Artifact

## Scope

- Role: AgentCodex implementation specialist.
- Slice: Slice 5, mixed Host stress with deterministic fault injection.
- Design source: `docs/host/design.md`.
- Plan source: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`.

## Changed Files

- `tests/host/stress_support.py`
  - Added `HostStressScenario`, a typed frozen dataclass for fixed mixed stress parameters.
- `tests/host/test_host_production_stress.py`
  - Added `Slice5MixedHostDiagnostics`.
  - Added `test_mixed_host_stress_deterministic_fault_injection`.
  - Added `_slice5_timeout_summary` so internal deadline failures include summary JSON.
- `docs/reviews/wu-stress-01-implementation-slice5-codex-20260601.md`
  - This implementation artifact.

## Behavior Proof

- Scenario is deterministic: 3 sessions, 5 runs per session, 15 total runs, no random input.
- Fault script covers:
  - final answer,
  - failed engine event,
  - queued cancel,
  - active cancel,
  - stream exception to `LOST`,
  - owner crash/recovery,
  - secondary watcher disconnect/reconnect.
- Primary watchers are attached for the live mixed flow and consume terminal events throughout.
- Secondary watcher disconnects after the first session-0 terminal, reconnects, and observes the post-reconnect terminal.
- Summary assertions cover:
  - `session_count == 3`,
  - `run_count == 15`,
  - `crash_count >= 1`,
  - `recovery_count == crash_count`,
  - watch lag samples and final drain,
  - `scheduler_drained`,
  - `liveness_stale_detected`,
  - `terminal_duplicate_count == 0`,
  - `terminal_dedupe_ok`.
- All final assertion failures use `summary_to_json(summary)` as the assertion message.
- Internal `TimeoutError` from deterministic wait helpers is converted to `AssertionError` with summary JSON.

## Validation Results

All commands were run with `source .venv/bin/activate`.

- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k mixed_host_stress -q`
  - Passed: `1 passed, 4 deselected`.
- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`
  - Passed: `5 passed`.
- `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - Passed: `25 passed`.
- `python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`.

## Docs Decision

`tests/README.md` was not changed because Slice 5 did not alter the stress marker, command surface, default exclusion behavior, or summary schema.

## Residual Risks

- `pytest-timeout` can still terminate the whole test if the event loop is globally wedged before internal deadlines execute; the test uses shorter explicit deadlines for normal controlled waits.
- The crash/recovery terminal can occur before primary watcher attach during Host startup recovery. The Slice 5 watch lag diagnostic therefore baselines pre-attach terminal count and measures drain for the live mixed flow after watcher attachment.
