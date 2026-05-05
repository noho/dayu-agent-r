# Engine Phase 1 实施计划 Review

## 1. Review 结论

通过。

本轮 `docs/engine/phase1-plan.md` 已解决上一轮全部阻塞、重要与建议残留：`AssistantToolCall` 测试归属已回到 Engine contract，Gemini `extra_content` 保持 OLD 证据中的 `{"google": {"thought_signature": ...}}` namespace shape，HTTP error code 已统一为公共 `RunnerHTTPErrorCode`，`ToolCallProviderState` 已改为封闭 TypeAlias 表述。计划可以进入 Phase 1 代码实施。

## 2. 阅读范围

实际阅读 NEW 文件：

- `docs/engine/phase1-plan.md`
- `docs/engine/phase1-plan-review.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase0-code-review.md`
- `docs/engine/design.md`
- `AGENTS.md`
- `dayu/contracts/tool_call.py`
- `dayu/contracts/json_value.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/finish_reason.py`

实际阅读 OLD Runner / Agent 强参考源：

- `~/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `~/workspace/dayu-agent/dayu/engine/sse_parser.py`
- `~/workspace/dayu-agent/dayu/engine/reasoning_protocol.py`
- `~/workspace/dayu-agent/dayu/engine/xml_extractor.py`
- `~/workspace/dayu-agent/dayu/engine/README.md`
- `~/workspace/dayu-agent/dayu/config/llm_models.json`
- `~/workspace/dayu-agent/tests/engine/test_sse_parser.py`
- `~/workspace/dayu-agent/tests/engine/test_async_agent.py`

## 3. OLD Runner 强参考对照结论

- payload 构建：已覆盖模型、消息、显式调用参数、tools schema、provider extension 投影、`supports_stream_usage` 门控、assistant `reasoning_content` outbound 保留。
- SSE 解析：已覆盖 `data:`、`[DONE]`、多行 data、缺失 tool call `index` 按 id 归属、`arguments: null`、尾部残留 data、empty choices + usage；非法 UTF-8 已修正为协议错误终态。
- reasoning 处理：Gemini `extra_body.google.thinking_config.include_thoughts` → `<thought>` 剥离路径与 OLD 一致。
- tool call delta：已通过 `ToolCallProviderState` 承载 Gemini continuation state，并保留 `extra_content.google.thought_signature` 的 provider namespace shape。
- usage：`supports_stream_usage` 已加入 `RunnerSpec`，门控规则与 OLD 一致。
- HTTP 错误分类：已新增公共 `RunnerHTTPErrorCode` + `RunnerHTTPErrorData`，HTTP / network / timeout 错误可进入 RunnerEvent 流。
- retry/backoff：计划覆盖 `Retry-After`、429 capped backoff、普通 5xx capped backoff 与 `max_retries`。
- cancellation：已明确取消是 `RunnerDoneData` 默认终态的唯一例外，Phase 2 Agent 以 `token.is_cancelled() + 无 RunnerDoneData` 双条件提升为取消终态。
- close：计划覆盖 `ClientSession` 幂等关闭；脏 session 废弃可作为实现阶段补充测试。

## 4. 阻塞问题

无。

## 5. 重要问题

无。

## 6. 建议问题

无必须修改项。

## 7. Runner 边界专项结论

- Runner 是否只产出 `RunnerEvent`：是。成功、协议错误、HTTP 错误、取消例外都在 RunnerEvent 或无事件终止边界内表达。
- 是否仍禁止工具执行：是。OLD `_emit_tool_batch` / `_run_tool_call` / `set_tools` 未迁移。
- 是否仍禁止 ToolExecutor / ToolRegistry：是。
- 是否仍禁止 `set_tools` / `**extra_payloads`：是。
- 是否仍禁止 Host / trace / fins 依赖：是。
- 是否应导出 `AsyncOpenAIRunner`：不应从 `dayu.engine.__all__` 导出；计划已锁定不导出。

## 8. 取消边界专项结论

- `_RunnerInterrupted` 是否可接受：可接受，私有、不导出、不进入公共 `:raises:`。
- 取消后“自然终止”是否会造成歧义：当前计划已用 `token.is_cancelled()` 双条件消除歧义。
- 是否需要修改计划，明确 Runner 与后续 Agent 的取消交接方式：已明确。Phase 2 仍需按该规则补 Agent 收口测试。
- 与 OLD cancellation 阻塞边界是否一致或有合理重设：一致且合理；取消异常从 OLD 公共异常改为 Runner 私有控制流，符合 NEW contract 边界。

## 9. 类型与 provider adapter 专项结论

- `_types.py` 是否会成为弱类型袋：当前风险可接受；计划继续禁止 `Any` / `object` / 裸 dict，并限制 `_types.py` 为私有 adapter。
- provider extension 投影是否过早：新版计划已用 OLD `llm_models.json` 直接证据修正 Anthropic / Qwen 顶层投影，可接受。
- `JsonValue` 使用是否合理：用于 `raw_payload` 与工具 arguments 合理；provider continuation state 已改为 `ToolCallProviderState`，方向正确。
- 是否存在 `Any` / `object` 风险：主要集中在 aiohttp fake、JSON decode、TypedDict cast；计划已安排 weak typing guard 和 pyright。

## 10. OLD Runner / Agent 事件流与状态机专项结论

- OLD README 明确区分 Runner 事件与 Agent 事件：`done` 只表示当前 Runner 回合结束，`final_answer` 只由 `AsyncAgent` 产出。Phase 1 计划保持 Runner 只产出 `RunnerEvent` / `RunnerDoneData`，不产出 `final_answer` 或 run 终态，符合该分层。
- OLD README 的 Agent 状态机是 `PrepareIteration -> CallRunner -> HandleToolBatch / ContinueAnswer / Finalize -> PrepareNextIteration`。Phase 1 只迁 `CallRunner` 内 provider 协议归一，不迁 `HandleToolBatch`、continuation、filtered final answer、压缩与降级，边界正确。
- OLD Runner 的 provider 协议流已落实到 NEW RunnerEvent：content delta、reasoning delta、tool call delta、tool calls completed、content completed、usage、protocol error、HTTP error、done。
- OLD Runner 的工具执行事件（`tool_call_dispatched` / `tool_call_result` / `tool_calls_batch_done`）没有被迁入 Runner，符合 NEW 边界；工具执行仍留给后续 Agent + Host ToolExecutor。
- OLD Agent 中 assistant `reasoning_content` 保留与 Gemini `extra_content` roundtrip 的关键协议事实已进入 contract / payload 计划，足以支撑 Phase 2 Agent 恢复 tool loop 状态机。
- Phase 1 不实现 Agent loop 是正确边界；真正端到端“模型请求工具 → Agent 调 ToolExecutor → assistant/tool messages 回填下一轮”的状态机必须在 Phase 2 继续以 OLD README §5 与 OLD Agent 测试作强参考。

## 11. 可接受风险

- Phase 0 contract 补丁并入 Phase 1 可以接受，前提是先实施 contract 补丁并先跑 contract tests + pyright，不通过就停止。
- 新增 `RunnerHTTPErrorData` / `RunnerHTTPErrorCode` 是合理扩展。
- `supports_stream_usage` 加入 `RunnerSpec` 是合理 capability 补丁。
- `ToolCallProviderState` 当前仅含 Gemini state 可以接受；后续新增 provider state 必须回 contract 评审。
- 多模块拆分与 `aiohttp` 放开可以接受。

## 12. 需要总控 / 用户确认的问题

无必须阻塞实施的问题。

## 13. 总体验收判断

- 是否允许基于当前 `docs/engine/phase1-plan.md` 开始 Phase 1 实施？允许。
- 如果不允许，需要先修哪些章节？不适用。
- 如果允许，Phase 1 最小实施范围是什么？先落 Phase 0 contract 补丁及同步测试，再实现不导出包根的 OpenAI-compatible Runner，覆盖 payload、SSE / non-stream、reasoning、tool call provider_state、usage、HTTP 错误事件、retry/backoff、取消边界和 close。
