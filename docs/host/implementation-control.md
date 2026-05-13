# Host 实施总控

## 文档职责

本文档是 Host 设计与实施的总控文档，负责记录实施工作流、phase 编排、phase 进入 / 退出条件、交付物和验证要求。

本文档不承载新的架构决策，不替代设计文档，不作为实现细节说明书。

## 设计目标

Host 设计与实施必须始终服务于以下目标：

- 生产级买方财报分析 Agent。
- 范式是“宿主强约束下的 LLM in the loop”。
- 支持单机多客户端 / 多进程。
- 支持本地 Engine 和远程 Engine 并列执行。

任何 phase plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项设计或实现选择削弱这些目标，应停下来修正 `docs/host/design.md` 后再继续。

## 真源层级

Host 后续计划与实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、远程执行和关键治理路径

docs/host/implementation-control.md
  -> 实施编排文档
  -> 只记录 phases、依赖、进入 / 退出条件、交付物和验证要求
```

术语真源是 `dayu/README.md` 的术语表。phase discussion、phase plan、implementation、review、fix 与 re-review
必须使用该术语表中的定义；不得由 planning / implementation agent 自行重解释 `Session`、`Run`、`Attempt`、
`EventLog`、`USER_INPUT_ACCEPTED`、`EngineEvent stream`、`Host event stream`、`TruncationManager`、
`scope_token` 等术语。若发现术语缺失、冲突或不足以指导实施，应先和用户讨论，并同步更新 `dayu/README.md`
及对应设计文档，再继续推进。

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到 `docs/host/design.md`，再更新本文档的 phase 编排。

## 工作流

Host 实施采用以下工作流：

```text
draft design checkpoint
  -> update implementation-control.md phases
  -> select one phase
  -> discuss and refine the corresponding docs/host/design.md section with the user
  -> update docs/host/design.md if the phase discussion changes architecture
  -> generate handoff implementation-ready plan for that phase
  -> review plan
  -> user confirmation
  -> implement phase
  -> verify
  -> update related docs
```

每个 phase 单独生成 handoff implementation-ready plan。phase plan 必须基于：

- `docs/host/design.md`
- 本文档中对应 phase 的范围、依赖和退出条件

phase plan 不得从旧设计稿、旧代码路径或非真源文档推导架构边界。

每个 phase 的第一步必须是和用户讨论并细化 `docs/host/design.md` 中的对应章节。该讨论属于 `$gateflow` 的 feature
discussion / requirement clarification 阶段，必须在进入 plan gate 前完成。

phase discussion 至少需要确认：

- phase 目标与 success signal；
- 本 phase 是否服务于总控设计目标；
- 对应 `docs/host/design.md` 章节是否足够具体；
- 本 phase 的 scope boundary、non-goals 与 stop conditions；
- 是否存在会阻塞 handoff implementation-ready plan 的架构、状态机、公共接口、schema、持久化或测试问题。

如果 discussion 发现 `docs/host/design.md` 对应章节不足以支撑直接写 plan，应先更新 `docs/host/design.md`，再进入该 phase 的 plan。

## 仓库发布约定

Host 设计与实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

## Slice 切分原则

每个 phase 内的 implementation slices 在该 phase discussion / phase plan 阶段再具体确定；总控阶段不预先替各 phase 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿稳定模块 ownership、公共契约、状态机边界、存储边界或 projection 边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令和后续 slice 可依赖的稳定交付物。

如果一个 phase 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 phase plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，phase plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## Phase 条目模板

Phase Map 中每个 phase 必须使用统一条目格式。模板如下：

```md
### Phase N. 名称

目标：
- ...

对应设计章节：
- `docs/host/design.md` §...

前置条件：
- ...

进入条件：
- ...

范围：
- 允许修改：
- 禁止修改：

不做：
- ...

关键设计问题：
- 必须在 phase discussion 中确认：
- 若改变架构，先写回 `docs/host/design.md`：

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: ...
- Slice 2: ...

验证要求：
- unit tests:
- integration tests:
- pyright:
- docs:

退出条件：
- ...

后续依赖：
- 后续 phase 可依赖的稳定契约：
- 需要追踪到后续 phase 的事项：
```

字段含义：

- 目标：该 phase 完成后系统新增或稳定下来的能力。
- 对应设计章节：phase plan 的架构依据，只能引用 `docs/host/design.md` 和本文档，不得引用旧讨论稿。
- 前置条件：必须已经完成的 phase、前置修正或外部确认。
- 进入条件：开始该 phase discussion / plan 前必须满足的状态，例如设计章节已细化、无 blocking open question。
- 范围：允许修改和禁止修改的模块 / 文件 / 层级；用于防止 scope creep。
- 不做：明确排除的能力、兼容性、性能优化、远程能力或后续 phase 内容。
- 关键设计问题：phase 第一步必须和用户讨论确认的问题；若结果改变架构，先写回 `docs/host/design.md`。
- 交付物：该 phase 需要产出的设计细化、plan、代码、测试和文档。
- 建议 slice 切分：总控给初始建议，最终 slices 在 phase discussion / phase plan 中确定。
- 验证要求：该 phase 必须通过的测试、pyright、文档同步和必要的手工验证。
- 退出条件：phase 可以被认定完成的客观条件。
- 后续依赖：后续 phase 可以依赖的稳定契约，以及必须转交到后续 phase 的 tracking items。

## 强制约束

以下约束均来自 `docs/host/design.md` 与 `dayu/README.md` 的终态设计语义；本文档只作为实施护栏重复列出，不引入新的架构决策。

- Host 后续每个复杂 work unit、phase plan、public contract change、schema / storage change、state-machine change
  和 architecture-sensitive task 都必须遵循 `$gateflow` 工作流。
- `docs/host/design.md` 只写终态架构语义，不写 review 过程、用户确认过程、历史讨论、迁移痕迹、上一版对比或临时 open question。流程约束、裁决记录和追踪项分别写入本文档或 `docs/reviews/`。
- phase plan、implementation 或 fix 过程中如果需要修改 Engine 代码，必须立即停下来向用户确认。未经用户明确确认，
  不得把 Engine 代码修改夹带进 Host phase。
- phase plan、implementation 或 fix 不得让 Engine 理解 Host 状态、memory、guidance、steer、fetch_more 或 tool governance。
- phase plan、implementation 或 fix 不得让 EngineEvent `tool_awaiting` / `run_suspended` 创建 wait record、推进 Run
  `WAITING` 或关闭 Attempt；Tool Awaiting canonical owner 是 ToolRuntime Host accept path。
- phase plan、implementation 或 fix 不得把 Engine provider overflow / `context_compaction_requested` 当作 proactive
  context governance；proactive compaction 属于 Host Context Governance，Engine overflow 只是 reactive fallback。
- phase plan、implementation 或 fix 不得把 projection / timeline / audit / trace / outbox 当事实真源。
- phase plan、implementation 或 fix 不得把旧 Attempt resume / takeover 作为实现方案。
- phase plan、implementation 或 fix 不得让 RemoteStub / EngineWorker append EventLog、关闭 Attempt、更新 Run。
- phase plan、implementation 或 fix 不得引入重 lease / fencing 系统替代 admission + SQLite transaction + CAS。
- phase plan、implementation 或 fix 不得把 lane token、`dispatching`、`dispatcher_instance_id` 当作 Host truth、
  lease / fencing token 或 Attempt owner；lane 只能表达资源容量，不能替代 admission、事务、CAS 或 EventLog ordering。
- phase plan、implementation 或 fix 不得让远端 sequence、内存 notification 或 projection checkpoint 替代 Host 分配的全局 `event_sequence`。
- phase plan、implementation 或 fix 不得把 assistant final answer 自动升级为 verified fact。
- phase plan、implementation 或 fix 不得让 `fetch_more` 走 Host / Engine 特化分支。
- phase plan、implementation 或 fix 不得让 Host 包 import 具体业务工具模块、扫描业务工具或在 per-run request /
  metadata 中塞 raw `ToolBundle`；业务 `ToolBundle` 由外部装配作为 Host construction / composition root 输入。
- phase plan、implementation 或 fix 不得让 replay Attempt 暴露 tool schemas 或执行工具；Replay 是 no-tool 结构修复，
  ToolRuntime 拒绝 tool call 只是 defense-in-depth。
- phase plan、implementation 或 fix 不得把 `resolve_wait` 实现成长阻塞等待、轮询或持有外部 job 的循环；它只接收
  poll / callback / manual 已带回的结果，并通过短事务纳入 Host governance。
- phase plan、implementation 或 fix 不得把 memory projection lag 当作 Run recovery，也不得因此把 Run 推入
  `RECOVERING`。
- phase plan、implementation 或 fix 不得让 `purge_session` 删除 append-only audit JSONL；purge 必须保留 tombstone /
  audit record，并让 audit 查询能识别源 EventLog facts 已被 purge。
- phase plan、implementation 或 fix 不得把语义级重复工具调用治理放进 Engine；它属于 Host / ToolRuntime。
- phase plan、implementation 或 fix 不得让 sink 失败影响 EventLog append 或 Run terminal。
- phase 讨论、plan、implementation、review、fix 或 re-review 过程中出现 material open question 时，必须停下来和用户讨论；
  不得让 planning / implementation agent 自行选择会影响架构、公共接口、状态机、schema、持久化、并发、恢复、测试期望或用户可见行为的方案。
- 每个 phase 产生的潜在影响、未覆盖项、deferred risk、后续 phase 依赖和明确不做项，必须回写到本文档的追踪区；
  不得只保留在对话、临时 artifact 或 phase plan 中。

## Phase Map

Phase 按依赖关系推进：先实现被其它阶段依赖的公共契约、runtime 基础能力、durable store、EventLog 与状态机，再连接执行路径、工具治理、projection core、memory、context governance、recovery 与 remote。Audit、Tool Trace、Outbox 是独立 projection sinks，后置到核心治理路径稳定之后实现。Phase 0 是 Engine cleanup 前置 work unit，只阻塞 Phase 10 Context Governance，不阻塞 Phase 1-9。每个 phase 开始时仍必须先和用户讨论并细化对应 `docs/host/design.md` 章节，再生成 handoff implementation-ready plan。

### Phase 0. Engine Context Compaction Event 语义前置

目标：
- 清理 Engine context overflow / compaction event 语义，避免 Host implementation agent 把 Engine reactive fallback 误解为 proactive context governance。
- 本 phase 只阻塞 Phase 10 Context Governance / Compaction；不阻塞 Phase 1-9 的 Host foundational work。

对应设计章节：
- `dayu/engine/README.md`
- `docs/engine/design.md`
- `docs/host/design.md` §25 Context Governance
- `docs/host/design.md` §25.1 Compact Event 响应路径
- `docs/host/implementation-control.md` 追踪区 `Engine Context Compaction Event 语义前置`

前置条件：
- 用户明确确认允许修改 Engine 代码。

进入条件：
- 明确本 phase 只修正 Engine contract / README / tests，不把 context budget governance 放进 Engine。

范围：
- 允许修改：Engine context overflow event contract、Engine README、Engine design docs、相关 Engine tests。
- 禁止修改：Host 实施代码、Host compaction policy、Host recovery state machine。

不做：
- 不实现 Host Context Governance。
- 不实现 provider-specific tokenizer。
- 不做 Engine proactive compaction。

关键设计问题：
- 必须确认 `budget_state` unknown / optional 的最终表达。
- 若改变 EngineEvent 公共契约，先写回相关 Engine 文档。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Engine contract / dataclass / tests cleanup。
- Slice 2: Engine README / docs/engine/design.md / dayu/README.md 同步。

验证要求：
- unit tests: Engine context overflow event contract tests。
- integration tests: 现有 Engine context overflow 路径不回归。
- pyright: 全量或受影响包通过。
- docs: Engine README 与 design docs 同步。

退出条件：
- Engine overflow event 明确表达 reactive fallback 与 unknown budget，provider overflow path 使用 `budget_state=None`。

后续依赖：
- 后续 phase 可依赖的稳定契约：Engine 只发出 reactive overflow signal，不做 Host proactive compaction。
- 需要追踪到后续 phase 的事项：Phase 10. Context Governance / Compaction 必须使用 Host estimator / policy 自主判断 budget。

### Phase 1. 公共契约与 runtime 基础设施

目标：
- 建立 Host 后续实现依赖的稳定类型、公共 request / snapshot / enum、`dayu.runtime` 基础能力与工具 / 场景装配边界。

对应设计章节：
- `docs/host/design.md` §3 dayu.runtime
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `dayu/README.md` 术语约定与 Runtime

前置条件：
- `dayu/README.md` 术语真源已覆盖本 phase 引入的命名。

进入条件：
- 确认哪些类型属于 `dayu.contracts`，哪些类型留在 `dayu.host` 内部。

范围：
- 允许修改：公共契约、Host request / snapshot / error typing、`dayu.runtime.lane`、`dayu.runtime.filelock`、ToolsDiscovery / ScenePrepare 的层中立装配接口。
- 禁止修改：Host durable state machine、Engine 执行路径、业务财报工具实现。

不做：
- 不实现 SQLite store。
- 不实现 Host command path。
- 不实现业务工具扫描或财报场景 prompt。

关键设计问题：
- 必须确认 Host API 类型放置位置与 import 边界。
- 必须确认 `ToolBundle` 作为 Host construction input 的 typed options 形状。
- 若 runtime helper 需要第三方依赖，必须确认它仍满足 `dayu.runtime` 层中立约束。
- 必须按 slice 分别确认 public typing、runtime infra、ToolsDiscovery、ScenePrepare；任何一类出现重大架构分歧时，应拆出独立 phase。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Host API request / snapshot / error / status 类型。
- Slice 2: `dayu.runtime.lane` 与 `dayu.runtime.filelock`。
- Slice 3: ToolsDiscovery / ScenePrepare 层中立装配接口。

验证要求：
- unit tests: contract validation、runtime lane / filelock behavior。
- integration tests: 无。
- pyright: 相关包无新增错误。
- docs: `dayu/README.md` 与受影响包 README 同步。

退出条件：
- 后续 phase 可以只依赖 typed contract，不需要自行发明 request、snapshot、status、runtime helper 或工具装配入口。

后续依赖：
- 后续 phase 可依赖的稳定契约：Host public typing、runtime helper、ToolBundle construction input。
- 需要追踪到后续 phase 的事项：具体 Host store / command path 不在本 phase 落地；RunInputBuilder typed input provider protocols 在 Phase 5 建立，不在本 phase 落地，Phase 5 必须保持与本 phase 公共类型风格和 import boundary 一致。

### Phase 2. Durable Store / EventLog / Payload Foundation

目标：
- 建立 SQLite durable truth、EventLog append primitive、payload descriptor、idempotency record、host instance liveness 与事务边界。

对应设计章节：
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §13 EventLog
- `docs/host/design.md` §13.1 Payload 存储
- `docs/host/design.md` §27 Host Lifecycle / Recovery

前置条件：
- Phase 1 公共类型与 runtime helper 已完成。

进入条件：
- 确认第一版 SQLite schema convention、transaction runner、WAL / busy timeout、retry policy、payload threshold 与 artifact 目录注入方式；确认形式为用户确认，或 `docs/host/design.md` 对应章节已细化到可直接生成 schema / typed contract / test matrix。

范围：
- 允许修改：SQLite connection / transaction runner / WAL / busy timeout、schema bootstrap convention、EventLog table 与 appender / reader、payload table / descriptor table、idempotency table、host instance liveness foundation。
- 禁止修改：WorkerProxy、ToolRuntime、Projection、Memory、Remote transport。

不做：
- 不实现完整 Host API。
- 不 dispatch Engine。
- 不实现 projection sink。

关键设计问题：
- 必须确认 EventLog row、canonical event identity、event_sequence、payload descriptor 的 typed contract。
- 必须确认 SQLite 多进程写入配置和测试策略。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: SQLite schema convention / migration-free fresh DB bootstrap / transaction runner。
- Slice 2: EventLog append / read / event_sequence / idempotency primitive。
- Slice 3: payload descriptor / host instance liveness / diagnostics foundation。

验证要求：
- unit tests: transaction atomicity、event_sequence monotonicity、idempotency conflict。
- integration tests: SQLite WAL / busy timeout / concurrent append smoke。
- pyright: Host store 模块通过。
- docs: Host README 或开发说明按触发规则同步。

退出条件：
- 后续 phase 能在一个事务内 append canonical facts、更新 state indexes，并可用 EventLog cursor 补读；后续 phase 增加的 tables 必须遵守本 phase 的 schema convention、transaction discipline 与全新 schema 起库约束。

后续依赖：
- 后续 phase 可依赖的稳定契约：SQLite durable truth、schema convention、EventLog append / read、payload descriptor、idempotency primitive、host instance liveness。
- 需要追踪到后续 phase 的事项：Session / Run / Attempt tables 由 Phase 3 拥有，wait record table 由 Phase 7 拥有，projection / memory / context / audit / trace / outbox / purge tombstone tables 由各自 phase 拥有；projection 与 recovery 只消费本 phase 提供的 durable primitives。

### Phase 3. Session / Run / Attempt 状态机与 Admission

目标：
- 实现 Session slot、Session lifecycle、Run / Attempt lifecycle、admission、durable queue、promotion 与 CAS-style state transition。

对应设计章节：
- `docs/host/design.md` §5 Session 生命周期
- `docs/host/design.md` §6 Session Slot
- `docs/host/design.md` §7 Run 生命周期
- `docs/host/design.md` §8 Attempt 生命周期
- `docs/host/design.md` §9 Admission 与多进程并发
- `docs/host/design.md` §9.1 状态迁移契约

前置条件：
- Phase 2 durable store 与 EventLog foundation 已完成。

进入条件：
- 确认状态迁移表是否足够直接生成 typed transition service 与测试矩阵；确认形式为用户确认，或 `docs/host/design.md` 对应章节已细化到可直接生成 typed transition contract / test matrix。

范围：
- 允许修改：Session / Session slot tables、Run / Attempt tables、active index、queue index、transition service、admission service、promotion service。
- 禁止修改：Engine dispatch、ToolRuntime、Projection、Remote transport。

不做：
- 不启动 Engine。
- 不实现 public API 全量 facade。
- 不实现 recovery scan。

关键设计问题：
- 必须确认每个 transition 的前置状态、终态、canonical events 与同事务索引更新。
- 必须确认 queued Run 不占 active slot、promotion 触发点与多进程 CAS 语义。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Session / slot lifecycle 与 idempotency。
- Slice 2: Run / Attempt transition service 与 CAS tests。
- Slice 3: admission / durable queue / promotion。

验证要求：
- unit tests: state transition matrix。
- integration tests: 同 Session 并发 start / follow-up / queue promotion。
- pyright: Host state 模块通过。
- docs: Host README 按触发规则同步。

退出条件：
- Host 可以在不启动 Engine 的情况下正确接受、排队、启动、取消和终态收口 Run / Attempt state indexes。

后续依赖：
- 后续 phase 可依赖的稳定契约：active Run admission、durable queue、promotion、CAS transition service。
- 需要追踪到后续 phase 的事项：dispatch、worker event ingest、recovery 会复用本 phase 状态机。

### Phase 4. Host Public API Command Path

目标：
- 落地不依赖执行、等待或投影清理的函数式 Host command path、HostCallContext、OperationContext、幂等语义、snapshot 读取与 command path / background runtime facet 分离。

对应设计章节：
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §12 Follow-up 与 Steer
- `docs/host/design.md` §22 Cancel

前置条件：
- Phase 3 状态机、admission 与 durable store 已完成。

进入条件：
- 确认 API request / response / error shape 已足够实现多入口稳定边界。

范围：
- 允许修改：Host handle / factory、public API functions、HostCallContext validation、idempotency handling、SessionSnapshot / RunSnapshot / FollowupSnapshot / PurgeSessionResult。
- 禁止修改：Engine dispatch、ToolRuntime、Projection worker、Remote transport。

不做：
- 不实现 Engine execution。
- 不实现 UI / Service channel delivery。
- 不实现 wait adapter。
- 不实现 `resolve_wait` 的等待结果治理语义；该能力在 Phase 7 落地。
- 不实现 `purge_session` 的 destructive cleanup；该能力在 Phase 14 落地。

关键设计问题：
- 必须确认 `submit_followup(queue)` 如何在事务内吸收 active Run 竞态。
- 必须确认 `submit_followup(steer)` 的 conflict / invalid_state 返回 shape。
- 必须确认哪些 public functions 在本 phase 已有完整行为，哪些只在公共契约中稳定、由后续 phase 落地。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Host handle / typed options / policy views / context validation。
- Slice 2: session APIs 与 snapshots。
- Slice 3: run / follow-up / cancel / retry / replay command path backed by state machine。

验证要求：
- unit tests: API idempotency、context validation、error classification。
- integration tests: multi-client style repeated calls and retry after timeout。
- pyright: Host public API 模块通过。
- docs: dayu/README.md / Host README 按触发规则同步。

退出条件：
- 多入口可以通过稳定函数式 API 操作 Host durable state；尚未支持真实 Engine execution 的接口必须以明确状态或受控 fake dispatch 测试。

后续依赖：
- 后续 phase 可依赖的稳定契约：public command path、Host handle、typed options、snapshot shape、API idempotency、read API shape（`get_run` / `get_session` / `stream_run_events` 的 snapshot 与 cursor contract）。
- 需要追踪到后续 phase 的事项：执行、projection、memory、remote 后续接入不得绕过 public command path；Phase 8 依赖本 phase 的 read API shape 与 snapshot / stream cursor contract；`resolve_wait` public signature / request envelope 在本 phase 稳定，等待结果治理语义在 Phase 7 落地；`purge_session` public signature / `PurgeSessionResult` / idempotency contract 在本 phase 稳定，destructive cleanup 在 Phase 14 落地。

### Phase 5. RunInputBuilder 与本地执行 Dispatch

目标：
- 连接 RunInputBuilder、Attempt dispatch record、LLM lane、LocalProxy / EngineWorker、EngineEvent ingest 与 terminal 收口，形成本地 Engine 执行闭环。

对应设计章节：
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §23 RunInputBuilder
- `docs/host/design.md` §13.4 EngineEvent 映射
- `docs/host/design.md` §22 Cancel

前置条件：
- Phase 4 public command path 已完成。
- Phase 1 runtime lane 已完成。

进入条件：
- 确认第一版 LocalProxy 与 EngineWorker 的 adapter 边界，以及 RunInputBuilder typed provider 最小集合。

范围：
- 允许修改：RunInputBuilder provider protocols、attempt snapshot、dispatch scheduler、LocalProxy adapter、EngineEvent ingest、cancel propagation。
- 禁止修改：Remote wire protocol、ToolRuntime advanced governance、Memory projection、Context Governance。

不做：
- 不实现 RemoteProxy。
- 不实现 full ToolRuntime governance；可使用最小 ToolExecutor / no-tool 或 fake tool path 支撑本地执行闭环。
- 不实现 Observer / Sink。

关键设计问题：
- 必须确认 `AgentRunRequest.messages` 由 canonical facts 重建，不读取 UI 临时文本。
- 必须确认 lane acquire 后 recheck / dispatching / ATTEMPT_RUNNING 的精确 transaction 边界。
- 必须确认 EngineEvent terminal / non-terminal / stream EOF 的 Host 收口规则。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: RunInputBuilder typed providers and deterministic messages。
- Slice 2: dispatch scheduler / lane / dispatch record / LocalProxy。
- Slice 3: EngineEvent ingest mapping and terminal closeout。
- Slice 4: cancel propagation and stream EOF failure handling。

验证要求：
- unit tests: RunInputBuilder determinism、EngineEvent mapping、dispatch recheck。
- integration tests: local Engine fake end-to-end run success / failure / cancel。
- pyright: Host execution modules 通过。
- docs: Host README / Engine boundary docs 按触发规则同步。

退出条件：
- 一个已 accepted 的 prompt 能通过本地 Engine path 产生 terminal EventLog fact 与 RunSnapshot terminal result。

后续依赖：
- 后续 phase 可依赖的稳定契约：attempt snapshot、LocalProxy semantic baseline、EngineEvent ingest、dispatch lane semantics。
- 需要追踪到后续 phase 的事项：RemoteProxy 必须保持与 LocalProxy 等价语义。

### Phase 6. ToolRuntime / Truncation / fetch_more / Duplicate Governance

目标：
- 落地 Host-owned ToolRuntime、ToolBundle snapshot、Host accept barrier、TruncationManager、`fetch_more` 与同 Run 语义级重复工具调用治理。

对应设计章节：
- `docs/host/design.md` §18 ToolRuntime
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `docs/host/design.md` §18.2 ToolRuntime Boundary
- `docs/host/design.md` §18.3 语义级重复工具调用治理
- `docs/host/design.md` §19 TruncationManager / fetch_more

前置条件：
- Phase 5 本地执行闭环已完成。
- Phase 2 payload descriptor 与 EventLog append primitive 已完成。

进入条件：
- 确认 ToolRuntime ports、accept idempotency key、effective ToolBundle 与 truncation descriptor 的最小 typed contract；确认形式为用户确认，或 `docs/host/design.md` 对应章节已细化到可直接生成 typed contract / test matrix。

范围：
- 允许修改：ToolRuntime factory、ToolExecutor wrapper、ToolBundle snapshot、tool fact accept path、TruncationManager、fetch_more framework tool、duplicate index、tool trace diagnostic emitter interface。
- 禁止修改：Engine 工具协议语义、Remote wire protocol、业务工具实现。

不做：
- 不实现长期 memory retrieval。
- 不实现 Remote transport。
- 不做跨 Run / 跨 Session 重复工具治理。

关键设计问题：
- 必须确认工具事实 accepted ack 失败 / timeout 的默认治理动作。
- 必须确认 truncation cursor / scope_token durable descriptor 的存储位置与恢复输入。
- 必须确认 replay no-tool 防线如何从 RunInputBuilder 与 ToolRuntime 双层执行。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: ToolRuntime ports / effective ToolBundle / schema projection。
- Slice 2: Host accept barrier and tool canonical fact append。
- Slice 3: TruncationManager / fetch_more / durable descriptors。
- Slice 4: run-local duplicate governance and tool trace diagnostic emitter。

验证要求：
- unit tests: ToolBundle validation、accept idempotency、duplicate policy、truncation scope validation。
- integration tests: fake tool execution through Engine, accepted ack retry, fetch_more normal tool path。
- pyright: ToolRuntime 模块通过。
- docs: dayu/README.md / Host README 工具边界同步。

退出条件：
- Engine 只能通过 Host-governed ToolExecutor 使用工具；LLM 不会消费未 durable accepted 的工具事实。

后续依赖：
- 后续 phase 可依赖的稳定契约：ToolRuntime accept barrier、effective ToolBundle、fetch_more 普通工具路径、tool diagnostic refs。
- 需要追踪到后续 phase 的事项：RemoteProxy 必须支持等价 tool fact accept ack 语义。

### Phase 7. Tool Awaiting / resolve_wait / Wait Adapter

目标：
- 实现长事务等待进入 Host 的 canonical path、wait record、`resolve_wait`、poll / manual adapter 最小能力与 WAITING resume。

对应设计章节：
- `docs/host/design.md` §20 Tool Awaiting / Wait Record
- `docs/host/design.md` §21 Suspend / Resume / Retry / Replay
- `docs/host/design.md` §22 Cancel

前置条件：
- Phase 6 ToolRuntime accept barrier 已完成。
- Phase 5 dispatch / resume attempt creation path 已完成。

进入条件：
- 确认第一版实现 internal / manual resolve + poll adapter，callback 只预留 adapter contract；必须复核 Phase 4 已冻结的 `resolve_wait` public signature / request envelope，如需变更，先回到 Public API contract 讨论。

范围：
- 允许修改：wait record table / store、wait adapter durable refs、ToolAwaitingOutcome accept path、resolve_wait command、wait poller background adapter、WAITING cancel / steer / resume。
- 禁止修改：外部系统专属 callback 服务、复杂 job reconcile、强制外部 job cancel。

不做：
- 不保证外部 job physical cancel。
- 不实现 callback 认证入口完整产品化。
- 不实现远端 worker 自治 resume。

关键设计问题：
- 必须确认 wait record adapter key / await_spec / external_job_id 的 typed fields。
- 必须确认 `resolve_wait` 非阻塞短事务错误 shape。
- 必须确认 WAITING cancel 后迟到结果进入 diagnostic / tool trace 的路径。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: wait record durable model and ToolAwaiting accept path。
- Slice 2: resolve_wait command path and resume attempt creation。
- Slice 3: poll / manual adapter and WAITING cancel / late result handling。

验证要求：
- unit tests: wait record state machine、resolve_wait idempotency、late result rejection。
- integration tests: awaiting -> resolve -> resumed local run。
- pyright: wait adapter modules 通过。
- docs: Host README wait / resume 语义同步。

退出条件：
- 长事务工具可以让 Run 进入 WAITING，并由统一 `resolve_wait` 创建新 Attempt 继续。

后续依赖：
- 后续 phase 可依赖的稳定契约：wait record、resolve_wait pipeline、wait poller background runtime。
- 需要追踪到后续 phase 的事项：callback adapter、外部 job cancel / revoke 属于后续能力。

### Phase 8. Projection Core / Host Event Stream / Minimal Read Model

目标：
- 实现 committed EventLog 消费基础、projection checkpoint、Host event stream cursor 与最小 RunResult / Session timeline read model，为 Memory、Recovery 和后续 projection sinks 提供稳定基座。

对应设计章节：
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

前置条件：
- Phase 2 EventLog foundation 已完成。
- Phase 4 public read APIs 已完成。

进入条件：
- 确认 projection runner、checkpoint、Host event stream 与最小 read model 的边界；Audit、Tool Trace、Outbox 只预留 consumer contract，不在本 phase 落地。

范围：
- 允许修改：projection runner、checkpoint store、typed consumer contract、stream fanout 基础、Host event stream、timeline / RunResult 最小 read model。
- 禁止修改：command path 状态机、Run / Attempt governance state、UI / Service channel delivery。

不做：
- 不实现 `LogAuditSink(JSONL)`。
- 不实现 tool trace hot JSON / cold JSONL。
- 不实现 OutboxSink。
- 不实现外部 audit 系统。
- 不保证 channel delivery exactly-once。
- 不让 terminal transaction 同步写 outbox 表。

关键设计问题：
- 必须确认 projection runner 的 typed consumer contract、checkpoint、幂等键和失败处理。
- 必须确认 Host event stream 只从 EventLog `event_sequence` cursor 补读，不触发执行。
- 必须确认最小 RunResult / Session timeline read model 损坏后可由 EventLog 重建。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: projection runner / checkpoint / typed consumer contracts。
- Slice 2: Host event stream from EventLog `event_sequence` cursor。
- Slice 3: minimal Session timeline / RunResult read model and rebuild path。

验证要求：
- unit tests: checkpoint idempotency、consumer replay、projection rebuild。
- integration tests: terminal EventLog -> Host event stream / minimal timeline / RunResult。
- pyright: projection modules 通过。
- docs: Host README read model / event stream 边界按触发规则同步。

退出条件：
- Projection lag 或 core projection failure 不影响 EventLog append、Run terminal、resume 或 memory truth；Memory phase 可以复用 checkpoint / consumer framework。

后续依赖：
- 后续 phase 可依赖的稳定契约：EventLog replay consumers、projection checkpoint、Host event stream cursor、minimal read model。
- 需要追踪到后续 phase 的事项：Audit / Tool Trace / Outbox 作为独立 projection sinks 后置；Service / UI channel delivery 不属于 Host truth。

### Phase 9. Conversation Memory / Session Memory Projection

目标：
- 实现 session-level Conversation Memory projection、stable layer、history pool、snapshot cursor、RunInputBuilder memory provider 与 projection repair path。

对应设计章节：
- `docs/host/design.md` §24 Conversation Memory
- `docs/host/design.md` §23 RunInputBuilder
- `docs/host/design.md` §26 Evidence / Retrieval / Long-term Memory

前置条件：
- Phase 8 projection runner 已完成。
- Phase 5 RunInputBuilder provider boundary 已完成。

进入条件：
- 确认第一版只做 session memory，不做长期 memory public edit / reset / forget API。

范围：
- 允许修改：memory projection、memory snapshot store、stable layer / history pool policy、RunInputBuilder MemorySnapshotProvider、memory lag diagnostic / repair path。
- 禁止修改：长期 memory retrieval、业务领域 evidence store、EventLog canonical fact semantics。

不做：
- 不实现跨多年长期记忆。
- 不把 final_answer 自动升级为 verified fact。
- 不让 memory projection 写 EventLog。

关键设计问题：
- 必须确认 stable layer 默认预算、recent raw turns floor、history pool 降级顺序。
- 必须确认 projection lag 阈值与 RunInputBuilder fallback 策略。
- 必须确认 assistant conclusion / verified fact 的投影规则。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: memory projection data model and checkpoint。
- Slice 2: stable layer / history pool builder。
- Slice 3: RunInputBuilder MemorySnapshotProvider and lag fallback。

验证要求：
- unit tests: final_answer not verified fact、tool facts verified、snapshot cursor coverage。
- integration tests: multi-run continuity with memory projection rebuild。
- pyright: memory modules 通过。
- docs: Host README / dayu/README.md 按触发规则同步。

退出条件：
- RunInputBuilder 可以稳定消费 memory snapshot；projection lag 不改变同一 EventLog + policy 下的 messages。

后续依赖：
- 后续 phase 可依赖的稳定契约：memory snapshot cursor、stable layer input provider、projection repair semantics。
- 需要追踪到后续 phase 的事项：长期 memory / query-time retrieval 后续单独设计。

### Phase 10. Context Governance / Compaction

目标：
- 实现 Host proactive context budget governance、compact event、compacted artifact、reactive Engine overflow recovery 与 RunInputBuilder compact provider。

对应设计章节：
- `docs/host/design.md` §25 Context Governance
- `docs/host/design.md` §25.1 Compact Event 响应路径
- `docs/host/design.md` §23 RunInputBuilder

前置条件：
- Phase 0 Engine context compaction event cleanup 已完成；Phase 10 不消费 Engine overflow event 作为真实 Host budget，必须使用 Host estimator / policy。
- Phase 9 memory projection 已完成。
- Phase 5 dispatch / reactive failure closeout 已完成。
- Phase 6 ToolRuntime / tool fact accept barrier / truncation descriptors 已完成。

进入条件：
- 确认 conservative estimator、provider-aware configured limits、safety margin 与 compact policy 的第一版默认值。

范围：
- 允许修改：Context Governance orchestrator、budget estimator、compact artifact store、compact canonical events、RunInputBuilder CompactArtifactProvider、reactive overflow recovery path。
- 禁止修改：Engine proactive compaction、memory projection direct write、audit / trace projection direct write。

不做：
- 不实现 provider-specific tokenizer adapter。
- 不实现长期 memory retrieval。
- 不做无限 compact retry。

关键设计问题：
- 必须确认 proactive 与 reactive 两条路径的 transaction / state transition。
- 必须确认 compacted snapshot 的质量检查、保留事实 refs 与 dropped / summarized ranges。
- 必须确认 compact failure 的 Run terminal / recoverable policy。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: budget estimator / policy view / proactive trigger。
- Slice 2: compact artifact and canonical events。
- Slice 3: reactive Engine overflow -> RECOVERING -> new Attempt path。
- Slice 4: RunInputBuilder compact provider and failure handling。

验证要求：
- unit tests: threshold decisions、compact event payload validation、failure policy。
- integration tests: proactive compact before dispatch and reactive overflow recovery。
- pyright: context governance modules 通过。
- docs: Host / Engine boundary docs 按触发规则同步。

退出条件：
- Host 能在 dispatch 前主动 compact，并能把 Engine overflow 当作 reactive fallback 恢复，不让 Engine 管理 Host context budget。

后续依赖：
- 后续 phase 可依赖的稳定契约：compact events、compact artifacts、context budget policy view。
- 需要追踪到后续 phase 的事项：provider-specific tokenizer adapter 是后续能力。

### Phase 11. Host Lifecycle / Recovery / Multi-process Hardening

目标：
- 实现 Host startup recovery scan、positive orphan proof、prompt accepted but answer not returned 的恢复语义、graceful shutdown 与多进程一致性硬化。

对应设计章节：
- `docs/host/design.md` §27 Host Lifecycle / Recovery
- `docs/host/design.md` §27.1 已接受 Prompt 的恢复语义
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §17 WorkerProxy / EngineWorker

前置条件：
- Phase 5 dispatch record / LocalProxy 已完成。
- Phase 2 host instance liveness foundation 已完成。
- Phase 3 state transition / admission 已完成。

进入条件：
- 确认 positive orphan proof 的本机 pid / process_start_token / heartbeat 判定实现策略。

范围：
- 允许修改：startup recovery scan、host instance heartbeat、orphan classifier、RECOVERING dispatch、shutdown policy、multi-process tests。
- 禁止修改：远端 takeover、lease / fencing 系统、旧 Attempt resume。

不做：
- 不保证 exactly-once 远程物理执行。
- 不强杀远程执行环境。
- 不从 projection 或 memory 恢复 Run truth。

关键设计问题：
- 必须确认 `RUNNING` / `CANCELLING` / `RECOVERING` / `WAITING` / `QUEUED` startup 分类。
- 必须确认 suspect owner 不被误杀的 diagnostic path。
- 必须确认 repeated recovery 上限与 LOST / FAILED 收口 policy。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: host instance heartbeat and positive orphan proof。
- Slice 2: recovery scan classification and CAS closeout。
- Slice 3: RECOVERING dispatch and prompt accepted recovery integration。
- Slice 4: graceful shutdown and multi-process race tests。

验证要求：
- unit tests: orphan proof classifier、state classification。
- integration tests: crash after USER_INPUT_ACCEPTED before final answer, restart produces answer; live second process not harmed; projection runner stopped or lagging 时仍能仅凭 EventLog / state indexes 完成 recovery。
- pyright: recovery modules 通过。
- docs: Host README recovery 语义同步。

退出条件：
- 已 durable accepted 的 prompt 在 Host 崩溃 / 重启后可通过新 Attempt 继续并最终产出 answer，且不会误杀仍存活 Host 进程的 active Attempt。

后续依赖：
- 后续 phase 可依赖的稳定契约：startup recovery、positive orphan proof、RECOVERING dispatch。
- 需要追踪到后续 phase 的事项：远端 orphan execution 仍按 RemoteProxy phase 和 exactly-once 非目标治理。

### Phase 12. Audit / Tool Trace / Outbox Projections

目标：
- 在已稳定的 EventLog consumer framework 上实现 LogAuditSink、tool trace hot / cold storage 与 Outbox terminal delivery queue projection。

对应设计章节：
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §14.1 Tool Trace Hot / Cold Storage
- `docs/host/design.md` §15 Audit
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

前置条件：
- Phase 8 Projection Core / Host Event Stream / Minimal Read Model 已完成。
- Phase 6 ToolRuntime diagnostic refs 已完成。

进入条件：
- 确认 Audit、Tool Trace、Outbox 只是 projection / sink，不参与 Host command path 成功条件，不反向成为恢复、resume、memory 或 Run 状态迁移真源。

范围：
- 允许修改：LogAuditSink(JSONL)、tool trace hot JSON projection、tool trace cold JSONL writer、OutboxSink、sink-local retry / error state、相关 read / analyze support。
- 禁止修改：EventLog append 语义、Run / Attempt governance state、terminal transaction、UI / Service channel delivery 状态。

不做：
- 不实现外部 audit 系统。
- 不保证 channel delivery exactly-once。
- 不让 terminal transaction 同步写 outbox 表。
- 不把 tool trace JSONL 当作恢复、resume、memory 或 Run 状态迁移真源。

关键设计问题：
- 必须确认 tool trace hot JSON 与 cold JSONL 的最小字段，以及 provider request id / operation context refs 的查询口径。
- 必须确认 Outbox item identity 与 UI / Service seen cursor 推荐语义。
- 必须确认 LogAuditSink 路径注入、append-only JSONL、sink failure 和 purge tombstone 查询语义。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: LogAuditSink and audit JSONL。
- Slice 2: tool trace hot JSON / cold JSONL。
- Slice 3: OutboxSink and terminal delivery queue projection。

验证要求：
- unit tests: sink checkpoint idempotency、sink retry、audit / trace / outbox projection rebuild。
- integration tests: terminal EventLog -> audit / tool trace / outbox；sink failure 不影响 Run terminal。
- pyright: projection sink modules 通过。
- docs: Host README / tool trace analysis docs 按触发规则同步。

退出条件：
- Audit、Tool Trace、Outbox 均能从 committed EventLog 独立追平；任一 sink 失败只造成 projection lag 或 sink-local error，不影响 Host command path。

后续依赖：
- 后续 phase 可依赖的稳定契约：audit JSONL、tool trace hot / cold、outbox terminal delivery queue。
- 需要追踪到后续 phase 的事项：Service / UI channel delivery、外部 audit 系统和长期归档策略不属于本 phase。

### Phase 13. RemoteProxy / RemoteStub

目标：
- 在 LocalProxy 语义基准上实现 RemoteProxy / RemoteStub transport substitution，保持 Host 治理真源、execution_id late event rejection 与 tool fact accept ack。

对应设计章节：
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §18 ToolRuntime
- `docs/host/design.md` §27 Host Lifecycle / Recovery

前置条件：
- Phase 5 LocalProxy semantic baseline 已完成。
- Phase 6 ToolRuntime accept barrier 已完成。
- Phase 11 recovery 与 positive orphan proof 已完成。

进入条件：
- 确认 remote phase 只定义并实现 transport，不改变 design 的 remote semantic contract。

范围：
- 允许修改：RemoteProxy、RemoteStub、remote event identity mapping、remote cancellation propagation、remote tool accept ack transport。
- 禁止修改：Host 状态 ownership、EventLog append ownership、Attempt takeover 语义、wire protocol 污染设计文档。

不做：
- 不实现远端 worker 自治恢复。
- 不保证 exactly-once 远程物理执行。
- 不引入远端 lease / fencing owner。

关键设计问题：
- 必须确认 remote event id / ordering hint / retry / ack 的 typed transport contract。
- 必须确认 stale execution_id、late terminal、late tool result 和 connection drop 的诊断路径。
- 必须确认 RemoteStub 不拥有 Host durable truth 的测试边界。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: RemoteProxy / RemoteStub transport skeleton and attempt snapshot serialization。
- Slice 2: remote EngineEvent ingest / late event rejection。
- Slice 3: remote cancel and connection failure closeout。
- Slice 4: remote tool fact accept ack path。

验证要求：
- unit tests: event identity mapping、stale execution_id rejection、ack idempotency。
- integration tests: remote fake worker success / cancel / disconnect / late event / duplicate event。
- pyright: remote modules 通过。
- docs: Host README remote boundary 同步。

退出条件：
- 本地与远程 EngineWorker 在 Host 视角下共享同一治理语义；远端只执行并回传事件，不拥有 Host state owner。

后续依赖：
- 后续 phase 可依赖的稳定契约：Remote transport substitution、tool accept ack over remote、late event diagnostic。
- 需要追踪到后续 phase 的事项：远程 wire protocol 细节可以独立演进，但不能改变 semantic contract。

### Phase 14. Retention / Purge / Production Hardening

目标：
- 收口第一版生产化要求：`purge_session` destructive cleanup、audit tombstone、projection rebuild 验证、性能 / 并发 smoke、docs 与 residual risk 归档。

对应设计章节：
- `docs/host/design.md` §5 Session 生命周期
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §15 Audit
- `docs/host/design.md` §28 第一版 Non-goals

前置条件：
- Phase 8 projection core、Phase 11 recovery、Phase 12 Audit / Tool Trace / Outbox、Phase 13 remote 已完成。

进入条件：
- 确认第一版 release / PR 前必须关闭的 residual risk 与可接受 non-goals。
- 先区分 release-blocking 与 follow-up items；如 projection rebuild tooling、stress / smoke tests 或 docs closeout scope 过大，必须拆出独立 phase 或后续 work unit。
- 必须复核 Phase 4 已冻结的 `purge_session` public signature / `PurgeSessionResult` / idempotency contract；如需变更，先回到 Public API contract 讨论。

范围：
- 允许修改：`purge_session` command implementation、purge delete ranges、shared artifact ref check、projection rebuild tooling、audit tombstone query support、stress / smoke tests、README sync。
- 禁止修改：新增 archive_session、长期 memory API、重型消息系统、服务化 DB。

不做：
- 不实现 archive_session。
- 不实现长期 retention policy UI。
- 不把第一版 non-goals 偷偷变成实现目标。

关键设计问题：
- 必须确认 purge 对 EventLog / payload / projection / outbox / tool trace hot data / audit JSONL 的最终清理矩阵。
- 必须确认第一版 residual risks 的接受、后续 issue 或当前修复归属。
- 必须确认 purge / tombstone / projection rebuild slices 是否可以在 Remote smoke 之前独立完成；remote smoke / release closeout slice 依赖 Phase 13。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: purge delete matrix and tombstone audit。
- Slice 2: projection rebuild / consistency checks。
- Slice 3: multi-process / remote / recovery production smoke。
- Slice 4: README / docs / residual risk closeout。

验证要求：
- unit tests: purge precondition and tombstone behavior。
- integration tests: purge after terminal runs, projection rebuild, audit JSONL retention。
- integration tests: crash after `USER_INPUT_ACCEPTED` + old attempt events, recovery scan creates new attempt, new attempt reaches terminal, projection rebuild from EventLog verifies old attempt facts、new attempt facts、terminal result、outbox / audit / trace projections as applicable。
- pyright: full project or affected packages。
- docs: all triggered README updates complete。

退出条件：
- 第一版 Host design 的核心目标可通过测试和文档说明支撑，剩余 non-goals 与 deferred risks 均有明确追踪归属。

后续依赖：
- 后续 phase 可依赖的稳定契约：purge semantics、production smoke baseline、residual risk registry。
- 需要追踪到后续 phase 的事项：archive_session、provider-specific tokenizer、长期 memory、remote wire protocol evolution。

## Open Questions 与风险追踪

总控文档负责追踪跨 phase 的 open questions、潜在影响和未覆盖项。

追踪规则：

- `blocking` open question 必须在对应 phase 的 plan review 通过前解决，并写回 `docs/host/design.md` 或 phase plan。
- `non-blocking` open question 必须写明 working assumption、风险、触发回看条件和归属 phase。
- implementation 中发现的新 open question，如果会影响设计边界或用户可见行为，必须停下交给用户讨论。
- residual risk 和 uncovered area 必须分类为：当前 phase 修复、后续 phase 覆盖、后续 work unit、用户明确接受、或需要新跟踪项。
- 任何 deferred 项都必须有 owner / destination；没有 destination 时不能关闭对应 phase。

### 追踪区

#### Engine Context Compaction Event 语义前置

背景决议：

- Engine 只在 provider 返回 `context_length_exceeded` 后 emit `context_compaction_requested`；这属于 reactive fallback，不是生产级 proactive context governance。
- P0-S1 已将 `ContextCompactionRequestedData.budget_state` 改为 `ContextBudgetSnapshot | None`；provider overflow path 使用 `None` 表示预算未知 / 未上报，不再使用零值快照作为 unknown sentinel。
- `ContextBudgetSnapshot` 仍只表示真实、可解释的 token snapshot；数值为零仍是普通真实快照，不得被解释为 unknown。
- Host 生产级治理应由 Context Governance 基于 provider-aware budget policy 主动判断 soft / hard threshold；provider overflow 只能作为最后防线。

前置实施步骤：

- P0-S1 Engine contract cleanup 已完成并提交为 `ad6d116`。
- P0-S2 同步 Engine README、Engine design docs、项目级术语和本追踪区，使后续 Host implementation agent 不会把 Engine reactive fallback 误解为 proactive context governance。
- P0 不把 budget governance 放进 Engine；Engine 不做 proactive threshold compaction，不做 compact / retry，不计算 Host budget，不提供 provider-aware tokenizer 或 Host budget policy。
- P0 保留 `usage_reported`、`iteration_completed`、provider request id 和 overflow reason，供 Host Context Governance 诊断与追踪。

追踪项：

- P0-S2 已同步 `dayu/engine/README.md`、`docs/engine/design.md`、`dayu/README.md` 中的相关术语与边界。
- `docs/host/design.md` 已明确：proactive threshold compaction 属于 Host Context Governance；Engine provider overflow event
  只是 reactive fallback。Phase 10. Context Governance / Compaction 只能按该语义实施。
- Phase 5 owns EngineEvent ingest validation：必须接受 `budget_state=None` 的 Engine event shape，不把 `None` 当作协议错误，不要求 Engine 提供 Host budget ref。
- Phase 10 owns Context Governance semantic interpretation：当 Engine overflow budget unknown 时，必须使用 Host estimator / policy 生成 before / after budget refs，并决策 compact / recovery。
- Phase 10. Context Governance / Compaction 的测试设计必须覆盖：Engine overflow event 中预算 unknown 时，Host 仍使用自身 budget estimator 进行 compact 诊断与恢复决策。

#### External Job Cancel Adapter 能力追踪

背景决议：

- `WAITING` Run 被 `cancel_run` 命中时，Host 第一版负责 durable 状态收口：append `CANCEL_REQUESTED`，标记 active wait record 为 cancelled，append `RUN_CANCELLED`，并释放 Session active slot。
- 外部 job 的实际取消属于对应 wait adapter / tool adapter 的 best-effort 能力，不作为 Host 第一版保证。

追踪项：

- Phase 7. Tool Awaiting / resolve_wait / Wait Adapter 必须定义 wait record 被 Host 标记 cancelled 后，adapter 如何观察该状态。
- 后续 adapter 可以按能力实现外部 job cancel / revoke / abandon，但必须明确这是 best-effort，不得影响 Host EventLog 和 Run 终态的正确性。
- 如果外部 job 在 Host 已取消 Run 后仍回调或被 poll 到结果，Host 必须拒绝其结果进入 canonical EventLog，只能记录 diagnostic / tool trace。
- Phase 6. ToolRuntime / Truncation / fetch_more / Duplicate Governance 必须明确具有外部副作用、付费调用或长耗时资源占用的工具是否提供 job id、cancel handle、idempotency key 和资源清理策略。
- 第一版测试至少覆盖：`WAITING -> CANCELLED` 后迟到 `resolve_wait` / callback 不污染 canonical EventLog。

#### Tool Trace / Provider Request 排错追踪

背景核实：

- OpenAI API reference 的 Debugging requests 说明 `x-request-id` 是每次 API request 的唯一标识，并建议生产环境记录 request id，便于和 OpenAI support 排障。
- 同一官方章节说明调用方可显式提供 `X-Client-Request-Id`；当 timeout / network issue 导致拿不到 `X-Request-Id` response header 时，可用该值让 OpenAI support 查询是否收到请求以及收到时间。
- 当前 Engine 已把 provider response header 的 `x-request-id` 提取为 `provider_request_id`，并在 Runner / Engine 错误与终态链路中显式透传：`RunnerHTTPErrorData`、`RunnerProtocolErrorData`、`RunnerDoneData`、`ProviderProtocolErrorData`、`RunFailedData`、`EngineRunOutcomeFailed` 等字段已覆盖；相关测试也覆盖了 HTTP error、protocol error、iteration completed、run failed 的透传。

追踪项：

- 不修改 `docs/host/design.md`；这不是 Host 架构边界新决策，而是 tool trace / analyze 工具排障能力需求。
- Phase 12. Audit / Tool Trace / Outbox Projections 实现 tool trace 与后续 `utils/analyze_tool_trace.py` 时，必须把 `provider_request_id` 纳入热 JSON projection 与冷 JSONL，便于按 OpenAI `x-request-id` 排查 provider 错误、超时、协议错误和重试耗尽。
- 后续 Host 外部 Service / provider adapter work unit 若为 OpenAI-compatible request 注入 `X-Client-Request-Id`，Phase 12 tool trace 也必须记录对应 client-side request id，并与 `provider_request_id`、`run_id`、`attempt_id`、`execution_id`、`event_sequence` 一起可查询。
- 对 timeout / network error 且 `provider_request_id=None` 的场景，analyze 工具应提示优先查看 client-side request id / `X-Client-Request-Id`、网络错误类型、attempt 次数和 retry history。

#### SQLite 多进程写入正确性验证

结论：

- 第一版继续使用 SQLite durable store 作为单机多进程 Host 真源。
- 不提前引入服务化数据库、消息队列、分库或重型写入架构。
- 正确性依赖 WAL、明确 busy timeout、短事务、显式重试、唯一约束和 CAS-style state transition。
- 该项重点是验证写竞争不会破坏状态机和 EventLog 真源；性能容量只有在压测或生产观察证明明显后才升级为容量治理问题。

追踪项：

- Phase 2. Durable Store / EventLog / Payload Foundation 必须明确 SQLite 连接配置、WAL、busy timeout、transaction 边界、retry 策略和错误分类。
- Phase 3. Session / Run / Attempt 状态机与 Admission 的多进程测试必须覆盖同 Session 并发 `start_run`、重复 `client_request_id`、active slot admission、queue promotion、cancel / terminal race、EventLog `event_sequence` 单调性。
- phase plan 不得把 SQLite 写竞争作为引入服务化 DB 或消息队列的默认理由。

#### Remote 物理执行 exactly-once 非目标

结论：

- 第一版不保证 exactly-once 远程物理执行。
- Host 只保证 canonical EventLog、Run / Attempt 状态和 Tool fact accept 的治理正确性。
- 远端 worker 在 Host 崩溃、断连或超时后可能继续执行旧 attempt；Host 必须通过 `execution_id` 和 active Attempt 校验拒绝迟到 terminal / tool fact。
- 外部副作用必须依赖工具级 idempotency key、tool policy、adapter best-effort cancel 和诊断追踪降低风险；不能依赖 Host lease / fencing 兜底。

追踪项：

- Phase 13. RemoteProxy / RemoteStub 必须测试旧 `execution_id` 的迟到 Engine event、迟到 tool result、迟到 terminal 只能进入 diagnostic / trace，不能污染 canonical EventLog。
- Phase 6. ToolRuntime / Truncation / fetch_more / Duplicate Governance 必须明确具有外部副作用的工具的 idempotency key、side-effect policy 和可取消能力。
- Phase 13. RemoteProxy / RemoteStub 不得引入远端 takeover attempt、远端 append EventLog 或远端更新 Run 状态。

#### Session Purge / Archive 追踪

结论：

- 第一版提供 `purge_session`，用于清理已关闭且所有 Run 已终态的 Session 的 Host 本地数据。
- `purge_session` 是 destructive purge，不是 close、cancel、archive、memory forget 或 UI hide。
- `purge_session` 必须保留最小 purge tombstone / audit record；purge 后不再支持恢复、resume、retry、replay、timeline 补读或 final answer 找回。
- `archive_session` 不进入第一版。archive 的语义是把冷 Session 移到 archive storage，保留可审计、可查询、可按需恢复的只读档案；archive 不删除事实。

追踪项：

- Phase 4. Host Public API Command Path 必须稳定 `purge_session` 的 request、幂等、错误形状和 `PurgeSessionResult` 公共契约；Phase 14. Retention / Purge / Production Hardening 必须细化删除范围、tombstone 存储位置和 destructive cleanup 语义。
- Phase 14. Retention / Purge / Production Hardening 必须定义共享 cold artifact 的引用计数或 ref 检查，防止 purge 删除仍被其它 Session 引用的 artifact。
- 后续单独追踪 `archive_session` 的需求和边界；不得用 `purge_session` 模拟 archive。

#### Host 跨层测试策略追踪

结论：

- Host 测试不能只依赖端到端路径。
- 每个 phase 的 handoff implementation-ready plan 必须包含与该 phase 边界匹配的验证策略。
- 跨层集成测试用于验证路径组合，不替代状态机、事务、adapter、projection、recovery 的分层测试。

追踪项：

- Phase 3. Session / Run / Attempt 状态机与 Admission 必须提供 Run / Attempt / Session 状态迁移单元测试。
- Phase 2. Durable Store / EventLog / Payload Foundation 必须提供 SQLite transaction、CAS、唯一约束、多进程竞争和 crash recovery foundation 测试。
- Phase 5. RunInputBuilder 与本地执行 Dispatch 必须提供 WorkerProxy fake integration；Phase 13. RemoteProxy / RemoteStub 必须提供迟到事件、断连、重发和 accept ack 测试。
- Phase 6. ToolRuntime / Truncation / fetch_more / Duplicate Governance 必须提供外部业务 `ToolBundle` 输入、attempt-local effective `ToolBundle`、`fetch_more` 注入、tool fact accept barrier、truncate / fetch_more、重复工具调用治理和 side-effect policy 测试。
- Phase 8. Projection Core / Host Event Stream / Minimal Read Model 必须提供 EventLog replay、checkpoint、Host event stream、minimal read model 的幂等追平测试；Phase 12. Audit / Tool Trace / Outbox Projections 必须提供 Outbox、audit、usage、tool trace 的幂等追平测试。
- Phase 11. Host Lifecycle / Recovery / Multi-process Hardening 必须提供 Host restart、positive orphan proof、LOST / RECOVERABLE_LOST、prompt 已 accepted 但 answer 未返回的恢复测试。

#### UI / Service Outbox 去重边界追踪

结论：

- 在线 / 已 attach 客户端通过 Host event stream、Session timeline、RunSnapshot 或 read model 读取 final answer。
- Outbox 只提供离线 / 外部渠道的 terminal 增量，不提供完整聊天记录或中间过程回放。
- 在线阅读路径和 Outbox 离线投递路径必须共享同一个 terminal identity。
- per-client 的 seen cursor、delivery ledger、read ack 和 channel 投递状态属于 UI / Service / channel adapter，不属于 Host truth。

追踪项：

- Phase 12. Audit / Tool Trace / Outbox Projections 必须保证 outbox item 携带稳定 `terminal_event_id`、`event_sequence`、`run_id`、`result_digest` 和幂等 item key。
- Host 外部 Service / UI 后续 work unit 必须定义 `last_seen_terminal_event_sequence` 或 `seen_terminal_event_ids` 的持久化位置和更新时机。
- Host 外部 Service / UI 后续 work unit 必须覆盖：客户端在线已展示 final answer 后离线重连，从 Outbox 读取增量时不会重复显示同一 terminal answer。
- Host 外部 UI 显示聊天记录必须按 terminal identity upsert / dedupe，不得按 final answer 文本内容去重。

## 当前状态

当前阶段为 P0：Engine Context Compaction Event 语义前置。Host 代码实施尚未开始；`docs/host/design.md` 已是 Host 架构真源，
`dayu/README.md` 是项目级术语真源。用户已确认 P0 直接进入 plan gate，并允许本 work unit 修改 Engine contract / docs / tests。

当前 gate 为 PR。P0 plan 已写入 `docs/host/phase0-engine-context-compaction-plan.md`；AgentMiMo 与 AgentDS 已完成并行 plan review，
review artifacts 分别为 `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-mimo-20260513.md` 和
`docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-ds-20260513.md`。总控裁决已写入
`docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-controller-adjudication-20260513.md`，plan fix artifact 已写入
`docs/reviews/gateflow-plan-fix-host-p0-engine-context-compaction-20260513.md`。plan re-review artifacts 已写入
`docs/reviews/gateflow-plan-re-review-host-p0-engine-context-compaction-mimo-20260513.md` 和
`docs/reviews/gateflow-plan-re-review-host-p0-engine-context-compaction-ds-20260513.md`，re-review 总控裁决已写入
`docs/reviews/gateflow-plan-re-review-host-p0-engine-context-compaction-controller-adjudication-20260513.md`。

P0 plan re-review 已通过，用户已确认进入 implementation；accepted plan commit 为 `866f6f5`。P0-S1 implementation artifact 已写入
`docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`。P0-S1 code review artifacts 已写入
`docs/reviews/gateflow-code-review-host-p0-s1-engine-context-compaction-mimo-20260513.md` 和
`docs/reviews/gateflow-code-review-host-p0-s1-engine-context-compaction-ds-20260513.md`；code review 总控裁决已写入
`docs/reviews/gateflow-code-review-host-p0-s1-engine-context-compaction-controller-adjudication-20260513.md`，C1 fix artifact 已写入
`docs/reviews/gateflow-fix-host-p0-s1-engine-context-compaction-20260513.md`。P0-S1 code re-review artifacts 已写入
`docs/reviews/gateflow-code-re-review-host-p0-s1-engine-context-compaction-mimo-20260513.md` 和
`docs/reviews/gateflow-code-re-review-host-p0-s1-engine-context-compaction-ds-20260513.md`，code re-review 总控裁决已写入
`docs/reviews/gateflow-code-re-review-host-p0-s1-engine-context-compaction-controller-adjudication-20260513.md`。P0-S1 accepted slice commit 为 `ad6d116`。P0-S2 implementation artifact 已写入
`docs/reviews/gateflow-implementation-host-p0-s2-docs-context-compaction-20260513.md`。P0-S2 code review artifacts 已写入
`docs/reviews/gateflow-code-review-host-p0-s2-docs-context-compaction-mimo-20260513.md` 和
`docs/reviews/gateflow-code-review-host-p0-s2-docs-context-compaction-ds-20260513.md`，code review 总控裁决已写入
`docs/reviews/gateflow-code-review-host-p0-s2-docs-context-compaction-controller-adjudication-20260513.md`。P0-S2 accepted slice commit 为 `6f6e716`。P0 两个 implementation slices 均已完成并通过 review loop，当前按用户确认进入 push / PR。P0 plan fix 已补充：明确 Runner HTTP overflow event-path 测试、P0-S1 pyright completion signal、
Phase 5 与 Phase 10 对 `budget_state=None` 的责任切分、多行 sentinel 搜索防线、`None` 与真实 `ContextBudgetSnapshot` 两条合法 contract 测试、`runner_events.py` docstring 目检，以及 `dayu/README.md` 术语精化边界。
