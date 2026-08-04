# Interactive Conversation Memory closure F10：Plan amendment review（MiMo）

## Gate

- Review 类型：plan amendment 独立审查。
- 审查目标：`docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-controller.md`。
- 对照材料：accepted plan codex（`wu-interactive-memory-closure-f08-f10-plan-codex.md`）、F10 blocked implementation artifact（`wu-interactive-memory-closure-f10-implementation-codex.md`）、根 `AGENTS.md`、当前 production owner code（`compaction.py`、`compact_material.py`、`compact_pipeline.py`、`compaction_operation.py`）。
- 结论：**PASS**。无 NEEDS_FIX 级反例。

---

## 1. SelectedBlockProvenance 三字段是否足以从 source snapshot 绑定 selection 到 material pack boundary

### 1.1 审查目标

amendment Decision 1 提议新增 `SelectedBlockProvenance(block_id, canonical_source_refs, content_digest)`，并要求 operation 在 provider 前和 durable accept 前做精确一一匹配。需证伪：三字段是否遗漏关键 identity 字段（如 `kind`、`section`、`labels`），或能否被 same-count swap / group swap 绕过。

### 1.2 直接代码证据

**当前 root guard 不具备 provenance binding（确认 F10-BLOCK-001）：**

`compaction_operation.py:1539-1580` 的 `_validate_operation_root_request` 只做两项校验：

1. **数量比较**（line 1569）：`len(selection.selected_block_ids) != selected_material_count`，只比较 count。
2. **自比较**（line 1579）：`pack_labels != tuple(entry.source_label for entry in compact_input.source_boundary)`，比较 material pack 自身的 prompt-local labels 与由同一 pack 投影出的 `CompactInputV2.source_boundary` labels——这是同一数据源的机械投影自比较，不涉及 block_id 到 boundary 的绑定。

pipeline 的 `_validate_segment_against_source_snapshot`（`compact_pipeline.py:966-996`）验证 block partition 和 group membership 对 source snapshot 一致，但它只检查 `block_id` 是否在 snapshot 中存在（line 983: `selected_ids.issubset(known_ids)`），不验证 pack 中实际 block 的 `canonical_source_refs` / `content_digest` 与 selection 声明的 block_id 对应。

**结论**：当前代码中确实不存在 block_id → boundary/canonical provenance 的 bridge。operation 不再持有 pipeline 的 source snapshot，无法独立重算该关系。amendment 的触发原因成立。

### 1.3 三字段充分性分析

**为什么 `canonical_source_refs` + `content_digest` 足以防 swap：**

- `canonical_source_refs` 是 EventLog source identity 的唯一标识（`RunInputMaterialBlock.canonical_source_refs`，`compact_material.py:209`）。
- `content_digest` 是业务可读文本的 canonical digest（`compact_material.py:210`）。
- 二者组合形成 block 的双重 identity：refs 是来源身份，digest 是内容身份。

**反例尝试 1：same-count swap（替换一个 block_id 为未知 id）**

假设 selection 声明 block A 的 provenance 为 `(refs_A, digest_A)`，但 material pack 中对应位置实际是 block B `(refs_B, digest_B)`。验证方做一一匹配时：
- 若按 `canonical_source_refs` 匹配：`refs_A != refs_B`，fail。
- 若按 `content_digest` 匹配：`digest_A != digest_B`（除非 A/B 文本恰好相同，见反例 3）。

**判定**：caught。

**反例尝试 2：whole-group swap（group A/B 的 selected/excluded disposition 等规模互换）**

假设 group A 的 blocks `[a1, a2]` 被声明为 selected，group B 的 blocks `[b1, b2]` 被声明为 excluded，但 material pack 中实际 selected 的是 `[b1, b2]`。

pipeline 的 `_validate_segment_against_source_snapshot`（line 985-990）验证 `selected_segment.turn_group_memberships == expected_memberships`，其中 `expected_memberships` 由 `source_snapshot.material_blocks` 机械产生。membership 包含 `turn_group_id` 和 `member_block_ids`，是 snapshot 级 identity。

如果 swap 后 selection 的 memberships 声明 group A 的成员为 `[a1, a2]`，但 pack 中实际是 `[b1, b2]`：
- pipeline 验证 memberships 与 snapshot 一致——这是 selection 声明级校验，通过（因为声明没变）。
- operation 的 provenance 匹配验证 pack 中每个 block 的 `(refs, digest)` 与声明的 provenance 一致——`refs_b1 != refs_a1`，fail。

**判定**：caught。

**反例尝试 3：同文本、同 digest、不同 refs 的 swap**

假设 block A 和 block B 的业务文本恰好相同（因此 `content_digest` 相同），但 `canonical_source_refs` 不同（来自不同 EventLog 事件）。此时：
- `content_digest` 匹配通过。
- `canonical_source_refs` 匹配失败：`refs_A != refs_B`。

**判定**：caught。`canonical_source_refs` 作为 EventLog source identity 是不可碰撞的（每个 event 有唯一 ref）。

**反例尝试 4：遗漏 `kind` / `section` / `labels`**

amendment 的 provenance 三字段不包含 `kind`、`section`、`source_labels`。但这些字段不参与 identity 绑定逻辑：
- `kind` 和 `section` 是 block 的分类属性，不是 identity 字段。同一 `canonical_source_refs` 不可能同时是 `USER_INPUT` 和 `TOOL_RESULT`。
- `source_labels` 是 prompt-local label，属于 pack 构造时的下游投影（`compact_material.py` 的 `_compact_material_block` 函数），不是 source identity。
- `CompactMaterialBlock.llm_json()`（line 416-427）明确剥离 `canonical_source_refs`、`content_digest`、`size_units`，只保留 `label`、`kind`、`text`、`source_labels`——这证实 labels 是 LLM-facing 投影，不是 identity。

**判定**：不遗漏。三字段是 block identity 的最小完备集。

### 1.4 结论

**PASS**。`SelectedBlockProvenance` 的 `canonical_source_refs` + `content_digest` 组合足以从 source snapshot 绑定 selection 到 material pack boundary，不能被 same-count swap 或 group swap 绕过。`kind`/`section`/`labels` 不是 identity 字段，不需纳入 provenance。

---

## 2. 是否遗漏 kind/section/labels

已在 1.4 节判定：不遗漏。补充直接代码证据：

- `CompactMaterialBlock.to_json()`（`compaction.py:399-414`）包含 `block_label`、`section`、`kind`、`text`、`size_units`、`source_labels`、`canonical_source_refs`、`content_digest`。其中 `canonical_source_refs` 和 `content_digest` 是 source identity；其余是派生属性。
- `CompactEvidenceBlock`（`compaction.py:431`）同样有 `canonical_source_refs` 和 `content_digest`，且 `accepted_evidence_id` 是 evidence 级 identity。amendment 未要求 provenance 包含 `accepted_evidence_id`，但 evidence block 的 `canonical_source_refs` 已足以唯一标识其 EventLog source。

**判定**：PASS。无需额外字段。

---

## 3. 是否泄漏 LLM/schema/public surface 或形成 God proof

### 3.1 LLM projection 泄漏检查

amendment 明确声明："它只进入 Host-internal durable request/manifest，不进入 `CompactionRequest.llm_material_json()`、repair feedback LLM projection或 v2 output schema。"

**直接代码验证：**

1. `CompactionRequest.llm_material_json()`（`compaction.py:2239-2245`）调用 `self.compact_input.to_json()`，后者构建 `CompactInputV2`，只包含 `source_label`、`source_kind`、`source_refs`、`readable_text`——不含 provenance bridge。
2. `_repair_feedback_prompt_json_vnext`（`llm_compaction.py:680-703`）只投影 `required_action` 和 `issues`，不含 `request_digest`、`source_boundary_digest` 或任何 provenance 字段。
3. `CompactMaterialBlock.llm_json()`（`compaction.py:416-427`）剥离 `canonical_source_refs`、`content_digest`、`size_units`，只保留 `label`、`kind`、`text`、`source_labels`。

**判定**：PASS。三处 LLM-facing 投影均不包含 provenance bridge 字段。

### 3.2 God proof 检查

amendment 声明："该类型不是 public schema、compatibility wrapper、root-proof facade 或 God helper；它是 accepted plan 已要求的同源不变量所缺少的最小 canonical fact。"

检查：
- `SelectedBlockProvenance` 是 frozen dataclass，只有3个字段，无方法。
- 它不聚合其他职责，不提供 facade/helper 行为。
- 它只承载 source snapshot 到 material pack 的 identity binding fact。
- 它由 selector 从同一 `RunInputMaterialBlock` source snapshot 机械产生，不由外部注入或重算。

**判定**：PASS。不是 God proof。

---

## 4. same-text canonical identity 修复是否正确 owner

### 4.1 问题确认

`compact_material.py:2737-2751` 的 `_is_current_input_history_duplicate` 函数：

```python
def _is_current_input_history_duplicate(block: RunInputMaterialBlock, current_anchor: CurrentInputAnchor) -> bool:
    if block.section is not CompactMaterialSection.TRACE_MATERIAL:
        return False
    if block.kind is not CompactMaterialBlockKind.USER_INPUT:
        return False
    if current_anchor.canonical_source_refs[0] in block.canonical_source_refs:
        return True
    return block.content_digest == current_anchor.content_digest  # BUG
```

line 2751 的 `content_digest` 比较导致不同 canonical ref 但相同文本的历史 user block 被错误去重。

### 4.2 Owner 判定

`compact_material.py` 是 material pack 构建与 deduplication 的 owner。`_is_current_input_history_duplicate` 是 packer 内部的私有 helper，被 `_selected_material_blocks`（line 2731）调用。修复方向（删除 content_digest 比较行）在 owner 边界内。

### 4.3 修复正确性

amendment 要求："重复 input 身份只使用 canonical source identity；不得以相同业务文本把不同事实合并。"

修复后逻辑应为：

```python
def _is_current_input_history_duplicate(block: RunInputMaterialBlock, current_anchor: CurrentInputAnchor) -> bool:
    if block.section is not CompactMaterialSection.TRACE_MATERIAL:
        return False
    if block.kind is not CompactMaterialBlockKind.USER_INPUT:
        return False
    return current_anchor.canonical_source_refs[0] in block.canonical_source_refs
```

**验证**：
- 同 ref、同文本 → `True`（正确，同一事件的不同投影）。
- 同 ref、不同文本 → `True`（正确，同一事件的更新内容）。
- 不同 ref、同文本 → `False`（修复后正确，不同事件的独立事实）。
- 不同 ref、不同文本 → `False`（正确）。

**判定**：PASS。修复在正确 owner 边界，逻辑正确。

---

## 5. excluded_reason_codes mapping freeze 是否必要且最小

### 5.1 当前状态

`CompactSegmentSelection` 是 `frozen=True` dataclass（`compaction.py:1829`），`excluded_reason_codes` 类型为 `Mapping[str, str]`，默认值为 `dict()`（line 1858）。

`frozen=True` 阻止字段重新赋值，但不阻止 mutable dict 的内部 mutation。如果外部持有传入的 dict 引用，后续修改该 dict 会改变 `excluded_reason_codes` 的内容，但不会改变 `selection_digest`（因为 digest 在构造时已计算）。

### 5.2 必要性

`excluded_reason_codes` 是 selection digest 与 root proof 的组成部分（amendment Decision 3）。如果构造后 mutation 发生：
- `selection_digest` 不变（构造时已算）。
- `excluded_reason_codes` 内容改变。
- operation 的 provenance 匹配使用 `excluded_reason_codes` 做 selected/excluded 二分校验——mutation 可能破坏该不变量。

**判定**：freeze 是必要的。

### 5.3 最小性

amendment 方案：在 `__post_init__` 中复制并冻结 mapping。保持现有 `Mapping[str, str]` contract 与 canonical JSON 形状。

检查是否有更小方案：
- 方案 A：改为 `tuple[tuple[str, str], ...]`——改变类型 contract，不最小。
- 方案 B：改为 `types.MappingProxyType`——改变运行时类型，可能影响序列化。
- 方案 C：`__post_init__` 中 `dict(self.excluded_reason_codes)` 复制——最小，保持 `Mapping[str, str]` contract。

**判定**：PASS。方案 C 最小且充分。

### 5.4 测试要求

amendment 要求："测试断言外部原 mapping 后续变更和对字段直接变更均不能改变 selection 内容或 digest。"

**判定**：测试要求合理且充分。

---

## 6. Scope / 测试是否足够

### 6.1 Scope 检查

amendment Decision 4："保持既有 F10 production owner files 不变；新增/继续允许的测试仅为 `test_compaction_contract.py` 和 `test_public_compact_smoke.py`。它们只迁移双 digest strict contract 与验证 LLM 投影不泄漏治理 digest。新的 provenance/duplicate/immutability 测试仍优先落在原计划的 compact material、pipeline、operation owner suites。"

检查：
- production files 不变——`SelectedBlockProvenance` 类型定义在 `compaction.py`（已有 F10 allowed），`_is_current_input_history_duplicate` 修复在 `compact_material.py`（已有 F10 allowed），`excluded_reason_codes` freeze 在 `compaction.py`（已有 F10 allowed）。
- 测试分配合理：provenance/duplicate/immutability 测试归 owner suites，双 digest/LLM 隔离测试归 contract/smoke suites。

**判定**：PASS。scope 最小且 owner 归属正确。

### 6.2 测试充分性检查

amendment 要求的测试：
1. provenance binding 测试：unknown id / same-count swap / whole-group swap / ref-digest mismatch → fail closed。
2. same-text/different-ref 完整组断言。
3. `excluded_reason_codes` freeze 断言。
4. LLM 投影不泄漏 governance digest。

对照 accepted plan 测试矩阵（plan codex section 7）：
- F10 selector/item、selector/char、selector/prefix、selector/oversized-first、selector/protection、selector/identity、digest——已由 F10 implementation 覆盖。
- F10 pipeline/raw retention——已覆盖。
- F10 scheduler feedback binding——已覆盖。
- F10 operation direct mismatch、defensive mismatch、reactive partition、partial proof——已覆盖。
- F10 fallback owner——已覆盖。
- F10 integration——已覆盖。

amendment 新增的 provenance binding 测试是 plan matrix 中 "伪造 partial root selection proof"（plan codex line 332）的具体化。same-text 测试是 F10-FIND-002 的修复验证。freeze 测试是 Decision 3 的实现保障。

**判定**：PASS。测试覆盖充分。

---

## 7. 逐项 adversarial checklist 对照

| checklist 项（来自 plan codex section 11） | amendment 覆盖情况 | 判定 |
|---|---|---|
| group selector 把一个 group 计作一个 item | 不涉及（amendment 不改 selector） | N/A |
| selector 在大组放不下后跳过它选择更晚小组 | 不涉及 | N/A |
| oversized group 触发专用 signal / 新 cap / 拆分 / 删除 | 不涉及 | N/A |
| already-represented/protected 导致同组不同 disposition | 不涉及 | N/A |
| feedback 按 stage 名而非双 digest 绑定 | 不涉及（amendment 不改 feedback binding） | N/A |
| repair feedback 治理 digest 投影进 LLM prompt | Decision 1 明确禁止；代码验证通过（3.1 节） | PASS |
| reactive pass 因 root atomic contract 被错误禁止 | 不涉及 | N/A |
| operation guard 只验证 reduced tier boundary 而无 root group proof | Decision 1 新增 provenance binding 解决 | PASS |
| feedback mismatch 以异常逃逸 scheduler | 不涉及 | N/A |
| accepted artifact/Memory/Tool Trace/RunInput 各自重算同一事实 | 不涉及（amendment 不改单源投影） | N/A |

---

## 8. 总结

| 审查维度 | 结论 | 反例 |
|---|---|---|
| SelectedBlockProvenance 三字段充分性 | PASS | 无。`canonical_source_refs` + `content_digest` 组合防 same-count swap、group swap、同文本不同 ref swap。 |
| 遗漏 kind/section/labels | PASS | 无。这些是派生属性，不是 identity 字段。 |
| LLM/schema/public surface 泄漏 | PASS | 无。三处 LLM-facing 投影均不含 provenance bridge。 |
| God proof | PASS | 无。最小 frozen dataclass，无 facade/helper 行为。 |
| same-text canonical identity 修复 owner | PASS | 无。`compact_material.py` 是 deduplication owner，修复逻辑正确。 |
| excluded_reason_codes freeze 必要性与最小性 | PASS | 无。`__post_init__` copy-and-freeze 是最小方案。 |
| Scope / 测试充分性 | PASS | 无。owner 归属正确，覆盖充分。 |

**最终结论：PASS。无需修复项。**

---

## 9. 实施注意事项（非 NEEDS_FIX，仅供参考）

以下不构成 NEEDS_FIX，但实施时需注意：

1. **SelectedBlockProvenance 的 operation 验证逻辑**：amendment 只描述了类型和约束，未给出 operation 的具体匹配算法。实施时需明确：是按 `canonical_source_refs` 做 set equality 匹配，还是按 position-by-position 顺序匹配。建议采用 refs set equality + digest equality 的双重校验，避免依赖 pack 的内部排序。

2. **`excluded_reason_codes` freeze 的 `__post_init__` 实现**：需注意 `frozen=True` dataclass 的 `__post_init__` 中不能直接赋值（`object.__setattr__` 模式），但 `excluded_reason_codes` 是引用字段，只需确保传入的是 copy 即可。建议在 `__post_init__` 中使用 `object.__setattr__(self, 'excluded_reason_codes', dict(self.excluded_reason_codes))`。

3. **same-text 修复的边界条件**：删除 `content_digest` 比较后，如果同一 EventLog event 被重复投影（理论上不应发生，但如果有 bug），canonical ref 相同的重复会被正确去重。如果不同 event 恰好产生相同文本（如模板化回复），它们会被视为独立事实——这是正确行为，符合"不同事件是不同事实"的语义。
