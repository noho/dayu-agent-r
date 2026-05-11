# Gateflow Re-review: engine-cancel-commit-boundary-and-tool-timeout / Slice 1

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `contract-timeout-policy-and-runtime-helper`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice1-20260512.md`
- **Fix artifact**: `docs/reviews/gateflow-fix-engine-cancel-slice1-20260512.md`
- **Review scope**: 仅复核上一轮两个 finding 的修复状态，以及 fix 是否引入新问题
- **Conclusion**: fail

两个原始 finding 的直接修复均已落地，但 fix 在 `await_or_cancel_or_timeout` 的预取消短路分支引入了一个新的 owned-awaitable 清理问题：当传入 awaitable 已经是 `asyncio.Task` 时，helper 返回 `WaitCancelled` 却不取消也不等待该 task。

## Finding 修复状态

### Finding 1: 已取消 token 入口仍会启动 target awaitable

- **Status**: fixed for coroutine input; new issue introduced for Task input
- **Evidence**:
  - `await_or_cancel_or_timeout` 已在 `ensure_future` 前检查 `token.is_cancelled()`（`dayu/runtime/cancellation.py:223-226`）。
  - 若 awaitable 是 coroutine，代码会 `awaitable.close()` 后返回 `WaitCancelled`，不会启动 coroutine body。
  - 新增测试 `test_await_or_cancel_or_timeout_short_circuits_when_cancelled` 覆盖 coroutine 预取消短路，并断言 `started is False`（`tests/runtime/test_cancellation.py:455-475`）。
- **Residual / new issue**:
  - 同一分支只处理 coroutine；若调用方传入已经创建的 `asyncio.Task`，`asyncio.iscoroutine(awaitable)` 为 false，helper 会直接返回 `WaitCancelled`，但不会 cancel / await 该 task。
  - 临时探针输出 `WaitCancelled True False False False`，其中后三项分别表示 `task.done() == False`、`task.cancelled() == False`、target finally 未执行。

### Finding 2: mandatory positive timeout 校验允许 NaN 与 infinity

- **Status**: fixed
- **Evidence**:
  - `AgentPolicy.__post_init__` 已使用 `not math.isfinite(...) or <= 0` 校验 timeout（`dayu/engine/contracts/agent_policy.py:75-81`）。
  - 非法 timeout 测试已覆盖 `0.0`、负数、`math.nan`、`math.inf`（`tests/engine/test_agent_phase3_tool_call.py:82-87`, `:696-703`）。

## New Finding

### 1. severity: medium / 预取消短路对 Task awaitable 不再执行 owned target 清理

- **file/line**: `dayu/runtime/cancellation.py:223`
- **evidence**:
  - `await_or_cancel_or_timeout` 的 docstring 声明 helper 拥有 awaitable，token 命中时取消并等待 target task 收口（`dayu/runtime/cancellation.py:200-204`）。
  - 当前预取消分支在 `awaitable` 不是 coroutine 时直接返回 `WaitCancelled`（`dayu/runtime/cancellation.py:223-226`），没有通过 `ensure_future` 取得 target，也没有 `_cancel_task_and_wait(...)`。
  - 临时验证：
    - 命令构造一个已创建的 `asyncio.Task`，token 在调用 helper 前已取消。
    - 输出 `WaitCancelled True False False False`。
    - 这证明 helper 返回取消结果后，传入 task 仍未 done、未 cancelled，target 的 `finally` 也未运行。
- **impact**:
  - 这是 fix 引入的新边界缺陷。Slice 1 approved contract 要求 helper 用 `ensure_future` 拥有 awaitable，并在 cancel / timeout 时 cancel target 并 await done，避免任务泄漏。
  - 虽然后续 Engine `ToolExecutor.execute(...)` 主要会传入 coroutine，但该 helper 是 `dayu.runtime` 的层中立公共能力，签名接受 `Awaitable[T]`，不能只对 coroutine 满足 ownership contract。
- **fix**:
  - 预取消分支区分两类输入：
    - coroutine：保持当前 `close()` 后返回，避免启动 body。
    - 非 coroutine awaitable / Task：用 `asyncio.ensure_future(awaitable)` 取得 target，调用 `_cancel_task_and_wait(target_task)` 后返回 `WaitCancelled`。
  - 增加测试覆盖预取消 + 已创建 Task，断言 helper 返回前 task 已 done / cancelled 或至少 target finally 已运行。

## 验证命令

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`69 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出
- 临时 Task pre-cancel 探针
  - 结果：`WaitCancelled True False False False`

## Residual Risk

- 未运行全量测试；本次 re-review 只按请求运行受影响测试、pyright 与 diff check。
- 本次未修改生产或测试文件；仅写入本 re-review artifact。
