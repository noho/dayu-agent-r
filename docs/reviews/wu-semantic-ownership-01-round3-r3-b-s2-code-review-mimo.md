# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S2 Code Review — AgentMiMo

## Review Target

`dayu/engine/runners/openai/tool_call_aggregator.py`、`_choice_policy.py`、`sse_parser.py`、`non_stream_parser.py` 的 S2 实现改动；新增 `tests/engine/runners/openai/test_tool_call_identity_conflicts.py`。

## Design / Control Context

- `docs/engine/design.md` §7 Runner 协议、§9 RunnerEvent、§10 工具调用协议
- `AGENTS.md` 语义所有权与修复边界

## Review Focus 验证

### 1. Native index 非 bool 非负 int ✅

- `_is_tool_call_index()` 新增 `value >= 0` 检查，`-1/-2/True/1.5/"0"` 均返回 `False`。
- `_resolve_index()` 中 `"index" in delta` 时，非法 index 产生 `tool_call_invalid_index` fatal 并返回 `None`，不回落到 id/synthetic path。
- `_move_partial_index()` 对已占用 target 抛 `RuntimeError`（防御性断言），旧 merge 逻辑（name/arguments 拼接）完全删除。

### 2. index/id/position 三种 routing signal 统一 binding ✅

- `_resolve_index()` 统一处理三种信号：native index → 直接使用；id → 查表或分配 synthetic；position → 仅限无 index/id 的 continuation。
- Position routing 限制：`position not in self._ambiguous_positions` 时才查 `_index_by_position`；同一 position 出现不同 resolved index 时标为 ambiguous，后续 position-only fragment 不再猜测归属。
- Synthetic → occupied target：`id_index < 0 and resolved_index not in self._partials_by_index` 时才允许迁移，否则 `tool_call_identity_conflict` fatal。
- Same id → two native indices / same native index → two ids：均为 `tool_call_identity_conflict` fatal。

### 3. Fatal identity conflict 后不拼接 ✅

- `_move_partial_index()` 只做 index 重映射，不做 name/arguments/provider state 合并。
- Fatal error 在 delta 写入 partial 前返回（`_resolve_index` 返回 `None` → `feed()` 返回 `None` → delta 被丢弃）。
- `finalize()` 只有在无 fatal errors 时才产出 `RunnerToolCallsCompletedData`。
- 测试 `test_native_index_and_id_conflicts_are_fatal_without_fragment_merge` 断言无 `lookupdelete`。

### 4. `_choice_policy.py` 是 terminal shape 唯一 owner ✅

- `_validate_terminal_shape()` 私有 helper：`finish_reason is None` → missing error；`has_tool_calls is not (finish_reason is TOOL_CALLS)` → mismatch error。
- `validate_non_stream_terminal_shape()` 和 `validate_sse_terminal_shape()` 各自包装该 helper，提供 transport-specific error codes。
- Non-stream parser：`validate_non_stream_terminal_shape()` 在 `_build_tool_calls()` 之前调用；mismatch 时直接 return，不产出 completed。
- SSE parser：`validate_sse_terminal_shape()` 在 `aggregator.finalize()` 之前调用；mismatch 时直接 return，不产出 completed。
- `FinishReason.TOOL_CALLS` 语义 scan 仅命中 `_choice_policy.py` 的 wire mapping 和 fail-closed 比较；`sse_parser.py` 和 `non_stream_parser.py` 零命中。

### 5. Missing/null finish_reason、tool calls + non-tool reason、content + TOOL_CALLS ✅

- Missing/null：`_validate_terminal_shape` 第一个检查 `finish_reason is None` → missing error。
- Tool calls + non-tool reason（如 STOP）：`has_tool_calls=True` 但 `finish_reason is not TOOL_CALLS` → mismatch error。
- Content + TOOL_CALLS：`has_tool_calls=False` 但 `finish_reason is TOOL_CALLS` → mismatch error。
- Completed 不先于 error：terminal shape validation 在 completed event 前执行；mismatch 时直接 return，不产出 completed。

### 6. Non-stream dict/list/number/bool/null/missing arguments ✅

- `_coerce_final_tool_call()` 删除 `isinstance(arguments, Mapping)` coercion 分支。
- `not isinstance(arguments, str)` 产生 `tool_call_arguments_not_string` fatal，覆盖 dict、list、number、bool、null 和 missing。
- String invalid JSON 保持 `tool_call_arguments_invalid_json`（aggregator 层）。
- JSON list/number/bool/null string 保持 `tool_call_arguments_not_object`（aggregator finalize 层）。
- Source scan `isinstance(arguments, Mapping)` / `json.dumps(dict(arguments))` 无命中。

### 7. Tests 覆盖 plan negative/positive matrix ✅

新增 `test_tool_call_identity_conflicts.py`：

- 5 个非法 native index parametrize：`-1/-2/True/1.5/"0"` → `tool_call_invalid_index`
- Synthetic positive：缺 index + 有 id → synthetic identity
- Same-id/same-index positive：正常分片稳定聚合
- Synthetic → empty target：无损迁移
- Synthetic → occupied target：`tool_call_identity_conflict` fatal
- Same-index/two-id + same-id/two-index：`tool_call_identity_conflict` fatal，无 merge
- Position continuation + position-routed conflict：`tool_call_identity_conflict` fatal
- SSE integration `test_position_routed_conflict_fails_closed_without_merge`：端到端验证

迁移的旧测试：`test_sse_tool_call_stream.py`、`test_non_stream_response.py`、`test_old_protocol_parity_regressions.py`、`test_stream_non_stream_terminal_parity.py`。

### 8. 无新增 compat shim / hasattr / getattr / loose parsing / 反向依赖 ✅

- Diff 中无 `hasattr`/`getattr` 新增。
- 无 provider capability flag、provider 名单、compatibility shim 或 Host repair。
- 无反向依赖：改动只在 OpenAI adapter 内部。

## Findings

未发现实质性问题。S2 实现正确落实 plan 的 identity conflict rules、terminal shape policy、arguments normalization 和所有 negative/positive matrix。

## Open Questions

无。

## Residual Risks

| Risk | Classification | Owner |
| --- | --- | --- |
| Synthetic delta preview 使用负内部 key | accepted current design | `ToolCallAggregator` |
| `_coerce_final_tool_call` 中 `function` 非 dict 时报 "arguments must be string" 而非 "function field malformed" | 诊断精度，不影响正确性 | non-stream parser diagnostic |

## Code Review Conclusion

**status: pass**

S2 实现正确落实 plan 的所有 implementation decisions。ToolCallAggregator 统一处理 index/id/position 三种 routing signal 并 fail closed on conflicts；`_choice_policy.py` 是 stream/non-stream terminal shape 唯一 owner；non-stream dict arguments compatibility 已删除；tests 覆盖完整 negative/positive matrix。无新增 compat shim、hasattr/getattr 或反向依赖。

**artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-code-review-mimo.md`
**findings**: 0
**blocking questions**: 0
