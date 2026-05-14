# Gateflow Code Review: Host Phase 2 Slice 1 Durable Schema / Transaction

## Review Gate

- gate name: `Phase 2 Slice 1 code review`
- work unit: Host Phase 2 Durable Store / EventLog / Payload Foundation
- assigned slice: Slice 1 - SQLite Schema Convention / Fresh DB Bootstrap / Transaction Runner

## Reviewed Target

- accepted plan commit: `83c6ad6`
- approved plan: `docs/host/phase2-durable-store-eventlog-plan.md`
- implementation artifact: `docs/reviews/gateflow-implementation-host-p2-s1-durable-schema-transaction-20260514.md`
- controller decision: `docs/reviews/gateflow-implementation-decision-host-p2-s1-sqlite-payload-table-name-20260514.md`
- reviewed files:
  - `dayu/host/durable/__init__.py`
  - `dayu/host/durable/errors.py`
  - `dayu/host/durable/codec.py`
  - `dayu/host/durable/options.py`
  - `dayu/host/durable/schema.py`
  - `dayu/host/durable/connection.py`
  - `dayu/host/durable/transaction.py`
  - `tests/host/test_durable_schema.py`
  - `tests/host/test_durable_transaction.py`
  - `docs/host/phase2-durable-store-eventlog-plan.md` (table-name patch)

## Reviewer

MiMo

## Reviewer Conclusion

**No findings.** Slice 1 实现正确对齐 approved plan，无阻塞问题。

## Review Summary

### Correctness Verification

1. **SQLite Schema DDL** (`schema.py`): 5 个 foundation DDL 完整对应 plan §Contract / Schema 中的表定义。`event_log` 使用 `AUTOINCREMENT`、`UNIQUE event_id`、`CHECK event_class IN (...)`、FK 到 `payload_descriptors`、`CHECK (payload_ref IS NULL OR payload_digest IS NOT NULL)`。`host_sqlite_payloads` 使用 `CHECK payload_format IN (...)` 和跨列 `CHECK` 约束确保 format 与 json/bytes 列一致。`payload_descriptors` 使用 `CHECK payload_kind IN (...)` 和跨列 `CHECK` 确保 kind 与 sqlite_payload_id/artifact_relative_path 一致。`idempotency_records` 使用复合 PK 和 FK 到 `event_log`。`host_instances` 使用 `CHECK pid > 0` 和 `CHECK status IN (...)`。DDL 顺序正确：`host_sqlite_payloads` → `payload_descriptors` → `event_log` → `idempotency_records` → `host_instances`，满足 FK 依赖。

2. **PRAGMA Setup** (`transaction.py:251-267`): `configure_connection_pragmas` 设置 `busy_timeout`（毫秒换算）、`foreign_keys=ON`、`journal_mode=WAL`。测试 `test_fresh_db_creates_foundation_tables_and_pragmas` 和 `test_wal_persists_on_second_independent_connection` 验证 WAL 模式持久化到独立 connection。

3. **Bootstrap Idempotency** (`schema.py:157-180`): `bootstrap_host_durable_store` 使用 `CREATE TABLE IF NOT EXISTS` 实现幂等。`user_version=0` 时创建表并设版本；`user_version=1` 时幂等执行 DDL；其它版本抛出 `HostSchemaMismatchError`。测试 `test_bootstrap_is_idempotent_for_matching_schema` 验证。

4. **Schema Version Mismatch** (`schema.py:170-175`): 非 0 且非当前版本时抛出 `HostSchemaMismatchError`，不做兼容读取或迁移。测试 `test_schema_mismatch_raises_structured_error` 验证 `user_version=2` 时抛出。

5. **Transaction Runner** (`transaction.py:192-248`):
   - `BEGIN IMMEDIATE` 写事务语义正确。
   - busy/locked 有限重试：`max_attempts = write_busy_retry_count + 1`，指数退避，上限 `write_retry_max_delay_seconds`。
   - `_is_busy_or_locked` 基于 `sqlite_errorcode` 属性而非消息字符串猜测。
   - `_classify_sqlite_error` 将 UNIQUE/PRIMARYKEY 映射为 `HostUniqueConstraintError`，FOREIGNKEY 映射为 `HostForeignKeyError`，其它映射为通用 `HostDurableError`。非约束错误不进入 busy retry 路径。
   - rollback 在所有失败路径（sqlite3.Error、HostDurableError、Exception）上执行。
   - after-commit 仅在 COMMIT 成功后执行。
   - after-commit 失败抛出 `HostAfterCommitError`，durable row 保持 committed。

6. **Canonical JSON / UTC Timestamp / Digest** (`codec.py`): `canonical_json_dumps` 使用 `sort_keys=True, separators=(",", ":"), allow_nan=False`。`format_utc_timestamp` 要求 timezone-aware，输出 `%Y-%m-%dT%H:%M:%S.%fZ`。`parse_utc_timestamp` 使用 `fullmatch` 正则验证固定格式。`sha256_digest_bytes` 输出 `sha256:<64 hex>`。

7. **HostTransaction Typed Wrapper** (`transaction.py:105-167`): 仅暴露 `execute`、`fetchone`、`fetchall`，不泄漏 `sqlite3.Connection`。`SQLParameters` 为 `tuple[SQLiteScalar, ...] | Mapping[str, SQLiteScalar]`。`HostRow` 和 `HostExecuteResult` 为 frozen dataclass。无 `Any`、`object`、无类型签名。

8. **Options Validation** (`options.py`): `HostSQLiteStoragePolicy` 校验 busy_timeout 正数、retry_count 非负、延迟正数。`PayloadStoragePolicy` 校验 artifact_root 有名称、阈值正数。`HostDurableStoreOptions` 校验 db_path 有名称。默认值通过 dataclass 字段默认值实现，无隐藏单例。

9. **Connection Factory** (`connection.py`): `open_host_durable_store` 准备 parent dir → 打开 raw connection → 配置 PRAGMA → bootstrap → validate → 返回 store。失败时关闭 connection。`HostDurableStore` 提供 context manager、close、connect（独立 connection）、transaction_runner 属性。

### Boundary Verification

1. **dayu.runtime 未被污染**: `dayu/host/durable/` 未 import `dayu.runtime`、`dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`。已 grep 验证。

2. **dayu.host 包根未泄漏 durable**: `dayu/host/__init__.py` 的 `__all__` 和 import 均不包含 `durable` 子包。

3. **无 Slice 2/3 行为**: 未实现 EventLog append/read、idempotency behavior、payload descriptor helper、artifact helper、host instance liveness behavior。仅包含 schema/types/DDL/transaction runner。

4. **无未来 phase 表**: 测试 `test_schema_does_not_create_future_phase_tables` 验证不存在 session/run/attempt/wait/projection/outbox/memory/purge 表。

5. **无兼容性 re-export / wrapper / facade**: `__init__.py` 仅含 docstring，无 re-export。

### Test Quality Verification

1. **Schema Tests** (`test_durable_schema.py`, 7 tests): fresh DB bootstrap、idempotent bootstrap、schema mismatch、WAL 持久化、PK/unique/FK 约束、无未来 phase 表。覆盖了 plan 要求的所有 schema 断言。

2. **Transaction Tests** (`test_durable_transaction.py`, 8 tests): commit + after-commit、rollback 无 after-commit、after-commit 失败保留 committed row、busy/locked 有限重试、unique/FK 不重试、schema/domain 错误不重试、fetch helpers 返回 typed row、codec helper。覆盖了 plan 要求的所有 transaction 断言。

3. 测试不依赖脆弱时序：busy retry 测试使用极短延迟和确定性锁持有，断言基于结构性不变量（operation_calls/callback_events 为空、attempts 计数）而非精确时间。

### Chinese Docstrings

所有模块、类、函数均提供中文 docstring，包含 `:param`、`:returns`、`:raises`。行内注释使用中文。符合项目约束。

### Type Signatures

pyright 通过，0 errors。无 `Any`、`object`、无类型参数/返回值。`getattr` 在 `transaction.py:338` 的使用有充分理由（Python 3.11 运行时属性声明不足）。

## Findings

无。

## Open Questions / Residual Risk

1. **`HostTransactionBusyError` 声明但未使用**: `errors.py:38-39` 声明了 `HostTransactionBusyError`，但 transaction runner 的重试路径在单次 busy/locked 时直接重试、耗尽时抛出 `HostTransactionRetryExhaustedError`，没有实例化 `HostTransactionBusyError`。这是 plan 声明的错误类型，保留供后续 slice 或外部调用方使用。风险级别：无（不影响正确性）。

2. **busy retry 测试极短延迟**: `test_durable_transaction.py:38-39` 使用 `busy_timeout_seconds=0.01` 和 `write_retry_initial_delay_seconds=0.001`。在极端慢 CI 上可能偶发 timing 问题，但测试断言基于结构性不变量而非精确时间，实际风险极低。

3. **`_classify_sqlite_error` 通用兜底**: 非约束、非忙/锁的 SQLite 错误映射为通用 `HostDurableError`。Slice 1 范围内合理；后续 slice 如需更精确的 schema 错误分类可扩展此函数。

## Controller Decision Status

`pending-controller-decision`

## Artifact Path

`docs/reviews/gateflow-code-review-host-p2-s1-durable-schema-transaction-mimo-20260514.md`
