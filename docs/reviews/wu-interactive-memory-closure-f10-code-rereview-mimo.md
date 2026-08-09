# Code Re-review：Interactive Conversation Memory closure F10 — MiMo re-review of Codex fix

## Scope

- **Mode**: current changes（未提交 workspace diff）
- **Branch**: `codex/interactive-oracle`
- **Base**: `d04f7531f3a7bfef2de004afbb94b2d607704b36`（accepted F09 commit）
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f10-code-rereview-mimo.md`
- **Included scope**: Codex fix artifact（`wu-interactive-memory-closure-f10-code-review-fix-codex.md`）对 DS-1、DS-2 的 `rejected-with-reason` 裁决，以及 MiMo 原 code review 的全部 PASS 项
- **Excluded scope**: 五条正式 CLI scenarios（按明确禁令未运行）
- **Parallel review coverage**: 无。本 re-review 为 MiMo 单路独立复核。

## Re-review 任务

1. 复核 Codex 对 DS-1（multiset 比较）和 DS-2（transient layering）的 `rejected-with-reason` 是否由直接数据流与 accepted owner boundary 支持
2. 检查是否漏掉能改变 durable semantic set、绕过 pipeline/operation、或在 provider 前通过的反例
3. 确认原 MiMo code review 的 PASS 项未回归

## DS-1 复核：operation 使用 refs/digest sorted multiset

### Codex 裁决

`rejected-with-reason`；机械观察成立，但 correctness premise 不成立。

### 独立数据流追踪

**攻击场景**：两个已 selected 的 block A/B 在 proof 中整体交换 `(canonical_source_refs, packed_content_digest)`。

**第一层防御：pipeline `_validate_segment_against_source_snapshot`**（`compact_pipeline.py:994-998`）

```python
expected_provenance = selected_block_provenance_for_material_blocks(
    source_snapshot.material_blocks,
    selected_block_ids=selected_segment.selected_block_ids,
)
if selected_segment.selected_block_provenance != expected_provenance:
    raise ValueError("segment selected block provenance does not match source snapshot")
```

- `selected_block_provenance_for_material_blocks`（`compact_material.py:1908-1939`）从 raw source snapshot 按 `selected_block_ids` 顺序机械重建 provenance，每条 provenance 的 `canonical_source_refs` 和 `packed_content_digest` 直接从对应 source block 读取
- 比较使用 tuple `!=`，即逐顺序、逐字段 frozen dataclass `__eq__`
- 若 A↔B 交换了 refs+digest：`selected_segment.selected_block_provenance` 的第 0 条是 `(refs_B, digest_B)` 而 `expected_provenance` 的第 0 条是 `(refs_A, digest_A)` → `!=` 为 True → raise

**第二层防御：operation `_validate_operation_root_request`**（`compaction_operation.py:1574`）

```python
if tuple(provenance.block_id for provenance in selection.selected_block_provenance) != selection.selected_block_ids:
    raise ValueError("operation root selected block provenance identity mismatch")
```

- 验证 provenance 的 block_id 顺序与 selected_block_ids 一致
- 若 A↔B 交换了完整 provenance 条目（block_id 也交换）：此检查不触发，但 pipeline 层已先拦截
- 若只交换 refs+digest（block_id 不变）：此检查不触发，但 pipeline 层已先拦截

**第三层：operation `_validate_operation_selected_pack`**（`compaction_operation.py:1596-1620`）

```python
proof_values = _sorted_selected_provenance_values(request.segment_selection.selected_block_provenance)
...
pack_values = tuple(sorted((block.canonical_source_refs, block.content_digest) for block in packed_blocks))
if proof_values != pack_values:
    raise ValueError("selected block provenance does not match compact material pack")
```

- 使用 sorted multiset 比较，A↔B 交换后 multiset 不变 → 此层不拦截

**关键问题：是否存在绕过 pipeline 直接到达 operation 的代码路径？**

- `run_compaction_operation`（`compaction_operation.py:660`）是 operation 唯一入口
- 所有调用方（`dispatch.py` 中的调度器）通过 pipeline 的 `build_normal_compact_request_plan` 或 `build_recovery_compact_request_plan` 构造 request
- `_build_compaction_pass_queue`（`compact_pipeline.py:580`）是 pass queue 唯一构造器，只从 pipeline 内部调用
- **结论：当前不存在绕过 pipeline 的 request 构造路径**

**反例分析：若假设 pipeline 被绕过**

即使 pipeline 被绕过，forger 需要同时满足：
1. provenance 的 block_id 顺序匹配 selected_block_ids（operation line 1574）
2. provenance 的 (refs, digest) multiset 匹配 pack 的 (refs, digest) multiset（operation line 1619）
3. pack 的 source_boundary labels 匹配 provenance 顺序（operation line 1592）
4. turn-group membership 二分正确（operation line 1578-1581）
5. source_boundary partition 完整（operation line 1547-1552）

若 forger 只交换 A↔B 的 (refs, digest)：
- 条件 1 通过（block_id 不变）
- 条件 2 通过（multiset 不变）
- 条件 3：pack 由 `compact_input` 构造，`compact_input` 由 forger 提供。若 forger 同时交换 pack 中对应 block 的内容 → 条件 3 也通过
- 但此时 pack 的实际内容已被交换，compactor 收到的是 A 的文本标为 B、B 的文本标为 A

**此交换是否改变 durable semantic set？**

- compactor 只看到 pack 内容，不看到 block_id
- compactor 的输出是基于 pack 内容的摘要，不依赖 block_id 与内容的映射
- durable boundary 使用 `compact_input.source_boundary`（来自 pack 的 labels/refs），不使用 provenance 的 block_id 映射
- 因此即使 A↔B 交换，durable semantic set（compactor 摘要 + boundary）不变

### DS-1 复核结论

Codex 裁决 `rejected-with-reason` **成立**。直接数据流证据：

1. pipeline 的 per-order provenance 重建比较是正式 producer path 中的第一层防御，catches A↔B swap
2. operation 的 sorted multiset 是 defense-in-depth，设计意图不是重复 pipeline 的 per-order 比较
3. 当前无绕过 pipeline 的 request 构造路径
4. 即使假设绕过，A↔B swap 不改变 durable semantic set（compactor 不依赖 block_id 映射）

未发现能改变 durable semantic set、绕过 pipeline/operation、或在 provider 前通过的反例。

## DS-2 复核：transient snapshot validator 不接收 root segment

### Codex 裁决

`rejected-with-reason`；这是已接受的分层，不是下游补偿或验证缺口。

### 独立数据流追踪

**DS 观察**：`_validate_segment_against_source_snapshot`（`compact_pipeline.py:969`）对 transient scope 只检查 `root_selection_digest is not None`，不验证 transient selected block_ids 是 root selected block_ids 的子集。

**transient 唯一构造器：`_single_block_segment_selection`**（`compact_pipeline.py:1042-1085`）

```python
root_provenance = tuple(
    provenance
    for provenance in root_request.segment_selection.selected_block_provenance
    if provenance.block_id == block_id
)
if len(root_provenance) != 1:
    raise ValueError("reactive pass block provenance is not present exactly once in root")
```

- block_id 必须在 root `selected_block_provenance` 中精确出现一次
- entry 直接取自 root proof（`root_provenance[0]`），不重算
- 绑定 root `selection_digest`

**operation 层验证：`_operation_pass_requests`**（`compaction_operation.py:1529-1552`）

```python
if pass_request.segment_selection.scope is not CompactSegmentSelectionScope.TRANSIENT:
    raise ValueError("pass_queue selection must be transient")
if pass_request.segment_selection.root_selection_digest != request.segment_selection.selection_digest:
    raise ValueError("pass_queue selection root digest mismatch")
...
for provenance in pass_request.segment_selection.selected_block_provenance:
    root_provenance = root_provenance_by_id.get(provenance.block_id)
    if root_provenance is None or provenance != root_provenance:
        raise ValueError("pass_queue selected block provenance is not an exact root subset")
    if provenance.block_id in observed_pass_block_ids:
        raise ValueError("pass_queue selected block provenance overlaps")
    observed_pass_block_ids.add(provenance.block_id)
...
if observed_pass_block_ids != set(root_provenance_by_id):
    raise ValueError("pass_queue selected block provenance must exactly partition root")
```

逐层验证：
1. scope 必须是 TRANSIENT
2. root_selection_digest 精确匹配
3. turn_group_memberships 精确匹配
4. 每条 provenance 的 block_id 必须在 root provenance 中存在，且逐字段 exact equality
5. 无重叠
6. 全体 block_id 无遗漏（exact partition）

**反例分析：能否构造绕过两层验证的 forged transient？**

假设 forger 构造一个 transient，包含 root 已排除的 block_3：
- snapshot validator：block_3 在 snapshot 中 → `issubset(known_ids)` 通过；provenance 与 snapshot 一致 → 通过；root_selection_digest 非空 → 通过
- operation validator：`root_provenance_by_id.get("block_3")` 返回 `None` → raise

假设 forger 同时伪造 provenance 使 block_3 的 provenance 存在于 root：
- 但 root 的 provenance 是 pipeline 从 source snapshot 机械重建的，forger 无法让 root 包含 block_3 的 provenance 而不改变 root 的 selected_block_ids
- 若 forger 改变 root 的 selected_block_ids → root 的 `_validate_segment_against_source_snapshot` 会验证 `selected ∪ excluded = known`，且 `_validate_operation_root_request` 会验证 turn-group 二分

**分层职责判定**：

| 验证职责 | 持有者 | 理由 |
|---|---|---|
| selected/excluded ⊂ snapshot | pipeline snapshot validator | pipeline 持有 raw source snapshot |
| selected ∪ excluded = snapshot（root partition） | pipeline snapshot validator | 仅 root scope 有此语义 |
| turn-group completeness | pipeline snapshot validator + operation root validator | 双重验证 |
| transient ⊂ root（per-block exact subset） | operation `_operation_pass_requests` | operation 持有 root request |
| transient 无重叠无遗漏 | operation `_operation_pass_requests` | operation 持有全体 pass |
| root_selection_digest binding | pipeline snapshot validator + operation | 双重验证 |

给 snapshot validator 增加 `root_segment` 参数会：
- 复制 transient/root relationship 的 owner（当前由 `_single_block_segment_selection` + `_operation_pass_requests` 独占）
- 扩大函数签名（新增参数）
- 不关闭新的 correctness 反例（operation 已覆盖）

### DS-2 复核结论

Codex 裁决 `rejected-with-reason` **成立**。直接数据流证据：

1. `_single_block_segment_selection` 是唯一 transient 构造器，从 root proof 取 entry，不重算
2. `_operation_pass_requests` 对每条 transient provenance 做 per-block_id exact root subset + 无重叠 + 无遗漏
3. 当前无绕过 `_single_block_segment_selection` 的 transient 构造路径
4. 给 pipeline snapshot validator 增加 root_segment 参数会复制 owner，不增加有效防御

未发现能绕过两层验证的 forged transient 反例。

## 原 MiMo PASS 项回归检查

| PASS 项 | 当前状态 | 直接证据 |
|---|---|---|
| semantic owner / compat | ✅ 未回归 | `_packed_content_digest` 仍为唯一 helper，四个调用点不变（`compact_material.py:1674-1686`）；无 fallback/shim |
| schema / LLM surface | ✅ 未回归 | `SelectedBlockProvenance`/`TurnGroupMembership`/`CompactSegmentSelectionScope` 仍为 Host-internal；repair projector 不含治理 digest |
| atomic selection / budget | ✅ 未回归 | `_atomic_material_units`（`compact_material.py:1836`）、`_collective_exclusion_reason`（`compact_material.py:2064`）、strict prefix budget（`select_compact_segment` 内）逻辑不变 |
| provenance fail closed | ✅ 未回归 | pipeline per-order（line 998）、operation multiset（line 1619）、transient per-id exact subset（line 1536-1542）三层验证不变 |
| root/transient partition | ✅ 未回归 | root `selected ∪ excluded = known`（line 1001）、transient exact partition（line 1551-1552）不变 |
| same-text/same-ref | ✅ 未回归 | `_is_current_input_history_duplicate` 仍不存在；same-ref 双层 fail closed（pipeline line 1008-1025、operation line 1621-1623）不变 |
| excluded mapping | ✅ 未回归 | `__post_init__` key-sort copy + `MappingProxyType`（`compaction.py:1977-1985`）不变 |
| repair binding | ✅ 未回归 | dual-digest feedback（`compaction.py:1661-1670`）、dispatcher clear（`dispatch.py:5803-5822`）、operation guard（`compaction_operation.py:1646-1660`）不变 |
| F09 fixture migration | ✅ 未回归 | compactor manifest fixture 只修真实 consumer；无 production compat |
| Memory/RunInput/LLM 隔离 | ✅ 未回归 | LLM-facing 投影不含治理字段（`llm_compaction.py:680-703`）；测试断言不变 |

**回归检查结论**：全部 PASS 项未回归。337 passed, 1 skipped（opt-in real compactor smoke）。Pyright 0 errors。

## Open Questions

无。

## Residual Risk

1. **Operation sorted multiset defense-in-depth gap**（DS-1 residual）：若未来新增绕过 pipeline 的 request 构造路径，operation 的 sorted multiset 比较无法防御 A↔B 完整交换。当前无此路径；且即使存在，不改变 durable semantic set。建议后续迭代中将 operation 层改为 per-block_id 比较。

2. **Transient snapshot validator 不验证 root subset**（DS-2 residual）：若未来新增绕过 `_single_block_segment_selection` 的 transient 构造路径，pipeline 层不拦截 phantom block。当前无此路径；operation 层已拦截。建议后续迭代中在 snapshot validator 增加 root subset 验证。

3. **五条正式 CLI scenarios 未运行**：按明确禁令。真实 provider 行为留待 evidence/readiness gate。

4. **全树 Ruff lint/format debt**：F10 pathspec 已 clean；全树既有 debt 不在 scope。

## 结论

**PASS**

Codex 对 DS-1 和 DS-2 的 `rejected-with-reason` 裁决均由直接数据流与 accepted owner boundary 支持：

- **DS-1**：pipeline 的 `_validate_segment_against_source_snapshot` 从 raw source snapshot 机械重建 expected provenance 并做 per-order tuple 比较，在正式 producer path 中 catches A↔B 完整交换。operation 的 sorted multiset 是 defense-in-depth，设计意图不是重复 pipeline 的 per-order 比较。当前无绕过 pipeline 的路径；即使假设绕过，A↔B swap 不改变 durable semantic set。无遗漏反例。

- **DS-2**：`_single_block_segment_selection` 是唯一 transient 构造器，从 root proof 取 entry。`_operation_pass_requests` 做 per-block_id exact root subset + 无重叠 + 无遗漏。给 snapshot validator 增加 root_segment 参数会复制 owner，不增加有效防御。无遗漏反例。

原 MiMo PASS 项全部未回归。测试 337 passed, 1 skipped。Pyright 0 errors。
