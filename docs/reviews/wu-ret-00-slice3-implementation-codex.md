# WU-RET-00 Slice 3 Implementation — Codex

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: implementation
- slice: Slice 3 — 删除证明只读原语 + maintenance dry-run
- agent: AgentCodex
- artifact path: `docs/reviews/wu-ret-00-slice3-implementation-codex.md`
- status: completed, not blocked

## 动机判断

本 slice 动机成立。Slice 1 已提供 `sha256/` namespace 的安全枚举，Slice 2 已提供只读 usage report；但在进入 destructive reclaim 前仍缺少内容寻址安全的 artifact path 引用证明和 operator-facing dry-run maintenance。直接按 descriptor 的 `artifact_relative_path` 做证明是必要的，因为同一物理 artifact 文件可被多个 payload descriptor 共享，不能用某个 payload_ref 的清理结果推断文件可删。

## 改动摘要

- `dayu/host/durable/storage_lifecycle.py`
  - 新增 `artifact_relative_path_is_referenced`、`collect_referenced_artifact_paths`。
  - 新增 `scan_orphan_artifact_files`，只扫描 `iter_published_artifact_relative_paths` 暴露的 `sha256/` namespace，按 `on_disk - referenced` 和 mtime grace 产生稳定排序候选。
  - 新增 `physical_artifact_bytes`，只统计已发布 `sha256/` artifact 文件，排除 `.tmp`、audit、tool-trace 与其它非 artifact namespace。
- `dayu/host/storage_maintenance.py`
  - 新增 `HostStorageMaintenanceRequest`、`HostStorageMaintenanceResult`、`HostStorageMaintenanceFileError` 与默认 grace 常量。
  - 新增 `run_storage_maintenance` dry-run facade。
  - `reclaim_orphan_artifacts=True` 当前 fail fast 为 `UNSUPPORTED_OPERATION`。
  - WAL checkpoint 使用独立 durable connection，关闭请求时返回 `None`。
- `dayu/host/command.py`
  - 新增 `_artifact_root()` 与 `_open_durable_connection()` 单职责 accessor，后者委托 `_durable_store.connect()` 并保持 closed guard / HostApiError 映射。
- `dayu/host/open_host.py`、`dayu/host/api.py`、`dayu/host/__init__.py`
  - 同步 async public handle、Host Protocol typing 和包根导出。
  - 包根导出 maintenance request/result/file-error、`run_storage_maintenance`、默认 grace 常量和 WAL checkpoint 类型。
- `tests/host/test_storage_orphan_proof.py`
  - 覆盖 descriptor truth、shared descriptor 去重、projection lag 下 descriptor 仍使 artifact referenced、namespace 安全、grace 过滤、稳定排序、物理 artifact size。
- `tests/host/test_storage_maintenance.py`
  - 覆盖 dry-run 不删除文件或 row、候选正确、physical bytes、checkpoint True/False、EventLog/Session/Run 状态不变、destructive reclaim fail fast、async open_host 入口与 closed handle。
- `tests/host/test_package_exports.py`
  - 同步 package export 和 Host Protocol public method 白名单。
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`
  - 只同步已实现 dry-run maintenance 边界，不写 deletion/reclaim 已实现。

## Dry-Run Invariants

- 不删除 artifact 文件。
- 不删除 SQLite row。
- 不执行 `VACUUM`。
- 不启动 scheduler。
- 不在 command transaction 内执行 WAL checkpoint。
- artifact orphan proof 只读取 `payload_descriptors` 中 `payload_kind='artifact_ref'` 的 `artifact_relative_path`。
- audit JSONL、tool-trace JSONL、`.tmp` 和非 `sha256/` namespace 文件不进入 orphan 候选。
- `reclaim_orphan_artifacts=True` 在本 slice fail fast，不进入扫描或删除流程。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py -q`
  - result: 10 passed
- `source .venv/bin/activate && pytest tests/host/test_storage_usage_report.py tests/host/test_artifact_store.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - result: 51 passed
- `source .venv/bin/activate && pyright dayu/host/durable/storage_lifecycle.py dayu/host/storage_maintenance.py dayu/host/command.py dayu/host/open_host.py dayu/host/api.py dayu/host/__init__.py tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py`
  - result: 0 errors, 0 warnings, 0 informations

## 未覆盖风险

- covered by later approved slice: destructive orphan artifact reclaim 仍未实现；当前只做 dry-run，`reclaim_orphan_artifacts=True` 明确 unsupported。
- covered by later approved slice: 删除前 recheck、containment delete 与 reclaim file error 的真实错误聚合属于 Slice 4。
- assigned to later work unit: SQLite orphan payload row 只报告不删除，保持 WU-RET-00 计划中“不删除 orphan SQLite payload row”的边界。
- assigned to later work unit: Audit JSONL 和 Tool Trace cold JSONL retention / rotation / size governance 仍分别属于 WU-RET-02 / WU-RET-01。

## Blocked

未 blocked。未发现需要 schema 变更的实现需求。
