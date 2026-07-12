# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2

## Artifact Metadata

- Review type: adversarial deep code review (current changes mode)
- Target slice: `S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets`
- Branch: `phaseflow/host-issues-control`
- Base: `main` (via uncommitted workspace diff)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-ds.md`
- Timestamp: 2026-07-13T00:47:03+08:00
- Risk profile: production-high
- Status: pass

## Scope

### Included（15 files, 均在 accepted plan S2 allowed set 内）

**Production**（8 files）:

- `dayu/fins/pipelines/docling_upload_service.py` — upload non-delete 统一 caller-owned batch, `commit_started` 所有权切换, `try/finally` operation rollback, 双错误传播
- `dayu/fins/ingestion_runtime.py` — generic download 同批次原子提交, 相同 token lifecycle 模式
- `dayu/fins/pipelines/cn_download_filing_workflow.py` — CN/HK async generator 重构: 网络/转换/yield 在 batch 外; 新增 `_commit_cn_filing_assets_batch()` 与 `_commit_cn_filing_metadata_batch()` 两个同步 batch wrapper; 新增 `_rollback_cn_batch_preserving_primary()` 公共 rollback helper
- `dayu/fins/pipelines/cn_download_source_upsert.py` — `commit_cn_filing_source_document` docstring 明确 stage-only contract
- `dayu/fins/pipelines/cn_download_models.py` — `DownloadedReportAsset.pdf_path: Path` → `pdf_bytes: bytes`
- `dayu/fins/pipelines/cn_download_protocols.py` — protocol docstring 同步
- `dayu/fins/downloaders/cninfo_downloader.py` — 删除 `tempfile`/`NamedTemporaryFile`/临时目录; 直接返回 `pdf_bytes`
- `dayu/fins/downloaders/hkexnews_downloader.py` — 同上

**Test**（7 files）:
- `tests/fins/test_docling_upload_service.py` — batch identity 验证, commit failure 不 caller rollback, dual error, create failure absence, update/overwrite failure 旧状态保持
- `tests/fins/test_fins_ingestion_runtime.py` — generic create failure absence, commit failure 不 caller rollback
- `tests/fins/test_cn_download_workflow.py` — replacement batch identity, fast-skip batch identity, replacement failure 恢复旧版本, replacement success 原子可见, CancelledError rollback, commit failure 不 caller rollback, PDF/Docling failure absence, inner/outer generator close 无 partial
- `tests/fins/test_cn_download_runtime.py`, `tests/fins/test_cn_pipeline.py` — fixture/constructor 迁移
- `tests/fins/test_cninfo_downloader.py`, `tests/fins/test_hkexnews_downloader.py` — `pdf_path` → `pdf_bytes` assertions

### Excluded

- S3 Host/Service wait adapter files、README、design docs、control docs — 未修改
- S1 storage files — prerequisite accepted commit `6e9ad77e`

### Sources of truth consulted

- `AGENTS.md`、accepted plan、plan re-review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-controller-validation.md`

---

## Review Walkthrough

以下按 accepted plan 的 9 个重点维度逐一走读。

### 1. S2 allowed file scope

Changed files vs plan allowed set:

| Plan allowed | 实际修改 | 匹配 |
|---|---|---|
| `docling_upload_service.py` | ✅ | ✅ |
| `ingestion_runtime.py` | ✅ | ✅ |
| `cn_download_filing_workflow.py` | ✅ | ✅ |
| `cn_download_models.py` | ✅ | ✅ |
| `cn_download_protocols.py` | ✅ | ✅ |
| `cn_download_source_upsert.py` | ✅ | ✅ |
| `cninfo_downloader.py` | ✅ | ✅ |
| `hkexnews_downloader.py` | ✅ | ✅ |

无越界修改。无 S3/Host/Service/Engine/README/design docs 修改。`rg 'from dayu\.(host|service|ui|engine)'` 在 S2 生产文件中零命中。✅

### 2. upload / generic / CN-HK caller-owned single document batch

**Upload service** (`docling_upload_service.py:331-428`)：

```text
token = begin_batch(ticker)         # 无条件开启（不再仅 overwrite 场景）
commit_started = False
try:
    [file read/validation/conversion — batch 外完成]
    _acknowledge_source_before_blob_write()  # 只 stage，不 begin/commit/rollback
    [blob writes]
    [final meta upsert]
    commit_started = True
    commit_batch(token)              # token 所有权转交 storage
finally:
    if not commit_started:
        operation_error = sys.exception()
        try: rollback_batch(token)
        except: add_note + raise operation_error from rollback_error
```

关键变化：
- 旧代码 `token: BatchToken | None = None` + `if replace_existing: token = begin_batch()` — 只有 overwrite 场景才开 batch
- 新代码 `token: BatchToken = self._source_repository.begin_batch(ticker)` — 所有 non-delete create/update/overwrite 都开 batch ✅
- 旧代码 `token = None` 绕过 commit failure 后的 rollback 状态判断
- 新代码 `commit_started` flag 精确区分 operation error（caller rollback）和 commit error（不 rollback）✅

**Ingestion runtime** (`ingestion_runtime.py:3791-3827`)：相同 `commit_started` + `try/finally` 模式。✅

**CN/HK workflow** — 两种路径：

- Normal path: `_commit_cn_filing_assets_batch()` — 同步函数，顺序为 `begin → reset → ack → blob:pdf → blob:json → final_meta → processed_marker → commit_started=True → commit_batch`，finally `_rollback_cn_batch_preserving_primary()`
- Fast-skip path: `_commit_cn_filing_metadata_batch()` — 同步函数，仅 `begin → final_meta → commit_started=True → commit_batch`，finally 同

测试 `test_cn_replacement_uses_one_batch_for_reset_ack_blobs_final_and_processed` 验证：8 个 phase 使用同一个 `batch_id`，`begin_calls == 1`, `commit_calls == 1`, `rollback_calls == 0`。✅

### 3. operation exception/cancellation rollback vs commit_batch storage-owned lifecycle

**所有三个 caller** 遵循同一规则：

| 异常类型 | commit_started | 行为 |
|---|---|---|
| operation exception（blob write / final upsert 失败） | False | finally rollback ✅ |
| `asyncio.CancelledError`（同步注入） | False | finally rollback ✅ |
| `CnDownloadCancelledError`（batch 内同步检查） | False | finally rollback ✅ |
| `commit_batch()` 本身失败 | True | 不 rollback，caller 传播 storage exception ✅ |

测试覆盖：
- `test_cn_active_batch_sync_cancelled_error_rolls_back_once`: 同步 `CancelledError` 在 batch 内第 3 次检查触发，断言 `rollback_calls == 1, commit_calls == 0`，document absent ✅
- `test_execute_upload_commit_failure_does_not_call_caller_rollback`: commit failure → `caller_rollback_calls == 0`，document absent ✅
- `test_cn_commit_failure_does_not_trigger_caller_rollback_or_success`: CN commit failure → `rollback_calls == 0`，无 `FILING_COMPLETED` event ✅
- `test_store_downloaded_document_commit_failure_does_not_caller_rollback`: generic commit failure → `caller_rollback_calls == 0`，document absent ✅

### 4. commit failure no second rollback

上文所有 commit failure 测试均断言 `caller_rollback_calls == 0` / `rollback_calls == 0`。✅

`_CommitFailingUploadSourceRepository.commit_batch()` 内部先 `rollback_batch(self, token)`（storage owner 自己在 commit 失败时恢复 pre-commit 状态）再抛 `OSError`，caller 只传播不额外 rollback。这符合 plan S1 storage owner 的 contract：`commit_batch` 已消费 token 并负责 rollback/recovery。✅

### 5. rollback failure primary/note/cause

**Upload** (`docling_upload_service.py:419-428`)：
```python
operation_error.add_note("rollback_batch failed; recovery evidence retained: ...")
raise operation_error from rollback_error
```

**Ingestion runtime** (`ingestion_runtime.py:3817-3823`)：相同模式。

**CN/HK** (`cn_download_filing_workflow.py` — `_rollback_cn_batch_preserving_primary`)：相同模式。

测试覆盖：
- `test_execute_upload_operation_and_rollback_failure_preserve_both_errors`: 断言 `isinstance(exc_info.value.__cause__, OSError)`, `"forced rollback failure"` in `__cause__`, `"recovery evidence retained"` in `__notes__` ✅

### 6. active batch segment no await/yield

**Upload service**: `execute_upload()` 是同步方法，无 `await`/`yield`。✅

**Ingestion runtime**: `_store_downloaded_document()` 是同步方法，无 `await`/`yield`。✅

**CN/HK workflow**: `_commit_cn_filing_assets_batch()` 和 `_commit_cn_filing_metadata_batch()` 均为同步函数，内部无 `await`/`yield`。async generator `run_cn_download_single_filing_stream` 的 `yield`（progress events）全部在 batch 函数调用之前。✅

### 7. `commit_cn_filing_source_document` stage-only contract

`cn_download_source_upsert.py:209-213`：
```text
本 helper 不是事务 commit owner：它不调用 begin_batch、commit_batch 或 rollback_batch。
调用方必须先持有与 ticker 对应的 active token，并把本 helper 与相关 reset、ack、blob
写入放在同一同步 batch 段内，最后由 caller 唯一一次调用 commit_batch。
```

实施确认：函数体内只调用 `source_repository.create_source_document()` / `update_source_document()` 和 `processed_repository.mark_processed_reprocess_required()`，不调用 begin/commit/rollback。✅

测试 `test_cn_pdf_sha_skip_final_meta_uses_one_caller_batch`：fast-skip 路径 `phases == ["begin", "final_meta", "commit"]`，`batch_ids` 只有 1 个，`begin_calls == 1`, `commit_calls == 1`。✅

### 8. fast-skip and normal-convert same token

- **Normal convert**: `_commit_cn_filing_assets_batch()` → phases: `begin, reset, ack, blob:pdf, blob:json, final_meta, processed_marker, commit`
- **Fast-skip**: `_commit_cn_filing_metadata_batch()` → phases: `begin, final_meta, commit`

两个函数都各自开启唯一的 caller batch，`commit_cn_filing_source_document` 在两者中都只 stage、不另开 batch。测试 `test_cn_replacement_uses_one_batch_for_reset_ack_blobs_final_and_processed` 和 `test_cn_pdf_sha_skip_final_meta_uses_one_caller_batch` 分别覆盖。✅

### 9. source/blob/final meta/processed marker atomic visibility

**Replacement success** (`test_cn_replacement_success_exposes_source_blobs_and_processed_marker_together`)：
- 先写入旧 source + blob + processed marker
- 发起 replacement（new pdf_bytes + overwrite=True）
- commit 成功后断言：`source_meta["ingest_complete"] is True`, new PDF blob 可读, new Docling blob 可读, `processed_meta["reprocess_required"] is True`
- 四者同时可见 ✅

**Replacement failure** (`test_cn_replacement_final_failure_restores_old_source_and_blobs`)：
- 先写入旧 source + blob, 记录 `old_meta`/`old_pdf`/`old_docling`
- 设置 `fail_final = True`
- 发起 replacement → 失败
- 断言：`source_meta == old_meta`（旧 meta 不变），`pdf == old_pdf`, `docling == old_docling`（旧 blob 不变）
- `rollback_calls == 1` ✅

**Create failure** (`test_execute_upload_create_final_failure_leaves_document_absent`)：
- 旧测试断言 `meta["ingest_complete"] is False` 且 blob entries 存在（固化 incomplete staging）
- 新测试断言 `FileNotFoundError`（source meta 不存在），`blob_repository.list_entries(handle) == []`
- 从"保留 incomplete staging"迁移到"document absent" ✅

**Download failure** (`test_cn_pdf_download_failure_leaves_document_absent`, `test_cn_docling_conversion_failure_leaves_document_absent`)：
- PDF download 和 Docling conversion 均在 batch 外失败
- 断言 source meta 不存在 ✅

### DownloadedReportAsset pdf_bytes owner

**Type owner** (`cn_download_models.py:247`): `pdf_bytes: bytes` 替代 `pdf_path: Path` ✅

**Downloaders**: 移除 `tempfile`/`NamedTemporaryFile`/临时目录/unlink handoff。HTTP request/URL/redirect/TLS/retry/`response.content`/PDF magic bytes 校验行为不变。✅

**Contract scans**（controller validation 确认）:
- `rg "NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path"` → 零命中
- `rg '\.pdf_path\b|pdf_path[[:space:]]*[:=]'` → 零命中（仅合法 `DownloadedReportAsset` type/import/docstring）
- `rg 'DownloadedReportAsset[[:space:]]*\('` → 2 production + 4 test constructors，全部使用 `pdf_bytes=`

无兼容 property/re-export/lazy import。✅

### 测试覆盖 plan rollback matrix

对照 plan S2 `Required state/rollback matrix`（8 种路径 × 失败点）：

| Plan path | 测试覆盖 |
|---|---|
| upload create → blob write / final upsert / commit failure → document absent | `test_execute_upload_create_final_failure_leaves_document_absent` ✅ |
| upload update/overwrite → failure → old source/blob 不变 | `test_execute_upload_update_failure_keeps_previous_document` (overwrite=True/False) ✅ |
| generic download create → failure → document absent | `test_store_downloaded_document_create_failure_leaves_document_absent` ✅ |
| generic download overwrite → failure → old source/blob 不变 + 非目标不变 | `test_store_downloaded_document_overwrite_failure_rolls_back_target_scope` (既有，未修改) ✅ |
| CN/HK new filing → failure → absent + 无 temp PDF | `test_cn_pdf_download_failure_leaves_document_absent` + `test_cn_docling_conversion_failure_leaves_document_absent` ✅ |
| CN/HK replacement → failure → old source/blob 不变 | `test_cn_replacement_final_failure_restores_old_source_and_blobs` ✅ |
| CN/HK generator close → no active batch, no partial document, no temp PDF | `test_cn_outer_generator_close_before_conversion_leaves_no_document` + `test_cn_inner_generator_close_before_conversion_leaves_no_document` ✅ |
| success → final source/blob/processed marker 同时可见 | `test_cn_replacement_success_exposes_source_blobs_and_processed_marker_together` ✅ |

全部 8 种路径覆盖，使用真实 filesystem state 断言（`get_source_meta`/`read_file_bytes`/`list_entries`）。✅

---

## Tool-Security Exclusion

- `rg 'allowlist|file.authority|symlink.safe|SSRF|byte.budget|security.schema|tool.security'` 在 S2 生产代码中零命中 ✅
- 删除 CN/HK `tempfile`/`NamedTemporaryFile`/临时 PDF handoff 不是 byte-budget/egress policy 实现 — `response.content` 读取行为不变，无大小上限或读取策略修改 ✅
- 无 LLM-facing prompt/schema/tool schema 修改 ✅
- 无 upload allowlist、file authority、URL/TLS/redirect/SSRF 或 remote byte budget 实现 ✅

---

## Open Questions

无。

---

## Residual Risk

| Risk | Classification | Owner / destination |
| --- | --- | --- |
| Docling conversion 通过线程执行同步第三方代码，线程中不可强制中断 | accepted — conversion 在 batch 外，延迟 cancel 不产生 partial storage state | future process/subprocess isolation WU |
| `pdf_bytes` 以内存交接，超大 PDF 内存压力 | accepted — 旧代码 `response.content` 已全量加载，本 slice 不新增内存压力 | future byte-budget WU |
| S3 Host/Service wait adapter 尚未迁移 | covered by later approved slice | mandatory R3-C S3 |
| 四类 tool-security | assigned to later work unit | dedicated tool-security / remote-egress WU |

---

## Final Review Conclusion

**Status: pass**

**Findings count: 0**

**Blocking questions: 0**

S2 实现严格遵循 accepted plan 的所有 contract：

- S2 全部 15 个文件在 allowed scope 内，无越界到 S3/Host/Service/Engine/README
- upload、generic download、CN/HK 三种 caller 全部使用 caller-owned single document batch
- `try/finally` + `commit_started` flag 精确区分 operation error（rollback）和 commit error（不 rollback）
- `_rollback_cn_batch_preserving_primary` / finally 双错误传播使用 `raise operation_error from rollback_error` + `add_note()`
- active batch segment 零 `await`/`yield`（CN/HK 重构为同步 `_commit_cn_filing_*_batch` wrapper）
- `commit_cn_filing_source_document` docstring 明确 stage-only contract，不 begin/commit/rollback
- fast-skip 与 normal-convert 两个路径各自使用唯一 caller batch
- replacement success 四者同时可见，replacement failure 恢复完整旧版本
- `DownloadedReportAsset.pdf_bytes` 类型 owner 明确，全仓 scan 零 `.pdf_path`/`pdf_path=`/tempfile 残留
- 测试覆盖 plan 8 种 rollback matrix 路径，使用真实 filesystem state 断言
- 194 tests passed, pyright 0 errors, 工具安全边界干净

实现已满足 S2 code-generation-ready 标准，可进入 per-slice review adjudication。
