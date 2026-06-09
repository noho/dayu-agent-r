"""CnPipeline download facade 行为测试。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from dayu.fins.downloaders.hkexnews_downloader import HkexnewsDiscoveryClient
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnReportCandidate,
    CnReportQuery,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.download_events import DownloadEventType

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'


@dataclass
class _PipelineDownloadFakeDiscoveryClient:
    """CnPipeline wrapper 测试用 CN fake discovery client。"""

    temp_dir: Path
    download_calls: int = 0

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
    ) -> tuple[CnReportCandidate, ...]:
        """返回一份固定 FY 候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。

        Returns:
            候选 tuple。

        Raises:
            无。
        """

        del profile
        return (
            CnReportCandidate(
                provider="cninfo",
                source_id="A1",
                source_url="https://static.cninfo.test/A1.pdf",
                title="平安银行：2025年年度报告",
                language="zh",
                filing_date="2026-04-01",
                fiscal_year=2025,
                fiscal_period="FY",
                amended=False,
                content_length=len(_PDF_BYTES),
                etag='"v1"',
                last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
            ),
        )

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """返回本地临时 PDF 资产。

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
class _PipelineDownloadFakeHkDiscoveryClient:
    """CnPipeline wrapper 测试用 HK fake discovery client。"""

    temp_dir: Path
    download_calls: int = 0

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
    ) -> tuple[CnReportCandidate, ...]:
        """返回一份固定 HK FY 候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。

        Returns:
            候选 tuple。

        Raises:
            无。
        """

        del profile
        return (
            CnReportCandidate(
                provider="hkexnews",
                source_id="HK1",
                source_url="https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0408/hk1.pdf",
                title="ANNUAL REPORT 2024",
                language="en",
                filing_date="2025-04-08",
                fiscal_year=2024,
                fiscal_period="FY",
                amended=False,
                content_length=len(_PDF_BYTES),
                etag='"hk-v1"',
                last_modified="Tue, 08 Apr 2025 00:00:00 GMT",
            ),
        )

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """返回本地临时 PDF 资产。

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
class _PipelineDownloadFakeConverter:
    """CnPipeline wrapper 测试用 Docling fake。"""

    calls: int = 0

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """返回固定 Docling JSON。

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
    converter = _PipelineDownloadFakeConverter()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        cn_discovery_client=discovery,
        convert_pdf_to_docling_json=converter,
    )

    result = pipeline.download(
        ticker="000001",
        form_type="FY",
        start_date="2025-01-01",
        end_date="2026-12-31",
        overwrite=True,
    )

    assert result["pipeline"] == "cn"
    assert result["action"] == "download"
    assert result["status"] == "ok"
    assert result["ticker"] == "000001"
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert discovery.download_calls == 1
    assert converter.calls == 1


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
    converter = _PipelineDownloadFakeConverter()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        hk_discovery_client=discovery,
        convert_pdf_to_docling_json=converter,
    )

    result = pipeline.download(
        ticker="0700",
        form_type="FY",
        start_date="2024-01-01",
        end_date="2025-12-31",
        overwrite=True,
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
    assert converter.calls == 1


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
    converter = _PipelineDownloadFakeConverter()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        cn_discovery_client=discovery,
        convert_pdf_to_docling_json=converter,
    )

    events = [
        event
        async for event in pipeline.download_stream(
            ticker="000001",
            form_type="FY",
            start_date="2025-01-01",
            end_date="2026-12-31",
            overwrite=False,
        )
    ]

    assert [event.event_type for event in events] == [
        DownloadEventType.PIPELINE_STARTED,
        DownloadEventType.COMPANY_RESOLVED,
        DownloadEventType.FILING_STARTED,
        DownloadEventType.FILE_DOWNLOADED,
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
    assert converter.calls == 1
