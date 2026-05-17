# P9.5 S7 LocalProxy Close / Events Race — Code Re-Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S7 fix re-review.
- Source review: `docs/reviews/p9-5-s7-code-review-mimo-20260517.md` (AgentMiMo F1).
- Fix artifact: `docs/reviews/p9-5-s7-fix-20260517.md`.
- Reviewed change: `dayu/host/local_proxy.py` — `_DefaultLocalWorkerEventStream.close()`.
- No code, tests, or artifacts were modified.

## F1 Fix Verification

### F1 原始问题

AgentMiMo F1 (Info): `_suppress_task_cancel` 只捕获 `CancelledError`。如果活跃 anext task 在 `task.cancel()` 注入 `CancelledError` 之前已经以非 `CancelledError` 异常完成（极窄时间窗口），`await task` 会重新抛出该异常，导致 `self._events.aclose()` 被跳过。

### 修复方案

`local_proxy.py:202-210` — 将 `await _suppress_task_cancel(task)` 包裹在 `try/finally` 中：

```python
# 修复前
if task is not None and not task.done():
    task.cancel()
    await _suppress_task_cancel(task)
await self._events.aclose()

# 修复后
if task is not None and not task.done():
    task.cancel()
    try:
        await _suppress_task_cancel(task)
    finally:
        await self._events.aclose()
    return
await self._events.aclose()
```

### 路径覆盖分析

| 场景 | 执行路径 | aclose() 执行？ | 异常传播？ |
|---|---|---|---|
| task 活跃，cancel 成功，CancelledError | `cancel()` → `_suppress_task_cancel` 捕获 → finally `aclose()` → return | ✓ 一次 | 无异常 |
| task 活跃，cancel 成功，但 task 已以非取消异常完成 (F1 race) | `cancel()` 返回 False → `_suppress_task_cancel` re-raise → finally `aclose()` → 异常传播 | ✓ 一次 | ✓ 非取消异常透传 |
| task 活跃，`cancel()` 成功，`aclose()` 自身抛异常 | `cancel()` → `_suppress_task_cancel` 正常 → finally `aclose()` 抛异常 → 异常传播 | ✓ 执行但抛异常 | ✓ aclose 异常透传 |
| task 已完成 (`task.done()` True) | 跳过 if → 无条件 `aclose()` | ✓ 一次 | 无异常 |
| 无活跃 task (`task is None`) | 跳过 if → 无条件 `aclose()` | ✓ 一次 | 无异常 |

所有路径均保证底层 Engine generator `aclose()` 恰好执行一次。非取消异常在 `aclose()` 完成后正确透传，不被吞。

### F1 结论

**Fixed.** `try/finally` 保证 `aclose()` 在 active anext task 被 cancel 后总会执行，不受 task 完成时机或异常类型影响。

## 其他检查

- 修复后的 `close()` 内仅在 active task 路径有 `return`（line 209）防止 fall-through 导致双次 `aclose()`；无 active task 的路径（line 210）执行后自然结束。无双重 `aclose()`。
- `task.cancel()` 在 `try` 之前（line 204）。`task.cancel()` 是标准 asyncio 操作，仅设置标记，不会抛异常。`not task.done()` 与 `task.cancel()` 之间的理论竞争已在 finally 保护下安全处理。
- 其余代码（handle close、`__anext__`、测试）本次未变更，AgentDS S7 原 review 已确认无问题。

## 验证

- `pytest tests/host/test_local_proxy_engine_ingest.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py` → 49 passed。
- `python -m pyright dayu/host/local_proxy.py` → 0 errors, 0 warnings, 0 informations。

## Summary

- **F1 状态**: **Fixed**
- **Blocking findings**: 0
- **新引入问题**: 无
