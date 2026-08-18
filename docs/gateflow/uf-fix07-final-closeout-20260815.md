# UF-FIX07 final closeout

## Completion status

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- 日期：2026-08-15
- Branch：`codex/upload-filing-oracle`
- Accepted deepreview commit：`4ad5a31f`
- 状态：`FINAL CLOSEOUT PASS / WORK UNIT COMPLETED`
- 工作树：closeout artifact 提交后应为空
- Next entry point：无当前 work unit 必做项；后续如获独立授权，可进入真实 evidence work 或已登记的 UF-FIX08/10/11

## What changed

- ingestion static admission 在 converter、workspace mutation 与 publication 前统一拒绝超过 100 个文件、重复规范路径、非法 action/file
  组合，以及多文件 primary 缺失/多个 selector/集合外 selector；单文件唯一文件自动成为 primary；
- `FinsUploadFilingFiles` 成为 validated primary/companions 的严格类型真源，CLI、Service、workflow 与 storage 传递同一事实；
- original assets 使用规范路径派生的无碰撞 identity 并保留 `original_filename`；primary derived assets 精确关联 original identity；同 basename
  或同 stem 不同后缀可原子共存；
- 只有 authoritative primary 执行 Docling 与 downstream `process_filing`，companions 只按 UF-FIX06 contract 原样保存；
- filing primary 持久化并由 storage primary accessor 精确消费，禁止下游按输入顺序、文件系统顺序、basename/stem 或已生成文件反推；
- publication 继续保持整批原子 prepared mutation，转换/publication 失败时零部分发布、stored count 为零；
- Service fingerprint owner 使用 single-file v1 / role-aware multi-file v2 typed contract，修复 primary flip 被错误 identical-skip；对 descriptor
  无法区分角色的 ambiguous case 保守禁用 skip；
- help、tool schema、CLI 错误、根 README、Fins README 与 tests README 已同步用户和维护者所需的 contract。

## Verification

- fingerprint owner focused suite：80 passed；
- 13-file affected suite：1366 passed，1 skipped，3 warnings；
- 全仓 `python -m pyright dayu/ tests/ utils/`：0 errors，0 warnings，0 informations；
- 六个修改生产文件 branch coverage：88% / 89% / 99% / 81% / 92% / 87%，全部达到 80% 门槛；
- UF-FIX07 scope `git diff --check 64050349..HEAD`：PASS；
- `docs/cli_ci_oracles.json` 与 `docs/cli_ci_scenarios.json` 相对 `64050349`：无 diff；
- 最终双路 aggregate closed-set review：AgentMiMo `code-review-20260815-230205.md` PASS；AgentDS
  `code-review-20260815-230207.md` PASS、无 findings。

Reviewer 曾执行全仓 tests，结果为 `7704 passed, 9 failed, 10 skipped, 6 deselected`。9 个 failure IDs 中 8 个在 base
`64050349` 稳定复现，另一个 host watchdog 用例在 base 与移除当前 working diff 的 HEAD 均通过、属于 unrelated flaky；相关路径均不在
本 work unit diff，已归类给 host/service/CLI owner，未用当前修复掩盖。

## Docs decision

- 根 `README.md`：更新最终用户 CLI primary、静态 usage failure、collision-free/primary-only/atomic 语义；
- `dayu/fins/README.md`：更新 validated request、asset identity、storage/downstream primary 与 role-aware fingerprint owner contract；
- `tests/README.md`：更新 deterministic owner coverage 与 affected validation 命令/事实；
- 未触及 `dayu/engine/`、`dayu/host/` 或分层装配边界，因此不修改 Engine/Host/Dayu README。

## Finding status

- aggregate correctness findings 2 项：全部已修复并双路 re-review 通过；
- aggregate/re-review LOW findings 3 项：owner guard coverage、全仓 failure 证据精度、证据来源回引全部已修复；
- slice reviews 与 aggregate closed set 中没有 blocking、deferred、部分修复或证据失效 finding。

## Remaining risks / owners

- primary/companion descriptor 完全相同时，当前 owner fail-closed 禁止 identical-skip，可能产生 version churn；这是避免保存错误 primary 的
  accepted conservative boundary；
- 旧无角色 multi-file digest 首次按 v2 upsert 会更新版本；不引入 dual-read、compatibility shim 或旧 schema auto repair；
- UF-FIX08 existing-source auto repair、UF-FIX10 concurrency、UF-FIX11 company meta warning：由各自后续 work unit 负责；
- optional real Docling 与 UF-PF07/UF-PF12：未执行，等待独立 evidence 授权；
- registry、oracle/scenario 和 frozen evidence：保持只读，仍记录第一轮真实观察，等待后续 evidence work。

## PR / issue status

- Draft PR URL：`N/A`。用户明确要求在当前分支提交且不创建 PR；因此 `ready-to-open-draft-PR -> draft-PR-pass` 链按用户显式约束
  不执行；未 push、未创建 PR、未做 PR review；
- Issue link：`N/A`。`UF-FIX07` 是本地 scenario registry repair item，不是已给定编号的 GitHub issue；本轮按约束未修改 registry；
- Issue closeout comment：`N/A`。没有外部 issue 授权或目标，不发送外部 comment。

UF-FIX07 已在当前本地分支完成实现、验证、双路 review、protected commits 与职责内文档更新；当前 work unit completed。
