# WU-CLI-DOWNLOAD-01 Slice 4 code-review fix

- 时间：2026-08-10 09:23:30 +08:00
- 基线 HEAD：`afde13dfeeb50f18bb35364ee15d8dcd23a7bcc2`
- Gate：implementation code-review fix，等待原 MiMo / DS rereview
- 输入：`docs/reviews/deep-review-20260810-slice4-mimo.md`、`docs/reviews/deep-review-20260810-slice4-ds.md`
- 约束：未修改 review artifacts、原 implementation artifact、README、Oracle/registry、base plan；未 commit、push 或创建 PR。

## 1. 裁决总表

| Finding / observation | 裁决 | 处置 |
|---|---|---|
| DS-F01：SC13 registry-only fallback 不可达 | `rejected-with-direct-evidence` | 保留 production fallback；新增真实顶层 transport typed failure 回归 |
| DS-F02：CN event company ID 可能与 durable owner 不一致 | `rejected-with-direct-evidence` | production 不改；现有 CN owner test 增加 event/source/company 三路同源断言 |
| DS-F03：prefetch cancel contract 未自足 | `accepted` | 修正 owner docstring；收口一个 conditional post-transport checkpoint；增加确定性回归 |
| MiMo：`create_source=True` 轻微耦合 | `rejected-with-reason`（非 defect） | production 不改；Phase B reset/create 不变量有直接证据 |

## 2. DS-F01 反驳证据

Reviewer 的“所有失败都 raise，正常只返回 `(True, None)`”前提不成立：

1. `dayu/fins/pipelines/sec_download_persistence.py:225-233` 完整消费 private typed prefetch events；transport safe failure 是 `_PrefetchFailed` 值，不是异常。
2. 同文件 `:247-258` 通过唯一 materializer 投影为 `file_failed`，形成非空 `failure_reason`。
3. 同文件 `:294-301` 仅对异常 rollback + re-raise；typed failure 明确走 `:297-299` rollback 并返回 `(False, failure_reason)`。因此 `False` 是正常、可达且有业务含义的封闭返回分支。
4. `dayu/fins/pipelines/sec_download_workflow.py:843-877` 对 `Sc13DirectionRejectedWithArtifact` 消费该返回值：成功时 artifact+registry 已同 batch 发布；`False` 时进入独立 registry-only durable unit。
5. v2 amendment `§5.4`（`:221-223`）与状态矩阵（`:295-297`）明确规定：SC13 listing/prefetch failure 发布 registry-only；6-K 同类失败则 artifact/registry 均保持 old 并投影 filing failure。删除 fallback 会破坏已接受的 provider-specific policy，而不是清理 dead compatibility code。
6. DS review 自身 `§2.5` 已把 `sec_download_workflow.py:863-877` 判为“SC13 listing/transport 失败 → registry-only PASS”，与 DS-F01 的不可达结论自相矛盾。

新增 `tests/fins/test_sec_pipeline_download.py::test_sec_pipeline_sc13_transport_failure_publishes_registry_only`，通过真实 `SecPipeline.download` 产生 `_PrefetchFailed(provider_unavailable)`，断言 registry entry durable 存在且 rejected artifact 不存在。该测试在未改 fallback 的生产调用链上通过，构成可达性动态证据。

## 3. DS-F02 owner 证据

三处事实均由 `dayu.fins.ticker_normalization` 的同一 public owner 产生：

- observable event：`cn_download_workflow.py:92-96` 取得 `NormalizedTicker`，`:199-204` 调 `ticker_to_company_id(normalized)`；
- durable company meta：`cn_download_company_meta.py:44-48` 调 `normalize_ticker` 后调用同一个 `ticker_to_company_id`；
- durable source meta：`cn_download_source_upsert.py:244-252` 同样调用 `ticker_to_company_id(normalize_ticker(ticker))`。

因此不存在两个 company-ID owner，也不应把 company event 延迟到 persistence 返回后或在 workflow 增加重复推导注释。`tests/fins/test_cn_download_workflow.py::test_cn_download_top_level_success` 现直接断言 `COMPANY_RESOLVED.payload.company_id == source_meta.company_id == company_meta.company_id == "600519_SSE"`，防止三路投影漂移；production 未修改。

## 4. DS-F03 修复

`SecDownloader.prefetch_files_stream` 的 docstring 已改为自足 contract：

- 取消命中后正常停止 stream；首 descriptor 前为空 stream；中途可保留已 yield 前缀；
- 不为取消伪造 `_PrefetchFailed`；
- terminal consumer 完整消费后必须立即执行同一 cancellation checkpoint；iterator 结束不等价于操作成功；
- 不增加 cancel variant、不改变 `_PrefetchEvent` 或 public `DownloaderEvent` schema。

检查实现时发现 conditional transport 返回 payload 后的 checkpoint 原位于 `SecDownloadCancelledError` 捕获块外；该极窄窗口会与 v1 §4.2 的“停止 stream”契约不一致。修复仅在 `sec_downloader.py` owner 内捕获该 cooperative cancellation 并 `return`。新增 `test_download_files_stream_conditional_cancel_after_transport_stops_without_failure`：fake transport 返回 payload 时触发 Event-equivalent boolean gate，断言只保留 started 前缀、无 callback、无 failed、无异常外泄。既有 `test_download_files_stream_cancel_stops_without_failed_event` 与 rejected prefetch-before-begin owner test继续通过。

production `prefetch_files_stream` 引用已用 `rg` 完整枚举：

- `sec_download_persistence.py:226`：完整消费后 `:234-235` checkpoint；
- `sec_download_filing_workflow.py:480`：完整消费后 `:489-490` checkpoint；
- `sec_downloader.py:1784`：public wrapper 只保留同一 stop-with-prefix stream observable，并由唯一 materializer 投影。

## 5. MiMo `create_source=True` 裁决

MiMo 明确把该项标为“功能正确、非 blocker”。直接调用链也证明它不是 owner defect：

- `sec_download_filing_workflow.py:494-549` Phase B 先做 staged identity/classification；same-identity COMPLETE + `overwrite=False` 已 rollback + skip；
- `:550-556` 对非 MISSING target 先在同一真实 batch `reset_source_document`；MISSING target无需 reset；
- 两类继续路径在 source mutation 时都处于“target 已不存在、必须 create”的状态，因此 `:703 create_source=True` 与 `sec_download_source_upsert.py:99,144-149` 的参数 contract 一致。

把它改为 update 或恢复 phase-A 旧存在性分支会违反 staging 真实状态；本轮不做无收益 refactor。

## 6. 实际修改

- `dayu/fins/downloaders/sec_downloader.py`
  - 修正 `prefetch_files_stream` cancellation doc contract；
  - 收口 conditional payload-return 后的 cooperative cancellation。
- `tests/fins/test_sec_downloader.py`
  - 新增 conditional post-transport cancellation owner regression。
- `tests/fins/test_cn_download_workflow.py`
  - 增加 event/source/company durable company-ID 同源断言。
- `tests/fins/test_sec_pipeline_download.py`
  - 新增 SC13 typed transport failure → registry-only 顶层回归。

## 7. 验证原文与结果

```text
.venv/bin/pytest -q tests/fins/test_sec_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_sec_pipeline_download.py -k 'cancel or top_level_success or rejected_prefetch or sc13_artifact_transport_failure'
exit 0: 16 passed, 204 deselected

.venv/bin/pytest -q tests/fins/test_sec_downloader.py
exit 0: 53 passed

.venv/bin/pytest -q tests/fins/test_cn_download_workflow.py
exit 0: 55 passed

.venv/bin/pytest -q tests/fins/test_sec_pipeline_download.py
exit 0: 113 passed, 3 third-party deprecation warnings

.venv/bin/pyright dayu/ tests/ utils/
exit 0: 0 errors, 0 warnings, 0 informations

.venv/bin/ruff check dayu/fins/downloaders/sec_downloader.py tests/fins/test_sec_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_sec_pipeline_download.py
exit 0: All checks passed!

.venv/bin/ruff format --check dayu/fins/downloaders/sec_downloader.py tests/fins/test_sec_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_sec_pipeline_download.py
exit 0: 4 files already formatted

git diff --check
exit 0
```

## 8. 风险与 gate 状态

- DS-F01 的 fallback 有真实 typed failure 可达性与顶层 durable 回归；剩余风险不是 dead code，而是未来修改 transport projection 时必须继续保留 SEC SC13 与 6-K 的不同 policy owner。
- cancellation 仍是协作式 contract；所有 terminal production consumer 已枚举并在完整消费后 checkpoint，public wrapper 保留既有停止/前缀行为。
- 未运行新的全量 10x/coverage：本轮只改一个窄取消分支、两个 owner assertions，并已完成完整受影响 owner tests；Slice 4 implementation artifact 中的既有全量门结果未被改写或重复冒充。
- 当前停止在原 MiMo / DS 双路 rereview 入口；未 commit、push、创建 PR 或触碰 PR190。
