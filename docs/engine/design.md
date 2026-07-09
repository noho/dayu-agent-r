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

若 `EngineEvent stream` 结束但没有产出 terminal event，聚合入口返回 `EngineRunOutcomeFailed(error_code="missing_terminal")`。

包根 `dayu.engine` 同时导出 Engine 专属契约和调用 Engine 必需的 Dayu Agent 公共契约，例如工具 schema、工具执行协议、工具 outcome、JSON 值与取消 token。当前包根也导出 Runner 请求身份与输入观测相关公共契约，包括 `ClientCorrelationPolicy`、`RunnerRequestIdentity`、`build_runner_request_identity`、`RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION`、`RunnerInputMessageProjection`、`RunnerInputToolCallProjection` 与 `runner_role_sequence_digest`。`_AsyncAgent` 与 `AsyncOpenAIRunner` 是当前实现类，不属于包根稳定导出；调用方依赖函数式入口与 contracts。

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
| `attempt_id` | Host attempt id；直接 Engine 或非 attempt 路径为 `None` |
| `execution_id` | Host execution id；直接 Engine 或非 attempt 路径为 `None` |

Engine 不读取配置文件，也不从 `ToolExecutor` 查询 schema。`tool_schemas` 是本次 run 模型可见工具的唯一输入快照。是否禁用工具由 `disable_tools`、`AgentPolicy.allow_tool_calls`、Runner `supports_tool_calling` 三者共同决定。

`messages` 必须非空。`attempt_id` 与 `execution_id` 必须同时为空或同时非空；Engine 只把它们用于本次逻辑 Runner 调用身份派生，不拥有 Host attempt / execution 生命周期。

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
4. 将内容、推理、工具调用增量、usage、provider 协议错误、上下文超限与 iteration 完成事实提升为 `EngineEvent`。
5. 根据 Runner 消费状态分类为最终回答、工具调用或失败。
6. 若得到最终回答，产出 `final_answer`。
7. 若得到工具调用，按 `index_in_iteration` 排序并构造一个 batch 工具 handshake。
8. 对工具批次产出 `tool_calls_batch_ready` 与逐个 `tool_call_requested`，然后执行一次 `ToolExecutor.execute` batch handshake。
9. 对 completed / failed / cancelled 工具 outcome 产出 `tool_result_accepted`，无 awaiting 时产出 `tool_calls_batch_done`，再注入 assistant tool calls 与 tool messages，进入下一轮 Runner。
10. 对包含 awaiting 的 batch，先产出同批普通 outcome 的 `tool_result_accepted`，再产出 `tool_awaiting` 和 `run_suspended`，结束本次 run。
11. 若普通工具轮次耗尽或连续失败工具批次达到阈值，按 `fallback_mode` 收口。

Runner 异常会转为 `run_failed(runner_exception)`。Runner 流结束但没有 `runner_done` 会转为 `run_failed(runner_abnormal_stop)`。同一 run 内重复 `tool_call_id` 会转为 `run_failed(duplicate_tool_call_id)`。

### Length 续写

当最终回答候选的 `finish_reason` 为 `LENGTH` 时，表示本次生成达到模型输出上限，例如 `max_tokens`、`max_output_tokens`、`max_completion_tokens` 或 provider 的最大输出 token cap；它不是输入上下文窗口溢出，不触发 `context_compaction_requested`。Agent 会在仍有续写次数和 iteration 预算的前提下：

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
        *,
        request_identity: RunnerRequestIdentity | None = None,
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

OpenAI-compatible Runner 的当前传输规则：

- 当 `RunnerCallOptions.stream=True` 但 `RunnerSpec.supports_streaming=False` 时，Runner 会把本次 effective option 降级为 `stream=False`。
- 只有 effective stream 为 `True` 且 HTTP 200 response 的 media type 是 `text/event-stream` 时按 SSE 解析；流式请求缺失 `Content-Type` 时保留 SSE fallback 并记录诊断；其它 media type 按非流式 JSON 解析。
- `supports_stream_usage=True` 且 effective stream 为 `True` 时，请求 payload 写入 `stream_options.include_usage=True`；否则不写该字段。
- HTTP / 网络 / timeout 的可重试错误按 `RunnerSpec.max_retries`、错误分类与 `Retry-After` 退避；若某次 attempt 已经产出过 RunnerEvent，后续可重试失败不再重试，而是产出 error 事件并收口。
- 取消 token 在 HTTP 建连、response 获取、body 读取、SSE byte chunk 等待与 retry sleep 边界被观察；Runner 被取消时生成器自然结束，不补 `RunnerDoneData`。

## 8. RunnerSpec 与 RunnerCallOptions

`RunnerSpec` 描述 Runner 规约：

- provider、model、endpoint、api key 引用、headers。
- client correlation policy。
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

### Client correlation

每次逻辑 Runner 调用前，Agent 都构造一个 `RunnerRequestIdentity`，字段包括：

- `run_id`
- `attempt_id`
- `execution_id`
- `iteration_id`
- `iteration_index`
- `runner_call_index`
- `client_correlation_id`

`attempt_id` 与 `execution_id` 沿用 `AgentRunRequest` 的成对出现不变量。`runner_call_index` 在单次 run 内从 1 起递增。`client_correlation_id` 是 `dayu-` 加完整 64 位 lowercase SHA-256 hex 的稳定 ASCII id，只用于本地诊断关联和 provider adapter 的显式 per-call 映射，不表达 Host 生命周期治理，也不是 provider end-user 字段。

`ClientCorrelationPolicy` 表达 provider 协议 outbound 映射策略：

- `DISABLED`：不发送客户端关联 id。
- `OPENAI_X_CLIENT_REQUEST_ID`：OpenAI-compatible 协议下发送 `X-Client-Request-Id`。

OpenAI-compatible Runner 只有在 policy 为 `OPENAI_X_CLIENT_REQUEST_ID` 且本次 `request_identity` 非空时发送 `X-Client-Request-Id`。policy 关闭或 identity 缺失时不发送。policy 开启时，`RunnerSpec.headers` 不得包含大小写不敏感匹配的 `X-Client-Request-Id` 静态 header。

### Provider extension 配置 DSL

`provider_request_extension_from_json` 把配置层原样保留的 JSON DSL 转为 `ProviderRequestExtension` typed contract。未知 type、未知字段、字段类型非法、非法枚举值或契约拒绝的字段组合都会 fail closed。该 helper 只负责 JSON DSL 到 Engine 契约的解析，不把单次采样参数、输出长度、top-p 或 stream 开关塞进 provider extension。

## 9. RunnerEvent

`RunnerEvent` 是 Runner 到 Agent 的协议归一事件契约。它通过 Engine contracts 导出，供 Runner 实现和契约测试使用，但不会作为 `run_agent_messages` 的对外 `EngineEvent stream` 直接产出；Agent 必须将 Runner 事实提升为 `EngineEvent`。

| Runner event | Data 类型 | Agent 处理 |
| --- | --- | --- |
| `runner_content_delta` | `RunnerContentDeltaData` | 累积正文并产出 `content_delta` |
| `runner_reasoning_delta` | `RunnerReasoningDeltaData` | 累积推理文本并产出 `reasoning_delta` |
| `runner_tool_call_delta` | `RunnerToolCallDeltaData` | 记录工具调用信号，并产出 `tool_call_delta` |
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

工具 batch 的输入顺序由 Agent 对本轮完整工具调用按 `index_in_iteration` 排序后确定。进入工具执行前，Engine 先检查同一 run 内重复 `tool_call_id`，再产出 `tool_calls_batch_ready` 和逐个 `tool_call_requested`。`tool_calls_batch_ready.tool_calls` 的顺序就是按 `index_in_iteration` 排序后的执行输入顺序，不是 provider stream chunk 到达顺序，也不是 executor 返回顺序。

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

completed / failed / cancelled outcome 会进入 `tool_result_accepted`。无 awaiting 的 batch 会被投影为 LLM-facing tool messages。awaiting outcome 不进入普通工具结果信封，而是触发挂起流程。进入模型上下文的工具 schema 与 prompt 只能描述业务请求、输入、输出和等待工具结果返回的行为，不得要求模型执行 polling、解析 Host wait id、observation handle、runtime 状态或其它等待治理标识。

工具结果信封只表达 completed / failed：

- `ToolResultSuccess(ok=True, value, meta)`
- `ToolResultFailure(ok=False, error, message, hint, meta)`

等待语义只能通过 `ToolAwaitingOutcome.await_spec` 显式表达，不能塞进工具结果 `meta`。

### Reasoning 与 provider roundtrip

Engine 对调用方暴露的 reasoning 契约是 provider-neutral 的 `reasoning_delta` 与 `reasoning_content`。Runner 负责把 provider 私有响应形态归一为 `RunnerReasoningDeltaData`、`RunnerContentCompletedData.reasoning_content` 或 `RunnerToolCallsCompletedData.reasoning_content`；Agent 再提升为 `ReasoningDeltaData` 或保存在后续 assistant tool-call message 中。

OpenAI-compatible Runner 当前支持两类 inbound reasoning 来源：

- 原生 `reasoning_content` 字段：SSE 路径读取 `choices[].delta.reasoning_content`，非流式路径读取 `choices[].message.reasoning_content`。
- Gemini `include_thoughts` 私有协议：当 `RunnerSpec.provider_request` 是 `GeminiThinkingExtension(include_thoughts=True)` 时，Runner 从 `content` 中剥离 `<thought>...</thought>` 标签；标签内文本进入 reasoning，标签外文本保留为正文。

如果同一响应同时包含 Gemini `<thought>` 提取内容与原生 `reasoning_content`，Runner 保持 `extracted_reasoning + native_reasoning` 的顺序，使 stream / non-stream 终态一致。

Outbound roundtrip 分两条独立通道：

- `AssistantMessage.reasoning_content` 非空时，payload builder 在 outbound assistant message 上原样写回 `reasoning_content` 字段。该字段是 Engine 历史回放事实，用于满足 thinking + tool-call provider 的 reasoning roundtrip；payload builder 不凭空生成 reasoning 内容。
- `ToolCallProviderState` 是封闭 provider-specific 联合。当前成员 `GeminiToolCallState` 表示 Gemini tool-call `extra_content.google.thought_signature`。Runner 从 inbound tool call 的 `extra_content.google.thought_signature` 解析出该状态；Agent 在注入 assistant tool calls 时保留 `provider_state`；payload builder 再把它写回 outbound tool call 的 `extra_content.google.thought_signature`。

`reasoning_content` 与 Gemini `thought_signature` 是不同协议通道：前者承载 assistant reasoning 文本，后者承载 Gemini tool-call 续航签名。二者都可能服务 provider roundtrip，但不能互相替代。

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

1. 对同批 completed / failed / cancelled record 产出 `tool_result_accepted`。
2. 对每个 awaiting record 产出 `tool_awaiting`，携带对应 call、`await_spec` 与 `snapshot`。
3. 关闭本次 Runner。
4. 产出 terminal `run_suspended`，`reason` 为 `tool_awaiting`，并携带同一批次已接受的普通工具事实与 awaiting 事实。
5. 结束本次 run。

awaiting 路径不产出 `tool_calls_batch_done`。`tool_calls_batch_done` 只表示本批不含 awaiting，completed / failed / cancelled outcome 已全部接受，可进入下一轮 Runner。

Engine 不等待外部长事务完成，不轮询 job，不持久化 wait record，不保留可恢复的 in-memory Agent 或 Runner。恢复不是恢复旧 Engine 实例；调用方在外部长事务结束后构造新的 `AgentRunRequest`，把同一 assistant tool-call 批次、已接受工具事实、工具终态结果或恢复输入显式放入新 run 的 `messages`。这些恢复输入必须是 LLM-facing 的业务可读消息，例如原工具请求和工具结果摘要；不能要求模型理解 wait record、poll adapter、external job lifecycle、observation handle 或 Host/ToolRuntime 治理术语。

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
- ToolExecutor 返回 completed / failed / cancelled outcome 后，Agent 先产出 `tool_result_accepted` 并注入 tool message；之后若观察到取消，只阻止下一轮 Runner，不丢失已接受工具结果。
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
| `tool_call_delta` | `ToolCallDeltaData` | Runner 流式工具调用增量 |
| `tool_calls_batch_ready` | `ToolCallsBatchReadyData` | Agent 已接受本轮完整工具调用批次，可进入工具执行 |
| `tool_call_requested` | `ToolCallRequestedData` | 模型请求工具调用 |
| `tool_result_accepted` | `ToolResultAcceptedData` | Engine 已接受 completed / failed / cancelled 工具 outcome |
| `tool_calls_batch_done` | `ToolCallsBatchDoneData` | 本批不含 awaiting，accepted outcome 已全部接受 |
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

`iteration_started` 携带 Engine 对本次真实 Runner 输入的直接观察：`message_count`、按实际 message role 顺序计算的 `role_sequence_digest`、`runner_input_serializer_schema_version`，以及 `input_projection`。`input_projection` 是按实际 Runner 输入顺序排列的中性 LLM-facing message projection，包含 message `index`、`role`、`content` / tool call id、assistant tool call 名称和参数；它不包含 Host-owned runner call index、manifest ref、source refs、memory / compact refs、tool schema refs、provider headers、Authorization/API key 或 provider raw request/response。

工具事件分层如下：

- `tool_call_delta` 直接提升 Runner 的流式工具调用增量。
- `tool_calls_batch_ready` 表示 Agent 已接受 Runner 完成的本批工具调用，顺序为按 `index_in_iteration` 排序后的执行输入顺序。
- `tool_call_requested` 表示 Agent 即将执行单个工具调用。
- `tool_result_accepted` 表示 completed / failed / cancelled 工具 outcome 已进入 Engine 接受边界。
- `tool_calls_batch_done` 只在本批不含 awaiting 时产出，不属于 terminal。
- `tool_awaiting` + `run_suspended` 表示本批包含 awaiting outcome；该路径不产出 `tool_calls_batch_done`。

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

`finish_reason=LENGTH` 不属于 provider context overflow。它表示输出生成触达模型输出上限，应由 Length 续写或降级 final 处理；只有 Runner 明确报告上下文长度超限时，Engine 才产出 `context_compaction_requested`。

## 16. Tool Schema

`ToolSchema` 使用 OpenAI-compatible function schema 形态：

- `ToolSchema.type` 固定为 `"function"`。
- `ToolFunctionSchema.name` 是工具名。
- `ToolFunctionSchema.description` 是工具描述。
- `ToolFunctionSchema.parameters` 是顶层 `object` 参数 schema。
- `ToolParametersSchema.required` 是必填字段名元组。
- `ToolParametersSchema.additional_properties` 为 `bool | None`。

`ToolTruncateSpec` 与 `ToolTruncationStrategy` 存在于 `dayu.contracts` 公共契约中，不属于 Engine 包根导出的稳定调用面。工具结果截断由 Engine 外部工具执行环境解释和执行；Engine 不创建 truncation cursor，不生成或校验 `scope_token`，不执行 `fetch_more`，不保存跨 run 工具状态。
