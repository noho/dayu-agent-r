# P8.5 Slice 2 Fix Report

## Gate / Scope

- Work gate name: `fix`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 2 — Durable Memory Repair Stabilization
- Source review artifact: `docs/host/phase8.5-s2-code-review.md`
- Implementation artifact: `docs/host/phase8.5-s2-implementation-report.md`
- Controller-accepted finding ids: `1`
- Explicit non-goals honored:
  - Did not start `$gateflow` / `/gateflow`.
  - Did not redo plan or review.
  - Did not handle rejected or deferred findings.
  - Did not add user-facing repair CLI.
  - Did not add old database compatibility reader or migration.
  - Did not commit, push, open PR, close out the work unit, or start Slice 3.

## Per-Finding Fix Status

### Finding 1 — corrupt snapshot row 诊断只覆盖 EventLog canonical session，漏掉 snapshot-only 坏行

- Status: fixed.
- Fix:
  - Added paged snapshot-only session scanning in `DurableConversationMemoryStore`.
  - Snapshot-only rows are inspected for corrupt payload / schema mismatch / session mismatch.
  - Snapshot-only corrupt rows emit `MemoryRepairDiagnosticKind.CORRUPT_SNAPSHOT`, log WARNING, and are not overwritten.
  - Missing-row rebuild remains driven only by EventLog canonical session candidates.
  - The scan is batched by `session_id` and does not load the full snapshot table.
- Verification point:
  - Added a regression test that creates a valid empty snapshot through `MemoryResetPatch` without canonical EventLog, corrupts the payload, runs `startup_reconcile()`, and asserts one `CORRUPT_SNAPSHOT` diagnostic, WARNING log, unchanged row, and no repair overwrite.

## Changed Files

- `dayu/host/_conversation_memory_durable.py`
- `tests/host/test_phase8_durable_memory_recovery.py`
- `dayu/host/README.md`
- `docs/host/phase8.5-s2-fix-report.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_phase8_durable_memory_recovery.py -q`
  - Result: passed, `17 passed in 0.22s`.
- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - Result: passed, `4 passed in 1.65s`.

## Documentation Decision

- Updated `dayu/host/README.md` because the durable memory repair wording needed to reflect that corrupt existing snapshot rows are diagnosed even when the session has no canonical EventLog.
- No other README update was needed; this fix does not change user-facing commands, configuration, Engine/Fins boundaries, or test workflow.

## New Risks / Open Questions

- No new open question introduced.
- New risk: snapshot-only scanning adds one extra paged repair pass over `host_conversation_memory_snapshots`; risk is low because it is bounded by `_REPAIR_SESSION_SCAN_BATCH_LIMIT` and only reads session ids plus per-row payload inspection.
- No plan deviation introduced.

## Residual Risk Classification

- `fixed-in-current-slice`: Finding 1 is fixed in this pass.
- `tracked-by-existing-issue`: corrupt snapshot row origin, quarantine policy, operator command, and auto-overwrite policy remain owned by issue #41, as recorded by the implementation report.
- `accepted-in-current-slice`: a corrupt row inserted concurrently after a repair pass may be diagnosed on a later repair run; this preserves the approved no-overwrite invariant.

## Artifact

- Artifact path: `docs/host/phase8.5-s2-fix-report.md`
