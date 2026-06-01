# WU-STRESS-01 Slice 4 Implementation Artifact

## Scope

- Implemented only approved Slice 4 scheduler / liveness stress coverage.
- Did not modify production code, Host design/control docs, commits, push, PR, or Slice 5 behavior.
- Changed files:
  - `tests/host/stress_support.py`
  - `tests/host/test_host_production_stress.py`
  - `docs/reviews/wu-stress-01-implementation-slice4-codex-20260601.md`

## Behavior Proof

- Added `InspectableStressWorkerFactory` for test-only accepted snapshot, handle close, cancel, and release-gate diagnostics.
- Added `wait_all_runs_terminal()` using public `Host.get_run()` only; it treats `LOST` as a public Run terminal state.
- Added `read_host_instances()` as a fresh short-read liveness diagnostic; it does not drive recovery or expose scheduler internals.
- Added `verify_lane_released()` using runtime lane public immediate acquire/release against the same `OpenHostOptions.lane_db_path`; it proves no remaining lane claim blocks capacity.
- Added `test_scheduler_liveness_long_run_mixed_flow_stress` covering:
  - intentional owner crash followed by startup recovery;
  - lane capacity 1 scheduler pressure;
  - active blocking success plus queued cancel plus queued tail promotion;
  - active cancel propagation to worker handle;
  - worker stream exception closeout to `LOST`;
  - explicit failed worker closeout;
  - Host clean close and reopen with no extra `RUN_RECOVERING` / `ATTEMPT_LOST` from the clean close;
  - terminal duplicate count, lane release, handle close count, cancel count, and stale liveness diagnostic.

The clean-close proof intentionally does not leave a nonterminal active Run open at context-manager exit. Current Host design says close does not write user terminal facts; leaving an active Run open would validly make startup recovery take over that Run. The Slice 4 test therefore proves cleanup after drained/cancelled/failed flows and separately proves recovery only for the intentional crash flow.

## Validation

Passed:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

Observed results:

- Slice 4 targeted stress: `1 passed, 3 deselected`.
- Required scheduler/liveness/cancel regression: `75 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Full Host production stress file: `4 passed`.

## Docs Decision

No `tests/README.md` change was needed. Slice 4 did not add or change the stress marker, default exclusion behavior, command shape, or documented test running contract.

## Residual Risks

- The stress is deterministic and bounded, not a randomized fuzz or long-duration soak.
- `read_host_instances()` uses a test threshold only to interpret stale heartbeat evidence created by `force_owner_pid_missing_and_heartbeat_stale()`; recovery truth remains the Host recovery scanner and EventLog facts.
- `RUN_LOST` is not a public `HostTerminalStatus`, so Slice 4 proves dedupe in two layers: succeeded/failed/cancelled terminal observations have no duplicates, and the count of all terminal EventLog rows including `RUN_LOST` equals the public terminal snapshot count.
