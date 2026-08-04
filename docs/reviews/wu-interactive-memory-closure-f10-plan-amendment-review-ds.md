# Interactive Conversation Memory closure F10：Plan Amendment Adversarial Review

- **Review target**: `docs/reviews/wu-interactive-memory-closure-f10-plan-amendment-controller.md`
- **Blocked artifact**: `docs/reviews/wu-interactive-memory-closure-f10-implementation-codex.md`
- **Review type**: 第二路独立 adversarial plan review
- **Timestamp**: 2026-08-04 17:58:38

## Reviewed Target and Scope

本 review 只审 plan amendment（总控裁决文件），不审 implementation artifact 或
已写代码。重点检查 provenance bridge 设计、dedup 修复方案、immutability 收紧
和 scope amendment 的充分性与安全性。

## Assumptions Tested

1. `SelectedBlockProvenance` 能诚实解决 block ID 到 boundary provenance 的桥接缺口。
2. content_digest 从 `RunInputMaterialBlock` 到 packed `CompactMaterialBlock` / `CompactEvidenceBlock` 可精确匹配。
3. `excluded_reason_codes` 的 digest 一致性不因 frozen 构造后外部 mutation 而漂移。
4. same-text dedup 修复不会引入新的 pack/selection 不一致。
5. transient selection 的 provenance subset binding 是安全且可验证的。

## Findings

### 1-NEEDS_FIX-高-evidence-block-content_digest-在-RunInputMaterialBlock-与-CompactEvidenceBlock-间不一致

- **位置**: Plan Amendment 第1节 "允许最小 Host-internal selected-block provenance binding"，`SelectedBlockProvenance.content_digest` 定义
- **问题类型**: 契约缺失
- **当前写法**: "content_digest：对应 block 业务可读文本的 canonical digest"，provenance 从 `RunInputMaterialBlock` 直接取值，operation 阶段与 material pack 中实际 block 的 `content_digest` 做精确一一匹配
- **反例/失败场景**:

  1. `RunInputMaterialBlock` 构造 evidence block 时 (compact_material.py:778-786):
     ```python
     material_text = text  # accepted_tool_evidence is not None 时不走 normalize
     content_digest = _text_digest(material_text)
     ```
     其中 `text = render_accepted_tool_evidence_for_llm(material)` (evidence.py:170-177)，
     生成四行完整 evidence 文本：
     ```
     工具名称：{tool_name}
     查询语义：{query_text}
     业务来源：{source_text}
     工具结果：{result_text}
     ```

  2. `_pack_evidence_blocks` (compact_material.py:2830) 构造 `CompactEvidenceBlock` 时:
     ```python
     CompactEvidenceBlock(
         ...
         content_digest=_text_digest(material.result_text),  # 只有 result_text
     )
     ```

  3. 两个 digest 不同源：一个 hash 四行完整 evidence，一个只 hash `result_text`。
     `SelectedBlockProvenance.content_digest` 若来自 `RunInputMaterialBlock.content_digest`，
     将无法匹配 `CompactEvidenceBlock.content_digest`。

- **为什么有问题**: operation 在 provider 前和 durable accept 前对 evidence block
  做精确 content_digest 匹配时将 FAIL CLOSED，即使 block identity 和 canonical_refs
  完全正确。这不是 transient error —— 它是类型转换路径上的系统性 mismatch。
- **直接证据**: `compact_material.py:786` vs `compact_material.py:2830`；
  `evidence.py:170-177` 定义完整四行 render，`CompactEvidenceBlock` 构造只取
  `material.result_text`。
- **影响**: 实施 Agent 若按 plan 字面实现，所有 evidence block 的 provenance
  验证均 fail closed；需回退修改 digest 来源或放宽 evidence 验证规则。
- **建议改法和验证点**:

  方案 A：`SelectedBlockProvenance.content_digest` 对 evidence block 使用
  `_text_digest(accepted_tool_evidence.result_text)`（与 `CompactEvidenceBlock`
  同源），并在此事实的 owner（`_pack_evidence_blocks` / `run_input_material_block`）
  文档中明确说明。

  方案 B：operation 中 evidence block 的 provenance 验证只比对 `canonical_source_refs`，
  不比对 `content_digest`。需明确为何 digest 验证可豁免。

  验证点：pipeline owner test 中 evidence block selected → packed → operation
  provenance 验证链路完整通过。

- **修复风险**: 低（只需调整 digest 来源，不影响其它类型）
- **严重程度**: 高

### 2-NEEDS_FIX-中-transient-selection-provenance-subset-验证位置未明确

- **位置**: Plan Amendment 第1节，"transient pass 只取 root proof 的对应子集并继续绑定
  root_selection_digest"
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: transient selection 的 `selected_block_provenance` 取 root proof
  子集，operation 验证 pass boundary 对 root boundary 是无重叠、无遗漏 exact partition。
- **反例/失败场景**:
  - 当前 pass_queue 验证 (`_operation_pass_requests`, compaction_operation.py:1495-1536)
    检查 turn_group_memberships 一致和 boundary partition，但不检查 per-block provenance
    subset。
  - 若 transient selection 的 `selected_block_provenance` 包含 root proof 中不存在的
    block_id、或替换了 canonical_refs/digest，pass_queue 验证不会捕获。operation loop
    中 transient pass 接受后，单 pass 的 accepted truth 与 root 的 provenance 漂移。
- **为什么有问题**: plan 描述了"transient pass 取 root proof 子集"的意图，但没有指定
  验证发生在哪个函数、用哪个 assertion。实施 Agent 可能在错误位置加检查（如只在
  `_validate_operation_root_request` 中检查 root scope 的 proof），或遗漏 transient
  proof 的 cross-validation。
- **直接证据**: `compaction_operation.py:1495-1536` 不检查 per-block provenance；
  plan 未指定 transient proof subset 验证的具体位置和 assertion。
- **影响**: 实施 Agent 可能遗漏此验证，导致 transient pass 携带伪造 provenance 仍通过验收。
- **建议改法和验证点**: plan 应明确：在 `_operation_pass_requests`（或 operation loop
  中构造 pass request 后）验证每个 transient `selected_block_provenance` 是 root
  `selected_block_provenance` 的子集（按 block_id 匹配，且 matching entry 的
  canonical_source_refs 和 content_digest 完全相同）。测试需覆盖 transient proof
  包含 unknown block_id 或篡改 refs/digest 的场景。
- **修复风险**: 低（纯新增检查，不影响现有 pass）
- **严重程度**: 中

### 3-NEEDS_FIX-中-excluded_reason_codes-digest-与-constructor-值可能因排序不一致

- **位置**: Plan Amendment 第3节 "收紧 selection 的真实不可变性"；`select_compact_segment`
  (compact_material.py:898-924) 和 `initial_segment_selection` (compact_material.py:1391-1418)
- **问题类型**: 契约缺失
- **当前写法**: `select_compact_segment` 的 digest_input 使用
  `_ordered_reason_mapping(excluded_reasons)` (key-sorted)，但 constructor 传入
  原始 `excluded_reasons` (insertion-ordered dict)。`initial_segment_selection` 同理。
- **反例/失败场景**:
  - `excluded_reasons` 以不同 key 顺序构造（例如 `{"B":"reason","A":"reason"}`），
    `_ordered_reason_mapping` 返回 `{"A":"reason","B":"reason"}` 用于 digest 计算，
    但 constructor 存储原始 `{"B":"reason","A":"reason"}`。
  - `to_json()` 通过 `_string_mapping_json` 序列化时为原始插入顺序，
    与 digest 计算时使用的 sorted 顺序不同。后续若任何代码路径对 `excluded_reason_codes`
    做重新 digest 计算（例如 selection digest 重新验证），将产生不同 digest。
  - plan 的 `__post_init__` freeze 只保护构造后不变异，不修复构造时传入的排序差异。
- **为什么有问题**: selection_digest 是 root proof 的核心组成部分；若构造时传入的
  mapping 排序与 digest 计算不一致，`to_json()` 的 serialization 可能产生与 digest
  计算时不同的 JSON。虽然当前 digest 只在构造时计算一次，但 freeze 方案的 contract
  应该是"frozen 后的 mapping 与 digest 完全一致"——如果不对传入值排序，排序不一致
  的 mapping 仍可构造成功且 digest 与 serialization 不同。
- **直接证据**: `compact_material.py:904` (`_ordered_reason_mapping(excluded_reasons)`)
  用于 digest；`compact_material.py:923` (`excluded_reason_codes=excluded_reasons`)
  传入原始值；`compact_material.py:1951` (`_string_mapping_json(self.excluded_reason_codes)`)
  使用原始顺序序列化。
- **影响**: 所有通过 `select_compact_segment` 构造的 root selection 的
  excluded_reason_codes 可能序列化顺序与 digest 不一致；后续若增加 `selection_digest`
  的 reconstruct-verify 步骤会失败。
- **建议改法和验证点**: plan 应明确：`__post_init__` freeze 时应先对 mapping 做
  key-sorted copy：`dict(sorted(self.excluded_reason_codes.items()))`，确保 freeze
  后的 mapping 与 `_ordered_reason_mapping` 输出完全一致。验证点：构造前后 digest
  与 `to_json()` serialization 一致性断言。
- **修复风险**: 低（只需在 freeze 时多一步排序）
- **严重程度**: 中

### 4-NEEDS_FIX-低-same-text-dedup-修复后-packer-仍可能静默丢弃-selected-group-member

- **位置**: Plan Amendment 第2节 "修复相同文本、不同 canonical ref 的错误去重"
- **问题类型**: 切片过粗
- **当前写法**: 只删除 `content_digest` fallback，保留 canonical ref identity 检查。
  同时声明"不得在 packer 中单独删除已被 root selector 原子选中的 group member"。
- **反例/失败场景**:
  - 删除 content_digest fallback 后，`_is_current_input_history_duplicate` 只剩
    canonical ref check: `current_anchor.canonical_source_refs[0] in block.canonical_source_refs`。
  - 该检查正确，但 `_selected_material_blocks` 中若返回 True，block 被 `continue` 跳过。
  - 如果 selector 选中了整个 turn group（包含该 user_input block），packer 删除了
    一个 group member，导致 `len(selected_block_ids) ≠ len(trace+evidence+answer)`，
    `_validate_operation_root_request` 在 operation 入口 fail closed。
  - 这种 fail-closed 是正确的防御行为（证明 packer 不能删除 group member），但
    当前 `_is_current_input_history_duplicate` 在 canonical ref 相同时返回 True 的
    场景 —— 该场景下 block 其实是当前输入自身的历史回显，删除它是正确的该 path fallback。
    然而 plan 只说要删除 content_digest fallback，没有明确 canonical ref 路径下
    的 group member 保护。
- **为什么有问题**: 当前 `_is_current_input_history_duplicate` 的 canonical ref 路径
  对 USER_INPUT 类型 block 可能匹配到"同一事件的不同表示"，删除它会导致 group 被拆分。
  但这是正确的行为 —— canonical ref 相同意味着是同一事实源，不应重复进入 pack。
  plan 的语言"不得在 packer 中单独删除已被 root selector 原子选中的 group member"
  可能被误解为连 canonical ref 相同的重复也不能删除，这会导致同一输入在 pack 中出现两次。
- **直接证据**: `compact_material.py:2749-2751`; 当前测试中无 same-canonical-ref
  group member dedup 场景覆盖。
- **影响**: plan 的语言可能让实施 Agent 过度保护，导致同一 canonical ref 的重复
  block 不删除。
- **建议改法和验证点**: plan 应区分两种 dedup：canonical ref 相同（同源，应 dedup）
  和 content_digest 相同但 ref 不同（不同源，不应 dedup）。"不得单独删除 group member"
  只适用于第二种。第一种（同源 dedup）仍应允许，但需在 selector 层而非 packer 层处理：
  selector 不应将同源 block 同时放入 selected 和 excluded。当前 selector
  (`_collective_exclusion_reason`) 不检查 canonical ref 重复 —— 可考虑在此层增加检查，
  或在 packer 层保留 ref-based dedup 但添加 group membership consistency assertion。
- **修复风险**: 低
- **严重程度**: 低

### 5-确认-低-provenance-bridge-设计总体正确且是最小方案

- **位置**: Plan Amendment 第1节整体
- **问题类型**: 非最优方案（已排除）
- **检查结果**: 经过对替代方案的逐一排除，`SelectedBlockProvenance` 是当前约束下
  的最简方案：
  - 不扩 `TurnGroupMembership`：group 是 collective exclusion 的概念，不应承载
    per-block provenance（违反单一职责）。
  - 不在 `CompactMaterialPack` 中反向索引：pack 的 provenance_map 以 prompt-local
    label 为 key，block_id → label 的映射在 packer 内部，operation 不应解析 label
    语义来反推 block 身份。
  - 不在 operation 中重新持有 source snapshot：已故意不持有以避免内存膨胀。
  - 不在下游 Memory/RunInput consumer 补偿：违反语义所有权边界。
  - 不用数量代理、label ordinal、字符串解析、测试特例：都是伪修复。
- **结论**: 该方案通过 optimal-solution review。F4 指出的 evidence content_digest
  不一致是可修复的实施细节，不否定方案本身。
- **严重程度**: 低（确认性 finding，非缺陷）

## Open Questions

1. **Evidence content_digest 不一致** (F1): 若采用方案 A（provenance 使用
   `_text_digest(accepted_tool_evidence.result_text)`），是否需要在
   `SelectedBlockProvenance` 的 docstring 中明确说明 evidence 的特殊 digest 来源？
   回答应为"是"——否则未来维护者可能误认为所有 content_digest 都来自
   `RunInputMaterialBlock.content_digest`。

2. **Transient proof subset 验证是否可以推迟到 F11**: F1 和 F3 是 correctness 问题，
   必须在 F10 闭合；F2 是 defense-in-depth，若当前 pass_queue 的 turn_group_memberships
   和 boundary partition 验证已经足够，F2 可作为 deferred enhancement。
   建议：仍纳入 F10 scope，因为它直接对应 plan 的 success signal
   "unknown selected id fail closed"。

## Residual Risks

- **digest 计算的一致性**: 当前系统中 `content_digest` 使用 `sha256_digest_json({"text": text})`
  作为 canonical 形式。`SelectedBlockProvenance` 的 `content_digest` 也必须使用同一
  canonical 形式。F1 修复后，应确保 evidence provenance 的 digest 使用同一函数且
  同一输入源。

- **selection_digest 重构验证**: 当前 selection_digest 只在构造时计算一次，没有
  reconstruct-verify 步骤。若未来增加该步骤，F3 的排序不一致可能暴露。建议在 freeze
  修复中一并解决。

## Final Plan Review Conclusion

**NEEDS_FIX**

F1（evidence content_digest 不一致）是高严重度 correctness gap —— plan 当前规格
在 evidence block 路径上无法满足其自身 success signal "canonical ref/digest mismatch
在 provider 前 fail closed"，因为 digest 源不一致会导致正确 block 也被误杀。

F2（transient proof subset 验证位置）和 F3（excluded_reason_codes 排序）是中严重度
可修复问题，不影响方案整体方向。

F4（dedup 语义区分）是低严重度 clarity issue。

所有 finding 均有直接代码证据，不需要修改 accepted plan 的产品语义、LLM schema、
Memory consumer 或五类 Memory fallback policy。

建议修复后重新提交 plan review。
