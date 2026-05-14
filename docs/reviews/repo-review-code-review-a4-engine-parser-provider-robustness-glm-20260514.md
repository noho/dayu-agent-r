# Code Review

## Scope

- Mode: current changes
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-review-a4-engine-parser-provider-robustness-glm-20260514.md`
- Source adjudication: `docs/reviews/repo-review-controller-adjudication-20260514.md` A4
- Implementation artifact: `docs/reviews/repo-review-fix-a4-engine-parser-provider-robustness-20260514.md`
- Included files:
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
- Excluded scope: malformed usage downgrade, GeminiToolCallState/public provider-state redesign, runner factory/provider injection, config json findings, A5/A6/A8/A9
- Parallel review coverage: 无；全部文件由主 reviewer 逐行走读

## Findings

未发现实质性问题。

逐项核对 accepted A4 项：

### 1. terminal constant reuse — 正确

`run_agent_and_wait`（agent.py:2438）将原来手写的四事件集合替换为 `TERMINAL_ENGINE_EVENT_TYPES`。该常量定义于 `engine_events.py:451-458`，恰好包含 `FINAL_ANSWER / RUN_FAILED / RUN_CANCELLED / RUN_SUSPENDED` 四项，与替换前语义完全等价。`agent.py:2261` 处 `_is_terminal_event` 已使用同一常量，消除了终态集合漂移风险。

### 2. assert_never guards — 正确

共 7 处新增 `assert_never`：

| 文件 | 函数 | 守护联合 |
|---|---|---|
| payload.py:97 | `_serialize_provider_state` | `ToolCallProviderState` |
| payload.py:163 | `_serialize_message` | `AgentMessage` |
| payload.py:253-254 | `_apply_provider_request` | `ProviderRequestExtension` |
| payload.py:288 | `_reasoning_effort_value` | `OpenAIReasoningEffort` |
| payload.py:304 | `_deepseek_reasoning_effort_value` | `DeepSeekReasoningEffort` |
| payload.py:324 | `_gemini_thinking_level_value` | `GeminiThinkingLevel` |
| reasoning_protocol.py:68-69 | `detect_reasoning_protocol_hook` | `ProviderRequestExtension` |

所有守护均位于封闭联合 `match` 的穷尽检查位置。`_apply_provider_request` 和 `detect_reasoning_protocol_hook` 使用 `case _: assert_never(...)` 模式，因为 match 使用字段提取模式；其余函数在 match 块外使用 `assert_never`，两种写法均符合 Python exhaustiveness checking 惯例。pyright 0 errors 验证了静态穷尽性。

### 3. 5xx context overflow detection — 正确

`detect_context_overflow`（error_classifier.py:109）将 `http_status >= 500` 改为 `http_status >= 600`，使 5xx 响应体中的 context overflow marker 可被检测。

- 边界正确：`< 400` 和 `>= 600` 仍返回 `False`；400–599 全部进入 marker 检测路径。
- 结构化 `error.code` 优先于 message marker fallback，5xx 响应体中若含 `context_length_exceeded` code 会被正确识别。
- marker 矩阵（`_CONTEXT_OVERFLOW_MESSAGE_MARKERS`）均为高特异性短语，5xx 误触发概率极低。
- 测试 `test_detect_context_overflow_accepts_bounded_5xx_body_marker` 验证了 500 + marker 的正向场景。

### 4. ClientPayloadError doc alignment — 正确

模块 docstring（error_classifier.py:17-18）将 `ClientPayloadError` 从 `TIMEOUT` 组移至 `NETWORK_ERROR` 组。实现中 `classify_exception` 的 `isinstance(exc, aiohttp.ClientError)` 分支已正确将 `ClientPayloadError` 归为 `NETWORK_ERROR`（它是 `ClientError` 的子类但不是 `ClientConnectionError` 或 `ServerTimeoutError` 的子类）。测试 `test_classify_exception_client_payload_error_is_network_error` 明确验证了运行时行为。

### 5. top-level json import — 正确

`payload.py:27` 将 `_serialize_arguments` 内的 lazy `import json` 移到模块顶部。`json` 是标准库，启动开销可忽略。原 lazy import 无必要。

### 6. diagnostic truncation marker preserving max length — 正确

`_exception_diagnostic_message`（agent.py:220-228）实现：

```python
max_body_length = _EXCEPTION_MESSAGE_MAX_LENGTH - len(_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX)
raw_message = raw_message[:max_body_length] + _EXCEPTION_MESSAGE_TRUNCATED_SUFFIX
```

- `_EXCEPTION_MESSAGE_MAX_LENGTH = 240`，`_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX = "... [truncated]"`（16 字符）
- `max_body_length = 224`，截断后 body = 224 + 16 = 240，不超过 `_EXCEPTION_MESSAGE_MAX_LENGTH`。
- 边界：消息长度 == 240 时不触发截断；== 241 时截断为 240；测试断言 `len(message.removeprefix("RuntimeError: ")) == 240`，验证了不变量。
- controller self-review 已纠正首版"先截后追加"的错误为"先预留 marker 长度再截断"，确保 body 不超限。

### 7. SSE non-dict choice diagnostic — 正确

`sse_parser.py:310-318` 在 `_handle_chunk_object` 中对 `choices` 内非 dict 成员记录 `sse.protocol_diagnostic code=sse_choice_not_object` 诊断日志并 `continue`，协议行为与原静默跳过一致。日志包含 `index` 和 `type` 信息，便于排查。测试 `test_sse_non_object_choice_logs_diagnostic` 验证了日志产出且 parser 仍正常完成。

### 8. non_stream fatal_emitted cleanup — 正确

`non_stream_parser.py:235` 删除 `fatal_emitted = False` 及后续条件 `and not fatal_emitted`。该变量在函数内从未被设为 `True`：fatal error 路径在 `yield Done(ERROR)` 后 `return`，不会到达 `if not tool_calls_emitted` 分支。删除后行为不变。

### 9. Chinese docstring completeness — 正确

所有触及的 helper / dataclass / match 函数均已补齐 `:param` / `:returns` / `:raises` 中文 docstring：

- `sse_parser.py`: `_make_event`, `_event_type_for`, `_handle_chunk_object`
- `non_stream_parser.py`: `_make_event`, `_emit_from_dict`, `_resolve_finish_reason`, `_NonStreamToolCallsResult`, `_build_tool_calls`, `_coerce_final_tool_call`
- `payload.py`: `_serialize_arguments`, `_serialize_provider_state`, `_serialize_message`, `_apply_provider_request`, `_reasoning_effort_value`, `_deepseek_reasoning_effort_value`, `_gemini_thinking_level_value`
- `reasoning_protocol.py`: `detect_reasoning_protocol_hook`

注意：`non_stream_parser._make_event` 的 `:raises KeyError` 与 `sse_parser._make_event` 的 `:raises AssertionError` 不同，这是因为前者用 `type_map[type(data)]` 查表、后者用 `match + case _` 模式，各自的异常类型描述与实现一致。

### 10. tests — 充分

- 新增 4 个测试：`test_detect_context_overflow_accepts_bounded_5xx_body_marker`、`test_classify_exception_client_payload_error_is_network_error`、`test_sse_non_object_choice_logs_diagnostic`、`test_exception_diagnostic_message_marks_truncation`。
- 各测试断言覆盖正向行为和关键不变量（截断标记存在 + body 长度 == MAX_LENGTH、分类枚举正确、日志消息包含 diagnostic code）。
- 全量 64 tests passed，OpenAI runner 套件 187 tests passed。

### 11. pyright — 通过

`pyright dayu/engine tests/engine` → 0 errors, 0 warnings, 0 informations。

## Open Questions

- 无

## Residual Risk

- 5xx context overflow 识别仍依赖 runner 已读取的错误体文本；本轮未修改 `runner.py` 的错误体读取策略（A4 artifact 已记录）。
- SSE 非 dict choice 仍保持旧行为：记录诊断并跳过，不升级为协议错误（A4 artifact 已记录）。

## Verdict

**Pass — A4 accepted items 全部通过，未发现实质性问题。**

A4 裁决中 9 项 accepted 实现逐行走读均正确：

1. terminal constant reuse — 语义等价
2. assert_never guards — 7 处穷尽守护位置正确，pyright 0 errors 验证静态穷尽性
3. 5xx context overflow detection — 边界 `>= 600` 正确，marker 高特异性
4. ClientPayloadError doc alignment — doc 与实现一致
5. top-level json import — 标准库无启动开销
6. diagnostic truncation marker preserving max length — 不变量 `body ≤ 240` 测试验证
7. SSE non-dict choice diagnostic — 仅日志，协议行为不变
8. non_stream fatal_emitted cleanup — 死变量，删除后行为不变
9. Chinese docstring completeness — 所有触及 helper 补齐

验证结果：64 tests passed，OpenAI runner 套件 187 tests passed，pyright 0 errors，`git diff --check` 通过。无 blocking finding，可进入下一阶段。
