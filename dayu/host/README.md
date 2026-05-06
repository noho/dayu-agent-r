# Host 开发手册

本文档是 `dayu.host` 的包级开发手册。它不是 `docs/host/` 的文档索引，也不记录迁移过程、
Phase 流程、review 过程或 PR 流程。

## 当前状态

`dayu.host` 当前落地 P1 最小 Run harness：

- 包根只暴露 Run 级最小契约与 `start_run(request)`。
- `start_run` 返回 `RunStream`，包含 `RunHandle` 与 `RunEvent` 异步流；调用时会立即启动
  P1 内存后台任务，事件流只负责消费后台任务写入的内存队列。
- Host 内部通过 `LocalProxy -> EngineWorker -> dayu.engine.run_agent_messages` 调用 Engine 函数式入口。
- `EngineEvent` 会被薄翻译为 `RunEvent`；P1 `RunEvent.data` 直接携带 Engine event data 联合。
- P1 cursor 只映射 Engine sequence，不具备持久补读语义。

当前未落地：

- `client_request_id` 创建幂等。
- Session governance 与同 Session active Run 仲裁。
- EventLog / RunEventStore append-before-stream 事实层。
- 持久化 schema、workspace migration、启动恢复、多进程 lease / fencing。
- Conversation Memory、ContextBuilder、timeline projection。
- ToolRuntime truncate / fetch_more、cursor、scope token、TTL。
- 完整取消治理、RemoteProxy、RemoteStub、Reply Outbox。

不得为旧 Host 接口创建兼容 wrapper、facade 或 re-export。

## 当前公开接口

`dayu.host.__all__` 只导出：

- Run 请求与选项：`StartRunRequest`、`RunInput`、`RunOptions`。
- Run 句柄与事件：`RunHandle`、`RunStream`、`RunEvent`、`RunEventCursor`、`RunEventType`、`RunState`。
- Run 终态结果类型：`RunResult`、`RunSucceededResult`、`RunFailedResult`、`RunCancelledResult`、`RunSuspendedResult`。
- 最小入口：`start_run`。

`EngineWorker`、`LocalProxy`、`WorkerProxy`、`ToolExecutor` 与 `run_agent_messages` 不属于 Host public API。

## 稳定边界

Host 位于固定分层中的 Service 与 Engine 之间：

```text
UI -> Service -> Host -> Engine
```

Host 的职责边界是通用 Agent 执行托管、会话、运行治理、恢复、上下文构造、工具运行时边界、事件事实与派生视图。Host 不承载财报业务知识，不直接理解财报文档语义。

财报文档存取必须通过 `dayu.fins.storage` 所属仓储边界由业务工具保证，不能进入 Host 或 Engine 的通用运行语义。

## 当前内部边界

P1 内部执行路径：

```text
dayu.host.start_run
  -> LocalRunHarness
  -> LocalProxy
  -> EngineWorker
  -> dayu.engine.run_agent_messages
```

`EngineWorker` 只负责把 Host `StartRunRequest` 装配为 Engine `AgentRunRequest` 并调用 Engine。
它不注册工具、不发现工具、不做权限、不做审计、不做 truncation。

默认 public `start_run` 不暴露 ToolExecutor 配置入口。需要 fake ToolExecutor 的 P1 测试使用内部
`LocalRunHarness` 装配，避免把 `ToolExecutor.execute` 提升为 Host public API。

P1 使用内存队列连接后台执行任务与 `RunStream.events`。该队列不是 EventLog，不支持断线补读、
持久 cursor 或多进程恢复。

## 当前手工验证

P1 提供 EngineWorker 手工 smoke 脚本：

```bash
python -m utils.smoke_engine_worker --case deepseek-v4-flash
```

该脚本直接调用 Host 内部 `EngineWorker` wrapper，使用真实 provider 配置与 fake `add_numbers`
ToolExecutor 验证 Host `StartRunRequest` 到 Engine 事件流的装配链路。脚本只用于人工验证，
不代表 EngineWorker 是 Host public API。

## 当前状态机

P1 只真实产生内存态运行中的句柄，并通过 Engine 终态事件映射结果：

```text
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
```

完整 `CREATED / QUEUED / WAITING / RECOVERING / CANCELLING / LOST` 治理状态尚未落地。
