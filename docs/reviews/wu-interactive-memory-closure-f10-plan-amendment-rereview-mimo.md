# Interactive Conversation Memory closure F10：Plan amendment re-review（MiMo）

## Gate

- Review 类型：plan amendment re-review，针对 fix controller 修订后的 amendment。
- 审查目标：`docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-fix-controller.md`。
- 对照材料：首次 MiMo review（`wu-interactive-memory-closure-f10-plan-amendment-review-mimo.md`）、DS review（`wu-interactive-memory-closure-f10-plan-amendment-review-ds.md`）、controller 裁决（`wu-interactive-memory-closure-f10-plan-amendment-controller.md`）、当前 production code。
- 结论：**NEEDS_FIX**。发现 1 个高严重度可执行性问题。

---

## 审查范围

本次 re-review 重点验证 fix controller 对 DS 四个 finding 的修订是否完整且可执行：

1. **F1 accepted**：`packed_content_digest` 单一 helper 是否可执行
2. **F2 accepted**：transient exact subset 验证是否完整且最小
3. **F3 accepted**：mapping sorted freeze 是否完整且最小
4. **F4 accepted**：packer 不 dedup + pipeline same-ref failclosed 是否完整且最小

---

## 1. packed_content_digest 单一 helper 可执行性审查

### 1.1 Fix controller 修订内容

> provenance字段改为 `packed_content_digest`；由 compact-material 单一 helper 按最终 pack 语义派生，accepted evidence 使用 `result_text` digest；producer 与 packer 复用同一 helper。

### 1.2 当前代码事实

**`RunInputMaterialBlock.content_digest` 构造路径**（`compact_material.py:180-230`）：

- `content_digest` 是 `RunInputMaterialBlock` 的直接字段，由外部构造时传入。
- 对于 evidence block，构造路径在 `build_material_blocks` 系列函数中，使用 `_text_digest(material_text)`，其中 `material_text = render_accepted_tool_evidence_for_llm(material)`（四行完整 evidence 文本）。

**`CompactEvidenceBlock.content_digest` 构造路径**（`compact_material.py:2807-2836`）：

```python
CompactEvidenceBlock(
    ...
    content_digest=_text_digest(material.result_text),  # 只有 result_text
)
```

**`_provenance_from_blocks` 函数**（`compact_material.py:2839-2860`）：

```python
def _provenance_from_blocks(blocks: tuple[CompactMaterialBlock, ...]) -> tuple[PromptLocalProvenanceEntry, ...]:
    return tuple(
        PromptLocalProvenanceEntry(
            ...
            content_digest=block.content_digest,  # 直接使用 block 的 digest
            ...
        )
        for block in blocks
    )
```

### 1.3 可执行性分析

**问题**：fix 要求"同一 helper 同时供 provenance producer 与 pack builder 使用"，但当前代码中不存在这样的单一 helper。

- `_provenance_from_blocks` 直接使用 `block.content_digest`（来自 `CompactMaterialBlock`/`CompactEvidenceBlock`）。
- `_pack_evidence_blocks` 使用 `_text_digest(material.result_text)` 构造 `CompactEvidenceBlock`。
- 两者的 digest 来源不同，且没有共享的 helper 函数。

**fix 的意图**：provenance producer 和 pack builder 应该使用同一个函数来计算 evidence block 的 `packed_content_digest`，确保 producer 声明的 digest 与 pack 中实际 block 的 digest 一致。

**当前状态**：fix 只描述了意图，没有指定 helper 的签名、位置或调用点。实施 Agent 需要：
1. 创建一个新 helper（如 `_evidence_packed_content_digest(material: AcceptedToolEvidenceLLMMaterial) -> str`）
2. 在 `_pack_evidence_blocks` 中使用该 helper
3. 在 `RunInputMaterialBlock` 构造 evidence block 时使用该 helper（或在 provenance producer 中使用）

**风险**：如果实施 Agent 不创建单一 helper，而是分别在两处调用 `_text_digest`，可能仍然使用不同输入（一处用 `result_text`，一处用四行 render），导致 provenance 声明的 digest 与 pack 中 block 的 digest 不一致。

### 1.4 结论

**NEEDS_FIX**。fix 的意图正确，但缺乏可执行的规格。需要明确：
- helper 的签名和位置
- 哪些调用点必须使用该 helper
- 如何验证 producer 和 packer 使用同一 digest

---

## 2. transient exact subset 验证完整性审查

### 2.1 Fix controller 修订内容

> 明确 `_single_block_segment_selection` 只能取 root entry；`_operation_pass_requests` 验证每个 pass 是 root proof 精确子集且合并后无重叠/遗漏，每个 pass 在 provider 前再与自身 pack 比对。

### 2.2 当前代码事实

**`_operation_pass_requests` 函数**（`compaction_operation.py:1495-1536`）：

当前验证：
- request identity 一致（trigger_source, session_id, run_id, attempt_id, execution_id）
- selection scope 是 transient
- root_selection_digest 匹配
- turn_group_memberships 匹配
- current_input 匹配
- boundaries 是 disjoint exact partition（by label）

**不验证**：
- per-block provenance subset（block_id, canonical_source_refs, packed_content_digest）
- pass provenance 与 root provenance 的逐字段相等

### 2.3 完整性分析

fix 要求在 `_operation_pass_requests` 中验证：
1. 每个 transient pass 的 `selected_block_provenance` 是 root `selected_block_provenance` 的子集
2. 按 block_id 匹配，且 matching entry 的 canonical_source_refs 和 packed_content_digest 完全相同
3. 所有 pass 合并后对 root selected proof 无重叠、无遗漏
4. 每个 pass 在 provider 前再与自身 pack 比对

**当前代码缺失**：
- `CompactSegmentSelection` 没有 `selected_block_provenance` 字段
- `_operation_pass_requests` 不检查 per-block provenance
- provider 前的 pack 比对逻辑不存在

### 2.4 最小性分析

fix 的描述是完整的：
- 验证位置：`_operation_pass_requests`（pass queue 入口）+ provider 前（单 pass 入口）
- 验证内容：block_id 存在性 + refs/digest 逐字段相等 + 无重叠无遗漏
- 测试覆盖：unknown block_id / 篡改 refs/digest 场景

**判定**：fix 描述完整且最小，但需要 `selected_block_provenance` 字段先存在于 `CompactSegmentSelection` 中（由 Decision 1 定义）。

### 2.5 结论

**PASS**。fix 描述完整且最小，可直接实施。

---

## 3. mapping sorted freeze 完整性审查

### 3.1 Fix controller 修订内容

> `__post_init__` 先 stable key sort copy 再冻结；stored mapping、`to_json()` 和 digest 使用同一 canonical order，新增 insertion-order 反例。

### 3.2 当前代码事实

**`select_compact_segment` 函数**（`compact_material.py:898-930`）：

```python
digest_input = {
    ...
    "excluded_reason_codes": _ordered_reason_mapping(excluded_reasons),  # sorted
    ...
}
return CompactSegmentSelection(
    ...
    excluded_reason_codes=excluded_reasons,  # 原始 insertion order
)
```

**`_ordered_reason_mapping` 函数**（`compact_material.py:2008-2016`）：

```python
def _ordered_reason_mapping(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in sorted(values)}
```

**`CompactSegmentSelection.__post_init__`**（`compaction.py:1862-1930`）：

当前不对 `excluded_reason_codes` 做排序或冻结。只做类型校验和 disjoint 检查。

**`CompactSegmentSelection.to_json`**（`compaction.py:1940-1960`）：

```python
"excluded_reason_codes": _string_mapping_json(self.excluded_reason_codes),  # 使用存储的顺序
```

### 3.3 完整性分析

**问题**：`select_compact_segment` 在 digest_input 中使用 `_ordered_reason_mapping(excluded_reasons)`（已排序），但构造 `CompactSegmentSelection` 时传入原始 `excluded_reasons`（insertion order）。

- digest 计算使用 sorted order
- 构造存储使用原始 order
- `to_json()` 使用存储的 order

如果 `excluded_reasons` 以不同 key 顺序构造（如 `{"B":"reason","A":"reason"}`），digest 计算时排序为 `{"A":"reason","B":"reason"}`，但存储和序列化使用原始 `{"B":"reason","A":"reason"}`。

**fix 要求**：`__post_init__` 先 stable key sort copy 再冻结。

**当前代码缺失**：
- `__post_init__` 不对 `excluded_reason_codes` 排序
- 没有 freeze 逻辑（只做校验，不修改字段值）

### 3.4 最小性分析

fix 的描述是完整的：
- 排序时机：`__post_init__`（构造后立即）
- 排序方式：`dict(sorted(self.excluded_reason_codes.items()))`
- 冻结方式：`frozen=True` dataclass 的 `__post_init__` 中使用 `object.__setattr__`
- 测试覆盖：不同 insertion order → 相同 stored order / JSON / digest

**判定**：fix 描述完整且最小，可直接实施。

### 3.5 结论

**PASS**。fix 描述完整且最小，可直接实施。

---

## 4. packer 不 dedup + pipeline same-ref failclosed 完整性审查

### 4.1 Fix controller 修订内容

> packer 不再静默 dedup 任何 selected block；same-text/different-ref 完整保留；same canonical current ref 是 source/request invariant violation，在 pipeline/provider 前 fail closed。

### 4.2 当前代码事实

**`_is_current_input_history_duplicate` 函数**（`compact_material.py:2737-2751`）：

```python
def _is_current_input_history_duplicate(block: RunInputMaterialBlock, current_anchor: CurrentInputAnchor) -> bool:
    if block.section is not CompactMaterialSection.TRACE_MATERIAL:
        return False
    if block.kind is not CompactMaterialBlockKind.USER_INPUT:
        return False
    if current_anchor.canonical_source_refs[0] in block.canonical_source_refs:
        return True
    return block.content_digest == current_anchor.content_digest  # BUG: content_digest fallback
```

**`_selected_material_blocks` 调用点**（`compact_material.py:2731`）：

```python
if _is_current_input_history_duplicate(block, current_anchor):
    continue  # 跳过 block
```

### 4.3 完整性分析

fix 要求：
1. 删除 `content_digest` fallback（line 2751）
2. packer 不再静默 dedup 任何 selected block
3. same canonical current ref 是 source/request invariant violation，在 pipeline/provider 前 fail closed

**当前代码问题**：
- line 2751 的 `content_digest` fallback 会导致不同 canonical ref 但相同文本的历史 user block 被错误去重
- 删除 fallback 后，`_is_current_input_history_duplicate` 只剩 canonical ref check

**fix 的两种 dedup 语义**：
1. **canonical ref 相同**（同源）：应 dedup，但这是 source/request invariant violation，应在 pipeline/provider 前 fail closed，而不是在 packer 中静默删除
2. **content_digest 相同但 ref 不同**（不同源）：不应 dedup，应完整保留

**fix 的意图**：
- 删除 content_digest fallback → 不同源的同文本 block 不再被错误去重
- same canonical ref 是 invariant violation → 在 pipeline/provider 前 fail closed，不在 packer 中静默删除

**当前代码缺失**：
- line 2751 仍然存在（content_digest fallback 未删除）
- 没有 pipeline/provider 前的 same-ref fail closed 逻辑

### 4.4 最小性分析

fix 的描述是完整的：
- 删除 content_digest fallback → 修改 `_is_current_input_history_duplicate` 函数
- same-ref fail closed → 在 pipeline source/request validation 中检查，或在 provider 前检查
- 测试覆盖：same-text/different-ref 完整组断言 + same-canonical-ref fail closed

**判定**：fix 描述完整且最小，可直接实施。

### 4.5 结论

**PASS**。fix 描述完整且最小，可直接实施。

---

## 5. 交叉验证：fix 是否完整覆盖 DS 四个 finding

| DS Finding | Fix Controller 修订 | Re-review 结论 |
|---|---|---|
| F1: evidence digest 与 RunInput digest 不同源 | provenance 字段改为 `packed_content_digest`；单一 helper | **NEEDS_FIX**：单一 helper 缺乏可执行规格 |
| F2: transient proof subset 验证位置不清 | 明确 `_operation_pass_requests` 验证 + provider 前比对 | **PASS** |
| F3: excluded mapping 排序与 digest 可能不一致 | `__post_init__` 先 stable key sort copy 再冻结 | **PASS** |
| F4: same-ref 与 same-text dedup 边界 | packer 不再静默 dedup；same-ref fail closed | **PASS** |

---

## 6. 逐项 adversarial checklist 对照

| checklist 项（来自 plan amendment Decision 1） | fix 覆盖情况 | 判定 |
|---|---|---|
| `packed_content_digest` 非空且与最终 pack block 的 existing `content_digest` 同源 | fix 要求单一 helper，但未指定 helper 签名 | **NEEDS_FIX** |
| 同一 helper 同时供 provenance producer 与 pack builder 使用 | fix 描述意图，但未指定调用点 | **NEEDS_FIX** |
| 禁止两处各自重算不同语义 | fix 描述意图，但缺乏 enforcement 机制 | **NEEDS_FIX** |
| `_single_block_segment_selection` 只能取 root entry | fix 明确 | **PASS** |
| `_operation_pass_requests` 验证每个 pass 是 root proof 精确子集 | fix 明确 | **PASS** |
| 所有 pass 合并后对 root selected proof 无重叠、无遗漏 | fix 明确 | **PASS** |
| 每个 pass 在 provider 前再与自身 pack 比对 | fix 明确 | **PASS** |
| `__post_init__` 先 stable key sort copy 再冻结 | fix 明确 | **PASS** |
| stored mapping、`to_json()` 和 digest 使用同一 canonical order | fix 明确 | **PASS** |
| packer 不再静默 dedup 任何 selected block | fix 明确 | **PASS** |
| same canonical current ref 是 source/request invariant violation | fix 明确 | **PASS** |
| pipeline/provider 前 fail closed | fix 明确 | **PASS** |

---

## 7. 总结

| 审查维度 | 结论 | 反例 |
|---|---|---|
| `packed_content_digest` 单一 helper 可执行性 | **NEEDS_FIX** | fix 只描述意图，未指定 helper 签名、位置或调用点；实施 Agent 可能分别在两处调用 `_text_digest` 但使用不同输入 |
| transient exact subset 验证 | PASS | fix 描述完整且最小 |
| mapping sorted freeze | PASS | fix 描述完整且最小 |
| packer 不 dedup + pipeline same-ref failclosed | PASS | fix 描述完整且最小 |

---

## 8. NEEDS_FIX 详情

### 8.1 packed_content_digest 单一 helper 缺乏可执行规格

- **位置**: Fix controller 修订 F1
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: "由 compact-material 单一 helper 按最终 pack 语义派生，accepted evidence 使用 `result_text` digest；producer 与 packer 复用同一 helper"
- **反例/失败场景**: 实施 Agent 可能：
  1. 在 `_pack_evidence_blocks` 中使用 `_text_digest(material.result_text)`
  2. 在 provenance producer 中使用 `block.content_digest`（来自 `RunInputMaterialBlock`，使用四行 render）
  3. 不创建单一 helper，导致两处 digest 来源不同
- **为什么有问题**: provenance 声明的 `packed_content_digest` 与 pack 中 `CompactEvidenceBlock.content_digest` 不一致，operation 验证 fail closed
- **直接证据**: `compact_material.py:2830` vs `compact_material.py:2848`
- **影响**: 实施 Agent 无法确定单一 helper 的签名、位置和调用点，可能产生系统性 mismatch
- **建议改法**: fix 应明确：
  1. helper 签名：`def _packed_content_digest_for_evidence(material: AcceptedToolEvidenceLLMMaterial) -> str`
  2. helper 位置：`compact_material.py` 模块级私有函数
  3. 调用点：
     - `_pack_evidence_blocks` 构造 `CompactEvidenceBlock` 时使用
     - `RunInputMaterialBlock` 构造 evidence block 时使用（或 provenance producer 使用）
  4. 验证点：pipeline owner test 中 evidence block selected → packed → operation provenance 验证链路完整通过
- **修复风险**: 低
- **严重程度**: 高

---

## 9. Open Questions

1. **单一 helper 的调用时机**：`RunInputMaterialBlock` 在构造时就需要 `content_digest`，但此时 `AcceptedToolEvidenceLLMMaterial` 已经可用。是否需要修改 `RunInputMaterialBlock` 的构造逻辑来使用新 helper？还是只在 provenance producer 中使用？

2. **transient proof subset 验证的测试覆盖**：fix 要求测试覆盖 transient proof 包含 unknown block_id 或篡改 refs/digest 的场景。这些测试应该放在哪个 suite？建议放在 `test_compaction_operation.py`。

---

## 10. Residual Risks

- **单一 helper 的实施路径不清晰**：fix 的意图正确，但缺乏可执行规格。实施 Agent 可能需要额外的设计决策（helper 签名、调用点、是否修改 `RunInputMaterialBlock` 构造逻辑）。

- **same-ref fail closed 的具体实现位置**：fix 要求在 pipeline/provider 前 fail closed，但没有指定具体位置。建议在 `compact_pipeline.py` 的 `_validate_segment_against_source_snapshot` 中检查，或在 `compaction_operation.py` 的 `_validate_operation_root_request` 中检查。

---

## Final Plan Review Conclusion

**NEEDS_FIX**

F1 修订（`packed_content_digest` 单一 helper）缺乏可执行规格，是高严重度实施风险。fix 的意图正确，但未指定 helper 签名、位置或调用点，实施 Agent 可能无法正确实现单一 helper 语义。

F2、F3、F4 修订均完整且最小，可直接实施。

建议 fix controller 补充 F1 的可执行规格后重新提交 re-review。
