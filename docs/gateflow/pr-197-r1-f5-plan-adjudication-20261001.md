# F5 计划提案：总控核收与未决契约

## 交付核收

Sol11838/afAcYs托管outer0，77JSONL逐行可解析、turn.completed、无turn.failed/error；完整last与423行指定proposal逐字令牌匹配。34live/34originals SHA根独立逐项保持，完整proposal noindexcheck1且双流0。当前proposal SHA d3ce48055f5b2f9c6e398e9b1161b4aca72445feb5cb2afede8905f6b78bc5bb，仅新增该文档和本任务tmp，没有产品源码改动。运行身份codex/gpt-6-sol/canonical unknown，事件没有精确部署证据，不假报、不加用户业务审批。

实际非零：event62 sha表少一项因为手录hash漏ed，34真实input从未漂移，表文字随后修复并全34同源readback；复合命令末项noindex差异1，不能说前表通过。event71 noindex差异1零双流为预期。stderr255为一次apply_patch verificationfailed（段落片段找不到），按作者及后续完整行file_change/readback恢复；不是白名单metadata，明确保留失败，原patch未改文件。根检查全部event/其它file_change只有允许proposal/tmp，技术修订最终完整阅读。

根读取实际selector、calendar、rebuild、公开契约和原F5裁决，亲跑当前生产resolver五用例：长度无anchor=None；可信年末→Q3；相关年末月份冲突→None；显式Q3无anchor→Q3；只有远年anchor却→None。独立结果workspace/tmp/pr197-controller-collection-20261001/f5-design-root/result.json。此为设计/缺陷证据，不是产品修后验证；不重复无源码改变的全仓baseline。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
evidence_gap: proposal delivery accepted; public behavior unresolved and plan unaccepted
retry_class: none
```

## 新finding即时登记

| 编号 | 根裁决／状态 | 直接证据、owner与destination |
| --- | --- | --- |
| F5-N01 | 低／accepted／未修复 | 远年anchor不能否决原直接披露显式Q3；根五用例已证。calendar/selection应只消费相关年度集合，与原goal远年不滥用／显式季度保全同源；当前F5计划fix及S1，不另立未经approved future slice。 |
| F5-N02 | 中／accepted／未修复 | rebuild初始化row拷旧form/coverage/reportdate，factsNone只update reason，不确定事实仍旧标签；adapter必须空coverage拒绝使owner错误无法正确投影。根直接读rebuild35-105与projection严格消费面。需在rebuild生产者清晰表达本次未知，再由公开契约统一投影，禁止adapter重算或无条件allow-empty；具体公开方案随Q1计划fix审查，不默认采纳示意allow_empty参数。 |
| F5-N03 | needs-more-evidence／资料gap，不是已成立产品缺陷 | 官方已捕获fixture为空不能当非空原始标题。根负责查现有授权证据或最小只读官方请求；不得编造provenance或以此强加未经确认超goal验收。合成raw+真实Fs仍有效owner回归；是否必须新官方非空fixture由实际验证缺口判断。 |

原F5仍未修；同源storage信任view、取消/普通异常/ID/count/meta保持尚待计划审查，不因proposal可行采纳全部新类型与接口。共享rawF4能力不强迫trusted-only；两个WU实施必须串行，不读未来接口。

## Q1—Q3裁决与用户现成规则

- **Q1真正未决，已异步提交用户具体二选一**：同次查询已知和财期未知报告并存，继续处理已知并明确单列未知，或写前整请求失败。根建议继续已知以保全用户逐文档成功语义；方案须具体定义未知报告的来源引用／事实／计数与public/durable投影，禁止伪造documentID或把unknown等于missing。原proposal P1是可比较的最小替代，不是已授权行为，用户未答不能实施依赖它的schema/错误分支。Gateflow bindinggoal规则要求新的公开取舍先裁决，不重问已有upload裁决。
- **Q2根技术裁决：可信本地证据读取是HK解析的直接输入校验，读取失败原样终止，不吞成无anchor；其先于远端查询可接受**。原goal没有绑定provider错误必须优先，此顺序由新增正确输入要求决定，不借F4已撤回普通错误typed迁移改变任何type/cause/reason；CN无HK读取。不另造用户审批。
- **Q3根技术裁决：相同可用可信证据集合时窄/宽/rebuild一致；新增真实相矛盾年度证据则必须保留不确定**。原goal明确冲突不猜与禁止超范围历史爬取，无法承诺未获取事实也已知。这是信息边界解释，不放弃窗口一致性、不忽略remote／优先local／多数投票。必须把同集合等价与不同新冲突两组断言明确，不把新范围当未来硬化。

P1称未知时公司也必须零写只是提案验证，不改写用户独立company事实（O34上传既有裁决）的授权；最终HK业务proposal需按真实现有workflow时序说明公司事实边界。若新增“未知即停止已知”或raw公开字段/计数，则以Q1回答为准，不能根偷偷选择。

## 当前入口与排程

F5处plan/proposal，非code-generation-ready、非accepted plan、未实施；Q1待用户，Q2/Q3技术已收敛，N01/N02需计划纳入，N03核证据。可以继续不依赖Q1的其它F3/F4工作，不以时间当回答/授权。下一依赖入口是用户Q1答复→Sol固化最小计划/登记既有新findings→同版Planreview/必要fix/re-review→acceptedplancommit→共同源码串行实施。README当前不改，原prospective职责记录待产品落地。无主干改动/newbranch/worktree/PRcomment。


### F5-N03资料补证完成

根两个精确单日官方公开GET取得非空200body，生产严格snapshot/raw/00700stockscope/hash验证均有效。详pr-197-r1-f5-official-raw-evidence-20261001.md及临时owner-validation.json；N03“非空原始raw缺失”gap解除，不是产品已修。原官方季度标题带三个月及九个月，无anchor已合法Q3；根首probe错误预设None断言1已恢复并披露，未造窄窗缺陷或改raw。未来fixture合成未知标题需标合成，原body/hash/provenance保持。Q1仍待用户，方案不实施。
