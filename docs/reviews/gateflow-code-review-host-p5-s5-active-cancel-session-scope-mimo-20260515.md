# Code Review: Host P5-S5 Active Cancel And Session-scope Cancel

- Reviewer: AgentMiMo
- Date: 2026-05-15
- Scope: `dayu/host/admission.py`, `dayu/host/command.py`, `dayu/host/dispatch.py`, `tests/host/test_active_cancel_dispatch.py`, `tests/host/test_public_cancel_session_runs.py`
- Design source: `docs/host/design.md` §22 Cancel, §17 Local EngineWorker, §9 Admission
- Control doc: `docs/host/implementation-control.md`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s5-active-cancel-session-scope-20260515.md`

---

## Findings

### F1 [Medium] Session cancel 幂等 replay 只重放首个 active target

**Location**: `admission.py:2148-2187` (`_active_cancelling_targets_for_session_replay`)

**Description**: `_idempotent_session_cancel_result` 调用 `_active_cancelling_targets_for_session_replay` 做 replay。该函数只从 `record.created_event_id` 读取一个 `run_id`，最多返回一个 `ActiveCancelTarget`。而 `created_event_id` 在首次 cancel 时只记录 `first_active_cancel_event_id`（第一个 active target 的 cancel event），后续 active target 被忽略。

当同一 Session 存在多个 active worker Run（例如用户快速 start_run 多次、promotion 尚未竞争时），首次 cancel 会正确取消全部 active target 并返回全部 `active_cancel_targets`；但幂等 replay 只重放第一个 active target 的 cancel propagation，后续 active worker 若未收到首次 cancel 信号，replay 不会补发。

**Evidence**:
```python
# admission.py:2148-2187
def _active_cancelling_targets_for_session_replay(...):
    if record.created_event_id is None:
        return ()
    event = EventLogStore().read_event_by_id(transaction, record.created_event_id)
    # 只读一个 event → 只关联一个 run_id → 最多返回一个 target
    ...
    return (ActiveCancelTarget(run_id=run.run_id, ...),)
```

```python
# admission.py:1295-1313 — idempotency record 只存 first_active_cancel_event_id
IdempotencyResultRef(
    created_event_id=(
        first_active_cancel_event_id
        if first_active_cancel_event_id is not None
        else first_cancel_event_id
    ),
    ...
)
```

**Risk**: 多 active target 场景下，replay 不会补发后续 active worker 的 cancel。这是可接受的 best-effort 语义（replay 已返回全部 active_cancel_targets 给调用方，调用方可自行决定是否再次传播），但当前 command.py 的 `_propagate_active_cancel_targets` 只传播 replay 返回的 targets，因此后续 target 的 cancel 永久丢失。

**Assessment**: 当前架构下同一 Session 多个 concurrent active worker 是罕见场景（FIFO promotion + single active slot 设计约束）。但若发生，这是一个 silent no-cancel bug。标记为 medium 而非 blocking，因为：
1. 多 active 并发需 Promotion 和 Cancel 并行竞争才可能发生
2. 最终 worker 超时 watchdog（后续 phase）会兜底

**Recommended fix**: 将 `created_event_id` 改为存储首个 active cancel event id 列表（或在 idempotency record 中追加 `active_cancel_event_ids` 字段），replay 时遍历所有 active cancel event id 重新传播。或者在 replay 路径直接扫描 Session 下所有 `CANCELLING` + `Attempt RUNNING` 的 Run，不依赖 idempotency record 的 event id。

---

### F2 [Low] EngineEventIngestor 的 wakeup_port 默认为 NoopAdmissionWakeupPort

**Location**: `dispatch.py:795-826` (`_consume_worker_events`)

**Description**: `_consume_worker_events` 创建 `EngineEventIngestor(transaction_runner=self._transaction_runner)` 时未传 `wakeup_port`，因此 ingestor 使用 `NoopAdmissionWakeupPort`。当 `run_cancelled` 或 `final_answer` 事件触发 terminal closeout 后，`_with_terminal_promotion_retry` 调用 `wakeup_port.wake_queue_promotion(session_id)` 为 no-op，不触发 queue promotion。

**Evidence**:
```python
# dispatch.py:806 — 无 wakeup_port 参数
ingestor = EngineEventIngestor(transaction_runner=self._transaction_runner)
```

```python
# engine_ingest.py:232-234 — 默认 NoopAdmissionWakeupPort
self._wakeup_port = (
    wakeup_port if wakeup_port is not None else NoopAdmissionWakeupPort()
)
```

**Impact**: 通过 Engine event stream 终结的 Run（`run_cancelled`、`final_answer`、`run_failed`）不会在 dispatch scheduler 内部触发 queue promotion。当前实现中 promotion 由上层（`closeout_attempt_terminal` callers）负责，但设计意图是 `_consume_worker_events` 内的 terminal closeout 应触发 promotion。

**Assessment**: 当前测试覆盖了 Run 终态迁移（`test_cancel_run_active_worker_propagates_and_closes_cancelled`），但未测试 terminal 后的 queue promotion。此 gap 不影响正确性但影响完整性，标记为 low。

**Recommended fix**: 让 scheduler 将 `wakeup_port` 传入 `EngineEventIngestor`，或在 `_consume_worker_events` 的 finally 块中主动触发 `wake_queue_promotion`。

---

### F3 [Low] `_is_worker_acceptable` 对 dispatch record 的 cancelled_event_id 做了隐式宽松检查

**Location**: `dispatch.py:861-892` (`_is_worker_acceptable`)

**Description**: `_is_worker_acceptable` 检查 `dispatch_record.cancelled_event_id is None`，但这与 `_dispatch_record_still_pre_accept` 重复——`_start_worker` 在调用 `_accept_worker_running` 前已经通过 `_dispatch_record_still_pre_accept` 确认了 `cancelled_event_id is None`。两处检查相同条件但走不同代码路径（read vs run_read transaction），增加了认知负担。

**Evidence**:
```python
# dispatch.py:552-570 — _dispatch_record_still_pre_accept 已检查
def _dispatch_record_still_pre_accept(self, dispatch_record):
    def _operation(transaction):
        latest = read_dispatch_record_by_id(transaction, dispatch_record.dispatch_record_id)
        return (
            latest is not None
            and latest.status == DispatchRecordStatus.DISPATCHING
            and latest.worker_accept_event_id is None
            and latest.cancelled_event_id is None  # ← 同一条件
        )
    return self._transaction_runner.run_read(_operation)

# dispatch.py:888-892 — _is_worker_acceptable 再次检查
    and dispatch_record.cancelled_event_id is None  # ← 重复
```

**Assessment**: 这是防御性编程（CAS 后可能有新 cancel event 写入），逻辑正确但增加维护成本。Not a bug, just a note。

---

### F4 [Low] `admission.py` 和 `command.py` 各自定义了 `_dispatch_record_is_direct_cancelable` / `_is_direct_cancelable_dispatch_record`

**Location**: `admission.py:2081-2100` 和 `command.py:895-914`

**Description**: 两个文件各自定义了功能完全相同的函数（`_dispatch_record_is_direct_cancelable` / `_is_direct_cancelable_dispatch_record`），只是命名略有不同。

**Evidence**:
```python
# admission.py:2081
def _dispatch_record_is_direct_cancelable(dispatch_record: DispatchRecordRow) -> bool:
    if dispatch_record.status in (DispatchRecordStatus.PENDING, DispatchRecordStatus.WAITING_FOR_LANE):
        return True
    return (dispatch_record.status == DispatchRecordStatus.DISPATCHING
        and dispatch_record.worker_accepted_at is None
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.worker_accept_event_sequence is None)

# command.py:895 — 逻辑完全相同
def _is_direct_cancelable_dispatch_record(dispatch_record: DispatchRecordRow) -> bool:
    if dispatch_record.status in (DispatchRecordStatus.PENDING, DispatchRecordStatus.WAITING_FOR_LANE):
        return True
    return (dispatch_record.status == DispatchRecordStatus.DISPATCHING
        and dispatch_record.worker_accepted_at is None
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.worker_accept_event_sequence is None)
```

**Assessment**: 重复逻辑。应抽取到 `dayu.host.durable.state` 或 `dayu.host.api` 中作为公共 helper。但这是编码规范问题，不影响正确性。

---

### F5 [Info] terminal 先赢 race 的正确性确认

**Location**: `dispatch.py:778-826`, `engine_ingest.py:610-703`

**Description**: 当 `final_answer` 和 `cancel_run` 并发时，terminal closeout 和 active cancel closeout 共享同一个 `terminal_closeout_in_transaction`，使用 CAS（`StateMutationStatus.UPDATED` vs `INVALID_STATE`）实现 first-committer-wins。先到的 terminal fact 胜出，后到的被 `_late_rejection_reason` 或 `_duplicate_terminal_result` 拒绝。

**Verification**:
- `final_answer` 先到 → `terminal_closeout_in_transaction` 写入 `ATTEMPT_SUCCEEDED` + `RUN_SUCCEEDED` → 后到的 `cancel_run` 读到 `terminal_event_id is not None` → `request_active_attempt_cancel_in_transaction` 返回 `INVALID_STATE` → `_raise_for_cancel_transition_status` 抛出
- `run_cancelled` 先到 → `active_cancel_closeout_in_transaction` 写入 `ATTEMPT_CANCELLED` + `RUN_CANCELLED` → 后到的 `final_answer` 被 `_late_rejection_reason` 拒绝

**Assessment**: 正确。terminal race first-wins 设计符合 §22 Cancel 规范。

---

### F6 [Info] cancel path 不释放 lane token 的正确性确认

**Location**: `admission.py` (all cancel paths), `command.py:808-818`, `dispatch.py:188-204`

**Description**: 全量审查确认：
1. `admission.py` 的 `cancel_run` / `cancel_session_runs` 只做 durable state transition + post-commit active registry propagation，不触碰 lane token
2. `command.py` 的 `_propagate_active_cancel_targets` 只调用 `cancel_active_worker(target)` 设置 cancellation token 和 `handle.cancel()`
3. `dispatch.py` 的 `ActiveWorkerRegistry.cancel()` 只 `request_cancel` + `handle.cancel()`，不释放 token
4. lane token 释放只在 `_consume_worker_events` 的 finally 块中 `await token.release()`

**Assessment**: 正确。cancel path 不直接释放 lane token，release 由 worker finally 管理，符合设计规范。

---

### F7 [Info] active registry 身份约束正确性确认

**Location**: `dispatch.py:135-204`

**Description**: 
- Registry 以 `(attempt_id, execution_id)` 做 key，`run_id` 在 `cancel()` 中做 secondary check（`entry.run_id != message.run_id`）
- `register` 在 `_accept_worker_running` durable commit 后调用
- `unregister` 在 `_consume_worker_events` finally 中调用
- `cancel` 先拿 entry 再检查 `run_id`，mismatch 时返回 False 不误取消

**Assessment**: 正确。身份约束覆盖 terminal/finally，run_id mismatch 不会误取消。

---

### F8 [Info] 测试覆盖评估

**Coverage**:

| 行为 | 测试 | 评价 |
|------|------|------|
| waiting_for_lane direct cancel | `test_cancel_run_waiting_for_lane_skips_later_dispatch` | ✓ 完整 |
| pre-accept dispatching direct cancel | `test_cancel_run_dispatching_pre_accept_stays_cancelled` | ✓ 完整 |
| active RUNNING → CANCELLING | `test_cancel_run_active_worker_propagates_and_closes_cancelled` | ✓ 含 worker event stream |
| terminal 先赢 race | `test_late_cancel_does_not_overwrite_terminal` | ✓ final_answer 先到 |
| session cancel replay 不追加 facts | `test_cancel_session_replay_repropagates_active_without_new_facts` | ✓ 但只覆盖单 active target |
| idempotent replay 不取消新 Run | `test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run` | ✓ 完整 |
| WAITING 无 partial mutation | `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` | ✓ 完整 |
| queued + active worker session cancel | `test_cancel_session_runs_cancels_queued_and_active_worker` | ✓ 新增 |
| active replay 不重复追加 facts | `test_cancel_session_runs_active_replay_does_not_append_facts` | ✓ 新增 |
| 无 supported Run 幂等 | `test_cancel_session_runs_no_supported_run_records_idempotency_without_event` | ✓ 完整 |
| CANCELLING 重复 cancel 不重复 RUN_CANCELLING | 隐含在 replay 测试中 | ✓ |

**Gaps**:
- 多 active target session cancel（F1 gap，无测试）
- terminal closeout 后 queue promotion 触发（F2 gap，无测试）
- CANCELLING 状态下 per-run `cancel_run` idempotent replay 返回 active cancel target 的测试

**Assessment**: 测试覆盖核心行为路径，无脆弱 DB 直改导致 false confidence。`_mark_attempt_running` 和 `_mark_run_status` 是状态模拟 helper，直改 DB 后的行为测试仅验证 "cancel path 在该状态下如何反应"，不依赖直改的 invariant。

---

## Required Fixes

1. **F1 [Medium]**: session cancel 幂等 replay 应覆盖全部 active CANCELLING target，不应只重放首个。建议在 replay 路径直接扫描 Session 下所有 `CANCELLING` + `Attempt RUNNING` 的 Run，或扩展 idempotency record 存储全部 active cancel event id。

## Residual Risks

1. **Active cancel watchdog 未实现**: 若 worker 收到 cancel 后长期不产出 terminal，Run 会停留在 `CANCELLING`。按计划留给后续 owner。
2. **`HostCommandHandleOptions.local_execution` 完整 command-handle 自动启动 dispatch scheduler 不在本 slice 范围**: 本实现通过进程内 default active registry 连接已运行 scheduler 与 public cancel facade。
3. **Terminal closeout 后 queue promotion 不在 dispatch scheduler 内部触发**: 需上层或 scheduler 自行处理。
4. **多 active target 场景的 replay gap** (F1): 当前架构下罕见但理论上存在 silent no-cancel 风险。

---

## Verdict

**Accept with one medium finding (F1).**

P5-S5 实现整体正确，cancel path 的 lane token 释放隔离、active registry 身份约束、terminal first-wins race、幂等 replay 不追加 facts、session cancel 全量分类无 partial mutation 等核心设计均已验证通过。代码质量良好，测试覆盖关键路径。

唯一 blocking 级别的发现是 F1（session cancel replay 只重放首个 active target），但由于多 concurrent active worker 是当前架构约束下的罕见场景，且有 worker timeout watchdog 作为兜底，标记为 medium 而非 blocking。建议在后续 hardening 中修复。
