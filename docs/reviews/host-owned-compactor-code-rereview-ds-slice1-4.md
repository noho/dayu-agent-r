# Host-owned Compactor Code Re-Review — Slice 1-4 (DeepSeek)

## Gate / Work Unit

- gate: parallel code re-review after fix for implementation Slice 1-4
- work unit: Host-owned LLM context compactor public opener contract
- review target: current workspace diff after code fix
- source review artifact: `docs/reviews/host-owned-compactor-code-review-ds-slice1-4.md`
- parallel review artifact: `docs/reviews/host-owned-compactor-code-review-mimo-slice1-4.md`
- fix artifact: `docs/reviews/host-owned-compactor-code-fix-codex-slice1-4.md`
- required re-review artifact: `docs/reviews/host-owned-compactor-code-rereview-ds-slice1-4.md`
- reviewer: DeepSeek (second independent re-review agent)
- date: 2026-05-19

## Re-Review Summary

| Criterion | Result |
|---|---|
| ACCEPTED-FIX-1 / MiMo F-1 / DS F1: duplicated compaction operation logic | **FIXED** |
| ACCEPTED-FIX-2 / MiMo F-2 / DS test gap: HostEvent projection for ATTEMPT_REJECTED | **FIXED** |
| ACCEPTED-FIX-3 / DS F4: operation_id diagnostic risk | **FIXED** |
| Regression: public contract / transaction boundary | **PASS** |
| Regression: Slice 5/6 overstep | **PASS** |
| Deferred items unchanged | **CONFIRMED** |
| **Overall** | **PASS** |

## ACCEPTED-FIX-1: Duplicated Compaction Operation Logic

### Evidence

- `dayu/host/compaction_operation.py` (new file, 234 lines): shared Host-internal module exporting `CompactionAttemptRejected`, `CompactionOperationResult`, `run_compaction_operation`.
- `run_compaction_operation` (line 71–177): bounded proposal attempt loop with three failure paths — `proposal_failed`, `quality_check_rejected`, `hard_threshold_after_compact` — plus `max_compaction_attempts_exhausted`. Each path constructs `CompactionAttemptRejected` via module-level `_attempt_rejected` helper.
- `dispatch.py`: imports `run_compaction_operation` (line 118); calls it at line 900 outside write transaction, inside `_execute_proactive_compaction`.
- `engine_ingest.py`: imports `run_compaction_operation` (line 69); calls it at line 1351 outside write transaction, inside `_execute_reactive_compaction`.
- **Removed from dispatch.py**: old `_CompactionAttemptRejected` dataclass, old `_CompactionOperationResult` dataclass, old `_run_compaction_operation` method, old `_attempt_rejected` helper, old `_quality_suffix` helper.
- **Removed from engine_ingest.py**: old `_CompactionAttemptRejected` dataclass, old `_CompactionOperationResult` dataclass, old `_run_reactive_compaction_operation` method, old `_reactive_attempt_rejected` helper, old `_reactive_quality_suffix` helper.
- EventLog writes (`_append_compaction_attempt_rejected_event`, `_append_compaction_failed_event`, `_append_compacted_event`) remain in dispatch.py (lines 926–963) and engine_ingest.py (lines 1371–1430). Artifact writes, state rechecks, recovery transitions remain in their respective modules.
- `compaction_operation.py` does not import any EventLog, artifact, memory, or transaction module.

### Verdict: FIXED

The shared helper correctly owns only the proposal attempt loop and quality/threshold validation. Dispatch and ingest still own all governance writes, state transitions, and recovery logic. No ownership leakage.

---

## ACCEPTED-FIX-2: HostEvent Projection Test Gap

### Evidence

- `tests/host/test_context_compact_events.py:331`: `test_attempt_rejected_projects_to_progress_host_event` added.
  - Creates a `CONTEXT_COMPACTION_ATTEMPT_REJECTED` EventLog row via `_attempt_rejected_row()`.
  - Opens a read transaction and calls `_host_event_from_row(transaction, row)`.
  - Asserts `HostEventKind.PROGRESS` (line 346).
- `test_context_compact_events.py:390`: helper `_attempt_rejected_row()` constructs a valid `EventLogRow` with `event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED`, `event_class=EventClass.CANONICAL_FACT`.
- HostEvent mapping logic (`read_api.py:419–436`) unchanged — only `RUN_SUCCEEDED`/`RUN_FAILED`/`RUN_CANCELLED` map to terminal kinds; all others (including `CONTEXT_COMPACTION_ATTEMPT_REJECTED`) fall through to `HostEventKind.PROGRESS`.

**Runner/provider retry HostEvent gap assessment**: The fix artifact notes that runner/provider retry HostEvent gap was not separately tested. This is structurally adequate:
- Provider retry happens inside `LLMContextCompactor` → `run_agent_and_wait` (runner execution), not at the Host event layer.
- `HostEvent` projection only reads EventLog rows (`read_api.py:408`).
- `compaction_operation.py` emits no EventLog rows — it only returns `CompactionOperationResult`.
- Therefore, provider retry cannot emit a HostEvent through any path.
- Existing test `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair` (`test_llm_compaction.py`) already covers that runner retry is passthrough.

### Verdict: FIXED

The explicit HostEvent projection test is present and correct. The runner/provider retry gap is structurally closed by the architecture (no EventLog rows from the shared helper or from the LLMContextCompactor).

---

## ACCEPTED-FIX-3: operation_id Diagnostic Risk

### Evidence

**Proactive path (dispatch.py)**:
- `_append_compaction_requested_event` (line 1285–1336) returns `EventLogRow` via `.row` (line 1336), giving access to `event_id`.
- `_GovernanceCompactPending.operation_id` (line 267) receives `requested.event_id` (line 1203).
- `_append_compaction_attempt_rejected_event` receives `operation_id=pending.operation_id` (line 929).
- Payload builder receives `operation_id=operation_id` (line 1427), which is the request event id.

**Reactive path (engine_ingest.py)**:
- `_ReactiveCompactPending.operation_id` (line 341) receives `requested.event_id` (line 1100).
- `_append_reactive_compaction_attempt_rejected_event` receives `operation_id=pending.operation_id` (line 1376).
- Payload builder receives `operation_id=operation_id` (line 1619), which is the request event id.

**Tests**:
- `test_dispatch_scheduler.py:2162`: `assert _event_payload(rejected)["operation_id"] == requested.event_id` — proactive rejected payload uses request event id.
- `test_engine_ingest_mapping.py:453`: `test_reactive_compaction_attempt_rejected_uses_request_event_operation_id`.
  - Line 486: `assert rejected_payload["operation_id"] == result.events[0].event_id` (request event id).
  - Line 487: `assert requested_payload["estimator_digest"] != rejected_payload["operation_id"]` — confirms divergence from old estimator_digest anchor.

### Verdict: FIXED

operation_id now uses the stable `CONTEXT_COMPACTION_REQUESTED` event id in both proactive and reactive paths. Tests cover both paths and explicitly verify the estimator_digest is not reused.

---

## Regression: Public Contract and Transaction Boundary

### Evidence

- `CompactorRunnerBaseline` (`api.py:921–962`): unchanged. No `context_compactor`, no `policy_ref`, no prompt fields.
- `HostEventKind` enum (`api.py:2387–2401`): unchanged — PROGRESS, SUCCEEDED, FAILED, CANCELLED. No new members.
- `__init__.py`: no `CompactorExecutionBaseline` or `context_compactor` export.
- Proactive transaction boundary: `run_compaction_operation` called at `dispatch.py:900` outside any transaction; result written in new `run_write` transaction at line 965. State recheck at lines 907–924 unchanged.
- Reactive transaction boundary: `run_compaction_operation` called at `engine_ingest.py:1351` outside any transaction; result written in new `run_write` transaction at line 1455 (via `_operation` → `transaction_runner.run_write`). Context revalidation via `_validate_durable_context` at line 1360 unchanged.

### Verdict: PASS

No regression to public contract or transaction boundary guarantees.

---

## Regression: Slice 5/6 Overstep

### Evidence

- `git diff --name-only HEAD`: 21 files, all within `dayu/host/` and `tests/host/`.
- `utils/smoke_host_public_multiturn.py`: **not in diff**.
- README files: **not in diff**.
- New file `dayu/host/compaction_operation.py` is a Host-internal module — within approved Slice 1-4 scope.
- `test_public_compact_smoke.py`: modified only for the controller-approved minimal compile fix (import renames, field renames). `_RealLLMContextCompactor` class definition preserved (line 122) for Slice 5 cleanup.

### Verdict: PASS

No Slice 5/6 overstep.

---

## Deferred Items Confirmation

| Finding | Status | Evidence |
|---|---|---|
| MiMo F-3 / `_RealLLMContextCompactor` dead code | Deferred, unchanged | Still defined at `test_public_compact_smoke.py:122`; deferred to Slice 5 |
| DS F2 / daemon thread bridge | Accepted, unchanged | `llm_compaction.py:222–231` daemon thread pattern intact per controller decision |
| DS F3 / `_input_range` ordering | Deferred, unchanged | `llm_compaction.py:380–393` ordering assumption intact |

---

## Validation

Command:
```
pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_llm_compaction.py tests/host/test_context_policy.py -q
```
Result: **101 passed in 0.97s**

Command:
```
pytest tests/host/test_package_exports.py tests/host/test_open_host_runtime.py tests/host/test_public_open_host_options.py tests/host/test_public_compact_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_retry_replay.py tests/host/test_submit_followup_public_contract.py tests/host/test_watch_session_events.py tests/host/test_effective_execution_config.py tests/host/test_per_run_tool_selection.py -q
```
Result: **43 passed in 8.58s**

Command:
```
python -m pyright dayu/host tests/host
```
Result: **0 errors, 0 warnings, 0 informations**

Command:
```
git diff --check
```
Result: **passed** (no whitespace errors)

---

## Final Status Mapping

| Finding | Original Severity | Status |
|---|---|---|
| ACCEPTED-FIX-1 / MiMo F-1 / DS F1: duplicated operation logic | MEDIUM (MiMo) / LOW (DS) | **FIXED** — shared helper extracted to `compaction_operation.py` |
| ACCEPTED-FIX-2 / MiMo F-2 / DS test gap: HostEvent projection | LOW | **FIXED** — explicit PROGRESS mapping test added; runner retry gap structurally closed |
| ACCEPTED-FIX-3 / DS F4: operation_id diagnostic risk | LOW | **FIXED** — stable request event id anchor; tests cover proactive and reactive |
| DEFERRED-1 / MiMo F-3: dead `_RealLLMContextCompactor` | LOW | Deferred to Slice 5, unchanged |
| REJECTED/DEFERRED-2 / DS F2: daemon thread bridge | LOW | Accepted per controller decision, unchanged |
| DEFERRED-3 / DS F3: `_input_range` ordering | LOW | Deferred, unchanged |

## Conclusion

**Result: PASS**

All three accepted findings are correctly fixed. No regressions detected in public contract, transaction boundaries, HostEvent mapping, or test coverage. No Slice 5/6 files were touched. All 144 tests pass with 0 pyright errors. All three deferred/rejected items remain in their original state as specified by the controller.

The implementation is ready for the next gate.
