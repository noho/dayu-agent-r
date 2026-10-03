# PR197 Sol 路由恢复：固定一次只读实测核收

背景：原F3两个修复派发均workspace routing discovery timeout/turn.failed，无工具或source写入；用户具体选择保留gpt-6-sol等待恢复。root外侧未认证transport从DNS timeout变化为HTTP451，该外部状态变化既不能证明模型恢复，也不能代替正常认证路由测量。故本轮固定一个只读测量，不是原修复批次的第三次盲重试，不抹去原失败、不计成修复通过。

label=`pr197-sol-routing-health-20261001-01`，runtime=codex，provider=gpt-6-sol，actual model=unknown（完整流没有可靠model metadata）。显式workspace `/Users/leo/workspace/dayu-agent-r`，预检ok，require_escalated/no-persist，新独立output/stderr/last与canary。托管39776明确outer exit0。

root完整读取7条合法JSONL、stderr和last：thread.started/turn.started；item_1真实command_execution执行一次cat本轮校验文件，exit0/完整原始输出与expected逐字匹配；item_2/last中canary均匹配；turn.completed。无error/failed/nonzero事件，stderr为空，无源码或plan写入，无子Agent。没有以agent自报、匿名curl0或耗时推断成功。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: []
evidence_gaps: []
retry_class: none
```

原件目录 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.9Aye0A`，独立 `pr197-sol-routing-health-20261001-01.jsonl/.stderr/.last.md`；任务正文 `workspace/tmp/pr197-sol-routing-health-20261001-01.md`。三个原旧服务故障/transport证据不删除、不覆写。

**结论：当前正常runner认证路由已能完成真实工具读取，可恢复用户指定Sol工作。** 不承诺未来持续可用、不宣称原F3/F6已修、不替代任何code/plan gate。root已核对五个F3候选SHA保持原值、F6冻结110身份未漂移。下一入口：新唯一标识/新冻结和独立输出派F3现成输入合同窄fix；F6四项必要计划窄fix仅写计划，与F3五utils互不重叠。仍由root核收和同版双审，所有开发只在原分支、PR197，main不变。
