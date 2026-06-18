# WU-CLI-ACTIVITY-01 Slice A Re-Review (AgentMiMo)

## Scope

- Work unit: `WU-CLI-ACTIVITY-01`
- Gate: Slice A code re-review after fix
- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Fix artifact: `docs/reviews/wu-cli-activity-01-slice-a-fix-codex.md`
- Adjudication artifact: `docs/reviews/code-review-wu-cli-activity-01-slice-a-adjudication-20260617-132855.md`
- Included scope: 仅验证 adjudication 中 accepted 的三个 DS findings 修复状态
- Excluded scope: Slice B-F，Engine / Service / CLI 变更

## Findings

### F-1-已修复-[中]-activity projection allowlist test coverage gap

- **入口/函数**: `_activity_from_row` 及其下游投影函数
- **文件(行号)**: `tests/host/test_host_activity_event_projection.py`
- **输入场景**: 各类 allowlist event type 的 activity 投影
- **实际分支**: adjudication 要求覆盖的全部分支均已新增测试
- **预期行为**: 测试覆盖 completed/cancelled outcome、awaiting/waiting、context compaction 四类、非终态 lifecycle、display fallback chain、descriptor degradation、bounded summary 边界
- **实际行为**: 以下测试已存在并验证通过：
  - `test_tool_result_completed_and_cancelled_outcomes` (L353): completed → COMPLETED/INFO，cancelled → CANCELLED/WARNING
  - `test_tool_awaiting_and_run_waiting_activity_projection` (L399): TOOL_AWAITING 带 tool_name 展示，RUN_WAITING 无 tool_name fallback
  - `test_context_compaction_activity_projection` (L446): REQUESTED/COMPACTED/FAILED/ATTEMPT_REJECTED 四类完整覆盖
  - `test_non_terminal_run_lifecycle_activity_projection` (L505): RUN_ACCEPTED → STARTED，RUN_STARTED → IN_PROGRESS
  - `test_tool_display_fallback_chain_for_missing_snapshot_parts` (L633): missing run、corrupt tool_set mapping、corrupt display_names mapping、empty display name 四种 fallback
  - `test_tool_display_fallback_when_input_event_missing` (L687): input event 缺失时 fallback
  - `test_activity_descriptor_read_degrades_to_no_activity` (L607): payload descriptor 缺失时 activity=None
  - `test_bounded_summary_boundaries` (L585): 空白/180 字符/181 字符截断边界
- **直接证据**: 测试文件 L353-711，所有新增测试均为 focused 单场景测试
- **影响**: 覆盖了 adjudication 要求的全部 allowlist 分支，回归风险降低
- **修复风险**: 低
- **严重程度**: 中

### F-2-已修复-[低]-`_tool_display_name` locally instantiates `EventLogStore()`

- **入口/函数**: `_tool_display_name`
- **文件(行号)**: `dayu/host/read_api.py:137,1421`
- **输入场景**: 任何触发 tool display name 查询的 activity 投影
- **实际分支**: `_tool_display_name` 使用 `_EVENT_LOG_STORE.read_event_by_id()`
- **预期行为**: 不在函数内局部构造 `EventLogStore()`，使用模块级私有实例
- **实际行为**: `read_api.py:137` 定义 `_EVENT_LOG_STORE = EventLogStore()` 模块级私有实例；`read_api.py:1421` 使用 `_EVENT_LOG_STORE.read_event_by_id(transaction, run.input_event_id)` 读取
- **直接证据**: `read_api.py:137` — `# EventLogStore 是无状态 durable primitive 方法容器；read projection 复用同一私有实例。`；`read_api.py:1421` — `input_event = _EVENT_LOG_STORE.read_event_by_id(transaction, run.input_event_id)`
- **影响**: 依赖所有权清晰，避免未来构造函数漂移
- **修复风险**: 低
- **严重程度**: 低

### F-3-已修复-[低]-redundant event_class validation in `_activity_from_row`

- **入口/函数**: `_activity_from_row`
- **文件(行号)**: `dayu/host/read_api.py:1050-1088`
- **输入场景**: 任何非终态 event 的 activity 投影
- **实际分支**: `_activity_from_row` 不再调用 `_public_event_class_from_durable`
- **预期行为**: event class 校验仅在 `_host_event_from_row` 中执行一次
- **实际行为**: `_activity_from_row` (L1050-1088) 仅按 `row.event_type` 做 allowlist 分支，不调用 `_public_event_class_from_durable`。event class 校验在 `_host_event_from_row` 的 fallback 路径 (L882) 和终态 handler (L948, L974, L1004, L1034) 中各执行一次——这些是互斥路径，不存在冗余
- **直接证据**: `read_api.py:1050-1088` 无 `_public_event_class_from_durable` 调用；`read_api.py:860-891` 中 `_host_event_from_row` 是唯一入口，终态和非终态走不同互斥路径
- **影响**: 单一校验点清晰，消除冗余调用
- **修复风险**: 低
- **严重程度**: 低

## Conclusion

**pass**

三个 accepted findings 均已修复：
- F-1 测试覆盖完整，覆盖了 adjudication 要求的全部 allowlist 分支与边界条件
- F-2 `_EVENT_LOG_STORE` 模块级私有实例替代局部构造，依赖所有权清晰
- F-3 冗余 event class 校验已移除，单一校验点明确

fix artifact 报告的验证结果（82 tests passed, 0 pyright errors, clean diff）与当前代码一致。

## Open Questions

无

## Residual Risk

- `_EVENT_LOG_STORE` 假设 `EventLogStore` 保持无状态 durable primitive 方法容器。若未来 `EventLogStore` 获得构造函数状态，read_api 应切换为 operation-level 注入。（已在 fix artifact 中记录）
- Slice B-F 的 Service / CLI activity 消费、去重、渲染行为不在本次 re-review 范围内。
