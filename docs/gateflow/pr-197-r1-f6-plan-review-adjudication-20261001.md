# PR197-R1/F6：同版计划审查裁决（阻塞修订已登记）

## Gate、输入与范围

唯一工作树 `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`。本次审查输入计划 `pr-197-r1-f6-plan-20261001.md` SHA256=`c59787460262b7706f6d5312da61d693474d02403b493e2484ad2c053cd6e566`，冻结 `workspace/tmp/pr197-f6-plan-review-20261001/freeze.json`。root 首末独立核算 **55 current + 55 originals 全部匹配**，结果逐件保存在 `workspace/tmp/pr197-controller-collection-20261001/f6-plan-review-end-identities.json`。当前基准8000f54b；非冻结文档 checkpoint 不冒称 owner 源码变化。main fac32ecbff 未改。

本轮仅 plan review，产品尚未实施。F6-PV01 已修复，F6-P1 仍是已批准 F6-S1 必要修复；job 不增加 schema，现有上传行为裁决不重开。旧 CLI Raw 用户确认删除，最终完整真实 CI 与正式 registry/readiness 收口义务不变。

**当前 gate 不通过**：以下两个 accepted finding 均未修复；另一路独立审查还在途。后续为 Sol 窄计划 fix → 同版双路 re-review → accepted plan commit → implementation；不可跳过或把本裁决当 accepted plan。

## F6-PR1-A1：中 / accepted / 未修复

Owner：SEC workflow 的结果构造、取消状态及完成日志产生层。Destination：本 F6 计划 D2/D3/E1 最小修订；不另设业务 WU。

当前 D2 的共享 `_build_sec_download_result` 无 status/cancelled 参数，要求正常完成和 typed abort 共用且默认 status='ok'；同时要求既有取消结果不变。root 实读 `sec_download_workflow.py:607-630,670-705,718-766`：三处真实取消分支会进入末尾结果构造，其 status 是 `"cancelled" if cancelled else "ok"`。计划接口不足以表达原取消事实，实施者必须另行设计或复制计数构造。抽取范围718–759还包含734–742完成日志，未明确日志只在正常调用方产生；字面整段抽入 helper 会使 abort 打出“美股下载完成”。这是可实施性缺口，不宣称未实现源码已经出现该回归。

最小修订：共享构造显式接收有类型的 status 或 cancelled 参数，正常路径保留原 cancelled/ok 值，abort 快照仍保留已决定的私有 ok、由异常承担操作失败；完成日志留在正常调用方，共享 builder 不产生完成日志，不造 PIPELINE_COMPLETED。明确取消保留断言与 abort 无完成日志验证，原早期取消 helper 保持。

MiMo 引用 `test_download_stream_repair_gate_rechecks_cancel_before_company_batch` 的 cancelled 断言确实存在（943–985），但其报告所述“首 repair filing 成功后取消”不是该测试的实际设置：该测试使用新的 tmp_path，未种入损坏 source。root **不采纳这段具体场景描述**，保留该原断言并要求计划验证真实 postrepair cancel 分支；不据测试名称冒称覆盖了成功 repair 后取消。finding 本身由上述生产分支与接口矛盾成立，不依赖这段错误描述。

修复风险低；属于原 goal 保持取消语义和唯一结果真源，不扩大验收规则，不迁移断言迎合错误状态。

## F6-PR1-A2：低 / accepted / 未修复

Owner：CN/HK workflow 的 postrepair typed 中止边界。Destination：本 F6 计划 D1 显式化；不改源/test 或独立业务规则。

root 实读 `cn_download_workflow.py:404-427`：SelectedSourceRepairRequired 的旧 raise 位于 try 内，紧接 except 只捕获 Preflight/RevisionConflict 两类型，再包装 `_integrity_abort`。计划当前 D1 要更换 raise 和扩展 wrapper cause union，却未明确该 postrepair except 同步扩展。若只按这两项改，新 RepairRequired 裸穿，不进入 CnDownloadIntegrityAbort；既有 adapter 不取得确认前缀，runtime 只能用请求级空摘要，违反 G3。SEC D3.4 已明确三类型 catch，CN 也须直接写出。

最小修订：postrepair classifier 与新 RepairRequired 抛点置于同一三类型封闭 catch，原 typed cause 对象与链经 `_integrity_abort` 保留确认行；维持既有真实 Fs 第二来源损坏 → production adapter 摘要守恒验证。mid-filing 只有真实可达的两类型 catch，不为不存在的抛点造 fake 分支。

修复风险低。属于已批准 typed 原因与确认摘要守恒，不改 job schema、修复预算或发布规则。

## MiMo：生命周期、证据与 root 裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - stderr 精确 unrecognized_model 前缀，非致命 metadata 诊断
  - Claude 汇总 JSON 不提供逐调用轨迹，不能认证所有中间步骤均成功
  - 报告的具体 repair-cancel 测试设置错误，root 已驳回并由真实分支独立证实计划缺口
evidence_gaps: []
retry_class: none
```

runtime=claude，provider=mimo，actual model=`mimo-v2.6-pro[1m]` 来自 JSON modelUsage，与自报一致；label=`pr197-f6-plan-review-mimo-20261001-01`。托管 write_stdin 25143 明确 outer exit0；完整 JSON 合法、subtype=success/is_error=false/terminal_reason=completed/69turns、permission_denials=[]。root 完整读取 JSON、stderr及正式报告，canary 在 result/report 与 expected 逐字匹配。

原件目录 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.3fOqFC`，独立 `pr197-f6-plan-review-mimo-20261001-01.json/.stderr`。正式报告 `docs/reviews/plan-review-20261001-113609.md`，SHA256=`59c1361b65c747d2a05c21a7153fe9a89296d1aa5b7b534e830984e6ecfaf601`。

root 实读当前计划前缀全部 B–E/F、真实 SEC 末尾构造/adapter 严格投影/runtime direct failure路径、CN postrepair catch及 cited cancel 测试设置；结合现存 owner 取证和修复 receipt，关键冻结身份与两 finding 独立成立。没有自跑新产品测试/pyright/coverage，不将计划审查写成产品验收。报告意见可采纳不等于门禁通过。

报告声明的中间复合 shell `echo ====` zsh glob 非零及 grep 无匹配无法从汇总 JSON 逐事件认证；已明确限制。其相关定位由 root 直接读真实文件恢复，无关键证据缺口。root 自己误猜 `sec_filing_collection_workflow.py` 导致 rg exit2，随后通过 sec_pipeline imports 与 rg --files 找到真实 `sec_filing_collection.py` / `sec_sc13_filtering.py`，读取实际调用；不会用错误路径扫描作结论。root 冻结核算最初误把 originals 字符串当映射导致 AttributeError/exit1；改按 freeze 实际目录与55相对路径逐项核算，110件全匹配。

## Kimi：真实额度失败，拒收结果并授权 ds-flash 备份

```yaml
setup_status: ok
agent_status: failed
tool_evidence: unknown
tool_trace: summary_only
required_evidence: missing
canary_status: unknown
result_status: rejected
warnings:
  - stderr 精确 unrecognized_model 前缀不是额度失败的豁免
evidence_gaps:
  - API 403 五小时额度耗尽，缺最终审查和可核对 canary
retry_class: provider
```

runtime=claude，provider=kimi，JSON modelUsage=`kimi-k3[1m]`；label=`pr197-f6-plan-review-kimi-20261001-01`。托管49742明确 outer exit1；完整 JSON 虽 subtype=success，实际 is_error=true/terminal_reason=api_error/api_error_status=403，result 明确五小时 usage limit，81turns 不证明审查完成。没有正式 report 或专属临时取证文件。root 未把 num_turns 或失败输出当 tool/通过证据。

原件目录 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.Ju3DqN`，独立 JSON/stderr均保留，不覆盖。切换是用户此前具体授权“Kimi额度不足用ds-flash备份”，不改变 Sol 实现路由。

## ds-flash 派发与自动审核恢复

- -01：预检通过，新目录 `sub-agents.Qhikvo`；functions.exec cell843 的 exec_command CreateProcess Rejected：automatic permission approval review deadline超时。Agent未启动，无 provider attempt、无 outer process exit。
- -02：工具明确允许的一次重试，新目录 `sub-agents.WfKNxB`；cell845同样自动审核deadline超时，Agent未启动，旧输出不覆盖。自动拒绝理由是审核未在deadline内完成，不证明该只读行动有不安全事实；不能绕过审核或在沙箱内假装派发符合skill。
- 用户明确答复“授权再尝试一次 ds-flash”后 -03：新目录 `sub-agents.q0qAlg`、新独立 output/stderr/instance，显式绝对cwd，require_escalated/no-persist/canary；预检和110冻结身份通过，托管43581成功启动，**当前在途，无终态裁决**。前两次不是模型失败/已运行审查。
- 用户最新另授权 `$sub-agents` 所有 runtime/provider 的派发；详 `pr-197-runner-runtime-provider-authorization-20261001.md`。不据此改写先前保留 Sol 等恢复的具体选择，也不跳过自动审核。

## OQ、residual 与下一入口

1. operation reason 与 document reason_category 的层级：同一恢复事实各有正确 owner；README 仅按其现成职责说明必要恢复动作，不把行“未完成”分类当全操作原因，不新增 prompt/字段。covered by current approved F6-S1 的既定 docs/投影验证。
2. abort warnings 只保留已经确认列表，不在异常后补正常循环尾的缺失申报扫描。沿 G3 真源与原事件前缀，无新的 warnings承诺；rejected-with-reason，作为本次阻塞不成立。
3. 早期 `_cancelled_pipeline_completed_event` 潜在计数差异仅有空行调用点，不在本 F6 统一；SEC workflow owner，requiring new issue or explicit user decision，不自动纳入本轮必修。
4. 两份既有 rejected helper 的统一属 SEC 结果协议 owner 后续 goal候选，本轮复用现成逻辑、不第三次复制。requiring new issue or explicit user decision，不顺带扩大已完成 F7。
5. 完整 reason durable、publication indeterminate、其它WU保持已有 owner/destination与非目标。F5 Q1仍待用户，不能从最新派发授权代选。
6. Sol 两轮 routing discovery超时已登记，用户要求保留Sol等待恢复。root只读未认证transport诊断在默认环境和runner同外侧环境均DNS超时；外侧curl28/http000不是模型quota或认证路由恢复证据。独立 `workspace/tmp/pr197-controller-collection-20261001/sol-transport-readonly-outside-health.json` 保留outer28，不用wrapper0冒绿。两个计划finding的Solfix当前受同一服务阻塞，不让root/MiMo/DS代写。

下一入口：收取43581全结构化/报告/首末身份并独立裁决新增意见；Sol服务实际恢复后最小修订 A1/A2、同版双路复审。必须保留此次失败/反例和原冻结版本。仍未 accepted plan、未产品实现、未最终PR review/closeout、未最终真实CLI CI。
