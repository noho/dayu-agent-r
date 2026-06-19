# WU-CM-13 Aggregate Deepreview

## Reviewed Target

- **Work unit**: WU-CM-13 — Unified conversation compact pipeline convergence
- **Accepted commits**:
  - Slice 1: `0390c9ad` — compact pipeline helper + compaction_evidence.py deletion
  - Slice 2a: `b180a510` — proactive dispatch wiring
  - Slice 2b: `7b0367ab` — reactive ingest wiring
  - Slice 2c: `7aab0f94` — RunInput raw-tail wiring
- **Aggregate scope**: 4 production files changed, 1 deleted, 1 new; 5 test files changed; net +992 / −3133 lines
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Accepted plan**: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- **Review date**: 2026-06-19

## Audit Results

### 1. Proactive/reactive compact request construction share same semantic helper path — PASS

| Call site | Helper | Policy digest source |
|---|---|---|
| `dispatch.py:1756` | `build_normal_compact_request_plan(...)` | `digest_memory_projection_policy(memory_policy)` |
| `engine_ingest.py:1619` | `build_normal_compact_request_plan(...)` | `digest_memory_projection_policy(memory_policy)` |

Both paths construct `CompactPipelineSourceSnapshot` via `compact_pipeline_source_snapshot_from_pre_dispatch_view(...)` from the same `build_pre_dispatch_compact_material_view(...)` output. The `CompactionRequest` is produced by the same `_request_plan_from_segment(...)` internal helper in `compact_pipeline.py`.

**No duplicate helpers remain**: `grep` for `select_compact_segment` / `build_compact_material_pack` / `_selected_evidence_refs` / `_selected_raw_turn_refs` / `_dedupe_texts` / `_proactive_compaction_recovery_request` in dispatch.py and engine_ingest.py returns zero hits.

### 2. Recovery/pass queue/fallback decision — no duplicate owners — PASS

| Semantic | Helper | Call site |
|---|---|---|
| Tier 1/2/3 recovery | `build_tier_recovery_request_plans(...)` | `dispatch.py:1512` |
| Reactive pass queue | `build_reactive_pass_queue_plan(...)` | `engine_ingest.py:1630` |
| Fallback decision (proactive) | `build_fallback_decision_input(...)` | `dispatch.py:1996` |
| Fallback decision (reactive) | `build_fallback_decision_input(...)` | `engine_ingest.py:1722` |

All four helpers are in `compact_pipeline.py`. No duplicate construction logic remains in dispatch.py or engine_ingest.py.

### 3. Ordinary post-compaction raw-tail — pipeline-owned selection — PASS

| Path | Selection owner | Provider |
|---|---|---|
| Proactive post-compact | `select_ordinary_protected_raw_tail(...)` via `_DurableProtectedRecentRawTailProvider` | `run_input.py:1483` |
| Reactive post-compact | Same provider (recovery dispatch creates new Attempt, same Run) | `run_input.py:1483` |
| RunInput ordinary branch | `load_ordinary_raw_tail(...)` | `run_input.py:1978` |

**WU-CM-14 preservation**: No proactive-only / reactive-only / RunInput-only drift. The selection eligibility is owned by `select_ordinary_protected_raw_tail(...)` in `compact_pipeline.py`, using `protected_recent_turn_group_ids_for_material_blocks(...)` and `_raw_tail_block_represented_by_memory(...)`. The second-read provider still exists (EventLog fresh read) but delegates selection to the pipeline helper.

### 4. Fallback branch unchanged; no tier 5 — PASS

- `_fallback_context_messages(...)` remains in `run_input.py:2020` (line unchanged)
- `grep "tier_5\|tier 5\|fallback_tier\|current_input_only" compact_pipeline.py dispatch.py engine_ingest.py run_input.py` → zero hits
- Test assertions confirm: `assert "fallback_tier" not in failed_input.fallback_input_window` (`test_compact_pipeline.py:273`, `test_dispatch_scheduler.py:5949`)

### 5. LLM-facing material — no internal ref leakage — PASS

| Protection | Location | Mechanism |
|---|---|---|
| Evidence source filtering | `compact_pipeline.py:1136-1170` | `_llm_facing_evidence_source_text(...)` filters `tool_call_event:`, `tool_result_event:`, `event:`, `eventlog:`, `payload:`, `artifact:`, `digest:` |
| Raw-tail message rendering | `compact_pipeline.py:1080-1127` | `_message_from_material_block(...)` renders UserMessage / AssistantMessage / SystemMessage without exposing event ids, payload refs, or digests |
| Fallback message rendering | `run_input.py:2923+` | `_fallback_context_messages(...)` unchanged, uses existing `_fallback_message_from_material_block(...)` |

**Test verification**: `test_ordinary_protected_raw_tail_filters_internal_evidence_source` asserts `source=filing page 12` is visible while `event-tool-result-new` and `payload-new` are filtered.

### 6. WU-CM-13-S1-R1: compact quality/provenance coverage — CLOSED

The S1-R1 residual was: "Malformed compacted payload / evidence-label edge coverage is not explicit at the new helper boundary."

**Closure evidence**:
- `build_compacted_payload_input(...)` accepts typed `ConversationCompactOutputVNext`, not raw JSON. Malformed JSON payload input is rejected at `ConversationCompactOutputVNext` parse time (in `compaction.py`), before reaching the pipeline helper. The old malformed JSON edge case no longer applies at this boundary.
- Evidence-label validation is handled by `accepted_evidence_mapping_refs_for_candidate(...)` in `compact_payload.py`.
- Migrated tests in `test_compact_material.py` cover: descriptor raw payload, missing request atoms, payload damage fail-closed, malformed envelope, missing raw outcome, producer mismatch.
- `test_compact_pipeline.py` covers: accepted payload semantic refs derivation, fallback decision input construction.

**Decision**: S1-R1 is closed. The typed contract boundary eliminates the malformed JSON edge case; remaining evidence-label validation is covered by existing `compact_payload.py` tests and migrated `test_compact_material.py` tests.

### 7. Public API/schema/EventLog/Engine contract — unchanged — PASS

| Contract | Verification |
|---|---|
| `dayu/host/__init__.py` | `git diff` → 0 lines |
| `dayu/host/api.py` | `git diff` → 0 lines |
| `dayu/host/durable/schema.py` | `git diff` → 0 lines |
| EventLog event types | `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` / `CONTEXT_COMPACTION_REQUESTED` payload format unchanged |
| Engine contract | No changes to `dayu/engine/` |
| Compact artifact contract | No changes to artifact schema |

### 8. Smoke hard gate — NOT RUN (intentional)

`utils/smoke_host_public_conversation_memory_scenarios.py` was not run during this aggregate review. Per accepted plan §13 item 12: "This smoke verifies public Host conversation memory behavior does not regress; helper convergence itself is verified by focused unit/integration tests above." The smoke must pass for WU-CM-13 final acceptance but is not a prerequisite for aggregate deepreview conclusion.

## Residual Risk Decisions

| ID | Status | Decision |
|---|---|---|
| `WU-CM-13-S1-R1` compact quality/provenance edge | **closed** | Typed contract boundary eliminates malformed JSON edge; evidence-label validation covered by compact_payload.py and migrated tests |
| `WU-CM-13-S1-R2` duplicate dedupe/selection helpers | **closed** | Slice 2a/2b removed all duplicate helpers from dispatch.py and engine_ingest.py |
| `WU-CM-14-RR-1` reactive material convergence | **closed** | All paths now use shared pipeline helpers |
| `WU-CM-14-RR-3` EventLog second-read | **closed** | Second-read remains caller-owned for freshness; selection semantics are pipeline-owned |

## Test Coverage Summary

| File | Tests | Delta |
|---|---|---|
| `test_compact_pipeline.py` | 11 | +11 (new) |
| `test_compact_material.py` | 50 | +4 (migrated from compaction_evidence) |
| `test_compaction_operation.py` | 22 | −18 (evidence tests migrated) |
| `test_dispatch_scheduler.py` | 78 | 0 (1 renamed + strengthened) |
| `test_run_input_builder.py` | 66 | 0 (infrastructure update for CONTEXT_COMPACTION_REQUESTED seed) |
| **Total** | **227** | **−3 net** |

The −3 net is explained by: 18 evidence tests removed from test_compaction_operation.py, 14 migrated to test_compact_material.py, 11 new in test_compact_pipeline.py, 0 deleted from other files. The migration table in plan §10 accounts for all 18 removed tests.

## Final Aggregate Deepreview Conclusion

**pass**

WU-CM-13 is correctly implemented across all four accepted slices:

1. **Shared semantic path**: Proactive and reactive compact request construction, recovery, pass queue, fallback decision, and ordinary raw-tail selection all flow through `compact_pipeline.py` helpers. No duplicate helper owners remain.

2. **WU-CM-14 preservation**: Protected recent raw-tail selection is pipeline-owned across proactive, reactive, and RunInput paths. No drift.

3. **Boundary compliance**: No tier 5, no fallback_tier, no public API/schema/EventLog/Engine contract changes. `compaction_evidence.py` fully deleted with zero remaining references.

4. **LLM-facing safety**: Evidence source filtering prevents internal provenance leakage. Raw-tail message rendering exposes only business-readable content.

5. **Tests**: 227 tests across 5 files. Migrated tests cover equivalent scenarios. New tests cover pipeline-specific behavior. No weakening.

6. **S1-R1 closed**: Typed contract boundary eliminates the malformed JSON edge case.

7. **Smoke**: Not run in this review (intentional). Must pass for final acceptance.
