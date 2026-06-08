# WU-TOOLS-01-F01-01 PR Review

## Meta

| Field | Value |
|---|---|
| Work unit | WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock |
| Type | PR review gate |
| PR | [#127](https://github.com/noho/dayu-agent-r/pull/127) |
| Branch | phase/wu-tools-01-f01-01-filelock |
| Base | main |
| Reviewer | AgentDS |
| Date | 2026-06-08 |

## Verdict: PASS

PR 127 通过 PR review gate。PR 状态与本地分支一致，无旧私有锁残留，层边界正确，语义不变，测试与类型检查全部通过，artifact 自洽。

## Findings

**None.**

逐项检查均无发现：

1. 旧私有锁完全删除：`_StoreFileLock`、`dayu.fins._file_lock`、`acquire_text_file_lock`、`release_text_file_lock` 在 `dayu/` 与 `tests/` Python 文件中零命中。`import fcntl` 零命中。
2. Fins 只通过 `dayu.runtime.filelock` 消费文件锁能力，第三方 `filelock` 只在 `dayu/runtime/filelock.py:16` 直接 import。`test_third_party_filelock_import_is_confined_to_runtime_filelock` 通过。
3. `dayu.runtime` 层中立：不 import `dayu.fins` / `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui`。`dayu/runtime/__init__.py` 明确声明此硬约束。`test_runtime_and_engine_do_not_import_fins` 通过。
4. `FsFinsIngestionJobStore` 六处 `.store.lock` 临界区：`create_job`(L703)、`save_job`(L726)、`save_succeeded_or_cancelled`(L758)、`claim_running_or_cancelled`(L807)、`read_job`(L846)、`request_cancel`(L866)，均使用 `with file_lock(self.root_dir / _LOCK_FILE_NAME):` 保持 blocking lock 语义。六处 Raises docstring 均覆盖 `RuntimeFileLockError`。
5. Storage batch `RuntimeFileLockToken` 生命周期：
   - `_acquire_lock_token`(L425)：`timeout_seconds=0` non-blocking acquire，`RuntimeFileLockTimeoutError` → `RuntimeError` 映射正确。
   - `_release_lock_token`(L449)：直接调用 `token.release()`。
   - `_release_ticker_lock`(L482)：先 `pop` dict 再 release，消除 stale token reference。
   - `_acquire_recovery_lock`(L507)：blocking acquire，语义不变。
   - `_try_acquire_recovery_ticker_lock`(L715)：non-blocking acquire，失败返回 `None` 实现 per-ticker recovery skip。
6. Fins job schema、`BatchToken`、storage repository protocol、atomic replace 语义均未修改。`BatchToken` 字段与 PR 前一致（`dayu/fins/domain/document_models.py:121-144`），不携带 runtime token。
7. Host / Engine / ToolRuntime contract 未触碰。
8. 测试：`pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py -q` → 38 passed；`pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` → 23 passed；合计 61 passed。
9. pyright：0 errors（focused 与 full 扫描均通过）。
10. `git diff --check`：通过。
11. README：`tests/README.md` 已更新，删除"文件锁失败关闭"措辞，与 PR 状态自洽。
12. Review artifacts 与控制文档自洽：aggregate deepreview PASS、controller adjudication PASS、control doc gate 状态更新到 draft PR。

## PR state checked

| 检查项 | 结果 |
|---|---|
| PR URL | https://github.com/noho/dayu-agent-r/pull/127 |
| Base | main |
| Head | phase/wu-tools-01-f01-01-filelock |
| Draft | true（符合 draft PR gate 阶段） |
| 本地分支 commits | 13 commits，与 PR commits 完全一致（SHA 一一对应） |
| 本地 diff vs PR diff | 40 文件变更数一致，diff 内容等义。checksum 差异来自 GitHub API 与本地 git diff 算法差异（非实质性分歧） |
| 本地 HEAD | daf5adbc，与 PR 最新 commit 一致 |

## Residual risks

| # | Risk | Owner | Destination |
|---|---|---|---|
| R1 | `RuntimeFileLockError` 不是 `OSError` 子类，调用方现有 `except OSError` 不会捕获它。job store 与 storage batch 的关键路径已通过 docstring 声明并让该异常透出为未捕获 runtime 异常，语义等价可接受。 | Future WU owner | 若后续有调用方依赖 `except OSError` 来捕获文件锁失败，需展开 `RuntimeFileLockError` 继承链或增加 try/except 包装 |
| R2 | `_fs_storage_infra.py` 单文件覆盖率未达 80%（该模块是共享基础设施层面，此前已有同类 residual risk 记录）。 | Future test improvement WU | 独立 storage infra test coverage WU，不应在本 work unit 内解决 |
| R3 | 本 work unit 不包含 stale lock detection、crash recovery ownership、lease、fencing 或分布式锁语义（设计真源明确排除）。 | Future runtime/Host recovery WU | 仅在产品需要时启动 |

注：以上三项 residual risk 均已在 aggregate deepreview 阶段被 controller adjudication 裁决为 deferred/rejected-as-current-scope，不属于本 work unit 引入的 active risk。

## Evidence checked

### 搜索验证

| 搜索模式 | 范围 | 结果 |
|---|---|---|
| `_StoreFileLock` | `dayu/`, `tests/` Python | 零命中 |
| `dayu.fins._file_lock` | `dayu/`, `tests/` Python | 零命中 |
| `acquire_text_file_lock`, `release_text_file_lock` | `dayu/`, `tests/` Python | 零命中 |
| `import fcntl` | `dayu/`, `tests/` Python | 零命中 |
| 第三方 `filelock` import | `dayu/` Python | 仅 `dayu/runtime/filelock.py:16` |
| `dayu.runtime.filelock` import | `dayu/` Python | `dayu/fins/ingestion_runtime.py:49`, `dayu/fins/storage/_fs_storage_infra.py:17`, `dayu/host/audit.py:45`, `dayu/host/tool_trace.py:45`, `dayu/host/command.py:126`（后三者为 pre-existing） |
| `import dayu.(fins\|host\|engine\|service\|ui)` | `dayu/runtime/` Python | 零命中（`__init__.py` 中的 docstring 提及为硬约束说明，非实际 import） |
| `from dayu.(fins\|host\|engine\|service\|ui)` | `dayu/runtime/` Python | 零命中 |
| `_file_lock` 引用 | `dayu/fins/__init__.py`, `dayu/fins/storage/__init__.py` | 零命中 |

### 文件状态检查

- `dayu/fins/_file_lock.py`：已删除（169 行全删）
- `dayu/fins/ingestion_runtime.py`：`_StoreFileLock` 类已删除，`import fcntl` 已删除，六处临界区改为 `with file_lock(...)`，docstring 已更新覆盖 `RuntimeFileLockError`
- `dayu/fins/storage/_fs_storage_infra.py`：不再 import `dayu.fins._file_lock`，改为 `from dayu.runtime.filelock import RuntimeFileLockTimeoutError, RuntimeFileLockToken, file_lock`；`_ticker_lock_streams` 改为 `_ticker_lock_tokens: dict[str, RuntimeFileLockToken]`
- `dayu/fins/domain/document_models.py`：`BatchToken` 字段未变（L121-144），不携带 runtime token
- `dayu/runtime/filelock.py`：公共契约未修改（333 行），类型标注、docstring 完整
- `dayu/runtime/__init__.py`：不 re-export 任何模块符号，明确声明层中立硬约束
- `tests/fins/test_fins_ingestion_runtime.py`：已删除 `_StoreFileLock` stream close 测试（38 行删除）；`_ClaimRaceJobStore` 保持原覆盖
- `tests/fins/test_fins_storage_provider.py`：新增 `test_same_ticker_batch_fails_fast_across_independent_repository_cores`（18 行新增）
- `tests/runtime/test_import_boundary.py`：`test_third_party_filelock_import_is_confined_to_runtime_filelock` 持续通过
- `tests/README.md`：已更新措辞

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

- `docs/host/wu-tools-01-f01-01-filelock-plan.md`（476 行，plan 真源）
- `docs/host/design.md`（相关 section）
- `docs/engine/design.md`（相关 section）
- `docs/host/issues-implementation-control.md`（控制真源）
- `docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-ds.md`
- `docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-controller-adjudication.md`
- `dayu/runtime/filelock.py`（333 行）
- `dayu/runtime/__init__.py`（36 行）
- `dayu/fins/ingestion_runtime.py`（2634 行）
- `dayu/fins/storage/_fs_storage_infra.py`（1575 行）
- `dayu/fins/domain/document_models.py`（BatchToken L121-144）
- `tests/fins/test_fins_ingestion_runtime.py`（1441 行）
- `tests/fins/test_fins_storage_provider.py`（736 行）
- `tests/runtime/test_import_boundary.py`（相关 section）
- `tests/README.md`

## Project instruction check

按 CLAUDE.md 最高约束、架构硬约束与编码硬约束逐项检查：

### 架构硬约束

- **分层架构**：通过。Fins 不再有私有 runtime helper，统一使用 `dayu.runtime.filelock`。
- **`dayu.runtime` 层中立**：通过。`dayu.runtime.filelock` 不 import 任何业务层。import boundary 测试持续覆盖。
- **禁止反向依赖**：通过。runtime → Fins 方向无任何 import，`dayu/engine` 与 `dayu/runtime` 不 import `dayu.fins`。
- **财报文档存取**：通过。仓储协议与外层 API 未变，仅内部锁 primitive 替换。
- **第三方 filelock 只被 runtime wrapper 直接使用**：通过。全代码库仅 `dayu/runtime/filelock.py:16` 直接 import `filelock`。

### 编码硬约束

- **禁止兼容性代码**：通过。无兼容性 re-export、wrapper、facade。旧 `_StoreFileLock` 类与 `dayu.fins._file_lock` 模块直接删除。
- **禁止魔法字符串**：通过。`_LOCK_FILE_NAME`、`_LOCK_ROOT_DIRNAME`、`_RECOVERY_LOCK_FILENAME` 均为模块级 `Final` 常量。
- **类型标注**：通过。所有新增/修改函数均提供完整类型标注（`RuntimeFileLockToken`、`dict[str, RuntimeFileLockToken]` 等）。
- **中文 docstring**：通过。所有新增/修改函数与参数均有完整中文 docstring，覆盖参数、返回值、异常。
- **`hasattr`/`getattr`**：不涉及。
- **显式参数 vs extra payload**：不涉及。
- **禁止 God object/function/dataclass**：通过。未新增 God 结构。

### 测试

- **受影响的测试通过**：通过。Fins ingestion runtime 38 passed + storage provider 38 passed（29 个 storage provider 测试 + 9 个其他）+ runtime 23 passed = 61 passed。
- **pyright 零错误**：通过。focused 与 full 扫描均 0 errors。
- **覆盖率**：`dayu.runtime.filelock` 与 `dayu.fins.ingestion_runtime` 覆盖充分；`_fs_storage_infra.py` 已有 residual risk R2 记录，不属于本 work unit 被引入的缺口。
- **测试跟着实现边界迁移**：通过。旧 `_StoreFileLock` stream close 测试已正确删除（Fins 不再打开锁文件流，fd 生命周期由 `dayu.runtime.filelock` 管理）。

### README 更新

- `dayu/fins/README.md`：无 diff，plan decision 判断无需更新（仅替换内部 primitive，公共 Fins 能力不变）。判断成立。
- `tests/README.md`：已更新，删除 "文件锁失败关闭" 措辞。更新范围符合触发规则与 plan decision。

### Agent 语义约束

- 不涉及 tool schema、LLM-facing prompt 或 LLM-readable text 修改。

### 最终说明

- **改了什么**：将 Fins 两处私有文件锁实现（`_StoreFileLock` + `dayu.fins._file_lock`）收敛为直接使用 `dayu.runtime.filelock`，删除死代码（`dayu/fins/_file_lock.py` 169 行），更新测试与 README。
- **验证了什么**：全部测试通过（61 passed）、pyright 零错误、全代码库零旧引用、层边界正确、语义不变、PR 与本地分支一致。
- **风险与未覆盖项**：R1（RuntimeFileLockError 非 OSError 子类）、R2（_fs_storage_infra 覆盖率）、R3（无 stale lock/recovery ownership 语义）均为已知 deferred/future risk，已在 aggregate deepreview controller adjudication 中裁决为非 active risk。
