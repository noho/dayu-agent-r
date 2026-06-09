"""CN/HK 下载管线与 NEW Fins runtime adapter。

本模块只迁移 OLD CN/HK pipeline 的下载面：download、download_stream、
下载候选过滤、PDF gate、Docling JSON 转换、skip/overwrite 与本地 rebuild。
上传、process、CLI 和 Host 集成不在本 Slice 内。
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
    FinsDownloadResultSummary,
    FinsSourceDownloadAdapter,
    FinsSourceDownloadAdapterRequest,
    FinsSourceDownloadAdapterResult,
)
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
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
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
from dayu.fins.ticker_normalization import try_normalize_ticker

CN_DOWNLOAD_SOURCE: Final[str] = "cninfo"
HK_DOWNLOAD_SOURCE: Final[str] = "hkexnews"
CN_PIPELINE_NAME: Final[str] = "cn"
HK_PIPELINE_NAME: Final[str] = "hk"
_CN_FORMS_ADAPTER_JOINER: Final[str] = ","
_CN_STATUS_DOWNLOADED: Final[str] = "downloaded"


CnPipelineDownloadResult: TypeAlias = dict[str, JsonValue]
"""CN/HK pipeline 下载聚合结果结构。"""


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


async def collect_cn_download_result_from_events(
    events: AsyncIterator[DownloadEvent],
) -> CnPipelineDownloadResult:
    """从 CN/HK 下载事件流收集最终结果。

    Args:
        events: CN/HK 下载事件流。

    Returns:
        ``PIPELINE_COMPLETED`` 事件携带的结果字典。

    Raises:
        RuntimeError: 事件流未产生完成事件，或完成事件缺少结果时抛出。
    """

    async for event in events:
        if event.event_type == DownloadEventType.PIPELINE_COMPLETED:
            result = event.payload.get("result")
            if isinstance(result, Mapping):
                return cast(CnPipelineDownloadResult, dict(result))
            raise RuntimeError("CN/HK 下载完成事件缺少结果 payload")
    raise RuntimeError("CN/HK 下载事件流未产生完成事件")


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
        通过 NEW storage repositories 完成 company/source/blob/reprocess 副作用。
        ``request.rebuild_processed`` 只代表 NEW processed 重处理治理语义，不映射为
        OLD ``CnPipeline.download(rebuild=...)``；OLD ``rebuild`` 仅表示基于本地
        已下载 source 文件重建 meta/manifest。

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
        result = self._pipeline.download(
            ticker=request.normalized_ticker.canonical,
            form_type=_form_type_from_adapter_request(request.form_types),
            start_date=request.filed_after,
            end_date=request.filed_before,
            overwrite=request.overwrite_existing,
            rebuild=False,
            cancel_checker=request.cancellation_checker,
        )
        return FinsSourceDownloadAdapterResult(
            discovered_count=_summary_int(result, "total"),
            persisted_summary=_summary_from_pipeline_result(result),
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
    "convert_pdf_bytes_to_docling_json_bytes",
]
