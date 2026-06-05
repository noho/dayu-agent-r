# WU-CM-01 PR Review Re-Review — AgentMiMo

## Gate

- Work unit: WU-CM-01
- Gate: PR review re-review
- Scope: 复核 controller adjudication Accepted Findings 修复是否完成，确认未处理 Deferred / Rejected findings，未引入新 design source drift 或 AGENTS.md 违规。
- PR: https://github.com/noho/dayu-agent-r/pull/116
- Review artifacts:
  - `docs/reviews/wu-cm-01-pr-review-controller-adjudication.md`
  - `docs/reviews/wu-cm-01-pr-review-fix-codex.md`

## Verdict

**PASS**

全部 7 项 Accepted Findings 修复完成，验证证据充分。5 项 Deferred / Rejected findings 未被处理，未引入新 design source drift 或 AGENTS.md 违规。

## Accepted Findings 逐项复核

### F-1 `_PAYLOAD_FIELD_DISPLAY_TEXT` 重复定义

- **状态**: FIXED
- **证据**: `dayu/host/memory.py:71` 仅有一处 `_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"`。原 L84 重复定义已删除。Grep 搜索全模块仅返回 1 处定义。
- **裁决**: 通过。

### F-2 `previous_compacted_view` 五类 stable view 映射

- **状态**: FIXED
- **证据**: `dayu/host/compact_material.py:2015-2041` — `_previous_compacted_view_vnext()` 现在调用全部 5 个子映射函数：
  - `_previous_compacted_session_summary_vnext()` → `session_summary`
  - `_previous_compacted_fact_material_vnext()` → `evidence_backed_facts`
  - `_previous_compacted_answer_anchors_vnext()` → `answer_anchors`
  - `_previous_compacted_forward_intents_vnext()` → `forward_intents`
  - `_previous_compacted_references_vnext()` → `reference_continuity_items`

  `CompactReadableViewVNext` 构造时五类字段全部填充。
- **测试**: `test_conversation_compact_input_vnext_previous_view_maps_stable_blocks()` 断言 `previous_view.session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items` 均非空且值正确。
- **裁决**: 通过。

### F-3 `USER_VISIBLE_RUN_STATE` trace material 映射

- **状态**: FIXED
- **证据**: `dayu/host/compact_material.py:1856-1881` — `_trace_material_vnext()` 现在同时处理 `CompactMaterialBlockKind.USER_INPUT` 与 `CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE`，映射为 `TraceReadableKindVNext.USER_INPUT` 与 `TraceReadableKindVNext.USER_VISIBLE_RUN_STATE`。`ASSISTANT_FINAL_ANSWER` 继续由 `_answer_material_vnext()` 路由到 `ANSWER_MATERIAL`，未引入 duplicate section owner。
- **测试**: `test_conversation_compact_input_vnext_maps_user_visible_state_to_trace()` 断言 `USER_VISIBLE_RUN_STATE` block 进入 `trace_material` 且 `trace_kind` 为 `"user_visible_run_state"`。
- **裁决**: 通过。

### F-4 `dayu/config/README.md` memory policy 字段列表

- **状态**: FIXED
- **证据**: `dayu/config/README.md:92-111` — 新增 `memory_projection_policy 当前字段为：` 表格，列出全部 20 个字段（`context_window_size`、`selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`selected_recent_window_turn_floor`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`、`evidence_fact_item_cap`、`evidence_fact_char_cap`、`evidence_fact_floor`、`session_summary_char_cap`、`answer_anchor_item_cap`、`answer_anchor_char_cap`、`forward_intent_item_cap`、`forward_intent_char_cap`、`reference_continuity_item_cap`、`reference_continuity_char_cap`、`reference_continuity_item_floor`、`max_lag_events_for_inline_delta`、`max_delta_repair_events`、`policy_ref`）。
- **裁决**: 通过。

### F-5 `_required_text()` 死代码

- **状态**: FIXED
- **证据**: `dayu/host/compact_material.py` 中 `_required_text` 函数已删除（Grep 返回 0 结果）。原调用点改为在 evidence block / provenance 构造处显式校验。`_require_non_empty_text` 仍保留（L2155），签名合理。
- **裁决**: 通过。

### F-6 inline delta repair view 缺失时 repair reason

- **状态**: FIXED
- **证据**:
  1. `dayu/host/memory.py:195` — `MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING = "inline_delta_repair_view_missing"` 已新增。
  2. `dayu/host/compact_material.py:832` — 小滞后但 `inline_delta_repair_view is None` 时，使用 `MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING`，不再使用 `SNAPSHOT_LAG_OVER_THRESHOLD`。
  3. 真正大滞后（lag > threshold）仍使用 `SNAPSHOT_LAG_OVER_THRESHOLD`（L818-823），rebuild retry 语义未破坏。
- **测试**:
  - `test_compact_material.py::test_snapshot_cursor_missing_inline_delta_view_has_accurate_reason` — 断言小滞后 + view 缺失时 reason 为 `INLINE_DELTA_REPAIR_VIEW_MISSING`。
  - `test_compact_material.py::test_snapshot_cursor_lag_requires_catchup_or_inline_delta` — 断言大滞后时 reason 仍为 `snapshot_lag_over_threshold`。
  - `test_dispatch_scheduler.py::test_inline_repair_view_missing_does_not_rebuild_retry` — 断言 `INLINE_DELTA_REPAIR_VIEW_MISSING` 不触发 rebuild retry（`factory.created == 0`，`RUN_FAILED` 事件写入，Run 不进入 RUNNING）。
- **裁决**: 通过。

### F-7 `TraceMemoryView` 设计真源字段同步

- **状态**: FIXED
- **证据**: `docs/host/design.md:2756-2758` — `TraceMemoryView` schema 已更新为：
  ```
  TraceMemoryView
    selected_recent_window: list[SelectedRecentWindowItem]
    reference_continuity_items: list[ReferenceContinuityItem]
  ```
  Section 24.5（L2790）文本同步为："TraceMemoryView 当前字段为 selected recent window 与 reference continuity items"。未新增不存在的 `reference_continuity_memory` schema。
- **裁决**: 通过。

## Deferred / Rejected Findings 未处理确认

| ID | 描述 | 期望状态 | 实际状态 |
|---|---|---|---|
| D-1 | `memory.py` / `context_fallback.py` 缺少 `__all__` | deferred | 未处理 ✅ |
| D-2 | `compaction_operation.py` string → enum | deferred | 未处理 ✅ |
| D-3 | `_empty_string_tuple()` 简化 | rejected | 未处理 ✅ |
| D-4 | slice1 诊断常量命名 | deferred | 未处理 ✅ |
| D-5 | 大 evidence chunk / repair 集成测试 / 并发矩阵 | deferred | 未处理 ✅ |

## Design Source Drift 检查

| 检查项 | 结果 |
|---|---|
| `docs/host/design.md` 是否引入不存在的 schema | 未发现 ✅ |
| `dayu/config/README.md` 是否引入不存在的配置字段 | 未发现 ✅ |
| `memory.py` 是否引入不存在的 repair reason | 未发现 ✅ |
| `compact_material.py` 是否引入不存在的 block kind | 未发现 ✅ |

## AGENTS.md 违规检查

| 检查项 | 结果 |
|---|---|
| 反向依赖 | 未发现 ✅ |
| `dayu.runtime` import 上层 | 未发现 ✅ |
| `Any` / `object` 类型 | 未发现 ✅ |
| 兼容性 re-export / wrapper | 未发现 ✅ |
| 魔法数字 / 魔法字符串 | 未发现 ✅ |
| God object / God function | 未发现 ✅ |
| `hasattr` / `getattr` 滥用 | 未发现 ✅ |

## 验证命令与结果

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
# => 135 passed in 1.54s

source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q
# => 67 passed in 0.34s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# => 0 errors, 0 warnings, 0 informations

git diff --check
# => clean
```

## Residual Risks

1. **`previous_compacted_view` 的 answer anchor / forward intent / reference continuity vNext 映射基于文本格式解析**: 这些映射使用 `_parse_previous_forward_intent_text()` 与 `_parse_previous_reference_continuity_text()` 解析本模块生成的分隔文本。若后续 stable block 改为结构化多 block，需同步调整映射与测试。风险可控——解析函数有完整 ValueError 覆盖。

2. **`_InlineRepairViewMissingRunInputBuilder` 测试 fixture 的 `_catch_up_memory_projection_before_worker` 被 monkeypatch 为 noop**: 该测试验证 dispatch 层对 `INLINE_DELTA_REPAIR_VIEW_MISSING` 的处理路径，但跳过了 catch-up。这是有意设计——测试目的是验证 dispatch 层不触发 rebuild retry，而非验证 catch-up 本身。

3. **Deferred findings 积压**: D-1（`__all__`）、D-2（string → enum）、D-4（诊断命名）、D-5（覆盖增强）均未处理。这些不影响当前 PR correctness，但应在后续 Host public surface hardening 中清理。
