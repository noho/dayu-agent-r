# WU-LIFE-01 + WU-LIFE-02 Slice A Implementation Report

## Scope

- Role: gateflow implementation worker.
- Controller: AgentController.
- Gate: implementation.
- Accepted plan commit: `975b9ba`.
- Plan artifact: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`.
- Slice: Slice A - Recovery lifecycle proof matrix + focused recovery tests.

## Modified Files

- `tests/host/test_recovery_scan.py`
  - Added `_RECOVERY_LIFECYCLE_PROOF_MATRIX` with scenario id, Run status, owner proof / dispatch condition, expected decision, expected durable mutation, expected reason, and coverage classification.
  - Added scanner-level still-live integration coverage for recent owner heartbeat.
  - Added scanner-level inconclusive integration coverage for process probe error and stale heartbeat with pid live but no identity proof.
  - Strengthened WAITING diagnostic-only assertions and added a stable durable-read user-visible semantics test.
  - Added local test probes and durable observation helpers.
- `docs/reviews/wu-life-01-02-implementation-sliceA-codex-20260601.md`
  - This implementation report.

## Tests Added Or Updated

- Added `test_recovery_lifecycle_proof_matrix_covers_slice_a_rows`.
- Added `test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows`.
- Added parametrized `test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows`.
- Updated `test_scan_waiting_uses_diagnostic_only_fallback` to assert reason and absence of recovery / terminal facts.
- Added `test_scan_waiting_public_visible_durable_state_remains_diagnostic_only`.

## Production Code Changes

- None.
- Tests-first execution did not prove a production recovery bug. Existing scanner behavior already keeps still-live and inconclusive proof paths diagnostic-only and preserves WAITING durable semantics.

## Validation

All commands were run after `source .venv/bin/activate`.

- `pytest tests/host/test_recovery_scan.py -q`
  - Passed: `13 passed`.
- `pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q`
  - Passed: `32 passed`.
- `python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`.

Secondary validation:

- Multiprocess validation was not triggered because Slice A touched only `tests/host/test_recovery_scan.py` and did not touch multiprocess code or tests.
- Public `open_host` validation was not triggered because WAITING coverage used the narrower durable-read path allowed by the plan.

## README And Doc Sync

- No README changes.
- `tests/README.md` was checked by trigger rule: this slice only adds focused recovery tests and does not change test layering, commands, markers, conventions, or maintenance rules.
- No package README is in scope because no production code, public API, schema, state-machine, CLI, configuration, or architecture boundary changed.

## Contract / Schema / State-Machine / Public Interface Changes

- Durable schema changes: none.
- EventLog type changes: none.
- Host public API changes: none.
- Run / Attempt state-machine changes: none.
- WAITING durable semantics changes: none.

## Residual Risks

- RR-DUR-04 is represented as a proof matrix row. This slice did not add instrumentation that mechanically proves transaction duration; the direct code evidence remains `StartupRecoveryScanner.scan()` using one `run_write` transaction and durable Run / Attempt / EventLog / dispatch / liveness reads, with projection-lag behavior covered by existing scanner tests.
- `pid live without identity proof` is classifier-defined as `ORPHAN_INCONCLUSIVE`, not `OWNER_STILL_LIVE`; Slice A records and tests the current safer scanner behavior without changing the classifier contract.

## Stop Conditions Hit

- None.
- No test required schema, EventLog, public API, Run / Attempt state-machine, WAITING semantic, or unauthorized file changes.
- No deterministic test depended on sleep or race timing.
- No test proved recovery scanner writes recovery / terminal facts from stale heartbeat alone, projection / read model lag, or inconclusive proof.
