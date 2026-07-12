# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S2 Code Review — AgentDS

## Scope

- **Review target**: S2 working tree changes（8 files, +718/−313 lines）
- **Plan**: `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- **Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-implementation-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-controller-validation.md`
- **Design truth**: `docs/engine/design.md`
- **Agent instructions**: `AGENTS.md`
- **Date**: 2026-07-12

## Review Method

按用户指定的 7 个 focus area 逐项做 adversarial review，每项给出直接代码证据与通过/风险判定。

---

## Focus 1: Native Index 校验（非 bool、非负 int）

### `_is_tool_call_index()` (tool_call_aggregator.py)

```python
return (
    isinstance(value, int)
    and not isinstance(value, bool)
    and value >= 0
)
```

- 旧代码只排除 bool；新代码增加 `value >= 0` 排除负数。✅
- `-1`, `-2` → `isinstance(-1, int)` True, 但 `>= 0` False → 返回 False。✅
- `True`/`False` → `isinstance(True, int)` True, `not isinstance(True, bool)` False → 返回 False。✅
- `1.5`, `"0"` → `isinstance(1.5, int)` False → 返回 False。✅

### `_resolve_index()` 显式非法 index 处理

```
if "index" in delta:
    raw_index = delta["index"]
    if not _is_tool_call_index(raw_index):
        self._append_fatal_error(error_code="tool_call_invalid_index", ...)
        return None          # ← 不 fallback 到 id/synthetic routing
```

- 显式非法 index → `tool_call_invalid_index` fatal + return None。✅
- **不回落**: 后续 routing logic（id/position）仅在 `native_index is None` 时执行。非法 index 设置 `native_index = raw_index`（int 类型），但 `_is_tool_call_index` 返回 False → fatal → return None — 不会进入 id/synthetic 路径。✅

**判定**: ✅ Pass — 显式非法 index fatal，不 fallback。

---

## Focus 2: index/id/position 三种 Routing Signal 统一 Identity Binding

### `_resolve_index()` 完整逻辑

三种 routing signal 的解析顺序:

1. **native_index** (L192-202): wire 显式 `index` 且合法 → `native_index`
2. **id_index** (L214-218): `index_by_id` table lookup
3. **position_index** (L220-226): position table lookup，仅在 `native_index is None and tool_call_id is None` 且 position 非 ambiguous 时

### Identity conflict 检查

**same-id/two-indices** (L230-237):
```python
if id_index is not None and id_index != resolved_index:
    if id_index < 0 and resolved_index not in self._partials_by_index:
        migration_source = id_index    # synthetic → empty native: 唯一允许的迁移
    else:
        self._append_identity_conflict("...different native index")
        return None
```
- synthetic (`id_index < 0`) → empty native target → 允许迁移。✅
- synthetic → occupied native target → conflict。✅
- already bound non-synthetic id → different native index → conflict。✅

**same-index/two-ids** (L244-253):
```python
target = self._partials_by_index.get(resolved_index)
if (target is not None and tool_call_id is not None
    and target.tool_call_id is not None
    and target.tool_call_id != tool_call_id):
    self._append_identity_conflict("...different id")
    return None
```
- 已有 partial 绑定 id A，新 delta 带 id B → conflict。✅

### Position routing

**Position binding** (L256-263):
```python
if position is not None:
    existing_position_index = self._index_by_position.get(position)
    if position not in self._ambiguous_positions:
        if existing_position_index is None:
            self._index_by_position[position] = resolved_index
        elif existing_position_index != resolved_index:
            self._index_by_position.pop(position, None)
            self._ambiguous_positions.add(position)
```
- 首次绑定: `existing_position_index is None` → 建立 binding。✅
- 同一 position 被不同 strong identity 占用 → position 标记为 ambiguous，后续 position-only fragment 不可猜测归属。✅
- `_ambiguous_positions` 在 `_resolve_index()` 的条件中检查: `position not in self._ambiguous_positions` → ambiguous position 不路由。✅

### `_move_partial_index()` 替代旧 merge

```python
if target_index in self._partials_by_index:
    raise RuntimeError("tool call identity validator allowed occupied target")
```
- 旧 `_remap_partial_index` 在 target occupied 时拼接 name/arguments — **已删除**。✅
- 新 `_move_partial_index` 仅在 validator 已确认 empty target 时调用（defense-in-depth RuntimeError）。✅
- `source.name + target.name` / `source.arguments_buffer + target.arguments_buffer` / `target.tool_call_id = target.tool_call_id or source.tool_call_id` — **三个 scan 均无命中**。✅

### Position-routed conflict 覆盖

Controller 指定反例（A/native0 + B/synthetic + position-routed fragment + occupied target）已在 `test_position_routed_conflict_fails_closed_without_merge` 中实现并通过。✅

**判定**: ✅ Pass — 三种 routing signal 统一进入 identity binding，position conflict fail closed。

---

## Focus 3: Fatal Identity Conflict 后无 Merge、无 Completed Tool Calls

### 冲突后执行路径

`_resolve_index()` 返回 `None` 时：
- `feed()` L200: `if index is None: return None`
- SSE parser: `resolved_index = self._aggregator.feed(raw, ...)` → None
- SSE parser `_tool_call_delta_event`: `if resolved_index is None: return None` (L574-579)
- 无 delta event 产出 ✅

`finalize()` 在 identity conflict 后的行为：
- `_fatal_errors` 非空 → `result.fatal_errors` 非空
- SSE parser flush: `if result.fatal_errors: ... yield RunnerDone(ERROR); return` — **不产出 `RunnerToolCallsCompletedData`**。✅
- Non-stream parser: `if tool_calls_request.fatal_errors: ... yield RunnerDone(ERROR); return` — **不产出 `RunnerToolCallsCompletedData`**。✅

### 拼接证据

- `_move_partial_index` 仅移动 partial 到 empty target，不拼接 name/arguments。✅
- 冲突时 `_resolve_index` 在写入 partial 前 return None。✅
- `feed()` 在 `index is None` 时立即 return，不写 name/arguments/provider state。✅

**判定**: ✅ Pass — conflict 后无 merge、无 completed。

---

## Focus 4: `_choice_policy.py` 是 Stream/Non-Stream Terminal Shape 唯一 Owner

### 共用 `_validate_terminal_shape()` (L339-377)

```python
def _validate_terminal_shape(*, finish_reason, has_tool_calls, missing_code, mismatch_code, transport_name):
    if finish_reason is None:
        return ChoicePolicyError(error_code=missing_code, ...)
    finish_declares_tool_calls = finish_reason is FinishReason.TOOL_CALLS
    if has_tool_calls is finish_declares_tool_calls:
        return None     # ← 双向一致 → pass
    return ChoicePolicyError(error_code=mismatch_code, ...)
```

- **`has_tool_calls is finish_declares_tool_calls`**: 双向一致检查。tool calls 存在 ⟺ finish_reason == TOOL_CALLS。✅
- Missing → transport-specific missing code。✅
- Mismatch → transport-specific mismatch code。✅

### Transport wrappers

- `validate_non_stream_terminal_shape(choice, finish_reason, has_tool_calls)` — 先校验 message shape，再调用共用 helper。✅
- `validate_sse_terminal_shape(finish_reason, has_tool_calls)` — 直接调用共用 helper。✅

### Parser direct forcing 删除

| 旧位置 | 旧代码 | 新代码 |
|--------|--------|--------|
| `non_stream_parser.py` L362-363 | `done_finish_reason = FinishReason.TOOL_CALLS` | 已删除，`RunnerDoneData(finish_reason=finish_reason)` |
| `sse_parser.py` L683 | `finish = FinishReason.TOOL_CALLS` | 已删除，`RunnerDoneData(finish_reason=self._finish_reason)` |

- `done_finish_reason = FinishReason\.TOOL_CALLS|finish = FinishReason\.TOOL_CALLS` scan → **无命中**。✅
- `FinishReason\.TOOL_CALLS` 语义 scan → 仅 `_choice_policy.py` 两处：wire mapping (L31) + presence 比较 (L366)。✅
- `sse_parser.py` 和 `non_stream_parser.py` **零命中**。✅

### Parser 消费 owner 的顺序

**SSE parser flush (L658-664)**:
```python
terminal_error = validate_sse_terminal_shape(finish_reason=..., has_tool_calls=...)
if terminal_error is not None:
    yield from _handle_choice_policy_error(...)  # fatal → 不产 completed/done
    return
```

**Non-stream parser (L268-280)**:
```python
terminal_error = validate_non_stream_terminal_shape(choice, finish_reason=..., has_tool_calls=...)
if terminal_error is not None:
    yield from _emit_choice_policy_error(...)  # fatal → 不产 completed/done
    return
assert finish_reason is not None
```

两路均在 **任何 completed/done event 之前** 调用 terminal shape policy。✅

**判定**: ✅ Pass — `_choice_policy` 是唯一 owner，parser 无 direct forcing。

---

## Focus 5: Missing/Null Finish Reason、Mismatch 全部 Fail Closed

### 矩阵覆盖

| 场景 | 处理 | 代码证据 |
|------|------|----------|
| missing/null finish (content) | `finish_reason is None` → missing_code fatal | `_validate_terminal_shape` L359-363 |
| missing/null finish (tool calls) | 同上 | 同一 helper，`has_tool_calls` 不影响 missing 分支 |
| tool calls + STOP/LENGTH/CONTENT_FILTER | `has_tool_calls=True`, `finish_declares_tool_calls=False` → mismatch fatal | L364-376 |
| content + TOOL_CALLS | `has_tool_calls=False`, `finish_declares_tool_calls=True` → mismatch fatal | L364-376 |
| unknown finish reason | 在 `_resolve_finish_reason` → `_FINISH_REASON_MAP.get(raw)` 返回 None → invalid_code fatal | choice_policy L369-376 |

### Completed 不先于 Error

- SSE flush: `terminal_error is not None` → return early，**不执行后续** completed 逻辑。✅
- Non-stream: `terminal_error is not None` → return early，**不执行后续** tool-call/content 处理。✅

**判定**: ✅ Pass — 全部 fail closed，completed 不先于 error。

---

## Focus 6: Non-Stream Arguments 仅接受 String

### `_coerce_final_tool_call()` (non_stream_parser.py L528-579)

```python
arguments: JsonValue | None = None
if isinstance(function, dict):
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        func_payload["arguments"] = arguments

pre_error: RunnerProtocolErrorData | None = None
if not isinstance(arguments, str):
    pre_error = RunnerProtocolErrorData(
        error_code=runner_protocol_error_code(_TOOL_CALL_ARGUMENTS_NOT_STRING_CODE),
        message="tool call ... function.arguments must be a JSON string",
        ...
    )
```

| 输入 | `isinstance(arguments, str)` | 结果 |
|------|------------------------------|------|
| `'{"a":1}'` | True | ✅ 正常处理 |
| `{"a":1}` (dict) | False | ❌ `tool_call_arguments_not_string` fatal |
| `[1,2]` (list) | False | ❌ 同上 |
| `42` (number) | False | ❌ 同上 |
| `true` (bool) | False | ❌ 同上 |
| `null` (None) | False | ❌ 同上 |
| 缺失 (key absent) | False (None) | ❌ 同上 |
| `function` 不是 dict | False (None) | ❌ 同上 |

### 删除的旧代码

- `isinstance(arguments, Mapping)` → `json.dumps(dict(arguments))` — **已删除**。✅
- `isinstance(arguments, Mapping)|json\.dumps\(dict\(arguments\)\)|dict arguments preserved` scan → **无命中**。✅

### String 的既有 fatal 分类保留

- Invalid JSON string → aggregator 内部 JSON parse → `tool_call_arguments_invalid_json`（不变）。✅
- Valid JSON scalar string → aggregator `_parse_arguments` → `tool_call_arguments_not_object`（不变）。✅

**判定**: ✅ Pass — 仅 string 合法，旧兼容完全删除。

---

## Focus 7: 测试与 Scan 完整性

### Negative/Positive Matrix 覆盖

| Plan matrix entry | 测试文件 | 状态 |
|---|---|---|
| 5 个非法 native index | `test_tool_call_identity_conflicts.py` | ✅ |
| synthetic positive | 同上 | ✅ |
| same-id/same-index positive | 同上 | ✅ |
| synthetic → empty target | 同上 | ✅ |
| synthetic → occupied target | 同上 | ✅ |
| same-id/two-index | 同上 | ✅ |
| same-index/two-id | 同上 | ✅ |
| position positive continuation | 同上 | ✅ |
| position-routed occupied-target conflict | `test_position_routed_conflict_fails_closed_without_merge` | ✅ |
| dict/list/number/bool/null/missing args | `test_old_protocol_parity_regressions.py` | ✅ |
| tool calls + STOP mismatch | `test_stream_non_stream_terminal_parity.py` | ✅ |
| content + TOOL_CALLS mismatch | 同上 | ✅ |
| content/tool missing/null finish | 同上 | ✅ |

### Scan 完整性

| Scan | 预期 | 实际 |
|------|------|------|
| `isinstance(arguments, Mapping)\|json\.dumps\(dict\(arguments\)\)\|dict arguments preserved` | 无 | **无命中** ✅ |
| `done_finish_reason = FinishReason\.TOOL_CALLS\|finish = FinishReason\.TOOL_CALLS` | 无 | **无命中** ✅ |
| `source\.name \+ target\.name\|source\.arguments_buffer \+ target\.arguments_buffer\|target\.tool_call_id = target\.tool_call_id or source\.tool_call_id` | 无 | **无命中** ✅ |
| `FinishReason\.TOOL_CALLS` in sse/non_stream | 无 | **仅 `_choice_policy.py` 两处** ✅ |
| `hasattr(\|getattr(` in 4 production files | 无 | **无命中** ✅ |
| `from dayu\.host\|import dayu\.host` in 4 production files | 无 | **无命中** ✅ |
| `loose\|compat\|OLD` in 4 production files | 无 | **无命中** ✅ |

### 验证结果

- Controller 指定 node: `1 passed` ✅
- S2 focused matrix: `109 passed` ✅
- Full OpenAI adapter suite: `302 passed` ✅
- Pyright: `0 errors, 0 warnings, 0 informations` ✅
- `git diff --check`: pass ✅

**判定**: ✅ Pass — 测试覆盖完整，无 compat shim/Host repair/loose parsing。

---

## Additional Checks

### S1 不变量保持

- Agent `_classify_iteration` 的 `finish_reason` 读取: S2 parser 现在产出正确 finish_reason → `_classify_iteration` 在 L1809 的 `finish_reason is not FinishReason.TOOL_CALLS` 检查正常触发（parser bug 时 defense-in-depth）。✅
- Agent `runner_done.finish_reason` contract: parser 始终产出显式 `FinishReason`，S1 的 `isinstance(data.finish_reason, FinishReason)` 守卫不会被触发（正常路径）。✅

### 未改范围

- Host、Agent、runtime schema、Fins、Service、CLI — 无修改。✅
- 合法 synthetic identity 与无歧义 position continuation 保留。✅
- Error classifier、Runner identity、HTTP/retry、provider marker — 未修改。✅

---

## Findings

无。7 个 focus area 全部通过，未发现 material issue。

---

## Plan Review Conclusion

**Pass** — 0 findings, 0 blocking questions.

**Artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-code-review-ds.md`
