"""SecPipeline 单 filing 下载工作流模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Optional, Protocol, TypeVar

from dayu.fins.domain.document_models import BatchToken, DownloadRejectionRegistry, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import FinsDownloadProviderError
from dayu.fins.downloaders.sec_downloader import (
    DownloaderEvent,
    RemoteFileDescriptor,
    SecDownloadCancelledError,
    SecDownloader,
    StoreDownloadedFile,
    accession_to_no_dash,
    build_source_fingerprint,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_6k_primary_document_repair import (
    mark_processed_for_6k_reconcile,
    select_prepared_6k_primary_document,
)
from dayu.fins.pipelines.sec_download_event_mapping import DownloadFileResult, build_download_file_event_payload
from dayu.fins.pipelines.sec_download_source_upsert import (
    upsert_downloaded_filing_source_document,
)
from dayu.fins.pipelines.sec_download_state import has_current_download_version
from dayu.fins.pipelines.sec_filing_collection import FilingRecord
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins._log import Log


class SecDownloadFilingWorkflowHost(Protocol):
    """单 filing 下载工作流所需的最小宿主边界。"""

    @property
    def _batching_repository(self) -> BatchingRepositoryProtocol:
        """返回 batch lifecycle 唯一仓储。"""

        ...

    @property
    def MODULE(self) -> str:
        """返回日志模块名。"""

        ...

    @property
    def _downloader(self) -> SecDownloader:
        """返回下载器实例。"""

        ...

    @property
    def _source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回 source 仓储。"""

        ...

    @property
    def _processed_repository(self) -> ProcessedDocumentRepositoryProtocol:
        """返回 processed 仓储。"""

        ...

    def _safe_get_filing_source_meta(self, ticker: str, document_id: str) -> Optional[dict[str, JsonValue]]:
        """安全读取 filing source meta。"""

        ...

    def _safe_get_processed_meta(self, ticker: str, document_id: str) -> Optional[dict[str, JsonValue]]:
        """安全读取 processed meta。"""

        ...

    def _can_skip_fast(self, previous_meta: Optional[dict[str, JsonValue]], overwrite: bool) -> Optional[str]:
        """快速预检是否可跳过。"""

        ...

    def _can_skip(
        self,
        previous_meta: Optional[dict[str, JsonValue]],
        source_fingerprint: str,
        overwrite: bool,
        remote_files: Optional[list[RemoteFileDescriptor]] = None,
    ) -> Optional[str]:
        """判断是否可跳过下载。"""

        ...

    def _resolve_document_version(
        self,
        previous_meta: Optional[dict[str, JsonValue]],
        source_fingerprint: str,
    ) -> str:
        """计算文档版本号。"""

        ...

    def _precheck_6k_filter(
        self,
        remote_files: list[RemoteFileDescriptor],
        primary_document: str,
        ticker: str,
        document_id: str,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> Awaitable[tuple[bool, str, str]]:
        """执行 6-K 预筛选。"""

        ...

    def _persist_rejected_filing_artifact(
        self,
        *,
        ticker: str,
        cik: str,
        filing: FilingRecord,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        rejection_reason: str,
        rejection_category: str,
        selected_primary_document: str,
        source_fingerprint: str,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> Awaitable[tuple[bool, Optional[str]]]:
        """持久化 rejected filing artifact。"""

        ...

    def _build_store_file(
        self,
        source_handle: SourceHandle,
        *,
        payload_sink: dict[str, bytes] | None,
    ) -> StoreDownloadedFile:
        """构建显式接收 batch、可选记录单 filing payload 的回调。"""

        ...

    def _build_file_entries(
        self,
        file_results: list[DownloadFileResult],
        previous_files: dict[str, dict[str, JsonValue]],
    ) -> list[dict[str, JsonValue]]:
        """构建 meta.json 的 files 列表。"""

        ...


_AwaitableResult = TypeVar("_AwaitableResult")


async def _maybe_await(value: Awaitable[_AwaitableResult] | _AwaitableResult) -> _AwaitableResult:
    """按需等待可等待对象。"""

    if inspect.isawaitable(value):
        return await value
    return value


async def run_download_single_filing_stream(
    host: SecDownloadFilingWorkflowHost,
    *,
    ticker: str,
    cik: str,
    filing: FilingRecord,
    overwrite: bool,
    rejection_registry: Optional[DownloadRejectionRegistry],
    is_rejected: Callable[[DownloadRejectionRegistry, str, bool], bool],
    record_rejection: Callable[[DownloadRejectionRegistry, str, str, str, str, str], None],
    build_download_filing_event_payload: Callable[[dict[str, JsonValue]], dict[str, JsonValue]],
    build_file_result_from_downloader_event: Callable[[DownloaderEvent], DownloadFileResult],
    summarize_failed_download_file_reasons: Callable[[list[DownloadFileResult]], str],
    has_same_file_name_set: Callable[[list[RemoteFileDescriptor], dict[str, dict[str, JsonValue]]], bool],
    resolve_download_fiscal_fields: Callable[..., tuple[Optional[int], Optional[str]]],
    index_file_entries: Callable[[Optional[dict[str, JsonValue]]], dict[str, dict[str, JsonValue]]],
    download_version: str,
    cancel_checker: Callable[[], bool] | None = None,
) -> AsyncIterator[DownloadEvent]:
    """下载单个 filing 并流式产出事件。

    Args:
        host: `SecPipeline` facade 暴露出的最小宿主边界。
        ticker: 股票代码。
        cik: CIK（无前导零）。
        filing: filing 记录。
        overwrite: 是否覆盖。
        rejection_registry: 拒绝注册表。
        is_rejected: 拒绝注册表命中判断 helper。
        record_rejection: 写入拒绝注册表 helper。
        build_download_filing_event_payload: filing 级事件 payload helper。
        build_file_result_from_downloader_event: 下载器事件转文件结果 helper。
        summarize_failed_download_file_reasons: 文件失败原因汇总 helper。
        has_same_file_name_set: 文件集合等价判断 helper。
        resolve_download_fiscal_fields: fiscal 字段解析 helper。
        index_file_entries: 旧文件条目索引 helper。
        download_version: 当前下载版本号。
        cancel_checker: 可选协作式取消检查器。

    Yields:
        文件级与 filing 级事件。

    Raises:
        RuntimeError: 关键路径异常时抛出。
    """

    accession_no_dash = accession_to_no_dash(filing.accession_number)
    internal_document_id = filing.accession_number
    document_id = f"fil_{internal_document_id}"
    previous_meta = host._safe_get_filing_source_meta(ticker=ticker, document_id=document_id)

    fast_skip_reason = host._can_skip_fast(previous_meta, overwrite)
    if fast_skip_reason is not None:
        Log.debug(
            f"快速预检跳过: ticker={ticker} document_id={document_id}",
            module=host.MODULE,
        )
        filing_result = {
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "status": "skipped",
            "form_type": filing.form_type,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "skip_reason": fast_skip_reason,
            "reason_code": fast_skip_reason,
            "reason_message": "本地已有完整下载结果，跳过重新下载",
        }
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload=build_download_filing_event_payload(filing_result),
        )
        return

    effective_registry = rejection_registry if rejection_registry is not None else {}
    if is_rejected(effective_registry, document_id, overwrite):
        Log.debug(
            f"拒绝注册表跳过: ticker={ticker} document_id={document_id}",
            module=host.MODULE,
        )
        filing_result = {
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "status": "skipped",
            "form_type": filing.form_type,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "skip_reason": "rejection_registry",
            "reason_code": "rejection_registry",
            "reason_message": "命中拒绝注册表，跳过重新下载",
        }
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload=build_download_filing_event_payload(filing_result),
        )
        return

    try:
        remote_files = await _maybe_await(
            host._downloader.list_filing_files(
                cik=cik,
                accession_no_dash=accession_no_dash,
                primary_document=filing.primary_document,
                form_type=filing.form_type,
                include_xbrl=True,
                include_exhibits=True,
                include_http_metadata=(previous_meta is not None and not overwrite),
                cancellation_checker=cancel_checker,
            )
        )
    except SecDownloadCancelledError:
        return
    except FinsDownloadProviderError as exc:
        filing_result = {
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "status": "failed",
            "form_type": filing.form_type,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "error": f"provider_{exc.transport_category.value}",
            "reason_code": f"provider_{exc.transport_category.value}",
            "reason_message": exc.safe_message,
        }
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_FAILED,
            ticker=ticker,
            document_id=document_id,
            payload=build_download_filing_event_payload(filing_result),
        )
        return
    source_fingerprint = build_source_fingerprint(remote_files)
    skip_reason = host._can_skip(
        previous_meta,
        source_fingerprint,
        overwrite,
        remote_files=remote_files,
    )
    if skip_reason is not None:
        Log.debug(
            f"命中已下载跳过: ticker={ticker} document_id={document_id}",
            module=host.MODULE,
        )
        reason_messages = {
            "source_fingerprint_matched": "远端 source_fingerprint 与本地一致，跳过重新下载",
            "remote_files_equivalent": "远端文件集合与本地等价，跳过重新下载",
        }
        filing_result = {
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "status": "skipped",
            "form_type": filing.form_type,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "skip_reason": skip_reason,
            "reason_code": skip_reason,
            "reason_message": reason_messages.get(skip_reason, "命中已下载跳过"),
        }
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload=build_download_filing_event_payload(filing_result),
        )
        return

    preferred_primary = ""
    if filing.form_type == "6-K":
        keep, category, selected_name = await host._precheck_6k_filter(
            remote_files=remote_files,
            primary_document=filing.primary_document,
            ticker=ticker,
            document_id=document_id,
            cancel_checker=cancel_checker,
        )
        if not keep:
            if category == "DOWNLOAD_FAILED":
                Log.warn(
                    "6-K 预下载筛选失败，未生成可用主文档",
                    module=host.MODULE,
                )
                filing_result = {
                    "document_id": document_id,
                    "internal_document_id": internal_document_id,
                    "status": "failed",
                    "form_type": filing.form_type,
                    "filing_date": filing.filing_date,
                    "report_date": filing.report_date,
                    "error": "6k_prefetch_failed",
                    "reason_code": "6k_prefetch_failed",
                    "reason_message": "6-K 预下载筛选失败，未生成可用主文档",
                }
                yield DownloadEvent(
                    event_type=DownloadEventType.FILING_FAILED,
                    ticker=ticker,
                    document_id=document_id,
                    payload=build_download_filing_event_payload(filing_result),
                )
                return
            Log.info(
                (
                    "6-K 筛选未命中，跳过落盘: "
                    f"ticker={ticker} document_id={document_id} category={category} file={selected_name}"
                ),
                module=host.MODULE,
            )
            try:
                artifact_saved, artifact_error = await host._persist_rejected_filing_artifact(
                    ticker=ticker,
                    cik=cik,
                    filing=filing,
                    remote_files=remote_files,
                    overwrite=overwrite,
                    rejection_reason="6k_filtered",
                    rejection_category=category,
                    selected_primary_document=selected_name or filing.primary_document,
                    source_fingerprint=source_fingerprint,
                    cancel_checker=cancel_checker,
                )
            except SecDownloadCancelledError:
                return
            if not artifact_saved:
                filing_result = {
                    "document_id": document_id,
                    "internal_document_id": internal_document_id,
                    "status": "failed",
                    "form_type": filing.form_type,
                    "filing_date": filing.filing_date,
                    "report_date": filing.report_date,
                    "error": "rejected_artifact_download_failed",
                    "reason_code": "rejected_artifact_download_failed",
                    "reason_message": artifact_error or "rejected filing artifact 下载失败",
                }
                yield DownloadEvent(
                    event_type=DownloadEventType.FILING_FAILED,
                    ticker=ticker,
                    document_id=document_id,
                    payload=build_download_filing_event_payload(filing_result),
                )
                return
            if rejection_registry is not None:
                record_rejection(
                    rejection_registry,
                    document_id,
                    "6k_filtered",
                    category,
                    filing.form_type,
                    filing.filing_date,
                )
            filing_result = {
                "document_id": document_id,
                "internal_document_id": internal_document_id,
                "status": "skipped",
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "skip_reason": "6k_filtered",
                "reason_code": "6k_filtered",
                "reason_message": "6-K 预筛选未命中保留条件，跳过落盘",
                "filter_category": category,
            }
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_COMPLETED,
                ticker=ticker,
                document_id=document_id,
                payload=build_download_filing_event_payload(filing_result),
            )
            return
        preferred_primary = selected_name

    token: BatchToken | None = host._batching_repository.begin_batch(ticker)
    try:
        existing_files = index_file_entries(previous_meta)
        file_results: list[DownloadFileResult] = []
        downloaded_payloads: dict[str, bytes] | None = {} if filing.form_type == "6-K" else None
        source_handle = SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=SourceKind.FILING.value,
        )
        async for event in host._downloader.download_files_stream(
            remote_files=remote_files,
            overwrite=overwrite,
            store_file=host._build_store_file(
                source_handle=source_handle,
                payload_sink=downloaded_payloads,
            ),
            batch=token,
            existing_files=existing_files,
            primary_document=filing.primary_document,
            cancellation_checker=cancel_checker,
        ):
            if event.event_type == DownloadEventType.FILE_DOWNLOAD_STARTED.value:
                yield DownloadEvent(
                    event_type=DownloadEventType.FILE_DOWNLOAD_STARTED,
                    ticker=ticker,
                    document_id=document_id,
                    payload={
                        "name": event.name,
                        "source_url": event.source_url,
                        "http_etag": event.http_etag,
                        "http_last_modified": event.http_last_modified,
                        "http_status": event.http_status,
                    },
                )
                continue
            mapped_result = build_file_result_from_downloader_event(event)
            file_results.append(mapped_result)
            yield DownloadEvent(
                event_type=DownloadEventType(event.event_type),
                ticker=ticker,
                document_id=document_id,
                payload=build_download_file_event_payload(mapped_result),
            )

        downloaded_files = sum(1 for item in file_results if item["status"] == "downloaded")
        skipped_files = sum(1 for item in file_results if item["status"] == "skipped")
        failed_files = [item for item in file_results if item["status"] == "failed"]
        if failed_files:
            Log.warn(
                (
                    "filling 下载失败（不落盘 meta）: "
                    f"ticker={ticker} document_id={document_id} failed={len(failed_files)}"
                ),
                module=host.MODULE,
            )
            filing_result = {
                "document_id": document_id,
                "internal_document_id": internal_document_id,
                "status": "failed",
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "failed_files": [build_download_file_event_payload(item) for item in failed_files],
                "reason_code": "file_download_failed",
                "reason_message": summarize_failed_download_file_reasons(failed_files),
            }
            assert token is not None
            host._batching_repository.rollback_batch(token)
            token = None
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_FAILED,
                ticker=ticker,
                document_id=document_id,
                payload=build_download_filing_event_payload(filing_result),
            )
            return

        has_xbrl = host._source_repository.has_staged_filing_xbrl_instance(
            ticker=source_handle.ticker,
            document_id=source_handle.document_id,
            batch=token,
        )

        if (
            previous_meta is not None
            and not overwrite
            and has_current_download_version(previous_meta, download_version)
            and downloaded_files == 0
            and skipped_files == len(file_results)
            and has_same_file_name_set(remote_files, existing_files)
        ):
            filing_result = {
                "document_id": document_id,
                "internal_document_id": internal_document_id,
                "status": "skipped",
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "downloaded_files": downloaded_files,
                "skipped_files": skipped_files,
                "skip_reason": "not_modified",
                "reason_code": "not_modified",
                "reason_message": "所有文件均未修改，跳过重新下载",
                "has_xbrl": has_xbrl,
            }
            assert token is not None
            host._batching_repository.rollback_batch(token)
            token = None
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_COMPLETED,
                ticker=ticker,
                document_id=document_id,
                payload=build_download_filing_event_payload(filing_result),
            )
            return

        primary_document = preferred_primary or filing.primary_document
        file_entries = host._build_file_entries(file_results=file_results, previous_files=existing_files)
        primary_reconcile = None
        if filing.form_type == "6-K":
            assert downloaded_payloads is not None
            prepared_file_values: list[JsonValue] = [entry for entry in file_entries]
            primary_reconcile = select_prepared_6k_primary_document(
                ticker=ticker,
                document_id=document_id,
                meta={
                    "form_type": filing.form_type,
                    "primary_document": primary_document,
                    "files": prepared_file_values,
                },
                candidate_payloads=downloaded_payloads,
            )
            if primary_reconcile is not None:
                primary_document = primary_reconcile.selected_primary_document
        inferred_fiscal_year, inferred_fiscal_period = resolve_download_fiscal_fields(
            source_handle=source_handle,
            source_repository=host._source_repository,
            file_entries=file_entries,
            form_type=filing.form_type,
            report_date=filing.report_date,
        )
        upsert_downloaded_filing_source_document(
            ticker=ticker,
            cik=cik,
            document_id=document_id,
            internal_document_id=internal_document_id,
            filing=filing,
            primary_document=primary_document,
            file_entries=file_entries,
            previous_meta=previous_meta,
            source_fingerprint=source_fingerprint,
            download_version=download_version,
            has_xbrl=has_xbrl,
            inferred_fiscal_year=inferred_fiscal_year,
            inferred_fiscal_period=inferred_fiscal_period,
            source_repository=host._source_repository,
            processed_repository=host._processed_repository,
            resolve_document_version=host._resolve_document_version,
            safe_get_processed_meta=host._safe_get_processed_meta,
            batch=token,
        )
        if primary_reconcile is not None:
            mark_processed_for_6k_reconcile(
                processed_repository=host._processed_repository,
                ticker=ticker,
                document_id=document_id,
                batch=token,
            )
        assert token is not None
        commit_token = token
        token = None
        host._batching_repository.commit_batch(commit_token)
        filing_result = {
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "status": "downloaded",
            "form_type": filing.form_type,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "downloaded_files": downloaded_files,
            "skipped_files": skipped_files,
            "has_xbrl": has_xbrl,
        }
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload=build_download_filing_event_payload(filing_result),
        )
    finally:
        if token is not None:
            host._batching_repository.rollback_batch(token)
