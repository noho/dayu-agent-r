# WU-PROJ-01 Slice 2 Re-Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: Slice 2 re-review (post-fix)
- 日期: 2026-06-11
- Fix artifact: `docs/reviews/wu-proj-01-slice2-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-proj-01-slice2-code-review-controller-adjudication.md`
- Previous MiMo review: `docs/reviews/wu-proj-01-slice2-code-review-mimo.md`
- Previous DS review: `docs/reviews/wu-proj-01-slice2-code-review-ds.md`
- Diff scope: `tests/host/test_dispatch_scheduler.py`（fix 变更）

## Verdict

**APPROVE** — 2 个 accepted fix items 均已正确修复，未引入新 correctness/type/test/architecture 问题。

## Fix Item 逐项确认

### DS-S2-L2: `_proactive_fallback_material_blocks` current input 追加逻辑边界测试

**Controller 要求**: 新增 focused test，直接断言 material view delta 不包含 current input，fallback material blocks 追加 current input 后不产生重复 current block。

**Fix 实现**: `test_proactive_fallback_material_blocks_append_current_input_once`（line 3892–3944）

**逐条验证**:

| 检查项 | 结果 | 证据 |
|---|---|---|
| 直接断言 material_view.material_blocks 不含 current input source ref | ✅ | line 3922–3925: `assert all(run.input_event_id not in block.canonical_source_refs for block in material_view.material_blocks)` |
| 直接断言 material_view.material_blocks 不含 current input event_sequence | ✅ | line 3926–3929: `assert all(block.event_sequence != run.input_event_sequence for block in material_view.material_blocks)` |
| 断言 fallback blocks 中 current input anchor 只出现一次 | ✅ | line 3935–3942: 按 `CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR` + `run.input_event_id` 过滤后 `assert len(current_input_blocks) == 1` |
| 断言追加的 current input anchor 内容正确 | ✅ | line 3943: `text == current_display_text`；line 3944: `event_sequence == run.input_event_sequence` |
| 使用 `_pre_dispatch_material_view_for_run` 直接构造同源 view | ✅ | line 3911–3915: 通过 `build_pre_dispatch_compact_material_view` 构造，不经过 scheduler 调度 |
| 测试先验证 delta 不含 current input，再验证 fallback 追加后不重复 | ✅ | 两段断言逻辑清晰分离：先验证 source view 不含（line 3917–3929），再验证 fallback 追加后恰好一次（line 3935–3944） |

**结论**: 测试完整覆盖 controller adjudication 要求的全部边界场景。构造方式可信——通过 `_pre_dispatch_material_view_for_run` 直接构造 material view，绕过 scheduler 调度路径，隔离了 fallback 追加逻辑的正确性验证。

### MiMo INFO-3: `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 阈值调整注释

**Controller 要求**: 补简短注释，说明阈值调高是为了让同源 material view 的完整估算超过 soft threshold 但低于 hard threshold，测试目标仍是 proactive compact lifecycle。

**Fix 实现**: line 4653–4658

```python
context_budget_policy=_soft_compact_policy(
    # 同源 material view 估算包含 previous view、delta 与 current input；
    # 这里需超过 soft threshold 且低于 hard threshold，目标仍是 proactive lifecycle。
    context_window_size=200,
    soft_threshold_tokens=60,
    hard_threshold_tokens=160,
),
```

**逐条验证**:

| 检查项 | 结果 | 证据 |
|---|---|---|
| 注释说明了调参原因 | ✅ | "同源 material view 估算包含 previous view、delta 与 current input" |
| 注释说明了阈值约束 | ✅ | "需超过 soft threshold 且低于 hard threshold" |
| 注释说明了测试目标不变 | ✅ | "目标仍是 proactive lifecycle" |
| 注释不掩盖 hard-threshold 行为 | ✅ | 注释明确说"低于 hard threshold"，不暗示 hard-threshold 被绕过或放宽 |
| 阈值参数合理 | ✅ | context_window_size=200, soft=60, hard=160；soft < hard，hard < context_window_size，数学关系正确 |

**结论**: 注释准确、完整，不掩盖任何行为。`_soft_compact_policy` 新增的 `context_window_size` / `soft_threshold_tokens` / `hard_threshold_tokens` 参数化改动也合理，保持了默认值不变（line 5470–5472），不影响其他测试。

## 额外验证

### 文件范围

Controller adjudication 限定 allowed files 为：
- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-proj-01-slice2-fix-codex.md`

Fix 变更仅涉及 `tests/host/test_dispatch_scheduler.py`（+452/-11）。其他未提交文件（`dispatch.py`, `engine_ingest.py`, `test_compact_material.py`, `issues-implementation-control.md`）属于 Slice 2 implementation diff，不在 fix 变更范围内。✅ 符合 allowed files 约束。

### Validation 可信性

| 验证项 | 结果 | 实际复验 |
|---|---|---|
| `pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"` | 19 passed, 48 deselected | ✅ 复验通过（0.63s） |
| `pyright` | 0 errors, 0 warnings, 0 informations | ✅ 复验通过 |

Fix report 声称 19 passed，实际复验 19 passed。✅ 一致。

### 新增测试完整性

Fix 除修复两个 accepted items 外，还新增了以下测试（均为 Slice 2 plan 要求的覆盖项）：

| 新增测试 | 覆盖目标 | 评估 |
|---|---|---|
| `test_proactive_budget_uses_pre_dispatch_material_view` | proactive budget 使用同源 material view | ✅ 断言 `estimated_input_tokens > 20`，验证 budget 包含全量 material |
| `test_proactive_fallback_material_blocks_append_current_input_once` | DS-S2-L2 fix | ✅ 已逐项验证 |
| `test_second_proactive_compact_uses_previous_view_without_old_raw_replay` | 第二次 proactive compact 使用 previous view | ✅ 断言 `previous_compacted_view != ()` 且旧 raw text 不重展 |
| `test_pre_start_governance_material_source_failure_fails_closed` | material source failure fail closed | ✅ 断言 Run FAILED、无 Attempt、failure_reason="material_source_failed" |
| `test_reactive_compact_request_uses_latest_previous_view` | reactive 复用 latest previous view | ✅ 断言 `previous_compacted_view[0].text == "rolled"` |

这些测试增强了 Slice 2 的覆盖深度，且均不超出 Slice 2 plan scope。

### `_soft_compact_policy` 参数化

`_soft_compact_policy` 新增 `context_window_size` / `soft_threshold_tokens` / `hard_threshold_tokens` 参数，默认值保持原值不变。所有现有调用点不受影响。新增参数化逻辑正确：`soft_threshold_tokens=None` 时从 `context_window_size` 计算，否则直接使用。✅ 无回归风险。

## New Findings

无新 findings。

## Blocking Open Questions

无。

## Residual Risks

1. **Deferred findings 未处理** — DS-S2-L1（异常捕获范围）、DS-S2-L3（reactive 不写 compact failed event）、MiMo INFO-1（reactive budget 单 fragment）按 controller adjudication 留给后续 owner。本轮 fix 不涉及这些项目，无新增风险。
2. **Fix 未改 production code** — 两个 accepted items 均为 test/comment 类型，production 代码未变更，无 production regression 风险。

## 结论

| 项目 | 状态 |
|---|---|
| DS-S2-L2 fix | ✅ fixed — 测试直接断言 delta 不含 current input、fallback 追加后恰好一次 |
| MiMo INFO-3 fix | ✅ fixed — 注释准确说明阈值调参原因，不掩盖 hard-threshold 行为 |
| Allowed files 约束 | ✅ 仅改 test file + fix artifact |
| Validation 可信 | ✅ 19 passed, pyright 0 errors，复验一致 |
| 新 correctness/type/test/architecture 问题 | ✅ 无 |
| Verdict | **APPROVE** |
