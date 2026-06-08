# WU-TOOLS-01-F01-01 Plan Review — AgentMiMo

## Verdict

**pass-with-findings**

Plan artifact `docs/host/wu-tools-01-f01-01-filelock-plan.md` is code-generation-ready。3 个 non-blocking findings，0 个 blocking findings。

## Findings

### F1 — `_release_ticker_lock` 参数签名变更未显式声明

- **严重性**：minor
- **文件路径 / 行号**：`dayu/fins/storage/_fs_storage_infra.py:494`；plan `docs/host/wu-tools-01-f01-01-filelock-plan.md:184`
- **影响**：`_release_ticker_lock` 当前签名为 `(self, ticker: str, *, stream: TextIO | None = None)`。Plan 要求将 `stream` 参数改为 `token: RuntimeFileLockToken | None`，但 plan 的 "Exact allowed changes" 只说"更新 … `_release_ticker_lock` 的局部变量和返回类型"，没有显式声明参数名从 `stream` 改为 `token`。
- **当前 phase 范围内**：是。参数签名属于 Slice 2 改动范围。
- **建议修复方向**：在 Slice 2 "Exact allowed changes" 中补充：`_release_ticker_lock` 参数 `stream` 改为 `token: RuntimeFileLockToken | None = None`。
- **裁决**：accepted

### F2 — `_StoreFileLock` stream 关闭语义变化需显式确认

- **严重性**：minor
- **文件路径 / 行号**：`dayu/fins/ingestion_runtime.py:1977-1983`；plan `docs/host/wu-tools-01-f01-01-filelock-plan.md:237-238`
- **影响**：旧 `_StoreFileLock.__enter__` 在 `fcntl.flock` 失败时显式 `stream.close()`（`dayu/fins/ingestion_runtime.py:1981-1983`）。`RuntimeFileLock.acquire()` 不打开 `TextIO`，因此该测试 `test_store_file_lock_closes_stream_when_flock_fails`（`tests/fins/test_fins_ingestion_runtime.py:1166`）的 fd 泄漏断言不再适用。Plan 正确要求删除该测试，但没有显式说明"fd 泄漏防护由 `RuntimeFileLock` 内部保证，不再由 Fins 代码承担"。
- **当前 phase 范围内**：是。行为变化在 Slice 1 范围。
- **建议修复方向**：在 Slice 1 completion signal 或 implementation report 中补充一行说明：`RuntimeFileLock.acquire()` 不打开 `TextIO`，fd 泄漏防护由第三方 `filelock.FileLock` 与 runtime wrapper 内部管理；旧 `_StoreFileLock` 的 stream 关闭测试语义不再适用。
- **裁决**：accepted

### F3 — `_fs_storage_infra` 覆盖率可能不足 80%

- **严重性**：minor
- **文件路径 / 行号**：`dayu/fins/storage/_fs_storage_infra.py`；plan `docs/host/wu-tools-01-f01-01-filelock-plan.md:396-397`
- **影响**：`_fs_storage_infra.py` 是 broad shared infra，包含路径解析、manifest 操作、handle 辅助等大量与本次 filelock 收敛无关的代码。Plan 已正确识别该风险（line 396-397），要求 implementation report 将覆盖率不足分类为 residual risk 而非降低标准。这是合理的处理方式。
- **当前 phase 范围内**：是。
- **建议修复方向**：无需修改 plan；implementation agent 应在 report 中如实记录覆盖率现状。
- **裁决**：accepted

## Plan Completeness Checklist

| 检查项 | 状态 |
|---|---|
| Ingestion job store blocking lock 覆盖 | pass |
| Parent dir creation 覆盖 | pass |
| Exception propagation（job store 透传 RuntimeFileLockError） | pass |
| Exception propagation（storage batch 映射 timeout → RuntimeError） | pass |
| Lifecycle — token 跨 begin_batch / commit_batch / rollback_batch 持有 | pass |
| RuntimeFileLockToken 不放进 public BatchToken | pass |
| Storage batch non-blocking acquire + 同 ticker fail-fast | pass |
| Recovery lock blocking acquire + finally release | pass |
| `_try_acquire_recovery_ticker_lock` skip live batch 语义 | pass |
| Host / Engine / ToolRuntime contract 不修改 | pass |
| Fins job schema 不修改 | pass |
| Storage protocol / BatchToken public shape 不修改 | pass |
| Atomic replace / json store 落盘语义不修改 | pass |
| 避免 Fins wrapper / facade / 兼容 re-export | pass |
| 避免 extra payload / 魔法兼容逻辑 | pass |
| Implementation slices 足够小且可独立验证 | pass |
| Tests/validation 覆盖充分 | pass |
| README 触发判断 | pass |
| Residual risks 全部分类到 owner/destination | pass |

## Design Alignment Verdict

**对齐**。

- `dayu.runtime` 层中立约束（`docs/host/design.md:63-65`）：plan 要求 Fins 复用 `dayu.runtime.filelock`，不在 Fins 中维护私有锁实现。
- `dayu.runtime.filelock` 语义边界（`docs/host/design.md:70, 245-298`）：plan 不引入 stale takeover、break lock、lease、fencing 或 recovery 语义。
- 第三方 `filelock` import 边界（`docs/host/design.md:295-297`）：plan 保持只有 `dayu.runtime.filelock` 直接 import 第三方 `filelock`。
- Engine 设计（`docs/engine/design.md:18-26`）：plan 不修改 Engine，正确识别 Fins storage batch 与 ingestion job store 均在 Engine 外部执行环境。
- 控制真源（`docs/host/issues-implementation-control.md:773-777`）：plan 完整对齐控制条目要求。

## Over-design / Under-design Assessment

**无过度设计，无不足设计**。

- Plan 用已有的 runtime 公共 primitive 替换两处私有实现，不引入新抽象层。
- Storage batch 的 ticker-specific conflict 语义保留在 Fins 调用点，不塞入 runtime filelock——这是正确的职责划分。
- Token 所有权保持在 `_FsStorageInfra` 私有状态，不扩大 `BatchToken` 或仓储协议。
- 删除死代码而非保留兼容 re-export。
- 不修改 Host / Engine / ToolRuntime contracts、durable schemas、job schemas、storage protocols。

## Validation Performed

| 验证 | 结果 |
|---|---|
| 读 `dayu/runtime/filelock.py` 确认 blocking acquire、non-blocking acquire、parent dir creation、context manager、token release 生命周期 | 满足 plan 所述能力 |
| 读 `dayu/fins/_file_lock.py` 确认 POSIX fcntl + Windows msvcrt 两套实现 | 确认为待删除的重复实现 |
| 读 `dayu/fins/ingestion_runtime.py:1945-2013` 确认 `_StoreFileLock` 定义与 6 个使用点 | 确认为待替换的 POSIX-only 私有锁 |
| 读 `dayu/fins/storage/_fs_storage_infra.py:120,169,195,257,291,369,374,425-474,476-511,513-526,620,648,678,693,721-737` 确认 storage batch lock 使用点与生命周期 | 确认 token 跨 begin/commit/rollback 持有，recovery lock finally release |
| 读 `tests/runtime/test_filelock.py` 确认覆盖 blocking/non-blocking/release lifecycle | 覆盖充分 |
| 读 `tests/runtime/test_import_boundary.py:159-172` 确认第三方 filelock import 边界测试 | 覆盖充分 |
| 读 `tests/fins/test_fins_ingestion_runtime.py:1166-1200` 确认 `_StoreFileLock` 专属测试 | 确认为需删除/迁移的测试 |
| 读 `dayu/fins/domain/document_models.py:120-144` 确认 BatchToken 不含 runtime token | 确认 plan 不修改 BatchToken |
| `git diff --check docs/host/wu-tools-01-f01-01-filelock-plan.md` | 无 whitespace error |

## Residual Risks and Uncovered Areas

| ID | 风险 | Owner | Destination |
|---|---|---|---|
| R1 | `RuntimeFileLockError` 不是 `OSError`，部分 docstring 只声明 `OSError` | implementation agent | Slice 1/2 docstring updates + pyright/test review |
| R2 | Storage batch release failure type 从 raw `OSError` 变为 `RuntimeFileLockError` | implementation agent | Slice 2 tests + implementation report |
| R3 | 不应断言 `filelock.FileLock` 同进程 reentrancy 细节 | implementation agent | tests must assert Fins public behavior |
| R4 | 若需更强跨进程 proof，属于 runtime contract 覆盖问题 | plan review | 已裁决：不阻塞当前 work unit |
| R5 | 不添加 stale lock detection / crash recovery / lease / fencing | future runtime/Host recovery | 不属于当前 work unit |

**无 unclassified residual risks。**

## Blocking Open Questions

None。
