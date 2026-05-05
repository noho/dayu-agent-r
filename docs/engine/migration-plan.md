# Engine 迁移总控计划

## 1. 计划状态

本计划是 Engine 迁移讨论稿，用于指导后续多个迁移 Agent 分阶段实施。它不是实现文档，不包含生产代码，也不代表可以立即进入迁移。

实施顺序必须是：

1. 本计划提交 review。
2. review Agent 审查通过。
3. 总控 Agent 检查阶段成果。
4. 用户确认。
5. 才能进入对应 Phase 的实现、测试、README 同步和 GitHub PR 流程。

任何 Phase 在实现中发现设计边界不成立、需要新增公共契约、需要触碰 Host / capability / fins 具体实现，必须停止当前实现，回到设计讨论或拆分新 issue。

## 2. 依据

本计划依据以下材料：

- `docs/engine/design.md`
- `docs/engine/review.md`
- GitHub issue #2：`https://github.com/noho/dayu-agent-r/issues/2`
- `AGENTS.md`

其中 `docs/engine/design.md` 是 Engine 接口设计依据，`docs/engine/review.md` 已确认该设计可进入迁移计划阶段。OLD 仓库只作为源码证据来源和有价值 implementation 片段来源，不作为 NEW 架构、目录边界或公共接口的真源。

## 3. 总体原则

- NEW 是全新架构，不为 OLD 路径、OLD 接口、OLD 测试保留兼容 wrapper / facade / re-export。
- OLD 只能提供直接源码证据和可复用 implementation 片段；禁止机械搬迁 OLD 架构、旧接口、旧目录边界或历史包袱。
- Dayu 是宿主强约束下的 `LLM in the loop`，不是 `LLM on the loop`。
- 分层固定为 `UI -> Service -> Host -> Engine`。
- Host 是 Engine 生命周期、取消、治理的强约束真源；具体覆盖 Engine 内部 Agent / AsyncAgent / AsyncOpenAIRunner 的创建、关闭、取消观察与运行治理，以及 Host 侧 ToolRegistry / ToolRuntime、长事务等待与恢复。
- Engine 只消费 Host 注入的 run 输入、RunnerSpec、tool schema 快照、ToolExecutor protocol 和 cancellation token。
- Engine 不反向依赖 Host / Service / UI 的具体实现。
- Engine 不注册工具、不持有 ToolRegistry、不执行权限审计、不写 transcript、不写 trace store、不实现 conversation memory。
- Runner 只负责 provider 请求、响应流归一、usage、错误分类、资源关闭和取消观察；Runner 不执行工具。
- Agent 是 Engine 内部推理循环实现；Host 稳定依赖函数式入口和 contracts，不依赖具体 `AsyncAgent` 类。
- EngineEvent 是 Engine -> Host 的唯一观测边界；显式契约事实必须进入强类型 data，不得塞进 metadata。
- ToolExecutor 是 Host 与 Engine 围绕 tool calling 的最小协议，只暴露 `execute(request) -> ToolExecutionOutcome`。
- 第一阶段 ToolExecutionOutcome 只落地 `completed | failed | awaiting`。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 在 Engine / Host 公共边界不可见。
- 财报文档存取必须且只能通过 `dayu.fins.storage` 下的仓储协议与仓储实现完成。
- 禁止使用 `Any`、`object`、无类型参数、无类型返回值逃避严格类型设计。
- 每个实现切片都必须先有接口测试和架构测试，再迁实现。

## 4. 阶段总览

| Phase | 名称 | 目标 | 输入 | 输出 | 禁止事项 | 验收信号 |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 0 | pure contracts 与 import boundary tests | 先落地 Engine 最小稳定 contract 和包边界测试 | `design.md` 第 9、14、16 节，`review.md` 通过结论 | 强类型 contracts、包根导出约束、import boundary tests | 不迁 `AsyncAgent`、`AsyncOpenAIRunner`、ToolRegistry、doc/web/fins tools | contracts 可被测试导入；架构测试能阻止旧 re-export 和反向依赖 |
| Phase 1 | Runner protocol 与 OpenAI-compatible Runner | 迁移 provider 协议归一能力，Runner 只产出 RunnerEvent | Phase 0 contracts，OLD `async_openai_runner.py` 可复用片段 | `AsyncRunner` protocol 当前实现、RunnerEvent 流、RunnerSpec provider extension | 不迁 `AsyncCliRunner`，不迁 Runner 工具执行，不保留 `call(**extra_payloads)` | Runner 测试证明 tool call 只产生 RunnerEvent，不调用 ToolExecutor |
| Phase 2 | Agent run loop 骨架 | 建立 run-scoped Agent 和函数式入口 | Phase 0 contracts，Phase 1 Runner | `run_agent_messages` / `run_agent_and_wait` 骨架、RunnerEvent -> EngineEvent 提升、terminal 收口 | 不接入 ToolRegistry，不实现 long-running tool waiting，不迁 doc/web/fins 工具 | 无工具 run 可完成 final_answer / run_failed / run_cancelled，并关闭 Runner |
| Phase 3 | Host 注入 ToolExecutor 的 tool calling 闭环 | 建立普通工具调用闭环 | Phase 2 Agent loop，Phase 0 ToolExecutor contract | 模型 tool call -> ToolExecutionRequest -> ToolExecutionOutcome -> tool message 注入下一轮 | Engine 不注册工具，不执行权限、审计、路径白名单、长事务治理 | completed / failed 工具结果可进入下一轮；无双执行、无事件驱动工具执行 |
| Phase 4 | completed / failed / awaiting outcome | 落地三类 outcome，awaiting 只产出挂起事实 | Phase 3 tool loop，ToolAwaitSpec / ToolAwaitSnapshot | `tool_awaiting` / `run_suspended` 事件，awaiting outcome 穷尽匹配测试 | 不实现 approval、detached、retry_after、artifact_ready 等扩展 outcome | awaiting 不轮询、不 sleep、不创建 Host wait record；只结束本次 run |
| Phase 5 | context budget、continuation、取消收口 | 迁移确定性预算、续写、fallback、取消优先级 | Phase 2-4 Agent/Runner 主链路 | budget state、continuation/fallback 最小策略、取消 terminal 收口 | 不实现 conversation memory，不做语义压缩，不写 transcript | 取消优先于 final_answer；context_compaction_requested 只发事件 |
| Phase 6 | 文档同步与阶段收口 | 按实际代码同步 README 和计划状态 | Phase 0-5 已落地代码和测试 | `dayu/engine/README.md` 等必要 README，同步后的 docs 边界 | 不写未来设计进 README，不把 docs 草案当用户手册 | README 与当前代码一致；docs、测试、pyright、PR checklist 完整 |

## 5. Phase 0 详细计划

### 目标

落地 Engine pure contracts 与 import boundary tests。该阶段只建立公共契约和架构护栏，不迁移 Agent loop、Runner 实现、ToolRegistry 或任何工具。

### 前置条件

- `docs/engine/design.md` 已通过 review。
- 用户确认可以从计划阶段进入 Phase 0 实现。
- 当前仓库不存在必须保留的 OLD Engine 兼容入口要求。

### 迁移 Agent 任务

- 新建 Engine contract 模块，定义封闭强类型 `EngineEvent`、`RunnerEvent`、事件 data 类型、terminal event 类型。
- 定义 `ToolResultEnvelope`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolCallRequest`、`ToolExecutionRequest`、`ToolExecutionContext`、`ToolExecutionOutcome`。
- 定义收窄后的 `ToolExecutor` protocol，仅包含 `execute(request) -> ToolExecutionOutcome`。
- 定义 `AsyncRunner` protocol，只包含 `call(messages, options, tools)`、`is_supports_tool_calling()`、`close()`。
- 定义 `AgentRunRequest`、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、cancellation 观察原语。
- 建立 Engine 包根导出策略与测试；Phase 0 只允许导出 contract 类型，不导出未实现的 `run_agent_messages` / `run_agent_and_wait` 占位函数。
- 建立 import boundary tests，阻止 Engine 导入 Host 具体实现、ToolRegistry、web/doc/fins tools、ToolTraceRecorder、`dayu.fins.storage` 具体实现。
- 建立 weak typing tests 或 pyright 覆盖，阻止公共 contract 中出现 `Any`、`object`、无类型参数、无类型返回值。

### 允许复用的 OLD implementation 片段

- `dayu/engine/events.py` 的事件语义作为命名和场景证据。
- `dayu/engine/tool_result.py` 的工具结果信封字段语义。
- `dayu/contracts/protocols.py` 中 `ToolExecutionContext` 的 run / iteration / tool_call / timeout / cancellation 字段语义。
- `dayu/engine/cancellation.py` 的协作式取消思想。

### 禁止迁移项

- `AsyncAgent` 实现。
- `AsyncOpenAIRunner` 实现。
- `AsyncCliRunner`。
- ToolRegistry / ToolRuntime 具体实现。
- doc/web/fins tools。
- processors。
- ToolTraceRecorder / JsonlToolTraceStore。
- `dayu.engine.__init__` 旧 re-export。
- `StreamEvent(data: Any, metadata: dict)` 弱类型接口。

### 测试要求

- contract 类型导入测试。
- Engine 包根导出测试：Phase 0 若导出超出 contract 类型则测试失败；`run_agent_messages` / `run_agent_and_wait` 到 Phase 2 具备真实最小实现后才加入包根导出。
- import boundary 测试：Engine 不得导入 Host、Service、UI、Host ToolRegistry、web/doc/fins tools、ToolTraceRecorder、`dayu.fins.storage` 具体实现。
- 事件 data 封闭联合测试：新增 event type 必须有强类型 data。
- `ToolExecutionOutcome` 穷尽匹配测试：只允许 `completed | failed | awaiting`。
- metadata 边界测试：显式契约事实不得进入 metadata。

### pyright 要求

- Phase 0 完成后必须运行 pyright。
- 不允许新增、扩散、掩盖类型错误。
- 公共 contract 禁止 `Any`、`object`、无类型参数、无类型返回值。

### README / docs 同步要求

- 若新增 `dayu/engine/` contract 代码，应检查 `dayu/engine/README.md` 是否需要记录当前公共契约。
- README 命中触发条件时先检查职责范围；只有当前可用契约确实落地且属于 `dayu/engine/README.md` 职责范围时才更新，不做机械同步。
- 若仅添加测试和内部 contract 草案，可在 PR 说明中解释 README 不更新的原因。
- 不更新根 README 的用户手册内容，除非实际公共命令或用户入口变化。

### review Agent 审查重点

- contract 是否严格对应 `design.md` 的事件表和 outcome 设计。
- 是否出现旧 `StreamEvent`、`EventType` 兼容 re-export。
- ToolExecutor 是否只暴露 `execute`。
- Engine 包根是否过宽。
- 是否存在 Engine -> Host / tool / fins 的反向导入。
- 是否有 `Any`、`object`、裸 dict 等弱类型逃逸。

### 总控验收标准

- Phase 0 可独立形成 PR。
- PR 只包含 contracts、架构测试、必要 README/docs 同步。
- 测试和 pyright 通过。
- review Agent 未发现边界回退。

### 用户确认点

- 是否确认 Engine 包根导出集合。
- 是否确认 `correlation_id` 作为可选中性字段保留。
- 是否确认 Phase 1 可基于该 contract 真源继续。

## 6. Phase 1 详细计划

### 目标

迁移 OpenAI-compatible Runner 的模型协议归一能力。Runner 只负责 provider 请求、SSE/JSON 响应解析、usage、错误分类、资源关闭和取消观察，并只产出 RunnerEvent。

### 前置条件

- Phase 0 contracts 与 import boundary tests 已合并。
- `RunnerSpec`、`RunnerCallOptions`、`ToolSchema`、`RunnerEvent` 已成为代码真源。
- 用户确认进入 Runner 实现阶段。

### 迁移 Agent 任务

- 基于 `AsyncRunner` protocol 实现 OpenAI-compatible Runner。
- 将 OLD `call(**extra_payloads)` 重设为 `call(messages, options, tools)`。
- 将 provider、model、endpoint、headers、thinking/reasoning provider 参数放入 `RunnerSpec`。
- 将 temperature、max tokens、top_p、response format 等请求级参数放入 `RunnerCallOptions`。
- 迁移 SSE / non-stream JSON 解析、usage 采集、HTTP 错误分类、重试与 backoff 的有价值实现。
- 迁移 provider reasoning 内容归一逻辑，但输出必须是 `runner_reasoning_delta` 或 `runner_content_completed.reasoning_content`。
- Runner 在 HTTP 建连、响应读取、SSE chunk 等待、重试 sleep 边界观察 cancellation token。
- Runner 关闭时释放 HTTP session / stream / parser 资源。

### 允许复用的 OLD implementation 片段

- `async_openai_runner.py` 中 payload 构建、SSE / JSON 响应解析、usage 采集、HTTP 错误分类、重试策略。
- `sse_parser.py`、`reasoning_protocol.py`、`xml_extractor.py` 中 provider 协议归一片段。
- cancellation helper 的 await / cancel 竞争思想。

### 禁止迁移项

- `_emit_tool_batch`、`_run_tool_call` 等 Runner 执行工具职责。
- `set_tools`。
- `call(**extra_payloads)`。
- `AsyncCliRunner`。
- ToolExecutor 依赖。
- ToolRegistry 依赖。
- trace recorder 依赖。
- 直接读取 `llm_models.json`。

### 测试要求

- Runner protocol 实现测试。
- SSE content delta / reasoning delta / tool call delta / usage / runner_done 测试。
- non-stream JSON 响应测试。
- HTTP 错误分类和重试测试。
- cancellation 阻塞边界测试。
- close 资源释放测试。
- tool call 输出测试必须证明 Runner 只产出 RunnerEvent，不执行工具、不依赖 ToolExecutor。
- provider request extension 测试必须证明显式字段不进入 extra payload 袋子。

### pyright 要求

- Runner 公共签名和 provider extension 类型必须通过 pyright。
- 禁止用 `Any`、`object` 或裸 dict 表达 provider 公共 contract。
- 若内部必须处理 JSON，应使用严格 JSON value union 或私有 adapter 类型。

### README / docs 同步要求

- 若 `dayu/engine/` 新增当前 Runner 实现，应检查 `dayu/engine/README.md` 的 Runner 协议说明。
- 若涉及 Engine / Host 装配边界变化，应检查 `dayu/README.md` 是否属于职责范围。
- 不写尚未落地的 tool calling 或 Host 实现细节。

### review Agent 审查重点

- Runner 是否仍然只产出 RunnerEvent。
- 是否删除 `set_tools` 和 `call(**extra_payloads)` 弱入口。
- provider 私有参数是否只在 RunnerSpec / provider adapter 内部受控流动。
- 取消观察和资源关闭是否覆盖阻塞边界。
- 是否误迁 `AsyncCliRunner` 或工具执行代码。

### 总控验收标准

- Phase 1 可独立形成 PR。
- Runner tests、架构测试、pyright 通过。
- Runner 不导入 ToolExecutor、ToolRegistry、tools、Host、trace recorder。
- RunnerEvent 与 Phase 0 contract 完全一致。

### 用户确认点

- 是否接受首个 OpenAI-compatible Runner 的 provider extension 范围。
- 是否确认暂不迁 `AsyncCliRunner`。

## 7. Phase 2 详细计划

### 目标

建立 run-scoped Agent run loop 骨架与函数式入口。该阶段只实现无工具主链路：iteration、RunnerEvent -> EngineEvent 提升、terminal event 收口和资源关闭。

### 前置条件

- Phase 0 contracts 已合并。
- Phase 1 Runner 可被函数式入口创建或注入。
- Engine 包根导出规则已由测试保护。

### 迁移 Agent 任务

- 实现 `run_agent_messages(request)`，返回 `AsyncIterator[EngineEvent]`。
- 实现 `run_agent_and_wait(request)`，聚合事件流得到 `AgentRunResult`。
- 建立 run-scoped Agent 内部类或私有实现函数。
- 每次 run 创建新的 Agent 与 Runner，run 终态后关闭 Runner。
- 实现 iteration_started、runner_* event 提升、runner_usage_recorded、runner_done、final_answer、run_failed、run_cancelled。
- 实现 Agent 实例 fail-fast 并发保护。
- 实现 final_answer 前取消检查。
- 实现 basic max iteration / basic fallback / provider error 收口的最小骨架。

### 允许复用的 OLD implementation 片段

- `AsyncAgent.run_messages` 的 run-scoped finally 关闭 Runner 思路。
- `_acquire_run_slot` 的并发 fail-fast 思路。
- `_run_loop` 中 iteration 与 final_answer 收敛的场景判断，但必须拆分，不能照搬 God function。
- content_filter / length finish_reason 的场景证据。

### 禁止迁移项

- ToolRegistry。
- ToolExecutor tool calling 闭环。
- awaiting / long-running tool waiting。
- doc/web/fins tools。
- ToolTraceRecorder。
- transcript 持久化。
- conversation memory。
- 语义压缩。

### 测试要求

- 函数式入口导出测试。
- 无工具成功 run：RunnerEvent 提升为 EngineEvent 并产出 final_answer。
- provider error -> run_failed。
- cancellation token 已取消 -> run_cancelled，且不产出 final_answer。
- final_answer 前取消命中 -> run_cancelled 优先。
- Runner close 在 success / failure / cancellation 中都执行。
- event_id 幂等、sequence 单调、terminal event 唯一性测试。
- Agent 实例并发 fail-fast 测试。

### pyright 要求

- Agent loop 内部状态和事件提升必须有完整类型。
- 不允许用裸 dict 传递 EngineEvent data。
- 不允许为了简化聚合使用 `Any`。

### README / docs 同步要求

- 若函数式入口落地，应更新 `dayu/engine/README.md` 的公共入口和生命周期说明。
- 若包根导出实际变化，应更新对应 README 或在 PR 中说明不更新原因。

### review Agent 审查重点

- Host 是否只依赖函数式入口和 contracts。
- Agent 是否 run-scoped，不跨 run 持有状态。
- Runner 是否在所有终态关闭。
- 取消是否优先于 final_answer。
- 是否提前接入工具、trace、memory 或 Host 具体实现。

### 总控验收标准

- Phase 2 可独立形成 PR。
- 无工具 Agent loop 可运行、可测试、可取消、可失败收口。
- import boundary tests 继续通过。
- README 同步与当前代码一致。

### 用户确认点

- 是否接受函数式入口作为 Host 首选依赖表面。
- 是否确认 Phase 3 开始接入 Host 注入的 ToolExecutor。

## 8. Phase 3 详细计划

### 目标

建立 Host 注入 ToolExecutor 的普通 tool calling 闭环：模型 tool call -> ToolExecutionRequest -> ToolExecutionOutcome -> tool message 注入下一轮 Runner。

### 前置条件

- Phase 2 Agent loop 已合并。
- Phase 0 ToolExecutor、ToolExecutionRequest、ToolExecutionOutcome 已稳定。
- Runner 已能输出 runner_tool_call_delta / runner_tool_calls_completed 或等价 RunnerEvent。

### 迁移 Agent 任务

- Agent 将 Runner tool call 归一为 ToolCallRequest。
- Agent 发出 `tool_call_requested` EngineEvent，该事件只用于观测。
- Agent 构造 ToolExecutionRequest，补齐 `session_id`、`run_id`、`iteration_id`、`tool_call_id`、`index_in_iteration`、`cancellation_token`、可选 `correlation_id`。
- Agent 调用 Host 注入的 `tool_executor.execute(request)`。
- completed / failed outcome 返回后，Agent 发出 `tool_result_accepted`，并把 LLM-facing tool message 注入下一轮 Runner。
- 工具执行失败作为普通工具失败结果进入上下文，由模型继续恢复或解释。
- 保持 ToolSchema 快照来自 AgentRunRequest，不从 ToolExecutor 再读取 schema。

### 允许复用的 OLD implementation 片段

- OLD tool call ID、index、arguments 归一场景。
- OLD ToolResultEnvelope -> LLM-facing projection 的思路，但内部契约必须保持强类型。
- duplicate call guard 的场景证据，可作为后续 AgentPolicy 的实现素材。

### 禁止迁移项

- Engine 内 ToolRegistry。
- Engine 内工具注册、参数校验、权限、审计、路径白名单。
- Runner 执行工具。
- Host 根据 `tool_call_requested` 事件另行执行工具。
- `get_schemas()` / `get_tool_display_info()` 回到 ToolExecutor。
- long-running awaiting outcome 的完整治理。
- doc/web/fins 工具实现。

### 测试要求

- tool_schemas 只从 AgentRunRequest 进入 Runner。
- 模型 tool call 后只调用一次 `ToolExecutor.execute`。
- `tool_call_requested` 事件不触发第二套执行路径。
- completed outcome 注入下一轮 tool message。
- failed outcome 注入下一轮失败工具消息。
- ToolExecutionRequest 字段完整性测试。
- ToolExecutor 异常边界测试：若 Host executor 违反契约，应进入 run_failed 或协议错误，而不是裸异常泄漏。
- Runner 不依赖 ToolExecutor 的架构测试继续通过。

### pyright 要求

- ToolExecutionRequest、ToolResultEnvelope、ToolExecutionOutcome 必须为封闭强类型。
- tool arguments 若为 JSON，应使用严格 JSON value union，不得用 `Any`。

### README / docs 同步要求

- 更新 `dayu/engine/README.md` 的 tool calling 状态机。
- 不写 Host ToolRegistry 具体实现细节。
- 不写 doc/web/fins 工具使用手册。

### review Agent 审查重点

- 是否存在双执行风险。
- ToolExecutor 是否保持最小协议。
- Engine 是否仍不接触 ToolRegistry。
- tool_result_accepted 事件与 ToolResultEnvelope 是否强类型。
- 工具失败是否被误当 run_failed。

### 总控验收标准

- Phase 3 可独立形成 PR。
- completed / failed 普通工具闭环可运行。
- 架构测试继续阻止 ToolRegistry / tools 导入。
- review Agent 确认工具调用控制流单一。

### 用户确认点

- 是否确认普通工具失败进入 LLM 上下文，由模型恢复或解释。
- 是否确认 Phase 4 再处理 awaiting，不在 Phase 3 提前实现。

## 9. Phase 4 详细计划

### 目标

落地第一阶段三类 outcome 中的 `awaiting` 分支。awaiting 只表达 Host 托管等待事实，使本次 Engine run 产出 `tool_awaiting` / `run_suspended` 后停止。

### 前置条件

- Phase 3 tool calling 闭环已合并。
- `ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolAwaitingOutcome` 已在 Phase 0 contract 中定义。
- Host wait record / monitor / resume 具体实现尚未进入 Engine。

### 迁移 Agent 任务

- Agent 识别 `ToolAwaitingOutcome`。
- 发出 `tool_awaiting` EngineEvent，data 中包含 `await_spec` 和必要 tool_call 关联事实。
- 发出 `run_suspended` terminal event。
- 结束本次 run 并关闭 Runner。
- 确保 awaiting 不注入普通 tool message，除非设计明确提供 Host 恢复输入。
- 定义 Engine 恢复输入的最小 contract：Host 后续以新的 AgentRunRequest 提供权威消息或工具终态结果。

### 允许复用的 OLD implementation 片段

- OLD #142 相关动机只作为场景证据。
- OLD 工具结果信封可作为 completed / failed 语义素材。
- 不复用 OLD 中 LLM 轮询或 sleep 的实现。

### 禁止迁移项

- approval、detached、retry_after、input_required、artifact_ready、delegated、deduplicated 等扩展 outcome。
- Host wait record / monitor / resume 具体实现。
- Engine 轮询 job 状态。
- Engine sleep / backoff。
- Engine 写 transcript 或 task ledger。
- Engine 创建后台任务。

### 测试要求

- awaiting outcome -> `tool_awaiting` + `run_suspended`。
- `run_suspended` 是 terminal event，之后不产出 final_answer。
- awaiting 不导致 Engine 轮询或 sleep。
- Runner 在 suspended 后关闭。
- ToolAwaitSpec 不进入 ToolResultEnvelope.meta。
- 穷尽匹配测试证明新增 outcome 必须显式处理。

### pyright 要求

- `ToolAwaitSpec` 与 `ToolAwaitSnapshot` 严格类型化。
- 不用 `status: str` 加 payload 表达 awaiting。

### README / docs 同步要求

- 更新 `dayu/engine/README.md` 中 awaiting / suspended 状态机。
- 只写 Engine 当前行为，不写 Host monitor 实现细节。
- 在 docs 中保留 issue #4 作为扩展 outcome 追踪入口。

### review Agent 审查重点

- awaiting 是否只是治理事实，不包含业务语义。
- Engine 是否未实现 Host wait record / monitor / resume。
- 是否出现扩展 outcome 偷跑。
- suspended 是否正确作为 terminal event。

### 总控验收标准

- Phase 4 可独立形成 PR。
- awaiting 主链路可测试。
- 扩展 outcome 均未进入 Engine core。
- issue #4 仍作为扩展 outcome 总跟踪。

### 用户确认点

- 是否确认 awaiting 的恢复由后续 Host 迁移实现。
- 是否需要为某个扩展 outcome 单独开子 issue。

## 10. Phase 5 详细计划

### 目标

迁移确定性 context budget 原语、continuation / fallback 最小策略和取消收口规则。保证取消优先于 final_answer，Runner 阻塞边界和 Agent terminal 前都观察取消。

### 前置条件

- Phase 2 Agent loop 已合并。
- Phase 3 / 4 tool loop 和 awaiting 主链路已合并，或明确本 Phase 只覆盖无工具路径。
- Phase 0 cancellation 和 context budget contract 已稳定。

### 迁移 Agent 任务

- 实现 `ContextBudgetState` 等确定性预算状态。
- Engine 只实现待注入下一轮 LLM tool message 的确定性预算裁剪；工具级截断、fetch_more cursor、TTL、scope token 仍归 Host ToolRuntime，不进入 Engine。
- 实现 `context_compaction_requested` EngineEvent。
- 实现最小 continuation 策略，例如 finish_reason=length 的可控续写次数。
- 实现最小 fallback 策略，例如 content_filter / provider error 的结构化失败或降级。
- Agent 每轮 iteration 起点检查取消。
- Runner 阻塞边界观察取消。
- Agent 在提交 final_answer 前再次检查取消。
- 取消命中后产出 run_cancelled，不产出 final_answer。

### 允许复用的 OLD implementation 片段

- `context_budget.py` 的 ContextBudgetState / ToolResultBudgetCapper 思路。
- `truncation_manager.py` 中工具结果预算与 cursor 的场景证据，但工具级 truncation 归 Host。
- `_compact_messages` 只能作为 emergency deterministic fallback 素材，不作为稳定接口。
- `cancellation.py` 的 await_or_cancel 思路。
- `AsyncAgent._run_loop` 中 continuation / fallback 场景判断，必须拆分。

### 禁止迁移项

- conversation memory。
- 语义压缩。
- Engine 写 transcript。
- Engine 调用 LLM 做压缩摘要。
- Engine 理解 fins/doc/web 业务语义。
- ToolRuntime 工具级截断 / fetch_more 具体实现。
- watchdog、取消超时升级、lost 判定等取消治理增强；这些由 issue #3 跟踪。

### 测试要求

- budget soft / hard limit 状态测试。
- 工具结果注入前裁剪测试。
- context_compaction_requested 事件测试。
- continuation 次数限制测试。
- fallback terminal 测试。
- 取消优先级测试：取消与 final_answer 竞争时产出 run_cancelled。
- Runner 阻塞取消测试。
- Agent terminal 前取消检查测试。
- Engine 不写 transcript / memory 的架构测试。

### pyright 要求

- budget state、continuation policy、fallback policy 必须严格类型化。
- 不允许用字符串魔法值表达终态或 budget 状态；使用 enum / 封闭类型。

### README / docs 同步要求

- 更新 `dayu/engine/README.md` 的 context budget、continuation、cancel 状态机。
- 如果涉及分层边界，应检查 `dayu/README.md` 是否需要同步。
- 不把 conversation memory 或语义压缩写成 Engine 当前能力。

### review Agent 审查重点

- 取消是否绝对优先于 final_answer。
- Engine 是否只发 context_compaction_requested，不实现 memory。
- emergency fallback 是否没有成为稳定公共接口。
- continuation / fallback 是否受 AgentPolicy 控制。
- 是否把工具级截断误迁回 Engine。

### 总控验收标准

- Phase 5 可独立形成 PR；若依赖 Phase 3/4 场景，可在 PR 中明确覆盖路径。
- 取消、budget、continuation、fallback 测试通过。
- pyright 通过。
- README 与当前实现一致。

### 用户确认点

- 是否接受 OLD `_compact_messages` 仅作为 emergency fallback 素材。
- 是否需要将取消治理增强继续留在 issue #3，而不进入本 Phase。

## 11. Phase 6 详细计划

### 目标

完成 Engine 迁移阶段的文档同步、计划状态收口和 PR 验收整理。该阶段只同步已经落地的事实，不写未来设计。

### 前置条件

- Phase 0-5 的实现 PR 已合并，或至少明确哪些 Phase 已落地。
- 所有实现切片已通过 review Agent 和总控验收。

### 迁移 Agent 任务

- 根据当前代码更新 `dayu/engine/README.md`。
- 若涉及整体分层、装配方式或 Host / Engine 边界变化，检查并更新 `dayu/README.md`。
- 若新增测试分层、架构测试或运行约定，检查并更新 `tests/README.md`。
- 清理 docs 中已过时的草案表述，保留 design / migration-plan 作为历史设计与计划依据。
- 在 issue #2 汇总 Phase 完成状态和剩余 issue。

### 允许复用的 OLD implementation 片段

- 不适用。Phase 6 不迁实现代码。

### 禁止迁移项

- 不新增生产代码。
- 不新增未 review 的公共接口。
- 不把未来计划写进 README。
- 不把 Host / fins / capability 具体实现写进 Engine README。

### 测试要求

- 若只改文档，至少运行 markdown / diff check。
- 若 README 同步伴随代码收口，运行全量受影响测试和 pyright。
- 确认架构测试仍长期保留。

### pyright 要求

- 若 Phase 6 不改代码，可复用上一实现 Phase 的 pyright 结果；最终收口 PR 仍建议运行 pyright。

### README / docs 同步要求

- `dayu/engine/README.md` 只写 Engine 当前架构、公共契约、Runner/Agent 事件流、状态机、扩展点。
- 根 README 只在用户安装、配置、运行、CLI 或导航变化时更新。
- `dayu/README.md` 只在整体架构或分层边界实际变化时更新。
- `tests/README.md` 只在测试分层、运行方式、约定变化时更新。

### review Agent 审查重点

- README 是否写当前事实而不是未来设计。
- 是否残留 OLD 术语、旧路径、旧入口、旧架构表述。
- docs 是否与代码真源冲突。
- 是否漏掉触发规则要求的 README。

### 总控验收标准

- Phase 6 可独立形成文档 PR，也可作为最后实现 PR 的文档收口部分。
- README 与当前代码一致。
- issue #2 有阶段总结。
- 后续拆分 issue 明确。

### 用户确认点

- 是否确认 Engine 迁移阶段可以收口。
- 是否确认进入 Host / ToolRuntime / capability 后续迁移。

## 12. 跨阶段架构测试

以下测试必须长期保留，不得只在 Phase 0 临时存在：

- Engine 包根导出测试：Phase 0 只允许导出 contract 类型；Phase 2 之后只允许导出 `run_agent_messages`、`run_agent_and_wait` 和 contract 类型；额外导出实现类、兼容 wrapper、旧 re-export 时测试失败。
- import boundary 测试：Engine 不得导入 Host / Service / UI 具体实现。
- Tool boundary 测试：Engine 不得导入 Host ToolRegistry、ToolRuntime 具体实现、doc/web/fins tools。
- Fins boundary 测试：Engine 不得导入 `dayu.fins.storage` 具体实现；财报文档读取不能经 Engine 直连文件路径。
- Runner boundary 测试：Runner 不得依赖 ToolExecutor，不得执行工具。
- Trace boundary 测试：Engine 不得依赖 ToolTraceRecorder、JsonlToolTraceStore 或 trace schema 真源。
- Weak typing 测试：Engine 公共 contract 不得出现 `Any`、`object`、无类型参数、无类型返回值、开放 metadata 承载显式契约事实。
- Event contract 测试：EngineEvent / RunnerEvent 事件名和 data 类型必须封闭；新增事件必须新增强类型 data 和测试。
- Outcome 穷尽测试：`ToolExecutionOutcome` 新增分支必须触发穷尽匹配测试失败，直到实现明确处理。
- Terminal 唯一性测试：每个 run 只能有一个 terminal event，`final_answer`、`run_failed`、`run_cancelled`、`run_suspended` 互斥。
- Cancellation priority 测试：取消命中后不得继续产出 final_answer。
- Metadata 测试：usage、provider_request_id、raw_payload、protocol error 等显式事实必须在 data 中，不得进入 metadata。
- README 触发检查：修改 `dayu/engine/`、分层边界或测试约定时必须检查对应 README。

## 13. GitHub issue / PR 策略

- issue #2 作为 Engine 迁移总控 issue，记录设计、计划、review、总控验收和阶段进展。
- 每个 Phase 建议单独开子 issue，issue 标题格式建议为：`Engine Phase N: <名称>`。
- 每个 Phase 原则上单独 PR，除非 Phase 6 作为某个实现 PR 的文档收口部分；若合并多个 Phase，必须由总控和用户确认。
- 扩展 outcome 使用 issue #4 作为总跟踪，并为每个扩展分支单独开子 issue。
- 取消治理增强使用 issue #3 跟踪，不塞进 Engine 初始迁移。
- Host ToolRuntime / ToolRegistry 具体实现必须另开 Host 迁移 issue。
- web tools capability、doc tools capability、fins tools / fins storage 实现、processors 归属与迁移、trace observer / audit / metrics / alerting、conversation memory 与语义压缩都必须另开 issue。

每个 PR 合并前的验收顺序：

1. 迁移 Agent 完成实现、测试、pyright、README/docs 同步。
2. 迁移 Agent 在 PR / issue 中列出改动、验证、未覆盖风险。
3. review Agent 审查代码、测试和边界。
4. 总控 Agent 检查是否符合本计划和 issue 范围。
5. 用户确认。
6. 才能合并或进入下一 Phase。

## 14. 风险与停止条件

必须停止实现、回到设计讨论的情况：

- 需要新增或修改 Engine 公共 contract，但 design / migration-plan 未覆盖。
- 实现要求 Engine 导入 Host、Service、UI、ToolRegistry、doc/web/fins tools 或 trace recorder。
- Runner 需要执行工具或依赖 ToolExecutor。
- ToolExecutor 需要恢复 `get_schemas()`、`get_tool_display_info()` 或其它 Registry 能力。
- `ToolExecutionOutcome` 需要新增 `approval_required`、`detached`、`retry_after`、`artifact_ready` 等分支。
- awaiting 需要 Engine sleep、轮询、创建后台任务或写 wait record。
- context budget 需要语义压缩、conversation memory 或业务语义。
- 财报工具需要绕过 `dayu.fins.storage` 直接读文件。
- 为了让旧测试通过而需要兼容 wrapper / facade / re-export。
- 为了快速实现而出现 `Any`、`object`、裸 dict、开放 metadata 承载契约事实。
- README 要写“未来会支持”才能解释当前接口。

必须拆分新 issue 的情况：

- Host ToolRuntime / ToolRegistry 具体实现。
- web tools capability。
- doc tools capability。
- fins tools / fins storage 实现。
- processors 归属与迁移。
- approval / detached / retry_after / input_required / artifact_ready / delegated 等扩展 outcome。
- conversation memory 和语义压缩。
- trace observer / audit / metrics / alerting 的 Host 实现。
- watchdog、取消超时升级、lost 判定、强制终止等取消治理增强。

必须由用户或总控确认的情况：

- Phase 范围需要合并、拆分或跨层。
- Engine 包根导出集合需要变化。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 的最终归属需要定为 Fins capability、document capability 或独立 contract 包。
- `correlation_id` 语义需要从可选中性关联 ID 扩展。
- README 触发范围存在争议。
- 实现无法同时满足设计文档、review 结论和 `AGENTS.md`。

## 15. 下一步

下一步不是实现，而是 review 本计划。

建议 review Agent 重点审查：

- Phase 切片是否足够小，是否能独立 PR。
- 每个 Phase 的“不迁什么”是否明确。
- review 与总控验收标准是否能防止边界回退。
- 是否遗漏长期架构测试。
- 是否把 Host / capability / fins / trace / memory 的后续工作误塞进 Engine core。

本计划 review 通过、总控检查通过并经用户确认后，才能从 Phase 0 开始实施。
