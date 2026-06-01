# WU-DUR-01-02 Plan Re-review - MiMo

## Reviewed Fix

- **Plan fixed**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Controller adjudication**: `docs/reviews/wu-dur-01-02-plan-controller-adjudication-20260601.md`
- **Fix artifact**: `docs/reviews/wu-dur-01-02-plan-fix-codex-20260601.md`
- **Original review**: `docs/reviews/wu-dur-01-02-plan-review-mimo-20260601.md`
- **Other review**: `docs/reviews/wu-dur-01-02-plan-review-ds-20260601.md`

## Conclusion

**pass**

全部 7 条 accepted findings / suggestions 均已修复，plan fix 未引入新的严重 correctness 或 scope bug。

## Finding Status

### MIMO-P1 — fixed

`_bootstrap_fresh_schema(connection)` 被明确为唯一允许执行 `HOST_DURABLE_DDL` 的路径（plan line 103）；`user_version == HOST_SCHEMA_VERSION` 分支明确"不执行任何 DDL；只调用 `validate_host_durable_schema(connection)` 做 full schema validation"（plan line 100）；plan line 103 进一步强调"必须直接跳过 DDL loop"。测试要求构造 current version + 缺表 DB 断言 opener 不创建缺失表（plan line 272）。边界无歧义。

### MIMO-P2 — fixed

`_open_configured_connection()` / `HostDurableStore.connect()` 被明确命名为"secondary connection validation-only 路径"（plan line 145），该路径"只做 parent 准备、raw connection、PRAGMA setup、`validate_host_durable_schema(connection)`；不得调用 `bootstrap_host_durable_store()`、不得调用 `_bootstrap_fresh_schema()`、不得执行任何 DDL"（plan line 145）。Slice 1 增加了 `store.connect()` 缺表或缺索引 fail closed 且不重建对象的测试要求（plan line 274）。Data flow 也明确写出"独立 `store.connect()` 配置 PRAGMA -> full validation only -> connection returned；该路径不 bootstrap、不执行 DDL"（plan line 264）。

### MIMO-P3 / DS-P1 — fixed

Plan line 113 明确 "`HOST_DURABLE_INDEXES` 必须包含 `schema.py` 中全部已有 `INDEX_*` durable index name constants"，并在 line 113-131 列出全部 22 个 index name constants 作为初始集合。Slice 1 exact changes 要求"不允许只挑核心索引子集"（plan line 249）。Slice 1 测试增加 consistency test："解析 `HOST_DURABLE_DDL` 中 `CREATE INDEX` / `CREATE UNIQUE INDEX` 的 index name 集合，并断言等于 `set(HOST_DURABLE_INDEXES)`"（plan line 275）。自动漂移检测已覆盖。

### MIMO-P4 — fixed

Plan line 291 明确 "This is a diagnostic-field observability test, not a requirement to stably manufacture `busy_pages > 0`"。Line 292 进一步约束"只有在不 over-mock SQLite transaction、WAL、locking、checkpoint correctness 或 retry behavior 的前提下，才可增加 unit-level synthetic `busy_pages > 0` coverage"。busy test 的定位从"验证 busy path"修正为"诊断字段可观测"，消除了 implementation agent 误读为必须稳定制造 busy 的歧义。

### DS-NBS-1 — fixed

Plan line 141-144 明确 validation call ownership：`bootstrap_host_durable_store()` 是"primary opener 的 schema dispatch + final validation owner"，`open_host_durable_store()` "只负责 parent 准备、raw connection、PRAGMA setup、调用 `bootstrap_host_durable_store(connection)`，不在 bootstrap 返回后再次调用 `validate_host_durable_schema()`"。消除了 primary opener 双重 full validation 的歧义。

### DS-NBS-2 — fixed

`_open_configured_connection()` 被明确为"secondary connection validation-only 路径"（plan line 145），且"不得调用 `bootstrap_host_durable_store()`、不得调用 `_bootstrap_fresh_schema()`、不得执行任何 DDL"（plan line 145）。声明明确，implementation agent 不可能误在此路径加入 DDL。

### DS-NBS-3 — fixed

Plan line 200 明确 read-stale 测试"使用同一 DB 文件上的两个独立 SQLite connections"，建议"使用 `open_host_durable_store()` 返回的 primary store connection 作为 connection A，再通过同一个 `HostDurableStore` 的 `store.connect()` 获取 connection B"（plan line 200）。Slice 2 data flow 同步要求"primary connection + `store.connect()` 和两个 `HostTransactionRunner` 实例"（plan line 301）。Connection 创建方式无歧义。

## New Blocking Issues

none。Plan fix 仅为文本澄清，未改变 scope、public contract、schema、state machine 或 slice 边界。

## Stop Status

rereview-complete
