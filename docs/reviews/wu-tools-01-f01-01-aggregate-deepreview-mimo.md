# WU-TOOLS-01-F01-01 Aggregate Deepreview

## Verdict

**PASS**

## Summary

WU-TOOLS-01-F01-01 Fins filelock convergence 到 `dayu.runtime.filelock` 已完成。所有计划目标均已实现，无阻塞性发现。

## Findings

**None**

无阻塞性或非阻塞性发现。

## Evidence Checked

### 1. 旧锁实现删除验证

- `dayu/fins/_file_lock.py` 已删除（`ls` 确认文件不存在）
- `dayu/fins/ingestion_runtime.py` 中 `_StoreFileLock` 类已删除（diff 确认）
- `dayu/fins/ingestion_runtime.py` 不再 import `fcntl`（diff 确认）
- `dayu/fins/storage/_fs_storage_infra.py` 不再 import `dayu.fins._file_lock`（diff 确认）
- 全局 grep `_StoreFileLock|_file_lock|acquire_text_file_lock|release_text_file_lock` 在 `dayu/` 和 `tests/` 下零命中（grep 结果确认，仅 review 文档中存在历史引用）

### 2. Runtime filelock 使用验证

- `dayu/fins/ingestion_runtime.py:49` 正确 import `from dayu.runtime.filelock import file_lock`
- `dayu/fins/storage/_fs_storage_infra.py:17` 正确 import `from dayu.runtime.filelock import RuntimeFileLockTimeoutError, RuntimeFileLockToken, file_lock`
- 第三方 `filelock` 只在 `dayu/runtime/filelock.py:16` 中直接 import（`test_third_party_filelock_import_is_confined_to_runtime_filelock` 测试覆盖）

### 3. FsFinsIngestionJobStore 六处临界区验证

| 方法 | 行号 | 临界区 | RuntimeFileLockError docstring |
|---|---|---|---|
| `create_job` | 703 | `with file_lock(self.root_dir / _LOCK_FILE_NAME)` | ✓ |
| `save_job` | 726 | `with file_lock(self.root_dir / _LOCK_FILE_NAME)` | ✓ |
| `save_succeeded_or_cancelled` | 758 | `with file_lock(self.root_dir / _LOCK_FILE_NAME)` | ✓ |
| `claim_running_or_cancelled` | 807 | `with file_lock(self.root_dir / _LOCK_FILE_NAME)` | ✓ |
| `read_job` | 846 | `with file_lock(self.root_dir / _LOCK_FILE_NAME)` | ✓ |
| `request_cancel` | 866 | `with file_lock(self.root_dir / _LOCK_FILE_NAME)` | ✓ |

所有六处临界区语义等价：blocking acquire（`timeout_seconds=None`），context manager 自动 release，异常 docstring 覆盖 `RuntimeFileLockError`。

### 4. Storage batch 锁生命周期验证

- `_acquire_lock_token` (行 425-447)：blocking 模式用 `file_lock(lock_path).acquire()`，non-blocking 模式用 `file_lock(lock_path).acquire(timeout_seconds=0)`
- `RuntimeFileLockTimeoutError` 正确映射为 `RuntimeError(f"ticker={lock_path.stem} 已存在跨进程活动 batch")`（非阻塞竞争语义保持）
- `_release_lock_token` (行 449-462)：直接调用 `token.release()`
- `_acquire_ticker_lock` (行 464-480)：non-blocking acquire，token 缓存到 `_ticker_lock_tokens`
- `_release_ticker_lock` (行 482-505)：优先使用缓存 token，支持显式 token 参数
- `_acquire_recovery_lock` (行 507-520)：blocking acquire
- `begin_batch` (行 167-199)：acquire 在前，失败路径正确 release
- `commit_batch` (行 201-258)：finally 路径正确 release
- `rollback_batch` (行 260-293)：finally 路径正确 release
- `ensure_batch_recovery` (行 366-375)：recovery lock 在 try/finally 中正确 release
- `_recover_orphan_batch_dirs` (行 611-648)：per-ticker lock 在 try/finally 中正确 release
- `_recover_orphan_backup_dirs` (行 669-693)：per-ticker lock 在 try/finally 中正确 release
- `_try_acquire_recovery_ticker_lock` (行 712-737)：non-blocking acquire，竞争时返回 `None`

### 5. dayu.runtime 依赖边界验证

- `grep "from dayu\.(fins|host|engine|service|ui)" dayu/runtime/` 零命中
- `test_runtime_and_engine_do_not_import_fins` 测试覆盖
- `test_fins_import_boundaries_do_not_reverse_depend` 测试覆盖

### 6. 测试验证

```bash
# Fins 测试
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py -q
# 结果：38 passed, 3 warnings (edgar deprecation)

# Runtime 测试
pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
# 结果：23 passed

# Pyright 检查
pyright dayu/fins tests/fins tests/runtime/test_import_boundary.py
# 结果：0 errors, 0 warnings, 0 informations

# Full pyright
pyright dayu tests
# 结果：0 errors

# Git diff check
git diff --check
# 结果：通过
```

### 7. README 更新验证

- `tests/README.md` 已更新：移除 `_StoreFileLock` 测试描述（diff 确认）
- 触发规则：`tests/` 修改 -> 检查并按需更新 `tests/README.md`，已正确执行

### 8. Control doc / artifact 自洽性

- `docs/host/issues-implementation-control.md` 已更新：gate 改为 `aggregate deepreview`，active work unit 改为 `WU-TOOLS-01-F01-01`（diff 确认）
- `docs/host/wu-tools-01-f01-01-filelock-plan.md` 已创建（476 行），包含完整计划（diff 确认）
- Slice 1/2/3 各有 implementation、code review、fix、rereview artifact（文件列表确认）

## Residual Risks

**None**

本 work unit 的目标已完全实现，无剩余风险。

## Project Instruction Check

### 架构约束

- ✓ `dayu.runtime` 保持层中立，不 import 业务层
- ✓ 第三方 `filelock` 只在 `dayu.runtime.filelock` 中直接使用
- ✓ Fins 只消费 `dayu.runtime.filelock`，无私有锁实现
- ✓ 严格遵守分层架构：Fins 在 `dayu.fins`，runtime 在 `dayu.runtime`

### 类型约束

- ✓ pyright 零报错
- ✓ 禁止使用 `object`、`Any`、无类型参数（已检查）

### Docstring 约束

- ✓ 所有变更函数都有完整中文 docstring
- ✓ 异常 docstring 覆盖 `RuntimeFileLockError`

### 测试约束

- ✓ 测试覆盖关键行为（38 + 23 passed）
- ✓ 新增测试 `test_same_ticker_batch_fails_fast_across_independent_repository_cores` 覆盖跨独立仓储 core 的 fail-fast 语义
- ✓ 删除测试 `test_store_file_lock_closes_stream_when_flock_fails`（旧私有类测试）

### README 更新触发

- ✓ `tests/` 修改 -> `tests/README.md` 已更新

## Conclusion

WU-TOOLS-01-F01-01 aggregate deepreview 通过。所有计划目标已实现，无阻塞性发现，无剩余风险。可以进入下一个 gate。
