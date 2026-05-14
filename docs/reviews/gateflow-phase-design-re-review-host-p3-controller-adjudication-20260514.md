# Host Phase 3 Design Fix Re-Review Controller Adjudication

- **gate name**: Phase 3 design fix re-review / controller adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **review artifacts**:
  - `docs/reviews/gateflow-phase-design-re-review-host-p3-mimo-20260514.md`
  - `docs/reviews/gateflow-phase-design-additional-re-review-host-p3-f1-mimo-20260514.md`
- **source fix artifacts**:
  - `docs/reviews/gateflow-phase-design-fix-host-p3-codex-20260514.md`
  - `docs/reviews/gateflow-phase-design-additional-fix-host-p3-f1-codex-20260514.md`
- **artifact path**: `docs/reviews/gateflow-phase-design-re-review-host-p3-controller-adjudication-20260514.md`

## Review Routing Note

用户已明确：只有 ready-to-create-PR 前的 aggregate review 需要 AgentMiMo 与 AgentDS 同时做；其它 review 默认由 AgentMiMo 一个做即可。AgentDS 的本轮 design fix re-review 已在写 artifact 前被 controller 中断，其未完成输出不作为 gate 输入。

## Finding Decisions

### BQ1

- **source**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md`
- **controller decision**: accepted
- **final status**: fixed
- **evidence**: AgentMiMo re-review 确认 `docs/host/design.md` 与 `docs/host/implementation-control.md` 已明确 Phase 3 创建 minimal dispatch intent / dispatch record row，只写 `pending` / `cancelled`，并把 scheduler、lane、WorkerProxy、Engine dispatch 与 `ATTEMPT_RUNNING` 交给 Phase 5 或后续。

### BQ2

- **source**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md`
- **controller decision**: accepted
- **final status**: fixed
- **evidence**: AgentMiMo re-review 确认 durable state / index contract 已写入设计真源。MiMo 追加提出 F1，要求 partial unique index fallback 条件也写入 `docs/host/design.md`；controller 接受 F1，AgentCodex 已补写，MiMo additional re-review 确认 fixed。

### BQ3

- **source**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md`
- **controller decision**: accepted
- **final status**: fixed
- **evidence**: AgentMiMo re-review 确认 Phase 3 owned transition subset 已写入 `docs/host/design.md`，且 Engine ingest、Tool awaiting、`resolve_wait`、steer、retry / replay、context compaction、recovery scan / dispatch 均标记为 future-owner references。

### F1

- **source**: `docs/reviews/gateflow-phase-design-re-review-host-p3-mimo-20260514.md`
- **controller decision**: accepted
- **final status**: fixed
- **evidence**: `docs/reviews/gateflow-phase-design-additional-re-review-host-p3-f1-mimo-20260514.md` 确认 fallback 条件已写入 `docs/host/design.md`，source review artifact 标题状态已回写为 `已修复`。

## Gate Decision

- **blocking findings**: 0
- **unresolved accepted findings**: 0
- **deferred findings**: 0
- **residual risks**:
  - operation idempotency per-operation scope / digest / result refs 必须在 Phase 3 plan 中具体化，并由 plan review 验证。
  - partial unique index 是当前设计真源的一版选择；若 plan review 或 implementation 发现 SQLite / 测试约束不匹配，必须回到 design discussion。
- **decision**: Phase 3 design discussion / refinement gate passed；允许进入 Phase 3 plan gate。
