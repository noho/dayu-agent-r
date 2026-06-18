# Code Review — WU-CLI-ACTIVITY-01 Follow-up Aggregate

## Scope

- Mode: current changes
- Branch: wu-cli-activity-01
- Base: 906c1ffa
- Output file: docs/reviews/ds-aggregate-wu-cli-activity-01-followup-20260618-081532.md
- Included scope: follow-up commits 3cb5fcb4..49c813a5 (slices 1–5), covering `dayu/host/durable/event_log.py`, `dayu/host/projection.py`, `dayu/host/memory_repair.py`, `dayu/host/engine_ingest.py`, `dayu/host/dispatch.py`, `dayu/host/open_host.py`, `dayu/host/durable/memory.py`, `dayu/host/run_input.py`, `dayu/host/api.py`, `docs/host/design.md`, `docs/host/issues-implementation-control.md`, `dayu/host/README.md`, related test files
- Excluded scope: original activity stream work before `906c1ffa` (referenced only for context)
- Parallel review coverage: 无（主 reviewer 单线走读全部关键文件与交叉链路）

## Work Unit Goal Verification

### Goal 1: Default Host does not durably persist content_delta / reasoning_delta / tool_call_delta

- **入口/函数**: `EngineEventIngestor._ingest_validated` → `_is_transient_delta_event`
- **文件(行号)**: `dayu/host/engine_ingest.py:928`, `4700-4717`, `213-219`, `6088-6101`
- **实际分支**: `_ingest_validated` 中第一道分支即检查 `_is_transient_delta_event(event)`，对 `CONTENT_DELTA` / `REASONING_DELTA` / `TOOL_CALL_DELTA` 返回 `True`，随后调用 `_accepted_no_event_result()` 返回 `events=()` 的 ingest 结果。
- **直接证据**: `_DELTA_ENGINE_EVENT_TYPES` frozenset（行 213-219）精确匹配三种 delta event type；`_is_transient_delta_event`（行 4700-4717）同时校验 event type 与 data instance 类型；`_accepted_no_event_result`（行 6088-6101）返回零 EventLog row 结果。设计文档 `docs/host/design.md:339` 明确声明“Host 默认不把 content_delta、reasoning_delta、tool_call_delta 这三类 per-delta EngineEvent 写入主 EventLog”。
- **状态**: ✅ 通过。delta event 不落入持久化 EventLog。

### Goal 2: ProjectionRunner uses filter-aware EventLog read and covered cursor semantics

- **入口/函数**: `ProjectionRunner._process_next_event` → `read_events_after_matching`
- **文件(行号)**: `dayu/host/projection.py:558-651`, `dayu/host/durable/event_log.py:643-740`
- **实际分支**: `_process_next_event` 通过 `event_log_read_filter_from_projection_filter(consumer.event_filter)` 将 projection filter 转为 durable `EventLogReadFilter`，调用 `read_events_after_matching` 获取 `FilteredEventLogPage`。当 `page.rows` 为空但 `covered_event_sequence > checkpoint` 时，以 `boundary_row` 的 event_sequence/event_id 推进 checkpoint（行 597-618）；当有 matching row 时只消费第一条（行 626），推进 checkpoint 到该 row（行 637-643）。
- **直接证据**: `FilteredEventLogPage.__post_init__`（行 227-259）校验 covered cursor 不变量——covered cursor 不允许回退，有推进（row 存在或 covered cursor 前移）时必须带 covered_event_id。`read_events_after_matching` 中 boundary 选择逻辑（行 731-734）：匹配行达到 limit 时 covered row = 最后一条匹配行，否则 covered row = boundary_row（扫描区间最后一条真实 row）。
- **状态**: ✅ 通过。covered cursor 语义正确，有匹配行时逐条消费，无匹配行时批量跳过不相关 row。

### Goal 3: Memory repair catch-up / rebuild has no semantic budget

- **入口/函数**: `catch_up_conversation_memory_projection`, `rebuild_conversation_memory_projection` → `_run_memory_projection_until_stop`
- **文件(行号)**: `dayu/host/memory_repair.py:75-255`
- **实际分支**: 循环终止条件仅三个——`TARGET_REACHED`（`_target_reached(finished_cursor, max_event_sequence)`）、`IDLE`（`batch_result.events_scanned < batch_size`）、`FAILURE`（`batch_result.failures > 0`）。不存在 batch 计数上限或语义预算。
- **直接证据**: 已删除符号验证——`MemoryProjectionCatchupBudget`、`MemoryProjectionRepairPurpose`（除去 `BEST_EFFORT_AFTER_COMMIT`）、`_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT`、`_opportunistic_memory_projection_catchup_budget` 均不在 `dayu/` 和 `tests/` 中。`ConversationMemoryProjectionRepairResult` 不含 `budget_exhausted` 字段；`MemoryProjectionRepairStopReason` 不再包含 `BUDGET_EXHAUSTED`。
- **状态**: ✅ 通过。catch-up / rebuild 循环只按 target / idle / failure 停止，不引用旧语义预算。

### Goal 4: Hot paths do not run required unbounded conversation-memory catch-up

- **入口/函数**: `HostDispatchScheduler._catch_up_memory_projection_before_worker`, `HostDispatchScheduler._build_request_for_dispatch` (rebuild path), `EngineEventIngestor._complete_reactive_recovery`
- **文件(行号)**: `dayu/host/dispatch.py:2969-2989`, `2853-2876`, `dayu/host/engine_ingest.py:2195-2201`
- **实际分支**: 三个调用点均传入显式 `max_event_sequence` 参数：
  - dispatch catch-up: `max_event_sequence=required_event_sequence`，其中 `required_event_sequence = attempt.started_event_sequence - 1`（`dispatch.py:2977-2982`）
  - dispatch rebuild: `max_event_sequence=exc.repair_request.required_event_sequence`（`dispatch.py:2869`）
  - reactive recovery: `max_event_sequence=accepted.compacted_event_sequence`（`engine_ingest.py:2200`）
- **直接证据**: 所有热点调用路径均在 `catch_up_conversation_memory_projection` / `rebuild_conversation_memory_projection` 调用时提供非 None 的 `max_event_sequence`，且每个调用后均经 `_raise_if_memory_projection_target_not_reached` 做 correctness 校验（`dispatch.py:2871-2876`, `2984-2989`）。
- **状态**: ✅ 通过。热点路径均有 `max_event_sequence` 上界，不存在无界 conversation-memory catch-up。

### Goal 5: No event delta durable rows

- **入口/函数**: `EngineEventIngestor._ingest_validated`
- **文件(行号)**: `dayu/host/engine_ingest.py:928-929`
- **实际分支**: delta event 走 `_accepted_no_event_result()`，返回 `EngineIngestResult(events=())`。
- **直接证据**: `_accepted_no_event_result` 返回零 event tuple。delta event 路径不产生任何 EventLog append 调用。
- **状态**: ✅ 通过。

### Goal 6: ProjectionRunner checkpoint correctness

- **入口/函数**: `ProjectionRunner._process_next_event`
- **文件(行号)**: `dayu/host/projection.py:558-651`
- **直接证据**:
  - 每步在独立 write transaction 内执行（`run_once` 行 463-471），checkpoint 在 transaction 内原子读取（`ensure_projection_checkpoint` 行 583-585）
  - 匹配行：checkpoint → 该行 event_sequence（行 637-643）
  - 无匹配行有覆盖：checkpoint → covered_event_sequence（行 604-610）
  - 无匹配行无覆盖：checkpoint 不变，step 返回 `scanned=False`（行 619-624）
  - 匹配行 consumer 失败：checkpoint 不推进，`ProjectionRunner` catch `_ProjectionApplyFailed` 后在外层写 failure row（行 472-479）
  - DUPLICATE / SKIPPED status：checkpoint 仍推进（consumer 已消费该事件）
  - failure row 写入与 checkpoint 推进状态一致：failure 路径中 run_once 跳出循环，不继续推进后续事件
- **状态**: ✅ 通过。checkpoint 推进、回退、失败边界均与 consumer apply 结果保持一致。

### Goal 7: Inline repair coverage correctness (RunInputBuilder)

- **入口/函数**: `DurableMemorySnapshotProvider._repair_inline_delta`
- **文件(行号)**: `dayu/host/run_input.py:1163-1229`
- **实际分支**: inline repair 使用 `event_log_read_filter_from_projection_filter(conversation_memory_projection_event_filter())` 构造 `EventLogReadFilter`（行 1181-1183），复用 `EventLogStore.read_events_after_matching`（行 1184-1191），并通过 session-scoped covered cursor 校验覆盖完整性（行 1192-1206）。`conversation_memory_projection_event_filter()` 是 `dayu/host/durable/memory.py:213-227` 定义的单一 filter 真源。
- **直接证据**: inline repair 的 filter 来自同一 `conversation_memory_projection_event_filter()` 函数，与 projection consumer 共享 filter 语义，不再维护 RunInputBuilder-local 的事件类型硬编码列表。covered cursor 验证 `page.covered_event_sequence != required_event_sequence` 时转 repair-required（行 1192-1198）。
- **状态**: ✅ 通过。inline repair 与 memory projection consumer 使用同一 EventLog filter 真源，covered cursor 验证 fail-closed。

## Cross-Slice Integration Findings

### 1. 无公共契约漂移

- **检查项**: `OpenHostOptions.memory_projection_catchup_batch_size`
- **文件(行号)**: `dayu/host/api.py:1016-1043`, `dayu/host/open_host.py:905`, `dayu/host/engine_ingest.py:638`, `dayu/host/dispatch.py:2868`, `dayu/service/host_assembly.py:692`
- **直接证据**: Host public API 使用 `memory_projection_catchup_batch_size`（统一命名）；`HostLocalExecutionOptions` 使用同名字段（`api.py:764`）；`open_host.py` 透传 `options.memory_projection_catchup_batch_size` 到 `HostLocalExecutionOptions`；三个消费点（dispatch worker catch-up、dispatch rebuild、engine ingest）均通过 `self._local_execution.memory_projection_catchup_batch_size` 读取。`ConfigLoader`（`dayu/runtime/config_loader.py:488-500`）使用 `memory_projection_catch_up_batch_size`（带下划线分隔 "catch_up"）属 runtime 层自身命名约定，经 `host_assembly.py:692` 显式映射为 Host API 的 `memory_projection_catchup_batch_size`，不存在隐式别名或重复真源。
- **结论**: 无公共契约漂移。

### 2. 无旧预算符号残留

- **检查项**: `MemoryProjectionCatchupBudget`, `MemoryProjectionRepairPurpose`, `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT`, `_opportunistic_memory_projection_catchup_budget`, `ConversationMemoryProjectionCatchupPort`
- **直接证据**: 全局 grep（`dayu/` + `tests/`）零命中。`MemoryProjectionRepairStopReason` 不再包含 `BUDGET_EXHAUSTED`。
- **结论**: 无旧预算符号残留。

### 3. 无 import 循环

- **检查项**: `memory_repair` ↔ `projection` ↔ `durable/event_log` ↔ `durable/memory` ↔ `run_input` ↔ `dispatch`
- **直接证据**: 依赖方向均为单向：`memory_repair → projection → durable/event_log`；`memory_repair → durable/memory → projection`；`dispatch → memory_repair / projection / run_input`；`run_input → projection / durable/memory`。无反向依赖。
- **结论**: 无 import 循环。

### 4. README / 设计文档一致性

- **检查项**: `dayu/host/README.md` 与 `docs/host/design.md` 对 memory catch-up page size / delta 非持久化语义的描述
- **文件(行号)**: `dayu/host/README.md:91-92`（"memory catch-up page size"），`docs/host/design.md:99`（"memory projection catch-up page size"），`docs/host/design.md:339`（delta 非持久化）
- **直接证据**: README 描述从 "memory catch-up batch size" 更新为 "memory catch-up page size"，与设计文档对齐。设计文档明确声明 delta 不持久化语义。
- **结论**: README 与设计文档一致。

### 5. 测试覆盖

- **文件**: `tests/host/test_event_log_store.py` (+273 行), `tests/host/test_projection_runner.py` (+211 行), `tests/host/test_run_input_builder.py` (+249 行), `tests/host/test_memory_repair.py`（重构）, `tests/host/test_dispatch_scheduler.py` (+67 行), `tests/host/test_engine_ingest_mapping.py` (+166 行)
- **关键测试覆盖**:
  - `test_projection_runner.py`: `test_runner_advances_covered_cursor_without_apply_when_no_matching_rows` — covered cursor 跳过不相关 row
  - `test_projection_runner.py`: `test_payload_parsing_failure_records_failure_without_advancing_checkpoint` — 解析失败不推进 checkpoint
  - `test_projection_runner.py`: `test_consumer_write_failure_rolls_back_write_and_checkpoint` — consumer 失败 rollback
  - `test_run_input_builder.py`: `test_inline_delta_uses_memory_filter_and_covers_required_cursor` — inline repair 使用共享 filter
  - `test_run_input_builder.py`: `test_inline_delta_unable_to_cover_required_cursor_raises_repair_required` — covered cursor 不满足时 fail-closed
  - `test_run_input_builder.py`: `test_small_memory_lag_repairs_inline_without_checkpoint_advance` — inline repair 不推进 projection checkpoint
- **结论**: 关键行为均有测试覆盖，覆盖边界包括正常路径、失败路径、covered cursor 推进/不推进、inline repair filter 共源。

## Findings

未发现实质性问题。

## Open Questions

- 无。所有 work unit goals 均已通过交叉验证，未发现代码、设计文档、测试或契约不一致。

## Residual Risk

- **ConfigLoader 与 Host API 命名差异**：`dayu/runtime/config_loader.py:488` 使用 `memory_projection_catch_up_batch_size`（`catch_up` 带下划线），而 Host API 使用 `memory_projection_catchup_batch_size`（`catchup` 单字）。当前通过 `host_assembly.py:692` 显式映射，不构成契约漂移；但若未来有人绕过 `host_assembly.py` 直接从 ConfigLoader 构造 Host options，字段名不匹配会被类型检查捕获。风险低。

- **covered cursor 边界语义的文档化**：`FilteredEventLogPage.covered_event_sequence` / `covered_event_id` 在部分匹配（1 ≤ matching < limit）时复用 boundary_row 作为 covered row。此行为在 `read_events_after_matching` 的 docstring 中有描述（`dayu/host/durable/event_log.py:652-657`），但在 `FilteredEventLogPage` 的 dataclass docstring 中未显式说明零匹配时 covered cursor 也可能推进（虽在 `__post_init__` 校验中体现）。建议在 `FilteredEventLogPage` docstring 中补一句"零匹配时 covered cursor 为扫描区间的 boundary row 以表达跳过语义"，降低未来维护者误解风险。

- **测试未覆盖场景**：未发现测试遗漏的关键行为。现有测试覆盖了 covered cursor 推进、checkpoint 回退、inline repair filter 共源、delta event 非持久化、rebuild/catch-up 到 target/idle/failure 的完整状态机。
