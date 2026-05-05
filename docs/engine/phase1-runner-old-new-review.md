# Engine Phase 1 Runner OLD/NEW 协议一致性专项 Review

## 1. Review 结论

通过。

本轮复审确认上一轮“不通过”清单中的关键问题已经收口：SSE pos fallback continuation 已按 OLD 语义迁移，后续缺 `id/index` 的 arguments 帧能按数组位置归位到既有 tool call partial；新增 regression 测试不再使用 `object` 返回类型或 `# type: ignore[arg-type]` 绕过类型边界。

当前未发现阻塞或重要问题。仍保留一个资源清理策略的建议项，可在后续实现中继续加强。

## 2. 阅读范围

实际阅读 NEW：

- `AGENTS.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase1-plan.md`
- `docs/engine/phase1-plan-review.md`
- `docs/engine/phase1-code-review.md`
- `docs/code_review.md`
- `dayu/contracts/tool_call.py`
- `dayu/engine/contracts/*`
- `dayu/engine/runners/openai/*`
- `tests/contracts/*`
- `tests/engine/contracts/*`
- `tests/engine/runners/openai/*`

实际阅读 OLD 强参考源：

- `~/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `~/workspace/dayu-agent/dayu/engine/sse_parser.py`
- `~/workspace/dayu-agent/dayu/engine/reasoning_protocol.py`
- `~/workspace/dayu-agent/dayu/engine/xml_extractor.py`
- `~/workspace/dayu-agent/dayu/engine/README.md`
- `~/workspace/dayu-agent/dayu/config/llm_models.json`
- `~/workspace/dayu-agent/tests/engine/test_sse_parser.py`
- `~/workspace/dayu-agent/tests/engine/test_async_agent.py`

## 3. OLD Runner 关键协议事实摘要

- Payload：OLD 保留 `messages` 中的 `reasoning_content` 和 assistant `tool_calls.extra_content`，`stream_options.include_usage` 受 `supports_stream_usage` 门控。
- SSE：OLD 支持 `data:`、`[DONE]`、多行 data、尾部无换行 data、跨 chunk UTF-8、empty choices + usage、content / reasoning / tool call delta。
- Tool call：OLD 对缺失 `index` 的 Gemini 兼容模式会先补齐 index 再处理 delta；有 `id` 时按 id 归属；没有 `id` 但数组位置 `pos` 已存在 partial 时按 `pos` 归位；`arguments: null` 安全忽略；non-stream `arguments` 允许 dict 或 JSON string。
- Reasoning：OLD non-stream 合并顺序明确为 `extracted_reasoning + native_reasoning`，以对齐 SSE 路径。
- HTTP / retry：OLD `RETRIABLE_STATUS_CODES` 包含 `408/429/500/502/503/504`；429 无 `Retry-After` 首退避 4s、cap 60s；429 `Retry-After` cap 120s。
- Cancellation / close：OLD 在 HTTP 建连、响应读取、SSE chunk、retry sleep 边界观察取消；response context 使用 `post_context.__aexit__` 收口。
- 事件流 / 状态机：OLD README 区分 Runner 事件与 Agent 事件，`done` 只表示单次 Runner 回合结束，`final_answer` 只由 Agent 产出。

## 4. NEW Runner 实现映射摘要

- Payload builder 已覆盖 system / user / assistant / tool 消息、tools schema、显式 options、provider extension、`supports_stream_usage`、assistant `reasoning_content` 和 Gemini provider_state outbound。
- SSE parser 已覆盖主要 content / reasoning / usage / done / fatal protocol error 路径，合法跨 chunk UTF-8 与非法 UTF-8 都有测试。
- ToolCallAggregator 现在同时覆盖缺 `index` 但有 `id` 的归属，以及后续缺 `id/index` arguments 帧按 `position` 归位的 OLD pos fallback continuation。
- Non-stream parser 已覆盖 dict arguments、非法 list arguments、非法 string JSON 和 reasoning 合并顺序。
- HTTP classifier / retry policy 已覆盖 408、429 专用 backoff 和 `Retry-After` cap。

## 5. Payload 构建对照结论

通过。未发现 `**extra_payloads` 回流；`reasoning_content`、tools schema、Gemini `extra_content.google.thought_signature` outbound shape 均符合 OLD 协议事实与 NEW contract。

## 6. SSE 解析对照结论

通过。本轮已补齐 OLD `test_sse_parser_pos_fallback_continuation` 对应语义：`SSEParser` 使用 `enumerate(tool_calls_delta)` 将数组位置传给 aggregator，aggregator 在缺 `id/index` 且该 `position` 已有 partial 时归位，不再丢弃后续 arguments。

## 7. Tool call delta 聚合对照结论

通过。缺 `index` 但有 `id` 的并行 tool call delta 能稳定分配不同 index；首帧有 `id/name`、后续帧仅有 arguments 的场景能拼出完整参数；无法归属的 delta 仍会产生 `tool_call_missing_index_and_id` warning。

## 8. Reasoning 协议对照结论

通过。NEW `reasoning_protocol.py` 与 OLD 一致，只在 Gemini `include_thoughts=True` 时启用 `<thought>` 剥离；non-stream 合并顺序为 `inside + native_reasoning`，已有 parity 测试覆盖 native `reasoning_content` 与 `<thought>` 同时存在的场景。

## 9. Non-stream 路径对照结论

通过。dict 形态 `function.arguments` 已序列化后进入 aggregator，list / 非 object arguments 会触发 fatal 协议错误，非法 JSON string 也有回归测试。

## 10. HTTP / retry / error 对照结论

通过。HTTP 408 归为 `RunnerHTTPErrorCode.TIMEOUT` 且可重试；429 无 header 首次 4s、cap 60s，429 `Retry-After` cap 120s，均有测试覆盖。HTTP / network / timeout 错误使用 NEW 的 `RunnerHTTPErrorData` 表达，这是合理架构重设。

## 11. Cancellation / close 对照结论

取消边界通过。`_RunnerInterrupted` 仍为私有控制流，未进入公共契约；取消路径不产出伪 done / error。

close 资源收口保留建议风险：NEW 仍是手动 `__aenter__` 后 `response.release()`，没有完全对齐 OLD 的 `post_context.__aexit__` + cleanup 失败作废 session 策略。当前未作为阻塞，因为已有 close / cancellation 主路径测试通过。

## 12. 事件流与状态机对照结论

通过。Runner 仍只表达单次模型调用状态机，不产出 `EngineEvent` / `final_answer` / run 终态。SSE pos fallback 修复后，tool call 参数续帧不再产生“warning + 成功空参数”的歧义事件流。

## 13. 架构边界对照结论

通过。未发现 Runner 导入 Host / Service / UI / fins / trace / ToolExecutor / ToolRegistry。`AsyncOpenAIRunner` 只在 `dayu.engine.runners.openai.runner` 子模块导出，未进入 `dayu.engine` 根包。未发现 `set_tools`、`call(**extra_payloads)`、兼容 wrapper / facade / re-export。

## 14. 阻塞问题

无。

## 15. 重要问题

无。

## 16. 建议问题

### 16.1 response context 收口仍未完全对齐 OLD 的 `__aexit__` / 脏 session 废弃策略

- 严重程度：建议
- NEW 文件：`dayu/engine/runners/openai/runner.py:236-292`
- OLD 证据：`~/workspace/dayu-agent/dayu/engine/async_openai_runner.py:1344-1378`
- 问题说明：NEW 手动进入 request context 后主要依靠 `response.release()`，未完全覆盖 OLD 的 `post_context.__aexit__` 与 cleanup 失败后作废 session 策略。
- 建议修复方向：后续补 fake context cleanup 失败测试；若 aiohttp 语义需要，保存 `response_ctx` 并在 finally 中调用 `__aexit__`，失败时关闭并清空 `HTTPClient` 内 session。

## 17. 测试与 pyright 结果

已运行：

```text
source .venv/bin/activate && pytest tests/contracts tests/engine -q
200 passed in 0.34s
```

已运行：

```text
source .venv/bin/activate && pyright
File or directory "/Users/leo/workspace/dayu-agent-r/utils" does not exist.
0 errors, 0 warnings, 0 informations
```

补充核验：

- `tests/engine/runners/openai/test_old_protocol_parity_regressions.py` 已移除 `_make_default_hook() -> object` 与 `# type: ignore[arg-type]`。
- 新增 `test_sse_pos_fallback_continuation_arguments_attached` 覆盖 OLD 等价场景，断言不产生 `tool_call_missing_index_and_id`，最终 `arguments == {"a": 1}`。
- `git status --short` 未显示 `__pycache__` 被纳入提交范围。

## 18. 总体验收判断

建议进入总控验收。

Phase 1 Runner 当前在 OpenAI-compatible 协议语义、SSE tool call 聚合、reasoning、non-stream、HTTP retry、取消边界与架构边界上均已达到本轮 OLD/NEW 协议一致性 review 的验收要求。后续可继续加强 response context cleanup 的异常路径测试，但不阻塞本阶段验收。
