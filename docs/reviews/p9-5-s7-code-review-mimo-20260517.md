# P9.5 S7 LocalProxy Close / Events Race — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S7 LocalProxy Close / Events Race code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S7.
- Implementation artifact: `docs/reviews/p9-5-s7-local-proxy-close-events-implementation-20260517.md`.
- Reviewed files: `dayu/host/local_proxy.py`, `tests/host/test_local_proxy_engine_ingest.py`, `tests/host/test_dispatch_scheduler.py`, `dayu/host/README.md`, `tests/README.md`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. _DefaultLocalWorkerHandle.events single-use 是否正确，close 后 / 二次 events 是否稳定失败

**结论：通过。**

**single-use 机制**（`local_proxy.py:80-81, 96-107`）：
- `self._events_started = False` 初始化。
- `events()` 先检查 `self._closed` → raise `RuntimeError("local worker handle is closed")`。
- 再检查 `self._events_started` → raise `RuntimeError("local worker events have already been opened")`。
- 设置 `self._events_started = True` 后才创建 `_DefaultLocalWorkerEventStream`。

**行为验证**：
- 首次调用 `events()` → 成功返回 `_DefaultLocalWorkerEventStream`。
- 二次调用 `events()` → `RuntimeError("already been opened")`。
- `close()` 后调用 `events()` → `RuntimeError("closed")`。
- `close()` 幂等：`async with self._close_lock` 保护，重复 `close()` 第二次直接 return。

**测试覆盖**：
- `test_default_local_worker_events_can_only_be_opened_once`：首次 events 成功，二次 `RuntimeError("already been opened")`。
- `test_default_local_worker_close_is_idempotent_and_events_fail_after_close`（已有）：close 后 events `RuntimeError("closed")`。

### 2. _DefaultLocalWorkerEventStream close while active anext 是否取消活跃 task、关闭底层 generator、不吞外部取消或泄漏未观察异常

**结论：通过。**

**并发 anext 防护**（`local_proxy.py:168-190`）：
- `__anext__` 获取 `self._lock`，检查 `self._active_anext is not None` → raise `RuntimeError("already being consumed")`。
- 创建 `asyncio.create_task(anext(self._events))` 存入 `self._active_anext`。
- 释放 lock 后 `await task`。`finally` 中清除 `self._active_anext`（仅当仍是同一 task）。

**close() 与 active anext 竞争**（`local_proxy.py:192-206`）：
- `close()` 获取 lock → 设置 `self._closed = True` → 读取 `task = self._active_anext` → 释放 lock。
- `task is not None and not task.done()` → `task.cancel()` → `await _suppress_task_cancel(task)`。
- `_suppress_task_cancel`（`local_proxy.py:209-217`）只捕获 `CancelledError`，其它异常正常传播。
- 之后 `await self._events.aclose()` 关闭底层 generator。

**外部取消传播**：`_consume_worker_events` 的 `while True` 循环中 `except asyncio.CancelledError: raise`（`dispatch.py:1136-1137`），不吞外部取消。当 scheduler close 触发 task cancel 时，`CancelledError` 从 `anext` task 注入 → stream `__anext__` 的 `await task` 抛 `CancelledError` → `_suppress_task_cancel` 捕获 → `aclose()` 关闭 generator → `finally` block 释放资源。

**测试覆盖**：
- `test_default_local_worker_close_cancels_active_event_stream`：受控阻塞 generator → `handle.events()` → `anext` task 活跃 → `handle.close()` → 验证 `stream_finalized.is_set()` 且 `pending_read.cancelled()`。

### 3. Scheduler close during active events 是否通过 finally 释放 lane / unregister active registry / close handle，测试是否真实验证

**结论：通过。**

**Production cleanup 路径**（`dispatch.py:1180-1189`）：
```python
finally:
    if run_terminal_closed:
        self._duplicate_governance_registry.clear_run(record.run_id)
    self._active_handles.discard(handle)
    self._active_registry.unregister(
        attempt_id=record.attempt_id,
        execution_id=record.execution_id,
    )
    await _safe_close_worker_handle(handle)
    await _safe_release_lane_token(token)
```

- `_safe_close_worker_handle`（`dispatch.py:1419-1429`）：`try: await handle.close() except Exception: return` — best-effort，吞异常。
- `_safe_release_lane_token`（`dispatch.py:1432-1442`）：`try: await token.release() except Exception: return` — best-effort，吞异常。

**测试覆盖**（`test_scheduler_close_during_active_events_releases_all_resources`）：
- 使用 `_ControlledBlockingHandle` — 受控阻塞 `events()` 直到 task cancel 或显式释放。
- scheduler `drain_once()` 后 `await handle.events_started.wait()` 确认 events 已打开。
- `await scheduler.close()` 触发 scheduler close。
- 验证：`handle.cancel_count == 1`、`handle.close_count == 1`、`handle.events_finalized.is_set()`。
- 验证 active registry 已注销：`registry.cancel(...)` 返回 `False`。
- 验证 lane 已释放：重新 `LaneController.open()` + `acquire()` 成功获取同一 lane。

### 4. Terminal accepted then late event 是否不再被消费且 generator finalized

**结论：通过。**

**Production 行为**（`dispatch.py:1176-1179`）：
- `result.terminal_closeout` 为 `True` → `terminal_seen = True` → `break` 退出 `while True` 循环。
- `finally` block 执行 → `_safe_close_worker_handle(handle)` → `handle.close()` → `event_stream.close()` → `self._events.aclose()` 关闭底层 generator。
- late event 从未被 `anext` 读取。

**测试覆盖**（`test_scheduler_closes_default_local_proxy_after_terminal_before_late_event`）：
- monkeypatch `run_agent_messages` 为 `terminal_then_late_run_agent_messages`：先 yield `FINAL_ANSWER`，再 yield `RUN_FAILED`（late event）。
- `finally` block 设置 `stream_finalized`。
- 验证：`run.status == RunStatus.SUCCEEDED`、`attempt.status == AttemptStatus.SUCCEEDED`、`stream_finalized.is_set()`、`not late_event_reached.is_set()`。
- late event 的 `late_event_reached` 事件未被设置，证明 generator 在 yield late event 之前被 `aclose()` 终结。

### 5. README / tests README 是否只同步当前行为

**结论：通过。**

**`dayu/host/README.md` Phase 5 说明**：
- 变更前："Default LocalProxy worker 调用 Engine public `run_agent_messages(request)` 并暴露 EngineEvent stream；handle close 后不再允许重新读取 events。"
- 变更后："Default LocalProxy worker 调用 Engine public `run_agent_messages(request)` 并暴露 single-use EngineEvent stream；同一 handle 不能重复打开 events，handle close 后不再允许读取 events，close 会关闭已打开的底层 Engine generator。"
- 准确反映 single-use 与 close generator 行为。

**`tests/README.md`**：
- 在覆盖描述列表中新增 "LocalProxy single-use events / close race"。
- 与实际新增测试一致。

### 6. 是否引入 RemoteProxy / exactly-once / recovery / P11 语义或违反 AGENTS 硬约束

**结论：通过。无违反。**

| 约束 | 验证 |
|---|---|
| RemoteProxy / wire protocol | ✅ 未引入 |
| Exactly-once event delivery | ✅ 未引入 |
| Orphan recovery / P11 recovery | ✅ 未引入 |
| 新 public facade | ✅ 未引入，`_DefaultLocalWorkerEventStream` 是 private |
| `Any`/`object`/无类型签名 | ✅ 所有新增函数有完整类型签名 |
| 中文 docstring | ✅ 所有新增类/函数有中文 docstring |
| 无兼容 wrapper | ✅ 未引入 |
| 无反向依赖 | ✅ `local_proxy.py` 只 import `asyncio`、`collections.abc`、`dayu.engine.contracts` |

## Findings

### F1 [Info] _suppress_task_cancel 只捕获 CancelledError，非取消异常从 close() 传播

- **File/line**: `local_proxy.py:209-217`（`_suppress_task_cancel`）+ `local_proxy.py:203-206`（`close()` 调用路径）
- **Evidence**: `_suppress_task_cancel` 只 `except asyncio.CancelledError: return`。如果活跃 anext task 在 `task.cancel()` 注入 `CancelledError` 之前已经以非 `CancelledError` 异常完成（极窄时间窗口），`await task` 会重新抛出该异常，导致 `close()` 传播异常且 `self._events.aclose()` 被跳过。
- **Impact**: 极窄竞争窗口。生产路径中 `_safe_close_worker_handle`（`dispatch.py:1419-1429`）catch-all `except Exception`，所以异常不会泄漏到 scheduler。且如果 task 已 done，`task.cancel()` 是 no-op（`task.done()` 为 True 时 close() 跳过 cancel 路径），只有 task 在 `done()` 检查与 `cancel()` 之间完成的理论窗口才触发。
- **Blocking**: No.

### F2 [Info] __anext__ task 异常未被主动 retrieve 可能触发 RuntimeWarning

- **File/line**: `local_proxy.py:174-190`（`__anext__`）
- **Evidence**: 如果 `__anext__` 的 `await task` 抛出异常（来自底层 generator），异常传播给调用方，但 task 对象持有该异常。如果 task 之后被 GC 回收且异常未被 retrieve，Python 会发出 `RuntimeWarning("Exception in Task was never retrieved")`。
- **Impact**: 不影响功能正确性。生产 scheduler 的 `_consume_worker_events` 在 `while True` 循环中 catch `asyncio.CancelledError: raise` 和 `except Exception`（映射为 worker lost closeout），所以 generator 异常总会被观察。白盒测试中 monkeypatch 的受控 generator 不会产生意外异常。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`local_proxy.py`、2 个测试文件、2 个 README。
- 未修改 production scheduler `dispatch.py`（通过测试锁住已有 `finally` cleanup 行为）。
- 未新增 public facade、public error code、状态机语义。

### Confirmed: no prohibited semantics introduced

- No RemoteProxy / wire protocol
- No exactly-once event delivery
- No orphan recovery / P11 recovery
- No new public facade or public error code
- No compatibility re-export/wrapper
- No `Any`/`object`/untyped signatures

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| RemoteProxy | Not introduced |
| Exactly-once delivery | Not introduced |
| P11 recovery | Not introduced |
| New state-machine states | Not introduced |
| New public facade | Not introduced |
| Compatibility wrapper | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 2 (F1–F2)

S7 实现正确达成计划目标：`_DefaultLocalWorkerHandle.events()` 收紧为 single-use，close 后 / 二次调用稳定抛 `RuntimeError`；`_DefaultLocalWorkerEventStream` 通过 `asyncio.Lock` 防并发 `anext`，`close()` 可取消活跃 task 并关闭底层 generator；scheduler close during active events 通过 `_consume_worker_events` 的 `finally` 单点释放 lane / unregister registry / close handle，测试真实验证全部三项资源释放；terminal accepted 后 late event 不被消费且 generator finalized；README 只同步当前行为；未引入 RemoteProxy / exactly-once / recovery / P11 语义。无硬约束违反。
