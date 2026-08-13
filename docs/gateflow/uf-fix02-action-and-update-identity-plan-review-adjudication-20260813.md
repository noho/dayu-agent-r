# UF-FIX02 action-and-update-identity — Plan Review Adjudication

## Gate context

- Gate：`plan review`
- Plan：`docs/gateflow/uf-fix02-action-and-update-identity-plan-20260813.md`
- AgentMiMo：`docs/reviews/plan-review-20260813-171637.md`，`pass-with-risks`
- AgentDS：`docs/reviews/plan-review-20260813-172351.md`，`pass-with-risks`
- Controller decision：**FIX REQUIRED**
- Next gate：`fix`，随后双路 `re-review`

## Finding adjudication

### MIMO-001 — accepted（bounded remedy）

- 状态：`accepted`
- 理由：实施后 UF-A08 的旧 observed behavior 确会与新正确行为不一致，plan 应显式说明其状态与后续 owner，避免实现 Agent 误判。
- 有界修复：只在 plan / Gateflow artifacts 说明 UF-A08 intentionally stale，等待后续统一 conformance refresh。
- 拒绝部分：不得按 reviewer 建议修改 scenario status；用户明确禁止本 WU 刷新 registry 或冻结 evidence。

### MIMO-002 — accepted

- 状态：`accepted`
- 理由：同 batch reset 后的 store/create failure 与 precommit cancellation 必须明确走 batch rollback/discard，published old state 保持不变；这是 UF-FIX01 atomic contract 的必要规格。
- 修复：在 publication transition 写出错误/取消分支，并绑定现有及新增 rollback assertions。

### MIMO-003 / DS-03 — accepted（consolidated）

- 状态：`accepted`
- 理由：reset 只清 staging identity tree，不应丢失 caller 已持有的 `previous_meta`；version 与 `first_ingested_at` 必须从该真源派生并由测试固定。
- 修复：明确 transition invariant；S2 对改名 update 与 deleted restore 断言 `first_ingested_at` 保持，version 规则不回退。

### DS-01 — accepted

- 状态：`accepted`
- 理由：`DoclingUploadService` 是 filing/material 共用 action、skip 与 publication owner；若仅为 filing 增加分支，会违反唯一 owner 与禁止下游特例约束。共享 owner 的一致性效果必须被明确并测试。
- 修复：plan 声明 material 同步获得 update-missing 不 upsert、deleted auto 不 skip、existing update 完整替换；增加最小 material parity owner tests。
- 边界：不新增 material typed usage、CLI/Service/SEC material workflow 生产改动或 focused-real matrix；material broader public error projection 交由既有后续 conformance owner。

### DS-02 — accepted

- 状态：`accepted`
- 理由：旧 import/assertion 精确固化本 WU 要移除的 upsert bug；未点名迁移会诱导 compat shim 或 collection failure。
- 修复：S2 明确删除 `_resolve_upsert_mode` import 与旧断言，以 owner action/replacement matrix 取代，并要求全仓零命中。

## Scope and residual risks

- Goal Confirmation 继续是 binding contract；不新增生产 owner、public schema 或跨层接口。
- UF-A08 stale observed evidence：owner/destination=`后续统一 conformance refresh`。
- material typed usage / full-real：owner/destination=`UF-PF12 或后续明确 work unit`；本 WU 只做共享 owner parity tests。
- UF-FIX03/06/07/08/10/11 与 UF-PF03–UF-PF12 其它范围保持 deferred，不进入实现。
- 无未分类 residual risk，无 blocking open question。
