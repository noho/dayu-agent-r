# Code Review — WU-CLI-ACTIVITY-01 Follow-up Aggregate

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main` (review range `906c1ffa..HEAD`, 5 follow-up slices)
- Output file: `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`
- Included scope:
  - `dayu/host/engine_ingest.py` — transient delta event filtering (no durable rows)
  - `dayu/host/durable/event_log.py` — `EventLogReadFilter`, `EventLogReadClassFilter`, `FilteredEventLogPage`, `read_events_after_matching`
  - `dayu/host/projection.py` — `ProjectionRunner` filter-aware read, covered cursor checkpoint advance, `event_log_read_filter_from_projection_filter`
  - `dayu/host/memory_repair.py` — budget removal, `_run_memory_projection_until_stop` (renamed from `_run_memory_projection_bounded`)
  - `dayu/host/open_host.py` — removal of `_MemoryProjectionCatchupPort`, `projection_catchup_port=None`
  - `dayu/host/dispatch.py` — removal of compact-accepted opportunistic catch-up, required catch-up paths preserved
  - `dayu/host/run_input.py` — `DurableMemorySnapshotProvider` filter-aware inline repair
  - `dayu/host/durable/memory.py` — `conversation_memory_projection_event_filter()` single source of truth
  - `docs/host/design.md`, `docs/host/issues-implementation-control.md`, `dayu/host/README.md`
  - All related tests in `tests/host/`
- Excluded scope: `dayu/engine/`, `dayu/service/`, `dayu/ui/`, `dayu/fins/`, `dayu/config/`, `dayu/runtime/`
- Parallel review coverage: 4 subagents — (1) EventLog + ProjectionRunner, (2) engine_ingest delta filter, (3) memory_repair + dispatch + open_host, (4) run_input inline repair + durable/memory; plus 1 cross-cutting integration agent (import cycles, public contract drift, old symbols, design/README consistency, tests, pyright)

## Work Unit Goal Summary

1. Default Host does not durably persist `content_delta`/`reasoning_delta`/`tool_call_delta` to EventLog.
2. `ProjectionRunner` uses filter-aware EventLog read and covered cursor semantics.
3. Memory repair catch-up/rebuild has no semantic budget; hot paths do not run unbounded conversation-memory catch-up.
4. `RunInputBuilder` inline repair shares Conversation Memory filter/read semantics.

## Findings

未发现实质性问题。

以下为两处 test coverage gap 和一处 dead code 观察，均非 correctness defects：

### 1-未修复-低-`read_events_after_matching` 中 `matching_rows >= limit` 分支缺少显式测试

- **入口/函数**: `read_events_after_matching` (`dayu/host/durable/event_log.py:731`)
- **文件(行号)**: `tests/host/test_event_log_store.py` — 现有测试均使用 `limit=10` 且匹配行 < limit
- **输入场景**: 匹配行数 >= limit 时，`covered_row = matching_rows[-1]`（而非 `boundary_row`）
- **实际分支**: `len(matching_rows) >= limit` 分支
- **预期行为**: `covered_event_sequence` 应等于 `matching_rows[-1].event_sequence`，而非 `boundary_row.event_sequence`
- **实际行为**: 代码逻辑正确（event_log.py:731-734），但无测试覆盖该分支
- **直接证据**: `test_read_events_after_matching_filters_mixed_classes_and_covers_latest` 使用 3 匹配行 + limit=10，始终走 `< limit` 分支
- **影响**: 仅 test coverage gap，生产代码正确
- **建议改法和验证点**: 新增测试：构造 >= limit 个匹配行，断言 `covered_event_sequence == matching_rows[-1].event_sequence`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-ProjectionRunner 无匹配 covered cursor 推进路径未测试 `clear_projection_failure`

- **入口/函数**: `ProjectionRunner._process_next_event` (`dayu/host/projection.py:611`)
- **文件(行号)**: `tests/host/test_projection_runner.py`
- **输入场景**: page.rows 为空但 `covered_event_sequence > checkpoint`，且存在先前 projection failure
- **实际分支**: projection.py:596-617 — 无匹配行时推进 checkpoint 并调用 `clear_projection_failure`
- **预期行为**: 先前 failure row 被清除
- **实际行为**: 代码正确调用了 `clear_projection_failure`（projection.py:611），但无测试验证此路径下 failure 被清除
- **直接证据**: `test_runner_advances_covered_cursor_without_apply_when_no_matching_rows` 验证了 checkpoint 推进但未设置先前 failure；`test_success_after_failure_clears_failure_row` 仅测试匹配行成功路径
- **影响**: 仅 test coverage gap，生产代码正确
- **建议改法和验证点**: 新增测试：先注入 projection failure，再运行无匹配 covered cursor 推进，断言 failure row 被清除
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-`read_api.py` 中 delta event 过滤为 dead code

- **入口/函数**: activity view 构造 (`dayu/host/read_api.py:1061`)
- **文件(行号)**: `dayu/host/read_api.py:102-103, 1061`
- **输入场景**: `CONTENT_DELTA` / `REASONING_DELTA` EventLog rows
- **实际分支**: `row.event_type in (_EVENT_TYPE_CONTENT_DELTA, _EVENT_TYPE_REASONING_DELTA)` 返回 `None`
- **预期行为**: 此过滤在旧代码中是有意义的（delta rows 存在于 EventLog 中）
- **实际行为**: delta events 在 `engine_ingest.py:928` 被短路，不再产生 durable rows，此过滤永远无法命中
- **直接证据**: `_is_transient_delta_event` 在 `_ingest_validated` 入口处拦截，`_accepted_no_event_result()` 返回空 events tuple
- **影响**: 无功能影响，dead code；`TOOL_CALL_DELTA` 也缺失于此过滤但同样无影响
- **建议改法和验证点**: 可在后续 cleanup 中移除；不影响正确性
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- `memory_repair.py:317` `_validate_batch_size` docstring 仍写"每批最多扫描的 EventLog row 数"，与全文统一的"projection page size"语义不一致。仅 docstring cosmetic，不影响行为。
- Finding #1 和 #2 的 test coverage gap 不影响生产正确性，但应在后续补充以防止回归。

## Cross-Slice Integration Verification

| 检查项 | 结果 |
|---|---|
| Import cycles | PASS — 8 个模块 import 无错 |
| Public contract drift | PASS — `MemoryProjectionCatchupBudget`, `MemoryProjectionRepairPurpose`, `ConversationMemoryProjectionCatchupPort` 均已从 `__init__.py` 和生产代码完全移除 |
| Old budget symbols | PASS — 无残留引用；`retry_repair_budget_exhausted` 属于 context compaction 语义，非 memory projection budget |
| Event delta durable rows | PASS — `content_delta`/`reasoning_delta`/`tool_call_delta` 在 ingest 入口短路，不产生 EventLog rows |
| ProjectionRunner checkpoint | PASS — filter-aware read + covered cursor 推进逻辑正确 |
| Inline repair coverage | PASS — filter/read 语义与 `ConversationMemoryProjectionConsumer` 共用 `conversation_memory_projection_event_filter()` |
| Hot path 无 unbounded catch-up | PASS — `open_host` 和 `dispatch` compact-accepted 路径均不再执行 memory projection catch-up；`projection_catchup_port=None` 正确传播 |
| Required catch-up 路径 | PASS — dispatch pre-worker `catch_up_conversation_memory_projection` 和 `rebuild_conversation_memory_projection` 保留且无 budget，追到 target/idle/failure |
| Design doc 一致性 | PASS — `docs/host/design.md` 和 `docs/host/issues-implementation-control.md` 准确描述新行为 |
| README 一致性 | PASS — `dayu/host/README.md` 准确描述新架构 |
| Tests | PASS — 235 tests, 0 failures (7 个关键测试文件) |
| Pyright | PASS — 0 errors, 0 warnings (8 个关键源文件) |
