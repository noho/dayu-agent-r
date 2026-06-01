# WU-DUR-01 + WU-DUR-02 Aggregate Doc-Only Fix

- **执行角色**: AgentCodex
- **日期**: 2026-06-01
- **输入裁决**: `docs/reviews/wu-dur-01-02-aggregate-controller-adjudication-20260601.md`
- **修复范围**: 仅 AGG-DOC-1 / AGG-DOC-2 / AGG-DOC-3

## 修复内容

### AGG-DOC-1

已将 `dayu/host/README.md` 中低层与 Diagnostic 路径下的 durable foundation 长 bullet 拆分为可读子项，并明确主连接与 secondary durable connections 都会执行完整当前 schema validation。

### AGG-DOC-2

已更新 `dayu/host/durable/schema.py` 中 `_bootstrap_fresh_schema()` 的 docstring，说明传入 connection 需要处于 autocommit 模式（`isolation_level=None`），因为函数内部自行开启 `BEGIN IMMEDIATE` 显式事务。

### AGG-DOC-3

已更新 `dayu/host/durable/maintenance.py` 中 `_read_wal_size_bytes()` 的 docstring，说明 WAL 文件不存在或已被 SQLite 清理时返回 `0`。

## 边界说明

本次只修改 README 与 docstring，并写入本修复 artifact；未处理 deferred findings，未修改生产行为、测试逻辑或 durable schema。
