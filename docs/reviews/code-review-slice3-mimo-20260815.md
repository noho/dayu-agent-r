# UF-FIX06 Slice 3 code review

## 元数据

- Reviewer：AgentMiMo
- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：3（让 Service 与 workflows 消费 typed roles）
- 基线：`affa665b`
- 评审范围：未提交 diff（11 files, +1042 / -131）
- 日期：2026-08-15
- 结论：`PASS` — blocking finding 为 0

## Review scope

Production files:
- `dayu/fins/pipelines/docling_upload_service.py`（+151 / -131，核心变更）
- `dayu/fins/pipelines/cn_pipeline.py`（+10 / -2）
- `dayu/fins/pipelines/sec_upload_workflow.py`（+10 / -2）
- `dayu/fins/upload_failure.py`（+29 / -8）

Test files:
- `tests/fins/test_docling_upload_service.py`（+394 / -40）
- `tests/fins/test_cn_pipeline.py`（+205 / -5）
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`（+100 / -4）
- `tests/fins/test_sec_pipeline_upload_material_stream.py`（+123 / -0）
- `tests/fins/test_fins_ingestion_runtime.py`（+20 / -12）
- `tests/fins/test_fins_ingestion_tools.py`（+128 / -2）
- `tests/fins/test_docling_upload_service_integration.py`（+3 / -1）

New file:
- `tests/fins/test_upload_failure.py`（+117）

## 审查清单

### 1. Service typed selection concrete type/source_kind/action emptiness 双向校验是否在零 I/O 前 ✅

**证据：** `docling_upload_service.py:282-293`

```
selection_preparation = _prepare_upload_selection(  # L282: source_kind vs selection type check
    source_kind=source_kind,
    selection=selection,
)
normalized_action = action.strip().lower()           # L286
if normalized_action not in UPLOAD_ACTIONS: ...      # L287
is_empty = not selection_preparation.ordered_files   # L289
if normalized_action == "delete" and not is_empty:   # L290: delete+files rejected
    raise ValueError(...)
if normalized_action != "delete" and is_empty:       # L292: create/update+empty rejected
    raise ValueError(...)
# ... ticker/document_id/form_type validation ...
validated_files = _validate_source_files(...)        # L313: FIRST file I/O (existence check)
```

**分析：** `_prepare_upload_selection` 在 L282 完成 `isinstance` 类型收窄检查。action/emptiness 双向校验在 L289-293 完成。首次文件 I/O 在 L313（`_validate_source_files` 的 `file_path.exists()`）。所有非法组合在零 I/O 前被拒绝。

**Filing workflow 调用方确认：** SEC `sec_upload_workflow.py:209` 和 CN `cn_pipeline.py:838` 直接传递 `authoritative_request.file_selection`，格式 admission 在 runtime 层 `validate_fins_upload_filing_request`（`ingestion_runtime.py:1002-1013`）完成，早于 service 调用。

### 2. filing 全 originals 只转 primary、material 全转 ✅

**证据：** `docling_upload_service.py:1014-1029`（`_prepare_upload_selection`）

- Filing：`converter_inputs = () if selection.is_empty else (selection.require_primary(),)` — 只有 primary 送入 converter
- Material：`converter_inputs = selection.files` — 全部 selection 文件送入 converter

**测试验证：**
- `test_filing_converts_only_primary_and_publishes_all_companions`：验证 `calls == [names[0]]`（只转换 primary）且 `stored_file_count == len(names)`（全部 original 存储）
- `test_execute_upload_material_converts_every_selected_file`：验证 `calls == ["first.pdf", "second.docx"]`（全部转换）
- `test_execute_upload_counts_only_successful_original_stores`：验证 filing 2 个 original 只产生 3 个 meta entries（1 primary + 1 docling + 1 companion），`stored_file_count == 2`

### 3. primary_document 不再扫描 ✅

**证据：**

- 删除了 `_pick_primary_docling_file`（从 stored entries 反推主文件名的旧逻辑）
- `_build_pending_assets`（L803）：`if primary_document is None: primary_document = docling_name` — 首次成功转换直接产生
- `_PreparedAssetMutation` 新增 `primary_document: str` 字段（L147）
- `_store_upload_assets` 接收并传递 `primary_document` 到 `_create_source_document`（L567-570）

**影响：** primary_document 不再依赖 publication 后的 stored entry 扫描，消除了存储状态反推语义的风险。

### 4. companion 事件/计数/原子 batch ✅

**证据：**

- `_build_original_assets`（L687-731）：所有 `ordered_files`（含 companions）读取为 original assets
- `_build_pending_assets`（L764）：只遍历 `converter_inputs`（filing 只有 primary），companions 不产生 `conversion_started` 事件
- `_store_upload_assets`（L528-554）：所有 `pending_assets`（含 companions 的 original asset）统一存储并产生 `file_uploaded` 事件

**测试验证：**
- `test_filing_converts_only_primary_and_publishes_all_companions`：`conversion_started` 事件只有 `[names[0]]`，`file_uploaded` source=original 包含全部 `names`
- `test_corrupt_primary_with_valid_companions_fails_atomically`：primary 损坏时 companions 不存储，`stored_file_count == 0`

### 5. SEC/CN fresh authoritative selection ✅

**证据：**

- SEC `sec_upload_workflow.py:209`：`selection=authoritative_request.file_selection`
- CN `cn_pipeline.py:838`：`selection=authoritative_request.file_selection`
- 两者都使用 fresh validation 产生的 typed selection，不从 raw files 重建

**测试验证：**
- `test_upload_filing_consumes_fresh_authoritative_file_selection`（SEC 和 CN 各一）：注入 `authoritative_validator` 替换 selection，验证 converter 和 storage 使用 authoritative 文件而非 raw 文件

### 6. material admission 在任何 state/file/mutation 前且 catch-all 投影 ✅

**证据：**

CN material（`cn_pipeline.py:1074-1078`）：
```python
selection = (                                    # L1074: 格式 admission 发生点
    FinsUploadMaterialFiles.for_delete()
    if requested_action == "delete"
    else FinsUploadMaterialFiles.from_upsert_paths(tuple(file_list))
)
previous_meta = self._safe_get_upload_document_meta(...)  # L1079: 首次 state read
```

SEC material（`sec_upload_workflow.py:459-463`）：同构。

`FinsUploadMaterialFiles.from_upsert_paths` → `__post_init__` → `require_material_path` → 不支持后缀抛出 `FinsUploadFormatError`。此异常在 `try` 块内，被 `except Exception`（`cn_pipeline.py:1185`）捕获，经 `fins_upload_failure_from_exception` 投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`。

**测试验证：**
- `test_upload_material_unsupported_suffix_fails_before_reads_or_mutation`（SEC 和 CN 各一）：monkeypatch 禁用 state read、batch 和 file read，验证格式错误在副作用前抛出且 failure JSON 正确

### 7. USAGE/UNSUPPORTED_UPLOAD_FORMAT JSON closed roundtrip ✅

**证据：**

- `FinsUploadFailureKind.USAGE = "usage"`（`upload_failure.py:31`）
- `FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT = "unsupported_upload_format"`（`upload_failure.py:40`）
- `_USAGE_FAILURE_CODES` 包含该 code（`upload_failure.py:167-169`）
- `_FAILURE_KIND_BY_CODE` 映射覆盖所有 code（`upload_failure.py:177-184`），module-load 时完整性和唯一性断言
- `fins_upload_failure_from_exception` 拦截 `FinsUploadFormatError`（L205-212）
- `upload_failure_reason_from_json` 使用 `_FAILURE_KIND_BY_CODE[code]` 恢复 kind（L350），kind/code 错配 fail closed

**测试验证：**
- `test_upload_format_error_maps_to_closed_usage_failure`：三个 `FinsUploadFormatFailureKind` 全部映射为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`
- `test_unsupported_upload_format_reason_strict_json_round_trip`：exact JSON 往返
- `test_upload_failure_json_rejects_unknown_or_mismatched_kind_code`：kind/code 错配与未知 code 被拒绝

### 8. 取消、rollback、commit linearization 是否回退 ✅

**证据：**

- `commit_prepared_upload_batch`（`docling_upload_service.py:910-963`）：逻辑未变更
- `_build_pending_assets`（L768-769）：取消检查从 `break` 改为 `raise DoclingConversionCancelledError()`，由 `prepare_upload` 的 `except DoclingConversionCancelledError`（L357-361）捕获并返回 cancelled result
- 取消后的 publication 不发生：exception 在 `_PreparedAssetMutation` 构造前抛出
- `rollback_prepared_upload_batch`（L966-993）：逻辑未变更

## 辅动检查

### raw list 旁路 ✅ 无

- Filing：`authoritative_request.file_selection` 是 typed `FinsUploadFilingFiles`，不含 raw list 旁路
- Material：`FinsUploadMaterialFiles.from_upsert_paths(tuple(file_list))` 在 workflow 内构造 typed selection，raw `file_list` 只用于 event payload 的 `file_count` 和最终 result 的 `files` 字段（展示用）
- Service：`prepare_upload` 签名从 `files: list[Path]` 改为 `selection: FinsUploadFilingFiles | FinsUploadMaterialFiles`，不接受 raw list

### 隐式 None/fallback ✅ 无

- `_prepare_upload_selection`：filing delete 产生空 `ordered_files` 和空 `converter_inputs`，service action/emptiness 校验正确拒绝 `delete + files` 和 `create/update + empty`
- `primary_document`：从首次转换直接产生，不再有 `_pick_primary_docling_file` 的 `None` fallback
- `_FAILURE_KIND_BY_CODE`：module-load 断言确保完整覆盖，不存在未映射 code 的 fallback

### 错误 event/count ✅ 无

- `stored_file_count` 只累计 `source == "original"` 的 assets（L541-542）
- Filing companions 作为 original assets 存储但不转换，count 正确
- `test_execute_upload_counts_only_successful_original_stores`：验证 4→3 entries（filing 只转 primary）且 `stored_file_count == 2`

### 测试假设与格式化 churn ✅ 无实质问题

- 旧测试 `test_corrupt_mixed_filing_fails_fast_without_publication`（参数化 2 组）拆分为 `test_corrupt_primary_with_valid_companions_fails_without_publication`（单组），因为 filing 现在只转换 primary，旧的 "valid.pdf 先转换再 corrupt.docx 失败" 场景不再适用
- `_OpenCancellationToken.__call__`：新增方法满足 `FinsJobCancellationChecker` 协议要求（`CancellationToken + Protocol`），是必要的测试适配
- 格式化变更（`published_names` 长行拆分、空行删除）：均为 Black 格式化，无语义变更

## Findings

### F1 — `_validate_source_files` docstring 中 "文件列表为空" 描述已过时

- **Severity：** Nit（不阻塞）
- **证据：** `docling_upload_service.py:1043` — `Raises: ValueError: 文件路径类型非法时抛出。` docstring 中无 "文件列表为空"，但旧版 `_validate_source_files` 的 docstring 包含该描述。当前版本 docstring 已正确更新。
- **影响：** 无。docstring 与实现一致。
- **修复：** 无需修复。已确认 docstring 准确。

*经仔细复核，此 finding 不成立。F1 撤回。*

### F2 — material 空文件（0 bytes）不在 service 层被拦截

- **Severity：** Low（不阻塞）
- **证据：** `_build_original_assets`（L711）只对 `SourceKind.FILING` 检查空数据。Material 空文件通过格式校验后到达 converter，由 converter 决定是否失败。
- **影响：** 空 material 文件的行为由 converter 实现定义，非 service contract。这是设计选择（filing 有显式空文件 failure code，material 依赖 converter），不是回归。
- **修复：** 不在本 slice scope 内。若需统一，应在 `_build_original_assets` 中对 material 增加空文件检查，但这属于新功能而非 bug fix。

### F3 — `_OpenCancellationToken.__call__` 是协议适配而非 bug

- **Severity：** Observation（不阻塞）
- **证据：** `FinsJobCancellationChecker` 继承 `CancellationToken + Protocol`，要求 `__call__() -> bool`。旧 `_OpenCancellationToken` 只有 `is_cancelled()`，新增 `__call__` 是满足生产类型协议的必要测试适配。
- **影响：** 无。测试正确反映生产协议要求。

## Verdict

**PASS** — blocking finding 为 0。

所有 plan 要求的 contract 行为已正确实现：
1. typed selection 在零 I/O 前完成 source_kind/emptiness 双向校验
2. filing 只转 primary、material 全转
3. primary_document 从首次转换直接产生，不再扫描
4. companion 事件/计数/原子 batch 行为正确
5. SEC/CN 使用 fresh authoritative selection
6. material admission 在 state/file/mutation 前且 catch-all 投影
7. USAGE/UNSUPPORTED_UPLOAD_FORMAT JSON closed roundtrip 完整
8. 取消/rollback/commit linearization 未回退

无 raw list 旁路、隐式 None/fallback、错误 event/count 或测试格式化 churn。

## 验证

- Focused test suite（5 files）：127 passed, 3 warnings
- 实现文档声明：1227 passed, 1 skipped, 3 warnings（完整 focused suite）
- Pyright changed files：0 errors（由实现文档确认）
- Ruff/Black：通过（由实现文档确认）
