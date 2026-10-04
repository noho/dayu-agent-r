# F3 plan amendment 最终双路核收与裁决

## 当前身份与范围

唯一 workspace `/Users/leo/workspace/dayu-agent-r`、branch `codex/upload-material-oracle`。HEAD `87dfbeae8625e34162812c06886610c37ba0f4e9`；main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 未改。当前 gate 为 plan re-review；仅最后两句 fix 与保全，不冒称再次全量设计审查。

## 两路终态与独立证据

MiMo11067、Kimi61008 托管真实 outer exit0，完整 JSON success/is_error=false/terminal_reason completed，分别25/29 turns。actual modelUsage 分别 mimo-v2.6-pro[1m]、kimi-k3[1m]。报告分别 `docs/reviews/plan-review-20261001-091041.md`、`docs/reviews/plan-review-20261001-090828.md`；实际 JSON 指向与报告声明一致，本轮各自 token 与 canary.txt/expected 字节匹配。独立 output/stderr 位于各自 run_dir jZE45w/hpJRtT，完整路径见报告。

root 实算16 current/16 originals/15 before-two originals，共47项匹配。当前 plan SHA `2983efa4326cc799565fab27a350d79bf74b40d540beb0143b4dfa90f181a421`；真旧原件 SHA `05729875b12bcf78a7518ed462b93cd582c056fb849321e38fed11e7fc09f126`。root 从实际差异两行重新计算唯一替换，正向全件等于当前、逆向全件等于原件；739行仅123/128变，737行逐字节保全。root 对读同一私有错误 owner 的123/128、136判据5与公共接口209–228，具名 ValueError 链原 OSError/ValueError、纯路径函数不虚构业务异常、main其余OSError原边界一致。完整报告 noindex check exit1且双流空。

Claude仅summary_only，不能断言所有中间工具零失败。MiMo预期helper搜索exit1表示源码仍未修，非证据缺失；两路noindex exit1无诊断为预期差异；Kimi一次BSD diff不支持--no-index exit2，改-U2实际差异及独立全件证明恢复；精确stderr model metadata warning非致命。根逐项必需证据补核，没有未解决缺口，不重跑既已接受22设计probe或业务裁决。

## 裁决与下一入口

F3-PR4-A1：**accepted / 已修复**。根将本轮窄证据与既已接受前轮合并：PR2-A1/C02计划主体、PR3-A1文字、PA01全量type义务均已修，完整 F3 plan amendment re-review **pass**。这不是多数表决；依据冻结原件、owner文本与真实caller。下一入口 **accepted plan commit → 同一F3-S1 source fix**。

C01固定摘要覆盖与C02跨记录目标别名两个产品finding仍 **accepted / 未修复**，不得将计划通过写成产品闭环。五utils真正fix在同一S1，无新S2；原非空完整harness、C01/C02新增矩阵、default full pyright PA01义务保持。原Unicode别名、预检后外部换链、跨运行缓存、历史locator和真实语料边界沿原plan分类owner/destination，未新扩goal。内部计划/裁决无README触发；测试/type本轮N/A。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - Claude只有汇总轨迹，root逐项必需证据补核
  - Kimi BSD diff语法失败已改-U2恢复
  - helper无匹配与noindex差异exit1均预期结果
  - 两路精确model metadata warning非致命
  - 合法19文件docs checkpoint改变HEAD但冻结16输入未变
evidence_gaps: []
retry_class: none
```
