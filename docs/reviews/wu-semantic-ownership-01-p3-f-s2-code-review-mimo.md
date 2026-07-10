# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S2

## Scope

- Mode: current changes (unstaged workspace diff since `42ea9c21`)
- Branch: `phaseflow/host-issues-control`
- Base: `42ea9c21` (S1 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-code-review-mimo.md`
- Included scope: 10 files (+843/-18) — S2 blob acknowledgement and staging source contract
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`, `docs/host/issues-implementation-control.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项检查：

### Blob 写入边界

`FsDocumentBlobRepository.store_file(SourceHandle, ...)` 在任何字节写入前调用 `self._get_handle_meta(handle)`（`_fs_blob_core.py:144-145`）。`_get_handle_meta` 在 `_fs_storage_infra.py:798` 检查 `meta_path.exists()`，不存在时抛出 `FileNotFoundError`。source meta 是 blob 写入的唯一前置承认事实；`ProcessedHandle` 路径不受影响。

### Upload staging 时序

`DoclingUploadService.execute_upload(...)` 在首个 blob 写入前调用 `_acknowledge_source_before_blob_write(...)`（`docling_upload_service.py:260-268`）。该方法在 `previous_meta is None` 或 `ingest_complete=False` 时构造 `staging_meta` 并调用 `self._source_repository.stage_source_document(...)`（line 430-448）。staging 完成后才进入 `for asset in pending_assets` 循环写入 blob（line 269-278）。

final upsert 使用同一份 `staging_meta`（line 308），`_upsert_source_document` 中 `merged_meta.update(req.meta)` 将 `ingest_complete` 从 staging 的 `False` 覆盖为 final 的 `True`（通过 `merged_meta.setdefault("ingest_complete", True)` 或显式写入）。当 final upsert 失败时，incomplete staging meta 和其名下 blob 保留——符合 plan 要求的"不产生 ownerless blob"。

### SEC stream/legacy staging 时序

`run_download_single_filing_stream(...)` 在 downloader `store_file` callback 之前调用 `stage_downloaded_filing_source_document(...)`（`sec_download_filing_workflow.py:419-430`）。`stage_downloaded_filing_source_document` 在 `previous_meta` 已完成时直接返回 `SourceHandle`；否则构造 meta payload 并调用 `source_repository.stage_source_document(...)`（`sec_download_source_upsert.py:104-137`）。

`source_handle` 被传入 `host._build_store_file(source_handle=source_handle)`（line 440），downloader 的 `store_file` callback 最终调用 `blob_repository.store_file(source_handle, ...)`，触发 blob guard。

注意：line 412-416 的 `source_handle = SourceHandle(...)` 是死代码，被 line 419 的 `source_handle = stage_downloaded_filing_source_document(...)` 立即覆盖。不影响 correctness，但增加理解成本。

### Completion stable fields 保护

`_upsert_source_document` 在 `is_create` 且 meta 已存在但为 incomplete 时，或 `not is_create` 且 previous meta 为 incomplete 时，调用 `_staging_completion_stable_fields_match(...)`（`_fs_source_document_core.py:781-786`）。

该函数要求：如果 staging meta 中某个 stable field 有非空值，completion request 必须提供相同值。允许 completion 补充 staging 阶段不可知的字段（如 CN/HK 的 `source_fingerprint`），但不允许改变 provider、remote fingerprint、company id 等既有事实。这与 `_staging_stable_fields_match`（staging 阶段）的语义互补：staging 要求双向匹配，completion 只要求不改变已声明值。

### CN 路径未回归

CN workflow 测试 7 passed。CN 路径已有 `update_cn_staging_source_document` 工作流 helper，S2 未修改 CN 代码，CN staging 行为不受影响。

### README 更新

`dayu/fins/README.md` 增加两段：source document acknowledgement contract 和 storage 层 source/blob 边界描述。内容在 `dayu/fins/` Agent update constraints 范围内，准确描述了 S2 引入的 owner boundary。

## Owner Boundary 评估

| 检查项 | 状态 | 证据 |
|---|---|---|
| Blob 写入拒绝未承认的 SourceHandle | ✅ | `_fs_blob_core.py:144-145` + `_fs_storage_infra.py:798-799` |
| Upload 在首个 blob 前 staging | ✅ | `docling_upload_service.py:260-268` |
| SEC stream 在 downloader callback 前 staging | ✅ | `sec_download_filing_workflow.py:419-430` |
| SEC legacy path 在 downloader callback 前 staging | ✅ | 同一 `stage_downloaded_filing_source_document` 路径 |
| Final commit 延续 staging stable facts | ✅ | `_staging_completion_stable_fields_match` in `_upsert_source_document` |
| CN staging 未回归 | ✅ | 7 CN workflow tests passed |
| Read runtime 排除 incomplete source | ✅ | S1 已实现，S2 测试验证 `fil_incomplete` 不在 list 结果中 |
| Pipeline 不自行构造第二份 staging truth | ✅ | 所有 staging 通过 `stage_source_document` 协议 |
| No downstream/read-runtime special casing | ✅ | 无新增下游分类或展示层特例 |

## Validation

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py -q`: **66 passed, 3 warnings**
- `pyright dayu/fins/...`: **0 errors**
- `git diff --check`: passed

## Residual Risk

- **Dead code**: `sec_download_filing_workflow.py:412-416` 的 `source_handle = SourceHandle(...)` 被 line 419 立即覆盖，是无害死代码。
- **Coverage 未测量**: pytest-cov 本地 numpy/pandas import 问题仍存在。
- **TOCTOU residual**: blob guard 的 source meta 检查与 blob 写入之间存在理论上的多进程竞争窗口，plan 已接受为 residual risk。
- **S3/S4 未实现**: wait adapter deadline/expiry 和 company metadata freshness 不在 S2 scope。

## Verdict

**PASS** — S2 实现正确执行了 plan 中的 blob acknowledgement 和 explicit staging source contract。blob 写入边界、staging 时序、completion stable fields 保护和 CN 路径均符合 owner boundary 设计。未发现 material defects。
