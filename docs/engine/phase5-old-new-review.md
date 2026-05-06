# Engine Phase 5 OLD/NEW 专项对比 Review

结论：**通过**。

本轮 review 对象是当前 `refactory/phase_5` 工作区相对 `main` 的 Phase 5 实现，重点核对 `finish_reason=length` final-answer continuation。Review 只读代码与测试；未修改生产代码、测试代码，未 commit，未 push。

## 1. Findings

### Blocking

无。

### Important

无。

### Suggestion

无。

## 2. OLD 证据摘要

OLD 可靠语义主要来自：

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1159`：当 Runner summary 表明 `truncated` / `finish_reason=length`，且 `budget_state.continuation_count < max_continuations` 时，Agent 自动进入 continuation，而不是立刻 final。
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1177`：将当前截断内容累积进 `accumulated_content_parts`。
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1180`：将截断 assistant content 追加回 messages。
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1183`：追加 continuation user prompt。
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1217`：非续写或续写结束时，将累积内容与当前 final content 拼接为最终回答。
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1219`：`content_filter` 不进入 continuation，而是作为 filtered final 收口。
- `/Users/leo/workspace/dayu-agent/tests/engine/test_context_budget.py:453`：覆盖一次 `length -> continuation -> stop`，断言最终内容包含前序与续写内容。
- `/Users/leo/workspace/dayu-agent/tests/engine/test_context_budget.py:498`：覆盖 continuation 达到上限后直接返回 final answer。
- `/Users/leo/workspace/dayu-agent/tests/engine/test_context_budget.py:1091`：覆盖多轮 continuation 后最终回答包含全部片段。

OLD 同一文件还包含 context overflow、soft-limit compaction、`TruncationManager` / `fetch_more` 相关能力；这些已被 Phase 5 计划明确排除，不作为本轮缺陷依据。

## 3. NEW 对照摘要

NEW 当前实现与 Phase 5 handoff 的对齐情况：

1. `length -> continuation prompt -> 多轮拼接 -> final answer` 已实现。
   - `dayu/engine/agent.py:572` 只在 `FinishReason.LENGTH` 下进入 `_handle_length_final_decision`。
   - `dayu/engine/agent.py:612` 将每轮截断 content 追加到 `continuation_content_parts`。
   - `dayu/engine/agent.py:627` 将当前截断 assistant content 追加回 run-local messages。
   - `dayu/engine/agent.py:636` 追加 `AgentPolicy.continuation_prompt` 作为下一轮 user message。
   - `dayu/engine/agent.py:580` 在 continuation 后得到非 LENGTH final 时拼接所有前序片段与当前 content。

2. continuation 上限与 max_iterations 边界已按 NEW 计划收口。
   - `dayu/engine/agent.py:613` 使用 `continuation_max_attempts` 限制 continuation 次数。
   - `dayu/engine/agent.py:616` 同时检查剩余 LLM iteration 预算。
   - 边界耗尽时返回 degraded final answer，内容为已累积片段，不进入 Phase 3 force-answer。

3. `tools=()` 收窄策略已实现，且不破坏普通 tool loop。
   - `dayu/engine/agent.py:414` 在 `continuation_active` 时传入空工具集合。
   - `dayu/engine/agent.py:489` 普通工具批次路径会清掉 continuation 状态，Phase 3 tool loop 保持独立。
   - 这是 NEW 架构决策：continuation 是 final-answer text continuation，不是普通 tool loop continuation。

4. continuation 轮返回 tool calls 已 fail-closed，且不执行 ToolExecutor。
   - `dayu/engine/agent.py:446` 在 continuation 轮分类前检查 tool-call 信号。
   - `dayu/engine/agent.py:654` 覆盖 `tool_calls`、tool-call delta 信号与 `finish_reason=TOOL_CALLS`。
   - 命中后返回 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)`。

5. `content_filter` 不 continuation。
   - `dayu/engine/agent.py:572` 只有 `LENGTH` 才续写。
   - `dayu/engine/agent.py:968` 将 `CONTENT_FILTER` 标记为 filtered final。

6. 取消优先与 Runner close 未回退。
   - 主循环在 Runner 调用前、调用后、tool 注入后均保留取消检查。
   - `_make_final_or_cancelled_after_close` 与 `_make_failed_or_cancelled_terminal_with_close` 仍在 terminal 前二次检查取消。
   - `run_messages` 的 `finally` 仍保证 `_close_runner_once()`。

7. 未意外迁入后移能力。
   - 当前 Phase 5 diff 未新增 context overflow 强类型识别、`context_compaction_requested` 生产路径、trigger ratio、`max_context_tokens` 策略入口、Engine compact/retry、OLD `TruncationManager` / `fetch_more`。

## 4. 测试对照

NEW 测试覆盖足以证明本轮 continuation 边界：

- `tests/engine/test_agent_phase3_tool_call.py::test_length_continuation_appends_prompt_and_joins_content`
- `tests/engine/test_agent_phase3_tool_call.py::test_length_continuation_stops_at_attempt_limit`
- `tests/engine/test_agent_phase3_tool_call.py::test_length_continuation_respects_max_iterations`
- `tests/engine/test_agent_phase3_tool_call.py::test_length_continuation_tool_call_is_fail_closed`
- `tests/engine/test_agent_phase3_tool_call.py::test_content_filter_does_not_trigger_continuation`
- `tests/engine/test_agent_phase3_tool_call.py::test_cancellation_wins_before_length_continuation`
- `tests/engine/test_agent_phase2.py::test_length_and_content_filter_final_boundaries`

本轮实际验证：

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q
```

结果：`43 passed`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

## 5. 本轮不作为缺陷的后移能力

以下 OLD 能力明确不属于 Phase 5 缺陷：

- provider context overflow 强类型识别。
- `context_compaction_requested` / `context_compaction_required`。
- Engine 内 context compact / retry。
- `max_context_tokens` / trigger ratio / projected context early stop。
- OLD `TruncationManager`。
- `fetch_more`、cursor、TTL、scope token、tool-level truncation manager。
- Host wait record / resume / `run_suspended`。
- Host conversation memory / transcript / trace store。
- DuplicateCallGuard / semantic repeat guard。
- provider-specific reasoning roundtrip patch。

## 6. Gate 结论

Phase 5 OLD/NEW continuation 专项对比 review 通过。可以进入常规 `docs/code_review.md` review 与总控验收后续 gate。
