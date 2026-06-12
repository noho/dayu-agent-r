# WU-RET-00 Aggregate Deep Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `work/wu-ret-00-retention`
- Base: `main`
- Output file: `docs/reviews/wu-ret-00-aggregate-deepreview-mimo.md`
- Review date: 2026-06-12
- Covered commits: `a2f94be0`（plan accept）、`473f1e6d`（slice 1）、`9c044934`（slice 2）、`4691ad9b`（slice 3）、`f5b1cccd`（slice 4）及相关 gateflow bookkeeping commits

### Included scope

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `dayu/host/durable/artifact.py` | EDIT | 新增 `iter_published_artifact_relative_paths`、`delete_artifact_file` |
| `dayu/host/durable/storage_lifecycle.py` | NEW | durable 原语：`read_storage_usage`、`artifact_relative_path_is_referenced`、`collect_referenced_artifact_paths`、`scan_orphan_artifact_files`、`reclaim_orphan_artifact_files`、`physical_artifact_bytes`、`HostStorageUsageReport` |
| `dayu/host/storage_maintenance.py` | NEW | Host facade：`report_storage_usage`、`run_storage_maintenance`、`HostStorageMaintenanceRequest`/`Result`/`FileError` |
| `dayu/host/command.py` | EDIT | `_db_path()`、`_artifact_root()`、`_open_durable_connection()` typed accessors |
| `dayu/host/open_host.py` | EDIT | `_PublicHostHandle.report_storage_usage`、`run_storage_maintenance` async wrappers |
| `dayu/host/__init__.py` | EDIT | 包根导出新增类型与函数 |
| `dayu/host/README.md` | EDIT | 新增 Storage Usage Report / Storage Maintenance 小节 |
| `tests/README.md` | EDIT | 增补三个新测试文件覆盖点 |
| `docs/host/design.md` | EDIT | 增补 Host storage maintenance public boundary 设计说明 |
| `docs/host/issues-implementation-control.md` | EDIT | WU-RET-00 状态与 gate artifacts 更新 |
| `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md` | NEW | Accepted plan |
| `tests/host/test_artifact_store.py` | EDIT | 新增 slice 1 helper 测试 |
| `tests/host/test_storage_usage_report.py` | NEW | usage report 测试（7 tests） |
| `tests/host/test_storage_orphan_proof.py` | NEW | orphan proof 测试（5 tests） |
| `tests/host/test_storage_maintenance.py` | NEW | maintenance 测试（9 tests） |
| `tests/host/test_package_exports.py` | EDIT | 包导出测试更新 |
| `docs/reviews/`（多个） | NEW | 各 slice 的 plan/code review/re-review artifacts |

### Excluded scope

- `docs/engine/design.md`：Engine 无接口耦合，不读 Host durable store。
- `purge.py` 删除事务语义：本 WU 不改写 purge 的 SQLite 删除事务。
- Schema 文件：本 WU 无 schema 变更。
- GitHub Issue #43 / #76：issue tracking 不在 review 范围。

### Parallel review coverage

无。本次 aggregate review 由单一 reviewer 完成全量走读。

---

## Findings

未发现实质性问题。

以下是对重点风险的逐一走读结论：

### 1. Artifact 删除安全 — PASS

**走读路径**：`storage_lifecycle.py:reclaim_orphan_artifact_files` → `artifact.py:delete_artifact_file`

- `delete_artifact_file` 执行 `_validate_relative_path_text` → `_validate_published_artifact_relative_path` → `_path_from_posix_relative` → `_ensure_contained` → `unlink(missing_ok=True)`，完整走完 containment 守卫链。
- `_ensure_contained` 使用 `root.resolve(strict=True)` 和 `candidate.resolve(strict=True)` 后 `relative_to` 校验，能防御 symlink 逃逸。
- `_validate_published_artifact_relative_path` 强制路径必须在 `sha256/` namespace 下，杜绝非 artifact namespace 文件被删除。
- `iter_published_artifact_relative_paths` 跳过 `.tmp` 子树、非 `sha256/` 路径、symlink，只枚举 `sha256/` 下的普通文件。
- 测试覆盖：`test_artifact_store.py` 中 symlink 逃逸、越界路径被拒；`test_storage_orphan_proof.py` 中 `.tmp` / `audit` / `tool-trace` 不入候选；`test_storage_maintenance.py` 中被引用文件不被删除。

### 2. Orphan Proof 直接证据 — PASS

**走读路径**：`storage_lifecycle.py:artifact_relative_path_is_referenced`、`collect_referenced_artifact_paths`

- 引用证明只读取 `payload_descriptors` 中 `payload_kind='artifact_ref'` 且 `artifact_relative_path` 完全匹配的 descriptor。
- 不依赖 audit JSONL、tool-trace JSONL、EventLog payload JSON 或任何非 descriptor 事实。
- `collect_referenced_artifact_paths` 返回 `frozenset[str]`，`scan_orphan_artifact_files` 用 `on_disk - referenced` 做差集。
- 测试覆盖：`test_storage_orphan_proof.py` 中 descriptor truth 场景、shared descriptor 去重、projection lag 场景全部验证。

### 3. Shared Ref / Projection Lag / Recheck — PASS

**走读路径**：`storage_lifecycle.py:scan_orphan_artifact_files` → `reclaim_orphan_artifact_files`

- 共享引用：两个 descriptor 指向同一 content-addressed artifact 文件时，`collect_referenced_artifact_paths` 收集到该路径，`scan_orphan_artifact_files` 的 `on_disk - referenced` 差集中不包含它。
- Projection lag：descriptor 仍被 timeline / run_results / memory / tool_trace / outbox 引用，但 orphan proof 只看 `payload_descriptors` 表的 `artifact_relative_path` 列，不看下游引用。只要 descriptor row 存活，artifact 就不被标为 orphan。
- Recheck：`reclaim_orphan_artifact_files` 接收显式 `is_artifact_path_referenced` callable，每个候选删除前重开读事务复查。测试 `test_storage_maintenance_reclaim_recheck_hit_skips_delete` 模拟 scan 后新增 descriptor 场景，验证 recheck 跳过删除。

### 4. Dry-run 与 Destructive Reclaim 的 Opt-in 边界 — PASS

**走读路径**：`storage_maintenance.py:_reclaim_orphan_artifacts_if_requested`

- `HostStorageMaintenanceRequest.reclaim_orphan_artifacts` 默认 `False`。
- `_reclaim_orphan_artifacts_if_requested` 在 `request.reclaim_orphan_artifacts` 为 `False` 时返回空结果。
- 测试覆盖：`test_storage_maintenance_dry_run_reports_candidates_without_deleting` 验证 dry-run 不删除文件、不改变 DB row。
- 测试覆盖：`test_storage_maintenance_reclaim_true_deletes_orphan_without_db_row_changes` 验证 opt-in 删除 orphan 但保留被引用文件和 DB row。

### 5. DB/WAL Report/Checkpoint 行为 — PASS

**走读路径**：`storage_lifecycle.py:_file_size_bytes`、`storage_maintenance.py:_run_wal_checkpoint_if_requested`

- `_file_size_bytes` 用 `Path.stat().st_size`，`FileNotFoundError` 返回 0，其它 `OSError` 透传。
- WAL 路径通过 `_wal_path_for_db_path` 生成 `<db_path>-wal`。
- checkpoint 使用 `host._open_durable_connection()` 打开独立 connection，在 `finally` 中关闭，不在 command transaction 内执行。
- 测试覆盖：fresh DB 零计数、WAL 缺失为 0、stat OSError 被包装为 `HostApiError(INTERNAL_ERROR)`、checkpoint on/off 行为正确。

### 6. Public Facade Error Mapping — PASS

**走读路径**：`command.py:_host_api_error_from_durable_error`、`storage_maintenance.py:report_storage_usage`、`run_storage_maintenance`

- `report_storage_usage` 捕获 `OSError` → `HostApiError(INTERNAL_ERROR, retryable=False)`。
- `run_storage_maintenance` 捕获 `OSError` → `HostApiError(INTERNAL_ERROR)` 和 `HostDurableError` → `HostApiError(INTERNAL_ERROR)`。
- `HostCommandHandle._raise_if_closed()` → `HostApiError(INVALID_STATE)` → `open_host._PublicHostHandle._raise_if_closed()` → `HostClosedError`。
- 测试覆盖：closed handle 语义在 report 和 maintenance 两条路径都验证。

### 7. Host 分层边界 — PASS

**走读路径**：import 链检查

- `dayu/host/durable/storage_lifecycle.py` 只 import `dayu.host.durable.*` 和 `dayu.contracts.*`，不 import service / UI / Engine / runtime。
- `dayu/host/storage_maintenance.py` import `dayu.host.api`、`dayu.host.command`、`dayu.host.durable.*`，不 import service / UI / Engine / runtime。
- `dayu/host/command.py` 新增的 `_db_path()`、`_artifact_root()`、`_open_durable_connection()` 是 typed 私有 accessor，不引入 god bag，不泄漏 durable store 具体实现。
- `dayu/host/open_host.py` async wrapper 只委托同步 facade，不引入新的依赖方向。

### 8. AGENTS.md 类型/Docstring/README/Pyright 约束 — PASS

- 所有新增函数、类、模块均有完整中文 docstring，包含参数、返回值、异常说明。
- 所有类型使用 `frozen=True, slots=True`，无 `object`、`Any`、无类型参数。
- `pyright` 0 errors（已验证）。
- `README.md` 新增 Storage Usage Report / Storage Maintenance 小节，内容与实现一致。
- `tests/README.md` 增补三个新测试文件覆盖点。
- `docs/host/design.md` 增补 public boundary 设计说明。

### 9. 测试覆盖真实性 — PASS

- `test_storage_usage_report.py`（7 tests）：fresh DB 零计数、row count / logical bytes / orphan 计数正确、stat OSError 包装、async handle、closed handle、json_value 键集合稳定。
- `test_storage_orphan_proof.py`（5 tests）：descriptor truth、shared descriptor 去重、projection lag、namespace 安全、grace 过滤 + 物理 size。
- `test_storage_maintenance.py`（9 tests）：dry-run 不删文件、checkpoint on/off、opt-in 删除 orphan、共享引用保留、recheck 跳过、单文件错误继续、幂等、async handle、closed handle。
- `test_artifact_store.py`（16 tests）：原有 12 + 新增 4（枚举、删除、越界、symlink 逃逸）。
- `test_purge_session.py`（28 tests）：全绿回归，未改 purge 语义。
- 总计 50 tests passed, 0 failed。

### 10. Schema 同步校验 — PASS

**走读路径**：`storage_lifecycle.py:_assert_report_tables_cover_schema`

- `read_storage_usage` 入口调用 `_assert_report_tables_cover_schema()`，校验 `_REPORT_TABLES == HOST_DURABLE_TABLES`。
- `_HOST_DURABLE_TABLE_TO_REPORT_FIELD` 覆盖全部 23 张 durable table。
- 若 schema 新增表但 report 未同步，该校验会在运行时 `AssertionError`，不会静默遗漏。

---

## Open Questions

无。

所有风险已在 plan gate 中识别并通过实现闭环：

- Q1（包根是否需同时导出 `HostWalCheckpointMode` / `HostWalCheckpointResult`）：已确认导出，result 出现在 facade 返回类型上。
- Q2（report 是否纳入所有 Host durable table）：已确认纳入，通过 `_assert_report_tables_cover_schema` 运行时校验同步。

---

## Residual Risk

### R1: publish-before-commit 竞态（grace 缓解）

artifact 落盘先于 descriptor commit；若写入 commit 延迟超过 `grace_seconds`，理论上仍可能误删在途文件。缓解：默认 `grace_seconds=3600.0`、删除前 recheck、默认 dry-run、content-addressed 可重写性。operator 可按需调大 grace。此为设计文档已记录的残余尾部风险。

### R2: purge `cleanup_refs` 死字段（deferred）

`purge_session_durable` 仍计算 `cleanup_refs.artifact_relative_paths` 但永不消费。本 WU 用 maintenance 全量扫描取代逐路径文件清理。不影响正确性。后续清理项。

### R3: orphan SQLite payload row 回收未实现（deferred）

本 WU 只报告其计数，不删 row。理由：`write_sqlite_payload` 总在同一事务写 descriptor + payload，orphan 仅来自部分失败 / 未来 bug。后续按需决策。

### R4: DB VACUUM 未实现（deferred to Issue #76）

本 WU 只 checkpoint + size 诊断，不回收 DB 物理空间。

### R5: recheck per-candidate 事务开销

`reclaim_orphan_artifact_files` 对每个候选打开独立 read transaction 执行 recheck。在大量 orphan 场景下可能有事务开销。当前 grace window（3600s）和 content-addressed 机制限制了候选数量；若后续出现大量 orphan，可优化为单事务批量 recheck。

### R6: `_run_wal_checkpoint_if_requested` 中 connection 关闭与异常传播

若 `run_host_wal_checkpoint` 抛出异常，`finally` 块仍会关闭 connection。但若 `connection.close()` 本身抛异常，会掩盖原始异常。当前 SQLite `Connection.close()` 极少抛异常，风险极低。

---

## 结论

**PASS** — blocking findings 0。

WU-RET-00 全量变更实现了一个最小正确且安全的 Host storage lifecycle 底座：

1. **可观测**：operator 可通过 `report_storage_usage` 获取全量 durable table row count、payload logical bytes、orphan 诊断和 DB/WAL size。
2. **可证明的安全删除**：content-addressed-safe 引用证明原语 + 共享引用去重 + projection lag 安全 + grace window + recheck + containment 守卫，闭合了 purge 永久泄漏的 orphan artifact 文件。
3. **慢维护隔离**：maintenance 是独立显式 entrypoint，不在 command path 中执行，checkpoint 用独立 connection。

设计与实现严格对齐 plan、设计真源和总控文档。类型纪律、docstring 覆盖、测试覆盖、pyright 干净度和 README 同步均达标。所有 plan 识别的风险已有对应缓解措施或明确 deferred owner。
