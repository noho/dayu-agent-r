# Gateflow Re-Review: Host P5-S5 Active Cancel And Session-scope Cancel (AgentMiMo)

## Re-Review Metadata

- **Reviewer**: AgentMiMo
- **Date**: 2026-05-15
- **Scope**: Fix artifact `docs/reviews/gateflow-fix-host-p5-s5-active-cancel-session-scope-20260515.md` 对应的当前 workspace 变更
- **Source Reviews**:
  - MiMo 初审: `gateflow-code-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md`
  - DS 初审: `gateflow-code-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`
- **Fix Agent**: AgentCodex

---

## 复核结论

**PASS — 无 blocking findings。**

5 项复核重点逐项结论：

| # | 复核项 | 结论 |
|---|--------|------|
| 1 | `HostDispatchScheduler` 作为 `wakeup_port` 传入 `EngineEventIngestor` 后 terminal closeout → promotion → dispatch 闭环 | PASS |
| 2 | 测试 active worker 前置不再依赖非法裸 SQL 状态组合；WAITING 直改注释充分 | PASS |
| 3 | Phase 4 stale 文本已修正 | PASS |
| 4 | 无新增 import boundary / 分层 / lane token / active registry / idempotency 风险 | PASS |
| 5 | residual risks 可接受；多 active replay 限制在单 active invariant 下非 blocking | PASS |

---

## 逐项复核详情

### 1. HostDispatchScheduler wakeup_port → terminal closeout → promotion 闭环

**Fix 内容**:

- `dispatch.py:384-397`: `HostDispatchScheduler` 新增 `wake_queue_promotion(session_id)` 方法，内部创建 `HostAdmissionService(wakeup_port=self)` 并调用 `promote_next_queued_run(session_id)`。
- `dispatch.py:821-824`: `_consume_worker_events` 创建 `EngineEventIngestor(wakeup_port=self)`，不再落到 `NoopAdmissionWakeupPort`。

**调用链验证**:

```
worker event stream (final_answer / run_cancelled)
  → ingestor.ingest(candidate)
    → _ingest_validated → terminal_closeout / active_cancel_closeout
    → result.terminal_closeout = True
  → _with_terminal_promotion_retry(result, session_id=...)
    → wakeup_port.wake_queue_promotion(session_id)   # scheduler 自身
      → create_host_admission_service(wakeup_port=self)
        .promote_next_queued_run(session_id)
      → _wake_dispatch_if_needed(port, pending_dispatch, suppress=True)
        → port.wake_dispatch(record)
          → self._queue.put_nowait(record)  # scheduler 队列
```

**递归风险**: 无。`wake_queue_promotion` → `promote_next_queued_run` → `_wake_dispatch_if_needed` → `wake_dispatch` 只是 `put_nowait`，不调用 `wake_queue_promotion`。无环。

**Event loop 阻塞**: `wake_queue_promotion` 是同步方法，在 async `_consume_worker_events` 内同步执行一次 SQLite write transaction。这与 `_dispatch_one` / `_accept_worker_running` 等现有路径一致（均为同步 `run_write` 在 async 上下文中调用）。SQLite 单次 promotion 事务延迟微秒级，对 event loop 的阻塞可接受。

**Closed scheduler 竞态**: `wake_queue_promotion` 入口检查 `self._closed`；若在 check 与 `promote_next_queued_run` 之间 scheduler 关闭，promotion 内部 `_wake_dispatch_if_needed(suppress_runtime_error=True)` 会吞掉 `wake_dispatch` 的 `RuntimeError`。即使 promotion 成功但 dispatch 未处理，新 worker 的 lane acquire 也会因 `LaneController.close()` 而失败，dispatch 被跳过。非理想但安全。

**Transaction 边界**: `wake_queue_promotion` 创建独立的 `HostAdmissionService` 使用 `self._transaction_runner`，每次 `run_write` 独立获取连接，不嵌套外层 `_consume_worker_events` 的 ingestor 事务（ingestor 事务已在 `ingest()` 内部提交完毕后才到 `_with_terminal_promotion_retry`）。无嵌套事务问题。

**完整性**: MiMo 初审 F2 指出的 "terminal closeout 后 queue promotion 不在 dispatch scheduler 内部触发" 问题已完全解决。新测试 `test_worker_terminal_promotes_and_dispatches_queued_run` 覆盖了完整路径：active worker `final_answer` → terminal closeout → promotion → queued Run dispatched → 第二个 worker accept → 第二个 `ATTEMPT_RUNNING` fact。断言 `worker_factory.created == 2` 和 `_event_type_count("ATTEMPT_RUNNING") == 2` 确认 promotion 不是 noop。

---

### 2. 测试 active worker 前置构造方式

**Fix 内容** (`tests/host/test_public_cancel_session_runs.py`):

- 删除旧的 `_mark_attempt_running` 裸 SQL helper（`UPDATE host_attempts SET status = 'running'`）。
- 新增 `_accept_active_worker(transaction_runner, run_id, attempt_id)` (line 253-308)，在 durable write transaction 内：
  1. `register_current_instance` — 注册 FK 诊断 row
  2. `mark_dispatch_waiting_for_lane_row` — PENDING → WAITING_FOR_LANE
  3. `mark_dispatching_after_lane_row` — WAITING_FOR_LANE → DISPATCHING
  4. `accept_worker_running_in_transaction` — 追加 `ATTEMPT_RUNNING` fact + `mark_attempt_running_row` + `mark_dispatch_worker_accepted_row`

**验证**: 此路径通过生产代码的 `accept_worker_running_in_transaction`（`dayu/host/durable/run_transition.py`），完整覆盖：
- CAS 校验（attempt 仍 STARTING，dispatch 仍 DISPATCHING）
- `ATTEMPT_RUNNING` canonical fact 写入 EventLog
- dispatch worker accepted refs 持久化
- host instance FK 约束

不再依赖裸 SQL 绕过 CAS 或 EventLog。

**WAITING 直改**: `_mark_run_status` (line 311-324) 仍用裸 SQL 直改 Run status 为 `WAITING`，注释 (line 395-397) 明确说明：

> "这里仅构造 WAITING 分类测试所需的 deferred 状态，不模拟生产 transition；该用例只验证 unsupported 分类不会产生 partial mutation。"

`WAITING` 是后续 Phase 7 的 deferred 状态，当前无生产 transition helper 可达此状态，裸 SQL 直改作为 deferred classification 测试占位合理，注释充分。

---

### 3. Phase 4 stale 文本修正

**Fix 内容** (`admission.py:1339-1347`):

`_read_supported_targets_or_raise` 的 error message 从：
```
"cancel_session_runs supports only queued and pre-dispatch STARTING Runs in Phase 4"
```
改为：
```
"cancel_session_runs supports only queued, pre-dispatch STARTING, and active worker Runs in the current Host cancel scope"
```

**验证**: 当前 workspace 中 `admission.py` 已无 "Phase 4" 文本（grep 确认）。"current Host cancel scope" 表述 phase-neutral，随实现范围自动正确。

**command.py 残留 "Phase 4"**: `command.py` 中仍有 "Phase 4" 引用（docstring 和 stable rejection message），这些是 retry/replay/resolve_wait/purge_session 等未实现功能的 stable rejection，与本次 fix 范围无关，不属于 stale 文本问题。

---

### 4. 新增风险扫描

#### 4a. Import boundary

`dispatch.py` 新增 import: `from dayu.host.admission import PendingDispatchRecord, create_host_admission_service`

方向：`dispatch → admission`。按分层 `UI → Service → Host → Engine`，`dispatch` 和 `admission` 同属 Host 层内部模块，同层横向依赖允许。`admission` 不 import `dispatch`，无循环。`wake_queue_promotion` 内部创建临时 service 实例，不持有持久引用。

**结论**: 无 import boundary 风险。

#### 4b. 分层

`HostDispatchScheduler` 实现 `AdmissionWakeupPort` 协议的 `wake_dispatch` 和 `wake_queue_promotion`，通过协议耦合而非具体实现耦合。`admission.py` 中 `AdmissionWakeupPort` 是 Protocol class，`dispatch.py` 实现该协议。符合面向接口设计。

**结论**: 无分层风险。

#### 4c. Lane token release

Lane token 释放仍在 `_consume_worker_events` finally 块中 (line 844: `await token.release()`)。`cancel` path 不释放 token。`wake_queue_promotion` 不触碰 lane token。新 dispatch 路径的 lane acquire 在 `_dispatch_one` 内管理。

**结论**: 无 lane token release 风险。

#### 4d. Active registry

注册/注销/取消逻辑未变更。`_accept_active_worker` 测试 helper 使用 `accept_worker_running_in_transaction` 后不注册 active handle（这是正确的——测试 helper 只构造 durable state，不启动真实 worker）。active handle 注册只发生在 `_start_worker` (line 633-639)。

**结论**: 无 active registry 风险。

#### 4e. Idempotency

`wake_queue_promotion` 不写 idempotency record，它只调用 `promote_next_queued_run`，后者有自己的幂等语义（检查 active run 是否存在）。多次 `wake_queue_promotion` 对同一 session 的幂等安全性由 `promote_queued_run_in_transaction` 的 CAS 保证（active run 存在时 skip）。

**结论**: 无 idempotency 风险。

---

### 5. Residual Risks 评估

| Risk | 评估 |
|------|------|
| **多 active replay 限制** | 当前架构约束下单 active invariant；replay 只重放首个 active target 属已知设计限制。首次 cancel 正确传播全部 target（测试 `test_cancel_session_runs_cancels_queued_and_active_worker` 覆盖）。replay 漏传播只在首次 cancel commit 后 worker 未响应且 replay 被触发时发生——窗口极小且有 worker timeout watchdog 兜底。**非 blocking。** |
| **Active cancel watchdog 未实现** | worker 收到 cancel 后长期不产出 terminal 会导致 Run 停留 CANCELLING。按计划留给后续 owner，当前 phase 不阻塞。**非 blocking。** |
| **cancel_run 幂等重放不重传播** (DS Finding 3) | 与 session cancel replay 的不对称性是显式设计决定。崩溃窗口极小（commit 后立刻 propagate，中间无 yield 点）。**非 blocking。** |
| **`_is_worker_acceptable` 与 `_dispatch_record_still_pre_accept` 重复检查** (MiMo F3) | 防御性编程，逻辑正确但增加维护成本。**Observation，非 blocking。** |
| **`_dispatch_record_is_direct_cancelable` / `_is_direct_cancelable_dispatch_record` 重复定义** (MiMo F4) | 编码规范问题，不影响正确性。**Observation，非 blocking。** |
| **command.py 中 "Phase 4" 文本残留** | 均为 stable rejection message 和历史 docstring，与本次 fix 无关。**Cosmetic，非 blocking。** |

---

## Residual Risks（承前）

1. 多 active target session cancel replay 限制：当前单 active invariant 下不作为 blocking，后续扩展多 active 语义时应重新设计 replay target truth。
2. Active cancel watchdog 仍属于后续 phase 风险。
3. `cancel_run` 幂等重放不重传播 active cancel target（与 session cancel 不对称），崩溃窗口极小。
4. 本轮未扩大 schema，未引入兼容性迁移。

---

## Verdict

**PASS。**

Fix artifact 中列出的 3 项 accepted findings 均已在当前 workspace 中正确解决：

1. **DS Finding 1** (裸 SQL active worker): 已替换为 `_accept_active_worker` → `accept_worker_running_in_transaction`，完整覆盖 CAS + EventLog + dispatch worker accepted 联动。
2. **MiMo F2 / DS Finding 6.1 follow-up** (wakeup_port noop): `HostDispatchScheduler` 实现 `wake_queue_promotion` 并作为 `wakeup_port` 传入 `EngineEventIngestor`，terminal closeout 后 promotion → dispatch 闭环完整，新增测试 `test_worker_terminal_promotes_and_dispatches_queued_run` 覆盖。
3. **Phase 4 stale 文本**: error message 已修正为 phase-neutral "current Host cancel scope" 表述。

无新增 import boundary、分层、lane token release、active registry 或 idempotency 风险。当前 residual risks 在单 active invariant 下均可接受。
