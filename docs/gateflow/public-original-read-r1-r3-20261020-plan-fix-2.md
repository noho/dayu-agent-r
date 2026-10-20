# R1–R3 第二次窄 plan fix 回执：P1 单次补读语义

本轮仅按[第一轮受影响面复审裁决](public-original-read-r1-r3-20261020-plan-adjudication.md#第一轮受影响面复审裁决)及 [DS 复审 P1 finding](../reviews/plan-review-20261020-115908.md)更正已被直接证据证伪的补读指令。既有 Host cursor 成功使用一次后即被消费；省略 `limit` 返回全部余量，小 `limit` 仅返回余量前缀且不产生新 cursor。因此取齐本页必须一次省略 `limit`，不能连续小批补读。本轮不改变 Host 契约或新增状态机。

## 版本绑定

- 对比基线：`workspace/tmp/public-original-read-r1-r3-20261020/plan-revised.md`（保存 v2），SHA-256 `583596a6f754d6ff695f5b1ba4afd79c673cc485975a755bbf2229c2715d1bef`。
- 修订后：[当前 plan](public-original-read-r1-r3-20261020-plan.md)，SHA-256 `1e10b5595161854a1f456f21c34bb72f68587e76f11375f79cfd8b653dbc70e7`。
- 仅修改当前 plan，新增本回执；未另存或修改计划快照。

## 实际改动位置

| 当前 plan 位置 | 本次 P1 更正 |
| --- | --- |
| §3.2，第 102 行 | schema 说明明确按本次返回的 `cursor/scope_token` 调用一次 `fetch_more`，省略 `limit` 取得本页全部余量，与可见前缀拼接后再按 `next_start/next_offset` 续页；cursor 单次使用，不返回新 cursor，不得以小 `limit` 期待后续 cursor。 |
| §5 工具层范围，第 148 行 | 新工具说明补同一单次补读规则；取齐当前页后才按 Fins `next_start/next_offset` 前进，保留两层范围区分及既有 Host 机制。 |
| §5 prompt 范围，第 149 行 | 拟定 `fins-read` 指引明确一次省略 `limit` 取齐本页、再读下一页，以及 cursor 单次使用/无后续 cursor。原文四操作、namespace 发现、文件/hash 含义、财务标志及 scene 装配要求不变。 |
| §6.1 第 8 项，第 177 行 | 删除“小 limit 和每次新返回的参数连续取回余量”；每个被 Host 截断的 Fins 页用一次省略 `limit` 的实际 `fetch_more` 取得全部余量，与可见前缀拼接并精确比对该 runtime 页原文后再续页。既有 Host 的 limit 前缀、单次使用及 scope/token/过期断言保留为独立回归，不混入取齐页联合流程；不修改 Host 生产机制。 |
| §6.1 第 8 项固定预算分支，第 179 行 | 长结构/事实被 Host 截断时，同样明确一次省略 `limit` 取齐当前页；固定预算分支的适用条件和其它断言不变。 |

## 窄差异核对

- 修订前，当前 plan 与保存 v2 的 SHA 完全一致，`diff -u` 无差异。修订后执行同一对比，退出码为 1（存在上述预期差异）；逐行核对确认总行数仍为 264，仅第 102、148、149、177、179 行变化，其余 259 行逐字节相同。
- P2/P3/P4 已确认修订保持；本次仅补充上述行内的 P1 续读语义。根因、51 锚、53 调用及其它主方案不变，未重扫或重新核验。
- 前后 SHA 核对确认 goal、control、裁决、旧 plan-fix、首轮双路报告、第一轮双路复审报告及已保存的原计划/v2/裁决快照均未变化。生产代码、测试、README 未修改；未派 agent，未 stage、commit 或 push。
- 本轮仅验证文档差异及文件 SHA，未运行 pytest、pyright、coverage、真实 API 或 live 验收；§6.2 的实施验证命令保持原样，不作为本轮通过证据。

## 未完成项与状态边界

- P1 正式状态仍以未修改的裁决为准：`accepted / 部分修复`。本回执仅记录文本更正，须待总控对 v2→当前版窄差异及受影响句完成双路受影响面复审和裁决；不宣称 P1 已正式核销或 plan-pass。
- 唯一 implementation / validation slice 尚未执行；新 schema/prompt、真实工具经 Host 截断后取齐页的联合测试、既有 Host 独立回归及其它实施验收仍待计划放行后完成。本轮不宣称代码、测试、类型检查或实施验收通过。
