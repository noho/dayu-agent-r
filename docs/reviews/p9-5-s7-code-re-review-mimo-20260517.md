# P9.5 S7 LocalProxy Close / Events Race — Re-Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S7 finding re-review。
- Source review: `docs/reviews/p9-5-s7-code-review-mimo-20260517.md` F1。
- Fix artifact: `docs/reviews/p9-5-s7-fix-20260517.md`。
- Reviewed file: `dayu/host/local_proxy.py`（`_DefaultLocalWorkerEventStream.close`）。
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## F1 Re-Review: aclose() 在 cancel / 非取消异常竞争下是否总会执行

**结论：Fixed。**

**原问题**：`close()` 中 `await _suppress_task_cancel(task)` 若传播非 `CancelledError` 异常，后续 `await self._events.aclose()` 被跳过，底层 Engine generator 未关闭。

**Fix**（`local_proxy.py` `close()` 方法）：
```python
if task is not None and not task.done():
    task.cancel()
    try:
        await _suppress_task_cancel(task)
    finally:
        await self._events.aclose()
    return
await self._events.aclose()
```

**路径验证**：

| 场景 | 行为 | aclose() 执行 | 异常传播 |
|---|---|---|---|
| task 被 cancel → CancelledError | `_suppress_task_cancel` 吞掉 → `finally` aclose → `return` | ✅ | 无异常 |
| task 已完成（done=True） | 跳过 if 块 → 直接 `await self._events.aclose()` | ✅ | 无异常 |
| task 在 cancel 前以非取消异常完成（极窄窗口） | `_suppress_task_cancel` 传播异常 → `finally` 先 aclose → 异常继续传播 | ✅ | 非取消异常传播给调用方 |
| `aclose()` 自身抛异常 | Python 标准异常链附加 | ✅ 已尝试 | 原始异常 + aclose 异常链 |

**非取消异常不被吞**：`_suppress_task_cancel` 只捕获 `CancelledError`（`except asyncio.CancelledError: return`），其它异常正常传播。Fix 通过 `try/finally` 保证 `aclose()` 在异常传播前执行，不改变异常传播语义。

**无新 blocker 发现**。

## Summary

- **F1**: Fixed
- **New blocking findings**: 0
