# WU-RET-00 Slice 2 Implementation — Codex

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: implementation
- slice: Slice 2 — read-only storage usage report
- agent: AgentCodex
- artifact path: `docs/reviews/wu-ret-00-slice2-implementation-codex.md`
- status: complete
- blocked: no

## 第一性原理判断

本 slice 的动机成立：长期运行 Host 需要 operator 可观测 storage usage，但该读面不能成为 cleanup、状态调度或 EventLog 写入路径。实现只读取 durable SQLite 与 DB/WAL 文件 `stat`，不扫描 artifact root、不 checkpoint、不删除、不写任何 Host 状态。

Engine 与本 slice 无接口耦合，本次未修改 `docs/engine/design.md`。DB VACUUM / SQLite space reclamation 仍 deferred 到 GitHub Issue 76。

## 改动摘要

- 新增 `HostStorageUsageReport` frozen/slots dataclass，所有字段为非负 `int`，提供稳定 `json_value() -> JsonValue`。
- 新增 `read_storage_usage(transaction, *, db_path)`，在 read transaction 内按 `HOST_DURABLE_TABLES` 全量逐表 `COUNT(*)`，并统计 SQLite payload logical bytes、artifact descriptor logical bytes、orphan SQLite payload count、DB/WAL 文件大小。
- `HostCommandHandle` 新增 `_db_path()` 单职责 typed accessor，避免向 facade 暴露 durable store internals。
- 新增 `report_storage_usage(host)` facade，经 `host._run_read(...)` 调 durable reader；错误映射沿用 command handle 现有 `_run_read` / `_db_path` 语义。
- `open_host` public async handle 新增 `report_storage_usage()`，先 closed guard，再委托 facade。
- `dayu.host` 包根导出 `report_storage_usage` 与 `HostStorageUsageReport`；`Host` Protocol 同步 async 方法，使用 type-checking-only import 避免 `api -> durable schema -> api` 循环依赖。
- 新增测试覆盖 fresh DB、payload/logical bytes、orphan SQLite payload、async handle、closed handle、`json_value()`。
- 最小同步 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`，仅描述已实现只读 report 边界。

## 修改文件

- `dayu/host/durable/storage_lifecycle.py`
- `dayu/host/storage_maintenance.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_storage_usage_report.py`
- `tests/host/test_package_exports.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-ret-00-slice2-implementation-codex.md`

## 字段清单

Row count 字段覆盖当前 `HOST_DURABLE_TABLES` 全量表：

- `event_log_rows`
- `idempotency_record_rows`
- `sqlite_payload_rows`
- `payload_descriptor_rows`
- `host_instance_rows`
- `host_session_rows`
- `host_session_slot_rows`
- `host_run_rows`
- `host_attempt_rows`
- `host_attempt_dispatch_record_rows`
- `host_wait_record_rows`
- `host_projection_checkpoint_rows`
- `host_projection_failure_rows`
- `host_run_result_rows`
- `host_session_timeline_item_rows`
- `host_memory_snapshot_rows`
- `host_memory_item_rows`
- `host_memory_diagnostic_rows`
- `host_audit_sink_marker_rows`
- `host_tool_trace_hot_rows`
- `host_outbox_terminal_item_rows`
- `host_outbox_drain_idempotency_rows`
- `host_purge_tombstone_rows`

Byte / diagnostic 字段：

- `sqlite_payload_logical_bytes`
- `artifact_descriptor_logical_bytes`
- `orphan_sqlite_payload_count`
- `db_file_bytes`
- `wal_file_bytes`

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_storage_usage_report.py -q`
  - passed: `5 passed in 0.29s`
- `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - passed: `28 passed in 1.64s`
- `source .venv/bin/activate && pyright dayu/host/durable/storage_lifecycle.py dayu/host/storage_maintenance.py dayu/host/command.py dayu/host/open_host.py dayu/host/__init__.py dayu/host/api.py tests/host/test_storage_usage_report.py`
  - passed: `0 errors, 0 warnings, 0 informations`

## README / Design 同步

- `docs/host/design.md`：新增 `report_storage_usage(host) -> HostStorageUsageReport` 公共只读诊断边界，明确不写 EventLog、不改变状态、不扫描 artifact root、不 checkpoint、不删除。
- `dayu/host/README.md`：在当前代码 public handle / facade 列表中加入 `report_storage_usage`，新增只读 report 小节。
- `tests/README.md`：Host 测试 inventory 加入 `test_storage_usage_report.py` 覆盖点。

## 未覆盖风险

- covered by later approved slice: artifact root 物理文件扫描、orphan artifact proof、orphan artifact deletion、maintenance dry-run / reclaim 与 WAL checkpoint entrypoint 属于 Slice 3/4，本 slice 未实现。
- tracked by existing issue: DB VACUUM / SQLite space reclamation 继续由 GitHub Issue 76 承接，本 slice 仅暴露 DB/WAL 文件大小诊断。
- deferred-with-owner: orphan SQLite payload 当前只报告计数，不删除 row；是否需要 DB row 回收路径由后续 retention work 决策。

## 非目标确认

本 slice 未实现 `run_storage_maintenance`，未遍历 artifact 文件，未执行 WAL checkpoint，未删除文件或 SQLite row，未修改 durable schema，未改变 Run / Attempt / Session 状态机。
