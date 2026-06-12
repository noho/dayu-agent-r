# WU-RET-00 Slice 2 F01 Fix Re-Review — AgentMiMo

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: re-review
- slice: Slice 2 — read-only storage usage report
- agent: AgentMiMo
- artifact path: `docs/reviews/wu-ret-00-slice2-rereview-mimo.md`
- re-review target: fix report `docs/reviews/wu-ret-00-slice2-fix-codex.md`

## Re-Review Scope

验证 Codex 对 MiMo F01 的修复：

- `dayu/host/storage_maintenance.py`
- `tests/host/test_storage_usage_report.py`
- `docs/reviews/wu-ret-00-slice2-fix-codex.md`

## F01 Original Finding

`report_storage_usage` 是 Service-facing public API，DB/WAL `Path.stat()` 的非缺失类 `OSError`（如 `PermissionError`）不应以裸异常泄漏给调用方。应包装为 `HostApiError(code=HostApiErrorCode.INTERNAL_ERROR, retryable=False)` 并保留异常链。

## Verification Checklist

### 1. F01 Fix Correctness — ✅ FIXED

`storage_maintenance.py:29-36`：

```python
try:
    return host._run_read(_ReadStorageUsageOperation(db_path=host._db_path()))
except OSError as exc:
    raise HostApiError(
        code=HostApiErrorCode.INTERNAL_ERROR,
        message="Storage usage file stat failed",
        retryable=False,
    ) from exc
```

验证：
- ✅ `except OSError` 正确捕获所有 `OSError` 子类（含 `PermissionError`、`NotADirectoryError` 等）
- ✅ `code=HostApiErrorCode.INTERNAL_ERROR` 使用正确的结构化错误码
- ✅ `retryable=False` 正确——文件权限错误不是瞬态错误，重试无意义
- ✅ `from exc` 保留原始异常链，调用方可通过 `__cause__` 获取根因
- ✅ docstring 已更新，声明 `:raises dayu.host.api.HostApiError: durable 读取失败或 DB/WAL 文件 stat 失败时抛出`

### 2. Durable `_file_size_bytes` 底层 OSError 语义不变 — ✅ UNCHANGED

`storage_lifecycle.py:389-400`：

```python
def _file_size_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
```

- ✅ 仍只 catch `FileNotFoundError`，返回 0
- ✅ 其它 `OSError` 仍透传（docstring 声明 `raises OSError`）
- ✅ 修复点在 facade 层，不在 durable reader 层——符合 fix report 的第一性原理判断

### 3. Closed Handle 行为未被意外转为 INTERNAL_ERROR — ✅ SAFE

`report_storage_usage` 的 `except OSError` 不会捕获 `HostClosedError`：

- `HostClosedError` 继承自 `Exception`，不是 `OSError` 的子类
- `host._run_read()` 内部通过 `_raise_if_closed()` → `_transaction_runner()` 在进入 durable reader 之前检查 closed 状态
- `HostClosedError` 正常传播，不受 `except OSError` 影响

已有测试 `test_open_host_report_storage_usage_fails_after_close` 验证此行为。

### 4. 新增 monkeypatch 测试质量 — ✅ GOOD

`test_storage_usage_report.py:435-476`（`test_report_storage_usage_wraps_file_stat_os_error`）：

- ✅ **局部性**：使用 `monkeypatch.setattr(Path, "stat", ...)` 替换 `Path.stat`，monkeypatch fixture 保证测试结束后自动恢复
- ✅ **类型化**：`fail_selected_stat` 签名完整 `(self: Path, *, follow_symlinks: bool = True) -> os.stat_result`
- ✅ **参数化**：`@pytest.mark.parametrize("stat_target", (_STAT_TARGET_DB, _STAT_TARGET_WAL))` 分别覆盖 DB 和 WAL 两个路径
- ✅ **断言完整**：验证 `HostApiError.code`、`HostApiError.retryable`、`HostApiError.__cause__` 三个关键属性
- ✅ **状态不泄漏**：`finally: host.close()` 确保 handle 关闭；monkeypatch 自动还原 `Path.stat`
- ✅ **不干扰既有测试**：`fail_selected_stat` 只对 `failed_path` 抛错，其它路径调用 `original_stat`

### 5. 未进入 Slice 3/4 范围 — ✅ COMPLIANT

- ✅ 修复只改动 `storage_maintenance.py` 的 facade 错误处理
- ✅ 新增测试只验证 OSError → HostApiError 包装
- ✅ 未扫描 artifact root、未 checkpoint、未删除文件或 SQLite row
- ✅ 未实现 artifact orphan proof、retention policy、cleanup 或 DB VACUUM

## Verification Evidence

Controller independently verified:
- `pytest tests/host/test_storage_usage_report.py -q` → 7 passed ✓
- `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` → 28 passed ✓
- `pyright dayu/host/storage_maintenance.py tests/host/test_storage_usage_report.py` → 0 errors ✓

## Blocking Findings

0

## Conclusion

**PASS**

F01 已正确修复。`report_storage_usage` facade 现在将 DB/WAL `Path.stat()` 的非缺失类 `OSError` 包装为 `HostApiError(code=INTERNAL_ERROR, retryable=False)` 并保留异常链。durable reader 底层语义不变，closed handle 行为不受影响，测试局部、类型化、不泄漏状态。无 blocking regression。
