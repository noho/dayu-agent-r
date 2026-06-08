# WU-TOOLS-01-F01-01 Plan Review — AgentDS

## Verdict

**pass-with-findings**

0 blocking findings。3 accepted-candidate findings，均可由 implementation agent 在对应 slice 中自行处理，无需回到 plan gate。

---

## Plan Completeness Checklist

| # | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1 | Ingestion job store blocking lock 收敛 | PASS | Plan §8 明确替换 6 个 `_StoreFileLock` context manager 使用点，使用 `file_lock(path)` blocking acquire |
| 2 | Parent dir creation 语义 | PASS | `RuntimeFileLock.acquire()` 调用 `_prepare_parent_directory`（`dayu/runtime/filelock.py:167`），与 `_StoreFileLock.__enter__` 的 `mkdir(parents=True)`（`ingestion_runtime.py:1977`）等价 |
| 3 | 异常传播 | PASS | 阻塞 acquire 失败抛 `RuntimeFileLockError`，由调用方透出；Plan §8 明确"不包装成 Fins-specific error" |
| 4 | 生命周期语义 | PASS | Ingestion job store 使用 context manager；storage batch 使用手动 `token.release()` 跨 `begin_batch` 到 `commit/rollback` 持有 |
| 5 | Storage batch non-blocking acquire | PASS | Plan §8：`timeout_seconds=0` → 捕获 `RuntimeFileLockTimeoutError` → 映射为现有 `RuntimeError` |
| 6 | 同 ticker 跨进程 fail-fast | PASS | Plan §8 明确映射异常消息与现有一致；`_try_acquire_recovery_ticker_lock` 继续捕获 `RuntimeError` 返回 `None` |
| 7 | Timeout/busy 异常映射和用户可读错误 | PASS | Plan §8：`RuntimeError(f"ticker={ticker} 已存在跨进程活动 batch")` 保持不变；非 busy 的 `RuntimeFileLockError` 透出 |
| 8 | RuntimeFileLockToken 跨 begin→commit/rollback 生命周期 | PASS | Plan §8：`_ticker_lock_tokens: dict[str, RuntimeFileLockToken]` 私有状态；commit/rollback finally 中 release |
| 9 | Token 不进入 BatchToken | PASS | Plan §7 明确"runtime token 只存在于 `_FsStorageInfra` 私有状态"；`BatchToken.ticker_lock_path` 继续作为诊断字段 |
| 10 | 不修改 Host / Engine / ToolRuntime contract | PASS | Plan §2 Non-goals 与 §7 明确 |
| 11 | 不修改 Fins job schema | PASS | Plan §2 Non-goals |
| 12 | 不修改 storage protocol | PASS | Plan §2 Non-goals |
| 13 | 不修改 atomic replace | PASS | Plan §2 Non-goals，`_write_record_locked` / `_read_record_locked` 不改 |
| 14 | 无 Fins wrapper / facade | PASS | Plan §8 明确"不要新增 `_fins_store_file_lock()` 这类仅透传 helper" |
| 15 | 无兼容 re-export | PASS | Plan §9 Slice 3："不增加 `dayu/fins/filelock.py`、`dayu/fins/_runtime_filelock.py` 或 package-level re-export" |
| 16 | 无反向依赖 | PASS | `dayu.runtime` → `dayu.fins` 方向正确（基础设施 → 业务层） |
| 17 | Implementation slices 足够小且可独立验证 | PASS | 三 slice：Slice 1（ingestion job store）、Slice 2（storage batch）、Slice 3（删除死代码），每个有独立 completion signal 和 stop condition |
| 18 | Tests/validation 足够 | PASS | §10 明确 pytest 命令、pyright、git diff --check、coverage 命令和预期断言 |
| 19 | README 触发判断 | PASS | §11 评估 `dayu/fins/README.md` 和 `tests/README.md`，判断可能不需要更新或只需轻量更新 |
| 20 | Residual risks 分类 | PASS | R1-R5 全部有 owner/destination，无 unclassified risk |

---

## Design Alignment Verdict

**PASS** — Plan 完全对齐设计真源。

- `docs/host/design.md:63-65`：`dayu.runtime` 是层中立基础设施，业务层应优先复用。Plan 正确执行此约束。
- `docs/host/design.md:70`：filelock 用于普通文件互斥，不表达 Host durable truth。Plan 正确理解此边界。
- `docs/host/design.md:245-297`：`RuntimeFileLock` API shape、timeout semantics、第三方 import 边界。Plan 完全符合，包括 non-blocking `timeout_seconds=0`、异常包装、token release 幂等、不实现 stale takeover。
- `docs/engine/design.md:18-26`：Engine 不感知财报语义和文档存储。Plan 正确判断 Engine 代码和 contract 无需修改。
- `docs/host/issues-implementation-control.md:218`：Work unit 定义精确覆盖 Plan scope。Plan 的 goal/non-goal 与控制真源一致。

无设计偏差。

---

## Over-Design / Under-Design Assessment

**无过度设计**：
- 用已有公共 primitive 替换两处私有实现，不引入新抽象
- ticker-specific conflict 错误语义保留在 Fins 调用点，不进入 runtime
- Token 所有权限制在 `_FsStorageInfra` 私有状态，不扩大 `BatchToken` 或仓储协议
- 主动删除死代码，不保留兼容 re-export
- 不修改 Host/Engine/ToolRuntime contract、schema、atomic replace

**无欠设计**：
- 三 slice 均有明确 stop condition 和 completion signal
- 异常映射、生命周期、import boundary、测试迁移均有覆盖
- Residual risks 均已分类到 owner/destination

---

## Findings

### Finding F1 (Medium, accepted-candidate) — 锁机制从阻塞 flock 到非阻塞+重试的语义差异

**文件与行号**：
- 当前实现：`dayu/fins/ingestion_runtime.py:1980` — `fcntl.flock(stream.fileno(), fcntl.LOCK_EX)` (blocking)
- 当前实现：`dayu/fins/_file_lock.py:119-122` — `fcntl.flock(stream.fileno(), LOCK_EX | LOCK_NB)` (non-blocking + Windows retry)
- Plan 替换目标：`dayu/runtime/filelock.py:16` — `from filelock import FileLock`
- 第三方实现：`filelock/_unix.py` — `fcntl.flock(fd, LOCK_EX | LOCK_NB)` + 重试循环实现阻塞语义

**影响**：`filelock` 3.28.0 在 Unix 上使用非阻塞 `flock(LOCK_EX | LOCK_NB)` + 重试循环替代 `_StoreFileLock` 的阻塞 `flock(LOCK_EX)`。两种方式最终都通过同一 `fcntl.flock()` syscall 实现跨进程互斥，但：

1. 重试循环引入了 poll interval（默认 0.05s），可能导致高竞争时的微小延迟差异
2. `filelock` 额外处理了 NFS/FUSE ENOENT、sticky-bit EACCES、ENOSYS fallback 等边缘情况，这些是 `_StoreFileLock` 未处理的——实际上是改进

**为什么是当前 phase 范围内的问题**：Slice 1 直接替换 `_StoreFileLock`，implementation agent 应在替换后运行现有 job store 测试确认行为等价。

**建议修复方向**：Implementation agent 确认 `filelock` 的阻塞语义（`timeout_seconds=None` → `timeout=-1` → 无限重试）在 job store 的同一 `.store.lock` 路径上提供等价的跨进程互斥。Plan 已有 stop condition（Slice 1：如果 runtime blocking acquire 不能替代跨进程互斥，停止并提出扩展）。此 finding 是 **accepted-candidate**，无需修改 plan。

**裁决**：accepted-candidate — 由 implementation agent 在 Slice 1 验证。

---

### Finding F2 (Low, accepted-candidate) — `_release_ticker_lock` 显式 token 路径的 dict 清理歧义

**文件与行号**：
- 当前代码：`dayu/fins/storage/_fs_storage_infra.py:508` — `effective_stream = stream or self._ticker_lock_streams.pop(ticker, None)`
- 当前代码：`dayu/fins/storage/_fs_storage_infra.py:195` — begin_batch 异常路径 `_release_ticker_lock(normalized_ticker, stream=lock_stream)`，显式传 stream 时 dict 不 pop，留 stale 引用
- Plan §8：`_release_ticker_lock(ticker, *, token: RuntimeFileLockToken | None = None)` — "从显式 token 或内部 dict 取 token"

**影响**：当前代码已存在一个 latent 问题：`begin_batch` 异常路径中显式传 stream 时，`_ticker_lock_streams` dict 不会 pop，留一个指向已关闭 stream 的 stale 引用。实际危害低（异常向上传播，后续不会访问同 ticker）。Plan 的 token 设计自然可以修复此问题，但未明确说明显式 token 路径是否也要同步 pop dict。

**为什么是当前 phase 范围内的问题**：Slice 2 重写 `_release_ticker_lock` 时，implementation agent 需要决定：当显式 token 传入且 dict 中也有同 ticker 条目时，是否 pop dict。

**建议修复方向**：Implementation agent 应在 `_release_ticker_lock` 中无条件 pop `_ticker_lock_tokens.pop(ticker, None)`（即使显式传了 token），因为同一次 acquire 必定在 dict 中留下了条目。Plan 可以补充一句："显式 token 传入时也需从内部 dict pop 对应条目，防止泄漏"。

**裁决**：accepted-candidate — implementation agent 在 Slice 2 自行处理。

---

### Finding F3 (Low, accepted-candidate) — 文件描述符泄漏测试覆盖迁移缺口

**文件与行号**：
- 当前测试：`tests/fins/test_fins_ingestion_runtime.py:1166-1200` — `test_store_file_lock_closes_stream_when_flock_fails`，验证锁获取失败时文件描述符被关闭
- Plan §9 Slice 1 Tests："将旧 `_StoreFileLock` stream close 测试删除或迁移为 runtime filelock 已覆盖的 acquire failure / context release 测试"

**影响**：当前测试通过 `monkeypatch` + `os.fstat(captured_fd)` 验证 fd 泄漏。Plan 正确指出该测试可删除或迁移。但 `RuntimeFileLock` 的 acquire 失败路径（`dayu/runtime/filelock.py:168-174`）在 `_prepare_parent_directory` 成功但第三方 `acquire()` 抛异常时，不会泄漏 fd——因为 `FileLock._acquire()` 内部在 flock 失败时已经 `os.close(fd)`（见 `filelock/_unix.py` 的 except 分支）。即 fd 安全已由第三方库保证。

**建议修复方向**：删除 `test_store_file_lock_closes_stream_when_flock_fails` 时，在 commit message 中注明 fd 安全已由 `filelock` 库保证。无需新增等价测试。

**裁决**：accepted-candidate — implementation agent 在 Slice 1 处理。

---

## Validation Performed

### 只读验证

```bash
# Plan artifact whitespace check
git diff --check docs/host/wu-tools-01-f01-01-filelock-plan.md
# Result: 无 whitespace error

# 当前 Fins 私有锁引用扫描
rg -n "dayu\.fins\._file_lock|from dayu\.fins import _file_lock|_file_lock|_StoreFileLock|import fcntl" dayu tests -g '*.py'
# Result: 确认 2 处生产引用（ingestion_runtime.py, _fs_storage_infra.py）和 1 处私有实现（_file_lock.py）+ 测试引用

# 第三方 filelock import 边界
rg -n "from filelock import|import filelock" dayu -g '*.py'
# Result: 仅 dayu/runtime/filelock.py（符合设计真源约束）

# 验证 filelock 版本和底层机制
python -c "import filelock; print(filelock.__version__)"
# Result: 3.28.0（>= 3.18.0 要求满足）

# filelock Unix 实现确认使用 fcntl.flock + non-blocking retry
# 与 _StoreFileLock 的 blocking fcntl.flock 使用同一 syscall，语义等价
```

### 代码对照验证

| Plan 声明 | 代码验证 | 结论 |
|---|---|---|
| Ingestion job store 6 处 `_StoreFileLock` 使用 | `ingestion_runtime.py:704,726,757,805,843,862` — 6 处 `with _StoreFileLock(...)` | 一致 |
| `_StoreFileLock` 定义在 `ingestion_runtime.py:1945` | 确认，使用 `fcntl.flock(LOCK_EX)` + `LOCK_UN` | 一致 |
| Storage infra import `dayu.fins._file_lock` | `_fs_storage_infra.py:16` — `from dayu.fins import _file_lock as file_lock_module` | 一致 |
| Storage `_ticker_lock_streams` dict | `_fs_storage_infra.py:120` — `_ticker_lock_streams: dict[str, TextIO] = {}` | 一致 |
| Storage `_open_and_lock_stream` 非阻塞冲突映射 | `_fs_storage_infra.py:450-451` — `RuntimeError(f"ticker={lock_path.stem} 已存在跨进程活动 batch")` | 一致 |
| Storage recovery lock blocking acquire | `_fs_storage_infra.py:526` — `self._open_and_lock_stream(self._recovery_lock_path, blocking=True)` | 一致 |
| `_try_acquire_recovery_ticker_lock` 返回 None | `_fs_storage_infra.py:734-737` — 捕获 `RuntimeError` 返回 `None` | 一致 |
| BatchToken 有 `ticker_lock_path` 字段 | `document_models.py:143` — `ticker_lock_path: Path` | 一致，且是诊断字段 |
| RuntimeFileLock token release 幂等 | `runtime/filelock.py:91-105` — `if self._release_completed: return` | 一致 |
| RuntimeFileLock non-blocking timeout 包装 | `runtime/filelock.py:169-172` — `Timeout` → `RuntimeFileLockTimeoutError` | 一致 |
| RuntimeFileLock parent dir 创建 | `runtime/filelock.py:167` — `_prepare_parent_directory` | 一致 |
| Test `_StoreFileLock` 直接 import | `test_fins_ingestion_runtime.py:40` — `_StoreFileLock` | 需在 Slice 1/3 删除 |
| Test import boundary 第三方 filelock 约束 | `test_import_boundary.py:159-172` — 只允许 `dayu.runtime.filelock` | Plan 收敛后无需修改此约束 |

---

## Residual Risks and Uncovered Areas

| Risk ID | 描述 | Owner | Destination | 来源 |
|---|---|---|---|---|
| R1 | `RuntimeFileLockError` 非 `OSError`，部分 docstring 需更新 | Implementation agent | Slice 1/2 docstring 更新 | Plan §12 |
| R2 | Storage batch release failure type 从 `OSError` → `RuntimeFileLockError` | Implementation agent | Slice 2 tests + report | Plan §12 |
| R3 | `filelock.FileLock` reentrancy 细节不应被 tests 断言 | Implementation agent | Tests | Plan §12 |
| R4 | 如需更强的跨进程证明，是 runtime contract 覆盖问题，非 Fins wrapper 问题 | Plan review | 本 review finding 或 future runtime test slice | Plan §12 |
| R5 | 本 work unit 不实现 stale lock / crash recovery / lease / fencing | Future runtime/Host recovery | 非本 work unit | Plan §12; `docs/host/design.md:286-293` |
| R6 (new) | 跨进程 storage batch conflict 端到端测试是建议性而非阻塞性 | Implementation agent | Slice 2 — 按实际情况决定是否添加 | 本 review：非阻塞，runtime filelock 已有跨进程测试 |
| R7 (new) | `begin_batch` 异常路径中显式 stream 传参时 `_ticker_lock_streams` 不 pop 的 latent 问题 | Implementation agent | Slice 2 — token 设计自然修复 | 本 review Finding F2 |

无未分类 residual risk。

---

## Blocking Open Questions

**无。**

Plan 在当前证据下足以指导实现。所有 finding 均为 accepted-candidate，implementation agent 可在对应 slice 中自行裁决处理。

---

## Additional Notes

1. **正向发现**：`filelock` 3.28.0 在 Unix 上额外处理了 NFS/FUSE ENOENT、sticky-bit EACCES、ENOSYS fallback 等边缘情况（见 `filelock/_unix.py` `_acquire` 方法），这些是当前 `_StoreFileLock` 和 `dayu.fins._file_lock` 未处理的。收敛后跨平台鲁棒性实际**提升**。

2. **Plan 的 stop condition 设计合理**：两个 slice 都有明确 stop condition——如果 runtime filelock 公共契约不足以满足需求，不得在 Fins 中新增 wrapper，必须回到 runtime 公共契约扩展。这防止了"先凑合用 wrapper 绕过"的反模式。

3. **Slice 顺序正确**：先收敛简单的 ingestion job store（纯 context manager 替换），再处理复杂的 storage batch（token 生命周期管理），最后清理死代码。Slice 1 的完成可以作为 Slice 2 对 runtime filelock 能力的信心验证。

4. **`tests/runtime/test_filelock.py` 覆盖充分**：已有测试覆盖 parent dir 创建、context manager 正常/异常 release、嵌套拒绝、手动 release 幂等、non-blocking timeout 包装、release 失败重试、marker 恢复失败幂等。无需为本次 work unit 扩展 runtime filelock 测试。
