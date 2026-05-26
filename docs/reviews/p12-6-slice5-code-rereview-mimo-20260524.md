# P12.6 Slice 5 Re-Review — AgentMiMo

## 基本信息

- role：AgentMiMo code re-reviewer
- base：410a620 gateflow: accept P12.6 slice 4
- scope：workspace diff，排除 `docs/host/implementation-control.md`
- source artifacts：
  - `docs/reviews/p12-6-slice5-code-review-controller-adjudication-20260524.md`
  - `docs/reviews/p12-6-slice5-fix-codex-20260524.md`
  - `docs/reviews/p12-6-slice5-code-review-mimo-20260524.md`
  - `docs/reviews/p12-6-slice5-code-review-ds-20260524.md`

## Verdict：PASS

## Accepted Fixes 验证

### A1 — `selected_material_source_refs` 提取到单一 Host internal helper ✓

**证据**：
- `compact_material.py:250-268` 新增模块级 `selected_material_source_refs()` 函数，位于 `RunInputMaterialBlock` 之后。
- `compact_material.py` `__all__` 已包含 `"selected_material_source_refs"`。
- `dispatch.py:129` 统一导入：`from dayu.host.compact_material import ... selected_material_source_refs`。
- `engine_ingest.py:64` 统一导入：`from dayu.host.compact_material import ... selected_material_source_refs`。
- `dispatch.py` 与 `engine_ingest.py` 中旧的 `_selected_material_source_refs` 私有实现已删除。
- 两处调用点（`dispatch.py:1394`、`engine_ingest.py:3050,3099`）均使用公共 helper。

**结论**：DRY 违规已消除，两处调用统一到单一 ownership 点。

### A2 — Multi-pass merge 不丢前序 episode summary；pinned patch merge 策略明确 ✓

**证据**：
- `compaction_operation.py:333-334`：`_merge_pass_candidates` 调用 `_merge_episode_summary_candidate` 和 `_merge_pinned_state_patch_candidate` 替代直接取 `last`。
- `_merge_episode_summary_candidate`（`compaction_operation.py:362-413`）：
  - `episode_title` / `goal` / `next_step` 通过 `_merge_required_text` / `_merge_optional_text` 按 pass 顺序用 separator 拼接。
  - `completed_actions` / `confirmed_fact_refs` / `confirmed_fact_summaries` / `user_constraints` / `open_questions` / `tool_finding_refs` / `source_event_refs` / `evidence_refs` / `proposed_evidence_backed_fact_refs` 通过 `_dedupe_strings` 按 pass 顺序去重合并。
- `_merge_pinned_state_patch_candidate`（`compaction_operation.py:416-441`）：
  - `current_goal`（text field）通过 `_merge_text_field_patch` 采用 deterministic last-writer-wins，代码注释明确说明 scalar 值无法无损拼接。
  - `confirmed_subjects` / `user_constraints` / `open_questions`（tuple field）通过 `_merge_tuple_field_patch` 合并所有 pass 的 replace values 和 evidence_refs，CLEAR 操作重置 values。
- 新增测试 `test_reactive_multi_pass_merges_distinct_summary_and_patch`（`test_compaction_operation.py`）覆盖差异化 pass candidate：
  - 断言 `goal` 拼接两 pass 文本。
  - 断言 `completed_actions` / `user_constraints` / `open_questions` 包含两 pass 内容。
  - 断言 `current_goal.value` 使用 pass 2（last-writer-wins）。
  - 断言 tuple patch `confirmed_subjects.value` 合并两 pass values。
  - 断言 `open_questions.evidence_refs` 合并两 pass evidence refs。

**结论**：episode summary 不再丢弃前序 pass；pinned patch merge 策略显式、有代码注释、有差异化测试覆盖。

### A3 — Reactive pass queue 不再用 `max_selected_size_units=0` trick ✓

**证据**：
- `engine_ingest.py` 中 `_reactive_compaction_pass_queue` 直接调用 `_single_block_segment_selection`（`engine_ingest.py:3069-3074`），不再先调用 `select_compact_segment(... max_selected_size_units=0 ...)`。
- 新增 `_single_block_segment_selection` helper（`engine_ingest.py:3109-3149`）：
  - 校验 `block_id` 在冻结 material list 中。
  - 直接构造 `CompactSegmentSelection`，包含 `deterministic_reason_codes=("reactive_single_pass_block",)`。
  - 无间接 trick 参数。
- 代码中无 `max_selected_size_units=0` 出现（review 文档中的引用属于历史记录）。

**结论**：single-block reactive pass selection 现在是直接、显式的实现。

### A4 — README 记录 frozen material list digest/refs durable semantics ✓

**证据**：
- `dayu/host/README.md` diff 新增："reactive compact request 会把 overflow 当时的 frozen material list digest 和 frozen material refs 写入 durable payload，后续 compaction request 与 pass queue 均以该冻结列表为输入边界；同一 reactive operation 内的 material pass 共享 proposal attempt 预算，只有所有 pass 成功后才提交一个 merged CONTEXT_COMPACTED，任一 pass 最终失败只提交一个 CONTEXT_COMPACTION_FAILED。"
- 语句是稳定行为描述，不写实现细节。
- 无旧术语残留。

**结论**：frozen material list durable semantics 已记录，符合 README 职责约束。

## Deferred Items 确认

| Item | 状态 | 说明 |
|------|------|------|
| D1：旧 range collector 删除 | Deferred 到 Slice 7 | `collect_compaction_request_evidence_inputs` 仍在 `compaction_evidence.py:152` 和 `__all__:582` 中，dispatch/engine_ingest 已无调用方。符合裁决。 |
| D2：`budget_after_compact` min non-blocking | 保持 non-blocking | `compaction_operation.py:356` 仍使用 `min(candidate.budget_after_compact for candidate in candidates)`，保守 merge 策略，不阻塞。 |
| D3：proactive pre-start current-only residual | 保持 accepted residual | `_proactive_material_blocks` 仅构造 current input anchor material block，无 AttemptDispatchSnapshot 级完整 view。依赖后续 Slice 6 memory projection。 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| A1 helper 提取到 compact_material.py，两处调用统一 | PASS |
| A2 multi-pass merge 不丢前序 summary / patch，有差异化测试 | PASS |
| A3 reactive pass queue 直接构造 single-block selection | PASS |
| A4 README 记录 frozen material list durable semantics | PASS |
| Deferred items 按裁决保持不变 | PASS |
| pytest 140 passed | PASS |
| pyright 0 errors | PASS |
| git diff --check | PASS |
| 无新增 Any / object / getattr / hasattr / lazy seam | PASS |
| 无反向依赖 / 无新增 durable schema / 无 Engine runner retry 修改 | PASS |
