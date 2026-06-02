# Engine 开发手册

Engine 位于整体链路最下游：

```text
UI -> Service -> Host -> Engine
```

## Agent更新约束【必须遵守】

- 本文档只写 `dayu.engine` 当前代码已经暴露的开发接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制、扩展点。
- 本文档不写过程状态，不写未来计划，不写实现细节，只保留稳定说明。

## 设计目标

- 为宿主强约束下的 LLM in the loop 提供单次 run 的执行状态机、Runner 协议归一、工具调用闭环与强类型 `EngineEvent stream`。
- Agent 与 Runner 都是 run-scoped 一次性对象：一次 `AgentRunRequest` 对应一次 Agent / Runner 生命周期；run 结束、失败、取消或挂起后，Engine 不复用旧实例。

## 接口

`dayu.engine` 的稳定调用入口是包根导出的函数式接口与强类型契约。调用方不直接实例化 Agent 或 Runner 实现类。

### 包根接口

包根 `dayu.engine` 导出两类符号：

- 真实执行入口：`run_agent_messages`、`run_agent_and_wait`。
- 契约类型：来自 `dayu.engine.contracts` 的 Engine 专属契约，以及来自 `dayu.contracts` 的跨层共享契约。

当前包根不导出私有 Agent 实现，不导出 OpenAI Runner 具体实现类，也不导出公共取消异常。

调用方可以从包根导入当前稳定接口：

```python
from dayu.engine import AgentRunRequest, EngineEvent, run_agent_messages
```

也可以从子包导入 Engine 专属契约：

```python
from dayu.engine.contracts import AgentRunRequest, RunnerSpec
```

跨层共享工具契约的定义真源在 `dayu.contracts`，包根 `dayu.engine` 仅把调用 Engine 所需的共享契约一并暴露出来，避免调用方在多个入口之间拼装基础类型。

### 执行入口

`run_agent_messages(request)` 运行一次 Agent，并返回 `EngineEvent stream`。这里的 stream 是本次 Engine run 的异步生成器，不是 Host event stream，也不携带 Host `event_sequence` cursor。

- 参数类型是 `AgentRunRequest`。
- 返回值是异步生成器。
- 每次调用都会创建本次 run 专属的 Agent 与 Runner；Engine 不复用旧 Agent / Runner，也不恢复旧实例。
- 调用方必须消费到生成器结束；如果提前停止消费，必须显式调用 `aclose()`，以触发 Runner 关闭和 run-scoped 资源收尾。
- `run_suspended` 或 `run_cancelled` 之后若要继续原目标，调用方需要构造新的 `AgentRunRequest`，把恢复输入、工具终态结果或用户意图显式放回 `messages`。
- Runner 构造失败时异常继续透传。

`run_agent_and_wait(request)` 运行一次 Agent，并完整消费 `run_agent_messages(request)` 的 `EngineEvent stream` 直到终态。

- 参数类型是 `AgentRunRequest`。
- 返回值类型是 `AgentRunResult`。
- `AgentRunResult` 是封闭联合，成员包括 `EngineRunOutcomeFinalAnswer`、`EngineRunOutcomeFailed`、`EngineRunOutcomeCancelled`、`EngineRunOutcomeSuspended`。
- Runner 构造失败时异常继续透传。

### AgentRunRequest

`AgentRunRequest` 是执行入口的唯一请求对象，字段包括：

- `run_id`：调用方传入的本次 run 标识；Engine 只随事件与工具执行上下文透传，不拥有 run 生命周期。
- `session_id`：调用方传入的 session 标识；Engine 只随事件与工具执行上下文透传，不拥有 session 生命周期。
- `messages`：进入本次 run 的非空 `AgentMessage` 元组；Engine 不使用自定义 byte 阈值拒绝 message，context 是否可处理由模型窗口、Runner / provider error path 与 Host Context Governance 收口。
- `disable_tools`：是否禁用工具调用。
- `runner_spec`：Runner 规约。
- `runner_options`：单次 Runner 调用参数。
- `agent_policy`：Agent 策略。
- `tool_schemas`：暴露给 LLM 的工具 schema 快照。
- `tool_executor`：工具执行协议实现。
- `cancellation_token`：取消观察 token；命中后阻止未来工作，并在取消赢得当前等待或调度边界时以 `run_cancelled` / `EngineRunOutcomeCancelled` 收口；已产出的事件事实不会被撤回。

Engine 消费这些字段完成单次 run；不从配置文件、调用方状态或 UI 状态中补读隐式参数。

### 事件接口

`EngineEvent` 是 Engine 对调用方暴露的事件对象，组成 `EngineEvent stream`。字段包括：

- `occurred_at`
- `session_id`
- `run_id`
- `type`
- `data`
- `metadata`

事件顺序由异步流产出顺序定义。EngineEvent 不提供事件序号、持久化 cursor、幂等键或 Host `event_sequence`；这些属于 Engine 外部调用方，尤其是 Host EventLog / Host event stream。`metadata` 只能承载中性 observer / debug hint，不承载契约事实。

`EngineEventType` 当前包括：

- `iteration_started`
- `content_delta`
- `reasoning_delta`
- `content_completed`
- `tool_call_delta`
- `tool_calls_batch_ready`
- `tool_call_requested`
- `tool_result_accepted`
- `tool_calls_batch_done`
- `tool_awaiting`
- `context_compaction_requested`
- `usage_reported`
- `provider_protocol_error`
- `iteration_completed`
- `final_answer`
- `run_suspended`
- `run_cancelled`
- `run_failed`

`TERMINAL_ENGINE_EVENT_TYPES` 是终态事件集合，当前包括 `final_answer`、`run_failed`、`run_cancelled`、`run_suspended`。

### Runner 接口

`AsyncRunner` 是 Engine 调用 LLM provider 的协议接口。它只负责把 provider 协议归一成 `RunnerEvent` 流，不执行工具，也不直接依赖 `ToolExecutor`。

`AsyncRunner` 当前定义三个方法：

- `call(messages, options, tools)`：发起一次 LLM 调用，返回 `RunnerEvent` 异步流。
- `is_supports_tool_calling()`：返回 Runner 是否支持工具调用。
- `close()`：关闭 Runner 并释放底层连接。

`RunnerSpec` 描述 Runner 规约，字段包括 provider、model、endpoint、api key 引用、headers、tool calling / streaming 能力、默认 timeout、最大重试次数、provider 请求扩展和 SSE idle 配置。`api_key_ref=None` 表示本地或免鉴权 provider 不需要 API key header。默认 timeout 必须为正数，最大重试次数必须为非负整数。

`RunnerCallOptions` 描述单次调用参数，字段包括 `temperature`、`max_tokens`、`top_p`、`stream`。

`RunnerSpec.provider_request` 是 `ProviderRequestExtension | None`，当前封闭联合成员包括 `OpenAIReasoningExtension`、`AnthropicThinkingExtension`、`DeepSeekThinkingExtension`、`MimoThinkingExtension`、`GeminiThinkingExtension`、`QwenThinkingExtension`。显式调用参数只进入 `RunnerCallOptions`，不放进 provider 扩展。

`dayu.engine.provider_extensions.provider_request_extension_from_json(value)` 是配置 DSL 到 `ProviderRequestExtension` 的 Engine 边界 helper。它支持 `openai_reasoning`、`anthropic_thinking`、`deepseek_thinking`、`mimo_thinking`、`gemini_thinking`、`qwen_thinking` 六类 DSL；未知 `type`、未知字段、非法枚举值或契约拒绝的字段组合都会以 `ProviderExtensionConfigError` fail closed。该 helper 不在包根 re-export，调用方应显式从子模块导入。

OpenAI-compatible Runner 会在内部执行 streaming capability：当 `RunnerCallOptions.stream=True` 但 `RunnerSpec.supports_streaming=False` 时，本次请求降级为 `stream=False`，且不写 `stream_options`。`RunnerSpec.supports_stream_usage` 只门控流式请求中是否写入 `stream_options.include_usage=True`；为 `False` 时不写该字段。`stream_idle_timeout_seconds` 与 `stream_idle_heartbeat_seconds` 是 SSE 字节空闲检测配置：heartbeat 只能在 timeout 已启用时设置，二者必须为正数，且 heartbeat 不能大于 timeout。

Engine / Runner 的可观测日志遵循 `dayu/README.md` 的级别语义。Agent 在 `VERBOSE` 记录 run、iteration、tool loop、fallback / continuation 与 terminal 骨架；OpenAI-compatible Runner 在 `VERBOSE` 记录单次 provider call start / done / cancelled 摘要，在 `DEBUG` 记录 HTTP attempt、response status、finish reason、usage、SSE heartbeat 与协议细节，在 `WARN` 记录 provider retry、协议差异和可恢复传输异常。Engine / Runner 日志不输出完整 prompt、provider headers、API key、完整工具结果或大段响应。

### 消息与工具接口

Engine 消费的消息类型来自 `AgentMessage` 封闭联合，当前包括：

- `SystemMessage`
- `UserMessage`
- `AssistantMessage`
- `ToolMessage`

工具执行通过 `ToolExecutor.execute(request)` 完成。Engine 只依赖 `ToolExecutor` 协议、`ToolSchema` 快照、`BatchToolExecutionRequest`、`BatchToolExecutionOutcome` 与 `ToolExecutionOutcome`；工具发现、权限、审计、路由和持久化不属于 Engine 接口。

工具声明与工具执行治理的整体边界见 [dayu/README.md 的“工具定义与执行边界”](../README.md#工具定义与执行边界)。`@tool(...)`、`ToolDefinition` 与 `ToolCallable` 属于 Host / ToolRuntime 装配输入；Engine 不消费这些对象，只接收调用方传入的 `tool_schemas` 与 `tool_executor`。

### 非接口

以下符号或能力不是 `dayu.engine` 当前稳定接口：

- 私有 Agent 实现。
- OpenAI Runner 具体实现类。
- Runner close 的内部实现。
- Engine 私有错误码常量。
- 取消异常类型。
- 上层 session / run 生命周期治理。
- 工具注册、工具权限、工具运行时治理。
- trace store、transcript、conversation memory。
- 财报文档存取或财报业务规则。

## 公共契约

Engine 公共契约分为 Engine 专属契约与跨层共享契约。Engine 专属契约位于 `dayu.engine.contracts`；工具、JSON 值、取消 token 等共享契约位于 `dayu.contracts`。

- `AgentRunRequest`：单次 run 的输入快照。形状包含 `run_id`、`session_id`、非空 `messages`、`disable_tools`、`runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor`、`cancellation_token`。
- `AgentPolicy`：Agent loop 策略。形状包含 iteration 预算、续写预算、工具开关、工具握手 timeout、fallback 模式、fallback prompt、continuation prompt 与连续失败工具批次阈值。
- `RunnerSpec`：Runner 规约。形状包含 provider、model、endpoint、可为空的 api key 引用、headers、tool calling / streaming 能力、stream usage 能力、默认 timeout、重试次数、provider 请求扩展、SSE idle timeout 与 heartbeat。
- `RunnerCallOptions`：单次 Runner 调用参数。形状包含 `temperature`、`max_tokens`、`top_p`、`stream`。
- `ProviderRequestExtension`：provider 私有请求扩展的封闭联合。当前成员包括 `OpenAIReasoningExtension`、`AnthropicThinkingExtension`、`DeepSeekThinkingExtension`、`MimoThinkingExtension`、`GeminiThinkingExtension`、`QwenThinkingExtension`。
- `AsyncRunner`：Engine 调用 LLM provider 的协议。形状包含 `call(messages, options, tools)`、`is_supports_tool_calling()`、`close()`。
- `RunnerEvent`：Runner 到 Agent 的协议归一事件。形状包含 `type`、`data`、`occurred_at`；不包含 `session_id` 或 `run_id`。
- `EngineEvent`：Engine 对调用方暴露的事件。形状包含 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata`。
- `EngineEventData`：Engine 事件 data 封闭联合。每个 `EngineEventType` 对应一个明确 data dataclass。
- `AgentRunResult`：`run_agent_and_wait` 的终态返回联合。成员包括 `EngineRunOutcomeFinalAnswer`、`EngineRunOutcomeFailed`、`EngineRunOutcomeCancelled`、`EngineRunOutcomeSuspended`。
- `tool_schemas`：本次 run 暴露给模型的工具 schema 快照。形状是 `tuple[ToolSchema, ...]`。
- `tool_executor`：工具执行协议 handle。形状是 `ToolExecutor.execute(BatchToolExecutionRequest) -> BatchToolExecutionOutcome`。
- `BatchToolExecutionRequest`：批式工具执行请求。形状包含 `calls: tuple[ToolCallRequest, ...]` 与 `context: BatchToolExecutionContext`。
- `BatchToolExecutionContext`：批式工具执行上下文。形状包含非空 `run_id`、`session_id`、`iteration_id`、`timeout_seconds`、`cancellation_token`、`correlation_id`。
- `ToolExecutionOutcome`：单工具执行结果封闭联合。成员包括 `ToolCompletedOutcome`、`ToolFailedOutcome`、`ToolAwaitingOutcome`、`ToolCancelledOutcome`。
- `BatchToolExecutionOutcome`：批式工具执行结果。形状包含 `records: tuple[BatchToolExecutionRecord, ...]`，构造期要求 record 的 tool call id 非空且不重复；与输入 calls 的完整双射由 Engine 校验。
- `ToolAwaitingOutcome`：长事务等待结果。形状包含 `await_spec: ToolAwaitSpec` 与 `snapshot: ToolAwaitSnapshot | None`。
- `cancellation_token`：Engine 可观察的取消入口。形状是 `CancellationToken`，包含 `is_cancelled()`、`cancel_reason()`、`requested_at()`。
- `RunnerHTTPErrorCode`：Runner HTTP / 网络 / 超时错误枚举。成员包括 `rate_limit_exceeded`、`server_error`、`client_error`、`network_error`、`timeout`、`context_length_exceeded`、`unknown_http_status`。
- `provider_request_id`：provider response 关联标识。形状是 `str | None`，出现在 `RunnerHTTPErrorData`、`RunnerProtocolErrorData`、`RunnerDoneData`、`IterationCompletedData`、`ProviderProtocolErrorData`、`ContextCompactionRequestedData` 与 `RunFailedData`。
- `raw_payload`：Runner / Provider 诊断事件上的可选诊断 JSON。该字段是有界、脱敏、摘要化的诊断载荷，不保证保留 provider 原始 payload；核心错误事实仍通过 `message`、`error_code`、`provider_request_id` 等强类型字段表达。

## 架构

Engine 内部按 contracts、Agent 协调层与 runners 分工：

- contracts 定义 `AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`RunnerEvent`、`AsyncRunner`、`RunnerSpec`、`RunnerCallOptions` 等公共类型。
- Agent 协调层消费 `AgentRunRequest`，组织单次 run 内的 LLM 迭代、RunnerEvent 提升、工具执行、终态判定和资源收尾。
- runners 提供 `AsyncRunner` 的具体实现，把 provider 协议、SSE / 非流式响应、HTTP / 网络错误归一为 RunnerEvent。

RunnerEvent 与 EngineEvent 是两层事件。RunnerEvent 不含 `session_id` / `run_id`，不直接暴露给 Engine 调用方；EngineEvent 在提升阶段补齐调用方关联字段，并把 Runner 的 provider 事件、工具执行结果和 run 终态投影为 Engine 公共事件。

## 边界

Engine 位于 `UI -> Service -> Host -> Engine` 链路最下游，只负责执行单次 Agent run 所需的协议归一、工具调用编排、`EngineEvent stream` 和终态结果。

Engine 不负责：

- 工具注册、工具权限、工具路由、工具审计和工具运行时治理。
- run / session 生命周期治理、调度策略、重试编排和上层取消来源管理。
- 事件持久化、trace store、transcript、conversation memory 和去重索引。
- 财报文档存取、财报业务规则和仓储选择。
- UI / Service / Host 的状态机、恢复策略或展示策略。

Engine 可以透传 `session_id`、`run_id`、provider request id、工具调用 id 等契约字段，但不规定这些标识的生成、持久化或去重方式。

Stream 术语边界：

- `EngineEvent stream`：`run_agent_messages(request)` 产出的本次 run 异步事件流。它是调用方 ingest 的输入来源，不是 durable truth。
- `RunnerEvent stream`：Runner 到 Agent 的 provider 协议归一事件流，只在 Engine 内部消费，不直接暴露给 Engine 调用方。
- `SSE stream` / provider streaming：Runner 与 provider 之间的传输能力，由 `RunnerCallOptions.stream`、`RunnerSpec.supports_streaming`、`supports_stream_usage` 和 SSE idle 配置控制。
- `Host event stream`：Host 从 EventLog `event_sequence` cursor 派生的订阅 / 补读流，不属于 Engine 能力面。
- `content_delta`、`reasoning_delta`、`tool_call_delta` 是 EngineEvent / RunnerEvent 的增量事件；是否进入 Host preview、canonical EventLog、memory 或 audit，由 Host ingest 与治理策略决定。

## 执行路径

```text
run_agent_messages(request)
  -> create run-scoped Runner from request.runner_spec
  -> create run-scoped Agent from request + Runner
      -> Agent.run_messages
      -> observe cancellation_token before work
      -> validate agent_policy.max_iterations >= 1
      -> emit EngineEvent.iteration_started
      -> run ordinary iterations within agent_policy.max_iterations
      -> compute effective tools from disable_tools / AgentPolicy / Runner capability
      -> AsyncRunner.call(messages, request.runner_options, effective_tools)
          -> RunnerEvent stream
              -> content_delta / reasoning_delta
              -> tool_call_delta
              -> content_completed
              -> tool_calls_batch_ready
              -> usage_reported
              -> provider_protocol_error
              -> context_compaction_requested
              -> iteration_completed
              -> after each consumed RunnerEvent, project accepted facts
              -> observe cancellation_token before future work
      -> if model requested tools
          -> emit EngineEvent.tool_call_requested
          -> ToolExecutor.execute(BatchToolExecutionRequest)
              -> BatchToolExecutionContext.timeout_seconds = agent_policy.tool_execution_timeout_seconds
              -> wait execute outcome with cancellation_token and handshake timeout
          -> if cancellation_token wins before outcome
              -> emit terminal EngineEvent.run_cancelled
          -> if handshake timeout wins before outcome
              -> cancel execute task
              -> emit terminal EngineEvent.run_failed(tool_execution_timeout)
          -> if completed / failed outcome
              -> emit EngineEvent.tool_result_accepted
              -> after every completed / failed outcome in the batch is accepted
                  -> emit EngineEvent.tool_calls_batch_done
              -> inject ToolMessage into run-local next-iteration messages
              -> if cancellation_token observed after accepted outcome
                  -> emit terminal EngineEvent.run_cancelled
              -> if all outcomes failed enough times
                  -> fallback by agent_policy.fallback_mode
              -> if max_iterations budget remains
                  -> continue next ordinary iteration
              -> if max_iterations exhausted
                  -> fallback by agent_policy.fallback_mode
          -> if awaiting outcome
              -> ToolExecutor returned batch outcome containing ToolAwaitingOutcome
              -> emit EngineEvent.tool_awaiting
              -> close Runner
              -> emit terminal EngineEvent.run_suspended
              -> late cancellation does not replace run_suspended
      -> if finish_reason is length
          -> append continuation_prompt while continuation and iteration budgets remain
          -> call Runner again with tools disabled
          -> merge continuation content into final answer
      -> if fallback_mode is FORCE_ANSWER
          -> observe cancellation_token before fallback Runner call
          -> append fallback_prompt to run-local messages
          -> AsyncRunner.call(messages, request.runner_options, tools=())
          -> emit EngineEvent.final_answer if content accepted
          -> emit EngineEvent.run_failed if force-answer is empty or still requests tools
      -> if fallback_mode is RAISE_ERROR
          -> emit EngineEvent.run_failed
      -> if final content accepted
          -> emit EngineEvent.final_answer
          -> close Runner
      -> if failure selected
          -> emit EngineEvent.run_failed
          -> close Runner
  -> EngineEvent stream
```

```text
run_agent_and_wait(request)
  -> consume run_agent_messages(request)
  -> keep last terminal EngineEvent
  -> map final_answer -> EngineRunOutcomeFinalAnswer
  -> map run_failed -> EngineRunOutcomeFailed
  -> map run_cancelled -> EngineRunOutcomeCancelled
  -> map run_suspended -> EngineRunOutcomeSuspended
  -> if EngineEvent stream ends without terminal -> EngineRunOutcomeFailed
```

## 状态机

当前 Engine run 可按以下抽象状态理解：

```text
CREATED
ITERATING
EXECUTING_TOOL
FORCE_ANSWER
FINAL_ANSWERED
FAILED
SUSPENDED
CANCELLED
```

状态迁移：

```text
CREATED -> ITERATING
CREATED -> FAILED
CREATED -> CANCELLED
ITERATING -> ITERATING
ITERATING -> EXECUTING_TOOL
ITERATING -> FINAL_ANSWERED
ITERATING -> FAILED
ITERATING -> CANCELLED
EXECUTING_TOOL -> ITERATING
EXECUTING_TOOL -> FORCE_ANSWER
EXECUTING_TOOL -> SUSPENDED
EXECUTING_TOOL -> FAILED
EXECUTING_TOOL -> CANCELLED
FORCE_ANSWER -> FINAL_ANSWERED
FORCE_ANSWER -> FAILED
FORCE_ANSWER -> CANCELLED
```

状态语义：

- `CREATED`：`run_agent_messages(request)` 已接收请求，但尚未开始普通 LLM iteration；如果取消 token 已命中或策略参数非法，可直接进入 terminal。
- `ITERATING`：Engine 已产出 `iteration_started`，正在消费一次 `AsyncRunner.call(...)` 的 `RunnerEvent` 流；普通迭代与 `finish_reason=length` continuation 都复用该状态，`iteration_completed` 只表示本轮 RunnerEvent 流结束，不是 run 终态。
- `EXECUTING_TOOL`：本轮 Runner 已完成工具调用请求，Engine 产出 `tool_call_requested`，并通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 等待工具 batch outcome。
- `FORCE_ANSWER`：普通工具 iteration 预算耗尽，或连续全失败工具批次达到阈值后，Engine 按 `AgentPolicy.fallback_mode=FORCE_ANSWER` 追加 `fallback_prompt`，禁用工具再调用一次 Runner；空回答或再次请求工具会收口为 `run_failed`。
- `FINAL_ANSWERED`：Engine 已产出 `final_answer`，对应 `EngineRunOutcomeFinalAnswer`。
- `FAILED`：Engine 已产出 `run_failed`，对应 `EngineRunOutcomeFailed`；provider protocol error、context overflow 后的 recoverable failure、重复工具调用 id、Runner 异常结束等都收口到该状态。
- `SUSPENDED`：Engine 已产出 `run_suspended`，对应 `EngineRunOutcomeSuspended`；当前来源是 ToolExecutor 返回 `ToolAwaitingOutcome`。
- `CANCELLED`：Engine 已观察到 `cancellation_token` 命中并产出 `run_cancelled`，对应 `EngineRunOutcomeCancelled`。

Terminal 事件集合由 `TERMINAL_ENGINE_EVENT_TYPES` 定义。进入 `FINAL_ANSWERED`、`FAILED`、`SUSPENDED` 或 `CANCELLED` 后，本次 run 不再继续产出普通事件。

## EngineEvent Stream

`EngineEventType` 当前公共事件名如下：

- `iteration_started`
- `content_delta`
- `reasoning_delta`
- `content_completed`
- `tool_call_delta`
- `tool_calls_batch_ready`
- `tool_call_requested`
- `tool_result_accepted`
- `tool_calls_batch_done`
- `tool_awaiting`
- `context_compaction_requested`
- `usage_reported`
- `provider_protocol_error`
- `iteration_completed`
- `final_answer`
- `run_suspended`
- `run_cancelled`
- `run_failed`

事件顺序由异步流实际产出顺序定义。EngineEvent 不提供单独的事件序号字段、持久化游标、幂等键或 Host `event_sequence`。调用方如果需要恢复、补读、多客户端 fanout、audit 或 memory，必须在 Engine 外部把 EngineEvent ingest 成自己的 durable facts。

RunnerEvent 层当前事件名如下：

- `runner_content_delta`
- `runner_reasoning_delta`
- `runner_tool_call_delta`
- `runner_tool_calls_completed`
- `runner_content_completed`
- `runner_usage_recorded`
- `provider_protocol_error`
- `runner_http_error`
- `runner_done`

Runner 的 `runner_done` 只表示本次 RunnerEvent 流结束；提升到 EngineEvent 后对应 `iteration_completed`，仍不等于 run 终态。

工具观测事件分三层：`tool_call_delta` 直接提升 Runner 的流式工具增量；`tool_calls_batch_ready` 表示 Agent 已接受 Runner 完成的本批工具调用，顺序与 Runner 完成顺序一致；`tool_calls_batch_done` 表示本批工具的 completed / failed outcome 已全部被 Engine 接受。`tool_call_requested` 仍表示 Agent 即将执行单个工具。`tool_calls_batch_done` 不是终态，不属于 `TERMINAL_ENGINE_EVENT_TYPES`。

当本批工具包含 `ToolAwaitingOutcome` 时，Engine 先逐个产出 accepted 工具的 `tool_result_accepted`，再为每个 awaiting 工具产出 `tool_awaiting`，随后直接以 `run_suspended` 收口；**不**产出 `tool_calls_batch_done`。换言之，`tool_calls_batch_done` 仅在本批不含 awaiting 时产出，作为 "本批 accepted outcome 已全部接受、可进入下一轮 Runner" 的信号；调用方依赖批处理完整性时必须同时识别 `tool_awaiting` + `run_suspended` 的 awaiting 路径。

HTTP 200 response 在 effective stream 为 `True` 且 `Content-Type` 为 `text/event-stream`、为空或不含 JSON 时按 SSE 解析；`Content-Type` 含 JSON 或 effective stream 为 `False` 时按非流式 JSON 解析。SSE 与非流式顶层 `error` object、SSE 既无有效 `choices` 也无有效 `usage` 的 chunk 会产出 `provider_protocol_error` 并以 `runner_done(error)` 收口；usage-only chunk 是合法统计 chunk。SSE 单行缓冲与单个 event 的 `data:` 行数有上限，超限会产出 `provider_protocol_error` 并以 `runner_done(error)` 收口。SSE `usage` 字段只承载附加 token 统计，字段格式错误会记录协议诊断日志并忽略该 usage，不终止后续 content / tool call 收口。SSE 与非流式响应遇到未知 provider `finish_reason` 时保留当前 `stop` 回落并记录 warning 诊断，避免 provider 协议变化被完全静默吞掉。

## 关键机制

取消 token 是 Engine 的取消收口。Agent 在迭代前、Runner 事件消费后、工具执行等待边界、工具结果注入后和下一轮工作开始前观察 token；工具执行通过 `dayu.runtime.cancellation.await_or_cancel_or_timeout` 把 token 与握手 timeout 纳入同一个 race。取消赢得当前边界时，公共结果以 `run_cancelled` 事件和 `EngineRunOutcomeCancelled` 表达。上层调用者要继续原目标时，需要用新的 `AgentRunRequest.messages` 显式提供已确认事实、用户意图或恢复输入。

工具执行协议以 `ToolSchema` 快照和 `ToolExecutor.execute` 为边界。Engine 把 Runner 完成的工具调用批次投影为 `BatchToolExecutionRequest`，其中包含本批 `ToolCallRequest`、run、session、iteration、批级 correlation 信息、取消 token 与工具握手 timeout；工具返回 completed / failed / cancelled outcome 后，Engine 先产出 `tool_result_accepted`，再将结果投影为 LLM 可消费的 tool message。若随后观察到取消，Engine 以 `run_cancelled` 收口，但不丢弃已接受的工具结果事实，也不进入下一轮 Runner。

工具握手 timeout 是 Engine 对 `ToolExecutor.execute` 的等待预算，不是外部长事务 timeout。`AgentPolicy.tool_execution_timeout_seconds` 是该预算真源；Engine 同时把它投影到 `BatchToolExecutionContext.timeout_seconds`，供 ToolExecutor 所在的工具执行环境协作设置内部等待边界。timeout 先于 outcome 命中时，runtime helper 取消 execute task，Engine 以不可恢复 `run_failed(tool_execution_timeout)` 收口。ToolExecutor 及其背后的工具执行环境负责协作响应取消，并治理可能已经启动的线程、子进程、HTTP 请求或远端 job。

`@tool(...)` 与 `ToolDefinition` 用于 Host / ToolRuntime 侧的工具声明和装配，不是 Engine 工具执行入口。Host / ToolRuntime 可以用 `@tool(...)` 获取 schema、truncate、display、tags 与单工具 `ToolCallable`，再用自身权限、审批、限流、并发、timeout、审计、awaiting、truncation cursor / scope_token 和 cleanup 策略包装出 batch `ToolExecutor`。Engine 不提供默认 `FunctionToolExecutor`，也不规定 batch 内部执行策略。

挂起 / 恢复协议以 `ToolAwaitingOutcome` 为边界。工具开始外部长事务并建议挂起时，ToolExecutor 返回 `await_spec` 与 `snapshot`；Engine 先产出 `tool_awaiting`，再以 `run_suspended` 收口并关闭 Runner。Engine 不等待外部长事务完成，不持久化等待记录，也不恢复旧 Agent/Runner 实例；上层调用者保存 `await_spec` / `snapshot`，等工具终态确定后构造新的 `AgentRunRequest`，把工具终态结果或恢复输入显式交回 Engine。

Engine 的取消提交边界是“阻止未来工作，不覆盖已接受事实”。已经提升的 RunnerEvent 事实、已经接受的普通工具结果、已经返回的 awaiting outcome 和已经接受的 final decision 都会按各自事实保留；取消只在尚未接受 outcome、下一轮 Runner、continuation、fallback 或工具批执行前抢占后续工作，工具批执行前命中取消时不会先登记本批 tool call id。上层调用者把自己的取消命令映射成 run-local token，把长事务映射成 `ToolAwaitingOutcome`，再用新 run 恢复，就能形成“宿主强约束下的 LLM in the loop”。

provider 协议错误与 HTTP / 网络错误分层处理。Runner 解析层错误产出 `provider_protocol_error`；HTTP、网络、超时和上下文超限产出 `runner_http_error`。其中上下文长度超限会被 Engine 提升为 `context_compaction_requested`，该事件在 provider overflow 路径中的 `budget_state` 为 `None`，并以可恢复失败候选收口；是否压缩、如何恢复、如何记录 Host budget 不属于 Engine。Engine 不做 proactive threshold compaction、compact / retry、provider-aware tokenizer 或 Host budget policy。

Runner close 是 run-scoped 收尾机制。`run_agent_messages` 在生成器结束或关闭时会触发 `EngineEvent stream` 关闭；Agent 也在终态路径和最终清理中按 once 语义关闭 Runner，普通 close 失败后不会重复 close 同一 Runner。普通 Runner close 失败只记录诊断，不改写已经确定的公共终态；close 被 asyncio cancellation 打断时透传取消，但仍释放私有 Agent 运行槽位。

`metadata` 是 EngineEvent 的中性 observer / debug hint 边界。契约事实必须进入强类型 data 字段，不得放进 metadata 让调用方解析。

## 扩展点

扩展 provider Runner 时，实现 `AsyncRunner`，把 provider 原生响应归一为 RunnerEvent，并保持工具执行、迭代决策和终态判定在 Agent 协调层。当前函数式入口通过私有默认装配点创建内置 OpenAI-compatible Runner；该私有装配点不是公共 factory、registry 或 runner 选择扩展点。

扩展 Engine 公共事件时，必须同步扩展 `EngineEventType`、对应 data dataclass、`EngineEventData` 封闭联合，以及 RunnerEvent 提升或 Agent 产出路径。

扩展 provider 请求参数时，优先进入 `RunnerSpec.provider_request` 的 provider extension；单次采样、输出长度、top-p 和流式开关进入 `RunnerCallOptions`。

扩展工具能力时，在 Host / ToolRuntime 侧使用 `@tool(...)` 或等价机制声明工具定义，将 `ToolSchema` 暴露给 Runner，并将受治理后的 `ToolExecutor` 提供给 Engine。Engine 不新增工具注册表，也不把工具部署位置、工具定义对象或 batch 内部执行策略写进 Engine 契约。
