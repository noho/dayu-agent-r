# Code Review

## Scope

- Mode: current changes (scoped A1 fix review)
- Branch: `fix/host-phase-4`
- Base: `main`
- Source adjudication: `docs/reviews/repo-review-controller-adjudication-20260514.md`
- Fix artifact: `docs/reviews/repo-review-fix-a1-engine-runner-cancel-cleanup-20260514.md`
- Output file: `docs/reviews/repo-review-code-review-a1-engine-runner-cancel-cleanup-mimo-20260514.md`
- Included scope: unstaged diff only — `dayu/engine/runners/openai/runner.py` and `tests/engine/runners/openai/test_response_cleanup_race.py`
- Excluded scope: A4 parser/provider robustness, Host, runtime, contracts, config, docs beyond changed files
- Parallel review coverage: 无

## Findings

### 1-未修复-低-外层 task 取消路径缺少专项测试覆盖

- **入口/函数**: `AsyncOpenAIRunner._enter_response_context_or_cancel()` 的 `except asyncio.CancelledError` 分支（runner.py:542-544）
- **文件(行号)**: `dayu/engine/runners/openai/runner.py:542-544`
- **输入场景**: runner 外层 task 被 `Task.cancel()` 取消（例如 Host 侧取消 runner task），此时 `_runtime_wait_for_or_cancel` 内部的 `asyncio.wait` 抛出 `CancelledError`
- **实际分支**: `except asyncio.CancelledError` 分支调用 `_release_response_task_if_acquired(response_task)` 并 `raise`
- **预期行为**: 若 response 已取得则释放；若未取得则取消 enter task；最终重新抛出 `CancelledError`
- **实际行为**: 实现正确——`_release_response_task_if_acquired` 对已完成 task 读取结果并 `release()`，对未完成 task 先 `cancel()` 再等待。但两条新增测试均 monkeypatch `_runtime_wait_for_or_cancel` 同步返回 `WaitCancelled`，走的是 `isinstance(outcome, WaitCancelled)` 分支（line 547-551），不触发 `CancelledError` 路径。已有 `test_cancellation_boundaries.py` 也不覆盖此方法。
- **直接证据**: `runner.py:542-544` 的 `except asyncio.CancelledError` 分支；`test_response_cleanup_race.py` 两个测试的 monkeypatch 均替换 `_runtime_wait_for_or_cancel` 为同步返回 `WaitCancelled` 的函数
- **影响**: 此路径的正确性依赖实现推理而非测试验证。若未来重构 `_release_response_task_if_acquired` 时引入回归，现有测试不会捕获。
- **建议改法和验证点**: 新增一个测试，不 monkeypatch `_runtime_wait_for_or_cancel`，而是让真实的 `wait_for_or_cancel` 运行，通过 `asyncio.Task.cancel()` 取消外层 runner task，验证 response 已取得时 `release()` 被调用且 `CancelledError` 正确传播。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## A1 正确性裁决

### 核心语义验证

**要求 1：response 已取得 + 取消胜出 → release 恰好一次**

`_enter_response_context_or_cancel` 使用 `asyncio.create_task` 包装 `response_ctx.__aenter__()`，通过 `wait_for_or_cancel` 做 pending vs cancel 二方 race。当取消胜出时，`_release_response_task_if_acquired` 检查 task 是否已完成：

- task 已完成（`__aenter__` 返回了 response）→ `await response_task` 获取 response → `response.release()` — 恰好一次
- task 未完成 → `response_task.cancel()` → `await response_task` 抛 `CancelledError` → return，不调用 `release()`

测试 `test_cancel_after_response_acquired_releases_once` 验证了此路径：`release_count == 1`，`read_count == 0`。

**要求 2：取消在 response 取得前 → 不 release**

测试 `test_cancel_before_response_acquired_does_not_release` 使用 `_NeverAcquireResponseContext`（`__aenter__` 中 `await asyncio.sleep(10.0)`），monkeypatch 使取消立即胜出。`_release_response_task_if_acquired` 先 `cancel()` task，再 `await` 收到 `CancelledError`，直接 return。`context.response` 为 `None`，无 response 可释放。

**要求 3：已有取消语义和重试/错误行为保持不变**

- `_do_attempt` 中 response 取得后的 `try/finally: response.release()` 路径未被修改
- `_call_impl` 中 `_RunnerInterrupted` 捕获和生成器自然终止语义未变
- 重试循环、`_AttemptFailedRetriable`、`_AttemptFailedTerminal` 路径未触碰
- `await_or_cancel` wrapper 和其他使用点（body read、retry sleep、stream idle）未修改
- 仅 `response_ctx.__aenter__()` 调用从 `await_or_cancel` 迁移到 `_enter_response_context_or_cancel`

**A4 和无关变更检查**

diff 仅涉及：
1. `Coroutine` import 新增（给新方法签名用）
2. `response_ctx.__aenter__()` 调用从 `await_or_cancel` 改为 `_enter_response_context_or_cancel`
3. 新增 `_enter_response_context_or_cancel` 和 `_release_response_task_if_acquired` 两个方法

未触碰 parser、provider、error classifier、retry policy、SSE parser、stream idle、payload 或其他 runner 子系统。A4 和无关 finding 未被修改。

### 实现质量

- **类型纪律**: `response_enter` 参数类型为 `Coroutine[None, None, aiohttp.ClientResponse]`，`response_task` 类型为 `asyncio.Task[aiohttp.ClientResponse]`。pyright 0 errors。
- **中文 docstring**: 两个新方法均有完整中文 docstring，包含参数、返回值、异常说明。
- **架构边界**: 新方法是 `AsyncOpenAIRunner` 的私有方法，未引入跨层依赖或反向 import。使用 `dayu.runtime.cancellation.wait_for_or_cancel` 符合 runtime 层中立复用约束。
- **资源释放**: `_release_response_task_if_acquired` 对 task cancel 和 await 的异常均做收口，不留孤儿 task。

## Open Questions

- 无。

## Residual Risk

- 外层 task 取消路径（`except asyncio.CancelledError` 分支）缺少专项测试覆盖，实现正确性依赖推理。风险等级：低。
- `_release_response_task_if_acquired` 中 `response.release()` 后未调用 `__aexit__`，但这与原始 `await_or_cancel` 路径行为一致（原始代码也不调用 `__aexit__`），不是回归。

## Verdict

A1 fix 正确实现了 controller adjudication 要求的三项核心语义。实现无实质性缺陷。唯一发现为低严重度的测试覆盖缺口（外层 task 取消路径），不阻塞 merge。
