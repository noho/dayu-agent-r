# Engine Phase 1 实施计划

本计划在 Phase 0（`dayu/contracts/` + `dayu/engine/contracts/` 已成为代码真源）基础上推进。Phase 1 目标：实现 OpenAI-compatible Runner 与必要的 Runner 内部私有 adapter，**并同步落地 Phase 0 contract 补丁**（review 暴露的 4 处契约缺口）。不实现 Agent loop、不引入工具执行、不动 Host / Service / UI。

本计划已根据 `docs/engine/phase1-plan-review.md` 的阻塞项与重要问题重写；review 中的待总控 / 用户决策已锁定（详见 §0.2）。

## 0. Phase 0 contract 补丁（并入本 Phase）

### 0.1 缺口与补丁项

review §4.2 / §4.3 / §5.1 与 OLD 取证（见 §3）暴露 4 处 contract 缺口，必须在本 Phase **先于 Runner 实现**落地：

| # | 文件 | 改动 | 依据 |
|---|---|---|---|
| 1 | `dayu/engine/contracts/runner_events.py` | 新增**公共枚举** `RunnerHTTPErrorCode(StrEnum)`，成员 `RATE_LIMIT_EXCEEDED` / `SERVER_ERROR` / `CLIENT_ERROR` / `NETWORK_ERROR` / `TIMEOUT` / `UNKNOWN_HTTP_STATUS`；新增 `RunnerEventType.RUNNER_HTTP_ERROR`；新增 `RunnerHTTPErrorData(error_code: RunnerHTTPErrorCode, http_status: int \| None, message: str, provider_request_id: str \| None, raw_payload: JsonValue \| None, attempt: int, retried: bool)`；纳入 `RunnerEventData` 联合 | review §4.2 + 复审 §5.1：Runner 必须把 HTTP / network / timeout 终态错误暴露为可观察事件，且 `error_code` 必须为公共 StrEnum 而非自由 `str`，避免下游 Agent 用字符串比较或 `Any` 接收 |
| 2 | `dayu/contracts/tool_call.py` | 新增 `GeminiToolCallState(thought_signature: str)`；定义封闭联合 `TypeAlias`：`ToolCallProviderState = GeminiToolCallState`（当前单成员，未来扩展时按 PEP 604 追加 `\|`）；`ToolCallRequest` 增加 `provider_state: ToolCallProviderState \| None` 字段 | review §4.3 + OLD `sse_parser.py:738/790-794/897-899`：联合定义放在公共契约层，避免 Engine → 公共 反向依赖；`AssistantToolCall` 在 §0.1 项 #3 由 Engine 层 import 引用 |
| 3 | `dayu/engine/contracts/messages.py` | `from dayu.contracts.tool_call import ToolCallProviderState` 引用项 #2 联合；`AssistantToolCall` 增加 `provider_state: ToolCallProviderState \| None` 字段 | 复审 §4.1 阻塞项：`AssistantToolCall` 真实归属是 `dayu/engine/contracts/messages.py:70`（不是 `dayu/contracts/tool_call.py`）；roundtrip 时由 Agent / Runner 把 `ToolCallRequest.provider_state` 透传给 `AssistantToolCall.provider_state` |
| 4 | `dayu/engine/contracts/runner_spec.py` | `RunnerSpec` 增加 `supports_stream_usage: bool` capability 字段 | review §5.1 + OLD `async_openai_runner.py:517/584/1059-1061`：`stream_options.include_usage` 是 capability 门控，非无条件发送 |
| 5 | `dayu/engine/contracts/runner_spec.py` | `OpenAIReasoningEffort` 枚举追加 `NONE = "none"`，后续同步扩展 `MINIMAL` / `XHIGH` | OLD `llm_models.json` 已使用 `reasoning_effort: "none"`；官方 OpenAI 文档已列出 `minimal` / `xhigh` |

### 0.2 已锁定决策（review §11 中已决项）

- **Phase 0 contract 补丁并入 Phase 1**：一次 PR 同步落地 contract + Runner，避免回退 Phase 0 流程。
- **`provider_state` 采用封闭 provider state 联合**：当前 Phase 仅含 `GeminiToolCallState`；后续新增 provider（如 Anthropic `signature`）时扩展联合，每次扩展回到 contract 评审。
- **`OpenAIReasoningEffort.NONE` 加入枚举**：与 OLD 真源一致，迁移 llm_models 配置无损；后续同步补齐官方 `minimal` / `xhigh`。
- **Gemini extra_content roundtrip 在 Phase 1 必须支持**：不放弃能力，由 §0.1 项 #2 contract 补丁承载。
- **HTTP / network / timeout 终态错误新增专用事件类型**：与协议解析错误 `RunnerProtocolErrorData` 正交分离（见 §0.1 项 #1）。
- **`AnthropicThinkingExtension` / `QwenThinkingExtension` 投影按 OLD `llm_models.json` 真源**：Anthropic / Qwen 是**顶层**字段，非 `extra_body`（详见 §6.3）。

### 0.3 Phase 0 同步测试

| 文件 | 用例 |
|---|---|
| `tests/contracts/test_tool_call.py`（修改） | `ToolCallRequest(provider_state=None)` / `ToolCallRequest(provider_state=GeminiToolCallState(...))` 构造与等值；`GeminiToolCallState` / `ToolCallProviderState` 联合 |
| `tests/engine/contracts/test_messages.py`（修改） | `AssistantToolCall(provider_state=None)` / `AssistantToolCall(provider_state=GeminiToolCallState(...))` 构造与等值；`ToolCallRequest` → `AssistantToolCall` provider_state 透传一致性 |
| `tests/engine/contracts/test_runner_events.py`（修改） | `RunnerHTTPErrorData` 构造、入 `RunnerEventData` 联合、`match RunnerEvent.data` 含 `RUNNER_HTTP_ERROR` 分支 |
| `tests/engine/contracts/test_runner_spec.py`（修改） | `RunnerSpec.supports_stream_usage` 字段；`OpenAIReasoningEffort` 值 |
| `tests/engine/test_weak_typing_guard.py`（修改） | 不允许 `provider_state` 退化为 `dict[str, Any]` / `JsonValue` 万能袋 |

### 0.4 联合穷尽影响

`assert_never` 守护点必须同步更新：
- `match RunnerEvent.data:` → 新增 `case RunnerHTTPErrorData()` 分支（NEW 现存使用方仅 contract 测试，影响面可控）。
- `match ToolCallProviderState:` → 新分支 `case GeminiToolCallState()` 在所有消费 provider_state 的位置必须穷尽（本 Phase 仅 Runner 内部使用）。
- `match OpenAIReasoningEffort:` → 覆盖当前枚举全部分支（payload builder 分支）。

## 1. Phase 范围

- 在 `dayu/engine/runners/openai/` 下落地 OpenAI-compatible Runner 实现，严格实现 Phase 0 + §0 补丁后的 `dayu.engine.contracts.runner.AsyncRunner` Protocol。
- 落地 Runner 内部私有 adapter 与 helper：HTTP 会话、SSE 解析（含 `extra_content` 透传与 OLD 已验证的非标兼容点）、reasoning 协议适配、XML 标签剥离、payload 构建、provider 错误分类与重试 backoff、阻塞边界 cancellation 协作观察。
- 落地配套测试：协议表面、SSE / non-stream / tool-call delta / usage / done / 协议错误 / **HTTP 错误事件**归一、HTTP 错误分类、retry/backoff、cancellation 阻塞边界、close 资源释放、Runner 不依赖 ToolExecutor / ToolRegistry / Host / trace。
- 更新 `tests/engine/test_import_boundary.py`：放开 `aiohttp`，仍禁 Host/Service/UI/fins/tools/processors/trace/requests/httpx。
- 更新 `dayu/engine/__init__.py`：默认**不**导出 `AsyncOpenAIRunner` 实现类（保持 `dayu.engine.__all__` 仅含 contract surface；Host 装配阶段直接 import 子模块）。

## 2. 明确不做什么

- 不实现 `AsyncCliRunner`、`AsyncAgent`、`AsyncOpenAIRunnerFactory`、`runner_factory` 同义品。
- 不实现 Agent loop / 多轮迭代控制 / iteration_started 事件提升。
- 不在 Runner 内执行工具，**不**调用 `ToolExecutor.execute`，**不**实现 `set_tools`。
- 不依赖 `ToolRegistry` / `ToolRuntime` / `dayu.engine.tools.*` / `dayu.engine.processors.*` / `dayu.fins.*` / `dayu.host.*` / `dayu.service.*` / `dayu.ui.*`。
- 不实现 `ToolTraceRecorder` / `JsonlToolTraceStore`，不写任何 trace。
- 不读取 `llm_models.json`（`RunnerSpec` 由 Host 配置 adapter 解析后注入）。
- 不接受 `call(**extra_payloads)`；OLD 开放 payload 入口被 `RunnerSpec.provider_request` 4 种强类型扩展替代。
- 不产出 `EngineEvent` / `final_answer` / `run_cancelled` / `run_failed` / `run_suspended`；不补 `session_id` / `run_id` / `iteration_id` / `event_id` / `sequence`。
- 不实现 watchdog / 超时升级 / lost 判定 / cancel 治理增强。
- 不实现 `final_answer` 内容过滤 / 上下文压缩 / context budget 计算。
- 不引入 `Any` / `object` / 裸 dict / 裸 list / 无类型签名 / metadata 万能袋。
- 不放弃 Gemini `extra_content` roundtrip 能力（由 §0 contract 补丁承载）。
- 不预先创建 README；按 §10 仅在汇报阶段判断。

## 3. 直接依据

- `docs/engine/migration-plan.md` §6（Phase 1 详细计划）。
- `docs/engine/design.md`：§2.1（Runner 协议结论：拒绝 `**extra_payloads`）；§2.3（StreamEvent → RunnerEvent / EngineEvent 拆分）；§8.2 / §8.3（RunnerEvent 稳定规则）；§9（Cancellation 稳定规则）。
- `docs/engine/phase1-plan-review.md`：阻塞项 §4.1 / §4.2 / §4.3，重要问题 §5.1 / §5.2 / §5.3 / §5.4。
- Phase 0（含 §0 补丁后）代码真源：
  - `dayu/engine/contracts/runner.py`、`runner_events.py`、`runner_spec.py`、`messages.py`、`finish_reason.py`。
  - `dayu/contracts/cancellation.py`、`tool_schema.py`、`tool_call.py`（含 `ToolCallProviderState`）、`json_value.py`。
- OLD 强参考（仅作 implementation 参考）：
  - `~/workspace/dayu-agent/dayu/engine/async_openai_runner.py`：`supports_stream_usage` 门控（`L517/584/1059-1061`）、HTTP 错误分类、`extra_content` 透传（`L843/897/975/1784-1787`）。
  - `~/workspace/dayu-agent/dayu/engine/sse_parser.py`：SSE 兼容点 + tool call `extra_content` 保留（`L738/790-794/897-899`）。
  - `~/workspace/dayu-agent/dayu/engine/async_agent.py`：tool_calls roundtrip `extra_content`（`L286-288/804-806`）。
  - `~/workspace/dayu-agent/dayu/engine/{reasoning_protocol,xml_extractor,cancellation}.py`。
  - `~/workspace/dayu-agent/dayu/config/llm_models.json`：provider 投影真源（顶层 vs `extra_body`）。
- `AGENTS.md` / `CLAUDE.md`：架构与编码硬约束。

## 4. OLD 可复用片段

OLD 文件路径相对于 `~/workspace/dayu-agent/`。

### 4.1 允许复用（仅作 implementation 参考，必须按 NEW contract 重构）

- `dayu/engine/async_openai_runner.py`
  - payload 构建：消息序列化、`temperature` / `max_tokens` / `top_p` / `stream` 字段映射、`tools` schema 透传。
  - **`supports_stream_usage` capability 门控**：仅当 `stream=True` 且 `spec.supports_stream_usage=True` 时追加 `stream_options.include_usage=True`；否则不写。
  - **assistant `reasoning_content` outbound 序列化**：当 `AssistantMessage.reasoning_content is not None` 时，outbound message 必须包含 `reasoning_content` 键；为 `None` 时不写该键。
  - HTTP 错误分类：`429` → `rate_limit_exceeded`；`500/502/503/504` → `server_error`；`4xx`（非 429）→ 不可重试客户端错误；超时 → `timeout`；连接错误 → `network_error`。
  - 重试与 backoff：`Retry-After` 头优先；指数退避基线 `min(2 ** attempt, cap)`；429 与普通 5xx 各自的 capped backoff；`spec.max_retries` 上限。
  - 流式 vs 非流式分支：`Content-Type` 自动检测 + `RunnerCallOptions.stream`；模型不支持流式时降级一次性 JSON。
  - **tool call `extra_content` 透传**：SSE / non-stream parser 解析到的 `extra_content` 字段（典型 Gemini `thought_signature`）必须保留并归一为 `ToolCallRequest.provider_state`。
- `dayu/engine/sse_parser.py`
  - SSE 行缓冲 + `data:` 前缀解析 + `[DONE]` 标记识别。
  - per-choice 增量累积：`content` / `reasoning_content` / `tool_calls`（按 `index` 聚合 name / arguments 增量；缺失 `index` 时按 `id` 归属）。
  - 工具调用最终组装与必填字段校验（`id` / `name` 缺失或 `arguments` 解析失败 → `RunnerProtocolErrorData`）。
  - **OLD 已验证的非标兼容点（必须迁移）**：
    - 多行 `data:` 聚合（同一事件跨多个 `data:` 行）。
    - 缺失 tool call `index` 时按 `id` 归属累积。
    - `function.arguments is None` 安全忽略，不视为错误。
    - 非法 UTF-8 chunk 处理：解码失败时**发出 `RunnerProtocolErrorData(error_code="invalid_utf8", message=..., raw_payload=<base64 chunk 或 None>)` 后以 `RunnerDoneData(FinishReason.ERROR)` 收口**，不再继续读流（与 OLD `sse_parser.py` 行为一致：解码错误是协议事实，不是可恢复噪声；复审 §5.2 修正）。
    - 尾部残留 data（无换行结尾）正常落库。
    - `choices` 为空但 `usage` 存在的 chunk 仍归一为 `RunnerUsageRecordedData`。
  - **Gemini `extra_content` 透传**（OLD `L738/790-794/897-899`）：tool call 增量 `extra_content` 字段全链路保留至最终组装。
- `dayu/engine/reasoning_protocol.py`
  - `ReasoningProtocolHook` 思想：检测 Gemini `extra_body.google.thinking_config.include_thoughts`，决定响应正文是否剥离 `<thought>` 标签到 reasoning。
- `dayu/engine/xml_extractor.py`
  - `StreamingXMLTagExtractor` 流式 XML 标签状态机（`start_only` 开关 + 失活）。
- `dayu/engine/cancellation.py`
  - `await_or_cancel` / `create_cancellation_waiter` 思想：`asyncio.wait` `FIRST_COMPLETED` 把 cancellation 观察并入 SSE 读取与 retry sleep 阻塞边界。

### 4.2 禁止复用 / 禁止迁移

- `set_tools(executor)` 入口、`self._tool_executor` 字段、`tool_call_dispatched` / `tool_calls_batch_ready` / `tool_calls_batch_done` / `tool_call_result` 系列工具执行事件。
- `_emit_tool_batch` / `_run_tool_call` / `_execute_tool_call` 等 Runner 内工具执行 path（属 Agent 职责）。
- `default_extra_payloads` 实例字段、`set_default_extra_payloads`、`call(**extra_payloads)` 开放参数袋。
- `ToolExecutor` / `ToolExecutionContext` 的 import。
- `_annotate_event(..., trace_meta)` / 任何 trace_meta 注入路径与 `dayu.engine.tool_trace*` import。
- `read_llm_models_config` / 任何对 `llm_models.json` 的直接读取。
- OLD `StreamEvent` / `EventType` / `metadata: dict[str, Any]` 弱类型事件载体。
- OLD `error_event` / `warning_event` 命名（NEW 用 `RunnerProtocolErrorData` 表达协议错误，`RunnerHTTPErrorData` 表达 HTTP / network 错误）。
- OLD 把 `extra_content` 塞进 `event.metadata["extra_content"]` 的弱类型路径（`L897-899` / `L975-977`）；NEW 必须经 `ToolCallProviderState` 联合。
- `AsyncCliRunner`、`runner_factory`。
- `argument_validator` / `duplicate_call_guard` / `truncation_manager` / `doc_access_policy`。

## 5. NEW 文件变更计划

### 5.1 生产代码（新增）

```
# Phase 0 contract 补丁（修改现有文件）
dayu/engine/contracts/runner_events.py    # +RunnerHTTPErrorCode, +RunnerEventType.RUNNER_HTTP_ERROR, +RunnerHTTPErrorData
dayu/contracts/tool_call.py               # +GeminiToolCallState, +ToolCallProviderState; ToolCallRequest +provider_state
dayu/engine/contracts/messages.py         # AssistantToolCall +provider_state（import ToolCallProviderState）
dayu/engine/contracts/runner_spec.py      # RunnerSpec +supports_stream_usage; OpenAIReasoningEffort 扩展

# Runner 实现（新增）
dayu/engine/runners/__init__.py
dayu/engine/runners/openai/__init__.py
dayu/engine/runners/openai/runner.py            # AsyncOpenAIRunner：实现 AsyncRunner Protocol
dayu/engine/runners/openai/payload.py           # _build_request_payload + ProviderRequestExtension 应用
dayu/engine/runners/openai/http_client.py       # aiohttp ClientSession 持有、超时、关闭、cancellation 观察
dayu/engine/runners/openai/sse_parser.py        # SSE 解析（含 extra_content 透传 + OLD 兼容点）
dayu/engine/runners/openai/non_stream_parser.py # 非流式 JSON 响应 → RunnerEvent
dayu/engine/runners/openai/reasoning_protocol.py # provider 私有 reasoning 协议探测
dayu/engine/runners/openai/xml_tag_extractor.py # 流式 XML 标签提取器
dayu/engine/runners/openai/error_classifier.py  # HTTP 状态 → 中性 error_code
dayu/engine/runners/openai/retry_policy.py      # max_retries / Retry-After / 指数退避
dayu/engine/runners/openai/cancellation_helpers.py # await_or_cancel
dayu/engine/runners/openai/tool_call_aggregator.py # 流式 tool_call delta → ToolCallRequest（含 provider_state 组装）
dayu/engine/runners/openai/_types.py            # 私有 TypedDict / dataclass / StrEnum，不出包
```

不引入：
- `dayu/engine/__init__.py` 的导出变更（默认不 re-export `AsyncOpenAIRunner`）。
- `dayu/engine/tools/*` / `dayu/engine/processors/*` / `dayu/engine/agent*.py`。

### 5.2 测试（新增）

```
# Contract 补丁同步测试（修改现有文件）
tests/contracts/test_tool_call.py                          # +ToolCallRequest.provider_state 构造、等值、None 默认；GeminiToolCallState
tests/engine/contracts/test_messages.py                    # +AssistantToolCall.provider_state；roundtrip ToolCallRequest→AssistantToolCall provider_state 透传
tests/engine/contracts/test_runner_events.py               # +RunnerHTTPErrorCode StrEnum、+RunnerHTTPErrorData 构造、联合穷尽
tests/engine/contracts/test_runner_spec.py                 # +supports_stream_usage 字段、OpenAIReasoningEffort
tests/engine/test_weak_typing_guard.py                     # provider_state 不退化为 dict[str, Any] / 万能 JsonValue；error_code 不退化为 str

# Runner 实现测试（新增）
tests/engine/runners/__init__.py
tests/engine/runners/openai/__init__.py
tests/engine/runners/openai/test_protocol_surface.py       # isinstance(runner, AsyncRunner)；表面无 set_tools / **kwargs
tests/engine/runners/openai/test_payload_build.py          # 4 种 ProviderRequestExtension 投影；provider_request=None；显式参数不进 extra_body
tests/engine/runners/openai/test_payload_assistant_reasoning_content_preserved.py  # review §5.4
tests/engine/runners/openai/test_stream_usage_capability_gating.py                 # review §5.1：supports_stream_usage=False 不写 stream_options
tests/engine/runners/openai/test_sse_content_delta.py
tests/engine/runners/openai/test_sse_reasoning_delta.py    # 原生 reasoning_content + <thought> 标签两路
tests/engine/runners/openai/test_sse_tool_call_stream.py
tests/engine/runners/openai/test_sse_tool_call_extra_content_preserved.py          # Gemini thought_signature → provider_state
tests/engine/runners/openai/test_sse_usage_recorded.py
tests/engine/runners/openai/test_sse_done.py
tests/engine/runners/openai/test_sse_multi_line_data_aggregation.py                # review §5.3
tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py             # review §5.3
tests/engine/runners/openai/test_sse_tool_call_arguments_null_ignored.py           # review §5.3
tests/engine/runners/openai/test_sse_invalid_utf8_chunk.py                         # review §5.3
tests/engine/runners/openai/test_sse_trailing_data_no_newline.py                   # review §5.3
tests/engine/runners/openai/test_sse_empty_choices_with_usage.py                   # review §5.3
tests/engine/runners/openai/test_non_stream_response.py
tests/engine/runners/openai/test_protocol_error.py         # SSE / JSON 协议错误 → RunnerProtocolErrorData
tests/engine/runners/openai/test_http_error_event.py       # review §4.2：HTTP / timeout / network 终态错误 → RunnerHTTPErrorData → RunnerDoneData(ERROR)
tests/engine/runners/openai/test_http_error_classification.py
tests/engine/runners/openai/test_retry_backoff.py
tests/engine/runners/openai/test_cancellation_boundaries.py
tests/engine/runners/openai/test_cancellation_no_done_event.py                     # review §4.1：token 取消时无 RunnerDoneData 收口
tests/engine/runners/openai/test_close_releases_resources.py
tests/engine/runners/openai/test_no_tool_executor_dep.py
tests/engine/runners/openai/test_no_extra_payload_bag.py
```

### 5.3 测试边界更新（修改）

- `tests/engine/test_import_boundary.py`：
  - **新增允许 import**：`aiohttp`（仅 `dayu/engine/runners/openai/` 子树）。
  - **保持永久禁止**：`dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` / `dayu.engine.tools` / `dayu.engine.processors` / `*tool_trace*` / `JsonlToolTraceStore`。
  - **保持当前 Phase 禁止**：`requests`、`httpx`。
- `tests/engine/test_weak_typing_guard.py`：
  - 扫描根从 `dayu/engine/contracts/` 扩展为 `dayu/engine/`。
  - 私有 adapter 类型例外白名单：`dayu/engine/runners/openai/_types.py` 内私有 `TypedDict` 字段允许 `JsonValue`；其它弱类型仍禁止。

### 5.4 文档

- 默认不更新 README；落地后由汇报阶段判断（§10）。

## 6. 类型设计计划

### 6.1 Runner 公共表面

```python
class AsyncOpenAIRunner:
    def __init__(self, *, spec: RunnerSpec, cancellation_token: CancellationToken) -> None: ...
    def call(self, messages: Sequence[AgentMessage], options: RunnerCallOptions, tools: Sequence[ToolSchema]) -> AsyncIterator[RunnerEvent]: ...
    def is_supports_tool_calling(self) -> bool: ...
    async def close(self) -> None: ...
```

- `call(...)` 不接收 `**kwargs`；provider 私有字段必须经 `spec.provider_request` 解析。
- `call(...)` 不接收 `ToolExecutor`；`tools` 仅是 schema 序列。

### 6.2 Runner 内部私有 adapter 类型

仅 `dayu/engine/runners/openai/_types.py` 内可见，`_OpenAI*` 前缀强调私有：

- `_OpenAIRequestPayload`：请求 JSON `TypedDict`；字段含 `model`、`messages`、`temperature`、`max_tokens`、`top_p`、`stream`、`tools`、`tool_choice`、`stream_options`、`reasoning_effort`、`thinking`、`enable_thinking`、`extra_body`；不接受任意键 `dict[str, Any]`。
- `_OpenAIChatMessage`：覆盖 `system` / `user` / `assistant` / `tool` 四角色对应字段；从 `AgentMessage` 联合 `match` 转换；**`assistant` 分支当 `reasoning_content is not None` 时必须包含 `reasoning_content` 键**（OLD `async_openai_runner.py` 已验证）。
- `_OpenAIToolCall`（outbound）：assistant message 内 tool_calls 的序列化形态；当 `provider_state == GeminiToolCallState(thought_signature=s)` 时，写入 `extra_content: {"google": {"thought_signature": s}}` 字段（保留 `google` provider namespace，与 OLD 一致）。
- `_OpenAIToolSchema`：`{"type": "function", "function": {...}}`。
- `_OpenAIExtraBody`：`google` provider 私有字段 `TypedDict.total=False`（仅 Gemini 走 `extra_body`；Anthropic / Qwen / OpenAI 走顶层）。
- `_OpenAIStreamOptions`：`{"include_usage": bool}`。
- `_OpenAIToolCallDelta` / `_OpenAIToolCallFinal`：流式增量与最终态；`extra_content` 字段为 `Mapping[str, Mapping[str, JsonValue]]`（按 provider namespace 分桶），由 parser 在归一阶段消费 → `provider_state`，不出包。
- `_OpenAIChoiceFinal`：non-stream 完整响应 choice。
- `_OpenAIUsage`：`prompt_tokens` / `completion_tokens` / `total_tokens`。
- 公共 `RunnerHTTPErrorCode`（StrEnum，定义在 `dayu.engine.contracts.runner_events`，§0.1 项 #1）由 `error_classifier.py` 生产；Runner 内部不另起 `_HTTPErrorCode` 私有镜像，避免双源。
- `_RetryDecision`：`@dataclass(frozen=True, slots=True)`；字段 `should_retry`、`sleep_seconds`、`attempt`。
- `_ReasoningProtocolHook`：字段 `tag_name: str | None`。

### 6.3 ProviderRequestExtension 应用规则（按 OLD `llm_models.json` 真源）

| Extension | 投影位置 | OLD 证据 |
|---|---|---|
| `OpenAIReasoningExtension(reasoning_effort)` | **顶层** `reasoning_effort: "none" \| "minimal" \| "low" \| "medium" \| "high" \| "xhigh"` | `llm_models.json:222/272`（`"none"` / `"high"`） |
| `AnthropicThinkingExtension(enabled, budget_tokens)` | **顶层** `thinking = {"type": "enabled" \| "disabled"}`；enabled 时追加 `budget_tokens`，disabled 时不传 | `llm_models.json:322/375`（disabled 无 `budget_tokens`，thinking case 含 `budget_tokens`） |
| `DeepSeekThinkingExtension(enabled, reasoning_effort)` | **顶层** `thinking = {"type": "enabled" \| "disabled"}`；`reasoning_effort` 非 `None` 时追加顶层 effort | `llm_models.json:15/67`（顶层 `thinking.type`，无 `budget_tokens`） |
| `MimoThinkingExtension(enabled)` | **顶层** `thinking = {"type": "enabled" \| "disabled"}` | `llm_models.json:994/1046`（顶层 `thinking.type`，无 `budget_tokens`） |
| `GeminiThinkingExtension(thinking_budget, include_thoughts, thinking_level)` | `extra_body.google.thinking_config`，仅写入非 `None` 字段；`thinking_budget` 与 `thinking_level` 互斥 | `llm_models.json:428-435`（`extra_body.google`） |
| `QwenThinkingExtension(enable_thinking, thinking_budget)` | **顶层** `enable_thinking: bool`；`thinking_budget` 非 `None` 时追加顶层预算 | `llm_models.json:1306/1356`（顶层 `enable_thinking`） |
| `provider_request is None` | 不写任何 provider 私有字段 | — |

实现要点：
- 不存在「未知扩展」分支：`ProviderRequestExtension` 是封闭联合，`match` + `assert_never` 守护。
- Anthropic 顶层 `thinking` 由 OpenAI-compatible Anthropic 网关识别，相关 header（`Authorization`、`anthropic-beta`）由 `RunnerSpec.headers` 注入，不属 `ProviderRequestExtension` 范畴。

### 6.4 RunnerEvent 归一规则

| Provider 协议事实 | 归一为 RunnerEvent | 备注 |
|---|---|---|
| SSE chunk `delta.content` 非空 | `RunnerContentDeltaData(delta)` | XML 标签外内容 |
| SSE chunk `delta.reasoning_content` 非空 | `RunnerReasoningDeltaData(delta)` | 与剥离后的 `<thought>` 内容合并为同一路 |
| SSE chunk `delta.tool_calls[i]` | `RunnerToolCallDeltaData(tool_call_index, tool_call_id, name_delta, arguments_delta)` | 按 `index` 聚合；缺失 `index` 时按 `id` 归属 |
| SSE 流结束 + tool_calls 已聚合且校验通过 | `RunnerToolCallsCompletedData(tool_calls=tuple[ToolCallRequest, ...])` | `provider_state` 由 SSE / non-stream parser 解析 tool call 上的 `extra_content` 后归一填充；详见 §6.4.3 |
| SSE 流结束（无 tool_calls）或 non-stream 完成 | `RunnerContentCompletedData(content, reasoning_content, finish_reason)` | `finish_reason` 由 provider 字段映射 |
| `usage` 字段（流式末 chunk 或 non-stream 响应） | `RunnerUsageRecordedData(prompt_tokens, completion_tokens, total_tokens)` | 仅当 `spec.supports_stream_usage=True` 时流式才会出现；non-stream 不受门控 |
| **SSE / JSON 解析错误、tool_calls 校验失败** | `RunnerProtocolErrorData(error_code, message, provider_request_id, raw_payload)` | **协议层错误** |
| **HTTP 终态错误**：non-retriable（4xx 非 429）/ retry exhausted（429 / 5xx）/ timeout / connection error / unknown HTTP status | `RunnerHTTPErrorData(error_code: RunnerHTTPErrorCode, http_status, message, provider_request_id, raw_payload, attempt, retried)` | **传输层错误**；`error_code` 是公共 StrEnum（不是自由 `str`）；与协议错误正交分离 |
| 流末或响应末总收口（成功 / 协议错误 / HTTP 错误） | `RunnerDoneData(finish_reason)` | 默认终态（含 `FinishReason.ERROR`） |

#### 6.4.1 取消终态例外（review §4.1 修正）

- **默认规则**：一次 `call(...)` 必须以 `RunnerDoneData` 作为最后一个事件。
- **唯一例外**：`cancellation_token.is_cancelled() == True` 且 Runner 已完成资源释放时，允许无 `RunnerDoneData` 终止（生成器 `async for` 自然终止）。
- **Phase 2 Agent 收口规则**：
  - `token cancelled == True` 且 Runner 流终止且无 `RunnerDoneData` → 收口为 `RunCancelledData` / `EngineRunOutcomeCancelled`。
  - `token cancelled == False` 且 Runner 流终止且无 `RunnerDoneData` → 视为协议错误 / `run_failed`（防止「自然终止」歧义）。
- 本 Phase 仅断言 Runner 行为；Phase 2 Agent 的双条件收口由后续 Phase 测试覆盖。

#### 6.4.2 错误事件类型选择规则

- 解析层面（SSE 行 / JSON 结构 / tool_calls 必填字段）→ `RunnerProtocolErrorData`。
- 传输层面（HTTP 状态码 / 网络异常 / 超时 / DNS / TLS）→ `RunnerHTTPErrorData`。
- 两者均以 `RunnerDoneData(FinishReason.ERROR)` 收口（除非取消例外触发）。

#### 6.4.3 tool call provider_state 透传规则

OLD 真实 shape（取证：`~/workspace/dayu-agent/tests/engine/test_sse_parser.py:1413/1460/1470/1507`）：
```
extra_content = {"google": {"thought_signature": "EjQKMgEMOdbH..."}}
# 或同时含 thought 标记：{"google": {"thought": True, "thought_signature": "..."}}
```
即 `extra_content` 是按 **provider namespace** 分桶的字典（最外层是 `google` 这一类 provider key），**不是**顶层裸 `thought_signature`。

归一规则：

- SSE / non-stream parser 读取 tool call 上的 `extra_content` 字典后，按 **provider namespace** 分派：
  - `extra_content["google"]["thought_signature"]: str` 存在 → `GeminiToolCallState(thought_signature=...)`。
  - `extra_content["google"]` 仅含 `thought: True` 但缺 `thought_signature` → `None`（不报错，正常无 signature 的 thinking chunk）。
  - 出现未知 provider namespace 或 `google` 下未知键 → `None` 并发 `RunnerProtocolErrorData`（不阻断流）。
- `RunnerToolCallsCompletedData.tool_calls[i].provider_state` 按上述规则填充；OpenAI / DeepSeek / Anthropic / Qwen 默认 `None`。
- outbound assistant message 序列化时，`AssistantToolCall.provider_state == GeminiToolCallState(s)` → `_OpenAIToolCall.extra_content = {"google": {"thought_signature": s}}`（**保留 `google` 命名空间**，与 OLD 一致；OLD 证据：`async_openai_runner.py:1784-1787` + `test_async_agent.py:2216/2247`）。
- 未来扩 `ToolCallProviderState` 时，每个新 provider 在 `extra_content` 下保留各自 namespace（如 `anthropic` / `qwen`），`match` 在 parser 与 serializer 两侧穷尽。

`RunnerEvent` 不含 `session_id` / `run_id` / `iteration_id` / `event_id` / `sequence`（Phase 0 已锁定）。

### 6.5 类型边界硬约束

- 公共表面（`AsyncOpenAIRunner` 全部公共方法）字段一律来自 `dayu.engine.contracts` / `dayu.contracts`，无 `Any` / `object` / 裸 dict。
- 内部 adapter 字段一律 `TypedDict` / `dataclass(frozen=True, slots=True)` / `StrEnum`。
- `provider_request_id` / `raw_payload` 在 `RunnerProtocolErrorData` / `RunnerHTTPErrorData` 中已是 `str | None` / `JsonValue | None`，解析失败一律降级 `None`。
- HTTP 响应 JSON 解析后立即用 `_OpenAI*` TypedDict 类型化；禁止 `getattr` / `hasattr` / 无类型字段访问。
- 不允许把显式参数（如 `temperature`）塞进 `provider_request` 或 `_OpenAIExtraBody`。
- **tool call provider continuation state 必须经过 `ToolCallProviderState` 封闭联合 `match`，禁止 `dict[str, Any]` / metadata 万能袋承载。**
- **`RunnerHTTPErrorData.error_code` 必须是 `RunnerHTTPErrorCode`（公共 StrEnum），禁止退化为自由 `str`；下游消费侧用 `match` + `assert_never` 守护。**
- **`extra_content` 在 outbound 序列化与 parser 解析两侧必须保留 `google` provider namespace 层级，禁止扁平化为 `{"thought_signature": ...}`。**

## 7. 取消与资源关闭计划

Runner 协作式观察 `cancellation_token`，**不**抛出取消异常作为公共契约（公共终态由 Agent / Engine 入口在后续 Phase 提升）。

阻塞边界与协作策略：

| 边界 | 协作机制 | 行为 |
|---|---|---|
| HTTP 建连（`session.post(...).__aenter__`） | `await_or_cancel(connect_task, token)` | token 命中 → 取消 connect_task；finally 释放 socket；抛内部 `_RunnerInterrupted`（私有，不出包） |
| 响应 body 读取（`response.content.read(...)`） | 同上 | token 命中 → 关闭 response；release underlying connection |
| SSE chunk 等待（异步迭代 `response.content`） | `await_or_cancel(read_chunk_task, token)` + idle timeout | token 命中或 idle 超时 → 关闭流 |
| Retry sleep（`asyncio.sleep(backoff)`） | `await_or_cancel(sleep_task, token)` | token 命中 → 立即退出，停止后续重试 |
| `close()` | 幂等关闭 `aiohttp.ClientSession`；忽略 `RuntimeError` / `ConnectionResetError` | 不再观察 token |

实现要点：
- 私有异常 `_RunnerInterrupted` 仅在 Runner 内部传递；**不**在公共出口抛出，**不**在 `__all__` 暴露，**不**写入 `:raises:`。
- `call(...)` 捕获 `_RunnerInterrupted` 后**直接退出生成器**，不再 yield；**不**在退出前补 `RunnerDoneData`（与 §6.4.1 取消例外一致）。
- Runner 不读取 `cancel_reason()` / `requested_at()`；Runner 不向 `RunnerEvent` 流注入取消事实。
- 取消事实由 Phase 2 Agent 通过 `token.is_cancelled() + 无 RunnerDoneData 终止` 双条件推断。
- 不实现 watchdog / 超时升级 / lost 判定。

## 8. 测试计划

### 8.1 责任划分

- pytest：协议表面、payload 映射、SSE / JSON 归一、HTTP 错误事件归一、HTTP 错误分类、retry 决策、cancellation 阻塞边界、close 幂等、AST 边界守卫、provider_state roundtrip。
- pyright：Runner 公共签名、内部 TypedDict 强类型、`ProviderRequestExtension` 联合穷尽、`AgentMessage` 联合穷尽、`ToolCallProviderState` 联合穷尽、`RunnerEventData` 含 `RunnerHTTPErrorData` 分支。

### 8.2 用例清单

按 §5.2 测试文件名一一映射；以下列出关键断言重点：

- **`test_protocol_surface.py`**：`isinstance(runner, AsyncRunner)`；`inspect.signature(call)` 无 `**kwargs`；无 `set_tools` 方法；`is_supports_tool_calling()` 返回 `spec.supports_tool_calling`；`close()` awaitable。
- **`test_payload_build.py`**：4 种 extension 各自的顶层 / `extra_body` 投影位置（按 §6.3 表）；`provider_request=None` 不写私有字段；显式参数不进 `extra_body`。
- **`test_payload_assistant_reasoning_content_preserved.py`**：`AssistantMessage(reasoning_content="x")` → outbound message 含 `reasoning_content: "x"`；`AssistantMessage(reasoning_content=None)` → outbound 不含该键。
- **`test_stream_usage_capability_gating.py`**：`stream=True` + `supports_stream_usage=True` → `stream_options.include_usage=True`；`supports_stream_usage=False` → 不写 `stream_options`；`stream=False` 始终不写。
- **`test_sse_*` 主干 5 项**：fake aiohttp response 喂 chunk → 事件序列严格匹配 `RunnerEvent` 列表。
- **`test_sse_tool_call_extra_content_preserved.py`**：fixture 含 Gemini `thought_signature` → `RunnerToolCallsCompletedData.tool_calls[0].provider_state == GeminiToolCallState(thought_signature=...)`。
- **`test_sse_*` 兼容点 6 项**（review §5.3）：多行 data 聚合、缺失 index 按 id 归属、`arguments: null` 安全忽略、**非法 UTF-8 → `RunnerProtocolErrorData(error_code="invalid_utf8") + RunnerDoneData(ERROR)` 收口**（不继续流）、尾部残留 data、empty choices + usage。
- **`test_non_stream_response.py`**：`Content-Type: application/json` 路径；一次性产出 `RunnerContentCompletedData` + `RunnerUsageRecordedData` + `RunnerDoneData`。
- **`test_protocol_error.py`**：坏 JSON / 缺失 `id` / arguments 非 JSON 对象 → `RunnerProtocolErrorData`；`raw_payload` 满足 `JsonValue`。
- **`test_http_error_event.py`**（review §4.2）：429 重试耗尽 / 5xx 重试耗尽 / 4xx non-retriable / `aiohttp.ClientConnectorError` / `asyncio.TimeoutError` / 未知 HTTP status → `RunnerHTTPErrorData(error_code=..., http_status=..., attempt=..., retried=...)` → `RunnerDoneData(FinishReason.ERROR)`。
- **`test_http_error_classification.py`**：`error_classifier` 单元测试；429 / 5xx / 4xx / timeout / connection / unknown HTTP status 各自映射到正确 `RunnerHTTPErrorCode` 成员。
- **`test_retry_backoff.py`**：`Retry-After: 3` 优先；指数退避基线；超 `spec.max_retries` 后停止并触发 `test_http_error_event.py` 中的「retry exhausted」分支。
- **`test_cancellation_boundaries.py`**：四路阻塞边界（建连 / 读流 / SSE chunk / retry sleep）token 命中后 ≤100ms 退出；不抛公共取消异常。
- **`test_cancellation_no_done_event.py`**（review §4.1）：取消时生成器自然终止，事件流**不含** `RunnerDoneData`；非取消场景下事件流必须以 `RunnerDoneData` 收口。
- **`test_close_releases_resources.py`**：`close()` 幂等；二次调用不抛；session 已关闭；取消后 `close()` 仍成功。
- **`test_no_tool_executor_dep.py`**（AST）：扫描 `dayu/engine/runners/`，不出现 `ToolExecutor` / `ToolRegistry` / `ToolRuntime` / `ToolTraceRecorder` / `JsonlToolTraceStore` / `dayu.host.*` / `dayu.service.*` / `dayu.ui.*` / `dayu.fins.*` / `dayu.engine.tools.*` / `dayu.engine.processors.*` import。
- **`test_no_extra_payload_bag.py`**（AST + signature）：`AsyncOpenAIRunner.call` 签名严格等于 `AsyncRunner.call`；内部 `_build_request_payload` 不接受 `**kwargs`；`_OpenAIRequestPayload` 构造点不通过 `dict[str, Any]` 中转。

Phase 0 contract 补丁同步测试见 §0.3。

### 8.3 失败路径

- Runner 内部任意模块新增违禁 import → 测试失败。
- `call(...)` 新增 `**kwargs` → 测试失败。
- `ProviderRequestExtension` 新增成员未在 payload builder `match` 中处理 → pyright `assert_never` 失败。
- `RunnerEventData` 新增成员未在消费侧 `match` 中处理 → pyright `assert_never` 失败。
- `ToolCallProviderState` 新增成员未在 parser `match` 中处理 → pyright `assert_never` 失败。
- **token 未取消但事件流缺少 `RunnerDoneData` 终态** → 测试失败（取消例外仅在 token cancelled 时成立）。
- HTTP 终态错误未发出 `RunnerHTTPErrorData` 而沿用 `RunnerProtocolErrorData` → 测试失败。
- Gemini fixture 的 tool call `extra_content` 未透传到 `provider_state` → 测试失败。

## 9. pyright 计划

- 沿用 `pyrightconfig.json`（`pythonVersion: 3.11`）。
- 禁止 `Any` / `object` / 裸 `dict` / 裸 `list` / 无注解参数 / 无注解返回。
- `aiohttp` 最小公共 surface：`ClientSession` / `ClientResponse` / `ClientTimeout` / 异常类；`http_client.py` 顶部 import。
- `_OpenAIRequestPayload` 等 TypedDict 用 `total=False` + `cast` 在最终发送前 freeze；构造时禁止 `dict[str, Any]`。
- `match` + `assert_never` 守护：
  - `AgentMessage` 4 分支
  - `ProviderRequestExtension` 全部分支
  - `OpenAIReasoningEffort` 全部分支（含 `NONE` / `MINIMAL` / `XHIGH`）
  - `RunnerHTTPErrorCode` 6 分支（含 `UNKNOWN_HTTP_STATUS`）
  - `RunnerEventData`（含 `RunnerHTTPErrorData`）所有消费侧
  - `ToolCallProviderState` 所有消费侧
- 完成命令：`source .venv/bin/activate && pyright`，0 errors / 0 warnings 增量。

## 10. README / docs 同步判断

- 默认本 Phase 不创建 README。
- 落地后判断：`dayu/engine/README.md` 不存在 → 暂不创建；待 Phase 2/3 Agent loop 与装配落地时一次性补齐。
- 不更新 `dayu/README.md` / 根 `README.md` / `tests/README.md`。
- 汇报阶段必须在最终说明里写明 README 判断结果（review §6.2）。

## 11. 风险与停止条件

必须停止并回到总控的情况：

- **Phase 0 contract 补丁测试不通过 / pyright 不通过**：必须先修复 §0 补丁再继续 Runner 实现。
- **新 provider 私有协议字段无法用现有 `ProviderRequestExtension` 表达**（如 DeepSeek、Mistral 新协议）→ 回到 contract 评审扩联合。
- **新 provider tool call continuation state 出现**（如 Anthropic `signature`）→ 回到 contract 评审扩 `ToolCallProviderState` 联合。
- **HTTP 错误码新增类目**（如 OpenAI Responses API 新错误 family）→ 回到 contract 评审扩 `RunnerHTTPErrorCode` 或 `RunnerHTTPErrorData`。
- **必须依赖 ToolExecutor**：发现实现需要 ToolExecutor 才能完成本 Phase 目标（按 design 不应发生）。
- **必须读取配置文件 / 反向 import 上层**：发现实现需要直接读 `llm_models.json` / 环境变量 / Host 模块。
- **必须引入 `Any` / `object` / 开放 payload**：发现严格类型化某分支不可行。

review §11 中的 5 项决策已在 §0.2 锁定，不再列入待确认。

## 12. 验收标准

客观信号：

- §0 contract 补丁全部落地：`RunnerHTTPErrorData` / `ToolCallProviderState` / `RunnerSpec.supports_stream_usage` / `OpenAIReasoningEffort`；contract 同步测试全绿。
- `dayu/engine/runners/openai/` 完整落地（§5.1 全部模块），无任何 `Any` / `object` / 裸 dict / 无注解。
- `pytest tests/contracts tests/engine -q` 全绿。
- `pyright` 0 errors / 0 warnings 增量。
- `python -c "from dayu.engine.runners.openai.runner import AsyncOpenAIRunner; from dayu.engine.contracts import AsyncRunner"` 成功；运行时 `isinstance(AsyncOpenAIRunner(...), AsyncRunner)` 为 True。
- `python -c "from dayu.engine import AsyncOpenAIRunner"` 抛 ImportError（默认不导出实现类）。
- `tests/engine/test_import_boundary.py` 守住：Runner 实现侧无 Host / Service / UI / fins / tools / processors / trace / `requests` / `httpx` import；允许 `aiohttp`。
- `RunnerEvent` 序列与 §6.4 表完全一致：
  - 默认终态恒为 `RunnerDoneData`；
  - **取消例外**：`token.is_cancelled()=True` 时允许无 `RunnerDoneData` 终止；
  - HTTP / network 终态错误以 `RunnerHTTPErrorData` 而非 `RunnerProtocolErrorData` 表达。
- Runner 在四路阻塞边界对 cancellation token 协作式响应：从 token 命中到生成器终止 ≤100ms（fake clock 测）。
- `close()` 幂等；任意时序下不泄漏 `aiohttp.ClientSession`。
- **`AssistantMessage.reasoning_content is not None` 时 outbound payload 必须保留该键**。
- **Gemini fixture 端到端**：SSE → `RunnerToolCallsCompletedData.tool_calls[i].provider_state == GeminiToolCallState(thought_signature=...)`；assistant message 反向序列化时回写 `extra_content == {"google": {"thought_signature": s}}`（保留 namespace）。
- **`RunnerHTTPErrorData.error_code` 是 `RunnerHTTPErrorCode` 枚举值**，不是自由 `str`；联合穷尽 pyright 通过。
- **非法 UTF-8 chunk 触发 `RunnerProtocolErrorData(error_code="invalid_utf8") + RunnerDoneData(ERROR)` 终态**，不静默继续流。
- **`stream_options.include_usage` 受 `spec.supports_stream_usage` 门控**：测试覆盖三种组合。
- README 未更新（按 §10）；汇报阶段记录判断结果。

## Critical Files

- 修改 contract：`dayu/engine/contracts/runner_events.py`、`dayu/engine/contracts/runner_spec.py`、`dayu/engine/contracts/messages.py`、`dayu/contracts/tool_call.py`。
- 新建生产代码：`dayu/engine/runners/openai/*.py`（按 §5.1）。
- 修改测试：`tests/engine/test_import_boundary.py`、`tests/engine/test_weak_typing_guard.py`、`tests/contracts/test_tool_call.py`、`tests/engine/contracts/test_messages.py`、`tests/engine/contracts/test_runner_events.py`、`tests/engine/contracts/test_runner_spec.py`。
- 新建测试：`tests/engine/runners/openai/test_*.py`（按 §5.2）。

## Verification

1. `source .venv/bin/activate`
2. **Contract 补丁先行**：先实施 §0，再跑 `pytest tests/contracts tests/engine/contracts -q` + `pyright` → 全绿；不绿则停止。
3. Runner 实现：`pytest tests/engine -q` → 全绿。
4. `pyright` → 0 errors / 0 warnings 增量。
5. 手动：
   - `python -c "from dayu.engine.contracts import AsyncRunner; from dayu.engine.runners.openai.runner import AsyncOpenAIRunner"` 成功。
   - `python -c "from dayu.engine import run_agent_messages"` / `from dayu.engine import CancelledError` 仍失败。
   - 临时构造 minimal `RunnerSpec` + fake `CancellationToken`，实例化 `AsyncOpenAIRunner`，断言 `isinstance(..., AsyncRunner)`。
6. 汇报：改了什么、验证了什么、未覆盖项、README 判断结果。
7. 等 review Agent → 总控 → 用户确认后才提交 GitHub。
