"""SecPipeline 异步下载事件流测试。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date

from dayu.contracts.json_value import JsonValue

from collections.abc import AsyncIterator, Callable, Mapping
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, cast

import pytest

from dayu.fins.domain.company_meta_contract import CompanyMetaCommitOutcome
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    DownloadRejectionRegistry,
    DownloadRejectionEntry,
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
from dayu.fins.ingestion_runtime import FinsDownloadProgressEvent, FinsSourceDownloadAdapterRequest, FinsSourceDownloadAdapterFailure
from dayu.fins.download_contract import (
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
    FinsDownloadDateRange,
    FinsDownloadTerminalDisposition,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_filing_collection import FilingRecord
from dayu.fins.pipelines import sec_download_workflow as _sec_download_workflow
from dayu.fins.pipelines.sec_pipeline import (
    SecPipeline,
    SecPipelineDownloadResult,
    collect_download_result_from_events,
    SecDownloadAdapter,
    _summary_from_pipeline_result,
    SEC_PIPELINE_DOWNLOAD_VERSION,
)
from dayu.fins.pipelines.sec_download_workflow import SecDownloadIntegrityAbort
from dayu.fins.ticker_normalization import normalize_ticker
from tests.fins.test_sec_pipeline_download import _seed_complete_sec_source
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage.fs_source_document_repository import FsSourceDocumentRepository
from dayu.fins.storage import (
    FilingMaintenanceRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    SourceIntegrityClassification,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
    SourceIntegrityRevisionConflictError,
    SourceIntegrityRepairRequiredError,
    SourceIntegrityStatus,
    SourceIntegrityReason,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set

_INTEGRITY_FIRST = "fil_0000000000-25-000001"
_INTEGRITY_REJECTED = "fil_0000000000-25-000002"
_INTEGRITY_SECOND = "fil_0000000000-25-000003"
_INTEGRITY_TAIL = "fil_0000000000-25-000004"
_INTEGRITY_IDS = (_INTEGRITY_FIRST, _INTEGRITY_REJECTED, _INTEGRITY_SECOND, _INTEGRITY_TAIL)


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


class _BatchIdentitySecBatchingRepository(FsBatchingRepository):
    """记录 SEC company publication 的 commit/rollback 选择。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet) -> None:
        """初始化 batch operation spy。

        Args:
            workspace_root: 工作区根目录。
            repository_set: 共享 filesystem repository set。

        Returns:
            无。

        Raises:
            OSError: storage 初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit_batch(self, batch: BatchToken) -> CompanyMetaCommitOutcome | None:
        """记录并提交 batch。

        Args:
            batch: 待提交 batch capability。

        Returns:
            download batch 的真实 typed company-meta outcome；无 intent 时返回 ``None``。

        Raises:
            OSError: storage commit 失败时抛出。
            ValueError: capability 非法时抛出。
        """

        self.commit_calls += 1
        return super().commit_batch(batch)

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录并回滚 batch。

        Args:
            batch: 待回滚 batch capability。

        Returns:
            无。

        Raises:
            OSError: storage rollback 失败时抛出。
            ValueError: capability 非法时抛出。
        """

        self.rollback_calls += 1
        super().rollback_batch(batch)


def _reject_unexpected_registry_save(
    repository: FilingMaintenanceRepositoryProtocol,
    ticker: str,
    registry: DownloadRejectionRegistry,
    *,
    batch: BatchToken,
) -> None:
    """拒绝 zero-rejection 测试中的意外 registry 写入。

    Args:
        repository: maintenance repository。
        ticker: canonical ticker。
        registry: rejection registry。
        batch: batch capability。

    Returns:
        无。

    Raises:
        AssertionError: 测试路径意外尝试写 registry 时抛出。
    """

    del repository, ticker, registry, batch
    raise AssertionError("zero-rejection company publication 不应写 registry")


def test_repeat_sec_company_publication_rolls_back_zero_mutation_batch(
    tmp_path: Path,
) -> None:
    """fresh 且 identity 未变化时 SEC caller 必须 rollback，禁止 full-tree swap。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 明确 ``None`` mutation signal 未被 caller 消费时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentitySecBatchingRepository(tmp_path, repository_set)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        batching_repository=batching_repository,
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set),
        processor_registry=build_fins_processor_registry(),
    )
    asyncio.run(
        _sec_download_workflow._publish_sec_post_repair_mutations(
            host=cast(_sec_download_workflow.SecDownloadWorkflowHost, pipeline),
            ticker="AAPL",
            cik="320193",
            company_name="Apple Inc.",
            ticker_aliases=(),
            rejection_decisions=(),
            rejection_registry={},
            overwrite=False,
            record_rejection=lambda _registry, _document_id, _reason, _category, _form, _date: None,
            save_rejection_registry=_reject_unexpected_registry_save,
            cancel_checker=None,
        )
    )
    published_meta_path = tmp_path / "portfolio" / "AAPL" / "meta.json"
    first_meta = published_meta_path.read_bytes()
    asyncio.run(
        _sec_download_workflow._publish_sec_post_repair_mutations(
            host=cast(_sec_download_workflow.SecDownloadWorkflowHost, pipeline),
            ticker="AAPL",
            cik="320193",
            company_name="Apple Inc.",
            ticker_aliases=(),
            rejection_decisions=(),
            rejection_registry={},
            overwrite=False,
            record_rejection=lambda _registry, _document_id, _reason, _category, _form, _date: None,
            save_rejection_registry=_reject_unexpected_registry_save,
            cancel_checker=None,
        )
    )

    assert batching_repository.commit_calls == 1
    assert batching_repository.rollback_calls == 1
    assert published_meta_path.read_bytes() == first_meta


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


class _IntegrityScenarioSource(FsSourceDocumentRepository):
    """在真实 postrepair 枚举前改变合成文件，并保留 owner 分类证据。"""

    def __init__(self, root: Path, repository_set: _FsRepositorySet, mutation: str) -> None:
        """初始化离线场景。

        参数：root 为隔离根；repository_set 为共享 core；mutation 为待制造状态。
        返回：无。异常：初始化失败传播 OSError。
        """
        super().__init__(root, repository_set=repository_set)
        self.root = root
        self.mutation = mutation
        self.scans = 0
        self.inventories: list[tuple[SourceIntegrityClassification, ...]] = []

    def list_source_integrity(self, ticker: str) -> tuple[SourceIntegrityClassification, ...]:
        """按真实文件状态触发 postrepair classifier，不注入异常。

        参数：ticker 为公司身份。返回：真实完整性 inventory。
        异常：文件操作失败传播 OSError；非法状态传播 ValueError。
        """
        self.scans += 1
        if self.scans == 2 and self.mutation:
            locator = self.get_source_document_locator(ticker, _INTEGRITY_SECOND, SourceKind.FILING)
            payload = self.root / locator / "sample-10k.htm"
            if self.mutation == "postrepair":
                payload.write_bytes(b"x" * len(payload.read_bytes()))
            elif self.mutation == SourceIntegrityPreflightReason.UNSAFE_PUBLICATION.value:
                (payload.parent / "undeclared.bin").write_bytes(b"synthetic-unsafe")
            else:
                payload.unlink()
                if self.mutation == SourceIntegrityPreflightReason.MULTIPLE_REPAIR_REQUIRED.value:
                    first_locator = self.get_source_document_locator(ticker, _INTEGRITY_FIRST, SourceKind.FILING)
                    (self.root / first_locator / "sample-10k.htm").unlink()
        result = super().list_source_integrity(ticker)
        self.inventories.append(result)
        return result


class _IntegrityScenarioDownloader(StreamStubDownloader):
    """用离线合成 HTML 和独立真实 writer 驱动四个候选。"""

    def __init__(self, root: Path, repository_set: _FsRepositorySet, *, changes: int = 0, unsafe: bool = False, selection: str = "all") -> None:
        """初始化无网络下载器。

        参数：root 为隔离根；repository_set 为共享 core；changes 为改版次数；unsafe 为 Phase B 损坏；selection 为 postrepair 候选集。
        返回：无。异常：仓储初始化失败传播 OSError。
        """
        super().__init__()
        self.root = root
        self.writer = FsSourceDocumentRepository(root, repository_set=repository_set)
        self.batching = FsBatchingRepository(root, repository_set=repository_set)
        self.changes = changes
        self.unsafe = unsafe
        self.selection = selection
        self.current = ""
        self.requested: list[str] = []
        self.prefetch_rounds = 0

    async def fetch_submissions(self, cik10: str, cancellation_checker: Callable[[], bool] | None = None) -> dict[str, JsonValue]:
        """返回日期升序排列的合成候选，避免默认年份筛选产生歧义。

        参数：cik10 为公司；cancellation_checker 为取消检查器。返回：离线 submissions。
        异常：无。
        """
        del cik10, cancellation_checker
        ids = list(_INTEGRITY_IDS)
        forms = ["10-K", "6-K", "10-K", "10-K"]
        if self.selection == SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED.value:
            ids = [_INTEGRITY_FIRST, _INTEGRITY_TAIL]
            forms = ["10-K", "10-K"]
        elif self.selection == "phase_b":
            ids = [_INTEGRITY_FIRST, _INTEGRITY_SECOND, _INTEGRITY_TAIL]
            forms = ["10-K", "10-K", "10-K"]
        elif self.selection == SourceIntegrityPreflightReason.SELECTED_REJECTED_REPAIR_REQUIRED.value:
            forms = ["10-K", "6-K", "6-K", "10-K"]
        form_values: list[JsonValue] = [form for form in forms]
        recent: dict[str, JsonValue] = {
            "form": form_values, "filingDate": [f"2025-02-0{i + 1}" for i in range(len(ids))],
            "reportDate": ["2024-12-31" for _ in ids],
            "accessionNumber": [item.removeprefix("fil_") for item in ids],
            "primaryDocument": ["sample-10k.htm" for _ in ids],
        }
        return {"filings": {"recent": recent, "files": []}}

    async def list_filing_files(self, cik: str, accession_no_dash: str, primary_document: str, form_type: str,
        include_xbrl: bool = True, include_exhibits: bool = True, include_http_metadata: bool = True,
        cancellation_checker: Callable[[], bool] | None = None) -> list[RemoteFileDescriptor]:
        """记录真实请求并复用离线 descriptor。

        参数：全部参数为真实 downloader 接口输入。返回：合成 descriptor。
        异常：无。
        """
        self.current = accession_no_dash
        self.requested.append(accession_no_dash)
        return await super().list_filing_files(cik, accession_no_dash, primary_document, form_type,
            include_xbrl, include_exhibits, include_http_metadata, cancellation_checker)

    async def fetch_file_bytes(self, url: str, cancellation_checker: Callable[[], bool] | None = None) -> bytes:
        """提供明确无业绩语义的合成 HTML，走真实 6-K 政策。

        参数：url 为 descriptor 标签；cancellation_checker 为取消检查器。
        返回：离线 HTML 字节。异常：无。
        """
        del url, cancellation_checker
        return b"<html><p>Annual general meeting voting results.</p></html>"

    async def prefetch_files_stream(self, remote_files: list[RemoteFileDescriptor], *, allow_not_modified: bool,
        existing_files: dict[str, dict[str, JsonValue]] | None = None, primary_document: str | None = None,
        cancellation_checker: Callable[[], bool] | None = None) -> AsyncIterator[_PrefetchEvent]:
        """在 Phase A/B 之间真实改版或制造 unsafe，不伪造异常。

        参数：全部参数为真实 prefetch 接口输入。返回：异步合成资产事件。
        异常：发布或文件写入失败传播 OSError/ValueError。
        """
        if self.current == _INTEGRITY_SECOND.removeprefix("fil_").replace("-", ""):
            self.prefetch_rounds += 1
            if self.prefetch_rounds <= self.changes:
                meta = self.writer.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
                meta["source_fingerprint"] = f"synthetic-revision-{self.prefetch_rounds}"
                batch = self.batching.begin_batch("AAPL")
                try:
                    self.writer.replace_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING, meta, batch=batch)
                except BaseException:
                    self.batching.rollback_batch(batch)
                    raise
                self.batching.commit_batch(batch)
            if self.unsafe:
                locator = self.writer.get_source_document_locator("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
                (self.root / locator / "undeclared.bin").write_bytes(b"synthetic-unsafe")
        async for event in super().prefetch_files_stream(remote_files, allow_not_modified=allow_not_modified,
            existing_files=existing_files, primary_document=primary_document, cancellation_checker=cancellation_checker):
            if isinstance(event, _PrefetchedFile):
                yield _PrefetchedFile(descriptor=event.descriptor, http_status=event.http_status,
                    content=f"<html>synthetic-round-{self.prefetch_rounds}</html>".encode())
            else:
                yield event


def _build_sec_integrity_scenario(root: Path, scenario: str, *, changes: int = 3) -> tuple[SecPipeline, _IntegrityScenarioDownloader, _IntegrityScenarioSource, _BatchIdentitySecBatchingRepository]:
    """装配共享真实 Fs、独立 writer 和离线下载器。

    参数：root 为隔离根；scenario 为真实损坏/改版场景；changes 为改版次数。
    返回：真实 pipeline、下载器、source 与 batch 观察器。异常：仓储失败传播 OSError/ValueError。
    """
    first_meta = _seed_complete_sec_source(workspace_root=root, document_id=_INTEGRITY_FIRST)
    _seed_complete_sec_source(workspace_root=root, document_id=_INTEGRITY_SECOND)
    postrepair = scenario == "postrepair" or scenario in {reason.value for reason in SourceIntegrityPreflightReason}
    shared = build_fs_repository_set(workspace_root=root)
    if scenario in {SourceIntegrityPreflightReason.SELECTED_REJECTED_REPAIR_REQUIRED.value, "registry"}:
        registry_writer = FsFilingMaintenanceRepository(root, repository_set=shared)
        registry_batching = FsBatchingRepository(root, repository_set=shared)
        batch = registry_batching.begin_batch("AAPL")
        registry_writer.save_download_rejection_registry("AAPL", {_INTEGRITY_SECOND: DownloadRejectionEntry(
            document_id=_INTEGRITY_SECOND,
            reason="synthetic_registry_rejection" if scenario == "registry" else "6k_filtered",
            category="SYNTHETIC_TEST" if scenario == "registry" else "NO_MATCH",
            form_type="10-K" if scenario == "registry" else "6-K",
            filing_date="2025-02-02" if scenario == "registry" else "2025-02-03",
            download_version=SEC_PIPELINE_DOWNLOAD_VERSION)}, batch=batch)
        registry_batching.commit_batch(batch)
    if postrepair:
        (first_meta.parent / "sample-10k.htm").unlink()
    source = _IntegrityScenarioSource(root, shared, scenario if postrepair else "")
    batching = _BatchIdentitySecBatchingRepository(root, shared)
    downloader = _IntegrityScenarioDownloader(root, shared, changes=changes if scenario == "churn" else 0,
        unsafe=scenario == "phase_b", selection="phase_b" if scenario == "registry" else scenario)
    pipeline = SecPipeline(workspace_root=root, source_repository=source, batching_repository=batching,
        blob_repository=FsDocumentBlobRepository(root, repository_set=shared),
        company_repository=FsCompanyMetaRepository(root, repository_set=shared),
        processed_repository=FsProcessedDocumentRepository(root, repository_set=shared),
        filing_maintenance_repository=FsFilingMaintenanceRepository(root, repository_set=shared),
        downloader=downloader, processor_registry=build_fins_processor_registry())
    return pipeline, downloader, source, batching


def _sec_integrity_request(*, overwrite: bool) -> FinsSourceDownloadAdapterRequest:
    """构造显式窗口的真实 SEC adapter 请求。

    参数：overwrite 为覆盖策略。返回：typed 请求。异常：输入非法传播 ValueError。
    """
    return FinsSourceDownloadAdapterRequest(normalized_ticker=normalize_ticker("AAPL"), source=FinsDownloadSource.SEC,
        form_types=("10-K", "6-K"), date_range=FinsDownloadDateRange(date(2025, 1, 1), date(2025, 12, 31), True, True),
        overwrite_existing=overwrite, rebuild_local_artifacts=False, cancellation_checker=_never_sec_cancel)


def _never_sec_cancel() -> bool:
    """提供显式无取消输入。

    参数：无。返回：False。异常：无。
    """
    return False


async def _consume_sec_integrity_events(pipeline: SecPipeline, events: list[DownloadEvent], *, overwrite: bool,
    cancel_checker: Callable[[], bool] | None = None, control: _SecCancelControl | None = None) -> None:
    """保留真实中止前完整事件前缀。

    参数：pipeline 为工作流；events 为事件真源；overwrite 为策略；cancel_checker 为取消检查；control 为事件边界取消器。
    返回：无。异常：真实 typed 中止原样传播。
    """
    async for event in pipeline.download_stream(ticker="AAPL", form_type="10-K,6-K", start_date="2025-01-01",
        end_date="2025-12-31", overwrite=overwrite, start_is_explicit=True, cancel_checker=cancel_checker):
        events.append(event)
        if control is not None:
            control.observe(event)


@pytest.mark.parametrize("changes", (1, 2, 3))
def test_sec_real_identity_retry_budget_and_abort_prefix(tmp_path: Path, changes: int) -> None:
    """独立真实 writer 改版触发原三轮预算，并保全成功和拒绝前缀。

    参数：tmp_path 为隔离根；changes 为改版次数。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, batching = _build_sec_integrity_scenario(tmp_path, "churn", changes=changes)
    events: list[DownloadEvent] = []
    if changes == 3:
        with pytest.raises(SecDownloadIntegrityAbort) as raised:
            asyncio.run(_consume_sec_integrity_events(pipeline, events, overwrite=True))
        abort = raised.value
        assert isinstance(abort.cause, SourceIntegrityRevisionConflictError)
        assert abort.__cause__ is abort.cause
        assert abort.result["status"] == "ok"
        summary = abort.result["summary"]
        assert isinstance(summary, dict)
        assert (summary["total"], summary["downloaded"], summary["rejected"], summary["skipped"], summary["failed"]) == (3, 1, 1, 0, 1)
        assert not any(e.event_type is DownloadEventType.PIPELINE_COMPLETED for e in events)
        assert _INTEGRITY_TAIL[4:].replace("-", "") not in downloader.requested
    else:
        asyncio.run(_consume_sec_integrity_events(pipeline, events, overwrite=True))
        assert _event_pipeline_result(events[-1])["status"] == "ok"
        locator = source.get_source_document_locator("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
        assert (tmp_path / locator / "sample-10k.htm").read_bytes() == f"<html>synthetic-round-{changes + 1}</html>".encode()
    assert downloader.prefetch_rounds == min(changes + 1, 3)
    assert batching.rollback_calls == changes
    terminals = [e for e in events if e.event_type in {DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED}]
    assert [e.document_id for e in terminals[:3]] == [_INTEGRITY_FIRST, _INTEGRITY_REJECTED, _INTEGRITY_SECOND]
    assert source.classify_source_integrity("AAPL", _INTEGRITY_FIRST, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    maintenance = FsFilingMaintenanceRepository(tmp_path)
    assert maintenance.load_download_rejection_registry("AAPL")[_INTEGRITY_REJECTED].reason == "6k_filtered"
    assert maintenance.get_rejected_filing_artifact("AAPL", _INTEGRITY_REJECTED)
    assert maintenance.read_rejected_filing_file_bytes("AAPL", _INTEGRITY_REJECTED, "sample-10k.htm") == b"<html>synthetic-round-0</html>"
    first_locator = source.get_source_document_locator("AAPL", _INTEGRITY_FIRST, SourceKind.FILING)
    assert (tmp_path / first_locator / "sample-10k.htm").read_bytes() == b"<html>synthetic-round-0</html>"


def test_sec_phase_b_real_preflight_aborts_with_confirmed_prior_filing(tmp_path: Path) -> None:
    """真实 Phase B unsafe 保原 cause、一次失败事件与已提交首文档。

    参数：tmp_path 为隔离根。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, batching = _build_sec_integrity_scenario(tmp_path, "phase_b")
    before = source.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
    events: list[DownloadEvent] = []
    with pytest.raises(SecDownloadIntegrityAbort) as raised:
        asyncio.run(_consume_sec_integrity_events(pipeline, events, overwrite=True))
    abort = raised.value
    assert isinstance(abort.cause, SourceIntegrityPreflightError)
    assert abort.cause.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert abort.__cause__ is abort.cause
    rows = abort.result["filings"]
    assert isinstance(rows, list) and len(rows) == 2
    summary = abort.result["summary"]
    assert isinstance(summary, dict) and (summary["total"], summary["downloaded"], summary["failed"]) == (2, 1, 1)
    assert isinstance(rows[-1], dict) and rows[-1]["reason_code"] == "source_integrity_failed"
    assert len([e for e in events if e.event_type is DownloadEventType.FILING_FAILED]) == 1
    assert not any(e.event_type is DownloadEventType.PIPELINE_COMPLETED for e in events)
    assert batching.rollback_calls == 1
    assert source.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING) == before
    assert source.classify_source_integrity("AAPL", _INTEGRITY_FIRST, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    assert _INTEGRITY_TAIL[4:].replace("-", "") not in downloader.requested


@pytest.mark.parametrize("reason", tuple(SourceIntegrityPreflightReason))
def test_sec_postrepair_preflight_abort_preserves_confirmed_prefix(tmp_path: Path, reason: SourceIntegrityPreflightReason) -> None:
    """真实全树复查四预检原因保持已确认 repair 行和原原因。

    参数：tmp_path 为隔离根；reason 为仓储原因。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, _batching = _build_sec_integrity_scenario(tmp_path, reason.value)
    events: list[DownloadEvent] = []
    with pytest.raises(SecDownloadIntegrityAbort) as raised:
        asyncio.run(_consume_sec_integrity_events(pipeline, events, overwrite=False))
    abort = raised.value
    assert isinstance(abort.cause, SourceIntegrityPreflightError) and abort.cause.reason is reason
    assert abort.__cause__ is abort.cause
    rows = abort.result["filings"]
    assert isinstance(rows, list) and len(rows) == 1
    assert isinstance(rows[0], dict) and rows[0]["document_id"] == _INTEGRITY_FIRST and rows[0]["status"] == "downloaded"
    assert downloader.requested == [_INTEGRITY_FIRST[4:].replace("-", "")]
    assert len(source.inventories) == 2
    assert not (tmp_path / "portfolio/AAPL/meta.json").exists()
    assert not any(e.event_type is DownloadEventType.PIPELINE_COMPLETED for e in events)


@pytest.mark.parametrize("scenario", ("postrepair", "churn"))
def test_sec_integrity_abort_adapter_preserves_cause_and_summary(tmp_path: Path, scenario: str, caplog: pytest.LogCaptureFixture) -> None:
    """真实 adapter 严格投影 owner 快照，typed 中止无完成日志。

    参数：tmp_path 为隔离根；scenario 为真实状态；caplog 为日志观察器。
    返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, _batching = _build_sec_integrity_scenario(tmp_path, scenario)
    with caplog.at_level(logging.INFO), pytest.raises(FinsSourceDownloadAdapterFailure) as raised:
        SecDownloadAdapter(pipeline=pipeline).download(_sec_integrity_request(overwrite=scenario == "churn"))
    failure = raised.value
    abort = failure.__cause__
    assert isinstance(abort, SecDownloadIntegrityAbort)
    assert failure.cause is abort.cause and abort.__cause__ is abort.cause
    assert isinstance(failure.cause, SourceIntegrityRepairRequiredError if scenario == "postrepair" else SourceIntegrityRevisionConflictError)
    assert abort.result["status"] == "ok"
    raw_summary = abort.result["summary"]
    assert isinstance(raw_summary, dict)
    assert set(raw_summary) == {"total", "downloaded", "skipped", "rejected", "failed", "elapsed_ms", "reused_downloads", "converted"}
    summary = failure.persisted_summary
    assert summary.downloaded_count == 1
    assert summary.rejected_count == summary.failed_count == (0 if scenario == "postrepair" else 1)
    assert summary.terminal_disposition is (FinsDownloadTerminalDisposition.SUCCEEDED if scenario == "postrepair" else FinsDownloadTerminalDisposition.PARTIAL_FAILURE)
    assert summary.document_rows[0].document_id == _INTEGRITY_FIRST
    assert summary.document_rows[0].artifact_locator is not None
    assert "美股下载完成" not in caplog.text
    assert _INTEGRITY_TAIL[4:].replace("-", "") not in downloader.requested
    assert source.classify_source_integrity("AAPL", _INTEGRITY_FIRST, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    print(json.dumps({"scenario": scenario, "snapshot": abort.result, "typed": summary.to_json_summary(max_json_chars=4096)}, ensure_ascii=False))


class _SecCancelControl:
    """在真实事件边界置取消标记，不替代单 filing 或结果构造。"""

    def __init__(self, checkpoint: str) -> None:
        """初始化取消器。

        参数：checkpoint 为待触发边界。返回：无。异常：无。
        """
        self.checkpoint = checkpoint
        self.cancelled = False

    def __call__(self) -> bool:
        """读取当前取消标记。

        参数：无。返回：取消状态。异常：无。
        """
        return self.cancelled

    def observe(self, event: DownloadEvent) -> None:
        """收到指定真实 filing 事件后置取消标记。

        参数：event 为实际 owner 事件。返回：无。异常：无。
        """
        if self.checkpoint == "single_filing_return" and event.event_type is DownloadEventType.FILING_STARTED:
            self.cancelled = True
        if self.checkpoint in {"between_filings", "postrepair"} and event.event_type is DownloadEventType.FILING_COMPLETED:
            self.cancelled = True


class _CancelAfterInitialInventory:
    """在真实首 preflight inventory 返回时置取消，保留初始 classifier 执行。"""

    def __init__(self, source: _IntegrityScenarioSource, control: _SecCancelControl) -> None:
        """保存真实读取边界。

        参数：source 为仓储；control 为取消器。返回：无。异常：无。
        """
        self.read = source.list_source_integrity
        self.control = control

    def __call__(self, ticker: str) -> tuple[SourceIntegrityClassification, ...]:
        """先真实读 inventory，再置取消。

        参数：ticker 为公司。返回：真实 inventory。异常：仓储失败原样传播 OSError。
        """
        result = self.read(ticker)
        self.control.cancelled = True
        return result


@pytest.mark.parametrize("checkpoint", ("before_first_filing", "between_filings", "single_filing_return"))
def test_sec_loop_tail_cancel_preserves_shared_result_status(tmp_path: Path, checkpoint: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """三个真实循环尾取消分支均由共享 builder 保 cancelled 和确认前缀。

    参数：tmp_path 为隔离根；checkpoint 为取消边界；monkeypatch 为真实 inventory 观察装配。
    返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, _batching = _build_sec_integrity_scenario(tmp_path, "normal")
    control = _SecCancelControl(checkpoint)
    if checkpoint == "before_first_filing":
        monkeypatch.setattr(source, "list_source_integrity", _CancelAfterInitialInventory(source, control))
    events: list[DownloadEvent] = []
    asyncio.run(_consume_sec_integrity_events(pipeline, events, overwrite=True, cancel_checker=control, control=control))
    result = _event_pipeline_result(events[-1])
    assert result["status"] == "cancelled"
    expected = 1 if checkpoint == "between_filings" else 0
    assert result["summary"]["total"] == result["summary"]["downloaded"] == expected
    assert len(result["filings"]) == expected
    assert _INTEGRITY_SECOND[4:].replace("-", "") not in downloader.requested
    assert _INTEGRITY_TAIL[4:].replace("-", "") not in downloader.requested
    assert len([e for e in events if e.event_type is DownloadEventType.PIPELINE_COMPLETED]) == 1


def test_sec_postrepair_clean_cancel_preserves_confirmed_repair(tmp_path: Path) -> None:
    """真实 repair clean 后取消保已发布行和 manifest，不提前发布公司。

    参数：tmp_path 为隔离根。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, _batching = _build_sec_integrity_scenario(tmp_path, "normal")
    first_locator = source.get_source_document_locator("AAPL", _INTEGRITY_FIRST, SourceKind.FILING)
    (tmp_path / first_locator / "sample-10k.htm").unlink()
    control = _SecCancelControl("postrepair")
    events: list[DownloadEvent] = []
    asyncio.run(_consume_sec_integrity_events(pipeline, events, overwrite=False, cancel_checker=control, control=control))
    result = _event_pipeline_result(events[-1])
    assert result["status"] == "cancelled"
    assert result["summary"]["total"] == result["summary"]["downloaded"] == 1
    assert [row["document_id"] for row in result["filings"]] == [_INTEGRITY_FIRST]
    assert len(source.inventories) == 2
    assert all(item.status is SourceIntegrityStatus.COMPLETE for item in source.inventories[-1])
    assert downloader.requested == [_INTEGRITY_FIRST[4:].replace("-", "")]
    assert not (tmp_path / "portfolio/AAPL/meta.json").exists()


@pytest.mark.parametrize("field", ("ticker", "document_id", "form_type", "filing_date", "report_date", "status", "filters", "overwrite"))
def test_sec_integrity_abort_snapshot_projection_rejects_invalid_fields(tmp_path: Path, field: str) -> None:
    """从真实 owner 快照破坏必填字段，原严格投影必须拒绝。

    参数：tmp_path 为隔离根；field 为被破坏字段。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, _downloader, _source, _batching = _build_sec_integrity_scenario(tmp_path, "postrepair")
    with pytest.raises(SecDownloadIntegrityAbort) as raised:
        asyncio.run(_consume_sec_integrity_events(pipeline, [], overwrite=False))
    snapshot = raised.value.result
    if field == "ticker":
        del snapshot["ticker"]
    elif field == "filters":
        snapshot["filters"] = []
    elif field == "overwrite":
        filters = snapshot["filters"]
        assert isinstance(filters, dict)
        filters["overwrite"] = "false"
    else:
        rows = snapshot["filings"]
        assert isinstance(rows, list) and isinstance(rows[0], dict)
        if field == "status":
            rows[0]["status"] = "unknown"
        else:
            del rows[0][field]
    with pytest.raises(ValueError):
        _summary_from_pipeline_result(snapshot, request=_sec_integrity_request(overwrite=False), source_repository=pipeline.source_repository)


def test_integrity_abort_causes_are_closed(tmp_path: Path) -> None:
    """所有私有中止构造均拒绝集合外异常，并原样保存三种合法 cause。

    参数：tmp_path 为隔离根。返回：无。异常：断言失败抛出 AssertionError。
    """
    from dayu.fins.pipelines.cn_download_workflow import CnDownloadIntegrityAbort
    pipeline, _downloader, _source, _batching = _build_sec_integrity_scenario(tmp_path, "postrepair")
    with pytest.raises(FinsSourceDownloadAdapterFailure) as raised:
        SecDownloadAdapter(pipeline=pipeline).download(_sec_integrity_request(overwrite=False))
    for cause in (SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSAFE_PUBLICATION),
                  SourceIntegrityRevisionConflictError(), SourceIntegrityRepairRequiredError()):
        assert SecDownloadIntegrityAbort(cause, {}).cause is cause
        assert CnDownloadIntegrityAbort(cause, {}, uncertain_reports=()).cause is cause
        assert FinsSourceDownloadAdapterFailure(cause, raised.value.persisted_summary).cause is cause
    pytest.raises(TypeError, SecDownloadIntegrityAbort, ValueError("synthetic"), {})
    pytest.raises(TypeError, CnDownloadIntegrityAbort, ValueError("synthetic"), {}, uncertain_reports=())
    pytest.raises(TypeError, FinsSourceDownloadAdapterFailure, ValueError("synthetic"), raised.value.persisted_summary)


async def _consume_sec_phase_a_unsafe(pipeline: SecPipeline, root: Path, events: list[DownloadEvent]) -> None:
    """在已开始第二文档但尚未 Phase A 分类时制造真实 unsafe。

    参数：pipeline 为真实工作流；root 为隔离根；events 为事件前缀。
    返回：无。异常：真实 typed 中止原样传播。
    """
    async for event in pipeline.download_stream(ticker="AAPL", form_type="10-K", start_date="2025-01-01",
        end_date="2025-12-31", overwrite=True, start_is_explicit=True):
        events.append(event)
        if event.event_type is DownloadEventType.FILING_STARTED and event.document_id == _INTEGRITY_SECOND:
            locator = pipeline.source_repository.get_source_document_locator("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
            (root / locator / "undeclared.bin").write_bytes(b"synthetic-phase-a-unsafe")


def test_sec_phase_a_real_preflight_keeps_confirmed_prefix(tmp_path: Path) -> None:
    """真实 Phase A UNSAFE 与 Phase B 使用同 pair catch，恰一当前失败行。

    参数：tmp_path 为隔离根。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, batching = _build_sec_integrity_scenario(tmp_path, "phase_b")
    before = source.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
    events: list[DownloadEvent] = []
    with pytest.raises(SecDownloadIntegrityAbort) as raised:
        asyncio.run(_consume_sec_phase_a_unsafe(pipeline, tmp_path, events))
    abort = raised.value
    assert isinstance(abort.cause, SourceIntegrityPreflightError)
    assert abort.cause.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION and abort.__cause__ is abort.cause
    summary = abort.result["summary"]
    assert isinstance(summary, dict) and (summary["total"], summary["downloaded"], summary["failed"]) == (2, 1, 1)
    assert len([event for event in events if event.event_type is DownloadEventType.FILING_FAILED]) == 1
    assert not any(event.event_type is DownloadEventType.PIPELINE_COMPLETED for event in events)
    assert downloader.prefetch_rounds == 0 and batching.rollback_calls == 0
    assert _INTEGRITY_SECOND[4:].replace("-", "") not in downloader.requested
    assert _INTEGRITY_TAIL[4:].replace("-", "") not in downloader.requested
    assert source.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING) == before
    assert source.classify_source_integrity("AAPL", _INTEGRITY_FIRST, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE


async def _consume_sec_registry_repair(
    pipeline: SecPipeline, registry: DownloadRejectionRegistry, events: list[DownloadEvent],
) -> None:
    """直接执行真实单文档 owner 的注册表分支，不绕过顶层预筛选。

    参数：pipeline 为真实工作流宿主；registry 为真实持久化读取；events 为事件记录。
    返回：无。异常：原完整性中止或文件操作异常原样传播。
    """
    filing = FilingRecord(
        form_type="10-K", filing_date="2025-02-02", report_date="2024-12-31",
        accession_number=_INTEGRITY_SECOND.removeprefix("fil_"), primary_document="sample-10k.htm",
    )
    async for event in pipeline._download_single_filing_stream(
        ticker="AAPL", cik="320193", filing=filing, overwrite=False, rejection_registry=registry,
    ):
        events.append(event)


def test_sec_registry_single_filing_real_preflight_preserves_published_state(tmp_path: Path) -> None:
    """真实注册表抛点保留原原因，零 batch/网络调用且不改已发布元数据与拒绝事实。

    参数：tmp_path 为隔离根。返回：无。异常：断言失败抛出 AssertionError。
    """
    pipeline, downloader, source, batching = _build_sec_integrity_scenario(tmp_path, "registry")
    before = source.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
    maintenance = FsFilingMaintenanceRepository(tmp_path)
    registry = maintenance.load_download_rejection_registry("AAPL")
    locator = source.get_source_document_locator("AAPL", _INTEGRITY_SECOND, SourceKind.FILING)
    (tmp_path / locator / "sample-10k.htm").unlink()
    events: list[DownloadEvent] = []
    with pytest.raises(SourceIntegrityPreflightError) as raised:
        asyncio.run(_consume_sec_registry_repair(pipeline, registry, events))
    assert raised.value.reason is SourceIntegrityPreflightReason.SELECTED_REJECTED_REPAIR_REQUIRED
    assert events == [] and downloader.requested == []
    assert downloader.prefetch_rounds == 0 and batching.commit_calls == 0 and batching.rollback_calls == 0
    assert source.get_source_meta("AAPL", _INTEGRITY_SECOND, SourceKind.FILING) == before
    assert maintenance.load_download_rejection_registry("AAPL") == registry
    assert source.classify_source_integrity("AAPL", _INTEGRITY_FIRST, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
