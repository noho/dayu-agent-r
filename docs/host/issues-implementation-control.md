# Host Issues Implementation Control

## 文档职责

本文档是 Host follow-up 中已由 GitHub Issue、umbrella issue、依赖链或过期裁决承接的 work units 实施总控文档。

本文档只承担实施编排职责：记录 issue-backed work unit 的范围、当前状态、issue owner / destination、进入条件、交付物、验证要求、review 结果、residual risk 和下一步入口。

本文档不替代 Host 设计真源，不承载新的架构决策，不作为实现细节说明书。若某个 work unit 的讨论发现需要修改架构边界、状态机、公共接口、durable schema、EventLog 语义或跨层契约，必须先更新设计真源，再更新本文档和对应 GitHub Issue。

## 设计目标

Host issue-backed follow-up 实施必须始终服务于以下目标：

- 生产级买方财报分析 Agent。
- 范式是“宿主强约束下的 LLM in the loop”。
- Host 对 Agent / Runner 的生命周期、取消、恢复、等待、上下文治理、审计与 durable truth 保持强约束。
- 严格遵守 `UI -> Service -> Host -> Engine` 分层边界，禁止反向依赖和跨层泄漏实现细节。
- 已有 GitHub Issue 的 work unit 必须尊重 issue owner / destination；不得在本文档中绕过 issue scope 抢先实施。
- 依赖型 work unit 必须等待前置 issue 完成后再进入 implementation gate；不得用测试私有入口或临时桥接伪造 production-grade 验收。
- 过期失效 work unit 只保留留痕，不作为实施入口。

任何 plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项选择削弱这些目标，应停下来修正设计真源、本文档或对应 GitHub Issue 后再继续。

## 真源层级

Host issue-backed follow-up 实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、等待、上下文治理和关键治理路径

docs/host/issues-implementation-control.md
  -> issue-backed follow-up 实施编排文档
  -> 记录已由 GitHub Issue / umbrella / dependency / obsolete 裁决承接的 work units、当前状态、进入 / 退出条件、交付物、验证要求、review 结论和 residual risk

GitHub Issues
  -> 对应 work unit 的外部执行 owner / destination
  -> 记录 issue scope、讨论、PR 关联和跨文档追踪状态
```

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到设计真源，再更新本文档对应 work unit 的范围、非目标、验收信号和对应 GitHub Issue。

术语必须遵循项目级术语真源和 Host 设计真源。planning、implementation、review、fix 与 re-review 不得自行重解释 `Session`、`Run`、`Attempt`、`EventLog`、`HostEvent`、`EngineEvent`、`WAITING`、`RECOVERING`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`、`ToolRuntime`、`Conversation Memory` 等术语。若发现术语缺失或冲突，应先讨论并同步真源文档，再继续推进。

## 管理范围

本文档只管理以下类型的 work units：

- 已有独立 GitHub Issue owner / destination 的 work unit。
- 已并入 umbrella issue 或 child issue 的 work unit。
- 必须等待其它 issue 完成后才能实施的依赖型 work unit。
- 已裁决过期失效，但仍需要在总控中保留留痕，避免后续误实施的 work unit。

本文档不管理未建立 GitHub Issue 且可独立推进的 work unit。若某个 work unit 后续获得新的 GitHub Issue owner / destination，必须先在本文档中新增或更新对应条目，再按本文档状态进入 discussion / plan / implementation gate。

## 工作流

Host issue-backed work unit 采用以下工作流：

```text
read issues-implementation-control.md
  -> select one work unit
  -> inspect current GitHub Issue / dependency / obsolete status
  -> inspect current code and tests
  -> discuss scope, non-goals, risk, and design sufficiency with the user
  -> update docs/host/design.md first if architecture or public contract changes are needed
  -> update this control doc and the GitHub Issue if scope, status, owner, residual risk, or entry point changes
  -> generate code-generation-ready plan for the selected work unit when dependencies are satisfied
  -> review plan
  -> user confirmation
  -> implement through the current gate workflow
  -> verify tests, pyright, and relevant README/doc sync
  -> run review / re-review
  -> update current status, artifacts, commits, residual risk, GitHub Issue state, and next entry point
```

每次只推进一个 work unit。进入 plan gate 前，必须先完成 issue / dependency / code 核对和 scope discussion，确认该 work unit 仍应在当前 owner 下推进。

work unit plan 必须基于：

- Host 设计真源；
- 本文档中对应 work unit 的状态、issue owner / destination、目标、非目标、验收信号；
- 对应 GitHub Issue 的当前 scope；
- 代码核对得到的直接证据。

plan 不得从旧设计稿、旧代码路径、非真源讨论记录或 reviewer 个人偏好推导架构边界。

plan 文档应放在 `docs/host/` 下；plan review、plan fix、plan re-review、implementation review、fix、re-review 和总控裁决 artifact 放在 `docs/reviews/` 下。

每个 work unit discussion 至少需要确认：

- work unit 目标与 success signal；
- 是否服务于本文档的设计目标；
- Host 设计真源是否足够具体；
- 对应 GitHub Issue 是否仍是正确 owner / destination；
- scope boundary、non-goals 与 stop conditions；
- 是否需要修改设计真源或 GitHub Issue；
- 是否存在会阻塞 code-generation-ready plan 的架构、状态机、公共接口、schema、持久化、依赖 issue 或测试问题。

## 仓库发布约定

Host issue-backed follow-up 实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners、GitHub Issue destination 和 next entry point。用户授权进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

## Slice 切分原则

每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿稳定模块 ownership、公共契约、状态机边界、存储边界、projection 边界、issue dependency 边界或测试矩阵边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。

如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | Host issue-backed follow-up implementation backlog |
| gate | discussion-ready |
| implementation status | not-started |
| active work unit | none selected |
| default next work unit | WU-CM-01 |
| next entry point | discussion：确认默认下一条、对应 GitHub Issue 状态和依赖是否满足；随后进入 plan / implementation / review |
| design source | 由 phaseflow 调用参数提供；本文档只维护 issue-backed 实施总控状态 |
| plan artifacts | none |
| implementation commits | none |
| review artifacts | none |
| aggregate review artifacts | none |
| draft PR status | not-started |
| blocking open questions | none；如果用户不接受默认顺序，需要先指定 active work unit |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码 / issue 核对入口，但还未形成 code-generation-ready plan。
- `blocked-by-issue`：需要等待指定 GitHub Issue / umbrella / dependency 完成。
- `obsolete`：已裁决过期失效，不作为实施入口。
- `planning`：正在形成或 review code-generation-ready plan。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。

## 推进规则

- 每次只推进一个 work unit。
- 先做 GitHub Issue / dependency / 代码核对，再进入方案和实现。
- 已明确 `blocked-by-issue` 或 `obsolete` 的 work unit 不得绕过状态进入 implementation gate。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；压力测试和长耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查、稳定文档说明和对应 GitHub Issue 状态。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、artifact、commit、review 和 residual risk 信息。

## Residual Risk / 遗留问题追踪

本章节专门追踪实施过程中发现但未在当前 work unit 内关闭的 residual risk、遗留问题、测试缺口、设计疑问、issue dependency 和后续 owner。不得把这类事项只停留在对话、review artifact、implementation report 或 GitHub Issue comment 中。

追踪规则：

- 每条 tracking item 必须有稳定 id、来源 work unit、状态、owner / destination 和下一步动作。
- `ready-to-open-draft-PR` 前，所有 tracking items 必须处于 `closed`、`deferred-with-owner` 或 `transferred-to-issue`，不得保留无 owner 的 open item。
- 如果 residual risk 需要修改 Host 架构、公共契约、状态机、durable schema 或 EventLog 语义，必须先同步设计真源，再更新本表和对应 GitHub Issue。
- 如果 residual risk 已由代码核对证明不存在，应标记 `closed` 并记录关闭依据，不继续保留为模糊风险。

状态值：

- `open`：仍需当前 work unit 或本轮 phase 处理。
- `deferred-with-owner`：明确后续 owner / work unit / issue，当前 work unit 不处理。
- `transferred-to-issue`：已迁移到独立 GitHub Issue 或等价外部追踪项。
- `closed`：已通过实现、测试、设计裁决或代码核对关闭。

| ID | 来源 | 类型 | 状态 | Owner / Destination | 下一步 | 记录 |
|---|---|---|---|---|---|---|
| none | - | - | closed | - | - | 当前没有未分配 residual risk 或遗留问题。 |

## 当前 Work Units

| Work Unit | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|
| WU-CM-01 | Conversation Memory overall optimization | GitHub Issue #81 | #81 umbrella 的正式 implementation entry point |
| WU-CM-02 | working_assumptions 生产者语义 | GitHub Issue #81 | 已纳入 Conversation Memory 整体优化，不单独实施 |
| WU-CM-03 | fact-candidate-only validation failure 策略 | GitHub Issue #81 | 已纳入 Conversation Memory 整体优化，不单独实施 |
| WU-CM-04 | minimum preserve 与 Fins 事实边界 | GitHub Issue #81 / Fins integration | 已纳入 Conversation Memory 整体优化与 Fins 边界 |
| WU-FINS-01 | Fins provider and storage integration | GitHub Issue #82 | 迁移可靠 Fins 代码，只允许接口适配 |
| WU-PROJ-01 | Projection catch-up budgeting | GitHub Issue #86 | memory pre-dispatch projection catch-up budgeting |
| WU-LIFE-03 | Active cancel watchdog | GitHub Issue #91 / #87 umbrella | Host lifecycle watchdog target |
| WU-GOV-01 | Host governance terminal taxonomy | GitHub Issue #88 | 引入 `REJECTED` |
| WU-CTX-01 | Provider tokenizer / sizing adapter | GitHub Issue #20 | provider-specific context sizing |
| WU-WAIT-01 | Callback endpoint / auth / replay | GitHub Issue #89 | wait callback adapter |
| WU-WAIT-02 | Production poller loop / backoff / fencing / retry | GitHub Issue #90 | production poller loop |
| WU-WAIT-03 | External job physical cancel / revoke / abandon | GitHub Issue #92 / #87 umbrella | WAITING external job lifecycle |
| WU-WAIT-04 | UI / Service production-grade awaiting E2E smoke | depends on #89 / #90 / #92 | dependent smoke，不独立实施 |
| WU-CM-05 | LLM compaction proposal typed parsing | GitHub Issue #93 / #81 child | deferred behind #81 |
| WU-CM-06 | Terminal summary text policy convergence | GitHub Issue #94 / #81 child | deferred behind #81 |
| WU-CM-07 | Evidence validation and pinned state cleanup | obsolete / #81 semantic model | 过期失效，不独立推进 |
| WU-CM-08 | Compaction material readability and smoke maintenance | GitHub Issue #95 / #81 child | #81 子任务，测试可维护性 cleanup |

## WU-CM-01 Conversation Memory Overall Optimization

### 状态

GitHub Issue #81 当前是 Conversation Memory 整体优化 umbrella issue。Issue body 明确它不是 code-generation-ready implementation plan；本 work unit 是将 #81 通过 phaseflow / gateflow 转化为可实施 scope、plan、slices、review 和验收闭环的正式入口。

### 目标

- 将 Conversation Memory 的语义类型与 prompt budget / assembly policy 分离，避免继续把 `stable layer`、`history pool`、`recent raw turns floor` 这类预算策略当作顶层 memory 心智模型。
- 固定 Memory Truth / Store、Semantic Memory Indexes、Prompt Assembly 三层边界：EventLog / artifacts / accepted evidence 保持真源地位，memory snapshot 保持 bounded read model，不成为新的事实真源。
- 裁决并实现 #81 scope 内优先级最高的语义 memory 能力，例如 Trace Memory、Evidence / Fact Memory、Session Summary Memory、Answer Anchor Memory、Forward Intent Memory，以及 User Profile Memory 的 durable store 边界。
- 将 WU-CM-02、WU-CM-03、WU-CM-04 等已并入 #81 的问题纳入统一 semantic model 裁决，不再对旧 memory shape 做局部补丁。
- 为 compact repair 固定策略：一次 repair LLM interaction 收集并修复多个 invalid fields，Host 合并旧 proposal 的 valid fields 与 repair patch 后必须完整 revalidate，成功后才可写 `CONTEXT_COMPACTED`。
- 对 trace / tool-output refs + recall tool 方向先做 research gate；不得在没有借鉴成熟 Agent / Memory 系统约束前自行发明 production recall 机制。
- 产出 code-generation-ready plan，明确 slices、allowed files / modules、schema / contract 变更、测试矩阵、migration strategy 和 residual risk owner。

### 非目标

- 不把 #81 issue body 直接当作 implementation plan。
- 不一次性实现所有 speculative memory 能力；必须按可验证闭环切 slice。
- 不让 assistant final answer、summary、answer anchor、user claim 或 user profile 自动升级为 evidence-backed facts。
- 不让 memory snapshot 替代 EventLog / artifacts / accepted evidence。
- 不在 research gate 前实现任意 ref probing / recall tool。
- 不为旧 `pinned_state` / `working_assumptions` 结构保留兼容 wrapper 或局部止血。

### 验收信号

- #81 被拆成 code-generation-ready phase plan 和可 review 的 implementation slices。
- 设计真源明确 semantic memory categories 与 prompt assembly / budget policy 的边界。
- tests 能区分 trace continuity、evidence-backed facts、session summary、answer anchors、forward intent、profile boundary 和 prompt assembly budget behavior。
- compact repair 测试覆盖多个 invalid fields 一次 repair、Host 合并 valid + repaired fields、完整 revalidation、repair exhausted fail closed。
- trace / tool-output refs + recall tool 若进入后续 scope，必须先有 research artifact 和明确 design constraints。
- WU-CM-02、WU-CM-03、WU-CM-04、WU-CM-05、WU-CM-06、WU-CM-08 的后续状态被更新为 closed、deferred-with-owner 或 transferred-to-issue。

## WU-CM-02 Working Assumptions Producer Semantics

### 状态

已纳入 GitHub Issue #81 的 Conversation Memory 整体优化；保留留痕，不单独进入 discussion / implementation。

### 目标

- 裁决 `working_assumptions` 是否保留。
- 若保留，定义 compact / user / diagnostic event 生产者。
- 若不保留，通过 schema / durable / renderer gate 删除该字段。

### 非目标

- 不让 `working_assumptions` 承载工具事实或财报事实。
- 不绕过 evidence-backed fact 主链路。
- 不在 #81 前抢先按旧 memory shape 做局部修补。

### 验收信号

- 字段存在即有明确生产者、消费者和测试。
- 字段不存在则 schema、snapshot codec、durable items、RunInputBuilder 和测试全部同步收敛。

## WU-CM-03 Fact-candidate-only Validation Failure Policy

### 状态

已纳入 GitHub Issue #81 的 Conversation Memory 整体优化；保留留痕，不单独进入 discussion / implementation。

### 目标

- 裁决 `CONTEXT_COMPACTED` 中 fact candidates 非法但其它 compact output 合法时，是否继续 partial materialize。
- 统一 quality check、payload validation、memory projection、diagnostic 与用户可见失败策略。

### 非目标

- 不在 #81 前抢先裁决新 memory 语义。
- 不让非法 fact candidates 进入 evidence-backed facts。

### 验收信号

- 测试覆盖 fact candidates invalid / non-fact compact fields invalid 两类路径。
- partial materialize 或 fail closed 的策略在 projection、diagnostic 和用户可见结果上一致。

## WU-CM-04 Minimum Preserve And Fins Fact Boundary

### 状态

已纳入 GitHub Issue #81 的 Conversation Memory 整体优化与后续 Fins integration 边界；保留留痕，不单独进入 discussion / implementation。

### 目标

- 确认 `minimum preserve` 继续作为 bounded continuity item，而不是事实真源。
- 明确后续 Fins 接入时不得把 minimum preserve 文本当作财报事实引用。

### 非目标

- 不把 minimum preserve 标成 verified / sourced fact。
- 不让 UI / Service 把 continuity item 当作财报引用真源。

### 验收信号

- Fins / ToolRuntime / RunInputBuilder 文档和测试均不把 minimum preserve 当 stable fact。
- minimum preserve 的 source refs 只服务 continuity，不成为财报引用真源。

## WU-FINS-01 Fins Provider And Storage Integration

### 状态

已纳入 GitHub Issue #82。Issue scope 是从 `dayu-agent/fins` 迁移长期运行验证可靠的 Fins 代码，只允许修改 `@tool` 与 ToolDiscovery 接口适配部分，不允许修改其它 Fins 业务代码。

### 目标

- 新增或接入 `dayu.fins.storage` 下的财报仓储协议与实现。
- 财报工具 provider 通过 ToolsDiscovery 进入 Host，而不是由 Host 扫描业务工具。
- 财报工具结果进入 accepted evidence 主链路。

### 非目标

- 不把财报原文存取放入 Host / Service / runtime。
- 不把 minimum preserve 或 compact summary 当作财报事实真源。
- 不修改已长期运行验证可靠的 Fins 业务代码，除 `@tool` 与 ToolDiscovery 接口适配外。

### 验收信号

- Fins storage、tool provider、ToolsDiscovery 和 ToolRuntime accept path 有端到端测试。
- `evidence_backed_facts` 仍只由 Host-governed compact extraction 生成。

## WU-PROJ-01 Projection Catch-up Budgeting For Memory Pre-dispatch Path

### 状态

由 GitHub Issue #86 跟踪并实施。

### 目标

- 聚焦 memory projection catch-up / rebuild 在 pre-dispatch 路径上的预算、背压和诊断边界。
- 为 memory catch-up 定义总预算，而不仅是单批大小，例如 max batches、max scanned events、timeout 或等价 bounded execution policy。
- 明确 admission after-commit 的 catch-up 只能是 bounded best-effort 或 wake background supervisor，不得在 command path 上无上限追平。
- 明确 dispatch 前 catch-up / rebuild 的行为：成功追到 required cursor 时继续 dispatch；超预算或失败时产生结构化 diagnostic。

### 非目标

- 不改变 EventLog 作为投影真源的语义。
- 不让 projection lag 影响 recovery truth。
- 不把 Audit / Tool Trace / Outbox 纳入本条。
- 不重写 ProjectionRunner 为大型调度系统。
- 不把所有 projection sink 合并成 God runner。

### 验收信号

- memory projection catch-up 的单批大小与单次总预算边界均有明确代码或配置表达。
- admission after-commit catch-up 不会无上限同步追平大量 EventLog。
- dispatch 前 memory catch-up / rebuild 超预算或失败时有结构化 diagnostic，且不会改写 EventLog / Run / Attempt governance truth。
- 测试覆盖 bounded catch-up、required cursor 已覆盖、lag / failure / rebuild 超预算不误触发 recovery，以及 Audit / Tool Trace / Outbox 不被改成 command-path blocking sink。

## WU-LIFE-03 Active Cancel Watchdog And Post-cancel Timeout

### 状态

已纳入 GitHub Issue #91；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 active Attempt cancel watchdog target，不单独引入第二套 watchdog runtime。

### 目标

- 复用 #87 的 Host lifecycle watchdog / supervisor，不另建 active cancel 专属 watchdog。
- 裁决 active cancel watchdog owner、timeout policy、Run / Attempt 终态、diagnostic payload、late terminal race 与 session cancel replay 语义。
- 明确 post-cancel timeout 后 Run / Attempt / diagnostic 的收敛路径，以及 first-committer-wins / late rejection 规则。

### 非目标

- 不直接 kill 不属于 Host 管理的外部进程。
- 不把 provider-specific cancel API 硬编码进 Host 核心。
- 不把 scheduler close 设计成 active cancel timeout closeout。

### 验收信号

- provider 卡死、stream 不结束、worker task 不响应 cancellation 时都有可测试 closeout。
- terminal event 与 diagnostic 不重复、不互相矛盾。
- GitHub Issue #87 明确跟踪设计问题、非目标和验收测试；实施前需要先回到 design gate。

## WU-GOV-01 Host Governance Terminal Taxonomy

### 状态

已裁决需要引入 `REJECTED`；后续由 GitHub Issue #88 跟踪设计与实施。

### 目标

- 引入 `RunStatus.REJECTED`，用于表达 Host governance 在执行前或执行外拒绝 Run，而不是复用执行失败语义。
- 裁决 rejected Run 的 canonical EventLog taxonomy，例如是否新增 `RUN_REJECTED`。
- 明确 hard threshold / compact failure / pre-dispatch governance failure 等场景哪些进入 `REJECTED`，哪些仍保留为 `FAILED`。
- 同步 Run status、EventLog reason、projection、public contract、retry / replay 前置条件、outbox / HostEvent 映射、文档与测试。

### 非目标

- 不为单个 failure reason 临时增加状态。
- 不让 Attempt terminal taxonomy 承担 Run-level governance 语义。

### 验收信号

- 用户可见 terminal status 与治理失败 reason 单一、不重叠。
- public contract freeze test 同步更新。

## WU-CTX-01 Provider Tokenizer / Sizing Adapter

### 状态

已由 GitHub Issue #20 跟踪；Issue 已更新为 WU-CTX-01 当前 scope。

### 目标

- 为不同 provider 的 token / context sizing 建立 typed adapter。
- 让 proactive / reactive compact 决策使用同一 sizing 入口。

### 非目标

- 不在 Context Governance 中硬编码 provider 名称分支。
- 不让 Engine provider 实现反向依赖 Host。

### 验收信号

- provider sizing 差异有单元测试。
- compact 前后 budget estimate 与 provider adapter 输出一致。

## WU-WAIT-01 Callback Endpoint / Auth / Replay

### 状态

research 已写入 GitHub Issue #89；本条后续按 callback adapter -> common `resolve_wait` pipeline 的方向实施。Claude Code 的 background subagent / lifecycle completion 行为可作为参考；Codex 具备 subagent orchestration，但公开 callback / hook surface 不应被假设为稳定生产 primitive。

### 目标

- 设计 callback endpoint 的认证、幂等 replay、payload digest 和错误分类。
- 将 callback 与现有 wait resolve / idempotent replay 语义对齐。
- 明确 callback endpoint 只是 transport adapter：认证、解析、校验 envelope 后调用 Host `resolve_wait`；不得直接写 EventLog、Run、Attempt 或 wait record。
- callback / poller / manual resolve 必须共用同一个 durable wait resolution pipeline。

### 非目标

- 不把 HTTP framework 细节放入 Host 核心。
- 不绕过 durable wait state。
- 不追求 Claude Code background subagent UI parity；本条只跟踪 Host wait completion callback 语义。

### 验收信号

- callback 重放、乱序、摘要不匹配、未知 wait id 都有测试。
- endpoint 层只映射输入，状态裁决仍由 Host wait 语义完成。
- 认证失败、cancelled / lost wait 的迟到 callback、同 key 不同 outcome digest 的 idempotency conflict 都有明确 diagnostic。

## WU-WAIT-02 Production Poller Loop / Backoff / Fencing / Retry

### 状态

已确认是较大的 production feature，并已用 GitHub Issue #90 跟踪。本条实施前仍需回到 design gate 讨论并更新设计真源；当前文档只冻结问题定位与实施方向。

### 目标

- 实现或接入 production poller loop。
- 为 adapter error、rate limit、cancelled abandon 和 repeated not-ready 设计 backoff。
- 防止同一 wait 被并发 poller 重复处理。
- 明确 poller loop 只负责推进 Host wait 状态，不直接向 UI 返回事件；UI / Service 仍通过 `watch_session_events` 观察 `resolve_wait` 产生的 Host events。
- 设计短生命周期 in-flight claim / fencing，防止多 poller 同时 poll / resolve 同一 wait；该 claim 不是 Attempt owner、不是 EventLog truth、不是外部 job owner。

### 非目标

- 不把 poller 做成通用 scheduler God object。
- 不让 backoff 状态污染 wait durable contract。
- 不在本条内实现 callback auth / replay。
- 不在未完成 design gate 前修改设计真源的 poller production 细节。

### 验收信号

- 同一 wait 在多 poller 下不会并发 resolve。
- adapter intermittent failure 不会丢 wait，也不会 tight loop。
- production loop 能后台运行并可被 Host close / supervisor clean stop。
- ready / lost outcome 仍必须通过 common `resolve_wait` pipeline，事件由现有 Host watch path 观察。

## WU-WAIT-03 External Job Physical Cancel / Revoke / Abandon

### 状态

已纳入 GitHub Issue #92；GitHub Issue #87 是共享 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 WAITING external job cancel / revoke / abandon target，不单独引入第二套 watchdog runtime。

### 目标

- 为外部 job 定义 best-effort cancel / revoke / abandon 协议。
- 明确外部取消失败、超时、重复取消和晚到结果的处理方式。
- 复用 #87 的 Host lifecycle watchdog / supervisor，外部 job 作为 WAITING-state watch target；target-specific adapter 只负责 provider cancel / revoke / abandon 能力。

### 非目标

- 不要求所有 provider 都支持 physical cancel。
- 不把外部 job id 当作 Host durable 主键。
- 不另建独立 wait-job watchdog；不得与 #91 的 active Attempt watchdog target 形成两套 runtime。

### 验收信号

- 支持取消和不支持取消的 adapter 都有契约测试。
- late result 与已 abandon / cancelled wait 的 diagnostic 一致。

## WU-WAIT-04 UI / Service Production-grade Awaiting E2E Smoke

### 状态

依赖 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92；不是可独立实施的 work unit。前置能力完成后，本条才作为 production-grade end-to-end smoke 进入 implementation gate。

### 目标

- 增加一条 production-grade public E2E smoke，冻结 UI / Service 正常接入 Host wait governance 的生产工作流。
- 流程覆盖 `open_host` 装配、`ensure_session`、`submit_followup(queue)`、记录 `accepted_run_id`、watch / `get_run` 观察 `WAITING`、生产 poller 或 callback 入口完成 wait resolution、同一 Run 最终产生 terminal `HostEvent` / outbox item。
- 验证 UI / Service 不直接依赖 ToolRuntime、EngineEvent、dispatch row、scheduler internals 或 wait record durable row 作为展示契约。

### 非目标

- 不在本条重新实现 callback endpoint、production poller loop、backoff、fencing 或外部 job physical cancel。
- 不新增 UI 专用 Host 分支。
- 不把 wait record 列表查询提升为普通 UI 必需契约。
- 不接受仅用 manual resolve 或测试私有 durable wait id 桥接完成的 smoke 作为 production-grade 验收。

### 验收信号

- smoke 测试能证明同一个 public watcher 在 Run 进入 `WAITING` 后继续接收由生产 poller / callback 恢复后的 terminal event。
- smoke 测试断言 `get_run(run_id).status == WAITING` 时 UI 可展示等待态，生产 wait resolution 后 Run 继续推进并最终成功。
- offline / reconnect 场景至少通过 outbox 证明 terminal item 可补读。
- 测试代码不从 UI / Service 路径导入 Host 内部 ToolRuntime、dispatch、scheduler 或 durable wait mutation API。

## WU-CM-05 LLM Compaction Proposal Typed Parsing

### 状态

GitHub Issue #93，作为 GitHub Issue #81 的后续子任务；deferred behind #81。#81 会调整 Conversation Memory 与 compact JSON 的目标 shape；本条不应抢先实施。

### 目标

- 在 #81 确定新的 compact JSON shape 后，将 LLM proposal parsing 收敛为显式 typed validation。
- 消除 unchecked cast、宽 payload 和模糊错误分类。
- 固定转换边界：LLM raw final answer -> parse JSON -> typed LLM compaction proposal -> Host-owned `CompactionCandidate` 或 #81 后等价 typed contract。

### 非目标

- 不在 #81 前抢先实现。
- 不改变 compact output 的业务含义。
- 不放宽非法 proposal 的接受条件。

### 验收信号

- 每个 post-#81 proposal 字段都有直接验证路径。
- invalid proposal 的 diagnostic 能定位字段和原因。
- malformed JSON、缺必填字段、字段类型错误、未知 label / ref、数组超限、非法 enum / patch operation 都有测试。

## WU-CM-06 Terminal Summary Text Policy Convergence

### 状态

GitHub Issue #94，作为 GitHub Issue #81 的后续子任务；deferred behind #81。terminal summary、assistant conclusion、episode summary、answer anchor 与 continuity 的语义边界会受 #81 Conversation Memory 整体优化影响。

### 目标

- 在 #81 后收敛 terminal summary 的来源、截断、渲染和 fallback policy。
- 避免 terminal summary 与 compact summary、assistant conclusion 语义重叠。
- 固定成功、失败、取消、lost、governance failure 与 compacted episode summary 的文本 policy 矩阵。

### 非目标

- 不在 #81 前抢先实现。
- 不把 terminal summary 变成事实引用源。
- 不改变 Run terminal taxonomy。
- 不让 compact / episode summary 冒充 terminal summary 或 final answer。
- 不借本条引入新的 public result read API。

### 验收信号

- terminal summary 在 success、failure、cancel、governance failure 下语义一致。
- 渲染测试覆盖空 summary、长 summary 和 compact 后 summary。
- memory projection 只在 policy 允许时把 terminal summary 用作 continuity，不得升级为 evidence-backed fact。

## WU-CM-07 Evidence Validation And Pinned State Cleanup

### 状态

过期失效，不再作为独立 work unit 推进。Conversation Memory semantic model cleanup 由 GitHub Issue #81 跟踪。

### 目标

- 无独立实施目标。
- 后续若 #81 仍需要 evidence validation 子任务，应按新的 semantic memory 分类重新建 issue / work unit，不复用本条。

### 非目标

- 不再围绕 `pinned_state` 做局部 cleanup。
- 不在 #81 前为 confirmed subjects、current goal、open questions 等字段预设最终 owner。

### 验收信号

- 无独立验收信号；由 #81 及其后续 scoped issues 重新定义。

## WU-CM-08 Compaction Material Readability And Smoke Maintenance

### 状态

GitHub Issue #95，作为 GitHub Issue #81 的子任务；定位为测试可维护性和 compaction material readability cleanup，不负责裁决 Conversation Memory 语义模型。

### 目标

- 改善 compaction material 的 chunking、可读性和测试 fixture 可维护性。
- 保持 public memory scenario smoke 覆盖关键用户路径。
- 让 smoke 失败能定位到输入构造、material pack / chunking / prompt-local labels、compactor request / proposal、memory projection 或 RunInput rendering 边界。

### 非目标

- 不改变 memory snapshot schema。
- 不裁决或实现 #81 semantic memory categories。
- 不用 snapshot 大量金文件掩盖语义测试缺失。
- 不引入新的 compactor JSON 语义。

### 验收信号

- compaction material 结构稳定、易读，且变更有小范围测试。
- smoke 失败能定位到输入构造、compaction、projection 或 rendering 边界。
- LLM-facing material 保持可读，不暴露 EventLog ledger wrapper、payload descriptor、digest 或 Host provenance internals。
