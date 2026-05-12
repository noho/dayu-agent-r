# Gateflow Fix: engine-cancel-commit-boundary-and-tool-timeout / Slice 1

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `contract-timeout-policy-and-runtime-helper`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice1-20260512.md`
- **Fix conclusion**: 两个 finding 均接受并已修复。

## Finding 处理

### Finding 1: 已取消 token 入口仍会启动 target awaitable

- **状态**: fixed
- **修复文件**:
  - `dayu/runtime/cancellation.py`
  - `tests/runtime/test_cancellation.py`
- **修复内容**:
  - `await_or_cancel_or_timeout` 在创建 target task 前检查 `token.is_cancelled()`。
  - 已取消时若 awaitable 是 coroutine，直接关闭 coroutine 并返回 `WaitCancelled`，不启动 target body。
  - 新增 `test_await_or_cancel_or_timeout_short_circuits_when_cancelled`，锁定入口已取消时 target body 不运行。

### Finding 2: mandatory positive timeout 校验允许 NaN 与 infinity

- **状态**: fixed
- **修复文件**:
  - `dayu/engine/contracts/agent_policy.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
- **修复内容**:
  - `AgentPolicy.tool_execution_timeout_seconds` 校验改为 `math.isfinite(...) and > 0`。
  - 非法 timeout 测试覆盖 `0.0`、负数、`math.nan`、`math.inf`。

### Re-review Finding: 预取消短路对 Task awaitable 不再执行 owned target 清理

- **状态**: fixed
- **修复文件**:
  - `dayu/runtime/cancellation.py`
  - `tests/runtime/test_cancellation.py`
- **修复内容**:
  - `await_or_cancel_or_timeout` 的预取消分支区分 coroutine 与已创建 task / future。
  - coroutine 输入仍直接 `close()`，避免启动 body。
  - 非 coroutine awaitable 输入通过 `asyncio.ensure_future(...)` 取得 target，并调用 `_cancel_task_and_wait(...)` 等待收口后返回 `WaitCancelled`。
  - 新增 `test_await_or_cancel_or_timeout_closes_task_when_cancelled`，锁定预取消 + task 输入时 target 已 done、已 cancelled，且 `finally` 已运行。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`70 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## 残余风险

- 本 slice 仍只完成契约与 runtime helper；Engine tool executor 调用点接入 timeout policy 属于后续 slice。
