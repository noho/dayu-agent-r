"""SecPipeline 异步下载事件流测试。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import json
from collections.abc import AsyncIterator, Callable, Mapping
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, cast

from dayu.fins.domain.document_models import (
    FinsIngestMethod,
    FinsSourceProvider,
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
    build_source_fingerprint,
)
from dayu.fins.ingestion_runtime import FinsDownloadProgressEvent
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_pipeline import (
    SEC_PIPELINE_DOWNLOAD_VERSION,
    SecPipeline,
    SecPipelineDownloadResult,
    collect_download_result_from_events,
)
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage.fs_source_document_repository import FsSourceDocumentRepository
from dayu.fins.storage import FsDocumentBlobRepository
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
        store_file: Callable[[str, BinaryIO], FileObjectMeta],
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
        file_meta = store_file(descriptor.name, BytesIO(b"payload"))
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
        store_file: Callable[[str, BinaryIO], FileObjectMeta],
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
            file_meta = store_file(descriptor.name, BytesIO(payload_by_name[descriptor.name]))
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
        store_file: Callable[[str, BinaryIO], FileObjectMeta],
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """输出失败事件，不写入 blob。"""

        del overwrite, store_file, existing_files, primary_document, cancellation_checker
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


class LegacyDownloadOnlyStubDownloader:
    """只提供 legacy download_files 聚合接口的下载器桩。"""

    def __init__(self) -> None:
        """初始化 legacy 下载器桩。"""

        self.configure_called = False

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
        """返回固定公司信息。"""

        del ticker, cancellation_checker
        return ("320193", "Apple Inc.", "0000320193")

    async def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """返回固定 submissions。"""

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
        """返回固定远端文件列表。"""

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

    async def download_files(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: Callable[[str, BinaryIO], FileObjectMeta],
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[dict[str, JsonValue | FileObjectMeta]]:
        """通过 legacy 聚合接口写入单文件并返回结果。"""

        del overwrite, existing_files, primary_document, cancellation_checker
        descriptor = remote_files[0]
        file_meta = store_file(descriptor.name, BytesIO(b"legacy-payload"))
        return [
            {
                "name": descriptor.name,
                "status": "downloaded",
                "file_meta": file_meta,
                "source_url": descriptor.source_url,
                "http_etag": descriptor.http_etag,
                "http_last_modified": descriptor.http_last_modified,
                "http_status": descriptor.http_status,
            }
        ]


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
        self.stage_calls = 0
        self._events = events

    def has_filing_xbrl_instance(self, ticker: str, document_id: str) -> bool:
        """记录调用后转发到真实实现。"""

        self.has_filing_xbrl_instance_calls.append((ticker, document_id))
        return super().has_filing_xbrl_instance(ticker, document_id)

    def stage_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
    ) -> SourceHandle:
        """记录 staging 调用后转发到真实实现。"""

        self.stage_calls += 1
        if self._events is not None:
            self._events.append("stage")
        return super().stage_source_document(req, source_kind)


class _StagingAwareSecBlobRepository(FsDocumentBlobRepository):
    """记录 SEC blob 写入前 source meta 是否已被 staging 承认。"""

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
        self.observed_ingest_complete: list[bool] = []

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录 source meta 承认事实后转发真实 blob 写入。"""

        if isinstance(handle, SourceHandle):
            meta = self._source_repository.get_source_meta(
                handle.ticker,
                handle.document_id,
                SourceKind(handle.source_kind),
            )
            self.observed_ingest_complete.append(bool(meta.get("ingest_complete", False)))
        self._events.append(f"store:{filename}")
        return super().store_file(
            handle,
            filename,
            data,
            content_type=content_type,
            metadata=metadata,
        )


async def _collect_events(
    pipeline: SecPipeline,
    ticker: str,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> list[DownloadEvent]:
    """收集异步下载事件。

    Args:
        pipeline: 待执行的 SEC pipeline。
        ticker: 下载 ticker。
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

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL"))
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


def test_download_stream_stages_source_before_blob_write(tmp_path: Path) -> None:
    """SEC stream 下载路径在 downloader store_file 回调前必须完成 source staging。"""

    events_log: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _SpySourceRepository(tmp_path, repository_set, events_log)
    blob_repository = _StagingAwareSecBlobRepository(tmp_path, repository_set, source_repository, events_log)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        source_repository=source_repository,
        blob_repository=blob_repository,
        processor_registry=build_fins_processor_registry(),
    )
    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL"))
    final_result = _event_pipeline_result(events[-1])
    meta = source_repository.get_source_meta("AAPL", "fil_0000000000-25-000001", SourceKind.FILING)

    assert final_result["summary"]["downloaded"] == 1
    assert events_log[0] == "stage"
    assert events_log[1] == "store:sample-10k.htm"
    assert blob_repository.observed_ingest_complete == [False]
    assert meta["ingest_complete"] is True


def test_download_legacy_path_stages_source_before_blob_write(tmp_path: Path) -> None:
    """SEC legacy download_files 路径在 store_file 回调前必须完成 source staging。"""

    events_log: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _SpySourceRepository(tmp_path, repository_set, events_log)
    blob_repository = _StagingAwareSecBlobRepository(tmp_path, repository_set, source_repository, events_log)
    legacy_downloader = LegacyDownloadOnlyStubDownloader()
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=cast(SecDownloader, legacy_downloader),
        source_repository=source_repository,
        blob_repository=blob_repository,
        processor_registry=build_fins_processor_registry(),
    )
    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL"))
    final_result = _event_pipeline_result(events[-1])
    meta = source_repository.get_source_meta("AAPL", "fil_0000000000-25-000001", SourceKind.FILING)

    assert final_result["summary"]["downloaded"] == 1
    assert events_log[0] == "stage"
    assert events_log[1] == "store:sample-10k.htm"
    assert blob_repository.observed_ingest_complete == [False]
    assert meta["ingest_complete"] is True


def test_failed_sec_download_leaves_incomplete_staging_and_retry_completes(tmp_path: Path) -> None:
    """失败下载不产生完成态 source；重试复用匹配 staging 并完成同一 source。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _SpySourceRepository(tmp_path, repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    document_id = "fil_0000000000-25-000001"
    remote_file = RemoteFileDescriptor(
        name="sample-10k.htm",
        source_url="https://example.com/sample-10k.htm",
        http_etag="etag-v1",
        http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
        remote_size=100,
        http_status=200,
    )
    failing_pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=FailingStreamStubDownloader(),
        source_repository=source_repository,
        blob_repository=blob_repository,
        processor_registry=build_fins_processor_registry(),
    )
    import asyncio

    failed_events = asyncio.run(_collect_events(failing_pipeline, ticker="AAPL"))
    failed_result = _event_pipeline_result(failed_events[-1])
    failed_handle = SourceHandle(ticker="AAPL", document_id=document_id, source_kind=SourceKind.FILING.value)
    try:
        failed_meta = source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    except FileNotFoundError:
        failed_meta = None

    assert failed_result["summary"]["failed"] == 1
    assert failed_meta is None or failed_meta["ingest_complete"] is False
    assert {entry.name for entry in blob_repository.list_entries(failed_handle)} <= {"meta.json"}
    assert source_repository.stage_calls == 1
    if failed_meta is None:
        source_repository.stage_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id=document_id,
                internal_document_id="0000000000-25-000001",
                form_type="10-K",
                meta={
                    "ingest_method": FinsIngestMethod.DOWNLOAD.to_storage_value(),
                    "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                    "source_fingerprint": build_source_fingerprint([remote_file]),
                    "company_id": "320193",
                    "download_version": SEC_PIPELINE_DOWNLOAD_VERSION,
                    "ingest_complete": False,
                },
            ),
            SourceKind.FILING,
        )
    stage_calls_before_retry = source_repository.stage_calls

    retry_pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        source_repository=source_repository,
        blob_repository=blob_repository,
        processor_registry=build_fins_processor_registry(),
    )
    retry_events = asyncio.run(_collect_events(retry_pipeline, ticker="AAPL"))
    retry_result = _event_pipeline_result(retry_events[-1])
    completed_meta = source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)

    assert retry_result["summary"]["downloaded"] == 1
    assert source_repository.stage_calls == stage_calls_before_retry + 1
    assert completed_meta["ingest_complete"] is True
    assert completed_meta["files"][0]["name"] == "sample-10k.htm"


def test_download_stream_final_status_does_not_recheck_cancel_token(
    tmp_path: Path,
) -> None:
    """最终状态只使用已记录取消路径，不在收尾阶段重读取消 token。"""

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
            cancel_checker=_cancel_on_second_call,
        )
    )
    final_result = _event_pipeline_result(events[-1])

    assert final_result["status"] == "ok"
    assert call_count == 1


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
            cancel_checker=lambda: True,
        )
    )
    final_result = _event_pipeline_result(events[-1])

    assert final_result["status"] == "cancelled"
    assert downloader.fetch_json_calls
    assert downloader.list_filing_files_called is False


def test_download_sync_wrapper_aggregates_stream_result(tmp_path: Path) -> None:
    """验证同步 download 包装器可返回事件流最终结果。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)
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
            pipeline.download_stream(ticker="AAPL", overwrite=False),
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

    document_dir = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001"
    document_dir.mkdir(parents=True, exist_ok=True)
    (document_dir / "meta.json").write_text(
        json.dumps(
            {
                "document_version": "v1",
                "source_fingerprint": "fp-ready",
                "download_version": SEC_PIPELINE_DOWNLOAD_VERSION,
                "ingest_complete": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamStubDownloader(),
        processor_registry=build_fins_processor_registry(),
    )

    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL"))
    filing_event = next(event for event in events if event.event_type == "filing_completed")
    assert filing_event.payload["skip_reason"] == "already_downloaded_complete"
    assert filing_event.payload["reason_code"] == "already_downloaded_complete"
    assert "完整下载结果" in str(filing_event.payload["reason_message"])
    assert _event_filing_result(filing_event)["skip_reason"] == "already_downloaded_complete"


def test_download_stream_resolves_has_xbrl_via_source_repository(tmp_path: Path) -> None:
    """验证下载完成后的 has_xbrl 由源文档仓储事实接口回填。"""

    source_repository = _SpySourceRepository(tmp_path)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StreamXbrlStubDownloader(),
        source_repository=source_repository,
        processor_registry=build_fins_processor_registry(),
    )

    import asyncio

    events = asyncio.run(_collect_events(pipeline, ticker="AAPL"))
    filing_event = next(event for event in events if event.event_type == "filing_completed")

    assert filing_event.payload["has_xbrl"] is True
    assert source_repository.has_filing_xbrl_instance_calls == [("AAPL", "fil_0000000000-25-000001")]
