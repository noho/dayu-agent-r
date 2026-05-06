# Phase 4 Awaiting / Run Suspended 计划

> 状态：已取消当前阶段独立实施，本文保留为历史草案。
>
> `suspend` / `run_suspended` / `ToolAwaitingOutcome` 后续由 GitHub issue #4 跟踪，并在 issue #4 下拆分子 issue 后重新计划与实施。本文不能作为当前实施 handoff prompt 使用。
>
> 后续重新启动该能力前，必须先在 issue #4 下明确 Host wait record、resume、monitor、EngineEvent 中性事实边界与治理策略，再生成新的 handoff 级计划。

本文档是 Phase 4 的 handoff 级实施计划。后续实施 Agent 应能按本文直接接手实现、测试、review 与验收。本文只规划 Phase 4，不实施代码。

当前总控定位：

- Phase 3 已完成普通 `completed` / `failed` tool calling 闭环、LLM-facing tool result projection、`max_iterations -> force-answer`、连续失败工具批次保护。
- Phase 4 只落地 `ToolAwaitingOutcome -> tool_awaiting -> run_suspended` 主链路。
- Phase 4 不实现 Host wait record、monitor、resume、RemoteProxy / RPC、HostEvent / WorkerEvent、ToolRegistry / ToolRuntime。

## 1. 动机

Phase 4 动机成立。

`ToolExecutionOutcome` 的第一阶段联合类型已经包含 `completed | failed | awaiting`。Phase 3 为了先完成普通工具闭环，把 `ToolAwaitingOutcome` 明确收口为 `run_failed("tool_awaiting_not_supported_in_phase3")`。这只是阶段性拒绝，不是最终语义。

Phase 4 要把 `awaiting` 从“协议已定义但 Agent 拒绝”推进到“Engine 可观测挂起事实”：

1. ToolExecutor 返回 `ToolAwaitingOutcome`。
2. Engine 发出 `tool_awaiting` 事件。
3. Engine 发出唯一 terminal：`run_suspended`。
4. 本次 run 停止，Runner 关闭。
5. 后续等待记录、监控、恢复由 Host / EngineWorker 后续阶段实现。

第一性原理判断：

- 长事务等待是 Host 托管治理事实，不是 Engine 内部后台任务。
- Engine 不应 sleep / poll / monitor 外部 job。
- Engine 必须把足够的强类型事实交给 Host observer，使后续 Host 能建立 wait record。
- Engine 挂起后不应继续调用 Runner，也不应把 incomplete tool batch 注入 LLM。

OLD 证据边界：

- OLD 没有 NEW 设计中的结构化 `ToolAwaitingOutcome` / `run_suspended` 主链路。
- OLD 可作为强参考的是工具结果注入、取消优先级、Runner close、Agent terminal 收口等可靠运行语义。
- Awaiting / suspended 是 NEW 架构明确新增的 Host 托管等待边界，不能机械寻找 OLD 等价实现。

## 2. 前置条件

实施前必须满足：

- Phase 3 PR 已合入 main。
- 当前实现中普通 tool calling 测试、Phase 3 code review、Phase 3 OLD/NEW review 均通过。
- 当前 contracts 已有：
  - `ToolAwaitKind`
  - `ToolAwaitSpec`
  - `ToolAwaitSnapshot`
  - `ToolAwaitingOutcome`
  - `ToolAwaitingData`
  - `RunSuspendedData`
  - `EngineRunOutcomeSuspended`
- `run_agent_messages` 当前能产出 `EngineEvent` 流。
- `run_agent_and_wait` 当前对 `RUN_SUSPENDED` 仍是 Phase 3 防御性失败，需要在 Phase 4 改为返回 suspended outcome。

若上述前置条件不成立，实施 Agent 必须停止并向总控汇报，不得在 Phase 4 里补做 Phase 3。

## 3. 明确目标

Phase 4 必须实现：

- Agent 识别 `ToolAwaitingOutcome`。
- Agent 产出 `tool_awaiting` EngineEvent。
- Agent 产出 `run_suspended` terminal EngineEvent。
- `run_suspended` 与 `final_answer` / `run_failed` / `run_cancelled` 互斥。
- `run_agent_and_wait` 对 `RUN_SUSPENDED` 返回 `EngineRunOutcomeSuspended`。
- Awaiting 命中后停止本次 run，不再调用 Runner。
- Awaiting 命中后关闭 Runner。
- Awaiting 不注入普通 LLM-facing tool message。
- Awaiting 不触发连续失败工具批次保护。
- Awaiting 不触发 max iteration force-answer。
- Awaiting 不被伪装成工具失败。
- Awaiting 不被伪装成 cancellation。

Phase 4 必须让 Host 后续可以从 EngineEvent 中拿到 wait record 所需的中性事实，但 Host wait record 本身不在本阶段实现。

## 4. 明确不做项

Phase 4 禁止实现：

- Host wait record。
- Host monitor。
- Host resume。
- RemoteProxy / RemoteStub / RPC。
- HostEvent / WorkerEvent。
- Host ToolRegistry。
- Host ToolRuntime。
- 权限、审计、路径白名单。
- 长事务 job 状态轮询。
- Engine sleep / backoff。
- Engine 后台任务。
- Engine 写 transcript / task ledger / trace store。
- conversation memory。
- context budget。
- continuation。
- broader fallback。
- fetch_more / truncation 可执行续读。
- Issue #10 provider-specific reasoning 写回优化。
- approval / detached / retry_after / input_required / artifact_ready / delegated / deduplicated 等扩展 outcome。

若实施中发现必须新增上述能力才能完成 Phase 4，说明当前边界不成立，必须停止并回到设计讨论。

## 5. 设计边界

### 5.1 分层边界

分层仍是：

```text
UI -> Service -> Host -> Engine
```

`EngineWorker` 是 Host capability，不是新业务层。

Local 形态：

```text
Host
  -> LocalProxy
      -> EngineWorker
          -> Engine
          -> local ToolExecutor
```

Remote 形态：

```text
Host
  -> RemoteProxy
      -> RemoteStub
          -> EngineWorker
              -> Engine
              -> remote ToolExecutor
```

Engine 只消费 `AgentRunRequest`、`ToolExecutor` protocol、`CancellationToken`、Runner contracts 与 Engine contracts。Engine 不知道 local / remote / proxy / stub / RPC。

### 5.2 Awaiting 语义

`ToolAwaitingOutcome` 表示：

- ToolExecutor 已接受工具调用。
- 该调用进入 Host 托管的外部长事务等待。
- 当前 Engine run 无法继续构造完整的 LLM tool message batch。
- Engine 必须停止本次 run，并把等待事实交给 Host observer。

`tool_awaiting` 是非 terminal 观测事件。

`run_suspended` 是 terminal 事件。

`run_suspended` 不是失败，也不是取消。它表达本次 run 已被 Engine 按协议挂起，后续恢复由 Host 用新的 run 输入完成。

### 5.3 Resume 输入边界

Phase 4 不实现 resume。

Phase 4 只保留以下恢复边界判断：

- Host 恢复时不复用旧 Agent / Runner 实例。
- Host 后续用新的 `AgentRunRequest` 恢复。
- 新的 `AgentRunRequest.messages` 是恢复时的权威上下文。
- Engine 不持久化旧消息历史。
- Engine 不读取 Host wait record。

待后续 Host phase 确认：

- Host 是直接构造已包含 assistant tool_calls 与 tool messages 的 `AgentRunRequest.messages`。
- 还是通过新增结构化 resume input 让 Engine 投影工具终态消息。

Phase 4 不新增 resume-specific public API。若实施 Agent 认为必须新增 `AgentResumeRequest` 或类似契约，必须停止并提交设计问题。

## 6. 文件级修改清单

### 6.1 预计需要修改的生产文件

- `dayu/engine/agent.py`
  - 将 Phase 3 的 awaiting 拒绝路径改为 `tool_awaiting` + `run_suspended`。
  - 调整工具批次执行顺序，确保 Host 可观察到当前 batch 的完整 tool call 事实。
  - 让 `run_agent_and_wait` 返回 `EngineRunOutcomeSuspended`。
  - 保证 suspended 后关闭 Runner。

- `dayu/engine/contracts/engine_events.py`
  - 扩展 `ToolAwaitingData`，使其包含 Host 建立 wait record 所需事实。
  - 如有必要，补充 docstring。

- `dayu/engine/contracts/agent_run.py`
  - 检查 `RunResumeHint` / `EngineRunOutcomeSuspended` 是否足够。
  - 如仅需 docstring 更新，保持字段最小化。

- `dayu/engine/contracts/__init__.py`
  - 若 contract 字段或类型发生变化，确认导出不漂移。

- `dayu/engine/__init__.py`
  - 若 contract 导出测试需要同步，按当前包根白名单更新。

- `dayu/engine/README.md`
  - Phase 4 实现后，当前 README 中 “awaiting / run_suspended 未落地” 的事实会过期，应更新为当前已实现行为。
  - 只写 Engine 当前行为，不写 Host wait record / monitor / resume 未来实现。

- `utils/smoke_async_agent_awaiting.py`
  - 新增 Phase 4 awaiting smoke 脚本。
  - 参考 `utils/smoke_async_agent_providers.py` / `utils/smoke_async_agent_tool_call.py` 的命令行形态、provider 配置读取、输出分段与 summary 格式。
  - 使用一个极小 command line tool 模拟 suspend / await：模型请求工具后，ToolExecutor 返回 `ToolAwaitingOutcome`，并在命令行提示用户输入；脚本随后打印用户输入代表的“外部长事务结果”，但 Phase 4 不把该结果恢复进 Engine。
  - smoke 只验证当前 run 产出 `tool_awaiting` 与 `run_suspended`，不实现 Host resume。

### 6.2 预计需要修改或新增的测试文件

- `tests/engine/test_agent_phase4_awaiting.py`
  - 建议新增 Phase 4 专项测试文件，避免继续膨胀 Phase 3 测试。

- `tests/engine/test_agent_phase3_tool_call.py`
  - 若 Phase 4 改变 tool call requested 事件顺序，需调整仍属于普通 completed / failed tool calling 的断言。
  - Phase 3 awaiting 拒绝测试应迁移或删除，不应继续期待 `tool_awaiting_not_supported_in_phase3`。

- `tests/engine/test_agent_phase2.py`
  - 目前 `run_agent_and_wait` 对 `RUN_SUSPENDED` 的防御性失败测试要更新为 Phase 4 行为，或迁移到 Phase 4 专项测试。

- `tests/engine/test_engine_event_contract.py`
  - 同步 `ToolAwaitingData` 字段断言。

- `tests/engine/test_package_exports.py`
  - 如导出集合变化，更新白名单。

- `tests/contracts/test_tool_outcome_exhaustive.py`
  - 应保持三分支穷尽匹配测试通过。

- `tests/README.md`
  - 更新测试分层说明，把 awaiting 从“拒绝路径”改为“suspended 主链路”。

## 7. 契约变化

### 7.1 ToolAwaitingData

当前 `ToolAwaitingData` 只有：

- `iteration_id`
- `tool_call_id`
- `await_spec`

Phase 4 应扩展为足够自描述的 wait fact：

- `iteration_id: str`
- `tool_call_id: str`
- `name: str`
- `index_in_iteration: int`
- `await_spec: ToolAwaitSpec`
- `snapshot: ToolAwaitSnapshot | None`

理由：

- Host observer 不应为了建立 wait record 反查或重放前序 `tool_call_requested`。
- `snapshot` 是 `ToolAwaitingOutcome` 的显式字段，不能丢失，也不能塞进 metadata。
- `name` / `index_in_iteration` 与 Phase 3 `ToolResultAcceptedData` 的自描述性保持一致。

禁止：

- 不把 `ToolAwaitSpec` 或 `ToolAwaitSnapshot` 放入 `ToolResultEnvelope.meta`。
- 不用 `status: str` + payload 表达 awaiting。
- 不通过 metadata 携带 `resume_token`、`snapshot_id`、`tool_call_id` 等显式事实。

### 7.2 RunSuspendedData

当前 `RunSuspendedData(reason: str, resume_hint: RunResumeHint | None)` 可以作为 Phase 4 最小 terminal data。

Phase 4 默认不扩字段，除非实施中证明 terminal 本身必须携带额外强事实。若要扩字段，必须先向总控汇报。

建议固定 reason 常量：

- `tool_awaiting`

不要在代码中散落魔法字符串。可在 `agent.py` 使用模块级私有常量。

`resume_hint` 默认可以为 `None`。若实现选择提供提示，应保持中性人类可读，不包含 Host 私有 wait record 结构，不泄漏业务工具细节。

### 7.3 EngineRunOutcomeSuspended

`run_agent_and_wait` 在看到 `EngineEventType.RUN_SUSPENDED` 且 data 为 `RunSuspendedData` 时，应返回：

- `EngineRunOutcomeSuspended(session_id, run_id, reason, resume_hint)`

Phase 4 应删除或更新 Phase 2/3 的 “unexpected_suspended_in_phase3” 防御性失败语义。

### 7.4 ToolAwaitSpec / ToolAwaitSnapshot

Phase 4 默认不扩展：

- `ToolAwaitKind.EXTERNAL_JOB`
- `ToolAwaitSpec(await_kind, deadline, resume_token)`
- `ToolAwaitSnapshot(snapshot_id, captured_at)`

如果实施 Agent 认为需要 `provider_job_id`、`poll_url`、`retry_after`、`artifact_id`、`approval_id` 等字段，必须停止。这些都是 Host ToolRuntime 或扩展 outcome 设计，不属于 Phase 4 Engine core。

## 8. Agent 状态机

### 8.1 当前 Phase 3 状态

Phase 3 工具分支当前语义：

1. Runner 产出 `RunnerToolCallsCompletedData`.
2. Agent 形成 tool call decision.
3. Agent 对每个 tool call 发出 `tool_call_requested`.
4. Agent 调用 `ToolExecutor.execute`.
5. `completed` / `failed` -> `tool_result_accepted`.
6. 全批次结束后注入 assistant tool_calls + tool messages.
7. 进入下一轮 Runner。
8. `awaiting` -> `run_failed("tool_awaiting_not_supported_in_phase3")`.

Phase 4 要替换第 8 点。

### 8.2 推荐执行顺序

为了支持 Host 后续建立 wait record，Phase 4 应考虑把一个 tool call batch 的观测和执行拆开：

1. 对当前 `decision.tool_calls` 按 `index_in_iteration` 稳定排序。
2. 在发出任何 `tool_call_requested` 前，对整个 batch 做 duplicate `tool_call_id` preflight：
   - 检查 batch 内重复。
   - 检查与当前 run 已处理过的 tool call id 重复。
   - 命中重复时不发 `tool_call_requested`、不执行工具、不发 `tool_awaiting`、不发 `tool_result_accepted`，只走唯一 terminal `run_failed("duplicate_tool_call_id")` 并关闭 Runner。
3. preflight 通过后，先为本批所有 tool call 发出 `tool_call_requested`。
4. 再按顺序调用 `ToolExecutor.execute`。
5. 每个 `completed` / `failed` 继续发出 `tool_result_accepted` 并记录 outcome。
6. 第一个 `awaiting` 出现时：
   - 发出 `tool_awaiting`。
   - 不执行本批后续尚未执行的 tool call。
   - 不注入 assistant tool_calls / tool messages。
   - 不进入下一轮 Runner。
   - 发出 `run_suspended` terminal。

这样即使第一项工具就 awaiting，Host 仍能从本批所有 `tool_call_requested` 观察到模型本轮请求的完整 assistant tool_calls 事实。后续 Host resume 设计可基于这些事实重建消息。

如果实施 Agent 认为“先全部 emit requested 再执行”会破坏 Phase 3 已确认边界，必须停止并提交替代方案。替代方案必须说明 Host 如何在 awaiting 时拿到完整 batch 的 tool call 事实。

### 8.3 Awaiting 命中后的行为

当 `ToolExecutor.execute` 返回 `ToolAwaitingOutcome`：

1. 若 cancellation 已命中，优先 `run_cancelled`。
2. 否则产出 `tool_awaiting`：
   - `iteration_id`
   - `tool_call_id`
   - `name`
   - `index_in_iteration`
   - `await_spec`
   - `snapshot`
3. 再次检查 cancellation。
4. 若 cancellation 未命中，产出 `run_suspended` terminal：
   - `reason="tool_awaiting"`
   - `resume_hint=None` 或中性提示。
5. 关闭 Runner。
6. 结束 async generator。

`tool_awaiting` 后不产出：

- `tool_result_accepted`
- `runner_done`
- `final_answer`
- `run_failed`
- 普通 tool message injection
- force-answer Runner call

除非 cancellation 在 `tool_awaiting` 和 terminal 之间命中；此时是否允许已经发出的 `tool_awaiting` 后跟 `run_cancelled` 需要实施前确认。推荐实现通过在发出 `tool_awaiting` 前后都检查 cancellation，尽量保证 terminal 仍唯一且语义清晰。

### 8.4 与连续失败批次保护的关系

`ToolAwaitingOutcome` 不是 failed outcome。

Awaiting 命中后本次 run 已 suspended，不应：

- 增加 `consecutive_failed_tool_batches`。
- 清零 `consecutive_failed_tool_batches`。
- 触发 `consecutive_failed_tool_batches` fallback。

如果一个批次先有 failed，再遇到 awaiting，最终仍以 awaiting 挂起，不触发失败批次 fallback。

### 8.5 与 max_iterations force-answer 的关系

Awaiting 优先于 max iteration force-answer。

若最后一个允许工具轮次中工具返回 awaiting：

- 不进入 force-answer。
- 不追加 fallback prompt。
- 不调用 Runner `tools=()`.
- 产出 `tool_awaiting` + `run_suspended`。

理由：等待型工具表示当前工具调用尚未得到终态结果，强行 force-answer 会让 LLM 在缺少工具终态时回答，破坏 Host 托管等待语义。

### 8.6 与 cancellation 的关系

取消优先级仍高于 suspended。

必须覆盖以下边界：

- 工具执行前已取消 -> `run_cancelled`。
- 工具执行过程中取消 -> `run_cancelled`，并取消 ToolExecutor awaitable。
- ToolExecutor 返回 awaiting 后、`tool_awaiting` 前取消 -> `run_cancelled`。
- `tool_awaiting` 已发出后、`run_suspended` 前取消：推荐尽量避免该竞态；若发生，terminal 必须唯一，优先 `run_cancelled`。

取消不能伪装成工具失败或 `run_suspended`。

## 9. Message / Resume 输入边界

### 9.1 Phase 4 不注入 tool messages

`awaiting` 表示工具还没有 LLM-facing 终态结果。Phase 4 不应给 Runner 注入：

- completed tool message
- failed tool message
- placeholder tool message
- partial tool message
- awaiting tool message

如果在 awaiting 前已有同批次工具 completed / failed，这些 accepted result 可以作为 EngineEvent 事实输出，但本次 run 仍不得注入任何 tool messages，因为 assistant tool_calls batch 未完整收口。

### 9.2 Host 后续恢复的最小事实

Phase 4 要保证 Host observer 至少能从事件流拿到：

- `session_id`
- `run_id`
- `iteration_id`
- 本批 tool calls 的 `tool_call_requested` 事实。
- awaiting tool 的 `tool_awaiting` 事实。
- `await_spec.resume_token`
- `snapshot`（如果有）
- `run_suspended` terminal。

这些事实足够 Host 后续建立 wait record。Host 具体如何恢复不在 Phase 4 实现。

### 9.3 待后续设计的恢复方式

后续 Host 恢复可能有两条路线：

- Host 构造完整 `AgentRunRequest.messages`，其中包含 assistant tool_calls 与全部 tool messages。
- Host 提供结构化工具终态结果，由 Engine 在新的 run 内构造 LLM-facing tool messages。

Phase 4 不选择最终路线，只需不把 Engine 设计死到必须复用旧 Agent / Runner。

## 10. 实现切片

### Slice A: Contract 自描述补齐

候选文件：

- `dayu/engine/contracts/engine_events.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`

任务：

- 扩展 `ToolAwaitingData` 字段。
- 更新中文 docstring。
- 更新 event data mapping 测试。
- 确保 metadata 不承载 awaiting 显式事实。

验收：

- 构造 `ToolAwaitingData` 必须显式提供 `name`、`index_in_iteration`、`snapshot`。
- 旧的三字段构造在测试中不再作为标准路径。

### Slice B: run_agent_and_wait suspended outcome

候选文件：

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase4_awaiting.py`
- `tests/engine/test_agent_phase2.py`

任务：

- 将 `RUN_SUSPENDED` terminal 映射为 `EngineRunOutcomeSuspended`。
- 删除或更新 `unexpected_suspended_in_phase3` 路径。

验收：

- `run_agent_and_wait` 收到 suspended terminal 返回 suspended outcome。
- `session_id` / `run_id` / `reason` / `resume_hint` 保持一致。

### Slice C: Agent awaiting 主链路

候选文件：

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase4_awaiting.py`

任务：

- 替换 Phase 3 的 `_ERROR_TOOL_AWAITING_NOT_SUPPORTED` 分支。
- 实现 `tool_awaiting` + `run_suspended`。
- 确保 Runner close。
- 确保 terminal 唯一。

验收：

- Awaiting 不产生 `run_failed`。
- Awaiting 不产生 `tool_result_accepted`。
- Awaiting 不注入 tool message。
- Awaiting 不触发下一轮 Runner。

### Slice D: Tool batch 完整观测

候选文件：

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase4_awaiting.py`
- 可能涉及 `tests/engine/test_agent_phase3_tool_call.py`

任务：

- 确认或调整 tool call batch 的 `tool_call_requested` 发出顺序。
- 目标是 awaiting 挂起时 Host 能观察到本批全部 tool calls。
- 在批量发出 `tool_call_requested` 前新增 duplicate `tool_call_id` preflight，避免非法 batch 污染 Host 可观察事件流。

验收：

- 两个 tool call 的 batch 中，第一个 awaiting 时，两个 `tool_call_requested` 都已产出。
- 第一个 awaiting 后，第二个 tool call 不执行。
- 同批或跨批重复 `tool_call_id` 时，不发出任何本批 `tool_call_requested`，不执行工具，并以 `run_failed("duplicate_tool_call_id")` 收口。
- 若调整事件顺序，普通 completed / failed 测试同步更新且语义不回退。

### Slice E: Cancellation priority

候选文件：

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase4_awaiting.py`

任务：

- 覆盖 awaiting 前、中、后的取消边界。
- 确保 cancellation terminal 仍唯一。

验收：

- 取消命中时 `run_cancelled` 胜出。
- 不出现 `run_cancelled` 与 `run_suspended` 双 terminal。

### Slice F: README / 测试文档同步

候选文件：

- `dayu/engine/README.md`
- `tests/README.md`

任务：

- `dayu/engine/README.md` 删除或改写 “awaiting / run_suspended 未落地”。
- 只写当前 Engine 行为：awaiting 产出 `tool_awaiting` + `run_suspended`，Host monitor / resume 不在 Engine。
- `tests/README.md` 把 awaiting 从拒绝路径更新为 suspended 主链路。

禁止：

- 不更新根 README。
- 不写 Host wait record、RemoteProxy、resume 已实现。
- 不写 Phase 5 context budget / continuation 能力。

### Slice G: Awaiting smoke 脚本

候选文件：

- `utils/smoke_async_agent_awaiting.py`

任务：

- 新增一个命令行 smoke，专门验证真实 provider 能把一个“需要外部输入”的工具调用带到 Engine suspended 边界。
- 工具建议命名为 `ask_user_echo` 或类似中性名称，schema 只表达“请求用户输入并回显该输入”。
- ToolExecutor 收到该工具调用后：
  - 输出模型请求的工具参数。
  - 在命令行读取用户输入。
  - 构造 `ToolAwaitingOutcome(await_spec=..., snapshot=...)` 返回给 Engine，使当前 run 进入 `tool_awaiting` + `run_suspended`。
  - 在脚本层打印用户输入作为模拟的外部长事务完成结果；不得在 Phase 4 内把它注入回 Engine 或伪造 resume。
- 输出风格对齐 `smoke_async_agent_providers.py`：
  - 支持固定 provider 集合。
  - 每个 provider 结束后输出空行。
  - 打印关键 EngineEvent，包括 `tool_call_requested`、`tool_awaiting`、`run_suspended`。
  - 最后输出 summary。

验收：

- smoke 可以用真实 provider 验证模型会触发 command line tool。
- 用户输入后，本次 Engine run 仍以 `run_suspended` 收口，而不是 `final_answer` / `run_failed`。
- smoke 明确声明“不测试 resume；用户输入只用于模拟外部长事务结果”。

## 11. 测试清单

新增 `tests/engine/test_agent_phase4_awaiting.py`，至少覆盖：

1. `ToolAwaitingOutcome` 产出 `tool_awaiting`。
2. `tool_awaiting` data 包含 `iteration_id`、`tool_call_id`、`name`、`index_in_iteration`、`await_spec`、`snapshot`。
3. `ToolAwaitingOutcome(snapshot=None)` 正常产出 `snapshot=None`。
4. `ToolAwaitingOutcome(snapshot=...)` 原样产出 snapshot。
5. `tool_awaiting` 后产出唯一 `run_suspended` terminal。
6. `run_suspended.data.reason == "tool_awaiting"`。
7. `run_agent_and_wait` 返回 `EngineRunOutcomeSuspended`。
8. Awaiting 不产出 `run_failed("tool_awaiting_not_supported_in_phase3")`。
9. Awaiting 不产出 `tool_result_accepted`。
10. Awaiting 不注入 LLM-facing tool message。
11. Awaiting 不触发下一轮 Runner。
12. Awaiting 后 Runner close 被调用。
13. Awaiting 不触发 max iteration force-answer。
14. Awaiting 不触发连续失败批次 fallback。
15. 同批次中 awaiting 前已有 failed outcome 时，仍以 `run_suspended` 收口。
16. 同批次中第一个 tool awaiting、第二个 tool 不执行。
17. 同批次所有 tool call 的 `tool_call_requested` 在 suspended 前可观察。
18. 工具执行前取消 -> `run_cancelled`。
19. 工具执行中取消 -> `run_cancelled`。
20. awaiting 返回后 terminal 前取消 -> terminal 唯一且取消优先。
21. `event_id` 唯一。
22. `sequence` 单调递增。
23. `session_id` / `run_id` 与 request 一致。
24. `run_suspended` 与 `final_answer` / `run_failed` / `run_cancelled` 互斥。
25. `ToolAwaitSpec` 不进入 `ToolResultEnvelope.meta`。
26. 同批重复 `tool_call_id` 时，duplicate preflight 在任何本批 `tool_call_requested` 前失败。
27. 跨批重复 `tool_call_id` 时，duplicate preflight 在任何本批 `tool_call_requested` 前失败。

更新既有测试：

- Phase 3 awaiting 拒绝测试改为 suspended 主链路，或移入 Phase 4 文件。
- `run_agent_and_wait_rejects_unexpected_suspended` 改为 suspended outcome 测试。
- import boundary tests 继续证明 Engine 不导入 Host / ToolRegistry / tools / fins。
- package exports tests 继续通过。
- Engine README tests 同步当前事实。

## 12. 验证命令

实施完成后至少运行：

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
```

```bash
source .venv/bin/activate && pyright
```

若测试拆分较大，实施中可先跑：

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase4_awaiting.py -q
```

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/test_agent_phase2.py tests/engine/test_engine_event_contract.py -q
```

手工 smoke 可在单测与 pyright 通过后运行：

```bash
source .venv/bin/activate && python utils/smoke_async_agent_awaiting.py
```

smoke 需要用户在命令行输入一段文本。脚本应输出各 provider 的 `tool_call_requested` / `tool_awaiting` / `run_suspended` 摘要和最终 summary。该 smoke 不属于自动测试，不要求覆盖率。

最终汇报必须写明完整命令与结果。

## 13. Review Gate

Phase 4 实施完成后必须进入以下 review gate：

1. **Phase 4 code review**
   - 输出到 `docs/engine/phase4-code-review.md`。
   - 按 code review 模式优先找 correctness / stability / architecture 问题。
   - 必须检查 review finding 修复后是否回写修复状态。

2. **OLD / NEW 开放式语义对比 review**
   - 输出到 `docs/engine/phase4-old-new-review.md`。
   - 不要机械限制 review Agent 只查本计划条目。
   - OLD 没有结构化 awaiting 主链路，因此对比重点是：
     - 取消优先级是否保持 OLD 可靠语义。
     - Runner close 是否保持 OLD 可靠语义。
     - 工具 batch / tool message 协议是否未破坏 Phase 3。
     - awaiting 是否未伪装成 completed / failed / cancellation。
   - 若 review Agent 发现本计划漏掉 OLD 可靠运行语义，必须先修计划或开 issue，再决定是否修代码。

3. **日常 code review**
   - 使用 `docs/code_review.md`。
   - 覆盖当前分支相对 main 的全部变更。

4. **总控验收**
   - 总控检查 diff、review 文档状态、测试结果、README 触发规则。
   - 用户确认后才 commit / push。

## 14. 停止条件

遇到以下任一情况，实施 Agent 必须停止并汇报：

- 需要 Engine 创建 wait record。
- 需要 Engine 轮询外部 job。
- 需要 Engine sleep / backoff 等待 job 状态。
- 需要 Engine 创建后台 task。
- 需要 Engine 读写 transcript / trace store / task ledger。
- 需要新增 HostEvent / WorkerEvent。
- 需要新增 RemoteProxy / RemoteStub / RPC。
- 需要 Engine 导入 Host / ToolRegistry / ToolRuntime / tools。
- 需要扩展 `ToolAwaitKind` 到 `EXTERNAL_JOB` 之外。
- 需要给 `ToolAwaitSpec` 增加业务字段或 provider 字段。
- 需要新增 resume-specific public API。
- 无法保证 `run_suspended` terminal 唯一。
- 无法解释 awaiting 时 Host 如何观察完整 tool call batch。
- 无法在批量 `tool_call_requested` 前完成 duplicate `tool_call_id` preflight。
- 发现 Phase 3 普通 completed / failed tool calling 因本改动回退。

停止后不要继续编码，不要用兼容 wrapper 或 metadata 绕过契约。

## 15. 风险

### 15.1 Tool batch 完整性风险

OpenAI-compatible 协议要求 assistant tool_calls 与后续 tool messages 配对完整。Awaiting 时本次 run 不注入 tool messages，因此 Host 后续恢复必须能拿到完整 tool call batch 事实。

缓解：

- Phase 4 要让 `tool_call_requested` 对本批所有 tool call 可观察。
- `tool_awaiting` 自身要足够自描述。
- 后续 Host resume 设计必须基于这些事件事实。

### 15.2 Resume 设计未定风险

Phase 4 不实现 resume，但如果事件事实不足，后续 Host 会被迫依赖 Engine 内部状态。

缓解：

- 不复用旧 Agent / Runner。
- 不要求 Engine 保存历史。
- 通过 EngineEvent 输出必要中性事实。
- 将恢复输入路线列为总控/用户确认点。

### 15.3 与 cancellation 竞争风险

ToolExecutor 返回 awaiting 与 Host cancellation 可能接近同时发生。

缓解：

- awaiting 前后都检查 cancellation。
- terminal 唯一。
- cancellation 优先于 suspended。

### 15.4 过度实现 Host 治理风险

Awaiting 很容易诱导实现 wait record、monitor、polling。

缓解：

- 本计划把这些列为停止条件。
- review gate 必须专门检查 Engine 是否偷跑 Host 能力。

## 16. 总控 / 用户待确认

实施前建议确认：

1. 是否同意 Phase 4 扩展 `ToolAwaitingData` 为：
   - `iteration_id`
   - `tool_call_id`
   - `name`
   - `index_in_iteration`
   - `await_spec`
   - `snapshot`

2. 是否同意 Phase 4 调整 tool batch 事件顺序为：
   - 先完成 duplicate `tool_call_id` preflight
   - 先发出本批所有 `tool_call_requested`
   - 再按序执行工具
   - awaiting 后停止执行后续工具

3. 是否同意 `RunSuspendedData.reason` 第一版固定为 `"tool_awaiting"`，`resume_hint` 默认为 `None`。

4. 是否确认 Phase 4 不选择最终 resume API，只保证 Host 后续可基于 EngineEvent 与新的 `AgentRunRequest` 恢复。

5. 是否需要为后续 Host resume 输入路线单独开 issue。

6. 是否需要为扩展 outcome（approval、retry_after、artifact_ready 等）继续挂在 issue #4 下，不进入 Phase 4。

7. 是否同意新增 `utils/smoke_async_agent_awaiting.py`，使用 command line tool 读取用户输入并以 `ToolAwaitingOutcome` 模拟 suspend / await；该 smoke 只验证 suspended 边界，不实现 resume。

## 17. 实施完成汇报格式

实施 Agent 完成后必须汇报：

- 改了哪些文件。
- 哪些 Phase 4 能力已实现。
- 哪些非目标明确未做。
- Awaiting 状态机如何保证 terminal 唯一。
- Host 后续可从哪些事件字段建立 wait record。
- 运行了哪些测试和 pyright，结果如何。
- 是否运行 `utils/smoke_async_agent_awaiting.py`，覆盖了哪些 provider，summary 如何。
- README 触发判断和实际修改范围。
- 剩余风险或待确认项。

不得 commit、不得 push，等待总控安排 review。
