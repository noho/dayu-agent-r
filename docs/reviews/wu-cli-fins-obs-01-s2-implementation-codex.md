# WU-CLI-FINS-OBS-01 S2 Implementation Artifact

## Slice / Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: `implementation`
- Slice: `S2-fins-runtime-progress-events`
- Scope: 只实现 runtime-owned bounded `PROGRESS` events；不进入 S3/S4/S5，不做 review，不 commit/push/PR，不修改控制文档。
- Approved plan: `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- S1 accepted commit: `3787f43d`

## Files Changed

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-fins-obs-01-s2-implementation-codex.md`

未修改 forbidden files；工作区中既有的 `docs/host/issues-implementation-control.md` dirty change 本轮未触碰。

## Implementation Summary

- 在 `FinsIngestionRuntime` 增加私有 `_emit_progress_event(...)` helper，统一追加 `FinsIngestionJobEventType.PROGRESS`，并在 append / mapping 失败时只记录 bounded WARN 后继续。
- `download`：在同步 `adapter.download(request)` 调用前写入 `download.started`，返回有界 summary 后写入 `download.completed` 或 `download.completed_with_failures`。
- `upload`：在同步 `upload_runner.run_upload(...)` 调用前写入 `upload.started`，返回有界 summary 后写入 `upload.completed` 或 `upload.completed_with_failures`；未修改 runner protocol，未装配 runner 的 unsupported 路径保持原业务失败语义。
- `preprocess`：在文档选择、单文档开始、processed / skipped / failed / not_supported、请求完成处写入 progress；没有改变原有 preprocess selected / loop / terminal 判定状态机。
- progress payload 只包含 ticker、market、source、source_kind、form_types、action、file_count 与 bounded counts 等业务可读摘要；不写绝对路径、完整文件路径、上传文件名、财报正文、provider raw payload 或大段材料。
- progress event 不改变 job status；取消仍由现有 cancellation checker 与 terminal closeout 写入 `CANCELLED`。

## Tests / Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `50 passed`
  - Notes: 仅有 edgar 依赖 deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Notes: pyright 提示存在新版本，不影响本次验证。

新增 / 更新覆盖：

- fake download adapter 与 production SEC adapter 同步调用边界的 started / completed progress。
- fake upload runner 与 production upload runner 同步调用边界的 started / completed progress。
- preprocess selected / document started / processed / skipped / completed progress。
- event sidecar bounded payload 不含绝对路径、上传文件名、正文或 raw provider payload。
- progress append 失败时 job 仍按业务成功终态收口，并记录 bounded WARN。

## README Decision

- `dayu/fins/README.md`：已按约束小幅更新当前已落地事实，说明 runtime 在 download / upload 同步边界和 preprocess 文档处理路径写入粗粒度 progress，且 progress 不推进 job 状态。
- `tests/README.md`：已按约束同步 `tests/fins/test_fins_ingestion_runtime.py` 当前覆盖事实，加入 coarse `PROGRESS` event 与 progress append failure WARN-and-continue 覆盖说明。

## Deferred Sequence Lookup Scalability Decision

S1 的 `FsFinsIngestionJobStore.append_job_event(...)` 当前在同一 file lock 下全读 event sidecar 以查找最后 sequence。本 slice 重新评估后未引入 tail-scan 优化，原因如下：

- S2 新增事件量有明确上界：download/upload 各新增 2 条 progress；preprocess 受现有 `_MAX_PREPROCESS_DOCUMENTS = 50` 限制，每个文档最多 2 条 progress，再加 selected / completed，单 job 约 102 条 progress，叠加 S1 状态事件后仍是低百级。
- 当前全读 lookup 与 S1 并发 sequence 测试同源，锁语义清晰；在 S2 事件量下 I/O 成本可接受。
- tail-scan / reverse scan 需要处理 UTF-8 JSONL 边界、空行、损坏行与并发写入测试；在本 slice 中引入会增加风险，且用户明确要求不要做无测试的 risky tail-scan optimization。

因此 S2 保持现有 sequence lookup，不做优化；若后续 S3/S4/S5 引入高频 pipeline stream event，再单独以测试驱动优化。

## Residual Risks / Uncovered Areas

- `covered by later approved slice`: Service / CLI 消费这些 `PROGRESS` events 并展示 live output 尚未实现，属于后续 S3/S4/S5。
- `covered by later approved slice`: download/upload 细粒度 async pipeline stream consumption 未实现；本 slice 只做同步边界 coarse progress，未修改 adapter / runner protocol。
- `assigned to later work unit`: 若未来单 job event 数量扩大到高千级，需要重新评估 sidecar sequence allocation 的读取策略。

## Completion Status

`ready-for-review`
