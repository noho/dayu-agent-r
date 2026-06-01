# WU-DUR-01 + WU-DUR-02 Aggregate Deepreview

- **Gate**: aggregate deepreview
- **Role**: AgentMiMo
- **Branch**: `feat/wu-dur-bootstrap-concurrency` vs `main`
- **Date**: 2026-06-01
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`

## Verdict

**PASS — 无 blocking findings。**

实现严格对齐 plan 的 4 个 slice，correctness、stability、maintainability、Host 分层边界均通过验证。所有受影响测试通过，pyright 零报错。

## Changed Files Summary

| 文件 | 变更类型 | Slice |
|------|----------|-------|
| `dayu/host/durable/schema.py` | 修改：新增 `HOST_DURABLE_INDEXES`、`_bootstrap_fresh_schema`、`validate_host_durable_schema`、`_validate_required_tables`、`_validate_required_indexes`；重构 `bootstrap_host_durable_store` 三分支 | 1 |
| `dayu/host/durable/connection.py` | 修改：opener 路径对齐新 validation 命名；删除 `open_host_durable_store` 中冗余 post-bootstrap validation 调用 | 1 |
| `dayu/host/durable/maintenance.py` | 新增：WAL checkpoint 内部 maintenance primitive | 2 |
| `tests/host/test_durable_schema.py` | 修改：新增 7 个 bootstrap/validation 测试 + 2 个 DDL 一致性测试 | 1 |
| `tests/host/test_durable_connection.py` | 修改：新增 4 个 WAL checkpoint 测试 | 2 |
| `tests/host/test_durable_transaction.py` | 修改：新增 1 个 read stale snapshot 测试 | 2 |
| `tests/host/test_durable_concurrency_matrix.py` | 新增：4 个 concurrency matrix 缺口测试 | 3 |
| `dayu/host/README.md` | 修改：同步 durable foundation 描述 | 4 |
| `tests/README.md` | 修改：同步测试命令分组 | 4 |

## Findings (按严重性排序)

### F1 — LOW: `_stale_projection_checkpoint` monkeypatch 替身忽略 `transaction` 参数

- **严重性**: LOW (不影响 correctness)
- **文件**: `tests/host/test_durable_concurrency_matrix.py:730-747`
- **证据**: `_stale_projection_checkpoint(transaction, consumer_id, *, now)` 函数体 `del transaction, now` 后直接构造 stale `ProjectionCheckpointRow` 返回，不读取真实 DB state。
- **评估**: 这是计划中明确的 synthetic stale checkpoint 设计（plan 第 226-231 行）。monkeypatch 替身故意不读 DB，以确定性方式制造 CAS rowcount=0 前置条件。测试断言覆盖了错误消息、persisted checkpoint 不变和 snapshot rollback 三个事实。替身签名与 `ensure_projection_checkpoint` 签名一致，不会因签名漂移静默失效。
- **结论**: 设计意图正确，无需修改。

### F2 — LOW: `HOST_DURABLE_DDL` 保留 `CREATE ... IF NOT EXISTS` 与 current-version 不静默修复的表面矛盾

- **严重性**: LOW (不影响 correctness)
- **文件**: `dayu/host/durable/schema.py` (DDL statements), `schema.py:1253-1269` (bootstrap 分支)
- **证据**: `HOST_DURABLE_DDL` 中的 DDL 语句保留了 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`。plan 第 105 行已明确说明："DDL 仍可保留 `CREATE ... IF NOT EXISTS`，因为 fresh branch 只服务 `user_version == 0` 的新库；但 current branch 禁止执行 DDL，避免静默补齐。"
- **评估**: `bootstrap_host_durable_store()` 的 `current_version == HOST_SCHEMA_VERSION` 分支只调用 `validate_host_durable_schema(connection)`，不遍历 `HOST_DURABLE_DDL`。`_bootstrap_fresh_schema()` 是唯一执行 DDL 的路径，且只在 `user_version == 0` 时进入。DDL 中的 `IF NOT EXISTS` 不影响 current-version 行为。
- **结论**: plan 已预见并裁决，实现正确遵守。无需修改。

### F3 — LOW: `test_fresh_bootstrap_rolls_back_when_ddl_fails` 依赖 `isolation_level=None` 连接

- **严重性**: LOW (测试正确性有保障)
- **文件**: `tests/host/test_durable_schema.py:343-365`
- **证据**: 测试使用 `sqlite3.connect(db_path, isolation_level=None)` 创建连接，然后调用 `bootstrap_host_durable_store(connection)`。`_bootstrap_fresh_schema()` 内部执行 `BEGIN IMMEDIATE`，与 `isolation_level=None` 的 autocommit 模式一致。
- **评估**: 生产路径 `open_host_durable_store()` 通过 `_open_raw_connection()` 创建连接，也使用 `isolation_level=None`。测试与生产路径的 SQLite isolation 模式一致。monkeypatch 注入的 broken DDL (`"CREATE TABLE broken_schema_probe ("`) 确保 SQLite 抛出 `sqlite3.Error`，触发 rollback 路径。
- **结论**: 测试设计正确，与生产路径一致。

### F4 — INFO: read stale snapshot 测试中 connection B 的 transaction runner 使用默认 policy

- **严重性**: INFO (不影响测试有效性)
- **文件**: `tests/host/test_durable_transaction.py:449-515`
- **证据**: `test_read_transaction_keeps_stale_snapshot_until_commit` 中 connection B 的 `HostTransactionRunner` 使用 `options.sqlite_policy` 和 `options.payload_policy.payload_inline_threshold_bytes`，与 primary store 的 runner 配置一致。
- **评估**: 两个 runner 共享同一 `HostSQLiteStoragePolicy` 实例，busy retry 参数一致。这确保了 connection B 的写入行为与 primary store 的写入行为在 retry 语义上对齐。测试通过 runner_b 在 connection A 的 read transaction 内部执行写入，正确验证了 SQLite snapshot 隔离语义。
- **结论**: 配置正确，无需修改。

## Verification Checklist

### Correctness

- [x] fresh bootstrap DDL + `user_version` 在同一 `BEGIN IMMEDIATE` 事务内：`_bootstrap_fresh_schema()` 使用 `BEGIN IMMEDIATE` / DDL / `PRAGMA user_version` / `COMMIT`
- [x] DDL 中途失败 rollback 不留 partial schema：`test_fresh_bootstrap_rolls_back_when_ddl_fails` 验证 `user_version == 0` 且无用户表
- [x] current-version 缺 required table opener fail closed：`test_current_schema_missing_table_opener_raises_without_repair`
- [x] current-version 缺 required index opener fail closed：`test_current_schema_missing_index_opener_raises_without_repair`
- [x] secondary connection 缺 table/index fail closed：`test_secondary_connection_missing_table_raises_without_repair`、`test_secondary_connection_missing_index_raises_without_repair`
- [x] `HOST_DURABLE_INDEXES` 与 DDL 同源：`test_host_durable_indexes_match_create_index_ddl`
- [x] `HOST_DURABLE_TABLES` 与 DDL 同源：`test_host_durable_tables_match_create_table_ddl`
- [x] `HOST_DURABLE_INDEXES` 完整性：23 个 `INDEX_*` 常量全部包含，无遗漏
- [x] `HOST_DURABLE_TABLES` 完整性：23 个 `TABLE_*` 常量全部包含，无遗漏
- [x] WAL checkpoint PASSIVE 诊断字段可观测：`test_wal_checkpoint_passive_result_fields_are_observable`
- [x] WAL checkpoint closed connection 结构化错误：`test_wal_checkpoint_closed_connection_failure_is_structured`
- [x] WAL checkpoint stat failure 精确消息：`test_wal_checkpoint_wal_size_stat_failure_has_precise_message`
- [x] WAL checkpoint 不改变 EventLog truth：`test_wal_checkpoint_diagnostic_does_not_change_event_log_truth`
- [x] read stale snapshot 同事务保持旧快照：`test_read_transaction_keeps_stale_snapshot_until_commit`
- [x] 新短读事务看到 fresh truth：同上测试断言 `fresh_count == 2`
- [x] idempotency 同 key/same digest 多进程共享 winner：`test_idempotency_same_scope_key_same_digest_multiprocess_shares_winner`
- [x] idempotency 同 key/different digest 多进程只有一个 winner：`test_idempotency_same_scope_key_different_digest_multiprocess_conflicts`
- [x] projection checkpoint lost CAS 不推进 persisted checkpoint：`test_projection_checkpoint_lost_cas_keeps_persisted_checkpoint`
- [x] memory snapshot + checkpoint CAS failure rollback snapshot：`test_memory_snapshot_checkpoint_lost_cas_rolls_back_snapshot`

### Stability

- [x] `pytest tests/host/test_durable_schema.py -q` → 28 passed
- [x] `pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q` → 22 passed
- [x] `pytest tests/host/test_durable_concurrency_matrix.py -q` → 4 passed
- [x] `python -m pyright dayu/host/durable/schema.py dayu/host/durable/connection.py dayu/host/durable/maintenance.py` → 0 errors
- [x] `python -m pyright tests/host/test_durable_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_durable_concurrency_matrix.py` → 0 errors

### Maintainability

- [x] 所有新增函数/类有完整中文 docstring（参数、返回值、异常）
- [x] 无私有辅助函数嵌套
- [x] 无 `Any`、`object`、无类型参数/返回值
- [x] 无魔法数字/字符串（除 schema 工具内的 SQL 常量）
- [x] 无兼容性 wrapper / facade
- [x] `validate_host_schema_version` 已删除，无兼容性 re-export

### Host 分层边界

- [x] `maintenance.py` 模块 docstring 明确声明"只服务 Host durable 内部 maintenance / test entry，不是 Service-facing public maintenance API"
- [x] `run_host_wal_checkpoint()` 不在 opener、transaction runner、EventLog、projection、memory 或 scheduler 中自动调用
- [x] `maintenance.py` 不导出到 `dayu.host` 包根
- [x] `_bootstrap_fresh_schema()` 是唯一执行 `HOST_DURABLE_DDL` 的路径
- [x] secondary connection path (`store.connect()`) 不调用 bootstrap、不执行 DDL
- [x] 不修改 `docs/host/design.md` 或 control doc
- [x] 不新增 Host public API 或 Service-facing behavior 变化

### Durable Bootstrap 原子性

- [x] `_bootstrap_fresh_schema()` 使用 `BEGIN IMMEDIATE` 显式事务
- [x] DDL 失败时 best-effort `ROLLBACK` 后透传原始 `sqlite3.Error`
- [x] rollback 失败只做 best-effort suppress，不扩大 scope
- [x] 测试验证 rollback 后 `user_version == 0` 且无用户表

### Current Schema Validation

- [x] `validate_host_durable_schema()` 校验 `user_version`、required tables、required indexes
- [x] 不执行 DDL、不尝试迁移或修复
- [x] 缺 table/index 时抛 `HostSchemaMismatchError`，包含具体对象名
- [x] primary opener 不做双重 full validation

### WAL Maintenance Primitive

- [x] `maintenance.py` 新增，含 `HostWalCheckpointMode`、`HostWalCheckpointResult`、`run_host_wal_checkpoint()`
- [x] 只允许 `PASSIVE` 或 `TRUNCATE` 模式
- [x] `busy_pages > 0` 不抛错，返回 diagnostic
- [x] `wal_size_bytes` 通过 `-wal` 文件读取，不存在返回 `0`
- [x] 不在任何生产热路径中自动调用

### Read Stale 语义

- [x] 同一 read transaction 内保持旧快照（connection B commit 前后 count 不变）
- [x] 新短 read transaction 看到 fresh truth
- [x] 不要求改 production code

### Concurrency Matrix

- [x] EventLog append 多进程：closed by evidence，不重复覆盖
- [x] ensure_session 多进程：closed by evidence，不重复覆盖
- [x] liveness update：closed by evidence，不重复覆盖
- [x] idempotency 同 key/same digest 多进程：新增测试
- [x] idempotency 同 key/different digest 多进程：新增测试
- [x] projection checkpoint lost CAS：新增 monkeypatch 测试
- [x] memory snapshot + checkpoint CAS rollback：新增 monkeypatch 测试
- [x] rollback failure：non-goal，不纳入

### Tests/README 同步

- [x] `dayu/host/README.md`：更新 durable foundation 描述，新增 read transaction snapshot 语义和 WAL checkpoint primitive 说明
- [x] `tests/README.md`：更新测试命令分组，新增 `test_durable_concurrency_matrix.py`、`test_durable_connection.py` 相关命令行
- [x] 不触发根目录 `README.md`、`dayu/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md` 更新

## Open Questions

none。

所有 plan 中的 blocking open questions 已在实现中关闭。non-blocking 项（DDL `IF NOT EXISTS` 保留、`validate_host_durable_schema` 不做 DDL text diff、idempotency multiprocess timing、DDL text 表面矛盾）均已在 findings 中裁决。

## Residual Risks

| 风险 | 分类 | 说明 |
|------|------|------|
| `validate_host_durable_schema()` 只校验 required table/index existence，不做 full SQL DDL text diff | deferred-to-WU-LAYER-01 | plan 已明确：DDL text drift 可作为后续 schema invariant hardening |
| SQLite `PRAGMA wal_checkpoint(PASSIVE)` 在本地测试中未必稳定返回 `busy_pages > 0` | accepted | 测试只断言 diagnostic 字段可观测、非负，不依赖具体 busy 数值 |
| 新增 idempotency multiprocess tests 在极慢机器上可能 timing flake | low | 使用 start gate + finite retry + result files，与现有 multiprocess smoke 同类 |
| `HOST_DURABLE_DDL` 保留 `IF NOT EXISTS` 可能引起 reviewer 疑虑 | accepted | plan 已裁决：fresh branch 是唯一执行 DDL 的路径，current branch 不执行 DDL |

## Verification Commands

需补跑的验证命令（当前已全部通过）：

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py -q
pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q
pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q
python -m pyright dayu/host/durable/schema.py dayu/host/durable/connection.py dayu/host/durable/maintenance.py tests/host/test_durable_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_durable_concurrency_matrix.py
```
