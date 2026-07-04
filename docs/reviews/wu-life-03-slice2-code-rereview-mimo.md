# WU-LIFE-03 Slice 2 Code Re-Review — AgentMiMo

## Scope

- Gate: Slice 2 re-review（controller accepted findings fix verification）
- Branch: `phase/host-engine-next`
- Base: `main`
- Output file: `docs/reviews/wu-life-03-slice2-code-rereview-mimo.md`
- Reviewed scope: controller accepted findings S2-CR-F01 与 S2-CR-F02 的修复代码与对应测试
- Excluded scope: 非目标 findings（DS F02/F03）、Slice 1 已提交变更

## Findings

未发现实质性问题。

## S2-CR-F01 Closure: CLOSED

**要求**: `recovery.py::_has_accepted_cancel_fact` 捕获 `HostDurableError` 并 `return False`；测试覆盖 malformed `RUN_CANCELLING` payload 不 crash 且不 defer 给 watchdog。

**修复验证**:

- **代码位置**: `dayu/host/recovery.py:676-683`
- **修复内容**: `event_payload_object(...)` 调用被包裹在 `try: ... except HostDurableError: return False` 中。malformed payload 时 `_has_accepted_cancel_fact` 返回 `False`，`_classify_run` 回退到 `_classify_active_or_cancelling` 正常 orphan 分类路径。
- **与参考实现一致性**: 修复模式与 `dayu/host/dispatch.py:4153-4160` 的 `_read_linked_cancel_requested_event` 完全一致——同一 `event_payload_object` 调用、同一异常类型、同一 fallback 语义。
- **测试位置**: `tests/host/test_recovery_scan.py:714-738` — `test_scan_malformed_cancelling_payload_uses_orphan_policy`
- **测试覆盖**:
  - seed 一个 payload 为非 object 字符串 `"malformed-cancelling-payload"` 的 `RUN_CANCELLING` event
  - `defer_accepted_cancel_to_watchdog=True`（watchdog enabled）
  - 断言 scan 不 crash
  - 断言 Run 分类为 `RUN_LOST`（走 orphan 策略），而非 `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`
  - 断言 Run 状态推进到 `LOST`
  - 断言 `RUN_LOST` event 被写入

**结论**: S2-CR-F01 已关闭。修复正确、测试充分、与参考实现一致。

## S2-CR-F02 Closure: CLOSED

**要求**: `dispatch.py::_active_cancel_watchdog_loop` 单次 tick 非 cancel 异常不永久终止 loop；测试覆盖 transient failure 后 loop 继续。

**修复验证**:

- **代码位置**: `dayu/host/dispatch.py:2583-2595`
- **修复内容**: `tick_active_cancel_watchdog(...)` 调用被包裹在内层 `try` 中：
  - `except asyncio.CancelledError: raise` — 保留 scheduler close 场景的透传行为
  - `except Exception as exc: ... continue` — 单次 tick 异常记录 `dispatch.active_cancel_watchdog.tick_failed` error log 后 `continue` 到下一轮循环
- **loop 结构**: 外层 `try` 包裹整个 `while not self._closed` 循环，只捕获 `asyncio.CancelledError`（scheduler close）和兜底 `Exception`（致命退出）。内层 tick 异常被内层 except 消化，不传播到外层。
- **测试位置**: `tests/host/test_dispatch_scheduler.py:2715-2774` — `test_active_cancel_watchdog_loop_continues_after_transient_tick_failure`
- **测试覆盖**:
  - 使用 `_TransientFailingActiveCancelWatchdogScheduler` 子类，第一次 `tick_active_cancel_watchdog` 抛 `RuntimeError`，第二次 tick 置位 `second_tick_seen` event
  - 唤醒 watchdog 后等待 `second_tick_seen`（timeout 0.5s）
  - 断言 `_active_cancel_watchdog_task.done() is False`（loop 仍在运行）
  - 断言 `"dispatch.active_cancel_watchdog.tick_failed"` 出现在 error log
  - 断言 `"error_type=RuntimeError"` 出现在 error log

**结论**: S2-CR-F02 已关闭。修复正确、测试充分。单次 transient tick 异常不会终止 watchdog loop。

## New Material Defect Check: 无

修复未引入新 material defect：

1. **类型/docstring 约束**: 修复只增加 try/except 和 continue，不改变函数签名、返回值类型或 docstring 语义。
2. **架构约束**: 不引入新的跨层依赖、反向 import 或 `dayu.runtime` 边界违反。
3. **非目标 DS F02/F03 影响**:
   - DS F02（`ActiveCancelWatchdogWakeupPort` 位置）：不受修复影响，仍为 non-blocking architecture debt。
   - DS F03（overlapping candidate/transition precondition checks）：不受修复影响，仍为 non-blocking maintenance note。
4. **S2-CR-F01 修复副作用**: malformed payload 时 `_has_accepted_cancel_fact` 返回 `False`，`_classify_run` 走 `_classify_active_or_cancelling` → orphan positive proof → `RUN_LOST`。这是正确行为：malformed payload 意味着无法证明 active cancel 已被接受，回退到 orphan 策略是安全的。
5. **S2-CR-F02 修复副作用**: tick 异常后 loop 继续，不会丢失后续 periodic fallback scan。`CancelledError` 仍正确透传给 scheduler close。

## Residual Risk

- watchdog loop 测试使用子类覆写 `tick_active_cancel_watchdog` 而非真实注入 durable storage failure。这是 controller 已接受的测试 tradeoff：子类隔离了核心行为证明（单次 transient 异常不终止 loop），真实 storage failure 场景概率极低且已被 loop 的 `except Exception` 兜底覆盖。
- DS non-blocking notes（F02/F03）未处理，属于 controller 裁决的 non-blocking 范围。

## Review Validation

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q
```

结果：`142 passed in 2.53s`

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`

## Conclusion

**PASS** — 无 BLOCKING FINDINGS。

- S2-CR-F01: **CLOSED** — `_has_accepted_cancel_fact` 正确捕获 `HostDurableError` 并返回 `False`；测试覆盖 malformed payload 不 crash 且不 defer 给 watchdog。
- S2-CR-F02: **CLOSED** — `_active_cancel_watchdog_loop` 单次 tick 非 cancel 异常不永久终止 loop；测试覆盖 transient failure 后 loop 继续。
- 修复未引入新 material defect、未违反 AGENTS.md 类型/docstring/架构约束、未让非目标 DS F02/F03 变成实际问题。
