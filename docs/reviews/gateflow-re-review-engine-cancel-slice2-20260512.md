# Gateflow Re-review: engine-cancel-commit-boundary-and-tool-timeout / Slice 2

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `agent-tool-handshake-timeout`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice2-20260512.md`
- **Fix artifact**: `docs/reviews/gateflow-fix-engine-cancel-slice2-20260512.md`
- **Review scope**: 仅复核工具握手 timeout 判定后 late cancel 不得覆盖 `RUN_FAILED(tool_execution_timeout)`
- **Conclusion**: pass

当前 diff 已修复 review finding。工具握手 timeout 返回 `WaitTimedOut` 后，`_execute_tool_batch` 直接提交 `RUN_FAILED(tool_execution_timeout)` terminal，不再通过会重新检查 cancellation token 的 `_make_failed_or_cancelled_terminal_with_close(...)`。

## Finding 修复状态

### Finding 1: timeout 已判定后仍可能被工具取消清理阶段触发的 token 覆盖为 RUN_CANCELLED

- **Status**: fixed
- **Evidence**:
  - `dayu/engine/agent.py` 的 `WaitTimedOut` 分支现在直接 `yield self._make_terminal_failed(RunFailedData(...))`，不会再把 timeout 写入 `_last_tool_batch_result` 后交给外层 cancellation-priority helper。
  - `tests/engine/test_agent_phase3_tool_call.py` 新增 `test_tool_execution_timeout_wins_over_cleanup_cancel`，覆盖工具 task 响应 timeout cancel 时触发同一个 token，terminal 仍为 `RUN_FAILED` 且 error code 为 `tool_execution_timeout`。
  - happy-path timeout 测试仍覆盖 target task 被取消、context timeout 来自 policy、无 `TOOL_RESULT_ACCEPTED`、无下一轮 Runner。

## 验证命令

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`72 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## Residual Risk

- 本次未运行全量测试；按请求运行受影响测试、pyright 与 diff check。
- 本次是 re-review-only；未修改生产或测试实现。
