# WU-TOOLS-01-F01-03 Slice 3 Implementation - AgentCodex

## Scope

本 Slice 只实现 CN/HK download migration：

- 迁移 OLD 巨潮 CNInfo downloader 与披露易 HKEXNews downloader。
- 迁移 OLD CN/HK download workflow 所需的 typed models、protocols、PDF gate、source upsert、staging、company meta、form/window helper、single filing workflow 与 ticker workflow。
- 新增窄 `CnPipeline` download facade 和同步 `FinsSourceDownloadAdapter` persisted-summary adapter。
- 在 `DefaultFinsRuntime.get_ingestion_runtime()` 注册：
  - `(source="cninfo", market="CN")`
  - `(source="auto", market="CN")`
  - `(source="hkexnews", market="HK")`
  - `(source="auto", market="HK")`

## OLD Import Tracing Evidence

直接 tracing 证据来自 `/Users/leo/workspace/dayu-agent`：

- `dayu/fins/downloaders/cninfo_downloader.py` 直接依赖 `cn_download_models` 和 OLD `dayu.log`；业务规则完整复制，NEW 仅适配日志 import。
- `dayu/fins/downloaders/hkexnews_downloader.py` 直接依赖 `cn_download_models` 和 OLD `dayu.log`；业务规则完整复制，NEW 仅适配日志 import。
- `dayu/fins/pipelines/cn_download_workflow.py` 直接 import `cn_download_company_meta`、`cn_download_filing_workflow`、`cn_download_models`、`cn_download_rebuild`、`cn_download_protocols`、`cn_form_utils`、`docling_upload_service.build_cn_filing_ids`、`download_events`、ticker normalization。
- `dayu/fins/pipelines/cn_download_filing_workflow.py` 直接 import `cn_download_pdf_gate`、`cn_download_models`、`cn_download_protocols`、`cn_download_source_upsert`、`cn_download_staging`、`docling_upload_service.build_cn_filing_ids`、`download_events`、storage protocols。
- `cn_download_rebuild.py` 是 OLD ticker workflow 的 direct import，因此作为额外 helper 迁移；它只做本地已下载 source meta/manifest rebuild，不访问远端、Docling 或 upload runner。
- `docling_upload_service.build_cn_filing_ids` 是 download workflow 的 direct helper 依赖；没有迁移 upload service，改为把该 ID 生成算法按 OLD seed 与 SHA-1 规则迁入 `cn_form_utils.build_cn_filing_ids`。
- `cn_download_protocols.py` 的 OLD `dayu.fins.docling_export.PdfToDoclingJsonBytes` 依赖收敛为本 Slice 内的窄 `Callable[[bytes, str], bytes]` 类型别名；默认转换实现放在 `cn_pipeline.py`，调用 NEW `dayu.documents.docling_runtime.convert_pdf_bytes_with_docling` 并返回 JSON bytes。
- OLD `cn_pipeline.py` 是 upload/process/download 混合大文件；Slice 3 只迁移 `download` / `download_stream` / `run_cn_download_stream_impl` 所需窄 facade，没有迁移 upload/process/CLI。

## What Changed

- 新增 production:
  - `dayu/fins/downloaders/cninfo_downloader.py`
  - `dayu/fins/downloaders/hkexnews_downloader.py`
  - `dayu/fins/pipelines/cn_download_*.py`
  - `dayu/fins/pipelines/cn_form_utils.py`
  - `dayu/fins/pipelines/cn_pipeline.py`
- 更新 production:
  - `dayu/fins/downloaders/__init__.py`
  - `dayu/fins/pipelines/download_events.py`
  - `dayu/fins/service_runtime.py`
- 新增/更新 tests:
  - `tests/fins/test_cninfo_downloader.py`
  - `tests/fins/test_hkexnews_downloader.py`
  - `tests/fins/test_cn_download_workflow.py`
  - `tests/fins/test_cn_download_runtime.py`
  - `tests/fins/test_cn_pipeline.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
- README:
  - `dayu/fins/README.md`
  - `tests/README.md`

## Invariants

- 迁移不是重写：CNInfo/HKEXNews 的 discovery、title filtering、amended preference、language、PDF fingerprint、HTTP retry/sleep、PDF 校验规则从 OLD 复制后仅适配 imports/logging/typing。
- 同步 adapter boundary 保留：`CnDownloadAdapter.download()` 同步调用窄 `CnPipeline.download()`，内部用 `asyncio.run` 聚合 OLD async event stream；未新增 async adapter protocol。
- Storage-only 写入：company meta、source meta、blob、processed reprocess marker、rebuild meta 均通过 `dayu.fins.storage` 仓储协议；没有直接拼业务 workspace 文件路径。
- CN/HK auto fallback 确定性：`auto/CN` 与 `cninfo/CN` 指向同一个 adapter；`auto/HK` 与 `hkexnews/HK` 指向同一个 adapter。
- Ticker normalization：ticker market 判定使用 `dayu.fins.ticker_normalization`；workflow 仍通过 `try_normalize_ticker` 归一化。
- User-Agent / rate-limit defaults：CNInfo 与 HKEXNews downloader 均保留 typed module constants，并由 downloader tests 断言默认 UA、sleep interval 和 retry count。
- PDF gate 语义：测试覆盖 Docling conversion 不在 PDF download gate 持有期间执行。
- Cancellation：使用 runtime job cancellation checker 传入 workflow 边界；OLD 内部取消异常迁移为 CN download 私有控制流异常，不引入 Host。
- No upload/process/CLI：未迁移 CN/HK upload runner、process/preprocess helpers 或 CLI entrypoint。
- No weak typing expansion：生产和测试 touched 文件 targeted scan 未命中 `Any` / type `object`。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `111 passed, 3 warnings`
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- Targeted scan:
  - Command scanned Slice 3 touched production/test files with `rg -n "\bAny\b|\bobject\b" ...`
  - Result: no matches.

## README Decision

README trigger applied because `dayu/fins/` and `tests/` changed.

- Updated `dayu/fins/README.md` because it previously stated CN/HK download was not built into the default runtime; current code now registers SEC/CN/HK production download adapters.
- Updated `tests/README.md` because Fins test coverage now includes CNInfo/HKEXNews downloader, CN/HK pipeline, and runtime auto adapter coverage.

## Residual Risks / Blockers

- No blocker.
- Tests use deterministic fake discovery/converter for runtime workflow and MockTransport for downloader HTTP behavior; they do not perform live CNInfo/HKEXNews network calls.
- Default Docling conversion path is typed and wired through `dayu.documents.docling_runtime`, but integration with real Docling runtime is not exercised in this Slice test set.
