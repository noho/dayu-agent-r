"""CN 年度当前原件的唯一声明投影与 exact publication 读取 owner。"""

from collections.abc import Callable, Mapping
import hashlib

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import CnAnnualReportPdf, CnAnnualReportPublication
from dayu.fins.storage import SourceDocumentRepositoryProtocol
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol, SourceSnapshotFileDescriptor
from dayu.fins.storage.source_integrity import (
    SourceIntegrityStatus, SourceIntegrityPreflightError, SourceIntegrityPreflightReason,
    SourceIntegrityRevisionConflictError, SourceIntegrityRepairRequiredError,
)

_PDF_MEDIA = "application/pdf"
_RANGE_FIELDS = ("ingest_method", "is_deleted", "filing_date", "fiscal_year", "fiscal_period", "covered_fiscal_periods")


class CnAnnualReportSourceError(ValueError):
    """本地声明与实际原件关系不能被确认；不是完整性调度错误。"""

    def __init__(self) -> None:
        """构造有界安全原因。参数：无。返回：无。异常：无。"""
        super().__init__("本地年度报告缺少可信且唯一声明的 PDF 原件，无法确认原文")


def project_cn_annual_report_original(snapshot: SourceSnapshotProtocol) -> SourceSnapshotFileDescriptor:
    """纯投影唯一显式 original PDF。

    参数：snapshot 为同版仓储快照。返回：exact 原件 descriptor。
    异常：CnAnnualReportSourceError 表示角色、媒体类型或声明不一致。
    """
    files = snapshot.source_meta.get("files")
    if not isinstance(files, list):
        raise CnAnnualReportSourceError()
    originals = tuple(entry for entry in files if isinstance(entry, Mapping) and entry.get("source") == "original")
    if len(originals) != 1:
        raise CnAnnualReportSourceError()
    entry = originals[0]
    name = entry.get("name")
    if type(name) is not str or name == "" or entry.get("content_type") != _PDF_MEDIA:
        raise CnAnnualReportSourceError()
    matches = tuple(d for d in snapshot.files if d.name == name)
    if len(matches) != 1 or matches[0].content_type != _PDF_MEDIA:
        raise CnAnnualReportSourceError()
    descriptor = matches[0]
    for field, declared in (("size", descriptor.size), ("sha256", descriptor.sha256)):
        if entry.get(field) is not None and entry.get(field) != declared:
            raise CnAnnualReportSourceError()
    return descriptor


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    """调用上层取消检查。参数：checkpoint 为可选控制点。返回：无。异常：原异常透传。"""
    if checkpoint is not None:
        checkpoint()


def read_cn_annual_report_pdf(
    ticker: str,
    document_id: str,
    expected_publication: CnAnnualReportPublication,
    expected_meta: Mapping[str, JsonValue],
    source_repository: SourceDocumentRepositoryProtocol,
    cancellation_checkpoint: Callable[[], None] | None,
) -> CnAnnualReportPdf:
    """从 exact 当前 publication 读取声明原件，确保释放快照与 stream。

    参数：ticker/document_id 为 exact target；expected_publication/expected_meta 来自同窗 COMPLETE；
    source_repository 为仓储；cancellation_checkpoint 为可选取消检查。
    返回：同版原件 bytes、实际 locator 与见证。
    异常：完整性三类型、仓储故障及取消原样传播；声明/字节不一致为 SourceError。
    """
    _checkpoint(cancellation_checkpoint)
    try:
        snapshot = source_repository.read_source_snapshot(ticker, document_id, SourceKind.FILING, materialize_files=True)
    except FileNotFoundError as exc:
        raise SourceIntegrityRevisionConflictError() from exc
    except ValueError as exc:
        current = source_repository.classify_source_integrity(ticker, document_id, SourceKind.FILING)
        if current.status is SourceIntegrityStatus.UNSAFE:
            raise SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSAFE_PUBLICATION) from exc
        if current.revision != expected_publication.revision or current.status is SourceIntegrityStatus.MISSING:
            raise SourceIntegrityRevisionConflictError() from exc
        if current.status is SourceIntegrityStatus.REPAIR_REQUIRED:
            raise SourceIntegrityRepairRequiredError() from exc
        raise
    with snapshot:
        _checkpoint(cancellation_checkpoint)
        meta = snapshot.source_meta
        if (snapshot.ticker != ticker or snapshot.document_id != document_id
            or snapshot.source_kind is not SourceKind.FILING
            or expected_publication.document_id != document_id
            or snapshot.revision != expected_publication.revision
            or meta.get("source_provider") != expected_publication.provider
            or meta.get("source_id") != expected_publication.source_id
            or any(meta.get(field) != expected_meta.get(field) for field in _RANGE_FIELDS)
            or any(meta.get(field) != expected_meta.get(field) for field in ("source_provider", "source_id"))):
            raise SourceIntegrityRevisionConflictError()
        descriptor = project_cn_annual_report_original(snapshot)
        locator = meta.get("source_url")
        if type(locator) is not str or locator == "":
            raise CnAnnualReportSourceError()
        _checkpoint(cancellation_checkpoint)
        with snapshot.get_source(descriptor.name).open() as stream:
            payload = stream.read()
            _checkpoint(cancellation_checkpoint)
        if not payload or (descriptor.size is not None and descriptor.size != len(payload)) or (
            descriptor.sha256 is not None and descriptor.sha256 != hashlib.sha256(payload).hexdigest()
        ):
            raise CnAnnualReportSourceError()
        result = CnAnnualReportPdf(expected_publication, locator, payload)
    _checkpoint(cancellation_checkpoint)
    return result
