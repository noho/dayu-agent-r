# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`
- Included scope:
  - `dayu/host/memory_repair.py`
  - `dayu/host/open_host.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/README.md`
  - `tests/host/test_memory_repair.py`
  - `tests/host/test_open_host_runtime.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_logging.py`
  - `docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md`
- Excluded scope: Slice 1-3 / Slice 5 改动；Engine / Service / UI / Fins；durable schema
- Parallel review coverage: 无
- Design truth: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md` Slice 4

## Findings

未发现实质性问题。

以下逐项验证 design truth Slice 4 的每个 success signal 和 exact change：

### 1. Memory repair 去预算化 ✓

- `MemoryProjectionCatchupBudget`、`MemoryProjectionRepairPurpose`、`MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED` 已从 `memory_repair.py` 删除。
- `ConversationMemoryProjectionRepairResult` 已删除 `budget_exhausted`、`max_batches`、`max_scanned_events` 字段。
- `catch_up_conversation_memory_projection(...)` 和 `rebuild_conversation_memory_projection(...)` 已删除 `budget` 参数。
- `_run_memory_projection_bounded` 已重命名为 `_run_memory_projection_until_stop`，循环直到 `target_reached`、`idle` 或 `failure`。
- `batch_size` 只作为 page size 传给 `runner.run_once(limit=batch_size)`。
- 删除了 `_bounded_batch_limit`、`_budget_scanned_events_exhausted`、`_budget_purpose_value`、`_budget_max_batches`、`_budget_max_scanned_events` 等辅助函数。
- 日志删除了 `budget_purpose`、`max_batches`、`max_scanned_events`、`budget_exhausted` warning 分支。

### 2. open_host after-commit 热路径不再执行 memory catch-up ✓

- `_MemoryProjectionCatchupPort` 类已从 `open_host.py` 删除。
- `_after_commit_memory_projection_budget` helper 已删除。
- `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT` 常量已删除。
- scheduler 和 admission service 的 `projection_catchup_port` 均传 `None`。
- close cleanup 的 `_CompositeProjectionCatchupPort` 不再包含 memory port。

### 3. dispatch compact accepted 热路径不再执行 memory catch-up ✓

- `_opportunistic_memory_projection_catchup_budget` helper 已删除。
- `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT` 常量已删除。
- `run_queue_promotion` 中 compact accepted 后不再调用 `catch_up_conversation_memory_projection`。
- 日志从 `compact_catchup` 改为 `compact_accepted`，准确反映只记录 diagnostic。

### 4. dispatch required repair 仍要求 target_reached ✓

- `_raise_if_memory_projection_target_not_reached` 仍检查 `result.failures == 0 and result.target_reached`。
- `rebuild_conversation_memory_projection` 和 `catch_up_conversation_memory_projection` 在 required path 中不再传 `budget=None`（参数已删除）。
- required path 调用 `_run_memory_projection_until_stop`，追到 target / idle / failure。

### 5. ConversationMemoryProjectionCatchupPort 保留为内部 hook ✓（可接受）

- 该类仍在 `memory_repair.py:75` 定义，`catch_up_projection()` 委托给 `catch_up_conversation_memory_projection`（无 budget）。
- 热路径（`open_host.py`、`dispatch.py`）不再实例化或注入该 port。
- 测试 `test_catchup_port_delegates_to_catch_up_function` 手动实例化并验证委托行为。
- 该类不是 Slice 4 热路径约束的目标；它只是 `memory_repair.py` 的一个适配器类，允许注入方以 `ProjectionCatchupPort` 协议调用 memory catch-up。当前无调用方使用它，但保留它不违反 "after-commit / after-compact 不做无界同步补账" 约束，因为热路径已不注入它。

### 6. 日志无 budget_exhausted 噪音 ✓

- `_log_memory_projection_result` 删除了 `result.budget_exhausted` warning 分支。
- 只保留 `failures > 0` warning 和 VERBOSE 正常 committed 日志。
- `test_logging.py` 删除了 `max_batches=None` 断言。

### 7. README 匹配当前代码 ✓

- `dayu/host/README.md:88` 改为 "memory catch-up page size"。
- `dayu/host/README.md:317` 明确 "opener 的 after-commit 热路径不执行 memory projection 追平"。
- `dayu/host/README.md:623` 补充 "Memory repair / catch-up 的 batch size 只控制单页读取和事务粒度；required path 会追到目标 cursor、idle 或 failure，不把 page size 当作正确性停止预算。"

### 8. 测试覆盖充分 ✓

- `test_memory_repair.py`：
  - `test_catch_up_batch_size_one_multiple_relevant_rows_reaches_idle` — page size=1 多页追到 idle。
  - `test_catch_up_stops_when_target_reached_before_idle` — target reached 停止。
  - `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target` — batch_size=1 追 17 页到 target。
  - `test_rebuild_batch_size_one_reaches_target` — rebuild 多页追到 target。
  - `test_rebuild_without_budget_crosses_old_batch_cap_to_target` — rebuild 追 33 页。
  - `test_catch_up_stops_on_failure_and_counts_failure` — failure 立即停止。
  - `test_catch_up_batch_size_one_reaches_idle_in_real_store` — 真实 durable store page size=1 追到 idle。
  - `test_catchup_port_delegates_to_catch_up_function` — port 委托验证（无 budget）。
- `test_open_host_runtime.py`：
  - `test_open_host_after_commit_does_notinject_memory_catchup_port` — scheduler open 时 `projection_catchup_port=None`。
  - `test_open_host_dispatch_memory_catchup_reaches_required_cursor` — dispatch 前 required catch-up 集成。
- `test_dispatch_scheduler.py`：
  - `test_compact_accepted_hot_path_does_not_call_memory_catchup` — monkeypatch `catch_up_conversation_memory_projection` 为 AssertionError，compact accepted 后不触发。
  - `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input` — required catch-up 集成。

### 9. retry_repair_budget_exhausted 不属于本 slice 范围 ✓

- `retry_repair_budget_exhausted` 是 Context Governance / compaction payload 字段（`context_events.py`、`tool_trace.py`、`dispatch.py`），描述 compaction retry/repair 预算是否耗尽。
- 与 `MemoryProjectionCatchupBudget` / `BUDGET_EXHAUSTED` 无关。implementation report 已标注此点。

## Open Questions

无。

## Residual Risk

- `ConversationMemoryProjectionCatchupPort` 类当前无调用方；若未来被误注入热路径，会执行无界 catch-up。风险低，因为该类不在 `open_host.py` 或 `dispatch.py` 的装配路径中，且 `memory_repair.py` 是 Host 内部模块。
- Slice 5（RunInputBuilder inline repair filter 共源化）未实现，属于后续 slice。
- `retry_repair_budget_exhausted` 命名可能与 "memory projection budget" 混淆，但它是 compaction 领域术语，不在本 slice 重命名范围内。
