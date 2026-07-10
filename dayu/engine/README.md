# Engine 开发手册

本文档是 `dayu.engine` 包的开发手册。

Engine 在整体架构中位置如下：

```text
UI -> Service -> Host -> Engine
```

## Agent更新约束【必须遵守】

- 本文档只写两类内容：
  - 当前代码已实现的整个 Agent 的设计意图、架构边界，范围包括 `UI -> Service -> Host -> Engine`。
  - 当前代码已实现的 `dayu.engine` package 的开发接口、公共契约、架构、稳定边界、主要组件、关键执行路径、状态机、事件流、关键机制、扩展点。
- 更新本文档时必须先核对 `dayu.engine` 当前代码；代码真源高于 `docs/engine/design.md`，设计文档只作为设计意图和术语边界参考。
- 必须按本文档现有章节职责写作：`设计意图` 和 `架构边界` 先说明整个 Agent 与 Engine 位置；其后章节只说明 `dayu.engine` package。
- 不写用户手册、安装运行命令、测试清单、文件级流水账或 review / work unit 过程状态。
- 不写未来计划、路线图、未落地能力或实现细节；只保留当前代码已经实现且对开发者稳定有用的说明。

## 设计意图

Dayu 是生产级通用 Agent，具备买方财报分析能力，核心范式是“宿主强约束下的 LLM in the loop”。

在整个 Agent 中，LLM 负责分析、推理和生成，但生命周期、取消、恢复、工具治理、事件事实、memory / context governance 与持久化事实由上层 Host 掌控。Engine 只执行单次 `AgentRunRequest`，将本次 run 内的模型调用、工具调用闭环、取消观察、provider 协议归一和终态收口表达为强类型 `EngineEvent stream` 或 `AgentRunResult`。

`dayu.engine` 的设计重点是把一次 Agent run 做成明确、可关闭、可恢复输入重建的执行边界：

- 每次 `run_agent_messages(request)` 都创建本次 run 专属的 Agent 与 Runner；run 结束、失败、取消、挂起或生成器关闭后，Engine 不复用旧实例。
- Engine 通过 `AsyncRunner` 调用模型 provider，并把 provider 原生响应归一为 `RunnerEvent`。
- Agent 协调层消费 `RunnerEvent`，产出调用方可见的 `EngineEvent`，并负责 iteration、tool loop、length continuation、fallback、取消和终态判定。
- 工具执行只通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 完成；Engine 不注册工具、不发现工具、不持有工具权限或审计策略。
- 长事务工具通过 `ToolAwaitingOutcome` 使本次 run 进入 `run_suspended`；Engine 不等待外部长事务完成，也不恢复旧 Agent / Runner。
- provider 上下文长度超限会被提升为 `context_compaction_requested`，随后以可恢复 `run_failed(context_compaction_required)` 收口；是否 compact、如何恢复由 Host 决定。
- 财报业务语义、ticker 归一、文档选择、XBRL 处理和财报文档仓储不属于 Engine；财报文档存取必须在 Engine 外部遵守 `dayu.fins.storage` 仓储边界。

## 架构边界

整体依赖方向固定为：

```text
UI -> Service -> Host -> Engine
```

- `UI` 负责展示、输入收集、流式订阅和用户动作触发。
- `Service` 负责业务入口、身份解析、配置装配和调用 Host。
- `Host` 负责 Session / Run / Attempt 生命周期、admission、dispatch、EventLog、ToolRuntime、wait-resume、memory / context governance 和恢复治理。
- `Engine` 负责单次 run 的模型交互、Runner 协议归一、tool loop、取消观察和 `EngineEvent stream`。

Engine 位于链路最下游。Host 可以调用 Engine public entry；Engine 不导入 Host，不读取 Host durable store，不管理 Session / Run / Attempt，不写 EventLog，也不拥有 wait record、memory snapshot、trace store 或 projection。

公共包边界固定如下：

- `dayu.contracts` 是 Dayu Agent 公共契约包，承载 UI / Service / Host / Engine / ToolRuntime / tools 可共同使用的层中立数据与协议，例如 JSON 值、取消 token、工具声明、工具 schema、工具调用请求、工具执行 outcome、工具等待 outcome 和 `ToolExecutor`；它不承载 Host / Engine 状态机，也不承载业务事实。
- `dayu.engine.contracts` 是 Engine 专属契约包，承载 Host 调用 Engine 所需的 `AgentRunRequest`、`AgentPolicy`、`EngineEvent`、`RunnerEvent`、`RunnerSpec`、`AsyncRunner` 等边界类型；它定义 Host -> Engine 的单次 run contract，不是 Agent 全局公共运行时。
- `dayu.runtime` 是层中立运行期基础设施包，提供取消等待、日志级别、诊断文本脱敏、截断、filelock、lane 等可复用 helper；它不得依赖 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`，也不承载任何层的状态机或业务语义。
- 工具声明契约属于 `dayu.contracts`；具体工具实现、工具发现、工具权限、工具运行时治理、截断治理、长事务监控和工具审计属于 Host / ToolRuntime、runtime discovery、Service assembly 或具体工具包。Engine 只接收调用方传入的 `tool_schemas` 与 `tool_executor`。

## 接口

`dayu.engine` 的稳定调用入口是包根导出的函数式接口与强类型契约。调用方不直接实例化私有 Agent 或具体 Runner 实现类。

包根 `dayu.engine` 导出：

- 执行入口：`run_agent_messages`、`run_agent_and_wait`。
- 调用 Engine 所需的 Engine 专属契约：来自 `dayu.engine.contracts`，包括 `RunnerSpec`、`ClientCorrelationPolicy`、`RunnerRequestIdentity` 与 `build_runner_request_identity`。
- 调用 Engine 必需的共享契约：来自 `dayu.contracts`，包括工具 schema、工具执行协议、工具 outcome、JSON 值与取消 token。

包根不导出 `_AsyncAgent`、`AsyncOpenAIRunner`、Runner close 内部实现、取消异常类型、工具注册表、ToolRuntime、trace store 或财报业务能力。

### `run_agent_messages`

`run_agent_messages(request)` 运行一次 Agent，并返回本次 run 的 `EngineEvent stream`。

- 参数类型是 `AgentRunRequest`。
- 返回值是异步生成器。
- 每次调用创建新的 run-scoped Agent 与 Runner。
- 调用方必须消费到生成器结束；如果提前停止消费，必须显式调用 `aclose()`，以触发 Runner 关闭和 run-scoped 资源收尾。
- `run_suspended` 或 `run_cancelled` 之后若要继续原目标，调用方需要构造新的 `AgentRunRequest`，把恢复输入、工具终态结果或用户意图显式放回 `messages`。
- Runner 构造失败时异常透传。

### `run_agent_and_wait`

`run_agent_and_wait(request)` 运行一次 Agent，完整消费 `run_agent_messages(request)` 的 `EngineEvent stream`，并返回 `AgentRunResult`。

`AgentRunResult` 是封闭联合，成员包括：

- `EngineRunOutcomeFinalAnswer`
- `EngineRunOutcomeFailed`
- `EngineRunOutcomeCancelled`
- `EngineRunOutcomeSuspended`

若 `EngineEvent stream` 未产出终态就结束，聚合入口返回 `EngineRunOutcomeFailed(error_code="missing_terminal")`。

### `AgentRunRequest`

`AgentRunRequest` 是执行入口的唯一请求对象，字段包括：

- `run_id`：调用方传入的本次 run 标识；Engine 随事件和工具执行上下文透传，不拥有 run 生命周期。
- `session_id`：调用方传入的 session 标识；Engine 随事件和工具执行上下文透传，不拥有 session 生命周期。
- `messages`：进入本次 run 的非空 `AgentMessage` 元组；构造期要求非空。
- `disable_tools`：本次 run 是否禁用工具。
- `runner_spec`：Runner 规约。
- `runner_options`：单次 Runner 调用参数。
- `agent_policy`：Agent loop 策略。
- `tool_schemas`：本次 run 暴露给 LLM 的工具 schema 快照。
- `tool_executor`：工具执行协议 handle。
- `cancellation_token`：取消观察 token。
- `attempt_id` / `execution_id`：Host attempt / execution 标识；直接 Engine 或非 attempt 路径为 `None`，构造期要求二者同时为空或同时非空。

Engine 只消费请求中显式传入的事实，不从配置文件、调用方状态、Host store 或 UI 状态补读隐式参数。

## 调用者装配示例

Engine 的稳定入口是单次 `AgentRunRequest`。直接调用 Engine 的调用方通常是 Host worker、底层测试或专门执行适配层；普通 Service 不应绕过 Host 直接驱动多轮 Agent。

### Event stream caller

调用方必须先完成 Runner、tool executor、tool schema、取消 token 和 policy 的 typed 装配，再把完整快照传给 `run_agent_messages(request)`：

```python
from dayu.engine import (
    AgentMessageRole,
    AgentRunRequest,
    UserMessage,
    run_agent_messages,
)

request = AgentRunRequest(
    run_id=run_id,
    session_id=session_id,
    messages=(
        UserMessage(role=AgentMessageRole.USER, content=user_prompt),
    ),
    disable_tools=False,
    runner_spec=runner_spec,
    runner_options=runner_options,
    agent_policy=agent_policy,
    tool_schemas=tool_schemas,
    tool_executor=tool_executor,
    cancellation_token=cancellation_token,
    attempt_id=attempt_id,
    execution_id=execution_id,
)

async for event in run_agent_messages(request):
    # Host worker 在这里把 EngineEvent 写入 EventLog / projection；
    # 直接调用方则写入自己的 observer 或测试断言。
    ...
```

示例中的 `...` 是调用方自己的消费逻辑，不是 Engine API。`runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor` 与 `cancellation_token` 都是调用方已经装配好的 typed value。Engine 不根据 `run_id` / `session_id` 回查 Host state，也不从配置文件补读 runner 或工具信息。

### Aggregate caller

需要一次性获得终态结果时，调用方可以完整消费 Engine event stream：

```python
from dayu.engine import run_agent_and_wait

outcome = await run_agent_and_wait(request)
```

`run_agent_and_wait(request)` 只做本次 run 的聚合收口；它不会创建 Session、不会恢复 waiting Run，也不会把 terminal 写入 Host EventLog。

## 公共契约

Engine 公共契约分为 Engine 专属契约与 Dayu Agent 公共契约。

### Engine 专属契约

- `AgentRunRequest`：单次 run 的完整输入快照。
- `AgentPolicy`：Agent loop 策略，包含 iteration 预算、continuation 预算、工具开关、工具握手 timeout、fallback 模式、fallback prompt、continuation prompt 与连续失败工具批次阈值。`fallback_prompt` 与 `continuation_prompt` 是调用方已经解析好的必填文本；Engine 不提供 LLM-facing prompt 默认值。
- `AgentRunResult`：`run_agent_and_wait` 的终态返回封闭联合。
- `AgentMessage`：Runner 输入消息封闭联合，成员包括 `SystemMessage`、`UserMessage`、`AssistantMessage`、`ToolMessage`。
- `AssistantToolCall`：assistant 消息中的工具调用记录，保留 `provider_state` 以支持 provider roundtrip。
- `EngineEvent`：Engine 对调用方暴露的公共事件，字段包括 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata`。
- `EngineEventData`：Engine 事件 data 封闭联合，每个 `EngineEventType` 对应明确 data dataclass。
- `RunnerEvent`：Runner 到 Agent 的协议归一事件，不含 `session_id` / `run_id`。
- `AsyncRunner`：Engine 调用模型 provider 的协议，定义 `call(...)`、`is_supports_tool_calling()`、`close()`。
- `RunnerSpec`：Runner 规约，包含 provider、model、endpoint、API key 引用、headers、client correlation policy、tool / stream capability、timeout、retry、provider 请求扩展、SSE idle 配置。
- `RunnerCallOptions`：单次 Runner 调用参数，包含 `temperature`、`max_tokens`、`top_p`、`stream`。
- `RunnerRequestIdentity`：单次逻辑 Runner 调用身份，包含 `run_id`、可选且成对出现的 `attempt_id` / `execution_id`、`iteration_id`、`iteration_index`、`runner_call_index` 和派生 `client_correlation_id`。
- `ProviderRequestExtension`：provider 请求扩展封闭联合，当前成员包括 OpenAI reasoning、Anthropic thinking、DeepSeek thinking、MiMo thinking、Gemini thinking、Qwen thinking。
- `ClientCorrelationPolicy`：客户端关联 id 的 provider 协议 outbound 映射策略，当前支持 `DISABLED` 与 `OPENAI_X_CLIENT_REQUEST_ID`。

### Dayu Agent 公共契约

这些契约定义真源在 `dayu.contracts`，由 Host / Engine / ToolRuntime 等层共同使用；Engine 只消费或透传，不拥有其治理语义。

- `ToolSchema`：本次 run 暴露给模型的工具 schema 快照。
- `ToolExecutor`：工具执行协议，形状是 `execute(BatchToolExecutionRequest) -> BatchToolExecutionOutcome`。
- `BatchToolExecutionRequest`：批式工具执行请求，包含 `calls` 与 `context`。
- `BatchToolExecutionContext`：批式工具执行上下文，包含 `run_id`、`session_id`、`iteration_id`、`timeout_seconds`、`cancellation_token`、`correlation_id`。
- `ToolCallRequest`：单个工具调用请求，包含 tool call id、工具名称、参数、iteration 内序号和 provider state。
- `ToolExecutionOutcome`：单工具执行结果封闭联合，成员包括 completed、failed、awaiting、cancelled。
- `BatchToolExecutionOutcome`：批式工具执行结果；Engine 校验返回记录与输入 calls 的 tool call id 严格双射。
- `ToolAwaitingOutcome`：长事务等待结果，包含 `await_spec` 与可选 `snapshot`。
- `CancellationToken`：Engine 可观察的取消入口。
- `JsonValue`：公共 JSON 值类型。

## 架构

`dayu.engine` 内部按 contracts、Agent 协调层、Runner 实现和 provider extension helper 分工。

```text
dayu.engine
├── __init__.py                 # 包根稳定导出
├── agent.py                    # run-scoped Agent 状态机与函数式入口
├── _default_runner.py          # 当前私有默认 Runner 装配点
├── provider_extensions.py      # provider_request JSON DSL -> typed contract
├── contracts/                  # Engine 专属契约
└── runners/openai/             # OpenAI-compatible AsyncRunner 实现
```

- `contracts/` 定义 Engine 专属 dataclass、enum、Protocol 和封闭联合。
- `agent.py` 消费 `AgentRunRequest`，组织单次 run 内的 LLM iteration、RunnerEvent 提升、工具执行、length continuation、fallback、取消与终态收口。
- `_default_runner.py` 根据 `AgentRunRequest.runner_spec` 构造当前内置 OpenAI-compatible Runner；它是私有默认实现细节，不是公共 factory、registry 或扩展点。
- `provider_extensions.py` 把配置层保留的 JSON DSL 转成 `ProviderRequestExtension`；未知 type、未知字段、非法枚举值或契约拒绝的字段组合都会 fail closed。
- `runners/openai/` 实现 OpenAI-compatible `AsyncRunner`，负责请求 payload 构建、HTTP 调用、SSE / 非流式解析、usage 归一、provider protocol / HTTP error 归一、retry、client correlation header 映射和 close。

## 稳定边界

Engine 稳定边界是单次 `AgentRunRequest`。一次 run 内的消息列表、iteration 状态、已执行 tool call id、连续失败工具批次计数、continuation 状态、Runner HTTP session 和 provider stream 都是 run-scoped 内部状态。

Engine 不负责：

- Session / Run / Attempt 生命周期治理、admission、dispatch、retry 编排和 startup recovery。
- EventLog 持久化、Host event stream、trace store、transcript、conversation memory、projection 或去重索引。
- 工具注册、工具发现、工具权限、审批、限流、审计、截断治理、后台任务治理、长事务监控或恢复调度。
- 配置解析、prompt 渲染、用户身份、UI 展示或 Service 业务流程。
- 财报业务语义、ticker 归一、文档选择、章节规则、XBRL 处理或财报文档仓储访问。

Stream 术语固定如下：

- `EngineEvent stream`：`run_agent_messages(request)` 产出的本次 run 异步事件流，是调用方 ingest 的输入，不是 durable truth。
- `RunnerEvent stream`：Runner 到 Agent 的 provider 协议归一事件流，只在 Engine 内部消费。
- `SSE stream` / provider streaming：Runner 与 provider 之间的传输能力，由 `RunnerCallOptions.stream`、`RunnerSpec.supports_streaming`、`supports_stream_usage` 和 SSE idle 配置控制。
- `Host event stream`：Host 从 EventLog `event_sequence` cursor 派生的订阅 / 补读流，不属于 Engine 能力面。

`EngineEvent.metadata` 只是中性 observer / debug hint。契约事实必须进入强类型 `data` 字段，不得放进 metadata 让调用方解析。

## 主要组件

### Agent 协调层

私有 `_AsyncAgent` 是单次 run 的状态机实现。它负责：

- 校验运行槽位，防止同一 Agent 实例并发复用。
- 产出 `iteration_started` 并构造每次逻辑 Runner 调用的 `RunnerRequestIdentity`。
- 消费 RunnerEvent，提升为 EngineEvent 或 run decision。
- 根据 final answer、tool calls、provider failure、context overflow、continuation 和 fallback 选择下一步。
- 通过 `ToolExecutor` 执行工具批次，并处理 completed / failed / cancelled / awaiting outcome。
- 在终态路径和生成器关闭路径幂等关闭 Runner。

### Runner 协议与 OpenAI-compatible Runner

`AsyncRunner` 是 Engine 对模型 provider 的唯一抽象。Runner 只负责把 provider 协议归一为 RunnerEvent，不执行工具，不管理 iteration，不补齐 `session_id` / `run_id`。

当前默认实现是 OpenAI-compatible Runner：

- 根据 `RunnerSpec` 与 `RunnerCallOptions` 构造 chat completion payload。
- 当 `RunnerCallOptions.stream=True` 但 `RunnerSpec.supports_streaming=False` 时降级为非流式请求。
- 只有在 effective stream 为 `True` 且 HTTP 200 response 的 media type 是 `text/event-stream` 时按 SSE 解析；流式请求缺失 `Content-Type` 时保留 SSE fallback 并记录诊断；其它 media type 按非流式 JSON 解析。
- `supports_stream_usage=True` 时，流式请求写入 `stream_options.include_usage=True`；否则不写该字段。
- SSE 与非流式响应都在 OpenAI-compatible Runner adapter 边界校验 `choices` 与 `finish_reason`：多 assistant choice、显式非零 choice index、非法 choice shape、未知或非法 `finish_reason` 都按 provider protocol error fail closed；`finish_reason` 缺失或 `null` 只表示 absent，不会默认成 `stop`。
- 按 `RunnerSpec.max_retries`、HTTP 分类、网络异常、timeout 和 `Retry-After` 执行重试；若一次 attempt 已经产出事件，后续 retriable failure 不再重试，而是以 error 收口。
- 取消 token 命中时 Runner 生成器自然结束，不补 `RunnerDoneData`。

### Provider 请求扩展

`ProviderRequestExtension` 用封闭联合表达 provider 私有请求扩展。payload builder 以穷尽匹配把不同扩展投影到对应 provider 字段；显式调用参数 `temperature`、`max_tokens`、`top_p`、`stream` 只来自 `RunnerCallOptions`，不放进 provider extension。

Engine 对外暴露 provider-neutral 的 `reasoning_delta` 与 `reasoning_content`。OpenAI-compatible Runner 会把原生 `reasoning_content` 字段，以及 Gemini `include_thoughts` 路径中 `content` 内的 `<thought>...</thought>` 标签文本，统一归一到该契约；标签外文本继续作为正文。

Provider roundtrip 分两条独立通道：`AssistantMessage.reasoning_content` 非空时回写到 outbound assistant message 的 `reasoning_content` 字段；Gemini tool-call `extra_content.google.thought_signature` 则解析为 `GeminiToolCallState`，经 `AssistantToolCall.provider_state` 保留，并在 outbound tool call 中回写到 `extra_content.google.thought_signature`。前者是 reasoning 文本，后者是 Gemini tool-call 续航签名，二者不能互相替代。

### 工具执行边界

Engine 只依赖 `ToolExecutor` batch 协议。`@tool(...)`、`ToolDefinition`、`ToolCallable`、工具权限、工具审计、工具内部 timeout、awaiting 监控和 cleanup 都属于 Engine 外部。Host / ToolRuntime 负责把受治理的工具集合包装成 `ToolExecutor`，再连同 `ToolSchema` 快照传给 Engine。

## 关键执行路径

### 普通 run

```text
run_agent_messages(request)
  -> build run-scoped Runner from request.runner_spec
  -> create run-scoped Agent
  -> observe cancellation before work
  -> for each iteration within AgentPolicy.max_iterations
      -> emit iteration_started
      -> compute effective tools from disable_tools / AgentPolicy / Runner capability
      -> build RunnerRequestIdentity
      -> AsyncRunner.call(messages, runner_options, tools, request_identity=identity)
      -> consume RunnerEvent stream
      -> emit content / reasoning / usage / provider diagnostic / iteration events
      -> classify as final answer, tool calls, failure, or context compaction request
  -> emit one terminal event
  -> close Runner once
```

### 工具调用

```text
Runner tool calls completed
  -> sort tool calls by index_in_iteration
  -> reject duplicate tool_call_id within this run
  -> emit tool_calls_batch_ready
  -> emit tool_call_requested for each call
  -> ToolExecutor.execute(BatchToolExecutionRequest)
      -> context.timeout_seconds = AgentPolicy.tool_execution_timeout_seconds
      -> wait with cancellation_token and handshake timeout
  -> validate returned records are a bijection with input tool calls
  -> emit tool_result_accepted for completed / failed / cancelled outcomes
  -> if no awaiting outcome
      -> emit tool_calls_batch_done
      -> inject assistant tool_calls and tool messages into run-local messages
      -> continue next iteration or fallback
  -> if any awaiting outcome
      -> emit tool_awaiting
      -> emit run_suspended
```

### Length continuation

当 final candidate 的 `finish_reason` 为 `LENGTH` 时，表示本次生成达到模型输出上限，例如 `max_tokens`、`max_output_tokens`、`max_completion_tokens` 或 provider 的最大输出 token cap；它不是输入上下文窗口溢出，不触发 `context_compaction_requested`。Agent 在 continuation 预算和 iteration 预算仍可用时：

- 保存当前回答片段。
- 将片段作为 assistant message 注入 run-local messages。
- 追加 `AgentPolicy.continuation_prompt` 作为 user message。
- 下一轮禁用工具继续调用 Runner。

续写轮再次产生工具调用时，Engine 以 `run_failed(continuation_tool_call_not_allowed)` 收口。续写预算耗尽时，Engine 合并已获得片段，以 `degraded=True` 的 `final_answer` 收口。

### Fallback

工具轮次耗尽或连续全失败工具批次达到阈值后，Agent 按 `AgentPolicy.fallback_mode` 收口：

- `RAISE_ERROR`：直接产出 `run_failed`。
- `FORCE_ANSWER`：追加 `fallback_prompt`，禁用工具再调用一次 Runner；成功得到最终回答时标记 `degraded=True`。

force-answer Runner 调用前会观察取消；一旦 final content 已被接受，迟到取消不改写 final answer。

### Suspend / resume

当前 run suspension 的唯一来源是 `ToolExecutor.execute` 返回的 batch outcome 中包含至少一个 `ToolAwaitingOutcome`。

Engine 在 suspended terminal 中携带：

- 本批已 accepted 的 completed / failed / cancelled 工具记录。
- 本批 awaiting 工具记录。
- 当前 assistant tool call batch snapshot。

Engine 不恢复旧 Agent / Runner。上层调用方需要保存等待信息，在外部长事务完成后构造新的 `AgentRunRequest`，把工具终态结果或恢复输入显式放回 `messages`。

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

主要迁移：

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

- `CREATED`：请求已进入 Engine，但尚未开始普通 Runner iteration。
- `ITERATING`：Engine 正在消费一次 RunnerEvent stream；普通 iteration 和 continuation 都使用该状态。
- `EXECUTING_TOOL`：Engine 正在等待一次 `ToolExecutor.execute` batch handshake。
- `FORCE_ANSWER`：Engine 禁用工具执行一次 fallback Runner 调用。
- `FINAL_ANSWERED`：Engine 已产出 `final_answer`。
- `FAILED`：Engine 已产出 `run_failed`。
- `SUSPENDED`：Engine 已产出 `run_suspended`。
- `CANCELLED`：Engine 已产出 `run_cancelled`。

Terminal 事件集合由 `TERMINAL_ENGINE_EVENT_TYPES` 定义，当前包括 `final_answer`、`run_failed`、`run_cancelled`、`run_suspended`。进入 terminal 后，本次 run 不再继续产出普通事件。

## 事件流

`EngineEvent stream` 的事件顺序由异步流实际产出顺序定义。EngineEvent 不提供事件序号、持久化 cursor、幂等键或 Host `event_sequence`。调用方如果需要恢复、补读、多客户端 fanout、audit 或 memory，必须在 Engine 外部把 EngineEvent ingest 成自己的 durable facts。

当前 `EngineEventType` 包括：

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
- `provider_diagnostic`
- `provider_protocol_error`
- `iteration_completed`
- `final_answer`
- `run_suspended`
- `run_cancelled`
- `run_failed`

`RunnerEventType` 包括：

- `runner_content_delta`
- `runner_reasoning_delta`
- `runner_tool_call_delta`
- `runner_tool_calls_completed`
- `runner_content_completed`
- `runner_usage_recorded`
- `provider_diagnostic`
- `provider_protocol_error`
- `runner_http_error`
- `runner_done`

Runner 的 `runner_done` 只表示本次 RunnerEvent stream 结束；提升到 EngineEvent 后对应 `iteration_completed`，不等于 run 终态。

工具事件有固定分层：

- `tool_call_delta`：直接提升 Runner 的流式工具调用增量。
- `tool_calls_batch_ready`：Agent 已接受 Runner 完成的本批工具调用，顺序为按 `index_in_iteration` 排序后的执行输入顺序。
- `tool_call_requested`：Agent 即将执行单个工具调用。
- `tool_result_accepted`：completed / failed / cancelled 工具 outcome 已进入 Engine 接受边界。
- `tool_calls_batch_done`：本批不含 awaiting 时，accepted outcome 已全部接受，可进入下一轮 Runner。
- `tool_awaiting` + `run_suspended`：本批包含 awaiting outcome 时的挂起路径；该路径不产出 `tool_calls_batch_done`。

`iteration_started` 携带 Engine 对本次真实 Runner 输入的直接观察：`message_count`、按实际 message role 顺序计算的 `role_sequence_digest`、`runner_input_serializer_schema_version`，以及 `input_projection`。`input_projection` 是按实际 Runner 输入顺序排列的中性 LLM-facing message projection，包含 message `index`、`role`、`content` / tool call id、assistant tool call 名称和参数；它不包含 Host-owned runner call index、manifest ref、source refs、memory / compact refs、tool schema refs、provider headers、Authorization/API key 或 provider raw request/response。

## 关键机制

### 取消提交边界

取消 token 的语义是阻止未来工作，不撤回已接受事实。Agent 在迭代前、Runner 事件消费后、工具执行等待边界、工具结果注入后和下一轮工作开始前观察 token。取消赢得当前边界时，Engine 以 `run_cancelled` 与 `EngineRunOutcomeCancelled` 收口。

已经提升的 RunnerEvent、已经 accepted 的普通工具结果、已经返回的 awaiting outcome 和已经接受的 final decision 不会被迟到取消改写。

### 工具握手 timeout

`AgentPolicy.tool_execution_timeout_seconds` 是 Engine 等待 `ToolExecutor.execute` 的握手 timeout 真源。Engine 同时把该值投影到 `BatchToolExecutionContext.timeout_seconds`。timeout 先于 outcome 命中时，runtime helper 会取消 execute await task，Engine 以不可恢复 `run_failed(tool_execution_timeout)` 收口。

该 timeout 只表示 Engine 不再等待 batch handshake outcome；不证明工具内部线程、子进程、HTTP 请求或远端 job 已停止。

### Provider 错误

Runner 解析层 fatal 错误产出 `provider_protocol_error`；非致命 provider / adapter 诊断产出 `provider_diagnostic`，例如未知 provider tool-call 扩展字段、malformed usage、HTTP 200 缺失 `Content-Type` 或 context overflow marker fallback provenance。`provider_diagnostic` 不设置 Agent 失败候选，不代表 run failure。HTTP、网络、timeout 和上下文超限产出 `runner_http_error`。`RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 是 Dayu 的中性错误分类，不是 provider 官方错误码，也不对应固定 HTTP 状态码。OpenAI-compatible Runner 只在 HTTP 失败响应中识别到明确的上下文溢出信号时才归一为该分类：

- 结构化 payload 的 `error.code == "context_length_exceeded"`。
- 错误文本命中受控 marker，例如 `maximum context length is`、`total message token length exceed model limit`、`range of input length should be`、`model's maximum context length`、`model requires more context` 或 `context length exceeded`。

普通 `400` 参数错误、限流、认证错误或 provider 未明确表达上下文溢出的错误，不得被归一为 `CONTEXT_LENGTH_EXCEEDED`。若结构化 `error.code` 明确存在且不是 `context_length_exceeded`，Runner 不再用 message marker 覆盖它。

### Context compaction

`context_window_tokens` 是模型单次请求可容纳的输入、输出预留与 reasoning 等总上下文窗口上限；它不同于 `max_output_tokens` 这类模型输出上限。Engine 不计算或裁决 `context_window_tokens`，只在 Runner 明确报告 provider context overflow 时把该事实提升为 `context_compaction_requested`。

Engine 收到 `CONTEXT_LENGTH_EXCEEDED` 后提升为 `context_compaction_requested`，该事件在 provider overflow 路径中的 `budget_state` 为 `None`，并以可恢复失败候选收口。若 Runner 只通过受控 message marker fallback 识别 overflow，Agent 会额外产出非致命 `provider_diagnostic` 记录 provenance；canonical compact request 仍只来自 typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`。Compact 治理由 Host 负责：Host ingest 将该事件转为 reactive compact / recovery，并决定预算估算、压缩策略、compact 执行、结果记录和恢复调度。Engine 自身不执行 compact。

Engine 不做 proactive threshold compaction、compact / retry、provider-aware tokenizer 或 Host budget policy。

### Client correlation

普通 Agent run 会在每次逻辑 Runner 调用前构造非空 `RunnerRequestIdentity`。`client_correlation_id` 是 `dayu-` 加完整 64 位 lowercase SHA-256 hex 的稳定 ASCII id，只用于本地诊断关联和 provider adapter 的显式 per-call 映射，不表达 Host 生命周期治理，也不是 provider end-user 字段。

OpenAI-compatible Runner 只有在 `RunnerSpec.client_correlation_policy == OPENAI_X_CLIENT_REQUEST_ID` 且 `request_identity` 非空时发送 `X-Client-Request-Id`。policy 关闭或 identity 缺失时不发送。policy 开启时，静态 `RunnerSpec.headers` 不得包含大小写不敏感的 `X-Client-Request-Id`。

OpenAI-compatible Runner 的 provider request id 从响应 header `x-request-id` 提取；DeepSeek 兼容入口缺少 `x-request-id` 时，也会把 `x-ds-trace-id` 映射为 `provider_request_id`。`x-trace-id`、`x-correlation-id`、`cf-ray`、W3C trace context、proxy 或 CDN header 不会被映射为 `provider_request_id`。Runner usage 事件与 Engine `usage_reported` 会透传该 provider request id；Runner 调用完成原因只由 `runner_done` / `iteration_completed` 承载，`runner_content_completed` / `content_completed` 只表达正文与推理内容完成。

### Runner close

Runner close 是 run-scoped 收尾机制。`run_agent_messages` 在生成器结束或关闭时触发 EngineEvent stream 关闭；Agent 也在终态路径和最终清理中按 once 语义关闭 Runner。普通 close 失败只记录诊断，不改写已经确定的公共终态；close 被 asyncio cancellation 打断时透传取消，但仍释放私有 Agent 运行槽位。

### 可观测日志与诊断载荷

Engine / Runner 日志遵循 `dayu/README.md` 的级别语义。Agent 在 `VERBOSE` 记录 run、iteration、tool loop、fallback / continuation 与 terminal 骨架；在 `DEBUG` 记录 Runner 事件分类细节，并在 `finish_reason=content_filter` 的降级 final 路径记录有界、脱敏的回答预览，帮助定位 provider 内容过滤收口。OpenAI-compatible Runner 在 `VERBOSE` 记录 provider call start / done / cancelled 摘要，在 `DEBUG` 记录 HTTP attempt、response status、实际存在的 provider request id headers、`X-Client-Request-Id`、finish reason、usage、SSE heartbeat 与协议细节；若 provider request id headers 全部缺失，response 日志保留 `x-request-id=None` 作为缺失信号；在 `WARN` 记录 provider retry、协议差异和可恢复传输异常。

Engine / Runner 日志不输出完整 prompt、provider headers、API key、完整工具结果或大段响应。Runner / provider 诊断事件上的 `raw_payload` 是有界、脱敏、摘要化诊断载荷，不保证保留 provider 原始 payload。

## 扩展点

扩展 provider Runner 时，实现 `AsyncRunner`，把 provider 原生响应归一为 RunnerEvent，并保持工具执行、迭代决策和终态判定在 Agent 协调层。当前函数式入口通过私有默认装配点创建内置 OpenAI-compatible Runner；该私有装配点不是公共 factory、registry 或 runner 选择扩展点。

扩展 Engine 公共事件时，必须同步扩展 `EngineEventType`、对应 data dataclass、`EngineEventData` 封闭联合，以及 RunnerEvent 提升或 Agent 产出路径。

扩展 RunnerEvent 时，必须同步扩展 `RunnerEventType`、对应 data dataclass、`RunnerEventData` 封闭联合，以及 Runner 实现和 Agent 消费路径。

扩展 provider 请求参数时，优先进入 `RunnerSpec.provider_request` 的 provider extension；单次采样、输出长度、top-p 和流式开关进入 `RunnerCallOptions`。

扩展工具能力时，在工具包中使用 `dayu.contracts` 的 `ToolDefinition` / `ToolBundle` 声明工具，由 Service / runtime discovery 装配给 Host / ToolRuntime；Host / ToolRuntime 将 `ToolSchema` 暴露给 Runner，并将受治理后的 `ToolExecutor` 提供给 Engine。Engine 不新增工具注册表，也不把工具部署位置、工具定义对象或 batch 内部执行策略写进 Engine 契约。
