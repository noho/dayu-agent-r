# F6-PV01 窄修复总控核收

**F6-PV01 已修复**，本次任务交付 accepted；F6 plan 仍 proposal，下一入口同版 MiMo/Kimi planreview，产品实现尚未开始。

runtime/provider/label：codex/gpt-6-sol/pr197-f6-probe-type-fix-sol-20261001-02，实际模型 unknown（事件没有模型元数据）。托管句柄31175 outer exit0，完整69条合法JSONL有一次turn.completed；stderr为空、last-message与正式报告齐备、随机读取凭据匹配。所有 command_execution 外层exit0，但 root 独立查了临时 runner 的真实内层exit，未以 wrapper0抹去 pyright-explicit-before exit1。

双流/last-message 在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.1hPDPT/`；前缀为唯一label。正式作者报告 `pr-197-r1-f6-probe-type-fix-20261001.md`；freeze/验证证据在 `workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/`。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - explicit-before inner pyright exit1 recovered by real date input
  - old default zero-file check retained and rejected as type-pass evidence
  - three existing edgar deprecation warnings
evidence_gaps: []
retry_class: none
```

root 已独立读取新旧两个脚本精确diff：probe仅新增date import并将两个既有ISO字符串转真实date参数；runner仅改输出目录。日期合同签名、断言、日期文本、排序、Fs writer场景保持。实际相对include两文件、exclude=[]配置与项目既有规则一致；before JSON=2files/2errors/exit1，after JSON=2files/0errors/0warnings/exit0，三SEC owner node真实3passed/3既有warning/exit0，各stderr为空。

root 重算45原件、44只读current均相符，额外275只读旧证据逐项复算无漂移；技术设计B–E与旧历史审计tail均字节相等。当前plan SHA=`c59787460262b7706f6d5312da61d693474d02403b493e2484ad2c053cd6e566`。最后root文档checkpoint0060be3e变化已由作者末检记录，未改相关源码。没有产品类型/coverage/真实CLI CI通过的结论。

此前controller setup失败-01未启动模型，由 `pr-197-f6-probe-dispatch-setup-recovery-20261001.md` 单独保留；-02不是provider失败重试。不改写旧SEC补计划报告的空绿声明，当前plan及新报告作为纠正入口。F6-P1及产品F6仍未修复，完整structured reason durable仍独立待goal，其它WU与Unicode/事务等不扩本任务。

总目标继续为已裁修复后真实CLI CI→upload_material oracle/scenarios/readiness，现有registry仅download/upload范围的ready不能证明本目标完成。
