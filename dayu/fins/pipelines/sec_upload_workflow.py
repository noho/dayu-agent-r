"""SEC 上传工作流模块。

本模块承载 OLD SEC filing/material upload stream 业务规则，pipeline facade
只提供 downloader、仓储和上传服务等最小宿主边界。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Final, Protocol, TypeAlias

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FinsIngestMethod
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.sec_downloader import SecDownloader
from dayu.fins.ingestion_runtime import (
    ValidatedFinsUploadFilingRequest,
    validate_fins_upload_filing_request,
)
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionError,
)
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    UploadOperationResult,
    build_material_ids,
    commit_prepared_upload_batch,
    derive_report_kind,
    resolve_upload_action,
    rollback_prepared_upload_batch,
    validate_material_upload_ids,
)
from dayu.fins.pipelines.upload_company_meta import (
    build_upload_company_id,
    stage_upload_company_meta_decision,
    upsert_company_meta_for_upload,
)
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent, UploadFilingEventType
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent, UploadMaterialEventType
from dayu.fins.pipelines.upload_progress_helpers import (
    map_upload_file_event_to_filing_event_type as _map_upload_file_event_to_filing_event_type,
    map_upload_file_event_to_material_event_type as _map_upload_file_event_to_material_event_type,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    FilingUploadStateRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.upload_failure import (
    FinsUploadFailureError,
    FinsUploadFailureReason,
    fins_upload_failure_from_exception,
)

JsonObject: TypeAlias = dict[str, JsonValue]
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class SecUploadWorkflowHost(Protocol):
    """SEC upload 工作流所需的最小宿主边界。"""

    @property
    def _batching_repository(self) -> BatchingRepositoryProtocol:
        """返回 batch lifecycle 唯一仓储。"""

        ...

    @property
    def _downloader(self) -> SecDownloader:
        """返回 SEC 下载器实例。"""

        ...

    @property
    def _company_repository(self) -> CompanyMetaRepositoryProtocol:
        """返回公司元数据仓储。"""

        ...

    @property
    def _filing_upload_state_repository(self) -> FilingUploadStateRepositoryProtocol:
        """返回 filing authoritative snapshot 唯一仓储。"""

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
    request: ValidatedFinsUploadFilingRequest,
    cancellation_checker: CancellationToken | None = None,
) -> AsyncIterator[UploadFilingEvent]:
    """执行流式财报上传。

    Args:
        host: SEC pipeline facade 暴露出的最小宿主边界。
        request: 已完成 preflight 的 typed filing 请求。
        cancellation_checker: 可选协作式取消检查器。

    Yields:
        上传流程事件。

    Raises:
        RuntimeError: 上传执行失败时抛出。
    """

    raw_request = request.request
    fresh_state = host._filing_upload_state_repository.read_filing_upload_state(
        request.normalized_ticker.canonical,
        request.document_id,
    )
    authoritative_request = validate_fins_upload_filing_request(
        raw_request,
        published_state=fresh_state,
    )
    _assert_authoritative_filing_identity(request, authoritative_request)
    if raw_request.fiscal_year is None:
        raise AssertionError("validated filing request 缺少 fiscal_year")
    requested_action = raw_request.action.strip().lower()
    normalized_ticker = authoritative_request.normalized_ticker.canonical
    normalized_company_id = build_upload_company_id(normalized_ticker)
    normalized_period = authoritative_request.normalized_fiscal_period
    filing_form_type = normalized_period
    document_id = authoritative_request.document_id
    internal_document_id = authoritative_request.internal_document_id
    previous_meta = authoritative_request.published_state.source_meta
    normalized_action = authoritative_request.resolved_action
    yield UploadFilingEvent(
        event_type=UploadFilingEventType.UPLOAD_STARTED,
        ticker=normalized_ticker,
        document_id=document_id,
        payload={
            "action": normalized_action,
            "requested_action": requested_action,
            "resolved_action": normalized_action,
            "fiscal_year": raw_request.fiscal_year,
            "fiscal_period": normalized_period,
            "amended": raw_request.amended,
            "filing_date": raw_request.filing_date,
            "report_date": raw_request.report_date,
            "company_id": normalized_company_id,
            "company_name": raw_request.company_name,
            "ticker_aliases": _json_text_list(list(raw_request.ticker_aliases)),
            "overwrite": raw_request.overwrite,
            "file_count": len(raw_request.files),
        },
    )
    try:
        prepared_upload = await host._upload_service.prepare_upload(
            ticker=normalized_ticker,
            source_kind=SourceKind.FILING,
            action=normalized_action,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=filing_form_type,
            files=list(raw_request.files),
            overwrite=raw_request.overwrite,
            previous_meta=previous_meta,
            cancellation=cancellation_checker,
            meta={
                "company_id": normalized_company_id,
                "ingest_method": FinsIngestMethod.UPLOAD.to_storage_value(),
                "fiscal_year": raw_request.fiscal_year,
                "fiscal_period": normalized_period,
                "report_kind": derive_report_kind(normalized_period),
                "filing_date": raw_request.filing_date,
                "report_date": raw_request.report_date,
                "amended": raw_request.amended,
            },
        )
        if isinstance(prepared_upload, UploadOperationResult):
            upload_result = prepared_upload
        else:
            publication_batch = host._batching_repository.begin_batch(normalized_ticker)
            try:
                stage_upload_company_meta_decision(
                    repository=host._company_repository,
                    decision=authoritative_request.company_meta_decision,
                    batch=publication_batch,
                )
            except BaseException as operation_error:
                rollback_prepared_upload_batch(
                    batching_repository=host._batching_repository,
                    batch=publication_batch,
                    operation_error=operation_error,
                )
                raise
            upload_result = commit_prepared_upload_batch(
                service=host._upload_service,
                batching_repository=host._batching_repository,
                batch=publication_batch,
                prepared=prepared_upload,
                cancellation=cancellation_checker,
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
            files=_json_text_list([str(path) for path in raw_request.files]),
            fiscal_year=raw_request.fiscal_year,
            fiscal_period=normalized_period,
            amended=raw_request.amended,
            filing_date=raw_request.filing_date,
            report_date=raw_request.report_date,
            company_id=normalized_company_id,
            company_name=raw_request.company_name,
            ticker_aliases=_json_text_list(list(raw_request.ticker_aliases)),
            overwrite=raw_request.overwrite,
            **upload_result.payload,
            stored_file_count=upload_result.stored_file_count,
            status=_resolve_upload_status(upload_result.status),
        )
        yield UploadFilingEvent(
            event_type=UploadFilingEventType.UPLOAD_COMPLETED,
            ticker=normalized_ticker,
            document_id=document_id,
            payload={"result": result},
        )
    except FinsUploadFailureError as exc:
        _LOGGER.exception("SEC filing upload typed content admission failed")
        yield _build_sec_filing_failure_event(
            host=host,
            request=authoritative_request,
            requested_action=requested_action,
            failure_reason=exc.failure,
        )
    except DoclingConversionError as exc:
        _LOGGER.exception("SEC filing upload Docling conversion failed")
        failure_reason = fins_upload_failure_from_exception(exc, file_label=None)
        yield _build_sec_filing_failure_event(
            host=host,
            request=authoritative_request,
            requested_action=requested_action,
            failure_reason=failure_reason,
        )
    except OSError as exc:
        _LOGGER.exception("SEC filing upload storage operation failed")
        failure_reason = fins_upload_failure_from_exception(exc, file_label=None)
        yield _build_sec_filing_failure_event(
            host=host,
            request=authoritative_request,
            requested_action=requested_action,
            failure_reason=failure_reason,
        )
    except Exception as exc:
        _LOGGER.exception("SEC filing upload runtime operation failed")
        failure_reason = fins_upload_failure_from_exception(exc, file_label=None)
        yield _build_sec_filing_failure_event(
            host=host,
            request=authoritative_request,
            requested_action=requested_action,
            failure_reason=failure_reason,
        )


def _assert_authoritative_filing_identity(
    preflight: ValidatedFinsUploadFilingRequest,
    authoritative: ValidatedFinsUploadFilingRequest,
) -> None:
    """断言 fresh validator 未改变 filing deterministic identity。

    Args:
        preflight: 入口 preflight validated request。
        authoritative: workflow fresh snapshot 产生的 validated request。

    Returns:
        无。

    Raises:
        RuntimeError: canonical ticker 或 filing identity 不一致时抛出。
    """

    if (
        authoritative.normalized_ticker.canonical != preflight.normalized_ticker.canonical
        or authoritative.document_id != preflight.document_id
        or authoritative.internal_document_id != preflight.internal_document_id
    ):
        raise RuntimeError("filing authoritative identity mismatch")


def _build_sec_filing_failure_event(
    *,
    host: SecUploadWorkflowHost,
    request: ValidatedFinsUploadFilingRequest,
    requested_action: str,
    failure_reason: FinsUploadFailureReason,
) -> UploadFilingEvent:
    """从 authoritative request 与 typed reason 构造 SEC filing 失败事件。

    Args:
        host: SEC workflow 宿主。
        request: authoritative validated request。
        requested_action: 用户请求动作。
        failure_reason: closed public failure reason。

    Returns:
        单个 typed upload failed 事件。

    Raises:
        无。
    """

    raw_request = request.request
    normalized_ticker = request.normalized_ticker.canonical
    normalized_company_id = build_upload_company_id(normalized_ticker)
    failed_result = host._build_result(
        action="upload_filing",
        ticker=normalized_ticker,
        filing_action=request.resolved_action,
        requested_action=requested_action,
        resolved_action=request.resolved_action,
        files=_json_text_list([str(path) for path in raw_request.files]),
        fiscal_year=raw_request.fiscal_year,
        fiscal_period=request.normalized_fiscal_period,
        amended=raw_request.amended,
        filing_date=raw_request.filing_date,
        report_date=raw_request.report_date,
        company_id=normalized_company_id,
        company_name=raw_request.company_name,
        ticker_aliases=_json_text_list(list(raw_request.ticker_aliases)),
        overwrite=raw_request.overwrite,
        stored_file_count=0,
        status="failed",
        message=failure_reason.message,
        failure=failure_reason.to_json(),
    )
    return UploadFilingEvent(
        event_type=UploadFilingEventType.UPLOAD_FAILED,
        ticker=normalized_ticker,
        document_id=request.document_id,
        payload={"error": failure_reason.message, "result": failed_result},
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
    cancellation_checker: CancellationToken | None = None,
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
        company_batch = host._batching_repository.begin_batch(normalized_ticker)
        try:
            upsert_company_meta_for_upload(
                repository=host._company_repository,
                ticker=normalized_ticker,
                action=normalized_action,
                company_id=company_id,
                company_name=company_name,
                ticker_aliases=ticker_aliases,
                batch=company_batch,
            )
        except BaseException:
            host._batching_repository.rollback_batch(company_batch)
            raise
        host._batching_repository.commit_batch(company_batch)
        prepared_upload = await host._upload_service.prepare_upload(
            ticker=normalized_ticker,
            source_kind=SourceKind.MATERIAL,
            action=normalized_action,
            document_id=resolved_document_id,
            internal_document_id=resolved_internal_id,
            form_type=form_type,
            files=file_list,
            overwrite=overwrite,
            previous_meta=previous_meta,
            cancellation=cancellation_checker,
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
        if isinstance(prepared_upload, UploadOperationResult):
            upload_result = prepared_upload
        else:
            upload_result = commit_prepared_upload_batch(
                service=host._upload_service,
                batching_repository=host._batching_repository,
                batch=host._batching_repository.begin_batch(normalized_ticker),
                prepared=prepared_upload,
                cancellation=cancellation_checker,
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
            stored_file_count=upload_result.stored_file_count,
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
            stored_file_count=0,
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
