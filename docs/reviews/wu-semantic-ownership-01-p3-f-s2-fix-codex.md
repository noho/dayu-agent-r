# WU-SEMANTIC-OWNERSHIP-01 P3-F S2 Fix Report

## 修复对象

- Finding: `P3-F-S2-CR-F01`
- 来源: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-code-review-ds.md` 与 controller adjudication
- 结论: accepted

## 修复说明

`dayu/fins/pipelines/sec_download_filing_workflow.py` 中，`run_download_single_filing_stream(...)` 原先先构造：

```python
source_handle = SourceHandle(...)
```

随后立即用 `stage_downloaded_filing_source_document(...)` 的返回值覆盖同一变量。第一份 `SourceHandle` 从未被读取，是死代码，并且会弱化 S2 想表达的 owner boundary：blob 写入前可用的 `source_handle` 应清晰来自 source repository acknowledgement，或来自该 helper 内部对已完成 source meta 的分支判断。

本次只删除该死赋值，保留 `stage_downloaded_filing_source_document(...)` 调用位置、参数和后续 downloader callback 行为不变。

## Owner Boundary 影响

- Source repository 仍是 source acknowledgement 真源。
- SEC workflow 仍在 stream / legacy downloader `store_file` callback 之前调用 `stage_downloaded_filing_source_document(...)`。
- Blob repository guard、upload staging、completion stable field protection、CN workflow 均未改动。
- 未修改测试；现有 S2 测试继续覆盖 staging 顺序和 ownerless blob 拒绝语义。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py -q`
  - 结果: `66 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果: 通过，无输出

## 残余风险

- 本次修复只处理 accepted finding F01 的死代码，不改变 S2 的既有 residual risk。
- SEC full pipeline 失败后的 incomplete staging 是否被 stale cleanup 保留仍属于 S2 implementation report 中记录的 residual；核心约束仍是不得产生 ownerless blob。

## 完成状态

ready-for-code-review
