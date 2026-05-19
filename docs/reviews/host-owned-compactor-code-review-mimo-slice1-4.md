# Host-owned Compactor Code Review: Slice 1-4

## Review Identity

- **Reviewer**: MiMo
- **Review target**: uncommitted workspace diff since accepted plan commit `cab7ad0`
- **Approved plan**: `docs/host/host-owned-compactor-plan.md`
- **Design source of truth**: `docs/host/design.md`
- **Implementation artifact**: `docs/reviews/host-owned-compactor-implementation-slice1-4-codex.md`
- **Date**: 2026-05-19

## Conclusion

**PASS-WITH-RISKS**

Implementation correctly satisfies all Slice 1-4 public contract, host-owned compactor, transaction boundary, and event mapping requirements. Two residual risks should be tracked for follow-up.

## Correctness Verification Matrix

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Public contract no longer exposes `ContextCompactor` / `CompactorExecutionBaseline` / `compactor_baseline` / `raw policy_ref` | PASS | `api.py:920-963` `CompactorRunnerBaseline` has no `context_compactor` or `policy_ref` field. `__init__.py:58` exports `CompactorRunnerBaseline`, not `CompactorExecutionBaseline`. `test_package_exports.py:160-174,191` asserts removed. |
| Host-owned `LLMContextCompactor` does not own semantic repair loop | PASS | `llm_compaction.py:155-173` `compact()` calls `_run_agent_request_sync` once, maps result, raises on failure. No retry loop. `dispatch.py:2536-2615` and `engine_ingest.py:2759-2838` own bounded repair via `max_compaction_attempts_per_operation`. |
| `LLMContextCompactor` does not write EventLog / artifact / memory | PASS | `llm_compaction.py` imports no EventLog, artifact store, or memory module. |
| `LLMContextCompactor` disables tools | PASS | `llm_compaction.py:196-208` `disable_tools=True`, `tool_schemas=()`, `_RejectingToolExecutor`, `allow_tool_calls=False`. |
| `LLMContextCompactor` does not add public test-only seams | PASS | `llm_compaction.py:448` `__all__` exports only `LLMCompactionProposalError` and `LLMContextCompactor`. Constructor only accepts `runner_spec` and `runner_options`. |
| `max_compaction_attempts_per_operation` semantics correct and distinct | PASS | `context_policy.py:65` field exists; `context_policy.py:123-128` validates positive int. Distinct from `max_proactive_compactions_per_run` (per-Run limit) and `max_reactive_compactions_per_run` (per-Run limit). `max_compaction_attempts_per_operation` is per-operation (single compaction invocation). `test_context_policy.py:31-48` validates. |
| `CONTEXT_COMPACTION_ATTEMPT_REJECTED` event type / payload / validator correct, canonical, tested | PASS | `context_events.py:34` constant defined. `context_events.py:359-423` builder and validator with all required fields. `test_context_compact_events.py:252-334` covers success, missing fields, bad `attempt_number`, empty refs, invalid budget. |
| Attempt rejected payload does not record sensitive prompt / provider payload | PASS | Payload fields: `operation_id`, `attempt_number`, `failure_category`, `repairable`, `runner_attempt_summary_refs`, `diagnostic_refs`, `next_policy_decision`, `budget_after_attempted_compact`. No prompt, headers, API key, or provider body. |
| Proactive compact calls LLM outside write transaction | PASS | `dispatch.py:892` first `run_write` returns `compact_pending`; `dispatch.py:895` calls `_execute_proactive_compaction` outside; `dispatch.py:1002` second `run_write` writes result. `test_dispatch_scheduler.py:2052-2078` verifies. |
| Reactive compact calls LLM outside write transaction | PASS | `engine_ingest.py:552` first `run_write` returns `_ReactiveCompactPending`; `engine_ingest.py:554` calls `_execute_reactive_compaction` outside; `engine_ingest.py:1375-1451` second `run_write` writes result. `test_engine_ingest_mapping.py:416-435` verifies. |
| State / cursor recheck before writing COMPACTED / FAILED | PASS | `dispatch.py:944-949` rechecks `run.status`, `run.input_event_sequence`. `engine_ingest.py:1378-1387` rechecks `latest.run.status`, `latest.attempt.terminal_event_id`. |
| Stale result does not write `CONTEXT_COMPACTED` | PASS | `dispatch.py:950-961` writes `CONTEXT_COMPACTION_FAILED` with `stale_compaction_result` when state changed. `test_dispatch_scheduler.py:2082-2109` verifies no `CONTEXT_COMPACTED` for stale result. |
| HostEvent mapping does not add `HostEventKind` | PASS | `read_api.py:419-436` only maps `RUN_SUCCEEDED`/`RUN_FAILED`/`RUN_CANCELLED` to terminal kinds; all others (including `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED`) fall through to `HostEventKind.PROGRESS`. No new `HostEventKind` member added. |
| Run terminal remains `RUN_*` | PASS | `dispatch.py` and `engine_ingest.py` terminal events use `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`. Compact facts are intermediate. |
| Did not overstep Slice 5/6 beyond approved minimal compile fix | PASS | `public_smoke_support.py`: single line rename `compactor_baseline` → `compactor_runner_baseline`. `test_public_compact_smoke.py`: import rename, `CompactorRunnerBaseline` usage, removed `compactor.call_count`/`last_summary` assertions. `utils/smoke_host_public_multiturn.py` and READMEs not touched. |

## Findings

### F-1: Duplicated compaction operation logic across dispatch.py and engine_ingest.py

- **Severity**: MEDIUM (maintainability)
- **Location**: `dispatch.py:247-269,2536-2615` and `engine_ingest.py:330-351,2759-2838`
- **Description**: Both modules define nearly identical `_CompactionAttemptRejected` dataclass, `_CompactionOperationResult` dataclass, and `_run_compaction_operation` / `_run_reactive_compaction_operation` functions. The loop structure (iterate attempts, catch proposal failure, check quality, check hard threshold, record rejected) is duplicated verbatim. Only the helper names (`_attempt_rejected` vs `_reactive_attempt_rejected`, `_quality_suffix` vs `_reactive_quality_suffix`) differ.
- **Why it matters**: Per project encoding constraint "重复逻辑必须抽取", shared logic should be extracted. If compaction operation semantics evolve (e.g., new failure category, new validation step), both modules must be updated in lockstep.
- **Recommendation**: Extract `_CompactionAttemptRejected`, `_CompactionOperationResult`, and the bounded-retry loop into a shared location (e.g., `dayu/host/compaction_operation.py` or extend `dayu/host/compaction.py`). Both dispatch and engine_ingest would call the shared operation function with their own request builder and event-writer callbacks.

### F-2: Missing HostEvent projection contract tests from plan verification matrix

- **Severity**: LOW (test coverage gap)
- **Location**: Plan §6.2 lists `test_compaction_attempt_rejected_maps_to_progress_host_event` and `test_runner_provider_retry_does_not_emit_host_event` as required.
- **Description**: These tests do not exist in the workspace. The behavioral guarantee is enforced by code in `read_api.py:419-436` which maps only `RUN_SUCCEEDED`/`RUN_FAILED`/`RUN_CANCELLED` to terminal kinds. No new `HostEventKind` was added. However, the absence of these tests means the HostEvent projection contract for compact events is not explicitly documented by a test.
- **Why it matters**: If someone later adds a new `HostEventKind` or modifies `_host_event_from_row`, there's no test to catch accidental terminal mapping of compact events.
- **Recommendation**: Add at least `test_compaction_attempt_rejected_maps_to_progress_host_event` to `test_context_compact_events.py` or `test_dispatch_scheduler.py` to pin the PROGRESS mapping contract.

### F-3: Dead code residual in test_public_compact_smoke.py

- **Severity**: LOW (dead code)
- **Location**: `test_public_compact_smoke.py` still contains the `_RealLLMContextCompactor` class definition (not shown in diff, but not removed).
- **Description**: The minimal compile fix removed the instantiation and assertions but left the class definition in the file. This is dead code since it's no longer imported or used by the test function.
- **Why it matters**: The class is a residual from the pre-refactor public contract pattern. It will be fully removed in Slice 5.
- **Recommendation**: No action needed for this review; tracked as Slice 5 cleanup.

## Validation Claims Cross-Check

The implementation artifact claims the following validations passed:

| Claim | Verified |
|-------|----------|
| `pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q` → 14 passed | Not re-run; code structure verified correct |
| `pytest tests/host/test_context_policy.py tests/host/test_llm_compaction.py tests/host/test_open_host_runtime.py tests/host/test_context_compact_events.py -q` → 35 passed | Not re-run; code structure verified correct |
| `pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q` → 68 passed | Not re-run; code structure verified correct |
| `pyright dayu/host tests/host` → 0 errors | Not re-run |
| `git diff --check` → passed | Not re-run |

## Residual Risks for Implementation Review

1. **Duplicated compaction operation logic** (F-1): Functional correctness is not at risk, but future maintenance requires updating two parallel implementations. Recommend extracting to shared module before the next compaction-related change.
2. **Missing HostEvent projection tests** (F-2): Behavioral guarantee exists in code but is not pinned by a test. Low risk since the mapping logic is simple and centralized.
3. **Real provider behavior**: No-network unit tests cover the Host-owned compactor contract. Real provider behavior (timeout, rate limit, malformed output) remains untested in CI. This is expected and env-gated.

## Scope Confirmation

All files reviewed within the approved Slice 1-4 scope plus controller-approved minimal Slice 5 compile fix. No files outside the approved list were modified. Slice 5 (smoke migration) and Slice 6 (README sync) are explicitly out of scope.
