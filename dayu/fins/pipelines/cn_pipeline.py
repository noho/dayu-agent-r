"""CN/HK 下载/上传管线与 NEW Fins runtime adapter。

本模块承载 OLD CN/HK pipeline 的下载面与 Slice 4 迁移的 production
upload facade：download、download_stream、上传 filing/material、下载候选过滤、
PDF gate、Docling JSON 转换、skip/overwrite 与本地 rebuild。process、CLI、
Host、tool/provider 装配不在本 Slice 内。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from pathlib import Path
from typing import Final, Optional, TypeAlias, cast

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.downloaders.cninfo_downloader import (
    DEFAULT_MAX_RETRIES as CNINFO_DEFAULT_MAX_RETRIES,
    DEFAULT_SLEEP_SECONDS as CNINFO_DEFAULT_SLEEP_SECONDS,
    DEFAULT_USER_AGENT as CNINFO_DEFAULT_USER_AGENT,
    CninfoDiscoveryClient,
)
from dayu.fins.downloaders.hkexnews_downloader import (
    DEFAULT_MAX_RETRIES as HKEXNEWS_DEFAULT_MAX_RETRIES,
    DEFAULT_SLEEP_SECONDS as HKEXNEWS_DEFAULT_SLEEP_SECONDS,
    DEFAULT_USER_AGENT as HKEXNEWS_DEFAULT_USER_AGENT,
    HkexnewsDiscoveryClient,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadDocumentResult,
    FinsDownloadEffectiveFilters,
    FinsDownloadResultSummary,
    FinsDownloadSource,
)
from dayu.fins.ingestion_runtime import (
    FinsDownloadProgressEvent,
    FinsDownloadProgressSink,
    FinsSourceDownloadAdapter,
    FinsSourceDownloadAdapterRequest,
    FinsSourceDownloadAdapterResult,
    ValidatedFinsUploadFilingRequest,
    validate_fins_upload_filing_request,
)
from dayu.fins.domain.document_models import FinsIngestMethod
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import CN_FISCAL_PERIOD_ORDER, CnMarketKind
from dayu.fins.pipelines.cn_download_pdf_gate import (
    CnDownloadPdfGateProtocol,
    NoopCnDownloadPdfGate,
)
from dayu.fins.pipelines.cn_download_protocols import (
    CnReportDiscoveryClientProtocol,
)
from dayu.fins.pipelines.cn_download_workflow import run_cn_download_stream_impl
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    UploadOperationResult,
    build_material_ids,
    commit_prepared_upload_batch,
    derive_report_kind,
    resolve_upload_action,
    rollback_prepared_upload_batch,
    validate_material_upload_ids,
)
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConverter,
    ProcessDoclingConverter,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.upload_company_meta import (
    build_upload_company_id,
    stage_company_meta_for_upload,
    stage_upload_company_meta_decision,
)
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent, UploadFilingEventType
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent, UploadMaterialEventType
from dayu.fins.pipelines.upload_progress_helpers import (
    map_upload_file_event_to_filing_event_type as _map_upload_file_event_to_filing_event_type,
    map_upload_file_event_to_material_event_type as _map_upload_file_event_to_material_event_type,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    FilingUploadStateRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsFilingUploadStateRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import normalize_ticker, try_normalize_ticker
from dayu.fins.upload_failure import (
    FinsUploadFailureError,
    FinsUploadFailureReason,
    fins_upload_failure_from_exception,
)

CN_DOWNLOAD_SOURCE: Final[str] = "cninfo"
HK_DOWNLOAD_SOURCE: Final[str] = "hkexnews"
CN_PIPELINE_NAME: Final[str] = "cn"
HK_PIPELINE_NAME: Final[str] = "hk"
_CN_FORMS_ADAPTER_JOINER: Final[str] = ","
_CN_STATUS_DOWNLOADED: Final[str] = "downloaded"
_CN_STATUS_SKIPPED: Final[str] = "skipped"
_CN_STATUS_FAILED: Final[str] = "failed"
_CN_TERMINAL_OK: Final[str] = "ok"
_CN_TERMINAL_CANCELLED: Final[str] = "cancelled"
_ADAPTER_PROGRESS_FILE_STARTED: Final[str] = "download.file_started"
_ADAPTER_PROGRESS_FILE_COMPLETED: Final[str] = "download.file_completed"
_ADAPTER_PROGRESS_FILE_SKIPPED: Final[str] = "download.file_skipped"
_ADAPTER_PROGRESS_FILE_FAILED: Final[str] = "download.file_failed"
_ADAPTER_PROGRESS_CONVERSION_STARTED: Final[str] = "download.conversion_started"
_ADAPTER_PROGRESS_CONVERSION_COMPLETED: Final[str] = "download.conversion_completed"
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


CnPipelineDownloadResult: TypeAlias = dict[str, JsonValue]
"""CN/HK pipeline 下载聚合结果结构。"""

CnPipelineUploadResult: TypeAlias = dict[str, JsonValue]
"""CN/HK pipeline 上传聚合结果结构。"""


def _run_async_download_sync(
    coro: Coroutine[None, None, CnPipelineDownloadResult],
) -> CnPipelineDownloadResult:
    """在同步上下文执行 CN/HK 下载协程。

    Args:
        coro: 下载协程。

    Returns:
        CN/HK 下载聚合结果。

    Raises:
        RuntimeError: 当前线程已有事件循环时抛出。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("检测到正在运行的事件循环，请改用 stream 异步接口")


def _run_async_upload_sync(
    coro: Coroutine[None, None, CnPipelineUploadResult],
) -> CnPipelineUploadResult:
    """在同步上下文执行 CN/HK 上传协程。

    Args:
        coro: 上传协程。

    Returns:
        CN/HK 上传聚合结果。

    Raises:
        RuntimeError: 当前线程已有事件循环时抛出。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("检测到正在运行的事件循环，请改用 stream 异步接口")


async def collect_cn_download_result_from_events(
    events: AsyncIterator[DownloadEvent],
    *,
    progress_sink: FinsDownloadProgressSink | None = None,
) -> CnPipelineDownloadResult:
    """从 CN/HK 下载事件流收集最终结果。

    Args:
        events: CN/HK 下载事件流。
        progress_sink: 可选 runtime 进度回调。

    Returns:
        ``PIPELINE_COMPLETED`` 事件携带的结果字典。

    Raises:
        RuntimeError: 事件流未产生完成事件，或完成事件缺少结果时抛出。
    """

    async for event in events:
        _emit_adapter_download_progress(event, progress_sink)
        if event.event_type == DownloadEventType.PIPELINE_COMPLETED:
            result = event.payload.get("result")
            if isinstance(result, Mapping):
                return cast(CnPipelineDownloadResult, dict(result))
            raise RuntimeError("CN/HK 下载完成事件缺少结果 payload")
    raise RuntimeError("CN/HK 下载事件流未产生完成事件")


def _emit_adapter_download_progress(
    event: DownloadEvent,
    progress_sink: FinsDownloadProgressSink | None,
) -> None:
    """把 CN/HK pipeline 文件事件投影为 runtime 下载进度。

    Args:
        event: CN/HK pipeline 下载事件。
        progress_sink: runtime adapter 进度回调。

    Returns:
        无。

    Raises:
        ValueError: 回调拒绝非法进度字段时抛出。
    """

    if progress_sink is None:
        return
    if event.event_type == DownloadEventType.FILE_DOWNLOAD_STARTED:
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_FILE_STARTED,
                message="开始下载",
                document_id=event.document_id,
                file_name=_payload_text(event.payload, "name"),
            )
        )
        return
    if event.event_type == DownloadEventType.CONVERSION_STARTED:
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_CONVERSION_STARTED,
                message="开始转换文档",
                document_id=event.document_id,
                file_name=_payload_text(event.payload, "name"),
            )
        )
        return
    if event.event_type == DownloadEventType.CONVERSION_COMPLETED:
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_CONVERSION_COMPLETED,
                message="完成转换文档",
                document_id=event.document_id,
                file_name=_payload_text(event.payload, "name"),
            )
        )
        return
    if event.event_type == DownloadEventType.FILE_DOWNLOADED:
        status = _payload_text(event.payload, "status")
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_FILE_SKIPPED if status == "skipped" else _ADAPTER_PROGRESS_FILE_COMPLETED,
                message="跳过下载" if status == "skipped" else "完成下载",
                document_id=event.document_id,
                file_name=_payload_text(event.payload, "name"),
            )
        )
        return
    if event.event_type == DownloadEventType.FILE_FAILED:
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_FILE_FAILED,
                message="下载失败",
                document_id=event.document_id,
                file_name=_payload_text(event.payload, "name"),
            )
        )


def _payload_text(payload: Mapping[str, JsonValue], key: str) -> str | None:
    """从 pipeline event payload 读取短文本。

    Args:
        payload: pipeline event payload。
        key: 字段名。

    Returns:
        非空文本或 ``None``。

    Raises:
        无。
    """

    value = payload.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


async def collect_cn_upload_result_from_events(
    events: AsyncIterator[UploadFilingEvent | UploadMaterialEvent],
    *,
    stream_name: str,
) -> CnPipelineUploadResult:
    """从 CN/HK 上传事件流收集最终结果。

    Args:
        events: CN/HK 上传事件流。
        stream_name: 事件流名称。

    Returns:
        完成或失败事件携带的 result 字典。

    Raises:
        RuntimeError: 事件流未产生完成/失败结果时抛出。
    """

    async for event in events:
        if event.event_type.value not in {"upload_completed", "upload_failed"}:
            continue
        result = event.payload.get("result")
        if isinstance(result, Mapping):
            return dict(result)
    raise RuntimeError(f"{stream_name} 未返回最终结果")


class CnPipeline:
    """CN/HK 下载管线 facade。

    该类承载 OLD CN/HK 下载工作流需要的最小宿主边界，并通过 NEW storage
    repositories 写入公司元数据、source 文件与 processed reprocess 标记。
    """

    MODULE: Final[str] = "FINS.CN_PIPELINE"

    def __init__(
        self,
        *,
        workspace_root: Optional[Path] = None,
        cn_discovery_client: CnReportDiscoveryClientProtocol | None = None,
        hk_discovery_client: CnReportDiscoveryClientProtocol | None = None,
        pdf_download_gate: CnDownloadPdfGateProtocol | None = None,
        docling_converter: DoclingConverter | None = None,
        batching_repository: BatchingRepositoryProtocol | None = None,
        company_repository: CompanyMetaRepositoryProtocol | None = None,
        source_repository: SourceDocumentRepositoryProtocol | None = None,
        processed_repository: ProcessedDocumentRepositoryProtocol | None = None,
        blob_repository: DocumentBlobRepositoryProtocol | None = None,
        filing_maintenance_repository: FilingMaintenanceRepositoryProtocol | None = None,
        filing_upload_state_repository: FilingUploadStateRepositoryProtocol | None = None,
        user_agent: Optional[str] = None,
        sleep_seconds: float = CNINFO_DEFAULT_SLEEP_SECONDS,
        max_retries: int = CNINFO_DEFAULT_MAX_RETRIES,
    ) -> None:
        """初始化 CN/HK 下载管线。

        Args:
            workspace_root: Fins 工作区根目录。
            cn_discovery_client: 可选巨潮 discovery client。
            hk_discovery_client: 可选披露易 discovery client。
            pdf_download_gate: 可选 PDF 下载段 gate。
            docling_converter: 可选共享 Docling converter；未提供时构造 production 实现。
            batching_repository: 可选 batch lifecycle 仓储。
            company_repository: 可选公司元数据仓储。
            source_repository: 可选源文档仓储。
            processed_repository: 可选 processed 文档仓储。
            blob_repository: 可选文件对象仓储。
            filing_maintenance_repository: 可选 filing 维护仓储。
            filing_upload_state_repository: 可选 filing 上传 published-state 只读仓储。
            user_agent: CN/HK HTTP User-Agent；为空时各 downloader 使用显式默认值。
            sleep_seconds: 连续 HTTP 请求间隔秒数。
            max_retries: 单次 HTTP 请求最大重试次数。

        Returns:
            无。

        Raises:
            OSError: 默认文件系统仓储初始化失败时抛出。
        """

        self._workspace_root = (workspace_root or Path.cwd()).resolve()
        repository_set = build_fs_repository_set(
            workspace_root=self._workspace_root,
            create_directories=False,
        )
        self._batching_repository = batching_repository or FsBatchingRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._company_repository = company_repository or FsCompanyMetaRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._source_repository = source_repository or FsSourceDocumentRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._processed_repository = processed_repository or FsProcessedDocumentRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._blob_repository = blob_repository or FsDocumentBlobRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._filing_maintenance_repository = filing_maintenance_repository or FsFilingMaintenanceRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._filing_upload_state_repository = filing_upload_state_repository or FsFilingUploadStateRepository(
            self._workspace_root,
            repository_set=repository_set,
        )
        self._user_agent = user_agent
        self._sleep_seconds = sleep_seconds
        self._max_retries = max_retries
        self._cn_discovery_client = cn_discovery_client or CninfoDiscoveryClient(
            user_agent=user_agent or CNINFO_DEFAULT_USER_AGENT,
            sleep_seconds=sleep_seconds,
            max_retries=max_retries,
        )
        self._hk_discovery_client = hk_discovery_client or HkexnewsDiscoveryClient(
            user_agent=user_agent or HKEXNEWS_DEFAULT_USER_AGENT,
            sleep_seconds=sleep_seconds,
            max_retries=max_retries,
        )
        self._pdf_download_gate = pdf_download_gate or NoopCnDownloadPdfGate()
        self._docling_converter = docling_converter or ProcessDoclingConverter()
        self._upload_service = DoclingUploadService(
            source_repository=self._source_repository,
            blob_repository=self._blob_repository,
            docling_converter=self._docling_converter,
        )

    @property
    def batching_repository(self) -> BatchingRepositoryProtocol:
        """返回 batch lifecycle 唯一仓储。

        Args:
            无。

        Returns:
            与各业务仓储共享同一 core 的 batching 仓储。

        Raises:
            无。
        """

        return self._batching_repository

    @property
    def company_meta_repository(self) -> CompanyMetaRepositoryProtocol:
        """返回公司元数据仓储。

        Args:
            无。

        Returns:
            公司元数据仓储协议实现。

        Raises:
            无。
        """

        return self._company_repository

    @property
    def source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回源文档仓储。

        Args:
            无。

        Returns:
            源文档仓储协议实现。

        Raises:
            无。
        """

        return self._source_repository

    @property
    def blob_repository(self) -> DocumentBlobRepositoryProtocol:
        """返回文件对象仓储。

        Args:
            无。

        Returns:
            文件对象仓储协议实现。

        Raises:
            无。
        """

        return self._blob_repository

    @property
    def processed_repository(self) -> ProcessedDocumentRepositoryProtocol:
        """返回 processed 仓储。

        Args:
            无。

        Returns:
            processed 文档仓储协议实现。

        Raises:
            无。
        """

        return self._processed_repository

    @property
    def filing_maintenance_repository(self) -> FilingMaintenanceRepositoryProtocol:
        """返回 filing 维护仓储。

        Args:
            无。

        Returns:
            filing 维护仓储协议实现。

        Raises:
            无。
        """

        return self._filing_maintenance_repository

    @property
    def cn_discovery_client(self) -> CnReportDiscoveryClientProtocol:
        """返回巨潮 discovery client。

        Args:
            无。

        Returns:
            巨潮 discovery client 协议实现。

        Raises:
            无。
        """

        return self._cn_discovery_client

    @property
    def hk_discovery_client(self) -> CnReportDiscoveryClientProtocol:
        """返回披露易 discovery client。

        Args:
            无。

        Returns:
            披露易 discovery client 协议实现。

        Raises:
            无。
        """

        return self._hk_discovery_client

    @property
    def pdf_download_gate(self) -> CnDownloadPdfGateProtocol:
        """返回 PDF 下载段 gate。

        Args:
            无。

        Returns:
            PDF 下载段 gate。

        Raises:
            无。
        """

        return self._pdf_download_gate

    @property
    def docling_conversion_runner(self) -> DoclingConverter:
        """返回共享 Docling converter。

        Args:
            无。

        Returns:
            typed converter。

        Raises:
            无。
        """

        return self._docling_converter

    @property
    def user_agent(self) -> Optional[str]:
        """返回配置的 HTTP User-Agent。

        Args:
            无。

        Returns:
            User-Agent 字符串；未显式配置时返回 ``None``。

        Raises:
            无。
        """

        return self._user_agent

    @property
    def sleep_seconds(self) -> float:
        """返回连续 HTTP 请求间隔秒数。

        Args:
            无。

        Returns:
            请求间隔秒数。

        Raises:
            无。
        """

        return self._sleep_seconds

    @property
    def max_retries(self) -> int:
        """返回单次 HTTP 请求最大重试次数。

        Args:
            无。

        Returns:
            最大重试次数。

        Raises:
            无。
        """

        return self._max_retries

    def download(
        self,
        ticker: str,
        form_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: Optional[list[str]] = None,
        *,
        start_is_explicit: bool,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> CnPipelineDownloadResult:
        """执行 CN/HK 下载并同步返回聚合结果。

        Args:
            ticker: 股票代码。
            form_type: 可选文档类型过滤。
            start_date: 可选开始日期。
            end_date: 可选结束日期。
            overwrite: 是否强制覆盖。
            rebuild: 是否仅基于本地已下载数据重建 meta。
            ticker_aliases: 可选 ticker alias。
            start_is_explicit: 起始日期是否来自调用方显式输入。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            OLD CN/HK 下载结果字典。

        Raises:
            RuntimeError: 当前线程已有事件循环时抛出。
            ValueError: ticker 或过滤参数非法时抛出。
        """

        return _run_async_download_sync(
            collect_cn_download_result_from_events(
                self.download_stream(
                    ticker=ticker,
                    form_type=form_type,
                    start_date=start_date,
                    end_date=end_date,
                    overwrite=overwrite,
                    rebuild=rebuild,
                    ticker_aliases=ticker_aliases,
                    start_is_explicit=start_is_explicit,
                    cancel_checker=cancel_checker,
                )
            )
        )

    async def download_stream(
        self,
        ticker: str,
        form_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: Optional[list[str]] = None,
        *,
        start_is_explicit: bool,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncIterator[DownloadEvent]:
        """执行 CN/HK 下载并流式产出事件。

        Args:
            ticker: 股票代码。
            form_type: 可选文档类型过滤。
            start_date: 可选开始日期。
            end_date: 可选结束日期。
            overwrite: 是否强制覆盖。
            rebuild: 是否仅基于本地已下载数据重建 meta。
            ticker_aliases: 可选 ticker alias。
            start_is_explicit: 起始日期是否来自调用方显式输入。
            cancel_checker: 可选协作式取消检查器。

        Yields:
            下载事件。

        Raises:
            ValueError: ticker 或过滤参数非法时抛出。
        """

        pipeline_name = _pipeline_name_for_ticker(ticker)
        async for event in run_cn_download_stream_impl(
            self,
            ticker=ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            rebuild=rebuild,
            ticker_aliases=ticker_aliases,
            start_is_explicit=start_is_explicit,
            cancel_checker=cancel_checker,
            module=self.MODULE,
            pipeline_name=pipeline_name,
        ):
            yield event

    def upload_filing(
        self,
        request: ValidatedFinsUploadFilingRequest,
        *,
        cancellation_checker: CancellationToken | None = None,
    ) -> CnPipelineUploadResult:
        """执行 CN/HK 财报上传并同步返回聚合结果。

        Args:
            request: 已完成 preflight 的 typed filing 请求。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            上传结果字典。

        Raises:
            RuntimeError: 当前线程存在运行中的事件循环时抛出。
        """

        return _run_async_upload_sync(
            collect_cn_upload_result_from_events(
                self.upload_filing_stream(
                    request,
                    cancellation_checker=cancellation_checker,
                ),
                stream_name="upload_filing_stream",
            )
        )

    async def upload_filing_stream(
        self,
        request: ValidatedFinsUploadFilingRequest,
        *,
        cancellation_checker: CancellationToken | None = None,
    ) -> AsyncIterator[UploadFilingEvent]:
        """执行流式 CN/HK 财报上传。

        Args:
            request: 已完成 preflight 的 typed filing 请求。
            cancellation_checker: 可选协作式取消检查器。

        Yields:
            上传过程事件流。

        Raises:
            RuntimeError: 上传执行失败时抛出。
        """

        raw_request = request.request
        fresh_state = self._filing_upload_state_repository.read_filing_upload_state(
            request.normalized_ticker.canonical,
            request.document_id,
        )
        authoritative_request = validate_fins_upload_filing_request(
            raw_request,
            published_state=fresh_state,
        )
        _assert_authoritative_filing_identity(request, authoritative_request)
        if raw_request.fiscal_year is None:
            raise AssertionError("validated filing request 缺少 fiscal_year")
        normalized_ticker = authoritative_request.normalized_ticker.canonical
        normalized_company_id = build_upload_company_id(normalized_ticker)
        normalized_period = authoritative_request.normalized_fiscal_period
        form_type = normalized_period
        requested_action = raw_request.action.strip().lower()
        document_id = authoritative_request.document_id
        internal_document_id = authoritative_request.internal_document_id
        previous_meta = authoritative_request.published_state.source_meta
        resolved_action = authoritative_request.resolved_action
        yield UploadFilingEvent(
            event_type=UploadFilingEventType.UPLOAD_STARTED,
            ticker=normalized_ticker,
            document_id=document_id,
            payload={
                "action": resolved_action,
                "requested_action": requested_action,
                "resolved_action": resolved_action,
                "fiscal_year": raw_request.fiscal_year,
                "fiscal_period": normalized_period,
                "amended": raw_request.amended,
                "filing_date": raw_request.filing_date,
                "report_date": raw_request.report_date,
                "company_id": normalized_company_id,
                "company_name": raw_request.company_name,
                "ticker_aliases": _json_text_list(list(raw_request.ticker_aliases)),
                "overwrite": raw_request.overwrite,
                "file_count": len(raw_request.files),
            },
        )
        try:
            prepared_upload = await self._upload_service.prepare_upload(
                ticker=normalized_ticker,
                source_kind=SourceKind.FILING,
                action=resolved_action,
                document_id=document_id,
                internal_document_id=internal_document_id,
                form_type=form_type,
                files=list(raw_request.files),
                overwrite=raw_request.overwrite,
                previous_meta=previous_meta,
                cancellation=cancellation_checker,
                meta={
                    "company_id": normalized_company_id,
                    "ingest_method": FinsIngestMethod.UPLOAD.to_storage_value(),
                    "fiscal_year": raw_request.fiscal_year,
                    "fiscal_period": normalized_period,
                    "report_kind": derive_report_kind(normalized_period),
                    "filing_date": raw_request.filing_date,
                    "report_date": raw_request.report_date,
                    "amended": raw_request.amended,
                },
            )
            if isinstance(prepared_upload, UploadOperationResult):
                upload_result = prepared_upload
            else:
                publication_batch = self._batching_repository.begin_batch(normalized_ticker)
                try:
                    stage_upload_company_meta_decision(
                        repository=self._company_repository,
                        decision=authoritative_request.company_meta_decision,
                        batch=publication_batch,
                    )
                except BaseException as operation_error:
                    rollback_prepared_upload_batch(
                        batching_repository=self._batching_repository,
                        batch=publication_batch,
                        operation_error=operation_error,
                    )
                    raise
                upload_result = commit_prepared_upload_batch(
                    service=self._upload_service,
                    batching_repository=self._batching_repository,
                    batch=publication_batch,
                    prepared=prepared_upload,
                    cancellation=cancellation_checker,
                )
            for file_event in upload_result.file_events:
                yield UploadFilingEvent(
                    event_type=_map_upload_file_event_to_filing_event_type(file_event),
                    ticker=normalized_ticker,
                    document_id=document_id,
                    payload={"name": file_event.name, **file_event.payload},
                )
            final_result = self._build_upload_result(
                action="upload_filing",
                ticker=normalized_ticker,
                filing_action=resolved_action,
                requested_action=requested_action,
                resolved_action=resolved_action,
                files=_json_text_list([str(path) for path in raw_request.files]),
                fiscal_year=raw_request.fiscal_year,
                fiscal_period=normalized_period,
                amended=raw_request.amended,
                filing_date=raw_request.filing_date,
                report_date=raw_request.report_date,
                company_id=normalized_company_id,
                company_name=raw_request.company_name,
                ticker_aliases=_json_text_list(list(raw_request.ticker_aliases)),
                overwrite=raw_request.overwrite,
                **upload_result.payload,
                stored_file_count=upload_result.stored_file_count,
                status=_resolve_upload_status(upload_result.status),
            )
            yield UploadFilingEvent(
                event_type=UploadFilingEventType.UPLOAD_COMPLETED,
                ticker=normalized_ticker,
                document_id=document_id,
                payload={"result": final_result},
            )
        except FinsUploadFailureError as exc:
            _LOGGER.exception("CN/HK filing upload typed content admission failed")
            yield _build_cn_filing_failure_event(
                pipeline=self,
                request=authoritative_request,
                requested_action=requested_action,
                failure_reason=exc.failure,
            )
        except OSError as exc:
            _LOGGER.exception("CN/HK filing upload storage operation failed")
            failure_reason = fins_upload_failure_from_exception(exc, file_label=None)
            yield _build_cn_filing_failure_event(
                pipeline=self,
                request=authoritative_request,
                requested_action=requested_action,
                failure_reason=failure_reason,
            )
        except Exception as exc:
            _LOGGER.exception("CN/HK filing upload runtime operation failed")
            failure_reason = fins_upload_failure_from_exception(exc, file_label=None)
            yield _build_cn_filing_failure_event(
                pipeline=self,
                request=authoritative_request,
                requested_action=requested_action,
                failure_reason=failure_reason,
            )

    def upload_material(
        self,
        ticker: str,
        action: Optional[str],
        form_type: str,
        material_name: str,
        files: Optional[list[Path]] = None,
        document_id: Optional[str] = None,
        internal_document_id: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        filing_date: Optional[str] = None,
        report_date: Optional[str] = None,
        company_id: Optional[str] = None,
        company_name: Optional[str] = None,
        ticker_aliases: Optional[list[str]] = None,
        overwrite: bool = False,
        *,
        cancellation_checker: CancellationToken | None = None,
    ) -> CnPipelineUploadResult:
        """执行 CN/HK 材料上传并同步返回聚合结果。

        Args:
            ticker: 股票代码。
            action: 可选动作类型。
            form_type: 材料类型。
            material_name: 材料名称。
            files: 可选上传文件列表。
            document_id: 可选文档 ID。
            internal_document_id: 可选内部文档 ID。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            filing_date: 可选披露日期。
            report_date: 可选报告日期。
            company_id: 可选兼容字段。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            overwrite: 是否强制覆盖。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            上传结果字典。

        Raises:
            RuntimeError: 当前线程存在运行中的事件循环时抛出。
        """

        return _run_async_upload_sync(
            collect_cn_upload_result_from_events(
                self.upload_material_stream(
                    ticker=ticker,
                    action=action,
                    form_type=form_type,
                    material_name=material_name,
                    files=files,
                    document_id=document_id,
                    internal_document_id=internal_document_id,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    filing_date=filing_date,
                    report_date=report_date,
                    company_id=company_id,
                    company_name=company_name,
                    ticker_aliases=ticker_aliases,
                    overwrite=overwrite,
                    cancellation_checker=cancellation_checker,
                ),
                stream_name="upload_material_stream",
            )
        )

    async def upload_material_stream(
        self,
        ticker: str,
        action: Optional[str],
        form_type: str,
        material_name: str,
        files: Optional[list[Path]] = None,
        document_id: Optional[str] = None,
        internal_document_id: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        filing_date: Optional[str] = None,
        report_date: Optional[str] = None,
        company_id: Optional[str] = None,
        company_name: Optional[str] = None,
        ticker_aliases: Optional[list[str]] = None,
        overwrite: bool = False,
        *,
        cancellation_checker: CancellationToken | None = None,
    ) -> AsyncIterator[UploadMaterialEvent]:
        """执行流式 CN/HK 材料上传。

        Args:
            ticker: 股票代码。
            action: 可选动作类型。
            form_type: 材料类型。
            material_name: 材料名称。
            files: 可选上传文件列表。
            document_id: 可选文档 ID。
            internal_document_id: 可选内部文档 ID。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            filing_date: 可选披露日期。
            report_date: 可选报告日期。
            company_id: 可选兼容字段。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            overwrite: 是否强制覆盖。
            cancellation_checker: 可选协作式取消检查器。

        Yields:
            上传过程事件流。

        Raises:
            RuntimeError: 上传执行失败时抛出。
        """

        file_list = files or []
        normalized_ticker = _normalize_upload_ticker(ticker)
        normalized_company_id = build_upload_company_id(normalized_ticker)
        normalized_fiscal_period = str(fiscal_period or "").strip().upper() or None
        stable_document_id, stable_internal_document_id = build_material_ids(
            form_type=form_type,
            material_name=material_name,
            fiscal_year=fiscal_year,
            fiscal_period=normalized_fiscal_period,
        )
        resolved_document_id, resolved_internal_id = validate_material_upload_ids(
            stable_document_id=stable_document_id,
            stable_internal_document_id=stable_internal_document_id,
            document_id=document_id,
            internal_document_id=internal_document_id,
        )
        requested_action = str(action or "").strip().lower() or None
        resolved_action: str | None = None
        try:
            previous_meta = self._safe_get_upload_document_meta(
                normalized_ticker,
                resolved_document_id,
                SourceKind.MATERIAL,
            )
            resolved_action = resolve_upload_action(action, previous_meta)
            yield UploadMaterialEvent(
                event_type=UploadMaterialEventType.UPLOAD_STARTED,
                ticker=normalized_ticker,
                document_id=resolved_document_id,
                payload={
                    "action": resolved_action,
                    "requested_action": requested_action,
                    "resolved_action": resolved_action,
                    "form_type": form_type,
                    "material_name": material_name,
                    "internal_document_id": resolved_internal_id,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": normalized_fiscal_period,
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "company_id": normalized_company_id,
                    "company_name": company_name,
                    "ticker_aliases": _json_text_list(ticker_aliases),
                    "overwrite": overwrite,
                    "file_count": len(file_list),
                },
            )
            company_batch = self._batching_repository.begin_batch(normalized_ticker)
            try:
                stage_company_meta_for_upload(
                    repository=self._company_repository,
                    ticker=normalized_ticker,
                    action=resolved_action,
                    company_name=company_name,
                    ticker_aliases=ticker_aliases,
                    batch=company_batch,
                )
            except BaseException:
                self._batching_repository.rollback_batch(company_batch)
                raise
            self._batching_repository.commit_batch(company_batch)
            prepared_upload = await self._upload_service.prepare_upload(
                ticker=normalized_ticker,
                source_kind=SourceKind.MATERIAL,
                action=resolved_action,
                document_id=resolved_document_id,
                internal_document_id=resolved_internal_id,
                form_type=form_type,
                files=file_list,
                overwrite=overwrite,
                previous_meta=previous_meta,
                cancellation=cancellation_checker,
                meta={
                    "company_id": normalized_company_id,
                    "ingest_method": FinsIngestMethod.UPLOAD.to_storage_value(),
                    "material_name": material_name,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": normalized_fiscal_period,
                    "filing_date": filing_date,
                    "report_date": report_date,
                },
            )
            if isinstance(prepared_upload, UploadOperationResult):
                upload_result = prepared_upload
            else:
                upload_result = commit_prepared_upload_batch(
                    service=self._upload_service,
                    batching_repository=self._batching_repository,
                    batch=self._batching_repository.begin_batch(normalized_ticker),
                    prepared=prepared_upload,
                    cancellation=cancellation_checker,
                )
            for file_event in upload_result.file_events:
                yield UploadMaterialEvent(
                    event_type=_map_upload_file_event_to_material_event_type(file_event),
                    ticker=normalized_ticker,
                    document_id=resolved_document_id,
                    payload={"name": file_event.name, **file_event.payload},
                )
            final_result = self._build_upload_result(
                action="upload_material",
                ticker=normalized_ticker,
                material_action=resolved_action,
                requested_action=requested_action,
                resolved_action=resolved_action,
                form_type=form_type,
                material_name=material_name,
                files=_json_text_list([str(path) for path in file_list]),
                fiscal_year=fiscal_year,
                fiscal_period=normalized_fiscal_period,
                filing_date=filing_date,
                report_date=report_date,
                company_id=normalized_company_id,
                company_name=company_name,
                overwrite=overwrite,
                **upload_result.payload,
                stored_file_count=upload_result.stored_file_count,
                status=_resolve_upload_status(upload_result.status),
            )
            yield UploadMaterialEvent(
                event_type=UploadMaterialEventType.UPLOAD_COMPLETED,
                ticker=normalized_ticker,
                document_id=resolved_document_id,
                payload={"result": final_result},
            )
        except Exception as exc:
            failure_reason = fins_upload_failure_from_exception(exc, file_label=None)
            failed_result = self._build_upload_result(
                action="upload_material",
                ticker=normalized_ticker,
                material_action=resolved_action,
                requested_action=requested_action,
                resolved_action=resolved_action,
                form_type=form_type,
                material_name=material_name,
                files=_json_text_list([str(path) for path in file_list]),
                document_id=resolved_document_id,
                internal_document_id=resolved_internal_id,
                fiscal_year=fiscal_year,
                fiscal_period=normalized_fiscal_period,
                filing_date=filing_date,
                report_date=report_date,
                company_id=normalized_company_id,
                company_name=company_name,
                overwrite=overwrite,
                stored_file_count=0,
                status="failed",
                message=failure_reason.message,
                failure=failure_reason.to_json(),
            )
            yield UploadMaterialEvent(
                event_type=UploadMaterialEventType.UPLOAD_FAILED,
                ticker=normalized_ticker,
                document_id=resolved_document_id,
                payload={"error": failure_reason.message, "result": failed_result},
            )

    def _safe_get_upload_document_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> dict[str, JsonValue] | None:
        """安全读取上传目标 source meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 源文档类型。

        Returns:
            元数据字典；不存在时返回 ``None``。

        Raises:
            ValueError: 元数据格式非法时抛出。
            OSError: 仓储读取失败时抛出。
        """

        try:
            return self._source_repository.get_source_meta(
                ticker=ticker,
                document_id=document_id,
                source_kind=source_kind,
            )
        except FileNotFoundError:
            return None

    def _build_upload_result(self, action: str, **payload: JsonValue) -> dict[str, JsonValue]:
        """构建统一上传结果。

        Args:
            action: 动作名称。
            **payload: 结果负载字段。

        Returns:
            统一结构的结果字典。

        Raises:
            KeyError: payload 缺少显式 status 时抛出。
        """

        return {
            "pipeline": _pipeline_name_for_ticker(str(payload.get("ticker", ""))),
            "action": action,
            "status": payload.pop("status"),
            **payload,
        }


class CnDownloadAdapter(FinsSourceDownloadAdapter):
    """CN/HK persisted-summary 下载 adapter。"""

    def __init__(
        self,
        *,
        pipeline: CnPipeline,
        source: str,
        market: CnMarketKind,
    ) -> None:
        """初始化 adapter。

        Args:
            pipeline: 已装配 NEW repositories 的 CN/HK 下载管线。
            source: adapter 绑定的下载来源。
            market: adapter 绑定的市场。

        Returns:
            无。

        Raises:
            ValueError: 来源与市场组合非法时抛出。
        """

        if (source, market) not in {
            (CN_DOWNLOAD_SOURCE, "CN"),
            (HK_DOWNLOAD_SOURCE, "HK"),
        }:
            raise ValueError(f"非法 CN/HK 下载 adapter 组合: source={source} market={market}")
        self._pipeline = pipeline
        self._source = source
        self._market = market

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """执行 CN/HK 下载并返回已持久化摘要。

        CN/HK adapter 是 persisted-summary adapter：现有 ``CnPipeline`` host
        负责 company/source/blob 与 local-only rebuild 副作用。

        Args:
            request: runtime 传入的已归一化下载请求。

        Returns:
            adapter 结果；CN/HK workflow 已通过 storage repositories 完成落盘。

        Raises:
            ValueError: ticker 市场或来源非法时抛出。
            RuntimeError: CN/HK 下载失败时抛出。
        """

        if request.normalized_ticker.market != self._market:
            raise ValueError(
                f"CN/HK 下载 market 不匹配: expected={self._market} actual={request.normalized_ticker.market}"
            )
        expected_source = FinsDownloadSource.CNINFO if self._market == "CN" else FinsDownloadSource.HKEXNEWS
        if request.source is not expected_source:
            raise ValueError(f"CN/HK 下载来源不匹配: expected={expected_source.value} actual={request.source.value}")
        result = _run_async_download_sync(
            collect_cn_download_result_from_events(
                self._pipeline.download_stream(
                    ticker=request.normalized_ticker.canonical,
                    form_type=_form_type_from_adapter_request(request.form_types),
                    start_date=request.date_range.start_text,
                    end_date=request.date_range.end_text,
                    overwrite=request.overwrite_existing,
                    rebuild=request.rebuild_local_artifacts,
                    start_is_explicit=request.date_range.start_is_explicit,
                    cancel_checker=request.cancellation_checker,
                ),
                progress_sink=request.progress_sink,
            )
        )
        persisted_summary = _summary_from_pipeline_result(
            result,
            request=request,
            source_repository=self._pipeline.source_repository,
        )
        return FinsSourceDownloadAdapterResult(
            discovered_count=persisted_summary.discovered_count,
            persisted_summary=persisted_summary,
        )


def _form_type_from_adapter_request(form_types: tuple[str, ...]) -> Optional[str]:
    """把 runtime form tuple 转为 OLD pipeline form_type 字符串。

    Args:
        form_types: 表单过滤元组。

    Returns:
        OLD pipeline 接受的逗号分隔表单字符串；空过滤返回 ``None``。

    Raises:
        无。
    """

    if not form_types:
        return None
    return _CN_FORMS_ADAPTER_JOINER.join(form_types)


def _summary_from_pipeline_result(
    result: Mapping[str, JsonValue],
    *,
    request: FinsSourceDownloadAdapterRequest,
    source_repository: SourceDocumentRepositoryProtocol,
) -> FinsDownloadResultSummary:
    """把 CN/HK workflow 私有结果严格投影为 typed 下载摘要。

    Args:
        result: CN/HK workflow 私有结果。
        request: 当前 adapter typed request。
        source_repository: relative locator 的 storage owner。

    Returns:
        rows、missing periods 与 effective filters 完整的 typed summary。

    Raises:
        ValueError: 必填字段缺失、类型非法或身份不一致时抛出。
        OSError: locator 查询失败时由 storage owner 抛出。
    """

    status = _required_cn_text(result, "status")
    if status not in {_CN_TERMINAL_OK, _CN_TERMINAL_CANCELLED}:
        raise ValueError(f"CN/HK 下载结果 terminal status 未封闭: {status}")
    ticker = _required_cn_text(result, "ticker")
    if ticker != request.normalized_ticker.canonical:
        raise ValueError("CN/HK 下载结果 ticker 与 typed request 不一致")
    filings = _required_cn_mapping_list(result, "filings")
    rows = tuple(
        _project_cn_document_row(
            item,
            ticker=ticker,
            source_repository=source_repository,
        )
        for item in filings
    )
    missing_periods = _required_cn_text_list(result, "missing_periods")
    filters = _project_cn_effective_filters(result, request=request)
    return FinsDownloadResultSummary.from_document_rows(
        source=request.source,
        canonical_ticker=ticker,
        effective_filters=filters,
        document_rows=rows,
        missing_periods=missing_periods,
    )


def _project_cn_document_row(
    item: Mapping[str, JsonValue],
    *,
    ticker: str,
    source_repository: SourceDocumentRepositoryProtocol,
) -> FinsDownloadDocumentResult:
    """严格投影单个 CN/HK filing result。

    Args:
        item: workflow 私有 filing result。
        ticker: canonical ticker。
        source_repository: relative locator 查询 owner。

    Returns:
        typed 单文档结果。

    Raises:
        ValueError: 必填字段缺失、类型非法或 status 未封闭时抛出。
        OSError: downloaded locator 查询失败时抛出。
    """

    document_id = _required_cn_text(item, "document_id")
    status = _required_cn_text(item, "status")
    reason_code = _optional_cn_text(item, "reason_code")
    allow_missing_business_fields = status == _CN_STATUS_FAILED and reason_code == "missing_form_type"
    form_or_period = _required_optional_cn_text(
        item,
        "form_type",
        allow_missing=allow_missing_business_fields,
    )
    filing_date = _required_optional_cn_text(
        item,
        "filing_date",
        allow_missing=allow_missing_business_fields,
    )
    report_date = _required_optional_cn_text(
        item,
        "report_date",
        allow_missing=allow_missing_business_fields,
    )
    covered_fiscal_periods = _required_cn_covered_fiscal_periods(
        item,
        identity_period=form_or_period,
    )
    if status == _CN_STATUS_DOWNLOADED:
        locator = source_repository.get_source_document_locator(
            ticker,
            document_id,
            SourceKind.FILING,
        )
        return FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period=form_or_period,
            filing_date=filing_date,
            report_date=report_date,
            covered_fiscal_periods=covered_fiscal_periods,
            disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
            reason_category=None,
            reason_message=None,
            artifact_locator=locator,
        )
    if status == _CN_STATUS_SKIPPED:
        category = reason_code or _required_cn_text(item, "skip_reason")
        return FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period=form_or_period,
            filing_date=filing_date,
            report_date=report_date,
            covered_fiscal_periods=covered_fiscal_periods,
            disposition=FinsDownloadDocumentDisposition.SKIPPED,
            reason_category=category,
            reason_message="该文档按下载策略跳过",
            artifact_locator=None,
        )
    if status == _CN_STATUS_FAILED:
        return FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period=form_or_period,
            filing_date=filing_date,
            report_date=report_date,
            covered_fiscal_periods=covered_fiscal_periods,
            disposition=FinsDownloadDocumentDisposition.FAILED,
            reason_category=reason_code or "cn_document_failed",
            reason_message="财报来源未能完成该文档",
            artifact_locator=None,
        )
    raise ValueError(f"CN/HK 下载结果 status 未封闭: {status}")


def _project_cn_effective_filters(
    result: Mapping[str, JsonValue],
    *,
    request: FinsSourceDownloadAdapterRequest,
) -> FinsDownloadEffectiveFilters:
    """严格读取 CN/HK workflow 实际采用的筛选条件。

    Args:
        result: workflow 私有结果。
        request: 当前 typed request，用于核对 mutation flags。

    Returns:
        typed effective filters。

    Raises:
        ValueError: filters 缺失、类型非法或 flags 与 request 不一致时抛出。
    """

    filters = _required_cn_mapping(result, "filters")
    forms = _required_cn_text_list(filters, "forms")
    start_dates = _required_cn_mapping(filters, "start_dates")
    start_values = tuple(_required_cn_text(start_dates, key) for key in sorted(start_dates))
    start_date = min(start_values) if start_values else None
    end_date = _required_optional_cn_text(filters, "end_date", allow_missing=False)
    overwrite = _required_cn_bool(filters, "overwrite")
    if overwrite is not request.overwrite_existing:
        raise ValueError("CN/HK effective overwrite 与 typed request 不一致")
    if "rebuild" in filters:
        rebuild = _required_cn_bool(filters, "rebuild")
        if rebuild is not request.rebuild_local_artifacts:
            raise ValueError("CN/HK effective rebuild 与 typed request 不一致")
    return FinsDownloadEffectiveFilters(
        form_types=forms,
        start_date=start_date,
        end_date=end_date,
        overwrite_existing=overwrite,
        rebuild_local_artifacts=request.rebuild_local_artifacts,
    )


def _required_cn_mapping(
    value: Mapping[str, JsonValue],
    key: str,
) -> Mapping[str, JsonValue]:
    """读取 CN/HK 私有结果中的必填 mapping。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        只读 mapping。

    Raises:
        ValueError: 字段缺失或类型非法时抛出。
    """

    if key not in value or not isinstance(value[key], Mapping):
        raise ValueError(f"CN/HK 下载结果 {key} 字段必须是对象")
    raw = value[key]
    assert isinstance(raw, Mapping)
    return raw


def _required_cn_mapping_list(
    value: Mapping[str, JsonValue],
    key: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 CN/HK 私有结果中的必填 mapping 列表。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        保持原顺序的 mapping tuple。

    Raises:
        ValueError: 字段缺失、不是列表或元素不是对象时抛出。
    """

    if key not in value or not isinstance(value[key], list):
        raise ValueError(f"CN/HK 下载结果 {key} 字段必须是列表")
    raw_items = value[key]
    assert isinstance(raw_items, list)
    items: list[Mapping[str, JsonValue]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"CN/HK 下载结果 {key}[{index}] 必须是对象")
        items.append(raw_item)
    return tuple(items)


def _required_cn_text(value: Mapping[str, JsonValue], key: str) -> str:
    """读取 CN/HK 私有结果中的必填非空文本。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        去空白文本。

    Raises:
        ValueError: 字段缺失、类型非法或为空时抛出。
    """

    if key not in value:
        raise ValueError(f"CN/HK 下载结果缺少必填文本字段: {key}")
    raw = value[key]
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"CN/HK 下载结果缺少必填文本字段: {key}")
    return raw.strip()


def _optional_cn_text(value: Mapping[str, JsonValue], key: str) -> str | None:
    """严格读取 CN/HK 私有结果中的可选文本。

    Args:
        value: 当前 mapping。
        key: 可选字段名。

    Returns:
        缺失或 ``None`` 返回 ``None``，否则返回去空白文本。

    Raises:
        ValueError: 字段存在但不是非空文本时抛出。
    """

    if key not in value or value[key] is None:
        return None
    return _required_cn_text(value, key)


def _required_optional_cn_text(
    value: Mapping[str, JsonValue],
    key: str,
    *,
    allow_missing: bool,
) -> str | None:
    """读取允许 ``None`` 但默认要求 key 存在的 CN/HK 文本。

    Args:
        value: 当前 mapping。
        key: 字段名。
        allow_missing: 特定 closed failure 是否允许字段缺失。

    Returns:
        ``None`` 或非空文本。

    Raises:
        ValueError: 必填 key 缺失或值类型非法时抛出。
    """

    if key not in value:
        if allow_missing:
            return None
        raise ValueError(f"CN/HK 下载结果缺少字段: {key}")
    if value[key] is None:
        return None
    return _required_cn_text(value, key)


def _required_cn_text_list(
    value: Mapping[str, JsonValue],
    key: str,
) -> tuple[str, ...]:
    """读取 CN/HK 私有结果中的必填文本列表。

    Args:
        value: 当前 mapping。
        key: 字段名。

    Returns:
        文本 tuple。

    Raises:
        ValueError: 字段缺失、类型非法或元素非法时抛出。
    """

    if key not in value or not isinstance(value[key], list):
        raise ValueError(f"CN/HK 下载结果 {key} 字段必须是列表")
    raw_items = value[key]
    assert isinstance(raw_items, list)
    items: list[str] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"CN/HK 下载结果 {key}[{index}] 必须是非空文本")
        items.append(item.strip())
    return tuple(items)


def _required_cn_covered_fiscal_periods(
    value: Mapping[str, JsonValue],
    *,
    identity_period: str | None,
) -> tuple[str, ...]:
    """严格读取 workflow 的必填覆盖财期投影。

    Args:
        value: 单文档 workflow 结果。
        identity_period: 同行身份财期；closed failure 可为 ``None``。

    Returns:
        canonical ordered 覆盖财期 tuple。

    Raises:
        ValueError: 字段缺失、为空、重复、顺序非法或不含 identity 时抛出。
    """

    periods = _required_cn_text_list(value, "covered_fiscal_periods")
    if not periods:
        raise ValueError("CN/HK 下载结果 covered_fiscal_periods 不能为空")
    if any(period not in CN_FISCAL_PERIOD_ORDER for period in periods):
        raise ValueError("CN/HK 下载结果 covered_fiscal_periods 含非法财期")
    if len(set(periods)) != len(periods):
        raise ValueError("CN/HK 下载结果 covered_fiscal_periods 不能重复")
    canonical = tuple(period for period in CN_FISCAL_PERIOD_ORDER if period in periods)
    if periods != canonical:
        raise ValueError("CN/HK 下载结果 covered_fiscal_periods 顺序非法")
    if identity_period is not None and identity_period not in periods:
        raise ValueError("CN/HK 下载结果 covered_fiscal_periods 必须包含 identity period")
    return periods


def _required_cn_bool(value: Mapping[str, JsonValue], key: str) -> bool:
    """读取 CN/HK 私有结果中的必填布尔字段。

    Args:
        value: 当前 mapping。
        key: 字段名。

    Returns:
        布尔值。

    Raises:
        ValueError: 字段缺失或不是布尔值时抛出。
    """

    if key not in value or not isinstance(value[key], bool):
        raise ValueError(f"CN/HK 下载结果 {key} 字段必须是布尔值")
    raw = value[key]
    assert isinstance(raw, bool)
    return raw


def _pipeline_name_for_ticker(ticker: str) -> str:
    """按 ticker 文本推导事件中的 pipeline 名称。

    Args:
        ticker: 原始 ticker。

    Returns:
        ``"hk"`` 或 ``"cn"``。

    Raises:
        无。
    """

    normalized = try_normalize_ticker(ticker)
    if normalized is not None and normalized.market == "HK":
        return HK_PIPELINE_NAME
    return CN_PIPELINE_NAME


def _assert_authoritative_filing_identity(
    preflight: ValidatedFinsUploadFilingRequest,
    authoritative: ValidatedFinsUploadFilingRequest,
) -> None:
    """断言 fresh validator 未改变 CN/HK filing deterministic identity。

    Args:
        preflight: 入口 preflight validated request。
        authoritative: workflow fresh snapshot 产生的 validated request。

    Returns:
        无。

    Raises:
        RuntimeError: canonical ticker 或 filing identity 不一致时抛出。
    """

    if (
        authoritative.normalized_ticker.canonical != preflight.normalized_ticker.canonical
        or authoritative.document_id != preflight.document_id
        or authoritative.internal_document_id != preflight.internal_document_id
    ):
        raise RuntimeError("filing authoritative identity mismatch")


def _build_cn_filing_failure_event(
    *,
    pipeline: CnPipeline,
    request: ValidatedFinsUploadFilingRequest,
    requested_action: str,
    failure_reason: FinsUploadFailureReason,
) -> UploadFilingEvent:
    """从 authoritative request 与 typed reason 构造 CN/HK filing 失败事件。

    Args:
        pipeline: CN/HK pipeline facade。
        request: authoritative validated request。
        requested_action: 用户请求动作。
        failure_reason: closed public failure reason。

    Returns:
        单个 typed upload failed 事件。

    Raises:
        无。
    """

    raw_request = request.request
    normalized_ticker = request.normalized_ticker.canonical
    normalized_company_id = build_upload_company_id(normalized_ticker)
    failed_result = pipeline._build_upload_result(
        action="upload_filing",
        ticker=normalized_ticker,
        filing_action=request.resolved_action,
        requested_action=requested_action,
        resolved_action=request.resolved_action,
        files=_json_text_list([str(path) for path in raw_request.files]),
        fiscal_year=raw_request.fiscal_year,
        fiscal_period=request.normalized_fiscal_period,
        amended=raw_request.amended,
        filing_date=raw_request.filing_date,
        report_date=raw_request.report_date,
        company_id=normalized_company_id,
        company_name=raw_request.company_name,
        ticker_aliases=_json_text_list(list(raw_request.ticker_aliases)),
        overwrite=raw_request.overwrite,
        document_id=request.document_id,
        stored_file_count=0,
        status="failed",
        message=failure_reason.message,
        failure=failure_reason.to_json(),
    )
    return UploadFilingEvent(
        event_type=UploadFilingEventType.UPLOAD_FAILED,
        ticker=normalized_ticker,
        document_id=request.document_id,
        payload={"error": failure_reason.message, "result": failed_result},
    )


def _normalize_upload_ticker(ticker: str) -> str:
    """按公共 ticker 真源标准化上传 ticker。

    Args:
        ticker: 原始 ticker。

    Returns:
        canonical ticker。

    Raises:
        ValueError: ticker 为空或无法归一化时抛出。
    """

    return normalize_ticker(ticker).canonical


def _resolve_upload_status(upload_status: str) -> str:
    """将上传服务状态映射为 pipeline 对外状态。

    Args:
        upload_status: 上传服务内部状态。

    Returns:
        pipeline 对外状态值。

    Raises:
        无。
    """

    if upload_status == "uploaded":
        return "ok"
    return upload_status


def _json_text_list(values: list[str] | None) -> list[JsonValue]:
    """将文本列表收窄为 JSON 数组。

    Args:
        values: 文本列表。

    Returns:
        JSON 数组。

    Raises:
        无。
    """

    return [item for item in values or []]


def build_cn_download_adapter(
    *,
    workspace_root: Path,
    batching_repository: BatchingRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    docling_converter: DoclingConverter,
    user_agent: Optional[str] = None,
    sleep_seconds: float | None = None,
    max_retries: int | None = None,
) -> CnDownloadAdapter:
    """构建 production CNInfo 下载 adapter。

    Args:
        workspace_root: Fins 工作区根目录。
        batching_repository: batch lifecycle 仓储。
        company_repository: 公司元数据仓储。
        source_repository: 源文档仓储。
        processed_repository: processed 仓储。
        blob_repository: 文件对象仓储。
        filing_maintenance_repository: filing 维护仓储。
        docling_converter: 与其它 Fins 路径共享的 Docling converter。
        user_agent: 可选 HTTP User-Agent。
        sleep_seconds: 请求间隔秒数。
        max_retries: 下载重试次数。

    Returns:
        CNInfo 下载 adapter。

    Raises:
        OSError: downloader 或默认组件初始化失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=workspace_root,
        batching_repository=batching_repository,
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=filing_maintenance_repository,
        docling_converter=docling_converter,
        user_agent=user_agent,
        sleep_seconds=CNINFO_DEFAULT_SLEEP_SECONDS if sleep_seconds is None else sleep_seconds,
        max_retries=CNINFO_DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
    )
    return CnDownloadAdapter(pipeline=pipeline, source=CN_DOWNLOAD_SOURCE, market="CN")


def build_hk_download_adapter(
    *,
    workspace_root: Path,
    batching_repository: BatchingRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    docling_converter: DoclingConverter,
    user_agent: Optional[str] = None,
    sleep_seconds: float | None = None,
    max_retries: int | None = None,
) -> CnDownloadAdapter:
    """构建 production HKEXNews 下载 adapter。

    Args:
        workspace_root: Fins 工作区根目录。
        batching_repository: batch lifecycle 仓储。
        company_repository: 公司元数据仓储。
        source_repository: 源文档仓储。
        processed_repository: processed 仓储。
        blob_repository: 文件对象仓储。
        filing_maintenance_repository: filing 维护仓储。
        docling_converter: 与其它 Fins 路径共享的 Docling converter。
        user_agent: 可选 HTTP User-Agent。
        sleep_seconds: 请求间隔秒数。
        max_retries: 下载重试次数。

    Returns:
        HKEXNews 下载 adapter。

    Raises:
        OSError: downloader 或默认组件初始化失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=workspace_root,
        batching_repository=batching_repository,
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=filing_maintenance_repository,
        docling_converter=docling_converter,
        user_agent=user_agent,
        sleep_seconds=HKEXNEWS_DEFAULT_SLEEP_SECONDS if sleep_seconds is None else sleep_seconds,
        max_retries=HKEXNEWS_DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
    )
    return CnDownloadAdapter(pipeline=pipeline, source=HK_DOWNLOAD_SOURCE, market="HK")


__all__ = [
    "CN_DOWNLOAD_SOURCE",
    "HK_DOWNLOAD_SOURCE",
    "CnDownloadAdapter",
    "CnPipeline",
    "build_cn_download_adapter",
    "build_hk_download_adapter",
    "collect_cn_download_result_from_events",
    "collect_cn_upload_result_from_events",
]
