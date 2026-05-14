# Gateflow Code Review: Host P3-S1 Schema And Row Codecs

- **review gate name**: code review
- **reviewed target**: Host Phase 3 P3-S1 Schema And Row Codecs
- **reviewed artifact**: `docs/reviews/gateflow-implementation-host-p3-s1-schema-row-codecs-20260514.md`
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md`, P3-S1 section
- **accepted plan commit**: `71ddcba`
- **reviewer**: mimo
- **reviewer conclusion**: **approve with 2 low-severity observations**. 无 blocking finding，不要求 fix。slice 可以推进到下一 gate。

## Review Scope

- `dayu/host/durable/schema.py` — DDL 真源、schema version、bootstrap DDL order
- `dayu/host/durable/state.py` — row dataclass、status serializer/deserializer、HostRow 转换
- `tests/host/test_state_schema.py` — schema 与 codec 测试
- `tests/host/test_durable_schema.py` — 既有 schema 测试适配
- `dayu/host/README.md` — narrow truth sync

## Review Criteria Verification

### 1. Schema version 2 and bootstrap DDL order

**通过。**

- `HOST_SCHEMA_VERSION = 2`（`schema.py:14`）。
- `HOST_DURABLE_DDL = FOUNDATION_DDL + PHASE3_STATE_DDL + PHASE3_INDEX_DDL`（`schema.py:423-426`），FK-safe order：foundation tables → Phase 3 state tables → Phase 3 indexes。
- `bootstrap_host_durable_store` 使用 `HOST_DURABLE_DDL`（`schema.py:448`）。
- `user_version=0` 视为 fresh DB，`user_version=HOST_SCHEMA_VERSION` 幂等执行，其它版本 `HostSchemaMismatchError`。
- 无兼容迁移、兼容读取或旧 schema fallback。

### 2. Phase 3 tables match approved plan

**通过。**

逐表对比：

| 表 | PK | 列 | CHECK / FK | 状态 |
|---|---|---|---|---|
| `host_sessions` | `session_id TEXT PK` | status, metadata_json, created/closed event refs, timestamps | status IN ('open','closed'); closed fields both-null or both-non-null; open→closed fields null, closed→closed fields non-null | match |
| `host_session_slots` | `(scope, slot_key)` | session_id, bound event refs, metadata_json, updated_at | FK to sessions, event_log | match |
| `host_runs` | `run_id TEXT PK` | session_id, status (9 values), event refs, source_run, execution_target, queue_policy, timestamps | queued CHECK, terminal/non-terminal CHECK, source_run both-null-or-both-non-null | match |
| `host_attempts` | `attempt_id TEXT PK` | run_id, execution_id UNIQUE, status (8 values), event refs, timestamps | terminal/non-terminal CHECK | match |
| `host_attempt_dispatch_records` | `dispatch_record_id TEXT PK` | run_id, attempt_id UNIQUE, execution_id UNIQUE, status, worker_kind, execution_target, owner_host_instance_id, event refs, timestamps | status IN ('pending','cancelled'); pending→cancelled fields null, cancelled→cancelled fields non-null | match |

- Phase 3 dispatch record CHECK 只允许 `pending`/`cancelled`（`schema.py:349`），与 plan §4 一致。
- `host_runs` 未添加 `UNIQUE(session_id, client_request_id)`，与 plan §4 一致（idempotency 由 `idempotency_records` 承载）。

### 3. Active Run partial unique index

**通过。**

- DDL（`schema.py:381-385`）：`CREATE UNIQUE INDEX host_runs_one_active_per_session ON host_runs(session_id) WHERE status IN ('running', 'waiting', 'cancelling', 'recovering')`，与 plan §4 完全一致。
- `PHASE3_INDEX_DDL` tuple 顺序正确：先建表后建索引。
- 测试 `test_active_run_partial_unique_index_shape`（`test_state_schema.py:69-104`）：验证索引存在、unique、partial、列为 `session_id`、WHERE 包含全部 4 个 active status。
- 测试 `test_two_active_runs_for_one_session_fail_structurally`（`test_state_schema.py:136-175`）：插入 RUNNING 后插入 WAITING 抛 `HostUniqueConstraintError`。
- 测试 `test_active_runs_for_different_sessions_succeed`（`test_state_schema.py:178-211`）：不同 Session 各一个 active Run 成功。

### 4. Queue FIFO index

**通过。**

- DDL（`schema.py:387-390`）：`CREATE INDEX host_runs_queue_fifo ON host_runs(session_id, accepted_event_sequence, run_id) WHERE status = 'queued'`，与 plan §4 一致。
- 测试 `test_queue_fifo_index_shape`（`test_state_schema.py:107-133`）：验证索引存在、非 unique、partial、列为 `(session_id, accepted_event_sequence, run_id)`。
- 测试 `test_multiple_queued_runs_for_one_session_succeed`（`test_state_schema.py:214-249`）：同一 Session 多个 queued Run 成功。

### 5. Row dataclasses/codecs 强类型

**通过。**

- 所有 row dataclass 使用 `@dataclass(frozen=True, slots=True)`。
- 字段类型全部显式标注：`str`、`int`、`str | None`、`int | None`、`SessionStatus`、`RunStatus`、`AttemptStatus`、`SourceRunRelation | None`、`DispatchRecordStatus`、`WorkerKind`。
- 无 `Any`、`object`、无类型参数、无类型返回值。
- 内部 enum：`DispatchRecordStatus`、`WorkerKind`、`RunStartReason`，全部 `StrEnum`。
- serializer/deserializer 使用 `_serialize_str_enum` / `_deserialize_str_enum` 私有 helper，通过 `_StatusT = TypeVar("_StatusT", bound=StrEnum)` 泛型化。
- `HostRow` 转换 helper 全部使用 `_validation` 模块的 typed helper（`require_text`、`optional_text`、`require_int`、`optional_int`、`require_non_empty_text`）。
- 无 command logic、无 EventLog append。

### 6. 无 reverse dependency

**通过。**

- `state.py` imports：`dayu.host.api`（public status enums）、`dayu.host.durable._validation`、`dayu.host.durable.errors`、`dayu.host.durable.transaction`。
- `schema.py` imports：`dayu.host.durable.errors`。
- 无 `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`、`dayu.runtime` 反向依赖。
- 无 future-slice behavior（admission、promotion、cancel、dispatch 均未实现）。

### 7. 测试直接证明 required assertions

**通过。**

plan P3-S1 要求的测试断言与实现对应：

| Plan 要求 | 测试 | 状态 |
|---|---|---|
| fresh DB 创建 foundation + Phase 3 tables | `test_fresh_db_creates_foundation_and_phase3_tables` | match |
| `PRAGMA user_version` 是 2 | 同上 + `assert HOST_SCHEMA_VERSION == 2` | match |
| `host_runs_one_active_per_session` 存在且为 partial unique on active statuses | `test_active_run_partial_unique_index_shape` | match |
| 同一 Session 插入两个 active runs 失败 | `test_two_active_runs_for_one_session_fail_structurally` | match |
| 不同 Session 的 active runs 成功 | `test_active_runs_for_different_sessions_succeed` | match |
| 同一 Session 多个 queued runs 成功 | `test_multiple_queued_runs_for_one_session_succeed` | match |
| dispatch record status CHECK 只允许 pending/cancelled | `test_dispatch_record_status_check_only_allows_pending_cancelled` | match |
| schema mismatch 仍结构化失败 | `test_schema_mismatch_raises_structured_error` | match |
| row codec round trip | `test_state_row_codecs_round_trip_from_host_rows` | match |

### 8. README change is current-fact sync

**通过。**

- `dayu/host/README.md` 变更（diff 第 46-48 行）：
  - 新增一行：`Phase 3 state schema / row codec：创建 Session、slot、Run、Attempt 与 attempt dispatch record durable tables；typed row codec 只负责状态枚举与 SQLite row 转换。` — 与当前代码事实一致。
  - 旧句更新：`不实现 ... Session / Run / Attempt 状态机 ...` 改为 `不实现 ... Session / Run / Attempt lifecycle command、admission、promotion、cancel ...` — 反映 P3-S1 已创建 schema/codec 但未实现 command 的事实。
- 无未来设计、无过程状态、无旧术语残留。

### 9. Implementation artifact validation results

**通过。**

- artifact 报告 `14 passed in 0.13s`，实际运行确认 `14 passed in 0.12s`。
- artifact 报告 `0 errors, 0 warnings, 0 informations`，实际运行确认一致。
- validation commands 与 plan §7 P3-S1 一致。

## Findings

### P3S1-MIMO-001-已修复-低-测试未验证 active partial unique index 拒绝 terminal status 组合

- **入口/函数**: `test_active_run_partial_unique_index_shape` / `test_two_active_runs_for_one_session_fail_structurally`
- **文件(行号)**: `tests/host/test_state_schema.py:69-175`
- **输入场景**: 同一 Session 插入一个 active Run（RUNNING）后，再插入一个 terminal Run（SUCCEEDED / FAILED / CANCELLED / LOST）
- **实际分支**: 测试只验证 RUNNING + WAITING 的 active 组合被拒绝
- **预期行为**: terminal status 不在 partial unique index WHERE 子句中，同一 Session 应允许同时存在 active Run 和 terminal Run
- **实际行为**: 未测试此路径。partial unique index DDL 正确（WHERE 子句只含 running/waiting/cancelling/recovering），但测试缺少对此正确性的直接证明
- **直接证据**: `schema.py:384` 的 WHERE 子句正确排除 terminal status；`test_state_schema.py:136-175` 只测 RUNNING + WAITING
- **影响**: 低。index DDL 本身正确，测试已覆盖 active→active 拒绝。缺少的是 terminal→active 允许的正面证明，不影响生产正确性
- **建议改法和验证点**: 可选增强：在 `test_active_runs_for_different_sessions_succeed` 中增加一个 terminal Run，验证 terminal + active 共存。不改也可以通过后续 slice 测试自然覆盖
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: `accepted` → `已修复`（见 `gateflow-code-re-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`）

### P3S1-MIMO-002-未修复-低-_serialize_str_enum 的 isinstance 校验可被非 StrEnum 的 Str 子类绕过

- **入口/函数**: `_serialize_str_enum`
- **文件(行号)**: `dayu/host/durable/state.py:510-522`
- **输入场景**: 传入一个继承 `str` 但不是 `StrEnum` 的值
- **实际分支**: `isinstance(value, StrEnum)` 为 False，但 `value.value` 可能存在（如果对象恰好有 `.value` 属性）
- **预期行为**: 非 StrEnum 值应被拒绝
- **实际行为**: 当前逻辑正确拒绝非 StrEnum（`isinstance` 检查在前），但如果未来有人传入一个有 `.value` 属性的普通对象，`_require_non_empty_text` 可能意外通过
- **直接证据**: `state.py:519-522`：先 `isinstance(value, StrEnum)` 再 `_require_non_empty_text(value.value)`
- **影响**: 低。当前所有调用点传入的都是正确的 StrEnum 实例，此路径无法被触发。属于防御性代码审查观察
- **建议改法和验证点**: 不需要改。当前 isinstance 检查已经足够。如果未来要更严格，可以用 `type(value).__mro__` 检查，但这属于过度防御
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: `rejected-with-reason`（controller 裁决：触发路径不成立，isinstance 检查已足够，过度防御非本 slice 必要修复）

## Open Questions / Residual Risk

无 blocking open questions。

Residual risks（全部由后续 slice 覆盖，非 P3-S1 遗留）：

- Session lifecycle command / slot idempotency → P3-S2
- Run / Attempt transition helpers and CAS updates → P3-S3
- Admission, FIFO promotion, cancel, terminal closeout → P3-S4 / P3-S5
- Multiprocess race proofs → P3-S6
- Old DB migration → 不在 Phase 3 范围内（fresh schema only）

## Artifact Path

`docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`

## Summary

- **finding 数量**: 2
- **blocking finding 数量**: 0
- **是否建议 fix**: 否。两个 finding 均为低严重度观察，不要求在 P3-S1 修复。slice 可以推进到下一 gate。
