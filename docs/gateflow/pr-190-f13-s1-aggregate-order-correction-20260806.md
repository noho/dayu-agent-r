# PR 190 F13 S1 Aggregate Order Contract Correction

## Direct evidence

已接受设计同时要求：

1. replacement aggregate exact 等于逐 fact refs 按 fact/entry 顺序的 ordered unique union；
2. accepted aggregate 是 request boundary-order union 的“有序子集”。

这两个要求在合法 proposal 上可能冲突。设 immutable boundary 顺序为 `E1, E2`，模型按业务顺序先输出只选择 `E2` 的 fact、再输出只选择 `E1` 的 fact：逐 fact binding均合法，replacement aggregate按已冻结公式为 `(E2-ref, E1-ref)`，但它不是 request union `(E1-ref, E2-ref)` 的单调子序列。当前 `compact_payload._validate_aggregate_boundary_ordered_subset` 会让 Context Governance 已接受的 proposal 在 durable payload 构造阶段才失败，违反 accept owner 必须在持久化前给出完整接受结果的边界。

## First-principles owner ruling

- 逐 fact atom 是 evidence provenance 真源；每个 new fact 的 refs 继续按该 fact canonical support labels / boundary 顺序构造并严格重验。
- replacement aggregate 只是按 replacement fact业务顺序派生的 projection；必须 exact 等于逐 fact refs 的 ordered unique union。
- request union 只定义 immutable available evidence membership。对 accepted aggregate 的额外约束应是唯一、非越界、属于 request union；不能覆盖逐 fact owner 已确定的跨 fact业务顺序。
- 因此删除“跨 fact aggregate 必须按 request boundary全局单调”的 reader约束，不改变任何逐 fact binding、kind、non-empty、coverage或omit语义。

## Implementation and test boundary

- S1 strict payload parser 把 `_validate_aggregate_boundary_ordered_subset` 收敛并重命名为 request-boundary unique membership/subset validation；显式拒绝aggregate重复ref，aggregate exact-union仍由 replacement equality独立强制。
- owner tests覆盖：正常`E1→E2`；反序`E2→E1`；三条fact的任意业务顺序；跨fact共享evidence时aggregate稳定去重；retained+new refs交错；repair后从新proposal/replacement完整重算；无EvidenceFact时empty aggregate合法。任何越界ref、重复ref或与replacement union不等仍fail closed。
- 这是同一S1 persistence owner内部矛盾修正，不扩大业务目标、不新增schema字段、不增加兼容路径。

## Gate state

`accepted`。MiMo 8/8 finding通过、无blocking；DS确认其一条blocking design残留与两条medium建议均已处理，无残余finding。Controller裁决：逐fact atom与fact业务顺序优先，strict reader只验证aggregate exact-union、唯一性和request-boundary membership，不再施加跨fact全局顺序。

Review evidence：

- `docs/reviews/plan-review-20260806-f13-s1-aggregate-order-mimo.md`
- `docs/reviews/plan-review-20260806-f13-s1-aggregate-order-ds.md`

DS first review指出的blocking design残留及两条medium建议均已处理：同步修正reactive multi-pass段，要求显式唯一性，并扩充owner test矩阵。
