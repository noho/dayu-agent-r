# Gateflow Re-review 2: engine-cancel-commit-boundary-and-tool-timeout / Slice 1

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `contract-timeout-policy-and-runtime-helper`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice1-20260512.md`
- **Fix artifact**: `docs/reviews/gateflow-fix-engine-cancel-slice1-20260512.md`
- **Previous re-review artifact**: `docs/reviews/gateflow-re-review-engine-cancel-slice1-20260512.md`
- **Review scope**: 仅复核原 code review 两个 finding 与第一次 re-review 新 finding
- **Conclusion**: pass

当前 diff 已修复三个目标 finding，未在本次复核范围内发现新的同域问题。

## Finding 修复状态

### 原 Finding 1: 已取消 token 入口仍会启动 target awaitable

- **Status**: fixed
- **Evidence**:
  - `await_or_cancel_or_timeout` 已在创建 target task 前检查 `token.is_cancelled()`。
  - coroutine 输入会在预取消分支直接 `close()` 并返回 `WaitCancelled`，不会启动 body。
  - `test_await_or_cancel_or_timeout_short_circuits_when_cancelled` 覆盖该语义，断言 `started is False`。

### 原 Finding 2: mandatory positive timeout 校验允许 NaN 与 infinity

- **Status**: fixed
- **Evidence**:
  - `AgentPolicy.__post_init__` 使用 `not math.isfinite(...) or <= 0` 校验 `tool_execution_timeout_seconds`。
  - 非法 timeout 测试覆盖 `0.0`、负数、`math.nan`、`math.inf`。

### 第一次 Re-review Finding: 预取消 + Task awaitable 必须取消并等待 target 收口

- **Status**: fixed
- **Evidence**:
  - 预取消分支已区分 coroutine 与非 coroutine awaitable。
  - 非 coroutine awaitable 通过 `asyncio.ensure_future(awaitable)` 取得 target，并调用 `_cancel_task_and_wait(target_task)` 后返回 `WaitCancelled`。
  - `test_await_or_cancel_or_timeout_closes_task_when_cancelled` 覆盖已创建 task 的预取消路径，断言 task 已 done、已 cancelled，且 target `finally` 已运行。
  - 临时 Task pre-cancel 探针输出 `WaitCancelled True True True True`，确认 outcome 为 `WaitCancelled`，task done/cancelled，target finally 已执行。

## 验证命令

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`70 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出
- 临时 Task pre-cancel 探针
  - 结果：`WaitCancelled True True True True`

## Residual Risk

- 本次未运行全量测试；按请求运行受影响测试、pyright 与 diff check。
- Slice 1 仍只完成契约与 runtime helper；Engine tool executor 调用点接入 timeout policy 属于后续 slice。
