"""CN/HK 下载/上传管线与 NEW Fins runtime adapter。

本模块承载 OLD CN/HK pipeline 的下载面与 Slice 4 迁移的 production
upload facade：download、download_stream、上传 filing/material、下载候选过滤、
PDF gate、Docling JSON 转换、skip/overwrite 与本地 rebuild。process、CLI、
Host、tool/provider 装配不在本 Slice 内。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from pathlib import Path
from typing import Final, Optional, TypeAlias, cast

from dayu.contracts.json_value import JsonValue
from dayu.documents.docling_runtime import (
    DoclingRuntimeInitializationError,
    convert_pdf_bytes_with_docling,
)
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
from dayu.fins.ingestion_runtime import (
    FinsDownloadProgressEvent,
    FinsDownloadProgressSink,
    FinsDownloadResultSummary,
    FinsSourceDownloadAdapter,
    FinsSourceDownloadAdapterRequest,
    FinsSourceDownloadAdapterResult,
    mark_downloaded_processed_rebuild_required,
)
from dayu.fins.domain.document_models import FinsIngestMethod
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import CnMarketKind
from dayu.fins.pipelines.cn_download_pdf_gate import (
    CnDownloadPdfGateProtocol,
    NoopCnDownloadPdfGate,
)
from dayu.fins.pipelines.cn_download_protocols import (
    CnReportDiscoveryClientProtocol,
    PdfToDoclingJsonBytes,
)
from dayu.fins.pipelines.cn_download_workflow import run_cn_download_stream_impl
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    UploadCancellationChecker,
    build_cn_filing_ids,
    build_material_ids,
    derive_report_kind,
    normalize_cn_fiscal_period,
    resolve_upload_action,
    validate_material_upload_ids,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.upload_company_meta import build_upload_company_id, upsert_company_meta_for_upload
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent, UploadFilingEventType
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent, UploadMaterialEventType
from dayu.fins.pipelines.upload_progress_helpers import (
    map_upload_file_event_to_filing_event_type as _map_upload_file_event_to_filing_event_type,
    map_upload_file_event_to_material_event_type as _map_upload_file_event_to_material_event_type,
)
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import normalize_ticker, try_normalize_ticker

CN_DOWNLOAD_SOURCE: Final[str] = "cninfo"
HK_DOWNLOAD_SOURCE: Final[str] = "hkexnews"
CN_PIPELINE_NAME: Final[str] = "cn"
HK_PIPELINE_NAME: Final[str] = "hk"
_CN_FORMS_ADAPTER_JOINER: Final[str] = ","
_CN_STATUS_DOWNLOADED: Final[str] = "downloaded"
_ADAPTER_PROGRESS_FILE_STARTED: Final[str] = "download.file_started"
_ADAPTER_PROGRESS_FILE_COMPLETED: Final[str] = "download.file_completed"
_ADAPTER_PROGRESS_FILE_SKIPPED: Final[str] = "download.file_skipped"
_ADAPTER_PROGRESS_FILE_FAILED: Final[str] = "download.file_failed"
_ADAPTER_PROGRESS_CONVERSION_STARTED: Final[str] = "download.conversion_started"


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
                message="开始 convert",
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


def convert_pdf_bytes_to_docling_json_bytes(raw_data: bytes, stream_name: str) -> bytes:
    """将 PDF 字节流转换为序列化后的 Docling JSON 字节内容。

    Args:
        raw_data: PDF 原始字节内容。
        stream_name: 流名称，建议直接传文件名以保留扩展名。

    Returns:
        已编码为 UTF-8 的 Docling JSON 字节内容。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖缺失或装配失败时抛出。
        RuntimeError: Docling 转换失败或导出结构非法时抛出。
    """

    try:
        result = convert_pdf_bytes_with_docling(
            raw_data,
            stream_name=stream_name,
            do_ocr=True,
            do_table_structure=True,
            table_mode="accurate",
            do_cell_matching=True,
        )
    except DoclingRuntimeInitializationError:
        raise
    except Exception as exc:  # pragma: no cover - 第三方转换异常兜底
        raise RuntimeError(f"Docling 转换失败: {stream_name}") from exc
    payload = cast(JsonValue, result.document.export_to_dict())
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Docling 导出结果非法: {stream_name}")
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


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
        convert_pdf_to_docling_json: PdfToDoclingJsonBytes | None = None,
        company_repository: CompanyMetaRepositoryProtocol | None = None,
        source_repository: SourceDocumentRepositoryProtocol | None = None,
        processed_repository: ProcessedDocumentRepositoryProtocol | None = None,
        blob_repository: DocumentBlobRepositoryProtocol | None = None,
        filing_maintenance_repository: FilingMaintenanceRepositoryProtocol | None = None,
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
            convert_pdf_to_docling_json: 可选 PDF 到 Docling JSON bytes 转换函数。
            company_repository: 可选公司元数据仓储。
            source_repository: 可选源文档仓储。
            processed_repository: 可选 processed 文档仓储。
            blob_repository: 可选文件对象仓储。
            filing_maintenance_repository: 可选 filing 维护仓储。
            user_agent: CN/HK HTTP User-Agent；为空时各 downloader 使用显式默认值。
            sleep_seconds: 连续 HTTP 请求间隔秒数。
            max_retries: 单次 HTTP 请求最大重试次数。

        Returns:
            无。

        Raises:
            OSError: 默认文件系统仓储初始化失败时抛出。
        """

        self._workspace_root = (workspace_root or Path.cwd()).resolve()
        repository_set = build_fs_repository_set(workspace_root=self._workspace_root)
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
        self._convert_pdf_to_docling_json = (
            convert_pdf_to_docling_json or convert_pdf_bytes_to_docling_json_bytes
        )
        self._upload_service = DoclingUploadService(
            source_repository=self._source_repository,
            blob_repository=self._blob_repository,
        )

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
    def convert_pdf_to_docling_json(self) -> PdfToDoclingJsonBytes:
        """返回 PDF 到 Docling JSON bytes 转换函数。

        Args:
            无。

        Returns:
            转换函数。

        Raises:
            无。
        """

        return self._convert_pdf_to_docling_json

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
        cancel_checker: Optional[Callable[[], bool]] = None,
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
        cancel_checker: Optional[Callable[[], bool]] = None,
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
            cancel_checker=cancel_checker,
            module=self.MODULE,
            pipeline_name=pipeline_name,
        ):
            yield event

    def upload_filing(
        self,
        ticker: str,
        action: Optional[str],
        files: list[Path],
        fiscal_year: int,
        fiscal_period: str,
        amended: bool = False,
        filing_date: Optional[str] = None,
        report_date: Optional[str] = None,
        company_id: Optional[str] = None,
        company_name: Optional[str] = None,
        ticker_aliases: Optional[list[str]] = None,
        overwrite: bool = False,
        *,
        cancellation_checker: UploadCancellationChecker | None = None,
    ) -> CnPipelineUploadResult:
        """执行 CN/HK 财报上传并同步返回聚合结果。

        Args:
            ticker: 股票代码。
            action: 可选动作类型。
            files: 上传文件列表。
            fiscal_year: 财年。
            fiscal_period: 财期。
            amended: 是否修订版。
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
                self.upload_filing_stream(
                    ticker=ticker,
                    action=action,
                    files=files,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    amended=amended,
                    filing_date=filing_date,
                    report_date=report_date,
                    company_id=company_id,
                    company_name=company_name,
                    ticker_aliases=ticker_aliases,
                    overwrite=overwrite,
                    cancellation_checker=cancellation_checker,
                ),
                stream_name="upload_filing_stream",
            )
        )

    async def upload_filing_stream(
        self,
        ticker: str,
        action: Optional[str],
        files: list[Path],
        fiscal_year: int,
        fiscal_period: str,
        amended: bool = False,
        filing_date: Optional[str] = None,
        report_date: Optional[str] = None,
        company_id: Optional[str] = None,
        company_name: Optional[str] = None,
        ticker_aliases: Optional[list[str]] = None,
        overwrite: bool = False,
        *,
        cancellation_checker: UploadCancellationChecker | None = None,
    ) -> AsyncIterator[UploadFilingEvent]:
        """执行流式 CN/HK 财报上传。

        Args:
            ticker: 股票代码。
            action: 可选动作类型。
            files: 上传文件列表。
            fiscal_year: 财年。
            fiscal_period: 财期。
            amended: 是否修订版。
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

        normalized_ticker = _normalize_upload_ticker(ticker)
        normalized_company_id = build_upload_company_id(normalized_ticker)
        normalized_period = normalize_cn_fiscal_period(fiscal_period)
        form_type = normalized_period
        requested_action = str(action or "").strip().lower() or None
        document_id, internal_document_id = build_cn_filing_ids(
            ticker=normalized_ticker,
            form_type=form_type,
            fiscal_year=fiscal_year,
            fiscal_period=normalized_period,
            amended=amended,
        )
        previous_meta = self._safe_get_upload_document_meta(
            normalized_ticker,
            document_id,
            SourceKind.FILING,
        )
        resolved_action = resolve_upload_action(action, previous_meta)
        yield UploadFilingEvent(
            event_type=UploadFilingEventType.UPLOAD_STARTED,
            ticker=normalized_ticker,
            document_id=document_id,
            payload={
                "action": resolved_action,
                "requested_action": requested_action,
                "resolved_action": resolved_action,
                "fiscal_year": fiscal_year,
                "fiscal_period": normalized_period,
                "amended": amended,
                "filing_date": filing_date,
                "report_date": report_date,
                "company_id": normalized_company_id,
                "company_name": company_name,
                "ticker_aliases": _json_text_list(ticker_aliases),
                "overwrite": overwrite,
                "file_count": len(files),
            },
        )
        try:
            upsert_company_meta_for_upload(
                repository=self._company_repository,
                ticker=normalized_ticker,
                action=resolved_action,
                company_id=company_id,
                company_name=company_name,
                ticker_aliases=ticker_aliases,
            )
            upload_result = self._upload_service.execute_upload(
                ticker=normalized_ticker,
                source_kind=SourceKind.FILING,
                action=resolved_action,
                document_id=document_id,
                internal_document_id=internal_document_id,
                form_type=form_type,
                files=files,
                overwrite=overwrite,
                cancellation_checker=cancellation_checker,
                meta={
                    "company_id": normalized_company_id,
                    "ingest_method": FinsIngestMethod.UPLOAD.to_storage_value(),
                    "fiscal_year": fiscal_year,
                    "fiscal_period": normalized_period,
                    "report_kind": derive_report_kind(normalized_period),
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "amended": amended,
                },
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
                files=_json_text_list([str(path) for path in files]),
                fiscal_year=fiscal_year,
                fiscal_period=normalized_period,
                amended=amended,
                filing_date=filing_date,
                report_date=report_date,
                company_id=normalized_company_id,
                company_name=company_name,
                ticker_aliases=_json_text_list(ticker_aliases),
                overwrite=overwrite,
                **upload_result.payload,
                status=_resolve_upload_status(upload_result.status),
            )
            yield UploadFilingEvent(
                event_type=UploadFilingEventType.UPLOAD_COMPLETED,
                ticker=normalized_ticker,
                document_id=document_id,
                payload={"result": final_result},
            )
        except Exception as exc:
            failed_result = self._build_upload_result(
                action="upload_filing",
                ticker=normalized_ticker,
                filing_action=resolved_action,
                requested_action=requested_action,
                resolved_action=resolved_action,
                files=_json_text_list([str(path) for path in files]),
                fiscal_year=fiscal_year,
                fiscal_period=normalized_period,
                amended=amended,
                filing_date=filing_date,
                report_date=report_date,
                company_id=normalized_company_id,
                company_name=company_name,
                ticker_aliases=_json_text_list(ticker_aliases),
                overwrite=overwrite,
                document_id=document_id,
                status="failed",
                message=str(exc),
            )
            yield UploadFilingEvent(
                event_type=UploadFilingEventType.UPLOAD_FAILED,
                ticker=normalized_ticker,
                document_id=document_id,
                payload={"error": str(exc), "result": failed_result},
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
        cancellation_checker: UploadCancellationChecker | None = None,
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
        cancellation_checker: UploadCancellationChecker | None = None,
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
        previous_meta = self._safe_get_upload_document_meta(
            normalized_ticker,
            resolved_document_id,
            SourceKind.MATERIAL,
        )
        requested_action = str(action or "").strip().lower() or None
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
        try:
            upsert_company_meta_for_upload(
                repository=self._company_repository,
                ticker=normalized_ticker,
                action=resolved_action,
                company_id=company_id,
                company_name=company_name,
                ticker_aliases=ticker_aliases,
            )
            upload_result = self._upload_service.execute_upload(
                ticker=normalized_ticker,
                source_kind=SourceKind.MATERIAL,
                action=resolved_action,
                document_id=resolved_document_id,
                internal_document_id=resolved_internal_id,
                form_type=form_type,
                files=file_list,
                overwrite=overwrite,
                cancellation_checker=cancellation_checker,
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
                status=_resolve_upload_status(upload_result.status),
            )
            yield UploadMaterialEvent(
                event_type=UploadMaterialEventType.UPLOAD_COMPLETED,
                ticker=normalized_ticker,
                document_id=resolved_document_id,
                payload={"result": final_result},
            )
        except Exception as exc:
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
                status="failed",
                message=str(exc),
            )
            yield UploadMaterialEvent(
                event_type=UploadMaterialEventType.UPLOAD_FAILED,
                ticker=normalized_ticker,
                document_id=resolved_document_id,
                payload={"error": str(exc), "result": failed_result},
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

        CN/HK adapter 是 persisted-summary adapter：迁移的 OLD workflow 已经
        通过 NEW storage repositories 完成 company/source/blob 副作用。
        ``request.rebuild_processed`` 只代表 NEW processed 重处理治理语义；
        adapter 在下载摘要确认后按 ``written_document_ids`` 标记既有 processed
        需要重处理，不映射为 OLD ``CnPipeline.download(rebuild=...)``。

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
        if request.source not in {self._source, "auto"}:
            raise ValueError(f"CN/HK 下载来源不匹配: expected={self._source} actual={request.source}")
        result = _run_async_download_sync(
            collect_cn_download_result_from_events(
                self._pipeline.download_stream(
                    ticker=request.normalized_ticker.canonical,
                    form_type=_form_type_from_adapter_request(request.form_types),
                    start_date=request.filed_after,
                    end_date=request.filed_before,
                    overwrite=request.overwrite_existing,
                    rebuild=False,
                    cancel_checker=request.cancellation_checker,
                ),
                progress_sink=request.progress_sink,
            )
        )
        persisted_summary = _summary_from_pipeline_result(result)
        if request.rebuild_processed:
            mark_downloaded_processed_rebuild_required(
                self._pipeline.processed_repository,
                ticker=request.normalized_ticker.canonical,
                summary=persisted_summary,
            )
        return FinsSourceDownloadAdapterResult(
            discovered_count=_summary_int(result, "total"),
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


def _summary_from_pipeline_result(result: Mapping[str, JsonValue]) -> FinsDownloadResultSummary:
    """把 OLD CN/HK pipeline 结果转换为 runtime 下载摘要。

    Args:
        result: OLD pipeline 下载结果。

    Returns:
        runtime 下载结果摘要。

    Raises:
        ValueError: 结果字段类型非法时抛出。
    """

    filings = result.get("filings", [])
    if not isinstance(filings, list):
        raise ValueError("CN/HK 下载结果 filings 字段必须是列表")
    written_document_ids: list[str] = []
    for item in filings:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") == _CN_STATUS_DOWNLOADED:
            document_id = str(item.get("document_id", "")).strip()
            if document_id:
                written_document_ids.append(document_id)
    summary = result.get("summary", {})
    summary_mapping: Mapping[str, JsonValue] = summary if isinstance(summary, Mapping) else {}
    return FinsDownloadResultSummary(
        discovered_count=_summary_int(result, "total"),
        downloaded_count=_json_int(summary_mapping.get("downloaded"), "summary.downloaded"),
        skipped_count=_json_int(summary_mapping.get("skipped"), "summary.skipped"),
        rejected_count=0,
        failed_count=_json_int(summary_mapping.get("failed"), "summary.failed"),
        written_document_ids=tuple(written_document_ids),
    )


def _summary_int(result: Mapping[str, JsonValue], field_name: str) -> int:
    """从 OLD 下载结果读取 summary 整数。

    Args:
        result: OLD pipeline 下载结果。
        field_name: summary 字段名。

    Returns:
        非负整数；缺失时返回 0。

    Raises:
        ValueError: 字段无法转换为非负整数时抛出。
    """

    summary = result.get("summary", {})
    if not isinstance(summary, Mapping):
        return 0
    return _json_int(summary.get(field_name), f"summary.{field_name}")


def _json_int(value: JsonValue | None, field_name: str) -> int:
    """从 JSON 值读取非负整数。

    Args:
        value: 原始 JSON 值。
        field_name: 字段名，用于错误说明。

    Returns:
        非负整数；空值返回 0。

    Raises:
        ValueError: 字段无法转换为非负整数时抛出。
    """

    if isinstance(value, list) or isinstance(value, Mapping):
        raise ValueError(f"CN/HK 下载 {field_name} 不是整数")
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CN/HK 下载 {field_name} 不是整数") from exc
    if parsed < 0:
        raise ValueError(f"CN/HK 下载 {field_name} 不能为负数")
    return parsed


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
    company_repository: CompanyMetaRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    user_agent: Optional[str] = None,
    sleep_seconds: float | None = None,
    max_retries: int | None = None,
) -> CnDownloadAdapter:
    """构建 production CNInfo 下载 adapter。

    Args:
        workspace_root: Fins 工作区根目录。
        company_repository: 公司元数据仓储。
        source_repository: 源文档仓储。
        processed_repository: processed 仓储。
        blob_repository: 文件对象仓储。
        filing_maintenance_repository: filing 维护仓储。
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
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=filing_maintenance_repository,
        user_agent=user_agent,
        sleep_seconds=CNINFO_DEFAULT_SLEEP_SECONDS if sleep_seconds is None else sleep_seconds,
        max_retries=CNINFO_DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
    )
    return CnDownloadAdapter(pipeline=pipeline, source=CN_DOWNLOAD_SOURCE, market="CN")


def build_hk_download_adapter(
    *,
    workspace_root: Path,
    company_repository: CompanyMetaRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    user_agent: Optional[str] = None,
    sleep_seconds: float | None = None,
    max_retries: int | None = None,
) -> CnDownloadAdapter:
    """构建 production HKEXNews 下载 adapter。

    Args:
        workspace_root: Fins 工作区根目录。
        company_repository: 公司元数据仓储。
        source_repository: 源文档仓储。
        processed_repository: processed 仓储。
        blob_repository: 文件对象仓储。
        filing_maintenance_repository: filing 维护仓储。
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
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=filing_maintenance_repository,
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
    "convert_pdf_bytes_to_docling_json_bytes",
]
