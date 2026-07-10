# Code Re-Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S2 Fix

## Scope

- Mode: current changes (unstaged) — S2 fix re-review
- Branch: `phaseflow/host-issues-control`
- Base: S2 initial implementation (post `42ea9c21`, prior to fix)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-rereview-ds.md`
- Reviewed artifacts:
  - DS review: `wu-semantic-ownership-01-p3-f-s2-code-review-ds.md`
  - MiMo review: `wu-semantic-ownership-01-p3-f-s2-code-review-mimo.md`
  - Controller adjudication: `wu-semantic-ownership-01-p3-f-s2-code-review-controller-adjudication.md`
  - Fix report: `wu-semantic-ownership-01-p3-f-s2-fix-codex.md`
  - Controller fix validation: `wu-semantic-ownership-01-p3-f-s2-fix-controller-validation.md`
- Included scope: 10 files (same as original S2; only `sec_download_filing_workflow.py` changed in fix)
- Validation: `pytest` 66 passed, `pyright` 0 errors

## Verdict

**PASS** — `P3-F-S2-CR-F01` 已正确修复，无新增 material finding，无 regression，无 owner boundary 漂移。

---

## Finding Status

### P3-F-S2-CR-F01 — 移除 SEC workflow 中被覆盖的 `source_handle` 死代码赋值 ✅ FIXED

- **Source**: DS finding 1; MiMo residual note.
- **Requirement**: 移除 `run_download_single_filing_stream` 中的死 `SourceHandle(...)` 赋值，不改变 staging 行为或测试预期。
- **Fix evidence**:

| 要求 | 状态 | 直接证据 |
| --- | --- | --- |
| 移除死 `SourceHandle(...)` 赋值 | ✅ | 原行 412-416 的 `source_handle = SourceHandle(ticker=..., document_id=..., source_kind=SourceKind.FILING.value)` 已删除。`existing_files` 和 `file_results` 上移填充空位 |
| `source_handle` 仅来自 `stage_downloaded_filing_source_document` | ✅ | 现在文件只有一处 `source_handle = stage_downloaded_filing_source_document(...)` 赋值（行 412-424），owner boundary 清晰：blob 写入前可用的 handle 明确来自 source repository acknowledgement |
| Staging 仍在 downloader callback 前 | ✅ | `source_handle = stage_downloaded_filing_source_document(...)` 在 stream `download_stream_func` / legacy 路径之前（行 431 起） |
| 不改变测试预期 | ✅ | 66 测试全部通过，无测试修改 |
| `host._build_store_file(source_handle=source_handle)` 仍使用 staging 结果 | ✅ | 行 443: `store_file=host._build_store_file(source_handle=source_handle)` |

---

## Regression Check

对比 S2 初始实现与 fix 后的 diff，仅 `sec_download_filing_workflow.py` 有变更，且变更仅限于删除死代码赋值和重排行顺序。以下文件与 S2 初始实现完全一致：

| 文件 | 状态 |
| --- | --- |
| `dayu/fins/storage/_fs_blob_core.py` | 不变 |
| `dayu/fins/storage/_fs_source_document_core.py` | 不变 |
| `dayu/fins/pipelines/docling_upload_service.py` | 不变 |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | 不变 |
| `dayu/fins/README.md` | 不变 |
| `tests/fins/test_fins_storage_provider.py` | 不变 |
| `tests/fins/test_docling_upload_service.py` | 不变 |
| `tests/fins/test_sec_pipeline_download_stream.py` | 不变 |

---

## New Defect Scan

对 fix 变更的唯一文件 `sec_download_filing_workflow.py` 逐行走读：

- **`SourceHandle` import**: 未受影响——`SourceHandle` 仍在该文件其他位置使用（`_build_store_file` 等），import 未被 orphan。
- **`stage_downloaded_filing_source_document` import**: S2 初始已添加，fix 未改动 import。
- **重排行顺序**: `existing_files = index_file_entries(previous_meta)` 和 `file_results: list[DownloadFileResult] = []` 上移到 staging 调用之前。这两个变量在 staging 调用中不被引用（`stage_downloaded_filing_source_document` 不接收 `existing_files` 或 `file_results`），且在下游 stream/legacy 路径中仍可按原有顺序读取。无数据流变更。
- **`source_handle` 变量**: 现在只有一处赋值，无歧义。

无新增 material defect。

---

## Owner Boundary Re-Verification

| Owner | 职责 | Fix 后状态 |
| --- | --- | --- |
| Blob repository | `store_file(SourceHandle)` 前校验 source meta 存在 | ✅ 不变（`_fs_blob_core.py:144-145`） |
| Source repository | staging + completion stable field protection | ✅ 不变（`_fs_source_document_core.py`） |
| SEC pipeline | 在 downloader callback 前调用 `stage_downloaded_filing_source_document` | ✅ 调用位置不变，`source_handle` 来源现在无歧义 |
| Upload pipeline | 在首个 blob 写入前调用 `_acknowledge_source_before_blob_write` | ✅ 不变（`docling_upload_service.py`） |
| Read runtime | 排除 incomplete source | ✅ 不变（S1 contract） |

---

## Open Questions

无。

## Residual Risk

- S2 既有 residual risk 不变：TOCTOU race（plan 已接受）、coverage 未测量、S3/S4 未实现。
- Fix 未引入新 risk。
