# P9.5 S5 Schema CHECK Hardening — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S5 Schema CHECK Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S5.
- Implementation artifact: `docs/reviews/p9-5-s5-schema-check-hardening-implementation-20260517.md`.
- Reviewed files: `dayu/host/durable/schema.py`, `tests/host/test_durable_schema.py`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. Schema version 7→8 是否必要且只面向 fresh schema

**结论：通过。**

**必要性验证**（`schema.py`）：
- `HOST_SCHEMA_VERSION` 从 `7` 改为 `8`，原因是 `event_log` 表和 `idempotency_records` 表的 CHECK 约束发生变化。
- `bootstrap_schema` 在 fresh database 上执行 `CREATE TABLE IF NOT EXISTS`，CHECK 约束是 DDL 的一部分，版本号必须反映实际 schema 结构。
- `_validate_schema_version` 比对已打开数据库的 `user_version` pragma 与 `HOST_SCHEMA_VERSION`，不匹配时抛 `HostDurableSchemaMismatchError`。

**Fresh-only 验证**：
- 无 `ALTER TABLE`、无 `migration`、无兼容读取路径。
- 实现 artifact 已确认"一律按全新 schema 起库处理"。
- 测试使用 `:memory:` SQLite 连接，全部走 fresh bootstrap 路径。

### 2. event_log payload_ref/payload_digest 成对 CHECK 是否与 Python validation 同源，是否误伤 inline payload

**结论：通过。无误伤。**

**Python validation**（`event_log.py:652-672`，`_validate_payload_reference`）：
- `payload_ref is None and payload_digest is None` → pass（inline mode）。
- `payload_ref is None or payload_digest is None`（XOR）→ raise `HostPayloadReferenceError`。
- 两者皆非空 → 检查 SHA-256 digest 格式。

**DDL CHECK**（`schema.py:194-198`）：
```sql
CHECK (
  (payload_ref IS NULL AND payload_digest IS NULL)
  OR
  (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
)
```

**同源性**：Python XOR 检查与 SQLite CHECK 表达的是同一个不变量——两者必须同时为空或同时非空。

**Inline payload 不误伤**：`event_log` 表有 `payload_json TEXT NOT NULL`（`schema.py:189`），这是始终存在的 inline payload 载体。当 `payload_ref` 和 `payload_digest` 皆为 NULL 时，表示该 event 没有外部 payload 引用，event body 完全由 `payload_json` 承载——这是合法且常见的 inline mode，CHECK 允许两者皆 NULL。

**旧 CHECK 对比**：旧 CHECK 为 `payload_ref IS NULL OR payload_digest IS NOT NULL`，这允许 `payload_ref IS NOT NULL AND payload_digest IS NULL`（有 ref 无 digest）的非法状态。新 CHECK 关闭了这个缺口。

### 3. idempotency_records created_event_id/created_event_sequence 成对与正数 CHECK 是否与 Python validation 同源，是否误伤无 created_event 的合法记录

**结论：通过。无误伤。**

**Python validation**（`idempotency.py:236-259`，`_validate_result_ref`）：
- `(created_event_id is None) != (created_event_sequence is None)` → raise（XOR 检查）。
- `created_event_sequence is not None and created_event_sequence <= 0` → raise。
- 两者皆 None → pass（无 created event 的合法记录）。

**DDL CHECK**（`schema.py`）：
```sql
CHECK (
  (created_event_id IS NULL AND created_event_sequence IS NULL)
  OR
  (created_event_id IS NOT NULL AND created_event_sequence IS NOT NULL)
),
CHECK (
  created_event_sequence IS NULL OR created_event_sequence > 0
)
```

**同源性**：
- 成对 CHECK：与 Python XOR 检查（`idempotency.py:249-255`）完全对应。
- 正数 CHECK：与 Python `<= 0` 检查（`idempotency.py:256-259`）完全对应。

**无 created_event 记录不误伤**：idempotency 记录的 `created_event_id` 和 `created_event_sequence` 可以同时为 NULL（表示该幂等结果尚未关联到具体 event），成对 CHECK 的第一分支 `(IS NULL AND IS NULL)` 允许这种情况。

**旧 DDL 对比**：原 `idempotency_records` 表无任何 CHECK 约束，允许 `created_event_id` 和 `created_event_sequence` 单边出现或 sequence 为零/负数。新 CHECK 关闭了这些缺口。

### 4. Direct SQLite insertion tests 是否真实绕过 Python API 并覆盖非法 row

**结论：通过。**

**测试设计验证**（`test_durable_schema.py`）：
- `_insert_payload_probe`：使用 `cursor.execute()` 直接 INSERT 到 `event_log`，绕过 `EventLogStore.append_event()` Python API。
- `test_event_log_schema_rejects_unpaired_payload_reference`：
  - Case 1：`payload_ref = 'ref-xxx'`, `payload_digest = NULL` → `sqlite3.IntegrityError`。
  - Case 2：`payload_ref = NULL`, `payload_digest = 'abc123...'` → `sqlite3.IntegrityError`。
- `test_idempotency_schema_rejects_unpaired_event_reference`：
  - Case 1：`created_event_id = 'evt-xxx'`, `created_event_sequence = NULL` → `sqlite3.IntegrityError`。
  - Case 2：`created_event_id = NULL`, `created_event_sequence = 1` → `sqlite3.IntegrityError`。
  - Case 3：`created_event_id = 'evt-xxx'`, `created_event_sequence = 0` → `sqlite3.IntegrityError`。

**绕过路径确认**：测试直接使用 `cursor.execute()` + raw SQL INSERT，不经过任何 Python validation helper，确认 SQLite DDL 是独立的最终防线。

### 5. 是否引入旧库迁移/兼容读取、future P10+ semantics、状态机或 public contract 变化

**结论：通过。无违反。**

| 约束 | 验证 |
|---|---|
| 旧库迁移/兼容读取 | ✅ 无 ALTER TABLE、无 migration、无兼容读取 |
| P10+ semantics (RECOVERING, ToolsDiscovery 等) | ✅ 未引入 |
| 新状态机状态或转换 | ✅ 未引入 |
| 新 public facade 或 public error code | ✅ 未引入 |
| 新 schema 表 | ✅ 未引入，只收紧现有表的 CHECK |
| 兼容 wrapper / re-export | ✅ 未引入 |
| `Any`/`object`/无类型签名 | ✅ 未引入 |

## Findings

### F1 [Info] 旧 CHECK 允许的非法状态被新 CHECK 关闭

- **File/line**: `schema.py:194-198`（event_log）、`schema.py` idempotency_records CHECK
- **Evidence**: 旧 event_log CHECK `payload_ref IS NULL OR payload_digest IS NOT NULL` 允许 `payload_ref IS NOT NULL AND payload_digest IS NULL`；旧 idempotency_records 无 CHECK。新 CHECK 关闭了这两个缺口。
- **Impact**: 纵深防御。Python validation 已阻止这些非法状态，SQLite CHECK 是 DDL 级别的最终防线，防止绕过 Python API 的 direct insertion。
- **Blocking**: No.

### F2 [Info] Python validation 比 SQLite CHECK 更严格

- **File/line**: `event_log.py:663-664`（`_require_optional_non_empty_text`）+ `event_log.py:671-672`（`is_sha256_digest`）；`idempotency.py:244-245`（`_require_non_empty_text`）
- **Evidence**: Python 层额外校验：`payload_ref`/`payload_digest` 非空字符串、`payload_digest` 必须是合法 SHA-256 hex、`result_kind`/`result_ref`/`created_event_id` 非空字符串。SQLite CHECK 不覆盖这些格式约束。
- **Impact**: 设计正确。SQLite CHECK 覆盖结构性不变量（成对性、正数性），Python validation 覆盖格式不变量（非空、SHA-256）。两者职责不重叠。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`schema.py`、`test_durable_schema.py`。
- 未修改 public facade、public error code、状态机语义。
- 未新增 schema 表，只收紧现有表的 CHECK 约束。

### Confirmed: no prohibited semantics introduced

- No P10+ semantics (RECOVERING, ToolsDiscovery, etc.)
- No new state-machine states or transitions
- No compatibility re-export/wrapper
- No `Any`/`object`/untyped signatures
- No migration or compatibility reads

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| New state-machine states | Not introduced |
| New schema tables | Not introduced |
| Public facade changes | Not introduced |
| RECOVERING / Phase 11 | Not introduced |
| Compatibility wrapper | Not introduced |
| Migration / compat reads | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 2 (F1–F2)

S5 实现正确达成计划目标：`HOST_SCHEMA_VERSION` bump 7→8 面向 fresh schema；`event_log` payload reference CHECK 与 `EventLogStore._validate_payload_reference` 同源，不误伤 inline payload（`payload_json TEXT NOT NULL` 始终承载 event body）；`idempotency_records` created event reference CHECK 与 `IdempotencyStore._validate_result_ref` 同源，不误伤无 created_event 的合法记录；direct SQLite insertion tests 真实绕过 Python API 并覆盖所有非法 row 模式。无硬约束违反。
