# 下载失败诊断：双路 plan review 总控裁决

- Work unit：download-failure-diagnostics-20261010
- Gate：plan review 已取得两路证据；未通过。下一未完成 gate：fix。
- Scope：冻结 plan SHA256 e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca；HEAD/base c65c2aa28fae9c47ad947783d63f7559db7768c4。
- Inputs：docs/reviews/download-failure-diagnostics-plan-mimo-20261010.md（SHA256 f27be4582bb88a74ee4f5cf2375abc17a5bf6494d5f17b74909cb0fac311770e）；同目录 plan-dsflash（SHA256 27a1c120c6d5b987fdbaabb68d182a65661ad1e0628d0233b783fed5b98c0fd8）。
- Docs decision：修订 plan 并澄清 goal 的已确认范围；此 gate 不改生产代码、tests 或 README。

## 派发验收

### mimo：dfdiag-plan-review-mimo-20261010-01

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [item_18与item_19模型元数据Node探针kernel失败，未恢复此可选探针；不影响plan代码取证，不把模型自报当路由证据, final未重复CANARY，已从独立review报告首部逐字核验本轮token]
evidence_gaps: []
retry_class: none
```

runtime/provider：codex/mimo；runner 使用 mimo_codex，所选模型卡配置 mimo-v2.6-pro。自报亦为该模型；event stream 没有权威 model 字段，物理后端型号不另作未经证明的保证。独立 exec_command require_escalated、no-persist、显式 cwd。托管 session 74255 的 write_stdin 最终 exit 0；217 条合法 JSONL、turn.completed、102 次 completed command_execution。两次 mcp_tool_call 的 node_repl.requestMeta kernel 失败为 item_18/19：只为可选模型元数据查询，关键代码证据均由成功 shell 工具取得，未用失败探针建立结论；不重派抹去失败。stderr 空。完整输出 SHA256 458eecd003099866fe6257f48afe025c5605b1be6fcf6ecd8a152908d8ae122b。

run_dir：/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.bawV9g；同目录保存 JSONL、stderr、last.md、canary.expected 与 controller-audit.json。报告首部 CANARY 与本轮 expected 逐字匹配，且有本轮 cat canary 工具执行；最终摘要没有重复该字段，不把摘要遗漏伪称 token mismatch。初始只查 final 的辅助脚本返回 false，改按任务实际报告 artifact 核验后匹配；没有改 token 或放宽逐字规则。

### ds-flash：dfdiag-plan-review-dsflash-20261010-01

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [一次apply_patch无效hunk错误随后由成功artifact写入恢复, final未重复CANARY，报告首部逐字匹配, 自报model为gpt-6.1-sol而所选模型卡为deepseek-flash，不采用该自报作身份依据]
evidence_gaps: []
retry_class: none
```

runtime/provider：codex/ds-flash，用户 ds_flash 已规范化为 runner ds-flash。runner/launcher/所选卡已独立检查：ds-flash_codex → exec -p ds-flash；native帮助明确 -p 加载对应 .config.toml；卡 model=deepseek-flash、model_provider=deepseek。event stream 没有权威 model 字段，不将错误自报 gpt-6.1-sol 当作真实模型身份证据，也不以自报推断路由已切换。没有 provider switch。

托管 session 46483 的 write_stdin 最终 exit 0；256 条合法 JSONL、turn.completed、116 次 completed command_execution。stderr 的 apply_patch verification failed（invalid hunk）未在 JSONL 提供失败 item；随后 file_change item_130 completed，报告完整、hash 已核验，必要 artifact 写入恢复；该错误不影响已独立复核的代码结论。完整输出 SHA256 268c77e73a874e1afffab2a5cdb70bc8aadbb2a0b4b1c61ea88086e88eb62e02。

run_dir：/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.NqRdnw；同目录 JSONL/stderr/last.md/expected/controller-audit。报告首部 CANARY 与本轮 expected 逐字相等，有真实文件读取工具执行；final 字段遗漏按实际 report 核验，同 mimo，不是实际 mismatch。

ds-flash 的 offline 空库 rebuild probe 使用 /private/tmp 下隔离 base，无生产来源查询；item_122 输出 EXIT=0 及空计数，与代码 local-only return 分支相符。总控将其作为装配前提证据，不作为修复后验收、远端下载或 fresh 数据版本保证；最终固定入口还需实施后的独立验证。

## 总控独立复核与 findings 裁决

复核原 plan 全文、goal 已确认请求范围、sec_pipeline:1933-1973/2092-2114 的通用文案、sec_download_filing_workflow 的 upstream reason；cn_pipeline 的对应投影；runtime activate_observation:4005、_mark_observation_failed:7486、_observation_failure_result；direct_events 的失败/download 组合；原 stdout hash、owner-read JSON、固定 CLI shebang/实际 import/模型卡选择代码。不能用两路一致代替这些直接复核。

| ID | 对应 review finding / question | Decision | 最终状态 / 修订要求 |
|---|---|---|---|
| P1 | mimo-01 / ds-01：SEC保真声明不实 | accepted（计划声明/验证不一致）；严重程度中 | 未修复。删除“SEC现有adapter原因保真”及跨来源原因修复承诺；通用完整接口保留既有typed rows，SEC测试只验证完整性/身份/既有投影不变；CN/HK真实安全原因保真仍必达。不得修改SEC生产代码。 |
| P1扩范围要求 | mimo将其解释为必须跨来源修复SEC | rejected-with-reason | 巡检线已明确目标限定于给定0700请求与最小修复；现有SEC同类问题可记录后续风险，不是本轮已确认验收义务。不需重复请求同一目标确认。 |
| P2 | mimo-02 / ds OQ2：download_result=None / activation failure 操作归属含糊 | accepted；严重程度中 | 未修复。写死合法download终态一律由拥有request的runtime提供typed result；None只用于无下载结果的非download合法结果，diagnostic方法对无download_result抛ValueError；不新增operation字段、wrapper或下游空结果fallback。_mark_observation_failed必须显式覆盖request-scoped typed空FAILED结果和whole failure，可复用已有_observation_failure_result owner；测试executor submit失败、prepare取消、adapter启动前失败及非下载拒绝。 |
| P3 | ds OQ1、两路旧meta核查表述 | accepted（事实更新） | 未修复。引用已完成owner-read JSON与总控授权/结果；删除再次等待同一现有证据核查确认或重复生产查询步骤；治理锁影响如实说明，未执行任何新来源观测。 |
| P4 | ds OQ3/OQ4/OQ5：negative operation tests、mismatch错误分类、CLI前缀 | accepted（规格具体化） | 未修复。显式负例：DOWNLOAD RESULT缺typed result/非DOWNLOAD携带均拒绝；period_metadata_mismatch是FAILED不是SKIPPED；唯一诊断行指按固定前缀筛选后的唯一行，不是stdout只有一行。 |

P1修复的是不实声明，并非延期本轮需求；现有SEC投影问题不改，owner=Dayu维护侧，destination=后续SEC原因owner work unit（需另定范围，不自行创建issue）。P2在既有runtime文件与当前终态contract内明确，不是新增目标；不得借此改executor生命周期或治理状态机。

## Residual risks（统一合法分类）

- 当前诊断缺口、full/bounded一致性、取消/失败前缀、负例及CLI转义：fixed in current slice，尚未实现/验证，不声称已修复。
- 原8项原异常/日期/URL：requiring explicit user decision；巡检线已授权如实未知。现有证据核查已完成，未来新观测由巡检线另确认，当前不等待新观测。
- 现有SEC原因泛化/unsafe upstream例子：assigned to later work unit，Dayu维护侧；不在当前0700原因保真修复内，不能直接passthrough原异常。
- 未捕获标准流、SIGKILL/崩溃/提前关闭后的历史恢复：requiring new issue or explicit user decision；本轮只承诺合法consumed RESULT，无历史仓储承诺。
- 极端结果规模性能与完整repr可能的日志扩大：assigned to later work unit（如真实扩展压力出现）；当前S1仍验证LLM/durable不含完整数组，不能增加分页/框架或无证据优化。
- 类型检查、单文件coverage、固定入口离线加载：fixed in current slice（实施验证项）；基线pyright零错误，任何验证失败须如实裁决，不靠skip/ignore伪造pass。
- 新观测、实际下载缺陷扩范围、merge等：requiring explicit user decision，巡检线/用户。

## 下一步

派发 gpt-6-sol 只修 plan 与 plan-fix artifact，交接当前所有dirty文件为本unit、总控/reviewer归属已知；原plan Agent ownership blocked 不再成立。然后两路独立 re-review，逐项确认P1-P4为已修复后才创建 accepted plan commit。未进入implementation，无生产修改，无新观测，无PR。
