# WU-LIFE-01 + WU-LIFE-02 Slice B Code Review

## Review Context

- **Reviewer**: MiMo (independent review)
- **Review target**: `tests/host/test_dispatch_scheduler.py` (uncommitted diff, +435/-2 lines)
- **Implementation report**: `docs/reviews/wu-life-01-02-implementation-sliceB-codex-20260601.md`
- **Design source**: `docs/host/design.md` Section 27
- **Accepted plan**: `docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md`
- **Branch**: `feat/host-life-recovery-scheduler-hardening`

## Review Scope

Slice B: Scheduler close / `cancel_all` lifecycle matrix + focused close-window tests.

## Conclusion

**PASS** — 无 blocking finding。Slice B 实现严格遵循 plan，测试 deterministic 且语义正确，无生产代码变更。

## Findings

### B1-信息-低-`_run_scheduler_drain_once` 单行 wrapper

**证据**: `tests/host/test_dispatch_scheduler.py:4520-4528` 定义了 `_run_scheduler_drain_once`，函数体仅 `await scheduler.drain_once()`，无额外逻辑。

**影响**: 增加一层无语义增益的间接调用。在 `test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact` 中用于创建 `asyncio.Task`，但直接用 `asyncio.create_task(scheduler.drain_once())` 同样清晰。

**建议**: 非 blocking，可保留。若追求简洁可内联。

### B2-信息-低-test matrix "worker started but not durable accepted" 场景标注

**证据**: plan Slice B matrix 包含 "worker started but not durable accepted / active registered" 场景，标注为 "new coverage if fixture can deterministically hit window; otherwise stop and report if not deterministic"。`_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` 未包含此场景。implementation report residual risks 正确说明 "stress / fuzz / soak close coverage remains out of scope per plan"。

**影响**: 无实际影响。该窗口需要 deterministic fixture，implementation agent 正确判断无法稳定构造，未强行写 timing-sensitive test。

**建议**: 非 blocking，已在 residual risks 中覆盖。

## Detailed Analysis

### 1. Slice B 严格性

- 所有变更限于 `tests/host/test_dispatch_scheduler.py`，无生产代码变更。
- 无 Slice A（recovery lifecycle）内容混入。
- 新增测试全部聚焦 scheduler close / `cancel_all` lifecycle。
- implementation report 声明 "Tests-first execution did not prove a scheduler close or `cancel_all` production bug"，符合 plan "tests-first, production fix only on failing evidence" 原则。

### 2. Close Lifecycle Matrix 覆盖

`_SCHEDULER_CLOSE_LIFECYCLE_MATRIX` 包含 7 行：

| scenario_id | coverage_classification | Plan 对齐 |
|---|---|---|
| `close-active-worker` | existing | ✅ 对应 plan "scheduler close active worker" |
| `cancel-all-after-register` | new | ✅ 对应 plan "`cancel_all` snapshot after-register" |
| `dispatch-queue-non-empty-close` | new | ✅ 对应 plan "dispatch queue non-empty close" |
| `promotion-queue-non-empty-close` | new | ✅ 对应 plan "promotion queue / task non-empty close" |
| `lane-wait-pre-worker-close` | new | ✅ 对应 plan "lane wait / pre-worker close" |
| `close-cancelled-mid-cleanup-retry` | new | ✅ 对应 plan "close 中途被外层取消" |
| `close-drain-until-empty` | non-goal | ✅ 对应 plan non-goal |

`test_scheduler_close_lifecycle_matrix_covers_slice_b_windows` 验证 required_ids 和 coverage_classification 集合，所有字段非空。

### 3. 测试 Determinism 与语义正确性

#### cancel_all snapshot (`test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel`)

- 使用 `_RegisteringCancelHandle` 在第一个 entry 的 `on_cancel` 回调中注册第二个 entry。
- 断言第一次 `cancel_all` 返回 1，第一个 token cancelled，第二个 token 未 cancelled。
- 断言第二次 `cancel_all` 返回 2，第二个 token cancelled。
- **Deterministic**: 纯同步操作，无 race/sleep。
- **语义正确**: 证明 `cancel_all` 使用锁内快照，不取消后注册 entry。

#### dispatch queue non-empty close (`test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal`)

- `wake_dispatch` 入队后立即 `close()`。
- 断言 `scheduler._queue.qsize() == 1`（未 drain）。
- 断言 `factory.created == 0`（未 dispatch）。
- 断言 Run/Attempt/dispatch 状态未变。
- 断言 `_assert_no_scheduler_close_terminal_events`。
- 断言 close 后 `wake_dispatch` / `drain_once` 抛 `RuntimeError`。
- **Deterministic**: 无 race/sleep。
- **语义正确**: 证明 close 不 drain pending queue，不写 terminal facts，fail closed。

#### promotion non-drain (`test_scheduler_close_cancels_tracked_promotion_task`)

- 使用 `promotion_started` event 确保 promotion 已进入 blocked wait。
- 注入 `scheduler._promotion_queue.put_nowait("session-promotion-pending")`。
- 断言 `promotion_task.done() is True`。
- 断言 `scheduler._promotion_queue.qsize() == 1`（未 drain）。
- 断言 `_assert_no_scheduler_close_terminal_events`。
- **Deterministic**: 使用 `asyncio.Event` 同步。
- **语义正确**: 证明 close 取消 promotion task 但不 drain pending queue，不写 terminal facts。

#### lane wait / pre-worker close (`test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact`)

- 使用 `_BlockedLaneAcquire` + monkeypatch 阻塞 lane acquire。
- 等待 `blocked_acquire.started` 确认进入 lane wait 窗口。
- 断言 dispatch 状态为 `WAITING_FOR_LANE`。
- `scheduler.close()` 后断言 drain task done、factory 未创建 worker、dispatch 状态不变、`cancelled_event_id is None`、无 terminal events、lane controller closed。
- **Deterministic**: 使用 `asyncio.Event` 同步。
- **语义正确**: 证明 lane wait 窗口 close 不写 worker startup timeout terminal fact。

#### close cancellation retry (`test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish`)

- 使用 `_CloseOnceBlockedLaneClose` 阻塞第一次 lane close。
- 创建 close task，等待阻塞点，取消 close task。
- 断言 `_closed is True`、`_close_cleanup_done is False`。
- 再次 `await scheduler.close()`。
- 断言 `blocked_close.calls == 2`（第一次被取消，第二次完成）。
- 断言 `_close_cleanup_done is True`。
- 断言 active tasks/handles 清空、handle cancel/close 各 1 次、registry empty、governance registry cleared。
- 断言 `_assert_no_scheduler_close_terminal_events`。
- 断言 lane controller closed。
- **Deterministic**: 使用 `asyncio.Event` 同步。
- **语义正确**: 证明 close 中途取消后 retry 能完成 cleanup，无资源泄漏，无 terminal facts。

验证了生产代码 `dispatch.py:1659-1698` 的 `close()` 实现：
```python
if self._closed and self._close_cleanup_done:
    return
self._closed = True
# ... cleanup ...
self._close_cleanup_done = True
```
支持 retry：`_closed=True` 但 `_close_cleanup_done=False` 时会重新执行 cleanup。

### 4. Race/Sleep 依赖

- 所有新增测试使用 `asyncio.Event` 进行确定性同步，无 `asyncio.sleep` 用于协调。
- `_wait_for_promotion_task_started` 使用 polling loop（`asyncio.sleep(0.01)` × 200），但这是已有 helper，用于等待后台 task 启动，非新增。

### 5. 私有状态访问

测试访问了以下 scheduler 私有状态：
- `scheduler._closed` / `scheduler._close_cleanup_done`: 验证 close lifecycle 状态机。
- `scheduler._queue.qsize()`: 验证 non-drain 语义。
- `scheduler._drain_task`: 验证 task 生命周期。
- `scheduler._promotion_drain_task` / `scheduler._promotion_queue`: 验证 promotion non-drain。
- `scheduler._active_tasks` / `scheduler._active_handles`: 验证资源清理。
- `scheduler._lane_controller`: 注入 blocked acquire/close。
- `scheduler._duplicate_governance_registry`: 验证 governance 清理。

这些访问在 Python 测试中是常见做法，用于验证内部状态转换。字段代表 scheduler 核心 lifecycle 状态，重构风险低。

### 6. Close Terminal Fact 断言

`_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 覆盖：
```python
("CANCEL_REQUESTED", "ATTEMPT_CANCELLED", "RUN_CANCELLED",
 "ATTEMPT_FAILED", "RUN_FAILED", "ATTEMPT_LOST", "RUN_LOST")
```

`_assert_no_scheduler_close_terminal_events` 遍历所有类型断言 count == 0。

- 每个测试使用独立 `tmp_path` 和 `open_host_durable_store`，数据库隔离。
- `_seed_current_run` 只创建 running run / starting attempt，不写 terminal events。
- 断言范围正确：证明 scheduler close 自身不写 terminal facts，不误把 user cancel path 纳入。

### 7. Docstring / 类型

- `_SchedulerCloseLifecycleCase`: frozen dataclass，所有字段 `str`，有中文 docstring。
- `_RegisteringCancelHandle`: 有中文 docstring，参数类型完整。
- `_BlockedLaneAcquire`: 有中文 docstring，参数类型完整。
- `_CloseOnceBlockedLaneClose`: 有中文 docstring，参数类型完整。
- `_assert_no_scheduler_close_terminal_events`: 有中文 docstring。
- `_run_scheduler_drain_once`: 有中文 docstring。
- 无 `Any`、`object`、无类型参数、无类型返回值。

### 8. README / Doc Sync

- 生产代码未变更，无需更新 `dayu/host/README.md`。
- 测试只新增 focused regression tests，不改变测试分层、命令、marker、约定，无需更新 `tests/README.md`。
- implementation report 正确说明 "No README changes"。

## Blocking Open Questions

无。

## Review Checklist

- [x] 是否严格实现 Slice B，不混入 Slice A 或生产逻辑重写
- [x] close lifecycle matrix 是否覆盖 plan 必需窗口
- [x] coverage_classification 标注是否准确
- [x] cancel_all snapshot test deterministic 且证明快照语义
- [x] dispatch queue non-empty close test deterministic 且证明 non-drain 语义
- [x] promotion non-drain test deterministic 且证明 non-drain 语义
- [x] lane wait / pre-worker close test deterministic 且证明不写 startup timeout
- [x] close cancellation retry cleanup test deterministic 且证明 retry 语义
- [x] 无错误依赖 race/sleep
- [x] 无过度 brittle 的私有状态访问
- [x] close 不写 terminal facts 断言足够
- [x] 不误把 user cancel path 纳入 scheduler close
- [x] helper / dataclass 有中文 docstring、严格类型
- [x] 无 Any / object / untyped 签名
- [x] 生产代码未改时无需 README/doc sync
- [x] correctness / stability / maintainability / test quality 优先
