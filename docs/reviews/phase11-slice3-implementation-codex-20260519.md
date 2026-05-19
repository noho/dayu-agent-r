# Phase 11 Slice 3 Implementation - AgentCodex

## Changed Files

- `dayu/host/recovery.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_open_host_runtime.py`
- `dayu/host/README.md`
- `tests/README.md`

Note: `docs/host/implementation-control.md` had a pre-existing workspace change before this slice and was not modified by this implementation.

## Implemented Plan Items

- Added startup recovery dispatch for `RECOVERING` Runs when the canonical EventLog recovery dispatch count is under the configured limit.
- For recoverable positive orphan `RUNNING` Runs, startup scan now closes the old Attempt and immediately creates a new recovery Attempt / execution / dispatch record in the same scan transaction when a scheduler wakeup port and current Host instance id are available.
- Recovery dispatch uses `start_recovery_run_with_starting_attempt_in_transaction(...)` to append `RUN_STARTED(start_reason=recovery)`, update Run current Attempt, append `ATTEMPT_STARTED`, insert the new `Attempt`, and insert a pending dispatch record in one write transaction.
- Recovery wakes the existing `HostDispatchScheduler` only after the write transaction returns; it does not call `WorkerProxy` or worker factories directly.
- `open_host.__aenter__` now runs startup recovery scan after scheduler registration and before logging ready / returning the public handle.
- `HostDispatchScheduler` exposes its registered Host instance id for recovery-owned pending dispatch records.
- `StartRecoveryRunInput` now supports startup recovery without a reactive `CONTEXT_COMPACTED` event while preserving reactive compact recovery fields when present.
- Verified `RunInputBuilder` recovery behavior: a recovery Attempt rebuilds the current prompt from the same Run's canonical `USER_INPUT_ACCEPTED` EventLog payload descriptor, not from the old Attempt snapshot.
- Added late old execution test: after recovery creates a new Attempt, a terminal event from the old `execution_id` is rejected and does not write `RUN_SUCCEEDED`.
- Added `open_host(options)` integration coverage: an interrupted Run is recovered on reopen and the final answer is observed through `watch_session_events(session_id)`.

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_recovery_dispatch.py tests/host/test_run_input_builder.py tests/host/test_open_host_runtime.py -q
```

Result: `39 passed in 0.47s`

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

- Updated `dayu/host/README.md` because `dayu/host/` behavior changed: `open_host` now runs startup recovery scan before ready, and `RECOVERING` can create a new recovery Attempt / dispatch under limit.
- Updated `tests/README.md` because new Host tests cover startup recovery dispatch, old execution rejection, RunInputBuilder recovery descriptor reconstruction, and public `open_host` recovery watch behavior.
- No root `README.md`, `dayu/README.md`, Engine/Fins/Config README changes were needed because this slice did not change project-level usage, layering, Engine/Fins/Config behavior, or public API surface.

## Residual Risks / Owners

- `RECOVERING` public cancel and `cancel_session_runs` support remain Slice 4 ownership and were not implemented here.
- Multi-process harness and runtime lane hardening remain Slice 5 ownership and were not implemented here.
- Startup recovery still relies on Slice 1 positive orphan proof semantics; heartbeat stale alone is not treated as proof.
- Recovery dispatch limit is still based on canonical EventLog `RUN_STARTED(start_reason=recovery)` count as planned; no schema change was introduced.

## Conclusion

HANDOFF_IMPLEMENTED
