# Host Phase Map Review Controller Adjudication

日期：2026-05-13

输入报告：

- `docs/reviews/host-phase-map-review-mimo-20260513.md`
- `docs/reviews/host-phase-map-review-ds-20260513.md`
- `docs/reviews/host-phase-map-review-codex-20260513.md`

审查对象：

- `docs/host/design.md`
- `docs/host/implementation-control.md`

说明：用户已确认本轮 review 中的 `design.md` 应理解为 `docs/host/design.md`。`docs/design.md` 不是 Host 架构真源。

## 总体裁决

当前 phase map 方向成立，主链路 `contracts/runtime -> store/EventLog -> state machine/admission -> public API -> local dispatch -> ToolRuntime -> awaiting -> projection core -> memory -> context -> recovery -> projection sinks -> remote -> hardening` 可以继续作为总控骨架。

但 review 报告指出的若干编排问题成立。进入具体 phase plan 前，必须先把 accepted findings 写回 `docs/host/implementation-control.md`，否则后续 planning agent 会遇到错误真源、错误前置依赖或不明确 owner。

## A1. Host 架构真源路径

关联 findings：

- MiMo P1-01 / P1-03
- DS P0-1 / P1-1
- Codex P0-1

裁决：接受，已直接修复。

结论：

- Host 架构真源必须显式写为 `docs/host/design.md`。
- `docs/design.md` 只承载仓库级跨层设计，不承担 Host phase planning 的架构真源职责。
- `docs/host/implementation-control.md` 中 Host-specific 的裸 `design.md` 引用必须改为 `docs/host/design.md`。

处置：

- 已直接修改 `docs/host/implementation-control.md` 的真源层级、工作流、模板说明、open question 规则和追踪项中的 Host design 引用。

## A2. Phase 0 Engine cleanup 不应阻塞 Phase 1-9

关联 findings：

- DS P0-2
- Codex P1-1
- MiMo Residual Risk R-01

裁决：接受。

结论：

- Engine Context Compaction Event cleanup 是必要前置，但它只阻塞 Phase 10 `Context Governance / Compaction`。
- Phase 1-9 不消费 Engine overflow budget 的准确语义，不应因为用户尚未确认 Engine 修改而被阻塞。
- Phase 0 可以保留为编号 phase / 前置 work unit，但文档必须明确它不是 Phase 1 的默认前置。

建议写回：

- 移除 Phase 1 前置条件中的 `Phase 0 已完成`。
- 在 Phase 0 标题或说明中标注：`仅阻塞 Phase 10，不阻塞 Phase 1-9`。
- 保留 Phase 10 前置条件：Phase 0 已完成，或 Phase 10 plan 明确临时兼容假设并禁止消费 `0/0/0` 作为真实预算。

理由：

- 这能避免把 Engine work 夹带进 Host foundational phases，同时不削弱 Context Governance 的正确性要求。

## A3. Phase 12 不需要依赖 Phase 11 Recovery

关联 findings：

- DS P0-3

裁决：接受。

结论：

- Audit / Tool Trace / Outbox 都是 committed EventLog 的 projection / sink。
- 它们需要 Phase 8 projection core 和 Phase 6 ToolRuntime diagnostic refs。
- 它们不需要 Recovery 已完成；Recovery events 对 sink 来说只是普通 committed events。

建议写回：

- Phase 12 前置条件移除 `Phase 11 recovery 已完成`。
- 若 Phase 12 需要覆盖 recovery event 的 audit / trace / outbox 投影，应通过 synthetic EventLog fixture 或后续 cross-phase integration test 覆盖，而不是把整个 Phase 12 排在 Recovery 后。

理由：

- 这样减少不必要串行依赖，同时保持 sink 不反向影响 Host command path 的边界。

## A4. Recovery 不应依赖 projection checkpoint

关联 findings：

- Codex P1-2

裁决：接受。

结论：

- Recovery 的事实依据是 durable store 中的 Run / Attempt indexes、EventLog、dispatch record 和 host instance liveness record。
- Projection checkpoint 不能成为 Recovery 的前置条件，也不能作为 recovery scan 的输入。

建议写回：

- Phase 11 前置条件移除 `Phase 8 projection checkpoint 已完成`。
- Phase 11 前置条件应明确依赖：
  - Phase 2 durable store / EventLog / host instance liveness foundation。
  - Phase 3 state transition / admission。
  - Phase 5 dispatch record / LocalProxy semantic baseline。
- 将“恢复后 projection 可追平 recovered terminal”放入 Phase 14 或跨 phase integration test，不作为 Recovery entry condition。

理由：

- 这维护了“EventLog / state indexes 是治理真源，projection 只是派生视图”的核心边界。

## A5. 追踪区 owner 必须改成精确 phase 编号或外部 destination

关联 findings：

- Codex P2-1

裁决：接受。

结论：

- `ToolRuntime phase`、`Storage phase`、`Projection / Sink phase`、`Service / UI phase` 这类泛称不能作为可执行 owner。
- 总控文档自己的规则要求 deferred item 必须有明确 owner / destination。

建议写回：

- `ToolRuntime / Tool Schema phase` 改为 `Phase 6. ToolRuntime / Truncation / fetch_more / Duplicate Governance`。
- `RemoteProxy / RemoteStub phase` 改为 `Phase 13. RemoteProxy / RemoteStub`。
- `Public API / Storage phase` 拆成：
  - Phase 4：`purge_session` public signature / request / result / idempotency contract。
  - Phase 14：destructive cleanup / tombstone / delete matrix。
- `Storage phase` 按具体事项拆为：
  - Phase 2：schema convention / payload descriptor / host durable primitive。
  - Phase 14：shared artifact ref check for purge。
- `State machine phase` 改为 `Phase 3. Session / Run / Attempt 状态机与 Admission`。
- `Proxy / Remote phase` 拆为 `Phase 5. Local dispatch` 与 `Phase 13. RemoteProxy / RemoteStub`。
- `Projection / Sink phase` 拆为：
  - Phase 8：projection core / checkpoint / stream / minimal read model。
  - Phase 12：Audit / Tool Trace / Outbox projections。
- `Recovery phase` 改为 `Phase 11. Host Lifecycle / Recovery / Multi-process Hardening`。
- `Service / UI phase` 明确标注为 Host 外部后续 work unit，不属于 Host phase map。

## A6. Phase 2 / Phase 3 / Phase 7 schema ownership 边界

关联 findings：

- DS P1-2
- DS P1-3

裁决：接受。

结论：

- Phase 2 不应模糊地拥有“所有 Host schema”。
- 更清晰的边界是：Phase 2 建立 SQLite / EventLog / transaction / schema convention / foundation tables；后续 phase 在各自 owner 范围内增加对应 durable tables，但必须遵守 Phase 2 的 schema、transaction 和 fresh DB bootstrap 约定。

建议写回：

- Phase 2 scope 明确包括：
  - SQLite connection / transaction runner / WAL / busy timeout。
  - schema bootstrap convention。
  - EventLog table。
  - payload / descriptor tables。
  - idempotency table。
  - host instance liveness foundation。
- Phase 3 scope 明确拥有：
  - Session / Session slot tables。
  - Run / Attempt tables。
  - active index / queue index。
- Phase 7 scope 明确拥有：
  - wait record table / wait adapter durable refs。
- Phase 8 / 9 / 10 / 12 / 14 各自拥有自己的 projection / memory / context / audit / trace / outbox / purge tombstone tables。
- 所有后续 schema 变更按全新 schema 起库处理，不做旧库兼容迁移；但每个 phase 必须使用 Phase 2 建立的 schema convention 和 transaction discipline。

理由：

- 这样避免 Phase 2 做空表或 Phase 3+ 偷改基础 schema，也符合本项目“全新 schema 起库”的约束。

## A7. Phase 10 应显式依赖 Phase 6 ToolRuntime

关联 findings：

- DS P1-4

裁决：接受。

结论：

- Phase 10 在实际 phase ordering 上已经位于 Phase 6 之后，但前置条件应显式列出 Phase 6。
- Context Governance 需要使用已 accepted tool facts、evidence anchors、truncation descriptors 和 tool diagnostic refs 来解释 compact 选择。

建议写回：

- Phase 10 前置条件增加：Phase 6 ToolRuntime / tool fact accept barrier / truncation descriptors 已完成。

边界：

- 这不表示 Context Governance 可以直接写 tool trace 或 ToolRuntime state；它只消费 canonical facts、refs 和 typed provider views。

## A8. Phase 4 read API 与 deferred API contract handoff

关联 findings：

- MiMo P1-02
- MiMo P1-04
- DS P2-3

裁决：接受。

结论：

- Phase 4 不只交付 command path，也应稳定 `get_run`、`get_session`、`stream_run_events` 的 snapshot / stream contract，供 Phase 8 使用。
- Phase 4 定义但不完整实现的 API 必须有明确后续 owner，避免 Phase 7 / Phase 14 改接口。

建议写回：

- Phase 4 后续依赖增加：
  - Phase 8 依赖 Phase 4 的 read API shape 与 snapshot / cursor contract。
  - `resolve_wait` public signature / request envelope 在 Phase 4 稳定，等待结果治理语义在 Phase 7 落地。
  - `purge_session` public signature / `PurgeSessionResult` / idempotency contract 在 Phase 4 稳定，destructive cleanup 在 Phase 14 落地。
- Phase 7 与 Phase 14 进入条件增加：必须复核 Phase 4 已冻结的公共契约；如需变更，先回到 API contract 讨论。

## A9. Phase 0 对应设计章节应补 Engine 文档

关联 findings：

- DS P2-1

裁决：接受。

结论：

- Phase 0 是 Engine contract cleanup work unit，Host design 只解释为什么需要这样做。
- Phase 0 的设计依据应同时引用 Engine README / Engine design。

建议写回：

- Phase 0 对应设计章节增加：
  - `dayu/engine/README.md`
  - `docs/engine/design.md`
  - `docs/host/design.md` §25 / §25.1 作为 Host-side motivation and boundary

约束：

- 因涉及 Engine 代码，Phase 0 仍必须先向用户确认。

## A10. Phase 14 是否必须依赖 Phase 13 Remote

关联 findings：

- DS P2-2

裁决：部分接受。

结论：

- 如果把 Phase 14 定义为整个第一版 Host 的 production hardening / release closeout，那么依赖 Phase 13 Remote 是合理的，因为设计目标包含“支持本地 Engine 和远程 Engine 并列执行”。
- 但 `purge_session` destructive cleanup 本身不依赖 Remote；projection rebuild 也不依赖 Remote。

建议写回：

- 保留 Phase 14 对 Phase 13 的整体前置，用于 final production hardening。
- 在 Phase 14 scope 或建议 slices 中明确：
  - purge / tombstone / projection rebuild slices 不依赖 Remote，可在用户决定时拆成更早的独立 phase。
  - remote smoke / release closeout slice 依赖 Phase 13。

理由：

- 这保持第一版总目标完整，同时不给 purge 子能力制造不必要技术依赖。

## A11. Phase 1 与 Phase 14 scope 较宽

关联 findings：

- MiMo P2-03 / P2-04
- Codex Residual Risk

裁决：接受为风险，不作为当前 phase map blocker。

结论：

- Phase 1 横跨 public typing、runtime infra、ToolsDiscovery、ScenePrepare；Phase 14 横跨 purge、projection rebuild、smoke、docs closeout。
- 总控阶段允许这种 phase 粒度，但进入 phase discussion 时必须进一步按 slice 拆分并确认是否需要拆 phase。

建议写回：

- Phase 1 关键设计问题增加：按 slice 分别确认 public typing、runtime infra、ToolsDiscovery、ScenePrepare；任何一类出现重大架构分歧时拆出独立 phase。
- Phase 14 进入条件增加：先区分 release-blocking 与 follow-up items；如 projection rebuild tooling 或 stress / smoke scope 过大，拆出独立 phase。

## A12. Phase 进入条件的确认形式

关联 findings：

- MiMo P2-02

裁决：接受。

结论：

- “确认...”类进入条件需要说明确认形式，避免 planning agent 自行判断。

建议写回：

- 对 Phase 2、Phase 3、Phase 6 等关键进入条件补充：确认形式为“用户确认，或 `docs/host/design.md` 对应章节已细化到可直接生成 typed contract / schema / test matrix”。

## A13. RunInputBuilder provider protocols 不放 Phase 1

关联 findings：

- MiMo P2-05

裁决：接受为 intentional split，补 tracking。

结论：

- RunInputBuilder typed input provider protocols 属于 Phase 5 执行闭环，不应提前塞进 Phase 1，避免 Phase 1 过大。
- 但 Phase 5 应明确遵守 Phase 1 已建立的公共 typing 风格与 import boundary。

建议写回：

- Phase 1 后续依赖增加：RunInputBuilder typed provider protocols 在 Phase 5 建立，不在 Phase 1 落地；Phase 5 必须保持与 Phase 1 公共类型风格一致。

## A14. Cross-phase recovery + projection rebuild 测试

关联 findings：

- DS P2-4

裁决：接受。

结论：

- crash recovery 后 projection rebuild 是关键跨 phase 场景，不能只分别测试 Recovery 和 Projection。

建议写回：

- Phase 14 验证要求增加：
  - crash after `USER_INPUT_ACCEPTED` + old attempt events
  - recovery scan creates new attempt
  - new attempt reaches terminal
  - projection rebuild from EventLog verifies old attempt facts、new attempt facts、terminal result、outbox/audit/trace projections as applicable

边界：

- 该测试不意味着 Recovery 依赖 Projection；它只验证 projection 后续能从 recovered EventLog 追平。

## A15. Phase 12 后置 Audit / Tool Trace / Outbox 的方向

关联 findings：

- MiMo No Finding
- DS P0-3
- Codex No Finding

裁决：方向保留，去掉错误前置。

结论：

- 把 Audit / Tool Trace / Outbox 从 Projection Core 中拆出来并后置，是正确方向。
- 需要修的是 Phase 12 不应依赖 Recovery 完成，而不是把这些 sinks 放回 Phase 8。

## 必须写回 implementation-control.md 的事项

P0 / P1 级必须先写回：

- A2：Phase 0 只阻塞 Phase 10，不阻塞 Phase 1-9。
- A3：Phase 12 移除 Phase 11 前置。
- A4：Phase 11 移除 Phase 8 projection checkpoint 前置。
- A5：追踪区 owner 改成精确 Phase 编号或 Host 外部 destination。
- A6：Phase 2 / 3 / 7 schema ownership 边界。
- A7：Phase 10 显式依赖 Phase 6。
- A8：Phase 4 read API / deferred API handoff。

P2 / 风险级建议写回：

- A9：Phase 0 补 Engine 文档引用。
- A10：Phase 14 remote dependency 说明按 slice 区分。
- A11：Phase 1 / Phase 14 scope 风险与拆 phase 条件。
- A12：进入条件确认形式。
- A13：RunInputBuilder provider protocols 在 Phase 5 建立。
- A14：cross-phase recovery + projection rebuild test。

## 当前结论

Review gate 当前状态：`fail until fixes are written back`。

原因不是 Host 架构设计本身失败，而是 phase map / implementation-control 中存在会误导后续 planning agent 的前置依赖、owner 和路径问题。路径问题已经直接修复；其余 accepted findings 需要下一步写回 `docs/host/implementation-control.md`。
