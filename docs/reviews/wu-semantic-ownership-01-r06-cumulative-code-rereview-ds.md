# WU-SEMANTIC-OWNERSHIP-01 R06 累计 S1+S2+S3 完整 Code Re-Review — AgentDS 第二路

## Review Identity

- **Reviewer**: AgentDS (DeepReview 第二路)
- **Date**: 2026-07-16
- **Mode**: Current Changes Mode（完整未提交 working tree）
- **Base**: `d048adf7ec1135aaf575384432ebf1137f8a34f2`（R06-S1 implementation gate transition commit）
- **Branch**: `phaseflow/host-issues-control`
- **Output**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-rereview-ds.md`
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **Gate**: R06 cumulative S1+S2+S3 code-review fix 之后的第二路完整 re-review
- **First review**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-controller-adjudication.md`
- **AgentCodex fix**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-fix-codex.md`
- **Controller fix validation**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-fix-controller-validation.md`

本 re-review 不是新 WU。目标是对完整累计 S1+S2+S3 working tree 执行独立第二路审查，重点：

1. 独立证明 R06-CR-F01 至 F04 全部关闭；
2. 确认此前 S1/S2 accepted findings 保持关闭；
3. 验证没有对 Accepted/Rejected/Deduplicated/Deferred 边界回归；
4. 执行 adversarial failure pass、semantic ownership drift、过度耦合、测试真实性、README 和安全边界审查。

## Scope

### Included Scope

57 changed files（~10,712 insertions, ~3,614 deletions），完整 uncommitted working tree diff from `d048adf7`：

**Storage infrastructure** (S1+S2 core):
- `dayu/fins/domain/document_models.py` — BatchToken, SourceDocumentProvenance, manifest items
- `dayu/fins/storage/repository_protocols.py` — 全部 6 个 public protocol
- `dayu/fins/storage/_fs_storage_infra.py` — core: transaction lifecycle, resolver, validator, recovery, publication guard, journal
- `dayu/fins/storage/_fs_blob_core.py` — blob-first staging
- `dayu/fins/storage/_fs_source_document_core.py` — source CRUD, guarded/unguarded read
- `dayu/fins/storage/_fs_company_meta_core.py` — company meta staging
- `dayu/fins/storage/_fs_maintenance_core.py` — filing maintenance staging
- `dayu/fins/storage/_fs_processed_core.py` — processed staging
- `dayu/fins/storage/_fs_storage_utils.py` — helpers

**Repository wrappers** (S1):
- `dayu/fins/storage/fs_batching_repository.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/fs_document_blob_repository.py`
- `dayu/fins/storage/fs_company_meta_repository.py`
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
- `dayu/fins/storage/fs_processed_document_repository.py`
- `dayu/fins/storage/local_file_source.py` — BinaryFileOpener protocol, _PublicationGuardedBinaryOpener

**Producer/Callback migration** (S3):
- `dayu/fins/ingestion_runtime.py` — `_store_downloaded_document`, `_store_rejected_filing_artifact`, `_preprocess_one_document`, `_rollback_batch_before_commit`
- `dayu/fins/service_runtime.py` — DefaultFinsRuntime composition root
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`

**Tests** (S1+S2+S3):
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/tools/test_combined_tools_acceptance.py`

**README / Control**:
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`

### Excluded Scope

- R07（storage revision, snapshot, retry, opaque ID）— deferred per plan §1.3
- Issue 142, 151, 175, 177, 178 — deferred
- 统一 tool authorization — 不在 scope
- `.venv/`, `__pycache__/`, generated artifacts

### Parallel Review Coverage

本 re-review 没有使用 subagent。Reviewer（AgentDS）独立完成了全部 57 个文件的关键路径走读、所有 accepted/rejected/deferred boundary 验证、以及 adversarial failure pass。

---

## R06-CR-F01..F04 Closure Ledger — 独立验证

### R06-CR-F01 — 单个不可解析 journal 必须 fail-closed、保留 evidence，并继续同轮 recovery

**修复位置**: `dayu/fins/storage/_fs_storage_infra.py:1256-1262`

**代码证据**:
```python
try:
    journal = _read_json_object(journal_path)
except ValueError:
    actions.append(
        f"skip batch transaction={token_dir.name} reason=unparseable_journal"
    )
    return actions
```

- 只捕获 `_read_json_object()` 的 `ValueError`（截断 JSON、空文件、非-object 根）
- `OSError` 未被捕获，真实文件系统错误仍向上传播
- malformed token 目录和 journal 原文均保留（不删除）
- `return actions` 后外层 for 循环继续处理后续合法 orphan

**测试证据**: `tests/fins/test_fins_storage_atomicity.py:1680-1724`
`test_unparseable_journal_preserves_evidence_and_later_orphan_recovers` — 3 个 parametrized case（截断 JSON `{`、空文件、非-object `[]`），每个 case 同时构造排序更后的合法 orphan。断言：
- malformed evidence 目录保留、原文保留
- 合法 orphan 同轮恢复
- published old 完整

**独立运行**: `3 passed in 0.66s`

**Verdict**: ✅ **CLOSED**。修复精确在 owner boundary（`_recover_single_batch_dir` per-entry），未放宽 journal 字段闭集、containment、symlink 或 phase 校验。

---

### R06-CR-F02 — SEC rebuild 取消与 operation/rollback 双失败语义

**修复位置**: `dayu/fins/pipelines/sec_rebuild_workflow.py:449-470`

**代码证据**:
```python
except BaseException as operation_error:
    try:
        batching_repository.rollback_batch(batch)
    except BaseException as rollback_error:
        operation_error.add_note(
            f"{_ROLLBACK_FAILURE_NOTE_PREFIX}: {rollback_error}"
        )
        raise operation_error from rollback_error
    if not isinstance(operation_error, Exception):
        raise
    return {
        "document_id": document_id,
        ...
        "status": "failed",
        "reason_code": "rebuild_write_failed",
        ...
    }
```

三条路径分流：
1. rollback 成功 + `KeyboardInterrupt` / `SystemExit` → 原 identity 继续传播
2. rollback 成功 + ordinary `Exception` → 保持既有 `failed` result
3. rollback 也失败 → operation 保持主异常 identity，rollback 为 `__cause__`，附加稳定 note `rollback_batch failed; recovery evidence retained`

`commit_batch()` 仍在 catch 外（line 471），commit-start 后不二次 rollback。

**测试证据**: `tests/fins/test_sec_pipeline_download.py:1398-1568`
- `test_sec_rebuild_rolls_back_once_and_reraises_cancellation_identity` — 2 parametrized case（KeyboardInterrupt, SystemExit）
- `test_sec_rebuild_operation_and_rollback_failure_preserve_primary_exception` — operation identity + cause + note
- `test_sec_rebuild_ordinary_failure_with_successful_rollback_returns_failed_result` — 既有行为回归

**独立运行**: `4 passed, 3 warnings in 0.72s`

**Verdict**: ✅ **CLOSED**。owner boundary 正确：单文档 batch lifecycle owner 决定异常优先级。CN rebuild 对照（`cn_download_rebuild.py`）未受影响——CN rebuild 由 caller 统一处理 rollback，不在此 owner。

---

### R06-CR-F03 — ingestion mutation owner 保留 operation 主异常

**修复位置**: `dayu/fins/ingestion_runtime.py:146-173`（新 helper）+ lines 3872, 4006, 4190（调用点）

**代码证据**:
```python
def _rollback_batch_before_commit(
    batching_repository: BatchingRepositoryProtocol,
    batch: BatchToken,
) -> None:
    operation_error = sys.exception()
    try:
        batching_repository.rollback_batch(batch)
    except BaseException as rollback_error:
        if operation_error is not None:
            operation_error.add_note(
                f"{_ROLLBACK_FAILURE_NOTE_PREFIX}: {rollback_error}"
            )
            raise operation_error from rollback_error
        raise
```

三条 caller-owned path 统一调用该模块级私有 helper：
- `_store_downloaded_document:3872` — 已有正确语义，收敛到 helper
- `_store_rejected_filing_artifact:4006` — 此前缺失，已修复
- `_preprocess_one_document:4190` — 此前缺失，已修复

helper 不建立跨模块 callback/facade/framework。`BaseException` 捕获确保 rollback 自身为取消类异常时也不替换 operation 主异常。

**测试证据**: `tests/fins/test_fins_ingestion_runtime.py:1514-1628`
- `test_store_rejected_artifact_double_failure_preserves_operation_identity`
- `test_preprocess_double_failure_preserves_operation_identity`

两条测试均断言：operation identity、rollback `__cause__`、稳定 note、单次 rollback。

**独立运行**: `2 passed, 3 warnings in 0.79s`

**Verdict**: ✅ **CLOSED**。三条 path 统一收敛到同一模块 owner helper，语义一致。

---

### R06-CR-F04 — publication barrier test 必须同步到真实 reader lock-acquire 点

**修复位置**: `tests/fins/test_fins_storage_atomicity.py:91-130`（`_PublicationGuardAcquireSignal` class）+ lines 2813-2842（`_read_source_ids_in_process` 函数）+ lines 2264-2367（`test_concurrent_reader_blocks_at_each_publication_rename_barrier`）

**代码证据**:

child 进程（`_read_source_ids_in_process`）：
```python
repository_set = build_fs_repository_set(workspace_root=Path(workspace_root))
repository = FsSourceDocumentRepository(
    Path(workspace_root),
    repository_set=repository_set,
)
core = repository_set.core
signalling_acquire = _PublicationGuardAcquireSignal(
    connection,
    core._acquire_publication_guard,
)
with patch.object(core, "_acquire_publication_guard", signalling_acquire):
    document_ids = repository.list_source_document_ids("AAPL", SourceKind.FILING)
```

`_PublicationGuardAcquireSignal.__call__`：
```python
self._connection.send_bytes(b"publication_acquire_entered")
return self._acquire(ticker)
```

parent 进程验证：
```python
assert parent_connection.recv_bytes() == b"publication_acquire_entered"
with pytest.raises(RuntimeError, match="已存在跨进程活动 batch"):
    core._acquire_lock_token(
        core._publication_lock_path("AAPL"),
        blocking=False,
    )
allow_rename.set()
```

关键改进：
- child 在真实 `_acquire_publication_guard()` 调用点发送同步信号（不是 repository 构造前）
- parent 用同一 publication lock 的真实 non-blocking acquire 证明 writer 正持有 guard（不是 `poll(0.25)` 推断）
- child 显式通过 `build_fs_repository_set()` 创建 repository_set 并注入 `FsSourceDocumentRepository`（不反射 concrete repository 私有属性）
- 无 production debug flag、sleep 或 fake policy

**独立运行**: `2 passed in 1.26s`

**独立扫描**: `poll(0.25)` / `send_bytes(b"ready")` / 私有属性反射均为 0 命中。

**Verdict**: ✅ **CLOSED**。同步 seam 精确收紧到真实 storage publication guard acquire 边界。

---

## 此前 S1/S2/S3 Accepted Findings Re-Verification

每个 finding 均用当前代码直接证据逐项复核。

| Finding | 内容 | 当前代码证据 | 状态 |
| --- | --- | --- | --- |
| R06-S1-CR-F01 | maintenance private unguarded read helper | `_fs_maintenance_core.py:377-413`：`read_rejected_filing_file_bytes`（public, guarded）获取 publication guard 后委托 `_read_rejected_filing_file_bytes_unguarded`（private, unguarded）；public self-call scan = `[]` | ✅ CLOSED |
| R06-S1-CR-F02 | 删除 processed-meta 回退描述 | `_fs_processed_core.py:181-204`：`get_processed_meta` docstring 只承诺读取 ``tool_snapshot_meta.json``；实现只有 published `_get_processed_meta_unguarded` 路径，无 `meta.json` fallback | ✅ CLOSED |
| R06-S1-CR-F03 | shared-core `mark_processed_reprocess_required` 返回 `None` | `_fs_processed_core.py:234-260`：返回类型 `-> None`；`required=False` 时 early return `None`；protocol/wrapper 同为 `None`；production return consumer = 0 | ✅ CLOSED |
| R06-S2-CR-F01 | primary mismatch 返回 `None` 不猜 first file | `_fs_storage_utils.py:396-416`：`_resolve_primary_uri` — `primary_name` 为空返回 `None`；只接受 file entry canonical name 精确匹配；未命中返回 `None`；`file_payloads[0]` fallback scan = 0 | ✅ CLOSED |
| R06-S3-CV-F01 | preprocess selection missing `ingest_complete` fail closed | `ingestion_runtime.py:4069`：`meta.get("ingest_complete") is not True` 正确拒绝缺失键和显式 `False`；owner test `test_preprocess_selection_rejects_missing_completion_and_keeps_complete_source` 存在并通过 | ✅ CLOSED |

---

## All Rejected/Deduplicated/Deferred Boundary Verification

对原累计 review Controller adjudication 中全部 rejected/deduplicated/deferred 项逐项验证，未发现偷带：

| Finding | 裁决 | 当前状态验证 |
| --- | --- | --- |
| `R06-CR-MIMO-F01` | REJECTED — `SWAPPED_TARGET` 是 pre-commit，不是 committed | ✅ `_PHASE_SWAPPED_TARGET` 写入仍在 rename 之后（line 352→353），journal/phase/recovery 处理完全相同。`test_swapped_target_recovery_without_old_target_deletes_new_target` 仍存在并通过 |
| `R06-CR-MIMO-F03` | REJECTED — force-release lock 不安全 | ✅ 无 `force_release`、`unlock_publication`、`remove.*lock.*file` 代码。retained operational residual 仍由 `dayu.runtime.filelock` / process termination 承担 |
| `R06-CR-MIMO-F05` | REJECTED — BatchToken 字段符合 plan | ✅ `BatchToken(transaction_id: str, ticker: str)` 未变，无 `__slots__`、property 或隐藏字段 |
| `R06-CR-MIMO-F06` | REJECTED — 不新增格式 validation | ✅ BatchToken 无 `__post_init__`；只两处 `__post_init__` 在 `DownloadRejectionEntry`（line 200）和另一既有 model（line 298），均非 R06 新增 |
| `R06-CR-MIMO-F07` | REJECTED — pre-existing/out of scope | ✅ processed manifest 字段投影未改；mutation 只接 caller batch/staging |
| `R06-CR-MIMO-F08` | REJECTED — pre-existing/out of scope | ✅ `DocumentSummary.from_dict` 的 `source_kind` 默认值未改 |
| `R06-CR-MIMO-F09` | REJECTED — pre-existing/out of scope | ✅ rejected-artifact 列表读取契约未改 |
| `R06-CR-MIMO-F10` | REJECTED — pre-existing/non-defect | ✅ `_upsert_processed` 写入顺序未改；staging 中写入由 caller rollback 保护 |
| `R06-CR-MIMO-F11` | REJECTED — validator 不应扩展 scope | ✅ `_validate_complete_source_tree` 只校验 source tree；无 processed/company/maintenance validator |
| `R06-CR-MIMO-F12` | REJECTED — overdesign | ✅ blob-first 是 producer sequence；storage 未添加写入顺序/时间戳校验 |
| `R06-CR-MIMO-F14` | REJECTED — test intent misread | ✅ `test_concurrent_composed_source_read_and_delayed_open_do_not_self_deadlock` 保持 `max_workers=1`，测试目标是证明单线程内不会自死锁 |
| `R06-CR-MIMO-F15` | REJECTED — non-material | ✅ SEC pipeline adapter 仍访问 `_batching_repository` 等私有属性；无有效语义的 passthrough property |
| `R06-CR-DS-F03` | REJECTED — composition-root misread | ✅ `CnPipeline`/`SecPipeline` 的 `or` fallback 未改；Controller 已裁决为正确共享行为 |
| `R06-CR-DS-F04` | REJECTED — duplicate impossible-state test | ✅ 未新增 `ingest_complete=False` 测试；storage validator negative tests 已覆盖 |
| `R06-CR-DS-F05` | REJECTED — downstream duplicate assertion | ✅ SEC pipeline 测试未新增 `ingest_complete=True` 重复断言 |
| `R06-CR-DS-F06` | DEFERRED — R07 owned | ✅ 未新增 revision-change-after-build 测试；`SourceDocumentRevision` 为 pre-existing type |

**结论**: 所有 rejected/deduplicated/deferred 项均未偷带。无 precommit `SWAPPED_TARGET` 改为 committed，无 force-release lock，无 BatchToken public shape 改变，无 source validator 吸收 processed/company/maintenance，无 R07 revision/snapshot/opaque-id/retry/cache 进入，无 Issue 142/151/175/177/178 或统一 authorization 进入。

---

## Independent Scan Evidence

以下扫描均由 AgentDS 独立执行（非 AgentCodex 自报复用）：

| Scan | Command / Boundary | Result |
| --- | --- | --- |
| Ambient authority | `rg -n 'ContextVar\|_BATCH_OWNER_CONTEXT\|owner_scope_id\|owner_token\|current_task\|get_ident\|thread.*ident\|_execute_with_auto_batch\|auto_batch' dayu/fins/storage tests/fins` | **0 hits** |
| Ack / false-completion | `rg -n 'stage_source_document\|_STAGING_STABLE_META_FIELDS\|staging.*ack\|ingest_complete.*False\|ingest_complete.*false' dayu/fins tests/fins` | **2 hits**（`test_fins_storage_provider.py:1444` 与 `:3478`，均为 validator negative tests）；production = 0 |
| Journal process facts | `rg -n 'owner_pid\|hostname' dayu/fins/storage/_fs_storage_infra.py tests/fins` | **0 hits** |
| Deferred scope | `rg -n 'SourceDocumentRevision\|source_snapshot\|snapshot_handle\|bounded_retry\|force.release.*lock\|unified.*authorization' dayu/fins tests/fins` | `SourceDocumentRevision` 命中均为 pre-existing type（非 R06 新增） |
| F04 old sync | `rg -n 'poll\(0\.25\)\|send_bytes\(b"ready"\)' tests/fins/test_fins_storage_atomicity.py` | **0 hits** |
| Optional/default batch | `rg -n 'BatchToken.*None\|Optional\[BatchToken\]\|batch=None\|batch: BatchToken =' dayu/fins/storage dayu/fins/ingestion_runtime.py dayu/fins/pipelines dayu/fins/downloaders` | **0 hits**（唯一命中是 `sec_download_filing_workflow.py:427` 的 local variable type annotation，不是 parameter default） |
| `hasattr`/`getattr` in infra | `rg -n 'hasattr\|getattr' dayu/fins/storage/_fs_storage_infra.py` | **0 hits** |
| Whitespace | `git diff --check d048adf7` | **exit 0** |

---

## Independent Test Matrix Verification

| Matrix | Command | Exit | Result |
| --- | --- | ---: | --- |
| F01-F04 direct owner | `pytest -q` 11 tests | 0 | `11 passed, 3 warnings in 1.67s` |
| S1+S2 storage/read | `pytest -q` 4 files | 0 | `238 passed, 3 warnings in 9.19s` |
| S3 producer/callback | `pytest -q` 6 files | 0 | `197 passed, 3 warnings in 4.07s` |
| Full aggregate | `pytest -q tests/fins tests/tools/test_combined_tools_acceptance.py` | 0 | `732 passed, 1 skipped, 3 warnings in 21.70s` |

唯一 skip 是既有可选 Docling integration 环境门控。三条 warning 均来自 `edgar` 依赖的既有 deprecation warning。

---

## Independent Type/Lint Verification

| Validation | Command | Exit | Result |
| --- | --- | ---: | --- |
| Full pyright | `pyright` | 0 | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff | `git diff --name-only d048adf7 -- '*.py' \| xargs ruff check` | 0 | `All checks passed!` |

---

## Adversarial Failure Pass — Re-Verified Safe

以下 adversarial scenarios 经直接代码路径验证，**未发现回归**：

| Scenario | Verification | Status |
| --- | --- | --- |
| begin_batch 后 staging 准备失败 → lock 释放 + staging 清理 | `_fs_storage_infra.py:304-313` | ✅ Safe |
| commit 前 validator 失败 → precommit rollback 恢复 old | `_fs_storage_infra.py:355-360` | ✅ Safe |
| commit 内 physical swap 失败 → backup 恢复 + rollback journal | `_fs_storage_infra.py:357-360` | ✅ Safe |
| COMMITTED journal 后 cleanup 失败 → post-commit error 不 rollback | `_fs_storage_infra.py:403-427` | ✅ Safe |
| rollback 后 staging 清理 → 即使 journal 写入失败也清理 | `_fs_storage_infra.py:913-914` | ✅ Safe |
| 同 ticker 第二 begin → RuntimeError | `_fs_storage_infra.py:277-278` | ✅ Safe |
| cross-core token → ValueError | `_fs_storage_infra.py:942-944` | ✅ Safe |
| 已 commit token 再次 mutation → ValueError | `_fs_storage_infra.py:957-958` | ✅ Safe |
| publication guard 释放失败 on committed → post-commit error（不回滚） | `_fs_storage_infra.py:371-378` | ✅ Safe |
| reader 在长 staging/validator 期间读取 → 不阻塞，读 old | 长事务只持 writer mutex | ✅ Safe |
| reader 在两个 rename barrier → publication guard 阻塞，终态只见 old/new | `_PublicationGuardAcquireSignal` + deterministic sync | ✅ Safe |
| writer/recovery 锁顺序 → writer first, publication second | begin→writer mutex only; commit→validator(no guard)→publication guard | ✅ Safe |
| 6-K primary selection 不读 staging | `select_prepared_6k_primary_document` 接收 `candidate_payloads` 参数 | ✅ Safe |
| `Source.open()` 重新获取 publication guard | `_PublicationGuardedBinaryOpener` → acquire → open fd → release | ✅ Safe |
| containment escape 拒绝 | `_require_contained_path` 解析 root + path，`relative_to` 校验 | ✅ Safe |
| symlink escape 拒绝 | validator 拒绝 symlink staging root, source root, meta, files | ✅ Safe |
| `ingest_complete=False` 被 validator 拒绝 | `_validate_complete_source_tree:444` | ✅ Safe |
| CN company meta + Docling document 分离短 transaction | `cn_download_workflow.py:208-220` + `cn_pipeline.py:908-920` | ✅ Safe |
| SEC company/filing/maintenance 独立短 transaction | `sec_download_workflow.py:487-499, 618-636` | ✅ Safe |
| Docling prepare 阶段 `ingest_complete` 固定 True | `docling_upload_service.py:719` | ✅ Safe |
| F01: malformed journal 保留 evidence + 继续 recovery | `_recover_single_batch_dir:1256-1262` | ✅ Safe (NEW) |
| F02: SEC rebuild 取消传播 + 双失败 cause/note | `sec_rebuild_workflow.py:449-470` | ✅ Safe (NEW) |
| F03: ingestion rejected/preprocess 双失败保留 operation | `_rollback_batch_before_commit` + 两条 path | ✅ Safe (NEW) |

---

## Semantic Ownership Drift Check

| 语义 | 唯一 Owner | Drift 证据 | 状态 |
| --- | --- | --- | --- |
| transaction authority | `BatchToken` + `_resolve_active_batch` | 无；删除全部 ambient authority | ✅ Converged |
| public token fields | `BatchToken(transaction_id, ticker)` | 无；不含 owner/scope/PID/hostname/path | ✅ Converged |
| mutation authority | `batch: BatchToken` keyword-only | 全部 54 mutation 显式 batch | ✅ Converged |
| lifecycle | `BatchingRepositoryProtocol` only | 无；Source protocol 已删除 lifecycle | ✅ Converged |
| publication completeness | storage validator (`_validate_complete_source_tree`) | producer 不写 `ingest_complete=False` | ✅ Converged |
| staging staging | storage internal `_ActiveBatchState` | 不进入 public token 或业务 meta | ✅ Converged |
| online read consistency | publication swap guard + `_PublicationGuardedBinaryOpener` | reader 不进 rename 空窗 | ✅ Converged |
| journal facts | `{transaction_id, ticker, phase}` only | 不含 PID/hostname/absolute path | ✅ Converged |
| source provenance | `SourceDocumentProvenance.from_meta` typed owner | 不从 document_id 前缀猜测 | ✅ Converged |
| pre-commit rollback error | `_rollback_batch_before_commit` 模块级 helper | 三条 path 统一语义，不再有不一致 | ✅ Converged |
| callback batch | invocation-time explicit keyword argument | `partial` 不 capture batch | ✅ Converged |

**结论**: R06 成功将语义所有权从三个分散 owner 收敛到唯一 storage owner boundary。F01-F04 修复进一步消除了 recovery isolation、cancellation/rollback priority 和 test synchronization 的最后三个 owner 缺口。未发现 semantic ownership drift。

---

## Over-Coupling Check

| 检查项 | 状态 |
| --- | --- |
| storage core ↔ producer 耦合 | separated：producer 只传 batch，不拥有 lifecycle ✅ |
| writer mutex ↔ publication guard 耦合 | separated：两个独立 lock file，不同生命周期 ✅ |
| source meta ↔ transaction staging 耦合 | separated：`ingest_complete` 不再是 staging ack ✅ |
| journal ↔ public token 耦合 | separated：journal 只有 {transaction_id, ticker, phase} ✅ |
| read runtime ↔ storage revision 耦合 | separated：revision 由 storage owner 统一计算 ✅ |
| CN ↔ Docling transaction 耦合 | separated：各自短 transaction ✅ |
| SEC company ↔ filing ↔ maintenance transaction 耦合 | separated：三个独立短 transaction ✅ |
| ingestion rollback ↔ 跨模块 framework 耦合 | separated：模块级私有 helper，不跨模块 ✅ |

**结论**: 未发现过度耦合。F01-F04 修复未引入新的层间依赖。

---

## README Audit

- `dayu/fins/README.md`：已陈述 batching-only lifecycle、commit 前失败/取消 exactly-once rollback、publication guard 与 crash recovery。F01-F03 是同一 contract 的错误分支修复，不追加 review/finding 实现细节。✅ No diff needed.
- `tests/README.md`：已陈述 commit/rollback fence、rename window、fresh recovery 与 old/new 测试职责。F01/F04 增强同一测试层的 owner case 与同步证明。✅ No diff needed.
- 根 `README.md`：无安装、CLI、输出、workspace、用户流程或排障变化。✅ No diff.
- `dayu/README.md`：无 `UI -> Service -> Host -> Engine` 分层/装配变化。✅ No diff.
- `docs/fins/design.md`：stable owner 决策未变。✅ No diff.

---

## Plan Conformance

对照 accepted plan §1–§13 逐项核对：

| Plan § | Requirement | Status |
| --- | --- | --- |
| §3.1 | BatchToken 只含 transaction_id + ticker | ✅ |
| §3.2 | internal resolver 五条校验规则 | ✅ |
| §3.3 | 只有 BatchingRepositoryProtocol 声明 lifecycle | ✅ |
| §3.4 | 全部 mutating protocol 有 required `batch=` | ✅ |
| §3.5 | 四个 composition roots shared core | ✅ |
| §4.1 | writer mutex 只作 writer exclusion | ✅ |
| §4.2 | publication swap guard 分离，reader F04 deterministic | ✅ |
| §4.3 | journal 字段闭集 | ✅ |
| §5.1 | blob-first, final source once | ✅ |
| §5.2 | commit validator 遍历完整 staged tree + 双向 manifest | ✅ |
| §6 | 全部 producer/callback 迁移，F02/F03 关闭了双失败缺口 | ✅ |
| §7 | 三 slice 累计 breaking cutover | ✅ |
| §8 | Aggregate validation, scans, smoke | ✅ |
| §9 | README trigger 决策 | ✅ |
| §10 | Baseline failure registry | ✅ |
| §11 | Stop conditions — 未触发 | ✅ |
| §1.3 | 未实施 R07, Issue 142/151/175/177/178, unified authorization | ✅ |

---

## Findings

**本次 re-review 未发现新的 material findings。**

此前 AgentDS first-review F01-F06 状态：
- F01: ✅ 已由 accepted F01 修复并关闭（详见 Closure Ledger）
- F02: ✅ 已由 accepted F03 修复并关闭（详见 Closure Ledger）
- F03: ✅ REJECTED（Controller 裁决 composition-root misread）
- F04: ✅ REJECTED（Controller 裁决 duplicate impossible-state test）
- F05: ✅ REJECTED（Controller 裁决 downstream duplicate assertion）
- F06: ✅ DEFERRED（Controller 裁决 R07 owned）
- F07: **RETRACTED AS NON-MATERIAL CURRENT FINDING** — 原始 finding 指出 `store_file` 的两套路径构造链（containment 校验 vs file_store 写入）可能分叉。当前代码直接证据（`_fs_blob_core.py:213` containment check + `:217-219` write path）：
  - containment check 以 `handle_dir = staging_ticker_dir / source_dir / document_id` 为 root 校验 filename 不越界（`_resolve_handle_child_path_for_state:1530-1557`）
  - write path 以 `LocalFileStore(root=staging_ticker_dir.parent)` + key `{ticker}/{source_dir}/{doc_id}/{filename}` 写入（`_build_file_store:1655-1671` → `_file_store_root_for_ticker:1963-1979` → `_build_store_key_from_normalized_filename:1692-1718`）
  - 当前 concrete 实现下，两路径解析到同一物理位置：`staging_ticker_dir.parent / ticker / source_dir / doc_id / filename` ≡ `handle_dir / filename`
  - 所有 production path 均使用默认 `LocalFileStore`；无 custom `FileStore` 注入路径（`_file_store` cache line 1669-1670 未被任何外部调用改写）
  - 无实际路径分叉、containment bypass 或 published half-source 风险证据
  - Controller 原 adjudication 未覆盖 F07（该 finding 为 DS first-review artifact 末尾晚追加）；本轮不替 Controller 裁决，保留为 retracted non-material observation

此前 AgentMiMo first-review F01-F16 状态：
- F01: ✅ REJECTED（Controller 裁决 `SWAPPED_TARGET` 不是 committed）
- F02: ✅ 已由 accepted F02 修复并关闭
- F03: ✅ REJECTED（Controller 裁决 unsafe remedy）
- F04: ✅ 已由 accepted F03 修复并关闭
- F05-F12: ✅ REJECTED
- F13: ✅ 已由 accepted F04 修复并关闭
- F14-F15: ✅ REJECTED
- F16: ✅ MERGED INTO F02（同一 lifecycle-owner 修复）

---

## Open Questions

无。

---

## Residual Risk

1. **Publication lock release syscall 失败**：仍由 `dayu.runtime.filelock` / process termination 安全恢复承担。属于 retained operational residual，不在 R06 scope。
2. **R07 独占 residual**：跨多次 read / processor cache 的 snapshot/revision consistency 仍由 R07 独占。R06 成功保证一次 published read/open 不进 rename 空窗。
3. **三条 edgar deprecation warning**：既有依赖问题，非 R06 引入。
4. **唯一 test skip**：Docling integration 环境门控，属于既有可选测试。

---

## Final Verdict

**PASS — READY_FOR_CONTROLLER_ADJUDICATION**

- **R06-CR-F01..F04**: 全部关闭，每个 finding 都有直接 owner 代码证据和独立通过的 owner test。
- **此前 S1/S2/S3 accepted findings**: 全部五项保持关闭（R06-S1-CR-F01..F03, R06-S2-CR-F01, R06-S3-CV-F01），均有当前代码直接证据。
- **全部 rejected/deduplicated/deferred 项**: 逐项确认未偷带。
- **New material findings**: 0。
- **DS first-review F07**: 本轮 retracted as non-material current finding；直接代码证据见 Findings 节。Controller 原 adjudication 未覆盖，待 Controller 显式裁决。
- **Blocking questions**: 0。
- **回归**: 无。732 全量测试通过，pyright = 0 errors，scoped Ruff = 0。
- **R06 累计 working tree**: 符合 accepted plan，所有 required contract（显式 BatchToken authority、完整 source 单次 publication、validator、commit/recovery/publication guard、cancellation/primary-error、shared-core composition、reader old/new 原子性）均已收敛，无 regression。

AgentDS 第二路 re-review 确认 R06 完整累计 S1+S2+S3 tree 已准备好进入 Controller final R06 accepted commit 裁决。

## READY_FOR_CONTROLLER_ADJUDICATION
