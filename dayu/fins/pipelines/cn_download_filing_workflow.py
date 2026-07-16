"""CN/HK 单份财报下载阶段机。

阶段机负责单个 :class:`CnReportCandidate` 的 skip、PDF 下载 / 复用、Docling
转换 / 复用以及 source commit。所有持久化动作都经 ``dayu.fins.storage`` 的
窄仓储协议完成；本模块不直接拼 workspace 路径。
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from io import BytesIO
from typing import cast

from dayu.fins.domain.document_models import BatchToken, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol
from dayu.fins.pipelines.cn_download_models import (
    CN_PIPELINE_DOWNLOAD_VERSION,
    CnDownloadCancelledError,
    CnCompanyProfile,
    CnReportCandidate,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_protocols import (
    CnReportDiscoveryClientProtocol,
)
from dayu.fins.pipelines.cn_download_source_upsert import (
    JsonObject,
    JsonValue,
    build_cn_file_entry,
    build_content_fingerprint,
    build_remote_fingerprint,
    commit_cn_filing_source_document,
)
from dayu.fins.pipelines.cn_download_staging import has_blob_file
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins._log import Log

_PDF_CONTENT_TYPE = "application/pdf"
_JSON_CONTENT_TYPE = "application/json"
_SOURCE_LABEL_ORIGINAL = "original"
_SOURCE_LABEL_DOCLING = "docling"


class CnDownloadFilingError(RuntimeError):
    """CN/HK 单 filing 下载失败。"""


def _download_report_pdf_with_gate(
    *,
    discovery_client: CnReportDiscoveryClientProtocol,
    pdf_download_gate: CnDownloadPdfGateProtocol,
    candidate: CnReportCandidate,
    cancel_checker: Callable[[], bool] | None,
) -> DownloadedReportAsset:
    """在 PDF 下载 gate 内访问远端 PDF。

    Args:
        discovery_client: 当前市场 downloader。
        pdf_download_gate: PDF 下载段 gate。
        candidate: 待下载候选。
        cancel_checker: 可选取消检查函数。

    Returns:
        已下载 PDF 资产。

    Raises:
        Exception: gate 获取、取消、主源下载或 PDF 校验失败时原样抛出。
    """

    with pdf_download_gate.lease_for_provider(candidate.provider, cancel_checker=cancel_checker):
        return discovery_client.download_report_pdf(candidate)


async def run_cn_download_single_filing_stream(
    *,
    batching_repository: BatchingRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    discovery_client: CnReportDiscoveryClientProtocol,
    pdf_download_gate: CnDownloadPdfGateProtocol,
    convert_pdf_to_docling_json: Callable[[bytes, str], bytes],
    ticker: str,
    profile: CnCompanyProfile,
    candidate: CnReportCandidate,
    overwrite: bool,
    cancel_checker: Callable[[], bool] | None,
    module: str,
) -> AsyncIterator[DownloadEvent]:
    """执行单个 CN/HK filing 下载阶段机。

    Args:
        batching_repository: batch lifecycle 唯一仓储。
        source_repository: source 文档仓储。
        blob_repository: 文件对象仓储。
        processed_repository: processed 文档仓储。
        discovery_client: 当前市场 downloader。
        pdf_download_gate: PDF 下载段 gate。
        convert_pdf_to_docling_json: PDF -> Docling JSON 转换函数。
        ticker: 已归一化 ticker。
        profile: 公司基础元数据。
        candidate: 远端候选报告。
        overwrite: 是否强制覆盖；为 ``True`` 时禁止复用和 skip。
        cancel_checker: 可选取消检查函数。
        module: 日志模块名。

    Yields:
        单 filing 的文件级与终态下载事件。``FILING_STARTED`` 由上层 workflow
        统一发出，本函数只发后续事件。

    Raises:
        CnDownloadFilingError: 仓储、下载或转换失败时抛出。
        CnDownloadCancelledError: 取消检查命中时抛出。
    """

    _raise_if_cancelled(module=module, ticker=ticker, document_id="", cancel_checker=cancel_checker)
    document_id, internal_document_id = build_cn_filing_ids(
        ticker=ticker,
        form_type=candidate.fiscal_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.fiscal_period,
        amended=candidate.amended,
    )
    pdf_filename = f"{document_id}.pdf"
    docling_filename = f"{document_id}_docling.json"
    previous_meta = _safe_get_source_meta(
        source_repository=source_repository,
        ticker=ticker,
        document_id=document_id,
    )
    previous_completed_meta = _resolve_previous_completed_meta(
        previous_meta=previous_meta,
        overwrite=overwrite,
    )
    remote_fingerprint = build_remote_fingerprint(candidate)
    skip_result = _resolve_fast_skip_result(
        previous_meta=previous_meta,
        remote_fingerprint=remote_fingerprint,
        overwrite=overwrite,
    )
    if skip_result is not None:
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload=_filing_event_payload(skip_result),
        )
        return

    existing_handle = (
        source_repository.get_source_handle(ticker, document_id, SourceKind.FILING)
        if previous_meta is not None
        else None
    )
    yield DownloadEvent(
        event_type=DownloadEventType.FILE_DOWNLOAD_STARTED,
        ticker=ticker,
        document_id=document_id,
        payload={
            "name": pdf_filename,
            "stage": "pdf_download_started",
        },
    )
    try:
        asset = await asyncio.to_thread(
            _download_report_pdf_with_gate,
            discovery_client=discovery_client,
            pdf_download_gate=pdf_download_gate,
            candidate=candidate,
            cancel_checker=cancel_checker,
        )
    except CnDownloadCancelledError:
        raise
    except Exception as exc:
        yield DownloadEvent(
            event_type=DownloadEventType.FILE_FAILED,
            ticker=ticker,
            document_id=document_id,
            payload={
                "name": pdf_filename,
                "stage": "pdf_download_failed",
                "status": "failed",
                "reason_code": "pdf_download_failed",
                "reason_message": str(exc),
            },
        )
        failed = _build_filing_result(
            document_id=document_id,
            status="failed",
            candidate=candidate,
            reason_code="pdf_download_failed",
            reason_message=str(exc),
            downloaded_files=0,
            skipped_files=0,
        )
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_FAILED,
            ticker=ticker,
            document_id=document_id,
            payload=_filing_event_payload(failed),
        )
        return
    _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
    pdf_bytes = asset.pdf_bytes
    pdf_sha256 = asset.sha256

    can_skip_by_pdf_sha = existing_handle is not None and _can_skip_by_pdf_sha(
        previous_meta=previous_meta,
        overwrite=overwrite,
        pdf_sha256=pdf_sha256,
        blob_repository=blob_repository,
        handle=existing_handle,
        docling_filename=docling_filename,
    )
    if can_skip_by_pdf_sha:
        _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
        primary_document = _read_required_text(previous_meta, "primary_document")
        file_entries = _read_file_entries(previous_meta)
        source_fingerprint = _read_required_text(previous_meta, "source_fingerprint")
        _commit_cn_filing_metadata_batch(
            batching_repository=batching_repository,
            source_repository=source_repository,
            processed_repository=processed_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=candidate.fiscal_period,
            primary_document=primary_document,
            file_entries=file_entries,
            candidate=candidate,
            profile=profile,
            pdf_sha256=pdf_sha256,
            remote_fingerprint=remote_fingerprint,
            source_fingerprint=source_fingerprint,
            previous_completed_meta=previous_completed_meta,
            cancel_checker=cancel_checker,
            module=module,
        )
        skipped = _build_filing_result(
            document_id=document_id,
            status="skipped",
            candidate=candidate,
            reason_code="pdf_sha256_matched",
            reason_message="PDF 内容与完成态一致且 Docling JSON 存在，跳过重新处理",
            downloaded_files=0,
            skipped_files=2,
        )
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload=_filing_event_payload(skipped),
        )
        return

    yield DownloadEvent(
        event_type=DownloadEventType.FILE_DOWNLOADED,
        ticker=ticker,
        document_id=document_id,
        payload={
            "name": pdf_filename,
            "stage": "pdf_downloaded",
            "status": "downloaded",
            "reused": False,
            "reason_code": None,
        },
    )

    _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
    reusable_docling = None
    if existing_handle is not None:
        reusable_docling = _resolve_reusable_docling(
            blob_repository=blob_repository,
            handle=existing_handle,
            docling_filename=docling_filename,
            previous_meta=previous_meta,
            pdf_sha256=pdf_sha256,
            overwrite=overwrite,
        )
    if reusable_docling is None:
        _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
        yield DownloadEvent(
            event_type=DownloadEventType.CONVERSION_STARTED,
            ticker=ticker,
            document_id=document_id,
            payload={
                "name": docling_filename,
                "source_name": pdf_filename,
                "stage": "docling_conversion_started",
            },
        )
        try:
            Log.info(
                f"开始 Docling 转换: ticker={ticker} document_id={document_id} "
                f"form={candidate.fiscal_period} filing_date={candidate.filing_date} "
                f"source_file={pdf_filename}",
                module=module,
            )
            docling_json_bytes = await asyncio.to_thread(
                convert_pdf_to_docling_json,
                pdf_bytes,
                pdf_filename,
            )
        except CnDownloadCancelledError:
            raise
        except Exception as exc:
            failed = _build_filing_result(
                document_id=document_id,
                status="failed",
                candidate=candidate,
                reason_code="docling_convert_failed",
                reason_message=str(exc),
                downloaded_files=1,
                skipped_files=0,
            )
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_FAILED,
                ticker=ticker,
                document_id=document_id,
                payload=_filing_event_payload(failed),
            )
            return
        _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
        reused_docling = False
        converted = True
    else:
        _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
        docling_json_bytes = reusable_docling
        reused_docling = True
        converted = False
    source_fingerprint = build_content_fingerprint(
        pdf_bytes=pdf_bytes,
        docling_json_bytes=docling_json_bytes,
    )
    _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
    _commit_cn_filing_assets_batch(
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
        processed_repository=processed_repository,
        ticker=ticker,
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type=candidate.fiscal_period,
        pdf_filename=pdf_filename,
        docling_filename=docling_filename,
        pdf_bytes=pdf_bytes,
        docling_json_bytes=docling_json_bytes,
        candidate=candidate,
        profile=profile,
        pdf_sha256=pdf_sha256,
        remote_fingerprint=remote_fingerprint,
        source_fingerprint=source_fingerprint,
        previous_completed_meta=previous_completed_meta,
        source_meta_exists=previous_meta is not None,
        cancel_checker=cancel_checker,
        module=module,
    )
    downloaded = _build_filing_result(
        document_id=document_id,
        status="downloaded",
        candidate=candidate,
        reason_code="download_committed",
        reason_message="PDF 与 Docling JSON 已完成落盘并提交 source meta",
        downloaded_files=1 + (0 if reused_docling else 1),
        skipped_files=1 if reused_docling else 0,
    )
    downloaded["reused_pdf"] = False
    downloaded["reused_docling"] = reused_docling
    downloaded["converted"] = converted
    yield DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker=ticker,
        document_id=document_id,
        payload=_filing_event_payload(downloaded),
    )


def _commit_cn_filing_assets_batch(
    *,
    batching_repository: BatchingRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    internal_document_id: str,
    form_type: str,
    pdf_filename: str,
    docling_filename: str,
    pdf_bytes: bytes,
    docling_json_bytes: bytes,
    candidate: CnReportCandidate,
    profile: CnCompanyProfile,
    pdf_sha256: str,
    remote_fingerprint: str,
    source_fingerprint: str,
    previous_completed_meta: JsonObject | None,
    source_meta_exists: bool,
    cancel_checker: Callable[[], bool] | None,
    module: str,
) -> None:
    """在一个 caller-owned batch 内提交 CN/HK filing 的全部持久态。

    Args:
        batching_repository: batch lifecycle 唯一仓储。
        source_repository: source 文档仓储及 batch owner 入口。
        blob_repository: PDF 与 Docling blob 仓储。
        processed_repository: processed marker 仓储。
        ticker: 已归一化 ticker。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        form_type: 财期 form type。
        pdf_filename: PDF 对象名。
        docling_filename: Docling JSON 对象名。
        pdf_bytes: 已在 batch 外完成下载或复用读取的 PDF 字节。
        docling_json_bytes: 已在 batch 外完成转换或复用读取的 JSON 字节。
        candidate: 远端候选报告。
        profile: 公司基础元数据。
        pdf_sha256: PDF SHA-256。
        remote_fingerprint: 远端 fingerprint。
        source_fingerprint: PDF 与 Docling 内容 fingerprint。
        previous_completed_meta: batch 前的上一版完成态 meta。
        source_meta_exists: batch 前是否存在待替换 source document。
        cancel_checker: 可选同步取消检查器。
        module: 日志模块名。

    Returns:
        无；返回时 storage ``COMMITTED`` 已成立。

    Raises:
        CnDownloadCancelledError: batch 内阶段边界命中取消时抛出并回滚。
        OSError: 任一仓储写入、commit 或 rollback 失败时抛出。
        RuntimeError: batch/token owner 契约不成立时抛出。
    """

    token = batching_repository.begin_batch(ticker)
    commit_started = False
    try:
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        if source_meta_exists:
            source_repository.reset_source_document(
                ticker,
                document_id,
                SourceKind.FILING,
                batch=token,
            )
            _raise_if_cancelled(
                module=module,
                ticker=ticker,
                document_id=document_id,
                cancel_checker=cancel_checker,
            )
        handle = SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=SourceKind.FILING.value,
        )
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        pdf_meta = blob_repository.store_file(
            handle,
            pdf_filename,
            BytesIO(pdf_bytes),
            batch=token,
            content_type=_PDF_CONTENT_TYPE,
            metadata={"source": _SOURCE_LABEL_ORIGINAL},
        )
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        docling_meta = blob_repository.store_file(
            handle,
            docling_filename,
            BytesIO(docling_json_bytes),
            batch=token,
            content_type=_JSON_CONTENT_TYPE,
            metadata={"source": _SOURCE_LABEL_DOCLING, "pdf_sha256": pdf_sha256},
        )
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        file_entries = [
            build_cn_file_entry(
                filename=pdf_filename,
                file_meta=pdf_meta,
                source_label=_SOURCE_LABEL_ORIGINAL,
            ),
            build_cn_file_entry(
                filename=docling_filename,
                file_meta=docling_meta,
                source_label=_SOURCE_LABEL_DOCLING,
            ),
        ]
        commit_cn_filing_source_document(
            source_repository=source_repository,
            processed_repository=processed_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            primary_document=docling_filename,
            file_entries=file_entries,
            candidate=candidate,
            profile=profile,
            pdf_sha256=pdf_sha256,
            remote_fingerprint=remote_fingerprint,
            source_fingerprint=source_fingerprint,
            previous_completed_meta=previous_completed_meta,
            source_meta_exists=False,
            batch=token,
        )
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        # commit_batch 开始后 token 由 storage owner 消费，caller 不再回滚。
        commit_started = True
        batching_repository.commit_batch(token)
    finally:
        if not commit_started:
            _rollback_cn_batch_preserving_primary(
                batching_repository=batching_repository,
                token=token,
                operation_error=sys.exception(),
            )


def _commit_cn_filing_metadata_batch(
    *,
    batching_repository: BatchingRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    internal_document_id: str,
    form_type: str,
    primary_document: str,
    file_entries: list[JsonObject],
    candidate: CnReportCandidate,
    profile: CnCompanyProfile,
    pdf_sha256: str,
    remote_fingerprint: str,
    source_fingerprint: str,
    previous_completed_meta: JsonObject | None,
    cancel_checker: Callable[[], bool] | None,
    module: str,
) -> None:
    """在 caller-owned batch 内提交 PDF-SHA skip 的最终 meta 与 marker。

    Args:
        batching_repository: batch lifecycle 唯一仓储。
        source_repository: source 文档仓储及 batch owner 入口。
        processed_repository: processed marker 仓储。
        ticker: 已归一化 ticker。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        form_type: 财期 form type。
        primary_document: 既有 Docling JSON 主文件名。
        file_entries: 既有完成态文件条目。
        candidate: 远端候选报告。
        profile: 公司基础元数据。
        pdf_sha256: PDF SHA-256。
        remote_fingerprint: 当前远端 fingerprint。
        source_fingerprint: 既有内容 fingerprint。
        previous_completed_meta: batch 前的完成态 meta。
        cancel_checker: 可选同步取消检查器。
        module: 日志模块名。

    Returns:
        无；返回时 storage ``COMMITTED`` 已成立。

    Raises:
        CnDownloadCancelledError: batch 内命中取消时抛出并回滚。
        OSError: meta、processed、commit 或 rollback 失败时抛出。
        RuntimeError: batch/token owner 契约不成立时抛出。
    """

    token = batching_repository.begin_batch(ticker)
    commit_started = False
    try:
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        commit_cn_filing_source_document(
            source_repository=source_repository,
            processed_repository=processed_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            primary_document=primary_document,
            file_entries=file_entries,
            candidate=candidate,
            profile=profile,
            pdf_sha256=pdf_sha256,
            remote_fingerprint=remote_fingerprint,
            source_fingerprint=source_fingerprint,
            previous_completed_meta=previous_completed_meta,
            source_meta_exists=True,
            batch=token,
        )
        _raise_if_cancelled(
            module=module,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        commit_started = True
        batching_repository.commit_batch(token)
    finally:
        if not commit_started:
            _rollback_cn_batch_preserving_primary(
                batching_repository=batching_repository,
                token=token,
                operation_error=sys.exception(),
            )


def _rollback_cn_batch_preserving_primary(
    *,
    batching_repository: BatchingRepositoryProtocol,
    token: BatchToken,
    operation_error: BaseException | None,
) -> None:
    """回滚未进入 commit 的 batch，并保留 operation/rollback 双错误。

    Args:
        batching_repository: 持有 token 的 batching 仓储。
        token: 尚未交给 ``commit_batch`` 的 caller-owned token。
        operation_error: 当前正在传播的业务异常或取消异常；正常 return 时为
            ``None``。

    Returns:
        无。

    Raises:
        BaseException: operation 与 rollback 都失败时重新抛出 operation，并以
            rollback 为 cause；仅 rollback 失败时原样抛出 rollback 异常。
    """

    try:
        batching_repository.rollback_batch(token)
    except Exception as rollback_error:
        if operation_error is not None:
            operation_error.add_note(
                "rollback_batch failed; recovery evidence retained: "
                f"{rollback_error}"
            )
            raise operation_error from rollback_error
        raise


def _safe_get_source_meta(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
) -> JsonObject | None:
    """安全读取 source meta。"""

    try:
        meta = source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)
    except FileNotFoundError:
        return None
    return {str(key): _coerce_json_value(value) for key, value in meta.items()}


def _resolve_fast_skip_result(
    *,
    previous_meta: JsonObject | None,
    remote_fingerprint: str,
    overwrite: bool,
) -> JsonObject | None:
    """判断是否可在下载 PDF 前 fast skip。"""

    if overwrite or previous_meta is None:
        return None
    if previous_meta.get("ingest_complete") is not True:
        return None
    if previous_meta.get("download_version") != CN_PIPELINE_DOWNLOAD_VERSION:
        return None
    if previous_meta.get("remote_fingerprint") != remote_fingerprint:
        return None
    return {
        "document_id": str(previous_meta.get("document_id") or ""),
        "status": "skipped",
        "form_type": str(previous_meta.get("form_type") or ""),
        "filing_date": str(previous_meta.get("filing_date") or ""),
        "report_date": None,
        "downloaded_files": 0,
        "skipped_files": 2,
        "reason_code": "remote_fingerprint_matched",
        "reason_message": "远端 fingerprint 与本地完成态一致，跳过下载",
        "skip_reason": "remote_fingerprint_matched",
    }


def _resolve_previous_completed_meta(
    *,
    previous_meta: JsonObject | None,
    overwrite: bool,
) -> JsonObject | None:
    """解析可用于版本计算的上一版完成态 meta。

    Args:
        previous_meta: 当前 source meta。
        overwrite: 是否强制覆盖。

    Returns:
        可用于版本计算和审计字段保留的完成态 meta；不存在时返回 ``None``。

    Raises:
        无。
    """

    if overwrite or previous_meta is None:
        return None
    return previous_meta


def _resolve_reusable_docling(
    *,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    docling_filename: str,
    previous_meta: JsonObject | None,
    pdf_sha256: str,
    overwrite: bool,
) -> bytes | None:
    """判断中间态 Docling JSON 是否可复用。

    Args:
        blob_repository: blob 仓储。
        handle: source document 句柄。
        docling_filename: Docling JSON 文件名。
        previous_meta: 当前 source meta。
        pdf_sha256: 当前 PDF 字节 SHA-256。
        overwrite: 是否强制覆盖。

    Returns:
        可复用 Docling JSON 字节；不可复用时返回 ``None``。

    Raises:
        OSError: 底层 blob 读取失败时抛出。
    """

    if overwrite or previous_meta is None:
        return None
    if previous_meta.get("pdf_sha256") != pdf_sha256:
        return None
    try:
        return blob_repository.read_file_bytes(handle, docling_filename)
    except FileNotFoundError:
        return None


def _can_skip_by_pdf_sha(
    *,
    previous_meta: JsonObject | None,
    overwrite: bool,
    pdf_sha256: str,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    docling_filename: str,
) -> bool:
    """判断完成态 PDF 内容未变时是否可跳过。"""

    if overwrite or previous_meta is None:
        return False
    if previous_meta.get("ingest_complete") is not True:
        return False
    if previous_meta.get("download_version") != CN_PIPELINE_DOWNLOAD_VERSION:
        return False
    if previous_meta.get("pdf_sha256") != pdf_sha256:
        return False
    return has_blob_file(blob_repository=blob_repository, handle=handle, filename=docling_filename)


def _read_file_entries(meta: JsonObject | None) -> list[JsonObject]:
    """读取完成态 meta 中的文件条目。

    Args:
        meta: source meta。

    Returns:
        可传给 source upsert 的文件条目列表。

    Raises:
        CnDownloadFilingError: meta 缺失或 ``files`` 字段不是对象列表时抛出。
    """

    if meta is None:
        raise CnDownloadFilingError("缺少 source meta，无法读取 files")
    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        raise CnDownloadFilingError("source meta.files 必须为 list")
    entries: list[JsonObject] = []
    for raw_item in raw_files:
        if not isinstance(raw_item, dict):
            raise CnDownloadFilingError("source meta.files 条目必须为 JSON 对象")
        entries.append({str(key): _coerce_json_value(value) for key, value in raw_item.items()})
    return entries


def _build_filing_result(
    *,
    document_id: str,
    status: str,
    candidate: CnReportCandidate,
    reason_code: str,
    reason_message: str,
    downloaded_files: int,
    skipped_files: int,
) -> JsonObject:
    """构建单 filing 结果 payload。"""

    payload: JsonObject = {
        "document_id": document_id,
        "status": status,
        "form_type": candidate.fiscal_period,
        "filing_date": candidate.filing_date,
        "report_date": None,
        "fiscal_year": candidate.fiscal_year,
        "fiscal_period": candidate.fiscal_period,
        "downloaded_files": downloaded_files,
        "skipped_files": skipped_files,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": reason_code,
        "reason_message": reason_message,
    }
    if status == "skipped":
        payload["skip_reason"] = reason_code
    return payload


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


def _read_required_text(meta: JsonObject | None, key: str) -> str:
    """读取必填文本 meta 字段。"""

    if meta is None:
        raise CnDownloadFilingError(f"缺少 source meta，无法读取 {key}")
    value = _optional_text(meta.get(key))
    if value is None:
        raise CnDownloadFilingError(f"source meta 缺少 {key}")
    return value


def _optional_text(value: JsonValue) -> str | None:
    """把值收窄为非空字符串。"""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_json_value(value: JsonValue) -> JsonValue:
    """把仓储 meta 值收窄到 JSON 值。

    Args:
        value: 仓储 meta 中的单个值。

    Returns:
        JSON 值；非 JSON 类型按字符串保存。

    Raises:
        无。
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    return str(value)


def _raise_if_cancelled(
    *,
    module: str,
    ticker: str,
    document_id: str,
    cancel_checker: Callable[[], bool] | None,
) -> None:
    """在阶段边界检查取消请求。"""

    if cancel_checker is None or not cancel_checker():
        return
    Log.info(
        f"CN/HK 下载收到取消请求: ticker={ticker} document_id={document_id}",
        module=module,
    )
    raise CnDownloadCancelledError("操作已被取消")


__all__ = [
    "CnDownloadFilingError",
    "run_cn_download_single_filing_stream",
]
