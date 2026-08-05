# PR 190 F11/F12 S4 evidence 双路 review 裁决（2026-08-06）

## 范围与结论

- 被审查基线：`d9f044f944dd44e0d369f9d93e0533d2b725e413`
- immutable evidence root：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- root `digest.json` SHA-256：`38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- MiMo review：`docs/reviews/pr-190-f11-f12-s4-evidence-mimo-review-20260805.md`
- DS review：`docs/reviews/pr-190-f11-f12-s4-evidence-ds-review-20260806.md`
- 总体裁决：接受 1 项低严重度 repo observation artifact 可验证性修正；其余 4 项 finding 均被直接 owner/canonical evidence 反驳。没有 production finding，不重新运行 provider，也不改 immutable evidence root。

## Finding 逐项裁决

### MiMo-01：拒绝——混淆了 fallback input boundary 与 dispatch 完成后的 Memory snapshot

Repo artifact 的 `selected=9、dropped=2` 描述的是 canonical `CONTEXT_COMPACTION_FAILED.payload.fallback_input_window`：

- `selected_block_ids` 精确为 9；
- `dropped_block_ids` 精确为 2；
- screen 的 `fallback_selected_block_ids=9 fallback_dropped_block_ids=2` 从该 terminal payload 投影。

Reviewer 比较的 `memory.json.snapshot.trace_memory.selected_recent_window` 是 fallback dispatch 完成后重新投影的 Memory，包含 8 个 recent items；它不是失败 terminal 的 input-boundary selection ledger，也不拥有 `dropped_block_ids`。因此不能把 report 改成 `selected=8、dropped=0`。为防止再次混淆，fix 只需把 repo artifact 文案收紧为“canonical failed terminal 的 fallback input boundary 为 9/2；post-dispatch Memory 是另一投影”。

### MiMo-02：接受——repo artifact 使用了不可由 bundle 直接复核的派生 digest

Repo artifact 将 `0f9c284b...` 称为两次 repair 的 source material digest；该值只出现在人类报告，不能从 machine-readable evidence 直接定位。same-boundary truth 应引用 canonical request owner：

- operation id：`event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff`；
- `CONTEXT_COMPACTION_REQUESTED.payload.frozen_material_list_digest`：`sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`；
- 两个 attempt 均绑定同一 operation，repair 只改变 self-contained feedback/whole-candidate replay。

最小修复是只改 repo observation artifact，改用上述 canonical field/value，并明确 immutable bundle 内的 `observed-report.md` 已由 root digest 封存、不得回写；本裁决与 repo correction 是其可审计勘误。

### DS-01：拒绝——把配置 model id 当成 effective provider/model

`SMOKE ASSEMBLY compactor_model_id=mimo-v2.5-pro-plan` 是 assembly 的配置选择 id。DeepSeek workspace 的 `config/models.json` 明确让该 id `extends=deepseek-v4-flash`；实际 runner spec 与真实调用身份由 `provider-identity.json`、`compactor-attempts.json`、public Tool Trace 和 canonical terminal 共同证明为 `deepseek/deepseek-v4-flash`。F11/F12 从未把 assembly selector id 当 actual identity，亦未从该行反推 provider。无需修改 smoke owner；repo artifact 可补一句 selector/effective identity 区分。

### DS-02：拒绝——直接数据与 finding 相反

`evidence/04-deepseek-baseline/memory.json.snapshot.session_summary_memory.summary_text` 是非空 baseline summary；`evidence/05-deepseek-replacement-constrained/...` 对应字段才是 `null`。这正是 accepted `session_summary:null` complete replacement 清除旧 summary 的 before/after evidence。无需实现或文档修复。

### DS-03：拒绝——36 是 Host owner 的精确计量值

`dayu.host.compaction.derive_compact_policy_usage_actuals_v3` 对 answer anchor 计量 `title + "\\n" + detail`。本次 attempt 1 为 title 7、换行 1、detail 28，共 36；canonical EventLog audit 也记录 `answer_anchor_char_actual=36`，repair feedback 明示同一公式与 `36 > 30`。Reviewer 只统计 detail 或漏掉换行，因此 finding 不成立。Repo artifact 可补公式以提升可复核性。

## Open question 裁决

- system prompt digest：bundle 保存完整 messages；所有 attempt 的 system contract 相同，initial/repair 差异位于 user projection。该项是可复核 evidence，不是 blocker。
- repair binding：以单一 `CONTEXT_COMPACTION_REQUESTED` operation、canonical `frozen_material_list_digest` 和两个 attempt 的 operation binding 为 owner truth；不依赖报告作者的临时派生 hash。
- private SQLite：只用于隔离审计，不作为 public F11 evidence；hash mapping 与 quarantine 文件一致，发布树 secret scan 为 0 finding。

## Fix 与 re-review 要求

AgentCodex 只允许修改 repo observation artifact并新增 fix artifact：

1. 用 canonical `frozen_material_list_digest=sha256:b798...` 替换不可定位的 `0f9c...` 声明；
2. 收紧 fallback 9/2 的 owner 名称，避免与 post-dispatch Memory 的 8 items 混淆；
3. 可补充 selector id 与 effective provider/model、36 字符公式的简短说明；
4. 不修改 immutable evidence root、production、tests、oracle/scenario/registry，不运行 provider。

修复后 MiMo、DS 必须分别 re-review 完整 S4 evidence gate；两路均接受后才能形成 S4 acceptance checkpoint。
