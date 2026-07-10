# Fins 开发手册

本文档是 `dayu.fins` 包的开发手册。

Fins 在整体架构中不是 `UI / Service / Host / Engine` 的一层，而是由工具与 Service assembly 接入的财报业务能力包：

```text
UI -> Service -> Host -> Engine
        |        |
        |        v
        |    ToolRuntime -> dayu.fins
        v
   Fins wait adapter assembly
```

## Agent更新约束【必须遵守】

- 本文档只写两类内容：
  - 当前代码已实现的整个 Agent 的设计意图、架构边界，范围包括 `UI -> Service -> Host -> Engine` 以及 Fins 作为财报业务能力包的位置。
  - 当前代码已实现的 `dayu.fins` package 的 capability 定位、两条执行路径、对外接口、公共契约、架构、稳定边界、主要组件、状态机、关键机制、Processors 的类继承关系和扩展点。
- 更新本文档时必须先核对 `dayu.fins` 当前代码；代码真源高于历史 plan、review artifact 或口头设计意图。
- 必须按本文档现有章节职责写作：`设计意图` 和 `架构边界` 先说明整个 Agent 与 Fins 位置；其后章节只说明 `dayu.fins` package。
- 不写用户手册、安装运行命令、测试清单、文件级流水账或 review / work unit 过程状态。
- 不写未来计划、路线图、未落地能力或实现细节；只保留当前代码已经实现且对开发者稳定有用的说明。

## 设计意图

Dayu 是生产级通用 Agent，具备买方财报分析能力，核心范式是“宿主强约束下的 LLM in the loop”。

在整个 Agent 中，LLM 负责分析、推理和生成；Host 负责生命周期、取消、恢复、工具治理、EventLog、memory / context governance 和持久化事实。Fins 提供买方财报分析所需的业务底座：财报文档存取、ticker 归一、公司信息 resolver、read tools、download / preprocess / upload direct stream、awaiting tools、processor registry、XBRL / financial statement 能力，以及把 lightweight observation handle 映射到 Host wait-resume 的 adapter。

`dayu.fins` 的设计重点是把财报业务能力从 Host / Engine 中剥离出来：

- Host / Engine 不读取财报文件树，不理解 SEC 表单、ticker、XBRL、章节切分或 processed 产物。
- 财报文档存取必须通过 `dayu.fins.storage` 的仓储协议与仓储实现完成。
- read、download、preprocess / process 与 upload foundation 共用 `DefaultFinsRuntime`、仓储协议、processor registry 和 workspace-scoped ingestion runtime，避免工具入口、测试 / CI 入口或其它入口复制业务逻辑后产生漂移。
- Fins 工具只暴露业务语义结果；工具权限、ToolRuntime accept barrier、截断、`fetch_more`、长事务 wait、cancel、resume 和审计仍由 Host / ToolRuntime 治理。
- Fins direct stream 是 CLI / Service direct 调用的用户可见进度边界；Fins awaiting observation handle 是 Host wait adapter 的轻量观察引用；二者都不是 Host durable truth。

## 架构边界

整体依赖方向固定为：

```text
UI -> Service -> Host -> Engine
```

- `UI` 负责展示、输入收集、流式订阅和用户动作触发。
- `Service` 负责业务入口、身份解析、配置 / scene / tool / runner 装配，并调用 Host。
- `Host` 负责 Agent 运行宿主边界、状态治理、持久化、工具运行时治理、memory / context governance、projection、恢复和取消。
- `Engine` 负责单次 run 的模型交互、Runner 协议归一、tool loop、取消观察和 `EngineEvent stream`。
- `Fins` 是财报业务能力包；它通过工具 provider、Fins runtime、storage、processor 和 wait adapter integration 被装配到 Agent 中，不成为新的架构层。

Fins 与其它层的稳定边界如下：

- Host 不导入 `dayu.fins`，不读取财报仓储，不执行财报下载 / 预处理，不解释财报业务规则；Host 只接收受治理工具结果或 wait adapter 映射后的 wait poll 结果。
- Engine 不导入 `dayu.fins`，不感知财报业务语义；Engine 只看到 Host 传入的 `ToolSchema` 和 `ToolExecutor`。
- Service / composition root 可以装配 Fins tools provider，也可以基于显式 Fins awaiting provider 配置构造 Host `WaitAdapterRegistry`；Service 负责把 raw config 映射为 typed assembly 输入。
- 除 `dayu.fins.ingestion.wait_adapter` 这个 Host wait integration 模块外，`dayu.fins` 不依赖 Host。wait adapter 只使用 Host wait-resume typed contract，不读取 Host durable store，也不改变 Host / Engine contract。
- Fins 不依赖 `dayu.service`、`dayu.ui` 或 `dayu.engine`；`dayu.engine` 与 `dayu.runtime` 也不得反向导入 Fins。

公共包边界固定如下：

- `dayu.contracts` 是 Dayu Agent 公共契约包，承载 UI / Service / Host / Engine / ToolRuntime / tools 可共同使用的层中立数据与协议，例如 JSON 值、取消 token、工具声明、工具 schema、工具调用请求、工具执行 outcome、工具等待 outcome 和 `ToolExecutor`；它不承载 Host / Engine 状态机，也不承载财报业务事实。
- `dayu.runtime` 是层中立运行期基础设施包，提供工具发现 provider contract、取消等待、日志级别、诊断文本脱敏、截断、filelock、lane 等可复用 helper；它不得依赖 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`，也不承载任何层的状态机或业务语义。
- `dayu.documents` 提供文档处理器公共协议、ProcessorRegistry 和通用 Docling / Markdown / BeautifulSoup 处理器；Fins 在其上注册财报业务增强处理器和 SEC 表单专项处理器。
- 工具声明契约属于 `dayu.contracts`；具体 Fins read / download / preprocess / upload 工具实现属于 `dayu.fins.tools`，工具发现装配属于 runtime discovery / Service assembly，工具运行时治理属于 Host / ToolRuntime。

## 接口

`dayu.fins` 包根当前不导出业务符号；开发者使用明确子包入口，避免把包根变成兼容性 re-export 面。

### Shared runtime

`dayu.fins.service_runtime.DefaultFinsRuntime` 是 Fins 默认共享装配根：

- `DefaultFinsRuntime.create(workspace_root=Path)`：由显式 Fins workspace root 创建文件系统仓储、processor registry、ingestion runtime 和 legacy job store。
- `get_read_runtime(processor_cache_max_entries=128)`：懒加载并缓存 `FinsReadRuntime`。
- `get_ingestion_runtime()`：懒加载并缓存 `FinsIngestionRuntime`。
- `get_processor_registry()`：返回 Fins processor registry。

`DefaultFinsRuntime` 不持有 Host、Service、EventLog、ToolRuntime 或 Engine Runner。共享语义不是进程级 singleton，而是同一 `workspace_root` 下复用同一套业务代码、仓储布局、processor registry 和 legacy job store。

### Storage

`dayu.fins.storage` 是财报文档存取边界，包内导出窄仓储协议与文件系统实现：

- `CompanyMetaRepositoryProtocol`
- `SourceDocumentRepositoryProtocol`
- `ProcessedDocumentRepositoryProtocol`
- `DocumentBlobRepositoryProtocol`
- `FilingMaintenanceRepositoryProtocol`
- `BatchingRepositoryProtocol`
- 对应 `Fs*Repository` 文件系统实现
- `FileStore` / `LocalFileStore`

source document meta 中的 `source_provider` 是来源提供方真源，当前支持 SEC EDGAR、巨潮资讯、港交所披露易与用户上传。`SourceDocumentRepositoryProtocol` 负责把 source meta 投影为 typed provenance；read runtime 的 citation 只消费该 provenance 来生成 LLM-facing `source_type` 与 `source_provider`。

source document acknowledgement 由 source repository 持有：完成态 source meta 或 `stage_source_document(...)` 写入的 `ingest_complete=false` staging meta 都表示该 source 已被仓储承认。`DocumentBlobRepositoryProtocol.store_file(SourceHandle, ...)` 只能在 source meta 已存在后写入 blob；下载与上传 pipeline 在首次 blob 写入前必须通过 source repository staging 或既有完成态 meta 获得承认。

`FilingMaintenanceRepositoryProtocol` 持有 SEC 下载拒绝注册表。注册表条目使用 `DownloadRejectionEntry` typed contract，包含 document id、拒绝原因、分类、SEC form、filing date 和下载版本；文件系统仓储读取非法 registry 时失败关闭，保存时只通过 typed entry 序列化，SEC 下载、SC13 过滤和下载诊断只消费该 typed registry。

上传链路的 company meta freshness 由 `dayu.fins.pipelines.upload_company_meta` 持有：只有既有 meta 的 `resolver_version` 等于当前 upload resolver 版本时才可保留；版本不一致时必须用本次上传字段重新校验并写入。`updated_at` 仅是审计时间，不是 freshness TTL。SEC/CN/HK 下载链路仍由各自 producer 写入公司元数据，不经上传 freshness 逻辑；read runtime 只读取仓储中的 company meta，不刷新或推断 freshness。

### Resolver

`dayu.fins.resolver` 是公司信息等财报业务标识解析能力的 public subpackage。`dayu.fins` 包根不 re-export resolver 符号，调用方应显式导入子包。

当前已实现 FMP 公司信息 resolver：

- `FmpCompanyInfo(canonical_ticker, company_name, ticker_aliases)`：不可变解析结果，`ticker_aliases` 是 tuple，首项恒为 canonical ticker。
- `FmpCompanyInfoResolver(api_key=..., http_client=..., timeout_seconds=...)`：显式接收 FMP API key 和 timeout，不读取环境变量。
- `resolve_company_info(canonical_ticker)`：先用 `search-symbol` 定位公司名，再用 `search-name` 搜索严格同名证券，alias 去重后返回；HTTP、JSON、空结果、非法 payload 或第二跳失败都会收口为 `FmpCompanyInfoResolutionError`。

resolver 只提供业务解析能力；调用方负责读取环境变量、配置超时、处理失败回退和决定是否把公司名投影给 LLM。

### Read runtime 与 read tools provider

`dayu.fins.tools.read_runtime.FinsReadRuntime` 是 read path runtime，当前提供：

- `list_documents`
- `get_document_sections`
- `read_section`
- `search_document`
- `list_tables`
- `get_table`
- `get_page_content`
- `get_financial_statement`
- `query_xbrl_facts`

`dayu.fins.tools.provider.discover_tools(spec)` 是 read tools 的 ToolsDiscovery provider 入口，provider id 为 `financial-read-tools`。启用时必须通过 effective spec 提供绝对 `workspace_root`，并返回九个 read tools；read provider 是否参与发现只由 provider-level `enabled` 控制。

当前 read tools 名称为：

- `list_documents`
- `get_document_sections`
- `read_section`
- `search_document`
- `list_tables`
- `get_table`
- `get_page_content`
- `get_financial_statement`
- `query_xbrl_facts`

### Download / preprocess / upload awaiting tools

Fins ingestion 通过三个独立 awaiting provider 暴露 awaiting tools：

- `dayu.fins.tools.download_provider.discover_tools(spec)`：provider id 为 `financial-download-tools`，返回 `start_fins_download`。
- `dayu.fins.tools.preprocess_provider.discover_tools(spec)`：provider id 为 `financial-preprocess-tools`，返回 `start_fins_preprocess`。
- `dayu.fins.tools.upload_provider.discover_tools(spec)`：provider id 为 `financial-upload-tools`，返回 `start_fins_upload`。

三个 awaiting provider 都必须通过 effective spec 获得绝对 `workspace_root`。upload provider 启用时注册 `start_fins_upload`；上传工具只在工具边界校验本地路径存在、指向普通文件且文件非空。当前实现不把本地源文件授权建模为 upload provider 的配置职责；调用方仍需在进入工具前承担本地文件来源可信性与用户授权。工具调用只注册 lightweight observation handle 并返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，不等待长事务完成、不直接 resolve Host wait，也不把 handle 当作业务事实返回给模型。上传后的 source/blob/processed 写入仍必须通过 Fins workspace repository 完成。

### Batch upload plan

`dayu.fins.upload_batch` 提供本地批量上传计划生成能力。它接收 `UploadBatchPlanRequest`，扫描调用方显式传入的本地源目录，并返回 `UploadBatchPlanResult` 与结构化 `UploadBatchPlanEntry` 条目。该 helper 通过公开常量 `FINS_UPLOAD_FILE_SUFFIXES` 固定 upload 输入后缀真源，只识别可作为 upload 输入的普通文件，并基于文件名中的 filing form token 或调用方传入的 `material_forms` 生成 `upload_filing` / `upload_material` 计划；它不启动 ingestion job、不读取 Fins storage、不创建 Host Run，也不输出 shell 文本。

### Ingestion runtime 与 wait adapter

`dayu.fins.ingestion_runtime.FinsIngestionRuntime` 是下载、预处理与上传的 typed runtime foundation。当前稳定入口分为 direct stream、awaiting observation 和 legacy durable job helpers：

- `download(FinsDownloadRequest, *, cancellation_token: CancellationToken | None = None) -> AsyncIterator[FinsEvent]`
- `preprocess(FinsPreprocessRequest, *, cancellation_token: CancellationToken | None = None) -> AsyncIterator[FinsEvent]`
- `upload(FinsUploadRequest, *, cancellation_token: CancellationToken | None = None) -> AsyncIterator[FinsEvent]`
- `start_observed_download(...) -> FinsObservationHandle`
- `start_observed_preprocess(...) -> FinsObservationHandle`
- `start_observed_upload(...) -> FinsObservationHandle`
- `prepare_observed_download(...) -> FinsObservationHandle`
- `prepare_observed_preprocess(...) -> FinsObservationHandle`
- `prepare_observed_upload(...) -> FinsObservationHandle`
- `activate_observation(handle) -> None`
- `poll_observation(handle) -> FinsObservationSnapshot`
- `cancel_observation(handle) -> FinsObservationSnapshot`
- `abandon_observation(handle) -> None`
- legacy helpers `start_download(...)` / `start_preprocess(...)` / `start_upload(...)` / `read_job(...)` / `read_job_events(...)` / `request_cancel(...)` 仍保留在 runtime foundation 中服务 legacy job-store 覆盖；Service direct 和 Fins awaiting tools 不消费这些入口。

`dayu.fins.ingestion.wait_adapter` 提供 Host wait-resume integration：

- `FINS_INGESTION_WAIT_ADAPTER_KEY = "poll:fins-ingestion"`
- `FINS_DOWNLOAD_AWAITING_TOOL_NAME = "start_fins_download"`
- `FINS_PREPROCESS_AWAITING_TOOL_NAME = "start_fins_preprocess"`
- `FINS_UPLOAD_AWAITING_TOOL_NAME = "start_fins_upload"`
- `FinsIngestionWaitPollAdapter`
- `build_fins_wait_adapter_registry(workspace_root=..., tool_names=...)`
- `FinsIngestionWaitActivationAdapter`
- `build_fins_wait_activation_registry(runtime=..., tool_names=...)`
- `build_fins_wait_poll_adapter_registry(runtime=..., tool_names=...)`

## 调用者装配示例

调用者进入 Fins 的稳定入口是 `DefaultFinsRuntime`。不同入口可以创建各自的 runtime 实例，但同一 `workspace_root` 会使用同一套仓储布局、processor registry 构造逻辑和 legacy job store。
awaiting tool callable 与 wait activation registry 例外：activation adapter 必须接收 awaiting tool callable 使用的同一个 `FinsIngestionRuntime` 实例，因为 prepared observation 是进程内 runtime 状态，不是可由 `workspace_root` 重新发现的持久事实。

### Read caller

Tool discovery 的 read provider 已经内置这条路径：

```text
dayu.fins.tools.provider.discover_tools(spec)
  -> parse_fins_workspace_root_config(spec.config)
  -> DefaultFinsRuntime.create(workspace_root=...)
  -> runtime.get_read_runtime(...)
  -> build_fins_read_tool_definitions(read_runtime=..., workspace_root=...)
```

其它直接调用 read runtime 的入口也应走同一装配根：

```python
from pathlib import Path

from dayu.fins.service_runtime import DefaultFinsRuntime

workspace_root = Path("/abs/path/to/fins-workspace")
runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
read_runtime = runtime.get_read_runtime()

documents = read_runtime.list_documents(ticker="AAPL")
sections = read_runtime.get_document_sections(
    ticker="AAPL",
    document_id="example-document-id",
)
```

调用者不应自行拼装 `FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`FsProcessedDocumentRepository` 或 `ProcessorRegistry`，也不应直接构造 `FinsReadRuntime(...)` 来绕过 shared runtime。

### Download / preprocess / upload caller

Tool discovery 的 download / preprocess / upload providers 已经内置这条路径：

```text
dayu.fins.tools.download_provider.discover_tools(spec)
dayu.fins.tools.preprocess_provider.discover_tools(spec)
dayu.fins.tools.upload_provider.discover_tools(spec)
  -> parse_fins_workspace_root_config(spec.config)
  -> DefaultFinsRuntime.create(workspace_root=...)
  -> runtime.get_ingestion_runtime()
  -> build start_fins_download / start_fins_preprocess / start_fins_upload ToolDefinition
```

其它直接调用 ingestion runtime 的入口也应走同一装配根，并优先消费 direct stream：

```python
import asyncio
from pathlib import Path

from dayu.fins.domain.enums import SourceKind
from dayu.fins.direct_events import FinsEventType
from dayu.fins.ingestion_runtime import (
    FinsDownloadRequest,
    FinsPreprocessRequest,
    FinsUploadFilingRequest,
)
from dayu.fins.service_runtime import DefaultFinsRuntime

workspace_root = Path("/abs/path/to/fins-workspace")
upload_file = Path("/abs/path/to/uploads/aapl-2025-10k.pdf")
runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
ingestion = runtime.get_ingestion_runtime()

async def run_direct_ingestion() -> None:
    async for event in ingestion.download(
        FinsDownloadRequest(
            ticker="AAPL",
            source="auto",
        )
    ):
        if event.event_type is FinsEventType.RESULT:
            break

    async for event in ingestion.preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            rebuild_processed=False,
        )
    ):
        if event.event_type is FinsEventType.RESULT:
            break

    async for event in ingestion.upload(
        FinsUploadFilingRequest(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="auto",
            files=(upload_file,),
            fiscal_year=2025,
            fiscal_period="FY",
            overwrite=False,
        )
    ):
        if event.event_type is FinsEventType.RESULT:
            break


asyncio.run(run_direct_ingestion())
```

Tool awaiting provider 使用同一装配根，但入口是 observation handle：

```text
start_fins_download / start_fins_preprocess / start_fins_upload
  -> FinsIngestionRuntime.prepare_observed_download / prepare_observed_preprocess / prepare_observed_upload
  -> return ToolAwaitingOutcome(EXTERNAL_JOB)
  -> Host accepted wait activation
  -> FinsIngestionRuntime.activate_observation(handle)
  -> FinsIngestionWaitPollAdapter polls observation snapshot
```

Legacy job-store helpers 仍可由低层测试或明确选择 legacy job-store 的内部路径调用：

```python
download_start = ingestion.start_download(
    FinsDownloadRequest(
        ticker="AAPL",
        source="auto",
    )
)
```

`FinsReadRuntime` 只服务 read path；download、preprocess 与 upload 必须使用 `FinsIngestionRuntime`。当前默认 runtime 为 US ticker 的 `source="sec"` / `source="auto"` 装配 SEC production download adapter，为 CN ticker 的 `source="cninfo"` / `source="auto"` 装配巨潮 production download adapter，为 HK ticker 的 `source="hkexnews"` / `source="auto"` 装配披露易 production download adapter；没有匹配 adapter 的 download stream 会进入明确 failed RESULT。preprocess path 读取 workspace 中已有 source docs，并通过 processor registry 写入 processed repository。当前默认 runtime 内置 production upload runner：US ticker 走 SEC upload workflow，CN/HK ticker 走 CN/HK upload facade，并通过 `DoclingUploadService` 写入 source/blob 仓储。直接调用 ingestion runtime 时，调用方必须自行保证 `files` 指向可信本地普通文件；`start_fins_upload` 工具会在工具边界校验本地路径存在、指向普通文件且文件非空。Material 上传使用 `FinsUploadMaterialRequest`，并必须提供 `form_type` 与 `material_name`。

## 公共契约

Fins 公共契约分为 Fins 专属契约、Dayu Agent 公共契约和文档处理器契约。

### Fins 专属契约

- `dayu.fins.domain`：财报领域模型、枚举与共享业务值 parser，包括 `Market`、`SourceKind`、公司元数据、源文档、processed 文档、文件对象、批处理 token、rejected filing artifact、SEC form parser / alias expansion、财期、文档质量与财务数据质量等数据对象和封闭值。
- `dayu.fins.ticker_normalization`：ticker 标准化结果与 market / exchange 推导。
- `dayu.fins.storage.repository_protocols`：公司、源文档、processed、blob、filing maintenance 与批处理事务仓储协议。
- `FinsDownloadRequest` / `FinsPreprocessRequest` / `FinsUploadFilingRequest` / `FinsUploadMaterialRequest`：下载、预处理与上传请求。
- `FinsSourceDownloadAdapter` / `FinsSourceDownloadAdapterRequest` / `FinsSourceDownloadAdapterResult`：下载来源 adapter 协议。
- `FinsUploadRunner` / `FinsJobCancellationChecker` / `FinsUploadResultSummary`：上传 runner 边界、协作式取消检查器与有界结果摘要。
- `FinsEvent` / `FinsProgress` / `FinsResultSummary`：direct stream 的用户可见进度、终态和有界详情契约。
- `FinsObservationHandle` / `FinsObservationSnapshot` / `FinsObservationStatus`：awaiting tools 与 Host wait adapter 之间的 lightweight observation 契约。
- `FinsIngestionJobRecord` / `FinsIngestionJobStatus` / `FinsIngestionOperationKind` / `FinsIngestionJobStart`：legacy ingestion durable job 契约，仍由 runtime foundation 保留，但不是 CLI direct 或 awaiting tool 的公共引用。
- `dayu.fins.ingestion_events`：legacy ingestion job event 的 canonical 公共入口，导出 `FinsIngestionJobEventAppend`、`FinsIngestionJobEventRecord`、`FinsIngestionJobEventType` 与有界 payload 校验 helper。
- `FinsIngestionStartCancelledError`：可选启动取消 token 在 direct / observed / legacy start 边界命中时的 runtime 异常。
- `FinsIngestionJobStore` / `FsFinsIngestionJobStore`：legacy ingestion job record 存储协议与文件系统实现。
- `FinancialDataProcessor` / `FinancialStatementResult` / `XbrlFactsResult`：财务报表与 XBRL 查询能力协议。

### Dayu Agent 公共契约

这些契约定义真源在 `dayu.contracts` 或层中立公共位置；Fins 只消费、生成或适配，不拥有 Host / Engine 治理语义。

- `JsonValue`：工具参数、工具结果、event detail 和有界 summary 的公共 JSON 值类型。
- `ToolDefinition` / `ToolDisplayInfo`：Fins provider 暴露给 runtime discovery 的工具定义。
- `ToolSchema` / `ToolFunctionSchema` / `ToolParametersSchema` / `ToolTruncateSpec`：工具 schema 与截断声明。
- `ToolCallRequest` / `BatchToolExecutionContext`：工具 callable 接收的调用请求与执行上下文。
- `ToolExecutionOutcome` / `ToolAwaitingOutcome`：普通工具结果、失败、取消和长事务等待 outcome。
- `ToolAwaitKind.EXTERNAL_JOB`：Fins download / preprocess / upload awaiting tools 使用的等待类型。
- `ToolsDiscoveryProviderSpec` / `ToolsDiscoveryProviderOutput`：Fins providers 的 runtime discovery contract。

### 文档处理器契约

这些契约定义真源在 `dayu.documents.processors`：

- `DocumentProcessor`：章节、表格、全文、搜索等通用文档读取协议。
- `PageAwareProcessor`：按页读取的可选协议。
- `ProcessorRegistry`：处理器注册、优先级选择与 fallback 创建。
- `DoclingProcessor` / `MarkdownProcessor` / `BSProcessor`：Fins 复用并增强的通用处理器实现。

## 架构

`dayu.fins` 内部按 domain、storage、processors、read runtime、tools、ingestion 与 wait adapter 分工。

```mermaid
flowchart LR
    assembly["Service / runtime discovery"]
    read_provider["financial-read-tools\nprovider"]
    download_provider["financial-download-tools\nprovider"]
    preprocess_provider["financial-preprocess-tools\nprovider"]
    upload_provider["financial-upload-tools\nprovider"]
    runtime["DefaultFinsRuntime\nworkspace-scoped assembly root"]
    storage["dayu.fins.storage\nrepositories"]
    registry["ProcessorRegistry\nFins processors"]
    read_service["FinsReadRuntime\nread runtime"]
    read_tools["9 read ToolDefinitions"]
    ingestion["FinsIngestionRuntime\ndownload / preprocess / upload jobs"]
    job_store["FsFinsIngestionJobStore\n.dayu/fins_ingestion/jobs"]
    wait_adapter["Fins wait adapter\npoll:fins-ingestion"]
    host_tool_runtime["Host ToolRuntime\naccept barrier"]
    host_wait["Host wait-resume"]

    assembly --> read_provider
    assembly --> download_provider
    assembly --> preprocess_provider
    assembly --> upload_provider
    read_provider --> runtime
    download_provider --> runtime
    preprocess_provider --> runtime
    upload_provider --> runtime
    runtime --> storage
    runtime --> registry
    runtime --> read_service
    runtime --> ingestion
    read_service --> storage
    read_service --> registry
    read_service --> read_tools
    ingestion --> storage
    ingestion --> registry
    ingestion --> job_store
    wait_adapter --> ingestion
    read_tools --> host_tool_runtime
    download_provider --> host_tool_runtime
    preprocess_provider --> host_tool_runtime
    upload_provider --> host_tool_runtime
    host_wait --> wait_adapter
```

```text
dayu.fins
├── domain                    # 财报领域模型、枚举、SEC form / 财期 / 质量封闭值 parser
├── downloaders               # source-specific 低层下载器；当前包含 SEC / 巨潮 / 披露易 downloader
├── storage                   # 仓储协议、文件系统仓储、文件对象存储
├── pipelines                 # source-specific ingestion pipeline；当前包含 SEC 与 CN/HK download / upload pipeline
├── processors                # 财报处理器、SEC 表单专项处理器、registry
├── tools                     # read tools、download/preprocess/upload awaiting tools、providers、read runtime
├── ingestion_runtime.py      # download/preprocess/upload direct stream、observation 与 legacy job runtime
├── ingestion / wait_adapter  # Fins observation handle -> Host wait-resume contract
├── service_runtime.py        # DefaultFinsRuntime shared assembly root
└── ticker_normalization.py   # ticker 标准化
```

## 稳定边界

Fins 稳定边界是 workspace-scoped runtime、仓储协议、processor registry、tools provider 输出、direct event contract、lightweight observation contract 和 wait adapter binding。

Fins 不负责：

- Host Session / Run / Attempt / EventLog / admission / dispatch / memory / context governance。
- Engine iteration、RunnerEvent、provider payload、provider retry、length continuation 或 context compaction。
- Service 配置加载、scene manifest 解释、runner profile 选择或 UI 交互。
- ToolRuntime accept barrier、工具权限、side-effect 幂等治理、truncation cursor、`fetch_more`、tool trace 或 audit。
- 把 observation handle、legacy job store、processed 产物、raw provider payload 或工具诊断提升为 Host truth。

Fins workspace 规则固定如下：

- 四个 Fins provider 的 effective spec 都必须提供非空绝对 `workspace_root`；provider 不从 cwd 或环境变量推断。
- 包内默认 `financial-read-tools`、`financial-download-tools`、`financial-preprocess-tools`、`financial-upload-tools` 均为 enabled 且 raw config 不写 `workspace_root`；Service assembly 会用当前运行时 workspace root 注入绝对 `workspace_root`。upload provider 默认注册 `start_fins_upload`，默认非上传 scene 通过窄标签 `fins-read`、`fins-download`、`fins-preprocess` 选择 read/download/preprocess 工具，避免 broad `fins` tag 误选 upload。
- Service assembly 为 Fins awaiting providers 构造 wait adapter registry 时，要求同一 Host assembly 内启用的 Fins download / preprocess / upload provider 使用同一个绝对 `workspace_root`。
- legacy ingestion job store 当前路径为 `<workspace_root>/.dayu/fins_ingestion/jobs`，保存 legacy job governance records 与每个 job 的 event sidecar，不保存财报正文、processed payload、raw download payload 或 upload 本地文件路径。Direct stream 和 lightweight observation handle 不以该目录作为公共观察真源。
- upload provider 不拥有本地源文件 allowlist 或授权配置；它只注册工具并做普通文件、存在性与非空校验。仓储写入边界仍属于 `dayu.fins.storage`，工具 caller 不能指定 source/blob/processed 的仓储写入目录。

## 主要组件

### Storage

Storage 是财报文件系统的唯一访问边界。仓储协议按职责拆分为 company meta、source document、processed document、blob、filing maintenance 与 batching，避免把所有能力塞进单个宽仓储。文件系统实现通过 shared repository set 复用路径、锁和批处理事务语义。

source repository 拥有 source document acknowledgement 与 provenance；blob repository 拥有最终文件写入边界，并在 `SourceHandle` 写入时拒绝未被 source repository 承认的 source。pipeline 可以请求 staging，但不能绕过 `stage_source_document(...)` 自行发明第二份 staging 真源。

### Downloaders 与 CN/HK report selection

CNInfo / HKEXNews downloader 只负责 HTTP 请求响应、provider JSON 解析、provider raw 字段归一、股票代码匹配、PDF URL 归一、HEAD / GET 与 PDF 字节校验。产品级财报候选语义由 `dayu.fins.pipelines.cn_report_selection` 持有：title blocklist、语言过滤、report kind / fiscal period / fiscal year 推断、同 period/year 去重、amended 优先和 `CnReportCandidate` 构造都在 pipeline helper 内完成。

### Processors

Processors 在 `dayu.documents.processors` 通用能力上增加财报语义：

- Fins Docling / Markdown / BS 处理器对表格补充金融语义标注。
- `SecProcessor` 基于 edgartools 读取 SEC 文档章节、表格、XBRL 与 financial statement。
- SEC 表单专项处理器通过虚拟章节 mixin 处理 `10-K`、`10-Q`、`20-F`、`8-K`、`DEF 14A`、`SC 13D/G`、`6-K` 等表单的章节切分、搜索和财务表回退。
- `build_fins_processor_registry()` 在 documents 默认处理器注册表基础上覆盖注册 Fins 增强处理器，并按优先级注册 SEC 表单专项主路径、回退路径和通用 SEC 兜底。

### FinsReadRuntime

`FinsReadRuntime` 是 read path runtime，负责 ticker 标准化、文档选择、document_id 到 source / processor 的路由、processor LRU 缓存、not-supported 降级、列表 / 章节 / 表格 / 页面 / 财务报表 / XBRL 查询结果构造。它不依赖 Host EventLog，也不把 processed 产物作为 read path 的唯一事实来源。

### Tools providers

Read、download、preprocess、upload 是四个独立 provider：

- read provider 只暴露 9 个 read tools。
- download provider 只暴露 `start_fins_download`。
- preprocess provider 只暴露 `start_fins_preprocess`。
- upload provider 只暴露 `start_fins_upload`，并在工具边界校验本地路径存在、指向普通文件且文件非空；本地源文件授权不是 provider-owned config。

四者都要求 effective spec 提供绝对 `workspace_root`，并通过 `DefaultFinsRuntime.create(workspace_root=...)` 获取共享 Fins 底座。

### Ingestion runtime

`FinsIngestionRuntime` 负责 download / preprocess / upload 的业务执行、direct event stream、awaiting observation 和 legacy job-store helper。下载 pipeline 通过 `FinsSourceDownloadAdapter` 返回待持久化文档，或在 adapter 内通过仓储完成 source / blob / rejected filing artifact 写入并返回有界已持久化摘要；预处理 pipeline 从 source repository 读取文档，经 processor registry 生成 sections / tables，再写入 processed repository；upload 通过 `FinsUploadRunner` 边界执行上传业务。runtime 的业务真源是仓储产物与有界 result summary，不是 Host EventLog，也不是 CLI-facing job id。

Preprocess result summary 使用同一个 typed status helper 判定业务成功或失败。`skipped_count` 只表示已支持但因已有 processed 产物等原因跳过的文档；无可用 processor 的文档单独计入 `not_supported_count` 与 `not_supported_document_ids`，不会混入 skipped。

Direct stream 入口 `download(...)` / `preprocess(...)` / `upload(...)` 返回 `AsyncIterator[FinsEvent]`。`PROGRESS` 表示运行中进度，唯一 terminal `RESULT` 携带 `FinsResultSummary`，成功、失败和取消都必须有明确终态；stream 正常结束但 producer 未产出 `RESULT`，或产出重复 `RESULT`，都会抛出 `FinsDirectStreamProtocolError`，不得合成业务 failure result。Download direct stream 的用户可见进度来自 source-specific downloader / pipeline 事件，再由 adapter 按业务对象粒度通过 runtime progress sink 投影为 direct progress；SEC 当前按 filing 输出，CN/HK 当前按报告下载与转换流程输出。CLI / Service 只展示 direct event 给出的 `stage`、`message` 和 `document_label`，不得从 summary、文件名或日志推断下载进度。Download terminal summary 的 `downloaded`、`skipped`、`rejected` 与 `failed` 是同一批候选 filing 的互斥分类；`total` / `discovered` 必须等于这些分类之和，除非后续 schema 显式增加非互斥指标并在 LLM-facing 文本中说明。Direct event 不包含 job id、sequence、cursor、resume token、sidecar path、绝对路径、provider raw payload 或财报正文。

Legacy job helpers 仍保留 `start_*`、`read_job(...)`、`read_job_events(...)` 和 `request_cancel(...)`。每个 legacy ingestion job 可追加 JSONL event sidecar，路径与 job record 同属 `<workspace_root>/.dayu/fins_ingestion/jobs`。该路径是 legacy runtime foundation，不是 Service direct 或 awaiting tool 的公共观察边界。

当前 `DefaultFinsRuntime` 内置三个 production download adapter：`source="sec"` 与 `source="auto"` 且 market 为 `US` 时走 SEC 下载；`source="cninfo"` 与 `source="auto"` 且 market 为 `CN` 时走巨潮下载；`source="hkexnews"` 与 `source="auto"` 且 market 为 `HK` 时走披露易下载。没有匹配 adapter 时，download job 会进入明确的 failed 终态，不伪造成功。

当前 `DefaultFinsRuntime` 内置 production upload runner：US filing/material 上传走 SEC upload workflow，CN/HK filing/material 上传走 CN/HK upload facade，通用文件校验、Docling 转换、source document create/update/delete/skip/overwrite 与 blob 写入由 `DoclingUploadService` 通过仓储协议完成。production upload runner 把 pipeline JSON result 收敛为 Fins-local typed upload result，`status` 必须由 pipeline 显式提供，runtime 不用缺省值伪造上传状态。直接调用 `FinsIngestionRuntime.create(...)` 且不装配 `FinsUploadRunner` 时，upload job 仍会进入明确的 failed 终态，不执行真实上传、文件读取或仓储写入。

### Wait adapter

`FinsIngestionWaitPollAdapter` 把 lightweight observation handle 映射到 Host wait poll 结果：

- `pending` / `running` -> not ready。
- `succeeded` -> completed outcome。
- `failed` -> failed outcome。
- `cancelled` -> cancelled outcome。
- `lost`、corrupt resume token 或当前进程找不到 handle -> lost outcome。
- `TRANSIENT_UNAVAILABLE` 消费 Host wait record 的 `deadline_at` / `expires_at` 边界；边界过期或非法时 lost，没有 Host 边界时保持 not ready。Fins wait adapter 不从 `created_at` 年龄自行制造终态 timeout。

Host 取消 wait 时，adapter 通过 `cancel_observation(handle)` / `abandon_observation(handle)` 做 best-effort 取消和本地 observation record 清理，不删除 Fins source docs、processed docs、legacy job record 或 Host wait record。

## 关键执行路径

### Read 路径

```text
ToolsDiscovery
  -> dayu.fins.tools.provider.discover_tools
  -> parse explicit absolute workspace_root
  -> DefaultFinsRuntime.create(workspace_root=...)
  -> get_read_runtime(...)
  -> build_fins_read_tool_definitions(..., workspace_root=...)
  -> current ToolDefinition bundle with process-backed execution
  -> Host ToolRuntime
  -> process-backed target reconstructs DefaultFinsRuntime from workspace_root
  -> FinsReadRuntime method
  -> storage repositories
  -> ProcessorRegistry.create_with_fallback(...)
  -> processor read / search / table / XBRL capability
  -> tool result accepted by Host ToolRuntime
```

Read path 只读取 Fins workspace 中已经存在的财报材料。九个 read tools 的生产执行形态为 `process_backed`：父进程只把 `workspace_root` 字符串、工具名、参数 JSON 副本、limits 和 timeout 标量放入可序列化 target；子进程通过 `DefaultFinsRuntime.create(workspace_root=Path(...))` 重新打开只读仓储并创建 `FinsReadRuntime`。read tool process target 不跨进程序列化 `FinsReadRuntime`、仓储对象、processor cache、provider lock、Host cancellation token 或 Host 内部对象。需要截断的 read tools 声明 `ToolTruncateSpec`；实际截断、cursor、`fetch_more` 与工具结果 accept 由 Host ToolRuntime 负责。

### Download / preprocess / upload awaiting tool 路径

```text
ToolsDiscovery
  -> dayu.fins.tools.download_provider / preprocess_provider / upload_provider
  -> parse explicit absolute workspace_root
  -> upload provider builds start_fins_upload from Fins ingestion runtime
  -> DefaultFinsRuntime.create(workspace_root=...)
  -> get_ingestion_runtime()
  -> start_fins_download / start_fins_preprocess / start_fins_upload tool call
  -> observe BatchToolExecutionContext.cancellation_token
  -> FinsIngestionRuntime.prepare_observed_download / prepare_observed_preprocess / prepare_observed_upload
  -> checkpoint before observation start
  -> register process-local lightweight observation handle as pending
  -> return ToolAwaitingOutcome(EXTERNAL_JOB)
  -> Host awaiting accept succeeds
  -> FinsIngestionWaitActivationAdapter activates observation
  -> background executor runs pipeline
  -> update observation snapshot with terminal result
  -> FinsIngestionWaitPollAdapter maps observation snapshot to Host wait result
  -> Host resolve / resume governance
```

Download、preprocess 与 upload awaiting tools 会先观察 Host ToolRuntime 传入的 cancellation token；prepare 前已取消时返回 `ToolCancelledOutcome`，不注册 observation handle。工具 callable 只登记 process-local observation 并返回 awaiting outcome，不提交 executor。Host awaiting accept 成功后，activation adapter 解析现有 resume token 并调用 `activate_observation(handle)`；activation 在 observation lock 内幂等检查取消、终态与已提交标志后才提交后台 executor。activation 前取消的 prepared observation 会收口为 `cancelled`，不会启动后台执行。后台 submit 后取消是 best-effort cooperative：runtime 通过 operation-scoped cancellation state / checker 传播取消请求，底层 blocking adapter 只有在检查点或自然返回时才会收口。

工具调用边界内的参数错误、observation prepare 失败或上传本地文件形态校验失败会返回工具失败 outcome；observation handle 注册成功且未取消时工具立即返回 awaiting outcome，不等待后台任务完成。activation submit 失败会把 observation terminal 化为 `failed`，由现有 wait adapter 映射为 Host wait failed，不新增 durable Fins prepared job 状态。

### Upload runtime 路径

```text
direct caller
  -> DefaultFinsRuntime.create(workspace_root=...)
  -> get_ingestion_runtime()
  -> FinsIngestionRuntime.upload(...)
  -> ticker_normalization.normalize_ticker(...)
  -> validate SourceKind filing/material discrimination
  -> direct stream producer delegates to FinsUploadRunner
  -> SEC/CN upload workflow
  -> DoclingUploadService writes through storage repositories
  -> emit PROGRESS events and terminal RESULT
```

当前 upload 同时具备 direct stream runtime contract、production runner、`start_fins_upload` awaiting tool provider 与 Host wait adapter binding。`FinsUploadFilingRequest` 与 `FinsUploadMaterialRequest` 使用已有 `SourceKind.FILING` / `SourceKind.MATERIAL` 区分 filing 与 material；direct result 只暴露有界业务字段和文件数量，不保存或输出本地文件路径。未装配 `FinsUploadRunner` 时，upload stream 产出 unsupported upload runtime 的 failed RESULT。

## 状态机

Fins direct stream 的用户可见终态由 `FinsResultStatus` 表达：

```text
success
failure
cancelled
```

Awaiting observation 状态集合：

```text
pending
running
succeeded
failed
cancelled
lost
```

Legacy ingestion job 状态集合：

```text
queued
running
cancelling
succeeded
failed
cancelled
```

Observation 终态是 `succeeded`、`failed`、`cancelled`、`lost`。`cancel_observation(handle)` 对非终态 observation 设置 operation-scoped cancellation state；`abandon_observation(handle)` 清理 process-local observation record 并 best-effort 请求取消，但不删除业务产物。

Legacy job 终态是 `succeeded`、`failed`、`cancelled`。`request_cancel(job_id)` 对非终态 legacy job 写入取消请求；后台 pipeline 在 claim、循环处理文档、写入终态前反复观察取消请求。已经终态的 legacy job 不会被取消请求改写业务结果。

典型状态流如下：

```text
prepare_observed_download / prepare_observed_preprocess / prepare_observed_upload
  -> pending
      -> activate_observation
      -> running
      -> succeeded
      -> failed
      -> cancelled
      -> lost

legacy start_download / start_preprocess / start_upload
  -> queued
      -> cancelling
  -> running
      -> succeeded
      -> failed
      -> cancelling -> cancelled
```

`FsFinsIngestionJobStore` 使用 workspace 派生路径、文件锁、原子写和有界 JSON record。legacy job id 是 opaque `finsjob_<32 hex>`；调用方不得解析其中语义。Observation handle id 是 opaque `finsobs_<hex>`，只供 wait adapter 在当前进程观察 completion，不承诺跨重启恢复。

## 事件流

Fins 不产出 `EngineEvent stream` 或 `Host event stream`，也不写 Host EventLog。Fins 对 Agent / Service direct 调用方的可观察输出包括：

- read tools 的普通 `ToolExecutionOutcome`。
- download / preprocess / upload direct stream 的 `FinsEvent(PROGRESS | RESULT)`。
- download / preprocess / upload awaiting tools 的 `ToolAwaitingOutcome(EXTERNAL_JOB)`。
- wait adapter poll 时把 Fins observation snapshot 映射成 Host resolve outcome。

Fins direct event、observation snapshot 和 legacy job record 都不是 Host durable truth；只有经 Host wait adapter 和 Host ingest / resolve 路径接受后，才会影响 Host Run / Attempt 状态。Download、preprocess 与 upload awaiting tools 都使用同一个 Fins wait adapter key，由 Service assembly 根据启用的 provider 显式绑定。

## Processors 的类继承关系

Fins processors 以 `dayu.documents.processors` 的协议与通用处理器为基础，但 SEC 专项处理器分成 BS 主路径与 edgartools / SecProcessor 回退路径。

```text
DocumentProcessor Protocol
PageAwareProcessor Protocol
FinancialDataProcessor Protocol

DoclingProcessor
└── FinsDoclingProcessor(FinsProcessorMixin, DoclingProcessor)

MarkdownProcessor
└── FinsMarkdownProcessor(FinsProcessorMixin, MarkdownProcessor)

BSProcessor
└── FinsBSProcessor(FinsProcessorMixin, BSProcessor)
    ├── _BaseBsReportFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor)
    │   ├── BsTenKFormProcessor
    │   ├── BsTenQFormProcessor
    │   └── BsTwentyFFormProcessor
    ├── BsDef14AFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor)
    ├── BsEightKFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor)
    ├── BsSc13FormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor)
    └── BsSixKFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor)

SecProcessor
└── _BaseSecReportFormProcessor(_VirtualSectionProcessorMixin, SecProcessor)
    ├── TenKFormProcessor
    ├── TenQFormProcessor
    ├── TwentyFFormProcessor
    ├── Def14AFormProcessor
    ├── EightKFormProcessor
    └── Sc13FormProcessor
```

继承语义固定如下：

- `FinsProcessorMixin` 只补充财报表格语义字段，不负责文档加载、章节切分或仓储。
- `FinsDoclingProcessor`、`FinsMarkdownProcessor`、`FinsBSProcessor` 复用通用处理器解析能力，并在初始化后对表格执行金融语义重标注。
- `SecProcessor` 是独立 SEC 文档处理器，结构上对齐 `DocumentProcessor` 与 `FinancialDataProcessor` 能力，但不继承 `FinsDoclingProcessor`。
- `_VirtualSectionProcessorMixin` 必须放在 MRO 的基础处理器之前，例如 `(_VirtualSectionProcessorMixin, SecProcessor)` 或 `(_VirtualSectionProcessorMixin, FinsBSProcessor)`，以便 mixin 的 `super()` 下一跳具备标准 section / table / search 接口。
- `_BaseBsReportFormProcessor` 是 10-K / 10-Q / 20-F 的 BeautifulSoup 主路径；`_BaseSecReportFormProcessor` 是 edgartools / SecProcessor 回退路径。
- `BsDef14AFormProcessor`、`BsEightKFormProcessor`、`BsSc13FormProcessor`、`BsSixKFormProcessor` 直接组合虚拟章节 mixin 与 `FinsBSProcessor`，不经过 `_BaseBsReportFormProcessor`。

`build_fins_processor_registry()` 当前注册优先级为：

- SEC 表单专项 BS 主路径：priority `200`。
- SEC 表单专项 edgartools 回退路径：priority `190`。
- 通用 `SecProcessor`：priority `120`。
- Fins Docling / Markdown：priority `100`。
- Fins BS：priority `80`。

## 关键机制

### Shared Fins runtime

`DefaultFinsRuntime` 是 read、download、preprocess / process 与 upload foundation 的 shared assembly root。它统一装配同一 workspace 下的文件系统仓储、processor registry、`FinsReadRuntime`、`FinsIngestionRuntime` 和 legacy ingestion job store。

这个机制用于保证多入口调用时 Fins 业务逻辑不漂移：工具 provider、测试 / CI 夹具或其它入口应调用 shared Fins runtime 的 typed API，而不是复制 ticker 归一、仓储路径、processor 选择、download、preprocess / process、upload、direct event 或 observation 逻辑。当前共享语义通常不是“所有入口必须共享同一个 Python 对象实例”，而是“同一 `workspace_root` 下走同一套业务代码、仓储布局和 runtime 装配”；但 awaiting observation 的 tool callable 与 activation adapter 必须共享同一个 `FinsIngestionRuntime` 实例，避免 activation 看不到 callable 准备的 process-local observation。

### Workspace root 与 provider fail fast

四个 Fins provider 都要求 effective spec 中存在绝对 `workspace_root`。read provider 启用时始终解析 workspace 并注册九个 read tools；upload provider 启用时始终注册 `start_fins_upload`，本地文件只在工具调用时校验存在、普通文件与非空，本地源文件授权由调用方在 provider 外部承担。其它启用路径缺少、空字符串或相对路径都会 fail fast。Service assembly 对 Fins awaiting providers 还会校验 download / preprocess / upload 使用同一个绝对 workspace root，避免一个 Host assembly 把 wait adapter 绑定到不同 Fins workspace。

### Storage repository boundary

财报文档存取必须通过 `dayu.fins.storage` 仓储协议完成。Read runtime、download pipeline、preprocess pipeline 都不能绕过仓储协议直接读写业务文件树。blob 文件、source meta、processed meta、rejected filing artifact 和 batching 事务分别由窄协议承担。

### Processor registry 与 processor cache

`build_fins_processor_registry()` 在 documents 默认处理器注册表基础上注册 Fins 业务增强处理器。`FinsReadRuntime` 按 ticker / document_id / source kind 路由到 source repository 和 processor registry，并缓存 processor 实例；缓存只保存 processor，不把 Host tool result、EventLog fact 或 LLM-facing material 缓存在 Fins 内部。

### Read tool 结果与截断

Read tools 的 schema、错误和结果字段必须面向 LLM 自解释。工具可以声明 `ToolTruncateSpec`，但截断执行、cursor 生命周期和 `fetch_more` 都由 Host ToolRuntime 处理。Fins read 工具的 direct callable 只作为测试和非生产 fallback；生产默认执行由 ToolRuntime 根据 `ToolDefinition.execution` 进入 process-backed 边界。Fins process target 使用 `dayu.contracts` 的 process-backed envelope helper 构造 completed / failed 信封；failed 信封的 `hint` 是结构化字段，由 Host 映射为 `ToolResultFailure.hint`，不得拼接进 `message`。Fins 工具不得自行模拟 Host truncation manager，也不得把内部 ref / digest 当成业务事实返回给模型。

### Download adapter 与 unsupported source

`FinsIngestionRuntime` 通过 `(source, market)` 选择 `FinsSourceDownloadAdapter`。当前默认 runtime 注册 `(sec, US)` / `(auto, US)` 到同一个 SEC production adapter，注册 `(cninfo, CN)` / `(auto, CN)` 到同一个巨潮 production adapter，注册 `(hkexnews, HK)` / `(auto, HK)` 到同一个披露易 production adapter；没有匹配 adapter 时，download job 写入明确 failed 终态和 unsupported-source 摘要。下载成功路径只通过 source repository、blob repository 和 filing maintenance repository 写入 source docs 与 rejected filing artifacts。

### Preprocess / process pipeline

`start_preprocess` 从 source repository 选择已存在源文档，按 `document_ids`、`form_types`、`source_kind` 和 `rebuild_processed` 控制处理范围。后台 pipeline 使用 processor registry 生成 sections / tables，并通过 processed repository create / update 写入 processed 产物。`rebuild_processed=false` 时跳过已有 processed 文档；`rebuild_processed=true` 时允许重建。

### Direct stream / observation / legacy job 与取消

Direct stream 不创建 durable job record；调用方关闭 async iterator、取消 task 或传入 cancellation token 时，runtime 通过 operation-scoped cancellation state / checker 做合作式取消。Awaiting tools 不等待长事务完成，只 prepare 并注册 process-local observation handle，返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`；Host awaiting accept ack durable 成立后，ToolRuntime 通过 Fins activation adapter 调用 `activate_observation(handle)` 提交后台执行。Host wait cancel 通过 wait adapter 调用 `cancel_observation(handle)` / `abandon_observation(handle)`。Legacy `start_*` job helpers 仍可创建 durable `queued` job record 并通过 `request_cancel(job_id)` 合作式取消，但 Service direct 和 awaiting tools 不消费该路径。

Runtime producer 在进入 download / preprocess / upload 业务执行前检查取消，避免已取消 observation 再启动后续长事务。SEC 下载在公司解析、submissions / history 拉取、filing 选择、Browse EDGAR 补选、index / headers / candidate 文件收集、单 filing 文件列表、HTTP 限流 / 退避、HEAD / GET、文件循环和落盘前后检查取消；取消命中后停止后续 SEC 请求和文件处理，不把用户取消记为 failed file / failed filing。CN/HK 下载在 discovery、候选选择、overwrite 清理、单 filing asset 下载、PDF bytes 读取、PDF / Docling blob 写入、staging source 写入、Docling convert 前后和最终 source commit 前检查取消；取消命中后产出 cancelled summary，已经完成的原子落盘保持一致，不再启动后续耗时步骤。

CN/HK Docling convert 当前通过 `asyncio.to_thread(...)` 调用同步第三方转换函数。转换线程运行期间不能观察 operation cancellation checker；当前可保证的是进入 convert 前、convert 返回后、写入 Docling blob 前后的合作式 checkpoint。需要在转换过程本身做到强中断时，应把 convert 隔离到 process-backed / subprocess 边界并配置 timeout，由父进程治理 terminate / kill；线程内同步第三方调用不能伪装成可强制取消。

### Wait adapter 与 Host resume

Fins awaiting tools 不直接恢复 Host Run。Service assembly 根据启用的 Fins awaiting provider 显式构造 wait adapter registry、wait activation registry 与 wait poll adapter registry，并确保 awaiting tool callable、activation adapter 与 poll adapter 使用同一个 workspace-scoped ingestion runtime。Host poller 通过 `FinsIngestionWaitPollAdapter` 读取 process-local observation snapshot，再由 Host 自己执行 resolve / resume / failed / lost 治理。Fins wait adapter 不改变 Host wait record，不写 Host EventLog，也不恢复旧 Engine 生成器；等待 deadline / expiry 的 durable truth 属于 Host wait record，adapter 只按 Host 边界消费。

### Ticker normalization

Fins read 与 ingestion 都通过 `ticker_normalization.normalize_ticker(...)` 收口 ticker 输入，生成 canonical ticker、market 和 exchange。工具 schema 允许模型传自然 ticker 写法；业务路由以 canonical ticker 为准。

## 扩展点

扩展 read tool 时，先在 storage protocol、processor 或 `FinsReadRuntime` 中建立稳定业务语义，再通过 `build_fins_read_tool_definitions(..., workspace_root=...)` 暴露工具 schema 与 process-backed execution 声明。process target / factory 只能保存可序列化 locator、工具名、参数 JSON 副本、limits 或必要标量；不要把仓储装配、Host 状态、ToolRuntime 治理、runtime 实例、repository、processor cache 或 provider lock 写进工具函数。

扩展财报存储后端时，实现 `dayu.fins.storage` 的窄仓储协议，并保持 source / processed / blob / filing maintenance / batching 职责分离。调用方仍通过 `DefaultFinsRuntime` 或等价 assembly root 注入仓储实现。

扩展 processor 时，实现 `DocumentProcessor` 所需能力或明确的财报能力协议，并在 `build_fins_processor_registry()` 中以可解释优先级注册。表单专项处理器应保持 BS 主路径与 SecProcessor 回退路径的职责边界。

扩展下载来源时，实现 `FinsSourceDownloadAdapter`，并通过 `FinsIngestionRuntime.create(download_adapters=...)` 注入 `(source, market)` adapter 映射。Adapter 可以返回 typed downloaded documents / rejected artifacts 交给 runtime 持久化；若迁移的 source workflow 已在 adapter 内通过仓储完成持久化，则必须返回有界 persisted summary，且不得再同时返回 documents / rejected artifacts。需要用户可见下载进度时，adapter 必须消费来源 pipeline 的真实事件，并通过 request 中的 progress sink 上报 `FinsDownloadProgressEvent`；上层 UI 不承担事件推断职责。

扩展 preprocess / process 时，保持 source repository -> processor registry -> processed repository 的闭环；不要在 CLI、tools、CI 或测试夹具中复制独立处理逻辑。

扩展 wait-resume 时，保持 Fins observation handle 与 Host wait record 分离。新增等待工具需要显式工具名、await kind、adapter key、resume policy 和 external job ref source，不得把 adapter object 塞进 ToolsDiscovery provider output。只有明确需要跨进程或跨重启恢复未完成 ingestion 时，才应单独设计最小 durable operation ledger；不得用 CLI direct 或“以后可能”作为 durable 需求。
