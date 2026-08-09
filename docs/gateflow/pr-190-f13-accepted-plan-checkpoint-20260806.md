# PR 190 F13 accepted plan checkpoint

## Gate result

- gate: `accepted plan`
- decision: `pass`
- branch / PR: `codex/interactive-oracle` / existing draft PR 190
- implementation changes: 无
- next entry point: `S0 — 设计真源切到 v4`

## Accepted inputs

- Goal Confirmation：`docs/gateflow/pr-190-f13-evidence-provenance-goal-confirmation-20260806.md`
- implementation plan：`docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`
- first reviews：
  - `docs/reviews/plan-review-20260806-141818.md`
  - `docs/reviews/plan-review-20260806-142113.md`
- Controller adjudication：`docs/gateflow/pr-190-f13-plan-review-adjudication-20260806-142533.md`
- re-reviews：
  - `docs/reviews/plan-review-20260806-142730.md`
  - `docs/reviews/plan-review-20260806-142748.md`
- final narrow fix：`docs/gateflow/pr-190-f13-plan-rereview-fix-20260806-143034.md`
- final reviewer acceptance：
  - `docs/reviews/pr-190-f13-plan-final-rereview-mimo-20260806.md`
  - `docs/reviews/pr-190-f13-plan-final-rereview-ds-20260806.md`

## Decision summary

- fresh compact v4、retain selector、Host atomic previous-fact projection、per-fact non-empty evidence provenance 与 accepted replacement 为冻结方案。
- proposal 只用于模型输出/response identity audit；所有 durable/read-model业务消费者只读accepted replacement。
- request available evidence union 可为 accepted per-fact union 真超集；accepted aggregate 必须 exact 等于逐 fact ordered unique union。
- `PromptLocalProvenanceEntry.canonical_evidence_refs` clean replacement旧singular字段；不建双真源。
- S1保持单一atomic accepted commit，但以C1-C3可追溯、可失效重跑的内部checkpoint控制大diff风险。
- 旧schema workspace只strict fail closed，不新增兼容reader、静默省略或fallback语义。

## Finding state

- unresolved blocking: 0
- unresolved high: 0
- unresolved medium: 0
- unresolved low: 0
- accepted residual risks: fresh schema旧workspace不可读；自然语言entailment不在程序判断范围；真实provider可能repair/fallback；formal replacement scenarios仍unadjudicated。

## Validation

- `git diff --check`: pass
- tests/pyright/CLI: 未运行；accepted plan commit只含治理文档
