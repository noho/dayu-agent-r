# Engine Phase 0 实施计划

本计划是 Engine 迁移 Phase 0 的实施依据，已根据 `docs/engine/phase0-plan-review.md` 修订。计划只覆盖 pure contracts 与 import boundary tests；未确认或 review 要求降级的项一律从 Phase 0 移除，留给后续 Phase。

## 1. Phase 范围

- 在 NEW 仓库新建 Engine 包骨架 `dayu/engine/`、`dayu/engine/contracts/` 与测试骨架 `tests/engine/`。
- 落地以下强类型 pure contracts，全部为代码真源：
  - 事件层：`EngineEventType`（StrEnum）、`EngineEvent`、各 EngineEvent data dataclass：`IterationStartedData` / `ContentDeltaData` / `ReasoningDeltaData` / `ContentCompleteData` / `ToolCallRequestedData` / `ToolResultAcceptedData` / `ToolAwaitingData` / `ContextCompactionRequestedData` / `RunnerUsageData` / `ProviderProtocolErrorData` / `RunnerDoneEngineData` / `FinalAnswerData` / `RunSuspendedData` / `RunCancelledData` / `RunFailedData`，以及类型别名 `EngineEventData`。Engine 侧 `runner_done` 事件 data 与 Runner 侧 `RunnerDoneData` 是**不同 dataclass**，命名固定使用 `RunnerDoneEngineData` 以避免冲突。
  - Runner 事件层：`RunnerEventType`、`RunnerEvent`、`RunnerContentDeltaData` / `RunnerReasoningDeltaData` / `RunnerToolCallDeltaData` / `RunnerToolCallsCompletedData` / `RunnerContentCompletedData` / `RunnerUsageRecordedData` / `RunnerProtocolErrorData` / `RunnerDoneData`，类型别名 `RunnerEventData`。
  - 工具调用层：`ToolSchema` / `ToolFunctionSchema` / `ToolParametersSchema`、`ToolCallRequest`、`ToolExecutionContext`、`ToolExecutionRequest`、`ToolResultSuccess` / `ToolResultFailure` / `ToolResultEnvelope`（联合，**保留 `ok: Literal[True/False]`**）、`ToolTruncationInfo`、`ToolResultMeta`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolAwaitingOutcome` / `ToolExecutionOutcome` 联合。
  - 协议层：`ToolExecutor`（仅 `execute(request) -> ToolExecutionOutcome`）、`AsyncRunner`（仅 `call(messages, options, tools)` / `is_supports_tool_calling()` / `close()`）、`CancellationToken`、`CancelledError`。
  - 配置 / 请求层：`AgentRunRequest`、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`AgentMessage`（封闭联合）、`JsonValue`、`AgentRunResult`（封闭联合：四种终态 outcome）。
  - Provider extension 层：仅落地已知 provider 强类型扩展：`OpenAIReasoningExtension` / `AnthropicThinkingExtension` / `GeminiThinkingExtension` / `QwenThinkingExtension` / `ProviderRequestExtension` 联合。
- 建立包根 `dayu/engine/__init__.py` 导出策略：仅导出 contract 类型，**不**导出函数式入口、实现类、占位函数。
- 建立架构测试套：包根导出白名单、import boundary（区分当前 Phase 与永久禁入）、weak typing 守卫、event/outcome 一一对应、协议表面、metadata 边界。

## 2. 明确不做什么

- 不实现 `AsyncAgent`、`AsyncOpenAIRunner`、`AsyncCliRunner`。
- 不导出 `run_agent_messages` / `run_agent_and_wait`（即使占位形态也禁止）。
- 不迁移 ToolRegistry / ToolRuntime / argument_validator / duplicate_call_guard / truncation_manager / runner_factory / sse_parser / xml_extractor / reasoning_protocol / doc_access_policy / toolset_registrars。
- 不迁移 doc/web/fins tools；不迁移 processors；不迁移 ToolTraceRecorder / JsonlToolTraceStore。
- 不实现取消治理增强、watchdog、超时升级、lost 判定。
- 不实现 ContextBudgetState 的运算逻辑；本 Phase 仅落地 `ContextBudgetSnapshot` 最小快照 dataclass，仅作为 `ContextCompactionRequestedData.budget_state` 字段类型，不含计算逻辑、不含 soft/hard 阈值消费。
- 不落地 `ValidatedProviderRequestExtension`（按 review §4.2 推迟，只保留四种已知 provider 强类型扩展；待配置 adapter 阶段单独评审引入）。
- 不落地 `FallbackStrategy`、`FinalAnswerFilter`、`ResponseFormat`、`ContextBudgetLimits` 等暂无消费方的辅助类型；按 review §3.2 进入“待引入名单”，留给消费它的 Phase。
- 不写 README 用户向手册内容；默认不创建 `dayu/engine/README.md`。

## 3. 直接依据

- `docs/engine/design.md`：第 2.7 / 8 / 9 / 14.1 / 14.2 / 14.3 / 14.4 节。
- `docs/engine/review.md`：第 8 节最小迁移切片清单。
- `docs/engine/migration-plan.md`：第 4 节 Phase 0 行；第 5 节详细计划；第 12 节跨阶段架构测试。
- `docs/engine/migration-plan-review.md`：第 4.2 节（禁止 Phase 0 导出占位）；第 5.2 节（README 检查而非必改）。
- `docs/engine/phase0-plan-review.md`：本计划修订依据。
- `AGENTS.md` / `CLAUDE.md`：架构、编码、思考纪律硬约束。

## 4. OLD 可复用片段（仅作为字段语义和场景证据来源，禁止机械搬迁）

- `~/workspace/dayu-agent/dayu/engine/events.py`：`EventType` 枚举值、`StreamEvent` 字段使用场景。
- `~/workspace/dayu-agent/dayu/engine/tool_result.py`：`ok` / `value` / `error` / `message` / `hint` / `meta` / `truncation` 字段语义。
- `~/workspace/dayu-agent/dayu/engine/protocols.py`：`AsyncRunner` 旧协议字段对照。
- `~/workspace/dayu-agent/dayu/engine/cancellation.py`：协作式取消 token 接口形态。
- `~/workspace/dayu-agent/dayu/contracts/protocols.py`：`ToolExecutionContext` 字段语义。
- `~/workspace/dayu-agent/dayu/engine/context_budget.py`：仅参考 budget snapshot 字段命名。

## 5. NEW 文件变更计划

### 5.1 生产代码（新增）

- `dayu/__init__.py`
- `dayu/engine/__init__.py`：仅 re-export contract 类型；显式 `__all__` 白名单。
- `dayu/engine/contracts/__init__.py`：聚合子模块导出。
- `dayu/engine/contracts/json_value.py`：`JsonValue` 严格 JSON 联合。
- `dayu/engine/contracts/messages.py`：`AgentMessageRole` / `SystemMessage` / `UserMessage` / `AssistantMessage` / `ToolMessage` / `AssistantToolCall` / `AgentMessage` 封闭联合。
- `dayu/engine/contracts/cancellation.py`：`CancellationToken` Protocol、`CancelledError`。
- `dayu/engine/contracts/tool_schema.py`：`ToolSchema` / `ToolFunctionSchema` / `ToolParametersSchema`。
- `dayu/engine/contracts/tool_call.py`：`ToolCallRequest`、`ToolExecutionContext`、`ToolExecutionRequest`。
- `dayu/engine/contracts/tool_result.py`：`ToolTruncationInfo` / `ToolResultMeta` / `ToolResultSuccess` / `ToolResultFailure` / `ToolResultEnvelope` 联合。
- `dayu/engine/contracts/tool_await.py`：`ToolAwaitSpec` / `ToolAwaitSnapshot`。
- `dayu/engine/contracts/tool_outcome.py`：`ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolAwaitingOutcome` / `ToolExecutionOutcome`。
- `dayu/engine/contracts/tool_executor.py`：`ToolExecutor` Protocol。
- `dayu/engine/contracts/runner_events.py`：RunnerEventType + 各 Runner data dataclass + `RunnerEvent` + `RunnerEventData` 别名。
- `dayu/engine/contracts/engine_events.py`：EngineEventType + 各 Engine data dataclass + `EngineEvent` + `EngineEventData` 别名 + `TERMINAL_ENGINE_EVENT_TYPES` 常量集合。
- `dayu/engine/contracts/runner_spec.py`：`OpenAIReasoningExtension` / `AnthropicThinkingExtension` / `GeminiThinkingExtension` / `QwenThinkingExtension` / `ProviderRequestExtension` 联合、`RunnerSpec`、`RunnerCallOptions`。
- `dayu/engine/contracts/runner.py`：`AsyncRunner` Protocol。
- `dayu/engine/contracts/agent_policy.py`：`AgentPolicy`（仅 `max_iterations: int`、`continuation_max_attempts: int`、`allow_tool_calls: bool`；其它策略字段待消费 Phase 引入）。
- `dayu/engine/contracts/agent_run.py`：`AgentRunRequest`、四种终态 `EngineRunOutcomeFinalAnswer` / `EngineRunOutcomeFailed` / `EngineRunOutcomeCancelled` / `EngineRunOutcomeSuspended`、`AgentRunResult` 联合、`ContextBudgetSnapshot`、`RunResumeHint`。
- `dayu/engine/contracts/finish_reason.py`：`FinishReason` StrEnum（覆盖 `stop` / `length` / `tool_calls` / `content_filter` / `error`）。

### 5.2 测试（新增）

- `tests/__init__.py`
- `tests/engine/__init__.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_import_boundary.py`
- `tests/engine/test_weak_typing_guard.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_runner_event_contract.py`
- `tests/engine/test_tool_outcome_exhaustive.py`
- `tests/engine/test_tool_result_envelope.py`
- `tests/engine/test_metadata_boundary.py`
- `tests/engine/test_protocols_surface.py`
- `tests/engine/test_agent_message_union.py`

### 5.3 文档

- 默认不创建 `dayu/engine/README.md`、`dayu/README.md`、`tests/README.md`、根 `README.md`。
- 实施完成后，若汇报中确认已落地事实足以构成稳定开发手册条目，且不写未来内容，再单独提议创建 `dayu/engine/README.md`。

## 6. 类型设计计划（Phase 0 contract 字段表）

### 6.1 通用约束

- 所有 dataclass 一律 `@dataclass(frozen=True, slots=True)`，全部字段必须显式注解。
- 联合一律 dataclass + PEP604 联合形成可辨识联合；穷尽匹配使用 `match` + `typing.assert_never`（pyright 守护）。
- 枚举一律 `enum.StrEnum`。
- `metadata` 注解一律 `Mapping[str, JsonValue] | None`，禁止 `dict[str, Any]`。
- 禁止 `Any` / `object` / 未注解参数 / 未注解返回值 / 裸 `dict` / 裸 `list`。

### 6.2 字段定义

> 注：以下 `StrEnum(...)` 写法是字段表速记。落地代码必须使用 Python 3.11 `enum.StrEnum` 显式 class 定义，每个成员名为 SCREAMING_SNAKE_CASE，值为下表 lower_snake_case 字符串。enum 成员名/值表见 §6.6。

- `JsonValue = None | bool | int | float | str | list["JsonValue"] | Mapping[str, "JsonValue"]`（不可变结构使用 Mapping，构造侧用 dict 即可）。Phase 0 仅落地类型别名，**不**实现 runtime validator、不实现序列化 helper；review §5.2 提到的 bool/int 区分只在后续 Phase 真正消费 JsonValue 时再处理。
- `AgentMessageRole`：StrEnum，成员见 §6.6。
- `SystemMessage(role: Literal[AgentMessageRole.SYSTEM], content: str)`。
- `UserMessage(role: Literal[AgentMessageRole.USER], content: str)`。
- `AssistantToolCall(id: str, name: str, arguments: Mapping[str, JsonValue])`。
- `AssistantMessage(role: Literal[AgentMessageRole.ASSISTANT], content: str | None, reasoning_content: str | None, tool_calls: tuple[AssistantToolCall, ...])`。
- `ToolMessage(role: Literal[AgentMessageRole.TOOL], tool_call_id: str, content: str)`。
- `AgentMessage = SystemMessage | UserMessage | AssistantMessage | ToolMessage`（PEP 604 联合 + `TypeAlias`）。
- `CancellationToken` Protocol：`is_cancelled() -> bool`、`cancel_reason() -> str | None`、`requested_at() -> datetime | None`。
- `ToolParametersSchema(type: Literal["object"], properties: Mapping[str, JsonValue], required: tuple[str, ...], additional_properties: bool | None)`。
- `ToolFunctionSchema(name: str, description: str, parameters: ToolParametersSchema)`。
- `ToolSchema(type: Literal["function"], function: ToolFunctionSchema)`。
- `ToolCallRequest(tool_call_id: str, name: str, arguments: Mapping[str, JsonValue], index_in_iteration: int)`。
- `ToolExecutionContext(run_id: str, session_id: str, iteration_id: str, tool_call_id: str, index_in_iteration: int, timeout_seconds: float | None, cancellation_token: CancellationToken, correlation_id: str | None)`。
- `ToolExecutionRequest(call: ToolCallRequest, context: ToolExecutionContext)`。
- `ToolTruncationInfo(scope_token: str, scope_hash: str, has_more: bool, ttl_seconds: int | None)`。
- `ToolResultMeta(tool_name: str, started_at: datetime, finished_at: datetime)`。**移除** `attributes` 字段；review §4.3 / §5.2 已指出弱类型语义袋风险，Phase 0 不预留任意属性袋。后续若需要观测扩展，由专门 EngineEvent metadata 承载或在消费 Phase 单独评审。
- `ToolResultSuccess(ok: Literal[True], value: JsonValue, truncation: ToolTruncationInfo | None, meta: ToolResultMeta | None)`。
- `ToolResultFailure(ok: Literal[False], error: str, message: str, hint: str | None, meta: ToolResultMeta | None)`。
- `ToolResultEnvelope = ToolResultSuccess | ToolResultFailure`。
- `ToolAwaitKind`：StrEnum，Phase 0 仅落地一个保守初始成员（见 §6.6），用于把 `await_kind` 收窄为枚举，避免 review §5.1 指出的 `str` 退化风险。
- `ToolAwaitSpec(await_kind: ToolAwaitKind, deadline: datetime | None, resume_token: str)`。**移除** `attributes` 字段（review §4.3 弱类型袋风险）。
- `ToolAwaitSnapshot(snapshot_id: str, captured_at: datetime)`。**移除** `attributes` 字段。
- `ToolCompletedOutcome(result: ToolResultSuccess)`。
- `ToolFailedOutcome(result: ToolResultFailure)`。
- `ToolAwaitingOutcome(await_spec: ToolAwaitSpec, snapshot: ToolAwaitSnapshot | None)`。
- `ToolExecutionOutcome = ToolCompletedOutcome | ToolFailedOutcome | ToolAwaitingOutcome`。
- `ToolExecutor` Protocol：`async def execute(self, request: ToolExecutionRequest) -> ToolExecutionOutcome`。
- `OpenAIReasoningEffort`：StrEnum，成员见 §6.6。
- `OpenAIReasoningExtension(reasoning_effort: OpenAIReasoningEffort)`。
- `AnthropicThinkingExtension(enabled: bool, budget_tokens: int)`。
- `GeminiThinkingExtension(thinking_budget: int, include_thoughts: bool)`。
- `QwenThinkingExtension(enable_thinking: bool)`。
- `ProviderRequestExtension = OpenAIReasoningExtension | AnthropicThinkingExtension | GeminiThinkingExtension | QwenThinkingExtension`。
- `RunnerSpec(provider: str, model: str, endpoint: str, api_key_ref: str, headers: Mapping[str, str], supports_tool_calling: bool, supports_streaming: bool, default_timeout_seconds: float, max_retries: int, provider_request: ProviderRequestExtension | None)`。
- `RunnerCallOptions(temperature: float | None, max_tokens: int | None, top_p: float | None, stream: bool)`（response_format 等待消费 Phase 引入）。
- `AsyncRunner` Protocol：`def call(self, messages: Sequence[AgentMessage], options: RunnerCallOptions, tools: Sequence[ToolSchema]) -> AsyncIterator[RunnerEvent]`、`def is_supports_tool_calling(self) -> bool`、`async def close(self) -> None`。
- `AgentPolicy(max_iterations: int, continuation_max_attempts: int, allow_tool_calls: bool)`。
- `ContextBudgetSnapshot(prompt_tokens: int, completion_tokens: int, total_tokens: int)`。
- `RunResumeHint(message: str)`。**移除** `attributes` 字段（同上）。
- `FinishReason`：StrEnum，成员见 §6.6。

### 6.3 RunnerEvent data 字段

- `RunnerContentDeltaData(delta: str)`。
- `RunnerReasoningDeltaData(delta: str)`。
- `RunnerToolCallDeltaData(tool_call_index: int, tool_call_id: str | None, name_delta: str | None, arguments_delta: str | None)`。
- `RunnerToolCallsCompletedData(tool_calls: tuple[ToolCallRequest, ...])`。
- `RunnerContentCompletedData(content: str | None, reasoning_content: str | None, finish_reason: FinishReason)`。
- `RunnerUsageRecordedData(prompt_tokens: int, completion_tokens: int, total_tokens: int)`。
- `RunnerProtocolErrorData(error_code: str, message: str, provider_request_id: str | None, raw_payload: JsonValue | None)`。
- `RunnerDoneData(finish_reason: FinishReason)`。
- `RunnerEventData = ` 上述全部联合。
- `RunnerEvent(type: RunnerEventType, data: RunnerEventData, occurred_at: datetime)`。**不含** `session_id` / `run_id` / `sequence` / `event_id`。

### 6.4 EngineEvent data 字段

- `IterationStartedData(iteration_id: str, iteration_index: int, message_count: int)`。
- `ContentDeltaData(iteration_id: str, delta: str)`。
- `ReasoningDeltaData(iteration_id: str, delta: str)`。
- `ContentCompleteData(iteration_id: str, content: str | None, reasoning_content: str | None, finish_reason: FinishReason)`。
- `ToolCallRequestedData(iteration_id: str, tool_call_id: str, name: str, arguments: Mapping[str, JsonValue], index_in_iteration: int)`。
- `ToolResultAcceptedData(iteration_id: str, tool_call_id: str, name: str, outcome: ToolCompletedOutcome | ToolFailedOutcome)`。
- `ToolAwaitingData(iteration_id: str, tool_call_id: str, await_spec: ToolAwaitSpec)`。
- `ContextCompactionRequestedData(iteration_id: str, budget_state: ContextBudgetSnapshot, reason: str)`。
- `RunnerUsageData(iteration_id: str, prompt_tokens: int, completion_tokens: int, total_tokens: int)`。
- `ProviderProtocolErrorData(iteration_id: str, error_code: str, message: str, provider_request_id: str | None, raw_payload: JsonValue | None)`。
- `RunnerDoneEngineData(iteration_id: str, finish_reason: FinishReason)`（避免与 RunnerEvent 同名 dataclass 冲突）。
- `FinalAnswerData(content: str, filtered: bool, finish_reason: FinishReason)`。
- `RunSuspendedData(reason: str, resume_hint: RunResumeHint | None)`。
- `RunCancelledData(reason: str, requested_at: datetime, accepted_at: datetime, finished_at: datetime)`。
- `RunFailedData(error_code: str, message: str, recoverable: bool)`。
- `EngineEventData = ` 上述全部联合。
- `EngineEvent(event_id: str, sequence: int, occurred_at: datetime, session_id: str, run_id: str, type: EngineEventType, data: EngineEventData, metadata: Mapping[str, JsonValue] | None)`。
- `TERMINAL_ENGINE_EVENT_TYPES: frozenset[EngineEventType] = frozenset({FINAL_ANSWER, RUN_FAILED, RUN_CANCELLED, RUN_SUSPENDED})`。

### 6.5 AgentRunRequest 与 AgentRunResult

- `AgentRunRequest(run_id: str, session_id: str, messages: tuple[AgentMessage, ...], stream: bool, disable_tools: bool, runner_spec: RunnerSpec, runner_options: RunnerCallOptions, agent_policy: AgentPolicy, tool_schemas: tuple[ToolSchema, ...], tool_executor: ToolExecutor, cancellation_token: CancellationToken)`。
- `EngineRunOutcomeFinalAnswer(session_id, run_id, content: str, filtered: bool, finish_reason: FinishReason)`。
- `EngineRunOutcomeFailed(session_id, run_id, error_code: str, message: str, recoverable: bool)`。
- `EngineRunOutcomeCancelled(session_id, run_id, reason: str, requested_at: datetime, accepted_at: datetime, finished_at: datetime)`。
- `EngineRunOutcomeSuspended(session_id, run_id, reason: str, resume_hint: RunResumeHint | None)`。
- `AgentRunResult = EngineRunOutcomeFinalAnswer | EngineRunOutcomeFailed | EngineRunOutcomeCancelled | EngineRunOutcomeSuspended`。

### 6.6 StrEnum 成员名/值表（Phase 0 锁定）

所有 enum 一律 `class X(StrEnum): MEMBER = "value"` 形式落地，不允许函数式 `StrEnum("X", ...)` 构造。

`AgentMessageRole`：

- `SYSTEM = "system"`
- `USER = "user"`
- `ASSISTANT = "assistant"`
- `TOOL = "tool"`

`FinishReason`：

- `STOP = "stop"`
- `LENGTH = "length"`
- `TOOL_CALLS = "tool_calls"`
- `CONTENT_FILTER = "content_filter"`
- `ERROR = "error"`

`OpenAIReasoningEffort`：

- `LOW = "low"`
- `MEDIUM = "medium"`
- `HIGH = "high"`

`ToolAwaitKind`（Phase 0 仅落地保守初始集合）：

- `EXTERNAL_JOB = "external_job"`

`EngineEventType`：

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

`RunnerEventType`：

- `RUNNER_CONTENT_DELTA = "runner_content_delta"`
- `RUNNER_REASONING_DELTA = "runner_reasoning_delta"`
- `RUNNER_TOOL_CALL_DELTA = "runner_tool_call_delta"`
- `RUNNER_TOOL_CALLS_COMPLETED = "runner_tool_calls_completed"`
- `RUNNER_CONTENT_COMPLETED = "runner_content_completed"`
- `RUNNER_USAGE_RECORDED = "runner_usage_recorded"`
- `PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"`
- `RUNNER_DONE = "runner_done"`

## 7. 测试计划

### 7.1 责任划分（review §4.3 修正）

- pytest 负责：导出白名单、模块导入图、AST 静态扫描（弱类型 / 反向依赖）、dataclass 字段结构、enum-data 一一对应、协议表面成员、metadata 注解。
- pyright 负责：联合穷尽匹配（`assert_never`）、签名类型、可选性。pytest **不**试图替代 pyright 完成穷尽性证明。
- 验收标准：pytest 与 pyright 必须同时通过；二者缺一不可。

### 7.2 测试场景

- `test_package_exports.py`
  - `set(dayu.engine.__all__)` 与 Phase 0 锁定白名单严格相等。
  - 断言 `run_agent_messages` / `run_agent_and_wait` / `AsyncAgent` / `AsyncOpenAIRunner` 等不在导出集合中。
- `test_import_boundary.py`
  - 标记为「Phase 0 当前禁止」（后续 Phase 可放开）：`aiohttp`、`requests`、`httpx`。
  - 标记为「Engine core 永久禁止」：`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins`（含全部子模块）、`dayu.engine.tools`、`dayu.engine.processors`、任何 `*tool_trace*` / `JsonlToolTraceStore`。
  - 通过 AST 扫描 `dayu/engine/` 下所有 `.py` 文件 import 语句实现，分组断言。
- `test_weak_typing_guard.py`
  - AST 扫描 `dayu/engine/contracts/` 内函数签名、Protocol 方法、dataclass 字段注解；禁止 `Any` / `object` / 无注解。
  - 禁止裸 `dict` / `list`（必须参数化）。
  - 禁止 `metadata: dict[str, Any]`；只允许 `Mapping[str, JsonValue] | None`。
- `test_engine_event_contract.py`
  - 断言 `EngineEventType` 枚举值与 EngineEvent data dataclass 一一对应表。
  - 断言 `TERMINAL_ENGINE_EVENT_TYPES == {FINAL_ANSWER, RUN_FAILED, RUN_CANCELLED, RUN_SUSPENDED}`。
  - 断言 `EngineEvent` 必填字段（无默认值）。
- `test_runner_event_contract.py`
  - RunnerEventType 与 RunnerEvent data 一一对应。
  - 断言 `RunnerEvent` dataclass 字段集合 **不**包含 `session_id` / `run_id` / `sequence` / `event_id`（强制由 Agent 提升时补齐）。
- `test_tool_outcome_exhaustive.py`
  - 提供一个最小 `match` helper，覆盖 `ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolAwaitingOutcome` 三分支并以 `assert_never` 收口；断言每分支返回值正确。pyright 负责守护新增子类型必须穷尽。
- `test_tool_result_envelope.py`
  - 构造 `ToolResultSuccess(ok=True,...)` / `ToolResultFailure(ok=False,...)`，断言类型判别成立。
  - 反射断言 `ToolResultSuccess` / `ToolResultFailure` 字段集合中**不**包含 `await_spec` / `await` / 任何指向 `ToolAwaitSpec` 的字段。
- `test_metadata_boundary.py`
  - 反射列举 EngineEventData / RunnerEventData 各 dataclass 字段；断言 `usage` 拆分字段（`prompt_tokens` 等）、`provider_request_id`、`raw_payload`、`error_code`、`finish_reason` 直接出现在对应 data dataclass 中。
  - 断言 `EngineEvent.metadata` 注解为 `Mapping[str, JsonValue] | None`。
- `test_protocols_surface.py`（review §5.3 修正）
  - 通过 `__dict__` 中用户定义的非下划线 callable 列表断言 `ToolExecutor` 仅有 `execute`、`AsyncRunner` 仅有 `call` / `is_supports_tool_calling` / `close`、`CancellationToken` 仅有 `is_cancelled` / `cancel_reason` / `requested_at`；不存在 `set_tools` / `get_schemas` / `get_tool_display_info`。
- `test_agent_message_union.py`
  - 对 `SystemMessage` / `UserMessage` / `AssistantMessage` / `ToolMessage` 各自构造一个实例，断言其类型在 `(SystemMessage, UserMessage, AssistantMessage, ToolMessage)` 元组之内（运行时 isinstance 测试针对**具体 dataclass 类**）；不依赖 `AgentMessage` TypeAlias 的运行时 isinstance 行为（review §5.1 修正：PEP604 union 在运行时是 `types.UnionType`，不直接用于 isinstance 检查）。
  - 反射断言四个 dataclass 字段集合精确符合 §6.2。

### 7.3 失败路径测试

- 包根 `__all__` 增/减项 → 测试失败。
- Engine 任意模块 `from dayu.host` / `from dayu.fins` / `from dayu.engine.tools` 等违禁导入 → 测试失败。
- contract 中出现 `Any` / `object` / 未注解 → 测试失败。
- `ToolResultEnvelope` 字段误加 `await_spec` → 测试失败。

## 8. pyright 计划

- 沿用 `pyrightconfig.json` 现有配置（`pythonVersion: 3.11`，include `dayu`、`tests`、`utils`）。
- 所有 dataclass 字段、Protocol 方法、函数签名必须显式类型注解。
- 联合穷尽匹配使用 `typing.assert_never`；任意未处理子类型 → pyright error。
- TypeAlias（`EngineEventData` / `RunnerEventData` / `ToolExecutionOutcome` / `AgentMessage` / `AgentRunResult` / `ProviderRequestExtension` / `JsonValue`）使用 `from typing import TypeAlias` 显式标注。
- 实施完成命令：`source .venv/bin/activate && pyright`，要求 0 errors / 0 warnings 增量。
- 若发现既存 pyright 错误（理论上无，因 NEW 仓库 dayu/ 为空），必须立即修复。

## 9. README / docs 同步判断

- 默认**不**创建 `dayu/engine/README.md`、`dayu/README.md`、`tests/README.md`、根 `README.md`。
- 不修改 `docs/engine/*` 中现有 design / migration-plan / review 文档。
- 实施完成后若需要文档化，仅记录已落地事实，不写 “待 Phase 1+ 实施”、不写未来路线图（review §4.1）。
- 在 PR / 汇报中说明本 Phase 不更新 README 的原因（contract 草案阶段，无用户向能力变化）。

## 10. 风险与停止条件

必须停止并回到总控的情况：

- 实施过程中发现 §6 字段表的某字段类型在 design.md 与 OLD 证据之间出现新冲突。
- 发现某 Phase 0 contract 必须依赖未列入 Phase 0 的实现。
- 发现 `import boundary` 禁止列表存在歧义（如发现 Phase 0 contract 内不可避免需要从 `dayu.fins` 导入，理论上不应发生）。
- 发现 `AgentMessage` 联合在 Phase 1 Runner 落地前已不足以表达 OLD 行为，需要扩字段。
- 发现 `ProviderRequestExtension` 已知 provider 字段不足（如 OpenAI 新增非 `reasoning_effort` 必要字段）。

需用户/总控确认的项（在等待确认环节解决）：

- §6.4 EngineEvent data 命名 `RunnerDoneEngineData`（与 RunnerEvent 侧 `RunnerDoneData` 区分）是否被总控/用户最终接受；本计划在第 1 / 6.4 节已统一为该命名，若总控不接受需同步改名两处。
- §6.2 `ToolAwaitKind` 是否接受 Phase 0 仅落地保守初始成员 `EXTERNAL_JOB`；后续成员需消费 Phase 单独评审引入。
- §6.2 `AgentMessage` 四元封闭联合（SystemMessage / UserMessage / AssistantMessage / ToolMessage）是否作为 Phase 0 稳定最小形态。
- §6.2 `correlation_id: str | None` 进入 `ToolExecutionContext`（本计划默认进入；review §5.2 已认可，但语义上仅作中性关联，不得变成 ToolTraceRecorder 私有入口）。
- Phase 0 是否全面禁止 `dayu.fins` 任意子模块导入（本计划默认禁止；review §7 已确认应继续禁止）。
- Phase 0 是否默认不创建 `dayu/engine/README.md`（本计划默认不创建；review §7 已确认默认不创建）。

已在本轮 review 中收口、不再作为待确认项的：

- `ToolResultEnvelope` 保留 `ok: Literal[True]/Literal[False]`（review §3 已收口）。
- `ToolResultMeta` / `ToolAwaitSpec` / `ToolAwaitSnapshot` / `RunResumeHint` 全部移除 `attributes` 字段（review §4.3 已收口）。
- StrEnum 一律 `class X(StrEnum): MEMBER = "value"` 形式落地，并以 §6.6 显式成员表为唯一真源（review §4.2 已收口）。
- `AgentMessage` 联合的 isinstance 测试改为针对四个具体 dataclass 的元组，不依赖 PEP604 union 的运行时 isinstance 行为（review §5.1 已收口）。

## 11. 验收标准

客观信号：

- `dayu/engine/contracts/` 与 `tests/engine/` 已建立，被 pyright include。
- `python -c "import dayu.engine; print(sorted(dayu.engine.__all__))"` 输出仅包含 §6 锁定的 contract 类型集合。
- `python -c "from dayu.engine import run_agent_messages"` 抛 ImportError。
- `pytest tests/engine -q` 全部通过。
- `pyright` 0 errors / 0 warnings 增量。
- 架构测试（包根导出、import boundary、weak typing、event/runner contract、outcome 穷尽、协议表面、metadata 边界、AgentMessage 联合）均通过。
- 没有任何 OLD 兼容 wrapper / facade / re-export。
- 没有 `Any` / `object` / 未注解参数 / 未注解返回值。
- README 未更新；汇报中已说明原因。

## Critical Files

- 新建生产代码：`dayu/engine/contracts/*.py`（按 §5.1）。
- 新建包根：`dayu/engine/__init__.py`。
- 新建测试：`tests/engine/test_*.py`（按 §5.2）。

## Verification

1. `source .venv/bin/activate`
2. `pytest tests/engine -q` → 全部通过。
3. `pyright` → 0 errors / 0 warnings 增量。
4. 手动：`python -c "from dayu.engine import EngineEvent, EngineEventType, ToolExecutor, AsyncRunner, AgentRunRequest, ToolResultEnvelope"` 成功；`python -c "from dayu.engine import run_agent_messages"` 失败。
5. 汇报：改了什么、验证了什么、未覆盖项。
6. 等 review Agent 审查；review 通过等总控；总控通过等用户确认；用户确认后才提交 GitHub。
