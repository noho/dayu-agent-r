"""SEC 下载/上传管线与 NEW Fins runtime adapter。

本模块承载 OLD SEC pipeline 的下载面与 Slice 4 迁移的 production
upload facade：download、download_stream、上传 filing/material、下载过滤、
skip/version、6-K 预筛选、SC13 补齐、rejection artifact 持久化与本地
rebuild。process、CLI、Host、tool/provider 装配不在本 Slice 内。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import asyncio
import datetime as dt
from pathlib import Path
from collections.abc import Mapping
from typing import AsyncIterator, Callable, Coroutine, Final, Optional, TypeAlias, TypedDict, cast

from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins._log import Log
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    DownloadRejectionRegistry,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.sec_downloader import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_SLEEP_SECONDS,
    RemoteFileDescriptor,
    SecDownloader,
    StoreDownloadedFile,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadDocumentResult,
    FinsDownloadEffectiveFilters,
    FinsDownloadResultSummary,
    FinsDownloadSource,
    FinsDownloadProviderError,
)
from dayu.fins.ingestion_runtime import (
    FinsDownloadProgressEvent,
    FinsDownloadProgressSink,
    FinsSourceDownloadAdapter,
    FinsSourceDownloadAdapterRequest,
    FinsSourceDownloadAdapterResult,
)
from dayu.fins.pipelines.docling_upload_service import DoclingUploadService, UploadCancellationChecker
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_6k_rules import (
    _has_6k_exhibit_candidate,
    _has_6k_xbrl_instance,
    _select_6k_target_name,
    _select_best_positive_6k_candidate,
)
from dayu.fins.pipelines.sec_company_meta import (
    extract_sec_ticker_aliases,
    merge_ticker_aliases,
    upsert_company_meta as _upsert_company_meta_impl,
)
from dayu.fins.pipelines.sec_download_diagnostics import warn_insufficient_filings, warn_xbrl_missing_filings
from dayu.fins.pipelines.sec_download_event_mapping import (
    DownloadFileResult,
    build_download_filing_event_payload,
    build_file_result_from_downloader_event,
    summarize_failed_download_file_reasons,
)
from dayu.fins.pipelines.sec_download_filing_workflow import (
    SecDownloadFilingWorkflowHost as _SecDownloadFilingWorkflowHost,
    run_download_single_filing_stream as _run_download_single_filing_stream,
)
from dayu.fins.pipelines.sec_download_persistence import (
    build_file_entries as _build_file_entries_impl,
    build_store_file as _build_store_file_impl,
    persist_rejected_filing_artifact as _persist_rejected_filing_artifact_impl,
)
from dayu.fins.pipelines.sec_download_state import (
    _has_same_file_name_set,
    _index_file_entries,
    _is_rejected as _is_rejected_impl,
    _load_rejection_registry as _load_rejection_registry_impl,
    _read_sec_cache_async,
    _record_rejection as _record_rejection_impl,
    _remote_files_equivalent_to_previous_meta,
    _save_rejection_registry as _save_rejection_registry_impl,
    _write_sec_cache_async,
    has_current_download_version,
)
from dayu.fins.pipelines.sec_download_workflow import (
    SecDownloadWorkflowHost as _SecDownloadWorkflowHost,
    run_download_stream_impl as _run_download_stream_impl,
)
from dayu.fins.pipelines.sec_filing_collection import (
    FilingRecord,
    classify_6k_remote_candidates,
    collect_filenums_from_table,
    collect_filings_from_table,
)
from dayu.fins.pipelines.sec_fiscal_fields import _resolve_download_fiscal_fields
from dayu.fins.pipelines.sec_form_utils import (
    DEFAULT_FORMS_US,
    LOOKBACK_GRACE_DAYS,
    LOOKBACK_YEARS_BY_FORM,
    expand_form_aliases,
    increment_document_version,
    parse_date,
    parse_sec_pipeline_form,
    split_form_input,
    subtract_years,
)
from dayu.fins.pipelines.sec_rebuild_workflow import (
    SecRebuildWorkflowHost as _SecRebuildWorkflowHost,
    rebuild_download_artifacts as _rebuild_download_artifacts_impl,
)
from dayu.fins.pipelines.sec_safe_meta_access import (
    resolve_document_version as _resolve_document_version_impl,
    safe_get_company_meta as _safe_get_company_meta_impl,
    safe_get_document_meta as _safe_get_document_meta_impl,
    safe_get_filing_source_meta as _safe_get_filing_source_meta_impl,
    safe_get_processed_meta as _safe_get_processed_meta_impl,
)
from dayu.fins.pipelines.sec_sc13_filtering import (
    Sc13DirectionDecision,
    SecSc13WorkflowHost as _SecSc13WorkflowHost,
    extend_with_browse_edgar_sc13 as _extend_with_browse_edgar_sc13_impl,
    filter_sc13_by_direction as _filter_sc13_by_direction_impl,
    keep_latest_sc13_per_filer as _keep_latest_sc13_per_filer_impl,
    retry_sc13_if_empty as _retry_sc13_if_empty_impl,
    should_keep_sc13_direction as _should_keep_sc13_direction_impl,
    should_warn_missing_sc13,
)
from dayu.fins.pipelines.sec_upload_workflow import (
    collect_upload_result_from_events as _collect_upload_result_from_events,
    run_upload_filing_stream as _run_upload_filing_stream,
    run_upload_material_stream as _run_upload_material_stream,
)
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

SEC_PIPELINE_DOWNLOAD_VERSION: Final[str] = "sec_pipeline_download_v1.2.0"
SEC_DOWNLOAD_SOURCE: Final[str] = "sec"
_SEC_FORMS_ADAPTER_JOINER: Final[str] = ","
_SEC_STATUS_DOWNLOADED: Final[str] = "downloaded"
_SEC_STATUS_REJECTED: Final[str] = "rejected"
_SEC_STATUS_SKIPPED: Final[str] = "skipped"
_SEC_STATUS_FAILED: Final[str] = "failed"
_SEC_REASON_6K_FILTERED: Final[str] = "6k_filtered"
_ADAPTER_PROGRESS_FILING_STARTED: Final[str] = "download.filing_started"
_ADAPTER_PROGRESS_FILING_COMPLETED: Final[str] = "download.filing_completed"
_ADAPTER_PROGRESS_FILING_SKIPPED: Final[str] = "download.filing_skipped"
_ADAPTER_PROGRESS_FILING_FAILED: Final[str] = "download.filing_failed"


class SecPipelineSummary(TypedDict):
    """SEC pipeline 下载结果 summary 结构。"""

    total: int
    downloaded: int
    skipped: int
    rejected: int
    failed: int
    elapsed_ms: int
    reused_downloads: int
    converted: int


class SecPipelineDownloadResult(TypedDict):
    """SEC pipeline 下载聚合结果结构。"""

    pipeline: str
    action: str
    status: str
    ticker: str
    market_profile: dict[str, JsonValue]
    filters: dict[str, JsonValue]
    warnings: list[str]
    filings: list[dict[str, JsonValue]]
    summary: SecPipelineSummary


SecPipelineUploadResult: TypeAlias = dict[str, JsonValue]
"""SEC pipeline 上传聚合结果结构。"""


def _run_async_upload_sync(
    coro: Coroutine[None, None, SecPipelineUploadResult],
) -> SecPipelineUploadResult:
    """在同步上下文执行 SEC 上传协程。

    Args:
        coro: 上传协程。

    Returns:
        SEC 上传聚合结果。

    Raises:
        RuntimeError: 当前线程已有事件循环时抛出。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("检测到正在运行的事件循环，请改用 stream 异步接口")


def _json_mapping(value: JsonValue | None) -> dict[str, JsonValue]:
    """将 JSON 值收窄为字典。

    Args:
        value: 原始 JSON 值。

    Returns:
        字典；非 mapping 返回空字典。

    Raises:
        无。
    """

    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _json_list(value: JsonValue | None) -> list[JsonValue]:
    """将 JSON 值收窄为列表。

    Args:
        value: 原始 JSON 值。

    Returns:
        列表；非列表返回空列表。

    Raises:
        无。
    """

    if isinstance(value, list):
        return value
    return []


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
        raise ValueError(f"SEC 下载 {field_name} 不是整数")
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SEC 下载 {field_name} 不是整数") from exc
    if parsed < 0:
        raise ValueError(f"SEC 下载 {field_name} 不能为负数")
    return parsed


def _is_rejected(
    registry: DownloadRejectionRegistry,
    document_id: str,
    overwrite: bool,
) -> bool:
    """判断 document_id 是否命中拒绝注册表。

    Args:
        registry: 拒绝注册表。
        document_id: 文档 ID。
        overwrite: 是否覆盖模式。

    Returns:
        命中返回 ``True``。

    Raises:
        无。
    """

    return _is_rejected_impl(
        registry=registry,
        document_id=document_id,
        overwrite=overwrite,
        download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
    )


def _record_rejection(
    registry: DownloadRejectionRegistry,
    document_id: str,
    reason: str,
    category: str,
    form_type: str,
    filing_date: str,
) -> None:
    """向拒绝注册表写入一条拒绝记录。

    Args:
        registry: 拒绝注册表（就地修改）。
        document_id: 文档 ID。
        reason: 拒绝原因标识。
        category: 筛选分类标签。
        form_type: 表单类型。
        filing_date: 申报日期。

    Returns:
        无。

    Raises:
        无。
    """

    _record_rejection_impl(
        registry=registry,
        document_id=document_id,
        reason=reason,
        category=category,
        form_type=form_type,
        filing_date=filing_date,
        download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
    )


def _run_async_download_sync(coro: Coroutine[None, None, SecPipelineDownloadResult]) -> SecPipelineDownloadResult:
    """在同步上下文执行下载协程。

    Args:
        coro: 下载协程对象。

    Returns:
        下载结果字典。

    Raises:
        RuntimeError: 当前线程已有事件循环时抛出。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("检测到正在运行的事件循环，请改用 stream 异步接口")


async def collect_download_result_from_events(
    events: AsyncIterator[DownloadEvent],
    *,
    progress_sink: FinsDownloadProgressSink | None = None,
) -> SecPipelineDownloadResult:
    """从下载事件流收集最终结果。

    Args:
        events: SEC 下载事件流。
        progress_sink: 可选 runtime 进度回调。

    Returns:
        ``PIPELINE_COMPLETED`` 事件携带的结果字典。

    Raises:
        RuntimeError: 事件流未产生完成事件时抛出。
    """

    async for event in events:
        _emit_adapter_download_progress(event, progress_sink)
        if event.event_type == DownloadEventType.PIPELINE_COMPLETED:
            result = event.payload.get("result")
            if isinstance(result, dict):
                return cast(SecPipelineDownloadResult, result)
            raise RuntimeError("SEC 下载完成事件缺少结果 payload")
    raise RuntimeError("SEC 下载事件流未产生完成事件")


def _emit_adapter_download_progress(
    event: DownloadEvent,
    progress_sink: FinsDownloadProgressSink | None,
) -> None:
    """把 SEC pipeline filing 事件投影为 runtime 下载进度。

    Args:
        event: SEC pipeline 下载事件。
        progress_sink: runtime adapter 进度回调。

    Returns:
        无。

    Raises:
        ValueError: 回调拒绝非法进度字段时抛出。
    """

    if progress_sink is None:
        return
    if event.event_type == DownloadEventType.FILING_STARTED:
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_FILING_STARTED,
                message="开始下载",
                document_id=event.document_id,
            )
        )
        return
    if event.event_type == DownloadEventType.FILING_COMPLETED:
        status = _payload_text(event.payload, "status")
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_FILING_SKIPPED if status == "skipped" else _ADAPTER_PROGRESS_FILING_COMPLETED,
                message="跳过下载" if status == "skipped" else "完成下载",
                document_id=event.document_id,
            )
        )
        return
    if event.event_type == DownloadEventType.FILING_FAILED:
        progress_sink(
            FinsDownloadProgressEvent(
                stage=_ADAPTER_PROGRESS_FILING_FAILED,
                message="下载失败",
                document_id=event.document_id,
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


class SecPipeline:
    """SEC 下载管线 facade。

    该类承载 OLD SEC 下载工作流需要的最小宿主边界，并通过 NEW storage
    repositories 写入公司元数据、source 文件、rejected artifact 与
    processed reprocess 标记。
    """

    PIPELINE_NAME: Final[str] = "sec"
    MODULE: Final[str] = "FINS.SEC_PIPELINE"

    def __init__(
        self,
        *,
        processor_registry: ProcessorRegistry,
        workspace_root: Optional[Path] = None,
        downloader: Optional[SecDownloader] = None,
        company_repository: CompanyMetaRepositoryProtocol | None = None,
        source_repository: SourceDocumentRepositoryProtocol | None = None,
        processed_repository: ProcessedDocumentRepositoryProtocol | None = None,
        blob_repository: DocumentBlobRepositoryProtocol | None = None,
        filing_maintenance_repository: FilingMaintenanceRepositoryProtocol | None = None,
        batching_repository: BatchingRepositoryProtocol | None = None,
        user_agent: Optional[str] = None,
        sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """初始化 SEC 下载管线。

        Args:
            processor_registry: Fins 文档处理器注册表。
            workspace_root: Fins 工作区根目录。
            downloader: 可选 SEC 下载器实例。
            company_repository: 可选公司元数据仓储。
            source_repository: 可选源文档仓储。
            processed_repository: 可选 processed 文档仓储。
            blob_repository: 可选文件对象仓储。
            filing_maintenance_repository: 可选 filing 维护仓储。
            batching_repository: 可选 batch lifecycle 仓储。
            user_agent: SEC User-Agent。
            sleep_seconds: SEC 请求间隔秒数。
            max_retries: SEC 下载重试次数。

        Returns:
            无。

        Raises:
            ValueError: processor_registry 缺失时抛出。
            OSError: 默认文件系统仓储初始化失败时抛出。
        """

        if processor_registry is None:
            raise ValueError("processor_registry 必须由调用方显式传入")
        self._workspace_root = (workspace_root or Path.cwd()).resolve()
        self._downloader = downloader or SecDownloader(
            workspace_root=self._workspace_root,
            user_agent=user_agent,
        )
        repository_set = build_fs_repository_set(workspace_root=self._workspace_root)
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
        self._processor_registry = processor_registry
        self._user_agent = user_agent
        self._sleep_seconds = sleep_seconds
        self._max_retries = max_retries
        self._upload_service = DoclingUploadService(
            source_repository=self._source_repository,
            blob_repository=self._blob_repository,
        )

    @property
    def source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回 SEC pipeline 使用的源文档仓储。

        Args:
            无。

        Returns:
            relative locator 查询所属的源文档仓储。

        Raises:
            无。
        """

        return self._source_repository

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
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> SecPipelineDownloadResult:
        """执行 SEC 下载并同步返回聚合结果。

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
            OLD SEC 下载结果字典。

        Raises:
            RuntimeError: 当前线程已有事件循环时抛出。
            ValueError: ticker 或过滤参数非法时抛出。
        """

        return _run_async_download_sync(
            collect_download_result_from_events(
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
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloadEvent]:
        """执行 SEC 下载并流式产出事件。

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

        async for event in self.download_stream_impl(
            ticker=ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            rebuild=rebuild,
            ticker_aliases=ticker_aliases,
            start_is_explicit=start_is_explicit,
            cancel_checker=cancel_checker,
        ):
            yield event

    async def download_stream_impl(
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
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloadEvent]:
        """执行 OLD SEC 下载主工作流。

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

        async for event in _run_download_stream_impl(
            cast(_SecDownloadWorkflowHost, self),
            ticker=ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            rebuild=rebuild,
            ticker_aliases=ticker_aliases,
            start_is_explicit=start_is_explicit,
            cancel_checker=cancel_checker,
            parse_date=parse_date,
            extract_sec_ticker_aliases=extract_sec_ticker_aliases,
            merge_ticker_aliases=merge_ticker_aliases,
            load_rejection_registry=_load_rejection_registry_impl,
            save_rejection_registry=_save_rejection_registry_impl,
            is_rejected=_is_rejected,
            record_rejection=_record_rejection,
            should_warn_missing_sc13=should_warn_missing_sc13,
            warn_insufficient_filings=warn_insufficient_filings,
            warn_xbrl_missing_filings=warn_xbrl_missing_filings,
            build_download_filing_event_payload=build_download_filing_event_payload,
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
    ) -> SecPipelineUploadResult:
        """执行 SEC 财报上传并同步返回聚合结果。

        Args:
            ticker: 股票代码。
            action: 可选动作类型。
            files: 上传文件列表。
            fiscal_year: 财年。
            fiscal_period: 财期。
            amended: 是否修订版。
            filing_date: 可选 filing 日期。
            report_date: 可选 report 日期。
            company_id: 可选兼容字段。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            overwrite: 是否覆盖。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            上传结果字典。

        Raises:
            RuntimeError: 当前线程已有事件循环时抛出。
        """

        return _run_async_upload_sync(
            _collect_upload_result_from_events(
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
    ) -> AsyncIterator["UploadFilingEvent"]:
        """执行流式 SEC 财报上传。

        Args:
            ticker: 股票代码。
            action: 可选动作类型。
            files: 上传文件列表。
            fiscal_year: 财年。
            fiscal_period: 财期。
            amended: 是否修订版。
            filing_date: 可选 filing 日期。
            report_date: 可选 report 日期。
            company_id: 可选兼容字段。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            overwrite: 是否覆盖。
            cancellation_checker: 可选协作式取消检查器。

        Yields:
            上传过程事件。

        Raises:
            RuntimeError: 上传执行失败时抛出。
        """

        async for event in _run_upload_filing_stream(
            self,
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
        ):
            yield event

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
    ) -> SecPipelineUploadResult:
        """执行 SEC 材料上传并同步返回聚合结果。

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
            filing_date: 可选 filing 日期。
            report_date: 可选 report 日期。
            company_id: 可选兼容字段。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            overwrite: 是否覆盖。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            上传结果字典。

        Raises:
            RuntimeError: 当前线程已有事件循环时抛出。
        """

        return _run_async_upload_sync(
            _collect_upload_result_from_events(
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
    ) -> AsyncIterator["UploadMaterialEvent"]:
        """执行流式 SEC 材料上传。

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
            filing_date: 可选 filing 日期。
            report_date: 可选 report 日期。
            company_id: 可选兼容字段。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            overwrite: 是否覆盖。
            cancellation_checker: 可选协作式取消检查器。

        Yields:
            上传过程事件。

        Raises:
            ValueError: 市场类型非法时抛出。
            RuntimeError: 上传执行失败时抛出。
        """

        async for event in _run_upload_material_stream(
            self,
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
        ):
            yield event

    def _rebuild_download_artifacts(
        self,
        *,
        ticker: str,
        form_type: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        overwrite: bool,
    ) -> dict[str, JsonValue]:
        """基于本地已下载 filings 重建 meta。

        Args:
            ticker: 标准化股票代码。
            form_type: 可选表单过滤。
            start_date: 可选开始日期。
            end_date: 可选结束日期。
            overwrite: 是否覆盖。

        Returns:
            下载结果字典。

        Raises:
            ValueError: 过滤条件非法时抛出。
        """

        return _rebuild_download_artifacts_impl(
            cast(_SecRebuildWorkflowHost, self),
            ticker=ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            pipeline_download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
            expand_form_aliases=expand_form_aliases,
            split_form_input=split_form_input,
            parse_date=parse_date,
            parse_sec_form=parse_sec_pipeline_form,
        )

    def _log_filing_download_result(self, ticker: str, filing_result: dict[str, JsonValue]) -> None:
        """记录单个 filing 下载结果。

        Args:
            ticker: 股票代码。
            filing_result: 单 filing 结果。

        Returns:
            无。

        Raises:
            无。
        """

        document_id = str(filing_result.get("document_id", ""))
        status = str(filing_result.get("status", "unknown"))
        form_type = str(filing_result.get("form_type", ""))
        filing_date = filing_result.get("filing_date")
        report_date = filing_result.get("report_date")
        downloaded_files = _json_int(filing_result.get("downloaded_files"), "downloaded_files")
        skipped_files = _json_int(filing_result.get("skipped_files"), "skipped_files")
        failed_files = filing_result.get("failed_files")
        failed_count = len(failed_files) if isinstance(failed_files, list) else 0
        skip_reason = filing_result.get("skip_reason")
        reason_code = filing_result.get("reason_code")
        reason_message = filing_result.get("reason_message")
        filter_category = filing_result.get("filter_category")
        Log.info(
            (
                "filing 下载完成: "
                f"ticker={ticker} document_id={document_id} status={status} form={form_type} "
                f"filing_date={filing_date} report_date={report_date} "
                f"downloaded_files={downloaded_files} skipped_files={skipped_files} "
                f"failed_files={failed_count} skip_reason={skip_reason} "
                f"reason_code={reason_code} reason_message={reason_message} "
                f"filter_category={filter_category}"
            ),
            module=self.MODULE,
        )

    async def _download_single_filing_stream(
        self,
        ticker: str,
        cik: str,
        filing: FilingRecord,
        overwrite: bool,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloadEvent]:
        """下载单个 SEC filing 并产出事件。

        Args:
            ticker: 股票代码。
            cik: CIK。
            filing: filing 记录。
            overwrite: 是否覆盖。
            rejection_registry: 拒绝注册表。
            cancel_checker: 可选协作式取消检查器。

        Yields:
            文件级和 filing 级事件。

        Raises:
            RuntimeError: 关键路径失败时抛出。
        """

        async for event in _run_download_single_filing_stream(
            cast(_SecDownloadFilingWorkflowHost, self),
            ticker=ticker,
            cik=cik,
            filing=filing,
            overwrite=overwrite,
            rejection_registry=rejection_registry,
            cancel_checker=cancel_checker,
            is_rejected=_is_rejected,
            record_rejection=_record_rejection,
            build_download_filing_event_payload=build_download_filing_event_payload,
            build_file_result_from_downloader_event=build_file_result_from_downloader_event,
            summarize_failed_download_file_reasons=summarize_failed_download_file_reasons,
            has_same_file_name_set=lambda remote_files, existing_files: _has_same_file_name_set(
                remote_files=remote_files,
                existing_files=existing_files,
            ),
            resolve_download_fiscal_fields=_resolve_download_fiscal_fields,
            index_file_entries=_index_file_entries,
            download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
        ):
            yield event

    def _resolve_form_windows(
        self,
        form_type: Optional[str],
        start_date: Optional[str],
        end_date: dt.date,
    ) -> dict[str, dt.date]:
        """计算 form 到起始日期的映射。

        Args:
            form_type: 可选表单过滤。
            start_date: 可选开始日期。
            end_date: 已确定结束日期。

        Returns:
            form 到起始日期映射。

        Raises:
            ValueError: 过滤参数非法时抛出。
        """

        if form_type:
            explicit_forms = expand_form_aliases(split_form_input(form_type))
        else:
            explicit_forms = expand_form_aliases(list(DEFAULT_FORMS_US))
        if start_date:
            lower_bound = parse_date(start_date, is_end=False)
            return {item: lower_bound for item in explicit_forms}
        grace = dt.timedelta(days=LOOKBACK_GRACE_DAYS)
        result: dict[str, dt.date] = {}
        for item in explicit_forms:
            years = LOOKBACK_YEARS_BY_FORM.get(item, 1)
            result[item] = subtract_years(end_date, years) - grace
        return result

    async def _filter_filings(
        self,
        ticker: str,
        submissions: dict[str, JsonValue],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Sc13DirectionDecision]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[list[FilingRecord], set[str]]:
        """过滤 filings 并收集 filenum。

        Args:
            ticker: 股票代码。
            submissions: SEC submissions 响应。
            form_windows: form 到起始日期映射。
            end_date: 下载结束日期。
            target_cik: 目标 CIK。
            sc13_direction_cache: SC13 方向缓存。
            rejection_registry: 拒绝注册表。
            overwrite: 是否覆盖。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            过滤后的 filing 列表与 filenum 集合。

        Raises:
            ValueError: submissions 结构非法时抛出。
        """

        records: dict[str, FilingRecord] = {}
        filenums: set[str] = set()
        filings_payload = _json_mapping(submissions.get("filings"))
        recent = _json_mapping(filings_payload.get("recent"))
        collect_filings_from_table(
            records=records,
            table=recent,
            form_windows=form_windows,
            end_date=end_date,
        )
        collect_filenums_from_table(filenums, recent)
        history_files = _json_list(filings_payload.get("files"))
        for history_file in history_files:
            if not isinstance(history_file, dict):
                continue
            filename = str(history_file.get("name", "")).strip()
            if not filename:
                continue
            cache_key = filename.replace(".json", "")
            cached_data = await _read_sec_cache_async(self._workspace_root, "submissions", cache_key)
            if isinstance(cached_data, dict):
                history_json = cached_data
            else:
                history_url = f"https://data.sec.gov/submissions/{filename}"
                history_json = await self._downloader.fetch_json(
                    history_url,
                    cancellation_checker=cancel_checker,
                )
                await _write_sec_cache_async(self._workspace_root, "submissions", cache_key, history_json)
            collect_filings_from_table(
                records=records,
                table=history_json,
                form_windows=form_windows,
                end_date=end_date,
            )
            collect_filenums_from_table(filenums, history_json)
        sorted_records = sorted(
            records.values(),
            key=lambda item: (item.filing_date, item.form_type, item.accession_number),
        )
        direction_result = await _filter_sc13_by_direction_impl(
            cast(_SecSc13WorkflowHost, self),
            ticker=ticker,
            filings=sorted_records,
            target_cik=target_cik,
            archive_cik=target_cik,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )
        direction_filtered_records = cast(list[FilingRecord], list(direction_result.filings))
        deduplicated_records = cast(
            list[FilingRecord],
            _keep_latest_sc13_per_filer_impl(tuple(direction_filtered_records)),
        )
        Log.debug(
            (
                "过滤后 filings 数量: "
                f"原始={len(sorted_records)} 方向过滤后={len(direction_filtered_records)} "
                f"去重后={len(deduplicated_records)}"
            ),
            module=self.MODULE,
        )
        return deduplicated_records, filenums

    async def _extend_with_browse_edgar_sc13(
        self,
        ticker: str,
        filings: list[FilingRecord],
        filenums: set[str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Sc13DirectionDecision]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> list[FilingRecord]:
        """通过 browse-edgar 补齐 SC13 filing。

        Args:
            ticker: 股票代码。
            filings: 当前 filings。
            filenums: submissions 中收集的 filenum。
            form_windows: form 到起始日期映射。
            end_date: 下载结束日期。
            target_cik: 目标 CIK。
            sc13_direction_cache: SC13 方向缓存。
            rejection_registry: 拒绝注册表。
            overwrite: 是否覆盖。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            合并后的 filings。

        Raises:
            RuntimeError: browse-edgar 执行失败时由底层抛出。
        """

        return cast(
            list[FilingRecord],
            await _extend_with_browse_edgar_sc13_impl(
                cast(_SecSc13WorkflowHost, self),
                ticker=ticker,
                filings=filings,
                filenums=filenums,
                form_windows=form_windows,
                end_date=end_date,
                target_cik=target_cik,
                parse_date=parse_date,
                create_filing_record=lambda form_type, filing_date, report_date, accession_number, primary_document, filer_key: (
                    FilingRecord(
                        form_type=form_type,
                        filing_date=filing_date,
                        report_date=report_date,
                        accession_number=accession_number,
                        primary_document=primary_document,
                        filer_key=filer_key,
                    )
                ),
                sc13_direction_cache=sc13_direction_cache,
                rejection_registry=rejection_registry,
                overwrite=overwrite,
                cancel_checker=cancel_checker,
            ),
        )

    async def _retry_sc13_if_empty(
        self,
        ticker: str,
        filings: list[FilingRecord],
        filenums: set[str],
        submissions: dict[str, JsonValue],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        start_is_explicit: bool,
        sc13_direction_cache: Optional[dict[str, Sc13DirectionDecision]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> list[FilingRecord]:
        """SC13 为空时执行渐进式回溯。

        Args:
            ticker: 股票代码。
            filings: 当前 filings。
            filenums: submissions 中收集的 filenum。
            submissions: SEC submissions 响应。
            form_windows: form 到起始日期映射。
            end_date: 下载结束日期。
            target_cik: 目标 CIK。
            start_is_explicit: 起始日期是否由调用方显式提供。
            sc13_direction_cache: SC13 方向缓存。
            rejection_registry: 拒绝注册表。
            overwrite: 是否覆盖。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            可能补齐后的 filings。

        Raises:
            RuntimeError: browse-edgar 执行失败时由底层抛出。
        """

        return cast(
            list[FilingRecord],
            await _retry_sc13_if_empty_impl(
                cast(_SecSc13WorkflowHost, self),
                ticker=ticker,
                filings=filings,
                filenums=filenums,
                submissions=submissions,
                form_windows=form_windows,
                end_date=end_date,
                target_cik=target_cik,
                start_is_explicit=start_is_explicit,
                sc13_direction_cache=sc13_direction_cache,
                rejection_registry=rejection_registry,
                overwrite=overwrite,
                cancel_checker=cancel_checker,
            ),
        )

    async def _should_keep_sc13_direction(
        self,
        ticker: str,
        filing: FilingRecord,
        archive_cik: str,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Sc13DirectionDecision]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Sc13DirectionDecision:
        """判断单条 SC13 是否满足别人持股当前 ticker 的方向。

        Args:
            ticker: 股票代码。
            filing: filing 记录。
            archive_cik: 归档路径 CIK。
            target_cik: 目标 CIK。
            sc13_direction_cache: SC13 方向缓存。
            rejection_registry: 拒绝注册表。
            overwrite: 是否覆盖。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            exact accession 对应的 pure typed direction decision。

        Raises:
            RuntimeError: 角色解析失败时由底层抛出。
        """

        return await _should_keep_sc13_direction_impl(
            cast(_SecSc13WorkflowHost, self),
            ticker=ticker,
            filing=filing,
            archive_cik=archive_cik,
            target_cik=target_cik,
            download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )

    def _can_skip_fast(self, previous_meta: Optional[dict[str, JsonValue]], overwrite: bool) -> Optional[str]:
        """仅基于本地 meta 判断是否可快速跳过。

        Args:
            previous_meta: 旧 meta。
            overwrite: 是否覆盖。

        Returns:
            跳过原因码或 ``None``。

        Raises:
            无。
        """

        if overwrite or previous_meta is None:
            return None
        if not has_current_download_version(previous_meta, SEC_PIPELINE_DOWNLOAD_VERSION):
            return None
        previous_fingerprint = str(previous_meta.get("source_fingerprint", "")).strip()
        return "already_downloaded_complete" if previous_fingerprint else None

    def _can_skip(
        self,
        previous_meta: Optional[dict[str, JsonValue]],
        source_fingerprint: str,
        overwrite: bool,
        remote_files: Optional[list[RemoteFileDescriptor]] = None,
    ) -> Optional[str]:
        """判断是否可跳过下载。

        Args:
            previous_meta: 旧 meta。
            source_fingerprint: 本次远端指纹。
            overwrite: 是否覆盖。
            remote_files: 本次远端文件。

        Returns:
            跳过原因码或 ``None``。

        Raises:
            无。
        """

        if overwrite or previous_meta is None:
            return None
        if not has_current_download_version(previous_meta, SEC_PIPELINE_DOWNLOAD_VERSION):
            return None
        previous_fingerprint = str(previous_meta.get("source_fingerprint", "")).strip()
        if previous_fingerprint and previous_fingerprint == source_fingerprint:
            return "source_fingerprint_matched"
        if _remote_files_equivalent_to_previous_meta(previous_meta=previous_meta, remote_files=remote_files):
            return "remote_files_equivalent"
        return None

    def _resolve_document_version(
        self,
        previous_meta: Optional[dict[str, JsonValue]],
        source_fingerprint: str,
    ) -> str:
        """计算下载文档版本。

        Args:
            previous_meta: 旧 meta。
            source_fingerprint: 本次来源指纹。

        Returns:
            文档版本。

        Raises:
            无。
        """

        return _resolve_document_version_impl(
            previous_meta,
            source_fingerprint,
            increment_document_version=increment_document_version,
        )

    def _safe_get_company_meta(self, ticker: str) -> Optional[CompanyMeta]:
        """安全读取公司元数据。

        Args:
            ticker: 股票代码。

        Returns:
            公司元数据；不存在时为 ``None``。

        Raises:
            OSError: 仓储读取失败时可由底层抛出。
        """

        return _safe_get_company_meta_impl(self._company_repository, ticker=ticker)

    def _safe_get_document_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> Optional[dict[str, JsonValue]]:
        """安全读取源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 源文档类型。

        Returns:
            meta 字典；不存在时为 ``None``。

        Raises:
            OSError: 仓储读取失败时可由底层抛出。
        """

        return _safe_get_document_meta_impl(
            self._source_repository,
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind,
        )

    def _safe_get_filing_source_meta(self, ticker: str, document_id: str) -> Optional[dict[str, JsonValue]]:
        """安全读取 filing source meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            filing meta；不存在时为 ``None``。

        Raises:
            OSError: 仓储读取失败时可由底层抛出。
        """

        return _safe_get_filing_source_meta_impl(
            self._source_repository,
            ticker=ticker,
            document_id=document_id,
        )

    def _safe_get_processed_meta(self, ticker: str, document_id: str) -> Optional[dict[str, JsonValue]]:
        """安全读取 processed meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed meta；不存在时为 ``None``。

        Raises:
            OSError: 仓储读取失败时可由底层抛出。
        """

        return _safe_get_processed_meta_impl(
            self._processed_repository,
            ticker=ticker,
            document_id=document_id,
        )

    def _build_file_entries(
        self,
        file_results: list[DownloadFileResult],
        previous_files: dict[str, dict[str, JsonValue]],
    ) -> list[dict[str, JsonValue]]:
        """构建 source meta 的 files 条目。

        Args:
            file_results: 下载文件结果。
            previous_files: 旧文件条目映射。

        Returns:
            files 条目列表。

        Raises:
            无。
        """

        return _build_file_entries_impl(file_results=file_results, previous_files=previous_files)

    def _build_store_file(
        self,
        source_handle: SourceHandle,
        *,
        payload_sink: dict[str, bytes] | None,
    ) -> StoreDownloadedFile:
        """构建 source 文件写入回调。

        Args:
            source_handle: 源文档句柄。
            payload_sink: 可选单 filing payload 映射；不携带 batch authority。

        Returns:
            文件写入回调。

        Raises:
            无。
        """

        return _build_store_file_impl(
            self._blob_repository,
            source_handle,
            payload_sink,
        )

    async def _persist_rejected_filing_artifact(
        self,
        *,
        ticker: str,
        cik: str,
        filing: FilingRecord,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        rejection_reason: str,
        rejection_category: str,
        selected_primary_document: str,
        source_fingerprint: str,
        registry_after: DownloadRejectionRegistry,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, Optional[str]]:
        """下载并保存 rejected filing artifact。

        Args:
            ticker: 股票代码。
            cik: 公司 CIK。
            filing: filing 记录。
            remote_files: 远端文件列表。
            overwrite: 是否覆盖。
            rejection_reason: 拒绝原因。
            rejection_category: 拒绝分类。
            selected_primary_document: 当前规则选中的主文件。
            source_fingerprint: 来源指纹。
            registry_after: 与 artifact 同 batch 发布的完整 registry 真值。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            成功标记与失败原因。

        Raises:
            无。底层错误会转换为失败原因。
        """

        return await _persist_rejected_filing_artifact_impl(
            ticker=ticker,
            cik=cik,
            filing=filing,
            remote_files=remote_files,
            overwrite=overwrite,
            rejection_reason=rejection_reason,
            rejection_category=rejection_category,
            selected_primary_document=selected_primary_document,
            source_fingerprint=source_fingerprint,
            classification_version=SEC_PIPELINE_DOWNLOAD_VERSION,
            batching_repository=self._batching_repository,
            filing_maintenance_repository=self._filing_maintenance_repository,
            downloader=self._downloader,
            registry_after=registry_after,
            build_file_result_from_downloader_event=build_file_result_from_downloader_event,
            summarize_failed_download_file_reasons=summarize_failed_download_file_reasons,
            cancellation_checker=cancel_checker,
        )

    async def _precheck_6k_filter(
        self,
        remote_files: list[RemoteFileDescriptor],
        primary_document: str,
        ticker: str,
        document_id: str,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str, str]:
        """预先应用 6-K 筛选规则。

        Args:
            remote_files: 远端文件描述列表。
            primary_document: 主文件名。
            ticker: 股票代码。
            document_id: 文档 ID。
            cancel_checker: 可选协作式取消检查器。

        Returns:
            是否保留、分类标签、选中主文件名。

        Raises:
            无。预下载失败按 OLD 语义转换为过滤分类。
        """

        has_xbrl_instance = _has_6k_xbrl_instance(remote_files)
        if has_xbrl_instance:
            try:
                selected_name = _select_6k_target_name(
                    [{"name": item.name, "sec_document_type": item.sec_document_type} for item in remote_files],
                    primary_document,
                )
            except ValueError:
                return True, "XBRL_AVAILABLE", primary_document
            return True, "XBRL_AVAILABLE", selected_name

        has_exhibit_candidate = _has_6k_exhibit_candidate(remote_files)
        selected_name = primary_document
        if has_exhibit_candidate:
            try:
                selected_name = _select_6k_target_name(
                    [{"name": item.name, "sec_document_type": item.sec_document_type} for item in remote_files],
                    primary_document,
                )
            except ValueError:
                return False, "NO_MATCH", ""

        if not primary_document and all(item.name != selected_name for item in remote_files):
            return False, "NO_MATCH", selected_name

        try:
            candidate_diagnoses = await classify_6k_remote_candidates(
                remote_files,
                primary_document,
                self._downloader,
                max_lines=120,
                cancellation_checker=cancel_checker,
            )
        except FinsDownloadProviderError as exc:
            Log.warn(
                f"6-K 预下载来源请求失败: transport_category={exc.transport_category.value}",
                module=self.MODULE,
            )
            return False, "DOWNLOAD_FAILED", selected_name

        if not candidate_diagnoses:
            return False, "NO_MATCH", selected_name
        positive_candidate = _select_best_positive_6k_candidate(candidate_diagnoses)
        if positive_candidate is not None:
            return True, positive_candidate.classification, positive_candidate.filename
        if not has_exhibit_candidate:
            return False, "NO_EX99_OR_XBRL", selected_name
        primary_diagnosis = next((item for item in candidate_diagnoses if item.is_primary_document), None)
        if primary_diagnosis is not None and primary_diagnosis.classification == "EXCLUDE_NON_QUARTERLY":
            return False, "EXCLUDE_NON_QUARTERLY", selected_name
        if any(item.classification == "EXCLUDE_NON_QUARTERLY" for item in candidate_diagnoses):
            return False, "EXCLUDE_NON_QUARTERLY", selected_name
        return False, "NO_MATCH", selected_name

    def _upsert_company_meta(
        self,
        ticker: str,
        company_id: str,
        company_name: str,
        ticker_aliases: Optional[list[str]] = None,
        *,
        batch: BatchToken,
    ) -> None:
        """写入公司元数据。

        Args:
            ticker: 股票代码。
            company_id: 公司 ID。
            company_name: 公司名称。
            ticker_aliases: 可选 ticker alias。
            batch: caller 显式传入的 batch capability。

        Returns:
            无。

        Raises:
            OSError: 仓储写入失败时由底层抛出。
        """

        _upsert_company_meta_impl(
            repository=self._company_repository,
            ticker=ticker,
            company_id=company_id,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
            batch=batch,
        )

    def _build_result(self, action: str, **payload: JsonValue) -> dict[str, JsonValue]:
        """构建统一下载结果。

        Args:
            action: 动作名称。
            **payload: 动作负载。

        Returns:
            结果字典。

        Raises:
            无。
        """

        return {
            "pipeline": self.PIPELINE_NAME,
            "action": action,
            "status": payload.pop("status", "ok"),
            **payload,
        }


class SecDownloadAdapter(FinsSourceDownloadAdapter):
    """NEW Fins runtime 使用的 SEC 同步下载 adapter。"""

    def __init__(
        self,
        *,
        pipeline: SecPipeline,
    ) -> None:
        """初始化 adapter。

        Args:
            pipeline: 已装配 NEW repositories 的 SEC 下载管线。

        Returns:
            无。

        Raises:
            无。
        """

        self._pipeline = pipeline

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """执行 SEC 下载并返回已持久化摘要。

        SEC adapter 是 persisted-summary adapter：SEC workflow 通过同一个
        ``SecPipeline`` host 完成 source/rejected 与 local-only rebuild 副作用。

        Args:
            request: runtime 传入的已归一化下载请求。

        Returns:
            adapter 结果；SEC workflow 已通过 storage repositories 完成落盘。

        Raises:
            ValueError: ticker 市场或表单过滤非法时抛出。
            RuntimeError: SEC 下载失败时抛出。
        """

        if request.normalized_ticker.market != "US":
            raise ValueError(f"SEC 下载仅支持 US market，当前 market={request.normalized_ticker.market}")
        if request.source is not FinsDownloadSource.SEC:
            raise ValueError(f"SEC 下载来源不匹配: source={request.source.value}")
        result = _run_async_download_sync(
            collect_download_result_from_events(
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
            cast(dict[str, JsonValue], result),
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
    return _SEC_FORMS_ADAPTER_JOINER.join(form_types)


def _summary_from_pipeline_result(
    result: Mapping[str, JsonValue],
    *,
    request: FinsSourceDownloadAdapterRequest,
    source_repository: SourceDocumentRepositoryProtocol,
) -> FinsDownloadResultSummary:
    """把 SEC workflow 私有结果严格投影为 typed 下载摘要。

    Args:
        result: SEC workflow 私有结果。
        request: 当前 adapter typed request。
        source_repository: relative artifact locator 的 storage owner。

    Returns:
        保留全部 operation-local document rows 的 typed 摘要。

    Raises:
        ValueError: 结果缺少必填字段、字段类型非法或身份不一致时抛出。
        OSError: locator 查询失败时由 storage owner 抛出。
    """

    ticker = _required_sec_text(result, "ticker")
    if ticker != request.normalized_ticker.canonical:
        raise ValueError("SEC 下载结果 ticker 与 typed request 不一致")
    filings = _required_sec_mapping_list(result, "filings")
    rows = tuple(
        _project_sec_document_row(
            item,
            ticker=ticker,
            source_repository=source_repository,
        )
        for item in filings
    )
    filters = _project_sec_effective_filters(result, request=request)
    return _build_sec_typed_summary(
        ticker=ticker,
        filters=filters,
        rows=rows,
    )


def _project_sec_document_row(
    item: Mapping[str, JsonValue],
    *,
    ticker: str,
    source_repository: SourceDocumentRepositoryProtocol,
) -> FinsDownloadDocumentResult:
    """严格投影单个 SEC filing result。

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

    document_id = _required_sec_text(item, "document_id")
    status = _required_sec_text(item, "status")
    reason_code = _optional_sec_text(item, "reason_code")
    allow_missing_business_fields = status == _SEC_STATUS_FAILED and reason_code == "missing_form_type"
    form_or_period = _required_optional_sec_text(
        item,
        "form_type",
        allow_missing=allow_missing_business_fields,
    )
    filing_date = _required_optional_sec_text(
        item,
        "filing_date",
        allow_missing=allow_missing_business_fields,
    )
    report_date = _required_optional_sec_text(
        item,
        "report_date",
        allow_missing=allow_missing_business_fields,
    )
    if status == _SEC_STATUS_DOWNLOADED:
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
            covered_fiscal_periods=(),
            disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
            reason_category=None,
            reason_message=None,
            artifact_locator=locator,
        )
    if status == _SEC_STATUS_SKIPPED:
        category = reason_code or _required_sec_text(item, "skip_reason")
        disposition = (
            FinsDownloadDocumentDisposition.REJECTED
            if _is_rejected_filing_result(item)
            else FinsDownloadDocumentDisposition.SKIPPED
        )
        return FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period=form_or_period,
            filing_date=filing_date,
            report_date=report_date,
            covered_fiscal_periods=(),
            disposition=disposition,
            reason_category=category,
            reason_message=_sec_safe_reason_message(disposition),
            artifact_locator=None,
        )
    if status == _SEC_STATUS_REJECTED:
        category = reason_code or _SEC_REASON_6K_FILTERED
        return FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period=form_or_period,
            filing_date=filing_date,
            report_date=report_date,
            covered_fiscal_periods=(),
            disposition=FinsDownloadDocumentDisposition.REJECTED,
            reason_category=category,
            reason_message=_sec_safe_reason_message(FinsDownloadDocumentDisposition.REJECTED),
            artifact_locator=None,
        )
    if status == _SEC_STATUS_FAILED:
        category = reason_code or "sec_document_failed"
        return FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period=form_or_period,
            filing_date=filing_date,
            report_date=report_date,
            covered_fiscal_periods=(),
            disposition=FinsDownloadDocumentDisposition.FAILED,
            reason_category=category,
            reason_message=_sec_safe_reason_message(FinsDownloadDocumentDisposition.FAILED),
            artifact_locator=None,
        )
    raise ValueError(f"SEC 下载结果 status 未封闭: {status}")


def _project_sec_effective_filters(
    result: Mapping[str, JsonValue],
    *,
    request: FinsSourceDownloadAdapterRequest,
) -> FinsDownloadEffectiveFilters:
    """严格读取 SEC workflow 实际采用的筛选条件。

    Args:
        result: SEC workflow 私有结果。
        request: 当前 typed request，用于核对 mutation flags。

    Returns:
        typed effective filters。

    Raises:
        ValueError: filters 字段缺失、类型非法或 flags 与 request 不一致时抛出。
    """

    filters = _required_sec_mapping(result, "filters")
    forms = _required_sec_optional_text_list(filters, "forms")
    overwrite = _required_sec_bool(filters, "overwrite")
    if overwrite is not request.overwrite_existing:
        raise ValueError("SEC effective overwrite 与 typed request 不一致")
    if "rebuild" in filters:
        rebuild = _required_sec_bool(filters, "rebuild")
        if rebuild is not request.rebuild_local_artifacts:
            raise ValueError("SEC effective rebuild 与 typed request 不一致")
    start_date = _sec_effective_start_date(filters)
    end_date = _required_optional_sec_text(filters, "end_date", allow_missing=False)
    return FinsDownloadEffectiveFilters(
        form_types=forms,
        start_date=start_date,
        end_date=end_date,
        overwrite_existing=overwrite,
        rebuild_local_artifacts=request.rebuild_local_artifacts,
    )


def _sec_effective_start_date(filters: Mapping[str, JsonValue]) -> str | None:
    """从 SEC normal/rebuild 私有 filters 读取 effective inclusive 起点。

    Args:
        filters: workflow 私有 filters。

    Returns:
        最早 form 窗口起点；显式空起点返回 ``None``。

    Raises:
        ValueError: start 字段缺失或类型非法时抛出。
    """

    if "start_date" in filters:
        return _required_optional_sec_text(filters, "start_date", allow_missing=False)
    start_dates = _required_sec_mapping(filters, "start_dates")
    values = tuple(_required_sec_text(start_dates, key) for key in sorted(start_dates))
    if not values:
        return None
    return min(values)


def _build_sec_typed_summary(
    *,
    ticker: str,
    filters: FinsDownloadEffectiveFilters,
    rows: tuple[FinsDownloadDocumentResult, ...],
) -> FinsDownloadResultSummary:
    """从同一 typed row tuple 派生 SEC 计数。

    Args:
        ticker: canonical ticker。
        filters: effective filters。
        rows: 完整 document rows。

    Returns:
        计数与 rows 同源的 typed summary。

    Raises:
        ValueError: summary 不变量失败时由 contract 抛出。
    """

    return FinsDownloadResultSummary.from_document_rows(
        source=FinsDownloadSource.SEC,
        canonical_ticker=ticker,
        effective_filters=filters,
        document_rows=rows,
        missing_periods=(),
    )


def _is_rejected_filing_result(item: Mapping[str, JsonValue]) -> bool:
    """判断 SEC filing 结果是否为 rejected artifact。

    Args:
        item: SEC workflow filing result。

    Returns:
        明确 rejected 或 6-K filtered skipped 返回 ``True``。

    Raises:
        ValueError: status 或 reason 字段类型非法时抛出。
    """

    status = _required_sec_text(item, "status")
    if status == _SEC_STATUS_REJECTED:
        return True
    if status != _SEC_STATUS_SKIPPED:
        return False
    skip_reason = _optional_sec_text(item, "skip_reason")
    reason_code = _optional_sec_text(item, "reason_code")
    return skip_reason == _SEC_REASON_6K_FILTERED or reason_code == _SEC_REASON_6K_FILTERED


def _sec_safe_reason_message(disposition: FinsDownloadDocumentDisposition) -> str:
    """为 SEC document disposition 选择不复制 raw provider 文本的说明。

    Args:
        disposition: typed document disposition。

    Returns:
        脱敏业务说明。

    Raises:
        ValueError: downloaded disposition 不需要 reason 时抛出。
    """

    if disposition is FinsDownloadDocumentDisposition.SKIPPED:
        return "该文档按下载策略跳过"
    if disposition is FinsDownloadDocumentDisposition.REJECTED:
        return "该文档未通过来源筛选规则"
    if disposition is FinsDownloadDocumentDisposition.FAILED:
        return "SEC 来源未能完成该文档"
    raise ValueError("downloaded disposition must not contain a reason")


def _required_sec_mapping(
    value: Mapping[str, JsonValue],
    key: str,
) -> Mapping[str, JsonValue]:
    """读取 SEC 私有结果中的必填 mapping。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        只读 mapping。

    Raises:
        ValueError: 字段缺失或类型非法时抛出。
    """

    if key not in value or not isinstance(value[key], Mapping):
        raise ValueError(f"SEC 下载结果 {key} 字段必须是对象")
    raw = value[key]
    assert isinstance(raw, Mapping)
    return raw


def _required_sec_mapping_list(
    value: Mapping[str, JsonValue],
    key: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 SEC 私有结果中的必填 mapping 列表。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        保持原顺序的 mapping tuple。

    Raises:
        ValueError: 字段缺失、不是列表或元素不是对象时抛出。
    """

    if key not in value or not isinstance(value[key], list):
        raise ValueError(f"SEC 下载结果 {key} 字段必须是列表")
    raw_items = value[key]
    assert isinstance(raw_items, list)
    items: list[Mapping[str, JsonValue]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"SEC 下载结果 {key}[{index}] 必须是对象")
        items.append(raw_item)
    return tuple(items)


def _required_sec_text(value: Mapping[str, JsonValue], key: str) -> str:
    """读取 SEC 私有结果中的必填非空文本。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        去空白文本。

    Raises:
        ValueError: 字段缺失、类型非法或为空时抛出。
    """

    if key not in value:
        raise ValueError(f"SEC 下载结果缺少必填文本字段: {key}")
    raw = value[key]
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"SEC 下载结果缺少必填文本字段: {key}")
    return raw.strip()


def _optional_sec_text(value: Mapping[str, JsonValue], key: str) -> str | None:
    """严格读取 SEC 私有结果中的可选文本。

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
    return _required_sec_text(value, key)


def _required_optional_sec_text(
    value: Mapping[str, JsonValue],
    key: str,
    *,
    allow_missing: bool,
) -> str | None:
    """读取允许 ``None`` 但默认要求 key 存在的 SEC 文本。

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
        raise ValueError(f"SEC 下载结果缺少字段: {key}")
    if value[key] is None:
        return None
    return _required_sec_text(value, key)


def _required_sec_optional_text_list(
    value: Mapping[str, JsonValue],
    key: str,
) -> tuple[str, ...]:
    """读取可为 ``None`` 的 SEC canonical form 列表。

    Args:
        value: 当前 mapping。
        key: 字段名。

    Returns:
        canonical form tuple；``None`` 返回空 tuple。

    Raises:
        ValueError: 字段缺失、类型非法或元素非法时抛出。
    """

    if key not in value:
        raise ValueError(f"SEC 下载结果缺少字段: {key}")
    raw = value[key]
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"SEC 下载结果 {key} 字段必须是列表或 null")
    forms: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"SEC 下载结果 {key}[{index}] 必须是非空文本")
        forms.append(item.strip())
    return tuple(forms)


def _required_sec_bool(value: Mapping[str, JsonValue], key: str) -> bool:
    """读取 SEC 私有结果中的必填布尔字段。

    Args:
        value: 当前 mapping。
        key: 必填字段名。

    Returns:
        布尔值。

    Raises:
        ValueError: 字段缺失或不是布尔值时抛出。
    """

    if key not in value or not isinstance(value[key], bool):
        raise ValueError(f"SEC 下载结果 {key} 字段必须是布尔值")
    raw = value[key]
    assert isinstance(raw, bool)
    return raw


def build_sec_download_adapter(
    *,
    workspace_root: Path,
    processor_registry: ProcessorRegistry,
    batching_repository: BatchingRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    user_agent: Optional[str] = None,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> SecDownloadAdapter:
    """构建 production SEC 下载 adapter。

    Args:
        workspace_root: Fins 工作区根目录。
        processor_registry: 文档处理器注册表。
        batching_repository: batch lifecycle 仓储。
        company_repository: 公司元数据仓储。
        source_repository: 源文档仓储。
        processed_repository: processed 仓储。
        blob_repository: 文件对象仓储。
        filing_maintenance_repository: filing 维护仓储。
        user_agent: 可选 SEC User-Agent。
        sleep_seconds: SEC 请求间隔秒数。
        max_retries: SEC 下载重试次数。

    Returns:
        SEC 下载 adapter。

    Raises:
        OSError: downloader 或默认组件初始化失败时抛出。
    """

    pipeline = SecPipeline(
        processor_registry=processor_registry,
        workspace_root=workspace_root,
        batching_repository=batching_repository,
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=filing_maintenance_repository,
        user_agent=user_agent,
        sleep_seconds=sleep_seconds,
        max_retries=max_retries,
    )
    return SecDownloadAdapter(pipeline=pipeline)


__all__ = [
    "SEC_DOWNLOAD_SOURCE",
    "SEC_PIPELINE_DOWNLOAD_VERSION",
    "SecDownloadAdapter",
    "SecPipeline",
    "build_sec_download_adapter",
    "collect_download_result_from_events",
]
