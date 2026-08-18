# UF-FIX03 accepted plan

## Decision

- work unit：`UF-FIX03 summary-and-bounded-errors`
- plan：`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
- decision：`PASS — accepted for implementation`
- next entry：`implementation S1`

## Review chain

- 首轮 AgentMiMo：`docs/reviews/plan-review-20260813-203415.md`
- 首轮 AgentDS：`docs/reviews/plan-review-20260813-203826.md`
- controller adjudication：`docs/gateflow/uf-fix03-plan-review-adjudication-20260813.md`
- AgentCodex fix：`docs/gateflow/uf-fix03-plan-review-fix-20260813.md`
- 全量 re-review AgentMiMo：`docs/reviews/plan-review-20260813-210131.md`（pass）
- 全量 re-review AgentDS：`docs/reviews/plan-review-20260813-210506.md`（pass with N1–N3 low findings）
- N1–N3 adjudication：`docs/gateflow/uf-fix03-plan-rereview-adjudication-20260813.md`
- AgentCodex N1–N3 fix：`docs/gateflow/uf-fix03-plan-rereview-fix-20260813.md`
- 定向 re-review AgentMiMo：`docs/reviews/plan-review-20260813-211608.md`（pass）
- 定向 re-review AgentDS：`docs/reviews/plan-review-20260813-211627.md`（pass）

## Accepted implementation contract

- requested count 来自 validated request；stored count 来自成功 commit 的 original publication。
- pipeline 与 summary constructor owner 各自校验完整状态矩阵，包含 `cancelled -> stored 0`。
- filing empty/corrupt/mixed 在 publication 前 typed fail-fast；material 只迁移 shared count。
- failure reason 是 stable closed owner；public label 由 direct events 唯一 canonicalize/validate，合法超长 basename 使用固定隐藏标签。
- CLI/runtime/durable/direct 只消费 typed projection；direct boundary 不创建 Host/Engine/legacy job artifact。
- 不执行 UF-PF03，不修改冻结 JSON/evidence，不创建 PR。

## Residual risk routing

- 真实 Docling 多平台差异：交后续 UF-PF03 evidence work。
- material generic raw failure 与 company-first publication：交后续 material work unit。
- 旧 durable summary/failure：按 fresh-schema 规则显式排除兼容读取。
