# Gateflow Code Review: engine-cancel-commit-boundary-and-tool-timeout / Slice 2

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `agent-tool-handshake-timeout`
- **Repository**: `/Users/leo/workspace/dayu-agent-r`
- **Branch**: `host/phase_0_design`
- **Review scope**: 当前未提交 Slice 2 diff
- **Conclusion**: fail

当前 diff 已把 `ToolExecutionContext.timeout_seconds` 接到 `AgentPolicy.tool_execution_timeout_seconds`，并使用 `await_or_cancel_or_timeout` 等待 `ToolExecutor.execute`。正常 timeout happy path 会产出 `RUN_FAILED(tool_execution_timeout)`，不进入下一轮 Runner，也不产出 `TOOL_RESULT_ACCEPTED`。但发现一个 late-cancel 边界会让 timeout 被最终收口成 `RUN_CANCELLED`，与 Slice 2 contract 不一致。

## Findings

### 1. severity: high / timeout 已判定后仍可能被工具取消清理阶段触发的 token 覆盖为 RUN_CANCELLED

- **file/line**: `dayu/engine/agent.py:1361`
- **evidence**:
  - `_execute_tool_batch` 在 `_execute_one_tool(...)` 返回 `WaitTimedOut` 时只把 `_last_tool_batch_result` 设置为 `RunFailedData(error_code="tool_execution_timeout", recoverable=False)`，然后返回（`dayu/engine/agent.py:1357-1367`）。
  - 外层主循环随后通过 `_make_failed_or_cancelled_terminal_with_close(batch_result)` 产出 terminal（`dayu/engine/agent.py:657-660`）。
  - `_make_failed_or_cancelled_terminal_with_close` 会重新检查 `self._is_cancelled()`；若 token 此时已取消，直接返回 `RUN_CANCELLED`，丢弃传入的 timeout failure（`dayu/engine/agent.py:1678-1690`）。
  - 临时探针构造了一个工具 executor：Engine timeout 后取消 execute task，executor 在 `CancelledError` 清理阶段触发同一个 token 并重新抛出。实际 terminal 输出为 `run_cancelled RunCancelledData None`，不是 `run_failed tool_execution_timeout`。
- **impact**:
  - Slice 2 scope 明确要求 timeout 收口为 `RUN_FAILED`，`RunFailedData(error_code="tool_execution_timeout", recoverable=False)`。
  - 当前实现只在 token 未被 late-trigger 的 happy path 满足该语义。若工具运行时在响应 Engine 的 timeout cancel 时同步传播取消信号，或外部取消恰好在 timeout 判定后、terminal 构造前到达，已判定的工具握手 timeout 会被覆盖成 run cancellation。
  - 这会让上层无法区分“用户/Host 取消”与“工具握手预算耗尽”，也削弱 timeout 作为治理失败的可观测性。
- **fix**:
  - timeout 是已接受的 terminal failure candidate 时，不应再走 `_make_failed_or_cancelled_terminal_with_close` 的 late-cancel 覆盖路径。
  - 可选方向：为 tool execution timeout 直接 yield `_make_terminal_failed(...)`；或引入明确的 terminal commit helper，表示 timeout 已赢得该 race，late cancellation 只阻止未来工作，不能覆盖该失败事实。
  - 增加测试覆盖：hanging executor 在 `CancelledError` 清理阶段触发 token，最终仍必须是 `RUN_FAILED` 且 `error_code == "tool_execution_timeout"`。

## Checked Behaviors

- `_execute_one_tool` 的普通 `except Exception` 路径不会吞掉 `WaitTimedOut`：timeout 由 `await_or_cancel_or_timeout` 返回 union 分支，当前不会被伪装成 `ToolFailedOutcome`。
- happy-path timeout 测试覆盖了无 `TOOL_RESULT_ACCEPTED`、无下一轮 Runner、target 收到取消、context timeout 来自 policy。
- `ToolExecutionContext.timeout_seconds` 当前由 `self._request.agent_policy.tool_execution_timeout_seconds` 填入。
- `dayu/contracts/tool_call.py` 与 `dayu/contracts/tool_executor.py` docstring 已说明 timeout 是 Engine 等待工具握手 outcome 的预算，且被取消后的下游清理属于 ToolExecutor / ToolRuntime 职责。
- 新增/修改签名未引入 `Any`、无类型参数或无类型返回值；新增类/函数具备中文 docstring。

## 验证命令

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`71 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出
- 临时 late-cancel probe
  - 结果：`run_cancelled RunCancelledData None`

## Residual Risk

- 本次未运行全量测试；已运行请求指定的受影响测试、pyright 与 diff check。
- 本次是 review-only；未修改生产或测试实现。
