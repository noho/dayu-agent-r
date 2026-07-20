# WU-SEMANTIC-OWNERSHIP-01 P1-C Plan Fix Re-Review — AgentMiMo

## Review Metadata

- **Date**: 2026-07-09
- **Reviewer**: AgentMiMo (MiMo via Claude Code)
- **Gate**: plan fix re-review（只审 accepted findings 是否在 plan 中闭环，不审 implementation）
- **Plan**: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- **Plan fix artifact**: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-review-controller-adjudication.md`
- **Fix validation**: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-fix-controller-validation.md`
- **Original reviews**: `docs/reviews/plan-review-20260709-p1-c-mimo.md`, `docs/reviews/plan-review-20260709-p1-c-ds.md`
- **Conclusion**: **pass**

---

## Accepted Finding Closure Verification

### F01 — RunInput memory `evidence_kind` cleanup and `test_run_input_builder.py` coverage

**Source**: P1C-PLAN-DS-F01 (blocking), P1C-PLAN-MIMO-F01, P1C-PLAN-MIMO-F07
**Adjudication requirement**: S1 必须将 `_memory_evidence_fact_message()` 与 fallback codec 的 `evidence_kind=...` 渲染列为确定性 LLM-facing cleanup；`tests/host/test_run_input_builder.py` 必须覆盖。

**Plan verification**:

- Plan line 145: "`dayu/host/run_input.py` 中 `_memory_evidence_fact_message()` 的 `evidence_kind={fact.evidence_kind.value}` 渲染，以及 fallback codec 的 `evidence_kind={evidence_kind}` 渲染，已确认进入 `SystemMessage`，必须作为确定性 LLM-facing cleanup 行动删除或改为业务可读文本。若 `MemoryEvidenceBackedFactKind` 只有单一业务含义且对模型无区分信息量，优先删除该字段；不得推迟到 P2-B 或仅在下游测试夹具掩盖。" ✅ 确定性行动项，措辞从原 plan 的条件判断（"如果仍输出"）提升为已确认事实（"已确认进入"）。
- Plan line 137: `tests/host/test_run_input_builder.py` 在 S1 files 列表中。 ✅
- Plan line 154: "`tests/host/test_run_input_builder.py` 必须明确覆盖 memory rendering：`_memory_evidence_fact_message()` 与 fallback codec 不再向 LLM-facing `SystemMessage` 渲染 `evidence_kind=...` 内部字段。" ✅ S1 tests 部分显式引用，解决原 MIMO-F07 遗漏。
- Plan line 250: validation commands 包含 `tests/host/test_run_input_builder.py`。 ✅

**Verdict**: ✅ closed. 确定性行动项 + 测试覆盖 + validation command 三重保障。

---

### F02 — Duplicate REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING classification

**Source**: P1C-PLAN-DS-F02, P1C-PLAN-MIMO-F02
**Adjudication requirement**: S0 必须覆盖非 AWAITING_FANOUT 的 duplicate 决策进入 `ToolFailedOutcome` 的路径，区分合法 LLM-facing 行为指导与治理泄漏。

**Plan verification**:

- Plan line 106: "对 duplicate-governance 路径列出当前 context path，不只覆盖 `AWAITING_FANOUT`。S0 分类必须逐一覆盖 `REUSE`、`HINT`、`HARD_STOP`、`REQUIRE_JUSTIFICATION`、`DURABLE_MISSING`：`DuplicateDecision.message` -> `_policy_decision_from_duplicate()` -> `_governed_failure_outcome()` -> `ToolFailedOutcome` -> accepted tool result / LLM tool message，并区分'合法 LLM-facing 行为指导'和'治理泄漏'。" ✅
- Plan line 107: `AWAITING_FANOUT` 单独列出 context path，与非 AWAITING_FANOUT 路径分离。 ✅
- Plan section 3 owner boundary 表（line 62）: Duplicate governance 行已标注 "S0 先分类 context path；LLM-facing 则改写，internal diagnostic 可保留治理术语或另设 diagnostic-only message"。 ✅

**Verdict**: ✅ closed. 五类 duplicate 决策全覆盖，路径分类要求明确。

---

### F03 — Waiting wording litmus test

**Source**: P1C-PLAN-DS-F03, P1C-PLAN-MIMO-F03
**Adjudication requirement**: S0 需要一个可操作的 litmus test 判断"等待工具结果返回"是业务可读还是治理泄漏。

**Plan verification**:

- Plan line 108: "对'等待工具结果返回'执行 litmus test：删除该文本后，模型是否会误以为工具同步返回或编造结果？若会，则该文本是任务必要的行为说明，可以保留或轻微业务化；若错误/失败语义已可由 `error`、message 或 outcome type 表达，例如'未进入等待状态'，则等待/治理词应删除或改写。" ✅
- Litmus test 与原 MIMO-F03 和 DS-F03 建议一致：删除后模型是否仍能完成任务。判据可操作、可验证。

**Verdict**: ✅ closed. Litmus test 已写入 S0 implementation shape。

---

### F04 — `ToolBusinessCancelled` fallback plus Doc/Web cancellation wording scope

**Source**: P1C-PLAN-DS-F04, P1C-PLAN-MIMO-F04
**Adjudication requirement**: S2 必须纳入 `ToolBusinessCancelled` optional fallback/docstring 清理，并审计 Doc/Web cancellation message 中的"宿主取消"和 hint 中的"后续调度"。

**Plan verification**:

- Plan line 193: "`ToolBusinessCancelled` 必须纳入同一迁移：清理 optional message/hint fallback 与 docstring，不再承诺由 runtime 填充 Host-governance 默认说明；可改为必填非空 message/hint，或改成调用方直接构造业务可读 cancelled outcome。相关测试必须覆盖缺省行为或 fail-fast contract。" ✅
- Plan line 194: "对 `dayu/tools/doc_tools.py`、`dayu/tools/web/web_tools.py`、Fins read tools 的调用点做显式 message/hint 审计，确保没有依赖 runtime 默认 Host 文案，并清理 Doc/Web cancellation messages 中的'宿主取消'以及 Doc/Web/Fins cancellation hints 中的'后续调度'。" ✅
- Plan line 183-184: S2 files 列表包含 `dayu/tools/doc_tools.py` 和 `dayu/tools/web/web_tools.py`。 ✅

**Verdict**: ✅ closed. `ToolBusinessCancelled` fallback 路径 + Doc/Web 文案审计均纳入 S2。

---

### F05 — Concrete Host evidence-kind derivation strategy and no-compat old artifact handling

**Source**: P1C-PLAN-DS-F05, P1C-PLAN-MIMO-F05
**Adjudication requirement**: S1 必须在 implementation 前选择并记录 evidence kind Host derivation 策略，列出候选方案；旧 compact artifacts 按全新 schema 起库处理。

**Plan verification**:

- Plan line 143: "在修改 compaction schema 前必须选择并记录 evidence kind Host derivation 策略，不得把策略留给实现时临场猜测。候选策略至少包括：按 `CompactMaterialBlockKind` / material section 派生；在 compact material construction 阶段把 evidence kind 预标注为 Host-owned metadata；保留 LLM-facing source/type 字段但值域改为自解释业务标签，并通过 typed mapping helper 映射到 Host 内部 enum。implementation artifact 必须说明选择理由、可靠输入信号、为何不会让 LLM 继续输出 `tool_source_text` / `accepted_evidence_material`。" ✅ 三条候选策略 + 选择理由要求。
- Plan line 147: "旧 compact artifacts 按本项目 schema 变更规则处理为全新 schema 起库，不新增兼容读取、兼容别名或兼容 parser 分支；如果 implementation 发现必须兼容旧 artifact，停止并回到 controller 裁决。" ✅ no-compat 策略 + stop condition。

**Verdict**: ✅ closed. 策略候选已列出、选择理由要求明确、旧 artifact no-compat 策略到位。

---

### F06 — Fins/Doc/Web cancellation hint consistency guard

**Source**: P1C-PLAN-DS-F06, P1C-PLAN-MIMO-F06
**Adjudication requirement**: S2 必须要求 Fins/Doc/Web cancellation hint 改写保持一致；可共享层中立中性 helper/constant 但不得引入 Host governance 文案。

**Plan verification**:

- Plan line 195: "Fins / Doc / Web cancellation hint 改写必须保持一致。优先复用一个层中立、业务可读 helper 或 constant，但不得引入 Host governance 文案或让 `dayu.runtime` 反向依赖上层；若不抽取共享 helper/constant，implementation artifact 必须列出三处最终文案并做一致性审计。" ✅

**Verdict**: ✅ closed. 一致性要求 + 共享 helper 约束 + fallback 一致性审计均到位。

---

### F07 — P1-A accepted-result projection preservation validation

**Source**: AgentDS validation observation, AgentMiMo validation observation
**Adjudication requirement**: S3/validation 必须增加 P1-A accepted-result projection contract preservation scan。

**Plan verification**:

- Plan line 231: "增加 P1-A accepted-result projection contract preservation scan / validation：确认 `dayu/host/run_input.py`、`dayu/host/compact_material.py`、`dayu/host/memory.py` 等 consumer 仍使用或保留 P1-A accepted-result projection 真源，不在 P1-C 中重新推导 query/status/source/result，也不用 LLM-facing 文案替代 typed projection contract。" ✅
- Plan line 253: validation command `rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py`。 ✅

**Verdict**: ✅ closed. P1-A preservation scan 已纳入 S3 validation shape + validation commands。

---

## Fix Artifact Quality Assessment

| 维度 | 评价 |
|---|---|
| Finding 映射准确性 | 每个 accepted finding 在 fix artifact 中有对应 plan 修复，且映射到正确的 plan section 和行号。 ✅ |
| Owner boundary 影响 | Fix artifact 正确标注了 4 个 owner boundary impact（RunInputBuilder / duplicate governance / cancellation wording / compaction evidence kind）。 ✅ |
| 残余风险 | Fix artifact 列出 3 条 residual risk，均为真实风险且有明确处理策略（回到 controller 裁决）。 ✅ |
| 与 controller adjudication 对齐 | Fix artifact 的所有修复项与 adjudication 的 required fix 一一对应，无遗漏、无超出。 ✅ |

---

## Residual Risk 评估（仅针对 plan，非 implementation）

1. **Duplicate message 最终投影位置**：fix artifact 正确指出 implementation 仍需用代码路径确认 duplicate message 的最终投影位置。Plan S0 已要求逐类分类，风险可控。 ✅
2. **Evidence kind derivation 策略选择**：fix artifact 正确指出最终策略需 implementation 基于当前 material structure 选择。Plan S1 已列出 3 条候选 + 选择理由要求。 ✅
3. **旧 compact artifacts 兼容性**：fix artifact 正确指出若必须兼容旧 artifact 应停止并回到 controller 裁决。Plan S1 line 147 已写明 stop condition。 ✅

---

## Conclusion

**Verdict: pass**

7 个 accepted findings 全部在 plan fix 后的 plan 中闭环：

| Finding | 状态 | 闭环位置 |
|---|---|---|
| F01 | ✅ closed | S1 line 145（确定性 cleanup）+ line 154（test coverage） |
| F02 | ✅ closed | S0 line 106（五类 duplicate 全覆盖） |
| F03 | ✅ closed | S0 line 108（litmus test） |
| F04 | ✅ closed | S2 line 193-194（ToolBusinessCancelled + Doc/Web audit） |
| F05 | ✅ closed | S1 line 143（候选策略）+ line 147（no-compat） |
| F06 | ✅ closed | S2 line 195（一致性 guard） |
| F07 | ✅ closed | S3 line 231（P1-A preservation scan）+ validation command line 253 |

Fix artifact 质量合格：finding 映射准确、owner boundary 影响正确标注、残余风险有明确处理策略。Plan 可进入 implementation 阶段。

无新 findings。
