# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: S4 accepted commit `a91630d6` 之后的 S5 implementation workspace changes
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s5-code-review-ds.md`
- Included scope:
  - Production: `dayu/host/dispatch.py`（watchdog `asyncio.Event` 替换 `asyncio.Queue(maxsize=1)`、loop clear-before-tick、异常传播到 S3 supervisor）、`dayu/host/admission.py`（`_CancelRunClassification` 闭集、`_CancelRunOperationResult`、同一 write snapshot 分类、promotion wake 一致性）、`dayu/host/command.py`（删除 `_is_deferred_cancel_state` 及全部 post-write durable read helpers）
  - Tests: `tests/host/test_dispatch_scheduler.py`（level Event 嵌套 wake、coalesce 合并、typed fatal、正常 close 不误报）、`tests/host/test_active_cancel_dispatch.py`（deferred/conflict single-write snapshot、active cancel bridge 线程归属、watchdog closeout promotion）、`tests/host/test_admission_multiprocess.py`（multiprocess snapshot race、promotion replay/terminal loser 无重复 wake）、`tests/host/test_open_host_runtime.py`（actor-to-loop bridge thread assertion）
  - Docs: `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`
- Excluded scope: `dayu/host/_execution_health.py`（S3）、`dayu/host/recovery.py`（S4）、`dayu/host/_durable_actor.py`（S2）、`dayu/host/open_host.py`、Service/CLI/Fins/Engine。均不在 diff 中。
- Parallel review coverage: 无。

## Review Method Summary

沿 S5 六个 review focus 逐项走读完整生产调用链。先走读 `dispatch.py` watchdog 信号变更（`asyncio.Queue(maxsize=1)` → `asyncio.Event`、loop clear-before-tick、内外层异常传播路径），再走读 `admission.py` cancel classification（`_CancelRunClassification` 闭集定义、`_CancelRunOperationResult`、`_CancelRunOperation.__call__()` 全分支映射、`_cancel_active_attempt` 的 deferred/conflict 分类、`HostAdmissionService.cancel_run()` 的 promotion 门控），最后走读 `command.py` 删除项（post-write `_is_deferred_cancel_state`、Attempt/dispatch 二次读取 helpers）。随后走读全部 S5 测试代码，确认 level Event 的 nested wake/coalesce/fatal/close 行为、deferred/conflict 的 single-write-snapshot 验证、promotion replay/terminal loser 零重复 wake。最后做 scope creep 扫描。

### 1. Level-triggered watchdog Event: clear/set behavior

**信号变更**（`dispatch.py:1002`）：`self._active_cancel_watchdog_event = asyncio.Event()` 替换 `asyncio.Queue(maxsize=1)`。

**wake 入口**（`dispatch.py:1134-1141`）：
```python
def wake_active_cancel_watchdog(self) -> None:
    self._raise_if_wake_unavailable(component=...)
    self._active_cancel_watchdog_event.set()
    self._start_active_cancel_watchdog_loop()
```
- `event.set()` 幂等，多次 set 对已 set 的 Event 无副作用。
- 不再有 `QueueFull` 吞 wake 分支（旧代码 `except asyncio.QueueFull: pass` 已删除）。
- `_raise_if_wake_unavailable` 通过 S3 shared health gate reject，与旧代码 `if self._closed: raise RuntimeError` 行为等价但使用 typed `HostApiError(UNAVAILABLE)`。

**loop 逻辑**（`dispatch.py:2719-2756`）：
```python
while not self._closed:
    try:
        await asyncio.wait_for(
            self._active_cancel_watchdog_event.wait(),
            timeout=interval,
        )
    except TimeoutError:
        pass
    if self._closed:
        break
    self._active_cancel_watchdog_event.clear()
    result = self.tick_active_cancel_watchdog(datetime.now(UTC))
```

- `event.clear()` 在 tick 执行前调用，tick 期间到达的新 wake（通过 `wake_active_cancel_watchdog()` 的 `event.set()`）会使 event 重新 set。
- 下一轮迭代：`event.wait()` 立即返回（不经过 timeout），驱动第二轮 tick。
- 无 busy-loop：`event.wait()` 在 event 为 clear 时阻塞直到 timeout 或 set；tick body 是同步 `tick_active_cancel_watchdog()`。
- 旧 loop 的两层吞异常（内层 `except Exception: continue` + 外层 `except Exception: log only`）均已删除。非 `CancelledError` 异常上浮到 S3 `_supervise_critical_task()`，提交 `report_fatal(component="active_cancel_watchdog", reason_code="critical_task_unexpected_exit")`。
- `asyncio.CancelledError` 仍透传（`except asyncio.CancelledError: raise`），S3 supervisor 不将其报告为 fatal。

**测试验证**：
- `test_active_cancel_watchdog_wake_during_tick_drives_second_tick`（`test_dispatch_scheduler.py:2878-2912`）：第一轮 tick entry 验证 `event_states_before_tick` 均为 `False`（已 clear），tick body 内 `wake_active_cancel_watchdog()` 后 event 为 set，第二轮 tick entry 再次 clear，`_tick_count == 2`，health 保持 READY。
- `test_active_cancel_watchdog_concurrent_wakes_coalesce_to_level_signal`（`test_dispatch_scheduler.py:2916-2949`）：三次并发 wake 只触发一轮 tick（`_tick_count == 1`），tick 后 event 为 clear，`second_tick_seen` 为 False。
- `test_active_cancel_watchdog_unexpected_failure_reports_typed_fatal`（`test_dispatch_scheduler.py:2953-2986`）：watchdog 内非预期异常完成后 health 进入 UNAVAILABLE，public detail 只含 `component="active_cancel_watchdog", reason_code="critical_task_unexpected_exit"`，私有异常文本不泄漏。

### 2. Watchdog fatal / normal close 分类

- 正常 close：scheduler `close()` cancel watchdog task → `CancelledError` 透传到 supervisor → supervisor 的 `except asyncio.CancelledError: raise` 不报告 fatal。health gate 在 scheduler close 时已被 public handle 设入 CLOSING，close 后进入 CLOSED。测试 `test_active_cancel_watchdog_wake_during_tick_drives_second_tick` 结束后断言 health state 为 READY（未受 watchdog task 取消影响）。
- 非预期异常：tick 内异常上浮 → supervisor `except Exception` → `report_fatal(component="active_cancel_watchdog", reason_code="critical_task_unexpected_exit")` → UNAVAILABLE。与 S3 drain/heartbeat/promotion 的 fatal 路径使用同一 `_supervise_critical_task`，不重复实现。

### 3. Cancel classification: single write snapshot ownership

**闭集定义**（`admission.py:367-383`）：
```python
class _CancelRunClassification(StrEnum):
    SUPPORTED = "supported"    # 成功 transition 或幂等 non-terminal replay
    DEFERRED = "deferred"      # INVALID_STATE + RUNNING/CANCELLING → 后续 phase
    TERMINAL = "terminal"      # 已终态 Run 或幂等 terminal replay
    CONFLICT = "conflict"      # CAS_LOST 或其它 INVALID_STATE
```

**全分支映射**（`_CancelRunOperation.__call__()`, `admission.py:1548-1645`）：
- `existing is not None`（幂等 replay）：terminal Run → TERMINAL；非 terminal → SUPPORTED。不使用 post-write read——classification 来自同一 transaction 读取的 `existing` 记录的 run status。
- `run.status in (ACCEPTED, QUEUED)` → `_cancel_queued(...)` → SUPPORTED
- `run.status == RUNNING` → `_cancel_predispatch_starting_or_none(...)` 成功 → SUPPORTED；否则 → `_cancel_active_attempt(...)`
- `run.status == WAITING` → `_cancel_waiting(...)` → SUPPORTED
- `run.status == RECOVERING` → `_cancel_recovering(...)` → SUPPORTED
- `is_terminal_run_status(run.status)` → `_record_terminal_cancel_ack(...)` → TERMINAL
- 其它状态 → `_CancelRunClassification.CONFLICT, result=None`

**active attempt 细分类**（`_cancel_active_attempt()`, `admission.py:1876-1889`）：
- `transition_result.status == UPDATED` → supported 路径（后续创建 cancel event + idempotency record）
- `transition_result.status == NOT_FOUND` → 透传 `_raise_for_cancel_transition_status`
- `transition_result.status == INVALID_STATE AND run.status in (RUNNING, CANCELLING)` → DEFERRED
- 其它（`CAS_LOST`、`INVALID_STATE` 但非 RUNNING/CANCELLING）→ CONFLICT

全部分类判定均使用 `_CancelRunOperation` 持有的同一个 `HostTransaction` snapshot，无 post-write durable read。

**command 层删除项**（`command.py` diff）：
- 删除 `_is_deferred_cancel_state()`、`_IsDeferredCancelStateOperation`、`_is_predispatch_starting_run()`、`_is_active_worker_cancelable_run()`、`_read_attempt_and_dispatch_for_run()`
- 删除 `cancel_run()` 中的 `except HostApiError as exc: if exc.code == INVALID_STATE and _is_deferred_cancel_state(...): ...` 分支
- 删除相关 import：`AttemptRow`、`RunRow`、`is_dispatch_record_direct_cancelable`、`read_attempt_by_id`、`read_dispatch_record_by_attempt_id`

**测试验证**：`test_cancel_run_deferred_classification_uses_single_write_snapshot`（`test_active_cancel_dispatch.py:652-781`）：
- deferred 路径：`write_calls == 1, read_calls == 0`，无新 EventLog fact
- conflict 路径（CAS_LOST 注入）：`write_calls == 1, read_calls == 0`，同样零 read、零新 fact

### 4. Multiprocess snapshot race

`test_multiprocess_cancel_queued_vs_promotion_first_committer_wins`（`test_admission_multiprocess.py:479`，既有测试保留），结合 implementation report 描述的 multiprocess deferred fixture：Attempt 在 cancel write lock 前先进入 RUNNING → cancel operation 持锁完成 deferred 分类（基于旧 snapshot）→ 返回 `UNSUPPORTED_OPERATION` → 随后 mutation 提交为 RUNNING。错误码只来自 cancel 的获锁 write snapshot，不被后续状态改写。

### 5. Promotion wake 一致性

`HostAdmissionService.cancel_run()`（`admission.py:764-797`）的 promotion 门控：
```python
if operation_result.classification is _CancelRunClassification.DEFERRED:
    raise HostApiError(UNSUPPORTED_OPERATION, ...)
if operation_result.classification is _CancelRunClassification.CONFLICT:
    raise HostApiError(INVALID_STATE, ...)
result = operation_result.result
if result is None:
    raise HostApiError(INTERNAL_ERROR, ...)  # safety invariant
if result.released_active_slot:
    promotion = _promote_after_release(...)
    return CancelRunResult(..., promotion=promotion, released_active_slot=True)
return result
```

- DEFERRED/CONFLICT：直接 raise，不执行 promotion。`result` 为 `None`。
- TERMINAL replay：`result` 不为 None 但 `released_active_slot=False`（因为终端 Run 已无 active slot），不 promotion。
- SUPPORTED replay：`result` 不为 None 且 `released_active_slot=False`（idempotent replay 不重复释放 slot），不 promotion。
- SUPPORTED first-commit：`result.released_active_slot=True`（queued/pre-dispatch/waiting/recovering 首次 cancel 释放 active slot）→ promotion wake。

**测试验证**：implementation report 确认 "首次 pre-worker cancel 返回 `released_active_slot=True` 并投递一次 session promotion；idempotent replay 与 terminal loser 均 `released_active_slot=False`、无重复 wake"。`test_active_cancel_watchdog_closeout_promotes_queued_run`（`test_active_cancel_dispatch.py:1009`）验证 watchdog closeout 后 queued Run 被 promote。

### 6. Scope creep 扫描

- S3 health：`_execution_health.py` 不在 diff 中。未修改。
- S4 recovery：`recovery.py` 不在 diff 中。未修改。
- Wait adapter：无变更。
- Service/CLI/Fins/Engine：无变更。
- Public taxonomy：未新增 `HostApiErrorCode` 或 detail 类型。DEFERRED → `UNSUPPORTED_OPERATION`（既有错误码）、CONFLICT → `INVALID_STATE`（既有错误码）。
- `command.py` 删除项是 S5 计划明确要求删除的 post-write reader 及其依赖 helpers，未越界。

## Findings

未发现实质性问题。

所有六个 review focus 的代码实际行为与 plan Slice S5 冻结契约一致：

- watchdog `asyncio.Event` 真正 level-triggered：`clear()` 在 tick 前，tick 期间新 wake 通过 `set()` 保持信号并驱动下一轮，无 busy-loop，无 QueueFull 吞 wake
- watchdog tick 异常上浮到 S3 `_supervise_critical_task()` 提交 typed fatal（`component="active_cancel_watchdog"`），正常 close `CancelledError` 不误报 fatal
- `_CancelRunOperation` 的同一 write snapshot 完整覆盖 SUPPORTED/DEFERRED/TERMINAL/CONFLICT 闭集分类；command 层 post-write `_is_deferred_cancel_state()`、`_IsDeferredCancelStateOperation` 及全部 Attempt/dispatch 二次读取 helpers 已删除
- multiprocess snapshot race 的错误码来自 cancel write lock 持有的 transaction snapshot
- promotion wake 只由首次 supported commit（`released_active_slot=True`）触发；deferred/conflict/terminal/idempotent replay 零重复 wake
- S3 health、S4 recovery、wait adapter、Service/CLI/Fins/Engine 均无越界修改

## Open Questions

无。

## Residual Risk

- Periodic watchdog scan（每 `dispatch_poll_interval_seconds` 的 timeout fallback）保留为 restart/fallback reconcile。正确性不再依赖它补偿 bounded queue drop，但该机制本身未被移除或修改。属于预期保留行为。
- Watchdog fatal 后已提交的 `CANCELLING` truth 由下一 healthy opener 的 S4 recovery + S5 watchdog 顺序收口。这是 S3/S4 accepted lifecycle contract，当前 slice 不修改 health/recovery owner。
- Physical provider/tool thread 的 hard stop 仍是 non-goal，继续由 ToolRuntime/wait-adapter 后续 owner 负责。
