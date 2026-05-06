# Host 开发手册

本文档是 `dayu.host` 的包级开发手册。它不是 `docs/host/` 的文档索引，也不记录迁移过程、
Phase 流程、review 过程或 PR 流程。

## 当前状态

`dayu.host` 当前落地 P1.5 最小 Run harness 与内存态 RunEventStore：

- 包根只暴露 Run 级最小契约与 `await start_run(request)`、`stream_run_events(run_id, after=cursor)`、
  `await get_run_result(run_id)`。
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
- 同一 run 的 terminal RunEvent 会封闭当前事件流；store 拒绝 terminal 后继续 append，harness 在首个
  terminal 后关闭 worker stream。

当前未落地：

- `client_request_id` 创建幂等。
- Session governance 与同 Session active Run 仲裁。
- 持久化 schema、workspace migration、启动恢复、多进程 lease / fencing。
- Conversation Memory、ContextBuilder、timeline projection。
- ToolRuntime truncate / fetch_more、cursor、scope token、TTL。
- 完整取消治理、RemoteProxy、RemoteStub、Reply Outbox。

不得为旧 Host 接口创建兼容 wrapper、facade 或 re-export。

## 当前公开接口

`dayu.host.__all__` 只导出：

- Run 请求与选项：`StartRunRequest`、`RunInput`、`RunOptions`。
- Run 句柄与事件：`RunHandle`、`RunStream`、`RunEvent`、`RunEventCursor`、`RunEventType`、
  `RunEventKind`、`RunEventSource`、`RunEventData`、`RunState`。
- Host-owned failure data：`HostRunFailedData`。
- Run 终态结果类型：`RunResult`、`RunSucceededResult`、`RunFailedResult`、`RunCancelledResult`、`RunSuspendedResult`。
- 最小入口：`start_run`、`stream_run_events`、`get_run_result`。

`EngineWorker`、`LocalProxy`、`WorkerProxy`、`ToolExecutor` 与 `run_agent_messages` 不属于 Host public API。

## 稳定边界

Host 位于固定分层中的 Service 与 Engine 之间：

```text
UI -> Service -> Host -> Engine
```

Host 的职责边界是通用 Agent 执行托管、会话、运行治理、恢复、上下文构造、工具运行时边界、事件事实与派生视图。Host 不承载财报业务知识，不直接理解财报文档语义。

财报文档存取必须通过 `dayu.fins.storage` 所属仓储边界由业务工具保证，不能进入 Host 或 Engine 的通用运行语义。

## 当前内部边界

P1.5 内部执行路径：

```text
await dayu.host.start_run
  -> LocalRunHarness
  -> LocalProxy
  -> EngineWorker
  -> dayu.engine.run_agent_messages
  -> EngineEvent
  -> RunEventDraft
  -> RunEventStore.append
  -> RunStream.events / stream_run_events
```

`EngineWorker` 只负责把 Host `StartRunRequest` 装配为 Engine `AgentRunRequest` 并调用 Engine。
它不注册工具、不发现工具、不做权限、不做审计、不做 truncation。

默认 public `start_run` 不暴露 ToolExecutor 配置入口。需要 fake ToolExecutor 的 Host 测试使用内部
`LocalRunHarness` 装配，避免把 `ToolExecutor.execute` 提升为 Host public API。

当前 `InMemoryRunEventStore` 是 Host 内部临时实现，提供 append-only、per-run cursor、
exclusive replay 和 replay-then-follow 订阅。它是单进程内存实现，不提供持久化 schema、多进程恢复
或 observer checkpoint。

如果 worker / proxy 异常导致 Host 无法获得 Engine terminal event，后台任务会 append 一个
Host-owned canonical `RUN_FAILED` 事件；该事件 `source=HOST`，`source_engine_event_id=None`。
翻译、append、terminal result 推导等 Host 内部错误不会伪装成 Host-owned failure；后台 task 会记录
ERROR 日志并取回异常，完整 supervisor / governance 仍不在 P1.5 范围内。

## 当前手工验证

当前提供 Host EventLog 手工 smoke 脚本，用于观察 P1.5 run harness 中的 append-before-stream、
cursor、replay 与 Host-owned failure 行为：

```bash
python utils/smoke_host_eventlog.py --case success --log-level DEBUG
python utils/smoke_host_eventlog.py --case worker-failure --log-level DEBUG
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
