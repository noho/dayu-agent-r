# Gateflow Fix: engine-cancel-commit-boundary-and-tool-timeout / Slice 2

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `agent-tool-handshake-timeout`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice2-20260512.md`
- **Fix conclusion**: 接受并修复 review finding。

## Finding 处理

### Finding 1: timeout 已判定后仍可能被工具取消清理阶段触发的 token 覆盖为 RUN_CANCELLED

- **状态**: fixed
- **修复文件**:
  - `dayu/engine/agent.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
- **修复内容**:
  - `WaitTimedOut` 分支不再把 timeout 写成可被外层 cancellation helper 覆盖的失败候选。
  - 工具握手 timeout 已判定后，`_execute_tool_batch` 直接提交 `RUN_FAILED(tool_execution_timeout)` terminal。
  - 新增 `test_tool_execution_timeout_wins_over_cleanup_cancel`，覆盖工具 task 在响应 timeout cancel 的清理阶段触发同一个 cancellation token 时，terminal 仍为 `RUN_FAILED`。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`72 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## 残余风险

- 本 slice 只处理工具握手 timeout；更广义的 final / suspended / tool result accepted 后 late cancel commit boundary 属于后续 slice。
