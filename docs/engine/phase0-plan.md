# Engine Phase 0 实施计划

本计划是 Engine 迁移 Phase 0 的实施依据，已根据 `docs/engine/phase0-plan-review.md` 与「层间共享契约迁入 `dayu.contracts`」收口范式修订。计划只覆盖 pure contracts 与 import boundary tests；未确认或 review 要求降级的项一律从 Phase 0 移除，留给后续 Phase。

## 0. 契约分层范式（本 Phase 落点判定唯一依据）

判定原则：

- **若语义真源在一方，另一方只是调用方** —— 契约落在语义真源所在层。例如 Engine 单向定义事件、出入参 schema：契约落 `dayu.engine.contracts`。
- **若两个层都需要独立实现、产生、解释或持久化它，且它描述的是层间协作协议而不是某一层的调用参数** —— 契约落公共契约层 `dayu.contracts`。例如 `CancellationToken`（Host 产生 / Engine 观察）、`ToolExecutor`（Host 实现 / Engine 调用）、工具 result/outcome 类（Host 产生 + 持久化 / Engine 解释）。

按此范式收口后的最终落点见 §1.1 / §1.2。

## 1. Phase 范围

在 NEW 仓库新建：
- 公共契约包 `dayu/contracts/`。
- Engine 包骨架 `dayu/engine/`、`dayu/engine/contracts/`。
- 测试骨架 `tests/contracts/`、`tests/engine/`。

落地全部强类型 pure contracts，按范式拆分为 §1.1 与 §1.2 两组。

### 1.1 落在 `dayu.contracts`（层间协作协议；Host 与 Engine 双方独立产生 / 解释 / 持久化）

- `JsonValue` 严格 JSON 联合（基础类型，所有层独立构造与解析）。
- `CancellationToken` Protocol（Host 实现 + 激活；Engine 协作式观察；公共终态由结构化事件 / outcome 表达，**不**导出取消异常）。
- `ToolExecutor` Protocol（Host 实现；Engine 调用）。
- `ToolCallRequest`、`ToolExecutionContext`、`ToolExecutionRequest`（Engine 构造；Host 解释 + 持久化）。
- `ToolResultSuccess` / `ToolResultFailure` / `ToolResultEnvelope`（保留 `ok: Literal[True/False]` 判别字段）、`ToolTruncationInfo`、`ToolResultMeta`（Host 产生；Engine 解释；Host 持久化）。
- `ToolAwaitKind` / `ToolAwaitSpec` / `ToolAwaitSnapshot`（Host 产生；Engine 解释；Host 持久化）。
- `ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolAwaitingOutcome` / `ToolExecutionOutcome` 联合。
- `ToolSchema` / `ToolFunctionSchema` / `ToolParametersSchema`（Host 注册产生；Engine 透传给 Runner）。

### 1.2 留在 `dayu.engine.contracts`（Engine 单向 API 表面 / Engine 内部协议；语义真源为 Engine）

- 入参 / 配置：`AgentMessage` 封闭联合 + `AgentMessageRole` + `AssistantToolCall`（Runner 协议归一真源在 Engine）；`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`AgentRunRequest`；`OpenAIReasoningExtension` / `AnthropicThinkingExtension` / `GeminiThinkingExtension` / `QwenThinkingExtension` / `ProviderRequestExtension` 联合。
- 出参 / 出口语义：`AgentRunResult` 封闭联合 + 四种终态 `EngineRunOutcomeFinalAnswer` / `EngineRunOutcomeFailed` / `EngineRunOutcomeCancelled` / `EngineRunOutcomeSuspended`；`ContextBudgetSnapshot`；`RunResumeHint`；`FinishReason` StrEnum。
- 事件出口（Engine 单向定义；Host 仅持久化既定形态，不独立定义事件类型）：`EngineEventType`、`EngineEvent`、全部 EngineEvent data dataclass（`IterationStartedData` / `ContentDeltaData` / `ReasoningDeltaData` / `ContentCompleteData` / `ToolCallRequestedData` / `ToolResultAcceptedData` / `ToolAwaitingData` / `ContextCompactionRequestedData` / `RunnerUsageData` / `ProviderProtocolErrorData` / `RunnerDoneEngineData` / `FinalAnswerData` / `RunSuspendedData` / `RunCancelledData` / `RunFailedData`）、`EngineEventData` 别名、`TERMINAL_ENGINE_EVENT_TYPES`。
- Engine 内部 Agent ↔ Runner 协议：`AsyncRunner` Protocol；`RunnerEventType` / `RunnerEvent` / `RunnerEventData` 别名 / 全部 Runner data dataclass（`RunnerContentDeltaData` / `RunnerReasoningDeltaData` / `RunnerToolCallDeltaData` / `RunnerToolCallsCompletedData` / `RunnerContentCompletedData` / `RunnerUsageRecordedData` / `RunnerProtocolErrorData` / `RunnerDoneData`）。

### 1.3 包根导出策略

- `dayu/contracts/__init__.py`：仅导出 §1.1 列表，显式 `__all__`。
- `dayu/engine/__init__.py`：导出 §1.2 列表 + 从 `dayu.contracts` re-export §1.1 全部符号，使 `from dayu.engine import ...` 仍是 Engine 调用方的单一入口。re-export 在此处是**结构契约导出**，不是兼容 wrapper：理由是 Engine 是 §1.1 的主要消费者，对调用方而言 `dayu.engine.*` 是 Engine API surface 的稳定面，避免调用方为同一组协作协议在两个 import 路径之间二选一。
- 任一包不得导出函数式入口、实现类、占位函数（`run_agent_messages` / `run_agent_and_wait` / `AsyncAgent` / `AsyncOpenAIRunner` 等）。

### 1.4 架构测试套范围

- `tests/contracts/`：`dayu.contracts` 包根导出白名单、import boundary（不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 任何子模块）、weak typing 守卫、协议表面、metadata 边界、tool outcome 穷尽、tool result envelope 判别字段。
- `tests/engine/`：`dayu.engine` 包根导出白名单（含从 `dayu.contracts` re-export 部分）、import boundary（区分当前 Phase 与永久禁入；允许 import `dayu.contracts`）、weak typing 守卫、event/runner contract、AgentMessage 联合、AsyncRunner 协议表面。

## 2. 明确不做什么

- 不实现 `AsyncAgent`、`AsyncOpenAIRunner`、`AsyncCliRunner`。
- 不导出 `run_agent_messages` / `run_agent_and_wait`（即使占位形态也禁止）。
- 不迁移 ToolRegistry / ToolRuntime / argument_validator / duplicate_call_guard / truncation_manager / runner_factory / sse_parser / xml_extractor / reasoning_protocol / doc_access_policy / toolset_registrars。
- 不迁移 doc/web/fins tools；不迁移 processors；不迁移 ToolTraceRecorder / JsonlToolTraceStore。
- 不实现取消治理增强、watchdog、超时升级、lost 判定。
- 不导出任何取消异常（如 `CancelledError`）；取消公共终态由 `RunCancelledData` 与 `EngineRunOutcomeCancelled` 表达。
- 不实现 ContextBudgetState 的运算逻辑；本 Phase 仅落地 `ContextBudgetSnapshot` 最小快照 dataclass，仅作为 `ContextCompactionRequestedData.budget_state` 字段类型，不含计算逻辑、不含 soft/hard 阈值消费。
- 不落地 `ValidatedProviderRequestExtension`（按 review §4.2 推迟，只保留四种已知 provider 强类型扩展；待配置 adapter 阶段单独评审引入）。
- 不落地 `FallbackStrategy`、`FinalAnswerFilter`、`ResponseFormat`、`ContextBudgetLimits` 等暂无消费方的辅助类型；按 review §3.2 进入「待引入名单」，留给消费它的 Phase。
- 不写 README 用户向手册内容；默认不创建 `dayu/engine/README.md` / `dayu/contracts/README.md`。

## 3. 直接依据

- `docs/engine/design.md`：第 2.7 / 8 / 9 / 14.1 / 14.2 / 14.3 / 14.4 节。
- `docs/engine/review.md`：第 8 节最小迁移切片清单。
- `docs/engine/migration-plan.md`：第 4 节 Phase 0 行；第 5 节详细计划；第 12 节跨阶段架构测试。
- `docs/engine/migration-plan-review.md`：第 4.2 节（禁止 Phase 0 导出占位）；第 5.2 节（README 检查而非必改）。
- `docs/engine/phase0-plan-review.md`：本计划早期修订依据。
- `AGENTS.md` / `CLAUDE.md`：架构、编码、思考纪律硬约束。
- 本计划 §0 契约分层范式：`dayu.contracts` vs `dayu.engine.contracts` 落点判定唯一依据。

## 4. OLD 可复用片段（仅作为字段语义和场景证据来源，禁止机械搬迁）

- `~/workspace/dayu-agent/dayu/engine/events.py`：`EventType` 枚举值、`StreamEvent` 字段使用场景。
- `~/workspace/dayu-agent/dayu/engine/tool_result.py`：`ok` / `value` / `error` / `message` / `hint` / `meta` / `truncation` 字段语义。
- `~/workspace/dayu-agent/dayu/engine/protocols.py`：`AsyncRunner` 旧协议字段对照。
- `~/workspace/dayu-agent/dayu/engine/cancellation.py`：协作式取消 token 接口形态。
- `~/workspace/dayu-agent/dayu/contracts/protocols.py`：`ToolExecutionContext` 字段语义。
- `~/workspace/dayu-agent/dayu/engine/context_budget.py`：仅参考 budget snapshot 字段命名。

## 5. NEW 文件变更计划

### 5.1 生产代码（新增）

#### 5.1.1 公共契约包 `dayu/contracts/`

- `dayu/__init__.py`
- `dayu/contracts/__init__.py`：聚合 §1.1 子模块导出；显式 `__all__` 白名单。
- `dayu/contracts/json_value.py`：`JsonValue` 严格 JSON 联合（仅 TypeAlias，无 runtime validator）。
- `dayu/contracts/cancellation.py`：`CancellationToken` Protocol（**不**导出任何取消异常）。
- `dayu/contracts/tool_schema.py`：`ToolSchema` / `ToolFunctionSchema` / `ToolParametersSchema`。
- `dayu/contracts/tool_call.py`：`ToolCallRequest`、`ToolExecutionContext`（含 `cancellation_token: CancellationToken`、`correlation_id: str | None`）、`ToolExecutionRequest`。
- `dayu/contracts/tool_result.py`：`ToolTruncationInfo` / `ToolResultMeta` / `ToolResultSuccess` / `ToolResultFailure` / `ToolResultEnvelope` 联合。
- `dayu/contracts/tool_await.py`：`ToolAwaitKind` StrEnum / `ToolAwaitSpec` / `ToolAwaitSnapshot`。
- `dayu/contracts/tool_outcome.py`：`ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolAwaitingOutcome` / `ToolExecutionOutcome`。
- `dayu/contracts/tool_executor.py`：`ToolExecutor` Protocol（仅 `execute(request) -> ToolExecutionOutcome`）。

依赖方向：`dayu/contracts/*` 之间允许相互引用；**禁止** import `dayu.engine.*` 或上层任何包。

#### 5.1.2 Engine 包 `dayu/engine/`

- `dayu/engine/__init__.py`：从 `dayu.engine.contracts` 与 `dayu.contracts` 双源 re-export，显式 `__all__` 白名单。
- `dayu/engine/contracts/__init__.py`：聚合 §1.2 子模块导出。
- `dayu/engine/contracts/messages.py`：`AgentMessageRole` / `SystemMessage` / `UserMessage` / `AssistantMessage` / `ToolMessage` / `AssistantToolCall` / `AgentMessage` 封闭联合。
- `dayu/engine/contracts/finish_reason.py`：`FinishReason` StrEnum。
- `dayu/engine/contracts/runner_spec.py`：`OpenAIReasoningEffort` StrEnum、四种 provider extension、`ProviderRequestExtension` 联合、`RunnerSpec`、`RunnerCallOptions`。
- `dayu/engine/contracts/agent_policy.py`：`AgentPolicy`（仅 `max_iterations: int`、`continuation_max_attempts: int`、`allow_tool_calls: bool`）。
- `dayu/engine/contracts/agent_run.py`：`AgentRunRequest`、四种终态 outcome、`AgentRunResult` 联合、`ContextBudgetSnapshot`、`RunResumeHint`。
- `dayu/engine/contracts/runner_events.py`：`RunnerEventType` + 8 个 Runner data + `RunnerEvent` + `RunnerEventData` 别名。
- `dayu/engine/contracts/engine_events.py`：`EngineEventType` + 全部 EngineEvent data + `EngineEvent` + `EngineEventData` 别名 + `TERMINAL_ENGINE_EVENT_TYPES`。
- `dayu/engine/contracts/runner.py`：`AsyncRunner` Protocol。

依赖方向：`dayu/engine/contracts/*` 单向 import `dayu/contracts/*`（如 `agent_run.AgentRunRequest` 引用 `dayu.contracts.tool_executor.ToolExecutor` 与 `dayu.contracts.cancellation.CancellationToken`，`engine_events.ToolCallRequestedData` 引用 `dayu.contracts.tool_call.ToolCallRequest`）；**严禁**反向。

### 5.2 测试（新增）

- `tests/__init__.py`
- `tests/contracts/__init__.py`
- `tests/contracts/test_package_exports.py`：`dayu.contracts.__all__` 等于 §1.1 白名单。
- `tests/contracts/test_import_boundary.py`：`dayu.contracts/` 下任何 `.py` 文件 AST 扫描禁止 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 及其子模块；当前 Phase 还禁止 `aiohttp` / `requests` / `httpx`。
- `tests/contracts/test_weak_typing_guard.py`：AST 扫描 `dayu/contracts/`；禁止 `Any` / `object` / 裸 `dict` / 裸 `list` / 无注解。
- `tests/contracts/test_protocols_surface.py`：`ToolExecutor` 仅 `execute`；`CancellationToken` 仅 `is_cancelled` / `cancel_reason` / `requested_at`。
- `tests/contracts/test_tool_outcome_exhaustive.py`：`match` + `assert_never` 覆盖 outcome 三分支。
- `tests/contracts/test_tool_result_envelope.py`：`ok` 判别字段；字段集合不含 `await_spec`。
- `tests/engine/__init__.py`
- `tests/engine/test_package_exports.py`：`dayu.engine.__all__` 等于 §1.1 ∪ §1.2 完整白名单（含 re-export）；禁止占位入口与实现类。
- `tests/engine/test_import_boundary.py`：`dayu/engine/` 下 AST 扫描；当前 Phase 禁止 `aiohttp` / `requests` / `httpx`；永久禁止 `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`（含子模块）/ `dayu.engine.tools` / `dayu.engine.processors` / 任何 `*tool_trace*` / `JsonlToolTraceStore`；**允许** import `dayu.contracts`。
- `tests/engine/test_weak_typing_guard.py`：AST 扫描 `dayu/engine/`。
- `tests/engine/test_engine_event_contract.py`：`EngineEventType` 与 EngineEvent data 一一对应；`TERMINAL_ENGINE_EVENT_TYPES` 集合精确等于四终态。
- `tests/engine/test_runner_event_contract.py`：`RunnerEventType` 与 Runner data 一一对应；`RunnerEvent` 字段不含 `session_id` / `run_id` / `sequence` / `event_id`。
- `tests/engine/test_metadata_boundary.py`：反射列举 EngineEventData / RunnerEventData 各 dataclass 字段；`EngineEvent.metadata` 注解为 `Mapping[str, JsonValue] | None`。
- `tests/engine/test_protocols_surface.py`：`AsyncRunner` 仅 `call` / `is_supports_tool_calling` / `close`；不存在 `set_tools` / `get_schemas` / `get_tool_display_info`。
- `tests/engine/test_agent_message_union.py`：四个具体 dataclass 实例 isinstance 测试针对 `(SystemMessage, UserMessage, AssistantMessage, ToolMessage)` 元组。

### 5.3 文档

- 默认不创建 `dayu/contracts/README.md`、`dayu/engine/README.md`、`dayu/README.md`、`tests/README.md`、根 `README.md`。
- 实施完成后，若汇报中确认已落地事实足以构成稳定开发手册条目，且不写未来内容，再单独提议创建相应 README。

## 6. 类型设计计划（Phase 0 contract 字段表）

### 6.1 通用约束

- 所有 dataclass 一律 `@dataclass(frozen=True, slots=True)`，全部字段必须显式注解。
- 联合一律 dataclass + PEP604 联合形成可辨识联合；穷尽匹配使用 `match` + `typing.assert_never`（pyright 守护）。
- 枚举一律 `enum.StrEnum`，显式 `class X(StrEnum): MEMBER = "value"` 形式（禁止函数式构造）。
- `metadata` 注解一律 `Mapping[str, JsonValue] | None`，禁止 `dict[str, Any]`。
- 禁止 `Any` / `object` / 未注解参数 / 未注解返回值 / 裸 `dict` / 裸 `list`。

### 6.2 字段定义（标注 host module）

> 注：表中「模块」一列指明该类型所在包；`dayu.contracts.*` 与 `dayu.engine.contracts.*` 严格遵守 §0 范式；StrEnum 成员名 / 值表见 §6.6。

属于 `dayu.contracts`：

- `dayu.contracts.json_value.JsonValue = None | bool | int | float | str | list["JsonValue"] | Mapping[str, "JsonValue"]`（仅类型别名；不实现 runtime validator / 序列化 helper）。
- `dayu.contracts.cancellation.CancellationToken` Protocol：`is_cancelled() -> bool`、`cancel_reason() -> str | None`、`requested_at() -> datetime | None`。**不**导出任何取消异常。
- `dayu.contracts.tool_schema.ToolParametersSchema(type: Literal["object"], properties: Mapping[str, JsonValue], required: tuple[str, ...], additional_properties: bool | None)`。
- `dayu.contracts.tool_schema.ToolFunctionSchema(name: str, description: str, parameters: ToolParametersSchema)`。
- `dayu.contracts.tool_schema.ToolSchema(type: Literal["function"], function: ToolFunctionSchema)`。
- `dayu.contracts.tool_call.ToolCallRequest(tool_call_id: str, name: str, arguments: Mapping[str, JsonValue], index_in_iteration: int)`。
- `dayu.contracts.tool_call.ToolExecutionContext(run_id: str, session_id: str, iteration_id: str, tool_call_id: str, index_in_iteration: int, timeout_seconds: float | None, cancellation_token: CancellationToken, correlation_id: str | None)`。
- `dayu.contracts.tool_call.ToolExecutionRequest(call: ToolCallRequest, context: ToolExecutionContext)`。
- `dayu.contracts.tool_result.ToolTruncationInfo(scope_token: str, scope_hash: str, has_more: bool, ttl_seconds: int | None)`。
- `dayu.contracts.tool_result.ToolResultMeta(tool_name: str, started_at: datetime, finished_at: datetime)`（**不**含 `attributes` 弱类型袋）。
- `dayu.contracts.tool_result.ToolResultSuccess(ok: Literal[True], value: JsonValue, truncation: ToolTruncationInfo | None, meta: ToolResultMeta | None)`。
- `dayu.contracts.tool_result.ToolResultFailure(ok: Literal[False], error: str, message: str, hint: str | None, meta: ToolResultMeta | None)`。
- `dayu.contracts.tool_result.ToolResultEnvelope = ToolResultSuccess | ToolResultFailure`。
- `dayu.contracts.tool_await.ToolAwaitKind` StrEnum（仅 `EXTERNAL_JOB`）。
- `dayu.contracts.tool_await.ToolAwaitSpec(await_kind: ToolAwaitKind, deadline: datetime | None, resume_token: str)`（**不**含 `attributes`）。
- `dayu.contracts.tool_await.ToolAwaitSnapshot(snapshot_id: str, captured_at: datetime)`（**不**含 `attributes`）。
- `dayu.contracts.tool_outcome.ToolCompletedOutcome(result: ToolResultSuccess)`。
- `dayu.contracts.tool_outcome.ToolFailedOutcome(result: ToolResultFailure)`。
- `dayu.contracts.tool_outcome.ToolAwaitingOutcome(await_spec: ToolAwaitSpec, snapshot: ToolAwaitSnapshot | None)`。
- `dayu.contracts.tool_outcome.ToolExecutionOutcome = ToolCompletedOutcome | ToolFailedOutcome | ToolAwaitingOutcome`。
- `dayu.contracts.tool_executor.ToolExecutor` Protocol：`async def execute(self, request: ToolExecutionRequest) -> ToolExecutionOutcome`。

属于 `dayu.engine.contracts`：

- `dayu.engine.contracts.messages.AgentMessageRole` StrEnum（成员见 §6.6）。
- `dayu.engine.contracts.messages.SystemMessage(role: Literal[AgentMessageRole.SYSTEM], content: str)`。
- `dayu.engine.contracts.messages.UserMessage(role: Literal[AgentMessageRole.USER], content: str)`。
- `dayu.engine.contracts.messages.AssistantToolCall(id: str, name: str, arguments: Mapping[str, JsonValue])`。
- `dayu.engine.contracts.messages.AssistantMessage(role: Literal[AgentMessageRole.ASSISTANT], content: str | None, reasoning_content: str | None, tool_calls: tuple[AssistantToolCall, ...])`。
- `dayu.engine.contracts.messages.ToolMessage(role: Literal[AgentMessageRole.TOOL], tool_call_id: str, content: str)`。
- `dayu.engine.contracts.messages.AgentMessage = SystemMessage | UserMessage | AssistantMessage | ToolMessage`（PEP604 联合 + `TypeAlias`）。
- `dayu.engine.contracts.finish_reason.FinishReason` StrEnum。
- `dayu.engine.contracts.runner_spec.OpenAIReasoningEffort` StrEnum。
- `dayu.engine.contracts.runner_spec.OpenAIReasoningExtension(reasoning_effort: OpenAIReasoningEffort)`。
- `dayu.engine.contracts.runner_spec.AnthropicThinkingExtension(enabled: bool, budget_tokens: int)`。
- `dayu.engine.contracts.runner_spec.GeminiThinkingExtension(thinking_budget: int, include_thoughts: bool)`。
- `dayu.engine.contracts.runner_spec.QwenThinkingExtension(enable_thinking: bool)`。
- `dayu.engine.contracts.runner_spec.ProviderRequestExtension = OpenAIReasoningExtension | AnthropicThinkingExtension | GeminiThinkingExtension | QwenThinkingExtension`。
- `dayu.engine.contracts.runner_spec.RunnerSpec(provider: str, model: str, endpoint: str, api_key_ref: str, headers: Mapping[str, str], supports_tool_calling: bool, supports_streaming: bool, default_timeout_seconds: float, max_retries: int, provider_request: ProviderRequestExtension | None)`。
- `dayu.engine.contracts.runner_spec.RunnerCallOptions(temperature: float | None, max_tokens: int | None, top_p: float | None, stream: bool)`。
- `dayu.engine.contracts.agent_policy.AgentPolicy(max_iterations: int, continuation_max_attempts: int, allow_tool_calls: bool)`。
- `dayu.engine.contracts.agent_run.ContextBudgetSnapshot(prompt_tokens: int, completion_tokens: int, total_tokens: int)`。
- `dayu.engine.contracts.agent_run.RunResumeHint(message: str)`（**不**含 `attributes`）。
- `dayu.engine.contracts.agent_run.AgentRunRequest(run_id: str, session_id: str, messages: tuple[AgentMessage, ...], stream: bool, disable_tools: bool, runner_spec: RunnerSpec, runner_options: RunnerCallOptions, agent_policy: AgentPolicy, tool_schemas: tuple[ToolSchema, ...], tool_executor: ToolExecutor, cancellation_token: CancellationToken)`（`ToolSchema` / `ToolExecutor` / `CancellationToken` 来自 `dayu.contracts`）。
- `dayu.engine.contracts.agent_run.EngineRunOutcomeFinalAnswer / Failed / Cancelled / Suspended` 与 `AgentRunResult` 联合（字段同 §6.5）。
- `dayu.engine.contracts.runner.AsyncRunner` Protocol：`def call(self, messages: Sequence[AgentMessage], options: RunnerCallOptions, tools: Sequence[ToolSchema]) -> AsyncIterator[RunnerEvent]`、`def is_supports_tool_calling(self) -> bool`、`async def close(self) -> None`。
- `dayu.engine.contracts.runner_events.*`：见 §6.3。
- `dayu.engine.contracts.engine_events.*`：见 §6.4。

### 6.3 RunnerEvent data 字段（`dayu.engine.contracts.runner_events`）

- `RunnerContentDeltaData(delta: str)`。
- `RunnerReasoningDeltaData(delta: str)`。
- `RunnerToolCallDeltaData(tool_call_index: int, tool_call_id: str | None, name_delta: str | None, arguments_delta: str | None)`。
- `RunnerToolCallsCompletedData(tool_calls: tuple[ToolCallRequest, ...])`（`ToolCallRequest` 来自 `dayu.contracts.tool_call`）。
- `RunnerContentCompletedData(content: str | None, reasoning_content: str | None, finish_reason: FinishReason)`。
- `RunnerUsageRecordedData(prompt_tokens: int, completion_tokens: int, total_tokens: int)`。
- `RunnerProtocolErrorData(error_code: str, message: str, provider_request_id: str | None, raw_payload: JsonValue | None)`（`JsonValue` 来自 `dayu.contracts.json_value`）。
- `RunnerDoneData(finish_reason: FinishReason)`。
- `RunnerEventData = ` 上述全部联合。
- `RunnerEvent(type: RunnerEventType, data: RunnerEventData, occurred_at: datetime)`。**不含** `session_id` / `run_id` / `sequence` / `event_id`。

### 6.4 EngineEvent data 字段（`dayu.engine.contracts.engine_events`）

- `IterationStartedData(iteration_id: str, iteration_index: int, message_count: int)`。
- `ContentDeltaData(iteration_id: str, delta: str)`。
- `ReasoningDeltaData(iteration_id: str, delta: str)`。
- `ContentCompleteData(iteration_id: str, content: str | None, reasoning_content: str | None, finish_reason: FinishReason)`。
- `ToolCallRequestedData(iteration_id: str, tool_call_id: str, name: str, arguments: Mapping[str, JsonValue], index_in_iteration: int)`。
- `ToolResultAcceptedData(iteration_id: str, tool_call_id: str, name: str, outcome: ToolCompletedOutcome | ToolFailedOutcome)`（outcome 类型来自 `dayu.contracts.tool_outcome`）。
- `ToolAwaitingData(iteration_id: str, tool_call_id: str, await_spec: ToolAwaitSpec)`（`ToolAwaitSpec` 来自 `dayu.contracts.tool_await`）。
- `ContextCompactionRequestedData(iteration_id: str, budget_state: ContextBudgetSnapshot, reason: str)`。
- `RunnerUsageData(iteration_id: str, prompt_tokens: int, completion_tokens: int, total_tokens: int)`。
- `ProviderProtocolErrorData(iteration_id: str, error_code: str, message: str, provider_request_id: str | None, raw_payload: JsonValue | None)`。
- `RunnerDoneEngineData(iteration_id: str, finish_reason: FinishReason)`（区别于 `RunnerDoneData`）。
- `FinalAnswerData(content: str, filtered: bool, finish_reason: FinishReason)`。
- `RunSuspendedData(reason: str, resume_hint: RunResumeHint | None)`。
- `RunCancelledData(reason: str, requested_at: datetime, accepted_at: datetime, finished_at: datetime)`。
- `RunFailedData(error_code: str, message: str, recoverable: bool)`。
- `EngineEventData = ` 上述全部联合。
- `EngineEvent(event_id: str, sequence: int, occurred_at: datetime, session_id: str, run_id: str, type: EngineEventType, data: EngineEventData, metadata: Mapping[str, JsonValue] | None)`。
- `TERMINAL_ENGINE_EVENT_TYPES: frozenset[EngineEventType] = frozenset({FINAL_ANSWER, RUN_FAILED, RUN_CANCELLED, RUN_SUSPENDED})`。

### 6.5 AgentRunRequest 与 AgentRunResult（`dayu.engine.contracts.agent_run`）

- `AgentRunRequest`：见 §6.2。
- `EngineRunOutcomeFinalAnswer(session_id: str, run_id: str, content: str, filtered: bool, finish_reason: FinishReason)`。
- `EngineRunOutcomeFailed(session_id: str, run_id: str, error_code: str, message: str, recoverable: bool)`。
- `EngineRunOutcomeCancelled(session_id: str, run_id: str, reason: str, requested_at: datetime, accepted_at: datetime, finished_at: datetime)`。
- `EngineRunOutcomeSuspended(session_id: str, run_id: str, reason: str, resume_hint: RunResumeHint | None)`。
- `AgentRunResult = EngineRunOutcomeFinalAnswer | EngineRunOutcomeFailed | EngineRunOutcomeCancelled | EngineRunOutcomeSuspended`。

### 6.6 StrEnum 成员名 / 值表（Phase 0 锁定）

`dayu.engine.contracts.messages.AgentMessageRole`：

- `SYSTEM = "system"`
- `USER = "user"`
- `ASSISTANT = "assistant"`
- `TOOL = "tool"`

`dayu.engine.contracts.finish_reason.FinishReason`：

- `STOP = "stop"`
- `LENGTH = "length"`
- `TOOL_CALLS = "tool_calls"`
- `CONTENT_FILTER = "content_filter"`
- `ERROR = "error"`

`dayu.engine.contracts.runner_spec.OpenAIReasoningEffort`：

- `LOW = "low"`
- `MEDIUM = "medium"`
- `HIGH = "high"`

`dayu.contracts.tool_await.ToolAwaitKind`：

- `EXTERNAL_JOB = "external_job"`

`dayu.engine.contracts.engine_events.EngineEventType`：

- `ITERATION_STARTED = "iteration_started"`
- `RUNNER_CONTENT_DELTA = "runner_content_delta"`
- `RUNNER_REASONING_DELTA = "runner_reasoning_delta"`
- `RUNNER_CONTENT_COMPLETED = "runner_content_completed"`
- `TOOL_CALL_REQUESTED = "tool_call_requested"`
- `TOOL_RESULT_ACCEPTED = "tool_result_accepted"`
- `TOOL_AWAITING = "tool_awaiting"`
- `CONTEXT_COMPACTION_REQUESTED = "context_compaction_requested"`
- `RUNNER_USAGE_RECORDED = "runner_usage_recorded"`
- `PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"`
- `RUNNER_DONE = "runner_done"`
- `FINAL_ANSWER = "final_answer"`
- `RUN_SUSPENDED = "run_suspended"`
- `RUN_CANCELLED = "run_cancelled"`
- `RUN_FAILED = "run_failed"`

`dayu.engine.contracts.runner_events.RunnerEventType`：

- `RUNNER_CONTENT_DELTA = "runner_content_delta"`
- `RUNNER_REASONING_DELTA = "runner_reasoning_delta"`
- `RUNNER_TOOL_CALL_DELTA = "runner_tool_call_delta"`
- `RUNNER_TOOL_CALLS_COMPLETED = "runner_tool_calls_completed"`
- `RUNNER_CONTENT_COMPLETED = "runner_content_completed"`
- `RUNNER_USAGE_RECORDED = "runner_usage_recorded"`
- `PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"`
- `RUNNER_DONE = "runner_done"`

## 7. 测试计划

### 7.1 责任划分

- pytest 负责：导出白名单、模块导入图、AST 静态扫描（弱类型 / 反向依赖）、dataclass 字段结构、enum-data 一一对应、协议表面成员、metadata 注解。
- pyright 负责：联合穷尽匹配（`assert_never`）、签名类型、可选性。pytest **不**试图替代 pyright 完成穷尽性证明。
- 验收标准：pytest 与 pyright 必须同时通过；二者缺一不可。

### 7.2 测试场景

#### 7.2.1 `tests/contracts/`

- `test_package_exports.py`
  - `set(dayu.contracts.__all__)` 与 §1.1 锁定白名单严格相等。
  - 断言 `CancelledError` 等取消异常名不在导出集合中、不可作为 `dayu.contracts` 属性访问。
- `test_import_boundary.py`
  - AST 扫描 `dayu/contracts/` 任意 `.py` 的 import 语句。
  - 永久禁止 import：`dayu.engine`（任意子模块）、`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins`（任意子模块）。
  - 当前 Phase 禁止：`aiohttp`、`requests`、`httpx`。
- `test_weak_typing_guard.py`
  - AST 扫描 `dayu/contracts/` 内函数签名、Protocol 方法、dataclass 字段注解；禁止 `Any` / `object` / 无注解 / 裸 `dict` / 裸 `list`。
- `test_protocols_surface.py`
  - 反射断言 `ToolExecutor` 仅有 `execute`；`CancellationToken` 仅有 `is_cancelled` / `cancel_reason` / `requested_at`。
- `test_tool_outcome_exhaustive.py`
  - `match` helper 覆盖 `ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolAwaitingOutcome` 三分支并以 `assert_never` 收口。
- `test_tool_result_envelope.py`
  - 构造 `ToolResultSuccess(ok=True,...)` / `ToolResultFailure(ok=False,...)` 并断言判别字段；
  - 反射断言 `ToolResultSuccess` / `ToolResultFailure` 字段集合**不**包含 `await_spec` / `await` / 任何指向 `ToolAwaitSpec` 的字段。

#### 7.2.2 `tests/engine/`

- `test_package_exports.py`
  - `set(dayu.engine.__all__)` 严格等于 §1.1 ∪ §1.2 完整白名单（即 Engine 包同时 re-export `dayu.contracts` 全部符号）。
  - 断言 `run_agent_messages` / `run_agent_and_wait` / `AsyncAgent` / `AsyncOpenAIRunner` / `CancelledError` 等不在导出集合中、不可作为 `dayu.engine` 属性访问。
- `test_import_boundary.py`
  - AST 扫描 `dayu/engine/` 任意 `.py`。
  - 当前 Phase 禁止 import：`aiohttp`、`requests`、`httpx`。
  - 永久禁止 import：`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins`（任意子模块）、`dayu.engine.tools`、`dayu.engine.processors`、任何 `*tool_trace*` / `JsonlToolTraceStore`。
  - 允许 import：`dayu.contracts`（任意子模块）。
- `test_weak_typing_guard.py`
  - AST 扫描 `dayu/engine/` 内 dataclass 字段、Protocol 方法、函数签名；禁止 `Any` / `object` / 无注解 / 裸 `dict` / 裸 `list`；禁止 `metadata: dict[str, Any]`，只允许 `Mapping[str, JsonValue] | None`。
- `test_engine_event_contract.py`
  - `EngineEventType` 枚举值与 EngineEvent data dataclass 一一对应表。
  - `TERMINAL_ENGINE_EVENT_TYPES == {FINAL_ANSWER, RUN_FAILED, RUN_CANCELLED, RUN_SUSPENDED}`。
  - `EngineEvent` 必填字段集合（无默认值）。
- `test_runner_event_contract.py`
  - `RunnerEventType` 与 Runner data 一一对应。
  - `RunnerEvent` 字段集合不含 `session_id` / `run_id` / `sequence` / `event_id`。
- `test_metadata_boundary.py`
  - 反射列举 EngineEventData / RunnerEventData 各 dataclass 字段；断言 `usage` 拆分字段、`provider_request_id`、`raw_payload`、`error_code`、`finish_reason` 直接出现在对应 data dataclass 中。
  - `EngineEvent.metadata` 注解为 `Mapping[str, JsonValue] | None`。
- `test_protocols_surface.py`
  - 反射断言 `AsyncRunner` 仅 `call` / `is_supports_tool_calling` / `close`；不存在 `set_tools` / `get_schemas` / `get_tool_display_info`。
- `test_agent_message_union.py`
  - 对 `SystemMessage` / `UserMessage` / `AssistantMessage` / `ToolMessage` 分别构造实例，断言 isinstance 针对**具体 dataclass 元组**（不依赖 PEP604 union 的运行时 isinstance 行为）。
  - 反射断言四个 dataclass 字段集合精确符合 §6.2。

### 7.3 失败路径测试

- 任一包根 `__all__` 增 / 减项 → 测试失败。
- `dayu.contracts` 任意模块 `from dayu.engine` → 测试失败。
- Engine 任意模块 `from dayu.host` / `from dayu.fins` / `from dayu.engine.tools` 等违禁导入 → 测试失败。
- contract 中出现 `Any` / `object` / 未注解 → 测试失败。
- `ToolResultEnvelope` 字段误加 `await_spec` → 测试失败。

## 8. pyright 计划

- 沿用 `pyrightconfig.json` 现有配置（`pythonVersion: 3.11`，include `dayu`、`tests`、`utils`）。
- 所有 dataclass 字段、Protocol 方法、函数签名必须显式类型注解。
- 联合穷尽匹配使用 `typing.assert_never`；任意未处理子类型 → pyright error。
- TypeAlias（`EngineEventData` / `RunnerEventData` / `ToolExecutionOutcome` / `AgentMessage` / `AgentRunResult` / `ProviderRequestExtension` / `JsonValue` / `ToolResultEnvelope`）使用 `from typing import TypeAlias` 显式标注。
- 实施完成命令：`source .venv/bin/activate && pyright`，要求 0 errors / 0 warnings 增量。
- 若发现既存 pyright 错误（理论上无，因 NEW 仓库 `dayu/` 为空），必须立即修复。

## 9. README / docs 同步判断

- 默认**不**创建 `dayu/contracts/README.md`、`dayu/engine/README.md`、`dayu/README.md`、`tests/README.md`、根 `README.md`。
- 不修改 `docs/engine/*` 中现有 design / migration-plan / review 文档。
- 实施完成后若需要文档化，仅记录已落地事实，不写「待 Phase 1+ 实施」、不写未来路线图。
- 在 PR / 汇报中说明本 Phase 不更新 README 的原因（contract 草案阶段，无用户向能力变化）。

## 10. 风险与停止条件

必须停止并回到总控的情况：

- 实施过程中发现 §6 字段表的某字段类型在 design.md 与 OLD 证据之间出现新冲突。
- 发现某 Phase 0 contract 必须依赖未列入 Phase 0 的实现。
- 发现 `dayu.contracts` 任一类型不可避免反向依赖 `dayu.engine.contracts`（违反 §0 范式与 §5.1 依赖方向）。
- 发现 `import boundary` 禁止列表存在歧义。
- 发现 `AgentMessage` 联合在 Phase 1 Runner 落地前已不足以表达 OLD 行为。
- 发现 `ProviderRequestExtension` 已知 provider 字段不足。

需用户 / 总控确认的项（在等待确认环节解决）：

- §0 / §1.1 / §1.2 契约分层范式与具体落点是否被总控 / 用户最终接受（核心决策点）。
- §1.3 `dayu/engine/__init__.py` 同时 re-export §1.1 与 §1.2 的导出策略是否被接受（避免调用方在两个 import 路径之间二选一；不构成兼容 wrapper）。
- §6.4 EngineEvent data 命名 `RunnerDoneEngineData`（与 RunnerEvent 侧 `RunnerDoneData` 区分）。
- §6.2 `ToolAwaitKind` 仅落地保守初始成员 `EXTERNAL_JOB`。
- §6.2 `AgentMessage` 四元封闭联合作为 Phase 0 稳定最小形态。
- `ToolExecutionContext.correlation_id: str | None` 进入公共契约（语义上仅作中性关联，不得变成 ToolTraceRecorder 私有入口）。
- Phase 0 全面禁止 `dayu.fins` 任意子模块导入。
- Phase 0 默认不创建 `dayu/contracts/README.md` / `dayu/engine/README.md`。

已收口、不再作为待确认项的：

- `ToolResultEnvelope` 保留 `ok: Literal[True] / Literal[False]` 判别字段。
- `ToolResultMeta` / `ToolAwaitSpec` / `ToolAwaitSnapshot` / `RunResumeHint` 全部移除 `attributes` 字段。
- StrEnum 一律 `class X(StrEnum): MEMBER = "value"` 形式落地，并以 §6.6 显式成员表为唯一真源。
- `AgentMessage` 联合的 isinstance 测试改为针对四个具体 dataclass 的元组，不依赖 PEP604 union 的运行时 isinstance 行为。
- 取消公共终态由 `RunCancelledData` / `EngineRunOutcomeCancelled` 表达；`dayu.contracts` / `dayu.engine` 均**不**导出取消异常。

## 11. 验收标准

客观信号：

- `dayu/contracts/`、`dayu/engine/contracts/` 与 `tests/contracts/`、`tests/engine/` 已建立，均被 pyright include。
- `python -c "import dayu.contracts; print(sorted(dayu.contracts.__all__))"` 输出仅包含 §1.1 锁定的 contract 类型集合。
- `python -c "import dayu.engine; print(sorted(dayu.engine.__all__))"` 输出仅包含 §1.1 ∪ §1.2 锁定集合。
- `python -c "from dayu.engine import run_agent_messages"` 抛 ImportError。
- `python -c "from dayu.engine import CancelledError"` 抛 ImportError。
- `python -c "from dayu.contracts import CancelledError"` 抛 ImportError。
- `pytest tests/contracts tests/engine -q` 全部通过。
- `pyright` 0 errors / 0 warnings 增量。
- 架构测试（包根导出、import boundary、weak typing、event/runner contract、outcome 穷尽、协议表面、metadata 边界、AgentMessage 联合）均通过。
- 没有任何 OLD 兼容 wrapper / facade / 兼容 re-export；`dayu/engine/__init__.py` 中对 `dayu.contracts` 的 re-export 仅作为 §1.3 所述结构契约导出。
- 没有 `Any` / `object` / 未注解参数 / 未注解返回值。
- README 未更新；汇报中已说明原因。

## Critical Files

- 新建公共契约：`dayu/contracts/__init__.py`、`dayu/contracts/*.py`（按 §5.1.1）。
- 新建 Engine 契约：`dayu/engine/__init__.py`、`dayu/engine/contracts/__init__.py`、`dayu/engine/contracts/*.py`（按 §5.1.2）。
- 新建测试：`tests/contracts/test_*.py`、`tests/engine/test_*.py`（按 §5.2）。

## Verification

1. `source .venv/bin/activate`
2. `pytest tests/contracts tests/engine -q` → 全部通过。
3. `pyright` → 0 errors / 0 warnings 增量。
4. 手动：
   - `python -c "from dayu.contracts import CancellationToken, ToolExecutor, ToolExecutionOutcome, ToolResultEnvelope, JsonValue"` 成功。
   - `python -c "from dayu.engine import EngineEvent, EngineEventType, AgentRunRequest, AsyncRunner, AgentMessage"` 成功。
   - `python -c "from dayu.engine import ToolExecutor, ToolExecutionOutcome, CancellationToken"` 成功（来自 §1.3 re-export）。
   - `python -c "from dayu.engine import run_agent_messages"` / `from dayu.engine import CancelledError` 失败。
5. 汇报：改了什么、验证了什么、未覆盖项。
6. 等 review Agent 审查；review 通过等总控；总控通过等用户确认；用户确认后才提交 GitHub。
