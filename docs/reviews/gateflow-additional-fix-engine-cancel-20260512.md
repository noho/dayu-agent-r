# Gateflow Additional Fix: engine-cancel-commit-boundary-and-tool-timeout

## 结论

- **Current gate**: user additional code review fix
- **Source decision artifact**: `docs/reviews/gateflow-additional-review-decision-engine-cancel-20260512.md`
- **Fix conclusion**: 已修复 controller accepted findings；rejected / deferred findings 未改实现。

## Accepted Finding Fix Status

### 0704-2 工具执行超时路径未显式关闭 Runner

- **Status**: fixed
- **Changed files**:
  - `dayu/engine/agent.py`
- **Fix**:
  - 新增 `_make_tool_timeout_terminal_with_close()`，timeout terminal path 先关闭 Runner，再提交 `RUN_FAILED(tool_execution_timeout)`。
  - 该 helper 不重新检查 cancellation，避免 timeout 已判定后被 late cancel 覆盖。

### 0704-3 cancellation commit boundary 缺少代码注释

- **Status**: fixed
- **Changed files**:
  - `dayu/engine/agent.py`
- **Fix**:
  - 在 ordinary iteration / force-answer 的 `done_seen` guard、final terminal helper 和 suspended terminal helper 处补充 commit boundary 注释。
  - `_make_suspended_terminal_with_close` docstring 明确：`ToolAwaitingOutcome` 已返回后，`await_spec` / `snapshot` 是已接受恢复事实，迟到取消不覆盖 `RUN_SUSPENDED`。

### 0701-2 timeout 语义重复定义于 `AgentPolicy` 与 `ToolExecutionContext`

- **Status**: fixed
- **Changed files**:
  - `dayu/engine/contracts/agent_policy.py`
  - `dayu/contracts/tool_call.py`
  - `dayu/engine/README.md`
- **Fix**:
  - 明确 `AgentPolicy.tool_execution_timeout_seconds` 是 Engine 工具握手 timeout 真源。
  - `ToolExecutionContext.timeout_seconds` 改写为该真源在本次工具调用上的预算投影，不是第二真源。

### 0701-4 `ToolAwaitSpec.resume_token` 安全模型未文档化

- **Status**: fixed
- **Changed files**:
  - `dayu/contracts/tool_await.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
- **Fix**:
  - `resume_token` docstring 明确为 Host-owned opaque reference，Engine 只透传，不解析、不签发、不当作授权凭据或 payload。
  - 增加基础校验：非空、长度上限。
  - 增加 invalid resume token 测试。

### 0701-5 `ToolExecutor.execute` 内部抛出 `asyncio.CancelledError` 绕过 Agent 错误处理

- **Status**: fixed
- **Changed files**:
  - `dayu/engine/agent.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
- **Fix**:
  - 新增 `_call_tool_executor()` 包裹 ToolExecutor 调用。
  - 当 run-local cancellation token 未取消而 executor 自身抛出 `asyncio.CancelledError` 时，归一为 `ToolFailedOutcome(tool_executor_exception)`。
  - token 已取消时仍透传取消，让等待 helper 收口为 `WaitCancelled`。
  - 增加 executor 内部 `asyncio.CancelledError` 回归测试。

### 0701-6 runtime helper pre-cancel 行为不对称

- **Status**: fixed
- **Changed files**:
  - `dayu/runtime/cancellation.py`
  - `tests/runtime/test_cancellation.py`
- **Fix**:
  - `await_or_cancel` 在 token 预取消且传入已创建 Task 时，与 `await_or_cancel_or_timeout` 一样取消并等待 target 收口。
  - 增加 pre-cancel + Task 输入测试。

### 0701-7 `ToolAwaitSnapshot` 语义不清

- **Status**: fixed
- **Changed files**:
  - `dayu/contracts/tool_await.py`
- **Fix**:
  - docstring 明确 `ToolAwaitSnapshot` 是 Host / ToolRuntime 持有的 opaque snapshot reference；Engine 不提供检索机制，也不承载业务状态或属性袋。

### 0701-8 多工具批次首个工具挂起测试缺口

- **Status**: fixed
- **Changed files**:
  - `tests/engine/test_agent_phase3_tool_call.py`
- **Fix**:
  - `test_tool_awaiting_suspends_run_without_next_tool_injection` 改为同一 iteration 两个 tool calls。
  - 断言首个工具返回 awaiting 后只执行第一个工具，第二个工具不会被调用。

## Rejected / Deferred Findings

- `0704-1`: rejected-with-reason。timeout 分支已胜出后，target cleanup 触发的 cancellation 是 late cancel，不能覆盖 timeout；保留 timeout 前 re-check，不做 cleanup 后覆盖。
- `0701-1`: rejected-with-reason。`ToolAwaitingOutcome` 已返回后，late cancel 不覆盖 `RUN_SUSPENDED`，该语义已写入 docstring。
- `0701-3`: deferred-with-owner，后续 Host resume / run recovery work unit。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`74 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## Residual Risk

- 全量测试尚未在本 fix pass 后运行；当前已运行 runtime cancellation 与 Engine Phase 2/3 受影响测试。
- `AgentPolicy.tool_execution_timeout_seconds` 上限、历史 artifact 旧术语、`RunSuspendedData.reason` enum 化均已在 decision artifact 中 deferred-with-owner。
