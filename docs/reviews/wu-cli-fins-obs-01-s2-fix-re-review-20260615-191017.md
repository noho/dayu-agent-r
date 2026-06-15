# WU-CLI-FINS-OBS-01 S2 Fix Re-Review

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S2-fins-runtime-progress-events`
- Fix item: `S2-FIX-01`
- Re-review type: scoped fix closure verification
- Controller adjudication: `docs/reviews/wu-cli-fins-obs-01-s2-code-review-adjudication-20260615-190347.md`
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-s2-fix-codex.md`
- Review artifacts reviewed:
  - AgentMiMo: `docs/reviews/code-review-20260615-190033.md`
  - AgentDS: `docs/reviews/code-review-20260615-190232.md`
- Re-review scope: `tests/fins/test_fins_ingestion_runtime.py` 中为 S2-FIX-01 新增/调整的测试，以及 fix artifact
- Excluded scope: S2 生产实现重新审查（除非新增测试暴露直接矛盾）；deferred items（preprocess skipped_count 语义、record/latest 快照）

## Verification Checklist

### 1. download.completed_with_failures 分支覆盖

**Status: ✅ CLOSED**

- Test: `test_start_download_failed_count_emits_completed_with_failures_progress` (line 944-977)
- Setup: `_PersistedSummaryDownloadAdapter` 传入 `FinsDownloadResultSummary(failed_count=1)`
- Assertions:
  - `source_event_type == "download.completed_with_failures"` ✅
  - `message == "下载已完成，存在失败候选"` ✅
  - `payload["failed_count"] == 1` ✅
  - `payload["downloaded_count"] == 1` ✅

### 2. upload.completed_with_failures 分支覆盖

**Status: ✅ CLOSED**

- Test: `test_start_upload_failed_status_emits_completed_with_failures_progress` (line 1378-1422)
- Setup: `_FakeUploadRunner` 传入 `FinsUploadResultSummary(status="failed")`
- Assertions:
  - `source_event_type == "upload.completed_with_failures"` ✅
  - `message == "上传已完成，存在失败"` ✅
  - `document_id == "aapl-investor-day"` ✅
  - `payload["upload_status"] == "failed"` ✅

### 3. preprocess.document_failed 分支覆盖

**Status: ✅ CLOSED**

- Test: `test_start_preprocess_general_exception_emits_document_failed_progress` (line 2404-2453)
- Setup: monkeypatch `_preprocess_one_document` 抛出 `RuntimeError("processor crashed")`
- Assertions:
  - `source_event_type == "preprocess.document_failed"` ✅
  - `message == "预处理源文档失败"` ✅
  - `document_id == "aapl-2024-10k"` ✅
  - `record.result_summary["failed_document_ids"] == ["aapl-2024-10k"]` ✅

### 4. preprocess.document_not_supported 分支覆盖

**Status: ✅ CLOSED**

- Test: `test_start_preprocess_unsupported_document_records_not_supported_summary` (line 2456-2486)
- Setup: 使用空 `ProcessorRegistry()` 使文档无法匹配处理器
- Assertions:
  - `source_event_type == "preprocess.document_not_supported"` ✅
  - `message == "预处理源文档不支持"` ✅
  - `document_id == "aapl-2024-10k"` ✅
  - `record.result_summary["not_supported_document_ids"] == ["aapl-2024-10k"]` ✅

### 5. AGENTS.md 合规检查

**Status: ✅ COMPLIANT**

- 中文 docstring: 所有新增测试函数均有完整中文 docstring ✅
- 无 `Any`/`object`/无类型签名: 检查全部新增测试，未使用 `Any`、`object` 或无类型参数/返回值 ✅
- 未为保旧测试加入兼容逻辑: 只新增测试，未修改既有测试断言或生产代码 ✅

### 6. 生产语义未修改

**Status: ✅ VERIFIED**

- Fix artifact 明确声明: "未修改 `dayu/fins/ingestion_runtime.py` 生产语义" ✅
- 只扩展测试替身 `_PersistedSummaryDownloadAdapter`，允许传入固定 persisted summary ✅
- `dayu/fins/ingestion_runtime.py` 未出现在 fix changes 中 ✅

### 7. 验证结果

**Status: ✅ PASSED**

- `pytest tests/fins/test_fins_ingestion_runtime.py -q`: `53 passed, 3 warnings` ✅
- `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`: `0 errors, 0 warnings, 0 informations` ✅

## Deferred Items (Not Handled)

按 controller 裁决，以下 deferred items 不在本次 fix 范围内：

- `S2-DEFER-01`: preprocess completed skipped_count 语义重叠
- `S2-DEFER-02`: preprocess progress event record 快照 vs latest 快照

## Conclusion

**PASS**

**S2-FIX-01: 4/4 fixed**

全部 4 个 progress branch 测试覆盖已关闭：

1. ✅ `download.completed_with_failures` — 断言 source_event_type、message、payload 关键字段
2. ✅ `upload.completed_with_failures` — 断言 source_event_type、message、document_id、payload 关键字段
3. ✅ `preprocess.document_failed` — 断言 source_event_type、message、document_id、failed_document_ids
4. ✅ `preprocess.document_not_supported` — 断言 source_event_type、message、document_id、not_supported_document_ids

新增测试遵守 AGENTS.md 约束，生产语义未被修改，pytest 53 passed，pyright 0 errors。
