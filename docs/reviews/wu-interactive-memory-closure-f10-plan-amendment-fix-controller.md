# F10 plan amendment review fix：总控裁决

## Review finding disposition

| Finding | 裁决 | 修订 |
|---|---|---|
| DS F1：evidence digest 与 RunInput digest不同源 | 接受 | provenance字段改为 `packed_content_digest`；由compact-material单一helper按最终pack语义派生，accepted evidence使用`result_text` digest；producer与packer复用同一helper。可执行规格见下文。 |
| DS F2：transient proof subset验证位置不清 | 接受 | 明确 `_single_block_segment_selection`只能取root entry；`_operation_pass_requests`验证每个pass是root proof精确子集且合并后无重叠/遗漏，每个pass在provider前再与自身pack比对。 |
| DS F3：excluded mapping排序与digest可能不一致 | 接受 | `__post_init__`先stable key sort copy再冻结；stored mapping、`to_json()`和digest使用同一canonical order，新增insertion-order反例。 |
| DS F4：same-ref与same-text dedup边界 | 接受finding，采用更强owner边界 | packer不再静默dedup任何selected block；same-text/different-ref完整保留；same canonical current ref是source/request invariant violation，在pipeline/provider前fail closed。 |
| MiMo PASS | 证据部分保持有效 | refs+packed digest仍是最小identity proof；kind/section/labels仍为派生字段，不加入typed proof。MiMo未识别evidence digest转换差异，由DS直接代码证据纠正。 |

## Decision

修订不改变产品语义、LLM schema、Memory/RunInput消费者或fallback策略；只把accepted plan既有的root provenance不变量补成可执行的Host-internal contract。等待两路re-review通过后恢复F10 implementation。

### F1 可执行规格：最终 pack content digest

1. 在 `dayu/host/compact_material.py` 定义模块级私有 helper：
   `def _packed_content_digest(block: RunInputMaterialBlock) -> str`。
2. helper 只表达“该 selected source block 进入最终 compact material pack 后的 content digest”：
   - ordinary trace/answer block：`_text_digest(block.text)`；
   - accepted evidence block：必须存在 `accepted_tool_evidence`，返回
     `_text_digest(block.accepted_tool_evidence.result_text)`，与
     `CompactEvidenceBlock.raw_result_text` 的内容精确同源；typed evidence 缺失时
     fail closed。
3. `RunInputMaterialBlock.content_digest` 仍是 source-boundary 中完整
   LLM-readable block 的 digest；不改它的语义，不用它冒充 evidence 的
   final-pack digest。
4. 以下路径必须直接调用同一 helper，禁止各自重算：
   - `SelectedBlockProvenance` producer 从 selected `RunInputMaterialBlock`
     产生 `packed_content_digest`；
   - `_compact_material_block`和`_pack_evidence_blocks` 产生最终 pack block digest；
   - `_provenance_from_evidence_blocks` 产生与 evidence pack 同源的
     prompt-local provenance digest。
5. operation 比对的是 `SelectedBlockProvenance.packed_content_digest`与已构建
   pack block 的 `content_digest`；不再直接比对
   `RunInputMaterialBlock.content_digest`。
6. owner test 必须覆盖 ordinary block 和 accepted evidence block 从 selection →
   provenance → pack → operation pre-provider validation 的完整链路，并断言
   evidence 的四行 source render digest 与 `result_text` pack digest 不同时仍正确通过。

### F4 可执行位置补充

same canonical current ref 的 invariant 由 compact pipeline 在 material pack 构建完成、
operation/provider 启动前校验；该校验比对 selected history/evidence 与
current anchor 的 canonical refs，不依赖文本相等。相同文本但不同 canonical refs
必须保留并进入 pack。
