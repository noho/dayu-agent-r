# PR 190 F13 Plan Final Re-Review (MiMo)

## Metadata

- reviewed target: `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`（rereview-fix-20260806-143034 修订后）
- scope: 窄验证 DS R1/R2 与 MiMo F08 三项修订；检查修订后 plan 是否引入新 blocking/high/medium finding
- reviewer: AgentMiMo
- timestamp: 2026-08-06T14:32:00+08:00

## 逐项验证

### DS R1（C1-C3 重验与证据持久化）→ fixed ✅

fix 描述：每个 checkpoint 写独立 timestamp artifact；后续修改覆盖文件/owner contract 时原 checkpoint 立即失效并必须重跑，旧 artifact 保留为 superseded evidence。

plan 第 308-313 行验证：

- checkpoint 持久化路径明确：`docs/gateflow/pr-190-f13-s1-cN-checkpoint-<timestamp>.md`
- 持久化内容明确：审阅范围、base/worktree diff identity、两路 reviewer 结论、命令与关键验证结果
- 失效规则明确："若后续步骤修改其覆盖文件或 owner contract，该 checkpoint 立即失效，必须基于新 diff 重跑相同 focused validation 与两路增量 review 并写新 artifact"
- 保留规则明确："旧 artifact 保留为 superseded evidence，不能覆盖"

修订引入新风险：无。checkpoint artifact 路径是 plan/gateflow 治理文件，不进入生产代码。

### DS R2（旧 singular 字段 scan）→ fixed ✅

fix 描述：residue scan 明确覆盖 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取；其它上游同名 typed 字段需逐处分类并记录。

plan 第 297 行验证：

- "全仓 `rg` 不得残留 v3 compact contract、旧 durable key 或 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取"
- "若其它上游 typed accepted-evidence atom 仍合法使用 singular `accepted_evidence_id`，必须逐处确认其不是 material-pack 下游读路径并在 checkpoint artifact 记录"

修订引入新风险：无。逐处分类规则避免了误删真实 accepted evidence source atom（如 `tool_runtime.py` 中的 `derive_accepted_evidence_id`），同时确保 material-pack 下游读路径被完全替换。

### MiMo F08（rolling source/evidence refs 链）→ fixed ✅

fix 描述：明确 `canonical_source_refs` 保存 compact event 来源，`canonical_evidence_refs` 保存逐 fact 证据；boundary 只能读后者。

plan 第 195 行验证：

- "`canonical_source_refs` 继续保存 previous compact EventLog ref（来源标识）；同一 block/provenance entry 的 `canonical_evidence_refs` 保存该 accepted fact atom 的逐 fact evidence refs（证据标识）"
- "material-pack boundary constructor 只能从后者构造 `PREVIOUS_EVIDENCE_FACT.canonical_evidence_refs`，不得从前者替代或推断"

修订引入新风险：无。两个字段语义清晰分离，boundary constructor 的读取来源约束明确。

## 修订后 plan 新 finding 检查

三项修订均为增量细化（checkpoint 持久化规则、residue scan 范围、字段语义说明），不改变 plan 的架构、状态机、slice 边界或 contract 设计。未引入新 blocking/high/medium finding。

## Conclusion

**accepted**

DS R1/R2 与 MiMo F08 三项修订均已正确反映在 plan 文本中，未引入新 blocking/high/medium finding。plan 可以进入 implementation。
