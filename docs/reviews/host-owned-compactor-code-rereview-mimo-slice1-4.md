# Host-owned Compactor Code Re-Review: Slice 1-4

## Re-Review Identity

- **Reviewer**: MiMo
- **Gate**: code re-review after fix for implementation Slice 1-4
- **Work unit**: Host-owned LLM context compactor public opener contract
- **Review target**: current workspace diff after code fix
- **Source review artifacts**:
  - `docs/reviews/host-owned-compactor-code-review-mimo-slice1-4.md`
  - `docs/reviews/host-owned-compactor-code-review-ds-slice1-4.md`
- **Fix artifact**: `docs/reviews/host-owned-compactor-code-fix-codex-slice1-4.md`
- **Date**: 2026-05-19

## Conclusion

**PASS**

All three accepted fixes are correctly implemented. No regressions introduced. No Slice 5/6 files touched. Public contract and transaction boundary guarantees hold.

## Accepted Fix Verification

### ACCEPTED-FIX-1: Duplicated compaction operation logic (MiMo F-1 / DS F1)

**Status**: FIXED

**Evidence**:

- `dayu/host/compaction_operation.py` extracted as Host-internal shared helper.
- Exports `run_compaction_operation`, `CompactionAttemptRejected`, `CompactionOperationResult`.
- Helper owns only: proposal attempt execution via `ContextCompactor.compact`, proposal failure capture, `check_compaction_candidate` quality validation, hard-threshold validation, structured result types.
- `dispatch.py:116-118` imports `CompactionAttemptRejected` and `run_compaction_operation` from shared module. No duplicate `_CompactionAttemptRejected` or `_CompactionOperationResult` dataclasses remain.
- `engine_ingest.py:66-69` imports `CompactionAttemptRejected`, `CompactionOperationResult`, `run_compaction_operation` from shared module. No duplicate dataclasses remain.
- `_append_compaction_attempt_rejected_event` (dispatch.py:1395) and `_append_reactive_compaction_attempt_rejected_event` (engine_ingest.py:1579) remain in their respective modules — these are EventLog write methods, correctly owned by the governance path.
- `check_compaction_candidate` import removed from both dispatch.py and engine_ingest.py; now only imported by `compaction_operation.py`.

**No regression**: EventLog writes, artifact writes, memory projection, state recheck, and dispatch/ingest behavior ownership unchanged.

### ACCEPTED-FIX-2: HostEvent projection test (MiMo F-2 / DS test gap)

**Status**: FIXED

**Evidence**:

- `tests/host/test_context_compact_events.py`: `test_attempt_rejected_projects_to_progress_host_event` added (lines 261-285).
- Test directly exercises the HostEvent projection path: constructs an `EventLogRow` with `event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED`, passes it through `_host_event_from_row`, asserts result is `HostEventKind.PROGRESS`.
- Test opens a real durable store via `open_host_durable_store` and runs inside `run_read`, exercising the actual projection code path.

**Runner/provider retry HostEvent gap**: Adequately addressed. Runner retry is passthrough inside `LLMContextCompactor` / runner execution (covered by `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair`). The shared `run_compaction_operation` helper emits no EventLog rows itself. HostEvent projection only reads EventLog rows. Provider retry cannot emit HostEvent through the helper. No residual gap.

### ACCEPTED-FIX-3: operation_id diagnostic risk (DS F4)

**Status**: FIXED

**Evidence**:

- `dispatch.py:267`: `_GovernanceCompactPending.operation_id: str` field.
- `dispatch.py:1203`: `operation_id=requested.event_id` — uses stable `CONTEXT_COMPACTION_REQUESTED` event id, not `estimator_digest`.
- `engine_ingest.py:341`: `_ReactiveCompactPending.operation_id: str` field.
- `engine_ingest.py:1100`: `operation_id=requested.event_id` — same stable anchor.
- `dispatch.py:929`: `_append_compaction_attempt_rejected_event` receives `operation_id=pending.operation_id`.
- `engine_ingest.py:1376`: `_append_reactive_compaction_attempt_rejected_event` receives `operation_id=pending.operation_id`.

**Test coverage**:

- `tests/host/test_dispatch_scheduler.py`: `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` asserts `_event_payload(rejected)["operation_id"] == requested.event_id`.
- `tests/host/test_engine_ingest_mapping.py`: `test_reactive_compaction_attempt_rejected_uses_request_event_operation_id` asserts `rejected_payload["operation_id"] == result.events[0].event_id` and `requested_payload["estimator_digest"] != rejected_payload["operation_id"]`.

Both proactive and reactive paths verified.

## Deferred/Rejected Items Confirmed Unchanged

| Finding | Status | Evidence |
|---------|--------|----------|
| MiMo F-3: dead `_RealLLMContextCompactor` in test_public_compact_smoke.py | Deferred, unchanged | `test_public_compact_smoke.py:122` — class definition remains, will be removed in Slice 5 |
| DS F2: daemon thread bridge in llm_compaction.py | Accepted, unchanged | `llm_compaction.py:228` — `daemon=True` thread still used for sync/async bridge |
| DS F3: `_input_range` ordering assumption | Deferred, unchanged | `llm_compaction.py:380-393` — still uses `input_event_refs[0]` / `[-1]` |

## Slice 5/6 Boundary Check

| File | Touched? | Notes |
|------|----------|-------|
| `README.md` | No | |
| `dayu/README.md` | No | |
| `dayu/host/README.md` | No | |
| `tests/README.md` | No | |
| `utils/smoke_host_public_multiturn.py` | No | |
| `dayu/host/compaction_operation.py` | Yes (new) | Shared helper, within Slice 1-4 scope |

## Public Contract And Transaction Boundary Guarantees

| Guarantee | Status | Evidence |
|-----------|--------|----------|
| Public contract exposes `CompactorRunnerBaseline`, not `ContextCompactor` / `CompactorExecutionBaseline` | HOLD | No changes to `api.py` public types in this fix |
| LLM calls happen outside write transaction (proactive) | HOLD | `dispatch.py:900` calls `run_compaction_operation` outside; `test_proactive_compaction_calls_llm_outside_write_transaction` verifies via `_TransactionReadableCompactor` |
| LLM calls happen outside write transaction (reactive) | HOLD | `engine_ingest.py:1351` calls `run_compaction_operation` outside; `test_reactive_compaction_calls_llm_outside_write_transaction` verifies |
| State recheck before writing COMPACTED/FAILED | HOLD | `dispatch.py:916-921` rechecks `run.status` and `run.input_event_sequence`; `engine_ingest.py:1378-1387` rechecks `latest.run.status` and `terminal_event_id` |
| `CONTEXT_COMPACTION_ATTEMPT_REJECTED` maps to `HostEventKind.PROGRESS` | HOLD | New test `test_attempt_rejected_projects_to_progress_host_event` pins this contract |

## Validation

```bash
pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q
# 93 passed in 0.97s

python -m pyright dayu/host/compaction_operation.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py
# 0 errors, 0 warnings, 0 informations
```

## Final Status Mapping

| Original Finding | Fix Status | Re-Review Status |
|-----------------|------------|------------------|
| MiMo F-1 / DS F1: duplicated compaction operation logic | FIXED | VERIFIED |
| MiMo F-2 / DS test gap: HostEvent projection test | FIXED | VERIFIED |
| DS F4: operation_id diagnostic risk | FIXED | VERIFIED |
| MiMo F-3: dead `_RealLLMContextCompactor` | Deferred | Confirmed unchanged |
| DS F2: daemon thread bridge | Accepted | Confirmed unchanged |
| DS F3: `_input_range` ordering | Deferred | Confirmed unchanged |

## Residual Risks

None introduced by this fix. Original residual risks from source reviews remain:
1. Real provider behavior not covered by no-network unit tests (expected).
2. README sync deferred to Slice 6.

## Stop Status

Re-review artifact complete. All accepted fixes verified. No regressions. Ready for Gateflow controller decision.
