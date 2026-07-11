# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B2 Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD~1` (latest commit on branch)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-b2-code-review-mimo.md`
- Included scope: Batch B2 accepted findings `145711-02` (same-ticker batch ownership), `145711-03` (download overwrite data-loss), `145711-04` (upload overwrite pre-delete rollback). Co-shipped: `145711-05` (`document_id` path containment), `145711-15` (HKEX truncation detection), `145711-16` (`rebuild_processed` consumption), stale-cleanup guard.
- Excluded scope: Batch A/C/D/E findings, HKEX pagination, `ingestion_runtime` split.
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对三个 accepted findings 逐项走读后的 evidence-based 结论：

### `145711-02` same-ticker batch/staging owner token

**实现路径**：`BatchToken` 新增 `owner_token`（uuid4）和 `owner_scope_id`（asyncio task id 或 thread id）。`_FsStorageInfra.begin_batch` 创建时生成并绑定到 `ContextVar[_BATCH_OWNER_CONTEXT]`。`commit_batch`、`rollback_batch`、`_execute_with_auto_batch`、`_source_root`、`_source_root_for_read`、`_ticker_dir_for_write`、`_ticker_dir_for_read` 等所有访问 staging 目录的路径均通过 `_require_batch_owner` 做 owner 校验。

**验证**：
- `_require_batch_owner` 同时检查 `ContextVar` 中的 `owner_token` 和当前 scope 的 `_current_execution_scope_id()`，双重约束确保同一 asyncio task / 线程才能操作。
- `ContextVar` 默认值是 `{}`，`_bind_batch_owner` 和 `_unbind_batch_owner` 均先 `dict(...)` 再修改，保证 child task 不会污染 parent context。
- 测试 `test_same_ticker_active_batch_rejects_non_owner_task_on_shared_core` 从主线程 `begin_batch`，在 `asyncio.run` 的新 task 中尝试 `create_source_document`，验证被拒绝。测试 `test_same_ticker_batch_fails_fast_across_independent_repository_cores` 验证独立 core 实例也被 ticker lock 阻止。

**结论**：owner 隔离机制完整，覆盖了所有 staging 目录访问路径。

### `145711-03` download overwrite no longer clears all ticker filings

**实现路径**：
- `sec_download_workflow.py`：移除 `clear_filings_dir` 参数和 overwrite 时的 `clear_filings_dir(host._filing_maintenance_repository, normalized_ticker)` 调用。
- `cn_download_workflow.py`：移除 overwrite 时的 `host.filing_maintenance_repository.clear_filing_documents(normalized_ticker)` 调用。
- `sec_download_filing_workflow.py`：每个单 filing 下载包裹在 `begin_batch` / `commit_batch` / `rollback_batch` 中。失败、跳过、取消路径均 `rollback_batch`，`finally` 兜底。
- `sec_pipeline.py`：`_cleanup_stale_filing_dirs` 新增 `if not valid_doc_ids: return 0` 守卫，避免空结果时清理所有旧 filing。

**验证**：
- `test_sec_cleanup_stale_filing_dirs_keeps_existing_docs_when_result_empty` 断言空 `filing_results` 不会删除已有文档。
- `test_sec_pipeline_remote_change_marks_reprocess` 更新断言从 `v1`（旧的清空重建行为）改为 `v2`（递增版本），证明 overwrite 不再清空目录。
- SEC 单 filing 下载在 batch 内完成，失败时 rollback 保留旧版本，符合 target-scoped 要求。

**结论**：download overwrite 已从"清空全部"改为"target-scoped 替换"，空结果守卫防止误删。

### `145711-04` upload overwrite does not delete old doc before conversion/cancel checks

**实现路径**：
- `docling_upload_service.py`：移除公共函数 `reset_upload_target_for_overwrite`（从 `__all__` 和所有调用方删除）。`_store_upload_assets` 新方法在 `replace_existing=True` 时开启 batch，先完成所有 asset 写入和取消检查，最后才 `reset_source_document` + `_upsert_source_document` + `commit_batch`。
- `sec_upload_workflow.py`、`cn_pipeline.py`：移除所有 `reset_upload_target_for_overwrite` 调用。
- 取消路径：在 asset 循环中检测到取消时，先 `rollback_batch` 再返回 cancelled 结果。
- 失败路径：`except Exception` 块中 `rollback_batch` 后 re-raise。

**验证**：
- `test_execute_upload_overwrite_cancel_after_conversion_keeps_previous_document`：先创建旧文档，再以 overwrite 模式上传并在第 5 次取消检查时取消，断言旧 meta 和 blob 条目不变。
- `test_execute_upload_overwrite_final_failure_keeps_previous_document`：注入 `_FailingFinalUploadSourceRepository` 使最终 upsert 失败，断言旧 meta 和 blob 条目通过 batch rollback 保留。

**结论**：upload overwrite 的 reset 已移入 batch 内、新材料写入之后，取消/失败均通过 rollback 保留旧文档。

### 附加覆盖（co-shipped，非 B2 核心）

- `145711-05`：`_normalize_document_id` 在所有 storage 层入口（source、processed、maintenance、rejected filing、blob handle、manifest）统一校验 `document_id` 不含路径分隔符。测试 `test_storage_document_id_must_be_single_path_component` 覆盖 8 个 API 入口。
- `145711-15`：HKEX `_raise_if_title_search_truncated` 在满页且无总数时抛出 typed `HkexnewsDiscoveryTruncatedError`。测试覆盖满页无总数、满页有总数、总数大于行数、整数 float 总数、非法 float 总数。
- `145711-16`：`SecDownloadAdapter` 和 `CnDownloadAdapter` 在 `rebuild_processed=True` 时调用 `mark_downloaded_processed_rebuild_required`，按 `written_document_ids` 标记 processed 需重处理。测试覆盖两个 adapter。
- `_cleanup_stale_filing_dirs` 空结果守卫。

### 编码规范检查

- 所有新增/修改函数均提供完整中文 docstring（参数、返回值、异常）。
- 无 `object`、`Any`、无类型参数。
- 无兼容性 shim、无 downstream fallback、无 `hasattr`/`getattr` 滥用。
- pyright `0 errors`。
- `git diff --check` pass。

## Open Questions

无。

## Residual Risk

- `_current_execution_scope_id` 使用 `id(task)` 作为 scope 标识，依赖 Python 对象地址在同一进程内唯一。这是 asyncio 的标准行为，但在 greenlet / task pool 等非标准 executor 中可能需要额外验证。当前代码库未使用此类 executor。
- co-shipped 的 HKEX truncation 检测（`145711-15`）仅实现了 fail-closed，未实现分页拉取。后续仍需 HKEX 分页支持以覆盖结果集大于 100 条的场景。
- Batch B 中的 `145711-05`（path containment）和 `145711-16`（`rebuild_processed`）与 B2 同时实现，但未在 B2 implementation artifact 中显式列出，建议在最终 commit message 中一并说明。
