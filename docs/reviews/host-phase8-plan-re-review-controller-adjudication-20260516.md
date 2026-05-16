# Host Phase 8 Plan Re-review Controller Adjudication - 2026-05-16

## Gate

当前 gate：Phase 8 plan re-review after accepted plan fix。

Plan artifact：

- `docs/host/phase8-projection-core-event-stream-plan.md`

Fix artifact：

- `docs/reviews/host-phase8-plan-fix-codex-20260516.md`

Re-review artifacts：

- `docs/reviews/host-phase8-plan-re-review-mimo-20260516.md`
- `docs/reviews/host-phase8-plan-re-review-ds-20260516.md`

Controller plan review adjudication：

- `docs/reviews/host-phase8-plan-review-controller-adjudication-20260516.md`

## Controller Verdict

PASS。Phase 8 plan fix 已通过双路 re-review，可以进入 accepted plan commit gate；accepted checkpoint commit 后进入 P8-S1
`Projection Runner / Checkpoint / Typed Consumer Contracts` implementation gate。

## Accepted Finding Verification

| Finding | Controller judgment | Evidence |
| --- | --- | --- |
| P8-PLAN-F1 checkpoint 同事务 | fixed | MiMo 与 DS 均确认 plan 已删除“等价原子性”逃生路径，并要求 checkpoint 与 projection writes 在同一 `HostTransactionRunner.run_write()` transaction 内提交。 |
| P8-PLAN-F2 per-class filter | fixed | Plan 已使用 `ProjectionEventClassFilter` + `ProjectionEventFilter(class_filters)` 固定 per-class 语义，并要求多 class + type 组合测试。 |
| P8-PLAN-F3 RunResult 冲突检测 | fixed | Plan 已明确 SELECT-by-`run_id`、匹配则 duplicate、不匹配则 projection failure 且 checkpoint 不推进；禁止 `INSERT OR REPLACE` 和静默 overwrite。 |
| P8-PLAN-F4 repair 两阶段分批 | fixed | Plan 已明确 reset 短事务与 replay batch transaction 分离，失败后从最后成功 checkpoint 继续。 |
| P8-PLAN-F5 runner 注入与生命周期 | fixed | Plan 已要求 `ProjectionRunner` 构造注入 `HostTransactionRunner`，不得自建 connection 或持有 public command facade；Phase 8 自动追平明确 deferred 给 Phase 9 owner。 |
| P8-PLAN-F6 fanout / wakeup non-truth | fixed | Plan 已明确不强制创建 fanout shell，P8-S2 只验证 `stream_run_events` 不依赖 projection / notification side effects。 |
| P8-PLAN-F7 schema / payload stop checks | fixed | Plan 已增加 `event_log(event_sequence)` FK target stop check 与 `USER_INPUT_ACCEPTED.display_text` payload stop check。 |

## New Finding Judgment

MiMo 与 DS 均未提出新的 blocking finding。Fix 未扩展 Phase 8 scope，没有引入 Engine、Service、UI、Fins、runtime、Audit /
Tool Trace / Outbox concrete sink 或 command path state-machine 变更。

## Residual Risks And Owners

- Phase 8 implementation owner：按 plan 验证 SQLite FK target、typed payload、per-class filter、repair batch、projection import boundary。
- Phase 9 owner：automatic after-commit projection catch-up / composition wiring。
- Phase 13 owner：Audit、Tool Trace、Outbox concrete sinks。
- Phase 15 owner：production admin rebuild tooling、large projection hardening、purge matrix。

上述 residual risks 都已有 owner，不阻塞 accepted plan commit。

## Validation

本 gate 只新增 / 修改 plan 与 review artifacts，未修改 production code 或 tests。Plan fix 已由 AgentCodex 执行
`git diff --check -- docs/host/phase8-projection-core-event-stream-plan.md docs/reviews/host-phase8-plan-fix-codex-20260516.md`
并通过。Accepted plan commit 前 controller 仍需运行整体 `git diff --check`。
