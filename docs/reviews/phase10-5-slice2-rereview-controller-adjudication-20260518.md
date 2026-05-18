# P10.5 Slice 2 Re-Review Controller Adjudication

## Gate

当前 gate：P10.5 Slice 2 re-review adjudication。

## Inputs

- Fix artifact: `docs/reviews/phase10-5-slice2-fix-codex-20260518.md`
- MiMo re-review: `docs/reviews/phase10-5-slice2-rereview-mimo-20260518.md`
- DS re-review: `docs/reviews/phase10-5-slice2-rereview-ds-20260518.md`
- Controller code review adjudication: `docs/reviews/phase10-5-slice2-code-review-controller-adjudication-20260518.md`
- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`

## Verdict

MiMo 与 DS re-review 均为 PASS，blocking count = 0。F1 / F2 均已 fixed，且 fix 未引入新的 public API、schema /
state-machine / Engine 变更，也未越界到 Slice 3 / 4 / 5。

总控裁决：P10.5 Slice 2 implementation / review / fix / re-review gate 通过，可以创建 accepted Slice 2 local commit，并进入
P10.5 implementation Slice 3 handoff。

## Finding Status

| Finding | Controller status | Evidence |
| --- | --- | --- |
| F1. `_PublicHostHandle.close()` durable cleanup after scheduler close failure | accepted fixed | 两份 re-review 均确认 nested `try/finally` 保证 scheduler close 抛错后仍尝试 projection catch-up 与 `command_handle.close()`，并保持 closed gate / 幂等 / 不写 terminal facts。 |
| F2. `context_budget_policy=None` fallback explicitness | accepted fixed | 两份 re-review 均确认 fallback 已收口到 `_INTERNAL_COMMAND_FALLBACK_*` constants、私有 helper 与 docstring，且不改变 public API、不从 Engine / extra payload / profile lookup 推导预算。 |

## Residual Risks

- `watch_session_events(...)` 仍为 Slice 4 placeholder。
- `SubmitFollowupRequest` typed fields、per-run effective config / tool-set freeze 仍属 Slice 3。
- Steer / retry / replay / WAITING public resume 仍属 Slice 5。
- 如果 scheduler close 与后续 cleanup 同时抛错，后抛出的 cleanup exception 可能覆盖先前异常；当前 fix 只保证后续 cleanup 被尝试，不引入异常聚合机制。

## Next Gate

创建 accepted Slice 2 local commit，记录 commit hash 到 `docs/host/implementation-control.md`，进入 P10.5 implementation Slice 3 handoff。
