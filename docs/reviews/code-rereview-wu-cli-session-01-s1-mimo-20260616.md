# Code Re-Review: WU-CLI-SESSION-01 S1 After Fix

## Scope

- Mode: focused re-review (controller-accepted findings only)
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-rereview-wu-cli-session-01-s1-mimo-20260616.md`
- Included scope: DS F-01, DS F-02（controller accepted findings）
- Excluded scope: 不重新扩大 scope；MiMo F-01（deferred）、MiMo F-02（rejected）不在此 review 范围内
- Parallel review coverage: 无

## Reviewed Artifacts

- Adjudication: `docs/reviews/code-review-wu-cli-session-01-s1-adjudication-20260616.md`
- Fix report: `docs/reviews/wu-cli-session-01-s1-fix-codex.md`

## Finding Status

### DS F-01: empty durable store list_sessions public boundary test

**状态: 已修复**

- **直接证据**:
  - `tests/host/test_public_session_api.py:619-628` — 新增 `test_list_sessions_empty_database_returns_empty_result`
  - 测试创建全新 `HostCommandHandle`（空 durable store），调用 `list_sessions(command_handle)`，断言 `result.sessions == ()`
  - 该测试直接验证 public read boundary：空库返回空元组，不抛异常
- **验证**: 测试通过（fix codex 报告 `28 passed`）

### DS F-02: joined slot alias decode fail-closed

**状态: 已修复**

- **直接证据**:
  - `dayu/host/durable/state.py:978-997` — `_slot_row_from_session_list_host_row` 已从 `_optional_text(row.get(...))` 改为 `_decode_optional_text(row, row_name=..., column=...)` 和 `_decode_optional_int(row, row_name=..., column=...)`
  - `_decode_optional_text`（`state.py:779-798`）调用 `_decode_scalar`（`state.py:737-754`），`_decode_scalar` 在 `HostRow.get()` 抛 `KeyError` 时捕获并转换为结构化 `HostRowDecodeError`，携带 `row_name` 和 `field_name`
  - `tests/host/test_public_session_api.py:631-649` — 新增 `test_session_list_slot_row_missing_alias_raises_row_decode_error`，构造缺少 `slot_scope` 列的 `HostRow`，断言 `_slot_row_from_session_list_host_row` 抛出 `HostRowDecodeError` 且 `field_name == "slot_scope"`
- **正常 LEFT JOIN 全空路径**: `state.py:1007-1008` — `if all(value is None for value in slot_values): return None` 仍然正确工作，因为 `_decode_optional_text` 对 SQL NULL 返回 `None`
- **部分为空路径**: `state.py:1009-1010` — `if any(value is None for value in slot_values): raise HostDurableError(...)` 仍然 fail closed
- **验证**: 测试通过（fix codex 报告 `28 passed`）

## Conclusion

**PASS**

两个 controller accepted findings 均已修复，有直接代码证据和回归测试覆盖。DS F-01 补齐了空库边界测试；DS F-02 将 slot alias 缺列错误从隐式 `KeyError` 升级为结构化 `HostRowDecodeError`，与现有 durable row decode 行为一致。

## Residual Risk

- 无阻断 S1 accepted slice 的 residual risk。
- MiMo F-01（N+1 query）按 adjudication deferred，不阻断 S1。
- MiMo F-02（pyright narrowing asserts）按 adjudication rejected，不阻断 S1。
