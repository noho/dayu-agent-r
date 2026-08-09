# F14 Plan Re-Review — AgentDS 窄 re-review

## Review metadata

- **Reviewed artifacts**:
  - Revised plan: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md` (revision 1)
  - Controller adjudication: `docs/gateflow/pr-190-f14-plan-review-adjudication-20260806-224800.md`
- **Original review**: `docs/reviews/pr-190-f14-plan-review-ds-20260806.md`
- **Reviewer**: AgentDS
- **Timestamp**: 2026-08-06T22:53:28+08:00
- **Gate**: plan re-review gate for F14 (窄 scope: 仅验证原 findings 修复 + 挑战 metadata-first user-anchor proof + suffix `_atomic_material_units`)

## Scope boundary

本 re-review 严格限于：
1. 验证原始 DS F1–F4 是否被正确解决
2. 挑战 metadata-first user-anchor proof 是否有 correctness gap
3. 挑战 suffix `_atomic_material_units` 是否有 correctness gap

不扩 scope：不重新 review 整个 plan、不检查 MiMo/Controller findings、不验证 test matrix 新增条目（A6/A7）的充分性（除非与上述三项直接相关）。

## Original findings resolution

### F1 (中): 全量扫描与风险缓解矛盾 → **已解决**

**原问题**: Implementation §1 描述读取全部 accepted compacts + 全部 raw material；Risk 表格描述 anchor 优化。两处矛盾。

**修订后**:
- Plan §2.1 明确分离为 metadata-first conservative frontier：raw 侧读全量 EventLog metadata（`EventLogRow` only，不 resolve payload），用 user-anchor proof 确定保守扫描起点；已消费 prefix 不解析 tool payload。
- Risk 表格（第 290 行）："raw侧采用metadata-first user-anchor proof，只解析保守frontier后的payload。增加>=10轮rolling owner test并记录rows/blocks范围"
- Controller adjudication：明确拒绝按 recent-window cap 或 terminal 附近估算（理由：recent policy 不是 coverage truth，任何 cap 都会重新引入 F14 同类 gap）。

**裁决**: 接受。全量 metadata 扫描（不 resolve payload）的成本远低于全量 payload 解析；accepted terminals 必须 strict parse（这是唯一 coverage truth，且数量远小于 raw events）。无矛盾残留。

### F2 (中): 函数级重构方案缺失 → **已解决**

**原问题**: Plan 未说明 `_post_compact_delta_start_sequence` / `_post_compact_delta_rows` / `_pre_dispatch_delta_material_blocks` 签名和职责如何变更。

**修订后**:
- Plan §2.1 step 2: `_post_compact_delta_rows` 改为 "读取 current input 之前全部 relevant canonical row metadata"（明确 scope 扩展）
- Plan §2.1 step 3: 新增 `_conservative_unconsumed_row_start_sequence(rows, consumed_source_refs, current_input_sequence) -> int`（显式新 helper）
- Plan §2.2 step 5: `_pre_dispatch_delta_material_blocks` "删除 `represented_evidence_refs` 参数与内部 early skip"（明确签名变更）
- Plan §2.2 step 6: 新增 `_unconsumed_atomic_material_blocks(material_blocks, consumed_source_refs) -> tuple[RunInputMaterialBlock, ...]`（显式新 helper）
- Plan §2.2 step 7: `_post_compact_delta_start_sequence` "改为纯派生 helper...不再接收 latest compact terminal，也不再执行 SQL"（明确语义和签名变更）
- 新增函数流图（第 132–142 行）

**裁决**: 接受。四个 helper 的签名、新增/删除参数、SQL 职责均明确。Implementation agent 可直接按签名编码。

### F3 (低): 双重过滤交互 → **已解决**

**原问题**: `_pre_dispatch_delta_material_blocks` 的 evidence early skip（`represented_evidence_refs`）与 plan §2.5 post-filter 职责重叠但数据源不同。

**修订后**:
- Plan §2.2 step 5: 直接删除 `represented_evidence_refs` 参数与 `_accepted_tool_evidence_delta_blocks` 的同名过滤参数。理由："early skip会隐藏partial-group corruption"。
- Controller F06: "suffix投影后由唯一cumulative atomic proof分类，避免隐藏partial corruption"

**裁决**: 接受。这是比原方案更干净的解法——消除双重过滤，让 `_unconsumed_atomic_material_blocks` 成为 consumed/unconsumed 分类的唯一 owner。

### F4 (低): 无 continuity answer 的 group atomicity → **已解决**

**原问题**: Plan 未说明 `RUN_SUCCEEDED` 存在但无 continuity text 时 atomic group proof 如何处理。

**修订后**:
- Plan §2.2 step 6: "`RUN_SUCCEEDED`虽存在但没有continuity text时本来就不产生answer block；atomic proof只计算typed projector实际产生的eligible blocks，不把无block的raw row虚构为source ref。"

**裁决**: 接受。这一定义与现有 projector 行为一致（`_assistant_answer_delta_block` 返回 None 时不产生 block），不会误判。

---

## Challenge 1: metadata-first user-anchor proof

### 算法摘要

1. 读取 current input 前全部 raw EventLog metadata（`USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`）
2. 按 `run_id` 首次出现位置归并 group
3. 对每个 group：必须有且仅有一个 `USER_INPUT_ACCEPTED` anchor；`anchor.event_id in consumed_source_refs` → 整组可跳过（consumed prefix）
4. 第一个不可跳过 group 的最早 row 成为保守扫描起点
5. consumed prefix 之后不能再出现 consumed group（fail closed）

### 验证：`anchor.event_id in consumed_source_refs` 是否充分证明整组已消费？

**关键不变量链**（逐项代码验证）:

| # | 不变量 | 证据 |
|---|--------|------|
| 1 | Selector 以 `turn_group_id`（= `run_id`）归并 `_AtomicMaterialUnit`，整组 selected 或整组 excluded | `compact_material.py:1873-1912` (`_atomic_material_units`); `compact_material.py:2101-2118` (`_collective_exclusion_reason` 返回 unit 级统一 reason) |
| 2 | `_REASON_ALREADY_REPRESENTED` 在 `_COLLECTIVE_EXCLUSION_PRECEDENCE` 中（优先级第三） | `compact_material.py:98-104` |
| 3 | 若 unit 内任一 block 为 `already_represented`，整组 excluded | `_collective_exclusion_reason` 取最高优先级 reason（第 2118 行） |
| 4 | represented + omitted coverage 精确分区 source boundary | `compact_payload.py:482-492` (`_validate_committed_coverage`) |
| 5 | user block 的 `canonical_source_refs` = `(row.event_id,)` | `compact_material.py:2696` |
| 6 | `compacted_source_refs` 从 covered entries 的 `source_refs` 派生，`source_refs` = `block.canonical_source_refs` | `compact_payload.py:169-181`; `compaction.py:3166` |
| 7 | `current_input_ref` 不在 `compacted_source_refs` 中 | `compact_payload.py:497` |

**推导**: `anchor.event_id in consumed_source_refs` → user block 进入过某次 accepted compact 的 source boundary → 整组被 selected（selector 原子性） → 整组被 represented 或 omitted（coverage 精确分区 selected boundary） → 整组已消费。

**结论**: 证明充分。不变量链完整，无 gap。

### 验证：user-anchor proof 的边界条件

| 场景 | 行为 | 安全性 |
|------|------|--------|
| `run_id=None` 的 row | "不能跳过" → 成为保守起点 | ✅ safe（保守） |
| 同一 `run_id` 有多个 `USER_INPUT_ACCEPTED` | "不能跳过" | ✅ safe（保守） |
| 同一 `run_id` 无 `USER_INPUT_ACCEPTED` | "不能跳过" | ✅ safe（保守） |
| 多个 reactive compacts 复用同一 `current_input_ref` | `current_input_ref` 被排除在 `compacted_source_refs` 外（plan §1 第 97 行 + `compact_payload.py:497`），该 user input 永不被标记为 consumed | ✅ 正确 |
| `consumed_source_refs` 含 evidence_id（与 user event_id 不同命名空间） | O(1) set membership 不会跨命名空间误匹配 | ✅ 安全（ID 前缀/格式不同） |
| `consumed_source_refs` 含 previous view block 的 compact event_id | compact event_id 是 CONTEXT_COMPACTED 的 event_id，与 user event_id 不同 | ✅ 安全 |
| consumed prefix 后再出现 consumed group | fail closed（`HostDurableError`） | ✅ 防御（不应发生，发生即 durable contract 损坏） |

**结论**: 所有边界条件均安全或保守。无 correctness gap。

### 一个值得注意的间接依赖

User-anchor proof 依赖 selector 的原子 group 行为（整组 selected 或整组 excluded）。如果未来 selector 变为允许 partial group selection（例如 "跳过 oversized evidence 但保留 user 和 answer"），此 proof 会失效。但这是 future change 的 concern，不属于当前 plan 的 gap。Plan §2.2 step 6 的 atomic proof（all-or-none per block/unit）会在 projected suffix 上独立验证，形成 defense-in-depth。

---

## Challenge 2: suffix `_atomic_material_units`

### 算法摘要

1. 从保守扫描起点投影 suffix rows → `RunInputMaterialBlock` 列表
2. 复用 `_sorted_material_blocks` + `_atomic_material_units` 归并 suffix blocks
3. 逐 unit 检查：all blocks consumed → 属 prefix（删除）；no blocks consumed → 属 suffix（保留）；mixed → fail closed
4. Units 必须是 consumed prefix 后接 unconsumed suffix；unconsumed 后再出现 consumed → fail closed

### 验证：metadata-first 分组 (`run_id`) 与 atomic proof 分组 (`turn_group_id`) 是否一致？

| 比对维度 | metadata-first (step 2.1) | atomic proof (step 2.2) | 一致性 |
|----------|--------------------------|------------------------|--------|
| 分组键 | `raw_row.run_id` | `projected_block.turn_group_id` | ✅ `turn_group_id` = `run_id`（`compact_material.py:2698,2733,2788`） |
| 分组粒度 | 按 `run_id` 首次出现顺序 | `_atomic_material_units` 按 `turn_group_id` 首次出现顺序 | ✅ 同序（均按 EventLog canonical order） |
| 成员 | 所有 `run_id` 相同的 raw rows | 所有 `turn_group_id` 相同的 projected blocks | ⚠️ 见下方分析 |

### 关键差异：raw rows vs projected blocks

Projector 可能不为某些 raw row 产生 block：
- `TOOL_RESULT_ACCEPTED` 且 `envelope_available=False` → 返回 `()`（`compact_material.py:2768-2769`）
- `RUN_SUCCEEDED` 且无 continuity text → 返回 `None`（`compact_material.py:2719-2725`）

因此 suffix 中一个 group 的 projected blocks 数量可能少于 raw rows 数量。

**对 atomic proof 的影响**:

Plan §2.2 step 6 明确规定："atomic proof只计算typed projector实际产生的eligible blocks，不把无block的raw row虚构为source ref。" 这意味着 atomic proof 在 projected blocks 的子集上做 all-or-none 判断。

具体场景分析：

| 场景 | metadata-first 判断 | projected blocks | atomic proof 判断 | 一致性 |
|------|---------------------|-----------------|-------------------|--------|
| Group G: user(row1) + tool(row2, no envelope) + answer(row3, no continuity) → user anchor consumed | skip（anchor in consumed_set） | N/A（已在保守起点之前） | N/A | ✅ |
| Group G: user(row1) + tool(row2, no envelope) → user anchor NOT consumed | 不可跳过 → 保守起点=row1 | user(block1) only | 1 block, 0 consumed → unconsumed → suffix | ✅ |
| Group G: user(row1, consumed) + tool(row2, consumed) + answer(row3, consumed, no continuity) → anchor consumed | skip | N/A | N/A | ✅ — 即使 answer 不产生 block，anchor proof 已证明整组消费 |

**结论**: 差异场景下行为一致——metadata-first 正确跳过 consumed groups（即使某些 member 不产生 projected block），atomic proof 正确保留 unconsumed groups（只检查实际产生的 block）。无 correctness gap。

### 验证：atomic proof 的 strict prefix 不变量是否合理？

Plan 要求 consumed prefix → unconsumed suffix（不可出现 "consumed, unconsumed, consumed"）。

**辩护**: Selector 从 eligible groups 中选择一个 contiguous prefix（按 canonical order）。一旦一个 group 被选中并进入 accepted boundary，所有更早的 eligible groups 也必须被选中（selector 从前向后扫描直到 budget 耗尽）。因此：
- Compact C1 的 source boundary 覆盖 groups [A, B, C]（prefix of eligible）
- Compact C2 的 source boundary 覆盖 groups [D, E]（next prefix after C1's coverage）
- 不存在 "C1 覆盖 A 和 C 但跳过 B"

strict prefix 检查是此不变量的运行时验证。合理。

**一个理论风险**: 如果在 C1 和 C2 之间，group B 从 protected 变为 eligible（aged out of recent floor），那么 C2 会覆盖 [B, D, E]，此时所有 groups [A, B, C, D, E] 连续覆盖。但如果 C1 跳过了 B（因为 protected），且 C2 也跳过了 B（因为某种原因），然后 C3 覆盖了 B——这不违反 strict prefix，因为 [A, C, D, E, B] 中的 B 在末尾（按 sequence order）。但 B 的 sequence 在 C 之前，EventLog order 是 [A, B, C, D, E]。如果 coverage 是 [A, C, D]，然后后续 compact 覆盖了 B，从 sequence order 看是 "A consumed, B unconsumed, C consumed" → strict prefix 会 fail closed。

**但是**: 这种情况要求 selector 跳过 B 而选中 C。在 selector 逻辑中，groups 按 canonical order 排列，protected 的 B 被 collective exclusion 跳过（整组 excluded），然后 C 被选中。在第二轮 compact 中，B aged out → eligible → 被选中。从 sequence order 看确实是 A consumed → B unconsumed（在第一轮）→ C consumed（在第一轮）。但 atomic proof 的 suffix 检查发生在单次 material build 中，不是在跨 compact 的 coverage 历史中。

**关键洞察**: 在单次 material build 中，atomic proof 检查的是 "当前这次 material view 的 suffix blocks 中，是否出现 consumed 穿插 unconsumed"。由于 metadata-first proof 已经把 consumed prefix 切掉了，suffix 中的所有 blocks 都应该属于 unconsumed groups。如果 suffix 中出现了 consumed block，说明 metadata-first proof 的切分有误（应该 fail closed）。

**进一步分析**: metadata-first proof 的切分基于 `run_id` 归组和 user-anchor check。如果 user anchor A 在 consumed_set 中（group A consumed），user anchor B 不在（group B unconsumed），那么 metadata-first 会切在 group B 的开头。suffix 包含 group B 及之后的所有 blocks。如果 group B 的某些 blocks 意外地在 consumed_set 中，atomic proof 的 all-or-none check 会捕获（mixed → fail closed）。如果 group B 的 blocks 都不在 consumed_set 中，但 group C（在 B 之后）的某些 blocks 在 consumed_set 中，atomic proof 的 strict prefix 检查会捕获（unconsumed B 之后出现 consumed C → fail closed）。

这里 atomic proof 的 strict prefix 检查实际上是在验证 metadata-first proof 的正确性——如果两者一致，suffix 中的第一个 unit 是 unconsumed，后续也都是 unconsumed。如果出现 consumed 穿插，意味着 metadata-first proof 的 `anchor.event_id in consumed_source_refs` 判断与 atomic proof 的 `block.canonical_source_refs subset of consumed_source_refs` 判断不一致——这本身就是 durable contract 损坏，fail closed 是正确的。

**结论**: strict prefix 检查作为 defense-in-depth 是正确的。无 gap。

---

## 总体裁决

### 原 findings 状态

| Finding | 状态 |
|---------|------|
| F1 全量扫描矛盾 | ✅ 已解决——metadata-first 分离 |
| F2 函数级重构缺失 | ✅ 已解决——四个 helper 签名明确 |
| F3 双重过滤交互 | ✅ 已解决——删除 early skip |
| F4 无 continuity answer | ✅ 已解决——显式排除无 block raw row |

### 新增挑战

| Challenge | 结论 |
|-----------|------|
| metadata-first user-anchor proof | ✅ 无 correctness gap——不变量链完整，边界条件安全，defense-in-depth（atomic proof 独立验证） |
| suffix `_atomic_material_units` | ✅ 无 correctness gap——分组键一致，projected block 子集正确处理，strict prefix 作为 defense-in-depth |

### 最终 re-review 结论

**`accepted`**

所有原始 findings 已被修订后的 plan 正确解决。metadata-first user-anchor proof 与 suffix `_atomic_material_units` 的组合经过逐项代码验证无 correctness gap。不变量链完整，边界条件保守安全，阶段间 defense-in-depth 设计合理。

无新的 blocking finding，无 residual open question。
