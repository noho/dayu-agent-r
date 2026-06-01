# WU-DUR-01-02 Slice 1 Code Review - DS

## Reviewed Target

- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Implementation artifact**: `docs/reviews/wu-dur-01-02-implementation-slice1-codex-20260601.md`
- **Diff**: 当前未提交 diff，范围限于 Slice 1 allowed files
- **Changed files**:
  - `dayu/host/durable/schema.py` — 新增 `HOST_DURABLE_INDEXES`、`_bootstrap_fresh_schema`、`validate_host_durable_schema`（替代旧 version-only helper）、`_validate_required_tables`、`_validate_required_indexes`；重写 `bootstrap_host_durable_store` 分 fresh/current/mismatch 三支
  - `dayu/host/durable/connection.py` — import 切换；删除 `open_host_durable_store` 中的重复 version-only validation；`_open_configured_connection` 改为 full schema validation
  - `tests/host/test_durable_schema.py` — 新增 7 个测试覆盖 DDL failure rollback、current-version 缺表/索引 fail closed、secondary path fail closed、索引一致性
- **Pyright**: `0 errors, 0 warnings, 0 informations`
- **Tests**: `27 passed`

## Conclusion

**pass**

实现正确关闭了 WU-DUR-01 Slice 1 的全部验收目标：fresh bootstrap 全量 DDL 与 `PRAGMA user_version` 在同一 `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` 显式事务内同成同败；current-version DB 不再执行任何 DDL，缺 required table/index 结构性 fail closed；secondary connection path 仅做 full validation，不 bootstrap、不 DDL。`HOST_DURABLE_INDEXES` 完整覆盖全部 23 个 durable index name constants。未发现 correctness 或 type-safety 缺陷。

## Findings

### DS-C1-未修复-低-一致性测试 regex 仅匹配 IF NOT EXISTS 语法

- **Evidence**: `tests/host/test_durable_schema.py:72-75`，`_CREATE_INDEX_NAME_PATTERN` 正则要求 `IF\s+NOT\s+EXISTS` 作为 `CREATE INDEX` 的必选部分。计划要求的一致性测试通过解析 DDL 文本抽取索引名，再与 `set(HOST_DURABLE_INDEXES)` 做等值断言。若未来有人添加不带 `IF NOT EXISTS` 的 `CREATE INDEX` 语句（违反当前约定但 SQL 合法），正则不会捕获该语句，导致 `ddl_index_names` 缺少该索引名，断言仍可能因巧合通过（若同时漏加到 `HOST_DURABLE_INDEXES`）。
- **Why it matters**: 一致性测试的防御价值依赖正则的覆盖完整性。当前全部 23 个索引 DDL 均使用 `IF NOT EXISTS`，风险不在当下而在未来维护者可能引入不同风格的 `CREATE INDEX`。
- **Required fix**: 将正则放宽为 `r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)"`，使 `IF NOT EXISTS` 变为可选。这不会影响当前匹配结果，但扩大了未来防御面。
- **Controller decision status**: pending
- **严重程度**: 低

### DS-C2-未修复-低-缺少 HOST_DURABLE_TABLES 与 DDL 中表名的自动化一致性检查

- **Evidence**: 计划要求 indexes 的一致性测试（已实现），但未要求 tables 的等价测试。当前表名一致性靠"DDL f-string 与 `HOST_DURABLE_TABLES` 子元组共用同名常量"的手工约定保证，例如 `TABLE_EVENT_LOG = "event_log"` 同时出现在 `_EVENT_LOG_DDL` 和 `FOUNDATION_TABLES` 中。但若有人在 DDL 中直接写字面量表名而不使用常量，或从子元组删除常量但保留 DDL，`validate_host_durable_schema` 仍会通过（因为 `sqlite_master` 中存在该表），一致性漂移不会被自动发现。
- **Why it matters**: 索引已有自动化交叉验证，表名集合是唯一仍仅靠人工保证的结构元数据。影响限于未来 schema 演进时的维护风险。
- **Required fix**: 添加类似 `test_host_durable_indexes_match_create_index_ddl` 的表名一致性测试，用 regex 从 DDL 中抽取 `CREATE TABLE ...` 表名，断言与 `HOST_DURABLE_TABLES` 等值。
- **Controller decision status**: pending
- **严重程度**: 低

## Non-blocking Suggestions

1. **DDL failure test 可增加通过 opener 的集成路径**：当前 `test_fresh_bootstrap_rolls_back_when_ddl_fails` 直接在 raw connection 上调用 `bootstrap_host_durable_store`，不经过 `open_host_durable_store` 的错误包装层（`HostDurableError("Host durable SQLite bootstrap failed")`）。可考虑额外增加一条通过 opener 的测试，证明 opener 在 DDL 失败时正确包装错误类型并清理 connection，同时 `user_version` 保持 0。当前 coverage 已够，此为非阻塞增强建议。
2. **`_validate_required_indexes` 的 `sqlite_master` 查询结果包含 SQLite 内部 autoindex**：`WHERE type='index'` 会返回 `sqlite_autoindex_*` 内部索引。当前不影响正确性（多出内部索引不导致误判），但若未来 HOST_DURABLE_INDEXES 中也包含与 autoindex 同名的索引名会制造迷惑。可在注释中标记此行为。

## Open Questions / Residual Risk

### Non-blocking

- **`configure_connection_pragmas` 与 `_bootstrap_fresh_schema` 的时序依赖**：`open_host_durable_store` 在 `bootstrap_host_durable_store` 前调用 `configure_connection_pragmas` 设置 `journal_mode=WAL`，这是 fresh bootstrap transaction 可回滚 DDL 的前提。该时序依赖是隐式的——`_bootstrap_fresh_schema` 自身不检查也不声明 journal_mode 前提。若未来有人绕过 opener 直接调用 `bootstrap_host_durable_store`（如测试中已这样做），在非 WAL 连接上 DDL 事务语义可能不同。当前所有 production path 均通过 opener，风险可控，但建议在 `_bootstrap_fresh_schema` 的 docstring 中添加前置条件声明。
- **非 WAL mode 下 DDL 事务行为差异**：SQLite 在非 WAL journal mode 下 DDL 仍支持事务回滚，但行为可能存在版本差异。由于 `configure_connection_pragmas` 始终设置 `journal_mode=WAL`，且 `_bootstrap_fresh_schema` 的 docstring 声明需要"已完成 PRAGMA setup 的 SQLite connection"，实际风险低。

### Residual Risk

- Slices 2-4 尚未实施，WAL maintenance primitive、read stale proof、concurrency matrix gap tests 的缺失不影响 Slice 1 结论，但需在后续 slices 完成。
- 计划中提到 "rollback failure remains best-effort suppressed; not expanded" 是既定设计决策，已确认未扩大 scope。

## Stop Status

review-complete
