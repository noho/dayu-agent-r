# Code Review

## Scope

- Mode: current changes (scoped A4 work unit)
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-review-a4-engine-parser-provider-robustness-mimo-20260514.md`
- Included scope:
  - `dayu/engine/agent.py`
  - `dayu/engine/runners/openai/payload.py`
  - `dayu/engine/runners/openai/reasoning_protocol.py`
  - `dayu/engine/runners/openai/error_classifier.py`
  - `dayu/engine/runners/openai/sse_parser.py`
  - `dayu/engine/runners/openai/non_stream_parser.py`
  - `tests/engine/test_agent_phase2.py`
  - `tests/engine/runners/openai/test_context_overflow_classifier.py`
  - `tests/engine/runners/openai/test_http_error_classification.py`
  - `tests/engine/runners/openai/test_protocol_error.py`
  - `docs/reviews/repo-review-fix-a4-engine-parser-provider-robustness-20260514.md`
- Excluded scope: A1/A2/A3/A5/A6/A8/A9；malformed usage downgrade；GeminiToolCallState/public provider-state redesign；runner factory/provider injection；config json findings。
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

### 逐项验证

以下按 controller adjudication A4 accepted items 逐项走读，确认实现正确性。

#### 1. 终态常量复用

- **入口**: `run_agent_and_wait()` (`agent.py:2435-2438`)
- **变更**: 手写四元素集合替换为 `TERMINAL_ENGINE_EVENT_TYPES`。
- **验证**: `TERMINAL_ENGINE_EVENT_TYPES` 定义于 `engine_events.py:451-458`，包含 `FINAL_ANSWER` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_SUSPENDED`，与原手写集合完全一致。`agent.py:2261` 已有相同复用（pre-existing），两处终态判断语义一致。
- **结论**: ✅ 正确。

#### 2. assert_never 穷尽守护

共 7 处 `match` + `assert_never`，逐一验证：

- **`_serialize_provider_state`** (`payload.py:91-97`): `ToolCallProviderState = GeminiToolCallState`（单一成员联合）；`None` 已在 match 前返回；`assert_never` 在 match 后，pyright 确认类型收敛。✅
- **`_serialize_message`** (`payload.py:132-163`): `AgentMessage = SystemMessage | UserMessage | AssistantMessage | ToolMessage`（四成员）；match 覆盖全部四成员后 `assert_never`。✅
- **`_apply_provider_request`** (`payload.py:208-254`): `ProviderRequestExtension`（六成员联合）；match 覆盖全部六成员 + `case _:` 通配；`None` 已在 match 前返回。✅
- **`_reasoning_effort_value`** (`payload.py:275-288`): `OpenAIReasoningEffort` 六个枚举成员全部覆盖。✅
- **`_deepseek_reasoning_effort_value`** (`payload.py:299-304`): `DeepSeekReasoningEffort` 两个枚举成员全部覆盖。✅
- **`_gemini_thinking_level_value`** (`payload.py:315-324`): `GeminiThinkingLevel` 四个枚举成员全部覆盖。✅
- **`detect_reasoning_protocol_hook`** (`reasoning_protocol.py:55-69`): `ProviderRequestExtension` 六成员 + `case _:` 通配；`None` 已在 match 前返回。✅

#### 3. 5xx context overflow 检测

- **入口**: `detect_context_overflow()` (`error_classifier.py:109`)
- **变更**: 条件从 `http_status >= 500` 改为 `http_status >= 600`。
- **验证**: 修改后 400-599 范围均进入 body 读取和 marker 检测路径。与 `classify_http_status()` 的 5xx → `SERVER_ERROR` 分类互补：runner 侧先分类 HTTP 错误码，再调用 `detect_context_overflow` 判断是否为 context overflow。5xx body 读取安全由调用方保证（`response_text` 已作为参数传入）。
- **测试**: `test_detect_context_overflow_accepts_bounded_5xx_body_marker` 覆盖 http_status=500 场景。✅

#### 4. ClientPayloadError 文档对齐

- **变更**: 模块 docstring 从 "``ClientPayloadError``（超时类）→ TIMEOUT" 改为 "``ClientPayloadError`` / 其它 → NETWORK_ERROR"。
- **验证**: 实现中 `classify_exception()` 的 `isinstance(exc, aiohttp.ClientError)` 分支（第 84 行）将 `ClientPayloadError`（`ClientError` 子类）归为 `NETWORK_ERROR`，与新文档一致。原 docstring 将其归为超时类是错误的。
- **测试**: `test_classify_exception_client_payload_error_is_network_error` 覆盖。✅

#### 5. 顶层 json import

- **变更**: `payload.py` 的 `import json` 从 `_serialize_arguments` 内部移至模块顶部。
- **验证**: `json` 在模块内多处使用（`_serialize_arguments`、`_parse_json_object` 在 `error_classifier.py`），顶层 import 消除不必要 lazy import。符合 CLAUDE.md "禁止胶水 seam，使用 lazy import 必须有充分理由"。✅

#### 6. 截断标记保留 max length

- **入口**: `_exception_diagnostic_message()` (`agent.py:220-228`)
- **变更**: 新增 `_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX = "... [truncated]"`（15 字符）；截断时先计算 `max_body_length = 240 - 15 = 225`，再拼接 suffix。
- **验证**: 最终诊断消息的 body 部分长度 = `len(raw_message[:225]) + len("... [truncated]")` = 225 + 15 = 240 = `_EXCEPTION_MESSAGE_MAX_LENGTH`。长度不变量成立。
- **测试**: `test_exception_diagnostic_message_marks_truncation` 断言 `message.endswith("... [truncated]")` 且 `len(message.removeprefix("RuntimeError: ")) == _EXCEPTION_MESSAGE_MAX_LENGTH`。✅

#### 7. SSE 非 dict choice 诊断

- **入口**: `SSEParser._handle_chunk_object()` (`sse_parser.py:310-318`)
- **变更**: 非 dict choice 时记录 `_LOGGER.warning`，附带 `code=sse_choice_not_object`、index、type。
- **验证**: 协议行为不变（仍 `continue` 跳过），只增加诊断日志。日志级别 `WARNING` 适当：这是协议异常但非 fatal。
- **测试**: `test_sse_non_object_choice_logs_diagnostic` 断言日志存在且后续正常 choice 仍产出 `RUNNER_CONTENT_COMPLETED`。✅

#### 8. non_stream fatal_emitted 清理

- **入口**: `_emit_from_dict()` (`non_stream_parser.py:281`)
- **变更**: 删除 `fatal_emitted = False`；条件从 `not tool_calls_emitted and not fatal_emitted` 简化为 `not tool_calls_emitted`。
- **验证**: `fatal_emitted` 从未被设为 `True`——fatal 路径（第 263-272 行）直接 `yield` 错误事件和 `RunnerDoneData(ERROR)` 后 `return`，不会到达第 281 行。因此 `fatal_emitted` 始终为 `False`，条件简化无行为变化。✅

#### 9. 中文 docstring 完整性

逐文件检查 touched helper 的 docstring：

- **`payload.py`**: `_serialize_arguments`、`_serialize_provider_state`、`_serialize_message`、`_apply_provider_request`、`_reasoning_effort_value`、`_deepseek_reasoning_effort_value`、`_gemini_thinking_level_value` 均有完整 `:param:` / `:returns:` / `:raises:`。✅
- **`reasoning_protocol.py`**: `detect_reasoning_protocol_hook` 有完整 docstring。✅
- **`sse_parser.py`**: `_make_event`、`_event_type_for`、`_handle_chunk_object` 均有完整 docstring。✅
- **`non_stream_parser.py`**: `_make_event`、`_emit_from_dict`、`_resolve_finish_reason`、`_NonStreamToolCallsResult`、`_build_tool_calls`、`_coerce_final_tool_call` 均有完整 docstring。✅

#### 10. 测试

- 64 passed（`test_context_overflow_classifier` 12 + `test_http_error_classification` 11 + `test_protocol_error` 12 + `test_agent_phase2` 29）。
- 新增测试覆盖所有新行为：5xx overflow、ClientPayloadError 分类、截断标记、SSE 非 dict choice 诊断。
- ✅

#### 11. Pyright

- `python -m pyright dayu/engine tests/engine`：0 errors, 0 warnings, 0 informations。
- ✅

## Open Questions

- 无。

## Residual Risk

- 5xx context overflow 识别依赖调用方已读取错误体文本。本轮未修改 runner 的错误体读取策略（`runner.py` 不在 A4 范围内），若 runner 在 5xx 路径未读取 body 或 body 截断过短，overflow marker 可能被漏判。此为 A4 artifact 已记录的已知残余风险。
- SSE 非 dict choice 仍保持旧行为（记录诊断并跳过），不升级为协议错误。这是有意的行为保持，非遗漏。

## Verdict

**通过。** A4 accepted items 全部正确实现，测试覆盖充分，pyright 无新增错误。未发现实质性问题。
