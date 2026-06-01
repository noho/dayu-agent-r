# WU-DUR-01 + WU-DUR-02 Implementation Slice 1 Report

## 基本信息

- **Gate**: WU-DUR-01 + WU-DUR-02 implementation
- **Slice**: Slice 1 - Bootstrap Atomicity And Current-schema Validation
- **Role**: implementation specialist
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Stop status**: completed

## 动机判断

动机成立。直接证据是原 `bootstrap_host_durable_store()` 在 current-version DB 上仍遍历 `HOST_DURABLE_DDL`，而 DDL 使用 `CREATE ... IF NOT EXISTS`，会把缺失 table / index 静默补齐；原 secondary connection path 只调用 version-only validation，不能证明当前 schema 结构完整。该风险与 approved plan 的 WU-DUR-01 验收目标一致，未发现需要扩 scope 的设计问题。

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/connection.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/wu-dur-01-02-implementation-slice1-codex-20260601.md`

`dayu/host/README.md` 已检查，未修改。

## Implemented Items

- 新增 `HOST_DURABLE_INDEXES`，覆盖当前 `schema.py` 中全部 durable `INDEX_*` name constants。
- 新增 `validate_host_durable_schema(connection)`，校验 `PRAGMA user_version`、required tables、required indexes；缺对象时抛 `HostSchemaMismatchError` 且错误消息包含对象名。
- 新增 `_bootstrap_fresh_schema(connection)`，唯一执行 `HOST_DURABLE_DDL` 的路径，显式执行 `BEGIN IMMEDIATE`、DDL、`PRAGMA user_version`、`COMMIT`，失败时 best-effort rollback 后透传 SQLite 错误。
- 调整 `bootstrap_host_durable_store()`：fresh 分支执行 `_bootstrap_fresh_schema()` 后 full validation；current 分支只 full validation，不执行 DDL、不 repair；version mismatch 仍抛 `HostSchemaMismatchError`。
- 调整 `open_host_durable_store()`：保留 primary bootstrap 调用，删除 bootstrap 后重复 version-only validation。
- 调整 `_open_configured_connection()` / `HostDurableStore.connect()`：secondary path 只做 PRAGMA setup + `validate_host_durable_schema()`，不 bootstrap、不执行 DDL。
- 删除旧 `validate_host_schema_version()` version-only helper，避免留下兼容 facade。
- 补充 tests 覆盖 fresh DDL failure rollback、current 缺 table/index opener fail closed、secondary path 缺 table/index fail closed、`HOST_DURABLE_INDEXES` 与 DDL 中 `CREATE INDEX` 名称一致性。

## Tests Run

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py -q`
  - **Result**: pass
  - **Evidence**: `27 passed in 0.36s`

## Pyright Result

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - **Result**: pass
  - **Evidence**: `0 errors, 0 warnings, 0 informations`

## README Decision

检查了 `dayu/host/README.md` 中 Host durable opener / schema validation 相关说明。现有稳定说明只表达 durable schema 按当前 fresh version 起库、version mismatch 需要重建 DB，没有声称 opener 只校验 `user_version`，也没有声称 current-version DB 会静默 repair。因此本 slice 不更新 README。

## Plan Deviations

无。未新增 public API、未新增 schema version、未做 migration、未做 offline repair、未改变 DDL text。

## Residual Risks Classification

- **fixed in current slice before review**: current-version DB 缺 required table / index 会 fail closed，不再通过 DDL 静默 repair；fresh bootstrap DDL 与 `user_version` 同事务提交或 rollback。
- **covered by later slice in approved plan**: WAL maintenance diagnostic、read stale snapshot proof、durable concurrency matrix gap tests 属于 Slice 2 / Slice 3。
- **assigned to later phase/work unit**: 无。
- **tracked by existing issue**: 无。
- **requiring new issue or explicit user decision**: 无。

## Completion Signal

Slice 1 required implementation 和 required tests 已完成，指定 pytest 与 pyright 均通过；未触发 stop condition。
