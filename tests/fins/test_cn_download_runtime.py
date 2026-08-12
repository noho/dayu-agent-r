"""CN/HK download runtime 接入测试。"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins.domain.document_models import FinsSourceProvider, ProcessedCreateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import (
    FinsDownloadDateRange,
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
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
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
        cn_discovery_client=cn_discovery,
        hk_discovery_client=hk_discovery,
        docling_converter=runner,
    )
    runtime = FinsIngestionRuntime.create(
        batching_repository=repositories.batching_repository,
        source_repository=repositories.source_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
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
    )
