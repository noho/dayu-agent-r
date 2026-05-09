# Host 开发手册

本文档是 `dayu.host` 的包级开发手册。它不是 `docs/host/` 的文档索引，也不记录迁移过程、
Phase 流程、review 过程或 PR 流程。

## 当前状态

`dayu.host` 当前落地 P5 no-full-governance 纵向 smoke 所需的最小 Run harness、内存态 RunEventStore、
Host-owned ToolRuntime 截断 / 补读、Host 内部 Conversation Memory / RunInputBuilder、context overflow
compact retry，以及公共 tool declaration 契约：

- 包根暴露 Run 级契约与 `await start_run(request)`、`stream_run_events(run_id, after=cursor)`、
  `await get_run_result(run_id)`、`await get_tool_fetch_more_handle(request)`、
  `await fetch_more_tool_result(request)`。
- `start_run` 是 async 入口，返回 `RunStream`，包含 `RunHandle` 与 `RunEvent` 异步流；被 await 时会立即启动
  内存后台任务。
- Host 内部通过 `LocalProxy -> EngineWorker -> dayu.engine.run_agent_messages` 调用 Engine 函数式入口。
- `EngineEvent` 会先被翻译为 `RunEventDraft`，再由 Host `RunEventStore.append` 生成 cursor-bearing
  `RunEvent`。
- `RunStream.events` 与 `stream_run_events` 都是 store 的订阅视图；事件必须先 append，再被订阅流消费。
- cursor 由 Host store 在单个 run 内分配，`after` 使用 exclusive 语义，不绑定 Engine sequence。
- RunEvent 已区分 `canonical` / `preview`：content delta、reasoning delta、content completed 为 preview；
  终态、工具、usage、provider protocol error、lifecycle 等当前事件为 canonical。
- `get_run_result` 是非阻塞快照补查，只从已 append 的 canonical terminal RunEvent 推导结果。
- `start_run` 会先 append Host-owned canonical `USER_INPUT_ACCEPTED`，再从 EventLog 中的该事件与
  session memory snapshot 构造交给 Engine 的 `RunInput`；该 append 失败时不会启动 Engine。
- `StartRunRequest.input` 在入口边界只接受若干 leading `SystemMessage` 加末尾唯一非空 `UserMessage`；
  assistant / tool 历史、多条 user、空 user 或 user 后追加 system 均会 fail fast，且不会启动 Engine、写
  EventLog 或污染 memory。
- `USER_INPUT_ACCEPTED` 使用封闭 `UserInputScope`，memory projection 从事件 data 推导 provenance scope；
  非法 scope 会在投影时失败。
- 同一 run 的 terminal RunEvent 会封闭当前事件流；store 拒绝 terminal 后继续 append，harness 在首个
  terminal 后关闭 worker stream。
- Host 内部 `InMemoryToolRuntime` 通过 `ToolRuntimeToolExecutor` 适配为 Engine 唯一可见的
  `ToolExecutor.execute`，Engine 不感知 cursor store、TTL、scope token 或补读实现。
- P5 smoke/test 工具使用公共 `ToolDefinition` / `ToolBundle` 声明：工具现场通过
  `@tool(..., truncate=ToolTruncateSpec(...))` 同源声明 LLM-facing `ToolSchema`、Host ToolRuntime
  `ToolTruncateSpec`、executor binding 与 `ToolDisplayInfo` 展示 metadata。Engine / Runner request
  只接收 `tuple[ToolSchema, ...]`，不会接收 definition / bundle、truncate spec、display metadata、
  tags、callable 或 executor binding。
- ToolRuntime 只按工具显式 `ToolTruncateSpec` 截断；无 spec、未启用、未知策略或非法 limit 不截断。
- `binary_bytes` 截断与补读在 Host public `JsonValue` 结果中返回 base64 ASCII 字符串；`unit="bytes"` 与
  `value_summary` 表示原始字节大小，不使用 OLD LLM projection 的 `content_base64` 包装结构。
- 截断与补读事实写入 canonical RunEvent：`tool_result_truncated`、`tool_cursor_issued`、
  `tool_fetch_more_requested`、`tool_fetch_more_completed`、`tool_fetch_more_failed`、
  `tool_cursor_expired`、`tool_cursor_denied`。
- LLM-facing 截断 tool result 会携带 `truncation.next_action="fetch_more"` 与
  `truncation.fetch_more_args={cursor, scope_token, limit?}`；Host 在写入 RunEvent 前会移除 framework
  `fetch_more` 调用参数中的 cursor 原文 / `scope_token`，并移除 accepted outcome 中仅供 LLM roundtrip 使用的
  截断凭证。
- `scope_token` 不进入 RunEvent、memory projection 或日志；Host public 调用方只能通过受控
  `get_tool_fetch_more_handle(...)` 按 session / run / 原始 tool_call / cursor fingerprint 换取短期 handle。
- framework `fetch_more` 作为最小 LLM-facing schema 与业务工具 schema 一起传给 Engine / Runner；
  `ToolRuntimeToolExecutor -> InMemoryToolRuntime.execute_tool_call` 会识别该工具名并路由到 Host ToolRuntime
  补读，不调用业务 executor，也不把它提升为完整 ToolRegistry / governance。
- 补读失败结果中的 `denied` 只表示权限 / scope 拒绝；cursor 不存在、cursor 过期和 terminal Run 都不是权限拒绝。
- terminal Run 后 `fetch_more_tool_result(...)` 返回 typed failure，不追加新 RunEvent。
- Host 内部 `InMemoryConversationMemoryStore` 只从 canonical RunEvent 投影 session memory；preview、
  reasoning delta、content delta 与 content completed 不进入 memory pool 或 RunInputBuilder replay。
- 当前 memory 结构预留 `ConversationPinnedState`、`TaskFrame`、`MemoryClaim`、`ClaimStatus`、
  `EvidenceAnchor`、`AssumptionRegister`、`UserPreferenceProfileRef`，但 Host 不解释财报业务语义。
- `ConversationPinnedState` 包含 `current_goal`、`confirmed_subjects`、`user_constraints`、
  `open_questions` 四槽，并由 `DefaultRunInputBuilder` 全量注入；该 stable block 不参与历史 pool 预算竞争。
- verified claims 与 assumptions 属于 stable ledger，同样全量注入且不参与历史 pool 预算竞争。
- assistant final answer 只作为原始对话记录 / assistant conclusion 参与连续性，不会自动升级为 verified claim。
- Host-owned worker / proxy failure 终态会以中性 terminal summary 进入原始对话记录；该摘要不被当作
  assistant final answer。
- `DefaultRunInputBuilder` 注入顺序为 pinned state、stable frame、verified claims、assumptions、
  evidence anchors / tool facts、recent raw turns、older pool、episode summary 插入位、current user；
  older pool 预算按新到旧消费，但渲染为模型可读的时间顺序。
- LLM-facing evidence anchor 与 tool fact 文本包含来源 event cursor，便于后续追溯到 canonical EventLog。
- `RunInputBuildTrace` 是 Host internal-only 诊断对象，记录 included / excluded item、裁剪原因、来源
  cursor 与估算大小；`LocalRunHarness` 仅保留最近一小段 trace 缓存，避免调试数据无界增长。trace 不进入
  `RunInput`，不进入 memory pool，也不作为下一轮事实真源。
- `LocalRunHarness` 另有更小的 RunInput 消息诊断缓存，仅用于内部 smoke 观察最近 run 的实际输入；它与
  trace 缓存独立裁剪，不进入 public API、memory pool 或事实真源。
- RunInputBuilder 与 context compact 使用同一个 Host 内部 token estimator：半角 / 窄字符按 1 unit，
  全角 / 宽字符按 2 unit，再按 2 units/token 转为 estimated tokens。该估算只用于 Host
  before / after 相对比较，不是 provider tokenizer 真源。
- `LocalRunHarness.start_run` 当前接受若干 leading `SystemMessage` 加一条非空 current `UserMessage`；
  caller system prompt 保持在前，Host Memory system block 追加在后，current user 始终为最后一条消息。
  assistant / tool 历史、多条 user、空 user 或 user 后追加 system 均会 fail fast。
- OpenAI-compatible Runner / Engine 把 provider context overflow 识别为强类型
  `context_compaction_requested` 与 recoverable `run_failed(error_code="context_compaction_required")`；
  Host 不匹配 provider 错误文本。
- `LocalRunHarness` 观察 context overflow 后，不把 recoverable Engine `RUN_FAILED` 追加成 terminal；
  它先追加 Host-owned canonical overflow / compact / retry 事实，再在同一 Run 下用 compacted `RunInput`
  启动新的 internal Engine attempt。若 Engine 发出 `context_compaction_requested` 后 stream 正常结束且缺少
  terminal overflow，Host 仍会追加 `context_overflow_observed` 事实，再按同一 compact retry 路径兜底处理。
- 若 Engine 在 `context_compaction_requested` 后意外产出非 compaction-required 终态，Host 会先追加
  Host-owned `context_compact_failed(reason=internal_error)` 事实闭合 compact 序列，再保留 Engine 原终态收口。
- P4 当前默认 deterministic compact：保留当前 `USER_INPUT_ACCEPTED`、pinned state、stable frame、
  evidence anchors、source cursor 与 tool facts；compact 前会把本 Run 已 append 的 canonical tool facts
  临时合并进 compact 输入，避免同一 Run overflow 前刚获得的工具证据断链。compact 会丢弃旧 raw turns，
  并在 compact memory system block 前部标注 internal-only / not-output-template 约束。compact completed 中
  `dropped_item_count` 记录本次丢弃的 raw turns；当前 deterministic compact 不做额外“保留但降级”的动作，
  因此 `degraded_item_count` 为 `0`。
- compact 成功必须满足 compact 后 RunInput 的 estimated token 与 char size 都严格变短，且必保事实保真；
  no-op、变长、保真失败、trace 缓存缺失、compact 分支异常或超过 compact retry 上限都会追加
  `context_compact_failed`，再由 Host-owned `RUN_FAILED` 收口。
- Engine final answer 若明显回显内部段落标题（如 `## Host Memory`、`## Tool Facts`）或字段形式的
  `tool_fact_id=`、`cursor_fingerprint=`、`source_event_cursor=`、`scope_token=`、raw EventLog metadata，
  Host 会把终态内容过滤为安全占位文本，并将结果标记为 `filtered=True`、`degraded=True`。

当前未落地：

- `client_request_id` 创建幂等。
- Session governance 与同 Session active Run 仲裁。
- workspace migration、多进程 lease / fencing 治理（已具备 SQLite WAL durable EventLog，
  恢复仅覆盖单进程重启，不含跨进程仲裁）。
- 完整 ToolRegistry、工具发现、权限治理、middleware、业务工具迁移。
- 远程 / 多进程补读。
- public memory edit / reset / forget API、跨 session / project / user memory。
- episode summary 生成与 LLM compaction scene。
- 完整取消治理、RemoteProxy、RemoteStub、Reply Outbox。

P6 已落地：

- `DurableRunEventStore` 提供 SQLite WAL 后端的 append-before-stream 持久 EventLog；
  per-run cursor 单调，跨 run 全局 position 单调。
- `RunEventData` 序列化注册表（`schema_version=1`）按封闭 type↔data 映射强校验，
  `RUN_FAILED` 同时支持 Engine `RunFailedData` 与 Host `HostRunFailedData` 两个变体。
- `RunStateStore` / `AttemptStateStore` 写 run 终态结果与 attempt 生命周期。
  Run 终态 `RunResult` 快照在 terminal RunEvent 入库的同一事务内由
  `DurableRunEventStore` 持久化，避免事件 / 快照分离失败。
  `LocalRunHarness` 在每个 attempt 起点写入 `CREATED → RUNNING`，终态写入
  `SUCCEEDED / FAILED / CANCELLED / SUSPENDED`；P8-S1 已在 internal
  `AttemptState` / store 层扩展 `STALE / RECOVERING / LOST` 诊断态，并提供
  owner lease 与全局单调 fencing token 的 CAS 基础。`attempt_id` 形如
  `attempt-<run_id>-<index>-<short_uuid>`。
- `ProjectionStore` + `ProjectionCoordinator` 驱动 at-least-once observer，记录
  per-observer checkpoint、`status`、`retry_count`、`lag_events`；checkpoint 不允许倒退，
  相同 position 重放幂等。`ProjectionCoordinator.drain()` 内置 `_drain_lock`
  防止并发 drain 重入，sink + checkpoint 同事务保证 at-least-once。
  `LocalRunHarness` 在 run 终态后调用 `coordinator.drain()` 推进所有 read model；
  无 coordinator 装配时退化为内存 fallback 仅用于 legacy `InMemoryRunEventStore` 测试路径。
- 自带三个 observer：memory（required）、timeline（非 required）、audit（非 required）。
  memory observer 写入用户输入永不丢失，成功终态写 assistant final，Engine `RUN_FAILED`
  与 Host-owned `RUN_FAILED` 写中性 terminal summary，cancelled / suspended 仅保留
  用户输入。
- `dayu.host._durable_harness.build_durable_harness` 装配 durable 路径的
  `LocalRunHarness` + `ProjectionCoordinator` + 默认 observer。

P7 已落地：

- EventLog 是 trace 唯一来源：``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` canonical
  fact 在 RunInputBuilder 完成、Engine attempt 启动前由 `LocalRunHarness`
  同事务追加，内联完整 ``raw_input_messages_json`` /
  ``raw_tool_schemas_json`` 与 ``raw_*_blob_id``。compact 重试路径合成
  trace 后追加；启用开关由 `tool_trace_context_fact_enabled` 控制，关闭
  时行为与 P6 完全一致。
- `RunInputContextFactBuilder`（位于 `dayu.host._run_input_context_fact`）
  把 `RunInput` / 当前 user 事件 / 工具 schemas 派生为强类型
  `RunInputContextSnapshotBuiltData`，包含 message / tool schema 摘要、
  ``content_hash``、``role_sequence``、``current_user_*`` 维度，
  ``raw_*_blob_id`` 跨 replay 稳定（相同输入产出相同 id）。
- `ToolTraceObserver`（位于 `dayu.host._tool_trace_projection`）把 EventLog
  canonical 事实派发为 5 类 trace record：``tool_call``、
  ``iteration_context_snapshot``、``iteration_usage``、``final_response``、
  ``provider_protocol_error``；同 batch 内按 ``(iteration_id, tool_call_id)``
  配对 ``TOOL_CALL_REQUESTED`` + ``TOOL_RESULT_ACCEPTED``，缺对抛
  `ProjectionSchemaError` -> `BLOCKED_FAILED`。``record_role`` /
  ``source_event_position`` 进入 sha256[:32] ``idempotency_key`` 让
  analyzer 去重重放副本。
- `ToolTraceJsonlSink` 落 ``<root>/sessions/<session_id>/tool_calls_*.jsonl``
  并按 ~10MB 滚动；每行 ``flush + fsync``。
  ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` 内联的 raw payload 写入
  ``<root>/raw_payloads/<run_id>_<iteration_id>/<blob_id>.json``，先 tmp +
  ``os.replace`` 原子落地。``PROVIDER_PROTOCOL_ERROR`` 的 ``raw_payload``
  在落盘前由 `_scrub_provider_secret` 替换 ``Authorization`` /
  ``api_key`` / ``cookie`` / ``x-api-key`` 等敏感键为 ``"***"``；缺失
  payload 时 fallback 到 ``{"reason": "omitted_no_payload"}``。其它字段
  （prompt、tool result、scope_token / cursor）按 OLD 热/冷分层保留。
- 装配开关：`DurableHarnessConfig.tool_trace_path` 非空字符串时装配
  `ToolTraceObserver`（非 required projection）并把 fact 开关传给
  `LocalRunHarness`；``None`` / 空字符串等价于未配置 trace，coordinator
  observer 元组与 EventLog 都不会出现 trace fact 与 trace observer。
  P7 不在 SQLite 引入任何 ``host_tool_trace_*`` 表。

不得为旧 Host 接口创建兼容 wrapper、facade 或 re-export。

## 当前公开接口

`dayu.host.__all__` 只导出：

- Run 请求与选项：`StartRunRequest`、`RunInput`、`RunOptions`。
- Run 句柄与事件：`RunHandle`、`RunStream`、`RunEvent`、`RunEventCursor`、`RunEventType`、
  `RunEventKind`、`RunEventSource`、`RunEventData`、`RunState`。
- Host-owned event data：`HostRunFailedData`、`UserInputAcceptedData`、`UserInputScope`。
- ToolRuntime fact data：`ToolResultTruncatedData`、`ToolCursorIssuedData`、`ToolFetchMoreRequestedData`、
  `ToolFetchMoreCompletedData`、`ToolFetchMoreFailedData`、`ToolCursorExpiredData`、`ToolCursorDeniedData`、
  `ToolRuntimeEventData`、`ToolValueSizeSummary`。
- Tool fetch_more 契约：`ToolRuntimeCursor`、`ToolFetchMoreHandleRequest`、`ToolFetchMoreHandle`、
  `ToolFetchMoreHandleResult`、`ToolFetchMoreHandleSucceededResult`、`ToolFetchMoreHandleFailedResult`、
  `ToolFetchMoreRequest`、`ToolFetchMoreResult`、`ToolFetchMoreSucceededResult`、
  `ToolFetchMoreFailedResult`。
- Run 终态结果类型：`RunResult`、`RunSucceededResult`、`RunFailedResult`、`RunCancelledResult`、`RunSuspendedResult`。
- Host context compact 事实类型：`HostContextOverflowObservedData`、`HostContextCompactRequestedData`、
  `HostContextCompactCompletedData`、`HostContextCompactFailedData`、`HostContextAttemptRetryData`、
  `HostContextCompactEventData`、`ContextCompactFailureReason`。
- 最小入口：`start_run`、`stream_run_events`、`get_run_result`、`get_tool_fetch_more_handle`、
  `fetch_more_tool_result`。

`EngineWorker`、`LocalProxy`、`WorkerProxy`、`ToolExecutor`、`InMemoryToolRuntime`、
`ToolRuntimeToolExecutor`、`InMemoryConversationMemoryStore`、`DefaultRunInputBuilder`、
`RunInputBuildTrace` 与 `run_agent_messages` 不属于 Host public API。

## 稳定边界

Host 位于固定分层中的 Service 与 Engine 之间：

```text
UI -> Service -> Host -> Engine
```

Host 的职责边界是通用 Agent 执行托管、会话、运行治理、恢复、上下文构造、工具运行时边界、事件事实与派生视图。Host 不承载财报业务知识，不直接理解财报文档语义。

财报文档存取必须通过 `dayu.fins.storage` 所属仓储边界由业务工具保证，不能进入 Host 或 Engine 的通用运行语义。

## 当前内部边界

当前内部执行路径：

```text
await dayu.host.start_run
  -> LocalRunHarness
  -> RunEventStore.append(USER_INPUT_ACCEPTED)
  -> ConversationMemoryStore.get_snapshot
  -> RunInputBuilder.build
  -> LocalProxy
  -> EngineWorker
  -> dayu.engine.run_agent_messages
  -> EngineEvent
  -> RunEventDraft
  -> RunEventStore.append
  -> RunStream.events / stream_run_events
```

P5 sequential smoke 主路径：

```text
LocalRunHarness.start_run(run_index=1)
  -> Engine Agent tool loop emits huge_echo tool call
  -> ToolExecutor.execute
  -> ToolRuntimeToolExecutor -> InMemoryToolRuntime -> huge_echo executor
  -> truncate / cursor facts
  -> Engine injects truncated tool result with fetch_more hint
  -> model emits framework fetch_more tool call
  -> ToolRuntime routes framework fetch_more and appends fetch_more facts
  -> final terminal
  -> memory projection
LocalRunHarness.start_run(run_index=2 after terminal)
  -> RunInputBuilder sees previous user / final / tool / fetch_more facts
```

context overflow compact retry 路径：

```text
Engine / Runner
  -> context_compaction_requested
  -> recoverable run_failed(context_compaction_required) 或 stream 正常结束
  -> LocalRunHarness
  -> context_overflow_observed
  -> context_compact_requested
  -> context_compact_completed 或 context_compact_failed
  -> context_attempt_retrying
  -> WorkerProxy.stream_engine_events(compacted RunInput)
```

工具调用执行路径：

```text
Engine
  -> ToolExecutor.execute
  -> ToolRuntimeToolExecutor
  -> InMemoryToolRuntime
  -> business ToolExecutor
  -> truncate / cursor facts
  -> RunEventStore.append
```

framework 补读路径：

```text
Model
  -> tool_call fetch_more(cursor, scope_token, limit?)
  -> Engine Agent tool loop
  -> ToolExecutor.execute
  -> ToolRuntimeToolExecutor
  -> InMemoryToolRuntime.execute_tool_call
  -> InMemoryToolRuntime.fetch_more
  -> RunEventStore.append(fetch_more facts for original business tool)
```

Host public 补读路径：

```text
LocalRunHarness / default harness
  -> get_tool_fetch_more_handle
  -> fetch_more_tool_result
  -> InMemoryToolRuntime.fetch_more
  -> RunEventStore.append
```

`EngineWorker` 只负责把 Host `StartRunRequest` 装配为 Engine `AgentRunRequest` 并调用 Engine。它不注册工具、
不发现工具、不直接做权限、不做审计；ToolRuntime adapter 是 Host 内部执行治理边界，不提升为 public API。

默认 public `start_run` 不暴露 ToolExecutor 配置入口。需要 fake ToolExecutor 的 Host 测试使用内部
`LocalRunHarness` 装配，避免把 `ToolExecutor.execute` 提升为 Host public API。

当前 `InMemoryRunEventStore` 是 Host 内部 runtime 临时实现；P6 起新增 SQLite WAL 后端的
`DurableRunEventStore`（位于 `dayu.host._durable_event_store`），同样实现 append-only、
per-run cursor、exclusive replay 与 replay-then-follow 订阅，并对外暴露
`fetch_events_by_position` / `latest_event_position` 以服务 observer。durable 路径通过
`dayu.host._durable_harness.build_durable_harness` 显式装配，会同时返回
`HostStorage`、`DurableRunEventStore`、`ProjectionCoordinator` 与三个默认 observer
（memory required、timeline、audit）。每个 observer 在 `ProjectionStore` 中保存
checkpoint、`status`、`retry_count`、`last_error_code`、`lag_events`；checkpoint 不允许
倒退。`DurableHarnessBundle.startup_reconcile()` 是装配后的显式追平入口：进程崩溃可能
停在 terminal 事件已持久化但 `coordinator.drain()` 尚未执行的瞬间，重启后调用方需要
在自己的 async 上下文内 `await bundle.startup_reconcile()`，本方法委派
`ProjectionCoordinator.startup_reconcile`，串行 drain 至 `CAUGHT_UP`，不引入新 event
loop / 线程，也不与 terminal 后的 `drain()` 重入冲突。`DurableRunEventStore` 写入
RunEventData 时通过封闭 type↔data 映射的序列化注册表
（`dayu.host._run_event_serializer`，`schema_version=1`）做 fail-fast 校验；schema 变化按
全新起库处理，不维护旧库兼容。P8-S1 已提供 internal attempt lease / fencing store 基础；
当前 `LocalRunHarness` 主路径、supervisor、renew loop、recovery scan 与 public lifecycle
governance 仍未接入。

Host 已落地主路径使用日志表达执行边界：`VERBOSE` 覆盖 `start_run` 接纳、background task、attempt、
EngineWorker 调用、terminal append、context overflow / compact / retry、ToolRuntime 调用边界、
RunInputBuilder 构造完成、Conversation Memory 投影与订阅起止；`DEBUG` 只保留有界细节，例如 canonical
EventStore append、ToolRuntime 截断策略 / cursor fingerprint、compact 失败估算；`INFO` 记录 run finished
摘要；`WARNING` 记录可恢复或不覆盖原始结果的异常边界；`ERROR` 记录本次操作失败；`CRITICAL` 记录
Engine stream 无 terminal 等 contract / invariant 破坏。日志不得输出 prompt、preview delta 全量、工具参数、
工具结果、raw cursor 或 `scope_token`。Host 内部发出 `VERBOSE` 日志时只读取
`dayu.runtime.log_levels` 的层中立常量，不导入日志装配模块。

`InMemoryRunEventStore` 在 DEBUG 下不逐条打印 preview delta append，也不打印 subscribe wait / batch 轮询；
terminal append、subscribe start / complete 与 canonical append 边界仍可观察。

当前 `InMemoryConversationMemoryStore` 也是 Host 内部临时实现。它以 `session_id` 隔离 memory，只投影
已 append 的 canonical RunEvent；不同 session 不互相读取 memory。它不提供跨进程恢复、持久 projection、
public memory 编辑或审计 UI。同一 store 实例通过 `asyncio.Lock` 序列化 snapshot 读写，只声明单进程
内存态一致性，不声明多进程正确性。

如果 worker / proxy 异常导致 Host 无法获得 Engine terminal event，或 Engine stream 正常结束但没有产出
terminal event，后台任务会 append 一个 Host-owned canonical `RUN_FAILED` 事件；该事件 `source=HOST`，
`source_engine_event_id=None`。无终态正常结束的错误码为 `engine_stream_ended_without_terminal`。
Engine stream 无 terminal 属于 Engine / Worker 协议违约，Host 会记录 `CRITICAL` 日志。
Host-owned failure 进入 terminal 后同样触发 memory projection，因此失败轮次的 `USER_INPUT_ACCEPTED`
与中性 terminal summary 会进入 session memory。
context overflow compact retry 不会再次追加 `USER_INPUT_ACCEPTED`，也不会把 compacted `RunInput`
投影成新的原始用户记录；只有最终 terminal 后，本 Run 的 canonical 事件整体进入 memory projection。
compact 分支的 trace 缺失与异常会以 Host-owned compact failed terminal 收口，避免订阅方永久等待；
其它翻译、append、terminal result 推导等 Host 内部错误不会伪装成 Host-owned failure；后台 task 会记录
ERROR 日志并取回异常，完整 supervisor / governance 仍不在 P1.5 范围内。
提前停止消费后的 worker stream 关闭失败只记录 WARNING 诊断日志，不替换原始异常，也不写入
Host-owned failure 事件。

## 当前手工验证

当前提供 Host EventLog 手工 smoke 脚本，用于观察 P1.5 run harness 中的 append-before-stream、
cursor、replay 与 Host-owned failure 行为：

```bash
python utils/smoke_host_eventlog.py --case success --log-level DEBUG
python utils/smoke_host_eventlog.py --case worker-failure --log-level DEBUG
```

当前提供 Host P6 durable EventLog 手工 smoke 脚本，用于观察 SQLite 后端 append、
`ProjectionCoordinator` drain、checkpoint 推进与 memory / timeline / audit observer 行为。
脚本默认启用 `VERBOSE` 日志以展示 P6 执行路径；需要更细诊断时可传 `--log-level DEBUG`，
只看摘要时可传 `--log-level INFO`：

```bash
python utils/smoke_host_p6_durable_eventlog.py
python utils/smoke_host_p6_durable_eventlog.py --log-level DEBUG
```

当前提供 Host ToolRuntime smoke 脚本，用于观察 P2 schema-driven truncate、cursor issued、
受控 handle、fetch_more 与 single-use 失效。脚本日志只输出 cursor fingerprint、事件 cursor、chunk size 等
中性摘要：

```bash
python utils/smoke_host_tool_runtime.py --log-level DEBUG
```

当前提供 Host context compaction smoke 脚本，用 fake overflow 稳定展示 P4 行为。该脚本不代表真实 provider
overflow 覆盖，日志只输出事件类型、cursor、attempt 数量、compact 前后估算大小与终态过滤 / 降级状态等中性摘要：

```bash
python utils/smoke_host_context_compaction.py --case fake-overflow --log-level DEBUG
python utils/smoke_host_context_compaction.py --case internal-echo-filter --log-level DEBUG
```

当前提供 Host P5 no-full-governance 多轮 smoke 脚本。`--case real-provider` 与 `--case all`
按 `utils/` 下 provider smoke 的既有范式，在脚本内写死 `mimo-v2.5-pro-plan`
`ProviderCase`，不读取 `dayu/config/llm_models.json` 或 `workspace/config`，也不充当配置
adapter；`MimoThinkingExtension(enabled=True)` 是该 hardcoded ProviderCase 的有意组成部分。缺
`MIMO_PLAN_API_KEY`、endpoint、model 或 tool calling capability 时清晰失败并返回
非零。真实 provider 主路径会向模型暴露 `huge_echo` 与 framework `fetch_more` schema，模型必须先调用
`huge_echo`，再根据截断 tool result 中的 hint 调用 `fetch_more`；脚本不会用 Host public API 代替模型成功补读。
fake provider / scripted WorkerProxy 只用于 integration 与 compact retry 辅助诊断，不能替代
真实 provider smoke 成功。默认不回显 provider thinking / reasoning；需要观察真实 provider 返回的
reasoning 诊断时，显式传 `--thinking`。该开关对齐 OLD `prompt --thinking` 的终端回显语义，
只读取 real-provider 路径中 provider 返回的 reasoning 字段，在消费 Host `RunEvent` 流时即时输出
provider reasoning delta；当前轮没有 delta 时才回退聚合 reasoning。`--thinking` 下的 thinking delta 与
final answer 使用前后空行分隔的观察块，不使用 `SMOKE ...` 单行日志格式；final answer 只显示前 320 个字符；
不读取 content preview、工具结果、RunInput 或 prompt：

```bash
python utils/smoke_host_multiturn_no_governance.py --case all --log-level INFO
python utils/smoke_host_multiturn_no_governance.py --case real-provider --log-level DEBUG
python utils/smoke_host_multiturn_no_governance.py --case real-provider --log-level DEBUG --thinking
python utils/smoke_host_multiturn_no_governance.py --case compact-retry --log-level DEBUG
```

当前也保留 EngineWorker 手工 smoke 脚本：

```bash
python utils/smoke_engine_worker.py --case deepseek-v4-flash
```

该脚本直接调用 Host 内部 `EngineWorker` wrapper，使用真实 provider 配置与 fake `add_numbers`
ToolExecutor 验证 Host `StartRunRequest` 到 Engine 事件流的装配链路。脚本只用于人工验证，
不代表 EngineWorker 是 Host public API。

## 当前状态机

P1.5 只真实产生内存态运行中的句柄，并通过已 append 的 terminal RunEvent 映射结果：

```text
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
```

`STALE / RECOVERING / LOST` 已作为 internal `AttemptState` / store 诊断态落地；完整
`QUEUED / WAITING / CANCELLING` 主路径治理，以及 supervisor、renew loop、recovery scan
和 public lifecycle governance 尚未接入。
