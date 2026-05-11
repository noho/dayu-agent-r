# Gateflow Additional Review Decision: engine-cancel-commit-boundary-and-tool-timeout

## 结论

- **Current gate**: user additional code review finding triage
- **Branch**: `host/phase_0_design`
- **Source artifacts**:
  - `docs/reviews/code-review-20260512-0701.md`
  - `docs/reviews/code-review-20260512-0704.md`
- **Controller conclusion**: 部分接受，部分拒绝，部分延后。只修复与当前已定稿 Engine timeout / cancellation commit boundary 直接相关、且不改变既定 public contract 方向的 findings。

## Finding Decisions

### 0704-1 await_or_cancel_or_timeout timeout / cancellation TOCTOU

- **Decision**: rejected-with-reason
- **Reason**: `asyncio.wait(..., timeout=...)` 返回 timeout 分支后，timeout 已赢得当前 handshake race；target cleanup 阶段触发的 token 属于 late cancel，不能覆盖 timeout。否则会重引入已修复的 Engine bug：`ToolExecutor.execute` timeout 被清理阶段 cancel 改写成 `run_cancelled`。当前实现已在 timeout 分支取消 target 前 re-check `token.is_cancelled()`，用于吸收 cancel watcher 轮询延迟；不再在 target cleanup 后二次覆盖 timeout。
- **Evidence**: `tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_cleanup_cancel` 锁定该语义。

### 0704-2 工具执行超时路径未显式关闭 Runner

- **Decision**: accepted with adjusted fix
- **Reason**: 显式关闭 Runner 可读性更好；但不能使用 `_make_failed_or_cancelled_terminal_with_close`，否则会重引入 timeout 已判定后被 late cancel 覆盖的问题。
- **Fix target**: 新增 timeout 专用 terminal helper：关闭 Runner 后直接提交 `RUN_FAILED(tool_execution_timeout)`，不重新检查 cancellation。

### 0704-3 cancellation commit boundary 缺少代码注释

- **Decision**: accepted
- **Reason**: `done_seen` guard、final commit 和 suspended commit 都是非直觉状态机不变量，缺少注释会诱导后续维护者把它“修回”旧语义。
- **Fix target**: `dayu/engine/agent.py`

### 0701-1 `_make_suspended_terminal_with_close` 缺少 cancel 检查

- **Decision**: rejected-with-reason
- **Reason**: 该 finding 的预期行为与已定稿设计冲突。当前设计是 `ToolAwaitingOutcome` 已返回后，Engine 必须先产出 `tool_awaiting` 并收口为 `run_suspended`；迟到 cancellation 不覆盖 `await_spec` / `snapshot`。取消要抢在 suspend 前，只能在 outcome 返回前生效。
- **Evidence**: `docs/engine/design.md` 的 Observable fact / cancellation 稳定规则；`dayu/engine/README.md` 关键机制；`tests/engine/test_agent_phase3_tool_call.py` 已覆盖 awaiting 前后 cancellation 边界。

### 0701-2 timeout 语义重复定义于 `AgentPolicy` 与 `ToolExecutionContext`

- **Decision**: accepted as documentation/ownership fix
- **Reason**: 真源应明确为 `AgentPolicy.tool_execution_timeout_seconds`；`ToolExecutionContext.timeout_seconds` 是 Engine 传递给 ToolExecutor 的本次调用预算投影，不是第二真源。
- **Fix target**: `dayu/engine/contracts/agent_policy.py`、`dayu/contracts/tool_call.py`、`dayu/engine/README.md`

### 0701-3 `resume_hint=None` 与 Runner close

- **Decision**: deferred-with-owner
- **Owner**: 后续 Host resume / run recovery work unit
- **Reason**: 当前已定稿恢复机制是不复用旧 Agent / Runner，由上层调用者构造新的 `AgentRunRequest` 显式恢复。`resume_hint` 当前不承载结构化恢复状态，直接删除或重构属于独立 public contract change。

### 0701-4 `ToolAwaitSpec.resume_token` 安全模型未文档化

- **Decision**: accepted
- **Reason**: `resume_token` 会穿过 EngineEvent / RunSuspendedData / EngineRunOutcomeSuspended，必须明确 opaque reference 语义，并做基础 fail-fast 校验。
- **Fix target**: `dayu/contracts/tool_await.py`、相关测试

### 0701-5 `ToolExecutor.execute` 内部抛出 `asyncio.CancelledError` 绕过 Agent 错误处理

- **Decision**: accepted
- **Reason**: ToolExecutor 公共协议不暴露取消异常；executor 自身在 token 未取消时抛出的 `asyncio.CancelledError` 应作为 executor 异常转成 tool failure。外层 task cancel 和 token cancellation 仍必须透传为 Engine cancellation。
- **Fix target**: `dayu/engine/agent.py`、`tests/engine/test_agent_phase3_tool_call.py`

### 0701-6 runtime helper pre-cancel 行为不对称

- **Decision**: accepted
- **Reason**: `await_or_cancel` 与 `await_or_cancel_or_timeout` 都声明拥有 awaitable；已取消 token + 已创建 Task 时应统一取消并等待 target 收口。
- **Fix target**: `dayu/runtime/cancellation.py`、`tests/runtime/test_cancellation.py`

### 0701-7 `ToolAwaitSnapshot` 语义不清

- **Decision**: accepted as documentation fix
- **Reason**: 当前 snapshot 是 Host-owned opaque snapshot reference；应明确 Engine 不提供检索机制，也不承载业务状态袋。
- **Fix target**: `dayu/contracts/tool_await.py`

### 0701-8 多工具批次首个工具挂起测试缺口

- **Decision**: accepted
- **Reason**: 当前状态机应在首个 awaiting outcome 后停止本次 run，不执行后续工具；需要测试锁定副作用边界。
- **Fix target**: `tests/engine/test_agent_phase3_tool_call.py`

## Residual Risk Classification

- `AgentPolicy.tool_execution_timeout_seconds` 无上限：deferred-with-owner，后续配置治理 / Host policy validation work unit。
- 历史 plan/review 文档旧术语：deferred-with-owner，历史 artifact 不作为当前稳定文档真源。
- `RunSuspendedData.reason` 自由字符串：deferred-with-owner，后续新增 suspend reason 时再评审是否改为 enum。
