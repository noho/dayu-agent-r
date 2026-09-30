"""CN/HK download runtime 接入测试。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins.domain.document_models import FinsSourceProvider, ProcessedCreateRequest
from dayu.fins.domain.document_models import BatchToken
from dayu.fins.domain.company_meta_contract import CompanyMetaCommitOutcome
from dayu.fins.direct_events import (
    FinsDownloadFailureReason,
    FinsErrorKind,
    FinsEvent,
    FinsEventType,
    FinsPublicFailureKind,
    FinsResultStatus,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import (
    FinsDownloadDateRange,
    FinsDownloadTerminalDisposition,
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
    build_fins_download_request,
)
from dayu.fins.ingestion_runtime import (
    FinsIngestionExecutor,
    FinsIngestionJobStatus,
    FinsIngestionRuntime,
    FinsSourceDownloadAdapterRequest,
    FsFinsIngestionJobStore,
)
from dayu.fins import ingestion_runtime as ingestion_runtime_module
from dayu.fins.storage._fs_storage_infra import _ActiveBatchState
from dayu.fins.storage._fs_identity import _FILING_IDENTITY_NAMESPACE, _identity_directory_path
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.pipelines.cn_download_models import (
    CnMarketKind,
    CnCompanyProfile,
    CnReportCandidate,
    CnReportPeriodProjection,
    CnReportQuery,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionResult,
)
import dayu.fins.pipelines.cn_pipeline as cn_pipeline_module
from dayu.fins.pipelines.cn_pipeline import (
    CN_DOWNLOAD_SOURCE,
    HK_DOWNLOAD_SOURCE,
    CnDownloadAdapter,
    CnPipeline,
    CnPipelineDownloadResult,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.service_runtime import DefaultFinsRuntime, ProductionFinsUploadRunner
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsFilingUploadStateRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    SourceIntegrityClassification,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import Exchange, NormalizedTicker

_PDF_BYTES = b"%PDF-1.7\n" + b"1" * 2048
_DOCLING_BYTES = b'{"document": "runtime-ok"}'


class _NeverCancelledChecker(CancellationToken):
    """始终未取消并保留 callable checkpoint 的测试 checker。"""

    def __call__(self) -> bool:
        """委托 canonical 方法。

        Returns:
            始终返回 ``False``。
        """

        return self.is_cancelled()

    def is_cancelled(self) -> bool:
        """返回取消状态。

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
        """返回取消时间。

        Returns:
            始终返回 ``None``。
        """

        return None


_NEVER_CANCELLED_CHECKER = _NeverCancelledChecker()


def _cn_projection_request() -> FinsSourceDownloadAdapterRequest:
    """构造 CN adapter projection 使用的 typed request。

    Returns:
        固定 canonical request。

    Raises:
        无。
    """

    return FinsSourceDownloadAdapterRequest(
        normalized_ticker=NormalizedTicker(
            canonical="600519",
            market="CN",
            exchange="SSE",
            raw="600519",
        ),
        source=FinsDownloadSource.CNINFO,
        form_types=("FY",),
        date_range=FinsDownloadDateRange(None, None, False, False),
        overwrite_existing=False,
        rebuild_local_artifacts=False,
        cancellation_checker=_NEVER_CANCELLED_CHECKER,
    )


def _cn_projection_result(filings: JsonValue) -> dict[str, JsonValue]:
    """构造带完整 effective filters 的 CN workflow 私有结果。

    Args:
        filings: 待验证的 filing payload。

    Returns:
        projection 测试输入。

    Raises:
        无。
    """

    return {
        "status": "ok",
        "ticker": "600519",
        "filters": {
            "forms": ["FY"],
            "start_dates": {},
            "end_date": None,
            "overwrite": False,
            "rebuild": False,
        },
        "missing_periods": [],
        "filings": filings,
        "summary": {
            "total": 999,
            "downloaded": 999,
            "skipped": 999,
            "failed": 999,
        },
    }


class _ImmediateExecutor(FinsIngestionExecutor):
    """测试用同步执行器。"""

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """立即执行后台操作。

        Args:
            job_id: job ID。
            operation: 待执行操作。

        Returns:
            无。

        Raises:
            RuntimeError: operation 失败时由 operation 抛出。
        """

        del job_id
        operation()


@dataclass
class _RuntimeFakeDiscoveryClient:
    """runtime 接入测试用 discovery fake。"""

    temp_dir: Path
    provider: str
    company_id: str
    company_name: str
    title: str
    source_id: str
    download_calls: int = 0
    cancellation_checkpoints: list[Callable[[], None] | None] = field(default_factory=list)

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """返回固定公司元数据。

        Args:
            query: 下载查询。

        Returns:
            公司元数据。

        Raises:
            无。
        """

        return CnCompanyProfile(
            provider="hkexnews" if self.provider == "hkexnews" else "cninfo",
            company_id=self.company_id,
            company_name=self.company_name,
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """返回固定年度报告候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。
            cancellation_checkpoint: workflow-owned 无参取消检查点。

        Returns:
            候选报告 tuple。

        Raises:
            无。
        """

        del profile
        self.cancellation_checkpoints.append(cancellation_checkpoint)
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        fiscal_year = 2025 if query.market == "CN" else 2024
        filing_date = "2026-04-01" if query.market == "CN" else "2025-04-08"
        return (
            CnReportCandidate(
                provider="hkexnews" if query.market == "HK" else "cninfo",
                source_id=self.source_id,
                source_url=f"https://download.test/{self.source_id}.pdf",
                title=self.title,
                language="zh",
                filing_date=filing_date,
                fiscal_year=fiscal_year,
                period_projection=CnReportPeriodProjection(identity_period="FY", covered_periods=("FY",)),
                amended=False,
                content_length=len(_PDF_BYTES),
                etag=f'"{self.source_id}-v1"',
                last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
            ),
        )

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """返回内存 PDF 资产。

        Args:
            candidate: 远端候选。

        Returns:
            已下载 PDF 资产。

        Raises:
            无。
        """

        self.download_calls += 1
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_bytes=_PDF_BYTES,
            sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
            content_length=len(_PDF_BYTES),
            downloaded_at="2026-05-02T00:00:00+00:00",
        )


@dataclass
class _RuntimeFakeConversionRunner:
    """runtime 接入测试用 typed Docling runner。"""

    calls: int = 0

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回固定 Docling JSON 字节。

        Args:
            pdf_bytes: PDF 字节。
            stream_name: 流名称。
            config: 闭合转换配置。
            cancellation: canonical 取消 token。

        Returns:
            Docling JSON 字节。

        Raises:
            无。
        """

        del input_bytes, stream_name, config
        assert cancellation is not None
        assert cancellation.is_cancelled() is False
        self.calls += 1
        return DoclingConversionResult(
            json_bytes=_DOCLING_BYTES,
            size=len(_DOCLING_BYTES),
            sha256=hashlib.sha256(_DOCLING_BYTES).hexdigest(),
        )


class _RecordingPipeline(CnPipeline):
    """记录 adapter 传入 rebuild 标记的测试 pipeline。"""

    def __init__(self, *, workspace_root: Path) -> None:
        """初始化记录型 pipeline。

        Args:
            workspace_root: 测试工作区根目录。

        Returns:
            无。

        Raises:
            OSError: 默认仓储初始化失败时抛出。
        """

        super().__init__(
            workspace_root=workspace_root,
            cn_discovery_client=_RuntimeFakeDiscoveryClient(
                temp_dir=workspace_root,
                provider="cninfo",
                company_id="CNINFO:unused",
                company_name="unused",
                title="unused",
                source_id="unused",
            ),
            docling_converter=_RuntimeFakeConversionRunner(),
        )
        self.recorded_rebuild_values: list[bool] = []
        self.result_filings: list[JsonValue] = []

    def download(
        self,
        ticker: str,
        form_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: list[str] | None = None,
        *,
        start_is_explicit: bool,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> CnPipelineDownloadResult:
        """记录 rebuild 参数并返回确定性结果。

        Args:
            ticker: 股票代码。
            form_type: form 过滤。
            start_date: 开始日期。
            end_date: 结束日期。
            overwrite: 是否覆盖。
            rebuild: OLD 本地 rebuild 标记。
            ticker_aliases: ticker aliases。
            start_is_explicit: 起始日期是否来自调用方显式输入。
            cancel_checker: 可选取消检查器。

        Returns:
            pipeline 下载结果。

        Raises:
            无。
        """

        del ticker_aliases, start_is_explicit, cancel_checker
        self.recorded_rebuild_values.append(rebuild)
        form_values: list[JsonValue] = [] if form_type is None else [item for item in form_type.split(",")]
        filters: dict[str, JsonValue] = {
            "forms": form_values,
            "start_dates": {} if start_date is None else {"requested": start_date},
            "end_date": end_date,
            "overwrite": overwrite,
            "rebuild": rebuild,
        }
        return {
            "pipeline": "cn",
            "action": "download",
            "status": "ok",
            "ticker": ticker,
            "company_info": {},
            "filters": filters,
            "warnings": [],
            "notes": [],
            "filings": self.result_filings,
            "missing_periods": [],
            "summary": {
                "total": len(self.result_filings),
                "downloaded": len(self.result_filings),
                "skipped": 0,
                "failed": 0,
                "elapsed_ms": 0,
                "reused_downloads": 0,
                "converted": 0,
            },
        }

    async def download_stream(
        self,
        ticker: str,
        form_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: list[str] | None = None,
        *,
        start_is_explicit: bool,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncIterator[DownloadEvent]:
        """记录 rebuild 参数并返回确定性完成事件流。

        Args:
            ticker: 股票代码。
            form_type: form 过滤。
            start_date: 开始日期。
            end_date: 结束日期。
            overwrite: 是否覆盖。
            rebuild: OLD 本地 rebuild 标记。
            ticker_aliases: ticker aliases。
            start_is_explicit: 起始日期是否来自调用方显式输入。
            cancel_checker: 可选取消检查器。

        Yields:
            单个 pipeline completed 事件。

        Raises:
            无。
        """

        result = self.download(
            ticker=ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            rebuild=rebuild,
            ticker_aliases=ticker_aliases,
            start_is_explicit=start_is_explicit,
            cancel_checker=cancel_checker,
        )
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_COMPLETED,
            ticker=ticker,
            payload={"result": result},
        )


@dataclass(frozen=True)
class _RuntimeRepositorySet:
    """runtime 测试用仓储集合。"""

    workspace_root: Path
    batching_repository: FsBatchingRepository
    company_repository: FsCompanyMetaRepository
    source_repository: FsSourceDocumentRepository
    processed_repository: FsProcessedDocumentRepository
    blob_repository: FsDocumentBlobRepository
    filing_maintenance_repository: FsFilingMaintenanceRepository
    filing_upload_state_repository: FsFilingUploadStateRepository


def test_start_download_cninfo_persists_summary_and_source_document(tmp_path: Path) -> None:
    """runtime 应通过 CNInfo adapter 执行真实 workflow 并写入 source 仓储。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    runtime, cn_discovery, _hk_discovery, converter = _build_runtime_with_cn_hk_adapters(tmp_path)

    start = runtime.start_download(
        build_fins_download_request(
            ticker="600519",
            form_types=("FY",),
            start="2025-01-01",
            end="2026-12-31",
            overwrite_existing=True,
        )
    )
    record = runtime.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["downloaded_count"] == 1
    assert record.result_summary["written_document_ids"]
    assert cn_discovery.download_calls == 1
    assert converter.calls == 1
    written_ids = record.result_summary["written_document_ids"]
    assert isinstance(written_ids, list)
    document_id = str(written_ids[0])
    source_meta = runtime.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    locator = runtime.source_repository.get_source_document_locator(
        "600519",
        document_id,
        SourceKind.FILING,
    )
    assert source_meta["source_provider"] == "cninfo"
    assert source_meta["ingest_complete"] is True
    assert isinstance(locator, PurePosixPath)
    assert not locator.is_absolute()
    assert str(tmp_path) not in locator.as_posix()
    assert (
        runtime.source_repository.get_source_document_provenance(
            "600519",
            document_id,
            SourceKind.FILING,
        ).source_provider
        is FinsSourceProvider.CNINFO
    )


def test_start_download_hk_uses_ticker_resolved_hkexnews_adapter(tmp_path: Path) -> None:
    """HK ticker 应由 request owner 确定性解析到 HKEXNews adapter。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    runtime, _cn_discovery, hk_discovery, converter = _build_runtime_with_cn_hk_adapters(tmp_path)

    start = runtime.start_download(
        build_fins_download_request(
            ticker="0700",
            form_types=("FY",),
            start="2024-01-01",
            end="2025-12-31",
            overwrite_existing=True,
        )
    )
    record = runtime.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["downloaded_count"] == 1
    assert hk_discovery.download_calls == 1
    assert converter.calls == 1
    written_ids = record.result_summary["written_document_ids"]
    assert isinstance(written_ids, list)
    document_id = str(written_ids[0])
    source_meta = runtime.source_repository.get_source_meta("0700", document_id, SourceKind.FILING)
    assert source_meta["source_provider"] == "hkexnews"
    assert source_meta["company_id"] == "0700_HKEX"
    assert (
        runtime.source_repository.get_source_document_provenance(
            "0700",
            document_id,
            SourceKind.FILING,
        ).source_provider
        is FinsSourceProvider.HKEXNEWS
    )


def test_default_runtime_registers_cn_hk_download_adapters(tmp_path: Path) -> None:
    """DefaultFinsRuntime 应注册 CN/HK 显式来源和 auto fallback。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path).get_ingestion_runtime()

    assert (CN_DOWNLOAD_SOURCE, "CN") in runtime.download_adapters
    assert ("auto", "CN") in runtime.download_adapters
    assert (HK_DOWNLOAD_SOURCE, "HK") in runtime.download_adapters
    assert ("auto", "HK") in runtime.download_adapters
    assert runtime.download_adapters[(CN_DOWNLOAD_SOURCE, "CN")] is runtime.download_adapters[("auto", "CN")]
    assert runtime.download_adapters[(HK_DOWNLOAD_SOURCE, "HK")] is runtime.download_adapters[("auto", "HK")]


def test_default_runtime_injects_one_converter_into_all_fins_paths(tmp_path: Path) -> None:
    """默认装配必须让四类 Fins caller 观察同一 converter identity。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: converter 或独立 pipeline identity 漂移时抛出。
    """

    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path).get_ingestion_runtime()
    cn_adapter = runtime.download_adapters[(CN_DOWNLOAD_SOURCE, "CN")]
    hk_adapter = runtime.download_adapters[(HK_DOWNLOAD_SOURCE, "HK")]
    upload_runner = runtime.upload_runner
    assert isinstance(cn_adapter, CnDownloadAdapter)
    assert isinstance(hk_adapter, CnDownloadAdapter)
    assert isinstance(upload_runner, ProductionFinsUploadRunner)

    cn_download_pipeline = cn_adapter._pipeline
    hk_download_pipeline = hk_adapter._pipeline
    cn_upload_pipeline = upload_runner.cn_pipeline
    sec_upload_pipeline = upload_runner.sec_pipeline
    converter = cn_download_pipeline._docling_converter

    assert (
        len(
            {
                id(cn_download_pipeline),
                id(hk_download_pipeline),
                id(cn_upload_pipeline),
            }
        )
        == 3
    )
    assert hk_download_pipeline._docling_converter is converter
    assert cn_upload_pipeline._docling_converter is converter
    assert cn_upload_pipeline._upload_service._docling_converter is converter
    assert sec_upload_pipeline._upload_service._docling_converter is converter


def test_cn_hk_adapter_factories_use_source_specific_downloader_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CN/HK adapter factory 应分别使用各自 downloader 默认值。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 工具。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    repositories = _build_runtime_repositories(tmp_path)
    cn_sleep_seconds = 0.11
    cn_max_retries = 7
    hk_sleep_seconds = 0.22
    hk_max_retries = 9
    monkeypatch.setattr(cn_pipeline_module, "CNINFO_DEFAULT_SLEEP_SECONDS", cn_sleep_seconds)
    monkeypatch.setattr(cn_pipeline_module, "CNINFO_DEFAULT_MAX_RETRIES", cn_max_retries)
    monkeypatch.setattr(cn_pipeline_module, "HKEXNEWS_DEFAULT_SLEEP_SECONDS", hk_sleep_seconds)
    monkeypatch.setattr(cn_pipeline_module, "HKEXNEWS_DEFAULT_MAX_RETRIES", hk_max_retries)

    cn_adapter = cn_pipeline_module.build_cn_download_adapter(
        workspace_root=repositories.workspace_root,
        batching_repository=repositories.batching_repository,
        company_repository=repositories.company_repository,
        source_repository=repositories.source_repository,
        processed_repository=repositories.processed_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
        docling_converter=_RuntimeFakeConversionRunner(),
    )
    hk_adapter = cn_pipeline_module.build_hk_download_adapter(
        workspace_root=repositories.workspace_root,
        batching_repository=repositories.batching_repository,
        company_repository=repositories.company_repository,
        source_repository=repositories.source_repository,
        processed_repository=repositories.processed_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
        docling_converter=_RuntimeFakeConversionRunner(),
    )

    assert cn_adapter._pipeline.sleep_seconds == cn_sleep_seconds
    assert cn_adapter._pipeline.max_retries == cn_max_retries
    assert hk_adapter._pipeline.sleep_seconds == hk_sleep_seconds
    assert hk_adapter._pipeline.max_retries == hk_max_retries


def test_cn_adapter_routes_local_rebuild_to_existing_pipeline(tmp_path: Path) -> None:
    """adapter 应把 local rebuild 传给现有 ``CnPipeline`` host。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = _RecordingPipeline(workspace_root=tmp_path)
    adapter = CnDownloadAdapter(pipeline=pipeline, source=CN_DOWNLOAD_SOURCE, market="CN")

    adapter.download(
        FinsSourceDownloadAdapterRequest(
            normalized_ticker=NormalizedTicker(canonical="600519", market="CN", exchange="SSE", raw="600519"),
            source=FinsDownloadSource.CNINFO,
            form_types=("FY",),
            date_range=FinsDownloadDateRange(None, None, False, False),
            overwrite_existing=False,
            rebuild_local_artifacts=True,
            cancellation_checker=_NEVER_CANCELLED_CHECKER,
        )
    )

    assert pipeline.recorded_rebuild_values == [True]


@pytest.mark.parametrize(
    "failure",
    [
        FinsDownloadProviderError(
            source=FinsDownloadSource.CNINFO,
            transport_category=FinsDownloadTransportCategory.TIMEOUT,
            retryable=True,
            safe_message="巨潮来源请求超时",
        ),
        OSError("/Users/private/contact-canary/source.json"),
        RuntimeError("raw execution https://secret.invalid/payload"),
    ],
)
def test_cn_adapter_preserves_stream_failure_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    """generator -> stream -> collector -> adapter 不得替换异常 owner identity。"""

    pipeline = _RecordingPipeline(workspace_root=tmp_path)

    async def failing_stream(
        ticker: str,
        form_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: list[str] | None = None,
        *,
        start_is_explicit: bool,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncIterator[DownloadEvent]:
        """在 workflow async generator 边界抛出预构造异常。"""

        del (
            ticker,
            form_type,
            start_date,
            end_date,
            overwrite,
            rebuild,
            ticker_aliases,
            start_is_explicit,
            cancel_checker,
        )
        raise failure
        yield DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="unused")

    monkeypatch.setattr(pipeline, "download_stream", failing_stream)
    adapter = CnDownloadAdapter(pipeline=pipeline, source=CN_DOWNLOAD_SOURCE, market="CN")

    with pytest.raises(type(failure)) as exc_info:
        adapter.download(_cn_projection_request())
    assert exc_info.value is failure


def test_cn_adapter_rejects_legacy_failed_terminal_without_guessing_provider(
    tmp_path: Path,
) -> None:
    """legacy status=failed 必须 strict ValueError，不能猜成 provider UNKNOWN。"""

    result = _cn_projection_result([])
    result["status"] = "failed"

    with pytest.raises(ValueError, match="status 未封闭"):
        cn_pipeline_module._summary_from_pipeline_result(
            result,
            request=_cn_projection_request(),
            source_repository=FsSourceDocumentRepository(tmp_path),
        )


def test_cn_integrity_snapshot_has_separate_strict_projection_entry(tmp_path: Path) -> None:
    """失败快照只经私有状态入口投影，普通 ok 入口与坏行仍严格拒绝。

    Args:
        tmp_path: 隔离 source 仓储根。

    Returns:
        无。

    Raises:
        AssertionError: status 或 row 校验被绕过时抛出。
    """

    result = _cn_projection_result([{
        "document_id": "fil-failed",
        "status": "failed",
        "reason_code": "source_integrity_preflight",
        "form_type": "FY",
        "filing_date": "2025-04-01",
        "report_date": None,
        "covered_fiscal_periods": ["FY"],
    }])
    result["status"] = "integrity_failed"
    repository = FsSourceDocumentRepository(tmp_path)
    with pytest.raises(ValueError, match="status 未封闭"):
        cn_pipeline_module._summary_from_pipeline_result(
            result, request=_cn_projection_request(), source_repository=repository
        )
    summary = cn_pipeline_module._summary_from_integrity_abort(
        result, request=_cn_projection_request(), source_repository=repository
    )
    assert summary.failed_count == 1
    assert summary.discovered_count == 1
    result["status"] = "ok"
    with pytest.raises(ValueError, match="失败快照 status 未封闭"):
        cn_pipeline_module._summary_from_integrity_abort(
            result, request=_cn_projection_request(), source_repository=repository
        )
    result["status"] = "integrity_failed"
    result["filings"] = [{"document_id": "fil-bad", "status": "downloaded"}]
    with pytest.raises(ValueError):
        cn_pipeline_module._summary_from_integrity_abort(
            result, request=_cn_projection_request(), source_repository=repository
        )


@pytest.mark.parametrize("entry", ("normal", "integrity"))
@pytest.mark.parametrize(
    ("status", "normal_accepted", "integrity_accepted"),
    (
        ("ok", True, False),
        ("cancelled", True, False),
        ("integrity_failed", False, True),
        (" ok ", True, False),
        (" cancelled ", True, False),
        (" integrity_failed ", False, True),
        ("failed", False, False),
        ("error", False, False),
        ("unknown", False, False),
        ("OK", False, False),
        ("Cancelled", False, False),
        ("INTEGRITY_FAILED", False, False),
    ),
)
def test_cn_terminal_projection_preserves_entry_subsets_and_strip(
    tmp_path: Path,
    entry: Literal["normal", "integrity"],
    status: str,
    normal_accepted: bool,
    integrity_accepted: bool,
) -> None:
    """两个入口按独立字面量预期互拒交叉终态，并保留去空白与 JSON 形状。

    Args:
        tmp_path: 隔离真实仓储根。
        entry: 普通结果或完整性快照入口。
        status: 原协议文本或非法文本。
        normal_accepted: 普通入口的独立预期。
        integrity_accepted: 完整性入口的独立预期。

    Returns:
        无。

    Raises:
        AssertionError: 合法子集、文本处理或序列化形状漂移时抛出。
    """

    result = _cn_projection_result([])
    result["status"] = status
    serialized = json.dumps(result)
    assert json.loads(serialized) == result
    assert type(result["status"]) is str
    project = (
        cn_pipeline_module._summary_from_pipeline_result if entry == "normal"
        else cn_pipeline_module._summary_from_integrity_abort
    )
    accepted = normal_accepted if entry == "normal" else integrity_accepted
    repository = FsSourceDocumentRepository(tmp_path)
    if accepted:
        summary = project(result, request=_cn_projection_request(), source_repository=repository)
        assert summary.discovered_count == 0
        assert summary.document_rows == ()
        assert summary.missing_periods == ()
    else:
        with pytest.raises(ValueError, match="status 未封闭"):
            project(result, request=_cn_projection_request(), source_repository=repository)
    assert json.dumps(result) == serialized


@pytest.mark.parametrize("entry", ("normal", "integrity"))
@pytest.mark.parametrize(
    ("present", "status"),
    ((False, None), (True, None), (True, 1), (True, ""), (True, " \t\n")),
)
def test_cn_terminal_projection_rejects_missing_and_nontext_status(
    tmp_path: Path,
    entry: Literal["normal", "integrity"],
    present: bool,
    status: JsonValue,
) -> None:
    """两个入口都在业务摘要投影前拒绝缺失、非文本或空白终态。

    Args:
        tmp_path: 隔离真实仓储根。
        entry: 待验证入口。
        present: 是否保留 status 字段。
        status: 待验证非法值。

    Returns:
        无。

    Raises:
        AssertionError: 非法终态被接受时抛出。
    """

    result = _cn_projection_result([])
    if present:
        result["status"] = status
    else:
        del result["status"]
    project = (
        cn_pipeline_module._summary_from_pipeline_result if entry == "normal"
        else cn_pipeline_module._summary_from_integrity_abort
    )
    with pytest.raises(ValueError, match="必填文本字段: status"):
        project(result, request=_cn_projection_request(), source_repository=FsSourceDocumentRepository(tmp_path))


@pytest.mark.parametrize("entry", ("normal", "integrity"))
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("ticker", "0700"),
        ("filters", None),
        ("missing_periods", [""]),
        ("filings", ["invalid"]),
        ("filings", [{"document_id": "fil-bad", "status": "downloaded"}]),
        ("filings", [{
            "document_id": "fil-bad", "status": "skipped", "form_type": "FY",
            "reason_code": "already_downloaded_complete", "filing_date": "2025-04-01",
            "report_date": None, "covered_fiscal_periods": [],
        }]),
        ("filings", [{
            "document_id": "fil-unpublished", "status": "downloaded", "form_type": "FY",
            "filing_date": "2025-04-01", "report_date": None, "covered_fiscal_periods": ["FY"],
        }]),
    ),
)
def test_cn_legal_terminal_does_not_bypass_summary_validation(
    tmp_path: Path,
    entry: Literal["normal", "integrity"],
    field_name: str,
    invalid_value: JsonValue,
) -> None:
    """合法终态不能绕过身份、筛选、行、覆盖财期或真实 locator 校验。

    Args:
        tmp_path: 隔离真实空仓储根。
        entry: 待验证入口。
        field_name: 要破坏的摘要字段。
        invalid_value: 非法业务字段值。

    Returns:
        无。

    Raises:
        AssertionError: 合法终态放宽其它契约时抛出。
    """

    result = _cn_projection_result([])
    result["status"] = "ok" if entry == "normal" else "integrity_failed"
    result[field_name] = invalid_value
    project = (
        cn_pipeline_module._summary_from_pipeline_result if entry == "normal"
        else cn_pipeline_module._summary_from_integrity_abort
    )
    with pytest.raises((ValueError, FileNotFoundError)):
        project(result, request=_cn_projection_request(), source_repository=FsSourceDocumentRepository(tmp_path))


@pytest.mark.parametrize("invalid_missing_periods", [None, "FY", [""]])
def test_cn_rebuild_projection_requires_exact_missing_periods_field(
    tmp_path: Path,
    invalid_missing_periods: JsonValue,
) -> None:
    """rebuild 也必须严格消费 producer 的 list-of-non-empty-text 字段。"""

    request = FinsSourceDownloadAdapterRequest(
        normalized_ticker=NormalizedTicker(
            canonical="600519",
            market="CN",
            exchange="SSE",
            raw="600519",
        ),
        source=FinsDownloadSource.CNINFO,
        form_types=("FY",),
        date_range=FinsDownloadDateRange(None, None, False, False),
        overwrite_existing=False,
        rebuild_local_artifacts=True,
        cancellation_checker=_NEVER_CANCELLED_CHECKER,
    )
    result = _cn_projection_result([])
    result["status"] = "ok"
    filters = result["filters"]
    assert isinstance(filters, dict)
    filters["rebuild"] = True
    if invalid_missing_periods is None:
        del result["missing_periods"]
    else:
        result["missing_periods"] = invalid_missing_periods

    with pytest.raises(ValueError, match="missing_periods"):
        cn_pipeline_module._summary_from_pipeline_result(
            result,
            request=request,
            source_repository=FsSourceDocumentRepository(tmp_path),
        )


def test_cn_adapter_rejects_invalid_binding_and_request_identity(tmp_path: Path) -> None:
    """CN/HK adapter 必须拒绝非法装配、market 与 source 错配。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非法 adapter identity 未 fail closed 时抛出。
    """

    pipeline = _RecordingPipeline(workspace_root=tmp_path)
    with pytest.raises(ValueError, match="非法 CN/HK 下载 adapter 组合"):
        CnDownloadAdapter(pipeline=pipeline, source="sec", market="CN")

    adapter = CnDownloadAdapter(pipeline=pipeline, source=CN_DOWNLOAD_SOURCE, market="CN")
    with pytest.raises(ValueError, match="market 不匹配"):
        adapter.download(
            FinsSourceDownloadAdapterRequest(
                normalized_ticker=NormalizedTicker(
                    canonical="0700",
                    market="HK",
                    exchange="HKEX",
                    raw="0700.HK",
                ),
                source=FinsDownloadSource.HKEXNEWS,
                form_types=(),
                date_range=FinsDownloadDateRange(None, None, False, False),
                overwrite_existing=False,
                rebuild_local_artifacts=False,
                cancellation_checker=_NEVER_CANCELLED_CHECKER,
            )
        )
    with pytest.raises(ValueError, match="来源不匹配"):
        adapter.download(
            FinsSourceDownloadAdapterRequest(
                normalized_ticker=NormalizedTicker(
                    canonical="600519",
                    market="CN",
                    exchange="SSE",
                    raw="600519",
                ),
                source=FinsDownloadSource.HKEXNEWS,
                form_types=(),
                date_range=FinsDownloadDateRange(None, None, False, False),
                overwrite_existing=False,
                rebuild_local_artifacts=False,
                cancellation_checker=_NEVER_CANCELLED_CHECKER,
            )
        )


@pytest.mark.parametrize(
    ("result", "error_pattern"),
    [
        (_cn_projection_result("invalid"), "filings 字段必须是列表"),
        (_cn_projection_result(["invalid"]), r"filings\[0\] 必须是对象"),
        (
            _cn_projection_result(
                [
                    {
                        "document_id": "fil-unknown",
                        "status": "provider_new_status",
                        "form_type": "FY",
                        "filing_date": "2024-08-01",
                        "report_date": "2023-12-31",
                        "covered_fiscal_periods": ["FY"],
                    }
                ]
            ),
            "status 未封闭",
        ),
    ],
)
def test_cn_adapter_summary_projection_rejects_invalid_shapes(
    tmp_path: Path,
    result: dict[str, JsonValue],
    error_pattern: str,
) -> None:
    """CN/HK adapter summary projection 必须拒绝非法结果 shape。

    Args:
        tmp_path: source repository 使用的临时根目录。
        result: source workflow 返回的非法结果。
        error_pattern: 预期错误文本。

    Returns:
        无。

    Raises:
        AssertionError: 非法结果未 fail closed 时抛出。
    """

    with pytest.raises(ValueError, match=error_pattern):
        cn_pipeline_module._summary_from_pipeline_result(
            result,
            request=_cn_projection_request(),
            source_repository=FsSourceDocumentRepository(tmp_path),
        )


def test_cn_adapter_summary_counts_are_derived_from_typed_rows(tmp_path: Path) -> None:
    """adapter 必须忽略 raw summary counts 并从 typed rows 派生计数。

    Args:
        tmp_path: source repository 使用的临时根目录。

    Returns:
        无。

    Raises:
        AssertionError: adapter projection 发生语义漂移时抛出。
    """

    summary = cn_pipeline_module._summary_from_pipeline_result(
        _cn_projection_result(
            [
                {
                    "document_id": "fil-existing",
                    "status": "skipped",
                    "reason_code": "already_downloaded_complete",
                    "form_type": "FY",
                    "filing_date": "2024-08-01",
                    "report_date": "2023-12-31",
                    "covered_fiscal_periods": ["FY"],
                }
            ]
        ),
        request=_cn_projection_request(),
        source_repository=FsSourceDocumentRepository(tmp_path),
    )
    assert cn_pipeline_module._form_type_from_adapter_request(()) is None
    assert summary.discovered_count == 1
    assert summary.skipped_count == 1
    assert summary.downloaded_count == 0
    assert summary.failed_count == 0
    assert summary.written_document_ids == ()
    assert summary.document_rows[0].covered_fiscal_periods == ("FY",)


@pytest.mark.parametrize(
    "coverage_value",
    (
        None,
        "FY",
        [],
        ["FY", "FY"],
        ["Q4", "FY"],
        ["FY"],
    ),
)
def test_cn_adapter_rejects_invalid_required_coverage(
    tmp_path: Path,
    coverage_value: JsonValue | None,
) -> None:
    """CN adapter 对缺失、非数组、空、重复、乱序或不含 identity 的 coverage fail closed。

    Args:
        tmp_path: source repository 临时根目录。
        coverage_value: 缺失或非法 coverage。

    Returns:
        无。

    Raises:
        AssertionError: 非法 workflow coverage 被接纳时抛出。
    """

    row: dict[str, JsonValue] = {
        "document_id": "fil-invalid-coverage",
        "status": "skipped",
        "reason_code": "already_downloaded_complete",
        "form_type": "Q4",
        "filing_date": "2025-01-01",
        "report_date": None,
    }
    if coverage_value is not None:
        row["covered_fiscal_periods"] = coverage_value

    with pytest.raises(ValueError, match="covered_fiscal_periods"):
        cn_pipeline_module._summary_from_pipeline_result(
            _cn_projection_result([row]),
            request=_cn_projection_request(),
            source_repository=FsSourceDocumentRepository(tmp_path),
        )


def test_cn_pipeline_upload_status_preserves_non_uploaded_state() -> None:
    """CN pipeline 上传状态投影应保留非 uploaded 终态。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非 uploaded 状态被意外改写时抛出。
    """

    assert cn_pipeline_module._resolve_upload_status("cancelled") == "cancelled"


@pytest.mark.parametrize(
    ("source", "market", "ticker", "exchange"),
    [
        (CN_DOWNLOAD_SOURCE, "CN", "600519", "SSE"),
        (HK_DOWNLOAD_SOURCE, "HK", "0700", "HKEX"),
    ],
)
def test_cn_hk_adapter_local_rebuild_does_not_mutate_processed_documents(
    tmp_path: Path,
    source: str,
    market: CnMarketKind,
    ticker: str,
    exchange: Exchange,
) -> None:
    """CN/HK local rebuild 应只改 source，不得标记 processed 重处理。"""

    pipeline = _RecordingPipeline(workspace_root=tmp_path)
    document_id = "fil_cn_rebuild"
    filing_payload: dict[str, JsonValue] = {
        "document_id": document_id,
        "status": "skipped",
        "reason_code": "already_downloaded_complete",
        "form_type": "FY",
        "filing_date": "2024-08-01",
        "report_date": "2023-12-31",
        "covered_fiscal_periods": ["FY"],
    }
    pipeline.result_filings = [filing_payload]
    setup_batch = pipeline.batching_repository.begin_batch(ticker)
    pipeline.processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            source_kind=SourceKind.FILING.value,
            form_type="FY",
            meta={"reprocess_required": False},
            sections=[],
            tables=[],
        ),
        batch=setup_batch,
    )
    pipeline.batching_repository.commit_batch(setup_batch)
    adapter = CnDownloadAdapter(pipeline=pipeline, source=source, market=market)
    request_source = FinsDownloadSource.CNINFO if market == "CN" else FinsDownloadSource.HKEXNEWS

    summary = adapter.download(
        FinsSourceDownloadAdapterRequest(
            normalized_ticker=NormalizedTicker(canonical=ticker, market=market, exchange=exchange, raw=ticker),
            source=request_source,
            form_types=("FY",),
            date_range=FinsDownloadDateRange(None, None, False, False),
            overwrite_existing=False,
            rebuild_local_artifacts=True,
            cancellation_checker=_NEVER_CANCELLED_CHECKER,
        )
    )

    processed_meta = pipeline.processed_repository.get_processed_meta(ticker, document_id)

    assert pipeline.recorded_rebuild_values == [True]
    assert summary.persisted_summary is not None
    assert summary.persisted_summary.missing_periods == ()
    assert processed_meta["reprocess_required"] is False


def _build_runtime_with_cn_hk_adapters(
    tmp_path: Path,
) -> tuple[
    FinsIngestionRuntime,
    _RuntimeFakeDiscoveryClient,
    _RuntimeFakeDiscoveryClient,
    _RuntimeFakeConversionRunner,
]:
    """构造带 CN/HK fake adapter 的 runtime。

    Args:
        tmp_path: 临时目录。

    Returns:
        runtime、CN discovery fake、HK discovery fake、converter fake。

    Raises:
        OSError: FS 仓储初始化失败时抛出。
    """

    repositories = _build_runtime_repositories(tmp_path)
    runner = _RuntimeFakeConversionRunner()
    cn_discovery = _RuntimeFakeDiscoveryClient(
        temp_dir=tmp_path,
        provider="cninfo",
        company_id="CNINFO:runtime-cn",
        company_name="贵州茅台",
        title="贵州茅台：2025年年度报告",
        source_id="cn-runtime-a1",
    )
    hk_discovery = _RuntimeFakeDiscoveryClient(
        temp_dir=tmp_path,
        provider="hkexnews",
        company_id="HKEX:7609",
        company_name="騰訊控股",
        title="ANNUAL REPORT 2024",
        source_id="hk-runtime-a1",
    )
    pipeline = CnPipeline(
        workspace_root=repositories.workspace_root,
        batching_repository=repositories.batching_repository,
        company_repository=repositories.company_repository,
        source_repository=repositories.source_repository,
        processed_repository=repositories.processed_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
        filing_upload_state_repository=repositories.filing_upload_state_repository,
        cn_discovery_client=cn_discovery,
        hk_discovery_client=hk_discovery,
        docling_converter=runner,
    )
    runtime = FinsIngestionRuntime.create(
        batching_repository=repositories.batching_repository,
        source_repository=repositories.source_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
        filing_upload_state_repository=repositories.filing_upload_state_repository,
        processed_repository=repositories.processed_repository,
        processor_registry=ProcessorRegistry(),
        job_store=FsFinsIngestionJobStore.from_workspace_root(repositories.workspace_root),
        executor=_ImmediateExecutor(),
        download_adapters={
            (CN_DOWNLOAD_SOURCE, "CN"): CnDownloadAdapter(
                pipeline=pipeline,
                source=CN_DOWNLOAD_SOURCE,
                market="CN",
            ),
            ("auto", "CN"): CnDownloadAdapter(
                pipeline=pipeline,
                source=CN_DOWNLOAD_SOURCE,
                market="CN",
            ),
            (HK_DOWNLOAD_SOURCE, "HK"): CnDownloadAdapter(
                pipeline=pipeline,
                source=HK_DOWNLOAD_SOURCE,
                market="HK",
            ),
            ("auto", "HK"): CnDownloadAdapter(
                pipeline=pipeline,
                source=HK_DOWNLOAD_SOURCE,
                market="HK",
            ),
        },
    )
    return runtime, cn_discovery, hk_discovery, runner


def _build_runtime_repositories(tmp_path: Path) -> _RuntimeRepositorySet:
    """构造 runtime 测试用文件系统仓储集合。

    Args:
        tmp_path: 临时目录。

    Returns:
        已初始化的仓储集合。

    Raises:
        OSError: FS 仓储初始化失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    return _RuntimeRepositorySet(
        workspace_root=workspace_root,
        batching_repository=FsBatchingRepository(workspace_root, repository_set=repository_set),
        company_repository=FsCompanyMetaRepository(workspace_root, repository_set=repository_set),
        source_repository=FsSourceDocumentRepository(workspace_root, repository_set=repository_set),
        processed_repository=FsProcessedDocumentRepository(workspace_root, repository_set=repository_set),
        blob_repository=FsDocumentBlobRepository(workspace_root, repository_set=repository_set),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        filing_upload_state_repository=FsFilingUploadStateRepository(
            workspace_root,
            repository_set=repository_set,
        ),
    )


@pytest.mark.parametrize("entry", ("direct", "job"))
def test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    """fresh company 意图经真实 commit 与 whole-tree 校验抛 typed，保持零候选请求事实。

    Args:
        tmp_path: 独立文件系统工作区。
        monkeypatch: 只在真实提交前注入 staging 外来条目。
        entry: direct 或后台 job 入口。

    Returns:
        无。

    Raises:
        AssertionError: company 意图、真实校验、pre-swap 或公开摘要不符时抛出。
    """

    runtime, discovery, _hk_discovery, _converter = _build_runtime_with_cn_hk_adapters(tmp_path)
    adapter = runtime.download_adapters[(CN_DOWNLOAD_SOURCE, "CN")]
    assert isinstance(adapter, CnDownloadAdapter)
    batching = adapter._pipeline.batching_repository
    assert isinstance(batching, FsBatchingRepository)
    core = batching._repository_set.core
    real_commit = batching.commit_batch
    real_validate = core._validate_complete_source_tree
    staged_intents: list[bool] = []
    validation_visits: list[bool] = []
    target_paths: list[Path] = []

    def validate_real_tree(state: _ActiveBatchState) -> None:
        """观察并委托真实 whole-tree 预检。

        Args:
            state: storage 当前活动 batch。

        Returns:
            无。

        Raises:
            SourceIntegrityPreflightError: 原 storage 校验拒绝外来条目时透传。
        """

        validation_visits.append(True)
        real_validate(state)

    def commit_with_staging_stray(batch: BatchToken) -> CompanyMetaCommitOutcome | None:
        """确认 company mutation 已 stage 后把外来文件交给真实 commit。

        Args:
            batch: workflow 转交的真实批次。

        Returns:
            真实 commit 的结果。

        Raises:
            SourceIntegrityPreflightError: 真实 whole-tree 预检拒绝外来条目。
        """

        state = core._resolve_active_batch(batch, batch.ticker)
        assert state.company_meta_intent is not None
        staged_intents.append(True)
        target_paths.append(state.target_ticker_dir)
        source_root = state.staging_ticker_dir / "filings"
        source_root.mkdir(parents=True, exist_ok=True)
        (source_root / "undeclared-company.bin").write_bytes(b"foreign")
        return real_commit(batch)

    monkeypatch.setattr(core, "_validate_complete_source_tree", validate_real_tree)
    monkeypatch.setattr(batching, "commit_batch", commit_with_staging_stray)
    request = build_fins_download_request(
        ticker="600519", form_types=("FY",), start="2025-01-01", end="2026-12-31"
    )
    if entry == "direct":
        async def collect() -> list[FinsEvent]:
            """收集真实 direct 流到唯一终态。

            Args:
                无。

            Returns:
                direct 事件列表。

            Raises:
                无。
            """

            return [event async for event in runtime.download(request)]

        events = asyncio.run(collect())
        results = [event.result for event in events if event.event_type is FinsEventType.RESULT]
        assert len(results) == 1
        result = results[0]
        assert result is not None
        assert result.status is FinsResultStatus.FAILURE
        assert result.download is not None
        assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.FAILED
        assert result.download.discovered_count == 0
        assert result.download.document_rows == ()
        assert result.failure is not None
        assert result.failure.reason_code is FinsDownloadFailureReason.UNSAFE_PUBLICATION
        assert result.failure.safe_message == "本地来源完整性预检失败"
    else:
        start = runtime.start_download(request)
        record = runtime.read_job(start.job_id)
        assert record.status is FinsIngestionJobStatus.FAILED
        expected = ingestion_runtime_module._empty_download_summary_from_request(
            request, terminal_disposition=FinsDownloadTerminalDisposition.FAILED
        )
        assert record.result_summary == expected.to_json_summary()
        assert record.failure_summary["message"] == "本地来源完整性预检失败"
    assert staged_intents == [True]
    assert validation_visits == [True]
    assert all(not path.exists() for path in target_paths)
    assert discovery.download_calls == 0


@pytest.mark.parametrize("entry", ("direct", "job"))
def test_cn_real_phase_b_abort_keeps_published_document_in_result_and_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    """真实 CN adapter 在第二候选 Phase B typed 中止后保留第一份已发布文档。

    Args:
        tmp_path: 独立仓储根。
        monkeypatch: 在第二候选下载回调放置未声明文件。
        entry: direct 或后台 job 入口。

    Returns:
        无。

    Raises:
        AssertionError: 已确认文档与失败投影不一致时抛出。
    """

    runtime, discovery, _hk_discovery, _converter = _build_runtime_with_cn_hk_adapters(tmp_path)
    original_list = discovery.list_report_candidates
    original_download = discovery.download_report_pdf
    second_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    injected: list[Path] = []

    def list_two(
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """返回两个不同文档 ID 的候选。

        Args:
            query: 来源查询。
            profile: 公司 profile。
            cancellation_checkpoint: 取消检查点。

        Returns:
            两个候选。

        Raises:
            无。
        """

        first = original_list(query, profile, cancellation_checkpoint=cancellation_checkpoint)[0]
        return (first, replace(first, source_id="cn-runtime-b2", fiscal_year=2024, filing_date="2025-04-01"))

    def download_second_with_stray(candidate: CnReportCandidate) -> DownloadedReportAsset:
        """在第二候选 Phase A 后创建未发布 exact target。

        Args:
            candidate: 当前候选。

        Returns:
            fake PDF 资产。

        Raises:
            OSError: 文件创建失败时抛出。
        """

        if candidate.source_id == "cn-runtime-b2":
            source_root = tmp_path / "workspace" / "portfolio" / "600519" / "filings"
            assert source_root.is_dir()
            target = _identity_directory_path(source_root, _FILING_IDENTITY_NAMESPACE, second_id)
            assert not target.exists()
            target.mkdir()
            (target / "undeclared.bin").write_bytes(b"foreign")
            injected.append(target)
        return original_download(candidate)

    monkeypatch.setattr(discovery, "list_report_candidates", list_two)
    monkeypatch.setattr(discovery, "download_report_pdf", download_second_with_stray)
    request = build_fins_download_request(
        ticker="600519", form_types=("FY",), start="2025-01-01", end="2026-12-31"
    )
    if entry == "direct":
        async def collect() -> list[FinsEvent]:
            """收集 direct 流中的唯一失败终态。

            Args:
                无。

            Returns:
                direct 事件列表。

            Raises:
                无。
            """

            return [event async for event in runtime.download(request)]

        events = asyncio.run(collect())
        results = [event.result for event in events if event.event_type is FinsEventType.RESULT]
        assert len(results) == 1
        result = results[0]
        assert result is not None
        assert result.status is FinsResultStatus.FAILURE
        assert result.download is not None
        assert result.download.discovered_count == 2
        assert result.download.downloaded_count == 1
        assert result.download.failed_count == 1
        assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.PARTIAL_FAILURE
        assert result.failure is not None
        assert result.failure.reason_code is FinsDownloadFailureReason.UNSAFE_PUBLICATION
    else:
        start = runtime.start_download(request)
        record = runtime.read_job(start.job_id)
        assert record.status is FinsIngestionJobStatus.FAILED
        assert record.result_summary["discovered_count"] == 2
        assert record.result_summary["downloaded_count"] == 1
        assert record.result_summary["failed_count"] == 1
        assert record.result_summary["terminal_disposition"] == "partial_failure"
        assert record.failure_summary["message"] == "本地来源完整性预检失败"
    assert injected
    first_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False
    )
    assert runtime.source_repository.get_source_meta("600519", first_id, SourceKind.FILING)


@pytest.mark.parametrize("entry", ("direct", "job"))
def test_hk_real_commit_preflight_uses_same_partial_failure_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    """HK adapter 共享 CN workflow 的真实 commit typed 与 direct/job 文档守恒。

    Args:
        tmp_path: 独立仓储根。
        monkeypatch: 在第二份 HK 候选 Phase A 后放置非点号 root 文件。
        entry: direct 或后台 job 入口。

    Returns:
        无。

    Raises:
        AssertionError: HK 路由或已确认文档摘要不一致时抛出。
    """

    runtime, _cn_discovery, discovery, _converter = _build_runtime_with_cn_hk_adapters(tmp_path)
    original_list = discovery.list_report_candidates
    original_download = discovery.download_report_pdf
    injected: list[Path] = []

    def list_two(
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """给 HK 来源增加第二个不同年份的候选。

        Args:
            query: HK 来源查询。
            profile: 公司 profile。
            cancellation_checkpoint: 取消检查点。

        Returns:
            两个候选。

        Raises:
            无。
        """

        first = original_list(query, profile, cancellation_checkpoint=cancellation_checkpoint)[0]
        return (first, replace(first, source_id="hk-runtime-b2", fiscal_year=2023, filing_date="2024-04-08"))

    def root_stray_after_first(candidate: CnReportCandidate) -> DownloadedReportAsset:
        """在第二次真实 commit 的 whole-tree 校验前创建 root 外来文件。

        Args:
            candidate: 当前 HK 候选。

        Returns:
            fake PDF 资产。

        Raises:
            OSError: 文件创建失败时抛出。
        """

        if candidate.source_id == "hk-runtime-b2":
            root = tmp_path / "workspace" / "portfolio" / "0700" / "filings"
            assert root.is_dir()
            rogue = root / "foreign-hk-commit.bin"
            rogue.write_bytes(b"foreign")
            injected.append(rogue)
        return original_download(candidate)

    monkeypatch.setattr(discovery, "list_report_candidates", list_two)
    monkeypatch.setattr(discovery, "download_report_pdf", root_stray_after_first)
    request = build_fins_download_request(
        ticker="0700", form_types=("FY",), start="2024-01-01", end="2026-12-31"
    )
    if entry == "direct":
        async def collect() -> list[FinsEvent]:
            """收集 HK direct 流。

            Args:
                无。

            Returns:
                direct 事件列表。

            Raises:
                无。
            """

            return [event async for event in runtime.download(request)]

        events = asyncio.run(collect())
        results = [event.result for event in events if event.event_type is FinsEventType.RESULT]
        assert len(results) == 1
        result = results[0]
        assert result is not None and result.status is FinsResultStatus.FAILURE
        assert result.download is not None
        assert result.download.source is FinsDownloadSource.HKEXNEWS
        assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.PARTIAL_FAILURE
        assert result.download.discovered_count == 2
        assert result.download.downloaded_count == result.download.failed_count == 1
        assert result.failure is not None
        assert result.failure.reason_code is FinsDownloadFailureReason.UNSAFE_PUBLICATION
        published_id = result.download.document_rows[0].document_id
    else:
        start = runtime.start_download(request)
        record = runtime.read_job(start.job_id)
        assert record.status is FinsIngestionJobStatus.FAILED
        assert record.result_summary["terminal_disposition"] == "partial_failure"
        assert record.result_summary["discovered_count"] == 2
        assert record.result_summary["downloaded_count"] == record.result_summary["failed_count"] == 1
        assert record.failure_summary["message"] == "本地来源完整性预检失败"
        written_ids = record.result_summary["written_document_ids"]
        assert isinstance(written_ids, list) and len(written_ids) == 1
        published_id = str(written_ids[0])
    assert injected
    assert runtime.source_repository.get_source_meta("0700", published_id, SourceKind.FILING)


@pytest.mark.parametrize("entry", ("direct", "job"))
def test_cn_post_repair_abort_then_same_request_skips_complete_source_and_downloads_next(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    """真实 post-repair 中止后，同请求重跑跳过完整来源并处理此前未开始的候选。

    Args:
        tmp_path: 独立真实仓储根。
        monkeypatch: 在 post-repair 枚举前放置 root 外来文件。
        entry: direct 或后台 job 入口。

    Returns:
        无。

    Raises:
        AssertionError: 文档发布、原公司字节或整体终态不一致时抛出。
    """

    runtime, discovery, _hk_discovery, _converter = _build_runtime_with_cn_hk_adapters(tmp_path)
    request = build_fins_download_request(
        ticker="600519", form_types=("FY",), start="2025-01-01", end="2026-12-31"
    )
    first = runtime.start_download(request)
    published = runtime.read_job(first.job_id)
    assert published.status is FinsIngestionJobStatus.SUCCEEDED
    written_ids = published.result_summary["written_document_ids"]
    assert isinstance(written_ids, list) and len(written_ids) == 1
    document_id = str(written_ids[0])
    second_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    original_candidates = discovery.list_report_candidates
    original_download = discovery.download_report_pdf
    downloaded_sources: list[str] = []

    def list_two(
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """从中止请求起提供原候选及尚未发布的第二候选。

        Args:
            query: 来源查询。
            profile: 公司资料。
            cancellation_checkpoint: 取消检查点。

        Returns:
            两个不同财年的候选。

        Raises:
            无。
        """

        first_candidate = original_candidates(query, profile, cancellation_checkpoint=cancellation_checkpoint)[0]
        return (
            first_candidate,
            replace(first_candidate, source_id="cn-runtime-b2", fiscal_year=2024, filing_date="2025-04-01"),
        )

    def record_download(candidate: CnReportCandidate) -> DownloadedReportAsset:
        """观察真实 workflow 是否调用远端传输。

        Args:
            candidate: 待下载候选。

        Returns:
            fake transport 的 PDF 资产。

        Raises:
            无。
        """

        downloaded_sources.append(candidate.source_id)
        return original_download(candidate)

    monkeypatch.setattr(discovery, "list_report_candidates", list_two)
    monkeypatch.setattr(discovery, "download_report_pdf", record_download)
    locator = runtime.source_repository.get_source_document_locator("600519", document_id, SourceKind.FILING)
    pdf_path = tmp_path / "workspace" / locator / f"{document_id}.pdf"
    original_pdf = pdf_path.read_bytes()
    pdf_path.write_bytes(original_pdf + b"-repair-needed")
    source_root = tmp_path / "workspace" / "portfolio" / "600519" / "filings"
    second_target = _identity_directory_path(source_root, _FILING_IDENTITY_NAMESPACE, second_id)
    assert not second_target.exists()
    company_path = tmp_path / "workspace" / "portfolio" / "600519" / "meta.json"
    old_company = company_path.read_bytes()
    source = runtime.source_repository
    assert isinstance(source, FsSourceDocumentRepository)
    original_list = source.list_source_integrity
    calls: list[int] = []

    def inject_post_repair(ticker: str) -> tuple[SourceIntegrityClassification, ...]:
        """第二次真实 whole-kind 枚举前让 root 产生不可归属事实。

        Args:
            ticker: 当前 ticker。

        Returns:
            真实仓储 inventory。

        Raises:
            SourceIntegrityPreflightError: post-repair root 非法时透传。
        """

        calls.append(1)
        if len(calls) == 2:
            (tmp_path / "workspace" / "portfolio" / "600519" / "filings" / "foreign-post-repair.bin").write_bytes(
                b"foreign"
            )
        return original_list(ticker)

    monkeypatch.setattr(source, "list_source_integrity", inject_post_repair)
    async def collect() -> list[FinsEvent]:
        """收集同一请求在 direct 入口的事件。

        Args:
            无。

        Returns:
            direct 事件列表。

        Raises:
            无。
        """

        return [event async for event in runtime.download(request)]

    if entry == "direct":
        events = asyncio.run(collect())
        results = [event.result for event in events if event.event_type is FinsEventType.RESULT]
        assert len(results) == 1
        result = results[0]
        assert result is not None and result.status is FinsResultStatus.FAILURE
        assert result.download is not None
        assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.SUCCEEDED
        assert result.download.discovered_count == result.download.downloaded_count == 1
        assert result.download.failed_count == 0
        assert result.download.document_rows[0].document_id == document_id
        assert result.failure is not None
        assert result.failure.reason_code is FinsDownloadFailureReason.UNSAFE_PUBLICATION
    else:
        start = runtime.start_download(request)
        record = runtime.read_job(start.job_id)
        assert record.status is FinsIngestionJobStatus.FAILED
        assert record.result_summary["terminal_disposition"] == "succeeded"
        assert record.result_summary["discovered_count"] == record.result_summary["downloaded_count"] == 1
        assert record.result_summary["failed_count"] == 0
        assert record.result_summary["written_document_ids"] == [document_id]
        assert record.failure_summary["message"] == "本地来源完整性预检失败"
    assert len(calls) == 2
    assert downloaded_sources == ["cn-runtime-a1"]
    assert not second_target.exists()
    assert pdf_path.read_bytes() == original_pdf
    assert company_path.read_bytes() == old_company

    # 只清除外来 mutation；同一 request 再经真实 adapter/runtime 与同仓 FS 执行。
    (source_root / "foreign-post-repair.bin").unlink()
    downloaded_sources.clear()
    if entry == "direct":
        retry_events = asyncio.run(collect())
        retry_results = [event.result for event in retry_events if event.event_type is FinsEventType.RESULT]
        assert len(retry_results) == 1
        retry = retry_results[0]
        assert retry is not None and retry.status is FinsResultStatus.SUCCESS
        assert retry.download is not None
        summary = retry.download
        assert summary.terminal_disposition is FinsDownloadTerminalDisposition.SUCCEEDED
        assert summary.discovered_count == 2
        assert (summary.downloaded_count, summary.skipped_count, summary.rejected_count, summary.failed_count) == (
            1, 1, 0, 0
        )
        assert [(row.document_id, row.disposition.value) for row in summary.document_rows] == [
            (document_id, "skipped"), (second_id, "downloaded")
        ]
    else:
        retry_start = runtime.start_download(request)
        retry_record = runtime.read_job(retry_start.job_id)
        assert retry_record.status is FinsIngestionJobStatus.SUCCEEDED
        retry_summary = retry_record.result_summary
        assert retry_summary["terminal_disposition"] == "succeeded"
        assert retry_summary["discovered_count"] == 2
        assert (
            retry_summary["downloaded_count"], retry_summary["skipped_count"],
            retry_summary["rejected_count"], retry_summary["failed_count"],
        ) == (1, 1, 0, 0)
        assert retry_summary["written_document_ids"] == [second_id]
    assert downloaded_sources == ["cn-runtime-b2"]
    assert pdf_path.read_bytes() == original_pdf
    assert source.get_source_meta("600519", document_id, SourceKind.FILING)
    assert source.get_source_meta("600519", second_id, SourceKind.FILING)
    assert {item.document_id: item.status for item in original_list("600519")} == {
        document_id: SourceIntegrityStatus.COMPLETE,
        second_id: SourceIntegrityStatus.COMPLETE,
    }


@pytest.mark.parametrize("entry", ("direct", "job"))
def test_cn_post_repair_real_second_source_revision_conflict_preserves_public_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    """第二 selected source 的真实 revision conflict 保留 repair 文档并沿既有执行分类投影。

    Args:
        tmp_path: 独立真实仓储根。
        monkeypatch: 仅在 post-repair 真实枚举前改变第二来源的 PDF 字节。
        entry: direct 或后台 job 入口。

    Returns:
        无。

    Raises:
        AssertionError: 仓储分类、公共失败或已发布摘要不守恒时抛出。
    """

    runtime, discovery, _hk_discovery, _converter = _build_runtime_with_cn_hk_adapters(tmp_path)
    original_candidates = discovery.list_report_candidates

    def list_two(
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """返回两份身份财期不同且都会被选中的真实仓储候选。

        Args:
            query: 来源查询。
            profile: 公司 profile。
            cancellation_checkpoint: 取消检查点。

        Returns:
            2025 与 2024 年度报告候选。

        Raises:
            无。
        """

        first = original_candidates(query, profile, cancellation_checkpoint=cancellation_checkpoint)[0]
        return (first, replace(first, source_id="cn-runtime-b2", fiscal_year=2024, filing_date="2025-04-01"))

    monkeypatch.setattr(discovery, "list_report_candidates", list_two)
    request = build_fins_download_request(
        ticker="600519", form_types=("FY",), start="2025-01-01", end="2026-12-31"
    )
    first = runtime.start_download(request)
    published = runtime.read_job(first.job_id)
    assert published.status is FinsIngestionJobStatus.SUCCEEDED
    initial_ids = published.result_summary["written_document_ids"]
    assert isinstance(initial_ids, list) and len(initial_ids) == 2
    repair_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False
    )
    second_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    assert set(initial_ids) == {repair_id, second_id}
    source = runtime.source_repository
    assert isinstance(source, FsSourceDocumentRepository)
    repair_locator = source.get_source_document_locator("600519", repair_id, SourceKind.FILING)
    second_locator = source.get_source_document_locator("600519", second_id, SourceKind.FILING)
    repair_pdf = tmp_path / "workspace" / repair_locator / f"{repair_id}.pdf"
    second_pdf = tmp_path / "workspace" / second_locator / f"{second_id}.pdf"
    original_repair = repair_pdf.read_bytes()
    original_second = second_pdf.read_bytes()
    repair_pdf.write_bytes(original_repair + b"-repair-needed")
    company_path = tmp_path / "workspace" / "portfolio" / "600519" / "meta.json"
    old_company = company_path.read_bytes()
    real_list = source.list_source_integrity
    calls: list[int] = []
    second_statuses: list[SourceIntegrityStatus] = []

    def second_source_changes_after_repair(ticker: str) -> tuple[SourceIntegrityClassification, ...]:
        """post-repair 枚举前改变另一 selected source，并返回真实仓储分类。

        Args:
            ticker: 当前 canonical ticker。

        Returns:
            真实文件系统仓储的完整性 inventory。

        Raises:
            OSError: 文件变更或仓储读取失败时抛出。
        """

        calls.append(1)
        if len(calls) == 2:
            assert repair_pdf.read_bytes() == original_repair
            second_pdf.write_bytes(original_second + b"-revision-changed")
        inventory = real_list(ticker)
        if len(calls) == 2:
            second_statuses.extend(item.status for item in inventory if item.document_id == second_id)
        return inventory

    monkeypatch.setattr(source, "list_source_integrity", second_source_changes_after_repair)
    if entry == "direct":
        async def collect() -> list[FinsEvent]:
            """收集真实 adapter/runtime 的 direct 终态。

            Args:
                无。

            Returns:
                direct 事件列表。

            Raises:
                无。
            """

            return [event async for event in runtime.download(request)]

        events = asyncio.run(collect())
        results = [event.result for event in events if event.event_type is FinsEventType.RESULT]
        assert len(results) == 1
        result = results[0]
        assert result is not None and result.status is FinsResultStatus.FAILURE
        assert result.error_kind is FinsErrorKind.EXECUTION
        assert result.download is not None
        assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.SUCCEEDED
        assert result.download.discovered_count == result.download.downloaded_count == 1
        assert result.download.skipped_count == result.download.rejected_count == result.download.failed_count == 0
        assert [row.document_id for row in result.download.document_rows] == [repair_id]
        assert result.failure is not None
        assert result.failure.kind is FinsPublicFailureKind.EXECUTION
        assert result.failure.reason_code is None
        assert result.failure.safe_message == "下载执行失败"
        assert result.error_message == result.failure.safe_message
    else:
        start = runtime.start_download(request)
        record = runtime.read_job(start.job_id)
        assert record.status is FinsIngestionJobStatus.FAILED
        assert record.result_summary["terminal_disposition"] == "succeeded"
        assert record.result_summary["discovered_count"] == record.result_summary["downloaded_count"] == 1
        assert record.result_summary["skipped_count"] == 0
        assert record.result_summary["rejected_count"] == record.result_summary["failed_count"] == 0
        assert record.result_summary["written_document_ids"] == [repair_id]
        assert record.result_summary["omitted_written_document_count"] == 0
        assert record.failure_summary == {"message": "下载执行失败"}
    assert len(calls) == 2
    assert second_statuses == [SourceIntegrityStatus.REPAIR_REQUIRED]
    assert repair_pdf.read_bytes() == original_repair
    assert second_pdf.read_bytes() == original_second + b"-revision-changed"
    assert company_path.read_bytes() == old_company
    assert source.get_source_meta("600519", repair_id, SourceKind.FILING)
    assert source.get_source_meta("600519", second_id, SourceKind.FILING)


@pytest.mark.parametrize("entry", ("direct", "job"))
def test_cn_real_initial_whole_kind_preflight_uses_request_zero_summary(
    tmp_path: Path,
    entry: str,
) -> None:
    """真实已发布来源 root 外来文件在首候选前产生请求级 FAILED 零摘要。

    Args:
        tmp_path: 独立真实仓储根。
        entry: direct 或后台 job 入口。

    Returns:
        无。

    Raises:
        AssertionError: 初始 whole-kind typed 或公共零摘要漂移时抛出。
    """

    runtime, discovery, _hk_discovery, _converter = _build_runtime_with_cn_hk_adapters(tmp_path)
    request = build_fins_download_request(
        ticker="600519", form_types=("FY",), start="2025-01-01", end="2026-12-31"
    )
    first = runtime.start_download(request)
    published = runtime.read_job(first.job_id)
    assert published.status is FinsIngestionJobStatus.SUCCEEDED
    written_ids = published.result_summary["written_document_ids"]
    assert isinstance(written_ids, list) and len(written_ids) == 1
    document_id = str(written_ids[0])
    locator = runtime.source_repository.get_source_document_locator("600519", document_id, SourceKind.FILING)
    pdf_path = tmp_path / "workspace" / locator / f"{document_id}.pdf"
    old_pdf = pdf_path.read_bytes()
    root = tmp_path / "workspace" / "portfolio" / "600519" / "filings"
    (root / "foreign-before-candidates.bin").write_bytes(b"foreign")
    previous_download_calls = discovery.download_calls
    expected = ingestion_runtime_module._empty_download_summary_from_request(
        request, terminal_disposition=FinsDownloadTerminalDisposition.FAILED
    )
    if entry == "direct":
        async def collect() -> list[FinsEvent]:
            """收集真实初始 whole-kind direct 失败。

            Args:
                无。

            Returns:
                direct 事件列表。

            Raises:
                无。
            """

            return [event async for event in runtime.download(request)]

        events = asyncio.run(collect())
        results = [event.result for event in events if event.event_type is FinsEventType.RESULT]
        assert len(results) == 1
        result = results[0]
        assert result is not None and result.status is FinsResultStatus.FAILURE
        assert result.download is not None
        assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.FAILED
        assert result.download.discovered_count == 0 and result.download.document_rows == ()
        assert result.failure is not None
        assert result.failure.reason_code is FinsDownloadFailureReason.UNSAFE_PUBLICATION
        assert result.failure.safe_message == "本地来源完整性预检失败"
    else:
        start = runtime.start_download(request)
        record = runtime.read_job(start.job_id)
        assert record.status is FinsIngestionJobStatus.FAILED
        assert record.result_summary == expected.to_json_summary()
        assert record.failure_summary["message"] == "本地来源完整性预检失败"
    assert discovery.download_calls == previous_download_calls
    assert pdf_path.read_bytes() == old_pdf
