# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2 Code Review

## Scope

- Mode: current changes (uncommitted S2 diff)
- Branch: `phaseflow/host-issues-control`
- Base: working tree diff (unstaged)
- Reviewer: AgentMiMo
- Generated: `20260713-004822`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-mimo.md`

### Included scope

Production files (S2 allowed set):
- `dayu/fins/pipelines/docling_upload_service.py` — upload caller-owned batch
- `dayu/fins/ingestion_runtime.py` — generic download caller-owned batch
- `dayu/fins/pipelines/cn_download_filing_workflow.py` — CN/HK single filing atomicity (582 lines)
- `dayu/fins/pipelines/cn_download_source_upsert.py` — stage-only helper contract
- `dayu/fins/pipelines/cn_download_models.py` — `DownloadedReportAsset.pdf_bytes`
- `dayu/fins/pipelines/cn_download_protocols.py` — protocol docstring
- `dayu/fins/downloaders/cninfo_downloader.py` — temp-less CN downloader
- `dayu/fins/downloaders/hkexnews_downloader.py` — temp-less HK downloader

Test files (S2 allowed set):
- `tests/fins/test_docling_upload_service.py` — upload rollback matrix
- `tests/fins/test_fins_ingestion_runtime.py` — generic download rollback matrix
- `tests/fins/test_cn_download_workflow.py` — CN/HK rollback matrix (680 lines)
- `tests/fins/test_cn_download_runtime.py` — runtime fixture migration
- `tests/fins/test_cn_pipeline.py` — pipeline fixture migration
- `tests/fins/test_cninfo_downloader.py` — bytes contract tests
- `tests/fins/test_hkexnews_downloader.py` — bytes contract tests

Reference:
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-controller-validation.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`

### Excluded scope

S3 Host/Service wait adapter, README, design/control docs, tool schema, prompts, Engine.

### Parallel review coverage

4 subagents covered:
1. Upload/generic download caller batch (docling_upload_service, ingestion_runtime)
2. CN/HK workflow atomicity (cn_download_filing_workflow, cn_download_source_upsert)
3. Temp-less asset contract (cn_download_models, cn_download_protocols, cninfo_downloader, hkexnews_downloader)
4. Test rollback matrix coverage (all 7 test files)

---

## Findings

### 001-未修复-低-CN commit failure 测试未断言 FS absence

- **入口/函数**: `test_cn_commit_failure_does_not_trigger_caller_rollback_or_success`
- **文件(行号)**: `tests/fins/test_cn_download_workflow.py`
- **输入场景**: CN/HK filing commit failure（`source_repository.fail_commit = True`）
- **实际分支**: 测试断言 `commit_calls == 1`、`rollback_calls == 0`、`FILING_COMPLETED not in events`，但未断言 `get_source_meta` 抛 `FileNotFoundError`
- **预期行为**: 与 upload 和 generic download 的 commit failure 测试对称，应验证 storage-owned rollback 后 FS 上 source absent
- **实际行为**: 测试验证了 caller-side 行为契约（不二次 rollback、不投影 success），但未独立验证 storage-owned rollback 后的 FS 状态
- **直接证据**: upload commit failure 测试 `test_execute_upload_commit_failure_does_not_call_caller_rollback` 断言了 `FileNotFoundError`；generic download 测试 `test_store_downloaded_document_commit_failure_does_not_caller_rollback` 同样断言了 `FileNotFoundError`；CN 测试缺少该断言
- **影响**: 低。storage-owned rollback 的 FS 正确性由 S1 storage tests 保证；此测试重点验证 caller 不越权。但缺少 FS absence 断言使三个 caller 的 commit failure 测试不对称
- **建议改法和验证点**: 在 CN commit failure 测试中增加 `with pytest.raises(FileNotFoundError): source_repository.get_source_meta(...)` 断言
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## S2 Contract Verification Summary

### Upload caller-owned batch (`docling_upload_service.py`)

| Contract | Status | Evidence |
|---|---|---|
| All non-delete mutations enter one caller-owned batch | ✅ | `begin_batch` unconditional at line 331; was conditional on `replace_existing` |
| `_acknowledge_source_before_blob_write` only stages | ✅ | Lines 562-581: no begin/commit/rollback calls |
| `commit_started` flag guards finally block | ✅ | Line 332: `False`; line 402: `True` before commit; line 419: `if not commit_started` |
| Commit failure no caller rollback | ✅ | `commit_started=True` at line 402 before `commit_batch` at line 403 |
| Dual error propagation: primary + note + cause | ✅ | Lines 421-430: `operation_error.add_note(...)` + `raise operation_error from rollback_error` |
| Cancellation returns trigger rollback | ✅ | Lines 362, 386, 398-399: all before `commit_started=True` |
| No yield/await inside active batch | ✅ | Method is synchronous `def`; zero `await`/`yield` in file |

### Generic download caller-owned batch (`ingestion_runtime.py`)

| Contract | Status | Evidence |
|---|---|---|
| Reset/source/blob/processed in one batch | ✅ | Line 3791: unconditional `begin_batch`; all mutations in try block |
| Same `commit_started` pattern as upload | ✅ | Lines 3792, 3810, 3813: structurally identical |
| Commit failure no caller rollback | ✅ | `commit_started=True` at line 3810 before `commit_batch` at line 3811 |
| No yield/await inside active batch | ✅ | Method is synchronous `def` |

### CN/HK single filing atomicity (`cn_download_filing_workflow.py`)

| Contract | Status | Evidence |
|---|---|---|
| Network/download/convert/progress yields outside batch | ✅ | All 10 yield points (lines 150-396) before any `begin_batch` |
| Normal path: synchronous commit segment, no yield/await | ✅ | `_commit_cn_filing_assets_batch` lines 460-561: synchronous function |
| PDF-SHA skip path: one caller batch | ✅ | `_commit_cn_filing_metadata_batch` lines 619-652 |
| `commit_started` ownership handoff | ✅ | Lines 461/620: `False`; lines 560/651: `True` before commit |
| `commit_cn_filing_source_document` stage-only | ✅ | Zero begin/commit/rollback calls in function body |
| Generator close during pre-commit yield: no partial document | ✅ | All yields before `begin_batch`; batch not yet begun |
| CancelledError rollback exactly once | ✅ | `_rollback_cn_batch_preserving_primary` called when `commit_started=False` |
| Commit failure no caller rollback | ✅ | `commit_started=True` guards finally block |
| Dual error propagation | ✅ | `sys.exception()` → `add_note()` → `raise ... from ...` |

### Temp-less asset contract

| Contract | Status | Evidence |
|---|---|---|
| `DownloadedReportAsset.pdf_path` → `pdf_bytes` | ✅ | `cn_download_models.py`: field changed, no compatibility property |
| `tempfile` removed from downloaders | ✅ | Both cninfo/hkexnews: `import tempfile` and `from pathlib import Path` removed |
| Bytes returned directly | ✅ | `DownloadedReportAsset(pdf_bytes=payload, ...)` in both downloaders |
| HTTP request/URL/redirect/TLS unchanged | ✅ | Zero diff lines touching HTTP configuration |
| Zero `pdf_path` references remain | ✅ | `rg` scans: zero matches across `dayu/fins` and `tests` |
| All constructors use `pdf_bytes=` | ✅ | 6/6 constructor sites verified |

### Test rollback matrix

| Scenario | Test | Real FS? |
|---|---|---|
| Upload create final failure: absence | `test_execute_upload_create_final_failure_leaves_document_absent` | ✅ |
| Upload update/overwrite final failure: old unchanged | `test_execute_upload_update_failure_keeps_previous_document` (parametrized) | ✅ |
| Upload same token, one commit | `test_execute_upload_uses_one_caller_batch_for...` | Hybrid |
| Upload commit failure no caller rollback | `test_execute_upload_commit_failure_does_not_call_caller_rollback` | ✅ |
| Upload dual failure: primary/note/cause | `test_execute_upload_operation_and_rollback_failure_preserve_both_errors` | Exception |
| Generic create failure: absence | `test_store_downloaded_document_create_failure_leaves_document_absent` | ✅ |
| Generic overwrite failure: old + non-target unchanged | `test_store_downloaded_document_overwrite_failure_rolls_back_target_scope` | ✅ |
| Generic commit failure no caller rollback | `test_store_downloaded_document_commit_failure_does_not_caller_rollback` | ✅ |
| CN replacement same token | `test_cn_replacement_uses_one_batch_for...` | Hybrid |
| CN PDF-SHA skip same token | `test_cn_pdf_sha_skip_final_meta_uses_one_caller_batch` | Hybrid |
| CN replacement final failure: restore old | `test_cn_replacement_final_failure_restores_old_source_and_blobs` | ✅ |
| CN success: source+blobs+marker visible | `test_cn_replacement_success_exposes_source_blobs_and_processed_marker_together` | ✅ |
| CN PDF download exception: absence | `test_cn_pdf_download_failure_leaves_document_absent` | ✅ |
| CN Docling conversion exception: absence | `test_cn_docling_conversion_failure_leaves_document_absent` | ✅ |
| CN CancelledError: rollback once | `test_cn_active_batch_sync_cancelled_error_rolls_back_once` | ✅ |
| CN commit failure: no rollback, no success | `test_cn_commit_failure_does_not_trigger_caller_rollback_or_success` | Partial ⚠️ |
| CN generator close: no partial | `test_cn_outer/inner_generator_close_before_conversion_leaves_no_document` | ✅ |
| CNInfo/HKEX pdf_bytes/SHA/length | Refactored tests | ✅ |

---

## Tool-Security Boundary Verification

| Check | Result |
|---|---|
| Upload allowlist / file authority / symlink-safe upload source policy | Not implemented |
| URL / TLS / redirect / SSRF provenance policy | Not implemented. Pre-existing redirect code in downloaders unchanged |
| Remote download byte-budget policy | Not implemented. `pdf_bytes` uses existing `response.content` |
| LLM-facing security schema / prompt / tool schema | Not implemented. `git diff --check` passes; no prompt/schema files in diff |
| `NamedTemporaryFile` / temp dir references | Zero matches in downloaders/pipelines/tests |
| `pdf_path` references | Zero matches in production and test code |

**Conclusion**: S2 无工具安全 scope drift。删除 temp PDF handoff 不是 byte-budget/egress policy。

---

## Validation

```bash
pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py -q
```
Result: `194 passed, 3 warnings`

```bash
python -m pyright dayu/fins/pipelines/ dayu/fins/downloaders/ dayu/fins/ingestion_runtime.py
```
Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```
Result: pass

```bash
rg -n "NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path" dayu/fins/downloaders dayu/fins/pipelines tests/fins
```
Result: no matches

```bash
rg -n '\.pdf_path\b' dayu/fins tests --glob '*.py'
```
Result: no matches

---

## Open Questions

无。

## Residual Risk

| Risk | Classification | Owner / destination |
|---|---|---|
| Docling conversion 在线程中不能强制中断 | accepted — conversion 在 batch 外，延迟取消不产生 partial storage state | future process/subprocess isolation WU |
| `DownloadedReportAsset` 以内存 bytes 交接 | accepted — `response.content` 已全量加载，不新增内存压力 | tool-security byte-budget WU |
| CN commit failure 测试缺少 FS absence 断言 | low — storage rollback 正确性由 S1 保证 | 可选增强，不阻塞 |

---

## Final Code Review Conclusion

**Status: pass-with-risks**

S2 实现与 accepted plan 高度对齐。8 个 production 文件均在 S2 allowed set 内。upload/generic/CN-HK 三条 caller 路径均正确实现 caller-owned single-document batch：unconditional `begin_batch`、`commit_started` flag guard、commit failure 不二次 rollback、dual error propagation、active batch 内无 yield/await。`commit_cn_filing_source_document` 是纯 stage-only helper。`DownloadedReportAsset.pdf_path` 已清除，无兼容 shim，tempfile 全部删除，HTTP 行为不变。194 测试全通过，pyright 零报错。无工具安全 scope drift。

一个低严重度 finding：CN commit failure 测试未断言 FS absence，与 upload/generic 测试不对称。不阻塞 S2 进入 controller adjudication。

## Completion Report

- **status**: pass-with-risks
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-mimo.md`
- **findings count**: 1
- **blocking questions count**: 0
