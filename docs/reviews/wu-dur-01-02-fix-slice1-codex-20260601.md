# WU-DUR-01-02 Slice 1 Code Review Fix - Codex

## Gate

- Gate: code review fix
- Work unit: WU-DUR-01 + WU-DUR-02
- Slice: Slice 1 - Bootstrap Atomicity And Current-schema Validation
- Role: fix specialist
- Approved plan: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- Controller adjudication: `docs/reviews/wu-dur-01-02-code-controller-adjudication-slice1-20260601.md`
- Source review artifact: `docs/reviews/wu-dur-01-02-code-review-slice1-ds-20260601.md`

## Scope

- 仅处理 controller accepted findings: DS-C1、DS-C2。
- 未进入 Slice 2/3/4。
- 未提交、未 push、未创建 PR。
- 未修改 production behavior。

## Per-finding Fix Status

### DS-C1-已修复-低-一致性测试 regex 仅匹配 IF NOT EXISTS 语法

- Fix: `_CREATE_INDEX_NAME_PATTERN` 已放宽为同时匹配 `CREATE INDEX name`、`CREATE INDEX IF NOT EXISTS name`、`CREATE UNIQUE INDEX name`、`CREATE UNIQUE INDEX IF NOT EXISTS name`。
- Assertion strength: `test_host_durable_indexes_match_create_index_ddl` 仍断言 DDL 抽取出的 index 名称集合与 `set(HOST_DURABLE_INDEXES)` 完全相等，未降级为 subset/superset。
- Production behavior: 未修改。

### DS-C2-已修复-低-缺少 HOST_DURABLE_TABLES 与 DDL 中表名的自动化一致性检查

- Fix: 新增 `_CREATE_TABLE_NAME_PATTERN` 与 `_ddl_table_names(statements: tuple[str, ...]) -> frozenset[str]` 测试 helper。
- Helper quality: helper 使用严格类型签名，并提供中文 docstring，包含参数、返回值、异常说明。
- Test: 新增 `test_host_durable_tables_match_create_table_ddl`，解析 `HOST_DURABLE_DDL` 中 `CREATE TABLE` 名称并断言与 `set(HOST_DURABLE_TABLES)` 完全相等。
- Production behavior: 未修改。

## Changed Files

- `tests/host/test_durable_schema.py`
- `docs/reviews/wu-dur-01-02-fix-slice1-codex-20260601.md`

## Notes

- `dayu/host/durable/schema.py` 在本 handoff 前已有未提交改动；本 fix pass 未修改其生产行为。
- `_bootstrap_fresh_schema` docstring 已包含 `已完成 PRAGMA setup 的 SQLite connection` 前置条件说明，因此本 fix pass 未再改动该文件。
- Source review artifact 标题未回写，因为本 handoff 的 allowed edits 不包含 `docs/reviews/wu-dur-01-02-code-review-slice1-ds-20260601.md`；本 artifact 记录 fix 自报状态，最终状态以 re-review 为准。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py -q`
  - Result: `28 passed in 0.36s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## New Risks / Open Questions

- New risks: 未发现。
- Open questions: 无。
- Residual risk classification: Slice 2/3/4 尚未实施属于 approved plan 后续 slice，不属于本 fix scope。

## Stop Status

fix-complete
