# PR 190 F13 S0 DeepSeek Re-Review

## Gate metadata

- Gate：S0 review re-review（follow-up）
- Base：`2d914beefb7bdee3e762df06f5f1ef0d115da143`
- 原 review：`docs/reviews/code-review-20260806-145052.md`
- Controller 裁决：`docs/gateflow/pr-190-f13-s0-review-adjudication-20260806.md`
- 被审文件：`docs/host/design.md`（当前 unstaged diff，474 行）、`docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md`
- Reviewer：DeepSeek（原 reviewer）
- Re-review scope：仅对原 D1–D5 逐项验证 FIXED / STILL OPEN

## 裁决摘要

Controller 对 D1–D5 全部裁决 ACCEPT / FIXED。M4 被 REJECT WITH REASON（避免重复真源）。Controller 已执行独立全文扫描确认 active v3 type/schema/function 为 0 命中。

## 逐项验证

### D1 — 空 evidence refs 检测点不明确

- **裁决**：ACCEPT / FIXED
- **声称修复**：§24.3 固定 material-pack/source-boundary 构造为 canonical detection point；non-repairable fail，不消耗 attempt，不写 attempt-rejected，不进 LLM repair；durable validator 只做 defense-in-depth
- **实际修复位置**：`docs/host/design.md` §24.3（diff line 113）
- **修复文本**：
  > 空 evidence refs的 canonical detection point固定在 material-pack / source-boundary构造阶段：`evidence_material`或`previous_evidence_fact`对应 entry为空时，Host必须在任何 compactor runner-call / proposal manifest前 typed fail closed，把它作为 non-repairable material/boundary construction failure交给既有 pre-dispatch或compaction failure owner；不得消耗 semantic attempt预算，不得写 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，也不得进入 LLM repair。accepted replacement validator与durable parser仍重复执行 non-empty / exact-binding检查，属于 defense-in-depth，只能拦截非法构造或损坏payload，不能成为把已知坏boundary送给模型的理由。
- **验证**：
  - 明确指定了 canonical detection point（material-pack/source-boundary 构造阶段）✓
  - 明确在 runner-call / proposal manifest 之前 fail ✓
  - 明确不消耗 attempt 预算 ✓
  - 明确不写 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` ✓
  - 明确不进 LLM repair ✓
  - 明确 validator/parser 是 defense-in-depth ✓
  - 明确禁止"把已知坏 boundary 送给模型" ✓
- **判定**：**FIXED**

### D2 — `PromptLocalProvenanceEntry` 缺完整 shape

- **裁决**：ACCEPT / FIXED
- **声称修复**：§24.3 新增完整字段、tuple provenance clean replacement、frozen/slots/无默认值与按 source kind 的 empty/non-empty 约束
- **实际修复位置**：`docs/host/design.md` §24.3（diff lines 82–97、line 110）
- **修复文本（完整 type shape）**：
  ```text
  PromptLocalProvenanceEntry
    label: PromptLocalMaterialLabel
    section: CompactMaterialSection
    kind: CompactMaterialBlockKind
    canonical_source_refs: tuple[str, ...]
    source_event_refs: tuple[str, ...]
    content_digest: str
    canonical_evidence_refs: tuple[str, ...]
    tool_result_event_ref: str | null
    tool_call_event_ref: str | null
    payload_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    source_locator_refs: tuple[OpaqueEvidenceRef, ...]
    chunk_parent_label: PromptLocalMaterialLabel | null
    chunk_ordinal: int | null
  ```
- **修复文本（约束）**：
  > PromptLocalProvenanceEntry 是 frozen/slots、无默认值的 material-pack typed contract；它只保留 canonical_evidence_refs，不再保留 singular accepted_evidence_id。current evidence material 从上游 accepted evidence atom机械形成单元素 refs；previous EvidenceFact 从上一轮 typed accepted replacement的对应 fact atom原样携带一个或多个 refs；普通 trace / answer / summary / intent / reference entry固定为空。其余字段继续分别保存 material section/kind、source/EventLog refs、内容 digest、当前 evidence 的 tool result/call refs、payload/artifact/source locator refs与可选 chunk binding，不能用其中任一字段替代 canonical evidence refs。
- **验证**：
  - 14 字段完整 type shape，含类型标注 ✓
  - frozen/slots、无默认值明确声明 ✓
  - 按 source kind 的 empty/non-empty 约束明确（evidence kind 非空，其余为空）✓
  - current evidence → 单元素 refs；previous fact → 一或多个 refs 的构造规则明确 ✓
  - 明确 `canonical_evidence_refs` 不再保留 singular `accepted_evidence_id` ✓
  - 明确其余字段不可替代 `canonical_evidence_refs` ✓
- **判定**：**FIXED**

### D3 — scan 声称缺方法和计数

- **裁决**：ACCEPT / FIXED
- **声称修复**：S0 implementation artifact 记录全文扫描范围、patterns、命中计数和两处 legacy negative-only 命中解释
- **实际修复位置**：`docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md` Validation section（line 95）
- **修复文本**：
  > design terminology / reference scan：PASS。扫描范围为`docs/host/design.md`全文；使用`rg -n`定位命中并用`rg -c`逐pattern计数：active v3 type/schema/function pattern（`CompactInputV3|CompactCandidateV3|CompactAcceptedTruthV3|CompactOutputCapsV3|compact_output_template_v3|compact_output_json_schema_v3|parse_compact_candidate_v3|dayu.context_compaction.input.v3|dayu.context_compaction.output.v3`）为0；`CompactInputV4` 10、`CompactCandidateV4` 7、`CompactAcceptedTruthV4` 6、`CompactAcceptedReplacementV4` 3、`retained_previous_evidence_fact_labels` 2、`canonical_evidence_refs` 10、`accepted_replacement` 4、artifact schema-5固定语句1。`accepted_candidate`与`schema-4`各2次，均只出现在fresh reader明确拒绝旧shape及对应negative owner test中，不是active contract。
- **验证**：
  - 扫描范围明确：`docs/host/design.md` 全文 ✓
  - 扫描方法明确：`rg -n` 定位 + `rg -c` 计数 ✓
  - v3 patterns 列表完整（9 个 pattern 组合为 1 个 regex），全部 0 命中 ✓
  - v4 关键 patterns 逐项计数（共 7 类 pattern，含具体命中数）✓
  - legacy `accepted_candidate`/`schema-4` 命中（各 2 次）有解释：仅在拒绝旧 shape 与 negative owner test 中出现 ✓
  - previous fact/support 与 aggregate/fact 组合扫描有定性说明 ✓
  - Controller 独立验证：adjudication line 40–41 确认 "active v3 type/schema/function全文扫描：0命中" ✓
- **判定**：**FIXED**

### D4 — descriptor v2 与 body v4 版本易混淆

- **裁决**：ACCEPT / FIXED
- **声称修复**：§24.4 明确 descriptor schema 与 body schema 是独立显式契约；reader 必须验证 body `schema`，不得从 descriptor 名字猜版本
- **实际修复位置**：`docs/host/design.md` §24.4（diff line 238）
- **修复文本**：
  > compactor input projection 继续使用 `compactor_input_projection.v2` descriptor schema，但 body 持久化完整 `CompactInputV4`、真实 output caps、可选 repair binding 与既有 provenance descriptor；descriptor schema版本与body业务schema版本是两个独立、显式校验的契约，reader必须从body的`schema`字段验证v4，不能从descriptor名字猜测input版本。
- **验证**：
  - 明确 descriptor schema 与 body schema 是两个独立契约 ✓
  - 明确 reader 必须从 body 的 `schema` 字段验证版本 ✓
  - 明确禁止从 descriptor 名字猜测 input 版本 ✓
  - 与 `CompactInputV4.schema: "dayu.context_compaction.input.v4"`（diff line 62）形成一致校验链 ✓
- **判定**：**FIXED**

### D5 — all-clear 语义未裁决

- **裁决**：ACCEPT / FIXED
- **声称修复**：§24.3 固定非空 boundary 下五类全空为 `EMPTY_SEMANTIC_OUTPUT` typed reject；section 清空与 retain-only 仍合法；空 boundary 不调用 compactor
- **实际修复位置**：`docs/host/design.md` §24.3（diff line 172）
- **修复文本**：
  > 若非空 source boundary最终生成的 replacement在五类语义上全部为空，即 summary为null且 facts / anchors / intents / reference continuity全空，Host必须以 `EMPTY_SEMANTIC_OUTPUT`或当前同义typed issue拒绝；section可以单独清空，但不能把 all-clear当作无条件session reset。source boundary为空时本来就不得调用compactor。
- **验证**：
  - all-clear 条件精确定义：非空 boundary + 五类语义全部为空 ✓
  - 拒绝动作明确：`EMPTY_SEMANTIC_OUTPUT` typed reject ✓
  - section 单独清空仍然合法（如 retain-only、summary-only clear）✓
  - 明确 all-clear ≠ 无条件 session reset ✓
  - 空 boundary 不调用 compactor 保持不变 ✓
  - retain-only 仍显式合法：同段 "evidence_facts=[] 且 retain selector 非空是合法 retain-only proposal" ✓
- **判定**：**FIXED**

## 修复引入的新内容审查

以下为本次修复新增、原 review 未覆盖的内容，简要走读确认无新问题：

1. **`CompactAcceptedTruthV4` 完整 typed shape**（diff lines 198–207）：包含 proposal、replacement、boundary、coverage、audit、current input 与 `_permit`。`_permit` 是 Python 惯例表示 governance-private token。shape 完整且与 accept chain 六步骤一致。无新问题。

2. **`PromptLocalProvenanceEntry` 新增字段与 `PromptLocalMaterialLabel`/`CompactMaterialSection`/`CompactMaterialBlockKind` 引用**（diff lines 82–97）：这些类型在当前 diff 中作为 forward reference 出现，未在本 diff 内定义。它们应属于既有的 material-pack 类型体系（在设计文档其它位置或将在 S1 实现时定义）。不是本 S0 设计真源的缺口——本 S0 的 owner 是 `canonical_evidence_refs` 字段的 replacement 来源契约，其余字段只为定位该新增字段的 type context。无新问题。

3. **reactive multi-pass 聚合详细规则**（diff lines 429–443）：pass-local accept、audit proposal 聚合、replacement 聚合、atom 不可拆分、root validator 重验——规则完整且与原有 single-pass accept chain 一致。无新问题。

4. **Goal Confirmation 逐项映射表**（implementation record lines 64–75）：8 项 confirmed goal × design owner/section × S0 固定结果。映射准确，每个 goal 均可追溯到 design.md 的具体段落。无新问题。

## 最终判定

| ID | 原严重程度 | 裁决 | 当前状态 |
|----|-----------|------|----------|
| D1 | 高 | ACCEPT / FIXED | **FIXED** |
| D2 | 中 | ACCEPT / FIXED | **FIXED** |
| D3 | 中 | ACCEPT / FIXED | **FIXED** |
| D4 | 低 | ACCEPT / FIXED | **FIXED** |
| D5 | 低 | ACCEPT / FIXED | **FIXED** |

全部 5 项 finding 均已修复。未发现修复引入的新问题。

## Residual Risk（不变）

原 review 的 residual risks 仍然成立且未因本次修复恶化或改善：

1. Schema-4 旧数据断裂风险（已知，已记录在 implementation record line 112）
2. Implementation complexity risk（S1/S2 负责，implementation record line 110）
3. Test coverage risk（S1/S2 负责，implementation record line 111）
4. Oracle formal scenario 区分（已验证通过，无变化）
5. `docs/host/design.md` 未修改区域未经本 reviewer 独立扫描（但 D3 修复后的全文 scan 证据 + Controller 独立验证已实质覆盖此风险）
6. `docs/engine/design.md` truth check（Controller 独立确认无 diff，adjudication line 41）
