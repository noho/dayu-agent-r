# PR190 F13 Final PR Review — DeepSeek Adversarial Route

**reviewer**: DS adversarial final reviewer
**delta**: `ab1207f1..2520b11b` (10 commits, 104 files, +12009/-2151)
**date**: 2026-08-06
**scope**: production code + tests + docs; 不重审 F11/F12 findings

---

## 1. Semantic Ownership Drift

**通过。** v4 的 proposal/replacement 分层是本次核心改动，ownership 清晰：

| 层 | Owner | 不变量 |
|---|---|---|
| `CompactCandidateV4` | 模型 | 七字段 proposal；只提 retain label，不重写旧 fact |
| `CompactAcceptedReplacementV4` | Host `derive_compact_accepted_replacement_v4` | retained atoms 从 boundary 原子复制 claim + refs；new facts 从 boundary evidence entries 合并 refs |
| `CompactAcceptedTruthV4` | Context Governance `accept_compact_candidate_v4` | proposal + replacement + boundary + coverage + audit 全量验收 |
| `validate_compact_proposal_replacement_binding_v4` | compaction.py | replacement == derive(proposal, boundary) 等式唯一校验点 |

每个 accepted fact atom 自带 `canonical_evidence_refs`，不从 aggregate refs 反推逐 fact 语义。Memory projection、Tool Trace resolver、compact material 三路消费者均从 `accepted_replacement` 同一真源读取，无各自解释 nested JSON 的路径。

`accept_compact_candidate_v4` 的验收顺序正确：先 `compact_proposal_boundary_binding_issues_v4`（label existence/kind/order），通过后再 `derive_compact_accepted_replacement_v4`，然后对 replacement 做 duplicate/contradiction/information/policy 检查。避免了 v3 中"先做 section 检查再发现 label binding 问题"的顺序缺陷。

---

## 2. Provenance Laundering 反例

**通过。** 逐层检查 evidence refs 的来源与传递：

1. **工具结果** → `PromptLocalProvenanceEntry.canonical_evidence_refs`（`_evidence_provenance` 设为 `(accepted_evidence_id,)`）
2. **compact boundary** → `CompactSourceBoundaryEntryV4.canonical_evidence_refs`（`CompactionRequest.compact_input` 从 provenance map 机械投影）
3. **模型 proposal** → 只提 support label，不提 refs
4. **Host derivation** → `derive_compact_accepted_replacement_v4` 从 boundary entries 逐 label 收集 refs，`dict.fromkeys` 去重不丢序
5. **durable** → `CONTEXT_COMPACTED` payload 双写 proposal + replacement；`_validate_aggregate_boundary_unique_membership` 额外校验 aggregate refs 是 boundary evidence 的子集
6. **read boundary** → `_parse_accepted_replacement` 严格恢复每个 fact 的四字段（含 `canonical_evidence_refs`），`CompactAcceptedEvidenceFactV4.__post_init__` 要求非空唯一

无任何路径可从模型输出或下游消费者反向构造 evidence refs。`COMPACT_FACT_SOURCE_KINDS_V4 = (EVIDENCE_MATERIAL,)` 确保新 fact 只能引用本轮 evidence material（非空 refs 已在 `CompactSourceBoundaryEntryV4.__post_init__` 担保）。

---

## 3. Empty Refs 接受路径

**通过。** `CompactAcceptedEvidenceFactV4.__post_init__` 调用 `_require_non_empty_unique_string_tuple(self.canonical_evidence_refs, ...)`——空 tuple 直接 `ValueError`。`CompactSourceBoundaryEntryV4.__post_init__` 对 `PREVIOUS_EVIDENCE_FACT` / `EVIDENCE_MATERIAL` 同样要求非空。下游 durable parser（`_parse_replacement_facts`）使用 `_required_unique_text_list` 恢复，空 array 同样 fail closed。全链路无 empty refs 可接受的路径。

---

## 4. Previous Claim 改写路径

**通过。** `derive_compact_accepted_replacement_v4` 对 retained fact：

```python
CompactAcceptedEvidenceFactV4(
    claim=entry.readable_text,          # ← 原样保留 boundary 中的 claim
    selection_labels=(entry.source_label,),
    context_labels=(),
    canonical_evidence_refs=entry.canonical_evidence_refs,  # ← 原样保留
)
```

LLM-facing prompt 明确："旧 EvidenceFact 只能通过 retain label 保留，未选择即省略；新 evidence_facts 的非空 support_labels 只能引用本轮 evidence_material"。模型无法通过 proposal 改写旧 claim——它只能选择 retain 或 omit。Host derivation 不从 proposal 反写 retained claim。

---

## 5. Multi-pass / Cap / Repair / Fallback / Stale-Late 第二 Terminal

**通过。** 关键检查点：

- **repair binding**: `build_compact_repair_feedback_v4` 绑定 `(request_digest, source_boundary_digest)`；`source_boundary_digest` 改用 `to_internal_json()`（含 `canonical_evidence_refs`），比 v3 更精确。`_repair_feedback_for_request` 两个 digest 任一不匹配即清空 feedback。
- **repair boundedness**: `MAX_COMPACT_REPAIR_ISSUES` + `MAX_COMPACT_REPAIR_FEEDBACK_CHARS` 双上限；只剩一条 issue 仍超限时 strip labels 而非截断 message。
- **multi-pass label binding**: `_bind_reactive_pass_to_root_labels` 将 pass 局部 label 重绑定到根 boundary；pipeline 在 provider 前核对 pack digest。
- **cap 语义**: evidence fact 的 item/char cap 计入"retained + new"，prompt 明示 combined caps。计量从同一 `MemoryProjectionPolicy` 和共享 `compact_text_size_units_v4` 派生。
- **fallback**: `accepted compact immediate candidate` 固定回退完整 conservative estimate——无 stale anchor 复用。

---

## 6. Durable / Public / Reconnect Divergence

**通过。** 三路消费者同源：

- **durable**: `CONTEXT_COMPACTED` payload 双写 proposal + replacement；`_FIELD_ACCEPTED_REPLACEMENT` 五区完整 JSON。
- **public Tool Trace**: `_resolved_compactor_response_from_row` 从 `semantic_payload.accepted_replacement.evidence_facts` 机械投影 `ResolvedCompactorEvidenceFact(claim, canonical_evidence_refs)`；attempt-rejected 固定空 tuple。
- **reconnect / Memory**: `project_conversation_memory_event` 从 `compacted_semantics.accepted_replacement` 读取；`_facts_from_accepted_event` 逐 fact 使用 `fact.canonical_evidence_refs`，不再从 aggregate `accepted_evidence_mapping_refs` 统一分配。

`accepted_evidence_mapping_refs` 现在是 `CompactPipelineAcceptedPayloadInput` 的 property，从 `accepted_truth.replacement.canonical_evidence_refs` 派生——单一真源，不被调用方各自重算。

---

## 7. Schema / Prompt 遗漏

**通过。** 关键一致性检查：

- `compact_output_template_v4` / `compact_output_prompt_rules_v4` / `compact_output_json_schema_v4` 三路同源（同一 `_ROOT` descriptor），均含 `retained_previous_evidence_fact_labels`。
- LLM-facing user prompt 明确七字段动作规则与引用约束，`source_kind` 含义与 `CompactSourceKindV4` 枚举一致。
- `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT` 从 4→5，artifact 结构含 `accepted_proposal` + `accepted_replacement` 双 key。
- `source_boundary` durable 字段新增 `canonical_evidence_refs`（通过 `to_internal_json()`），LLM-facing 不含——正确分层。

**一个值得注意的设计选择（非缺陷）**：`source_boundary` 的 durable 存储从手工 dict 改为 `entry.to_internal_json()`，统一了序列化路径。这是正向重构。

---

## 8. Overengineering

**通过。** 核心改动量虽大但均为必要：

- `CompactAcceptedEvidenceFactV4` + `CompactAcceptedReplacementV4` 两个新类型是 proposal/replacement 分离的最小表达
- `derive_compact_accepted_replacement_v4` 是单一 derivation 函数，无多余 abstraction
- `compact_proposal_boundary_binding_issues_v4` 替代了 v3 中分散在 `context_governance.py` 的 `_check_labels`，从 compaction contract owner 统一出口
- `validate_compact_proposal_replacement_binding_v4` 仅在 durable read boundary 调用一次，不是多余的运行时校验链

Type rename (V3→V4) 规模大但机械，不引入新语义。

---

## 9. README / Design Truth

**通过。** `dayu/host/README.md`、`dayu/config/README.md`、`docs/host/design.md` 与实际代码一致：

- README: "v4 proposal" / "accepted replacement" / "逐 fact canonical evidence refs" 术语匹配
- design.md: "accepted replacement truth" 与 `CompactAcceptedTruthV4` 一致
- config README: `dayu.context_compaction.output.v4` 七字段描述匹配 `CompactCandidateV4`

---

## 10. Real MiMo Evidence & Errata 纪律

**通过。** 本 review 基于实际 diff 证据，未运行 provider。所有结论均有代码行号锚定：

- `CompactAcceptedEvidenceFactV4.__post_init__` 的非空 refs 担保
- `derive_compact_accepted_replacement_v4` 的 retained claim 原子复制
- `_validate_aggregate_boundary_unique_membership` 的 aggregate 子集校验
- `_repair_feedback_for_request` 的 dual-digest binding
- Tool Trace `_resolved_compactor_response_from_row` 的 attempt-rejected empty facts 守卫

无基于间接迹象的推测性发现。

---

## 判决

**ACCEPTED**

本 PR 的 v4 proposal/replacement 分离设计正确地解决了 semantic ownership 问题：模型只表达"保留哪些旧事实 + 新增哪些事实"，Host 从 immutable boundary 原子展开 replacement 并逐 fact 绑定 evidence provenance。全链路（durable → Memory → Tool Trace → next-round compact material）从同一 `accepted_replacement` 真源消费，无 provenance laundering、empty refs acceptance 或 previous claim rewrite 路径。

无 blocking finding。
