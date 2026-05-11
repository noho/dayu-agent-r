# Engine 开发手册

Engine 位于整体链路最下游：

```text
UI -> Service -> Host -> Engine
```

本文档记录 `dayu.engine` 当前代码已经暴露的开发接口、公共契约、边界与关键运行机制。

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

`run_agent_messages(request)` 运行一次 Agent，并返回 `EngineEvent` 异步流。

- 参数类型是 `AgentRunRequest`。
- 返回值是异步生成器。
- 调用方必须消费到生成器结束；如果提前停止消费，必须显式调用 `aclose()`，以触发 Runner 关闭和 run-scoped 资源收尾。
- Runner 构造失败时异常继续透传。

`run_agent_and_wait(request)` 运行一次 Agent，并完整消费 `run_agent_messages(request)` 直到终态。

- 参数类型是 `AgentRunRequest`。
- 返回值类型是 `AgentRunResult`。
- `AgentRunResult` 是封闭联合，成员包括 `EngineRunOutcomeFinalAnswer`、`EngineRunOutcomeFailed`、`EngineRunOutcomeCancelled`、`EngineRunOutcomeSuspended`。
- Runner 构造失败时异常继续透传。

### AgentRunRequest

`AgentRunRequest` 是执行入口的唯一请求对象，字段包括：

- `run_id`：本次 run 标识。
- `session_id`：调用方传入的会话标识；Engine 只随事件透传，不拥有 session 生命周期。
- `messages`：进入本次 run 的 `AgentMessage` 元组。
- `disable_tools`：是否禁用工具调用。
- `runner_spec`：Runner 规约。
- `runner_options`：单次 Runner 调用参数。
- `agent_policy`：Agent 策略。
- `tool_schemas`：暴露给 LLM 的工具 schema 快照。
- `tool_executor`：工具执行协议实现。
- `cancellation_token`：取消观察 token；命中后阻止尚未开始的后续工作，并在取消赢得当前边界时以 `run_cancelled` / `EngineRunOutcomeCancelled` 收口。

Engine 消费这些字段完成单次 run；不从配置文件、调用方状态或 UI 状态中补读隐式参数。

### 事件接口

`EngineEvent` 是 Engine 对调用方暴露的事件对象，字段包括：

- `occurred_at`
- `session_id`
- `run_id`
- `type`
- `data`
- `metadata`

事件顺序由异步流产出顺序定义。`metadata` 只能承载中性 observer / debug hint，不承载契约事实。

`EngineEventType` 当前包括：

- `iteration_started`
- `content_delta`
- `reasoning_delta`
- `content_completed`
- `tool_call_requested`
- `tool_result_accepted`
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

`RunnerSpec` 描述 Runner 规约，字段包括 provider、model、endpoint、api key 引用、headers、tool calling / streaming 能力、默认 timeout、最大重试次数、provider 请求扩展和 SSE idle 配置。

`RunnerCallOptions` 描述单次调用参数，字段包括 `temperature`、`max_tokens`、`top_p`、`stream`。

### 消息与工具接口

Engine 消费的消息类型来自 `AgentMessage` 封闭联合，当前包括：

- `SystemMessage`
- `UserMessage`
- `AssistantMessage`
- `ToolMessage`

工具执行通过 `ToolExecutor.execute(request)` 完成。Engine 只依赖 `ToolExecutor` 协议、`ToolSchema` 快照、`ToolExecutionRequest` 与 `ToolExecutionOutcome`；工具发现、权限、审计、路由和持久化不属于 Engine 接口。

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

Engine 公共契约分为 Engine 专属契约与跨层共享契约。Engine 专属契约位于 `dayu.engine.contracts`；工具、JSON 值、取消 token 等共享契约位于 `dayu.contracts`，由 Engine 在请求、事件和工具执行协议中消费。

`AgentRunRequest` 归属 Engine 执行入口，是单次 run 的完整输入快照。它包含调用方标识、消息快照、工具开关、Runner 规约、Runner 调用参数、Agent 策略、工具 schema 快照、工具执行协议实现和取消观察 token。Engine 不从隐式全局状态补读请求参数；Runner 是否流式输出只由 `RunnerCallOptions.stream` 表达。

`tool_schemas` 与 `tool_executor` 是同一组工具能力在 Engine 边界上的两个投影。`tool_schemas` 是模型可见的工具 schema 快照，只进入 Runner 调用；`tool_executor` 是工具调用的统一执行入口，只通过 `ToolExecutor.execute(request)` 接收模型返回的工具名、参数和执行上下文。Engine 要求二者由调用方作为同源输入提供，但 Engine 不持有工具注册表，不从 executor 反查 schema，也不负责工具名路由、权限校验或运行时治理。

`AgentPolicy.tool_execution_timeout_seconds` 是 Engine 等待 `ToolExecutor.execute` 返回 outcome 的握手超时预算，必须是有限正数。Engine 构造 `ToolExecutionContext` 时填入该值，并用同一预算等待工具执行协议返回。

`ToolAwaitingOutcome` 是长时间运行工具的挂起契约。ToolExecutor 返回该 outcome 时，Engine 产出 `tool_awaiting` 和 `run_suspended`，事件 data 携带 `await_spec` 与 `snapshot`；`run_agent_and_wait` 返回 `EngineRunOutcomeSuspended`，同样携带这些机器可读恢复事实。

`cancellation_token` 是 Engine 可观察的取消入口。Engine 在 run 开始、Runner 事件消费边界、工具执行等待边界和下一轮工作开始前观察该 token；取消不是普通失败、工具失败或最终回答，也不是公共异常类型。已经被 Engine 接受的 RunnerEvent、工具 outcome、awaiting 事实和 final decision 不会被迟到取消改写。

`AgentRunResult` 是 `run_agent_and_wait` 的终态返回联合，成员为 `EngineRunOutcomeFinalAnswer`、`EngineRunOutcomeFailed`、`EngineRunOutcomeCancelled`、`EngineRunOutcomeSuspended`。终态 outcome 只表达本次 run 的结果，不表达上层持久化状态。

`EngineEvent` 与 `EngineEventData` 是调用方可观察事件契约。`EngineEventData` 是封闭联合，每个 `EngineEventType` 对应一个明确 data 类型；新增事件时必须扩展事件枚举、data 联合、提升逻辑和测试。

`RunnerEvent` 是 Runner 到 Agent 的内部归一事件契约。RunnerEvent 层保留 `runner_*` 命名，包括 `runner_content_delta`、`runner_reasoning_delta`、`runner_tool_call_delta`、`runner_tool_calls_completed`、`runner_content_completed`、`runner_usage_recorded`、`runner_http_error`、`runner_done`；`provider_protocol_error` 作为 provider 协议错误事件在 RunnerEvent 与 EngineEvent 中同名表达。

`AsyncRunner` 归属 Engine Runner 抽象，只负责把 provider 调用归一为 `RunnerEvent` 异步流，并提供能力查询与关闭入口。`ToolExecutor` 归属共享工具执行协议，Engine 只通过 `ToolExecutor.execute(request)` 调用它；工具注册、权限、路由、审计和运行环境不属于 Engine 契约。

## 架构

Engine 内部按 contracts、Agent 协调层与 runners 分工：

- contracts 定义 `AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`RunnerEvent`、`AsyncRunner`、`RunnerSpec`、`RunnerCallOptions` 等公共类型。
- Agent 协调层消费 `AgentRunRequest`，组织单次 run 内的 LLM 迭代、RunnerEvent 提升、工具执行、终态判定和资源收尾。
- runners 提供 `AsyncRunner` 的具体实现，把 provider 协议、SSE / 非流式响应、HTTP / 网络错误归一为 RunnerEvent。

RunnerEvent 与 EngineEvent 是两层事件。RunnerEvent 不含 `session_id` / `run_id`，不直接暴露给 Engine 调用方；EngineEvent 在提升阶段补齐调用方关联字段，并把 Runner 的 provider 事件、工具执行结果和 run 终态投影为 Engine 公共事件。

## 边界

Engine 位于 `UI -> Service -> Host -> Engine` 链路最下游，只负责执行单次 Agent run 所需的协议归一、工具调用编排、事件流和终态结果。

Engine 不负责：

- 工具注册、工具权限、工具路由、工具审计和工具运行时治理。
- run / session 生命周期治理、调度策略、重试编排和上层取消来源管理。
- 事件持久化、trace store、transcript、conversation memory 和去重索引。
- 财报文档存取、财报业务规则和仓储选择。
- UI / Service / Host 的状态机、恢复策略或展示策略。

Engine 可以透传 `session_id`、`run_id`、provider request id、工具调用 id 等契约字段，但不规定这些标识的生成、持久化或去重方式。

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
              -> content_completed
              -> usage_reported
              -> provider_protocol_error
              -> context_compaction_requested
              -> iteration_completed
              -> after each accepted RunnerEvent, observe cancellation_token
      -> if model requested tools
          -> emit EngineEvent.tool_call_requested
          -> ToolExecutor.execute(ToolExecutionRequest)
              -> ToolExecutionContext.timeout_seconds = agent_policy.tool_execution_timeout_seconds
              -> wait execute outcome with cancellation_token and handshake timeout
          -> if cancellation_token wins before outcome
              -> emit terminal EngineEvent.run_cancelled
          -> if handshake timeout wins before outcome
              -> cancel execute task
              -> emit terminal EngineEvent.run_failed(tool_execution_timeout)
          -> if completed / failed outcome
              -> emit EngineEvent.tool_result_accepted
              -> inject ToolMessage into next iteration messages
              -> if cancellation_token observed after injection
                  -> emit terminal EngineEvent.run_cancelled
              -> if all outcomes failed enough times
                  -> fallback by agent_policy.fallback_mode
              -> if max_iterations budget remains
                  -> continue next ordinary iteration
              -> if max_iterations exhausted
                  -> fallback by agent_policy.fallback_mode
          -> if awaiting outcome
              -> ToolExecutor returned ToolAwaitingOutcome(await_spec, snapshot)
              -> AsyncAgent emits EngineEvent.tool_awaiting
              -> close Runner
              -> AsyncAgent emits terminal EngineEvent.run_suspended
              -> late cancellation does not replace run_suspended
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
  -> EngineEvent async stream
```

```text
run_agent_and_wait(request)
  -> consume run_agent_messages(request)
  -> keep last terminal EngineEvent
  -> map final_answer -> EngineRunOutcomeFinalAnswer
  -> map run_failed -> EngineRunOutcomeFailed
  -> map run_cancelled -> EngineRunOutcomeCancelled
  -> map run_suspended -> EngineRunOutcomeSuspended
  -> if stream ends without terminal -> EngineRunOutcomeFailed
```

## 状态机

当前 Engine run 状态机固定为：

```text
CREATED
ITERATING
EXECUTING_TOOL
FINAL_ANSWERED
FAILED
CANCELLED
```

合法迁移：

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
- `ITERATING`：Engine 已产出 `iteration_started`，正在消费一次 `AsyncRunner.call(...)` 的 `RunnerEvent` 流；`iteration_completed` 只表示本轮 RunnerEvent 流结束，不是 run 终态。
- `EXECUTING_TOOL`：本轮 Runner 已完成工具调用请求，Engine 产出 `tool_call_requested`，并通过 `ToolExecutor.execute(ToolExecutionRequest)` 等待工具 outcome。
- `FORCE_ANSWER`：普通工具 iteration 预算耗尽，或连续全失败工具批次达到阈值后，Engine 按 `AgentPolicy.fallback_mode=FORCE_ANSWER` 追加 `fallback_prompt`，禁用工具再调用一次 Runner；空回答或再次请求工具会收口为 `run_failed`。
- `FINAL_ANSWERED`：Engine 已产出 `final_answer`，对应 `EngineRunOutcomeFinalAnswer`。
- `FAILED`：Engine 已产出 `run_failed`，对应 `EngineRunOutcomeFailed`；provider protocol error、context overflow 后的 recoverable failure、重复工具调用 id、Runner 异常结束等都收口到该状态。
- `SUSPENDED`：Engine 已产出 `run_suspended`，对应 `EngineRunOutcomeSuspended`；当前来源是 ToolExecutor 返回 `ToolAwaitingOutcome`。
- `CANCELLED`：Engine 已观察到 `cancellation_token` 命中并产出 `run_cancelled`，对应 `EngineRunOutcomeCancelled`。

Terminal 事件集合由 `TERMINAL_ENGINE_EVENT_TYPES` 定义。进入 `FINAL_ANSWERED`、`FAILED`、`SUSPENDED` 或 `CANCELLED` 后，本次 run 不再继续产出普通事件。

## 事件流

`EngineEventType` 当前公共事件名如下：

- `iteration_started`
- `content_delta`
- `reasoning_delta`
- `content_completed`
- `tool_call_requested`
- `tool_result_accepted`
- `tool_awaiting`
- `context_compaction_requested`
- `usage_reported`
- `provider_protocol_error`
- `iteration_completed`
- `final_answer`
- `run_suspended`
- `run_cancelled`
- `run_failed`

事件顺序由异步流实际产出顺序定义。EngineEvent 不提供单独的事件序号字段、持久化游标或幂等键。

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

## 关键机制

取消 token 是 Engine 的取消收口。Agent 在迭代前、Runner 事件消费后、工具执行等待边界和下一轮工作开始前观察 token；工具执行通过共享 runtime 的取消 / timeout 等待 helper 把 token 纳入等待过程。取消赢得当前边界时，公共结果以 `run_cancelled` 事件和 `EngineRunOutcomeCancelled` 表达。上层调用者要继续原目标时，需要用新的 `AgentRunRequest.messages` 显式提供已确认事实、用户意图或恢复输入。

工具执行协议以 `ToolSchema` 快照和 `ToolExecutor.execute` 为边界。Engine 把 Runner 完成的工具调用投影为 `ToolExecutionRequest`，其中包含 run、session、iteration、tool call、correlation 信息、取消 token 与工具握手 timeout；工具返回完成或失败 outcome 后，Engine 先产出 `tool_result_accepted`，再将结果投影为 LLM 可消费的 tool message。若随后观察到取消，Engine 以 `run_cancelled` 收口，但不丢弃已接受的工具结果事实，也不进入下一轮 Runner。

工具握手 timeout 是 Engine 对 `ToolExecutor.execute` 的等待预算，不是外部长事务 timeout。`AgentPolicy.tool_execution_timeout_seconds` 是该预算真源；timeout 先于 outcome 命中时，Engine 取消 execute task，并以不可恢复 `run_failed(tool_execution_timeout)` 收口。ToolExecutor / ToolRuntime 负责协作响应取消，并治理可能已经启动的线程、子进程、HTTP 请求或远端 job。

挂起 / 恢复协议以 `ToolAwaitingOutcome` 为边界。工具开始外部长事务并建议挂起时，ToolExecutor 返回 `await_spec` 与 `snapshot`；Engine 先产出 `tool_awaiting`，再以 `run_suspended` 收口并关闭 Runner。Engine 不等待外部长事务完成，不持久化等待记录，也不恢复旧 Agent/Runner 实例；上层调用者保存 `await_spec` / `snapshot`，等工具终态确定后构造新的 `AgentRunRequest`，把工具终态结果或恢复输入显式交回 Engine。

Engine 的取消提交边界是“阻止未来工作，不覆盖已接受事实”。已经提升的 content / reasoning delta、已经接受的普通工具结果、已经返回的 awaiting outcome 和已经接受的 final decision 都会先按各自事实收口；取消只在尚未接受 outcome、下一轮 Runner、continuation 或 fallback 之前抢占。上层调用者把自己的取消命令映射成 run-local token，把长事务映射成 `ToolAwaitingOutcome`，再用新 run 恢复，就能形成“宿主强约束下的 LLM in the loop”。

provider 协议错误与 HTTP / 网络错误分层处理。Runner 解析层错误产出 `provider_protocol_error`；HTTP、网络、超时和上下文超限产出 `runner_http_error`。其中上下文长度超限会被 Engine 提升为 `context_compaction_requested`，并以可恢复失败候选收口；是否压缩、如何恢复不属于 Engine。

Runner close 是 run-scoped 收尾机制。`run_agent_messages` 在生成器结束或关闭时会触发内部事件流关闭；Agent 也在终态路径和最终清理中幂等关闭 Runner。Runner close 失败只记录诊断，不改写已经确定的公共终态。

`metadata` 是 EngineEvent 的中性 observer / debug hint 边界。契约事实必须进入强类型 data 字段，不得放进 metadata 让调用方解析。

## 扩展点

新增 provider Runner 时，实现 `AsyncRunner`，把 provider 原生响应归一为 RunnerEvent，并保持工具执行、迭代决策和终态判定在 Agent 协调层。

新增 Engine 公共事件时，必须同步扩展 `EngineEventType`、对应 data dataclass、`EngineEventData` 封闭联合、RunnerEvent 提升或 Agent 产出路径，以及覆盖事件名、data 类型和终态语义的测试。

新增 provider 请求参数时，优先进入 `RunnerSpec.provider_request` 的 provider extension；单次采样、输出长度、top-p 和流式开关进入 `RunnerCallOptions`。

新增工具能力时，通过 `ToolSchema` 暴露给 Runner，通过 `ToolExecutor` 输入与 `ToolExecutionOutcome` 返回结果表达。Engine 不新增工具注册表，也不把工具部署位置写进 Engine 契约。
