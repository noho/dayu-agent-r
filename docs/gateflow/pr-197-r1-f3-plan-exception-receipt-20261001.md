# F3 异常 contract 文字修订：总控核收

## 本轮证据与裁决

Sol `pr197-f3-planexception-sol-20261001-01`，Codex/gpt-6-sol，精确canonical model未知。托管99211已outer0；e3CL7a完整77JSONL可解析且turn.completed、stderr0；last/report/plan本轮令牌均与独立expected逐字匹配。根完整读取作者report与实际原件→候选差异，独立正向重建全部5替换严格相等，26readonly/27originals保持；全plan与全report noindexcheck均1且双流0。当前plan SHA `05729875b12bcf78a7518ed462b93cd582c056fb849321e38fed11e7fc09f126`，五utils源码未改。

改变只有头部元信息、分组预检ValueError链原OSError/ValueError、C01仅委托公共analysis_targets_alias以及schema/A-B直接来源行号。公共alias仍透传OSError，分组参数/返回/底层判据、所有C01/C02矩阵/原A1–A4/PA01/默认与布局保持。作者五替换往返与保护段不是产品验证；根逐句确认owner同一、没有新公开行为选择。接受本次作者delivery，F3-PR3-A1暂记已修候选，**尚未双路re-review/plan gate pass；C01/C02产品accepted未修**。

## 逐项工具失败恢复

完整event中非零命令只有四项（以下为1起JSONL行）：47错误断言u0 hunk=5，真实7，49/51读取并恢复；56错误约束全树status只能新增作者报告，非冻结F4根文档并发新增触发，58恢复相关冻结而不约束无关docs；63错误要求HEAD恒等起点，获授权根docs checkpoint推进2cc→49，65/67直接身份与路径核验、75恢复只记录HEAD；69元信息精确旧串已经不匹配，71读取实值后73按唯一行前缀更正。根逐条查看失败命令/原输出及对应恢复，不以末0遮盖首1；这些是验证脚本scope/计数错误，不改变候选技术内容，冻结已独立恢复，无关键缺口。最终静态恢复75实际exit0。普通工具错误已恢复不消耗provider重试。

根另一次浏览误用不存在workflows路径，sed诊断后rg --files明确实际在pipelines并完整读取目标，不将组合命令末0伪称前读成功；该路径错误与本文F3裁决无关，F4派发用真实路径。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 四项内部验证脚本失败均已定位及恢复，未掩盖退出码
  - HEAD推进为根授权docs checkpoint，source和26只读SHA保持
  - canonical精确model未知，不由token推断
  - noindex新增全文check exit1且零双流为预期差异
evidence_gaps: []
retry_class: none
```

输出/独立stderr/last在 `sub-agents.e3CL7a` 临时目录，原件与命令日志在 `workspace/tmp/pr197-f3-planexception-sol-20261001-01/`；作者报告 `docs/gateflow/pr-197-r1-f3-plan-exception-fix-20261001.md`。不修改旧失败或原件。

## 下一入口与残余

下一MiMo/已授权DS备份同时仅复审三个技术文字变化及对应差异保全，然后根裁决／必要fix/re-review→accepted amendment commit→C01/C02同一S1sourcefix。不重新裁决既有业务、不重跑19/22设计probe或全仓基线。真实源码实施的原完整临时harness+新增非空C01/C02矩阵+激活venv默认全量pyright0义务保持。C01/C02为covered by later approved slice（同一F3-S1后续源码fix，非新S2）；原输入缓存/算法/并发/Unicode残余沿原plan目标外destination，分类不用于放行当前accepted未修。其它WU为assigned to later work unit。文档技术修订无README触发。
