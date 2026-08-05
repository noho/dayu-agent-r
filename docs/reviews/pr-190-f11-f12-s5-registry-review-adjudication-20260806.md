# PR 190 F11/F12 S5 Registry/Docs Review Adjudication

## Gate

- Slice: S5 registry/docs lifecycle replacement
- MiMo review: `docs/reviews/pr-190-f11-f12-s5-registry-mimo-review-20260806.md`
- DeepSeek review: `docs/reviews/pr-190-f11-f12-s5-registry-ds-review-20260806.md`
- Controller decision date: 2026-08-06

## Finding adjudication

### S5-MiMo residual: `611 records` 与当前 612 条 interactive command records 看似不一致

**裁决：接受为低严重度文档歧义，与 DS finding 1 合并修复。**

直接 inventory 证明两组数字统计口径不同：

- 当前 `command=interactive` 是 612 records / 768 total refs；
- 变更前历史集合中，至少引用一个 `interactive.*` predicate 的是 611 records / 768 total refs，其中
  766 个 interactive refs 与 2 个 prompt cross-entry refs；
- 当前完整 registry 是 1059 records / 1614 refs；当前 accepted owners 共定义 66 个 stable predicates，其中
  64 个被 scenario 引用。

实现 artifact 把历史子集、当前全集和 owner 定义数压在同一行，虽不改变 registry contract，却不够可复核。修复只澄清统计口径，
不得改动 registry 数据或 accepted contract。

### S5-DS-01: `29 stable predicate ids` 与 owner 定义的 30 个 interactive predicates 不一致

**裁决：接受为低严重度文档歧义。**

`29` 是上述 611 条历史 scenario 子集实际引用的 stable predicate id 数（28 个 interactive + 1 个 prompt），不是
`core-execution@2` 定义的 interactive predicate 总数。实现 artifact 必须明确“referenced”与“owner-defined”的区别，并同时记录
完整 registry 的 66/64 统计，避免读者误把引用数当 schema inventory。

### S5-DS-02: active scenarios 的冻结 `accepted_oracle_refs` 指向 superseded oracle

**裁决：拒绝为 finding，保留为已缓解的维护注意事项。**

这是本次用户确认的 lifecycle contract，而不是实现偏差。`docs/cli_ci.md` 已明确：

1. `accepted_oracle_refs` 是 scenario 获裁决时的历史版本证据，不参与 current owner resolution；
2. current owner 只能由 stable `oracle_predicate_refs` 解析；
3. zero/multiple current owner 必须 fail closed。

机器检查证明 1614 个 refs 全部唯一解析，0 dangling、0 duplicate owner。继续批量改写 frozen refs 或新增兼容读法反而会破坏历史
verdict 的可解释性。后续若实现新的 registry consumer，其 owner tests 必须锁定上述解析规则；当前 S5 不扩张 README/example。

### DS open question 1: PX01/PX02 是否需要 lifecycle update

**裁决：不需要。**

它们的 frozen refs 正确记录原裁决版本，stable interactive predicate 已解析到 `core-execution@2`。修改其 lifecycle 会把历史事实误写成
本次新裁决。

### DS open question 2: predicate 10/17 当前零 scenario 引用

**裁决：不属于本 work unit 的 finding。**

它们是既有 accepted oracle predicates；本 work unit 只替换 F11/F12 对应 29/30 contract，且明确禁止借机扩张 scenario set。
是否新增正式 scenario 仍由后续 Oracle controller calibration 拥有。

## Required fix

只修改 `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md` 的 validation 统计说明：

- 精确区分 historical referenced subset、current command inventory、current full registry；
- 精确区分 owner-defined predicates 与 scenario-referenced predicate ids；
- 保留所有 registry、handbook、readiness 内容与 digest 不变；
- 写独立 fix artifact，并重跑两份 JSON、graph、stable-owner resolution、registry digest 与 `git diff --check`。

完成后必须由 MiMo 与 DeepSeek 各自 re-review，不能以本裁决替代两路复核。

