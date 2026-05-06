# Host Migration Plan Review

## Review 范围

- 审查文件：`docs/host/migration-plan.md`
- 设计真源：`docs/host/design.md`
- 参考材料：
  - `docs/host/interface-discussion-notes.md`
  - `docs/host/design-best-practice-review.md`
  - `docs/host/design-optimal-review.md`
  - `docs/engine/design.md`
  - `docs/engine/migration-plan.md`
  - `docs/code_review.md`
- 审查目标：判断 Host 迁移总控计划是否能指导总控 Agent 分阶段开分支、写 handoff plan、做 plan review、人审、commit、实现、code review、人审、commit、PR、PR review、squash merge / delete branch，并确保阶段顺序不违反 Host 设计边界。

## 结论

当前计划的总控流程、阶段拆分方向和前半段 smoke 目标总体成立。先从 EngineWorker 开始，再补 truncate / fetch_more、Conversation Memory、context overflow / compaction，最后串 no-governance multi-turn smoke，符合“先跑通最小纵向链路，再补完整治理”的迁移策略。

阻塞问题：已修复。

原阻塞点不在阶段大方向，而在 `EventLog` 落点：`docs/host/design.md` 明确 EventLog 第一阶段就做，但 `migration-plan.md` 把可靠 EventLog / Projection / Observers 放到 P6。该问题已通过新增 P1.5 `Minimal EventLog / RunEventStore` 修复；P6 继续作为持久化、projection checkpoint、observer 与 trace / audit / timeline hardening 阶段。

## 阻塞 Findings

### 1-已修复-高-P1 到 P5 缺少最小 EventLog 事实层，和 design.md 的“EventLog 第一阶段就做”冲突

- **位置**：`docs/host/migration-plan.md` P1、P3、P5、P6。
- **直接证据**：
  - P1 主要输出只写了 `EngineEvent -> RunEvent 翻译薄层`，P1 启动问题里还把“是否需要最小 EventLog，还是允许测试内 in-memory EventLog”列为待回答。
  - P3 要输出 `Session transcript facts`、`tool facts projection`、`ContextBuilder`。
  - P5 要跑通 no-governance multi-turn smoke。
  - P6 才“建立可靠事件事实与派生机制”。
  - `docs/host/design.md` 第 9 节明确：“EventLog 第一阶段就做。EventLog 是 Run 的 append-only 事实账本，不是 EventBus。”
- **问题**：如果 P1-P5 没有一个最小的 canonical EventLog / RunEventStore 真源，Memory、ContextBuilder、tool facts、smoke transcript 很可能先依赖临时内存结构或专用 facts 表。P6 再补 EventLog 时，不只是加 projection，而是要倒改前面几个阶段的事实来源。
- **影响**：会削弱断线补读、自动 resume、replay、tool trace / audit 派生、ContextBuilder 可重建性，也会让 P5 的 smoke 成为“能跑但不是按目标架构跑”的纵向链路。
- **建议改法**：保留 P6 作为“持久化、checkpoint、observer、trace/audit/timeline/outbox projection 完整阶段”，但在 P1 或 P1.5 明确落地最小 EventLog 契约：
  - append-before-stream；
  - per-run cursor exclusive 语义；
  - canonical / preview 分层；
  - terminal event 与最小 Run state 可调和；
  - 第一版可使用简单持久实现或测试级实现，但接口不能让 P3/P5 依赖旁路事实源。
- **Review gate**：P1 handoff plan 必须把最小 EventLog / RunEventStore 是否落地作为用户确认项；若选择后移，必须解释 P3/P5 的事实来源如何无损迁到 P6。

## 重要 Findings

### 2-已修正-中-P2 truncate / fetch_more 需要绑定 ToolRuntime 生命周期事实，否则 P6 trace / audit 无法可靠派生

- **位置**：`docs/host/migration-plan.md` P2、P6。
- **直接证据**：P2 输出包含工具结果截断契约、fetch_more 调用路径、cursor storage、TTL / scope token 测试；P6 才输出 tool trace observer、audit observer、timeline projection。
- **问题**：truncate / fetch_more 不是单纯 cursor storage，它会成为 tool trace、audit、ContextBuilder 和用户补读体验共同依赖的事实。如果 P2 只实现读取路径，不定义 `tool_call_started/completed/truncated/fetch_more` 等最小 RunEvent / ToolRuntime fact，P6 observer 没有可靠输入。
- **建议改法**：P2 phase plan 增加一条硬边界：truncate / fetch_more 的发生、cursor 创建、scope token 颁发、TTL 过期、fetch_more 成功 / 失败都必须进入通用 ToolRuntime 事实或 canonical RunEvent；trace/audit 存储可以等 P6，但事实不能等 P6。
- **修正结论**：经讨论，该 finding 的原表述混淆了 ToolRuntime 运行事实与后续 observer。P2 不绑定
  tool trace / audit / timeline observer；P2 只要求 ToolRuntime 留下最小运行事实，避免
  truncate / fetch_more 成为黑盒。observer 只是后续阅读者。

### 3-已修复-中-P3 Conversation Memory 的事实来源需要和 EventLog / projection 边界提前对齐

- **位置**：`docs/host/migration-plan.md` P3。
- **直接证据**：P3 目标是迁移 Host 上下文治理核心，输出包含 `Session transcript facts`、`pinned_state`、`memory pool`、`tool facts projection`、`ContextBuilder`。
- **问题**：Conversation Memory 很满意 OLD 实现，但 NEW 设计要求客户端 timeline、ContextBuilder 输入、reasoning 展示字段、tool facts、evidence refs 分离。如果 P3 没有明确哪些事实来自 canonical EventLog、哪些来自 Memory store、哪些来自 timeline read model，实施 Agent 可能把展示 transcript 直接当上下文回放源，或把 reasoning / preview delta 流回运行态上下文。
- **建议改法**：P3 handoff plan 必须显式列出三类输入：
  - ContextBuilder 可消费事实；
  - 客户端 timeline 展示事实；
  - 只可观测 / audit / trace 事实。
  并要求 reasoning 只能进入展示 read model，不得进入 RunInput replay 或 Memory pool。

### 4-已吸收-中-P4 context overflow / compaction 需要提前声明 OutputContract / Replay / validation 的交互边界

- **位置**：`docs/host/migration-plan.md` P4。
- **直接证据**：P4 输出包含 Host context budget、compaction trigger、Engine 协作事件 / 错误映射、恢复策略；设计中 Replay 依赖 `OutputContractRef` / `ValidationDecision`，context overflow / compaction 后续也会影响 replay 与 attempt 重建。
- **问题**：context overflow 不只是“超上下文时压缩或失败”，还会影响 RunInput 可回放、Attempt 输入重建、validator decision 后是否 replay、以及 compaction 事实是否进入 canonical event。当前 P4 描述较粗，实施 Agent 可能只做 prompt 缩短路径，没有把 overflow / compaction 作为 Host 可恢复事实。
- **建议改法**：P4 phase plan 增加状态与事实要求：context budget exceeded、compaction requested、compaction completed / failed、retry / replay decision 都应作为 Host 通用事实表达；Engine 只通过强类型事件或错误边界暴露“无法继续”的事实，不承载 compact/retry 策略。
- **修正结论**：经讨论，到 smoke 阶段 P4 只是把 OLD 中原本在 Engine 内做的 compact 搬到 Host，
  不牵扯 replay、validation、OutputContract 或完整 context governance。compact 输入边界由
  Finding 3 的 ContextBuilder 可消费事实分层吸收，因此该 finding 不再作为独立问题成立。

### 5-已澄清-中-P7 才实现 start_run 幂等与同 Session active Run 仲裁，可能晚于 P5 smoke 的真实调用需求

- **位置**：`docs/host/migration-plan.md` P1、P5、P7。
- **直接证据**：P7 目标包含同 Session 单 active Run、幂等 `start_run`、取消基础收口稳定；P5 目标是端到端多轮 smoke。
- **问题**：即使 P5 是 no-governance smoke，也需要一个不会重复创建 Run 的最小 `start_run` 创建事实和同 Session 串行上下文假设。若幂等与 active Run 仲裁完全等到 P7，P5 只能绕过真实 Host public interface 或接受错误的并发语义。
- **建议改法**：把“强治理版本”留在 P7，但 P1 或 P5 前必须落地最小 `StartRunRequest(client_request_id)` 唯一约束和单 active Run fail-fast / typed conflict 语义。P7 再补完整状态机、admission policy、取消与恢复治理。

### 6-已修复-中-PR 流程中的 squash merge / delete branch 需要和“用户手工 merge”例外统一

- **位置**：`docs/host/migration-plan.md` 第 3、9 节。
- **直接证据**：计划写明用户确认后执行 squash merge PR 并删除远端分支；同时又写“如果用户选择手工 merge，总控只记录状态”。
- **问题**：这和当前总控职责是可兼容的，但在 phase checklist 里缺少一个明确决策点：到底由总控执行 merge，还是用户手工 merge。若没有记录，后续 Agent 可能在用户只确认 PR review 通过后直接 merge。
- **建议改法**：每个 PR review 通过后的停止点明确写成“等待用户确认 merge 执行方”；只有用户明确要求总控 merge 时，才执行 squash merge / delete branch。
- **修复结论**：已确认 squash merge / delete branch 默认由用户执行；只有用户明确指示总控
  Agent 执行时，总控 Agent 才能执行。

## 建议 Findings

### 7-已修复-高-P1 EngineWorker 最小入口应避免暴露 EngineWorker / ToolExecutor 为 Host public API

- **位置**：`docs/host/migration-plan.md` P1、P11 启动问题。
- **问题**：P1 要落地 EngineWorker capability 和最小 Run Harness，容易为了测试方便把 `EngineWorker.run_agent_messages` 或 `ToolExecutor.execute` 暴露成 public surface。
- **建议**：P1 plan 的 public API gate 写死：调用方只能通过 Host 测试级 `start_run` 或内部 harness 触达 Engine；EngineWorker / ToolExecutor 只能作为 Host 内部 capability / protocol 被测试。
- **修复结论**：该 finding 已提升为 P1 高优先级 gate。`docs/host/migration-plan.md` 已明确
  `EngineWorker.run_agent_messages` 和 `ToolExecutor.execute` 不得成为 Host public API；
  调用方只能通过 Host 的 Run 入口或测试 harness 触达 Engine。若 P1 暴露该边界，plan review
  或 code review 必须判定不通过。

### 8-已修复-低-P8 多进程并发应补充 lane runtime 的阶段归属或依赖声明

- **位置**：`docs/host/migration-plan.md` P8、总控检查清单。
- **问题**：设计已经确认 lane 是 `dayu.runtime` 或层中立 infra 能力，不属于 Host 内部。P8 聚焦 Attempt lease / recovery / 多进程并发，但没有说明是否依赖已有 lane runtime，还是同阶段新增 `dayu.runtime` 能力。
- **建议**：P8 phase plan 增加“runtime dependency”小节，明确若新增 lane，需要遵守 `dayu.runtime` 不 import Host / Engine / Service / UI / fins 的约束。
- **修复结论**：`docs/host/migration-plan.md` 已要求每个 phase plan 说明 runtime dependency；若涉及
  lane，必须说明是否复用或扩展 `dayu.runtime`。P8 也已明确不把 lane 实现为 Host 私有能力。

### 9-已修复-低-P13 文档收口应拆出迁移文档归档策略

- **位置**：`docs/host/migration-plan.md` P13。
- **问题**：P13 写了清理迁移过程文档，但没有定义哪些文档保留为审计记录，哪些只作为历史计划归档。总控 Agent 可能误删 review 证据。
- **建议**：P13 明确：phase plan / review / code review 默认保留，只有迁移结束后经用户确认才归档或移动；`docs/code_review.md` 只写当前事实专项，不吸收迁移过程。
- **修复结论**：`docs/host/migration-plan.md` 已明确 phase plan / review / code review 默认保留为迁移
  审计记录；迁移结束后只有经用户确认才归档或移动。P13 也已改为“归档迁移过程文档”，并明确不误删 review 证据。

## 可选改进

- 可以考虑增加 P1.5：`Minimal EventLog / Run Store`。这样不改变用户期望的前半段能力顺序，又能让 P2-P5 都基于同一事实层推进。
- 可以在阶段总览中把“无完整治理”改成“无完整生产治理”，避免实施 Agent 误读为可以跳过幂等、强类型事件、append-before-stream 等基础正确性。
- 可以为每个 Phase 增加“可接受临时实现 / 不可接受临时实现”段落。例如 in-memory observer 可以接受，绕过 RunEvent 直接写 memory 不接受。
- P6 可拆为 P6a `EventLog persistence + recovery reconcile` 与 P6b `Observers / trace / audit / metrics`。如果 P1 已有最小 EventLog，P6a 可以自然演进。

## 总控可执行性判断

总控流程本身足够可执行：分支命名、handoff plan 模板、plan review、code review、人工 review 停止点、commit 边界、PR review、review finding 修复状态、README / `docs/code_review.md` 触发规则都已经写清楚。

阶段顺序总体合理，但必须在进入 P1 前解决阻塞 finding：最小 EventLog / RunEventStore 的落点。只要 P1/P1.5 明确提供最小事件事实层，现有顺序可以继续保持：

```text
EngineWorker
  -> truncate / fetch_more
  -> Conversation Memory
  -> context overflow / compaction
  -> no-governance multi-turn smoke
  -> EventLog persistence / Observers hardening
  -> 完整治理能力
```

在阻塞 finding 修复前，不建议让迁移 Agent 进入 P1 生产代码实现；可以继续进行人工 review 和计划修订。

## 修复状态

修复日期：2026-05-06。

- Finding 1 已修复：`docs/host/migration-plan.md` 已新增 P1.5 `Minimal EventLog / RunEventStore`，
  要求在 P2 前固定 append-before-stream、per-run cursor、canonical / preview 分层和最小
  Run state 调和。P6 保留为持久化、checkpoint、observer、trace / audit / timeline projection
  的 hardening 阶段。
- Finding 2 已按讨论修正：`truncate / fetch_more` 不绑定 P6 的 tool trace / audit / timeline
  observer；这些 observer 只是后续阅读者。P2 只要求 ToolRuntime 留下最小运行事实，例如
  result truncated、cursor issued、fetch_more requested / completed / failed、cursor expired /
  denied，避免截断补读成为不可审计黑盒。
- Finding 3 已修复：`docs/host/migration-plan.md` 已要求 P3 phase plan 显式列出
  ContextBuilder 可消费事实、客户端 timeline 展示事实、只可观测 / audit / trace 事实三类边界。
  reasoning / preview delta 只能进入展示 read model，不得进入 RunInput replay、Memory pool 或
  ContextBuilder 运行态输入；P3 也不能绕过 P1.5 的 RunEventStore 直接制造独立 transcript 真源。
- Finding 4 已由 Finding 3 的修复吸收，不再作为独立问题成立：到 smoke 阶段，P4 只是把
  OLD 中原本在 Engine 内做的 compact 搬到 Host，使 Engine 遇到 context overflow 时可以由
  Host compact 后继续运行或明确失败收口；不牵扯 replay、validation、OutputContract 或完整
  context governance。
- Finding 5 已澄清，不作为 P5 前置：`docs/host/migration-plan.md` 已明确 P5 smoke 只覆盖
  单进程、单调用方、顺序执行 happy path，每轮等待上一轮 terminal 后再启动下一轮。P5 需要
  最小 Run 创建事实和 Session 下多轮顺序，但不验证生产级 `start_run` 幂等、active Run 并发仲裁、
  断线重试或调用重试语义；这些治理能力仍留在 P7。
- Finding 6 已修复：`docs/host/migration-plan.md` 已明确 squash merge / delete branch 默认由用户执行；
  只有用户明确指示总控 Agent 执行时，总控 Agent 才能执行。用户手工 merge 后，总控只记录状态并确认目标分支已包含该 PR。
- Finding 7 已修复并提升为高优先级 gate：P1 必须验证 EngineWorker / ToolExecutor 不暴露为
  Host public API，只能作为 Host capability / 内部 protocol 被装配和测试。
- Finding 8 已修复：P8 已补充 lane runtime dependency 判断，且明确 lane 不能成为 Host 私有能力。
- Finding 9 已修复：P13 已补充迁移文档归档策略，phase plan / review / code review 默认保留为审计记录。
