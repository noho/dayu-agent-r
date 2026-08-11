# WU-CLI-DOWNLOAD-02 Aggregate Deepreview 裁决

## Gate 范围

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Base：`3811f95c82fbf0daf15740a5d217eed4d8b49df5`
- Reviewed HEAD：`a24671793c0d69f2a3e0f2d39e1b611d945b6044`
- Reviewer：AgentMiMo、AgentDS
- Review artifacts：
  - `docs/reviews/wu-cli-download-02-aggregate-deepreview-mimo-20260810.md`
  - `docs/reviews/wu-cli-download-02-aggregate-deepreview-ds-20260810.md`

## 总控裁决

两路独立 aggregate deepreview 均为 **PASS**，没有提出 material finding、blocking contract question、scope drift 或过度设计问题。本 gate 无需 implementation fix 或 re-review；接受当前 DL-F12、DL-F13、DL-F14 产品实现进入 production CLI post-fix evidence gate。

总控逐项复核并接受以下结论：

1. DL-F12 的唯一语义 owner 是 typed download request/effective-filter invariant；两个冲突 argv 顺序均在 workspace 解析、Service/operation 构造、provider、网络与业务写入前失败，单独 overwrite/rebuild 不受影响。
2. DL-F14 的唯一 market policy owner 同时产生 effective、discovery、missing-eligible 三个集合；CN bare、HK bare、显式 forms、rebuild 和 summary/missing 投影没有下游重算或双真源。
3. DL-F13 的 raw discovery root cause 是旧 HKEX 季度子类查询未包含腾讯实际 Q2/Q4 results rows；修复改为一般化全 results group discovery，再由 category-first classifier 产生 typed identity/coverage，不含发行人、ticker、日期、URL 或完整标题特例。
4. `identity_period` 单独决定 document identity、selection、window、missing、form/report kind；`covered_periods` 只表达同一披露覆盖的业务期间，不复制 document，也不替代 FY/H1 baseline missing。
5. fresh-schema rebuild 对 coverage 严格 fail closed；SEC/generic 构造点显式提供空 coverage；skip、failure、cancel、empty-candidate 路径未发现 contract 断裂。
6. 修改严格位于 CLI/Service/Fins 允许边界；Host/Engine、storage schema、其它 CLI 命令、通用观察/CI 基础设施未被扩建。
7. README 更新与实际用户契约一致，未写入 WU 历史或未来能力承诺。

## Finding 裁决

两路 reviewer 均未提出 finding，因此没有需要接受、拒绝、降级或延期的条目。

## Residual risk 分类

| 风险 | 裁决 | 后续 owner |
|---|---|---|
| 真实 HKEX 全 results 数据规模、边缘 category 文本与腾讯实际材料链尚未经过 production CLI | 已知且未掩盖；属于下一 evidence gate | production CLI post-fix observation |
| 通用 substring 分类对未知歧义文本会保守丢弃 | 接受的 fail-closed residual；禁止在本 gate 添加 issuer 特例 | 真实观察；出现直接证据后由用户裁决 |
| 旧 workspace source meta 缺少 coverage 无兼容读取 | 符合用户冻结的 fresh-schema 边界，不是 finding | 非本 work unit |
| formal Oracle/scenario/readiness 尚未更新 | 必须保持未 ready，等待用户裁决真实观察 | 用户裁决 |

## Gate 结论

**accepted-deepreview-pass**。允许在该 accepted 产品 HEAD 基础上执行最小、真实、可供用户裁决的 post-fix CLI 覆盖；不得把观察脚本、报告生成器或 evidence framework 扩建为产品/通用基础设施，也不得根据观察结果自行接受 Oracle 或标记 readiness。
