# Phase 3 OLD / NEW 严格对比 Review

结论：**通过**。

本轮从 OLD `AsyncAgent` 普通工具调用主链路建立行为地图，再对照 NEW 当前实现、测试与文档。初审曾发现 1 个 important：NEW 的 LLM-facing truncation 投影会输出不可执行的 `{"has_more": true}`，与 OLD `project_for_llm()` 只投影可执行续读字段的可靠语义不一致。Zeno 随后已修复：当前 Phase 3 不再投影不可执行的 `has_more`，也不伪造尚未落地的 `next_action` / `fetch_more_args`。

复核判断：Phase 3 普通 tool calling 主链路、LLM-facing 基础投影、force-answer、content/reasoning roundtrip、content_filter degraded、连续失败批次保护、取消优先级与 Runner 边界均已收口。当前剩余风险是 fetch_more / truncation 可执行续读能力尚未在 Phase 3 实现，后续需要通过明确 contract 扩展再引入。

## 初审发现与修复记录

### Important: truncation 投影只暴露 `has_more`，丢失 OLD 的 LLM 可执行续读语义

初审严重级别：important，曾阻塞 OLD/NEW gate 通过。

OLD 证据：

- OLD `project_for_llm()` 明确只把 `truncation` 中的 LLM 可执行字段投影给模型：`next_action` 与 `fetch_more_args`，见 `/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:226`、`/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:289`、`/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:332`-`/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:337`。
- OLD `fetch_more` 工具 schema 要求模型直接使用最近一次截断结果中的 `truncation.fetch_more_args.cursor` 与 `scope_token`，见 `/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:262`-`/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:272`。
- OLD 测试锁定 truncation 中包含 `next_action="fetch_more"` 与 `fetch_more_args`，见 `/Users/leo/workspace/dayu-agent/tests/engine/test_truncation_manager.py:374`-`/Users/leo/workspace/dayu-agent/tests/engine/test_truncation_manager.py:391`。

初审时的 NEW 问题：

- NEW projection helper 曾在有 truncation 时只输出 `{"has_more": result.truncation.has_more}`。
- NEW Phase 3 测试曾把该形状锁定为期望。

为什么这是语义漂移：

OLD 的 truncation 不是普通诊断字段，而是模型可继续取数的协议提示。只告诉模型“还有更多”，但不给任何可执行动作或参数，会让模型知道结果不完整，却无法按协议继续读取。Phase 3 可以不实现 Host ToolRuntime / fetch_more，但既然尚无可执行续读契约，就不能投影一个不可执行的半协议。

修复后复核：

- 当前 Phase 3 不再把 `ToolTruncationInfo.has_more` 单独投影为 LLM-facing truncation。
- 当前 Phase 3 也不伪造 `next_action` / `fetch_more_args`。
- fetch_more / truncation 可执行续读能力保留到后续 contract 扩展阶段实现。
- 修复状态：已修复，OLD/NEW gate 复核通过。

### Suggestion: smoke final answer 摘要曾打印完整正文

初审严重级别：suggestion，不阻塞 Phase 3 主链路。

初审时 `utils/smoke_async_agent_tool_call.py` 的 final answer 事件摘要会打印完整 `content`。这不影响生产路径，但与脚本“不输出敏感载荷，只输出摘要”的定位不一致。后处理已改为默认只输出 `content_len`、`degraded`、`filtered`、`finish_reason` 等摘要字段。

修复状态：已按后续用户要求调整为人工 smoke 明确输出固定 smoke prompt 的 final answer，并保留 key / headers / payload / 工具参数不泄漏；`tests/engine/test_smoke_async_agent_tool_call.py` 已同步覆盖输出格式。

## 已确认收口

- **普通 tool calling 主链路**：NEW `_AsyncAgent.run_messages()` 已实现多 iteration loop，Runner tool call 后构造 `ToolExecutionRequest`，调用 `ToolExecutor.execute()`，接受 completed / failed outcome，再注入 assistant tool_calls + tool messages。
- **LLM-facing 基础投影**：成功 object 展开、scalar 包 `content`、失败只含 `error/message/hint`，没有把内部 `ok/value` 信封直接塞给 LLM。
- **content / reasoning roundtrip**：流式 content delta 与非流式 `reasoning_content` 都能进入下一轮 assistant tool_calls message。
- **provider_state / Gemini thought signature**：Runner payload 会把 `AssistantToolCall.provider_state` 投影回 provider `extra_content`，Agent 注入 assistant tool_calls 时保留 `provider_state`。
- **max_iterations force-answer**：最后一轮工具照常执行，随后默认追加 `UserMessage` fallback prompt、以 `tools=()` 调 Runner，并产出 `degraded=True` final answer；`RAISE_ERROR` 才失败。
- **content_filter degraded**：NEW 普通 final 把 `CONTENT_FILTER` 标记为 `filtered=True, degraded=True`。
- **连续失败工具批次保护**：NEW 默认阈值 2，成功批次清零，达到阈值后按 fallback mode 收口。
- **Runner 边界**：Runner 协议仍只接收 messages/options/tools 并产出 RunnerEvent，不依赖 ToolExecutor、不执行工具。

## 可接受差异与合理后移

- **多工具调用串行执行**：NEW Phase 3 选择 Agent 串行调用 `ToolExecutor.execute()`，这是为了守住 Engine/Runner 职责分离，属于合理重设。
- **`tool_calls_remaining` 暂不投影**：OLD `project_for_llm()` 会在 budget 非 None 时注入该字段。Phase 3 不落 context budget，因此暂不作为 blocking 字段；Phase 5 做 context budget / continuation 时应重新评估。
- **语义级 DuplicateCallGuard 后移**：NEW Phase 3 只做协议级 duplicate `tool_call_id` guard。语义级重复调用保护与 Host ToolRuntime / ToolRegistry policy 关联更强，合理后移。
- **context budget / continuation 后移**：OLD `finish_reason=length` continuation 与 context overflow compaction 仍可靠，但 migration plan 明确放到 Phase 5。这不阻塞 Phase 3，但后续不能把 Phase 3/4 描述成完整 OLD Agent 等价能力。
- **fetch_more / truncation 可执行续读后移**：Phase 3 不投影不可执行 truncation。后续应通过 contract 扩展表达可执行续读动作和参数，再恢复 LLM-facing truncation 投影。
- **Issue #10 provider-specific reasoning 写回策略后移**：Phase 3 复刻 OLD 无条件写回 `reasoning_content` 的过渡行为，后续再做 provider-specific 策略，符合当前迁移决策。

## 验证记录

Zeno 修复后已有验证记录：

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py -q
# passed
```

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
# passed
```

```bash
source .venv/bin/activate && pyright
# 0 errors
```

总控之后也复跑过：

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
# passed
```

```bash
source .venv/bin/activate && pyright
# 0 errors
```

本次后处理只针对 review 文档状态与 smoke 摘要输出；未伪造新的全量测试记录。

## 总控判断

Phase 3 OLD/NEW 严格对比 gate 当前通过。剩余 truncation / fetch_more 风险不属于 Phase 3 blocking，而是后续 contract 扩展任务。
