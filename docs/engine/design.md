# Engine 接口设计文档

本文档是 Engine 迁移第一阶段产物，只记录从 OLD 源码直接得到的接口结论、边界判断与迁移建议。接口确认前，不迁移 NEW 代码。

## 1. 阅读范围

OLD Engine 阅读范围：

- `dayu/engine/async_agent.py`
- `dayu/engine/async_openai_runner.py`
- `dayu/engine/protocols.py`
- `dayu/engine/events.py`
- `dayu/engine/tool_registry.py`
- `dayu/engine/tool_contracts.py`
- `dayu/engine/tool_result.py`
- `dayu/engine/tool_trace.py`
- `dayu/engine/context_budget.py`
- `dayu/engine/cancellation.py`
- `dayu/engine/truncation_manager.py`
- `dayu/engine/runner_factory.py`
- `dayu/engine/async_cli_runner.py`
- `dayu/engine/sse_parser.py`
- `dayu/engine/reasoning_protocol.py`
- `dayu/engine/xml_extractor.py`
- `dayu/engine/duplicate_call_guard.py`
- `dayu/engine/argument_validator.py`
- `dayu/engine/doc_access_policy.py`
- `dayu/engine/toolset_registrars.py`
- `dayu/engine/exceptions.py`
- `dayu/engine/tool_errors.py`
- `dayu/engine/__init__.py`
- `dayu/engine/README.md`
- `dayu/engine/tools/base.py`
- `dayu/engine/tools/doc_tools.py`
- `dayu/engine/tools/utils_tools.py`
- `dayu/engine/tools/web_tools.py`
- `dayu/engine/tools/web_search_providers.py`
- `dayu/engine/tools/web_fetch_orchestrator.py`
- `dayu/engine/tools/web_http_session.py`
- `dayu/engine/tools/web_http_encoding.py`
- `dayu/engine/tools/web_playwright_backend.py`
- `dayu/engine/tools/web_challenge_detection.py`
- `dayu/engine/tools/web_recovery.py`
- `dayu/engine/tools/error_contract.py`
- `dayu/engine/processors/base.py`
- `dayu/engine/processors/source.py`
- `dayu/engine/processors/registry.py`
- `dayu/engine/processors/processor_registry.py`
- `dayu/engine/processors/_doc_processor_factory.py`
- `dayu/engine/processors/bs_processor.py`
- `dayu/engine/processors/docling_processor.py`
- `dayu/engine/processors/markdown_processor.py`
- `dayu/engine/processors/search_utils.py`
- `dayu/engine/processors/text_utils.py`
- `dayu/engine/processors/table_utils.py`
- `dayu/engine/processors/html_extraction.py`
- `dayu/engine/processors/html_normalization.py`
- `dayu/engine/processors/html_markdown.py`
- `dayu/engine/processors/html_pipeline.py`
- `dayu/engine/processors/local_file_source.py`
- `dayu/engine/processors/perf_utils.py`

为判断 fins 边界，补充阅读：

- `dayu/fins/toolset_registrars.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/service.py`
- `dayu/fins/storage/repository_protocols.py`

## 2. 直接证据摘要

### 2.1 Runner 协议

`dayu/engine/protocols.py::AsyncRunner` 定义 OLD Runner 最小协议：

- `call(messages, *, stream=True, **extra_payloads) -> AsyncIterator[StreamEvent]`
- `set_tools(executor | None) -> None`
- `is_supports_tool_calling() -> bool`
- `close() -> None`

结论：Agent 不应依赖具体 Runner 实现。OLD 的 `extra_payloads` 动机成立：不同 thinking/reasoning 模型确实需要不同 provider 参数；但它不应作为 `call(**extra_payloads)` 的开放调用入口。NEW 应把模型级 provider 参数收进 `RunnerSpec`，由配置解析层强类型化或校验后交给 Runner。

### 2.2 ToolExecutor 与 ToolExecutionContext

`dayu/contracts/protocols.py::ToolExecutionContext` 是强类型 dataclass，字段为：

- `run_id`
- `iteration_id`
- `tool_call_id`
- `index_in_iteration`
- `timeout_seconds`
- `cancellation_token`

`dayu/contracts/protocols.py::ToolExecutor` 方法包括：

- `execute(name, arguments, context) -> dict`
- `get_schemas()`
- `clear_cursors()`
- `get_dup_call_spec(name)`
- `get_execution_context_param_name(name)`
- `get_tool_display_info(name)`
- `register_response_middleware(callback)`

结论：ToolExecutionContext 是 Engine 与 Host / EngineWorker 侧 ToolExecutor 沟通单次工具调用事实的上下文真源。NEW 应保留强类型上下文，不退回 `dict` 式上下文。

### 2.3 StreamEvent

`dayu/engine/events.py::EventType / StreamEvent` 覆盖：

- 内容事件：`content_delta`、`content_complete`、`reasoning_delta`
- 工具事件：`tool_call_start`、`tool_call_delta`、`tool_call_dispatched`、`tool_call_result`、`tool_calls_batch_ready`、`tool_calls_batch_done`
- 控制事件：`iteration_start`、`metadata`、`warning`、`error`、`done`、`final_answer`

结论：`done` 表示单次 Runner 回合结束；`final_answer` 是 Agent 对外最终回答真源，只能由 Agent 产出。OLD `StreamEvent(data: Any, metadata: dict[str, Any])` 不能原样作为 NEW 稳定接口迁移。NEW Host 可见边界统一命名为 `EngineEvent`；Runner 内部可以使用 `RunnerEvent` 归一 provider 流，Agent 再补齐 session/run/sequence/terminal 语义并提升为 `EngineEvent`。

### 2.4 AsyncAgent

`dayu/engine/async_agent.py::AgentRunningConfig` 承载 Agent 内部治理参数：最大迭代、fallback、重复工具调用保护、连续失败批次、上下文预算、续写与压缩次数。

`AsyncAgent.__init__` 接收：

- `runner`
- `tool_executor`
- `tool_trace_recorder_factory`
- `running_config`
- `trace_identity`
- `cancellation_token`

`AsyncAgent.run_messages` 接收 `messages/session_id/run_id/disable_tools/stream`，并在运行中原地追加消息历史。

`_acquire_run_slot` 明确同一 `AsyncAgent` 实例不支持并发运行。

`run_messages` 在 finally 中调用 `await self.runner.close()`、`trace_recorder.close()` 并释放运行槽位。结论：OLD 已经接近 run-scoped 自动关闭模型。NEW 建议把这一点定成显式契约：每次 run 创建新的 Agent 与 Runner，或由函数式入口在内部创建并关闭二者。

`_run_loop` 承担 iteration、Runner 调用、工具结果收集、重复调用保护、失败保护、工具结果注入、context overflow 压缩、finish_reason=length 续写、content_filter 降级和 final_answer 产出。源码注释也承认该方法过大。结论：迁移时必须拆分，不应照搬 God function。

### 2.5 AsyncOpenAIRunner

`dayu/engine/async_openai_runner.py::AsyncOpenAIRunnerRunningConfig` 承载 SSE 调试、工具超时、stream idle timeout、heartbeat。

`AsyncOpenAIRunner.__init__ / _ensure_session / close` 显示 Runner 持有 `aiohttp.ClientSession`，支持显式关闭，并在同一 run 内多轮复用。

`call` 负责：

- 构建 OpenAI compatible payload。
- 合并 default/call 级 payload。
- 校验保留字段。
- HTTP 重试、429/5xx backoff、非重试错误分类。
- SSE 与 JSON 响应分支。
- usage 采集。
- context overflow 错误分类。

`_process_sse_stream / _process_non_stream` 负责把 provider 协议归一成 `StreamEvent`。

`_emit_tool_batch / _run_tool_call` 显示 OLD Runner 还负责并发执行工具并产出工具批次事件。结论：这是 NEW 必须重设的边界；Runner 只应做模型协议归一，不应执行工具。

### 2.6 Cancellation

`dayu/engine/cancellation.py::await_or_cancel` 让业务 awaitable 与 cancellation waiter 竞争；取消先到时取消子任务并抛 `dayu.contracts.cancellation.CancelledError`。

结论：取消真源应由 Host 持有，Engine、Runner、工具只观察。取消命中后不能继续产出 `final_answer`。

### 2.7 ToolRegistry 与工具结果

`dayu/engine/tool_registry.py::ToolRegistry` 管理：

- 工具注册。
- schema 校验。
- 参数校验与规整。
- 路径白名单。
- 工具执行。
- 异常封装。
- 工具级截断。
- `fetch_more` 游标续读。
- response middleware。

`execute` 原则是不抛异常，失败封成工具结果。

结论：OLD ToolRegistry 是有价值的实现素材，但不应作为 NEW Engine 组件迁入。NEW 中 ToolRegistry / ToolRuntime 应归 Host 所有，承担工具注册、权限、审计、超时、取消、长事务等待和恢复等治理入口；Engine 只通过 ToolExecutor 协议与 Host 沟通 tool calling。

`dayu/engine/tool_result.py` 是工具结果信封唯一真源：

- 成功：`ok=true,value=...,truncation?,meta?`
- 失败：`ok=false,error,message,hint?,meta?`

`project_for_llm` 只负责把内部信封投影成 LLM-facing 扁平 JSON，不应替代内部契约。

### 2.8 截断与上下文预算

`dayu/engine/truncation_manager.py::TruncationManager` 按工具 schema 的 `ToolTruncateSpec` 执行工具级截断，生成内存 cursor。`fetch_more` 具备 TTL、scope hash、scope token、single-use 语义。

`dayu/engine/context_budget.py::ContextBudgetState`、OLD `ToolResultBudgetCapper` / soft-hard capping 只作为历史证据和后续 Host 上下文治理设计素材，不作为当前 Engine 迁移范围。

OLD `_compact_messages` 是规则化、确定性的本 run 应急压缩：保留 system、首条 user 和最近尾部消息，把中间历史压成一条 system summary。它不调用 LLM，也不写回 Host conversation memory。

结论：工具级截断属于 Host 侧 ToolRuntime 的工具结果治理；context overflow / context compaction 属于后续 Host 上下文治理与 Engine 协作能力。当前 Engine 迁移不实现 projected tokens 早停、context overflow 强类型识别、`context_compaction_requested` 生产路径或 Engine 内 compact / retry。OLD `_compact_messages` 效果有限，不应作为 NEW Engine 稳定能力迁移；当前 Engine 阶段只把它作为 Host 后续设计参考，不作为 Phase 5 fallback 实现项。

### 2.9 ToolTrace

`dayu/engine/tool_trace.py::JsonlToolTraceStore` 负责 JSONL 结构化 trace 与 raw payload 冷存。

`V2ToolTraceRecorder` 观察：

- iteration start/finish
- tool dispatched/result
- iteration usage
- final response
- SSE protocol error

结论：OLD ToolTrace 是有价值的可观测性实现素材，但不应作为 NEW Engine 组件迁入。NEW Engine 只负责产出足够完整、稳定、强类型、可关联、可持久化、可重放的 `EngineEvent`；Host 负责建立事件订阅/observer 管线。tool trace 只是 Host 订阅 Engine 事件后的一个 observer，后续审计、指标、告警、调试采样、合规留痕也应复用同一事件订阅边界。OLD `tool_trace_v2` 可作为 Host observer 默认实现素材，NEW trace schema 真源由 Host/观测层迁移阶段确认。

### 2.10 Processors 与工具

`dayu/engine/processors/*` 实际是文档解析能力，包含 `DocumentProcessor`、`Source`、section/table/search/page content 结果类型，以及 Markdown/HTML/Docling 处理器。

`dayu/engine/tools/doc_tools.py` 直接使用 `Path`、`open`、`create_doc_file_processor` 读取本地文件，只靠 ToolRegistry 路径白名单守门。

`dayu/engine/tools/web_tools.py` 注册 `search_web` 与 `fetch_web_page`，fetch 工具接收 `ToolExecutionContext`，并通过 public URL 安全策略、requests pipeline、Playwright fallback、取消检查和截断返回网页正文。

`dayu/fins/tools/service.py::FinsToolService` 通过 `CompanyMetaRepositoryProtocol / SourceDocumentRepositoryProtocol / ProcessedDocumentRepositoryProtocol` 与 processor registry 路由财报文档。

`dayu/fins/storage/repository_protocols.py` 提供 `get_source`、`get_primary_source` 等 Source 入口。

结论：OLD Engine 中 processors/doc/web 已经超出 core Engine。NEW 财报文档读取必须沿 `dayu.fins.storage`，不能迁移 `doc_tools.py` 的裸文件读取路径作为财报入口。

## 3. Engine 稳定职责

Engine 应负责：

- Agent 推理循环的中性运行机制：iteration、工具请求/结果回填协议、最终回答收敛、降级、续写、预算检测。
- Runner 抽象与模型协议归一：把 provider 的 SSE、JSON、usage、error、tool call 表达转换为稳定事件。
- 工具调用中性契约：ToolExecutor 协议、ToolSchema、ToolExecutionContext、工具结果信封、工具请求/回填事件。
- 跨模块运行契约：强类型 EngineEvent、RunnerEvent、取消观察原语、上下文预算原语。
- 可观测性事件边界：事件必须携带 Host observer 所需的 run/session/iteration/tool_call/usage/error/raw payload 等事实。

Engine 不应负责：

- UI、Service、Host 的会话、run 生命周期、并发治理、取消真源和持久化治理。
- trace 记录、trace 存储、raw payload 冷存、审计策略和保留周期。
- 配置文件直读、scene 解析、prompt 渲染、模板变量替换。
- 财报业务语义、ticker 归一、文档清单选择、财报章节/表格/XBRL 业务规则。
- ToolRegistry、具体工具注册、工具权限、工具审计、工具执行调度、长事务等待与恢复。
- 绕过 `dayu.fins.storage` 直接访问财报文档文件。
- 作为大杂烩包级 API 重新导出 doc/web/fins 工具和配置类型。

## 4. Engine 在分层中的位置

NEW 架构定位必须是：

```text
UI -> Service -> Host -> Engine
```

Engine 位于 Host 下游，提供 Agent、Runner、tool calling 协议等运行原语。Host 是生命周期、取消、治理、ToolRegistry、工具调度、长事务等待和 run/session 持久化真源。Engine 只消费 Host 通过 EngineWorker capability 提供的运行事实，不反向依赖 UI、Service、Host 的具体实现。

术语固定口径：

- Engine 是包/能力边界，对 Host 暴露函数式入口与稳定 contracts。
- Agent 是 Engine 内部推理循环实现，负责 iteration、RunnerEvent 提升、tool outcome 处理和终态收口。
- Runner 是 Engine 内部模型协议适配器，负责 provider 请求、响应流归一、usage 与资源关闭。
- Host 稳定依赖 Engine 函数式入口和 contracts，不依赖具体 `AsyncAgent` / `AsyncOpenAIRunner` 类。

设计下层组件接口时，应假设上层组件不存在。Engine 接口只能表达“运行一次 Agent 所需的输入与输出”以及“模型请求工具、工具结果回填”的抽象协议，不能泄漏 Host 如何排队、如何持久化、如何注册工具、UI 如何展示、Service 如何装配 scene。

## 5. Host -> Engine 接口文档

最新 Host / EngineWorker 边界以 `docs/host/design.md` 为准。EngineWorker 是 Host 的 capability，不是新的顶层业务层；`AgentRunRequest` 仍是 Engine 一次 run 的最小语义输入，并已包含 `session_id`、`run_id` 与 `cancellation_token`。

本文档中早期“Host 注入 ToolExecutor”的表述，应统一理解为“Host 通过 EngineWorker capability 提供执行环境，并由 EngineWorker 替 Host 在该执行环境中代持、提供 `ToolExecutor`”。Host 仍是生命周期、取消、治理和工具策略真源；Engine 不知道 LocalProxy、RemoteProxy、RemoteStub、RPC 或 ToolExecutor 的真实部署位置。

建议 Host -> Engine 边界：

- Host 解析配置快照和治理输入，并通过 EngineWorker capability 提供执行环境、ToolExecutor、事件消费者与 run-local cancellation token。
- Host 提供权威 `run_id` 与 `session_id`。
- Host 传入已装配好的 `list[AgentMessage]`，Engine 不读取 scene、prompt 模板或配置文件。
- Host 传入强类型 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`，承接 `llm_models.json` 中支撑 Runner / Agent 运行的参数。
- Host 拥有工具治理真源；EngineWorker 只是在执行环境中替 Host 代持并提供 ToolExecutor；Host / EngineWorker 把当前 run 可用工具投影为 `list[ToolSchema]` 与 ToolExecutor protocol；Engine 不注册工具、不执行工具发现。
- Host 调用 `run_agent_messages(request)` 或等价函数式入口；该入口内部为本次 run 创建 Agent 与 Runner。
- Engine 输出 `AsyncIterator[EngineEvent]`；Host 不直接消费 RunnerEvent/StreamEvent。
- Host / EngineWorker 负责消费事件、持久化 transcript、处理取消，并通过注入的 ToolExecutor / ToolRuntime 实现承担工具执行、长事务等待/恢复和失败收口。

工具注册边界：

- 工具注册只发生在 Host/capability 层。web、doc、fins 等 capability 向 Host ToolRegistry 注册工具 descriptor、schema、执行函数、权限策略、超时策略、截断策略和长事务等待策略。
- Host 在创建 `AgentRunRequest` 前，根据 scene、用户权限、workspace policy、模型能力和当前 run policy 选择本次可用工具，生成稳定的 `tool_schemas: list[ToolSchema]` 快照。
- Host 通过 EngineWorker capability 提供 run-scoped `ToolExecutor` handle。LocalEngineWorker 可替 Host 代持本地 ToolExecutor，RemoteEngineWorkerStub 可替 Host 代持远端 ToolExecutor；该 handle 只暴露 Engine 需要的协议方法，内部可以连接 ToolRuntime、权限审计、trace、取消、job monitor、仓储依赖。
- Engine 不接触 ToolRegistry，不接收工具函数，不扫描 toolset，不读取工具配置文件，不保存跨 run 工具状态。

工具调用与结果回填边界：

1. Engine 将 `tool_schemas` 传给 Runner，Runner 只把 schema 发送给模型。
2. 模型返回 tool call 后，Runner 归一为 `ToolCallRequest` 事件，Agent 负责补齐 `run_id`、`iteration_id`、`tool_call_id`、参数 JSON 与调用序号。
3. Agent 调用 EngineWorker 替 Host 代持并提供的 `ToolExecutor.execute(request)`。这是 Engine 唯一“调用工具”的方式；实际注册、校验、执行、权限、超时、审计、取消和长事务治理都在 Host / EngineWorker 执行环境内完成。
4. ToolExecutor 返回 `ToolExecutionOutcome`：
   - `completed`：包含 `ToolResultEnvelope`，Agent 产出 `tool_result_accepted` 事件，并把 LLM-facing tool message 注入下一轮 Runner 调用。
   - `failed`：包含失败 `ToolResultEnvelope`，Agent 按普通工具失败结果注入上下文，让模型决定恢复或给出失败说明。
   - `awaiting`：包含 `ToolAwaitSpec` 与当前 job snapshot，Agent 产出 `tool_awaiting` / `run_suspended` 事件后停止本次 run；Host 记录 wait record，监控终态，并在终态后用新的 run-scoped Engine 调用恢复原始目标。
5. Host 恢复时，不要求复用旧 Agent/Runner；Host 只需把终态工具结果作为权威消息或恢复输入放回新的 `AgentRunRequest`。

扩展 outcome 预留：

> 本节中的 `completed`、`failed`、`awaiting` 等名称只是文档标签。实现时 `ToolExecutionOutcome` 必须是强类型联合类型，例如 `ToolCompletedOutcome | ToolFailedOutcome | ToolAwaitingOutcome`，不能设计成 `status: str` 或字符串字面量加 payload。

第一阶段 Engine contract 只落地 `completed | failed | awaiting`。其它治理分支不进入初始 Engine contract，避免把 Host task ledger、审批、通知、artifact store、去重策略提前泄漏到 Engine。若后续确有需要，可在 #4 下逐个子 issue 论证并扩展强类型 outcome。

扩展 outcome 的后续实现由 [issue #4](https://github.com/noho/dayu-agent-r/issues/4) 总跟踪；每个扩展分支必须单独开子 issue 明确边界、事件、Host 职责和测试策略。

事件边界：

- `iteration_started` 表示 Engine 新一轮 agent iteration 开始。
- `tool_call_requested` 表示模型请求调用工具，是观测事件；Engine 随后通过 EngineWorker 替 Host 代持并提供的 `ToolExecutor.execute(request)` 调用工具，Host 不因该事件另行触发第二套工具执行路径。
- `tool_result_accepted` 表示 EngineWorker 替 Host 代持的 ToolExecutor 已返回结果，Engine 已接收并进入后续上下文注入。
- `tool_awaiting` 表示工具返回长事务等待事实；Host 挂起 run、监控 job，并在终态后恢复 Agent。
- `run_suspended` 表示 Engine 已因 Host 托管等待停止本次 run，后续恢复由 Host 重新发起。
- `runner_done` 表示 Runner 单回合完成，只是 EngineEvent 的观测事实，不是 run 终态。
- `final_answer` 表示 Agent 对外最终回答完成。
- `run_failed` 表示运行失败终态。
- `run_cancelled` 表示 Host 取消请求已被 Engine 接受并收口为取消终态。取消不是普通 `error`，也不能伪装成工具失败或最终回答。

生命周期边界：

- OLD `AsyncAgent.run_messages` 在 finally 关闭 Runner。
- NEW 推荐定死为 run-scoped：Host 每次 run 都创建新的 Agent；Agent 每次 run 都创建新的 Runner，或由 `run_agent_messages(request)` 在函数内部创建二者。
- 若采用函数式入口，Engine 包稳定导出 `run_agent_messages`、`run_agent_and_wait` 与 contracts；`AsyncAgent`、`AsyncOpenAIRunner` 可以保留为包内实现类，但不作为 Host 的主依赖表面。
- Runner 的 HTTP client、SSE stream、provider session 等资源由本次 run 所有，并在 run 达到终态时完成资源收口。
- ToolRegistry / ToolRuntime 生命周期不跟随 Agent/Runner，由 Host / EngineWorker 执行环境持有；Engine 只使用本次 run 的 ToolExecutor handle。

## 6. Agent / AsyncAgent 接口文档

建议保留的入口语义：

- 稳定主入口应是 `run_agent_messages(request: AgentRunRequest)` 或同语义函数式入口。
- `run_agent_and_wait(request: AgentRunRequest)` 只是事件流聚合，不应改变 Runner 是否 stream 的底层语义。
- `AsyncAgent.run_messages(request)` 可作为 Engine 内部实现入口，不建议作为 Host 首选公共入口。

生命周期约束：

- Agent 是 run-scoped，一次实例只服务一次 run，不支持复用与并发 run。
- Runner 是 run-scoped，由 Agent 或函数式入口创建，并在 run 结束、取消、失败、挂起时关闭。
- 新 run 的 Agent 自然拥有新的上下文预算、iteration 状态和 pending tool-call 状态；工具截断 cursor 属于 Host ToolRuntime。
- Agent 只观察 Host 提供的取消令牌。
- 在提交 `final_answer` 前必须再次检查取消。

并发约束：

- Agent 实例级并发要 fail fast。
- Agent 不决定工具执行并发度；多个 tool call 是否并发、队列化、限流或挂起，属于 Host ToolRuntime 治理。
- Agent 只维护“模型请求工具 -> 调用 EngineWorker 替 Host 代持的 ToolExecutor -> 注入下一轮消息或挂起 run”的协议状态机。

取消约束：

- Agent 每轮 iteration 起点检查取消。
- Runner 阻塞边界检查取消。
- Host 侧 ToolExecutionContext 带 linked cancellation token。
- 工具超时、取消、后台任务收口由 Host ToolRuntime 负责；Engine 只接收终态工具结果或等待事实。

## 7. Runner 接口文档

OLD Runner 协议：

```python
class AsyncRunner(Protocol):
    def call(
        self,
        messages: list[AgentMessage],
        *,
        stream: bool = True,
        **extra_payloads,
    ) -> AsyncIterator[StreamEvent]: ...

    def set_tools(self, executor: ToolExecutor | None) -> None: ...

    def is_supports_tool_calling(self) -> bool: ...

    async def close(self) -> None: ...
```

NEW 建议：

```python
class AsyncRunner(Protocol):
    def call(
        self,
        messages: list[AgentMessage],
        options: RunnerCallOptions,
        tools: list[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]: ...

    def is_supports_tool_calling(self) -> bool: ...

    async def close(self) -> None: ...
```

- 保留 `call`、`is_supports_tool_calling`、`close` 的概念；删除 `set_tools`。
- 删除 `call(**extra_payloads)` 弱类型调用入口；保留模型级 provider request extension，但必须放入 `RunnerSpec`，不能散落在每次 `call`。
- 将 `llm_models.json` 中的 provider、model、base URL、API key 引用、headers、thinking/reasoning provider 参数、tool calling capability、超时和重试等模型规格收敛到 `RunnerSpec`。
- 将每次 run 或每次请求可变的 temperature、max tokens、top_p、response format 等收敛到 `RunnerCallOptions`。
- Runner 可接收 `list[ToolSchema]` 作为模型请求 schema，但不接收 ToolExecutor，也不执行工具。
- Runner 负责模型请求、SSE/JSON 解析、HTTP 错误分类、usage 采集、资源关闭。
- Runner 必须在 HTTP 建连、响应读取、SSE chunk 等待、重试 sleep 边界观察取消。
- provider 私有 reasoning 标签只能在 Runner 边界内存在；跨过 Runner 后统一表现为 `ReasoningDeltaData` 或 `ContentCompleteData.reasoning_content` 等强类型字段，不能塞进 metadata。

Provider request extension 建议：

- 已知 provider 参数必须建模为强类型配置，例如 OpenAI `reasoning_effort`、Anthropic `thinking`、Gemini `extra_body.google.thinking_config`、Qwen `enable_thinking`。
- 对暂时无法统一抽象的新 provider，可以在配置 adapter 内部保留受控的 `ProviderRequestPatch` 输入；公共 Engine contract 不直接接受任意 patch。
- Runner 负责把 `RunnerSpec.provider_request` 编译成最终 HTTP request payload；Agent 和 Host 不拼 provider 私有 payload。

必须重设的边界：

- OLD Runner 会执行工具批次。NEW 不迁移该职责；Runner 只把模型返回的 tool call 归一为稳定事件。
- tool calling 调度、权限、审计、超时、长事务等待与恢复都属于 Host ToolRuntime。
- Runner 的 tool calling 能力只表达“模型是否支持工具 schema 与 tool call 输出”，不表达“本地是否能执行工具”。

不建议迁移：

- `AsyncCliRunner` 不进入 NEW 主链路。它不支持 tool calling，并会写工作目录 `AGENTS.md`，不符合当前 Host 强约束下的 Engine 边界。

## 8. Tool 接口文档

NEW 结论：

- ToolRegistry / ToolRuntime 不属于 Engine，归 Host / EngineWorker 执行环境所有。
- ToolExecutor 是 Host / EngineWorker 与 Engine 围绕 tool calling 沟通的协议边界，不是 Engine 内的默认执行器。
- Engine 只表达模型请求的 `ToolCallRequest`、EngineWorker 替 Host 代持的 ToolExecutor 返回的 `ToolCallResultEnvelope`、长事务等待的 `ToolAwaitSpec`。

ToolExecutor 最小协议应由 Host / EngineWorker 执行环境实现：

```python
class ToolExecutor(Protocol):
    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome: ...
```

`tool_schemas` 由 `AgentRunRequest` 单独提供，是本次 run 模型可见 schema 的唯一真源。Engine 不再从 ToolExecutor 读取 schema，也不读取 display info。展示名、参数摘要、UI enrichment 由 Host observer 或 UI 基于 Host ToolRegistry 自行处理。

工具 schema：

- 使用 OpenAI compatible function schema。
- `type` 必须是 `function`。
- `function.name` 与注册名一致。
- `function.parameters.type` 必须是 `object`。
- `required` 必须是字符串数组。
- `additionalProperties` 若提供，必须是布尔值。

工具执行上下文：

- `run_id`
- `session_id`
- `iteration_id`
- `tool_call_id`
- `index_in_iteration`
- `timeout_seconds`
- `cancellation_token`
- `correlation_id`：可选中性关联 ID；不是 ToolTraceRecorder 依赖。Host ToolRuntime 默认应使用 `session_id`、`run_id`、`iteration_id`、`tool_call_id` 与 EngineEvent sequence 建立关联。

工具结果契约：

- 内部流通只使用 ToolResultEnvelope。
- 成功必须包含 `ok=true` 与 `value`。
- 失败必须包含 `ok=false`、`error`、`message`。
- `hint` 是给 LLM 的恢复建议。
- `meta` 是运行时元信息。
- `truncation` 是 Host ToolRuntime 的工具级截断续读信息。
- `ToolAwaitSpec` 只能作为 `ToolAwaitingOutcome` 的显式字段返回；普通 `ToolResultEnvelope.meta` 不承载 run suspension / resume 语义。

Host ToolRegistry / ToolRuntime 职责：

- 管理注册、schema、参数校验、工具执行、异常封装、工具级截断、fetch_more、middleware。
- 执行权限、审计、限流、超时、取消传播、后台任务收口。
- 处理 `await_spec`：挂起 run、监控 job、终态后恢复 Agent。
- 装配 web/doc/fins 等 capability，并保证 Fins 工具只能通过 `dayu.fins.storage`。
- 不进入 Engine 包，也不通过 Engine re-export 暴露。

## 9. EngineEvent / Trace / Cancellation / Context Budget 契约

EngineEvent 稳定规则：

- `EngineEvent` 是 Engine -> Host 的唯一观测边界；Host 侧 tool trace、审计、指标、告警、调试采样都订阅同一事件流。
- 事件必须包含 `event_id`、`sequence`、`occurred_at`、`session_id`、`run_id`、`type`、强类型 `data`。
- iteration 相关事件必须包含 `iteration_id`；tool 相关事件必须包含 `tool_call_id`。
- terminal event 必须明确：`final_answer`、`run_cancelled`、`run_failed`、`run_suspended`。
- Runner usage、SSE protocol error、provider request id、raw payload 等可观测事实必须作为强类型事件 data 暴露给 Host。
- `metadata` 只能承载非契约的 debug tag、采样标记或 observer hint；禁止用 `data: Any`、开放 `metadata` 或 typed metadata 承载显式契约语义。若实现保留 metadata，其值类型必须是严格 JSON value union。
- 事件顺序必须可恢复：同一 run 内 `sequence` 单调递增；Host observer 可依赖 `event_id` 做幂等写入。
- `final_answer` 的 `filtered` 是受过滤完成态的稳定真源。

EngineEvent data 类型草案：

| Event type | Data 类型 | 必要字段 |
| --- | --- | --- |
| `iteration_started` | `IterationStartedData` | `iteration_id`, `iteration_index`, `message_count` |
| `runner_content_delta` | `ContentDeltaData` | `iteration_id`, `delta` |
| `runner_reasoning_delta` | `ReasoningDeltaData` | `iteration_id`, `delta` |
| `runner_content_completed` | `ContentCompleteData` | `iteration_id`, `content`, `reasoning_content`, `finish_reason` |
| `tool_call_requested` | `ToolCallRequestedData` | `iteration_id`, `tool_call_id`, `name`, `arguments`, `index_in_iteration`, `provider_state` |
| `tool_result_accepted` | `ToolResultAcceptedData` | `iteration_id`, `tool_call_id`, `name`, `index_in_iteration`, `outcome` |
| `tool_awaiting` | `ToolAwaitingData` | `iteration_id`, `tool_call_id`, `await_spec` |
| `context_compaction_requested` | `ContextCompactionRequestedData` | `iteration_id`, `budget_state`, `reason`；后续 Host 上下文治理协作事件草案，当前 Engine 迁移不生产 |
| `runner_usage_recorded` | `RunnerUsageData` | `iteration_id`, `prompt_tokens`, `completion_tokens`, `total_tokens` |
| `provider_protocol_error` | `ProviderProtocolErrorData` | `iteration_id`, `error_code`, `message`, `provider_request_id`, `raw_payload` |
| `runner_done` | `RunnerDoneData` | `iteration_id`, `finish_reason` |
| `final_answer` | `FinalAnswerData` | `content`, `filtered`, `finish_reason` |
| `run_suspended` | `RunSuspendedData` | `reason`, `resume_hint` |
| `run_cancelled` | `RunCancelledData` | `reason`, `requested_at`, `accepted_at`, `finished_at` |
| `run_failed` | `RunFailedData` | `error_code`, `message`, `recoverable` |

工具事件字段规则：

- `provider_state` 来自模型 provider 的 tool call 响应，是 provider tool call roundtrip 所需的显式事实；后续注入 assistant tool_calls 给 Runner 时，应按 provider 规则原样带回，避免多轮工具调用协议断链。它不能放入 `metadata`。
- `ToolCallProviderState` 是封闭 provider-specific 联合类型；当前已确认的具体形态只有 `GeminiToolCallState`。
- `reasoning_content` 是否需要随 assistant tool_calls 写回也属于 provider-specific roundtrip 语义。Phase 3 可以先按 OLD 已证明可行的行为无条件写回本轮 `reasoning_content`，作为普通工具闭环的过渡实现；但这不应成为 NEW 跨 provider 稳定规则。有些 provider 可能要求写回，有些 provider 可能不要求写回，也可能存在写回后被 provider 拒绝的情况。Phase 3 后需要用专门 patch 把无脑写回改为 provider-specific 非无脑写回，并评估是否把部分 provider 的 reasoning roundtrip 纳入 `provider_state`。
- `index_in_iteration` 是本轮 tool call 排序事实，`tool_call_requested` 与 `tool_result_accepted` 都必须显式携带，observer 不应依赖回查前序事件才能重建结果顺序。
- `tool_call_requested` 只是观测事件，不触发第二套执行路径；工具执行只能由 Agent 状态机继续调用 EngineWorker 替 Host 代持的 `ToolExecutor`。

RunnerEvent 稳定规则：

- Runner 内部可产出 `RunnerEvent`，用于表达 provider 归一后的 content delta、reasoning delta、tool call delta、usage、runner_done、SSE protocol error 等事实。
- `RunnerEvent` 不跨 Host 边界；Agent 必须把 RunnerEvent 提升为 EngineEvent，补齐 `session_id`、`run_id`、`iteration_id`、`event_id`、`sequence` 和 terminal 语义。
- Runner 不产出 `final_answer`、`run_cancelled`、`run_failed`、`run_suspended` 等 Host 可见终态事件。

RunnerEvent data 类型草案：

| Event type | Data 类型 | 必要字段 |
| --- | --- | --- |
| `runner_content_delta` | `RunnerContentDeltaData` | `delta` |
| `runner_reasoning_delta` | `RunnerReasoningDeltaData` | `delta` |
| `runner_tool_call_delta` | `RunnerToolCallDeltaData` | `tool_call_index`, `tool_call_id`, `name_delta`, `arguments_delta` |
| `runner_tool_calls_completed` | `RunnerToolCallsCompletedData` | `tool_calls` |
| `runner_content_completed` | `RunnerContentCompletedData` | `content`, `reasoning_content`, `finish_reason` |
| `runner_usage_recorded` | `RunnerUsageRecordedData` | `prompt_tokens`, `completion_tokens`, `total_tokens` |
| `provider_protocol_error` | `RunnerProtocolErrorData` | `error_code`, `message`, `provider_request_id`, `raw_payload` |
| `runner_done` | `RunnerDoneData` | `finish_reason` |

Host 事件订阅与 Trace 稳定规则：

- Engine 不依赖 `ToolTraceRecorder`，不直接写 JSONL，不决定 trace schema version。
- Host 订阅 Engine 事件，并把事件分发给一个或多个 observer，例如 tool trace、审计、指标、告警、调试采样。
- tool trace 是 Host observer 的一种实现，不是 Engine 组件；ToolRuntime 的工具执行 trace 也由 Host 侧合并。
- OLD `JsonlToolTraceStore` / `V2ToolTraceRecorder` 可作为 Host 侧 tool trace observer 的实现素材复用。
- OLD `tool_trace_v2` 可作为 Host observer 默认实现素材；是否作为 NEW trace schema 真源由 Host/观测层迁移阶段确认。Engine 只承诺事件事实足够重建该 schema。
- 新增 observer 不应要求 Engine 增加反向依赖；若事件事实不足，应优先扩展稳定 EngineEvent 契约，而不是让 Engine 调用具体 observer。

Cancellation 稳定规则：

- Host 是取消真源，负责创建取消请求、记录取消原因和决定 run 终态。
- NEW 第一阶段直接迁移 OLD 已有主路径：Host 发取消信号，Host 外层 run supervisor 或进程适配层触发 run-local cancellation token，Agent / Runner 在阻塞边界观察取消并收口。
- Engine 公共入口不接收后续 `CancelRun(...)` 命令；`CancelRun(session_id, run_id, reason, requested_at)` 属于 Host API / 进程适配层命令，由 Host 映射为 `AgentRunRequest.cancellation_token` 的取消状态。
- `CancellationToken` 必须能让 Engine 读取取消是否已请求、取消原因和请求时间；Engine 不读取 Host 的 cancel registry 或 run 管理表。
- Engine 接受取消事实后必须返回结构化终态：`run_cancelled` 事件或 `EngineRunOutcomeCancelled`。
- `EngineRunOutcomeCancelled` 至少包含 `session_id`、`run_id`、`reason`、`requested_at`、`accepted_at`、`finished_at`。
- transport error、连接断开、RPC timeout 不是业务取消真源，只能作为 Host 治理输入，由 Host 判定是否转成取消、失败或 lost。
- 取消优先于最终回答；Engine 收到取消后不得继续产出 `final_answer`。
- Engine 必须停止本次 run 相关的 Runner 请求、SSE 读取和事件产出，并完成资源收口。
- Host ToolRuntime 负责工具子任务取消和后台 job 治理，Engine 只接收取消事实或终态结果。
- watchdog、取消超时升级、强制终止、lost 判定等取消治理增强不进入第一阶段迁移细节，由 [issue #3](https://github.com/noho/dayu-agent-r/issues/3) 跟踪。

Context budget / compaction 后续协作规则：

- context overflow / `context_compaction_requested` 不进入本轮 Engine 迁移实现范围。
- `ContextBudgetState`、projected context tokens、trigger ratio、soft / hard limit 和工具结果 capping 只作为后续 Host 上下文治理与 Engine 协作设计素材；当前 Engine 不生产这些状态。
- 当前 Engine 不做 Engine 内 compact / retry，不做 projected tokens 早停，不把 provider context overflow 改写成 `context_compaction_required` recoverable failure。
- Host 未来基于 conversation_memory / transcript / tool facts 压缩后，可重新构造 `AgentRunRequest.messages` 并发起新的 run；是否需要 `context_compaction_requested`、recoverable terminal 和对应数据结构，留给后续 Host 实施时的独立 issue 决定。
- wait / resume / monitor 的 terminal 与恢复语义留给 issue #4 后续设计。
- Engine 不理解业务语义，也不应让 Host 内核理解业务语义；若压缩需要业务知识，应由对应 capability 提供摘要/恢复输入。
- OLD `_compact_messages` 只作为 context overflow 历史行为证据和后续 Host 设计参考；当前 Engine 阶段不得把它作为稳定 compact / retry 能力迁入。

## 10. Processor 与工具边界判断

结论：processors 不应继续作为 NEW core Engine 的职责整体迁入。

理由：

- OLD processors 是文档解析能力，不是 Agent/Runner 核心执行原语。
- OLD doc tools 直接读取本地文件，只适合普通工作区文件工具。
- OLD FinsToolService 已通过 `dayu.fins.storage` 仓储协议拿 Source，再路由 processor。
- NEW 明确要求财报文档存取必须且只能通过 `dayu.fins.storage`。

建议：

- `Source`、`DocumentProcessor`、`ProcessorRegistry` 在 Engine / Host 边界不可见；Engine / Host 不直接拥有、导出、re-export、传递或匹配这些类型。
- 文档解析与 source 类型属于 capability 内部实现；Host 只装配 capability 暴露出的 tool descriptor / schema / executor，不读取 processor registry 或 source 对象。
- Fins 业务处理器、SEC/财报章节/XBRL/财务表增强规则留在 `dayu.fins` 或 Fins capability 内部。
- Web tools 可作为 Host 侧可选 toolset/capability 迁移，不属于 core Engine。
- 通用 doc tools 若迁移，只能定位为普通本地文件读取工具，必须与财报工具隔离。

## 11. Web / Doc / Fins 工具边界

Web tools：

- `search_web` 和 `fetch_web_page` 可作为 Host 侧可选联网 toolset。
- public URL 安全策略、requests pipeline、Playwright fallback 是 web capability 内部实现。
- HTML pipeline 只处理已获取文本，不负责财报仓储读取。

Doc tools：

- OLD doc tools 直接 `Path/open` 读取文件。
- 可迁为 Host 侧普通文件工具，但不能作为财报工具入口。
- 文件白名单是安全边界，不是业务仓储边界。

Fins tools：

- Fins 读取工具应由 `dayu.fins.tools` 暴露，并由 Host ToolRuntime 装配。
- FinsToolService 通过 `dayu.fins.storage` 仓储协议读取公司元数据、源文档和 processed 文档；source 对象是 Fins capability 内部实现事实，不进入 Engine / Host 接口。
- 禁止任何 Engine/doc/web 工具绕过 Fins storage 直接访问财报文档目录。

## 12. OLD 接口处理建议

建议保留：

- OLD `StreamEvent` / `EventType` 的事件语义可作为 RunnerEvent / EngineEvent 设计素材，但 Host 可见边界必须统一为 `EngineEvent`。
- `AsyncRunner` 的抽象能力，但收紧 options 类型。
- `ToolExecutor` / `ToolExecutionContext` / ToolResultEnvelope。
- `ToolRegistry` 的 schema 管理、参数校验、异常信封、截断 cursor 等内部算法可作为 Host ToolRuntime 实现素材。
- ToolTraceRecorder / JsonlToolTraceStore 的实现思路可作为 Host 侧 trace 素材。
- Cancellation helper 的协作式取消语义。
- ContextBudgetState 的单 run projected token 压力判断素材；OLD `ToolResultBudgetCapper`、soft / hard capping 与 `_compact_messages` 仅作为历史证据和 Host 后续设计参考，不进入本轮 Engine 实现。

建议重设：

- Runner 执行工具批次的边界：NEW Runner 不执行工具。
- ToolRegistry / ToolRuntime 的归属：从 Engine 下沉到 Host。
- ToolTrace 的归属：从 Engine 下沉到 Host，Engine 只产出可观测事件。
- OLD `StreamEvent(data: Any, metadata: dict[str, Any])` 的弱类型边界；NEW 中 RunnerEvent 与 EngineEvent 都必须强类型化。
- OLD `_compact_messages` 的归属：不作为 Engine 稳定能力；语义压缩由 Host 协调 conversation memory/capability。是否需要 Engine 发出 `context_compaction_requested` 留给后续 Host 实施时的独立 issue。
- toolset registrar 的装配位置：从 Engine 移到 Host/capability 装配层。
- AsyncAgent God function。
- `extra_payloads` 弱类型扩展袋。
- 包级 `dayu.engine.__init__` 大量 re-export。
- `llm_models.json` 相关运行参数必须进入 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 等强类型契约。
- processors/doc/web 与 core Engine 的包边界。
- OLD #142 所代表的长事务等待：从 LLM 轮询重设为 Host wait record / monitor / resume。

建议删除或不迁移：

- `AsyncCliRunner` 主链路入口。
- 兼容旧测试锚点的薄包装和私有 backend 透传。
- 仅为旧路径保留的 re-export。
- 直接配置文件读取入口。
- 财报文档裸路径读取路径。
- `dayu.engine.tools` 作为 Engine 子包的归属。
- Engine 内解释 doc/web/fins toolset 配置的入口。

## 13. OLD 历史包袱

- `dayu/engine/__init__.py` 包级再导出过宽，容易把 Engine 变成大杂烩 API。
- `AsyncCliRunner` 不支持 tool calling 且写 `AGENTS.md`。
- `AsyncAgent._run_loop` 是 God function。
- `AsyncOpenAIRunner` 同时做模型协议解析和工具执行。
- `extra_payloads` 是弱类型配置袋。
- OLD 大量使用 `Any`、`object`、裸 `dict`。
- `ToolRegistry` 通过 `getattr` 读取函数对象动态元数据。
- `toolset_registrars.py` 在 Engine 内解释 doc/web toolset 配置。
- `doc_access_policy.py` 属于 doc toolset 边界，不是 Engine core。
- `doc_tools.py` 直接读取文件，不能迁移成 Fins 读取路径。
- `web_tools.py` 中存在兼容测试锚点的薄包装。
- OLD README 说 Engine 不理解业务语义，但源码里包含 processors、doc tools、web tools、toolset registrar；结论以源码为准，NEW 应拆出 core Engine。

## 14. 建议的新接口草案

### 14.1 AgentRunRequest

建议字段：

- `run_id: str`
- `session_id: str`
- `messages: list[AgentMessage]`
- `stream: bool`
- `disable_tools: bool`
- `runner_spec: RunnerSpec`
- `runner_options: RunnerCallOptions`
- `agent_policy: AgentPolicy`
- `tool_schemas: list[ToolSchema]`
- `tool_executor: ToolExecutor`
- `cancellation_token: CancellationToken`

不包含：

- 配置文件路径。
- scene。
- UI 状态。
- Host 持久化细节。
- ToolRegistry 实例。
- 工具函数或工具对象实例。
- TraceRecorder 或 trace store。

### 14.2 函数式入口

建议 Engine 包稳定导出：

```python
async def run_agent_messages(
    request: AgentRunRequest,
) -> AsyncIterator[EngineEvent]: ...

async def run_agent_and_wait(
    request: AgentRunRequest,
) -> AgentRunResult: ...
```

入口职责：

- 为本次 run 创建新的 Agent。
- 根据 `RunnerSpec` 为本次 run 创建新的 Runner。
- 把 `tool_schemas` 传给 Runner，把 `tool_executor` 传给 Agent tool-call bridge。
- 在 run 达到终态时关闭 Runner，并收口 Agent 内部任务。
- 不持有跨 run 状态，不缓存工具，不读取配置文件，不写 trace store。

Engine 包根导出建议：

- 导出函数式入口、稳定 contract 类型、事件类型、错误类型。
- 不从包根导出 Host ToolRegistry、web/doc/fins tools、toolset registrar。
- `AsyncAgent`、`AsyncOpenAIRunner` 可保留在子模块作为当前实现和测试对象，但 Host 首选依赖函数式入口。

### 14.3 RunnerSpec / AgentPolicy

建议字段：

- `RunnerSpec`：provider、model、endpoint、API key 引用、headers、模型能力、默认超时、重试策略、stream 能力、tool calling 能力、reasoning/thinking provider request extension。
- `RunnerCallOptions`：temperature、max tokens、top_p、response format、当前请求覆盖项。
- `AgentPolicy`：max iterations、continuation 策略、fallback 策略、是否允许 tool calling、最终回答过滤策略。上下文预算 / compaction 策略不属于本轮 Engine 迁移范围，后续 Host 上下文治理实施时再确定。

约束：

- 这些类型承接 `llm_models.json` 的运行参数，但 Engine 不读取该 JSON 文件。
- `llm_models.json` 中原 `extra_payloads` 的语义应迁为 `RunnerSpec.provider_request`，而不是进入 `Runner.call`。
- 显式参数必须成为显式字段，不能塞进 `extra_payloads` 或 `metadata`。
- provider 私有扩展只能进入强类型 provider extension；公共 Engine contract 不直接接受任意 provider patch。
- `ProviderRequestPatch` 若存在，只能作为配置 adapter 内部输入，配置解析阶段必须校验 provider、schema_id、schema_version、允许 patch 的 JSON pointer 白名单和禁止覆盖的保留字段；业务代码不能动态拼接任意 payload。

建议类型草案：

- `ProviderRequestExtension = OpenAIReasoningExtension | AnthropicThinkingExtension | DeepSeekThinkingExtension | MimoThinkingExtension | GeminiThinkingExtension | QwenThinkingExtension | ValidatedProviderRequestExtension`
- `OpenAIReasoningExtension`：`reasoning_effort: OpenAIReasoningEffort`
- `AnthropicThinkingExtension`：`enabled: bool`、`budget_tokens: int | None`；disabled 时不传 `budget_tokens`，相关 beta header 仍属于 `RunnerSpec.headers`
- `DeepSeekThinkingExtension`：`enabled: bool`、`reasoning_effort: DeepSeekReasoningEffort | None`，投影为顶层 `thinking.type`，不含 `budget_tokens`
- `MimoThinkingExtension`：`enabled: bool`，投影为顶层 `thinking.type`，不含 `budget_tokens`
- `GeminiThinkingExtension`：`thinking_budget: int | None`、`include_thoughts: bool | None`、`thinking_level: GeminiThinkingLevel | None`
- `QwenThinkingExtension`：`enable_thinking: bool`、`thinking_budget: int | None`
- `ValidatedProviderRequestExtension`：只由配置 adapter 基于受控 `ProviderRequestPatch` 生成，必须带 `provider`、`schema_id`、`schema_version` 和已校验的 provider 私有字段；Agent/Host 调用 Engine 时不能传入原始 patch。

### 14.4 Tool Calling Protocol

建议核心类型：

- `ToolSchema`：Host 从 ToolRegistry 投影出的模型可见 schema 快照。
- `ToolCallRequest`：Engine 从模型 tool call 归一出的工具调用请求。
- `ToolExecutionRequest`：Agent 调用 ToolExecutor 时补齐运行上下文后的请求。
- `ToolExecutionOutcome`：ToolExecutor 返回给 Engine 的结果联合类型。
- `ToolResultEnvelope`：普通完成/失败工具结果。
- `ToolAwaitSpec`：Host 托管长事务等待、终态唤醒和 resume 的机器可读契约。
- `ToolAwaitSnapshot`：Host 返回给 Engine 的等待态快照，只表达可恢复等待所需的中性治理事实，不表达 web/doc/fins 业务状态。

稳定流程：

1. Host 注册工具并生成 `tool_schemas`。
2. Host / EngineWorker 将 `tool_schemas` 与 run-scoped `tool_executor` 放入 `AgentRunRequest`。
3. Engine 把 `tool_schemas` 交给 Runner。
4. Runner 产出模型 tool call，Agent 转成 `ToolExecutionRequest`。
5. Agent 调用 `tool_executor.execute(request)`。
6. ToolExecutor 返回普通结果时，Agent 注入下一轮 tool message。
7. ToolExecutor 返回 `ToolAwaitSpec` 时，Agent 产出 suspended 事件并结束本次 run；Host 终态后重新调用函数式入口恢复。

第一阶段 Outcome 联合类型建议：

> 以下写法是接口语义速记，不是要求实现为字符串枚举。落地代码应使用独立 dataclass / typed class 组成封闭联合类型；序列化需要字符串时，只能在边界 adapter 使用 enum 映射。

- `completed(result: ToolResultEnvelope)`
- `failed(result: ToolResultEnvelope)`
- `awaiting(await_spec: ToolAwaitSpec, snapshot: ToolAwaitSnapshot | None)`

约束：

- `ToolExecutionOutcome` 必须是封闭可辨识联合类型，不能用 `status: str` 加任意 payload 逃避类型设计。
- 第一阶段除 `awaiting` 外不定义其它非终态 outcome；后续治理分支必须经 #4 子 issue 单独确认。
- Host 恢复 run 时必须提供结构化恢复输入，不依赖旧 Agent/Runner 实例仍然存活。

### 14.5 AsyncAgent

建议定位：

- run-scoped 内部实现类。
- 不作为 Host 首选公共入口。
- 不持有 ToolRegistry。
- 可持有本次 run 的 `ToolExecutor` protocol handle。

建议公开入口：

- `run_messages(request: AgentRunRequest) -> AsyncIterator[EngineEvent]`
- `run_and_wait(request: AgentRunRequest) -> AgentResult`
- `close() -> None` 用于函数式入口资源收口。

Agent tool calling 边界：

- Agent 将模型 tool call 归一为 `ToolCallRequest`，并发出 `tool_call_requested` 观测事件。
- Agent 调用 EngineWorker 替 Host 代持的 ToolExecutor 后，以 `ToolCallResultEnvelope` 或 `ToolAwaitSpec` 继续或挂起本次 run。
- Agent 不持有 ToolRegistry，不决定工具执行并发度，不轮询外部长事务。

### 14.6 AsyncRunner

建议职责：

- 模型请求。
- 响应协议归一。
- usage 采集。
- 错误分类。
- 资源关闭。
- 取消观察。

明确不负责：

- 工具执行。
- 工具注册。
- 长事务等待。
- Host run/session 状态。

生命周期：

- 每次 run 创建新 Runner。
- 每次 run 结束、取消、失败、挂起时关闭 Runner。
- 不跨 run 复用 HTTP stream、response parser、provider request 状态。

### 14.7 ToolExecutor / ToolRegistry

建议：

- `ToolExecutor` 保留为 Host 与 Engine 沟通 tool calling 的最小协议。
- `ToolRegistry` 不进入 Engine；若复用 OLD 代码，只作为 Host ToolRuntime 内部实现素材。
- 工具 metadata 由显式 descriptor 承载，减少函数对象动态属性读取。
- 工具结果使用专用 envelope 类型，不用裸弱类型字典表达公共边界。
- `ToolAwaitSpec` 只能作为 `ToolAwaitingOutcome` 的显式字段返回；普通 `ToolResultEnvelope.meta` 不承载 run suspension / resume 语义。

### 14.8 Processor

建议：

- 不进入 core Engine。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 在 Engine / Host 不可见。
- 通用文档解析属于 document capability 内部实现。
- Fins processor 与 source 对象属于 `dayu.fins` / Fins capability 内部实现，外部只通过 `dayu.fins.storage` 仓储协议和 Fins tools 结果契约交互。

## 15. 外部 Agent 机制参考

本节只作为接口扩展参考，不覆盖 OLD 源码证据，也不要求一次性照搬实现。

参考来源：

- OpenClaw docs：`https://docs.openclaw.ai/automation/tasks`、`https://docs.openclaw.ai/automation`
- Claude Code docs：`https://code.claude.com/docs/en/scheduled-tasks`、`https://code.claude.com/docs/en/web-scheduled-tasks`
- Claude Code repo：`https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum`
- Codex repo：`https://github.com/openai/codex/tree/main/codex-rs/core/src/unified_exec`

OpenClaw：

- 官方 Background tasks 文档把任务定义为 detached work 的 activity ledger，不是 scheduler；状态机包含 `queued -> running -> terminal`，终态包括 `succeeded/failed/timed_out/cancelled/lost`。
- OpenClaw 明确推荐 push-driven completion：后台工作完成后直接通知或唤醒 requester session/heartbeat，通常不应写 status polling loop。
- OpenClaw task 支持 notification policy：`done_only`、`state_changes`、`silent`，并有 `tasks audit/maintenance` 处理 stale、lost、delivery_failed、cleanup 等治理问题。
- OpenClaw Automation 文档区分 cron、heartbeat、hooks、standing orders、task flow；Task Flow 是 background task 之上的 durable multi-step orchestration。

Claude Code：

- Scheduled tasks 的动态 `/loop` 会根据观察结果选择下一次延迟；Monitor tool 可运行后台脚本并流式返回输出，避免按固定间隔重新 prompt 轮询。
- Routines 支持 schedule、API、GitHub event 等触发，并为每次 run 创建新 session；权限和可达资源由 repository、environment、connectors、permissions 限定。
- `anthropics/claude-code` 的 Ralph Wiggum plugin 使用 Stop hook 阻止会话退出，把同一 prompt 重新送回当前 session，直到 completion promise 或 max iterations；它适合自我修复循环，但不适合作为 Dayu 长事务等待主路径。

Codex：

- `openai/codex` unified exec 使用 `process_id`、`ProcessStore` 和 `write_stdin` 支持可继续的 live process；初始 yield 前会持久化 live session，避免 turn 中断导致后台进程被释放。
- unified exec 有 output delta 与 end event：后台 watcher 持续读取 PTY 输出并发出 `ExecCommandOutputDelta`，进程退出后发统一的 end event。
- Codex 有 network approval 机制，支持 pending approval、allow once / allow for session / deny、deferred network approval 与取消令牌。

对 Dayu 的接口启发：

- `awaiting` 只覆盖“当前 run 等待外部长事务终态”；`detached`、`progressing`、`approval_required`、`retry_after`、`input_required`、`cancelled/timed_out/lost`、`deduplicated`、`delegated`、`artifact_ready` 等治理分支留给 issue #4 的子 issue 逐一论证，不进入第一阶段 Engine contract。
- Host 必须拥有 task ledger、notification policy、approval UI、retry scheduler、artifact store、cleanup/maintenance；Engine 不持有这些治理真源。
- Engine 只需要稳定事件和结构化 outcome，使 Host 能挂起、恢复、取消、审计和通知。

## 16. 下一阶段迁移计划草案

Engine 迁移顺序：

1. 迁移 pure contracts：强类型 `EngineEvent`、`RunnerEvent`、`ToolResultEnvelope`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolCallRequest`、`ToolSchema`、`ToolExecutionContext`、`ToolExecutionOutcome`、`ToolExecutor` protocol、`AsyncRunner`、取消观察原语。context budget / compaction 原语只保留为后续 Host 协作设计素材。
2. 建立 Engine 包根导出与 import boundary 测试；先证明不导出兼容 wrapper / 旧 re-export，不导入 Host ToolRegistry、web/doc/fins tools、ToolTraceRecorder 或 `dayu.fins.storage` 具体实现。
3. 新增 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`，承接 `llm_models.json` 的运行参数；删除 `Runner.call(**extra_payloads)` 弱类型入口，并把 provider request extension 收敛为强类型配置。
4. 迁移 AsyncOpenAIRunner 的模型协议归一能力，先只产出 `RunnerEvent`；不迁 AsyncCliRunner，不迁 Runner 工具执行职责。
5. 实现函数式入口骨架 `run_agent_messages` / `run_agent_and_wait`，入口内部创建 run-scoped Agent 与 Runner，并只向 Host 暴露 `EngineEvent`。
6. 实现 Agent 最小 loop：无工具场景下完成 iteration 调度、RunnerEvent 提升、usage 记录、final_answer、失败终态和资源收口。
7. 实现 completed / failed tool loop：Engine 接收 `tool_schemas` 与 `ToolExecutor` protocol，发出 `ToolExecutionRequest`，接收 `completed` / `failed` outcome，注入下一轮 tool message；不实现 ToolRegistry / ToolRuntime。
8. awaiting / suspended 主链路已取消当前 Engine 独立实施，转入 issue #4 后续拆子 issue；当前迁移不实现 `tool_awaiting` / `run_suspended` / resume。
9. 实现取消观察主链路：`AgentRunRequest.cancellation_token` 是 Engine 可见取消入口；Engine 观察取消并产出 `run_cancelled` / `EngineRunOutcomeCancelled`。`CancelRun(session_id, run_id, reason, requested_at)` 只作为 Host API / 进程适配层命令，不进入 Engine 公共 contract。
10. context overflow / `context_compaction_requested` 后移：当前 Engine 迁移只保留事件契约/概念草案，不实现生产路径、recoverable terminal、Engine 内 compact / retry、conversation memory 或语义压缩；后续 Host 上下文治理实施时再完善 Engine 协作事件。
11. 清理 processors/tools/web/doc/fins 与 Engine core 的导入关系；`Source`、`DocumentProcessor`、`ProcessorRegistry` 对 Engine / Host 不可见，Engine 只保留协议与事件边界。
12. 根据实际落地同步 `dayu/engine/README.md`；涉及 Host、fins、capability 的 README 留给对应迁移阶段更新。

Host 接口要求：

- Host / EngineWorker 提供 `AgentRunRequest`，包括 `session_id`、`run_id`、messages、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`tool_schemas`、`ToolExecutor` 和 run-local cancellation token；该 request 是 EngineWorker 最小运行输入，不需要在 EngineWorker 方法签名里重复展开 `session_id`、`run_id` 或 `cancellation_token`。
- Host 消费 `AsyncIterator[EngineEvent]`，并自行决定 transcript 持久化、tool trace observer、审计、指标、UI 转发。
- Host 是 ToolRuntime / ToolRegistry 与工具治理真源；ToolExecutor 由 EngineWorker 替 Host 代持并提供，可以在本地 worker 或远程 worker 内执行；Engine 只依赖协议。
- Host 外层取消命令映射为 run-local cancellation token；Engine 不持有跨 run cancel registry。
- Host 未来负责 conversation memory、语义压缩、context overflow 后的消息重构与重新发起 run；如需要 `context_compaction_requested`，由后续 Host 实施时的独立 issue 完善 Engine。
- Host 未来负责 `await_spec` 的 wait record、monitor、resume；当前 Engine 迁移不产出 awaiting/suspended 事实，相关能力由 issue #4 后续设计。
- Host 负责 web/doc/fins toolset/capability 装配；财报文档读取仍只能通过 `dayu.fins.storage`。

测试策略：

- 测试代码按 NEW Engine contracts 重写；OLD tests 不迁移为兼容测试，只作为行为证据、场景样本和回归用例来源。
- 每个迁移切片先建立接口测试，再迁实现；接口测试必须覆盖 Host -> Engine 公共入口、输入类型、输出事件、取消、tool calling 等当前稳定契约。context budget / compaction request 不作为本轮稳定实现契约。
- 必须建立架构测试，防止边界回退：
  - 若约定 Engine 包根只导出 `run_agent_messages`、`run_agent_and_wait` 和 contract 类型，则导出更多实现类、兼容 wrapper、旧 re-export 时测试必须失败。
  - Engine 不得导入 Host 具体实现、Host ToolRegistry、web/doc/fins tools、`dayu.fins.storage` 具体实现。
  - Runner 不得依赖 ToolExecutor，不得执行工具。
  - Engine 不得依赖 ToolTraceRecorder / JsonlToolTraceStore；只能产出 EngineEvent。
  - Engine 不得保留 `Runner.call(**extra_payloads)`、OLD `StreamEvent(data: Any, metadata: dict)` 等弱类型边界。
- pyright 每步必须无新增或扩散错误。
- ToolResult、ToolAwaitSpec、EngineEvent、RunnerEvent、ToolExecutionContext、Runner cancellation、Agent loop 状态机必须有专门测试。
- EngineEvent 必须覆盖强类型 data、sequence 单调性、event_id 幂等、terminal event 唯一性、raw payload 事件载荷语义。
- ToolExecutionOutcome 联合类型需要穷尽匹配测试，确保新增 outcome 不会被吞成普通失败或弱类型 payload。
- Runner 测试必须证明 Runner 只产出 tool call 事件，不执行工具。
- Engine 边界测试必须证明 Engine 不导入 Host ToolRegistry、web/doc/fins tools 或 `dayu.fins.storage` 具体实现。

主要风险：

- Host/Engine tool calling 接口需要设计清楚，否则容易在挂起、恢复、取消之间产生重复执行。
- await_spec 的 Engine 事件事实必须足够 Host 后续实现 wait record / resume，否则后续 Host 迁移会补接口。
- outcome 分支过多可能诱导业务状态泄漏进 Engine；必须坚持只收 Host 治理语义，不收 fins/web/doc 业务状态。
- Tool schema/result 当前大量弱类型，严格类型化会牵动工具实现和测试。
- Processors/tools 从 Engine 拆出会影响后续 Host/capability/fins 迁移，但 Engine 阶段只负责不再依赖这些包。
- EngineEvent 必须一次性定好强类型边界；否则 Host observer、trace、audit 后续会被迫依赖临时字段。
- run-scoped Agent/Runner 生命周期与 OLD `AsyncAgent` 自动关闭 Runner 的差异需要在 Engine 接口中一次性定死。
