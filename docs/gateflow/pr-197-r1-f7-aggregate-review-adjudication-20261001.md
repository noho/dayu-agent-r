# F7 Aggregate Deepreview：总控裁决

## 当前gate

F7 accepted S1已在PR197，commit31473fe1；当前aggregate gate尚未通过。MiMo27939/ru6aEW仍在途。Kimi47199/moVmMy取得托管outerexit1，必须拒收，不能把JSON subtype success视为通过。

## Kimi provider故障与授权备份

label pr197-f7-aggregate-kimi-20261001-01。完整JSON可解析，is_error=true，terminal_reason=api_error，api_error_status403，result明确“5-hour usage limit”，num_turns64，modelUsage kimi-k3[1m]。没有指定code-review-20261001-022319.md，结果无可比对令牌，canary_status unknown非match；stderr仅精确unrecognized_model warning不导致此故障。JSON另记录Write临时pyrightconfig permission_denial但未给原因，记录局限、不推断为额度或根自动审批拒绝；该工具取证未完成，不能采纳类型探针或任何审查结论。

原output/stderr/prompt/expected位于独立run_dir sub-agents.moVmMy，全部保留；不重跑来抹掉此provider故障。用户已有“Kimi额度不足失败用ds-flash备份”授权，因此下一独立label用Claude ds-flash，当前35冻结同版source/goal/plan不改，与原MiMo在途独立审查重叠；不是用户业务裁决变更。当前5小时额度窗口尚无解除证据，不能宣称恢复；后续审查路由须标注此实际provider失败与备份依据。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: unknown
tool_trace: summary_only
required_evidence: incomplete
canary_status: unknown
result_status: rejected
evidence_gap: provider quota failure; no review artifact or completed evidence
retry_class: provider
```

下一入口收取MiMo与授权ds-flash备份的真实终态/结构化结果/报告，根独立核验后才裁决aggregate。当前不accepted deepreview，不关闭F7或PR197。


## 双路终态与总控最终 aggregate 裁决

MiMo27939/ru6aEW与ds-flash11340/LVsUm9均已由托管句柄取得outerexit0，不再在途。完整JSON逐路解析为success/is_error=false，分别86/85turns；canonical model以各自modelUsage为准（mimo-v2.6-pro[1m]／deepseek-flash[1m]）。result及完整指定报告的本轮令牌均逐字匹配，stderr只有精确unrecognized_model warning。两报告为docs/reviews/code-review-20261001-022318.md和024935.md，完整读取后根再次独立35live/35originals SHA、九目标文件工作树与31473fe1一致、实际九路径diff与冻结aggregate.diff逐字一致，完整报告noindexcheck各1且双流0。独立receipt：workspace/tmp/pr197-controller-collection-20261001/f7-aggregate-final-receipt.json。

Claude JSON为summary_only，不能以86/85turns或令牌声明每个内部tool成功。MiMo披露/dev/fd比较受限、两轮类型探针setup噪声及zsh组合读失败，分别以cmp/hash、正确None返回并只关闭探针私有访问诊断、分开sed恢复。产品类型没有豁免；根前gate独立严格正负探针各实际分析1file，正0／负恰2reportArgumentType已从同源签名复核。DS披露第一次JSON键diagnostics误用、全量diff与九路径冻结范围不同，分别以generalDiagnostics和显式九路径恢复；根实际再次九路径逐字比对，非快照漂移。DS临时pos/neg.json根已实读：各filesAnalyzed1，正0／负3（2argument+1assignment）；两路关键证据恢复，无未解决取证缺口。预期rg无命中exit1、ls写前文件不存在1、noindex差异1与真实失败分开记录；不抹去Kimi403原故障。

根同源裁决证据：九路径完整生产／测试／README增量及owner→workflow两producer→rebuild→collector→adapter两个入口→direct/job保全；词表原字符串、strip、取消时点、原异常／rows/count/cause均未改。唯一新设计是Literal/Final共享owner与各入口同真源子集，移除producer私有跨模块常量。两路独立阅读与74/188+65定向pytest只是补充；根此前亲跑741pass／全量pyright0、四文件coverage97.22／94.76／85.64／94.61均绑定本轮九源码同字节，未无理由重跑基线。当前没有成立material finding；F7唯一S1完整组合通过aggregate Deepreview，fix/re-review明确no-fix pass。

残余分类与范围：

| 项目 | 分类／owner／destination | 根裁决 |
| --- | --- | --- |
| 三值重复／producer漏迁／入口子集漂移 | fixed in current slice；共享模型owner | 同源代码与契约测试已修且本aggregate复核 |
| 类型门禁＋adapter原runtime拒绝，不新增producer runtime validator／rebuild字段收拢 | fixed in current slice；当前acceptedplan边界 | 既定最小方案已落实，不把固定设计重标新风险或偷偷加验收 |
| 行级/SEC/公开disposition词表与原因码 | assigned to later work unit；相应协议owner／根是否立项 | binding goal明确非目标；无本gate成立finding延期 |
| CN/HK空库rebuild取消既有不对称 | requiring new issue or explicit user decision；用户／根后续另定goal | 本增量未改变或放大，现成不改裁决保留；不是当前blocking业务选择 |
| 全仓pytest／真实外网与转换／PR整体风险 | assigned to later work unit；PR197完整验证／PR review与final closeout | 741及全量类型已亲跑；未冒称全仓/外网本路执行 |
| F3/F4/F5/F6共用源码及未完成队列 | assigned to later work unit；根按既有依赖串行 | 不把其它accepted未修项归为F7已闭环；全PR仍处修复 |
| Kimi403、运行metadata工具可见性 | assigned to later work unit；runner诊断owner | 故障保留；既有授权DS备份有效，无业务语义改变 |

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
evidence_gap: none for F7 aggregate gate; PR review and final closeout pending
retry_class: none
```

**aggregate gate pass，仅针对F7当前完整目标。** 下一Gate Order entry为accepted deepreview commit→ready-to-open-draft-PR（沿用用户指定现有draft PR197）→push/读回→PR review，后续PR review/fix/re-review/accepted PR review commit/finalpush/draft-PR-pass/finalcloseout仍未完成。不能以已存在PR、Git MERGEABLE、其它WU旧closeout或本aggregate代替F7的这些gate；不新建PR、不markready、不merge、不对外comment。当前两空位按既有优先修复队列派F3同版窄Planreview，F7 PR review待下一组审查名额，普通gate不是停止授权工作理由。
