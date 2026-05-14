# Gateflow Re-Review: Host P3-S2 Session And Slot Lifecycle

- **review gate**: re-review
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S2 Session And Slot Lifecycle
- **reviewer**: mimo
- **re-review scope**: F003 fix only（不重新打开 F001/F002）
- **fix artifact**: `docs/reviews/gateflow-fix-host-p3-s2-session-lifecycle-20260514.md`
- **artifact path**: `docs/reviews/gateflow-code-re-review-host-p3-s2-session-lifecycle-mimo-20260514.md`

## Reviewer Conclusion

F003 已正确修复。新增测试 `test_create_session_idempotency_conflict_on_changed_bind_slot` 覆盖了 `bind_slot` 变化触发幂等冲突的路径，断言合理且额外验证了 rejected retry 不引入脏写。修复未引入新问题，无 scope creep。通过。

## F003 Re-Review Detail

### 修复内容验证

- **新增测试**: `test_session_lifecycle.py:451-486` — `test_create_session_idempotency_conflict_on_changed_bind_slot`
- **测试逻辑**:
  1. 以 `bind_slot=False` 创建 Session（`client_request_id="create-bind-slot-conflict"`）
  2. 以相同 `client_request_id`、相同 `caller_semantic_digest`、`bind_slot=True` 重试
  3. 断言 `HostApiError` 且 `code == HostApiErrorCode.IDEMPOTENCY_CONFLICT`
  4. 额外断言：rejected retry 后 durable 状态仍为 1 Session、0 slot binding、1 SESSION_CREATED event
- **符合 F003 建议**: 覆盖了 `bind_slot` 变化导致 digest 不匹配的路径
- **符合 controller adjudication**: 只修改 `tests/host/test_session_lifecycle.py`，未改生产代码

### digest 计算一致性确认

`_create_session_semantic_digest`（`session_lifecycle.py:568-578`）的 digest 输入包含 `bind_slot`、`scope`、`slot_key`、`metadata_digest`、`caller_semantic_digest`、`call_context_digest`。测试中两次调用仅 `bind_slot` 不同（`False` vs `True`），同时 `scope`/`slot_key` 随之从 `None` 变为 `"workspace"`/`"slot-a"`，确保 digest 必然不同。测试设计正确。

### 额外断言质量

测试不仅断言 conflict error，还验证了：
- Session row 数仍为 1（未创建第二个 Session）
- slot row 数为 0（第一次 `bind_slot=False` 不创建 slot，conflict 的第二次也不创建）
- SESSION_CREATED event 数为 1（conflict 不追加事件）

这超出了 F003 最低要求，属于正向增量，不构成 scope creep。

## 验证命令

fix artifact 已记录以下验证命令及结果，本 re-review 独立复验：

| Command | Result |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_session_lifecycle.py tests/host/test_state_schema.py tests/host/test_durable_schema.py -q` | passed: `27 passed in 0.43s` |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host` | passed: `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | passed |

re-review 未额外运行其他命令。

## F001/F002 状态确认

- F001: rejected-with-reason，controller 裁决维持，无代码变更，无直接证据证明裁决前提不成立。
- F002: rejected-with-reason，controller 裁决维持，无代码变更。

## Findings 状态总结

| Finding | Status | 说明 |
|---------|--------|------|
| F001 | rejected-with-reason | 保持不变，P3-S4 注意项 |
| F002 | rejected-with-reason | 保持不变 |
| F003 | **已修复** | 测试已补充，re-review 通过 |

## 新问题 / Scope Creep

- 无新 findings。
- 无 scope creep。修复严格限制在测试文件内。
- 无生产代码变更。
