# Gateflow Code Review Artifact: Host Phase 2 Slice 1 Durable Schema / Transaction

## Review Gate

- **gate name**: code review
- **reviewed target**: Host Phase 2 Slice 1 — SQLite Schema Convention / Fresh DB Bootstrap / Transaction Runner
- **reviewed diff**: current workspace (`feat/host-phase2-durable-store-eventlog`) relative to accepted plan commit `83c6ad6`
- **approved plan**: `docs/host/phase2-durable-store-eventlog-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p2-s1-durable-schema-transaction-20260514.md`
- **controller decision**: `docs/reviews/gateflow-implementation-decision-host-p2-s1-sqlite-payload-table-name-20260514.md`
- **reviewer**: Claude Opus 4.6 (deepreview agent)
- **review date**: 2026-05-14

## Reviewed Files

### Production (7 files)

- `dayu/host/durable/__init__.py` — 包概览 docstring
- `dayu/host/durable/errors.py` — Phase 2 durable 结构化错误类型
- `dayu/host/durable/codec.py` — canonical JSON、UTC timestamp、sha256 digest helper
- `dayu/host/durable/options.py` — `HostSQLiteStoragePolicy`、`PayloadStoragePolicy`、`HostDurableStoreOptions`
- `dayu/host/durable/schema.py` — foundation table 常量、DDL、bootstrap、schema version 校验
- `dayu/host/durable/connection.py` — `HostDurableStore`、`open_host_durable_store`、connection lifecycle
- `dayu/host/durable/transaction.py` — `HostTransaction`、`HostTransactionRunner`、`AfterCommitCallback`、typed row/result wrappers

### Tests (2 files)

- `tests/host/test_durable_schema.py` — schema bootstrap、PRAGMA、constraint、future-table 检查
- `tests/host/test_durable_transaction.py` — commit/rollback/after-commit、busy retry、constraint 非重试、codec helper

### Plan patch (1 file)

- `docs/host/phase2-durable-store-eventlog-plan.md` — `sqlite_payloads` → `host_sqlite_payloads` per controller decision

## Review Scope

Per review instructions, the review focused on:

1. SQLite schema DDL correctness, PRAGMA setup, bootstrap idempotency, schema version mismatch
2. Transaction runner `BEGIN IMMEDIATE`, retry only busy/locked, rollback semantics, after-commit after durable commit only
3. No broad message-guessing for SQLite errors; no retry for non-busy/non-locked errors
4. canonical JSON and UTC timestamp helpers comply with plan and strict typing
5. `HostTransaction` typed wrapper does not leak raw `sqlite3.Connection` and avoids `Any`/`object`/untyped signatures
6. `dayu.runtime` boundary is not polluted; no Engine/Fins/Service/UI imports
7. No Slice 2/3 behavior beyond schema/types needed by Slice 1
8. Tests are meaningful, do not assert brittle timing/order
9. Chinese docstrings and type signatures satisfy project constraints

## Reviewer Conclusion

**No findings.** All review dimensions pass with zero violations.

## Detailed Review Evidence

### 1. SQLite Schema DDL & PRAGMA Setup

- `schema.py:15-30` — 表名常量与 foundation table 集合，物理表名使用 `host_sqlite_payloads`（已执行 controller 决策）
- `schema.py:33-153` — DDL 与计划完全一致：`event_log`（`AUTOINCREMENT`、`UNIQUE` on `event_id`、`CHECK event_class`、`payload_ref` FK to `payload_descriptors`、`CHECK payload_ref/payload_digest`）、`idempotency_records`（composite PK `scope_kind, scope_id, idempotency_key`、FK to `event_log`）、`host_sqlite_payloads`（`CHECK payload_format`、`CHECK payload_json/payload_bytes` 互斥）、`payload_descriptors`（`CHECK payload_kind`、`CHECK sqlite_payload_id/artifact_relative_path` 互斥、FK to `host_sqlite_payloads`）、`host_instances`（`CHECK pid > 0`、`CHECK status`）
- `schema.py:157-180` — `bootstrap_host_durable_store` 对 `user_version=0` 执行 fresh create，`user_version=1` 幂等，其他版本抛出 `HostSchemaMismatchError`
- `connection.py:251-267` — `configure_connection_pragmas` 设置 `busy_timeout`、`foreign_keys=ON`、`journal_mode=WAL`
- `connection.py:147-158` — `open_host_durable_store` 依次执行 parent dir 准备 → raw connection → PRAGMA → bootstrap → validate
- 验证：`test_wal_persists_on_second_independent_connection` 通过第二条独立 connection 证明 WAL 持久化

### 2. Transaction Runner Semantics

- `transaction.py:192-248` — `run_write` 使用 `BEGIN IMMEDIATE`，单次 `COMMIT`，`_rollback` 在 `sqlite3.Error`/`HostDurableError`/`Exception` 三个异常分支均执行
- `transaction.py:316-324` — `_is_busy_or_locked` 仅匹配 `SQLITE_BUSY` 和 `SQLITE_LOCKED` 两个 numeric code
- `transaction.py:327-341` — `_sqlite_error_code` 使用 `getattr(error, "sqlite_errorcode", None)` 读取 runtime 属性，注释中说明了理由（兼容类型 stub 对 `sqlite_errorcode` 声明不足），不是字符串消息猜测
- `transaction.py:301-313` — `_classify_sqlite_error` 仅分类 `SQLITE_CONSTRAINT_UNIQUE`/`SQLITE_CONSTRAINT_PRIMARYKEY` → `HostUniqueConstraintError`、`SQLITE_CONSTRAINT_FOREIGNKEY` → `HostForeignKeyError`，其他 fallthrough 到通用 `HostDurableError`，不猜测消息
- `transaction.py:283-298` — `_run_after_commit` 仅在 commit 成功后执行（不在任何异常处理分支内）；callback 失败抛出 `HostAfterCommitError` 且不回滚
- 验证：`test_after_commit_failure_preserves_durable_commit` 独立 connection 读取确认 row 仍然存在（committed row remains visible）

### 3. Retry Policy — Only Busy/Locked

- 重试循环 `max_attempts = write_busy_retry_count + 1`（含首次尝试），指数退避上限 `write_retry_max_delay_seconds`
- `_is_busy_or_locked` 返回 `False` 时直接 `raise durable_error` 不重试
- 验证：`test_unique_and_foreign_key_errors_are_not_retried` 使用 `retry_count=5`，unique/FK 错误仅一次调用即抛出
- 验证：`test_schema_and_domain_errors_are_not_retried` → generic SQLite error 和 `HostSchemaMismatchError` 均仅一次调用即抛出

### 4. Canonical JSON & UTC Timestamp

- `codec.py:24-39` — `canonical_json_dumps` 使用 `sort_keys=True`、`separators=(",", ":")`、`allow_nan=False`
- `codec.py:42-53` — `format_utc_timestamp` 拒绝 naive datetime（`ValueError`），转 UTC 后固定 `%Y-%m-%dT%H:%M:%S.%fZ`
- `codec.py:56-67` — `parse_utc_timestamp` 先正则 `fullmatch` 校验格式再 `strptime`，拒绝缺微秒 / 缺 `Z` / 含时区偏移的变体格式
- `codec.py:70-89` — digest 格式 `sha256:<64 lowercase hex>`，JSON digest 先 canonical 编码再 sha256 bytes
- 验证：`test_codec_canonical_json_timestamp_and_digest` 覆盖 key 顺序稳定性、NaN 拒绝、时区转换、格式拒绝、digest 确定性

### 5. HostTransaction Typed Wrapper — No Raw Connection Leak

- `HostTransaction._connection` 为私有字段，不通过公共属性暴露
- `HostTransaction.execute` / `fetchone` / `fetchall` 返回 `HostExecuteResult` / `HostRow | None` / `tuple[HostRow, ...]`
- `SQLiteScalar` = `None | int | float | str | bytes`，`SQLParameters` = `tuple[SQLiteScalar, ...] | Mapping[str, SQLiteScalar]`，`HostRow.values` = `tuple[SQLiteScalar, ...]`
- 所有签名严格类型化，无 `Any`、`object`、裸 builtin 容器
- `_build_host_row` 中 `cast(tuple[SQLiteScalar, ...], tuple(row))` 是必要的类型收窄，配合 `cursor.description` 提取列名

### 6. Boundary Pollution Check

- `dayu/host/durable/` 下无任何 `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui` import（grep 确认为空）
- `dayu/host/durable/` 下无 `dayu.runtime` import
- `tests/host/test_package_exports.py` 通过 — durable foundation 未进入 `dayu.host.__all__`
- `tests/host/test_import_boundary.py` 通过 — 无跨层违规 import
- `tests/host/test_weak_typing_guard.py` 通过 — 无弱类型违规

### 7. No Slice 2/3 Behavior Leaks

- 不存在 `event_log.py`、`idempotency.py`、`payload.py`、`artifact.py`、`liveness.py` 文件
- schema DDL 创建了所有 Phase 2 foundation tables（这是 Slice 1 的允许行为，plan 明确要求）
- 错误类型声明了后续 slice 需要但当前未使用的类型（`HostDigestMismatchError`、`HostIdempotencyConflictError` 等） — 这是 plan 要求的 error taxonomy
- `HostTransactionBusyError` 声明但未在 Slice 1 使用 — plan error taxonomy 的一部分，runner 通过 `HostTransactionRetryExhaustedError` 暴露重试耗尽，不暴露单次 busy
- 无 `append_event`、`record_idempotent_result`、`write_sqlite_payload`、`write_artifact_bytes`、`register_current_instance` 等 Slice 2/3 函数实现

### 8. Test Quality

- 所有测试使用 `tmp_path` fixture，不依赖外部文件系统状态
- `test_busy_locked_retries_are_finite` 通过 holding `BEGIN IMMEDIATE` 制造确定性 busy 场景，不依赖 sleep/timing
- `test_unique_and_foreign_key_errors_are_not_retried` 设置 `retry_count=5` 证明不进入重试
- `test_wal_persists_on_second_independent_connection` 通过独立 connection 证明 WAL 不是 connection-local 假象
- `test_schema_does_not_create_future_phase_tables` 通过 fragment 黑名单防御性检查
- 没有对 timing/order 的脆弱断言

### 9. Chinese Docstrings & Project Constraints

- 所有模块、类、函数均有中文 docstring（含参数、返回值、异常说明）
- `_sqlite_error_code` 的 `getattr` 使用有明确注释说明理由（兼容类型 stub），符合项目 `getattr` 必须充分理由的约束
- 无兼容性 re-export、wrapper、facade
- 无魔法数字/字符串（常量均提取为模块级私有变量如 `_DIGEST_PREFIX`）

## Open Questions / Residual Risk

1. **after-commit 采用 fail-fast 而非 aggregate 语义**：当前 `_run_after_commit` 在第一个 callback 失败时立即 `raise HostAfterCommitError`，不执行后续 callback。plan 原文为 "raises or aggregates"，当前选择 "raises" 路径，符合 plan 允许的歧义空间。如果未来有多个 after-commit callback 且需要全部执行后才报告，需改为 aggregate 语义。

2. **`HostTransactionBusyError` 未被 Slice 1 使用**：该错误类型在 `errors.py:38` 声明但 runner 内部消化 busy/locked 为 retry → `HostTransactionRetryExhaustedError`。plan error taxonomy 要求声明但未强制 Slice 1 使用。后续 slice 如需区分单次 busy（不重试场景）可使用该类型。

3. **bootstrap 部分失败**：`bootstrap_host_durable_store` 中 DDL 语句为 `CREATE TABLE IF NOT EXISTS`，且 bootstrap 在 `isolation_level=None` 下运行（DDL 自动提交）。如果中途失败，部分 table 可能已创建但 `user_version` 仍为 0，下次 `open_host_durable_store` 会重新进入 bootstrap。plan 明确拒绝旧库兼容迁移，此行为可接受。

4. **`_rollback` 静默吞掉 rollback 失败**：如果 connection 在异常状态下 ROLLBACK 本身也失败，`_rollback` 吞掉异常。这是 best-effort 语义，核心不变量（after-commit 不触发）保持成立。

## Controller Decision Status

pending-controller-decision

## Artifact Path

`docs/reviews/gateflow-code-review-host-p2-s1-durable-schema-transaction-ds-20260514.md`
