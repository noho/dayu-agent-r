# Gateflow Additional Re-review: engine-cancel-commit-boundary-and-tool-timeout

## 结论

- **Current gate**: additional re-review
- **Branch**: `host/phase_0_design`
- **Review scope**: 当前未提交 diff；只复核 controller accepted findings 及其 fixes，并确认 rejected / deferred 裁决是否有证据支撑
- **Source review artifacts**:
  - `docs/reviews/code-review-20260512-0701.md`
  - `docs/reviews/code-review-20260512-0704.md`
- **Decision artifact**: `docs/reviews/gateflow-additional-review-decision-engine-cancel-20260512.md`
- **Fix artifact**: `docs/reviews/gateflow-additional-fix-engine-cancel-20260512.md`
- **Conclusion**: pass

所有 controller-accepted findings 均已修复；rejected / deferred findings 的裁决与当前 design、README、测试和代码事实一致。本轮未发现新的 blocker。

## Accepted Finding Re-review

### 0704-2 工具执行超时路径未显式关闭 Runner

- **Status**: fixed
- **Evidence**:
  - `dayu/engine/agent.py` 新增 `_make_tool_timeout_terminal_with_close()`，先 `await self._close_runner_once()`，再直接提交 `RUN_FAILED(tool_execution_timeout)`。
  - `WaitTimedOut` 分支调用该专用 helper，不走 `_make_failed_or_cancelled_terminal_with_close()`，因此 late cancel 不会覆盖 timeout terminal。
  - `test_tool_execution_timeout_wins_over_cleanup_cancel` 仍覆盖 cleanup cancel 不覆盖 timeout。

### 0704-3 cancellation commit boundary 缺少代码注释

- **Status**: fixed
- **Evidence**:
  - ordinary iteration 与 force-answer 的 `done_seen` guard 已补充 commit boundary 注释。
  - `_make_final_after_close()` 已注释 final decision 进入 terminal commit boundary 后 late cancel 不覆盖。
  - `_make_suspended_terminal_with_close()` docstring 与注释明确 `ToolAwaitingOutcome` 已返回后，`await_spec` / `snapshot` 是已接受恢复事实，late cancel 不覆盖 `RUN_SUSPENDED`。

### 0701-2 timeout 语义重复定义于 AgentPolicy 与 ToolExecutionContext

- **Status**: fixed
- **Evidence**:
  - `AgentPolicy.tool_execution_timeout_seconds` docstring 明确为工具握手 timeout 真源，且必须有限正数。
  - `ToolExecutionContext.timeout_seconds` docstring 改为 AgentPolicy 真源投影到本次工具调用的预算，供 ToolExecutor / ToolRuntime 协作设置内部超时；不再表述为第二真源。
  - `dayu/engine/README.md` 明确 `ToolExecutionContext.timeout_seconds` 不是第二真源。

### 0701-4 ToolAwaitSpec.resume_token 安全模型未文档化

- **Status**: fixed
- **Evidence**:
  - `ToolAwaitSpec.resume_token` docstring 明确为 Host-owned opaque reference；Engine 只透传，不解析、不签发、不视为授权凭据或可执行 payload。
  - `ToolAwaitSpec.__post_init__()` 校验空白 token 与超长 token。
  - `test_tool_await_spec_rejects_invalid_resume_token` 覆盖空字符串、空白字符串与超长 token。

### 0701-5 ToolExecutor.execute 内部抛 asyncio.CancelledError 绕过 Agent 错误处理

- **Status**: fixed
- **Evidence**:
  - `_execute_one_tool()` 改为等待 `_call_tool_executor(tool_request)`。
  - `_call_tool_executor()` 在 run-local token 未取消时把 executor 内部 `asyncio.CancelledError` 归一为 `ToolFailedOutcome(tool_executor_exception)`；token 已取消时继续透传，让等待 helper 收口为 cancellation。
  - `test_duplicate_and_executor_exception_paths` 新增 executor 内部 `asyncio.CancelledError` 分支，验证其作为工具失败注入 ToolMessage 后继续 Agent 流程。
  - 临时探针确认外层 task cancel 仍透传为 `asyncio.CancelledError`，未被 `_call_tool_executor()` 吞掉；token 已取消且 executor 抛 `CancelledError` 时收口为 `RUN_CANCELLED`。

### 0701-6 runtime helper pre-cancel 行为不对称

- **Status**: fixed
- **Evidence**:
  - `await_or_cancel()` 的 pre-cancel 分支现在与 `await_or_cancel_or_timeout()` 对齐：coroutine 输入直接 close；非 coroutine awaitable / Task 输入通过 `ensure_future()` 取得 target，并 `_cancel_task_and_wait()` 等待收口。
  - `test_await_or_cancel_closes_task_when_already_cancelled` 覆盖 pre-cancel + 已创建 Task，断言 task done / cancelled 且 target finally 已运行。
  - `await_or_cancel_or_timeout()` 的 timeout cleanup late cancel 语义未改，仍在 timeout 前 re-check token，不在 target cleanup 后用 late cancel 覆盖 timeout。

### 0701-7 ToolAwaitSnapshot 语义不清

- **Status**: fixed
- **Evidence**:
  - `ToolAwaitSnapshot` docstring 明确它是 Host / ToolRuntime 持有的 opaque snapshot reference。
  - 文档明确 Engine 只透传 `snapshot_id` 与采集时间，不提供检索机制，也不承载业务状态或任意属性袋。

### 0701-8 多工具批次首个工具挂起测试缺口

- **Status**: fixed
- **Evidence**:
  - `test_tool_awaiting_suspends_run_without_next_tool_injection` 改为同一 iteration 两个 tool calls。
  - 测试断言首个工具返回 awaiting 后只执行 `tc_1`，`tc_2` 未被调用；同时仍断言无 `TOOL_RESULT_ACCEPTED`、terminal 为 `RUN_SUSPENDED`、不进入下一轮 Runner。

## Rejected / Deferred Decision Re-review

### 0704-1 await_or_cancel_or_timeout timeout / cancellation TOCTOU

- **Decision review**: rejected-with-reason is supported
- **Evidence**:
  - 当前设计要求 timeout 已赢得 handshake race 后，target cleanup 阶段触发的 cancellation 属于 late cancel，不能覆盖 `RUN_FAILED(tool_execution_timeout)`。
  - `await_or_cancel_or_timeout()` 保留 timeout 前的 `token.is_cancelled()` re-check，用于吸收 watcher 轮询延迟；未增加 cleanup 后覆盖 timeout 的二次检查。
  - `test_tool_execution_timeout_wins_over_cleanup_cancel` 锁定该语义。

### 0701-1 _make_suspended_terminal_with_close 缺少 cancel 检查

- **Decision review**: rejected-with-reason is supported
- **Evidence**:
  - 当前 design / README 明确 `ToolAwaitingOutcome` 已返回后，Engine 先产出 `TOOL_AWAITING` 并收口 `RUN_SUSPENDED`；late cancel 不覆盖 `await_spec` / `snapshot`。
  - `_make_suspended_terminal_with_close()` docstring 已写明该 commit boundary。
  - `test_awaiting_cancellation_before_and_after_outcome_boundary` 覆盖 awaiting outcome 前取消仍赢、`TOOL_AWAITING` 事件后 late cancel 不覆盖 suspended。

### 0701-3 resume_hint=None 与 Runner close

- **Decision review**: deferred-with-owner is supported
- **Owner**: 后续 Host resume / run recovery work unit
- **Evidence**:
  - 当前已定稿恢复机制是不复用旧 Agent / Runner，由上层调用者保存 `await_spec` / `snapshot` 并构造新的 `AgentRunRequest` 恢复。
  - 直接删除或重构 `resume_hint` 属于独立 public contract change，超出当前 fix gate。

### Residual deferred findings

- **AgentPolicy.tool_execution_timeout_seconds 无上限**: deferred-with-owner is supported；属于后续配置治理 / Host policy validation work unit。
- **历史 plan/review 文档旧术语**: deferred-with-owner is supported；历史 artifact 不作为当前稳定文档真源。
- **RunSuspendedData.reason enum 化**: deferred-with-owner is supported；应在新增 suspend reason 时再评审。

## New Findings

- 无。

## 验证命令

- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - 结果：`74 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出
- 临时探针：outer task cancel during tool execution
  - 结果：`outer-cancel-propagated`
- 临时探针：token 已取消且 executor 抛 `asyncio.CancelledError`
  - 结果：terminal `run_cancelled`

## Residual Risk

- 本轮未运行全量测试；按 handoff 要求运行 runtime cancellation 与 Engine Phase 2 / Phase 3 受影响测试、pyright、diff check。
- 本轮是 additional re-review-only；未修改生产或测试实现。
