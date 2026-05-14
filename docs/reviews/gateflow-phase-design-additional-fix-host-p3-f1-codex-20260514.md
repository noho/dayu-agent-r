# Host Phase 3 Design Additional Fix

- **work gate name**: fix
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **source review artifact path**: `docs/reviews/gateflow-phase-design-re-review-host-p3-mimo-20260514.md`
- **controller-accepted finding ids**: F1
- **artifact path**: `docs/reviews/gateflow-phase-design-additional-fix-host-p3-f1-codex-20260514.md`

## Fix Status

### F1-Partial unique index fallback 条件未在 design.md 中写明

- **status**: fixed
- **修复内容**: 已在 `docs/host/design.md` §10 Phase 3 durable state / index contract 的 active Run invariant 句后补充 fallback 条件：若后续 implementation 或 review 证明 partial unique index 与 SQLite 或测试约束不匹配，必须回到 design discussion 决策，不得由 implementation agent 自行改为独立 active-run table 或其它 active index 表示。
- **source review artifact 状态回写**: 未修改 source review artifact。当前 handoff 明确要求只修改 `docs/host/design.md` 并追加本 fix artifact；finding 最终标题状态应由后续 re-review gate 回写。

## Changed Files

- `docs/host/design.md`
- `docs/reviews/gateflow-phase-design-additional-fix-host-p3-f1-codex-20260514.md`

## Validation Commands / Results

- `git diff --check`: passed（exit code 0，无输出）。

## New Risks / Open Questions

- **new risks**: 未发现。本次仅补充设计真源中的 fallback 决策边界，不改变 implementation-control、生产代码或测试。
- **open questions**: 无 blocking question。
