# Gateflow Code Review: Host P2 Slice 2 EventLog / Idempotency

## Review Gate

- **gate name**: Phase 2 Slice 2 code review
- **reviewed target**: workspace changes relative to accepted Slice 1 commit `be5dbdc`
- **approved plan**: `docs/host/phase2-durable-store-eventlog-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p2-s2-eventlog-idempotency-20260514.md`
- **reviewer**: mimo
- **review date**: 2026-05-14

## Reviewed Files

- `dayu/host/durable/codec.py` (modified: added `is_sha256_digest`)
- `dayu/host/durable/errors.py` (new)
- `dayu/host/durable/event_log.py` (new, 609 lines)
- `dayu/host/durable/idempotency.py` (new, 358 lines)
- `tests/host/test_event_log_store.py` (new, 401 lines)
- `tests/host/test_event_log_multiprocess.py` (new, 157 lines)
- `tests/host/test_idempotency_store.py` (new, 310 lines)

## Conclusion

**no-findings**. 实现严格遵循 approved plan 的 Slice 2 范围与契约。所有核心语义正确：全局 `event_sequence`、`event_body_digest` 幂等去重、payload ref 组合校验、idempotency scope/key/digest 冲突检测、所有 mutation 在 caller-provided `HostTransaction` 内执行、多进程依赖 SQLite transaction 语义。测试覆盖完整，pyright 通过，无 Slice 3 行为泄漏。

## Findings

无 blocking 或 non-blocking finding。

### 逐项验证结果

**1. EventLog append/read 正确性**
- 全局 `event_sequence`：由 SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` 分配，多 event class 共享同一全局 cursor。验证：`schema.py:84` DDL、`test_event_log_store.py:137-163`。
- 重复 `event_id` 同 digest 返回既有 row，`inserted=False`，不追加第二行。验证：`event_log.py:218-221`、`test_event_log_store.py:166-189`。
- 重复 `event_id` 不同 digest 抛出 `HostEventIdentityConflictError`。验证：`event_log.py:222-224`、`test_event_log_store.py:192-219`。
- `read_event_by_id` 与 `read_events_after` 使用全局 cursor 语义。验证：`event_log.py:279-370`、`test_event_log_store.py:222-252`。

**2. event_body_digest 计算**
- digest input 包含 plan 指定的全部 16 个 request-assigned fields（`event_class`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`event_type`、`occurred_at`、`actor`、`source`、`client_request_id`、`idempotency_key`、`policy_decision_json`、`reason_json`、`payload_json`、`payload_ref`、`payload_digest`）。验证：`event_log.py:404-421`。
- 排除 `event_id`、`event_sequence`、`appended_at` 和所有 DB-assigned fields。验证：上述 digest_input dict 不含这些 key。
- canonical JSON 处理：`policy_decision_json` 与 `reason_json` 为 `None` 时按 SQL NULL 处理，非 `None` 时按 canonical JSON 编码；`payload_json` 始终 canonical JSON。验证：`event_log.py:401-403`、`_optional_canonical_json` 函数。
- `occurred_at` 固定 UTC 微秒精度 `Z` timestamp。验证：`codec.py:43-54`、`format_utc_timestamp` 函数。

**3. payload_ref / payload_digest 校验**
- `payload_ref` 与 `payload_digest` 必须成对出现或同时为 `None`。验证：`event_log.py:470-490`、`_validate_payload_reference` 函数。
- 非空 `payload_digest` 必须符合 `sha256:<64 lowercase hex>` 格式。验证：`event_log.py:489-490`、`codec.py:93-100`。
- 缺失 `payload_ref` FK 由 SQLite FK constraint 触发，transaction runner 转为 `HostForeignKeyError`，不被 busy retry。验证：`test_event_log_store.py:334-362`。
- 无 payload descriptor helper beyond nullable FK。验证：无 `payload.py` 或 descriptor 写入逻辑。

**4. Idempotency primitive**
- scope 三元组 `(scope_kind, scope_id, idempotency_key)` 作为 composite PK。验证：`schema.py:116-131` DDL。
- 相同 scope/key/digest 返回既有 record。验证：`idempotency.py:141-143`、`test_idempotency_store.py:149-183`。
- 相同 scope/key/不同 digest 抛出 `HostIdempotencyConflictError`。验证：`idempotency.py:144-146`、`test_idempotency_store.py:186-211`。
- 冲突不被 transaction runner 重试。验证：`test_idempotency_store.py:214-251`。
- `result_kind` 来自显式 `IdempotencyResultRef.result_kind`，不从其它字段推断。验证：`idempotency.py:236`。
- `IdempotencyResultRef` 显式四字段结构。验证：`idempotency.py:33-46`。
- 可通过 FK 引用已创建 EventLog event_id / sequence。验证：`test_idempotency_store.py:254-281`。

**5. Transaction 边界**
- 所有 mutation 在 caller-provided `HostTransaction` 内执行。验证：`append_event`、`read_event_by_id`、`record_idempotent_result`、`read_idempotency_record` 均接受 `HostTransaction` 参数，不创建独立 connection 或 command path。
- `EventLogStore` 与 `IdempotencyStore` 是轻量方法集合，不持有连接。验证：`event_log.py:150-155`、`idempotency.py:75-80`。

**6. 多进程 append**
- 依赖 SQLite transaction semantics，不使用 lane / filelock。验证：`test_event_log_multiprocess.py` 无 `dayu.runtime` import。
- 最终 row count 正确、`event_sequence` 全局唯一递增、无重复 `event_id`。验证：`test_event_log_multiprocess.py:110-157`。

**7. 无 Slice 3 行为**
- 无 artifact helper、无 host instance liveness operations、无 payload descriptor write helper。验证：新增文件中无 `artifact.py`、`liveness.py`、`payload.py`。

**8. 类型约束**
- 无 `Any`、`object`、无类型参数或无类型返回值。验证：所有函数签名均有完整类型注解。
- 所有模块、类与函数均有中文 docstring。验证：逐文件检查通过。

**9. 边界隔离**
- 无 `dayu.runtime`、`dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui` import。验证：`event_log.py` 和 `idempotency.py` 只 import `dayu.contracts.json_value` 与 `dayu.host.durable.*`。
- 无兼容 re-export / wrapper / facade。验证：无 re-export 逻辑。
- 无隐藏全局 storage policy 或 cwd / env 派生的 artifact root。验证：所有配置通过 `HostDurableStoreOptions` 显式传入。

**10. 错误分类**
- `HostEventIdentityConflictError` 继承 `HostDurableError`，不被 busy retry。验证：`transaction.py:237-239` catch `HostDurableError` 并 rollback re-raise。
- `HostIdempotencyConflictError` 同上。验证：同上。
- `HostForeignKeyError` 由 `_classify_sqlite_error` 正确映射。验证：`transaction.py:311-312`。
- 无 raw `sqlite3.IntegrityError` 泄漏。验证：所有 SQLite error 经 `_classify_sqlite_error` 转换。

## Open Questions / Residual Risk

**无 blocking residual risk。**

以下为已知但不阻塞当前 slice 的项：

1. **未测试有效 `payload_ref` append**：因缺少 descriptor write helper，无法测试 EventLog 引用已存在 payload descriptor 的完整路径。已 accepted by implementation artifact，由 Slice 3 覆盖。

2. **未测试 deliberate long lock 的 retry exhausted 多进程分支**：当前多进程测试只覆盖正常 append 成功场景。Slice 1 已覆盖 busy retry 单测，deliberate contention 测试可后续补充。

3. **`_require_optional_non_empty_text` 命名与实现的语义一致性**：该函数名称暗示"optional 字段如果存在则必须非空"，但实现只检查空字符串，`None` 值直接通过。当前调用点均为 `str | None` 参数，`None` 通过是正确行为（对应 SQL NULL），但函数名可能在后续维护中造成误导。这不阻塞当前 slice，且修改命名/行为属于 refactor 范畴。

4. **validation helper 跨模块重复**：`event_log.py` 与 `idempotency.py` 各自定义了相同的 `_require_text`、`_optional_text`、`_require_non_empty_text`、`_require_optional_non_empty_text` 辅助函数。当前重复量小，可接受；后续 slice 如有第三个 consumer 可考虑抽取到 `codec.py` 或新增 `validation.py`。

## Controller Decision Status

`status=pending-controller-decision`

## Artifact Path

`docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-mimo-20260514.md`
