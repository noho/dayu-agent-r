# Host Design v2 Final Readiness Review

- **Reviewer**: MiMo
- **Date**: 2026-05-13
- **Gate**: Host draft design v2 final readiness review
- **Scope**: `docs/host/design.md`, `docs/host/implementation-control.md`
- **术语真源**: `dayu/README.md`

## Verdict

**Pass with non-blocking findings**

设计整体 ready 进入 phase 编排。架构边界硬、semantic contract 足够清晰、状态机覆盖主要路径、EventLog 真源层级明确。无 blocker。存在若干 medium / low findings 和 over-coupling 观察，可在对应 phase discussion 中解决，不阻塞 phase plan 启动。

---

## Findings

### Blocker

无。

### High

#### H-1: `STEER_REQUESTED` 与 steer-lost 竞态缺 canonical event 定义

**位置**: design.md §8.1 状态迁移契约、§11 Follow-up 与 Steer、§12.2 Canonical Event 最小集合

**证据**:
- §11 明确描述了 "Host 已 append `STEER_REQUESTED` 但旧 Attempt 先提交 terminal 时，terminal 优先；Host 只能记录 steer-lost diagnostic / projection"。
- §12.2 canonical event 最小集合包含 `STEER_REQUESTED`，但不包含 steer-lost 相关 canonical event。
- §8.1 状态迁移表只覆盖 steer 成功路径，不覆盖 steer 竞态失败路径。

**风险**: 实现 agent 无法确定 steer-lost 应该写入什么 event type / event_class。是 `diagnostic`？是新增 canonical event？还是只写 projection？如果 phase plan 不澄清，实现可能自行发明，破坏 EventLog 一致性。

**建议裁决**: High — 在 steer phase discussion 中明确 steer-lost 的 event class 和 event type。大概率应为 `diagnostic` event class + `STEER_LOST` event type，但需显式确认。

---

#### H-2: `resolve_wait` canonical fact 序列与状态迁移表不一致

**位置**: design.md §8.1 状态迁移契约 vs §19 Tool Awaiting / Wait Record vs §20 Suspend / Resume / Retry / Replay

**证据**:
- §8.1 表格: `resolve_wait` -> 必须追加 `RESUME_REQUESTED`、tool terminal/result fact、`RUN_STARTED`、`ATTEMPT_STARTED`。
- §20 Resume 文本: "Host appends RESUME_REQUESTED -> Host appends tool terminal/result fact -> Host creates new Attempt"。
- §8.1 中 `RUN_STARTED` 出现在 resolve_wait 路径，但 §6 Run 生命周期中 `RUN_STARTED` 语义是 "Run 已占用 Session active slot"。对于 `WAITING -> RUNNING` 的恢复路径，是否需要 `RUN_STARTED` 还是应使用 `RUN_RESUMED` 或其它语义更精确的 event？

**风险**: 如果实现 agent 直接按表格追加 `RUN_STARTED`，语义上可能与首次 `start_run` 的 `RUN_STARTED` 混淆。恢复路径和首次启动路径的 canonical fact 是否应该区分？

**建议裁决**: High — 在 wait/resume phase discussion 中明确 `WAITING -> RUNNING` 恢复路径的 canonical fact 序列。如果 `RUN_STARTED` 确实复用，需在 contract matrix 中说明恢复场景也使用 `RUN_STARTED` 的语义覆盖范围。

---

#### H-3: recovery 路径中 `RECOVERING -> RUNNING` 的 Attempt 创建时序未完整定义

**位置**: design.md §8.1 状态迁移契约、§26 Host Lifecycle / Recovery

**证据**:
- §8.1 表格: recovery scan -> `RUN_RECOVERING` 或 `RUN_LOST` -> "可恢复时再创建新 Attempt"。
- §26 分类规则: "RUNNING / CANCELLING 且具备 positive orphan proof：通过 CAS 将旧 Attempt -> LOST；Run 按 policy 与事实完整性进入 RECOVERING 或 LOST"。
- §8.1 RECOVERING 退出: "RECOVERING -> RUNNING：Host 成功基于 canonical facts 创建新 Attempt，记录 dispatch intent，并让 Attempt 进入 STARTING"。

**缺口**: 从 `RECOVERING` 到 `RUNNING` 的路径中，是否需要追加新的 `RUN_STARTED` canonical fact？还是 `RUN_RECOVERING` 本身就表达了 "Run 正在恢复" 的语义，新 Attempt 创建只需追加 `ATTEMPT_STARTED`？§8.1 表格中 recovery scan 行的 "必须追加的 canonical facts" 列只写了 `ATTEMPT_LOST`、`RUN_RECOVERING` 或 `RUN_LOST`，没有写恢复成功后的 `RUN_STARTED` / `ATTEMPT_STARTED`。

**建议裁决**: High — 在 recovery phase discussion 中补全 recovery 成功路径的完整 canonical fact 序列。至少应包含 `ATTEMPT_STARTED`；是否需要额外 event 表达 "恢复成功" 需确认。

---

### Medium

#### M-1: `ContextCompactionRequestedData.budget_state` 占位语义在 canonical event contract matrix 中未显式标注

**位置**: design.md §12.3 Canonical Event Contract Matrix、implementation-control.md 追踪区

**证据**:
- implementation-control.md "Engine Context Compaction Event 语义前置" 追踪区明确说明当前 Engine 的 `budget_state` 是 `ContextBudgetSnapshot(0, 0, 0)` 占位。
- design.md §12.3 `CONTEXT_COMPACTION_REQUESTED` 行: "必需 payload" 列包含 "trigger source / budget reason / provider error refs / snapshot refs"。
- 但 design.md 没有明确说 `budget_state` 在 reactive trigger 场景下可能是 unknown / placeholder。

**风险**: Phase plan agent 可能把 `0/0/0` 当作真实预算。

**建议裁决**: Medium — implementation-control.md 已追踪此问题。建议在 design.md §24.1 reactive trigger 约束中显式加一句："reactive trigger 的 budget snapshot 可能为 unknown / placeholder；Host Context Governance 不得将其作为预算决策输入。" 但此修改可在 Context Governance phase discussion 中完成，不阻塞 phase 编排启动。

---

#### M-2: payload 存储阈值与策略边界未定义

**位置**: design.md §9 Durable Store、§12.1 Payload 存储

**证据**:
- §9: "小型 / 中型可恢复 payload 可以写入 SQLite payload table"。
- §12.1: "超过 Host policy 阈值的大工具结果...必须外移到 artifact / blob / tool trace / 领域仓储"。
- 阈值是什么？由谁定义？policy provider 的哪个分支负责？

**风险**: 实现 agent 需要猜测 "小型 / 中型" 的边界。

**建议裁决**: Medium — 在 Storage / Payload phase discussion 中定义默认阈值策略（例如 100KB inline / >100KB external），并明确属于 `ToolGovernancePolicyView` 还是独立的 `PayloadPolicyView`。不阻塞 phase 编排。

---

#### M-3: `purge_session` 对共享 cold artifact 的引用检查机制未定义

**位置**: design.md §4 Session 生命周期

**证据**:
- design.md: "共享 cold artifact 只有在没有其它 durable ref 引用时才允许被清理"。
- implementation-control.md: "Storage phase 必须定义共享 cold artifact 的引用计数或 ref 检查"。

**风险**: 实现时可能跳过引用检查，导致 purge 删除其它 Session 仍引用的 artifact。

**建议裁决**: Medium — 已在 implementation-control.md 追踪。在 Storage / Purge phase discussion 中定义 ref check 机制即可。

---

#### M-4: `RunInputBuilder` 的 7 个 typed provider 与 `HostPolicyProviderSet` 的 7 个 policy provider 存在潜在职责重叠

**位置**: design.md §9.1 Host Handle / Composition Root、§22 RunInputBuilder

**证据**:
- §22 定义了 `CurrentRunFactProvider`、`SessionContinuityProvider`、`MemorySnapshotProvider`、`CompactArtifactProvider`、`ToolSchemaSnapshotProvider`、`SceneParameterProvider`、`PolicySnapshotProvider`。
- §9.1 定义了 `AdmissionPolicyView`、`WorkerSelectionPolicyView`、`ToolGovernancePolicyView`、`ContextBudgetPolicyView`、`OutboxPolicyView` 等 typed policy views。
- `PolicySnapshotProvider` 是 RunInputBuilder 的输入之一，而 policy views 来自 `HostPolicyProviderSet`。

**风险**: 如果不明确 `PolicySnapshotProvider` 是从 `HostPolicyProviderSet` 解析后的 typed view 聚合，还是独立的 provider，phase plan agent 可能设计出两套独立的 policy 解析路径。

**建议裁决**: Medium — 在 RunInputBuilder phase discussion 中明确 `PolicySnapshotProvider` 的来源是 composition root 解析后的 typed policy snapshot refs，不是独立的 policy 存储。

---

#### M-5: `close_session` 的 `client_request_id` 幂等语义与 `ensure_session` 的 slot 幂等语义存在交互歧义

**位置**: design.md §4 Session 生命周期、§10 Host 公共接口

**证据**:
- `close_session` 按 `(session_id, client_request_id)` 幂等。
- `ensure_session` 按 `(scope, slot_key)` 幂等，不需要 `client_request_id`。
- 如果 `close_session` 后 UI 立即调用 `ensure_session(scope, slot_key)`，旧 Session 已 CLOSED，slot 仍绑定旧 Session。`ensure_session` 应返回 CLOSED Session 还是创建新 Session？

**风险**: §5 已说明 `ensure_session` 返回当前 slot Session，snapshot 标记为 CLOSED。但 UI 可能期望 `ensure_session` 在 CLOSED 后自动创建新 Session。

**建议裁决**: Medium — design.md §4 已部分覆盖此场景（"UI / Service 若要继续聊天，应显式调用 create_session(bind_slot=true)"），但 `ensure_session` 在 CLOSED Session 上的行为应在 phase discussion 中显式确认：返回 CLOSED snapshot 而不是自动创建新 Session。

---

### Low

#### L-1: `CONTEXT_COMPACTION_FAILED` 后的 retry 上限与退避策略仅约束为 "policy 上限"

**位置**: design.md §24.1

**证据**: "compact 必须有 policy 上限。compaction 后仍超过 budget threshold 时，Host 必须按 policy 降级输入层或 append CONTEXT_COMPACTION_FAILED 并让 Run 进入 FAILED / RECOVERING / LOST；不得无限 compact retry。"

**风险**: 低。policy 上限的默认值和退避策略属于 Host policy，不影响架构正确性。

**建议裁决**: Low — 在 Context Governance phase 定义默认重试次数（例如 3）和退避策略即可。

---

#### L-2: `replay_run` 的 `repair_instruction` 字段语义边界未定义

**位置**: design.md §10 Host 公共接口

**证据**: `ReplayRunRequest` 包含可选 `repair_instruction?`，但 design.md 没有定义该字段的语义边界：谁提供？是用户文本还是结构化 validation error？是否进入 messages？

**风险**: 低。phase plan agent 需要猜测。

**建议裁决**: Low — 在 Replay phase discussion 中明确 `repair_instruction` 的来源（Host 输出 policy 检查结果 + 可选用户文本）和进入 messages 的方式。

---

#### L-3: `EventLog.event_class` 的 `projection_signal` 与 `diagnostic` 的边界在实现中可能模糊

**位置**: design.md §12 EventLog

**证据**: §12 明确定义了四种 event_class，但 `projection_signal`（"只能由 Host ingest / Host policy 写入，用于 usage、tool trace 或其它 projection 输入"）和 `diagnostic`（"用于排错和 trace"）在某些场景下可能重叠，例如 tool trace policy decision。

**风险**: 低。§12 已有足够约束，实现 agent 在边界 case 可以按 "projection_signal 用于 Sink 消费输入，diagnostic 用于人工排错" 区分。

**建议裁决**: Low — 在 EventLog phase 中补充一个 decision rule 即可。

---

## Over-coupling / Overengineering Findings

### OE-1: `HostPolicyProviderSet` + typed policy views 设计完备但第一版实现复杂度高

**位置**: design.md §9.1

**观察**: `HostPolicyProviderSet` 包含 7 个 policy provider，每个解析为 typed policy view。这是生产级治理的正确方向，但第一版如果全部实现，每个 policy provider 都需要接口定义、默认实现、typed view 和注入路径。

**建议**: 第一版可以先实现 `AdmissionPolicyView`（queue / reject / steer / attach 决策）、`ToolGovernancePolicyView`（截断、重复治理）和 `ContextBudgetPolicyView`（compact 阈值）。其余 policy 可以用 hardcoded defaults + typed stub 实现，后续 phase 逐步填充。设计本身不过度，但 phase plan 应合理分配实现节奏。

### OE-2: RunInputBuilder 的 7 个 typed provider 接口可能过早抽象

**位置**: design.md §22

**观察**: `CurrentRunFactProvider`、`SessionContinuityProvider`、`MemorySnapshotProvider`、`CompactArtifactProvider`、`ToolSchemaSnapshotProvider`、`SceneParameterProvider`、`PolicySnapshotProvider` — 这些 provider 的分离在架构上合理，但第一版 RunInputBuilder 的实现可能只需要 3-4 个实际输入源（EventLog reader、memory snapshot reader、tool schema snapshot、scene parameters）。过早定义 7 个独立 provider 接口可能增加 phase plan 的接口设计负担。

**建议**: 设计保留 7 个 provider 作为架构方向；第一版 phase plan 可以先实现为 RunInputBuilder 内部的 3-4 个 typed dependency，后续需要独立替换或测试时再抽取为独立 provider 接口。

### OE-3: ToolRuntime 内部 8 个 port 边界可能过早拆分

**位置**: design.md §17 ToolRuntime

**观察**: ToolRuntime 内部定义了 8 个 port（registry / dispatcher / policy / truncation / awaiting / duplicate / accept / trace）。这是生产级治理的正确方向，但第一版如果同时实现所有 port，每个都需要接口、实现和测试。

**建议**: 第一版可以先合并为 3-4 个核心 port（registry+dispatcher、policy+duplicate、truncation+accept、trace），后续按需拆分。设计保留 8 个 port 作为演进方向即可。

---

## Phase Readiness Gaps

### PRG-1: Engine Context Compaction Event 清理是前置依赖

**位置**: implementation-control.md 追踪区

**状态**: 已追踪。Host Context Governance phase plan 必须显式依赖 Engine cleanup 完成，或在 plan 中写明临时兼容假设。

**影响**: 不阻塞 phase 编排启动，但阻塞 Context Governance phase plan 的 handoff。

### PRG-2: steer 竞态路径的 canonical event 定义缺失

**位置**: design.md §11、§12.2

**状态**: 对应 H-1。

**影响**: 阻塞 steer phase plan 的完整 canonical event 定义。应在 steer phase discussion 中解决。

### PRG-3: recovery 路径的完整 canonical fact 序列未定义

**位置**: design.md §8.1、§26

**状态**: 对应 H-3。

**影响**: 阻塞 recovery phase plan 的状态迁移测试设计。应在 recovery phase discussion 中解决。

### PRG-4: SQLite 多进程写入正确性验证策略

**位置**: implementation-control.md 追踪区

**状态**: 已追踪。Storage phase 必须覆盖同 Session 并发 `start_run`、重复 `client_request_id`、active slot admission、queue promotion、cancel / terminal race、EventLog `event_sequence` 单调性。

**影响**: 不阻塞 phase 编排启动，但 Storage phase plan 必须包含明确的多进程测试策略。

### PRG-5: Remote 物理执行 exactly-once 非目标的测试覆盖

**位置**: implementation-control.md 追踪区

**状态**: 已追踪。RemoteProxy / RemoteStub phase 必须测试旧 `execution_id` 的迟到事件拒绝。

**影响**: 不阻塞 phase 编排启动。

---

## Residual Risks that Should Stay in implementation-control

| 风险 | 当前状态 | 建议 |
| --- | --- | --- |
| Engine Context Compaction Event 语义前置 | 已追踪 | 保持。Host Context Governance phase 显式依赖。 |
| External Job Cancel Adapter 能力 | 已追踪 | 保持。Tool Awaiting phase 定义 adapter 观察机制。 |
| Tool Trace / Provider Request 排错 | 已追踪 | 保持。tool trace phase 纳入 `provider_request_id`。 |
| SQLite 多进程写入正确性 | 已追踪 | 保持。Storage phase 明确 WAL / busy timeout / CAS / retry。 |
| Remote exactly-once 非目标 | 已追踪 | 保持。Remote phase 测试迟到事件拒绝。 |
| Session Purge / Archive | 已追踪 | 保持。Storage / Purge phase 定义 ref check 和 tombstone。 |
| Host 跨层测试策略 | 已追踪 | 保持。每个 phase 的 handoff plan 包含验证策略。 |
| UI / Service Outbox 去重边界 | 已追踪 | 保持。Projection / Sink phase 定义 terminal identity 去重。 |

**新增建议追踪项**:

| 风险 | 归属 phase | 建议 |
| --- | --- | --- |
| steer-lost 竞态 event class 定义 | Steer / Follow-up phase | 在 phase discussion 中明确 event type 和 event class。 |
| recovery 成功路径 canonical fact 序列 | Recovery phase | 在 phase discussion 中补全完整序列。 |
| `resolve_wait` 恢复路径是否复用 `RUN_STARTED` | Wait / Resume phase | 在 phase discussion 中确认语义覆盖范围。 |
| payload 存储阈值默认策略 | Storage / Payload phase | 在 phase discussion 中定义默认阈值。 |
| RunInputBuilder provider 接口第一版粒度 | RunInputBuilder phase | phase plan 可先合并为 3-4 个 dependency，后续按需抽取。 |
| ToolRuntime port 第一版粒度 | ToolRuntime phase | phase plan 可先合并为 3-4 个 port，后续按需拆分。 |
| `replay_run` 的 `repair_instruction` 语义边界 | Replay phase | 在 phase discussion 中定义来源和 messages 注入方式。 |

---

## Summary

设计文档质量高，架构边界硬，semantic contract 覆盖了 Host 治理的核心路径。EventLog 真源层级、canonical event 矩阵、admission / queue promotion、cancel / steer 竞态、WorkerProxy / ToolRuntime 边界、Outbox 投递语义、Recovery / positive orphan proof 均已定义到足够进入 phase 编排的粒度。

主要不足集中在：steer 竞态 canonical event 缺失（H-1）、`resolve_wait` 恢复路径 canonical fact 序列与表格不一致（H-2）、recovery 成功路径的完整 canonical fact 序列未定义（H-3）。这三项均为 "设计已覆盖语义但未落到 canonical event contract" 的 gap，可在对应 phase discussion 中解决，不构成 blocker。

over-coupling 观察（OE-1/2/3）均为 "设计方向正确但第一版实现可简化" 的建议，不影响架构正确性。

**结论: pass with non-blocking findings. 可以进入 phase 编排。**
