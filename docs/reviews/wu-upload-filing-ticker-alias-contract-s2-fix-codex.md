# WU Upload Filing Ticker Alias Contract — S2 Fix

## 1. Gate 与边界

- Gate：同一 S2 implementation 的 fix gate。
- 基线：`c5446b770d238aafd8c42552dadbe132cba94ad2`；未提交。
- 输入：完整读取 `code-review-20260815-011944.md`、`code-review-20260815-011809.md` 与 S2 code-review controller adjudication。
- 只处理 controller accepted F1/F2/F3；未重构既有正确 semantic owner、workspace identity lock graph 或 durable layout。
- controller rejected notes 全部保留为 rejected：未新增 durable index/cache，未改变 `_PHASE_STARTED` recovery 语义，未调整 typed corruption catch priority，未改变无真实 mutation 时的 `updated_at`。
- 未触碰 UF-PF05、oracle/scenario registry、冻结 evidence、Host/Engine、其它 finding、PR/push/commit，也未开始 re-review。

## 2. F1 — begin-time existence fail closed

`_FsStorageInfra.begin_batch(...)` 不再用 `Path.exists()` / `Path.is_symlink()` 派生 `publishes_new_corpus`。在 same-ticker writer 持有期间，它调用 storage-owned `_lstat_optional_storage_path(...)`：

- 仅 `ENOENT` 返回 missing；
- `EACCES`、`EIO` 与其它 I/O 原样 fail closed；
- existing non-directory 或 symlink 因 `lstat` mode 不是 directory 而拒绝，不能冻结为新 corpus；
- 只有明确 missing 才令 `_ActiveBatchState.publishes_new_corpus=True`。

`test_begin_batch_lstat_failure_never_reclassifies_existing_corpus_as_new` 对 `EACCES/EIO` 参数化注入一次性 exact-path `os.lstat` failure，断言 errno 保留、错误不泄漏 target path、published tree 的全部相对文件与 bytes 完全相等，并以 retry begin/rollback 证明 writer/active state 正常释放。

## 3. F2 — accepted §11.3 / §11.4 测试矩阵

以下均为本 fix 补充的直接 owner/durable-state 断言，不用 event payload 替代 storage truth。

1. 跨进程 same-canonical：
   - `test_cross_process_same_canonical_stale_intent_preserves_alias_union` 使用 `multiprocessing.get_context("spawn")`，父进程先冻结 stale intent、子进程提交较新同版本事实，最终断言 P2 非身份事实与 `OLD/CHILD/PARENT` stable union。
   - `test_cross_process_same_canonical_changed_but_still_stale_is_rejected` 断言 `CompanyMetaConcurrentUpdateError`、P2 published tree byte-for-byte 不变、PARENT alias 未发布。
   - `test_two_material_processes_on_same_canonical_union_aliases` 同时启动两个真实 `stage_company_meta_for_upload(...)` producer 进程，断言两个 commit 都成功且 durable CompanyMeta 精确保留 `OLD/MAT-A/MAT-B`。
2. `test_existing_corpus_document_only_commit_does_not_take_global_guards` 把 recovery/identity acquire seam 替换为必抛 callable，document-only commit 仍成功，证明只走 target publication guard。
3. `test_alias_resolution_lock_order_is_identity_then_sorted_publications` 记录真实 `_acquire_lock_token(...)` 调用，断言首锁为 `company_identity.lock`、后续全为按 basename 排序的 publication guards，且没有 recovery 或反向顺序。
4. `test_identity_commit_acquire_failures_happen_before_first_replace` 参数化 recovery、identity、sorted scan-publication、最终 target-publication 四个 acquire 点；`_ReplaceDirectoryForbidden` 断言首次 replace 调用数为零，published tree exact bytes 不变。
5. `test_alias_conflict_survives_identity_release_failure_with_bounded_note` 与 `test_alias_conflict_survives_publication_release_failure_with_bounded_note` 断言 `CompanyTickerAliasConflictError` 保持 earliest primary、secondary note 有界且无 workspace path、loser absent、winner tree 不变。
6. `test_swapped_orphan_is_recovered_before_interleaving_conflict_validation` 构造 A 已 physical swap、journal 仍为 `swapped_target` 的真实 evidence，同时 B 已持不同 ticker writer。B commit 先恢复 A 的 OLD alias，再以 typed conflict 拒绝；A exact old tree 恢复、NEW 不可路由、B 不发布。
7. `test_meta_less_canonical_and_healthy_alias_conflict_in_both_directions` 参数化 healthy-first/meta-less-first，两个方向均在 publication 前 typed conflict，winner tree exact 不变且唯一 route 指向 winner。
8. `test_recovery_holds_identity_barrier_across_physical_restore` 在 recovery 第一次 `_replace_directory` 前建立 Event barrier；并发 read 已尝试 identity acquire 但不得完成，放行后只观察 restored OLD route，NEW 不可见。
9. `test_orphan_identity_acquire_failure_preserves_recovery_evidence` 断言 identity acquire failure 前 physical mutation 为零，workspace 全树 bytes、journal token dir 与 backup 均保留；`test_orphan_identity_release_failure_preserves_primary_and_completed_restore` 断言 restore 已完成、release failure 可见、fresh repository 一致读取 OLD、NEW 不可见且已完成 evidence cleanup。
10. `test_list_documents_meta_less_corpus_coexists_with_healthy_alias_corpus` 通过 public batch/source/blob APIs 发布带完整 document 的 DELTA meta-less corpus；`DELTA/delta.us` 返回 exact same documents，`AAPL/APPLE` 保持 exact same healthy corpus，DLTA 不获隐式 alias，DELTA 无 `meta.json`。
11. Failure projection：
   - SEC filing/material：`test_upload_filing_alias_conflict_projects_exact_typed_terminal`、`test_upload_material_alias_conflict_projects_exact_typed_terminal`。
   - CN filing/material：同名两项测试。
   - 四项均先发布真实 MSFT corpus，再让另一 canonical 声明 `MSFT` alias；断言 failed terminal、`stored_file_count=0`、loser absent，以及 exact `storage/ticker_alias_conflict/message/retry_hint/file_label=None`。
   - `test_alias_conflict_failure_is_identical_across_direct_durable_and_observation` 从同一个 `FinsUploadFailureReason` 构造 failed summary，断言 direct RESULT 字段、durable `result_summary["failure"]`、durable `failure_summary` exact JSON 相等，awaiting observation 持有与 direct 相同的 terminal `FinsResultSummary`，且 path/lock key/internal job id 不进入 public observation。

SEC/CN material terminal catch 原先仍直接使用 `str(exc)`，这是补测确认的 owner 缺口。现已与 filing 一样机械调用 `fins_upload_failure_from_exception(...)`，把同一个 bounded reason 同时写入 result `message/failure` 与 terminal `error`；没有新增 mapper 或下游 classifier。

## 4. F3 — awaiting snapshot opacity

`tests/fins/test_fins_ingestion_tools.py` 当前三个 awaiting owner 测试各恰有一条不透明性断言：

- download：`test_download_tool_returns_external_job_awaiting_outcome`；
- preprocess：`test_preprocess_tool_returns_external_job_awaiting_outcome`；
- upload：`test_upload_tool_returns_external_job_awaiting_outcome`。

每项均断言 `"finsjob_" not in outcome.snapshot.snapshot_id`。upload 断言已恢复，download 重复断言已删除。

## 5. README decision

已重新核对根 README、`dayu/fins/README.md`、`tests/README.md` 的更新约束。本 fix 的 F1 是内部 fail-closed 修正，F2 主要补冻结测试矩阵，material mapper 只是兑现 S2 已记录的统一 typed failure contract，F3 仅修测试断言；没有新增用户工作流、CLI 参数、workspace 位置、测试入口或分层关系，因此不再机械修改 README。S2 implementation 已有的必要 README 更新保留。

## 6. Validation

全部命令均在 `source .venv/bin/activate` 后执行。

- fix focused（11 组新增证据 + F1/F3）：`46 passed`。
- 完整 identity owner/storage contract：`35 passed`。
- 最终 full relevant branch run：`coverage run --branch -m pytest -q tests/fins tests/tools/test_combined_tools_acceptance.py` -> `1599 passed, 1 skipped, 3 warnings`；skip 为既有环境条件，warnings 为 `edgar` dependency deprecation。
- 修改生产文件逐文件 branch coverage 全部 `>=80%`；最低为 `_fs_company_meta_core.py` / `fins_tools.py` / `read_runtime.py` 的 `83%`，本 fix 直接修改的 `_fs_storage_infra.py=84%`、`sec_upload_workflow.py=92%`、`cn_pipeline.py=92%`。
- 全量 `pyright`：`0 errors, 0 warnings, 0 informations`。
- 全部 S2 修改 Python 文件 `ruff check`：通过。
- 全部 S2 修改 Python 文件 `ruff format --check`：通过。
- residue：旧 `resolve_existing_ticker`、旧 alias-index helpers、repository `upsert_company_meta` contract、read ticker `upper/normalize` fallback 均无 S2 owner 路径命中；F3 三个 snapshot test 各恰一条 opacity 断言。
- `git diff --check`：通过。

## 7. Residual risk 与 stop

- 未执行明确禁止的 UF-PF05 真实 CLI evidence；未运行非 relevant 的 Host/Engine 全仓测试。
- filesystem 权限/I/O 继续使用 exact `os.lstat` failure injection，以避免 CI 用户权限模型掩盖 errno；未增加跨平台 ACL/NFS 外部环境 evidence。
- 当前 fix 已完成但未提交；按用户指令停在 S2 fix implementation，不开始 re-review。

## 8. S2 re-review controller narrow follow-up

### 8.1 Gate 与裁决边界

- 已完整读取 `code-review-20260815-020224.md`、`code-review-20260815-021015.md` 与 `wu-upload-filing-ticker-alias-contract-s2-rereview-controller-adjudication.md`。
- 只处理 controller accepted 的两个 low findings；material 缺 company name 的 pipeline-direct open question 保持 rejected/deferred，未修改 admission 或 failure 分类。
- 未改 README、workspace identity lock graph、merge/recovery owner、durable schema/index/cache 或其它 finding。

### 8.2 Commit-time backup existence owner

`_commit_batch_with_publication_guard(...)` 在持有 target publication guard 后、第一次 physical replace 前，改为调用既有 `_lstat_optional_storage_path(...)`：

- 仅 `ENOENT` 被视为 target missing；
- `EACCES/EIO` 与其它 operational I/O 保留 errno、去除 locator 后 fail closed；
- lstat 返回的 existing locator 必须是 directory；regular file 或 symlink 在 replace 前抛 `ValueError`；
- 只有 strict directory 才执行 target -> backup replace；后续 journal phase、rollback 与锁释放图均未改变。

直接测试证据：

- `test_commit_backup_lstat_io_failure_precedes_replace_and_preserves_evidence`（EACCES/EIO 参数化）在 begin 完成后才注入 exact target `os.lstat` failure，并用 `_ReplaceDirectoryForbidden` 证明 replace 调用数为零；断言 errno/path-free、published tree byte-for-byte 不变、backup evidence exact 不变、transaction staging 按既有 rollback 语义清理、active capability 被消费。
- `test_commit_backup_rejects_non_directory_before_replace_and_preserves_locator` 在 begin 后把 published directory 停放到受控 locator，并在 exact target 放置 regular file；commit 必须在 replace 前拒绝，regular-file bytes、停放的 published tree 与 backup evidence 均 exact 不变，且 transaction staging/active state 正常收口。

### 8.3 Begin-time symlink / regular-file owner tests

`test_begin_batch_rejects_non_directory_locator_and_releases_writer` 对 `symlink/regular_file` 参数化：

- 断言相同 bounded `ValueError`；
- 通过 `os.lstat` 分别确认 locator 仍是 symlink/regular file，并断言 raw link target 或 exact bytes 不变；
- 断言 `_active_batches`、`_active_transaction_by_ticker`、`_reserved_batch_tickers` 与 batch transaction directory 均无泄漏；
- 移除受控非法 fixture 后，同 ticker 再次 `begin_batch/rollback_batch` 成功，直接证明 local reservation 与跨进程 writer lock 可恢复。

### 8.4 Follow-up validation

全部命令均在 `source .venv/bin/activate` 后执行：

- 两项 accepted finding focused：`5 passed`。
- identity contract + storage atomicity：`190 passed`。
- final relevant branch run：`1604 passed, 1 skipped, 3 warnings`；skip 与 warnings 均为既有环境/dependency 条件。
- 修改生产文件 branch coverage 全部 `>=80%`；最低 `83%`，`_fs_storage_infra.py=84%`。
- 全量 `pyright`：`0 errors, 0 warnings, 0 informations`。
- 修改文件 `ruff check` 与 `ruff format --check`：通过。
- residue：`_commit_batch_with_publication_guard` 及 begin target 判定不再使用 `Path.exists/is_symlink`；旧 route/index/repository compatibility symbols 仍为零命中。
- `git diff --check`：通过。

### 8.5 Stop

两个 accepted low findings 已完成窄修复且未提交。按用户指令停在同一 S2 fix，不开始 review/re-review。
