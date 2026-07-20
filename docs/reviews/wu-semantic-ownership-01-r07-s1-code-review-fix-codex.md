# WU-SEMANTIC-OWNERSHIP-01 R07-S1 code-review fix（Codex）

## 1. 结论与停止点

- Work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 `R07-S1` code-review fix；不是新 WU。
- 唯一 finding 裁决：`docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-controller-adjudication.md`，SHA-256 为 `e6506fdd035b812e666694b66d7cd13ffb976db606411c22c8c7c52594d9d55c`。
- 首轮 fix validation：`docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-controller-validation.md`，SHA-256 为 `b2dd4e25c857d372cbb30a5a2b4e5726767e75082a8363daa720e0d80cad5485`；其 verdict 为 `FAIL / VALIDATION_FIX_REQUIRED`，accepted `R07-S1-CR-CV-F01` 归入既有 CR-F03。
- accepted plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`，SHA-256 为 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- transition HEAD：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- 实施结论：只实现 Controller accepted 的 `R07-S1-CR-F01..03` 及同 finding validation correction `R07-S1-CR-CV-F01`；完整 exception graph 缺口已在 storage owner 修正并完成黑盒验证。
- 当前状态：**CODE_REVIEW_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION**。
- 停止点：本代理停在 Controller validation；未进入 re-review、S2/S3、R08+、deferred Issue 或统一 authorization。
- Git：未 stage、未 commit、未 push、未创建 PR；未修改 control、plan、design、README 或旧 artifact。

## 2. 动机与语义 owner 判定

三项 accepted finding 均有直接代码与真实文件系统证据，动机成立：

1. destructive clear/stale cleanup 的业务事实是“候选集合整体可安全删除”。其 owner 是执行删除的 maintenance/processed storage producer；逐条边验证边删除会在后续 evidence 损坏时制造 partial delete。
2. batch 初始化的 authoritative failure 是最早的 journal/descriptor/copy/目录初始化失败。其 owner 是 `begin_batch` transaction state machine；staging cleanup 与 writer-lock release 只是次级收尾，不能替换主异常或提前发布 active state。
3. filesystem locator 由 storage owner 产生，raw `OSError` 或 runtime-lock nested cause 中的 absolute path/private key 也必须在同一 producer boundary 投影；只清理顶层 `str/args` 不成立，因为 `__cause__`、`__context__`、notes 与格式化 traceback 仍可传播 locator。ingestion/tool/trace 下游不是修复 owner。

修复因此只落在 storage owner 或其直接 I/O helper，没有下游 blacklist、regex sanitizer、LLM-safe normalization、fallback、compatibility shim 或反向 registry。

## 3. Fix-specific scope

本次修复仅改动 Controller adjudication 允许的八个 S1 storage 文件：

| 文件 | F01..03 修复职责 |
| --- | --- |
| `dayu/fins/storage/_fs_identity.py` | descriptor locator/read/enumeration 的 raw `OSError` 统一投影；enumeration 仍 fail closed。 |
| `dayu/fins/storage/_fs_storage_utils.py` | 新增完整 graph path-free filesystem projection、显式 raw-context removal、次级失败 note、directory/read/open/unlink owner helpers；JSON read/write 保留 corruption contract。 |
| `dayu/fins/storage/_fs_storage_infra.py` | `begin_batch` 主因优先；runtime lock acquire/release 在 storage adapter 投影 nested cause；三个 terminal note 复用 typed owner；complete-source preflight 与 batch/recovery/maintenance I/O 投影。 |
| `dayu/fins/storage/_fs_blob_core.py` | blob list/read/delete 使用 owner helpers，保留 missing/is-directory 业务异常。 |
| `dayu/fins/storage/_fs_company_meta_core.py` | inventory 枚举使用 owner helper；descriptor/I/O 失败不进入 pathful typed detail。 |
| `dayu/fins/storage/_fs_maintenance_core.py` | filing/rejected 完整 preflight、stale fail closed、rejected read 与 destructive I/O 投影。 |
| `dayu/fins/storage/_fs_processed_core.py` | processed 完整 preflight；meta 继续拥有 record existence；destructive I/O 投影。 |
| `dayu/fins/storage/_fs_source_document_core.py` | source XBRL/read/reset 可跨 public boundary 的 I/O 投影。 |

测试只在既有 exact allowlist 中追加到：

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`

另外两个 exact test file 仅参与完整回归，fix 未改动。`dayu/fins/domain/document_models.py` 没有本次 owner contract 变更，fix 未修改。接手时 worktree 已包含 S1 implementation 的 domain、control、四个测试文件及旧 review/validation artifacts；这些不是本次 fix 的越界变更，本代理没有修改 control 或旧 artifact。本文件是唯一新增 fix artifact。

## 4. R07-S1-CR-F01：destructive cleanup complete preflight

### 4.1 Production evidence

- `_fs_storage_infra.py::_validate_complete_source_kind_tree` 在任何删除前验证：
  - filing source root 必须存在且为 non-symlink directory；
  - root 仅允许已知 manifest、`download_rejections.json`、`.rejections` 与 descriptor-backed document directories；
  - filing manifest typed 字段、ticker/document ID、重复项；
  - 每个 document descriptor、meta 的 ticker/document ID/source kind/completion/provenance；
  - meta 声明的 primary/files 与 physical regular files 双向一致，包含 size/hash（若声明）；
  - descriptor document IDs 与 manifest document IDs 双向一致。
- `_fs_maintenance_core.py::_preflight_rejected_filing_tree` 完整验证 nested `.rejections`：container、identity directory、descriptor、required meta、exact ticker/document ID、业务文件集合；symlink、unexpected entry、missing/corrupt/mismatch 均 fail closed。
- `_fs_maintenance_core.py::_preflight_filing_cleanup` 组合 complete filing tree、download rejection registry 与 nested rejected tree；`clear_filing_documents` 和 `cleanup_stale_filing_documents` 在 snapshot/delete/manifest mutation 前调用该 preflight。
- stale cleanup 直接消费 preflight 返回的 validated meta，不再对 missing/corrupt/mismatch meta `continue`。只有完整验证通过后才先更新 manifest、再删除 stale directories。
- `_fs_processed_core.py::_preflight_processed_cleanup` 在删除前一次性验证 processed root 已知 control、identity descriptor、required `meta.json`、exact document ID、regular entries、manifest typed/duplicate/set equality。
- `_fs_processed_core.py::_mark_processed_reprocess_required_impl` 对读不到的 processed identity 直接返回，不再为缺失业务 record 创建 descriptor-only directory；存在性仍以 processed meta 为唯一 owner，没有采用被 Controller 拒绝的 directory-existence fallback。

删除循环只消费完整 preflight 后取得的 entry/document snapshot。validation failure 发生时，manifest、document directories、control files 与 rejected artifacts 均未发生 mutation。

### 4.2 黑盒测试

- `test_filing_clear_preflight_rejects_all_invalid_evidence_before_deletion`：8 类参数——filing descriptor、filing manifest、rejection registry、rejected descriptor、rejected meta、rejected symlink、nested unexpected file、top-level unexpected control；逐类断言无 partial delete。
- `test_processed_clear_preflight_rejects_all_invalid_evidence_before_deletion`：7 类参数——descriptor、meta missing/corrupt/mismatch、manifest corrupt、symlink、unexpected entry；逐类断言无 partial delete。
- `test_stale_cleanup_meta_failure_is_fail_closed_without_partial_deletion`：missing/corrupt/mismatch 三类 stale meta；逐类断言 manifest 与候选目录均未改变。

## 5. R07-S1-CR-F02：`begin_batch` 主异常优先

### 5.1 Production evidence

`_fs_storage_infra.py::begin_batch` 的 state machine 现在是：

1. 构造未发布的 local state；
2. 执行 journal、descriptor/copy 或 fresh structure initialization；
3. 捕获最早 primary；若是 raw filesystem `OSError`，先按 F03 投影为同 subclass/errno 的 path-free storage error；其它异常对象保持原 identity；
4. staging cleanup 与 writer-lock release 分别 best effort 执行；任一失败只用 `BaseException.add_note` 附加 path-free `action + error_type + optional errno`，不复制次级异常 message/path，也不替换 primary；
5. 只有全部初始化成功后才写入 `_active_batches` 与 `_active_transaction_by_ticker`。

因此 cleanup/release 双失败仍只抛最早主异常，且 active maps 不会发布半初始化 state。

### 5.2 黑盒测试

- `test_begin_batch_preserves_initialization_primary_when_lock_release_fails` 参数化覆盖 journal、descriptor、copy 三种 primary；断言主异常语义不变、release note 可诊断、staging 已尽力清理、两张 active map 均为空。
- `test_begin_batch_preserves_primary_with_staging_cleanup_and_release_failures` 同时制造 pathful staging `PermissionError` 与 lock release failure；断言原 `RuntimeError` 对象仍为主异常，两个次级 note 均可诊断且不含 locator，active maps 不发布。
- `test_begin_batch_projects_pathful_journal_oserror_graph_without_publishing_state` 断言 primary `PermissionError` subclass/`EACCES` 与 path-free cause 类别保留，raw error 不可从 cause/context 到达，完整 graph/notes/traceback 无 workspace、staging、backup、lock/private key，active maps 为空。

## 6. R07-S1-CR-F03：path-free filesystem error producer boundary

### 6.1 唯一 owner projection

`_fs_storage_utils.py::_project_filesystem_error` 创建与 raw exception 同类型、同 `errno` 的顶层异常，并另行创建同类别/errno、无 raw args/notes/traceback 的 path-free cause。**首轮 artifact 关于“保留 raw cause”的表述错误，现明确推翻：raw exception 对象本身及其 pathful graph 不得跨 storage boundary。**

`_raise_path_free_error` 只接收 owner 已重新构造的安全异常；它在明确投影点清除 Python 自动注入的 raw `__context__`，并只保留预先构造的 path-free cause。它不读取、匹配或改写 raw message，不是下游 sanitizer。

同模块的 `_list_directory`、`_read_file_bytes`、`_open_binary_file`、`_unlink_path` 统一拥有基础 raw I/O 投影；`_read_json`/`_write_json` 在该边界投影 raw filesystem failure，同时继续把 JSON corruption 投影为既有 `ValueError("JSON 解析失败")`。atomic-write cleanup failure 只附加 path-free secondary note，不遮蔽主因。

调用边界覆盖：

- identity JSON/descriptor/enumeration；
- company meta/inventory candidate enumeration；
- source/processed/rejected/blob public read/list/open；
- batch workspace、journal/copy/init、lock release、recovery/backup enumeration；
- filing/processed maintenance preflight 与 destructive operations。

`_fs_storage_infra.py` 新增 storage-local runtime-lock adapter：

- `_acquire_storage_lock_token` 与 `_release_storage_lock_token` 是 `file_lock(...).acquire()` / `RuntimeFileLockToken.release()` 的唯一 owner seam；
- `_project_runtime_lock_error` 保留 `RuntimeFileLockError` / `RuntimeFileLockTimeoutError` subclass；nested `OSError` 仅投影为 path-free 同 subclass/errno cause，其它 nested cause 只保留 path-free error-type category；
- `_PublicationGuardedBinaryOpener`、ticker/publication/recovery acquire 与全部 release 都复用该 adapter；未修改 `dayu.runtime.filelock` 的层中立 contract；
- `commit_batch` publication-release note、post-commit cleanup note、`_close_active_batch` writer-release note 全部复用 `_append_secondary_error_note`，只写 action、error type 与可用 errno，不复制次级 message/path。

`scan_company_meta_inventory` 对 descriptor/I/O 异常使用固定业务 detail `缺少可验证且一致的 ticker identity descriptor`；唯一残留的 `detail=str(exc)` 只位于已收窄的 `except (KeyError, TypeError, ValueError)` 业务解析分支，raw `OSError` 不会进入 typed detail。

已有 business-readable contract 保持：正常 missing/corruption 仍使用业务 ticker、document ID 与 safe filename；没有用 digest/private key 取代业务语义。顶层与递归 `str/args/notes`、`__cause__`、`__context__`、typed inventory detail 及 `traceback.format_exception` 均不含 workspace absolute path、actual private key、staging/backup/lock locator；有意义 subclass、`errno` 与 path-free 因果类别保留。

### 6.2 真实 filesystem 黑盒测试

- `test_public_storage_os_errors_are_path_free_across_read_and_inventory_boundaries` 覆盖 company/source/processed/rejected/list/descriptor-inventory。当前验证用户 `uid=501`，通过真实 `chmod` 产生 `EACCES`，不是只在 root 下失效的权限假设；测试仍为 root-like 平台保留同一 `Path.read_text` seam 的等价 fallback，但本次执行走真实权限失败。
- `test_blob_read_projects_real_socket_io_error_without_private_locator` 把 blob regular file 替换为真实 Unix domain socket，再由 public blob read 触发真实 OS I/O failure；该 probe 不依赖 chmod 或执行用户权限。
- 两组均递归遍历 `__cause__` 与 `__context__`，检查每个节点的 `str/args/notes` 及格式化 traceback；raw socket/permission error 不可达，workspace/private locator 不出现，safe cause 的 subclass/errno 保留。
- `test_runtime_lock_acquire_error_graph_is_path_free_at_public_batch_boundary` 优先通过真实 lock-root permission failure 覆盖 acquire；root-like 平台使用同一 runtime `file_lock` seam 的等价 nested-cause fallback。完整 graph 不含 lock path/private key，top subclass 与 nested `PermissionError/EACCES` category 保留。
- `test_runtime_lock_release_error_graph_is_path_free_at_public_batch_boundary` 真实释放 token 后注入 runtime wrapper 的 pathful nested cause；public rollback 只暴露 path-free `RuntimeFileLockError -> PermissionError(EACCES)` graph。
- `test_commit_primary_failure_survives_writer_release_failure` 与 `test_commit_batch_publication_release_failure_preserves_committed_truth` 覆盖三个 terminal note；断言 authoritative primary 不变、note 精确为 action/type/errno，次级 message/path 不可从 graph 或 traceback 观察。

## 7. Rejected findings 与既有 contract 保留

- stale cleanup 仍在 descriptor 恢复 exact external ID 后应用 `external_document_id.startswith("fil_")` 的 SEC 业务分类。
- `_require_external_identity` 仍是“非空且可 UTF-8 exact 持久化”；未添加 strip、Unicode normalization、whitespace/control-character blacklist。
- `_list_external_identities` 对 symlink、unexpected/private descriptor corruption 继续 fail closed；没有 per-artifact skip/warn。
- processed meta 继续拥有业务 record existence；未以 directory existence 替代。
- recovery 继续对 target/backup descriptor evidence 做 cross-validation；损坏、缺失、mismatch 不静默忽略。
- 未增加 compatibility/fallback、reverse registry、`hasattr/getattr`、下游 sanitizer 或测试专用 production seam。

## 8. 验证证据

### 8.1 Accepted finding 精确节点

运行本 artifact §4.2、§5.2、§6.2 的 12 个参数化/精确 test functions：

```text
29 passed, 3 warnings in 1.09s
```

### 8.2 四个 exact full test files

```text
tests/fins/test_fins_storage_provider.py
tests/fins/test_fins_storage_atomicity.py
tests/fins/test_fins_ingestion_runtime.py
tests/fins/test_sec_pipeline_download.py
```

最终普通 full-file rerun：`363 passed, 3 warnings in 12.68s`。branch coverage run 同时执行上述四文件：

```text
363 passed, 3 warnings in 14.83s
```

三个 warning 均来自安装环境 `edgar` 包的既有 deprecation warning，未新增 warning 类型。

### 8.3 九个 S1 production file line coverage

覆盖率命令使用 `coverage run --branch`，门禁按 JSON 的 `covered_lines / num_statements` 单文件复算。证据文件为未纳入 git 的 `workspace/tmp/r07-s1-code-review-fix-coverage.json`。

| Production file | covered / statements | line coverage |
| --- | ---: | ---: |
| `dayu/fins/domain/document_models.py` | 417 / 434 | 96.08% |
| `dayu/fins/storage/_fs_identity.py` | 92 / 115 | 80.00% |
| `dayu/fins/storage/_fs_storage_utils.py` | 202 / 241 | 83.82% |
| `dayu/fins/storage/_fs_storage_infra.py` | 861 / 999 | 86.19% |
| `dayu/fins/storage/_fs_blob_core.py` | 59 / 67 | 88.06% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 123 / 135 | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 182 / 197 | 92.39% |
| `dayu/fins/storage/_fs_processed_core.py` | 159 / 179 | 88.83% |
| `dayu/fins/storage/_fs_source_document_core.py` | 354 / 423 | 83.69% |

全部逐文件 `>=80%`。

### 8.4 pyright、Ruff 与 diff

- `pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff（九个 S1 production + 四个 exact test files）：`All checks passed!`。
- full Ruff：仍为既有 `152` fingerprint，未扩散：
  - `72 F401`
  - `66 E402`
  - `10 F841`
  - `3 F541`
  - `1 F821`
- `git diff --check`：通过。

## 9. Scope、source、AST 与 private-locator scans

### 9.1 Scope

- fix production：仅 §3 的八个 adjudication allowlist storage files。
- fix tests：仅两个既有 exact test files；没有新增 test file。
- fix artifact：仅本文件。
- 没有修改 domain、README、plan/design/control、旧 artifact、S2/S3/R08+ 或 deferred Issue。
- `git status --short` 仍显示接手前累计 S1 worktree；本代理未 stage/commit，Controller 可按 implementation artifact 与接手状态核对累计 allowlist。

### 9.2 Identity source scan

按 plan §8.3 三组 `rg` 扫描并逐项分类：

- `_normalize_document_id`、`_list_directory_names`、`_published_ticker_directory_names`：0。
- `_normalize_ticker` family 仅命中 company alias 业务 normalization；不参与 external identity path join。
- `_parse_backup_directory_name` 仅解析 private backup candidate，随后必须 descriptor cross-validation；不反推业务 ticker。
- `directory_name`/`child.name` 命中仅属于固定 owner control name、private candidate、业务 filename 或 descriptor enumeration；没有目录名 → external identity fallback。
- raw external ticker/document ID 不直接拼入 portfolio/source/processed/rejected path；均先经 identity owner 映射或经已验证的 owner path helper。

### 9.3 AST audit

按 plan 的完整 storage AST 脚本输出并人工分类 121 个 ticker/document-id-like `Path /` 或 f-string 候选：

| 文件 | candidates | 分类 |
| --- | ---: | --- |
| `_fs_blob_core.py` | 3 | business-readable missing/is-directory error text。 |
| `_fs_company_meta_core.py` | 4 | descriptor-verified ticker root 下固定 meta control，或业务 error text。 |
| `_fs_maintenance_core.py` | 5 | mapped ticker root 下固定 owner subdir、internal local URI、业务 error text。 |
| `_fs_processed_core.py` | 8 | mapped/staging ticker root 下固定 owner subdir、业务 error text。 |
| `_fs_source_document_core.py` | 11 | business-readable missing/corruption error text。 |
| `_fs_storage_infra.py` | 90 | identity owner 产生的 `ticker_key/document_key` private locator、mapped root helper 后固定 subdir、business meta/URI serialization 或业务 error/log text。 |

逐项没有发现 raw external identity 直接作为 filesystem path/object key/lock/backup/staging 组件，也没有 private directory name 反推业务事实。

### 9.4 Raw I/O 与 private locator scan

- 八个 storage 文件内 `iterdir/read_bytes/open/unlink` 的 raw 调用只剩 `_fs_storage_utils.py` owner helpers/atomic JSON helper；caller 全部使用 path-free projection。
- `shutil.rmtree` 只剩 `begin_batch` failure cleanup、统一 `_remove_directory` owner 和既有 ignore-errors rollback best effort；可抛出的前两处均在 producer boundary 投影或转成 path-free secondary note。
- `raise _project_filesystem_error ... from raw`、`raise projected_error from raw`、terminal note `str(release_error/cleanup_error)`：0。
- `file_lock(...).acquire()` 与 `token.release()` 只在 storage-local acquire/release adapter 内出现；publication opener 与 core lock methods 无绕过调用。
- `raise` 对 `workspace_root/portfolio_root/ticker_key/document_key/staging/backup/lock/path` 的值插值扫描：0。
- typed detail locator 插值扫描：0。唯一 `detail=str(exc)` 已证明只消费 `KeyError/TypeError/ValueError` 业务解析异常。
- `hasattr/getattr/sanitize/blacklist/regex` 补偿：0；`fil_` 业务分类、exact identity、enumeration fail closed、processed meta owner 与 backup cross-validation 均有正向 source evidence。
- 递归 propagation tests 独立遍历 cause 与 context，并对每个节点检查 `str/args/notes/traceback.format_exception`；动态 permission/socket/runtime-lock acquire/release smoke 均无 workspace/private/transaction/lock locator，且 subclass/errno/path-free cause category 正确。
- `git diff -- dayu/runtime/filelock.py`：0；runtime 层未修改。

## 10. README 决策、residual 与 handoff

- README：用户明确禁止本 gate 修改 README；本 fix 不改变最终用户安装、CLI、工作流或分层关系，因此未修改。
- 已知 accepted finding residual：无。
- 继承项：full Ruff 152 条 legacy fingerprint；`edgar` 三个 deprecation warning。均未扩散，不属于 R07-S1-CR-F01..03 owner。
- 安全边界：不再保留 raw filesystem/runtime-lock cause。storage owner 只保留重新构造的 path-free cause category 与 errno，并显式清除 raw context；完整公开 exception graph 与格式化 traceback 已关闭 locator 泄漏。
- 未覆盖且不得在本 gate 扩张：S2 revision/snapshot、S3 cache/read/citation、R08 financial/XBRL、R09+、Issue 142/151/175/177/178 与统一 authorization。
- 下一动作唯一为 **Controller validation**；本代理到此停止。
