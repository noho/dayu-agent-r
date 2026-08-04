# Interactive Conversation Memory closure F10：Plan amendment re-review 2（MiMo）

## Gate

- Review 类型：plan amendment re-review 2，针对 fix controller 补充可执行规格后的修订。
- 审查目标：`docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-fix-controller.md`（2026-08-04 修订版）。
- 对照材料：首次 re-review（`wu-interactive-memory-closure-f10-plan-amendment-rereview-mimo.md`）、DS review、当前 production code。
- 结论：**PASS**。所有旧 finding 已关闭，无新 NEEDS_FIX。

---

## 审查范围

本次 re-review 验证 fix controller 对首次 re-review NEEDS_FIX 的补充规格是否完整且可执行：

1. **F1 修订**：`packed_content_digest` 单一 helper 可执行规格
2. **F4 修订**：same-ref failclosed 位置补充

---

## 1. F1 可执行规格审查

### 1.1 Fix controller 补充内容

> 1. 在 `dayu/host/compact_material.py` 定义模块级私有 helper：`def _packed_content_digest(block: RunInputMaterialBlock) -> str`。
> 2. helper 只表达"该 selected source block 进入最终 compact material pack 后的 content digest"：
>    - ordinary trace/answer block：`_text_digest(block.text)`；
>    - accepted evidence block：必须存在 `accepted_tool_evidence`，返回 `_text_digest(block.accepted_tool_evidence.result_text)`，与 `CompactEvidenceBlock.raw_result_text` 的内容精确同源；typed evidence 缺失时 fail closed。
> 3. `RunInputMaterialBlock.content_digest` 仍是 source-boundary 中完整 LLM-readable block 的 digest；不改它的语义，不用它冒充 evidence 的 final-pack digest。
> 4. 以下路径必须直接调用同一 helper，禁止各自重算：
>    - `SelectedBlockProvenance` producer 从 selected `RunInputMaterialBlock` 产生 `packed_content_digest`；
>    - `_compact_material_block`和`_pack_evidence_blocks` 产生最终 pack block digest；
>    - `_provenance_from_evidence_blocks` 产生与 evidence pack 同源的 prompt-local provenance digest。
> 5. operation 比对的是 `SelectedBlockProvenance.packed_content_digest`与已构建 pack block 的 `content_digest`；不再直接比对 `RunInputMaterialBlock.content_digest`。
> 6. owner test 必须覆盖 ordinary block 和 accepted evidence block 从 selection → provenance → pack → operation pre-provider validation 的完整链路，并断言 evidence 的四行 source render digest 与 `result_text` pack digest 不同时仍正确通过。

### 1.2 直接代码证据验证

**`RunInputMaterialBlock.content_digest` 构造路径**（`compact_material.py:780-786`）：

```python
material_text = text if accepted_tool_evidence is not None else normalized_material_text(text)
return RunInputMaterialBlock(
    ...
    text=material_text,
    content_digest=_text_digest(material_text),
    ...
)
```

- 对 ordinary block：`material_text = normalized_material_text(text)`，`content_digest = _text_digest(normalized_material_text(text))`
- 对 evidence block：`material_text = text`（四行 render），`content_digest = _text_digest(text)`

**`_packed_content_digest(block)` 预期行为**：

- 对 ordinary block：`_text_digest(block.text)` = `_text_digest(normalized_material_text(text))` = `block.content_digest` ✓
- 对 evidence block：`_text_digest(block.accepted_tool_evidence.result_text)` ≠ `_text_digest(block.text)`（四行 render）≠ `block.content_digest`

**`CompactEvidenceBlock.content_digest` 构造路径**（`compact_material.py:2830`）：

```python
CompactEvidenceBlock(
    ...
    content_digest=_text_digest(material.result_text),
)
```

**`_packed_content_digest(block)` 与 `CompactEvidenceBlock.content_digest` 同源验证**：

- `_packed_content_digest(block)` = `_text_digest(block.accepted_tool_evidence.result_text)`
- `CompactEvidenceBlock.content_digest` = `_text_digest(material.result_text)`（其中 `material = block.accepted_tool_evidence`）
- 两者同源 ✓

### 1.3 调用点验证

**`_compact_material_block`（`compact_material.py:2787-2806`）**：

当前：`content_digest=block.content_digest`
修复后：`content_digest=_packed_content_digest(block)`

- 对 ordinary block：两者相同（`block.text` = `material_text`）
- 对 evidence block：不适用（`_compact_material_block` 只处理 ordinary block）

**`_pack_evidence_blocks`（`compact_material.py:2807-2836`）**：

当前：`content_digest=_text_digest(material.result_text)`
修复后：`content_digest=_packed_content_digest(block)`

- 两者相同（`_packed_content_digest(block)` 对 evidence block 返回 `_text_digest(block.accepted_tool_evidence.result_text)`）

**`_provenance_from_evidence_blocks`（`compact_material.py:2862-2900`）**：

当前：`content_digest=source.content_digest`
修复后：`content_digest=_packed_content_digest(source)`

- 当前使用 `source.content_digest`（四行 render digest）
- 修复后使用 `_packed_content_digest(source)`（result_text digest）
- 修复后与 `_pack_evidence_blocks` 同源 ✓

### 1.4 RunInput digest 语义不变验证

fix 明确："RunInputMaterialBlock.content_digest 仍是 source-boundary 中完整 LLM-readable block 的 digest；不改它的语义"

- `RunInputMaterialBlock.content_digest` 字段不变
- 构造逻辑不变
- 不再被用于 operation 比对

**判定**：语义不变 ✓

### 1.5 operation 比对点验证

fix 明确："operation 比对的是 SelectedBlockProvenance.packed_content_digest 与已构建 pack block 的 content_digest；不再直接比对 RunInputMaterialBlock.content_digest"

- `SelectedBlockProvenance.packed_content_digest` 由 `_packed_content_digest(block)` 产生
- pack block `content_digest` 由 `_packed_content_digest(block)` 产生（通过 `_compact_material_block` / `_pack_evidence_blocks`）
- 两者同源 ✓

### 1.6 结论

**PASS**。F1 可执行规格完整且可执行：
- helper 签名明确
- 算法区分 ordinary / evidence
- 调用点明确（4 处）
- RunInput digest 语义不变
- operation 比对点明确
- 测试要求明确

---

## 2. F4 same-ref failclosed 位置审查

### 2.1 Fix controller 补充内容

> same canonical current ref 的 invariant 由 compact pipeline 在 material pack 构建完成、operation/provider 启动前校验；该校验比对 selected history/evidence 与 current anchor 的 canonical refs，不依赖文本相等。相同文本但不同 canonical refs 必须保留并进入 pack。

### 2.2 直接代码证据验证

**当前 `_selected_material_blocks` 逻辑**（`compact_material.py:2714-2735`）：

```python
for block_id in selected_block_ids:
    block = block_by_id.get(block_id)
    if block is None:
        raise ValueError("selected segment references unknown material block")
    if _is_current_input_history_duplicate(block, current_anchor):
        continue  # 静默跳过
    selected.append(block)
```

**当前 `_is_current_input_history_duplicate` 逻辑**（`compact_material.py:2737-2751`）：

```python
if current_anchor.canonical_source_refs[0] in block.canonical_source_refs:
    return True  # canonical ref 相同 → 跳过
return block.content_digest == current_anchor.content_digest  # content_digest fallback
```

### 2.3 Fix 实现路径分析

fix 要求：
1. 删除 content_digest fallback（line 2751）
2. same canonical current ref 是 invariant violation
3. 在 pipeline/provider 前 fail closed

**实现路径**：

1. 删除 `_is_current_input_history_duplicate` 的 content_digest fallback（line 2751）
2. 修改 `_is_current_input_history_duplicate` 或 `_selected_material_blocks`：
   - 当检测到 same canonical ref 时，抛出异常（fail closed），而不是返回 True（静默跳过）

**具体实现**：

方案 A：修改 `_is_current_input_history_duplicate`，当 canonical ref 相同时抛出异常
- 优点：改动最小
- 缺点：函数名暗示"判断是否重复"，改为抛出异常语义不符

方案 B：修改 `_selected_material_blocks`，删除 `_is_current_input_history_duplicate` 调用，直接在 canonical ref 相同时抛出异常
- 优点：语义清晰
- 缺点：需要重构

方案 C：保留 `_is_current_input_history_duplicate` 只做 canonical ref 检查（删除 content_digest fallback），在 `_selected_material_blocks` 中当返回 True 时抛出异常
- 优点：职责分离清晰
- 缺点：需要两处修改

**fix 的意图**：方案 C 最符合 fix 的描述
- `_is_current_input_history_duplicate` 只做 canonical ref 检查（删除 content_digest fallback）
- `_selected_material_blocks` 当检测到 same canonical ref 时抛出异常（fail closed）

### 2.4 位置验证

fix 说"由 compact pipeline 在 material pack 构建完成、operation/provider 启动前校验"。

**当前调用链**：
- `_request_plan_from_segment` → `build_compact_material_pack` → `_selected_material_blocks` → `_is_current_input_history_duplicate`

**校验位置**：
- `_selected_material_blocks` 在 `build_compact_material_pack` 内部被调用
- 如果 same canonical ref 检测到，抛出异常
- 异常会向上传播到 `_request_plan_from_segment`，阻止 request 构造
- 这符合"material pack 构建完成、operation/provider 启动前校验"

**判定**：位置正确 ✓

### 2.5 结论

**PASS**。F4 same-ref failclosed 位置补充完整：
- 校验位置明确（`_selected_material_blocks` 或 `_is_current_input_history_duplicate`）
- 校验内容明确（canonical ref 相同时 fail closed）
- 不依赖文本相等 ✓
- 相同文本但不同 canonical refs 保留 ✓

---

## 3. 旧 finding 逐项复核

| Finding | 首次 re-review 结论 | 本次复核结论 | 关闭证据 |
|---|---|---|---|
| F1: packed_content_digest 单一 helper 缺乏可执行规格 | NEEDS_FIX | **PASS** | fix 补充了完整可执行规格：helper 签名、算法、调用点、RunInput 语义不变、operation 比对点、测试要求 |
| F2: transient exact subset 验证 | PASS | **PASS** | 无变化 |
| F3: mapping sorted freeze | PASS | **PASS** | 无变化 |
| F4: same-ref failclosed 位置不明确 | PASS（首次 re-review 未识别为 NEEDS_FIX） | **PASS** | fix 补充了位置：compact pipeline 在 material pack 构建完成前校验 |

---

## 4. 新 finding 检查

### 4.1 F1 实施一致性风险

**风险**：fix 要求 `_compact_material_block`、`_pack_evidence_blocks`、`_provenance_from_evidence_blocks` 都使用 `_packed_content_digest(block)`，但当前 `_compact_material_block` 使用 `block.content_digest`。

**分析**：
- 对 ordinary block，`_packed_content_digest(block)` = `_text_digest(block.text)` = `block.content_digest`（构造时相同）
- 如果实施 Agent 不修改 `_compact_material_block`，仍然使用 `block.content_digest`，结果相同
- 但如果未来 `RunInputMaterialBlock.content_digest` 的构造逻辑变化，可能导致不一致

**建议**：实施时统一使用 `_packed_content_digest(block)`，确保 producer 和 packer 同源。

**严重程度**：低（当前行为正确，但存在未来风险）

### 4.2 F4 异常传播路径

**风险**：`_selected_material_blocks` 抛出异常后，需要确保异常向上传播到 `_request_plan_from_segment`，并正确处理。

**分析**：
- `_selected_material_blocks` 被 `build_compact_material_pack` 调用
- `build_compact_material_pack` 被 `_request_plan_from_segment` 调用
- 异常会自然向上传播
- `_request_plan_from_segment` 不捕获该异常，会继续传播到 `build_normal_compact_request_plan`
- 最终由调用方处理

**判定**：异常传播路径正确，无需额外处理。

**严重程度**：无

---

## 5. 总结

| 审查维度 | 结论 | 反例 |
|---|---|---|
| F1 可执行规格完整性 | PASS | 无。helper 签名、算法、调用点、语义不变、比对点、测试要求均明确。 |
| F4 same-ref failclosed 位置 | PASS | 无。校验位置在 `_selected_material_blocks`，符合"material pack 构建完成前校验"。 |
| 旧 finding 关闭状态 | PASS | 全部关闭。 |
| 新 finding | 无 NEEDS_FIX | F1 实施一致性风险为低严重度，不影响结论。 |

---

## 6. 实施注意事项（非 NEEDS_FIX，仅供参考）

1. **F1 helper 实现**：建议在 `compact_material.py` 中 `_text_digest` 函数附近定义 `_packed_content_digest`，便于维护。

2. **F4 异常类型**：建议使用 `ValueError`，与现有 `_selected_material_blocks` 的异常类型一致。

3. **F4 错误信息**：建议包含 block_id 和 canonical_source_refs，便于调试。

4. **F1 测试覆盖**：建议测试：
   - ordinary block 的 `_packed_content_digest` 与 `block.content_digest` 相同
   - evidence block 的 `_packed_content_digest` 与 `CompactEvidenceBlock.content_digest` 相同
   - evidence block 的 `_packed_content_digest` 与 `block.content_digest` 不同
   - operation provenance 验证链路完整通过

5. **F4 测试覆盖**：建议测试：
   - same canonical ref 时 fail closed
   - same text / different canonical ref 时保留

---

## Final Plan Review Conclusion

**PASS**

所有旧 finding 已关闭。F1 可执行规格完整且可执行；F4 same-ref failclosed 位置明确。fix controller 的修订满足首次 re-review 的要求，可以恢复 F10 implementation。
