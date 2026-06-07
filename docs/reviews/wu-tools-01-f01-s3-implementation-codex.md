# WU-TOOLS-01-F01 Slice S3 Implementation Artifact

## 范围

- Gate: implementation only。
- Slice: S3 - Download Runtime Pipeline。
- 未进入 code review / fix / re-review / commit / push / PR / 后续 slice。
- 未修改 Host / Engine / Service / tool provider。

## 第一性原理判断与直接代码证据

判断：S3 动机成立。生产级财报 Agent 不能让下载路径绕过 Fins runtime 与 storage 仓储协议，否则下载、预处理和未来 CLI / tool adapter 会产生不同的 ticker normalization、market/source 路由、overwrite/rebuild 与结果摘要语义。S3 的 root cause 是 `start_download` 仍停留在 S1 foundation：只创建 durable job record，没有 source adapter 协议、没有 normalized 后路由，也没有通过 source/blob/maintenance repository 写入源文档。

直接证据：

- `dayu/fins/ingestion_runtime.py` 既有 `FinsIngestionJobStore`、`FinsIngestionExecutor`、`_mark_job_running_or_cancelled(...)`、`_save_succeeded(...)`、`_save_failed(...)`，说明 S1/S2 已有可复用 job 语义。
- `dayu/fins/ingestion_runtime.py` 的 S2 `start_preprocess(...)` 已经 queued 后提交 executor，并通过 `SourceDocumentRepositoryProtocol` / `ProcessedDocumentRepositoryProtocol` 完成 source -> processed pipeline。
- 修改前 `start_download(...)` 只调用 `normalize_ticker(...)` 和 `_create_queued_job(...)`，没有提交 executor、没有 adapter selection、没有 storage write。
- `dayu/fins/storage/repository_protocols.py` 已有 `SourceDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol`、`FilingMaintenanceRepositoryProtocol`，足以表达 source/blob/rejected filing 写入；无需扩展 storage protocol。
- `dayu/fins/ticker_normalization.py` 明确 `normalize_ticker(...)` 是 ticker normalization 公共 API；下载路由必须基于该结果，不应由 adapter 解析 ticker 后缀。
- `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md` 的 S3 要求明确：download 通过同一 job store/executor，adapter receive `NormalizedTicker`，无 adapter 时 explicit unsupported-source failure，不实现真实 SEC/CN/HK 网络 adapter。

## 改动文件与关键设计

- `dayu/fins/ingestion_runtime.py`
  - 增加 Fins-owned typed download adapter protocol：`FinsSourceDownloadAdapter`、`FinsSourceDownloadAdapterRequest`、`FinsSourceDownloadAdapterResult`。
  - 增加 adapter 返回的业务形状：`FinsDownloadedFile`、`FinsDownloadedSourceDocument`、`FinsRejectedFilingDownloadArtifact`。
  - `start_download(...)` 现在调用 `normalize_ticker(...)` 后创建 queued job，再提交同一 `FinsIngestionExecutor`。
  - 后台 download job 按 `(source, normalized.market)` 选择 adapter；默认无 adapter 时写 failed terminal record，错误包含 source 和 market。
  - 成功路径通过 `SourceDocumentRepositoryProtocol` 创建 / 更新 source meta，通过 `DocumentBlobRepositoryProtocol` 写文件，通过 `FilingMaintenanceRepositoryProtocol` 写 rejected filing artifact。
  - 重复下载由 runtime storage 语义处理：`overwrite_existing=False` 时跳过已有 source document，`overwrite_existing=True` 时 reset 后重写。
  - job result summary 归一为 `discovered_count`、`downloaded_count`、`skipped_count`、`rejected_count`、`failed_count`、`written_document_ids`。

- `dayu/fins/service_runtime.py`
  - `DefaultFinsRuntime` 增加 blob repository 与 filing maintenance repository 装配，并传入 ingestion runtime。

- `tests/fins/test_fins_ingestion_runtime.py`
  - 增加确定性无网络 fake download adapter。
  - 覆盖 fake adapter 写 source/blob、unsupported source failed terminal、重复请求 skip、rejected filing artifact 维护仓储写入。
  - 原本只观察 download queued record 的测试改用 holding executor，避免 S3 后台 job 竞争影响 queued 断言。

- `dayu/fins/README.md`
  - 同步 ingestion runtime 当前稳定事实：download 已有 typed adapter protocol、storage write path 和 unsupported-source terminal failure；仍无真实 SEC/CN/HK 网络 adapter 与 tool provider。

- `tests/README.md`
  - 同步 Fins ingestion runtime 测试覆盖范围。

## 验证结果

已运行：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py
```

结果：35 passed，3 个 edgar 依赖 deprecation warnings。

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：0 errors，0 warnings，0 informations。pyright 提示有新版本可用，但不影响验证。

额外自查：

- `rg -n "\bAny\b|\bobject\b|hasattr\(|getattr\(" dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py` 无匹配。
- `git diff --name-only` 仅包含允许范围内的 Fins runtime、Fins README、tests README 与 Fins ingestion runtime 测试。

## README 同步

已同步：

- `dayu/fins/README.md`：命中 `dayu/fins/` 修改触发条件，且原文仍称 `start_download` 只创建 queued record，已过期。
- `tests/README.md`：命中 `tests/` 修改触发条件，且 Fins ingestion runtime 测试说明未包含 S3 download runtime 覆盖，已过期。

未同步其它 README：本 slice 未修改 CLI、config、Host/Engine/Service 分层关系、tool provider 或用户入口。

## 未覆盖风险与 blocker

- 未实现真实 SEC / CN / HK 网络下载 adapter；这是 S3 明确 non-goal，也是 stop condition 要求避免的范围。
- 当前 adapter registry 由 runtime 构造参数注入；生产 provider / wait adapter 暴露属于后续 S4，不在本 slice。
- 下载 adapter response 仍需未来真实 adapter owner 保证不携带 provider raw payload；runtime job record 只保存有界计数、document ids 与失败摘要。
- 未发现 S3 blocker。
