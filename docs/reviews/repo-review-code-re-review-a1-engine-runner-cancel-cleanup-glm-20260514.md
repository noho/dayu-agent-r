# Code Review

## Scope

- Mode: current changes (scoped A1 fix re-review)
- Branch: `fix/host-phase-4`
- Base: `main`
- Gate: full repository review fix work unit A1 re-review
- Source review artifact: `docs/reviews/repo-review-code-review-a1-engine-runner-cancel-cleanup-mimo-20260514.md`
- Review-fix artifact: `docs/reviews/repo-review-fix-a1-engine-runner-cancel-cleanup-review-fix-20260514.md`
- Output file: `docs/reviews/repo-review-code-re-review-a1-engine-runner-cancel-cleanup-glm-20260514.md`
- Included scope: unstaged diff — `dayu/engine/runners/openai/runner.py` 和 `tests/engine/runners/openai/test_response_cleanup_race.py`
- Excluded scope: A4 parser/provider robustness, Host, runtime, contracts, config, docs beyond changed files
- Parallel review coverage: 无

## 验证项逐条追踪

### 1. `except asyncio.CancelledError` 分支是否有直接测试覆盖

**新增测试**: `test_outer_task_cancel_after_response_acquired_propagates_and_releases_once`（test_response_cleanup_race.py:323-344）

**测试机制**: 使用 `_CancelOuterAfterAcquireContext`，其 `__aenter__()` 在取得 response 后通过 `loop.call_soon(self.outer_task.cancel)` 调度取消外层 `runner_task`。不 monkeypatch `_runtime_wait_for_or_cancel`，因此使用真实的 `dayu.runtime.cancellation.wait_for_or_cancel`。

**执行路径追踪**:

1. `runner_task = asyncio.create_task(runner._enter_response_context_or_cancel(context.__aenter__()))` — 创建外层 task
2. `context.outer_task = runner_task` — 注入外层 task 引用
3. `_enter_response_context_or_cancel` 执行：
   - `response_task = asyncio.create_task(response_enter)` — 启动内层 `__aenter__` 协程
   - `await _runtime_wait_for_or_cancel(response_task, ...)` — 真实 runtime helper，内部 `asyncio.wait({pending, cancel_watcher})`
4. 事件循环运行 `response_task`：
   - `_CancelOuterAfterAcquireContext.__aenter__()` 执行
   - 创建 `_TrackedResponse`
   - `loop.call_soon(self.outer_task.cancel)` — 入队 `runner_task.cancel()` 回调
   - 返回 response → `response_task` 完成
5. 事件循环处理 `call_soon` 队列：`runner_task.cancel()` 执行，向外层 task 注入取消
6. `wait_for_or_cancel` 内部 `asyncio.wait` 被 `CancelledError` 中断；`wait_for_or_cancel` 无 `except CancelledError`，仅 `finally` 清理 `cancel_watcher`，`CancelledError` 向上传播
7. `_enter_response_context_or_cancel` 的 `except asyncio.CancelledError` 分支（runner.py:542-544）命中
8. `_release_response_task_if_acquired(response_task)` 调用：
   - `response_task.done()` → True（response 已取得）
   - `response = await response_task` → 取得已完成的 response
   - `response.release()` → `release_count = 1`
9. `raise` 重新抛出 `CancelledError`
10. 测试断言通过：`CancelledError` ✓、`release_count == 1` ✓、`read_count == 0` ✓

**结论**: `except asyncio.CancelledError` 分支通过真实 runtime helper 被直接覆盖。✓

### 2. CancelledError 是否正确传播

测试使用 `pytest.raises(asyncio.CancelledError)` 断言外层 task await 抛出 `CancelledError`。执行路径追踪确认：

- `_release_response_task_if_acquired` 不吞 `CancelledError`（仅捕获 `response_task` 内部的取消/异常，不影响外层传播）
- `_enter_response_context_or_cancel` 的 `except asyncio.CancelledError` 块末尾 `raise` 重新抛出
- `runner_task` 以 `CancelledError` 终止

**结论**: `CancelledError` 正确传播。✓

### 3. 已取得 response 是否 release 恰好一次

测试断言 `context.response.release_count == 1`。执行路径追踪确认：

- `_release_response_task_if_acquired` 中 `response_task.done()` 为 True → 不调用 `cancel()`
- `await response_task` 成功返回 response → `response.release()` 恰好调用一次
- 后续 `_enter_response_context_or_cancel` 直接 `raise`，不再有其他释放路径

**结论**: 已取得 response release 恰好一次。✓

### 4. 无 acquisition 前释放

此场景中 `_CancelOuterAfterAcquireContext.__aenter__()` 在调度取消前已创建并返回 response，`response_task` 在取消发生时已完成。`_release_response_task_if_acquired` 检查 `response_task.done()` 为 True 后走 await+release 路径，不存在"未取得就释放"的可能。

"未取得 response + 外层取消" 的 `CancelledError` 路径未被新测试直接覆盖，但该路径的正确性可通过推理验证：`response_task.done()` 为 False → `cancel()` → `await` 抛 `CancelledError` → return，不调用 `release()`。这与 `WaitCancelled` 分支的 `test_cancel_before_response_acquired_does_not_release` 测试逻辑等价。

**结论**: 无 acquisition 前释放。✓

### 5. 无 scope creep

**生产代码变更**: runner.py 变更属于原始 A1 fix，非本次 MiMo finding fix 的 scope。本次 fix scope 仅为测试文件。

**测试文件变更**:
- 新增 `_CancelOuterAfterAcquireContext` 类（148-189 行）— 专为覆盖 `CancelledError` 分支设计
- 新增 `test_outer_task_cancel_after_response_acquired_propagates_and_releases_once` 测试（323-344 行）
- 原有两个测试未修改
- `_RaceSession` 类型注解仍为 `_AcquireResponseContext | _NeverAcquireResponseContext`，新测试不使用 `_RaceSession`，无需扩展

**结论**: 无 scope creep。✓

### 6. 测试通过

```
pytest tests/engine/runners/openai/test_response_cleanup_race.py -v → 3 passed
pytest tests/engine/runners/openai -q → 184 passed
```

**结论**: 测试全部通过。✓

### 7. pyright 通过

```
pyright dayu/engine/runners/openai/runner.py tests/engine/runners/openai/test_response_cleanup_race.py → 0 errors, 0 warnings, 0 informations
```

**结论**: pyright 通过。✓

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- "未取得 response + 外层 `Task.cancel()`" 的 `CancelledError` 路径缺少独立测试。该路径的正确性可由 `_release_response_task_if_acquired` 的逻辑推理（`response_task.done()` 为 False → cancel+await → `CancelledError` → return，不调用 `release()`），且与已有 `WaitCancelled` 分支测试的取消前场景语义等价。风险等级：极低。

## Verdict

**PASS** — MiMo 低严重度 finding（外层 task 取消路径缺少专项测试覆盖）已修复。新增测试 `test_outer_task_cancel_after_response_acquired_propagates_and_releases_once` 使用真实 `wait_for_or_cancel` runtime helper 直接覆盖 `except asyncio.CancelledError` 分支，验证了：`CancelledError` 正确传播、已取得 response release 恰好一次、无 acquisition 前释放。无 scope creep、测试通过、pyright 通过。A1 fix 验收完成。
