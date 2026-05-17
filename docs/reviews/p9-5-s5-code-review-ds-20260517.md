# P9.5 S5 Schema CHECK Hardening — Code Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S5 Schema CHECK Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S5.
- Implementation artifact: `docs/reviews/p9-5-s5-schema-check-hardening-implementation-20260517.md`.
- Reviewed files: `dayu/host/durable/schema.py`, `tests/host/test_durable_schema.py`.
- No code, tests, or artifacts were modified.

## Scope Adherence Verification

- All changes within S5 allowed files: `dayu/host/durable/schema.py`, `tests/host/test_durable_schema.py`.
- No new states, tables, columns, or public API.
- No migration, compatibility reads, or P10+ semantics.
- No `_validation.py` or other durable helper changes (Python validation parity pre-existed).

## Findings

未发现实质性问题。

## Review Point Checklist

### 1. Schema version 7→8 必要且只面向 fresh schema

**通过。**

- `schema.py:22`: `HOST_SCHEMA_VERSION = 7` → `8`
- `test_durable_schema.py:233-234`: `user_version` 断言同步从 `7` 更新为 `8`
- DDL 使用 `CREATE TABLE IF NOT EXISTS` — 对已有旧 schema 数据库不生效，不破坏既有数据
- 无迁移代码、无兼容读取代码，符合 S5 plan "fresh schema only" 约束

### 2. event_log payload_ref/payload_digest 成对 CHECK

**通过。**

DDL 变更 (`schema.py:194-199`):

```sql
-- 旧: CHECK (payload_ref IS NULL OR payload_digest IS NOT NULL)
-- 新:
CHECK (
  (payload_ref IS NULL AND payload_digest IS NULL)
  OR
  (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
)
```

Python 同源验证 (`event_log.py:665-669`):

```python
if payload_ref is None and payload_digest is None:
    return
if payload_ref is None or payload_digest is None:
    raise HostPayloadReferenceError(
        "EventLog payload_ref and payload_digest must be provided together"
    )
```

- SQL CHECK 与 Python `_validate_payload_reference` 逻辑同源：两者均要求成对出现或同时为空
- 合法 inline payload（两者均为 NULL）不受影响：`payload_ref IS NULL AND payload_digest IS NULL` 路径通过
- CHECK 不做 digest 格式校验（如 SHA256 pattern），与 Python 分层一致：format validation 留在 Python 层 (`event_log.py:671: is_sha256_digest`)
- 旧 CHECK (`payload_ref IS NULL OR payload_digest IS NOT NULL`) 允许 `payload_ref` 有值而 `payload_digest` 为 NULL——这是 Python 已拒绝的状态，SQL CHECK 收窄消除了 Python/DDL 不一致缺口

### 3. idempotency_records created_event_id/created_event_sequence 成对与正数 CHECK

**通过。**

DDL 变更 (`schema.py:222-226`):

```sql
-- 新增 CHECK 1: 成对引用
CHECK (
  (created_event_id IS NULL AND created_event_sequence IS NULL)
  OR
  (created_event_id IS NOT NULL AND created_event_sequence IS NOT NULL)
),
-- 新增 CHECK 2: sequence 必为正数
CHECK (
  created_event_sequence IS NULL OR created_event_sequence > 0
)
```

Python 同源验证 (`idempotency.py:249-258`):

```python
if (result.created_event_id is None) != (
    result.created_event_sequence is None
):
    raise HostDurableError(
        "created_event_id and created_event_sequence "
        "must be both set or both unset"
    )
if result.created_event_sequence is not None and result.created_event_sequence <= 0:
    raise HostDurableError(
        "created_event_sequence must be positive when provided"
    )
```

- 两 CHECK 与 Python validation 完全同源
- 无 `created_event` 的合法记录（两者均为 NULL）不受影响：两个 CHECK 的 NULL 路径均通过
- `created_event_sequence = 0` 同时触发 CHECK 2 (`0 > 0` 为 FALSE) 和 FK violation（`event_log.event_sequence` AUTOINCREMENT 从 1 起，0 无匹配行）——双重防御，非误伤

### 4. Direct SQLite insertion 测试真实绕过 Python API

**通过。**

测试使用 `store.connect()` 获取原始 `sqlite3.Connection`，直接执行 `INSERT` 语句：

- `test_event_log_schema_rejects_unpaired_payload_reference`：
  - 插入 `payload_ref` 有值、`payload_digest` NULL → `sqlite3.IntegrityError` ✓
  - 插入 `payload_digest` 有值、`payload_ref` NULL → `sqlite3.IntegrityError` ✓
  - 依赖 `_insert_payload_descriptor_probe` 先插入 FK 所需的 payload_descriptor row ✓
- `test_idempotency_schema_rejects_unpaired_event_reference`：
  - 插入 `created_event_id` 有值、`created_event_sequence` NULL → `sqlite3.IntegrityError` ✓
  - 插入 `created_event_sequence=1`、`created_event_id` NULL → `sqlite3.IntegrityError` ✓
  - 插入 `created_event_id` + `created_event_sequence=0` → `sqlite3.IntegrityError` ✓
  - 依赖 `_insert_event_log_probe` 先插入 FK 所需的 event_log row，AUTOINCREMENT 自动赋予正 sequence ✓
- 所有非法 row 均通过原始 `connection.execute(INSERT)` 构造，完全不经过 Python dataclass/validation/append API

### 5. 不引入旧库迁移/兼容读取、P10+ semantics、状态机或 public contract 变化

**通过。**

- 无迁移代码（无 ALTER TABLE、无旧 schema version 兼容路径）
- 无 P10+ 语义（无 compaction、memory history、proactive governance）
- 无新状态、新 table、新 column
- 无 public facade/error code/contract 变化
- `wait_records`、memory diagnostic event reference 等未稳定字段未添加额外 DDL 约束，避免把未来语义写死

## Residual Risk

- S5 CHECK 只收窄了 `event_log` 和 `idempotency_records` 两处。其它表中已存在的成对引用 CHECK（如 `host_sessions`、`host_runs`、`host_attempts`、`host_memory_snapshots` 等）在 schema 定义中已具备完整成对约束；本次未触碰，也未新增表。如果后续发现其它表存在 DDL/Python 不一致缺口，应作为独立 fix item 处理。
- `idempotency_records.created_event_sequence > 0` 的 CHECK 与 FK `REFERENCES event_log(event_sequence)` 都对 `sequence=0` 起防御作用。当 sequence=0 时 SQLite 可能先触发 CHECK 或先触发 FK（行为不保证），但两者都返回 `IntegrityError`，不影响功能正确性——测试无法区分是哪一条约束触发，但 rejection 本身就是正确行为。

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **五项审查点**: 全部通过
- **验证**: 71 tests passed (已由 implementation artifact 记录: pytest tests targeting schema/state/wait/projection/memory)
- **类型检查**: pyright 0 errors / 0 warnings
