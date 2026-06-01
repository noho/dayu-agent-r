# WU-DUR-01-02 Slice 1 Code Re-review - DS

## Scope

- **Gate**: DS focused re-review
- **Controller adjudication**: `docs/reviews/wu-dur-01-02-code-controller-adjudication-slice1-20260601.md`
- **Original DS review**: `docs/reviews/wu-dur-01-02-code-review-slice1-ds-20260601.md`
- **Fix artifact**: `docs/reviews/wu-dur-01-02-fix-slice1-codex-20260601.md`
- **Review target**: DS-C1 / DS-C2 fix verification in current workspace diff
- **Changed files**: `tests/host/test_durable_schema.py`
- **Verification**: `28 passed in 0.31s`, `pyright: 0 errors, 0 warnings, 0 informations`

## Conclusion

**pass**

## Finding Status

### DS-C1: fixed

- **入口/函数**: `_CREATE_INDEX_NAME_PATTERN` (测试模块级正则)
- **文件(行号)**: `tests/host/test_durable_schema.py:72-75`
- **直接证据**: 正则已从 `r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+([A-Za-z0-9_]+)"` 放宽为 `r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)"`，`IF NOT EXISTS` 子句由必选变为可选。当前覆盖全部四种合法形式：`CREATE INDEX name`、`CREATE INDEX IF NOT EXISTS name`、`CREATE UNIQUE INDEX name`、`CREATE UNIQUE INDEX IF NOT EXISTS name`。
- **断言强度验证**: `test_host_durable_indexes_match_create_index_ddl`（行 488-500）仍使用 `ddl_index_names == set(HOST_DURABLE_INDEXES)` 等值断言，未降级为 subset/superset。

### DS-C2: fixed

- **入口/函数**: `test_host_durable_tables_match_create_table_ddl` (新增测试)
- **文件(行号)**: 
  - `_CREATE_TABLE_NAME_PATTERN`: `tests/host/test_durable_schema.py:78-81`
  - `_ddl_table_names` helper: `tests/host/test_durable_schema.py:85-97`
  - 测试函数: `tests/host/test_durable_schema.py:503-510`
- **直接证据**: 新增了与索引一致性测试结构一致的 `_CREATE_TABLE_NAME_PATTERN` 正则、`_ddl_table_names` helper 和 `test_host_durable_tables_match_create_table_ddl` 测试。测试从 `HOST_DURABLE_DDL` 中抽取 `CREATE TABLE` 名称，与 `set(HOST_DURABLE_TABLES)` 做等值断言。
- **Helper 质量验证**: `_ddl_table_names` 使用严格类型签名 `(tuple[str, ...]) -> frozenset[str]`，提供完整中文 docstring（参数、返回值、异常）。

## New Blocking Issues

none

## Stop Status

rereview-complete
