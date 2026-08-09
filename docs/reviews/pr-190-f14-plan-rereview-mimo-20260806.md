# F14 Plan Re-review — AgentMiMo narrow re-review

## Review target

- revised plan: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`（revision 1）
- adjudication: `docs/gateflow/pr-190-f14-plan-review-adjudication-20260806-224800.md`
- scope: 窄 re-review，验证原 7 findings 是否被正确解决，挑战 metadata-first user-anchor proof + suffix `_atomic_material_units` 的 correctness

## Original findings resolution

| # | finding | resolution |
|---|---------|-----------|
| 01 | Run group atomic proof 未规格化 | resolved：§2.1 冻结 metadata-first user-anchor proof，§2.2 冻结 suffix `_atomic_material_units` typed atomic proof。衔接路径明确。 |
| 02 | 全历史扫描 prefix 优化未说明 | resolved：§2.1 明确 metadata-first 优化（只读 metadata，不 resolve payload）；风险缓解表同步更新。 |
| 03 | compacted_source_refs 混合 id 类型 | resolved：§2.1.3 只检查 user anchor `event_id`；§2.2.5 明确 tool projector 产生 `evidence_id`。 |
| 04 | attempt-rejected event class | resolved：§1 明确 rejected 是 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，不进入 chain 查询。 |
| 05 | rolling chain ref 累积语义 | resolved：§1 明确各 terminal 直接贡献当轮 coverage，previous event ref 只作 provenance。 |
| 06 | regression proof 具体化 | resolved：A.1 明确 fixture 断言 protected seq 早于 terminal、frontier 等于最早 protected block。 |
| 07 | CLI 人工标准 | resolved：Validation plan 第 5 点拆分 mechanical boundary/ref 检查与自然语言记录。 |

## Correctness challenge: metadata-first user-anchor proof + suffix `_atomic_material_units`

### prefix invariant 验证

**claim**: consumed groups 在 canonical order 中形成 contiguous prefix。

**直接代码证据**:

1. `protected_recent_turn_group_ids_for_material_blocks`（`compact_material.py:2023-2059`）按各 group 最新 block 的 `(event_sequence, event_sub_index, index)` 降序排列，取前 N 个。因此 protected groups 必为 canonical suffix —— 任何更近的 group 也必然在 floor 中。
2. `_sorted_material_blocks` 按 `(event_sequence, event_sub_index, kind_order, block_id)` 排序，即 canonical order。
3. `select_compact_segment`（`compact_material.py:878-911`）按 sorted order 遍历 `_atomic_material_units`，eligible units 按序进入 budget 检查，第一个超 budget 的 unit 及其后所有 units 被排除。因此 selected units 是 eligible units 的 contiguous prefix。
4. eligible units = 全部 units - protected units。protected units 是 canonical suffix。eligible units 是 canonical prefix。
5. 因此 selected units 是 canonical prefix 的 prefix = canonical prefix。

**结论**: consumed groups 在 canonical order 中必为 contiguous prefix。§2.1.3 的 "unconsumed group 之后出现 consumed group → fail closed" 规则正确 —— 此场景只在 corruption 时发生，protected groups 不可能打断连续性（它们必在 suffix）。

### user anchor 证明整组 consumed 的充分性

selector 对 `_AtomicMaterialUnit` 做整组 selected/excluded（`compact_material.py:878-911`）。同一 `turn_group_id` 的 blocks 归入同一 unit（`compact_material.py:1873-1912`）。若 user anchor 的 `event_id ∈ consumed_source_refs`，说明该 unit 被整组 selected，同 unit 的 tool evidence blocks 也必然被 selected（其 `evidence_id` 也在 consumed refs 中）。✓

### suffix `_atomic_material_units` all-or-none 验证完备性

三条规则覆盖所有 partial consumption 场景：block 级 all-or-none、unit 级 all-or-none、suffix 级 consumed-prefix-only。在 prefix invariant 成立的前提下，第三条规则只在 corruption 时触发。✓

## Conclusion

**accepted**。原 7 findings 均被正确解决。metadata-first user-anchor proof + suffix `_atomic_material_units` 的 prefix invariant 成立：protected groups 必为 canonical suffix（`protected_recent_turn_group_ids_for_material_blocks` 按最新 block 降序取前 N），eligible/consumed groups 必为 canonical prefix。无 correctness gap。
