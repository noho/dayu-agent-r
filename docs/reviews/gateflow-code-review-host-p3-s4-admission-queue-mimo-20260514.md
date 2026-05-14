# Gateflow Code Review: Host P3-S4 Admission And Queue Promotion — AgentMiMo

- **gate**: Phase 3 implementation code review
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S4 Admission And Queue Promotion
- **reviewer**: AgentMiMo
- **review date**: 2026-05-14
- **baseline HEAD**: 5943c89
- **reviewed files**:
  - `dayu/host/admission.py`
  - `tests/host/test_admission_queue.py`

## Review Checklist

### C1. Scope 仅限 internal admission

**结论: PASS**

`admission.py` 模块 docstring 明确声明只实现内部 admission 与 queue promotion，不实现 public facade、scheduler、lane、WorkerProxy、Engine dispatch、steer、retry、replay、wait 或 recovery。

import 分析：
- 只 import `dayu.host.api`（公共类型，用于 request/response）
- 只 import `dayu.host.durable.*`（internal durable foundation）
- 无 `dayu.engine`、`dayu.runtime`、`dayu.service`、`dayu.ui`、`dayu.fins` import
- `NoopAdmissionWakeupPort` 确实 no-op
- `HostAdmissionService` 使用 Protocol 注入 clock/id/wakeup，无全局单例

### C2. start_run 和 follow-up queue 在事务内校验 Session OPEN

**结论: PASS**

`_StartRunOperation.__call__`（L429-470）:
1. 先查 idempotency record（同事务内）
2. `_require_open_session(transaction, self.request.session_id)` 在事务内读 Session row 并校验 `status == OPEN`
3. 后续读 active Run、追加事件、写 state rows 都在同一个 `run_write` 事务内

`_SubmitFollowupQueueOperation.__call__`（L543-594）:
1. 先查 idempotency record
2. `_require_open_session(transaction, request.session_id)` 同事务内校验
3. 后续读 active Run、创建 Run 都在同一事务

Closed Session 测试 `test_closed_session_rejects_start_and_followup_without_event_side_effects`（L255-294）验证：
- closed Session 对 `start_run` 和 `submit_followup_queue` 都返回 `INVALID_STATE`
- EventLog row count 不变
- idempotency_records row count 不变

### C3. queue_policy 只允许 queue/reject/attach_active 且未知值事务前 ValueError

**结论: PASS**

`_parse_admission_policy`（L948-959）在 `start_run` 方法体中、`run_write` 调用前执行。使用 `AdmissionPolicy(queue_policy)` 做 StrEnum 解析，未知值抛 `ValueError`。

测试 `test_unknown_queue_policy_raises_value_error_without_transaction`（L489-509）验证：
- `queue_policy="unknown"` 抛 `ValueError`
- EventLog row count 不变（事务未打开）

### C4. follow-up resolved_execution_target 显式输入、非空、持久化、digest 排除、同 key retry 不改 target

**结论: PASS**

- `SubmitFollowupQueueAdmissionInput` 是 frozen dataclass，`resolved_execution_target: str` 是显式字段（L151-160）
- `_validate_followup_queue_input`（L962-975）在事务前校验 `resolved_execution_target.strip() != ""`
- `_CreateAdmissionRequest.from_followup_queue_input`（L698-717）使用 `admission_input.resolved_execution_target` 作为 `execution_target`
- 持久化通过 `CreateQueuedRunInput.execution_target` / `CreateRunningRunInput.execution_target` 写入 `host_runs.execution_target`
- `_followup_queue_semantic_digest`（L1254-1272）digest 字段为 `operation`、`input_digest`、`behavior`、`caller_semantic_digest`、`call_context_digest`，**不包含** `resolved_execution_target`
- 测试 `test_followup_idempotency_excludes_later_resolved_execution_target`（L357-393）验证：第二次 `resolved_execution_target="second-target"` 返回首次 Run，`latest.execution_target == "first-target"`

### C5. reject active 无 EventLog 且无幂等记录

**结论: PASS**

`_StartRunOperation._handle_active_run`（L472-529）reject 分支（L490-495）：
- 直接 `raise HostApiError(code=HostApiErrorCode.CONFLICT, ...)`
- 不调用 `idempotency_store.record_idempotent_result`
- 不调用 `event_log_store.append_event`
- 异常导致事务 rollback

测试 `test_reject_and_attach_active_have_expected_event_and_idempotency_effects`（L438-486）验证：
- `reject_error.value.code == HostApiErrorCode.CONFLICT`
- `_event_count` 不变
- `_count_rows("idempotency_records")` 只增加 1（来自后续 `attach_active` 调用）

### C6. attach_active 无 EventLog、写 null event ref 幂等记录并返回 active

**结论: PASS**

`_handle_active_run` attach_active 分支（L496-517）：
- 调用 `idempotency_store.record_idempotent_result`，`IdempotencyResultRef` 中 `created_event_id=None, created_event_sequence=None`
- 不调用 `event_log_store.append_event`
- 返回 `RunAdmissionResult` 中 `attached_active=True`

测试同一函数（L438-486）验证：
- `attached.run.run_id == active.run.run_id`
- `attached.attached_active is True`
- 幂等记录 `created_event_id` 为 `None`，`created_event_sequence` 为 `None`

### C7. idempotency conflict 映射为 IDEMPOTENCY_CONFLICT

**结论: PASS**

`_raise_if_digest_conflict`（L1037-1053）：
- `record.semantic_input_digest != semantic_digest` 时抛 `HostApiError(code=HostApiErrorCode.IDEMPOTENCY_CONFLICT, ...)`

测试 `test_same_idempotency_key_with_changed_input_digest_conflicts`（L396-435）验证：
- `exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT`
- `_event_count` 不变

### C8. promotion FIFO by accepted_event_sequence，active 存在 skipped

**结论: PASS**

`_PromoteNextQueuedRunOperation.__call__`（L606-662）：
- 调用 `promote_queued_run_in_transaction`（底层 P3-S3 helper）
- 底层 helper 先检查 `read_active_run_for_session`，active 存在返回 `skip_reason=ACTIVE_RUN_EXISTS`
- 底层 helper 调用 `read_earliest_queued_run`（按 `accepted_event_sequence` 排序）
- 底层 helper CAS 更新 `QUEUED -> RUNNING`
- admission 层将 `StateMutationStatus.UPDATED` 转为 `PromotionResult(skipped=False)`
- admission 层将 `StateMutationStatus.INVALID_STATE` / `NOT_FOUND` 转为 `PromotionResult(skipped=True)`

测试 `test_promotion_skips_with_active_then_promotes_earliest_queued_run`（L512-562）验证：
- active 存在时 `skipped.skipped is True`，`skip_reason.value == "active_run_exists"`
- 释放 active 后 promotion 选中 `first_queued`（先入队的 Run），其 `execution_target == "first-target"`
- 第二个 queued Run 仍为 `QUEUED`

### C9. wakeup port 只 no-op/test spy，不 dispatch

**结论: PASS**

- `AdmissionWakeupPort` 是 `Protocol`，定义 `wake_dispatch` 和 `wake_queue_promotion`（L123-148）
- `NoopAdmissionWakeupPort`（L227-249）两个方法都只 `del record` / `del session_id`
- 测试 `_WakeupSpy`（L96-119）只 append 到 list，不做真实 dispatch
- `_wake_dispatch_if_needed`（L1161-1173）只在 `pending_dispatch is not None` 时调用 `wake_dispatch`
- **注意**: `wake_queue_promotion` 在 P3-S4 中未被调用；promotion trigger 属于 P3-S5 scope。这是正确的 scope 控制。

### C10. 测试覆盖 plan expected assertions

**结论: PASS**

plan P3-S4 测试要求 vs 实际测试覆盖：

| plan 要求 | 测试函数 | 状态 |
|---|---|---|
| start on open Session with no active creates running Run and pending dispatch | `test_start_run_on_open_session_creates_running_attempt_and_dispatch` | ✓ |
| follow-up queue with active Run creates queued Run with no Attempt | `test_followup_queue_with_active_creates_queued_run_with_supplied_target` | ✓ |
| follow-up queue with active Run stores supplied target, not active target | 同上，`assert queued.run.execution_target == "queued-target"` | ✓ |
| follow-up queue without active creates running Run, starting Attempt and pending dispatch | `test_followup_queue_without_active_creates_running_run_with_four_facts` | ✓ |
| follow-up without active has exactly 4 canonical facts in order | 同上，`_event_types_for_run` 断言 | ✓ |
| follow-up without active stores supplied target | 同上，`assert result.run.execution_target == "follow-target"` | ✓ |
| closed Session rejects start/follow-up with invalid_state, no EventLog side effects | `test_closed_session_rejects_start_and_followup_without_event_side_effects` | ✓ |
| duplicate idempotency returns same Run, no extra events (both paths) | `test_duplicate_idempotency_returns_same_run_without_extra_events` | ✓ |
| duplicate idempotency with different target returns first Run | `test_followup_idempotency_excludes_later_resolved_execution_target` | ✓ |
| same key changed digest returns idempotency_conflict | `test_same_idempotency_key_with_changed_input_digest_conflicts` | ✓ |
| promotion chooses earliest accepted event_sequence | `test_promotion_skips_with_active_then_promotes_earliest_queued_run` | ✓ |
| concurrent promotion at most one | `test_concurrent_promotion_attempts_promote_at_most_one_run` | ✓ |

额外覆盖：
- `test_reject_and_attach_active_have_expected_event_and_idempotency_effects`：reject/attach_active 行为
- `test_unknown_queue_policy_raises_value_error_without_transaction`：未知 policy 事务前拒绝

## Findings

### F001: wake_queue_promotion 未在 P3-S4 中被调用（observation，非 finding）

`AdmissionWakeupPort.wake_queue_promotion` 已定义但未在 P3-S4 admission 路径中调用。这是正确的 scope 控制：promotion trigger 属于 P3-S5 Cancel And Terminal Closeout Orchestration。当前 P3-S4 只负责单次 `promote_next_queued_run` 的编排，不负责 terminal/cancel 后自动触发。

**分类**: observation，不需要修复。

### F002: promote_next_queued_run 不检查 Session 是否 CLOSED（observation，非 finding）

`promote_next_queued_run` 只检查 Session 是否存在（`_require_existing_session`），不检查是否 OPEN。这是正确的：plan §5 Data Flow 中 `promote_next_queued_run` 的校验是 `_require_existing_session`，且 promotion 是对已有 queued Run 的状态推进，不应因 Session 关闭而阻止已 accepted 的 queued Run 完成 promotion。

**分类**: observation，不需要修复。

## Validation Results

```
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
-> 20 passed in 0.20s

source .venv/bin/activate && python -m pyright dayu/host tests/host
-> 0 errors, 0 warnings, 0 informations

git diff --check
-> (clean)
```

## Conclusion

P3-S4 Admission And Queue Promotion 实现正确，scope 严格限于内部 admission 编排。10 个 review checkpoint 全部通过。无 blocking finding、无 accepted finding。测试覆盖 plan 全部 expected assertions，包括 closed session 无副作用和并发 promotion at-most-one。实现可接受。
