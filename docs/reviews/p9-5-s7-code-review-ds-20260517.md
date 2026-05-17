# P9.5 S7 LocalProxy Close / Events Race — Code Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S7 LocalProxy Close / Events Race code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S7.
- Implementation artifact: `docs/reviews/p9-5-s7-local-proxy-close-events-implementation-20260517.md`.
- Reviewed files: `dayu/host/local_proxy.py`, `tests/host/test_local_proxy_engine_ingest.py`, `tests/host/test_dispatch_scheduler.py`, `dayu/host/README.md`, `tests/README.md`.
- `dayu/host/dispatch.py` 本次未改，但 scheduler finally 清理路径是 review 重点；`dayu/host/engine_ingest.py` 本次未改。
- No code, tests, or artifacts were modified.

## Scope Adherence Verification

- All changes within S7 allowed files: `dayu/host/local_proxy.py`, `tests/host/test_local_proxy_engine_ingest.py`, `tests/host/test_dispatch_scheduler.py`, `dayu/host/README.md`, `tests/README.md`.
- `dispatch.py` 与 `engine_ingest.py` 未修改，仅通过测试锁住已有 finally 清理行为。
- 无 RemoteProxy 语义、无 exactly-once event delivery、无 wire protocol、无 P11 orphan recovery。
- Plan boundaries honored.

## Findings

未发现实质性问题。

## Review Point Checklist

### 1. `_DefaultLocalWorkerHandle.events()` single-use 正确性

**通过。**

- `local_proxy.py:102-106`: `_closed` 检查阻止 close 后读取 events，`_events_started` 检查阻止重复打开
- `_events_started = True` 在创建 stream 前设（line 106），同步执行无 TOCTOU
- close 后的 events() 返回 `RuntimeError("local worker handle is closed")`；二次 events() 返回 `RuntimeError("local worker events have already been opened")`
- 测试 `test_default_local_worker_events_can_only_be_opened_once` (test_local_proxy_engine_ingest.py:437)：首次 events() 正常返回，二次 events() 抛 RuntimeError
- 测试 `test_default_local_worker_close_is_idempotent_and_events_fail_after_close` (已有，line ~186)：close 后 events() 稳定抛 RuntimeError

### 2. `_DefaultLocalWorkerEventStream` close while active anext 正确性

**通过。**

- `__anext__` (local_proxy.py:166-191): 通过 `_lock` 阻止并发 anext；`_closed` 已设时立即 `raise StopAsyncIteration`
- 活跃 anext 时 close() 调用 `task.cancel()` (line 204)，再 `await _suppress_task_cancel(task)` 吞掉 CancelledError (line 205)，最后 `await self._events.aclose()` 关闭底层 generator (line 206)
- `close()` 在 `_closed = True` 后不再进入 close 逻辑 —— 幂等
- CancelledError 通过 `__anext__` 向外传播 (不被 `except StopAsyncIteration` 捕获)，scheduler 的 `_consume_worker_events` 有 `except asyncio.CancelledError: raise` 正确透传
- 测试 `test_default_local_worker_close_cancels_active_event_stream` (test_local_proxy_engine_ingest.py:472)：验证 pending_read task 被取消、底层 generator finalize (`stream_finalized.is_set()`)、close 后 events() 拒绝

### 3. scheduler close during active events 资源释放

**通过。**

- `_consume_worker_events` finally block (dispatch.py:1180-1189) 单点负责：duplicate governance registry 清理、`_active_handles.discard(handle)`、`_active_registry.unregister()`、`_safe_close_worker_handle(handle)`、`_safe_release_lane_token(token)`
- scheduler `close()` (dispatch.py:465-484) 取消 drain task → cancel 所有 active handle → cancel 所有 active task → close lane controller → clear_all duplicate registry
- 当 active task 被 cancel 时，`_consume_worker_events` 的 finally 块仍执行 —— lane release、registry unregister、handle close 都会完成
- `_safe_close_worker_handle` 与 `_safe_release_lane_token` 都是 best-effort（内部 try/except），确保任一失败不阻止其它清理
- 测试 `test_scheduler_close_during_active_events_releases_all_resources` (test_dispatch_scheduler.py:267): 使用 `_ControlledBlockingHandle` 阻塞事件消费，验证 `cancel_count == 1`、`close_count == 1`、`events_finalized.is_set()`、registry unregister、lane token 可被新 LaneController 重新 acquire

### 4. terminal accepted then late event 不再被消费且 generator finalized

**通过。**

- 生产路径：terminal event 被 ingest 后，`_consume_worker_events` 设 `terminal_seen = True` 并 break (dispatch.py:1178-1179)，finally 块调用 `_safe_close_worker_handle(handle)` → `handle.close()` → `event_stream.close()` → `self._events.aclose()`
- `aclose()` 对 async generator 投送 `GeneratorExit`，在最后一个 yield 暂停点终止 generator 执行
- 测试 `test_scheduler_closes_default_local_proxy_after_terminal_before_late_event` (test_dispatch_scheduler.py:336): monkeypatch generator 先产出 `FINAL_ANSWER` (terminal)，再设 `late_event_reached.set()` 并产出 `RUN_FAILED` (late event)
  - `assert not late_event_reached.is_set()` — 证明 late event 未被执行到
  - `assert stream_finalized.is_set()` — 证明 generator finally 执行
  - `assert run.status == RunStatus.SUCCEEDED` — 证明只接受 terminal closeout
  - `_wait_for_active_tasks_to_finish(scheduler)` — 证明 task 完整结束

### 5. README/tests README 只同步当前行为

**通过。**

- `dayu/host/README.md` 变更：`"Default LocalProxy worker ... 暴露 single-use EngineEvent stream；同一 handle 不能重复打开 events，handle close 后不再允许读取 events，close 会关闭已打开的底层 Engine generator"` — 只描述当前实现行为，无未来设计
- `tests/README.md` 变更：`"LocalProxy single-use events / close race / Engine entry boundary"` — 补充当前新增测试覆盖类别
- 两处都不引入 RemoteProxy、recovery、P11 等未来语义

### 6. 无 RemoteProxy / exactly-once / recovery / P11 语义，无 AGENTS 硬约束违反

**通过。**

- 全文搜索 S7 diff：无 "RemoteProxy"、"exactly-once"、"recovery"、"orphan"、"P11"、"callback"、"wire protocol"、"durable ack"
- scheduler close 仍是 best-effort cancel + finally cleanup，符合当前本地 worker 语义
- clean EOF without terminal 与 stream exception 仍沿当前 `EngineEventIngestor` closeout 路径映射为 FAILED / LOST，无新增 recovery 分支
- AGENTS 硬约束验证：
  - 无 `object`/`Any`/无类型参数/无类型返回值
  - 所有新函数有完整中文 docstring（参数、返回值、异常）
  - 无兼容性 re-export/wrapper
  - 无反向依赖（LocalProxy → Engine 向下，正确）
  - 无 God object/function/dataclass
  - 无 `hasattr`/`getattr` 滥用
  - 无魔法数字/字符串 —— `_LOCAL_WORKER_ID_PREFIX = "local-worker"` 为模块级常量

## Open Questions

无。

## Residual Risk

- `_suppress_task_cancel` 在 `local_proxy.py`（`Task[EngineEvent]`）与 `dispatch.py`（`Task[None]`）存在双份实现，逻辑相同仅类型参数不同。当前两份各自 private 且调用上下文语义不同，不构成实际缺陷。若后续出现第三处同类逻辑可考虑抽取到 `dayu.runtime`。
- `_DefaultLocalWorkerEventStream.close()` 在 cancel task 后调用 `self._events.aclose()`。若 `asyncio.create_task(anext(self._events))` 被取消与 `aclose()` 并发作用于同一 async generator，CPython 的 `aclose()` 对已 finalized generator 是幂等的。但在非 CPython 运行时（如 PyPy）上行为可能不同——当前项目只支持 CPython 3.11。
- S7 未新增 `_DefaultLocalWorkerHandle.cancel()` 的生产路径链路。当前 `cancel()` 仍是空操作（只记录 reason），实际取消通过 scheduler 的 `_safe_cancel_worker_handle` + active task cancel 实现。`_DefaultLocalWorkerHandle.cancel()` 的 `del reason` 保持 handle 边界但无实际取消效果——这是 Phase 5 既有的设计决定，本次未变更。

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **六项审查点**: 全部通过
- **测试**: 49 passed, 0 failed (`pytest tests/host/test_local_proxy_engine_ingest.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py`)
- **类型检查**: pyright 0 errors, 0 warnings, 0 informations
- **diff check**: 通过
