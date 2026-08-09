"""Fins direct command Service stream 边界测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import dayu.service.fins_direct as fins_direct_module
from dayu.contracts.cancellation import CancellationToken
from dayu.fins.direct_events import (
    FinsErrorKind,
    FinsDirectStreamProtocolError,
    FinsDirectStreamProtocolErrorKind,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsOperationKind,
    FinsProgress,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.direct_events import ValidatedFinsEventStream
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import (
    FINS_DOWNLOAD_MAX_FORM_CHARS,
    FINS_DOWNLOAD_MAX_FORM_ITEMS,
    FINS_DOWNLOAD_MAX_TICKER_CHARS,
    FinsDownloadDateRange,
    FinsDownloadSource,
    FinsDownloadUsageError,
    FinsDownloadRequest,
    build_fins_download_request,
)
from dayu.fins.ingestion_runtime import (
    FinsPreprocessRequest,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadRequest,
)
from dayu.service.fins_direct import (
    FINS_DIRECT_EXIT_FAILURE,
    FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT,
    FINS_DIRECT_EXIT_SUCCESS,
    FinsDirectCommandService,
)
from tests.host.fake_cancellation import ControllableCancellationToken

_NOW: datetime = datetime(2026, 6, 14, tzinfo=timezone.utc)


class _FakeIngestionRuntime:
    """测试用 Fins direct ingestion runtime。"""

    download_requests: list[FinsDownloadRequest]
    preprocess_requests: list[FinsPreprocessRequest]
    upload_requests: list[FinsUploadRequest]
    cancellation_tokens: list[CancellationToken | None]
    events: tuple[FinsEvent, ...]
    stream_error: Exception | None
    closed_streams: int
    pause_after_first_event: bool
    first_event_yielded: asyncio.Event
    release_paused_stream: asyncio.Event
    returned_streams: list[ValidatedFinsEventStream]

    def __init__(
        self,
        events: tuple[FinsEvent, ...],
        *,
        stream_error: Exception | None = None,
        pause_after_first_event: bool = False,
    ) -> None:
        """初始化 fake runtime。

        :param events: 每个 direct stream 需要产出的事件。
        :param stream_error: 可选 stream 末尾抛出的异常。
        :param pause_after_first_event: 是否在第一个事件后阻塞，供取消测试使用。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests = []
        self.preprocess_requests = []
        self.upload_requests = []
        self.cancellation_tokens = []
        self.events = events
        self.stream_error = stream_error
        self.closed_streams = 0
        self.pause_after_first_event = pause_after_first_event
        self.first_event_yielded = asyncio.Event()
        self.release_paused_stream = asyncio.Event()
        self.returned_streams = []

    def download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录下载请求并返回 fake direct stream。

        :param request: 下载请求。
        :param cancellation_token: 可选取消 token。
        :returns: Fins direct 事件异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests.append(request)
        self.cancellation_tokens.append(cancellation_token)
        return self._validated_stream(FinsOperationKind.DOWNLOAD)

    def preprocess(
        self,
        request: FinsPreprocessRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录预处理请求并返回 fake direct stream。

        :param request: 预处理请求。
        :param cancellation_token: 可选取消 token。
        :returns: Fins direct 事件异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        self.preprocess_requests.append(request)
        self.cancellation_tokens.append(cancellation_token)
        return self._validated_stream(FinsOperationKind.PREPROCESS)

    def upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """记录上传请求并返回 fake direct stream。

        :param request: 上传请求。
        :param cancellation_token: 可选取消 token。
        :returns: Fins direct 事件异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        self.upload_requests.append(request)
        self.cancellation_tokens.append(cancellation_token)
        if isinstance(request, FinsUploadFilingRequest):
            operation_kind = FinsOperationKind.UPLOAD_FILING
        else:
            operation_kind = FinsOperationKind.UPLOAD_MATERIAL
        return self._validated_stream(operation_kind)

    def _validated_stream(
        self,
        operation_kind: FinsOperationKind,
    ) -> ValidatedFinsEventStream:
        """用 production owner 包装 raw fake stream。

        :param operation_kind: runtime 拥有的 direct 操作来源。
        :returns: production validator stream。
        :raises Exception: 不主动抛出异常。
        """

        stream = ValidatedFinsEventStream(
            self._raw_stream(),
            operation_kind=operation_kind,
        )
        self.returned_streams.append(stream)
        return stream

    async def _raw_stream(self) -> AsyncGenerator[FinsEvent, None]:
        """产出预设 raw 事件并在关闭时记录 close。

        :returns: 未校验的 Fins direct raw 事件 async generator。
        :raises Exception: stream_error 不为空时在事件后抛出。
        """

        try:
            for index, event in enumerate(self.events):
                yield event
                if index == 0:
                    self.first_event_yielded.set()
                    if self.pause_after_first_event:
                        await self.release_paused_stream.wait()
            if self.stream_error is not None:
                raise self.stream_error
        finally:
            self.closed_streams += 1


def _progress_event(
    *,
    operation_kind: FinsOperationKind = FinsOperationKind.DOWNLOAD,
    message: str = "download started",
) -> FinsEvent:
    """构造 progress 事件。

    :param operation_kind: 操作类型。
    :param message: 事件说明。
    :returns: Fins direct progress 事件。
    :raises ValueError: 事件违反 direct contract 时抛出。
    """

    return FinsEvent(
        event_type=FinsEventType.PROGRESS,
        operation_kind=operation_kind,
        message=message,
        emitted_at=_NOW,
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=FinsProgress(stage="download", completed_units=1, total_units=2),
        result=None,
    )


def _result_event(
    *,
    status: FinsResultStatus = FinsResultStatus.SUCCESS,
    operation_kind: FinsOperationKind = FinsOperationKind.DOWNLOAD,
) -> FinsEvent:
    """构造 result 事件。

    :param status: 终态状态。
    :param operation_kind: 操作类型。
    :returns: Fins direct result 事件。
    :raises ValueError: 事件违反 direct contract 时抛出。
    """

    if status is FinsResultStatus.SUCCESS:
        exit_code = FINS_DIRECT_EXIT_SUCCESS
        error_kind = None
        error_message = None
    elif status is FinsResultStatus.FAILURE:
        exit_code = FINS_DIRECT_EXIT_FAILURE
        error_kind = FinsErrorKind.EXECUTION
        error_message = "provider failed"
    else:
        exit_code = FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT
        error_kind = FinsErrorKind.CANCELLED
        error_message = "cancelled"
    return FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=operation_kind,
        message="download finished",
        emitted_at=_NOW,
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=None,
        result=FinsResultSummary(
            status=status,
            exit_code=exit_code,
            title="Download finished",
            details=(FinsEventDetail(label="ticker", value="AAPL"),),
            error_kind=error_kind,
            error_message=error_message,
        ),
    )


async def _collect_events(events: AsyncIterator[FinsEvent]) -> list[FinsEvent]:
    """完整消费 direct stream。

    :param events: Fins direct 事件异步迭代器。
    :returns: 已收集事件列表。
    :raises Exception: stream 迭代失败时原样透传。
    """

    collected: list[FinsEvent] = []
    async for event in events:
        collected.append(event)
    return collected


async def _consume_until_cancelled(events: AsyncIterator[FinsEvent]) -> None:
    """持续消费 stream，直到测试取消 task。

    :param events: Fins direct 事件异步迭代器。
    :returns: ``None``。
    :raises asyncio.CancelledError: task 被取消时透传。
    """

    async for _event in events:
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_download_stream_accepts_typed_request_and_yields_progress_result() -> None:
    """download 必须透传 owner 构造的 typed request 并产出 progress -> result。"""

    token = ControllableCancellationToken()
    runtime = _FakeIngestionRuntime((_progress_event(), _result_event()))
    service = FinsDirectCommandService(runtime)
    request = build_fins_download_request(
        ticker="AAPL",
        form_types=("10-K", "10-Q"),
        start="2024-01-01",
        end="2024-12-31",
        overwrite_existing=True,
        rebuild_local_artifacts=True,
    )

    events = await _collect_events(
        service.download(
            request,
            cancellation_token=token,
        )
    )

    assert runtime.download_requests == [request]
    assert runtime.cancellation_tokens == [token]
    assert [event.event_type for event in events] == [
        FinsEventType.PROGRESS,
        FinsEventType.RESULT,
    ]
    assert events[-1].result is not None
    assert events[-1].result.exit_code == FINS_DIRECT_EXIT_SUCCESS


def test_download_request_builder_owns_canonical_ticker_forms_source_and_dates() -> None:
    """builder 应一次性产生下游可直接消费的 US canonical 业务事实。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: canonical contract 与显式日期语义不符时抛出。
    """

    request = build_fins_download_request(
        ticker=" aapl.us ",
        form_types=("10k", "10-K", "SC13D/G"),
        start="2024-02",
        end="2024",
    )

    assert request.normalized_ticker.canonical == "AAPL"
    assert request.source is FinsDownloadSource.SEC
    assert request.form_types == ("10-K", "SC 13D/G")
    assert request.date_range.start_bound == date(2024, 2, 1)
    assert request.date_range.end_bound == date(2024, 12, 31)
    assert request.date_range.start_is_explicit
    assert request.date_range.end_is_explicit


@pytest.mark.parametrize(
    ("start_bound", "end_bound", "start_is_explicit", "end_is_explicit", "expected_message"),
    (
        (None, None, True, False, "显式起始日期必须提供 start_bound"),
        (None, None, False, True, "显式结束日期必须提供 end_bound"),
        (
            date(2025, 1, 1),
            date(2024, 12, 31),
            False,
            False,
            "--start 不能晚于 --end",
        ),
    ),
)
def test_download_date_range_rejects_invalid_contract_combinations(
    start_bound: date | None,
    end_bound: date | None,
    start_is_explicit: bool,
    end_is_explicit: bool,
    expected_message: str,
) -> None:
    """日期契约 owner 应拒绝显式标记缺边界与倒序边界。

    Args:
        start_bound: 起始日期边界。
        end_bound: 结束日期边界。
        start_is_explicit: 起始日期是否显式。
        end_is_explicit: 结束日期是否显式。
        expected_message: 预期中文错误文本。

    Returns:
        无。

    Raises:
        AssertionError: 非法组合未由日期契约 owner 拒绝时抛出。
    """

    with pytest.raises(FinsDownloadUsageError, match=expected_message):
        FinsDownloadDateRange(
            start_bound=start_bound,
            end_bound=end_bound,
            start_is_explicit=start_is_explicit,
            end_is_explicit=end_is_explicit,
        )


def test_download_date_range_allows_non_explicit_nonempty_bounds() -> None:
    """日期契约应允许未来默认边界携带非空日期而保持非显式。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 合法的未来默认边界被拒绝时抛出。
    """

    date_range = FinsDownloadDateRange(
        start_bound=date(2024, 1, 1),
        end_bound=date(2024, 12, 31),
        start_is_explicit=False,
        end_is_explicit=False,
    )

    assert date_range.start_text == "2024-01-01"
    assert date_range.end_text == "2024-12-31"


@pytest.mark.parametrize(
    ("ticker", "forms", "start", "end", "expected_message"),
    (
        (" ", (), None, None, "--ticker 不能为空"),
        ("AAPL,MSFT", (), None, None, "只接受一个公司代码"),
        ("A" * (FINS_DOWNLOAD_MAX_TICKER_CHARS + 1), (), None, None, "--ticker 过长"),
        ("INVALID!", (), None, None, "--ticker 无法识别"),
        ("AAPL", ("",), None, None, "第 1 项不能为空"),
        ("AAPL", ("UNKNOWN",), None, None, "--forms 不支持"),
        (
            "AAPL",
            tuple("10-K" for _ in range(FINS_DOWNLOAD_MAX_FORM_ITEMS + 1)),
            None,
            None,
            "--forms 最多允许",
        ),
        (
            "AAPL",
            ("X" * (FINS_DOWNLOAD_MAX_FORM_CHARS + 1),),
            None,
            None,
            "第 1 项过长",
        ),
        ("AAPL", (), "2024-13", None, "--start 不是有效日期"),
        ("AAPL", (), "2024/01/01", None, "--start 格式错误"),
        ("AAPL", (), "2025", "2024", "--start 不能晚于 --end"),
    ),
)
def test_download_request_builder_rejects_static_usage_errors(
    ticker: str,
    forms: tuple[str, ...],
    start: str | None,
    end: str | None,
    expected_message: str,
) -> None:
    """builder 应把全部静态非法输入归一为中文 actionable usage error。

    Args:
        ticker: 测试 ticker。
        forms: 测试 form tuple。
        start: 测试起始日期。
        end: 测试结束日期。
        expected_message: 预期中文错误片段。

    Returns:
        无。

    Raises:
        AssertionError: 错误类型或中文诊断不符合 contract 时抛出。
    """

    with pytest.raises(FinsDownloadUsageError, match=expected_message):
        build_fins_download_request(
            ticker=ticker,
            form_types=forms,
            start=start,
            end=end,
        )


@pytest.mark.parametrize(
    ("ticker", "forms", "expected_source", "expected_forms"),
    (
        ("600519.SH", ("年度报告", "Q1"), FinsDownloadSource.CNINFO, ("FY", "Q1")),
        ("700.HK", ("中报", "4Q"), FinsDownloadSource.HKEXNEWS, ("H1", "Q4")),
    ),
)
def test_download_request_builder_reuses_domain_period_alias_owner(
    ticker: str,
    forms: tuple[str, ...],
    expected_source: FinsDownloadSource,
    expected_forms: tuple[str, ...],
) -> None:
    """CN/HK 请求应复用 domain alias owner 并由市场解析唯一来源。

    Args:
        ticker: 带市场语义的 ticker。
        forms: CN/HK 财期别名。
        expected_source: 预期下载来源。
        expected_forms: 预期 canonical 财期。

    Returns:
        无。

    Raises:
        AssertionError: 来源或财期 canonicalization 漂移时抛出。
    """

    request = build_fins_download_request(ticker=ticker, form_types=forms)

    assert request.source is expected_source
    assert request.form_types == expected_forms


@pytest.mark.asyncio
async def test_process_methods_build_preprocess_requests() -> None:
    """process/process_filing/process_material 必须映射到 preprocess request。"""

    runtime = _FakeIngestionRuntime(
        (
            _result_event(operation_kind=FinsOperationKind.PREPROCESS),
        )
    )
    service = FinsDirectCommandService(runtime)

    await _collect_events(
        service.process(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_ids=("doc-1",),
            form_types=("10-K",),
            rebuild_processed=True,
        )
    )
    await _collect_events(
        service.process_filing(
            ticker="MSFT",
            document_ids=("filing-1",),
            form_types=("8-K",),
            rebuild_processed=False,
        )
    )
    await _collect_events(
        service.process_material(
            ticker="TSLA",
            document_ids=("material-1",),
            form_types=("presentation",),
            rebuild_processed=True,
        )
    )

    assert runtime.preprocess_requests == [
        FinsPreprocessRequest(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_ids=("doc-1",),
            form_types=("10-K",),
            rebuild_processed=True,
        ),
        FinsPreprocessRequest(
            ticker="MSFT",
            source_kind=SourceKind.FILING,
            document_ids=("filing-1",),
            form_types=("8-K",),
            rebuild_processed=False,
        ),
        FinsPreprocessRequest(
            ticker="TSLA",
            source_kind=SourceKind.MATERIAL,
            document_ids=("material-1",),
            form_types=("presentation",),
            rebuild_processed=True,
        ),
    ]


@pytest.mark.asyncio
async def test_upload_methods_build_union_requests(tmp_path: Path) -> None:
    """upload_filing/upload_material 必须调用 runtime.upload union 边界。"""

    filing_file = tmp_path / "filing.pdf"
    material_file = tmp_path / "material.pdf"
    runtime = _FakeIngestionRuntime(
        (
            _result_event(operation_kind=FinsOperationKind.UPLOAD_FILING),
        )
    )
    service = FinsDirectCommandService(runtime)

    await _collect_events(
        service.upload_filing(
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
    )
    await _collect_events(
        service.upload_material(
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
async def test_failure_result_is_passed_through() -> None:
    """runtime 产出的 failure RESULT 必须原样通过 Service。"""

    runtime = _FakeIngestionRuntime((_result_event(status=FinsResultStatus.FAILURE),))
    service = FinsDirectCommandService(runtime)

    events = await _collect_events(
        service.download(build_fins_download_request(ticker="AAPL"))
    )

    assert len(events) == 1
    assert events[0].result is not None
    assert events[0].result.status is FinsResultStatus.FAILURE
    assert events[0].result.exit_code == FINS_DIRECT_EXIT_FAILURE


@pytest.mark.asyncio
async def test_stream_exception_is_propagated_without_synthetic_result() -> None:
    """runtime stream 异常必须透传，不能伪造成 terminal fallback。"""

    runtime = _FakeIngestionRuntime(
        (_progress_event(),),
        stream_error=RuntimeError("provider failed"),
    )
    service = FinsDirectCommandService(runtime)

    with pytest.raises(RuntimeError, match="provider failed"):
        await _collect_events(
            service.download(build_fins_download_request(ticker="AAPL"))
        )


@pytest.mark.asyncio
async def test_fins_owned_protocol_error_fields_and_object_are_propagated_by_identity() -> None:
    """验证 Service 透传同一个 Fins owner stream 与 typed error 对象。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: stream/error identity 或 typed fields 改变时抛出。
    """

    owner_error = FinsDirectStreamProtocolError(
        FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT,
        FinsOperationKind.DOWNLOAD,
        "Fins direct stream produced multiple RESULT events",
    )
    runtime = _FakeIngestionRuntime(
        (_progress_event(),),
        stream_error=owner_error,
    )
    service = FinsDirectCommandService(runtime)
    stream = service.download(build_fins_download_request(ticker="AAPL"))

    assert stream is runtime.returned_streams[-1]
    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)

    assert captured.value is owner_error
    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT
    assert captured.value.operation_kind is FinsOperationKind.DOWNLOAD
    assert captured.value.message == "Fins direct stream produced multiple RESULT events"


@pytest.mark.asyncio
async def test_process_filing_keeps_runtime_preprocess_protocol_error_provenance() -> None:
    """验证 process_filing 不把 runtime PREPROCESS 来源改成入口 alias。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: stream identity 或 operation provenance 改变时抛出。
    """

    runtime = _FakeIngestionRuntime(
        (
            _result_event(operation_kind=FinsOperationKind.PREPROCESS),
            _result_event(operation_kind=FinsOperationKind.PREPROCESS),
        )
    )
    service = FinsDirectCommandService(runtime)
    stream = service.process_filing(ticker="AAPL")

    assert stream is runtime.returned_streams[-1]
    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)

    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT
    assert captured.value.operation_kind is FinsOperationKind.PREPROCESS


@pytest.mark.asyncio
async def test_process_material_keeps_runtime_preprocess_protocol_error_provenance() -> None:
    """验证 process_material 不把 runtime PREPROCESS 来源改成入口 alias。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: stream identity 或 operation provenance 改变时抛出。
    """

    runtime = _FakeIngestionRuntime(
        (
            _result_event(operation_kind=FinsOperationKind.PREPROCESS),
            _result_event(operation_kind=FinsOperationKind.PREPROCESS),
        )
    )
    service = FinsDirectCommandService(runtime)
    stream = service.process_material(ticker="AAPL")

    assert stream is runtime.returned_streams[-1]
    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)

    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT
    assert captured.value.operation_kind is FinsOperationKind.PREPROCESS


@pytest.mark.asyncio
async def test_task_cancellation_closes_runtime_stream() -> None:
    """调用方取消消费 task 时必须关闭 runtime async iterator。"""

    runtime = _FakeIngestionRuntime(
        (_progress_event(), _result_event()),
        pause_after_first_event=True,
    )
    service = FinsDirectCommandService(runtime)

    task = asyncio.create_task(
        _consume_until_cancelled(
            service.download(build_fins_download_request(ticker="AAPL"))
        )
    )
    await runtime.first_event_yielded.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runtime.closed_streams == 1


def test_service_public_direct_api_does_not_export_job_handle() -> None:
    """Service public direct API 不得暴露 job handle 或 job event。"""

    assert "FinsDirectJobHandle" not in fins_direct_module.__all__
    assert "FinsDirectJobEvent" not in fins_direct_module.__all__
    assert "FinsDirectTerminalResult" not in fins_direct_module.__all__
    assert "FinsDirectJobHandle" not in dir(fins_direct_module)
    assert "FinsDirectJobEvent" not in dir(fins_direct_module)
    assert "FinsDirectTerminalResult" not in dir(fins_direct_module)
    assert "stream_job_events_until_terminal" not in dir(FinsDirectCommandService)
    assert "wait_for_terminal" not in dir(FinsDirectCommandService)
    assert "request_cancel" not in dir(FinsDirectCommandService)


def test_fins_event_contract_rejects_invalid_progress_and_result_shapes() -> None:
    """FinsEvent 必须校验 PROGRESS/RESULT 互斥规则。"""

    with pytest.raises(ValueError, match="PROGRESS"):
        FinsEvent(
            event_type=FinsEventType.PROGRESS,
            operation_kind=FinsOperationKind.DOWNLOAD,
            message="progress",
            emitted_at=_NOW,
            ticker="AAPL",
            filing_kind=None,
            document_label=None,
            progress=_progress_event().progress,
            result=_result_event().result,
        )
    with pytest.raises(ValueError, match="RESULT"):
        FinsEvent(
            event_type=FinsEventType.RESULT,
            operation_kind=FinsOperationKind.DOWNLOAD,
            message="result",
            emitted_at=_NOW,
            ticker="AAPL",
            filing_kind=None,
            document_label=None,
            progress=None,
            result=None,
        )


@pytest.mark.parametrize(
    ("status", "exit_code"),
    (
        (FinsResultStatus.SUCCESS, FINS_DIRECT_EXIT_FAILURE),
        (FinsResultStatus.FAILURE, FINS_DIRECT_EXIT_SUCCESS),
        (FinsResultStatus.CANCELLED, FINS_DIRECT_EXIT_FAILURE),
    ),
)
def test_fins_result_exit_code_mapping_is_fixed(
    status: FinsResultStatus,
    exit_code: int,
) -> None:
    """SUCCESS/FAILURE/CANCELLED 必须固定映射到 0/1/130。"""

    with pytest.raises(ValueError, match="exit code"):
        FinsResultSummary(
            status=status,
            exit_code=exit_code,
            title="bad mapping",
            details=(),
            error_kind=None,
            error_message=None,
        )


@pytest.mark.parametrize(
    "message",
    (
        "job_id=finsjob_0123456789abcdef0123456789abcdef",
        "sequence=42",
        "cursor abc",
        "path=/Users/leo/workspace/secret.pdf",
        "raw payload contains provider json",
        "财报正文：long body",
    ),
)
def test_fins_event_leakage_guard_rejects_internal_or_sensitive_text(
    message: str,
) -> None:
    """message/details/document_label 不得包含内部治理或敏感材料。"""

    with pytest.raises(ValueError):
        FinsEvent(
            event_type=FinsEventType.PROGRESS,
            operation_kind=FinsOperationKind.DOWNLOAD,
            message=message,
            emitted_at=_NOW,
            ticker="AAPL",
            filing_kind=None,
            document_label=None,
            progress=FinsProgress(stage="download", completed_units=None, total_units=None),
            result=None,
        )
    with pytest.raises(ValueError):
        FinsEventDetail(label="source", value=message)
    with pytest.raises(ValueError):
        FinsEvent(
            event_type=FinsEventType.PROGRESS,
            operation_kind=FinsOperationKind.DOWNLOAD,
            message="progress",
            emitted_at=_NOW,
            ticker="AAPL",
            filing_kind=None,
            document_label=message,
            progress=FinsProgress(stage="download", completed_units=None, total_units=None),
            result=None,
        )
