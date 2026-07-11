# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B1 Code Review (AgentMiMo)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (unstaged workspace changes relative to `86f9a2dc`)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-code-review-mimo.md`
- Included scope:
  - `dayu/fins/storage/_fs_storage_utils.py` — `_normalize_document_id`, `_write_json`
  - `dayu/fins/storage/_fs_storage_infra.py` — path construction / manifest upsert/remove
  - `dayu/fins/storage/_fs_source_document_core.py` — source doc CRUD
  - `dayu/fins/storage/_fs_processed_core.py` — processed doc CRUD
  - `dayu/fins/storage/_fs_maintenance_core.py` — rejected filing / rejection registry / purge
  - `dayu/fins/downloaders/hkexnews_downloader.py` — HKEX title search completeness
  - `dayu/fins/ingestion_runtime.py` — `mark_downloaded_processed_rebuild_required`
  - `dayu/fins/pipelines/sec_pipeline.py` — SEC adapter `rebuild_processed` consumption
  - `dayu/fins/pipelines/cn_pipeline.py` — CN/HK adapter `rebuild_processed` consumption
  - `tests/fins/test_fins_storage_provider.py` — document_id path containment test
  - `tests/fins/test_hkexnews_downloader.py` — HKEX truncation tests
  - `tests/fins/test_cn_download_runtime.py` — CN/HK adapter rebuild_processed test
  - `tests/fins/test_sec_pipeline_download.py` — SEC adapter rebuild_processed test
- Excluded scope: Batch A/C/D/E, `local_file_store.py` blob Path.replace (outside Batch B1)
- Parallel review coverage: 无

## Findings

### B1-MIMO-01-未修复-中-HKEX 截断缺少 `total_count > row_count` 测试覆盖

- **入口/函数**: `_raise_if_title_search_truncated` / `HkexnewsDiscoveryClient.list_report_candidates`
- **文件(行号)**: `dayu/fins/downloaders/hkexnews_downloader.py:725-727`, `tests/fins/test_hkexnews_downloader.py:409-427`
- **输入场景**: HKEX API 返回显式 `total` 大于实际返回行数（如 `total=200` 但只返回 100 行）
- **实际分支**: 代码在 `page.total_count is not None` 且 `page.total_count > row_count` 时抛出 `HkexnewsDiscoveryTruncatedError`
- **预期行为**: 当 API 声明的总数超过返回行数时，必须 typed fail closed
- **实际行为**: 逻辑正确（line 726-731），但无测试覆盖此分支
- **直接证据**: 现有两个测试仅覆盖「满页无总数」和「满页有相等总数」；缺少「显式总数大于行数」的测试
- **影响**: 若未来重构误删 `page.total_count > row_count` 分支，无测试能捕获回归
- **建议改法和验证点**: 添加测试：构造 `total=200` 但只有 100 行的响应，断言抛出 `HkexnewsDiscoveryTruncatedError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### B1-MIMO-02-未修复-低-`_normalize_document_id` 与 `_normalize_entry_name` 逻辑重复

- **入口/函数**: `_normalize_document_id` / `_normalize_entry_name`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_utils.py:81-101` vs `104-124`
- **输入场景**: 任何 `document_id` 或 entry name 校验
- **实际分支**: 两个函数执行完全相同的校验逻辑（strip → 空检查 → `.`/`..` 检查 → 路径分隔符检查）
- **预期行为**: 校验逻辑应有唯一 source of truth
- **实际行为**: 两个独立函数，逻辑完全相同，仅 docstring 和变量名不同
- **直接证据**: 行 81-101 和 104-124 代码结构完全一致
- **影响**: 若校验规则需变更（如禁止更多特殊字符），需同步修改两处；维护负担增加
- **建议改法和验证点**: 可考虑让 `_normalize_document_id` 内部调用 `_normalize_entry_name`，保持各自的公共 API 语义独立。但鉴于当前两个函数服务于不同语义域（文档 ID vs 条目名），且均为模块私有，此为低优先级维护性观察
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Findings Summary

| 编号 | severity | 简述 | 状态 |
|------|----------|------|------|
| B1-MIMO-01 | 低 | HKEX 截断缺少 `total_count > row_count` 测试覆盖 | 未修复 |
| B1-MIMO-02 | 低 | `_normalize_document_id` 与 `_normalize_entry_name` 逻辑重复 | 未修复 |

两个 findings 均为低严重程度的测试覆盖 / 维护性问题，不影响当前正确性。

## Accepted Findings Verification

### `145711-05` — document_id path-component validation

**实现正确性**: ✅ 通过

- `_normalize_document_id` 在 `_fs_storage_utils.py:104-124` 定义，校验空值、`.`/`..`、路径分隔符
- 在以下路径统一调用：
  - `_fs_storage_infra.py`: 14 处调用，覆盖 `_source_meta_path`、`_source_meta_path_for_read`、`_processed_dir_for_write`、`_processed_dir_for_read`、`_rejected_filing_dir`、`_rejected_filing_dir_for_read`、`_resolve_handle_path`、`_handle_blob_object_key`、`_upsert_manifest_items`、`_remove_manifest_item`、`_remove_manifest_items`
  - `_fs_source_document_core.py`: 12 处调用，覆盖 `get_document_meta`、`get_source_meta`、`delete_source_meta_with_manifest`、`list_filing_entries`、`delete_source_document`、`get_source_handle`、`_upsert_source_document`、`_upsert_staging_source_document`、`ingest_complete_source_document`、`_staging_stable_fields_match`、`_staging_completion_stable_fields_match`
  - `_fs_processed_core.py`: 6 处调用，覆盖 `delete_processed`、`get_processed_handle`、`get_processed_meta`、`mark_processed_reprocess_required`、`create_processed`
  - `_fs_maintenance_core.py`: 8 处调用，覆盖 `load_download_rejection_registry`、`save_download_rejection_registry`、`store_rejected_filing_file`、`upsert_rejected_filing_artifact`、`get_rejected_filing_artifact`、`read_rejected_filing_file`、`_purge_stale_source_documents`

**路径安全验证**:
- 所有 `/` 路径拼接都使用已 normalize 的 `document_id`
- `_purge_stale_source_documents` 中 `child.name` 来自 `filings_dir.iterdir()`，本身即为合法目录名，无需再 normalize
- `_processed_meta_path` / `_processed_meta_path_for_read` 通过 `_processed_dir_for_write` / `_processed_dir_for_read` 间接调用，已包含 normalize
- `_rejected_filing_meta_path` / `_rejected_filing_meta_path_for_read` / `_rejected_filing_file_path_for_read` 通过 `_rejected_filing_dir` / `_rejected_filing_dir_for_read` 间接调用，已包含 normalize

**无下游 fallback**: ✅ 确认。未发现 `hasattr`/`getattr`、loose parsing 或路径字符串修补。

**测试验证**: `test_storage_document_id_must_be_single_path_component` 覆盖 source、processed、blob、filing 仓储对 `../MSFT/filings/fil_safe` 的拒绝。

### `145711-15` — HKEX completeness / truncation fail-closed

**实现正确性**: ✅ 通过

- `_extract_title_search_rows_page` 提取行和可选总数
- `_extract_title_search_total_count` 尝试 8 个常见 key，使用 `_coerce_non_negative_int` 收窄
- `_coerce_non_negative_int` 正确处理 `bool`（排除）、`int`（非负检查）、`str`（`isdecimal` 检查）
- `_raise_if_title_search_truncated` 在两种情况 fail closed：
  1. `total_count is not None` 且 `total_count > row_count`
  2. `total_count is None` 且 `row_count >= _HKEXNEWS_ROW_LIMIT`（100）
- `HkexnewsDiscoveryTruncatedError` 在 `list_report_candidates` 中被显式 re-raise（line 296-297），不被 `RuntimeError` 兜底吞掉

**测试验证**: 两个测试覆盖「满页无总数 → fail closed」和「满页有相等总数 → accepted」。

**残余风险**: 缺少 `total_count > row_count` 的测试（见 B1-MIMO-01）。

### `145711-16` — production download adapter consumes rebuild_processed

**实现正确性**: ✅ 通过

- `mark_downloaded_processed_rebuild_required` 在 `ingestion_runtime.py:5474-5496` 定义，遍历 `summary.written_document_ids`，对每个 document_id 调用 `_mark_processed_reprocess_required_if_present`
- `_mark_processed_reprocess_required_if_present` 先检查 processed 是否存在（`_processed_exists`），存在时才调用 `repository.mark_processed_reprocess_required(ticker, document_id, True)`
- SEC adapter (`sec_pipeline.py:1861-1866`): `if request.rebuild_processed:` 后调用 `mark_downloaded_processed_rebuild_required`
- CN/HK adapter (`cn_pipeline.py:1330-1335`): 同上
- OLD `rebuild=False` 保持不变，不映射为 OLD `CnPipeline.download(rebuild=...)`

**测试验证**:
- `test_sec_adapter_marks_processed_rebuild_for_written_documents` 验证 SEC adapter 正确标记 processed
- `test_cn_hk_adapter_marks_processed_rebuild_for_written_documents` 验证 CN/HK adapter 正确标记 processed
- 两个测试都断言 `pipeline.recorded_rebuild_values == [False]`（OLD rebuild 不受影响）和 `processed_meta["reprocess_required"] is True`

### `150304-09` — atomic JSON owner uses explicit atomic replace

**实现正确性**: ✅ 通过

- `_write_json` 在 `_fs_storage_utils.py:462-486`：
  - `path.parent.mkdir(parents=True, exist_ok=True)` — 确保目录存在
  - 写入 `temp_path`（同目录下 `.{name}.{uuid}.tmp`）
  - `stream.flush()` + `os.fsync(stream.fileno())` — 刷新数据
  - `os.replace(temp_path, path)` — POSIX 原子替换（同文件系统内 rename）
  - `_fsync_directory(path.parent)` — 刷新目录元数据
- `os.replace` 保证：目标文件要么是旧内容，要么是新内容，不会出现半写入状态
- 临时文件在 `os.replace` 成功后不再存在（rename 语义）
- 唯一残余 `Path.replace` 在 `local_file_store.py:78`，为 blob/object store 写入，不在 JSON owner 范围内

## Open Questions

- 无。

## Residual Risk

1. **HKEX 分页未实现** — 当前行为在无法证明完整性时 fail closed，是正确的防御性设计。但若 HKEX 后续支持稳定的分页协议，需实现分页以避免在大数据集场景下持续 fail。
2. **`local_file_store.py` 的 `Path.replace`** — 不在 Batch B1 JSON atomic owner 范围内，但在跨平台场景下（Windows）可能存在语义差异。建议后续 batch 评估。
3. **HKEX `total_count > row_count` 测试缺失** — 见 B1-MIMO-01。
4. **`_normalize_document_id` / `_normalize_entry_name` 重复** — 见 B1-MIMO-02，当前不影响正确性。

## Conclusion

Batch B1 的四个 accepted findings 均已正确实现。`_normalize_document_id` 在所有 storage 路径构造点统一调用，无下游 fallback 或路径修补；HKEX fail-closed 逻辑正确，typed error 正确传播；`rebuild_processed` 在 SEC/CN/HK adapter 中正确消费且不影响 OLD rebuild 语义；JSON 原子写入使用 `os.replace` 保证 POSIX 原子性。

发现两个低严重程度问题：HKEX 截断缺少 `total_count > row_count` 分支的测试覆盖，以及 `_normalize_document_id` 与 `_normalize_entry_name` 的逻辑重复。两者均不影响当前正确性。

**结论**: 实现质量良好，可以进入下一阶段。
