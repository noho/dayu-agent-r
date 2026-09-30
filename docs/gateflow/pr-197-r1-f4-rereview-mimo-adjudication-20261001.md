# PR197 F4 同版复审 MiMo 返回与裁决

## 运行及证据验收

label pr197-f4-planrereview-mimo-20260930-01；runtime claude/provider mimo，JSONmodelUsage与自报model mimo-v2.6-pro[1m]。托管79430已outerexit0；G6DAKq独立JSON有效、subtype success/is_error false/65turns，result与report docs/reviews/plan-review-20260930-235229.md的token逐字匹配expected。stderr仅精确unrecognized_model warning。作者pass-with-risks不代总控gate。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 'Claude JSON仅汇总轨迹；总控关键源码/32SHA及保存输入/旧contract真实Fsprobe补核，不断言全部中间工具成功。'
  - 'stderr精确unrecognized_model诊断，非致命warning。'
  - '作者初probe用00001非canonical被owner拒绝，改600519后恢复；总控独立同contract复跑0。'
  - '总控首次originals检查错误地把已在原件根中的controller alias再嵌套，FileNotFoundError exit1、尚未写docs；改为31镜像原件+1独立alias，32SHA全匹配。'
evidence_gaps: []
retry_class: none
```

完整报告已实读，整文件一次截断后单独补读54～82行。总控32现场SHA及31镜像原件+独立controller-current字节alias全部MATCH，HEADb42/branch正确。源码identity/formID/workflow/start/stream与storageget/listguard已实读。独立workspace/tmp/pr197-f4-controller-rereview-20261001/probe_allocated_absent.py（作者脚本副本仅改临时根）激活venv真实空Fs执行exit0：返回fil_cn_3b0b304b9c63757ef09befa4dfd08bf8707c427e，与build_cn_filing_ids相同且不等于纠正ID。只证旧owner，非新API验收；未重复全量baseline。

## F4-PR2-A1／未修复／低：缺席 allocated 文档需显式规则

裁决accepted；owner身份分配计划契约，destination本F4 planfix→窄re-review。源MiMoF1标中，总控降为低：现生产源码正确，本项为代码生成计划文字缺口，不能宣称真实发生双ID或把未来风险当根因。

直接证据cn_download_identity.py的allocated_period_changed初值False，只有扫描到allocated[0]且任一财期不同才True；新plan §5步骤5只说period/year比较，mapping缺席规则未明示。文档不存在是正常首次下载，不得get默认(None,None)造changed。最小修复明示：键不存在→原allocated；只有真实键存在且任一财期直接比较不同才SHA1纠正；read_error仍先抛不能绕过。矩阵钉三态：不存在/存在同财期/存在异财期；存在meta缺字段按原None比较。只保全旧裁决，不新业务规则。状态accepted/未修复、分类fixed in current slice（待本WUplanfix）。Kimi44800仍在途，freeze不可改，双路收齐后才Sol修plan。

## MiMo F2／rejected-with-reason：未证实的空索引防护扩张

候选已要求真实消费集合传read helper：W0用selected，start/stream用(candidate,)，禁止过滤待处理HK。没有实际合法caller漏读证据。手工未读index再传HK违反明确前提，是未来误用，无当前风险证据支持新view_loaded字段。提议(b)拒绝空索引还会拒绝真实D=0首次下载；同形状值不能靠空值区分已读。故不采提案、不改报告原文；若以后出现实际误用证据再审。无新增accepted修复义务或业务确认。

## 范围、风险与下一入口

旧A1～A5越权方案已按新goal撤销。新API未实施，guard计数/竞态/事件/错误投影需代码后owner测试；当前非产品pass。F4-R01跨writer target-only保持requiring new issue or explicit user decision，F4-R02总扫描量assigned to later work unit；不顺带uniqueness/长锁/typed错误迁移。README无触发，仅review/治理。下一等待Kimi同版终态→合并裁决→Solplanfix→同版窄双审；main/newbranch/worktree/PR/comment无操作。
