RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-77432511

# PR197-R1/F6：A1–A4 已裁计划 finding 窄修复交付

时间取本机时钟：2026-10-01 12:14:21 CST。Label=`pr197-f6-plan-review-fix-sol-20261001-01`，design_doc=N/A，当前 gate=`fix`，原 plan review gate=`fail`。本报告交付计划文本修复，**待 root 核收及同版双路 re-review；不接受 plan，不实施产品，不推进后续 gate**。A1–A4 的最终修复状态须由 root 根据同版复审回写，作者不代裁门禁。

实际模型为 unknown：本轮可读 runner JSONL 的 thread.started 没有 model 元数据，stderr 当时为空；不从任务指定 provider/model label 或 canary 猜 actual model。仅尝试定位本轮 thread 的本地 session 文件未得到匹配，未据此切模型或声称认证失败。本轮 canary 是通过工具直接读取 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.vfHnDP/canary.txt` 所得，内容逐字如报告第二行；旧轮 token 不作为本轮证明。

## 1. 授权、身份与唯一裁决

- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；首末 branch 均 `codex/upload-material-oracle`。
- 首末 HEAD 均 `8328699a0f124c11c1e9db0e489e0337fe394f73`，main 均 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。没有 stage/commit/push/PR/merge/branch/worktree 操作。
- 唯一 freeze：`workspace/tmp/pr197-f6-plan-review-fix-sol-20261001-01/freeze.json`，首末 SHA256=`c937922289ce2bf23d94f4fd63b8d8fbb1ad9e432a6a09128e3b871935233e7f`。60 current + 60 originals，59 current readonly，allowed 仅 current plan；未修改 freeze/originals。
- 已读 AGENTS.md、gateflow/planreview SKILL、F6 goal/owner-preflight/plan-delivery、当前计划前缀及历史全文。权威 `docs/gateflow/pr-197-r1-f6-plan-review-adjudication-20261001.md` 全文，包含最新 DS 终态/A1–A4/恢复段；两份 `docs/reviews/plan-review-20261001-113609.md`、`plan-review-20261001-115109.md` 仅作只读建议，票数或 pass-with-risks 不替代 root。
- 本轮开端仅观察到 F3 五 utils 的改动，与用户交接 Sol7594 的独立写入范围一致；本作者未改这五文件，未核收 F3 产品。root 非冻结 checkpoint 仅作记录，不作 owner 源码漂移。未派子 Agent，未访问网络、真实 PDF/OCR 或私人语料。

交付末次 `git status` 另观察到三份不在 freeze 内的 root 可变文档改动：`docs/gateflow/pr-197-review-repair-adjudication-20260930.md`、`docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`、`docs/upload_material_repair_handoff_prompt_3.md`；只记录，本作者未写它们。`end-status.txt` 保留完整观察；本任务实际正式写入仍仅 current plan 与本报告。计划的 `git diff --check` 实际 exit0、双流为空，记录 `final-diff-check.*`；该命令不检查未跟踪报告，未将它冒称产品测试或报告全量验证。

动机成立且仅为可实施性修订：真实 SEC 正常尾部有 cancelled/ok 两值和完成日志，现计划共享接口缺这一维度；CN 新异常若漏三类型 catch 会丢确认前缀；SEC 已决定的两类型中止规则需要枚举真实抛点和迁移既有测试；CN 已决定的行 reason 必须迁移真实 Phase B node。未重新裁产品行为、未新增业务/schema/owner 选择。

## 2. 每 finding 的最小改文与 owner 验证清单

| Finding | 计划修订位置与最小变化 | 实施后验证及保留边界 | 本轮状态 |
| --- | --- | --- | --- |
| A1 中 | B/D2/E：`_build_sec_download_result` 增显式 `status: Literal["ok", "cancelled"]`；正常尾部传原 cancelled/ok，所有 abort 调用点传既定 ok。仅抽计数和结果组装，完成日志留正常调用方，消费同次 summary；builder/abort 不打完成日志，不造 PIPELINE_COMPLETED | 真实循环尾与成功 repair 后 clean→cancel 覆盖；旧早期 helper 保持；原 SEC 八键/rejected/skipped 计数唯一，不新造终态 | 计划文本已修复，待 root/同版复审核定 |
| A2 低 | D1/E：postrepair classifier 和新 RepairRequired raise 同处三类型封闭 catch；原 cause 对象/链经 `_integrity_abort` 保确认前缀，再走现成 adapter | 真实 Fs 第二来源损坏经 CN production adapter direct/job 保 repair 行和新 cause；mid-filing 仍真实可达两类型，不造 fake 第三类 | 计划文本已修复，待 root/同版复审核定 |
| A3 中 | D3.2/E：枚举 SEC 四个单 filing Preflight 抛点，沿已决定 pair catch/当前无 terminal 恰一 failed 行规则，不收窄裸抛；保原 cause/reason、确认前缀、tail 零执行/零新 mutation。补 6-K 旧 node 迁移和真实 Phase B UNSAFE 前缀覆盖 | 初始整体 preflight 仍裸抛/空摘要；failed 行仅表示已开始文档未完成，不造 rejected 成功发布，不改预算/发布政策；single-filing 的源码仍只读 | 计划文本已修复，待 root/同版复审核定 |
| A4 低 | E：补 CN 真实 Phase B node 的旧 reason→source_integrity_failed 迁移；D1 明确保留私有 abort 安全文字“本地来源完整性预检失败” | 原 cause 链/成功+failed 行/失败事件/commitrollback 不削弱；runtime 解原 cause、C 表唯一 public mapping，不从 wrapper str 发明第二原因/新日志/schema/prompt/双常量兼容 | 计划文本已修复，待 root/同版复审核定 |

### A1：明确真实调用、取消与日志

本作者实读 `sec_download_workflow.py:580–766`，其中 `:607–630`、`:670–705` 的真实取消会进入统一尾部；`:718–733` 是计数，`:734–742` 是完成日志，`:743–762` 显式传 status。新计划接口是朴素显式 typed 参数，status 决策留各调用点。abort 私有 ok 只保既定快照形状，操作失败由原 typed 异常承担；正常尾部仍按原规则产生包括 cancelled 在内的完成事件。

E 明列 `tests/fins/test_sec_pipeline_download_stream.py` 内拟新增 `test_sec_loop_tail_cancel_preserves_shared_result_status`（首 filing 前/文档边界/single-filing 无 terminal 取消 return）与 `test_sec_postrepair_clean_cancel_preserves_confirmed_repair`（真实 Fs 种坏来源，收到 repair 成功 terminal 后置取消，真实 classifier 已 clean）。确认行、COMPLETE/meta/payload、未执行 tail、公司/deferred gate 均守恒。未取消正常尾部保持 ok。

本作者实读旧 `test_download_stream_repair_gate_rechecks_cancel_before_company_batch`（943–985）与 `test_download_stream_cancel_stops_during_collection_before_filing_requests`（988–1014）：前者没有种坏来源，后者走早期独立 helper。保留原 cancelled/调用次数/不发 filing 请求断言，**不将任何一条冒称成功 repair 后取消或共享 builder 的完整覆盖**。早期 helper 潜在空行计数差异不统一。

既有拟新增 `test_sec_integrity_abort_adapter_preserves_cause_and_summary[postrepair/churn]` 补断言：真实 abort 链的私有 snapshot ok、无 PIPELINE_COMPLETED、无“美股下载完成”日志；不以直接调用 builder 取代实际 abort 验证。

### A2：CN 三类型 catch 与确认前缀

本作者实读 `cn_download_workflow.py:404–427` 的真实 try/raise/except：旧 raise 在 try 内、except 仅两类型。D1 现在精确指定 `(SourceIntegrityPreflightError, SourceIntegrityRevisionConflictError, SourceIntegrityRepairRequiredError)`；保同对象 `raise _integrity_abort(cause=exc, 原快照参数) from exc`，不让 RepairRequired 裸穿成为请求级空摘要。

迁移 `test_cn_post_repair_real_second_selected_source_conflict_preserves_first_row` 及 runtime `test_cn_post_repair_real_second_source_revision_conflict_preserves_public_summary[direct/job]`，真实第二来源损坏→新 cause→原 workflow/adapter 摘要；只有成功 repair 行时文档摘要 succeeded 允许，操作失败保持。不将 mid-filing 两类型 catch 泛化成 fake 三类型生产路径。

### A3：四抛点、failed 行、零新 mutation 与旧 node 迁移

本作者实读 `sec_download_filing_workflow.py:238/275/383/505`：依次为 Phase A UNSAFE、registry 拒绝 repair target、6-K 政策拒绝 repair target、Phase B UNSAFE；原 reason 分别为 UNSAFE_PUBLICATION 或 SELECTED_REJECTED_REPAIR_REQUIRED。均沿 D3 已确定的 pair catch、保 cause/链/确认前缀，当前无 terminal 时恰一 failed 行/一次失败事件，然后 typed abort；tail 零执行、不新发布。Phase B 原临时 batch rollback 留原 owner。initial 整体 preflight 仍裸抛/空摘要；没有新业务取舍或按 reason 例外裸抛。

实读 `tests/fins/test_sec_pipeline_download.py:6148–6205` 的 `test_sec_selected_repair_that_6k_policy_rejects_fails_before_mutation`。E 迁移 expect 到 SecDownloadIntegrityAbort，原 Preflight cause/SELECTED_REJECTED_REPAIR_REQUIRED、__cause__ 同对象、snapshot total=1/failed=1；原 meta/payload 字节不变、company/registry/rejected 不存在等断言全部保留。新增失败行不表示持久发布发生，不削弱旧 zero-mutation 契约。

E 另列原 stream 文件内 `test_sec_phase_b_real_preflight_aborts_with_confirmed_prior_filing`：首真实成功确认后，第二 filing Phase A 后、staged classifier 前置 exact target 非声明合成文件，实际 Phase B UNSAFE；success+当前 failed、total=2/down=1/failed=1、原 cause/链、一次失败事件/无完成事件、rollback/零新提交发布、首 meta/payload/manifest、第三 tail 零调用/零行。不得 fake throw。

### A4：CN Phase B 精确迁移与私有文字决定

本作者实读 `tests/fins/test_cn_download_workflow.py:2893–3000` 的 `test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing`。E 只迁移旧行 reason 断言到 source_integrity_failed；其余 Preflight/UNSAFE_PUBLICATION、__cause__ identity、integrity_failed 快照、downloaded+failed 两行、FILING_FAILED 恰一次、无 PIPELINE_COMPLETED、commit_calls=2/rollback_calls=1、首 meta 可读与第二 unsafe target 断言全部保留。

实读 CN 私有类 `:59–84` 和 runtime `:6900–6991`：wrapper 文案是现有安全文字，公共 owner 解 adapter 原 cause 并按类型/原 reason 映射。按 root 已拒的额外阻塞意见，D1 明确保留该私有文字，不中性化以扩修日志/prompt。行常量换为已决定原因/说明，wrapper 常量仅保内部职责，禁止旧值兼容别名或用两套常量兼容旧行原因。操作 reason 与行 reason_category 的层级按既有合同保持。

## 3. 最小性、业务守恒与文档职责

只改计划当前前缀及真实当前状态，保留一个 F6-S1、原 8 个 production 文件和原 10 个 test 文件集合；拟新增/迁移 node 均在原文件集合内。没有新 goal/slice/schema/status/repair 预算/发布政策。F6-P1 是本 F6 必要修复，不延期、不重问；F6-PV01 已修，不重提。来源仅 SEC/CNINFO/HKEXNEWS 三值，入口 direct/job/CLI/wait 四种，不造第四来源。

job 仍仅同源 message+result_summary，不保存 reason/hint/新字段，wait 仍 process observation reader；cancel、普通文档 fail、6k_filtered、SC13、manifest 成功与公司独立事实的其它已裁规则保持。没有宽 parsing/fallback/字符串猜因/下游补偿或重写 source/tests。

已实读三份 README 职责：Fins README 只写已实现架构/公共契约，tests README 只写已存在测试，根 README 只写当前用户流程/排障。当前只有计划文档修订，没有产品、测试、用户流程或架构行为落地，故本轮不触 README；未来已批准实施完成后原职责触发义务不变。AGENTS 的测试/pyright/逐文件 coverage 要求留在 E1 实施验收，本轮不冒称执行。

## 4. Old/new SHA、逐件身份与 history 保全

| 对象 | 实算结果 |
| --- | --- |
| 原 current plan / 本轮 original | `c59787460262b7706f6d5312da61d693474d02403b493e2484ad2c053cd6e566` |
| 修订 current plan | `57ab49b7648444629db3290b7d8ba54b397b63f1495fe70fd0e0d18c71d7f1b1` |
| freeze 首末 | `c937922289ce2bf23d94f4fd63b8d8fbb1ad9e432a6a09128e3b871935233e7f` |
| 历史 tail，原/新均 45,467 字节 | `1e5dc65d5c152088d696254140ed3bf0a090e70778405af42d2d02f3406742b9`，cmp exit0 |
| 首检 | 60 current + 60 originals 逐项重算与 freeze 全匹配，两次 shasum -c 均 exit0 |
| 末检 | 60 current + 60 originals 实际 SHA 清单；59 readonly 与 freeze 全匹配；60 originals 与原 freeze 全匹配；唯一 current plan SHA 如上 |

临时证据全部在 `workspace/tmp/pr197-f6-plan-review-fix-sol-20261001-01/`：

- `start-current.sha256` / `start-originals.sha256` 为从 freeze 生成的逐件 expected 清单，实际重算结果及独立双流/exit 在 `start-current.*` / `start-originals.*`；不是只读 expected 就宣称验证。
- `end-current.sha256` / `end-originals.sha256` 为实际重新计算的 60+60 件 SHA；`end-readonly.sha256` 是 59 件 expected，实际核算在 `end-readonly.stdout.log/.stderr.log/.exit`。`end-originals.stdout.log/.stderr.log/.exit` 核全部 originals，`end-originals-hash.*` 记录重算退出。各项 exit0；全部 stderr 空。
- `freeze-start.sha256`、`freeze-end.stdout.log/.stderr.log/.exit` 核 freeze 不变。
- `history-original.bytes` / `history-current.bytes` 使用 tail 从历史标题行开始提取原字节，保原换行；原标题第196行、新第208行，边界在 `history-boundaries.txt`。`history-cmp.stdout.log/.stderr.log/.exit` 为独立字节比较证据，exit0；history 原作者正文、旧 token、旧失败全部保留。
- `plan-prefix-original.md` / `plan-prefix-current.md`、`plan-prefix.diff` / `plan-prefix-diff.stderr.log/.exit` 是独立前缀证据；diff exit1 表示有预期改文，非失败冒绿。历史 tail 不在 prefix diff。
- `start/end-branch.txt`、`start/end-head-main.txt`、`start-status.txt`、`end-status-before-report.txt` 记录身份/外部并行变更。所有新证据不覆盖 freeze/originals 或旧日志；报告路径在写前两次确认不存在，末次 `report-absence.*` 有 exit0。
- `command-ledger.json` 记录关键核算命令、独立双流和真实 exit；工具读取/补丁原记录留本轮 transcript，不编造 shell 退出码。

## 5. 本轮命令限制、非零与恢复

未引入可执行验证脚本、临时 Python 或新 pyright 配置。身份及字节验证只调用 jq/shasum/head/tail/cmp/diff/git 等现成工具，关键实际核算有独立 stdout/stderr/exit。读取探索保留本轮工具 transcript，未伪称每次 read 都另存双流。

1. 一次 apply_patch 包含了对整段 PV01 文字的短行匹配，工具 verification failed（找不到该短行），整批未落笔；去掉该失败 hunk，按真实整行重做 E 修订成功。旧作者三个证据/失败段正文未改，改用段前说明限定其轮次。本错误仅是 patch 上下文失败，无 shell exit 值，不伪造为 exit0；工具 transcript 保留。
2. 本轮 thread session 文件定位无匹配，搜索与后续 sed 是复合 read，outer0 不认证其内部搜索退出码；没有独立记录该内层 exit，不补造。恢复为直接读取本轮 runner thread.started/stderr、如实报告 actual model unknown；该定位不承担业务事实，未扩大目录扫描或切模型。
3. 多次大段只读输出被工具截断，outer0 不证明作者读完显示内容；已按真实行段拆开补读当前前缀/历史/两 review/源码与测试，未用截断处得出结论。
4. `diff -u` 前缀 exit1 是已保存的预期“内容不同”，stderr 空，无恢复需要；另对未跟踪报告运行 `git diff --no-index --check /dev/null`，真实 exit1 来自 no-index 隐含的差异退出语义，stdout/stderr 均空、没有 whitespace 诊断，独立记录 `report-whitespace.*`，不写成 exit0。cmp 与所有 hash 检查实际 exit0，不用总 shell0 掩盖这些 diff1。

SEC 旧 fixture 两次 pytest exit1（shared core/keyword/seed、日期排序问题）、旧空文件类型检查、PV01 explicit-before 内层 exit1/2 errors→真实2-file after0 的记录和数字原样留在计划 F/旧报告，未重跑或覆盖；旧 0-files 永不当类型通过。root 裁决内的 MiMo69turns/outer0、Kimi 五小时403失败原件、授权 DS97turns/outer0 部分核收、DS 两次自动审核deadline未启动、Sol routing失败/39776恢复核收均保留只读，本作者不重新认证所有旧中间命令，也不将失败原件变成 gate pass。

本轮实际未执行：产品 pytest/pyright/coverage、旧4/3 owner probes、真实下载/转换/网络、最终 CLI CI、oracle/scenarios/readiness、任何产品 source/test/README/config/registry 写入、git stage/commit/push/PR/merge、子 Agent 派发。没有 0-files 冒绿，没有把旧160执行/readiness当真实 CI；旧 Raw 已删除，不补造历史证据。

## 6. Residual 分类、未覆盖与下一入口

| 项目 | 分类 / owner / destination |
| --- | --- |
| A1–A4 计划合同与迁移遗漏 | fixed in current fix（计划文本证据）；root 与同版 re-review 核最终修复状态，本报告不能自动关闭 gate |
| 真取消、postrepair、四SEC抛点、CN Phase B 的产品动态验收 | covered by later approved F6-S1；workflow/adapter/runtime owner，须 accepted plan 后实施 E/E1，本轮未跑 |
| PV01 2-file/3-owner 证据 | root 已修复核收；原件保全，非当前产品类型/coverage验收 |
| 完整 structured reason durable | assigned to 既有 WU `fins-download-job-reason-code-persistence`；job contract/store owner，原独立 schema/待 goal 边界保持 |
| publication indeterminate | assigned to 既有 storage publication 独立 WU；本 F6 非目标 |
| 早期取消 helper 空行计数差异、两份 rejected helper 的统一 | requiring new issue or explicit user decision；SEC workflow/结果协议 owner，不自动扩 F6/F7 |
| RepairBlocked 下载 mapping、私有 abort 中性化作为额外 blocker | root rejected-with-reason，前者无真实下载专用 repair 路径，后者未证实公共/持久化第二原因；不新增必修 |
| F3/F4/F5/F7 和最后真实完整CLI CI | root 管理既有 WU/依赖序列；F5 Q1 不代选，最终 commit 上重建真实 CLI CI→oracle/scenarios/readiness，旧 Raw 不补造 |
| actual model 元数据未获得 | runner/controller 证据限制；本轮如实 unknown，root 以真实运行元数据核收，不据任务标签填值 |

本轮没有新增 business/schema/owner open question，也未 defer 任何 accepted finding。当前计划修复及本报告交付后停止；**下一入口仅 root 核收本版 SHA/身份/修复证据，再安排同版 MiMo/Kimi（quota 时已授权 DS 备份）re-review**。plan gate 仍未通过，F6 产品尚未实施，全部以后续授权流程进入既有 draft PR197，由用户 merge；本作者不执行 accepted plan commit 或后续 gate。
