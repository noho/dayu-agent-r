# Host Phase 3 Design Fix / Write-back

- **work gate name**: fix
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **source review artifact path**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md`
- **controller adjudication artifact path**: `docs/reviews/gateflow-phase-design-host-p3-controller-adjudication-20260514.md`
- **controller-accepted finding ids**: BQ1, BQ2, BQ3
- **artifact path**: `docs/reviews/gateflow-phase-design-fix-host-p3-codex-20260514.md`

## Fix Summary

本次 fix 只做 Phase 3 design fix / write-back，不进入 plan gate，不修改生产代码、测试、README，不创建 commit / push / PR。

## Per-finding Fix Status

### BQ1: Phase 3 是否创建最小 dispatch intent / dispatch record durable row？

- **fix status**: fixed
- **写回位置**:
  - `docs/host/design.md` §9.1：Phase 3 owned transition subset 明确 queue promotion 创建 Attempt `STARTING` 与 dispatch record `pending`，cancel pre-dispatch starting 将 dispatch record 标记为 `cancelled`。
  - `docs/host/design.md` §10：Phase 3 durable state / index contract 明确 minimal dispatch record row 属于 Attempt startup truth，`ATTEMPT_STARTED` 要求 Attempt `STARTING` 与 dispatch record `pending` 同事务创建；Phase 3 只写 `pending` / `cancelled`。
  - `docs/host/implementation-control.md` Phase 3 条目与追踪区：明确 scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy、Engine dispatch、`dispatching` 与 `ATTEMPT_RUNNING` 属于 Phase 5 或后续。

### BQ2: Phase 3 的 state index / CAS / idempotency 最小 contract 是否需要在 design.md 中补齐？

- **fix status**: fixed
- **写回位置**:
  - `docs/host/design.md` §10：补充 Session / Session slot / Run / Attempt / minimal dispatch record row contract。
  - `docs/host/design.md` §10：明确 active Run invariant 第一版优先 SQLite partial unique index on active Run statuses。
  - `docs/host/design.md` §10：明确 queue FIFO by accepted `event_sequence`、CAS preconditions、`rowcount=0` loser handling、operation idempotency scope / digest / result refs 必须在实现前按 operation 固定。
  - `docs/host/implementation-control.md` Phase 3 条目与追踪区：把 durable state / index / CAS / idempotency contract 列为 plan gate 前必须满足的设计边界。

### BQ3: Phase 3 plan 是否只覆盖 Phase 3 transition subset，并把跨 phase matrix 行标记为 future-owner？

- **fix status**: fixed
- **写回位置**:
  - `docs/host/design.md` §9.1：新增 Phase 3 owned transition subset，只包含 Session lifecycle、start / follow-up admission、queue promotion、cancel queued、cancel pre-dispatch starting、internal terminal closeout helper、terminal / cancel 后 promotion trigger。
  - `docs/host/design.md` §9.1：明确 Engine final answer / failure ingest、Tool awaiting、`resolve_wait`、steer、retry / replay、context compaction、recovery scan / dispatch 是 future-owner references。
  - `docs/host/implementation-control.md` Phase 3 条目：更新范围、不做、关键设计问题、验证要求与退出条件，避免后续 plan agent 越界进入 Phase 5 / 7 / 10 / 11。

## Changed Files

- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-fix-host-p3-codex-20260514.md`

## Validation Commands / Results

- not run: 本次只修改设计文档与 review artifact，未修改生产代码或测试；按 handoff 约束不运行实现测试或 pyright。

## New Risks / Open Questions

- 未发现新的 blocking question。
- `operation idempotency scope_kind / scope_id / semantic digest / result refs` 已被固定为 plan gate 前必须收敛的 contract 项，但本 fix 未替每个 operation 填具体命名；该细化应在 Phase 3 plan 生成前或 plan 中按 operation 写清，并由 plan review 验证。
- active Run partial unique index 是 controller-confirmed 第一版 preference；若后续实现或 review 证明与 SQLite / 测试约束不匹配，必须回到 design discussion，不能由 implementation agent 直接改成独立 active-run table。

## Residual Risk Classification

- **design re-review required**: 需要 Phase 3 design fix re-review 确认 BQ1 / BQ2 / BQ3 已充分写回，且没有引入新的架构越界。
- **later phase owner**: scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy、Engine dispatch、dispatch record `dispatching` 与 `ATTEMPT_RUNNING` 归 Phase 5 或后续。
- **later phase owner**: recovery scan、positive orphan proof、RECOVERING dispatch 与 recovery multi-process hardening 归 Phase 11。
- **later phase owner**: Tool awaiting / `resolve_wait` 归 Phase 7；steer、retry / replay、context compaction 归对应后续 phase plan。
