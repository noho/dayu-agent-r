# P8.5 Plan Amendment Report

> **Superseded / historical artifact.** This amendment belonged to accepted plan
> commit `1aad621762765d27c5cd161836f062b1ed906995`. The controller later declared
> P8.5 Slice 1 implementation failed, reverted the slice outputs, and reset P8.5
> back to plan gate. Current planning truth is `docs/host/phase8.5-plan.md`,
> `docs/host/phase8.5-plan-review.md`,
> `docs/host/phase8.5-plan-fix-report.md`,
> `docs/host/phase8.5-plan-rereview.md`, and the later manual-review amendment
> artifacts. Keep this file only as audit history.

- **amendment gate name**: plan amendment
- **plan target**: `docs/host/phase8.5-plan.md`
- **previous review artifacts**:
  - `docs/host/phase8.5-plan-review.md`
  - `docs/host/phase8.5-plan-fix-report.md`
  - `docs/host/phase8.5-plan-rereview.md`
- **artifact path**: `docs/host/phase8.5-plan-amendment-report.md`

## Reason For Amendment

Controller 裁决原 Slice 1 和 Slice 2 必须合并。该原因成立：单独删除 `TOOL_FETCH_MORE_*` / `ToolFetchMore*Data` 会立即打断 `_tool_runtime.py`、serializer、memory projection、tool trace projection 和相关测试。为了让这种中间态可运行，implementation agent 很可能被诱导添加临时兼容代码或桥接逻辑，这与 P8.5 不写兼容层的约束以及每个 implementation slice 完成后系统应可运行的 Gateflow 要求冲突。

## Changed Sections

- `## 8. Implementation Slices`
  - 将原 Slice 1 和 Slice 2 替换为 `Slice 1 — ToolRuntime generic fetch_more event model`。
  - 顺延后续 slice 编号。
  - 更新 implementation prompt、前置依赖、禁止范围和验收条件。
- `## 9. Review Gates`
  - 明确 Contract gate、ToolRuntime gate 和 Projection gate 都属于 Slice 1 review 项，必须一起验证。
- `## 10. Validation Commands`
  - 明确 Slice 1 validation 必须同时运行 contract、serializer、ToolRuntime、memory projection、tool trace projection 和 public surface 测试。
- `## 11. Residual Risk Owner Changes`
  - 将 `fetch_more concrete RunEventType` 的关闭 owner 从 `Slice 1-2` 改为 `Slice 1`。
  - 将 attempt lease residual owner 从 `Slice 7a/7b` 改为 `Slice 6a/6b`。
- `## 2. Authoritative Decisions`
  - 保持所有 P8.5 核心契约裁决不变。

## Changed Slice List

| Amendment 前 | Amendment 后 |
| --- | --- |
| Slice 1 — Remove fetch_more-specific RunEvent contract | Slice 1 — ToolRuntime generic fetch_more event model |
| Slice 2 — Model fetch_more through generic tool-call facts | 并入 Slice 1 |
| Slice 3 — Durable memory repair stabilization | Slice 2 — Durable memory repair stabilization |
| Slice 4 — Tool trace observer I/O boundary | Slice 3 — Tool trace observer I/O boundary |
| Slice 5 — Compact / RunInput payload / semantic cleanup | Slice 4 — Compact / RunInput payload / semantic cleanup |
| Slice 6 — SSE partial tool-call trace diagnostic | Slice 5 — SSE partial tool-call trace diagnostic |
| Slice 7a — Attempt lease contract hardening | Slice 6a — Attempt lease contract hardening |
| Slice 7b — Attempt adversarial coverage | Slice 6b — Attempt adversarial coverage |
| Slice 8 — Docs, migration notes, final validation | Slice 7 — Docs, migration notes, final validation |

## New Risks / Open Questions

- New risk introduced: none.
- New open question introduced: none.
- Blocking open question remaining: none.

## Validation

本轮只修改 plan 文档和 amendment report，未修改生产代码或测试代码。未运行 pytest 或 pyright；documentation-only amendment 不需要执行代码验证。

## Completion Signal

plan 现在把 ToolRuntime `fetch_more` event-model correction 表达为单个纵向 contract migration slice。本次 amendment 不改变已通过 re-review 的 P8.5 核心契约裁决，不恢复 legacy public `fetch_more` handle，也不引入 compatibility reader / wrapper / re-export 范围。
