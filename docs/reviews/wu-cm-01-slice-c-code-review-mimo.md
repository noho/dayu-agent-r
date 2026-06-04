# WU-CM-01 Slice C Code Review

## Gate

- Work unit: WU-CM-01 Conversation Memory
- Gate: Slice C code review
- Reviewer: mimo
- Artifact path: `docs/reviews/wu-cm-01-slice-c-code-review-mimo.md`
- Scope: uncommitted workspace changes for Slice C full vertical closure

## Verdict

**PASS with 2 advisory findings, 0 blocking findings.**

## Findings

### Advisory-1: `run_input.py` compact artifact message path retains old payload field readers

**Severity**: advisory
**Files**: `dayu/host/run_input.py:128-134`, `dayu/host/run_input.py:2287-2314`, `dayu/host/run_input.py:2663-2729`

**Evidence**: `_compact_artifact_message_content` (line 2663) reads old payload fields `episode_summary_candidate` (line 2708), `preserved_fact_refs` (line 2684/2691), `goal` (line 2712), `open_questions` (line 2714), `user_constraints` (line 2713). These fields do not exist in vNext `CONTEXT_COMPACTED` payloads. The functions handle absence gracefully (return None/empty), so no runtime failure. But these are dead code paths for vNext payloads and retain old mental model (`episode_summary`, `goal`, `open_questions`, `preserved_fact_refs`).

**Why non-blocking**: The functions correctly return None/empty for vNext payloads, so no incorrect behavior. The compact artifact message will include `compact_artifact_ref`, `compact_artifact_digest`, `compacted_event_id`, `compacted_event_sequence`, and empty `preserved_fact_refs=` for vNext payloads. This is functionally correct but leaves dead code.

**Recommendation**: In a future cleanup pass, replace `_optional_summary_text_from_compacted_payload` and `_preserved_fact_refs_summary` with vNext-aware readers that extract session summary and accepted evidence mapping refs from the vNext candidate. This is not blocking because the old readers are harmlessly inert.

### Advisory-2: Budget limiting logic in `memory.py` lacks direct unit test coverage

**Severity**: advisory
**Files**: `dayu/host/memory.py:1913-2045` (`_limit_selected_recent_window`, `_limit_facts`, `_limit_reference_items`, `_limit_anchors`, `_limit_intents`), `tests/host/test_memory_projection.py`

**Evidence**: The old `test_memory_projection.py` contained tests for fact budget limiting (`test_evidence_backed_fact_budget_keeps_latest_facts_and_records_diagnostic`), working assumption budget, continuity budget, and stable layer budget. The new test file has 11 tests covering policy contract, snapshot contract, pre-compact projection, accepted compact materialization, accepted evidence without fact diagnostic, failed compaction rejection, JSON round-trip, checkpoint atomicity, consumer projection, policy digest, and empty snapshot. None of these directly test that `_limit_facts`, `_limit_reference_items`, `_limit_anchors`, or `_limit_intents` correctly truncate when budget is exceeded and record `BUDGET_LIMIT_REACHED` diagnostics.

The `test_run_input_builder.py` tests use pre-built snapshots (not projected through `project_conversation_memory_event`), so they don't exercise the budget limiting paths either.

**Why non-blocking**: The budget limiting functions are structurally straightforward (sort by event_sequence descending, keep items until char cap is exceeded). The integration path through RunInputBuilder is tested. The missing coverage is specifically the unit-level assertion that exceeding a per-section cap produces the correct diagnostic and truncation.

**Recommendation**: Add 1-2 focused tests to `test_memory_projection.py` that project events with facts/anchors/intents exceeding their respective char caps and assert `BUDGET_LIMIT_REACHED` diagnostics and correct truncation.

## Positive Verification Checklist

### Policy contract alignment with design source

- `MemoryProjectionPolicy` has exactly 20 fields matching `docs/host/design.md` line 95: `context_window_size`, `selected_recent_window_item_cap`, `selected_recent_window_char_cap`, `selected_recent_window_turn_floor`, `fallback_selected_recent_window_item_cap`, `fallback_selected_recent_window_char_cap`, `evidence_fact_item_cap`, `evidence_fact_char_cap`, `evidence_fact_floor`, `session_summary_char_cap`, `answer_anchor_item_cap`, `answer_anchor_char_cap`, `forward_intent_item_cap`, `forward_intent_char_cap`, `reference_continuity_item_cap`, `reference_continuity_char_cap`, `reference_continuity_item_floor`, `max_lag_events_for_inline_delta`, `max_delta_repair_events`, `policy_ref`.
- No old/generic policy fields remain (`max_working_assumptions`, `history_pool_*`, `stable_layer_*`, `raw_turn_*`, `max_pinned_items`, `recent_raw_turns_floor` are all gone).
- No alias, wrapper, default fill, extra payload, or dual-field reading detected.
- `execution_profiles.json`, `config_loader.py`, `host_assembly.py` all use the same 20-field set.
- Policy validation includes cross-field constraints (fallback caps <= normal caps, fallback item cap >= turn floor, floors <= caps).

### Durable schema scope expansion

- `host_memory_items.item_kind` CHECK now includes: `evidence_backed_fact`, `selected_recent_window`, `reference_continuity`, `answer_anchor`, `forward_intent`, `session_summary` (old kinds removed).
- `host_memory_diagnostics.reason` CHECK now includes `accepted_evidence_without_fact_candidate` and removes `minimum_preserve_item_covered`.
- No old kind bridge or alias detected.
- `_validate_snapshot_item_kinds` in `durable/memory.py` uses the same vNext kind set.

### Snapshot/checkpoint transaction ordering

- `write_memory_snapshot_with_checkpoint` (line 486) writes snapshot first via `write_memory_snapshot`, then advances checkpoint. Checkpoint never precedes snapshot within the same transaction.
- `test_write_snapshot_with_checkpoint_commits_snapshot_before_checkpoint` explicitly verifies this ordering.

### Accepted CONTEXT_COMPACTED materialization

- `_accepted_candidate_mapping` validates `schema_version == "conversation_compact_output_v1"` before materialization.
- `_facts_from_accepted_event` materializes facts from `evidence_backed_facts` in the accepted candidate.
- `_session_summary_from_accepted_event`, `_answer_anchors_from_accepted_event`, `_forward_intents_from_accepted_event`, `_reference_continuity_from_accepted_event` materialize the other four memory section types.
- Invalid/rejected/failed compaction events do not reach materialization (they raise in `_accepted_candidate_mapping` or are handled by the caller).
- `test_accepted_compact_materializes_vnext_memory_sections` and `test_failed_compaction_event_does_not_materialize_memory_sections` cover both paths.

### Accepted evidence without fact candidate

- `_facts_from_accepted_event` (line ~2420) checks `len(evidence_refs) > 0 and len(fact_values) == 0` and returns `ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE` diagnostic without synthesizing a fallback fact.
- `test_accepted_evidence_without_fact_candidate_records_diagnostic_only` covers this path.

### RunInputBuilder / compact material vNext rendering

- RunInputBuilder renders vNext sections in fixed order: Session Summary, Evidence/Fact, Answer Anchor, Forward Intent, Reference Continuity, selected recent window.
- Old stable block headers (`Memory user goals and constraints`, `Memory confirmed subjects and methodology`, `Memory open questions and working assumptions`, `Memory minimum preserve continuity`, `Memory episode summaries`) are all removed.
- Compact material `_previous_blocks_from_snapshot` reads from vNext snapshot fields (session_summary, evidence_facts, answer_anchors, forward_intents, reference_continuity).
- No old snapshot renderer wrapper detected in `run_input.py` or `compact_material.py`.

### Duplicate material section owner test replacement

- Old test `test_material_pack_one_to_one_section_mapping_rejects_duplicate_content` raised `DuplicateMaterialSectionOwnerError` for same-section duplicate content.
- New test `test_vnext_snapshot_does_not_bridge_old_goal_into_previous_view` verifies that vNext snapshot doesn't produce goal blocks in previous compacted view, and duplicate blocks go into `trace_material` without error.
- `DuplicateMaterialSectionOwnerError` still exists in `compact_material.py` for cross-section duplicates (line 1779). The test change is correct because vNext snapshots don't have goals, so the old duplicate scenario doesn't apply.

### README synchronization

- `dayu/config/README.md`: Updated `memory_projection_policy` description from ratio/floor/cap to per-section cap/floor with explicit field list. Within config README responsibilities.
- `dayu/host/README.md`: Updated Memory Projection section to describe vNext snapshot, policy, and rendering. Removed old stable layer / history pool / pinned-state / working assumption terminology. Within host README responsibilities.
- `tests/README.md`: Updated P12.6 memory semantic smoke description to reflect vNext test coverage. Within tests README responsibilities.
- No future plans or roadmap content detected in any README.

### Test migration integrity

- Removed tests correspond to deleted vNext concepts (pinned_state, working_assumptions, open_questions, episode_summary, minimum_preserve).
- New tests cover vNext equivalents (policy contract, snapshot contract, pre-compact projection, accepted compact materialization, accepted evidence diagnostic, failed compaction rejection, JSON round-trip, checkpoint atomicity).
- `tests/host/test_compact_material.py`: fixture and helper migration to vNext snapshot types is correct.
- `tests/host/test_run_input_builder.py`: rendering assertions updated to vNext section headers and field names.
- `tests/host/test_public_compact_smoke.py`, `tests/host/test_public_contracts.py`, `tests/service/test_host_assembly.py`, `tests/runtime/test_config_loader.py`: all pass.

### Validation results

All commands run with `source .venv/bin/activate`:

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py tests/host/test_memory_repair.py -q` -> `62 passed`
- `pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py -q` -> `59 passed`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q` -> `66 passed`
- `pytest tests/host/test_public_compact_smoke.py tests/host/test_public_contracts.py -q` -> `45 passed, 1 skipped`
- `python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`
