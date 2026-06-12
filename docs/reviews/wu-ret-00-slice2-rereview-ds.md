# WU-RET-00 Slice 2 F01 Fix Re-Review — AgentDS

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: re-review
- slice: Slice 2 read-only storage usage report
- reviewer: AgentDS
- artifact path: `docs/reviews/wu-ret-00-slice2-rereview-ds.md`
- review target: MiMo F01 fix as reported in `docs/reviews/wu-ret-00-slice2-fix-codex.md`

## Re-review Scope

仅验证 MiMo F01 fix，不重新审查 Slice 2 全部 target files。

Re-review target files:
- `dayu/host/storage_maintenance.py`
- `tests/host/test_storage_usage_report.py`
- `docs/reviews/wu-ret-00-slice2-fix-codex.md`

## Verification Evidence (独立复现)

- `pytest tests/host/test_storage_usage_report.py -q` → 7 passed in 0.29s
- `pyright dayu/host/storage_maintenance.py tests/host/test_storage_usage_report.py` → 0 errors, 0 warnings, 0 informations

与 fix report 一致。

## 逐项验证

### 1. F01 是否已修复

**判断：fixed。**

`dayu/host/storage_maintenance.py:29-36`：

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

- `OSError`（非 `FileNotFoundError`）从 `_file_size_bytes` → `Path.stat()` 透传到 `_ReadStorageUsageOperation.__call__` → `host._run_read()` → `report_storage_usage`，被 `except OSError` 捕获。
- 包装为 `HostApiError(code=INTERNAL_ERROR, retryable=False)`。
- `raise ... from exc` 保留异常链，`__cause__` 指向原始 `OSError`。
- docstring 已更新：`:raises dayu.host.api.HostApiError: durable 读取失败或 DB/WAL 文件 stat 失败时抛出。`

fix report 声称的 3 个改动点全部到位。

### 2. Durable `_file_size_bytes` 底层 OSError 语义是否保持不变

**判断：不变。**

`dayu/host/durable/storage_lifecycle.py:389-400`：

```python
def _file_size_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
```

- Fix 仅在 facade 层添加 `except OSError` 包装，未修改 `_file_size_bytes`。
- `_file_size_bytes` 仍只 catch `FileNotFoundError` 返回 0，其它 `OSError` 仍透传。
- docstring `:raises OSError: stat 发生非缺失类错误时透传` 未变。
- MiMo F06 "accepted" 裁决对应的底层语义完整保留。

### 3. Closed handle 行为是否被意外转换为 HostApiError INTERNAL_ERROR

**判断：未转换，行为正确。**

`report_storage_usage` 调用链：

1. `host._db_path()` → `self._raise_if_closed()` → 若已关闭，抛 `HostApiError(code=INVALID_STATE, message="Host command handle is closed", retryable=False)`
2. `host._run_read(operation)` → `self._transaction_runner()` → `_raise_if_closed()` → 同样抛 `HostApiError(INVALID_STATE, ...)`

`HostApiError` 不是 `OSError` 的子类（继承自 `Exception`），不会被 `except OSError` 捕获。closed handle 错误以 `HostApiError(INVALID_STATE, ...)` 形态直接传播给调用方。

`test_open_host_report_storage_usage_fails_after_close` 仍然通过，验证此路径未受影响。

### 4. 新增 monkeypatch 测试是否局部、typed、不泄漏状态

**判断：通过。**

`tests/host/test_storage_usage_report.py:435-476`：

- **局部性**：使用 pytest `monkeypatch` fixture，patch 作用于 `Path.stat`，测试结束后 pytest 自动恢复。未使用 `unittest.mock.patch` 或全局 monkeypatch。
- **类型正确**：
  - `stat_target: str` 参数来自 `@pytest.mark.parametrize`，通过 `_STAT_TARGET_DB` / `_STAT_TARGET_WAL` 常量注入。
  - `fail_selected_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result` 类型标注完整，与 `Path.stat` 签名兼容。
  - `original_stat` 保存原始 `Path.stat` unbound method，类型收窄正确。
- **状态不泄漏**：
  - `host.close()` 在 `try/finally` 中执行，确保 handle 释放。
  - monkeypatch 由 pytest 自动撤销，无手动 `setattr` 残留。
- **参数化覆盖**：分别对 DB 路径和 WAL 路径 mock stat 失败，两个子用例均断言 `HostApiError` + `INTERNAL_ERROR` + `retryable=False` + `__cause__ is expected_error`。
- **原始 stat 回退**：`fail_selected_stat` 对非目标路径调用 `original_stat`，不影响 `_run_read` 内其他可能需要 stat 的路径（实际无）。

### 5. 是否进入 Slice 3/4 scope

**判断：未进入。**

Fix 改动范围：
- `dayu/host/storage_maintenance.py`：仅添加 `except OSError` 包装，不涉及 artifact root 扫描、checkpoint、删除、WAL checkpoint。
- `tests/host/test_storage_usage_report.py`：仅新增 public facade OSError 包装测试，不创建 artifact 文件系统遍历、不调用 checkpoint、不删除文件或 row。

Fix report 明确声明"本 fix 不处理 controller 已拒绝为 blocking 的其它 review 项"和"本 fix 不进入 Slice 3/4 范围"。

## Adversarial Check

### 反向思考：`except OSError` 是否过宽？

`except OSError` 捕获 `report_storage_usage` 调用链中所有 `OSError` 子类。调用链分析：

| 调用点 | 可能的异常 | 备注 |
|---|---|---|
| `host._db_path()` | `HostApiError` (closed/durable error) | 不是 OSError，不被捕获 |
| `host._run_read()` → transaction runner | `HostDurableError` → `HostApiError` | 不是 OSError，不被捕获 |
| `_ReadStorageUsageOperation.__call__` → `read_storage_usage` → `_count_rows` 等 | `AssertionError` (invariant violation) | 不是 OSError，不被捕获 |
| `read_storage_usage` → `_file_size_bytes` → `Path.stat()` | `OSError`（非 FileNotFoundError） | **唯一的 OSError 来源** |

`FileNotFoundError` 被 `_file_size_bytes` 内部 catch 返回 0，不会到达 facade。因此 `except OSError` 实际只捕获 `_file_size_bytes` → `Path.stat()` 的非缺失类 `OSError`（如 `PermissionError`、`NotADirectoryError`）。范围精确，无意外吞异常风险。

### 反向思考：`retryable=False` 是否正确？

`Path.stat()` 失败的非缺失类 `OSError`（如 `PermissionError`）通常表示部署环境配置错误或文件系统权限问题，不是瞬时故障。重试不会自愈。`retryable=False` 正确。

## 裁决

**PASS**

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | F01 fixed | ✅ fixed |
| 2 | `_file_size_bytes` OSError 语义不变 | ✅ 不变 |
| 3 | Closed handle 未被意外转换 | ✅ 正确 |
| 4 | 新测试局部/typed/不泄漏 | ✅ 通过 |
| 5 | 未进入 Slice 3/4 scope | ✅ 未进入 |

- blocking finding count: **0**
- 无回归。
- 无需要更多证据的项。
