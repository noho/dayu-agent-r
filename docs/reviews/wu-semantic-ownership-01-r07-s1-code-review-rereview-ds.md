# WU-SEMANTIC-OWNERSHIP-01 / R07-S1 Complete Cumulative Code Re-Review (AgentDS)

## Scope

- **Mode**: cumulative re-review of accepted finding fixes + full S1 product/test tree
- **Branch**: `phaseflow/host-issues-control`
- **Base**: transition HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`（`docs: enter R07 opaque identity implementation`）
- **Accepted plan**: `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`（SHA-256 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`）
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-controller-adjudication.md`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-codex.md`（最终 SHA-256 `765685b713de24e4cadcb1c462981a1ee2657faf4453406345bf812e2623437d`）
- **Controller fix validation**: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-controller-validation.md`（verdict PASS）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-ds.md`
- **Included scope**: 9 S1 production files（plan §7.1 allowlist）+ 4 test files + `_fs_identity.py`
- **Excluded scope**: plan/control/design/旧 review/README、S2/S3、R08+、deferred ISSUE 142/151/175/177/178、统一 authorization
- **Reviewer**: AgentDS（second independent cumulative re-review）

## Conclusion

**PASS — 0 blocker, 所有 4 项 accepted findings 已关闭。**

`R07-S1-CR-F01`（destructive cleanup complete preflight）、`R07-S1-CR-F02`（`begin_batch` 主异常优先）、`R07-S1-CR-F03`（path-free filesystem error boundary）与 `R07-S1-CR-CV-F01`（exception graph locator 泄漏）四项在 production owner boundary 全部正确修复，黑盒测试覆盖真实 filesystem failure、permission denial、Unix-domain socket I/O failure、runtime lock acquire/release failure、staging cleanup + lock release 双失败与三个 terminal cleanup note 路径。Controller 已 rejected 的 11 项 alternatives 均未在新代码中出现，也无新的直接代码反例。

完整 S1 product/test tree 的 independent adversarial pass 未发现新的 correctness blocker、owner drift、overdesign 或 test gap。R06 4-phase atomicity、lock 顺序、primary error、old/new publication guard、security containment、symlink rejection、filename/URI escape rejection、identity descriptor round-trip truth、opaque identity mapping fail-closed、company inventory breaking cutover 全部保持。

## Accepted Finding Closeout

### R07-S1-CR-F01 — CLOSED — destructive cleanup complete preflight

**Production evidence**：

- `_fs_storage_infra.py::_validate_complete_source_kind_tree`（line 664）在任何删除前验证 filing source root、manifest、全部 document descriptor/meta/files/primary/size/hash 双向关系，以及 control files（`_download_rejections.json`、`.rejections`）。
- `_fs_maintenance_core.py::_preflight_rejected_filing_tree`（line 520）完整验证 nested `.rejections` container、identity directory、descriptor、required meta、exact ticker/document ID 与业务文件集。
- `_fs_maintenance_core.py::_preflight_filing_cleanup`（line 594）组合 complete filing tree + download rejection registry + nested rejected tree；`clear_filing_documents`（line 660）和 `cleanup_stale_filing_documents`（line 739）在 snapshot/delete/manifest mutation 前调用该 preflight。
- stale cleanup（line 741-749）直接消费 preflight 返回的 validated meta，对 missing/corrupt/mismatch meta 不再 `continue`。
- `_fs_processed_core.py::_preflight_processed_cleanup`（line 356）在删除前一次性验证 processed root、identity descriptor、required `meta.json`、exact document ID、regular entries、manifest typed/duplicate/set equality。

**Test evidence**：

- `test_filing_clear_preflight_rejects_all_invalid_evidence_before_deletion`：8 类参数化 corruption（filing descriptor/manifest、rejection registry、rejected descriptor/meta/symlink/unexpected、top-level unexpected），逐类断言 `filings_root.iterdir()` 前后一致、stale/non-stale directories 与 rejected directory 均未删除。
- `test_processed_clear_preflight_rejects_all_invalid_evidence_before_deletion`：7 类参数化 corruption（descriptor、meta missing/corrupt/mismatch、manifest corrupt、symlink、unexpected），逐类断言无 partial delete。
- `test_stale_cleanup_meta_failure_is_fail_closed_without_partial_deletion`：3 类参数化 stale meta corruption（missing/corrupt/mismatch），逐类断言 manifest 与候选目录均未改变。

**验证**：三类 destructive cleanup（filing clear / processed clear / stale cleanup）的任何 validation failure 均发生在第一次 `rmtree`/`unlink`/manifest mutation 之前。✅

### R07-S1-CR-F02 — CLOSED — `begin_batch` 主异常优先

**Production evidence**：

- `_fs_storage_infra.py::begin_batch`（line 426）的 exception handler（line 488-514）：
  1. 捕获最早 primary（journal/descriptor/copy 失败）；
  2. 若 primary 是 raw `OSError`，先通过 `_project_filesystem_error` 投影为 path-free 同类异常；
  3. staging cleanup 失败只通过 `_append_secondary_error_note` 附加诊断；
  4. writer-lock release 失败同样只附加诊断；
  5. active maps（`_active_batches`、`_active_transaction_by_ticker`）仅在全部初始化成功后写入（line 516-517）。

**Test evidence**：

- `test_begin_batch_preserves_initialization_primary_when_lock_release_fails`：参数化覆盖 journal/descriptor/copy 三种 primary；`exc_info.value is primary_error`（journal/copy）或 `isinstance(..., ValueError)`（descriptor corrupt）+ release note 可诊断 + `_active_batches == {}` + `_active_transaction_by_ticker == {}` + `batch_root.iterdir() == []`。
- `test_begin_batch_preserves_primary_with_staging_cleanup_and_release_failures`：同时制造 pathful staging `PermissionError` 与 lock release failure；断言原 `RuntimeError` 对象仍为主异常，两个次级 note 均可诊断且不含 locator，active maps 不发布。
- `test_begin_batch_projects_pathful_journal_oserror_graph_without_publishing_state`：断言 primary `PermissionError` subclass/`EACCES` 与 path-free cause 类别保留，raw error 不可从 cause/context 到达，完整 graph/notes/traceback 无 workspace/staging/backup/lock/private key，active maps 为空。

**验证**：任何初始化 primary failure 都不会被次级 cleanup/release failure 替换；active state maps 只在完全成功后发布。✅

### R07-S1-CR-F03 — CLOSED — path-free filesystem error producer boundary

**Production evidence**：

- `_fs_storage_utils.py::_new_path_free_filesystem_error`（line 454）：创建与 raw exception 同 subclass、同 `errno`、仅含 action message 的新异常。
- `_fs_storage_utils.py::_project_filesystem_error`（line 474）：构造 path-free 顶层异常 + path-free cause；`__suppress_context__ = True`。
- `_fs_storage_utils.py::_raise_path_free_error`（line 501）：在明确投影点通过 `raise error from error.__cause__`（隐式 suppress context）+ `except` 后显式 `projected_error.__context__ = None` 双重关闭 raw context 泄漏。
- `_fs_storage_utils.py::_append_secondary_error_note`（line 526）：诊断仅含 `action + error_type + optional errno`，不复制次级 message/path。
- Owner I/O helpers（`_list_directory`、`_read_file_bytes`、`_open_binary_file`、`_unlink_path`）统一在 storage producer boundary 投影 raw I/O failure。
- `_read_json`/`_write_json`（line 633/701）：raw I/O failure 在此边界投影；JSON corruption 继续走既有 `ValueError` contract；atomic-write cleanup failure 只附加 path-free secondary note。
- `_fs_storage_infra.py::_project_runtime_lock_error`（line 119）：投影 runtime-lock 异常，nested `OSError` cause 只保留同 subclass/errno 的 path-free cause；非 OSError cause 只保留 error_type 类别名。
- `_acquire_storage_lock_token`（line 152）/ `_release_storage_lock_token`（line 192）：runtime lock acquire/release 的唯一 storage-local adapter；未修改 `dayu.runtime.filelock`。
- 调用边界覆盖：identity JSON/descriptor/enumeration、company meta/inventory candidate enumeration、source/processed/rejected/blob public read/list/open、batch workspace/journal/copy/init、lock release、recovery/backup enumeration、filing/processed maintenance preflight 与 destructive operations。
- `scan_company_meta_inventory`（`_fs_company_meta_core.py:129`）：`OSError` 被 catch 后使用固定 business detail `"缺少可验证且一致的 ticker identity descriptor"`；唯一 `detail=str(exc)` 仅位于 `except (KeyError, TypeError, ValueError)` 业务解析分支（line 162）。

**Test evidence**：

- `test_public_storage_os_errors_are_path_free_across_read_and_inventory_boundaries`：真实 `chmod(0)` 制造 company/source/processed/rejected 四个 read path 的 `EACCES` failure；root-like 平台 fallback 使用同一 `Path.read_text` seam 注入等价异常。断言顶层 `PermissionError`/`EACCES` + path-free cause + `__context__ is None` + complete graph 无 workspace root/private locator。
- `test_blob_read_projects_real_socket_io_error_without_private_locator`：blob regular file 替换为真实 Unix domain socket，触发真实 OS I/O failure；递归遍历 `__cause__`/`__context__`，每个节点检查 `str/args/notes` 及 `traceback.format_exception`，确认 raw socket error 不可达、workspace/private locator 不出现。
- `test_runtime_lock_acquire_error_graph_is_path_free_at_public_batch_boundary`：真实 `chmod(0)` 锁根目录制造 acquire failure（root-like fallback 注入等价 nested cause）；graph 无 lock path/private key，top subclass 与 nested `PermissionError/EACCES` category 保留。
- `test_runtime_lock_release_error_graph_is_path_free_at_public_batch_boundary`：真实释放后注入 runtime wrapper 的 pathful nested cause；public rollback 只暴露 path-free `RuntimeFileLockError -> PermissionError(EACCES)` graph。
- `test_commit_primary_failure_survives_writer_release_failure` 与 `test_commit_batch_publication_release_failure_preserves_committed_truth`：覆盖三个 terminal note（publication release、post-commit cleanup、writer release）；断言 authoritative primary 不变、note 精确为 action/type/errno，次级 message/path 不可从 graph 或 traceback 观察。

**验证**：storage public boundary 抛出的完整 exception graph（`__cause__`、`__context__`、`args`、`notes`、`traceback.format_exception`）均不含 workspace absolute path、private storage key、staging、backup 或 lock locator。✅

### R07-S1-CR-CV-F01 — CLOSED — exception graph locator 泄漏修复

本 finding 是 Controller fix validation 发现的首轮 fix artifact 残留问题，归入 CR-F03 修复范围。

**修复要点**：

- `_project_filesystem_error` 现重新构造同 subclass/errno 的 path-free 顶层异常与 path-free cause；不再保留 raw exception 对象或其 pathful graph。
- `_raise_path_free_error` 显式清除 Python 自动挂入的 raw context。
- Storage-local runtime-lock adapter 重新投影 acquire/release failure，保留 `RuntimeFileLockError`/timeout 类别而不暴露第三方/raw nested locator。
- publication release、post-commit cleanup、writer release 三处 note 均复用 `_append_secondary_error_note`，只保留 action、error type 与可用 errno。

**Controller 独立复验**：真实 Unix-domain socket failure 完整异常图结果为 `nodes=2, top_type=OSError, top_errno=102, cause_type=OSError, context_none=True, graph_leak=False, raw_node_reachable=False`。✅

## Adversarial Attack Surface Pass

### Security / Containment / Recovery

| 机制 | 状态 | 证据 |
|---|---|---|
| external identity 拒绝 separator/dot/drive/absolute | **有意修改**：identity channel round-trip exact；path safety 由 filename/URI owner 独立保证 | Unicode/层级/separator/drive-like/`./..` identity 全部 round-trip 测试通过 |
| filename/entry name 单路径组件拒绝 | **保留** | `_normalize_path_component` 拒绝 empty/`./..`/separator/drive/absolute |
| local URI/object key containment | **保留并收紧**：只含 private keys + safe filename | `_local_path_from_uri` resolve + `relative_to` containment |
| path containment | **保留** | `_require_contained_path`、`_is_contained_recovery_path` 全链路 |
| symlink rejection | **保留** | descriptor、directory、root、copy tree 全链路 fail closed |
| atomic JSON/file write | **保留并复用** | `_write_json` same-dir temp + flush/fsync + `os.replace` + parent fsync |
| R06 writer mutex | **保留**：lock locator 改用 private ticker key | 两个不同 external identity 不碰撞；same identity 仍互斥；preprocess 持锁一致性 |
| R06 publication guard | **保留** | commit/recovery swap 短窗；copy/processor 阶段不持有 |
| journal/recovery state machine | **保留状态机，locator 改用 descriptor round-trip** | 每个 crash phase、orphan backup、corrupt descriptor、key/meta mismatch |
| complete-source validator | **扩展**：加入 identity descriptor 与 file completeness | incomplete/collision/corruption/meta mismatch 均不能 commit |
| typed provenance/citation | **保留** | source type/provider matrix |
| typed read errors | **保留** | decode/not-found/cancel 不改名 |

### Raw locator scan

- `_normalize_document_id`、`_list_directory_names`、`_published_ticker_directory_names`：**0 残留**。
- raw external ticker/document ID 参与 path/object-key/lock/backup/staging join：**0**。
- `child.name`/`directory_name` 反推业务 identity：**0**。所有残留命中均属 owner control name 过滤、private candidate 解析、业务 filename 或 descriptor enumeration。
- `hasattr`/`getattr`：**0**。
- compatibility re-export/wrapper/facade：**0**。
- S2/S3/R08+/Issue 142/151/175/177/178/统一 authorization：**0**。

### AST audit

121 个 ticker/document-id-like `Path /` 或 f-string 候选全部人工分类：
- identity owner 产生的 private key locator（`ticker_key`/`document_key`）
- mapped root helper 后的固定 owner subdirectory（`/filings`/`/materials`/`/processed`）
- business-readable error/log text（含 external ticker/document ID 但不含 private locator）
- business meta/URI serialization（local URI 含 private directory name 但仅在 storage internal validator 使用）

逐项无 raw external identity 直接作为 filesystem path/lock/backup/staging 组件。

### 806-line `_fs_storage_infra.py` begin_batch primary-error state machine

完整路径追踪确认：

1. journal/descriptor/copy 任一初始化失败 → primary 被保留且 OSError 被投影
2. staging cleanup `shutil.rmtree` 失败 → `_append_secondary_error_note`（action 为 `"batch staging cleanup failed"`）
3. `_release_lock_token` 失败 → `_append_secondary_error_note`（action 为 `"writer mutex release failed during batch initialization"`）
4. primary 是 projected error 时 `_raise_path_free_error(primary_error)`，否则 `raise`
5. active maps 仅在 try 块完全成功后写入

双失败场景（staging cleanup + lock release 同时失败）仍只抛最早主异常，两个 note 均可诊断且不含 locator。✅

### `_raise_path_free_error` context-clearing 正确性

```python
try:
    raise error from error.__cause__  # suppress_context=True（隐式）
except BaseException as projected_error:
    projected_error.__context__ = None  # 显式防御
    raise
```

在 caller 处于 `except OSError as exc:` 上下文中时，`raise error from error.__cause__` 的 `from` 子句会设置 `__suppress_context__ = True`，阻止 Python 将 raw `exc` 写入 `__context__`。随后的 `except` 内 `projected_error.__context__ = None` 是额外防御，确保即使 `error.__cause__` 为 `None`（无 `from` 等价路径）时也不泄漏 raw context。

### Rejected alternatives 无回归

Controller 已 rejected 的 11 项 alternatives：
- MIMO-F01（stale `startswith("fil_")`）：仍保留 SEC 业务分类，在 descriptor 恢复 external ID 后执行
- MIMO-F03（null byte/whitespace/control chars）：仍接受非空 UTF-8 exact identity
- MIMO-F04（`_fs_identity.py` 无独立测试文件）：仍由现有四文件集成覆盖，coverage 80.00%
- MIMO-F05（unused import）：证实为 false evidence，当前无此 import
- DS-F01（corrupt backup 污染 valid target）：仍 fail closed cross-validation
- DS-F02（per-artifact skip-warn）：仍 fail closed enumeration
- DS-F03（directory vs meta existence）：仍以 processed meta 为 record existence owner
- DS-F05（ticker guard 不一致）：仍服务不同 typed owner
- DS-F06（`mkdir` 非幂等）：仍由 writer lock 序列化
- DS-F07（unvalidated missing locator）：仍为 `FileNotFoundError` contract 必要输入
- DS-F08（test fixture `removeprefix`）：仍编码 SEC producer 业务关系

无新直接代码反例。✅

### Test coverage

| Production file | Line coverage |
|---|---|
| `dayu/fins/domain/document_models.py` | 96.08% |
| `dayu/fins/storage/_fs_identity.py` | 80.00% |
| `dayu/fins/storage/_fs_storage_utils.py` | 83.82% |
| `dayu/fins/storage/_fs_storage_infra.py` | 86.19% |
| `dayu/fins/storage/_fs_blob_core.py` | 88.06% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 92.39% |
| `dayu/fins/storage/_fs_processed_core.py` | 88.83% |
| `dayu/fins/storage/_fs_source_document_core.py` | 83.69% |

全部逐文件 `>=80%`。

### Verification matrix

| 检查 | 结果 |
|---|---|
| 4 exact full test files | `363 passed, 3 warnings in 12.99s` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-scope Ruff | `All checks passed!` |
| `git diff --check` | PASS |
| identity source scan | `_normalize_document_id/_list_directory_names/_published_ticker_directory_names` = 0；`_parse_backup_directory_name` 仅解析 private candidate |
| raw external identity in path join scan | 0 |
| directory name → business identity scan | 0（所有命中为 control file 过滤/private candidate/filename） |
| AST audit | 121 候选全部人工分类，0 raw external identity path/lock/backup/staging join |
| runtime lock adapter | `file_lock(...).acquire()`/`token.release()` 仅存在于 storage-local adapter |
| `hasattr`/`getattr` | 0 |
| S2/S3/R08+/Issue/统一 authorization | 0 diff |

## Open Questions

无。

## Residual Risk

1. **`_ensure_identity_directory` TOCTOU 窗口**（继承自 MiMo review）：line 162 的存在性检查与 line 169 的 `mkdir` 之间存在理论性 TOCTOU 窗口。需对 workspace root 有写权限才能利用；所有 production caller 均在 writer/publication lock 保护下调用。实际风险极低，且 Controller 已拒绝 DS-F06 的修复方案（单独的 `exist_ok=True` 不能安全解决 descriptor publication race）。

2. **Unicode hierarchy separators**（继承自 MiMo review）：`_normalize_path_component` 的路径分隔符检测未覆盖 Unicode 行分隔符（U+2028、U+2029、U+0085）。Python `pathlib` 在 macOS 上不将这些字符视为路径分隔符，当前无实际 bypass 风险。

3. **`_list_external_identities` O(n) 重复检测**（继承自 MiMo review）：line 331 `if identity in identities` 对 list 做线性查找。当前 ticker/document 数量级（数百）不构成性能问题。

4. **Inherited test failures**（plan §1.1 ledger）：三个 Service/Runtime 层测试 failure（`test_configure_does_not_touch_root_by_default`、`test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`、`test_service_does_not_import_forbidden_layers`）与 R07 S1 无关，未扩散。

5. **Full Ruff 152 legacy fingerprint**：`72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`。均为继承项，S1 未新增或扩散任何 rule。

---

**最终裁决：PASS。0 blocker。R07-S1 可进入 R07-S2。**
