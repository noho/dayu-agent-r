# Host-owned Compactor Code Review — Slice 1-4 (DeepSeek)

## Gate / Work Unit

- gate: parallel code review for implementation Slice 1-4
- work unit: Host-owned LLM context compactor public opener contract
- review target: uncommitted workspace diff since accepted plan commit `cab7ad0`
- accepted plan: `docs/host/host-owned-compactor-plan.md`
- design source of truth: `docs/host/design.md`
- implementation artifact: `docs/reviews/host-owned-compactor-implementation-slice1-4-codex.md`
- reviewer: DeepSeek (second independent review agent)

## Review Summary

| Criterion | Result |
|---|---|
| 1. Public contract no longer exposes ContextCompactor/CompactorExecutionBaseline | PASS |
| 2. LLMContextCompactor ownership boundaries | PASS |
| 3. ContextBudgetPolicy.max_compaction_attempts_per_operation | PASS |
| 4. CONTEXT_COMPACTION_ATTEMPT_REJECTED event type/builder/validator | PASS |
| 5. Proactive/reactive compaction outside Host write transaction | PASS |
| 6. HostEvent mapping — no new HostEventKind | PASS |
| 7. No Slice 5/6 overstep | PASS |
| **Overall** | **PASS-WITH-RISKS** |

## Criterion 1: Public Contract No Longer Exposes Internal Compaction Types

### Evidence

- `dayu/host/api.py`: `CompactorRunnerBaseline` (line 920–962) replaces `CompactorExecutionBaseline`. Fields: `compactor_runner_spec`, `compactor_runner_options`, `compact_artifact_root`, `compact_artifact_create_parent_dirs`. No `context_compactor`, no `policy_ref`, no prompt fields. **PASS**
- `dayu/host/api.py`: `OpenHostOptions.compactor_runner_baseline` (line 1022) replaces `compactor_baseline`. **PASS**
- `dayu/host/__init__.py`: exports `CompactorRunnerBaseline` (line 58, 154); no longer exports `CompactorExecutionBaseline`. **PASS**
- `dayu/host/api.py` `__all__` (line 2854): exports `CompactorRunnerBaseline`; no `CompactorExecutionBaseline`. **PASS**
- `tests/host/test_public_compact_smoke.py`: no longer constructs `_RealLLMContextCompactor`, no longer imports `CompactorExecutionBaseline`, uses `CompactorRunnerBaseline` with runner/config fields only. Asserts removed: `compactor.call_count >= 1` and `compactor.last_summary is not None`. **PASS**
- `tests/host/public_smoke_support.py`: field rename `compactor_baseline=None` → `compactor_runner_baseline=None`. **PASS**

### Verdict: PASS

## Criterion 2: LLMContextCompactor Ownership Boundaries

### Evidence

- `dayu/host/llm_compaction.py`: `LLMContextCompactor.__init__` (line 134–153) accepts only `runner_spec` and `runner_options`. No prompt, candidate callback, quality callback, artifact writer, policy ref, or cancellation token. **PASS**
- `dayu/host/llm_compaction.py`: `compact()` (line 155–173) performs single proposal: calls `_run_agent_request_sync`, checks for `EngineRunOutcomeFinalAnswer`, validates non-empty summary, returns `_candidate_from_summary()`. No repair loop. **PASS**
- `dayu/host/llm_compaction.py`: `_agent_request()` (line 176–208) sets `disable_tools=True`, `tool_schemas=()`, `_RejectingToolExecutor`, `AgentPolicy(allow_tool_calls=False, max_iterations=1)`. **PASS**
- `dayu/host/llm_compaction.py`: prompt is module-level private constant `_SYSTEM_PROMPT` (line 51–56) — Host-owned, general, financially-neutral. **PASS**
- `dayu/host/llm_compaction.py`: no EventLog writes, no artifact writes, no memory projection updates. **PASS**
- `dayu/host/llm_compaction.py`: no public test-only seams. Tests monkeypatch `dayu.host.llm_compaction.run_agent_and_wait`. **PASS**
- `tests/host/test_llm_compaction.py`: five focused tests cover tool-disabled request construction, final-answer-to-candidate mapping, empty/non-final rejection, Host-owned refs/evidence preservation, and `RunnerSpec.max_retries` passthrough without semantic repair. **PASS**

### Verdict: PASS

## Criterion 3: ContextBudgetPolicy.max_compaction_attempts_per_operation

### Evidence

- `dayu/host/context_policy.py`: field `max_compaction_attempts_per_operation: int` (line 65) in `ContextBudgetPolicy`. **PASS**
- `dayu/host/context_policy.py`: validated with `_require_positive_int` in `__post_init__` (line 123–128). Rejects 0, negative, bool, non-int. **PASS**
- `dayu/host/context_policy.py`: default constant `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 1` (line 25). **PASS**
- Semantically distinct from `max_proactive_compactions_per_run` and `max_reactive_compactions_per_run` — the former is per-operation attempt budget, the latter two are per-Run operation count limits. **PASS**
- `tests/host/test_context_policy.py`: tests cover default value, positive int acceptance, 0 rejection, negative rejection, bool rejection, non-int rejection, and direct constructor with custom value. **PASS**

### Verdict: PASS

## Criterion 4: CONTEXT_COMPACTION_ATTEMPT_REJECTED Event Type/Payload

### Evidence

- `dayu/host/context_events.py`: `CONTEXT_COMPACTION_ATTEMPT_REJECTED = "CONTEXT_COMPACTION_ATTEMPT_REJECTED"` (line 34–35). **PASS**
- `dayu/host/context_events.py`: `build_context_compaction_attempt_rejected_payload()` (line 359–398) constructs payload with required fields: `operation_id`, `attempt_number`, `failure_category`, `repairable`, `runner_attempt_summary_refs`, `diagnostic_refs`, `next_policy_decision`, `budget_after_attempted_compact`. **PASS**
- `dayu/host/context_events.py`: `validate_context_compaction_attempt_rejected_payload()` (line 401–423) validates all required fields, `attempt_number` as positive int (not bool), `runner_attempt_summary_refs` and `diagnostic_refs` as non-empty text lists, `budget_after_attempted_compact` as non-negative int or None. **PASS**
- No sensitive fields: builder does not record API keys, headers, complete prompts, or provider payloads. **PASS**
- `tests/host/test_context_compact_events.py`: 4 dedicated tests — `test_attempt_rejected_payload_builder_and_validator`, `test_attempt_rejected_payload_rejects_missing_required_fields`, `test_attempt_rejected_payload_requires_positive_attempt_number` (parametrized over 0/bool/"bad"), `test_attempt_rejected_payload_requires_non_empty_ref_lists`, `test_attempt_rejected_payload_rejects_invalid_budget`. **PASS**
- `dispatch.py` and `engine_ingest.py` append `CONTEXT_COMPACTION_ATTEMPT_REJECTED` via `build_context_compaction_attempt_rejected_payload` in their respective `_append_compaction_attempt_rejected_event` / `_append_reactive_compaction_attempt_rejected_event` methods. **PASS**

### Verdict: PASS

## Criterion 5: Proactive/Reactive Compaction Outside Host Write Transaction

### Evidence

**Proactive (dispatch.py)**:

- `_prepare_compact_before_dispatch` (line 1147–1231) runs inside write transaction, appends `CONTEXT_COMPACTION_REQUESTED`, returns `_GovernanceCompactPending` with frozen snapshot (`run.status`, `run.input_event_sequence`). **PASS**
- On return from write transaction, `_execute_proactive_compaction` (line 872–1007) calls `_run_compaction_operation` **outside** any transaction. **PASS**
- After LLM call returns, `_execute_proactive_compaction` opens a **new** write transaction (`_operation` inner function, line 943–1006), rechecks `run.status != pending.expected_status or run.input_event_sequence != pending.expected_input_event_sequence` before writing. **PASS**
- Stale result handling (line 946–961): if state changed, writes `CONTEXT_COMPACTION_FAILED` with `failure_reason="stale_compaction_result"` and returns None. **PASS**

**Reactive (engine_ingest.py)**:

- `_ingest_validated` → `_handle_context_compaction_requested` returns `_ReactiveCompactPending` from write transaction (line 1108–1120) with `result_prefix` carrying the request/closeout rows. **PASS**
- Caller at line 553–554: `result = self._transaction_runner.run_write(_operation); if isinstance(result, _ReactiveCompactPending): result = self._execute_reactive_compaction(result)`. The compaction execution is **outside** the write transaction. **PASS**
- `_execute_reactive_compaction` (line 1343–1497) opens a **new** write transaction, revalidates context via `_validate_durable_context`, checks `latest.run.status is not RunStatus.RECOVERING`, and writes COMPACTED or FAILED. **PASS**

**Tests**:

- `test_proactive_compaction_calls_llm_outside_write_transaction`: uses `_TransactionReadableCompactor` that opens an independent read transaction during `compact()`, verifying no write lock conflict. **PASS**
- `test_compaction_stale_result_does_not_write_compacted_event`: uses `_StaleMutatingCompactor` that mutates run state during compact, verifies `CONTEXT_COMPACTED` count is 0 and run is FAILED. **PASS**
- `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`: uses `_RaisingCompactor` with `max_compaction_attempts_per_operation=2`, verifies 2 `ATTEMPT_REJECTED` events and 1 `COMPACTION_FAILED`. **PASS**
- `test_reactive_compaction_calls_llm_outside_write_transaction`: uses `_TransactionReadableCompactor`, verifies compact call count and COMPACTED event. **PASS**

### Verdict: PASS

## Criterion 6: HostEvent Mapping — No New HostEventKind

### Evidence

- `dayu/host/api.py`: `HostEventKind` enum (line 2387–2401) unchanged — PROGRESS, SUCCEEDED, FAILED, CANCELLED. No new members. **PASS**
- `dayu/host/read_api.py`: `_host_event_from_row()` (line 408–436) maps only `RUN_SUCCEEDED` → SUCCEEDED, `RUN_FAILED` → FAILED, `RUN_CANCELLED` → CANCELLED. All other event types (including `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED`) → `HostEventKind.PROGRESS`. **PASS**
- Compact facts remain PROGRESS; Run terminal remains RUN_*. The plan's conservative mapping (§3.6) is faithfully implemented. **PASS**
- No `CONTEXT_COMPACTION_*` references in `read_api.py`. **PASS**

### Verdict: PASS

## Criterion 7: No Slice 5/6 Overstep

### Evidence

- `utils/smoke_host_public_multiturn.py`: **not edited**. **PASS**
- `README.md`, `dayu/host/README.md`, `tests/README.md`: **not edited**. **PASS**
- Controller-approved minimal compile fixes:
  - `tests/host/public_smoke_support.py`: only field rename `compactor_baseline=None` → `compactor_runner_baseline=None`. No behavioral change. **PASS**
  - `tests/host/test_public_compact_smoke.py`: removed `_RealLLMContextCompactor` usage, removed `CompactorExecutionBaseline` import, removed `compactor.call_count`/`compactor.last_summary` assertions, added `CompactorRunnerBaseline` with runner-only fields. Kept `_RealLLMContextCompactor` class definition (will be removed in Slice 5). **PASS**
- Other impacted test files (`test_effective_execution_config.py`, `test_per_run_tool_selection.py`, `test_public_lifecycle_smoke.py`, `test_public_retry_replay.py`, `test_submit_followup_public_contract.py`, `test_watch_session_events.py`) only have field renames. **PASS**

### Verdict: PASS

## Findings

### F1: Code Duplication Between dispatch.py and engine_ingest.py (Maintainability)

**Severity**: LOW

**Evidence**:
- `_run_compaction_operation` (`dispatch.py:2536–2701`) and `_run_reactive_compaction_operation` (`engine_ingest.py:2759–2915`) are near-identical (~170 lines each). The only differences are the `_attempt_rejected` vs `_reactive_attempt_rejected` and `_quality_suffix` vs `_reactive_quality_suffix` helper calls.
- `_CompactionAttemptRejected` and `_CompactionOperationResult` dataclasses are defined identically in both modules.
- `_attempt_rejected` / `_reactive_attempt_rejected` and `_quality_suffix` / `_reactive_quality_suffix` are identical helper pairs.

**Analysis**: The plan explicitly keeps dispatch and ingest as separate governance paths. The duplication is mechanical—both paths share the same compaction operation semantics (proposal loop, quality check, hard threshold check, attempt budget). Consolidating into a shared internal module (e.g., `dayu/host/compaction_operation.py`) would reduce the maintenance surface without coupling the dispatch and ingest governance concerns.

**Recommendation**: Consider extracting the shared compaction operation logic in a future slice. Not blocking for Slice 1-4.

### F2: `_run_agent_request_sync` Daemon Thread Pattern (Correctness/Stability)

**Severity**: LOW

**Evidence**: `dayu/host/llm_compaction.py:211–236`

**Analysis**: When called from within an existing event loop, the compactor spawns a daemon thread running `asyncio.run()`. Daemon threads are abruptly terminated on process exit, and `asyncio.run()` in a non-main thread can have subtle issues on some platforms. The plan acknowledges this constraint (§3.2): "CancellationToken 第一版不从 Service 传入" and "runner timeout / retry 做上界控制". The compactor is a sync adapter bridging the sync `ContextCompactor.compact()` interface to the async Engine runner. This is an acceptable trade-off given the interface constraint.

**Recommendation**: When `ContextCompactor.compact()` is eventually made async, this thread bridge can be removed. Not blocking for Slice 1-4.

### F3: `_input_range` Relies on Input Event Ordering (Correctness)

**Severity**: LOW

**Evidence**: `dayu/host/llm_compaction.py:380–393`

**Analysis**: `_input_range` uses `request.input_event_refs[0]` as `start_input_ref` and `request.input_event_refs[-1]` as `end_input_ref`. This assumes the refs are ordered by event sequence. The `CompactionRequest` is constructed by Host code (in `_prepare_compact_before_dispatch` and `_reactive_compaction_request`), so the ordering is under Host control. However, if a future change to the request construction changes the ordering, the range representation could become misleading.

**Recommendation**: Document the ordering assumption in the `CompactionRequest` docstring or in `_input_range`. Not blocking.

### F4: `operation_id` Reuses `estimator_digest` (Diagnostic Correctness)

**Severity**: LOW

**Evidence**: `dispatch.py:1507` and `engine_ingest.py:1645` — `operation_id=estimate.estimator_digest` in both `_append_compaction_attempt_rejected_event` methods.

**Analysis**: The `estimate.estimator_digest` is used as the `operation_id` in the attempt rejected payload. In theory, two different compaction operations could produce the same budget estimate digest if the inputs and policy are identical. In practice, the estimate includes `run.input_event_sequence` (via the cursor in `_compute_governance_budget`), making collision extremely unlikely within a single Run's lifecycle. The plan's validation does not require a separate operation-scoped UUID.

**Recommendation**: Acceptable as-is. If stronger operation identity is needed in the future, generate a dedicated operation UUID when creating the compaction request.

## Implementation Artifact Validation

The implementation artifact (`docs/reviews/host-owned-compactor-implementation-slice1-4-codex.md`) makes the following claims. Each was checked against the code:

| Claim | Verified? |
|---|---|
| "Replaced Service-facing CompactorExecutionBaseline with CompactorRunnerBaseline" | YES |
| "Replaced OpenHostOptions.compactor_baseline with OpenHostOptions.compactor_runner_baseline" | YES |
| "Removed package-root export of CompactorExecutionBaseline" | YES |
| "Kept ContextCompactor only as Host internal / low-level test seam" | YES |
| "LLMContextCompactor constructor accepts only runner_spec and runner_options" | YES |
| "Added ContextBudgetPolicy.max_compaction_attempts_per_operation with positive-int validation" | YES |
| "open_host constructs Host-owned LLMContextCompactor from CompactorRunnerBaseline" | YES |
| "Added CONTEXT_COMPACTION_ATTEMPT_REJECTED event type, builder, validator, and tests" | YES |
| "Kept compact EventLog facts mapped through existing HostEvent PROGRESS projection" | YES |
| "Split proactive dispatch compaction into request write, transaction-outside, result recheck/write" | YES |
| "Split reactive ingest compaction same way" | YES |
| "Added bounded Host semantic repair attempts" | YES |
| "LLMContextCompactor does not loop for semantic repair and does not write EventLog/artifact/memory" | YES |
| "pyright: 0 errors, 0 warnings, 0 informations" | YES (per implementation artifact) |
| "All listed tests pass" | YES (per implementation artifact) |

All implementation artifact claims that were checked against code are consistent.

## Test Coverage Assessment

| Test file | New/updated tests | Coverage of review criteria |
|---|---|---|
| `test_llm_compaction.py` | 5 new | Compactor constructor, tool-disabled request, candidate mapping, empty/non-final rejection, refs/evidence preservation, max_retries passthrough |
| `test_context_policy.py` | 3 new | max_compaction_attempts_per_operation default, validation, direct constructor |
| `test_context_compact_events.py` | 7 new | attempt rejected builder/validator, missing fields, attempt_number validation, non-empty refs, invalid budget |
| `test_dispatch_scheduler.py` | 3 new | LLM outside write transaction, stale result, repair attempt rejection in EventLog |
| `test_engine_ingest_mapping.py` | 1 new | Reactive LLM outside write transaction |
| `test_open_host_runtime.py` | updated | CompactorRunnerBaseline integration |
| `test_package_exports.py` | updated | Export verification |
| `test_public_open_host_options.py` | updated | CompactorRunnerBaseline validation |

**Gap**: No test explicitly verifying that `CONTEXT_COMPACTION_ATTEMPT_REJECTED` maps to `HostEventKind.PROGRESS` in the HostEvent projection. The design guarantees this structurally (since `_host_event_from_row` only maps RUN_SUCCEEDED/FAILED/CANCELLED to terminal kinds, and everything else defaults to PROGRESS), so the lack of a dedicated test is acceptable but noted.

## Conclusion

**Result: PASS-WITH-RISKS**

The implementation correctly executes Slices 1-4 of the approved plan. All seven review criteria pass. The Service-facing public contract no longer exposes `ContextCompactor` or `CompactorExecutionBaseline`. The Host-owned `LLMContextCompactor` has correct ownership boundaries. The transaction boundary split for proactive and reactive compaction is correctly implemented with state recheck. The `CONTEXT_COMPACTION_ATTEMPT_REJECTED` event type is canonical, well-validated, and tested. HostEvent mapping remains conservative. No Slice 5/6 overstep occurred beyond controller-approved compile fixes.

### Residual Risks

1. **Code duplication** (F1): `_run_compaction_operation` / `_run_reactive_compaction_operation` and associated helpers are near-identical across dispatch.py and engine_ingest.py. Recommend future consolidation.
2. **Daemon thread pattern** (F2): `_run_agent_request_sync` bridges sync/async via daemon thread. Acceptable under current `ContextCompactor.compact()` sync interface constraint.
3. **No HostEvent mapping test** for `CONTEXT_COMPACTION_ATTEMPT_REJECTED → PROGRESS`. Structurally guaranteed but untested.
4. **Real provider behavior**: Not covered by no-network unit tests. Full public compact smoke migration remains Slice 5.
5. **README sync**: Remains Slice 6.
