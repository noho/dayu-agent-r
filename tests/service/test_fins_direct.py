"""Fins direct command Service helper 测试。"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_events import FinsIngestionJobEventRecord, FinsIngestionJobEventType
from dayu.fins.ingestion_runtime import (
    FinsDownloadRequest,
    FinsIngestionJobRecord,
    FinsIngestionOperationKind,
    FinsIngestionJobStart,
    FinsIngestionJobStatus,
    FinsPreprocessRequest,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
)
from dayu.service.fins_direct import (
    DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
    FINS_DIRECT_JOB_EVENT_READ_LIMIT,
    FINS_DIRECT_SYNTHETIC_TERMINAL_EVENT_LABEL,
    FinsDirectCommandService,
    FinsDirectJobHandle,
    FinsDirectRuntimeStateError,
    FinsDirectStartRequest,
    FinsDirectUsageError,
)

_NOW: str = "2026-06-14T00:00:00+00:00"


class _FakeIngestionRuntime:
    """测试用 Fins ingestion runtime。"""

    download_requests: list[FinsDownloadRequest]
    preprocess_requests: list[FinsPreprocessRequest]
    upload_requests: list[FinsUploadFilingRequest | FinsUploadMaterialRequest]
    cancel_requests: list[str]
    records: list[FinsIngestionJobRecord]
    event_batches: list[tuple[FinsIngestionJobEventRecord, ...]]
    event_read_calls: list[tuple[str, int, int]]
    event_read_error: Exception | None
    read_job_error: Exception | None

    def __init__(
        self,
        records: tuple[FinsIngestionJobRecord, ...] = (),
        *,
        event_batches: tuple[tuple[FinsIngestionJobEventRecord, ...], ...] = (),
        event_read_error: Exception | None = None,
        read_job_error: Exception | None = None,
    ) -> None:
        """初始化 fake runtime。

        :param records: read_job 依次返回的 records。
        :param event_batches: read_job_events 依次返回的事件批次。
        :param event_read_error: read_job_events 需要抛出的异常。
        :param read_job_error: read_job 需要抛出的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests = []
        self.preprocess_requests = []
        self.upload_requests = []
        self.cancel_requests = []
        self.records = list(records)
        self.event_batches = list(event_batches)
        self.event_read_calls = []
        self.event_read_error = event_read_error
        self.read_job_error = read_job_error

    def start_download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """记录下载请求。

        :param request: 下载请求。
        :param cancellation_token: 启动边界取消 token。
        :returns: fake job start。
        :raises Exception: 不主动抛出异常。
        """

        del cancellation_token
        self.download_requests.append(request)
        return _job_start("download-job")

    def start_preprocess(
        self,
        request: FinsPreprocessRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """记录预处理请求。

        :param request: 预处理请求。
        :param cancellation_token: 启动边界取消 token。
        :returns: fake job start。
        :raises Exception: 不主动抛出异常。
        """

        del cancellation_token
        self.preprocess_requests.append(request)
        return _job_start("preprocess-job")

    def start_upload(
        self,
        request: FinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """记录上传请求。

        :param request: upload union request。
        :param cancellation_token: 启动边界取消 token。
        :returns: fake job start。
        :raises Exception: 不主动抛出异常。
        """

        del cancellation_token
        self.upload_requests.append(request)
        return _job_start("upload-job")

    def read_job(self, job_id: str) -> FinsIngestionJobRecord:
        """读取预设 job record。

        :param job_id: Fins ingestion job id。
        :returns: 预设 record。
        :raises AssertionError: 未配置 record 时抛出。
        """

        assert job_id == "job-1"
        if self.read_job_error is not None:
            raise self.read_job_error
        assert self.records
        if len(self.records) > 1:
            return self.records.pop(0)
        return self.records[0]

    def read_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int = 0,
        limit: int = FINS_DIRECT_JOB_EVENT_READ_LIMIT,
    ) -> tuple[FinsIngestionJobEventRecord, ...]:
        """读取预设 job events。

        :param job_id: Fins ingestion job id。
        :param after_sequence: 事件游标。
        :param limit: 单次读取数量上限。
        :returns: 预设事件批次。
        :raises Exception: 配置 event_read_error 时抛出。
        """

        assert job_id == "job-1"
        self.event_read_calls.append((job_id, after_sequence, limit))
        if self.event_read_error is not None:
            raise self.event_read_error
        if self.event_batches:
            return self.event_batches.pop(0)
        return ()

    def request_cancel(self, job_id: str) -> FinsIngestionJobRecord:
        """记录取消请求。

        :param job_id: Fins ingestion job id。
        :returns: cancelling record。
        :raises Exception: 不主动抛出异常。
        """

        self.cancel_requests.append(job_id)
        return _record(job_id=job_id, status=FinsIngestionJobStatus.CANCELLING)


def _record(
    *,
    job_id: str = "job-1",
    status: FinsIngestionJobStatus,
    result_summary: dict[str, JsonValue] | None = None,
    failure_summary: dict[str, JsonValue] | None = None,
) -> FinsIngestionJobRecord:
    """构造测试 job record。

    :param job_id: Fins ingestion job id。
    :param status: job 状态。
    :param result_summary: 可选结果摘要。
    :param failure_summary: 可选失败摘要。
    :returns: job record。
    :raises Exception: 不主动抛出异常。
    """

    return FinsIngestionJobRecord(
        job_id=job_id,
        operation_kind=FinsIngestionOperationKind.DOWNLOAD,
        normalized_ticker="AAPL",
        market="US",
        exchange=None,
        source=None,
        source_kind=None,
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        started_at=None,
        finished_at=_NOW if status in {
            FinsIngestionJobStatus.SUCCEEDED,
            FinsIngestionJobStatus.FAILED,
            FinsIngestionJobStatus.CANCELLED,
        } else None,
        request_summary={},
        result_summary={} if result_summary is None else result_summary,
        failure_summary={} if failure_summary is None else failure_summary,
        cancellation_requested=status in {
            FinsIngestionJobStatus.CANCELLING,
            FinsIngestionJobStatus.CANCELLED,
        },
    )


def _job_start(job_id: str) -> FinsIngestionJobStart:
    """构造测试 job start。

    :param job_id: Fins ingestion job id。
    :returns: job start。
    :raises Exception: 不主动抛出异常。
    """

    record = _record(job_id=job_id, status=FinsIngestionJobStatus.QUEUED)
    return FinsIngestionJobStart(
        job_id=job_id,
        status=FinsIngestionJobStatus.QUEUED,
        record=record,
    )


def _handle() -> FinsDirectJobHandle:
    """构造测试 direct job handle。

    :returns: 测试 direct job handle。
    :raises Exception: 不主动抛出异常。
    """

    return FinsDirectJobHandle(
        job_id="job-1",
        initial_status=FinsIngestionJobStatus.QUEUED,
        start_request=FinsDirectStartRequest(command_name="download", ticker="AAPL"),
    )


def _event(
    *,
    sequence: int,
    event_type: FinsIngestionJobEventType,
    status: FinsIngestionJobStatus | None = None,
    source_event_type: str | None = None,
    message: str = "progress",
    payload: dict[str, JsonValue] | None = None,
) -> FinsIngestionJobEventRecord:
    """构造测试 job event record。

    :param sequence: event sequence。
    :param event_type: Fins job event type。
    :param status: 事件状态。
    :param source_event_type: 可选来源事件标签。
    :param message: 事件说明。
    :param payload: 事件 payload。
    :returns: Fins ingestion job event record。
    :raises Exception: 不主动抛出异常。
    """

    return FinsIngestionJobEventRecord(
        job_id="job-1",
        sequence=sequence,
        operation_kind=FinsIngestionOperationKind.DOWNLOAD,
        status=status,
        event_type=event_type,
        source_event_type=source_event_type,
        source_kind=SourceKind.FILING,
        document_id=None,
        message=message,
        payload={} if payload is None else payload,
        emitted_at=_NOW,
    )


def test_start_download_builds_typed_request() -> None:
    """download helper 必须构造 FinsDownloadRequest。"""

    runtime = _FakeIngestionRuntime()
    service = FinsDirectCommandService(runtime)

    handle = service.start_download(
        ticker="AAPL",
        form_types=("10-K", "10-Q"),
        filed_after="2024-01-01",
        filed_before="2024-12-31",
        overwrite_existing=True,
        rebuild_processed=True,
    )

    assert handle.job_id == "download-job"
    assert runtime.download_requests == [
        FinsDownloadRequest(
            ticker="AAPL",
            form_types=("10-K", "10-Q"),
            filed_after="2024-01-01",
            filed_before="2024-12-31",
            overwrite_existing=True,
            rebuild_processed=True,
        )
    ]


def test_start_preprocess_builds_typed_request() -> None:
    """preprocess helper 必须构造 FinsPreprocessRequest。"""

    runtime = _FakeIngestionRuntime()
    service = FinsDirectCommandService(runtime)

    handle = service.start_preprocess(
        command_name="process_material",
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        document_ids=("doc-1",),
        form_types=("8-K",),
        rebuild_processed=True,
    )

    assert handle.start_request.command_name == "process_material"
    assert runtime.preprocess_requests == [
        FinsPreprocessRequest(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            document_ids=("doc-1",),
            form_types=("8-K",),
            rebuild_processed=True,
        )
    ]


def test_upload_wrappers_call_start_upload_with_union_requests(tmp_path: Path) -> None:
    """upload_filing/material wrapper 必须调用 runtime.start_upload。"""

    filing_file = tmp_path / "filing.pdf"
    material_file = tmp_path / "material.pdf"
    runtime = _FakeIngestionRuntime()
    service = FinsDirectCommandService(runtime)

    service.start_upload_filing(
        ticker="AAPL",
        action="update",
        files=(filing_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        amended=True,
        filing_date="2025-01-30",
        report_date="2024-12-31",
        company_name="Apple Inc.",
        ticker_aliases=("Apple",),
        overwrite=True,
    )
    service.start_upload_material(
        ticker="MSFT",
        action="create",
        files=(material_file,),
        form_type="8-K",
        material_name="Investor Day",
        document_id="doc-1",
        internal_document_id="internal-1",
        fiscal_year=2024,
        fiscal_period="Q4",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        company_name="Microsoft",
        ticker_aliases=("MS",),
        overwrite=True,
    )

    assert isinstance(runtime.upload_requests[0], FinsUploadFilingRequest)
    assert runtime.upload_requests[0] == FinsUploadFilingRequest(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        files=(filing_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        amended=True,
        filing_date="2025-01-30",
        report_date="2024-12-31",
        company_name="Apple Inc.",
        ticker_aliases=("Apple",),
        overwrite=True,
    )
    assert isinstance(runtime.upload_requests[1], FinsUploadMaterialRequest)
    assert runtime.upload_requests[1] == FinsUploadMaterialRequest(
        ticker="MSFT",
        source_kind=SourceKind.MATERIAL,
        action="create",
        files=(material_file,),
        form_type="8-K",
        material_name="Investor Day",
        document_id="doc-1",
        internal_document_id="internal-1",
        fiscal_year=2024,
        fiscal_period="Q4",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        company_name="Microsoft",
        ticker_aliases=("MS",),
        overwrite=True,
    )


@pytest.mark.asyncio
async def test_stream_job_events_outputs_progress_and_terminal_by_sequence() -> None:
    """stream_job_events_until_terminal 必须按 sequence 输出 progress 并在 terminal 停止。"""

    progress = _event(
        sequence=1,
        event_type=FinsIngestionJobEventType.PROGRESS,
        source_event_type="download_started",
        message="download started",
        payload={"ticker": "AAPL"},
    )
    terminal = _event(
        sequence=2,
        event_type=FinsIngestionJobEventType.JOB_SUCCEEDED,
        status=FinsIngestionJobStatus.SUCCEEDED,
        message="download succeeded",
    )
    runtime = _FakeIngestionRuntime(
        (_record(status=FinsIngestionJobStatus.SUCCEEDED, result_summary={"ok": True}),),
        event_batches=((progress, terminal),),
    )
    service = FinsDirectCommandService(runtime, sleep=_unused_sleep)

    events = [
        event
        async for event in service.stream_job_events_until_terminal(
            _handle(),
            after_sequence=0,
        )
    ]

    assert runtime.event_read_calls == [("job-1", 0, FINS_DIRECT_JOB_EVENT_READ_LIMIT)]
    assert [event.sequence for event in events] == [1, 2]
    assert events[0].command_name == "download"
    assert events[0].ticker == "AAPL"
    assert events[0].event_label == "download_started"
    assert events[0].payload == {"ticker": "AAPL"}
    assert events[0].terminal_result is None
    assert events[1].event_label == FinsIngestionJobEventType.JOB_SUCCEEDED.value
    assert events[1].terminal_result is not None
    assert events[1].terminal_result.exit_code == FINS_DIRECT_EXIT_SUCCESS
    assert events[1].terminal_result.result_summary == {"ok": True}


@pytest.mark.asyncio
async def test_stream_job_events_rejects_negative_after_sequence() -> None:
    """after_sequence 为负数时必须 fail fast，且不读取 runtime。"""

    runtime = _FakeIngestionRuntime()
    service = FinsDirectCommandService(runtime, sleep=_unused_sleep)

    with pytest.raises(FinsDirectUsageError, match="after_sequence"):
        async for _event_item in service.stream_job_events_until_terminal(
            _handle(),
            after_sequence=-1,
        ):
            raise AssertionError("unexpected event")

    assert runtime.event_read_calls == []


@pytest.mark.asyncio
async def test_stream_job_events_reports_terminal_record_inconsistency() -> None:
    """terminal event 到达但 job record 非终态时必须暴露 runtime 数据不一致。"""

    terminal = _event(
        sequence=7,
        event_type=FinsIngestionJobEventType.JOB_SUCCEEDED,
        status=FinsIngestionJobStatus.SUCCEEDED,
        message="download succeeded",
    )
    runtime = _FakeIngestionRuntime(
        (_record(status=FinsIngestionJobStatus.RUNNING),),
        event_batches=((terminal,),),
    )
    service = FinsDirectCommandService(runtime, sleep=_unused_sleep)

    with pytest.raises(
        FinsDirectRuntimeStateError,
        match="terminal job event observed before terminal job record",
    ):
        async for _event_item in service.stream_job_events_until_terminal(_handle()):
            raise AssertionError("unexpected event")

    assert runtime.event_read_calls == [("job-1", 0, FINS_DIRECT_JOB_EVENT_READ_LIMIT)]


@pytest.mark.asyncio
async def test_stream_job_events_propagates_read_job_failure_after_terminal_event() -> None:
    """terminal event 到达后 read_job 失败时必须向调用方透传。"""

    terminal = _event(
        sequence=8,
        event_type=FinsIngestionJobEventType.JOB_FAILED,
        status=FinsIngestionJobStatus.FAILED,
        message="download failed",
    )
    runtime = _FakeIngestionRuntime(
        event_batches=((terminal,),),
        read_job_error=LookupError("unknown job"),
    )
    service = FinsDirectCommandService(runtime, sleep=_unused_sleep)

    with pytest.raises(LookupError, match="unknown job"):
        async for _event_item in service.stream_job_events_until_terminal(_handle()):
            raise AssertionError("unexpected event")

    assert runtime.event_read_calls == [("job-1", 0, FINS_DIRECT_JOB_EVENT_READ_LIMIT)]


@pytest.mark.asyncio
async def test_stream_job_events_synthesizes_terminal_after_missing_terminal_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminal event 缺失但 job record 已终态时必须 WARN 并合成 terminal event。"""

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        """记录 sleep 调用。

        :param seconds: sleep 秒数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        sleep_calls.append(seconds)

    runtime = _FakeIngestionRuntime(
        (_record(status=FinsIngestionJobStatus.FAILED, failure_summary={"error": "boom"}),),
        event_batches=((),),
    )
    service = FinsDirectCommandService(
        runtime,
        poll_interval_seconds=0.25,
        sleep=fake_sleep,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.service.fins_direct"):
        events = [
            event
            async for event in service.stream_job_events_until_terminal(
                _handle(),
                after_sequence=3,
            )
        ]

    assert sleep_calls == [0.25]
    assert len(events) == 1
    assert events[0].sequence == 4
    assert events[0].status is FinsIngestionJobStatus.FAILED
    assert events[0].event_label == FINS_DIRECT_SYNTHETIC_TERMINAL_EVENT_LABEL
    assert events[0].payload == {}
    assert events[0].terminal_result is not None
    assert events[0].terminal_result.exit_code == FINS_DIRECT_EXIT_FAILURE
    assert events[0].terminal_result.failure_summary == {"error": "boom"}
    assert "missing_terminal_event" in caplog.text
    assert "job-1" in caplog.text
    assert "failed" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.asyncio
async def test_stream_job_events_sleeps_after_empty_read_before_polling_again() -> None:
    """empty read 后必须按 poll_interval_seconds sleep，避免 tight loop。"""

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        """记录 sleep 调用。

        :param seconds: sleep 秒数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        sleep_calls.append(seconds)

    progress = _event(
        sequence=1,
        event_type=FinsIngestionJobEventType.PROGRESS,
        message="still running",
    )
    terminal = _event(
        sequence=2,
        event_type=FinsIngestionJobEventType.JOB_CANCELLED,
        status=FinsIngestionJobStatus.CANCELLED,
        message="cancelled",
    )
    runtime = _FakeIngestionRuntime(
        (
            _record(status=FinsIngestionJobStatus.RUNNING),
            _record(status=FinsIngestionJobStatus.CANCELLED),
        ),
        event_batches=((), (progress,), (terminal,)),
    )
    service = FinsDirectCommandService(
        runtime,
        poll_interval_seconds=0.5,
        sleep=fake_sleep,
    )

    events = [
        event
        async for event in service.stream_job_events_until_terminal(
            _handle(),
            after_sequence=0,
        )
    ]

    assert sleep_calls == [0.5]
    assert runtime.event_read_calls == [
        ("job-1", 0, FINS_DIRECT_JOB_EVENT_READ_LIMIT),
        ("job-1", 0, FINS_DIRECT_JOB_EVENT_READ_LIMIT),
        ("job-1", 1, FINS_DIRECT_JOB_EVENT_READ_LIMIT),
    ]
    assert [event.sequence for event in events] == [1, 2]
    assert events[-1].terminal_result is not None
    assert events[-1].terminal_result.exit_code == FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT


@pytest.mark.asyncio
async def test_stream_job_events_propagates_event_store_failure() -> None:
    """read_job_events 失败必须向调用方透传。"""

    runtime = _FakeIngestionRuntime(event_read_error=RuntimeError("store failed"))
    service = FinsDirectCommandService(runtime, sleep=_unused_sleep)

    with pytest.raises(RuntimeError, match="store failed"):
        async for _event_item in service.stream_job_events_until_terminal(_handle()):
            raise AssertionError("unexpected event")


@pytest.mark.asyncio
async def test_stream_job_events_propagates_unknown_job_after_empty_read() -> None:
    """empty read 后 read_job 发现未知 job 时必须向调用方透传。"""

    async def fake_sleep(seconds: float) -> None:
        """允许 fallback 前的一次 sleep。

        :param seconds: sleep 秒数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del seconds

    runtime = _FakeIngestionRuntime(
        event_batches=((),),
        read_job_error=LookupError("unknown job"),
    )
    service = FinsDirectCommandService(runtime, sleep=fake_sleep)

    with pytest.raises(LookupError, match="unknown job"):
        async for _event_item in service.stream_job_events_until_terminal(_handle()):
            raise AssertionError("unexpected event")


@pytest.mark.asyncio
async def test_wait_for_terminal_sleeps_only_for_nonterminal_statuses() -> None:
    """wait_for_terminal 只在非终态状态下 sleep，默认间隔为 1 秒。"""

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        """记录 sleep 调用。

        :param seconds: sleep 秒数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        sleep_calls.append(seconds)

    runtime = _FakeIngestionRuntime(
        (
            _record(status=FinsIngestionJobStatus.QUEUED),
            _record(status=FinsIngestionJobStatus.RUNNING),
            _record(status=FinsIngestionJobStatus.CANCELLING),
            _record(
                status=FinsIngestionJobStatus.SUCCEEDED,
                result_summary={"ok": True},
            ),
        )
    )
    service = FinsDirectCommandService(runtime, sleep=fake_sleep)

    result = await service.wait_for_terminal("job-1")

    assert service.poll_interval_seconds == DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS
    assert sleep_calls == [
        DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
        DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
        DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS,
    ]
    assert result.exit_code == FINS_DIRECT_EXIT_SUCCESS
    assert result.result_summary == {"ok": True}


@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    (
        (FinsIngestionJobStatus.SUCCEEDED, FINS_DIRECT_EXIT_SUCCESS),
        (FinsIngestionJobStatus.FAILED, FINS_DIRECT_EXIT_FAILURE),
        (FinsIngestionJobStatus.CANCELLED, FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT),
    ),
)
@pytest.mark.asyncio
async def test_terminal_status_exit_mapping(
    status: FinsIngestionJobStatus,
    expected_exit_code: int,
) -> None:
    """SUCCEEDED / FAILED / CANCELLED 必须映射到稳定退出码。"""

    runtime = _FakeIngestionRuntime((_record(status=status),))
    service = FinsDirectCommandService(runtime, sleep=_unused_sleep)

    result = await service.wait_for_terminal("job-1")

    assert result.exit_code == expected_exit_code


def test_request_cancel_delegates_to_runtime() -> None:
    """request_cancel 必须调用 runtime durable cancel。"""

    runtime = _FakeIngestionRuntime()
    service = FinsDirectCommandService(runtime)

    record = service.request_cancel("job-1")

    assert runtime.cancel_requests == ["job-1"]
    assert record.status is FinsIngestionJobStatus.CANCELLING


def test_invalid_poll_interval_fails_fast() -> None:
    """非法 poll interval 必须 fail fast。"""

    runtime = _FakeIngestionRuntime()

    with pytest.raises(FinsDirectUsageError):
        FinsDirectCommandService(runtime, poll_interval_seconds=0.0)


async def _unused_sleep(seconds: float) -> None:
    """不应被调用的 sleep 替身。

    :param seconds: sleep 秒数。
    :returns: ``None``。
    :raises AssertionError: 被调用时抛出。
    """

    raise AssertionError(f"unexpected sleep: {seconds}")
