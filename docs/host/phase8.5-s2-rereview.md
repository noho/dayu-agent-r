# P8.5 Slice 2 Re-review

## Gate / Target

- Review gate name: `code re-review`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 2 — Durable Memory Repair Stabilization
- Current gate: `re-review`
- Source review artifact: `docs/host/phase8.5-s2-code-review.md`
- Fix artifact: `docs/host/phase8.5-s2-fix-report.md`
- Re-reviewed accepted finding ids: `1`
- Reviewed scope:
  - `dayu/host/_conversation_memory_durable.py`
  - `dayu/host/_durable_harness.py`
  - `tests/host/test_phase8_durable_memory_recovery.py`
  - `dayu/host/README.md`

## Reviewer Conclusion

pass

Accepted Finding 1 is fixed. The repair path now has a separate paged scan for snapshot rows that have no canonical EventLog session, inspects those rows for corrupt payload / schema mismatch / session mismatch, emits typed `CORRUPT_SNAPSHOT` diagnostics, logs WARNING, and does not overwrite the row. Missing-row rebuild remains restricted to EventLog canonical candidates, so snapshot-only missing rows and snapshot-only non-canonical sessions are not rebuilt from an absent fact source. The implementation uses bounded `LIMIT ?` pagination and does not load the full snapshot table.

This re-review does not make the final Gateflow controller decision, does not expand scope beyond Finding 1, and does not review unrelated residual risks.

## Re-review Result

### Finding 1 — fixed

- **Source finding**: corrupt snapshot row 诊断只覆盖 EventLog canonical session，漏掉 snapshot-only 坏行。
- **Fix status**: fixed.
- **Direct evidence**:
  - `DurableConversationMemoryStore._repair_missing_session_snapshots_locked()` first scans `_collect_snapshot_only_session_ids_after()` and only calls `_inspect_snapshot_row()` for each snapshot-only session; it appends diagnostics and calls `_log_memory_repair_diagnostic()` when inspection reports corruption. It does not call `_repair_missing_snapshot_for_session()` in this snapshot-only pass. See `dayu/host/_conversation_memory_durable.py:364-380`.
  - EventLog canonical candidate handling remains a separate pass. Only that pass checks missing snapshot rows and calls `_repair_missing_snapshot_for_session()` when the row is absent. See `dayu/host/_conversation_memory_durable.py:382-402`.
  - `_collect_snapshot_only_session_ids_after()` scans `host_conversation_memory_snapshots` with `NOT EXISTS` against canonical `host_run_events`, ordered by `session_id`, with `_REPAIR_SESSION_SCAN_BATCH_LIMIT`. The paginated `after_session_id` branch also keeps the scan bounded. See `dayu/host/_conversation_memory_durable.py:506-561`.
  - `_inspect_snapshot_row()` returns typed corrupt diagnostics for non-text payload, decode/schema failure, and decoded session mismatch, without writing any snapshot row. See `dayu/host/_conversation_memory_durable.py:563-611`.
  - `_build_corrupt_snapshot_diagnostic()` constructs `MemoryRepairDiagnosticKind.CORRUPT_SNAPSHOT`, and `_log_memory_repair_diagnostic()` logs through `_LOGGER.warning(...)`. See `dayu/host/_conversation_memory_durable.py:817-866`.
  - `DurableHarnessBundle.startup_reconcile()` still exposes the repair report by returning `repair_missing_session_snapshots()` for durable memory stores. See `dayu/host/_durable_harness.py:149-179`.

## Required Behavior Check

- Snapshot table session scan: satisfied. `_collect_snapshot_only_session_ids_after()` covers rows in `host_conversation_memory_snapshots` that have no canonical EventLog session.
- Typed diagnostic: satisfied. Snapshot-only corrupt rows return `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, session_id=..., reason=...)`.
- WARNING: satisfied. Diagnostics flow through `_log_memory_repair_diagnostic()`, which logs at WARNING.
- No overwrite: satisfied. The snapshot-only pass only inspects rows and logs diagnostics; the regression test confirms the corrupt payload remains unchanged and `get_snapshot()` still raises `ValueError`.
- No rebuild for snapshot-only missing/non-canonical rows: satisfied. Snapshot-only scan starts from existing snapshot rows and does not trigger rebuild. Missing-row rebuild remains driven only by EventLog canonical candidate sessions and requires terminal canonical facts.
- No unbounded full-table load: satisfied. Snapshot-only and EventLog candidate scans both page by `session_id` with `_REPAIR_SESSION_SCAN_BATCH_LIMIT`; single-session canonical replay uses the existing paged fetch path.

## Test Coverage

- `tests/host/test_phase8_durable_memory_recovery.py:902` adds `test_repair_reports_snapshot_only_corrupt_row_without_overwrite`.
- The test creates a snapshot-only row through `MemoryResetPatch`, corrupts `snapshot_payload`, calls `startup_reconcile()`, and asserts:
  - no repaired session ids;
  - exactly one `CORRUPT_SNAPSHOT` diagnostic for the snapshot-only session;
  - WARNING log contains `durable_repair_diagnostic`;
  - corrupt payload remains unchanged;
  - `get_snapshot()` still raises `ValueError`, proving repair did not overwrite.
- Existing tests still cover EventLog-backed corrupt rows continuing repair for other missing sessions and intentional empty snapshots not being rebuilt from old EventLog facts.

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_durable_memory_recovery.py -q`
  - Result: passed, `17 passed in 0.20s`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - Result: passed, `4 passed in 1.58s`.

## Open Questions And Residual Risk

- No new blocker found in the accepted Finding 1 fix.
- Residual risk from the fix report remains non-blocking for this finding: a corrupt row inserted concurrently after a repair pass may be diagnosed on a later repair run. This preserves the approved no-overwrite invariant.
- Corrupt snapshot row origin, quarantine policy, operator command, and auto-overwrite policy remain outside this slice and are tracked by existing issue #41 per the implementation and fix artifacts.

## Artifact

- Artifact path: `docs/host/phase8.5-s2-rereview.md`
