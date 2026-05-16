# Host Phase 8 Plan Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：Phase 8 `Projection Core / Host Event Stream / Minimal Read Model` plan review。

Plan artifact：

- `docs/host/phase8-projection-core-event-stream-plan.md`

Review artifacts：

- `docs/reviews/host-phase8-plan-review-mimo-20260516.md`
- `docs/reviews/host-phase8-plan-review-ds-20260516.md`

设计真源：

- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

总控真源：

- `docs/host/implementation-control.md` Phase 8

## Controller Verdict

Plan review gate 暂不进入 accepted plan commit。MiMo 与 DS 均给出 PASS / PASS-with-risks，且没有严重或高严重度 finding；
但若直接进入 implementation，部分中等风险会迫使 implementation agent 临场重新设计 plan 已应固定的 contract。

裁决：进入 Phase 8 plan fix gate。Fix scope 只允许修改 plan artifact，并新增 plan fix artifact；不得修改 production code、
tests、README、design.md 或 implementation-control.md。

## Accepted Findings

### P8-PLAN-F1: Checkpoint advance must be same transaction, no equivalence escape hatch

来源：DS F-1，MiMo P8-PR-003 相关。

裁决：accepted。

修复要求：删除 plan 中“或由实现证明具备等价原子性”的替代路径，明确第一版 checkpoint advance 与对应 projection writes
必须处于同一 `HostTransactionRunner` 管理的 Host durable transaction。Consumer idempotency upsert 只能作为 replay 防御，
不得替代事务原子性。

### P8-PLAN-F2: ProjectionEventFilter must define per-class type semantics

来源：DS F-2。

裁决：accepted。

修复要求：把 `ProjectionEventFilter(event_classes, event_types)` 改为 per-class filter 语义，例如
`ProjectionEventClassFilter(event_class, event_types)` 与 `ProjectionEventFilter(class_filters)`；每个 event class 独立声明
是否消费全部类型或指定类型。Plan 必须要求 filter tests 覆盖多 class + type 组合。

### P8-PLAN-F3: RunResult terminal conflict handling must be explicit

来源：MiMo P8-PR-002。

裁决：accepted。

修复要求：RunResult consumer 必须先按 `run_id` 读取既有 row；不存在时 insert；存在且 `terminal_event_id` /
`terminal_event_sequence` 相同则 duplicate；存在但 terminal identity 不同则 projection failure，checkpoint 不推进。禁止
`INSERT OR REPLACE` 或静默覆盖。

### P8-PLAN-F4: Repair reset and replay must be two-phase, batch-safe

来源：MiMo P8-PR-003，DS F-3。

裁决：accepted。

修复要求：`reset_checkpoint=True` 时，一个短 transaction 只删除 Phase 8 projection rows、minimal read model checkpoint 与
failure row；随后从 cursor 0 按 `batch_size` 分批 replay，每批独立 transaction 推进 checkpoint。中途失败后，下次 repair
从 checkpoint 继续；不得把全量 replay 放进单个长 write transaction。

### P8-PLAN-F5: ProjectionRunner transaction injection and lifecycle must be specified

来源：MiMo P8-PR-001，DS F-4 / Q3。

裁决：accepted。

修复要求：`ProjectionRunner` 构造时接收 `HostTransactionRunner`，由 `HostCommandHandle` 或后续 composition root private
dependency 注入；不得自建 SQLite connection，不得持有 public command facade。Plan 必须明确 Phase 8 自动追平策略：如果
after-commit wakeup 接入本 phase，则只触发 wakeup，不在 terminal transaction 内运行 projection；如果不接入，则必须把
read model 自动追平延迟写为明确 deferred owner，并让 Phase 8 通过 runner / repair primitive 交付可复用基座。

### P8-PLAN-F6: Fanout / wakeup scope and tests must not force dead code

来源：MiMo P8-PR-004，DS F-5。

裁决：accepted。

修复要求：plan 必须把 fanout / wakeup 定义为可选 non-truth optimization；P8-S2 测试命名和成功信号应验证
`stream_run_events` correctness 不依赖 projection、fanout 或 notification side effects，而不是强迫创建 fanout shell。

### P8-PLAN-F7: Schema assumptions need implementation stop checks

来源：DS open questions Q1 / Q2。

裁决：accepted as explicit stop/check requirement。

修复要求：plan 中增加 P8-S1 / P8-S3 stop checks：如果 `event_log(event_sequence)` 无法作为 FK target，implementation
agent 必须在 schema slice 内补齐或改用符合 SQLite 约束的 FK / index 方案，并写测试；如果 `USER_INPUT_ACCEPTED`
payload 没有 typed `display_text`，timeline consumer 不得自行从 raw payload 拼文本，应保留 refs 或写空 display text。

## Rejected Findings

无。

## Deferred Findings

无当前 plan review deferred finding。Fanout 自动追平是否接入本 phase不是强制能力；但 plan fix 必须显式选择并记录 owner，
不能让 implementation agent 自行猜测。

## Plan Fix Scope

允许：

- 修改 `docs/host/phase8-projection-core-event-stream-plan.md`。
- 新增 `docs/reviews/host-phase8-plan-fix-codex-20260516.md`。

禁止：

- 修改 production code、tests、README、`docs/host/design.md`、`docs/host/implementation-control.md`。
- 进入 implementation。
- commit、push 或创建 PR。

## Re-review Requirements

Plan fix 完成后必须由 MiMo 与 DS 双路 re-review，重点确认 P8-PLAN-F1 至 P8-PLAN-F7 均 fixed，且未引入新 scope creep。
