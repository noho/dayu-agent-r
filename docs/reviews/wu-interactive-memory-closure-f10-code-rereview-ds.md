# Code Review Re-Review：Interactive Conversation Memory closure F10 — 第二独立路线 adversarial 复核

## Scope

- **Mode**: current changes（未提交 workspace diff）
- **Branch**: `codex/interactive-oracle`
- **Base**: `d04f7531f3a7bfef2de004afbb94b2d607704b36`（accepted F09 commit）
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f10-code-rereview-ds.md`
- **Reviewed artifacts**:
  - DS initial code review: `wu-interactive-memory-closure-f10-code-review-ds.md`（F1–F4 + DS-1, DS-2）
  - MiMo initial code review: `wu-interactive-memory-closure-f10-code-review-mimo.md`（12 PASS items）
  - Codex fix artifact: `wu-interactive-memory-closure-f10-code-review-fix-codex.md`（DS-1, DS-2 rejected-with-reason）
  - Controller adjudication: `wu-interactive-memory-closure-f10-plan-amendment-controller-adjudication.md`
- **Included scope**: 全部 17 个 changed files（同 DS 原 review）
- **Excluded scope**: 五条正式 CLI scenarios（按要求不运行）；`docs/reviews/` 下的 plan/amendment 过程 artifact
- **Parallel review coverage**: 无。本 re-review 为 DS 单路全量走读。

## Review 目标

1. 对 DS initial code review 中的 DS-1（operation refs/digest sorted multiset）和 DS-2（transient pipeline layering）做 adversarial 复核：Codex 的 rejected-with-reason 是否确实不改变 durable semantic set、是否所有 producer/provider 路径都由 snapshot exact proof 或 operation exact partition 覆盖、是否存在手工构造/stale request 在 provider 前通过的产品反例。
2. 确认 F1–F4 及原 MiMo PASS 项未回归。
3. 逐项给直接证据。不得为纯 defense-in-depth 观察强行扩大 schema 或复制 owner。

## DS-1 adversarial 复核：operation refs/digest sorted multiset

### Codex 裁决回顾

DS initial review 提出 `_validate_operation_selected_pack` 使用 sorted multiset 比较，若 A↔B 整体交换 (refs, digest)，sorted multiset 不变，operation 层无法发现。Codex fix artifact 将此裁决为 `rejected-with-reason`，理由：

1. Pipeline owner 从 raw snapshot 做 per-block_id exact proof 验证
2. Operation 的 sorted multiset 是信息约束下的正确工具（pack 不携带 block_id）
3. A↔B 整体交换不改变 durable business truth
4. Transient path 使用 per-block_id exact equality

### 独立复核

#### 路径 1：Pipeline producer → Operation（正常构造路径）

**Pipeline 层 proof 验证**（`_validate_segment_against_source_snapshot`，`compact_pipeline.py:969`）：

- Line 994-996：从同一 raw snapshot 按 `selected_block_ids` 顺序逐一重建 `expected_provenance`
- Line 998：`selected_segment.selected_block_provenance != expected_provenance` → **逐元素 frozen dataclass `__eq__` 比较**

```python
# compact_pipeline.py:994-998
expected_provenance = selected_block_provenance_for_material_blocks(
    source_snapshot.material_blocks,
    selected_block_ids=selected_segment.selected_block_ids,
)
if selected_segment.selected_block_provenance != expected_provenance:
    raise ValueError("segment selected block provenance does not match source snapshot")
```

- `selected_block_provenance_for_material_blocks`（`compact_material.py:1930-1942`）对每个 `selected_block_ids[i]` 从 `block_by_id[block_id]` 读取 raw block 并用 `_packed_content_digest(block)` 计算 digest → 构造 `SelectedBlockProvenance`
- `!= `在 frozen dataclass tuple 上是**逐位置元素**比较，不是 multiset 比较。A↔B 交换后 element[0] ≠ expected[0] → raise

**直接证据**：若 A（id="a", refs=("R_A",), digest="D_A"）与 B（id="b", refs=("R_B",), digest="D_B"）在 selection 中交换 provenance，则 `selected_block_ids = ("a", "b")`，`expected_provenance = (Provenance("a", "R_A", "D_A"), Provenance("b", "R_B", "D_B"))`，但 `selected_block_provenance = (Provenance("a", "R_B", "D_B"), Provenance("b", "R_A", "D_A"))` → `!=` → raise。

**Operation 层 multiset 验证**（`_validate_operation_selected_pack`，`compaction_operation.py:1596`）：

- Line 1604-1618：分别从 proof 和 pack 提取 `(canonical_source_refs, packed_content_digest)` 对，sort 后比较 tuple
- **关键事实**：pack 不携带 `block_id`（`CompactMaterialBlock` 的 `block_label` 是 prompt-local 标签，非 source `block_id`），pack 顺序由 section（trace/evidence/answer）决定而非由 source 顺序决定。在 operation 层使用 block_id 做逐元素比较需要依赖 section order 假设或把 block_id 塞入 pack schema，两者均违反 accepted 最小设计。

**Operation root identity 验证**（`_validate_operation_root_request`，`compaction_operation.py:1556`）：

- Line 1574-1575：`tuple(provenance.block_id for provenance in selection.selected_block_provenance) != selection.selected_block_ids` → **额外验证 block_id 顺序一致性**

#### 路径 2：手工构造绕过 pipeline（攻击场景）

**前提**：攻击者直接构造 `CompactionRequest` 调用 `run_compaction_operation`，绕过 pipeline 的 `_validate_segment_against_source_snapshot`。

**场景 A**：交换 A/B proof 但 pack 不变
- Proof values = `((R_B, D_B), (R_A, D_A))`（sorted）
- Pack values = `((R_A, D_A), (R_B, D_B))`（sorted，因为 pack 未改）
- `proof_values != pack_values` → raise（line 1619）✓

**场景 B**：交换 A/B proof 且同时交换 pack 对应 block
- Proof values = `((R_A, D_A), (R_B, D_B))`（sorted，两者都交换后 multiset 不变）
- Pack values = `((R_A, D_A), (R_B, D_B))`（sorted，两者都交换后 multiset 不变）
- 比较通过。但**进入 provider 的实际材料不变**：仍是同一组 (refs, digest) 对 → 不改变 durable business truth ✓

**场景 C**：将 selected A 替换为 excluded B（不等数量/不等内容）
- Proof multiset ≠ Pack multiset → raise（line 1619）✓
- 测试 `test_root_selected_provenance_mismatch_fails_before_provider_call`（`test_compaction_operation.py:513`）参数化覆盖 `unknown_block`/`source_ref`/`packed_digest` 三种 mismatch，全部验证 `compactor.prepared_inputs == []`、`compactor.run_calls == 0`、`failure_reason == "proposal_failed"`、`repairable is False` ✓

**场景 D**：完整 group swap（等数量但不同 block）
- 测试 `test_whole_group_swap_proof_fails_before_provider`（`test_compact_pipeline.py:585`）：两组 block 整体交换 → `run_calls == 0`、`failure_reason == "proposal_failed"` ✓

#### 路径 3：Transient path

`_operation_pass_requests`（`compaction_operation.py:1496`）：

- Line 1536-1539：**per-block_id exact root subset**，不只是 multiset：
  ```python
  root_provenance = root_provenance_by_id.get(provenance.block_id)
  if root_provenance is None or provenance != root_provenance:
      raise ValueError(...)
  ```
- Line 1540-1542：pass 间无重叠
- Line 1551-1552：全体 pass 无遗漏

Transient path 的验证比 root path 更强——使用了 per-block_id 精确比较，而不是 sorted multiset。

### DS-1 结论

**rejected-with-reason 成立**。Pipeline owner 通过 per-block_id exact proof 验证保证了 A↔B 交换在正常构造路径中不可行。Operation 的 sorted multiset 是当前层信息约束下的正确工具；A↔B 同时交换 proof 和 pack 时 multiset 不变，但实际进入 provider 的材料不变，不产生错误的 durable accepted truth。将 multiset 改为 per-block_id pack compare 需要把 block_id 塞入 pack 或依赖 section ordinal 假设，违反 accepted 最小 schema 且不关闭新的 correctness 反例。

---

## DS-2 adversarial 复核：transient pipeline layering

### Codex 裁决回顾

DS initial review 提出 `_validate_segment_against_source_snapshot` 对 transient scope 不验证 selected 与 root 的 subset 关系。Codex fix artifact 将此裁决为 `rejected-with-reason`，理由：

1. Snapshot validator 对 root/transient 共用的职责完整
2. Root relationship 由唯一 producer `_single_block_segment_selection` 独占
3. `_operation_pass_requests` 做最终 per-block_id exact root subset 验证
4. 没有绕过 operation 的 provider path

### 独立复核

#### Transient producer 路径（唯一构造器）

两个 transient 生产者均在 `compact_pipeline.py`：

1. **`build_reactive_pass_queue_plan`**（line 579）：对每个 selected block 调用 `_single_block_segment_selection`
2. **`_single_block_segment_selection`**（line 1042-1098）是唯一构造器：
   - Line 1057-1059：block_id 必须在 `material_blocks` 中
   - Line 1060-1066：block_id 必须在 root `selected_block_provenance` 中**精确出现一次**（`len(root_provenance) != 1` → raise）
   - Line 1087：`selected_block_provenance=root_provenance` → **直接取自 root proof，不重算**
   - Line 1088：`root_selection_digest=root_request.segment_selection.selection_digest` → **绑定 root digest**

#### Pipeline snapshot validator 对 transient 的职责

`_validate_segment_against_source_snapshot`（`compact_pipeline.py:969`）：

- Line 982-987（root/transient 共用）：selected_ids ⊆ known_ids 且 excluded_ids ⊆ known_ids
- Line 988-993（root/transient 共用）：turn_group_memberships == expected
- Line 994-998（root/transient 共用）：每个 selected block 的 provenance == expected（按 block_id 从 raw snapshot 逐元素重建 → **per-block_id exact**）
- Line 1000-1002（仅 ROOT）：selected ∪ excluded == known（root partition 语义）
- Line 1004-1005（仅 TRANSIENT）：root_selection_digest 非 None

**关键分析**：Snapshot validator 的 transient 分支不检查 `selected ∪ excluded = known`（这正确——transient 不需要完整 partition，只需要 subset），也不检查 transient selected 是 root selected 的子集。但 transient 的 source-snapshot identity（provenance exact match at line 998）已完整：每个 transient selected block 的 expected provenance 由原始 raw snapshot 对同一 block_id 重建，与 selection 逐元素精确比较。**这保证了 transient 不会伪造 block_id 对应的 content digest 或 source refs**。

#### Operation boundary 对手工构造 transient 的防御

`_operation_pass_requests`（`compaction_operation.py:1496`）在 provider 前对 transient 做完整验证：

- Line 1529：scope 必须是 TRANSIENT
- Line 1531：`root_selection_digest` 必须与 root 的 `selection_digest` 精确相等
- Line 1533：`turn_group_memberships` 必须与 root 完全相同（tuple equality）
- Line 1535：`_validate_operation_selected_pack` → proof multiset == pack multiset
- Line 1536-1539：**per-block_id exact root subset**——`root_provenance_by_id.get(provenance.block_id)` → None 则 raise；`provenance != root_provenance`（frozen dataclass `__eq__`）→ raise
- Line 1540-1542：pass 间 block_id 无重叠
- Line 1549-1552：全体 pass 的 source boundary 与 root exact partition、全体 block_id 与 root 无遗漏

#### 手工构造攻击场景

**攻击**：构造一个 transient request，selected block_id 存在于 raw snapshot 但已被 root **排除**。

- Pipeline validator 通过：TRANSIENT scope 不检查 selected ∪ excluded = known，且 snapshot provenance 会为该 block_id 正确重建（它在 snapshot 中存在）
- **Operation `_operation_pass_requests` line 1537 拦截**：`root_provenance_by_id.get(provenance.block_id)` 返回 `None`（该 block 已从 root selection 排除，不在 `selected_block_provenance` 中）→ raise ValueError

测试覆盖：
- `test_reactive_pass_provenance_tamper_fails_before_provider`（`test_compact_pipeline.py:515`）参数化 `root_subset` 和 `pass_pack` 两种篡改，验证 `run_calls == 0`、`failure_reason == "proposal_failed"`、`repairable is False`
- `test_whole_group_swap_proof_fails_before_provider`（`test_compact_pipeline.py:585`）验证等数量 group swap 被拦截

### DS-2 结论

**rejected-with-reason 成立**。Snapshot validator 对 transient source identity 已完整（provenance exact match、memberships match）。Root relationship 由唯一 producer `_single_block_segment_selection` 独占。Operation boundary 的 `_operation_pass_requests` 对任何绕过 producer 的 forged transient 做 per-block_id exact root subset 验证，provider 前 fail closed。给 snapshot validator 增加 `root_segment` 参数将复制 owner 且当前无第二 transient producer 或绕过 operation 的 provider path。

---

## F1–F4 回归确认

### F1（evidence packed content digest 同源）

**DS initial review**: NEEDS_FIX → Codex fix 修复 → DS code review 关闭。

**当前代码证据**（与 DS code review 时一致，未变化）:

- `_packed_content_digest`（`compact_material.py:1674-1686`）：统一 helper，ordinary 取 `_text_digest(block.text)`，evidence 取 `_text_digest(block.accepted_tool_evidence.result_text)`
- 四个调用点全部使用该 helper：
  - `selected_block_provenance_for_material_blocks:1939` → `_packed_content_digest(block)`
  - `_compact_material_block:2888` → `_packed_content_digest(block)`
  - `_pack_evidence_blocks:2915` → `_packed_content_digest(block)`
  - `_provenance_from_evidence_blocks:2975` → `_packed_content_digest(source)` ← 确认从 `source.content_digest` 改为统一 helper

**结论**: 无回归。四个调用点 digest 来源完全一致。

### F2（transient per-block exact subset）

**DS initial review**: NEEDS_FIX → Codex fix 修复 → DS code review 关闭。

**当前代码证据**（未变化）:

- `_single_block_segment_selection:1060-1066`：`len(root_provenance) != 1` → raise（block_id 必须在 root proof 中精确出现一次）
- `_operation_pass_requests:1536-1539`：per-block_id exact root subset（`root_provenance_by_id.get(provenance.block_id)` + `provenance != root_provenance`）

**结论**: 无回归。两层 per-block exact subset 验证均在。

### F3（excluded mapping sorted copy + freeze）

**DS initial review**: NEEDS_FIX → Codex fix 修复 → DS code review 关闭。

**当前代码证据**（未变化）:

- `CompactSegmentSelection.__post_init__:1977-1985`：`sorted()` + 新 dict + `MappingProxyType`
- Digest 计算使用 `_ordered_reason_mapping`（`compact_material.py:2115-2122`，key-sorted）
- `to_json()` 使用 `_string_mapping_json`（`compaction.py:3172-3182`，key-sorted）
- 测试 `test_excluded_reason_mapping_is_sorted_copied_and_read_only`（`test_compact_material.py:440`）仍然存在

**结论**: 无回归。存储值、digest、JSON 三者同源同序，只读不可变。

### F4（selected packer dedup 删除 + same-ref fail-closed）

**DS initial review**: NEEDS_FIX → Codex fix 修复 → DS code review 关闭。

**当前代码证据**（未变化）:

- `_is_current_input_history_duplicate`：grep 结果为**无匹配**——确认已完全删除
- `_selected_material_blocks:2817-2836`：不做任何 dedup，纯 block_id→block 映射，`continue` skip 逻辑不存在
- Same-ref pipeline fail-closed：`_validate_selected_pack_current_input_separation:1008-1025`
- Same-ref operation fail-closed：`_validate_operation_selected_pack:1621-1623`
- 测试覆盖：`test_same_text_different_ref_preserves_complete_selected_group`、`test_same_canonical_current_ref_fails_during_pipeline_request_build`、`test_current_input_ref_overlap_fails_before_provider_call`

**结论**: 无回归。Packer 不做 dedup；same-text/different-ref 完整保留；same-ref 两层 fail closed。

---

## 原 MiMo PASS 项逐项复核

| 项目 | 复核心 | 直接证据 |
|---|---|---|
| semantic owner / compat | PASS（未变） | `_packed_content_digest` 仍是唯一 helper；无 fallback/shim/loose parser |
| schema / LLM surface | PASS（未变） | `_repair_feedback_prompt_json_vnext` 只投影 action/issues；测试断言 `request_digest not in projected` |
| atomic selection / budget | PASS（未变） | `_atomic_material_units`、collective exclusion、strict prefix 逻辑未变 |
| provenance fail closed | PASS（未变） | 三层验证仍在（pipeline exact proof + operation multiset + transient per-id exact） |
| root/transient partition | PASS（未变） | root `selected ∪ excluded = known`；transient per-id exact subset + no overlap/omission |
| same-text/same-ref | PASS（未变） | Packer 无 dedup；same-ref pipeline/operation 拒绝 |
| excluded mapping | PASS（未变） | Key-sort copy + `MappingProxyType`；JSON/digest 同序 |
| repair binding | PASS（未变） | `_repair_feedback_for_request:5806-5824`：双 digest `!=` → return `None` |
| F09 fixture migration | PASS（未变） | `_compactor_manifest` fixture 仅修真实 consumer |
| Memory/RunInput/LLM 隔离 | PASS（未变） | Governance proof/digest 不进入 LLM-facing material |
| current anchor duplicate owner | PASS（未变） | `_raise_on_duplicate_section_owner` 跳过 CURRENT_INPUT_ANCHOR |
| initial selection | PASS（未变） | `_initial_selected_block_provenance` 从 final pack 读取 |

### 修复反馈 cross-tier 清除链路复核

- **Constructor 强制双 digest**：`build_compact_repair_feedback_v2`（`context_governance.py:117`）新增必填参数 `request_digest` 和 `source_boundary_digest`
- **Dispatcher binding**：`_repair_feedback_for_request:5819-5822` 比较 `feedback.request_digest != request.digest()` 和 `feedback.source_boundary_digest != request.source_boundary_digest()`；任一不匹配 → return `None`
- **Dispatcher 调用点**：`_execute_proactive_compaction:2294-2297`，在每次 `run_compaction_attempt` 前调用 `_repair_feedback_for_request`
- **Operation defense-in-depth**：`_repair_feedback_matches_request:1646-1660`，provider 前再做同样检查
- **Non-repairable terminal**：`_compaction_result_is_non_repairable:5827-5840` → break stop
- **Test**：`test_defensive_feedback_mismatch_stops_schedule_with_single_terminal`（`test_dispatch_scheduler.py:8191`）绕过 dispatcher 验证 operation 拒绝 mismatch 且只产生一个 terminal

**结论**: 无回归。Dual-digest binding 在 constructor、dispatcher、operation 三层始终一致。

---

## 补充 adversarial 检查

### 是否所有 producer/provider 路径都由 snapshot exact proof 或 operation exact partition 覆盖？

**系统级覆盖**：

| 路径 | Pipeline 覆盖 | Operation 覆盖 |
|---|---|---|
| Root（`build_normal_compact_request_plan`） | `_validate_segment_against_source_snapshot`：per-block exact proof (line 998) + complete partition (line 1002) | `_validate_operation_root_request`：block_id identity (line 1574) + turn group (line 1578) + pack multiset (line 1582) |
| Recovery root（`build_tier_recovery_request_plans`） | 同 root path（`_request_plan_from_segment` 在 line 525/546/565 调用） | 同 root |
| Transient（`build_reactive_pass_queue_plan` → `_single_block_segment_selection`） | `_validate_segment_against_source_snapshot`：per-block exact proof (line 998) + root digest non-None (line 1004)，不要求 complete partition | `_operation_pass_requests`：per-block exact root subset (line 1537-1539) + no overlap/omission (line 1540-1552) |
| Single attempt（`run_compaction_attempt`） | 间接：request 由上层 pipeline 或 tier recovery 构造 | `_validate_operation_root_request`：same as root |
| Hand-forged（绕过全部 pipeline） | 不涉及 | `_validate_operation_root_request` + `_operation_pass_requests`：pre-provider fail closed |

**结论**: 全部 5 条 producer/provider 路径均由 snapshot exact proof（pipeline）或 operation exact partition（operation）覆盖，无盲区。

### 是否存在手工构造/stale request 在 provider 前通过的产品反例？

对以下攻击场景逐一验证：

| 攻击 | 拦截层 | 拦截位置 | 测试覆盖 |
|---|---|---|---|
| 已知 block_id 替换为未知 block_id | Pipeline: selected_ids ⊆ known_ids (line 986-987) 或 Operation: `_validate_operation_root_request` line 1574-1575 identity check | Pipeline 拦截：`"outside source snapshot"` | `test_unknown_selected_block_id_fails_against_source_snapshot` |
| Unknown block_id + 复用真实 refs/digest | Pipeline: same as above | Pipeline 拦截 | 同测试（line 440） |
| Source ref tamper（per-block） | Pipeline: exact proof `!=` (line 998) + Operation: `_operation_pass_requests` line 1538 `!=` | Pipeline 拦截 | `test_root_selected_provenance_mismatch_fails_before_provider_call` with `source_ref` |
| Digest tamper（per-block） | Pipeline: exact proof `!=` (line 998) + Operation: `_operation_pass_requests` line 1538 `!=` | Pipeline 拦截 | 同测试 with `packed_digest` |
| Current ref overlap（绕过 pipeline 注入） | Operation: `_validate_operation_selected_pack` line 1622-1623 | Operation 拦截 | `test_current_input_ref_overlap_fails_before_provider_call` |
| Feedback cross-tier mismatch（绕过 dispatcher 清理） | Operation: `_repair_feedback_matches_request` line 1646-1660 | Operation 拦截 | `test_defensive_feedback_mismatch_stops_schedule_with_single_terminal` |
| Transient root_subset tamper（block excluded from root） | Operation: `_operation_pass_requests` line 1537 `None` check | Operation 拦截 | `test_reactive_pass_provenance_tamper_fails_before_provider` with `root_subset` |
| Transient pass_pack tamper | Operation: `_validate_operation_selected_pack` line 1619 | Operation 拦截 | 同测试 with `pass_pack` |
| Whole group swap（等数量不同 block） | Pipeline: exact proof `!=` (line 998) — per-block_id different content | Pipeline 拦截 | `test_whole_group_swap_proof_fails_before_provider` |
| Stale repair feedback（request digest 不匹配） | Dispatcher: `_repair_feedback_for_request` line 5819-5822 → return `None` | Dispatcher return `None`，operation 收到 `None` 作为 `initial_repair_feedback` | `test_mismatched_initial_feedback_fails_before_provider_call` |

**结论**: 所有 10 个攻击场景在 provider 之前被拦截，均有测试覆盖。不存在可手工构造/stale request 在 provider 前通过的产品反例。

---

## 测试验证

```
source .venv/bin/activate
python -m pytest tests/host/test_compact_material.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_public_compact_smoke.py \
  tests/host/test_runner_call_hot_payload_contract.py \
  -x -q
```

结果: **337 passed, 1 skipped in 3.49s**（skip 为 opt-in real compactor smoke）

Pyright: **0 errors, 0 warnings, 0 informations**

## Findings

未发现实质性问题。

DS-1 和 DS-2 均为 rejected-with-reason，当前代码路径不存在可复现的 correctness 反例。F1–F4 全部保持关闭。原 MiMo PASS 项 12 项均未回归。

## Open Questions

无。

## Residual Risk

1. **五条正式 CLI scenarios 未运行**: 按任务明确禁令未运行。真实 provider 对 F08/F09/F10 的端到端行为留待后续 evidence/readiness gate。

2. **全树 Ruff lint/format**: F10 pathspec 已 clean；全树既有 debt 不在 scope 内。

## Final Conclusion

**PASS**

本次 F10 implementation re-review（第二独立路线）对 DS initial review 的两个 low defense-in-depth observation（DS-1 operation refs/digest multiset、DS-2 transient pipeline layering）做了独立 adversarial 复核。Codex 的 rejected-with-reason 裁决在两条路径上均成立：pipeline owner 通过 per-block_id exact proof 验证保证正常构造路径安全；operation owner 对所有手工构造绕过路径在 provider 前 fail closed。全部 10 个攻击场景有测试覆盖且全部被拦截。F1–F4 未回归，原 MiMo 12 项 PASS 均保持。337 tests passed，pyright 0 errors。
