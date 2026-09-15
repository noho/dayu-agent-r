"""在既有本地 rebuild 入口内重投影港股财期；仅发布元数据。"""

import json
from collections.abc import Callable

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FilingUpdateRequest, ProcessedUpdateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_protocols import CnDownloadWorkflowHost
from dayu.fins.pipelines.cn_form_utils import PeriodDownloadWindow
from dayu.fins.pipelines.cn_report_selection import resolve_hk_report_period
from dayu.fins.pipelines.hk_fiscal_calendar import annual_end_dates, report_end_date
from dayu.fins.storage import SourceIntegrityStatus

_PERIOD_VERSION = "hk-period-v2"


def rebuild_hk_periods(
    host: CnDownloadWorkflowHost,
    ticker: str,
    windows: tuple[PeriodDownloadWindow, ...],
    cancel_checker: Callable[[], bool] | None,
) -> tuple[list[dict[str, JsonValue]], bool]:
    """从同公司本地来源标题重投影财期，并原子同步 source/manifest/processed 索引。

    参数：host 为仓储宿主；ticker 为公司；windows 按旧或新身份圈定范围；
        cancel_checker 为取消检查。返回：逐文档结果及取消状态。
    异常：仓储或校验异常透传且回滚；commit 自己负责提交失败清理。
    """
    batch = host.batching_repository.begin_batch(ticker)
    filings: list[dict[str, JsonValue]] = []
    changed = False
    cancelled = False
    try:
        # 先取得 ticker writer lock 再读取，避免并发重建用锁外旧 meta 覆盖新状态。
        metas = {
            doc: dict(host.source_repository.get_source_meta(ticker, doc, SourceKind.FILING))
            for doc in host.source_repository.list_source_document_ids(ticker, SourceKind.FILING)
        }
        sources = {
            doc: meta
            for doc, meta in metas.items()
            if meta.get("source_provider") == "hkexnews"
            and meta.get("ingest_method") == "download"
            and meta.get("is_deleted") is False
        }
        anchors = {
            doc: str(meta.get("source_title", ""))
            for doc, meta in sources.items()
            if annual_end_dates((str(meta.get("source_title", "")),))
            and host.source_repository.classify_staged_source_integrity(
                ticker, doc, SourceKind.FILING, batch=batch
            ).status
            is SourceIntegrityStatus.COMPLETE
        }
        ends = annual_end_dates(tuple(anchors.values()))
        for document_id, meta in sources.items():
            if cancel_checker is not None and cancel_checker():
                cancelled = True
                break
            title = str(meta.get("source_title", ""))
            # 老缓存未存分类时，只使用标题本身的 report/results 事实，不复用旧季度猜分类。
            category = str(meta.get("source_category") or title)
            facts = resolve_hk_report_period(title=title, category_text=category, annual_ends=ends)
            period = facts[1].identity_period if facts is not None else None
            filing_date = str(meta.get("filing_date", ""))
            if not any(
                w.fiscal_period in (meta.get("fiscal_period"), period) and w.start_date <= filing_date <= w.end_date
                for w in windows
            ):
                continue
            result: dict[str, JsonValue] = {
                "document_id": document_id,
                "internal_document_id": meta.get("internal_document_id"),
                "form_type": meta.get("form_type"),
                "filing_date": filing_date,
                "report_date": meta.get("report_date"),
                "covered_fiscal_periods": meta.get("covered_fiscal_periods"),
                "status": "failed",
                "downloaded_files": 0,
                "skipped_files": 0,
                "failed_files": [],
                "has_xbrl": False,
                "rebuild": True,
            }
            filings.append(result)
            if facts is None:
                result.update(
                    reason_code="uncertain_hk_period",
                    reason_message="财期依据不足或冲突，保留原文档；需补齐明确年度截止日来源后重试",
                )
                continue
            integrity = host.source_repository.classify_staged_source_integrity(
                ticker,
                document_id,
                SourceKind.FILING,
                batch=batch,
            )
            if integrity.status is not SourceIntegrityStatus.COMPLETE:
                result.update(reason_code="incomplete_source", reason_message="本地来源不完整，不能仅纠正财期")
                continue
            year, projection = facts
            end = report_end_date(title)
            updates: dict[str, JsonValue] = {
                "form_type": projection.identity_period,
                "fiscal_period": projection.identity_period,
                "report_kind": projection.identity_period,
                "fiscal_year": year,
                "covered_fiscal_periods": list(projection.covered_periods),
                "report_date": end.isoformat() if end is not None else meta.get("report_date"),
                "fiscal_year_source": "source_title_and_annual_end",
                "report_date_source": "source_title" if end is not None else meta.get("report_date_source"),
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
            meta.update(updates)
            host.source_repository.update_source_document(
                FilingUpdateRequest(
                    ticker=ticker,
                    document_id=document_id,
                    internal_document_id=str(meta["internal_document_id"]),
                    form_type=projection.identity_period,
                    meta=meta,
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
                        internal_document_id=str(meta["internal_document_id"]),
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
    return filings, cancelled
