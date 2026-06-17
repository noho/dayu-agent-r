"""SecPipeline 下载持久化真源模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import partial
from typing import BinaryIO, Final, Optional, Protocol, TypeVar

from dayu.fins.domain.document_models import (
    FileObjectMeta,
    RejectedFilingArtifactUpsertRequest,
    SourceFileEntry,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.downloaders.sec_downloader import DownloaderEvent, RemoteFileDescriptor
from dayu.fins.pipelines.sec_download_event_mapping import DownloadFileResult
from dayu.fins.storage import (
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
)

from .sec_6k_rules import _remote_files_have_xbrl_instance
from .sec_fiscal_fields import _infer_download_fiscal_fields


class RejectedArtifactFilingRecord(Protocol):
    """rejected artifact 落盘所需的 filing 最小字段边界。"""

    @property
    def accession_number(self) -> str:
        """返回 accession number。"""

        ...

    @property
    def form_type(self) -> str:
        """返回 form type。"""

        ...

    @property
    def filing_date(self) -> str:
        """返回 filing date。"""

        ...

    @property
    def report_date(self) -> Optional[str]:
        """返回 report date。"""

        ...

    @property
    def primary_document(self) -> str:
        """返回 primary document。"""

        ...


_AwaitableResult = TypeVar("_AwaitableResult")
_DOWNLOADER_EVENT_FILE_DOWNLOAD_STARTED: Final[str] = "file_download_started"


async def _maybe_await(value: Awaitable[_AwaitableResult] | _AwaitableResult) -> _AwaitableResult:
    """按需等待可等待对象。

    Args:
        value: 可能为 awaitable 的值。

    Returns:
        最终结果值。

    Raises:
        无。
    """

    if inspect.isawaitable(value):
        return await value
    return value


def build_file_entries(
    file_results: list[DownloadFileResult],
    previous_files: dict[str, dict[str, JsonValue]],
) -> list[dict[str, JsonValue]]:
    """构建 source meta.json 的 files 列表。

    Args:
        file_results: 下载结果列表。
        previous_files: 旧文件条目映射（按文件名）。

    Returns:
        文件条目列表。

    Raises:
        无。
    """

    entries: list[dict[str, JsonValue]] = []
    for item in file_results:
        status = item.get("status")
        name = str(item.get("name", "")).strip()
        if status == "downloaded":
            file_meta = item.get("file_meta")
            if not isinstance(file_meta, FileObjectMeta) or not name:
                continue
            entries.append(
                {
                    "name": name,
                    "uri": file_meta.uri,
                    "etag": file_meta.etag,
                    "last_modified": file_meta.last_modified,
                    "size": file_meta.size,
                    "content_type": file_meta.content_type,
                    "sha256": file_meta.sha256,
                    "source_url": _download_result_json_value(item, "source_url"),
                    "http_etag": _download_result_json_value(item, "http_etag"),
                    "http_last_modified": _download_result_json_value(item, "http_last_modified"),
                    "ingested_at": now_iso8601(),
                }
            )
            continue
        if status == "skipped" and name:
            previous = previous_files.get(name)
            if previous:
                entries.append(previous)
    return entries


def build_store_file(
    repository: DocumentBlobRepositoryProtocol,
    source_handle: SourceHandle,
) -> Callable[[str, BinaryIO], FileObjectMeta]:
    """构建 source 文件写入回调。

    Args:
        repository: 文档文件对象仓储。
        source_handle: 源文档句柄。

    Returns:
        store_file 回调。

    Raises:
        无。
    """

    return partial(_store_file_callback, repository, source_handle)


def build_rejected_store_file(
    repository: FilingMaintenanceRepositoryProtocol,
    *,
    ticker: str,
    document_id: str,
) -> Callable[[str, BinaryIO], FileObjectMeta]:
    """构建 rejected filing 文件写入回调。

    Args:
        repository: filing 维护治理仓储。
        ticker: 股票代码。
        document_id: rejected filing 文档 ID。

    Returns:
        写入 rejected artifact 文件的回调。

    Raises:
        无。
    """

    return partial(
        _store_rejected_filing_file_callback,
        repository,
        ticker,
        document_id,
    )


async def persist_rejected_filing_artifact(
    *,
    ticker: str,
    cik: str,
    filing: RejectedArtifactFilingRecord,
    remote_files: list[RemoteFileDescriptor],
    overwrite: bool,
    rejection_reason: str,
    rejection_category: str,
    selected_primary_document: str,
    source_fingerprint: str,
    classification_version: str,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    download_files_stream: Optional[Callable[..., AsyncIterator[DownloaderEvent]]],
    download_files: Callable[..., Awaitable[list[DownloadFileResult]] | list[DownloadFileResult]],
    build_file_result_from_downloader_event: Callable[[DownloaderEvent], DownloadFileResult],
    normalize_download_file_result: Callable[[DownloadFileResult], DownloadFileResult],
    summarize_failed_download_file_reasons: Callable[[list[DownloadFileResult]], str],
) -> tuple[bool, Optional[str]]:
    """下载并保存 rejected filing artifact。

    Args:
        ticker: 股票代码。
        cik: 公司 CIK。
        filing: filing 记录。
        remote_files: 远端文件列表。
        overwrite: 是否覆盖。
        rejection_reason: 拒绝原因。
        rejection_category: 拒绝分类。
        selected_primary_document: 当前规则选中的主文件。
        source_fingerprint: 远端文件指纹。
        classification_version: 当前下载链路版本号。
        filing_maintenance_repository: rejected artifact 仓储。
        download_files_stream: 流式下载函数；为空时回退到 legacy 下载函数。
        download_files: legacy 下载函数。
        build_file_result_from_downloader_event: 下载器事件转文件结果 helper。
        normalize_download_file_result: legacy 文件结果规范化 helper。
        summarize_failed_download_file_reasons: 文件失败原因汇总 helper。

    Returns:
        `(成功标记, 失败原因)`；成功时失败原因返回 `None`。

    Raises:
        无。内部错误会转换为失败原因返回。
    """

    document_id = f"fil_{filing.accession_number}"
    store_file = build_rejected_store_file(
        filing_maintenance_repository,
        ticker=ticker,
        document_id=document_id,
    )
    file_results: list[DownloadFileResult] = []
    if download_files_stream is not None:
        async for event in download_files_stream(
            remote_files=remote_files,
            overwrite=overwrite,
            store_file=store_file,
            existing_files={},
            primary_document=filing.primary_document,
        ):
            if event.event_type == _DOWNLOADER_EVENT_FILE_DOWNLOAD_STARTED:
                continue
            file_results.append(build_file_result_from_downloader_event(event))
    else:
        legacy_results = await _maybe_await(
            download_files(
                remote_files=remote_files,
                overwrite=overwrite,
                store_file=store_file,
                existing_files={},
                primary_document=filing.primary_document,
            )
        )
        for item in legacy_results:
            file_results.append(normalize_download_file_result(dict(item)))

    failed_files = [item for item in file_results if item.get("status") == "failed"]
    if failed_files:
        return False, summarize_failed_download_file_reasons(failed_files)

    file_entries = build_file_entries(file_results=file_results, previous_files={})
    fiscal_year, fiscal_period = _infer_download_fiscal_fields(
        filing.form_type,
        filing.report_date,
    )
    filing_maintenance_repository.upsert_rejected_filing_artifact(
        RejectedFilingArtifactUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=filing.accession_number,
            accession_number=filing.accession_number,
            company_id=cik,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            primary_document=filing.primary_document,
            selected_primary_document=selected_primary_document or filing.primary_document,
            rejection_reason=rejection_reason,
            rejection_category=rejection_category,
            classification_version=classification_version,
            source_fingerprint=source_fingerprint,
            files=_build_typed_source_file_entries(file_entries),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            amended=filing.form_type.endswith("/A"),
            has_xbrl=_remote_files_have_xbrl_instance(remote_files),
        )
    )
    return True, None


def mark_processed_reprocess_required(
    repository: ProcessedDocumentRepositoryProtocol,
    *,
    ticker: str,
    document_id: str,
) -> None:
    """标记 processed 产物需要重处理。

    Args:
        repository: processed 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。

    Returns:
        无。

    Raises:
        OSError: 写文件失败时抛出。
    """

    repository.mark_processed_reprocess_required(
        ticker=ticker,
        document_id=document_id,
        required=True,
    )


def _download_result_json_value(file_result: DownloadFileResult, key: str) -> JsonValue:
    """读取内部下载结果中的 JSON 字段。

    Args:
        file_result: 内部文件下载结果。
        key: 字段名。

    Returns:
        JSON 值；字段为 ``FileObjectMeta`` 或不存在时返回 ``None``。

    Raises:
        无。
    """

    value = file_result.get(key)
    if isinstance(value, FileObjectMeta):
        return None
    return value


def _build_typed_source_file_entries(file_entries: list[dict[str, JsonValue]]) -> list[SourceFileEntry]:
    """将 dict 文件条目转换为强类型 `SourceFileEntry` 列表。

    Args:
        file_entries: 字典形式的文件条目列表。

    Returns:
        强类型文件条目列表。

    Raises:
        ValueError: 文件条目缺少必要字段时抛出。
    """

    typed_entries: list[SourceFileEntry] = []
    for item in file_entries:
        name = str(item.get("name") or "").strip()
        uri = str(item.get("uri") or "").strip()
        if not name or not uri:
            raise ValueError("文件条目缺少 name/uri")
        typed_entries.append(
            SourceFileEntry(
                name=name,
                uri=uri,
                etag=_normalize_optional_string(item.get("etag")),
                last_modified=_normalize_optional_string(item.get("last_modified")),
                size=_coerce_optional_int(item.get("size")),
                content_type=_normalize_optional_string(item.get("content_type")),
                sha256=_normalize_optional_string(item.get("sha256")),
                source_url=_normalize_optional_string(item.get("source_url")),
                http_etag=_normalize_optional_string(item.get("http_etag")),
                http_last_modified=_normalize_optional_string(item.get("http_last_modified")),
                ingested_at=_normalize_optional_string(item.get("ingested_at")) or now_iso8601(),
            )
        )
    return typed_entries


def _coerce_optional_int(value: JsonValue) -> Optional[int]:
    """将输入值安全转换为可选整数。

    Args:
        value: 输入值。

    Returns:
        转换成功时返回整数，否则返回 `None`。

    Raises:
        无。
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if not text.lstrip("-").isdigit():
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _normalize_optional_string(value: JsonValue) -> Optional[str]:
    """标准化可选字符串。

    Args:
        value: 输入值。

    Returns:
        标准化后的字符串；空值返回 `None`。

    Raises:
        无。
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _store_file_callback(
    repository: DocumentBlobRepositoryProtocol,
    source_handle: SourceHandle,
    filename: str,
    stream: BinaryIO,
) -> FileObjectMeta:
    """通用文件落盘回调。

    Args:
        repository: 文档文件对象仓储。
        source_handle: 源文档句柄。
        filename: 文件名。
        stream: 文件二进制流。

    Returns:
        文件元数据。

    Raises:
        OSError: 写入失败时抛出。
    """

    return repository.store_file(source_handle, filename, stream)


def _store_rejected_filing_file_callback(
    repository: FilingMaintenanceRepositoryProtocol,
    ticker: str,
    document_id: str,
    filename: str,
    stream: BinaryIO,
) -> FileObjectMeta:
    """rejected filing 文件落盘回调。

    Args:
        repository: filing 维护治理仓储。
        ticker: 股票代码。
        document_id: rejected filing 文档 ID。
        filename: 文件名。
        stream: 文件二进制流。

    Returns:
        文件元数据。

    Raises:
        OSError: 写入失败时抛出。
    """

    return repository.store_rejected_filing_file(
        ticker=ticker,
        document_id=document_id,
        filename=filename,
        data=stream,
    )
