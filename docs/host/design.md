# Host 设计决策

本文档记录 Host 侧已经确认的架构决策，作为后续 Host / EngineWorker / ToolExecutor 设计与 review 的依据。本文只写当前已经确认的设计边界，不描述尚未确认的实现细节。

## 1. 总体分层

Dayu 的总体分层仍然是：

```text
UI -> Service -> Host -> Engine
```

`EngineWorker` 不新增为 `UI / Service / Host / Engine` 之间的新业务层。`EngineWorker` 是 Host 的一个执行能力，由 Host 选择本地或远程形态来承载 Engine 运行。

## 2. EngineWorker 定位

`EngineWorker` 是 Host 的 capability。

Host 仍然是 run/session 生命周期、取消、治理、工具策略和执行环境选择的真源。EngineWorker 代表 Host 持有一次运行所需的执行环境，并在该环境中启动 Engine。

EngineWorker 可以有两类形态：

```text
Host
  -> LocalProxy
      -> EngineWorker
          -> Engine
          -> local ToolExecutor
```

```text
Host
  -> RemoteProxy
      -> RemoteStub
          -> EngineWorker
              -> Engine
              -> remote ToolExecutor
```

Local Agent 表示 LocalProxy 通过本地 EngineWorker 让 Engine 与 tools 在本地 worker 侧执行。Remote Agent 表示 RemoteProxy 通过 RemoteStub 连接远端 EngineWorker，让 Engine 与 tools 都在远程 worker 侧执行。

## 3. ToolExecutor 归属

Host owns governance truth。

EngineWorker holds execution environment on behalf of Host。

ToolExecutor 由 EngineWorker 替 Host 在执行环境中代持，并提供给 Engine：

- 本地 EngineWorker 替 Host 代持本地 ToolExecutor。
- RemoteStub 侧的 EngineWorker 替 Host 代持远程 ToolExecutor。
- Engine 只消费 `ToolExecutor` protocol。
- Engine 不知道 ToolExecutor 是本地实现还是远程 worker 内实现。
- Engine 不注册工具、不发现工具、不持有 ToolRegistry。

因此，Phase 3 的正确边界不是“Engine 直接接 Host ToolExecutor”，而是：

```text
Host 选择 / 控制 EngineWorker
EngineWorker 替 Host 代持并提供 ToolExecutor
Engine 调用 ToolExecutor protocol
```

## 4. Remote Agent 语义

Remote Agent 的语义是：

```text
Engine + tools execute remotely
```

Remote Agent 不是“远程 Engine 回调 Host 进程执行工具”。远程模式下，工具执行发生在远程 worker 侧；Host 通过 EngineWorker capability 控制远程执行环境、下发治理输入，并接收事件与结果。

这避免了 Engine 直接理解网络、RPC、ack、重连、远程取消等传输细节。远程能力属于 Host 的 EngineWorker capability，而不是 Engine 核心。

## 5. Engine 边界

Engine 的边界保持不变：

- Engine 只依赖强类型 run request、RunnerSpec、ToolExecutor protocol、CancellationToken 等契约。
- Engine 不依赖 Host / Service / UI 具体实现。
- Engine 不知道 LocalProxy / RemoteProxy / RemoteStub / EngineWorker 的部署形态。
- Engine 不关心 ToolExecutor 的真实部署位置。
- EngineEvent 仍是 Engine 对外观测事实；网络传输协议不进入 Engine 核心。

## 6. Phase 3 影响

Phase 3 应落地普通 tool calling 闭环，但必须按 EngineWorker 口径设计：

- Agent 从 Runner tool call 构造 `ToolExecutionRequest`。
- Agent 调用 EngineWorker 替 Host 代持并提供的 `ToolExecutor.execute(request)`。
- completed / failed outcome 回到 Agent。
- Agent 将工具结果注入下一轮 Runner。
- `tool_call_requested` 只能作为观测事件，不能触发第二套执行路径。

Phase 3 不实现：

- Host ToolRegistry。
- 工具权限、审计、路径白名单。
- 远程 RPC 协议。
- RemoteProxy / RemoteStub。
- awaiting / run_suspended。

这些能力分别属于后续 Host / Worker / Phase 4+ 设计。

## 7. Context Compaction Early Stop 后续职责

`context_compaction_requested` 是后续 Host 上下文治理可能需要的 Engine 协作事件草案，不是当前已实现能力，也不是本轮 Engine 迁移范围。

后续如果 Host 实施 context overflow / compaction 治理，可按以下职责边界设计：

- Engine 只暴露单 run 上下文压力的中性事实，例如当前 run、iteration、估算压力、触发原因和已观测事件。
- Host 基于 conversation_memory、transcript、tool facts 和 session 状态压缩或重构上下文。
- Host 以新的 `AgentRunRequest` 重新发起 run，并负责幂等、观测、审计和失败治理。

该能力不是 Engine 内 compact / retry；不是 `run_suspended` / resume；也不是 issue #4 的等待型 suspend。本文只确认未来职责归属和后续实现边界，不表示 Host 当前已经实现该能力，也不要求当前 Engine 迁移实现 `context_compaction_requested`、`context_compaction_required`、`max_context_tokens` 或 trigger ratio。

## 8. EngineWorker 最小接口

EngineWorker 第一版采用简单接口。参数签名后续可随 Host / Worker 真实实现调整，但第一版语义先固定为：

```python
class EngineWorker(Protocol):
    def run_agent_messages(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]: ...

    async def cancel(self, run_id: str) -> None: ...

    async def close(self) -> None: ...
```

接口含义：

- `run_agent_messages`：启动一次 Engine run，并返回 Engine 产出的业务事件流。
- `cancel`：Host 通过 worker capability 请求取消指定 run；本地 worker 可翻译为本地 cancellation token，远程 worker 可由 proxy / stub 翻译为远程 cancel signal。
- `close`：关闭 worker 持有的执行环境资源。

`AgentRunRequest` 是 `run_agent_messages` 的第一版最小语义输入。该 request 已经包含 `session_id`、`run_id` 与 `cancellation_token`，因此 EngineWorker 接口不需要把这些字段重复展开成独立参数。

取消语义必须按执行形态解释：

- LocalProxy / 本地 EngineWorker 可以直接传递 Host 创建的本地 `cancellation_token`。
- RemoteProxy 不能把 Python 进程内 `cancellation_token` 对象当作跨进程序列化契约；RemoteStub 应在远端创建 worker-local cancellation token，并把 Host 的 `cancel(run_id)` 映射为远端取消信号。
- `cancel(run_id)` 是独立控制通道。即使 `AgentRunRequest` 已携带 `cancellation_token`，远程 run 启动后仍需要通过 run id 定位并取消远端 worker 内正在执行的 run。

EngineWorker 不需要知道自己是被 local proxy 还是 remote proxy 调用。

## 9. Proxy / Stub 边界

Host 不直接区分本地或远程 Engine 细节，而是通过 proxy 使用 EngineWorker capability。

Local 形态：

```text
Host
  -> LocalProxy
      -> EngineWorker
          -> Engine
          -> local ToolExecutor
```

Remote 形态：

```text
Host
  -> RemoteProxy
      -> RemoteStub
          -> EngineWorker
              -> Engine
              -> remote ToolExecutor
```

Proxy / Stub 不是 Phase 3 的实现目标，但它们定义了后续远程化边界：

- LocalProxy 是 Host 侧本地 adapter。
- RemoteProxy 是 Host 侧远程 adapter。
- RemoteStub 是远端进程的 RPC 接入层。
- EngineWorker 仍保持同一语义，内部 in-process 调 Engine。
- Remote Agent 表示 RemoteStub 侧的 EngineWorker 同时承载 Engine 和 remote ToolExecutor。

## 10. HostEvent / WorkerEvent 边界

`EngineEvent` 是 Engine 产出的业务事件事实。

`HostEvent` / `WorkerEvent` 是 Proxy 层面向 Host 产出的运行环境事件事实，不由 Engine 或 EngineWorker 产生。

示例：

```text
HostEvent(worker_started)
HostEvent(engine_event=EngineEvent(iteration_started))
HostEvent(engine_event=EngineEvent(final_answer))
HostEvent(worker_closed)
```

因此：

- Engine 不产生 HostEvent。
- EngineWorker 第一版也不产生 HostEvent。
- LocalProxy / RemoteProxy 后续负责把 EngineEvent 包装进 HostEvent，并补充 worker lifecycle、RPC failure、heartbeat、disconnect 等运行环境事件。
- Phase 3 不实现 HostEvent / WorkerEvent，只需确保 Engine 和 ToolExecutor 边界不阻碍 Proxy 后续包装事件。

## 11. Review 约束

后续 review 必须按以下口径判断：

- 不得把 EngineWorker 当作新的顶层业务层。
- 不得要求 Engine 直接理解 remote worker。
- 不得把 ToolExecutor 实现迁入 Engine。
- 不得把 Remote Agent 解释为远程 Engine 回调 Host 执行工具。
- 不得把 Host governance truth 误解为工具必须在 Host 进程内执行。
- Phase 3 中测试用 fake ToolExecutor 可以存在，但只能作为 EngineWorker 替 Host 代持 ToolExecutor 的测试替身，不代表生产 Host 实现。
- Phase 3 不实现 LocalProxy / RemoteProxy / RemoteStub / HostEvent；但不得把这些后续边界设计进 Engine。
