"""CN/HK download workflow 单元测试。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Optional, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.company_meta_contract import CompanyMetaCommitIntent
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    DocumentMeta,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedHandle,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import (
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
)
from dayu.fins.pipelines import cn_download_workflow as _cn_download_workflow
from dayu.fins.pipelines import cn_download_filing_workflow as _cn_download_filing_workflow
from dayu.fins.pipelines import cn_download_models as _cn_download_models
from dayu.fins.pipelines import cn_download_rebuild as _cn_download_rebuild
from dayu.fins.pipelines.cn_download_models import (
    CnDownloadCancelledError,
    CnCompanyProfile,
    CnFiscalPeriod,
    CnMarketKind,
    CnReportCandidate,
    CnReportPeriodProjection,
    CnReportQuery,
    CnSourceProvider,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionCancelledError,
    DoclingConversionConfig,
    DoclingConversionResult,
    DoclingConverter,
)
from dayu.fins.pipelines.cn_form_utils import (
    CnDownloadPeriodPolicy,
    build_cn_filing_ids,
    resolve_download_period_policy,
)
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import FsBatchingRepository, FsCompanyMetaRepository, FsDocumentBlobRepository
from dayu.fins.storage import FsFilingMaintenanceRepository, FsProcessedDocumentRepository
from dayu.fins.storage import (
    FsSourceDocumentRepository,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'


def test_download_period_policy_owns_market_defaults_and_explicit_forms() -> None:
    """期间 policy 应唯一投影市场 bare default 与显式 forms。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 三集合市场 contract 漂移时抛出。
    """

    assert resolve_download_period_policy(None, "CN") == CnDownloadPeriodPolicy(
        effective_periods=("FY", "H1", "Q1", "Q3"),
        discovery_periods=("FY", "H1", "Q1", "Q3"),
        missing_eligible_periods=("FY", "H1", "Q1", "Q3"),
    )
    assert resolve_download_period_policy(None, "HK") == CnDownloadPeriodPolicy(
        effective_periods=("FY", "H1"),
        discovery_periods=("FY", "H1", "Q1", "Q2", "Q3", "Q4"),
        missing_eligible_periods=("FY", "H1"),
    )
    assert resolve_download_period_policy(("四季报", "二季报", "Q2"), "CN") == (
        CnDownloadPeriodPolicy(
            effective_periods=("Q2", "Q4"),
            discovery_periods=("Q2", "Q4"),
            missing_eligible_periods=("Q2", "Q4"),
        )
    )
    assert resolve_download_period_policy(("Q4", "Q2"), "HK") == CnDownloadPeriodPolicy(
        effective_periods=("Q2", "Q4"),
        discovery_periods=("Q2", "Q4"),
        missing_eligible_periods=("Q2", "Q4"),
    )


def test_download_period_policy_rejects_noncanonical_direct_construction() -> None:
    """policy owner 应拒绝空、重复、乱序和集合包含关系错误。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一非法 policy 未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="effective_periods 不能为空"):
        CnDownloadPeriodPolicy(
            effective_periods=(),
            discovery_periods=("FY",),
            missing_eligible_periods=("FY",),
        )
    with pytest.raises(ValueError, match="重复"):
        CnDownloadPeriodPolicy(
            effective_periods=("FY", "FY"),
            discovery_periods=("FY",),
            missing_eligible_periods=("FY",),
        )
    with pytest.raises(ValueError, match="canonical"):
        CnDownloadPeriodPolicy(
            effective_periods=("H1", "FY"),
            discovery_periods=("FY", "H1"),
            missing_eligible_periods=("FY",),
        )
    with pytest.raises(ValueError, match="missing_eligible_periods"):
        CnDownloadPeriodPolicy(
            effective_periods=("FY",),
            discovery_periods=("FY", "H1"),
            missing_eligible_periods=("FY", "H1"),
        )
    with pytest.raises(ValueError, match="effective_periods"):
        CnDownloadPeriodPolicy(
            effective_periods=("FY", "H1"),
            discovery_periods=("FY",),
            missing_eligible_periods=("FY",),
        )

    with pytest.raises(ValueError, match="form 输入"):
        resolve_download_period_policy(("not-a-period",), "CN")


class _BatchIdentityCnBatchingRepository(FsBatchingRepository):
    """记录 CN/HK 顶层事务 owner 及显式 token identity 的 batching spy。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet) -> None:
        """初始化 source batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self.active_token: BatchToken | None = None
        self.phases: list[tuple[str, str]] = []
        self.begin_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.fail_commit_call: int | None = None

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启 batch 并记录 token。"""

        token = super().begin_batch(ticker)
        self.active_token = token
        self.begin_calls += 1
        self.phases.append(("begin", token.transaction_id))
        return token

    def commit_batch(self, batch: BatchToken) -> None:
        """记录 caller 唯一 commit，并模拟 storage owner 消费 token 的失败。"""

        self.record_phase("commit", batch)
        self.commit_calls += 1
        if self.fail_commit_call == self.commit_calls:
            FsBatchingRepository.rollback_batch(self, batch)
            self.active_token = None
            raise OSError("forced CN storage commit failure")
        super().commit_batch(batch)
        self.active_token = None

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录 caller operation rollback 并转发。"""

        self.record_phase("rollback", batch)
        self.rollback_calls += 1
        super().rollback_batch(batch)
        self.active_token = None

    def record_phase(self, phase: str, token: BatchToken) -> None:
        """记录阶段与 invocation-time 显式 token identity。"""

        assert self.active_token == token
        self.phases.append((phase, token.transaction_id))


class _BatchIdentityCnSourceRepository(FsSourceDocumentRepository):
    """记录 CN/HK source mutation 显式 batch identity 的 source spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        batching_repository: _BatchIdentityCnBatchingRepository,
    ) -> None:
        """初始化 source batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._batching_repository = batching_repository
        self.fail_final = False

    def reset_source_document(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> None:
        """记录 reset 所处 token 后转发。"""

        self._batching_repository.record_phase("reset", batch)
        super().reset_source_document(ticker, document_id, source_kind, batch=batch)

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """记录唯一 final create 的显式 token。"""

        self._batching_repository.record_phase("final_meta", batch)
        if self.fail_final:
            raise RuntimeError("forced CN final meta failure")
        return super().create_source_document(req, source_kind, batch=batch)

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """记录唯一 final update 的显式 token。"""

        self._batching_repository.record_phase("final_meta", batch)
        if self.fail_final:
            raise RuntimeError("forced CN final meta failure")
        return super().update_source_document(req, source_kind, batch=batch)


class _BatchIdentityCnBlobRepository(FsDocumentBlobRepository):
    """记录 CN/HK blob 写入所处 token 的真实文件仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        batching_repository: _BatchIdentityCnBatchingRepository,
    ) -> None:
        """初始化 blob batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._batching_repository = batching_repository

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录 PDF/Docling blob 阶段后转发真实写入。"""

        self._batching_repository.record_phase(f"blob:{filename.rsplit('.', 1)[-1]}", batch)
        return super().store_file(
            handle,
            filename,
            data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )


class _BatchIdentityCnProcessedRepository(FsProcessedDocumentRepository):
    """记录 processed marker 与 source mutation 共享 token 的 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        batching_repository: _BatchIdentityCnBatchingRepository,
    ) -> None:
        """初始化 processed batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._batching_repository = batching_repository

    def get_processed_meta(self, ticker: str, document_id: str) -> dict[str, JsonValue]:
        """优先返回真实 durable meta；缺席时驱动 marker no-op 分支。"""

        try:
            return super().get_processed_meta(ticker, document_id)
        except FileNotFoundError:
            return {"reprocess_required": False}

    def mark_processed_reprocess_required(
        self,
        ticker: str,
        document_id: str,
        required: bool,
        *,
        batch: BatchToken,
    ) -> None:
        """记录 marker 阶段并通过真实 public contract 持久化。"""

        assert required is True
        self._batching_repository.record_phase("processed_marker", batch)
        super().mark_processed_reprocess_required(
            ticker,
            document_id,
            required,
            batch=batch,
        )


class _FailingCnCompanyMetaRepository(FsCompanyMetaRepository):
    """在 company publication mutation 处失败的真实仓储 spy。"""

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """拒绝 company mutation，以验证 top-level rollback owner。"""

        del intent, batch
        raise OSError("forced company publication failure")


@dataclass
class _FakeDiscoveryClient:
    """CN discovery fake。"""

    temp_dir: Path
    candidates: tuple[CnReportCandidate, ...]
    pdf_bytes: bytes = _PDF_BYTES
    download_calls: int = 0
    queries: list[CnReportQuery] = field(default_factory=list)
    cancellation_checkpoints: list[Callable[[], None] | None] = field(default_factory=list)
    checkpoint_errors: list[RuntimeError] = field(default_factory=list)

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """返回固定公司元数据。

        Args:
            query: 下载查询。

        Returns:
            公司元数据。

        Raises:
            无。
        """

        provider: CnSourceProvider = "cninfo" if query.market == "CN" else "hkexnews"
        company_id = "CNINFO:9900000600" if query.market == "CN" else "HKEX:7609"
        return CnCompanyProfile(
            provider=provider,
            company_id=company_id,
            company_name="贵州茅台" if query.market == "CN" else "腾讯控股",
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """返回测试候选。

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
        self.queries.append(query)
        self.cancellation_checkpoints.append(cancellation_checkpoint)
        if cancellation_checkpoint is not None:
            try:
                cancellation_checkpoint()
            except RuntimeError as exc:
                self.checkpoint_errors.append(exc)
                raise
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


class _FirstCandidateFailureDiscoveryClient(_FakeDiscoveryClient):
    """仅让第一个 candidate 失败、后续 candidate 正常完成的 fake。"""

    def __init__(
        self,
        *,
        temp_dir: Path,
        candidates: tuple[CnReportCandidate, ...],
        failure: Exception,
    ) -> None:
        """初始化单 candidate failure fake。

        Args:
            failure: 首个 candidate 应原样抛出的异常。
            temp_dir: 测试临时目录。
            candidates: 固定候选序列。

        Raises:
            TypeError: fake 构造字段非法时抛出。
        """

        super().__init__(temp_dir=temp_dir, candidates=candidates)
        self.failure = failure

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """首个 candidate 抛错，后续复用成功实现。

        Args:
            candidate: 当前候选。

        Returns:
            非首个 candidate 的内存 PDF 资产。

        Raises:
            Exception: 首个 candidate 抛出预构造异常。
        """

        if candidate.source_id == "A1":
            self.download_calls += 1
            raise self.failure
        return super().download_report_pdf(candidate)


@dataclass
class _FakeConverter:
    """typed Docling conversion fake。"""

    calls: int = 0

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

        del input_bytes, stream_name, config, cancellation
        self.calls += 1
        return DoclingConversionResult(
            json_bytes=_DOCLING_BYTES,
            size=len(_DOCLING_BYTES),
            sha256=hashlib.sha256(_DOCLING_BYTES).hexdigest(),
        )


@dataclass
class _FailingConverter:
    """按配置抛出预构造异常的 typed Docling runner。"""

    failure: Exception
    calls: int = 0

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """抛出预构造异常。

        Args:
            pdf_bytes: PDF 字节。
            stream_name: 流名称。
            config: 闭合转换配置。
            cancellation: canonical 取消 token。

        Returns:
            不返回。

        Raises:
            Exception: 原样抛出 ``failure``。
        """

        del input_bytes, stream_name, config, cancellation
        self.calls += 1
        raise self.failure


@dataclass
class _FilingFailureProjectionSpy:
    """记录 CN/HK 单 filing failure projection 调用的 spy。"""

    delegate: Callable[[Exception], tuple[str, str]]
    calls: list[Exception] = field(default_factory=list)

    def __call__(self, error: Exception) -> tuple[str, str]:
        """记录异常并调用真实 owner helper。

        Args:
            error: 待投影异常。

        Returns:
            真实 owner helper 返回的原因 pair。

        Raises:
            无。
        """

        self.calls.append(error)
        return self.delegate(error)


@dataclass
class _CancelAfterConvertConverter:
    """转换返回前触发取消的 typed Docling runner。"""

    cancel_state: "_CancelState"
    calls: int = 0

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回固定 Docling JSON 并设置取消状态。

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

        del input_bytes, stream_name, config, cancellation
        self.calls += 1
        self.cancel_state.cancelled = True
        return DoclingConversionResult(
            json_bytes=_DOCLING_BYTES,
            size=len(_DOCLING_BYTES),
            sha256=hashlib.sha256(_DOCLING_BYTES).hexdigest(),
        )


@dataclass
class _CancelState(CancellationToken):
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

    def is_cancelled(self) -> bool:
        """返回当前取消状态。

        Returns:
            已取消时返回 ``True``。
        """

        return self.cancelled

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Returns:
            已取消时返回固定原因，否则返回 ``None``。
        """

        return "test_cancelled" if self.cancelled else None

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Returns:
            本测试不需要时间，返回 ``None``。
        """

        return None


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

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """断言转换阶段没有持有 PDF 下载 gate。

        Args:
            pdf_bytes: PDF 字节。
            stream_name: 流名称。
            config: 闭合转换配置。
            cancellation: canonical 取消 token。

        Returns:
            Docling JSON 字节。

        Raises:
            AssertionError: Docling 转换发生在 gate 内时抛出。
        """

        assert self.gate.active is False
        return await super().convert_to_json_bytes(
            input_bytes,
            stream_name,
            config=config,
            cancellation=cancellation,
        )


def _candidate(
    *,
    source_id: str = "A1",
    etag: str = '"v1"',
    fiscal_year: int = 2024,
    fiscal_period: CnFiscalPeriod = "FY",
    filing_date: str | None = None,
    provider: CnSourceProvider = "cninfo",
    covered_periods: tuple[CnFiscalPeriod, ...] | None = None,
) -> CnReportCandidate:
    """构造 CN 候选。

    Args:
        source_id: 来源内文档 ID。
        etag: 远端 ETag。
        fiscal_year: 财年。
        fiscal_period: 财期。
        filing_date: 披露日期。
        provider: 候选来源 provider。
        covered_periods: 显式覆盖财期；省略时构造 identity singleton。

    Returns:
        候选报告。

    Raises:
        无。
    """

    return CnReportCandidate(
        provider=provider,
        source_id=source_id,
        source_url=f"https://static.cninfo.test/{source_id}.pdf",
        title=f"贵州茅台：{fiscal_year}年{fiscal_period}报告",
        language="zh",
        filing_date=filing_date or f"{fiscal_year + 1}-04-01",
        fiscal_year=fiscal_year,
        period_projection=CnReportPeriodProjection(
            identity_period=fiscal_period,
            covered_periods=(fiscal_period,) if covered_periods is None else covered_periods,
        ),
        amended=False,
        content_length=len(_PDF_BYTES),
        etag=etag,
        last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
    )


def _build_pipeline(
    *,
    tmp_path: Path,
    discovery: _FakeDiscoveryClient,
    hk_discovery: _FakeDiscoveryClient | None = None,
    converter: DoclingConverter,
    pdf_download_gate: CnDownloadPdfGateProtocol | None = None,
    repository_set: _FsRepositorySet | None = None,
    batching_repository: FsBatchingRepository | None = None,
    company_repository: FsCompanyMetaRepository | None = None,
    source_repository: FsSourceDocumentRepository | None = None,
    blob_repository: FsDocumentBlobRepository | None = None,
    processed_repository: FsProcessedDocumentRepository | None = None,
) -> CnPipeline:
    """构造注入 fake downloader / converter 的 CnPipeline。

    Args:
        tmp_path: 临时工作区目录。
        discovery: fake discovery client。
        hk_discovery: 可选 HK fake discovery client；缺省时使用 production 默认装配。
        converter: fake Docling conversion runner。
        pdf_download_gate: 可选 PDF 下载 gate。
        repository_set: 可选共享 FS 仓储集合。
        batching_repository: 可选 batching 仓储 spy。
        company_repository: 可选 company 仓储 spy。
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
        batching_repository=batching_repository or FsBatchingRepository(tmp_path, repository_set=shared_repository_set),
        company_repository=company_repository
        or FsCompanyMetaRepository(tmp_path, repository_set=shared_repository_set),
        source_repository=source_repository
        or FsSourceDocumentRepository(tmp_path, repository_set=shared_repository_set),
        processed_repository=processed_repository
        or FsProcessedDocumentRepository(tmp_path, repository_set=shared_repository_set),
        blob_repository=blob_repository or FsDocumentBlobRepository(tmp_path, repository_set=shared_repository_set),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            tmp_path,
            repository_set=shared_repository_set,
        ),
        cn_discovery_client=discovery,
        hk_discovery_client=hk_discovery,
        pdf_download_gate=pdf_download_gate,
        docling_converter=converter,
    )


def _collect_events(
    pipeline: CnPipeline,
    *,
    start_is_explicit: bool,
    form_type: str | None = "FY",
    overwrite: bool = False,
    cancel_checker: Callable[[], bool] | None = None,
) -> list[DownloadEvent]:
    """同步收集 download_stream 事件。

    Args:
        pipeline: 待执行 pipeline。
        start_is_explicit: 起始日期是否来自调用方显式输入。
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
            start_is_explicit=start_is_explicit,
            cancel_checker=cancel_checker,
        )
    )


def test_repeat_cn_company_publication_rolls_back_zero_mutation_batch(
    tmp_path: Path,
) -> None:
    """fresh 且 identity 未变化时 caller 必须 rollback，禁止 full-tree swap。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 明确 ``None`` mutation signal 未被 caller 消费时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
    )
    profile = CnCompanyProfile(
        provider="cninfo",
        company_id="CNINFO:9900000600",
        company_name="贵州茅台",
        ticker="600519",
    )

    _cn_download_workflow._publish_cn_company_after_repair(
        host=pipeline,
        profile=profile,
        normalized_ticker="600519",
        ticker_aliases=None,
    )
    published_meta_path = tmp_path / "portfolio" / "600519" / "meta.json"
    first_meta = published_meta_path.read_bytes()
    _cn_download_workflow._publish_cn_company_after_repair(
        host=pipeline,
        profile=profile,
        normalized_ticker="600519",
        ticker_aliases=None,
    )

    assert batching_repository.commit_calls == 1
    assert batching_repository.rollback_calls == 1
    assert batching_repository.phases[-2][0] == "begin"
    assert batching_repository.phases[-1][0] == "rollback"
    assert published_meta_path.read_bytes() == first_meta


async def _collect_events_async(
    *,
    pipeline: CnPipeline,
    ticker: str,
    form_type: str | None,
    start_date: str | None,
    end_date: str,
    overwrite: bool,
    start_is_explicit: bool,
    cancel_checker: Callable[[], bool] | None = None,
) -> list[DownloadEvent]:
    """异步收集 download_stream 事件。

    Args:
        pipeline: 待执行 pipeline。
        ticker: 股票代码。
        form_type: form 过滤。
        start_date: 可选开始日期；``None`` 表示使用各财期默认业务窗口。
        end_date: 结束日期。
        overwrite: 是否覆盖。
        start_is_explicit: 起始日期是否来自调用方显式输入。
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
        start_is_explicit=start_is_explicit,
        cancel_checker=cancel_checker,
    ):
        events.append(event)
    return events


def _collect_single_filing_events(
    *,
    pipeline: CnPipeline,
    candidate: CnReportCandidate,
    cancel_checker: Callable[[], bool] | None = None,
) -> list[DownloadEvent]:
    """同步收集真实 CN/HK 单 filing owner 事件。

    Args:
        pipeline: 提供真实仓储与注入依赖的 CN pipeline。
        candidate: 待执行候选。
        cancel_checker: 可选取消检查器。

    Returns:
        单 filing owner 产生的完整事件列表。

    Raises:
        Exception: owner 未消费的异常原样传播。
    """

    return asyncio.run(
        _collect_single_filing_events_async(
            pipeline=pipeline,
            candidate=candidate,
            cancel_checker=cancel_checker,
        )
    )


async def _collect_single_filing_events_async(
    *,
    pipeline: CnPipeline,
    candidate: CnReportCandidate,
    cancel_checker: Callable[[], bool] | None,
) -> list[DownloadEvent]:
    """异步收集真实 CN/HK 单 filing owner 事件。

    Args:
        pipeline: 提供真实仓储与注入依赖的 CN pipeline。
        candidate: 待执行候选。
        cancel_checker: 可选取消检查器。

    Returns:
        单 filing owner 产生的完整事件列表。

    Raises:
        Exception: owner 未消费的异常原样传播。
    """

    events: list[DownloadEvent] = []
    async for event in _cn_download_filing_workflow.run_cn_download_single_filing_stream(
        batching_repository=pipeline.batching_repository,
        source_repository=pipeline.source_repository,
        blob_repository=pipeline.blob_repository,
        processed_repository=pipeline.processed_repository,
        discovery_client=pipeline.cn_discovery_client,
        pdf_download_gate=pipeline.pdf_download_gate,
        docling_conversion_runner=pipeline.docling_conversion_runner,
        ticker="600519",
        profile=CnCompanyProfile(
            provider="cninfo",
            company_id="CNINFO:9900000600",
            company_name="贵州茅台",
            ticker="600519",
        ),
        candidate=candidate,
        overwrite=False,
        cancel_checker=cancel_checker,
        module="TEST",
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


def test_cn_bare_download_consumes_policy_for_query_filters_and_missing(tmp_path: Path) -> None:
    """CN bare download 应同源消费 FY/H1/Q1/Q3 三个 policy 投影。

    Args:
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: query、effective filters 或 missing 发生分叉时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    result = _final_result(
        _collect_events(
            pipeline,
            start_is_explicit=True,
            form_type=None,
        )
    )

    assert discovery.queries[0].discovery_periods == ("FY", "H1", "Q1", "Q3")
    filters = result["filters"]
    assert isinstance(filters, dict)
    assert filters["forms"] == ["FY", "H1", "Q1", "Q3"]
    start_dates = filters["start_dates"]
    assert isinstance(start_dates, dict)
    assert set(start_dates) == {"FY", "H1", "Q1", "Q3"}
    assert result["missing_periods"] == ["FY", "H1", "Q1", "Q3"]


def test_cn_bare_download_projects_actual_default_period_window_start_dates(
    tmp_path: Path,
) -> None:
    """未显式指定起点时应投影 FY 五年与其它财期两年的实际业务窗口。

    Args:
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: filters 与逐期 business window 不同源时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    events = asyncio.run(
        _collect_events_async(
            pipeline=pipeline,
            ticker="600519",
            form_type=None,
            start_date=None,
            end_date="2026",
            overwrite=False,
            start_is_explicit=False,
        )
    )
    result = _final_result(events)
    filters = result["filters"]
    assert isinstance(filters, dict)
    start_dates = filters["start_dates"]
    assert start_dates == {
        "FY": "2021-11-01",
        "H1": "2024-11-01",
        "Q1": "2024-11-01",
        "Q3": "2024-11-01",
    }


def test_cn_fiscal_period_order_is_declared_in_owner_module_exports() -> None:
    """canonical 财期顺序应由 owner 模块的显式公共清单声明。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: owner 常量遗漏于 ``__all__`` 时抛出。
    """

    assert "CN_FISCAL_PERIOD_ORDER" in _cn_download_models.__all__


@pytest.mark.parametrize(
    ("candidates", "expected_missing"),
    [
        ((), ["FY", "H1"]),
        (
            (
                _candidate(
                    source_id="HK-Q2",
                    fiscal_period="Q2",
                    provider="hkexnews",
                    covered_periods=("H1", "Q2"),
                ),
                _candidate(
                    source_id="HK-Q4",
                    fiscal_period="Q4",
                    provider="hkexnews",
                    covered_periods=("FY", "Q4"),
                ),
            ),
            ["FY", "H1"],
        ),
        (
            (
                _candidate(source_id="HK-FY", fiscal_period="FY", provider="hkexnews"),
                _candidate(source_id="HK-H1", fiscal_period="H1", provider="hkexnews"),
            ),
            [],
        ),
    ],
)
def test_hk_bare_download_discovers_six_periods_but_only_fy_h1_are_missing_eligible(
    tmp_path: Path,
    candidates: tuple[CnReportCandidate, ...],
    expected_missing: list[str],
) -> None:
    """HK bare download 应发现六期，但 effective/missing 只承诺 FY/H1。

    Args:
        tmp_path: 临时工作区。
        candidates: fake provider 返回的实际材料。
        expected_missing: 只按 FY/H1 identity 计算的期望 missing。

    Returns:
        无。

    Raises:
        AssertionError: optional quarter 被当 mandatory 或 query 范围缩窄时抛出。
    """

    cn_discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    hk_discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=candidates)
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=cn_discovery,
        hk_discovery=hk_discovery,
        converter=_FakeConverter(),
    )

    events = asyncio.run(
        _collect_events_async(
            pipeline=pipeline,
            ticker="0700",
            form_type=None,
            start_date="2024",
            end_date="2026",
            overwrite=False,
            start_is_explicit=True,
        )
    )
    result = _final_result(events)

    assert hk_discovery.queries[0].discovery_periods == (
        "FY",
        "H1",
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    )
    filters = result["filters"]
    assert isinstance(filters, dict)
    assert filters["forms"] == ["FY", "H1"]
    start_dates = filters["start_dates"]
    assert isinstance(start_dates, dict)
    assert set(start_dates) == {"FY", "H1", "Q1", "Q2", "Q3", "Q4"}
    assert result["missing_periods"] == expected_missing


def test_cn_explicit_q2_q4_remains_effective_discovery_and_missing_policy(
    tmp_path: Path,
) -> None:
    """CN 显式 Q2/Q4 应保持可请求并在无候选时报告 missing。

    Args:
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: 显式 Q2/Q4 被 bare policy 改写时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    result = _final_result(
        _collect_events(
            pipeline,
            start_is_explicit=True,
            form_type="Q2,Q4",
        )
    )

    assert discovery.queries[0].discovery_periods == ("Q2", "Q4")
    filters = result["filters"]
    assert isinstance(filters, dict)
    assert filters["forms"] == ["Q2", "Q4"]
    assert result["missing_periods"] == ["Q2", "Q4"]


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

    events = _collect_events(pipeline, start_is_explicit=True)

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
    company_event = next(event for event in events if event.event_type is DownloadEventType.COMPANY_RESOLVED)
    company_meta = pipeline._company_repository.get_company_meta("600519")
    assert company_event.payload["company_id"] == source_meta["company_id"] == company_meta.company_id == "600519_SSE"
    assert source_meta["provider_company_id"] == "CNINFO:9900000600"
    assert source_meta["document_version"] == "v1"


def test_cn_company_publication_failure_rolls_back_once(tmp_path: Path) -> None:
    """company mutation 失败时其短事务只 rollback 一次，且不进入文档事务。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),)),
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        company_repository=_FailingCnCompanyMetaRepository(
            tmp_path,
            repository_set=repository_set,
        ),
    )

    with pytest.raises(OSError, match="forced company publication failure"):
        _collect_events(pipeline, start_is_explicit=True)

    assert batching_repository.begin_calls == 1
    assert batching_repository.commit_calls == 0
    assert batching_repository.rollback_calls == 1


def test_hk_result_coverage_projects_without_creating_extra_documents(tmp_path: Path) -> None:
    """Q4 result 与 FY report 各有一个 identity，coverage 不增加 source/manifest 数量。

    Args:
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: identity、source meta、workflow row 或 manifest 投影漂移时抛出。
    """

    q4_candidate = _candidate(
        source_id="GENERIC-Q4-RESULT",
        fiscal_period="Q4",
        provider="hkexnews",
        covered_periods=("FY", "Q4"),
    )
    fy_candidate = _candidate(
        source_id="GENERIC-FY-REPORT",
        fiscal_period="FY",
        provider="hkexnews",
    )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        hk_discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(fy_candidate, q4_candidate)),
        converter=_FakeConverter(),
    )

    result = _final_result(
        asyncio.run(
            _collect_events_async(
                pipeline=pipeline,
                ticker="0005",
                form_type=None,
                start_date="2024",
                end_date="2026",
                overwrite=False,
                start_is_explicit=True,
            )
        )
    )
    document_ids = pipeline.source_repository.list_source_document_ids("0005", SourceKind.FILING)

    assert len(document_ids) == 2
    rows = result["filings"]
    assert isinstance(rows, list)
    coverage_values: set[tuple[str, ...]] = set()
    for row in rows:
        assert isinstance(row, dict)
        raw_coverage = row["covered_fiscal_periods"]
        assert isinstance(raw_coverage, list)
        assert all(isinstance(value, str) for value in raw_coverage)
        coverage_values.add(tuple(cast(list[str], raw_coverage)))
    assert coverage_values == {
        ("FY",),
        ("FY", "Q4"),
    }
    q4_document_id = next(
        document_id
        for document_id in document_ids
        if pipeline.source_repository.get_source_meta("0005", document_id, SourceKind.FILING)["fiscal_period"] == "Q4"
    )
    q4_meta = pipeline.source_repository.get_source_meta("0005", q4_document_id, SourceKind.FILING)
    assert q4_meta["form_type"] == q4_meta["fiscal_period"] == q4_meta["report_kind"] == "Q4"
    assert q4_meta["covered_fiscal_periods"] == ["FY", "Q4"]
    assert q4_meta["source_id"] == "GENERIC-Q4-RESULT"
    assert q4_meta["source_provider"] == "hkexnews"
    assert q4_meta["source_url"] == q4_candidate.source_url

    locator = pipeline.source_repository.get_source_document_locator("0005", q4_document_id, SourceKind.FILING)
    manifest = json.loads((tmp_path / locator.parent / "filing_manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    manifest_rows = manifest["documents"]
    assert isinstance(manifest_rows, list)
    assert len(manifest_rows) == 2
    q4_manifest_rows = [row for row in manifest_rows if isinstance(row, dict) and row["document_id"] == q4_document_id]
    assert len(q4_manifest_rows) == 1
    assert q4_manifest_rows[0]["fiscal_period"] == "Q4"


@pytest.mark.parametrize(
    ("previous_meta", "expected_reason"),
    [
        (
            {
                "internal_document_id": "missing-form",
                "form_type": "",
                "files": [],
            },
            "missing_form_type",
        ),
        (
            {
                "internal_document_id": "missing-docling",
                "form_type": "FY",
                "files": [{"name": "report.pdf", "sha256": "pdf"}],
            },
            "missing_docling_json",
        ),
        (
            {
                "internal_document_id": "missing-pdf",
                "form_type": "FY",
                "files": [{"name": "report_docling.json", "sha256": "docling"}],
            },
            "missing_pdf",
        ),
    ],
)
def test_cn_rebuild_rejects_missing_complete_download_facts(
    tmp_path: Path,
    previous_meta: dict[str, JsonValue],
    expected_reason: str,
) -> None:
    """CN rebuild owner 应拒绝缺失 form、PDF 或 Docling 的完成态输入。"""

    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        converter=_FakeConverter(),
    )

    result = _cn_download_rebuild._rebuild_single_cn_download_document(
        host=pipeline,
        ticker="600519",
        document_id="fil_invalid",
        previous_meta=previous_meta,
        covered_fiscal_periods=("FY",),
    )

    assert result["status"] == "failed"
    assert result["reason_code"] == expected_reason


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (
            {
                "ingest_method": "upload",
                "fiscal_period": "FY",
                "filing_date": "2025-01-01",
            },
            False,
        ),
        (
            {
                "ingest_method": "download",
                "is_deleted": True,
                "fiscal_period": "FY",
                "filing_date": "2025-01-01",
                "covered_fiscal_periods": ["FY"],
            },
            False,
        ),
        ({"ingest_method": "download", "fiscal_period": "invalid", "filing_date": "2025-01-01"}, False),
        (
            {
                "ingest_method": "download",
                "fiscal_period": "Q1",
                "filing_date": "2025-01-01",
                "covered_fiscal_periods": ["Q1"],
            },
            False,
        ),
        (
            {
                "ingest_method": "download",
                "fiscal_period": "FY",
                "covered_fiscal_periods": ["FY"],
            },
            False,
        ),
        (
            {
                "ingest_method": "download",
                "fiscal_period": "FY",
                "filing_date": "2025-01-01",
                "covered_fiscal_periods": ["FY"],
            },
            True,
        ),
    ],
)
def test_cn_rebuild_scope_filter_contract(meta: dict[str, JsonValue], expected: bool) -> None:
    """CN rebuild 仅处理当前窗口内、未删除的 download source。"""

    window = _cn_download_rebuild.PeriodDownloadWindow(
        fiscal_period="FY",
        start_date="2024-01-01",
        end_date="2026-12-31",
    )

    projection = _cn_download_rebuild._resolve_rebuild_period_projection(
        meta=meta,
        period_windows=(window,),
    )
    assert (projection is not None) is expected


@pytest.mark.parametrize(
    "coverage_value",
    (
        None,
        "FY",
        [],
        ["FY", "FY"],
        ["Q4", "FY"],
        ["FY"],
        ["INVALID", "Q4"],
    ),
)
def test_cn_rebuild_fails_closed_on_invalid_fresh_schema_coverage(
    coverage_value: JsonValue | None,
) -> None:
    """fresh source schema 的 coverage 缟失或畸形时 rebuild 必须 fail closed。

    Args:
        coverage_value: 缺失或非法 coverage 值。

    Returns:
        无。

    Raises:
        AssertionError: rebuild 未拒绝非法 coverage 时抛出。
    """

    meta: dict[str, JsonValue] = {
        "ingest_method": "download",
        "fiscal_period": "Q4",
        "filing_date": "2025-01-01",
    }
    if coverage_value is not None:
        meta["covered_fiscal_periods"] = coverage_value
    window = _cn_download_rebuild.PeriodDownloadWindow(
        fiscal_period="Q4",
        start_date="2024-01-01",
        end_date="2026-12-31",
    )

    with pytest.raises(ValueError, match="covered_fiscal_periods"):
        _cn_download_rebuild._resolve_rebuild_period_projection(
            meta=meta,
            period_windows=(window,),
        )


def test_cn_rebuild_cancel_checker_contract() -> None:
    """CN rebuild 应把显式取消收敛为取消，把检查器故障保留为错误。"""

    expected = CnDownloadCancelledError("rebuild cancelled")

    def _raise_cancelled() -> bool:
        """抛出调用方取消异常。"""

        raise expected

    def _raise_failure() -> bool:
        """抛出取消检查器故障。"""

        raise ValueError("broken checker")

    with pytest.raises(CnDownloadCancelledError) as cancel_error:
        _cn_download_rebuild._is_cancel_requested(_raise_cancelled)
    assert cancel_error.value is expected
    with pytest.raises(ValueError, match="broken checker"):
        _cn_download_rebuild._is_cancel_requested(_raise_failure)
    assert _cn_download_rebuild._optional_period(None) is None


def test_cn_workflow_cancel_and_log_projection_contract() -> None:
    """ticker owner 应传播取消、显式报告 checker 故障并稳定投影日志数值。"""

    def _raise_failure() -> bool:
        """抛出取消检查器故障。"""

        raise ValueError("broken checker")

    with pytest.raises(ValueError, match="broken checker"):
        _cn_download_workflow._is_cancel_requested(_raise_failure)
    with pytest.raises(CnDownloadCancelledError, match="操作已被取消"):
        _cn_download_workflow._raise_if_cancelled(
            module="TEST",
            ticker="600519",
            document_id="fil_cancelled",
            cancel_checker=lambda: True,
        )
    assert _cn_download_workflow._log_int(1.5) == 1
    assert _cn_download_workflow._log_int("invalid") == 0
    assert _cn_download_workflow._log_int([]) == 0


def test_cn_replacement_separates_company_and_document_transactions(
    tmp_path: Path,
) -> None:
    """company 独立提交，replacement 全部文档 mutation 共享第二个 token。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    processed_repository = _BatchIdentityCnProcessedRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
        processed_repository=processed_repository,
    )
    _collect_events(pipeline, start_is_explicit=True)
    batching_repository.phases.clear()
    begin_calls = batching_repository.begin_calls
    commit_calls = batching_repository.commit_calls
    rollback_calls = batching_repository.rollback_calls
    discovery.pdf_bytes = _PDF_BYTES + b"replacement"

    result = _final_result(_collect_events(pipeline, start_is_explicit=True, overwrite=True))

    phases = [phase for phase, _ in batching_repository.phases]
    batch_ids = {batch_id for _, batch_id in batching_repository.phases}
    assert result["status"] == "ok"
    assert phases == [
        "begin",
        "rollback",
        "begin",
        "reset",
        "blob:pdf",
        "blob:json",
        "final_meta",
        "processed_marker",
        "commit",
    ]
    assert len(batch_ids) == 2
    assert batching_repository.begin_calls == begin_calls + 2
    assert batching_repository.commit_calls == commit_calls + 1
    assert batching_repository.rollback_calls == rollback_calls + 1


def test_cn_complete_phase_a_skips_transport_without_source_mutation(tmp_path: Path) -> None:
    """Phase A COMPLETE+overwrite=False 必须零 PDF 传输且不打开 source batch。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
    )
    _collect_events(pipeline, start_is_explicit=True)
    batching_repository.phases.clear()
    begin_calls = batching_repository.begin_calls
    commit_calls = batching_repository.commit_calls
    rollback_calls = batching_repository.rollback_calls
    download_calls = discovery.download_calls
    discovery.candidates = (_candidate(source_id="A2", etag='"v2"'),)

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))

    phases = [phase for phase, _ in batching_repository.phases]
    batch_ids = {batch_id for _, batch_id in batching_repository.phases}
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["skipped"] == 1
    assert phases == ["begin", "rollback"]
    assert len(batch_ids) == 1
    assert batching_repository.begin_calls == begin_calls + 1
    assert batching_repository.commit_calls == commit_calls
    assert batching_repository.rollback_calls == rollback_calls + 1
    assert discovery.download_calls == download_calls


def test_cn_replacement_final_failure_restores_old_source_and_blobs(tmp_path: Path) -> None:
    """replacement final meta 失败必须回滚 reset 与新 blobs，恢复完整旧版本。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
    )
    _collect_events(pipeline, start_is_explicit=True)
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
    rollback_calls = batching_repository.rollback_calls
    source_repository.fail_final = True
    discovery.pdf_bytes = _PDF_BYTES + b"replacement"

    result = _final_result(_collect_events(pipeline, start_is_explicit=True, overwrite=True))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    assert source_repository.get_source_meta("600519", document_id, SourceKind.FILING) == old_meta
    assert blob_repository.read_file_bytes(handle, f"{document_id}.pdf") == old_pdf
    assert blob_repository.read_file_bytes(handle, f"{document_id}_docling.json") == old_docling
    assert batching_repository.rollback_calls == rollback_calls + 2


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
    _collect_events(pipeline, start_is_explicit=True)
    document_id, internal_document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    setup_batch = pipeline.batching_repository.begin_batch("600519")
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
        ),
        batch=setup_batch,
    )
    pipeline.batching_repository.commit_batch(setup_batch)
    replacement_pdf = _PDF_BYTES + b"replacement"
    discovery.pdf_bytes = replacement_pdf
    discovery.candidates = (_candidate(source_id="A2", etag='"v2"'),)

    result = _final_result(_collect_events(pipeline, start_is_explicit=True, overwrite=True))

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


def test_cn_rebuild_updates_only_source_in_one_batch(tmp_path: Path) -> None:
    """CN rebuild 必须在一个短事务内只更新 source，不读写 processed。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    processed_repository = _BatchIdentityCnProcessedRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),)),
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
        processed_repository=processed_repository,
    )
    _collect_events(pipeline, start_is_explicit=True)
    document_id, internal_document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    setup_batch = batching_repository.begin_batch("600519")
    processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=internal_document_id,
            source_kind=SourceKind.FILING.value,
            form_type="FY",
            meta={"reprocess_required": False},
            sections=[],
            tables=[],
        ),
        batch=setup_batch,
    )
    batching_repository.commit_batch(setup_batch)
    batching_repository.phases.clear()
    begin_calls = batching_repository.begin_calls
    commit_calls = batching_repository.commit_calls
    rollback_calls = batching_repository.rollback_calls
    source_handle = source_repository.get_source_handle("600519", document_id, SourceKind.FILING)
    source_pdf_before = blob_repository.read_file_bytes(source_handle, f"{document_id}.pdf")
    source_docling_before = blob_repository.read_file_bytes(
        source_handle,
        f"{document_id}_docling.json",
    )

    result = pipeline.download(
        ticker="600519",
        form_type="FY",
        start_date="2024",
        end_date="2026",
        overwrite=False,
        rebuild=True,
        start_is_explicit=True,
    )

    phase_names = [phase for phase, _ in batching_repository.phases]
    transaction_ids = {transaction_id for _, transaction_id in batching_repository.phases}
    processed_meta = FsProcessedDocumentRepository.get_processed_meta(
        processed_repository,
        "600519",
        document_id,
    )
    assert result["status"] == "ok"
    assert result["missing_periods"] == []
    assert phase_names == ["begin", "final_meta", "commit"]
    assert len(transaction_ids) == 1
    assert batching_repository.begin_calls == begin_calls + 1
    assert batching_repository.commit_calls == commit_calls + 1
    assert batching_repository.rollback_calls == rollback_calls
    assert processed_meta["reprocess_required"] is False
    assert blob_repository.read_file_bytes(source_handle, f"{document_id}.pdf") == source_pdf_before
    assert blob_repository.read_file_bytes(source_handle, f"{document_id}_docling.json") == source_docling_before


def test_hk_bare_rebuild_includes_local_optional_quarter_without_provider_io(
    tmp_path: Path,
) -> None:
    """HK bare rebuild 应按六期 discovery 找到本地 Q2，effective 仍为 FY/H1。

    Args:
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: Q2 被 discovery 漏掉、访问 provider 或覆盖 source 时抛出。
    """

    cn_discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    hk_candidate = _candidate(
        source_id="HK-Q2-LOCAL",
        fiscal_period="Q2",
        provider="hkexnews",
    )
    hk_discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(hk_candidate,))
    converter = _FakeConverter()
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=cn_discovery,
        hk_discovery=hk_discovery,
        converter=converter,
    )
    asyncio.run(
        _collect_events_async(
            pipeline=pipeline,
            ticker="0700",
            form_type="Q2",
            start_date="2024",
            end_date="2026",
            overwrite=False,
            start_is_explicit=True,
        )
    )
    document_id, _ = build_cn_filing_ids(
        ticker="0700",
        form_type="Q2",
        fiscal_year=2024,
        fiscal_period="Q2",
        amended=False,
    )
    source_handle = pipeline.source_repository.get_source_handle(
        "0700",
        document_id,
        SourceKind.FILING,
    )
    source_pdf_before = pipeline.blob_repository.read_file_bytes(
        source_handle,
        f"{document_id}.pdf",
    )
    source_docling_before = pipeline.blob_repository.read_file_bytes(
        source_handle,
        f"{document_id}_docling.json",
    )
    hk_discovery.queries.clear()
    hk_discovery.download_calls = 0
    converter.calls = 0

    result = pipeline.download(
        ticker="0700",
        form_type=None,
        start_date="2024",
        end_date="2026",
        overwrite=False,
        rebuild=True,
        start_is_explicit=True,
    )

    filters = result["filters"]
    filings = result["filings"]
    assert isinstance(filters, dict)
    assert isinstance(filings, list)
    assert filters["forms"] == ["FY", "H1"]
    assert result["missing_periods"] == []
    assert [item["form_type"] for item in filings if isinstance(item, dict)] == ["Q2"]
    assert hk_discovery.queries == []
    assert hk_discovery.download_calls == 0
    assert converter.calls == 0
    assert pipeline.blob_repository.read_file_bytes(source_handle, f"{document_id}.pdf") == source_pdf_before
    assert (
        pipeline.blob_repository.read_file_bytes(
            source_handle,
            f"{document_id}_docling.json",
        )
        == source_docling_before
    )


def test_cn_rebuild_producer_always_emits_required_missing_periods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """零文档、匹配、失败文档与取消结果都由 producer 直接发必填字段。"""

    empty_pipeline = _build_pipeline(
        tmp_path=tmp_path / "empty",
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        converter=_FakeConverter(),
    )
    empty_result = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=empty_pipeline,
        ticker="600519",
        market="CN",
        form_type="FY",
        start_date="2024",
        end_date="2026",
        overwrite=False,
        pipeline_name="cn",
    )
    assert empty_result["missing_periods"] == []

    pipeline = _build_pipeline(
        tmp_path=tmp_path / "seeded",
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),)),
        converter=_FakeConverter(),
    )
    _collect_events(pipeline, start_is_explicit=True)
    matching_result = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=pipeline,
        ticker="600519",
        market="CN",
        form_type="FY",
        start_date="2024",
        end_date="2026",
        overwrite=False,
        pipeline_name="cn",
    )
    assert matching_result["missing_periods"] == []

    original_get_meta = pipeline.source_repository.get_source_meta

    def missing_form_meta(
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> dict[str, JsonValue]:
        """返回删除必填 form_type 的 source meta。"""

        meta = dict(original_get_meta(ticker, document_id, source_kind))
        meta.pop("form_type", None)
        return meta

    monkeypatch.setattr(pipeline.source_repository, "get_source_meta", missing_form_meta)
    failed_result = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=pipeline,
        ticker="600519",
        market="CN",
        form_type="FY",
        start_date="2024",
        end_date="2026",
        overwrite=False,
        pipeline_name="cn",
    )
    assert failed_result["missing_periods"] == []
    failed_filings = failed_result["filings"]
    assert isinstance(failed_filings, list)
    assert isinstance(failed_filings[0], dict)
    assert failed_filings[0]["status"] == "failed"

    monkeypatch.setattr(pipeline.source_repository, "get_source_meta", original_get_meta)
    cancelled_result = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=pipeline,
        ticker="600519",
        market="CN",
        form_type="FY",
        start_date="2024",
        end_date="2026",
        overwrite=False,
        pipeline_name="cn",
        cancel_checker=lambda: True,
    )
    assert cancelled_result["status"] == "cancelled"
    assert cancelled_result["missing_periods"] == []


@pytest.mark.parametrize(
    ("market", "ticker", "expected_forms", "expected_discovery"),
    [
        ("CN", "600519", ["FY", "H1", "Q1", "Q3"], {"FY", "H1", "Q1", "Q3"}),
        (
            "HK",
            "0700",
            ["FY", "H1"],
            {"FY", "H1", "Q1", "Q2", "Q3", "Q4"},
        ),
    ],
)
def test_cn_hk_bare_rebuild_is_local_only_and_always_has_empty_missing(
    tmp_path: Path,
    market: CnMarketKind,
    ticker: str,
    expected_forms: list[str],
    expected_discovery: set[str],
) -> None:
    """CN/HK bare rebuild 应消费 policy、保持 local-only 且不生成 missing。

    Args:
        tmp_path: 临时工作区。
        market: 待验证市场。
        ticker: 市场对应 canonical ticker。
        expected_forms: effective forms 投影。
        expected_discovery: 本地 source scan 的 discovery 财期。

    Returns:
        无。

    Raises:
        AssertionError: rebuild 访问 provider、触发转换或生成 missing 时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    converter = _FakeConverter()
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        hk_discovery=discovery,
        converter=converter,
    )

    result = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=pipeline,
        ticker=ticker,
        market=market,
        form_type=None,
        start_date="2024",
        end_date="2026",
        overwrite=False,
        pipeline_name="cn" if market == "CN" else "hk",
    )

    filters = result["filters"]
    assert isinstance(filters, dict)
    start_dates = filters["start_dates"]
    assert isinstance(start_dates, dict)
    assert filters["forms"] == expected_forms
    assert set(start_dates) == expected_discovery
    assert result["missing_periods"] == []
    assert discovery.queries == []
    assert discovery.download_calls == 0
    assert converter.calls == 0


def test_cn_active_batch_sync_cancelled_error_rolls_back_once(tmp_path: Path) -> None:
    """同步抛出的 asyncio.CancelledError 必须触发一次 operation rollback。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
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
            batching_repository=batching_repository,
            source_repository=source_repository,
            blob_repository=blob_repository,
            processed_repository=processed_repository,
            ticker="600519",
            document_id="fil_cancelled",
            internal_document_id="fil_cancelled",
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
            phase_a_integrity=source_repository.classify_source_integrity(
                "600519",
                "fil_cancelled",
                SourceKind.FILING,
            ),
            overwrite=False,
            cancel_checker=cancel_during_batch,
            module="TEST",
        )

    assert exc_info.value is expected
    assert batching_repository.rollback_calls == 1
    assert batching_repository.commit_calls == 0
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("600519", "fil_cancelled", SourceKind.FILING)


def test_cn_commit_failure_does_not_trigger_caller_rollback_or_success(tmp_path: Path) -> None:
    """CN commit 失败后不得二次 rollback，也不得投影 filing success。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    batching_repository.fail_commit_call = 2
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
    )

    events = _collect_events(pipeline, start_is_explicit=True)
    result = _final_result(events)
    summary = result["summary"]

    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    assert batching_repository.commit_calls == 2
    assert batching_repository.rollback_calls == 0
    assert DownloadEventType.FILING_COMPLETED not in {event.event_type for event in events}
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("600519", "fil2024", SourceKind.FILING)


@pytest.mark.parametrize("corruption", ["size", "digest", "missing"])
def test_cn_top_level_repairs_selected_corruption_with_overwrite_false(
    tmp_path: Path,
    corruption: str,
) -> None:
    """真实 CN top-level 必须在 company mutation 前修复唯一 selected source。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=converter,
    )
    _collect_events(pipeline, start_is_explicit=True)
    candidate = _candidate()
    document_id, _internal_document_id = build_cn_filing_ids(
        ticker="600519",
        form_type=candidate.period_projection.identity_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.period_projection.identity_period,
        amended=candidate.amended,
    )
    locator = pipeline.source_repository.get_source_document_locator(
        "600519",
        document_id,
        SourceKind.FILING,
    )
    pdf_path = tmp_path / locator / f"{document_id}.pdf"
    old_pdf = pdf_path.read_bytes()
    if corruption == "size":
        pdf_path.write_bytes(old_pdf + b"-corrupt")
    elif corruption == "digest":
        pdf_path.write_bytes(b"X" * len(old_pdf))
    else:
        pdf_path.unlink()

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert converter.calls == 1
    with pipeline.source_repository.read_source_snapshot(
        "600519",
        document_id,
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        with snapshot.get_primary_source().open() as stream:
            assert stream.read() == _DOCLING_BYTES


def test_cn_selected_repair_transport_failure_preserves_old_company_and_source(
    tmp_path: Path,
) -> None:
    """selected repair 的 PDF 失败由 filing owner 收口，且 company/source 全保持 old。"""

    initial_discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    initial_pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=initial_discovery,
        converter=_FakeConverter(),
    )
    _collect_events(initial_pipeline, start_is_explicit=True)
    old_company = initial_pipeline._company_repository.get_company_meta("600519")
    candidate = _candidate()
    document_id, _internal_document_id = build_cn_filing_ids(
        ticker="600519",
        form_type=candidate.period_projection.identity_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.period_projection.identity_period,
        amended=candidate.amended,
    )
    locator = initial_pipeline.source_repository.get_source_document_locator(
        "600519",
        document_id,
        SourceKind.FILING,
    )
    source_dir = tmp_path / locator
    meta_path = source_dir / "meta.json"
    old_meta = meta_path.read_bytes()
    pdf_path = source_dir / f"{document_id}.pdf"
    pdf_path.unlink()
    failing_pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FailingDownloadDiscoveryClient(
            temp_dir=tmp_path,
            candidates=(candidate,),
        ),
        converter=_FakeConverter(),
    )

    result = _final_result(_collect_events(failing_pipeline, start_is_explicit=True))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["failed"] == 1
    assert failing_pipeline._company_repository.get_company_meta("600519") == old_company
    assert meta_path.read_bytes() == old_meta
    assert pdf_path.exists() is False


def test_cn_no_filing_with_corruption_fails_before_company_batch(tmp_path: Path) -> None:
    """no-filing 若仍有 corruption，必须在首个新 batch 前 typed fail closed。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
    )
    _collect_events(pipeline, start_is_explicit=True)
    old_company = pipeline._company_repository.get_company_meta("600519")
    candidate = _candidate()
    document_id, _internal_document_id = build_cn_filing_ids(
        ticker="600519",
        form_type=candidate.period_projection.identity_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.period_projection.identity_period,
        amended=candidate.amended,
    )
    locator = pipeline.source_repository.get_source_document_locator(
        "600519",
        document_id,
        SourceKind.FILING,
    )
    (tmp_path / locator / f"{document_id}.pdf").unlink()
    begin_calls = batching_repository.begin_calls
    discovery.candidates = ()

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        _collect_events(pipeline, start_is_explicit=True)

    assert exc_info.value.reason is SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED
    assert batching_repository.begin_calls == begin_calls
    assert pipeline._company_repository.get_company_meta("600519") == old_company


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

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))

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

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))
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
    filings = result["filings"]
    assert isinstance(filings, list)
    first_filing = filings[0]
    assert isinstance(first_filing, dict)
    assert first_filing["reason_code"] == "filing_execution_failed"
    assert first_filing["reason_message"] == "财报文档执行失败"
    assert "forced PDF" not in str(first_filing)
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )


@pytest.mark.parametrize(
    ("failure", "expected_reason_code", "expected_safe_message"),
    [
        (
            FinsDownloadProviderError(
                source=FinsDownloadSource.CNINFO,
                transport_category=FinsDownloadTransportCategory.TIMEOUT,
                retryable=True,
                safe_message="巨潮来源请求超时",
            ),
            "provider_timeout",
            "巨潮来源请求超时",
        ),
        (
            OSError("/Users/private/contact-canary/report.pdf"),
            "storage_failed",
            "下载产物读写失败",
        ),
        (
            RuntimeError("raw https://secret.invalid/payload"),
            "filing_execution_failed",
            "财报文档执行失败",
        ),
    ],
)
def test_cn_candidate_failure_uses_closed_safe_facts_and_continues(
    tmp_path: Path,
    failure: Exception,
    expected_reason_code: str,
    expected_safe_message: str,
) -> None:
    """单文档失败只投影安全事实，并允许后续 candidate 完成。"""

    discovery = _FirstCandidateFailureDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(source_id="A1"), _candidate(source_id="A2")),
        failure=failure,
    )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))
    filings = result["filings"]
    assert isinstance(filings, list)
    filing_rows = [filing for filing in filings if isinstance(filing, dict)]
    assert len(filing_rows) == len(filings)
    assert [filing["status"] for filing in filing_rows] == ["failed", "downloaded"]
    assert filing_rows[0]["reason_code"] == expected_reason_code
    assert filing_rows[0]["reason_message"] == expected_safe_message
    serialized = str(filing_rows[0])
    assert "secret.invalid" not in serialized
    assert "/Users/private" not in serialized
    assert "contact-canary" not in serialized


@pytest.mark.parametrize("stage", ["pdf", "docling"])
@pytest.mark.parametrize(
    ("failure", "expected_reason_code", "expected_safe_message"),
    [
        (
            FinsDownloadProviderError(
                source=FinsDownloadSource.CNINFO,
                transport_category=FinsDownloadTransportCategory.TIMEOUT,
                retryable=True,
                safe_message="巨潮来源请求超时",
            ),
            "provider_timeout",
            "巨潮来源请求超时",
        ),
        (
            OSError("/Users/private/contact-canary/report.pdf"),
            "storage_failed",
            "下载产物读写失败",
        ),
        (
            RuntimeError("raw https://secret.invalid/payload payload-marker contact@example.invalid"),
            "filing_execution_failed",
            "财报文档执行失败",
        ),
    ],
)
def test_cn_single_filing_owner_projects_closed_failure_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    failure: Exception,
    expected_reason_code: str,
    expected_safe_message: str,
) -> None:
    """PDF/Docling owner 应直接投影一次并只公开同一安全原因 pair。"""

    candidate = _candidate(source_id="A1")
    if stage == "pdf":
        discovery: _FakeDiscoveryClient = _FirstCandidateFailureDiscoveryClient(
            temp_dir=tmp_path,
            candidates=(candidate,),
            failure=failure,
        )
        converter: DoclingConverter = _FakeConverter()
    elif stage == "docling":
        discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(candidate,))
        converter = _FailingConverter(failure=failure)
    else:
        raise AssertionError(f"未知测试阶段: {stage}")

    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=converter,
    )
    projection_spy = _FilingFailureProjectionSpy(delegate=_cn_download_filing_workflow.project_cn_filing_failure)
    logs: list[str] = []
    monkeypatch.setattr(
        _cn_download_filing_workflow,
        "project_cn_filing_failure",
        projection_spy,
    )
    monkeypatch.setattr(
        _cn_download_filing_workflow.Log,
        "info",
        lambda message, *, module: logs.append(f"{module}:{message}"),
    )

    events = _collect_single_filing_events(
        pipeline=pipeline,
        candidate=candidate,
    )

    assert len(projection_spy.calls) == 1
    assert projection_spy.calls[0] is failure
    filing_terminals = [
        event
        for event in events
        if event.event_type in {DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED}
    ]
    assert [event.event_type for event in filing_terminals] == [DownloadEventType.FILING_FAILED]
    filing_failed = filing_terminals[0]
    expected_pair = (expected_reason_code, expected_safe_message)
    assert (
        filing_failed.payload["reason_code"],
        filing_failed.payload["reason_message"],
    ) == expected_pair

    file_failures = [event for event in events if event.event_type is DownloadEventType.FILE_FAILED]
    if stage == "pdf":
        assert len(file_failures) == 1
        assert (
            file_failures[0].payload["reason_code"],
            file_failures[0].payload["reason_message"],
        ) == expected_pair
    else:
        assert file_failures == []

    serialized = f"{[event.payload for event in events]} {' '.join(logs)}"
    for forbidden in (
        "secret.invalid",
        "/Users/private",
        "contact-canary",
        "contact@example.invalid",
        "payload-marker",
        "Traceback",
    ):
        assert forbidden not in serialized


def test_cn_single_filing_owner_preserves_cancel_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF owner 应让 typed cancellation 原样逸出且不调用 failure helper。"""

    expected = CnDownloadCancelledError("caller cancelled during PDF")
    candidate = _candidate(source_id="A1")
    discovery = _FirstCandidateFailureDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(candidate,),
        failure=expected,
    )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )
    projection_spy = _FilingFailureProjectionSpy(delegate=_cn_download_filing_workflow.project_cn_filing_failure)
    monkeypatch.setattr(
        _cn_download_filing_workflow,
        "project_cn_filing_failure",
        projection_spy,
    )

    with pytest.raises(CnDownloadCancelledError) as exc_info:
        _collect_single_filing_events(
            pipeline=pipeline,
            candidate=candidate,
        )

    assert exc_info.value is expected
    assert projection_spy.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        FinsDownloadProviderError(
            source=FinsDownloadSource.CNINFO,
            transport_category=FinsDownloadTransportCategory.CONNECTION,
            retryable=True,
            safe_message="巨潮来源连接失败",
        ),
        OSError("/Users/private/contact-canary/leaked-owner.pdf"),
        RuntimeError("raw https://secret.invalid/parent payload-marker contact@example.invalid"),
    ],
)
def test_cn_parent_leak_catch_reuses_filing_owner_pair_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    """父 workflow 防御 catch 应直接复用 child owner pair 并继续后续文档。"""

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(source_id="A1"), _candidate(source_id="A2")),
    )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )
    original_get_source_meta = pipeline.source_repository.get_source_meta
    source_meta_calls = 0

    def fail_first_source_meta(
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """第一次读取抛出预构造异常，之后调用真实仓储。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: source 类型。

        Returns:
            后续调用的真实 published meta。

        Raises:
            Exception: 第一次调用原样抛出 ``failure``。
            FileNotFoundError: 后续真实仓储没有文档时抛出。
        """

        nonlocal source_meta_calls
        source_meta_calls += 1
        if source_meta_calls == 1:
            raise failure
        return original_get_source_meta(ticker, document_id, source_kind)

    monkeypatch.setattr(
        pipeline.source_repository,
        "get_source_meta",
        fail_first_source_meta,
    )
    projection_spy = _FilingFailureProjectionSpy(delegate=_cn_download_filing_workflow.project_cn_filing_failure)
    monkeypatch.setattr(
        _cn_download_workflow,
        "project_cn_filing_failure",
        projection_spy,
    )

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))

    filings = result["filings"]
    assert isinstance(filings, list)
    filing_rows = [filing for filing in filings if isinstance(filing, dict)]
    assert len(filing_rows) == len(filings)
    # MISSING target 不再执行冗余 published meta probe；首个真实 meta read 发生在
    # 第一份 filing 的 staging/fiscal owner 后，故 injected failure 对应第二行。
    assert [filing["status"] for filing in filing_rows] == ["downloaded", "failed"]
    assert len(projection_spy.calls) == 1
    assert projection_spy.calls[0] is failure
    assert (
        filing_rows[1]["reason_code"],
        filing_rows[1]["reason_message"],
    ) == _cn_download_filing_workflow.project_cn_filing_failure(failure)
    serialized = str(filing_rows[1])
    for forbidden in (
        "secret.invalid",
        "/Users/private",
        "contact-canary",
        "contact@example.invalid",
        "payload-marker",
        "Traceback",
    ):
        assert forbidden not in serialized


def test_cn_docling_conversion_failure_leaves_document_absent(tmp_path: Path) -> None:
    """Docling conversion exception 发生在 batch 外，不得创建 source 或 blob。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FailingConverter(
            failure=RuntimeError("forced Docling conversion failure"),
        ),
    )

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))
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


def test_cn_docling_converter_cancel_maps_to_download_cancelled(tmp_path: Path) -> None:
    """shared converter cancel 必须在 workflow 边界映射为 CN/HK cancelled。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: cancel 被投影为 failed 或产生半发布时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FailingConverter(failure=DoclingConversionCancelledError()),
    )

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))

    assert result["status"] == "cancelled"
    assert result["filings"] == []
    assert pipeline.source_repository.list_source_document_ids("600519", SourceKind.FILING) == []


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
            start_is_explicit=True,
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
    assert DownloadEventType.CONVERSION_STARTED not in {event.event_type for event in events}


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
                start_is_explicit=True,
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
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
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
                batching_repository=batching_repository,
                source_repository=source_repository,
                blob_repository=blob_repository,
                processed_repository=processed_repository,
                discovery_client=discovery,
                pdf_download_gate=_RecordingPdfGate(),
                docling_conversion_runner=_FakeConverter(),
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

    events = _collect_events(pipeline, start_is_explicit=True, cancel_checker=cancel_state)
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
    assert DownloadEventType.FILING_COMPLETED not in {event.event_type for event in events}


def test_cn_download_cancel_after_conversion_completed_skips_publication(
    tmp_path: Path,
) -> None:
    """CONVERSION_COMPLETED 后取消仍须在 publication eligibility 前收口。

    Args:
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: completed 后缺少取消 checkpoint 或出现半发布时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    cancel_state = _CancelState()
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
    )

    async def collect_with_completed_cancel() -> list[DownloadEvent]:
        """观察 completed 事件后在确定性 yield boundary 请求取消。

        Returns:
            完整 pipeline 事件列表。

        Raises:
            无。
        """

        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="FY",
            start_date="2024",
            end_date="2026",
            overwrite=False,
            start_is_explicit=True,
            cancel_checker=cancel_state,
        ):
            events.append(event)
            if event.event_type is DownloadEventType.CONVERSION_COMPLETED:
                cancel_state.cancelled = True
        return events

    events = asyncio.run(collect_with_completed_cancel())
    result = _final_result(events)
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )

    assert result["status"] == "cancelled"
    assert [event.event_type for event in events].count(DownloadEventType.CONVERSION_COMPLETED) == 1
    assert DownloadEventType.FILING_COMPLETED not in {event.event_type for event in events}
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_meta(
            "600519",
            document_id,
            SourceKind.FILING,
        )


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


def test_cn_workflow_maps_bool_true_inside_single_owned_checkpoint(
    tmp_path: Path,
) -> None:
    """raw checker 在 discovery-pre 为 false、checkpoint 内为 true 时应映射为 typed cancel。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    raw_calls = 0

    def cancel_checker() -> bool:
        nonlocal raw_calls
        raw_calls += 1
        return raw_calls == 4

    events = _collect_events(pipeline, start_is_explicit=True, cancel_checker=cancel_checker)
    result = _final_result(events)

    assert result["status"] == "cancelled"
    assert raw_calls == 4
    assert len(discovery.cancellation_checkpoints) == 1
    checkpoint = discovery.cancellation_checkpoints[0]
    assert checkpoint is not None
    assert checkpoint is not cancel_checker
    assert len(discovery.checkpoint_errors) == 1
    assert isinstance(discovery.checkpoint_errors[0], CnDownloadCancelledError)
    assert discovery.download_calls == 0
    assert converter.calls == 0
    assert all(
        event.event_type
        not in {
            DownloadEventType.FILING_STARTED,
            DownloadEventType.FILE_DOWNLOAD_STARTED,
        }
        for event in events
    )


def test_cn_workflow_preserves_caller_cancel_object_through_checkpoint(
    tmp_path: Path,
) -> None:
    """raw checker 主动抛出的 typed cancel 应穿过 partial/protocol 保持 identity。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    expected = CnDownloadCancelledError("caller cancelled inside checkpoint")
    raw_calls = 0

    def cancel_checker() -> bool:
        nonlocal raw_calls
        raw_calls += 1
        if raw_calls == 4:
            raise expected
        return False

    result = _final_result(_collect_events(pipeline, start_is_explicit=True, cancel_checker=cancel_checker))

    assert result["status"] == "cancelled"
    assert discovery.checkpoint_errors == [expected]
    assert discovery.checkpoint_errors[0] is expected
    assert discovery.download_calls == 0
    assert converter.calls == 0


def test_cn_workflow_cancel_before_first_candidate_suppresses_download(
    tmp_path: Path,
) -> None:
    """discovery 完成后、首个 candidate 前取消应停止 PDF/转换发布。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    raw_calls = 0

    def cancel_checker() -> bool:
        nonlocal raw_calls
        raw_calls += 1
        return raw_calls == 6

    events = _collect_events(pipeline, start_is_explicit=True, cancel_checker=cancel_checker)
    result = _final_result(events)

    assert result["status"] == "cancelled"
    assert raw_calls == 6
    assert discovery.download_calls == 0
    assert converter.calls == 0
    assert DownloadEventType.FILING_STARTED not in {event.event_type for event in events}


def test_cn_workflow_preserves_checkpoint_non_cancel_failure_identity(
    tmp_path: Path,
) -> None:
    """raw checker 非取消失败应原样越过 workflow/stream/collector。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    expected = ValueError("raw checker failure")
    raw_calls = 0

    def cancel_checker() -> bool:
        nonlocal raw_calls
        raw_calls += 1
        if raw_calls == 4:
            raise expected
        return False

    with pytest.raises(ValueError) as exc_info:
        _collect_events(pipeline, start_is_explicit=True, cancel_checker=cancel_checker)

    assert exc_info.value is expected
    assert discovery.checkpoint_errors == []
    assert discovery.download_calls == 0
    assert converter.calls == 0


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

    _collect_events(pipeline, start_is_explicit=True)
    second_events = _collect_events(pipeline, start_is_explicit=True)

    result = _final_result(second_events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["skipped"] == 1
    assert discovery.download_calls == 1
    assert converter.calls == 1


def test_cn_download_reports_missing_independent_quarter_outside_document_counts(tmp_path: Path) -> None:
    """主源缺少独立季度时应单独报告，不伪装成 skipped 文档。

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

    events = _collect_events(pipeline, start_is_explicit=True, form_type="Q2")

    result = _final_result(events)
    summary = result["summary"]
    filings = result["filings"]
    assert isinstance(summary, dict)
    assert isinstance(filings, list)
    assert summary["total"] == 0
    assert summary["downloaded"] == 0
    assert summary["skipped"] == 0
    assert summary["failed"] == 0
    assert result["missing_periods"] == ["Q2"]
    assert filings == []
    assert discovery.download_calls == 0
    assert converter.calls == 0
    assert DownloadEventType.FILING_COMPLETED not in {event.event_type for event in events}
