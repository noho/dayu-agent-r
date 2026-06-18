# WU-CLI-ACTIVITY-01 follow-up delta EventLog and projection catch-up plan

## 元数据

- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- 类型：architecture-sensitive bug fix / hardening
- 当前 gate：plan gate only
- 日期：2026-06-18
- plan gate 观察到的分支：`wu-cli-activity-01`
- artifact path：`docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- 设计真源：`docs/host/design.md`；`docs/engine/design.md`
- 总控真源：`docs/host/issues-implementation-control.md`
- 约束：本 gate 只创建本 plan artifact；不实现代码、不运行 broad tests、不提交、不 push、不改 GitHub issue。

## Goal

本 follow-up 解决 WU-CLI-ACTIVITY-01 closeout 后暴露的三个同源问题：

1. Host 默认不再把 `content_delta`、`reasoning_delta`、`tool_call_delta` 这类 per-delta EngineEvent 持久化到主 EventLog。
2. Conversation Memory projection catch-up / rebuild 从 consumer checkpoint 追到目标 cursor、idle 或 failure；`memory_projection_catchup_batch_size` 只保留为内部分页 / transaction page size，不再表达“本轮最多追多少事件”的语义预算。
3. Projection scan 与 RunInputBuilder inline repair 使用 consumer `event_filter` 作为过滤真源；SQL/read path 不再复制 memory event type 列表。

成功后，durable replay 不承诺 token-level delta replay；terminal / final answer / canonical facts / accepted compact facts 仍是 durable truth。Projection catch-up 不会因为 LIMIT N 语义预算提前停止在目标 cursor 之前。RunInputBuilder inline repair 与 durable projection 使用同一套 filter/read 语义。

## Motivation

动机整体成立；其中 inline repair 与 durable projection 的 memory filter 当前语义等价，真实风险是未来维护漂移，而不是当前已经出现 material 不一致。

第一性原理上，Engine 的 delta 是本次 `EngineEvent stream` 的运行观察，不是 Host 必须长期保存的 durable fact。Host durable truth 应优先保存可恢复、可审计、可重建的事实：Run / Attempt 生命周期、用户输入、工具接受事实、terminal final answer、compact canonical fact、usage / diagnostic / projection signal 等。把 token 级增量默认写入主 EventLog 会扩大 durable store、让 replay 暗示 token-level 保真，并让 projection catch-up 被大量无关 preview row 拖慢。

Projection catch-up 的正确语义是 consumer 从自己的 checkpoint 追到调用方要求的 cursor 或当前 idle，而不是“扫描 N 行后停下”。`LIMIT N` 可以存在，但只能是 SQL page size / transaction 粒度；它不能成为 correctness path 的停止条件。若 consumer 只关心 canonical memory facts，read path 就应按 consumer filter 找下一条相关事件，同时安全推进 checkpoint 越过不相关事件。

RunInputBuilder inline repair 是 Conversation Memory projection 的临时只读修复。当前 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row` 与 Conversation Memory consumer 的 filter 语义等价，但它们是两份独立列表；未来 memory event type 调整时容易漂移。计划只做最小共源化：提供模块级 `conversation_memory_projection_event_filter()` 作为单一 filter 真源，consumer 和 inline repair 都调用它。

## Success Signals

- Host ingest 接收 `content_delta`、`reasoning_delta`、`tool_call_delta` 时默认不 append EventLog row；`EngineIngestResult.status` 仍为 accepted，不触发 rejected diagnostic，不停止 worker stream。
- `read_session_host_events_after`、`stream_run_events`、CLI activity backfill 不再从 EventLog 看到 per-delta rows；final answer、terminal lifecycle、tool requested / result / batch、usage、diagnostic 和 compact events 行为不退化。
- `ProjectionRunner` 使用 consumer `event_filter` 派生的 SQL/read criteria 读取下一批相关 rows，并能在无匹配 row 时把 checkpoint 推进到 target cursor 或当前 latest cursor。
- `catch_up_conversation_memory_projection(...)` / `rebuild_conversation_memory_projection(...)` 不再接受或返回 `MemoryProjectionCatchupBudget`、`budget_exhausted`、`max_batches`、`max_scanned_events` 这类语义预算字段；停止原因只保留 `idle`、`target_reached`、`failure`。
- `memory_projection_catchup_batch_size` 仍保留，含义改为内部 page size；多页循环会继续直到 target / idle / failure。
- After-commit / after-compact hot-path hook 不执行无界 correctness catch-up；若保留机会性 projection 动作，只能是显式页数上限的 latency-only maintenance，不得用其结果判定 required cursor 是否满足。
- RunInputBuilder inline repair 使用 `conversation_memory_projection_event_filter()`，Conversation Memory consumer 也由同一 helper 构造 `event_filter`；不再使用 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row` 这套并行 memory type 逻辑。
- 不引入 durable schema 变更；若实现发现需要新增 EventLog 列、checkpoint 列或 durable index 才能满足语义，必须停止并回到设计讨论。
- 受影响测试通过，`python -m pyright dayu/ tests/ utils/` 无新增或扩散错误。

## Non-goals / Scope Boundary

- 不新增 transient fanout / SSE / websocket / in-memory live delta bus。
- 不承诺 durable token-level replay，不补偿历史 per-delta rows，不迁移旧库。
- 不改变 Engine delta producer contract；Engine 仍可 emit `content_delta`、`reasoning_delta`、`tool_call_delta`。
- 不改变 terminal final answer、tool accept barrier、canonical fact、usage、context compaction、audit、tool trace、outbox 的事实语义。
- 不重写 ProjectionRunner 为大型调度系统，不引入公平性、优先级、后台 worker 或跨 consumer scheduler。
- 不移除或重命名 `memory_projection_catchup_batch_size` 配置字段；本 WU 必须更新 docstring / README / design 表述，明确它是内部 page size，不是单次 catch-up 的语义预算。
- 不把 `ProjectionEventFilter` 暴露为 public Host API。
- 不修改财报工具、Fins storage、Service scene assembly、CLI composer 行为。

## Design Alignment

- `docs/engine/design.md` 已固定：`content_delta`、`reasoning_delta`、`tool_call_delta` 是 EngineEvent / RunnerEvent 的增量事件；是否进入 Host preview、canonical EventLog、memory 或 audit，由 Host ingest 与治理策略决定。
- `docs/engine/design.md` 已固定：EngineEvent 不提供 Host `event_sequence`、持久化 cursor 或 replay 语义；这些属于 Host。
- `docs/host/design.md` 固定 Host 是 EventLog / lifecycle / memory / projection 治理真源，Projection、timeline、audit、tool trace、outbox、memory snapshot 都不能反向成为 EventLog 真源。
- `docs/host/design.md` 当前第 3213 行同时写着 catch-up “执行预算”和“不得让 dispatch hot path 无上限同步补账”。implementation 必须把 correctness 语义改成：ordinary dispatch 前 memory snapshot 不覆盖 required cursor 时，Host 通过 page-bounded catch-up / rebuild 追到 required cursor、idle 或 failure；page size 不是语义预算。同时保留 hot-path 硬约束：after-commit / after-compact 不能做无界同步补账，只能移除机会性同步动作，或执行 latency-only、显式页数上限的 maintenance。
- `docs/host/design.md` / `docs/engine/design.md` 不需要引入 durable schema 变化。EventLog 现有 `event_sequence`、`event_class`、`event_type` 足以表达 filter-aware read。

## First-principles Judgment And Direct Code Evidence

直接代码证据：

- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:1007) 当前 `_is_preview_event(event)` 命中后直接 `_append_preview_event(...)` 并返回单 EventLog row。
- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4666) 到 [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4687) 当前把 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 全部归入 preview event。
- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:2394) `_append_preview_event(...)` 会以 `EventClass.PREVIEW` append durable EventLog row。
- [dayu/host/read_api.py](/Users/leo/workspace/dayu-agent-r/dayu/host/read_api.py:481) 与 [dayu/host/read_api.py](/Users/leo/workspace/dayu-agent-r/dayu/host/read_api.py:520) public read path 从 EventLog 补读 rows；因此 per-delta preview row 一旦持久化，就会进入 public backfill / stream。
- [dayu/host/projection.py](/Users/leo/workspace/dayu-agent-r/dayu/host/projection.py:562) 当前 ProjectionRunner 每步调用全局 `read_events_after(..., limit=1)`。
- [dayu/host/projection.py](/Users/leo/workspace/dayu-agent-r/dayu/host/projection.py:587) 到 [dayu/host/projection.py](/Users/leo/workspace/dayu-agent-r/dayu/host/projection.py:606) 当前先把全局 row 构造成 projection event view，再用 `consumer.event_filter.matches(event)` 在内存过滤；不匹配也推进 checkpoint。
- [dayu/host/durable/event_log.py](/Users/leo/workspace/dayu-agent-r/dayu/host/durable/event_log.py:452) `read_events_after(...)` 只有 `event_sequence > ? ORDER BY event_sequence LIMIT ?`，没有 event class / type filter。
- [dayu/host/durable/memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/durable/memory.py:240) Conversation Memory consumer 已有 `ProjectionEventFilter`，只消费 `EventClass.CANONICAL_FACT` 下的 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`、`CONTEXT_COMPACTED`。
- [dayu/host/memory_repair.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory_repair.py:49) 当前存在 `MemoryProjectionCatchupBudget`，并在 [dayu/host/memory_repair.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory_repair.py:336) 到 [dayu/host/memory_repair.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory_repair.py:367) 以 `BUDGET_EXHAUSTED` 作为停止原因。
- [dayu/host/open_host.py](/Users/leo/workspace/dayu-agent-r/dayu/host/open_host.py:152) 到 [dayu/host/open_host.py](/Users/leo/workspace/dayu-agent-r/dayu/host/open_host.py:170) after-commit memory projection 构造一批 budget。
- [dayu/host/dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:324) 到 [dayu/host/dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:344) compact accepted 后也构造 opportunistic budget。
- [dayu/host/run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:236) 定义 `_MEMORY_EVENT_TYPES`，并在 [dayu/host/run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:1210) 通过 `_is_memory_projection_row(...)` 过滤 inline repair rows。这是独立于 consumer `event_filter` 的并行 memory type 逻辑。

## Affected Files / Modules

Plan gate 创建：

- `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`

后续 implementation 允许修改：

- `docs/host/design.md`
- `docs/engine/design.md`，仅当需要把 Host 默认不持久化 per-delta 的边界写得更明确；当前证据显示可选。
- `docs/host/issues-implementation-control.md`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/projection.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory_repair.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `dayu/host/run_input.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_host_event.py` / `tests/host/test_watch_session_events.py` / `tests/host/test_host_activity_event_projection.py`，按现有覆盖落点选择。
- `tests/host/test_event_log_store.py`
- `tests/host/test_projection_runner.py`，若不存在则新增。
- `tests/host/test_memory_repair.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_run_input_builder.py` 或现有 RunInputBuilder memory tests，按当前文件命名选择。
- `tests/README.md` 与 `dayu/host/README.md`，仅在 README 更新约束判定需要时修改。

后续 implementation 不应修改：

- `dayu.engine` public contract 或 Runner delta 生产逻辑。
- `dayu.service` / `dayu.ui` / `dayu.fins`。
- durable schema migration 或旧库兼容读取。
- Tool Trace / Audit / Outbox projection 语义，除非 filter-aware ProjectionRunner 统一测试自然覆盖其 existing consumer。

## Contract / Schema / State / Public API Changes

- Public Host API：签名无计划变更；但 EventLog-backed stream / read 行为会变更，默认不再返回 `content_delta`、`reasoning_delta`、`tool_call_delta` per-delta rows。
- Engine public contract：无计划变更。
- Durable schema：无计划变更。若实现阶段认为必须新增列、索引或 checkpoint schema，标记 blocking，停止实现并回到设计真源。
- EventLog durable semantics：默认不再持久化 per-delta preview rows；非 delta preview、canonical facts、diagnostic、projection signal 仍按现有语义持久化。
- Run / Attempt 状态机：无计划变更。
- Internal contract：
  - 新增或扩展 durable EventLog filtered read primitive，表达 class / type 过滤和 covered cursor。
  - ProjectionRunner 的 `limit` / memory repair 的 `batch_size` 只表示 page size。
  - 删除 `MemoryProjectionCatchupBudget` 与 `BUDGET_EXHAUSTED` 停止语义。
  - Hot-path opportunistic maintenance 若保留，使用独立 latency-only page cap；该 cap 不属于 correctness catch-up contract。
  - RunInputBuilder inline repair 改用 `conversation_memory_projection_event_filter()` 的 shared read semantics。

## Implementation Decisions

1. Delta ingest 默认 non-durable。

   `content_delta`、`reasoning_delta`、`tool_call_delta` 通过 durable context validation 后，返回 accepted ingest result，但 `events=()`。不 append preview row，不 append rejected diagnostic，不停止 worker stream，不触发 queue promotion。若 consume loop 通过 `result.events` 更新 `last_accepted_event_id`，空 events 必须保持上一条 durable accepted event id。

2. 非 delta preview 保持 durable。

   `ITERATION_STARTED`、`CONTENT_COMPLETED`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE`、`ITERATION_COMPLETED` 等现有非 delta preview 仍可 durable append，除非 implementation 发现其中某类只是 per-delta 的派生碎片；本 WU 不扩大裁剪范围。

3. Filter-aware EventLog read 返回 covered cursor。

   新增 durable-neutral read filter 类型，例如 `EventLogReadFilter` / `EventLogReadClassFilter`。Projection 层从 consumer `ProjectionEventFilter` 机械转换为 durable read filter；durable 层不 import projection 层。

   新 read primitive 返回 `FilteredEventLogPage`：

   - `rows`：按 `event_sequence` 升序排列的匹配 rows。
   - `covered_event_sequence`：本次 read 已证明可以跳过到的全局 cursor；它永远不小于调用方传入的 `cursor`。
   - `covered_event_id`：仅当 `covered_event_sequence > cursor` 时必填，并且必须对应真实 EventLog row。`covered_event_sequence == cursor` 且 `covered_event_id is None` 表示本次没有可推进的真实 row。

   边界不变量：

   - EventLog 为空，或 `cursor` 已在 latest row 之上时，返回 `rows=()`、`covered_event_sequence=cursor`、`covered_event_id=None`，表示 idle 且不推进 checkpoint。
   - `cursor` 正好等于 latest row 时，同样返回 `covered_event_sequence=cursor`、`covered_event_id=None`；调用方无需再次推进到同一 row。
   - 当有匹配 row 且达到 page limit 时，covered cursor 是最后一条匹配 row。
   - 未达到 page limit 时，covered cursor 是 `cursor` 之后、读边界之内可证明的最大真实 EventLog row。若 `max_event_sequence` 超过实际 latest，只能覆盖到实际 latest row；若 `max_event_sequence` 在 EventLog 范围内但没有精确 row，只能覆盖到 `<= max_event_sequence` 的最近真实 row。
   - 若 `cursor` 与读边界之间没有任何真实 row，则返回 `covered_event_sequence=cursor`、`covered_event_id=None`，不得返回不存在的 sequence。
   - 匹配 rows 查询与 covered row 查询必须在调用方提供的同一个 transaction 内完成。

4. ProjectionRunner 仍保持短事务和 per-row apply 原子性。

   Runner 每个 write transaction 最多 apply 一条 matching row，并推进 checkpoint 到该 row。若 filtered read 没有返回 matching row 但 `covered_event_sequence` 大于当前 checkpoint，则只推进 checkpoint 到 covered cursor 并 clear failure，不调用 consumer。这样既避免读取不相关 rows，又保留 projection checkpoint 表达“已扫描到全局 cursor”的语义。

5. Memory catch-up 不再有总预算。

   `catch_up_conversation_memory_projection(...)` 和 `rebuild_conversation_memory_projection(...)` 循环调用 runner page，直到：

   - target cursor reached；
   - idle；
   - projection failure。

   `batch_size` 只控制单次 page limit。删除 `_bounded_batch_limit`、`_budget_scanned_events_exhausted`、budget 日志字段和 result 中的 budget 字段。

6. After-commit / after-compact 不做无界 correctness catch-up。

   `open_host._MemoryProjectionCatchupPort` 与 `dispatch` compact accepted follow-up 不再调用 required correctness catch-up，也不再构造 `MemoryProjectionCatchupBudget`。如果保留机会性同步动作，必须改名并改语义为 latency-only maintenance：使用命名常量限制最多处理的 page 数，达到上限时只记录 maintenance incomplete / behind，不产生 required cursor failure，也不得把上限暴露成“已追平”的正确性结论。若实现阶段发现 maintenance helper 会显著扩大改动面，选择更小方案：直接移除 after-commit / after-compact 的机会性 memory projection 动作，让下一次 required catch-up 负责正确性。

7. Inline repair 复用 consumer filter。

   `DurableMemorySnapshotProvider._repair_inline_delta(...)` 不再用 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row`。`dayu/host/durable/memory.py` 提供模块级 `conversation_memory_projection_event_filter() -> ProjectionEventFilter`，`ConversationMemoryProjectionConsumer.__init__` 和 inline repair 都调用该 helper。Inline repair 通过 shared filtered read helper 读取当前 session 在 snapshot cursor 到 required cursor 之间的 matching canonical facts，按同一 `_memory_projection_event_from_row(...)` 投影。

   session 条件可以作为 inline repair 的上下文范围传给 durable read helper；它不是第二套 memory event type 真源。

8. Required cursor 覆盖仍必须显式校验。

   Inline repair 过滤读取 matching rows 后，必须证明 covered cursor 已达到 `required_event_sequence`。若无法覆盖，抛 `MemoryProjectionRepairRequired`。成功时临时 snapshot cursor 设置为 `required_event_sequence` 及其 EventLog id，而不是最后一条 matching memory row。

## Implementation Slices

### Slice 1：设计真源与 delta durable 语义同步

Objective：

- 更新设计文档，明确 Host 默认不持久化 per-delta EventLog rows，projection catch-up page size 不是语义预算。

Allowed files：

- `docs/host/design.md`
- `docs/engine/design.md`，仅限补一句 Host durable policy 边界；若现有文字足够，可不改。
- `docs/host/issues-implementation-control.md`

Exact changes：

- 将 Host design 中 “超出 catch-up 执行预算” 改为 “required catch-up / rebuild 追到 required cursor、idle 或 failure；page size 只控制单批读取 / transaction 粒度”。同时保留 “dispatch hot path 不得无上限同步补账” 约束，并说明 after-commit / after-compact 只能执行 bounded latency-only maintenance 或不执行机会性同步 projection。
- 在 Host EventLog / EngineEvent ingest 语义处补充：Host 默认不把 `content_delta`、`reasoning_delta`、`tool_call_delta` 写入主 EventLog；durable replay 不承诺 token-level delta。
- 更新 `memory_projection_catchup_batch_size` 配置说明：它是 required catch-up / rebuild 的内部 page size，不是“本次最多追多少事件”的语义预算。
- 控制文档记录该 follow-up 的 plan artifact、状态和 next entry point。

Tests / validation：

- `git diff --check`
- 文档 grep：`rg -n "catch-up 执行预算|budget_exhausted|content_delta|tool_call_delta" docs/host/design.md docs/engine/design.md docs/host/issues-implementation-control.md`

Completion signal：

- 设计真源不再把 LIMIT / budget 表述为 memory catch-up correctness 停止条件。

Stop condition：

- 若文档更新需要新增 public stream / replay contract，停止并回到用户确认；本 follow-up 不设计 transient delta fanout。

### Slice 2：Host ingest 移除 per-delta EventLog 默认持久化

Objective：

- `content_delta`、`reasoning_delta`、`tool_call_delta` 被 Host 接受但默认不 append EventLog row。

Allowed files：

- `dayu/host/engine_ingest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_host_event.py` / `tests/host/test_watch_session_events.py` / `tests/host/test_host_activity_event_projection.py`，按现有断言落点修改。

Exact changes：

- 新增私有 helper，例如 `_is_non_durable_delta_event(event: EngineEvent) -> bool`，只匹配 `ContentDeltaData`、`ReasoningDeltaData`、`ToolCallDeltaData`。
- 在 `_ingest_validated(...)` 中于 `_is_preview_event(event)` 之前处理 non-durable delta，返回 accepted empty-event result。
- 从 `_is_preview_event(...)` 移除三类 delta，避免未来分支顺序调整后重新 durable append。
- 新增或复用 `_no_event_accepted_result(reason: str | None = None) -> EngineIngestResult`，保持 `terminal_closeout=False`、`promotion_triggered=False`、`stop_worker_stream=False`。
- 不改变 non-delta preview payload builder。

Tests / validation：

- 构造 `CONTENT_DELTA` / `REASONING_DELTA` / `TOOL_CALL_DELTA` ingest，断言 result accepted、`events == ()`、EventLog 中没有对应 `event_type` row。
- 构造 `CONTENT_COMPLETED` 或 `TOOL_CALL_REQUESTED`，断言仍 append preview row。
- 构造 final answer，断言 terminal canonical facts / final answer durable row 不受影响。
- public watch / stream 测试断言 delta 不出现在 backfill 中；终态事件仍出现。

Completion signal：

- per-delta EngineEvent 不再进入主 EventLog；非 delta durable 行为保持。

Stop condition：

- 如果 scheduler / worker consume loop 把 empty `events` 视为 rejection 或 fatal，需要先修 consume loop contract 并补测试；不得用 fake EventLog row 填充。

### Slice 3：EventLog filter-aware read 与 ProjectionRunner catch-up 语义

Objective：

- ProjectionRunner 使用 consumer filter 驱动 SQL/read path，并移除以 LIMIT N 为语义停止条件的 catch-up 行为。

Allowed files：

- `dayu/host/durable/event_log.py`
- `dayu/host/projection.py`
- `tests/host/test_event_log_store.py`
- `tests/host/test_projection_runner.py`，若不存在则新增。
- 现有 projection consumer tests，按失败情况最小更新。

Exact changes：

- 在 durable EventLog primitive 中新增 neutral filter dataclass：
  - `EventLogReadClassFilter(event_class: EventClass, event_types: tuple[str, ...] | None)`
  - `EventLogReadFilter(class_filters: tuple[EventLogReadClassFilter, ...])`
  - `FilteredEventLogPage(rows: tuple[EventLogRow, ...], covered_event_sequence: int, covered_event_id: str | None)`
- 新增 `read_events_after_matching(transaction, cursor, *, event_filter, limit, max_event_sequence=None, session_id=None) -> FilteredEventLogPage`。
- SQL 必须由 filter 生成 `event_class` / `event_type` 条件；不得在 durable read helper 中写 memory-specific event type。
- `max_event_sequence` 存在时 SQL 限制 `event_sequence <= max_event_sequence`。
- 所有查询必须在调用方提供的同一个 transaction 内完成，包括 matching rows 查询和 covered row 查询。
- 当 rows 数量小于 limit 时，helper 查询 covered row 并返回 covered cursor；covered row 可以不匹配 filter，但只要 `covered_event_sequence > cursor` 就必须存在于 EventLog 且提供 `covered_event_id`。
- 空 EventLog、`cursor` 位于 latest row 或已超过 latest row 时，返回 `covered_event_sequence=cursor`、`covered_event_id=None`，调用方不得推进 checkpoint。
- `max_event_sequence` 超过实际 latest 时，covered cursor 只能推进到实际 latest row；`max_event_sequence` 没有精确 row 时，covered cursor 只能推进到 `<= max_event_sequence` 的最近真实 row。
- 在 `projection.py` 中新增 `_event_log_read_filter_from_projection_filter(...)`，唯一从 consumer `event_filter` 转换 durable read filter。
- `ProjectionRunner._process_next_event(...)` 改用 filtered page：
  - 有 matching row：构造 `ProjectionEventView`、apply、checkpoint advance 到该 row。
  - 无 matching row 且 covered cursor 大于 checkpoint：checkpoint advance 到 covered cursor，不 apply。
  - 无 matching row 且 covered cursor 等于 checkpoint：返回 idle。
- `run_once(limit=...)` 的 `limit` 文档改为 page size / step cap；它不再表达追平总预算。若当前 public/internal tests 依赖 scanned unmatched rows 数量，改为断言 checkpoint / matched / applied 语义。

Tests / validation：

- EventLog read helper：在 canonical、preview、diagnostic 混排 rows 中，只返回 filter 命中 rows，并返回正确 covered cursor。
- EventLog read helper：空 EventLog 返回 `covered_event_sequence=cursor`、`covered_event_id=None`。
- EventLog read helper：`max_event_sequence` 超过 actual latest 时 covered cursor 是 actual latest；`max_event_sequence` 没有精确 row 时 covered cursor 是最近的真实 row `<= max_event_sequence`。
- ProjectionRunner：consumer filter 只关心 canonical type A；EventLog 中大量 preview / unrelated canonical rows 不触发 consumer apply，但 checkpoint 最终追到 latest / target。
- ProjectionRunner：`max_event_sequence` 小于下一条 matching row 时，不 apply row，但 checkpoint 追到 target。
- ProjectionRunner failure：matching row apply 抛错时记录 failure，不越过 failed row。

Completion signal：

- ProjectionRunner 不再为了 consumer filter 逐行读取无关 EventLog rows；checkpoint 仍表示已覆盖全局 cursor。

Stop condition：

- 如果 checkpoint schema 不允许以 non-matching covered row 作为 checkpoint event id，停止并回到 durable schema discussion。当前 schema 允许 checkpoint 指向任意 EventLog row，因此预计不阻塞。

### Slice 4：Conversation Memory repair 去预算化并迁移调用方

Objective：

- 删除 memory projection correctness 语义预算；required catch-up / rebuild 只传 page size / target cursor，并保证 after-commit / after-compact hot path 不做无界同步补账。

Allowed files：

- `dayu/host/memory_repair.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_logging.py`，仅限删除旧 budget 日志断言。

Exact changes：

- 删除 `MemoryProjectionCatchupBudget`、`MemoryProjectionRepairPurpose`、`MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED`。
- `ConversationMemoryProjectionRepairResult` 删除 `budget_exhausted`、`max_batches`、`max_scanned_events`；保留 `batches_used`、`events_scanned`、`events_matched`、`events_applied`、`duplicates`、`failures`、`target_reached`、`max_event_sequence`。
- `catch_up_conversation_memory_projection(...)` / `rebuild_conversation_memory_projection(...)` 删除 `budget` 参数。
- `_run_memory_projection_bounded(...)` 重命名为 `_run_memory_projection_until_stop(...)` 或等价名称；循环直到 target / idle / failure。
- Required correctness path 只调用 `_run_memory_projection_until_stop(...)`；该路径没有 `max_batches`、`max_scanned_events` 或 `budget_exhausted`。
- Hot-path opportunity path 不能调用 required catch-up。实现二选一，优先选择改动更小且证据支持的方案：
  - 保留 after-commit / after-compact 机会性 projection，但改为 `run_conversation_memory_projection_maintenance(...)` 或等价私有 helper；该 helper 只接受 page size 与命名常量 page cap，达到 cap 时返回 maintenance incomplete，不产生 required cursor failure，不声称 target reached。
  - 如果拆分 maintenance helper 会让调用面或结果类型膨胀，直接移除 after-commit / after-compact 机会性 projection hook。
- `open_host._MemoryProjectionCatchupPort` 若保留，只能暴露 maintenance 语义，不得命名为 catch-up port；否则删除该 port。
- `dispatch` compact accepted follow-up 若保留，只能调用 bounded maintenance；否则删除该 follow-up。
- 所有日志移除 semantic budget fields，保留 page size、batches_used、target_reached / maintenance_incomplete、failure。
- 更新 tests：删除 budget exhausted 断言，新增 required path 多页追到 target / idle 的断言，并新增 hot-path maintenance 不超过 page cap 或 hook 被移除的断言。

Tests / validation：

- `tests/host/test_memory_repair.py` 覆盖：
  - batch_size=1 且多条 relevant rows 时，catch-up 多页追到 idle。
  - max_event_sequence 指向目标 cursor 时，多页追到 target。
  - rebuild 多页追到 target。
  - projection failure 停在 failed matching row，不继续推进。
- `tests/host/test_open_host_runtime.py` 断言 after-commit 不调用 required catch-up；若保留 maintenance，断言最多处理命名常量允许的 page 数，未追平只记录 maintenance incomplete。
- `tests/host/test_dispatch_scheduler.py` 断言 dispatch required repair 仍要求 target reached；compact accepted hot path 不做无界 catch-up，不再记录 budget exhausted。

Completion signal：

- 代码库中无 `MemoryProjectionCatchupBudget`、`budget_exhausted`、`BUDGET_EXHAUSTED` memory repair 语义引用；after-commit / after-compact 不存在无界同步 correctness catch-up。

Stop condition：

- 如果无法在不扩大设计面的前提下把 hot-path opportunity path 表达为 latency-only maintenance，删除该机会性 hook；不得恢复 LIMIT N correctness 语义预算。

### Slice 5：RunInputBuilder inline repair 复用 filter-aware read

Objective：

- Inline repair 与 Conversation Memory consumer 使用同源 filter/read semantics。

Allowed files：

- `dayu/host/run_input.py`
- `dayu/host/durable/memory.py`，仅限新增或复用 `conversation_memory_projection_event_filter()`；不写新 projection 语义。
- `dayu/host/projection.py`，仅限复用 filter conversion helper。
- RunInputBuilder memory tests。

Exact changes：

- 删除 `_MEMORY_EVENT_TYPES` 与 `_is_memory_projection_row(...)`。
- 在 `dayu/host/durable/memory.py` 提供模块级 `conversation_memory_projection_event_filter() -> ProjectionEventFilter`，它是 Conversation Memory projection filter 的单一真源。
- `ConversationMemoryProjectionConsumer.__init__` 调用 `conversation_memory_projection_event_filter()` 设置 `event_filter`。
- `DurableMemorySnapshotProvider` 的 inline repair 也调用 `conversation_memory_projection_event_filter()`；不得实例化 consumer 只为读取 filter，不得把 memory event type tuple 复制回 `run_input.py`。
- Inline repair 使用 filtered EventLog read helper，附加 `session_id=snapshot.session_id` 和 `max_event_sequence=required_event_sequence`。
- 对返回的 matching rows 逐条调用 `project_conversation_memory_event(...)`。
- 通过 `FilteredEventLogPage.covered_event_sequence` 校验已覆盖 `required_event_sequence`；成功后通过 required row id 设置临时 `MemorySnapshotCursor`。
- 保留现有 `max_lag_events_for_inline_delta` / `max_delta_repair_events` policy：这是 inline repair 的 lag safety，不是 projection catch-up semantic budget。本 follow-up 不移除这些 policy 字段。

Tests / validation：

- Inline repair 在 delta 区间包含大量 preview / diagnostic / unrelated canonical rows 时，只投影 consumer filter 命中的 memory facts，但 cursor 覆盖 required sequence。
- 修改 helper 的测试替身或断言，证明 consumer 与 inline repair 使用 `conversation_memory_projection_event_filter()` 这一单一真源，而不是 `_MEMORY_EVENT_TYPES`。
- Inline repair 无 matching rows 但 covered cursor 到 required 时，返回原 snapshot 加 inline repair diagnostic。
- Inline repair 无法覆盖 required cursor 时仍抛 `MemoryProjectionRepairRequired`。

Completion signal：

- RunInputBuilder 不再有独立 memory event type filter；inline repair 与 durable consumer filter 同源。

Stop condition：

- 如果 helper 放置位置导致 import cycle，停止并回到设计讨论；不得退回 consumer 实例读取 filter，也不得把 memory event type tuple 复制回 `run_input.py`。

## Tests / Validation Commands

Implementation 完成后优先运行：

```bash
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_public_host_event.py tests/host/test_watch_session_events.py tests/host/test_host_activity_event_projection.py -q
pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_memory_repair.py -q
pytest tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_run_input_builder.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

如果 `tests/host/test_projection_runner.py` 或 `tests/host/test_run_input_builder.py` 当前不存在，implementation 应选择现有等价测试文件或新增聚焦测试文件，并在完成报告中说明。

## Docs Decision

- 必须更新 `docs/host/design.md`：移除 catch-up semantic budget 设计表述，补充 per-delta EventLog 默认不持久化。
- 必须在 `docs/host/design.md` 保留并细化 dispatch hot path 约束：required correctness catch-up 无语义 LIMIT，但 after-commit / after-compact 不得做无界同步补账。
- 必须更新相关配置 docstring / README / design wording，说明 `memory_projection_catchup_batch_size` 是内部 page size，不是 semantic budget；本 WU 不重命名该字段。
- `docs/engine/design.md` 当前已说明 Host 决定 delta 是否进入 durable EventLog；若实现者认为仍不够明确，可以补一句“不承诺 Host durable token-level delta replay”，但不要求 Engine contract 变更。
- 必须更新 `docs/host/issues-implementation-control.md`：记录 follow-up plan artifact、当前 gate、后续 implementation / validation / residual risk。
- README 更新按 AGENTS.md 触发规则执行。若只改 Host 内部语义且 `dayu/host/README.md` 已覆盖 “PREVIEW 是 UI 流式体验事件” 的旧表述，implementation 必须先阅读该 README 的更新约束，再决定是否同步说明 per-delta 默认不 durable。

## Risks / Open Questions

- Risk 1：当前 public watch 是 EventLog-backed；移除 durable delta 后，不会再有 token-level live/backfill delta。用户已明确 durable replay 不承诺 token-level delta replay；本 WU 不补 transient live bus。状态：accepted scope。
- Risk 2：filter-aware ProjectionRunner 跳过 unmatched rows 时必须仍能推进 checkpoint 到真实 EventLog row。当前 checkpoint schema 要求 `checkpoint_event_id` 非空并引用 EventLog row；计划通过 `covered_event_id` 满足，不需要 schema 变更。状态：covered by Slice 3。
- Risk 3：after-commit / after-compact 若继续执行机会性 projection，可能在大量 matching memory facts 场景下阻塞 hot path。状态：covered by Slice 4；必须通过 bounded latency-only maintenance 或删除机会性 hook 解决，不得推迟为无界同步补账。
- Risk 4：`events_scanned` 诊断在 filter-aware read 后含义可能变化。implementation 应更新 docstring / tests，使其不再被用作 semantic budget。状态：covered by Slice 3 / Slice 4。
- Risk 5：保留 `memory_projection_catchup_batch_size` 名称但改变语义，可能误导后续维护者。状态：accepted tradeoff in current WU，必须通过 docstring / README / design wording 明确 page size 语义；字段重命名若需要，另立后续 WU。
- Blocking open questions：无。

## No-overdesign Rationale

本方案只改三处直接根因：delta durable 默认、ProjectionRunner read path、Memory repair / inline repair filter 语义。它不引入新的 stream subsystem、不改变 public API signature、不改 durable schema、不建设后台 projection scheduler、不迁移历史 EventLog。Filter-aware read 使用现有 EventLog class / type / sequence 列即可表达，page size 继续服务内存和 transaction 控制；required correctness path 不保留 LIMIT N 预算，hot-path opportunity path 只允许 bounded maintenance 或直接移除，因此同时满足 correctness 与 dispatch hot path 约束。

## Completion Report Format

Implementation closeout 必须按以下格式汇报：

```text
改动：
- ...

验证：
- ...

文档：
- ...

风险 / 未覆盖：
- ...

后续入口：
- plan review / implementation review artifact path 或 next gate
```
