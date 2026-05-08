# Engine 开发手册

本手册记录当前 Engine 已落地的开发边界。Engine 位于分层链路最下游：

```text
UI -> Service -> Host -> Engine
```

Host 是 run/session 生命周期、取消真源、治理与工具运行时的拥有者。Engine 只消费 Host 注入的强类型请求、Runner 规约、取消观察 token 与工具契约快照，并产出可被 Host 订阅的 `EngineEvent`。

## 当前职责

Engine 当前负责：

- 定义 Engine 公共契约：`AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`RunnerEvent`、`AsyncRunner`、`RunnerSpec`、`AgentPolicy`。
- 提供函数式入口：`run_agent_messages(request)` 与 `run_agent_and_wait(request)`。
- 在私有 run-scoped Agent 中消费 Runner 事件流，并提升为带 `session_id`、`run_id`、`sequence`、`event_id` 的 `EngineEvent`。
- 执行普通 completed / failed tool calling 闭环：Runner tool call -> `ToolExecutionRequest` -> `ToolExecutor.execute` -> tool message 注入下一轮 Runner。
- 若 ToolExecutor 返回的成功结果携带截断信息，Agent 会把它投影为 LLM-facing
  `truncation.next_action="fetch_more"` 与 `truncation.fetch_more_args`；Engine 不持有 cursor store，也不解释
  `scope_token`。
- 在 `finish_reason=length` 时执行 final-answer text continuation；continuation 轮固定 `tools=()`，只续写被截断的最终回答文本。
- 收口三类终态：`final_answer`、`run_failed`、`run_cancelled`。
- 维护 OpenAI-compatible Runner，把 provider 响应归一为 `RunnerEvent`。
- 在 Runner / Agent 边界识别 provider context overflow，并暴露强类型
  `context_compaction_requested` 与 recoverable `run_failed("context_compaction_required")` 事实。
- 在 Runner 边界提供诊断日志与 SSE idle heartbeat / timeout 处理；这些诊断不进入事件契约。

Engine 当前不负责：

- Host ToolRegistry、工具权限、工具执行调度或长事务等待。
- awaiting / `run_suspended` 工具主链路。
- trace store、transcript 持久化、conversation memory。
- context compact policy、memory、retry、RunInput 重建、OLD `TruncationManager`、framework `fetch_more` 路由
  或语义压缩。
- 财报文档存取；财报文档只能通过 `dayu.fins.storage` 所属仓储边界处理。

## 稳定依赖表面

Host 稳定依赖以下表面：

- `dayu.engine.run_agent_messages`
- `dayu.engine.run_agent_and_wait`
- `dayu.engine.contracts`
- `dayu.contracts`

`run_agent_messages` 返回异步生成器；调用方必须迭代至结束，或在提前
停止消费时显式调用 `aclose()`，以触发 Runner 关闭和 run-scoped 资源
收尾。`run_agent_and_wait` 会完整消费该事件流。

Host 不应依赖以下实现细节：

- 私有 `_AsyncAgent`
- `AsyncOpenAIRunner` 具体类
- Runner close 的内部实现
- Engine 私有错误码常量

`dayu.engine.__all__` 当前只导出契约与两个真实函数式入口，不导出 Agent / Runner 实现类，也不导出公共取消异常。

## 事件流

Runner 只产出 `RunnerEvent`。RunnerEvent 不包含 Host 治理字段，不携带 `session_id`、`run_id`、`sequence` 或 `event_id`。

私有 Agent 负责把 RunnerEvent 提升为 EngineEvent：

- `RUNNER_CONTENT_DELTA` -> `RUNNER_CONTENT_DELTA`
- `RUNNER_REASONING_DELTA` -> `RUNNER_REASONING_DELTA`
- `RUNNER_CONTENT_COMPLETED` -> `RUNNER_CONTENT_COMPLETED`
- `RUNNER_USAGE_RECORDED` -> `RUNNER_USAGE_RECORDED`
- `PROVIDER_PROTOCOL_ERROR` -> `PROVIDER_PROTOCOL_ERROR`
- `RUNNER_HTTP_ERROR(context_length_exceeded)` -> `CONTEXT_COMPACTION_REQUESTED`，随后由 recoverable
  `RUN_FAILED(context_compaction_required)` 收口；Host 决定是否 compact / retry
- `RUNNER_DONE` -> `RUNNER_DONE`
- Runner 完整 tool call 在 Agent 确认可执行后提升为 `TOOL_CALL_REQUESTED`
- ToolExecutor completed / failed outcome 被 Agent 接受后提升为 `TOOL_RESULT_ACCEPTED`

普通 HTTP error 当前不提升为单独 EngineEvent；Agent 将其记录为失败候选，并收口为 `run_failed`。
context overflow 是例外：OpenAI-compatible Runner 先在 provider adapter 边界把结构化
`error.code=context_length_exceeded` 或受控 OLD 多 provider message 信号归一为
`RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`，Agent 再提升为 `context_compaction_requested`。若 provider
payload 已给出明确非空结构化 `error.code` 且不是 `context_length_exceeded`，Runner 不再用 message
marker fallback 覆盖该结构化分类。
HTTP overflow 边界没有 provider usage 数据时，`ContextBudgetSnapshot` 使用 `0/0/0` 占位；真正的
compact before / after 诊断由 Host estimator 记录。
显式契约事实不得塞进 `metadata`。

`final_answer` 只能由 Agent 产生，Runner 不能产生最终回答终态。

## Run-Scoped Agent

当前 Agent 是 run-scoped 私有实现。每次函数式入口调用都会创建 Runner 与 Agent，单次 run 结束后关闭 Runner。

生命周期：

1. 申请当前 Agent 实例运行槽位，同一实例并发运行 fail-fast。
2. 若 cancellation token 已取消，先 close Runner，再产出 `run_cancelled`。
3. 产出 `iteration_started`。
4. 按 `disable_tools`、`AgentPolicy.allow_tool_calls`、Runner tool calling 能力决定本轮有效工具 schema。
5. 消费并提升 RunnerEvent。
6. 若 Runner 请求普通工具调用，按 `index_in_iteration` 串行调用 ToolExecutor，并注入 assistant tool_calls 与 tool messages。
7. 若 Runner 给出普通内容或错误边界，按 finish reason 收口唯一 terminal；`LENGTH` 在预算内进入 continuation。
8. 普通工具轮次耗尽或连续全失败工具批次达到阈值时，按 `AgentPolicy.fallback_mode` force-answer 或 `run_failed`。
9. success / failure / cancellation 都执行 Runner close。

Runner close 失败只记录日志，不覆盖已经确定的业务 terminal。

## Agent 状态机

当前 Agent 支持多轮普通 tool calling：

- `max_iterations < 1` -> `run_failed("max_iterations_exceeded")`
- 正常 `STOP` -> `final_answer`
- `CONTENT_FILTER` -> `final_answer(filtered=True, degraded=True)`
- `LENGTH` -> final-answer text continuation；continuation 轮固定 `tools=()`，不进入普通 tool loop
- continuation 轮再次请求工具 -> `run_failed("continuation_tool_call_not_allowed")`
- 达到 `continuation_max_attempts` 或 `max_iterations` 边界 -> `final_answer(degraded=True)`
- `ERROR` -> `run_failed`
- provider context overflow -> `context_compaction_requested` -> `run_failed("context_compaction_required", recoverable=True)`
- 工具被禁用或 Runner 不支持工具时收到 `TOOL_CALLS` -> `run_failed("tool_call_not_enabled")`
- `TOOL_CALLS` 且工具可用 -> `tool_call_requested` -> ToolExecutor -> `tool_result_accepted` -> 注入下一轮 Runner
- completed 工具结果和 failed 工具结果都会进入 LLM 上下文；failed outcome 不是 cancellation，也不会直接伪装成 final answer
- framework `fetch_more` 对 Engine 仍只是普通 tool call：Engine 负责发出 `ToolExecutionRequest` 与注入
  ToolMessage，实际路由、cursor 校验、EventLog facts 与敏感参数 redaction 由 Host ToolRuntime / Host 翻译层负责。
- ToolExecutor 返回 awaiting -> `run_failed("tool_awaiting_not_supported_in_phase3")`
- Runner 流结束但无 `RunnerDoneData` -> `run_failed("runner_abnormal_stop")`，若此时 token 已取消则 `run_cancelled`

terminal event 在单次 run 内唯一，`sequence` 从 0 起单调递增，`event_id` 以 run 内 sequence 保持唯一。

## Tool Calling

ToolExecutor 由 EngineWorker 替 Host 在选定执行环境中代持，并通过 `AgentRunRequest.tool_executor` 提供给 Engine。Engine 只调用 `ToolExecutor.execute(request)`，不持有 ToolRegistry，不发现工具，不执行权限、审计、路径白名单或长事务治理。

工具结果注入下一轮 Runner 前会先投影成 LLM-facing JSON 字符串：

- 成功且 value 是 JSON object 时展开 value，不包内部 `ok/value` 信封。
- 成功且 value 不是 JSON object 时包成 `{"content": ...}`。
- 失败时投影 `error` / `message`，仅在 hint 非空时投影 `hint`。
- 当前 `ToolTruncationInfo` 只承载内部截断治理事实，不含 LLM 可执行续读动作；Phase 3 不把 `has_more`、scope token 或 scope hash 投影给 LLM。

当最后一轮普通工具调用执行完后，默认 `AgentFallbackMode.FORCE_ANSWER` 会追加 `AgentPolicy.fallback_prompt` 作为 `UserMessage`，以 `tools=()` 再调用 Runner，并产出 `final_answer(degraded=True)`。`AgentFallbackMode.RAISE_ERROR` 才直接 `run_failed("max_iterations_exceeded")`。连续全失败工具批次达到 `AgentPolicy.max_consecutive_failed_tool_batches` 时使用同一 fallback mode 收口。

force-answer 只尝试一次；如果该降级 Runner 仍请求工具或没有产出可用正文，Agent 直接收口为 `run_failed`，不会继续重试或再次执行工具。

## Final Answer Continuation

`finish_reason=length` 表示模型最终回答文本被 provider 截断。当前 Agent 会在 `AgentPolicy.continuation_max_attempts` 预算内追加 `AgentPolicy.continuation_prompt`，并以 `tools=()` 再调用 Runner 续写最终回答文本。多轮 continuation 的 partial content 会按顺序拼接，最终产出一个 `final_answer`。

Continuation 是 final-answer text continuation，不是普通 tool loop continuation。Continuation 轮不会向 Runner 暴露工具；如果 provider 仍返回 tool calls，Agent 收口为 `run_failed("continuation_tool_call_not_allowed")`，不会调用 ToolExecutor。

`CONTENT_FILTER` 不进入 continuation，直接以 `final_answer(filtered=True, degraded=True)` 收口。达到 `continuation_max_attempts` 或 `max_iterations` 边界时，Agent 使用已拼接内容产出 `final_answer(degraded=True)`。

## 取消优先级

取消是 Host 拥有的治理事实，Engine 只观察 `CancellationToken`。当前公共取消终态是 `run_cancelled` / `EngineRunOutcomeCancelled`，不是公共取消异常。

优先级规则：

- 取消优先于 `final_answer`。
- 取消优先于 failure terminal。
- 取消优先于工具结果继续注入与 force-answer final。
- Runner 因取消自然终止且没有 `RunnerDoneData` 时，Agent 收口为 `run_cancelled`。
- `RunCancelledData.finished_at` 表示 Runner close 尝试完成后的时间。
- 外层 `asyncio.CancelledError` 继续透传。

## OpenAI-Compatible Runner

当前唯一内置 Runner 是 OpenAI-compatible Runner。它负责：

- 构造 OpenAI 风格请求 payload。
- 按 `RunnerSpec.provider_request` 强类型扩展投影 provider 私有请求字段：
  `OpenAIReasoningExtension`、`AnthropicThinkingExtension`、
  `DeepSeekThinkingExtension`、`MimoThinkingExtension`、
  `GeminiThinkingExtension`、`QwenThinkingExtension`。
- provider 私有字段用 `None` 表示不传；只有 provider 文档把 `0`
  定义为显式关闭时才传 `0`。
- 解析 SSE 与 non-stream JSON 响应。
- 归一 content、reasoning、usage、tool call、HTTP error、protocol error 与 done 事件。
- 识别 context overflow：结构化 `context_length_exceeded` 优先，结构化非 overflow code 会阻止 message
  fallback；当前结构化 code 只读取 `{"error":{"code":...}}` 与 `{"code":...}`，数组包装等新增
  provider shape 不在 P4 范围；fallback 只覆盖已测试的 provider overflow 信号。Runner 不做 compact 或 retry。
- 执行 HTTP retry / backoff。
- 观察 cancellation token。
- 关闭 HTTP 资源。

Runner 不执行工具，不依赖 `ToolExecutor` / ToolRegistry，不产出 `EngineEvent`。

## Diagnostics 与 SSE Idle

Runner 使用标准库 `logging.getLogger(__name__)` 记录运行边界诊断。日志装配入口在 `dayu.runtime.log`，Engine 代码不导入 `dayu.runtime.log`。

SSE idle heartbeat / timeout 属于 Runner 字节流读取边界：

- heartbeat 只写诊断日志，不进入 RunnerEvent / EngineEvent。
- hard timeout 映射为 Runner HTTP timeout 错误，并沿 RunnerEvent 失败路径收口。
- cancellation 与 timeout 同时出现时，取消优先。

## 扩展点

当前稳定扩展点是契约而不是实现类：

- 新 Runner 需要实现 `AsyncRunner`，只产出 `RunnerEvent`。
- 新 provider 参数应进入 `RunnerSpec` / provider request extension 的强类型字段。
- 新 EngineEvent 或 RunnerEvent 必须扩展封闭 data 联合，并补齐穷尽匹配测试。
- awaiting / `run_suspended`、Host resume、trace store、conversation memory、context compact policy、
  OLD `TruncationManager` 与 framework `fetch_more` 路由不属于 Engine；这些能力不能通过当前 Agent 私自接入。
