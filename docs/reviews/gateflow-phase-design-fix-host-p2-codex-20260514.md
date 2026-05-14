# Host Phase 2 Phase Design Fix Artifact

## Work Gate Name

phase design fix

## Source Artifact

- `docs/reviews/gateflow-phase-design-host-p2-codex-20260514.md`

## Controller-Accepted Blocking Questions

- BQ1: SQLite schema convention / fresh DB bootstrap 仍未收敛。
- BQ2: Transaction runner、WAL / busy timeout、retry policy 和错误分类未形成 typed contract。
- BQ3: EventLog row typed contract 与 idempotency primitive 的唯一约束不够具体。
- BQ4: Payload threshold、descriptor shape、artifact 目录注入与外移失败顺序未收敛。
- BQ5: Host instance liveness foundation 的最小边界需要裁决。

## Fix Status

- **BQ1 fixed**: `docs/host/design.md` 已补充 SQLite schema convention：single Host SQLite durable DB、fresh bootstrap、`PRAGMA user_version`、TEXT durable ids、canonical JSON TEXT、显式 unique indexes / primary keys、foreign keys on、无旧库兼容读取 / 迁移 / fallback。`docs/host/implementation-control.md` 已同步为 Phase 2 已确认 durable foundation 决策。
- **BQ2 fixed**: `docs/host/design.md` 已补充 transaction runner 语义：短 write transaction、`BEGIN IMMEDIATE`、WAL、busy timeout、`foreign_keys=ON`、busy / locked 有限 retry、唯一约束冲突等非 busy 错误不 retry、after-commit 只在 commit 成功后触发。`docs/host/implementation-control.md` 已同步追踪项，要求 plan 转成 typed API、schema、错误类型和测试断言。
- **BQ3 fixed**: `docs/host/design.md` 已补充 EventLog / idempotency contract：全局 INTEGER `event_sequence` cursor、TEXT `event_id` 全局唯一、所有 event class 都有 ledger identity、EventLog schema 必须显式约束关键字段、idempotency 以 `(scope_kind, scope_id, idempotency_key)` 绑定 `semantic_input_digest` 与 result ref，同 key 不同 digest 返回 `idempotency_conflict`。
- **BQ4 fixed**: `docs/host/design.md` 已补充 payload foundation：Phase 2 支持 `sqlite_payload` 与本地 `artifact_ref` 最小 descriptor；composition root 注入 `payload_inline_threshold_bytes` 与 artifact root；大 payload 先 durable 写入、digest verify、atomic rename，再写 SQLite descriptor + EventLog；SQLite 失败后的 orphan artifact 只作为 cleanup / diagnostic 处理，不作为 accepted fact。
- **BQ5 fixed**: `docs/host/design.md` 已补充 host instance liveness 最小边界：Phase 2 只提供 register / heartbeat / stopping / stopped / read row primitive；host instance row 最小字段已写明；不实现 positive orphan proof classifier，不读取 dispatch record，不引入 lease / fencing / Attempt takeover。`docs/host/implementation-control.md` 已同步该边界。

## Changed Files

- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-fix-host-p2-codex-20260514.md`

## Validation Status

- 本次是设计真源与总控状态同步，未修改生产代码、测试或 README。
- 未运行测试：无代码行为变更。
- 未运行 pyright：无 Python 代码变更。

## Residual Risks

- Phase 2 handoff-ready plan 仍需把这些设计决策细化为具体 file ownership、typed classes / functions、schema DDL、错误类型、multi-process test matrix 和 validation commands。
- Payload artifact 写入与 SQLite transaction 之间仍存在文件系统 / SQLite 非同事务的 orphan artifact cleanup 风险；该风险已在设计中归为 cleanup / diagnostics，不得影响 accepted fact。
- Host instance liveness foundation 仍不能被误用为 lease / fencing。positive orphan proof、Attempt `LOST`、Run `RECOVERING` 和新 Attempt 创建必须留给后续 recovery / state machine phase。
- Phase 2 plan review 应重点复核 implementation slices 是否严格停留在 durable foundation，不夹带 Session / Run / Attempt 状态机、Host command path、Engine dispatch、Projection、Memory、ToolRuntime 或 Remote transport。

## Artifact Path

`docs/reviews/gateflow-phase-design-fix-host-p2-codex-20260514.md`
