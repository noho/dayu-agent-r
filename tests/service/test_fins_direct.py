"""Fins direct command Service helper 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
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
    FinsDirectCommandService,
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

    def __init__(self, records: tuple[FinsIngestionJobRecord, ...] = ()) -> None:
        """初始化 fake runtime。

        :param records: read_job 依次返回的 records。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.download_requests = []
        self.preprocess_requests = []
        self.upload_requests = []
        self.cancel_requests = []
        self.records = list(records)

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
        assert self.records
        if len(self.records) > 1:
            return self.records.pop(0)
        return self.records[0]

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
