# Code Review：Interactive Conversation Memory closure F10 — DS 第二路独立 code review

## Scope

- **Mode**: current changes（未提交 workspace diff）
- **Branch**: `codex/interactive-oracle`
- **Base**: `d04f7531f3a7bfef2de004afbb94b2d607704b36`（accepted F09 commit）
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f10-code-review-ds.md`
- **Included scope**: 全部 17 个 changed files：
  - Production: `dayu/host/compact_material.py`, `compact_pipeline.py`, `compaction.py`, `compaction_operation.py`, `context_governance.py`, `dispatch.py`
  - Docs: `docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`
  - Tests: `test_compact_material.py`, `test_compact_pipeline.py`, `test_compaction_contract.py`, `test_compaction_operation.py`, `test_dispatch_scheduler.py`, `test_llm_compaction.py`, `test_public_compact_smoke.py`, `test_runner_call_hot_payload_contract.py`
- **Excluded scope**: `docs/reviews/` 下的 MiMo review artifact（按要求不得参考）；Engine、Memory projector、RunInput consumer 未修改故不纳入
- **Parallel review coverage**: 无。本 review 为 DS 单路全量走读。

## 前置：DS re-review（plan amendment re-review）finding 交叉验证

DS 对 plan amendment implementation 的 re-review（`wu-interactive-memory-closure-f10-plan-amendment-rereview2-ds.md`）提出了 F1–F4 四个未关闭 finding 与 N1–N5 五个新增观察。本次 code review 先逐项交叉验证这些 finding 的当前状态，再进行独立 adversarial 检查。

### F1（evidence content_digest 不一致）→ **已关闭**

**DS re-review 判定**: 部分关闭 / latent risk。`_provenance_from_evidence_blocks` 使用 `source.content_digest`（四行 render hash），`_pack_evidence_blocks` 使用 `_text_digest(material.result_text)`（仅 result_text hash）。

**当前代码证据**:

- `_packed_content_digest`（`compact_material.py:1674-1686`）是统一 helper：
  ```python
  def _packed_content_digest(block: RunInputMaterialBlock) -> str:
      if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE:
          ...
          return _text_digest(block.accepted_tool_evidence.result_text)
      return _text_digest(block.text)
  ```
- 四个调用点全部使用该 helper：
  - `selected_block_provenance_for_material_blocks:1939`（provenance producer）：`_packed_content_digest(block)`
  - `_compact_material_block:2888`（ordinary block packer）：`_packed_content_digest(block)`
  - `_pack_evidence_blocks:2915`（evidence block packer）：`_packed_content_digest(block)`
  - `_provenance_from_evidence_blocks:2975`（evidence provenance map producer）：`_packed_content_digest(source)` ← diff 确认从 `source.content_digest` 改为 `_packed_content_digest(source)`

**结论**: 四个调用点 digest 来源完全一致。DS re-review 的 N1 latent inconsistency 已不存在。

---

### F2（transient per-block subset 验证）→ **已关闭**

**DS re-review 判定**: 未完全关闭。`_operation_pass_requests` 不验证 transient selected_block_ids ⊆ root selected_block_ids；`_single_block_segment_selection` 不验证 block_id ∈ root selected_block_ids。

**当前代码证据**:

1. `_single_block_segment_selection`（`compact_pipeline.py:1060-1066`）：
   ```python
   root_provenance = tuple(
       provenance
       for provenance in root_request.segment_selection.selected_block_provenance
       if provenance.block_id == block_id
   )
   if len(root_provenance) != 1:
       raise ValueError("reactive pass block provenance is not present exactly once in root")
   ```
   **反例验证**: 若 block_id 不在 root 的 selected_block_provenance 中 → `len(root_provenance) == 0` → raise。phantom block 被拦截 ✓

2. `_operation_pass_requests`（`compaction_operation.py:1536-1539`）：
   ```python
   for provenance in pass_request.segment_selection.selected_block_provenance:
       root_provenance = root_provenance_by_id.get(provenance.block_id)
       if root_provenance is None or provenance != root_provenance:
           raise ValueError("pass_queue selected block provenance is not an exact root subset")
   ```
   **双重验证**: block_id 必须在 root provenance 中存在（`root_provenance is not None`）**且**逐字段完全相等（`provenance != root_provenance` → 包括 refs 和 digest）。单独 block_id 匹配或单独值匹配均不通过 ✓

**结论**: per-block exact subset 验证在 `_single_block_segment_selection` 和 `_operation_pass_requests` 两层均实现，且使用 `!=` 全字段比较而非仅 block_id 匹配。

---

### F3（excluded_reason_codes sorted copy + freeze）→ **已关闭**

**DS re-review 判定**: 部分关闭。digest/to_json 一致性通过排序保证，但 `__post_init__` 缺少 copy+sort+freeze。

**当前代码证据**:

`CompactSegmentSelection.__post_init__`（`compaction.py:1977-1985`）：
```python
sorted_excluded_reasons = {
    block_id: self.excluded_reason_codes[block_id]
    for block_id in sorted(self.excluded_reason_codes)
}
object.__setattr__(
    self,
    "excluded_reason_codes",
    MappingProxyType(sorted_excluded_reasons),
)
```

**验证链**:
1. `sorted(self.excluded_reason_codes)` → key 排序
2. 从排序 keys 构造新 dict → 独立 copy（外部原 dict 被修改不影响存储值）
3. `MappingProxyType(...)` → 只读视图（`frozen=True` dataclass + MappingProxyType 双重不可变）
4. `to_json()` 调用 `_string_mapping_json`（`compaction.py:3172-3182`）→ 也按 `sorted(values)` 输出
5. digest 计算使用 `_ordered_reason_mapping`（`compact_material.py:2115-2122`）→ 也按 key 排序

**测试覆盖**: `test_excluded_reason_mapping_is_sorted_copied_and_read_only`（`test_compact_material.py:440`）验证了 MappingProxyType 类型、排序不变性、外部 mutation 不影响存储值、TypeError on mutation attempt。

**结论**: sorted copy + MappingProxyType freeze 已实现。digest、JSON 序列化、存储值三者同源。

---

### F4（same-text dedup / content_digest fallback）→ **已关闭**

**DS re-review 判定**: 未关闭。`_is_current_input_history_duplicate` 的 content_digest fallback（`compact_material.py:2751`）未被删除。

**当前代码证据**:

1. `_is_current_input_history_duplicate` 函数已被**完全删除**。`git show d04f7531:dayu/host/compact_material.py | grep -n "_is_current_input_history_duplicate"` 确认 base 中存在（line 2584），当前代码中**不存在**。

2. `_selected_material_blocks`（`compact_material.py:2817-2836`）不再接收 `current_anchor` 参数，不再有 `continue` skip 逻辑：
   ```python
   def _selected_material_blocks(
       selected_block_ids: tuple[str, ...],
       material_blocks: tuple[RunInputMaterialBlock, ...],
   ) -> tuple[RunInputMaterialBlock, ...]:
       ...
       for block_id in selected_block_ids:
           block = block_by_id.get(block_id)
           if block is None:
               raise ValueError(...)
           selected.append(block)  # 不再有 continue skip
       return tuple(selected)
   ```

3. `build_compact_material_pack`（`compact_pipeline.py:921`）不再传递 `current_anchor` 给 `_selected_material_blocks`。

4. Same-ref fail-closed 在两层实现：
   - Pipeline: `_validate_selected_pack_current_input_separation`（`compact_pipeline.py:1008-1025`），在 request 构造后立即调用（line 931）
   - Operation: `_validate_operation_selected_pack`（`compaction_operation.py:1621-1623`），provider 前再次检查

**测试覆盖**:
- `test_same_text_different_ref_preserves_complete_selected_group`（`test_compact_pipeline.py:383`）验证相同文本不同 ref 的 block 完整保留
- `test_same_canonical_current_ref_fails_during_pipeline_request_build`（`test_compact_pipeline.py:418`）验证相同 ref 在 pipeline 中 fail closed
- `test_current_input_ref_overlap_fails_before_provider_call`（`test_compaction_operation.py:572`）验证绕过 pipeline 注入时 operation 仍 fail closed

**结论**: `_is_current_input_history_duplicate` 及其 content_digest fallback 已完全删除。packer 不再做任何 selected block dedup。same-ref 在 pipeline 和 operation 两层 fail closed。

---

## Findings

### 1-NEEDS_FIX-低-`_validate_operation_selected_pack` 的 sorted multiset 比较不防御 whole-provenance 交换

- **入口/函数**: `_validate_operation_selected_pack`（`compaction_operation.py:1596`），通过 `_sorted_selected_provenance_values` 做 sorted multiset 比较
- **文件(行号)**: `dayu/host/compaction_operation.py:1604-1620`
- **输入场景**: 攻击者构造一个 root request，其中 selected_block_provenance 把 A 和 B 的 `(canonical_source_refs, packed_content_digest)` 整体交换（即 A 的 provenance 拿到 B 的 refs+digest，B 的拿到 A 的）
- **实际分支**: `_sorted_selected_provenance_values` 返回按 `(canonical_source_refs, packed_content_digest)` tuple 排序的列表。如果 A↔B 交换了完整的 refs+digest，排序后 multiset 不变
- **预期行为**: 任何 provenance 与 pack 的不一致都应被检测
- **实际行为**: sorted multiset 比较通过（因为排序后 `((R_A, D_A), (R_B, D_B))` 在交换后仍是 `((R_A, D_A), (R_B, D_B))`），且 pack 的 sorted values 也匹配
- **直接证据**:
  - `_sorted_selected_provenance_values`（line 1626-1643）使用 `sorted()` 而非 per-block_id 一一对应比较
  - `_validate_operation_selected_pack`（line 1619）比较 `proof_values != pack_values`，两者都用 `sorted()`
  - 对比：`_operation_pass_requests`（line 1536-1539）对 transient pass 使用 **per-block_id 精确相等**（`provenance != root_provenance`），更强
- **影响**: 当前不可利用——pipeline `_validate_segment_against_source_snapshot`（`compact_pipeline.py:994-998`）在 request 构造前会从 source snapshot 重建 expected provenance 并做 **逐字段精确比较**（`!=`），会先一步拦截此攻击。但若未来任何代码路径绕过 pipeline 直接构造 `CompactionRequest` 并调用 `run_compaction_operation`，operation 层的 sorted multiset 比较将漏过此攻击
- **建议改法和验证点**:
  1. 将 `_validate_operation_selected_pack` 的 proof-vs-pack 比较从 sorted multiset 改为 per-block_id 精确对应，与 `_operation_pass_requests` 的验证风格一致
  2. 或者保留 sorted multiset 作为 defense-in-depth，但在 `_validate_operation_root_request` 中增加与 pipeline 同源的 provenance 重建比较（即从 `source_boundary` 或 pack 反向重建 expected provenance）
  3. 验证点：添加 `test_root_whole_provenance_swap_fails_before_provider` 测试，构造 A↔B 完整交换的 forged request 并断言 `run_compaction_operation` 返回 non-repairable failure
- **修复风险（低）**: 修改仅限于 operation 内部验证逻辑，不改变 product behavior。per-block_id 比较比 sorted multiset 更严格，可能暴露既有的 latent inconsistency（若有），但这正是修复的目的
- **严重程度（低）**: pipeline 层已有独立验证拦截此场景；operation 层 gap 仅在 pipeline 被绕过时暴露。当前所有 request 构造路径均经过 pipeline

---

### 2-NEEDS_FIX-低-`_validate_segment_against_source_snapshot` 对 transient scope 不验证 selected 与 root 的关系

- **入口/函数**: `_validate_segment_against_source_snapshot`（`compact_pipeline.py:969`）
- **文件(行号)**: `dayu/host/compact_pipeline.py:1000-1005`
- **输入场景**: 假想的 transient `CompactSegmentSelection`，其 `selected_block_ids` 包含 source snapshot 中存在但 root selection 排除的 block_id，且 `selected_block_provenance` 与 source snapshot 一致
- **实际分支**: 对 transient scope（line 1004），只检查 `root_selection_digest is not None`，跳过了 root scope 的 `selected_ids.union(excluded_ids) != known_ids` 完整 partition 检查
- **预期行为**: 对 transient scope 也应验证 selected block_ids 是 root selected block_ids 的子集，或至少验证 transient 的 provenance 来自 root provenance 的子集
- **实际行为**: 跳过此检查，依赖下游 `_operation_pass_requests` 做最终验证
- **直接证据**:
  - `compact_pipeline.py:1000`: `if selected_segment.scope is CompactSegmentSelectionScope.ROOT:` → root scope 做完整 partition 检查后 `return`
  - `compact_pipeline.py:1004-1005`: transient scope 仅检查 `root_selection_digest is None` → raise
  - 当前 transient selection 的唯一构造器 `_single_block_segment_selection`（line 1060-1066）在构造时验证 block_id 存在于 root provenance 中，因此 pipeline 层的 gap 不可利用
- **影响**: 与 Finding 1 类似——当前因唯一构造器保护而不可利用，但 pipeline 层验证不完整，依赖 operation 层补偿
- **建议改法和验证点**:
  1. 在 `_validate_segment_against_source_snapshot` 的 transient 分支中增加：transient `selected_block_provenance` 的每个 entry 必须是 root（调用方传入 `root_segment: CompactSegmentSelection` 参数）`selected_block_provenance` 的子集
  2. 或至少验证 transient 的 `root_selection_digest` 与传入 root 的 `selection_digest` 一致（当前只验证非 None，不验证具体值）
  3. 注意：当前函数签名不接收 root_segment 参数，需先扩展签名
- **修复风险（低）**: 需要扩展函数签名（新增 `root_segment` 参数），但调用方 `build_normal_compact_request_plan` 和 `build_recovery_compact_request_plan` 都可以提供 root
- **严重程度（低）**: 当前调用路径安全，属 defense-in-depth gap

---

## Adversarial 逐项检查结果

以下各项均通过独立 code path 走读验证，未发现 correctness bug。

### Semantic owner 漂移 / 下游补偿 / 兼容代码 / schema 或 public surface 扩大

- **Turn-group membership owner**: `compact_material.py` 的 `turn_group_memberships_for_material_blocks` 是唯一 producer；`CompactSegmentSelection.__post_init__` 是唯一 validator；pipeline 和 operation 只消费。无下游重算 ✓
- **SelectedBlockProvenance owner**: `selected_block_provenance_for_material_blocks`（`compact_material.py:1908`）是唯一 producer；`_validate_segment_against_source_snapshot` 重建验证。无 fallback ✓
- **Excluded mapping owner**: `CompactSegmentSelection.__post_init__` 是 canonical storage；`_ordered_reason_mapping` 和 `_string_mapping_json` 提供排序投影。无下游重排 ✓
- **Feedback owner**: `build_compact_repair_feedback_v2`（`context_governance.py:117`）是唯一 typed constructor。所有调用方显式传入 `request_digest` 和 `source_boundary_digest`；无默认值、optional shim 或旧 digest fallback ✓
- **No compatibility code**: diff 中无兼容性 re-export、wrapper/facade 或旧接口保留 ✓
- **Public surface**: `dayu/host/compaction.py` 的 `__all__` 等价物（line 3498 附近）新增了 `CompactSegmentSelectionScope`、`TurnGroupMembership`、`SelectedBlockProvenance`。这些是 Host-internal 类型，不出现在 `dayu/__init__` 或 public API 中 ✓

### Turn-group atomicity、strict-prefix item/char budget、无超限 first-unit 特例

- **集体排除**: `select_compact_segment`（`compact_material.py:851-860`）先对每个 atomic unit 做 collective exclusion；任一 member 命中 protected/already-represented/previous/not-in-segment 即整组排除 ✓
- **Atomic unit 构造**: `_atomic_material_units` 按 stable material order 归并相同 `turn_group_id` 的 blocks 为 group，无 group 的 block 为 singleton ✓
- **Strict prefix budget**: lines 865-885 — `budget_blocked` flag 在首个 oversized unit 时置为 `True`，该 unit 不入选（全部标 `budget_limit`），**之后所有 eligible unit** 也全部 `budget_limit`。无"跳过 oversized 继续选更小 unit"的特例 ✓
- **Item budget 使用真实 block 数**: `unit_item_count = len(unit.blocks)`（line 871），turn group 内三个 blocks（user/tool/answer）计为 3 items ✓
- **Exact cap 可选**: `max_selected_size_units` 和 `max_selected_item_count` 均为 Optional；None 时不限制 ✓
- **Test**: `test_turn_group_selection_uses_real_block_count_and_never_splits`（3 blocks，cap=2 items → 整组排除）、`test_turn_group_char_cap_accepts_exact_total_and_rejects_one_less`（exact cap 通过，少一字排除）✓

### SelectedBlockProvenance fail-closed

- **Unknown block_id**: `_operation_pass_requests:1537` — `root_provenance_by_id.get(provenance.block_id)` 返回 `None` → raise ✓
- **Same-count swap（等数量替换）**: `_operation_pass_requests:1538` — `provenance != root_provenance` 逐字段比较，refs/digest 任一不同即 raise ✓
- **Singleton swap**: 同上。singleton 也是通过 per-block_id exact match 验证 ✓
- **Group swap**: turn_group_memberships 在 `_operation_pass_requests:1533` 做 tuple 相等比较；任一 member 变动 → mismatch ✓
- **Ref tamper**: `_operation_pass_requests:1538` — `!=` 比较包含 `canonical_source_refs` ✓
- **Digest tamper**: `_operation_pass_requests:1538` — `!=` 比较包含 `packed_content_digest` ✓
- **Transient tamper（绕过 `_single_block_segment_selection`）**: `_operation_pass_requests:1536-1541` 对每个 pass 逐项检查，且 `observed_pass_block_ids` 防重叠 ✓
- **Pipeline 层重建验证**: `_validate_segment_against_source_snapshot:994-998` 从 source snapshot 重建 expected provenance 并做 tuple 精确比较 ✓
- **Test**: `test_root_selected_provenance_mismatch_fails_before_provider_call` 参数化测试了 unknown_block / source_ref / digest 三种 mismatch，全部验证 provider 未被调用 + `failure_reason == "proposal_failed"` + `repairable is False` ✓

### Root/transient exact partition 无重叠遗漏

- **Pass boundary partition**: `_operation_pass_requests:1547-1552` — 收集所有 pass 的 source_boundary entries，验证 label 集合与 root 完全一致（`pass_entries_by_label != root_entries_by_label` → raise）✓
- **Selected block partition**: `_operation_pass_requests:1551-1552` — 验证 `observed_pass_block_ids != set(root_provenance_by_id)` → raise ✓
- **Root scope 完整 partition**: `_validate_segment_against_source_snapshot:1000-1002` — `selected_ids.union(excluded_ids) != known_ids` → raise ✓
- **Root turn-group 二分**: `_validate_operation_root_request:1578-1581` — 每个 turn group 必须 `issubset(selected)` 或 `issubset(excluded)`；部分选中 → raise ✓
- **CompactSegmentSelection.__post_init__:1992-1996** — 同样验证 root turn group 二分 ✓

### Same-text/different-ref 保留、same-ref current anchor provider 前失败

- **Same-text/different-ref 保留**: `_is_current_input_history_duplicate` 已删除；`_selected_material_blocks` 不跳过任何 block ✓
- **Pipeline same-ref fail-closed**: `_validate_selected_pack_current_input_separation`（`compact_pipeline.py:1008-1025`）在 `build_normal_compact_request_plan:931` 调用；检查 selected history/evidence/answer 的 canonical refs 是否与 current anchor 重叠 → raise ✓
- **Operation same-ref fail-closed**: `_validate_operation_selected_pack:1621-1623` 在 provider 前再次检查 ✓
- **Test**: `test_same_text_different_ref_preserves_complete_selected_group`（完整 group 保留）、`test_same_canonical_current_ref_fails_during_pipeline_request_build`（pipeline fail closed）、`test_current_input_ref_overlap_fails_before_provider_call`（绕过 pipeline 时 operation fail closed）✓

### Excluded mapping sorted-copy/read-only/digest 同源

- **Sorted copy**: `CompactSegmentSelection.__post_init__:1977-1984` — `sorted()` + 新 dict + `MappingProxyType` ✓
- **Read-only**: `MappingProxyType` 阻止写入；`frozen=True` dataclass 阻止字段替换 ✓
- **Digest 同源**: digest 计算使用 `_ordered_reason_mapping`（key-sorted）；`to_json()` 使用 `_string_mapping_json`（key-sorted）；存储值使用 `MappingProxyType(sorted_excluded_reasons)`（key-sorted）→ 三处同序 ✓
- **Test**: `test_excluded_reason_mapping_is_sorted_copied_and_read_only` 验证 MappingProxyType 类型、reverse-order 构造仍排序、外部 mutation 不影响、TypeError on mutation ✓

### Repair feedback request+source-boundary binding 与 cross-tier 清除

- **Constructor 强制双 digest**: `build_compact_repair_feedback_v2` 新增 `request_digest` 和 `source_boundary_digest` 必填参数；`CompactRepairFeedbackV2.__post_init__` 验证两者非空 ✓
- **Dispatcher binding**: `_repair_feedback_for_request`（`dispatch.py:5803-5822`）比较 `feedback.request_digest != request.digest()` 和 `feedback.source_boundary_digest != request.source_boundary_digest()`；任一不匹配 → 返回 `None`（清空）✓
- **Operation defense-in-depth**: `_repair_feedback_matches_request`（`compaction_operation.py:1646-1660`）做同样检查，防止绕过 dispatcher ✓
- **Non-repairable terminal**: `_compaction_result_is_non_repairable`（`dispatch.py:5825-5839`）→ 停止 schedule；`CONTEXT_COMPACTION_FAILED` 只写一次 ✓
- **Test**: `test_defensive_feedback_mismatch_stops_schedule_with_single_terminal`（`test_dispatch_scheduler.py:8191`）— monkeypatch 绕过 dispatcher 清理，验证 operation 拒绝 mismatch、只产生一个 terminal ✓

### F09 fixture 迁移只修真实 consumer

- `test_runner_call_hot_payload_contract.py` 的 `_compactor_manifest` fixture 变更：
  - Base: `value.pop("runner_call_projection_artifact_ref")` 等三个 pop
  - New: 设置 compactor-specific 值（`"payload-compactor-runner-call-projection"`、`sha256_digest_json({"projection": "compactor-hot-contract"})`、`192`）
  - 这 6 个字段的变更仅服务于 compactor 测试的 manifest contract；production `runner_call_hot_payload` 和 `complete_runner_call_hot_diagnostic` 未增加兼容 fallback ✓
- `test_compaction_contract.py` 和 `test_public_compact_smoke.py` 的变更：只因 `build_compact_repair_feedback_v2` 新增必填参数而更新调用点，传入真实的 `request.digest()` 和 `request.source_boundary_digest()` ✓

### Memory/RunInput/LLM-facing 无治理字段泄漏

- **LLM repair projection**: `_repair_feedback_prompt_json_vnext`（`llm_compaction.py:680-703`）只投影 `required_action` 和 `issues`（code/json_path/message/source_labels）→ 不含 `request_digest` 和 `source_boundary_digest` ✓
- **Test assertion**: `test_llm_compaction.py:263-264` — `assert "request_digest" not in projected` 和 `assert "source_boundary_digest" not in projected` ✓
- **LLM material JSON**: `CompactMaterialPack.llm_material_json()`（`compaction.py:2310-2316`）委托给 `compact_input.to_json()` → 不含 `SelectedBlockProvenance`、`TurnGroupMembership`、`selection_digest` 等治理字段 ✓
- **Memory projection**: 未修改；F10 不改变 Memory 写入路径 ✓
- **RunInput**: 未修改；F10 不改变 RunInput 结构 ✓

### 其他检查项

- **Raw snapshot retention**: canonical source snapshot（`CompactPipelineSourceSnapshot.material_blocks`）始终保留完整 raw blocks；tier 1–3 只消费 atomic selection view；tier 4/5 fallback 从完整 snapshot 派生。`_selected_material_blocks` 和 `_fallback_selection` 均从 snapshot 读取 ✓
- **Aggregate-root-only durable accept**: `run_compaction_operation` 只在 root path（`_operation_pass_requests` 返回单元素 `(request,)` 且验证通过）产生 `CompactAcceptedTruthV2`；transient pass 不写 artifact、Memory 或 terminal ✓
- **Provider count 为零**: non-repairable failure 路径（如 provenance mismatch）不调用 compactor；`compactor.prepared_inputs == []` 和 `compactor.run_calls == 0` 在测试中断言 ✓
- **类型安全**: 无 `hasattr`/`getattr` 新增使用；无 `Any`/`object` 新增；`SelectedBlockProvenance`、`TurnGroupMembership`、`CompactRepairFeedbackV2` 均为 `frozen=True, slots=True` dataclass ✓
- **Docstring**: 所有新增 public 和 private 函数提供中文 docstring ✓
- **README 更新**: `dayu/host/README.md`、`docs/host/design.md`、`tests/README.md` 已更新，内容与代码一致 ✓

---

## Open Questions

无。

---

## Residual Risk

1. **Whole-provenance swap at operation layer**（对应 Finding 1）: `_validate_operation_selected_pack` 的 sorted multiset 比较在 pipeline 被绕过时无法防御 A↔B 完整交换。当前所有 request 构造路径均经过 pipeline 的 `_validate_segment_against_source_snapshot`（逐字段精确比较），故此风险仅当未来新增绕过 pipeline 的 request 构造路径时暴露。

2. **Transient validation layering**（对应 Finding 2）: pipeline 层 `_validate_segment_against_source_snapshot` 对 transient scope 的验证较轻，依赖 operation 层补偿。当前 transient 构造器 `_single_block_segment_selection` 做了充分验证，故此风险仅当未来新增 transient 构造路径时暴露。

3. **Initial segment selection 使用 prompt-local labels 作为 block_ids**: `initial_segment_selection`（`compact_material.py:1373-1427`）的 `selected_block_ids` 和 `excluded_reason_codes` keys 是 prompt-local labels（如 "T.1"），而非 `RunInputMaterialBlock.block_id`。此设计对 initial（无 raw material blocks）场景正确，但若 future code 将 initial selection 与 recovery selection 混合使用，block_id 语义差异可能导致混淆。当前无此使用场景。

4. **五条正式 CLI scenarios 未运行**: 按明确禁令未运行。真实 provider 对 F08/F09/F10 的端到端行为留待后续 evidence/readiness gate。

5. **全树 Ruff lint/format**: F10 pathspec 已 clean；全树既有 debt 不在 scope 内。

---

## Final Conclusion

**PASS**

本次 F10 implementation 完成了 accepted plan amendment 和 controller adjudication 的全部要求：

- `SelectedBlockProvenance` 类型已实现，`_packed_content_digest` 作为统一 helper 服务于全部四个调用点
- Turn-group atomic selection、strict prefix budget、collective exclusion 全部落实
- Per-block provenance exact equality verification 在 `_single_block_selection`、`_operation_pass_requests`、`_validate_segment_against_source_snapshot` 三层实现
- Packer dedup 已完全移除；same-text/different-ref 保留、same-ref fail-closed 两层验证
- Excluded mapping sorted copy + MappingProxyType freeze 已实现
- Dual-digest feedback binding 在 constructor、dispatcher、operation 三层落实
- F09 fixture consumers 已迁移，只修真实 consumer
- LLM-facing 投影不含治理字段
- 测试覆盖了 adversarial 场景（unknown id、ref/digest tamper、same-count swap、same-text/different-ref、same-ref fail-closed、excluded mapping immutability、feedback mismatch defensive guard 等）

两个 low-severity finding（1 和 2）属于 defense-in-depth gap，当前调用路径安全，不阻塞 ship。建议在后续迭代中加固。
