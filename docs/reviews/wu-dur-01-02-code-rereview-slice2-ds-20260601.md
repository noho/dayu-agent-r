# WU-DUR-01-02 Slice 2 Code Re-review - DS

## Scope

- **Mode**: focused re-review, DS-C2-A / DS-C2-B only
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Controller adjudication**: `docs/reviews/wu-dur-01-02-code-controller-adjudication-slice2-20260601.md`
- **Original DS review**: `docs/reviews/wu-dur-01-02-code-review-slice2-ds-20260601.md`
- **Fix artifact**: `docs/reviews/wu-dur-01-02-fix-slice2-codex-20260601.md`
- **Output file**: `docs/reviews/wu-dur-01-02-code-rereview-slice2-ds-20260601.md`

## Conclusion

**pass**

两个 accepted finding 均已修复，未引入新 blocking issue。

## Finding Status

### DS-C2-A: fixed

- **问题回顾**: `_read_wal_size_bytes` 的 `OSError` 分支与 checkpoint PRAGMA failure 共用 `"Host durable WAL checkpoint failed"`，调用方无法区分。
- **修复证据**:
  - `dayu/host/durable/maintenance.py:124-126`: `OSError` 分支已改为 `raise HostDurableError("Host durable WAL checkpoint failed to read WAL file size")`，与行 69 的 `sqlite3.Error` 分支消息 `"Host durable WAL checkpoint failed"` 明确区分。
  - `tests/host/test_durable_connection.py:198-237`: 新增 `test_wal_checkpoint_wal_size_stat_failure_has_precise_message`，通过 `monkeypatch.setattr(Path, "stat", fail_wal_stat)` 注入 `PermissionError` 并断言 `pytest.raises(HostDurableError, match="Host durable WAL checkpoint failed to read WAL file size")`，验证精确错误消息。
- **修复与 controller 要求一致**: controller 要求 `"Host durable WAL checkpoint failed to read WAL file size"`，实际字符串完全匹配。

### DS-C2-B: fixed

- **问题回顾**: row length 校验分支与 `row is None` 分支共用 `"Host durable WAL checkpoint returned no result"`，错误消息不精确。
- **修复证据**:
  - `dayu/host/durable/maintenance.py:75-77`: row length 校验分支已改为 `raise HostDurableError("Host durable WAL checkpoint returned unexpected result shape")`，与行 71 的 `row is None` 分支消息 `"Host durable WAL checkpoint returned no result"` 明确区分。
- **修复与 controller 要求一致**: controller 要求 `"Host durable WAL checkpoint returned unexpected result shape"`，实际字符串完全匹配。
- **测试说明**: 该分支在真实 SQLite 行为下不可达，未新增 direct unit test。fix artifact 对此有明确说明，controller 原始 review 中该 finding 严重程度为低，不构成 blocking gap。

## New Blocking Issues

none

## Stop Status

rereview-complete
