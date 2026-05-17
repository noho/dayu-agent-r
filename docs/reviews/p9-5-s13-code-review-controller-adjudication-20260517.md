# P9.5 S13 Code Review Controller Adjudication

## 范围

- Slice: P9.5 S13 Message / Tool Result Size Governance。
- Design source: `docs/host/design.md`。
- Control doc: `docs/host/implementation-control.md`。
- Implementation artifact: `docs/reviews/p9-5-s13-message-tool-result-size-governance-implementation-20260517.md`。
- Reviews:
  - `docs/reviews/p9-5-s13-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s13-code-review-ds-20260517.md`
  - `docs/reviews/p9-5-s13-code-re-review-ds-20260517.md`

## 裁决原则

本次裁决以 `docs/host/design.md` 的设计目标为准：大消息、大工具结果与大 canonical payload 不得无界进入 LLM / EventLog inline 边界；Host 保持强治理，Engine 只守住自身 Runner 输入边界，不实现 P10 proactive compaction。

## Review 结论

- MiMo: PASS，0 blocking finding。
- DS: PASS，0 blocking finding，提出 O1/O4 等 non-blocking observations。
- Controller: 接受 DS O1/O4 为 S13 内应修复问题，因为二者直接关系到 Engine message inline 边界是否完整与测试是否覆盖真实 run loop。
- DS re-review: PASS，O1/O4 已关闭，0 new blocking finding。

## 已接受并修复

### DS O1: Engine iteration-loop size check 缺少集成测试

裁决：接受。

理由：per-iteration guard 是工具结果注入后、下一轮 Runner 前的真实防线。只测 helper 会低估回归风险。

修复：

- 新增 `tests/engine/test_agent_phase3_tool_call.py::test_oversized_tool_message_fails_before_next_runner_call`。
- 覆盖 oversized tool result 注入 messages 后，下一轮 Runner 调用前以 `context_compaction_required` recoverable failure 收口。

### DS O4: AssistantMessage.tool_calls.arguments 未纳入 inline size guard

裁决：接受。

理由：assistant tool call arguments 会作为下一轮 assistant message 回送 Runner，属于同一 inline message 边界。若只检查 content / reasoning_content，会留下绕过路径。

修复：

- `dayu/engine/agent.py` 新增 `_assistant_tool_call_inline_texts(...)`。
- `_message_inline_texts(...)` 纳入 assistant tool call 的 id、name、arguments JSON 与 Gemini provider_state signature。
- 新增 `tests/engine/test_agent_message_union.py::test_oversized_assistant_tool_call_arguments_require_context_boundary`。

## 不阻塞项

- O2: proactive defensive failure 不 emit `CONTEXT_COMPACTION_REQUESTED`。裁决为不阻塞；S13 不是 P10 proactive compaction，当前直接 `RUN_FAILED(context_compaction_required)` 是防御失败路径。
- O3 / MiMo F1: Engine 与 Host inline 阈值独立定义。裁决为 residual risk；当前避免跨层配置依赖是合理的，P10 可统一预算策略。
- O5 / MiMo F2: oversized `fetch_more` continuation 失败时不清理当前 cursor。裁决为不阻塞；保留 cursor 允许调用方用更小 limit 重试，TTL 会兜底回收。
- O6: ToolRuntime truncation path 与总 outcome path 有双重大小检查。裁决为不阻塞；两处 owner 不同，前者保护 truncation/fetch_more continuation，后者保护所有工具 outcome。
- MiMo F6 关于 composition root 可覆盖 EventLog / ToolRuntime 内部阈值的表述不完全准确；控制器按 implementation artifact 的 residual risk 记录：S13 内部防御阈值当前使用默认 payload inline threshold，未接 per-handle override。

## 验证

- `source .venv/bin/activate && pytest tests/engine/test_agent_message_union.py tests/engine/test_agent_phase3_tool_call.py::test_oversized_tool_message_fails_before_next_runner_call`
  - 9 passed。
- `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_event_log_store.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/engine/test_agent_message_union.py tests/engine/test_agent_phase3_tool_call.py`
  - 115 passed。
- `source .venv/bin/activate && pytest tests/host tests/engine`
  - 913 passed。
- `source .venv/bin/activate && python -m pyright dayu tests`
  - 0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - clean。

## 最终裁决

S13 accepted。当前实现满足 S13 设计目标，未新增 public error taxonomy，未把 Engine reactive overflow 当作 Host proactive context governance，未破坏 Host / Engine 分层。
