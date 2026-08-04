# Code Review — Interactive Conversation Memory closure F10

## Scope

- Mode: current changes（未提交 workspace diff）
- Branch: `codex/interactive-oracle`
- Base: `d04f7531f3a7bfef2de004afbb94b2d607704b36`
- Output file: `docs/reviews/wu-interactive-memory-closure-f10-code-review-mimo.md`
- Included scope: 六个 production owner 文件（`compaction.py`、`compact_material.py`、`compact_pipeline.py`、`context_governance.py`、`compaction_operation.py`、`dispatch.py`）、八个测试文件、三个文档（`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`）
- Excluded scope: Engine、Memory projector、RunInput consumer、compact v2 output schema、CLI scenarios、frozen oracle/evidence
- Parallel review coverage: 无

## Review context

- Accepted plan: `wu-interactive-memory-closure-f08-f10-plan-codex.md`
- Accepted amendment: `wu-interactive-memory-closure-f10-plan-amendment-controller-adjudication.md`
- Controller fix: `wu-interactive-memory-closure-f10-plan-amendment-fix-controller.md`
- Implementation artifact: `wu-interactive-memory-closure-f10-implementation-codex.md`

## Findings

未发现实质性问题。

以下是对用户指定的每个 adversarial 检查维度的逐项 evidence-based 复核：

### 1. Semantic owner 漂移 / 下游补偿 / 兼容代码

**结论：无漂移。**

- `_packed_content_digest` 是唯一从 `RunInputMaterialBlock` 到 final-pack content digest 的转换点，定义于 `compact_material.py:1671-1685`，四个调用点（`selected_block_provenance_for_material_blocks`、`_compact_material_block`、`_pack_evidence_blocks`、`_provenance_from_evidence_blocks`）全部直接调用同一 helper，无各自重算。
- `RunInputMaterialBlock.content_digest`（source-boundary 四行业务可读语义）不变，不被冒充为 evidence 的 final-pack digest。
- `_selected_material_blocks`（`compact_material.py:2817-2836`）完全移除了旧的 `_is_current_input_history_duplicate` 过滤，selected packer 不做任何文本去重。same-text/different-ref 保留由 pipeline/operation 的 ref overlap 校验保障。
- 没有 `hasattr`/`getattr`/loose parsing/兼容 shim/默认值 fallback。

### 2. Schema / public surface 扩大

**结论：仅 Host-internal 扩大，LLM-facing 无泄漏。**

- `CompactSegmentSelection` 新增 `scope`、`turn_group_memberships`、`selected_block_provenance`、`root_selection_digest` 四个字段，全部在 `__post_init__` 严格校验。
- `CompactRepairFeedbackV2` 新增 `request_digest`、`source_boundary_digest`，`__post_init__` 强制非空。
- LLM repair projector `_repair_feedback_prompt_json_vnext`（`llm_compaction.py:680-703`）只投影 `required_action` 与 `issues`，两个治理 digest 不暴露。测试 `test_repair_feedback_is_separate_and_requires_whole_candidate`（`test_llm_compaction.py`）显式断言 `"request_digest" not in projected` 和 `"source_boundary_digest" not in projected`。
- `SelectedBlockProvenance`、`TurnGroupMembership`、`CompactSegmentSelectionScope` 均在 `__all__` 中导出，但属于 Host-internal compaction contract，不进入 v2 output schema 或 Memory/RunInput。

### 3. Turn-group atomicity 与严格 budget

**结论：正确实现。**

- `_atomic_material_units`（`compact_material.py:1836-1885`）按稳定 material 顺序归并 turn groups/singletons，group 成员保持 canonical order。
- `_collective_exclusion_reason`（`compact_material.py:2064-2083`）使用 `_COLLECTIVE_EXCLUSION_PRECEDENCE` 固定优先级 tuple（`protected_current_input > protected_recent_raw_floor > already_represented > previous_compacted_view > not_in_segment`），`min(reasons, key=priority.__getitem__)` 确保全组统一 reason。
- Budget 阶段（`select_compact_segment` 内）按 `unit_size_units = sum(block.size_units)` 和 `unit_item_count = len(unit.blocks)` 计算，`exceeds_size_cap` 或 `exceeds_item_cap` 时整组排除并 `budget_blocked = True`，不拆组、不跳过。
- 测试覆盖：`test_turn_group_selection_uses_real_block_count_and_never_splits`（3 blocks per group, item_count=2 全排除）、`test_turn_group_char_cap_accepts_exact_total_and_rejects_one_less`（exact cap 通过、少一全排除）、`test_turn_group_budget_preserves_atomic_prefix_after_oversized_middle`（前组可放、中间大组不可放时不跳到后续小组）。

### 4. SelectedBlockProvenance fail-closed

**结论：对 unknown/same-count/singleton/group swap/ref/digest/transient tampering 全部 fail-closed。**

- **unknown block id**: `selected_block_provenance_for_material_blocks`（`compact_material.py:1960-1990`）对未知 block id 抛出 `ValueError("selected block provenance references unknown material block")`。pipeline `_validate_segment_against_source_snapshot`（`compact_pipeline.py:982-987`）拒绝 `selected_ids` 或 `excluded_ids` 不在 `known_ids` 中的情况。测试 `test_unknown_selected_block_id_fails_against_source_snapshot` 覆盖等数量 unknown ids 复用真实 refs/digest 的反例。
- **same-count swap**: `_sorted_selected_provenance_values`（`compaction_operation.py:1626-1643`）使用 sorted multiset 比较，等数量不同 block 的 (refs, digest) 对排序后不同。测试 `test_whole_group_swap_proof_fails_before_provider` 覆盖等数量完整 group swap。
- **ref tamper**: pipeline 校验 `selected_segment.selected_block_provenance != expected_provenance`（逐字段 `SelectedBlockProvenance` frozen dataclass `__eq__`）。测试 `test_root_selected_provenance_mismatch_fails_before_provider_call` 覆盖 `source_ref` 和 `packed_digest` 篡改。
- **digest tamper**: 同上，`packed_content_digest` 字段不同即拒绝。
- **transient tamper**: `_operation_pass_requests`（`compaction_operation.py:1536-1542`）验证每 pass provenance 是 root provenance 的逐字段 exact subset，且全体 pass 无重叠。测试 `test_reactive_pass_provenance_tamper_fails_before_provider` 覆盖 `root_subset` 和 `pass_pack` 两种篡改。

### 5. Root/transient exact partition 无重叠遗漏

**结论：正确实现。**

- Root: `CompactSegmentSelection.__post_init__`（`compaction.py:1986-1989`）校验 `selected ∩ excluded = ∅`。pipeline `_validate_segment_against_source_snapshot`（`compact_pipeline.py:1000-1002`）对 ROOT 校验 `selected ∪ excluded = known`。
- Transient: `_operation_pass_requests`（`compaction_operation.py:1536-1552`）校验每 pass provenance 是 root exact subset，`observed_pass_block_ids` 无重叠，最终 `observed_pass_block_ids != set(root_provenance_by_id)` 时拒绝。source boundary 同样校验 disjoint exact partition。

### 6. Same-text/different-ref 保留、same-ref current anchor provider 前失败

**结论：正确实现。**

- Packer 不做文本去重：`_selected_material_blocks` 已移除 `_is_current_input_history_duplicate`。
- Same canonical current ref: pipeline `_validate_selected_pack_current_input_separation`（`compact_pipeline.py:1008-1025`）拒绝 selected pack 与 current anchor 共享 canonical ref。operation `_validate_operation_selected_pack`（`compaction_operation.py:1621-1623`）再次校验。
- 测试：`test_same_text_different_ref_preserves_complete_selected_group`（文本相同、ref 不同，完整 group 保留）、`test_same_canonical_current_ref_fails_during_pipeline_request_build`（same ref fail closed）、`test_current_input_ref_overlap_fails_before_provider_call`（operation 层 same ref fail closed）。

### 7. Excluded mapping 真只读且 digest 同源

**结论：正确实现。**

- `CompactSegmentSelection.__post_init__`（`compaction.py:1977-1985`）先 key-sort copy，再 `MappingProxyType` 冻结。`to_json()`（`compaction.py:2022`）使用 `_string_mapping_json` 序列化，与 stored mapping 和 selection digest 共用同一 canonical order。
- 测试 `test_excluded_reason_mapping_is_sorted_copied_and_read_only` 覆盖：传入 reversed mapping → stored 为 sorted；外部 mutation 不影响 frozen；`MappingProxyType` 直接写入抛 `TypeError`。

### 8. Repair feedback request+source-boundary binding 及 cross-tier 清除

**结论：正确实现。**

- `CompactRepairFeedbackV2.__post_init__`（`compaction.py:1661-1670`）强制 `request_digest` 和 `source_boundary_digest` 非空。
- Dispatcher `_repair_feedback_for_request`（`dispatch.py:5797-5816`）只保留精确绑定当前 request 与 source boundary 的 feedback，否则返回 `None`。
- Operation `_repair_feedback_matches_request`（`compaction_operation.py:1646-1660`）在 provider 前再次防御校验，mismatch 使用 `_non_repairable_contract_failure_result` 收口。
- 测试：`test_mismatched_initial_feedback_fails_before_provider_call`（直接注入跨 request feedback）、`test_defensive_feedback_mismatch_stops_schedule_with_single_terminal`（绕过 dispatcher 清理时 operation 拒绝且只收口一次）、`test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback`（tier 变化时 feedback 清空）。

### 9. F09 fixture 迁移是否仅修真实 consumer

**结论：仅修 fixture，未扩大 production boundary。**

- `test_runner_call_hot_payload_contract.py` 的 `_compactor_manifest` fixture 从删除 `runner_call_projection_artifact_*` 字段改为按 F09 canonical manifest contract 提供 compactor-specific ref/digest/size。Production recorder/resolver 未增加兼容 fallback。Implementation artifact 记录 6 个 deterministic failures 全部来自同一 fixture。

### 10. Memory/RunInput/LLM-facing 无治理字段泄漏

**结论：无泄漏。**

- `SelectedBlockProvenance`、`TurnGroupMembership`、`CompactSegmentSelectionScope`、`request_digest`、`source_boundary_digest` 均不进入 `llm_material_json()`、repair projector JSON 或 v2 output schema。
- `_repair_feedback_prompt_json_vnext`（`llm_compaction.py:680-703`）只投影 `required_action` 与 `issues`。
- `CompactSegmentSelection.to_json()` 包含全部字段，但该 JSON 仅用于 Host-internal digest 计算和 audit，不直接投给 LLM。

### 11. CURRENT_INPUT_ANCHOR 在 duplicate section owner 检查中的跳过

**结论：正确且必要。**

- `_raise_on_duplicate_section_owner`（`compact_material.py:2994-3005`）和 `_require_one_section_per_canonical_content`（`compaction.py:2707-2718`）均跳过 `CURRENT_INPUT_ANCHOR` section。
- 这是 F10 移除 selected packer 文本去重后的必然结果：current input anchor 与 selected history 可能共享相同文本（same-text/different-ref 保留场景），此时它们的 `(canonical_source_refs, content_digest)` key 相同。如果不跳过，anchor 的 provenance entry 会与 trace material 的 entry 冲突。
- Anchor 的 ref overlap 已由 pipeline/operation 的 `_validate_selected_pack_current_input_separation` / `_validate_operation_selected_pack` 在更早阶段拒绝，因此 duplicate section owner 跳过不引入安全缺口。

### 12. `initial_segment_selection` 的 provenance 与 excluded_reason_codes

**结论：正确实现。**

- `_initial_selected_block_provenance`（`compact_material.py:1430-1480`）从已构造的 pack block 读取 `content_digest`（即 `_packed_content_digest` 的结果），不重新解释 source text。
- `excluded_reasons` 包含 previous compacted view 的 `previous_compacted_view` reason 和 current anchor 的 `protected_current_input` reason。
- `turn_group_memberships=()` 对 initial path 正确，因为 initial material 没有 raw source snapshot 的 turn group 信息。
- `excluded_protected_ids` 正确只包含 current anchor label。

## Open Questions

无。

## Residual Risk

- 真实 provider 对 F08/F09/F10 的行为与五条正式 CLI scenarios 仍属后续 evidence/readiness gate；本次按明确禁令未运行。
- 全树 Ruff lint/format 是 accepted base 的仓库级债务，F10 精确 lint 均通过。
- `_validate_segment_against_source_snapshot` 对 transient selection 不校验 `selected ∪ excluded = known`（只校验 ROOT），但 transient 的 partition 正确性由 `_operation_pass_requests` 的 exact subset + 无重叠无遗漏校验保障。两层校验的职责分工明确，不存在缺口。

## 结论

**PASS**

F10 实现与 accepted plan/amendment/fix 的可执行规格一致。六个 production owner 文件的改动在 semantic ownership、fail-closed、atomic selection、provenance proof、feedback binding、LLM-facing 隔离各维度均无实质性问题。八个测试文件覆盖了所有关键 happy path、failure path、boundary condition 和 adversarial tampering 场景。337 passed, 1 skipped（opt-in real compactor smoke 按要求未运行）。Pyright 0 errors。
