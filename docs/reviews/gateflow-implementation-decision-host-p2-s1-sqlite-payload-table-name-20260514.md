# Host Phase 2 Slice 1 Implementation Decision: SQLite Payload Table Name

## Work Gate Name

implementation controller decision

## Source Artifact

- `docs/reviews/gateflow-implementation-host-p2-s1-durable-schema-transaction-20260514.md`

## Finding

`sqlite_payloads` 不能作为 SQLite 用户表名。SQLite 保留 `sqlite_` 前缀用于内部对象，fresh bootstrap 在创建该表时失败，错误为 `object name reserved for internal use: sqlite_payloads`。

## Controller Decision

该问题成立，属于 approved plan 的 schema table name bug，不是 implementation bug。Controller 决定将用户表名从 `sqlite_payloads` 改为 `host_sqlite_payloads`。

决策理由：

- `host_sqlite_payloads` 不使用 SQLite 保留前缀。
- 表名仍表达该表属于 Host durable store，且承载 `payload_kind='sqlite_payload'` descriptor 对应的 SQLite-local payload rows。
- descriptor kind `sqlite_payload`、字段 `sqlite_payload_id` 和 public typed semantics 不变；只改变物理表名。
- 不引入 Slice 2 / Slice 3 行为，不改变 payload descriptor 架构边界。

## Required Fix

- Update `docs/host/phase2-durable-store-eventlog-plan.md` DDL and tests references from table `sqlite_payloads` to `host_sqlite_payloads`.
- Update `dayu/host/durable/schema.py` table constant / DDL accordingly.
- Update affected tests.
- Continue Slice 1 validation.

## Artifact Path

`docs/reviews/gateflow-implementation-decision-host-p2-s1-sqlite-payload-table-name-20260514.md`
