# OLD / NEW Engine 对比报告

## 对比范围

- OLD：`~/workspace/dayu-agent/dayu/engine`
- NEW：`~/workspace/dayu-agent-r/dayu/engine`
- 对比维度：OpenAI 协议处理逻辑、事件流、状态机、错误处理逻辑。
- 真源口径：只对照当前代码，不使用设计意图替代代码事实。

## 总体结论

NEW 不是对 OLD 的原地重命名，而是把 OLD 中混在 Runner / Agent 内的职责重新分层：

- OpenAI-compatible 协议解析仍保留了主要兼容点，包括 SSE / non-stream 双路径、reasoning 内容归一、tool_calls 聚合、`stream_options.include_usage` 门控、Gemini `extra_content.google.thought_signature` 回传。
- 事件边界发生结构性变化：OLD 对外暴露一个宽松 `StreamEvent` 流；NEW 明确拆成 Runner 内部 `RunnerEvent` 与 Engine 对外 `EngineEvent`。
- 工具执行边界发生结构性变化：OLD Runner 内部执行工具；NEW Runner 只归一 provider 协议，Agent 才调用 `ToolExecutor`。
- 状态机从 OLD 的单个长循环迁移为 NEW 的可分类状态机，并新增唯一终态锁、取消 / 挂起终态、Runner close 收口。
- 错误处理从 OLD 的自由字符串 `error_event` 转为 NEW 的结构化协议错误、HTTP 错误和 Engine terminal failure；context overflow 从 Engine 内部压缩重试改为 Host compaction 请求事实。

## 1. OpenAI 协议处理逻辑

### 相同点

1. 两边都支持 OpenAI-compatible chat completion 的流式与非流式响应。
   OLD 在 `AsyncOpenAIRunner.call` 中按 `Content-Type` 选择 SSE 或 JSON；`text/event-stream` 走 `_process_sse_stream`，`application/json` 或非流式请求走 `_process_non_stream`。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1114-1180`。
   NEW 在 `_do_attempt` 中同样按 `options.stream` 与 `Content-Type` 选择 `SSEParser` 或 `parse_non_stream_response`。证据：`dayu/engine/runners/openai/runner.py:375-392`。

1. 两边都保留 `stream_options.include_usage` 的能力门控。
   OLD 仅在 `stream and supports_stream_usage` 时写入。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1059-1061`。
   NEW 仅在 `options.stream and spec.supports_stream_usage` 时写入。证据：`dayu/engine/runners/openai/payload.py:342-344`。

1. 两边都保留 reasoning 协议归一。
   OLD SSE 路径把正文中 vendor 私有 reasoning 标签剥离到 reasoning buffer，并同时处理原生 `reasoning_content`。证据：`~/workspace/dayu-agent/dayu/engine/sse_parser.py:587-602`。
   NEW SSE 路径做同类归一并产出 `RunnerReasoningDeltaData`。证据：`dayu/engine/runners/openai/sse_parser.py:289-313`。
   NEW non-stream 路径还显式保留 OLD 的 `extracted_reasoning + native_reasoning` 顺序。证据：`dayu/engine/runners/openai/non_stream_parser.py:202-210`。

1. 两边都只处理 `tool_calls`，不支持 legacy `function_call`。
   OLD non-stream 路径注释明确只处理 `tool_calls`。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1672-1675`。
   NEW non-stream 解析只读取 `message.tool_calls` 并转成 `ToolCallRequest`。证据：`dayu/engine/runners/openai/non_stream_parser.py:211-230`。

1. 两边都兼容 tool call delta 缺失 `index` 的 provider 行为。
   OLD 通过 id 查找已有 buffer，或用数组位置 / 新 index 兜底。证据：`~/workspace/dayu-agent/dayu/engine/sse_parser.py:642-687`。
   NEW 用 `ToolCallAggregator` 按 `index`、`id` 和 position fallback 归属。证据：`dayu/engine/runners/openai/tool_call_aggregator.py:106-176`。

1. 两边都保留 Gemini tool call `extra_content` / thought signature 回传能力。
   OLD 从 tool call delta 中保留 `extra_content` 并在组装结果时写回。证据：`~/workspace/dayu-agent/dayu/engine/sse_parser.py:790-799`。
   NEW 将 `extra_content.google.thought_signature` 解析为 `GeminiToolCallState`，再在 outbound assistant tool call 中投影回 `extra_content.google.thought_signature`。证据：`dayu/engine/runners/openai/tool_call_aggregator.py:184-222`、`dayu/engine/runners/openai/payload.py:78-116`。

### 差异点

1. 请求扩展从自由 payload 变成强类型 provider extension。
   OLD 合并 `default_extra_payloads` 与调用级 `extra_payloads` 后直接并入请求 payload。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1040-1057`。
   NEW 只接受 `RunnerCallOptions` 显式字段和 `ProviderRequestExtension` 封闭联合，并用 `match` 投影到顶层或 `extra_body.google`。证据：`dayu/engine/runners/openai/payload.py:188-245`、`dayu/engine/runners/openai/payload.py:312-344`。
   影响：NEW 类型边界更强，但 OLD 中依赖任意 `extra_payloads` 的调用方不能直接迁移。

1. `supports_streaming` 在 NEW Runner 中不是自动降级条件。
   OLD 在 `stream and not self.supports_stream` 时自动把 `stream=False`。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1035-1038`。
   NEW `RunnerSpec` 有 `supports_streaming` 字段，但 OpenAI Runner 的 payload 构建和 `_do_attempt` 只使用 `RunnerCallOptions.stream`，当前未在 Runner 内部检查 `spec.supports_streaming`。证据：`dayu/engine/contracts/runner_spec.py:259-260`、`dayu/engine/runners/openai/payload.py:328-344`、`dayu/engine/runners/openai/runner.py:381-392`。
   影响：如果 Host 仍传 `stream=True` 给不支持 streaming 的 provider，NEW Runner 不会像 OLD 一样在 Engine 内自动降级。

1. 未知 `Content-Type` 的 fallback 策略不同。
   OLD 在 HTTP 200 但既非 SSE 也非 JSON 时，若请求是 stream 则尝试 SSE，否则尝试 JSON。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1155-1179`。
   NEW 只有 `options.stream and text/event-stream` 才走 SSE，其余 HTTP 200 都读完整 body 后按 non-stream JSON 解析。证据：`dayu/engine/runners/openai/runner.py:381-392`。
   影响：对返回非标准 content type 但实际是 SSE 的 provider，NEW 行为与 OLD 不同。

1. 多候选 `n > 1` 的处理消失。
   OLD 发现 payload 中 `n > 1` 会覆盖为 `1`。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1071-1079`。
   NEW 强类型调用选项不暴露 `n`，也没有自由 `extra_payloads` 注入路径。证据：`dayu/engine/contracts/runner_spec.py:306-318`、`dayu/engine/runners/openai/payload.py:328-344`。
   影响：这是接口收敛，不是协议等价；旧调用方若依赖 `n`，需要在 Host/配置适配层另行表达或明确不支持。

1. 协议错误从“parser 记录后 Runner 组装 error_event”改为“parser 直接产出结构化协议错误事件”。
   OLD SSE parser 将错误记录到 `protocol_errors`，由 Runner 后续产出 `content_complete + error_event`。证据：`~/workspace/dayu-agent/dayu/engine/sse_parser.py:450-473`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1430-1455`。
   NEW SSE parser 直接产出 `RunnerProtocolErrorData + RunnerDoneData(ERROR)`。证据：`dayu/engine/runners/openai/sse_parser.py:180-201`、`dayu/engine/runners/openai/sse_parser.py:228-247`。

## 2. 事件流

### 相同点

1. 两边都有内容增量、reasoning 增量、内容完成、usage、迭代开始、最终回答等事件语义。
   OLD `EventType` 包含 `content_delta`、`content_complete`、`reasoning_delta`、`iteration_start`、`metadata`、`final_answer`。证据：`~/workspace/dayu-agent/dayu/engine/events.py:24-50`。
   NEW `EngineEventType` 包含 `content_delta`、`reasoning_delta`、`content_completed`、`usage_reported`、`iteration_started`、`final_answer`。证据：`dayu/engine/contracts/engine_events.py:34-51`。

1. 两边都把 usage 作为可观察事件进入上层。
   OLD Runner 在 done 后额外产出 `metadata_event("token_usage_summary")`。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1543-1556`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1837-1845`。
   NEW Runner 产出 `RunnerUsageRecordedData`，Agent 提升为 `UsageReportedData`。证据：`dayu/engine/runners/openai/sse_parser.py:413-451`、`dayu/engine/agent.py:1048-1070`。

1. 两边都保留工具调用进入下一轮前的 assistant tool_calls + tool messages 注入语义。
   OLD 在工具批次完成后构建 assistant tool_calls，并逐条追加 tool message。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:999-1061`。
   NEW 在 `_inject_tool_messages` 中追加 `AssistantMessage(tool_calls=...)` 与对应 `ToolMessage`。证据：`dayu/engine/agent.py:1504-1543`。

### 差异点

1. 事件模型从单层宽松 `StreamEvent` 变为双层封闭契约。
   OLD `StreamEvent.data` 是 `Any`，`metadata` 是 `Dict[str, Any]`。证据：`~/workspace/dayu-agent/dayu/engine/events.py:53-64`。
   NEW `RunnerEventData` 与 `EngineEventData` 都是封闭联合，并使用 dataclass 表达具体 data。证据：`dayu/engine/contracts/runner_events.py:205-233`、`dayu/engine/contracts/engine_events.py:289-300`。
   影响：NEW 更利于类型检查与边界治理，但旧事件消费者不能按原 `data` 字典形态直接消费。

1. Runner 事件不再等同于调用方事件。
   OLD Runner 直接产出调用方可见的 `StreamEvent`，Agent 主要是注解、聚合和继续状态机。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:989-995`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:760-864`。
   NEW Runner 只产出 `RunnerEvent`，Agent 在 `_consume_runner_event` 中提升为 `EngineEvent`；`RunnerToolCallDeltaData` 和 HTTP error 默认不直接暴露为 EngineEvent。证据：`dayu/engine/agent.py:987-1191`。

1. 工具事件的对外语义发生变化。
   OLD 对外暴露 `tool_call_start`、`tool_call_delta`、`tool_call_dispatched`、`tool_calls_batch_ready`、`tool_call_result`、`tool_calls_batch_done`。证据：`~/workspace/dayu-agent/dayu/engine/events.py:32-38`。
   NEW 对外暴露 `tool_call_requested`、`tool_result_accepted`、`tool_awaiting`，不再把 provider tool_call delta 或 batch ready/done 作为 Engine 对外事件。证据：`dayu/engine/contracts/engine_events.py:41-43`、`dayu/engine/agent.py:1157-1185`、`dayu/engine/agent.py:1316-1412`。
   影响：UI 若依赖 OLD 的工具调用流式 delta 或 batch 事件，需要改为观察 NEW 的工具请求/结果事件；NEW 不提供等价的外部 tool_call_delta。

1. 终态从“final answer 或错误事件后生成器结束”变为显式四类 terminal。
   OLD `ERROR` 和 `DONE` 都是普通 `StreamEvent`，成功时才有 `FINAL_ANSWER`。证据：`~/workspace/dayu-agent/dayu/engine/events.py:43-50`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:1227-1241`。
   NEW terminal 集合是 `final_answer`、`run_failed`、`run_cancelled`、`run_suspended`，并由 `_terminal_seen` 锁定唯一终态。证据：`dayu/engine/contracts/engine_events.py:48-51`、`dayu/engine/agent.py:1779-1845`。

## 3. 状态机

### 相同点

1. 两边都是多轮 LLM iteration + 工具闭环。
   OLD 在 `while iteration < max_iterations` 中消费 Runner 事件，工具批次完成后注入 assistant/tool messages 并 `continue` 下一轮。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:697-760`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:964-1136`。
   NEW 在 `for iteration_index in range(ordinary_iterations)` 中先跑 Runner，再分类为 final / failed / tool calls；工具完成后注入消息进入下一轮。证据：`dayu/engine/agent.py:497-710`。

1. 两边都支持 `finish_reason=length` 的续写。
   OLD 根据 `done_event_summary.truncated` 追加 assistant 片段与 continuation prompt。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:1154-1215`。
   NEW 在 `_handle_length_final_decision` 中追加 assistant 片段与 continuation prompt，并受 continuation attempts 与 iteration budget 约束。证据：`dayu/engine/agent.py:738-819`。

1. 两边都支持达到工具 / 迭代边界后的 fallback。
   OLD 在 max iterations 或连续失败工具批次后按 `fallback_mode` 选择 `raise_error` 或 `force_answer`。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:1081-1128`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:1250-1289`。
   NEW 在 `_fallback_after_tools` 中按 `AgentFallbackMode` 选择 `RUN_FAILED` 或 force-answer Runner 调用。证据：`dayu/engine/agent.py:1545-1594`。

1. 两边都在 tool loop 中保留 reasoning 内容，避免 thinking provider 后续请求丢上下文。
   OLD 在工具调用 assistant message 中回填 `reasoning_content`。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:1001-1018`。
   NEW 在 `_inject_tool_messages` 中把 `decision.reasoning_content` 写入 `AssistantMessage`。证据：`dayu/engine/agent.py:1520-1534`。

### 差异点

1. 工具执行从 Runner 内并发执行变为 Agent 内顺序执行。
   OLD `_emit_tool_batch` 创建多个 task，并用 `asyncio.gather` 等待整批工具结果。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:904-939`。
   NEW `_execute_tool_batch` 对 `decision.tool_calls` 逐个 `await self._execute_one_tool`。证据：`dayu/engine/agent.py:1292-1430`。
   影响：NEW 的工具批次时序更易治理，并支持 awaiting/suspend；但并行工具吞吐与 OLD 不同。

1. context overflow 的责任边界改变。
   OLD Agent 收到 `context_overflow` 后在 Engine 内压缩 messages 并重试，且该重试不计入 iteration。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:893-960`。
   NEW Agent 将 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 提升为 `context_compaction_requested`，并设置可恢复 `RunFailedData(context_compaction_required)`；是否压缩由 Host 决定。证据：`dayu/engine/agent.py:1100-1136`。
   影响：这是符合 NEW 分层的治理迁移，但不是 OLD 行为的原地等价。

1. OLD 有语义级重复工具调用干预，NEW 只防重复 tool_call_id。
   OLD 用 `DuplicateCallGuard` 基于工具名、参数、结果做 hint / hard stop。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:671-673`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:807-825`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:1063-1128`。
   NEW 只在同一 run 内检测重复 `tool_call_id`。证据：`dayu/engine/agent.py:1304-1314`。
   影响：如果 OLD 的重复调用治理是产品语义，NEW 当前 Engine 代码没有等价机制；可能已迁移到 Host/Service，也可能是行为差异。

1. OLD 内置上下文预算治理与工具结果预算截断，NEW Engine 当前未保留等价预算状态机。
   OLD 有 soft-limit 主动压缩、overflow 压缩、tool result 预测性预算截断。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:675-747`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:1027-1049`。
   NEW `ContextBudgetSnapshot` 只用于 `context_compaction_requested` 的事件载荷，当前填充为 0 token 快照。证据：`dayu/engine/agent.py:1118-1129`。
   影响：NEW 将预算治理从 Engine 移出或尚未接入；这不是协议解析问题，但会影响长上下文运行行为。

1. NEW 明确实现 run-scoped 资源与终态边界。
   OLD 成功 / 错误路径主要靠事件流 return 收口，未看到唯一 terminal 锁。
   NEW 在 `finally` 中关闭 Runner 并释放 run slot，同时 `_make_terminal_event` 用 `_terminal_seen` 防重复终态。证据：`dayu/engine/agent.py:711-713`、`dayu/engine/agent.py:1831-1845`。

1. NEW 新增工具等待挂起状态。
   OLD 工具结果只有结构化 ok/error/timeout/cancelled 结果事件。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:949-987`。
   NEW `ToolAwaitingOutcome` 会先产出 `tool_awaiting`，再以 `run_suspended` 终态收口。证据：`dayu/engine/agent.py:1371-1398`、`dayu/engine/agent.py:1729-1752`。

## 4. 错误处理逻辑

### 相同点

1. 两边都区分可重试 HTTP / 网络错误与不可重试错误。
   OLD 用 `RETRIABLE_STATUS_CODES`、`NON_RETRIABLE_STATUS_CODES`、`_calculate_backoff` 处理 429 / 5xx / timeout / network。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1193-1259`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1863-1886`。
   NEW 用 `RunnerHTTPErrorCode`、`classify_http_status`、`is_retriable`、`compute_retry_decision` 处理。证据：`dayu/engine/runners/openai/runner.py:229-284`、`dayu/engine/runners/openai/runner.py:345-374`。

1. 两边都把 provider 协议错误视为不可继续的本轮错误。
   OLD SSE JSON / UTF-8 / tool call 组装错误会转为 `error_event` 并 return。证据：`~/workspace/dayu-agent/dayu/engine/sse_parser.py:295-304`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1430-1455`。
   NEW SSE / non-stream 协议错误会产出 `RunnerProtocolErrorData` 与 `RunnerDoneData(ERROR)`，Agent 再转成 `provider_protocol_error` 与 `run_failed` 候选。证据：`dayu/engine/runners/openai/sse_parser.py:180-201`、`dayu/engine/runners/openai/non_stream_parser.py:90-139`、`dayu/engine/agent.py:1071-1099`。

1. 两边都保留 context length exceeded 的特殊识别。
   OLD 400 且命中文本 / 结构化特征时归类为 `context_overflow`。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:306-323`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:448-449`。
   NEW 检测 context overflow 后产出 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`。证据：`dayu/engine/runners/openai/runner.py:350-360`、`dayu/engine/contracts/runner_events.py:51-64`。

### 差异点

1. HTTP / 网络终态错误从普通错误事件变为 RunnerHTTPError + RunnerDone(ERROR) + Engine RUN_FAILED。
   OLD 最终 HTTP / timeout / network 错误 yield `error_event` 后 return，通常没有专门 terminal run_failed。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1232-1259`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1289-1337`。
   NEW Runner 在 terminal / exhausted retriable error 时 yield `runner_http_error` 再 yield `runner_done(ERROR)`；Agent 将其转成 `RunFailedData`。证据：`dayu/engine/runners/openai/runner.py:229-270`、`dayu/engine/agent.py:1100-1136`、`dayu/engine/agent.py:1222-1228`。

1. context overflow 从 Engine 内部可重试错误变为 Host 可恢复治理信号。
   OLD `context_overflow` 触发压缩后重试，压缩耗尽才改写为 `context_overflow_exhausted`。证据：`~/workspace/dayu-agent/dayu/engine/async_agent.py:893-945`。
   NEW 产出 `context_compaction_requested`，最终失败候选为 recoverable `context_compaction_required`。证据：`dayu/engine/agent.py:1112-1129`。

1. 取消语义更强。
   OLD Runner / parser 多处通过 cancellation token 抛 `EngineCancelledError`，工具批次取消会中止 gather。证据：`~/workspace/dayu-agent/dayu/engine/sse_parser.py:273-278`、`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:911-939`。
   NEW Runner 取消时直接退出生成器且不补 `RunnerDoneData`；Agent 负责产出 `run_cancelled` terminal，并记录 requested / accepted / finished 时间。证据：`dayu/engine/runners/openai/runner.py:285-293`、`dayu/engine/agent.py:1754-1777`。

1. 工具错误处理从“工具结果错误继续进入 LLM”变为“completed/failed outcome 继续；timeout/awaiting/cancel 可成为 run 终态”。
   OLD 工具超时 / 执行异常被封装成 `tool_call_result`，批次结束后仍注入工具消息进入下一轮，除非触发连续失败或重复调用 fallback。证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:780-807`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:999-1061`。
   NEW 普通异常归一为 `ToolFailedOutcome(tool_executor_exception)` 并继续注入；但 `WaitTimedOut` 直接 `run_failed(tool_execution_timeout)`，`ToolAwaitingOutcome` 直接 `run_suspended`，取消直接 `run_cancelled`。证据：`dayu/engine/agent.py:1362-1398`、`dayu/engine/agent.py:1445-1502`。

1. 错误码从自由字符串迁移为部分强类型枚举。
   OLD `error_event` 依赖 metadata 中的 `error_type` 字符串。证据：`~/workspace/dayu-agent/dayu/engine/events.py:43-50`、`~/workspace/dayu-agent/dayu/engine/async_agent.py:872-934`。
   NEW HTTP 错误使用 `RunnerHTTPErrorCode` 枚举，Engine terminal 使用 `RunFailedData.error_code` 中性字符串。证据：`dayu/engine/contracts/runner_events.py:36-64`、`dayu/engine/contracts/engine_events.py:275-286`。

## 需要关注的行为差异

1. `supports_streaming` 未在 NEW OpenAI Runner 内部降级。若 Host 没有提前保证 `RunnerCallOptions.stream` 与 `RunnerSpec.supports_streaming` 一致，NEW 会向不支持流式的 provider 发送 `stream=True`。
1. OLD 的语义级重复工具调用治理在 NEW Engine 目录内没有等价实现；当前只防重复 `tool_call_id`。
1. OLD 的 Engine 内部 context budget / compaction / tool result capping 在 NEW Engine 内不再等价存在；NEW 改为暴露 compaction requested 事实给 Host。
1. OLD 对 `tool_call_start` / `tool_call_delta` / batch ready / done 的外部可见性，在 NEW EngineEvent 中不再保留；需要确认 UI 或 trace 消费方是否已经迁移到新事件模型。
1. 工具批次执行并发度从 OLD 并发变成 NEW 顺序执行，可能影响多工具调用场景延迟。

## 结论

从 OpenAI provider 协议解析角度看，NEW 保留了 OLD 的核心兼容行为，并把 payload、SSE、non-stream、tool call 聚合拆成更可测试的边界。从 Engine 外部行为角度看，NEW 与 OLD 不是完全等价：事件流、终态、工具执行位置、context overflow 治理、重复工具调用治理和工具批次并发度都发生了真实行为变化。这些差异大多符合 NEW 的 Host 强治理 / Engine 协议归一定位，但其中 `supports_streaming` 降级、重复工具治理、预算治理归属和工具并发度需要由后续迁移任务明确是否接受。
