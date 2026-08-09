"""SecPipeline 下载工作流模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import datetime as dt
import inspect
import time
from typing import AsyncIterator, Awaitable, Callable, Final, Optional, Protocol, TypeVar, cast

from dayu.fins.domain.document_models import BatchToken, DownloadRejectionRegistry
from dayu.fins.downloaders.sec_downloader import SecDownloadCancelledError
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_filing_collection import FilingRecord
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins._log import Log

_FILING_STATUS_DOWNLOADED: Final[str] = "downloaded"
_FILING_STATUS_SKIPPED: Final[str] = "skipped"
_FILING_STATUS_FAILED: Final[str] = "failed"
_FILING_REASON_6K_FILTERED: Final[str] = "6k_filtered"


class _DownloadWorkflowDownloader(Protocol):
    """下载工作流所需的最小下载器边界。"""

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """配置下载器。"""

        ...

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。"""

        ...

    def resolve_company(
        self,
        ticker: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[tuple[str, str, str]] | tuple[str, str, str]:
        """解析公司信息。"""

        ...

    def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[dict[str, JsonValue]] | dict[str, JsonValue]:
        """拉取 submissions。"""

        ...


class _SaveRejectionRegistry(Protocol):
    """SEC maintenance registry 写入回调边界。"""

    def __call__(
        self,
        repository: FilingMaintenanceRepositoryProtocol,
        ticker: str,
        registry: DownloadRejectionRegistry,
        *,
        batch: BatchToken,
    ) -> None:
        """写入拒绝注册表。

        Args:
            repository: filing 维护仓储。
            ticker: 股票代码。
            registry: 拒绝注册表。
            batch: invocation-time 显式 batch capability。

        Returns:
            无。

        Raises:
            OSError: 仓储写入失败时抛出。
            ValueError: batch capability 非法时抛出。
        """

        ...


class SecDownloadWorkflowHost(Protocol):
    """Sec download 工作流所需的最小宿主边界。"""

    @property
    def _batching_repository(self) -> BatchingRepositoryProtocol:
        """返回 batch lifecycle 唯一仓储。"""

        ...

    @property
    def MODULE(self) -> str:
        """返回日志模块名。"""

        ...

    @property
    def _downloader(self) -> _DownloadWorkflowDownloader:
        """返回下载器实例。"""

        ...

    @property
    def _user_agent(self) -> Optional[str]:
        """返回 User-Agent。"""

        ...

    @property
    def _sleep_seconds(self) -> float:
        """返回下载间隔秒数。"""

        ...

    @property
    def _max_retries(self) -> int:
        """返回最大重试次数。"""

        ...

    @property
    def _filing_maintenance_repository(self) -> FilingMaintenanceRepositoryProtocol:
        """返回 filing 维护仓储。"""

        ...

    @property
    def _source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回 source 仓储。"""

        ...

    def _rebuild_download_artifacts(
        self,
        *,
        ticker: str,
        form_type: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        overwrite: bool,
    ) -> dict[str, JsonValue]:
        """基于本地已下载 filings 重建 meta/manifest。"""

        ...

    def _resolve_form_windows(
        self,
        form_type: Optional[str],
        start_date: Optional[str],
        end_date: dt.date,
    ) -> dict[str, dt.date]:
        """计算 form 到起始日期映射。"""

        ...

    def _upsert_company_meta(
        self,
        ticker: str,
        company_id: str,
        company_name: str,
        ticker_aliases: Optional[list[str]],
        *,
        batch: BatchToken,
    ) -> None:
        """写入公司元数据。"""

        ...

    def _build_result(self, action: str, **payload: JsonValue) -> dict[str, JsonValue]:
        """构建统一结果。"""

        ...

    def _log_filing_download_result(self, ticker: str, filing_result: dict[str, JsonValue]) -> None:
        """记录单个 filing 下载结果。"""

        ...

    def _download_single_filing_stream(
        self,
        *,
        ticker: str,
        cik: str,
        filing: FilingRecord,
        overwrite: bool,
        rejection_registry: DownloadRejectionRegistry,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloadEvent]:
        """执行单 filing 下载流。"""

        ...

    def _filter_filings(
        self,
        *,
        ticker: str,
        submissions: dict[str, JsonValue],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[tuple[list[FilingRecord], set[str]]]:
        """过滤 filings 并收集 filenum。"""

        ...

    def _extend_with_browse_edgar_sc13(
        self,
        *,
        ticker: str,
        filings: list[FilingRecord],
        filenums: set[str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[list[FilingRecord]]:
        """补充 browse-edgar SC13 filings。"""

        ...

    def _retry_sc13_if_empty(
        self,
        *,
        ticker: str,
        filings: list[FilingRecord],
        filenums: set[str],
        submissions: dict[str, JsonValue],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        start_is_explicit: bool,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[DownloadRejectionRegistry] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[list[FilingRecord]]:
        """仅在未显式给出起点且 SC13 为空时执行渐进式回溯。"""

        ...


_AwaitableResult = TypeVar("_AwaitableResult")


async def _maybe_await(value: Awaitable[_AwaitableResult] | _AwaitableResult) -> _AwaitableResult:
    """按需等待可等待对象。"""

    if inspect.isawaitable(value):
        return await value
    return value


async def run_download_stream_impl(
    host: SecDownloadWorkflowHost,
    *,
    ticker: str,
    form_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    overwrite: bool = False,
    rebuild: bool = False,
    ticker_aliases: Optional[list[str]] = None,
    start_is_explicit: bool,
    cancel_checker: Optional[Callable[[], bool]] = None,
    parse_date: Callable[[str, bool], dt.date],
    extract_sec_ticker_aliases: Callable[..., list[str]],
    merge_ticker_aliases: Callable[..., list[str]],
    load_rejection_registry: Callable[
        [FilingMaintenanceRepositoryProtocol, str],
        DownloadRejectionRegistry,
    ],
    save_rejection_registry: _SaveRejectionRegistry,
    should_warn_missing_sc13: Callable[[dict[str, dt.date], list[FilingRecord]], bool],
    warn_insufficient_filings: Callable[
        [dict[str, dt.date], list[dict[str, JsonValue]], DownloadRejectionRegistry],
        list[str],
    ],
    warn_xbrl_missing_filings: Callable[[list[dict[str, JsonValue]]], list[str]],
    build_download_filing_event_payload: Callable[[dict[str, JsonValue]], dict[str, JsonValue]],
) -> AsyncIterator[DownloadEvent]:
    """执行 SecPipeline 下载主工作流。

    Args:
        host: `SecPipeline` facade 暴露出的最小宿主边界。
        ticker: 股票代码。
        form_type: 可选文档类型。
        start_date: 可选开始日期。
        end_date: 可选结束日期。
        overwrite: 是否强制覆盖。
        rebuild: 是否仅基于本地已下载数据重建 `meta/manifest`。
        ticker_aliases: CLI 侧传入的 alias 列表。
        start_is_explicit: 起始日期是否来自调用方显式输入。
        cancel_checker: 可选协作式取消检查函数。
        parse_date: 日期解析 helper。
        extract_sec_ticker_aliases: SEC alias 提取 helper。
        merge_ticker_aliases: alias 合并 helper。
        load_rejection_registry: 加载拒绝注册表 helper。
        save_rejection_registry: 保存拒绝注册表 helper。
        should_warn_missing_sc13: SC13 缺失 warning helper。
        warn_insufficient_filings: form 数量检查 helper。
        warn_xbrl_missing_filings: XBRL 缺失检查 helper。
        build_download_filing_event_payload: 构建 filing 事件 payload helper。

    Yields:
        下载流程事件流。

    Raises:
        ValueError: ticker 不合法或市场不匹配时抛出。
        RuntimeError: 下载执行失败时抛出。
    """

    normalized = normalize_ticker(ticker)
    if normalized.market != "US":
        raise ValueError(f"SecPipeline 仅支持 US，当前 market={normalized.market}")
    normalized_ticker = host._downloader.normalize_ticker(ticker)
    if rebuild:
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_STARTED,
            ticker=normalized_ticker,
            payload={
                "form_type": form_type,
                "start_date": start_date,
                "end_date": end_date,
                "overwrite": overwrite,
                "rebuild": True,
            },
        )
        rebuild_result = host._rebuild_download_artifacts(
            ticker=normalized_ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
        )
        raw_rebuild_filings = rebuild_result.get("filings")
        rebuild_filings = raw_rebuild_filings if isinstance(raw_rebuild_filings, list) else []
        for filing_result in rebuild_filings:
            if not isinstance(filing_result, dict):
                continue
            status = str(filing_result.get("status", "failed"))
            event_type = (
                DownloadEventType.FILING_FAILED
                if status == "failed"
                else DownloadEventType.FILING_COMPLETED
            )
            document_id = str(filing_result.get("document_id", ""))
            yield DownloadEvent(
                event_type=event_type,
                ticker=normalized_ticker,
                document_id=document_id,
            payload=build_download_filing_event_payload(cast(dict[str, JsonValue], filing_result)),
            )
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_COMPLETED,
            ticker=normalized_ticker,
            payload={"result": rebuild_result},
        )
        return

    download_end_date = parse_date(end_date, True) if end_date else dt.date.today()
    host._downloader.configure(
        user_agent=host._user_agent,
        sleep_seconds=host._sleep_seconds,
        max_retries=host._max_retries,
    )
    yield DownloadEvent(
        event_type=DownloadEventType.PIPELINE_STARTED,
        ticker=normalized_ticker,
        payload={
            "form_type": form_type,
            "start_date": start_date,
            "end_date": end_date,
            "overwrite": overwrite,
            "rebuild": False,
        },
    )
    started_at = time.perf_counter()

    try:
        cik, company_name, cik10 = await _maybe_await(
            host._downloader.resolve_company(
                normalized_ticker,
                cancellation_checker=cancel_checker,
            )
        )
        submissions = await _maybe_await(
            host._downloader.fetch_submissions(
                cik10,
                cancellation_checker=cancel_checker,
            )
        )
    except SecDownloadCancelledError:
        yield _cancelled_pipeline_completed_event(
            host=host,
            normalized_ticker=normalized_ticker,
            normalized_market=normalized.market,
            form_type=form_type,
            start_date=start_date,
            end_date=download_end_date,
            overwrite=overwrite,
            warnings=(),
            filing_results=(),
            elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        )
        return
    sec_ticker_aliases = extract_sec_ticker_aliases(
        submissions=submissions,
        primary_ticker=normalized_ticker,
    )
    merged_ticker_aliases = merge_ticker_aliases(
        primary_ticker=normalized_ticker,
        alias_groups=[sec_ticker_aliases, ticker_aliases],
    )
    yield DownloadEvent(
        event_type=DownloadEventType.COMPANY_RESOLVED,
        ticker=normalized_ticker,
        payload={
            "cik": cik,
            "company_name": company_name,
            "cik10": cik10,
        },
    )
    form_windows = host._resolve_form_windows(
        form_type=form_type,
        start_date=start_date,
        end_date=download_end_date,
    )
    Log.verbose(
        f"下载窗口详情: { {key: value.isoformat() for key, value in form_windows.items()} }",
        module=host.MODULE,
    )
    Log.info(
        (
            "进入美股下载流程: "
            f"ticker={normalized_ticker} form_type={form_type} start={start_date} end={end_date} "
            f"overwrite={overwrite}"
        ),
        module=host.MODULE,
    )
    company_batch = host._batching_repository.begin_batch(normalized_ticker)
    try:
        host._upsert_company_meta(
            ticker=normalized_ticker,
            company_id=cik,
            company_name=company_name,
            ticker_aliases=merged_ticker_aliases,
            batch=company_batch,
        )
    except BaseException:
        host._batching_repository.rollback_batch(company_batch)
        raise
    host._batching_repository.commit_batch(company_batch)
    sc13_direction_cache: dict[str, Optional[bool]] = {}
    rejection_registry = load_rejection_registry(host._filing_maintenance_repository, normalized_ticker)
    try:
        filings, filenums = await host._filter_filings(
            ticker=normalized_ticker,
            submissions=submissions,
            form_windows=form_windows,
            end_date=download_end_date,
            target_cik=cik,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )
        filings = await host._extend_with_browse_edgar_sc13(
            ticker=normalized_ticker,
            filings=filings,
            filenums=filenums,
            form_windows=form_windows,
            end_date=download_end_date,
            target_cik=cik,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )
        filings = _filter_filings_to_windows(
            filings=filings,
            form_windows=form_windows,
            end_date=download_end_date,
            parse_date=parse_date,
        )
        filings = await host._retry_sc13_if_empty(
            ticker=normalized_ticker,
            filings=filings,
            filenums=filenums,
            submissions=submissions,
            form_windows=form_windows,
            end_date=download_end_date,
            target_cik=cik,
            start_is_explicit=start_is_explicit,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )
        filings = _filter_filings_to_windows(
            filings=filings,
            form_windows=form_windows,
            end_date=download_end_date,
            parse_date=parse_date,
        )
    except SecDownloadCancelledError:
        Log.info(
            f"下载任务收到取消请求，filing 收集阶段停止: ticker={normalized_ticker}",
            module=host.MODULE,
        )
        yield _cancelled_pipeline_completed_event(
            host=host,
            normalized_ticker=normalized_ticker,
            normalized_market=normalized.market,
            form_type=form_type,
            start_date=start_date,
            end_date=download_end_date,
            overwrite=overwrite,
            warnings=(),
            filing_results=(),
            elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        )
        return
    warnings: list[str] = []
    if should_warn_missing_sc13(form_windows, filings):
        warning = (
            "未在 issuer 的 submissions/browse-edgar 中发现 SC 13D/G；"
            "13D/G 往往由申报人提交，需要申报人 CIK 维度或反查补齐。"
        )
        warnings.append(warning)
        Log.warn(warning, module=host.MODULE)

    filing_results: list[dict[str, JsonValue]] = []
    cancelled = False
    for filing in filings:
        if cancel_checker is not None and cancel_checker():
            cancelled = True
            Log.info(
                f"下载任务收到取消请求，文档边界停止: ticker={normalized_ticker}",
                module=host.MODULE,
            )
            break
        document_id = f"fil_{filing.accession_number}"
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_STARTED,
            ticker=normalized_ticker,
            document_id=document_id,
            payload={
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "accession_number": filing.accession_number,
                "total_filings": len(filings),
            },
        )
        filing_terminal_seen = False
        async for event in host._download_single_filing_stream(
            ticker=normalized_ticker,
            cik=cik,
            filing=filing,
            overwrite=overwrite,
            rejection_registry=rejection_registry,
            cancel_checker=cancel_checker,
        ):
            event_result = event.payload.get("filing_result")
            if event.event_type in {
                DownloadEventType.FILING_COMPLETED,
                DownloadEventType.FILING_FAILED,
            } and isinstance(event_result, dict):
                filing_terminal_seen = True
                filing_results.append(cast(dict[str, JsonValue], event_result))
                host._log_filing_download_result(
                    ticker=normalized_ticker,
                    filing_result=cast(dict[str, JsonValue], event_result),
                )
            yield event
        if not filing_terminal_seen and cancel_checker is not None and cancel_checker():
            cancelled = True
            Log.info(
                f"下载任务收到取消请求，当前 filing 已停止: ticker={normalized_ticker} document_id={document_id}",
                module=host.MODULE,
            )
            break

    maintenance_batch = host._batching_repository.begin_batch(normalized_ticker)
    try:
        save_rejection_registry(
            host._filing_maintenance_repository,
            normalized_ticker,
            rejection_registry,
            batch=maintenance_batch,
        )
    except BaseException:
        host._batching_repository.rollback_batch(maintenance_batch)
        raise
    host._batching_repository.commit_batch(maintenance_batch)
    for warning in warn_insufficient_filings(
        form_windows,
        filing_results,
        rejection_registry,
    ):
        warnings.append(warning)
        Log.warn(warning, module=host.MODULE)
    for warning in warn_xbrl_missing_filings(filing_results):
        warnings.append(warning)
        Log.warn(warning, module=host.MODULE)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    rejected_count = sum(1 for item in filing_results if _is_rejected_filing_result(item))
    skipped_count = sum(
        1
        for item in filing_results
        if item["status"] == _FILING_STATUS_SKIPPED and not _is_rejected_filing_result(item)
    )
    summary = {
        "total": len(filing_results),
        "downloaded": sum(1 for item in filing_results if item["status"] == _FILING_STATUS_DOWNLOADED),
        "skipped": skipped_count,
        "rejected": rejected_count,
        "failed": sum(1 for item in filing_results if item["status"] == _FILING_STATUS_FAILED),
        "elapsed_ms": elapsed_ms,
        "reused_downloads": 0,
        "converted": 0,
    }
    Log.info(
        (
            "美股下载完成: "
            f"ticker={normalized_ticker} total={summary['total']} downloaded={summary['downloaded']} "
            f"skipped={summary['skipped']} rejected={summary['rejected']} "
            f"failed={summary['failed']} elapsed_ms={summary['elapsed_ms']}"
        ),
        module=host.MODULE,
    )
    final_result = host._build_result(
        action="download",
        ticker=normalized_ticker,
        market_profile={
            "market": normalized.market,
        },
        filters=cast(JsonValue, {
            "forms": sorted(form_windows.keys()),
            "start_dates": {key: value.isoformat() for key, value in sorted(form_windows.items())},
            "end_date": download_end_date.isoformat(),
            "overwrite": overwrite,
        }),
        warnings=cast(JsonValue, warnings),
        filings=cast(JsonValue, filing_results),
        summary=cast(JsonValue, summary),
        status="cancelled" if cancelled else "ok",
    )
    yield DownloadEvent(
        event_type=DownloadEventType.PIPELINE_COMPLETED,
        ticker=normalized_ticker,
        payload={"result": final_result},
    )


def _cancelled_pipeline_completed_event(
    *,
    host: SecDownloadWorkflowHost,
    normalized_ticker: str,
    normalized_market: str,
    form_type: Optional[str],
    start_date: Optional[str],
    end_date: dt.date,
    overwrite: bool,
    warnings: tuple[str, ...],
    filing_results: tuple[dict[str, JsonValue], ...],
    elapsed_ms: int,
) -> DownloadEvent:
    """构造 SEC 下载取消完成事件。

    Args:
        host: `SecPipeline` facade 暴露出的最小宿主边界。
        normalized_ticker: 标准化 ticker。
        normalized_market: 标准化市场。
        form_type: 可选表单过滤。
        start_date: 可选开始日期。
        end_date: 已解析结束日期。
        overwrite: 是否覆盖。
        warnings: 已收集 warning。
        filing_results: 已完成 filing 结果。
        elapsed_ms: 已耗时毫秒。

    Returns:
        `PIPELINE_COMPLETED` 取消事件。

    Raises:
        无。
    """

    form_windows = host._resolve_form_windows(
        form_type=form_type,
        start_date=start_date,
        end_date=end_date,
    )
    summary = {
        "total": len(filing_results),
        "downloaded": sum(1 for item in filing_results if item["status"] == _FILING_STATUS_DOWNLOADED),
        "skipped": sum(1 for item in filing_results if item["status"] == _FILING_STATUS_SKIPPED),
        "rejected": sum(1 for item in filing_results if _is_rejected_filing_result(item)),
        "failed": sum(1 for item in filing_results if item["status"] == _FILING_STATUS_FAILED),
        "elapsed_ms": elapsed_ms,
        "reused_downloads": 0,
        "converted": 0,
    }
    final_result = host._build_result(
        action="download",
        ticker=normalized_ticker,
        market_profile={"market": normalized_market},
        filters=cast(JsonValue, {
            "forms": sorted(form_windows.keys()),
            "start_dates": {key: value.isoformat() for key, value in sorted(form_windows.items())},
            "end_date": end_date.isoformat(),
            "overwrite": overwrite,
        }),
        warnings=cast(JsonValue, list(warnings)),
        filings=cast(JsonValue, list(filing_results)),
        summary=cast(JsonValue, summary),
        status="cancelled",
    )
    return DownloadEvent(
        event_type=DownloadEventType.PIPELINE_COMPLETED,
        ticker=normalized_ticker,
        payload={"result": final_result},
    )


def _is_rejected_filing_result(item: dict[str, JsonValue]) -> bool:
    """判断 filing 结果是否代表 rejected artifact。

    Args:
        item: SEC filing 下载结果。

    Returns:
        6-K 预筛未命中并写入 rejected artifact 时返回 ``True``。

    Raises:
        无。
    """

    if item["status"] != _FILING_STATUS_SKIPPED:
        return False
    skip_reason = str(item.get("skip_reason", "")).strip()
    reason_code = str(item.get("reason_code", "")).strip()
    return skip_reason == _FILING_REASON_6K_FILTERED or reason_code == _FILING_REASON_6K_FILTERED


def _filter_filings_to_windows(
    *,
    filings: list[FilingRecord],
    form_windows: dict[str, dt.date],
    end_date: dt.date,
    parse_date: Callable[[str, bool], dt.date],
) -> list[FilingRecord]:
    """在产生 filing outcome 前执行统一 inclusive 窗口终检。

    Args:
        filings: submissions、browse 与 SC13 retry 合并后的候选。
        form_windows: 每个 canonical form 的 inclusive 起始日期。
        end_date: 所有 form 共享的 inclusive 结束日期。
        parse_date: SEC 日期解析 owner。

    Returns:
        仍处于各自 form inclusive 窗口内的候选。

    Raises:
        ValueError: 候选 filing date 非法时由日期 owner 抛出。
    """

    selected: list[FilingRecord] = []
    for filing in filings:
        lower_bound = form_windows.get(filing.form_type)
        if lower_bound is None:
            continue
        filing_date = parse_date(filing.filing_date, False)
        if lower_bound <= filing_date <= end_date:
            selected.append(filing)
    return selected
