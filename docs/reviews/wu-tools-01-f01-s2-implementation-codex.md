# WU-TOOLS-01-F01 Slice S2 Implementation Report

## Gate Metadata

- Gate: implementation only.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S2 - Preprocess / Process Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s2-implementation-codex.md`.
- Scope guard: 本轮只执行 Slice S2；未进入 S3/S4、review、commit、push 或 PR gate。

## 第一性原理判断与代码证据

动机成立。买方财报 Agent 的 preprocess/process 不是工具 provider 的 UI 细节，而是财报文档从 source storage 到 processed storage 的业务操作。如果该逻辑分散到 tool provider、未来 CLI 或 CI runner，会导致 document selection、overwrite/reprocess、processor fallback、processed metadata 与 job terminal summary 分裂。正确修复点是共享的 `dayu.fins` runtime。

直接代码证据：

- `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md` 的 S2 明确要求 `FinsIngestionRuntime.start_preprocess(request) -> job store -> executor -> source repository -> processor registry -> processed repository -> terminal update`。
- `dayu/fins/ingestion_runtime.py` 在 S1 后只有 `start_preprocess` 创建 queued job record，未执行 source 读取、processor 处理或 processed 写入。
- `dayu/fins/storage/repository_protocols.py` 已有 `SourceDocumentRepositoryProtocol` 的 `list_source_document_ids`、`get_source_meta`、`get_primary_source`，以及 `ProcessedDocumentRepositoryProtocol` 的 `create_processed`、`update_processed`、`get_processed_meta`，足以表达 S2，不需要直接写 `processed/` 文件树。
- `dayu/documents/processors/processor_registry.py` 已提供 `create_with_fallback`，`dayu.fins.processors.registry.build_fins_processor_registry()` 已装配 Fins processor registry，S2 可以复用现有 processor 边界。
- `dayu/fins/storage/_fs_processed_core.py` 的 `create_processed` / `update_processed` 会写 `sections.json`、`tables.json`、`financials.json` 与 processed manifest，并走仓储内部 auto batch，满足不绕过 storage 的要求。

## 改动文件与关键设计

- `dayu/fins/ingestion_runtime.py`
  - 新增 `FinsIngestionExecutor` 协议与最小 `FinsIngestionThreadExecutor`，`start_preprocess` 在 durable queued record 创建后提交后台执行。
  - `FinsIngestionRuntime` 显式持有 `ProcessorRegistry`，通过 `source_repository` 选择文档、读取 source/meta，通过 `processor_registry.create_with_fallback` 生成 processor，通过 `processed_repository.create_processed/update_processed` 写入 processed 产物。
  - 支持显式 `document_ids` 与 whole-ticker 选择，whole-ticker 选择受 `_MAX_PREPROCESS_DOCUMENTS` 限制。
  - `rebuild_processed=False` 跳过已有 processed 文档；`rebuild_processed=True` 更新已有 processed 文档。
  - 后台异常收口为 failed terminal record；取消请求收口为 cancelled；unsupported processor 记录 `not_supported_document_ids`，只有无任何请求文档完成处理且包含失败/unsupported 时 job failed。
  - job summary 只包含 selected/processed/skipped/failed 计数与 document ids，不包含 Host refs、文件系统路径或正文 payload。
- `dayu/fins/service_runtime.py`
  - `DefaultFinsRuntime.get_ingestion_runtime()` 把 shared `processor_registry` 注入 ingestion runtime。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 增加可控 `_HoldingExecutor`，覆盖 queued-before-execution 与取消。
  - 增加 source fixture，经仓储 public API 写入 source 文档。
  - 覆盖成功 preprocess、skip existing、rebuild update、cancel before execution、missing document failed terminal、unsupported processor not_supported summary。
- `dayu/fins/README.md`
  - 同步说明 preprocess runtime pipeline 已落地，download 仍只持久化 queued record。
- `tests/README.md`
  - 同步 Fins ingestion runtime 测试覆盖范围。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
  - 结果：29 passed。
  - 备注：出现 edgartools deprecation warnings，非本 slice 新增失败。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations。
  - 备注：pyright 提示有新版本可用，未影响验证。

## README 同步

已同步：

- `dayu/fins/README.md`：原文仍写 `start_preprocess` 只持久化 queued record，S2 后该稳定说明已过期。
- `tests/README.md`：原文只描述 ingestion runtime foundation，未覆盖 preprocess source -> processed pipeline 与新增测试语义。

未更新其它 README，因为本 slice 未修改 Host/Engine/Service/config/CLI 使用方式，也未新增 tool provider 或 CLI 入口。

## 未覆盖风险与 Blocker

- `covered by later approved slice`: `start_download` 仍只创建 queued record；真实 download pipeline 属于 S3。
- `covered by later approved slice`: preprocess tool provider、Host wait adapter wiring、service host assembly wiring 属于后续 slice。
- `assigned to later work unit`: processed `financials` 当前写入为 `None`，因为现有 processor protocol 没有统一结构化 financials 生产方法；本 slice 写入 sections/tables/meta，未发明新的 financials contract。
- `fixed in current slice`: 未发现需要直接文件树写入的 storage blocker；S2 全部 source/processed 访问均通过 repository protocols。

Completion status: S2 implementation complete; stopped before review/commit/push/PR gate as requested.
