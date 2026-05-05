# Engine Phase 1 Runner 协议一致性 Round 2 Review

## 1. Review 结论

**通过**。

NEW OpenAI-compatible Runner 在协议语义、消息流、状态机和边界行为上与 OLD 高度一致。所有协议关键路径均有直接代码证据比对，发现 0 个阻塞问题、0 个重要问题、4 个建议问题（均不阻塞验收）。200 个测试通过，pyright 0 errors / 0 warnings。

## 2. 阅读范围

实际阅读 NEW 文件：

- `AGENTS.md`
- `docs/engine/design.md`
- `docs/engine/phase1-plan.md`
- `docs/engine/phase1-plan-review.md`
- `docs/engine/phase1-code-review.md`
- `dayu/contracts/tool_call.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/runners/openai/*.py`（全部 13 个模块）
- `tests/engine/runners/openai/*.py`（全部 38 个测试文件）
- `tests/contracts/*.py`
- `tests/engine/contracts/*.py`

实际阅读 OLD 强参考源：

- `~/workspace/dayu-agent/dayu/engine/async_openai_runner.py`（1983 行）
- `~/workspace/dayu-agent/dayu/engine/sse_parser.py`（991 行）
- `~/workspace/dayu-agent/dayu/engine/reasoning_protocol.py`（121 行）
- `~/workspace/dayu-agent/dayu/engine/xml_extractor.py`（177 行）
- `~/workspace/dayu-agent/dayu/engine/README.md`（354 行）
- `~/workspace/dayu-agent/dayu/config/llm_models.json`（1442 行）
- `~/workspace/dayu-agent/tests/engine/test_sse_parser.py`（1575 行）
- `~/workspace/dayu-agent/tests/engine/test_async_agent.py`（2291 行）

## 3. OLD Runner 关键协议事实摘要

- **payload 构建**：`model` / `messages` / `temperature` / `stream` 为显式字段；`stream_options.include_usage=True` 仅当 `stream and supports_stream_usage`（L1059-1061）；`messages` 直接透传（含 `reasoning_content`）；`extra_payloads` 为开放袋合并。
- **SSE 解析**：行缓冲 + `data:` 前缀 + `[DONE]` 检测；多行 data 聚合；尾部残留 data 处理；UTF-8 增量解码（`codecs.getincrementaldecoder("utf-8")("strict")`）；非法 UTF-8 → protocol_error + break；empty choices + usage → usage 事件；content/reasoning 分流（XML 标签剥离 + 原生 `reasoning_content`）。
- **tool call delta**：按 `index` 聚合；缺失 `index` 时按 `id` 归属（`_resolve_tool_call_index` L659-687）；`arguments: null` 安全忽略（L758-761）；`extra_content` 透传到 buffer entry（L792-794）。
- **reasoning 协议**：`_detect_google_thinking` 探测 `extra_body.google.thinking_config.include_thoughts=True` → `tag_name="thought"`；`StreamingXMLTagExtractor` 剥离 `<thought>` 标签；`start_only=True` 安全锁。
- **non-stream**：`extract_full` 剥离 `<thought>`；`extracted_reasoning + native_reasoning` 合并顺序；tool_calls 完整校验（id/name/arguments 类型/JSON 解析）；`extra_content` 保留。
- **HTTP/retry**：`RETRIABLE_STATUS_CODES={429,500,502,503,504}`；`NON_RETRIABLE_STATUS_CODES={400,401,403,404}`；backoff `2 ** attempt`（无 cap）；`Retry-After` 直接使用。
- **cancellation**：`EngineCancelledError`（公共异常）；`_raise_if_cancelled()` 轮询；`_await_or_cancel` 竞速。
- **close**：`session.close()` 幂等；脏 session 废弃后重建。

## 4. NEW Runner 实现映射摘要

- **payload 构建**（`payload.py`）：`build_request_payload` 纯函数；4 种 `ProviderRequestExtension` 按 `match` + `assert_never` 穷尽投影；`stream_options` 受 `supports_stream_usage` 门控；`reasoning_content` 非 None 时保留；`provider_state` → `extra_content.google.thought_signature`。
- **SSE 解析**（`sse_parser.py`）：`SSEParser` 类；行缓冲 + `data:` 前缀 + `[DONE]`；多行 data 聚合；UTF-8 增量解码（`codecs.getincrementaldecoder("utf-8")(errors="strict")`）；非法 UTF-8 → `RunnerProtocolErrorData(invalid_utf8)` + `RunnerDoneData(ERROR)`；content/reasoning 分流（`StreamingXMLTagExtractor`）；tool call delta 委派 `ToolCallAggregator`。
- **tool call 聚合**（`tool_call_aggregator.py`）：`ToolCallAggregator` 类；按 `index` 聚合；缺失 `index` 时按 `id` 分配合成 index；`arguments: null` 安全忽略；`extra_content` → `ToolCallProviderState`；fatal/warning 两路错误累积。
- **reasoning 协议**（`reasoning_protocol.py` + `xml_tag_extractor.py`）：`detect_reasoning_protocol_hook` 探测 `GeminiThinkingExtension(include_thoughts=True)` → `tag_name="thought"`；`StreamingXMLTagExtractor` 剥离 `<thought>`；`start_only=True` 安全锁 + 永久失活。
- **non-stream**（`non_stream_parser.py`）：`parse_non_stream_response` 函数；`_split_thought` 剥离 `<thought>`；`inside + (reasoning or "")` 合并顺序；tool_calls 通过 `ToolCallAggregator` 复用。
- **HTTP/retry**（`error_classifier.py` + `retry_policy.py`）：`classify_http_status` / `classify_exception` → `RunnerHTTPErrorCode`；`is_retriable` 判断；429 专用 backoff（首次 4s, cap 60s, Retry-After cap 120s）；其它可重试 `2^(attempt-1)` cap 30s。
- **cancellation**（`cancellation_helpers.py`）：`_RunnerInterrupted`（私有异常）；`await_or_cancel` 轮询竞速；50ms 轮询间隔。
- **close**（`http_client.py`）：`HTTPClient.close()` 幂等。

## 5. Payload 构建对照结论

**结论：一致**。

| 字段 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| `model` | `self.model` | `spec.model` | ✓ |
| `messages` | 直接透传 `List[AgentMessage]` | `_serialize_message()` 逐条序列化 | ✓ 有意重设：NEW 强类型化 |
| `temperature` | `self.temperature`（必填） | `options.temperature`（可选） | ✓ |
| `max_tokens` | 未显式支持 | `options.max_tokens`（可选） | ✓ 合理扩展 |
| `top_p` | 未显式支持 | `options.top_p`（可选） | ✓ 合理扩展 |
| `stream` | 显式参数 | `options.stream` | ✓ |
| `stream_options` | `stream and supports_stream_usage` 门控 | `stream and spec.supports_stream_usage` 门控 | ✓ |
| `tools` | `self._tool_executor.get_schemas()` | `Sequence[ToolSchema]` 参数 | ✓ 有意重设：Runner 不依赖 ToolExecutor |
| `reasoning_content` | 透传（messages 直接传） | `reasoning_content is not None` 时写入 | ✓ |
| `provider_state` | `extra_content` 透传 | `GeminiToolCallState` → `extra_content.google.thought_signature` | ✓ |
| OpenAI `reasoning_effort` | `extra_payloads["reasoning_effort"]` 顶层 | `payload["reasoning_effort"]` 顶层 | ✓ |
| Anthropic `thinking` | `extra_payloads["thinking"]` 顶层 | `payload["thinking"]` 顶层 | ✓ |
| Gemini `thinking_config` | `extra_body.google.thinking_config` | `extra_body.google.thinking_config` | ✓ |
| Qwen `enable_thinking` | `extra_payloads["enable_thinking"]` 顶层 | `payload["enable_thinking"]` 顶层 | ✓ |
| `extra_payloads` 开放袋 | 支持（`**extra_payloads`） | 不支持（`ProviderRequestExtension` 封闭联合） | ✓ 有意重设 |

**证据**：

- OLD: `async_openai_runner.py:1048-1061`（payload 构建 + stream_options 门控）
- NEW: `payload.py:242-276`（`build_request_payload`）
- OLD: `llm_models.json:222-224`（OpenAI `reasoning_effort` 顶层）
- NEW: `payload.py:198-199`（OpenAI 顶层投影）
- OLD: `llm_models.json:428-435`（Gemini `extra_body.google`）
- NEW: `payload.py:208-219`（Gemini `extra_body.google` 投影）

## 6. SSE 解析对照结论

**结论：一致**。

| 协议点 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| `data:` 行处理 | `line_text[5:]` + 前缀空格跳过 | `stripped[len(_DATA_PREFIX):].lstrip(" ")` | ✓ |
| `[DONE]` 处理 | `_flush_event_data_lines` 检测 | `_dispatch_event_payload` 检测 | ✓ |
| 多行 data 聚合 | `event_data_lines` 列表 + 空行触发 flush | `_data_lines` 列表 + 空行触发 flush | ✓ |
| 尾部无换行 data | `trailing_line` 处理 | `_line_carry` 处理 | ✓ |
| 注释/空行 | `startswith(":")` 跳过；空行触发 flush | 非 `data:` 行忽略；空行触发 flush | ✓ |
| UTF-8 跨 chunk | `codecs.getincrementaldecoder("utf-8")("strict")` | `codecs.getincrementaldecoder("utf-8")(errors="strict")` | ✓ |
| invalid UTF-8 | `_record_protocol_error` + `break` | `RunnerProtocolErrorData(invalid_utf8)` + `RunnerDoneData(ERROR)` + `return` | ✓ |
| invalid JSON | `_record_protocol_error` + 继续 | `RunnerProtocolErrorData(sse_invalid_json)` + `RunnerDoneData(ERROR)` + 终止 | ✓ 有意重设：fatal 终态 |
| empty choices + usage | usage 事件仍产出 | usage 事件仍产出 | ✓ |
| content delta | `_yield_content_chunks` XML 分流 | `_extractor.feed` XML 分流 | ✓ |
| reasoning delta | XML 标签内 + 原生 `reasoning_content` | XML 标签内 + 原生 `reasoning_content` | ✓ |
| tool call delta | `_handle_tool_call_delta` 逐个处理 | `ToolCallAggregator.feed` 聚合 | ✓ |
| finish reason | `_stream_state["finish_reason"]` | `_FINISH_REASON_MAP` 映射 | ✓ |
| usage chunk | `result.usage` 记录 | `RunnerUsageRecordedData` 事件 | ✓ |
| fatal 后停止 | `_protocol_errors` → `return` | `_fatal_terminated` → `return` | ✓ |

**证据**：

- OLD: `sse_parser.py:216-394`（`parse_stream` 主循环）
- NEW: `sse_parser.py:126-177`（`SSEParser.parse` 主循环）
- OLD: `sse_parser.py:296-304`（UTF-8 增量解码 + 错误处理）
- NEW: `sse_parser.py:138-143`（UTF-8 增量解码 + 错误处理）
- OLD: `sse_parser.py:422-470`（`_flush_event_data_lines` + `[DONE]`）
- NEW: `sse_parser.py:212-254`（`_dispatch_event_payload` + `[DONE]`）

## 7. Tool call delta 聚合对照结论

**结论：一致**。

| 协议点 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| 按 `index` 聚合 | `_tool_calls_buffer[tool_index]` | `_partials_by_index[index]` | ✓ |
| 缺 `index` 按 `id` 归属 | `_resolve_tool_call_index` L659-687 | `_resolve_index` L114-149 | ✓ |
| `arguments: null` | 安全忽略（L758-761） | 安全忽略（`if isinstance(arguments, str)`） | ✓ |
| arguments 非字符串 | `_record_protocol_error` + `return` | `fatal_errors` 累积 + finalize 时跳过 | ✓ 等价终态 |
| 多 tool call 并发 | 按 `index` 分桶 | 按 `index` 分桶 + 合成 index | ✓ |
| `extra_content` 保留 | `entry["extra_content"] = tc_extra`（L793-794） | `partial.provider_state = new_state` | ✓ |
| Gemini `thought_signature` | `extra_content` 透传到 tool call batch | `GeminiToolCallState(thought_signature=...)` | ✓ |
| 缺 `id` 校验 | `_assemble_tool_calls` 校验 | `finalize` 校验 `tool_call_missing_id` | ✓ |
| 缺 `name` 校验 | `_assemble_tool_calls` 校验 | `finalize` 校验 `tool_call_missing_name` | ✓ |
| arguments 非法 JSON | `_assemble_tool_calls` 校验 | `_parse_arguments` 校验 `tool_call_arguments_invalid_json` | ✓ |
| pos fallback | `elif pos in self._tool_calls_buffer`（L680-682） | `if position is not None and position in self._partials_by_index`（L144-148） | ✓ |

**证据**：

- OLD: `sse_parser.py:659-687`（`_resolve_tool_call_index`）
- NEW: `tool_call_aggregator.py:114-149`（`_resolve_index`）
- OLD: `sse_parser.py:689-829`（`_handle_tool_call_delta`）
- NEW: `tool_call_aggregator.py:151-204`（`feed`）
- OLD: `sse_parser.py:790-794`（`extra_content` 透传）
- NEW: `tool_call_aggregator.py:198-203`（`extra_content` → `provider_state`）

## 8. Reasoning 协议对照结论

**结论：一致**。

| 协议点 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| 探测入口 | `resolve_reasoning_protocol(payload)` 遍历注册表 | `detect_reasoning_protocol_hook(provider_request)` match | ✓ |
| Gemini 探测 | `_detect_google_thinking` 检查 `extra_body.google.thinking_config.include_thoughts` | `GeminiThinkingExtension(include_thoughts=True)` | ✓ |
| 标签名 | `"thought"` | `"thought"` | ✓ |
| stream 剥离 | `StreamingXMLTagExtractor.process()` + `flush()` | `StreamingXMLTagExtractor.feed()` + `flush()` | ✓ |
| non-stream 剥离 | `extract_full(text, tag_name)` | `_split_thought(content, hook=hook)` | ✓ |
| start_only 安全锁 | 默认 `True`，标签外非空白正文 → 永久失活 | 默认 `True`，标签外非空白正文 → 永久失活 | ✓ |
| reasoning 合并顺序 | `extracted_reasoning + native_reasoning`（L1663） | `inside + (reasoning or "")`（L195） | ✓ |
| 非 Gemini | `tag_name=None`，不做剥离 | `tag_name=None`，不做剥离 | ✓ |

**证据**：

- OLD: `reasoning_protocol.py:54-83`（`_detect_google_thinking`）
- NEW: `reasoning_protocol.py:34-61`（`detect_reasoning_protocol_hook`）
- OLD: `xml_extractor.py:19-138`（`StreamingXMLTagExtractor`）
- NEW: `xml_tag_extractor.py:50-209`（`StreamingXMLTagExtractor`）
- OLD: `async_openai_runner.py:1651-1663`（non-stream reasoning 合并）
- NEW: `non_stream_parser.py:188-195`（non-stream reasoning 合并）

## 9. Non-stream 路径对照结论

**结论：一致**。

| 协议点 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| Content-Type 检测 | `"application/json" in content_type` | `options.stream and _SSE_CONTENT_TYPE_FRAGMENT in content_type` 取反 | ✓ |
| choices 缺失 | `error_event("No choices in response")` | `RunnerProtocolErrorData(non_stream_missing_choices)` + `RunnerDoneData(ERROR)` | ✓ |
| message 解析 | `first_choice.get("message", {})` | `choice.get("message")` | ✓ |
| content | `raw_content` or `""` | `raw_content` if str | ✓ |
| reasoning_content | `message.get("reasoning_content") or ""` | `message.get("reasoning_content")` if str | ✓ |
| `<thought>` 剥离 | `extract_full(raw_content, tag_name)` | `_split_thought(content, hook=hook)` | ✓ |
| reasoning 合并 | `extracted_reasoning + native_reasoning` | `inside + (reasoning or "")` | ✓ |
| tool_calls 校验 | 完整校验（id/name/args type/JSON） | `ToolCallAggregator` 复用 + `_coerce_final_tool_call` | ✓ |
| `extra_content` | `tc.get("extra_content")` → `item["extra_content"]` | `extra_content` → `provider_state` via aggregator | ✓ |
| usage | `result.get("usage")` → 事件 | `parsed.get("usage")` → `RunnerUsageRecordedData` | ✓ |
| finish_reason | `stream_state["finish_reason"]` | `_resolve_finish_reason(choice)` | ✓ |

**证据**：

- OLD: `async_openai_runner.py:1594-1793`（`_process_non_stream`）
- NEW: `non_stream_parser.py:75-239`（`parse_non_stream_response`）

## 10. HTTP / retry / error 对照结论

**结论：一致（NEW 有合理改进）**。

| 协议点 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| 429 分类 | `RETRIABLE_STATUS_CODES` | `RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED` | ✓ |
| 5xx 分类 | `RETRIABLE_STATUS_CODES` {500,502,503,504} | `RunnerHTTPErrorCode.SERVER_ERROR` | ✓ |
| 4xx 分类 | `NON_RETRIABLE_STATUS_CODES` {400,401,403,404} | `RunnerHTTPErrorCode.CLIENT_ERROR` | ✓ |
| 1xx/3xx | `error_type="unknown_http_status"` | `RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS` | ✓ |
| timeout | `asyncio.TimeoutError` → 重试 | `RunnerHTTPErrorCode.TIMEOUT` → 重试 | ✓ |
| network | `aiohttp.ClientError` → 重试 | `RunnerHTTPErrorCode.NETWORK_ERROR` → 重试 | ✓ |
| Retry-After | 直接使用 header 值 | `parse_retry_after` + 429 cap 120s | ✓ 合理改进 |
| backoff | `2 ** attempt`（无 cap） | 429: 首次 4s cap 60s; 其它: `2^(attempt-1)` cap 30s | ✓ 合理改进 |
| 重试耗尽 | `error_event` + `return` | `RunnerHTTPErrorData` + `RunnerDoneData(ERROR)` | ✓ |
| 不可重试 | `error_event` + `return` | `_AttemptFailedTerminal` → `RunnerHTTPErrorData` + `RunnerDoneData(ERROR)` | ✓ |
| 错误后 done | 无显式 done 事件 | `RunnerDoneData(FinishReason.ERROR)` 收口 | ✓ 有意重设 |

**证据**：

- OLD: `async_openai_runner.py:217-234`（`RETRIABLE_STATUS_CODES` / `NON_RETRIABLE_STATUS_CODES`）
- NEW: `error_classifier.py:29-106`（`classify_http_status` / `is_retriable`）
- OLD: `async_openai_runner.py:1852-1882`（`_calculate_backoff`）
- NEW: `retry_policy.py:57-97`（`compute_retry_decision`）

## 11. Cancellation / close 对照结论

**结论：一致（NEW 有合理重设）**。

| 协议点 | OLD 行为 | NEW 行为 | 一致性 |
|---|---|---|---|
| 取消异常 | `EngineCancelledError`（公共） | `_RunnerInterrupted`（私有） | ✓ 有意重设 |
| 取消检查 | `_raise_if_cancelled()` 轮询 | `await_or_cancel` 竞速（50ms 轮询） | ✓ |
| 取消 before request | `raise EngineCancelledError` | `raise _RunnerInterrupted` | ✓ |
| 取消 during stream | `raise EngineCancelledError` | `raise _RunnerInterrupted` | ✓ |
| 取消后 done | 无 done 事件 | 无 done 事件（生成器自然终止） | ✓ |
| close 幂等 | `session is None` / `session.closed` 检查 | `HTTPClient.close()` 幂等 | ✓ |
| 脏 session | 废弃 + 重建 | 不适用（每次 call 新建 session） | ✓ 合理简化 |

**证据**：

- OLD: `async_openai_runner.py:607-611`（`_raise_if_cancelled`）
- NEW: `cancellation_helpers.py:72-113`（`await_or_cancel`）
- OLD: `async_openai_runner.py:633-642`（`close`）
- NEW: `runner.py:152-158`（`close`）

## 12. 事件流与状态机对照结论

**结论：一致**。

| 事件事实 | OLD 表达 | NEW 表达 | 映射 |
|---|---|---|---|
| content delta | `content_delta(delta)` | `RunnerContentDeltaData(delta)` | ✓ |
| reasoning delta | `reasoning_delta(delta)` | `RunnerReasoningDeltaData(delta)` | ✓ |
| tool call delta | `tool_call_delta(tool_call_id, name, arguments_delta)` | `RunnerToolCallDeltaData(tool_call_index, tool_call_id, name_delta, arguments_delta)` | ✓ |
| tool calls completed | `tool_calls_batch_done(...)` | `RunnerToolCallsCompletedData(tool_calls)` | ✓ 有意重设：Runner 不执行工具 |
| content completed | `content_complete(content, reasoning_content=...)` | `RunnerContentCompletedData(content, reasoning_content, finish_reason)` | ✓ |
| usage | `metadata_event("token_usage_summary", ...)` | `RunnerUsageRecordedData(prompt_tokens, completion_tokens, total_tokens)` | ✓ |
| protocol error | `error_event(message, error_type=..., body=...)` | `RunnerProtocolErrorData(error_code, message, ...)` | ✓ |
| HTTP error | `error_event(message, error_type=..., status=...)` | `RunnerHTTPErrorData(error_code, http_status, ...)` | ✓ 有意重设 |
| done | `done_event(summary=...)` | `RunnerDoneData(finish_reason)` | ✓ |
| stream/non-stream 终态 | 一致（均以 done 收口） | 一致（均以 `RunnerDoneData` 收口） | ✓ |
| Runner 范围 | 包含工具执行事件 | 不包含工具执行事件 | ✓ 有意重设 |

Runner 只表达单次模型调用状态机，不迁入 Agent 多轮 loop，不执行工具，不产出 `final_answer` / `EngineEvent` / Host 可见 run 终态。✓

## 13. 架构边界对照结论

**结论：通过**。

| 边界检查 | 结果 |
|---|---|
| NEW Runner 不 import Host / Service / UI / fins / trace | ✓ AST 边界测试通过 |
| NEW Runner 不依赖 ToolExecutor / ToolRegistry | ✓ `test_no_tool_executor_dep.py` 通过 |
| `AsyncOpenAIRunner` 不从 `dayu.engine` 根包导出 | ✓ `from dayu.engine import AsyncOpenAIRunner` → ImportError |
| Engine 语义真源契约在 `dayu.engine.contracts` | ✓ |
| 双方协作协议在 `dayu.contracts` | ✓ |
| `aiohttp` 仅在 `dayu/engine/runners/openai/` 子树 | ✓ |

## 14. 阻塞问题

无。

## 15. 重要问题

无。

## 16. 建议问题

### 16.1 OLD stream idle heartbeat 未迁移

- **NEW 文件**：`dayu/engine/runners/openai/sse_parser.py`
- **OLD 证据**：`sse_parser.py:395-398`（`_get_stream_idle_heartbeat_sec`）+ `sse_parser.py:250-291`（idle timeout + heartbeat 日志）
- **触发场景**：SSE 流长时间无 chunk 到达
- **实际行为**：NEW 无 idle timeout 检测，SSE 流静默等待直到连接超时
- **预期协议语义**：OLD 在 `stream_idle_timeout` 秒后记录 heartbeat 日志，帮助运维排查卡住的流
- **影响**：不影响协议正确性；生产环境卡流时缺少可观测信号
- **建议修复方向**：Phase 2 可在 `SSEParser` 或 Runner 层补充 idle timeout + 日志；当前 Phase 1 不阻塞

### 16.2 OLD context overflow 检测未迁移

- **NEW 文件**：`dayu/engine/runners/openai/runner.py`
- **OLD 证据**：`async_openai_runner.py:306-340`（`_detect_context_overflow`）
- **触发场景**：模型返回 400 + `context_length_exceeded` / `maximum_context_length` 等错误体
- **实际行为**：NEW 归类为 `CLIENT_ERROR`（不可重试），不区分 context overflow
- **预期协议语义**：OLD 把 context overflow 作为特殊 `error_type` 产出，供 Agent 做上下文压缩决策
- **影响**：Phase 1 无 Agent loop，不影响当前验收；Phase 2 Agent 需要该信号时再补充
- **建议修复方向**：Phase 2 Agent 实现时在 error_classifier 或 Runner 层补充 context overflow 检测

### 16.3 OLD `n>1` 覆盖未迁移

- **NEW 文件**：`dayu/engine/runners/openai/payload.py`
- **OLD 证据**：`async_openai_runner.py:1072-1079`（`n` 参数强制覆盖为 1）
- **触发场景**：调用方误传 `n>1`
- **实际行为**：NEW 不检查 `n` 参数（`RunnerCallOptions` 不含 `n`）
- **预期协议语义**：OLD 强制覆盖 `n=1` 并警告，因 Runner 只处理 `choices[0]`
- **影响**：`RunnerCallOptions` 不含 `n` 字段，调用方无法误传；NEW 的 `choices` 遍历逻辑处理多 choices
- **建议修复方向**：无需修复；NEW 的类型设计已从源头消除该风险

### 16.4 OLD 脚本 session 清理未迁移

- **NEW 文件**：`dayu/engine/runners/openai/runner.py`
- **OLD 证据**：`async_openai_runner.py:1344-1378`（response cleanup + 脚 session 废弃 + 重建）
- **触发场景**：aiohttp response `__aexit__` 抛异常
- **实际行为**：NEW 用 `finally: response.release()` 简化
- **预期协议语义**：OLD 在 cleanup 失败时废弃当前 session 并重建，防止脏连接池
- **影响**：NEW 每次 `call` 创建新 `HTTPClient`（含新 session），不存在跨 call 脏连接问题
- **建议修复方向**：无需修复；NEW 的 session 生命周期设计已消除该风险

## 17. 测试与 pyright 结果

```text
source .venv/bin/activate && pytest tests/contracts tests/engine -q
200 passed in 0.32s
```

```text
source .venv/bin/activate && pyright
File or directory "/Users/leo/workspace/dayu-agent-r/utils" does not exist.
0 errors, 0 warnings, 0 informations
```

补充核验：

```text
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner  # 成功
from dayu.engine import AsyncOpenAIRunner  # ImportError，符合预期
isinstance(AsyncOpenAIRunner.__new__(AsyncOpenAIRunner), AsyncRunner)  # True
```

测试覆盖矩阵（38 个测试文件）：

| 类别 | 测试文件 | 覆盖点 |
|---|---|---|
| 协议表面 | `test_protocol_surface.py` | isinstance、签名、无 set_tools、无 **kwargs |
| payload 构建 | `test_payload_build.py` | 4 种 extension 投影、provider_request=None、显式参数不进 extra_body |
| assistant reasoning | `test_payload_assistant_reasoning_content_preserved.py` | reasoning_content 非 None 保留 |
| stream usage 门控 | `test_stream_usage_capability_gating.py` | 三种组合 |
| SSE content delta | `test_sse_content_delta.py` | 正文增量 |
| SSE reasoning delta | `test_sse_reasoning_delta.py` | 原生 + `<thought>` 两路 |
| SSE tool call stream | `test_sse_tool_call_stream.py` | 正常聚合 |
| SSE extra_content | `test_sse_tool_call_extra_content_preserved.py` | Gemini thought_signature → provider_state |
| SSE usage | `test_sse_usage_recorded.py` | usage 事件 |
| SSE done | `test_sse_done.py` | 终态 |
| SSE 多行 data | `test_sse_multi_line_data_aggregation.py` | 多行 data 聚合 |
| SSE index fallback | `test_sse_tool_call_index_fallback_to_id.py` | 缺 index 按 id 归属 |
| SSE arguments null | `test_sse_tool_call_arguments_null_ignored.py` | null 安全忽略 |
| SSE invalid UTF-8 | `test_sse_invalid_utf8_chunk.py` | 协议错误 + ERROR 收口 |
| SSE trailing data | `test_sse_trailing_data_no_newline.py` | 尾部残留 |
| SSE empty choices | `test_sse_empty_choices_with_usage.py` | empty choices + usage |
| SSE UTF-8 跨 chunk | `test_sse_utf8_cross_chunk.py` | 多字节跨 chunk |
| non-stream | `test_non_stream_response.py` | JSON 响应归一 |
| non-stream thought | `test_non_stream_thought_strip.py` | Gemini `<thought>` 剥离 |
| protocol error | `test_protocol_error.py` | 坏 JSON / 缺 id / args 非对象 |
| HTTP error event | `test_http_error_event.py` | 429/5xx/4xx/timeout/network/unknown |
| HTTP classification | `test_http_error_classification.py` | 状态码 → 枚举映射 |
| HTTP unknown status | `test_http_unknown_status_runner.py` | 1xx/3xx → UNKNOWN_HTTP_STATUS |
| retry backoff | `test_retry_backoff.py` | Retry-After、指数退避、重试耗尽 |
| cancellation | `test_cancellation_boundaries.py` | 四路阻塞边界 |
| cancellation no done | `test_cancellation_no_done_event.py` | 取消时无 RunnerDoneData |
| close | `test_close_releases_resources.py` | 幂等、二次调用 |
| import boundary | `test_no_tool_executor_dep.py` | 无 ToolExecutor/Host/Service/UI/fins import |
| no extra_payload | `test_no_extra_payload_bag.py` | 无 **kwargs / dict[str, Any] |
| event flow ordering | `test_event_flow_ordering.py` | 事件顺序 |
| stream/non-stream parity | `test_stream_non_stream_terminal_parity.py` | 终态一致性 |
| OLD regressions | `test_old_protocol_parity_regressions.py` | OLD 协议回归 |
| runner event only | `test_runner_only_emits_runner_event.py` | 不产出 EngineEvent |
| runner interrupted | `test_runner_interrupted_private.py` | 私有异常不导出 |
| xml extractor | `test_xml_tag_extractor_start_only.py` | start_only 安全锁 |

## 18. 总体验收判断

**建议进入总控验收**。

Phase 1 Runner 协议一致性 Round 2 已达成：

- payload 构建：显式字段、`stream_options` 门控、`reasoning_content` outbound、Gemini `extra_content` namespace shape、4 种 provider extension 投影均与 OLD 一致或有合理重设。
- SSE 解析：`data:`、`[DONE]`、多行 data、尾部残留、UTF-8 增量解码、非法 UTF-8、empty choices + usage、content/reasoning/tool_call delta、finish reason、usage 全路径覆盖。
- tool call delta 聚合：按 index 聚合、缺 index 按 id 归属、`arguments: null`、并发 tool call、`extra_content` → `provider_state` 全路径覆盖。
- reasoning 协议：Gemini `<thought>` 剥离在 stream 与 non-stream 两条路径均与 OLD 一致；`start_only` 安全锁已恢复。
- non-stream 路径：content、reasoning、tool_calls、usage、finish reason 与 stream 语义对齐。
- HTTP/retry/error：429/4xx/5xx/network/timeout/unknown status 分类正确；backoff 策略有合理改进。
- cancellation/close：私有 `_RunnerInterrupted` 不泄漏；取消路径不补 done；close 幂等。
- 事件流：content delta → reasoning delta → tool call delta → tool calls completed → content completed → usage → protocol/HTTP error → done 映射清晰。
- 架构边界：Runner 不依赖 ToolExecutor / Host / Service / UI / fins / trace；不从 `dayu.engine` 根包导出。
- 测试 200 passed，pyright 0 errors / 0 warnings。
