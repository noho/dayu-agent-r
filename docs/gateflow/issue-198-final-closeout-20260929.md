# Issue #198 final closeout（待 issue 评论授权）

## Gate 状态与目标

- Work unit：GitHub issue [#198](https://github.com/noho/dayu-agent-r/issues/198)，范围为 Fins download 的 typed source integrity 公共失败投影/partial publication 守恒（S1）与真正未知 download 的安全 operator 诊断及 CLI 日志定位（S2）。
- 已通过：goal、plan/双路 review、S1/S2 实施及双路 code review、整项双路 aggregate deepreview、合入既有 draft PR #197 后双路 PR re-review、accepted PR review commit、final push、`draft-PR-pass`。
- 当前：`final closeout` 的本地证据已备妥；`$gateflow` 要求给 issue 添加 closeout comment，且该外部 comment 需要用户额外授权。**评论未获授权/未发出前不得记 `final closeout pass` 或 `work unit completed`。**

## 改动与验证

- S1：storage 完整性预检的封闭 `reason_code` 由 Fins 失败 owner 同源投影到 direct、CLI、wait；job 存安全摘要，partial publication 不被误判成功。S2：未知 download 异常只在 operator 日志留下有界脱敏类型指纹与包内位置，公开失败不泄漏原异常；CLI 使用唯一日志文件指引。PR review F1 把 `safe_exception_trace` 的昂贵受信帧校验限制到最终 16 帧，owner 测试断言校验集合与顺序。
- S1 accepted commit `7234d42dbaea603112c6fed52776281228d261a7`；S2 accepted commit `2643de25d6258fe2d83b527ea3823ffa3eb19bff`；整项 aggregate accepted commit `cc6ee444fba62ff128fd01d97263a6c53efe5bc7`；PR 受控 merge commit `2219d40b662ae7336dfbcaf62e5fdeb2ab9fa6d7`；accepted PR review commit `c37b71ee1a271e22c3a2330a0fb88bcd32f6aab4`。PR 原有增量没有被强推覆盖。
- 受影响八文件在隔离 editable Python 3.11 venv 中 **863 passed**；`dayu/runtime.log` owner 118 passed、单文件 coverage **94%**；全量 `pyright dayu/ tests/ utils/` **0 errors**。两路独立 r2 复审均锁同一修订快照，F1 修前 owner 测试精确失败、修后通过；七组异常输出 A/B 逐字节一致，受信深栈路径解析计数由 183 降为 48（61 帧例），外部帧在路径解析前早退。没有全仓测试/CI 通过的声明。
- fresh 隔离 CLI：2025-03-27..31 真实 CNInfo→Docling→manifest 一份成功；注入根外来文件时 typed `storage/unsafe_publication` 失败；清除后 integrity-complete skip 恢复。精确 2025-03-28 单日 0 候选是独立 CNInfo 日期 WU。证据在 `issue-198-s2-cli-fresh-evidence-20260929.md`。
- README 职责核对：S1/S2 已更新根 README、Fins README 与 tests README；PR F1 仅变更层中立 runtime helper 和 owner 断言，不触发上述 README 的新增读者内容。审查与验证 artifact 已纳入 PR。

## Findings 与剩余 owner

- PR-R1/F1 低／accepted／**已修复**；PR-R1/F2 低／`rejected-with-reason`（显式 import 不依赖 `__all__`）；PR-R1/F3 低／accepted／**已修复**（普通文本 `Closes #198`）；PR-R2/F1 低／accepted 文档精度／**已修复**（I/O 随受信 Dayu 帧数增长）。两路 r2 无新 material finding。首次 MiMo、ds-flash 审查和 Sol fix 的结构化协议失败保留作审计，未充当有效 gate。
- 其它残余按主队列归独立 WU：`fins-direct-projection-failsafe`、`fins-source-integrity-reason-constructor-invariant`、`fins-download-storage-sibling-errors`、`fins-other-raw-diagnostics-audit`、`fins-download-no-source-retry-hint`、`fins-download-indeterminate-publication-state`、`fins-download-other-source-summary-conservation`、`fins-cancellation-coverage-order-sensitivity`、CNInfo 中国本地披露日/单日查询。它们不改变 #198 的本次验收范围；各项 owner、证据与依赖见 `upload-material-issue-198-repair-sequence-20260928.md`。
- 跨安装布局可能将受信帧保守降级为 `[external]`，真实取消竞争仍缺直证；无 CI checks，线上 `statusCheckRollup=[]`。这些是已分类残余，不冒充当前 #198 代码 gate 失败。

## PR 与 issue 关联

- Draft PR：[ #197 ](https://github.com/noho/dayu-agent-r/pull/197)，base `main`、head `codex/upload-material-oracle`，用户手工 merge。2026-09-29 线上 readback：OPEN/draft/mergeable，head `c37b71ee1a271e22c3a2330a0fb88bcd32f6aab4`，CI checks 空。
- PR body 有唯一普通文本 `Closes #198`；GitHub GraphQL `closingIssuesReferences` 已读回 OPEN issue #198。用户 merge 后应由 GitHub 自动关闭；当前不得主动关 issue。
- 推送 `c37b71ee` 的远端写入成功并经 `git ls-remote`/`gh pr view` 双重证实；共享 `.git` 内本地远端跟踪 ref 的 lock 更新受权限阻挡，不影响 PR 远端 head。
- **Issue closeout comment：待额外用户授权。** 拟发布内容如下，获授权后用临时 body file 提交并读回 URL/body，再将本段改为已发布并记录 comment URL。

> #198 的 S1/S2 已完成并进入 draft PR #197：https://github.com/noho/dayu-agent-r/pull/197 。S1/S2、整项 aggregate deepreview 和 PR 双路复审已通过；受影响 863 项测试通过、pyright 0 errors，真实隔离 CLI 已验证成功发布、typed 完整性失败及恢复。PR review 的 F1/F3 已修复，F2 有证据驳回，F1 论证精度已更正；没有未裁决的 #198 finding。其它独立残余与 owner 见 PR 中 `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`（包括 direct failsafe、其它 storage 分类、CNInfo 中国本地披露日等），不计入本 issue 的 S1/S2 范围。PR body 有 `Closes #198`；issue 目前保持 OPEN，用户手工 merge PR 后预计由 GitHub 自动关闭。

## 下一入口与停止点

- 当前用户要求完成 #198 后停下；不启动下一 WU。给下一位 Agent 的指令是 `docs/upload_material_repair_handoff_prompt_3.md`，以主队列实时依赖和 PR head 为准选择下一项。
- 若用户批准上述 comment：发布、读回、把本文件和主队列更新为 `final closeout pass / work unit completed`，仅提交/推送这些文档，不再修改产品代码，然后停止并汇报。若未获批准：保持 `final closeout pending external comment`，已通过的 PR 和代码门禁不倒退。
