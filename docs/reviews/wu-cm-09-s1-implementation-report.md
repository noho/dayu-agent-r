# WU-CM-09 S1 Implementation Report

## Scope

S1 implemented the durable read-only memory snapshot integrity classifier. It does not expose a new public Host API, does not modify `run_storage_maintenance(...)`, and does not rebuild, overwrite, quarantine, or delete memory snapshot rows.

## Changes

- Added `MemorySnapshotIntegrityFailureKind` and `MemorySnapshotIntegrityIssue` in `dayu.host.durable.memory`.
- Added `inspect_memory_snapshot_integrity(transaction)` as a read-only classifier over `host_memory_snapshots`.
- Classified direct evidence into:
  - `invalid_json`
  - `schema_mismatch`
  - `digest_mismatch`
  - `unsupported_item_kind`
  - `storage_read_failed`
- Preserved existing `read_memory_snapshot(...)` / latest snapshot fail-closed behavior.
- Added `test_memory_snapshot_integrity_...` coverage in `tests/host/test_memory_projection.py` for empty/valid rows, invalid JSON, schema mismatch, manual digest mismatch, old `verified_fact` item kind fail-closed behavior, mixed damaged rows, and storage read failure.

## Validation

- Baseline before edits: `pytest tests/host/test_memory_projection.py -q` -> 17 passed.
- S1 target: `pytest tests/host/test_memory_projection.py -q` -> 26 passed.
- Coverage: `pytest --cov=dayu.host.durable.memory --cov-report=term-missing tests/host/test_memory_projection.py -q` -> 26 passed, `dayu/host/durable/memory.py` 80%.
- Type check: `python -m pyright dayu/ tests/ utils/` -> 0 errors, 0 warnings.
- Whitespace: `git diff --check` -> clean.

## README Decision

- `dayu/host/README.md` is not updated in S1 because the classifier is still an internal durable primitive and not yet part of the public operator-facing maintenance result.
- `tests/README.md` is not updated in S1 because the broader Host tests coverage paragraph will be updated in S3 after the operator-facing maintenance report is wired.

## Residual Risk

- S1 intentionally does not classify via a public maintenance result yet; S2 owns the operator-facing report surface.
- `storage_read_failed` scan failure is covered with a controlled monkeypatch of the classifier row-reader helper; real SQLite failures remain environment-dependent and are not forced through unsafe DB corruption.
- Code review low findings were fixed before accepted slice commit: removed an unused scan constant and added focused tests for row digest column mismatch and unknown item kind.
