# PR197 F6 计划交付核收与 SEC 同根因裁决

## 总控当前结论

接受 Sol 计划交付证据，不接受整体实现计划。作者提出的 F6-P1/OQ-1 已由root直接复核，**accepted / 未修复**；纳入本F6必要修正，先由Sol补齐计划，再MiMo/Kimi同版Planreview。不新增业务规则、durable schema或独立产品goal，也不进入implementation。

唯一workspace `/Users/leo/workspace/dayu-agent-r`，唯一分支 `codex/upload-material-oracle`。计划输入checkpoint fe47438c；期间F4已接受slice普通提交/推送75fec034，local/tracking/PR head及远端实读均 `75fec034d8993f300c2f2e2c8b9c574e243f8538`，main仍 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。29相关输入字节完全未改，checkpoint变化不是source drift。

## 生命周期和独立核收

- Codex/gpt-6-sol，label `pr197-f6-plan-sol-20261001-01`，实际模型unknown。托管44460外层0，66行完整JSONL合法且turn.completed，无turn失败，stderr空。
- stdout/last-message/stderr：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.wa7ZFB/`，各文件以label命名。
- artifact `docs/gateflow/pr-197-r1-f6-plan-20261001.md`。root读取计划正文、真实goal、owner证据和SEC真实抛点/adapter；随机读取凭据匹配独立基准。
- 冻结29当前输入与29原件root实时SHA全匹配；四个真实Fs/合成字节owner探针实际exit0、4 passed/3既有edgar warnings、stderr空。仅证明旧缺陷路径，不是产品绿。
- 完整JSONL非零：12/item5误读不存在dayu/ui；29/item14测试文字rg无匹配打断后读；33/item16猜测sec_download_adapter.py不存在；42/item21猜测cn_download_summary.py不存在。恢复读真实SEC adapter、CN summary、实际config/测试位置，命令ledger与后续exit0证明恢复。计划如实登记，root不把猜测路径作依据。没有重派。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [探索读取错误路径已恢复, 无匹配打断后续读取已恢复, 已知旧探针非产品验收]
evidence_gaps: []
retry_class: none
```

## F6-P1/OQ-1：root裁决

root直接证据：`dayu/fins/pipelines/sec_download_workflow.py:681-688` 的真实 postrepair 分类为 SelectedSourceRepairRequired，却抛 SourceIntegrityRevisionConflictError；`sec_download_filing_workflow.py` 真正identity churn也抛同类。`sec_pipeline.py:1750-1794` 收集事件时没有typed部分摘要包装，异常直接逃离collector，已处理结果没有进入adapter公共失败摘要。

本F6明确目标是区别真实版本变化与来源仍待修复，公共mapping由runtime统一产生，适用于所有下载source。只修CN再全局增加“等待并发写入”提示会让SEC已存在的错误事实获得错误公开承诺。以source特判不同提示、保持错误SEC分支并泛称延期，都不符合unique owner。

因此选择作者推荐的最小必要路径：在同一F6行为slice补SEC产生层typed cause、中止快照与adapter保全；SEC复用自身结果构造、已拒绝行与严格summary契约，不套CN结果字典，不新造状态、reason或job字段。加入SEC真实source/tests同一冻结后修订计划，双路审查挑战完整性和范围。

这属于已经批准修复“版本churn/仍需repair语义”的必要owner修正，未提出新的用户业务取舍，无需重复索取执行许可。具体SEC设计仍待Sol及Planreview核证，不能把本条裁决当accepted implementation plan。

## 保留边界与下一入口

- durable job仍只存同源safe_message和已确认summary；结构化reason/hint持久化保持原独立待goal，不能在F6顺带新增schema。
- RepairBlockedError在下载没有真实专用repair调用路径：不因注入fake exception扩scope，upload已拥有现成处理。
- storage publication indeterminate等原独立残余不变；逐文档manifest成功、公司独立发布、取消/repair基本流程不改。
- F6-P1立即登记主队列/交接；Sol只修计划并补必要最小owner证据，源码只读。root核收修订版后MiMo/Kimi同时Planreview。F3同版双路代码review继续，F4aggregate等待并发槽位。

root操作恢复记录：F4首次误用不存在remote名origin，push outer128无远端写入；实读remote为github后正常push0，并独立readback证实local/tracking/live/PR一致。未force、未改main、未丢候选文件。
