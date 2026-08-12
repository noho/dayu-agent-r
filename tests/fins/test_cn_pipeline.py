"""CnPipeline download facade 行为测试。"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.downloaders.hkexnews_downloader import HkexnewsDiscoveryClient
from dayu.fins.domain.document_models import CompanyMeta, now_iso8601
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import FinsDownloadProgressEvent
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnReportCandidate,
    CnReportPeriodProjection,
    CnReportQuery,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_pipeline import CnPipeline, collect_cn_download_result_from_events
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionResult,
)
from dayu.fins.pipelines.download_events import DownloadEventType
from dayu.fins.pipelines.upload_company_meta import RESOLVER_VERSION
from dayu.fins.pipelines.upload_filing_events import UploadFilingEventType
from dayu.fins.pipelines.upload_material_events import UploadMaterialEventType

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'


class _NeverCancelledToken(CancellationToken):
    """始终未取消的 canonical 测试 token。"""

    def __call__(self) -> bool:
        """委托 canonical 观察方法。

        Returns:
            始终返回 ``False``。
        """

        return self.is_cancelled()

    def is_cancelled(self) -> bool:
        """返回未取消的稳定测试信号。

        Args:
            无。

        Returns:
            始终为 ``False``。

        Raises:
            无。
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


_never_cancel = _NeverCancelledToken()


@dataclass
class _PipelineDownloadFakeDiscoveryClient:
    """CnPipeline wrapper 测试用 CN fake discovery client。"""

    temp_dir: Path
    candidates: tuple[CnReportCandidate, ...] | None = None
    download_calls: int = 0
    cancellation_checkpoints: list[Callable[[], None] | None] = field(default_factory=list)

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """返回固定公司元数据。

        Args:
            query: 下载查询。

        Returns:
            公司基础元数据。

        Raises:
            无。
        """

        return CnCompanyProfile(
            provider="cninfo",
            company_id="CNINFO:9900000001",
            company_name="平安银行",
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """返回一份固定 FY 候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。
            cancellation_checkpoint: workflow-owned 无参取消检查点。

        Returns:
            候选 tuple。

        Raises:
            无。
        """

        del profile
        self.cancellation_checkpoints.append(cancellation_checkpoint)
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        default_candidates = (
            CnReportCandidate(
                provider="cninfo",
                source_id="A1",
                source_url="https://static.cninfo.test/A1.pdf",
                title="平安银行：2025年年度报告",
                language="zh",
                filing_date="2026-04-01",
                fiscal_year=2025,
                period_projection=CnReportPeriodProjection(identity_period="FY", covered_periods=("FY",)),
                amended=False,
                content_length=len(_PDF_BYTES),
                etag='"v1"',
                last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
            ),
        )
        return self.candidates if self.candidates is not None else default_candidates

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
class _PipelineDownloadFakeHkDiscoveryClient:
    """CnPipeline wrapper 测试用 HK fake discovery client。"""

    temp_dir: Path
    download_calls: int = 0
    cancellation_checkpoints: list[Callable[[], None] | None] = field(default_factory=list)

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """返回固定 HK 公司元数据。

        Args:
            query: 下载查询。

        Returns:
            公司基础元数据。

        Raises:
            无。
        """

        return CnCompanyProfile(
            provider="hkexnews",
            company_id="HKEX:7609",
            company_name="騰訊控股",
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """返回一份固定 HK FY 候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。
            cancellation_checkpoint: workflow-owned 无参取消检查点。

        Returns:
            候选 tuple。

        Raises:
            无。
        """

        del profile
        self.cancellation_checkpoints.append(cancellation_checkpoint)
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        return (
            CnReportCandidate(
                provider="hkexnews",
                source_id="HK1",
                source_url="https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0408/hk1.pdf",
                title="ANNUAL REPORT 2024",
                language="en",
                filing_date="2025-04-08",
                fiscal_year=2024,
                period_projection=CnReportPeriodProjection(identity_period="FY", covered_periods=("FY",)),
                amended=False,
                content_length=len(_PDF_BYTES),
                etag='"hk-v1"',
                last_modified="Tue, 08 Apr 2025 00:00:00 GMT",
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
class _PipelineDownloadFakeConversionRunner:
    """CnPipeline wrapper 测试用 typed Docling runner。"""

    calls: int = 0
    cancellations: list[CancellationToken | None] = field(default_factory=list)

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回固定 Docling JSON。

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
        assert cancellation is None or cancellation.is_cancelled() is False
        self.calls += 1
        self.cancellations.append(cancellation)
        return DoclingConversionResult(
            json_bytes=_DOCLING_BYTES,
            size=len(_DOCLING_BYTES),
            sha256=hashlib.sha256(_DOCLING_BYTES).hexdigest(),
        )


def _seed_cn_upload_company_meta(
    *,
    pipeline: CnPipeline,
    company_name: str,
    resolver_version: str,
    ticker_aliases: list[str],
) -> None:
    """写入 CN upload 测试用公司元数据。

    Args:
        pipeline: CN pipeline 实例。
        company_name: 公司名称。
        resolver_version: 元数据 resolver 版本。
        ticker_aliases: ticker alias 列表。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    batch = pipeline.batching_repository.begin_batch("600519")
    pipeline._company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="600519_CN",
            company_name=company_name,
            ticker="600519",
            market="CN",
            resolver_version=resolver_version,
            updated_at=now_iso8601(),
            ticker_aliases=ticker_aliases,
        ),
        batch=batch,
    )
    pipeline.batching_repository.commit_batch(batch)


def test_download_runs_cn_workflow_with_injected_discovery_client(tmp_path: Path) -> None:
    """同步 ``download`` wrapper 应调用真实 CN workflow 且不访问网络。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _PipelineDownloadFakeDiscoveryClient(temp_dir=tmp_path)
    runner = _PipelineDownloadFakeConversionRunner()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        cn_discovery_client=discovery,
        docling_converter=runner,
    )
    cancel_checker = _never_cancel

    result = pipeline.download(
        ticker="000001",
        form_type="FY",
        start_date="2025-01-01",
        end_date="2026-12-31",
        overwrite=True,
        start_is_explicit=True,
        cancel_checker=cancel_checker,
    )

    assert result["pipeline"] == "cn"
    assert result["action"] == "download"
    assert result["status"] == "ok"
    assert result["ticker"] == "000001"
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert discovery.download_calls == 1
    assert len(discovery.cancellation_checkpoints) == 1
    assert discovery.cancellation_checkpoints[0] is not None
    assert discovery.cancellation_checkpoints[0] is not cancel_checker
    assert runner.calls == 1
    assert runner.cancellations == [cancel_checker]


def test_default_hk_discovery_client_is_hkexnews(tmp_path: Path) -> None:
    """CnPipeline 默认 HK discovery client 应接入披露易。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
    )

    assert isinstance(pipeline.hk_discovery_client, HkexnewsDiscoveryClient)


def test_download_runs_hk_workflow_with_injected_discovery_client(tmp_path: Path) -> None:
    """HK ticker 应经同一 CN/HK workflow 完成下载闭环。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _PipelineDownloadFakeHkDiscoveryClient(temp_dir=tmp_path)
    runner = _PipelineDownloadFakeConversionRunner()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        hk_discovery_client=discovery,
        docling_converter=runner,
    )
    cancel_checker = _never_cancel

    result = pipeline.download(
        ticker="0700",
        form_type="FY",
        start_date="2024-01-01",
        end_date="2025-12-31",
        overwrite=True,
        start_is_explicit=True,
        cancel_checker=cancel_checker,
    )

    assert result["pipeline"] == "hk"
    assert result["action"] == "download"
    assert result["status"] == "ok"
    assert result["ticker"] == "0700"
    company_info = result["company_info"]
    summary = result["summary"]
    assert isinstance(company_info, dict)
    assert isinstance(summary, dict)
    assert company_info["company_id"] == "0700_HKEX"
    assert summary["downloaded"] == 1
    assert discovery.download_calls == 1
    assert len(discovery.cancellation_checkpoints) == 1
    assert discovery.cancellation_checkpoints[0] is not None
    assert discovery.cancellation_checkpoints[0] is not cancel_checker
    assert runner.calls == 1
    assert runner.cancellations == [cancel_checker]


@pytest.mark.asyncio
async def test_download_stream_runs_cn_workflow_with_injected_discovery_client(
    tmp_path: Path,
) -> None:
    """``download_stream`` wrapper 应产出真实 CN download 事件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _PipelineDownloadFakeDiscoveryClient(temp_dir=tmp_path)
    runner = _PipelineDownloadFakeConversionRunner()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        cn_discovery_client=discovery,
        docling_converter=runner,
    )

    events = [
        event
        async for event in pipeline.download_stream(
            ticker="000001",
            form_type="FY",
            start_date="2025-01-01",
            end_date="2026-12-31",
            overwrite=False,
            start_is_explicit=True,
        )
    ]

    assert [event.event_type for event in events] == [
        DownloadEventType.PIPELINE_STARTED,
        DownloadEventType.COMPANY_RESOLVED,
        DownloadEventType.FILING_STARTED,
        DownloadEventType.FILE_DOWNLOAD_STARTED,
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.CONVERSION_STARTED,
        DownloadEventType.CONVERSION_COMPLETED,
        DownloadEventType.FILING_COMPLETED,
        DownloadEventType.PIPELINE_COMPLETED,
    ]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert result["status"] == "ok"
    assert summary["downloaded"] == 1
    assert discovery.download_calls == 1
    assert runner.calls == 1


@pytest.mark.asyncio
async def test_hk_adapter_progress_sink_projects_conversion_lifecycle(tmp_path: Path) -> None:
    """HK adapter 应按真实 workflow 顺序投影完整文档转换生命周期。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 转换完成事件缺失、乱序或业务字段漂移时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
        hk_discovery_client=_PipelineDownloadFakeHkDiscoveryClient(temp_dir=tmp_path),
        docling_converter=_PipelineDownloadFakeConversionRunner(),
    )
    progress_events: list[FinsDownloadProgressEvent] = []

    result = await collect_cn_download_result_from_events(
        pipeline.download_stream(
            ticker="0700",
            form_type="FY",
            start_date="2024-01-01",
            end_date="2025-12-31",
            overwrite=False,
            start_is_explicit=True,
        ),
        progress_sink=progress_events.append,
    )
    conversion_progress = [event for event in progress_events if event.stage.startswith("download.conversion_")]

    assert result["status"] == "ok"
    assert [(event.stage, event.message) for event in conversion_progress] == [
        ("download.conversion_started", "开始转换文档"),
        ("download.conversion_completed", "完成转换文档"),
    ]
    assert conversion_progress[0].document_id is not None
    assert conversion_progress[0].document_id == conversion_progress[1].document_id
    assert conversion_progress[0].file_name is not None
    assert conversion_progress[0].file_name == conversion_progress[1].file_name


def test_download_non_explicit_nonempty_start_keeps_default_business_limit(tmp_path: Path) -> None:
    """未来默认起点非空时，CN pipeline 仍须启用默认 FY 五年限制。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: workflow 从日期非空错误反推显式性时抛出。
    """

    candidates = tuple(
        CnReportCandidate(
            provider="cninfo",
            source_id=f"A{fiscal_year}",
            source_url=f"https://static.cninfo.test/A{fiscal_year}.pdf",
            title=f"平安银行：{fiscal_year}年年度报告",
            language="zh",
            filing_date=f"{fiscal_year + 1}-04-01",
            fiscal_year=fiscal_year,
            period_projection=CnReportPeriodProjection(identity_period="FY", covered_periods=("FY",)),
            amended=False,
            content_length=len(_PDF_BYTES),
            etag=f'"v{fiscal_year}"',
            last_modified=f"Wed, 01 Apr {fiscal_year + 1} 00:00:00 GMT",
        )
        for fiscal_year in range(2025, 2019, -1)
    )
    discovery = _PipelineDownloadFakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=candidates,
    )
    runner = _PipelineDownloadFakeConversionRunner()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        cn_discovery_client=discovery,
        docling_converter=runner,
    )

    result = pipeline.download(
        ticker="000001",
        form_type="FY",
        start_date="2020-01-01",
        end_date="2026-12-31",
        overwrite=False,
        start_is_explicit=False,
    )

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 5
    assert discovery.download_calls == 5
    assert runner.calls == 5


@pytest.mark.asyncio
async def test_upload_filing_stream_uploads_files_with_docling(tmp_path: Path) -> None:
    """CN filing upload stream 应完成上传并生成 Docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
        docling_converter=_PipelineDownloadFakeConversionRunner(),
    )
    filing_file = tmp_path / "annual.pdf"
    filing_file.write_text("demo cn filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="600519",
            action="create",
            files=[filing_file],
            fiscal_year=2024,
            fiscal_period="FY",
            amended=False,
            filing_date="2025-04-01",
            report_date="2024-12-31",
            company_name="贵州茅台",
            ticker_aliases=["600519", "600519.SH"],
            overwrite=False,
        )
    ]

    assert [event.event_type for event in events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        UploadFilingEventType.CONVERSION_STARTED,
        UploadFilingEventType.FILE_UPLOADED,
        UploadFilingEventType.FILE_UPLOADED,
        UploadFilingEventType.UPLOAD_COMPLETED,
    ]
    result_value = events[-1].payload["result"]
    assert isinstance(result_value, dict)
    assert result_value["pipeline"] == "cn"
    assert result_value["action"] == "upload_filing"
    assert result_value["status"] == "ok"
    assert str(result_value["document_id"]).startswith("fil_cn_")
    assert result_value["filing_action"] == "create"
    meta = pipeline._source_repository.get_source_meta(
        "600519",
        str(result_value["document_id"]),
        SourceKind.FILING,
    )
    assert str(meta["primary_document"]).endswith("_docling.json")
    assert meta["report_kind"] == "annual"


@pytest.mark.asyncio
async def test_upload_filing_stream_refreshes_stale_company_meta(tmp_path: Path) -> None:
    """CN filing upload 遇到旧 resolver 版本公司元数据时应刷新。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
        docling_converter=_PipelineDownloadFakeConversionRunner(),
    )
    _seed_cn_upload_company_meta(
        pipeline=pipeline,
        company_name="旧贵州茅台",
        resolver_version="market_resolver_v0.9.0",
        ticker_aliases=["600519", "OLD"],
    )
    filing_file = tmp_path / "annual.pdf"
    filing_file.write_text("demo cn filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="600519",
            action="create",
            files=[filing_file],
            fiscal_year=2024,
            fiscal_period="FY",
            amended=False,
            filing_date="2025-04-01",
            report_date="2024-12-31",
            company_name="贵州茅台",
            ticker_aliases=["600519", "600519.SH"],
            overwrite=False,
        )
    ]

    assert events[-1].event_type == UploadFilingEventType.UPLOAD_COMPLETED
    company_meta = pipeline._company_repository.get_company_meta("600519")
    assert company_meta.company_id == "600519_SSE"
    assert company_meta.company_name == "贵州茅台"
    assert company_meta.resolver_version == RESOLVER_VERSION
    assert company_meta.ticker_aliases == ["600519"]


@pytest.mark.asyncio
async def test_upload_material_stream_uploads_files_with_docling(tmp_path: Path) -> None:
    """CN material upload stream 应完成上传并生成 Docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
        docling_converter=_PipelineDownloadFakeConversionRunner(),
    )
    material_file = tmp_path / "deck.pdf"
    material_file.write_text("demo cn material", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="600519",
            action="create",
            form_type="MATERIAL_OTHER",
            material_name="Roadshow Deck",
            files=[material_file],
            company_name="贵州茅台",
            overwrite=False,
        )
    ]

    assert [event.event_type for event in events] == [
        UploadMaterialEventType.UPLOAD_STARTED,
        UploadMaterialEventType.CONVERSION_STARTED,
        UploadMaterialEventType.FILE_UPLOADED,
        UploadMaterialEventType.FILE_UPLOADED,
        UploadMaterialEventType.UPLOAD_COMPLETED,
    ]
    result_value = events[-1].payload["result"]
    assert isinstance(result_value, dict)
    assert result_value["pipeline"] == "cn"
    assert result_value["action"] == "upload_material"
    assert result_value["status"] == "ok"
    assert str(result_value["document_id"]).startswith("mat_")
    meta = pipeline._source_repository.get_source_meta(
        "600519",
        str(result_value["document_id"]),
        SourceKind.MATERIAL,
    )
    assert str(meta["primary_document"]).endswith("_docling.json")


@pytest.mark.asyncio
async def test_upload_filing_stream_auto_resolves_create_update_skip(tmp_path: Path) -> None:
    """CN filing upload stream 应自动 create/update 并跳过相同源文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
        docling_converter=_PipelineDownloadFakeConversionRunner(),
    )
    filing_file = tmp_path / "annual.pdf"
    filing_file.write_text("demo cn filing", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="600519",
            action=None,
            files=[filing_file],
            fiscal_year=2024,
            fiscal_period="FY",
            company_name="贵州茅台",
        )
    ]
    skip_events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="600519",
            action=None,
            files=[filing_file],
            fiscal_year=2024,
            fiscal_period="FY",
            company_name="贵州茅台",
        )
    ]
    create_result = create_events[-1].payload["result"]
    skip_result = skip_events[-1].payload["result"]

    assert isinstance(create_result, dict)
    assert isinstance(skip_result, dict)
    assert create_result["filing_action"] == "create"
    assert skip_result["filing_action"] == "update"
    assert skip_result["status"] == "skipped"
    assert [event.event_type for event in skip_events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        UploadFilingEventType.FILE_SKIPPED,
        UploadFilingEventType.UPLOAD_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_upload_material_stream_overwrite_resets_single_document(tmp_path: Path) -> None:
    """CN material upload stream 的 overwrite 应重置当前 material 文档。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = CnPipeline(
        workspace_root=tmp_path,
        docling_converter=_PipelineDownloadFakeConversionRunner(),
    )
    old_file = tmp_path / "deck_old.pdf"
    new_file = tmp_path / "deck_new.pdf"
    old_file.write_text("old material", encoding="utf-8")
    new_file.write_text("new material", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="600519",
            action=None,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[old_file],
            company_name="贵州茅台",
        )
    ]
    overwrite_events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="600519",
            action=None,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[new_file],
            company_name="贵州茅台",
            overwrite=True,
        )
    ]
    create_result = create_events[-1].payload["result"]
    overwrite_result = overwrite_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    assert isinstance(overwrite_result, dict)
    assert overwrite_result["status"] == "ok"
    assert overwrite_result["material_action"] == "update"
    assert overwrite_result["document_id"] == create_result["document_id"]

    handle = pipeline._source_repository.get_source_handle(
        "600519",
        str(overwrite_result["document_id"]),
        SourceKind.MATERIAL,
    )
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))
    assert file_names == ["deck_new.pdf", "deck_new_docling.json"]
