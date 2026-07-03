"""Fins ingestion runtime foundation 测试。"""

from __future__ import annotations

import io
import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock as ThreadingLock, Thread
from typing import cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins import ticker_normalization
from dayu.fins.domain.enums import SourceKind
from dayu.fins import ingestion_runtime
from dayu.fins.direct_events import (
    FinsErrorKind,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsResultStatus,
)
from dayu.fins.ingestion_events import (
    FinsIngestionJobEventAppend,
    FinsIngestionJobEventRecord,
    FinsIngestionJobEventType,
)
from dayu.fins.ingestion.wait_adapter import FinsIngestionWaitPollAdapter
from dayu.fins.ingestion.wait_adapter import FINS_INGESTION_WAIT_ADAPTER_KEY
from dayu.fins.ingestion.observation_handle import (
    FinsObservationHandle,
    FinsObservationStatus,
)
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME
from dayu.host.durable.state import (
    ExternalJobRef,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
)
from dayu.host.api import ResolveWaitFailedOutcome
from dayu.host.wait_adapter import WaitPollReady
from dayu.fins.domain.document_models import (
    CompanyMeta,
    SourceDocumentUpsertRequest,
    now_iso8601,
)
from dayu.fins.ingestion_runtime import (
    FinsDownloadedFile,
    FinsDownloadedSourceDocument,
    FinsDownloadProgressEvent,
    FinsDownloadRequest,
    FinsDownloadResultSummary,
    FinsJobCancellationChecker,
    FinsIngestionExecutor,
    FinsIngestionOperationKind,
    FinsIngestionJobStatus,
    FinsPreprocessRequest,
    FinsPreprocessResultSummary,
    FinsRejectedFilingDownloadArtifact,
    FinsSourceDownloadAdapter,
    FinsSourceDownloadAdapterRequest,
    FinsSourceDownloadAdapterResult,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadRequest,
    FinsUploadResultSummary,
    FinsUploadRunner,
)
from dayu.fins.pipelines.cn_pipeline import CnDownloadAdapter
from dayu.fins.pipelines.sec_pipeline import SecDownloadAdapter
from dayu.fins.service_runtime import DefaultFinsRuntime, ProductionFinsUploadRunner
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsSourceDocumentRepository,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import NormalizedTicker
from dayu.fins.tools.read_runtime import FinsReadRuntime


class _HoldingExecutor(FinsIngestionExecutor):
    """测试用延迟执行器。"""

    def __init__(self) -> None:
        """初始化待执行操作列表。

        Args:
            无。

        Returns:
            无。
        """

        self.operations: list[Callable[[], None]] = []

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """记录后台操作但不立即执行。

        Args:
            job_id: opaque job id。
            operation: 待执行操作。

        Returns:
            无。

        Raises:
            无。
        """

        del job_id
        self.operations.append(operation)

    def run_all(self) -> None:
        """执行全部待执行操作。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        operations = tuple(self.operations)
        self.operations.clear()
        for operation in operations:
            operation()


class _FailingSubmitExecutor(FinsIngestionExecutor):
    """测试用提交失败执行器。"""

    def __init__(self, exc: Exception) -> None:
        """初始化提交异常。

        Args:
            exc: submit 时抛出的异常。

        Returns:
            无。
        """

        self.exc = exc
        self.submitted_job_ids: tuple[str, ...] = ()

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """记录提交并抛出预设异常。

        Args:
            job_id: opaque job id。
            operation: 待执行操作。

        Returns:
            无。

        Raises:
            Exception: 始终抛出初始化传入的异常。
        """

        del operation
        self.submitted_job_ids = self.submitted_job_ids + (job_id,)
        raise self.exc


class _HookedObservationLock:
    """可控阻塞的 observation lock，用于证明 cancel/activate 共用锁。"""

    def __init__(self) -> None:
        """初始化同步事件。

        Args:
            无。

        Returns:
            无。
        """

        self._lock = ThreadingLock()
        self.first_entered = Event()
        self.allow_first_exit = Event()
        self.second_enter_attempted = Event()
        self.enter_attempts = 0

    def __enter__(self) -> "_HookedObservationLock":
        """进入锁并在第一次进入后阻塞。

        Returns:
            当前锁对象。

        Raises:
            无。
        """

        self.enter_attempts += 1
        if self.enter_attempts == 2:
            self.second_enter_attempted.set()
        self._lock.acquire()
        if self.enter_attempts == 1:
            self.first_entered.set()
            self.allow_first_exit.wait()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """释放锁。

        Args:
            exc_type: 异常类型。
            exc: 异常对象。
            traceback: traceback 对象。

        Returns:
            无。

        Raises:
            无。
        """

        del exc_type, exc, traceback
        self._lock.release()


class _FakeDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用确定性无网络下载 adapter。"""

    def __init__(self, *, include_rejected: bool = False) -> None:
        """初始化 fake adapter。

        Args:
            include_rejected: 是否返回一个 rejected filing artifact。

        Returns:
            无。
        """

        self.include_rejected = include_rejected
        self.requests: list[FinsSourceDownloadAdapterRequest] = []

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """返回确定性下载结果。

        Args:
            request: 已归一化下载请求。

        Returns:
            fake 下载结果。

        Raises:
            无。
        """

        self.requests.append(request)
        document_id = f"{request.normalized_ticker.canonical.lower()}-fake-10k"
        document = FinsDownloadedSourceDocument(
            source_kind=SourceKind.FILING,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document=f"{document_id}.md",
            meta={
                "form_type": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "amended": False,
            },
            files=(
                FinsDownloadedFile(
                    filename=f"{document_id}.md",
                    content=b"# Fake 10-K\n\nRevenue increased.",
                    content_type="text/markdown",
                    metadata={"source": request.source},
                ),
            ),
        )
        rejected_artifacts: tuple[FinsRejectedFilingDownloadArtifact, ...] = ()
        if self.include_rejected:
            rejected_artifacts = (
                FinsRejectedFilingDownloadArtifact(
                    document_id=f"{request.normalized_ticker.canonical.lower()}-fake-rejected",
                    internal_document_id="fake-rejected-internal",
                    accession_number="0000000000-24-000001",
                    company_id=f"{request.normalized_ticker.canonical}_US",
                    form_type="8-K",
                    filing_date="2024-08-01",
                    report_date=None,
                    primary_document="rejected.htm",
                    selected_primary_document="rejected.htm",
                    rejection_reason="表单类型不在请求范围内",
                    rejection_category="form_filter",
                    source_fingerprint="fake-rejected-fingerprint",
                    files=(
                        FinsDownloadedFile(
                            filename="rejected.htm",
                            content=b"<html>rejected</html>",
                            content_type="text/html",
                        ),
                    ),
                ),
            )
        return FinsSourceDownloadAdapterResult(
            discovered_count=1 + len(rejected_artifacts),
            documents=(document,),
            rejected_artifacts=rejected_artifacts,
        )


class _PersistedSummaryDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用 persisted-summary 下载 adapter。"""

    def __init__(self, summary: FinsDownloadResultSummary | None = None) -> None:
        """初始化请求记录。

        Args:
            summary: 可选的固定下载摘要；为空时使用默认 skipped 摘要。

        Returns:
            无。
        """

        self.requests: list[FinsSourceDownloadAdapterRequest] = []
        self.summary = summary or FinsDownloadResultSummary(
            discovered_count=1,
            downloaded_count=0,
            skipped_count=1,
            rejected_count=0,
            failed_count=0,
            written_document_ids=(),
        )

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """记录请求并返回已持久化摘要。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            只包含 persisted summary 的 adapter 结果。

        Raises:
            无。
        """

        self.requests.append(request)
        return FinsSourceDownloadAdapterResult(discovered_count=1, persisted_summary=self.summary)


class _ProgressReportingDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用会通过 progress sink 上报文件级进度的 adapter。"""

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """上报文件进度并返回 persisted summary。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            固定 persisted summary。

        Raises:
            无。
        """

        if request.progress_sink is not None:
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.file_started",
                    message="开始下载",
                    document_id="fil-test",
                    file_name="sample-10k.htm",
                )
            )
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.conversion_started",
                    message="开始 convert",
                    document_id="fil-test",
                    file_name="sample-10k_docling.json",
                )
            )
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.file_completed",
                    message="完成下载",
                    document_id="fil-test",
                    file_name="sample-10k.htm",
                )
            )
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=FinsDownloadResultSummary(
                discovered_count=1,
                downloaded_count=1,
                skipped_count=0,
                rejected_count=0,
                failed_count=0,
                written_document_ids=("fil-test",),
            ),
        )


class _CancellationAwareDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用会观察取消检查器的下载 adapter。"""

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """执行两次取消检查后返回 persisted summary。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            固定 persisted summary。

        Raises:
            无。
        """

        request.cancellation_checker()
        request.cancellation_checker()
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=FinsDownloadResultSummary(
                discovered_count=1,
                downloaded_count=1,
                written_document_ids=("aapl-cancel-aware-10k",),
            ),
        )


class _FakeUploadRunner(FinsUploadRunner):
    """测试用确定性上传 runner。"""

    def __init__(self, result_summary: FinsUploadResultSummary) -> None:
        """初始化 fake 上传 runner。

        Args:
            result_summary: 每次 run_upload 返回的确定性结果摘要。

        Returns:
            无。
        """

        self.result_summary = result_summary
        self.requests: list[FinsUploadRequest] = []
        self.cancellation_checks: list[bool] = []

    def run_upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """记录上传请求并返回确定性结果摘要。

        Args:
            request: runtime 传入的上传请求。
            cancellation_checker: runtime 提供的取消检查器。

        Returns:
            初始化时传入的结果摘要。

        Raises:
            OSError: 取消检查器读取 job store 失败时由检查器抛出。
            ValueError: job record 非法时由检查器抛出。
        """

        self.requests.append(request)
        self.cancellation_checks.append(cancellation_checker())
        return self.result_summary


class _BlockingArtifactUploadRunner(FinsUploadRunner):
    """写入源文档后阻塞的 observed upload runner。"""

    def __init__(
        self,
        *,
        source_repository: SourceDocumentRepositoryProtocol,
        document_id: str,
    ) -> None:
        """初始化 runner。

        Args:
            source_repository: Fins 源文档仓储协议实现。
            document_id: 测试写入的源文档 id。

        Returns:
            无。
        """

        self.source_repository = source_repository
        self.document_id = document_id
        self.artifact_written = Event()
        self.allow_finish = Event()
        self.cancellation_checks: tuple[bool, ...] = ()
        self.requests: tuple[FinsUploadRequest, ...] = ()

    def run_upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """写入源文档后等待测试释放，并记录取消检查结果。

        Args:
            request: runtime 传入的上传请求。
            cancellation_checker: runtime 提供的取消检查器。

        Returns:
            fake 上传摘要。

        Raises:
            OSError: 仓储写入或取消检查失败时抛出。
            ValueError: 源文档字段非法时抛出。
        """

        self.requests = self.requests + (request,)
        self.source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker=request.ticker,
                document_id=self.document_id,
                internal_document_id=self.document_id,
                form_type="10-K",
                primary_document=f"{self.document_id}.md",
                meta={
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "amended": False,
                    "ingest_method": "upload",
                },
            ),
            SourceKind.FILING,
        )
        self.artifact_written.set()
        self.allow_finish.wait(timeout=1.0)
        self.cancellation_checks = self.cancellation_checks + (cancellation_checker(),)
        return FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id=self.document_id,
            internal_document_id=self.document_id,
            status="uploaded",
            uploaded_files=(f"{self.document_id}.md",),
            primary_document=f"{self.document_id}.md",
        )


def _upload_runtime_converter(raw_data: bytes, stream_name: str) -> dict[str, JsonValue]:
    """runtime production upload 测试用 Docling converter。

    Args:
        raw_data: 上传文件字节。
        stream_name: 上传文件名。

    Returns:
        固定 Docling JSON 对象。

    Raises:
        无。
    """

    del raw_data
    return {"name": stream_name, "format": "docling"}


class _CancelOnSecondCheckToken(CancellationToken):
    """第二次 checkpoint 开始返回已取消的测试 token。"""

    def __init__(self) -> None:
        """初始化 checkpoint 计数。

        Args:
            无。

        Returns:
            无。
        """

        self.check_count = 0
        self._cancelled = False
        self._requested_at = datetime(2026, 6, 8, tzinfo=timezone.utc)

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        Returns:
            第一次返回 ``False``，第二次及之后返回 ``True``。
        """

        self.check_count += 1
        if self.check_count >= 2:
            self._cancelled = True
        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            取消被观察后返回测试原因，否则返回 ``None``。
        """

        if self._cancelled:
            return "host-cancelled"
        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            取消被观察后返回测试请求时间，否则返回 ``None``。
        """

        if self._cancelled:
            return self._requested_at
        return None


class _NeverCancelledToken(CancellationToken):
    """始终未取消的测试 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        Returns:
            始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            始终返回 ``None``。
        """

        return None


class _ClaimRaceJobStore:
    """测试用 job store，精确模拟 claim-running 窗口中的取消请求。"""

    def __init__(self) -> None:
        """初始化空 job store。

        Args:
            无。

        Returns:
            无。
        """

        self._record: ingestion_runtime.FinsIngestionJobRecord | None = None
        self._events: list[FinsIngestionJobEventRecord] = []
        self.read_race_triggered = False
        self.claim_race_triggered = False
        self.claim_running_calls = 0
        self.save_job_calls = 0

    def create_job(
        self,
        record: ingestion_runtime.FinsIngestionJobRecord,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """创建测试 job record。

        Args:
            record: 待创建的 job record。

        Returns:
            已保存的 job record。

        Raises:
            FileExistsError: job 已存在时抛出。
        """

        if self._record is not None:
            raise FileExistsError(f"Fins ingestion job 已存在: {record.job_id}")
        self._record = record
        return record

    def save_job(
        self,
        record: ingestion_runtime.FinsIngestionJobRecord,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """保存完整测试 job record。

        Args:
            record: 待保存的 job record。

        Returns:
            已保存的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self._require_record(record.job_id)
        self.save_job_calls += 1
        self._record = record
        return record

    def save_succeeded_or_cancelled(
        self,
        job_id: str,
        *,
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """按当前取消状态保存 succeeded 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            result_summary: succeeded 终态结果摘要。
            finished_at: 终态写入时间。

        Returns:
            已保存的终态 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=finished_at,
                finished_at=finished_at,
                cancellation_requested=True,
            )
            self._record = cancelled
            return cancelled
        succeeded = replace(
            record,
            status=FinsIngestionJobStatus.SUCCEEDED,
            updated_at=finished_at,
            finished_at=finished_at,
            result_summary=result_summary,
            failure_summary={},
        )
        self._record = succeeded
        return succeeded

    def save_cancelled_if_active(
        self,
        job_id: str,
        *,
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """仅当当前测试 job 非终态时保存 cancelled 终态。

        Args:
            job_id: opaque job id。
            finished_at: 终态写入时间。

        Returns:
            已保存的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        cancelled = replace(
            record,
            status=FinsIngestionJobStatus.CANCELLED,
            updated_at=finished_at,
            finished_at=finished_at,
            cancellation_requested=True,
        )
        self._record = cancelled
        return cancelled

    def save_failed_or_cancelled_if_active(
        self,
        job_id: str,
        *,
        failure_summary: dict[str, JsonValue],
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """按当前测试 job 状态保存 failed 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            failure_summary: failed 终态失败摘要。
            result_summary: failed 终态结果摘要。
            finished_at: 终态写入时间。

        Returns:
            已保存的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=finished_at,
                finished_at=finished_at,
                cancellation_requested=True,
            )
            self._record = cancelled
            return cancelled
        failed = replace(
            record,
            status=FinsIngestionJobStatus.FAILED,
            updated_at=finished_at,
            finished_at=finished_at,
            failure_summary=failure_summary,
            result_summary=result_summary,
        )
        self._record = failed
        return failed

    def claim_running_or_cancelled(
        self,
        job_id: str,
        *,
        started_at: str,
        updated_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """在一次测试 claim 内模拟 queued 读取后收到取消请求。

        Args:
            job_id: opaque job id。
            started_at: running 开始时间。
            updated_at: 本次状态更新时间。

        Returns:
            claim 后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self.claim_running_calls += 1
        record = self._require_record(job_id)
        if not self.claim_race_triggered and record.status is FinsIngestionJobStatus.QUEUED:
            self.claim_race_triggered = True
            self.request_cancel(job_id, updated_at=updated_at)
            record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=updated_at,
                finished_at=updated_at,
                cancellation_requested=True,
            )
            self._record = cancelled
            return cancelled
        running = replace(
            record,
            status=FinsIngestionJobStatus.RUNNING,
            started_at=record.started_at or started_at,
            updated_at=updated_at,
        )
        self._record = running
        return running

    def read_job(self, job_id: str) -> ingestion_runtime.FinsIngestionJobRecord:
        """读取测试 job record，并模拟旧 read/save 窗口中的取消。

        Args:
            job_id: opaque job id。

        Returns:
            当前或刻意滞后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if not self.read_race_triggered and record.status is FinsIngestionJobStatus.QUEUED:
            self.read_race_triggered = True
            self.request_cancel(job_id, updated_at=record.updated_at)
            return record
        return record

    def request_cancel(
        self,
        job_id: str,
        *,
        updated_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """标记测试 job 取消请求。

        Args:
            job_id: opaque job id。
            updated_at: 本次状态更新时间。

        Returns:
            更新后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        updated = replace(
            record,
            status=FinsIngestionJobStatus.CANCELLING,
            updated_at=updated_at,
            cancellation_requested=True,
        )
        self._record = updated
        return updated

    def append_job_event(
        self,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """追加测试 job event。

        Args:
            job_id: opaque job id。
            event: 无 sequence 的事件追加输入。

        Returns:
            已追加且带 sequence 的事件。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self._require_record(job_id)
        record = FinsIngestionJobEventRecord(
            job_id=job_id,
            sequence=len(self._events) + 1,
            operation_kind=event.operation_kind,
            status=event.status,
            event_type=event.event_type,
            source_event_type=event.source_event_type,
            source_kind=event.source_kind,
            document_id=event.document_id,
            message=event.message,
            payload=event.payload,
            emitted_at=event.emitted_at,
        )
        self._events.append(record)
        return record

    def read_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[FinsIngestionJobEventRecord, ...]:
        """读取测试 job events。

        Args:
            job_id: opaque job id。
            after_sequence: 只返回 sequence 大于该值的事件。
            limit: 本次最多返回事件数量。

        Returns:
            满足游标条件的事件元组。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self._require_record(job_id)
        return tuple(event for event in self._events if event.sequence > after_sequence)[:limit]

    def _require_record(self, job_id: str) -> ingestion_runtime.FinsIngestionJobRecord:
        """读取并校验当前测试 job record。

        Args:
            job_id: opaque job id。

        Returns:
            当前 job record。

        Raises:
            FileNotFoundError: 当前没有匹配 job 时抛出。
        """

        record = self._record
        if record is None or record.job_id != job_id:
            raise FileNotFoundError(f"Fins ingestion job 不存在: {job_id}")
        return record


def test_default_runtime_instances_share_workspace_job_store_without_singleton(tmp_path: Path) -> None:
    """同一 workspace 的两个 runtime 实例应共享持久化 store 而非 Python singleton。"""

    workspace_root = tmp_path / "fins-workspace"
    first_executor = _HoldingExecutor()
    second_executor = _HoldingExecutor()
    first_ingestion = _build_ingestion_runtime(workspace_root, executor=first_executor)
    second_ingestion = _build_ingestion_runtime(workspace_root, executor=second_executor)

    start = first_ingestion.start_download(
        FinsDownloadRequest(
            ticker="AAPL",
            source="sec",
            form_types=("10-K",),
        )
    )
    job_file = _job_file(workspace_root, start.job_id)
    cross_instance_record = second_ingestion.read_job(start.job_id)

    assert first_ingestion is not second_ingestion
    assert job_file.is_file()
    assert cross_instance_record == start.record
    assert cross_instance_record.status is FinsIngestionJobStatus.QUEUED
    assert len(first_executor.operations) == 1


def test_start_download_persists_queued_record_and_uses_public_ticker_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下载启动应通过 ticker_normalization 并先持久化 queued record。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    original_normalize = ticker_normalization.normalize_ticker
    calls: list[str] = []

    def normalize_spy(raw: str) -> NormalizedTicker:
        """记录归一化调用并委托公共实现。

        Args:
            raw: 原始 ticker。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 非法时由公共实现抛出。
        """

        calls.append(raw)
        return original_normalize(raw)

    monkeypatch.setattr(ticker_normalization, "normalize_ticker", normalize_spy)

    start = runtime.start_download(
        FinsDownloadRequest(
            ticker="aapl.us",
            source="sec",
            form_types=("10-K", "10-Q"),
            filed_after="2024-01-01",
            filed_before="2024-12-31",
            overwrite_existing=True,
        )
    )
    record = runtime.read_job(start.job_id)

    assert calls == ["aapl.us"]
    assert start.status is FinsIngestionJobStatus.QUEUED
    assert record.normalized_ticker == "AAPL"
    assert record.market == "US"
    assert record.source == "sec"
    assert record.source_kind is None
    assert record.request_summary["form_types"] == ["10-K", "10-Q"]
    assert record.request_summary["overwrite_existing"] is True
    assert record.result_summary == {}
    assert record.failure_summary == {}
    assert not record.cancellation_requested
    assert len(executor.operations) == 1


def test_start_download_allows_sec_amended_form_type(tmp_path: Path) -> None:
    """下载请求应允许 SEC 修正表单类型中的业务合法斜杠。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    start = runtime.start_download(FinsDownloadRequest(ticker="AAPL", form_types=("10-K/A",)))
    record = runtime.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.QUEUED
    assert record.request_summary["form_types"] == ["10-K/A"]


def test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit(
    tmp_path: Path,
) -> None:
    """下载 start 在 create 后、submit 前观察到取消时应标记 job 且不提交后台操作。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    token = _CancelOnSecondCheckToken()

    start = runtime.start_download(FinsDownloadRequest(ticker="AAPL"), cancellation_token=token)
    record = runtime.read_job(start.job_id)

    assert start.status is FinsIngestionJobStatus.CANCELLED
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert executor.operations == []


def test_start_download_still_rejects_path_separator_in_source(tmp_path: Path) -> None:
    """下载来源标识仍应拒绝路径分隔符，避免 source-like 字段被当作路径片段。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    with pytest.raises(ValueError, match="source 不得包含路径分隔符"):
        runtime.start_download(FinsDownloadRequest(ticker="AAPL", source="../sec"))


def test_start_download_fake_adapter_writes_source_document_through_storage(tmp_path: Path) -> None:
    """fake 下载 adapter 应通过 source/blob 仓储写入源文档。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="FAKE", form_types=("10-K",)))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    source_meta = runtime.source_repository.get_source_meta("AAPL", "aapl-fake-10k", SourceKind.FILING)
    handle = runtime.source_repository.get_source_handle("AAPL", "aapl-fake-10k", SourceKind.FILING)
    content = runtime.blob_repository.read_file_bytes(handle, "aapl-fake-10k.md")

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["discovered_count"] == 1
    assert record.result_summary["downloaded_count"] == 1
    assert record.result_summary["skipped_count"] == 0
    assert record.result_summary["rejected_count"] == 0
    assert record.result_summary["failed_count"] == 0
    assert record.result_summary["written_document_ids"] == ["aapl-fake-10k"]
    assert source_meta["ingest_method"] == "download"
    assert content == b"# Fake 10-K\n\nRevenue increased."
    assert adapter.requests[0].normalized_ticker.canonical == "AAPL"
    assert adapter.requests[0].normalized_ticker.market == "US"
    assert [event.source_event_type for event in progress_events] == [
        "download.started",
        "download.completed",
    ]
    assert progress_events[0].payload["ticker"] == "AAPL"
    assert progress_events[0].payload["source"] == "fake"
    assert progress_events[0].payload["form_types"] == ["10-K"]
    assert progress_events[1].payload["downloaded_count"] == 1
    assert progress_events[1].payload["written_document_count"] == 1


@pytest.mark.asyncio
async def test_direct_download_stream_writes_storage_and_does_not_create_job_record(
    tmp_path: Path,
) -> None:
    """direct download 应产出 progress/result，并且不创建 durable job record。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )

    events = await _collect_direct_events(
        ingestion.download(FinsDownloadRequest(ticker="AAPL", source="FAKE", form_types=("10-K",)))
    )
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    source_meta = runtime.source_repository.get_source_meta("AAPL", "aapl-fake-10k", SourceKind.FILING)
    handle = runtime.source_repository.get_source_handle("AAPL", "aapl-fake-10k", SourceKind.FILING)
    content = runtime.blob_repository.read_file_bytes(handle, "aapl-fake-10k.md")
    jobs_dir = workspace_root / ".dayu" / "fins_ingestion" / "jobs"

    assert executor.operations == []
    assert [event.event_type for event in events].count(FinsEventType.RESULT) == 1
    assert events[0].event_type is FinsEventType.PROGRESS
    assert events[-1].event_type is FinsEventType.RESULT
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.SUCCESS
    assert events[-1].result.exit_code == 0
    assert source_meta["ingest_method"] == "download"
    assert content == b"# Fake 10-K\n\nRevenue increased."
    assert tuple(jobs_dir.glob("*.json")) == ()
    assert tuple(jobs_dir.glob("*.jsonl")) == ()


@pytest.mark.asyncio
async def test_direct_download_projects_adapter_file_progress_events(
    tmp_path: Path,
) -> None:
    """direct download 应投影 adapter 上报的文件级下载进度。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _ProgressReportingDownloadAdapter()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        download_adapters={("fake", "US"): adapter},
    )

    events = await _collect_direct_events(
        ingestion.download(FinsDownloadRequest(ticker="AAPL", source="FAKE"))
    )
    progress_events = [event for event in events if event.event_type is FinsEventType.PROGRESS]
    file_progress = [
        event
        for event in progress_events
        if event.progress is not None and event.progress.stage.startswith("download.file")
    ]
    conversion_progress = [
        event
        for event in progress_events
        if event.progress is not None and event.progress.stage == "download.conversion_started"
    ]

    file_progress_details: list[tuple[str, str | None, str]] = []
    for event in file_progress:
        assert event.progress is not None
        file_progress_details.append((event.progress.stage, event.document_label, event.message))
    assert file_progress_details == [
        ("download.file_started", "sample-10k.htm", "开始下载"),
        ("download.file_completed", "sample-10k.htm", "完成下载"),
    ]
    assert [(event.document_label, event.message) for event in conversion_progress] == [
        ("sample-10k_docling.json", "开始 convert"),
    ]


@pytest.mark.asyncio
async def test_direct_download_result_details_do_not_double_display_rejected_skips(
    tmp_path: Path,
) -> None:
    """direct download summary 展示应避免 skipped/rejected 重复表达同一批拒绝项。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _PersistedSummaryDownloadAdapter(
        FinsDownloadResultSummary(
            discovered_count=17,
            downloaded_count=15,
            skipped_count=2,
            rejected_count=2,
            failed_count=0,
            written_document_ids=tuple(f"fil-{index}" for index in range(15)),
        )
    )
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        download_adapters={("fake", "US"): adapter},
    )

    events = await _collect_direct_events(
        ingestion.download(FinsDownloadRequest(ticker="FUTU", source="FAKE"))
    )
    result_event = events[-1]

    assert result_event.result is not None
    assert {detail.label: detail.value for detail in result_event.result.details} == {
        "discovered": "17",
        "downloaded": "15",
        "skipped": "0",
        "rejected": "2",
        "failed": "0",
        "written documents": "15",
    }


@pytest.mark.asyncio
async def test_direct_download_unsupported_source_returns_failure_result(tmp_path: Path) -> None:
    """direct download adapter 失败应收口为 FAILURE RESULT，不得静默结束。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    events = await _collect_direct_events(
        ingestion.download(FinsDownloadRequest(ticker="AAPL", source="unknown"))
    )

    assert events[0].event_type is FinsEventType.PROGRESS
    assert events[-1].event_type is FinsEventType.RESULT
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.FAILURE
    assert events[-1].result.exit_code == 1
    assert events[-1].result.error_message is not None
    assert "不支持的下载来源" in events[-1].result.error_message


@pytest.mark.asyncio
async def test_direct_stream_missing_result_returns_failure_result(tmp_path: Path) -> None:
    """direct producer 静默结束时 runtime 自身应补齐失败 RESULT。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    normalized = ticker_normalization.normalize_ticker("AAPL")

    def quiet_producer(context: ingestion_runtime._FinsIngestionExecutionContext) -> None:
        """模拟未产出 RESULT 的 producer。

        Args:
            context: direct stream 执行上下文。

        Returns:
            无。

        Raises:
            无。
        """

        del context

    events = await _collect_direct_events(
        ingestion._run_direct_stream(
            operation_kind=FinsIngestionOperationKind.DOWNLOAD,
            direct_operation_kind=FinsOperationKind.DOWNLOAD,
            normalized=normalized,
            source="fake",
            source_kind=SourceKind.FILING,
            cancellation_token=None,
            producer=quiet_producer,
        )
    )

    assert [event.event_type for event in events] == [FinsEventType.RESULT]
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.FAILURE
    assert events[-1].result.exit_code == 1


@pytest.mark.asyncio
async def test_direct_download_uses_operation_scoped_cancellation_token(tmp_path: Path) -> None:
    """direct download 取消应使用 operation-scoped token/checker 并返回 cancelled RESULT。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("cancel", "US"): _CancellationAwareDownloadAdapter()},
    )
    token = _CancelOnSecondCheckToken()

    events = await _collect_direct_events(
        ingestion.download(
            FinsDownloadRequest(ticker="AAPL", source="cancel"),
            cancellation_token=token,
        )
    )

    assert executor.operations == []
    assert token.check_count >= 2
    assert events[-1].event_type is FinsEventType.RESULT
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.CANCELLED
    assert events[-1].result.exit_code == 130


def test_start_download_production_adapter_boundary_emits_progress_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production 下载 adapter 同步调用边界应产生 started/completed PROGRESS event。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    def fake_sec_download(
        adapter: SecDownloadAdapter,
        request: FinsSourceDownloadAdapterRequest,
    ) -> FinsSourceDownloadAdapterResult:
        """替换 production SEC adapter 的网络下载，只保留同步调用边界。

        Args:
            adapter: 被替换的 SEC adapter 实例。
            request: runtime 传入的下载请求。

        Returns:
            有界 persisted summary。

        Raises:
            无。
        """

        del adapter
        assert request.source == "sec"
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=FinsDownloadResultSummary(
                discovered_count=1,
                downloaded_count=1,
                written_document_ids=("aapl-production-10k",),
            ),
        )

    monkeypatch.setattr(SecDownloadAdapter, "download", fake_sec_download)

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="sec"))
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert [event.source_event_type for event in progress_events] == [
        "download.started",
        "download.completed",
    ]
    assert progress_events[0].payload["ticker"] == "AAPL"
    assert progress_events[0].payload["source"] == "sec"
    assert progress_events[1].payload["downloaded_count"] == 1
    assert progress_events[1].payload["written_document_count"] == 1


def test_start_download_failed_count_emits_completed_with_failures_progress(tmp_path: Path) -> None:
    """下载摘要含失败计数时应产生 completed_with_failures progress。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _PersistedSummaryDownloadAdapter(
        FinsDownloadResultSummary(
            discovered_count=2,
            downloaded_count=1,
            skipped_count=0,
            rejected_count=0,
            failed_count=1,
            written_document_ids=("aapl-partial-10k",),
        )
    )
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("persisted", "US"): adapter},
    )

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="persisted"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert [event.source_event_type for event in progress_events] == [
        "download.started",
        "download.completed_with_failures",
    ]
    assert progress_events[1].message == "下载已完成，存在失败候选"
    assert progress_events[1].payload["failed_count"] == 1
    assert progress_events[1].payload["downloaded_count"] == 1


def test_start_download_unsupported_source_writes_failed_terminal_record(tmp_path: Path) -> None:
    """无 adapter 的 market/source 应返回明确 unsupported-source 失败。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="unknown"))
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["failed_count"] == 1
    assert "不支持的下载来源" in str(record.failure_summary["message"])
    assert "source=unknown" in str(record.failure_summary["message"])
    assert "market=US" in str(record.failure_summary["message"])


def test_default_runtime_registers_production_download_adapters(tmp_path: Path) -> None:
    """默认 runtime 应为 US/CN/HK 装配确定性的 production download adapter。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    sec_adapter = ingestion.download_adapters[("sec", "US")]
    auto_adapter = ingestion.download_adapters[("auto", "US")]
    cn_adapter = ingestion.download_adapters[("cninfo", "CN")]
    auto_cn_adapter = ingestion.download_adapters[("auto", "CN")]
    hk_adapter = ingestion.download_adapters[("hkexnews", "HK")]
    auto_hk_adapter = ingestion.download_adapters[("auto", "HK")]

    assert isinstance(sec_adapter, SecDownloadAdapter)
    assert auto_adapter is sec_adapter
    assert isinstance(cn_adapter, CnDownloadAdapter)
    assert auto_cn_adapter is cn_adapter
    assert isinstance(hk_adapter, CnDownloadAdapter)
    assert auto_hk_adapter is hk_adapter


def test_start_download_repeated_request_skips_existing_source_document(tmp_path: Path) -> None:
    """重复语义请求应由 runtime storage 语义确定性跳过已有源文档。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )

    first = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    executor.run_all()
    first_record = ingestion.read_job(first.job_id)
    second = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    executor.run_all()
    second_record = ingestion.read_job(second.job_id)

    assert first_record.status is FinsIngestionJobStatus.SUCCEEDED
    assert first_record.result_summary["downloaded_count"] == 1
    assert second_record.status is FinsIngestionJobStatus.SUCCEEDED
    assert second_record.result_summary["downloaded_count"] == 0
    assert second_record.result_summary["skipped_count"] == 1
    assert second_record.result_summary["written_document_ids"] == []


def test_start_download_persists_rejected_filing_artifact(tmp_path: Path) -> None:
    """adapter 返回 rejected filing 时应通过 filing maintenance 仓储保存。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter(include_rejected=True)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    artifacts = runtime.filing_maintenance_repository.list_rejected_filing_artifacts("AAPL")
    content = runtime.filing_maintenance_repository.read_rejected_filing_file_bytes(
        "AAPL",
        "aapl-fake-rejected",
        "rejected.htm",
    )

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["discovered_count"] == 2
    assert record.result_summary["downloaded_count"] == 1
    assert record.result_summary["rejected_count"] == 1
    assert len(artifacts) == 1
    assert artifacts[0].document_id == "aapl-fake-rejected"
    assert artifacts[0].rejection_category == "form_filter"
    assert content == b"<html>rejected</html>"


def test_start_download_persisted_summary_adapter_receives_rebuild_processed(tmp_path: Path) -> None:
    """persisted-summary adapter 应接收 NEW rebuild_processed 治理标记并记录请求。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _PersistedSummaryDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("persisted", "US"): adapter},
    )

    start = ingestion.start_download(
        FinsDownloadRequest(
            ticker="AAPL",
            source="persisted",
            rebuild_processed=True,
        )
    )
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.request_summary["rebuild_processed"] is True
    assert record.result_summary["skipped_count"] == 1
    assert len(adapter.requests) == 1
    assert adapter.requests[0].rebuild_processed is True


def test_start_preprocess_persists_queued_record_and_uses_public_ticker_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预处理启动应通过 ticker_normalization 并先持久化 queued record。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    original_normalize = ticker_normalization.normalize_ticker
    calls: list[str] = []

    def normalize_spy(raw: str) -> NormalizedTicker:
        """记录归一化调用并委托公共实现。

        Args:
            raw: 原始 ticker。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 非法时由公共实现抛出。
        """

        calls.append(raw)
        return original_normalize(raw)

    monkeypatch.setattr(ticker_normalization, "normalize_ticker", normalize_spy)

    start = runtime.start_preprocess(
        FinsPreprocessRequest(
            ticker="HK.00700",
            source_kind=SourceKind.FILING,
            document_ids=("tencent-2024-annual",),
            form_types=("annual",),
            rebuild_processed=True,
        )
    )
    record = runtime.read_job(start.job_id)

    assert calls == ["HK.00700"]
    assert record.status is FinsIngestionJobStatus.QUEUED
    assert len(executor.operations) == 1
    assert record.normalized_ticker == "0700"
    assert record.market == "HK"
    assert record.exchange == "HKEX"
    assert record.source is None
    assert record.source_kind is SourceKind.FILING
    assert record.request_summary["document_ids"] == ["tencent-2024-annual"]
    assert record.request_summary["rebuild_processed"] is True


def test_start_preprocess_allows_slash_in_document_ids(tmp_path: Path) -> None:
    """预处理请求应允许 document_id 中的业务合法斜杠。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    start = runtime.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("sec/aapl-2024-10ka",),
            form_types=("10-K/A",),
        )
    )
    record = runtime.read_job(start.job_id)

    assert record.request_summary["document_ids"] == ["sec/aapl-2024-10ka"]
    assert record.request_summary["form_types"] == ["10-K/A"]


def test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit(
    tmp_path: Path,
) -> None:
    """预处理 start 在 create 后、submit 前观察到取消时应标记 job 且不提交后台操作。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    token = _CancelOnSecondCheckToken()

    start = runtime.start_preprocess(FinsPreprocessRequest(ticker="AAPL"), cancellation_token=token)
    record = runtime.read_job(start.job_id)

    assert start.status is FinsIngestionJobStatus.CANCELLED
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert executor.operations == []


def test_start_upload_persists_queued_record_and_uses_public_ticker_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传启动应通过 ticker_normalization 并先持久化 queued record。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="uploaded",
        )
    )
    runtime = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)
    original_normalize = ticker_normalization.normalize_ticker
    calls: list[str] = []

    def normalize_upload_ticker(raw: str) -> NormalizedTicker:
        """记录归一化调用并委托公共实现。

        Args:
            raw: 原始 ticker。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 非法时由公共实现抛出。
        """

        calls.append(raw)
        return original_normalize(raw)

    monkeypatch.setattr(ticker_normalization, "normalize_ticker", normalize_upload_ticker)

    start = runtime.start_upload(
        FinsUploadFilingRequest(
            ticker="aapl.us",
            action="CREATE",
            files=(tmp_path / "aapl-10k.pdf",),
            fiscal_year=2024,
            fiscal_period="FY",
            amended=True,
            filing_date="2024-11-01",
            report_date="2024-09-28",
            company_name="Apple Inc.",
            ticker_aliases=("APPLE",),
        )
    )
    record = runtime.read_job(start.job_id)
    payload_text = _job_file(workspace_root, start.job_id).read_text(encoding="utf-8")

    assert calls == ["aapl.us"]
    assert start.status is FinsIngestionJobStatus.QUEUED
    assert record.operation_kind is FinsIngestionOperationKind.UPLOAD
    assert record.normalized_ticker == "AAPL"
    assert record.market == "US"
    assert record.source is None
    assert record.source_kind is SourceKind.FILING
    assert record.request_summary["source_kind"] == "filing"
    assert record.request_summary["action"] == "create"
    assert record.request_summary["file_count"] == 1
    assert record.request_summary["fiscal_year"] == 2024
    assert record.request_summary["amended"] is True
    assert record.request_summary["ticker_aliases"] == ["APPLE"]
    assert str(tmp_path) not in payload_text
    assert "aapl-10k.pdf" not in payload_text
    assert len(executor.operations) == 1
    assert runner.requests == []


def test_upload_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit(
    tmp_path: Path,
) -> None:
    """上传 start 在 create 后、submit 前观察到取消时应标记 job 且不提交后台操作。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    token = _CancelOnSecondCheckToken()

    start = runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL"), cancellation_token=token)
    record = runtime.read_job(start.job_id)

    assert start.status is FinsIngestionJobStatus.CANCELLED
    assert record.operation_kind is FinsIngestionOperationKind.UPLOAD
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert executor.operations == []


def test_start_upload_without_runner_writes_failed_terminal_record(tmp_path: Path) -> None:
    """未装配 upload runner 时应写入明确 unsupported upload runtime 失败终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            action="delete",
            document_id="aapl-investor-day",
            material_name="Investor Day",
        )
    )
    executor.run_all()
    record = runtime.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.operation_kind is FinsIngestionOperationKind.UPLOAD
    assert record.source_kind is SourceKind.MATERIAL
    assert record.result_summary["source_kind"] == "material"
    assert record.result_summary["status"] == "failed"
    assert record.result_summary["uploaded_files"] == []
    assert "unsupported upload runtime" in str(record.failure_summary["message"])
    assert "production upload runner" in str(record.failure_summary["message"])


def test_start_upload_with_runner_writes_bounded_result_summary(tmp_path: Path) -> None:
    """上传 runner 结果应按有界 JSON 摘要写入 succeeded 终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.MATERIAL,
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
            status="uploaded",
            uploaded_files=("primary.pdf",),
            primary_document="primary.pdf",
            deleted=False,
            skip_reason=None,
            document_version="v2",
            source_fingerprint="sha256:abc123",
        )
    )
    runtime = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)

    start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            action="auto",
            files=(tmp_path / "primary.pdf",),
            form_type="8-K",
            material_name="Investor Day",
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
        )
    )
    executor.run_all()
    record = runtime.read_job(start.job_id)
    progress_events = _progress_events(runtime, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["source_kind"] == "material"
    assert record.result_summary["document_id"] == "aapl-investor-day"
    assert record.result_summary["internal_document_id"] == "aapl-investor-day-internal"
    assert record.result_summary["status"] == "uploaded"
    assert record.result_summary["uploaded_files"] == ["primary.pdf"]
    assert record.result_summary["primary_document"] == "primary.pdf"
    assert record.result_summary["deleted"] is False
    assert record.result_summary["document_version"] == "v2"
    assert record.result_summary["source_fingerprint"] == "sha256:abc123"
    assert len(runner.requests) == 1
    assert isinstance(runner.requests[0], FinsUploadMaterialRequest)
    assert runner.requests[0].action == "auto"
    assert runner.cancellation_checks == [False]
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed",
    ]
    assert progress_events[0].document_id == "aapl-investor-day"
    assert progress_events[0].payload["source_kind"] == "material"
    assert progress_events[0].payload["file_count"] == 1
    assert progress_events[1].document_id == "aapl-investor-day"
    assert progress_events[1].payload["upload_status"] == "uploaded"


@pytest.mark.asyncio
async def test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text(tmp_path: Path) -> None:
    """direct upload 用户事件不得暴露路径、job id、raw payload 或正文。"""

    workspace_root = tmp_path / "fins-workspace"
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="uploaded",
            uploaded_files=("primary.pdf",),
            primary_document="primary.pdf",
        )
    )
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        upload_runner=runner,
    )
    upload_file = tmp_path / "raw" / "aapl-10k.pdf"
    upload_file.parent.mkdir(parents=True)
    upload_file.write_text("Annual recurring revenue increased raw provider payload", encoding="utf-8")

    events = await _collect_direct_events(
        ingestion.upload(FinsUploadFilingRequest(ticker="AAPL", files=(upload_file,)))
    )
    event_text = repr(events)

    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.SUCCESS
    assert str(tmp_path) not in event_text
    assert "aapl-10k.pdf" not in event_text
    assert "finsjob_" not in event_text
    assert "raw provider payload" not in event_text
    assert "Annual recurring revenue increased" not in event_text


def test_start_upload_failed_status_emits_completed_with_failures_progress(tmp_path: Path) -> None:
    """上传摘要为 failed 状态时应产生 completed_with_failures progress。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.MATERIAL,
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
            status="failed",
            uploaded_files=(),
            primary_document=None,
            deleted=False,
            skip_reason="fixture failure",
            document_version=None,
            source_fingerprint=None,
        )
    )
    runtime = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)

    start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            action="auto",
            files=(tmp_path / "primary.pdf",),
            form_type="8-K",
            material_name="Investor Day",
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
        )
    )
    executor.run_all()
    record = runtime.read_job(start.job_id)
    progress_events = _progress_events(runtime, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["status"] == "failed"
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed_with_failures",
    ]
    assert progress_events[1].message == "上传已完成，存在失败"
    assert progress_events[1].document_id == "aapl-investor-day"
    assert progress_events[1].payload["upload_status"] == "failed"


def test_default_runtime_start_upload_sec_filing_uses_production_runner(tmp_path: Path) -> None:
    """DefaultFinsRuntime 应装配 production runner 并执行 SEC filing 上传。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    upload_runner = ingestion.upload_runner
    assert isinstance(upload_runner, ProductionFinsUploadRunner)
    upload_runner.sec_pipeline._upload_service._convert_with_docling = _upload_runtime_converter
    filing_file = tmp_path / "aapl-10q.pdf"
    filing_file.write_text("runtime sec filing", encoding="utf-8")

    start = ingestion.start_upload(
        FinsUploadFilingRequest(
            ticker="AAPL",
            action="create",
            files=(filing_file,),
            fiscal_year=2025,
            fiscal_period="Q1",
            filing_date="2025-05-01",
            report_date="2025-03-31",
            company_name="Apple Inc.",
            overwrite=False,
        )
    )
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["source_kind"] == "filing"
    assert record.result_summary["status"] == "ok"
    assert record.result_summary["primary_document"] == "aapl-10q_docling.json"
    document_id = str(record.result_summary["document_id"])
    meta = ingestion.source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    assert meta["ingest_method"] == "upload"
    assert meta["primary_document"] == "aapl-10q_docling.json"
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed",
    ]
    assert progress_events[0].payload["source_kind"] == "filing"
    assert progress_events[0].payload["file_count"] == 1
    assert progress_events[1].payload["upload_status"] == "ok"


def test_default_runtime_start_upload_cn_material_uses_production_runner(tmp_path: Path) -> None:
    """DefaultFinsRuntime 应装配 production runner 并执行 CN material 上传。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    upload_runner = ingestion.upload_runner
    assert isinstance(upload_runner, ProductionFinsUploadRunner)
    upload_runner.cn_pipeline._upload_service._convert_with_docling = _upload_runtime_converter
    material_file = tmp_path / "deck.pdf"
    material_file.write_text("runtime cn material", encoding="utf-8")

    start = ingestion.start_upload(
        FinsUploadMaterialRequest(
            ticker="600519",
            action="create",
            files=(material_file,),
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            company_name="贵州茅台",
            overwrite=False,
        )
    )
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.market == "CN"
    assert record.result_summary["source_kind"] == "material"
    assert record.result_summary["status"] == "ok"
    assert record.result_summary["primary_document"] == "deck_docling.json"
    document_id = str(record.result_summary["document_id"])
    meta = ingestion.source_repository.get_source_meta("600519", document_id, SourceKind.MATERIAL)
    assert meta["material_name"] == "Deck"
    assert meta["primary_document"] == "deck_docling.json"


def test_upload_request_and_result_summaries_enforce_bounds(tmp_path: Path) -> None:
    """上传请求与结果摘要应执行数量和长度边界。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    too_many_aliases = tuple(f"alias-{index}" for index in range(ingestion_runtime._MAX_TUPLE_ITEMS + 1))
    too_many_files = tuple(f"file-{index}.pdf" for index in range(ingestion_runtime._MAX_TUPLE_ITEMS + 1))

    with pytest.raises(ValueError, match="ticker_aliases 元素数量超出上限"):
        runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL", ticker_aliases=too_many_aliases))
    with pytest.raises(ValueError, match="uploaded_files 元素数量超出上限"):
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="uploaded",
            uploaded_files=too_many_files,
        ).to_json_summary()
    assert executor.operations == []


def test_upload_requests_use_source_kind_for_filing_material_discrimination(tmp_path: Path) -> None:
    """上传请求应使用 SourceKind 区分 filing/material，错误组合在建 job 前失败。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    with pytest.raises(ValueError, match="filing 上传请求必须使用 source_kind=filing"):
        runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL", source_kind=SourceKind.MATERIAL))
    with pytest.raises(ValueError, match="material 上传请求必须使用 source_kind=material"):
        runtime.start_upload(FinsUploadMaterialRequest(ticker="AAPL", source_kind=SourceKind.FILING))

    material_start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            document_id="aapl-investor-day",
        )
    )
    material_record = runtime.read_job(material_start.job_id)

    assert material_record.source_kind is SourceKind.MATERIAL
    assert material_record.request_summary["source_kind"] == "material"
    assert material_record.request_summary["document_id"] == "aapl-investor-day"
    assert len(executor.operations) == 1


def test_result_summaries_allow_slash_in_document_ids() -> None:
    """结果摘要中的 document-id 类字段应允许业务合法斜杠。"""

    download_summary = FinsDownloadResultSummary(written_document_ids=("sec/aapl-2024-10ka",))
    preprocess_summary = FinsPreprocessResultSummary(processed_document_ids=("processed/aapl-2024-10ka",))
    upload_summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        document_id="sec/aapl-2024-10ka",
        internal_document_id="sec/aapl-2024-10ka-internal",
    )

    assert download_summary.to_json_summary()["written_document_ids"] == ["sec/aapl-2024-10ka"]
    assert preprocess_summary.to_json_summary()["processed_document_ids"] == ["processed/aapl-2024-10ka"]
    assert upload_summary.to_json_summary()["document_id"] == "sec/aapl-2024-10ka"
    assert upload_summary.to_json_summary()["internal_document_id"] == "sec/aapl-2024-10ka-internal"


def test_prepare_observed_operations_do_not_submit_until_activation(tmp_path: Path) -> None:
    """download/preprocess/upload prepare 只登记 observation，activation 才提交。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    download = runtime.prepare_observed_download(
        FinsDownloadRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )
    preprocess = runtime.prepare_observed_preprocess(
        FinsPreprocessRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )
    upload = runtime.prepare_observed_upload(
        FinsUploadFilingRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    assert executor.operations == []

    runtime.activate_observation(download)
    runtime.activate_observation(preprocess)
    runtime.activate_observation(upload)

    assert len(executor.operations) == 3


def test_activate_observation_is_idempotent_for_same_handle(tmp_path: Path) -> None:
    """同一 observation 重复 activation 不得 double-submit。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_download(
        FinsDownloadRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    runtime.activate_observation(handle)
    runtime.activate_observation(handle)

    assert len(executor.operations) == 1


def test_cancel_prepared_observation_prevents_later_activation_submit(
    tmp_path: Path,
) -> None:
    """prepared observation activation 前取消后不得提交，并可观察为 CANCELLED。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_preprocess(
        FinsPreprocessRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    cancelled = asyncio.run(runtime.cancel_observation(handle))
    runtime.activate_observation(handle)
    polled = asyncio.run(runtime.poll_observation(handle))

    assert cancelled.status is FinsObservationStatus.CANCELLED
    assert cancelled.result is not None
    assert cancelled.result.status is FinsResultStatus.CANCELLED
    assert cancelled.result.error_kind is FinsErrorKind.CANCELLED
    assert cancelled.result.error_message == "Observation was cancelled before activation."
    assert polled.status is FinsObservationStatus.CANCELLED
    assert executor.operations == []


def test_abandon_cancelled_prepared_observation_releases_handle_before_activation(
    tmp_path: Path,
) -> None:
    """prepared observation 取消并 abandon 后不得提交且 handle 应释放。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_download(
        FinsDownloadRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    cancelled = asyncio.run(runtime.cancel_observation(handle))
    asyncio.run(runtime.abandon_observation(handle))
    runtime.activate_observation(handle)
    polled = asyncio.run(runtime.poll_observation(handle))

    assert cancelled.status is FinsObservationStatus.CANCELLED
    assert polled.status is FinsObservationStatus.LOST
    assert executor.operations == []


def test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts(
    tmp_path: Path,
) -> None:
    """submitted observation abandon 后应协作式取消并保留已写入仓储产物。"""

    workspace_root = tmp_path / "fins-workspace"
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    document_id = "aapl-observed-upload"
    runner = _BlockingArtifactUploadRunner(
        source_repository=default_runtime.source_repository,
        document_id=document_id,
    )
    runtime = ingestion_runtime.FinsIngestionRuntime.create(
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=executor,
        upload_runner=runner,
    )
    handle = runtime.prepare_observed_upload(
        FinsUploadFilingRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    runtime.activate_observation(handle)
    operation_thread = Thread(target=executor.run_all)
    operation_thread.start()
    assert runner.artifact_written.wait(timeout=1.0)

    asyncio.run(runtime.abandon_observation(handle))
    runner.allow_finish.set()
    operation_thread.join(timeout=1.0)
    polled = asyncio.run(runtime.poll_observation(handle))
    source_meta = default_runtime.source_repository.get_source_meta(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )

    assert not operation_thread.is_alive()
    assert runner.cancellation_checks == (True,)
    assert polled.status is FinsObservationStatus.LOST
    assert source_meta["ingest_method"] == "upload"


def test_cancel_and_activate_share_observation_lock_without_timing_sleep(
    tmp_path: Path,
) -> None:
    """cancel 持有 observation lock 时 activation 必须等待同一把锁。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_upload(
        FinsUploadFilingRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )
    hooked_lock = _HookedObservationLock()
    object.__setattr__(runtime, "_observation_lock", hooked_lock)
    snapshots: list[FinsObservationStatus] = []
    exceptions: list[BaseException] = []

    def cancel_operation() -> None:
        """执行取消并记录结果。"""

        try:
            snapshot = asyncio.run(runtime.cancel_observation(handle))
            snapshots.append(snapshot.status)
        except BaseException as exc:
            exceptions.append(exc)

    def activate_operation() -> None:
        """执行 activation 并记录异常。"""

        try:
            runtime.activate_observation(handle)
        except BaseException as exc:
            exceptions.append(exc)

    cancel_thread = Thread(target=cancel_operation)
    cancel_thread.start()
    assert hooked_lock.first_entered.wait(timeout=1.0)

    activate_thread = Thread(target=activate_operation)
    activate_thread.start()
    assert hooked_lock.second_enter_attempted.wait(timeout=1.0)
    assert executor.operations == []

    hooked_lock.allow_first_exit.set()
    cancel_thread.join(timeout=1.0)
    activate_thread.join(timeout=1.0)

    assert not cancel_thread.is_alive()
    assert not activate_thread.is_alive()
    assert exceptions == []
    assert snapshots == [FinsObservationStatus.CANCELLED]
    assert executor.operations == []


def test_activation_submit_failure_is_observed_as_failed_by_wait_adapter(
    tmp_path: Path,
) -> None:
    """activation submit failure 必须转为 FAILED，且现有 wait adapter 可观察。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = _build_ingestion_runtime(
        workspace_root,
        executor=_FailingSubmitExecutor(OSError("submit unavailable")),
    )
    handle = runtime.prepare_observed_download(
        FinsDownloadRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    with pytest.raises(OSError):
        runtime.activate_observation(handle)

    poll = FinsIngestionWaitPollAdapter(runtime=runtime).poll_wait(
        _observation_wait_record(handle, DOWNLOAD_TOOL_NAME)
    )

    assert isinstance(poll, WaitPollReady)
    assert isinstance(poll.outcome, ResolveWaitFailedOutcome)


def test_unexpected_activation_exception_terminalizes_prepared_observation(
    tmp_path: Path,
) -> None:
    """prepared observation 存在后 activation 非预期异常不得遗留 PENDING。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = _build_ingestion_runtime(
        workspace_root,
        executor=_FailingSubmitExecutor(ValueError("unexpected activation error")),
    )
    handle = runtime.prepare_observed_upload(
        FinsUploadFilingRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    with pytest.raises(ValueError):
        runtime.activate_observation(handle)
    snapshot = asyncio.run(runtime.poll_observation(handle))

    assert snapshot.status is FinsObservationStatus.FAILED
    assert snapshot.result is not None
    assert snapshot.result.error_message == "Observation activation failed."


def test_job_serialization_validates_upload_operation_shape(tmp_path: Path) -> None:
    """upload job record 序列化/反序列化应校验 operation/source/source_kind 组合。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    start = runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL"))
    job_file = _job_file(workspace_root, start.job_id)
    payload_value = cast(JsonValue, json.loads(job_file.read_text(encoding="utf-8")))

    assert isinstance(payload_value, Mapping)
    assert payload_value["operation_kind"] == "upload"
    assert payload_value["source"] is None
    assert payload_value["source_kind"] == "filing"

    corrupt_payload = dict(cast(Mapping[str, JsonValue], payload_value))
    corrupt_payload["source_kind"] = None
    job_file.write_text(json.dumps(corrupt_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="upload job record 必须包含 source_kind"):
        runtime.read_job(start.job_id)


def test_request_cancel_marks_active_job_and_keeps_terminal_job_terminal(tmp_path: Path) -> None:
    """取消请求应标记 active job，且不得把终态 job 回退为 active。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    queued_start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    cancelled = ingestion.request_cancel(queued_start.job_id)

    terminal_start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="MSFT"))
    terminal_record = replace(
        terminal_start.record,
        status=FinsIngestionJobStatus.SUCCEEDED,
        result_summary={"processed_count": 0},
        finished_at=terminal_start.record.updated_at,
    )
    ingestion.job_store.save_job(terminal_record)
    after_terminal_cancel = ingestion.request_cancel(terminal_start.job_id)

    assert cancelled.status is FinsIngestionJobStatus.CANCELLING
    assert cancelled.cancellation_requested
    assert after_terminal_cancel.status is FinsIngestionJobStatus.SUCCEEDED
    assert not after_terminal_cancel.cancellation_requested
    assert after_terminal_cancel.result_summary == {"processed_count": 0}


def test_job_events_record_queued_running_and_terminal_sequence(tmp_path: Path) -> None:
    """job 创建、running claim 与终态保存应产生单调递增状态事件。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    queued_events = ingestion.read_job_events(start.job_id)
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id, after_sequence=0, limit=100)
    after_first = ingestion.read_job_events(start.job_id, after_sequence=1, limit=100)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert [event.event_type for event in queued_events] == [FinsIngestionJobEventType.JOB_QUEUED]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
    ]
    assert [event.sequence for event in after_first] == [2, 3, 4, 5]


def test_request_cancel_records_cancel_requested_and_terminal_cancel_events(tmp_path: Path) -> None:
    """request_cancel 应记录 CANCEL_REQUESTED，后台取消收口应记录 JOB_CANCELLED。"""

    workspace_root = _build_fins_workspace(tmp_path)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    cancelling = ingestion.request_cancel(start.job_id)
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert cancelling.status is FinsIngestionJobStatus.CANCELLING
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert [event.sequence for event in events] == [1, 2, 3]
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.CANCEL_REQUESTED,
        FinsIngestionJobEventType.JOB_CANCELLED,
    ]


def test_job_event_sidecar_omits_paths_payload_bodies_and_raw_provider_payloads(tmp_path: Path) -> None:
    """event sidecar 不应包含绝对路径、完整文件路径、财报正文或 provider raw payload。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="uploaded",
        )
    )
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)
    upload_file = tmp_path / "raw" / "aapl-10k.pdf"
    upload_file.parent.mkdir(parents=True)
    upload_file.write_text("Annual recurring revenue increased raw provider payload", encoding="utf-8")

    start = ingestion.start_upload(FinsUploadFilingRequest(ticker="AAPL", files=(upload_file,)))
    executor.run_all()
    event_text = _job_event_file(workspace_root, start.job_id).read_text(encoding="utf-8")

    assert str(workspace_root) not in event_text
    assert str(upload_file) not in event_text
    assert "aapl-10k.pdf" not in event_text
    assert "Annual recurring revenue increased" not in event_text
    assert "raw provider payload" not in event_text
    assert "raw_provider_payload" not in event_text
    assert "provider_raw_payload" not in event_text


def test_job_event_store_concurrent_append_allocates_unique_monotonic_sequences(tmp_path: Path) -> None:
    """并发 append 使用同一 store lock 后 sequence 不应重复或倒退。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL"))
    append_count = 40

    def append_progress(index: int) -> int:
        """追加一个测试 progress event 并返回 sequence。

        Args:
            index: 测试事件序号。

        Returns:
            已分配 sequence。

        Raises:
            FileNotFoundError: job id 不存在时由 store 抛出。
            OSError: event sidecar 写入失败时由 store 抛出。
            ValueError: event payload 非法时由 store 抛出。
        """

        event = ingestion.job_store.append_job_event(
            start.job_id,
            FinsIngestionJobEventAppend(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                status=None,
                event_type=FinsIngestionJobEventType.PROGRESS,
                source_event_type="test",
                source_kind=None,
                document_id=None,
                message="测试进度事件",
                payload={"index": index},
                emitted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )
        return event.sequence

    with ThreadPoolExecutor(max_workers=8) as pool:
        sequences = tuple(pool.map(append_progress, range(append_count)))

    events = ingestion.read_job_events(start.job_id, after_sequence=0, limit=100)

    assert len(sequences) == append_count
    assert len(set(sequences)) == append_count
    assert sorted(sequences) == list(range(2, append_count + 2))
    assert [event.sequence for event in events] == list(range(1, append_count + 2))


def test_job_event_sidecar_skips_corrupted_rows_and_append_continues(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """sidecar 坏行应被跳过，后续 append 仍按有效事件分配 sequence。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL"))
    event_path = _job_event_file(workspace_root, start.job_id)
    leaked_payload_value = "SHOULD_NOT_APPEAR_IN_WARNING"
    original_text = event_path.read_text(encoding="utf-8")
    event_path.write_text(
        f'{original_text}{{"payload":"{leaked_payload_value}"\n'
        f'["{leaked_payload_value}"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        appended = ingestion.job_store.append_job_event(
            start.job_id,
            FinsIngestionJobEventAppend(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                status=None,
                event_type=FinsIngestionJobEventType.PROGRESS,
                source_event_type="test.progress",
                source_kind=None,
                document_id=None,
                message="测试进度事件",
                payload={"step": "after_corruption"},
                emitted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )
        events = ingestion.read_job_events(start.job_id)

    assert appended.sequence == 2
    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.PROGRESS,
    ]
    assert "fins.ingestion.job_event_sidecar_row_skipped" in caplog.text
    assert "sidecar_kind=fins_ingestion_job_event" in caplog.text
    assert "sidecar_suffix=.events.jsonl" in caplog.text
    assert "line_number=2" in caplog.text
    assert "line_number=3" in caplog.text
    assert "error_summary=malformed_or_invalid_event_row" in caplog.text
    assert leaked_payload_value not in caplog.text
    assert start.job_id not in caplog.text


def test_job_event_sidecar_still_rejects_non_monotonic_valid_records(tmp_path: Path) -> None:
    """坏行跳过不得放宽有效 event record 的 sequence 单调性校验。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL"))
    event_path = _job_event_file(workspace_root, start.job_id)
    queued_event_text = event_path.read_text(encoding="utf-8")
    event_path.write_text(f"{queued_event_text}{queued_event_text}", encoding="utf-8")

    with pytest.raises(ValueError, match="sequence 未递增"):
        ingestion.read_job_events(start.job_id)


def test_job_event_append_rejects_non_json_compatible_payload(tmp_path: Path) -> None:
    """event append payload 非 JSON-compatible 时应 fail fast。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL"))

    with pytest.raises(ValueError, match="不是 JSON-compatible"):
        ingestion.job_store.append_job_event(
            start.job_id,
            FinsIngestionJobEventAppend(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                status=None,
                event_type=FinsIngestionJobEventType.PROGRESS,
                source_event_type="test",
                source_kind=None,
                document_id=None,
                message="非法 payload",
                payload=cast(dict[str, JsonValue], {"bad": {"not-json"}}),
                emitted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )


def test_non_terminal_event_append_failure_warns_and_job_still_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """non-terminal event append 失败时应 WARN，且 job 仍可正常进入成功终态。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )
    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    original_append = ingestion_runtime.FsFinsIngestionJobStore.append_job_event

    def raise_for_running_event(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """仅在 JOB_RUNNING event append 时模拟 sidecar 写入失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            event: 待追加事件。

        Returns:
            非 JOB_RUNNING event 的真实追加结果。

        Raises:
            OSError: JOB_RUNNING event append 时抛出。
        """

        if event.event_type is FinsIngestionJobEventType.JOB_RUNNING:
            raise OSError("event sidecar unavailable")
        return original_append(store, job_id, event)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "append_job_event",
        raise_for_running_event,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        executor.run_all()

    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["downloaded_count"] == 1
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
    ]
    assert "fins.ingestion.job_event_append_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "event_type=job_running" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "error_summary=event_append_failed" in caplog.text
    assert "event sidecar unavailable" not in caplog.text


def test_terminal_event_append_failure_warns_without_rolling_back_terminal_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminal event append 失败时应 WARN，且不回滚已保存 terminal job record。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )
    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    original_append = ingestion_runtime.FsFinsIngestionJobStore.append_job_event

    def raise_for_terminal_event(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """仅在 terminal event append 时模拟 sidecar 写入失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            event: 待追加事件。

        Returns:
            非 terminal event 的真实追加结果。

        Raises:
            OSError: terminal event append 时抛出。
        """

        if event.event_type is FinsIngestionJobEventType.JOB_SUCCEEDED:
            raise OSError("event sidecar unavailable")
        return original_append(store, job_id, event)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "append_job_event",
        raise_for_terminal_event,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        executor.run_all()

    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["downloaded_count"] == 1
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.PROGRESS,
    ]
    assert "fins.ingestion.job_event_append_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "event_type=job_succeeded" in caplog.text
    assert "error_type=OSError" in caplog.text


def test_progress_event_append_failure_warns_and_job_still_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PROGRESS event append 失败时应 WARN，且不得改变 upload 业务终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="uploaded",
        )
    )
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        upload_runner=runner,
    )
    start = ingestion.start_upload(FinsUploadFilingRequest(ticker="AAPL"))
    original_append = ingestion_runtime.FsFinsIngestionJobStore.append_job_event

    def raise_for_progress_event(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """仅在 PROGRESS event append 时模拟 sidecar 写入失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            event: 待追加事件。

        Returns:
            非 PROGRESS event 的真实追加结果。

        Raises:
            OSError: PROGRESS event append 时抛出。
        """

        if event.event_type is FinsIngestionJobEventType.PROGRESS:
            raise OSError("event sidecar unavailable")
        return original_append(store, job_id, event)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "append_job_event",
        raise_for_progress_event,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        executor.run_all()

    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["document_id"] == "aapl-2024-10k"
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
    ]
    assert "fins.ingestion.job_event_append_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "event_type=progress" in caplog.text
    assert "source_event_type=upload.started" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "event sidecar unavailable" not in caplog.text


def test_save_cancelled_does_not_overwrite_current_terminal_record(tmp_path: Path) -> None:
    """_save_cancelled 应读取 store 当前状态，不能用旧 active record 覆盖终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    terminal_record = replace(
        start.record,
        status=FinsIngestionJobStatus.SUCCEEDED,
        updated_at=start.record.updated_at,
        finished_at=start.record.updated_at,
        result_summary={"processed_count": 0, "sentinel": True},
        cancellation_requested=False,
    )
    ingestion.job_store.save_job(terminal_record)

    saved = ingestion._save_cancelled(start.record)
    reloaded = ingestion.read_job(start.job_id)

    assert saved.status is FinsIngestionJobStatus.SUCCEEDED
    assert reloaded.status is FinsIngestionJobStatus.SUCCEEDED
    assert not reloaded.cancellation_requested
    assert reloaded.result_summary == {"processed_count": 0, "sentinel": True}
    assert reloaded.finished_at == terminal_record.finished_at


def test_save_failed_uses_current_cancelling_record_instead_of_stale_active_record(
    tmp_path: Path,
) -> None:
    """_save_failed 应读取 store 当前状态，不能用旧 active record 覆盖取消请求。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    cancelling = ingestion.request_cancel(start.job_id)

    saved = ingestion._save_failed(
        start.record,
        message="late failure",
        result_summary={"processed_count": 1},
    )
    reloaded = ingestion.read_job(start.job_id)

    assert cancelling.status is FinsIngestionJobStatus.CANCELLING
    assert saved.status is FinsIngestionJobStatus.CANCELLED
    assert reloaded.status is FinsIngestionJobStatus.CANCELLED
    assert reloaded.cancellation_requested
    assert reloaded.result_summary == {}
    assert reloaded.failure_summary == {}
    assert reloaded.finished_at is not None


def test_job_records_do_not_expose_payload_bodies_raw_provider_payloads_or_paths(tmp_path: Path) -> None:
    """job record 只应包含治理摘要，不应暴露正文、raw payload 或文件系统路径。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
            form_types=("10-K",),
        )
    )
    payload_text = _job_file(workspace_root, start.job_id).read_text(encoding="utf-8")
    payload_value = cast(JsonValue, json.loads(payload_text))

    assert isinstance(payload_value, Mapping)
    assert str(workspace_root) not in payload_text
    assert "Annual recurring revenue increased" not in payload_text
    assert "processed_payload" not in payload_text
    assert "provider_raw_payload" not in payload_text
    assert "raw_provider_payload" not in payload_text
    assert "aapl-2024-10k.md" not in payload_text
    assert payload_value["request_summary"] == {
        "source_kind": "filing",
        "document_ids": ["aapl-2024-10k"],
        "form_types": ["10-K"],
        "rebuild_processed": False,
    }


def test_start_preprocess_processes_source_document_to_processed_repository(tmp_path: Path) -> None:
    """预处理应通过仓储读取 source 并写入 processed 产物。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
            form_types=("10-K",),
        )
    )
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)
    processed_meta = runtime.processed_repository.get_processed_meta("AAPL", "aapl-2024-10k")

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]
    assert processed_meta["document_id"] == "aapl-2024-10k"
    assert int(processed_meta["section_count"]) > 0
    assert processed_meta["parser_version"] != ""
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_processed",
        "preprocess.completed",
    ]
    assert progress_events[0].payload["selected_count"] == 1
    assert progress_events[1].document_id == "aapl-2024-10k"
    assert progress_events[2].document_id == "aapl-2024-10k"
    assert progress_events[3].payload["processed_count"] == 1


def test_start_preprocess_whole_ticker_applies_limit_after_form_filter(tmp_path: Path) -> None:
    """整 ticker 预处理上限应作用于表单过滤后的实际工作集。"""

    workspace_root = _build_fins_workspace(tmp_path)
    _add_unmatched_source_documents(
        workspace_root=workspace_root,
        count=ingestion_runtime._MAX_PREPROCESS_DOCUMENTS + 1,
    )
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            form_types=("10-K",),
        )
    )
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]


def test_start_preprocess_skips_existing_processed_document_without_rebuild(tmp_path: Path) -> None:
    """rebuild_processed=False 时已有 processed 文档应被跳过。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()
    first = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    _wait_terminal(ingestion, first.job_id)

    second = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    record = _wait_terminal(ingestion, second.job_id)
    progress_events = _progress_events(ingestion, second.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["processed_count"] == 0
    assert record.result_summary["skipped_count"] == 1
    assert record.result_summary["skipped_document_ids"] == ["aapl-2024-10k"]
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_skipped",
        "preprocess.completed",
    ]
    assert progress_events[2].document_id == "aapl-2024-10k"
    assert progress_events[3].payload["skipped_count"] == 1


def test_start_preprocess_rebuild_updates_existing_processed_document(tmp_path: Path) -> None:
    """rebuild_processed=True 时已有 processed 文档应走 update。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()
    first = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    _wait_terminal(ingestion, first.job_id)

    second = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
            rebuild_processed=True,
        )
    )
    record = _wait_terminal(ingestion, second.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]


def test_start_preprocess_cancel_before_execution_writes_cancelled_terminal(tmp_path: Path) -> None:
    """queued 后执行前收到取消请求时，后台执行应收口为 cancelled。"""

    workspace_root = _build_fins_workspace(tmp_path)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    cancelling = ingestion.request_cancel(start.job_id)
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert cancelling.status is FinsIngestionJobStatus.CANCELLING
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested


def test_claim_running_preserves_cancel_between_read_and_running_write(
    tmp_path: Path,
) -> None:
    """claim running 期间收到取消请求时，不得覆盖为 running。"""

    workspace_root = _build_fins_workspace(tmp_path)
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    job_store = _ClaimRaceJobStore()
    ingestion = ingestion_runtime.FinsIngestionRuntime.create(
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=job_store,
        executor=executor,
    )

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
        )
    )
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert job_store.claim_running_calls == 1
    assert job_store.save_job_calls == 0
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.status is not FinsIngestionJobStatus.RUNNING
    assert record.cancellation_requested


def test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功终态写入前收到取消请求时，应以当前取消状态收口为 cancelled。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("fake", "US"): adapter},
    )
    original_save = ingestion.job_store.save_succeeded_or_cancelled

    def cancel_before_success_terminalization(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """在 success 终态裁决前插入取消请求。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            result_summary: success 结果摘要。
            finished_at: 终态写入时间。

        Returns:
            真实 success-or-cancelled 终态写入结果。

        Raises:
            FileNotFoundError: job id 不存在时由真实实现抛出。
            OSError: job store 读写失败时由真实实现抛出。
            ValueError: record 或摘要非法时由真实实现抛出。
        """

        del store
        ingestion.request_cancel(job_id)
        return original_save(job_id, result_summary=result_summary, finished_at=finished_at)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_succeeded_or_cancelled",
        cancel_before_success_terminalization,
    )

    start = ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert len(adapter.requests) == 1
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert record.result_summary == {}


def test_runners_return_for_preterminalized_jobs_without_executing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已进入终态的 download 与 preprocess job 不应被后台 runner 再次执行。"""

    download_workspace = tmp_path / "download-workspace"
    download_adapter = _FakeDownloadAdapter()
    download_executor = _HoldingExecutor()
    download_ingestion = _build_ingestion_runtime(
        download_workspace,
        executor=download_executor,
        download_adapters={("fake", "US"): download_adapter},
    )
    download_start = download_ingestion.start_download(FinsDownloadRequest(ticker="AAPL", source="fake"))
    download_ingestion.job_store.save_job(
        replace(
            download_start.record,
            status=FinsIngestionJobStatus.SUCCEEDED,
            finished_at=download_start.record.updated_at,
            result_summary={"sentinel": True},
        )
    )

    preprocess_workspace = _build_fins_workspace(tmp_path)
    preprocess_executor = _HoldingExecutor()
    preprocess_ingestion = _build_ingestion_runtime(preprocess_workspace, executor=preprocess_executor)
    preprocess_start = preprocess_ingestion.start_preprocess(
        FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",))
    )
    preprocess_ingestion.job_store.save_job(
        replace(
            preprocess_start.record,
            status=FinsIngestionJobStatus.SUCCEEDED,
            finished_at=preprocess_start.record.updated_at,
            result_summary={"sentinel": True},
        )
    )
    preprocess_execute_calls = 0

    def count_preprocess_execution(
        record: ingestion_runtime.FinsIngestionJobRecord,
        request: FinsPreprocessRequest,
    ) -> FinsPreprocessResultSummary:
        """记录 preprocess 执行调用。

        Args:
            record: runner 传入的 job record。
            request: runner 传入的预处理请求。

        Returns:
            空预处理摘要。

        Raises:
            无。
        """

        nonlocal preprocess_execute_calls
        del record, request
        preprocess_execute_calls += 1
        return FinsPreprocessResultSummary()

    monkeypatch.setattr(preprocess_ingestion, "_execute_preprocess_request", count_preprocess_execution)

    download_executor.run_all()
    preprocess_executor.run_all()
    download_record = download_ingestion.read_job(download_start.job_id)
    preprocess_record = preprocess_ingestion.read_job(preprocess_start.job_id)

    assert download_adapter.requests == []
    assert download_record.result_summary == {"sentinel": True}
    assert preprocess_execute_calls == 0
    assert preprocess_record.result_summary == {"sentinel": True}


def test_start_preprocess_missing_document_fails_terminal_record(tmp_path: Path) -> None:
    """显式缺失文档应写入 failed 终态而不是后台异常逃逸。"""

    workspace_root = _build_fins_workspace(tmp_path)
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("missing-doc",)))
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert "源文档不存在" in str(record.failure_summary["message"])


def test_start_preprocess_general_exception_emits_document_failed_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单文档预处理出现一般异常时应产生 document_failed progress。"""

    workspace_root = _build_fins_workspace(tmp_path)
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    def fail_preprocess_document(
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        rebuild_processed: bool,
    ) -> str:
        """模拟处理器执行期一般异常。

        Args:
            ticker: 标准化 ticker。
            document_id: 源文档 ID。
            source_kind: 源文档类型。
            rebuild_processed: 是否重建 processed 产物。

        Returns:
            不返回；总是抛出异常。

        Raises:
            RuntimeError: 始终抛出，用于触发一般异常分支。
        """

        del ticker, document_id, source_kind, rebuild_processed
        raise RuntimeError("processor crashed")

    monkeypatch.setattr(ingestion, "_preprocess_one_document", fail_preprocess_document)

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["failed_document_ids"] == ["aapl-2024-10k"]
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_failed",
        "preprocess.completed",
    ]
    assert progress_events[2].message == "预处理源文档失败"
    assert progress_events[2].document_id == "aapl-2024-10k"


def test_start_preprocess_unsupported_document_records_not_supported_summary(tmp_path: Path) -> None:
    """无可用处理器时应记录 not_supported 文档并按无可处理文档失败。"""

    workspace_root = _build_fins_workspace(tmp_path)
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = ingestion_runtime.FinsIngestionRuntime.create(
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=ProcessorRegistry(),
        job_store=default_runtime.ingestion_job_store,
    )

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 0
    assert record.result_summary["not_supported_document_ids"] == ["aapl-2024-10k"]
    assert "没有任何请求文档完成预处理" in str(record.failure_summary["message"])
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_not_supported",
        "preprocess.completed",
    ]
    assert progress_events[2].message == "预处理源文档不支持"
    assert progress_events[2].document_id == "aapl-2024-10k"


def test_save_failed_from_exception_logs_secondary_job_store_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """失败收口二次写 job store 失败时应记录诊断且不向外传播。"""

    workspace_root = _build_fins_workspace(tmp_path)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))

    def raise_save_failed_or_cancelled(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        failure_summary: dict[str, JsonValue],
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """模拟 failed 终态落盘失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            failure_summary: failed 终态失败摘要。
            result_summary: failed 终态结果摘要。
            finished_at: 终态写入时间。

        Returns:
            不返回；始终抛出异常。

        Raises:
            OSError: 始终抛出，模拟 job store 写入失败。
        """

        del store, job_id, failure_summary, result_summary, finished_at
        raise OSError("job store save failed")

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_failed_or_cancelled_if_active",
        raise_save_failed_or_cancelled,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        ingestion._save_failed_from_exception(start.job_id, RuntimeError("primary failure"))

    assert "fins.ingestion.failed_terminalization_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "original_error_type=RuntimeError" in caplog.text


def test_job_store_removes_temp_file_when_atomic_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """atomic replace 失败时 job store 应删除本次写入留下的临时文件。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    jobs_dir = workspace_root / ".dayu" / "fins_ingestion" / "jobs"

    def raise_replace(
        src: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        dst: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        """模拟 atomic replace 在临时文件已写入后失败。

        Args:
            src: 源路径。
            dst: 目标路径。

        Returns:
            无。

        Raises:
            OSError: 始终抛出，模拟文件系统 replace 失败。
        """

        raise OSError("replace failed")

    monkeypatch.setattr(ingestion_runtime.os, "replace", raise_replace)

    with pytest.raises(OSError, match="replace failed"):
        runtime.start_download(FinsDownloadRequest(ticker="AAPL"))

    assert jobs_dir.is_dir()
    assert tuple(jobs_dir.glob(".*.tmp")) == ()


def test_default_runtime_keeps_read_runtime_lazy_singleton(tmp_path: Path) -> None:
    """新增 ingestion runtime 不应破坏 read runtime 懒加载行为。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    first_read_runtime = runtime.get_read_runtime()
    second_read_runtime = runtime.get_read_runtime()

    assert isinstance(first_read_runtime, FinsReadRuntime)
    assert first_read_runtime is second_read_runtime


def _job_file(workspace_root: Path, job_id: str) -> Path:
    """返回 S1 约定的 job record 文件路径。

    Args:
        workspace_root: Fins 工作区根目录。
        job_id: opaque job id。

    Returns:
        job record JSON 文件路径。

    Raises:
        无。
    """

    return workspace_root / ".dayu" / "fins_ingestion" / "jobs" / f"{job_id}.json"


def _job_event_file(workspace_root: Path, job_id: str) -> Path:
    """返回 S1 约定的 job event sidecar 路径。

    Args:
        workspace_root: Fins 工作区根目录。
        job_id: opaque job id。

    Returns:
        job event JSONL 文件路径。

    Raises:
        无。
    """

    return workspace_root / ".dayu" / "fins_ingestion" / "jobs" / f"{job_id}.events.jsonl"


def _build_ingestion_runtime(
    workspace_root: Path,
    *,
    executor: FinsIngestionExecutor,
    download_adapters: Mapping[tuple[str, ticker_normalization.Market], FinsSourceDownloadAdapter] | None = None,
    upload_runner: FinsUploadRunner | None = None,
) -> ingestion_runtime.FinsIngestionRuntime:
    """构建测试用 ingestion runtime。

    Args:
        workspace_root: Fins workspace root。
        executor: 测试执行器。
        download_adapters: 可选下载 adapter 映射。
        upload_runner: 可选上传 runner。

    Returns:
        ingestion runtime。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    return ingestion_runtime.FinsIngestionRuntime.create(
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=executor,
        download_adapters=download_adapters,
        upload_runner=upload_runner,
    )


def _observation_wait_record(
    handle: FinsObservationHandle,
    tool_name: str,
) -> WaitRecordRow:
    """构造 observation wait adapter 测试用 Host wait record。

    Args:
        handle: Fins observation handle。
        tool_name: awaiting 工具名。

    Returns:
        Host wait record row。

    Raises:
        ValueError: 字段非法时由 Host durable 类型抛出。
    """

    return WaitRecordRow(
        wait_id=f"wait-{handle.handle_id}",
        session_id="session-fins",
        run_id="run-fins",
        attempt_id="attempt-fins",
        execution_id="execution-fins",
        tool_call_id=f"call-{tool_name}",
        tool_name=tool_name,
        adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
        await_kind="external_job",
        resume_policy=WaitResumePolicy.POLL,
        resume_token=handle.handle_id,
        snapshot_ref=None,
        external_job_ref=ExternalJobRef(
            adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
            external_job_id=handle.handle_id,
        ),
        accept_idempotency_key=f"accept-{handle.handle_id}",
        resolve_idempotency_key=None,
        resolve_semantic_digest=None,
        deadline_at=None,
        expires_at=None,
        status=WaitRecordStatus.WAITING,
        created_event_id=f"event-created-{handle.handle_id}",
        created_event_sequence=1,
        updated_event_id=f"event-updated-{handle.handle_id}",
        updated_event_sequence=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        terminal_at=None,
    )


def _add_unmatched_source_documents(
    *,
    workspace_root: Path,
    count: int,
) -> None:
    """追加不匹配 10-K 表单过滤条件的源文档。

    Args:
        workspace_root: Fins workspace root。
        count: 需要追加的 10-Q 源文档数量。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
        ValueError: 源文档字段非法时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    token = batching_repository.begin_batch("AAPL")
    try:
        for index in range(count):
            document_id = f"aapl-2024-10q-{index:02d}"
            source_repository.create_source_document(
                SourceDocumentUpsertRequest(
                    ticker="AAPL",
                    document_id=document_id,
                    internal_document_id=document_id,
                    form_type="10-Q",
                    primary_document=f"{document_id}.md",
                    meta={
                        "fiscal_year": 2024,
                        "fiscal_period": "Q",
                        "filing_date": "2024-08-01",
                        "report_date": "2024-06-29",
                        "amended": False,
                        "ingest_method": "upload",
                    },
                ),
                SourceKind.FILING,
            )
        batching_repository.commit_batch(token)
    except Exception:
        batching_repository.rollback_batch(token)
        raise


def _wait_terminal(
    ingestion: ingestion_runtime.FinsIngestionRuntime,
    job_id: str,
) -> ingestion_runtime.FinsIngestionJobRecord:
    """等待 job 进入终态。

    Args:
        ingestion: ingestion runtime。
        job_id: opaque job id。

    Returns:
        终态 job record。

    Raises:
        AssertionError: 超时未进入终态时抛出。
    """

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        record = ingestion.read_job(job_id)
        if record.status in {
            FinsIngestionJobStatus.SUCCEEDED,
            FinsIngestionJobStatus.FAILED,
            FinsIngestionJobStatus.CANCELLED,
        }:
            return record
        time.sleep(0.02)
    raise AssertionError(f"job 未进入终态: {job_id}")


def _progress_events(
    ingestion: ingestion_runtime.FinsIngestionRuntime,
    job_id: str,
) -> tuple[FinsIngestionJobEventRecord, ...]:
    """读取指定 job 的 PROGRESS events。

    Args:
        ingestion: ingestion runtime。
        job_id: opaque job id。

    Returns:
        按 sequence 升序排列的 PROGRESS event 元组。

    Raises:
        FileNotFoundError: job id 不存在时由 runtime 抛出。
        OSError: event sidecar 读取失败时由 runtime 抛出。
        ValueError: event sidecar 内容非法时由 runtime 抛出。
    """

    return tuple(
        event
        for event in ingestion.read_job_events(job_id, after_sequence=0, limit=1000)
        if event.event_type is FinsIngestionJobEventType.PROGRESS
    )


async def _collect_direct_events(events: AsyncIterator[FinsEvent]) -> tuple[FinsEvent, ...]:
    """收集 direct stream 事件。

    Args:
        events: Fins direct async event stream。

    Returns:
        已收集事件元组。

    Raises:
        Exception: stream 迭代失败时原样抛出。
    """

    collected: list[FinsEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)


def _build_fins_workspace(
    tmp_path: Path,
    *,
    content_type: str = "text/markdown",
) -> Path:
    """构造确定性 Fins fixture 工作区。

    Args:
        tmp_path: pytest 临时目录。
        content_type: 主文件 content type。

    Returns:
        Fins workspace root。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            market="US",
            resolver_version="test",
            updated_at=now_iso8601(),
            ticker_aliases=["APPLE"],
        )
    )
    token = batching_repository.begin_batch("AAPL")
    try:
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="aapl-2024-10k",
                internal_document_id="aapl-2024-10k",
                form_type="10-K",
                primary_document="aapl-2024-10k.md",
                meta={
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "amended": False,
                    "ingest_method": "upload",
                },
            ),
            SourceKind.FILING,
        )
        handle = source_repository.get_source_handle("AAPL", "aapl-2024-10k", SourceKind.FILING)
        file_meta = blob_repository.store_file(
            handle,
            "aapl-2024-10k.md",
            io.BytesIO(_fixture_markdown().encode("utf-8")),
            content_type=content_type,
        )
        source_repository.update_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="aapl-2024-10k",
                internal_document_id="aapl-2024-10k",
                form_type="10-K",
                primary_document="aapl-2024-10k.md",
                meta={
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "amended": False,
                    "ingest_method": "upload",
                },
                files=[file_meta],
            ),
            SourceKind.FILING,
        )
        batching_repository.commit_batch(token)
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    return workspace_root


def _fixture_markdown() -> str:
    """返回测试财报 Markdown 内容。

    Args:
        无。

    Returns:
        Markdown 财报片段。

    Raises:
        无。
    """

    return "\n".join(
        (
            "# Apple 2024 Form 10-K",
            "",
            "## Item 1. Business",
            "Annual recurring revenue increased in services.",
            "",
            "## Item 7. Management Discussion",
            "| Segment | Revenue |",
            "| --- | ---: |",
            "| Services | 100 |",
        )
    )


def _is_terminal_job_status(status: FinsIngestionJobStatus) -> bool:
    """判断 Fins ingestion job 状态是否为终态。

    Args:
        status: 待判断的 job 状态。

    Returns:
        终态返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    return status in {
        FinsIngestionJobStatus.SUCCEEDED,
        FinsIngestionJobStatus.FAILED,
        FinsIngestionJobStatus.CANCELLED,
    }
