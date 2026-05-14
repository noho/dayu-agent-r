# Gateflow Code Review: Host P3-S2 Session And Slot Lifecycle

- **review gate**: code review
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S2 Session And Slot Lifecycle
- **reviewer**: mimo
- **reviewed target**: diff since accepted P3-S1 commit `27d3145`, P3-S2 scope only
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p3-s2-session-lifecycle-20260514.md`
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md`, P3-S2 section
- **artifact path**: `docs/reviews/gateflow-code-review-host-p3-s2-session-lifecycle-mimo-20260514.md`

## Reviewer Conclusion

P3-S2 实现总体符合 approved plan 的 P3-S2 section。核心生命周期语义（ensure_session slot PK 幂等、create/close IdempotencyStore 合约、EventLog 与 state row 同事务、slot 原子重绑定、close 不触碰 Run rows）均已正确实现。类型签名全部强类型，无 `Any`/`object` 泄漏。测试覆盖了主要 happy path、幂等重试、幂等冲突与多进程并发。

发现 3 个 findings：1 个中等（多进程竞态下错误类型泄漏 durable 层异常到 API 边界）、1 个低（类型签名不精确）、1 个低（测试盲区）。无 blocking finding。建议 fix 后通过。

## Findings

### F001-未修复-[中]-多进程 create_session/close_session 竞态下抛出 HostIdempotencyConflictError 而非 HostApiError

- **入口/函数**: `_CreateSessionOperation.__call__` / `_CloseSessionOperation.__call__`
- **文件(行号)**: `dayu/host/durable/session_lifecycle.py` (287-290, 376-379)
- **输入场景**: 两个进程同时调用 `create_session` 或 `close_session`，使用相同 `client_request_id`、相同 semantic digest。
- **实际分支**: 进程 A 和进程 B 都执行 `read_idempotency_record` 返回 `None`，都通过 `_raise_if_digest_conflict`（无冲突），然后都进入 `record_idempotent_result`。先提交者成功写入；后提交者在 `idempotency.py:152` 触发 `HostIdempotencyConflictError`（`HostDurableError` 子类）。
- **预期行为**: 调用方收到 `HostApiError(code=HostApiErrorCode.IDEMPOTENCY_CONFLICT, ...)`。
- **实际行为**: 调用方收到 `HostIdempotencyConflictError`（`HostDurableError` 子类），不是 `HostApiError`。`HostTransactionRunner.run_write` 对 `HostDurableError` 做 rollback 后直接 re-raise，不做 error type mapping。
- **直接证据**:
  - `session_lifecycle.py:287-290`: `_CreateSessionOperation` 只做 read + pre-check + record，无 try/except 包裹 `record_idempotent_result`。
  - `idempotency.py:150-154`: `record_idempotent_result` 内部检测到不同 digest 时抛出 `HostIdempotencyConflictError`；同 digest 时返回 existing record。
  - `transaction.py:238-239`: `run_write` 捕获 `HostDurableError` 后 rollback 并 re-raise，不做 error type 转换。
  - 同 digest 竞态：后提交者实际返回 existing record（无错误），行为正确。
  - 不同 digest 竞态（理论上不可能，因为 pre-check 已在同 digest 时通过）：不会触发此路径。
- **影响**: 同 digest 多进程竞态下，后提交者实际不抛错（`record_idempotent_result` 对同 digest 返回 existing record）。因此该 finding 在当前 `create_session` / `close_session` 的实际使用模式下不会触发错误类型泄漏。但如果未来 P3-S4 的 `start_run` / `submit_followup_queue` 也复用同样的 pre-check + record 模式，且存在同 key 不同 digest 的并发请求（合法场景），则会暴露此问题。当前 P3-S2 为防御性发现。
- **建议改法和验证点**:
  - 方案 A（推荐）：在 `_CreateSessionOperation.__call__` 和 `_CloseSessionOperation.__call__` 中用 `try/except HostIdempotencyConflictError` 包裹 `record_idempotent_result` 调用，捕获后转换为 `HostApiError(code=HostApiErrorCode.IDEMPOTENCY_CONFLICT, ...)`。
  - 方案 B：在 `HostTransactionRunner.run_write` 中增加 `HostIdempotencyConflictError -> HostApiError` 的 error mapping（但这会改变 runner 的通用契约，影响面更大）。
  - 验证点：新增多进程测试，两个进程用同 `client_request_id` 不同 semantic digest 并发调用 `create_session`，断言两个进程都收到 `HostApiError` 且 `code == IDEMPOTENCY_CONFLICT`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

### F002-未修复-[低]-_session_closed_event_request.reason 参数类型标注为 str 但实际传入 dict

- **入口/函数**: `_session_closed_event_request`
- **文件(行号)**: `dayu/host/durable/session_lifecycle.py` (672, 701)
- **输入场景**: 任何 `close_session` 调用。
- **实际分支**: `_CloseSessionOperation.__call__` 在 line 408 传入 `reason=self.request.reason`（`str` 类型），但 `_session_closed_event_request` 的函数体在 line 701 将其构造为 `{"reason": reason}`（`dict`）传给 `EventLogAppendRequest.reason`。
- **预期行为**: 函数签名 `reason: str` 与函数体使用一致；或签名标注为 `JsonValue` 以反映实际传入 `EventLogAppendRequest.reason` 的类型。
- **实际行为**: 参数类型 `str` 正确反映了调用方传入值的类型，但函数体将其包装为 `dict` 后传给 `EventLogAppendRequest.reason: JsonValue | None`。类型签名本身不错误（`str` 是调用方输入类型），但与 `EventLogAppendRequest.reason` 的实际语义（结构化 JSON reason 对象）存在认知间隙。
- **直接证据**: `session_lifecycle.py:672`: `reason: str`; `session_lifecycle.py:701`: `reason={"reason": reason}`。
- **影响**: 运行时无影响（`dict` 是合法 `JsonValue`）。pyright 不报错因为 `str` 也是 `JsonValue` 的子类型（通过 `JsonValue` 的 union 定义）。仅影响代码可读性与维护者理解。
- **建议改法和验证点**: 保持当前实现不变，或在 docstring 中补充说明 `reason` 参数会被包装为 `{"reason": reason}` 结构化对象传入 EventLog。无需改签名。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

### F003-未修复-[低]-create_session 幂等冲突测试未覆盖 bind_slot 变化场景

- **入口/函数**: `test_create_session_idempotency_conflict_on_changed_digest`
- **文件(行号)**: `tests/host/test_session_lifecycle.py` (425-448)
- **输入场景**: 同 `client_request_id`，先 `bind_slot=False` 后 `bind_slot=True`（或反向），metadata 和 caller_semantic_digest 不变。
- **实际分支**: 当前测试只覆盖 metadata 变化导致的 digest 冲突。`bind_slot` 是 `_create_session_semantic_digest` 的 digest 字段（`session_lifecycle.py:573`），变化也会产生不同 digest。
- **预期行为**: 测试覆盖 `bind_slot` 变化导致的幂等冲突路径。
- **实际行为**: 测试未覆盖该路径。
- **直接证据**: `test_session_lifecycle.py:431-435`: 两次调用都用 `bind_slot=False`，只变 `metadata_value`。
- **影响**: 测试覆盖不完整，但 `bind_slot` 变化路径的逻辑与 metadata 变化路径完全相同（都是 digest 不匹配触发 `_raise_if_digest_conflict`），代码正确性不受影响。
- **建议改法和验证点**: 新增测试用例，同 `client_request_id` 先 `bind_slot=False` 后 `bind_slot=True`，断言 `HostApiErrorCode.IDEMPOTENCY_CONFLICT`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

## Review Criteria Checklist

| 标准 | 结果 | 说明 |
|------|------|------|
| ensure_session 使用 slot PK 作为幂等真源，不写 idempotency_records | PASS | `session_lifecycle.py:191-208`: 只读 slot PK，slot 存在即返回；`session_lifecycle.py:251-252`: slot 不存在时 insert session + slot，不写 `idempotency_records`。 |
| create_session 和 close_session 使用 IdempotencyStore，同 digest 返回既有 / 不同 digest 返回 conflict | PASS | 两个操作都通过 `IdempotencyStore.read_idempotency_record` + `_raise_if_digest_conflict` + `record_idempotent_result` 实现。 |
| SESSION_CREATED / SESSION_CLOSED EventLog rows 与 state row 同事务 | PASS | `ensure_session`: EventLog append + insert_session + insert_session_slot 都在同一 `__call__` 内。`create_session`: EventLog append + insert_session + upsert_slot + record_idempotent_result 同事务。`close_session`: EventLog append + close_open_session_row + record_idempotent_result 同事务。 |
| create_session(bind_slot=true) 原子重绑定 slot，旧 Session 不变 | PASS | `upsert_session_slot` 用 `ON CONFLICT(scope, slot_key) DO UPDATE SET session_id = excluded.session_id`。旧 Session row 不被修改。测试 `test_create_session_with_slot_rebinds_without_closing_old_session` 验证旧 Session 仍 OPEN。 |
| close_session 不修改 Run rows | PASS | `_CloseSessionOperation.__call__` 只读 session、写 EventLog、CAS close session、写 idempotency record。无任何 `host_runs` 操作。 |
| 无 start_run/follow-up/admission/promotion/cancel/Engine/Worker/ToolRuntime/recovery 泄漏 | PASS | `session_lifecycle.py` 不 import 任何 Engine/Worker/runtime 模块。无 Run/Attempt 写入。 |
| 并发 same-slot ensure_session 留下一个可见 Session/slot 绑定 | PASS | `test_concurrent_same_slot_ensure_session_returns_one_bound_session` 用 6 进程并发，断言 session_count=1, slot_count=1, 所有 worker 返回同一 session_id。 |
| 返回快照与 helper 读取一致强类型 | PASS | `SessionSnapshot`, `SessionSlotRef`, `HostStreamCursor` 均为 frozen dataclass。无 `Any`/`object`/untyped 签名。 |
| 测试覆盖预期断言且验证结果合理 | PASS with F003 | 8 个测试覆盖 ensure/create/close lifecycle、slot 重绑定、幂等重试、幂等冲突、多进程并发。F003 为测试覆盖盲区。 |

## Open Questions / Residual Risks

- 无 blocking open questions。
- **residual risk covered by later slice**: `SessionSnapshot.active_run_id` 与 `queued_run_ids` 当前只读取 schema rows；Run/Attempt 写入与状态推进由 P3-S3/P3-S4 覆盖。
- **residual risk covered by later slice**: close 后拒绝新 Run/follow-up 的 admission 行为由 P3-S4+ 覆盖。
- **F001 residual**: 同 digest 多进程竞态在当前 P3-S2 使用模式下不触发错误（后提交者返回 existing record）。P3-S4 若复用相同模式需注意 error type mapping。

## Controller Decision Status

| Finding | Status |
|---------|--------|
| F001 | pending-controller-decision |
| F002 | pending-controller-decision |
| F003 | pending-controller-decision |
