# PR197-R1/F7 同版双路 Planreview 总控裁决

## 审查版本与任务终态

candidate SHA4473d2a5e0de4b4cdbd1d8151e1fc9c6d068ff8f320384e9e945887a0d27abcf；21输入与workspace/tmp/pr197-f7-planreview-freeze-20260930.json均匹配，首尾HEAD60307c15、branch codex/upload-material-oracle。两个runner显式cwd主树、独立output/stderr、同时审同版，均不改源码。

| 路线 | 唯一label / 外层退出证据 | 结构化终态 / artifact |
| --- | --- | --- |
| claude/mimo | pr197-f7-planreview-mimo-20260930-01，托管55123 exit0 | JSONsuccess/is_error false/54turns；docs/reviews/plan-review-20260930-230120.md，SHA25b8827ebb64d7fe76c4611167cc9e9410692caee76138f3483240e85c94cf6c |
| claude/kimi | pr197-f7-planreview-kimi-20260930-01，托管88992 exit0 | JSONsuccess/is_error false/56turns；docs/reviews/plan-review-20260930-230304.md，SHA018c3f1acc1d6ade0395113687eda5c7b14738b07cf5d43e0612119d5c30161c |

两路result与artifact中的校验token均与各自实际基准逐字一致。Kimi最后消息将CANARY标签加粗，token内容完整，artifact也有标准纯文本行；总控初次朴素substring判false后抽取token核对确认match，不能把标签格式误作内容错配。此与F4-PV01真实少末位是不同事实。

两路stderr均只有精确`[claude-code:unrecognized_model]`诊断，按skill记录warning，不判派发失败；实际JSON modelUsage与自报分别为mimo-v2.6-pro[1m]/kimi-k3[1m]。没有配额失败，不启用ds-flash备份。

## 总控独立必需证据

不是按两票放行。总控实读goal/候选及两完整报告，已核真实三producer写入、所有_build_result调用、rebuild/HK返回、adapter两入口子集与_required_cn_text strip、原早期异常位置；六核心source输入与扩展21相关身份独立核对不变。严格类型正例实际1文件0错、负例1文件恰两项参数拒绝已在F7-controller-evidence中独立复核；只证明候选写法，不冒称产品门禁。

ClaudeJSON仅汇总，无逐工具trace；不据54/56turns或匹配标记声称全部中间工具成功。两报告额外coverage可行性结论由总控激活venv独立执行同六模块补取证：托管25859外层exit0，**679passed/3warnings（第三方edgar弃用提示）**，12.12秒；四文件真实JSON百分比models96.9388/rebuild85.5556/workflow94.4030/pipeline93.7768，全超过80。独立日志/coverage均在workspace/tmp/pr197-f7-controller-validation-20260930/，没有覆盖reviewer证据或根coverage文件。仍是未实施F7时的baseline，后续真实改动必须重新验证。

MiMo自报首次测量包含尚不存在的新测试文件，file-not-found/0tests，改实际六模块后679成功；Kimi自报zsh组合命令解析失败，拆条恢复。汇总可见性下这些中间事件不能逐条核查，相关关键结论已总控独立恢复，不把自报当事件轨迹。预期负例exit1/no-index差异exit1不是产品验证失败。

## Findings合并与gate

- **F7-PV01 accepted／未修复／低**：两路均确认候选收尾no-index子命令实际差异exit1、无空白错误，被组合末项0掩盖；MiMo列唯一finding，Kimi以既登记项引用，合并为一个。必须由Sol仅修事实记录，再MiMo/Kimi同版窄复审核真实新SHA与最小diff，不重评业务规则或增加产品目标。
- 无新增技术finding、无阻塞业务openquestion。Literal+Final同models owner、normal子集tuple、三个既有终态/全部producer/入口拒绝/strip/异常identity保全方案有直接证据支持，严重性仍低。
- 计划技术结论pass-with-risks，但**plan review gate fail／待PV01修复复审**；accepted finding尚未已修复，不能先提交accepted plan或实施。

## 子任务裁决

以下块分别适用于两label；报告结论可采纳，不代表gatepass：

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - Claude汇总无逐工具trace，必要源码/身份/类型/coverage由总控独立补取证
  - 精确unrecognized_model诊断按skill为warning
  - 作者自报测量setup失败已恢复，不能凭JSONsuccess断言全部工具成功
evidence_gaps: []
retry_class: none
```

## 风险分类与下一入口

| 风险 | 分类 / owner / 目的地 |
| --- | --- |
| PV01事实修订及复审核新SHA | fixed in current slice；Sol planfix/MiMo-Kimi窄复审/总控 |
| 实施后真实类型/测试/逐文件coverage | fixed in current slice；F7implementation owner；不能以baseline替代 |
| 共用workflow被F4/F5/F6改动使旧计划过期 | assigned to later work unit；总控串行源码排程、进入实施前重取证 |
| CN/HK空库取消不对称既有事实 | requiring new issue or explicit user decision；不属于本goal，不统一行为、不将其计新阻塞finding |
| 全仓/真实外网转换可用性 | assigned to later work unit；既有PR197完整验证/closeout；本slice受控验证不承诺provider质量 |

下一入口**Sol仅planfix PV01 → 同版MiMo/Kimi窄re-review → accepted plan commit → implementation**。当前F3 planamend与F4报告修复文档可并行，三个源码范围只读；F7业务始终以用户现成裁决为准。


## F7-PV01窄复审最终回写（20261001）

MiMo26981/XNPxri/28turns与Kimi64366/Q2Zmb2/47turns均outer0/JSONsuccess/token完整逐字match，报告002227/002251可采；根26SHA/原件/精确1行→4行/逆替换/结构/独立真实noindex再核通过。PV01已修复，plan review/re-review gate pass、plan accepted，新plan5820a492…；下一accepted plan commit→implementation。详细summary_only/恢复/残余和共用源码排程见docs/gateflow/pr-197-r1-f7-plan-rereview-adjudication-20261001.md。产品尚未实施，原679/cov只是旧baseline，不代新源码门禁；F4Sol36只读输入任务未终态前不改CN源码。
