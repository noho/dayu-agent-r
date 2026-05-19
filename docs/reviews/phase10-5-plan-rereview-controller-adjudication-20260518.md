# Phase 10.5 Plan Re-Review Controller Adjudication

## Gate

当前 gate：P10.5 plan re-review adjudication。

## Inputs

- Plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Fix report: `docs/reviews/phase10-5-plan-fix-codex-20260518.md`
- MiMo re-review: `docs/reviews/phase10-5-plan-rereview-mimo-20260518.md`
- DS re-review: `docs/reviews/phase10-5-plan-rereview-ds-20260518.md`
- Controller review adjudication: `docs/reviews/phase10-5-plan-review-controller-adjudication-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Verdict

MiMo re-review 与 DS re-review 均为 PASS，blocking count = 0。A1-A5 全部 fixed，且未引入新的 public API、
scope creep、状态机 / schema / 持久化变更，未与 `docs/host/design.md` 或 `docs/host/implementation-control.md` 冲突。

总控裁决：P10.5 handoff implementation-ready plan review / fix / re-review gate 通过，可以创建 accepted plan local commit，并进入
P10.5 implementation Slice 1 handoff。

## Finding Status

| Finding | Controller status | Re-review evidence |
| --- | --- | --- |
| A1. Slice dependency and Slice 2 request-shape boundary | accepted fixed | MiMo 与 DS 均确认 sequencing、Slice 2 current request shape boundary、不得提前实现 steer / retry / replay 已写入 plan。 |
| A2. Public handle session/read wrappers ownership | accepted fixed | MiMo 与 DS 均确认 `ensure_session` / `create_session` / `get_session` / `get_run` public async delegation 归属 Slice 2。 |
| A3. HostEventStream disposition | accepted fixed | MiMo 与 DS 均确认 Slice 4 明确移除 public export；若保留只能是 internal `AsyncIterator[HostEvent]` alias / Protocol。 |
| A4. Compactor baseline None semantics and field mapping | accepted fixed | MiMo 与 DS 均确认 fail-closed 语义、Slice 2 field mapping、S4 owner 包含 Slice 2 wiring。 |
| A5. HostToolingOptions shape note | accepted fixed | MiMo 与 DS 均确认复用 typed shape、缺失 ToolRuntime policy fields 时由 Slice 1 补齐、禁止 extra payload / service locator。 |

## Residual Risks

- R1: S3 real-runner matrix 可能因 provider secret / network 全部 skip。Owner: Slice 6 + Controller。
- R2: S4 real compactor smoke 依赖真实 compactor adapter / provider availability。Owner: Slice 6 + Controller。
- R3: Phase 11 Recovery 后续不得破坏 P10.5 frozen public contract；若必须调整，需回到用户讨论。
- R4: `OpenHostOptions` 字段较多，Slice 1 可在不引入 ConfigLoader / service locator / extra payload 的前提下做 typed defaults 或 helper。

## Next Gate

创建 accepted plan local commit 后，进入 P10.5 implementation Slice 1 handoff。
