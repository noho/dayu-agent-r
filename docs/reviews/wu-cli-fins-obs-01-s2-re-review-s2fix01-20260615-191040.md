# WU-CLI-FINS-OBS-01 S2 Scoped Re-Review

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S2-fins-runtime-progress-events`
- Re-review target: `S2-FIX-01` progress branch test coverage
- Controller adjudication: `docs/reviews/wu-cli-fins-obs-01-s2-code-review-adjudication-20260615-190347.md`
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-s2-fix-codex.md`
- Original reviews: `docs/reviews/code-review-20260615-190033.md` (AgentMiMo), `docs/reviews/code-review-20260615-190232.md` (AgentDS)
- Re-review scope: `tests/fins/test_fins_ingestion_runtime.py` 中 S2-FIX-01 新增/调整的测试，以及 fix artifact
- Excluded scope: S2 生产实现（除非新增测试暴露直接矛盾），deferred items（preprocess skipped_count 语义、record/latest 快照）

## Verification

### Check 1: download.completed_with_failures

- **测试**: `test_start_download_failed_count_emits_completed_with_failures_progress` (line 944)
- **入口**: `_PersistedSummaryDownloadAdapter` 注入 `failed_count=1` 的 `FinsDownloadResultSummary`
- **断言**:
  - `source_event_type` 序列为 `["download.started", "download.completed_with_failures"]`（line 971-974）
  - `progress_events[1].message == "下载已完成，存在失败候选"`（line 975）
  - `progress_events[1].payload["failed_count"] == 1`（line 976）
  - `progress_events[1].payload["downloaded_count"] == 1`（line 977）

**结论**: ✅ 已覆盖，message 和 payload 关键字段均已断言。

### Check 2: upload.completed_with_failures

- **测试**: `test_start_upload_failed_status_emits_completed_with_failures_progress` (line 1378)
- **入口**: `_FakeUploadRunner` 注入 `status="failed"` 的 `FinsUploadResultSummary`
- **断言**:
  - `source_event_type` 序列为 `["upload.started", "upload.completed_with_failures"]`（line 1416-1419）
  - `progress_events[1].message == "上传已完成，存在失败"`（line 1420）
  - `progress_events[1].document_id == "aapl-investor-day"`（line 1421）
  - `progress_events[1].payload["upload_status"] == "failed"`（line 1422）

**结论**: ✅ 已覆盖，message 和 payload 关键字段均已断言。

### Check 3: preprocess.document_failed

- **测试**: `test_start_preprocess_general_exception_emits_document_failed_progress` (line 2404)
- **入口**: monkeypatch `_preprocess_one_document` 抛 `RuntimeError("processor crashed")`
- **断言**:
  - `source_event_type` 序列为 `["preprocess.selected", "preprocess.document_started", "preprocess.document_failed", "preprocess.completed"]`（line 2446-2451）
  - `progress_events[2].message == "预处理源文档失败"`（line 2452）
  - `progress_events[2].document_id == "aapl-2024-10k"`（line 2453）

**结论**: ✅ 已覆盖，message 和 document_id 均已断言。

### Check 4: preprocess.document_not_supported

- **测试**: `test_start_preprocess_unsupported_document_records_not_supported_summary` (line 2456)
- **入口**: 使用空的 `ProcessorRegistry()`（无任何已注册处理器）触发 `_PreprocessNotSupportedError`
- **断言**:
  - `source_event_type` 序列为 `["preprocess.selected", "preprocess.document_started", "preprocess.document_not_supported", "preprocess.completed"]`（line 2479-2484）
  - `progress_events[2].message == "预处理源文档不支持"`（line 2485）
  - `progress_events[2].document_id == "aapl-2024-10k"`（line 2486）

**结论**: ✅ 已覆盖，message 和 document_id 均已断言。

### Check 5: AGENTS.md 合规性

- **中文 docstring**: 所有新增/调整的测试函数、类、方法均有完整中文 docstring，覆盖参数、返回值、异常。✅
- **无 Any/object/无类型签名**: 检查全部新增代码：
  - `_PersistedSummaryDownloadAdapter.__init__` 使用 `FinsDownloadResultSummary | None` ✅
  - `test_start_download_failed_count_emits_completed_with_failures_progress` 参数类型为 `Path` ✅
  - `test_start_upload_failed_status_emits_completed_with_failures_progress` 参数类型为 `Path` ✅
  - `test_start_preprocess_general_exception_emits_document_failed_progress` 参数类型为 `Path, pytest.MonkeyPatch` ✅
  - `test_start_preprocess_unsupported_document_records_not_supported_summary` 参数类型为 `Path` ✅
  - `fail_preprocess_document` 内部函数使用 keyword-only 参数与完整类型注解 ✅
- **无兼容逻辑**: 未为保旧测试添加任何兼容性代码。`_PersistedSummaryDownloadAdapter.summary` 参数的默认值语义与原有行为一致（skipped summary），是纯扩展，不是兼容性 wrapper。✅

### Check 6: 未修改生产语义

- 所有变更均在 `tests/fins/test_fins_ingestion_runtime.py` 内。
- `_PersistedSummaryDownloadAdapter` 是测试替身，仅在测试模块内使用。
- `dayu/fins/ingestion_runtime.py` 生产代码未被修改。✅

### Check 7: 独立验证

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
# => 53 passed, 3 warnings (仅 edgar deprecation warnings)
```

```bash
source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py
# => 0 errors, 0 warnings, 0 informations
```

与 fix artifact 声明的结果一致。✅

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 新增的四个测试通过 monkeypatch（`_preprocess_one_document`）或空 `ProcessorRegistry` 触发目标分支，不经过真实 adapter/runner 或 production processor 路径。这符合 S2-FIX-01 的范围——验证 progress event 的 source_event_type 选择和 payload 构造在对应分支下正确，而非验证真实 processor 行为。真实 processor 路径的回归防护由已有的 `test_start_preprocess_processes_source_document_to_processed_repository` 等测试覆盖。
- 所有 deferred items（preprocess skipped_count 语义、record/latest 快照）不在本次复核范围内，由 controller 裁决 deferred 到后续 slice 处理。

## Conclusion

**PASS**

S2-FIX-01 全部关闭：**4/4 fixed**。

| 核对项 | 状态 |
|--------|------|
| download.completed_with_failures 分支覆盖 | ✅ |
| upload.completed_with_failures 分支覆盖 | ✅ |
| preprocess.document_failed 分支覆盖 | ✅ |
| preprocess.document_not_supported 分支覆盖 | ✅ |
| AGENTS.md 合规（docstring/类型/无兼容逻辑） | ✅ |
| 未修改生产语义 | ✅ |
| 53 passed / pyright 0 errors | ✅ |
