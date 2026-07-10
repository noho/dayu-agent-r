"""CN/HK download runtime 接入测试。"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins.domain.document_models import FinsSourceProvider
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsDownloadRequest,
    FinsIngestionExecutor,
    FinsIngestionJobStatus,
    FinsIngestionRuntime,
    FinsSourceDownloadAdapterRequest,
    FsFinsIngestionJobStore,
)
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnReportCandidate,
    CnReportQuery,
    DownloadedReportAsset,
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
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.storage import (
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import NormalizedTicker

_PDF_BYTES = b"%PDF-1.7\n" + b"1" * 2048
_DOCLING_BYTES = b'{"document": "runtime-ok"}'


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
    ) -> tuple[CnReportCandidate, ...]:
        """返回固定年度报告候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。

        Returns:
            候选报告 tuple。

        Raises:
            无。
        """

        del profile
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
                fiscal_period="FY",
                amended=False,
                content_length=len(_PDF_BYTES),
                etag=f'"{self.source_id}-v1"',
                last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
            ),
        )

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """返回本地 PDF 资产。

        Args:
            candidate: 远端候选。

        Returns:
            已下载 PDF 资产。

        Raises:
            OSError: 临时文件写入失败时抛出。
        """

        self.download_calls += 1
        pdf_path = self.temp_dir / f"{candidate.source_id}_{self.download_calls}.pdf"
        pdf_path.write_bytes(_PDF_BYTES)
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_path=pdf_path,
            sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
            content_length=len(_PDF_BYTES),
            downloaded_at="2026-05-02T00:00:00+00:00",
        )


@dataclass
class _RuntimeFakeConverter:
    """runtime 接入测试用 Docling fake。"""

    calls: int = 0

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """返回固定 Docling JSON 字节。

        Args:
            raw_data: PDF 字节。
            stream_name: 流名称。

        Returns:
            Docling JSON 字节。

        Raises:
            无。
        """

        del raw_data, stream_name
        self.calls += 1
        return _DOCLING_BYTES


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
            convert_pdf_to_docling_json=_RuntimeFakeConverter(),
        )
        self.recorded_rebuild_values: list[bool] = []

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
            cancel_checker: 可选取消检查器。

        Returns:
            pipeline 下载结果。

        Raises:
            无。
        """

        del form_type, start_date, end_date, overwrite, ticker_aliases, cancel_checker
        self.recorded_rebuild_values.append(rebuild)
        return {
            "pipeline": "cn",
            "action": "download",
            "status": "ok",
            "ticker": ticker,
            "company_info": {},
            "filters": {},
            "warnings": [],
            "notes": [],
            "filings": [],
            "summary": {
                "total": 0,
                "downloaded": 0,
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
        FinsDownloadRequest(
            ticker="600519",
            source=CN_DOWNLOAD_SOURCE,
            form_types=("FY",),
            filed_after="2025-01-01",
            filed_before="2026-12-31",
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
    assert source_meta["source_provider"] == "cninfo"
    assert source_meta["ingest_complete"] is True
    assert runtime.source_repository.get_source_document_provenance(
        "600519",
        document_id,
        SourceKind.FILING,
    ).source_provider is FinsSourceProvider.CNINFO


def test_start_download_auto_hk_uses_hkexnews_adapter(tmp_path: Path) -> None:
    """``source=auto`` 且 market=HK 应确定性走 HKEXNews adapter。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    runtime, _cn_discovery, hk_discovery, converter = _build_runtime_with_cn_hk_adapters(tmp_path)

    start = runtime.start_download(
        FinsDownloadRequest(
            ticker="0700",
            source="auto",
            form_types=("FY",),
            filed_after="2024-01-01",
            filed_before="2025-12-31",
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
    assert runtime.source_repository.get_source_document_provenance(
        "0700",
        document_id,
        SourceKind.FILING,
    ).source_provider is FinsSourceProvider.HKEXNEWS


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
        company_repository=repositories.company_repository,
        source_repository=repositories.source_repository,
        processed_repository=repositories.processed_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
    )
    hk_adapter = cn_pipeline_module.build_hk_download_adapter(
        workspace_root=repositories.workspace_root,
        company_repository=repositories.company_repository,
        source_repository=repositories.source_repository,
        processed_repository=repositories.processed_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
    )

    assert cn_adapter._pipeline.sleep_seconds == cn_sleep_seconds
    assert cn_adapter._pipeline.max_retries == cn_max_retries
    assert hk_adapter._pipeline.sleep_seconds == hk_sleep_seconds
    assert hk_adapter._pipeline.max_retries == hk_max_retries


def test_cn_adapter_receives_rebuild_processed_without_old_rebuild(tmp_path: Path) -> None:
    """adapter 应记录 NEW rebuild_processed，但不映射为 OLD download rebuild。

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
            source=CN_DOWNLOAD_SOURCE,
            form_types=("FY",),
            filed_after=None,
            filed_before=None,
            overwrite_existing=False,
            rebuild_processed=True,
            cancellation_checker=lambda: False,
        )
    )

    assert pipeline.recorded_rebuild_values == [False]


def _build_runtime_with_cn_hk_adapters(
    tmp_path: Path,
) -> tuple[
    FinsIngestionRuntime,
    _RuntimeFakeDiscoveryClient,
    _RuntimeFakeDiscoveryClient,
    _RuntimeFakeConverter,
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
    converter = _RuntimeFakeConverter()
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
        company_repository=repositories.company_repository,
        source_repository=repositories.source_repository,
        processed_repository=repositories.processed_repository,
        blob_repository=repositories.blob_repository,
        filing_maintenance_repository=repositories.filing_maintenance_repository,
        cn_discovery_client=cn_discovery,
        hk_discovery_client=hk_discovery,
        convert_pdf_to_docling_json=converter,
    )
    runtime = FinsIngestionRuntime.create(
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
    return runtime, cn_discovery, hk_discovery, converter


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
        company_repository=FsCompanyMetaRepository(workspace_root, repository_set=repository_set),
        source_repository=FsSourceDocumentRepository(workspace_root, repository_set=repository_set),
        processed_repository=FsProcessedDocumentRepository(workspace_root, repository_set=repository_set),
        blob_repository=FsDocumentBlobRepository(workspace_root, repository_set=repository_set),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            workspace_root,
            repository_set=repository_set,
        ),
    )
