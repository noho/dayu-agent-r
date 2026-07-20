# WU-SEMANTIC-OWNERSHIP-01 R06-S1 validation-fix checkpoint

## 1. 身份、输入与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 validation fix。
- Accepted plan commit：`0d802220fd1ca4ec67addc85915df27becc9b594`。
- Implementation entry HEAD：`d048adf7ec1135aaf575384432ebf1137f8a34f2`。
- Controller 输入：`docs/reviews/wu-semantic-ownership-01-r06-s1-controller-validation.md` 中 R06-S1-VF-01..04；control gate 已由 Controller 转为 R06-S1 validation fix。
- 本 follow-up 只修复 VF-01..04，不进入 S2 complete-source validator/blob-first/ack cutover，不进入 S3 producer/callback/composition propagation。
- 本实现仍只触及 S1 的 15 个 production files、4 个 test files，更新原 implementation artifact，并新增本 artifact。Controller 自有的 control diff 与 validation artifact 保持原样；未修改 design、README 或其它 review artifact。
- checkpoint 未 stage、commit、push 或创建 PR。

## 2. 第一性原理与 owner 判定

四个 finding 均成立，且必须在 storage owner boundary 修复：

1. recovery 消费 journal ticker 与 orphan-backup 目录名，这些都是不可信 durable input。normalizer 正确地 fail closed，但 recovery orchestrator 没有把业务输入无效与整轮 recovery 失败区分开，单个 malformed evidence 因而阻断后续合法 orphan。input-validation owner 应保留无效证据、禁止触碰其 published tree、记录 skip/preserve，并继续扫描。
2. required batch、published/staged read 和 terminal lifecycle 是 S1 新 public contract。缺失的 Args/Returns/Raises 会让 owner 的异常和可见性承诺不完整；正确位置是本次触及的 protocol/core/wrapper 方法，而不是调用方或 README 的补偿描述。
3. commit/rollback operation error 是 transaction 的 authoritative primary cause。writer token release 是 terminal cleanup；它必须执行且 registry 必须消费，但 secondary release failure 不能替换已存在的 primary。没有 primary 时，release failure 才是调用方应收到的 authoritative failure。
4. ``COMMITTED`` 是 durable truth，但不等于 terminal API 必须返回 success。publication guard release failure 可能继续阻塞 readers，必须成为 caller 可见的 post-commit primary；同时不得把它误送入 pre-commit rollback。后续 cleanup/writer release 仍执行，其失败只能附着到发生更早的 publication primary。

## 3. VF-01：recovery fail-closed continuation

### 3.1 实现

- `_recover_single_batch_dir` 在 journal exact-field/type 检查后，仅围绕 `_normalize_ticker(ticker)` 捕获 `ValueError`。
- invalid journal ticker 时不获取 ticker writer/publication lock、不派生或触碰 published tree、不删除 transaction evidence；记录 `skip batch transaction=<name> reason=invalid_journal_ticker`，然后返回，由外层继续后续 evidence。
- `_recover_orphan_backup_dirs` 解析 backup directory name 后，仅围绕 ticker normalization 捕获 `ValueError`。
- invalid backup ticker 时不派生或触碰 published tree、不删除 backup；记录 `preserve backup directory=<name> reason=invalid_backup_ticker`，然后 `continue` 扫描。
- normalizer 未放宽；捕获范围不包含 journal read、目录扫描、lock acquire、rename、fsync 或 cleanup，因此无关 I/O error 不会被吞掉。

### 3.2 Owner tests

- invalid journal ticker：journal 写入 `../MSFT`，同时保护 published MSFT sentinel；同轮再布置合法 AAPL orphan。断言 invalid batch evidence 保留、MSFT published tree 未触碰、skip action 存在，且后续 AAPL orphan 恢复并清理。
- invalid orphan-backup ticker：目录名使用跨平台单路径组件 `...bak.000-invalid-backup`。现有 parser 精确得到 ticker `..`，所有目标平台都可创建该组件，但 `_normalize_ticker` 必然拒绝；测试不依赖反斜杠或 POSIX-only 文件名语义。
- 同轮再布置合法 `MSFT.bak.999-valid-backup`，并保护 published AAPL sentinel；断言 invalid backup 与内容保留、preserve action 存在、AAPL 未触碰、后续 MSFT orphan 恢复并清理。

## 4. VF-02：touched contract docstring 审计

对 15 个 changed production files 中本次新增或修改签名/行为的方法执行 AST 与人工语义审计：

- 每个触及函数/方法都有中文概览，以及 `Args`、`Returns`、`Raises`。
- 每个带 required keyword-only `batch` 的 contract 都说明 batch 是当前 storage core 的 open capability，并说明 invalid/unknown/cross-core/cross-ticker/terminal capability 的 `ValueError`。
- public published reads 明确默认只读 published tree、publication guard 的持有边界与 `RuntimeFileLockError`；explicit staged XBRL read 明确只观察指定 active transaction staging。
- batching lifecycle 明确 begin 的 writer ownership、commit/rollback terminal consumption、operation/cleanup exception contract。
- `LocalFileSource` 与 typed delayed opener 明确 publication guard 只持到 file descriptor open 成功或失败，后续读取不持 guard。
- 最终 AST 结果：`missing_sections=[]`、`missing_batch_contract=[]`；没有机械扩展 allowlist 外代码。

## 5. VF-03：terminal error precedence

### 5.1 实现 contract

- `_close_active_batch(state, *, primary_error)` 先把 internal lifecycle 置为 closed，再移除 transaction registry 与 per-ticker active index；registry/capability consumption 不依赖 writer release 是否成功。
- 随后尝试 release writer lock token。
- 若没有 earlier primary，writer release failure 原样抛出。
- 若已有 commit/rollback/cleanup authoritative primary，release failure 通过 `BaseException.add_note` 附着到 primary，并写 warning diagnostic；不会替换 primary exception object。
- commit pre-commit error、commit cleanup error 与 rollback error 都显式把 primary 传入 terminal close；成功无 primary 路径仍保留 release failure 可见性。

### 5.2 Failure-injection tests

- commit：注入 target→backup primary `OSError`，同时注入 writer release `RuntimeError`；断言调用方收到同一个 primary object、note 包含 writer release failure，两个 registry index 已移除，token 后续被拒绝。
- rollback：注入 rolled-back journal primary `OSError`，同时注入 writer release `RuntimeError`；断言同样的 primary identity、secondary note 与 terminal registry consumption。
- 测试 finally 使用保存的真实 release primitive 清理 OS lock，避免 failure injection 泄漏测试资源；这不是 business authority 或 compatibility path。

## 6. VF-04：committed publication-release outcome

### 6.1 实现 contract

- `commit_batch` 新增独立 `post_commit_error`，不复用会进入 pre-commit failure/rollback 语义的 `commit_error`。
- publication guard 在 journal phase 已为 ``COMMITTED`` 后释放失败时，将同一个 release exception object 记录为 post-commit primary；durable target 不回滚，也不调用 `_rollback_precommit_batch`。
- cleanup 随后照常尝试；若它失败，通过 exception note 与 warning diagnostic 附着到 publication primary，不替换最早异常 identity。
- `_close_active_batch(..., primary_error=...)` 仍先关闭 lifecycle、移除两个 registry index，再尝试 writer release；writer release failure 继续附着为后续 secondary。
- terminal 最终抛出原 publication release object。若 publication release 正常，则原有 cleanup-primary / writer-only-primary contract 不变。

### 6.2 Owner failure-injection test

单个 owner test 同时注入 publication guard release、post-commit cleanup 与 writer release failure，并断言：

- caller 收到的对象 `is` 注入的 `RuntimeFileLockError`；cleanup/writer 两个 secondary diagnostic 按顺序存在。
- `_rollback_precommit_batch` 从未调用，state phase 保持 ``COMMITTED``，published `state.txt` 保持新版本。
- transaction/ticker registry 均已移除，使用原 token 再次 commit 被拒绝。
- 测试 finally 仅用保存的真实 release primitive 释放被 injection 保留的 OS tokens，不从 public token 推导 locator 或 authority。

## 7. 精确 validation-fix diff

- 行为变更只在 `dayu/fins/storage/_fs_storage_infra.py`：VF-01 recovery input validation/continuation、VF-03 terminal close error precedence 与 VF-04 committed publication-release outcome。
- owner behavior tests 只在 `tests/fins/test_fins_storage_atomicity.py`：两个 invalid recovery cases、同轮合法 continuation、两个 pre-commit/rollback dual-failure cases，以及一个 post-commit triple-failure case。
- VF-02 仅在既有 15 个 changed production files 补齐本次 touched function/method contract docstrings，没有扩大 production allowlist。
- 更新 `docs/reviews/wu-semantic-ownership-01-r06-s1-implementation-codex.md`，新增本 artifact。
- 当前累计 production + tests 精确为 19 files、`+5230/-1398`；Controller control diff 不计入本实现统计。

## 8. 验证证据

### 8.1 Tests

- Plan §7.1 focused：`108 passed, 61 deselected, 3 warnings in 3.23s`。
- 四个允许 test files 完整 coverage session：`206 passed, 3 warnings in 10.16s`。
- warnings 均为第三方 `edgar` deprecated import，不是本次新增失败。

### 8.2 Changed production line coverage

coverage JSON：`/tmp/dayu-r06-s1-vf-coverage.json`；全部 15 个 changed production files 达到 `>=80%`。

| 文件 | covered/statements | coverage |
| --- | ---: | ---: |
| `document_models.py` | `384/399` | `96%` |
| `_fs_blob_core.py` | `54/58` | `93%` |
| `_fs_company_meta_core.py` | `115/119` | `97%` |
| `_fs_maintenance_core.py` | `133/145` | `92%` |
| `_fs_processed_core.py` | `110/117` | `94%` |
| `_fs_source_document_core.py` | `378/460` | `82%` |
| `_fs_storage_infra.py` | `576/650` | `89%` |
| `fs_batching_repository.py` | `17/18` | `94%` |
| `fs_company_meta_repository.py` | `18/18` | `100%` |
| `fs_document_blob_repository.py` | `20/20` | `100%` |
| `fs_filing_maintenance_repository.py` | `29/29` | `100%` |
| `fs_processed_document_repository.py` | `26/26` | `100%` |
| `fs_source_document_repository.py` | `71/79` | `90%` |
| `local_file_source.py` | `20/20` | `100%` |
| `repository_protocols.py` | `60/60` | `100%` |

### 8.3 Static validation

- Scoped Ruff（15 production + 4 tests）：`All checks passed!`。
- Full Ruff read-only delta：`Found 160 errors`，低于 accepted entry baseline 162；changed files 无命中、无新增/扩散。
- Scoped Pyright（15 production + 4 tests）：`0 errors, 0 warnings, 0 informations`。
- Full Pyright：`110 errors, 0 warnings, 0 informations`。这些均为 S1 明确禁止迁移的 S2/S3 consumers/producers/test doubles：required batch 尚未传播、Source lifecycle 调用待拆分、override/callback 待迁移或旧 token shape 待迁移；changed owner 与四个允许 tests 为 0。未添加 optional/default、compat、`type: ignore`、cast 或 fake token，也未把 110 项登记为 baseline。

### 8.4 Scans、diff 与 allowlist

- ambient authority scan：0。
- S2 ack scan：59，全部 deferred；未提前删除 incomplete acknowledgement 或实施 complete-source/blob-first cutover。
- lifecycle scan：168；增加项来自 VF-03/VF-04 tests 的显式 commit/rollback 与 consumed-token retry，changed storage lifecycle 定义只在 batching protocol/wrapper 与 infra internal owner。
- mutation propagation scan：165；changed files 已显式 `batch=`，其余为 deferred S3 propagation。
- locator scan：118；新增项为 recovery owner tests 对 internal filesystem evidence 的断言。public token/journal 均无 physical locator，tests 不从 public token 推导 staging/backup 布局。
- public core read scan：无 public-to-public read 调用；outer guarded entry 仍只获取 publication guard 一次。
- `git diff --check` 与两个 untracked Codex artifacts 的 no-index check：通过。
- allowlist：本实现精确为 15 production + 4 tests + 2 Codex artifacts；Controller 自有 control/validation paths 单独识别并保持原样，无其它路径。
- staged diff：空；HEAD 保持 implementation entry commit。

## 9. README、安全保留与 residual

- README 不修改：用户与 S1 allowlist 明确禁止；而 S2 ack cutover 与 S3 producer/composition 尚未完成，此时同步会把累计中间状态误写成 final public workflow。README 更新 deferred 到 accepted final cumulative slice。
- ticker/path normalization、root containment、symlink refusal、atomic journal/rename/fsync、writer/publication 独立锁序与 delayed opener 短锁窗均保留。
- VF-01 只处理业务 input `ValueError`，不吞 I/O；invalid evidence fail closed，合法 evidence 继续。
- VF-03 既不丢 authoritative primary，也不静默无-primary release failure；registry consumption 先于 release，避免 stale authority。
- VF-04 保留 ``COMMITTED`` durable tree，不把 post-commit release failure 静默成 success，也不误触发 rollback；后续 terminal failure 只作为 secondary diagnostic。
- residual 仍仅为 accepted S2/S3 迁移和全仓 110 个相应 pyright error；没有把 residual 变成 S1 compatibility code。

## 10. Stop condition

VF-01..04 已实现并通过 owner tests、四文件完整 tests、逐文件 coverage、scoped Ruff/Pyright、full delta attribution、source scans、diff-check 与 allowlist 审计。本实现停在未暂存累计 working-tree checkpoint，等待 Controller 复验；不继续 S2/S3，不 stage/commit/push/PR。
