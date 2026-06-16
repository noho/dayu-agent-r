# WU-CLI-FINS-OBS-01 S2 Fix Artifact

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S2-fins-runtime-progress-events`
- Fix item: `S2-FIX-01`
- Controller adjudication: `docs/reviews/wu-cli-fins-obs-01-s2-code-review-adjudication-20260615-190347.md`

## Changes

- 在 `tests/fins/test_fins_ingestion_runtime.py` 补齐 progress branch tests：
  - download summary `failed_count > 0` 时断言 `download.completed_with_failures`、message 和关键 payload。
  - upload summary `status="failed"` 时断言 `upload.completed_with_failures`、message 和关键 payload。
  - preprocess 单文档一般异常时断言 `preprocess.document_failed` progress。
  - preprocess unsupported processor 分支断言 `preprocess.document_not_supported` progress。
- 只扩展测试替身 `_PersistedSummaryDownloadAdapter`，允许测试传入固定 persisted summary。
- 未修改 `dayu/fins/ingestion_runtime.py` 生产语义。

## Validation

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
```

Result: `53 passed, 3 warnings`.

Warnings: 仅有 `edgar` 依赖 deprecation warnings。

```bash
source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py
```

Result: `0 errors, 0 warnings, 0 informations`.

## README Decision

- 本 fix 只补 `tests/fins/test_fins_ingestion_runtime.py` 内既有 S2 progress 能力的分支断言。
- `tests/README.md` 已描述 ingestion runtime 粗粒度 `PROGRESS` event 覆盖；本 fix 不新增测试层级、测试职责或稳定能力说明，因此不更新 README。

## Deferred Items Not Handled

- 未处理 `preprocess skipped_count` 与 `not_supported` 的 summary 语义重叠；该项已由 controller 裁决 deferred。
- 未处理 preprocess progress event 使用入口 `record` 快照而非 latest snapshot；该项已由 controller 裁决为未来 pause/resume 或 richer cancellation progress 的 residual note。
- 未修改 Service、CLI、adapter / runner protocol、pipeline stream 或线程模型。

## Status

`ready-for-scoped-re-review`
