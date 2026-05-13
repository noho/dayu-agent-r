# Host Phase Map Review - AgentCodex - 2026-05-13

## Findings

### P0-1-未修复-[严重]-Host 架构真源路径冲突，当前 target docs 不足以支撑下一步 phase plan
- **状态**: accepted-candidate
- **位置**: `docs/host/implementation-control.md:29`, `docs/host/implementation-control.md:44`, `docs/host/implementation-control.md:54`, `docs/host/implementation-control.md:66`, `docs/host/implementation-control.md:71`, `docs/host/implementation-control.md:1221`; `docs/design.md:1`; `docs/design.md:3`; `docs/host/design.md:1`
- **问题类型**: 架构边界 / 真源缺失 / 不可直接实施
- **当前写法**: 用户指定 review target 是 `docs/design.md` 与 `docs/host/implementation-control.md`；但实施总控的 phase 条目和当前状态实际指向 `docs/host/design.md` 作为 Host 架构真源。总控前半段又多次使用裸 `design.md`，例如真源层级写 `design.md -> Host 架构真源`，工作流要求细化 `design.md`。
- **反例/失败场景**: 下一步 planner 若按本次 target 只读 `docs/design.md`，只能得到仓库级日志与可观测性设计，无法获得 Host 的 Session / Run / Attempt、EventLog、恢复、ToolRuntime、Remote 等架构契约；若按总控后半段读取 `docs/host/design.md`，则和本次 review target 不一致，当前 gate 的审查结论无法覆盖实际架构源。
- **为什么有问题**: phase plan 必须基于确定的架构真源，否则 implementation agent 只能从 implementation-control 的护栏和 phase 摘要反推架构，等于让编排文档承担架构设计职责。`docs/design.md` 明确是“Dayu 整体架构设计”，并说明包内局部机制由包级 README 或专题设计文档承载；`docs/host/design.md` 的标题和内容才是 Host 设计。
- **直接证据**: `docs/design.md:1` 标题为 `Dayu 整体架构设计`，`docs/design.md:3` 说明它记录仓库级设计决策；`docs/host/design.md:1` 标题为 `Host 设计`；`docs/host/implementation-control.md:1221` 明确写 `docs/host/design.md` 已是 Host 架构真源；但 `docs/host/implementation-control.md:29`、`:44`、`:54`、`:66`、`:71` 仍使用裸 `design.md`。
- **影响**: 下一个 phase discussion / plan 可能选错文件，或者在没有审查实际 Host 架构真源的情况下进入 implementation-ready plan；这会导致 plan 不可验收、架构猜测、路径争议和后续返工。
- **建议改法和验证点**: 把 `docs/host/implementation-control.md` 中所有 Host-specific 的裸 `design.md` 改为显式 `docs/host/design.md`；同时说明 `docs/design.md` 只承载仓库级跨层设计。若本 gate 要判断 Host phase map 是否足以进入下一步，应把 `docs/host/design.md` 纳入必读 / 必审 target，而不是用 `docs/design.md` 替代。验证点：`rg -n "design.md" docs/host/implementation-control.md` 中 Host 架构引用均指向 `docs/host/design.md`，`docs/design.md` 只在跨层仓库设计语境出现。
- **修复风险**: 低
- **严重程度**: 严重

### P1-1-未修复-[高]-Phase 0 被设成 Phase 1 默认前置，过度耦合 Engine cleanup 与无关 Host 基础设施
- **状态**: accepted-candidate
- **位置**: `docs/host/implementation-control.md:212`, `docs/host/implementation-control.md:222`, `docs/host/implementation-control.md:228`, `docs/host/implementation-control.md:277`, `docs/host/implementation-control.md:790`
- **问题类型**: 过度耦合 / 架构边界 / sequencing 风险
- **当前写法**: Phase 0 是 Engine context compaction event contract / README / tests cleanup，且前置条件是用户确认允许修改 Engine 代码；Phase 1 的前置条件却要求 Phase 0 已完成，除非用户明确决定 Phase 0 只阻塞 Context Governance。Phase 10 已经单独把 Phase 0 作为 Context Governance 前置或临时兼容假设。
- **反例/失败场景**: 实施 Phase 1 公共契约、`dayu.runtime.lane`、`filelock`、ToolsDiscovery / ScenePrepare 时并不消费 Engine overflow budget 语义，但 planner 会因为 Phase 1 默认前置被迫先启动 Engine work unit，或把 Engine cleanup 混入 Host 基础设施计划。
- **为什么有问题**: 这把只影响 Context Governance 的 Engine contract cleanup 扩大成整个 Host phase map 的全局 gate，削弱了分层边界，也让不需要 Engine 修改的 Host foundational work 依赖用户对 Engine 修改的确认。Phase 0 的后续依赖本身只说 Host Context Governance phase 必须使用 Host estimator / policy；Phase 10 已有正确局部依赖。
- **直接证据**: Phase 0 范围允许修改 Engine contract / README / docs / tests，禁止修改 Host 实施代码；Phase 1 前置要求 Phase 0 完成；Phase 10 前置再次要求 Phase 0 完成或写明临时兼容假设。
- **影响**: Phase 1 handoff plan 会被无关 Engine work 阻塞，或在 Host work 中夹带 Engine 修改；review 时也难以判断 Phase 1 的 success signal，因为它被一个 Context Governance 专属风险污染。
- **建议改法和验证点**: 将 Phase 0 从 Phase 1 前置条件移除，改成独立 Engine work unit 或标注为“仅阻塞 Phase 10 Context Governance / reactive overflow recovery”。Phase 1 只依赖 `dayu/README.md` 术语真源和 `docs/host/design.md` 对 runtime、Host public typing、ToolBundle input 的设计。验证点：Phase 1 handoff plan 能在不修改 Engine 的前提下生成；Phase 10 handoff plan 必须显式检查 Phase 0 完成状态或写明禁止消费 `0/0/0` 的临时假设。
- **修复风险**: 低
- **严重程度**: 高

### P1-2-未修复-[高]-Recovery phase 把 projection checkpoint 设为前置，和“projection 不是真源”边界冲突
- **状态**: accepted-candidate
- **位置**: `docs/host/implementation-control.md:849`, `docs/host/implementation-control.md:852`, `docs/host/implementation-control.md:861`, `docs/host/design.md:41`, `docs/host/design.md:54`, `docs/host/design.md:55`, `docs/host/design.md:2063`
- **问题类型**: 架构边界 / 过度耦合 / 恢复语义风险
- **当前写法**: Phase 11 的前置条件包含 `Phase 8 projection checkpoint 已完成`；同一 phase 又声明不从 projection 或 memory 恢复 Run truth。Host design 明确 projection、timeline、audit、usage、tool trace、outbox、memory snapshot 都不能反向成为 EventLog 真源，Recovery 是唯一负责 startup scan、旧 Attempt `LOST` 收口和可恢复 Run 新 Attempt 创建的模块。
- **反例/失败场景**: implementation agent 可能把 projection checkpoint 当成 recovery scan 的输入或完成条件；或者在 projection runner 尚未实现、损坏或落后时，认为 accepted prompt crash recovery 不能实现。更隐蔽的失败是测试只通过 read model / projection 成功证明 recovery，而没有证明 EventLog 与 Run / Attempt indexes 在 projection 停止时仍可恢复。
- **为什么有问题**: Recovery 的事实依据应是 durable store 中的 Run / Attempt indexes、EventLog、dispatch record 和 host instance liveness，而不是 projection checkpoint。把 Phase 8 作为 Phase 11 前置会把核心治理能力绑定到派生视图框架，削弱 Host 对 durable facts 可恢复的核心目标。
- **直接证据**: `docs/host/implementation-control.md:852` 要求 Phase 8 projection checkpoint 完成；`:864` 又禁止从 projection 或 memory 恢复 Run truth。`docs/host/design.md:41` 禁止 projection 反向成为 EventLog 真源，`:54` 定义 Observer / Sink / Projection 只消费 committed events，`:55` 定义 Recovery 负责 startup scan 和新 Attempt 创建，`:2063` 开始的 recovery 语义从 Host 启动扫描 Run / Attempt indexes。
- **影响**: 可能生成错误的 recovery plan、错误测试边界，或把 production-critical crash recovery 推迟到 read model/projection 成熟之后；这会让 Host 在已 accepted prompt 崩溃场景下的核心 guarantee 后移。
- **建议改法和验证点**: 从 Phase 11 前置条件移除 Phase 8 projection checkpoint，替换为 Phase 2 durable store / host instance liveness、Phase 3 state transition / admission、Phase 5 dispatch record / LocalProxy semantic baseline。若需要证明恢复后的 terminal 可被 UI 读取，可作为 Phase 8 已存在时的附加集成验证，不作为 recovery entry condition。验证点：Phase 11 测试在 projection runner 停止或 projection checkpoint 落后时仍能通过 EventLog 与 state indexes 完成 recovery；另设可选测试证明 projection 后续能追平 recovered terminal。
- **修复风险**: 中
- **严重程度**: 高

### P2-1-未修复-[中]-追踪区使用不存在或非编号 phase 名称，deferred items 缺少可执行 owner
- **状态**: accepted-candidate
- **位置**: `docs/host/implementation-control.md:1168`, `docs/host/implementation-control.md:1182`, `docs/host/implementation-control.md:1183`, `docs/host/implementation-control.md:1196`, `docs/host/implementation-control.md:1200`, `docs/host/implementation-control.md:1214`
- **问题类型**: stale reference / handoff boundary 不清 / 追踪归属缺失
- **当前写法**: 追踪区使用 `ToolRuntime / Tool Schema phase`、`Public API / Storage phase`、`Storage phase`、`State machine phase`、`Projection / Sink phase`、`Service / UI phase` 等名称，但 Phase Map 实际只有 Phase 0-14，且没有 `Tool Schema phase`、`Storage phase` 或单独的 `Projection / Sink phase`。
- **反例/失败场景**: purge 的 request / tombstone / shared artifact ref check 可能被 Phase 2、Phase 4 和 Phase 14 互相推诿；外部副作用工具的 idempotency key 与 side-effect policy 可能落到不存在的 Tool Schema phase；Outbox terminal identity 可能被 Phase 8 projection core 或 Phase 12 OutboxSink 计划重复定义。
- **为什么有问题**: 总控文档自己的追踪规则要求任何 deferred 项都必须有 owner / destination；非编号 phase 名称不是可执行 destination，后续 phase discussion 无法直接判断哪些追踪项必须纳入本 phase 的 exit criteria。
- **直接证据**: `docs/host/implementation-control.md:1081` 要求任何 deferred 项都有 owner / destination；但 `:1168`、`:1182`、`:1183`、`:1196`、`:1200`、`:1214` 使用的 phase 名称无法和 Phase Map 中 `### Phase N` 一一对应。
- **影响**: 追踪项可能在 phase handoff 之间丢失，或者被 implementation agent 自行选择归属，导致 scope creep、重复实现或关键验证遗漏。
- **建议改法和验证点**: 把追踪区所有 phase owner 改为精确 `Phase N. 名称`；跨 phase 项拆成多条。例如：side-effect tool policy 归 `Phase 6`，Remote late tool result 验证归 `Phase 13`；`purge_session` request/result contract 若只稳定类型归 `Phase 4`，destructive cleanup / tombstone / shared artifact ref check 归 `Phase 14`，若 Phase 2 必须预留 durable primitive 则明确写入 Phase 2 exit condition；Outbox item identity 归 `Phase 12`，Service / UI seen cursor 标为 Host 外部后续 work unit。验证点：追踪区 `rg -n "phase" docs/host/implementation-control.md` 的每个 owner 都能映射到 Phase Map 中的编号 phase 或明确外部 destination。
- **修复风险**: 低
- **严重程度**: 中

## Reviewed Target And Scope

- 指定 target：`docs/design.md`、`docs/host/implementation-control.md`。
- 辅助核对：`dayu/README.md` 术语真源、`docs/host/design.md` 的存在性与章节索引，仅用于判断 target 是否选错和实施总控引用是否可解析。
- 审查重点：phase map 是否能进入下一步 phase discussion / handoff implementation-ready plan；是否存在过耦合、god-phase、缺少 non-goals / allowed modules、边界不清、依赖循环、stale references 和验证缺口。
- 动机判断：该 review 动机成立。当前文档处于 phase map draft，若不先澄清真源与 phase 依赖，后续 implementation plan 会被迫猜架构。

## Assumptions Tested

- 每个 phase plan 必须能只基于架构真源与 implementation-control 的范围 / 依赖 / 退出条件生成，不应从编排文档反推架构。
- 编排文档不得把只影响后续某 phase 的风险提升为所有 Host work 的全局 blocker。
- Recovery、projection、memory、outbox 等边界必须保持 EventLog / state indexes 为治理真源，projection 只能是派生能力。
- 总控阶段可以不固定每个 implementation slice 的最终细节，但必须给后续 phase discussion 留出明确 owner、non-goals、validation 和 handoff boundary。

## No Finding Notes

- Phase Map 大多数 phase 条目包含目标、设计章节、前置 / 进入条件、范围、不做、关键设计问题、交付物、建议 slices、验证要求、退出条件和后续依赖；条目形状总体可用于 phase discussion。
- Slice 切分在总控阶段没有过早固定到文件级实现，和 `docs/host/implementation-control.md:84` 开始的切分原则一致；最终 slices 留到 phase discussion / phase plan 再确定是合理的。
- Phase 5 和 Phase 6 范围较宽，但当前文档通过 suggested slices 把 RunInputBuilder、dispatch、EngineEvent ingest、cancel、ToolRuntime accept barrier、truncation、fetch_more 和 duplicate governance 分开；在 phase map draft 层面未形成单独 god-phase blocker。
- 多数关键路径都有 unit tests、integration tests、pyright 和 docs update 要求；不是只依赖 happy path e2e。
- `docs/host/design.md` 中被 phase 条目引用的主要章节号存在，包括 §3、§5-§28、§9.1、§10.1、§13.1-§13.4、§14.1、§18.1-§18.3、§25.1、§27.1。
- 未发现明确的编号依赖环；已报告的问题是局部过度前置和 tracking owner 不清。

## Open Questions

- 本 gate 是否应补做一次以 `docs/host/design.md` 为 target 的 Host architecture source review？当前指定的 `docs/design.md` 无法承担 Host 架构真源审查。
- Phase 0 是否应保留编号为 Host Phase 0，还是应移出 Host phase map，作为 Phase 10 前的独立 Engine work unit？
- Service / UI Outbox dedupe tracking 是否仍放在 Host implementation-control 中，还是拆到 Host 外部后续 work unit registry？

## Residual Risks

- 本次没有完整审查 `docs/host/design.md` 的架构内容，只用它确认真源路径和章节存在性；实际 Host 架构是否足够支撑每个 phase plan 仍需在正确 target 下复审。
- phase map 仍以模块描述而非具体文件路径描述 allowed scope。考虑到 Host 代码实施尚未开始，这在总控阶段可接受；但每个 handoff implementation-ready plan 必须补齐具体 allowed files / modules。
- Phase 14 同时包含 purge、projection rebuild、production smoke、docs 和 residual risk closeout，后续 phase discussion 必须继续拆 slice，避免 release-hardening god-phase。

## Final Plan Review Conclusion

`fail`

存在 blocking findings。当前 phase map 方向整体可信，但在进入下一步 phase planning 前，必须先修正 Host 架构真源路径、Phase 0 的过度前置、Recovery 对 projection checkpoint 的错误前置，并把追踪区 owner 改成精确 phase / 外部 destination。
