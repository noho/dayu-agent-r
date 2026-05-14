# Code Re-Review: A1 Engine Runner Cancel Cleanup

## Scope

- Mode: current changes (scoped A1 re-review)
- Branch: `fix/host-phase-4`
- Base: `main`
- Source review artifact: `docs/reviews/repo-review-code-review-a1-engine-runner-cancel-cleanup-mimo-20260514.md`
- Review-fix artifact: `docs/reviews/repo-review-fix-a1-engine-runner-cancel-cleanup-review-fix-20260514.md`
- Output file: `docs/reviews/repo-review-code-re-review-a1-engine-runner-cancel-cleanup-mimo-20260514.md`
- Included scope: unstaged diff — `tests/engine/runners/openai/test_response_cleanup_race.py`
- Excluded scope: production code (no change since last review), A4, Host, runtime, contracts, config
- Parallel review coverage: 无

## Accepted Finding 1 Verification

**Original finding (MiMo low)**: `_enter_response_context_or_cancel()` 外层 `asyncio.CancelledError` 分支缺少专项测试覆盖。

**Fix 承诺**: 新增测试，不 monkeypatch `_runtime_wait_for_or_cancel`，通过 `asyncio.Task.cancel()` 取消外层 task，验证 `CancelledError` 传播与 response 恰好释放一次。

### 逐项验证

**要求 1：使用真实 runtime wait helper，不 monkeypatch**

新测试 `test_outer_task_cancel_after_response_acquired_propagates_and_releases_once`（`test_response_cleanup_race.py:323-344`）：
- 无 `monkeypatch` 参数
- 不替换 `_runtime_wait_for_or_cancel`
- 调用 `runner._enter_response_context_or_cancel(context.__aenter__())` 经由 `asyncio.create_task` 包装后，内部 `_runtime_wait_for_or_cancel` 是真实实现

**证据**: test 函数签名无 `monkeypatch` fixture；函数体无 `monkeypatch.setattr` 调用。

**判定**: 通过。

**要求 2：`CancelledError` 正确传播**

`_CancelOuterAfterAcquireContext.__aenter__` 在取得 response 后通过 `loop.call_soon(self.outer_task.cancel)` 调度取消外层 task。外层 task 是 `asyncio.create_task(runner._enter_response_context_or_cancel(...))`，取消触发 `runner.py:542` 的 `except asyncio.CancelledError` 分支，执行清理后 `raise` 重新抛出。

测试用 `pytest.raises(asyncio.CancelledError)` 断言异常确实传播到调用方。

**证据**: `test_response_cleanup_race.py:339-340`；`runner.py:542-544`。

**判定**: 通过。

**要求 3：已取得 response 恰好释放一次**

`_release_response_task_if_acquired`（`runner.py:553-572`）在 response task 已完成时 `await response_task` 获取 response → `response.release()`。`_TrackedResponse.release` 递增 `release_count`。

测试断言 `context.response.release_count == 1`。

**证据**: `test_response_cleanup_race.py:343`；`runner.py:572`。

**判定**: 通过。

**要求 4：取得前不 release**

`_CancelOuterAfterAcquireContext.__aenter__` 先创建 response，再调度取消，最后 return response。response 创建在取消调度之前，但取消通过 `call_soon` 在当前迭代结束后才执行——此时 `__aenter__` 已返回 response，response task 已完成。因此 `_release_response_task_if_acquired` 走已完成分支，`release()` 被调用。

测试断言 `context.response is not None`（response 确实被创建）且 `release_count == 1`（恰好一次）。

**证据**: `test_response_cleanup_race.py:342-344`；`_CancelOuterAfterAcquireContext.__aenter__` 的执行顺序。

**判定**: 通过。

### 测试设计质量

- 测试直接调用 `_enter_response_context_or_cancel` 而非通过 `_collect_events` 端到端路径，聚焦度高
- `_CancelOuterAfterAcquireContext` 职责单一：只在 `__aenter__` 中创建 response 并调度取消
- `call_soon` 确保取消在当前事件循环迭代后发生，时序确定性好
- 断言覆盖三个关键事实：异常传播、response 存在、release 恰好一次

## Scope Creep Check

unstaged diff 仅新增：
- `_CancelOuterAfterAcquireContext` 类（测试 helper）
- `test_outer_task_cancel_after_response_acquired_propagates_and_releases_once` 测试函数

未修改任何 production 代码、未修改已有测试、未引入新依赖。

**判定**: 无 scope creep。

## Validation

- `pytest tests/engine/runners/openai/test_response_cleanup_race.py -q`: 3 passed
- `pytest tests/engine/runners/openai`: 184 passed
- `pyright tests/engine/runners/openai/test_response_cleanup_race.py`: 0 errors
- `pyright dayu/engine/runners/openai tests/engine/runners/openai`: 0 errors

## Verdict

**通过。** Accepted MiMo low finding 已正确修复。新测试使用真实 runtime wait helper 直接覆盖 `except asyncio.CancelledError` 分支，验证 CancelledError 传播与已取得 response 恰好释放一次。无 scope creep，测试通过，pyright 通过。
