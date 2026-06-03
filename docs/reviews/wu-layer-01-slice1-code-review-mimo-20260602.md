# WU-LAYER-01 Slice 1 Code Review — AgentMiMo

## 结论

**PASS**

无 blocking finding。实现正确、稳定、可维护，严格限于 Slice 1 scope。

## Review Scope

- `dayu/host/durable/schema.py` — HEAD diff
- `tests/host/test_durable_schema.py` — HEAD diff
- `docs/host/host-core-followup-implementation-control.md` — controller bookkeeping（仅检查状态记录）
- `docs/reviews/wu-layer-01-slice1-schema-definition-validation-codex-20260602.md` — implementation artifact

## Review Checklist

### 1. Schema expected SQL generation 是否真正同源于 HOST_DURABLE_DDL

**PASS** — `_expected_schema_sql_by_name()` (`schema.py:1422-1448`) 创建内存 SQLite fresh DB，执行 `HOST_DURABLE_DDL`，从 `sqlite_master` 读取 catalog SQL。没有第二份手写 expected DDL 字符串。`HOST_DURABLE_DDL` 仍是唯一 DDL 真源。

### 2. validate_host_durable_schema 是否仍 fail closed

**PASS** — `validate_host_durable_schema` (`schema.py:1304-1328`) 按序校验 user_version → required tables → required indexes → required object definitions。任何一步失败即抛 `HostSchemaMismatchError`。`_validate_required_object_definitions` (`schema.py:1397-1419`) 不执行 DDL、不修复、不迁移。

### 3. _normalize_schema_sql 是否只做最小 whitespace normalization

**PASS** — `_normalize_schema_sql` (`schema.py:1497-1508`) 仅 `sql.strip()` + `re.sub(r"\s+", " ", ...)`。保持大小写、identifier quoting、标点、clause 顺序不变。`test_normalize_schema_sql_only_strips_and_collapses_whitespace` (`test_durable_schema.py:752-791`) 覆盖了大小写变化、quote 变化、clause 变化、标点变化均不被吞掉的负面断言。

### 4. sqlite_master query/placeholders 是否类型安全、无 SQL 注入风险、无空集合隐患

**PASS** — `_SQLITE_MASTER_SQL_QUERY_TEMPLATE` (`schema.py:1259-1264`) 使用 `?` 参数化占位符。`_sqlite_placeholders` (`schema.py:1511-1523`) 生成 `?,?,...` 字符串，`value_count <= 0` 时抛 `HostSchemaMismatchError`。`_read_schema_sql_by_name` (`schema.py:1451-1480`) 将 type/name 值作为参数传入，不拼接用户输入。

### 5. 测试覆盖审查

**PASS** — 新增测试覆盖：

| 测试 | 文件:行 | 覆盖场景 |
|---|---|---|
| `test_current_schema_wrong_index_definition_opener_raises_without_repair` | test:531-568 | 同名 required index 定义错误 → opener fail closed |
| `test_current_schema_mutated_table_definition_opener_raises_without_repair` | test:571-611 | 同名 table catalog SQL 变异 → opener fail closed |
| `test_secondary_connection_definition_mismatch_raises_without_repair` | test:666-701 | secondary connection definition mismatch → fail closed |
| `test_fresh_bootstrapped_schema_matches_generated_expected_sql` | test:729-749 | fresh bootstrap → generated expected SQL 校验通过 |
| `test_normalize_schema_sql_only_strips_and_collapses_whitespace` | test:752-791 | normalization 负面用例 |

所有新增测试均验证失败后错误定义未被修复（verify_connection 断言 wrong SQL 仍在）。

### 6. 是否越界实现 Slice 2/3 或 WU-LAYER-02

**PASS** — diff 只修改 `schema.py` 和 `test_durable_schema.py`。未新增 `_row_rules.py`、未修改 `state.py`、未新增 `HostRowDecodeError`、未修改 `errors.py`、未触及 `dayu.runtime`。严格限于 Slice 1 allowed files。

### 7. Docstring/type/signature 是否违反 AGENTS.md

**PASS** — 所有新增函数提供完整中文 docstring（参数、返回值、异常）。类型签名无 `Any`、`object`、无类型参数或无类型返回值。`_SchemaObjectKey = tuple[str, str]` 类型别名正确。

## Findings

### F1 — 模块级 docstring 未反映新增 definition validation（信息级）

- **文件**: `schema.py:1-8`
- **问题**: 模块 docstring 仍描述 "校验范围包括 PRAGMA user_version、required tables 和 required indexes"，未提及新增的 required object definition 校验。`validate_host_durable_schema` 函数 docstring 已正确更新。
- **影响**: 不影响运行时行为。开发者阅读模块概览时可能遗漏新增校验能力。
- **建议**: 更新模块 docstring 中关于 validation 范围的描述。非 blocking。

### F2 — _expected_schema_sql_by_name 创建内存 DB 后不显式关闭游标（信息级）

- **文件**: `schema.py:1434-1448`
- **问题**: `connection.execute(...)` 返回的 cursor 未显式关闭；`connection.close()` 在 `finally` 中关闭 connection，游标会被 GC 回收。
- **影响**: 无实际影响，SQLite connection close 会清理关联资源。
- **建议**: 不需要修改，当前写法符合 sqlite3 模块惯例。

### F3 — controller bookkeeping 状态记录（信息级）

- **文件**: `docs/host/host-core-followup-implementation-control.md`
- **问题**: 状态记录更新正确反映了 "implementation complete; code review pending"，与当前 review gate 一致。implementation artifact 路径正确。
- **影响**: 无。
- **建议**: 无。

## Open Questions

无。

## Residual Risks

1. **Slice 2 DDL CHECK 变更**: Slice 2 将从 `_row_rules.py` 生成 Run/Attempt/WaitRecord DDL CHECK 片段。如果 DDL 文本变更，`_expected_schema_sql_by_name()` 会自动生成新的 expected SQL，但 Slice 2 实现后必须重跑 Slice 1 schema definition validation 测试，确认 fresh bootstrap 不会 false-positive。这是 plan 已识别的依赖，不是本 Slice 的风险。

2. **内存 DB 创建开销**: `_expected_schema_sql_by_name()` 每次校验创建一个内存 SQLite DB 并执行全量 DDL。当前 Host durable bootstrap 频率极低（进程启动 / secondary connection 创建），开销可忽略。如果未来校验频率增加，可考虑缓存 expected SQL（schema version 不变时结果不变），但当前无需优化。
