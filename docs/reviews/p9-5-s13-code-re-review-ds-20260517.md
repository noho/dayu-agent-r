# P9.5 S13 Message / Tool Result Size Governance Code Re-Review (O1/O4 fix)

**Reviewer**: AgentDS
**Date**: 2026-05-17
**Scope**: 仅复核原 DS review O1/O4 fix，不做全量重审
**Original review**: `docs/reviews/p9-5-s13-code-review-ds-20260517.md`

## 结论: PASS

O1 和 O4 均已有效修复。0 new blocking findings。原 review 其余 O2/O3/O5/O6 不在本次复核范围。

## O1 复核 — Engine iteration-loop 集成测试

**原发现**: `_AsyncAgent.run_messages()` per-iteration guard（line 710）是捕获工具产出注入后消息变大的唯一防线，但缺少 end-to-end 集成测试覆盖该路径。

**Fix**: 新增 `test_oversized_tool_message_fails_before_next_runner_call`（`tests/engine/test_agent_phase3_tool_call.py:961-983`）

**复核证据**:

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 模拟 oversized tool result 注入 | PASS | `_success({"content": "x" * 70000})` → ToolMessage content ~70KB |
| 验证 per-iteration guard 在下一轮 Runner 前拦截 | PASS | `runner.call_count == 1`（第二轮 `_final_script("unreachable")` 从未执行） |
| 验证 error_code | PASS | `"context_compaction_required"` |
| 验证 recoverable | PASS | `True` |
| 验证 Runner 正确关闭 | PASS | `runner.close_count == 1` |
| 验证 executor 确实被调用 | PASS | `len(executor.requests) == 1` |
| 测试通过 | PASS | `pytest` targeted pass |

**判定**: O1 **已关闭**。集成测试完整覆盖了 tool result 注入 → per-iteration guard 拦截 → `RUN_FAILED(context_compaction_required)` 的端到端路径。Runner 在 oversized 消息进入前被阻止，close 也被正确执行。

## O4 复核 — `_message_inline_texts` 纳入 Assistant tool call arguments

**原发现**: `_message_inline_texts` 对 `AssistantMessage` 只提取 `content` 和 `reasoning_content`，不提取 `tool_calls[].arguments`，超大 tool call arguments 会绕过 Engine inline size guard。

**Fix**:
1. 新增 `_assistant_tool_call_inline_texts()`（`dayu/engine/agent.py:384-408`）
2. `_message_inline_texts()` 对 `AssistantMessage` 新增 `tool_call_texts` 提取（`dayu/engine/agent.py:375-379`）
3. 新增 `test_oversized_assistant_tool_call_arguments_require_context_boundary`（`tests/engine/test_agent_message_union.py:100-123`）

**复核证据**:

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `tool_call.id` 纳入 inline text | PASS | `_assistant_tool_call_inline_texts` return tuple 首个元素 |
| `tool_call.name` 纳入 inline text | PASS | return tuple 第二个元素 |
| `tool_call.arguments` JSON 序列化后纳入 | PASS | `json.dumps(dict(tool_call.arguments), ensure_ascii=False, sort_keys=True)` |
| `tool_call.provider_state` 纳入（Gemini thought_signature） | PASS | pattern match `GeminiToolCallState(thought_signature=signature)` → `(signature,)` |
| `provider_state=None` 正确处理 | PASS | 返回空 tuple，不产生额外文本 |
| `assert_never` 穷尽性检查 | PASS | 新增 provider_state 类型时 type checker 会在此处报错 |
| `dict()` 包装处理 `Mapping[str, JsonValue]` | PASS | `arguments` 类型为 `Mapping[str, JsonValue]`，`dict()` 确保 JSON 可序列化 |
| docstring 完整（中文） | PASS | 含参数、返回值、异常说明 |
| oversized arguments 触发 guard | PASS | 测试 assert failure is not None, error_code, recoverable |
| pyright clean | PASS | 0 errors, 0 warnings |
| 测试通过 | PASS | `pytest` targeted pass |

**额外验证** — `_assistant_tool_call_inline_texts` 的 provider_state 穷尽性:

```
ToolCallProviderState ≡ GeminiToolCallState  (dayu/contracts/tool_call.py:47)
```

当前仅 `GeminiToolCallState` 一个具体类型。`_assistant_tool_call_inline_texts` 的 `match` 语句覆盖了 `None` 和 `GeminiToolCallState` 两个分支，`assert_never` 在新增 provider state 类型但未更新此函数时会在 type checking 阶段报错。穷尽性正确。

**判定**: O4 **已关闭**。Assistant tool call 的所有 outbound 文本字段（id、name、arguments JSON、provider_state）均已纳入 Engine inline size guard。超大 arguments 不再能绕过检查直接进入 Runner。

## 未覆盖项

- O2/O3/O5/O6 不在本次复核范围，状态维持原 review 判定。
- `_assistant_tool_call_inline_texts` 对 `json.dumps(dict(tool_call.arguments))` 无法序列化的场景声明了 `TypeError`，但当前 `JsonValue` 类型保证所有合法值均可序列化，无测试覆盖此边缘路径——不构成 blocking。
- `_assistant_tool_call_inline_texts` 将 `tool_call.id` 和 `tool_call.name`（通常极短）也纳入 size 计算，语义上偏保守但正确——不构成问题。
