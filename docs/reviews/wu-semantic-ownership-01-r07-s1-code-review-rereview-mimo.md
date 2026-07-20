# WU-SEMANTIC-OWNERSHIP-01 / R07-S1 Complete Cumulative Code Re-Review — AgentMiMo

## Scope

- Mode: current changes (cumulative S1 working tree re-review)
- Branch: `phaseflow/host-issues-control`
- Base: transition HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`（`docs: enter R07 opaque identity implementation`）
- Output file: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-mimo.md`
- Included scope: 9 production files（plan §7.1 exact allowlist + `_fs_identity.py`）+ 4 test files
- Excluded scope: S2/S3、R08+、Issue 142/151/175/177/178、统一 authorization、README、design、control、plan
- Parallel review coverage: 4 subagents — (1) `_fs_identity.py` + `_fs_storage_utils.py`, (2) `_fs_storage_infra.py` begin_batch/lock/terminal, (3) `_fs_maintenance_core.py` + `_fs_processed_core.py` + `_fs_blob_core.py` + `_fs_company_meta_core.py` + `_fs_source_document_core.py`, (4) 全量 4 个测试文件 coverage audit。主 reviewer 独立复核全部 evidence chain 并整合裁决。

## 验证矩阵

| 检查 | 结果 |
|---|---|
| 四个 exact full test files | `363 passed, 3 warnings`（13.16s） |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（9 production + 4 test） | `All checks passed!` |
| full Ruff baseline | 既有 `152`：`72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散 |
| `git diff --check` | PASS |
| `SourceDocumentRevision` import in infra | 0（scope clean） |
| S2/S3/R08+/deferred Issue/统一 authorization 偷带 | 0 |

## 结论

**PASS**

累计 S1 product/test tree 通过完整对抗性 re-review。Controller accepted 的 `R07-S1-CR-F01`、`R07-S1-CR-F02`、`R07-S1-CR-F03`（含 validation correction `R07-S1-CR-CV-F01`）全部关闭。Controller rejected 的 11 项 finding 均未被误实现。未发现新的 evidence-backed blocker finding。

---

## Accepted Findings 闭合状态

### R07-S1-CR-F01 — destructive cleanup complete preflight — **已关闭**

**Production evidence**:

- `_fs_storage_infra.py::_validate_complete_source_kind_tree`（L664-763）在任何删除前完成只读完整校验：filing source root non-symlink directory、仅允许已知条目、manifest typed 字段、descriptor/meta bidirectional consistency、physical files 与 meta claims 双向一致、descriptor document IDs 与 manifest document IDs 双向一致。任意 corruption 均 `raise`，无 fallback/skip/continue。
- `_fs_maintenance_core.py::_preflight_filing_cleanup`（L594-621）组合 complete filing tree + download rejection registry + nested rejected tree preflight。`clear_filing_documents`（L660）和 `cleanup_stale_filing_documents`（L739）在 snapshot/delete/manifest mutation 前调用该 preflight。
- `_fs_maintenance_core.py::_preflight_rejected_filing_tree`（L520-592）完整验证 nested `.rejections`：container non-symlink directory、identity directory non-symlink、descriptor via `_read_identity_descriptor`、required meta non-symlink regular file、exact ticker/document ID、business file collection 双向一致。symlink/unexpected entry/missing/corrupt/mismatch 均 fail closed。
- stale cleanup（L739-741）直接消费 preflight 返回的 validated meta，不再对 missing/corrupt/mismatch meta `continue`。
- `_fs_processed_core.py::_preflight_processed_cleanup`（L356-433）在删除前一次性验证 processed root、known control、identity descriptor、required `meta.json`、exact document ID、regular entries、manifest typed/duplicate/set equality。`clear_processed_documents`（L472）在删除前调用该 preflight。
- `_fs_processed_core.py::_mark_processed_reprocess_required_impl`（L345）对不存在的 processed meta 直接返回，不为缺失业务 record 创建 descriptor-only directory。processed meta 继续拥有 business record existence owner。

**Test evidence**:

- `test_filing_clear_preflight_rejects_all_invalid_evidence_before_deletion`（atomicity L1148-1257）：8 类参数全覆盖，逐类断言无 partial delete。
- `test_processed_clear_preflight_rejects_all_invalid_evidence_before_deletion`（atomicity L1259-1351）：7 类参数全覆盖，逐类断言无 partial delete。
- `test_stale_cleanup_meta_failure_is_fail_closed_without_partial_deletion`（atomicity L1353-1425）：missing/corrupt/mismatch 3 类全覆盖，逐类断言 manifest 与候选目录均未改变。

**裁决**: CR-F01 闭合。destructive cleanup 在任何 mutation 前完成 complete preflight；stale cleanup fail closed。

---

### R07-S1-CR-F02 — `begin_batch` primary-error preservation — **已关闭**

**Production evidence**:

`_fs_storage_infra.py::begin_batch`（L488-514）state machine：

1. 构造未发布的 local state（L427-477）；
2. 执行 journal、descriptor/copy 或 fresh structure initialization（L479-487）；
3. 捕获最早 primary（L488）；若是 raw filesystem `OSError`，先按 F03 投影为同 subclass/errno 的 path-free storage error（L491-494）；其它异常对象保持原 identity；
4. staging cleanup 与 writer-lock release 分别 best effort 执行（L496-511）；任一失败只用 `_append_secondary_error_note` 附加 path-free `action + error_type + optional errno`，不复制次级异常 message/path，也不替换 primary；
5. 只有全部初始化成功后才写入 `_active_batches` 与 `_active_transaction_by_ticker`（L516-518）。

因此 cleanup/release 双失败仍只抛最早主异常，且 active maps 不会发布半初始化 state。

**Test evidence**:

- `test_begin_batch_preserves_initialization_primary_when_lock_release_fails`（atomicity L251-357）：参数化覆盖 journal/descriptor/copy 3 种 primary；断言 `exc_info.value is primary_error`、release note 可诊断、staging 已清理、两 active map 为空。
- `test_begin_batch_preserves_primary_with_staging_cleanup_and_release_failures`（atomicity L360-461）：同时制造 pathful staging `PermissionError` 与 lock release failure；断言原 `RuntimeError` 仍为主异常、两个次级 note 均可诊断且不含 locator、active maps 未发布。
- `test_begin_batch_projects_pathful_journal_oserror_graph_without_publishing_state`（atomicity L463-540）：断言 primary `PermissionError` subclass/`EACCES` 与 path-free cause 类别保留、raw error 不可从 cause/context 到达、完整 graph/notes/traceback 无 workspace/staging/backup/lock/private key、active maps 为空。

**裁决**: CR-F02 闭合。`begin_batch` 初始化失败始终保持原始异常为主异常；staging cleanup 和 writer-lock release failure 只作为附加诊断。

---

### R07-S1-CR-F03（含 CR-CV-F01）— path-free filesystem error producer boundary — **已关闭**

**Production evidence**:

`_fs_storage_utils.py` 核心投影链：

- `_project_filesystem_error`（L474-498）：创建与 raw exception 同类型、同 `errno` 的 path-free 顶层异常与 path-free cause。`__suppress_context__ = True` 阻止 Python 隐式 chaining raw exception。
- `_raise_path_free_error`（L501-523）：`raise error from error.__cause__` 保留预构造 path-free cause；`__context__ = None` 清除 Python 自动注入的 raw context。
- `_append_secondary_error_note`（L526-549）：只写 `action: error_type={class_name}` + 可选 `errno={errno}`，不复制次级异常 message/path。

基础 I/O helpers 统一投影：`_list_directory`（L552）、`_read_file_bytes`（L572）、`_open_binary_file`（L92）、`_unlink_path`（L612）均通过 `_project_filesystem_error` + `_raise_path_free_error` 投影。`_read_json`/`_write_json` 在该边界投影 raw filesystem failure，JSON corruption 继续投影为 `ValueError("JSON 解析失败")`。

`_fs_storage_infra.py` runtime-lock adapter：

- `_acquire_storage_lock_token`（L173）与 `_release_storage_lock_token`（L207）是 `file_lock(...).acquire()` / `RuntimeFileLockToken.release()` 的唯一调用点。
- `_project_runtime_lock_error`（L137-148）保留 `RuntimeFileLockError` / `RuntimeFileLockTimeoutError` subclass；nested `OSError` 投影为 path-free 同 subclass/errno cause。
- `dayu/runtime/filelock.py` 未修改。

Terminal notes 三处均复用 `_append_secondary_error_note`：

- `commit_batch` publication guard release（L567-574）
- `commit_batch` post-commit cleanup（L614-621）
- `_close_active_batch` writer mutex release（L1239-1243）

`scan_company_meta_inventory`（company_meta_core L129）对 descriptor/I/O 异常使用固定业务 detail `"缺少可验证且一致的 ticker identity descriptor"`；唯一 `detail=str(exc)` 位于 `except (KeyError, TypeError, ValueError)` 业务解析分支。

raw I/O scan 确认：八个 storage 文件内 `iterdir/read_bytes/open/unlink` 的 raw 调用只剩 `_fs_storage_utils.py` owner helpers；`shutil.rmtree` 只剩 `begin_batch` failure cleanup、统一 `_remove_directory` owner 和 ignore-errors rollback best effort；`file_lock(...).acquire()` / `token.release()` 只在 storage-local adapter 内出现；`raise` 对 `workspace_root/portfolio_root/ticker_key/document_key/staging/backup/lock/path` 值插值扫描为 0；`hasattr/getattr/sanitize/blacklist/regex` 补偿为 0。

**Test evidence**:

- `test_public_storage_os_errors_are_path_free_across_read_and_inventory_boundaries`（provider L2152-2467）：覆盖 company/source/processed/rejected/list/descriptor-inventory。真实 `chmod(0)` + root-like 平台 fallback。递归遍历 `__cause__`/`__context__`，检查每个节点 `str/args/notes` 及格式化 traceback。
- `test_blob_read_projects_real_socket_io_error_without_private_locator`（provider L2469-2553）：真实 Unix domain socket，不依赖 chmod。完整异常图无 private locator。
- `test_runtime_lock_acquire_error_graph_is_path_free_at_public_batch_boundary`（atomicity L543-625）：真实 lock-root permission failure + root-like fallback。完整 graph 不含 lock path/private key。
- `test_runtime_lock_release_error_graph_is_path_free_at_public_batch_boundary`（atomicity L628-699）：真实释放 token 后注入 pathful nested cause。public rollback 只暴露 path-free graph。
- `test_commit_primary_failure_survives_writer_release_failure`（atomicity L2188-2293）：三条终态 note 断言 action/type/errno only、主异常 identity 不变。
- `test_commit_batch_publication_release_failure_preserves_committed_truth`（atomicity L2296-2429）：post-commit cleanup + writer release note 同上断言。

**裁决**: CR-F03（含 CR-CV-F01）闭合。storage public boundary 的完整 exception graph（`__cause__`、`__context__`、`args`、notes 及格式化 traceback）不含 workspace absolute path、private storage key、staging、backup、lock locator。有意义 subclass、`errno` 与 path-free 因果类别保留。

---

## Rejected Findings 误实现检查

| Controller rejected finding | 要求 | 实际状态 | 判定 |
|---|---|---|---|
| MIMO-F01: `fil_` 业务分类保留 | stale cleanup 在 descriptor 恢复 exact external ID 后应用 `startswith("fil_")` 业务分类 | `cleanup_stale_filing_documents` L742 确认 | 正确 |
| MIMO-F03: 不做 strip/normalization/blacklist | `_require_external_identity` 仅校验非空+UTF-8 | L44-64 确认，无 null byte/control/whitelist 检查 | 正确 |
| MIMO-F04: 不新增 test file | S1 test allowlist 只有 4 个文件 | 无第五个 test file | 正确 |
| MIMO-F05: `SourceDocumentRevision` 未使用 | 从 infra import 删除 | infra 无该 import | 正确 |
| DS-F01: backup cross-validation 保留 | corrupt backup 不阻止 valid target | `_ticker_identity_from_candidate_key` 保留 target/backup 区分 | 正确 |
| DS-F02: enumeration fail-closed 保留 | `_list_external_identities` 对 corruption fail closed | L296-338 确认，无 per-artifact skip | 正确 |
| DS-F03: processed meta 存在性 owner | 不以 directory existence 替代 | `_delete_processed_impl` L132-135 以 meta_path 为准 | 正确 |
| DS-F05: optional guard for generic meta | `_get_document_meta_unguarded` 可无 ticker | 两处服务不同 typed owner | 正确 |
| DS-F06: 不用 exist_ok | `_ensure_identity_directory` 无 `exist_ok=True` | L169 确认，writer lock 序列化 | 正确 |
| DS-F07: deterministic missing locator | 目录不存在时返回确定性路径 | L266-272 确认 | 正确 |
| DS-F08: removeprefix producer 关系 | fixture 编码 SEC producer 业务关系 | provider L1071 确认 | 正确 |

**裁决**: 全部 11 项 rejected findings 均未被误实现。语义所有权边界正确。

---

## Observations（非 blocker）

### OBS-1 — 低 — `_fs_storage_infra.py::_require_copyable_ticker_tree` 中 `rglob("*")` 未在函数内直接投影 OSError

- **文件(行号)**: `_fs_storage_infra.py:2101`
- **场景**: `ticker_dir.rglob("*")` 是 `begin_batch` 调用链中唯一的裸 `Path` 迭代器，其 `OSError` 未在函数内直接捕获和投影。
- **缓解**: `begin_batch` 的外层 `except Exception`（L488）会捕获并投影所有 OSError，因此实际不会泄漏路径。
- **风险**: 低。属于防御深度不一致，非 correctness 问题。

### OBS-2 — 低 — `_fs_storage_utils.py::_write_json` 参数 `payload: Any` 违反编码硬约束

- **文件(行号)**: `_fs_storage_utils.py:701`
- **约束**: CLAUDE.md 编码硬约束禁止使用 `Any`。
- **缓解**: 此为既有模式（同文件 `_read_json` 返回 `dict[str, Any] | list[Any]`、`_extract_file_payloads` 参数 `meta: dict[str, Any]` 等均有类似用法）。项目已有 `JsonValue` 类型（L15 导入），可替代但属于 pre-existing debt。
- **风险**: 低。pyright 通过，功能无影响。与 CR-F01/F02/F03/CV-F01 无关。

---

## Open Questions

无。

## Residual Risk

1. **`_fs_identity.py` 无直接单元测试**: 6 个函数的覆盖率来自集成测试间接路径（Controller 验证 80.00%）。S1 test allowlist 约束下无法新增 test file。若 S2 允许扩展 test file，建议补充直接单元测试。
2. **`_fs_storage_utils.py` error projection 函数无直接单元测试**: `_project_filesystem_error`、`_raise_path_free_error`、`_append_secondary_error_note` 的覆盖率来自上层集成路径（83.82%）。同上约束。
3. **legacy Ruff 152 fingerprint**: 既有 `72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散。不属于 R07-S1 owner。
4. **`edgar` 3 个 deprecation warning**: 既有安装环境问题，未扩散。

以上 residual 均不阻塞 re-review gate。

---

## 覆盖确认

| 维度 | 结论 |
|---|---|
| descriptor 为唯一 round-trip truth | ✅ 所有 point lookup/listing/recovery 通过 descriptor 校验，无目录名推断 |
| CR-F01 destructive cleanup complete preflight | ✅ filing/processed/rejected 三类均在 mutation 前完成 whole-candidate preflight |
| CR-F02 `begin_batch` primary-error preservation | ✅ 初始化主异常始终为 authoritative；cleanup/release 只附加 note |
| CR-F03/CV-F01 path-free exception graph | ✅ 完整 graph（cause/context/args/notes/traceback）无 locator |
| runtime lock adapter | ✅ 唯一调用点；保留 subclass/errno；不修改 runtime contract |
| terminal notes | ✅ 三处均复用 `_append_secondary_error_note`，只含 action/type/errno |
| opaque identity containment | ✅ Unicode/separator/drive/dot/dotdot round-trip 通过 containment |
| company alias 与 storage identity 分权 | ✅ alias resolution 只读，不修改 storage path |
| rejected findings 未被误实现 | ✅ 全部 11 项确认 |
| 无 S2/S3/R08+/Issue/统一 authorization 偷带 | ✅ |
| 四文件全量回归 | ✅ 363 passed |
| 静态检查 | ✅ pyright 0 errors + Ruff baseline 152 未扩散 |
