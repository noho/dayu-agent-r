# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: `main` (committed: `b85fd8e`)
- Output file: `docs/reviews/host-phase8-code-review-s1-mimo-20260516.md`
- Included scope: `dayu/host/durable/schema.py`, `dayu/host/durable/projection.py`, `dayu/host/projection.py`, `tests/host/test_durable_schema.py`, `tests/host/test_projection_checkpoint.py`, `tests/host/test_projection_runner.py`, `tests/host/test_import_boundary.py`, `tests/README.md`
- Excluded scope: all other files per plan §7 P8-S1 allowed files
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Blocking Criteria Verification

按 plan §5 和 §7 blocking criteria 逐项验证：

| Blocking Criterion | Result | Evidence |
|---|---|---|
| checkpoint advancing outside same transaction as consumer write | PASS | `_process_next_event` (projection.py:444-496) 在单个 `run_write()` transaction 内顺序执行 consumer `apply_event` 与 `advance_projection_checkpoint`；commit 是原子的 |
| failure row advancing checkpoint | PASS | `_ProjectionApplyFailed` 由 `_process_next_event` 抛出，事务 rollback，checkpoint 不推进；`_record_failure` (projection.py:498-527) 只调用 `write_projection_failure`，不触及 checkpoint |
| runner opening its own connection or using public command facade | PASS | `ProjectionRunner.__init__` (projection.py:314-336) 接收注入的 `HostTransactionRunner`；所有 DB 操作均通过 `self._transaction_runner.run_write()` 完成；无 `sqlite3.connect`、无 `HostCommandHandle` 引用 |
| untyped Any/object/raw payload boundary | PASS | `ProjectionEventView.payload` 类型为 `Mapping[str, JsonValue]` (projection.py:173)；`JsonValue` 是递归强类型联合 (contracts/json_value.py:19-27)；`payload_object` 返回 `Mapping[str, JsonValue]` 且 runtime 验证 `isinstance(value, Mapping)` (_event_payload.py:371-372)；AST guard test 覆盖新文件 |
| projection importing Host mutators or Engine/runtime/service/ui/fins | PASS | `durable/projection.py` 仅导入 `durable._validation`、`durable.errors`、`durable.schema`、`durable.transaction`；`projection.py` 仅导入 `contracts.json_value`、`host._event_payload`、`durable.codec`、`durable.errors`、`durable.event_log`、`durable.projection`、`durable.transaction`；import boundary test 新增 `PROJECTION_FORBIDDEN_PREFIXES` 覆盖 (test_import_boundary.py:49-61) |
| schema mismatch | PASS | `HOST_SCHEMA_VERSION` 从 4 bump 到 5 (schema.py:24)；DDL 精确匹配 plan §3.1/§3.2 定义；PRAGMA user_version=5 验证 (test_durable_schema.py:111-112) |
| missing tests for critical invariants | PASS | 见下方 Test Adequacy Analysis |

## Test Adequacy Analysis

Plan §7 P8-S1 要求测试 → 实现测试映射：

| Required Test | Test Function | File |
|---|---|---|
| fresh bootstrap creates checkpoint/failure tables, PRAGMA user_version=5 | `test_fresh_db_creates_foundation_and_phase7_tables`, `test_projection_checkpoint_and_failure_tables_are_created` | test_durable_schema.py |
| constraints reject negative checkpoint and invalid failure count | `test_projection_schema_constraints_reject_invalid_rows` | test_durable_schema.py |
| event_log(event_sequence) valid FK target | `test_event_sequence_is_sqlite_foreign_key_parent_key` | test_durable_schema.py |
| missing checkpoint initializes to cursor 0 | `test_missing_checkpoint_initializes_to_cursor_zero` | test_projection_checkpoint.py |
| advance persists event id and timestamp | `test_advance_checkpoint_persists_event_identity_and_timestamp` | test_projection_checkpoint.py |
| advancing backwards rejected | `test_advancing_checkpoint_backwards_is_rejected` | test_projection_checkpoint.py |
| filter calls consumer only for matching events in sequence order | `test_runner_filters_matching_events_in_sequence_order` | test_projection_runner.py |
| per-class filters handle multi-class + type combinations | `test_per_class_filters_do_not_share_event_type_sets` | test_projection_runner.py |
| consumer writes and checkpoint commit in same transaction | `test_runner_commits_projection_write_and_checkpoint_together` | test_projection_runner.py |
| consumer write failure leaves checkpoint unchanged | `test_consumer_write_failure_rolls_back_write_and_checkpoint` | test_projection_runner.py |
| duplicate result still advances checkpoint | `test_duplicate_apply_result_still_advances_checkpoint` | test_projection_runner.py |
| failure writes failure row, success clears it | `test_consumer_write_failure_rolls_back_write_and_checkpoint`, `test_success_after_failure_clears_failure_row` | test_projection_runner.py |
| projection modules do not import forbidden layers | `test_projection_modules_do_not_import_forbidden_layers_or_mutators` | test_import_boundary.py |
| weak typing guard green | existing `test_host_disallows_weak_typing` covers new files | test_weak_typing_guard.py |

## Detailed Walk-transaction Atomicity

`_process_next_event` (projection.py:444-496) 在单个 `HostTransactionRunner.run_write()` 调用内顺序执行：

1. `ensure_projection_checkpoint` — 读取或初始化 checkpoint
2. `read_events_after` — 读取下一条 EventLog row
3. `consumer.apply_event` — consumer 在同一事务内写 projection-owned rows
4. `advance_projection_checkpoint` — 推进 checkpoint
5. `clear_projection_failure` — 清除既有 failure row

以上步骤共享同一 SQLite `BEGIN IMMEDIATE` transaction。consumer 抛异常时 `_ProjectionApplyFailed` 传播到 `run_write`，runner rollback 整个事务，consumer writes 和 checkpoint advance 一起回滚。

## Failure Path Analysis

`run_once` (projection.py:338-399) 的 failure 路径：

1. `_process_next_event` 抛出 `_ProjectionApplyFailed`
2. `run_write` rollback 事务 — consumer writes 和 checkpoint advance 回滚
3. `_record_failure` 在新事务中调用 `write_projection_failure`
4. `failures += 1; break` — 停止当前 batch

关键不变量：checkpoint cursor 保持在 consumer 失败 event 之前，下次 `run_once` 从同一位置重试。

## Schema DDL Ordering

`HOST_DURABLE_DDL` (schema.py:657-659) 按 `FOUNDATION_DDL + PHASE3_STATE_DDL + PROJECTION_DDL + PHASE3_INDEX_DDL` 排列。Projection DDL 包含 `FOREIGN KEY(checkpoint_event_id) REFERENCES event_log(event_id)` 和 `FOREIGN KEY(failed_event_id) REFERENCES event_log(event_id)`。`event_log` 在 `FOUNDATION_DDL` 中先创建，FK 依赖满足。

## Type Strictness

- 全部新增 dataclass 使用 `frozen=True, slots=True`
- 全部函数参数和返回值有类型注解
- 无 `Any`、`object`、裸 `dict`/`list`/`tuple`/`set`/`frozenset` 注解
- `JsonValue` 递归联合类型保护 payload 边界
- AST weak typing guard 覆盖所有新增 `.py` 文件

## Open Questions

无。

## Residual Risk

- `_record_failure` 自身 `run_write` 失败时（如 SQLite 磁盘满），failure 丢失且 checkpoint 未推进，但 `HostTransactionRetryExhaustedError` 会传播到 `run_once` 调用方，调用方可决定重试。此行为符合 plan §5 第 5 条不变量。
- `test_import_boundary.py` 的 `PROJECTION_FORBIDDEN_PREFIXES` 未包含 `dayu.host.read_model` 和 `dayu.host.read_api`（P8-S3 才新增），后续 slice 应同步更新。
- Plan §3.3/§3.4 的 `host_run_results` 和 `host_session_timeline_items` 表属于 P8-S3 scope，当前 `test_schema_does_not_create_future_sink_tables` 的 forbidden fragments 未包含 `run_result`/`timeline`，P8-S3 实现时需同步更新。
