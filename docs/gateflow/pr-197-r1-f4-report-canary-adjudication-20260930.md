# PR197-R1/F4-PV01：候选计划报告校验标记不匹配

## 生命周期、输入与直接证据

codex/gpt-6-sol label `pr197-f4-planfix-sol-20260930-02`，托管51450已外层exit0；80条有效JSONL，turn.completed，stderr空。最后消息和两个计划artifact均报告 `gpt-6-sol-c242e29`，本轮预检基准及实际文件均为 `gpt-6-sol-c242e290`，末尾0缺失。总控逐字比对确认 mismatch，不以最后报告自称精确匹配放行。

item_1真实cat结果包含完整正确值，exit0；这支持工具确实读取文件，不修复报告字符串不匹配。item_34收尾通过Python读取并将错误短值另写进报告，命令exit0也不证明内容正确。依据sub-agents Result Validation，canary mismatch是硬拒收条件，外层正常完成不等于结果可接受；不能由总控替它改一位再自动宣布验收通过。

当前candidate plan SHA `e972b900adfd62e8ff27fc9bc0fa72f94f296beef9a903927cf85160a3186c6d`；user-scope fix SHA `d5fc7f29ee80c2f95031f34c9e3998a49091e75bb9a98437f07226e94bf348ed`。修复前原字节已保存 `workspace/tmp/pr197-f4-report-validation-20260930/` 与sha.json，旧blocked candidate仍在60307，任何版本不删除。总控核本轮原freeze：除可改plan外22项只读输入均不变，bindinggoal d1f374...正确，源码未改。

## 每非零步骤及影响

- item_25 exit2：搜索了不存在的cn_download_runtime.py；后续实际inventory找到ingestion_runtime/download_contract/tools和真实tests，补读公开projection，来源恢复。
- item_26 exit1：zsh不存在glob阻止rg执行；随后item_27/28使用真实路径恢复，不用无结果推断错误语义。
- item_38 exit1且无输出：新增artifact的no-index差异退出，无空白诊断，不是产品失败。
- 初次pyright绝对include无效的配置警告虽外层exit0，作者已改相对include/显式exclude=[]后实际Found1源文件、strict0错；仅类型形状，不证明生产新API通过。ownerprobe未纳入strict，不冒称全临时代码类型通过。

以上已解释的工具问题不是拒收主因；**F4-PV01（低，报告准确性）为canary不匹配，未修复。** 技术候选的设计论证先保存，不能计accepted plan或通过子任务。总控已实读有序成功前缀/原异常/候选依赖错误优先级/两新鲜观察窗口方案；后续同版审查仍须核验全部真实source，不以该记录预先接受方案。

## 裁决与唯一恢复路径

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: mismatch
result_status: rejected
warnings:
  - 实际工具读取完整正确值，但报告三处漏末位
  - 不存在路径及glob错误已通过真实owner路径补读恢复
  - 初始include警告纠正，严格形状仅1文件，不是产品新API验收
  - no-index差异exit1已解释，未掩盖为0
evidence_gaps: []
retry_class: task
```

允许一次明确理由的同provider窄修复性重派：新label/独立输出/新本轮标记，只修历史报告准确性并重新核当前22输入及候选身份；保留原误报值/失败解释，不改产品设计、源码、业务裁决或重新评分。新任务按其本轮协议报告自身校验值、用实际字节核对；旧任务读取正确/报告错误必须作为历史事实，不冒称旧验收成功。新结果经总控完整核验后，才能冻结候选并同时派MiMo/Kimi Planreview。恢复若再次失败，先归因/依skill重试限制，不无限重派、不据此切Kimi配额备份。

当前F4产品未实施，plan gate未pass；用户既有错误、事件、继续、取消与manifest成功语义保持。此报告修复无需新的业务裁决。

## 修复派发setup与在途记录

reportfix label01预检失败，未启动：canary命名裁决文件的8位日期匹配了机械旧token regex，并非正文提供旧校验值。总控保留失败task、将同字节裁决复制到不触发文件名规则的临时controller-evidence.md供读取，新label02重新预检ok；未禁用检查、未改预检器。label01裁定setup_status fail/agent_status not_started/tool_evidence no/tool_trace not_required/required_evidence not_required/canary_status not_run/result_status not_assessed/retry_class setup，不占provider重试。

唯一一次同provider实际恢复任务reportfix label02已启动，托管91705/run_dir KELGKS，独立output/stderr/last/新校验文件，显式cwd主树。当前在途，不填完成裁决；技术正文/源码冻结、旧失败原件保留。

## 修复任务终态：报告修复已验证，旧拒收不撤销

reportfix label02/托管91705已外层0，59有效JSONL turn.completed，stderr空，last和新artifact的本轮token逐字匹配。总控独立核22只读input、旧原件/技术正文零变化、全部精确diff和三文件单独no-index check1/无诊断。新candidate0080f245...可作下一同版审查输入，plan仍未accepted。新report首轮item21 exit3/10处trailing whitespace（嵌入diff空上下文）改零上下文后item24差异1/无输出，失败恢复已核；item16/17差异1无诊断。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 新报告嵌入diff的空上下文空白诊断已修正并独立复核
  - 差异exit1均无空白诊断，不冒称0
  - provider gpt-6-sol配置实际model为gpt-6.1-sol，当前任务与总控只读配置核对一致
evidence_gaps: []
retry_class: none
```

F4-PV01报告修复最终状态已修复，接受新任务证据；原task mismatch rejected作为历史不撤销。此处只闭合报告准确性，不是F4产品或plan gatepass。新报告风险表的“later approved slice”不表示已有代码slice审批，总控归类为本WU后续计划审查/实施的必要义务，不能跳accepted plan gate。下一同版MiMo/Kimi Planreview。
