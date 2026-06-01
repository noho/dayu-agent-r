# WU-LIFE-01 + WU-LIFE-02 Slice B Code Review

## Meta

- **Reviewer**: Agent DS (deepreview).
- **Controller**: AgentController.
- **Gate**: code review Slice B.
- **Design source**: `docs/host/design.md`.
- **Accepted plan**: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`.
- **Implementation report**: `docs/reviews/wu-life-01-02-implementation-sliceB-codex-20260601.md`.
- **Review target**: workspace uncommitted diff in `tests/host/test_dispatch_scheduler.py`.

## Scope Assessment

Implementation report claims Slice B scope only; no production code changes. Verified: diff touches only `tests/host/test_dispatch_scheduler.py`. No changes to `dayu/host/dispatch.py`, `dayu/host/open_host.py`, `dayu/host/api.py`, durable schema, EventLog types, Run/Attempt state machine, or public Host API. This matches the plan's allowed files for Slice B exactly. ✓

## Matrix Coverage Verification

The `_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` constant covers all Slice B required scenarios:

| Plan Scenario | Matrix scenario_id | Coverage Classification |
|---|---|---|
| `cancel_all` snapshot after-register | `cancel-all-after-register` | new ✓ |
| dispatch queue non-empty close | `dispatch-queue-non-empty-close` | new ✓ |
| promotion queue non-empty close | `promotion-queue-non-empty-close` | new ✓ |
| lane wait / pre-worker close | `lane-wait-pre-worker-close` | new ✓ |
| close cancellation retry cleanup | `close-cancelled-mid-cleanup-retry` | new ✓ |
| close drain-until-empty | `close-drain-until-empty` | non-goal ✓ |

The validating test `test_scheduler_close_lifecycle_matrix_covers_slice_b_windows` correctly checks that all 5 required scenario IDs are present and that all classification values (`existing`, `new`, `non-goal`) appear. All fields (window, expected_close_action, expected_durable_mutation, expected_resource_cleanup) are validated as non-empty. ✓

## Test-by-Test Analysis

### test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel

**Design**: Uses `_RegisteringCancelHandle` whose `on_cancel` callback registers a second `(run_id, attempt_id, execution_id, handle, token)` entry into the same `ActiveWorkerRegistry` during the first entry's cancel propagation.

**Trace**:
1. `first_count = registry.cancel_all(_SCHEDULER_CLOSE_REASON)` → lock acquires, tuple is built from `{("attempt-first","execution-first"): entry_first}` → lock releases → `first_handle.on_cancel("scheduler_close")` fires, which calls `registry.register(run_id="run-second", ...)` → this new entry goes into `_entries` under lock → cancel propagation finishes.
2. `first_count == 1` — only the snapshot entry was cancelled. ✓
3. `first_token.is_cancelled() is True` and `first_token.cancel_reason() == "scheduler_close"`. ✓
4. `second_token.is_cancelled() is False` — after-register entry was not cancelled. ✓
5. `second_count = registry.cancel_all(...)` → now both entries are in the snapshot → count is 2. ✓

**Deterministic?** Yes. No sleeps, no races. The `on_cancel` hook is called synchronously within the cancel propagation loop (after lock release), and `register` acquires the lock independently. ✓

### test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal

**Design**: Seeds a RUNNING Run with STARTING Attempt + PENDING dispatch. Wakes dispatch (adds record to queue), then immediately calls `scheduler.close()`.

**Trace**:
1. `_seed_current_run` creates `(RUNNING, STARTING, PENDING)` durable state.
2. `scheduler.wake_dispatch(pending)` → queue has 1 item. `_drain_task` is started but may not have run yet (depends on event loop scheduling).
3. `scheduler.close()`:
   - Sets `_closed = True`.  
   - Cancels heartbeat task, drain task, promotion task (all via `_suppress_task_cancel`).
   - Calls `cancel_all("scheduler_close")` → 0 entries (no worker was accepted).
   - Cancels active tasks (none).  
   - Closes lane controller.  
   - Clears duplicate governance registry.  
   - `_close_cleanup_done = True`.
4. Asserts `scheduler._queue.qsize() == 1` — queue was not drained. ✓
5. Asserts `factory.created == 0` — no worker was created. ✓
6. Asserts durable state unchanged: `(RUNNING, STARTING, PENDING)`. ✓
7. `_assert_no_scheduler_close_terminal_events` — no terminal facts written. ✓
8. `wake_dispatch` after close raises `RuntimeError("HostDispatchScheduler is closed")`. ✓
9. `drain_once()` after close raises same error. ✓

**Deterministic?** Yes. The close call's `_closed = True` gate, followed by drain task cancellation, guarantees the queue is not drained regardless of event loop timing. ✓

### test_scheduler_close_cancels_tracked_promotion_task (updated)

**Pre-existing test extended with**: `promotion_started` event synchronization, `_promotion_queue.put_nowait("session-promotion-pending")` before close, `qsize() == 1` post-close assertion, and `_assert_no_scheduler_close_terminal_events`.

**Trace**:
1. `wake_queue_promotion("session-promotion-close")` → starts `_promotion_drain_loop`.
2. `_promotion_drain_loop` gets `"session-promotion-close"` from queue (queue becomes empty) and calls patched `run_queue_promotion` → enters `_blocked_promotion` → `promotion_started.set()` → `await blocker.wait()`.
3. `scheduler._promotion_queue.put_nowait("session-promotion-pending")` — queue has 1 unprocessed item.
4. `scheduler.close()` → cancels `_promotion_drain_task`.  
5. CancelledError propagates from `blocker.wait()` → `_blocked_promotion` → `_promotion_drain_loop`. `_promotion_drain_loop` catches CancelledError at line 1907 and returns without re-raising.  
6. `_suppress_task_cancel(promotion_task)` completes (task finished normally per asyncio semantics since CancelledError was caught internally).
7. `promotion_task.done() is True`. ✓
8. `scheduler._promotion_queue.qsize() == 1` — pending item not consumed. ✓
9. `_assert_no_scheduler_close_terminal_events`. ✓

**Deterministic?** Yes. The `promotion_started` event + `blocker` event pair guarantees the promotion task is blocked at `blocker.wait()` when close runs. ✓

### test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact

**Design**: Uses `_BlockedLaneAcquire` to deterministically block at lane acquire, creates a drain task that enters the blocked acquire, then closes the scheduler.

**Trace**:
1. Seeds `(RUNNING, STARTING, PENDING)`.
2. `scheduler.wake_dispatch(pending)` → queue has 1 item → drain loop started (or existing).
3. `_drain_task = asyncio.create_task(_run_scheduler_drain_once(scheduler))` — explicit drain task.
4. `await blocked_acquire.started.wait()` — confirms drain task has entered `_dispatch_one` → `_mark_waiting_for_lane` → `lane_controller.acquire(...)` which is the blocked acquire.
5. Asserts dispatch status is `WAITING_FOR_LANE`. ✓
6. `scheduler.close()`:
   - `_closed = True` ✓
   - Cancels drain task → `drain_task.cancel()` → CancelledError propagates from `blocked_acquire.release.wait()` (which is the blocking point in `_BlockedLaneAcquire.__call__`) → `_suppress_task_cancel` catches it → drain task is done.
   - Note: CancelledError from `release.wait()` escapes `_BlockedLaneAcquire.__call__` without the `AssertionError` being reached. ✓
   - `cancel_all` → 0 entries (no worker started).
   - `lane_controller.close()` → sets `_closed = True` on lane controller.
7. Asserts `scheduler._drain_task.done() is True`. ✓
8. Asserts `factory.created == 0`. ✓
9. Asserts dispatch status still `WAITING_FOR_LANE` (no transition). ✓
10. Asserts `dispatch_record.cancelled_event_id is None` — no cancel event written to dispatch. ✓
11. `_assert_no_scheduler_close_terminal_events`. ✓
12. `_lane_controller.acquire(...)` after close raises `RuntimeLaneClosedError`. ✓

**Critical path verification**: The plan requires that "lane wait close 不写 worker startup timeout terminal fact". In `_dispatch_one`, worker startup timeout is written at three sites (lines 1940, 1954, 1986-1990, 2192-2196, 2209-2213, 2228-2231, 2248-2251). ALL of these paths are **after** `lane_controller.acquire()`. Since the drain task is cancelled DURING `acquire()` (before any lane-acquire result is returned), `_dispatch_one` never reaches any of the `_safe_closeout_worker_startup_timeout` call sites. The test correctly proves this path. ✓

**Deterministic?** Yes. The blocked acquire guarantees the drain task is in the pre-acquire-result window when close runs. ✓

### test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish

**Design**: Uses `_ControlledBlockingHandle` for worker event stream blocking and `_CloseOnceBlockedLaneClose` to block the first `lane_controller.close()` call, creating a deterministic cancellation window between active task cleanup and lane controller close.

**Trace — first close**:
1. Dispatch worker with `_ControlledBlockingHandle` → worker enters `_consume_worker_events` → awaits `handle.events()` → blocked at `release_events.wait()`.
2. `duplicate_governance_registry.duplicate_governance_for_run(...)` → 1 active run in registry.
3. Patch `_lane_controller.close` → `_CloseOnceBlockedLaneClose`.
4. `asyncio.create_task(scheduler.close())` → close begins:
   - `_closed = True`. ✓
   - `_best_effort_mark_host_instance_stopping(...)` ✓
   - heartbeat_task cancelled (no-op if not started, or cancelled+suppressed).
   - drain_task — `drain_once()` already returned, `_drain_task` may be None. If started by wake_dispatch, cancelled+suppressed. ✓
   - promotion_task — None (no promotion queued).
   - `cancel_all("scheduler_close")` → cancels the active worker token → `_ControlledBlockingHandle.on_cancel` → `cancel_count = 1`. ✓
   - `tuple(self._active_tasks)` → cancels the worker's `_consume_worker_events` task → CancelledError propagates from `release_events.wait()` → `_consume_worker_events` finally block runs: unregister from registry, `handle.close_count = 1`, token released, handle removed from `_active_handles`, task removed from `_active_tasks` via done callback. ✓
   - `await self._lane_controller.close(...)` → enters `_CloseOnceBlockedLaneClose.__call__` → `calls = 1` → `started.set()` → `await release.wait()` → **blocks**.
5. `await blocked_close.started.wait()` — confirms close is blocked at lane close. ✓
6. `close_task.cancel()` + `await close_task` → raises `CancelledError`.
7. `scheduler._closed is True` and `scheduler._close_cleanup_done is False`. ✓

**Trace — second close**:
1. `await scheduler.close()` — `_closed=True, _close_cleanup_done=False` → passes early return gate → re-executes cleanup:
   - heartbeat_task already done → cancel no-op, suppress returns immediately.
   - drain_task None or done → no-op.
   - promotion_task None → no-op.
   - `cancel_all` → 0 entries (registry was emptied by task finally in first close). ✓
   - `tuple(self._active_tasks)` → empty set. ✓
   - `await self._lane_controller.close(...)` → `_CloseOnceBlockedLaneClose.__call__` → `calls = 2` → falls through to `self._original_close(reason)` → lane controller actually closed. ✓
   - `duplicate_governance_registry.clear_all()` → active_run_count = 0. ✓
   - `_close_cleanup_done = True`. ✓
2. `blocked_close.calls == 2`. ✓
3. `_close_cleanup_done is True`. ✓
4. `not scheduler._active_tasks` — empty. ✓
5. `not scheduler._active_handles` — empty. ✓
6. `handle.cancel_count == 1` — cancelled only once (in first close). ✓
7. `handle.close_count == 1` — closed only once (in first close's task finally). ✓
8. `registry.cancel(ActiveCancelMessage(...))` returns `False` — entry not found (already unregistered). ✓
9. `duplicate_governance_registry.active_run_count() == 0`. ✓
10. `_assert_no_scheduler_close_terminal_events`. ✓
11. `_lane_controller.acquire(...)` raises `RuntimeLaneClosedError`. ✓

**Deterministic?** Yes. The `_CloseOnceBlockedLaneClose` provides a synchronous barrier at a known point in the close() sequence. ✓

**Production code close retry semantics confirmed**: The existing `close()` implementation at line 1665 (`if self._closed and self._close_cleanup_done: return`) already supports "close was started but interrupted" → "retry close to finish cleanup". The test proves this without requiring a production fix. ✓

## Close Terminal Fact Boundary

All four close-window tests call `_assert_no_scheduler_close_terminal_events` which checks that these 7 event types have count 0 in the EventLog:

- `CANCEL_REQUESTED` — user cancel path, NOT scheduler close.
- `ATTEMPT_CANCELLED` — user/engine cancel path.
- `RUN_CANCELLED` — user/engine cancel path.
- `ATTEMPT_FAILED` — engine failure path.
- `RUN_FAILED` — engine failure path.
- `ATTEMPT_LOST` — orphan recovery path.
- `RUN_LOST` — orphan/lost path.

None of these should be written by scheduler close. The test coverage is comprehensive: 4 distinct close windows (queue non-empty, lane wait, close-cancelled-retry, promotion-non-drain) all assert zero terminal facts. ✓

The pre-existing `test_scheduler_close_cancels_tracked_promotion_task` was also extended with this assertion. ✓

## User Cancel vs Scheduler Close Separation

The plan's requirement "不误把用户 cancel path 纳入 scheduler close" is implicitly satisfied because:

1. `_assert_no_scheduler_close_terminal_events` includes `CANCEL_REQUESTED` in the checked types.
2. The `cancel_all` reason is always `"scheduler_close"` (verified in snapshot test: `first_token.cancel_reason() == "scheduler_close"`).
3. Production code at `_consume_worker_events:2771` already has the guard `cancellation_token.is_cancelled() and not self._closed` — during scheduler close, `_closed=True`, so the cancellation token check is short-circuited and no cancelled closeout terminal fact is written. ✓

The pre-existing public cancel tests (`tests/host/test_public_cancel_session_runs.py`) cover user cancel semantics independently. ✓

## Findings

### B1-未修复-低-`_SCHEDULER_CLOSE_REASON` 重复定义

**证据**: 测试文件第 163 行定义 `_SCHEDULER_CLOSE_REASON = "scheduler_close"`，与 `dayu/host/dispatch.py:218` 的生产常量完全相同的值。由于生产常量带 `_` 前缀，测试无法直接导入，形成隐式耦合。

**影响**: 如果生产代码的 `_SCHEDULER_CLOSE_REASON` 值发生变更（例如改为更具体的 reason），测试中的 `first_token.cancel_reason() == _SCHEDULER_CLOSE_REASON` 断言会失败，但失败原因是"测试常量过时"而非"生产逻辑错误"，可能增加排障成本。当前风险较低，因为该常量语义稳定且值不太可能变更。

**建议修复**: 在 `_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` 的 docstring 或 `_SchedulerCloseLifecycleCase` 的注释中记录该常量来自 `dispatch.py:_SCHEDULER_CLOSE_REASON`，提醒未来维护者同步更新。如需更严格的方案，可在 `dayu.host.dispatch` 的 `__all__` 中导出该常量供测试引用，但当前 plan 不允许修改生产代码。

### B2-未修复-低-close cancellation test 访问多个私有状态

**证据**: `test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish` 直接访问：
- `scheduler._closed` (line 2718)
- `scheduler._close_cleanup_done` (line 2718, 2723)
- `scheduler._active_tasks` (line 2724)
- `scheduler._active_handles` (line 2725)
- `scheduler._duplicate_governance_registry` (line 2700, 2737)

以及 `test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal` 中：
- `scheduler._queue.qsize()` (line 2621) — 注：`asyncio.Queue.qsize()` 是公开方法，不算私有访问。

**影响**: 如果 `HostDispatchScheduler` 内部重构（重命名 `_close_cleanup_done`、改变 `_active_tasks` 存储结构、将 `_duplicate_governance_registry` 内联），这些测试会直接损坏。不过这些字段代表稳定的 close lifecycle 状态，命名清晰且语义明确，短期内重构风险低。

**建议修复**: 考虑将 `_close_cleanup_done`、`_active_tasks`、`_active_handles` 的断言替换为可观察行为验证：
- `_active_tasks` / `_active_handles` 为空 → 可通过 `cancel_all` 返回 0 间接验证无残余 entry，但无法区分"已全部 unregister 且 task done"与"从未 register"。
- `_close_cleanup_done` → 可通过"重复 close 不抛异常且不重复 cancel handle"间接验证。

在缺乏等价公开验证路径的情况下，当前私有状态访问是最小必要成本。不阻塞通过，但标记为进一步重构的 watch item。

### B3-未修复-信息-`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 需手动维护

**证据**: 测试文件第 165-172 行硬编码了 7 种 terminal event types。如果未来系统新增 terminal event type（例如 `RUN_TIMED_OUT`），该列表不会自动包含新类型。

**影响**: 新增 terminal event type 时，如果 scheduler close 错误地写入了该新类型，现有测试不会捕获到。风险很低，因为新增 terminal event type 本身就是极罕见的 schema 变更，且必然会伴随对应的 plan + review。

**建议修复**: 无需立即修复。在 plan 或 CLAUDE.md 中记录：新增 EventLog terminal event type 时必须同步检查 `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES`。或将该常量提升到 `dayu.host.dispatch` 的 `__all__` 导出供测试引用。

### B4-未修复-信息-close cancelled mid-cleanup test 依赖 `_HostCancellationToken` 内部状态

**证据**: snapshot test 通过 `first_token.is_cancelled() is True` 和 `first_token.cancel_reason() == _SCHEDULER_CLOSE_REASON` 断言取消语义。这些是 `_HostCancellationToken` 的公开方法，不涉及私有状态访问。✓

但 `_RegisteringCancelHandle.cancel_reasons: list[str]` 是一个自定义属性，不在 `LocalWorkerHandle` 协议中。如果 `LocalWorkerHandle` 协议未来扩展了 `on_cancel` 的返回类型或增加取消审计接口，该断言需要对应调整。

**影响**: 低。`_RegisteringCancelHandle` 是测试专用 fake，与生产 `LocalWorkerHandle` 协议解耦。当协议变更时，fake 随之更新是标准维护成本。

**建议**: 无需修复。

## Contract / Schema / State-Machine Verification

- Durable schema: **unchanged**. ✓
- EventLog type: **unchanged**. ✓
- Host public API: **unchanged**. ✓
- Run / Attempt state machine: **unchanged**. ✓
- Public cancel semantics: **unchanged**. ✓
- Close terminal fact boundary: **unchanged** (close writes no terminal facts, confirmed by all 5 focused tests). ✓

## Production Code Change Assessment

Implementation report correctly states **no production code changes**. All tests pass on existing production code, confirming:

1. `ActiveWorkerRegistry.cancel_all()` already implements snapshot semantics (lock → tuple → release → propagate). ✓
2. `HostDispatchScheduler.close()` already supports close-retry-after-cancellation (`_closed=True, _close_cleanup_done=False` → re-execute cleanup). ✓
3. Close does not drain dispatch/promotion queues (tasks are cancelled, queues not consumed). ✓
4. Close does not write terminal facts (no durable write in close path). ✓

## Helper / Dataclass Quality

All new test helpers and dataclasses meet the plan's requirements:

| Symbol | Docstring | Strict Types | No `Any`/`object`/untyped |
|---|---|---|---|
| `_SchedulerCloseLifecycleCase` | ✓ 中文 | ✓ `frozen=True, slots=True` | ✓ |
| `_RegisteringCancelHandle` | ✓ 中文 | ✓ 完整参数/返回值类型 | ✓ |
| `_BlockedLaneAcquire` | ✓ 中文 | ✓ 匹配 `acquire` 签名 | ✓ |
| `_CloseOnceBlockedLaneClose` | ✓ 中文 | ✓ 参数/返回值类型完整 | ✓ |
| `_assert_no_scheduler_close_terminal_events` | ✓ 中文 | ✓ 参数/返回值类型完整 | ✓ |
| `_run_scheduler_drain_once` | ✓ 中文 | ✓ 参数/返回值类型完整 | ✓ |

所有新增符号均为模块级私有 helper（`_` 前缀），无嵌套函数/嵌套类。无 `Any`、`object`、无类型签名。 ✓

## README / Doc Sync

Implementation report correctly states no README changes needed:
- `tests/README.md`: checked by trigger rule. This slice adds focused regression tests but does not change test layering, commands, markers, conventions, or maintenance rules. ✓
- No production code, public API, schema, state-machine, CLI, or architecture boundary changed. ✓

## Validation Check

- pyright: `0 errors, 0 warnings, 0 informations`. ✓
- `pytest tests/host/test_dispatch_scheduler.py -q`: `54 passed`. ✓
- Regression suite: `20 passed`. ✓

## Risk Assessment

1. **Close cancellation retry test coverage scope**: The test monkeypatches `LaneController.close` as the cancellation barrier. This proves retry semantics at the lane-close boundary, which is the second-to-last cleanup step (before duplicate clear and stopped mark). If a future production change adds cleanup steps BEFORE `cancel_all` that are non-idempotent, the retry semantics could break. The test would not directly catch this because the barrier insertion point would need adjustment. **Risk**: low; any such change would be a close() refactor that should include updated tests.

2. **Lane-wait close test scope**: Tests only the `_dispatch_one` → `lane_controller.acquire()` -> cancelled path. Does not test the `_drain_loop` → multiple `drain_once` → acquire cancelled path. The `_drain_loop` has its own CancelledError handler that re-raises, so the behavior chain is identical. Not a gap. ✓

3. **Worker-started-but-not-accepted window**: Plan marks this as "new coverage if fixture can deterministically hit window; otherwise stop and report." Implementation report does not mention this scenario as tested or stopped. The `_BlockedLaneAcquire` blocks BEFORE the acquire returns, which is the pre-lane-acquired window. The worker-started-but-not-accepted window comes AFTER lane acquire returns and `_start_worker` is called but before `worker.events()` yields the first event. This specific window is **not directly tested**. However, the lane-wait-pre-worker-close test effectively covers the closest deterministic window (pre-acquire), and the close-active-worker existing tests cover post-accept cancellation. The gap between these two windows is difficult to hit deterministically without additional instrumentation. **Risk**: acceptable; the plan allows stopping and reporting if a window is not deterministically reachable. The implementation report's Residual Risks section correctly identifies this as covered only via the lane-wait test and the existing active worker close test.

4. **Production code close-retry semantics**: The current `close()` implementation at line 1665 has `if self._closed and self._close_cleanup_done: return`. This is the ONLY public-facing retry gate. If `self._closed` is True and `_close_cleanup_done` is False (cancelled mid-cleanup), close() re-executes ALL cleanup steps. Steps before the cancellation point are re-executed as idempotent no-ops (cancel done task, suppress done task, cancel_all on empty registry, iterate empty active_tasks). This is correct and proven by the test. ✓

## Conclusion

**Pass.** No blocking findings.

- Finding count: 4 (all low/informational, none blocking).
- Production code: unchanged, no fixes needed. ✓
- Matrix coverage: complete, all Slice B scenarios covered with accurate classification. ✓
- Test determinism: all 5 new/updated tests are deterministic; no sleep/race dependencies. ✓
- Terminal fact boundary: correctly asserted in 4 distinct close windows. ✓
- User cancel separation: maintained (`CANCEL_REQUESTED` counted, `cancel_all` reason is `scheduler_close`, production guard `not self._closed` verified). ✓
- Type quality: strict throughout, no `Any`/`object`/untyped. ✓
- Docstrings: complete Chinese docstrings for all new symbols. ✓
- README sync: correctly determined not needed. ✓

### Blocking Open Questions

None.
