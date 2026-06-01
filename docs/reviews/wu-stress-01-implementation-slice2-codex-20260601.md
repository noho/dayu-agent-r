# WU-STRESS-01 Slice 2 Implementation Artifact

## Scope

- Role: AgentCodex, WU-STRESS-01 implementation specialist.
- Slice: Slice 2 Repeated startup / recovery / crash E2E stress.
- Accepted plan: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`.
- Slice 1 accepted commit: `ffcc7e5`.
- Stop status: not stopped; no production-code change was required.

## Changed Files

- `tests/host/stress_support.py`
  - Added thin stress wrappers around `tests.host.recovery_support` process/probe helpers.
  - Added `start_and_crash_owner_for_stress`.
  - Added event count, attempt count, and durable terminal observation diagnostic helpers.
- `tests/host/test_host_production_stress.py`
  - Added `test_repeated_startup_recovery_crash_stress`.
  - Added live owner probe helper and Slice 2 failure-boundary summary helper.

## Implemented Plan Items

- Reused recovery multiprocess process target, accepted marker, process termination, lane TTL wait, stale owner injection, event count, and attempt count logic through thin wrappers.
- Repeated crash/reopen recovery with 3 deterministic crash cycles.
- Verified every crashed run reaches public `SUCCEEDED` terminal event and public `RunStatus.SUCCEEDED`.
- Verified each crashed run has exactly 2 attempts.
- Verified `RUN_RECOVERING` count equals crash count.
- Verified `ATTEMPT_LOST` count equals crash count.
- Verified terminal duplicate count is 0 using durable terminal observations and existing stress summary helpers.
- Added live owner probe proving a second opener does not create `ATTEMPT_LOST` or `RUN_RECOVERING` while the owner is alive.
- Built `HostStressSummary`, recorded it via `record_property`, used `summary_to_json`, and routed final assertions through summary JSON diagnostics.

## Validation

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k repeated_startup_recovery_crash -q
```

Result: `1 passed, 1 deselected`.

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_multiprocess.py -q
```

Result: `3 passed`.

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

## Docs Decision

- `tests/README.md` was not changed.
- Reason: Slice 2 did not add a new command, marker, summary field, or user-facing testing convention beyond Slice 1.

## Plan Gaps

- None found for Slice 2.
- No need to change recovery stale threshold, recovery policy, or `open_host` startup scan signature.

## Residual Risks

- The stress loop uses the minimum accepted crash count, 3 cycles, to keep runtime stable in local and CI environments.
- Terminal dedupe is diagnosed from fresh durable reads plus public terminal observations for crashed runs; this slice does not attempt watch reconnect semantics, which are reserved for Slice 3.
