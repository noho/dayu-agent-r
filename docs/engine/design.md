# Engine 设计说明

本文档描述当前代码中的 Engine 设计事实。Engine 提供一次性 Agent run 的函数式入口、Runner 协议归一、工具调用闭环、`EngineEvent stream` 与终态 outcome。Engine 不保存跨 run 状态，不拥有工具注册表，不读取配置文件，不理解财报业务语义，也不直接访问财报文档存储。

## 1. 边界与职责

Engine 位于调用方下游，只暴露运行一次 Agent 所需的输入、输出与中性协议。调用方负责构造完整的 `AgentRunRequest`，Engine 只消费请求中的事实并产出 `EngineEvent stream` 或聚合后的 `AgentRunResult`。

Engine 当前负责：

- 运行单次 Agent 推理循环，包括 iteration、RunnerEvent 消费、工具结果回填、最终回答、降级收口、续写与终态提交。
- 通过 `AsyncRunner` 调用模型 provider，并把 provider 协议归一为 `RunnerEvent`。
- 通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 与工具执行环境完成 bounded handshake。
- 将 Runner 和工具执行事实提升为强类型 `EngineEvent`。
- 观察 `CancellationToken`，在可中断边界收口为结构化取消终态。
- 在 provider 上下文超限时产出 `context_compaction_requested`，随后以可恢复 `run_failed(context_compaction_required)` 结束本次 run。

Engine 当前不负责：

- 会话、用户意图、配置解析、prompt 渲染、权限、审计、持久化、trace 存储或观察者管线。
- 工具注册、工具发现、工具参数校验、工具权限、工具内部超时、后台任务治理、长事务监控或恢复调度。
- Host 上下文预算治理、proactive threshold compaction、context compact / retry、provider-aware tokenizer 或 budget policy。
- 财报业务语义、ticker 归一、文档选择、章节规则、XBRL 处理或财报文档仓储访问。
- 通过上层包反向依赖 UI、Service、Host、Fins 或具体工具实现。

财报文档存取不属于 Engine 能力面。涉及财报文档的工具必须在 Engine 外部执行环境内遵守 `dayu.fins.storage` 仓储约束；Engine 只看见工具 schema、工具调用请求和工具 outcome。

### 1.1 Stream 术语边界

本文档不得把不同层的流式概念混称为 “stream”。固定术语如下：

- `EngineEvent stream`：`run_agent_messages(request)` 产出的本次 run 异步事件流。它是调用方 ingest 的输入来源，不是 durable truth。
- `RunnerEvent stream`：Runner 到 Agent 的 provider 协议归一事件流，只在 Engine 内部消费，不直接暴露给 Engine 调用方。
- `SSE stream` / provider streaming：Runner 与 provider 之间的传输能力，由 `RunnerCallOptions.stream`、`RunnerSpec.supports_streaming`、`supports_stream_usage` 和 SSE idle 配置控制。
- `Host event stream`：Host 从 EventLog `event_sequence` cursor 派生的订阅 / 补读流，不属于 Engine 能力面。
- `content_delta`、`reasoning_delta`、`tool_call_delta` 是 EngineEvent / RunnerEvent 的增量事件；是否进入 Host preview、canonical EventLog、memory 或 audit，由 Host ingest 与治理策略决定。

EngineEvent 不提供事件序号、持久化 cursor、幂等键或 Host `event_sequence`。这些属于调用方，尤其是 Host EventLog / Host event stream。

## 2. 公共入口

Engine 公共入口由 `dayu.engine.agent` 提供，并通过 `dayu.engine.__init__` 导出：

- `run_agent_messages(request: AgentRunRequest) -> AsyncGenerator[EngineEvent, None]`
- `run_agent_and_wait(request: AgentRunRequest) -> AgentRunResult`

`run_agent_messages` 是 `EngineEvent stream` 入口。它为本次 request 构造新的 Runner 与私有 `_AsyncAgent`，然后产出 `EngineEvent`。调用方必须完整消费生成器；若提前停止消费，必须显式 `aclose()`，以触发 Runner 关闭和 run-scoped 资源收尾。

`run_agent_and_wait` 是聚合入口。它完整消费 `run_agent_messages` 的 `EngineEvent stream`，并把 terminal event 转换为 `AgentRunResult` 的四种封闭终态之一：

- `EngineRunOutcomeFinalAnswer`
- `EngineRunOutcomeFailed`
- `EngineRunOutcomeCancelled`
- `EngineRunOutcomeSuspended`

包根 `dayu.engine` 同时导出 Engine 专属契约和调用 Engine 必需的跨层共享契约，例如工具 schema、工具执行协议、工具 outcome、JSON 值与取消 token。`_AsyncAgent` 与 `AsyncOpenAIRunner` 是当前实现类，不属于包根稳定导出；调用方依赖函数式入口与 contracts。

## 3. Run-Scoped 生命周期

Engine 当前采用 run-scoped 一次性 Agent / Runner 模型：

- 每次 `run_agent_messages(request)` 都创建新的 `_AsyncAgent`。
- 每次 run 都通过 `_build_runner(request)` 创建新的 `AsyncOpenAIRunner`。
- `_AsyncAgent` 实例只服务一个 run，并用实例级运行槽防止并发复用。
- Runner 的 HTTP session、provider-side SSE stream 与 provider 请求资源属于本次 run。
- run 正常结束、失败、取消、挂起或生成器关闭时，Agent 都会幂等调用 `runner.close()`。
- 本次 run 内的消息列表、iteration 状态、已执行 tool call id、连续失败工具批次计数和续写状态都只存在于该 Agent 实例内。

取消和恢复都不会复用旧 Agent 或旧 Runner。若取消后调用方要继续原目标，或长事务工具完成后要恢复原目标，调用方都必须构造新的 `AgentRunRequest`，把已确认事实、工具终态结果或新的用户意图显式放入 `messages`。

## 4. AgentRunRequest

`AgentRunRequest` 是运行一次 Agent 的完整输入：

| 字段 | 含义 |
| --- | --- |
| `run_id` | 本次运行 id |
| `session_id` | 会话 id |
| `messages` | 本次 run 的输入消息快照 |
| `disable_tools` | 本次 run 是否禁用工具 |
| `runner_spec` | Runner 规约 |
| `runner_options` | 单次 Runner 调用参数 |
| `agent_policy` | Agent 运行策略 |
| `tool_schemas` | 本次 run 暴露给 LLM 的工具 schema 快照 |
| `tool_executor` | 工具执行协议 handle |
| `cancellation_token` | 取消观察 token |

Engine 不读取配置文件，也不从 `ToolExecutor` 查询 schema。`tool_schemas` 是本次 run 模型可见工具的唯一输入快照。是否禁用工具由 `disable_tools`、`AgentPolicy.allow_tool_calls`、Runner `supports_tool_calling` 三者共同决定。

## 5. AgentPolicy

`AgentPolicy` 是 Agent loop 的运行策略真源：

- `max_iterations` 控制普通 LLM 迭代次数，必须至少为 1 才能运行。
- `continuation_max_attempts` 控制 `finish_reason=length` 续写尝试次数，必须大于等于 0。
- `allow_tool_calls` 控制策略层是否允许工具调用。
- `tool_execution_timeout_seconds` 是 Engine 等待 `ToolExecutor.execute` 返回 outcome 的握手超时真源，必须为有限正数。
- `fallback_mode` 控制工具轮次耗尽或连续失败工具批次达到阈值后的收口方式。
- `fallback_prompt` 是 force-answer 模式追加给 Runner 的用户消息。
- `continuation_prompt` 是 length 续写时追加给 Runner 的用户消息，不能为空。
- `max_consecutive_failed_tool_batches` 控制连续全失败工具批次阈值，必须至少为 1。

`BatchToolExecutionContext.timeout_seconds` 不是独立真源。Agent 构造工具执行上下文时，把 `AgentPolicy.tool_execution_timeout_seconds` 投影到 `BatchToolExecutionContext.timeout_seconds`，供工具执行环境协作使用；Engine 同时用同一个策略值包裹 `ToolExecutor.execute` handshake。

## 6. Agent 推理循环

一次 run 内，Agent 按 iteration 执行以下状态机：

1. 检查取消与 `max_iterations`。
2. 产出 `iteration_started`。
3. 调用 Runner，并消费 `RunnerEvent`。
4. 将内容、推理、usage、provider 协议错误、上下文超限与 iteration 完成事实提升为 `EngineEvent`。
5. 根据 Runner 消费状态分类为最终回答、工具调用或失败。
6. 若得到最终回答，产出 `final_answer`。
7. 若得到工具调用，按 `index_in_iteration` 排序并构造一个 batch 工具 handshake。
8. 对 completed / failed / cancelled 工具 outcome 产出 `tool_result_accepted`，无 awaiting 时注入 assistant tool calls 与 tool messages，进入下一轮 Runner。
9. 对包含 awaiting 的 batch 产出 `tool_awaiting` 和 `run_suspended`，结束本次 run。
10. 若普通工具轮次耗尽或连续失败工具批次达到阈值，按 `fallback_mode` 收口。

Runner 异常会转为 `run_failed(runner_exception)`。Runner 流结束但没有 `runner_done` 会转为 `run_failed(runner_abnormal_stop)`。同一 run 内重复 `tool_call_id` 会转为 `run_failed(duplicate_tool_call_id)`。

### Length 续写

当最终回答候选的 `finish_reason` 为 `LENGTH` 时，Agent 会在仍有续写次数和 iteration 预算的前提下：

- 记录当前回答片段。
- 将已有片段作为 assistant message 注入 run-local 消息。
- 追加 `AgentPolicy.continuation_prompt` 作为 user message。
- 进入下一轮 Runner，并禁用工具。

续写轮如果再次产生工具调用，会以 `run_failed(continuation_tool_call_not_allowed)` 收口。续写预算耗尽时，Agent 合并已获得的内容片段，以 `degraded=True` 的 `final_answer` 收口。

### Fallback 收口

工具轮次耗尽或连续全失败工具批次达到阈值后：

- `AgentFallbackMode.RAISE_ERROR` 直接产出 `run_failed`。
- `AgentFallbackMode.FORCE_ANSWER` 追加 `fallback_prompt`，禁用工具再调用一次 Runner。该路径得到的最终回答标记 `degraded=True`。

force-answer Runner 调用前会观察取消；force-answer 已经得到可接受 final content 后进入 final answer commit boundary，迟到取消不能改写终态。

## 7. Runner 协议

`AsyncRunner` 是 Engine 调用 LLM provider 的唯一抽象：

```python
class AsyncRunner(Protocol):
    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]: ...

    def is_supports_tool_calling(self) -> bool: ...

    async def close(self) -> None: ...
```

Runner 负责：

- 根据 `RunnerSpec` 与 `RunnerCallOptions` 发起 provider 请求。
- 将 provider 流式或非流式响应归一为 `RunnerEvent`。
- 表达 content delta、reasoning delta、tool call delta、tool calls completed、content completed、usage、HTTP 错误、provider 协议错误和 runner done。
- 在 HTTP 建连、响应读取、SSE chunk 等待、重试 sleep 等阻塞边界观察取消。
- 关闭底层连接资源。

Runner 不负责：

- 产出 Host 可见的 `EngineEvent`。
- 补齐 `session_id`、`run_id`、`iteration_id`。
- 执行工具或依赖 `ToolExecutor`。
- 做 Agent 多轮迭代、fallback、续写、取消终态或 run 终态决策。

当前 `_build_runner` 固定构造 OpenAI-compatible `AsyncOpenAIRunner`。Runner 选择和配置事实由 `RunnerSpec` 表达；Engine 公共契约不接受开放的 `**extra_payloads`。

## 8. RunnerSpec 与 RunnerCallOptions

`RunnerSpec` 描述 Runner 规约：

- provider、model、endpoint、api key 引用、headers。
- 是否支持 tool calling、streaming、stream usage。
- 默认请求超时、最大重试次数。
- provider 请求扩展。
- SSE stream idle timeout 与 heartbeat。

`supports_stream_usage` 是 stream usage 请求字段的能力门控。仅当 `RunnerCallOptions.stream=True` 且 `RunnerSpec.supports_stream_usage=True` 时，OpenAI-compatible Runner 才写入 `stream_options.include_usage=True`；不支持时不写该 provider 字段。

`stream_idle_timeout_seconds` 与 `stream_idle_heartbeat_seconds` 是 Runner 规约的一部分。`stream_idle_timeout_seconds=None` 表示不启用 SSE byte chunk 空闲检测；启用时必须为正数。`stream_idle_heartbeat_seconds` 只有在 idle timeout 启用时才允许设置，也必须为正数，且不得大于 `stream_idle_timeout_seconds`。

provider 请求扩展是封闭联合：

- `OpenAIReasoningExtension`
- `AnthropicThinkingExtension`
- `DeepSeekThinkingExtension`
- `MimoThinkingExtension`
- `GeminiThinkingExtension`
- `QwenThinkingExtension`

`RunnerCallOptions` 描述单次调用参数：

- `temperature`
- `max_tokens`
- `top_p`
- `stream`

模型级 provider 扩展归入 `RunnerSpec.provider_request`。单次调用可变参数归入 `RunnerCallOptions`。Agent 不拼 provider 私有 payload。

## 9. RunnerEvent

`RunnerEvent` 是 Runner 到 Agent 的协议归一事件契约。它通过 Engine contracts 导出，供 Runner 实现和契约测试使用，但不会作为 `run_agent_messages` 的对外 `EngineEvent stream` 直接产出；Agent 必须将 Runner 事实提升为 `EngineEvent`。

| Runner event | Data 类型 | Agent 处理 |
| --- | --- | --- |
| `runner_content_delta` | `RunnerContentDeltaData` | 累积正文并产出 `content_delta` |
| `runner_reasoning_delta` | `RunnerReasoningDeltaData` | 累积推理文本并产出 `reasoning_delta` |
| `runner_tool_call_delta` | `RunnerToolCallDeltaData` | 记录工具调用信号，不对外产出 EngineEvent |
| `runner_tool_calls_completed` | `RunnerToolCallsCompletedData` | 保存完整工具调用请求，等待 iteration 分类 |
| `runner_content_completed` | `RunnerContentCompletedData` | 保存完整正文与 finish reason，产出 `content_completed` |
| `runner_usage_recorded` | `RunnerUsageRecordedData` | 产出 `usage_reported` |
| `provider_protocol_error` | `RunnerProtocolErrorData` | 产出 `provider_protocol_error`，设置失败候选 |
| `runner_http_error` | `RunnerHTTPErrorData` | 上下文超限时产出 `context_compaction_requested`，其它 HTTP 错误设置失败候选 |
| `runner_done` | `RunnerDoneData` | 标记 Runner 完成，产出 `iteration_completed` |

`RunnerEvent` 不含 `session_id` 或 `run_id`。这些字段在 `EngineEvent` 提升阶段补齐。调用方消费 Agent run 时只观察 `EngineEvent`；只有实现或测试 Runner 协议时才直接处理 `RunnerEvent`。

## 10. 工具调用协议

Engine 只通过 `ToolExecutor` 协议调用工具：

```python
class ToolExecutor(Protocol):
    async def execute(
        self,
        request: BatchToolExecutionRequest,
    ) -> BatchToolExecutionOutcome: ...
```

`BatchToolExecutionRequest` 包含：

- `calls: tuple[ToolCallRequest, ...]`
- `context: BatchToolExecutionContext`

`ToolCallRequest` 包含：

- `tool_call_id`
- `name`
- `arguments`
- `index_in_iteration`
- `provider_state`

`BatchToolExecutionContext` 包含：

- `run_id`
- `session_id`
- `iteration_id`
- `timeout_seconds`
- `cancellation_token`
- `correlation_id`

批内单次工具调用身份由 `ToolCallRequest.tool_call_id` 和 `ToolCallRequest.index_in_iteration` 承载。`correlation_id` 是批级中性跨组件关联 id，不承载 trace recorder 私有语义，不作为幂等键、游标或授权凭据。

`BatchToolExecutionOutcome` 包含 `records: tuple[BatchToolExecutionRecord, ...]`。每个 record 包含 `tool_call_id` 与 `outcome`，必须与输入 `calls` 严格双射。Engine 按输入 call 顺序处理返回记录，不把 executor 返回顺序作为公共事件顺序真源。

### ToolDefinition 与 ToolCallable

工具声明与工具执行治理不属于 Engine。

`@tool(...)`、`ToolDefinition`、`ToolCallable` 的整体边界见 [dayu/README.md 的“工具定义与执行边界”](../../dayu/README.md#工具定义与执行边界)。Engine 不消费 `ToolDefinition`，不调用 `ToolCallable`，也不从工具定义对象读取 schema 或治理策略。

Host / ToolRuntime 可以用 `@tool(...)` 在工具现场同源声明 `ToolSchema`、截断声明、展示 metadata、标签和单工具 callable。`ToolCallable` 是单工具调用协议；Host / ToolRuntime 持有它，并在自身治理边界内把一组工具定义包装为 `ToolExecutor`。batch 内串行、并发、权限、审批、限流、内部 timeout、审计、长事务 awaiting、orphan cleanup 和工具级取消都属于 Host / ToolRuntime。

`dayu.contracts` 不提供 `FunctionToolExecutor` 或其它默认执行器。公共契约只定义 `ToolCallable`、`ToolDefinition`、`ToolExecutor` 与 batch request/outcome 形状，不定义 batch 内部执行策略。

### ToolExecutionOutcome

工具执行 outcome 是封闭联合：

- `ToolCompletedOutcome(result: ToolResultSuccess)`
- `ToolFailedOutcome(result: ToolResultFailure)`
- `ToolAwaitingOutcome(await_spec: ToolAwaitSpec, snapshot: ToolAwaitSnapshot | None)`
- `ToolCancelledOutcome(reason, message, hint, meta)`

completed / failed / cancelled outcome 会进入 `tool_result_accepted`。无 awaiting 的 batch 会被投影为 LLM-facing tool messages。awaiting outcome 不进入普通工具结果信封，而是触发挂起流程。

工具结果信封只表达 completed / failed：

- `ToolResultSuccess(ok=True, value, meta)`
- `ToolResultFailure(ok=False, error, message, hint, meta)`

等待语义只能通过 `ToolAwaitingOutcome.await_spec` 显式表达，不能塞进工具结果 `meta`。

### Provider State

`ToolCallProviderState` 是封闭 provider-specific 联合。当前成员是 `GeminiToolCallState`，用于在工具调用 roundtrip 中携带 Gemini `thought_signature`。Agent 在注入 assistant tool calls 时会保留 `provider_state`，使 Runner 序列化阶段能按 provider 规则回传。

## 11. ToolExecutor Handshake Timeout

`ToolExecutor.execute` 是 Engine 与工具执行环境之间的 bounded handshake。Engine 等待 outcome，但不托管工具内部任务或外部长事务生命周期。

当前 timeout 规则：

- `AgentPolicy.tool_execution_timeout_seconds` 是唯一真源。
- Agent 构造 `BatchToolExecutionContext.timeout_seconds` 时投影该值。
- Agent 调用 `await_or_cancel_or_timeout` 包裹 `ToolExecutor.execute`，使用同一个 timeout。
- 若 execute 在 timeout 前返回 completed / failed / awaiting outcome，Agent 按 outcome 提交后续事件。
- 若 execute 抛出普通异常，Agent 将其归一为 `ToolFailedOutcome(error="tool_executor_exception")`，随后按普通 failed outcome 产出 `tool_result_accepted` 并注入 tool message。
- 若 execute 抛出 `asyncio.CancelledError` 且本次 run 的 `cancellation_token` 已取消，Agent 以 `run_cancelled` 收口；若 token 未取消，则该异常同样归一为 `ToolFailedOutcome(error="tool_executor_exception")`。
- 若 timeout 先到，runtime helper 会取消 execute await task，并等待该 task 收口。
- Engine 以不可恢复 `run_failed(tool_execution_timeout)` 收口。

该 timeout 只表示 Engine 不再等待 `execute()` 的 handshake outcome。它不证明工具内部线程、子进程、HTTP 请求或远端 job 已停止。若工具已经启动外部长事务但未在 timeout 前返回 `ToolAwaitingOutcome`，Engine 没有 `await_spec` 或 snapshot，因此不能恢复、监控或取消该长事务。

## 12. Suspend 与 Resume

当前 run suspension 的唯一来源是 `ToolExecutor.execute` 返回的 batch outcome 中包含至少一个 `ToolAwaitingOutcome`。

收到包含 `ToolAwaitingOutcome` 的 batch outcome 后，Agent 按固定顺序处理：

1. 对每个 awaiting record 产出 `tool_awaiting`，携带对应 call、`await_spec` 与 `snapshot`。
2. 关闭本次 Runner。
3. 产出 terminal `run_suspended`，`reason` 为 `tool_awaiting`，并携带同一批次已接受的普通工具事实与 awaiting 事实。
4. 结束本次 run。

Engine 不等待外部长事务完成，不轮询 job，不持久化 wait record，不保留可恢复的 in-memory Agent 或 Runner。恢复不是恢复旧 Engine 实例；调用方在外部长事务结束后构造新的 `AgentRunRequest`，把同一 assistant tool-call 批次、已接受工具事实、工具终态结果或恢复输入显式放入新 run 的 `messages`。

`run_agent_messages` 调用方需要消费并保存 `tool_awaiting` / `run_suspended` 中的恢复事实。`run_agent_and_wait` 调用方通过 `EngineRunOutcomeSuspended` 获取同一组结构化事实。

## 13. Cancellation

`CancellationToken` 是 Engine 公共取消观察协议：

- `is_cancelled() -> bool`
- `cancel_reason() -> str | None`
- `requested_at() -> datetime | None`

Engine 只观察 token，不持有取消治理真源。取消公共终态通过 `run_cancelled` 与 `EngineRunOutcomeCancelled` 表达。Engine 不把取消异常作为公共契约。

`dayu.runtime.cancellation` 提供层中立 race helper：

- `await_or_cancel`
- `await_or_cancel_or_timeout`
- `wait_for_or_cancel`

这些 helper 使用封闭联合结果表达 completed / cancelled / timed out。helper 自身所在 task 被外层 `Task.cancel()` 取消时，`asyncio.CancelledError` 会透传。

### Cancellation Commit Boundary

取消不是随时覆盖一切。Engine 当前遵守已接受事实优先的提交边界：

- iteration 起点、Runner 调用期间、工具 handshake 前和 fallback Runner 调用前会观察取消。
- RunnerEvent 已经被 Agent 消费后，相关 content、reasoning、usage、protocol error 或状态更新先被接受，再观察取消。
- Runner 未完成时取消可以抢占本轮并收口为 `run_cancelled`。
- Runner 已 `done` 后，分类得到的 final / tool / failure 候选不能被迟到取消改写。
- ToolExecutor 返回 completed / failed outcome 后，Agent 先产出 `tool_result_accepted` 并注入 tool message；之后若观察到取消，只阻止下一轮 Runner，不丢失已接受工具结果。
- ToolExecutor 返回 awaiting outcome 后，Agent 先产出 `tool_awaiting`，再产出 `run_suspended`；迟到取消不能吞掉 `await_spec` 或 snapshot。
- final decision 进入 terminal commit boundary 后，`final_answer` 是终态；迟到取消不能改写为 `run_cancelled`。

取消是当前 run 的 terminal reason。取消后若调用方要继续原目标，必须构造新的 `AgentRunRequest`。

## 14. EngineEvent Stream

`EngineEvent` 是 Engine 对调用方暴露的事件边界，组成 `EngineEvent stream`：

```python
@dataclass(frozen=True, slots=True)
class EngineEvent:
    occurred_at: datetime
    session_id: str
    run_id: str
    type: EngineEventType
    data: EngineEventData
    metadata: Mapping[str, JsonValue] | None
```

`metadata` 只允许承载中性 observer / debug hint，不承载契约事实。当前 Agent 产出的事件 `metadata` 为 `None`。

Terminal event 类型固定为：

- `final_answer`
- `run_failed`
- `run_cancelled`
- `run_suspended`

`TERMINAL_ENGINE_EVENT_TYPES` 提供上述终态集合。

| Engine event | Data 类型 | 含义 |
| --- | --- | --- |
| `iteration_started` | `IterationStartedData` | 新一轮 LLM iteration 开始 |
| `content_delta` | `ContentDeltaData` | 正文增量 |
| `reasoning_delta` | `ReasoningDeltaData` | 推理文本增量 |
| `content_completed` | `ContentCompleteData` | 本轮完整正文与 finish reason |
| `tool_call_requested` | `ToolCallRequestedData` | 模型请求工具调用 |
| `tool_result_accepted` | `ToolResultAcceptedData` | Engine 已接受 completed / failed 工具 outcome |
| `tool_awaiting` | `ToolAwaitingData` | 工具进入长事务等待 |
| `context_compaction_requested` | `ContextCompactionRequestedData` | provider 上下文超限，需要调用方重构上下文后新开 run |
| `usage_reported` | `UsageReportedData` | provider usage 事实 |
| `provider_protocol_error` | `ProviderProtocolErrorData` | provider 协议解析错误 |
| `iteration_completed` | `IterationCompletedData` | 本轮 Runner done |
| `final_answer` | `FinalAnswerData` | 最终回答终态 |
| `run_suspended` | `RunSuspendedData` | run 挂起终态 |
| `run_cancelled` | `RunCancelledData` | run 取消终态 |
| `run_failed` | `RunFailedData` | run 失败终态 |

`tool_call_requested` 是观测事件，不是外部二次执行命令。工具执行由 Agent 状态机在事件之后继续调用 `ToolExecutor.execute` 完成。

`EngineEvent stream` 的顺序只由本次异步生成器产出顺序定义。Engine 不提供持久化 cursor、Host `event_sequence`、重放语义、多客户端 fanout 或 EventLog append；调用方若需要恢复、补读、audit、usage、tool trace 或 memory，必须在 Engine 外部把 EngineEvent ingest 成自己的 durable facts。

## 15. Context Compaction

当前 Engine 不做上下文压缩，不在 run 内 compact / retry，不计算 Host
budget，也不做 proactive threshold compaction、provider-aware tokenizer
或 Host budget policy。

当 Runner 报告 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 时，Agent：

1. 产出 `context_compaction_requested`。
2. 将 `ContextCompactionRequestedData.budget_state` 设为 `None`，表示
   provider overflow 边界没有可靠预算快照。
3. 设置失败候选 `context_compaction_required`。
4. 在 Runner done 后以 `run_failed(recoverable=True)` 收口。

是否压缩、如何压缩、如何重新构造消息、如何记录 before / after
budget，以及是否再次发起 run，属于调用方在 Engine 之外的职责。
Engine 只表达 provider context overflow 这一可恢复事实。

## 16. Tool Schema

`ToolSchema` 使用 OpenAI-compatible function schema 形态：

- `ToolSchema.type` 固定为 `"function"`。
- `ToolFunctionSchema.name` 是工具名。
- `ToolFunctionSchema.description` 是工具描述。
- `ToolFunctionSchema.parameters` 是顶层 `object` 参数 schema。
- `ToolParametersSchema.required` 是必填字段名元组。
- `ToolParametersSchema.additional_properties` 为 `bool | None`。

`ToolTruncateSpec` 与 `ToolTruncationStrategy` 存在于 `dayu.contracts` 公共契约中，不属于 Engine 包根导出的稳定调用面。工具结果截断由 Engine 外部工具执行环境解释和执行；Engine 不创建 truncation cursor，不生成或校验 `scope_token`，不执行 `fetch_more`，不保存跨 run 工具状态。
