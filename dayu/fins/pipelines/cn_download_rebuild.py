"""CN/HK 下载本地重建工作流。

本模块只基于已经落盘的 source meta 与文件条目重建 ``meta.json`` /
``filing_manifest.json``，不访问巨潮、披露易或 Docling。文档存取统一经
``dayu.fins.storage`` 仓储协议完成。
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FinsIngestMethod, FilingUpdateRequest, now_iso8601
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import (
    CN_FISCAL_PERIOD_ORDER,
    CN_PIPELINE_DOWNLOAD_VERSION,
    CnFiscalPeriod,
    CnMarketKind,
)
from dayu.fins.pipelines.cn_download_protocols import CnDownloadWorkflowHost
from dayu.fins.pipelines.cn_form_utils import (
    PeriodDownloadWindow,
    resolve_period_windows,
    resolve_download_period_policy,
)

JsonObject: TypeAlias = dict[str, JsonValue]

_DOCLING_SUFFIX = "_docling.json"
_PDF_SUFFIX = ".pdf"


def rebuild_cn_download_artifacts(
    *,
    host: CnDownloadWorkflowHost,
    ticker: str,
    market: CnMarketKind,
    form_type: str | None,
    start_date: str | None,
    end_date: str | None,
    overwrite: bool,
    pipeline_name: str,
    cancel_checker: Callable[[], bool] | None = None,
) -> JsonObject:
    """基于本地 CN/HK 下载结果重建 source meta 与 manifest。

    Args:
        host: CN/HK 下载 workflow 宿主协议。
        ticker: 已归一化 ticker。
        market: 已归一化市场。
        form_type: 可选 form 输入。
        start_date: 可选窗口起点。
        end_date: 可选窗口终点。
        overwrite: 是否覆盖；rebuild 不下载远端文件，仅回填 filters。
        pipeline_name: pipeline 名称。
        cancel_checker: 可选取消检查函数。

    Returns:
        download 结果字典。

    Raises:
        ValueError: form/date 参数非法时抛出。
        OSError: 仓储写入失败时抛出。
    """

    period_policy = resolve_download_period_policy(form_type, market)
    period_windows = resolve_period_windows(
        discovery_periods=period_policy.discovery_periods,
        start_date=start_date,
        end_date=end_date,
    )
    started_at = time.perf_counter()
    filings: list[JsonObject] = []
    document_ids = host.source_repository.list_source_document_ids(ticker, SourceKind.FILING)
    cancelled = False
    for document_id in document_ids:
        if _is_cancel_requested(cancel_checker):
            cancelled = True
            break
        previous_meta = host.source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)
        meta = dict(previous_meta)
        period_projection = _resolve_rebuild_period_projection(meta=meta, period_windows=period_windows)
        if period_projection is None:
            continue
        filings.append(
            _rebuild_single_cn_download_document(
                host=host,
                ticker=ticker,
                document_id=document_id,
                previous_meta=meta,
                covered_fiscal_periods=period_projection[1],
            )
        )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    warnings: list[str] = []
    if not filings:
        warnings.append("未匹配到可重建的已下载 CN/HK filings")
    form_values: list[JsonValue] = [period for period in period_policy.effective_periods]
    warning_values: list[JsonValue] = [warning for warning in warnings]
    note_values: list[JsonValue] = []
    if cancelled:
        note_values.append("cancelled")
    filing_values: list[JsonValue] = [filing for filing in filings]
    result: JsonObject = {
        "pipeline": pipeline_name,
        "action": "download",
        "status": "cancelled" if cancelled else "ok",
        "ticker": ticker,
        "company_info": {},
        "filters": {
            "forms": form_values,
            "start_dates": {item.fiscal_period: item.start_date for item in period_windows},
            "end_date": period_windows[0].end_date if period_windows else end_date,
            "overwrite": overwrite,
            "rebuild": True,
        },
        "warnings": warning_values,
        "notes": note_values,
        "filings": filing_values,
        "missing_periods": [],
        "summary": _build_rebuild_summary(filings=filings, elapsed_ms=elapsed_ms),
    }
    return result


def _resolve_rebuild_period_projection(
    *,
    meta: JsonObject,
    period_windows: tuple[PeriodDownloadWindow, ...],
) -> tuple[CnFiscalPeriod, tuple[CnFiscalPeriod, ...]] | None:
    """严格解析 source 财期投影，并判断是否属于本次 rebuild 范围。

    Args:
        meta: source meta。
        period_windows: 本次 discovery 财期窗口。

    Returns:
        命中范围时返回身份与覆盖财期；不属于 CN/HK download 范围时返回
        ``None``。

    Raises:
        ValueError: 命中 CN/HK download source 的 coverage schema 非法时抛出。
    """

    if FinsIngestMethod.from_storage_value(str(meta["ingest_method"])) is not FinsIngestMethod.DOWNLOAD:
        return None
    if bool(meta.get("is_deleted", False)):
        return None
    period = _optional_period(meta.get("fiscal_period"))
    if period is None:
        return None
    covered_fiscal_periods = _required_covered_fiscal_periods(meta, identity_period=period)
    matched_window = next((item for item in period_windows if item.fiscal_period == period), None)
    if matched_window is None:
        return None
    filing_date = _optional_text(meta.get("filing_date"))
    if filing_date is None:
        return None
    if not matched_window.start_date <= filing_date <= matched_window.end_date:
        return None
    return period, covered_fiscal_periods


def _rebuild_single_cn_download_document(
    *,
    host: CnDownloadWorkflowHost,
    ticker: str,
    document_id: str,
    previous_meta: JsonObject,
    covered_fiscal_periods: tuple[CnFiscalPeriod, ...],
) -> JsonObject:
    """重建单个 CN/HK 本地下载文档。

    Args:
        host: CN/HK workflow 宿主。
        ticker: canonical ticker。
        document_id: source 文档 ID。
        previous_meta: 已验证属于本次范围的 source meta。
        covered_fiscal_periods: 已严格解析的覆盖财期。

    Returns:
        单文档 rebuild 结果。

    Raises:
        OSError: 仓储操作失败时抛出。
    """

    internal_document_id = _required_text(previous_meta, "internal_document_id", document_id)
    form_type = _required_text(previous_meta, "form_type", "")
    filing_date = _optional_text(previous_meta.get("filing_date"))
    report_date = _optional_text(previous_meta.get("report_date"))
    file_entries = _extract_file_entries(previous_meta)
    if not form_type:
        return _failed_rebuild_result(
            document_id=document_id,
            internal_document_id=internal_document_id,
            reason_code="missing_form_type",
            reason_message="重建失败：meta.json 缺少 form_type",
            covered_fiscal_periods=covered_fiscal_periods,
        )
    if not _has_docling_file(file_entries):
        return _failed_rebuild_result(
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            filing_date=filing_date,
            report_date=report_date,
            reason_code="missing_docling_json",
            reason_message="重建失败：CN/HK 下载完成态缺少 Docling JSON",
            covered_fiscal_periods=covered_fiscal_periods,
        )
    if not _has_pdf_file(file_entries):
        return _failed_rebuild_result(
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            filing_date=filing_date,
            report_date=report_date,
            reason_code="missing_pdf",
            reason_message="重建失败：CN/HK 下载完成态缺少 PDF",
            covered_fiscal_periods=covered_fiscal_periods,
        )
    primary_document = _resolve_primary_document(previous_meta=previous_meta, file_entries=file_entries)
    if not primary_document:
        return _failed_rebuild_result(
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            filing_date=filing_date,
            report_date=report_date,
            reason_code="missing_primary_document",
            reason_message="重建失败：CN/HK 下载完成态缺少 primary_document",
            covered_fiscal_periods=covered_fiscal_periods,
        )
    source_fingerprint = _resolve_source_fingerprint(previous_meta=previous_meta, file_entries=file_entries)
    meta_payload = dict(previous_meta)
    file_values: list[JsonValue] = [item for item in file_entries]
    update_payload: JsonObject = {
        "document_id": document_id,
        "internal_document_id": internal_document_id,
        "ingest_method": FinsIngestMethod.DOWNLOAD.to_storage_value(),
        "ticker": ticker,
        "form_type": form_type,
        "primary_document": primary_document,
        "files": file_values,
        "ingest_complete": True,
        "download_version": CN_PIPELINE_DOWNLOAD_VERSION,
        "source_fingerprint": source_fingerprint,
        "updated_at": now_iso8601(),
    }
    meta_payload.update(update_payload)
    batch = host.batching_repository.begin_batch(ticker)
    try:
        host.source_repository.update_source_document(
            FilingUpdateRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=internal_document_id,
                form_type=form_type,
                primary_document=primary_document,
                file_entries=file_entries,
                meta=meta_payload,
            ),
            source_kind=SourceKind.FILING,
            batch=batch,
        )
    except BaseException:
        host.batching_repository.rollback_batch(batch)
        raise
    host.batching_repository.commit_batch(batch)
    return {
        "document_id": document_id,
        "internal_document_id": internal_document_id,
        "status": "downloaded",
        "form_type": form_type,
        "filing_date": filing_date,
        "report_date": report_date,
        "covered_fiscal_periods": list(covered_fiscal_periods),
        "downloaded_files": 0,
        "skipped_files": len(file_entries),
        "failed_files": [],
        "has_xbrl": False,
        "rebuild": True,
    }


def _extract_file_entries(meta: JsonObject) -> list[JsonObject]:
    """从 source meta 提取文件条目。"""

    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        return []
    return [dict(item) for item in raw_files if isinstance(item, dict)]


def _resolve_primary_document(*, previous_meta: JsonObject, file_entries: list[JsonObject]) -> str:
    """解析 CN/HK rebuild 完成态主文件名。"""

    raw_primary = _optional_text(previous_meta.get("primary_document"))
    if raw_primary is not None and raw_primary.endswith(_DOCLING_SUFFIX):
        return raw_primary
    for item in file_entries:
        name = _optional_text(item.get("name"))
        if name is not None and name.endswith(_DOCLING_SUFFIX):
            return name
    return raw_primary or _optional_text(file_entries[0].get("name")) or ""


def _is_cancel_requested(cancel_checker: Callable[[], bool] | None) -> bool:
    """安全检查取消信号。

    Args:
        cancel_checker: 可选取消检查函数。

    Returns:
        True 表示已取消。

    Raises:
        CnDownloadCancelledError: 检查器主动抛出的取消异常原样传播。
        Exception: provider、storage 或 execution 异常原样传播。
    """

    if cancel_checker is None:
        return False
    return cancel_checker()


def _resolve_source_fingerprint(*, previous_meta: JsonObject, file_entries: list[JsonObject]) -> str:
    """解析或重建 source fingerprint。"""

    previous_fingerprint = _optional_text(previous_meta.get("source_fingerprint"))
    if previous_fingerprint is not None:
        return previous_fingerprint
    pdf_sha = _find_entry_sha(file_entries, _PDF_SUFFIX)
    docling_sha = _find_entry_sha(file_entries, _DOCLING_SUFFIX)
    if pdf_sha is None or docling_sha is None:
        return ""
    return hashlib.sha256(f"{pdf_sha}|{docling_sha}".encode("utf-8")).hexdigest()


def _find_entry_sha(file_entries: list[JsonObject], suffix: str) -> str | None:
    """按文件后缀查找文件 SHA-256。"""

    for item in file_entries:
        name = _optional_text(item.get("name"))
        sha = _optional_text(item.get("sha256"))
        if name is not None and name.endswith(suffix) and sha is not None:
            return sha
    return None


def _has_docling_file(file_entries: list[JsonObject]) -> bool:
    """判断文件条目是否包含 Docling JSON。"""

    return any((_optional_text(item.get("name")) or "").endswith(_DOCLING_SUFFIX) for item in file_entries)


def _has_pdf_file(file_entries: list[JsonObject]) -> bool:
    """判断文件条目是否包含 PDF。"""

    return any((_optional_text(item.get("name")) or "").endswith(_PDF_SUFFIX) for item in file_entries)


def _failed_rebuild_result(
    *,
    document_id: str,
    internal_document_id: str,
    reason_code: str,
    reason_message: str,
    covered_fiscal_periods: tuple[CnFiscalPeriod, ...],
    form_type: str | None = None,
    filing_date: str | None = None,
    report_date: str | None = None,
) -> JsonObject:
    """构建单文档 rebuild 失败结果。

    Args:
        document_id: source 文档 ID。
        internal_document_id: 内部文档 ID。
        reason_code: 稳定失败原因码。
        reason_message: 失败说明。
        covered_fiscal_periods: 已验证的覆盖财期。
        form_type: 可选 form type。
        filing_date: 可选披露日期。
        report_date: 可选报告日期。

    Returns:
        单文档失败结果。

    Raises:
        无。
    """

    return {
        "document_id": document_id,
        "internal_document_id": internal_document_id,
        "status": "failed",
        "form_type": form_type,
        "filing_date": filing_date,
        "report_date": report_date,
        "covered_fiscal_periods": list(covered_fiscal_periods),
        "downloaded_files": 0,
        "skipped_files": 0,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": reason_code,
        "reason_message": reason_message,
        "rebuild": True,
    }


def _build_rebuild_summary(*, filings: list[JsonObject], elapsed_ms: int) -> JsonObject:
    """构建 CN/HK rebuild summary。"""

    return {
        "total": len(filings),
        "downloaded": sum(1 for item in filings if item.get("status") == "downloaded"),
        "skipped": sum(1 for item in filings if item.get("status") == "skipped"),
        "failed": sum(1 for item in filings if item.get("status") == "failed"),
        "elapsed_ms": elapsed_ms,
        "reused_downloads": 0,
        "converted": 0,
    }


def _optional_period(value: JsonValue | None) -> CnFiscalPeriod | None:
    """把 JSON 字段收窄为 CN/HK 财期。"""

    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if normalized == "FY":
        return "FY"
    if normalized == "H1":
        return "H1"
    if normalized == "Q1":
        return "Q1"
    if normalized == "Q2":
        return "Q2"
    if normalized == "Q3":
        return "Q3"
    if normalized == "Q4":
        return "Q4"
    return None


def _required_covered_fiscal_periods(
    meta: JsonObject,
    *,
    identity_period: CnFiscalPeriod,
) -> tuple[CnFiscalPeriod, ...]:
    """严格读取 fresh source schema 的覆盖财期。

    Args:
        meta: source meta。
        identity_period: source 身份财期。

    Returns:
        canonical ordered 覆盖财期。

    Raises:
        ValueError: 字段缺失、类型非法、重复、顺序非法或不含 identity 时抛出。
    """

    if "covered_fiscal_periods" not in meta or not isinstance(meta["covered_fiscal_periods"], list):
        raise ValueError("CN/HK rebuild source meta 的 covered_fiscal_periods 必须是列表")
    raw_periods = meta["covered_fiscal_periods"]
    assert isinstance(raw_periods, list)
    periods: list[CnFiscalPeriod] = []
    for index, value in enumerate(raw_periods):
        period = _optional_period(value)
        if period is None:
            raise ValueError(f"CN/HK rebuild covered_fiscal_periods[{index}] 非法")
        periods.append(period)
    if not periods:
        raise ValueError("CN/HK rebuild covered_fiscal_periods 不能为空")
    if len(set(periods)) != len(periods):
        raise ValueError("CN/HK rebuild covered_fiscal_periods 不能重复")
    canonical = tuple(period for period in CN_FISCAL_PERIOD_ORDER if period in periods)
    if tuple(periods) != canonical:
        raise ValueError("CN/HK rebuild covered_fiscal_periods 顺序非法")
    if identity_period not in periods:
        raise ValueError("CN/HK rebuild covered_fiscal_periods 必须包含 identity period")
    return tuple(periods)


def _optional_text(value: JsonValue | None) -> str | None:
    """把 JSON 字段转换为非空字符串。"""

    if not isinstance(value, (str, int, float, bool)):
        return None
    text = str(value).strip()
    return text or None


def _required_text(meta: JsonObject, key: str, fallback: str) -> str:
    """读取必需文本字段，缺失时使用 fallback。"""

    return _optional_text(meta.get(key)) or fallback


__all__ = ["rebuild_cn_download_artifacts"]
