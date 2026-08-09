# PR 190 F13 Plan Final Re-Review — AgentDS 窄 follow-up

## Review metadata

- **review type**: adversarial plan re-review（窄 follow-up，仅验证三项修订）
- **reviewer**: AgentDS
- **original review**: `docs/reviews/plan-review-20260806-141818.md`
- **re-review**: `docs/reviews/plan-review-20260806-142730.md`（结论 `pass-with-risks`，含 R1/R2）
- **re-review fix**: `docs/gateflow/pr-190-f13-plan-rereview-fix-20260806-143034.md`
- **revised plan**: `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`
- **timestamp**: 2026-08-06

## 修订验证

本 follow-up 仅验证三项修订：DS R1、DS R2、MiMo F08。

### DS R1（C1-C3 checkpoint re-validation 与证据持久化，原 medium）→ **verified fixed**

**修订位置**: plan 第 308-313 行

**验证结果**:

| R1 要求 | 修订内容 | 状态 |
|---|---|---|
| 证据持久化格式与位置 | `docs/gateflow/pr-190-f13-s1-cN-checkpoint-<timestamp>.md` | ✅ |
| 持久化内容 | "审阅范围、base/worktree diff identity、两路reviewer结论、命令与关键验证结果" | ✅ |
| re-validation 触发条件 | "若后续步骤修改其覆盖文件或owner contract，该checkpoint立即失效" | ✅ |
| re-validation 动作 | "必须基于新diff重跑相同focused validation与两路增量review并写新artifact" | ✅ |
| 旧 artifact 处理 | "旧artifact保留为superseded evidence，不能覆盖" | ✅ |

修订后的 checkpoint 机制有完整的生命周期：创建 → 通过 → 可能失效 → 重跑 → superseded。可追溯、可审计、不可覆盖。

### DS R2（旧 accepted_evidence_id residue scan 范围，原 low）→ **verified fixed**

**修订位置**: plan 第 297 行

**修订前**: "全仓 `rg` 不得残留 v3 compact contract或旧 durable key"
**修订后**: "全仓 `rg` 不得残留 v3 compact contract、旧 durable key或 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取。若其它上游 typed accepted-evidence atom仍合法使用 singular `accepted_evidence_id`，必须逐处确认其不是 material-pack 下游读路径并在checkpoint artifact记录；历史 evidence 文档除外。"

**验证结果**:

| R2 要求 | 修订内容 | 状态 |
|---|---|---|
| scan scope 覆盖旧字段名 | 显式包含 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取 | ✅ |
| 上游合法引用不误删 | "若其它上游 typed accepted-evidence atom 仍合法使用...必须逐处确认...并在 checkpoint artifact 记录" | ✅ |
| 历史 evidence 文档排除 | "历史 evidence 文档除外" | ✅ |

### MiMo F08（rolling canonical_source_refs vs canonical_evidence_refs 链，原 low）→ **verified fixed**

**修订位置**: plan 第 194-195 行

**修订前**: "compact_material.py 从 previous typed accepted_replacement.evidence_facts 构造 previous blocks；每个 block 的 readable claim 与 provenance entry refs 来自同一个 fact atom，不能分别读取 flat fields。"

**修订后**: 前句保留，新增： "rolling material block 的 `canonical_source_refs` 继续保存 previous compact EventLog ref（来源标识）；同一 block/provenance entry 的 `canonical_evidence_refs` 保存该 accepted fact atom 的逐 fact evidence refs（证据标识）。material-pack boundary constructor 只能从后者构造 `PREVIOUS_EVIDENCE_FACT.canonical_evidence_refs`，不得从前者替代或推断。"

**验证结果**:

| MiMo F08 要求 | 修订内容 | 状态 |
|---|---|---|
| 区分 source refs 与 evidence refs | `canonical_source_refs` = compact EventLog ref（来源标识），`canonical_evidence_refs` = 逐 fact evidence refs（证据标识） | ✅ |
| boundary constructor 只读 evidence refs | "只能从后者构造...不得从前者替代或推断" | ✅ |
| 不被 source refs 污染 | 显式禁止替代或推断 | ✅ |

## 新增 finding 检查

对三项修订引入的 plan 变更做全量扫描，检查是否引入新 blocking/high/medium finding：

- **C1-C3 artifact 持久化**（第 308-313 行）：无新问题。checkpoint artifact 路径格式明确，re-validation 规则完备。
- **residue scan 范围扩展**（第 297 行）：无新问题。`accepted_evidence_id` 的 scan scope 正确处理了 material-pack 下游与上游合法引用的分类。
- **canonical_source_refs/evidence_refs 区分**（第 194-195 行）：无新问题。两个 ref 类型的语义清晰分离，boundary constructor 只消费后者。

## 结论

**accepted**

三项修订均已正确应用到 plan 中。DS R1（C1-C3 re-validation + 证据持久化）、DS R2（旧字段 residue scan）、MiMo F08（rolling source/evidence refs 分离）全部 verified fixed。

修订后 plan 无新增 blocking、high 或 medium finding。原两轮 review 的全部 findings 均已关闭（fixed 或 correctly rejected-with-reason）。plan 可以进入 implementation gate。
