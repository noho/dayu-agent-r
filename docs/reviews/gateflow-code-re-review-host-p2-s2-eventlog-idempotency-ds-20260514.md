# Gateflow Code Re-Review Artifact: Host P2 S2 EventLog / Idempotency (Fix Verification)

## Review Gate

- **review gate name**: code-re-review
- **reviewed target**: Phase 2 Slice 2 accepted findings fix (DS-F1 - DS-F4)
- **approved plan**: `docs/host/phase2-durable-store-eventlog-plan.md`
- **original DS review**: `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`
- **controller adjudication**: `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/gateflow-fix-host-p2-s2-eventlog-idempotency-20260514.md`
- **accepted Slice 1 commit**: `be5dbdc`
- **current branch**: `feat/host-phase2-durable-store-eventlog`
- **reviewer**: DS (deepreview)
- **re-review date**: 2026-05-14

## Scope Verified

Reviewed workspace changes (relative to `be5dbdc`):

| File | Status |
|---|---|
| `dayu/host/durable/codec.py` | Modified (+`is_sha256_digest`, +`_SHA256_DIGEST_PATTERN`) |
| `dayu/host/durable/event_log.py` | New (Slice 2 implementation + DS-F1 fix) |
| `dayu/host/durable/idempotency.py` | New (Slice 2 implementation + DS-F1 fix) |
| `tests/host/test_event_log_store.py` | New (14 tests) |
| `tests/host/test_event_log_multiprocess.py` | New (1 test) |
| `tests/host/test_idempotency_store.py` | New (7 tests) |

Not re-reviewed in depth: Slice 1 baseline files (`schema.py`, `transaction.py`, `connection.py`, `options.py`, `errors.py`) — unchanged from accepted Slice 1.

## Re-Review Conclusion

**PASS。** 全部 4 项 accepted findings (DS-F1 至 DS-F4) 已正确修复，无未修复项。修复严格遵守 plan non-goals 与 controller adjudication 边界。EventLog append/read、event_body_digest、idempotency conflict、transaction 边界、multi-process sequence 行为正确。测试覆盖所有 accepted findings，无兼容性代码。无新增 BLOCKING 或 ACCEPTED 级别 finding。67 项测试全部通过，pyright 零报错。

## Accepted Findings Fix Verification

### DS-F1: whitespace-only identifier strings — 已修复

**原始问题**: `_require_non_empty_text` 仅检查 `value == ""`，未拒绝纯空白字符串。

**修复验证**:

- `event_log.py:544-553` — `_require_non_empty_text` 现在检查 `value == "" or value.isspace()`。
- `event_log.py:557-568` — `_require_optional_non_empty_text` 现在检查 `value is not None and (value == "" or value.isspace())`。
- `idempotency.py:289-298` — `_require_non_empty_text` 相同实现。
- `idempotency.py:302-314` — `_require_optional_non_empty_text` 相同实现。
- `event_log.py:461-462` — `actor` 和 `source` 已路由到 `_require_optional_non_empty_text`（controller follow-up 发现并已修复）。
- 实现不做 trim/normalize；只拒绝语义空文本。非空文本原样存储。

**测试覆盖**:

| 测试 | 文件 | 覆盖字段 |
|---|---|---|
| `whitespace_event_id` | `test_event_log_store.py:401-408` | 必填 event_id 纯空白 |
| `whitespace_optional_text` | `test_event_log_store.py:410-417` | optional run_id 纯空白 |
| `whitespace_actor` | `test_event_log_store.py:419-428` | optional actor 纯空白 |
| `whitespace_source` | `test_event_log_store.py:430-438` | optional source 纯空白 |
| `whitespace_scope` | `test_idempotency_store.py:252-292` | 必填 scope_kind 纯空白 |
| `whitespace_result` | `test_idempotency_store.py:252-292` | 必填 result_kind 纯空白 |

**附加验证**: `str.isspace()` 正确处理 `" "`, `"\t"`, `"\n"`, `" \t\n"`, `"\u00a0"` (Unicode 不间断空格)。空字符串 `""` 由 `value == ""` 分支拦截（`"".isspace()` 返回 `False`）。验证命令：`python3 -c "print(''.isspace())"` → `False`。两者组合完整覆盖纯空白场景。

**结论**: 已修复。必填和 optional 文本字段的纯空白拒绝完整。

---

### DS-F2: Store class wrapper methods — 已修复

**原始问题**: `EventLogStore` / `IdempotencyStore` wrapper 方法零测试覆盖。

**修复验证**:

- `test_event_log_store.py:321-350` — `test_event_log_store_wrapper_methods_delegate_to_functions`：通过 `EventLogStore().append_event()` / `.read_event_by_id()` / `.read_events_after()` 执行完整 append → read by id → read cursor 链路，断言返回值与直接调用 primitive 一致。
- `test_idempotency_store.py:187-213` — `test_idempotency_store_wrapper_methods_delegate_to_functions`：通过 `IdempotencyStore().record_idempotent_result()` / `.read_idempotency_record()` 执行完整 write → read 链路，断言返回值正确。

**结论**: 已修复。两 Store 类的 wrapper 方法均有 smoke 测试。

---

### DS-F3: read_event_by_id None / read_events_after 空元组 — 已修复

**原始问题**: 缺失 `read_event_by_id` 返回 `None` 和 `read_events_after` 返回空元组的边界测试。

**修复验证**:

- `test_event_log_store.py:353-372` — `test_missing_event_and_cursor_beyond_end_return_empty_results`：
  - `read_event_by_id(transaction, "missing-event")` 断言返回 `None`。
  - `read_events_after(transaction, 999, limit=10)` 断言返回空元组 `()`。
  - 先写入一条事件确保 DB 非空，然后测试不存在的 id 和超出最大 cursor 的读取。

**结论**: 已修复。两条边界路径均覆盖。

---

### DS-F4: NULL optional 字段 digest 与 round-trip — 已修复

**原始问题**: `_request` 辅助函数始终填充所有 optional 字段为非 None，未测试 NULL 路径。

**修复验证**:

- `test_event_log_store.py:193-255` — `test_append_optional_none_fields_preserves_nulls_and_digest_idempotency`：
  - 构造所有 optional 字段为 `None` 的 `EventLogAppendRequest`（`run_id`, `attempt_id`, `execution_id`, `actor`, `source`, `client_request_id`, `idempotency_key`, `policy_decision`, `reason`, `payload_ref`, `payload_digest`）。
  - 断言首次 append `inserted=True`。
  - 断言重复 append `inserted=False`（digest 幂等稳定）。
  - 断言 `read_event_by_id` 返回的 row 保持所有 optional 字段为 `None`。
  - 断言 `event_body_digest` 为合法 sha256 digest 且 first/second/re-read 三者一致。
  - 断言 `none_fields_preserved and digest_stored_and_stable` 同时成立。

**结论**: 已修复。NULL optional 字段的 round-trip 保持、digest 计算与幂等稳定性全部覆盖。

---

## Plan Non-Goals Compliance

逐项复核 plan §"Non-Goals And Scope Boundary" 与 controller adjudication 约束：

| Non-goal | 状态 |
|---|---|
| 未引入 payload descriptor writer | ✓ `event_log.py` 仅处理 `payload_ref`/`payload_digest` nullable FK 列，无 descriptor 写入逻辑 |
| 未引入 artifact helper | ✓ 无 artifact 文件写入、digest verify、atomic rename |
| 未引入 liveness | ✓ 无 `host_instances` 表操作 |
| 未引入 Session/Run/Attempt 状态机 | ✓ 无 session/run/attempt 状态迁移、CAS、queue |
| 未引入 Engine/Runtime/Fins/Service/UI 依赖 | ✓ import 仅限于 `dayu.contracts.json_value`（公共契约）和 `dayu.host.durable.*`（内部 foundation） |
| 未引入 command path | ✓ `append_event` / `record_idempotent_result` 仅接受 `HostTransaction`，不启动/推进/取消 command |
| 未修改 `dayu.runtime` | ✓ 无 runtime 模块变更 |

## Core Correctness Verification

### EventLog append/read

- **全局 event_sequence**: SQLite `AUTOINCREMENT` 分配，`test_multiple_event_classes_share_one_global_cursor` 验证跨 event class 单调递增 (1,2,3,4)。
- **Duplicate event_id 同体 → 返回既有 row**: `event_log.py:219-221`，`test_duplicate_event_id_same_body_returns_existing_row` 验证 inserted=False 且 row count 不增加。
- **Duplicate event_id 异体 → HostEventIdentityConflictError**: `event_log.py:222-224`，`test_duplicate_event_id_different_body_raises_identity_conflict` 验证。
- **Reader cursor**: `event_log.py:341-368` 使用 `WHERE event_sequence > ? ORDER BY event_sequence ASC LIMIT ?`，`test_read_events_after_uses_global_cursor_order` 验证。
- **Insert 后 re-read 守卫**: `event_log.py:273-275`，若 re-read 返回 None 则抛出 `HostDurableError`。

### event_body_digest 计算

- `event_log.py:401-428` — digest_input dict 包含所有 request-assigned 字段（event_class, session_id, run_id, attempt_id, execution_id, event_type, occurred_at, actor, source, client_request_id, idempotency_key, policy_decision_json, reason_json, payload_json, payload_ref, payload_digest），排除 event_id/event_sequence/appended_at。
- Canonical JSON 编码通过 `canonical_json_dumps`（sort_keys=True, compact separators, allow_nan=False），digest 使用 `sha256_digest_json`。

### Idempotency conflict

- `idempotency.py:140-146` — same key + same digest → 返回既有记录；same key + different digest → `HostIdempotencyConflictError`。
- `test_same_scope_key_different_digest_raises_conflict` 和 `test_idempotency_conflict_is_not_retried_by_transaction_runner` 验证冲突检测与不重试。

### Transaction 边界

- 所有 mutation 在调用方传入的 `HostTransaction` 内执行。
- `test_after_commit_callback_runs_only_after_append_commit` 验证 after-commit 仅在 commit 成功后执行。
- 业务冲突（event identity conflict, idempotency conflict）不被 transaction runner 重试。

### Multi-process sequence

- `test_multiprocess_append_allocates_unique_global_sequences`：4 进程 × 12 事件 = 48 行，event_sequence 全局唯一递增，event_id 无重复。
- SQLite WAL + `BEGIN IMMEDIATE` + busy retry 处理并发。

### codec.py 新增 `is_sha256_digest`

- `_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")` — 正确匹配 sha256 hexdigest（64 小写 hex 字符）。
- `event_log.py:_validate_payload_reference` 和 `idempotency.py:_validate_digest` 正确使用此函数校验 digest 格式。
- 已通过 `test_append_optional_none_fields_preserves_nulls_and_digest_idempotency` 间接验证（断言 `is_sha256_digest(first.row.event_body_digest)` 为 True）。

## Validation Rerun

| Command | Result |
|---|---|
| `pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q` | 19 passed in 0.09s |
| `pytest tests/host/test_event_log_multiprocess.py -q` | 1 passed in 0.19s |
| `pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q` | 15 passed in 0.08s |
| `pytest tests/host -q` | 67 passed in 0.30s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |

## Findings

未发现实质性问题。

以下为已确认无风险的观察项，不作为 finding：

### 观察项 1: `created_event_sequence <= 0` 校验缺少错误路径测试

- `idempotency.py:241-244` — `_validate_result_ref` 在 `created_event_sequence is not None and created_event_sequence <= 0` 时抛出 `HostDurableError`。
- 当前仅有 happy path 测试（`test_idempotency_record_can_reference_created_event` 传入正数 sequence），无零或负数 `created_event_sequence` 的校验测试。
- **影响**: 极低。校验逻辑简单且正确；`event_sequence` 由 SQLite AUTOINCREMENT 从 1 开始分配，零/负数不会在生产路径出现。
- **建议**: 可在后续 slice 补齐，不阻塞当前 slice。

### 观察项 2: `_require_non_empty_text` / `_require_optional_non_empty_text` / `_require_text` / `_optional_text` 在 event_log.py 与 idempotency.py 中重复定义

- 两个模块各有完全相同的私有校验函数拷贝（event_log.py:544-611，idempotency.py:289-358）。
- 这是原实现中的设计选择（每模块自包含），未被原始 DS review 或 MiMo review 标记为 finding。修复仅同步更新两处实现，未改变模块边界。
- **影响**: 低。若未来校验语义变更需双处同步，但当前 scope 内无此需求。是否抽取共享校验模块属于超出当前 slice 范围的重构决策。

## Open Questions

无。

## Residual Risk

1. **DS-F1 至 DS-F4**: 全部修复，无残存 accepted-finding 风险。
2. **Unicode 零宽空格**: `str.isspace()` 将 `\u200b`（零宽空格）视为非空白，因此 `"\u200b"` 会通过校验。这是 Python 标准库行为，且零宽空格需蓄意注入才会出现；当前 slice 不需要额外防护。
3. **README 同步**: 修复 artifact 注明 README 同步未执行（handoff 允许文件列表不含 README）。后续 slice 应按触发规则检查 `dayu/host/README.md` 和 `tests/README.md`。
4. **Slice 3 依赖**: EventLog `payload_ref` 非空合法值路径需 Slice 3 payload descriptor writer 才能完整测试。当前 slice 通过 FK 缺失测试覆盖了错误路径。

## Artifact Path

`docs/reviews/gateflow-code-re-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`
