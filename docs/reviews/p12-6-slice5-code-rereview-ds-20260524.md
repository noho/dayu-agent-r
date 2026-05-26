# P12.6 Slice 5 Code Re-Review — AgentDS

## 基本信息

- **Reviewer**: AgentDS (re-review)
- **Gate**: P12.6 Slice 5 targeted fix acceptance
- **Base**: `410a620`
- **Source artifacts**:
  - Controller adjudication: `docs/reviews/p12-6-slice5-code-review-controller-adjudication-20260524.md`
  - Codex fix report: `docs/reviews/p12-6-slice5-fix-codex-20260524.md`
  - MiMo review: `docs/reviews/p12-6-slice5-code-review-mimo-20260524.md`
  - DS initial review: `docs/reviews/p12-6-slice5-code-review-ds-20260524.md`
- **Scope**: accepted fixes A1-A4 完成度验证，回归检查，deferred items 状态确认

## Verdict: PASS

## 逐项验证

### A1 — selected_material_source_refs 提取到单一 Host internal helper ✅

| 检查项 | 结果 |
|--------|------|
| `compact_material.py:250` 为唯一定义点 | PASS |
| `compact_material.py:1867` `__all__` 导出 | PASS |
| `dispatch.py:129` 统一 import | PASS |
| `engine_ingest.py:64` 统一 import | PASS |
| `dispatch.py` 中旧 `_selected_material_source_refs` 私有定义已删除 | PASS (grep 无匹配) |
| `engine_ingest.py` 中旧 `_selected_material_source_refs` 私有定义已删除 | PASS (grep 无匹配) |
| 两处调用点 (`dispatch.py:1394`, `engine_ingest.py:3050,3099`) 均使用统一 helper | PASS |

### A2 — multi-pass merge 不丢前序 episode summary；pinned patch merge 策略明确并有差异化测试 ✅

| 检查项 | 结果 |
|--------|------|
| `_merge_pass_candidates(313)` 使用 `_merge_episode_summary_candidate` 替代 `last.episode_summary_candidate` | PASS |
| `_merge_pass_candidates(336)` 使用 `_merge_pinned_state_patch_candidate` 替代 `last.pinned_state_patch_candidate` | PASS |
| `_merge_episode_summary_candidate(362)` 去重合并 action/constraint/questions/fact refs/evidence refs，scalar 文本用分隔符合并 | PASS |
| `_merge_pinned_state_patch_candidate(419)` tuple 字段合并所有 pass values/evidence_refs，text 字段 deterministic last-writer-wins 带注释 | PASS |
| 旧 `last.` 模式残留 | PASS (grep 无匹配) |
| 新增 `test_reactive_multi_pass_merges_distinct_summary_and_patch(542)` 覆盖不同 pass candidate 的 summary/patch merge | PASS |
| 测试断言前序 pass 的 action/constraint/question/evidence_refs 不丢失 | PASS |
| 测试断言 tuple patch 合并两个 pass 的 values/evidence_refs，scalar `current_goal` 使用最后一个非 missing patch | PASS |

### A3 — reactive pass queue 不再用 max_selected_size_units=0 trick ✅

| 检查项 | 结果 |
|--------|------|
| `max_selected_size_units=0` 在 `engine_ingest.py` 中出现 | PASS (grep 无匹配，已消除) |
| `_reactive_compaction_pass_queue(3059)` 直接调用 `_single_block_segment_selection` 构造单 block pass selection | PASS |
| `_single_block_segment_selection(3110)` 功能签名完整：接受 `root_request`/`block_id`/`material_blocks` | PASS |

### A4 — README 记录 frozen material list digest/refs durable semantics ✅

| 检查项 | 结果 |
|--------|------|
| `dayu/host/README.md:258` 包含 "frozen material list digest" 语义 | PASS |
| `dayu/host/README.md:258` 包含 "frozen material refs" 语义 | PASS |
| 完整语句: "reactive compact request 会把 overflow 当时的 frozen material list digest 和 frozen material refs 写入 durable payload，后续 compaction request 与 pass queue 均以该冻结列表为输入边界" | PASS |
| 表述为稳定行为描述，无实现细节 | PASS |

## Deferred Items 状态确认

| Item | 状态 | 核实 |
|------|------|------|
| D1: 旧 range collector `collect_compaction_request_evidence_inputs` 删除 | Deferred to Slice 7 | `compaction_evidence.py:152` 仍存在，`__all__:582` 仍导出；`dispatch.py`/`engine_ingest.py` 已移除 import 和调用 |
| D2: `budget_after_compact=min(...)` 保守 merge | Non-blocking | `compaction_operation.py:356` 未修改，符合 controller 裁决 |
| D3: proactive pre-start current-only residual | Accepted residual | 未修改，符合 controller 裁决 |

## 回归检查

| 检查项 | 结果 |
|--------|------|
| pytest (dispatch_scheduler + engine_ingest_mapping + compaction_operation + context_budget) | 140 passed in 4.02s |
| pyright (dispatch.py + engine_ingest.py + compaction_operation.py + context_budget.py + compact_material.py + 对应测试) | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | PASS (per fix artifact) |
| `dispatch.py` 中无遗留旧 `_selected_material_source_refs` | PASS |
| `engine_ingest.py` 中无遗留旧 `_selected_material_source_refs` | PASS |
| `compaction_operation.py` 中无 `last.episode_summary_candidate` / `last.pinned_state_patch_candidate` | PASS |
| 无 `max_selected_size_units=0` 残留 | PASS |

## 无新引入回归

fix A1-A4 均完成了 controller 指定的修复目标，未在类型系统、测试覆盖、架构边界或文档一致性方面引入新回归。新增 `_DistinctPassCompactor` fake 只用于新测试，不影响既有 fake 行为。合并辅助函数 `_merge_episode_summary_candidate` / `_merge_pinned_state_patch_candidate` / `_merge_text_field_patch` / `_merge_tuple_field_patch` 均为纯函数无副作用。

## Residual Risks（不变）

1. 旧 range collector 删除仍 deferred 到 Slice 7
2. proactive pre-dispatch material view 仍是 current-input-only
3. `budget_after_compact=min(...)` 保守估值在 multi-pass 场景可能低估 savings，当前不阻塞
