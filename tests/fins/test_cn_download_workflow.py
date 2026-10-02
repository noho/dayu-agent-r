"""CN/HK download workflow 单元测试。"""

from __future__ import annotations

from dayu.fins.storage import FsBatchingRepository, FsCompanyMetaRepository, FsSourceDocumentRepository, FsDocumentBlobRepository, FsFilingMaintenanceRepository, FsFilingUploadStateRepository, FsProcessedDocumentRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

from dayu.fins.storage import FsMaterialUploadStateRepository

import asyncio
import hashlib
import io
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Literal, Optional, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    CompanyMetaCommitOutcome,
)
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
from dayu.fins.pipelines.cn_download_identity import build_cn_download_identity_index, resolve_cn_download_ids
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
    CnReportDiscoveryResult,
    CnReportPeriodProjection,
    CnReportQuery,
    CnSourceProvider,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol
from dayu.fins.pipelines.cn_download_source_upsert import (
    build_content_fingerprint, build_remote_fingerprint, build_cn_file_entry, commit_cn_filing_source_document,
)
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
    CompanyTickerIdentityCorruptionError,
    FsSourceDocumentRepository,
    SourceIntegrityClassification,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
    SourceIntegrityRevisionConflictError,
    SourceIntegrityRepairRequiredError,
    SourceIntegrityReason,
    SourceIntegrityStatus,
    SourceMetaReadView,
    SourceMetaIntegrityReadEntry,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage._fs_identity import _FILING_IDENTITY_NAMESPACE, _identity_directory_path
from tests.fins.test_fins_storage_atomicity import _create_complete_source, _identity_descriptor_file

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

    def commit_batch(self, batch: BatchToken) -> CompanyMetaCommitOutcome | None:
        """记录 caller 唯一 commit，并模拟 storage owner 消费 token 的失败。

        Args:
            batch: caller 转交的 batch capability。

        Returns:
            download batch 的真实 typed company-meta outcome；无 intent 时返回 ``None``。

        Raises:
            OSError: 启用 commit failure injection 或真实提交失败时抛出。
            ValueError: capability 非法时抛出。
        """

        self.record_phase("commit", batch)
        self.commit_calls += 1
        if self.fail_commit_call == self.commit_calls:
            FsBatchingRepository.rollback_batch(self, batch)
            self.active_token = None
            raise OSError("forced CN storage commit failure")
        outcome = super().commit_batch(batch)
        self.active_token = None
        return outcome

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
        local_annual_ends: tuple[date, ...],
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> CnReportDiscoveryResult:
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
        return CnReportDiscoveryResult(candidates=self.candidates, uncertain_reports=())

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
     material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path, repository_set=repository_set), filing_upload_state_repository=FsFilingUploadStateRepository(tmp_path, repository_set=repository_set),)


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
    assert result["status"] == "ok"
    assert type(result["status"]) is str


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
    """完整正文缓存面对合成全文候选时保留旧来源和文件，且不打开 source batch。

    Args:
        tmp_path: pytest 隔离工作区。

    Returns:
        无。

    Raises:
        AssertionError: 默认跳过发生传输、来源变更或文档事务时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    blob_repository = _BatchIdentityCnBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    old_candidate = replace(_candidate(), title="合成测试：2024年年度报告正文")
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(old_candidate,))
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
    document_id, = source_repository.list_source_document_ids("600519", SourceKind.FILING)
    old_meta = source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    handle = source_repository.get_source_handle("600519", document_id, SourceKind.FILING)
    old_pdf = blob_repository.read_file_bytes(handle, f"{document_id}.pdf")
    assert old_meta["source_id"] == old_candidate.source_id
    assert old_meta["source_title"] == old_candidate.title
    assert old_meta["source_url"] == old_candidate.source_url
    assert old_pdf == _PDF_BYTES
    batching_repository.phases.clear()
    begin_calls = batching_repository.begin_calls
    commit_calls = batching_repository.commit_calls
    rollback_calls = batching_repository.rollback_calls
    download_calls = discovery.download_calls
    discovery.candidates = (
        replace(_candidate(source_id="A2", etag='"v2"'), title="合成测试：2024年年度报告全文"),
    )
    discovery.pdf_bytes = _PDF_BYTES + b"synthetic-full-report"

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
    assert source_repository.get_source_meta("600519", document_id, SourceKind.FILING) == old_meta
    assert blob_repository.read_file_bytes(handle, f"{document_id}.pdf") == old_pdf


def test_cn_unsafe_phase_a_fails_before_meta_transport_or_reset(tmp_path: Path) -> None:
    """Phase A UNSAFE 必须消费 typed classification，且不读取/复用旧 source。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: UNSAFE 后仍发生 meta 相关传输或 mutation 时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
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
    locator = source_repository.get_source_document_locator("600519", document_id, SourceKind.FILING)
    unsafe_file = tmp_path / locator / "undeclared.bin"
    unsafe_file.write_bytes(b"unsafe")
    begin_calls = batching_repository.begin_calls
    reset_phases = [phase for phase, _batch_id in batching_repository.phases if phase == "reset"]
    download_calls = discovery.download_calls

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        _collect_single_filing_events(
            pipeline=pipeline,
            candidate=candidate,
            cancel_checker=None,
        )

    assert exc_info.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert batching_repository.begin_calls == begin_calls
    assert [phase for phase, _batch_id in batching_repository.phases if phase == "reset"] == reset_phases
    assert discovery.download_calls == download_calls
    assert unsafe_file.read_bytes() == b"unsafe"


def test_cn_unsafe_phase_b_rolls_back_without_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase B UNSAFE 必须在 identity 比较与 reset 前 typed fail closed。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: staged UNSAFE 进入 identity 比较、reset 或 commit 时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    source_repository = _BatchIdentityCnSourceRepository(tmp_path, repository_set, batching_repository)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
        source_repository=source_repository,
    )

    def classify_staged_unsafe(
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> SourceIntegrityClassification:
        """返回 storage owner 已确定的 staged UNSAFE fact。

        Args:
            ticker: exact ticker。
            document_id: exact document ID。
            source_kind: exact source kind。
            batch: 已打开的 batch capability。

        Returns:
            staged target 的 typed UNSAFE classification。

        Raises:
            无。
        """

        del batch
        return SourceIntegrityClassification(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            revision=None,
            status=SourceIntegrityStatus.UNSAFE,
            reasons=(SourceIntegrityReason.META_UNTRUSTED,),
        )

    monkeypatch.setattr(
        source_repository,
        "classify_staged_source_integrity",
        classify_staged_unsafe,
    )

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        _collect_single_filing_events(
            pipeline=pipeline,
            candidate=_candidate(),
            cancel_checker=None,
        )

    assert exc_info.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert [phase for phase, _batch_id in batching_repository.phases] == ["begin", "rollback"]
    assert batching_repository.commit_calls == 0
    assert batching_repository.rollback_calls == 1
    assert "reset" not in [phase for phase, _batch_id in batching_repository.phases]
    assert source_repository.list_source_document_ids("600519", SourceKind.FILING) == []


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
    """合成正文覆盖为全文后来源、文件及清单同步，随后增量保持完成态。

    Args:
        tmp_path: pytest 隔离工作区。

    Returns:
        无。

    Raises:
        AssertionError: 覆盖投影、重处理标记或再次增量跳过不符合合同。
    """

    old_candidate = replace(_candidate(), title="合成测试：2024年年度报告正文")
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(old_candidate,))
    converter = _FakeConverter()
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=converter,
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
    old_meta = pipeline.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    replacement_pdf = _PDF_BYTES + b"replacement"
    discovery.pdf_bytes = replacement_pdf
    new_candidate = replace(
        _candidate(source_id="A2", etag='"v2"'),
        title="合成测试：2024年年度报告全文",
        content_length=len(replacement_pdf),
    )
    discovery.candidates = (new_candidate,)

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
    assert source_meta["source_id"] == new_candidate.source_id
    assert source_meta["source_title"] == new_candidate.title
    assert source_meta["source_url"] == new_candidate.source_url
    assert source_meta["pdf_sha256"] == hashlib.sha256(replacement_pdf).hexdigest()
    assert source_meta["source_fingerprint"] == build_content_fingerprint(
        pdf_bytes=replacement_pdf, docling_json_bytes=_DOCLING_BYTES,
    )
    assert source_meta["remote_fingerprint"] == build_remote_fingerprint(new_candidate)
    assert source_meta["source_fingerprint"] != old_meta["source_fingerprint"]
    assert source_meta["remote_fingerprint"] != old_meta["remote_fingerprint"]
    assert pipeline.blob_repository.read_file_bytes(handle, f"{document_id}.pdf") == replacement_pdf
    assert pipeline.blob_repository.read_file_bytes(handle, f"{document_id}_docling.json") == _DOCLING_BYTES
    assert processed_meta["reprocess_required"] is True
    files = pipeline.blob_repository.list_files(handle)
    expected_files = {
        f"{document_id}.pdf": replacement_pdf,
        f"{document_id}_docling.json": _DOCLING_BYTES,
    }
    assert len(files) == len(expected_files)
    assert {Path(file.uri).name for file in files} == set(expected_files)
    for file in files:
        expected_bytes = expected_files[Path(file.uri).name]
        assert file.size == len(expected_bytes)
        assert file.sha256 == hashlib.sha256(expected_bytes).hexdigest()
    # 仓储完整性 owner 比较落盘 manifest 与当前 meta 的完整规范投影，
    # 同时拒绝缺项、多余项和投影漂移；不在测试中另造 manifest 字段规则。
    integrity, = pipeline.source_repository.list_source_integrity("600519")
    assert integrity.document_id == document_id
    assert integrity.status is SourceIntegrityStatus.COMPLETE
    assert integrity.reasons == ()

    download_calls = discovery.download_calls
    conversion_calls = converter.calls
    incremental_result = _final_result(_collect_events(pipeline, start_is_explicit=True))
    summary = incremental_result["summary"]
    assert incremental_result["status"] == "ok"
    assert isinstance(summary, dict)
    assert summary["skipped"] == 1
    assert summary["downloaded"] == 0
    assert summary["failed"] == 0
    assert discovery.download_calls == download_calls
    assert converter.calls == conversion_calls
    assert pipeline.source_repository.get_source_meta("600519", document_id, SourceKind.FILING) == source_meta
    assert pipeline.blob_repository.list_files(handle) == files
    assert pipeline.blob_repository.read_file_bytes(handle, f"{document_id}.pdf") == replacement_pdf
    assert pipeline.source_repository.list_source_integrity("600519") == (integrity,)


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
    hk_candidate = replace(hk_candidate, title="2024年第二季度業績", category_text="季度業績")
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


@pytest.mark.parametrize("unmatched_filing", (False, True))
def test_cn_rebuild_empty_matches_reject_published_ticker_corruption(
    tmp_path: Path, unmatched_filing: bool,
) -> None:
    """真实发布公司根损坏时，CN rebuild 不得返回正常空命中。

    参数：tmp_path 为隔离真实仓储根；unmatched_filing 控制有无非 download 来源 filing。
    返回：无。
    异常：损坏被空枚举/空匹配掩盖、错误 kind 或来源原字节漂移时断言失败。
    """
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    converter = _FakeConverter()
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    pipeline = _build_pipeline(
        tmp_path=tmp_path, discovery=discovery, converter=converter,
        repository_set=repository_set, source_repository=source, blob_repository=blob,
    )
    batch = pipeline.batching_repository.begin_batch("600519")
    _create_complete_source(
        source, blob, batch=batch,
        ticker="600519", document_id="control",
        source_kind=SourceKind.FILING if unmatched_filing else SourceKind.MATERIAL,
    )
    pipeline.batching_repository.commit_batch(batch)
    normal = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=pipeline, ticker="600519", market="CN", form_type="FY",
        start_date="2024", end_date="2026", overwrite=False, pipeline_name="cn",
    )
    assert normal["status"] == "ok" and normal["filings"] == []
    ticker_dir = tmp_path / "portfolio" / "600519"
    descriptor = _identity_descriptor_file(ticker_dir)
    descriptor.write_text("{}", encoding="utf-8")
    original_source_bytes = {
        path.relative_to(ticker_dir): path.read_bytes()
        for path in ticker_dir.rglob("*") if path.is_file() and path != descriptor
    }
    with pytest.raises(CompanyTickerIdentityCorruptionError) as raised:
        _cn_download_rebuild.rebuild_cn_download_artifacts(
            host=pipeline, ticker="600519", market="CN", form_type="FY",
            start_date="2024", end_date="2026", overwrite=False, pipeline_name="cn",
        )
    assert raised.value.kind == "invalid_descriptor"
    assert {
        path.relative_to(ticker_dir): path.read_bytes()
        for path in ticker_dir.rglob("*") if path.is_file() and path != descriptor
    } == original_source_bytes
    assert discovery.queries == [] and discovery.download_calls == 0 and converter.calls == 0


def test_cn_rebuild_producer_always_emits_required_missing_periods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """零文档、匹配、失败文档与取消结果直接保全顶层终态及必填字段。

    Args:
        tmp_path: 隔离真实仓储根。
        monkeypatch: 仅在 source 读取边界构造缺失 form 的文档。

    Returns:
        无。

    Raises:
        AssertionError: 顶层终态、文档失败行或必填字段漂移时抛出。
    """

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
    assert empty_result["status"] == "ok"
    assert type(empty_result["status"]) is str

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
    assert matching_result["status"] == "ok"
    assert type(matching_result["status"]) is str

    original_get_meta = pipeline.source_repository.get_source_meta

    def missing_form_meta(
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> dict[str, JsonValue]:
        """在读取边界返回删除必填 form_type 的合成文档元数据。

        Args:
            ticker: 当前股票代码。
            document_id: 当前来源文档 ID。
            source_kind: 来源种类。

        Returns:
            仅缺失 form_type 的元数据副本。

        Raises:
            OSError: 原仓储读取异常原样传播。
        """

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
    assert failed_result["status"] == "ok"
    assert type(failed_result["status"]) is str
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
    assert type(cancelled_result["status"]) is str
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
    assert result["status"] == "ok"
    assert type(result["status"]) is str
    assert discovery.queries == []
    assert discovery.download_calls == 0
    assert converter.calls == 0

    # 先用合成下载链路建立真实本地文档；取消测试必须命中文档循环，避免改变空库语义。
    discovery.candidates = (_candidate(provider="cninfo" if market == "CN" else "hkexnews"),)
    asyncio.run(_collect_events_async(
        pipeline=pipeline, ticker=ticker, form_type="FY", start_date="2024", end_date="2026",
        overwrite=False, start_is_explicit=True,
    ))
    assert pipeline.source_repository.list_source_document_ids(ticker, SourceKind.FILING)
    prior_queries = tuple(discovery.queries)
    prior_download_calls = discovery.download_calls
    prior_converter_calls = converter.calls
    cancelled_result = _cn_download_rebuild.rebuild_cn_download_artifacts(
        host=pipeline, ticker=ticker, market=market, form_type=None,
        start_date="2024", end_date="2026", overwrite=False,
        pipeline_name="cn" if market == "CN" else "hk", cancel_checker=lambda: True,
    )
    assert cancelled_result["status"] == "cancelled"
    assert type(cancelled_result["status"]) is str
    assert cancelled_result["missing_periods"] == []
    assert tuple(discovery.queries) == prior_queries
    assert discovery.download_calls == prior_download_calls
    assert converter.calls == prior_converter_calls


@dataclass(frozen=True)
class _RebuildFailureProbe:
    """仅在仓储读取或取消检查边界提供预构造异常，不替换生产状态语义。"""

    failure: Exception

    def read_meta(self, ticker: str, document_id: str, source_kind: SourceKind) -> dict[str, JsonValue]:
        """模拟仓储读失败并保留原异常对象。

        Args:
            ticker: 仓储调用的股票代码。
            document_id: 来源文档 ID。
            source_kind: 来源种类。

        Returns:
            不返回；读取边界始终抛出指定异常。

        Raises:
            Exception: 预构造的原始仓储异常。
        """

        del ticker, document_id, source_kind
        raise self.failure

    def read_integrity(self, ticker: str, source_kind: SourceKind, *, batch: BatchToken | None) -> tuple[SourceMetaIntegrityReadEntry, ...]:
        """参数为同窗读取范围和 batch；返回不发生；抛出指定原始读取异常。"""
        del ticker, source_kind, batch
        raise self.failure

    def check_cancel(self) -> bool:
        """模拟非取消 checker 失败并保留原异常对象。

        Args:
            无。

        Returns:
            不返回；检查边界始终抛出指定异常。

        Raises:
            Exception: 预构造的非取消检查异常。
        """

        raise self.failure


@pytest.mark.parametrize("market", ("CN", "HK"))
@pytest.mark.parametrize("operation", ("read", "checker"))
def test_cn_hk_rebuild_preserves_read_and_checker_failure_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    market: CnMarketKind,
    operation: Literal["read", "checker"],
) -> None:
    """真实本地 rebuild 不把仓储或 checker 原异常转换成顶层结果。

    Args:
        tmp_path: 隔离真实仓储根。
        monkeypatch: 仅读取边界注入原异常。
        market: 待验证市场。
        operation: 原样失败的边界。

    Returns:
        无。

    Raises:
        AssertionError: 原异常 identity 或 local-only 行为漂移时抛出。
    """

    ticker = "600519" if market == "CN" else "0700"
    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(provider="cninfo" if market == "CN" else "hkexnews"),),
    )
    converter = _FakeConverter()
    pipeline = _build_pipeline(
        tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=converter,
    )
    asyncio.run(_collect_events_async(
        pipeline=pipeline, ticker=ticker, form_type="FY", start_date="2024", end_date="2026",
        overwrite=False, start_is_explicit=True,
    ))
    prior_calls = (tuple(discovery.queries), discovery.download_calls, converter.calls)
    expected = OSError("synthetic source read failure") if operation == "read" else ValueError(
        "synthetic rebuild checker failure"
    )
    probe = _RebuildFailureProbe(expected)
    if operation == "read":
        if market == "HK":
            monkeypatch.setattr(pipeline.source_repository, "read_source_meta_integrity_view", probe.read_integrity)
        else:
            monkeypatch.setattr(pipeline.source_repository, "get_source_meta", probe.read_meta)
    with pytest.raises(type(expected)) as exc_info:
        pipeline.download(
            ticker=ticker, form_type="FY", start_date="2024", end_date="2026",
            rebuild=True, start_is_explicit=True,
            cancel_checker=probe.check_cancel if operation == "checker" else None,
        )
    assert exc_info.value is expected
    assert (tuple(discovery.queries), discovery.download_calls, converter.calls) == prior_calls


@pytest.mark.parametrize(
    ("ticker", "form_type", "start_date", "end_date"),
    (
        ("invalid-ticker", "FY", "2024", "2026"),
        ("600519", "invalid-form", "2024", "2026"),
        ("600519", "FY", "2024-02-30", "2026"),
        ("600519", "FY", "2024", "2026-02-30"),
    ),
)
@pytest.mark.parametrize("rebuild", (False, True))
def test_cn_workflow_early_invalid_parameters_remain_exceptions(
    tmp_path: Path,
    ticker: str,
    form_type: str,
    start_date: str,
    end_date: str,
    rebuild: bool,
) -> None:
    """非法 ticker、form 或日期在业务执行前抛错，不生成新终态结果。

    Args:
        tmp_path: 隔离真实仓储根。
        ticker: 原始股票代码。
        form_type: 原始财期参数。
        start_date: 原始起始日期。
        end_date: 原始结束日期。
        rebuild: 是否走本地重建入口。

    Returns:
        无。

    Raises:
        AssertionError: 非法参数被转换为结果或执行了 provider/converter 时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    converter = _FakeConverter()
    pipeline = _build_pipeline(
        tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=converter,
    )
    with pytest.raises(ValueError):
        pipeline.download(
            ticker=ticker, form_type=form_type, start_date=start_date, end_date=end_date,
            rebuild=rebuild, start_is_explicit=True,
        )
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


@pytest.mark.parametrize("corruption", ["size", "digest", "missing", "manifest"])
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
    elif corruption == "missing":
        pdf_path.unlink()
    else:
        (tmp_path / locator.parent / "filing_manifest.json").unlink()

    result = _final_result(_collect_events(pipeline, start_is_explicit=True))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert converter.calls == 1
    assert pipeline.source_repository.classify_source_integrity(
        "600519",
        document_id,
        SourceKind.FILING,
    ).status is SourceIntegrityStatus.COMPLETE
    assert (tmp_path / locator.parent / "filing_manifest.json").is_file()
    with pipeline.source_repository.read_source_snapshot(
        "600519",
        document_id,
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        with snapshot.get_primary_source().open() as stream:
            assert stream.read() == _DOCLING_BYTES


def test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二候选的真实 staged exact target UNSAFE 仅终止未提交文档并保留前一结果。

    Args:
        tmp_path: 独立真实仓储根。
        monkeypatch: 在第二次 PDF 返回时放置未声明的真实文件。

    Returns:
        无。

    Raises:
        AssertionError: Phase B 未到达或已确认文档快照丢失时抛出。
    """

    first = _candidate(source_id="A1", fiscal_year=2024)
    second = _candidate(source_id="A2", fiscal_year=2025)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(first, second))
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    batching = _BatchIdentityCnBatchingRepository(tmp_path, repositories)
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repositories,
        batching_repository=batching,
    )
    second_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False
    )
    original_download = discovery.download_report_pdf
    injected: list[Path] = []

    def download_and_inject(candidate: CnReportCandidate) -> DownloadedReportAsset:
        """在第二候选 Phase A 后创建 exact target 非点号未声明文件。

        Args:
            candidate: 当前 provider 候选。

        Returns:
            fake provider PDF 资产。

        Raises:
            OSError: 测试文件创建失败时抛出。
        """

        if candidate.source_id == second.source_id:
            source_root = tmp_path / "portfolio" / "600519" / "filings"
            assert source_root.is_dir()
            target = _identity_directory_path(source_root, _FILING_IDENTITY_NAMESPACE, second_id)
            assert not target.exists()
            target.mkdir()
            (target / "undeclared.bin").write_bytes(b"foreign")
            injected.append(target)
        return original_download(candidate)

    monkeypatch.setattr(discovery, "download_report_pdf", download_and_inject)
    events: list[DownloadEvent] = []

    async def consume() -> None:
        """在异常传播前保留真实事件序列。

        Args:
            无。

        Returns:
            无。

        Raises:
            CnDownloadIntegrityAbort: workflow 的私有封闭中止。
        """

        async for event in pipeline.download_stream(
            ticker="600519", form_type="FY", start_date="2024", end_date="2026",
            overwrite=False, start_is_explicit=True,
        ):
            events.append(event)

    with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as exc_info:
        asyncio.run(consume())
    abort = exc_info.value
    assert isinstance(abort.cause, SourceIntegrityPreflightError)
    assert abort.cause.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert abort.__cause__ is abort.cause
    assert abort.result["status"] == "integrity_failed"
    rows = abort.result["filings"]
    assert isinstance(rows, list)
    assert [row["status"] for row in rows if isinstance(row, dict)] == ["downloaded", "failed"]
    assert isinstance(rows[1], dict)
    assert rows[1]["reason_code"] == "source_integrity_failed"
    assert [event.event_type for event in events].count(DownloadEventType.FILING_FAILED) == 1
    assert DownloadEventType.PIPELINE_COMPLETED not in [event.event_type for event in events]
    assert batching.commit_calls == 2
    assert batching.rollback_calls == 1
    assert injected and injected[0].is_dir()
    first_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    assert pipeline.source_repository.get_source_meta("600519", first_id, SourceKind.FILING)
    with pytest.raises(ValueError, match="identity descriptor"):
        pipeline.source_repository.get_source_meta("600519", second_id, SourceKind.FILING)


def test_cn_post_repair_real_preflight_keeps_confirmed_repair_and_old_company(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repair 已确认发布后真实 whole-kind 预检失败仍保留该 filing 与旧公司元数据。

    Args:
        tmp_path: 独立真实仓储根。
        monkeypatch: 在 post-repair list 前放置非点号外来文件。

    Returns:
        无。

    Raises:
        AssertionError: repair、preflight 抛点或快照所有权漂移时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=_FakeConverter())
    _collect_events(pipeline, start_is_explicit=True)
    candidate = _candidate()
    document_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=candidate.fiscal_year,
        fiscal_period="FY", amended=False,
    )
    locator = pipeline.source_repository.get_source_document_locator("600519", document_id, SourceKind.FILING)
    pdf_path = tmp_path / locator / f"{document_id}.pdf"
    original_pdf = pdf_path.read_bytes()
    pdf_path.write_bytes(original_pdf + b"-repair-needed")
    company_path = tmp_path / "portfolio" / "600519" / "meta.json"
    old_company = company_path.read_bytes()
    source = pipeline.source_repository
    assert isinstance(source, FsSourceDocumentRepository)
    real_list = source.list_source_integrity
    calls: list[int] = []

    def inject_before_post_repair(ticker: str) -> tuple[SourceIntegrityClassification, ...]:
        """在第二次 whole-kind 枚举前让真实 classifier 看到 root 外来文件。

        Args:
            ticker: canonical ticker。

        Returns:
            真实仓储枚举结果。

        Raises:
            SourceIntegrityPreflightError: post-repair root 非法时透传。
        """

        calls.append(1)
        if len(calls) == 2:
            (tmp_path / "portfolio" / "600519" / "filings" / "foreign-after-repair.bin").write_bytes(b"foreign")
        return real_list(ticker)

    monkeypatch.setattr(source, "list_source_integrity", inject_before_post_repair)
    events: list[DownloadEvent] = []

    async def consume() -> None:
        """观察 post-repair 中止之前的真实事件。

        Args:
            无。

        Returns:
            无。

        Raises:
            CnDownloadIntegrityAbort: 已处理 filing 后的私有中止。
        """

        async for event in pipeline.download_stream(
            ticker="600519", form_type="FY", start_date="2024", end_date="2026",
            overwrite=False, start_is_explicit=True,
        ):
            events.append(event)

    with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as exc_info:
        asyncio.run(consume())
    abort = exc_info.value
    assert len(calls) == 2
    assert isinstance(abort.cause, SourceIntegrityPreflightError)
    assert abort.cause.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    rows = abort.result["filings"]
    assert isinstance(rows, list) and len(rows) == 1
    assert isinstance(rows[0], dict) and rows[0]["status"] == "downloaded"
    assert abort.result["status"] == "integrity_failed"
    assert pdf_path.read_bytes() == original_pdf
    assert company_path.read_bytes() == old_company
    assert DownloadEventType.FILING_FAILED not in [event.event_type for event in events]
    assert DownloadEventType.PIPELINE_COMPLETED not in [event.event_type for event in events]


def test_cn_post_repair_company_preswap_typed_spy_preserves_snapshot_and_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """company batch 的受控 pre-swap typed 只在后置调用点携带已确认 filing 快照。

    Args:
        tmp_path: 隔离真实仓储根。
        monkeypatch: 在 company token 已 stage 后模拟 owner pre-swap typed。

    Returns:
        无。

    Raises:
        AssertionError: 调用点、原异常链或旧发布字节漂移时抛出。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=_FakeConverter())
    _collect_events(pipeline, start_is_explicit=True)
    document_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    locator = pipeline.source_repository.get_source_document_locator("600519", document_id, SourceKind.FILING)
    pdf_path = tmp_path / locator / f"{document_id}.pdf"
    original_pdf = pdf_path.read_bytes()
    pdf_path.write_bytes(original_pdf + b"-repair-needed")
    company_path = tmp_path / "portfolio" / "600519" / "meta.json"
    old_company = company_path.read_bytes()
    batching = pipeline.batching_repository
    assert isinstance(batching, FsBatchingRepository)
    core = batching._repository_set.core
    original_commit = batching.commit_batch
    cleanup_error = OSError("journal cleanup failed")
    preflight_error = SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSAFE_PUBLICATION)
    preflight_error.__cause__ = cleanup_error
    company_intents: list[bool] = []

    def company_preswap_failure(batch: BatchToken) -> CompanyMetaCommitOutcome | None:
        """真实 filing commit 后在 company intent 已 stage 的边界注入原 typed。

        Args:
            batch: 当前真实 batch token。

        Returns:
            普通 filing 委托真实 commit 的结果。

        Raises:
            SourceIntegrityPreflightError: company pre-swap 受控失败。
        """

        state = core._resolve_active_batch(batch, batch.ticker)
        if state.company_meta_intent is not None:
            company_intents.append(True)
            batching.rollback_batch(batch)
            raise preflight_error
        return original_commit(batch)

    monkeypatch.setattr(batching, "commit_batch", company_preswap_failure)

    async def consume() -> None:
        """运行同一 selected repair 到后置 company 失败边界。

        Args:
            无。

        Returns:
            无。

        Raises:
            CnDownloadIntegrityAbort: 后置 typed 快照透传。
        """

        async for _event in pipeline.download_stream(
            ticker="600519", form_type="FY", start_date="2024", end_date="2026",
            overwrite=False, ticker_aliases=["600520"], start_is_explicit=True,
        ):
            pass

    with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as exc_info:
        asyncio.run(consume())
    abort = exc_info.value
    assert company_intents == [True]
    assert abort.cause is preflight_error
    assert abort.cause.__cause__ is cleanup_error
    assert abort.result["status"] == "integrity_failed"
    assert type(abort.result["status"]) is str
    rows = abort.result["filings"]
    assert isinstance(rows, list) and len(rows) == 1
    assert isinstance(rows[0], dict) and rows[0]["status"] == "downloaded"
    assert pdf_path.read_bytes() == original_pdf
    assert company_path.read_bytes() == old_company


def test_cn_second_filing_real_commit_tree_preflight_keeps_first_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二候选真实 commit whole-tree 抛 typed 时第一份文档字节仍已确认。

    Args:
        tmp_path: 独立真实仓储根。
        monkeypatch: 在第二候选 Phase A 后向 source root 放置外来文件。

    Returns:
        无。

    Raises:
        AssertionError: 异常未到真实 commit 或已发布字节改变时抛出。
    """

    first = _candidate(source_id="A1", fiscal_year=2024)
    second = _candidate(source_id="A2", fiscal_year=2025)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(first, second))
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    batching = _BatchIdentityCnBatchingRepository(tmp_path, repositories)
    pipeline = _build_pipeline(
        tmp_path=tmp_path, discovery=discovery, converter=_FakeConverter(),
        repository_set=repositories, batching_repository=batching,
    )
    original_download = discovery.download_report_pdf
    injected: list[Path] = []

    def inject_root_on_second(candidate: CnReportCandidate) -> DownloadedReportAsset:
        """让 Phase B exact-target 保持 MISSING，再由真实 commit 检查全树。

        Args:
            candidate: 当前候选。

        Returns:
            fake PDF 资产。

        Raises:
            OSError: root 文件创建失败时抛出。
        """

        if candidate.source_id == second.source_id:
            root = tmp_path / "portfolio" / "600519" / "filings"
            assert root.is_dir()
            rogue = root / "foreign-at-commit.bin"
            rogue.write_bytes(b"foreign")
            injected.append(rogue)
        return original_download(candidate)

    monkeypatch.setattr(discovery, "download_report_pdf", inject_root_on_second)
    first_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    second_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False
    )

    with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as exc_info:
        _collect_events(pipeline, start_is_explicit=True)
    abort = exc_info.value
    assert injected
    assert isinstance(abort.cause, SourceIntegrityPreflightError)
    assert abort.cause.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert batching.commit_calls == 3  # company、首候选、第二候选的真实 commit。
    rows = abort.result["filings"]
    assert isinstance(rows, list) and len(rows) == 2
    assert isinstance(rows[0], dict) and rows[0]["status"] == "downloaded"
    assert isinstance(rows[1], dict) and rows[1]["status"] == "failed"
    locator = pipeline.source_repository.get_source_document_locator("600519", first_id, SourceKind.FILING)
    assert (tmp_path / locator / f"{first_id}.pdf").read_bytes() == _PDF_BYTES
    with pytest.raises(FileNotFoundError):
        pipeline.source_repository.get_source_document_locator("600519", second_id, SourceKind.FILING)


def test_cn_mid_filing_revision_conflict_injection_aborts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """受控边界冲突保原因并中止，后续候选不得执行。

    Args:
        tmp_path: 独立仓储根。
        monkeypatch: 在第一候选 Phase A owner 查询边界注入冲突。

    Returns:
        无。

    Raises:
        AssertionError: 中止链或未执行候选事实失守时抛出。
    """

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(source_id="A1", fiscal_year=2024), _candidate(source_id="A2", fiscal_year=2025)),
    )
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=_FakeConverter())
    source = pipeline.source_repository
    assert isinstance(source, FsSourceDocumentRepository)
    real_classify = source.classify_source_integrity
    injected: list[bool] = []

    def first_phase_a_conflict(
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> SourceIntegrityClassification:
        """只在第一候选的单 filing Phase A 抛受控冲突。

        Args:
            ticker: 当前 ticker。
            document_id: 当前候选 ID。
            source_kind: 来源种类。

        Returns:
            其它调用的真实 owner 分类。

        Raises:
            SourceIntegrityRevisionConflictError: 首次调用的受控注入。
        """

        if not injected:
            injected.append(True)
            raise SourceIntegrityRevisionConflictError()
        return real_classify(ticker, document_id, source_kind)

    monkeypatch.setattr(source, "classify_source_integrity", first_phase_a_conflict)
    with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as exc_info:
        _collect_events(pipeline, start_is_explicit=True)
    assert isinstance(exc_info.value.cause, SourceIntegrityRevisionConflictError)
    assert exc_info.value.__cause__ is exc_info.value.cause
    result = exc_info.value.result
    rows = result["filings"]
    assert isinstance(rows, list) and len(rows) == 1
    assert isinstance(rows[0], dict) and rows[0]["status"] == "failed"
    assert rows[0]["reason_code"] == "source_integrity_failed"
    assert injected == [True]


def test_cn_post_repair_real_second_selected_source_conflict_preserves_first_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repair 后另一 selected source 真正变坏时显式仍需修复原因 保留已确认行。

    Args:
        tmp_path: 独立真实仓储根。
        monkeypatch: 在后置真实枚举前修改第二份已发布 PDF。

    Returns:
        无。

    Raises:
        AssertionError: 后置 classifier、原异常或旧公司状态漂移时抛出。
    """

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(source_id="A1", fiscal_year=2024), _candidate(source_id="A2", fiscal_year=2025)),
    )
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=_FakeConverter())
    _collect_events(pipeline, start_is_explicit=True)
    first_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False
    )
    second_id, _ = build_cn_filing_ids(
        ticker="600519", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False
    )
    first_locator = pipeline.source_repository.get_source_document_locator("600519", first_id, SourceKind.FILING)
    second_locator = pipeline.source_repository.get_source_document_locator("600519", second_id, SourceKind.FILING)
    first_pdf = tmp_path / first_locator / f"{first_id}.pdf"
    second_pdf = tmp_path / second_locator / f"{second_id}.pdf"
    original_first = first_pdf.read_bytes()
    first_pdf.write_bytes(original_first + b"-repair-needed")
    company_path = tmp_path / "portfolio" / "600519" / "meta.json"
    old_company = company_path.read_bytes()
    source = pipeline.source_repository
    assert isinstance(source, FsSourceDocumentRepository)
    real_list = source.list_source_integrity
    calls: list[int] = []

    def second_source_changes_after_repair(ticker: str) -> tuple[SourceIntegrityClassification, ...]:
        """第二次真实枚举前把另一 selected source 改为待修复。

        Args:
            ticker: canonical ticker。

        Returns:
            真实仓储的完整性 inventory。

        Raises:
            OSError: 文件变更或仓储读取失败时抛出。
        """

        calls.append(1)
        if len(calls) == 2:
            second_pdf.write_bytes(second_pdf.read_bytes() + b"-new-corruption")
        return real_list(ticker)

    monkeypatch.setattr(source, "list_source_integrity", second_source_changes_after_repair)
    with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as exc_info:
        _collect_events(pipeline, start_is_explicit=True)
    abort = exc_info.value
    assert len(calls) == 2
    assert isinstance(abort.cause, SourceIntegrityRepairRequiredError)
    assert abort.__cause__ is abort.cause
    rows = abort.result["filings"]
    assert isinstance(rows, list) and len(rows) == 1
    assert isinstance(rows[0], dict) and rows[0]["status"] == "downloaded"
    assert first_pdf.read_bytes() == original_first
    assert company_path.read_bytes() == old_company


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
    """whole manifest 缺失且 repair target 未选中时必须在首个新 batch 前拒绝。"""

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
    manifest_path = tmp_path / locator.parent / "filing_manifest.json"
    manifest_path.unlink()
    begin_calls = batching_repository.begin_calls
    discovery.candidates = ()

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        _collect_events(pipeline, start_is_explicit=True)

    assert exc_info.value.reason is SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED
    assert batching_repository.begin_calls == begin_calls
    assert pipeline._company_repository.get_company_meta("600519") == old_company
    assert manifest_path.exists() is False


def test_cn_whole_manifest_missing_with_multiple_selected_actual_sources_fails_closed(
    tmp_path: Path,
) -> None:
    """多个 actual/selected source 共享 manifest 缺失时不得任选一个 repair。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: preflight 未以 MULTIPLE_REPAIR_REQUIRED 零 mutation 拒绝时抛出。
    """

    fy_candidate = _candidate(source_id="FY", fiscal_period="FY")
    h1_candidate = _candidate(source_id="H1", fiscal_period="H1")
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityCnBatchingRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(fy_candidate,))
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=_FakeConverter(),
        repository_set=repository_set,
        batching_repository=batching_repository,
    )
    _collect_events(pipeline, start_is_explicit=True, form_type="FY")
    discovery.candidates = (h1_candidate,)
    _collect_events(pipeline, start_is_explicit=True, form_type="H1")
    document_ids = tuple(
        build_cn_filing_ids(
            ticker="600519",
            form_type=candidate.period_projection.identity_period,
            fiscal_year=candidate.fiscal_year,
            fiscal_period=candidate.period_projection.identity_period,
            amended=candidate.amended,
        )[0]
        for candidate in (fy_candidate, h1_candidate)
    )
    first_locator = pipeline.source_repository.get_source_document_locator(
        "600519",
        document_ids[0],
        SourceKind.FILING,
    )
    manifest_path = tmp_path / first_locator.parent / "filing_manifest.json"
    manifest_path.unlink()
    begin_calls = batching_repository.begin_calls
    download_calls = discovery.download_calls
    old_company = pipeline._company_repository.get_company_meta("600519")
    discovery.candidates = (fy_candidate, h1_candidate)

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        _collect_events(
            pipeline,
            start_is_explicit=True,
            form_type=None,
        )

    assert exc_info.value.reason is SourceIntegrityPreflightReason.MULTIPLE_REPAIR_REQUIRED
    assert batching_repository.begin_calls == begin_calls
    assert discovery.download_calls == download_calls
    assert pipeline._company_repository.get_company_meta("600519") == old_company
    assert manifest_path.exists() is False
    for document_id in document_ids:
        classification = pipeline.source_repository.classify_source_integrity(
            "600519",
            document_id,
            SourceKind.FILING,
        )
        assert classification.status is SourceIntegrityStatus.REPAIR_REQUIRED
        assert classification.reasons == (SourceIntegrityReason.SOURCE_MANIFEST_MISSING,)


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


class _IdentityObservationSourceRepository(FsSourceDocumentRepository):
    """仅监视真实 batch 观察与原 public 身份读取调用。"""

    def __init__(self, root: Path, repository_set: _FsRepositorySet) -> None:
        """初始化。参数：root/repository_set 为真实仓储。返回：无。异常：原初始化异常。"""
        super().__init__(root, repository_set=repository_set)
        self.views: list[SourceMetaReadView] = []
        self.public_lists = 0
        self.public_gets = 0
        self.reset_calls = 0
        self.corrupt_before_window: int | None = None
        self.corrupt_meta: Path | None = None

    def read_source_meta_view(self, ticker: str, source_kind: SourceKind) -> SourceMetaReadView:
        """读取真实新窗口。参数：ticker/source_kind 为范围。返回：真实观察。异常：原读取异常。"""
        if self.corrupt_before_window == len(self.views) + 1:
            assert self.corrupt_meta is not None
            self.corrupt_meta.write_bytes(b"{")
        view = super().read_source_meta_view(ticker, source_kind)
        self.views.append(view)
        return view

    def list_source_document_ids(self, ticker: str, source_kind: SourceKind) -> list[str]:
        """监视原 public list。参数：ticker/source_kind 为范围。返回：真实列表。异常：原读取异常。"""
        self.public_lists += 1
        return super().list_source_document_ids(ticker, source_kind)

    def get_source_meta(self, ticker: str, document_id: str, source_kind: SourceKind) -> DocumentMeta:
        """监视原 public get。参数：ticker/document_id/source_kind 为目标。返回：原 meta。异常：原读取异常。"""
        self.public_gets += 1
        return super().get_source_meta(ticker, document_id, source_kind)


    def reset_source_document(self, ticker: str, document_id: str, source_kind: SourceKind, *, batch: BatchToken) -> None:
        """监视真实 reset。参数：ticker/document_id/source_kind 为目标；batch 为能力。返回：无。异常：原仓储异常。"""
        self.reset_calls += 1
        super().reset_source_document(ticker, document_id, source_kind, batch=batch)


def _publish_identity_binding(
    writer: CnPipeline, ticker: str, candidate: CnReportCandidate,
    document_id: str, internal_id: str, *, remove_id: str | None,
) -> None:
    """独立真实 writer 发布新绑定，使用原 blob/source/manifest owner。

    参数：writer 为独立仓储宿主；ticker/candidate 为来源；document_id/internal_id 为新身份；remove_id 为旧目标。
    返回：无。异常：原仓储/commit 异常。
    """
    batch = writer.batching_repository.begin_batch(ticker)
    if remove_id is not None:
        writer.source_repository.reset_source_document(ticker, remove_id, SourceKind.FILING, batch=batch)
    handle = SourceHandle(ticker=ticker, document_id=document_id, source_kind=SourceKind.FILING.value)
    pdf_name, docling_name = f"{document_id}.pdf", f"{document_id}_docling.json"
    pdf = writer.blob_repository.store_file(handle, pdf_name, io.BytesIO(_PDF_BYTES), batch=batch, content_type="application/pdf")
    docling = writer.blob_repository.store_file(handle, docling_name, io.BytesIO(_DOCLING_BYTES), batch=batch, content_type="application/json")
    commit_cn_filing_source_document(
        source_repository=writer.source_repository, processed_repository=writer.processed_repository,
        ticker=ticker, document_id=document_id, internal_document_id=internal_id, primary_document=docling_name,
        file_entries=[build_cn_file_entry(filename=pdf_name, file_meta=pdf, source_label="original"),
                      build_cn_file_entry(filename=docling_name, file_meta=docling, source_label="docling")],
        candidate=candidate,
        profile=CnCompanyProfile(provider="hkexnews", company_id="HKEX:7609", company_name="腾讯控股", ticker=ticker),
        pdf_sha256=hashlib.sha256(_PDF_BYTES).hexdigest(), remote_fingerprint=build_remote_fingerprint(candidate),
        source_fingerprint=build_content_fingerprint(pdf_bytes=_PDF_BYTES, docling_json_bytes=_DOCLING_BYTES),
        previous_completed_meta=None, source_meta_exists=False, batch=batch,
    )
    writer.batching_repository.commit_batch(batch)


async def _collect_hk_identity_events(
    pipeline: CnPipeline, events: list[DownloadEvent], *,
    after_event: Callable[[DownloadEvent], None] | None = None,
    overwrite: bool = False, cancel_checker: Callable[[], bool] | None = None,
) -> None:
    """收集真实 HK 流并在用户事件边界运行测试 writer。

    参数：pipeline 为真实宿主；events 为收集器；after_event 为事件边界动作；overwrite/cancel_checker 为原输入。
    返回：无。异常：原 pipeline 异常；已发生事件保存在 events。
    """
    async for event in pipeline.download_stream(
        ticker="0700", form_type="FY", start_date="2024", end_date="2026",
        overwrite=overwrite, start_is_explicit=True, cancel_checker=cancel_checker,
    ):
        events.append(event)
        if after_event is not None:
            after_event(event)


class _IdentityStartWriter:
    """在首个 start yield 后通过独立 writer 改变绑定或实际损坏 meta。"""

    def __init__(self, root: Path, writer: CnPipeline, candidate: CnReportCandidate, old_id: str, operation: str) -> None:
        """初始化。参数：root 为隔离根；writer/candidate/old_id 为目标；operation 为动作。返回：无。异常：无。"""
        self.root = root
        self.writer, self.candidate, self.old_id, self.operation = writer, candidate, old_id, operation
        self.ran = False

    def __call__(self, event: DownloadEvent) -> None:
        """执行一次 writer。参数：event 为已发事件。返回：无。异常：原仓储异常。"""
        if event.event_type is not DownloadEventType.FILING_STARTED or self.ran:
            return
        self.ran = True
        if self.operation == "rebind":
            _publish_identity_binding(self.writer, "0700", self.candidate, "rebound", "internal-rebound", remove_id=self.old_id)
        else:
            locator = self.writer.source_repository.get_source_document_locator("0700", self.old_id, SourceKind.FILING)
            meta = self.root / locator / "meta.json"
            if self.operation == "missing":
                meta.unlink()
            else:
                meta.write_bytes(b"{")


@pytest.mark.parametrize("second_run", (False, True))
def test_hk_identity_windows_count_and_previous_meta_are_separate(tmp_path: Path, second_run: bool) -> None:
    """全 HK 两候选 batch=1+2n；下一 filing 观察前一 publication，原 previous_meta get 单列。

    参数：tmp_path 为隔离根；second_run 为已有来源增量路径。返回：无。异常：AssertionError。
    """
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    candidates = (_candidate(provider="hkexnews", source_id="first", fiscal_year=2025),
                  _candidate(provider="hkexnews", source_id="second", fiscal_year=2024))
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=candidates)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()),
                               hk_discovery=discovery, converter=_FakeConverter(), repository_set=repository_set,
                               source_repository=source)
    if second_run:
        asyncio.run(_collect_hk_identity_events(pipeline, []))
        source.views.clear()
        source.public_lists = source.public_gets = 0
    events: list[DownloadEvent] = []
    asyncio.run(_collect_hk_identity_events(pipeline, events))
    assert len(source.views) == 5
    assert source.public_lists == 0
    assert source.public_gets == (2 if second_run else 0)
    assert [len(view.entries) for view in source.views] == ([2, 2, 2, 2, 2] if second_run else [0, 0, 0, 1, 1])
    starts = [event.document_id for event in events if event.event_type is DownloadEventType.FILING_STARTED]
    terminals = [event.document_id for event in events if event.event_type is DownloadEventType.FILING_COMPLETED]
    assert starts == terminals and len(starts) == 2
    summary = _final_result(events)["summary"]
    assert isinstance(summary, dict)
    assert {key: summary[key] for key in ("total", "downloaded", "skipped", "failed")} == {
        "total": 2, "downloaded": 0 if second_run else 2, "skipped": 2 if second_run else 0, "failed": 0,
    }


@pytest.mark.parametrize("operation", ("rebind", "malformed", "missing"))
def test_hk_stream_reads_fresh_after_start_yield(tmp_path: Path, operation: str) -> None:
    """start 后真实 writer 改变绑定时 stream 新读；坏 meta 保持 ordinary failure 并继续。

    参数：tmp_path 为隔离根；operation 为真实 writer 动作。返回：无。异常：AssertionError。
    """
    candidate = _candidate(provider="hkexnews", source_id="first", fiscal_year=2025)
    second = _candidate(provider="hkexnews", source_id="second", fiscal_year=2024)
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()),
        hk_discovery=_FakeDiscoveryClient(tmp_path, (candidate,)), converter=_FakeConverter(),
        repository_set=repository_set, source_repository=source)
    asyncio.run(_collect_hk_identity_events(pipeline, []))
    old_id = source.views[-1].entries[0].document_id if source.views[-1].entries else build_cn_filing_ids(
        ticker="0700", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False)[0]
    discovery = _FakeDiscoveryClient(tmp_path, (candidate, second))
    follow = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()),
        hk_discovery=discovery, converter=_FakeConverter(), repository_set=repository_set, source_repository=source)
    writer = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), converter=_FakeConverter())
    hook = _IdentityStartWriter(tmp_path, writer, candidate, old_id, operation)
    source.views.clear()
    events: list[DownloadEvent] = []
    if operation == "rebind":
        asyncio.run(_collect_hk_identity_events(follow, events, after_event=hook))
        assert len(source.views) == 5
        assert source.views[1].entries[0].document_id == old_id
        assert source.views[2].entries[0].document_id == "rebound"
        starts = [e.document_id for e in events if e.event_type is DownloadEventType.FILING_STARTED]
        terminals = [e.document_id for e in events if e.event_type is DownloadEventType.FILING_COMPLETED]
        assert starts[0] == old_id and terminals[0] == "rebound"
        assert _final_result(events)["status"] == "ok"
        assert source.get_source_meta("0700", "rebound", SourceKind.FILING)["internal_document_id"] == "internal-rebound"
    else:
        # stream 内当前 ordinary failure 已记录；下一 start 在原 try 外再次遭遇坏 meta。
        with pytest.raises(FileNotFoundError if operation == "missing" else ValueError):
            asyncio.run(_collect_hk_identity_events(follow, events, after_event=hook))
        failed = [e for e in events if e.event_type is DownloadEventType.FILING_FAILED]
        assert len(failed) == 1 and failed[0].document_id == old_id
        row = failed[0].payload["filing_result"]
        assert isinstance(row, dict)
        assert row["reason_code"] == ("storage_failed" if operation == "missing" else "filing_execution_failed")
        assert len([e for e in events if e.event_type is DownloadEventType.FILING_STARTED]) == 1
        assert discovery.download_calls == 0
        assert len(source.views) == 4


class _IdentityChurnConverter:
    """转换边界用独立真实 writer 改 target revision，保留各轮 PDF/Docling acquisition。"""

    def __init__(self, writer: CnPipeline, candidate: CnReportCandidate, changes: int) -> None:
        """初始化。参数：writer 为独立仓储；candidate 为目标；changes 为发布轮数。返回：无。异常：无。"""
        self.writer, self.candidate, self.changes = writer, candidate, changes
        self.calls = 0
        self.document_id = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=candidate.fiscal_year,
                                               fiscal_period="FY", amended=False)[0]

    async def convert_to_json_bytes(
        self, input_bytes: bytes, stream_name: str, *, config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回分轮 payload 并发布 revision。参数：input_bytes/stream_name/config/cancellation 为原转换输入。

        返回：本轮 Docling 资产。异常：真实 writer 发布异常。
        """
        self.calls += 1
        if self.calls <= self.changes:
            _publish_identity_binding(self.writer, "0700", self.candidate, self.document_id,
                                      f"internal-{self.calls}", remove_id=None if self.calls == 1 else self.document_id)
        payload = json.dumps({"round": self.calls}).encode()
        return DoclingConversionResult(json_bytes=payload, size=len(payload), sha256=hashlib.sha256(payload).hexdigest())


@pytest.mark.parametrize("changes", (1, 2, 3))
def test_hk_retry_rounds_read_fresh_and_discard_old_assets(tmp_path: Path, changes: int) -> None:
    """真实 target churn 使 round0/1/2 新观察，耗尽 typed 中止，成功仅提交最后 payload。

    参数：tmp_path 为隔离根；changes 为独立 publication 次数。返回：无。异常：AssertionError。
    """
    candidate = _candidate(provider="hkexnews", source_id="retry", fiscal_year=2025)
    writer = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), converter=_FakeConverter())
    converter = _IdentityChurnConverter(writer, candidate, changes)
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(tmp_path, (candidate,))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), hk_discovery=discovery,
                               converter=converter, repository_set=repository_set, source_repository=source)
    events: list[DownloadEvent] = []
    if changes == 3:
        with pytest.raises(_cn_download_workflow.CnDownloadIntegrityAbort) as raised:
            asyncio.run(_collect_hk_identity_events(pipeline, events, overwrite=True))
        assert isinstance(raised.value.cause, SourceIntegrityRevisionConflictError)
        assert raised.value.__cause__ is raised.value.cause
        assert raised.value.result["status"] == "integrity_failed"
    else:
        asyncio.run(_collect_hk_identity_events(pipeline, events, overwrite=True))
    rounds = min(changes + 1, 3)
    assert len(source.views) == 1 + 2 + rounds - 1
    assert converter.calls == discovery.download_calls == rounds
    assert source.views[2].entries == ()
    for i, view in enumerate(source.views[3:], start=1):
        assert view.entries[0].source_meta["internal_document_id"] == f"internal-{i}"
    assert len([e for e in events if e.event_type is DownloadEventType.FILING_STARTED]) == 1
    terminals = [e for e in events if e.event_type in (DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED)]
    assert len(terminals) == 1
    row = terminals[0].payload["filing_result"]
    assert isinstance(row, dict)
    assert row["status"] == ("failed" if changes == 3 else "downloaded")
    if changes == 3:
        assert row["reason_code"] == "source_integrity_failed"
    else:
        handle = source.get_source_handle("0700", converter.document_id, SourceKind.FILING)
        assert json.loads(pipeline.blob_repository.read_file_bytes(handle, f"{converter.document_id}_docling.json")) == {"round": rounds}
        assert source.get_source_meta("0700", converter.document_id, SourceKind.FILING)["internal_document_id"] == f"internal-{changes}"
    if changes != 3:
        assert _final_result(events)["status"] == "ok"
    else:
        assert not any(e.event_type is DownloadEventType.PIPELINE_COMPLETED for e in events)


@pytest.mark.parametrize("corruption", ("unsafe", "malformed", "missing"))
def test_hk_direct_stream_preserves_raw_binding_then_original_rejection(
    tmp_path: Path, corruption: str,
) -> None:
    """无 ticker preflight 的 direct stream 保留 raw 可读身份，Phase A 拒绝或原 get 错不修改旧发布。

    参数：tmp_path 为隔离根；corruption 为实际文件损坏。返回：无。异常：AssertionError。
    """
    candidate = _candidate(provider="hkexnews")
    writer = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), converter=_FakeConverter())
    _publish_identity_binding(writer, "600519", candidate, "A-original", "internal-original", remove_id=None)
    _publish_identity_binding(writer, "600519", replace(candidate, source_id="sibling"), "Z-sibling", "internal-sibling", remove_id=None)
    sibling_locator = writer.source_repository.get_source_document_locator("600519", "Z-sibling", SourceKind.FILING)
    original_locator = writer.source_repository.get_source_document_locator("600519", "A-original", SourceKind.FILING)
    if corruption == "unsafe":
        (tmp_path / original_locator / "undeclared.bin").write_bytes(b"unsafe")
    elif corruption == "malformed":
        (tmp_path / sibling_locator / "meta.json").write_bytes(b"{")
    else:
        (tmp_path / sibling_locator / "meta.json").unlink()
    before = {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()}
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(tmp_path, (candidate,))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter,
                               repository_set=repository_set, source_repository=source)
    expected = SourceIntegrityPreflightError if corruption == "unsafe" else (ValueError if corruption == "malformed" else FileNotFoundError)
    with pytest.raises(expected) as raised:
        _collect_single_filing_events(pipeline=pipeline, candidate=candidate)
    assert len(source.views) == 1
    if corruption == "unsafe":
        assert resolve_cn_download_ids("600519", candidate, build_cn_download_identity_index(source.views[0])) == ("A-original", "internal-original")
        assert isinstance(raised.value, SourceIntegrityPreflightError)
        assert raised.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    else:
        assert raised.value is source.views[0].read_error
    assert source.reset_calls == discovery.download_calls == converter.calls == 0
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()}


def test_hk_repair_sort_reuses_w0_and_company_gate_keeps_original_order(tmp_path: Path) -> None:
    """批初 accepted/repair 排序共享一次 W0，真实修复先于 clean 候选且 company gate 不前移。

    参数：tmp_path 为隔离根。返回：无。异常：AssertionError 或原仓储异常。
    """
    first = _candidate(provider="hkexnews", source_id="clean", fiscal_year=2025)
    repair = _candidate(provider="hkexnews", source_id="repair", fiscal_year=2024)
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(tmp_path, (first, repair))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), hk_discovery=discovery,
                               converter=_FakeConverter(), repository_set=repository_set, source_repository=source)
    asyncio.run(_collect_hk_identity_events(pipeline, []))
    repair_id = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False)[0]
    locator = source.get_source_document_locator("0700", repair_id, SourceKind.FILING)
    (tmp_path / locator / f"{repair_id}_docling.json").unlink()
    source.views.clear()
    events: list[DownloadEvent] = []
    asyncio.run(_collect_hk_identity_events(pipeline, events))
    assert len(source.views) == 5
    assert [e.document_id for e in events if e.event_type is DownloadEventType.FILING_STARTED][0] == repair_id
    assert source.classify_source_integrity("0700", repair_id, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    summary = _final_result(events)["summary"]
    assert isinstance(summary, dict) and summary["downloaded"] == summary["skipped"] == 1 and summary["failed"] == 0


@pytest.mark.parametrize("prior_row", (False, True))
def test_hk_start_read_error_stays_outside_filing_try_and_keeps_prior_events(tmp_path: Path, prior_row: bool) -> None:
    """start 新读出错不造当前 start/failed，也不改造已有 rows 为 typed partial abort。

    参数：tmp_path 为隔离根；prior_row 为首份已成功事件路径。返回：无。异常：AssertionError。
    """
    first = _candidate(provider="hkexnews", source_id="first", fiscal_year=2025)
    second = _candidate(provider="hkexnews", source_id="second", fiscal_year=2024)
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()),
                               hk_discovery=_FakeDiscoveryClient(tmp_path, (first, second)), converter=_FakeConverter(),
                               repository_set=repository_set, source_repository=source)
    asyncio.run(_collect_hk_identity_events(pipeline, []))
    first_id = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=2025, fiscal_period="FY", amended=False)[0]
    source.corrupt_meta = tmp_path / source.get_source_document_locator("0700", first_id, SourceKind.FILING) / "meta.json"
    source.views.clear()
    source.corrupt_before_window = 4 if prior_row else 2
    events: list[DownloadEvent] = []
    with pytest.raises(ValueError) as raised:
        asyncio.run(_collect_hk_identity_events(pipeline, events))
    assert raised.value is source.views[-1].read_error
    assert len([e for e in events if e.event_type is DownloadEventType.FILING_STARTED]) == int(prior_row)
    assert len([e for e in events if e.event_type is DownloadEventType.FILING_COMPLETED]) == int(prior_row)
    assert not [e for e in events if e.event_type in (DownloadEventType.FILING_FAILED, DownloadEventType.PIPELINE_COMPLETED)]


class _IdentityStartCancel:
    """在 start 事件处发出取消，证明 stream 入口先取消后读取。"""

    def __init__(self, state: _CancelState) -> None:
        """初始化。参数：state 为原取消 token。返回：无。异常：无。"""
        self.state = state

    def __call__(self, event: DownloadEvent) -> None:
        """start 时取消。参数：event 为原事件。返回：无。异常：无。"""
        if event.event_type is DownloadEventType.FILING_STARTED:
            self.state.cancelled = True


class _IdentityCancelError:
    """保留调用者取消或普通 checker 错误的原对象。"""

    def __init__(self, error: RuntimeError) -> None:
        """初始化。参数：error 为原对象。返回：无。异常：无。"""
        self.error = error

    def __call__(self) -> bool:
        """抛原 checker 错。参数：无。返回：无。异常：原 RuntimeError 子类。"""
        raise self.error


def test_hk_cancel_after_start_suppresses_stream_identity_read(tmp_path: Path) -> None:
    """start 后取消只观察 W0/start，不读 stream，结果保留 cancelled 与零 rows。

    参数：tmp_path 为隔离根。返回：无。异常：AssertionError。
    """
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    discovery = _FakeDiscoveryClient(tmp_path, (_candidate(provider="hkexnews"),))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), hk_discovery=discovery,
                               converter=_FakeConverter(), repository_set=repository_set, source_repository=source)
    state = _CancelState()
    events: list[DownloadEvent] = []
    asyncio.run(_collect_hk_identity_events(pipeline, events, after_event=_IdentityStartCancel(state), cancel_checker=state))
    assert len(source.views) == 2 and discovery.download_calls == 0
    assert _final_result(events)["status"] == "cancelled"
    assert _final_result(events)["filings"] == []
    assert not [e for e in events if e.event_type in (DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED)]


@pytest.mark.parametrize("error", [CnDownloadCancelledError("same cancel"), RuntimeError("checker failure")])
def test_hk_direct_cancel_and_checker_error_precede_identity_read(tmp_path: Path, error: RuntimeError) -> None:
    """direct 取消/非取消 checker 错保持原对象，均先于新身份读取。

    参数：tmp_path 为隔离根；error 为调用者对象。返回：无。异常：AssertionError。
    """
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = _IdentityObservationSourceRepository(tmp_path, repository_set)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=_FakeDiscoveryClient(tmp_path, ()), converter=_FakeConverter(),
                               repository_set=repository_set, source_repository=source)
    with pytest.raises(type(error)) as raised:
        _collect_single_filing_events(pipeline=pipeline, candidate=_candidate(provider="hkexnews"), cancel_checker=_IdentityCancelError(error))
    assert raised.value is error and not source.views
