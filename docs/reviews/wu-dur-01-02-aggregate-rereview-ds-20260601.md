# WU-DUR-01 + WU-DUR-02 Aggregate Doc-Only Fix Re-Review

- **执行角色**: AgentDS
- **日期**: 2026-06-01
- **输入裁决**: `docs/reviews/wu-dur-01-02-aggregate-controller-adjudication-20260601.md`
- **输入修复记录**: `docs/reviews/wu-dur-01-02-fix-aggregate-codex-20260601.md`
- **审查范围**: `dayu/host/README.md`, `dayu/host/durable/schema.py`, `dayu/host/durable/maintenance.py` 三处未提交 diff

## 审查方法

逐条对照 Controller adjudication 中 AGG-DOC-1/2/3 的 required fix 描述，验证 diff 是否完整满足要求；同时扫描 diff 是否引入行为改动或越界修复。

## 逐条验证

### AGG-DOC-1: Host README durable bullet 可读性

- **要求**: 拆分 `dayu/host/README.md` 中 durable foundation 长 bullet 为可读子项，并明确 secondary durable connections 也执行完整当前 schema validation。
- **实际变更**: 原单行 bullet 已拆分为 6 条子 bullet，归属 `durable foundation：` 标题下。子项 2 明确写入"主连接与 secondary durable connections 都会执行完整当前 schema validation"。
- **行为检查**: 纯 README 文本重构，无代码变更。
- **结论**: **PASS** — 完整满足要求。

### AGG-DOC-2: Fresh bootstrap docstring 前置条件

- **要求**: 更新 `_bootstrap_fresh_schema()` docstring，说明传入 connection 需处于 autocommit 模式（`isolation_level=None`），因为函数自行开启 `BEGIN IMMEDIATE` 显式事务。
- **实际变更**: `:param connection:` 描述已更新为"已完成 PRAGMA setup 且处于 autocommit 模式（``isolation_level=None``）的 SQLite connection；本函数会自行开启 ``BEGIN IMMEDIATE`` 显式事务"。
- **代码一致性验证**: 函数体第 1319 行确实执行 `connection.execute("BEGIN IMMEDIATE")`，docstring 与实现一致。
- **行为检查**: 仅 docstring 变更，函数体未修改。
- **结论**: **PASS** — 完整满足要求，docstring 与实现一致。

### AGG-DOC-3: WAL size missing-file diagnostic 措辞

- **要求**: 更新 `_read_wal_size_bytes()` docstring，说明 WAL 文件不存在时返回 `0`，覆盖不存在与被 SQLite 清理两种情况。
- **实际变更**: `:returns:` 描述已更新为"WAL 文件不存在或已被 SQLite 清理时返回 ``0``"。
- **代码一致性验证**: 函数体第 122-123 行 `except FileNotFoundError: return 0` — `FileNotFoundError` 同时覆盖文件从未创建和已被 SQLite checkpoint 清理两种场景，docstring 与实现语义一致。
- **行为检查**: 仅 docstring 变更，函数体未修改。
- **结论**: **PASS** — 完整满足要求，docstring 与实现一致。

## 越界检查

扫描三处 diff 的全部 hunks:

| 文件 | 变更类型 | 是否含行为改动 |
|---|---|---|
| `dayu/host/README.md` | 纯文本重构（bullet 拆分 + 一句说明） | 否 |
| `dayu/host/durable/schema.py` | 仅 `_bootstrap_fresh_schema` docstring `:param connection:` 扩展 | 否 |
| `dayu/host/durable/maintenance.py` | 仅 `_read_wal_size_bytes` docstring `:returns:` 扩展 | 否 |

未发现任何 deferred findings 被夹带修复，未发现测试逻辑、durable schema 或生产行为改动。

## Verdict

**ALL PASS — 文档修复完整，无行为改动，无越界修复。**

三处 AGG-DOC-1/2/3 required fixes 均已完整实施，且仅限文档/docstring 层面。未引入任何生产行为变更、deferred finding 修复或 scope creep。
