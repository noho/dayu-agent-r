# PR197 F3/F7 返回核验与 F3-PA01 裁决

## 现场及当前入口

唯一主树 `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD `b42bbea1e7ccc58561764c20d873214783283eb2`。只以用户现成裁决为准。F4 的 MiMo79430/Kimi44800同版复审仍在途，32相关SHA必须保持；F3/F7 Sol均已取得外层终态，不再冒称三路Sol运行。

## F3 amendment 收取（保留候选，不放行）

Runtime codex/provider gpt-6-sol，label pr197-f3-planamend-sol-20260930-01；自报model gpt-6，仅按该轮可见证据保留，不据现部署profile倒填历史型号。托管88943外层exit0，9dmnBf目录111有效JSONL/turn.completed/stderr空，last+artifact中的token与expected逐字匹配。完整output/stderr/last在本轮runner独立目录，原文件不覆盖。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: partial
warnings:
  - 'item27误断filesAnalyzed=0，实际2；随后相对include修复严格2文件零错。'
  - 'item33 schema缓存fixture缺成功字段导致反例探针失败；只修fixture后五碰撞CLI和三个无关CLI取证恢复。'
  - 'item42临时fixture空列表Unknown，明确JsonValue映射后严格2文件零错。'
  - 'item50/56 no-index新增差异exit1且无空白诊断。'
evidence_gaps: []
retry_class: none
```

总控独立七只读SHA与八原件一致、新plan68c73f081a66a2457667cbe1d3d0b8ea273d98e862970a74f53318b1bcb4fc9f、精确diff保存在workspace/tmp/pr197-controller-receipts-20261001。将作者两probe复制到独立同深度workspace/tmp/pr197-f3-controller-amendment-probes-20261001，不覆盖作者证据；激活venv分别实际重跑：五真实digest CLI均exit0并覆盖numbers（缺陷证据，不是修复通过），三个其它CLI均exit0且digest字节保持；设计probe10拒绝/6接受（design_only，产品未修）；严格pyright相对include/exclude=[]实际2文件0error。三个操作外层均0。newartifact no-index独立1/零双流。

取证可采纳，计划仍为未accepted候选：下述F3-PA01文本矛盾必须修后一起同版窄Planreview。C01仍accepted/未修复，implementation blocked，五utils源码候选全部保留。无provider重派或切换。

## F3-PA01／未修复／低：增补验证条款矛盾

- 裁决：accepted；owner为F3 plan验证契约，destination当前C01 amendment的Sol文本fix与MiMo/Kimi窄复审。
- 直接证据：plan第160行称“本轮及后续C01窄fix不…全量pyright…原gate最终要求由总控…不重跑未改全仓基线”；同一plan第19/44/571行及AGENTS要求真实代码改后激活venv全量pyright，不能以受影响文件替代。
- 影响：实施Agent可能把原780文件历史基线当后续真实源码修后门禁，产生错误免检，不是产品业务缺陷。
- 最小修法：明确本次仅计划文本与临时probe不重复全量baseline；后续真实C01源码fix必须按原S1/AGENTS跑激活venv全量pyright，历史780文件不能代替；保留严格临时配置与utils永久tests/coverage豁免。只改此验证段及对应增补报告表述，不改goal/技术判据/矩阵/源码。
- 根因：增补计划把“避免重复未改代码的baseline”扩大为后续真实改动的验证豁免。现授权已经包含该qualitygate，无新业务取舍，不重新请用户裁决。
- 风险分类：fixed in current slice（仅待fix，不宣称已修）；后续真实源码验证属于同一原S1义务。

## F7 PV01 收取（等待窄复审）

Runtime codex/provider gpt-6-sol，自报model gpt-6-sol，label pr197-f7-planfix-sol-20260930-01；托管40745外层exit0，WrEfzE目录83有效JSONL/turn.completed/stderr空，last+artifact校验token与expected逐字匹配。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 'item24/29新plan与item34/39新fix no-index exit1均为差异且双流空。'
  - 'item30精确版本diff exit1为真实一处变化，无空白失败。'
evidence_gaps: []
retry_class: none
```

总控独立20只读SHA/21原件/四额外证据匹配；新plan5820a4924bcd91c7a964b3bbc241fa739979ef3a8183bf11a7837787dc944e3d精确只有第245行1行换4行，逆替换逐字恢复旧冻结，全部技术正文不变。结构与plan/fix独立no-index1/零双流核验成立。未重复679测试baseline或coverage，修后真实门禁保持。此accepted只采作者事实修复证据；F7-PV01仍等待同版MiMo/Kimi窄re-review后回写已修复，plan gate未pass/产品未实施。

## 排程与剩余风险

F4仅计划审查，MiMo/Kimi同版freeze32input，输出/stderr独立，显式绝对cwd；尚无终态不接受结论。F3下一个入口Sol窄验证条款fix→同版C01双审→accepted amendment commit→原源码fix；F7下一入口PV01双审→accepted plan commit→实施。F4审查未终态前不得改变共用CN/storage源码，F7实现必须与F4源码排程串行。三个产品finding仍未闭环，不宣称整个PRpass。

README决定：本轮只有开发治理文件和隔离临时探针，不触发产品README修改。风险：原C01外部并发换链接/缓存鉴权等仍按原artifact requiring new issue or explicit user decision，不扩大当前目标；F4/F7共用源码变动风险 assigned to later work unit，由总控串行排程。所有代码/报告均保留，不操作main/新branch/worktree/外部comment。
