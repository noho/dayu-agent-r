# Gateflow Code Review Artifact: Host P5-S5 Active Cancel And Session-scope Cancel (AgentDS)

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-05-15
- **Scope**: dayu/host/admission.py, dayu/host/command.py, dayu/host/dispatch.py, tests/host/test_active_cancel_dispatch.py, tests/host/test_public_cancel_session_runs.py
- **Design Source**: docs/host/design.md §22 Cancel, §17 Local EngineWorker, §9 Admission
- **Implementation Artifact**: docs/reviews/gateflow-implementation-host-p5-s5-active-cancel-session-scope-20260515.md
- **Reviewed Commits**: Uncommitted workspace changes on branch `feat/host-phase5-local-dispatch`

---

## Findings

### Finding 1 [MEDIUM]: 测试使用裸 SQL UPDATE 绕过生产路径 CAS 与 EventLog，存在 false confidence 风险

**Evidence**:

tests/host/test_public_cancel_session_runs.py:207-219
```python
def _mark_attempt_running(db_path: Path, attempt_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE host_attempts SET status = ? WHERE attempt_id = ?",
            ("running", attempt_id),
        )
```

tests/host/test_public_cancel_session_runs.py:222-235
```python
def _mark_run_status(db_path: Path, run_id: str, status: RunStatus) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE host_runs SET status = ? WHERE run_id = ?",
            (status.value, run_id),
        )
```

这两个辅助函数直接通过裸 SQL 修改 durable 表 `host_attempts` 和 `host_runs`，用于构造 active worker (`RUNNING` attempt) 和 deferred (`WAITING`) 测试前置状态。

**为什么是问题**:

1. **绕过 CAS (Compare-And-Swap)**: 生产路径中 Attempt 状态从 `STARTING` 迁移到 `RUNNING` 必须通过 `mark_attempt_running_row`，该函数对 attempt row 做 CAS 校验；裸 SQL `UPDATE` 不做任何前置状态校验。
2. **绕过 EventLog**: `ATTEMPT_RUNNING` canonical fact 不会被追加，但 `active_cancel_closeout_in_transaction` 依赖 `RUN_CANCELLING` fact 中的 `cancel_request_event_id` 链（engine_ingest.py:661-664）。测试未覆盖 EventLog 完整性校验路径。
3. **绕过 dispatch record 状态联动**: 生产路径中 `_accept_worker_running` 同时更新 `host_attempts`（`mark_attempt_running_row`）和 `host_attempt_dispatch_records`（`mark_dispatch_worker_accepted_row`），且要求两者都 `UPDATED`。裸 SQL 只改 attempt，dispatch record 仍为 `PENDING`。

**受影响测试**:

- `test_cancel_session_runs_cancels_queued_and_active_worker` — 依赖 `_mark_attempt_running` 构造 active worker 状态
- `test_cancel_session_runs_active_replay_does_not_append_facts` — 同上
- `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` — 依赖 `_mark_run_status` 构造 WAITING 状态

**注意**: `test_active_cancel_dispatch.py` 中的 `test_cancel_run_active_worker_propagates_and_closes_cancelled` 和 `test_late_cancel_does_not_overwrite_terminal` 走完整 scheduler dispatch 路径，不依赖裸 SQL，这两个测试的信心是可靠的。

**建议修复**:

- 优先：将这些测试改为通过 scheduler dispatch 路径设置 RUNNING 状态，参考 `test_cancel_run_active_worker_propagates_and_closes_cancelled` 的模式。
- 次选：如果必须快速构造状态，至少通过 `mark_attempt_running_row` + `mark_dispatch_worker_accepted_row`（通过 durable transaction runner），而非裸 SQL。
- WAITING 状态测试可以保留裸 SQL 作为 deferred phase 占位，但必须在测试注释中明确标注"bypasses CAS, only for deferred state classification check"。

**Severity**: MEDIUM — 不阻塞当前 phase gate（核心 cancel 行为另有完整路径测试覆盖），但降低了回归保护质量，可能在后续 phase 修改 durable schema 时产生误报通过。

---

### Finding 2 [LOW]: Session cancel replay 多 active target 时仅重传播首个，其余 target 静默丢失

**Evidence**:

dayu/host/admission.py:2148-2187 `_active_cancelling_targets_for_session_replay`
```python
def _active_cancelling_targets_for_session_replay(...) -> tuple[ActiveCancelTarget, ...]:
    if record.created_event_id is None:
        return ()
    event = EventLogStore().read_event_by_id(transaction, record.created_event_id)
    if event is None or event.session_id != session_id or event.run_id is None:
        return ()
    run = read_run_by_id(transaction, event.run_id)
    if (run is None or run.session_id != session_id
        or run.status != RunStatus.CANCELLING or run.current_attempt_id is None):
        return ()
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    if attempt is None or attempt.status != AttemptStatus.RUNNING:
        return ()
    return (ActiveCancelTarget(run_id=run.run_id, attempt_id=attempt.attempt_id,
                               execution_id=attempt.execution_id, reason=reason),)
```

该函数始终返回至多 1 个 target。幂等记录的 `created_event_id` 逻辑为：

dayu/host/admission.py:1296-1311
```python
created_event_id=(
    first_active_cancel_event_id
    if first_active_cancel_event_id is not None
    else first_cancel_event_id
),
```

`first_active_cancel_event_id` 是第一个成功追加了 `CANCEL_REQUESTED` 的 active target 的 event id。

**场景**: Session 有 2 个 active worker Run A 和 Run B，首次 `cancel_session_runs` 同时取消两者：
- A 的 cancel 先执行，`first_active_cancel_event_id` = A 的 cancel event id
- B 的 cancel 后执行，`active_cancel_targets` 包含 A 和 B 两者（首次调用正确传播两个目标）
- 幂等记录 `created_event_id` = A 的 cancel event id
- 重放时 `_active_cancelling_targets_for_session_replay` 只返回 A 的 target
- B 的 active worker 在重放时不会收到 cancel 传播

**分析**:

- 设计文档未要求 replay 必须重传播所有 target；实现 artifact 明确声明 "幂等 replay 只基于幂等记录首个 created_event_id 重新传播一个目标"
- 重传播本身是 best-effort（`_propagate_active_cancel_targets` 吞掉 RuntimeError），worker 可能已不在 registry 中
- 单 active worker 场景（当前 Phase 5 最常见情况）不受影响
- 如果 worker 在首次 cancel 后已响应并产出 `run_cancelled`，该 Run 已终态，replay 无需重传播

**建议**: 在 residual risks 中记录此限制，由后续 phase 根据实际多 worker 场景需要决定是否扩展为遍历所有 CANCELLING + RUNNING attempt 的 Run。

**Severity**: LOW — 已知设计限制，best-effort 语义下可接受，但属于代码审查应标出的语义边界。

---

### Finding 3 [LOW]: `cancel_run` 幂等重放不重传播 active cancel target，与 `cancel_session_runs` 重放行为不对称

**Evidence**:

dayu/host/admission.py:1980-1988 `_idempotent_cancel_result`
```python
return CancelRunResult(
    run=run,
    attempt=_read_current_attempt(transaction, run),
    dispatch_record=_read_current_dispatch_record(transaction, run),
    promotion=None,
    active_cancel_target=None,  # <-- 始终为 None
    idempotent_replay=True,
    released_active_slot=False,
)
```

与之对比，`_idempotent_session_cancel_result`（line 1991-2030）会调用 `_active_cancelling_targets_for_session_replay` 返回需要重传播的 target，且在 command.py 中 `cancel_session_runs` 会调用 `_propagate_active_cancel_targets` 处理这些 target。

而 command.py `cancel_run`（line 355-403）也调用 `_propagate_active_cancel_targets`，但因为 `_idempotent_cancel_result` 的 `active_cancel_target` 始终为 None，所以幂等重放永远不会重传播。

**分析**:

- 设计意图可理解：`cancel_run` 是单 Run 操作，首次调用已传播 cancel；重放只是"确认状态"
- 但如果首次 cancel 在 commit 后、propagate 前崩溃，重放不会补救
- `cancel_session_runs` 选择重传播是有意的（session 级操作更关键），这种不对称是显式设计决定

**建议**: 在代码注释中明确记录此不对称性的设计理由，避免未来维护者误认为这是遗漏。

**Severity**: LOW — 显式设计决定，且 `cancel_run` 重放丢失传播的窗口极小（commit 后立刻 propagate，中间无 yield 点）。

---

### Finding 4 [OBSERVATION]: Lane token 释放确认由 worker finally 管理，cancel path 未触及

**Evidence**:

dayu/host/dispatch.py:808-826 `_consume_worker_events`
```python
try:
    async for event in handle.events():
        worker_event_index += 1
        ingestor.ingest(...)
finally:
    self._active_handles.discard(handle)
    self._active_registry.unregister(
        attempt_id=record.attempt_id,
        execution_id=record.execution_id,
    )
    await handle.close()
    await token.release()  # <-- lane release in finally
```

dayu/host/dispatch.py:188-204 `ActiveWorkerRegistry.cancel`
```python
def cancel(self, message: ActiveCancelMessage) -> bool:
    with self._lock:
        entry = self._entries.get((message.attempt_id, message.execution_id))
    if entry is None or entry.run_id != message.run_id:
        return False
    entry.cancellation_token.request_cancel(message.reason)
    try:
        entry.handle.cancel(message.reason)
    except RuntimeError:
        return True
    return True
    # 注意：此处不释放 lane token
```

**验证结论**: 符合设计。Cancel path 只设置 cancellation token 并调用 worker handle cancel，不释放 lane token。Lane token 生命周期完全由 `_consume_worker_events` 的 `finally` 块管理，确保无论正常 terminal、cancel 触发 terminal、还是异常退出，lane 都会被释放。

**Severity**: OBSERVATION — 无问题，确认符合设计约束。

---

### Finding 5 [OBSERVATION]: Active registry 身份约束与 run_id mismatch 保护正确

**Evidence**:

dayu/host/dispatch.py:149-204
- 注册 key: `(attempt_id, execution_id)` (line 171)
- 查找 key: `(message.attempt_id, message.execution_id)` (line 196)
- 附加 `run_id` 校验: `entry.run_id != message.run_id` → return False (line 197)
- 注销: `finally` 块中 `unregister(attempt_id=..., execution_id=...)` (line 821-824)

**验证结论**:
1. `(attempt_id, execution_id)` 作为 registry key 是正确的——这两个 ID 唯一标识一次 worker accept。
2. `run_id` 额外校验防止了 registry 残留导致的误取消（虽然极不可能，因为 execution_id 已唯一）。
3. `unregister` 覆盖了 `finally` 路径（正常完成、cancel 触发 terminal、异常），也覆盖了 `close()` → `_consume_worker_events` finally（dispatch.py:414-433 中 `handle.close()` 会导致 `events()` 迭代器退出，进入 finally）。

**Severity**: OBSERVATION — 无问题，确认符合设计约束。

---

### Finding 6 [OBSERVATION]: EngineEventIngestor first-terminal-wins race 机制正确

**Evidence**:

dayu/host/engine_ingest.py:1132-1144 `_late_rejection_reason`
```python
def _late_rejection_reason(context: _ValidatedCandidate) -> str | None:
    if (context.run.terminal_event_id is not None
        or context.attempt.terminal_event_id is not None):
        return _REASON_TERMINAL_ALREADY_CLOSED
    return None
```

流程：
1. `ingest()` → 先校验 durable context（execution_id 匹配）
2. 检查 duplicate（已存在的 terminal event ids）
3. 检查 late rejection（Run/Attempt 已有 terminal_event_id）
4. 才进入 `_ingest_validated` 做具体事件处理

对于 `FINAL_ANSWER` vs `RUN_CANCELLED` race:
- 两者都走 `terminal_closeout_in_transaction` / `active_cancel_closeout_in_transaction`
- 底层 CAS 更新 Run/Attempt 行，先提交者设 `terminal_event_id`
- 后到者在 `_late_rejection_reason` 被拒绝，记录 diagnostic
- `_close_active_cancel` 额外要求 `RUN_CANCELLING` fact 已存在（line 655-660），防止未经过 `cancel_run` 的 `run_cancelled` 被接受

测试覆盖：`test_late_cancel_does_not_overwrite_terminal` 验证 terminal（succeeded）先提交时 late cancel 返回 current terminal 状态。

**Severity**: OBSERVATION — 无问题，确认 first-terminal-wins 逻辑正确。

---

### Finding 6.1 [OBSERVATION]: EngineEventIngestor wakeup_port 对 active cancel closeout 正确触发 queue promotion

**Evidence**:

dayu/host/engine_ingest.py:798-820 `_with_terminal_promotion_retry`
```python
def _with_terminal_promotion_retry(
    self, result: EngineIngestResult, *, session_id: str
) -> EngineIngestResult:
    if result.terminal_closeout and result.status in (
        EngineIngestStatus.ACCEPTED,
        EngineIngestStatus.DUPLICATE,
    ):
        self._wakeup_port.wake_queue_promotion(session_id)
        return EngineIngestResult(
            status=result.status,
            events=result.events,
            terminal_closeout=True,
            promotion_triggered=True,
            reason=result.reason,
        )
    return result
```

`_close_active_cancel` (line 610-703) 返回 `terminal_closeout=True, promotion_triggered=False`。这**不是 bug**——`promotion_triggered` 在 write transaction 内部始终为 False，真正的 promotion wakeup 由 `_with_terminal_promotion_retry` 在 transaction commit 后统一执行。

调用链：
1. `ingest()` → `_transaction_runner.run_write(_operation)` → 返回 result（terminal_closeout=True, promotion_triggered=False）
2. `ingest()` → `_with_terminal_promotion_retry(result, session_id=...)` → 检测到 terminal_closeout=True + ACCEPTED → 调用 `wakeup_port.wake_queue_promotion(session_id)` → 返回 promotion_triggered=True

**验证结论**: `_close_active_cancel` 和 `_close_terminal` 均通过同一 `_with_terminal_promotion_retry` 路径触发 queue promotion。active cancel closeout 释放 active slot 后，queue promotion 会被正确唤醒。**无 blocking 问题**。

**Severity**: OBSERVATION — 无问题，wakeup_port 接线正确。

---

### Finding 7 [OBSERVATION]: CANCELLING 状态不重复追加 RUN_CANCELLING 的实现正确

**Evidence**:

dayu/host/durable/run_transition.py:1100-1107 `request_active_attempt_cancel_in_transaction`
```python
if run.status == RunStatus.CANCELLING and run.current_attempt_id is not None:
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=run,
        attempt=attempt,
        dispatch_record=_read_dispatch_for_attempt(transaction, attempt),
    )
```

当 Run 已是 `CANCELLING` 时，直接返回当前状态，不追加 `CANCEL_REQUESTED` 或 `RUN_CANCELLING`。

调用方（admission.py `_cancel_active_attempt` line 1145-1161）通过 `_require_event_sequence_if_present` 处理 event 可能未写入的情况：
```python
cancel_request_sequence = _require_event_sequence_if_present(
    transaction, self.event_log_store, cancel_request_event_id,
)
self.idempotency_store.record_idempotent_result(
    ...,
    created_event_id=cancel_request_event_id
    if cancel_request_sequence is not None
    else None,
    ...
)
```

当 `cancel_request_sequence` 为 None 时，`created_event_id` 设为 None——正确反映了"本次调用未创建新事实"。

**验证结论**: CANCELLING 重复 cancel 不会追加重复 facts，但会记录新的幂等记录（`created_event_id=None`），且返回 `active_cancel_target` 用于 best-effort 重新传播。

**Severity**: OBSERVATION — 无问题，确认符合设计。

---

### Finding 8 [OBSERVATION]: cancel_session_runs 分类正确，WAITING/RECOVERING 无 partial mutation

**Evidence**:

dayu/host/admission.py:1325-1348 `_read_supported_targets_or_raise`
```python
for run in read_non_terminal_runs_for_session(transaction, self.session_id):
    target = _session_cancel_target_for_run(transaction, run)
    if target is None:
        raise HostApiError(
            code=HostApiErrorCode.UNSUPPORTED_OPERATION,
            message="cancel_session_runs supports only queued and "
                    "pre-dispatch STARTING Runs in Phase 4",
            retryable=False,
        )
    targets.append(target)
```

分类在遍历中完成：先全量分类所有 non-terminal Run，任一不支持立即抛出 `UNSUPPORTED_OPERATION`。由于在同一个 write transaction 内，异常会回滚整个事务，确保不会出现 partial mutation。

`_session_cancel_target_for_run` (line 2190-2249) 的分类逻辑：
- `QUEUED` → 支持 (queued cancel)
- `WAITING` / `RECOVERING` → 不支持 (返回 None)
- `RUNNING` with `STARTING` attempt + direct cancelable dispatch → 支持 (pre-dispatch cancel)
- `RUNNING` / `CANCELLING` with `RUNNING` attempt → 支持 (active worker cancel)
- 其他状态 → 不支持 (返回 None)

测试覆盖：`test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 验证 WAITING 存在时无 partial mutation。

**注意**: error message 仍写 "Phase 4"，而实际已进入 Phase 5——建议更新 message 或使用 phase-neutral 表述。

**Severity**: OBSERVATION — 无功能问题，message 文本滞后属于 cosmetic。

---

### Finding 9 [OBSERVATION]: Command facade 只在 durable commit 后 best-effort 传播，无反向依赖

**Evidence**:

dayu/host/command.py:391-403 `cancel_run`
```python
_propagate_active_cancel_targets(
    (ActiveCancelMessage(...),)
    if result.active_cancel_target is not None
    else ()
)
return run_snapshot_from_row(result.run)
```

dayu/host/command.py:808-818 `_propagate_active_cancel_targets`
```python
def _propagate_active_cancel_targets(
    targets: tuple[ActiveCancelMessage, ...]
) -> None:
    for target in targets:
        cancel_active_worker(target)
```

`cancel_active_worker` (dispatch.py:263-270) 调用 `DEFAULT_ACTIVE_WORKER_REGISTRY.cancel(message)`，其中 `handle.cancel()` 的 `RuntimeError` 被吞掉（dispatch.py:201-203）。

**验证结论**:
1. 传播在 `admission_service.cancel_run()` / `cancel_session_runs()` 返回后执行——此时 durable commit 已完成。
2. 传播失败不影响 durable state，无 rollback。
3. 传播是单向的：command → dispatch registry，不存在 durable/ephemeral 状态反向依赖。
4. `handle.cancel()` 的 `RuntimeError` 被吞掉符合 best-effort 语义。

**Severity**: OBSERVATION — 无问题，确认符合设计约束。

---

### Finding 10 [OBSERVATION]: cancel_session_runs 幂等 replay 不取消首次后新 Run 且不追加 facts

**Evidence**:

dayu/host/admission.py:1991-2030 `_idempotent_session_cancel_result`
- 返回当前 `session_snapshot_from_rows`——反映当前真实状态，包含首次操作后新增的 Run
- `cancelled_run_count=0`——明确表示本次未取消任何 Run
- `_active_cancelling_targets_for_session_replay` 只重传播仍 active 的 CANCELLING target
- 不对新 Run 做任何状态变更

测试覆盖：
- `test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run` 验证新 Run 不被取消
- `test_cancel_session_runs_active_replay_does_not_append_facts` 验证不追加 CANCEL_REQUESTED / RUN_CANCELLING
- `test_cancel_session_runs_no_supported_run_records_idempotency_without_event` 验证空 Session 场景

**局限性（与 Finding 2 关联）**：如果首次操作后有新的 active worker Run 进入 CANCELLING（例如通过另一个 `cancel_run` 调用），replay 不会重传播这些"非首次产生"的 CANCELLING target。这是因为 `created_event_id` 只锚定首次操作的事件。对于当前 Phase 5 的 Session 单 active worker 约束，此限制无实际影响。

**Severity**: OBSERVATION — 核心幂等语义正确。

---

## Required Fixes

1. **[Finding 1]** 将 `test_public_cancel_session_runs.py` 中的 `_mark_attempt_running` 替换为通过 scheduler dispatch 路径（或至少通过 `mark_attempt_running_row` + `mark_dispatch_worker_accepted_row` via transaction runner）设置 RUNNING 状态。WAITING 状态裸 SQL 可保留但需加注释说明 deferred phase 占位。

2. **[Finding 8]** 更新 `_read_supported_targets_or_raise` 中的 error message，将 "Phase 4" 改为 phase-neutral 表述或 "Phase 5"。

## Residual Risks

1. **Active cancel watchdog 未实现**：若 worker 收到 cancel 后长期不产出 terminal（例如 LLM call 卡住），Run 会停留在 CANCELLING。当前无超时升级到 LOST 的机制。已由 implementation artifact 记录，留给后续 owner。

2. **Session cancel replay 多 target 局限**（Finding 2）：当前单 active worker 约束下无实际影响，多 worker 场景需扩展。

3. **cancel_run 幂等重放不重传播**（Finding 3）：崩溃窗口极小（commit 后立刻 propagate），但理论存在。

4. **测试裸 SQL 风险**（Finding 1）：如果后续 phase 修改 `host_attempts` schema 或 CAS 逻辑，相关测试可能误报通过。

5. **`_NeverCancelledToken` 占位**：`_consume_worker_events` 中 cancellation_token 已通过 `_HostCancellationToken` 正确注入，但 Engine 侧是否真正观察 token 取决于 Engine 实现，超出 Host 审查范围。

## Verdict

**APPROVED with medium findings**

8 项审查重点逐项结论：

| # | 审查项 | 结论 |
|---|--------|------|
| 1 | cancel path 不直接释放 lane token | PASS — lane 释放仅由 worker finally 管理 |
| 2 | active registry 身份约束与 unregister 覆盖 | PASS — (attempt_id, execution_id) 约束 + finally 注销 |
| 3 | cancel_run 状态覆盖完整性 | PASS — queued/predispatch/active/terminal 路径均正确 |
| 4 | command facade best-effort 传播与无反向依赖 | PASS — durable commit 后传播，不 rollback |
| 5 | cancel_session_runs 分类与无 partial mutation | PASS — 先全量分类，异常回滚事务 |
| 6 | 幂等 replay 语义 | PASS with observation — 多 target 局限见 Finding 2 |
| 7 | EngineEventIngestor first-terminal-wins | PASS — CAS + late rejection 正确 |
| 8 | 测试覆盖与 DB 直改风险 | MEDIUM — 裸 SQL 绕过 CAS，见 Finding 1 |

核心 cancel 路径实现正确，与设计文档 §22 一致。唯一需要修复的是测试中的裸 SQL 直改（Finding 1），建议在合入前处理。其余 LOW/OBSERVATION 级发现可在后续 phase 中逐步完善。
