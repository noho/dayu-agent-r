# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S5 Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `a91630d6`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s5-code-review-mimo.md`
- Included scope: `dayu/host/command.py`, `dayu/host/dispatch.py`, `dayu/host/admission.py`, `tests/host/test_active_cancel_dispatch.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_admission_multiprocess.py`, `tests/host/test_open_host_runtime.py`, `docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`
- Excluded scope: S3 health state machine, S4 recovery, wait adapter, public API, Service/CLI/Fins/Engine

## Findings

未发现实质性问题。

## Review Analysis

### 1. Level-triggered watchdog event — PASS

**dispatch.py** L2739: `self._active_cancel_watchdog_event.clear()` 在 tick 前执行。tick 期间到达的新 wake 调用 `event.set()`，event 保持 set，loop 下一轮 `wait()` 立即返回（L2731-2734），再次 `clear()` 后执行新 tick。`await asyncio.wait_for(event.wait(), timeout=interval)` 在 timeout 时捕获 `TimeoutError`（L2735-2736），不影响循环。

并发 wake 合并为 level signal：多次 `set()` 不产生多个 tick，因为 event 是二值状态。测试 `test_active_cancel_watchdog_concurrent_wakes_coalesce_to_level_signal` 验证三次 wake 只产生一轮 tick。

不会 busy-loop：每个 tick 必须先 `clear()` 再执行，新 wake 只能在 tick 执行期间到达，驱动恰好一轮额外 tick。

### 2. Watchdog fatal vs normal close — PASS

**dispatch.py** L2740: `self.tick_active_cancel_watchdog(datetime.now(UTC))` 无 try/except 包裹。普通异常直接上浮到 S3 `_supervise_critical_task()`（dispatch.py 约 L2683），由 supervisor 提交 `report_fatal(component="active_cancel_watchdog", reason_code="critical_task_unexpected_exit")`。

旧的两层吞异常逻辑（inner tick `except Exception: continue` + outer loop `except Exception`）已删除。

`CancelledError` 由 L2751 捕获并 re-raise，supervisor 对 `CancelledError` 不报告 fatal。测试 `test_active_cancel_watchdog_unexpected_failure_reports_typed_fatal` 验证 UNAVAILABLE + detail；测试 `test_active_cancel_watchdog_wake_during_tick_drives_second_tick` 验证正常 close 后 health 保持 READY。

### 3. Cancel classification 在同一 write snapshot — PASS

**admission.py** L1548: `_CancelRunOperation.__call__` 返回 `_CancelRunOperationResult`，分类在同一 write transaction 内完成：
- `run.status` 从同一 snapshot 读取（L1576）
- `_cancel_active_attempt` 的 transition 结果在同一 snapshot 判定 deferred/conflict（L1876-1889）
- idempotent replay 从同一 snapshot 的 idempotency record 恢复（L1566-1573）

**command.py**: `_is_deferred_cancel_state`、`_IsDeferredCancelStateOperation`、`_is_predispatch_starting_run`、`_is_active_worker_cancelable_run`、`_read_attempt_and_dispatch_for_run` 已全部删除（diff 确认 -96 行）。`cancel_run` 不再有 `except HostApiError` 后的二次 read transaction。

source scan `rg -n "_is_deferred_cancel_state|Queue(maxsize=1)|except asyncio.QueueFull" dayu/host/command.py dayu/host/dispatch.py` 零命中。

### 4. 多进程 snapshot race 错误码来源 — PASS

**admission.py** L1881-1888: deferred 判定条件 `transition_result.status == StateMutationStatus.INVALID_STATE and transition_result.run.status in (RUNNING, CANCELLING)` 全部来自 transition 在 write lock 内返回的结果。conflict 为 else 分支。

测试 `test_multiprocess_cancel_error_uses_locked_write_snapshot`（test_admission_multiprocess.py）使用 `_BarrierWriteOperation` + `multiprocessing.Pipe` 在 cancel write snapshot 持锁期间让另一进程等待，cancel 完成分类后释放 barrier，另一进程提交 mutation。验证当前调用返回 `UNSUPPORTED_OPERATION`，不被后续 mutation 改写。

### 5. Promotion wake 与 durable classification 一致 — PASS

**admission.py** L783-796: 只有 `result.released_active_slot == True` 时才调用 `_promote_after_release()`。各路径：
- `_cancel_queued` → `released_active_slot=True`（L1707→实际设为 True 在 transition 内）
- `_cancel_active_attempt` (SUPPORTED) → `released_active_slot=False`（L1924）
- terminal/idempotent replay → `released_active_slot=False`（通过 `_classified_cancel_result` 传递）

测试 `test_idempotent_replay_derives_matching_wake_from_durable_snapshot`（test_admission_multiprocess.py）验证：首次 cancel `released_active_slot=True` + promotion wake；replay `released_active_slot=False` + 无 wake；terminal loser `released_active_slot=False` + 无 wake。

watchdog closeout 路径（test_active_cancel_dispatch.py `test_active_cancel_watchdog_closeout_promotes_queued_run`）验证首次 closeout `closed=1` + promotion，第二次 tick `closed=0` + 无额外 worker。

### 6. 未越界修改 — PASS

- S3 health: 未修改 `dayu/host/_execution_health.py`
- S4 recovery: 未修改 `dayu/host/recovery.py` 或 `dayu/host/durable/state.py`
- wait adapter: 未修改
- Service/CLI/Fins/Engine: 未修改
- public taxonomy: `HostApiErrorCode` 未新增；deferred → `UNSUPPORTED_OPERATION`、conflict → `INVALID_STATE` 均为既有错误码

## Open Questions

无。

## Residual Risk

1. `_cancel_active_attempt` 对 `CAS_LOST` 返回 `CONFLICT`（service 层 `INVALID_STATE`）。这与旧 `_raise_for_cancel_transition_status` 对 `CAS_LOST` 抛 `INVALID_STATE` 行为一致，但新代码对 `NOT_FOUND` 仍调用旧 helper 抛错，而对 `INVALID_STATE`/`CAS_LOST` 返回 classification。需确认 `request_active_attempt_cancel_in_transaction` 对 `NOT_FOUND` 是否只在 run 被并发删除时返回——当前代码路径正确。
2. multiprocess deferred fixture 删除 child dispatch row 构造 snapshot，这是测试专用操作，不影响生产。
3. periodic watchdog scan 保留为 fallback reconcile，正确性不再依赖它补偿 queue drop。
