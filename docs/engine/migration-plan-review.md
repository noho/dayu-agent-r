# Engine 迁移总控计划 Review

## 1. Review 结论

有条件通过。

`docs/engine/migration-plan.md` 总体继承了 `docs/engine/design.md` 与 `docs/engine/review.md` 的核心结论：Phase 切片足够小，Phase 0 聚焦 pure contracts 与 import boundary tests，Runner 不执行工具，ToolRegistry / ToolRuntime 不进入 Engine，第一阶段 outcome 只落地 `completed | failed | awaiting`，processors/doc/web/fins/trace/memory 均被排除出 Engine core。当前未发现阻止计划继续进入下一步讨论的阻塞问题；但在进入 Phase 0 实施前，应先修正最新架构口径中的术语残留，以及 Phase 0 “函数式入口占位”的公共 API 风险。

## 2. 阅读范围

NEW 文档：

- `AGENTS.md`
- `docs/engine/design.md`
- `docs/engine/review.md`
- `docs/engine/migration-plan.md`

OLD 源码：

- 本轮未额外读取 OLD 源码文件。`docs/engine/design.md` 与 `docs/engine/review.md` 已列出并引用 OLD Engine / Fins 直接源码证据；本轮 review 只围绕迁移计划是否正确继承这些结论。

## 3. 阻塞问题

本轮未发现阻塞问题。

计划没有把 Host ToolRuntime / ToolRegistry 具体实现塞进 Engine core，没有让 Runner 执行工具或依赖 ToolExecutor，没有让 Engine 注册工具、写 trace store、写 transcript 或实现 conversation memory，也没有放开 `call(**extra_payloads)`、开放 metadata、`Any` / `object` 等弱类型边界。

## 4. 重要问题

### 4.1 最新架构口径中仍有 “Host 是 Agent ... 真源” 的术语残留

- 严重级别：重要
- 位置：`docs/engine/migration-plan.md` 第 3 节“总体原则”
- 问题说明：计划第 3 节写“Host 是 Agent / AsyncAgent / AsyncOpenAIRunner 生命周期、取消、治理、ToolRegistry / ToolRuntime、长事务等待与恢复的真源”。最新口径已统一为 `UI -> Service -> Host -> Engine`，Agent 只是 Engine 内部推理循环实现。虽然同节后面已经说明“Agent 是 Engine 内部推理循环实现”，但第一句话仍容易让迁移 Agent 把架构层级误读回 `Host -> Agent`。
- 为什么违反架构 / 流程 / 类型 / 测试原则：总控计划是后续多个迁移 Agent 的执行依据。架构层级术语若在最高原则中不统一，会在后续 PR、README、测试命名中扩散旧口径，尤其容易把 `AsyncAgent` 内部类误当成 Host 依赖的架构层。
- 建议修改方向：改为“Host 是 Engine 生命周期、取消、治理的强约束真源；具体覆盖 Engine 内部 Agent / AsyncAgent / AsyncOpenAIRunner 的创建、关闭、取消观察与运行治理，以及 Host 侧 ToolRegistry / ToolRuntime、长事务等待与恢复。”同时保留“Host 不依赖具体 `AsyncAgent` 类”的说明。

### 4.2 Phase 0 “函数式入口占位” 可能诱导未实现公共 API 先落地

- 严重级别：重要
- 位置：`docs/engine/migration-plan.md` 第 5 节“Phase 0 详细计划”、第 12 节“跨阶段架构测试”
- 问题说明：Phase 0 任务写“建立 Engine 包根导出清单，明确只导出函数式入口占位和 contract 类型”；第 12 节又写包根导出测试可约定只导出 `run_agent_messages`、`run_agent_and_wait` 和 contract 类型。Phase 0 的目标是 pure contracts 与 import boundary tests，明确不迁 `AsyncAgent`、`AsyncOpenAIRunner` 或函数式入口实现。若该阶段要求导出函数式入口“占位”，实现 Agent 可能会创建未实现的公共函数、抛 `NotImplementedError` 的 facade，或提前承诺还不能运行的 Host API。
- 为什么违反架构 / 流程 / 类型 / 测试原则：NEW 禁止兼容 wrapper / facade / re-export，也要求 README 只写当前事实。公共入口应在 Phase 2 run loop 骨架具备真实语义时落地；Phase 0 只能建立 contract 真源和包边界护栏。提前导出占位函数会让“当前可用 API”和“未来计划”混在一起，并降低包根导出测试的真实性。
- 建议修改方向：Phase 0 改为“建立 Engine 包根导出策略与测试，Phase 0 只允许导出 contract 类型；`run_agent_messages` / `run_agent_and_wait` 在 Phase 2 具备最小真实实现后加入包根导出”。第 12 节的长期架构测试可改为分阶段断言：Phase 0 断言只导出 contracts；Phase 2 之后断言只导出函数式入口和 contracts，额外实现类、兼容 wrapper、旧 re-export 均失败。

## 5. 建议问题

### 5.1 Phase 5 的工具结果预算裁剪表述可再收窄

- 严重级别：建议
- 位置：`docs/engine/migration-plan.md` 第 10 节“Phase 5 详细计划”
- 问题说明：Phase 5 写“实现工具结果注入前的确定性裁剪，若该职责仍位于 Engine；工具级截断仍归 Host ToolRuntime”。方向基本正确，但“若该职责仍位于 Engine”略显犹豫。
- 为什么违反架构 / 流程 / 类型 / 测试原则：设计文档已区分两类职责：工具级截断 / fetch_more 属于 Host ToolRuntime，Agent 上下文预算下的“即将注入下一轮 tool message”的确定性裁剪属于 Engine。计划中若语义不够清晰，后续实现可能把 Host 工具级截断误迁回 Engine，或反过来把 Engine 消息注入预算推给 Host。
- 建议修改方向：改为“Engine 只实现待注入下一轮 LLM tool message 的确定性预算裁剪；工具级截断、fetch_more cursor、TTL、scope token 仍归 Host ToolRuntime，不进入 Engine。”

### 5.2 Phase 0 的 README 规则可以更明确为“检查而非必改”

- 严重级别：建议
- 位置：`docs/engine/migration-plan.md` 第 5 节“README / docs 同步要求”
- 问题说明：计划已写“若新增 `dayu/engine/` contract 代码，应检查 `dayu/engine/README.md` 是否需要记录当前公共契约”，这是符合 `AGENTS.md` 的。为了避免 Phase 0 为纯 contract 草案写过多用户向文档，可再强调“命中触发条件先检查职责范围，不做机械同步”。
- 为什么违反架构 / 流程 / 类型 / 测试原则：README 应以当前代码为准，不应抢 design / plan 的职责。Phase 0 是 contract 和架构测试，README 若写成未来能力，会违反文档职责。
- 建议修改方向：保留检查项，并补一句“只有公共入口或当前可用契约确实落地且属于 `dayu/engine/README.md` 职责范围时才更新”。

## 6. 可接受风险

- Phase 1 先迁 OpenAI-compatible Runner：可接受。计划已明确不迁 `AsyncCliRunner`、不迁 Runner 工具执行、不保留 `call(**extra_payloads)`，并要求 Runner 测试证明 tool call 只产出 RunnerEvent。
- Phase 3 与 Phase 4 分开：可接受。普通 completed / failed tool loop 与 awaiting / suspended 主链路拆开，有利于避免 long-running tool governance 提前污染普通工具闭环。
- Phase 5 晚于 tool loop：可接受。context budget、continuation、fallback、取消收口会触及 Agent 主循环多个边界，放在普通 run loop 与 tool loop 后统一收口更可测。
- Host ToolRuntime / ToolRegistry、web/doc/fins capability、processors、trace observer、conversation memory 均另开 issue：可接受。计划已明确这些不进入 Engine core 初始迁移。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 最终归属未定：可接受。当前 Engine 计划只需保证它们不进入 Engine / Host 公共边界；最终归属留给 Fins / document capability 迁移确认。

## 7. 需要总控 / 用户确认的问题

- 是否接受在修正术语残留后，将总控口径统一为“Host 是 Engine 及其内部 Agent / Runner 生命周期、取消、治理真源”。
- 是否接受 Phase 0 不导出未实现的 `run_agent_messages` / `run_agent_and_wait` 占位函数，只落地 contract 类型和包根导出策略；函数式入口到 Phase 2 才以真实最小实现导出。
- 是否按当前计划进入 Phase 0：pure contracts、import boundary tests、包根导出策略、weak typing 防线；暂不迁 `AsyncAgent`、`AsyncOpenAIRunner`、ToolRegistry、doc/web/fins tools。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 的最终归属后续是否单独由 Fins capability、document capability 或独立 contract 包确认。

## 8. 总体验收判断

- 是否允许基于当前 `migration-plan.md` 进入 Phase 0 实施准备？有条件允许。
- 如果不允许，需要先修哪些章节？进入 Phase 0 前建议先修第 3 节的“Host 是 Agent ... 真源”术语残留，以及第 5 / 12 节中“函数式入口占位”的 Phase 0 导出策略。
- 如果允许，Phase 0 的最小执行范围是什么？只做 pure contracts 与 import boundary tests：封闭 `EngineEvent` / `RunnerEvent` 类型、`ToolResultEnvelope`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolCallRequest`、`ToolExecutionRequest`、收窄后的 `ToolExecutor` protocol、`AsyncRunner` protocol、cancellation 观察原语、Engine 包根 contract 导出策略和架构测试；不迁 `AsyncAgent`、`AsyncOpenAIRunner`、ToolRegistry、doc/web/fins tools，不导出未实现函数式入口占位。
