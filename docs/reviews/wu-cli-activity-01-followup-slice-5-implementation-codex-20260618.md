# WU-CLI-ACTIVITY-01 follow-up Slice 5 implementation

## 结论

Slice 5 动机成立，但严重性是维护漂移风险，不是当前已发生的 memory 投影不一致。实现只收敛 Conversation Memory consumer 与 RunInputBuilder inline repair 的过滤真源和读取语义，没有修改 Host / Engine public API、public contract 或 durable schema。

## 改动

- `dayu.host.durable.memory.conversation_memory_projection_event_filter()` 成为 Conversation Memory projection filter 的单一真源。
- `ConversationMemoryProjectionConsumer.__init__` 改为调用该 helper，不再内联构造 filter。
- `dayu.host.projection.event_log_read_filter_from_projection_filter()` 暴露 projection filter 到 durable EventLog read filter 的内部转换 helper，`ProjectionRunner` 与 RunInputBuilder inline repair 共用该转换语义。
- `DurableMemorySnapshotProvider._repair_inline_delta(...)` 删除本地 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row` 并改用 `read_events_after_matching(...)`：
  - `event_filter` 来自 `conversation_memory_projection_event_filter()`。
  - `session_id` 限定为 snapshot session。
  - `max_event_sequence` 限定为 required cursor。
  - 只对 matching rows 调用 `project_conversation_memory_event(...)`。
  - 使用 `FilteredEventLogPage.covered_event_sequence` 与 `covered_event_id` 证明 required cursor 覆盖，并用 required row id 构造临时 `MemorySnapshotCursor`。
- 保留 `max_lag_events_for_inline_delta` 与 `max_delta_repair_events` 的 lag safety；没有引入新的 semantic budget。

## 测试

- `tests/host/test_run_input_builder.py`
  - 覆盖大量 preview / diagnostic / unrelated canonical / foreign session rows 下 inline repair 只投影 matching memory facts，同时 cursor 覆盖 required row。
  - 覆盖无 matching rows 但 covered cursor 达到 required 时返回原 snapshot 加 inline repair diagnostic。
  - 覆盖无法证明 covered cursor 达到 required 时仍抛 `MemoryProjectionRepairRequired`。
- `tests/host/test_memory_projection.py`
  - 覆盖 `ConversationMemoryProjectionConsumer.event_filter` 与 `conversation_memory_projection_event_filter()` 一致。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py`
- `source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/durable/memory.py dayu/host/projection.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py`

## README 判断

- 修改命中 `dayu/host/` 与 `tests/`，已检查 `dayu/host/README.md` 与 `tests/README.md` 的更新边界。
- 本次没有新增 Host public API、公共契约、架构边界、测试层级或运行命令；README 不需要更新。

## 风险与未覆盖

- 未运行全量 `python -m pyright dayu/ tests/ utils/`；本 slice 只运行了相关文件 pyright。
- 未运行全量 `tests/host`；本 slice 运行了受影响的 RunInputBuilder 与 Memory projection 测试文件。
