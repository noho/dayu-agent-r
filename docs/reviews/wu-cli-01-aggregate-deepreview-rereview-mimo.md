# WU-CLI-01 aggregate deepreview re-review — AGG-RV-F01

## Scope

- Mode: re-review（仅复核 accepted finding AGG-RV-F01 fix）
- Work unit: WU-CLI-01
- Output file: `docs/reviews/wu-cli-01-aggregate-deepreview-rereview-mimo.md`
- Re-review scope:
  - `dayu/service/entrypoint_runtime.py`（`_close_watcher` 函数，行 534–551）
  - `tests/service/test_entrypoint_runtime.py`（`test_close_watcher_cancels_and_awaits_drain_when_aclose_is_cancelled` 行 843–857，`test_close_watcher_cancels_and_awaits_drain_when_aclose_fails` 行 860–877）
  - `docs/reviews/wu-cli-01-aggregate-deepreview-fix-codex.md`
- Background artifacts:
  - `docs/reviews/wu-cli-01-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-cli-01-aggregate-deepreview-ds.md`
  - `docs/reviews/wu-cli-01-aggregate-deepreview-controller-adjudication.md`
  - `docs/reviews/wu-cli-01-aggregate-deepreview-fix-codex.md`

## Controller fix requirement

> 调整 `_close_watcher`，确保无论 `watcher.aclose()` 成功、失败或被 cancellation 中断，`drain_task` 都会被 cancel 并 await 回收；不吞掉 `watcher.aclose()` 的非取消异常；不改变 watcher attach-before-submit、outbox fallback、cancel terminal observation 语义。

## AGG-RV-F01 状态：已修复

### Fix 分析

**原实现**（AGG-RV-F01 指出的问题）：先 `await watcher.aclose()`，再 `drain_task.cancel()` / `await drain_task`。如果调用方 cancellation 或 `aclose()` 异常在第一个 await 点落地，drain task 的取消与回收路径不执行。

**修复后实现**（`entrypoint_runtime.py` 行 534–551）：

```python
async def _close_watcher(*, watcher: ClosableHostEventIterator, drain_task: asyncio.Task[None]) -> None:
    try:
        await watcher.aclose()
    finally:
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass
```

逐项验证 fix requirement：

| Requirement | 状态 | 证据 |
|---|---|---|
| `watcher.aclose()` 成功时 `drain_task` 被 cancel + await | ✅ | `try` 正常完成后 `finally` 块执行（行 547–551） |
| `watcher.aclose()` 抛普通异常时 `drain_task` 被 cancel + await | ✅ | `finally` 在 `try` body 抛异常后仍执行 |
| `watcher.aclose()` 被 `CancelledError` 中断时 `drain_task` 被 cancel + await | ✅ | `finally` 在 `CancelledError` 传播后仍执行 |
| 不吞掉 `watcher.aclose()` 的非取消异常 | ✅ | `finally` 块不捕获 `aclose()` 异常；`CancelledError` from `drain_task` 被单独抑制（行 550–551），不影响 `aclose()` 异常传播 |
| `CancelledError` from `aclose()` 向上传播 | ✅ | `finally` 块不捕获 `aclose()` 的 `CancelledError` |
| watcher attach-before-submit 语义不变 | ✅ | fix 未修改 `submit_entrypoint_turn_and_wait`（行 402）和 `cancel_entrypoint_run_and_wait`（行 470）的 attach 顺序 |
| outbox fallback 语义不变 | ✅ | fix 未修改 `_wait_for_terminal` 或 `_read_outbox_terminal` |
| cancel terminal observation 语义不变 | ✅ | fix 未修改 `cancel_entrypoint_run_and_wait` 的 cancel 逻辑 |

### Test 覆盖

**新增测试**（`test_entrypoint_runtime.py` 行 843–877）：

1. `test_close_watcher_cancels_and_awaits_drain_when_aclose_is_cancelled`（行 843–857）：
   - 配置 `_FakeHostEventIterator(close_error=asyncio.CancelledError())`
   - 断言：`aclose()` 抛 `CancelledError`、`drain_cancel_observed.is_set()`、`drain_task.done()`、`drain_task.cancelled()`
   - 覆盖：`CancelledError` from `aclose()` 路径

2. `test_close_watcher_cancels_and_awaits_drain_when_aclose_fails`（行 860–877）：
   - 配置 `_FakeHostEventIterator(close_error=RuntimeError("watcher close failed"))`
   - 断言：`aclose()` 异常向上传播（`exc_info.value is close_error`）、`drain_cancel_observed.is_set()`、`drain_task.done()`、`drain_task.cancelled()`
   - 覆盖：普通异常 from `aclose()` 路径

**辅助设施**：
- `_FakeHostEventIterator` 新增 `close_error` 参数支持（行 87–152），使测试可配置 `aclose()` 抛出异常。
- `_wait_until_cancelled` 辅助协程（行 897–910），用 `asyncio.Event` 记录 drain task 被取消的事实。

### Validation evidence 确认

| 检查项 | 结果 |
|---|---|
| `pytest tests/service/test_entrypoint_runtime.py -q` | 20 passed ✅ |
| `pytest tests/service/test_entrypoint_runtime.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` | 56 passed ✅ |
| `pyright` | 0 errors ✅ |
| `git diff --check` | clean ✅ |

## New Findings

未发现实质性问题。Fix 引入的 `try/finally` 结构正确、测试覆盖了关键路径、未引入新问题。

## Open Questions

无。

## Residual Risk

- `drain_task` 已正常完成（非取消）时，`drain_task.cancel()` 为 no-op，`await drain_task` 返回正常结果或抛出 task 自身异常。当前 `_drain_host_events` 设计为只抛 `CancelledError`，因此该路径安全。若未来 `_drain_host_events` 逻辑变更导致 task 抛出非 `CancelledError`，该异常会在 `finally` 块中替代 `aclose()` 异常成为活跃异常——属于 future maintenance 注意事项，不阻塞当前 fix。
- AGG-RV-F02（deferred）、AGG-RV-F03（deferred）、AGG-RV-F04（rejected）均不涉及本次 fix scope，不重新打开。
