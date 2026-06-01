# WU-DUR-01-02 Slice 1 Code Review - MiMo

## Reviewed Target

- **Diff**: `feat/wu-dur-bootstrap-concurrency` 未提交 workspace diff（相对 HEAD），涉及 `dayu/host/durable/schema.py`、`dayu/host/durable/connection.py`、`tests/host/test_durable_schema.py`。
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Implementation artifact**: `docs/reviews/wu-dur-01-02-implementation-slice1-codex-20260601.md`

## Conclusion

**pass**

## Findings

未发现实质性问题。

逐项验证结论：

### 1. Fresh bootstrap DDL + user_version 事务原子性

`_bootstrap_fresh_schema()` (`schema.py:1307-1327`) 使用 `BEGIN IMMEDIATE` / DDL loop / `PRAGMA user_version` / `COMMIT` 显式事务。connection 由 `_open_raw_connection()` 以 `isolation_level=None` 打开（`connection.py:203-207`），Python sqlite3 模块不管理事务，因此显式 `BEGIN IMMEDIATE` 正确进入事务状态。DDL 中途失败时 `except sqlite3.Error` 分支执行 `ROLLBACK`，rollback 失败仅 best-effort suppress 并透传原始异常。

**直接证据**: `schema.py:1316-1327` — try 块内 `BEGIN IMMEDIATE` 到 `COMMIT` 包裹全部 DDL + user_version；except 块内 `ROLLBACK` + raise。

**事务边界验证**: `PRAGMA user_version` 在 `BEGIN IMMEDIATE` 之后执行，属于该事务；COMMIT 前任何失败都会 rollback，不留下 partial schema 或 current user_version。

### 2. Current-version path 不执行 DDL

`bootstrap_host_durable_store()` (`schema.py:1253-1280`) 的 `current_version == HOST_SCHEMA_VERSION` 分支直接调用 `validate_host_durable_schema(connection)` 并 return，不进入 `_bootstrap_fresh_schema()`，不遍历 `HOST_DURABLE_DDL`。

**直接证据**: `schema.py:1273-1275` — `if current_version == HOST_SCHEMA_VERSION: validate_host_durable_schema(connection); return`。

### 3. Missing table/index 结构化 fail closed

`validate_host_durable_schema()` (`schema.py:1283-1304`) 先校验 `user_version`，再调用 `_validate_required_tables()` 和 `_validate_required_indexes()`。这两个函数查询 `sqlite_master` 并逐项比对 `HOST_DURABLE_TABLES` / `HOST_DURABLE_INDEXES`，缺对象时抛 `HostSchemaMismatchError` 且消息包含具体对象名。不执行 DDL，不尝试修复。

**直接证据**: `schema.py:1330-1369`。

### 4. Secondary path validation-only

`_open_configured_connection()` (`connection.py:170-191`) 只做 PRAGMA setup + `validate_host_durable_schema(connection)`，不调用 `bootstrap_host_durable_store()`，不执行 DDL。`HostDurableStore.connect()` 委托给 `_open_configured_connection()`。

**直接证据**: `connection.py:183-185` — `configure_connection_pragmas(connection, options.sqlite_policy); validate_host_durable_schema(connection)`。无 bootstrap 调用。

### 5. `HOST_DURABLE_INDEXES` 覆盖完整性

`HOST_DURABLE_INDEXES` (`schema.py:138-162`) 包含 23 个 index 常量。通过与 `schema.py` 中全部 `INDEX_*` 常量（行 53-75）逐项比对，确认一一对应，无遗漏。

**一致性测试**: `test_host_durable_indexes_match_create_index_ddl()` (`test_durable_schema.py:467-479`) 用正则从 `HOST_DURABLE_DDL` 中抽取全部 `CREATE INDEX` 名称，断言与 `set(HOST_DURABLE_INDEXES)` 相等。测试可靠且不过度脆弱：DDL 变更时自动发现不一致。

### 6. 测试覆盖

- `test_fresh_bootstrap_rolls_back_when_ddl_fails`: monkeypatch 注入 broken DDL，断言 rollback 后无 user tables 且 `user_version == 0`。
- `test_current_schema_missing_table_opener_raises_without_repair`: 手动设置 `user_version` 但不建表，opener 抛 `HostSchemaMismatchError` 且不创建缺失表。
- `test_current_schema_missing_index_opener_raises_without_repair`: 正常 bootstrap 后删除一个 index，opener 抛错且不重建。
- `test_secondary_connection_missing_table_raises_without_repair`: `store.connect()` 缺表时只校验不 bootstrap。
- `test_secondary_connection_missing_index_raises_without_repair`: `store.connect()` 缺索引时只校验不 bootstrap。
- `test_host_durable_indexes_match_create_index_ddl`: DDL 与 `HOST_DURABLE_INDEXES` 一致性。

### 7. 类型与编码规范

- 全部新增函数有完整中文 docstring，包含参数、返回值、异常。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- 旧 `validate_host_schema_version()` 已删除，未留下兼容 facade。`connection.py` 正确 import 新函数名 `validate_host_durable_schema`。
- 无 God helper、无 God function。

### 8. README 决策

`dayu/host/README.md` 未修改。Implementation artifact 说明现有 README 只表达"durable schema 按当前 fresh version 起库、version mismatch 需要重建 DB"，未声称 opener 只校验 `user_version` 或 current-version 会静默 repair，因此不更新。决策合理。

## Non-blocking Suggestions

无。

## Open Questions / Residual Risk

### Non-blocking

- **DDL 文本保留 `IF NOT EXISTS`**: 当前 `HOST_DURABLE_DDL` 中的 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` 与"current-version 不静默修复"的语义不冲突（因为 current-version 分支不执行 DDL），但可能引起 reviewer 误解。Plan 已明确此决策边界，不影响 correctness。
- **`_validate_required_tables` / `_validate_required_indexes` 不做 DDL text diff**: 第一版只校验 required table/index existence，不做 full SQL DDL text drift 检测。Plan 将 DDL text drift 归为后续 WU-LAYER-01 schema invariant hardening，不在本轮 scope。

## Stop Status

review-complete
