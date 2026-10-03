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

## ds-flash 终态核收与最终有效裁决（取代在途状态）

托管43581已明确 outer exit0。root 完整读取独立 JSON/stderr/report；合法 JSON、subtype=success/is_error=false/terminal_reason=completed/97turns、permission_denials=[]、subagent_stats.spawned=0。actual model=`deepseek-flash[1m]` 来自 modelUsage，与正式报告自报一致。stderr只有精确 `[claude-code:unrecognized_model]` warning。正式报告 `docs/reviews/plan-review-20261001-115109.md` SHA256=`7d2bd89140c114e34a94d2fd80726fa6594149ec01a1132833da2ff648df89e0`；报告 canary 与 expected 逐字匹配。最终 JSON 的短 result 未带 runtime/canary前缀，正式 report 包含两者，root 已直接核对，不假称 result 也含 token。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: partial
canary_status: match
result_status: partial
warnings:
  - 精确 unrecognized_model metadata warning
  - JSON result 缺固定开头，但正式报告自报及 canary 已核对
  - 两条取消测试都经统一尾部的泛化不成立，早期取消有独立 helper
evidence_gaps:
  - 作者 freeze 脚本只有合并核对 log，无独立 stderr/命令退出 ledger，未认证全部中间命令
retry_class: task
```

接受其下列源码/测试 finding 证据，**不接受完整交付或 pass-with-risks 放行结论**。作者宣称 F1/F2 实施前必须关闭，按 Gateflow 这就是当前 gate 未通过；标签不能消除阻塞。root再次核算110 current/original匹配，自读 verifier 与完整4725字节日志（尾部各55/0/0）。脚本即使 mismatch 也默认exit0，因此不得单独靠exit0宣称身份成立；root逐件实际SHA完成独立补核。脚本无独立双流/exit ledger、main docstring不完整，记录交付限制，不修改原件，不把脚本冒称产品type验证；下一复审须遵守当前取证协议。

### ds Finding01 → F6-PR1-A1：accepted / 未修复（合并，不重复计数）

与 MiMo 的取消/status缺口同根同owner。root不采纳“1012测试也经统一尾部”的描述：它明确是收集早期取消，生产443/543的独立 `_cancelled_pipeline_completed_event` 已由原计划保留。旧两个取消断言都保留，同时必须实测 helper涉及的循环尾取消路径；不能把只测早期helper当共享builder取消覆盖。A1完成日志归属缺口维持先前裁决。

### F6-PR1-A3：中 / accepted / 未修复（ds Finding02）

Owner：SEC workflow typed 中止边界及其 owner 级测试迁移；destination 本F6 D3/E最小计划fix。root 实读 single-filing 238/275/383/505四真实抛点，分别是 Phase A UNSAFE、repair target已拒、6-K政策拒绝repair target、Phase B UNSAFE；都在已声明pair catch内、无当前terminal。实读 `tests/fins/test_sec_pipeline_download.py:6148-6205` 真实损坏source与6-K NO_MATCH旧节点，当前断言裸Preflight异常及所有旧facts零mutation。

**计划的中止行为已经有明确决定**：D3.2/3的两类型catch + 当前无terminal则一条failed行/typed abort，没有按PreflightReason例外。维持这个已批准目标内的计划规则，不收窄为裸抛、不另问新业务选择；该行只表示已开始文档未完成，不把政策拒绝伪造为新rejected成功发布。初始整体preflight仍裸抛/空摘要，与单filing已经开始后的边界分开。

accepted缺口是抛点说明与旧测试迁移/覆盖未列清，而不是“尚无任何行语义决定”。D3须写出这四抛点均保原cause/reason、确认前缀、当前恰一failed行、后续零执行、零新发布。E补既有 `test_sec_selected_repair_that_6k_policy_rejects_fails_before_mutation` 迁移：assert typed abort→原PreflightCause/SELECTED_REJECTED、total=1/failed=1；原meta/payload/company/registry/rejected zero-mutation断言全部保留。补真实Phase B UNSAFE的确认前缀覆盖，仍在原10测试文件，不新正式文件/业务状态/修复预算。

### F6-PR1-A4：低 / accepted / 未修复（ds Finding03 的测试迁移部分）

Owner：CN workflow行原因合同及其owner测试，destination 本F6 E迁移清单。root实读 `test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing`（2893、2970–2992）：当前真实Phase B UNSAFE后有成功+failed两行、cause链、integrity_failed快照、failed事件恰一次与commit/rollback守恒，旧reason断言确为source_integrity_preflight。计划已有统一新reason决定，补列此node及新reason断言；其它守恒断言不能削弱。无需发明双常量或兼容旧值。

ds“内部abort文案中性化”不是新增阻塞：runtime 已解原 cause，由唯一 public mapping 承诺原因；该私有wrapper的旧内部文字没有在本次证据中形成另一公共/持久化原因。rejected-with-reason作为额外必须修项；Sol须在计划明确内部安全文字是否保留、避免实施者猜新公共文案，但不得为此新改日志/schema/prompt或新增业务规则。公共恢复文案仍按已批准C表，不从wrapper str推导。

### 服务、输入准备与最终状态

独立事项推进后再次只读未认证transport检查：外侧curl真实exit0/http451/stdout=`451 0.667112`。DNS从原timeout变为可得到HTTP响应，但451仍不是认证路由或模型服务恢复证明，不将transport exit0当Sol可用。新证据 `workspace/tmp/pr197-controller-collection-20261001/sol-transport-readonly-followup-health.json`；旧两次DNS超时和Sol两次14事件turn.failed原件保留。

31正式UM裁决的SHA/引用追溯索引与当前7个parser/准入函数只读span已准备：`final-ci-adjudication-index.json`、`final-ci-parser-readonly-preparation.json`（同controller collection目录）。这不是最终inventory冻结、mandatory矩阵、registry登记或CI通过；待所有已批准修复完成后仍须在最终commit重建全矩阵、重新采集真实输入、完整新真实CLI执行与readiness。旧Raw用户已删除，不补造历史执行。

**两路已全部终态收齐，当前无活动审查/sourcewriter。F6 plan gate fail，A1/A2/A3/A4 accepted且未修，F6产品尚未实施。下一入口是gpt-6-sol服务实际恢复后的窄计划fix，再同版MiMo/Kimi（quota时DS）复审。** 用户要求保留Sol等待恢复，root不自行切实现模型或代写。F5混合财期Q1仍待具体裁决，最新runtime/provider派发授权不等于其业务选择；最终PRreview/closeout及完整真实CLI CI未完成。

## 正常Sol路由恢复后的下一入口（最新）

固定一次只读认证runner39776已outer0/实际cat0/canary/turn.completed，root完整核收，详 `pr-197-sol-routing-recovery-receipt-20261001.md`。允许恢复原Sol工作，不凭HTTP451判路由，也不自切模型。当前四accepted计划finding仍未修；下一Sol只写当前计划前缀/新报告/独占tmp，保历史tail与所有源码/原件，之后同版双审。F3同时只写五utils，两任务写入范围不重叠，root控制唯一产品sourcewriter。
