"""在既有本地 rebuild 入口内重投影港股财期；仅发布元数据。"""

import json
from collections.abc import Callable, Mapping

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FilingUpdateRequest, ProcessedUpdateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_protocols import CnDownloadWorkflowHost
from dayu.fins.pipelines.cn_form_utils import PeriodDownloadWindow
from dayu.fins.pipelines.cn_report_selection import resolve_hk_report_period, local_hk_annual_ends
from dayu.fins.pipelines.hk_fiscal_calendar import report_end_date, hk_report_date_source
from dayu.fins.download_contract import FinsDownloadUncertainReport
from dayu.fins.storage import SourceIntegrityStatus

_PERIOD_VERSION = "hk-period-v3"


def rebuild_hk_periods(
    host: CnDownloadWorkflowHost,
    ticker: str,
    windows: tuple[PeriodDownloadWindow, ...],
    cancel_checker: Callable[[], bool] | None,
) -> tuple[list[dict[str, JsonValue]], tuple[FinsDownloadUncertainReport, ...], bool]:
    """从同公司本地来源标题重投影财期，并原子同步 source/manifest/processed 索引。

    参数：host 为仓储宿主；ticker 为公司；windows 按旧或新身份圈定范围；
        cancel_checker 为取消检查。
    返回：已确认逐文档结果、独立未知 tuple 及取消状态；未知不携带旧财期标签。
    异常：仓储或校验异常透传且回滚；commit 自己负责提交失败清理。
    """
    if cancel_checker is not None and cancel_checker():
        return [], (), True
    batch = host.batching_repository.begin_batch(ticker)
    filings: list[dict[str, JsonValue]] = []
    uncertain: list[FinsDownloadUncertainReport] = []
    changed = False
    cancelled = False
    try:
        # writer capability 的 staging 是 raw 与完整性唯一根，不拼接 published 观察。
        entries = host.source_repository.read_source_meta_integrity_view(ticker, SourceKind.FILING, batch=batch)
        if cancel_checker is not None and cancel_checker():
            host.batching_repository.rollback_batch(batch)
            return [], (), True
        anchors = local_hk_annual_ends(entries)
        ends = tuple(sorted(set(anchors.values())))
        sources = {
            entry.document_id: entry for entry in entries
            if entry.source_meta.get("source_provider") == "hkexnews"
            and entry.source_meta.get("ingest_method") == "download"
            and entry.source_meta.get("is_deleted") is False
        }
        for document_id, entry in sources.items():
            meta = entry.source_meta
            if cancel_checker is not None and cancel_checker():
                cancelled = True
                break
            title = _required_meta_text(meta, "source_title")
            # 老缓存未存分类时，只使用标题本身的 report/results 事实，不复用旧季度猜分类。
            raw_category = meta.get("source_category")
            if raw_category is not None and not isinstance(raw_category, str):
                raise ValueError("source_category must be text or null")
            category = raw_category or title
            facts = resolve_hk_report_period(title=title, category_text=category, annual_ends=ends)
            period = facts[1].identity_period if facts is not None else None
            filing_date = _required_meta_text(meta, "filing_date")
            if not any(
                w.fiscal_period in (meta.get("fiscal_period"), period) and w.start_date <= filing_date <= w.end_date
                for w in windows
            ):
                continue
            end = report_end_date(title)
            report_date = end.isoformat() if end is not None else None
            if facts is None:
                uncertain.append(FinsDownloadUncertainReport(
                    source_id=_required_meta_text(meta, "source_id"), filing_date=filing_date,
                    report_date=report_date, existing_document_id=document_id, reason_category="uncertain_hk_period",
                ))
                continue
            year, projection = facts
            result: dict[str, JsonValue] = {
                "document_id": document_id, "internal_document_id": meta["internal_document_id"],
                "form_type": projection.identity_period, "filing_date": filing_date, "report_date": report_date,
                "covered_fiscal_periods": list(projection.covered_periods),
                "status": "failed", "downloaded_files": 0, "skipped_files": 0,
                "failed_files": [], "has_xbrl": False, "rebuild": True,
            }
            filings.append(result)
            integrity = entry.integrity
            if integrity.status is not SourceIntegrityStatus.COMPLETE:
                result.update(reason_code="incomplete_source", reason_message="本地来源不完整，不能仅纠正财期")
                continue
            updates: dict[str, JsonValue] = {
                "form_type": projection.identity_period,
                "fiscal_period": projection.identity_period,
                "report_kind": projection.identity_period,
                "fiscal_year": year,
                "covered_fiscal_periods": list(projection.covered_periods),
                "report_date": report_date,
                "fiscal_year_source": "source_title_and_annual_end",
                "report_date_source": hk_report_date_source(report_date),
                "period_resolution_version": _PERIOD_VERSION,
                "period_resolution_sources": [doc for doc in sorted(anchors)],
            }
            result.update(
                form_type=projection.identity_period,
                covered_fiscal_periods=list(projection.covered_periods),
                report_date=updates["report_date"],
                status="skipped",
            )
            if all(meta.get(key) == value for key, value in updates.items()):
                result.update(reason_code="period_metadata_current", reason_message="财期元数据已一致，无需更新")
                continue
            updated_meta = dict(meta)
            updated_meta.update(updates)
            host.source_repository.update_source_document(
                FilingUpdateRequest(
                    ticker=ticker,
                    document_id=document_id,
                    internal_document_id=_required_meta_text(meta, "internal_document_id"),
                    form_type=projection.identity_period,
                    meta=updated_meta,
                ),
                SourceKind.FILING,
                batch=batch,
            )
            # 解析文本未变化；同步 processed 的财期投影即可，不伪造内容版本变化。
            try:
                processed = host.processed_repository.get_processed_meta(ticker, document_id)
            except FileNotFoundError:
                processed = None
            if processed is not None:
                handle = host.processed_repository.get_processed_handle(ticker, document_id)
                financials: dict[str, JsonValue] | None = None
                if any(entry.name == "financials.json" for entry in host.blob_repository.list_entries(handle)):
                    raw: JsonValue = json.loads(host.blob_repository.read_file_bytes(handle, "financials.json"))
                    if not isinstance(raw, dict):
                        raise ValueError("processed financials 必须是 JSON 对象")
                    financials = raw
                host.processed_repository.update_processed(
                    ProcessedUpdateRequest(
                        ticker=ticker,
                        document_id=document_id,
                        internal_document_id=_required_meta_text(meta, "internal_document_id"),
                        source_kind=SourceKind.FILING.value,
                        form_type=projection.identity_period,
                        meta=updates,
                        financials=financials,
                    ),
                    batch=batch,
                )
            changed = True
            result["status"] = "downloaded"
        if cancel_checker is not None and cancel_checker():
            cancelled = True
    except BaseException:
        host.batching_repository.rollback_batch(batch)
        raise
    if cancelled or not changed:
        host.batching_repository.rollback_batch(batch)
        if cancelled:
            for result in filings:
                if result["status"] == "downloaded":
                    result.update(status="failed", reason_code="cancelled", reason_message="取消，元数据纠正已回滚")
    else:
        host.batching_repository.commit_batch(batch)
    if not cancelled and cancel_checker is not None and cancel_checker():
        cancelled = True
    return filings, tuple(sorted(uncertain, key=lambda r: (r.filing_date or "", r.source_id, r.existing_document_id or ""))), cancelled


def _required_meta_text(meta: Mapping[str, JsonValue], key: str) -> str:
    """读取重建所需的来源必填文本。

    参数：meta 为来源元数据；key 为必填字段名。
    返回：未经转换的非空原文本。
    异常：缺字段时原样抛 KeyError；空或非文本值抛 ValueError。
    """
    value = meta[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"HK source {key} must be non-empty text")
    return value
