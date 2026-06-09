"""Fins ingestion runtime foundation 测试。"""

from __future__ import annotations

import json
import io
import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins import ticker_normalization
from dayu.fins.domain.enums import SourceKind
from dayu.fins import ingestion_runtime
from dayu.fins.domain.document_models import (
    CompanyMeta,
    SourceDocumentUpsertRequest,
    now_iso8601,
)
from dayu.fins.ingestion_runtime import (
    FinsDownloadedFile,
    FinsDownloadedSourceDocument,
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

    def __init__(self) -> None:
        """初始化请求记录。"""

        self.requests: list[FinsSourceDownloadAdapterRequest] = []

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
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=FinsDownloadResultSummary(
                discovered_count=1,
                downloaded_count=0,
                skipped_count=1,
                rejected_count=0,
                failed_count=0,
                written_document_ids=(),
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

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["source_kind"] == "filing"
    assert record.result_summary["status"] == "ok"
    assert record.result_summary["primary_document"] == "aapl-10q_docling.json"
    document_id = str(record.result_summary["document_id"])
    meta = ingestion.source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    assert meta["ingest_method"] == "upload"
    assert meta["primary_document"] == "aapl-10q_docling.json"


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
    processed_meta = runtime.processed_repository.get_processed_meta("AAPL", "aapl-2024-10k")

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]
    assert processed_meta["document_id"] == "aapl-2024-10k"
    assert int(processed_meta["section_count"]) > 0
    assert processed_meta["parser_version"] != ""


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

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["processed_count"] == 0
    assert record.result_summary["skipped_count"] == 1
    assert record.result_summary["skipped_document_ids"] == ["aapl-2024-10k"]


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

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 0
    assert record.result_summary["not_supported_document_ids"] == ["aapl-2024-10k"]
    assert "没有任何请求文档完成预处理" in str(record.failure_summary["message"])


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
