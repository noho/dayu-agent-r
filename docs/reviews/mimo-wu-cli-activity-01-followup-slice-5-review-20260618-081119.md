# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-5-review-20260618-081119.md`
- Included scope:
  - `dayu/host/run_input.py` — inline repair 复用 shared filter/read
  - `dayu/host/durable/memory.py` — `conversation_memory_projection_event_filter()` single truth
  - `dayu/host/projection.py` — `event_log_read_filter_from_projection_filter()` 从 private 改为 public
  - `tests/host/test_run_input_builder.py` — 3 个新 inline repair 测试 + `_append_inline_repair_filter_noise` helper
  - `tests/host/test_memory_projection.py` — 1 个 consumer filter 同源测试
  - `docs/reviews/wu-cli-activity-01-followup-slice-5-implementation-codex-20260618.md` — implementation artifact
- Excluded scope: Slice 1–4 改动（已在之前 slice 完成）、Engine contract、durable schema、Service/UI/Fins
- Parallel review coverage: 无

## Design Truth

accepted plan Slice 5 in `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`

核心设计要求：
1. `conversation_memory_projection_event_filter()` 为 filter 单一真源
2. consumer 和 inline repair 都调用它；不保留 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row`
3. inline repair 使用 `read_events_after_matching` 附加 `session_id` 和 `max_event_sequence`
4. covered cursor 语义正确：无 matching rows 但 covered 达标 → 原 snapshot + diagnostic；无法覆盖 → raise
5. `max_lag_events_for_inline_delta` / `max_delta_repair_events` safety 保留
6. 不引入 import cycle
7. 测试证明行为

## Findings

未发现实质性问题。

### 逐项验证

**1. filter 单一真源** ✅

`dayu/host/durable/memory.py:213` 新增 `conversation_memory_projection_event_filter()`，返回基于 `_EVENT_TYPE_FILTER`（`USER_INPUT_ACCEPTED`, `RUN_SUCCEEDED`, `TOOL_RESULT_ACCEPTED`, `CONTEXT_COMPACTED`）的 `ProjectionEventFilter`。`ConversationMemoryProjectionConsumer.__init__`（`memory.py:257`）直接调用该 helper。`run_input.py:1181` inline repair 也调用同一 helper。代码库中 `_MEMORY_EVENT_TYPES` 和 `_is_memory_projection_row` 已完全移除（grep 确认无残留）。

**2. inline repair 使用 filtered read** ✅

`run_input.py:1181-1191` 构造 `event_filter = event_log_read_filter_from_projection_filter(conversation_memory_projection_event_filter())`，调用 `read_events_after_matching` 传入 `session_id=snapshot.session_id` 和 `max_event_sequence=required_event_sequence`。只对 `page.rows` 逐条调用 `project_conversation_memory_event`，不再有 `_is_memory_projection_row` 过滤。

**3. covered cursor 语义** ✅

- `run_input.py:1192`：`page.covered_event_sequence != required_event_sequence` → raise `MemoryProjectionRepairRequired`
- `run_input.py:1199-1206`：`covered_event_id is None` → raise `MemoryProjectionRepairRequired`
- 无 matching rows 但 covered 达标时：`page.rows` 为空 → `repaired = snapshot`（不变），diagnostic 正常附加，cursor 设为 `required_event_sequence` + `covered_event_id`
- 测试 `test_inline_delta_no_matching_rows_still_covers_required_cursor` 精确覆盖此路径

**4. max_lag / max_delta safety** ✅

`lag_events` 仍作为 `read_events_after_matching` 的 `limit` 参数传入，控制单次 filtered read page size。`max_event_sequence=required_event_sequence` 确保不越界。`max_lag_events_for_inline_delta` / `max_delta_repair_events` policy 字段未被移除或修改。

**5. import cycle** ✅

- `run_input.py` → `durable/memory.py`（`conversation_memory_projection_event_filter`）：host 内部 durable 子模块
- `run_input.py` → `projection.py`（`event_log_read_filter_from_projection_filter`）：host 内部
- `durable/memory.py` → `projection.py`（`ProjectionEventFilter` 等类型）：已有依赖，非新增
- 无反向依赖：`projection.py` 不 import `run_input.py` 或 `durable/memory.py`；`durable/memory.py` 不 import `run_input.py`

**6. `event_log_read_filter_from_projection_filter` visibility 变更** ✅

从 `_event_log_read_filter_from_projection_filter`（private）改为 `event_log_read_filter_from_projection_filter`（public）。合理：`run_input.py` 需要该转换逻辑，且函数本身是 durable-neutral 的 filter 转换，不泄漏 projection 内部状态。

**7. 测试覆盖** ✅

| 测试 | 覆盖路径 |
|------|----------|
| `test_inline_delta_uses_memory_filter_and_covers_required_cursor` | 大量 noise rows（preview/diagnostic/unrelated canonical/foreign session）下只投影 matching memory facts，cursor 覆盖 required |
| `test_inline_delta_no_matching_rows_still_covers_required_cursor` | 无 matching rows，covered cursor 达标 → 原 snapshot + diagnostic |
| `test_inline_delta_unable_to_cover_required_cursor_raises_repair_required` | covered cursor 未达标 → raise `MemoryProjectionRepairRequired` |
| `test_conversation_memory_consumer_uses_shared_projection_event_filter` | consumer.event_filter 与 `conversation_memory_projection_event_filter()` 一致 |

**8. 现有测试回归** ✅

- `tests/host/test_run_input_builder.py`：48 passed
- `tests/host/test_memory_projection.py`：28 passed
- 其中 6 个 inline_delta 相关测试全部通过

**9. pyright** ✅

`dayu/host/run_input.py`, `dayu/host/durable/memory.py`, `dayu/host/projection.py`：0 errors, 0 warnings, 0 informations。

## Open Questions

无。

## Residual Risk

- 实现 artifact 未运行全量 `python -m pyright dayu/ tests/ utils/` 和全量 `tests/host`。建议 closeout 前补跑确认无扩散。
- `event_log_read_filter_from_projection_filter` 从 private 改为 public 后，若未来有其他模块需要 projection-to-durable filter 转换，可能被过度复用；当前只有两个调用点（`projection.py` 内部 + `run_input.py`），风险低。
