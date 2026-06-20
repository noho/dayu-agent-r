# PR #152 Review — WU-CM-14 + WU-CM-13

## Reviewed Target

- **PR**: https://github.com/noho/dayu-agent-r/pull/152
- **Branch**: `wu-cm-14-final-answer-preservation` → `main`
- **Commits**: 19 commits (WU-CM-14 plan/fix/review + WU-CM-13 plan/fix/review)
- **Aggregate scope**: 51 files changed, +9567 / −3110 lines
- **Production code**: 5 files in `dayu/host/` (+1739 / −1390 net)
- **Tests**: 6 files in `tests/` (+1804 / −1689 net)
- **Review date**: 2026-06-19

## Review Focus

### 1. PR diff coherence — PASS

PR contains only:
- `dayu/host/` production code (compact_pipeline.py new, compaction_evidence.py deleted, dispatch.py/engine_ingest.py/run_input.py modified)
- `tests/` test code
- `docs/reviews/` review artifacts
- `docs/host/host-issues/` plan artifacts
- `docs/host/issues-implementation-control.md` control doc
- `tests/README.md` test organization update

No changes outside these areas. No unrelated files touched.

### 2. WU-CM-14 recent final answer preservation — PASS

WU-CM-14 motivation: ordinal follow-up "详细解释第三条" requires protected recent raw tail after compact.

**Preservation after WU-CM-13**:
- `select_ordinary_protected_raw_tail(...)` in `compact_pipeline.py` owns selection eligibility
- `_DurableProtectedRecentRawTailProvider` in `run_input.py` delegates to pipeline helper
- `selected_recent_window_turn_floor` threaded from `memory_policy` through all paths
- `_raw_tail_block_represented_by_memory(...)` deduplicates against memory selected recent
- `_message_from_material_block(...)` renders UserMessage / AssistantMessage / SystemMessage

No proactive-only / reactive-only / RunInput-only drift.

### 3. WU-CM-13 proactive/reactive pipeline unification — PASS

| Semantic | Proactive (dispatch.py) | Reactive (engine_ingest.py) | Helper |
|---|---|---|---|
| Source snapshot | `compact_pipeline_source_snapshot_from_pre_dispatch_view(...)` | Same | `compact_pipeline.py` |
| Normal request | `build_normal_compact_request_plan(...)` | Same | `compact_pipeline.py` |
| Recovery tiers | `build_tier_recovery_request_plans(...)` | N/A (reactive uses pass queue) | `compact_pipeline.py` |
| Pass queue | N/A | `build_reactive_pass_queue_plan(...)` | `compact_pipeline.py` |
| Fallback decision | `build_fallback_decision_input(...)` | Same | `compact_pipeline.py` |
| Policy digest | `digest_memory_projection_policy(memory_policy)` | Same | `memory.py` |

Lifecycle state machines remain separate: dispatch.py owns proactive admission/precondition/commit guard; engine_ingest.py owns reactive Attempt closeout/RUN_RECOVERING/recovery Attempt creation.

### 4. Public API/schema/EventLog/Engine contract — unchanged — PASS

| Contract | Verification |
|---|---|
| `dayu/host/__init__.py` | 0 lines diff |
| `dayu/host/api.py` | 0 lines diff |
| `dayu/host/durable/schema.py` | 0 lines diff |
| EventLog event types | `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` / `CONTEXT_COMPACTION_REQUESTED` payload format unchanged |
| Engine contract | No changes to `dayu/engine/` |
| Compact artifact contract | No changes to artifact schema |

### 5. No tier 5 / fallback_tier — PASS

`grep "tier_5\|tier 5\|fallback_tier\|current_input_only" compact_pipeline.py dispatch.py engine_ingest.py run_input.py` → zero hits.

Test assertions confirm: `assert "fallback_tier" not in ...` in `test_compact_pipeline.py:273` and `test_dispatch_scheduler.py:5949`.

### 6. LLM-facing text — no internal ref leakage — PASS

| Protection | Location |
|---|---|
| Evidence source filtering | `compact_pipeline.py:1136-1170` — filters `tool_call_event:`, `tool_result_event:`, `event:`, `eventlog:`, `payload:`, `artifact:`, `digest:` |
| Raw-tail message rendering | `compact_pipeline.py:1080-1127` — `_message_from_material_block(...)` renders without internal refs |
| Fallback message rendering | `run_input.py:2923+` — `_fallback_context_messages(...)` unchanged |

### 7. Tests/smoke — sufficient and not weakened — PASS

| File | Tests | Delta |
|---|---|---|
| `test_compact_pipeline.py` | 11 | +11 (new) |
| `test_compact_material.py` | 50 | +4 (migrated) |
| `test_compaction_operation.py` | 22 | −18 (migrated) |
| `test_dispatch_scheduler.py` | 78 | +0 (1 renamed + strengthened) |
| `test_run_input_builder.py` | 66 | +0 (infrastructure update) |
| **Total** | **227** | **−3 net** |

Migration: 18 evidence tests removed from `test_compaction_operation.py`, 14 migrated to `test_compact_material.py`, 11 new in `test_compact_pipeline.py`. Plan §10 migration table accounts for all 18.

Smoke: `utils/smoke_host_public_conversation_memory_scenarios.py` must pass for final acceptance (not run in this review).

### 8. README trigger scope — PASS

`dayu/host/` changes are internal Host behavior; no user-facing CLI/Web/WeChat workflow, install steps, public commands, or public schema changes. Root README not triggered.

## Findings

### 无 material findings

PR diff is coherent, WU-CM-14 preservation is intact after WU-CM-13, no boundary violations.

## Residual Risks

| ID | Risk | Severity | Tracking |
|---|---|---|---|
| RR-1 | Smoke not run in this review | Low | Must pass for final acceptance |

## Final PR Review Conclusion

**pass**

PR #152 is coherent and contains only WU-CM-14 + WU-CM-13 scope:

- WU-CM-14 protected recent raw-tail preservation is intact after WU-CM-13 pipeline unification
- WU-CM-13 proactive/reactive compact pipeline unification is correct; lifecycle state machines remain separate
- No public API/schema/EventLog/Engine contract drift
- No tier 5 / fallback_tier
- LLM-facing material does not leak internal refs
- Tests sufficient and not weakened (227 tests across 5 files)
- compaction_evidence.py fully deleted with zero remaining references

PR may proceed to accepted PR review commit.
