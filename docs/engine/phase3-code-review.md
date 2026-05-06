# Phase 3 Code Review

## 结论

通过。

本次复审针对上一轮 3 个 important 问题逐项走读修复路径，并重新运行指定验证。结论：

- 0 blocking。
- 0 important。
- 1 个 suggestion，不阻塞 Phase 3 总控验收。

本次 review 未发现 Engine 反向依赖 Host / Service / UI / fins、Runner 执行工具、ToolRegistry 进入 Engine、metadata 承载显式事实、awaiting / remote / trace / continuation 提前落地、Issue #10 provider-specific reasoning 策略提前实现等边界问题。

## Blocking

无。

## Important

无。

## Suggestion

### 1-已修复-[低]-smoke 摘要曾打印完整 final answer

- **入口/函数**: `safe_event_summary`
- **文件(行号)**: `/Users/leo/workspace/dayu-agent-r/utils/smoke_async_agent_tool_call.py:376`
- **输入场景**: 人工 smoke 真实 provider 返回 final answer。
- **实际分支**: final 事件摘要输出 `content={data.content!r}`。
- **预期行为**: smoke 输出应保持摘要化，优先输出 case、事件类型、sequence、tool name、content_len、final 摘要，避免输出完整 prompt / 财报内容 / 完整 payload。
- **实际行为**: 当前固定 prompt 下风险较低，但脚本会打印完整模型回答；如果后续 smoke prompt 或 provider 输出包含业务片段，会输出不必要正文。
- **直接证据**: `utils/smoke_async_agent_tool_call.py:373-380`。
- **影响**: 人工日志可能泄漏不必要的模型正文。
- **建议改法和验证点**: 只输出 `content_len` 与短截断摘要，或默认不输出正文；同步更新 `tests/engine/test_smoke_async_agent_tool_call.py` 中对 final 摘要的断言。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。
- **修复状态**: 已修复。后续按用户要求 tool-call smoke 需要输出 final answer 正文，因此脚本已改为人工 smoke 明确输出固定 smoke prompt 的 final answer，同时保留 key / payload / 工具参数不泄漏约束；`tests/engine/test_smoke_async_agent_tool_call.py` 已同步覆盖 4 provider、case 空行、final summary 与 final answer 输出。

## 上轮问题复审

### 1. 流式 content_delta 保留：已修复

- **上一轮问题**: tool-call 轮次先收到 `RunnerContentDeltaData`，随后收到 `RunnerToolCallsCompletedData` 与 `RunnerDoneData(TOOL_CALLS)` 时，assistant tool_calls message 的 `content` 会变成 `None`。
- **修复证据**: `_AsyncAgent._classify_iteration` 在 tool-call 分支先读 `state.tool_calls_content`，再回退 `state.completed_content`，最后回退 `"".join(state.content_chunks)`，并将空字符串归一为 `None`。
- **直接位置**: `/Users/leo/workspace/dayu-agent-r/dayu/engine/agent.py:715`。
- **测试证据**: `test_tool_call_iteration_preserves_streamed_content_delta` 覆盖 synthetic Runner 先发 content delta 再发 tool calls，断言第二轮 Runner 输入的 assistant message `content == "先说明"`。
- **直接位置**: `/Users/leo/workspace/dayu-agent-r/tests/engine/test_agent_phase3_tool_call.py:597`。
- **判断**: 修复覆盖原问题。

### 2. non-stream tool_calls reasoning_content roundtrip：已修复

- **上一轮问题**: 非流式 provider 响应同时包含 `tool_calls` 与 `reasoning_content` 时，Runner 没有把 reasoning 暴露给 Agent，导致 assistant tool_calls 写回时丢失 reasoning。
- **修复证据**: `RunnerToolCallsCompletedData` 新增 `content: str | None` 与 `reasoning_content: str | None` 强类型字段；non-stream parser 在 tool_calls 分支把 `content` / `reasoning` 写入该事件；Agent 消费该事件后写入 `_ToolCallsDecision.reasoning_content` 并注入 `AssistantMessage.reasoning_content`。
- **直接位置**:
  - `/Users/leo/workspace/dayu-agent-r/dayu/engine/contracts/runner_events.py:101`
  - `/Users/leo/workspace/dayu-agent-r/dayu/engine/runners/openai/non_stream_parser.py:224`
  - `/Users/leo/workspace/dayu-agent-r/dayu/engine/agent.py:646`
  - `/Users/leo/workspace/dayu-agent-r/dayu/engine/agent.py:722`
  - `/Users/leo/workspace/dayu-agent-r/dayu/engine/agent.py:895`
- **测试证据**:
  - `test_non_stream_tool_calls_emitted` 断言 non-stream tool-call event 携带 content / reasoning_content，且不额外发 `RunnerContentCompletedData`。
  - `test_non_stream_tool_calls_preserve_reasoning_content` 断言第二轮 Runner 输入的 assistant message 保留 `reasoning_content == "非流式推理"`。
- **直接位置**:
  - `/Users/leo/workspace/dayu-agent-r/tests/engine/runners/openai/test_non_stream_response.py:72`
  - `/Users/leo/workspace/dayu-agent-r/tests/engine/test_agent_phase3_tool_call.py:631`
- **判断**: 修复覆盖原问题，且未使用 metadata 承载显式事实。

### 3. max_consecutive_failed_tool_batches 非法值保护：已修复

- **上一轮问题**: `AgentPolicy(max_consecutive_failed_tool_batches=0)` 或负数会让成功工具批次也触发 fallback / raise-error。
- **修复证据**: `AgentPolicy.__post_init__` 在构造期拒绝 `< 1` 的阈值，抛出 `ValueError`。
- **直接位置**: `/Users/leo/workspace/dayu-agent-r/dayu/engine/contracts/agent_policy.py:58`。
- **测试证据**:
  - `test_agent_policy_rejects_invalid_failed_batch_threshold` 覆盖 0 / -1。
  - `test_success_batch_does_not_trigger_failed_batch_fallback` 覆盖成功批次不会误触发失败批次 fallback。
- **直接位置**:
  - `/Users/leo/workspace/dayu-agent-r/tests/engine/test_agent_phase3_tool_call.py:505`
  - `/Users/leo/workspace/dayu-agent-r/tests/engine/test_agent_phase3_tool_call.py:715`
- **判断**: 修复覆盖原问题。

## 边界复审

- Runner 仍只产出 `RunnerEvent`，没有导入或依赖 `ToolExecutor` / `ToolRegistry`。
- Engine 未导入 Host / Service / UI / fins。
- `RunnerToolCallsCompletedData.content` 与 `reasoning_content` 是显式强类型字段，没有塞入 metadata。
- Agent 的 reasoning roundtrip 仍是 Phase 3 过渡复刻行为；没有实现 Issue #10 的 provider-specific 策略。
- `AgentRunRequest.tool_executor` docstring 已同步为 “Host 通过 EngineWorker capability 提供，EngineWorker 替 Host 代持并提供 protocol handle”。

## 已运行验证

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
```

结果：`295 passed in 1.00s`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

## 交总控判断

可以进入总控验收。上一轮 suggestion 已完成后处理，不影响 Phase 3 普通 tool calling 闭环、Runner / Agent 协议、取消边界或架构边界。
