# upload_material 修复阶段接手 prompt（#198 闭环后）

给新 Agent：本文件是可执行接手指令。全程中文。用户已完成 UM-O01～O36 第一轮逐项裁决，随后授权按 `$gateflow` 与 `$sub-agents` 修复所有 accepted 项及 GitHub issue #198，并要求所有闭环代码进入现有 draft PR #197，由用户手工 merge。前一份 `docs/upload_material_oracle_celibration_handoff_prompt_2.md` 停在 UM-O11 逐项裁决阶段，**不能作为本阶段的执行入口**。接手后先验证当前状态，不重跑已完成的裁决，也不要求用户重述授权。

## 1. 首先读取与实时核对

工作区：`/Users/leo/workspace/dayu-agent-r`；Git remote 是 `github`；PR：`https://github.com/noho/dayu-agent-r/pull/197`，保持 draft，用户自己 merge。先读根 `AGENTS.md`、`/Users/leo/.codex/skills/gateflow/SKILL.md`、`/Users/leo/.codex/skills/sub-agents/SKILL.md`，对应 plan 使用 `$planreview`、代码/aggregate/PR review 使用 `$deepreview`。先执行 `git status --short`、`git branch --show-current`、`git log`，读 `gh pr view 197` 与相关 issue 的实时状态。

权威队列：`docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`。先读其“修复清单”“硬依赖与建议顺序”“后续 review 揭示的组内集成边”，再读**末尾时间线**及每个独立 WU 的 goal、plan、adjudication artifact。旧冻结 oracle 的观察不等于当前代码，旧计划的“在途”状态也会过时；以结构化 runner 结果、已提交快照、真实代码和当前 Git/PR 为准。任何新 repair finding 必须立刻同时登记独立 WU adjudication 和主队列，避免上下文压缩丢失。

## 2. #198 的边界与当前检查点

Issue：`https://github.com/noho/dayu-agent-r/issues/198`。已接受的 S1 修 typed source integrity 公共失败投影及 partial publication 守恒；S2 修真正未知 download 的安全 operator 诊断与 CLI 日志指引。S1 commit `7234d42dbaea603112c6fed52776281228d261a7`；S2 commit `2643de25d6258fe2d83b527ea3823ffa3eb19bff`。S2 fresh 隔离 CLI 证据在 `docs/gateflow/issue-198-s2-cli-fresh-evidence-20260929.md`，有效日期窗口扩大到 2025-03-27..31 才发现同一 FY 候选，真实 CNInfo→Docling→manifest 发布、typed `storage/unsafe_publication` 失败及清除后恢复均已验证；精确单日 0 候选归独立 CNInfo WU。

重要集成事实：PR #197 原 head `9735800c` 与 #198 S2 `2643de25` 从共同基线 `8d8d494f` 分叉，前者**不是**后者祖先。上一 Agent 已在 PR head 上受控 merge #198，合并 commit `2219d40b` 两父为 `9735800c` 与已过 aggregate deepreview 的 `cc6ee444`；没有强推覆盖 PR 原有点号元数据/O03/O20 提交。接手时仍要核实时 `gh pr view` 与 `git merge-base`，不沿用旧“可快进”推断。

**#198 交接检查点（2026-09-29）**：整项 aggregate accepted commit `cc6ee444fba62ff128fd01d97263a6c53efe5bc7`；PR review F1 修复后双路同版 MiMo/ds-flash 复审有效且无新 material finding，accepted PR review commit `c37b71ee1a271e22c3a2330a0fb88bcd32f6aab4`。该 commit 已推送并经 `git ls-remote` 与 `gh pr view` 读回，PR #197 OPEN/draft/mergeable、base main、CI checks 空。PR body 唯一普通文本 `Closes #198`，GraphQL `closingIssuesReferences` 返回 OPEN issue #198，用户手工 merge 后预计自动关闭。四份 PR review artifact、总控裁决与修复队列均在 PR 中；`docs/gateflow/issue-198-final-closeout-20260929.md` 是 final closeout 真源。用户已单独授权 issue closeout comment，评论 `https://github.com/noho/dayu-agent-r/issues/198#issuecomment-5893424991` 已发布且正文读回一致；**#198 已 final closeout pass / work unit completed**。接手时以实时 PR head 与 closeout artifact 的最新版本为准，不把本段代码验收 commit 当作最终文档 head。

## 3. 新 Agent 的下一个入口

#198 已通过 final closeout。用户随后要求先对 **PR #197 完整 diff** 做一轮 MiMo/ds-flash 并行审查，再更新本 prompt；这轮已经完成并总控裁决，**没有在此轮修产品代码**。代码审查快照 base `fac32ecbf`、head `2c1d0a71`，全 PR 255 changed files/45 commits；两路原始 review 为 `docs/reviews/pr-197-review-20260930-002934.md` 与 `docs/reviews/pr-197-review-20260930-000803.md`，总控结论为 `docs/reviews/pr-197-review-20260930-003634.md`，逐项裁决为 `docs/gateflow/pr-197-full-review-adjudication-20260929.md`。它与 #198 已闭环的局部 PR review 是两件事。**总控结论：完整 PR 尚有 accepted finding，当前不是可合并验收状态；GitHub 的 MERGEABLE 只说明当时无 Git 冲突。**接手时先读上述 artifact、主队列开头的 `PR197-R1` 表，并在线核对新 PR head；不要把审查快照 head 当成此后文档提交的最新 head。

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
- O04/O23 统一资产规划与文件名→Docling 文件名函数是 O25 primary 选择的前置；隔离工作树和审查结果见主队列，已有候选修复/findings 不得漏掉。
- 请求/身份链中的 O05/O06/O09/O10/O11/O12/O16/O17 须按唯一 canonical form、日期与 company/source 身份 owner 的依赖顺序集成。O06 用户已选 `material_name` trim 后最多 240 Unicode 码点；O11 另有本地 accepted commit `cea46f5f`，仍须确认是否集成。O17 是 form 单函数真源，O05 不能再建第二份。
- O14/O15 的 published state guard 依赖 O12 同版公司/source 单 batch 与可信 COMPLETE tombstone；O18 amended 行为依赖 O12/O14/O15。用户已定同字节仅切 amended：无 `--overwrite` metadata-only 保留内容版本；带 `--overwrite` 强制重新转换并发布，版本按既有指纹规则保持。
- O20-F02 按受控 XBRL 支持推进：补齐 Docling/Arelle、taxonomy 和 OS 隔离，验证有效 instance，经 Docling 转换并登记 manifest 才算成功；Docling 抽取正确性归上游。纯合成 typed-member 崩溃已报上游 #4437。O21/O22 typed content failure、O33 同 identity 并发均有依赖，见主队列。
- CNInfo 公开 `filing_date` 用户已定按中国本地披露日，仅修新发现/新下载；历史已发布迁移另议。它是 #198 验证中发现的独立 WU，不要改写 #198 S2 通过结论。

## 4. 外部子 Agent 与门禁合同

**用户指定的派发与裁决合同**：使用 `$sub-agents`，通过 `claude-agent-run` / `codex-agent-run` **runner 子进程**派发外部 Agent；你自己担任总控并作最终裁决。`gpt-6-sol` 负责 plan、implement、fix；`mimo` 与 `ds-flash` 负责**两路同时并行、彼此独立的 review**。每一次调用都必须显式传入 `--cwd <workspace 绝对路径>`，使用该次调用独立的 output 与 stderr 文件（Codex 另有独立 last-message，验证任务另有 canary），唯一 label/instance；不得依赖默认 cwd 或共用输出文件。先运行 `sub-agent-preflight` 并确认 `setup_status=ok`，再按 skill 以独立子进程调用派发。总控逐路检查进程 exit、JSON/JSONL 结构化 terminal、失败事件、stderr 白名单、canary 逐字匹配、工具成功证据及实际 artifact，核查代码/测试后**自行裁决**；Agent 自述或两路一致意见都不能代替总控 gate pass。只允许一次有理由的同 provider 修复性重试，再失败切换路线并登记。并行 review 使用不同干净 clone/worktree，不允许写冲突。

每个 WU 按 Gateflow 的 goal→plan/双路 review→实施/双路 review→aggregate deepreview→draft PR 复审→final closeout 顺序推进；accepted finding 先 Sol 修复后同版双路复审。每次代码改动补测试、跑受影响 pytest 和全量 pyright，按根 `AGENTS.md` 判断 README 更新；单文件覆盖率目标 ≥80%。只 stage 当前 gate 授权路径，先 `git diff --cached --check`。所有闭环代码、评审证据和必要 handoff 文档进入同一个 PR #197；不要新开 PR、mark ready 或 merge，用户手工 merge。

## 5. 停止与汇报

遇到 owner/contract/schema 的真正阻断、用户未授权的外部 comment/issue/merge 动作，按 Gateflow 停下并说明已完成的可审结果。不要因模型容量或上下文压缩丢失修复清单；先回读主队列与独立 adjudication 再接续。每个 WU 完成时汇报目标、实际代码、测试/pyright/CLI 证据、findings、风险、PR #197 head 与下一个入口，所有本地 artifact 用可见的**完整绝对路径**。完成所有授权 WU 后汇总，等待用户手工 merge。
