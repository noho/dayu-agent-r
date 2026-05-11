# Gateflow Plan Review: engine-cancel-commit-boundary-and-tool-timeout

## Review Scope

- **Review gate**: plan review
- **Reviewed target**: `docs/reviews/gateflow-plan-engine-cancel-commit-boundary-20260511.md`
- **Reviewer posture**: evidence-based adversarial plan review
- **Conclusion**: fail
- **Artifact path**: `docs/reviews/gateflow-plan-review-engine-cancel-commit-boundary-20260511.md`

本 review 只审查 plan 是否 handoff-ready / code-generation-ready，不修改 plan、不进入 implementation、不裁决最终 Gateflow gate。

## Assumptions Tested

- 设计真源确实要求取消只阻止未来工作，不吞掉已接收/已接受 observable fact。
- `AgentPolicy.tool_execution_timeout_seconds` 作为必填字段的决策是否有直接设计依据，且修改面是否被 plan 正确圈定。
- runtime helper 是否仍保持 `dayu.runtime` 层中立，同时把 task ownership、timeout、取消优先级和 cleanup 语义说到可实现级别。
- Slice 3 的 final / awaiting / RunnerEvent delta / completed-failed tool outcome / force-answer commit boundary 是否覆盖完整。
- 测试计划是否能证明“先 accept/emit，再 cancel 只阻止未来工作”，且不会诱导 implementation agent 新增 public seam 或依赖脆弱私有 monkeypatch。
- docs sync 是否会清理当前 code/design drift，而不是只更新部分冲突文本。

## Findings

### 001-未修复-[高]-Slice 3 把 ToolMessage 注入放进错误 ownership，实施者必须重新设计调用图
- **Status**: accepted-candidate
- **位置**: Slice 3 `agent-cancellation-commit-boundary`，Exact changes 第 335-341 行。
- **问题类型**: 不可直接实施 / 状态机漏洞 / 切片过粗
- **当前写法**: plan 要求“修改 `_execute_tool_batch`”，在 completed/failed outcome 后先 emit `TOOL_RESULT_ACCEPTED`、append records，并且“工具批次结束后调用 `_inject_tool_messages(...)` 必须发生在取消检查前”。
- **反例/失败场景**: implementation agent 按 plan 在 `_execute_tool_batch` 内调用 `_inject_tool_messages(...)` 时会发现该函数没有 `messages` 入参，也不持有 run-local `messages` 列表；若自行给 `_execute_tool_batch` 加 `messages` 参数、迁移注入逻辑或改 outer loop sequencing，就已经在 plan 外重新设计 Agent 主循环边界。
- **为什么有问题**: 当前代码的 ownership 是 `_execute_tool_batch` 只执行工具并设置 `_last_tool_batch_result`，真正注入发生在 `run_messages` 读取 `batch_result` 后。plan 的目标“completed/failed outcome accepted 后注入，再观察取消”在当前调用图上应明确修改 `run_messages` 的取消检查与 `_execute_tool_batch` 的早退点，而不是笼统要求 `_execute_tool_batch` 注入消息。
- **直接证据**: plan 第 335-341 行；`dayu/engine/agent.py:1280-1432` 的 `_execute_tool_batch` 没有 `messages` 参数，只 append `records` 并设置 `_last_tool_batch_result`；`dayu/engine/agent.py:631-676` 才在 outer `run_messages` 中调用 `_inject_tool_messages(...)`，随后检查 `_is_cancelled()`；`dayu/engine/agent.py:1464-1503` 的 `_inject_tool_messages` 明确需要 `messages`。
- **影响**: 实施 Agent 跑偏 / 生成错误代码 / review 不可验收 / 后续返工。
- **建议改法和验证点**: plan 应把 completed/failed 路径拆成精确 call path：`_execute_tool_batch` 只删除 `WaitCompleted` 后、outcome 分类前的取消抢占，并保证返回 `_ToolBatchCompleted(records)`；`run_messages` 保持在 `_inject_tool_messages(...)` 之后观察取消并 terminal `RUN_CANCELLED`，不进入下一轮 Runner。若确实要把注入迁入 `_execute_tool_batch`，必须显式改变函数签名、messages ownership、测试边界和允许改动范围。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 002-未修复-[高]-runtime timeout helper 的 bounded handshake 与 “等待 target done” 语义未收敛
- **Status**: accepted-candidate
- **位置**: Public Contract / Runtime Wait Contract 第 124-149 行；Slice 1 runtime tests 第 217-224 行；Slice 2 timeout behavior 第 286-297 行。
- **问题类型**: 契约缺失 / 并发恢复风险 / 测试缺口
- **当前写法**: plan 要求新增 `await_or_cancel_or_timeout`，helper 拥有 awaitable；timeout 先到时取消 target task、等待 task done、返回 `WaitTimedOut`。同时目标称 `ToolExecutor.execute` 是 bounded handshake，timeout before outcome 必须收口为 `run_failed(tool_execution_timeout)`。
- **反例/失败场景**: `ToolExecutor.execute()` 在 timeout 后吞掉 `asyncio.CancelledError` 或进入长 cleanup，runtime helper 因“等待 task done”无限等待，Agent 既不返回 `WaitTimedOut`，也不产出 `run_failed(tool_execution_timeout)`。这样 timeout policy 存在但不再 bounded。
- **为什么有问题**: design 真源说 Engine 主动执行同一 timeout，timeout before outcome 时 Engine 取消 execute await task 并以不可恢复 failure 收口；discussion 也说 Engine handshake timeout 后 responsibility ends。plan 选择“不留下后台 target task”的 ownership 方向可以成立，但必须把前提写清楚：`ToolExecutor.execute` 必须对 task cancellation 协作，不得吞掉 `CancelledError` 后无限等待；否则 bounded handshake 目标无法由实现和测试证明。
- **直接证据**: plan 第 141-145 行；`docs/engine/design.md:526-533`；`docs/engine/cancel-suspend-boundary-discussion.md:120-138`；当前 `dayu/runtime/cancellation.py:207-223` 的 `_cancel_task_and_wait` 会等待 task 收口且吞掉异常；当前 `dayu/contracts/tool_executor.py:32-35` 只要求观察 `request.context.cancellation_token`，没有说明 Engine timeout 会通过 task cancellation 终止 execute，也没有禁止吞掉 `asyncio.CancelledError` 后继续运行。
- **影响**: 状态不一致 / 不可恢复 / review 不可验收 / 风险后移。
- **建议改法和验证点**: plan 应明确二选一：A. 维持 no-background-task ownership，并把 `ToolExecutor.execute` 的取消协作契约写入 docstring，要求 timeout task cancellation 必须可收口，测试覆盖 executor 收到 `CancelledError` 并确认 helper 返回；或 B. 定义 bounded cleanup grace / detach 语义，并说明 orphan control owner。当前 work unit 若不做 B，应把非协作 executor 明确列为协议违约和 residual risk，而不是让 “bounded timeout” 看起来无条件成立。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 003-未修复-[中]-late cancel 后 ToolMessage 注入测试方案诱导私有 monkeypatch，但可观察契约没有收敛
- **Status**: accepted-candidate
- **位置**: Slice 3 Tests / validation 第 372-377 行；Risks 第 468 行。
- **问题类型**: 测试缺口 / 不可直接实施 / 最佳实践偏离
- **当前写法**: plan 要求 completed/failed outcome returned 后证明 `tool_result_accepted + inject ToolMessage`，并建议通过 monkeypatch `_inject_tool_messages` 计数、检查 `_last_tool_batch_result` 或重构私有纯函数测试，同时又把“不得为了测试便利扩大 Engine 公共契约”列为 stop condition。
- **反例/失败场景**: late cancel 场景下 plan 同时要求不进入下一轮 Runner，因此现有 `_ScriptedRunner.messages_seen[1]` 这种公共-ish fake runner 观测点不可用；implementation agent 为了满足“确认注入已执行”很可能 monkeypatch 私有方法或读取私有 `_last_tool_batch_result`，测试绑定实现细节。后续只要 Agent 内部结构调整，测试会破碎，但并不能更强地证明 Host 可恢复事实。
- **为什么有问题**: 设计真源对调用者可见的恢复事实主要是 `tool_result_accepted` 事件与后续由调用方构造新 `AgentRunRequest.messages`；late cancel 后不进入下一轮 Runner，内部 ToolMessage 是否已经 append 到 run-local list 没有公共可观察出口。plan 需要先决定这是 public contract 还是 implementation invariant。若是 contract，应通过事件/结果可见事实证明；若只是内部 invariant，不应强迫 worker 用私有 monkeypatch 证明。
- **直接证据**: plan 第 372-377、395、468 行；当前测试 fake runner 只有下一轮调用时才记录 messages，见 `tests/engine/test_agent_phase3_tool_call.py:136-174`；正常 completed/failed 注入通过第二轮 `runner.messages_seen[1]` 断言，见 `tests/engine/test_agent_phase3_tool_call.py:760-795` 和 `:875-892`；当前 late cancel 测试断言不进入第二轮 Runner，见 `tests/engine/test_agent_phase3_tool_call.py:1581-1600`。
- **影响**: review 不可验收 / 实施 Agent 跑偏 / 后续返工。
- **建议改法和验证点**: plan 应把 late cancel 测试验收降到稳定可观察契约：`TOOL_RESULT_ACCEPTED` 已 emit、outcome projection 内容正确、terminal 为 `RUN_CANCELLED`、`runner.call_count == 1`、无下一轮 Runner。ToolMessage 注入本身继续由正常 completed/failed 下一轮测试覆盖。若 controller 坚持 late cancel 必须证明内部注入，应先在 plan 中批准一个不新增 public API 的具体测试策略，例如抽取模块级私有 projection helper 并只测试 projection，不 monkeypatch Agent 私有方法。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 004-未修复-[中]-docs sync 只点名部分漂移，遗漏 AgentPolicy 与早期取消表述的稳定文档冲突
- **Status**: accepted-candidate
- **位置**: Slice 4 `docs-sync-and-full-validation` 第 409-419 行。
- **问题类型**: 测试缺口 / 文档同步缺口 / 后续返工
- **当前写法**: plan 只明确更新 `dayu/engine/README.md:339-345`，以及 `docs/engine/design.md:341-355` 的早期冲突表述；同时说 `docs/engine/design.md:518-544` 已正确。
- **反例/失败场景**: 实现新增必填 `AgentPolicy.tool_execution_timeout_seconds` 后，`docs/engine/design.md` 中 AgentPolicy 字段建议仍只列 max iterations、continuation、fallback、tool calling 与 final filter；早期 cancellation 小节仍写“取消命中后不能继续产出 final_answer”。后续读者可能继续引用旧段落，而不是后面的稳定规则。
- **为什么有问题**: 本 work unit 改的是公共 contract 和状态机边界。README 触发规则要求 Engine README 只写当前接口、公共契约和状态机；design doc 如果保留同一文档内的新旧冲突，会让 implementation reviewer 难以判断真源。plan 的 docs sync 不足以清理 `AgentPolicy` 必填字段和 final commit boundary 的 drift。
- **直接证据**: plan 第 411-419 行；`docs/engine/design.md:157-162` 写“取消命中后不能继续产出 final_answer”；`docs/engine/design.md:748-754` 的 `AgentPolicy` 建议字段没有 timeout policy；`docs/engine/design.md:526-533` 又把 `AgentPolicy.tool_execution_timeout_seconds` 定为真源；`dayu/engine/README.md:339-345` 确实仍写取消优先于挂起、最终回答和失败候选。
- **影响**: 生成错误代码 / review 不可验收 / 后续返工。
- **建议改法和验证点**: Slice 4 应把 docs sync 验收改为基于术语搜索：清理或限定 `docs/engine/design.md` 中与稳定规则冲突的早期 cancellation 结论；更新 AgentPolicy 字段列表；保留 OLD 分析时必须标明“历史行为/已被稳定规则取代”。验证点包括 `rg` 检查不再出现“取消优先于挂起、最终回答”这类旧稳定口径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- `ToolExecutor.execute` 在 Engine-enforced timeout 后是否必须通过 `asyncio.CancelledError` 协作收口？如果是，应写入共享协议 docstring；如果不是，runtime helper 必须定义 cleanup grace / detach / orphan tracking owner。
- completed/failed late cancel 场景中，“ToolMessage 已注入 run-local context”是否是必须被测试证明的 public contract，还是仅由正常下一轮路径覆盖的内部 invariant？

## Residual Risks And Suggested Tracking

- `AgentPolicy.tool_execution_timeout_seconds` 必填字段本身有直接设计依据，当前代码事实显示构造点主要在 tests 与 `utils/smoke_async_agent_providers.py`；未发现需要阻塞该字段位置的证据。剩余风险是 docs 与所有构造点同步，建议留在当前 work unit 内修复。
- timeout 后工具侧真实工作停止仍不由 Engine 保证，这是设计已接受边界；建议在本 work unit 文档中明确 ToolRuntime / ToolExecutor owner，不扩成 Host orphan scanner 实现。

## Final Plan Review Conclusion

**fail**。目标与动机成立，但 plan 仍有 material implementation choices 未收敛：Slice 3 的 ToolMessage 注入 ownership 与当前调用图不匹配，runtime timeout helper 的 bounded/ownership 契约不够精确，测试方案会诱导私有 monkeypatch，docs sync 范围也不足。修复这些 finding 前，不建议交给 implementation agent。
