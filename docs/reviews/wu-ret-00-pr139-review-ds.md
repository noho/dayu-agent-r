# WU-RET-00 PR 139 Deep Review — DS

## Scope

- Mode: PR Review
- Repository: noho/dayu-agent-r
- PR: #139
- Title: WU-RET-00 Host storage lifecycle retention
- Author: noho (Leo Liu)
- Head branch: work/wu-ret-00-retention
- Base branch: main
- URL: https://github.com/noho/dayu-agent-r/pull/139
- Review date: 2026-06-12 13:02 UTC
- Output file: docs/reviews/wu-ret-00-pr139-review-ds.md
- Design truth sources: docs/host/design.md, docs/engine/design.md, docs/host/issues-implementation-control.md, docs/host/wu-ret-00-storage-lifecycle-retention-plan.md
- Included scope: PR 139 对 base main 的完整 diff（44 files, +8545/-10）
- Excluded scope: 无
- Parallel review coverage: 无（单 reviewer 沿关键路径逐行走读）

## PR Facts

| 项目 | 值 |
|---|---|
| PR number | 139 |
| Title | WU-RET-00 Host storage lifecycle retention |
| Author | noho (Leo Liu) |
| Head branch | work/wu-ret-00-retention |
| Base branch | main |
| State | OPEN, MERGEABLE |
| Commits | 12 (plan accept → plan record → slice 1–4 implementation + record + finalize + draft PR ready) |
| Files changed | 44 (+8545 / -10) |
| Key production files | `dayu/host/durable/artifact.py` (+106), `dayu/host/durable/storage_lifecycle.py` (+740 NEW), `dayu/host/storage_maintenance.py` (+586 NEW), `dayu/host/command.py` (+45), `dayu/host/open_host.py` (+37), `dayu/host/__init__.py` (+19), `dayu/host/api.py` (+36) |
| Key test files | `tests/host/test_artifact_store.py` (+118), `tests/host/test_storage_usage_report.py` (+582 NEW), `tests/host/test_storage_orphan_proof.py` (+316 NEW), `tests/host/test_storage_maintenance.py` (+751 NEW) |
| Docs changed | `docs/host/design.md` (+6/-2), `dayu/host/README.md` (+15/-1), `tests/README.md` (+1/-1), `docs/host/issues-implementation-control.md` (+46/-5), `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md` (+369 NEW) |
| Review gate artifacts | 38 review/fix/rereview/adjudication artifacts in docs/reviews/ |
| Related issue | #43 |

## Checks

| Check | Status |
|---|---|
| GitHub CI checks | **无 checks 报告**（`gh pr checks 139` 返回 "no checks reported on the 'work/wu-ret-00-retention' branch"） |
| pytest (93 tests) | **全部通过**（93 passed in 2.90s） |
| pyright | **0 errors, 0 warnings** |
| git diff --check | **通过**（PR body 确认） |

CI 未报告 checks 是已知状态——该分支可能未配置 GitHub Actions workflow，或 workflow 尚未对此分支触发。本地验证（pytest + pyright）已通过。

## Findings

### 001-未修复-中-`run_storage_maintenance` 同步阻塞 async event loop

- **入口/函数**: `open_host.py:_PublicHostHandle.run_storage_maintenance()` (line 525-542)
- **文件(行号)**: `dayu/host/open_host.py:525-542`, `dayu/host/storage_maintenance.py:233-299`
- **输入场景**: Service/UI 在 event loop 线程中调用 `await host.run_storage_maintenance(request)`，且 artifact root 包含大量文件（例如数千个 `sha256/` 文件）。
- **实际分支**: `_run_storage_maintenance` 是同步函数，内部执行 `physical_artifact_bytes()`（遍历整个 `sha256/` namespace 并对每个文件做 `stat`）和可选的 orphan 候选扫描、checkpoint。这些操作全都在 async 方法的调用线程中同步执行。
- **预期行为**: 长时间文件 I/O 不应阻塞 async event loop。理想情况下，文件遍历和 I/O 密集型操作应在专用线程或 executor 中运行。
- **实际行为**: maintenance 的所有文件 I/O（`iter_published_artifact_relative_paths` → 递归目录遍历 + stat，`delete_artifact_file` → unlink）在 async 上下文中同步执行，可能长时间阻塞 event loop。
- **直接证据**: `open_host.py:542` 调用 `_run_storage_maintenance(self._command_handle, request)`，这是一个同步函数；`storage_maintenance.py:233-299` 的 `run_storage_maintenance()` 内部执行文件系统遍历 (`_physical_artifact_bytes` → `iter_published_artifact_relative_paths` → 全量 `sha256/` 递归 + stat) 和可能的 orphan 文件删除。
- **影响**: 大 artifact root 时 event loop 阻塞增加，Service/UI 的其它并发操作（如 `watch_session_events` 的 event delivery）会被延迟。由于 maintenance 是显式 operator 工具，不是 hot command path，实际生产影响为中等。
- **建议改法和验证点**: 将文件 I/O 部分（`physical_artifact_bytes`, `scan_orphan_artifact_files`, `reclaim_orphan_artifact_files`）通过 `asyncio.to_thread` 或 `loop.run_in_executor` 卸载到线程池；或至少在 docstring/README 中显式说明"maintenance 在调用线程同步执行文件 I/O，大 artifact root 下建议在后台线程/进程调用"。若选择保持同步，需在 README 中记录该行为作为 operator 须知。
- **修复风险（低）**: 不影响核心安全逻辑（dry-run、recheck、containment 不依赖 async），只是执行位置变更。
- **严重程度（中）**: operator-facing tool 非 hot path，但 async 上下文中的同步阻塞 I/O 违反 async contract 最佳实践。

### 002-未修复-低-`DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS` 未从包根导出

- **入口/函数**: `dayu/host/__init__.py`
- **文件(行号)**: `dayu/host/__init__.py:102-109`, `dayu/host/storage_maintenance.py:37`
- **输入场景**: operator 想在构造 `HostStorageMaintenanceRequest(orphan_grace_seconds=<非默认值>)` 时引用具名常量而非硬编码数字。
- **实际分支**: `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS` 定义在 `storage_maintenance.py` 并从该模块 `__all__` 导出，但未列入 `dayu/host/__init__.py` 的 `__all__`。
- **预期行为**: 如果该常量是 operator 可能引用的具名默认值，应从包根导出供一致使用。
- **实际行为**: operator 必须从 `dayu.host.storage_maintenance` 子模块导入，或直接使用字面量 `3600.0`。
- **直接证据**: `dayu/host/__init__.py:102-109` 导入但不重新导出 `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`；`dayu/host/storage_maintenance.py:578` 在其 `__all__` 中包含它但包根未转发。
- **影响**: 轻微 ergonomics 不便，不影响正确性。
- **建议改法和验证点**: 若认定该常量属于公共面，在 `dayu/host/__init__.py` 的 import 和 `__all__` 中加入 `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`。
- **修复风险（低）**: 纯导出变更。
- **严重程度（低）**: 不影响 correctness/stability。

## Open Questions

- Q1: 是否需要为 `report_storage_usage` 和 `run_storage_maintenance` 增加端到端 `open_host` async handle smoke 测试？当前已有 `open_host` async handle 的单元测试（`test_open_host_async_handle_reports_storage_usage`、`test_open_host_run_storage_maintenance_dry_run`），但均使用空 DB。可以补充一个有真实 Session/Run/artifact 的完整 `open_host` async maintenance smoke。
- Q2: artifact root 下 `sha256/` namespace 外如有其他内容寻址 namespace（如未来可能的 `blake3/`），当前 `iter_published_artifact_relative_paths` 会排他性只遍历 `sha256/`。这是 plan 明确要求的安全约束，但若未来扩展 artifact digest 算法，需同步更新枚举逻辑。

## Residual Risk

- **R1 并发 maintenance**: 两个并发 `run_storage_maintenance(reclaim_orphan_artifacts=True)` 调用可能在重叠时间窗口内操作同一批候选文件。`delete_artifact_file` 使用 `unlink(missing_ok=True)` 且不将缺失文件视为错误，因此并发删除不会导致错误报告或文件系统损坏；但第二个调用的 `reclaimed_artifact_paths` 可能遗漏已被第一个调用删除的文件。当前未提供分布式锁或 fencing，考虑到 maintenance 是 operator 手动触发工具，该风险可接受。
- **R2 TOCTOU 残余**: recheck 与 unlink 之间的窗口已在代码、README、design doc 中显式文档化。由 grace window + content-addressed 可重写性 + containment 守卫共同降低风险。该风险理论上可被极长事务（大于 grace window）触发，生产环境中默认 3600s grace 应充足。
- **R3 CI checks 缺失**: GitHub 上该分支无 CI checks 报告。本地 pytest + pyright 已全部通过，但缺少自动化 CI 验证意味着后续 merge 前需手动确认。
- **R4 `DurableArtifactFileError` / `HostStorageMaintenanceFileError` 双层错误类型**: durable 层和 facade 层各有一份几乎同构的文件错误 dataclass（`DurableArtifactFileError` vs `HostStorageMaintenanceFileError`），facade 的 `_maintenance_file_errors()` 做逐字段复制转换。这增加了两个类型需要同步维护的负担。当前层级隔离（durable 不依赖 facade 类型）是合理架构选择，但若未来字段增加，需确保两边同步。不影响正确性。

## 结论

**PASS**

blocking finding 数量: **0**

PR 139 的 storage lifecycle retention 实现满足 correctness、stability 和 maintainability 要求：

- **architecture compliance**: 严格遵守 `UI -> Service -> Host -> Engine` 分层。新增模块 `storage_lifecycle.py`（durable 原语层）和 `storage_maintenance.py`（facade 层）无反向依赖，不使用 `dayu.service`/`dayu.ui`/`dayu.fins`/`dayu.engine`。
- **destructive artifact reclaim safety**: 三层防护——descriptor 全量引用集合（跨 Session）+ grace window + 逐文件 recheck——确保只删除真正 orphan 的文件。containment 守卫 (`_ensure_contained`) 防止越界删除。默认 dry-run。
- **PR body 与实现一致性**: PR body 描述的所有能力均已在代码中实现并验证。
- **review gate artifacts**: 38 个 gate artifacts（plan/review/fix/rereview/adjudication/aggregate deepreview）完整，记录了 WU-RET-00 从 plan 到 draft-PR-ready 的全过程。
- **docs 同步**: `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`、`docs/host/issues-implementation-control.md` 均已更新。
- **tests**: 93 tests passed；覆盖 usage report（空库、计数、logical bytes、orphan、DB/WAL stat、async handle、closed handle、json_value keys）、orphan proof（引用证明、共享引用去重、projection lag、namespace 安全、grace 过滤、物理 size）、maintenance（dry-run、opt-in reclaim、shared reference keep、recheck skip、file error continue、idempotent、async handle、closed handle）。
- **pyright**: 0 errors, 0 warnings。
- **residual risks**: 已文档化的 TOCTOU 窗口、并发 maintenance、缺失 CI checks、双层错误类型——均有明确缓解或 owner，非 blocking。
