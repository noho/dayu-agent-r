# WU-RET-00 Slice 4 Implementation — AgentCodex

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: implementation
- slice: Slice 4 — orphan artifact 文件回收
- agent: AgentCodex
- artifact path: `docs/reviews/wu-ret-00-slice4-implementation-codex.md`
- status: completed

## 改动摘要

- `dayu/host/durable/storage_lifecycle.py`
  - 新增 `DurableArtifactFileError`、`DurableArtifactReclaimResult` 与 `reclaim_orphan_artifact_files(...)`。
  - 回收函数接收显式 `is_artifact_path_referenced(relative_path: str) -> bool` recheck callable，不把 `HostTransaction` 或 transaction factory 泄漏到 durable helper 外部边界。
  - 每个 candidate 删除前先 recheck；仍被引用则跳过，未被引用才调用 Slice 1 `delete_artifact_file` 做 containment-guarded delete。
  - 单文件 `HostArtifactWriteError` 转为 durable file error，失败文件不进入 `reclaimed_paths`，并继续处理其它候选。

- `dayu/host/storage_maintenance.py`
  - `run_storage_maintenance` 不再对 `reclaim_orphan_artifacts=True` fail fast。
  - 使用 Slice 3 candidates；opt-in 时通过 `_ArtifactPathReferenceChecker` 对每个 candidate 用 `host._run_read(...)` 执行 `artifact_relative_path_is_referenced` recheck。
  - 删除成功填充 `reclaimed_artifact_paths`；失败转换为 `HostStorageMaintenanceFileError(path, operation, message)` 并进入 `file_errors`。
  - dry-run 仍不删除，`reclaimed_artifact_paths=()`、`file_errors=()`。

- `tests/host/test_storage_maintenance.py`
  - 覆盖 opt-in 回收删除 orphan 物理文件但不改 DB row、被引用文件保留。
  - 覆盖 shared reference、删除前 recheck 命中、单文件删除失败继续处理、dry-run 不删除、连续两次回收幂等。

- 文档
  - `docs/host/design.md` 与 `dayu/host/README.md` 最小同步当前实现：默认 dry-run，显式 opt-in 回收 orphan artifact 物理文件。
  - `tests/README.md` 更新 Host storage maintenance 测试 inventory。

## Destructive Safety Invariants

- 只扫描并删除 artifact root 下 `sha256/` 内容寻址 namespace 的已发布 artifact 文件；audit JSONL、tool-trace JSONL、`.tmp` 和其它非 `sha256/` namespace 不参与候选。
- 删除前必须 recheck `payload_descriptors` 中是否仍存在同一 `artifact_relative_path` 的 `artifact_ref` descriptor；命中引用则跳过。
- 文件删除只通过 `delete_artifact_file` 执行，复用 Slice 1 namespace 与 containment 守卫。
- 单文件删除失败不静默吞掉，不进入成功删除列表，以结构化 `path` / `operation` / `message` 返回，并继续处理其它候选。
- 不删除任何 SQLite row；不处理 SQLite orphan payload row；不实现 scheduler、VACUUM、audit JSONL retention 或 tool-trace JSONL retention。
- residual TOCTOU：recheck 与 unlink 之间仍有极短窗口。当前通过默认 grace window、content-addressed artifact 可重写性、删除前 recheck 与 containment-guarded delete 降低风险。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_storage_maintenance.py -q`
  - 9 passed
- `source .venv/bin/activate && pytest tests/host/test_artifact_store.py tests/host/test_storage_usage_report.py tests/host/test_storage_orphan_proof.py tests/host/test_purge_session.py -q`
  - 56 passed
- `source .venv/bin/activate && pyright dayu/host/durable/storage_lifecycle.py dayu/host/storage_maintenance.py tests/host/test_storage_maintenance.py`
  - 0 errors, 0 warnings, 0 informations

## 未覆盖风险

- residual TOCTOU classified as tracked by current design: recheck 与 unlink 之间不能由当前朴素文件系统 delete 完全消除；本 slice 已按 accepted plan 通过 grace + recheck + content-addressed 可重写性 + containment 降低风险。
- SQLite orphan payload row 回收 classified as assigned to later work unit / existing issue scope: 本 slice 只报告、不删除 SQLite orphan payload row。
- SQLite space reclamation / VACUUM classified as tracked by existing Issue 76。
- Audit JSONL 与 tool-trace JSONL retention classified as assigned to WU-RET-02 / WU-RET-01。
