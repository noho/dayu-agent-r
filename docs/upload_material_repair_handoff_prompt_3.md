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

#198 已通过 final closeout。用户已指示上一 Agent 到此停止；**新 Agent**接手后按主队列依赖顺序选择**下一个 eligible WU**，从该 WU 当前**下一个未完成 gate**继续，不回退已通过 gate，不把 plan 候选当产品修复。候选顺序要由当前依赖重新裁决：

- 点号元数据与 UM-O03 的闭环增量此前已在 PR #197；核实时以线上 commit 与 review artifact 为准，不重复实施。
- O04/O23 统一资产规划与文件名→Docling 文件名函数是 O25 primary 选择的前置；隔离工作树和审查结果见主队列，已有候选修复/findings 不得漏掉。
- 请求/身份链中的 O05/O06/O09/O10/O11/O12/O16/O17 须按唯一 canonical form、日期与 company/source 身份 owner 的依赖顺序集成。O06 用户已选 `material_name` trim 后最多 240 Unicode 码点；O11 另有本地 accepted commit `cea46f5f`，仍须确认是否集成。O17 是 form 单函数真源，O05 不能再建第二份。
- O14/O15 的 published state guard 依赖 O12 同版公司/source 单 batch 与可信 COMPLETE tombstone；O18 amended 行为依赖 O12/O14/O15。用户已定同字节仅切 amended：无 `--overwrite` metadata-only 保留内容版本；带 `--overwrite` 强制重新转换并发布，版本按既有指纹规则保持。
- O20-F02 按受控 XBRL 支持推进：补齐 Docling/Arelle、taxonomy 和 OS 隔离，验证有效 instance，经 Docling 转换并登记 manifest 才算成功；Docling 抽取正确性归上游。纯合成 typed-member 崩溃已报上游 #4437。O21/O22 typed content failure、O33 同 identity 并发均有依赖，见主队列。
- CNInfo 公开 `filing_date` 用户已定按中国本地披露日，仅修新发现/新下载；历史已发布迁移另议。它是 #198 验证中发现的独立 WU，不要改写 #198 S2 通过结论。

## 4. 外部子 Agent 与门禁合同

按用户指定：gpt-6-sol 负责 plan、implement、fix；MiMo 与 Kimi 做两路并行独立 review，Kimi 因额度不足失败时可用 ds-flash 备份。所有外部 runner 调用必须显式 `--cwd` 工作区**绝对路径**、每次唯一 label/instance、独立 output/stderr/last-message/canary；先 `sub-agent-preflight` 且 `setup_status=ok`，再以独立提权调用派发。总控检查 process exit、JSON/JSONL terminal、失败事件、stderr 白名单、canary 逐字匹配、工具成功证据及实际 artifact，自己裁决；代理自述不能代替 gate pass。只允许一次有理由的同 provider 修复性重试，再失败切换路线并登记。并行 review 用不同干净 worktree，不允许写冲突。

每个 WU 按 Gateflow 的 goal→plan/双路 review→实施/双路 review→aggregate deepreview→draft PR 复审→final closeout 顺序推进；accepted finding 先 Sol 修复后同版双路复审。每次代码改动补测试、跑受影响 pytest 和全量 pyright，按根 `AGENTS.md` 判断 README 更新；单文件覆盖率目标 ≥80%。只 stage 当前 gate 授权路径，先 `git diff --cached --check`。所有闭环代码、评审证据和必要 handoff 文档进入同一个 PR #197；不要新开 PR、mark ready 或 merge，用户手工 merge。

## 5. 停止与汇报

遇到 owner/contract/schema 的真正阻断、用户未授权的外部 comment/issue/merge 动作，按 Gateflow 停下并说明已完成的可审结果。不要因模型容量或上下文压缩丢失修复清单；先回读主队列与独立 adjudication 再接续。每个 WU 完成时汇报目标、实际代码、测试/pyright/CLI 证据、findings、风险、PR #197 head 与下一个入口，所有本地 artifact 用可见的**完整绝对路径**。完成所有授权 WU 后汇总，等待用户手工 merge。
