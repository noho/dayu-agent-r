# WU-RET-00 Slice 4 Code Review — AgentMiMo

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: code review
- slice: Slice 4 — opt-in orphan artifact reclaim
- agent: AgentMiMo
- artifact path: `docs/reviews/wu-ret-00-slice4-code-review-mimo.md`
- status: completed

## Review Target Files

| 文件 | 变更类型 |
|---|---|
| `dayu/host/durable/storage_lifecycle.py` | EDIT: 新增 `DurableArtifactFileError`、`DurableArtifactReclaimResult`、`reclaim_orphan_artifact_files` |
| `dayu/host/storage_maintenance.py` | EDIT: 新增 opt-in reclaim 路径、`_ArtifactPathReferenceChecker`、`_MaintenanceReclaimResult`、文件错误映射 |
| `tests/host/test_storage_maintenance.py` | EDIT: 新增 7 个 reclaim 测试用例 |
| `docs/host/design.md` | EDIT: 同步 maintenance boundary 描述 |
| `dayu/host/README.md` | EDIT: 同步 Storage Maintenance 章节 |
| `tests/README.md` | EDIT: 同步 test inventory |

## 审查维度与结论

### 1. Destructive Safety

**结论：PASS。**

- `reclaim_orphan_artifact_files` 逐候选调用 `is_artifact_path_referenced` recheck，仍被引用则跳过。
- 仅当 recheck 返回 `False` 后，才调用 Slice 1 `delete_artifact_file`。该函数执行 `_validate_relative_path_text` → `_validate_published_artifact_relative_path`（强制 `sha256/` namespace）→ `_path_from_posix_relative` → `_ensure_contained(artifact_root, final_path)` → `unlink`。
- `_ensure_contained` 使用 `resolve(strict=True)` 校验 symlink 逃逸，是 containment guard 的真源。
- `.tmp` 文件由 `iter_published_artifact_relative_paths` 在 `sha256/` namespace 遍历时跳过（`artifact.py:316` `if entry.name == _ARTIFACT_TEMP_DIR_NAME: continue`）。
- `audit/`、`tool-trace/` 等非 `sha256/` namespace 文件不进入 `iter_published_artifact_relative_paths` 枚举，因此不进入 orphan 候选。
- 不删除任何 SQLite row；`run_storage_maintenance` 不写 EventLog、不改 Session/Run 状态。

### 2. Recheck Callable 边界

**结论：PASS。**

- `_ArtifactPathReferenceChecker` 封装 `host._run_read(_ArtifactPathReferencedOperation(relative_path))`。
- `_ArtifactPathReferencedOperation.__call__` 在 read transaction 内调用 `artifact_relative_path_is_referenced(transaction, self.relative_path)`。
- `HostTransaction` 不泄漏到 `storage_lifecycle.py` 的 `reclaim_orphan_artifact_files` 边界外；该函数只接收 `Callable[[str], bool]`。
- 每个候选在独立 read transaction 中 recheck，符合 accepted plan 设计。

### 3. Reclaim 流程正确性

**结论：PASS。**

- `reclaim_orphan_artifact_files` 流程：遍历 candidates → recheck（True 则跳过）→ `delete_artifact_file` → `HostArtifactWriteError` 捕获转 `DurableArtifactFileError` → 成功则 `reclaimed_paths.append` → 失败则 `file_errors.append` + `continue`。
- 失败文件不进入 `reclaimed_paths`，正确。
- 删除失败后继续处理其它候选，正确。

### 4. Dry-run 默认行为

**结论：PASS。**

- `HostStorageMaintenanceRequest.reclaim_orphan_artifacts` 默认 `False`。
- `_reclaim_orphan_artifacts_if_requested` 在 `not request.reclaim_orphan_artifacts` 时返回 `reclaimed_paths=(), file_errors=()`。
- `HostStorageMaintenanceResult.reclaimed_artifact_paths` 在 dry-run 时为空元组。

### 5. DB Row 不变

**结论：PASS。**

- 代码不执行任何 `DELETE FROM` SQL（除了 test helper `_delete_payload_descriptor` 用于构造测试 fixture）。
- 不删除 payload descriptor、SQLite payload、EventLog 或 projection row。
- 测试 `test_storage_maintenance_dry_run_reports_candidates_without_deleting` 和 `test_storage_maintenance_reclaim_true_deletes_orphan_without_db_row_changes` 断言 `after_usage.event_log_rows == before_usage.event_log_rows` 和 `after_usage.payload_descriptor_rows == before_usage.payload_descriptor_rows`。

### 6. Residual TOCTOU 文档

**结论：PASS。**

TOCTOU 窗口在以下位置清楚记录，与 accepted plan §11 R1 一致：

- `reclaim_orphan_artifact_files` docstring（`storage_lifecycle.py:470-471`）："recheck 与 unlink 之间仍存在极短 TOCTOU 窗口；maintenance 默认 grace window、content-addressed artifact 可重写性与 containment 守卫共同降低风险。"
- `run_storage_maintenance` docstring（`storage_maintenance.py:244-247`）："recheck 与 unlink 之间仍存在极短 TOCTOU 窗口；默认 grace、content-addressed artifact 可重写性与 containment-guarded delete 用于降低风险。"
- `dayu/host/README.md` Storage Maintenance 章节："recheck 与 unlink 之间仍有极短 TOCTOU 窗口；默认 grace、content-addressed artifact 可重写性与 containment-guarded delete 用于降低风险。"

### 7. 测试覆盖

**结论：PASS。**

| 测试用例 | 覆盖场景 |
|---|---|
| `test_storage_maintenance_dry_run_reports_candidates_without_deleting` | dry-run 不删除、候选正确、物理 size、非 artifact 文件不被删、EventLog/Session/Run 状态不变 |
| `test_storage_maintenance_wal_checkpoint_true_returns_result` | WAL checkpoint 诊断 |
| `test_storage_maintenance_reclaim_true_deletes_orphan_without_db_row_changes` | opt-in 删除 orphan、被引用文件保留、DB row 不变 |
| `test_storage_maintenance_reclaim_keeps_shared_referenced_artifact` | 共享引用：一个 descriptor 删了但另一个仍引用同一物理文件 → 不进入候选 |
| `test_storage_maintenance_reclaim_recheck_hit_skips_delete` | recheck 命中（scan 后新 descriptor 引用）→ 跳过删除 |
| `test_storage_maintenance_reclaim_file_error_keeps_processing` | 单文件删除失败进入 `file_errors`、其它候选继续处理、`file_errors[0].json_value()` 正确 |
| `test_storage_maintenance_reclaim_is_idempotent` | 幂等：第二次 reclaim 无候选 |
| `test_open_host_async_handle_runs_storage_maintenance_dry_run` | async handle dry-run |
| `test_open_host_run_storage_maintenance_fails_after_close` | closed handle 错误语义 |

accepted plan Slice 4 测试要求全部覆盖：

- ✅ 回收后 orphan 物理文件消失，DB row 不变，被引用文件保留
- ✅ 共享引用文件不被回收
- ✅ recheck 命中跳过删除
- ✅ 删除失败进入 `file_errors`，其它候选仍可处理
- ✅ dry-run 文件不变、`reclaimed_artifact_paths` 为空
- ✅ 幂等：第二次无候选不抛错

### 8. 文档边界

**结论：PASS。**

- `docs/host/design.md` 只描述已实现的 opt-in reclaim，不越界到 scheduler/VACUUM/JSONL retention/SQLite orphan row deletion。
- `dayu/host/README.md` Storage Maintenance 章节明确列出非目标："不删除任何 SQLite row，不回收 SQLite orphan payload row，不执行 VACUUM、不启动 scheduler，也不处理 audit JSONL 或 tool-trace JSONL"。
- `tests/README.md` test inventory 准确反映当前测试覆盖。

### 9. AGENTS.md 合规

**结论：PASS。**

- 全部函数提供完整中文 docstring（参数、返回值、异常）。
- 类与模块提供中文概览 docstring。
- 严格类型：无 `Any`、`object`、无类型参数或无类型返回值。
- 无无理由 `getattr`/`hasattr`。
- 无兼容 facade。
- 无过度设计：opt-in reclaim 只添加最小必要的类型和函数。
- `pyright` 0 errors。

## Findings

| ID | Severity | File / Line | Finding | Status |
|---|---|---|---|---|
| F01 | info | `tests/host/test_storage_maintenance.py:309-353` | dry-run 测试调用了 `_write_non_artifact_files`（写 `.tmp`、`audit/`、`tool-trace/`），但未显式断言这些文件不进入 `orphan_artifact_candidates`。当前正确性由 `scan_orphan_artifact_files` 只遍历 `sha256/` namespace 保证，且 Slice 3 `test_storage_orphan_proof.py` 已覆盖 namespace 安全。测试设计可接受，但若 reviewer 认为应在 maintenance 测试中补充显式 namespace 断言，可作为 follow-up。 | accepted |

## Review 结论

**PASS**

- blocking findings: 0
- accepted findings: 1 (info)
- deferred findings: 0

Slice 4 实现与 accepted plan 完全对齐。destructive safety invariant 成立：只删除 recheck 仍 orphan、grace 外、`sha256/` namespace、containment 内的文件。recheck callable 通过 `host._run_read(...)` 执行，不泄漏 `HostTransaction`。删除失败结构化进入 `file_errors` 且继续处理。dry-run 默认不删除。DB row 不变。TOCTOU 残余在 docstring/README 清楚记录。测试覆盖全部 accepted plan 要求场景。文档只描述已实现 opt-in reclaim，不越界。AGENTS.md 合规。
