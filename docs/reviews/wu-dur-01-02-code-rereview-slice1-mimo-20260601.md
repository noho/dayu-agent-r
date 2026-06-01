# WU-DUR-01-02 Slice 1 Code Re-review - MiMo

## Gate

- Gate: focused code re-review
- Work unit: WU-DUR-01 + WU-DUR-02
- Slice: Slice 1 - Bootstrap Atomicity And Current-schema Validation
- Controller adjudication: `docs/reviews/wu-dur-01-02-code-controller-adjudication-slice1-20260601.md`
- Fix artifact: `docs/reviews/wu-dur-01-02-fix-slice1-codex-20260601.md`
- Scope: DS-C1 regex fix 和 DS-C2 table consistency test，以及 fix 是否引入新 blocking issue

## Conclusion

**pass**

## Finding Status

### DS-C1: fixed

- **原始问题**: `_CREATE_INDEX_NAME_PATTERN` 正则要求 `IF NOT EXISTS` 为必选部分，未来不带该子句的 `CREATE INDEX` 语句不会被一致性测试捕获。
- **修复证据**: `tests/host/test_durable_schema.py:72-75`，正则已改为 `r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)"`。`(?:IF\s+NOT\s+EXISTS\s+)?` 使 `IF NOT EXISTS` 变为可选，同时保留 `UNIQUE` 可选匹配。
- **断言强度**: `test_host_durable_indexes_match_create_index_ddl` (line 500) 仍断言 `ddl_index_names == set(HOST_DURABLE_INDEXES)` — 完全相等，未降级为 subset/superset。
- **验证**: 28 tests passed, pyright 0 errors。

### DS-C2: fixed

- **原始问题**: 缺少 `HOST_DURABLE_TABLES` 与 DDL 中表名的自动化一致性检查，表名漂移仅靠人工约定发现。
- **修复证据**:
  - `_CREATE_TABLE_NAME_PATTERN` (line 78-82): `r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)"`，从 DDL 中抽取 `CREATE TABLE` 表名。
  - `_ddl_table_names()` helper (line 85-97): 严格类型签名 `tuple[str, ...] -> frozenset[str]`，中文 docstring 完整。
  - `test_host_durable_tables_match_create_table_ddl` (line 503-507): 断言 `_ddl_table_names(HOST_DURABLE_DDL) == set(HOST_DURABLE_TABLES)` — 完全相等。
- **验证**: 28 tests passed, pyright 0 errors。

## New Blocking Issues

none

- Fix 范围仅限 `tests/host/test_durable_schema.py`，未修改 production 代码。
- 新增 regex 和 helper 类型签名严格，docstring 完整。
- 测试数量从 27 增至 28，全部通过。
- pyright 无新增报错。

## Stop Status

rereview-complete
