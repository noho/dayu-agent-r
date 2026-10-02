# 统一修复计划正式双审：总控裁决登记

Gate：plan review，尚未通过、没有 accepted plan checkpoint。冻结候选 SHA `2fc3d1911737e4afcd964a2cb586a2e661c5fd38a55cf62480c15ce6c3a9f9d7`；HEAD `619d092ab4278645203c7ebe08515f7697d92b71`。MiMo 仍在途（session59215），不得修改冻结输入或开始实施。ds-flash session5140已返回outer0，独立artifact `docs/reviews/plan-review-20261002-182942.md`。

## ds-flash 证据核收

完整 stream-json 明确 result success/is_error=false，实际 model `deepseek-flash[1m]`，136 turns、135 tool uses。工具实际Read本轮校验值与最终报告匹配，stderr中明确 `[claude-code:unrecognized_model]` 为skill精确允许warning。已读全部artifact并独立追A/U/R与5处真实commit调用点；9226冻结输入现场核对无漂移。

作者自述“一条===报错”实际上两条Bash失败：`call_00_YyTBmW2cH9Ktbfg5qaWl0769`、`call_00_ItaVDnnt9cBEiBmUk3545783`，均zsh把未引号===解释成命令查询；后续正确定位已恢复，root亦独立复核相关代码。第一次source核验脚本绝对路径误拼导致3假missing/内部exit1，修正后18/18正确；Raw EOF diffcheck内部exit2为既定有效反例。含复合命令的Bash返回不能证明内部全exit0。完整流、逐失败/恢复与校验在独占 `formal-plan-review-01/ds-flash-runner-audit.json`，不把作者摘要当唯一证据。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - unrecognized_model精确warning，不是provider失败
  - 两条zsh定位错误及source核验脚本错误已恢复；作者摘要少计一条，root纠正
  - Raw EOF diffcheck非零是本次预期反例，不是全PR验证pass
evidence_gaps: []
retry_class: none
```

报告可采不等于计划通过。子报告pass-with-risks没有放行accepted未修findings的效力。

## 成立修复清单（立即登记，等待MiMo结束后一轮集中fix）

| ID | 裁决 / 最终状态 | owner / 准确修订方向 |
| --- | --- | --- |
| UP-DS-F1 | accepted / 未修复 | S2调用迁移：实际5处含`filing_upload_publication.py:859`，加入最窄白名单且filing显式None，原返回/取消语义保留；不造兼容默认。 |
| UP-DS-F2 | accepted / 未修复 | A资产规划持规范化路径与selector算法，U持usage分类/消息，R只消费；补精确失败出口/映射及一次路径规范化。**不采纳建议中的“material selector整体移到planner前”**，它会改已裁数量→路径/名称/格式→selector首错。保持现成顺序，用明确typed selection失败出口，U保持既有filing REQUEST语义、不扩planner-exclusive枚举吞selector；不能A反向importU。 |
| UP-DS-F3 / P0-R09 | accepted / 未修复 | 技术采集器：封闭实际I/O判据与证据字段；转换退出/SUCCESS不作读取判据；未观察=unknown/not-attempted，runtime例外=允许；实际denied须同源请求/OS证据。只修新独占采集器副本和计划，不改产品为财务准确性reject、不刷旧失败。 |
| UP-DS-F4 | accepted / 未修复 | 计划当前binding输入引用与冻结字节一致，明确历史读取版本和动态control gate状态区别；避免后续控制状态变化被误判goal变化。不是改变用户目标。 |
| UP-DS-F5 | accepted / 未修复 | 计划状态/§8/§11同步当前已证可行性；已执行证据与作者交付时“待核”历史分开，不再触发昂贵重复准备。仍非accepted checkpoint。 |
| UP-DS-F6 | accepted / 未修复 | U selector文案/hint唯一owner按明确source kind产生，material不输出filing对象，filing既有字面合同保持；与F2同一次完整准入修订，不单切片。 |

## Questions 的总控处理

- Q1：保留现有仓储最终条件guard，并复用同一个校验owner；writer保护与提交前自有staging/recovery边界不是删guard的证据。不得让publication层反读重算，也不新增第二种状态机。只读登记和最终提交条件是现有仓储模式的最小材料扩展。
- Q2：S1仍一个完整行为slice，允许内部正常保存技术证据/进度，不把它切成额外gate/checkpoint或按文件微拆。一个implementation pass集中完成V1–V6，正式slice review/accepted commit一次闭环。
- Q3：与F2同修，明确identity owner抛typed`FinsUploadUsageError`及唯一U事实，不迫使实施者发明新异常/分类。
- Q4：集中plan fix补实际独占探针启动脚本包裹真实CLI/owner入口的可执行barrier recipe，不改产品、不替换仓储/结果；同步启动但未证共同old admission的轮次仍只算顺序幂等。
- Q5：补无配置、配置/准备复验失败→既有`CONVERTER_CONSTRUCTION`的准确owner映射；不新资源reason/回退，也不把内容准确性评估纳入。

所有项仍单一WU/三行为slice；正式PR review在全slice+aggregate后，完整CLI/registry在WU后。下一入口是等待MiMo真实终态、完整核收并合并同根因findings，再派gpt-6-sol一次集中plan fix，随后同版双路re-review。没有因这份单路结果提前写计划或实施。

## MiMo 终态核收与统一 fix 入口

MiMo session59215 已取得外层退出0，stream-json 13461 events/43 actual tools/result.success/is_error=false，实际 model `mimo-v2.6-pro[1m]`。实际 Bash 读取本轮校验值，最终匹配；精确 unrecognized_model stderr 为允许warning。两次真实工具错误：f-string SyntaxError、未引号glob及连带sed失败，后续全量9226哈希、正确源码读取恢复；总控再次逐件核9226/9226无漂移。完整轨迹与恢复保于 `workspace/tmp/upload-material-unified-repair-20261002/formal-plan-review-01/mimo-runner-audit.json`。artifact已全文核读并追实际 tool material 拒primary分支及同owner文案。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 精确unrecognized_model warning
  - 核验脚本语法和glob定位失败已恢复；复合命令内部失败不能以outer0抹掉
evidence_gaps: []
retry_class: none
```

| ID | 裁决 / 最终状态 | 根因和集中修复 |
| --- | --- | --- |
| UP-M-F1 | accepted / 未修复 | 明确删除tool material拒primary分支及旧否定文案；format owner统一primary/help/files说明与真实tool断言。四selector code与总5selection failure区别逐项列清，不能把missing/duplicate重复计数；与UP-DS-F2/F6同次修。空字节由原始字节owner判内容失败，LLM只写业务可读内容，不暴露内部实现术语。 |
| UP-M-F2 | accepted / 未修复 | 同UP-DS-F3/F5及P0-R09，归同根因，采集器判据与当前可行性状态集中修。 |
| UP-M-F3 | accepted / 未修复 | 同UP-DS-F4，准确冻结读入版本；动态control与历史binding分清。 |

MiMo Q1：既有`.xml/.xbrl`已是XBRL候选，S3按受控配置路径；明确README缺配置行为与CONVERTER_CONSTRUCTION，不新增普通XML兜底。Q2同DS-Q3：identity owner抛typed FinsUploadUsageError，唯一U映射。

正式plan review未通过，下一未完成gate为fix。冻结版原件与两个review保留，gpt-6-sol一次集中处理全部成立项和已决questions，再冻结新候选进行MiMo/ds-flash同时re-review。仍三slice，不额外切片、不提前产品实施。

## 一次集中 fix 已核收，下一未完成 gate：re-review

gpt-6-sol session53531终态outer0/turn.completed，100events/40 actual completed commands，actual model未暴露记unknown。实际读取本轮校验值且final一致；stderr空，无error/turn.failed。修后planSHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`。作者报告 `upload-material-unified-plan-fix-report-20261002.md` 已全文核；新技术采集器/owner/tests和plan新增合同已沿actual source核。4合同测试pass、判据owner coverage100%、自身explicit10script pyright0；不冒产品全量验证。

root逐件核869protected、18sources、14inputs及delivery清单无漂移；正式9226清单仅计划及root控制状态两项预期变动，所有tracked产品/测试/依赖/持久旧证据未变。root第一次delivery-map诊断错用顶层metadata当path，已改正确nested hashes全部实核，不是实际缺件。40commands的3非零分别：item39收据数量误计（10关系另1取消，总11，已修）、item44新脚本typed None推断（已修pyright0）、item46 no-index diffcheck1/空双流为差异，不冒fullPRpass；item26内部rg2可选不存在配置已用实际pyproject恢复。完整私有audit在concentrated-plan-fix-01/root-runner-audit.json。

全部UP-DS-F1..6/UP-M-F1..3/P0-R09为“作者已修、总控证据可采、待同版re-review”，尚不能标gate pass。S2第五caller、A/U/R typed失败出口与一次normalization、tool material primary/空内容文案、O33真实barrier配方、初始化异常owner、采集器五值判据与plan当前状态已一起收口。runtime allowed/unknown/未观察诚实保留；离线没有kernel raw不能制造denied事件，已有root精准PID93381证据与不同证据集合区别保留。不重复昂贵macro/安装。

### 技术输出范围偏差裁决

首次pytest默认覆盖了ignored `.coverage`、更新pytest nodeids。作者保全本轮覆盖率、修改后缓存，移除自己新增4nodeids，后续独占COVERAGE_FILE及禁cache；**旧.coverage原字节未知，不能声称保全/恢复了该临时缓存**。root已核所有tracked及本WU持久旧Raw/报告/源码字节未动。这个可重建生成缓存不属于业务代码、输入原件、accepted artifact或本WU必要验证真源，无现有gate依赖它，裁为已解释非阻塞技术warning；既有持久coverage/test日志继续按原SHA使用，旧临时coverage不当证据。后续派发强制coverage/test输出独占，不重复同类失误。不需扩大产品scope、增加slice或重做旧全部测试。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 3个非零及内部locator失败已逐项解释恢复
  - 默认pytest缓存路径偏差；旧coverage缓存原字节未知，不能冒历史完整恢复
evidence_gaps: []
retry_class: none
```

下一入口：冻结修后同版plan+inputs、MiMo/ds-flash同时独立re-review，全部accepted findings经复审已修才acceptedplancheckpoint。三slice/全slice后PRreview/WU后CLIregistry顺序保留。
