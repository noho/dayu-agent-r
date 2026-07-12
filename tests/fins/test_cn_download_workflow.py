"""CN/HK download workflow 单元测试。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Optional, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedHandle,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines import cn_download_workflow as _cn_download_workflow
from dayu.fins.pipelines import cn_download_filing_workflow as _cn_download_filing_workflow
from dayu.fins.pipelines.cn_download_models import (
    CnDownloadCancelledError,
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
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'


class _BatchIdentityCnSourceRepository(FsSourceDocumentRepository):
    """记录 CN/HK storage mutation 所处 batch identity 的 source spy。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet) -> None:
        """初始化 source batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self.active_token: BatchToken | None = None
        self.phases: list[tuple[str, str]] = []
        self.begin_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.fail_final = False
        self.fail_commit = False

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启 batch 并记录 token。"""

        token = super().begin_batch(ticker)
        self.active_token = token
        self.begin_calls += 1
        self.phases.append(("begin", token.token_id))
        return token

    def reset_source_document(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> None:
        """记录 reset 所处 token 后转发。"""

        self.record_phase("reset")
        super().reset_source_document(ticker, document_id, source_kind)

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
    ) -> DocumentHandle:
        """按 ingest_complete 区分 acknowledgement 与 final create。"""

        phase = "final_meta" if req.meta.get("ingest_complete") is True else "ack"
        self.record_phase(phase)
        if self.fail_final and phase == "final_meta":
            raise RuntimeError("forced CN final meta failure")
        return super().create_source_document(req, source_kind)

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
    ) -> DocumentHandle:
        """按 ingest_complete 区分 acknowledgement 与 final update。"""

        phase = "final_meta" if req.meta.get("ingest_complete") is True else "ack"
        self.record_phase(phase)
        if self.fail_final and phase == "final_meta":
            raise RuntimeError("forced CN final meta failure")
        return super().update_source_document(req, source_kind)

    def commit_batch(self, token: BatchToken) -> None:
        """记录 caller 唯一 commit 并转发。"""

        self.record_phase("commit")
        self.commit_calls += 1
        if self.fail_commit:
            FsSourceDocumentRepository.rollback_batch(self, token)
            self.active_token = None
            raise OSError("forced CN storage commit failure")
        super().commit_batch(token)
        self.active_token = None

    def rollback_batch(self, token: BatchToken) -> None:
        """记录 caller operation rollback 并转发。"""

        self.record_phase("rollback")
        self.rollback_calls += 1
        super().rollback_batch(token)
        self.active_token = None

    def record_phase(self, phase: str) -> None:
        """记录阶段与当前 active token identity。"""

        token = self.active_token
        assert token is not None
        self.phases.append((phase, token.token_id))


class _BatchIdentityCnBlobRepository(FsDocumentBlobRepository):
    """记录 CN/HK blob 写入所处 token 的真实文件仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        source_repository: _BatchIdentityCnSourceRepository,
    ) -> None:
        """初始化 blob batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._source_repository = source_repository

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录 PDF/Docling blob 阶段后转发真实写入。"""

        self._source_repository.record_phase(f"blob:{filename.rsplit('.', 1)[-1]}")
        return super().store_file(
            handle,
            filename,
            data,
            content_type=content_type,
            metadata=metadata,
        )


class _BatchIdentityCnProcessedRepository(FsProcessedDocumentRepository):
    """记录 processed marker 与 source mutation 共享 token 的 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        source_repository: _BatchIdentityCnSourceRepository,
    ) -> None:
        """初始化 processed batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._source_repository = source_repository

    def get_processed_meta(self, ticker: str, document_id: str) -> dict[str, JsonValue]:
        """返回存在的 processed meta 以驱动 marker 分支。"""

        del ticker, document_id
        return {"reprocess_required": False}

    def mark_processed_reprocess_required(self, ticker: str, document_id: str, required: bool) -> None:
        """记录 marker 阶段；测试不伪造额外 durable processed 文档。"""

        del ticker, document_id
        assert required is True
        self._source_repository.record_phase("processed_marker")


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
        """返回内存 PDF 下载资产。

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
            pdf_bytes=self.pdf_bytes,
            sha256=hashlib.sha256(self.pdf_bytes).hexdigest(),
            content_length=len(self.pdf_bytes),
            downloaded_at="2026-05-02T00:00:00+00:00",
        )


class _FailingDownloadDiscoveryClient(_FakeDiscoveryClient):
    """在 PDF download 阶段失败的 discovery fake。"""

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """抛出固定下载异常且不构造资产。"""

        del candidate
        self.download_calls += 1
        raise RuntimeError("forced PDF download failure")


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
class _CancelAfterConvertConverter:
    """转换完成后触发取消的 Docling fake。"""

    cancel_state: "_CancelState"
    calls: int = 0

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """返回固定 Docling JSON 并设置取消状态。

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
        self.cancel_state.cancelled = True
        return _DOCLING_BYTES


@dataclass
class _CancelState:
    """测试用取消状态。"""

    cancelled: bool = False

    def __call__(self) -> bool:
        """返回当前取消状态。

        Args:
            无。

        Returns:
            已取消时返回 ``True``。

        Raises:
            无。
        """

        return self.cancelled


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
    converter: Callable[[bytes, str], bytes],
    pdf_download_gate: CnDownloadPdfGateProtocol | None = None,
    repository_set: _FsRepositorySet | None = None,
    source_repository: FsSourceDocumentRepository | None = None,
    blob_repository: FsDocumentBlobRepository | None = None,
    processed_repository: FsProcessedDocumentRepository | None = None,
) -> CnPipeline:
    """构造注入 fake downloader / converter 的 CnPipeline。

    Args:
        tmp_path: 临时工作区目录。
        discovery: fake discovery client。
        converter: fake Docling converter。
        pdf_download_gate: 可选 PDF 下载 gate。
        repository_set: 可选共享 FS 仓储集合。
        source_repository: 可选 source 仓储 spy。
        blob_repository: 可选 blob 仓储 spy。
        processed_repository: 可选 processed 仓储 spy。

    Returns:
        CN/HK pipeline。

    Raises:
        OSError: FS 仓储初始化失败时抛出。
    """

    shared_repository_set = repository_set or build_fs_repository_set(workspace_root=tmp_path)
    return CnPipeline(
        workspace_root=tmp_path,
        company_repository=FsCompanyMetaRepository(tmp_path, repository_set=shared_repository_set),
        source_repository=source_repository
        or FsSourceDocumentRepository(tmp_path, repository_set=shared_repository_set),
        processed_repository=processed_repository
        or FsProcessedDocumentRepository(tmp_path, repository_set=shared_repository_set),
        blob_repository=blob_repository
        or FsDocumentBlobRepository(tmp_path, repository_set=shared_repository_set),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=shared_repository_set,
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
    cancel_checker: Callable[[], bool] | None = None,
) -> list[DownloadEvent]:
    """同步收集 download_stream 事件。

    Args:
        pipeline: 待执行 pipeline。
        form_type: form 过滤。
        overwrite: 是否覆盖。
        cancel_checker: 可选取消检查函数。

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
            cancel_checker=cancel_checker,
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
    cancel_checker: Callable[[], bool] | None = None,
) -> list[DownloadEvent]:
    """异步收集 download_stream 事件。

    Args:
        pipeline: 待执行 pipeline。
        ticker: 股票代码。
        form_type: form 过滤。
        start_date: 开始日期。
        end_date: 结束日期。
        overwrite: 是否覆盖。
        cancel_checker: 可选取消检查函数。

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
        cancel_checker=cancel_checker,
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
        DownloadEventType.FILE_DOWNLOAD_STARTED,
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.CONVERSION_STARTED,
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


def test_cn_replacement_uses_one_batch_for_reset_ack_blobs_final_and_processed(
    tmp_path: Path,
) -> None:
    """replacement 全部 mutation 必须共享一个 token 且只由 caller commit 一次。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        source_repository,
    )
    processed_repository = _BatchIdentityCnProcessedRepository(
        tmp_path,
        repository_set,
        source_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        source_repository=source_repository,
        blob_repository=blob_repository,
        processed_repository=processed_repository,
    )
    _collect_events(pipeline)
    source_repository.phases.clear()
    begin_calls = source_repository.begin_calls
    commit_calls = source_repository.commit_calls
    rollback_calls = source_repository.rollback_calls
    discovery.pdf_bytes = _PDF_BYTES + b"replacement"

    result = _final_result(_collect_events(pipeline, overwrite=True))

    phases = [phase for phase, _ in source_repository.phases]
    batch_ids = {batch_id for _, batch_id in source_repository.phases}
    assert result["status"] == "ok"
    assert phases == [
        "begin",
        "reset",
        "ack",
        "blob:pdf",
        "blob:json",
        "final_meta",
        "processed_marker",
        "commit",
    ]
    assert len(batch_ids) == 1
    assert source_repository.begin_calls == begin_calls + 1
    assert source_repository.commit_calls == commit_calls + 1
    assert source_repository.rollback_calls == rollback_calls


def test_cn_pdf_sha_skip_final_meta_uses_one_caller_batch(tmp_path: Path) -> None:
    """PDF-SHA skip 的 final meta helper 也必须只暂存到 caller 唯一 batch。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        source_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        source_repository=source_repository,
        blob_repository=blob_repository,
    )
    _collect_events(pipeline)
    source_repository.phases.clear()
    begin_calls = source_repository.begin_calls
    commit_calls = source_repository.commit_calls
    discovery.candidates = (_candidate(source_id="A2", etag='"v2"'),)

    result = _final_result(_collect_events(pipeline))

    phases = [phase for phase, _ in source_repository.phases]
    batch_ids = {batch_id for _, batch_id in source_repository.phases}
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["skipped"] == 1
    assert phases == ["begin", "final_meta", "commit"]
    assert len(batch_ids) == 1
    assert source_repository.begin_calls == begin_calls + 1
    assert source_repository.commit_calls == commit_calls + 1
    assert source_repository.rollback_calls == 0


def test_cn_replacement_final_failure_restores_old_source_and_blobs(tmp_path: Path) -> None:
    """replacement final meta 失败必须回滚 reset 与新 blobs，恢复完整旧版本。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        source_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        source_repository=source_repository,
        blob_repository=blob_repository,
    )
    _collect_events(pipeline)
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    handle = source_repository.get_source_handle("600519", document_id, SourceKind.FILING)
    old_meta = source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    old_pdf = blob_repository.read_file_bytes(handle, f"{document_id}.pdf")
    old_docling = blob_repository.read_file_bytes(handle, f"{document_id}_docling.json")
    source_repository.fail_final = True
    discovery.pdf_bytes = _PDF_BYTES + b"replacement"

    result = _final_result(_collect_events(pipeline, overwrite=True))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    assert source_repository.get_source_meta("600519", document_id, SourceKind.FILING) == old_meta
    assert blob_repository.read_file_bytes(handle, f"{document_id}.pdf") == old_pdf
    assert blob_repository.read_file_bytes(handle, f"{document_id}_docling.json") == old_docling
    assert source_repository.rollback_calls == 1


def test_cn_replacement_success_exposes_source_blobs_and_processed_marker_together(
    tmp_path: Path,
) -> None:
    """replacement commit 成功后 final source、新 blobs 与 processed marker 同时可见。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )
    _collect_events(pipeline)
    document_id, internal_document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    pipeline.processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=internal_document_id,
            source_kind=SourceKind.FILING.value,
            form_type="FY",
            meta={"reprocess_required": False},
            sections=[],
            tables=[],
        )
    )
    replacement_pdf = _PDF_BYTES + b"replacement"
    discovery.pdf_bytes = replacement_pdf
    discovery.candidates = (_candidate(source_id="A2", etag='"v2"'),)

    result = _final_result(_collect_events(pipeline))

    source_meta = pipeline.source_repository.get_source_meta(
        "600519",
        document_id,
        SourceKind.FILING,
    )
    processed_meta = pipeline.processed_repository.get_processed_meta("600519", document_id)
    handle = pipeline.source_repository.get_source_handle("600519", document_id, SourceKind.FILING)
    assert result["status"] == "ok"
    assert source_meta["ingest_complete"] is True
    assert pipeline.blob_repository.read_file_bytes(handle, f"{document_id}.pdf") == replacement_pdf
    assert pipeline.blob_repository.read_file_bytes(handle, f"{document_id}_docling.json") == _DOCLING_BYTES
    assert processed_meta["reprocess_required"] is True


def test_cn_active_batch_sync_cancelled_error_rolls_back_once(tmp_path: Path) -> None:
    """同步抛出的 asyncio.CancelledError 必须触发一次 operation rollback。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        source_repository,
    )
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    expected = asyncio.CancelledError("sync cancel")
    checks = 0

    def cancel_during_batch() -> bool:
        """第三个 batch 阶段检查同步抛出预构造取消异常。"""

        nonlocal checks
        checks += 1
        if checks == 3:
            raise expected
        return False

    candidate = _candidate()
    with pytest.raises(asyncio.CancelledError) as exc_info:
        _cn_download_filing_workflow._commit_cn_filing_assets_batch(
            source_repository=source_repository,
            blob_repository=blob_repository,
            processed_repository=processed_repository,
            ticker="600519",
            document_id="fil_cancelled",
            internal_document_id="fil_cancelled",
            form_type="FY",
            pdf_filename="fil_cancelled.pdf",
            docling_filename="fil_cancelled_docling.json",
            pdf_bytes=_PDF_BYTES,
            docling_json_bytes=_DOCLING_BYTES,
            candidate=candidate,
            profile=CnCompanyProfile(
                provider="cninfo",
                company_id="CNINFO:9900000600",
                company_name="贵州茅台",
                ticker="600519",
            ),
            pdf_sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
            remote_fingerprint="remote",
            source_fingerprint="source",
            previous_completed_meta=None,
            source_meta_exists=False,
            cancel_checker=cancel_during_batch,
            module="TEST",
        )

    assert exc_info.value is expected
    assert source_repository.rollback_calls == 1
    assert source_repository.commit_calls == 0
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("600519", "fil_cancelled", SourceKind.FILING)


def test_cn_commit_failure_does_not_trigger_caller_rollback_or_success(tmp_path: Path) -> None:
    """CN commit 失败后不得二次 rollback，也不得投影 filing success。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set)
    source_repository.fail_commit = True
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        source_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        source_repository=source_repository,
        blob_repository=blob_repository,
    )

    events = _collect_events(pipeline)
    result = _final_result(events)
    summary = result["summary"]

    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    assert source_repository.commit_calls == 1
    assert source_repository.rollback_calls == 0
    assert DownloadEventType.FILING_COMPLETED not in {
        event.event_type for event in events
    }
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("600519", "fil2024", SourceKind.FILING)


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


def test_cn_pdf_download_failure_leaves_document_absent(tmp_path: Path) -> None:
    """PDF download exception 发生在 batch 外，不得创建 source 或 blob。"""

    discovery = _FailingDownloadDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(),),
    )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    result = _final_result(_collect_events(pipeline))
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )


def test_cn_docling_conversion_failure_leaves_document_absent(tmp_path: Path) -> None:
    """Docling conversion exception 发生在 batch 外，不得创建 source 或 blob。"""

    def fail_conversion(raw_data: bytes, stream_name: str) -> bytes:
        """抛出固定 Docling conversion 异常。"""

        del raw_data, stream_name
        raise RuntimeError("forced Docling conversion failure")

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=fail_conversion,
    )

    result = _final_result(_collect_events(pipeline))
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )


def test_cn_download_cancel_after_pdf_download_does_not_start_docling(
    tmp_path: Path,
) -> None:
    """PDF 已下载后取消时不应启动 Docling，也不计为 failed filing。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    cancel_state = _CancelState()

    async def _collect_with_event_cancel() -> list[DownloadEvent]:
        """收集事件并在 PDF 下载事件后触发取消。

        Args:
            无。

        Returns:
            下载事件列表。

        Raises:
            AssertionError: 下游断言失败时由测试抛出。
        """

        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="FY",
            start_date="2024",
            end_date="2026",
            overwrite=False,
            cancel_checker=cancel_state,
        ):
            events.append(event)
            if event.event_type is DownloadEventType.FILE_DOWNLOADED:
                cancel_state.cancelled = True
        return events

    events = asyncio.run(_collect_with_event_cancel())
    result = _final_result(events)
    summary = result["summary"]

    assert result["status"] == "cancelled"
    assert isinstance(summary, dict)
    assert summary["failed"] == 0
    assert discovery.download_calls == 1
    assert converter.calls == 0
    assert DownloadEventType.CONVERSION_STARTED not in {
        event.event_type for event in events
    }


def test_cn_outer_generator_close_before_conversion_leaves_no_document(tmp_path: Path) -> None:
    """outer generator 在 pre-commit progress yield 关闭时不得留下 active batch 或 partial。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    async def close_after_pdf_event() -> None:
        """消费到 FILE_DOWNLOADED 后显式关闭 outer generator。"""

        stream = cast(
            AsyncGenerator[DownloadEvent, None],
            pipeline.download_stream(
                ticker="600519",
                form_type="FY",
                start_date="2024",
                end_date="2026",
                overwrite=False,
            ),
        )
        async for event in stream:
            if event.event_type is DownloadEventType.FILE_DOWNLOADED:
                await stream.aclose()
                return
        raise AssertionError("未观察到 FILE_DOWNLOADED")

    asyncio.run(close_after_pdf_event())
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )


def test_cn_inner_generator_close_before_conversion_leaves_no_document(tmp_path: Path) -> None:
    """single-filing generator 在 pre-commit yield 关闭时不得创建 partial document。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    candidate = _candidate()
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(candidate,))

    async def close_inner_after_pdf_event() -> None:
        """消费到 FILE_DOWNLOADED 后显式关闭 single-filing generator。"""

        stream = cast(
            AsyncGenerator[DownloadEvent, None],
            _cn_download_filing_workflow.run_cn_download_single_filing_stream(
                source_repository=source_repository,
                blob_repository=blob_repository,
                processed_repository=processed_repository,
                discovery_client=discovery,
                pdf_download_gate=_RecordingPdfGate(),
                convert_pdf_to_docling_json=_FakeConverter(),
                ticker="600519",
                profile=CnCompanyProfile(
                    provider="cninfo",
                    company_id="CNINFO:9900000600",
                    company_name="贵州茅台",
                    ticker="600519",
                ),
                candidate=candidate,
                overwrite=False,
                cancel_checker=None,
                module="TEST",
            ),
        )
        async for event in stream:
            if event.event_type is DownloadEventType.FILE_DOWNLOADED:
                await stream.aclose()
                return
        raise AssertionError("未观察到 FILE_DOWNLOADED")

    asyncio.run(close_inner_after_pdf_event())
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )


def test_cn_download_cancel_after_docling_convert_skips_source_commit(
    tmp_path: Path,
) -> None:
    """Docling convert 后取消时不创建任何可见 source 或 blob。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    cancel_state = _CancelState()
    converter = _CancelAfterConvertConverter(cancel_state=cancel_state)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline, cancel_checker=cancel_state)
    result = _final_result(events)
    summary = result["summary"]
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    assert result["status"] == "cancelled"
    assert isinstance(summary, dict)
    assert summary["failed"] == 0
    assert converter.calls == 1
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )
    assert DownloadEventType.FILING_COMPLETED not in {
        event.event_type for event in events
    }


def test_cn_cancel_checker_preserves_cancel_exception_object() -> None:
    """取消检查器主动抛出的 CN/HK 取消异常应原样传播。"""

    expected = CnDownloadCancelledError("caller cancelled")

    def _raise_cancelled() -> bool:
        """抛出预构造取消异常。

        Args:
            无。

        Returns:
            不返回。

        Raises:
            CnDownloadCancelledError: 始终抛出预构造异常。
        """

        raise expected

    try:
        _cn_download_workflow._is_cancel_requested(_raise_cancelled)
    except CnDownloadCancelledError as exc:
        assert exc is expected
    else:
        raise AssertionError("应传播原始 CnDownloadCancelledError")


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
