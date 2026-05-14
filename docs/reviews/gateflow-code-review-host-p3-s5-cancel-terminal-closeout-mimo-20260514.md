# Gateflow Code Review: Host Phase 3 P3-S5 Cancel And Terminal Closeout Orchestration

- **reviewer**: AgentMiMo
- **artifact**: `docs/reviews/gateflow-code-review-host-p3-s5-cancel-terminal-closeout-mimo-20260514.md`
- **baseline**: `f45dc3f`
- **branch**: `feat/host-phase3-admission-state-machine`
- **scope**: `dayu/host/admission.py`, `dayu/host/durable/run_transition.py`, `tests/host/test_admission_queue.py`, `tests/host/test_run_attempt_transitions.py`
- **plan reference**: `docs/host/phase3-session-run-attempt-admission-plan.md` § P3-S5

## Verification Results

| check | result |
| --- | --- |
| `pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q` | **29 passed in 0.23s** |
| `python -m pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **passed** |

## Findings Summary

| # | severity | category | file | finding |
| --- | --- | --- | --- | --- |
| F1 | **INFO** | test-coverage | `test_admission_queue.py` | Attempt RUNNING 的 pre-dispatch cancel 未在 admission 层测试中覆盖（仅 `test_cancel_attempt_running_is_phase3_invalid_state_without_side_effects` 覆盖了 Attempt RUNNING 状态下的拒绝，但未覆盖 RUNNING Run + RUNNING Attempt 的组合路径） |
| F2 | **INFO** | test-coverage | `test_run_attempt_transitions.py` | `cancel_predispatch_starting_in_transaction` 未测试 `attempt != STARTING` 或 `dispatch != PENDING` 的 `INVALID_STATE` 分支 |
| F3 | **INFO** | scope-check | all | 无 Engine/WorkerProxy/scheduler/lane/wait/recovery/public facade 引用侵入 |

**Overall**: 无 blocking findings。实现与 plan 完全对齐，scope 边界干净。

## Detailed Review

### 1. Scope Boundary Check

**结论**: PASS。

- `admission.py` 不 import Engine、runtime lane、WorkerProxy、LocalProxy、RemoteProxy、Service、UI 或 Fins。
- `run_transition.py` 不 import Engine、WorkerProxy、scheduler 或 public facade。
- 所有新增代码严格在 `dayu/host/admission.py` 和 `dayu/host/durable/run_transition.py` 内。
- 新增 import 仅限 `dayu.host.api`（`AttemptStatus`、`CancelRunRequest`）、`dayu.host.durable.run_transition`（cancel/terminal helpers）和 `dayu.host.durable.state`（既有状态读取），均为 plan 允许范围。
- 未修改 `dayu/host/api.py` 或其他 forbidden files。

### 2. Cancel Queued Path

**结论**: PASS。

`_CancelRunOperation._cancel_queued()` (admission.py:871-929) 正确实现了：

- 先读 idempotency record，命中则重放结果（不重复 promotion）。
- 调用 `cancel_queued_in_transaction` 写 `CANCEL_REQUESTED` + `RUN_CANCELLED`。
- 不创建 Attempt（`run_transition.py:616-675`：queued cancel 只 append 两个 event 并调用 `cancel_queued_run_row`，无 `insert_attempt` 调用）。
- 记录 idempotency（`cancel_request_event_id` 作为 `created_event_id`），同 key 重试返回同一结果。
- `released_active_slot=False`，不触发 promotion。

`run_transition.py` 中 `cancel_queued_in_transaction` (line 616-675)：
- 检查 `run.status == RunStatus.QUEUED`，非 QUEUED 返回 `INVALID_STATE`。
- 仅写 `CANCEL_REQUESTED` 和 `RUN_CANCELLED` 两个 event。
- 调用 `cancel_queued_run_row` 更新 Run row。
- 返回 `attempt=None, dispatch_record=None`。

### 3. Cancel Pre-dispatch Starting Path

**结论**: PASS。

`_CancelRunOperation._cancel_predispatch_starting()` (admission.py:931-990) 正确实现了：

- 调用 `cancel_predispatch_starting_in_transaction`。
- 该函数 (run_transition.py:678-788) 严格检查 `Run RUNNING + current_attempt_id != None + Attempt STARTING + dispatch PENDING`。
- 原子写入三个 event：`CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`。
- 原子更新三个 row：dispatch record → `cancelled`、Attempt → `CANCELLED`、Run → `CANCELLED`。
- 不通知 WorkerProxy（无 dispatch/wakeup 调用）。
- `released_active_slot=True`，由外层 `cancel_run` 在 commit 后触发 promotion。

### 4. Terminal Closeout Path

**结论**: PASS。

`closeout_attempt_terminal()` (admission.py:479-509) 正确实现了：

- 校验只允许 `(SUCCEEDED, SUCCEEDED)`、`(FAILED, FAILED)`、`(LOST, LOST)` 三对终态（`_validate_closeout_attempt_terminal_input` line 1824-1833）。
- 终态映射函数 `_attempt_terminal_event_type` / `_run_terminal_event_type` (run_transition.py:1484-1515) 只支持 `SUCCEEDED`、`FAILED`、`LOST`，不支持 `CANCELLED`。
- 前置条件检查 `_invalid_terminal_precondition` (run_transition.py:1444-1481) 要求 `Run RUNNING + current_attempt_id 匹配 + Attempt STARTING`。
- Attempt `RUNNING` 返回 `INVALID_STATE`（run_transition.py:1473-1474：`attempt.status != AttemptStatus.STARTING`）。
- cancellation terminal 由 cancel path 处理，不在此 helper 中。

### 5. After-commit Promotion Orchestration

**结论**: PASS。

- `_promote_after_release()` (admission.py:1597-1608) 先调用 `wakeup_port.wake_queue_promotion(session_id)`，然后在**新事务**中调用 `service.promote_next_queued_run(session_id)`。
- `cancel_run` (admission.py:464-477) 只在 `released_active_slot=True` 时触发 promotion。
- `closeout_attempt_terminal` (admission.py:500-508) 始终触发 promotion（因为 terminal closeout 总是释放 active slot）。
- rollback 不触发 promotion：`_CancelRunOperation.__call__` 在事务内执行，若事务 rollback 则外层 `cancel_run` 的 `result.released_active_slot` 分支不会执行。
- 测试 `test_rollback_before_cancel_commit_does_not_wake_or_promote` (test_admission_queue.py:832-897) 明确验证了 rollback 场景。

### 6. Unsupported States → Phase 3 `invalid_state`

**结论**: PASS。

`_CancelRunOperation.__call__` (admission.py:853-869)：
- `QUEUED` → `_cancel_queued`。
- `RUNNING` → `_cancel_predispatch_starting`。
- 其他所有状态（包括 `WAITING`、`RECOVERING`、`CANCELLING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST`）→ `INVALID_STATE`。

`_cancel_predispatch_starting` 内部 (admission.py:949-966 → run_transition.py:678-788)：
- `Run != RUNNING` → `INVALID_STATE`。
- `current_attempt_id is None` → `INVALID_STATE`。
- `Attempt != STARTING` → `INVALID_STATE`。
- `dispatch != PENDING` → `INVALID_STATE`。
- 覆盖了 `WAITING`、`RECOVERING`、`CANCELLING`、dispatching、Attempt `RUNNING` 等所有 Phase 3 不支持的状态。

terminal closeout `_invalid_terminal_precondition` (run_transition.py:1469-1480)：
- `Run != RUNNING` → `INVALID_STATE`。
- `current_attempt_id != attempt_id` → `INVALID_STATE`。
- `attempt.run_id != run.run_id` → `INVALID_STATE`。
- `Attempt != STARTING` → `INVALID_STATE`（覆盖 Attempt `RUNNING` 等）。

### 7. Idempotency And Conflict/Error Mapping

**结论**: PASS。

- `cancel_run` 幂等 scope 为 `(cancel_run, run_id, client_request_id)`，语义 digest 包含 `reason`、`mode`、`caller_semantic_digest`、`call_context_digest`。
- 幂等记录 `result_ref` 指向 `run_id`，`created_event_id` 指向 `CANCEL_REQUESTED` event。
- 同 key 同 digest 重试返回 `_idempotent_cancel_result`（`released_active_slot=False`，不重复 promotion）。
- 同 key 不同 digest → `IDEMPOTENCY_CONFLICT`。
- `NOT_FOUND` → `HostApiErrorCode.NOT_FOUND`。
- `INVALID_STATE` / `CAS_LOST` → `HostApiErrorCode.INVALID_STATE`（`_raise_for_cancel_transition_status` line 1678-1700）。
- terminal closeout 同理（`_raise_for_terminal_transition_status` line 1703-1725）。

### 8. Test Coverage Assessment

**结论**: PASS with minor INFO findings.

Plan 要求的 tests / expected assertions 覆盖情况：

| plan assertion | test | status |
| --- | --- | --- |
| cancel queued writes no Attempt and can be retried idempotently | `test_cancel_queued_run_is_idempotent_and_creates_no_attempt` | ✅ |
| cancel pre-dispatch starting marks dispatch cancelled, Attempt CANCELLED, Run CANCELLED | `test_cancel_predispatch_starting_promotes_exactly_one_queued_run` | ✅ |
| cancel terminal Run cannot rewrite terminal | `test_cancel_terminal_run_returns_invalid_state_without_new_facts` | ✅ |
| terminal closeout of active Run promotes exactly one queued Run after commit | `test_terminal_closeout_promotes_exactly_one_queued_run_after_commit` | ✅ |
| cancel active pre-dispatch promotes exactly one queued Run after commit | `test_cancel_predispatch_starting_promotes_exactly_one_queued_run` | ✅ |
| rollback before commit does not invoke wakeup/promotion | `test_rollback_before_cancel_commit_does_not_wake_or_promote` | ✅ |

`run_transition.py` 低层测试：

| behavior | test | status |
| --- | --- | --- |
| terminal closeout succeeded facts | `test_terminal_closeout_appends_concrete_terminal_events` | ✅ |
| terminal closeout failed/lost facts | `test_terminal_closeout_supports_failure_and_lost_facts` | ✅ |
| Attempt RUNNING terminal closeout → invalid_state | `test_terminal_closeout_rejects_attempt_running_in_phase3` | ✅ |
| cancel queued terminal Run → invalid_state | `test_cancel_queued_terminal_run_returns_invalid_state` | ✅ |
| cancel pre-dispatch starting updates all three | `test_cancel_predispatch_starting_updates_dispatch_attempt_and_run` | ✅ |
| CAS loser rollback | `test_promote_cas_loser_keeps_queued_state` | ✅ |
| active Run skip | `test_promote_active_run_skip_does_not_append_queued_started_event` | ✅ |

**F1** (INFO): `test_cancel_attempt_running_is_phase3_invalid_state_without_side_effects` 覆盖了 admission 层对 Attempt RUNNING 的拒绝，但该测试构造的是 `RUNNING Run + RUNNING Attempt`（通过 `_force_attempt_status`），而非 `RUNNING Run + STARTING Attempt + dispatching`（Phase 3 不存在 dispatching 状态，所以无法测试）。这不是遗漏，而是 Phase 3 schema 限制。

**F2** (INFO): `run_transition.py` 中 `cancel_predispatch_starting_in_transaction` 的 `attempt.status != STARTING` 或 `dispatch.status != PENDING` 分支在低层测试中未直接覆盖（admission 层测试通过 `_force_attempt_status` 间接覆盖了 Attempt RUNNING 路径）。可考虑在 `test_run_attempt_transitions.py` 中增加直接的低层 precondition 失败测试，但非 blocking。

### 9. Code Quality

- 所有 dataclass 使用 `frozen=True, slots=True`，符合项目约束。
- 所有函数和类提供完整中文 docstring，包含参数、返回值、异常。
- 模块级私有辅助函数优先（如 `_promote_after_release`、`_idempotent_cancel_result`、`_validate_closeout_attempt_terminal_input`）。
- 无魔法数字/字符串（常量定义在模块顶部）。
- 无 `object`、`Any`、无类型参数。
- 无胶水 seam 或不必要的兼容性代码。

## Conclusion

P3-S5 实现与 plan 完全对齐，scope 边界无侵入，cancel/terminal/promotion 三条路径逻辑正确，幂等和错误映射完整，测试覆盖所有 plan 要求的 assertions 和 side effects。29 tests passed，pyright 0 errors，git diff --check passed。无 blocking findings。
