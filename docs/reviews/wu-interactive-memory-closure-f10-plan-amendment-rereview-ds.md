# Interactive Conversation Memory closure F10：Plan Amendment Re-review（DS 第二路）

- **Review target**: 当前 working tree 所有 F10 amendment 相关改动（`dayu/host/compact_material.py`, `compaction.py`, `compaction_operation.py`, `compact_pipeline.py`, `context_governance.py`, `dispatch.py` 及对应测试）
- **对照基准**: `docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-controller.md`（总控裁决）与 `docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-fix-controller.md`（fix disposition）
- **Review type**: 第二路 DS adversarial re-review，逐项验证 F1–F4 关闭状态并检查是否引入新问题
- **Timestamp**: 2026-08-04

---

## 总览

本次 implementation 采用了一条**与总控裁决不同的实现路径**。总控裁决要求新增 `SelectedBlockProvenance` 类型做 per-block provenance bridge，并要求 packer 彻底移除历史/当前输入 dedup、`__post_init__` 中做 excluded mapping 的 sorted copy+freeze。实际 implementation 未添加 `SelectedBlockProvenance`，而是通过 `TurnGroupMembership` + `CompactSegmentSelectionScope` + group-level collective exclusion + count/label-order validation + 双 digest feedback binding 来加固 root/transient boundary。

这导致 F1–F4 的关闭判定不能简单用"是否按总控字面实现"来衡量——需要用"原 finding 指出的 correctness gap 是否已通过替代路径消除"来重新判定。

---

## F1 逐项验证：evidence content_digest 在 RunInputMaterialBlock 与 CompactEvidenceBlock 间不一致

### 原 finding 回顾

`RunInputMaterialBlock.content_digest` 对 evidence block 计算四行完整 evidence render 的 hash（`compact_material.py:786`），而 `CompactEvidenceBlock.content_digest` 只取 `material.result_text` 的 hash（`compact_material.py:2830`）。若 `SelectedBlockProvenance.content_digest` 取自前者，则与后者无法精确匹配，导致 evidence block 的 provenance 验证全部 fail closed。

### 当前代码状态

**`SelectedBlockProvenance` 类型未被实现。** 搜索 `packed_content_digest`、`SelectedBlockProvenance` 在整个代码库中均无结果。当前 operation 的 root validation（`_validate_operation_root_request`, `compaction_operation.py:1539-1580`）使用：
- selected_block_ids count vs material_pack count 比较
- pack_labels vs source_boundary labels 顺序比较
- turn_group_memberships 与 excluded_reason_codes 的二分满射检查

**不做 per-block content_digest 精确匹配。** 因此 F1 所指的"digest 不匹配导致正确 block 被误杀"场景在当前代码路径中不存在。

### 但存在一个相关的新增不一致

`_provenance_from_evidence_blocks`（`compact_material.py:2890`）构造 `PromptLocalProvenanceEntry` 时使用 `source.content_digest`（来自 `RunInputMaterialBlock`，即四行 render 的 hash），而 `_pack_evidence_blocks`（`compact_material.py:2830`）构造 `CompactEvidenceBlock` 时使用 `_text_digest(material.result_text)`（仅 result_text 的 hash）。两者对同一 evidence block 产生不同的 `content_digest` 值，存储在 `provenance_map` 与 `CompactEvidenceBlock` 中。

**当前影响**：`PromptLocalProvenanceEntry.content_digest` 在现有代码中不用于 validation gate，仅作为 provenance map 的元数据。因此这是一个 **latent inconsistency**，不是 correctness bug。但若未来任何代码路径以 `provenance_map` 中的 `content_digest` 与 `CompactEvidenceBlock.content_digest` 做匹配，将立即暴露为 fail-closed bug。

**违反总控裁决**：总控明确要求 "同一 helper 同时供 provenance producer 与 pack builder 使用，禁止两处各自重算不同语义"。当前代码 `_provenance_from_evidence_blocks:2890` 与 `_pack_evidence_blocks:2830` 使用了不同数据源计算 digest，违反了此要求。

### F1 判定：**部分关闭 / 新 latent risk 引入**

原 finding 的 correctness gap（per-block digest 匹配 fail-closed）因未实施 SelectedBlockProvenance 而暂不触发。但 `_provenance_from_evidence_blocks` 与 `_pack_evidence_blocks` 间的 digest 来源不一致是新引入的 latent inconsistency，违反总控的 "同一 helper" 要求。**列为新 finding N1。**

---

## F2 逐项验证：transient selection provenance subset 验证位置未明确

### 原 finding 回顾

Plan amendment 描述了 "transient pass 取 root proof 子集" 的意图，但未指定验证发生在哪个函数、用哪个 assertion。实施 Agent 可能遗漏此验证，导致 transient pass 携带伪造 provenance 仍通过验收。

### 当前代码状态

**已实现的验证：**

1. `_single_block_segment_selection`（`compact_pipeline.py:1029-1062`）：transient selection 的 `scope=TRANSIENT`，`root_selection_digest` 绑定 root 的 `selection_digest`，`turn_group_memberships` 从 root 复制。digest 输入包含 `root_selection_digest` 和完整的 `turn_group_memberships`——这些作为 transient selection 的不可变 binding。

2. `_operation_pass_requests`（`compaction_operation.py:1519-1536`）：验证每个 pass request 的 scope 为 TRANSIENT、`root_selection_digest` 与 root `selection_digest` 匹配、`turn_group_memberships` 与 root 完全一致、source boundary 为 root boundary 的 disjoint exact partition。

3. `_validate_segment_against_source_snapshot`（`compact_pipeline.py:966-996`）：验证 selected/excluded ids 在 snapshot 中、turn_group_memberships 与 snapshot 一致、root scope 的 partition 完整性、transient scope 的 root_selection_digest 非空。

**未实现的验证：**

1. `_operation_pass_requests` 不验证 transient `selected_block_ids` 是 root `selected_block_ids` 的子集（按 block_id 匹配）。只验证 `root_selection_digest` 绑定和 `turn_group_memberships` 一致。

2. `_single_block_segment_selection` 不验证传入的 `block_id` 在 root 的 `selected_block_ids` 中。它只检查 `block_id` 在 material_blocks 中存在（line 1029）。

3. `_validate_segment_against_source_snapshot` 对 transient scope 不验证 `selected_ids.issubset(root_selected_ids)`。

**反例**：若调用方传入一个 root `selected_block_ids` 中不存在的 block_id 给 `_single_block_segment_selection`，transient selection 会成功构造——其 `root_selection_digest` 正确绑定、`turn_group_memberships` 与 root 一致，但 `selected_block_ids=(phantom_id,)` 不在 root 的 selected 集合中。`_operation_pass_requests` 的 turn_group_memberships 检查通过（因为 phantom_id 属于某个 group 的 member，该 group 在 root 中可能整体 selected 或整体 excluded——但若 phantom group 在 root 中是 excluded 的，transient 却声称 selected，validation 不会捕获）。

**wait，进一步分析**：若 `phantom_id` 属于一个在 root 中被 excluded 的 group，`_operation_pass_requests` 的 `turn_group_memberships` 匹配仍通过（因为 membership 结构相同，只是 root 的 selection disposition 不同）。但 transient 的 `source_boundary` 只会包含这一个 block——与 root 的 source_boundary 做 disjoint exact partition 检查时会如何？

`_operation_pass_requests:1532-1535` 检查 pass boundary entries 的 label 集合等于 root boundary entries 的 label 集合（disjoint exact partition）。若 phantom block 在 root 中有一个 label（它在 root 的 material_pack 中），则 label 集合匹配通过。但 phantom block 在 root 的 `selected_block_ids` 中不存在——这个事实不被检查。

**结论**：存在一个可以通过的 transient block 伪造路径：用一个在 root material 中存在但未被 root selected 的 block_id 构造 transient selection。所有现有 validation 均通过，但 semantic 上 transient 携带了 root 未授权的 block。

### F2 判定：**未完全关闭**

Transient proof 的 `root_selection_digest` binding 和 `turn_group_memberships` 复制是正确的结构性加固，但缺少 per-block subset 验证。总控裁决明确要求 "逐 pass 验证 transient provenance 是 root provenance 的精确子集：block id 存在于 root"。当前代码未实现此验证。**列为遗留 gap R1。**

---

## F3 逐项验证：excluded_reason_codes digest 与 constructor 值可能因排序不一致

### 原 finding 回顾

`select_compact_segment` 的 digest_input 使用 `_ordered_reason_mapping(excluded_reasons)`（key-sorted），但 constructor 传入原始 `excluded_reasons`（insertion-ordered dict）。`to_json()` 的序列化顺序可能与 digest 计算时的 sorted 顺序不同。

### 当前代码状态

1. **digest 计算**：`select_compact_segment:904` 使用 `_ordered_reason_mapping(excluded_reasons)`（按 key 排序返回新 dict）。
2. **to_json 序列化**：`CompactSegmentSelection.to_json():1951` 调用 `_string_mapping_json(self.excluded_reason_codes)`，该函数（`compaction.py:3099-3109`）也按 key 排序输出。
3. **存储值**：`excluded_reason_codes` 字段存储的是 constructor 传入的原始 dict（`select_compact_segment:923` 传入 `excluded_reason_codes=excluded_reasons`），**未排序、未复制**。
4. **`__post_init__`**：`CompactSegmentSelection.__post_init__:1860-1932` 验证了 `excluded_reason_codes` 的类型、selected/excluded 互斥、protected ⊆ excluded、root group 二分，但**不做 sorted copy、不做 freeze**。

### 分析

- digest 与 `to_json()` 的序列化一致性：两者都按 key 排序 → **一致**。F3 的原始反例（digest 与 serialization 不同）已通过 `_string_mapping_json` 的内部排序规避。
- 外部 mutation 风险：`frozen=True` dataclass 阻止字段重新赋值，但 `excluded_reason_codes` 是 `Mapping[str, str]`，若构造时传入的原始 dict 被外部持有并修改，selection 内容会漂移而 `selection_digest` 不变。
  - 实际风险：`select_compact_segment` 中 `excluded_reasons` 是函数内局部变量，构造后不再被外部持有。`initial_segment_selection` 同理。**当前调用路径下外部 mutation 不可达。**
  - 但类型契约不防御：任何新调用方若在构造后继续持有并修改传入的 dict，将破坏不变量。
- 总控裁决要求 "`__post_init__` 先 stable key sort copy 再冻结"——**未实现**。

### F3 判定：**部分关闭**

digest/to_json 一致性已通过两处均排序来保证。外部 mutation 在当前调用路径下不可达，但类型契约缺少 copy+sort+freeze 的防御层，不符合总控的防御性设计要求。**列为遗留 gap R2。**

---

## F4 逐项验证：same-text dedup 修复后 packer 仍可能静默丢弃 selected group member

### 原 finding 回顾

删除 content_digest fallback 后，canonical ref 路径下的 group member 保护语义不清晰。plan 可能被误解为连 canonical ref 相同的重复也不能删除。

### 总控裁决要求

> packer 不再拥有 selected history/current-input dedup：`_selected_material_blocks` 对 selector 已选 block 必须一项不漏地投影，不得 `continue` 删除任何 group member。不得因 content digest 相同而删除 canonical refs 不同的历史 user input。若 source snapshot 意外让与 current input anchor 相同 canonical ref 的 history block 进入 selected boundary，pipeline source/request validation 必须在 pack/provider 前 fail closed。

### 当前代码状态

**`_is_current_input_history_duplicate`（`compact_material.py:2737-2751`）未修改：**

```python
def _is_current_input_history_duplicate(block, current_anchor):
    if block.section is not CompactMaterialSection.TRACE_MATERIAL:
        return False
    if block.kind is not CompactMaterialBlockKind.USER_INPUT:
        return False
    if current_anchor.canonical_source_refs[0] in block.canonical_source_refs:
        return True
    return block.content_digest == current_anchor.content_digest  # ← 仍在
```

**`_selected_material_blocks`（`compact_material.py:2731-2733`）仍在 skip：**

```python
if _is_current_input_history_duplicate(block, current_anchor):
    continue  # ← 仍在跳过 selected block
```

**Pipeline 验证**：`_validate_segment_against_source_snapshot` 检查 block partition 和 group membership，但**不专门检查 same-canonical-ref 的 current/history 冲突**。

### 分析

1. **content_digest fallback 仍在**：line 2751 的 `block.content_digest == current_anchor.content_digest` 比较未被删除。不同 canonical refs 但相同文本的历史 user block 仍会被错误去重。

2. **packer 仍在静默删除 selected block**：line 2732 的 `continue` 未被移除。若 dedup 触发，selected block 从 pack 中消失，导致 `_validate_operation_root_request` 的 count 检查失败（`len(selected_block_ids) ≠ selected_material_count`）→ non-repairable failure。

3. **fail-closed 路径存在但不够早**：count mismatch 在 operation 入口（provider 前）被 `_validate_operation_root_request` 捕获，阻止 durable accept。但这发生在 material pack 已构造完成后，且错误原因是 count mismatch 而非明确的 "same-ref duplicate in selection"——诊断精度降低。

4. **总控的两条要求均未满足**：
   - "packer 不得 continue 删除任何 group member" → **未实现**
   - "不得因 content digest 相同而删除 canonical refs 不同的历史 user input" → **未实现**

### F4 判定：**未关闭**

这是四个 finding 中最明确的未关闭项。`_is_current_input_history_duplicate` 的 content_digest fallback 是原 review 指出的 correctness bug，总控明确要求修复，但代码未改动。测试中亦无 same-text/different-ref 的完整组保留测试（总控要求的新增 owner test）。

---

## 新增问题检查

### N1（中）：evidence provenance content_digest 来源不一致

- **位置**：`compact_material.py:2890` vs `compact_material.py:2830`
- **问题**：`_provenance_from_evidence_blocks` 使用 `source.content_digest`（四行 evidence render hash），`_pack_evidence_blocks` 使用 `_text_digest(material.result_text)`（仅 result_text hash）。同一 evidence block 在 provenance map 与 CompactEvidenceBlock 中有不同的 content_digest。
- **影响**：当前不触发 correctness bug（provenance_map 的 content_digest 不参与 validation gate），但违反总控 "同一 helper 同时供 producer 与 packer 使用" 的要求。若未来代码使用 provenance_map.content_digest 做匹配，将 fail closed。
- **建议**：统一为 `_text_digest(material.result_text)`，或抽取单一 helper 供两处使用。

### N2（低）：transient selection 缺少 per-block subset 验证

- **位置**：`compaction_operation.py:1519-1536`、`compact_pipeline.py:1029-1062`
- **问题**：`_operation_pass_requests` 不验证 transient `selected_block_ids ⊆ root.selected_block_ids`；`_single_block_segment_selection` 不验证 `block_id ∈ root.selected_block_ids`。
- **影响**：可构造一个 transient selection，其 block_id 在 root material 中存在但未被 root selector 选中。所有现有 structural validation 通过，但 semantic 不正确。
- **建议**：在 `_single_block_segment_selection` 中增加 `block_id in root_request.segment_selection.selected_block_ids` 检查；在 `_operation_pass_requests` 中增加 `set(pass_selected).issubset(root_selected)` 检查。

### N3（低）：`_validate_segment_against_source_snapshot` 对 transient 的验证不完整

- **位置**：`compact_pipeline.py:991-996`
- **问题**：对 transient scope 只检查 `root_selection_digest is not None`，不检查 transient selected_ids 与 root selected_ids 的关系。
- **建议**：增加 root_selected_ids 参数或交叉验证。

### N4（信息）：`initial_segment_selection` 的 `excluded_reason_codes` 在 root 构造后不再有外部引用

- **位置**：`compact_material.py:1378-1418`
- **观察**：`excluded_reasons` 是函数内局部 dict，传参后不再被持有。外部 mutation 风险在调用路径上不可达。但若未来重构使该 dict 被外部持有，风险暴露。R2 已覆盖。

### N5（信息）：`CompactRepairFeedbackV2` 新增 `request_digest`/`source_boundary_digest` 字段正确且 LLM 投影不泄漏

- **位置**：`compaction.py:1638-1698`、`llm_compaction.py` 相关
- **验证**：`_repair_feedback_prompt_json_vnext` 输出中 `assert "request_digest" not in projected` 和 `assert "source_boundary_digest" not in projected`（`test_llm_compaction.py` 新增断言）→ LLM-facing 投影不泄漏治理 digest。**PASS。**

---

## 逐项 checklist 对照

| 总控裁决要求 | 实现状态 | 判定 |
|---|---|---|
| Decision 1: `SelectedBlockProvenance` 类型 | **未实现** | 替代方案：group-level + count + label-order，无 per-block digest 匹配 |
| Decision 1: `packed_content_digest` 单一 helper | **未实现** | N1: evidence 路径两处 digest 来源不一致 |
| Decision 1: pipeline 验证 proof | 部分实现 | `_validate_segment_against_source_snapshot` 验证 group/partition，不验证 per-block provenance |
| Decision 1: operation provider/accept 前精确一一匹配 | 部分实现 | count + label-order 匹配，无 per-block refs/digest 匹配 |
| Decision 1: unknown id/swap/group swap → fail closed | 部分实现 | count mismatch → fail closed ✓；same-count swap 不检测 ✗ |
| Decision 2: packer 不再 dedup selected block | **未实现** | `_is_current_input_history_duplicate` + `continue` 仍在 |
| Decision 2: 删除 content_digest fallback | **未实现** | `compact_material.py:2751` 仍在 |
| Decision 2: same-ref → pipeline fail closed | 未实现 | pipeline 不专门检查此条件 |
| Decision 3: `__post_init__` sorted copy + freeze | **未实现** | digest/to_json 均排序（规避），但无 copy+freeze |
| Decision 3: 外部 mutation 不能改变 selection | 脆弱 | 当前调用路径安全，类型契约不防御 |
| Decision 4: Scope amendment | **已实现** | contract/smoke 测试迁移 feedback digest ✓ |
| 禁止: LLM-facing 泄漏 governance digest | **已实现** | 测试断言 `request_digest`/`source_boundary_digest` 不在 LLM prompt 中 ✓ |
| 禁止: 修改 v2 schema/Memory/RunInput | **遵守** | 未修改 ✓ |

---

## 测试覆盖评估

### 已覆盖

- `TurnGroupMembership` 构造、序列化、唯一性校验 ✓
- `CompactSegmentSelectionScope` ROOT/TRANSIENT 区分 ✓
- Group-level collective exclusion（全选/全排、原子性、precedence） ✓
- `selection_digest` 随 group partition 变化 ✓
- Root contract 拒绝 partial turn group ✓
- Transient 的 scope/root_selection_digest/turn_group_memberships 绑定 ✓
- Feedback 双 digest binding ✓
- Feedback mismatch → non-repairable ✓
- Root boundary mismatch → non-repairable ✓
- Dispatcher feedback 清理与 defensive guard ✓
- LLM 投影不泄漏 governance digest ✓

### 未覆盖（对应未关闭 finding）

- same-text/different-ref 完整组保留测试（总控 F4 新增要求） ✗
- same-canonical-ref current → pipeline fail closed 测试 ✗
- transient per-block subset 验证测试 ✗
- `excluded_reason_codes` 外部 mutation 不变性测试 ✗

---

## Residual Risks

1. **same-count swap 不检测**：若 attacker 将 root selected 中的一个 block 替换为另一个 block（相同 count），current operation 的 count + label-order 验证均通过（label 是 packer 按 ordinal 分配的，与 block identity 无关）。只有 `turn_group_memberships` 中的 member_block_ids 能间接暴露——如果替换导致 group 的 member 集合变化，且该 group 在 root 中是 selected 的，才会在 `_validate_operation_root_request` 的 group partition 检查（line 1924-1928，已在 `__post_init__` 中）暴露。但若替换发生在 singleton block（无 group），则无防御。

2. **content_digest fallback 持续存在**：任何与 current input 文本相同的历史 user input 将被 packer 静默删除——无论 canonical ref 是否相同。这是 F4 指出的 correctness bug，仍在代码中。

3. **provenance_map 的 evidence content_digest 不一致**：latent risk，不在当前 validation path 上触发。

---

## Final Conclusion

**NEEDS_FIX**

F4（same-text dedup）是明确的未关闭 correctness bug：`_is_current_input_history_duplicate` 的 content_digest fallback（`compact_material.py:2751`）未被删除，packer 仍可能因相同文本而错误删除不同 canonical ref 的历史 user block。这是总控裁决 Decision 2 的**直接违反**，且修复成本极低（删除一行 + 添加 pipeline 验证或直接移除 packer dedup）。

F2/F3 为部分关闭：核心结构性加固已到位（root_selection_digest binding、turn_group_memberships、双 digest feedback），但 per-block subset 验证和 `__post_init__` copy+freeze 缺失，属于 defense-in-depth gap，可在不改变产品语义的前提下补齐。

F1 因实施路径变更而变为 moot——`SelectedBlockProvenance` 未实现，因此原 finding 的 per-block digest mismatch fail-closed 场景不存在。但 evidence provenance content_digest 的不一致（N1）是新增 latent risk，同样需要在 producer/packer 之间统一 digest 来源。

**建议修复优先级**：
1. **F4**（高）：删除 `compact_material.py:2751` 的 content_digest fallback；考虑一并移除 `_is_current_input_history_duplicate` 的 `continue` skip（改为在 pipeline 中 fail closed）
2. **N1**（中）：统一 `_provenance_from_evidence_blocks:2890` 与 `_pack_evidence_blocks:2830` 的 digest 来源
3. **F2/N2**（中）：在 `_single_block_segment_selection` 和 `_operation_pass_requests` 中增加 per-block subset 检查
4. **F3/R2**（低）：在 `__post_init__` 中增加 sorted copy（当前调用路径下外部 mutation 不可达，属防御性加固）
