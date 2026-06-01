# WU-DUR-01 + WU-DUR-02 Aggregate Doc-Only Fix Re-Review

- **角色**: AgentMiMo
- **日期**: 2026-06-01
- **输入裁决**: `docs/reviews/wu-dur-01-02-aggregate-controller-adjudication-20260601.md`
- **输入修复**: `docs/reviews/wu-dur-01-02-fix-aggregate-codex-20260601.md`
- **审查范围**: 未提交 diff 中 `dayu/host/README.md`、`dayu/host/durable/schema.py`、`dayu/host/durable/maintenance.py`
- **审查目标**: 确认 AGG-DOC-1/2/3 是否完整满足，且无行为改动或越界修复

## Verdict

**PASS — 三项 AGG-DOC 均完整满足，无行为改动，无越界修复。**

## AGG-DOC-1: Host README durable bullet readability

- **要求**: 将 `dayu/host/README.md` 中 durable foundation 长 bullet 拆分为可读子项，并明确 secondary durable connections 也执行完整 schema validation。
- **实际改动**: 原单行长 bullet 拆分为 6 个子项（`-` 下的 `  -`），覆盖 store/codec/helper、schema fresh version + validation（含主连接与 secondary connections）、WAL/auto-checkpoint、read transaction snapshot 语义、WAL checkpoint primitive 定位、store close 事务拒绝。
- **新增信息**: 子项中明确写了「主连接与 secondary durable connections 都会执行完整当前 schema validation」，与裁决要求一致。
- **判定**: ✓ 完整满足。内容未增删语义，仅拆分格式并补充 secondary validation 说明。

## AGG-DOC-2: Fresh bootstrap docstring precondition

- **要求**: `_bootstrap_fresh_schema()` docstring 说明 connection 需处于 autocommit 模式（`isolation_level=None`），因为函数自行开启 `BEGIN IMMEDIATE`。
- **实际改动**: `:param connection:` 从「已完成 PRAGMA setup 的 SQLite connection」改为「已完成 PRAGMA setup 且处于 autocommit 模式（`isolation_level=None`）的 SQLite connection；本函数会自行开启 `BEGIN IMMEDIATE` 显式事务」。
- **实现一致性**: 函数体第一行即 `connection.execute("BEGIN IMMEDIATE")`，与 docstring 前置条件一致。
- **判定**: ✓ 完整满足。仅 docstring 变更，无函数签名或行为改动。

## AGG-DOC-3: WAL size missing-file diagnostic wording

- **要求**: `_read_wal_size_bytes()` docstring 说明 WAL 文件不存在或已被 SQLite 清理时返回 `0`。
- **实际改动**: `:returns:` 从「文件不存在时返回 `0`」改为「WAL 文件不存在或已被 SQLite 清理时返回 `0`」。
- **实现一致性**: 函数体 `except FileNotFoundError: return 0` 与此语义一致。
- **判定**: ✓ 完整满足。仅 docstring 变更，无行为改动。

## 边界检查

| 检查项 | 结果 |
|--------|------|
| 是否有行为改动 | 否 — 仅 README 文档与 docstring 变更 |
| 是否有越界修复（超出 AGG-DOC-1/2/3 范围） | 否 — diff 仅含裁决指定的三处改动 |
| 是否有签名变更 | 否 |
| 是否有新增/删除函数或类 | 否 |
| 是否有生产逻辑改动 | 否 |
| 是否有测试改动 | 否 |

## 结论

AgentCodex 的 doc-only fix 完整覆盖了裁决要求的 AGG-DOC-1、AGG-DOC-2、AGG-DOC-3，无行为变更，无越界修复。三项改动均可接受。
