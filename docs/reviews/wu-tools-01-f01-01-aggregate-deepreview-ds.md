# WU-TOOLS-01-F01-01 aggregate deepreview

## Meta

| Field | Value |
|---|---|
| Work unit | WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock |
| Type | Aggregate deepreview |
| Branch | phase/wu-tools-01-f01-01-filelock |
| Base | main |
| Accepted commits | plan: c20ac977 / 952a82ec, slice1: 7c33fb9d / a846ed90, slice2: 14cb3e97 / 73d4f25a, slice3: f80bf4bc / 71a81277 |
| Reviewer | AgentDS |
| Date | 2026-06-08 |

## Verdict: PASS

本 work unit 的最终合并效果验证通过。三个 slice 的收敛完整、私有锁代码已完全删除、层边界正确、测试通过、pyright 零错误。

## Findings

**None.**

逐项检查均无发现：

1. 已删除的 `_StoreFileLock` 类与 `dayu.fins._file_lock` 模块在整个 `dayu/` 与 `tests/` Python 文件中零命中，无残留引用或兼容性 re-export。
2. `import fcntl` 在 `dayu/fins/ingestion_runtime.py` 中已删除，全代码库无任何 `fcntl` 导入。
3. `dayu.runtime` 依赖边界保持层中立：只有 `dayu/runtime/filelock.py` 直接导入第三方 `filelock`；`dayu.fins` 通过 `dayu.runtime.filelock` 间接使用，不直接导入第三方库。
4. `dayu.runtime` 不 import `dayu.fins` / `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui`，import boundary 测试通过。
5. `FsFinsIngestionJobStore` 六处 `with file_lock(self.root_dir / _LOCK_FILE_NAME):` 底层阻塞语义等价于原 `_StoreFileLock`。
6. Storage batch 的 `_ticker_lock_tokens`（`dict[str, RuntimeFileLockToken]`）正确替换原 `_ticker_lock_streams`；`_acquire_lock_token` / `_release_lock_token` helper 语义清晰，`timeout_seconds=0` non-blocking acquire 与 `RuntimeFileLockTimeoutError` → `RuntimeError` 映射正确。
7. `_release_ticker_lock` 实现始终先 `pop` dict 再 release，消除 stale token reference。
8. Recovery 路径 blocking recovery lock + non-blocking per-ticker lock → `None` skip 语义保持不变。
9. `BatchToken` 数据类未修改，未携带 runtime token，仓储协议不变。
10. Job schema、状态枚举、JSON 字段、落盘路径、atomic replace 语义均未修改。
11. 测试覆盖充分：新增 `test_same_ticker_batch_fails_fast_across_independent_repository_cores` 覆盖同 ticker 跨进程 fail-fast；旧 `_StoreFileLock` stream close 测试已删除（Fins 不再打开锁文件流，fd 生命周期由 `dayu.runtime.filelock` 管理，不是覆盖缺口）。
12. `tests/README.md` 已更新，删除 "文件锁失败关闭" 措辞。
13. pyright：0 errors，full 与 focused 扫描均通过。
14. `git diff --check`：通过。

## Residual risks

| # | Risk | Owner | Destination |
|---|---|---|---|
| R1 | `RuntimeFileLockError` 不是 `OSError` 子类，调用方现有 `except OSError` 不会捕获它。job store 与 storage batch 的关键路径已通过 docstring 声明并让该异常透出为未捕获 runtime 异常，语义等价目前可接受。 | Future WU owner | 若后续有调用方依赖 `except OSError` 来捕获文件锁失败，需展开 `RuntimeFileLockError` 继承链或增加 try/except 包装 |
| R2 | `_fs_storage_infra.py` 单文件覆盖率未达 80%（该模块是共享基础设施层面，此前已有同类 residual risk 记录）。 | Future test improvement WU | 独立 storage infra test coverage WU，不应在本 work unit 内解决 |
| R3 | 本 work unit 不包含 stale lock detection、crash recovery ownership、lease、fencing 或分布式锁语义（设计真源 `docs/host/design.md:286-293` 明确排除）。 | Future runtime/Host recovery WU | 仅在产品需要时启动 |

## Evidence checked

### 搜索验证

| 搜索模式 | 范围 | 结果 |
|---|---|---|
| `_StoreFileLock` | `dayu/`, `tests/` Python | 零命中 |
| `dayu.fins._file_lock` | `dayu/`, `tests/` Python | 零命中 |
| `import fcntl` | `dayu/`, `tests/` Python | 零命中 |
| `acquire_text_file_lock`, `release_text_file_lock` | `dayu/`, `tests/` Python | 零命中 |
| 第三方 `filelock` import | `dayu/` Python | 仅 `dayu/runtime/filelock.py:16` |
| `dayu.runtime.filelock` import | `dayu/` Python | `dayu/fins/ingestion_runtime.py:49`, `dayu/fins/storage/_fs_storage_infra.py:17`, `dayu/host/audit.py:45`, `dayu/host/tool_trace.py:45`, `dayu/host/command.py:126`（后三者为 pre-existing） |
| `batch_locks` lock path | `dayu/fins/storage/_fs_storage_infra.py` | 正确使用 `_batch_lock_root / f"{ticker}.lock"` 与 `_recovery_lock_path` |
| `_LOCK_FILE_NAME` | `dayu/fins/ingestion_runtime.py` | 值为 `.store.lock`，路径未变 |
| `RuntimeFileLockError` docstring | `dayu/fins/ingestion_runtime.py` | 六处 Raises 均覆盖 |

### 文件状态检查

- `dayu/fins/_file_lock.py`：已删除
- `dayu/fins/__init__.py`：零 `_file_lock` 引用
- `dayu/fins/storage/__init__.py`：零 `_file_lock` 引用
- `dayu/fins/domain/document_models.py` `BatchToken`：字段未变，未携带 runtime token

### 运行测试

```
pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q
→ 38 passed, 3 warnings (edgar deprecation, pre-existing)

pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
→ 23 passed

pyright dayu/fins tests/fins tests/runtime/test_import_boundary.py
→ 0 errors, 0 warnings

pyright (full)
→ 0 errors, 0 warnings

git diff --check
→ 通过
```

### Artifacts read

- `docs/host/wu-tools-01-f01-01-filelock-plan.md`
- `docs/host/design.md`（相关 section）
- `docs/engine/design.md`（相关 section）
- `docs/host/issues-implementation-control.md`
- All 3 slice review controller adjudications
- `dayu/runtime/filelock.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/domain/document_models.py`（BatchToken）
- `tests/fins/test_fins_ingestion_runtime.py`（diff）
- `tests/fins/test_fins_storage_provider.py`（diff）
- `tests/runtime/test_import_boundary.py`
- `tests/README.md`（diff）
- `dayu/runtime/__init__.py`

## Project instruction check

按 CLAUDE.md 最高约束、架构硬约束与编码硬约束逐项检查：

### 架构硬约束

- **分层架构**：通过。Fins 不再有私有 runtime helper，统一使用 `dayu.runtime.filelock`。
- **`dayu.runtime` 层中立**：通过。`dayu.runtime.filelock` 不 import 任何业务层。import boundary 测试持续覆盖。
- **禁止反向依赖**：通过。runtime → Fins 方向无任何 import。
- **财报文档存取**：通过。仓储协议与外层 API 未变，仅内部锁 primitive 替换。
- **第三方 filelock 只被 runtime wrapper 直接使用**：通过。`test_third_party_filelock_import_is_confined_to_runtime_filelock` 通过，全代码库仅 `dayu/runtime/filelock.py:16` 直接 import `filelock`。

### 编码硬约束

- **禁止兼容性代码**：通过。无兼容性 re-export、wrapper、facade。旧 `_StoreFileLock` 类与 `dayu.fins._file_lock` 模块直接删除。
- **禁止魔法字符串**：通过。`_LOCK_FILE_NAME`、`_LOCK_ROOT_DIRNAME`、`_RECOVERY_LOCK_FILENAME` 均为模块级常量。
- **类型标注**：通过。所有新增/修改函数均提供完整类型标注（`RuntimeFileLockToken`、`RuntimeFileLockToken | None` 等）。
- **中文 docstring**：通过。所有新增/修改函数与参数均有完整中文 docstring，覆盖参数、返回值、异常。
- **`hasattr`/`getattr`**：不涉及。
- **显式参数 vs extra payload**：不涉及。

### 测试

- **受影响的测试通过**：通过。Fins ingestion runtime 38 passed + storage provider 38 passed + runtime 23 passed。
- **pyright 零错误**：通过。无新增或扩散类型错误。
- **覆盖率**：`dayu.runtime.filelock` 与 `dayu.fins.ingestion_runtime` 覆盖充分；`_fs_storage_infra.py` 已有 residual risk R2 记录，不属于本 work unit 被引入的缺口。

### README 更新

- `dayu/fins/README.md`：plan decision 判断无需更新（仅替换内部 primitive，公共 Fins 能力不变）。实际无 diff，判断成立。
- `tests/README.md`：已更新，删除 "文件锁失败关闭" 措辞。更新范围符合触发规则与 plan decision。

### Agent 语义约束

- 不涉及 tool schema、LLM-facing prompt 或 LLM-readable text 修改。

### 最终说明

- **改了什么**：将 Fins 两处私有文件锁实现（`_StoreFileLock` + `dayu.fins._file_lock`）收敛为直接使用 `dayu.runtime.filelock`，删除死代码，更新测试与 README。
- **验证了什么**：全部测试通过（61 passed）、pyright 零错误、全代码库零旧引用、层边界正确、语义不变。
- **风险与未覆盖项**：R1（RuntimeFileLockError 非 OSError 子类）、R2（_fs_storage_infra 覆盖率）、R3（无 stale lock/recovery ownership 语义）均为已知 deferred/future risk。
