# upload_material 修复阶段接手 prompt（#198 闭环后）

给新 Agent：本文件是可执行接手指令。全程中文。用户已完成 UM-O01～O36 第一轮逐项裁决，随后授权按 `$gateflow` 与 `$sub-agents` 修复所有 accepted 项及 GitHub issue #198，并要求所有闭环代码进入现有 draft PR #197，由用户手工 merge。前一份 `docs/upload_material_oracle_celibration_handoff_prompt_2.md` 停在 UM-O11 逐项裁决阶段，**不能作为本阶段的执行入口**。接手后先验证当前状态，不重跑已完成的裁决，也不要求用户重述授权。

## 1. 首先读取与实时核对

**唯一开发工作树与分支**：`/Users/leo/workspace/dayu-agent-r` 中的 `codex/upload-material-oracle`。Git remote 是 `github`；PR：`https://github.com/noho/dayu-agent-r/pull/197`，保持 draft，用户自己 merge。只能在该工作树的该分支上编写 plan、实现、修复、文档，执行开发验证、暂存、提交和推送；不得再从旧本地分支、隔离工作树或 detached checkout 开发，也不得修改 `main`。如果起步时不在该分支，先停止写入，核对主工作树与 Git 引用并安全切回，不得在错误分支上继续。旧工作树只作为证据来源；审查者可在隔离快照运行审查验证，但不得对快照做持久编辑或提交。审查报告由总控核验后归档到目标分支。

先读根 `AGENTS.md`、`/Users/leo/.codex/skills/gateflow/SKILL.md`、`/Users/leo/.codex/skills/sub-agents/SKILL.md`，对应 plan 使用 `$planreview`、代码/aggregate/PR review 使用 `$deepreview`。先执行 `git status --short --branch`、`git branch --show-current`、`git log`，核对本地 `codex/upload-material-oracle`、`github/codex/upload-material-oracle`、`git ls-remote github` 和 `gh pr view 197` 的 head，再读相关 issue 的实时状态。任何写入前先确认主工作树干净或已有改动均已盘点，避免覆盖未提交成果。

权威队列：`docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`。先读其“修复清单”“硬依赖与建议顺序”“后续 review 揭示的组内集成边”，再读**末尾时间线**及每个独立 WU 的 goal、plan、adjudication artifact。另读 `docs/gateflow/upload-material-local-branch-integration-audit-20260930.md` 和 `docs/gateflow/upload-material-local-evidence-preservation-20260930.json`，核对已汇入代码、历史证据与尚未实施 WU 的边界。主队列开头的整合前状态是历史记录，不能覆盖末尾时间线和当前代码。旧冻结 oracle 的观察不等于当前代码，旧计划的“在途”状态也会过时；以结构化 runner 结果、已提交快照、真实代码和当前 Git/PR 为准。任何新 repair finding 必须立刻同时登记独立 WU adjudication 和主队列，避免上下文压缩丢失。

## 2. #198 的边界与当前检查点

Issue：`https://github.com/noho/dayu-agent-r/issues/198`。已接受的 S1 修 typed source integrity 公共失败投影及 partial publication 守恒；S2 修真正未知 download 的安全 operator 诊断与 CLI 日志指引。S1 commit `7234d42dbaea603112c6fed52776281228d261a7`；S2 commit `2643de25d6258fe2d83b527ea3823ffa3eb19bff`。S2 fresh 隔离 CLI 证据在 `docs/gateflow/issue-198-s2-cli-fresh-evidence-20260929.md`，有效日期窗口扩大到 2025-03-27..31 才发现同一 FY 候选，真实 CNInfo→Docling→manifest 发布、typed `storage/unsafe_publication` 失败及清除后恢复均已验证；精确单日 0 候选归独立 CNInfo WU。

历史集成事实：PR #197 原 head `9735800c` 与 #198 S2 `2643de25` 从共同基线 `8d8d494f` 分叉；#198 后以 merge commit `2219d40b` 受控汇入 PR，没有强推覆盖原有点号元数据/O03/O20 提交。此分叉已处理，不能把当时的状态当成当前待解决问题；接手时以实时 `gh pr view` 与 Git 图为准。

**#198 交接检查点（2026-09-29）**：整项 aggregate accepted commit `cc6ee444fba62ff128fd01d97263a6c53efe5bc7`；PR review F1 修复后双路同版 MiMo/ds-flash 复审有效且无新 material finding，accepted PR review commit `c37b71ee1a271e22c3a2330a0fb88bcd32f6aab4`。该 commit 已推送并经 `git ls-remote` 与 `gh pr view` 读回，PR #197 OPEN/draft/mergeable、base main、CI checks 空。PR body 唯一普通文本 `Closes #198`，GraphQL `closingIssuesReferences` 返回 OPEN issue #198，用户手工 merge 后预计自动关闭。四份 PR review artifact、总控裁决与修复队列均在 PR 中；`docs/gateflow/issue-198-final-closeout-20260929.md` 是 final closeout 真源。用户已单独授权 issue closeout comment，评论 `https://github.com/noho/dayu-agent-r/issues/198#issuecomment-5893424991` 已发布且正文读回一致；**#198 已 final closeout pass / work unit completed**。接手时以实时 PR head 与 closeout artifact 的最新版本为准，不把本段代码验收 commit 当作最终文档 head。

## 3. 新 Agent 的下一个入口

#198 已通过 final closeout。用户随后要求对 **PR #197 完整 diff** 做 MiMo/ds-flash 并行审查；首轮已完成并裁决。代码审查快照 base `fac32ecbf`、head `2c1d0a71`，当时全 PR 255 changed files/45 commits；两路原始 review 为 `docs/reviews/pr-197-review-20260930-002934.md` 与 `docs/reviews/pr-197-review-20260930-000803.md`，总控结论为 `docs/reviews/pr-197-review-20260930-003634.md`，逐项裁决为 `docs/gateflow/pr-197-full-review-adjudication-20260929.md`。它与 #198 已闭环的局部 PR review 是两件事。**首轮完整 PR review 的 F2～F7 仍是待闭环优先队列；GitHub 的 MERGEABLE 仅表示当前无 Git 冲突，不表示代码审查通过。**接手时先读上述 artifact、主队列开头的 `PR197-R1` 表，并在线核对新 PR head；不要把旧审查快照 head 当成最新 head。

**2026-09-30 本地分支整合完成后的检查点**：用户要求先把其它分支已有成果汇入 `codex/upload-material-oracle`、本地与远端同步，再实施尚未实施的 WU；此整合已完成。资产规划代码、相应测试、README 与历史裁决/审查证据随 `e215b446da89bccfea4856aceaa6dce807659b57` 提交并普通推送；最终整合审计文档随 `9c70bea1fab65a33e5b3e027cf22d16ec991072e` 提交并推送。整合的资产 S1 最终同版 MiMo/ds-flash r9 复审均有效、零新 material finding；总控受影响 17 文件矩阵 **1399 passed/1 skipped**、全量 pyright **0 errors/0 warnings**。已盘点的 163 份历史文档均获保存；旧工作树及安全备份仍在，但旧草稿或候选不能冒称 gate acceptance。整合审计详见 `docs/gateflow/upload-material-local-branch-integration-audit-20260930.md`，资产代码审查裁决详见 `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md`。

交接前实时核对：本地 `codex/upload-material-oracle`、远端同名分支与 PR #197 head 均为 `9c70bea1fab65a33e5b3e027cf22d16ec991072e`；本地及远端 `main` 均为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`，两个对应工作树均干净。PR #197 为 OPEN/draft、base `main`；GitHub 报 MERGEABLE。上述值是本次读回快照，更新本 prompt 或后续修复推送后须重新读回，不能沿用旧 hash/mergeable 结论。**本次整合不等于 F2～F7 或 O05/O16/material file-state 等未实施 WU 已修复。**

**用户最新执行顺序：下一位 Agent 先修复这次完整 PR review 中成立的全部 findings，完成同版双路复审和总控 closeout，之后才继续原有 upload_material / 其它独立 WU 队列。**这里的“全部”包括新发现的 `F2/F3/F4/F5/F7`，也包括本次审查重新确认、此前虽已分配独立 WU 的 `F6`；`F1` 已被总控 rejected-with-reason，不要求修。`deferred-with-owner` 表示修复归对应 WU 的语义 owner，不表示在本次优先顺序中可以跳过。各项须先按 Gateflow 确认 goal/依赖、由 Sol plan/implement/fix、MiMo 与 ds-flash 同版并行 review，总控逐项裁决；发现新修复项立即登记主队列和对应 artifact。不得在这些 findings 未闭环时转做原队列下一项，也不得仅把它们写进计划就宣称 PR review 已通过。

建议按依赖与风险安排下列修复；可并行处理互不冲突的 WU，但最终必须全部闭环并对同一最终 PR head 做完整复审。不回退已通过 gate，不把 plan 候选当产品修复：

1. `PR197-R1/F2`：test owner 的 `result` 循环外引用在 pyright 1.1.408 报 possibly-unbound。低风险，Sol 最小修测试后同时用 1.1.408 与项目 venv 模块版 pyright 复核。
2. `PR197-R1/F3`：四个新增 `utils/` 分析脚本有硬编码私有绝对样本路径/身份。Sol 将样本根与清单改为显式输入并用临时样本核验；**普通提交无法抹去公开 PR 历史**，不能擅自 force push 或声称历史已清除。历史级处理如确有需要须另行裁决。
3. `PR197-R1/F5`：HK discovery 与 rebuild 使用不同年度锚点证据；窄窗口可能把长度型季度公告静默丢弃并报 missing。先对独立 `fins-hk-fiscal-anchor-consistency` 做 goal confirmation，再由 Sol plan/implement/fix、MiMo/ds-flash 双路 review；owner 必须统一受信公司年度证据，明确并发/冲突与“有候选但证据不足”的公开语义，不能恢复“三个月直接猜 Q1”。这是本轮中等优先级语义 finding。
4. `PR197-R1/F7`：`ok/cancelled/integrity_failed` workflow→adapter status 词表所有权分散；独立 `fins-download-status-contract-owner` goal 后在协议 owner 收敛，勿加兼容 re-export。本次 PR findings 修复批次内完成。
5. `PR197-R1/F4`：HK identity O(S·D) 重复 meta/锁读取，已归 `fins-hk-download-identity-batch-read`。先由 storage owner 设计同一 publication guard 下的一致批量快照，不用跨发布 stale cache 局部修；本次 PR findings 修复批次内完成。
6. `PR197-R1/F6`：RevisionConflict 的公开 EXECUTION 分类是真实残余，但 #198 plan/测试已明确归既有 `fins-download-storage-sibling-errors`，不是本轮新建 #198 回归。该 WU 要区分损坏需修复与并发冲突重试的安全 reason/hint；本次 PR findings 修复批次内完成。生成脚本 PATH 候选 `F1` 因未激活/不满足 Docling 依赖下界而 rejected-with-reason；不安排该项产品修复。

本轮激活隔离 venv 的 22 个变更 Python test 文件 **2128 passed/2 skipped/3 warnings**；当前 venv `python -m pyright dayu/ tests/ utils/` 0 errors，但系统 pyright 1.1.408 对 F2 报 1。全 PR `git diff --check` 有 fixture `final-pyright.log` 一处 EOF 空行；后续编辑/合并前清理并复核。没有远端 CI checks、全仓 pytest、coverage 或真实外网 provider 验证。以上是锁定 `2c1d0a71` 的审查证据，任何修复 commit 后都要对新 head 重新验证。**仅在 F2/F3/F4/F5/F6/F7 全部修复、受影响测试和 pyright 通过、MiMo/ds-flash 同版复审与总控 PR closeout 通过后**，才按主队列依赖顺序选择下一 eligible WU：

- 点号元数据与 UM-O03 的闭环增量此前已在 PR #197；核实时以线上 commit 与 review artifact 为准，不重复实施。
- O04/O23 统一资产规划与文件名→Docling 文件名函数的已审代码随 `e215b446` 汇入；按主队列核对其 gate 边界和 O25 primary 选择后续工作，不在旧资产分支再开发。
- 请求/身份链中的 O05/O06/O09/O10/O12/O16/O17 仍须按唯一 canonical form、日期与 company/source 身份 owner 的依赖顺序实施。O06 用户已选 `material_name` trim 后最多 240 Unicode 码点。O11 的已接受日期校验代码已受控重放到目标分支（`c4c83891`、`e698895a`），整合时保留其前置校验语义；不用再从旧 O11 分支搬代码。O17 是 form 单函数真源，O05 不能再建第二份。
- O14/O15 的 published state guard 依赖 O12 同版公司/source 单 batch 与可信 COMPLETE tombstone；O18 amended 行为依赖 O12/O14/O15。用户已定同字节仅切 amended：无 `--overwrite` metadata-only 保留内容版本；带 `--overwrite` 强制重新转换并发布，版本按既有指纹规则保持。
- O20-F02 按受控 XBRL 支持推进：补齐 Docling/Arelle、taxonomy 和 OS 隔离，验证有效 instance，经 Docling 转换并登记 manifest 才算成功；Docling 抽取正确性归上游。纯合成 typed-member 崩溃已报上游 #4437。O21/O22 typed content failure、O33 同 identity 并发均有依赖，见主队列。
- CNInfo 公开 `filing_date` 用户已定按中国本地披露日，仅修新发现/新下载；历史已发布迁移另议。它是 #198 验证中发现的独立 WU，不要改写 #198 S2 通过结论。

## 4. 外部子 Agent 与门禁合同

**用户指定的派发与裁决合同**：使用 `$sub-agents`，通过 `claude-agent-run` / `codex-agent-run` **runner 子进程**派发外部 Agent；你自己担任总控并作最终裁决。`gpt-6-sol` 负责 plan、implement、fix，开发调用的 `--cwd` 必须是 `/Users/leo/workspace/dayu-agent-r` 且该工作树处于 `codex/upload-material-oracle`；`mimo` 与 `ds-flash` 负责**两路同时并行、彼此独立的 review**。每一次调用都必须显式传入 `--cwd <workspace 绝对路径>`，使用该次调用独立的 output 与 stderr 文件（Codex 另有独立 last-message，验证任务另有 canary），唯一 label/instance；不得依赖默认 cwd 或共用输出文件。先运行 `sub-agent-preflight` 并确认 `setup_status=ok`，再按 skill 以独立子进程调用派发。总控逐路检查进程 exit、JSON/JSONL 结构化 terminal、失败事件、stderr 白名单、canary 逐字匹配、工具成功证据及实际 artifact，核查代码/测试后**自行裁决**；Agent 自述或两路一致意见都不能代替总控 gate pass。只允许一次有理由的同 provider 修复性重试，再失败切换路线并登记。并行 review 可使用不同干净快照读取代码和运行验证；评审发现回到目标主工作树登记和修复，不能在快照上创建开发分支、持久改代码、提交或推送。

每个 WU 按 Gateflow 的 goal→plan/双路 review→实施/双路 review→aggregate deepreview→draft PR 复审→final closeout 顺序推进；accepted finding 先 Sol 在唯一目标分支修复，后同版双路复审。每次代码改动补测试、跑受影响 pytest 和全量 pyright，按根 `AGENTS.md` 判断 README 更新；单文件覆盖率目标 ≥80%。只在 `codex/upload-material-oracle` stage 当前 gate 授权路径，先 `git diff --cached --check`，再提交并普通 push 到远端同名分支，读回远端 ref 和 PR head。所有闭环代码、评审证据和必要 handoff 文档进入同一个 PR #197；不要新开 PR、mark ready 或 merge，用户手工 merge。

## 5. 停止与汇报

遇到 owner/contract/schema 的真正阻断、用户未授权的外部 comment/issue/merge 动作，按 Gateflow 停下并说明已完成的可审结果。不要因模型容量或上下文压缩丢失修复清单；先回读主队列与独立 adjudication 再接续。每个 WU 完成时汇报目标、实际代码、测试/pyright/CLI 证据、findings、风险、PR #197 head 与下一个入口，所有本地 artifact 用可见的**完整绝对路径**。完成所有授权 WU 后汇总，等待用户手工 merge。
