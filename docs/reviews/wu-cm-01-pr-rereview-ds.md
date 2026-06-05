# WU-CM-01 PR Re-Review — AgentDS

- **Gate**: PR review re-review
- **PR**: https://github.com/noho/dayu-agent-r/pull/116
- **Base artifact**: `docs/reviews/wu-cm-01-pr-review-controller-adjudication.md`
- **Fix artifact**: `docs/reviews/wu-cm-01-pr-review-fix-codex.md`
- **Review date**: 2026-06-04
- **Scope**: 仅复核 controller adjudication 中 7 项 Accepted Findings 的修复完成情况
- **Verdict**: **PASS**

## 复核摘要

对 controller adjudication 中 7 项 Accepted Findings 逐项复核，全部修复完成，无残留问题。未发现新的 design source drift 或 AGENTS.md 违规。Deferred / Rejected findings 未被错误修改。

## Accepted Findings 逐项复核

### F-1 — `_PAYLOAD_FIELD_DISPLAY_TEXT` 重复定义 ✅ 已修复

- **文件**: `dayu/host/memory.py`
- **证据**: `_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"` 仅在 line 71 定义一次。原 line 84 的重复定义已删除。grep 确认该常量仅在 line 71、1648、1829、2905 出现，后三处均为引用。

### F-2 — `previous_compacted_view` 五类 stable view 映射 ✅ 已修复

- **文件**: `dayu/host/compact_material.py:2015-2041`, `tests/host/test_compact_material.py:427-483`
- **证据**:
  - `_previous_compacted_view_vnext()` 现在调用五个独立映射函数：`_previous_compacted_session_summary_vnext`、`_previous_compacted_fact_material_vnext`、`_previous_compacted_answer_anchors_vnext`、`_previous_compacted_forward_intents_vnext`、`_previous_compacted_references_vnext`
  - 当所有五类均为空时返回 `None`，否则构造完整 `CompactReadableViewVNext`，包含全部五字段
  - 新增 `_parse_previous_forward_intent_text()` (line 2059) 与 `_parse_previous_reference_continuity_text()` (line 2088) 从 stable block 文本格式还原结构化数据
  - 测试 `test_conversation_compact_input_vnext_previous_view_maps_stable_blocks` (line 427) 断言五类字段全部映射：`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`

### F-3 — `USER_VISIBLE_RUN_STATE` 进入 vNext trace material ✅ 已修复

- **文件**: `dayu/host/compact_material.py:1856-1881`, `tests/host/test_compact_material.py:486-509`
- **证据**:
  - `_trace_material_vnext()` 现在处理 `USER_INPUT` 和 `USER_VISIBLE_RUN_STATE` 两种 block kind，分别映射为 `TraceReadableKindVNext.USER_INPUT` 和 `TraceReadableKindVNext.USER_VISIBLE_RUN_STATE`
  - `ASSISTANT_FINAL_ANSWER` 由 `_ordinary_section_for_kind()` (line 983-984) 路由到 `ANSWER_MATERIAL`，由 `_answer_material_vnext()` (line 1884-1895) 单独处理——未引入 duplicate section owner
  - 测试 `test_conversation_compact_input_vnext_maps_user_visible_state_to_trace` (line 486) 断言 `USER_VISIBLE_RUN_STATE` 以 `trace_kind="user_visible_run_state"` 进入 `trace_material`

### F-4 — `dayu/config/README.md` 列出 memory_projection_policy 字段 ✅ 已修复

- **文件**: `dayu/config/README.md:92-115`
- **证据**: 新增完整字段表格，包含全部 20 个 `memory_projection_policy` 字段：`context_window_size`、`selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`selected_recent_window_turn_floor`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`、`evidence_fact_item_cap`、`evidence_fact_char_cap`、`evidence_fact_floor`、`session_summary_char_cap`、`answer_anchor_item_cap`、`answer_anchor_char_cap`、`forward_intent_item_cap`、`forward_intent_char_cap`、`reference_continuity_item_cap`、`reference_continuity_char_cap`、`reference_continuity_item_floor`、`max_lag_events_for_inline_delta`、`max_delta_repair_events`、`policy_ref`。字段与 `execution_profiles.json` 实际字段一致，无未来计划表述。

### F-5 — `_required_text()` 死代码删除 ✅ 已修复

- **文件**: `dayu/host/compact_material.py`
- **证据**: `_required_text()` 函数（原 line 2007-2020）已完全删除。grep 确认 `def _required_text` 无匹配。原调用点替换为直接使用 `_require_non_empty_text` 进行显式校验。不再存在 "接收 `str | None` 但 None 分支不可达" 的类型语义误导。
- **注意**: 现场仍有多处 `_require_non_empty_text` 调用（line 208, 213, 220, 699, 748, 752, 756, 786, 1172），这些是正常的前置校验，不是死代码。

### F-6 — Inline delta repair view missing 不再使用错误 repair reason ✅ 已修复

- **文件**: `dayu/host/memory.py:195`, `dayu/host/compact_material.py:829-836`, `dayu/host/dispatch.py:2679-2680`, `tests/host/test_compact_material.py:570-587`, `tests/host/test_dispatch_scheduler.py:1077-1105`
- **证据**:
  - 新增 `MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING = "inline_delta_repair_view_missing"` (memory.py:195)
  - `check_compact_memory_snapshot_cursor` 中三个 repair 分支语义正确：
    1. `lag_events > max_lag_events_for_inline_delta` → `SNAPSHOT_LAG_OVER_THRESHOLD` (line 824) —— 真正大滞后
    2. `inline_delta_repair_view is None` → `INLINE_DELTA_REPAIR_VIEW_MISSING` (line 832) —— view 缺失
    3. inline repair 后仍滞后 → `SNAPSHOT_LAG_OVER_THRESHOLD` (line 847) —— repair 不足
  - Dispatch 逻辑（dispatch.py:2679）仅对 `SNAPSHOT_LAG_OVER_THRESHOLD` 触发 rebuild retry，`INLINE_DELTA_REPAIR_VIEW_MISSING` 走 re-raise 路径（不触发重建）
  - 测试 `test_snapshot_cursor_missing_inline_delta_view_has_accurate_reason` (test_compact_material.py:570) 断言 view 缺失时抛出 `INLINE_DELTA_REPAIR_VIEW_MISSING`
  - Dispatch 测试 `_InlineDeltaRepairViewMissingBuilder` (test_dispatch_scheduler.py:1077) 使用新 reason 构造 repair request，验证不触发大滞后 rebuild retry

### F-7 — `TraceMemoryView` 设计真源字段同步 ✅ 已修复

- **文件**: `docs/host/design.md:2756-2758`, `docs/host/design.md:2790`
- **证据**:
  - `TraceMemoryView` 现在列出 `selected_recent_window: list[SelectedRecentWindowItem]` 与 `reference_continuity_items: list[ReferenceContinuityItem]`（line 2756-2758）
  - Section 24.5 描述同步为 "TraceMemoryView 当前字段为 selected recent window 与 reference continuity items"（line 2790）
  - 未新增不存在的 schema（如 `reference_continuity_memory`），与代码 `memory.py:645-649` 中 `TraceMemoryView` 的 dataclass 定义一致

## Deferred / Rejected Findings 状态

对 controller adjudication 中 Deferred (D-1~D-5) 与 Rejected (D-3) findings 进行完整性检查：

| Finding | 状态 | 检查结果 |
|---------|------|---------|
| D-1: `__all__` 缺失 | Deferred | 未被错误修改；`memory.py` 仍无 `__all__` |
| D-2: string category → enum | Deferred | 未被错误修改；`compaction_operation.py` 仍使用 `str` |
| D-3: `_empty_string_tuple()` | Rejected | 未被错误修改；函数仍存在 |
| D-4: slice1 诊断常量 | Deferred | 未被错误修改；常量仍在 |
| D-5: 测试覆盖增强 | Deferred | 未被错误修改 |

**结论**: 无 deferred/rejected finding 被错误修改。

## 未发现新 Design Source Drift

对以下项目进行补充检查：

| 检查项 | 结果 |
|--------|------|
| 设计真源 24.3 `previous_compacted_view` 字段与代码 `CompactReadableViewVNext` 一致 | PASS |
| 设计真源 24.4 `TraceMemoryView` 字段与代码一致 | PASS |
| `dayu/config/README.md` 字段与 `execution_profiles.json` 一致 | PASS |
| `docs/host/design.md` 中 vNext memory projection schema 与代码一致 | PASS |
| 五类 session memory 命名在代码、测试、设计文档、README 中一致 | PASS |

## AGENTS.md 违规检查

| 检查项 | 结果 |
|--------|------|
| 无反向依赖 | PASS |
| 无 `# type: ignore` / `# pyright: ignore` 扩散 | PASS |
| 无新的 `Any` 类型 | PASS |
| 无新的兼容性 re-export / wrapper | PASS |
| 文档只同步当前事实，无"未来计划" | PASS |
| `dayu.runtime` 未新增业务层 import | PASS |

## 验证命令与结果

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py \
  tests/host/test_memory_projection.py tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py -q
# => 135 passed in 1.54s

source .venv/bin/activate && pytest tests/service/test_host_assembly.py \
  tests/runtime/test_config_loader.py -q
# => 67 passed in 0.42s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# => 0 errors, 0 warnings, 0 informations

git diff --check
# => (无输出)
```

## Residual Risks

1. **Forward intent / reference continuity 文本解析依赖本模块文本格式**: `_parse_previous_forward_intent_text()` 与 `_parse_previous_reference_continuity_text()` 基于 `_PREVIOUS_FORWARD_INTENT_PREFIX` / `_PREVIOUS_REFERENCE_PREFIX` 等模块内私有常量的格式约定进行字符串解析。若未来 stable block 文本格式变更（如改为结构化多 block），需要同步更新解析逻辑。当前测试覆盖了 happy path，但格式畸变路径（如 `ValueError` 分支）未经直接测试覆盖。

2. **`USER_VISIBLE_RUN_STATE` trace_kind 枚举值未经 `CompactReadableViewVNext` 端到端测试**: 当前测试验证了 `USER_VISIBLE_RUN_STATE` 进入 `trace_material` 且 `trace_kind` 正确，但 compact output → next input 闭环的端到端路径（如 vNext compact output 中 trace_material 被下一次 compact 的 `_trace_material_vnext` 正确消费）未直接测试。

3. **未执行完整仓库测试**: 本轮按 controller adjudication 的 required validation 范围覆盖受影响测试，未执行 `pytest tests/host -q` 全量 Host 测试套件。
