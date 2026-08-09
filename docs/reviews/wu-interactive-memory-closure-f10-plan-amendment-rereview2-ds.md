# Interactive Conversation Memory closure F10：Plan Amendment Re-review #2（DS 第二路）

- **Review target**: `docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-controller.md` + `docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-fix-controller.md`
- **Review type**: 第二路 DS adversarial plan re-review——检查修订后的 plan 是否自足、可执行，严格区分 plan gap 与 implementation TODO
- **前次 rereview 勘误**: `rereview-ds.md` 误将 "尚未实施 amendment" 判为 "plan 不可执行"。本 artifact 是独立纠正版，审查对象仅为 plan 文档本身，不审查当前 working tree 的 partial implementation
- **Timestamp**: 2026-08-04

---

## 审查方法

逐项验证修订后 plan 是否对以下 7 个关键规格给出了可生成代码的明确描述。若 plan 本身已明确，即使代码尚未编写，也判为 implementation TODO 而非 plan finding。仅在 plan 缺失关键规格、存在矛盾、或可导致两种以上不同正确实现时才判为 plan gap。

---

## 1. SelectedBlockProvenance 类型规格

### Plan 内容

**Controller §1（line 13-17）**：
- 类型位置：`dayu/host/compaction.py`
- 类型性质：最小 frozen strict type
- 三字段：`block_id`（selection 内部 block identity）、`canonical_source_refs`（由 RunInputMaterialBlock 直接提供的非空 canonical refs）、`packed_content_digest`（pack 中业务可读文本的 canonical digest）

**Fix-controller F1（line 17-41）**：
- Helper 签名：`def _packed_content_digest(block: RunInputMaterialBlock) -> str`，位于 `dayu/host/compact_material.py`
- Ordinary trace/answer block：`_text_digest(block.text)`
- Accepted evidence block：`_text_digest(block.accepted_tool_evidence.result_text)`，typed evidence 缺失时 fail closed
- 明确区分 `RunInputMaterialBlock.content_digest`（source-boundary 完整 LLM-readable block digest）与 `packed_content_digest`（final-pack digest），不改前者语义
- 四个调用点：SelectedBlockProvenance producer、`_compact_material_block`、`_pack_evidence_blocks`、`_provenance_from_evidence_blocks`

**Controller §1（line 19-24）**：
- `CompactSegmentSelection` 增加 `selected_block_provenance`，与 `selected_block_ids` 一一对应且顺序相同
- refs 非空、每项唯一、不从 label/ordinal 反推
- `packed_content_digest` 非空且与 pack block `content_digest` 同源
- Root selector 从 RunInputMaterialBlock source snapshot 机械产生
- Transient pass 只取 root proof 对应子集
- Canonical serialization 与 selection/request digest 包含该 proof
- 不进入 LLM-facing 投影

### 判定：CLEAR ✓

类型定义、字段语义、helper 签名、digest 来源、调用点、序列化规则、LLM 隔离均明确。一个有能力阅读 `compact_material.py` 和 `compaction.py` 的实现者可以直接生成代码。

### 观察（非 gap）

- **Root selector producer 位置未命名**：Plan 说 "root selector 从同一 RunInputMaterialBlock source snapshot 机械产生"。F10 有两个 root selector——`select_compact_segment`（有 source snapshot）和 `initial_segment_selection`（无 source snapshot，从 CompactMaterialPack 构造）。前者是 provenance 的自然 producer；后者因无 source snapshot，`selected_block_provenance` 应为空 tuple `()`。Plan 未显式区分两者，但 "从 RunInputMaterialBlock source snapshot 机械产生" 的条件从句已隐含：无 snapshot 则无 provenance。实现者可自行判断，不构成阻塞。

---

## 2. 每 pass exact root subset / 无重叠 / 无遗漏

### Plan 内容

**Controller §1（line 28）**：
> `_operation_pass_requests` 必须逐 pass 验证 transient provenance 是 root provenance 的精确子集：block id存在于root，refs与packed digest逐字段相等，所有pass合并后对root selected proof无重叠、无遗漏

**Fix-controller F2**：
> 明确 `_single_block_segment_selection`只能取root entry；`_operation_pass_requests`验证每个pass是root proof精确子集且合并后无重叠/遗漏

### 判定：CLEAR ✓

验证算法可明确推导：
1. 逐 pass：对每个 transient pass 的 `selected_block_provenance` 中每个 entry，验证其 `block_id` 在 root `selected_block_provenance` 中存在，且对应 entry 的 `canonical_source_refs` 和 `packed_content_digest` 逐字段相等。
2. 合并验证：所有 pass 的 `selected_block_ids` 取并集，应等于 root `selected_block_ids`；各 pass 的 `selected_block_ids` 两两交集为空。

Matching key 是 `block_id`（provenance 的 identity 字段），比较值是 `(canonical_source_refs, packed_content_digest)`。实现者可选择建立 `block_id → entry` 映射或线性搜索——这是实现细节。

### 观察（非 gap）

- **Transient producer 约束已明确**：`_single_block_segment_selection` "只能取 root entry，不允许重算或接受外部值"——这意味着 `_single_block_segment_selection` 必须从 `root_request.segment_selection.selected_block_provenance` 中按 `block_id` 查找，获取单个 entry 作为 transient 的 `selected_block_provenance`。约束清晰。

---

## 3. 每个 pass 在 provider 前验证自身 proof 与 material pack 一致

### Plan 内容

**Controller §1（line 26, 28）**：
> operation 在 provider 前和 durable accept 前，将 proof 与 material pack 中实际 selected trace/evidence/answer blocks 的 canonical refs + packed content digest 做精确一一匹配
> 每个pass还要在provider前验证其proof与自身material pack一致

### 判定：CLEAR ✓

验证时机明确（provider 前），验证内容明确（proof 与 material pack blocks 的 refs + digest 匹配）。实现位置在 `_run_compaction_operation` 的 attempt loop 中，provider 调用之前。

### 观察（非 gap）

- **Matching key 未指定**：Plan 说 "精确一一匹配" 但不指定用 position（provenance 第 i 项 ↔ pack block 第 i 项）还是 ref-based lookup。但 plan 已约束 `selected_block_provenance` 与 `selected_block_ids` 同序（line 21），且 pack blocks 保持 selected_block_ids 的相对 stable order（section 内）。因此 position-based 匹配可行且最简单。若实现者选择 ref-based lookup 也等价——两种方式在正确实现下结果相同。不构成歧义。

---

## 4. excluded_reason_codes mapping sorted copy + read-only freeze

### Plan 内容

**Controller §3（line 42）**：
> `CompactSegmentSelection.__post_init__` 必须先按 block id key稳定排序复制，再以真正只读的 mapping view保存；selection digest构造与 `to_json()` 都消费相同的sorted canonical mapping。保持现有 read-only `Mapping[str, str]` contract与 canonical JSON形状，不新增 alias/default/compat。测试断言不同input insertion order得到相同stored order/JSON/digest，外部原 mapping后续变更和对字段直接变更均不能改变 selection内容或digest。

**Fix-controller F3**：
> `__post_init__`先stable key sort copy再冻结；stored mapping、`to_json()`和digest使用同一canonical order，新增insertion-order反例。

### 判定：CLEAR ✓

排序键明确（block id key，即 `excluded_reason_codes` 的 key），排序方向明确（stable sort），冻结语义明确（不能通过外部引用或字段赋值改变）。测试要求覆盖 insertion-order invariance 和 external mutation defense。

### 观察（非 gap）

- **"真正只读的 mapping view" 的具体 Python 类型未固定**：可选 `types.MappingProxyType`（运行时拒绝 mutation）或 plain `dict` copy（依赖 `frozen=True` 阻止字段重赋值，但 dict 本身仍可被持有引用的外部代码 mutate）。考虑到 plan 的测试要求 "外部原 mapping 后续变更...均不能改变 selection 内容"，`MappingProxyType` 是满足此约束的最自然选择。当前 `select_compact_segment` 中 `excluded_reasons` 是局部变量，构造后无外部引用，因此 plain dict copy 在实践中同样安全。无论实现者选择哪种，都不影响 contract 正确性——这是实现选择而非 plan gap。

---

## 5. 取消 packer dedup

### Plan 内容

**Controller §2（line 34）**：
> `dayu/host/compact_material.py` 的 packer 不再拥有 selected history/current-input dedup：`_selected_material_blocks` 对 selector 已选 block 必须一项不漏地投影，不得 `continue` 删除任何 group member。不得因 content digest 相同而删除 canonical refs 不同的历史 user input。

**Fix-controller F4**：
> packer不再静默dedup任何selected block；same-text/different-ref完整保留

**Controller §2（line 36-38）**，新增 owner tests：
> - 历史 user input 与 current input 文本相同但 event refs不同，完整 user/evidence/final group仍进入 pack与proof；
> - selected history与current anchor canonical ref相同，pipeline fail closed且provider不调用；
> - packer对任何合法selected ids保持数量和stable order一一对应。

### 判定：CLEAR ✓

修复范围精确（`_selected_material_blocks` 函数），修复动作精确（移除 `continue` 逻辑），禁止行为精确（不得因 content_digest 相同而删除不同 ref 的 block）。三个测试用例覆盖了修复后的正确行为（same-text → 保留）、防御行为（same-ref → fail closed）和不变量（数量与顺序一致）。

---

## 6. same-ref pipeline pre-provider fail-closed

### Plan 内容

**Controller §2（line 34）**：
> 若 source snapshot 意外让与 current input anchor 相同 canonical ref 的 history block进入 selected boundary，pipeline source/request validation 必须在pack/provider前 fail closed；不得把它当作pack阶段可静默删除的重复。

**Fix-controller F4 可执行位置补充（line 43-48）**：
> same canonical current ref 的 invariant 由 compact pipeline 在 material pack 构建完成、operation/provider 启动前校验；该校验比对 selected history/evidence 与 current anchor 的 canonical refs，不依赖文本相等。相同文本但不同 canonical refs 必须保留并进入 pack。

### 判定：CLEAR ✓

- **时机**：material pack 构建完成后、operation/provider 启动前 → pipeline 层，在 `_request_plan_from_segment` 或 `_validate_segment_against_source_snapshot` 附近
- **校验逻辑**：比对 selected history/evidence blocks 的 `canonical_source_refs` 与 current anchor 的 `canonical_source_refs[0]`——基于 source identity，不基于文本相等
- **失败行为**：fail closed，provider 不调用
- **与 §5 的配合**：packer 不再静默 dedup；若 same-ref 意外进入 selection，pipeline 在此处捕获

### 观察（非 gap）

- **校验函数名未固定**：Plan 说 "由 compact pipeline 在 material pack 构建完成...前校验"，未指定具体函数名。合理的实现位置是 `_validate_segment_against_source_snapshot`（已有 source snapshot 和 selected_segment 参数）或新增一个独立校验函数在 `_request_plan_from_segment` 中调用。实现者根据 pipeline 结构自行决定——这是实现细节。

---

## 7. 单一 digest helper 签名与调用点

### Plan 内容

**Fix-controller F1（line 17-41）**——完整可执行规格：

| 项目 | 规格 |
|---|---|
| 函数签名 | `def _packed_content_digest(block: RunInputMaterialBlock) -> str` |
| 模块位置 | `dayu/host/compact_material.py` |
| Ordinary block 逻辑 | `_text_digest(block.text)` |
| Evidence block 逻辑 | `block.accepted_tool_evidence` 必须存在 → `_text_digest(block.accepted_tool_evidence.result_text)`；缺失 → fail closed |
| 调用点 1 | `SelectedBlockProvenance` producer（从 selected RunInputMaterialBlock 产生 `packed_content_digest`） |
| 调用点 2 | `_compact_material_block`（产生普通 pack block digest） |
| 调用点 3 | `_pack_evidence_blocks`（产生 evidence pack block digest） |
| 调用点 4 | `_provenance_from_evidence_blocks`（产生与 evidence pack 同源的 prompt-local provenance digest） |
| 明确不做的 | 不改 `RunInputMaterialBlock.content_digest` 语义；不用它冒充 evidence 的 final-pack digest |
| Operation 比对 | `SelectedBlockProvenance.packed_content_digest` ↔ pack block `content_digest`；不直接比对 `RunInputMaterialBlock.content_digest` |
| Owner test | 覆盖 ordinary + evidence 从 selection → provenance → pack → operation pre-provider validation 完整链路；断言 evidence 四行 source render digest ≠ `result_text` pack digest 时仍正确通过 |

### 判定：CLEAR ✓

这是 plan 中规格最完整的部分。函数名、签名、位置、分 case 逻辑、四个调用点、与既有 digest 的关系、operation 比对方式和测试要求均明确。实现者可直接生成代码。

---

## Plan 完整性总评

### 七项关键规格检查

| # | 规格项 | 状态 | 备注 |
|---|---|---|---|
| 1 | SelectedBlockProvenance 类型 | CLEAR | 三字段 + helper + 四个调用点 + LLM 隔离 |
| 2 | Per-pass root subset / 无重叠遗漏 | CLEAR | 算法可从 block_id 匹配 + 并集/交集推导 |
| 3 | 每 pass provider 前验证自身 pack | CLEAR | 时机和比对内容明确 |
| 4 | Mapping sorted copy + read-only freeze | CLEAR | 排序键、冻结语义、测试要求明确 |
| 5 | 取消 packer dedup | CLEAR | 修复函数、动作、禁止行为精确 |
| 6 | Same-ref pipeline fail-closed | CLEAR | 时机、校验逻辑、失败行为明确 |
| 7 | 单一 digest helper 签名与调用点 | CLEAR | 函数签名、位置、四调用点、测试链路完整 |

### 跨项一致性检查

- **F1 helper 调用点 vs F4 dedup 取消**：无冲突。F1 的 helper 供 provenance 和 pack builder 使用；F4 取消了 packer 的 dedup，packer 仍通过 F1 helper 构造 block digest。
- **F1 packed_content_digest vs F3 excluded_reason_codes**：selection_digest 现在包含 `excluded_reason_codes`（sorted mapping）和 `selected_block_provenance`（含 `packed_content_digest`）。两者都是 selection 不可变 proof 的组成部分，无循环依赖。
- **§1 transient subset vs §2 same-ref fail-closed**：两者互补——§1 防止 transient 伪造 provenance，§2 防止 same-ref history 混入 root selection。两个防御层独立且不重叠。

### 已知的 implementation TODO（非 plan gap）

以下事项 plan 已明确要求但尚未写入代码，属 implementation TODO，不构成 plan finding：

1. `SelectedBlockProvenance` 类型尚未在 `compaction.py` 中定义
2. `_packed_content_digest` helper 尚未在 `compact_material.py` 中定义
3. `CompactSegmentSelection.selected_block_provenance` 字段尚未添加
4. `select_compact_segment` 尚未产生 provenance
5. `_selected_material_blocks` 中的 dedup `continue` 尚未移除
6. `_is_current_input_history_duplicate` 中的 `content_digest` fallback 尚未删除
7. Pipeline same-ref 校验尚未添加
8. `__post_init__` 的 sorted copy + freeze 尚未添加
9. `_single_block_segment_selection` 尚未从 root provenance 取 entry
10. `_operation_pass_requests` 的 per-block subset 验证尚未添加
11. Operation loop 中 per-pass pack 一致性验证尚未添加
12. F1 要求的 owner test（完整链路 + evidence digest 差异断言）尚未编写
13. F4 要求的三个 owner tests 尚未编写

### 非阻塞观察汇总

| # | 观察 | 严重度 | 理由 |
|---|---|---|---|
| O1 | Root selector producer 位置未显式命名 | 信息 | "从 RunInputMaterialBlock source snapshot 机械产生" 的条件从句已隐含：`select_compact_segment` 有 snapshot → 生产；`initial_segment_selection` 无 snapshot → 空 tuple |
| O2 | Pass proof ↔ pack 匹配键未指定（position vs ref） | 信息 | 两者等价；position-based 更简单且 plan 已保证同序 |
| O3 | "真正只读的 mapping view" 未固定具体类型 | 信息 | MappingProxyType 与 dict copy 均满足 contract；测试要求排除外部 mutation 即可 |
| O4 | Same-ref 校验函数名未固定 | 信息 | 实现者根据 pipeline 结构自行决定；校验逻辑已明确 |
| O5 | `initial_segment_selection` 的 provenance 值未显式说明 | 信息 | 无 source snapshot → 空 tuple，与 `turn_group_memberships=()` 同模式 |

---

## Final Conclusion

**PASS**

修订后的 plan amendment（controller + fix-controller）对所有七项关键规格给出了可生成代码的明确描述：

- `SelectedBlockProvenance` 类型定义、三字段语义、helper 签名与四个调用点均已精确指定
- Per-pass exact root subset / 无重叠 / 无遗漏的验证算法可从 plan 描述直接推导
- 每 pass provider 前与自身 pack 的一致性验证时机与比对内容明确
- `excluded_reason_codes` 的 sorted copy + read-only freeze 步骤、排序键、测试要求完整
- Packer dedup 取消的修改范围（函数、行、禁止行为）精确
- Same-ref pipeline pre-provider fail-closed 的时机、校验逻辑、失败行为明确
- 单一 digest helper 的规格达到可直接编码的详细程度（含四个命名调用点与 owner test 链路）

五项非阻塞观察均为实现细节选择，不影响 plan 的可执行性与正确性。所有未写入代码的项目均为 implementation TODO，不是 plan finding。

建议恢复 F10 implementation，按 plan amendment 规格完成编码。
