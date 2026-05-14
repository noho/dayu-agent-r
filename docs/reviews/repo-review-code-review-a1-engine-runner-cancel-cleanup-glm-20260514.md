# Code Review

## Scope

- Mode: current changes
- Branch: `fix/host-phase-4`
- Base: `main`
- Output file: `docs/reviews/repo-review-code-review-a1-engine-runner-cancel-cleanup-glm-20260514.md`
- Included scope: unstaged diff in `dayu/engine/runners/openai/runner.py` and `tests/engine/runners/openai/test_response_cleanup_race.py`
- Excluded scope: all other files, committed changes, A4 and unrelated findings
- Source adjudication: `docs/reviews/repo-review-controller-adjudication-20260514.md` A1
- Fix artifact: `docs/reviews/repo-review-fix-a1-engine-runner-cancel-cleanup-20260514.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下逐路径走读确认 A1 修复的正确性：

### 路径 1：response 已取得，cancellation 赢得 race（A1 核心场景）

1. `_do_attempt:430` — `response_ctx = session.post(...)` 返回 context manager
2. `_do_attempt:433` — `await self._enter_response_context_or_cancel(response_ctx.__aenter__())`
3. `_enter_response_context_or_cancel:535` — `response_task = asyncio.create_task(response_enter)`，显式持有 task ownership
4. `:537` — `await _runtime_wait_for_or_cancel(response_task, ...)`，不拥有 task，仅 race
5. `_runtime_wait_for_or_cancel` 内部 `asyncio.wait` 返回时 response_task 已完成（response 已产生），cancel_watcher 同时命中，cancellation 优先，返回 `WaitCancelled`
6. `:545` — `isinstance(outcome, WaitCompleted)` → False
7. `:547` — `assert isinstance(outcome, WaitCancelled)` → 通过（`timeout_seconds=None` 保证不返回 `WaitTimedOut`）
8. `:548` — `await self._release_response_task_if_acquired(response_task)`
9. `_release_response_task_if_acquired:564` — `response_task.done()` 为 True，不 cancel；`:567` `await response_task` 返回已取得的 response；`:572` `response.release()` 被调用。**Release count = 1**
10. `:549` — `raise _RunnerInterrupted(...)`，传播到 `_call_impl:371` `except _RunnerInterrupted:` → 生成器退出，无事件发出
11. `_do_attempt:445-520` 的 `try/finally` 块**未进入**，`finally: response.release()` 未执行

**结论：response 精确释放一次，与 A1 要求一致。**

### 路径 2：cancellation 在 response 取得前命中

1. `_runtime_wait_for_or_cancel` 返回 `WaitCancelled`（cancel_watcher 先于 response_task 完成）
2. `_release_response_task_if_acquired` — task 未完成 → `response_task.cancel()`；`await response_task` 抛 `CancelledError` → 捕获后返回
3. 无 `response.release()` 调用
4. `_RunnerInterrupted` 被抛出

**结论：未取得 response 时不释放，与 A1 要求一致。**

### 路径 3：正常流程，无 cancellation

1. `_runtime_wait_for_or_cancel` 返回 `WaitCompleted(value=response)`
2. `:545-546` — `return outcome.value`，response 交给正文处理
3. `_do_attempt:519-520` — `finally: response.release()` 精确调用一次

**结论：与修改前行为一致，原有 cancellation 语义和 retry/error 行为未改变。**

### 路径 4：外部 `asyncio.CancelledError`

1. `_runtime_wait_for_or_cancel` 清理内部 cancel_watcher 后重抛 `CancelledError`
2. `:542-544` — `except asyncio.CancelledError:` 捕获 → `_release_response_task_if_acquired` 清理 → `raise` 重抛
3. 若 response 已取得则释放；若未取得则 cancel task

**结论：外部取消路径清理正确，CancelledError 正确透传。**

### 架构边界与 task ownership 审查

- 修复将 response enter 的 task ownership 从 `_runtime_await_or_cancel`（helper 拥有）改为 `_enter_response_context_or_cancel`（runner 拥有），使用 `_runtime_wait_for_or_cancel`（helper 不拥有 pending task）。这是正确的设计选择：runner 需要在 cancellation 命中时判断 response 是否已取得，无法将该决策委托给 runtime helper。
- `_release_response_task_if_acquired` 覆盖所有 task 状态分支（done/success、done/cancelled、done/exception、not-done），无 task 泄漏。
- `dayu.runtime` 无新增依赖，无反向 import，符合分层约束。

### 保留行为确认

- `await_or_cancel`（runner 内部 wrapper）仍用于 retry sleep、body read、SSE chunk read、error body read，不受本次修改影响。
- `_do_attempt` 的 `except (aiohttp.ClientError, asyncio.TimeoutError)` 仍捕获 `__aenter__()` 的网络异常并转为 `_AttemptFailedRetriable`。
- `_call_impl` 的 `except _RunnerInterrupted:` 仍为取消唯一出口，不补 `RunnerDoneData`。
- `finally: response.release()` 在正常流程和 body 处理异常时仍精确调用一次。

### 测试质量

- `test_cancel_after_response_acquired_releases_once` — 验证 A1 核心场景：response 已取得 + cancellation 赢得 race → release 精确一次，不读取正文，不发出事件。通过 monkeypatch `_runtime_wait_for_or_cancel` 为 `_cancel_after_response_entered`（先 await pending 再返回 WaitCancelled），正确模拟了"response enter 完成 + cancellation 优先"的竞态结果。
- `test_cancel_before_response_acquired_does_not_release` — 验证 cancellation 先于 response 取得 → 不调用 release，context.response 为 None。通过 `_cancel_before_response_entered`（直接返回 WaitCancelled）正确模拟。
- 测试使用 `_TrackedResponse` 记录 `release_count` 和 `read_count`，能捕获双重释放和意外读取。
- 现有 183 个 runner 测试全部通过，确认无回归。

### pyright / 类型纪律

- `pyright dayu/engine/runners/openai/runner.py tests/engine/runners/openai/test_response_cleanup_race.py` — 0 errors, 0 warnings, 0 informations
- `Coroutine[None, None, aiohttp.ClientResponse]` 类型标注与 `__aenter__()` 返回值一致
- `asyncio.create_task()` 对 `Coroutine` 返回 `Task[T]`，类型链完整
- `assert isinstance(outcome, WaitCancelled)` 在 `timeout_seconds=None` 下不可达 `WaitTimedOut`，是正确的窄化断言

### 中文 docstring

- `_enter_response_context_or_cancel` — 包含 `:param:`、`:returns:`、`:raises:` 三段，中文完整
- `_release_response_task_if_acquired` — 包含 `:param:`、`:returns:`、`:raises:` 三段，中文完整
- 测试文件全部函数和类均包含中文 docstring

### 无关变更检查

- diff 仅涉及：import `Coroutine`、替换 `await_or_cancel` 调用、新增两个方法、新增测试文件
- 无 A4（parser/provider robustness）相关变更
- 无其他 finding 的变更

## Open Questions

- 无

## Residual Risk

- `except asyncio.CancelledError:` 分支（`_enter_response_context_or_cancel:542-544`）的清理逻辑与 `WaitCancelled` 分支共用 `_release_response_task_if_acquired`，但 CancelledError 重抛路径本身未被直接测试。该路径的清理正确性已通过代码走读确认，实际风险极低。
- 测试通过 monkeypatch 模拟竞态结果，未构造真实并发调度压力测试。逻辑正确性不依赖调度时序，但若未来 runtime helper 语义变更，需回归验证。
- `_release_response_task_if_acquired` 中 `except Exception:` 吞掉所有异常，包括理论上不应出现的意外异常。在清理路径中这是合理设计，但若未来 debug 需要可考虑添加 debug 日志。
