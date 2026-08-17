# UF-FIX01 fiscal-period prevalidation residual — Plan Review Fix

## Gate 元数据

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- gate：`fix`
- 日期：2026-08-18
- plan：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-plan-20260817.md`
- adjudication：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-plan-review-adjudication-20260818.md`
- changed files：本 plan 与本 fix artifact
- current gate：`re-review`
- next entry point：`re-review`
- completion status：`fix-complete`
- artifact path：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-plan-review-fix-20260818.md`

## Finding fixes

- M-001：`已修复`。`derive_report_kind` 改为消费非 optional `FiscalPeriod`，不调用 optional normalizer。
- M-002：`已修复`。类型收窄贯穿 validated/static request、derive helper 与两个 upload ID builders。
- M-003：`已修复`。计划要求删除 upload ID builders 内 strip/uppercase，lower consumer 不重做 owner 语义。
- M-004：`已修复`。计划加入 exact try/except、通用 usage mapping 与 impossible-None invariant。
- M-005：`已修复`。计划显式列出 closed enum/value/message 和旧名称全仓扫描。
- D-F1：`已修复`。现有 CLI UF-024 exact reason 移入 S1 allowed files/validation，S1 不保留已知红。
- D-F2：`已修复`。禁止修改 `filing_semantics.py` production，coverage exact include 固定为三个实际 production files。
- D-F3：`已修复`。S2 纳入 `upload_tools.py` 与 schema exact test，LLM-facing description 自足列全六值。

## Validation

- `git diff --check`：由 controller 在 re-review 前执行。
- 本 gate 只修改 plan artifacts，未运行产品测试；baseline test/coverage/pyright evidence 已记录在两份 plan review。

## Docs decision

本 fix 只修改 Gateflow artifacts。产品 README 的触发与职责决定仍由 S2 实施，未提前改写当前行为文档。

## Residual risks

- 真实 calibration、冻结 evidence/oracle/scenario：`assigned to later work unit`。
- material optional fiscal metadata：`assigned to later work unit`。
- download aliases：`rejected-with-reason`，独立 owner。
- 旧 durable 非法 period：`assigned to later work unit`。
- AgentCodex plan/fix pane 可复现无产出停滞：workflow execution risk；controller 机械落盘，必须由两路 re-review 复核。

## Completion status

全部 accepted plan-review findings 已按 adjudication 写回 plan；无 blocking open question，进入两路 re-review。
