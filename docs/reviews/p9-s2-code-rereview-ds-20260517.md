# Code Re-Review

## Scope

- Mode: current changes (same-gate re-review of fixes)
- Branch: feat/host-p9-conversation-memory
- Original review: docs/reviews/p9-s2-code-review-ds-20260517.md
- Output file: docs/reviews/p9-s2-code-rereview-ds-20260517.md
- Reviewed fixes (5):
  1. else branch in event dispatch for unknown event_type
  2. always_items unified into budget competition in _limit_continuity_items
  3. tool_name fallback changed from "host_projection" to "unknown_tool"
  4. recent_raw_turns_floor=0 special handling (no items[-0:])
  5. malformed OpaqueMemoryRef source_refs wrapped in try/except ValueError (not in original findings)
- Excluded scope: all other unchanged code

## Verification

```
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py
→ 35 passed in 0.25s

source .venv/bin/activate && pytest tests/host/test_weak_typing_guard.py
→ 1 passed in 0.31s

source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ 无输出（无空白问题）
```

新增 5 个测试全部通过；类型检查干净；无空白或格式问题。

## Fix-by-Fix Assessment

### Fix 1: else branch in event dispatch — PASS

- **文件(行号)**: `dayu/host/memory.py:409-435`
- **变更**: 原 if/elif 链末尾新增 else 分支，调用 `_unsupported_event_type_diagnostic(event)` 追加 diagnostic，不修改 view。
- **新辅助函数**: `_unsupported_event_type_diagnostic()`（行 1572-1602），使用 `SNAPSHOT_DAMAGED` reason 作为临时 proxy，docstring 明确标注 schema 限制。
- **对应测试**: `test_unknown_event_type_records_diagnostic_and_advances_cursor` — 验证未知 event_type 产生 diagnostic 且 snapshot 推进。
- **评估**: 防御性分支正确实现。cursor 仍由 runner 推进（consumer 返回 APPLIED 后 runner 更新 checkpoint），cursor 推进合理——事件被标记为已消费并带 diagnostic 记录。docstring 中 `SNAPSHOT_DAMAGED` 作为 proxy reason 的标注清晰。
- **判決**: PASS

### Fix 2: always_items unified budget competition — PASS

- **文件(行号)**: `dayu/host/memory.py:1326-1340`（重构后）
- **变更**: `always_items`（recent raw + assistant conclusions）不再无条件全量纳入。改为：
  - `budget_used = _EMPTY_SIZE_UNITS`（原为 `_size_units_sum(always_items)`）
  - `primary_pool_items = always_items + episode_summaries` → `_event_ordered_items(older_raw + primary_pool_items)` → 统一预算竞争
  - 预算优先级：recent raw floor 保留 → older_raw 先被裁剪 → summaries 先于 older_raw 被丢弃
- **新辅助函数**: `_event_ordered_items()`（行 1361-1370），按 `event_sequence` 稳定排序。
- **对应测试**: `test_history_pool_limits_assistant_conclusions_before_episode_summaries` 和 `_assistant_budget_policy()` — 验证 assistant conclusions 在引入 episode summaries 后最先被预算裁剪。
- **评估**: 统一预算竞争模型正确。排序稳定（按 event_sequence），去重逻辑保持不变（`_replace_item_by_id`）。`_size_units_sum` 函数可能不再被调用（需确认）。
- **判決**: PASS

### Fix 3: tool_name fallback → "unknown_tool" — PASS

- **文件(行号)**: `dayu/host/memory.py:72, 1031-1032`
- **变更**: 新常量 `_UNKNOWN_TOOL_PRODUCER_NAME = "unknown_tool"`；原 `tool_name = _PRODUCER_NAME_HOST_PROJECTION` 改为 `tool_name = _UNKNOWN_TOOL_PRODUCER_NAME`。
- **对应测试**: `test_missing_tool_name_uses_unknown_tool_producer` — 验证缺失 tool_name 时 producer_name 为 `"unknown_tool"`，producer_kind 仍为 `TOOL`。
- **评估**: 语义正确——TOOL producer 与 HOST_PROJECTION producer 名称不再混淆；下游可按 producer_name 区分。`_PRODUCER_NAME_HOST_PROJECTION` 仍在 episode summary 路径中用于 `producer_kind=HOST_PROJECTION`，职责清晰。
- **判決**: PASS

### Fix 4: recent_raw_turns_floor=0 explicit check — PASS

- **文件(行号)**: `dayu/host/memory.py:1323-1324`
- **变更**: `if policy.recent_raw_turns_floor == _MIN_SEQUENCE: recent_raw = ()` — 显式处理 floor=0 情况，避免 Python `items[-0:]` 语义导致全部 item 进入 recent_raw。
- **对应测试**: `test_recent_raw_turns_floor_zero_keeps_no_raw_floor` 和 `_zero_recent_floor_policy()` — 验证 floor=0 时无 raw turn 进入无条件保留层。
- **评估**: 修复正确。policy 校验仍允许 floor>=0（`_require_non_negative`），floor=0 的语义明确：不保留保底 raw turn，所有 raw_turn 进入 older_raw 参与预算竞争。
- **判決**: PASS

### Fix 5: malformed source_refs try/except ValueError — PASS

- **文件(行号)**: `dayu/host/memory.py:1562-1568`
- **变更**: `OpaqueMemoryRef` 构造包裹在 `try/except ValueError: continue` 中，格式不合法的 source_ref（如缺少 `/` 分隔符）被跳过而非导致整个 fact 丢弃或 crash。
- **对应测试**: `test_invalid_source_refs_are_skipped_without_dropping_fact` — 验证 malformed `data_source_id` 被跳过但不影响同一 fact 内其他合法 source_refs 及 fact 本身。
- **评估**: 防御性处理正确。跳过非法 source_ref 而非丢弃整个 fact 是合理的设计选择——source_ref 是可选的 provenance 增强，不应因个别格式错误导致 fact 丢失。
- **判決**: PASS

## New Issues

无新增阻塞性问题。两个观察：

1. **`_unsupported_event_type_diagnostic` 使用 `SNAPSHOT_DAMAGED` 作为 proxy reason**（`dayu/host/memory.py:1594-1600`）：docstring 已明确标注此为临时性代理，因当前 `MemoryDiagnosticReason` schema 尚无 `UNSUPPORTED_EVENT_TYPE` 成员。这属于已知限制，非缺陷。

2. **`_size_units_sum` 可能成为死代码**：修订后的 `_limit_continuity_items` 使用 `_EMPTY_SIZE_UNITS` 初始化 budget_used（行 1334），不再从 `always_items` 计算初始占用。若 `_size_units_sum` 在模块内已无其他调用点，应考虑移除。搜索确认：
   - `_size_units_sum` 在 `_limit_continuity_items` 的重构分支中仍用于迭代预算检查（`budget_used += _size_units_sum([item])`），因此并非死代码。
   - 此观察从原 review residual risk 中移除。

## Open Questions

无。

## Residual Risk

- `_unsupported_event_type_diagnostic` 的 `SNAPSHOT_DAMAGED` proxy reason 未在测试中断言具体 reason 值，仅断言 `diagnostics` 非空。不影响功能，但建议在新增专用 reason member 时补充断言。
- `_size_units_sum` 函数签名接受 `Sequence` 但在 budget 循环中每次以单元素 `[item]` 列表调用，性能影响可忽略（item count 受 budget 限制）。

## Verdict

**5/5 PASS，阻塞计数: 0。**

所有 5 项 fix 正确实施，均被对应测试覆盖，无回归。无新增阻塞性问题。review gate 可进入 Slice 3。
