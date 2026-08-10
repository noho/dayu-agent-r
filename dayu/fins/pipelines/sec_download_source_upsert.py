"""SecPipeline 下载成功后的 source upsert 真源模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

from collections.abc import Callable
from typing import Optional, Protocol

from dayu.fins.domain.document_models import (
    BatchToken,
    FinsIngestMethod,
    FinsSourceProvider,
    FilingCreateRequest,
    FilingUpdateRequest,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import ProcessedDocumentRepositoryProtocol, SourceDocumentRepositoryProtocol


class DownloadedFilingRecord(Protocol):
    """下载成功后写入 source meta 所需的 filing 最小字段边界。"""

    @property
    def accession_number(self) -> str:
        """返回 accession number。

        Returns:
            accession number。
        """

        ...

    @property
    def form_type(self) -> str:
        """返回 form type。

        Returns:
            form type。
        """

        ...

    @property
    def filing_date(self) -> str:
        """返回 filing date。

        Returns:
            filing date。
        """

        ...

    @property
    def report_date(self) -> Optional[str]:
        """返回 report date。

        Returns:
            report date。
        """

        ...


def upsert_downloaded_filing_source_document(
    *,
    ticker: str,
    cik: str,
    document_id: str,
    internal_document_id: str,
    filing: DownloadedFilingRecord,
    primary_document: str,
    file_entries: list[dict[str, JsonValue]],
    previous_meta: Optional[dict[str, JsonValue]],
    create_source: bool,
    source_fingerprint: str,
    download_version: str,
    has_xbrl: bool,
    inferred_fiscal_year: Optional[int],
    inferred_fiscal_period: Optional[str],
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    batch: BatchToken,
    resolve_document_version: Callable[[Optional[dict[str, JsonValue]], str], str],
    safe_get_processed_meta: Callable[[str, str], Optional[dict[str, JsonValue]]],
) -> None:
    """写入下载成功后的 filing source document，并按规则标记重处理。

    Args:
        ticker: 股票代码。
        cik: 公司 CIK。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        filing: filing 记录。
        primary_document: 当前写入的主文件名。
        file_entries: 已规范化的文件条目列表。
        previous_meta: 历史 filing source meta。
        create_source: 当前 staging target 已不存在、必须走 create 时为真。
        source_fingerprint: 当前远端文件指纹。
        download_version: 当前下载链路版本号。
        has_xbrl: 当前 filing 是否已落盘 XBRL instance。
        inferred_fiscal_year: 推断出的 fiscal year。
        inferred_fiscal_period: 推断出的 fiscal period。
        source_repository: source 仓储。
        processed_repository: processed 仓储。
        batch: caller 显式传入的 batch capability。
        resolve_document_version: 文档版本计算函数。
        safe_get_processed_meta: 安全读取 processed meta 的函数。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
        ValueError: 仓储参数不合法时抛出。
    """

    document_version = resolve_document_version(previous_meta, source_fingerprint)
    meta_payload = _build_downloaded_filing_meta_payload(
        ticker=ticker,
        cik=cik,
        document_id=document_id,
        internal_document_id=internal_document_id,
        filing=filing,
        previous_meta=previous_meta,
        source_fingerprint=source_fingerprint,
        download_version=download_version,
        has_xbrl=has_xbrl,
        inferred_fiscal_year=inferred_fiscal_year,
        inferred_fiscal_period=inferred_fiscal_period,
        document_version=document_version,
    )
    upsert_request = _build_filing_upsert_request(
        ticker=ticker,
        document_id=document_id,
        internal_document_id=internal_document_id,
        filing=filing,
        primary_document=primary_document,
        file_entries=file_entries,
        meta_payload=meta_payload,
        previous_meta=previous_meta,
    )
    if create_source:
        source_repository.create_source_document(
            upsert_request,
            source_kind=SourceKind.FILING,
            batch=batch,
        )
    else:
        source_repository.update_source_document(
            upsert_request,
            source_kind=SourceKind.FILING,
            batch=batch,
        )

    if _should_mark_processed_reprocess_required(
        ticker=ticker,
        document_id=document_id,
        previous_meta=previous_meta,
        source_fingerprint=source_fingerprint,
        safe_get_processed_meta=safe_get_processed_meta,
    ):
        processed_repository.mark_processed_reprocess_required(
            ticker,
            document_id,
            True,
            batch=batch,
        )


def _build_downloaded_filing_meta_payload(
    *,
    ticker: str,
    cik: str,
    document_id: str,
    internal_document_id: str,
    filing: DownloadedFilingRecord,
    previous_meta: Optional[dict[str, JsonValue]],
    source_fingerprint: str,
    download_version: str,
    has_xbrl: bool,
    inferred_fiscal_year: Optional[int],
    inferred_fiscal_period: Optional[str],
    document_version: str,
) -> dict[str, JsonValue]:
    """构建下载成功后的 source meta payload。

    Args:
        ticker: 股票代码。
        cik: 公司 CIK。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        filing: filing 记录。
        previous_meta: 历史 filing source meta。
        source_fingerprint: 当前远端文件指纹。
        download_version: 当前下载链路版本号。
        has_xbrl: 是否已落盘 XBRL instance。
        inferred_fiscal_year: 推断出的 fiscal year。
        inferred_fiscal_period: 推断出的 fiscal period。
        document_version: 当前文档版本号。

    Returns:
        可直接写入仓储的 meta payload。

    Raises:
        无。
    """

    # `first_ingested_at` 和 `created_at` 一旦存在就应保持稳定，避免重拉覆盖历史首入库时间。
    first_ingested_at = (
        str(previous_meta.get("first_ingested_at"))
        if previous_meta and previous_meta.get("first_ingested_at")
        else now_iso8601()
    )
    created_at = (
        str(previous_meta.get("created_at")) if previous_meta and previous_meta.get("created_at") else now_iso8601()
    )
    return {
        "document_id": document_id,
        "internal_document_id": internal_document_id,
        "accession_number": filing.accession_number,
        "ingest_method": FinsIngestMethod.DOWNLOAD.to_storage_value(),
        "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
        "ticker": ticker,
        "company_id": cik,
        "form_type": filing.form_type,
        "fiscal_year": inferred_fiscal_year,
        "fiscal_period": inferred_fiscal_period,
        "report_kind": None,
        "report_date": filing.report_date,
        "filing_date": filing.filing_date,
        "first_ingested_at": first_ingested_at,
        "ingest_complete": True,
        "is_deleted": False,
        "deleted_at": None,
        "document_version": document_version,
        "source_fingerprint": source_fingerprint,
        "amended": filing.form_type.endswith("/A"),
        "download_version": download_version,
        "created_at": created_at,
        "updated_at": now_iso8601(),
        "has_xbrl": has_xbrl,
    }


def _build_filing_upsert_request(
    *,
    ticker: str,
    document_id: str,
    internal_document_id: str,
    filing: DownloadedFilingRecord,
    primary_document: str,
    file_entries: list[dict[str, JsonValue]],
    meta_payload: dict[str, JsonValue],
    previous_meta: Optional[dict[str, JsonValue]],
) -> FilingCreateRequest | FilingUpdateRequest:
    """构建 filing create/update 请求。

    Args:
        ticker: 股票代码。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        filing: filing 记录。
        primary_document: 当前写入的主文件名。
        file_entries: 规范化文件条目。
        meta_payload: source meta payload。
        previous_meta: 历史 filing source meta。

    Returns:
        `FilingCreateRequest` 或 `FilingUpdateRequest`。

    Raises:
        无。
    """

    request_kwargs = {
        "ticker": ticker,
        "document_id": document_id,
        "internal_document_id": internal_document_id,
        "form_type": filing.form_type,
        "primary_document": primary_document,
        "file_entries": file_entries,
        "meta": meta_payload,
    }
    if previous_meta is None:
        return FilingCreateRequest(**request_kwargs)
    return FilingUpdateRequest(**request_kwargs)


def _should_mark_processed_reprocess_required(
    *,
    ticker: str,
    document_id: str,
    previous_meta: Optional[dict[str, JsonValue]],
    source_fingerprint: str,
    safe_get_processed_meta: Callable[[str, str], Optional[dict[str, JsonValue]]],
) -> bool:
    """判断下载成功后是否需要标记 processed 需重处理。

    Args:
        ticker: 股票代码。
        document_id: 文档 ID。
        previous_meta: 历史 filing source meta。
        source_fingerprint: 当前远端文件指纹。
        safe_get_processed_meta: 安全读取 processed meta 的函数。

    Returns:
        `True` 表示应标记重处理；否则返回 `False`。

    Raises:
        无。
    """

    if previous_meta is None:
        return safe_get_processed_meta(ticker, document_id) is not None
    previous_source_fingerprint = str(previous_meta.get("source_fingerprint") or "").strip()
    return bool(previous_source_fingerprint) and previous_source_fingerprint != source_fingerprint
