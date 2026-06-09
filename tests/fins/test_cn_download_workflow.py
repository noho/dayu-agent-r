"""CN/HK download workflow 单元测试。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnFiscalPeriod,
    CnReportCandidate,
    CnReportQuery,
    CnSourceProvider,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import FsCompanyMetaRepository, FsDocumentBlobRepository
from dayu.fins.storage import FsFilingMaintenanceRepository, FsProcessedDocumentRepository
from dayu.fins.storage import FsSourceDocumentRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'


@dataclass
class _FakeDiscoveryClient:
    """CN discovery fake。"""

    temp_dir: Path
    candidates: tuple[CnReportCandidate, ...]
    pdf_bytes: bytes = _PDF_BYTES
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
            provider="cninfo",
            company_id="CNINFO:9900000600",
            company_name="贵州茅台",
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
    ) -> tuple[CnReportCandidate, ...]:
        """返回测试候选。

        Args:
            query: 下载查询。
            profile: 公司元数据。

        Returns:
            候选报告 tuple。

        Raises:
            无。
        """

        del query, profile
        return self.candidates

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """写入临时 PDF 并返回下载资产。

        Args:
            candidate: 远端候选。

        Returns:
            已下载 PDF 资产。

        Raises:
            OSError: 临时 PDF 写入失败时抛出。
        """

        self.download_calls += 1
        path = self.temp_dir / f"{candidate.source_id}_{self.download_calls}.pdf"
        path.write_bytes(self.pdf_bytes)
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_path=path,
            sha256=hashlib.sha256(self.pdf_bytes).hexdigest(),
            content_length=len(self.pdf_bytes),
            downloaded_at="2026-05-02T00:00:00+00:00",
        )


@dataclass
class _FakeConverter:
    """Docling 转换 fake。"""

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


@dataclass
class _RecordingPdfGate(CnDownloadPdfGateProtocol):
    """记录 PDF 下载 gate 持有状态。"""

    active: bool = False
    enter_count: int = 0
    exit_count: int = 0

    def lease_for_provider(
        self,
        provider: CnSourceProvider,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AbstractContextManager[None]:
        """返回记录型 lease。

        Args:
            provider: 来源 provider。
            cancel_checker: 可选取消检查函数。

        Returns:
            记录型上下文管理器。

        Raises:
            AssertionError: provider 非法时抛出。
        """

        del cancel_checker
        assert provider in {"cninfo", "hkexnews"}
        return _RecordingPdfGateLease(self)


@dataclass
class _RecordingPdfGateLease:
    """测试用 PDF gate lease。"""

    gate: _RecordingPdfGate

    def __enter__(self) -> None:
        """进入 gate lease。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.gate.active = True
        self.gate.enter_count += 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出 gate lease。

        Args:
            exc_type: 异常类型。
            exc: 异常实例。
            traceback: traceback。

        Returns:
            无。

        Raises:
            无。
        """

        del exc_type, exc, traceback
        self.gate.active = False
        self.gate.exit_count += 1


@dataclass
class _GateAwareConverter(_FakeConverter):
    """验证 Docling 转换不在 PDF 下载 gate 内执行。"""

    gate: _RecordingPdfGate = field(default_factory=_RecordingPdfGate)

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """断言转换阶段没有持有 PDF 下载 gate。

        Args:
            raw_data: PDF 字节。
            stream_name: 流名称。

        Returns:
            Docling JSON 字节。

        Raises:
            AssertionError: Docling 转换发生在 gate 内时抛出。
        """

        assert self.gate.active is False
        return super().__call__(raw_data, stream_name)


def _candidate(
    *,
    source_id: str = "A1",
    etag: str = '"v1"',
    fiscal_year: int = 2024,
    fiscal_period: CnFiscalPeriod = "FY",
    filing_date: str | None = None,
) -> CnReportCandidate:
    """构造 CN 候选。

    Args:
        source_id: 来源内文档 ID。
        etag: 远端 ETag。
        fiscal_year: 财年。
        fiscal_period: 财期。
        filing_date: 披露日期。

    Returns:
        候选报告。

    Raises:
        无。
    """

    return CnReportCandidate(
        provider="cninfo",
        source_id=source_id,
        source_url=f"https://static.cninfo.test/{source_id}.pdf",
        title=f"贵州茅台：{fiscal_year}年{fiscal_period}报告",
        language="zh",
        filing_date=filing_date or f"{fiscal_year + 1}-04-01",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        amended=False,
        content_length=len(_PDF_BYTES),
        etag=etag,
        last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
    )


def _build_pipeline(
    *,
    tmp_path: Path,
    discovery: _FakeDiscoveryClient,
    converter: _FakeConverter,
    pdf_download_gate: CnDownloadPdfGateProtocol | None = None,
) -> CnPipeline:
    """构造注入 fake downloader / converter 的 CnPipeline。

    Args:
        tmp_path: 临时工作区目录。
        discovery: fake discovery client。
        converter: fake Docling converter。
        pdf_download_gate: 可选 PDF 下载 gate。

    Returns:
        CN/HK pipeline。

    Raises:
        OSError: FS 仓储初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    return CnPipeline(
        workspace_root=tmp_path,
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set),
        source_repository=FsSourceDocumentRepository(tmp_path, repository_set=repository_set),
        processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=repository_set),
        blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=repository_set),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=repository_set,
        ),
        cn_discovery_client=discovery,
        pdf_download_gate=pdf_download_gate,
        convert_pdf_to_docling_json=converter,
    )


def _collect_events(
    pipeline: CnPipeline,
    *,
    form_type: str = "FY",
    overwrite: bool = False,
) -> list[DownloadEvent]:
    """同步收集 download_stream 事件。

    Args:
        pipeline: 待执行 pipeline。
        form_type: form 过滤。
        overwrite: 是否覆盖。

    Returns:
        下载事件列表。

    Raises:
        RuntimeError: 事件循环执行失败时抛出。
    """

    return asyncio.run(
        _collect_events_async(
            pipeline=pipeline,
            ticker="600519",
            form_type=form_type,
            start_date="2024",
            end_date="2026",
            overwrite=overwrite,
        )
    )


async def _collect_events_async(
    *,
    pipeline: CnPipeline,
    ticker: str,
    form_type: str,
    start_date: str,
    end_date: str,
    overwrite: bool,
) -> list[DownloadEvent]:
    """异步收集 download_stream 事件。

    Args:
        pipeline: 待执行 pipeline。
        ticker: 股票代码。
        form_type: form 过滤。
        start_date: 开始日期。
        end_date: 结束日期。
        overwrite: 是否覆盖。

    Returns:
        下载事件列表。

    Raises:
        ValueError: pipeline 参数非法时由底层抛出。
    """

    events: list[DownloadEvent] = []
    async for event in pipeline.download_stream(
        ticker=ticker,
        form_type=form_type,
        start_date=start_date,
        end_date=end_date,
        overwrite=overwrite,
    ):
        events.append(event)
    return events


def _final_result(events: list[DownloadEvent]) -> dict[str, JsonValue]:
    """读取最终 pipeline result。

    Args:
        events: 下载事件列表。

    Returns:
        最终结果字典。

    Raises:
        AssertionError: 最终事件缺少结果时抛出。
    """

    payload = events[-1].payload.get("result")
    assert isinstance(payload, dict)
    return {str(key): value for key, value in payload.items()}


def test_cn_download_workflow_commits_pdf_and_docling(tmp_path: Path) -> None:
    """主流程应按事件序列完成 PDF + Docling + source commit。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline)

    assert [event.event_type for event in events] == [
        DownloadEventType.PIPELINE_STARTED,
        DownloadEventType.COMPANY_RESOLVED,
        DownloadEventType.FILING_STARTED,
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.FILING_COMPLETED,
        DownloadEventType.PIPELINE_COMPLETED,
    ]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert summary["converted"] == 1
    assert discovery.download_calls == 1
    assert converter.calls == 1
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    source_meta = pipeline.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    assert source_meta["company_id"] == "600519_SSE"
    assert source_meta["provider_company_id"] == "CNINFO:9900000600"
    assert source_meta["document_version"] == "v1"


def test_cn_download_pdf_gate_does_not_cover_docling_convert(tmp_path: Path) -> None:
    """PDF 下载 gate 只覆盖远端 PDF 下载，不覆盖 Docling 转换。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    gate = _RecordingPdfGate()
    converter = _GateAwareConverter(gate=gate)
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=converter,
        pdf_download_gate=gate,
    )

    result = _final_result(_collect_events(pipeline))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert summary["converted"] == 1
    assert gate.enter_count == 1
    assert gate.exit_count == 1
    assert gate.active is False
    assert converter.calls == 1


def test_cn_download_fast_skip_uses_remote_fingerprint(tmp_path: Path) -> None:
    """第二次下载远端 fingerprint 相同应 fast skip 且不重新下载 PDF。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    _collect_events(pipeline)
    second_events = _collect_events(pipeline)

    result = _final_result(second_events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["skipped"] == 1
    assert discovery.download_calls == 1
    assert converter.calls == 1


def test_cn_download_marks_missing_independent_quarter_skipped(tmp_path: Path) -> None:
    """主源没有独立季度候选时 workflow 应标记 skipped，不折叠到相邻累计期间。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline, form_type="Q2")

    result = _final_result(events)
    summary = result["summary"]
    filings = result["filings"]
    assert isinstance(summary, dict)
    assert isinstance(filings, list)
    assert summary["skipped"] == 1
    assert discovery.download_calls == 0
    assert converter.calls == 0
    first = filings[0]
    assert isinstance(first, dict)
    assert first["form_type"] == "Q2"
    assert first["skip_reason"] == "candidate_not_found"
