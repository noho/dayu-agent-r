"""SecPipeline 异步下载事件流测试。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

from collections.abc import AsyncIterator, Callable, Mapping
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, cast

import pytest

from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    FileObjectMeta,
    ProcessedHandle,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.sec_downloader import (
    DownloaderEvent,
    RemoteFileDescriptor,
    SecDownloadCancelledError,
    SecDownloader,
    StoreDownloadedFile,
    _PrefetchEvent,
    _PrefetchFailed,
    _PrefetchedFile,
    _PrefetchStarted,
)
from dayu.fins.ingestion_runtime import FinsDownloadProgressEvent
from dayu.fins.download_contract import (
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_pipeline import (
    SecPipeline,
    SecPipelineDownloadResult,
    collect_download_result_from_events,
)
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage.fs_source_document_repository import FsSourceDocumentRepository
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set


def _event_pipeline_result(event: DownloadEvent) -> SecPipelineDownloadResult:
    """从完成事件中读取并收窄 pipeline result。"""

    raw_result = event.payload.get("result")
    assert isinstance(raw_result, dict)
    return cast(SecPipelineDownloadResult, raw_result)


def _event_filing_result(event: DownloadEvent) -> Mapping[str, JsonValue]:
    """从 filing 事件中读取并收窄 filing_result。"""

    raw_result = event.payload.get("filing_result")
    assert isinstance(raw_result, Mapping)
    return raw_result


class StreamStubDownloader(SecDownloader):
    """用于验证 `download_stream` 的下载器桩。"""

    def __init__(self) -> None:
        """初始化下载器桩。"""

        self.configure_called = False

    async def prefetch_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        *,
        allow_not_modified: bool,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[_PrefetchEvent]:
        """为 pipeline 测试产生无 storage callback 的固定 prefetch variants。

        Args:
            remote_files: 远端 descriptors。
            allow_not_modified: 是否允许 conditional transport。
            existing_files: 既有文件映射。
            primary_document: 主文档名。
            cancellation_checker: 可选取消检查器。

        Yields:
            started 与 downloaded/failed typed variants。

        Raises:
            无。
        """

        del allow_not_modified, existing_files, primary_document, cancellation_checker
        for descriptor in remote_files:
            yield _PrefetchStarted(descriptor=descriptor)
            if isinstance(self, FailingStreamStubDownloader):
                yield _PrefetchFailed(
                    descriptor=descriptor,
                    http_status=descriptor.http_status,
                    reason_code="download_failed",
                    reason_message="测试下载失败",
                    error="测试下载失败",
                )
                continue
            payload = b"<xbrl></xbrl>" if descriptor.name.endswith(".xml") else b"<html>payload</html>"
            yield _PrefetchedFile(
                descriptor=descriptor,
                http_status=descriptor.http_status or 200,
                content=payload,
            )

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """记录配置调用。"""

        del user_agent, sleep_seconds, max_retries
        self.configure_called = True

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。"""

        return ticker.strip().upper()

    async def resolve_company(
        self,
        ticker: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[str, str, str]:
        """返回固定公司信息。

        Args:
            ticker: 股票代码。
            cancellation_checker: 可选取消检查器。

        Returns:
            `(cik, company_name, cik10)`。

        Raises:
            无。
        """

        del ticker, cancellation_checker
        return ("320193", "Apple Inc.", "0000320193")

    async def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """返回固定 submissions。

        Args:
            cik10: 10 位 CIK。
            cancellation_checker: 可选取消检查器。

        Returns:
            submissions JSON。

        Raises:
            无。
        """

        del cik10, cancellation_checker
        return {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-02-01"],
                    "reportDate": ["2024-12-31"],
                    "accessionNumber": ["0000000000-25-000001"],
                    "primaryDocument": ["sample-10k.htm"],
                },
                "files": [],
            }
        }

    async def list_filing_files(
        self,
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool = True,
        include_exhibits: bool = True,
        include_http_metadata: bool = True,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[RemoteFileDescriptor]:
        """返回固定远端文件列表。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            primary_document: 主文件名。
            form_type: 表单类型。
            include_xbrl: 是否包含 XBRL。
            include_exhibits: 是否包含 exhibits。
            include_http_metadata: 是否拉取 HTTP 元数据。
            cancellation_checker: 可选取消检查器。

        Returns:
            远端文件描述列表。

        Raises:
            无。
        """

        del (
            cik,
            accession_no_dash,
            primary_document,
            form_type,
            include_xbrl,
            include_exhibits,
            include_http_metadata,
            cancellation_checker,
        )
        return [
            RemoteFileDescriptor(
                name="sample-10k.htm",
                source_url="https://example.com/sample-10k.htm",
                http_etag="etag-v1",
                http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
                remote_size=100,
                http_status=200,
            )
        ]

    async def download_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """输出单文件下载事件。"""

        del overwrite, existing_files, primary_document, cancellation_checker
        descriptor = remote_files[0]
        yield DownloaderEvent(
            event_type="file_download_started",
            name=descriptor.name,
            source_url=descriptor.source_url,
            http_etag=descriptor.http_etag,
            http_last_modified=descriptor.http_last_modified,
            http_status=descriptor.http_status,
        )
        file_meta = store_file(descriptor.name, BytesIO(b"payload"), batch=batch)
        yield DownloaderEvent(
            event_type="file_downloaded",
            name=descriptor.name,
            source_url=descriptor.source_url,
            http_etag=descriptor.http_etag,
            http_last_modified=descriptor.http_last_modified,
            http_status=descriptor.http_status,
            file_meta=file_meta,
        )


class StreamXbrlStubDownloader(StreamStubDownloader):
    """用于验证 download_stream 的 XBRL 落盘路径。"""

    async def list_filing_files(
        self,
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool = True,
        include_exhibits: bool = True,
        include_http_metadata: bool = True,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[RemoteFileDescriptor]:
        """返回 HTML 与 XBRL instance 两个远端文件。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            primary_document: 主文件名。
            form_type: 表单类型。
            include_xbrl: 是否包含 XBRL。
            include_exhibits: 是否包含 exhibits。
            include_http_metadata: 是否拉取 HTTP 元数据。
            cancellation_checker: 可选取消检查器。

        Returns:
            远端文件描述列表。

        Raises:
            无。
        """

        del (
            cik,
            accession_no_dash,
            primary_document,
            form_type,
            include_xbrl,
            include_exhibits,
            include_http_metadata,
            cancellation_checker,
        )
        return [
            RemoteFileDescriptor(
                name="sample-10k.htm",
                source_url="https://example.com/sample-10k.htm",
                http_etag="etag-v1",
                http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
                remote_size=100,
                http_status=200,
            ),
            RemoteFileDescriptor(
                name="sample_htm.xml",
                source_url="https://example.com/sample_htm.xml",
                http_etag="etag-xbrl",
                http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
                remote_size=80,
                http_status=200,
            ),
        ]

    async def download_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """输出 HTML 与 XBRL instance 两个下载事件。"""

        del overwrite, existing_files, primary_document, cancellation_checker
        payload_by_name = {
            "sample-10k.htm": b"<html>payload</html>",
            "sample_htm.xml": b"<xbrl></xbrl>",
        }
        for descriptor in remote_files:
            yield DownloaderEvent(
                event_type="file_download_started",
                name=descriptor.name,
                source_url=descriptor.source_url,
                http_etag=descriptor.http_etag,
                http_last_modified=descriptor.http_last_modified,
                http_status=descriptor.http_status,
            )
            file_meta = store_file(
                descriptor.name,
                BytesIO(payload_by_name[descriptor.name]),
                batch=batch,
            )
            yield DownloaderEvent(
                event_type="file_downloaded",
                name=descriptor.name,
                source_url=descriptor.source_url,
                http_etag=descriptor.http_etag,
                http_last_modified=descriptor.http_last_modified,
                http_status=descriptor.http_status,
                file_meta=file_meta,
            )


class FailingStreamStubDownloader(StreamStubDownloader):
    """下载文件失败且不调用 store_file 的下载器桩。"""

    async def download_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """输出失败事件，不写入 blob。"""

        del overwrite, store_file, batch, existing_files, primary_document, cancellation_checker
        descriptor = remote_files[0]
        yield DownloaderEvent(
            event_type="file_download_started",
            name=descriptor.name,
            source_url=descriptor.source_url,
            http_etag=descriptor.http_etag,
            http_last_modified=descriptor.http_last_modified,
            http_status=descriptor.http_status,
        )
        yield DownloaderEvent(
            event_type="file_failed",
            name=descriptor.name,
            source_url=descriptor.source_url,
            http_etag=descriptor.http_etag,
            http_last_modified=descriptor.http_last_modified,
            http_status=descriptor.http_status,
            reason_code="download_error",
            reason_message="forced download failure",
            error="forced download failure",
        )


class CancelAwareCollectionDownloader(StreamStubDownloader):
    """用于验证 collection 阶段取消传播的下载器桩。"""

    def __init__(self) -> None:
        """初始化下载器桩。"""

        super().__init__()
        self.fetch_json_calls: list[str] = []
        self.list_filing_files_called = False

    async def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """返回带历史 submissions 文件的响应。

        Args:
            cik10: 10 位 CIK。
            cancellation_checker: 可选取消检查器。

        Returns:
            submissions JSON。

        Raises:
            无。
        """

        del cik10, cancellation_checker
        return {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2025-02-01"],
                    "reportDate": ["2024-12-31"],
                    "accessionNumber": ["0000000000-25-000001"],
                    "primaryDocument": ["sample-10k.htm"],
                },
                "files": [{"name": "CIK0000320193-submissions-001.json"}],
            }
        }

    async def fetch_json(
        self,
        url: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """在历史 submissions 补拉处观察取消。

        Args:
            url: 请求 URL。
            cancellation_checker: 可选取消检查器。

        Returns:
            JSON 字典。

        Raises:
            SecDownloadCancelledError: 取消检查器命中时抛出。
        """

        self.fetch_json_calls.append(url)
        if cancellation_checker is not None and cancellation_checker():
            raise SecDownloadCancelledError("cancelled during history fetch")
        return {}

    async def list_filing_files(
        self,
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool = True,
        include_exhibits: bool = True,
        include_http_metadata: bool = True,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[RemoteFileDescriptor]:
        """记录不应到达的 filing 文件列表调用。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            primary_document: 主文件名。
            form_type: 表单类型。
            include_xbrl: 是否包含 XBRL。
            include_exhibits: 是否包含 exhibits。
            include_http_metadata: 是否拉取 HTTP 元数据。
            cancellation_checker: 可选取消检查器。

        Returns:
            远端文件描述列表。

        Raises:
            无。
        """

        self.list_filing_files_called = True
        return await super().list_filing_files(
            cik=cik,
            accession_no_dash=accession_no_dash,
            primary_document=primary_document,
            form_type=form_type,
            include_xbrl=include_xbrl,
            include_exhibits=include_exhibits,
            include_http_metadata=include_http_metadata,
            cancellation_checker=cancellation_checker,
        )


class ProviderFailureHistoryDownloader(CancelAwareCollectionDownloader):
    """历史 submissions 请求抛出预构造 typed provider failure 的 fake。"""

    def __init__(self, failure: FinsDownloadProviderError) -> None:
        """初始化历史文件失败 fake。

        Args:
            failure: fetch_json 应原样抛出的来源失败。

        Raises:
            无。
        """

        super().__init__()
        self.failure = failure

    async def fetch_json(
        self,
        url: str,
        cancellation_checker: Callable[[], bool] | None = None,
    ) -> dict[str, JsonValue]:
        """在历史 submissions owner 处原样抛出 typed failure。"""

        del cancellation_checker
        self.fetch_json_calls.append(url)
        raise self.failure


class _SpySourceRepository(FsSourceDocumentRepository):
    """记录 SEC source repository 调用的源文档仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet | None = None,
        events: list[str] | None = None,
    ) -> None:
        """初始化 spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self.has_filing_xbrl_instance_calls: list[tuple[str, str]] = []
        self.final_source_calls = 0
        self._events = events

    def has_filing_xbrl_instance(self, ticker: str, document_id: str) -> bool:
        """记录调用后转发到真实实现。"""

        self.has_filing_xbrl_instance_calls.append((ticker, document_id))
        return super().has_filing_xbrl_instance(ticker, document_id)

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """记录唯一 final source create 后转发。"""

        self.final_source_calls += 1
        if self._events is not None:
            self._events.append("final_source")
        return super().create_source_document(req, source_kind, batch=batch)


class _BlobFirstSecBlobRepository(FsDocumentBlobRepository):
    """证明 SEC blob 写入时 published source 尚不存在的仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        source_repository: FsSourceDocumentRepository,
        events: list[str],
    ) -> None:
        """初始化 SEC blob 仓储 spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._source_repository = source_repository
        self._events = events
        self.observed_source_absent: list[bool] = []

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录 published source 缺席事实后转发 batch blob 写入。"""

        if isinstance(handle, SourceHandle):
            try:
                self._source_repository.get_source_meta(
                    handle.ticker,
                    handle.document_id,
                    SourceKind(handle.source_kind),
                )
            except FileNotFoundError:
                self.observed_source_absent.append(True)
            else:
                self.observed_source_absent.append(False)
        self._events.append(f"store:{filename}")
        return super().store_file(
            handle,
            filename,
            data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )


async def _collect_events(
    pipeline: SecPipeline,
    ticker: str,
    *,
    start_is_explicit: bool,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> list[DownloadEvent]:
    """收集异步下载事件。

    Args:
        pipeline: 待执行的 SEC pipeline。
        ticker: 下载 ticker。
        start_is_explicit: 起始日期是否来自调用方显式输入。
        cancel_checker: 可选取消检查函数。

    Returns:
        下载事件列表。

    Raises:
        ValueError: pipeline 参数非法时由下游抛出。
    """

    events: list[DownloadEvent] = []
    async for event in pipeline.download_stream(
        ticker=ticker,
        overwrite=False,
        start_is_explicit=start_is_explicit,
        cancel_checker=cancel_checker,
    ):
        events.append(event)
    return events


async def _event_stream(events: tuple[DownloadEvent, ...]) -> AsyncIterator[DownloadEvent]:
    """把固定事件元组转为异步事件流。"""

    for event in events:
        yield event


def test_download_stream_emits_ordered_events(tmp_path: Path) -> None:
    """验证事件顺序与完成事件负载。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )
    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL", start_is_explicit=False))
    event_types = [event.event_type for event in events]
    assert event_types[0] == "pipeline_started"
    assert "company_resolved" in event_types
    assert "filing_started" in event_types
    assert "file_download_started" in event_types
    assert "file_downloaded" in event_types
    assert "filing_completed" in event_types
    assert event_types[-1] == "pipeline_completed"
    final_result = _event_pipeline_result(events[-1])
    assert final_result["summary"]["downloaded"] == 1


def test_download_stream_writes_blob_before_single_complete_source(tmp_path: Path) -> None:
    """SEC stream 必须 blob-first，并且最终 source 只发布一次。"""

    events_log: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = _SpySourceRepository(tmp_path, repository_set, events_log)
    blob_repository = _BlobFirstSecBlobRepository(tmp_path, repository_set, source_repository, events_log)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        batching_repository=batching_repository,
        downloader=StreamStubDownloader(),
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set),
        source_repository=source_repository,
        processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=repository_set),
        blob_repository=blob_repository,
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=repository_set,
        ),
        processor_registry=build_fins_processor_registry(),
    )
    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL", start_is_explicit=False))
    final_result = _event_pipeline_result(events[-1])
    meta = source_repository.get_source_meta("AAPL", "fil_0000000000-25-000001", SourceKind.FILING)

    assert final_result["summary"]["downloaded"] == 1
    assert events_log == ["store:sample-10k.htm", "final_source"]
    assert blob_repository.observed_source_absent == [True]
    assert source_repository.final_source_calls == 1
    assert meta["ingest_complete"] is True


def test_failed_sec_download_rolls_back_and_retry_publishes_complete_source(tmp_path: Path) -> None:
    """失败下载不发布 source/blob；重试从干净 published state 完整提交。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = _SpySourceRepository(tmp_path, repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    document_id = "fil_0000000000-25-000001"
    failing_pipeline = SecPipeline(
        workspace_root=tmp_path,
        batching_repository=batching_repository,
        downloader=FailingStreamStubDownloader(),
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set),
        source_repository=source_repository,
        processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=repository_set),
        blob_repository=blob_repository,
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=repository_set,
        ),
        processor_registry=build_fins_processor_registry(),
    )
    import asyncio

    failed_events = asyncio.run(_collect_events(failing_pipeline, ticker="AAPL", start_is_explicit=False))
    failed_result = _event_pipeline_result(failed_events[-1])
    failed_handle = SourceHandle(ticker="AAPL", document_id=document_id, source_kind=SourceKind.FILING.value)
    assert failed_result["summary"]["failed"] == 1
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    assert blob_repository.list_entries(failed_handle) == []
    assert source_repository.final_source_calls == 0

    retry_pipeline = SecPipeline(
        workspace_root=tmp_path,
        batching_repository=batching_repository,
        downloader=StreamStubDownloader(),
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set),
        source_repository=source_repository,
        processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=repository_set),
        blob_repository=blob_repository,
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=repository_set,
        ),
        processor_registry=build_fins_processor_registry(),
    )
    retry_events = asyncio.run(_collect_events(retry_pipeline, ticker="AAPL", start_is_explicit=False))
    retry_result = _event_pipeline_result(retry_events[-1])
    completed_meta = source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)

    assert retry_result["summary"]["downloaded"] == 1
    assert source_repository.final_source_calls == 1
    assert completed_meta["ingest_complete"] is True
    assert completed_meta["files"][0]["name"] == "sample-10k.htm"


def test_download_stream_repair_gate_rechecks_cancel_before_company_batch(
    tmp_path: Path,
) -> None:
    """whole-tree repair gate 后、company batch 前必须主动重读取消 token。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )
    call_count = 0

    def _cancel_on_second_call() -> bool:
        """第二次读取时才返回取消。

        Args:
            无。

        Returns:
            第二次及之后调用返回 ``True``。

        Raises:
            无。
        """

        nonlocal call_count
        call_count += 1
        return call_count >= 2

    import asyncio

    events = asyncio.run(
        _collect_events(
            pipeline,
            ticker="AAPL",
            start_is_explicit=False,
            cancel_checker=_cancel_on_second_call,
        )
    )
    final_result = _event_pipeline_result(events[-1])

    assert final_result["status"] == "cancelled"
    assert call_count == 2


def test_download_stream_cancel_stops_during_collection_before_filing_requests(
    tmp_path: Path,
) -> None:
    """collection 阶段取消后不应继续进入 filing 文件列表请求。"""

    downloader = CancelAwareCollectionDownloader()
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    import asyncio

    events = asyncio.run(
        _collect_events(
            pipeline,
            ticker="AAPL",
            start_is_explicit=False,
            cancel_checker=lambda: True,
        )
    )
    final_result = _event_pipeline_result(events[-1])

    assert final_result["status"] == "cancelled"
    assert downloader.fetch_json_calls
    assert downloader.list_filing_files_called is False


def test_download_stream_historical_submissions_provider_failure_is_operation_fatal(
    tmp_path: Path,
) -> None:
    """历史 submissions typed failure 必须越过 collection，不能缩减候选集。"""

    expected = FinsDownloadProviderError(
        source=FinsDownloadSource.SEC,
        transport_category=FinsDownloadTransportCategory.TIMEOUT,
        retryable=True,
        safe_message="SEC 来源请求超时",
    )
    downloader = ProviderFailureHistoryDownloader(expected)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    import asyncio

    with pytest.raises(FinsDownloadProviderError) as exc_info:
        asyncio.run(
            _collect_events(
                pipeline,
                ticker="AAPL",
                start_is_explicit=False,
                cancel_checker=lambda: False,
            )
        )

    assert exc_info.value is expected
    assert downloader.fetch_json_calls
    assert downloader.list_filing_files_called is False


def test_download_sync_wrapper_aggregates_stream_result(tmp_path: Path) -> None:
    """验证同步 download 包装器可返回事件流最终结果。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)
    assert result["action"] == "download"
    assert result["summary"]["downloaded"] == 1


def test_adapter_progress_sink_uses_filing_granularity(tmp_path: Path) -> None:
    """验证 SEC adapter progress 投影按 filing 而不是文件输出。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )
    progress_events: list[FinsDownloadProgressEvent] = []

    import asyncio

    result = asyncio.run(
        collect_download_result_from_events(
            pipeline.download_stream(
                ticker="AAPL",
                overwrite=False,
                start_is_explicit=False,
            ),
            progress_sink=progress_events.append,
        )
    )

    assert result["summary"]["downloaded"] == 1
    assert [(event.stage, event.document_id, event.file_name, event.message) for event in progress_events] == [
        ("download.filing_started", "fil_0000000000-25-000001", None, "开始下载"),
        ("download.filing_completed", "fil_0000000000-25-000001", None, "完成下载"),
    ]


def test_adapter_progress_sink_reports_filing_failure() -> None:
    """验证 SEC adapter progress 用 filing failed 表达下载失败。"""

    progress_events: list[FinsDownloadProgressEvent] = []
    pipeline_result: SecPipelineDownloadResult = {
        "pipeline": "sec",
        "action": "download",
        "status": "ok",
        "ticker": "AAPL",
        "market_profile": {},
        "filters": {},
        "warnings": [],
        "filings": [],
        "summary": {
            "total": 1,
            "downloaded": 0,
            "skipped": 0,
            "rejected": 0,
            "failed": 1,
            "elapsed_ms": 0,
            "reused_downloads": 0,
            "converted": 0,
        },
    }

    import asyncio

    asyncio.run(
        collect_download_result_from_events(
            _event_stream(
                (
                    DownloadEvent(
                        event_type=DownloadEventType.FILING_STARTED,
                        ticker="AAPL",
                        document_id="fil-failed",
                    ),
                    DownloadEvent(
                        event_type=DownloadEventType.FILE_FAILED,
                        ticker="AAPL",
                        document_id="fil-failed",
                        payload={"name": "detail.xml"},
                    ),
                    DownloadEvent(
                        event_type=DownloadEventType.FILING_FAILED,
                        ticker="AAPL",
                        document_id="fil-failed",
                    ),
                    DownloadEvent(
                        event_type=DownloadEventType.PIPELINE_COMPLETED,
                        ticker="AAPL",
                        payload={"result": cast(JsonValue, pipeline_result)},
                    ),
                )
            ),
            progress_sink=progress_events.append,
        )
    )

    assert [(event.stage, event.document_id, event.file_name, event.message) for event in progress_events] == [
        ("download.filing_started", "fil-failed", None, "开始下载"),
        ("download.filing_failed", "fil-failed", None, "下载失败"),
    ]


def test_download_stream_filing_skip_event_exposes_reason_fields(tmp_path: Path) -> None:
    """验证 filing 跳过事件会同时暴露扁平与嵌套的原因字段。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )

    import asyncio

    first_events = asyncio.run(_collect_events(pipeline, ticker="AAPL", start_is_explicit=False))
    assert _event_pipeline_result(first_events[-1])["summary"]["downloaded"] == 1
    events = asyncio.run(_collect_events(pipeline, ticker="AAPL", start_is_explicit=False))
    filing_event = next(event for event in events if event.event_type == "filing_completed")
    assert filing_event.payload["skip_reason"] == "already_downloaded_complete"
    assert filing_event.payload["reason_code"] == "already_downloaded_complete"
    assert "完整下载结果" in str(filing_event.payload["reason_message"])
    assert _event_filing_result(filing_event)["skip_reason"] == "already_downloaded_complete"


def test_download_stream_resolves_has_xbrl_from_complete_file_entries(tmp_path: Path) -> None:
    """验证 has_xbrl 由同批次完整文件事实派生，不读取未发布 source。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _SpySourceRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        batching_repository=FsBatchingRepository(tmp_path, repository_set=repository_set),
        downloader=StreamXbrlStubDownloader(),
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set),
        source_repository=source_repository,
        processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=repository_set),
        blob_repository=blob_repository,
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=repository_set,
        ),
        processor_registry=build_fins_processor_registry(),
    )

    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL", start_is_explicit=False))
    filing_event = next(event for event in events if event.event_type == "filing_completed")
    published_meta = source_repository.get_source_meta(
        "AAPL",
        "fil_0000000000-25-000001",
        SourceKind.FILING,
    )

    assert filing_event.payload["has_xbrl"] is True
    assert source_repository.has_filing_xbrl_instance_calls == []
    assert published_meta["ingest_complete"] is True
