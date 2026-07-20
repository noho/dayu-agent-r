# P1-C Plan Fix Re-Review — AgentDS

## Review Metadata

- **Date**: 2026-07-09
- **Reviewer**: AgentDS (Claude Code)
- **Re-review type**: plan fix re-review (只审 accepted plan-review findings 是否在 plan 中闭环，不审 implementation)
- **Plan**: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- **Plan fix artifact**: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-review-controller-adjudication.md`
- **Fix validation**: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-fix-controller-validation.md`
- **原 reviews**: `docs/reviews/plan-review-20260709-p1-c-mimo.md`, `docs/reviews/plan-review-20260709-p1-c-ds.md`
- **Conclusion**: **pass**

## Executive Summary

7 个 controller-adjudicated accepted findings 在更新后的 plan 中均已确定性闭环。每个 finding 的 required fix 在 plan 中有明确行号对应，措辞从条件判断改为确定性行动，测试覆盖、consistency guard、derivation strategy 选择要求均已写入 plan contract。无新增问题。

---

## Accepted Finding Closure Verification

### F01 — RunInput memory `evidence_kind` rendering deterministic S1 action

- **Controller required**: S1 显式声明 `_memory_evidence_fact_message()` 与 fallback codec 渲染为 LLM-facing，必须删除或改为业务可读文本；增加 `test_run_input_builder.py` 显式覆盖。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L145)**: "`_memory_evidence_fact_message()` 的 `evidence_kind={fact.evidence_kind.value}` 渲染，以及 fallback codec 的 `evidence_kind={evidence_kind}` 渲染，已确认进入 `SystemMessage`，必须作为确定性 LLM-facing cleanup 行动删除或改为业务可读文本。若 `MemoryEvidenceBackedFactKind` 只有单一业务含义且对模型无区分信息量，优先删除该字段；不得推迟到 P2-B 或仅在下游测试夹具掩盖。"
- **Plan evidence (L154)**: "`tests/host/test_run_input_builder.py` 必须明确覆盖 memory rendering：`_memory_evidence_fact_message()` 与 fallback codec 不再向 LLM-facing `SystemMessage` 渲染 `evidence_kind=...` 内部字段。"
- **Verdict**: ✅ 闭环。两条 rendering path 均已确定性命名，测试文件显式列出，禁止推迟到 P2-B。

### F02 — Duplicate governance S0 classification 覆盖非 AWAITING_FANOUT 路径

- **Controller required**: S0 覆盖 REUSE / HINT / HARD_STOP / REQUIRE_JUSTIFICATION / DURABLE_MISSING 进入 ToolFailedOutcome 路径，区分合法 LLM-facing 行为指导与治理泄漏。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L106)**: "S0 分类必须逐一覆盖 REUSE、HINT、HARD_STOP、REQUIRE_JUSTIFICATION、DURABLE_MISSING：DuplicateDecision.message -> _policy_decision_from_duplicate() -> _governed_failure_outcome() -> ToolFailedOutcome -> accepted tool result / LLM tool message，并区分'合法 LLM-facing 行为指导'和'治理泄漏'。例如'请优先使用上一次工具结果继续推理'可以是业务可读行为指导；'等待状态 / wait id / poll / adapter / durable governance'才是 P1-C 必改治理泄漏。"
- **Verdict**: ✅ 闭环。五种 decision kind 逐一列出，完整 context path 已写明，区分标准含正例/反例。

### F03 — "等待工具结果返回" litmus test

- **Controller required**: S0 增加可操作判据，区分任务必要行为说明 vs Host wait-governance 泄漏。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L108)**: "对'等待工具结果返回'执行 litmus test：删除该文本后，模型是否会误以为工具同步返回或编造结果？若会，则该文本是任务必要的行为说明，可以保留或轻微业务化；若错误/失败语义已可由 error、message 或 outcome type 表达，例如'未进入等待状态'，则等待/治理词应删除或改写。"
- **Verdict**: ✅ 闭环。litmus test 含具体判定问题、两条分支的处置方式、正例/反例。

### F04 — `ToolBusinessCancelled` fallback + Doc/Web cancellation wording

- **Controller required**: S2 纳入 ToolBusinessCancelled optional message/hint fallback 迁移 + Doc/Web "宿主取消"/"后续调度" 审计。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L193)**: "ToolBusinessCancelled 必须纳入同一迁移：清理 optional message/hint fallback 与 docstring，不再承诺由 runtime 填充 Host-governance 默认说明；可改为必填非空 message/hint，或改成调用方直接构造业务可读 cancelled outcome。相关测试必须覆盖缺省行为或 fail-fast contract。"
- **Plan evidence (L194)**: "对 dayu/tools/doc_tools.py、dayu/tools/web/web_tools.py、Fins read tools 的调用点做显式 message/hint 审计，确保没有依赖 runtime 默认 Host 文案，并清理 Doc/Web cancellation messages 中的'宿主取消'以及 Doc/Web/Fins cancellation hints 中的'后续调度'。"
- **Verdict**: ✅ 闭环。ToolBusinessCancelled fallback/docstring 清理、Doc/Web/Fins 三处审计均已明确写入。

### F05 — Evidence kind Host derivation 策略具体化

- **Controller required**: S1 先选择并记录可靠 Host derivation 策略，列出候选方案，说明旧 artifact no-compat 处理。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L143)**: "在修改 compaction schema 前必须选择并记录 evidence kind Host derivation 策略，不得把策略留给实现时临场猜测。候选策略至少包括：按 CompactMaterialBlockKind / material section 派生；在 compact material construction 阶段把 evidence kind 预标注为 Host-owned metadata；保留 LLM-facing source/type 字段但值域改为自解释业务标签，并通过 typed mapping helper 映射到 Host 内部 enum。implementation artifact 必须说明选择理由、可靠输入信号、为何不会让 LLM 继续输出 tool_source_text / accepted_evidence_material。"
- **Plan evidence (L147)**: "旧 compact artifacts 按本项目 schema 变更规则处理为全新 schema 起库，不新增兼容读取、兼容别名或兼容 parser 分支；如果 implementation 发现必须兼容旧 artifact，停止并回到 controller 裁决。"
- **Verdict**: ✅ 闭环。三个候选策略已列出，选择理由记录要求已写明，no-compat 策略 + stop condition 已写入。

### F06 — Fins/Doc/Web cancel hint 一致性 guard

- **Controller required**: S2 要求三处 cancel hint 改写一致，优先共享层中立 helper/constant，否则 implementation artifact 做一致性审计。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L195)**: "Fins / Doc / Web cancellation hint 改写必须保持一致。优先复用一个层中立、业务可读 helper 或 constant，但不得引入 Host governance 文案或让 dayu.runtime 反向依赖上层；若不抽取共享 helper/constant，implementation artifact 必须列出三处最终文案并做一致性审计。"
- **Verdict**: ✅ 闭环。consistency guard 已写入，优先 shared helper 路径含架构约束，fallback 审计路径已明确。

### F07 — P1-A accepted-result projection contract preservation validation

- **Controller required**: S3/validation 增加 P1-A accepted-result projection 消费者真源确认 scan。
- **Plan fix table**: ✅ 已映射。
- **Plan evidence (L231)**: "增加 P1-A accepted-result projection contract preservation scan / validation：确认 dayu/host/run_input.py、dayu/host/compact_material.py、dayu/host/memory.py 等 consumer 仍使用或保留 P1-A accepted-result projection 真源，不在 P1-C 中重新推导 query/status/source/result，也不用 LLM-facing 文案替代 typed projection contract。"
- **Plan evidence (L253, validation commands)**: `rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py`
- **Plan evidence (L263)**: "P1-A scan 确认 P1-C consumers 仍通过 accepted-result projection 真源消费 query/status/source/result；若命中显示重新推导，必须回到 S1/S3 修正。"
- **Verdict**: ✅ 闭环。S3 action item + validation command + correction loop 均已写入。

---

## Cross-cutting Verification

### Controller validation 一致性

`wu-semantic-ownership-01-p1-c-plan-fix-controller-validation.md` 中 7 个 finding 均标记为 `closed`，与本 re-review 独立核验结论一致。

### Plan fix codex table 完整性

`wu-semantic-ownership-01-p1-c-plan-fix-codex.md` 的 fix table (L18-L26) 7 个 finding → plan fix 映射完整，与 plan 实际内容一致。

### 未引入新问题

逐段对比更新前后 plan 差异，所有新增文本均为 accepted finding 的确定性闭环，无 scope creep、无新增 ambiguity、无与原有 stop condition 冲突。

### Owner boundary 一致性

Plan fix codex 的 owner boundary impact 分析 (L30-L33) 与 controller adjudication 的 owner boundary 划分一致：run_input.py → RunInputBuilder projection、duplicate → policy message owner、cancellation → tool callable/runtime boundary、compaction → Host material/parser boundary。

---

## Conclusion

**Verdict: pass**

全部 7 个 controller-adjudicated accepted findings 在更新后的 `docs/host/wu-semantic-ownership-01-p1-c-plan.md` 中均已确定性闭环。措辞从条件判断/实现时再发现提升为显式 plan contract，测试覆盖、策略选择要求、consistency guard、P1-A preservation scan 均已写入对应 slice。无新增问题，无未闭环项。

Plan 可以进入 implementation。
