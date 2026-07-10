# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-c-s2-code-review-mimo.md`
- Included scope: `dayu/host/compact_material.py`, `dayu/host/compact_payload.py`, `dayu/host/compact_pipeline.py`, `dayu/host/compaction.py`, `dayu/host/compaction_operation.py`, `dayu/host/context_budget.py`, `dayu/host/llm_compaction.py`, `dayu/host/run_input.py`, `dayu/host/README.md`, `docs/host/issues-implementation-control.md`, `tests/README.md`, `tests/host/test_compact_material.py`, `tests/host/test_compact_pipeline.py`, `tests/host/test_compaction_operation.py`, `tests/host/test_context_budget.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_run_input_builder.py`
- Excluded scope: 无
- Parallel review coverage: 无

## Review Method

按 P3-C S2 既定 8 项审查清单逐项走读，每项绑定到具体代码路径和直接证据。

### 审查 1：previous compacted view 是否只由 typed candidate 产生 blocks + CompactReadableViewVNext pair

**结论：符合。**

直接证据：
- `compact_material.py:_previous_compacted_view_pair_from_compacted_event()` (行 ~2038) 调用 `parse_context_compacted_semantic_payload(payload).accepted_candidate` 获取 typed `ConversationCompactOutputVNext`。
- `_previous_compacted_view_pair_from_candidate()` (行 ~2077) 从同一个 typed candidate 原子生成 blocks 和 `CompactReadableViewVNext`。
- `validate_previous_compacted_view_pair()` 在 `compaction.py` (行 2185-2261) 做 exact invariant 校验：presence 一致性、kind 合法、label 唯一、每项 label+text 逐字匹配。
- `CompactMaterialPack.__post_init__()` 调用 `_require_previous_compacted_view_pair()` 校验。
- `PreDispatchCompactMaterialView.__post_init__()` 调用 `validate_previous_compacted_view_pair()` 校验。
- `CompactPipelineSourceSnapshot.__post_init__()` 调用 `validate_previous_compacted_view_pair()` 校验。
- `build_compact_material_pack()` 在 `previous_compacted_view is not None` 分支调用 `validate_previous_compacted_view_pair()` 校验。

旧的 `_candidate_*` 字符串解析函数（`_candidate_session_summary_text`, `_candidate_facts_texts`, `_candidate_answer_anchor_texts`, `_candidate_forward_intent_texts`, `_candidate_reference_continuity_texts`）已全部删除。旧的 `_previous_compacted_view_vnext()` blocks-to-typed-view 逆向解析函数已删除。旧的 `_snapshot_*_texts` 函数和 `_previous_blocks_from_snapshot()` 已删除。源码搜索零匹配确认。

### 审查 2：tier2/tier3 是否只通过 transform_previous_compacted_view_pair_for_recovery 同步过滤

**结论：符合。**

直接证据：
- `compact_pipeline.py:build_tier_recovery_request_plans()` 中 tier2 使用 `retained_previous_compacted_view_labels_for_recovery()` 获取 retained labels，再调用 `transform_previous_compacted_view_pair_for_recovery()` 同步过滤 blocks 和 readable_view。
- tier3 使用 `transform_previous_compacted_view_pair_for_recovery(blocks=..., readable_view=..., retained_block_labels=frozenset())` 生成空 pair。
- 旧的 `degrade_previous_compacted_view_for_recovery()` 已删除，替换为 `retained_previous_compacted_view_labels_for_recovery()` + `transform_previous_compacted_view_pair_for_recovery()` 两步。
- `transform_previous_compacted_view_pair_for_recovery()` 内部先 `validate_previous_compacted_view_pair()`，再按 retained labels 过滤 blocks，再从 readable_view 中按 label 映射保留对应 typed items，最后再次 `validate_previous_compacted_view_pair()` 校验输出 pair。
- 测试 `test_degrade_previous_compacted_view_keeps_highest_priority_section_exact` 和 `test_degrade_previous_compacted_view_preserves_verified_pair_order` 验证了 tier2 同步过滤 blocks 和 readable_view 的行为。

### 审查 3：compact_material.py / run_input.py 是否删除旧 string round-trip 和旧渲染路径

**结论：符合。**

直接证据（源码搜索零匹配）：
- `_compact_material_source_ref` — 已删除。
- `_compact_artifact_message_content` — 已删除。
- `_accepted_compacted_view_prefix` — 已删除。
- `_accepted_evidence_mapping_refs` (run_input.py 中的旧版本) — 已删除。
- `_vnext_compact_candidate_semantic_lines` — 已删除。
- `_accepted_compact_fact_lines`, `_accepted_compact_answer_anchor_lines`, `_accepted_compact_forward_intent_lines`, `_accepted_compact_reference_lines` — 已删除。
- `_optional_session_summary_text` — 已删除。
- `_required_mapping_field`, `_required_mapping_list_field`, `_required_text_list_field`, `_optional_text_list_field`, `_optional_semantic_text_field` — 已删除。
- `compact.messages` 在 `_build_ordinary_run_input` 中的 `*compact.messages` 展开 — 已删除。
- `build_run_input_material_blocks()` 的 `compact` 参数 — 已删除。
- compact material loop（`for index, message in enumerate(compact.messages)`）— 已删除。

`DurableCompactArtifactProvider.load_compact_artifact()` 现在使用 `parse_context_compacted_semantic_payload(payload)` 获取 typed payload，不再自行解释 nested candidate JSON。`CompactArtifactView` 不再包含 `messages` 字段。ordinary RunInput 从 memory 渲染 accepted compact 一次（memory projection 物化后），不从 compact artifact provider 直接渲染。

### 审查 4：CompactArtifactView / CompactPipelineCompactArtifactView protocol 是否符合 S2

**结论：符合。**

直接证据：
- `run_input.py:CompactArtifactView` (行 407-420)：字段为 `compaction_event_ref: str | None`, `compact_artifact_ref: str | None`, `compact_artifact_digest: str | None`, `represented_evidence_refs: tuple[str, ...]`。无 `messages` 字段。
- `compact_pipeline.py:CompactPipelineCompactArtifactView` (行 150-169)：Protocol 只声明 `compact_artifact_ref` 和 `compact_artifact_digest` 两个 property。无 `messages`，无 `represented_evidence_refs`。
- `CompactArtifactView` 是 concrete view，保留 `compaction_event_ref` 和 `represented_evidence_refs` 作为 provenance。
- structural subtype 成立：`CompactArtifactView` 实现了 `CompactPipelineCompactArtifactView` 的所有 protocol 成员。

### 审查 5：RunInputBuilder compact event ref 与 memory latest compaction ref repair matrix

**结论：符合。**

直接证据：
- `_require_compact_memory_event_ref_consistency()` (run_input.py 行 3084-3116)：
  - `compact_ref is None and memory_ref is None` → pass（无 compaction 历史）
  - `compact_ref is not None and memory_ref == compact_ref` → pass（一致）
  - `compact_ref is not None and memory_ref is None` → `MemoryProjectionRepairRequired`（memory 落后）
  - `compact_ref is None and memory_ref is not None` → `MemoryProjectionRepairRequired`（memory 有未知 compaction ref）
  - `compact_ref is not None and memory_ref is not None and compact_ref != memory_ref` → `MemoryProjectionRepairRequired`（不同源）
- 调用点在 `RunInputBuilder._build_ordinary_run_input()` 中，位于 `memory` 和 `compact` 加载之后、任何后续消费之前。
- 不会 mismatch 时继续读取 raw tail/manifest/dispatch：repair 异常中断构建流程。

测试覆盖：`test_no_compact_event_and_no_memory_compaction_ref_builds_without_repair`, `test_matching_compact_and_memory_compaction_event_refs_build_once`, `test_compact_event_without_memory_compaction_ref_requires_repair`, `test_memory_compaction_ref_without_compact_event_requires_repair`, `test_mismatched_compact_and_memory_compaction_event_refs_require_repair`。

`_latest_compacted_event_before_attempt()` SQL 已移除 `run_id` 过滤，改为 session 级查询。docstring 已更新为"当前 Session 在 Attempt start cursor 前最新"。

### 审查 6：post-compact budget 归 context_budget owner，llm_compaction dead constants 原地删除

**结论：符合。**

直接证据：
- `context_budget.py:estimate_post_compact_budget()` (行 494-517) 接收 `compacted_business_texts: tuple[str, ...]` 和 `current_input_text: str`，只统计业务文本 token + message overhead。diagnostics 不参与预算。
- `context_budget.py:POST_COMPACT_BASE_MESSAGE_COUNT = 2` 已添加并导出。
- `compaction_operation.py` 中的 `_budget_after_compact_candidate()` 和 `_candidate_text_fragments()` 已删除（源码搜索零匹配）。
- `compaction_operation.py:run_compaction_operation()` 改为调用 `estimate_post_compact_budget(compacted_business_texts=accepted_compact_business_texts(candidate), current_input_text=compact_input.current_input_anchor.text)`。
- `compact_payload.py:accepted_compact_business_texts()` (行 158-187) 收集 candidate 业务文本（summary, facts, anchors, intents, references），不含 diagnostics。
- `llm_compaction.py` 中的 `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`, `_POST_COMPACT_BASE_MESSAGE_COUNT`, `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` 已删除（源码搜索零匹配）。无 alias / re-export。

### 审查 7：S3 scope 是否未提前实现

**结论：符合。**

直接证据：
- accepted evidence renderer / mismatch 旧路径在 run_input.py 中保留（`accepted_evidence_envelope_from_payload` 调用、`_accepted_evidence_mapping_refs` 从 semantic payload 读取），这些是 S1 已有路径，S2 diff 未新增或破坏。
- S2 diff 对这些路径的唯一改动是将 `_accepted_evidence_mapping_refs(payload)` 替换为 `parse_context_compacted_semantic_payload(payload).accepted_evidence_mapping_refs`，属于 S2 统一 typed read boundary 的自然结果。
- `_proposal_failure_offending_block()`, `_previous_reference_continuity_line_invalid()`, `_offending_block_locator()`, `_has_reference_continuity_blocks()` 已从 `compaction_operation.py` 删除，因为旧的 string exception protocol 不再存在。
- `_proposal_failure_stage()` 中的 `has_reference_blocks` 参数和相关分支已删除，`exception_message` 参数被 `del exception_message` 消除。

### 审查 8：README/test updates 是否符合职责

**结论：符合。**

直接证据：
- `dayu/host/README.md` 更新了 RunInputBuilder 和 Context governance 章节，准确描述了 S2 变更：compact artifact provenance-only、ordinary RunInput 不渲染 compact artifact 为第二条 system message、memory/compact ref 一致性检查、post-compact budget 归 context budget owner。
- `tests/README.md` 更新了 P12.6 记录，准确反映了新增测试点：typed previous view、previous blocks 与 typed readable view exact invariant、compact event ref 与 memory latest compaction ref 一致性矩阵、accepted compact 后预算只统计业务文本且 diagnostics 不计入。
- `docs/host/issues-implementation-control.md` 更新了 next entry point 记录。
- 测试全部通过（259 passed, 1.19s）。
- pyright 0 errors, 0 warnings, 0 informations。
- per-file coverage 均 >= 80%：compact_material 86%, compact_payload 83%, compact_pipeline 93%, compaction 85%, compaction_operation 83%, context_budget 93%, llm_compaction 90%, run_input 88%。总体 87%。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `_require_compact_memory_event_ref_consistency()` 在 `compact_ref is None and memory_ref is not None` 场景使用 `MemoryRepairReason.SNAPSHOT_DAMAGED`。语义上这是"memory 有未知 compaction ref"而非"damaged"，但不影响功能正确性。若未来新增更精细的 repair reason 分类，可进一步细化。当前不构成 S2 defect。
