# PR197 F6 SEC 计划探针类型证据裁决

## 当前结论

**F6-PV01：低 / accepted / 未修复。** 属于F6已交付计划的取证修复，不增加产品WU或业务oracle。SEC修订计划结构与三真实Fs旧路径证据保留；其“临时探针pyright通过”当前不可采纳，须Sol在新独占tmp目录保留原字节、修正确切日期参数类型、执行非空类型检查及必要三个探针，并用新报告/计划当前状态更正旧错误声明。source/测试/README/config全部不改。

## 进程、原件与实际证据

- Sol50829托管outer0，104行完整合法JSONL、turn.completed、stderr空；路由gpt-6-sol，实际model unknown。
- label `pr197-f6-plan-sec-fix-sol-20261001-01`；双流/last-message目录 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.sxqQ6h/`。
- 作者报告 `pr-197-r1-f6-plan-sec-amendment-20261001.md`，当前plan SHA `27e898b51f7273896e0a280e191e032f0fa83cefc90883b30eacc61e98b58d4a`；随机读取凭据匹配。root41原件/40当前只读身份全匹配，计划原全文完整保留为尾部，只有授权新增当前计划前缀。
- probe wrapper外层命令均0，但两次内层pytest实际1（首次装配错误、二次合成日期顺序错误）已经真实日志保存；恢复最终三个探针passed/3既有warning，stderr空。作者如实报告这些内层失败，不能拿外层0代替它们。

## F6-PV01直接证明

作者直接向默认项目pyright传workspace/tmp两个脚本，默认项目排除workspace。root激活venv用同一命令加outputjson：filesAnalyzed=0、errorCount=0；这是空检查，不是类型通过。

root用独立明确include的配置（两个文件、exclude=[]、既有项目规则、venv/extraPaths精确指向checkout）复核，filesAnalyzed=2、errorCount=2。均位于临时 `test_sec_owner_probe.py:184`：日期范围 `start_bound`/`end_bound` 要求 `date | None`，却传 `2024-01-01`/`2025-12-31` 字符串。不属于产品类型错误，也不能通过宽松签名、cast、ignore或删文件修掉。

正确方向是在临时request构造处使用真实date值，保持日期文本、所有探针断言、真实Fs/独立writer与原症状不变；新复制脚本改日志目录仅为独占输出，不修改原证据。显式新配置必须相对include、实际非空2文件；临时类型0与三个owner探针重跑通过后root再核收。不能把未来产品default full pyright义务改成临时检查。

root自身首次配置错误也保留：绝对include被pyright忽略，误扫描自身controller目录、命中F7预期negative类型探针；该结果不是F6问题。将include改为配置相对路径后得到上述真正两个F6错误。原错误配置另存 `workspace/tmp/pr197-controller-collection-20261001/f6-sec-plan-probe-invalid-absolute-include.json`；有效配置 `f6-sec-plan-probe-pyrightconfig.json`。未改仓库config、未抹除负例或安装依赖。

## 当前门禁与范围

本轮Sol计划交付部分采纳：source/原件身份与计划SEC owner补齐可用于下一设计判断，完整required_evidence尚有类型缺口，不能accepted全部证据。当前固定裁决块：

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: partial
canary_status: match
result_status: partial
warnings: [两次内部pytest失败已恢复, 默认项目workspace排除导致空类型检查, root绝对include配置失败已恢复]
evidence_gaps: [两个临时脚本非空pyright仍有2错误]
retry_class: none
```

这是新的窄修复任务，不是provider重试，不抹除旧测量或旧终态。完成后同版MiMo/Kimi planreview及必要修订，accepted plan commit后才产品implementation。F3/F4审查和最终真实CLI CI/registry目标按现成用户裁决继续。
