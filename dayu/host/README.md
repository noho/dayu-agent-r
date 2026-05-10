# Host 开发手册

本文档是 `dayu.host` 的包级开发手册。它不是 `docs/host/` 的文档索引，也不记录迁移过程、
Phase 流程、review 过程或 PR 流程。

## 当前状态

`dayu.host` 当前落地最小 Run harness（含内存态与 P6 durable 两条路径）、Host-owned ToolRuntime
截断 / 补读、Host 内部 Conversation Memory / RunInputBuilder、context overflow compact retry、
公共 tool declaration 契约，以及 P8 attempt lease / fencing / recovery / terminal atomic close /
attempt-scoped append / durable memory：

- 包根只暴露 Run 级契约与 fetch_more 协议契约 (`ToolFetchMoreRequest` 等)；
  Run 生命周期与 fetch_more 操作必须经由 `LocalRunHarness` / `build_durable_harness()` 装配后的
  实例方法（`harness.start_run` / `harness.stream_run_events` / `harness.get_run_result`）调用，
  framework `fetch_more` 工具调用经 `ToolRuntimeToolExecutor -> HostToolRuntime.execute_tool_call`。
- `harness.start_run` 是 async 入口，返回 `RunStream`，包含 `RunHandle` 与 `RunEvent` 异步流；被 await 时会立即启动
  内存后台任务。
- Host 内部通过 `LocalProxy -> EngineWorker -> dayu.engine.run_agent_messages` 调用 Engine 函数式入口。
- `EngineEvent` 会先被翻译为 `RunEventDraft`，再由 Host `RunEventStore.append` 生成 cursor-bearing
  `RunEvent`。
- `RunStream.events` 与 `stream_run_events` 都是 store 的订阅视图；事件必须先 append，再被订阅流消费。
- cursor 由 Host store 在单个 run 内分配，`after` 使用 exclusive 语义，不绑定 Engine sequence。
- RunEvent 已区分 `canonical` / `preview`：content delta、reasoning delta、content completed 为 preview；
  终态、工具、usage、provider protocol error、lifecycle 等当前事件为 canonical。
- `get_run_result` 是 harness 的非阻塞快照补查实例方法，只从已 append 的 canonical terminal RunEvent 推导结果。
- `harness.start_run` 会先 append Host-owned canonical `USER_INPUT_ACCEPTED`，再从 EventLog 中的该事件与
  session memory snapshot 构造交给 Engine 的 `RunInput`；该 append 失败时不会启动 Engine。
- `StartRunRequest.input` 在入口边界只接受若干 leading `SystemMessage` 加末尾唯一非空 `UserMessage`；
  assistant / tool 历史、多条 user、空 user 或 user 后追加 system 均会 fail fast，且不会启动 Engine、写
  EventLog 或污染 memory。
- `USER_INPUT_ACCEPTED` 使用封闭 `UserInputScope`，memory projection 从事件 data 推导 provenance scope；
  非法 scope 会在投影时失败。
- 同一 run 的 terminal RunEvent 会封闭当前事件流；store 拒绝 terminal 后继续 append，harness 在首个
  terminal 后关闭 worker stream。
- Host 内部 `HostToolRuntime` 通过 `ToolRuntimeToolExecutor` 适配为 Engine 唯一可见的
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
- `scope_token` 不进入 RunEvent、memory projection 或日志；framework `fetch_more` 通过 LLM-facing tool
  message 中的 `truncation.fetch_more_args` 把 cursor / scope_token 透传给模型，模型按普通 tool call
  回传，由 Host `ToolRuntimeToolExecutor -> HostToolRuntime.execute_tool_call` 在 framework 路径下消费。
- framework `fetch_more` 作为最小 LLM-facing schema 与业务工具 schema 一起传给 Engine / Runner；
  `ToolRuntimeToolExecutor -> HostToolRuntime.execute_tool_call` 会识别该工具名并路由到 Host ToolRuntime
  补读，不调用业务 executor，也不把它提升为完整 ToolRegistry / governance。
- 补读失败结果中的 `denied` 只表示权限 / scope 拒绝；cursor 不存在、cursor 过期和 terminal Run 都不是权限拒绝。
- terminal Run 后 framework `fetch_more` 工具调用返回 typed failure，不追加新 RunEvent。
- Host 内部 `DurableConversationMemoryStore`（P8-S8 起为默认 read model）只从 canonical RunEvent 投影 session memory；preview、
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
- recovery scan 自动装配到生产启动链路（当前仅为内部显式入口，`build_durable_harness` 不自动调用）。
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
  `AttemptState` / store 层扩展 `STALE / LOST` 诊断态，并提供
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

P8 已落地：

- attempt lease / fencing 核心（P8-S1 基础 + P8-S3 接入）：`AttemptSupervisor` 通过
  `DurableHarnessConfig.attempt_lease_config` 装配到 `build_durable_harness`；每个 attempt 在
  `LocalRunHarness.start_run` 时经 `AttemptSupervisor.lease_context()` 获取 owner secret token
  （SHA-256 digest 入库，明文不入库、不进日志、不进 EventLog）与全局单调 fencing token；
  `_renew_loop` 后台心跳在 `AttemptOwnerLossReason.FENCED / STORAGE_ERROR` 时通过
  `wait_owner_lost()` 暴露 typed 信号，`LocalRunHarness` 用 `_next_engine_event_or_lose_owner()`
  在 Engine event 与 owner-lost 之间 race，一旦 owner 失活即停止后续 EventLog append 并走
  owner-aware diagnostic close。
- terminal atomic close（P8-S4）：`AttemptSupervisor.append_terminal_and_close` 在单个
  `BEGIN IMMEDIATE` 事务内串联 `verify_owner` → EventLog terminal RunEvent append →
  `host_attempts.terminal_event_position` 写入 → attempt 终态 close；任何 owner / fencing
  token / lease 过期校验失败抛 `AttemptFencingError` 并整事务回滚，EventLog 不残留 stale
  terminal，`host_attempts` 不被旧 owner 覆盖未来状态。
- attempt-scoped append（P8-S5）：`AttemptScopedRunEventAppender` 收敛所有当前 attempt
  owner 的 canonical fact 写入（Engine 翻译事件、context overflow / compact、trace fact、
  ToolRuntime fact）；`draft.run_id` 与 `owner_context.run_id` 不一致直接抛
  `AttemptFencingError(reason=OWNER_MISMATCH)`。`ToolRuntimeOwnerScope`（ContextVar）
  在 `LocalRunHarness._run_to_store` 每个 attempt 生命周期内把 scoped appender 注入
  `HostToolRuntime`，使框架 `fetch_more` 也按 originating attempt 落库。
- stale / orphan recovery（P8-S6）：`AttemptSupervisor.recover_stale_attempts` 内部显式
  入口扫描 `state IN ('running','created') AND lease_expires_at <= now`，逐候选用独立
  `BEGIN IMMEDIATE` 事务 CAS 决策——旧 attempt 一律 `MARK_LOST` 诊断收口，不再创建
  recovery attempt（P8 D2）；run terminal 推 `MARK_LOST`；`CREATED` 孤儿推 `MARK_LOST`；
  fencing token 被改写时命中 `NOOP_TERMINAL` 安全分支。该入口当前未自动 wire 进
  `build_durable_harness` 或 Session 生命周期。
- 多进程 stress 验证（P8-S7）：`tests/host/test_phase8_multiprocess_stress.py` 通过
  spawn-only + file SQLite (WAL + `BEGIN IMMEDIATE`) 覆盖并发 append、terminal close
  race、跨进程 stale recovery、observer drain 四场景。不引入 multiprocessing launcher
  生产代码。
- durable conversation memory（P8-S8）：`DurableConversationMemoryStore` 成为
  `build_durable_harness` 默认 memory read model，与 EventLog checkpoint 同事务原子推进；
  `startup_reconcile` 后追加 `repair_missing_session_snapshots()` 在 checkpoint 已 CAUGHT_UP
  但 snapshot row 因运维误操作丢失时从 EventLog 重建。生产代码不再保留
  `InMemoryConversationMemoryStore`。
- attempt state 诊断态扩展：`AttemptState` / store 层新增 `STALE`、`LOST`
  两个诊断态（P8-S1），配合 fencing token CAS 基础。

不得为旧 Host 接口创建兼容 wrapper、facade 或 re-export。

## 当前公开接口

`dayu.host.__all__` 只导出：

- Run 请求与选项：`StartRunRequest`、`RunInput`、`RunOptions`。
- Run 句柄与事件：`RunHandle`、`RunStream`、`RunEvent`、`RunEventCursor`、`RunEventType`、
  `RunEventKind`、`RunEventSource`、`RunEventData`、`RunState`。
- Host-owned event data：`HostRunFailedData`、`UserInputAcceptedData`、`UserInputScope`。
- Run input context fact data：`RunInputContextSnapshotBuiltData`、`RunInputContextMeta`、
  `RunInputMessageSummary`、`RunInputToolSchemaSummary`。
- ToolRuntime fact data：`ToolResultTruncatedData`、`ToolCursorIssuedData`、`ToolFetchMoreRequestedData`、
  `ToolFetchMoreCompletedData`、`ToolFetchMoreFailedData`、`ToolCursorExpiredData`、`ToolCursorDeniedData`、
  `ToolRuntimeEventData`、`ToolValueSizeSummary`。
- Tool fetch_more 契约：`ToolRuntimeCursor`、`ToolFetchMoreRequest`、`ToolFetchMoreResult`、
  `ToolFetchMoreSucceededResult`、`ToolFetchMoreFailedResult`。
- Run 终态结果类型：`RunResult`、`RunSucceededResult`、`RunFailedResult`、`RunCancelledResult`、`RunSuspendedResult`。
- Host context compact 事实类型：`HostContextOverflowObservedData`、`HostContextCompactRequestedData`、
  `HostContextCompactCompletedData`、`HostContextCompactFailedData`、`HostContextAttemptRetryData`、
  `HostContextCompactEventData`、`ContextCompactFailureReason`。

`LocalRunHarness` / `build_durable_harness()` 仍位于 Host internal/submodule 路径；当前使用方经这些
装配入口取得 harness 后调用实例方法 `start_run` / `stream_run_events` / `get_run_result`。
framework `fetch_more` 通过普通 tool call 路径走
`ToolRuntimeToolExecutor -> HostToolRuntime.execute_tool_call`，不再有独立 public helper。

`EngineWorker`、`LocalProxy`、`WorkerProxy`、`ToolExecutor`、`HostToolRuntime`、
`ToolRuntimeToolExecutor`、`DurableConversationMemoryStore`、`DefaultRunInputBuilder`、
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
  -> ToolRuntimeToolExecutor -> HostToolRuntime -> huge_echo executor
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
  -> HostToolRuntime
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
  -> HostToolRuntime.execute_tool_call
  -> HostToolRuntime.fetch_more
  -> RunEventStore.append(fetch_more facts for original business tool)
```

Host framework `fetch_more` 路径（与业务工具走同一 Engine 工具调用路径）：

```text
Engine ToolExecutor.execute(ToolExecutionRequest{name=FRAMEWORK_FETCH_MORE_TOOL_NAME})
  -> ToolRuntimeToolExecutor
  -> HostToolRuntime.execute_tool_call
  -> HostToolRuntime._fetch_more (内部子例程)
  -> RunEventStore.append
```

`EngineWorker` 只负责把 Host `StartRunRequest` 装配为 Engine `AgentRunRequest` 并调用 Engine。它不注册工具、
不发现工具、不直接做权限、不做审计；ToolRuntime adapter 是 Host 内部执行治理边界，不提升为 public API。

默认 `harness.start_run` 不暴露 ToolExecutor 配置入口。需要 fake ToolExecutor 的 Host 测试使用内部
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
P8-S3 已经把 `AttemptSupervisor` 接入 `DurableHarnessConfig.attempt_lease_config` 装配入口，
在 `LocalRunHarness` 主路径上完成 owner lease acquire、renew heartbeat 与 owner-aware
diagnostic close：renew 命中 `FENCED / TERMINAL / BUSY` 或抛出 storage 异常时
supervisor 暴露 typed `AttemptOwnerLossReason`（`FENCED` / `STORAGE_ERROR`），
`LocalRunHarness` 在等待 Engine event 时与该信号 race，一旦 owner 失活立即停止
后续 EventLog append、调用 `AttemptSupervisor.close_attempt_with_diagnostic_state`
做 owner_token + fencing_token CAS 收口，不再退回到 legacy 非 owner-aware update。
P8-S4 已把 terminal RunEvent append、owner fencing 校验、attempt 终态收口与
`host_attempts.terminal_event_position` 写入收敛到同一 `BEGIN IMMEDIATE` 事务内：
`AttemptSupervisor.append_terminal_and_close` 串联 `verify_owner` →
`DurableRunEventStore.append_with_position_in_transaction` →
`AttemptLeaseStore.close_terminal`，正常 owner 路径在原子事务内写出 terminal RunEvent
全局 position 与 attempt SUCCEEDED / FAILED / CANCELLED / SUSPENDED 终态字段，并复用
EventLog 既有的 Run 终态状态推进与 `RunResult` 快照同事务语义；任何步骤的 owner /
fencing token / lease 过期校验失败都会抛 typed `AttemptFencingError` 并整事务回滚，
EventLog 不残留 stale terminal RunEvent，`host_attempts` 也不会被旧 owner 覆盖未来
状态。`LocalRunHarness._run_to_store` 在 supervisor 注入且 active attempt 持有
owner_context + lease_exit_stack 时通过 `_can_atomic_terminal_close` 路由到原子路径，
完成后立即 `aclose` lease_exit_stack 退出 supervisor lease_context；非 supervisor 装配
路径退化为既有的 `event_store.append` + `_finish_attempt_if_durable` 两步。
public `StartRunRequest` / `start_run` 不暴露 lease TTL，owner secret token 明文不入库、
不进入日志、不进入 EventLog payload。P8-S5 进一步把 attempt-scoped append 收敛到
`AttemptScopedRunEventAppender`：所有由当前 attempt owner 写入的 canonical fact
（Engine-sourced 翻译事件、`CONTEXT_OVERFLOW_OBSERVED` / `CONTEXT_COMPACT_*` /
`CONTEXT_ATTEMPT_RETRYING`、`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`、ToolRuntime
`TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_*` / `TOOL_FETCH_MORE_*`）都通过该 appender
在同一 `BEGIN IMMEDIATE` 事务内执行 `verify_owner` + EventLog append；
`draft.run_id` 与 `owner_context.run_id` 不一致直接抛 typed
`AttemptFencingError(reason=OWNER_MISMATCH)`，stale owner / fencing token 不一致 / lease
过期同样抛 `AttemptFencingError` 整事务回滚，EventLog 不残留 stale fact，也不写诊断
RunEvent。`AttemptSupervisor.scoped_appender(owner_context)` 是构造该 appender 的唯一
公开入口；`LocalRunHarness._run_to_store` 在每个 attempt 生命周期内通过
`ToolRuntimeOwnerScope`（基于 `contextvars.ContextVar`）把 scoped appender 注入到
`HostToolRuntime`，使框架级 `fetch_more` 也按 originating attempt 的 owner
落库，避免跨 attempt 写错 run。`ToolExecutionContext` 不变，不向 ToolExecutor 暴露
任何 owner secret。P8 D2 后 stale / orphan recovery 入口
`AttemptSupervisor.recover_stale_attempts(*, run_id=None)` 仅做诊断收口：候选扫描使用短读事务挑选
`state IN ('running','created') AND (lease_expires_at <= now OR lease_expires_at IS NULL)` 的 attempt，
随后逐候选用独立 `BEGIN IMMEDIATE` 事务通过 `AttemptLeaseStore` CAS 决策落地：
旧 RUNNING lease 过期 / `CREATED` 孤儿一律走 `MARK_LOST` (reason 分别为
`recovery_lease_expired` / `recovery_created_orphan`); run 已 terminal 走
`MARK_LOST` (reason `recovery_run_terminal`); fencing token 在 scan 与短事务之间被改写时
CAS rowcount=0 命中 `NOOP_TERMINAL` 安全分支不残留改写。Recovery 不再创建新的 recovery
attempt; 重试 / resume 必须由 Service 层显式发起新的 `StartRunRequest`。recovery scan 不修改
`host_projection_checkpoints`，不写诊断 RunEvent，所有决策以 typed `AttemptRecoveryDecision`
返回。该入口当前只是内部入口，未自动 wire 进 `build_durable_harness` 或 Session 生命周期，
自动装配时机仍未在生产链路落地。

P8-S7 引入了真实多进程 + observer drain 验证测试套（`tests/host/test_phase8_multiprocess_stress.py`
与 `tests/host/_multiprocess_platform.py`），在文件落库 SQLite (WAL + ``BEGIN IMMEDIATE``) 上
确认: 多进程并发 `DurableRunEventStore.append` 严格保留 per-run sequence + global
`event_position` 单调唯一；多进程 terminal close 仅 owner secret 命中库内 hash 的胜出，另一方
落 `AttemptFencingError(OWNER_MISMATCH)` 整事务回滚；跨进程 stale recovery 仍透传 typed
`AttemptRecoveryDecision(MARK_LOST, reason=recovery_lease_expired)`、旧 owner late append 仍 fenced；
`build_durable_harness` + `coordinator.startup_reconcile` 在进程 A 落 terminal 但未 drain 后由
进程 B 把 memory / timeline / audit checkpoint 追到 EventLog tail 且第二次 reconcile 幂等。
该测试套 **不** 引入 multiprocessing launcher / process supervisor 生产代码，也不自动接入
`build_durable_harness`；recovery scan 自动装配仍未落地。P8-S8 起 `build_durable_harness` 默认装配
`DurableConversationMemoryStore`，memory 与 checkpoint 在同一 SQLite 事务原子推进，且
`startup_reconcile` 在 checkpoint 已追平但 memory snapshot 丢失时也会重投全部 EventLog 把 memory
重建到 tail。

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

P8-S8 起默认装配的 `DurableConversationMemoryStore` 把 session memory snapshot 写入与 EventLog
checkpoint 共用的 SQLite 事务，因此 ProjectionCoordinator 提交 batch 时 memory read model、timeline、
audit、checkpoint 同生同灭；任何一方失败则整体回滚。它以 `session_id` 隔离 memory，只投影
已 append 的 canonical RunEvent；不同 session 不互相读取 memory。memory observer 遇到 terminal
事件时会在同一 observer transaction 内按 `session_id` + `run_id` 从 durable EventLog 重读该 run
的完整 canonical facts，再写 snapshot 并推进 checkpoint；进程内 pending 只服务单进程短生命周期，
不承担跨 checkpoint / restart 的事实保存职责。`apply_patch`（reset / SESSION clear
/ claim correction）也走同事务路径，跨进程恢复由 `startup_reconcile` 在启动时把 EventLog tail 投到
read model；非 SESSION scope clear 视为契约违约抛 `ValueError`。同一 store 实例通过 `asyncio.Lock`
序列化 snapshot 读写以避免单进程内并发竞态，跨进程一致性靠 SQLite WAL + checkpoint 提交顺序。
non-durable 顶层 `start_run` 便利入口仍接受调用方显式注入的 `ConversationMemoryStore`（例如
tests-only `FakeInMemoryConversationMemoryStore`），但生产路径下不再有内存态 store 默认装配。

`DurableHarnessBundle.startup_reconcile()` 在 `ProjectionCoordinator.startup_reconcile()`
之后会再调用 `DurableConversationMemoryStore.repair_missing_session_snapshots()`：
当 projection checkpoint 已 `CAUGHT_UP`、EventLog 无新事件、但
`host_conversation_memory_snapshots` 因运维误操作 / read model 损坏导致部分 session row
丢失时，普通 drain 不会再驱动 observer 重投，repair 路径按 session 扫描 EventLog 中的
canonical 事件、对“snapshot row 缺失且 EventLog 已含 terminal 事件”的 session 重建快照。
`MemoryResetPatch` 与 `ScopeClearPatch(SESSION)` 走 UPSERT 写入空快照行，行依然存在，因此
不会被 repair 误判成“缺失”而被旧 EventLog 内容覆盖。EventLog 仍是事实真源，memory snapshot
只是 read model。

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

当前提供 Host P8 attempt lease / fencing / recovery 手工 smoke 脚本，用 file SQLite +
fake clock + deterministic fake worker 覆盖 7 个场景：owner acquire + renew、busy、
supervisor recovery scan、late write fenced、terminal close、observer reconcile 与
durable memory recovery（checkpoint 已 CAUGHT_UP 且 snapshot row 缺失时由
`startup_reconcile` 走 repair 路径从 EventLog 重建 session memory）。owner token 明文不出现
在输出中，summary 输出 ≤20 行 `key=value` 格式：

```bash
python utils/smoke_host_p8_attempt_lease.py
python utils/smoke_host_p8_attempt_lease.py --log-level DEBUG
```

## 当前状态机

P1.5 只真实产生内存态运行中的句柄，并通过已 append 的 terminal RunEvent 映射结果：

```text
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
```

`STALE / LOST` 已作为 internal `AttemptState` / store 诊断态落地（P8-S1）；
`AttemptSupervisor` 的 lease acquire / renew heartbeat / owner-aware diagnostic close /
recovery scan / terminal atomic close / attempt-scoped append 已落地（P8-S3 至 P8-S6）。
完整 `QUEUED / WAITING / CANCELLING` 主路径治理、recovery scan 自动装配到生产启动链路、
以及 public lifecycle governance 尚未接入。
