# Host Phase 5 P5-S3 Dispatch Scheduler, Lane And LocalProxy 代码审查报告

- **审查对象**: Host Phase 5 P5-S3 未提交实现 diff
- **审查分支**: `feat/host-phase5-local-dispatch`
- **审查日期**: 2026-05-15
- **审查角色**: 独立代码审查员 (review only, no production changes)
- **设计真源**: `docs/host/design.md` §17 / `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S3/§3.4/§3.5/§4

## 审查范围

已审查文件:

| 文件 | 状态 | 说明 |
|---|---|---|
| `dayu/host/dispatch.py` | 新增 | HostDispatchScheduler + DispatchDrainResult |
| `dayu/host/local_proxy.py` | 新增 | DefaultLocalEngineWorker/Factory + DefaultLocalWorkerHandle |
| `dayu/host/api.py` | 修改 | 新增 4 个 typed contracts + HostCommandHandleOptions.local_execution |
| `dayu/host/__init__.py` | 修改 | 导出新增类型 |
| `tests/host/test_dispatch_scheduler.py` | 新增 | 4 个 scheduler 测试 + 辅助工具 |
| `tests/host/test_local_proxy_engine_ingest.py` | 新增 | 1 个 LocalProxy Engine 边界测试 |
| `tests/host/test_command_handle.py` | 修改 | import-boundary 允许 Host → Engine 依赖 |

未改动文件确认:
- `dayu/host/command.py` — P5-S3 未触碰 ✓
- `dayu/host/admission.py` — P5-S3 未触碰 ✓
- `dayu/host/durable/run_transition.py` — P5-S3 未触碰 ✓
- `dayu/engine/` — 全部未改动 ✓

## 结论摘要

**未发现阻塞性 (blocking) 问题。接受此 slice。**

发现 2 个 Low 建议项，均为非阻塞性。

---

## 逐项审查

### 1. HostDispatchScheduler 生命周期 — dispatch.py

**设计要求** (plan §3.3 / §4.1): pending → waiting_for_lane → lane acquire → durable recheck → dispatching → worker accept → ATTEMPT_RUNNING。

**实现** (`_dispatch_one`, dispatch.py:295-325):

```
_mark_waiting_for_lane()           # PENDING → WAITING_FOR_LANE CAS
  → _lane_controller.acquire()     # runtime lane
  → LaneAcquireTimedOut → FAILED closeout
  → LaneAcquireCancelled → skip
  → _mark_dispatching_after_recheck()  # durable recheck + WAITING_FOR_LANE → DISPATCHING CAS
  → CAS loser → release lane, skip
  → asyncio.sleep(0) yield
  → _dispatch_record_still_pre_accept()  # pre-call cancel race check
  → cancel detected → release lane, skip
  → _start_worker() → build request → worker.accept() → accept commit
```

**审查结果**: 正确。

- `_mark_waiting_for_lane()` (line 327-355): 先读 latest row，若已在 WAITING_FOR_LANE 则复用（幂等）；否则 CAS PENDING → WAITING_FOR_LANE ✓
- `_mark_dispatching_after_recheck()` (line 357-394): lane acquired 后在 short transaction 内 re-read Run/Attempt/dispatch，通过 `_is_dispatchable_recheck` 全面校验 11 个条件，再 CAS WAITING_FOR_LANE → DISPATCHING ✓
- `_dispatch_record_still_pre_accept()` (line 396-416): `asyncio.sleep(0)` 后的独立 read transaction，检查 `status=DISPATCHING` + `worker_accept_event_id IS NULL` + `cancelled_event_id IS NULL` ✓
- 不存在 `pending → dispatching` 生产路径直达 ✓

### 2. Durable Recheck — `_is_dispatchable_recheck` 与 `_is_worker_acceptable`

**`_is_dispatchable_recheck`** (dispatch.py:627-656) 检查 11 个条件:
1. Run 存在且 `status == RUNNING` ✓
2. `run.current_attempt_id == record.attempt_id`（Run 仍指向当前 Attempt）✓
3. Attempt 存在且 `status == STARTING` ✓
4. `attempt.execution_id == record.execution_id` ✓
5. Dispatch record 存在且 `status == WAITING_FOR_LANE` ✓
6. `dispatch_record.execution_id == record.execution_id` ✓
7. `worker_accept_event_id IS NULL`（未被其他 worker 抢先 accepted）✓
8. `cancelled_event_id IS NULL`（未被 cancel 抢先）✓

**`_is_worker_acceptable`** (dispatch.py:659-690) 在 worker accept transaction 内重新检查:
- Run RUNNING + current_attempt_id 匹配 ✓
- Attempt STARTING + execution_id 匹配 ✓
- Dispatch DISPATCHING + worker_accept_event_id IS NULL + cancelled_event_id IS NULL ✓

**审查结果**: 正确。两阶段 recheck 覆盖了 lane-acquire 后和 worker-call 后两个 race window。CAS loser 均 release lane 且不调用 worker。

### 3. Lane Acquire / Release / Finally

**Lane release 触发点**:

| 位置 | 触发条件 | 释放 |
|---|---|---|
| `_dispatch_one:319` | CAS WAITING_FOR_LANE → DISPATCHING 失败 | `await token.release()` |
| `_dispatch_one:323` | pre-call cancel race 检测到 cancelled | `await token.release()` |
| `_start_worker:450` | worker accept timeout (asyncio.wait_for TimeoutError) | `await token.release()` |
| `_start_worker:459` | accept commit CAS 失败 | `await token.release()` |
| `_consume_worker_events:624` | EngineEvent stream 结束（finally） | `await token.release()` |

**审查结果**: 正确。

- LaneAcquireTimedOut (line 309-311): 未获得 lane token，不存在释放。直接调用 FAILED closeout ✓
- LaneAcquireCancelled (line 312-313): 跳过，不做 FAILED closeout，不释放任何 lane（没有持有 token）✓
- 所有持有 token 的路径均在 finally 语义下释放 ✓
- Lane token release owner 是 scheduler / worker finally，cancel path 不直接释放 ✓

### 4. Pre-call Cancel Race

**设计要求** (plan §4.3): scheduler 已 commit dispatching 但 WorkerProxy 未 accepted → cancel_run wins → dispatch record → cancelled → scheduler recheck 看到 cancelled → release lane → skip worker。

**实现**:
1. `_mark_dispatching_after_recheck` 提交后，`asyncio.sleep(0)` 让出 event loop
2. cancel 可在此时段赢得 durable transaction
3. `_dispatch_record_still_pre_accept()` 在独立 read transaction 中检查 `cancelled_event_id IS NULL`
4. 若 cancel 已提交，返回 False → release lane, skip ✓
5. 即使 `_dispatch_record_still_pre_accept` 通过，`_accept_worker_running` 内的 `_is_worker_acceptable` 再次检查 `cancelled_event_id IS NULL`（双重防护）✓

**测试** (`test_cancelled_dispatch_is_skipped_before_worker_call`): 将 dispatch 推进到 dispatching 后 direct cancel，验证 scheduler 不创建 worker (`factory.created == 0`) 且 `result.skipped == 1` ✓

**审查结果**: 正确。双重防护（pre-call recheck + accept commit recheck）覆盖了 cancel race 的全部时间窗口。

### 5. Startup Timeout Closeout

**设计要求** (plan §3.3 / §3.6): lane acquire timeout 和 worker accept timeout 均关闭 Attempt FAILED / Run FAILED，reason=`worker_startup_timeout`。

**实现**:
- Lane acquire timeout: `_dispatch_one:309-311` → `_closeout_worker_startup_timeout(record)` → `terminal_closeout_in_transaction` with reason=`worker_startup_timeout` ✓
- Worker accept timeout: `_start_worker:448-451` → `_closeout_worker_startup_timeout(record)` → 同上 ✓
- `_closeout_worker_startup_timeout` (dispatch.py:575-606) 使用 P5-S1 已有的 `terminal_closeout_in_transaction` ✓

**测试覆盖**:
- `test_lane_acquire_timeout_closes_starting_attempt_failed`: 预占 lane capacity 导致 acquire timeout → Run/Attempt FAILED, reason=`worker_startup_timeout` ✓
- `test_worker_startup_timeout_closes_starting_attempt_failed`: slow worker → accept timeout → Run/Attempt FAILED, reason=`worker_startup_timeout` ✓

**审查结果**: 正确。两种 timeout 均正确关闭为 FAILED。

**备注**: plan §3.6 的 closeout 表将 "startup timeout" 作为一个统一场景，涵盖 lane acquire timeout 和 worker accept timeout 两种情况。两者在语义上均属于 "在 worker accepted 前超时"，使用同一 reason 符合 plan 定义。不构成 issue。

### 6. ATTEMPT_RUNNING Payload

**设计要求** (plan P5-S3): payload 包含 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id`。

**实现** (`_attempt_running_event_request`, dispatch.py:693-749):

```python
payload = {
    "attempt_id": attempt.attempt_id,
    "execution_id": attempt.execution_id,
    "dispatch_record_id": dispatch_record.dispatch_record_id,
    "worker_kind": _worker_kind_text(dispatch_record.worker_kind),
    "execution_target": dispatch_record.execution_target,
    "local_worker_id": local_worker_id,         # ✓
    "worker_accepted_at": accepted_at_text,     # ✓
    "lane_name": lane_name,                     # ✓
    "lane_claim_id": lane_claim_id,             # ✓
    "reason": _WORKER_ACCEPT_REASON,
}
```

**审查结果**: 正确。4 个 P5-S3 residual 字段全部包含 ✓。event_class=`CANONICAL_FACT` ✓。event_type=`ATTEMPT_RUNNING` ✓。

### 7. Attempt RUNNING 顺序

**设计要求**: Attempt RUNNING 只能在 durable ATTEMPT_RUNNING 之后。

**实现** (`_accept_worker_running`, dispatch.py:506-573):
1. 单次 write transaction 内:
2. `event_log_store.append_event(transaction, ATTEMPT_RUNNING_request)` → 获取 `event.event_id` 和 `event.event_sequence`
3. `mark_attempt_running_row(transaction, ...)` → CAS Attempt STARTING → RUNNING
4. `mark_dispatch_worker_accepted_row(transaction, worker_accept_event_id=event.event_id, ...)` → CAS dispatch worker accept refs

**审查结果**: 正确。ATTEMPT_RUNNING 事件先追加（获取 event_sequence），然后 Attempt 状态推进。三个操作在同一事务内原子完成 ✓。

### 8. Dispatch Record Status 语义

**设计要求** (plan §3.2): `dispatching` 在 WorkerProxy accept 后仍是 dispatch record 最终非取消状态。active worker truth 是 `ATTEMPT_RUNNING`。

**实现**:
- `mark_dispatch_worker_accepted_row` 写入 worker accept refs 后 dispatch record status 仍为 `DISPATCHING` ✓
- 不存在 `accepted` / `running` / `completed` dispatch record 状态 ✓
- dispatch record 不表达 active worker truth ✓

**审查结果**: 正确。

### 9. LocalProxy Default Worker — local_proxy.py

**设计要求** (plan P5-S3): default worker 使用 `dayu.engine.run_agent_messages(request)`。不做 EngineEvent ingest，不做 terminal closeout。

**实现**:

- `DefaultLocalEngineWorkerFactory.create_worker()`: 返回 `DefaultLocalEngineWorker` ✓
- `DefaultLocalEngineWorker.accept()`: 创建 `_DefaultLocalWorkerHandle` ✓
- `_DefaultLocalWorkerHandle.events()`: 懒初始化 `run_agent_messages(self._request)` ✓
- `_DefaultLocalWorkerHandle.cancel()`: no-op（P5-S5 实现）✓
- `_DefaultLocalWorkerHandle.close()`: `await events.aclose()` ✓
- 不包含任何 EngineEvent ingest、terminal mapping、closeout 逻辑 ✓

**测试** (`test_default_local_worker_uses_run_agent_messages`): 通过 monkeypatch 替换 `run_agent_messages`，验证:
- worker 确实调用了 `run_agent_messages(request)` ✓
- events 流正确暴露 ✓
- `local_worker_id` 以 `local-worker-` 为前缀 ✓

**审查结果**: 正确。LocalProxy 只做 Engine 函数调用边界，不做 ingest/closeout。

### 10. Typed Contracts — api.py

**新增 4 个 typed contracts**:

| Protocol / Dataclass | 类型 | 关键方法/字段 |
|---|---|---|
| `LocalWorkerHandle` | Protocol | `local_worker_id`, `events()`, `close()`, `cancel()` |
| `LocalEngineWorker` | Protocol | `accept(snapshot, request) -> LocalWorkerHandle` |
| `LocalEngineWorkerFactory` | Protocol | `create_worker(snapshot) -> LocalEngineWorker` |
| `HostLocalExecutionOptions` | frozen dataclass | 12 个配置字段 |

**审查结果**: 正确。

- 所有 Protocol 均为 `@runtime_checkable` ✓
- `HostLocalExecutionOptions.__post_init__` 对 10 个字段做非空/正数校验 ✓
- `worker_factory` 类型为 `LocalEngineWorkerFactory`（Protocol，非具体实现）✓
- 所有字段均有完整中文 docstring ✓
- 已在 `api.__all__` 和 `__init__.__all__` 中导出 ✓

### 11. HostCommandHandleOptions.local_execution

**设计要求** (plan P5-S3): `local_execution: HostLocalExecutionOptions | None = None`；为 `None` 时保持 no-op dispatch wakeup。

**实现** (api.py:775):
```python
local_execution: HostLocalExecutionOptions | None = None
```

**审查结果**: 正确。
- 默认 `None`，不影响现有 command handle 行为 ✓
- `command.py` 未修改 — 不启动 scheduler ✓
- `admission.py` 未修改 — no-op wakeup 端口保持不变 ✓
- 现有 command handle 测试全部通过 ✓

**设计判断**: plan 明确将 full command-handle scheduler lifecycle wiring 放在 controller 显式开启该 scope 时完成。当前 slice 的职责是定义 typed contract 和提供 scheduler 实现，不要求 wiring 到 command handle。**不阻塞**。

### 12. Architecture / Boundary 检查

**Host → Engine 依赖**:
- `local_proxy.py` import `run_agent_messages` from `dayu.engine` ✓ (plan 允许)
- `local_proxy.py` import `AgentRunRequest`, `EngineEvent` from `dayu.engine.contracts` ✓ (plan 允许)
- `dispatch.py` import `CancellationToken` from `dayu.contracts` ✓ (plan 允许)

**禁止依赖检查**:
- 无 `dayu.fins` import ✓
- 无 `dayu.service` import ✓
- 无 `dayu.ui` import ✓
- `test_command_handle.py` 已更新 `_FORBIDDEN_IMPORT_PREFIXES`：移除 `"dayu.engine"`（从 4 个 → 3 个 prefix），反映 Host → Engine 合法依赖 ✓

**越界实现检查**:

| 禁止实现项 (P5-S4/P5-S5/后续) | 状态 |
|---|---|
| EngineEvent durable ingest / mapping | 未实现 ✓ |
| terminal closeout from Engine events | 未实现 ✓ |
| active/session-scope cancel propagation | 未实现 ✓ |
| ToolRuntime / WAITING / RemoteProxy | 未实现 ✓ |
| recovery / lease / fencing / takeover | 未实现 ✓ |
| Engine 文件修改 | 未修改 ✓ |
| 把 lane token / dispatching 当 lease/fencing | 未使用 ✓ |

**审查结果**: 所有边界约束满足。

### 13. 测试覆盖

| 测试 | 覆盖场景 |
|---|---|
| `test_pending_waiting_dispatching_worker_accept_marks_running` | 完整成功路径：pending → dispatching → ATTEMPT_RUNNING payload 字段验证 |
| `test_cancelled_dispatch_is_skipped_before_worker_call` | pre-accept cancel race: skip worker, factory.created == 0 |
| `test_worker_startup_timeout_closes_starting_attempt_failed` | worker accept timeout → FAILED closeout |
| `test_lane_acquire_timeout_closes_starting_attempt_failed` | lane acquire timeout → FAILED closeout |
| `test_default_local_worker_uses_run_agent_messages` | LocalProxy Engine 边界：调用 run_agent_messages + 事件流 |

**审查结果**: 覆盖计划要求的全部 5 个测试场景 ✓。

---

## 发现项

### L1 (Low) — `_snapshot_from_dispatch` 接受但未使用 `dispatch_record` 参数

**文件**: `dayu/host/dispatch.py:467-488`

**证据**:
```python
def _snapshot_from_dispatch(
    self, record: PendingDispatchRecord, dispatch_record: DispatchRecordRow
) -> AttemptDispatchSnapshot:
    del dispatch_record  # 显式删除
    ...
    return AttemptDispatchSnapshot(
        ...
        dispatch_record_id=record.dispatch_record_id,  # 从 record 取值
        ...
    )
```

参数 `dispatch_record` 在函数体首行被 `del`，所有 dispatch 信息从 `record: PendingDispatchRecord` 获取。`dispatch_record` 参数仅作为文档信号 (snapshot 只在 dispatch record 验证通过后调用)，但不参与实际逻辑。

**影响**: 极低。函数签名与实际使用不一致，可能让读者困惑——为什么传入了 `DispatchRecordRow` 却用 `record.dispatch_record_id`。

**建议**: 移除 `dispatch_record` 参数，或改为从 `dispatch_record` 取值以保持一致性。

**是否阻塞**: 否。

### L2 (Low) — `_NeverCancelledToken` 在 `dispatch.py` 和 `test_local_proxy_engine_ingest.py` 中重复定义

**文件**: `dayu/host/dispatch.py:99-118`, `tests/host/test_local_proxy_engine_ingest.py:27-52`

**证据**: 两个模块各自定义了功能等价的 `_NeverCancelledToken` 类（实现 `CancellationToken` protocol，始终返回 `is_cancelled() == False`）。

**影响**: 无功能影响。两个 token 分别在 scheduler 和测试中使用。

**建议**: 后续可考虑将 `_NeverCancelledToken` 提取为 `dayu.contracts.cancellation` 的公共工具，或作为测试 fixture 共享。

**是否阻塞**: 否。

---

## 架构约束检查

- [x] 分层架构: `dispatch.py` 依赖 `dayu.host.*` / `dayu.runtime.lane` / `dayu.contracts`；`local_proxy.py` 依赖 `dayu.engine`（合法 Host → Engine 方向）✓
- [x] 无反向依赖: Engine 不 import Host 类型 ✓
- [x] 无 `Any` / `object` / 无类型签名 ✓
- [x] 中文 docstring: 所有新增类和函数均有完整中文 docstring ✓
- [x] 无胶水 seam / lazy import / hasattr-getattr 滥用 ✓
- [x] 无 God object: Scheduler 委托 recheck 给模块级辅助函数，worker 创建委托 factory Protocol ✓
- [x] 无兼容性代码 ✓
- [x] Runtime lane DB 独立于 Host durable DB ✓

## 计划对标检查

| 需求 | 状态 |
|---|---|
| scheduler pending → waiting → dispatching → worker accepted | ✓ |
| runtime lane 独立 DB acquire/release/finally | ✓ |
| durable recheck CAS loser release lane 且不调用 worker | ✓ |
| pre-call cancel race 跳过 worker | ✓ |
| lane acquire timeout → FAILED closeout | ✓ |
| worker startup timeout → FAILED closeout | ✓ |
| ATTEMPT_RUNNING payload 含 local_worker_id/worker_accepted_at/lane_name/lane_claim_id | ✓ |
| Attempt RUNNING 只在 durable ATTEMPT_RUNNING 之后 | ✓ |
| LocalProxy default worker 只调用 Engine public run_agent_messages | ✓ |
| LocalProxy 不做 EngineEvent ingest / terminal closeout | ✓ |
| `HostCommandHandleOptions.local_execution` 默认 None | ✓ |
| dispatch record status `dispatching` 保持为最终非取消状态 | ✓ |
| lane token release owner 是 scheduler/worker finally | ✓ |
| 不实现 P5-S4/P5-S5/ToolRuntime/Recovery | ✓ |

## 验证结果

```
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q
→ 27 passed in 0.71s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ no whitespace errors
```

## 裁决

**接受此 slice。** 无阻塞性发现。2 个 Low 建议项均为非阻塞性改进机会。

核心实现——scheduler 的 pending → waiting → dispatching → worker accepted 生命周期、runtime lane 的 acquire/release/finally 语义、durable recheck 的双重防护、pre-call cancel race 检测、ATTEMPT_RUNNING payload 字段、以及 LocalProxy 的 Engine 边界——均正确且通过了所有计划要求的测试。`HostCommandHandleOptions.local_execution` 默认 `None`，不改变现有 command handle 行为，符合 plan 预期。无越界实现。
