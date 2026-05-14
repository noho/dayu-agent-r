# Code Re-Review: Host P4-S4 Read APIs, Event Stream And Deferred Facade Behavior

- **Reviewer**: MiMo
- **Date**: 2026-05-14
- **Baseline**: previous review `gateflow-code-review-host-p4-s4-read-stream-deferred-mimo-20260514.md`
- **Review target**: workspace uncommitted diff (post-fix)
- **Fix target**: F-1 blocking finding — limit 校验先于 Run 存在校验

## Conclusion

**F-1 fixed. 0 blocking findings.**

`stream_run_events` 现在在 read transaction 内先校验 Run 存在（NOT_FOUND），再校验 limit（INVALID_STATE）。missing run + invalid limit 返回 NOT_FOUND，existing run + invalid limit 返回 INVALID_STATE。EventLog 扫描只在 Run 存在且 limit 合法后执行。DS low finding（default limit 测试使用硬编码 cursor 算术）已通过 `_max_scanned_event_sequence` helper 修正。无 scope creep。

## Fix Review

### F-1 Fix: limit 校验顺序

**变更文件**: `dayu/host/read_api.py:66-92, 147-188`

**变更内容**:

1. `stream_run_events` 函数体不再调用 `_resolve_stream_limit`；`limit` 以 `int | None` 直接传入 `_StreamRunEventsOperation`（L86-92）。
2. `_StreamRunEventsOperation.limit` 类型从 `int` 改为 `int | None`（L153）。
3. `_StreamRunEventsOperation.__call__` 内先执行 `read_run_by_id` 校验（L163-168），再调用 `_resolve_stream_limit`（L169）。

**契约验证**:
```
missing run + limit=-1  → NOT_FOUND   ✅ (was INVALID_STATE)
missing run + limit=0   → NOT_FOUND   ✅ (was INVALID_STATE)
existing run + limit=-1 → INVALID_STATE ✅ (unchanged)
existing run + limit=0  → INVALID_STATE ✅ (unchanged)
```

**EventLog 扫描安全性**: `read_events_after` 在 L170 执行，位于 Run 存在校验和 limit 校验之后。非法 limit 不触发数据库扫描。

### Collateral Changes

| 变更 | 文件 | 评估 |
|------|------|------|
| `_max_scanned_event_sequence` helper | `test_public_event_stream.py:147-180` | 按 EventLog scan-window contract 从 DB 读取期望 cursor，替代硬编码 `cursor + DEFAULT_LIMIT`。纯测试辅助，无生产代码影响。 |
| `test_stream_run_events_rejects_invalid_limits` 使用 existing Run | `test_public_event_stream.py:262-284` | 修正：确保 limit 校验在 Run 存在时仍生效。 |
| `test_stream_run_events_missing_run_invalid_limit_returns_not_found` | `test_public_event_stream.py:287-312` | 新增：覆盖 missing run + limit=0/-1/MAX+1 组合场景，直接验证 F-1 fix。 |
| `test_stream_run_events_default_limit_is_scan_window` 使用 `_max_scanned_event_sequence` | `test_public_event_stream.py:335-339` | DS low finding fix：从 DB 读取实际 scan-window 末尾 cursor，不再依赖 `cursor + DEFAULT_LIMIT == next_cursor` 的隐含假设。 |

### Scope 合规性

- 未修改 `command.py`、`__init__.py`、README 或其他生产文件。
- 未修改 P4-S3 cancel 语义。
- 未新增生产代码依赖。
- 测试从 200 增至 201（新增 1 个组合场景测试）。

## Validation Results

```
pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q  → 201 passed
python -m pyright dayu/host tests/host  → 0 errors, 0 warnings, 0 informations
git diff --check  → clean
```
