# WU-CM-15 Implementation Artifact

## Gate

- Gate: implementation only.
- Work unit: WU-CM-15 Conversation memory public smoke reactive compact and fallback coverage.
- Accepted plan commit: `97518e93`.
- Implementation stopped before code review. No commit, push, PR, merge, control-doc edit, README edit, review gate, or fix gate was performed.

## Scope

Changed files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `docs/reviews/wu-cm-15-implementation-codex-20260620.md`

Observed pre-existing dirty file not touched by this implementation:

- `docs/host/issues-implementation-control.md`

## Implementation Decisions

- Added `SuiteMode.MEMORY_REACTIVE_COMPACT` and `SuiteMode.MEMORY_COMPACT_FALLBACK`.
- Kept `memory-compact` strict: proactive request, proactive accepted compact, compact artifacts, and `CONTEXT_COMPACTION_FAILED` remains a hard failure.
- Added suite-specific acceptance helpers for reactive compact and fallback dispatch instead of weakening `_assert_compact_acceptance`.
- Added smoke-local deterministic worker infrastructure. The worker records both `AgentRunRequest` and `AttemptDispatchSnapshot` in `accept(snapshot, request)` and is injected with `dataclasses.replace(...)` after normal `compose_open_host_options(...)`.
- Added smoke-local compactor runner patch context for deterministic accepted compact and deterministic semantic rejection. Runtime utils do not import `tests`.
- Extended `CompactFailedOperationAudit` with bounded fallback window refs: `selected_block_ids`, `dropped_block_ids`, and `current_input_ref`.
- Kept stdout bounded to audit counts, operation ids, dispatch ids, fallback refs/counts, and artifact paths. It does not print full pressure blobs, compactor prompts, provider payloads, or per-delta stream logs.
- Split pressure behavior by suite: deterministic fallback keeps a strong single-run pressure to force proactive compact; existing `memory-compact` uses more conservative pressure to reduce hard-threshold pre-dispatch failures in long real-provider smoke.

## Validation

Passed:

- `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Result: `18 passed`.
- `pytest tests/host/test_public_compact_smoke.py::test_public_reactive_compact_recovers_with_followup_attempt tests/host/test_public_compact_smoke.py::test_public_compact_failure_dispatches_deterministic_recent_window -q`
  - Result: `2 passed`.
- `pytest tests/host/test_dispatch_scheduler.py::test_reactive_overflow_recovers_and_dispatches_new_attempt tests/host/test_dispatch_scheduler.py::test_reactive_root_compact_selection_passes_protected_recent_floor tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view tests/host/test_dispatch_scheduler.py::test_reactive_fallback_pipeline_uses_memory_policy_caps tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free tests/host/test_run_input_builder.py::test_fallback_provider_renders_only_selected_window_and_current_input tests/host/test_run_input_builder.py::test_fallback_context_messages_render_all_and_only_selected_blocks tests/host/test_run_input_builder.py::test_fallback_context_messages_fail_closed_on_protected_group_mismatch -q`
  - Result: `8 passed`.
- `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL`
  - Result: passed. Observed `requested_reactive=1`, `compacted_reactive=1`, `failed_reactive=0`, new recovery attempt id, and final `SMOKE PASS`.
- `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL`
  - Result: passed. Observed `requested_proactive=1`, `failed_proactive=1`, `fallback_action=dispatch`, selected and dropped fallback ids, and final `SMOKE PASS`.
- `python -m pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - Result: `0 errors`.
- `python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors`.
- `git diff --check`
  - Result: passed.

Not passed:

- `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact --pressure-mode auto --log-level CRITICAL`
  - Result: failed in the existing real-provider long smoke compactor path.
  - Final run progressed through `long-l25-constraint-assert`, observed `requested_proactive=2`, `compacted_proactive=0`, `failed_proactive=2`, then failed strict proactive acceptance with `RuntimeError: memory-compact did not observe proactive CONTEXT_COMPACTED`.
  - Direct evidence: compact reject diagnostics contained `compactor runner failed error_code=client_error recoverable=False message={"error":{"message":"Authentication Fails, Your api key: <redacted> is invalid","type":"authentication_error","param":null,"code":"invalid_request_error"}}`.
  - Earlier exploratory runs also exposed pressure sensitivity before the final reserve adjustment, but the final required-command failure is the unavailable real-provider authentication path above. The new deterministic reactive and fallback suites did not make real provider calls and passed.

## Docs / README Decision

- No README update.
- `tests/README.md` was checked by trigger rule scope: this change adds focused tests and does not alter test organization, test-running contract, or reader-facing test guidance.
- No `dayu/host`, `dayu/engine`, `dayu/config`, user-facing CLI workflow, or control doc change was made.

## Residual Risk / Uncovered Areas

- Existing `memory-compact` remains a real-provider, long-output smoke. The strict proactive acceptance helper remains intact, but the required command could not validate accepted proactive compact with `test-provider-key` because the real compactor provider rejected authentication and Host correctly recorded compact failures/fallback dispatches instead of `CONTEXT_COMPACTED`.
- The new deterministic suites cover reactive compact and deterministic fallback through public Host flow, but they intentionally do not validate real provider response quality.

## Completion Status

- Implementation scope for WU-CM-15 new reactive/fallback public smoke coverage is complete and ready for code review.
- Required validation is partially complete: all focused tests, new deterministic smoke commands, pyright, and diff checks passed; the existing `memory-compact` real-provider smoke command remains a residual failure with direct evidence above.
