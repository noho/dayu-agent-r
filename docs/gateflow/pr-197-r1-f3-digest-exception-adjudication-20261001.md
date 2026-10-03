# F3-PR4-A1：digest 私有预检异常说明残余矛盾

## 直接证据与独立裁决

DS74668/4mBOyc已托管outer0，完整JSONsuccess/is_errorfalse/35turns，canonical modelUsage deepseek-flash[1m]；唯一报告043243中的本轮令牌逐字匹配expected。JSON最终result未重复令牌，但本次协议只要求报告声明，报告实际匹配，非mismatch。stderr仅精确metadatawarning；根12live/12originals/oldplan38SHA及完整report noindex1零流保持，实际schema/A-B行号逐点同源核对。Claude只有summary_only，报告披露一次218/219索引脚本失误后26锚点恢复，根实际source读取一致，不造中间全tooltrace。

根接受该路三个已改技术文字的复审证据，F3-PR3-A1已修候选受支持；MiMo83589仍在途，尚未合并gatepass。不能因本路pass-with-risks而放行新的真实遗漏。

**F3-PR4-A1：低／accepted／未修复（计划文字）**。候选05729875的123行 `_require_distinct_digest_targets` 表称“身份检查 OSError 向 main 传播”；136行判据5却明确私有helper补记录/PDF/目标和“无法检查固定汇总冲突”后重新抛具名ValueError链原异常。128行又笼统要求“新增函数docstring至少说明…ValueError/OSError”。后者可能引导纯路径推导helper虚构异常、或私有分组helper继续宣称直接OSError。这是同一私有错误owner的精确接口矛盾，CLI exit2虽相同但是否有具名上下文/raises声明仍不同。根直接完整对读表、判据5及N7/C2-N5，确认正确现成语义是判据5的具名ValueError链原异常；不是新的公开行为选择或用户审批。

最小fix只有两句：123行改为私有helper补具名上下文后ValueError链原OSError/ValueError；128行按各函数实际contract说明参数/返回/异常，纯路径推导不虚构业务异常，私有预检ValueError原因链。保留公共analysis_targets_alias透传OSError、公共require_distinct_sample_targets具名ValueError链、main原except(OSError,ValueError)、固定布局/判据/全部矩阵/类型/PA01逐字。禁止新异常类、新增矩阵、业务hardening、新S2或代码变动。该fix目的在owner contract消除互斥说明，严重性不放大为产品故障。

## 当前入口与残余

新修复项即时在本artifact及根三份当前状态登记，防上下文丢失。先收MiMo当前057版终态并根合并证据，然后Sol仅两个文字句fix，同版MiMo/授权DS备份只审两个改句及保全，不重跑已有22probe或wholeplanbaseline。F4唯一sourcewriter和本task文档写界无重叠；文字fix可并行，F3真正sourcefix等F4writer结束。C01/C02产品仍accepted未修，未来同一S1的非空harness/新增矩阵/fullpyright义务保持。

分类：本finding为fixed in current slice（待当前planfix/re-review，分类不作pass）；C01/C02为covered by later approved slice（原F3-S1源码阶段，非新S2）；其它WU为assigned to later work unit；原Unicode/跨运行缓存/并发外部替换等残余按原plan既有用户/owner目的地，不扩大当前goal。只内部计划语义，README不触发。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 一次索引脚本错误已恢复，root实际行号与独立完整差异一致
  - 精确model metadata warning非致命
  - JSON result未重复令牌，但本任务报告协议及artifact已实际匹配
evidence_gaps: []
retry_class: none
```


## MiMo终态与合并裁决

MiMo83589/1wCeVm已outer0，JSONsuccess/is_errorfalse/24turns，canonical modelUsage mimo-v2.6-pro[1m]；result及完整050515报告令牌匹配。根完整读报告、12live/12originals+原件38SHA与全文noindex1零流保持。summaryonly局限保留，报告仅披露预期diff1/路径未占2，没有实际逐tooltrace，根不背书“全部工具零失败”；根实算全件五替换与真实来源行已复核。两路均证明三个已改句正确、无新回归；F3-PR3-A1回写已修复，既有PR2-A1/C02计划主体亦已修复。两路同源新旧123/136矛盾与根独立证据一致，合并到既已登记F3-PR4-A1低accepted/未修；128实际异常章节清晰性一并同一文字fix。

不采MiMo“若明确接受可保留/延期”路径：code-generation-ready仍有互斥文案，现成判据5已经唯一规定具名ValueError链原错误，无新用户选择，必须当前fix/re-review。当前整个F3 plan gate **未通过**，下一Sol只改两句，再同版窄双审→根裁决→accepted amendment commit→源码C01/C02。现有根裁决没有改变用户业务语义。

## 两句修复 Sol18703 终态核收

托管18703真实exit0，0xbuvT完整33JSONL可解析、turn.completed、stderr空；报告e9121de2本轮token与expected匹配。last未重复token，但preflight要求报告声明，报告已真实匹配，不误判mismatch。根逐件15原件/14readonly SHA保持，完整plan当前2983efa4独立正向两唯一替换等于全件当前bytes、逆向回原件；只有123/128两行变化。全文plan与报告noindexcheck各exit1/双流空。完整owner技术句与保全原件同源，不以作者末消息作pass。源码五utils不变，pytest/types/cov本轮N/A。

实际非零item_8/JSONL17因unified2相邻两个改行合成一hunk而错误assert，编辑本身已正确；item_11/22实际读unified1两hunk并正逆全件恢复。item_13/26生成报告检查真正尾空白exit3导致outer命令assert1，item_14/28实读诊断，item_16/31将嵌入diff换成真实unified0并完整复检exit1零流。原失败/恢复三项保留，不作全部工具零失败。根独立复核两改句、14保护源、全部原件、report全文、恢复日志。delivery accepted；F3-PR4-A1仍仅已修候选，待同版窄双审，plan gate未通过，C01/C02产品未修。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 相邻diff hunk错误assert已恢复，编辑字节保全
  - 报告嵌入diff真正尾空白已修并全文核验
  - last未重复token，报告本轮协议已满足
evidence_gaps: []
retry_class: none
```

修复分类仍fixed in current slice待re-review；C01/C02 covered by later approved slice（同S1源码阶段），其它WU assigned to later work unit，不改用户业务。下一同版窄双审在名额可用时并行，accepted amendment后才能sourcefix。F4冻结code-review期间不改共同source。
