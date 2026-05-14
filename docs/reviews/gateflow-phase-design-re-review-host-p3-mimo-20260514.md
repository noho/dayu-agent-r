# Host Phase 3 Design Fix Re-Review

- **review gate name**: Phase 3 design fix re-review
- **reviewed target**:
  - `docs/reviews/gateflow-phase-design-fix-host-p3-codex-20260514.md`
  - `docs/host/design.md`（BQ1 / BQ2 / BQ3 写回区域）
  - `docs/host/implementation-control.md`（Phase 3 条目与追踪区）
- **reviewer**: AgentMiMo
- **artifact path**: `docs/reviews/gateflow-phase-design-re-review-host-p3-mimo-20260514.md`
- **conclusion**: 基本通过；BQ1 / BQ2 / BQ3 已充分写回，有一个低严重程度 finding 需要确认。

## BQ Fix Mapping

### BQ1: Phase 3 是否创建最小 dispatch intent / dispatch record durable row？

- **fix status**: fixed
- **验证证据**:
  - `docs/host/design.md` §9.1（行 540-552）Phase 3 owned transition subset 明确 queue promotion 创建 Attempt `STARTING` 与 dispatch record `pending`，cancel pre-dispatch starting 将 dispatch record 标记为 `cancelled`。
  - `docs/host/design.md` §10（行 671）Phase 3 durable state / index contract 明确 minimal dispatch record row 属于 Attempt startup truth，`ATTEMPT_STARTED` 要求 Attempt `STARTING` 与 dispatch record `pending` 同事务创建；Phase 3 只写 `pending` / `cancelled`。
  - `docs/host/implementation-control.md`（行 445-446、455）禁止 scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy、Engine dispatch、`dispatching` 与 `ATTEMPT_RUNNING`。
- **写回忠实度**: 忠实于 controller 裁决。Phase 3 创建 minimal dispatch intent，只写 `pending` / `cancelled`，不实现 scheduler / lane / WorkerProxy / Engine。

### BQ2: Phase 3 的 state index / CAS / idempotency 最小 contract 是否需要在 design.md 中补齐？

- **fix status**: fixed（有一个低严重程度收尾项）
- **验证证据**:
  - `docs/host/design.md` §10（行 662-673）Phase 3 durable state / index contract 覆盖：Session row、Session slot unique `(scope, slot_key)`、active Run partial unique index、Run row、queue FIFO by `event_sequence`、Attempt row、minimal dispatch record row、CAS preconditions `rowcount=0` loser handling、operation idempotency scope / digest / result refs 规则。
  - `docs/host/implementation-control.md`（行 456）确认 active Run invariant 第一版优先采用 SQLite partial unique index on active Run statuses。
  - `docs/host/implementation-control.md`（行 458）确认 operation idempotency scope / digest / result ref 必须在 plan gate 前按 operation 固定。
  - `docs/host/implementation-control.md`（行 475）multi-process test matrix 覆盖 controller 裁决要求的所有场景。
- **写回忠实度**: 忠实于 controller 裁决。durable state / index contract 已写入设计真源；CAS preconditions 规则、queue FIFO ordering、active Run invariant 均已明确。operation idempotency per-operation scope / digest 细化正确标记为 plan gate 前必须收敛的 contract 项，由 plan agent 按 operation 填写。
- **收尾项**: partial unique index fallback 条件未在 design.md 中写明（见 Finding F1）。

### BQ3: Phase 3 plan 是否只覆盖 Phase 3 transition subset，并把跨 phase matrix 行标记为 future-owner？

- **fix status**: fixed
- **验证证据**:
  - `docs/host/design.md` §9.1（行 540-552）新增 Phase 3 owned transition subset，只包含 Session lifecycle、start / follow-up admission、queue promotion、cancel queued、cancel pre-dispatch starting、internal terminal closeout helper、terminal / cancel 后 promotion trigger。
  - `docs/host/design.md` §9.1（行 552）明确 Engine final answer / failure ingest、Tool awaiting、`resolve_wait`、steer、retry / replay、context compaction、recovery scan / dispatch 是 future-owner references。
  - `docs/host/implementation-control.md`（行 447-452）Phase 3 不做列表排除了 EngineEvent ingest、Tool awaiting、`resolve_wait`、steer、retry / replay、context compaction、recovery scan。
  - `docs/host/implementation-control.md`（行 484-485）后续依赖明确 Phase 5 owns scheduler / lane / WorkerProxy / LocalProxy / Engine dispatch / `dispatching` / `ATTEMPT_RUNNING`，Phase 11 owns recovery scan / positive orphan proof / RECOVERING dispatch。
- **写回忠实度**: 忠实于 controller 裁决。Phase 3 只实现 owned transition subset；跨 phase 行标记为 future-owner references；implementation-control 的不做和后续依赖追踪正确分配了后续 phase owner。

## Findings

### F1-已修复-低-Partial unique index fallback 条件未在 design.md 中写明

- **Plan位置**: `docs/host/design.md` §10 Phase 3 durable state / index contract（行 668）
- **问题类型**: 契约缺失
- **计划当前写法**: design.md §10 写道"active Run invariant 第一版优先采用 SQLite partial unique index on active Run statuses"；fix artifact（行 55）写道"若后续实现或 review 证明与 SQLite / 测试约束不匹配，必须回到 design discussion，不能由 implementation agent 直接改成独立 active-run table"。
- **为什么有问题**: controller 裁决明确要求 partial unique index 不可行时必须回到 design discussion，不能由 implementation agent 自行决定。该 fallback 条件是 active index contract 的一部分，应写入设计真源，而非只在 fix artifact 中。
- **直接证据**: controller adjudication（行 24）写道"若实现或 review 证明 SQLite partial unique index 与当前测试/portable schema 不匹配，再回到 design discussion"；fix artifact（行 55）也记录了该条件；但 design.md §10（行 668）只有正向描述，没有 fallback 条件。
- **影响**: 低。fix artifact 和 implementation-control.md 均已记录该条件；implementation-control.md 的追踪区（行 1289）也要求 re-review 确认。设计真源缺失该条件的实际风险是 plan agent 或 implementation agent 可能只读 design.md 而错过 fallback 约束。
- **建议改法和验证点**: 在 `docs/host/design.md` §10 的 active Run invariant 句后补充："若实现或 review 证明 partial unique index 与 SQLite 或测试约束不匹配，必须回到 design discussion 决策，不得由 implementation agent 自行改为独立 active-run table。"验证点：读 design.md §10 确认 fallback 条件已存在。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

## Open Questions / Residual Risk

1. **operation idempotency per-operation scope / digest 细化**: design.md 正确标记为 plan gate 前必须收敛的 contract 项。该项不是 design-level 缺口，而是 plan-time 细化工作，由 plan agent 按 operation 填写，plan review 验证。不阻塞 re-review。
2. **partial unique index 与 SQLite / 测试约束兼容性**: 当前选择是 controller-confirmed 第一版 preference。兼容性在 implementation 和 plan review 中验证。fallback 条件记录在 fix artifact 中（待写入 design.md，见 F1）。
3. **`waiting_for_lane` 出现在 transition matrix 但 Phase 3 不实现**: 设计 §9.1 cancel pre-dispatch starting 行描述 `dispatch record pending / waiting_for_lane`；Phase 3 只写 `pending` / `cancelled`，`waiting_for_lane` 是 schema enum 预留，Phase 5 才使用。这不是冲突，只是 schema 覆盖范围大于 Phase 3 实施范围。

## Re-Review Gate Decision

- **BQ1**: fixed
- **BQ2**: fixed（F1 为低严重程度收尾项）
- **BQ3**: fixed
- **new blocker**: 0（F1 为低严重程度，不阻塞 plan gate）
- **建议**: BQ1 / BQ2 / BQ3 已充分写回，写回内容忠实于 controller 裁决。F1 是低严重程度的文档补全项，可在 plan gate 前或 plan 中补入 design.md。建议进入 Phase 3 plan gate。
