# Gateflow Plan Fix — Host Phase 0 / P0 Engine Context Compaction

- Work gate name: `fix`
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Fixed plan path: `docs/host/phase0-engine-context-compaction-plan.md`
- Source review artifacts:
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-mimo-20260513.md`
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-ds-20260513.md`
- Controller adjudication:
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-controller-adjudication-20260513.md`
- Artifact path:
  - `docs/reviews/gateflow-plan-fix-host-p0-engine-context-compaction-20260513.md`

## Scope

本次 fix 只处理 controller adjudication 中 accepted findings A1-A7。未处理 deferred finding D1，未扩大 scope，未修改生产代码、测试、README、design docs 或 implementation-control。

Changed files:

- `docs/host/phase0-engine-context-compaction-plan.md`
- `docs/reviews/gateflow-plan-fix-host-p0-engine-context-compaction-20260513.md`

## Finding Fix Status

| Finding | Status | Fix summary |
| --- | --- | --- |
| A1 | fixed | 将 Runner HTTP context overflow event-path 测试从条件项改为 P0-S1 必做项，并写入 allowed files、exact changes、tests、expected assertions 与 validation commands。 |
| A2 | fixed | P0-S1 completion signal 明确要求 `source .venv/bin/activate && pyright` 通过。 |
| A3 | fixed | residual risk destination 拆分为 Phase 5 ingest validation 与 Phase 10 Context Governance semantic interpretation，并要求 P0 closeout 回写 implementation-control 追踪区。 |
| A4 | fixed | sentinel 检查扩展为 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0`、`0/0/0`、`占位快照`，并要求 implementation report 说明多行构造检查结果。 |
| A5 | fixed | P0-S1 contract tests 同时要求覆盖 `budget_state=None` 合法与 `ContextBudgetSnapshot(1000, 500, 1500)` 真实 snapshot 合法，并说明不类型级禁止零值。 |
| A6 | fixed | P0-S2 将 `dayu/engine/contracts/runner_events.py` 列为 docstring 可选检查文件；无需修改时 artifact 必须记录 `checked, no change needed`。 |
| A7 | fixed | 将 `dayu/README.md` 操作改为精化已有 Context Governance 术语条目，避免冗余，不把未来 Phase 10 写成已完成。 |

## Validation

未运行测试或 pyright，因为本 gate 只修改 plan artifact 与 fix artifact，不改生产代码或测试代码。

Artifact self-check:

- 已读取 controller adjudication，并逐项写回 A1-A7。
- 已用 `rg -n "test_http_error_event|pyright|Phase 5|Phase 10|ContextBudgetSnapshot\\(1000|prompt_tokens=0|runner_events.py|精化|checked, no change needed|多行构造|unknown-budget sentinel" docs/host/phase0-engine-context-compaction-plan.md` 检查关键修订点均存在。
- 未修改 source review artifacts，未更新 finding 标题状态词；这些 review artifact 是输入证据，本次 handoff 仅要求写 plan fix artifact。

## New Risks Or Open Questions

无新增 blocking question。

无新增 plan deviation。修订仍保持原 scope：Engine contract cleanup 支撑 `docs/host/design.md` §25 / §25.1 的 Host Context Governance 语义，不夹带 Host implementation code、Engine proactive governance、compact / retry / tokenizer / policy。

## Residual Risk Classification

- D1 reason 字符串自由度：未处理，保持 controller adjudication 的 `deferred-with-owner`，归属 Host Phase 5 EngineEvent ingest mapping 与 Phase 10 Context Governance ingest semantics。
- `budget_state=None` 的 Host 侧责任切分：已在 plan 中分类为 Phase 5 ingest validation 与 Phase 10 semantic interpretation，并要求 P0 closeout 回写 `docs/host/implementation-control.md` 追踪区。
- provider-specific tokenizer adapter：仍 deferred to Host later capability，不进入 P0 或第一版 Phase 10。

## Completion Signal

A1-A7 均已写回 plan。当前 plan 可进入 plan re-review。

