# Gateflow Plan Re-review: engine-cancel-commit-boundary-and-tool-timeout

## Review Scope

- **Review gate**: plan re-review
- **Reviewed target**: `docs/reviews/gateflow-plan-engine-cancel-commit-boundary-20260511.md`
- **Source review artifact**: `docs/reviews/gateflow-plan-review-engine-cancel-commit-boundary-20260511.md`
- **Fix artifact**: `docs/reviews/gateflow-plan-fix-engine-cancel-commit-boundary-20260511.md`
- **Scope**: only re-review source review accepted findings 001-004.
- **Conclusion**: fail
- **Artifact path**: `docs/reviews/gateflow-plan-re-review-engine-cancel-commit-boundary-20260511.md`

本 re-review 只检查四个已接受 plan review findings 的修复状态；不修改 plan、不进入 implementation、commit、PR 或 closeout。

## Finding Status

### 001-fixed-ToolMessage 注入 ownership

- **Source finding**: Slice 3 把 ToolMessage 注入放进错误 ownership，实施者必须重新设计调用图。
- **Re-review status**: fixed.
- **Evidence**:
  - Fixed plan `5.5 Cancellation Commit Boundary` 已把 completed / failed outcome 的后续处理明确放到 outer `run_messages`：`docs/reviews/gateflow-plan-engine-cancel-commit-boundary-20260511.md:187` 写明 outer `run_messages` 根据 completed batch 调用 `_inject_tool_messages(...)`，随后观察取消。
  - Slice 3 exact changes 明确 `_execute_tool_batch` 不持有 `messages`、不负责注入 ToolMessage、不新增 `messages` 参数，并要求 `run_messages` 读取 `_last_tool_batch_result` 后调用 `_inject_tool_messages(...)`，见 fixed plan `:353-357`。
  - 当前代码事实支持该 ownership：`dayu/engine/agent.py:656-660` 是 outer `run_messages` 调用 `_inject_tool_messages(...)`；`dayu/engine/agent.py:1464-1470` 显示该函数需要 `messages` 参数；`dayu/engine/agent.py:1280-1420` 的 `_execute_tool_batch` 只执行工具、emit 工具事件并记录 batch result。
- **Result**: 原 finding 的 material implementation choice 已收敛。

### 002-fixed-runtime timeout helper bounded/no-background semantics

- **Source finding**: runtime timeout helper 的 bounded handshake 与“等待 target done”语义未收敛。
- **Re-review status**: fixed.
- **Evidence**:
  - Fixed plan `5.3 Runtime Wait Contract` 明确 helper 拥有 awaitable，timeout / cancellation 后取消 target task 并等待 task done，见 fixed plan `:149-157`。
  - 同一节明确选择 no-background-task ownership，并把非协作 executor 定义为协议违约：`ToolExecutor.execute` 必须协作 task cancellation，不得吞掉 `asyncio.CancelledError` 后无限运行，见 fixed plan `:156-157`。
  - Slice 1 test plan 增加 timeout 后 target task 被取消并收口、target 内部收到 `asyncio.CancelledError` 的测试要求，见 fixed plan `:228-233`。
  - Slice 2 要求更新 `ToolExecutor.execute` docstring：Engine-enforced timeout / cancellation 通过 coroutine task cancellation 终止等待，executor 必须协作 `asyncio.CancelledError`，见 fixed plan `:289-290`。
- **Result**: Plan 已选择 finding 建议中的 no-background-task 方案，并把协作取消前提、docstring 和测试验收写清。

### 003-partially-fixed-late cancel ToolMessage 注入测试策略

- **Source finding**: late cancel 后 ToolMessage 注入测试方案诱导私有 monkeypatch，但可观察契约没有收敛。
- **Re-review status**: partially-fixed.
- **Fixed evidence**:
  - Slice 3 tests 已把 late cancel 场景验收降到稳定可观察契约：`TOOL_RESULT_ACCEPTED` 已 emit、terminal 为 `RUN_CANCELLED`、不进入下一轮 Runner，见 fixed plan `:388-396`。
  - 同一测试段明确禁止为证明内部 list append 而新增 public API、monkeypatch `_inject_tool_messages` 或读取 `_last_tool_batch_result`，见 fixed plan `:392`。
  - ToolMessage projection 内容改由正常 completed / failed 下一轮测试覆盖，见 fixed plan `:393`。
- **Remaining blocker evidence**:
  - Fixed plan 的 residual risk section 仍保留旧指导：“late cancel 场景如无法进入第二轮 Runner，应选择低侵入断言 `_last_tool_batch_result` 或私有方法局部 monkeypatch”，见 fixed plan `9. Risks And Residual Risks` 中的 `Risk: accepted ToolMessage 注入难以直接观察`。
  - 该残留文字与 Slice 3 tests 的禁止项直接冲突，且正是 source finding 003 要求移除的诱导路径。它会让 implementation agent 在 plan 后部读到相反指令，继续可能使用私有状态或 monkeypatch 来证明 late cancel 内部注入。
- **Result**: 主测试验收已修正，但 fixed plan 仍存在直接相关的冲突性 residual risk 指令；finding 003 不能标记 fully fixed。

### 004-fixed-docs sync omissions

- **Source finding**: docs sync 只点名部分漂移，遗漏 AgentPolicy 与早期取消表述的稳定文档冲突。
- **Re-review status**: fixed.
- **Evidence**:
  - Slice 4 now requires updating `dayu/engine/README.md` cancellation text and documenting observable fact priority, final / suspended / tool result commit boundaries, timeout policy source and timeout failure semantics,见 fixed plan `:428-434`。
  - Slice 4 requires de-staling `docs/engine/design.md:341-355` early conflict text and updating AgentPolicy field list with `tool_execution_timeout_seconds`,见 fixed plan `:435-437`。
  - Completion signal now includes removal or qualification of old phrases such as “取消优先于挂起、最终回答” and “取消命中后不能继续产出 final_answer”, and requires timeout policy discoverability in README and design docs,见 fixed plan `:451-455`。
  - Current docs evidence confirms the targeted drift exists and is in scope: `docs/engine/design.md:161` still says cancellation cannot continue to `final_answer`; `docs/engine/design.md:754` omits timeout policy from AgentPolicy list; `dayu/engine/README.md:345` still says cancellation wins over suspend/final answer.
- **Result**: Plan now names the missing documentation drift and defines concrete doc validation criteria.

## Open Questions And Residual Risk

- No new unrelated findings were introduced.
- The only unresolved blocker is directly tied to accepted finding 003: the residual risk section contradicts the fixed late-cancel test strategy by retaining private monkeypatch / `_last_tool_batch_result` guidance.

## Final Re-review Conclusion

**fail**. Findings 001, 002 and 004 are fixed. Finding 003 is only partially fixed because the fixed plan still contains a directly conflicting residual-risk instruction that reintroduces the private monkeypatch / private state testing path the source review required removing.
