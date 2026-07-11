# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch B1

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace unstaged changes)
- Review target: Batch B1 accepted findings only
- Accepted findings: `145711-05`, `145711-15`, `145711-16`, `150304-09`
- Design sources read:
  - `AGENTS.md`
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-round2-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-b1-controller-validation.md`
- Excluded scope: Batch A/C/D/E; `local_file_store.py` Path.replace (out of JSON owner scope); HKEX pagination (deferred)
- Parallel review coverage: 无（单 reviewer 逐链路走读）

## Findings

### B1-01-未修复-低-`_resolve_handle_dir` ProcessedHandle 分支与 SourceHandle 分支的归一化风格不一致

- **入口/函数**: `_FsStorageInfra._resolve_handle_dir`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:751-755`
- **输入场景**: 传入任意 `ProcessedHandle`，`handle.document_id` 含前导/尾部空白。
- **实际分支**: `isinstance(handle, ProcessedHandle)` → `self._processed_dir_for_read(normalized_ticker, handle.document_id)` — 不在此处调用 `_normalize_document_id`，归一化发生在 `_processed_dir_for_read` 内部。
- **预期行为**: 两个分支都在路径构造前完成 `document_id` 归一化，行为等同。
- **实际行为**: 两个分支均正确完成归一化，但 **SourceHandle 分支显式调用 `_normalize_document_id`**，而 **ProcessedHandle 分支将归一化委托给 `_processed_dir_for_read`**。当前行为正确，但不一致会让后续维护者误以为 ProcessedHandle 绕过了归一化，增加误读风险。
- **直接证据**: `_fs_storage_infra.py:754` 显式调用 `_normalize_document_id(handle.document_id)`；`:752` 仅传递 `handle.document_id` 给 `_processed_dir_for_read`。`_processed_dir_for_read` 在 `:1403-1406` 内部调用 `_normalize_document_id`。
- **影响**: 仅代码可读性与维护风险；无运行时错误。
- **建议改法和验证点**: 在 `_resolve_handle_dir` 的 ProcessedHandle 分支也显式调用 `_normalize_document_id`，保持两分支风格一致。或者将 SourceHandle 分支也改为委托风格。任选其一即可。
- **修复风险（低）**: 纯风格调整，不改变行为。
- **严重程度（低）**:

### B1-02-未修复-低-`_coerce_non_negative_int` 不处理 `float` 类型，可能漏识别 `total` 字段

- **入口/函数**: `_coerce_non_negative_int` → `_extract_title_search_total_count`
- **文件(行号)**: `dayu/fins/downloaders/hkexnews_downloader.py:678-699`
- **输入场景**: 披露易 title search API 返回 `{"total": 100.0}`（JSON number 带小数点，Python `json.loads` 解析为 `float`）。
- **实际分支**: `isinstance(value, bool)` → False; `isinstance(value, int)` → **False**（Python 中 `float` 不是 `int` 的子类）; `isinstance(value, str)` → False → 返回 `None`。
- **预期行为**: 若 `100.0` 是合法整数（无小数部分），应识别为 `total=100`。
- **实际行为**: 返回 `None`，`total_count` 为 `None`。若此时 `row_count >= 100`，触发满页无总数截断报错，导致本可证明完整的结果被当作截断拒绝。
- **直接证据**: `_coerce_non_negative_int` 的 `isinstance` 链不含 `float` 分支（`:691-698`）。测试 `test_list_report_candidates_accepts_full_page_when_total_proves_complete` 只用字符串 `"100"` 测试了 `str` 分支，未覆盖 `float` 输入。
- **影响**: 若披露易 API 变更返回格式（例如从字符串 `"100"` 变为数字 `100.0`），原本成功的结果会变成 typed truncated error。当前披露易 API 返回的是字符串格式的总数，实际触发概率低。
- **建议改法和验证点**: 在 `_coerce_non_negative_int` 中增加 `isinstance(value, float)` 分支：若 `value == int(value)` 且 `value >= 0` 则返回 `int(value)`。补充 `float` 输入的参数化测试。
- **修复风险（低）**: 添加类型分支，不影响现有 int/str 路径。
- **严重程度（低）**:

### B1-03-未修复-低-`mark_processed_reprocess_required` 标记链路中的重复 meta 读取

- **入口/函数**: `_mark_processed_reprocess_required_if_present` → `_processed_exists` → `mark_processed_reprocess_required`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:5447-5471`，`dayu/fins/storage/_fs_processed_core.py:193-217`
- **输入场景**: `rebuild_processed=True`，`written_document_ids` 含已存在的 processed 文档。
- **实际分支**: `_processed_exists` 调用 `repository.get_processed_meta(ticker, document_id)` 读取 meta JSON（`:5413-5414`）→ 存在则 `mark_processed_reprocess_required` → `_mark_processed_reprocess_required_impl` 再次 `_read_json_object(processed_meta_path)` 读取同一文件（`:213`），然后写入。
- **预期行为**: 仅读取一次 meta，判断存在性同时准备好写入。
- **实际行为**: 每次标记需两次 JSON 读取（一次判存，一次标记），对单个文档开销极小，但在 `rebuild_processed` 批量标记大量文档时可累积为可感知的 I/O 浪费。
- **直接证据**: `_processed_exists` at `:5414` 调用 `get_processed_meta`；`_mark_processed_reprocess_required_impl` at `:213` 调用 `_read_json_object`。两者读取同一文件路径，中间无缓存。
- **影响**: 批量 rebuild 时额外 I/O；不影响正确性。仅在生产级批量操作中可感知。
- **建议改法和验证点**: 将 `_mark_processed_reprocess_required_if_present` 改为直接尝试标记，由 `mark_processed_reprocess_required` 内部判存（`_mark_processed_reprocess_required_impl` 已通过 `processed_meta_path.exists()` 判存）。或者提供一个批量标记接口，一次读取后批量写入。
- **修复风险（低）**: 需确保调用方不依赖 `_processed_exists` 的副作用。
- **严重程度（低）**:

## Open Questions

1. **披露易 API 的 `total` 字段实际返回格式**：代码通过 8 种 key 名称和 `int`/`str` 类型尝试提取总数。当前测试仅覆盖字符串 `"100"`。是否需要通过真实 API 响应或历史抓取数据确认实际字段名和类型，以验证 `_extract_title_search_total_count` 的搜索优先级和类型覆盖是否正确？

2. **HKEX `_raise_if_title_search_truncated` 对 `total_count < row_count` 情况的处理**：当 `total_count is not None` 且 `total_count < row_count`（API 返回矛盾数据，total 比实际行数少），当前逻辑只检查 `total_count > row_count`，会静默接受结果。是否需要增加 `total_count < row_count` 的防御性检查？

3. **`save_download_rejection_registry` 中 `entry_payload["document_id"]` 的覆盖**：代码在 `entry.to_dict()` 之后用 `normalized_document_id` 覆盖 `entry_payload["document_id"]`（`:360`）。如果 `DownloadRejectionEntry` 将来增加 `document_id` 以外的持久化字段需要保留原始值，当前逻辑可能需要调整。不过目前 `to_dict()` 返回的内容中 `document_id` 是唯一需要归一化的字段，此风险暂不成立。

## Residual Risk

1. **HKEX 分页未实现**：当前 `rowRange=100` 仅请求单页。`_raise_if_title_search_truncated` 确保满页无总数时失败关闭，但代码未实现多页抓取。如果披露易 API 支持分页参数（如 `page`/`offset`）但当前 downloader owner 未暴露，则多页场景下结果永远是截断报错。这是已记录的延期项，不在 Batch B1 scope 内。

2. **`_normalize_document_id` 防御深度**：虽然所有存储入口和路径构造函数都调用了 `_normalize_document_id`，但 `_get_handle_meta`（`:796-799`）和 `_resolve_handle_dir`（`:752`）直接将 `handle.document_id` 传给下游函数，依赖下游函数内部归一化。如果未来有人新增一个不归一化的下游路径构造函数并被这些调用点使用，可能引入漏洞。建议在 handle-based API 入口统一归一化，而非仅依赖下游。

3. **`local_file_store.py:78` 仍使用 `Path.replace`**：Controller validation 和 implementation codex 均记录此项在 Batch B1 scope 外。当前 `_write_json` 的 `os.replace` 修改仅覆盖 JSON 写入路径，blob/object store 的文件写入仍使用非原子替换。

4. **SEC adapter 测试使用 `cast` 绕过类型检查**：`test_sec_adapter_marks_processed_rebuild_for_written_documents` 中 `cast(sec_pipeline.SecPipeline, pipeline)` 将 `_RecordingSecPipelineForAdapter`（非 `SecPipeline` 子类）强制转型。运行时安全（duck typing 兼容），但类型检查被绕过。如果 `SecDownloadAdapter.__init__` 将来增加对 `SecPipeline` 特有属性/方法的访问，测试会在运行时而非类型检查时暴露。

5. **未覆盖的测试场景**：
   - `_normalize_document_id` 对 `\`（反斜杠）的拒绝：测试中的 `invalid_document_id = "../MSFT/filings/fil_safe"` 仅含 `/`，未测试含 `\` 的输入。
   - `_raise_if_title_search_truncated` 对 `total_count < row_count`（矛盾数据）的行为：未覆盖此分支。
   - HKEX `list_report_candidates` 对多语言场景下每种语言独立检查截断：未覆盖两种语言都返回满页但只有一种语言有 `total` 的场景。
