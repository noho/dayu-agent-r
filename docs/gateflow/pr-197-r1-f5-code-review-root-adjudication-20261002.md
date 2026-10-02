# F5-S1 正式代码审查总控裁决（MiMo仍在途，未gate pass）

审查freeze7545bd52：86 current、46 changed（23生产/3README/14测试/6正式fixture），精确基线3a836a46。总控原始基线46件Git对象对照无差异，86 live/snapshot及diff匹配；独立82owner回归通过。两路是MiMo/MiMo-flash，禁止以两票或作者自报替代裁决。

## MiMo-flash 57771 终态核收

outer0、11560合法JSONL、全部工具成对、result success/is_error=false、实际当前canary读取匹配，stderr只有精确SDK unrecognized_model非致命warning；报告 code-review-20261002-093801.md已全文读。当前86源及15验证证据仍匹配。107passed、fullpyright0、取消/IV04 probe最终5输出均符合预期。IV01–04 owner修复/实际回归与总控源码和82真实回归一致，新增material为空。

全部工具结果保全 workspace/tmp/pr197-controller-collection-20261001/f5-final-code-review-mimo-flash-root-receipt.json。内部非零及隐藏失败逐项裁：

- 历史provider-interruption文档误去掉s1，wc/cat找不到；未恢复正确历史文件的全文读，报告“6作者文档全读”该部分不采纳。原历史报告当前SHA仍核，最终作者/计划/binding/四finding原文已实读，非本门禁关键缺口，不据错误读史声称证明保全。
- probe前三次分别没有创建jobstore、非法jobID、save不存在job；shell末echo为0不能代表probe成功。其真实exit1/Traceback在完整事件保存，均为探针设置错误，不登记产品bug。最后采用create_job及合法32hex ID后原探针输出5项全部符合预期、真实probe.exitcode0；仅采最终证据，不抹旧失败。
- 报告的路径分类加总与46不符，以实际manifest的23/3/14/6为准；错误函数简称 `_build_cn_download_result` 以实际 `_build_result` 为准，不为metadata/nit另开slice或fix/reviewloop。

## Open Questions 裁决

**Q-A closed / rejected-as-defect**：计划§5“请求窗口并集”是多个请求财期窗口的并集，不是远端运输最大查询窗与业务请求窗的并集。准确集合为 `filing_date ∈ query_window ∩ union(period_windows)`。`resolve_window`既有doc明确最大5年运输窗，workflow再按业务window；`resolve_period_windows`的FY5年/非FY2年及60天宽限是既有规则；§4明确当前请求范围、明确不属请求财期保原过滤。未知不能用猜测财年来每期裁剪，故代码使用any窗口纳入，而不按未知财期选择一个窗口。扩成query窗与业务窗并集会引入业务窗外材料及无关unknown失败，扩既有行为，未被用户裁决授权。源日期作范围条件，绝不作财期推断。保持accepted计划原始SHA，在本裁决澄清，不改源码/重问用户/扩大网络窗口。

**Q-B rejected-with-reason**：classification按同稳定根同枚举inventory必有键，当前没有可达分歧的直接证据。若未来实际发生，修inspector/枚举owner，不在consumer加typedKeyError兜底或默认分类。此前同根反例/原异常/guard释放回归保留，不为假设扩修。

## residual 分类

二次终态保存失败warning、未返回typed的lateordinary全局快照→既有runtime/storage，计划§10非目标；filing_date None未来producer→discovery/selection，现役raw/rebuild必有有效披露日期，不扩消费者fallback；typedabort实际source边界由完整typedsummary校验，CN恒空未知→既有CN/HKowner，无现行逃逸；store取消非法投影测试覆盖由本轮真实probe补证，owner读写已failclosed，不新slice；超窗/52周/过渡财年/不支持标题→calendar/selection信息边界；外网/Docling/最终CLI campaign→用户已指定的新Agent后续验收，不宣称本轮完成。

下一步收MiMo完整终态及全部工具证据，核实际source/fullreport后独立裁决正式codegate。现在不accepted slice、不提交、不进入aggregate。

## MiMo 86817终态与本轮codegate结论

outer0/22238合法JSONL/145成对工具/result success/is_error=false、实际canary/86源/15验证全匹配；SDK精确warning非致命。完整report code-review-20261002-100334.md已读。107回归与7关键文件pyright0、IV01–04确认修复，唯一material与root已登记IV05相同，不重复编号。选择CLI literal owner修复，不收紧public合法字符或裁断引用；根因是显示格式，同数据真源、财期、状态不变。

两报告输入metadata错误不采：精确baseline为3a而不是mainfac32；实际46manifest，不采42/44路径计数。root生成的文本diff在两无尾换行body后未加newline标记，导致两个后继header粘连；旧freeze/diff原件不改，六件Raw实际SHA/严格解析/完整移交回归已直接证明，源字节身份无缺口。下一fix/re-review冻结输入生成规范的no-newline标记及独立新增文件diff，全部46文件头再核，不能沿用错误计数。此为总控取证格式更正，不产品slice/nitfix。

Q-A/Q-B及residual前文裁决继续有效，两审未新增业务裁决。IV01–04已修复并经两路真实复审/总控回归验证；IV05 accepted/未修，正式codegate当前不通过。两source租约均结束，下一步gpt-6-sol集中当前同F5-S1的IV05必要fix及owner测试，完成后MiMo/MiMo-flash同版re-review。禁止为此新开slice或重规划/重读全部已交付义务。
