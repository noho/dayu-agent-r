# Gateflow Code Re-Review Artifact: Host P5-S5 Active Cancel And Session-scope Cancel (AgentDS)

## Re-Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-05-15
- **Scope**: P5-S5 fix workspace re-review（不修改生产代码）
- **Input Artifacts**:
  - Implementation: `docs/reviews/gateflow-implementation-host-p5-s5-active-cancel-session-scope-20260515.md`
  - MiMo 初审: `docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md`
  - DS 初审: `docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`
  - Fix artifact: `docs/reviews/gateflow-fix-host-p5-s5-active-cancel-session-scope-20260515.md`
- **Reviewed Files**: `dayu/host/dispatch.py`, `dayu/host/admission.py`, `dayu/host/command.py`, `dayu/host/README.md`, `tests/README.md`, `tests/host/test_active_cancel_dispatch.py`, `tests/host/test_public_cancel_session_runs.py`

---

## 复核要点 1: HostDispatchScheduler 作为 wakeup_port 传入 EngineEventIngestor

### 调用链追踪

```
_consume_worker_events (dispatch.py:793-844)
  → EngineEventIngestor(transaction_runner=..., wakeup_port=self)  # line 821-824
  → ingestor.ingest(candidate)
    → _with_terminal_promotion_retry(result, session_id=...)       # engine_ingest.py:253-268
      → self._wakeup_port.wake_queue_promotion(session_id)
        → HostDispatchScheduler.wake_queue_promotion (dispatch.py:384-397)
          → create_host_admission_service(..., wakeup_port=self)
          → .promote_next_queued_run(session_id)
            → run_write(_PromoteNextQueuedRunOperation)            # 独立 write transaction
            → _wake_dispatch_if_needed(wakeup_port, ..., suppress_runtime_error=True)
              → scheduler.wake_dispatch(record)                    # dispatch.py:370-382
                → queue.put_nowait(record)
                → asyncio.create_task(_drain_loop())               # 异步 drain
```

### Recursion 分析

**结论: 无 recursion。** 每一步都是同步返回后才进入下一步。`wake_dispatch` 放入队列后立即返回；`_drain_loop` 在独立 asyncio task 中运行。`wake_queue_promotion` 内部的 `promote_next_queued_run` 运行独立的 write transaction，与外层 `ingest()` 的 transaction 完全隔离。

### Event loop 分析

**结论: 无新增 event loop 阻塞风险。** `promote_next_queued_run` 内的 `run_write` 是同步调用，与代码库中其他 transaction runner 使用模式一致。promotion transaction 轻量（单行 scan + CAS update），不会造成显著的 event loop 阻塞。

### Closed scheduler 分析

**结论: 已正确处理。** `wake_queue_promotion` (line 392-393) 和 `wake_dispatch` (line 378-379) 均有 `self._closed` 前置检查。`promote_next_queued_run` 调用 `_wake_dispatch_if_needed(..., suppress_runtime_error=True)`，即使 scheduler 在 promotion transaction 期间被关闭，`RuntimeError` 也会被静默吞掉，不会污染 promotion 结果。

### Transaction 边界

**结论: 正确隔离。** `wake_queue_promotion` 通过 `create_host_admission_service` 创建独立 admission service，promotion 在独立 write transaction 中执行，与 EngineEventIngestor 的内部 transaction 无共享状态。

### 校验

`test_worker_terminal_promotes_and_dispatches_queued_run` (test_active_cancel_dispatch.py:415-466) 覆盖了完整链路：active worker terminal (final_answer) → scheduler promotion → queued Run 被 promote → 新 dispatch 被同一 scheduler 处理。断言 `worker_factory.created == 2` 和 `ATTEMPT_RUNNING` count == 2，证明 wakeup port 不是 noop。

**Verdict: PASS**

---

## 复核要点 2: test_public_cancel_session_runs.py active worker 前置

### _accept_active_worker (lines 253-308)

替代了原裸 SQL `UPDATE host_attempts SET status = 'running'`。新实现：

1. `register_current_instance` — 注册 host instance FK 行
2. `mark_dispatch_waiting_for_lane_row` — PENDING → WAITING_FOR_LANE（CAS 校验）
3. `mark_dispatching_after_lane_row` — WAITING_FOR_LANE → DISPATCHING（CAS 校验）
4. `accept_worker_running_in_transaction` — 追加 `ATTEMPT_RUNNING` EventLog fact，推进 Attempt STARTING → RUNNING，记录 dispatch worker accepted refs
5. 所有操作在同一 write transaction 内，每步 assert `StateMutationStatus.UPDATED`

该 helper 经过 durable transition primitive 的 CAS 校验，且追加了完整的 EventLog fact。覆盖了 DS Finding 1 的核心诉求。

### _mark_run_status (lines 311-324)

保留裸 SQL，但仅在 `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 中使用，且有充分中文注释：

```python
# 这里仅构造 WAITING 分类测试所需的 deferred 状态，不模拟生产
# transition；该用例只验证 unsupported 分类不会产生 partial mutation。
_mark_run_status(options.db_path, active.run_id, RunStatus.WAITING)
```

WAITING 状态在当前 Phase 5 没有生产 transition path，裸 SQL 是唯一可行的状态构造方式。注释清晰说明了 bypass 的范围和目的。

### 受影响测试

| 测试 | 原前置方式 | 现前置方式 | 评价 |
|------|-----------|-----------|------|
| `test_cancel_session_runs_cancels_queued_and_active_worker` | 裸 SQL UPDATE host_attempts | `_accept_active_worker` (完整 durable transition) | FIXED |
| `test_cancel_session_runs_active_replay_does_not_append_facts` | 裸 SQL UPDATE host_attempts | `_accept_active_worker` (完整 durable transition) | FIXED |
| `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` | 裸 SQL UPDATE host_runs | 裸 SQL UPDATE host_runs + 注释 | ACCEPTABLE |

**Verdict: PASS**

---

## 复核要点 3: Phase 4 stale 文本

### admission.py

- `_read_supported_targets_or_raise` (line 1340-1346): `"Phase 4"` → `"current Host cancel scope"` — **FIXED**
- 其他 error message (`_raise_for_cancel_transition_status`, `_raise_for_session_cancel_transition_status`) 使用 "Phase 5"，正确反映当前 phase。

### command.py

- `cancel_run` docstring: `"Phase 4 只覆盖 queued 与 pre-dispatch STARTING"` → `"当前覆盖 queued、pre-dispatch STARTING、pre-accept dispatching 与 active worker"` — **FIXED**
- `cancel_session_runs` docstring: `"Phase 4 只覆盖..."` → `"当前覆盖 queued、pre-dispatch STARTING、pre-accept dispatching 与 active worker"` — **FIXED**
- `_is_predispatch_starting_run` docstring: `"Phase 4 可直接取消"` → `"可直接取消"` — **FIXED**
- `_is_deferred_cancel_state`: 移除了 `CANCELLING` 从 deferred 列表（CANCELLING 现在由 active worker cancel 支持），增加了 `_is_active_worker_cancelable_run` 检查 — **FIXED**

### README

- `dayu/host/README.md`: 清理了 Phase 4 cancel 描述，更新为当前能力范围（queued + pre-dispatch/pre-accept dispatching + active worker）；补充了 scheduler 作为 wakeup port 的说明；移除了 `queue scanning / after-commit wakeup`、`dispatch scheduler 到 EngineEventIngestor 的 worker stream 端到端接线`、`active cancel propagation` 等已实现能力的"未实现"列表项 — **FIXED**
- `tests/README.md`: `cancel_session_runs` 覆盖描述从 `queued / pre-dispatch STARTING 子集` 更新为 `queued / pre-dispatch STARTING / active worker 子集` — **FIXED**

**Verdict: PASS**

---

## 复核要点 4: import boundary / 分层 / lane token release / active registry / idempotency 新增风险

### Import boundary

`dispatch.py` 中 `wake_queue_promotion` 使用的 `create_host_admission_service` 在 fix 前已 import (line 21)。`command.py` 新增 `from dayu.host.dispatch import ActiveCancelMessage, cancel_active_worker` (line 80)，这是 Host → Host 的合法依赖。无新增跨层 import。

### 分层

`HostDispatchScheduler.wake_queue_promotion` 调用 `create_host_admission_service` → `promote_next_queued_run`，均在 `dayu.host` 层内部。无 UI、Service、Engine 层反向依赖。

### Lane token release

未修改。Lane token 仍在 `_consume_worker_events` finally 块中释放 (dispatch.py:844)。`wake_queue_promotion` → `promote_next_queued_run` → `wake_dispatch` → dispatch 新 worker 会获取新的 lane token，与释放的 token 无关。

### Active registry

未修改。`cancel_active_worker` 仍通过 `DEFAULT_ACTIVE_WORKER_REGISTRY.cancel(message)` 传播。`wake_queue_promotion` 不涉及 registry 操作。

### Idempotency

未修改。`promote_next_queued_run` 没有 idempotency 机制（promotion 是内部操作，非用户可见）。session cancel / run cancel 的幂等 replay 逻辑未变。

### 潜在新风险: wake_queue_promotion 异常传播

`_with_terminal_promotion_retry` 调用 `wakeup_port.wake_queue_promotion(session_id)` 时未 catch 异常。如果 `promote_next_queued_run` 抛出（例如 DB 错误），异常会传播到 `ingest()` → `_consume_worker_events` async for loop。Worker finally 块仍会执行清理（unregister、close handle、release lane token），但 asyncio task 会以未处理异常结束。

**评估**: 这是让 noop wakeup port 变为功能端口的固有风险增量。`promote_next_queued_run` 本身对常见错误（session 缺失、promotion skip）有防御，真正的 DB 层错误在任何 transaction 路径上都可能发生。当前风险可接受，但建议在未来 phase 中考虑在 `_with_terminal_promotion_retry` 内加 try/except 并 log diagnostic，避免单个 promotion 失败拖垮整个 worker event consumption task。

**Verdict: PASS（含一条 observation）**

---

## 复核要点 5: residual risks 可接受性

### 5.1 多 active replay 限制 (MiMo F1 / DS Finding 2)

**未修复，按 controller 裁决接受。** 当前同 Session 单 active worker 的 FIFO promotion 约束下，多 active 并发是罕见竞争窗口。首次 `cancel_session_runs` 正确传播全部 active target；仅幂等 replay 只重传播首个 target。Replay 本身是 best-effort（worker 可能已终止），且 active cancel watchdog（后续 phase）会兜底超时未终止的 CANCELLING worker。

**评估: 非 blocking。**

### 5.2 Active cancel watchdog 未实现

**已知 residual risk。** Worker 收到 cancel 后若长期不产出 terminal，Run 停留在 CANCELLING。按计划留给后续 owner。

**评估: 非 blocking。**

### 5.3 cancel_run 幂等重放不重传播 (DS Finding 3)

**已知 design decision。** `_idempotent_cancel_result` 的 `active_cancel_target=None` 是有意的——`cancel_run` 是单 Run 操作，重放只确认状态。崩溃窗口（commit 后 → propagate 前）极小。

**评估: 非 blocking。**

### 5.4 wake_queue_promotion 异常传播风险

**新识别的 risk（见复核要点 4 的 observation）。** 严重程度低——worker finally 仍执行清理，DB 层错误在任何路径上都可能发生。

**评估: 非 blocking，建议后续 phase 加 try/except + diagnostic log。**

### 5.5 测试覆盖

新增 `test_worker_terminal_promotes_and_dispatches_queued_run` 覆盖了 terminal → promotion → dispatch 完整链路，弥补了 MiMo F2 的覆盖 gap。22 tests passed, 0 pyright errors.

**评估: 覆盖充分。**

---

## Verdict

**PASS**

5 项复核要点全部通过，无 blocking finding。

| # | 复核要点 | 结论 |
|---|---------|------|
| 1 | HostDispatchScheduler 作为 wakeup_port → terminal closeout → promote queued Run → wake promoted dispatch | PASS |
| 2 | test_public_cancel_session_runs.py active worker 前置不再依赖裸 SQL；WAITING 直改有充分注释 | PASS |
| 3 | Phase 4 stale 文本已修正（admission.py, command.py, README） | PASS |
| 4 | 无新增 import boundary / 分层 / lane token / active registry / idempotency 风险 | PASS（含 1 条 observation） |
| 5 | Residual risks 可接受；多 active replay 限制在单 active invariant 下非 blocking | PASS |

### Observations (non-blocking)

1. **`_with_terminal_promotion_retry` 未 catch `wake_queue_promotion` 异常**: promotion 失败会传播到 worker event consumption task，虽然 finally 清理不受影响，但建议后续 phase 加 try/except + diagnostic log。
2. **`_is_direct_cancelable_dispatch_record` 重复定义**: `admission.py:2082-2101` 和 `command.py:895-914` 各自定义了功能相同的函数。MiMo F4 已标记，fix 未处理（非本轮 scope）。不影响正确性。

### Fix Verification Summary

| DS/MiMo Finding | 状态 |
|-----------------|------|
| DS F1 (裸 SQL 测试) | FIXED — `_accept_active_worker` 使用完整 durable transition |
| MiMo F2 / DS 6.1 (wakeup_port) | FIXED — scheduler 实现 `wake_queue_promotion`，传入 `wakeup_port=self` |
| DS F8 (Phase 4 文本) | FIXED — error message 更新为 phase-neutral |
| MiMo F1 / DS F2 (多 active replay) | ACCEPTED — controller 裁决非 blocking |
| DS F3 (cancel_run 重放不对称) | ACCEPTED — design decision |
| MiMo F4 (重复 helper) | DEFERRED — 非本轮 scope |
