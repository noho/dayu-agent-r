# WU-DUR-01 + WU-DUR-02 Implementation Slice 2 Report

## Gate / Scope

- **Gate**: WU-DUR-01 + WU-DUR-02 implementation
- **Slice**: Slice 2 - Internal WAL Maintenance Primitive And Read-stale Proof
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Role**: implementation specialist；只实现当前 slice，不重启完整 gateflow，不提交、不 push、不创建 PR。

## 动机判断

动机成立，且严重性未被高估。SQLite WAL checkpoint 是维护 / 诊断能力，不应成为 EventLog、state index、projection 或 recovery correctness 的前置条件；read transaction stale snapshot 是 SQLite WAL 模式下的真实隔离语义，需要直接测试证明同一长读内旧快照与新短读 fresh truth 的边界。

## Changed Files

- `dayu/host/durable/maintenance.py`
- `tests/host/test_durable_connection.py`
- `tests/host/test_durable_transaction.py`
- `dayu/host/README.md`
- `docs/reviews/wu-dur-01-02-implementation-slice2-codex-20260601.md`

未修改 `dayu/host/durable/transaction.py`；现有 WAL auto-checkpoint 常量 ownership 保持不变，因为本 slice 不需要移动常量即可满足计划约束。

## Implemented Items

- 新增 `dayu.host.durable.maintenance` 内部模块，模块 docstring 明确该 primitive 只服务 Host durable 内部 maintenance / test entry，不是 public maintenance API，不改变 EventLog correctness 前置条件。
- 新增 `HostWalCheckpointMode(StrEnum)`，包含 `PASSIVE = "PASSIVE"` 与 `TRUNCATE = "TRUNCATE"`。
- 新增 frozen slots dataclass `HostWalCheckpointResult`，字段为 `mode`、`busy_pages`、`log_pages`、`checkpointed_pages`、`wal_size_bytes`。
- 新增 `run_host_wal_checkpoint(connection, *, db_path, mode=PASSIVE)`：
  - 只执行 `PRAGMA wal_checkpoint(PASSIVE)` 或 `PRAGMA wal_checkpoint(TRUNCATE)`。
  - SQLite 无返回 row 时抛 `HostDurableError("Host durable WAL checkpoint returned no result")`。
  - SQLite 执行失败统一转为 `HostDurableError("Host durable WAL checkpoint failed")`。
  - `busy_pages > 0` 不抛错，作为诊断字段返回。
  - WAL 文件大小按 `db_path.with_name(db_path.name + "-wal")` 读取，不存在返回 `0`。
- 补充 PASSIVE checkpoint 结果字段可观测测试。
- 补充 closed connection checkpoint 失败结构化测试。
- 补充 checkpoint diagnostic 不改变 EventLog committed truth 的测试。
- 补充两个独立 configured connections 的 read-stale snapshot 测试：connection A 同一 read transaction 内保持旧快照；connection B commit 后，A 同一读仍旧；A commit 后新短读看到 fresh committed truth。

## Tests Run

- `source .venv/bin/activate && pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q`
  - Result: `21 passed in 0.31s`

## Pyright Result

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

已更新 `dayu/host/README.md` 的“低层与 Diagnostic 路径”条目，仅同步当前内部 durable 能力边界：read transaction 使用 SQLite snapshot 语义，新短读读取最新 committed truth；内部 WAL checkpoint primitive 只服务 diagnostic / test entry，不是 public maintenance API，也不作为 EventLog 或状态正确性前置条件。未把该 primitive 写成 Service-facing API。

## Plan Deviations

- 无功能偏离。
- 未移动 `dayu/host/durable/transaction.py` 中的 WAL auto-checkpoint 常量；计划允许“复用或移动常量 owner”，当前实现无复用需求，保持原 owner 是更小变更。

## Residual Risks Classification

- **fixed in current slice before review**: WAL checkpoint primitive、失败结构化、诊断字段可观测、checkpoint 不改变 EventLog truth、read-stale snapshot 直接证明均已覆盖。
- **covered by later slice in approved plan**: WU-DUR-02 的 idempotency 多进程、projection checkpoint CAS、memory snapshot + checkpoint CAS 并发矩阵缺口属于 Slice 3。
- **assigned to later phase/work unit**: 无。
- **tracked by existing issue**: 无。
- **requiring new issue or explicit user decision**: 无。

## Stop Status

- **completed**: 当前 slice 在允许文件范围内完成，未触发需要 public maintenance method、opener option、background scheduler、checkpoint correctness precondition 或 forbidden files 修改的停止条件。
