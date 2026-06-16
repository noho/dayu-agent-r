# Code Re-Review — WU-CLI-SESSION-01 S1 DS Findings Fix

## Scope

- Mode: focused re-review（仅复核 adjudication 接受的 DS findings）
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-rereview-wu-cli-session-01-s1-ds-20260616.md
- Reviewed adjudication: docs/reviews/code-review-wu-cli-session-01-s1-adjudication-20260616.md
- Reviewed fix report: docs/reviews/wu-cli-session-01-s1-fix-codex.md
- Included scope（仅复核 accepted findings 的 fix）:
  - `dayu/host/durable/state.py` — `_slot_row_from_session_list_host_row` decode 路径
  - `tests/host/test_public_session_api.py` — 新增空库测试 + slot alias 缺列回归测试
- Excluded scope:
  - MiMo F-01（deferred-with-owner，不在本次复核范围）
  - MiMo F-02（rejected-with-reason，不在本次复核范围）
  - 其他非 S1 文件与未改动代码
- Parallel review coverage: 无

## Finding Status

### DS F-01 — empty durable store list_sessions public boundary test

- **裁决**: accepted
- **要求**: 补齐 fresh Host durable store 无 Session 时 `list_sessions` 返回 `ListSessionsResult(sessions=())` 的测试
- **状态**: **已修复**

**直接证据**:

`tests/host/test_public_session_api.py` 新增测试函数（diff 行 618-627）:

```python
def test_list_sessions_empty_database_returns_empty_result(tmp_path: Path) -> None:
    """list_sessions 在全新 durable store 上返回空 Session 元组。"""

    command_handle = _open_handle(tmp_path)
    try:
        result = list_sessions(command_handle)

        assert result.sessions == ()
    finally:
        command_handle.close()
```

- 入口: `list_sessions(command_handle)` — public facade
- 输入: 全新 `HostCommandHandle`，无任何 Session
- 断言: `result.sessions == ()` — 空元组，不抛异常
- 该测试在 fix report 验证中通过（28 passed，较原 26 增加 2 个新测试）

### DS F-02 — joined slot alias decode fail-closed / structured durable row decode boundary

- **裁决**: accepted
- **要求**: joined-slot 列解码在预期 alias 缺失时 fail closed，使用与已有 durable row decode 一致的结构化错误边界
- **状态**: **已修复**

**直接证据**:

`dayu/host/durable/state.py` `_slot_row_from_session_list_host_row` 函数（diff 行 969-1022）:

原实现使用裸 `_optional_text(row.get("slot_scope"), ...)` → 改为 `_decode_optional_text(row, row_name=row_name, column="slot_scope")`。全部 7 个 slot alias 列（`slot_scope`、`slot_slot_key`、`slot_session_id`、`slot_bound_event_id`、`slot_bound_event_sequence`、`slot_metadata_json`、`slot_updated_at`）均已改用 `_decode_optional_text` / `_decode_optional_int`。

`_decode_optional_text` 内部路径（`state.py:779-798`）: `_decode_scalar` → `row.get(column)` → 缺列时 `KeyError` → `HostRowDecodeError`。这提供了与原 review 要求一致的结构化 row decode 错误。

函数 docstring 已同步更新:
```
:raises HostRowDecodeError: slot alias 缺列或字段类型非法时抛出。
:raises HostDurableError: slot 字段只有部分为空时抛出。
```

回归测试 `tests/host/test_public_session_api.py`（diff 行 633-650）:

```python
def test_session_list_slot_row_missing_alias_raises_row_decode_error() -> None:
    """Session list slot join row 缺少预期 alias 时 fail closed。"""

    row = HostRow(
        columns=(
            "slot_slot_key",
            "slot_session_id",
            "slot_bound_event_id",
            "slot_bound_event_sequence",
            "slot_metadata_json",
            "slot_updated_at",
        ),
        values=(None, None, None, None, None, None),
    )

    with pytest.raises(HostRowDecodeError) as exc_info:
        _slot_row_from_session_list_host_row(row)

    assert exc_info.value.field_name == "slot_scope"
```

- 入口: `_slot_row_from_session_list_host_row(row)` — 内部 durable row decoder
- 输入: `HostRow` 缺少 `"slot_scope"` 列
- 断言: 抛出 `HostRowDecodeError`，`field_name == "slot_scope"`
- LEFT JOIN 全空正常路径（所有 slot alias 均为 NULL）仍返回 `None`，未被该 fix 破坏
- 部分为空路径仍抛 `HostDurableError("session slot left join row is incomplete")`，未被该 fix 破坏

## Conclusion

**PASS**

两个 accepted DS findings 均已修复，有直接代码证据和对应回归测试。无 residual risk 阻断 S1 accepted slice。

## Open Questions

无。

## Residual Risk

- 本次 fix gate 未处理 MiMo F-01（N+1 query / pagination）——已在 adjudication 中 `deferred-with-owner`，不属于 DS re-review scope。
- 本次 fix gate 未处理 MiMo F-02（pyright narrowing asserts）——已在 adjudication 中 `rejected-with-reason`，不属于 DS re-review scope。
