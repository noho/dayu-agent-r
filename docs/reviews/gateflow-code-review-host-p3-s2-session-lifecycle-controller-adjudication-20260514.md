# Gateflow Controller Adjudication: Host P3-S2 Session And Slot Lifecycle Code Review

- **gate**: code review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S2 Session And Slot Lifecycle
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s2-session-lifecycle-mimo-20260514.md`
- **controller**: Codex
- **artifact path**: `docs/reviews/gateflow-code-review-host-p3-s2-session-lifecycle-controller-adjudication-20260514.md`

## Controller Conclusion

MiMo review 覆盖了 P3-S2 的主要状态边界、幂等语义、EventLog 同事务写入和并发测试。总控裁决为：F003 accepted，需要补测试；F001 rejected-with-reason；F002 rejected-with-reason。P3-S2 代码修复范围只允许覆盖 accepted finding，不扩大到 Run / Attempt / admission 或 public facade。

## Finding Decisions

| Finding | Severity | Decision | Owner | Required Action |
|---------|----------|----------|-------|-----------------|
| F001 | 中 | rejected-with-reason | controller | 无代码修改；保留为 P3-S4 幂等错误映射注意项。 |
| F002 | 低 | rejected-with-reason | controller | 无代码修改。 |
| F003 | 低 | accepted | AgentCodex | 在 `tests/host/test_session_lifecycle.py` 增加 `bind_slot` 变化触发 create_session 幂等冲突的覆盖。 |

## Decision Details

### F001: rejected-with-reason

MiMo 提出的“两进程都先读到 `None` 后再竞争写入 `idempotency_records`”不是当前 P3-S2 durable 写事务模型下可达的执行路径。`HostTransactionRunner.run_write` 在进入 operation 前执行 `BEGIN IMMEDIATE`，同一 SQLite database 上的 write transaction 会被串行化。第二个写事务必须等第一个写事务提交或重试后才能进入 operation，因此它在 `read_idempotency_record` 时会看到第一个事务已经写入的幂等记录。

因此：

- 相同 digest 的重试会在 operation 开始处命中既有记录并返回既有 Session result。
- 不同 digest 的重试会在 operation 开始处命中既有记录，并由 `_raise_if_digest_conflict` 转换为 `HostApiError(code=HostApiErrorCode.IDEMPOTENCY_CONFLICT)`。
- `record_idempotent_result` 的 `HostIdempotencyConflictError` 路径在这个 pre-check + `BEGIN IMMEDIATE` 写事务组合下不是 P3-S2 的实际 API 边界泄漏。

保留一个后续注意项：P3-S4 若为 Run / follow-up 引入新的幂等写入模式，必须继续满足“幂等冲突在 Host API 边界表现为 `HostApiErrorCode.IDEMPOTENCY_CONFLICT`”。

### F002: rejected-with-reason

`_session_closed_event_request(reason: str)` 的参数类型表达的是调用方传入的 close reason 文本；函数内部把该文本包装为 EventLog 的结构化 `reason={"reason": reason}` 是事件记录格式转换，不代表参数签名错误。当前签名、调用点和 `EventLogAppendRequest.reason` 的 JSON 值要求一致，运行时与 pyright 均无问题。

该点不需要代码修复。后续如果 EventLog reason 结构需要统一命名，应作为事件 schema 设计变更处理，不在 P3-S2 lifecycle helper 内做局部调整。

### F003: accepted

`bind_slot` 是 `_create_session_semantic_digest` 的明确输入字段。同一 `client_request_id` 下改变 `bind_slot` 应触发 `HostApiErrorCode.IDEMPOTENCY_CONFLICT`。当前测试已覆盖 metadata 变化导致的 digest conflict，但未覆盖 `bind_slot` 变化。该缺口真实存在且补充成本低，应修复。

## Fix Scope

AgentCodex 只需修改：

- `tests/host/test_session_lifecycle.py`
- `docs/reviews/gateflow-fix-host-p3-s2-session-lifecycle-20260514.md`

不得修改生产代码，除非补测试过程中发现直接证据证明 F001/F002 裁决前提不成立。若出现这种情况，应暂停并返回总控裁决。

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_session_lifecycle.py tests/host/test_state_schema.py tests/host/test_durable_schema.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`
