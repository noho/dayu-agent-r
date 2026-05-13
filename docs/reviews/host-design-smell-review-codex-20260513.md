# Host Design Architecture Smell Review

## 元信息

- 日期：2026-05-13
- Reviewer：Codex
- 范围：窄范围 architecture smell review
- 读取材料：
  - `docs/host/design.md`
  - `dayu/README.md`
  - `docs/reviews/host-design-phase-ready-controller-adjudication-20260513.md`
- 非目标：
  - 不要求 SQL schema、wire protocol、完整 dataclass 或测试矩阵。
  - 不使用旧 discussion、archive、issue、旧 review 作为依据。
  - 不修改设计文档或代码。

## Review 目标

本次 review 只检查 Host 设计中是否仍存在类似 RunInputBuilder 原设计的架构坏味道：一个组件直接知道太多上游 / 周边模块内部结构，而不是依赖 typed Provider Protocol、projector、command port 或 narrow facet。

## Assumptions Tested

- EventLog 被多个消费者读取是该架构的必要耦合，但消费者不应直接理解全量 event matrix。
- Host composition root 持有多个依赖是必要的，但公共 command path 不应直接持有 background runner / dispatcher 能力。
- ToolRuntime 作为 Host-owned governance module 是必要的，但不应实现成 dispatch、policy、truncation、awaiting、duplicate、trace、cleanup 混在一起的 God object。
- Context Governance 可以编排 compact，但 memory patch、trace / audit projection、budget calculation 和 message block 生成必须通过边界清晰的 provider / projector / sink 完成。
- Remote transport 可以承载语义 ack，但不能拥有 Host governance state。

## Findings

### SMELL-HOST-001-未修复-中-Host handle 仍把 command path 与 background runner 能力放在同一个 handle 轮廓里

- **id**: `SMELL-HOST-001`
- **severity**: 中
- **位置**: `docs/host/design.md` 9.1 Host Handle / Composition Root，尤其是最小依赖边界列出 `Observer / Sink runner`、`Outbox dispatcher`；controller 裁决 B9。
- **坏味道类型**: handle / snapshot / policy object 变成 god bag；Projection / Sink 反向贴近 command path。
- **问题**: 当前文本声明 Host handle 不是 God object，但同一个公共函数接收的 `host` handle 同时列出 command path 所需依赖和 background runner / delivery dispatcher。若 implementation phase 直接照此建模，`start_run`、`cancel_run`、`resolve_wait` 等 mutating API 很容易获得直接启动 sink runner、投递 outbox 或操作投影后台循环的能力，而不是只通过 after-commit wakeup port 通知。
- **为什么会影响 phase design / phase plan**: 这会让 phase slicing 难以拆分 command path、projection supervisor、outbox dispatcher 的 ownership。实现 Agent 可能把“提交事务后唤醒后台工作”和“直接持有并驱动后台 dispatcher”混在同一对象里，导致公共 API 变成治理、投影、投递的能力集合。
- **最小建议**: 写回 `design.md` 一个窄约束：Host command handle 与 background supervisor facet 分离。Public mutating API 只能持有 transaction runner、state services、RunInputBuilder / ToolRuntime factory、WorkerProxy factory 和 after-commit wakeup port；`Observer / Sink runner`、`Outbox dispatcher` 属于 Host supervisor / background facet，不进入 public command handle。
- **建议去向**: `design.md` 小幅写回。该约束影响模块 ownership，不只是 phase checklist。

### SMELL-HOST-002-未修复-中-RunInputBuilder 的 Provider Protocol 裁决尚未反映到设计真源措辞

- **id**: `SMELL-HOST-002`
- **severity**: 中
- **位置**: `docs/host/design.md` 2 节把 RunInputBuilder / Context Governance 描述为从 EventLog、memory snapshot、compact artifact 与场景约束构造 messages；22 节直接列出 `session memory snapshot`、`compact artifact / context snapshot refs`、`tool schemas snapshot`、`runner / policy config`；controller 裁决 B7。
- **坏味道类型**: 组件直接读多个模块内部结构，而不是依赖 typed Provider Protocol / projector。
- **问题**: 已裁决的方向是 RunInputBuilder 聚合 typed input Provider Protocol，并主动调用 provider 生成 message-ready blocks。但当前 `design.md` 仍以“RunInputBuilder 输入多种内部对象”的形态表达，容易让后续 phase plan 继续把 memory snapshot、compact artifact、EventLog row、tool registry / policy config 的内部结构暴露给 Builder。
- **为什么会影响 phase design / phase plan**: RunInputBuilder phase 如果从这些对象字段开始设计，会重新走回原坏味道：Builder 成为 memory、compact、EventLog、tool schema、policy 的结构知识汇聚点。之后任何 memory 或 compact artifact 结构变化都会牵动 message 构造层。
- **最小建议**: phase design 必须以 Provider Protocol 为第一层切片，而不是先定义 Builder 读取哪些表 / snapshot。最小 provider 集合包括 canonical fact projector、memory block provider、compact artifact provider、tool schema snapshot provider、scene message provider、policy message provider。Provider 输出 message-ready block 和解释 refs；Builder 只负责排序、预算协调与最终 request 装配。
- **建议去向**: phase design checklist 必须前置；若 `design.md` 会作为 implementation agent 的唯一入口，则需要补一句 Provider Protocol 边界，避免设计真源继续误导。

### SMELL-HOST-003-未修复-中-EventLog contract 仍是 event-centric，缺少 per-consumer typed contract

- **id**: `SMELL-HOST-003`
- **severity**: 中
- **位置**: `docs/host/design.md` 12.3 Canonical Event Contract Matrix、13 Observer / Sink / Projection；controller 裁决 B8。
- **坏味道类型**: EventLog consumer 需要理解过多 `event_type`，缺少 per-consumer contract。
- **问题**: 12.3 的矩阵按 event type 描述 payload、状态副作用、resume / memory、audit / stream；13 节只要求 sink 声明消费哪些 event_class / event_type。它仍没有按消费者定义“必须消费 / 必须忽略 / payload view / 投影输出”的 typed contract。
- **为什么会影响 phase design / phase plan**: 如果 phase plan 直接让 Memory、RunInputBuilder、Audit、Outbox、ToolTrace 各自遍历同一张 event matrix，它们会各自实现事件筛选、payload 解析和忽略规则。结果是 EventLog schema 变化会扩散到所有 consumer，且容易出现某个 consumer 把 diagnostic / preview 或不该消费的 canonical event 当作事实输入。
- **最小建议**: EventLog phase design 增加 per-consumer contract 表，而不是只扩充全局 event matrix。建议至少拆成 StateTransitionConsumer、RunInputFactProjector、MemoryProjectionInput、OutboxIntentProjector、AuditEventProjector、ToolTraceProjector、HostEventStreamProjector；每个 contract 明确 allowed event_class、allowed event_type、typed payload view、must-ignore 列表和 cursor / checkpoint 语义。
- **建议去向**: phase design checklist。架构级 design 已有“sink 必须声明消费范围”的方向，不必写完整 consumer 表。

### SMELL-HOST-004-未修复-中-ToolRuntime 职责清单过宽，phase slicing 若不拆 port 会自然长成 God object

- **id**: `SMELL-HOST-004`
- **severity**: 中
- **位置**: `docs/host/design.md` 17 ToolRuntime，尤其是 `ToolRuntime wraps tool registry / dispatcher / policies`、负责工具注册装配、权限 / policy、并发 / timeout / cleanup、awaiting、truncation / fetch_more、duplicate governance、trace diagnostics、工具级 idempotency；controller 裁决 B10。
- **坏味道类型**: ToolRuntime 过度聚合；职责泄漏。
- **问题**: 当前设计正确限定 Engine 只看 `ToolExecutor`，但 ToolRuntime 内部边界仍是职责清单，没有把执行、治理、持久化 accept、截断、等待、重复治理、诊断输出拆成 narrow ports。实现上很容易出现一个 `ToolRuntime.execute` 同时做工具注册查找、权限、并发、duplicate index、截断 descriptor、wait record candidate、trace 诊断和 accept barrier。
- **为什么会影响 phase design / phase plan**: ToolRuntime 是 Host / Engine 接缝上风险最高的模块之一。若 phase slicing 以一个大 ToolRuntime 类为中心，后续 remote/local accept barrier、truncation descriptor lifecycle、duplicate reuse model-facing response、awaiting resume 会互相耦合，review 也无法判断某个 slice 是否只改了一个责任。
- **最小建议**: ToolRuntime phase plan 第一层先拆内部 port：ToolRegistryView、ToolDispatchPort、ToolPolicyEvaluator、DuplicateGovernance、TruncationService、AwaitingOutcomePort、ToolFactAcceptPort、TraceDiagnosticEmitter、CleanupPolicy。`ToolRuntime` 只编排 typed outcomes，并实现 `ToolExecutor`；每个 port 的输入输出必须是 typed value，不共享 god context。
- **建议去向**: phase design checklist，不需要扩大 `design.md`。

### SMELL-HOST-005-未修复-中-Context Governance 清单把预算、memory patch、compact artifact 与 trace / audit 投影放在同一责任句法下

- **id**: `SMELL-HOST-005`
- **severity**: 中
- **位置**: `docs/host/design.md` 24 Context Governance，尤其是 Host 负责列表中的 `RunInputBuilder 输入层预算分配`、`LLM episode summary compaction`、`pinned_state patch`、`trace / audit projection`，以及 compact path 中 `compacts inputs / memory / evidence summaries`；controller 裁决 B6。
- **坏味道类型**: Context Governance 过度聚合；Projection / trace / memory 反向贴近 command path。
- **问题**: 设计意图是 Context Governance 编排 Host-side compact，但当前措辞容易被实现为一个直接读取 / 修改 memory 内部结构、生成 trace / audit projection、同时做预算估算和 message rebuild 的治理大模块。`pinned_state patch` 和 `trace / audit projection` 特别容易让 command path 直接碰 memory projection 与 sink 输出。
- **为什么会影响 phase design / phase plan**: Context phase 很可能与 RunInputBuilder、Memory、EventLog、ToolTrace 同时接壤。如果不先定 provider / artifact / sink 边界，phase plan 会难以决定哪些文件归 Context Governance，哪些归 Memory projection，哪些归 Trace / Audit sink，进而诱发跨模块修改和反向依赖。
- **最小建议**: Context Governance phase design 把它定义为 orchestrator：通过 BudgetEstimator、CompactInputProvider、CompactionExecutor、CompactArtifactStore、MemoryPatchProposalPort、AfterCommitDiagnosticPort 协作。Memory 是否吸收 compact summary 由 Memory projection policy 决定；trace / audit 只从 compact canonical events 或 projection_signal 派生，Context Governance 不直接写 projection。
- **建议去向**: phase design checklist。若保留 `pinned_state patch` / `trace / audit projection` 这些词，建议在 checklist 中明确它们是 proposal / event source，不是直接 projection writer。

### SMELL-HOST-006-未修复-中-Outbox target freeze 在 design.md 中仍不够硬，OutboxSink 可能被迫理解 request / session binding 语义

- **id**: `SMELL-HOST-006`
- **severity**: 中
- **位置**: `docs/host/design.md` 15 Outbox 只说 delivery target 来自 `HostCallContext`、Session binding 或 request 显式字段；controller 裁决 A9 明确要求 Run acceptance transaction 冻结 resolved delivery target。
- **坏味道类型**: Sink / transport 层理解 governance 语义；Projection 反向耦合 command path。
- **问题**: 当前 `design.md` 已禁止从 metadata 猜 target，但没有明确“在 Run acceptance command transaction 中冻结 resolved delivery target”。如果后续按 15 节实现，OutboxSink 在扫描 terminal fact 时可能需要重新解析 HostCallContext、Session binding default 或 request 字段，等于让 projection / delivery 层理解 command acceptance 时的治理语义。
- **为什么会影响 phase design / phase plan**: Outbox phase 的 ownership 会变模糊：delivery target 解析到底属于 Run acceptance command path，还是 OutboxSink terminal projection？若不冻结，session binding 后续变更、resume / wait resolution、replay 或 background delivery retry 都可能读到不同 target，导致投递不可解释。
- **最小建议**: 写回 `design.md`：resolved delivery target 在 `RUN_ACCEPTED` 同一 transaction 冻结，进入 `RUN_ACCEPTED` payload 或 Run durable state；OutboxSink 只读取 terminal fact + frozen delivery target ref，不重新解析 request / HostCallContext / Session binding；无 target 时不创建 delivery record。
- **建议去向**: `design.md` 写回。该项影响 sink 与 command path 的 semantic contract。

### SMELL-HOST-007-未修复-低-HostPolicyProviderSet 的“不传全量 provider set”边界需要在 phase plan 前锁死

- **id**: `SMELL-HOST-007`
- **severity**: 低
- **位置**: `docs/host/design.md` 9.1 HostPolicyProviderSet；16 Worker dispatch 的 attempt snapshot 包含 `policy snapshot ids / refs required to explain execution`；22 RunInputBuilder 输入包含 `runner / policy config`；controller 裁决 A13。
- **坏味道类型**: policy object 变成 god bag / service locator。
- **问题**: `design.md` 已说明 HostPolicyProviderSet 不是 registry 或 god bag，但尚未明确它只能存在于 composition root，且 ToolRuntime、RunInputBuilder、OutboxSink 不得回查全量 provider set。当前 `runner / policy config` 与 attempt snapshot 的 `policy snapshot ids / refs` 如果不收窄，implementation agent 可能把整个 provider set 传入各子系统，让子系统在运行中任意拉取 unrelated policy。
- **为什么会影响 phase design / phase plan**: Policy ownership 会跨 phase 扩散。ToolRuntime phase、Context phase、Outbox phase 和 RunInputBuilder phase 都可能各自新增 policy lookup，导致 policy 依赖不可审计，也难以重放“当时看到的是哪版 policy”。
- **最小建议**: phase plan 前明确：HostPolicyProviderSet 只在 composition root / acceptance command path 使用；Attempt snapshot 只携带执行所需 immutable typed policy subset 或 policy snapshot refs；RunInputBuilder、ToolRuntime、OutboxSink 只接收自己的 policy view，不接收全量 provider set。
- **建议去向**: 可写回 `design.md` 一句边界；至少进入 phase design checklist。

## Non-findings / 降级判断

- **Remote transport 没有发现新增系统性坏味道**：`docs/host/design.md` 已明确 RemoteProxy 是 transport substitution，不是治理 boundary；wire protocol 细节不得改变 semantic contract；RemoteStub / EngineWorker 不 append EventLog、不关闭 Attempt、不更新 Run。
- **Projection / Sink 总方向成立**：设计已明确 Sink 只消费 committed EventLog、按 checkpoint 追平、失败不回滚 EventLog、不改变 Run / Attempt 状态。当前问题不是方向错误，而是 per-consumer contract 与 command handle facet 还需细化。
- **ToolRuntime 放在 Host ownership 下是必要耦合，不是问题本身**：问题只在内部 port 和 phase slicing 尚未锁死。

## 写回 vs Phase Checklist

应写回 `design.md` 的最小项：

- `SMELL-HOST-001`：Host command handle 与 background supervisor facet 分离。
- `SMELL-HOST-006`：Outbox delivery target 在 Run acceptance transaction 冻结，OutboxSink 不重新解析 command / session binding 语义。
- `SMELL-HOST-007`：HostPolicyProviderSet 只在 composition root；子系统只接收 immutable typed policy view / refs。

只应进入 phase design checklist 的项：

- `SMELL-HOST-002`：RunInputBuilder Provider Protocol。
- `SMELL-HOST-003`：per-consumer EventLog contract。
- `SMELL-HOST-004`：ToolRuntime internal ports / slicing。
- `SMELL-HOST-005`：Context Governance orchestrator 与 memory / trace / audit 边界。

## 是否发现系统性坏味道

未发现“整体 Host 设计系统性错误”或需要推翻当前架构的坏味道。已发现的问题是局部聚合边界没有完全收窄：几个高连接度组件仍需要在 phase design 前通过 typed provider、port、facet 和 per-consumer contract 固化边界。

## 是否阻塞当前 design cleanup

不阻塞继续进行 design cleanup；但若目标是把 `docs/host/design.md` 作为 phase plan 的唯一稳定真源，则 `SMELL-HOST-001`、`SMELL-HOST-006`、`SMELL-HOST-007` 应在 cleanup 完成前写回。其余 finding 不应扩大架构文档，进入对应 phase design entry checklist 即可。

## 建议下一步重点讨论的 3 个问题

1. Host composition 是否明确拆成 command handle、background supervisor、after-commit wakeup port 三个 facet，并约束公共 mutating API 只拿 command handle。
2. RunInputBuilder / Context Governance 的 provider 边界是否统一：谁负责把 EventLog / memory / compact artifact / scene / policy 转成 message-ready block，谁只做排序与预算协调。
3. EventLog per-consumer contract 如何组织：是为每个 consumer 定义独立 projector / payload view，还是先定义共享 canonical fact view 再由各 consumer 声明子集。

## Final Plan Review Conclusion

`pass-with-risks`。主架构方向成立；未发现系统性过度设计或治理真源反转。但上述 P1 边界如果不在 phase design 前收敛，下一阶段实现很容易重新生成 RunInputBuilder 原设计同类的“组件知道太多内部结构”坏味道。
