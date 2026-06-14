# WU-CM-09 S2 Implementation Report

## Scope

S2 connected the S1 memory snapshot integrity classifier to the existing operator-facing `run_storage_maintenance(...)` report. It does not add quarantine, rebuild, overwrite, deletion, or a new public command.

## Changes

- Extended `HostStorageMaintenanceResult` with `memory_snapshot_integrity_issues`.
- Added runtime validation for the new issue tuple in `HostStorageMaintenanceResult.__post_init__`.
- Included integrity issues in `HostStorageMaintenanceResult.json_value()`.
- Collected `inspect_memory_snapshot_integrity(...)` output in the same storage maintenance read state as usage and artifact references.
- Exported `MemorySnapshotIntegrityIssue` through `dayu.host.storage_maintenance` and package root.
- Added public maintenance tests for empty integrity issues, invalid JSON snapshot reporting, JSON key stability, and package exports.

## Validation

- Baseline before edits: `pytest tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` -> 24 passed.
- S2 target: `pytest tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` -> 25 passed.
- Coverage: `pytest --cov=dayu.host.storage_maintenance --cov-report=term-missing tests/host/test_storage_maintenance.py -q` -> 12 passed, `dayu/host/storage_maintenance.py` 88%.
- Type check: `python -m pyright dayu/ tests/ utils/` -> 0 errors, 0 warnings.
- Whitespace: `git diff --check` -> clean.

## README Decision

- `dayu/host/README.md` and `tests/README.md` updates are deferred to WU-CM-09 S3 per accepted plan, because S3 is the documentation closure slice for the now-public maintenance report field and test coverage summary.

## Residual Risk

- `run_storage_maintenance(...)` now reports memory snapshot integrity issues alongside artifact orphan diagnostics. This remains read-only and does not couple integrity classification to artifact reclaim.
