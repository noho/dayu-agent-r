# P8.5 Slice 2 Implementation Report

## Gate / Scope

- Work gate name: `implementation`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: P8.5 Slice 2 — Durable Memory Repair Stabilization
- Approved plan path: `docs/host/phase8.5-plan.md`
- Current branch: `migration/host-p8-5-stabilization`
- Previous accepted slice commit: `20617f6 gateflow: accept host p8.5 slice 1`
- Allowed scope: durable memory repair, durable EventLog helper/index, durable harness startup exposure, focused recovery tests, relevant Host README
- Explicit non-goals honored:
  - Did not modify ToolRuntime event model.
  - Did not implement user-facing repair CLI.
  - Did not implement old database migration or compatibility reader.
  - Did not research or correct the origin of corrupt snapshot rows.
  - Did not commit, push, open PR, start Slice 3, or enter closeout.

## Changed Files

- `dayu/host/_conversation_memory_durable.py`
- `dayu/host/_durable_event_store.py`
- `dayu/host/_durable_harness.py`
- `tests/host/test_phase8_durable_memory_recovery.py`
- `dayu/host/README.md`
- `docs/host/phase8.5-s2-implementation-report.md`

## Plan Items Implemented

- Added typed repair report: `MemoryRepairReport(repaired_session_ids, diagnostics)`.
- Added typed diagnostic: `MemoryRepairDiagnostic` with `MemoryRepairDiagnosticKind.CORRUPT_SNAPSHOT`.
- Changed `repair_missing_session_snapshots()` to return `MemoryRepairReport`.
- Changed `DurableHarnessBundle.startup_reconcile()` to expose the durable memory repair report when the configured memory store is durable; custom stores return `None`.
- Preserved auto-rebuild for missing snapshot row when EventLog contains terminal canonical facts.
- Added corrupt snapshot row handling:
  - invalid JSON / invalid payload shape,
  - schema version mismatch,
  - decoded snapshot session id mismatch.
- Corrupt rows are not overwritten; repair returns diagnostic, logs WARNING, and continues processing other sessions.
- Added `DurableRunEventStore.fetch_events_for_session_by_position()` using the required SQL shape:
  `WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`.
- Added index `idx_host_run_events_session_kind_position` on `(session_id, kind, event_position)`.
- Replaced unbounded missing-session collection with paged candidate session scanning.
- Updated recovery tests for report shape, corrupt-row diagnostics, startup exposure, and continued repair after a corrupt row.

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_durable_memory_recovery.py -q`
  - Result: passed, `16 passed`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - Result: passed, `4 passed`.

## Docs Decision

- Updated `dayu/host/README.md` because Slice 2 changed Host durable startup/recovery behavior and the repair return contract.
- No root README, Engine README, Fins README, Config README, or tests README update was needed; no user-facing command, Engine boundary, Fins boundary, config entry, or test workflow changed.

## Residual Risks

- `tracked-by-existing-issue`: corrupt snapshot row origin, quarantine policy, operator command, and auto-overwrite policy remain owned by issue #41.
- `accepted-in-current-slice`: existing corrupt row inserted concurrently after the pre-check but before the repair transaction causes the transaction recheck to skip overwrite; it may not emit a diagnostic until the next repair pass. This preserves the approved no-overwrite invariant.
- `assigned-to-later-slice`: broader ToolRuntime EventLog model cleanup remains outside Slice 2 and was not touched.

## Stop Condition Status

- User-facing repair CLI was not needed.
- Old database migration / compatibility reader was not needed.
- No direct code evidence was found that current normal write paths produce corrupt snapshot rows: normal writes encode with `_encode_snapshot_text()` before the snapshot UPSERT.
- No ToolRuntime event model changes were made.

## Completion Signal

Slice 2 implementation is complete for code, tests, README sync, and required implementation artifact. Ready for controller-owned code review gate.
