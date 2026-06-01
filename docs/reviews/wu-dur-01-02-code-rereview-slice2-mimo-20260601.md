# WU-DUR-01-02 Slice 2 Code Re-review - MiMo

## Conclusion

pass。

## Finding Status

### DS-C2-A: fixed

- **原始问题**: `_read_wal_size_bytes` 的 `OSError` 分支与 checkpoint PRAGMA failure 共用 `"Host durable WAL checkpoint failed"` 消息。
- **修复证据**: `dayu/host/durable/maintenance.py:124-126` — `OSError` 分支现在抛出 `HostDurableError("Host durable WAL checkpoint failed to read WAL file size")`，与 PRAGMA failure 的 `"Host durable WAL checkpoint failed"`（第 69 行）明确区分。
- **测试证据**: `tests/host/test_durable_connection.py` 新增 `test_wal_checkpoint_wal_size_stat_failure_has_precise_message`，使用 `monkeypatch` 仅对目标 WAL 文件 stat 注入 `PermissionError`，断言 `pytest.raises(HostDurableError, match="Host durable WAL checkpoint failed to read WAL file size")`。测试运行通过（22 passed）。

### DS-C2-B: fixed

- **原始问题**: checkpoint row length unexpected shape 与 no row 共用 `"Host durable WAL checkpoint returned no result"` 消息。
- **修复证据**: `dayu/host/durable/maintenance.py:74-77` — row length 不等于 3 时抛出 `HostDurableError("Host durable WAL checkpoint returned unexpected result shape")`，与 `row is None` 的 `"Host durable WAL checkpoint returned no result"`（第 71 行）明确区分。
- **测试评估**: 该分支在真实 SQLite `PRAGMA wal_checkpoint` 正常实现下不可达，需伪造 cursor 返回非 3 列 row 才能触发，会 over-mock SQLite correctness。fix artifact 已说明决策理由，字符串级改动风险极低，可接受不加 direct unit test。

## New Blocking Issues

none。

修复仅涉及两处错误消息字符串变更，不改变控制流、公共 API、checkpoint 语义或事务边界。`monkeypatch` 测试正确恢复 `_ORIGINAL_PATH_STAT`，未引入副作用。所有 22 个测试通过，pyright 零错误。

## Stop Status

rereview-complete。
