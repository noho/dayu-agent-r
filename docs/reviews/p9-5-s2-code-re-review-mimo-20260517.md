# P9.5 S2 Code Re-Review (AgentMiMo)

## Gate

- Role: AgentMiMo, re-review only.
- Gate: verify F1/F2/F3 fixed, no new blockers introduced.
- Source adjudication: `docs/reviews/p9-5-s2-code-review-controller-adjudication-20260517.md`.
- Source review: `docs/reviews/p9-5-s2-code-review-ds-20260517.md`.
- Fix artifact: `docs/reviews/p9-5-s2-fix-20260517.md`.
- Changed files: `dayu/engine/runners/openai/_types.py`, `dayu/engine/runners/openai/sse_parser.py`, `dayu/engine/runners/openai/tool_call_aggregator.py`, `tests/engine/runners/openai/test_sse_tool_call_stream.py`.
- No code, tests, plan, or artifacts were modified by this re-review.

## F1 Verification: Dead `_OpenAIUsage` TypedDict Removed

- **Diff evidence**: `_types.py` 删除了 `_OpenAIUsage` 类定义（原 lines 152-157）及其 `__all__` 条目（原 line 226）。`sse_parser.py` 删除了 `_OpenAIUsage` 的 import，替换为 `from dayu.engine.runners.openai.usage import coerce_usage`。
- **Grep verification**: 当前代码库中 `_OpenAIUsage` 仅残留于 `docs/engine/phase1-plan.md`（历史文档，非生产代码）。
- **Verdict**: ✅ F1 fixed. 无回归。

## F2 Verification: Bool-as-int Rejected in `_coerce_tool_call_delta`

- **Diff evidence**: `sse_parser.py:469` 从 `isinstance(index, int)` 改为 `_is_tool_call_index(index)`。
- **`_is_tool_call_index` 实现**（`tool_call_aggregator.py:48-56`）:
  ```python
  def _is_tool_call_index(value: JsonValue | None) -> TypeGuard[int]:
      return isinstance(value, int) and not isinstance(value, bool)
  ```
  正确拒绝 `bool`，`TypeGuard[int]` 为 pyright 提供类型收窄。
- **下游影响追踪**: 当 `index` 为 `True`/`False` 时，`_is_tool_call_index` 返回 `False`，delta 中不写入 `"index"` 键。后续 `_tool_call_delta_event` fallback 路径（`delta.get("index")` → `None` → `0`）安全，因为 `raw_index` 不可能是 `bool`。
- **Verdict**: ✅ F2 fixed. 无回归。

## F3 Verification: Bool-as-int Rejected in `ToolCallAggregator._resolve_index`

- **Diff evidence**: `tool_call_aggregator.py:170` 从 `isinstance(delta_index, int)` 改为 `_is_tool_call_index(delta_index)`。
- **双重防御确认**: F2 在 parser 层拒绝 bool index，F3 在 aggregator 层做二次拦截。即使外部直接调用 `aggregator.feed()`（绕过 parser），bool index 也会被拒绝并走 id fallback。
- **Verdict**: ✅ F3 fixed. 无回归。

## Test Coverage Verification

- **`test_bool_index_tool_calls_stay_separate_by_id`**: 端到端 SSE 解析路径，两个 tool call 使用 `index: true` / `index: false`，验证按 id 稳定聚合为 `[0, 1, 0, 1]`。覆盖 F2 parser 层。
- **`test_aggregator_rejects_bool_index_and_falls_back_to_id`**: 直接调用 `ToolCallAggregator.feed()`，覆盖 F3 aggregator 层。
- **回归确认**: 原有 3 个 tool call 测试全部通过（5/5 passed）。
- **Verdict**: ✅ 测试覆盖充分。

## Scope / No-New-Blocker Check

| Concern | Status |
|---|---|
| Provider public state/contract | Not introduced |
| Retry model redesign | Not introduced |
| Host governance in parser/runner | Not introduced |
| Memory/tool governance in metadata | Not introduced |
| Proactive context governance | Not introduced |
| P10+ semantics | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |
| Compatibility re-export/wrapper | Not introduced |
| Extra payload bag | Not introduced |

## Validation

- `pytest tests/engine/runners/openai/test_sse_tool_call_stream.py` — 5/5 passed.
- `pyright dayu/engine/runners/openai/_types.py sse_parser.py tool_call_aggregator.py` — 0 errors, 0 warnings, 0 informations.

## Residual Notes

- `_is_tool_call_index` 未列入 `tool_call_aggregator.py` 的 `__all__`，但它是 `_` 前缀私有函数，且 `__all__` 仅控制 `from module import *` 的公共 API。当前通过显式 import 使用，符合项目约定。无 action needed。
- Fix artifact 声称 "No WARN diagnostic was added for bool index rejection"。控制器裁决已明确 WARN 为 optional-only，当前行为（静默走 id fallback）可接受。

## Summary

- **F1**: ✅ fixed, verified.
- **F2**: ✅ fixed, verified.
- **F3**: ✅ fixed, verified.
- **New blockers**: 0.
- **Blocking count**: 0.
