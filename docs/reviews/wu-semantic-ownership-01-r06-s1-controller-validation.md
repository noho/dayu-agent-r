# WU-SEMANTIC-OWNERSHIP-01 R06-S1 Controller Validation

## 1. 结论

**PASS / READY_FOR_DUAL_CUMULATIVE_REVIEW**

本次验证只判断 accepted R06 plan 的 S1 累计 checkpoint，不把全仓尚未传播的 S2/S3 breaking-cutover 错误误判为 S1 finding，也不授权 S2/S3、README、accepted commit、push 或 PR。

S1 的 transaction owner、required explicit batch、publication guard、published/private read boundary、delayed opener、测试 allowlist和逐文件覆盖目标均成立。初验发现的 `R06-S1-VF-01..03` 与修复后复验发现的同源补充项 `R06-S1-VF-04` 已全部在 storage owner boundary 关闭；当前 accepted validation finding 为 0。

## 2. 独立验证证据

- Implementation entry HEAD：`d048adf7ec1135aaf575384432ebf1137f8a34f2`；无 staged diff。
- Diff scope：15 个 accepted S1 production 文件、4 个 accepted S1 test 文件和 implementation artifact；未修改 S2/S3、README、control/design truth 或其它产品范围。
- Focused owner matrix：`103 passed, 61 deselected, 3 warnings`。
- 四个授权测试文件完整矩阵：`201 passed, 3 warnings`。
- 逐 changed production file line coverage：`82%` 至 `100%`，全部 `>=80%`；最低 `_fs_source_document_core.py 82%`、`_fs_storage_infra.py 83%`。
- Scoped Ruff：`All checks passed!`。
- 在 `source .venv/bin/activate` 环境运行 scoped pyright：`0 errors, 0 warnings, 0 informations`。
- 全仓 pyright：`110 errors`；逐条落在 S2/S3 尚未迁移的 producer/callback/test-double，changed S1 owner 和四个授权测试文件无命中，不登记为 baseline。
- 全仓 Ruff：`160 errors`，较 accepted entry baseline `162` 减少 2 项；减少项是 touched owner 的旧 unused import，没有新增/扩散。
- ambient authority scan：0 命中。
- `git diff --check`：pass。

## 3. Accepted validation findings

### R06-S1-VF-01 — malformed recovery ticker 会中止整轮恢复

- 严重性：high。
- 直接证据：`_recover_single_batch_dir()` 在读取不可信 journal 后直接执行 `_normalize_ticker(ticker)`；`_recover_orphan_backup_dirs()` 对由目录名解析出的 ticker 也直接执行 `_normalize_ticker(ticker)`。两处 `ValueError` 都未投影为 `skip/preserve` action，因而一个损坏或恶意 ticker 可中止整个 `recover_orphan_batches()`，阻止后续合法 orphan 被恢复。
- Owner：`dayu/fins/storage/_fs_storage_infra.py` recovery input validation boundary。
- Required fix：在 recovery owner 内把 invalid ticker 作为 fail-closed evidence 处理，保留对应目录、不接触 published tree，并继续扫描其它 orphan；不得放宽 normalizer、吞掉无关 I/O 错误或在 caller/fake 中补偿。
- Required tests：至少覆盖 invalid journal ticker、invalid orphan-backup ticker，以及同轮后续合法 orphan 仍被恢复；断言 invalid evidence 保留且 published tree 未被改写。

### R06-S1-VF-02 — 本次改动函数的中文 contract docstring 不完整

- 严重性：medium / repository hard constraint。
- 直接证据：本次新增或改变 public contract 的多处方法仍只有一句摘要，例如 `CompanyMetaRepositoryProtocol.upsert_company_meta()`、`SourceDocumentRepositoryProtocol.has_staged_filing_xbrl_instance()`、多个 required-`batch` mutation protocol/wrapper，以及 `FsBatchingRepository.commit_batch()`；docstring 未列出 Args/Returns/Raises，也未说明新增 required `batch`。
- Owner：本次 S1 改动函数本身及其 protocol/public wrapper contract。
- Required fix：审计 15 个 changed production 文件中所有本次新增或修改签名/行为的函数和方法，补齐中文概览、Args、Returns、Raises；required `batch`、published/staged read 与 lifecycle 终态异常必须在其 owner contract 中准确说明。不得扩大到未触及模块的机械文档重写。
- Required validation：scoped Ruff、scoped pyright、focused/full S1 tests、coverage、diff-check 和 source scans复跑；文档改动不得改变 S1/S2/S3 scope。

### R06-S1-VF-03 — writer lock release 可覆盖 commit/rollback 主异常

- 严重性：high。
- 直接证据：`commit_batch()` 的 pre-commit failure 分支先调用 `_close_active_batch(state)` 再重新抛出 `commit_error`；`rollback_batch()` 也在已有 `rollback_error` 时于 `finally` 调用 `_close_active_batch(state)`。`_close_active_batch()` 直接释放 writer token，release 失败会先抛出并覆盖原始 commit/rollback failure，与 accepted plan 的 primary-cause preservation stop condition 冲突。
- Owner：storage transaction lifecycle / terminal cleanup boundary。
- Required fix：capability 和 registry 仍必须终态消费；writer release failure 必须被保留为 note/cause/diagnostic，不能覆盖更早的 authoritative operation failure。没有更早主异常时，release failure 仍应按明确 contract 抛出。补 owner-level failure injection tests，分别证明 commit primary failure 与 rollback journal primary failure不被 writer-release failure替换。

### R06-S1-VF-04 — committed publication-guard release failure 被静默为 success

- 严重性：high。
- 直接证据：`commit_batch()` 的 publication token release 分支在 `state.phase == COMMITTED` 且没有更早 `commit_error` 时只写 warning，随后 cleanup/close 并正常返回；但修复后的 protocol/core contract 已明确承诺“没有更早 operation error 时 publication/writer lock release failure 抛出”。静默成功还可能隐藏仍阻塞 published readers 的 guard-release 故障。
- Owner：storage commit terminal outcome / lock-release error precedence boundary。
- Required fix：`COMMITTED` durable truth 不得回滚，capability/registry 仍必须终态消费，writer release 仍必须尝试；publication release failure 必须作为 post-commit primary error 返回给 caller，而不是静默。若同时发生 cleanup/writer release failure，按发生顺序保留 primary identity并附着 secondary diagnostic。补 owner-level failure injection test，断言已发布新树保持、token 已终态、同一 primary release error 被抛出且没有调用 pre-commit rollback。

## 4. Validation-fix revalidation

### 4.1 Finding closure

- `R06-S1-VF-01`：closed。malformed journal/backup ticker 只在 recovery input-validation boundary 捕获 `ValueError`，保留 invalid evidence、不触碰其 published tree，并继续同轮后续合法 orphan；跨平台 backup fixture 由合法目录组件 `...bak.<token>` 解析出必被拒绝的 ticker `..`。
- `R06-S1-VF-02`：closed。15 个 changed production 文件的所有函数均有中文概览及 `Args/Returns/Raises`；AST 独立复核结果为 `[]`，required-`batch`、published/staged read 与 lifecycle/post-commit terminal contract 均由 protocol/core/wrapper 同源说明。
- `R06-S1-VF-03`：closed。registry/capability 先终态消费；已有 commit/rollback primary 时 writer-release failure 只附着 note/diagnostic，无 primary 时独立抛出。双重 failure-injection tests 保持 primary exception identity。
- `R06-S1-VF-04`：closed。`COMMITTED` 后 publication-release failure 成为 post-commit primary 原对象；不调用 pre-commit rollback，durable new tree 保持，cleanup 与 writer-release failure 按发生顺序附着，capability/registry 仍终态消费。

### 4.2 Controller independent evidence

- Focused owner matrix：`108 passed, 61 deselected, 3 warnings`。
- 四个授权测试文件完整 coverage matrix：`206 passed, 3 warnings`。
- 逐 changed production file line coverage：`82%` 至 `100%`，全部 `>=80%`；最低 `_fs_source_document_core.py 82%`，`_fs_storage_infra.py 88%`。
- Scoped Ruff：`All checks passed!`；scoped pyright：`0 errors, 0 warnings, 0 informations`。
- Full Ruff：`160`，低于 accepted entry baseline `162`，无 changed-scope 命中或新增/扩散。
- Full pyright：仍为预期累计 `110 errors`，全部属于 S2/S3 尚未传播的 producer/callback/test-double；不登记为 baseline，无 compatibility shim。
- Source scans：ambient `0`、S2 ack `59`、lifecycle `168`、mutation `165`、locator `118`；新增 lifecycle/locator 命中只来自 owner failure-injection tests，public token/journal 仍无 physical locator。
- Touched-function AST contract scan：0 gap；public core read self-call scan无命中。
- Exact implementation scope：15 个 S1 production 文件、4 个 S1 tests、implementation artifact 与 validation-fix artifact；Controller control/validation 文件独立识别。无 S2/S3、README、design 或其它产品范围 diff。
- `git diff --check`：pass；staged diff为空；HEAD仍为 `d048adf7ec1135aaf575384432ebf1137f8a34f2`。

## 5. Gate decision

当前 gate 转为 **R06-S1 dual cumulative code review**。AgentMiMo / AgentDS 必须独立审查从 `d048adf7ec1135aaf575384432ebf1137f8a34f2` 到当前未暂存累计 tree 的完整 S1 代码、测试、implementation/fix evidence 与 accepted plan conformance，特别审查 transaction authority、recovery、writer/publication 锁序、public/private read graph、delayed opener、pre/post-commit error precedence、测试是否固化 private layout，以及未越界进入 S2/S3/R07。S1/S2/S3 仍是同一 R06 breaking cutover 的累计 working tree，不生成中间 accepted commit；S2 未授权。
