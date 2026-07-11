"""SEC 上传工作流模块。

本模块承载 OLD SEC filing/material upload stream 业务规则，pipeline facade
只提供 downloader、仓储和上传服务等最小宿主边界。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Protocol, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FinsIngestMethod
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.sec_downloader import SecDownloader
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    UploadCancellationChecker,
    build_material_ids,
    build_sec_filing_ids,
    derive_report_kind,
    resolve_upload_action,
    validate_material_upload_ids,
)
from dayu.fins.pipelines.upload_company_meta import build_upload_company_id, upsert_company_meta_for_upload
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent, UploadFilingEventType
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent, UploadMaterialEventType
from dayu.fins.pipelines.upload_progress_helpers import (
    map_upload_file_event_to_filing_event_type as _map_upload_file_event_to_filing_event_type,
    map_upload_file_event_to_material_event_type as _map_upload_file_event_to_material_event_type,
)
from dayu.fins.storage import CompanyMetaRepositoryProtocol, SourceDocumentRepositoryProtocol
from dayu.fins.ticker_normalization import normalize_ticker

JsonObject: TypeAlias = dict[str, JsonValue]


class SecUploadWorkflowHost(Protocol):
    """SEC upload 工作流所需的最小宿主边界。"""

    @property
    def _downloader(self) -> SecDownloader:
        """返回 SEC 下载器实例。"""

        ...

    @property
    def _company_repository(self) -> CompanyMetaRepositoryProtocol:
        """返回公司元数据仓储。"""

        ...

    @property
    def _upload_service(self) -> DoclingUploadService:
        """返回上传服务。"""

        ...

    @property
    def _source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回源文档仓储。"""

        ...

    def _safe_get_document_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> JsonObject | None:
        """安全读取 source meta。"""

        ...

    def _build_result(self, action: str, **payload: JsonValue) -> JsonObject:
        """构建统一结果。"""

        ...


async def collect_upload_result_from_events(
    stream: AsyncIterator[UploadFilingEvent | UploadMaterialEvent],
    *,
    stream_name: str,
) -> JsonObject:
    """从上传事件流中提取最终结果。

    Args:
        stream: 上传事件流。
        stream_name: 事件流名称。

    Returns:
        最终结果字典。

    Raises:
        RuntimeError: 事件流未返回有效最终结果时抛出。
    """

    result: JsonObject | None = None
    async for event in stream:
        if event.event_type.value not in {"upload_completed", "upload_failed"}:
            continue
        payload_result = event.payload.get("result")
        if isinstance(payload_result, Mapping):
            result = dict(payload_result)
    if result is None:
        raise RuntimeError(f"{stream_name} 未返回最终结果")
    return result


async def run_upload_filing_stream(
    host: SecUploadWorkflowHost,
    *,
    ticker: str,
    action: str | None,
    files: list[Path],
    fiscal_year: int,
    fiscal_period: str,
    amended: bool = False,
    filing_date: str | None = None,
    report_date: str | None = None,
    company_id: str | None = None,
    company_name: str | None = None,
    ticker_aliases: list[str] | None = None,
    overwrite: bool = False,
    cancellation_checker: UploadCancellationChecker | None = None,
) -> AsyncIterator[UploadFilingEvent]:
    """执行流式财报上传。

    Args:
        host: SEC pipeline facade 暴露出的最小宿主边界。
        ticker: 股票代码。
        action: 可选动作类型；为空时自动判定。
        files: 上传文件列表。
        fiscal_year: 财年。
        fiscal_period: 财期。
        amended: 是否修订版。
        filing_date: 可选 filing 日期。
        report_date: 可选 report 日期。
        company_id: 可选兼容字段；上传链路不会把它作为身份真源。
        company_name: 公司名称。
        ticker_aliases: ticker alias 列表。
        overwrite: 是否覆盖。
        cancellation_checker: 可选协作式取消检查器。

    Yields:
        上传流程事件。

    Raises:
        RuntimeError: 上传执行失败时抛出。
    """

    requested_action = str(action or "").strip().lower() or None
    normalized_ticker = host._downloader.normalize_ticker(ticker)
    normalized_company_id = build_upload_company_id(normalized_ticker)
    normalized_period = str(fiscal_period).strip().upper()
    filing_form_type = normalized_period
    document_id, internal_document_id = build_sec_filing_ids(
        ticker=normalized_ticker,
        fiscal_year=fiscal_year,
        fiscal_period=normalized_period,
        amended=amended,
    )
    previous_meta = host._safe_get_document_meta(
        normalized_ticker,
        document_id,
        SourceKind.FILING,
    )
    normalized_action = resolve_upload_action(action, previous_meta)
    yield UploadFilingEvent(
        event_type=UploadFilingEventType.UPLOAD_STARTED,
        ticker=normalized_ticker,
        document_id=document_id,
        payload={
            "action": normalized_action,
            "requested_action": requested_action,
            "resolved_action": normalized_action,
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
            repository=host._company_repository,
            ticker=normalized_ticker,
            action=normalized_action,
            company_id=company_id,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
        )
        upload_result = host._upload_service.execute_upload(
            ticker=normalized_ticker,
            source_kind=SourceKind.FILING,
            action=normalized_action,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=filing_form_type,
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
        result = host._build_result(
            action="upload_filing",
            ticker=normalized_ticker,
            filing_action=normalized_action,
            requested_action=requested_action,
            resolved_action=normalized_action,
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
            payload={"result": result},
        )
    except Exception as exc:
        failed_result = host._build_result(
            action="upload_filing",
            ticker=normalized_ticker,
            filing_action=normalized_action,
            requested_action=requested_action,
            resolved_action=normalized_action,
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
            status="failed",
            message=str(exc),
        )
        yield UploadFilingEvent(
            event_type=UploadFilingEventType.UPLOAD_FAILED,
            ticker=normalized_ticker,
            document_id=document_id,
            payload={"error": str(exc), "result": failed_result},
        )


async def run_upload_material_stream(
    host: SecUploadWorkflowHost,
    *,
    ticker: str,
    action: str | None,
    form_type: str,
    material_name: str,
    files: list[Path] | None = None,
    document_id: str | None = None,
    internal_document_id: str | None = None,
    fiscal_year: int | None = None,
    fiscal_period: str | None = None,
    filing_date: str | None = None,
    report_date: str | None = None,
    company_id: str | None = None,
    company_name: str | None = None,
    ticker_aliases: list[str] | None = None,
    overwrite: bool = False,
    cancellation_checker: UploadCancellationChecker | None = None,
) -> AsyncIterator[UploadMaterialEvent]:
    """执行流式材料上传。

    Args:
        host: SEC pipeline facade 暴露出的最小宿主边界。
        ticker: 股票代码。
        action: 可选动作类型；为空时自动判定。
        form_type: 材料类型。
        material_name: 材料名称。
        files: 文件列表。
        document_id: 可选文档 ID。
        internal_document_id: 可选内部文档 ID。
        fiscal_year: 可选财年。
        fiscal_period: 可选财期。
        filing_date: 可选 filing 日期。
        report_date: 可选 report 日期。
        company_id: 可选兼容字段；上传链路不会把它作为身份真源。
        company_name: 公司名称。
        ticker_aliases: ticker alias 列表。
        overwrite: 是否覆盖。
        cancellation_checker: 可选协作式取消检查器。

    Yields:
        上传流程事件。

    Raises:
        ValueError: 市场类型非法时抛出。
        RuntimeError: 上传执行失败时抛出。
    """

    normalized = normalize_ticker(ticker)
    if normalized.market != "US":
        raise ValueError(f"SecPipeline 仅支持 US，当前 market={normalized.market}")
    normalized_ticker = host._downloader.normalize_ticker(ticker)
    normalized_company_id = build_upload_company_id(normalized_ticker)
    file_list = files or []
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
    previous_meta = host._safe_get_document_meta(
        normalized_ticker,
        resolved_document_id,
        SourceKind.MATERIAL,
    )
    requested_action = str(action or "").strip().lower() or None
    normalized_action = resolve_upload_action(action, previous_meta)
    yield UploadMaterialEvent(
        event_type=UploadMaterialEventType.UPLOAD_STARTED,
        ticker=normalized_ticker,
        document_id=resolved_document_id,
        payload={
            "action": normalized_action,
            "requested_action": requested_action,
            "resolved_action": normalized_action,
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
            repository=host._company_repository,
            ticker=normalized_ticker,
            action=normalized_action,
            company_id=company_id,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
        )
        upload_result = host._upload_service.execute_upload(
            ticker=normalized_ticker,
            source_kind=SourceKind.MATERIAL,
            action=normalized_action,
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
        final_result = host._build_result(
            action="upload_material",
            ticker=normalized_ticker,
            material_action=normalized_action,
            requested_action=requested_action,
            resolved_action=normalized_action,
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
        failed_result = host._build_result(
            action="upload_material",
            ticker=normalized_ticker,
            material_action=normalized_action,
            requested_action=requested_action,
            resolved_action=normalized_action,
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


def require_upload_result_mapping(result: JsonValue) -> JsonObject:
    """把上传完成事件的 result payload 收窄为字典。

    Args:
        result: 原始 JSON payload。

    Returns:
        result 字典。

    Raises:
        RuntimeError: result 不是字典时抛出。
    """

    if isinstance(result, Mapping):
        return dict(result)
    raise RuntimeError("上传事件 result payload 不是字典")


__all__ = [
    "SecUploadWorkflowHost",
    "collect_upload_result_from_events",
    "require_upload_result_mapping",
    "run_upload_filing_stream",
    "run_upload_material_stream",
]
