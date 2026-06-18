# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main` (Slice 5 workspace changes — uncommitted diff only)
- Output file: `docs/reviews/ds-wu-cli-activity-01-followup-slice-5-20260618-080958.md`
- Included scope:
  - `dayu/host/run_input.py` — inline repair filter 共源化
  - `dayu/host/durable/memory.py` — `conversation_memory_projection_event_filter()` 单一真源
  - `dayu/host/projection.py` — `event_log_read_filter_from_projection_filter` 公开
  - `tests/host/test_run_input_builder.py` — inline repair filter-aware read 测试
  - `tests/host/test_memory_projection.py` — consumer 与 filter 真源一致性测试
- Excluded scope:
  - Slice 1–4 已提交代码（不在本次 diff 中）
  - 设计文档（已按 plan gate 评审）
  - 其他 Host 模块（本次变更不触及）
- Design truth: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md` Slice 5
- Parallel review coverage: 无

## Findings

未发现实质性问题。

所有 plan 定义的 success signal 均满足。以下逐一核查：

### 1. 单一 filter 真源

- `conversation_memory_projection_event_filter()` 定义在 `dayu/host/durable/memory.py:213`，返回 `ProjectionEventFilter`（只消费 `CANONICAL_FACT` 下的 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`、`CONTEXT_COMPACTED`）。
- `ConversationMemoryProjectionConsumer.__init__`（`dayu/host/durable/memory.py:257`）调用该 helper 设置 `self._event_filter`。
- `DurableMemorySnapshotProvider._repair_inline_delta`（`dayu/host/run_input.py:1181`）同样调用 `conversation_memory_projection_event_filter()`，不经由 consumer 实例。
- `tests/host/test_memory_projection.py:783` 验证 `consumer.event_filter == conversation_memory_projection_event_filter()`。

### 2. `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row` 完全移除

- grep 全量 `dayu/` 与 `tests/` 目录，零匹配。
- `run_input.py` 中的 `_EVENT_TYPE_USER_INPUT_ACCEPTED`、`_EVENT_TYPE_RUN_SUCCEEDED`、`_EVENT_TYPE_TOOL_RESULT_ACCEPTED` 常量仍保留，但仅用于其他目的（`_payload_with_assistant_final_answer`、tool trace 投影等），不再参与 memory inline repair 过滤。

### 3. Inline repair 使用 `read_events_after_matching` with `session_id` 和 `max_event_sequence`

- `_repair_inline_delta`（`dayu/host/run_input.py:1184–1191`）调用：
  ```python
  page = self._event_log_store.read_events_after_matching(
      transaction,
      snapshot.cursor.checkpoint_event_sequence,
      event_filter=event_filter,
      limit=lag_events,
      max_event_sequence=required_event_sequence,
      session_id=snapshot.session_id,
  )
  ```
- `session_id` 限定了 matching rows 与 covered cursor 的 session 范围（`dayu/host/durable/event_log.py:1026, 1064–1074`）。
- `max_event_sequence` 限定了边界行不超过 required cursor（`dayu/host/durable/event_log.py:1021–1025`）。

### 4. Covered cursor/id 语义正确

- `covered_event_sequence != required_event_sequence` 时抛 `MemoryProjectionRepairRequired`（`dayu/host/run_input.py:1192–1198`），`!=` 比旧实现的 `<` 更严格——也捕获 `covered > required`（但 `max_event_sequence` 使该 case 不可能出现）。
- `covered_event_id is None` 时同样抛 repair-required（`dayu/host/run_input.py:1199–1206`）。由于 `covered_event_sequence == required_event_sequence > cursor`，此处的 `covered_event_id` 必定非空（按 `read_events_after_matching` 的 covered cursor 不变量），该 check 是防御性正确性加固。
- 临时 cursor 使用 `required_event_sequence` 与 `required_event_id` 构造（`dayu/host/run_input.py:1222–1225`），不再使用最后一条 matching row 的 sequence/id。

### 5. 无 matching rows 但 covered required → 返回原 snapshot + 诊断

- `page.rows` 为空时，`for row in page.rows` 不执行，`repaired = snapshot`（原始 snapshot）。
- `build_inline_delta_repair_diagnostic` 仍追加诊断（`dayu/host/run_input.py:1216–1219`）。
- `tests/host/test_run_input_builder.py:1282` 覆盖此路径。

### 6. Unable to cover required → 仍抛 repair-required

- 两个 guard 覆盖了无法证明覆盖的 case（covered != required / covered_id is None）。
- `tests/host/test_run_input_builder.py:1343` 用 `pytest.raises(MemoryProjectionRepairRequired)` 覆盖。

### 7. `max_lag` / `max_delta` safety 保留

- `_load_memory_snapshot_tx`（`dayu/host/run_input.py:1064–1073`）在调用 `_repair_inline_delta` 前仍检查 `lag_events > max_lag_events_for_inline_delta` 与 `lag_events > max_delta_repair_events`。

### 8. 无 import cycle

- `dayu/host/projection.py` → 不 import `dayu/host/durable/memory.py`
- `dayu/host/durable/memory.py` → import `dayu/host/projection`（单向）
- `dayu/host/run_input.py` → import 两者（单向）

### 9. 测试覆盖

- `test_conversation_memory_consumer_uses_shared_projection_event_filter`：验证 consumer 与模块级 helper 返回的 filter 等价。
- `test_inline_delta_uses_memory_filter_and_covers_required_cursor`：在大量 noise rows（preview / diagnostic / unrelated canonical / foreign session）中，验证 inline repair 只投影 matching memory facts，cursor 覆盖 required row。使用了新辅助函数 `_append_inline_repair_filter_noise` 构造 cross-class、cross-type、cross-session 的 EventLog rows。
- `test_inline_delta_no_matching_rows_still_covers_required_cursor`：无 matching memory rows 但 covered cursor 达标时返回原 snapshot 加诊断。
- `test_inline_delta_unable_to_cover_required_cursor_raises_repair_required`：无法证明 covered cursor 达标时抛 repair-required。

### 10. 验证结果

- `pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py`：76 passed。
- `pyright dayu/host/run_input.py dayu/host/durable/memory.py dayu/host/projection.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py`：0 errors, 0 warnings。

## Open Questions

无。

## Residual Risk

- 本次仅运行了 Slice 5 直接受影响的测试文件；未运行全量 `tests/host/`。低风险，因为 Slice 5 仅改 inline repair read path 和 filter 构造方式，不改变公共 API、durable schema 或状态机行为。
- `event_log_read_filter_from_projection_filter` 从 `_event_log_read_filter_from_projection_filter` 改为公开（去下划线），`ProjectionRunner._process_next_event` 和 `run_input.py` inline repair 均使用。该函数未通过 `dayu/host/__init__.py` 暴露，仅内部使用，符合 plan 的 "不把 ProjectionEventFilter 暴露为 public Host API" 约束。
- `conversation_memory_projection_event_filter()` 每次调用返回新的 filter 实例（非单例），`ProjectionEventFilter` / `ProjectionEventClassFilter` 为 frozen dataclass，`__eq__` 按字段比较，consumer 的 `event_filter` 属性与函数返回值等价。每次调用重建 filter 的分配开销可忽略，inline repair 只在小滞后且非热路径上调用。
