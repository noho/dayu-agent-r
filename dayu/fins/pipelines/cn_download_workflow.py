"""CN/HK ticker 级下载主工作流。

本模块负责 ticker 归一化、form/window 解析、company meta 写入、候选发现、
overwrite ticker 级清理、单 filing 阶段机调度和 summary 聚合。单文件落盘细节由
``cn_download_filing_workflow`` 承担。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from functools import partial
from typing import TypeAlias, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.pipelines.cn_download_company_meta import stage_company_meta_for_cn_download
from dayu.fins.pipelines.cn_download_filing_workflow import (
    project_cn_filing_failure,
    run_cn_download_single_filing_stream,
)
from dayu.fins.pipelines.cn_download_models import (
    CnDownloadCancelledError,
    CnCompanyProfile,
    CnFiscalPeriod,
    CnMarketKind,
    CnReportCandidate,
    CnReportQuery,
)
from dayu.fins.pipelines.cn_download_rebuild import rebuild_cn_download_artifacts
from dayu.fins.pipelines.cn_download_protocols import (
    CnDownloadWorkflowHost,
    CnReportDiscoveryClientProtocol,
)
from dayu.fins.pipelines.cn_form_utils import (
    PeriodDownloadWindow,
    build_cn_filing_ids,
    resolve_period_windows,
    resolve_download_period_policy,
    resolve_window,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import (
    SelectedSourceRepairRequired,
    SourceIntegrityRevisionConflictError,
    classify_source_integrity_preflight,
)
from dayu.fins._log import Log
from dayu.fins.ticker_normalization import ticker_to_company_id, try_normalize_ticker

JsonObject: TypeAlias = dict[str, JsonValue]


async def run_cn_download_stream_impl(
    host: CnDownloadWorkflowHost,
    *,
    ticker: str,
    form_type: str | None,
    start_date: str | None,
    end_date: str | None,
    overwrite: bool,
    rebuild: bool,
    ticker_aliases: list[str] | None,
    start_is_explicit: bool,
    cancel_checker: Callable[[], bool] | None,
    module: str,
    pipeline_name: str,
) -> AsyncIterator[DownloadEvent]:
    """执行 CN/HK ticker 级下载工作流。

    Args:
        host: workflow 所需宿主协议。
        ticker: 原始 ticker。
        form_type: 可选 form 输入。
        start_date: 可选窗口起点。
        end_date: 可选窗口终点。
        overwrite: 是否强制覆盖。
        rebuild: 是否仅基于本地已下载数据重建 `meta/manifest`。
        ticker_aliases: 可选 ticker alias。
        start_is_explicit: 起始日期是否来自调用方显式输入。
        cancel_checker: 可选取消检查函数。
        module: 日志模块名。
        pipeline_name: pipeline 名称。

    Yields:
        下载事件流。

    Raises:
        ValueError: ticker、form 或日期参数非法时抛出。
        OSError: 仓储读写失败时抛出。
    """

    started_at = time.perf_counter()
    normalized = try_normalize_ticker(ticker)
    if normalized is None or normalized.market not in {"CN", "HK"}:
        raise ValueError(f"CN/HK download 不支持 ticker={ticker!r}")
    market = _coerce_market(normalized.market)
    normalized_ticker = normalized.canonical
    period_policy = resolve_download_period_policy(form_type, market)
    period_windows = resolve_period_windows(
        discovery_periods=period_policy.discovery_periods,
        start_date=start_date,
        end_date=end_date,
    )
    window = resolve_window(start_date, end_date)
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
        rebuild_result = rebuild_cn_download_artifacts(
            host=host,
            ticker=normalized_ticker,
            market=market,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            pipeline_name=pipeline_name,
            cancel_checker=cancel_checker,
        )
        raw_filings = rebuild_result.get("filings")
        rebuild_filings = raw_filings if isinstance(raw_filings, list) else []
        for raw_filing in rebuild_filings:
            try:
                if _is_cancel_requested(cancel_checker):
                    break
            except CnDownloadCancelledError:
                break
            if not isinstance(raw_filing, dict):
                continue
            filing_result: JsonObject = dict(raw_filing)
            status = str(filing_result.get("status", "failed"))
            event_type = DownloadEventType.FILING_FAILED if status == "failed" else DownloadEventType.FILING_COMPLETED
            document_id = str(filing_result.get("document_id", ""))
            yield DownloadEvent(
                event_type=event_type,
                ticker=normalized_ticker,
                document_id=document_id,
                payload=_filing_event_payload(filing_result),
            )
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_COMPLETED,
            ticker=normalized_ticker,
            payload={"result": rebuild_result},
        )
        return

    yield DownloadEvent(
        event_type=DownloadEventType.PIPELINE_STARTED,
        ticker=normalized_ticker,
        payload={
            "form_type": form_type,
            "start_date": window.start_date,
            "end_date": window.end_date,
            "overwrite": overwrite,
            "rebuild": rebuild,
        },
    )
    Log.info(
        (
            "进入CN/HK下载流程: "
            f"ticker={normalized_ticker} market={market} form_type={form_type} "
            f"start={start_date} end={end_date} overwrite={overwrite}"
        ),
        module=module,
    )
    discovery = _select_discovery_client(host=host, market=market)
    query = CnReportQuery(
        market=market,
        normalized_ticker=normalized_ticker,
        start_date=window.start_date,
        end_date=window.end_date,
        discovery_periods=period_policy.discovery_periods,
    )
    cancellation_checkpoint: Callable[[], None] | None = None
    if cancel_checker is not None:
        cancellation_checkpoint = partial(
            _raise_if_cancelled,
            module=module,
            ticker=normalized_ticker,
            document_id="",
            cancel_checker=cancel_checker,
        )
    filings: list[JsonObject] = []
    warnings: list[str] = []
    notes: list[str] = []
    company_info: JsonObject = {}
    missing_periods: tuple[str, ...] = ()
    try:
        _raise_if_cancelled(module=module, ticker=normalized_ticker, document_id="", cancel_checker=cancel_checker)
        profile = discovery.resolve_company(query)
        _raise_if_cancelled(module=module, ticker=normalized_ticker, document_id="", cancel_checker=cancel_checker)
        company_info = {
            "company_id": ticker_to_company_id(normalized),
            "provider_company_id": profile.company_id,
            "company_name": profile.company_name,
            "market": market,
        }
        _raise_if_cancelled(module=module, ticker=normalized_ticker, document_id="", cancel_checker=cancel_checker)
        yield DownloadEvent(
            event_type=DownloadEventType.COMPANY_RESOLVED,
            ticker=normalized_ticker,
            payload=company_info,
        )
        candidates = discovery.list_report_candidates(
            query,
            profile,
            cancellation_checkpoint=cancellation_checkpoint,
        )
        _raise_if_cancelled(module=module, ticker=normalized_ticker, document_id="", cancel_checker=cancel_checker)
        selected = _select_candidates_for_a4(
            candidates,
            period_windows=period_windows,
            use_default_business_limits=not start_is_explicit,
        )
        accepted_filing_ids = frozenset(_candidate_document_id(normalized_ticker, candidate) for candidate in selected)
        preflight = classify_source_integrity_preflight(
            host.source_repository.list_source_integrity(normalized_ticker),
            accepted_filing_ids=accepted_filing_ids,
            rejected_filing_ids=frozenset(),
        )
        repair_document_id: str | None = None
        if isinstance(preflight, SelectedSourceRepairRequired):
            repair_document_id = preflight.target.document_id
            selected = tuple(
                sorted(
                    selected,
                    key=lambda item: (_candidate_document_id(normalized_ticker, item) != repair_document_id,),
                )
            )
        missing_periods = _resolve_missing_periods(
            period_policy.missing_eligible_periods,
            selected,
        )
        cancelled = False
        repair_gate_completed = False
        if repair_document_id is None:
            _publish_cn_company_after_repair(
                host=host,
                profile=profile,
                normalized_ticker=normalized_ticker,
                ticker_aliases=ticker_aliases,
            )
            repair_gate_completed = True
        for candidate in selected:
            if cancel_checker is not None and cancel_checker():
                notes.append("cancelled")
                cancelled = True
                break
            document_id = _candidate_document_id(normalized_ticker, candidate)
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_STARTED,
                ticker=normalized_ticker,
                document_id=document_id,
                payload={
                    "form_type": candidate.period_projection.identity_period,
                    "filing_date": candidate.filing_date,
                    "fiscal_year": candidate.fiscal_year,
                    "fiscal_period": candidate.period_projection.identity_period,
                    "covered_fiscal_periods": list(candidate.period_projection.covered_periods),
                    "source_id": candidate.source_id,
                },
            )
            filing_terminal_status: str | None = None
            try:
                async for event in run_cn_download_single_filing_stream(
                    batching_repository=host.batching_repository,
                    source_repository=host.source_repository,
                    blob_repository=host.blob_repository,
                    processed_repository=host.processed_repository,
                    discovery_client=discovery,
                    pdf_download_gate=host.pdf_download_gate,
                    docling_conversion_runner=host.docling_conversion_runner,
                    ticker=normalized_ticker,
                    profile=profile,
                    candidate=candidate,
                    overwrite=overwrite,
                    cancel_checker=cancel_checker,
                    module=module,
                ):
                    item = event.payload.get("filing_result")
                    if isinstance(item, dict) and event.event_type in {
                        DownloadEventType.FILING_COMPLETED,
                        DownloadEventType.FILING_FAILED,
                    }:
                        filing_result: JsonObject = dict(item)
                        filing_terminal_status = str(filing_result.get("status", "failed"))
                        filings.append(filing_result)
                        _log_filing_download_result(
                            module=module,
                            ticker=normalized_ticker,
                            filing_result=filing_result,
                        )
                    yield event
            except CnDownloadCancelledError:
                notes.append("cancelled")
                cancelled = True
                break
            except Exception as exc:
                reason_code, reason_message = project_cn_filing_failure(exc)
                failed_item = _build_candidate_failed_result(
                    ticker=normalized_ticker,
                    candidate=candidate,
                    reason_code=reason_code,
                    reason_message=reason_message,
                )
                filing_terminal_status = "failed"
                filings.append(failed_item)
                _log_filing_download_result(
                    module=module,
                    ticker=normalized_ticker,
                    filing_result=failed_item,
                )
                yield DownloadEvent(
                    event_type=DownloadEventType.FILING_FAILED,
                    ticker=normalized_ticker,
                    document_id=str(failed_item["document_id"]),
                    payload=_filing_event_payload(failed_item),
                )
            if document_id == repair_document_id and not repair_gate_completed:
                if filing_terminal_status == "failed":
                    # 单 filing owner 已投影失败；repair gate 直接终止，company 保持旧值。
                    break
                post_repair = classify_source_integrity_preflight(
                    host.source_repository.list_source_integrity(normalized_ticker),
                    accepted_filing_ids=accepted_filing_ids,
                    rejected_filing_ids=frozenset(),
                )
                if isinstance(post_repair, SelectedSourceRepairRequired):
                    raise SourceIntegrityRevisionConflictError
                _raise_if_cancelled(
                    module=module,
                    ticker=normalized_ticker,
                    document_id=document_id,
                    cancel_checker=cancel_checker,
                )
                _publish_cn_company_after_repair(
                    host=host,
                    profile=profile,
                    normalized_ticker=normalized_ticker,
                    ticker_aliases=ticker_aliases,
                )
                repair_gate_completed = True
    except CnDownloadCancelledError:
        notes.append("cancelled")
        cancelled = True

    try:
        final_cancelled = cancelled or _is_cancel_requested(cancel_checker)
    except CnDownloadCancelledError:
        final_cancelled = True

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    summary = _build_summary(filings=filings, elapsed_ms=elapsed_ms)
    result = _build_result(
        pipeline_name=pipeline_name,
        status="cancelled" if final_cancelled else "ok",
        ticker=normalized_ticker,
        company_info=company_info,
        filters={
            "forms": list(period_policy.effective_periods),
            "start_dates": {item.fiscal_period: item.start_date for item in period_windows},
            "end_date": window.end_date,
            "overwrite": overwrite,
        },
        warnings=warnings,
        notes=notes,
        filings=filings,
        missing_periods=missing_periods,
        summary=summary,
    )
    Log.info(
        (
            "CN/HK 下载完成: "
            f"ticker={normalized_ticker} total={summary['total']} "
            f"downloaded={summary['downloaded']} skipped={summary['skipped']} "
            f"failed={summary['failed']} elapsed_ms={summary['elapsed_ms']}"
        ),
        module=module,
    )
    yield DownloadEvent(
        event_type=DownloadEventType.PIPELINE_COMPLETED,
        ticker=normalized_ticker,
        payload={"result": result},
    )


def _select_discovery_client(
    *,
    host: CnDownloadWorkflowHost,
    market: CnMarketKind,
) -> CnReportDiscoveryClientProtocol:
    """按市场选择 discovery client。"""

    return host.cn_discovery_client if market == "CN" else host.hk_discovery_client


def _publish_cn_company_after_repair(
    *,
    host: CnDownloadWorkflowHost,
    profile: CnCompanyProfile,
    normalized_ticker: str,
    ticker_aliases: list[str] | None,
) -> None:
    """在 whole-tree clean gate 后以独立 atomic batch 发布 company meta。

    Args:
        host: CN/HK workflow host。
        profile: provider 已解析的公司 profile。
        normalized_ticker: canonical ticker。
        ticker_aliases: request 传入的可选 aliases。

    Returns:
        无。

    Raises:
        OSError: company storage batch 失败时抛出。
        ValueError: company facts 或 batch capability 非法时抛出。
    """

    company_batch = host.batching_repository.begin_batch(normalized_ticker)
    try:
        stage_company_meta_for_cn_download(
            repository=host.company_meta_repository,
            profile=profile,
            normalized_ticker=normalized_ticker,
            ticker_aliases=ticker_aliases,
            batch=company_batch,
        )
    except BaseException:
        host.batching_repository.rollback_batch(company_batch)
        raise
    host.batching_repository.commit_batch(company_batch)


def _is_cancel_requested(cancel_checker: Callable[[], bool] | None) -> bool:
    """安全检查取消信号。

    Args:
        cancel_checker: 可选取消检查函数。

    Returns:
        True 表示已取消。

    Raises:
        CnDownloadCancelledError: ``cancel_checker`` 主动抛出取消异常时原样传播。
        Exception: provider、storage 或 execution 异常原样传播。
    """

    if cancel_checker is None:
        return False
    return cancel_checker()


def _raise_if_cancelled(
    *,
    module: str,
    ticker: str,
    document_id: str,
    cancel_checker: Callable[[], bool] | None,
) -> None:
    """在 CN/HK ticker 级阶段边界检查取消请求。

    Args:
        module: 日志模块名。
        ticker: 当前 ticker。
        document_id: 可选当前文档 ID。
        cancel_checker: 可选取消检查函数。

    Returns:
        无。

    Raises:
        CnDownloadCancelledError: 取消检查命中时抛出。
        RuntimeError: ``cancel_checker`` 自身失败时抛出。
    """

    if not _is_cancel_requested(cancel_checker):
        return
    Log.info(
        f"CN/HK 下载收到取消请求: ticker={ticker} document_id={document_id}",
        module=module,
    )
    raise CnDownloadCancelledError("操作已被取消")


def _coerce_market(raw: str) -> CnMarketKind:
    """把 ticker_normalization 市场收窄为 CN/HK 字面量。"""

    if raw == "CN":
        return "CN"
    if raw == "HK":
        return "HK"
    raise ValueError(f"不支持的 market: {raw}")


def _select_candidates_for_a4(
    candidates: tuple[CnReportCandidate, ...],
    *,
    period_windows: tuple[PeriodDownloadWindow, ...],
    use_default_business_limits: bool,
) -> tuple[CnReportCandidate, ...]:
    """返回 downloader 在窗口内选出的全部候选。

    Args:
        candidates: downloader 已按 ``(fiscal_year, fiscal_period)`` 去重后的候选。
        period_windows: 各财期业务窗口；默认年报 5 年、半年报/季报 2 年。
        use_default_business_limits: 是否启用默认业务数量约束；显式 start_date 时
            只按用户窗口过滤。

    Returns:
        业务窗口内的候选 tuple。

    Raises:
        无。
    """

    windows = {item.fiscal_period: item for item in period_windows}
    preselected: list[CnReportCandidate] = []
    for candidate in candidates:
        window = windows.get(candidate.period_projection.identity_period)
        if window is None:
            continue
        if window.start_date <= candidate.filing_date <= window.end_date:
            preselected.append(candidate)
    if not use_default_business_limits:
        return tuple(preselected)
    return _apply_default_business_limits(preselected, period_windows=period_windows)


def _apply_default_business_limits(
    candidates: list[CnReportCandidate],
    *,
    period_windows: tuple[PeriodDownloadWindow, ...],
) -> tuple[CnReportCandidate, ...]:
    """应用默认业务数量约束：FY 5 年，半年报/季报当前和上一 fiscal year。"""

    end_years = {item.fiscal_period: _year_from_iso_date(item.end_date) for item in period_windows}
    fy_count = 0
    selected: list[CnReportCandidate] = []
    for candidate in candidates:
        end_year = end_years.get(candidate.period_projection.identity_period)
        if end_year is None:
            continue
        if candidate.period_projection.identity_period == "FY":
            if fy_count >= 5:
                continue
            fy_count += 1
            selected.append(candidate)
            continue
        if end_year - 1 <= candidate.fiscal_year <= end_year:
            selected.append(candidate)
    return tuple(selected)


def _year_from_iso_date(value: str) -> int:
    """从 ``YYYY-MM-DD`` 字符串提取年份。"""

    return int(value[:4])


def _resolve_missing_periods(
    missing_eligible_periods: tuple[CnFiscalPeriod, ...],
    selected: tuple[CnReportCandidate, ...],
) -> tuple[CnFiscalPeriod, ...]:
    """只按 missing eligibility 与候选 identity period 计算缺失财期。

    Args:
        missing_eligible_periods: policy owner 允许报告 missing 的 canonical 财期。
        selected: workflow 已选择的候选；仅消费其 identity fiscal period。

    Returns:
        保持 policy canonical 顺序的缺失财期 tuple。

    Raises:
        无。
    """

    found = {item.period_projection.identity_period for item in selected}
    return tuple(period for period in missing_eligible_periods if period not in found)


def _build_candidate_failed_result(
    *,
    ticker: str,
    candidate: CnReportCandidate,
    reason_code: str,
    reason_message: str,
) -> JsonObject:
    """构建单候选异常失败结果。

    Args:
        ticker: ticker。
        candidate: 远端候选。
        reason_code: 稳定原因码。
        reason_message: 失败说明。

    Returns:
        单 filing 失败结果。

    Raises:
        无。
    """

    return {
        "document_id": _candidate_document_id(ticker, candidate),
        "status": "failed",
        "form_type": candidate.period_projection.identity_period,
        "filing_date": candidate.filing_date,
        "report_date": None,
        "fiscal_year": candidate.fiscal_year,
        "fiscal_period": candidate.period_projection.identity_period,
        "covered_fiscal_periods": list(candidate.period_projection.covered_periods),
        "downloaded_files": 0,
        "skipped_files": 0,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": reason_code,
        "reason_message": reason_message,
    }


def _filing_event_payload(filing_result: JsonObject) -> dict[str, JsonValue]:
    """构建单 filing 事件 payload。

    Args:
        filing_result: 单 filing 结果。

    Returns:
        同时包含展开字段和 ``filing_result`` 子对象的事件 payload。

    Raises:
        无。
    """

    payload: dict[str, JsonValue] = dict(filing_result)
    payload["filing_result"] = cast(JsonValue, filing_result)
    return payload


def _log_filing_download_result(
    *,
    module: str,
    ticker: str,
    filing_result: JsonObject,
) -> None:
    """输出单个 CN/HK filing 下载完成日志。

    Args:
        module: 日志模块名。
        ticker: 股票代码。
        filing_result: 单个 filing 的下载结果字典。

    Returns:
        无。

    Raises:
        无。
    """

    document_id = _optional_log_text(filing_result.get("document_id"))
    status = _optional_log_text(filing_result.get("status")) or "unknown"
    form_type = _optional_log_text(filing_result.get("form_type"))
    filing_date = _optional_log_text(filing_result.get("filing_date"))
    report_date = _optional_log_text(filing_result.get("report_date"))
    downloaded_files = _log_int(filing_result.get("downloaded_files"))
    skipped_files = _log_int(filing_result.get("skipped_files"))
    failed_files = filing_result.get("failed_files")
    failed_count = len(failed_files) if isinstance(failed_files, list) else 0
    skip_reason = _optional_log_text(filing_result.get("skip_reason"))
    reason_code = _optional_log_text(filing_result.get("reason_code"))
    reason_message = _optional_log_text(filing_result.get("reason_message"))
    filter_category = _optional_log_text(filing_result.get("filter_category"))
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
        module=module,
    )


def _optional_log_text(value: JsonValue | None) -> str | None:
    """把日志字段转换为可读字符串。

    Args:
        value: JSON 字段值。

    Returns:
        ``None`` 或字符串。

    Raises:
        无。
    """

    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def _log_int(value: JsonValue | None) -> int:
    """把日志数值字段转换为整数。

    Args:
        value: JSON 字段值。

    Returns:
        可安全记录的整数；无法解析时返回 0。

    Raises:
        无。
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _build_summary(*, filings: list[JsonObject], elapsed_ms: int) -> JsonObject:
    """构建下载 summary。"""

    return {
        "total": len(filings),
        "downloaded": sum(1 for item in filings if item.get("status") == "downloaded"),
        "skipped": sum(1 for item in filings if item.get("status") == "skipped"),
        "failed": sum(1 for item in filings if item.get("status") == "failed"),
        "elapsed_ms": elapsed_ms,
        "reused_downloads": sum(1 for item in filings if item.get("reused_pdf") is True),
        "converted": sum(1 for item in filings if item.get("converted") is True),
    }


def _build_result(
    *,
    pipeline_name: str,
    status: str,
    ticker: str,
    reason_code: str | None = None,
    message: str | None = None,
    company_info: JsonObject | None = None,
    filters: JsonObject | None = None,
    warnings: list[str] | None = None,
    notes: list[str] | None = None,
    filings: list[JsonObject] | None = None,
    missing_periods: tuple[str, ...] = (),
    summary: JsonObject | None = None,
) -> JsonObject:
    """构建 pipeline download 结果。

    Args:
        pipeline_name: 来源 pipeline 名称。
        status: pipeline 终态。
        ticker: canonical ticker。
        reason_code: 可选失败原因码。
        message: 可选失败说明。
        company_info: 公司业务事实。
        filters: 生效筛选条件。
        warnings: 用户可读 warning。
        notes: pipeline notes。
        filings: 真实 provider candidates 的结果。
        missing_periods: 主源没有候选的请求财期；不属于 document outcome。
        summary: 从真实 filing 结果计算的计数。

    Returns:
        统一 pipeline download 结果。

    Raises:
        无。
    """

    warning_values: list[JsonValue] = list(warnings or [])
    note_values: list[JsonValue] = list(notes or [])
    filing_values: list[JsonValue] = list(filings or [])
    return {
        "pipeline": pipeline_name,
        "action": "download",
        "status": status,
        "ticker": ticker,
        "reason_code": reason_code,
        "message": message,
        "company_info": company_info or {},
        "filters": filters or {},
        "warnings": warning_values,
        "notes": note_values,
        "filings": filing_values,
        "missing_periods": list(missing_periods),
        "summary": summary
        or {
            "total": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "elapsed_ms": 0,
            "reused_downloads": 0,
            "converted": 0,
        },
    }


def _candidate_document_id(ticker: str, candidate: CnReportCandidate) -> str:
    """构建单候选真实 document_id。

    Args:
        ticker: 已归一化 ticker。
        candidate: 远端候选。

    Returns:
        与单 filing 阶段机一致的 source document ID。

    Raises:
        无。
    """

    document_id, _ = build_cn_filing_ids(
        ticker=ticker,
        form_type=candidate.period_projection.identity_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.period_projection.identity_period,
        amended=candidate.amended,
    )
    return document_id


__all__ = ["run_cn_download_stream_impl"]
