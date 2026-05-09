# Host 迁移总控计划

## 1. 计划状态

本文档是 Host 迁移总控计划草稿，用于指导总控 Agent 分阶段派 Agent 编写 / 修复 phase plan，
并生成代码实施、代码修复与 review prompt，由用户手工派 Agent 完成代码实施、代码修复与 review。
它不是单阶段 handoff plan，也不是实现文档。

当前总控状态：

- P1 已通过 PR #16 合入 `main`，当前确认基线为 `051cf20`。
- P1.5 已通过 PR #17 合入 `main`，merge commit 为 `ec1627c94f352205ee77bcd992d652e677fa0ebb`。
- P2 已通过 PR #18 合入 `main`，merge commit 为 `3d86eefd4bd8b99b24c638735220d9ee571255f7`。
- P3 已通过 PR #19 合入 `main`，merge commit 为 `b20e792 Host P3 conversation memory (#19)`。
- P4 已通过 PR #21 合入 `main`，merge commit 为 `843fb99 Host P4 context overflow compact (#21)`。
- P5 已通过 PR #22 合入 `main`，merge commit 为 `a825b4c Host P5 no-governance multiturn smoke (#22)`。
  P5 已落地 No-Full-Governance Multi-Turn Smoke、公共 `@tool` / `ToolDefinition` 声明、
  LLM-facing truncation hint、framework `fetch_more`、真实 provider `mimo-v2.5-pro-plan` +
  `huge_echo` tool calling smoke、Host / Engine P1-P5 日志可观测性梳理与 review 修复。P5 code review findings
  已在 `docs/reviews/code-review-20260508-1039.md` 与
  `docs/reviews/code-review-20260508-1122.md` 标注修复状态；PR review findings 已在
  `docs/reviews/pr-22-review-20260508-1211.md` 标注修复状态，用户复核通过。
- P5.5 deferred scope reconciliation 已完成文档收口：已把 P1-P5 漏排 / 误排 / 已落地的 deferred
  能力重新安排到 P6+，并经开放式架构 review 讨论后补充最小 observer / sink、`LocalRunHarness`
  防 God Object、OLD public interface 调研前置、代表性 web tool smoke、P12-P14 保留等总控约束。
- P5.5 已通过 PR #25 合入 `main`，merge commit 为 `758fd4a Host P5.5 deferred scope reconciliation (#25)`。
- P6 Durable EventLog / Run State / Projection 已完成实现、修复与复审：落地 SQLite WAL durable
  `RunEventStore`、Run / Attempt 最小持久状态、同事务 terminal result snapshot、ProjectionCoordinator、
  memory / timeline / audit observer、checkpoint / retry / lag 观察、真实 `harness.start_run` 路径
  smoke。P6 code / architecture / concurrency review findings 已在
  `docs/host/phase6-code-review.md`、`docs/host/phase6-architecture-review.md`、
  `docs/host/phase6-concurrency-review.md` 标注修复状态；复审结果见
  `docs/host/phase6-fix-rereview.md`，结论通过。P6 已通过 PR #26 合入 `main`，
  merge commit 为 `499b9b1 Host P6 durable EventLog (#26)`。
- P7 Tool Trace Projection / Sink plan gate 已通过：plan 见 `docs/host/phase7-plan.md`，
  plan review 见 `docs/host/phase7-plan-review.md`，复审见
  `docs/host/phase7-plan-rereview.md`，结论通过。计划阶段提交为
  `f55f5ac docs: finalize host p7 tool trace plan`。P7 代码实施、常规 code review、
  OLD / NEW review、架构边界 review、review fix 与复审均已完成，复审见
  `docs/host/phase7-fix-rereview.md`，结论通过；ToolRuntime `iteration_id` root-cause
  follow-up review 见 `docs/reviews/code-review-20260508-001.md`，Finding 001 / 003 已修复并复审通过；
  PR review 见 `docs/reviews/pr-37-review-20260509-0829.md`，finding 已修复。残余风险已拆分到
  GitHub issues #29-#36。P7 已通过 PR #37 合入 `main`，merge commit 为
  `5fccad4 Host P7 tool trace projection (#37)`。
- 当前进入 P8 Attempt Lease / Recovery / 多进程并发基础 plan gate；工作分支为
  `migration/host-p8-attempt-lease-recovery`。

每个 Phase 进入实现前，必须另写可交接的 phase plan，细化到迁移 Agent 可以直接接手：
目标、非目标、边界、文件级改动清单、契约变化、状态机、测试清单、验证命令、review gate、
停止条件、风险、待确认项、实施完成汇报格式。

本文档只固定总控节奏、阶段顺序、阶段边界和每阶段必须产出的文档 / review / GitHub 工件。

## 2. 依据

本计划依据以下材料：

- `docs/host/design.md`
- `docs/host/interface-discussion-notes.md`
- `docs/host/design-best-practice-review.md`
- `docs/host/design-optimal-review.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- GitHub issue #3：取消治理增强。
- GitHub issue #4：ToolExecutionOutcome 扩展分支跟踪。
- GitHub issue #20：Host token estimator 接入 provider 官方 token 计数算法。
- GitHub issue #23：Host context governance 跟踪。
- GitHub issue #24：Host memory governance、长期记忆与 public memory edit / reset / forget 跟踪。
- OLD conversation memory 设计：`https://github.com/noho/dayu-agent/issues/48`
- `AGENTS.md`

`docs/host/design.md` 是 Host 接口与架构边界真源。Engine 只提供强类型 `EngineEvent`、
函数式入口和 `ToolExecutor` 协议，不能把 Host ToolRuntime、trace、memory、transcript、
context overflow 治理回流到 Engine。

## 3. 总控工作流

每个 Phase 默认使用 `$gateflow` / Gateflow 工作流进行计划、review、实施切片、修复、复审、
commit、PR 与收口。本文档不另造一套与 Gateflow 冲突的流程，只记录 Dayu Host 迁移对
Gateflow 的项目级扩展和固定约束。若本文档某条流程与 `$gateflow` 的通用 gate 冲突，
优先按 `$gateflow` 的 gate 语义执行，再叠加本节明确写出的 Dayu Host 扩展。

Gateflow 当前没有“一开始开独立分支”的前置步骤；Dayu Host 迁移额外要求每个 Phase 在进入
plan gate 前先从最新主线或用户指定基线创建独立分支。

每个 Phase 都必须使用独立分支。默认分支名：

```text
migration/host-p{phase}-{short-name}
```

如果用户指定其它分支名，以用户指令为准。

当前仓库远端名是 `github`，不是 `origin`。总控 Agent 执行 push / PR 前必须先用
`git remote -v` 或等价命令确认远端名，禁止假设远端一定叫 `origin`。本仓库默认 push
形态为 `git push -u github <branch>`。

每个 Phase 的固定节奏：

1. 从最新主线或用户指定基线开新分支。
2. 派 Agent 写 phase handoff plan。除纯文档 / 极小修复外，plan 必须拆成若干可独立交付的
   implementation stage / slice。每个 slice 必须足够小，原则上一个实施 Agent pass 加一个
   review pass 可以完成；若 slice 太大、无法干净 review，必须先拆分再实施。每个 slice 必须
   写明：slice id、短标题、目标、预期用户可见或契约可见结果、文件 / 模块 ownership、
   允许修改、明确非目标、前置依赖、测试 / 验证命令、完成信号、停止条件和预计上下文压力。
   slices 必须按依赖和风险排序；优先使用每步后系统仍可工作的 vertical slice。只有文件
   ownership 与契约边界完全不重叠时，才允许并行 slice。计划必须是 handoff-ready，可直接指导
   实施 Agent 生成代码；不能停留在方向讨论、概念设计或需要实施 Agent 自行补全关键边界的粗计划。
   禁止只写一个覆盖整个 phase 的大实施任务。
3. 派 review Agent 做 plan review；必要时派额外 review Agent 做 OLD / NEW 对比、最佳实践、
   架构边界或并发专项 review。plan review 必须检查 slice 是否过粗、ownership 是否清晰、
   测试是否只堆到最后、顺序是否容易诱导实施 Agent 提前做未来 slice；不合格时必须要求修 plan。
4. 总控 Agent 读取 plan review 结果并判断 finding 是否成立；成立时派 Agent 修 plan，修复 Agent 必须在对应
   review 文档的 finding 标题上标注修复状态。
5. 派 review Agent 复审修复后的 plan；若仍不通过，重复步骤 4-5，直到 review Agent 明确通过。
6. plan review 通过后，停下来等用户人工确认。
7. 用户确认后，commit phase plan 与 review 文档。
8. 总控 Agent 按通过 plan 的 implementation stage / slice 逐个生成实施指导 prompt，交给用户
   手工派迁移 Agent 生成代码。每个实施 Agent 只能执行当前 stage，不得提前实现后续 stage；
   若实施中发现当前 stage 过大、上下文窗口不足或需要跨 stage 改契约，必须停止并回报总控拆分 /
   修 plan，不得硬做。
9. 每个 stage 完成后，迁移 Agent 必须报告改动文件、验证结果、未覆盖项和是否触碰后续 stage。
   总控 Agent 判断是否进入下一 stage；对契约 / schema / state-machine / 并发 / durable storage /
   public interface 等高风险 stage，必须先生成 stage-level code review prompt 并完成修复 / 复审后，
   才能进入下一 stage。
10. 所有 stage 完成后，总控 Agent 生成 phase-level code review 指导 prompt，交给用户手工派
    Agent 执行整体 code review；必要时额外生成 OLD / NEW
   对比、架构边界、类型安全或并发专项 review prompt。
11. 用户提交 code review 结果后，总控 Agent 判断 finding 是否成立；成立时生成代码修复 prompt，
    交给用户手工派 Agent 修复代码。修复 Agent 必须在对应 code review 文档的 finding 标题上标注
    修复状态，总控 Agent 负责检查标注是否到位。
12. 总控 Agent 生成复审 prompt，交给用户手工派 Agent 执行复审；若仍不通过，重复步骤 11-12，
    直到用户复审通过。
13. code review 通过后，停下来等用户人工 review。
14. 用户确认后，commit 代码、测试和必要 README / docs 更新。若 Phase 被拆成多个高风险
    stage，总控可在用户确认后按 stage 分别 commit，或在 phase 收口时统一 commit；无论哪种方式，
    每个 commit 都必须只包含已通过对应 review gate 的改动。
15. 准备 PR 时，确认只包含本 Phase 范围内提交，push 并创建 ready PR；不创建 draft PR，
    除非用户明确要求。PR 创建后停下来等用户人工 PR review。
16. 用户提交 PR review 结果后，总控 Agent 判断 finding 是否成立；成立时生成代码修复 prompt，
    交给用户手工派 Agent 修复代码。修复 Agent 必须在对应 PR review 文档的 finding 标题上标注
    修复状态，总控 Agent 负责检查标注是否到位。
17. PR review 通过后，停下来等用户确认。若 review 由用户本人完成，则对应修复也必须由用户本人复核；
    总控 Agent 与其它 review Agent 不得替代用户复核结论。
18. squash merge PR 并删除远端分支默认由用户执行；只有用户明确指示总控 Agent 执行时，
    总控 Agent 才能执行 squash merge / delete branch。用户手工 merge 后，总控只记录状态。

禁止事项：

- 不在未通过 plan review 的情况下写生产代码。
- 不用总控 Agent 自己的复核替代用户 review / 复审结论；总控只负责派 Agent 写 / 修 phase plan、
  生成代码实施 / 代码修复 / review prompt、判断 finding 是否成立和维护修复状态。
- 不在 review finding 未标注修复状态的情况下声称 review 通过。
- 不把大 Phase 一次性塞给单个实施 Agent；若计划中已有多个 stage，必须按 stage 逐段实施、
  逐段验证。若实施 Agent 报告上下文窗口不足，总控必须拆分 stage 或修 plan。
- 不让实施 Agent 在当前 slice 中提前实现未来 slice；除非已通过 plan 明确授权多个 disjoint
  slice 并行，否则发现 drift 必须停止并回到总控。
- 不把多个 Phase 的实现混进一个 PR，除非用户明确批准合并。
- 不在用户确认前 commit / push / create PR / merge。
- 不把迁移过程要求写进 `docs/code_review.md`；该文档只写日常 review 当前事实专项。

## 4. 阶段总览

前半段目标是先跑通一个“没有完整生产治理”的多轮会话 smoke：

```text
EngineWorker
  -> Minimal EventLog / RunEventStore
  -> truncate / fetch_more
  -> Conversation Memory
  -> context overflow / compaction 协作
  -> no-full-governance multi-turn smoke
  -> deferred-scope reconciliation
```

这里的“没有完整生产治理”只表示先不实现完整多进程并发、恢复、Remote、Outbox、
audit hard-gate 等生产治理；不表示可以破坏分层、跳过强类型契约、绕过
`dayu.fins.storage`、绕过 append-before-stream EventLog 事实层，或把 Host 职责塞回 Engine。

P5.5 人工 review 后，P6 及以后阶段的总目标重写为：支持多进程并发 Full-Governance
Multi-Turn。后半段必须先建立 durable facts 与 observer / sink 基础，再把 tool trace 作为独立
phase 落地；随后建立多进程 attempt ownership，并在该基础上落地 Session / Run lifecycle、
完整 ToolRegistry、validation replay、outbox、remote、wait / suspend / resume、治理 hardening
与最终 full-governance smoke。

从 P6 开始，每新增一项 Host 治理能力，必须同步新增或更新一个 `utils/` 下的手工 smoke。该 smoke
用于让用户通过日志和关键摘要直接观察新增治理能力的真实执行路径；它不能替代单元 / 并发 / 恢复测试，
也不能输出大块 delta、大工具结果、scope token 或内部大 prompt。P5 的
`utils/smoke_host_multiturn_no_governance.py` 是 no-full-governance 纵向基线；P6+ 的每个治理
phase 都应提供对应 smoke，P16 再把这些验证面收束为 Full-Governance Multi-Turn Smoke。

| Phase | 名称 | 目标 | 主要输出 | 明确不做 | 验收信号 |
| --- | --- | --- | --- | --- | --- |
| P0 | 计划与议题同步 | 固定 Host 迁移总控计划，创建 / 更新必要 issue 与 review prompt 事实 | 本文档、plan review、必要 issue comment | 不写生产代码 | 用户确认可以进入 P1 |
| P1 | EngineWorker + 最小 Run Harness | 落地与 Engine 最接近的 Host capability：Local EngineWorker、最小 WorkerProxy、最小 Run 执行装配 | `dayu.host` 最小入口、LocalProxy、EngineWorker wrapper、EngineEvent -> RunEvent 翻译薄层、最小 `start_run` 测试入口 | 不做 Remote RPC、不做完整 Session governance、不做 memory、不做 truncate/fetch_more | 单 Run 可通过 Host 调 Engine 函数式入口并流出事件；EngineWorker / ToolExecutor 不暴露为 Host public API |
| P1.5 | Minimal EventLog / RunEventStore | 固定 P2-P5 共同依赖的最小事件事实层，避免旁路 transcript / memory facts | append-before-stream EventLog 契约、per-run cursor、canonical / preview 分层、最小 Run state 调和 | 不做完整 observer、不做 trace / audit sink、不做完整多进程 recovery | P2-P5 只能依赖 RunEventStore / canonical facts，不需要未来 P6 倒改事实来源 |
| P2 | ToolRuntime truncate / fetch_more | 把 OLD TruncationManager / cursor / TTL / scope token 迁到 Host / ToolRuntime 边界 | 工具结果截断契约、fetch_more 调用路径、cursor storage、TTL / scope token 测试、ToolRuntime 最小运行事实 | 不做完整 ToolRegistry 权限、不做业务工具迁移、不让 Engine 持有 cursor 管理；不实现 tool trace / audit / timeline observer | 工具结果可被截断，后续 fetch_more 可补读；截断 / 补读不是不可审计黑盒 |
| P3 | Conversation Memory / RunInputBuilder | 迁移 Host 上下文治理核心，使多轮上下文可构造 | RunInputBuilder 可消费事实、客户端 timeline 展示事实、只可观测 facts 三类边界；pinned_state、memory pool、tool facts projection | 不做 context overflow 完整协作、不做 Reply Outbox、不把 reasoning 回流运行态 | 多轮 Run 可以基于 Session / memory 构造下一轮输入；reasoning 只进展示 read model |
| P4 | Host Compact for Context Overflow | 把 OLD 中原本在 Engine 内做的 compact 搬到 Host，使 Engine context overflow 时仍能继续运行 | Host compact 入口、compact 输入 / 输出、Engine overflow 事件 / 错误映射、compact 后 attempt 输入重建 | 不实现完整 context governance；不引入 replay / validation 联动；不在 Engine 内实现 compact/retry | Engine 遇到 context overflow 时，Host 完成 compact 后继续运行或明确失败收口 |
| P5 | No-Full-Governance Multi-Turn Smoke | 将 P1-P4 与 P1.5 串成最小纵向 smoke，并落地最小公共 tool declaration 与 framework `fetch_more` 能力 | smoke CLI / test harness、端到端多轮测试、公共 `@tool` declaration / `ToolDefinition`、LLM-facing truncation hint、framework `fetch_more` schema、必要 README / tests 文档 | 不做完整多进程治理、不做 Remote、不做 Outbox、不做 audit hard-gate；不验证 `start_run` 幂等、active Run 并发仲裁或调用重试语义；不做完整 ToolRegistry / 权限治理 / 业务工具迁移；不做自动透明补读 | 一个单调用方、顺序执行的无完整生产治理多轮会话可按目标事实层跑通，含工具截断补读、memory、compaction；手工 smoke 真实向 `mimo-v2.5-pro-plan` 发送 prompt，由模型调用公共声明的 `huge_echo`，再由模型根据 `truncation.next_action=fetch_more` 调用 framework `fetch_more` |
| P5.5 | Deferred Scope Reconciliation | 回看 P1-P5 所有“本阶段不实现”能力，确认没有遗留能力被漏排或误排 | deferred-scope inventory、能力归属表、后续 Phase 调整建议、必要的新 Phase / issue / plan 修订 | 不写生产代码；不把未落地能力补写成已落地事实；不直接修改后续 Phase 代码边界 | P1-P5 的非目标均被明确标记为已实现、已安排到 P6+、新增 Phase / issue 承接，或经用户确认关闭 |
| P6 | Durable EventLog / Run State / Projection | 在 P1.5 最小事实层上建立多进程共享的 durable facts、projection checkpoint 与 observer / sink 基础 | 持久 EventLog、Run / Attempt 最小持久状态、atomic append / cursor allocation、projection checkpoint、最小 observer / sink protocol、audit / timeline / memory projection 重建基础、observer retry / lag、`utils/smoke_host_p6_durable_eventlog.py` | 不实现 attempt lease / fencing；不落地具体 tool trace schema；不把 trace 写回 Engine；不要求所有 observer hard-gate；不把 observer / sink 做成完整消息队列消费者框架 | EventLog storage 本身具备多进程安全的 append / replay / checkpoint 语义；Host 具备足以支撑 tool trace / audit / timeline / memory projection 的最小 observer / sink 基础；P6 smoke 可观察 durable append / replay / projection / checkpoint |
| P7 | Tool Trace Projection / Sink | 在 P6 observer / sink 基础上落地 tool trace，继承 OLD tool trace schema 的关键语义 | tool trace observer、tool trace sink / store、Host-owned RunInput context fact、OLD tool trace schema 对齐、OLD analyzer 业务无关能力迁移、tool call / result / iteration usage / final response / protocol error 投影测试、provider secret 排除与 trace 热/冷分层、`utils/smoke_host_p7_tool_trace.py` | 不恢复 Engine 私有 recorder / store；不扩大 ToolRegistry 权限治理；不实现 audit hard-gate | tool trace 不再由 Engine recorder 落盘，而由 Host observer / sink 从 Engine / ToolRuntime canonical events 幂等派生；`iteration_context_snapshot` 由 Host-owned durable fact 支撑；scope token / cursor / prompt / tool result 按 OLD 热/冷分层保留以便诊断，provider secret 不进 trace；P7 smoke 可观察 trace projection |
| P8 | Attempt Lease / Recovery / 多进程并发基础 | 落地 AttemptSupervisor、lease / fencing、startup recovery，使多进程执行具备 owner 真源 | 全局单调 fencing token 分配器、attempt store、owner secret、lease renew、旧 attempt 标记 `STALE` / `RECOVERING` / `LOST`、新 recovery attempt 与 `recovered_from_attempt_id`、ToolRuntime facts fencing、`ObserverSink.process` async 协议迁移、真实 deterministic multiprocessing append / terminal race / stale recovery / observer drain 验证、测试 / smoke 级多平台操作封装、`utils/smoke_host_p8_attempt_lease.py` | 不做 Remote RPC；不实现完整 Session / Run admission；不 takeover 同一 attempt；不实现 observer claim / lease；不把 lane 实现为 Host 私有能力；不把测试用 process launcher 提升为 Host 生产能力；不把随机 owner token 当作 fencing token | 多进程下同一 attempt 只有持有当前全局 fencing token 与 owner secret 的有效 owner 可写入，迟到 owner 写入被拒绝，orphan / stale 先关闭旧 attempt 再用新 attempt 恢复或 LOST；真实多进程 append / terminal / recovery / observer drain stress 不破坏 durable facts；P8 smoke 可观察 owner / fencing / recovery |
| P9 | Session / Run Lifecycle Governance / Public Interface 固定 | 在 durable facts 与 attempt ownership 上完整落地 Session / Run 状态机、admission policy、取消基础治理，并固定 Host public interface | SessionManager、RunManager、RunSupervisor、`client_request_id` 幂等、同 Session active Run 仲裁、cancel_run、状态机测试、生产级 admission policy、Host public interface 契约、OLD wechat / web / prompt / interactive 调用需求调研、`utils/smoke_host_p9_lifecycle.py` | 不做 issue #3 的强制终止增强；不做 wait / suspend / resume；不做 Remote RPC；不迁移业务工具 | 同 Session 单 active Run、幂等 start_run、跨进程 admission、取消基础收口稳定；`docs/host/design.md` 的 Public Interface 口径与 `dayu.host` public exports 固定，且已对照 OLD wechat / web / prompt / interactive 需求验证；P9 smoke 可观察 lifecycle/admission/cancel |
| P10 | ToolRegistry Governance | 在 P5 最小 tool declaration 之上落地完整通用工具注册与治理能力 | ToolRegistry / tool catalog、display metadata 治理、permission policy、middleware chain、framework tool registration、schema / binding 校验、registry audit facts、`utils/smoke_host_p10_tool_registry.py` | 不迁移 business fins / doc / web 工具；不让 Host / Engine 承载财报业务语义；不让 Engine 持有 registry | 通用工具可被发现、注册、授权、middleware 处理与审计；Engine 仍只接收 `ToolSchema` projection 与 `ToolExecutor` 协议；P10 smoke 可观察 registry governance |
| P10.5 | Web Tools Migration Smoke | 在 P10 后立即迁移代表性 web tools 到 Host ToolRegistry，趁热验证真实业务工具可走完整通用工具治理链路 | web tool `@tool` declaration、ToolRegistry 注册、permission / middleware / display metadata 对接、ToolRuntime truncate / fetch_more 适配、tool trace / memory facts 验证 smoke、必要 web tool README / docs 更新、`utils/smoke_host_p10_5_web_tools.py` | 不迁移 fins / doc 全量业务工具；不把 web 业务语义塞进 Host / Engine；不扩大 P10 ToolRegistry 契约；不实现 P11 validation replay | 至少一个代表性 web tool 可通过 Host ToolRegistry 被模型真实调用，并产出可审计 ToolRuntime / trace / memory facts；P10 通用治理链路在真实工具上通过 smoke 验证 |
| P11 | OutputContract / Validation Replay | 补齐输出契约、验证决策与 replay attempt，使财报回答可靠性有可验收闭环 | OutputContractRef、ValidationDecision fact、validator execution boundary、replay attempt policy、replay 上限、恢复 / 失败收口测试、`utils/smoke_host_p11_validation_replay.py` | 不把 validation 混入 P4 compact retry；不把 audit hard-gate 当成 validation replay；不实现业务 validator 全量规则库 | final answer 可按契约验证，失败可产生可审计 replay attempt 或明确失败终态，恢复后不会丢失 validation decision；P11 smoke 可观察 validation decision / replay |
| P12 | Reply Outbox | 将 RunResult / final answer 可靠投影到外部信道 outbox | Outbox 状态机、delivery key、claim / retry / reconcile、`utils/smoke_host_p12_reply_outbox.py` | 不实现具体 WeChat / Web delivery 业务适配 | final answer 到 outbox 无丢失窗口，重复 projection 不重复投递；P12 smoke 可观察 outbox claim / retry / reconcile |
| P13 | RemoteProxy / RemoteStub | 落地远程执行边界 | RemoteProxy、RemoteStub、cursor / ack / reconnect、remote cancel、`utils/smoke_host_p13_remote_proxy.py` | 不让远程 Engine 回调 Host 执行工具 | Remote Agent = Engine + tools execute remotely；P13 smoke 可观察 remote cursor / ack / reconnect / cancel |
| P14 | Wait / Suspend / Resume 协作 | 基于 Engine suspended outcome 与 Host durable governance 落地等待协作能力 | WaitRecord、awaiting outcome、自动 resume、状态机与恢复测试、取消 / 超时语义、`utils/smoke_host_p14_wait_resume.py` | 不把 `resume_run` 暴露为普通 public API；不把 wait 伪装成普通 tool failure | 等待型工具 / 长事务可 suspend、恢复、取消、超时，且多进程恢复后语义稳定；P14 smoke 可观察 suspend / resume / timeout |
| P15 | Governance Hardening | 补齐取消增强、policy hard-gate、audit hard-gate、运行治理 | issue #3 增强、watchdog、强制终止、required projection、schema bootstrap 严格事务化 / 半失败治理评估、运维可观测性、`utils/smoke_host_p15_governance_hardening.py` | 不扩大 Host 业务语义；不补 business tools 迁移 | Host 可作为强约束真源运行生产治理；schema bootstrap 半失败有明确恢复 / 报警 / 初始化策略；P15 smoke 可观察 hard-gate / watchdog / 强制终止 |
| P16 | Full-Governance Multi-Turn Smoke / 文档收口 / 接口冻结 | 在 P6-P15 完整治理能力打开后，按 P5 与 P10.5 同一验证面跑最终纵向 smoke，固定 Engine / Host 接口，并更新当前事实文档、归档迁移过程文档 | full-governance smoke CLI / test harness、与 P5 / P10.5 对齐的验证面清单、代表性 web tool 通过完整 ToolRegistry / ToolRuntime / trace / memory / governance 链路的 smoke、`InMemoryRunEventStore` 收口决策、Engine / Host interface freeze 方案、契约变更治理规则、`docs/code_review.md` 当前事实专项、必要 README、issue / PR 收口、phase 文档归档策略 | 不新增治理能力；不写未来设计为已落地事实；不误删 review 证据；不把 smoke failure 用文档绕过；不允许未走接口变更流程的 Engine / Host 契约修改；不迁移 fins / doc 全量业务工具 | Full-Governance Multi-Turn Smoke 覆盖 P5 与 P10.5 同一语义面：真实模型 tool calling、真实 web tool、ToolRuntime truncate / framework `fetch_more`、Conversation Memory、context compact、durable EventLog / observers、tool trace、attempt lease / recovery、lifecycle / admission、ToolRegistry governance、validation replay、outbox / remote / wait / audit hard-gate；`InMemoryRunEventStore` 不再作为生产默认装配，必须被删除、迁移到测试 helper / explicit local adapter，或经专项理由保留为非生产 adapter；Engine / Host public contracts、protocols、events、result types、错误码和 package exports 被明确冻结，后续变更必须走设计更新、兼容性取舍、测试和专项 review；日常 review prompt 与 README 均只描述当前已落地事实，迁移审计记录可追溯 |

### 4.1 第一批能力边界

P2 的 `truncate / fetch_more` 不绑定 P6 的 observer / sink 基础，也不绑定 P7 tool trace、
P15 audit hard-gate 或 timeline projection。这些 observer / sink 只是后续阅读者，不能反向决定
P2 的实现形状。

P2 需要保证的是 ToolRuntime 最小运行事实不成为黑盒，例如：

- result truncated。
- cursor issued。
- fetch_more requested。
- fetch_more completed / failed。
- cursor expired / denied。

这些事实可以在 P2 phase plan 中选择进入 canonical RunEvent 或 ToolRuntime fact store；P6 observer
后续可以读取这些事实，但 P2 不实现 observer。

P3 的 Conversation Memory 必须提前对齐 EventLog / projection 边界。P3 phase plan 必须显式列出：

- RunInputBuilder 可消费事实，例如 pinned_state、memory pool、结构化 tool facts、
  evidence anchors、source references。
- 客户端 timeline 展示事实，例如 answer、reasoning 展示字段、tool summary、warnings/errors。
- 只可观测 / audit / trace 事实，例如内部治理事件、trace-only payload、debug sampling。

reasoning / preview delta 只能进入展示 read model，不得进入 RunInput replay、Memory pool 或
RunInputBuilder 运行态输入。P3 不能绕过 P1.5 的 RunEventStore 直接制造独立 transcript 真源。

P4 到 smoke 阶段只迁移 compact 的归属：把 OLD 中原本在 Engine 内完成的上下文压缩搬到 Host。
它的目标只是让 Engine 遇到 context overflow 时，Host 能基于 P3 的 RunInputBuilder 可消费事实
完成 compact，并用 compact 后的输入重建 attempt 继续运行。P4 不牵扯 replay、validation、
OutputContract 或完整 context governance。

P5 smoke 只覆盖单进程、单调用方、顺序执行 happy path：每轮等待上一轮 terminal 后再启动下一轮。
P5 需要最小 Run 创建事实和 Session 下多轮顺序，但不以生产级 `start_run` 幂等、
同 Session active Run admission policy、断线重试或并发输入仲裁为前提。这些治理能力仍留在 P9，
并依赖 P8 attempt ownership。
用户人工 review 后，P5 同时承接最小公共 tool declaration 与 framework `fetch_more` 能力：OLD-like
`@tool(..., truncate=ToolTruncateSpec(...))` 需要产出强类型 `ToolDefinition` / `ToolBundle`，
同源携带 LLM-facing schema、executor binding、Host ToolRuntime truncate metadata 与 display metadata。
这不是完整 ToolRegistry，也不恢复权限治理 / middleware / 业务工具迁移；但 P5 必须恢复 OLD 语义中的
LLM-facing truncation hint 与 framework `fetch_more` tool，使模型在同一个 run 内自行补读。
`huge_echo` 是该声明能力的首个 smoke/test 工具。
用户人工 review 已将手工 smoke 主目标改为真实 provider `mimo-v2.5-pro-plan` tool calling，缺配置应清晰失败，
不能把 fake provider 或 scripted WorkerProxy 作为主 smoke 成功证据。

P5.5 是非生产代码的总控核对阶段。它必须逐项回看 P1、P1.5、P2、P3、P4、P5 phase plan 中
“本阶段不实现”“明确不做”“后移”的能力，判断每项是否已经被后续 Phase 承接、需要调整到现有
P6+、需要新增 Phase / issue，或应经用户确认关闭。P5.5 的输出是排期与边界修订，不直接补实现；
如果发现某个能力会改变 P6+ 的目标、非目标或验收信号，必须更新总控计划并走对应 review gate。

P5.5 人工 review 固定以下总控判断：

- 完整 ToolRegistry / tool catalog / display metadata governance / permission / middleware 是
  Full-Governance Multi-Turn 的通用基础能力，P5 只落地最小 declaration，后续必须单独安排。
- tool trace 已从 Engine 私有 recorder/store 中移出。NEW 架构保留“Engine 发出强类型事件，Host 提供
  sink / observer 能力，audit / tool trace / timeline 从 EventLog facts 派生”的方向；P6 只提供
  tool trace 能工作的 observer / sink 基础，具体 tool trace projection / sink 与 OLD tool trace schema
  对齐由 P7 单独承接。
- business fins / doc / web 工具迁移不属于 Host 迁移主线；Host 只提供通用工具注册、执行、治理边界，
  财报文档存取仍由业务工具通过 `dayu.fins.storage` 保证。为证明 Host 治理链路能承载真实业务工具，
  P10.5 在 P10 后立即迁移代表性 web tools 做 smoke，趁热验证 P10 ToolRegistry；P16 复用该
  代表性 web tool 做 full-governance smoke。不要求迁移 fins / doc 全量业务工具。
- P12 Reply Outbox、P13 RemoteProxy / RemoteStub、P14 Wait / Suspend / Resume 经用户确认保留在
  Host 迁移后半段计划中，不从 P6+ 主计划删除。后续 phase plan 可以按实际需求控制最小实现边界，
  但不能把这些能力从总目标中悄悄移除。
- P3 已落地同 session 多轮所需的 Conversation Memory / RunInputBuilder 结构；加入“多进程”定语后，
  P3 的内存态实现不够，P6 必须把 memory projection / read model 变成可由 durable EventLog
  幂等重建或持久派生的事实层。长期记忆、跨 session / project / user memory、public edit /
  reset / forget 不阻塞 Full-Governance Multi-Turn，后续由 GitHub issue #24 跟踪。
- context governance 不阻塞 P6+ 主迁移，已由 GitHub issue #23 跟踪；provider 官方 token
  estimator 已由 GitHub issue #20 跟踪。P4 / P5 的 Host 内部估算与 compact retry 只作为当前
  no-full-governance 能力，不宣称 provider tokenizer 真源。
- P5 已落地的是 LLM-facing framework `fetch_more`：模型根据 truncation hint 在同一个 run 内
  自行调用 framework `fetch_more`。Host-side transparent continuation 不是 Full-Governance
  Multi-Turn 必需项，后续如需改善 UX 再单独讨论。
- Attempt lease / recovery / fencing 是多进程并发 Full-Governance Multi-Turn 的必要能力。
  P6 durable EventLog 不依赖 lease，但 P6 自身必须提供多进程安全的存储语义，例如 atomic append、
  cursor / sequence 唯一约束、事务边界与 projection checkpoint 并发安全。`client_request_id`
  幂等与同 Session active Run admission 可以用数据库唯一约束 / 行锁建模；但生产级 attempt
  ownership、recovery 与跨进程 cancel 收口必须建立在 owner 真源之上，因此 P8 落地 Attempt
  Lease / Recovery，P9 再固定完整 Session / Run Lifecycle Governance。
- Host 内部必须防止 `LocalRunHarness` 继续膨胀为 God Object。P6 及以后 phase plan 只要新增
  durable projection、observer / sink、attempt ownership、lifecycle、validation replay、outbox、
  remote 或 wait/suspend/resume 能力，就必须明确 Run orchestration、event translation、compact
  retry、memory projection trigger、attempt supervision、observer dispatch 的模块边界；不得把新职责
  继续堆入 `LocalRunHarness`。
- P6 的 observer / sink 先按最小 durable protocol 与 checkpoint 能力落地，避免一次性做成完整
  消息队列消费者框架。claim / lease / fencing、独立 observer worker、projection lag monitor 等
  生产级增强只有在对应 phase plan 证明必要时才进入实现。

### 4.2 P6 残余风险追踪

P6 code / architecture / concurrency review 修复后，若仍存在不阻断 P6 语义成立但必须后续追踪的
残余风险，必须在本节登记；不得只写在实施报告中口头记忆。总控判断每项残余风险时，必须按
`accepted`、`deferred-with-owner`、`rejected-with-reason` 或 `needs-more-evidence` 标注。

当前 P6 残余风险追踪如下：

- `deferred-with-owner: P8`：真实多进程 stress 测试。P6 只要求 durable storage 具备事务、唯一约束、
  cursor / global position 分配和 projection checkpoint 的并发安全基础；真实跨进程 append、
  terminal race、observer drain / recovery stress 必须在 P8 Attempt Lease / Recovery 阶段补齐，
  并进入 P8 smoke 或测试验收信号。
- `deferred-with-owner: P8`：owner lease / fencing / orphan attempt recovery。P6 可以落地
  AttemptStateStore 最小状态与承载空间，但不能宣称具备生产级 owner 真源。P8 必须实现 owner token、
  lease renew、late write fencing、stale cleanup、orphan recovery 与对应恢复测试。
- `deferred-with-owner: P8`：attempt `terminal_event_position` 写入。P6 的
  `_finish_attempt_if_durable` 只写入 attempt 终态，`terminal_event_position` 作为 P8 recovery /
  fencing 的预留字段保持 `NULL`；P8 落地 attempt recovery 时必须从 durable EventLog 的
  global position 真源补齐 terminal attempt 与 terminal event 的关联。
- `deferred-with-owner: P15`：schema bootstrap 半失败治理。P6 可用 `CREATE ... IF NOT EXISTS`
  与全新 schema 起库假设保证当前开发 / smoke 路径；若生产需要严格事务化 DDL、半初始化检测、
  初始化锁或运维报警，统一在 P15 Governance Hardening 阶段评估并收口。
- `deferred-with-owner: P15`：compact 成功但后续 EventLog append 失败时的诊断事件精度。
  当前 `_append_compact_exception_failure` 会把 compact 分支异常统一收口为
  `context_compact_failed(reason=INTERNAL_ERROR)` 与 Host-owned failed terminal；若真实根因是
  compact 已成功但写入 `context_compact_completed` / `context_attempt_retrying` 失败，持久化诊断
  可能把存储层 append failure 误读为 compact 内部错误。该场景通常意味着 durable write 已不可用，
  后续 failure append 也大概率失败，不阻塞 P6；P15 hardening 需要评估是否引入更精确的
  storage failure diagnostic / alert 语义。
- `deferred-with-owner: P15`：observer 在无事件且 `last_success_position is None` 时
  无法转 `CAUGHT_UP`。`ProjectionCoordinator._run_once_locked` 当前要求 `advance_success`
  携带具体 position；首次 initialize 后若 EventLog 为空，observer 状态保持 `IDLE`，
  对运维状态视图可能误读为“未启动”。不影响 projection 正确性。需要在 P15 Governance
  Hardening 阶段为 `ProjectionStore` 增加无 position 的 `set_status` 入口，或引入哨兵
  position 显式表达 "已追平且尚无事件"。
- `deferred-with-owner: P8/#28/P15`：`ObserverSink.process` async 升级与 observer claim / lease。
  P6 当前保留同步 observer 协议，并由 `MemoryProjectionObserver._run_async` 桥接 async
  `ConversationMemoryStore` 接口；这保证 P6 diff 边界小，但每个 terminal projection 会引入
  thread + event loop 桥接开销。P8 plan gate 已固定：P8 负责把 `ObserverSink.process` 升级为
  async 协议并删除 `_run_async` bridge；P8 不实现 observer claim / lease，不升级 observer
  ownership，只通过 deterministic multiprocessing observer drain 验证 attempt lease 不破坏现有
  checkpoint 语义。后台 observer drain、observer claim / lease 归 #28 或 P15 单独设计。
- `deferred-with-owner: P9`：`startup_reconcile` 进入 Host 启动流程。P6 只提供
  `DurableHarnessBundle.startup_reconcile()` 显式入口，用于在 terminal event 已持久化但 terminal 后
  `drain()` 尚未执行就崩溃的场景中追平 read model。由于 `build_durable_harness()` 是同步装配函数，
  P6 不能在构造时直接 `await`；P9 落地 Session / Run Lifecycle 与生产 Host bootstrap 时，必须把
  startup reconcile 收进 Host 启动 / durable harness 装配流程，避免 UI / Service 业务调用方需要知道并
  主动调用该恢复入口。
- `accepted: P6 re-review passed`：post-commit hook 异常隔离。`docs/host/phase6-fix-rereview.md`
  已确认 hook 是 best-effort in-memory `Condition.notify_all()` 唤醒，数据在 hook 执行前已 commit
  到 SQLite；hook 失败只会错过即时唤醒，不影响 durable drain、replay 或后续读路径。P6 接受
  `try/except + logger.error` 隔离。
- `accepted: P6 re-review passed`：`_project_run_events` fallback。`docs/host/phase6-fix-rereview.md`
  已确认 durable harness 注入 `ProjectionCoordinator` 后，terminal projection path 走
  `coordinator.drain()` 并 return，不会执行 fallback；`_project_run_events` 仅服务非 durable
  `InMemoryRunEventStore` 测试 / 过渡装配，P6 可接受。
- `accepted: P6/P15 scope`：observer lag 近似。P6 可以只提供最小 lag / caught-up 观察信号，
  不宣称生产级 projection lag SLA；P15 若需要 required projection、lag monitor 或 hard-gate，
  必须重新定义严格指标与报警语义。
- `deferred-with-owner: P16`：`InMemoryRunEventStore` 收口。P6 后它只作为 P1.5-P5 单元测试、
  no-full-governance smoke 与非 durable 过渡装配使用，不再代表生产事实层。P16 interface freeze /
  文档收口时必须决定：删除它、迁移到测试 helper / explicit local adapter，或用专项理由保留为
  非生产 adapter；不得继续作为 Host 生产默认装配或 public interface 暗含依赖。

### 4.3 P7 残余风险追踪

P7 落地后，仍需后续阶段追踪的残余风险：

- `accepted: P7 scope`：`ToolTraceObserver` 是同步 sink。每行 `flush + fsync` + raw payload
  `tmp + os.replace` 的写入完全发生在文件系统、不动 SQLite、不阻塞 Engine 事件产生，但会
  阻塞 terminal `coordinator.drain()`。当 trace root 处于慢速文件系统时 terminal completion 可能
  被拉长；P8 只升级 observer 调用协议为 async，不把 JSONL sink 改成后台 worker；后续若 P15
  需要更强 SLA，可结合 issue #28 评估 buffered drain。
- `accepted: P7 scope`：JSONL 与 EventLog checkpoint 非原子。每行 trace 在 EventLog 已 commit
  之后由 observer 写入；进程在两步之间崩溃，replay 后会产生重复行。靠行内 sha256[:32]
  `idempotency_key` 让 analyzer 去重消化崩溃窗口；P7 不引入跨子系统二阶段提交。
- `deferred-with-owner: issue #36`：Tool Trace JSONL 文件滚动边界。`_select_jsonl_file`
  当前在 append 前按现有文件大小选择分片，crash replay / duplicate append 可能让接近阈值的
  `tool_calls_*.jsonl` 分片超过目标大小。正确性由 analyzer `idempotency_key` 去重保证，
  但长期文件管理可预测性与运维体验需要在 #36 跟踪治理。
- `deferred-with-owner: P7-followup`：compact 重试路径合成 `RunInputContextSnapshotBuiltData`
  时的 `iteration_index` / `attempt_index` 取值需要与真实 Engine attempt 元信息对齐验证，
  避免 trace `iteration_context_snapshot` 字段在 compact retry 后语义偏移。
- `deferred-with-owner: P8`：partial tool calls 完整语义。Engine 在 SSE 中途失败造成的部分
  tool call 当前不会进入 P7 trace 的 `tool_call` record（因为缺 `TOOL_RESULT_ACCEPTED`），
  observer 会在 batch 内抛 `ProjectionSchemaError`；P8 owner fencing / recovery 落地后需要重新
  定义 partial tool call 的 trace 语义（独立 record vs. failed outcome）。
- `accepted: P7 scope, mid-term-evaluate`：`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact `data` payload
  内联完整 `raw_input_messages_json` / `raw_tool_schemas_json`。该方案让 raw payload 与 fact
  落库收敛到单条 `append_in_transaction`，天然消除"fact 已落但 raw ref 缺失"窗口；trade-off 是
  `run_events` 行体积可达数十 KB ~ 数百 KB，长期会让 EventLog 变成冷热混合存储、影响
  `ProjectionCoordinator.drain()` 反序列化吞吐与未来 retention / compaction。当 Run 体量或 tool
  schema 数量显著增长后，应评估把 raw payload 外迁到独立表 / 文件、fact 仅保留 ref。
- `accepted: P7 baseline, defer-to-P8/P9`：`LocalRunHarness` 已承载 16 字段 / 43 方法，横跨 Run
  生命周期管理、Engine 事件翻译、context compact、memory projection、attempt state 持久化、
  P7 fact append 等多个职责；P7 增量虽克制（builder 抽到 `_run_input_context_fact.py`、harness
  仅装配 + `append_in_transaction`），但基线已接近 God Object 阈值。后续 P8 / P9 应评估按职责
  拆分为更小组件（如 `AttemptManager` / `ContextCompactHandler` / `RunInputContextFactAppender`）；
  不属于 P7 阻断项。

P9 实施 `start_run` 幂等时，必须重新讨论并固定 `(session_id, client_request_id)` 如何幂等映射到
同一个 `run_id`：包括 `run_id` 由 Host 生成还是由持久 Run 创建事实确定、重复请求返回同一
`RunStream` / `RunHandle` 的精确语义、原 Run 已 terminal 或事件 cursor 已推进时的补读起点、
以及该映射依赖的持久唯一约束 / compare-and-set 边界。

P9 同时是 Host public interface 固定点。当前 `dayu.host.__init__` 暴露的是 P5 no-full-governance
smoke surface，不等同于最终 public contract。OLD wechat / web / prompt / interactive 对 Host /
Service / Agent 入口的真实需求必须在 P9 phase plan 进入 review 前完成调研，并输出
`docs/host/old-interface-requirements.md` 或等价文档。P9 plan 必须基于该调研结果固定
`docs/host/design.md` 第 5 节
Public Interface 口径与 `dayu.host` public exports。调查至少覆盖：

- WeChat / Web 对异步启动、断线重连、cursor 补读、重复提交、取消、终态获取和外部投递的需求。
- `prompt` / `interactive` 对同步等待、流式输出、会话 label / session 绑定、历史接续、thinking /
  reasoning 展示和错误收口的需求。
- Service 层如何装配 caller / agent / app system prompt、tool catalog、RunOptions、`client_request_id`
  与 session scope；Host public interface 不得泄漏 fins/doc/web 业务语义。
- `start_run`、`stream_run_events`、`get_run_result`、`cancel_run`、`RunStream`、`RunHandle`、
  `RunEventCursor` 与错误/拒绝结果的最终稳定语义。

P9 不能闭门造车固定接口；若 OLD 调研发现 `docs/host/design.md` 第 5 节需要修订，必须在 P9 plan
review 前把修订建议和取舍理由写清楚。

## 5. Phase 文档命名

每个 Phase 使用固定文档命名：

```text
docs/host/phase{N}-plan.md
docs/host/phase{N}-plan-review.md
docs/host/phase{N}-code-review.md
docs/host/phase{N}-old-new-review.md
docs/host/phase{N}-pr-review.md
```

如果某个 Phase 需要专项 review，可追加：

```text
docs/host/phase{N}-{topic}-review.md
```

例如：

```text
docs/host/phase1_5-plan.md
docs/host/phase5_5-plan.md
docs/host/phase8-concurrency-review.md
docs/host/phase14-wait-state-review.md
```

小数 Phase 的文件名使用下划线，例如 P1.5 对应 `phase1_5-*`，P5.5 对应 `phase5_5-*`。

所有 review finding 修复后，必须在对应 review 文档的 finding 标题上标注修复状态；可在正文保留
“修复状态”说明作为证据，但标题状态是必需项。

## 6. Phase Plan 必填模板

每个 `phase{N}-plan.md` 必须包含：

- 目标。
- 非目标。
- 前置条件。
- 架构边界。
- 文件级改动清单。
- 新增 / 修改契约。
- 状态机变化。
- 数据持久化 / schema 变化。
- 多进程并发影响。
- ToolRuntime / EngineWorker / Engine 边界影响。
- EventLog / RunEventStore / projection 影响。
- 可接受临时实现 / 不可接受临时实现。
- runtime dependency；若涉及 lane，必须说明是否复用或扩展 `dayu.runtime`。
- 测试清单。
- 验证命令。
- README / docs 触发判断。
- review gate。
- 停止条件。
- 风险与回滚。
- 待用户确认项。
- 迁移 Agent 实施完成汇报格式。

涉及 schema 变更时，必须同时说明：

- NEW 按全新 schema 起库处理，不做旧库兼容读取。
- 是否需要将旧库迁移动作作为 `workspace_migrations` 插件进入 `dayu-cli init` 流程。

## 7. Review Gate

每个 Phase 至少需要两个 gate：

- plan review gate。
- code review gate。

总控 Agent 仍负责自动派 Agent 编写 / 修复 phase plan，并自动派 Agent 执行 plan review / 复审。
总控 Agent 不再负责直接派代码实施 Agent、代码修复 Agent 或 code review Agent；PR 创建后也不生成
PR review 指导 prompt，而是停下来等用户人工 PR review。总控 Agent 只负责为 code implementation /
code fix / code review gate 生成可直接交给对应 Agent 的指导 prompt，由用户手工派 Agent 执行代码实施、
代码修复、code review 与复审，并把结果交回总控处理。代码修复 Agent 负责同步标注对应 review 文档
finding 的修复状态，总控 Agent 负责检查标注是否完整。

必要时增加：

- OLD / NEW 对比 review。
- 最佳实践 review。
- 并发 / recovery 专项 review。
- 类型 / import boundary 专项 review。
- PR diff review。

P1 必须增加 EngineWorker public boundary gate：

- `EngineWorker.run_agent_messages` 不得成为 Host public API。
- `ToolExecutor.execute` 不得成为 Host public API。
- 调用方只能通过 Host 的 Run 入口或测试 harness 触达 Engine。
- EngineWorker 只能作为 Host capability / 内部 protocol 被装配和测试。
- 若 P1 代码或文档把 EngineWorker、ToolExecutor 暴露给 UI / Service 调用方，则 plan review
  或 code review 必须判定不通过。

P2 必须增加 OLD / NEW code review gate：

- P2 代码 review 除常规 code review prompt 外，必须额外生成 OLD / NEW 对比 review prompt。
- OLD / NEW review 必须对照 OLD `TruncationManager`、OLD `fetch_more` schema、OLD
  `project_for_llm` 与 OLD 测试，确认 NEW 继承 cursor lifecycle、scope token、TTL、
  single-use、limit clamp、page structure 等底层可靠语义。
- OLD / NEW review 同时必须确认 P2 不误恢复 OLD LLM-facing `fetch_more` 半协议，也没有把
  OLD Engine 归属的实现机械迁回 `dayu.engine`。P5 若恢复 framework `fetch_more`，必须走 Host ToolRuntime
  ownership 与 Engine 普通 tool call 边界，不能恢复 OLD 完整 ToolRegistry / Engine-owned cursor manager。
- P2 code review 只有用户手工执行的常规 code review 与 OLD / NEW 对比 review 均明确通过后，
  才允许停下来等用户人工确认。

总控生成的 review prompt 不能只让 review Agent 按 checklist 打勾；必须要求 review Agent 以 OLD
Host 中可靠行为作为强参考源，开放式寻找遗漏能力、边界泄漏、状态机漏洞、幂等缺口、数据丢失窗口和
多进程竞争问题。

## 8. 验证与文档规则

每个代码 Phase 必须运行：

```bash
source .venv/bin/activate
python -m pyright
```

并运行该 Phase 影响范围内的测试。若某 Phase 只改文档，可以只运行 pyright，并在最终说明中说明
未跑 pytest 的原因。

README 更新遵循 `AGENTS.md`：

- 除 `tests/README.md` 外，其它 README 默认等迁移结束或对应代码事实落地后再改。
- 命中 README 触发条件时，必须先判断是否属于该 README 的职责范围。
- README 只写当前已落地事实，不写未来设计。

`docs/code_review.md` 更新规则：

- 每完成一个代码 Phase 且用户确认该 Phase 事实已经落地后，更新日常 review prompt 的当前事实专项。
- `docs/code_review.md` 不要求 review Agent 理解迁移过程，只描述当前代码事实和 review 应检查的边界。

## 9. GitHub / PR 规则

每个 Phase 默认一个 ready PR。

PR 准备前必须确认：

- 当前分支只包含本 Phase 范围内提交。
- plan commit 与 code commit 边界清楚。
- review 文档中的 finding 修复状态已经标注。
- 测试与 pyright 结果已记录。
- README / docs 触发判断已记录。

PR 创建后：

- 总控 Agent 停下来等用户人工 PR review，不生成 PR review 指导 prompt。
- 用户提交 PR review 结果后，总控 Agent 判断 finding 是否成立；成立时生成修复 prompt，
  用户手工派 Agent 修复和复审；修复 Agent 标注 review finding 修复状态，总控检查标注并补 commit。
- PR review 通过后停下来等用户确认。
- squash merge PR 并删除远端分支默认由用户执行；只有用户明确指示总控 Agent 执行时，
  总控 Agent 才能执行 squash merge / delete branch。
- 用户手工 merge 后，总控记录结果，确认目标分支已包含该 PR 后再进入下一 Phase。

## 10. 总控检查清单

每个 Phase 结束前，总控 Agent 必须确认：

- Phase 目标已完成，非目标未被偷做。
- phase plan 已按 implementation stage / slice 拆分；每个非平凡 slice 都有 slice id、短标题、
  目标、预期可见结果、文件 / 模块 ownership、前置依赖、明确非目标、测试命令、完成信号和
  停止条件。实际实施记录能对应到这些 slice，未把整个大 Phase 一次性交给单个实施 Agent，
  也未在当前 slice 中偷做未来 slice。
- P6 及以后每项新增治理能力都有对应 `utils/` 手工 smoke，且 smoke 输出足以观察新增治理能力的
  执行路径，不刷屏、不泄露 scope token、不打印大块 prompt / delta / tool result。
- 没有旧接口兼容 wrapper / facade / re-export。
- 没有 Engine -> Host / Service / UI 反向依赖。
- 没有 Host / Engine 内嵌业务知识。
- 财报文档访问仍只能通过 `dayu.fins.storage` 由业务工具 / tool 边界保证。
- 没有 `Any`、`object`、无类型参数、无类型返回值扩散到公共契约。
- review finding 已修复或明确后移，且 review 文档有修复状态。
- 测试与 pyright 通过，或阻塞原因清楚。
- `docs/code_review.md` 与 README 的触发判断已完成。
- phase plan / review / code review 默认保留为迁移审计记录；迁移结束后只有经用户确认才归档或移动。

## 11. 后半段 Phase 的启动顺序

P1、P1.5、P2、P3、P4、P5 已完成并合入 `main`。当前启动 P5.5；P5.5 只做
deferred-scope reconciliation 与总控计划写回，不写生产代码。

P5.5 用户确认后，后续启动顺序必须遵守以下依赖：

- P6 先落地 durable EventLog / Run state / projection。P6 是多进程事实层基础，不依赖 attempt
  lease，但必须为 tool trace、attempt ownership、session lifecycle、memory projection 与 observer replay
  提供 durable facts 和最小 observer / sink 基础；P6 不一次性实现完整消息队列消费者治理。
- P7 在 P6 observer / sink 基础上单独落地 tool trace projection / sink，并对齐 OLD tool trace schema。
- P8 再落地 Attempt Lease / Recovery / fencing。P8 是多进程并发 Full-Governance Multi-Turn 的
  必要基础，必须证明 owner secret、全局单调 fencing token、lease renew、late write fencing、
  orphan / stale recovery 语义稳定；
  同时承接 P6 残余风险中的真实多进程 stress，覆盖跨进程 append、terminal race、observer drain
  与 recovery 路径。P8 的 multiprocessing 测试 / smoke 必须集中封装平台差异，包括 start method、
  join timeout、进程终止、文件 SQLite path 与跨进程结果收集；该封装先定位为测试 / smoke helper，
  不作为 Host 生产 process launcher。
- P9 在 P6 durable facts 与 P8 attempt ownership 之上落地 Session / Run lifecycle governance。
  `client_request_id` 幂等与同 Session active Run admission 可以用数据库唯一约束 / 行锁建模，但
  生产级 attempt ownership、recovery 与跨进程 cancel 基础收口必须建立在 P8 owner 真源之上。P9 同时
  必须把 P6 的 `startup_reconcile` 显式入口收进 Host 启动 / bootstrap 流程，使 durable read model
  崩溃恢复成为 Host 内部治理能力，而不是 UI / Service 业务调用方的使用要求。
- P10 落地完整通用 ToolRegistry governance，但不迁移 business fins / doc / web 工具。
- P10.5 紧接 P10 迁移代表性 web tools 到 Host ToolRegistry，立即验证 P10 的真实工具注册、
  permission / middleware / display metadata、ToolRuntime、tool trace 与 memory facts 链路；P10.5
  不迁移 fins / doc 全量业务工具。
- P11 落地 OutputContract / Validation Replay，不能把 validation replay 混入 P4 compact retry 或
  P15 audit hard-gate。
- P12-P15 依次补齐 Reply Outbox、RemoteProxy / RemoteStub、Wait / Suspend / Resume、
  Governance Hardening；P12 / P13 / P14 经用户确认保留，不从主计划删除。P15 同时承接 P6
  残余风险中的 schema bootstrap 半失败治理评估，决定是否需要严格事务化 DDL、初始化锁、
  半初始化检测或运维报警。
- P16 才执行 Full-Governance Multi-Turn Smoke / 文档收口 / 接口冻结；P16 不新增治理能力，只验证
  P6-P15 与 P10.5 已落地能力的最终纵向闭环，并固定 Engine / Host 接口。P16 smoke 复用 P10.5
  迁移的代表性 web tool 通过完整治理链路，不要求迁移 fins / doc 全量业务工具。P16 同时收口
  `InMemoryRunEventStore`：确认它被删除、移动到测试 helper / explicit local adapter，或以明确
  非生产 adapter 身份保留，且不再是 Host 默认生产装配。

P16 必须产出明确的 Engine / Host interface freeze 方案。该方案至少包括：

- 默认规则：P16 之后 Engine / Host public interface 视为稳定契约，默认不允许随意修改；任何例外都必须
  先完成接口变更提案、专项 review 与回归守护测试，不能在普通 feature PR 中顺手改动。
- 冻结范围：Engine public contracts / protocols / package exports、Host public interface / package exports、
  EngineEvent / RunEvent / RunResult / ToolExecutor / ToolSchema / ToolRuntime-facing contracts、错误码、
  retry / terminal / suspended / cancel outcome 语义。
- 变更流程：P16 后任何 Engine / Host 接口变更都必须先更新设计文档，说明动机、兼容性取舍、
  schema / migration 影响、上下游调用方影响和替代方案；再补契约测试、边界测试与专项 review。
- 禁止项：不得用兼容 wrapper / facade / re-export 偷改接口；不得让 Engine 反向依赖 Host；
  不得把 Host ToolRuntime / ToolRegistry / memory / trace / governance 语义塞回 Engine。
- 守护测试：package export 测试、protocol/import boundary 测试、事件契约 exhaustiveness 测试、
  public interface smoke 与 full-governance smoke 必须成为后续接口变更的回归门槛。

## 12. P16 后 CI / Smoke Follow-up

P16 完成 full-governance smoke 与 Engine / Host interface freeze 后，必须评估是否立即启动下一份
migration plan，或追加 P17 建立 GitHub CI workflow。该事项不阻塞 P6-P16 主迁移，但不能遗忘。

基础 CI 方向如下：

- 必跑质量门：`pytest` 全量通过；`pyright` 全量通过。
- 必跑离线 smoke：从 P5-P16 各 phase 的 `utils/` smoke 中抽取不依赖真实 provider、网络、外部密钥、
  时间敏感资源或大模型非确定行为的 smoke，作为 CI 必跑 smoke 集合。
- 可选集成 smoke：依赖真实 provider、真实 web tool、网络、GitHub / 外部服务或密钥的 smoke，不直接进入
  PR 必跑门；可放入手动 workflow、nightly workflow 或带 secrets 的受控集成 workflow。
- smoke 分层要求：每个 smoke 必须声明自己属于 `offline-deterministic`、`integration-with-secrets`、
  `manual-observation` 中哪一类；CI 只能默认运行第一类。
- 输出要求：CI smoke 不打印 delta、大工具结果、scope token、内部大 prompt 或真实密钥；失败输出必须足以定位
  phase 能力边界。

该 CI follow-up 的目标不是替代 code review，而是把 P16 后已冻结的契约、测试、类型检查和关键 smoke
变成持续回归门槛。
