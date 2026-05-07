# Host 开发手册

本文档是 `dayu.host` 的包级开发手册。它不是 `docs/host/` 的文档索引，也不记录迁移过程、
Phase 流程、review 过程或 PR 流程。

## 当前状态

`dayu.host` 当前落地 P4 最小 Run harness、内存态 RunEventStore、Host-owned ToolRuntime 截断 / 补读，
Host 内部 Conversation Memory / RunInputBuilder，以及 context overflow compact retry：

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
- ToolRuntime 只按工具显式 `ToolTruncateSpec` 截断；无 spec、未启用、未知策略或非法 limit 不截断。
- `binary_bytes` 截断与补读在 Host public `JsonValue` 结果中返回 base64 ASCII 字符串；`unit="bytes"` 与
  `value_summary` 表示原始字节大小，不使用 OLD LLM projection 的 `content_base64` 包装结构。
- 截断与补读事实写入 canonical RunEvent：`tool_result_truncated`、`tool_cursor_issued`、
  `tool_fetch_more_requested`、`tool_fetch_more_completed`、`tool_fetch_more_failed`、
  `tool_cursor_expired`、`tool_cursor_denied`。
- `scope_token` 不进入 RunEvent、Engine projection 或日志；调用方只能通过受控
  `get_tool_fetch_more_handle(...)` 按 session / run / 原始 tool_call / cursor fingerprint 换取短期 handle。
- 补读失败结果中的 `denied` 只表示权限 / scope 拒绝；cursor 不存在、cursor 过期和 terminal Run 都不是权限拒绝。
- terminal Run 后 `fetch_more_tool_result(...)` 返回 typed failure，不追加新 RunEvent。
- Host 内部 `InMemoryConversationMemoryStore` 只从 canonical RunEvent 投影 session memory；preview、
  reasoning delta、content delta 与 content completed 不进入 memory pool 或 RunInputBuilder replay。
- 当前 memory 结构预留 `ConversationPinnedState`、`TaskFrame`、`MemoryClaim`、`ClaimStatus`、
  `EvidenceAnchor`、`AssumptionRegister`、`UserPreferenceProfileRef`，但 Host 不解释财报业务语义。
- `ConversationPinnedState` 包含 `current_goal`、`confirmed_subjects`、`user_constraints`、
  `open_questions` 四槽，并由 `DefaultRunInputBuilder` 全量注入；该 stable block 不参与历史 pool 预算竞争。
- verified claims 与 assumptions 属于 stable ledger，同样全量注入且不参与历史 pool 预算竞争。
- assistant final answer 只作为 raw turn / assistant conclusion 参与连续性，不会自动升级为 verified claim。
- Host-owned worker / proxy failure 终态会以中性 terminal summary 进入 raw turn；该摘要不被当作
  assistant final answer。
- `DefaultRunInputBuilder` 注入顺序为 pinned state、stable frame、verified claims、assumptions、
  evidence anchors / tool facts、recent raw turns、older pool、episode summary 插入位、current user；
  older pool 预算按新到旧消费，但渲染为模型可读的时间顺序。
- LLM-facing evidence anchor 与 tool fact 文本包含来源 event cursor，便于后续追溯到 canonical EventLog。
- `RunInputBuildTrace` 是 Host internal-only 诊断对象，记录 included / excluded item、裁剪原因、来源
  cursor 与估算大小；`LocalRunHarness` 仅保留最近一小段 trace 缓存，避免调试数据无界增长。trace 不进入
  `RunInput`，不进入 memory pool，也不作为下一轮事实真源。
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
  启动新的 internal Engine attempt。
- 若 Engine 在 `context_compaction_requested` 后意外产出非 compaction-required 终态，Host 会先追加
  Host-owned `context_compact_failed(reason=internal_error)` 事实闭合 compact 序列，再保留 Engine 原终态收口。
- P4 当前默认 deterministic compact：保留当前 `USER_INPUT_ACCEPTED`、pinned state、stable frame、
  evidence anchors、source cursor 与 tool facts；compact 前会把本 Run 已 append 的 canonical tool facts
  临时合并进 compact 输入，避免同一 Run overflow 前刚获得的工具证据断链。compact 会丢弃旧 raw turns，
  并在 compact memory system block 前部标注 internal-only / not-output-template 约束。
- compact 成功必须满足 compact 后 RunInput 的 estimated token 与 char size 都严格变短，且必保事实保真；
  no-op、变长、保真失败、trace 缓存缺失、compact 分支异常或超过 compact retry 上限都会追加
  `context_compact_failed`，再由 Host-owned `RUN_FAILED` 收口。
- Engine final answer 若明显回显内部段落标题（如 `## Host Memory`、`## Tool Facts`）或字段形式的
  `tool_fact_id=`、`cursor_fingerprint=`、`source_event_cursor=`、`scope_token=`、raw EventLog metadata，
  Host 会把终态内容过滤为安全占位文本，并将结果标记为 `filtered=True`、`degraded=True`。

当前未落地：

- `client_request_id` 创建幂等。
- Session governance 与同 Session active Run 仲裁。
- 持久化 schema、workspace migration、启动恢复、多进程 lease / fencing。
- timeline projection。
- 完整 ToolRegistry、工具发现、display info、middleware、业务工具迁移。
- LLM-facing `fetch_more` schema、`fetch_more_args` projection、远程 / 多进程补读。
- public memory edit / reset / forget API、持久 memory projection、跨 session / project / user memory。
- episode summary 生成与 LLM compaction scene。
- 完整取消治理、RemoteProxy、RemoteStub、Reply Outbox。

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

context overflow compact retry 路径：

```text
Engine / Runner
  -> context_compaction_requested
  -> recoverable run_failed(context_compaction_required)
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

补读路径：

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

当前 `InMemoryRunEventStore` 是 Host 内部临时实现，提供 append-only、per-run cursor、
exclusive replay 和 replay-then-follow 订阅。它是单进程内存实现，不提供持久化 schema、多进程恢复
或 observer checkpoint。

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
投影成新的 raw user turn；只有最终 terminal 后，本 Run 的 canonical 事件整体进入 memory projection。
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

完整 `CREATED / QUEUED / WAITING / RECOVERING / CANCELLING / LOST` 治理状态尚未落地。
