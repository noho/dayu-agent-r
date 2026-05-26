# Aggregate Deepreview Controller Adjudication — Conversation Memory Optimize

- **Date**: 2026-05-26
- **Branch**: `feat/phase-12-5-conversation-memory-optimize`
- **Gate**: aggregate deepreview adjudication
- **Reviewed artifacts**:
  - `docs/reviews/gateflow-aggregate-deepreview-conversation-memory-optimize-ds-20260526.md`
  - `docs/reviews/gateflow-aggregate-deepreview-conversation-memory-optimize-mimo-20260526.md`

## Verdict

PASS. No aggregate deepreview finding is accepted as blocking for the current gate.

## Finding Adjudication

### Rejected — DS Finding 6: multi-pass compaction operation attempt counter starvation

The finding claims that sharing `attempt_number` across reactive multi-pass compaction can starve later passes after an earlier pass consumes the configured `max_attempts`.

Controller decision: rejected as a defect. This is the approved design, not an implementation bug.

Direct evidence:

- `docs/host/design.md:2685-2687` defines `max_compaction_attempts_per_operation` as the total number of external LLM proposal calls for one Host compaction operation.
- `docs/host/design.md:2805-2809` defines reactive multi-pass as material block batch processing inside one compaction operation, with pass proposals consuming the same operation budget and failing closed when repair budget is exhausted.
- `docs/reviews/p12-6-slice5-implementation-codex-20260524.md:30` records that all multi-pass passes share `max_compaction_attempts_per_operation`.
- `docs/reviews/p12-6-slice5-code-review-ds-20260524.md:121` previously reviewed the same `attempt_number` loop and marked shared budget semantics as correct.
- `tests/host/test_compaction_operation.py:669-687` explicitly asserts that reactive passes share the operation attempt budget.

Changing the loop to reset attempts per pass would silently change the bounded Host governance contract and could multiply external LLM proposal calls by the number of material passes. That would violate the current design unless a later phase explicitly introduces a separate `max_material_block_passes_per_operation` or per-pass repair budget.

### Deferred — `_payload_with_terminal_summary` text policy divergence

Accepted as a real maintainability risk but not blocking this gate. It was already tracked as a cross-phase residual item before this work unit. Owner: later Host memory/refactor phase.

### Deferred — LOW production-hardening findings

Deferred as residual tracking, not blocking:

- reactive non-`RECOVERING` compact discard has weak diagnostics;
- `_compact_pressure_reserve_tokens` dead branch and duplicate pressure padding computation in the manual smoke;
- `OpaqueEvidenceRef` does not enforce the Host-neutral kind allowlist directly;
- `_propagate_active_worker_cancel` logs exception type without full exception detail;
- `ActiveWorkerRegistry.cancel_all` snapshot window relies on scheduler close task cancellation as the second line of defense;
- query text readability, confirmed subjects dedupe, payload digest hot-path optimization, evidence chunk boundary awareness, and related LOW observations.

## Coverage Notes

AgentDS completed the aggregate review with six subagent coverage lanes and returned PASS. AgentMiMo returned PASS but one compaction/material subagent did not finish before the controller timeout; MiMo listed that portion under "Areas Not Fully Covered" while still covering the same files through main-review path walking. The missing subagent result is a coverage limitation, not evidence of a blocking defect.

## Validation Evidence

Implementation validations reviewed:

- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q` — 58 passed.
- `python -m pyright dayu/ tests/ utils/` — 0 errors, 0 warnings, 0 informations.
- `python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE` — `SMOKE PASS public Host conversation memory finance continuity`.

Previously completed branch validations and smoke runs remain recorded in the phase and implementation artifacts.
