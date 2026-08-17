"""Filing upload publication identity 与纯裁决 owner 测试。"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.company_metadata_warning import (
    COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    CompanyMetadataWarning,
    CompanyMetadataWarningKind,
    company_metadata_warnings_to_json,
    project_company_name_ignored_warning,
)
from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    CompanyMetaCommitOutcome,
    CompanyNameIgnoredChange,
)
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    CompanyMetaInventoryEntry,
    SourceDocumentRevision,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsUploadFilingRequest,
    ValidatedFinsUploadFilingRequest,
    validate_fins_upload_filing_request,
)
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    FilingInitialSkipDisposition,
    UploadOperationResult,
    _PendingFileAsset,
    _PreparedFilingAssetMutation,
    build_sec_filing_ids,
)
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionResult,
)
from dayu.fins.pipelines.filing_upload_publication import (
    FilingUploadPublicationOutcome,
    FilingUploadPublicationDisposition,
    FilingUploadPublishMode,
    arbitrate_filing_upload_publication,
    execute_prepared_filing_publication,
)
from dayu.fins.storage import (
    FILING_UPLOAD_ASSET_SOURCE_DOCLING,
    FILING_UPLOAD_ASSET_SOURCE_ORIGINAL,
    FilingUploadAssetDescriptor,
    FilingUploadPublicationIdentity,
    FilingUploadPublishedState,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsSourceDocumentRepository,
    SourceIntegrityClassification,
    SourceIntegrityReason,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureError,
    fins_upload_prevalidation_corruption_failure,
    fins_upload_prevalidation_io_failure,
)
from dayu.fins.upload_repair_contract import NoExistingSourceRepair

_FINGERPRINT_A = "a" * 64
_FINGERPRINT_B = "b" * 64
_ORIGINAL_PRIMARY_SHA = "c" * 64
_ORIGINAL_COMPANION_SHA = "d" * 64
_DOCLING_SHA = "e" * 64
_RESOLVER_VERSION = "market_resolver_v1.0.0"


class _PublicationBatchRecorder:
    """记录 shared owner batch lifecycle 的无 I/O 测试仓储。"""

    def __init__(
        self,
        *,
        commit_outcome: CompanyMetaCommitOutcome | None = None,
        commit_error: OSError | None = None,
        events: list[str] | None = None,
        forbid_rollback_after_commit: bool = False,
    ) -> None:
        """初始化 lifecycle 记录与可选 metadata commit 行为。

        Args:
            commit_outcome: commit 正常返回的可选 exact typed outcome。
            commit_error: commit 消费 capability 后需要抛出的可选异常。
            events: 可选共享顺序记录。
            forbid_rollback_after_commit: 是否直接拒绝 commit 后 caller rollback。

        Returns:
            无。

        Raises:
            无。
        """

        self.begin_tokens: list[BatchToken] = []
        self.commit_tokens: list[BatchToken] = []
        self.rollback_tokens: list[BatchToken] = []
        self.commit_outcome = commit_outcome
        self.commit_error = commit_error
        self.events = events if events is not None else []
        self.forbid_rollback_after_commit = forbid_rollback_after_commit

    def begin_batch(self, ticker: str) -> BatchToken:
        """产生并记录测试 batch capability。

        Args:
            ticker: canonical ticker。

        Returns:
            新测试 batch token。

        Raises:
            无。
        """

        token = BatchToken(transaction_id=f"publication-{len(self.begin_tokens)}", ticker=ticker)
        self.begin_tokens.append(token)
        return token

    def commit_batch(self, batch: BatchToken) -> CompanyMetaCommitOutcome | None:
        """记录 capability transfer，并返回配置 outcome 或抛配置异常。

        Args:
            batch: caller-owned batch capability。

        Returns:
            配置的 company-meta outcome；structural 场景默认返回 ``None``。

        Raises:
            OSError: 配置 commit failure 时在消费 capability 后抛出。
        """

        self.commit_tokens.append(batch)
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error
        return self.commit_outcome

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录 owner rollback。

        Args:
            batch: caller-owned batch capability。

        Returns:
            无。

        Raises:
            AssertionError: 配置禁止 commit 后 rollback 且发生该调用时抛出。
        """

        self.rollback_tokens.append(batch)
        self.events.append("rollback")
        if self.forbid_rollback_after_commit and self.commit_tokens:
            raise AssertionError("commit 已消费 capability 后禁止 caller rollback")

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """返回空 recovery action。

        Args:
            dry_run: 是否只检查；测试仓储无 orphan。

        Returns:
            空 action tuple。

        Raises:
            无。
        """

        del dry_run
        return ()


class _MetadataStageRecorder:
    """记录 metadata-only skip 的唯一 company intent stage。"""

    def __init__(
        self,
        *,
        stage_error: OSError | None = None,
        events: list[str] | None = None,
    ) -> None:
        """初始化空 stage 记录与可选 stage failure。

        Args:
            stage_error: commit 前 stage 应抛出的可选异常。
            events: 可选共享顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self.stage_error = stage_error
        self.intents: list[CompanyMetaCommitIntent] = []
        self.stage_tokens: list[BatchToken] = []
        self.events = events if events is not None else []

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """返回空盘点结果。

        Args:
            无。

        Returns:
            空 inventory。

        Raises:
            无。
        """

        return []

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """返回固定 fresh company meta。

        Args:
            ticker: 预期 canonical ticker。

        Returns:
            AAPL fresh company meta。

        Raises:
            ValueError: ticker 不是 AAPL 时抛出。
        """

        if ticker != "AAPL":
            raise ValueError("fixture 仅支持 AAPL")
        return _fresh_company_meta()

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """记录 intent，并在配置时于 capability transfer 前失败。

        Args:
            intent: fresh validator 产生的 preserve intent。
            batch: caller-owned batch capability。

        Returns:
            无。

        Raises:
            OSError: 配置 stage failure 时抛出。
        """

        self.intents.append(intent)
        self.stage_tokens.append(batch)
        self.events.append("stage")
        if self.stage_error is not None:
            raise self.stage_error

    def resolve_company_ticker(self, ticker: str) -> str | None:
        """按 fixture identity 解析 AAPL。

        Args:
            ticker: 待解析 ticker。

        Returns:
            AAPL 命中时返回 AAPL，否则返回 ``None``。

        Raises:
            无。
        """

        return "AAPL" if ticker == "AAPL" else None


class _WaitingPublicationBatchRecorder(_PublicationBatchRecorder):
    """在 begin 返回 capability 前暴露可控 writer 等待窗口。"""

    def __init__(self, entered: Event, release: Event) -> None:
        """初始化等待边界。

        Args:
            entered: begin 已进入等待窗口的通知。
            release: 允许 begin 返回的释放信号。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self._entered = entered
        self._release = release

    def begin_batch(self, ticker: str) -> BatchToken:
        """等待测试释放后再返回 batch capability。

        Args:
            ticker: canonical ticker。

        Returns:
            父类产生的 batch capability。

        Raises:
            TimeoutError: 测试未在边界内释放 writer 时抛出。
        """

        self._entered.set()
        if not self._release.wait(timeout=10):
            raise TimeoutError("publication writer wait 未释放")
        return super().begin_batch(ticker)


class _FailingBeginBatchRecorder(_PublicationBatchRecorder):
    """在 batch acquire 边界抛出固定 RuntimeError。"""

    def begin_batch(self, ticker: str) -> BatchToken:
        """模拟 reservation/lock acquire operational failure。

        Args:
            ticker: canonical ticker。

        Returns:
            不返回。

        Raises:
            RuntimeError: 始终抛出。
        """

        del ticker
        raise RuntimeError("private acquire failure")


class _RollbackFailureBatchRecorder(_PublicationBatchRecorder):
    """在 rollback 边界抛出 caller 指定的异常。"""

    def __init__(self, error: BaseException) -> None:
        """初始化 rollback failure。

        Args:
            error: rollback 时原样抛出的异常。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self._error = error

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录 rollback 后抛出预设异常。

        Args:
            batch: caller-owned batch capability。

        Returns:
            不返回。

        Raises:
            BaseException: 原样抛出初始化传入的异常。
        """

        self.rollback_tokens.append(batch)
        raise self._error


class _FixedBatchStateRepository:
    """为 shared owner 固定返回同一个 fresh batch state。"""

    def __init__(self, state: FilingUploadPublishedState) -> None:
        """初始化固定 fresh state。

        Args:
            state: batch read 应返回的 typed state。

        Returns:
            无。

        Raises:
            无。
        """

        self._state = state
        self.batch_reads: list[tuple[BatchToken, str]] = []

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """返回固定 published state。

        Args:
            ticker: canonical ticker。
            document_id: exact filing document ID。

        Returns:
            固定 state。

        Raises:
            无。
        """

        del ticker, document_id
        return self._state

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """记录并返回固定 writer-owned fresh state。

        Args:
            batch: shared owner 取得的 batch capability。
            document_id: exact filing document ID。

        Returns:
            固定 state。

        Raises:
            无。
        """

        self.batch_reads.append((batch, document_id))
        return self._state


class _RuntimeFailingBatchStateRepository(_FixedBatchStateRepository):
    """在 batch fresh read 边界抛出 RuntimeError。"""

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """记录调用并模拟 inspector operational failure。

        Args:
            batch: shared owner 取得的 batch capability。
            document_id: exact filing document ID。

        Returns:
            不返回。

        Raises:
            RuntimeError: 始终抛出。
        """

        self.batch_reads.append((batch, document_id))
        raise RuntimeError("private fresh read failure")


class _SecondCheckpointCancellationToken(CancellationToken):
    """只在 shared owner 第二 checkpoint 起稳定取消。"""

    def __init__(self) -> None:
        """初始化零次观察。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.observations = 0

    def is_cancelled(self) -> bool:
        """第二次及后续观察返回真。

        Args:
            无。

        Returns:
            是否已到第二 checkpoint。

        Raises:
            无。
        """

        self.observations += 1
        return self.observations >= 2

    def cancel_reason(self) -> str | None:
        """返回稳定测试取消原因。

        Args:
            无。

        Returns:
            第二次观察后返回原因，否则为空。

        Raises:
            无。
        """

        return "checkpoint-two" if self.observations >= 2 else None

    def requested_at(self) -> datetime | None:
        """不声明墙钟取消时间。

        Args:
            无。

        Returns:
            始终为空。

        Raises:
            无。
        """

        return None


class _EventCancellationToken(CancellationToken):
    """由测试 Event 驱动的稳定取消 token。"""

    def __init__(self, requested: Event) -> None:
        """初始化 Event-backed token。

        Args:
            requested: 取消请求事件。

        Returns:
            无。

        Raises:
            无。
        """

        self._requested = requested

    def is_cancelled(self) -> bool:
        """读取取消事件。

        Args:
            无。

        Returns:
            Event 已设置时返回真。

        Raises:
            无。
        """

        return self._requested.is_set()

    def cancel_reason(self) -> str | None:
        """返回 writer-wait 测试原因。

        Args:
            无。

        Returns:
            已取消时返回原因，否则为空。

        Raises:
            无。
        """

        return "writer-wait" if self._requested.is_set() else None

    def requested_at(self) -> datetime | None:
        """不声明墙钟取消时间。

        Args:
            无。

        Returns:
            始终为空。

        Raises:
            无。
        """

        return None


class _ForbiddenPublicationConverter:
    """第二 checkpoint 测试中禁止被调用的 converter。"""

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """若 lifecycle 错误回到 conversion 则立即失败。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 转换配置。
            cancellation: 取消 token。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del input_bytes, stream_name, config, cancellation
        raise AssertionError("shared publication lifecycle 不得重新执行 conversion")


def _build_publication_identity(
    *,
    primary_original_name: str = "original-main.pdf",
    source_fingerprint: str = _FINGERPRINT_A,
    companion_sha256: str = _ORIGINAL_COMPANION_SHA,
    docling_sha256: str = _DOCLING_SHA,
    docling_content_type: str = "application/json",
) -> FilingUploadPublicationIdentity:
    """构造满足 exact equality contract 的多文件 publication identity。

    Args:
        primary_original_name: 当前 authoritative primary 的 storage name。
        source_fingerprint: publication source fingerprint。
        companion_sha256: companion original 摘要。
        docling_sha256: primary Docling 派生内容摘要。
        docling_content_type: primary Docling 内容类型。

    Returns:
        稳定排序且无路径字段的 publication identity。

    Raises:
        ValueError: primary storage name 不属于 fixture originals 时抛出。
    """

    original_names = ("original-appendix.xlsx", "original-main.pdf")
    if primary_original_name not in original_names:
        raise ValueError("primary fixture 必须命中 original storage name")
    original_assets = (
        FilingUploadAssetDescriptor(
            name="original-appendix.xlsx",
            original_filename="appendix.xlsx",
            derived_from=None,
            sha256=companion_sha256,
            size=13,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            source=FILING_UPLOAD_ASSET_SOURCE_ORIGINAL,
        ),
        FilingUploadAssetDescriptor(
            name="original-main.pdf",
            original_filename="main.pdf",
            derived_from=None,
            sha256=_ORIGINAL_PRIMARY_SHA,
            size=11,
            content_type="application/pdf",
            source=FILING_UPLOAD_ASSET_SOURCE_ORIGINAL,
        ),
    )
    primary_basename = "main.pdf" if primary_original_name.endswith("main.pdf") else "appendix.xlsx"
    docling_name = f"{primary_original_name}_docling.json"
    docling_asset = FilingUploadAssetDescriptor(
        name=docling_name,
        original_filename=primary_basename,
        derived_from=primary_original_name,
        sha256=docling_sha256,
        size=17,
        content_type=docling_content_type,
        source=FILING_UPLOAD_ASSET_SOURCE_DOCLING,
    )
    document_id, internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    return FilingUploadPublicationIdentity(
        ticker="AAPL",
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type="10-K",
        company_id="company-aapl",
        ingest_method="upload",
        fiscal_year=2024,
        fiscal_period="FY",
        report_kind="annual",
        filing_date="2025-01-31",
        report_date="2024-12-31",
        amended=False,
        source_provider="user_upload",
        is_deleted=False,
        document_version="v1",
        source_fingerprint=source_fingerprint,
        primary_document=docling_name,
        primary_original_asset_name=primary_original_name,
        companion_original_asset_names=tuple(sorted(name for name in original_names if name != primary_original_name)),
        assets=tuple(sorted((*original_assets, docling_asset), key=lambda asset: asset.name)),
    )


def _build_prepared_candidate(
    *,
    request: ValidatedFinsUploadFilingRequest,
    identity: FilingUploadPublicationIdentity,
    disposition: FilingInitialSkipDisposition,
) -> _PreparedFilingAssetMutation:
    """从 exact identity 构造不执行 I/O 的 prepared filing candidate。

    Args:
        request: preparation 使用的 initial validated request。
        identity: candidate 应精确描述的 publication identity。
        disposition: preparation owner 已产生的 closed skip disposition。

    Returns:
        能被 production identity helper验证的 typed candidate。

    Raises:
        ValueError: identity asset 的 source 字段不在 closed set 时抛出。
    """

    pending_assets = tuple(
        _PendingFileAsset(
            name=asset.name,
            original_filename=asset.original_filename,
            derived_from=asset.derived_from,
            data=b"prepared-only",
            content_type=asset.content_type,
            sha256=asset.sha256,
            size=asset.size,
            source=asset.source,
        )
        for asset in identity.assets
    )
    return _PreparedFilingAssetMutation(
        ticker=identity.ticker,
        source_kind=SourceKind.FILING,
        action=request.resolved_action,
        document_id=identity.document_id,
        internal_document_id=identity.internal_document_id,
        form_type=identity.form_type,
        overwrite=request.request.overwrite,
        pending_assets=pending_assets,
        conversion_events=(),
        primary_document=identity.primary_document,
        previous_meta=(
            dict(request.published_state.source_meta) if request.published_state.source_meta is not None else None
        ),
        meta={
            "company_id": identity.company_id,
            "ingest_method": identity.ingest_method,
            "fiscal_year": identity.fiscal_year,
            "fiscal_period": identity.fiscal_period,
            "report_kind": identity.report_kind,
            "filing_date": identity.filing_date,
            "report_date": identity.report_date,
            "amended": identity.amended,
            "source_provider": identity.source_provider,
            "is_deleted": identity.is_deleted,
            "document_version": identity.document_version,
            "source_fingerprint": identity.source_fingerprint,
        },
        source_fingerprint=identity.source_fingerprint,
        document_version=identity.document_version,
        repair_disposition=NoExistingSourceRepair(),
        initial_skip_disposition=disposition,
    )


def _execute_publication_test_candidate(
    *,
    workspace_root: Path,
    request: ValidatedFinsUploadFilingRequest,
    fresh_state: FilingUploadPublishedState,
    batching: _PublicationBatchRecorder,
    cancellation: CancellationToken | None = None,
    disposition: FilingInitialSkipDisposition = FilingInitialSkipDisposition.NOT_ELIGIBLE,
) -> tuple[FilingUploadPublicationOutcome, _FixedBatchStateRepository]:
    """装配最小真实仓储依赖并执行一条 prepared publication candidate。

    Args:
        workspace_root: 临时 filesystem workspace。
        request: preparation 使用的 initial validated request。
        fresh_state: batch read 应返回的 fresh durable state。
        batching: 需要观测或注入失败的 batch repository。
        cancellation: 可选 cancellation token。
        disposition: preparation 已产生的初始 skip disposition。

    Returns:
        publication outcome 与记录 fresh read 的 state repository。

    Raises:
        BaseException: shared publication owner 未封闭的异常原样传播。
    """

    identity = _build_publication_identity()
    prepared = _build_prepared_candidate(
        request=request,
        identity=identity,
        disposition=disposition,
    )
    state_repository = _FixedBatchStateRepository(fresh_state)
    repository_set = build_fs_repository_set(
        workspace_root=workspace_root,
        create_directories=False,
    )
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    upload_service = DoclingUploadService(
        source_repository,
        FsDocumentBlobRepository(workspace_root, repository_set=repository_set),
        docling_converter=_ForbiddenPublicationConverter(),
    )
    outcome = execute_prepared_filing_publication(
        request=request,
        prepared=prepared,
        filing_state_repository=state_repository,
        company_repository=FsCompanyMetaRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        batching_repository=batching,
        upload_service=upload_service,
        cancellation=cancellation,
    )
    return outcome, state_repository


def _fresh_company_meta() -> CompanyMeta:
    """构造能令 company resolver 精确返回 keep 的 durable company meta。

    Args:
        无。

    Returns:
        当前 resolver version 下的 AAPL company meta。

    Raises:
        ValueError: ticker identity fixture 非法时抛出。
    """

    return CompanyMeta(
        company_id="company-aapl",
        company_name="Apple Inc.",
        ticker_identity=build_company_ticker_identity("AAPL", ()),
        resolver_version=_RESOLVER_VERSION,
        updated_at="2025-01-01T00:00:00+00:00",
    )


def _build_request(
    file_path: Path,
    *,
    action: str = "auto",
    overwrite: bool = False,
    company_name: str = "Apple Inc.",
    ticker_aliases: tuple[str, ...] = (),
) -> FinsUploadFilingRequest:
    """构造同一 arbitration 前后可重复验证的 filing raw request。

    Args:
        file_path: 已存在的 authoritative primary 文件。
        action: raw upload action。
        overwrite: raw overwrite 开关。
        company_name: 用户显式提交的公司名称。
        ticker_aliases: 用户显式提交的 ticker aliases。

    Returns:
        AAPL FY2024 filing request。

    Raises:
        无。
    """

    return FinsUploadFilingRequest(
        ticker="AAPL",
        action=action,
        files=(file_path,),
        primary_selectors=(file_path,),
        fiscal_year=2024,
        fiscal_period="FY",
        filing_date="2025-01-31",
        report_date="2024-12-31",
        company_name=company_name,
        ticker_aliases=ticker_aliases,
        overwrite=overwrite,
    )


def _build_validated_request(
    request: FinsUploadFilingRequest,
    *,
    status: SourceIntegrityStatus,
    revision: str | None = None,
    publication_identity: FilingUploadPublicationIdentity | None = None,
    company_meta: CompanyMeta | None = None,
) -> ValidatedFinsUploadFilingRequest:
    """按指定 storage observation 运行真实 filing validator。

    Args:
        request: 两次 arbitration 共用的不可变 raw request。
        status: 当前 exact target integrity status。
        revision: COMPLETE/REPAIR_REQUIRED 的 opaque revision。
        publication_identity: COMPLETE user-upload target 的可选 exact identity。
        company_meta: 当前同版 company meta。

    Returns:
        真实 validator 产生的 typed request。

    Raises:
        ValueError: status/revision 或 request/state contract 不一致时抛出。
    """

    document_id, _internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    if status is SourceIntegrityStatus.MISSING:
        source_revision = None
        reasons: tuple[SourceIntegrityReason, ...] = ()
        source_meta = None
    elif status is SourceIntegrityStatus.COMPLETE:
        if revision is None:
            raise ValueError("COMPLETE fixture 必须携带 revision")
        source_revision = SourceDocumentRevision(revision)
        reasons = ()
        source_meta = {"is_deleted": False}
    elif status is SourceIntegrityStatus.REPAIR_REQUIRED:
        if revision is None:
            raise ValueError("REPAIR_REQUIRED fixture 必须携带 revision")
        source_revision = SourceDocumentRevision(revision)
        reasons = (SourceIntegrityReason.ORIGINAL_FILE_MISSING,)
        source_meta = {"is_deleted": False}
    else:
        raise ValueError("pure arbitration fixture 不构造 UNSAFE validated request")
    state = FilingUploadPublishedState(
        company_meta=company_meta,
        source_integrity=SourceIntegrityClassification(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_id=document_id,
            revision=source_revision,
            status=status,
            reasons=reasons,
        ),
        source_meta=source_meta,
        publication_identity=(publication_identity if status is SourceIntegrityStatus.COMPLETE else None),
    )
    return validate_fins_upload_filing_request(request, published_state=state)


def test_publication_identity_is_exact_sorted_path_free_business_fact() -> None:
    """identity 必须跟踪角色/全部资产事实并拒绝路径语义。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: exact equality、排序、角色或无路径 contract 漂移时抛出。
    """

    identity = _build_publication_identity()
    primary_flipped = _build_publication_identity(primary_original_name="original-appendix.xlsx")
    companion_changed = _build_publication_identity(companion_sha256="f" * 64)
    derived_bytes_changed = _build_publication_identity(docling_sha256="1" * 64)
    derived_content_type_changed = _build_publication_identity(docling_content_type="application/octet-stream")

    assert tuple(asset.name for asset in identity.assets) == tuple(sorted(asset.name for asset in identity.assets))
    assert identity.companion_original_asset_names == ("original-appendix.xlsx",)
    assert identity.primary_original_asset_name == "original-main.pdf"
    assert all(asset.source in {"original", "docling"} for asset in identity.assets)
    assert identity != primary_flipped
    assert identity != companion_changed
    assert identity != derived_bytes_changed
    assert identity != derived_content_type_changed
    assert "/private/" not in repr(identity)
    assert not {"path", "uri", "etag", "last_modified", "revision"}.intersection(
        field.name for field in fields(identity)
    )
    with pytest.raises(ValueError, match="无路径 basename"):
        replace(identity.assets[0], name="/private/report.pdf")


def test_publication_identity_rejects_non_string_business_text() -> None:
    """identity owner 必须在运行时拒绝 required text 与 content type 的错误类型。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非字符串业务文本被 closed contract 接受时抛出。
    """

    identity = _build_publication_identity()
    with pytest.raises(TypeError, match="fiscal_period 必须是字符串"):
        replace(identity, fiscal_period=2024)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="name 与 original_filename 必须是字符串"):
        replace(identity.assets[0], name=7)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="content_type 必须是字符串或 None"):
        replace(identity.assets[0], content_type=5)  # type: ignore[arg-type]


def test_arbitration_closed_table_for_stable_and_changed_observations(
    tmp_path: Path,
) -> None:
    """pure owner 必须覆盖 stable、convergence、rebase 与 conflict 封闭分支。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 frozen arbitration 决策或 typed reason 漂移时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()

    auto_request = _build_request(primary)
    missing_initial = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.MISSING,
    )
    missing_fresh = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.MISSING,
    )
    stable_missing = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=missing_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert stable_missing.disposition is FilingUploadPublicationDisposition.PUBLISH
    assert stable_missing.publish_mode is FilingUploadPublishMode.PREPARED

    complete_winner = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=durable_company,
    )
    converged = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=complete_winner,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert converged.disposition is FilingUploadPublicationDisposition.SKIP

    company_not_durable = _build_validated_request(
        auto_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=None,
    )
    company_conflict = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=company_not_durable,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert company_conflict.failure_reason is not None
    assert company_conflict.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT

    identity_conflict = arbitrate_filing_upload_publication(
        initial_request=missing_initial,
        fresh_request=complete_winner,
        prepared_identity=_build_publication_identity(source_fingerprint=_FINGERPRINT_B),
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert identity_conflict.failure_reason is not None
    assert identity_conflict.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT

    overwrite_request = _build_request(primary, action="create", overwrite=True)
    overwrite_initial = _build_validated_request(
        overwrite_request,
        status=SourceIntegrityStatus.MISSING,
    )
    overwrite_fresh = _build_validated_request(
        overwrite_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=durable_company,
    )
    rebased = arbitrate_filing_upload_publication(
        initial_request=overwrite_initial,
        fresh_request=overwrite_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert rebased.disposition is FilingUploadPublicationDisposition.PUBLISH
    assert rebased.publish_mode is FilingUploadPublishMode.REBASE_CREATE_OVERWRITE


def test_arbitration_preserves_retransmission_and_repair_ownership(
    tmp_path: Path,
) -> None:
    """stable retransmission 与 repair revision 漂移必须由各自 typed owner 裁决。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: stable skip/publish 或 repair stale code 漂移时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()
    update_request = _build_request(primary, action="update")
    complete_initial = _build_validated_request(
        update_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="stable",
        publication_identity=identity,
        company_meta=durable_company,
    )
    complete_fresh = _build_validated_request(
        update_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="stable",
        publication_identity=identity,
        company_meta=durable_company,
    )
    retransmission = arbitrate_filing_upload_publication(
        initial_request=complete_initial,
        fresh_request=complete_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.IDENTICAL_PUBLICATION,
    )
    assert retransmission.disposition is FilingUploadPublicationDisposition.SKIP

    ordinary_stable_update = arbitrate_filing_upload_publication(
        initial_request=complete_initial,
        fresh_request=complete_fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert ordinary_stable_update.disposition is FilingUploadPublicationDisposition.PUBLISH
    assert ordinary_stable_update.publish_mode is FilingUploadPublishMode.PREPARED

    complete_changed = _build_validated_request(
        update_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="changed",
        publication_identity=identity,
        company_meta=durable_company,
    )
    changed_complete = arbitrate_filing_upload_publication(
        initial_request=complete_initial,
        fresh_request=complete_changed,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.IDENTICAL_PUBLICATION,
    )
    assert changed_complete.failure_reason is not None
    assert changed_complete.failure_reason.code is FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT

    repair_request = _build_request(primary)
    repair_initial = _build_validated_request(
        repair_request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="repair-a",
        company_meta=durable_company,
    )
    repair_stable = _build_validated_request(
        repair_request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="repair-a",
        company_meta=durable_company,
    )
    stable_repair = arbitrate_filing_upload_publication(
        initial_request=repair_initial,
        fresh_request=repair_stable,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert stable_repair.disposition is FilingUploadPublicationDisposition.PUBLISH

    repair_changed = _build_validated_request(
        repair_request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="repair-b",
        company_meta=durable_company,
    )
    stale_repair = arbitrate_filing_upload_publication(
        initial_request=repair_initial,
        fresh_request=repair_changed,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    assert stale_repair.failure_reason is not None
    assert stale_repair.failure_reason.code is FinsUploadFailureCode.SOURCE_REVISION_STALE


@pytest.mark.parametrize(
    (
        "initial_status",
        "fresh_status",
        "action",
        "overwrite",
        "manual_explicit_create_fresh",
        "expected_failure_code",
    ),
    (
        (
            SourceIntegrityStatus.MISSING,
            SourceIntegrityStatus.REPAIR_REQUIRED,
            "auto",
            False,
            False,
            FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT,
        ),
        (
            SourceIntegrityStatus.COMPLETE,
            SourceIntegrityStatus.MISSING,
            "auto",
            False,
            False,
            FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT,
        ),
        (
            SourceIntegrityStatus.COMPLETE,
            SourceIntegrityStatus.REPAIR_REQUIRED,
            "auto",
            False,
            False,
            FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT,
        ),
        (
            SourceIntegrityStatus.MISSING,
            SourceIntegrityStatus.COMPLETE,
            "auto",
            True,
            False,
            FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT,
        ),
        (
            SourceIntegrityStatus.MISSING,
            SourceIntegrityStatus.COMPLETE,
            "create",
            False,
            True,
            FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT,
        ),
        (
            SourceIntegrityStatus.REPAIR_REQUIRED,
            SourceIntegrityStatus.MISSING,
            "auto",
            False,
            False,
            FinsUploadFailureCode.SOURCE_REVISION_STALE,
        ),
        (
            SourceIntegrityStatus.REPAIR_REQUIRED,
            SourceIntegrityStatus.COMPLETE,
            "auto",
            False,
            False,
            FinsUploadFailureCode.SOURCE_REVISION_STALE,
        ),
    ),
)
def test_arbitration_conflict_grid_is_closed_and_typed(
    tmp_path: Path,
    initial_status: SourceIntegrityStatus,
    fresh_status: SourceIntegrityStatus,
    action: str,
    overwrite: bool,
    manual_explicit_create_fresh: bool,
    expected_failure_code: FinsUploadFailureCode,
) -> None:
    """§7.4 changed-observation conflict 格必须统一 fail closed 且绝不 skip。

    Args:
        tmp_path: authoritative primary fixture 目录。
        initial_status: preparation observation 状态。
        fresh_status: batch staging fresh observation 状态。
        action: raw upload action。
        overwrite: raw overwrite 开关。
        manual_explicit_create_fresh: 是否直接构造 validator 不会产生的 fresh create 观察。
        expected_failure_code: 当前 closed conflict 格的精确 failure code。

    Returns:
        无。

    Raises:
        AssertionError: conflict 格产生 publish/skip 或错误 failure code 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary, action=action, overwrite=overwrite)
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()
    initial = _build_validated_request(
        request,
        status=initial_status,
        revision=("initial" if initial_status is not SourceIntegrityStatus.MISSING else None),
        publication_identity=(identity if initial_status is SourceIntegrityStatus.COMPLETE else None),
        company_meta=(durable_company if initial_status is not SourceIntegrityStatus.MISSING else None),
    )
    if manual_explicit_create_fresh:
        donor_request = _build_request(primary, action="update")
        donor = _build_validated_request(
            donor_request,
            status=SourceIntegrityStatus.COMPLETE,
            revision="fresh",
            publication_identity=identity,
            company_meta=durable_company,
        )
        fresh = replace(
            initial,
            published_state=donor.published_state,
            company_meta_decision=donor.company_meta_decision,
        )
    else:
        fresh = _build_validated_request(
            request,
            status=fresh_status,
            revision=("fresh" if fresh_status is not SourceIntegrityStatus.MISSING else None),
            publication_identity=(identity if fresh_status is SourceIntegrityStatus.COMPLETE else None),
            company_meta=(durable_company if fresh_status is not SourceIntegrityStatus.MISSING else None),
        )

    decision = arbitrate_filing_upload_publication(
        initial_request=initial,
        fresh_request=fresh,
        prepared_identity=identity,
        initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )

    assert decision.disposition is FilingUploadPublicationDisposition.CONFLICT
    assert decision.disposition is not FilingUploadPublicationDisposition.SKIP
    assert decision.publish_mode is None
    assert decision.failure_reason is not None
    assert decision.failure_reason.code is expected_failure_code


@pytest.mark.parametrize("unsafe_side", ("initial", "fresh"))
def test_arbitration_rejects_unsafe_observation_at_either_entry(
    tmp_path: Path,
    unsafe_side: str,
) -> None:
    """UNSAFE initial/fresh observation 即使由 adversarial caller 伪造也必须 raise。

    Args:
        tmp_path: authoritative primary fixture 目录。
        unsafe_side: 需要伪造为 UNSAFE 的输入侧。

    Returns:
        无。

    Raises:
        AssertionError: UNSAFE 被转换为普通 decision 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary)
    initial = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    fresh = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    unsafe_state = FilingUploadPublishedState(
        company_meta=None,
        source_integrity=SourceIntegrityClassification(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            document_id=initial.document_id,
            revision=None,
            status=SourceIntegrityStatus.UNSAFE,
            reasons=(SourceIntegrityReason.IDENTITY_UNTRUSTED,),
        ),
        source_meta=None,
        publication_identity=None,
    )
    # Validated request 自身拒绝 UNSAFE；这里刻意越过 frozen dataclass，测试纯 owner 的防线。
    object.__setattr__(
        initial if unsafe_side == "initial" else fresh,
        "published_state",
        unsafe_state,
    )

    with pytest.raises(ValueError, match="UNSAFE source observation"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=_build_publication_identity(),
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )


def test_arbitration_rejects_stable_repair_action_invariant_drift(tmp_path: Path) -> None:
    """stable REPAIR_REQUIRED 必须分别检查 initial/fresh 的 update action。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: 两侧同样漂移的 action 绕过 stable owner invariant 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary)
    initial = _build_validated_request(
        request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="stable",
        company_meta=_fresh_company_meta(),
    )
    fresh = _build_validated_request(
        request,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        revision="stable",
        company_meta=_fresh_company_meta(),
    )
    # 伪造两侧相等但非法的 action，确保测试命中 REPAIR_REQUIRED 分支自身的 fresh 检查。
    object.__setattr__(initial, "resolved_action", "create")
    object.__setattr__(fresh, "resolved_action", "create")

    with pytest.raises(ValueError, match="stable REPAIR_REQUIRED observation"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=_build_publication_identity(),
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )


def test_arbitration_rejects_target_and_closed_input_contract_drift(tmp_path: Path) -> None:
    """pure owner 必须拒绝不同 raw request、target identity 与 open disposition。

    Args:
        tmp_path: authoritative primary fixture 目录。

    Returns:
        无。

    Raises:
        AssertionError: invariant drift 被静默降级为 publish/skip/conflict 时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    request = _build_request(primary)
    initial = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    fresh = _build_validated_request(request, status=SourceIntegrityStatus.MISSING)
    identity = _build_publication_identity()

    with pytest.raises(TypeError, match="FilingInitialSkipDisposition"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=identity,
            initial_skip_disposition="not_eligible",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="prepared target identity"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=fresh,
            prepared_identity=replace(identity, internal_document_id="foreign-internal"),
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )
    different_request = _build_request(primary, overwrite=True)
    different_fresh = _build_validated_request(
        different_request,
        status=SourceIntegrityStatus.MISSING,
    )
    with pytest.raises(ValueError, match="同一不可变 raw request"):
        arbitrate_filing_upload_publication(
            initial_request=initial,
            fresh_request=different_fresh,
            prepared_identity=identity,
            initial_skip_disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
        )


@pytest.mark.parametrize("candidate_branch", ["publish", "skip", "conflict"])
def test_second_checkpoint_cancels_closed_candidate_before_any_publication_mutation(
    tmp_path: Path,
    candidate_branch: str,
) -> None:
    """第二 checkpoint 必须统一覆盖 PUBLISH/SKIP/CONFLICT 三类已裁决候选。

    Args:
        tmp_path: 构造未使用真实仓储 composition 的临时根。
        candidate_branch: 第二 checkpoint 前已经形成的 closed candidate 类别。

    Returns:
        无。

    Raises:
        AssertionError: fresh read、rollback、取消终态或 mutation boundary 漂移时抛出。
        ValueError: 参数不是 closed 测试分支时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()
    if candidate_branch == "publish":
        raw_request = _build_request(primary)
        initial = _build_validated_request(
            raw_request,
            status=SourceIntegrityStatus.MISSING,
        )
        fresh_state = initial.published_state
        disposition = FilingInitialSkipDisposition.NOT_ELIGIBLE
    elif candidate_branch == "skip":
        raw_request = _build_request(primary, action="update")
        initial = _build_validated_request(
            raw_request,
            status=SourceIntegrityStatus.COMPLETE,
            revision="stable",
            publication_identity=identity,
            company_meta=durable_company,
        )
        fresh_state = initial.published_state
        disposition = FilingInitialSkipDisposition.IDENTICAL_PUBLICATION
    elif candidate_branch == "conflict":
        raw_request = _build_request(primary, action="create")
        initial = _build_validated_request(
            raw_request,
            status=SourceIntegrityStatus.MISSING,
        )
        fresh_state = _build_validated_request(
            _build_request(primary),
            status=SourceIntegrityStatus.COMPLETE,
            revision="winner",
            publication_identity=identity,
            company_meta=durable_company,
        ).published_state
        disposition = FilingInitialSkipDisposition.NOT_ELIGIBLE
    else:
        raise ValueError("candidate_branch 必须是 publish/skip/conflict")
    prepared = _build_prepared_candidate(
        request=initial,
        identity=identity,
        disposition=disposition,
    )
    batching = _PublicationBatchRecorder()
    state_repository = _FixedBatchStateRepository(fresh_state)
    repository_set = build_fs_repository_set(
        workspace_root=tmp_path,
        create_directories=False,
    )
    company_repository = FsCompanyMetaRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    upload_service = DoclingUploadService(
        source_repository,
        blob_repository,
        docling_converter=_ForbiddenPublicationConverter(),
    )
    cancellation = _SecondCheckpointCancellationToken()

    outcome = execute_prepared_filing_publication(
        request=initial,
        prepared=prepared,
        filing_state_repository=state_repository,
        company_repository=company_repository,
        batching_repository=batching,
        upload_service=upload_service,
        cancellation=cancellation,
    )

    assert outcome.result.status == "cancelled"
    assert outcome.result.stored_file_count == 0
    assert cancellation.observations == 2
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert state_repository.batch_reads == [(batching.begin_tokens[0], initial.document_id)]
    assert outcome.authoritative_request is initial


def test_second_checkpoint_changed_observation_keeps_initial_request_projection(
    tmp_path: Path,
) -> None:
    """第二 checkpoint 取消不得把 auto 请求按 fresh COMPLETE 偶然投影成 update。

    Args:
        tmp_path: 构造最小 publication composition 的临时根。

    Returns:
        无。

    Raises:
        AssertionError: changed observation 改写取消终态 action 或 batch lifecycle 时抛出。
    """

    primary = tmp_path / "changed-cancel.pdf"
    primary.write_bytes(b"changed cancellation")
    raw_request = _build_request(primary)
    initial = _build_validated_request(
        raw_request,
        status=SourceIntegrityStatus.MISSING,
    )
    fresh = _build_validated_request(
        raw_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=_build_publication_identity(),
        company_meta=_fresh_company_meta(),
    )
    batching = _PublicationBatchRecorder()

    outcome, state_repository = _execute_publication_test_candidate(
        workspace_root=tmp_path,
        request=initial,
        fresh_state=fresh.published_state,
        batching=batching,
        cancellation=_SecondCheckpointCancellationToken(),
    )

    assert initial.resolved_action == "create"
    assert fresh.resolved_action == "update"
    assert outcome.result.status == "cancelled"
    assert outcome.authoritative_request is initial
    assert outcome.authoritative_request.resolved_action == "create"
    assert state_repository.batch_reads == [(batching.begin_tokens[0], initial.document_id)]
    assert batching.rollback_tokens == batching.begin_tokens


@pytest.mark.parametrize("signal_type", (KeyboardInterrupt, SystemExit))
def test_cancel_rollback_signal_exception_propagates_unchanged(
    tmp_path: Path,
    signal_type: type[BaseException],
) -> None:
    """cancel rollback 只映射仓储普通异常，进程信号必须原样传播。

    Args:
        tmp_path: 构造最小 publication composition 的临时根。
        signal_type: rollback 应原样抛出的信号异常类型。

    Returns:
        无。

    Raises:
        AssertionError: 信号被 STORAGE_IO 重写或 rollback 未发生时抛出。
    """

    primary = tmp_path / "rollback-signal.pdf"
    primary.write_bytes(b"rollback signal")
    initial = _build_validated_request(
        _build_request(primary),
        status=SourceIntegrityStatus.MISSING,
    )
    batching = _RollbackFailureBatchRecorder(signal_type("rollback signal"))
    requested = Event()
    requested.set()

    with pytest.raises(signal_type, match="rollback signal"):
        _execute_publication_test_candidate(
            workspace_root=tmp_path,
            request=initial,
            fresh_state=initial.published_state,
            batching=batching,
            cancellation=_EventCancellationToken(requested),
        )

    assert batching.rollback_tokens == batching.begin_tokens


def test_batch_acquire_runtime_error_maps_to_typed_storage_io(tmp_path: Path) -> None:
    """batch reservation RuntimeError 必须由 acquire owner 映射为 typed STORAGE_IO。

    Args:
        tmp_path: 构造最小 publication composition 的临时根。

    Returns:
        无。

    Raises:
        AssertionError: acquire failure 分类或 lifecycle 漂移时抛出。
    """

    primary = tmp_path / "acquire-runtime.pdf"
    primary.write_bytes(b"acquire runtime")
    initial = _build_validated_request(
        _build_request(primary),
        status=SourceIntegrityStatus.MISSING,
    )
    batching = _FailingBeginBatchRecorder()

    with pytest.raises(FinsUploadFailureError) as raised:
        _execute_publication_test_candidate(
            workspace_root=tmp_path,
            request=initial,
            fresh_state=initial.published_state,
            batching=batching,
        )

    assert raised.value.failure == fins_upload_prevalidation_io_failure()
    assert batching.begin_tokens == []
    assert batching.rollback_tokens == []


def test_batch_fresh_read_runtime_error_maps_to_typed_storage_io(tmp_path: Path) -> None:
    """batch inspector RuntimeError 必须映射为 typed STORAGE_IO 并 rollback。

    Args:
        tmp_path: 构造最小 publication composition 的临时根。

    Returns:
        无。

    Raises:
        AssertionError: fresh read failure 分类或 rollback 漂移时抛出。
    """

    primary = tmp_path / "read-runtime.pdf"
    primary.write_bytes(b"read runtime")
    initial = _build_validated_request(
        _build_request(primary),
        status=SourceIntegrityStatus.MISSING,
    )
    batching = _PublicationBatchRecorder()
    state_repository = _RuntimeFailingBatchStateRepository(initial.published_state)
    repository_set = build_fs_repository_set(
        workspace_root=tmp_path,
        create_directories=False,
    )
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)

    with pytest.raises(FinsUploadFailureError) as raised:
        execute_prepared_filing_publication(
            request=initial,
            prepared=_build_prepared_candidate(
                request=initial,
                identity=_build_publication_identity(),
                disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
            ),
            filing_state_repository=state_repository,
            company_repository=FsCompanyMetaRepository(
                tmp_path,
                repository_set=repository_set,
            ),
            batching_repository=batching,
            upload_service=DoclingUploadService(
                source_repository,
                FsDocumentBlobRepository(tmp_path, repository_set=repository_set),
                docling_converter=_ForbiddenPublicationConverter(),
            ),
            cancellation=None,
        )

    assert raised.value.failure == fins_upload_prevalidation_io_failure()
    assert state_repository.batch_reads == [(batching.begin_tokens[0], initial.document_id)]
    assert batching.rollback_tokens == batching.begin_tokens


def test_fresh_validator_value_error_maps_to_typed_corruption(tmp_path: Path) -> None:
    """fresh validator 的 producer invariant ValueError 必须映射为 typed corruption。

    Args:
        tmp_path: 构造最小 publication composition 的临时根。

    Returns:
        无。

    Raises:
        AssertionError: validator failure 分类或 rollback 漂移时抛出。
    """

    primary = tmp_path / "fresh-corruption.pdf"
    primary.write_bytes(b"fresh corruption")
    initial = _build_validated_request(
        _build_request(primary),
        status=SourceIntegrityStatus.MISSING,
    )
    corrupt_state = replace(
        initial.published_state,
        source_integrity=replace(
            initial.published_state.source_integrity,
            ticker="MSFT",
        ),
    )
    batching = _PublicationBatchRecorder()

    with pytest.raises(FinsUploadFailureError) as raised:
        _execute_publication_test_candidate(
            workspace_root=tmp_path,
            request=initial,
            fresh_state=corrupt_state,
            batching=batching,
        )

    assert raised.value.failure == fins_upload_prevalidation_corruption_failure()
    assert batching.rollback_tokens == batching.begin_tokens


@pytest.mark.parametrize("candidate_branch", ["publish", "skip", "conflict"])
def test_writer_wait_cancellation_stops_before_fresh_read_for_all_candidate_classes(
    tmp_path: Path,
    candidate_branch: str,
) -> None:
    """等待同 ticker writer 时取消的三类候选均在 checkpoint1 原子终结。

    Args:
        tmp_path: 构造未使用真实仓储 composition 的临时根。
        candidate_branch: 原本会进入 publish、skip 或 conflict 的候选类别。

    Returns:
        无。

    Raises:
        AssertionError: 等待、fresh read、rollback 或取消终态漂移时抛出。
        ValueError: 参数不是 closed 测试分支时抛出。
    """

    primary = tmp_path / "main.pdf"
    primary.write_bytes(b"filing")
    identity = _build_publication_identity()
    durable_company = _fresh_company_meta()
    if candidate_branch == "publish":
        initial = _build_validated_request(
            _build_request(primary),
            status=SourceIntegrityStatus.MISSING,
        )
        fresh_state = initial.published_state
        disposition = FilingInitialSkipDisposition.NOT_ELIGIBLE
    elif candidate_branch == "skip":
        initial = _build_validated_request(
            _build_request(primary, action="update"),
            status=SourceIntegrityStatus.COMPLETE,
            revision="stable",
            publication_identity=identity,
            company_meta=durable_company,
        )
        fresh_state = initial.published_state
        disposition = FilingInitialSkipDisposition.IDENTICAL_PUBLICATION
    elif candidate_branch == "conflict":
        initial = _build_validated_request(
            _build_request(primary, action="create"),
            status=SourceIntegrityStatus.MISSING,
        )
        fresh_state = _build_validated_request(
            _build_request(primary),
            status=SourceIntegrityStatus.COMPLETE,
            revision="winner",
            publication_identity=identity,
            company_meta=durable_company,
        ).published_state
        disposition = FilingInitialSkipDisposition.NOT_ELIGIBLE
    else:
        raise ValueError("candidate_branch 必须是 publish/skip/conflict")
    prepared = _build_prepared_candidate(
        request=initial,
        identity=identity,
        disposition=disposition,
    )
    entered = Event()
    release = Event()
    requested = Event()
    batching = _WaitingPublicationBatchRecorder(entered, release)
    state_repository = _FixedBatchStateRepository(fresh_state)
    repository_set = build_fs_repository_set(
        workspace_root=tmp_path,
        create_directories=False,
    )
    company_repository = FsCompanyMetaRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    upload_service = DoclingUploadService(
        source_repository,
        FsDocumentBlobRepository(tmp_path, repository_set=repository_set),
        docling_converter=_ForbiddenPublicationConverter(),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            execute_prepared_filing_publication,
            request=initial,
            prepared=prepared,
            filing_state_repository=state_repository,
            company_repository=company_repository,
            batching_repository=batching,
            upload_service=upload_service,
            cancellation=_EventCancellationToken(requested),
        )
        assert entered.wait(timeout=10)
        requested.set()
        release.set()
        outcome = future.result(timeout=10)

    assert outcome.result.status == "cancelled"
    assert outcome.result.stored_file_count == 0
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert state_repository.batch_reads == []


def _execute_metadata_only_skip_fixture(
    *,
    workspace_root: Path,
    requested_company_name: str,
    ticker_aliases: tuple[str, ...],
    batching: _PublicationBatchRecorder,
    company_repository: _MetadataStageRecorder,
) -> FilingUploadPublicationOutcome:
    """执行一条 fresh preserve intent 的 canonical metadata-only skip。

    Args:
        workspace_root: 临时 filesystem 根。
        requested_company_name: fresh request 显式公司名称。
        ticker_aliases: fresh request 显式 alias。
        batching: terminal-aware metadata commit recorder。
        company_repository: company intent stage recorder。

    Returns:
        shared publication owner 的 typed outcome。

    Raises:
        BaseException: stage、commit 或 shared owner invariant 失败时原样传播。
    """

    primary = workspace_root / "metadata-skip.pdf"
    primary.write_bytes(b"metadata-only skip")
    raw_request = _build_request(
        primary,
        company_name=requested_company_name,
        ticker_aliases=ticker_aliases,
    )
    initial = _build_validated_request(
        raw_request,
        status=SourceIntegrityStatus.MISSING,
    )
    identity = _build_publication_identity()
    fresh = _build_validated_request(
        raw_request,
        status=SourceIntegrityStatus.COMPLETE,
        revision="winner",
        publication_identity=identity,
        company_meta=_fresh_company_meta(),
    )
    assert fresh.company_meta_decision.disposition == "stage"
    assert fresh.company_meta_decision.company_meta_intent is not None
    assert fresh.company_meta_decision.company_meta_intent.merge_mode == "preserve_published"
    prepared = _build_prepared_candidate(
        request=initial,
        identity=identity,
        disposition=FilingInitialSkipDisposition.NOT_ELIGIBLE,
    )
    repository_set = build_fs_repository_set(
        workspace_root=workspace_root,
        create_directories=False,
    )
    upload_service = DoclingUploadService(
        FsSourceDocumentRepository(workspace_root, repository_set=repository_set),
        FsDocumentBlobRepository(workspace_root, repository_set=repository_set),
        docling_converter=_ForbiddenPublicationConverter(),
    )
    return execute_prepared_filing_publication(
        request=initial,
        prepared=prepared,
        filing_state_repository=_FixedBatchStateRepository(fresh.published_state),
        company_repository=company_repository,
        batching_repository=batching,
        upload_service=upload_service,
        cancellation=None,
    )


def test_publication_outcome_rejects_cancelled_warning(tmp_path: Path) -> None:
    """cancelled publication outcome 必须在 owner boundary 拒绝非空 warning。

    Args:
        tmp_path: 构造 validated request 的临时文件根。

    Returns:
        无。

    Raises:
        AssertionError: cancelled outcome 接受 warning 时抛出。
    """

    primary = tmp_path / "cancelled-warning.pdf"
    primary.write_bytes(b"cancelled warning")
    request = _build_validated_request(
        _build_request(primary),
        status=SourceIntegrityStatus.MISSING,
    )
    result = UploadOperationResult(
        status="cancelled",
        document_id=request.document_id,
        internal_document_id=request.internal_document_id,
        stored_file_count=0,
        file_events=[],
        payload={"skip_reason": "cancelled"},
    )
    warning = CompanyMetadataWarning(
        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    )

    with pytest.raises(ValueError, match="cancelled publication outcome"):
        FilingUploadPublicationOutcome(
            authoritative_request=request,
            result=result,
            warnings=(warning,),
        )


def test_publication_outcome_rejects_warning_commit_outcome_mismatch(
    tmp_path: Path,
) -> None:
    """publication warnings 必须与内部 commit outcome 的 exact 投影一致。

    Args:
        tmp_path: 构造 validated request 的临时文件根。

    Returns:
        无。

    Raises:
        AssertionError: outcome 接受不同源 warnings 时抛出。
    """

    primary = tmp_path / "warning-mismatch.pdf"
    primary.write_bytes(b"warning mismatch")
    request = _build_validated_request(
        _build_request(primary),
        status=SourceIntegrityStatus.MISSING,
    )
    commit_outcome = CompanyMetaCommitOutcome(
        company_meta=_fresh_company_meta(),
        ignored_company_name=CompanyNameIgnoredChange(
            requested_company_name="Apple Holdings",
            published_company_name="Apple Inc.",
        ),
    )
    result = UploadOperationResult(
        status="skipped",
        document_id=request.document_id,
        internal_document_id=request.internal_document_id,
        stored_file_count=0,
        file_events=[],
        payload={"skip_reason": "already_uploaded"},
        company_meta_commit_outcome=commit_outcome,
    )

    with pytest.raises(ValueError, match="必须与内部 commit outcome 同源"):
        FilingUploadPublicationOutcome(
            authoritative_request=request,
            result=result,
            warnings=(),
        )


@pytest.mark.parametrize(
    ("kind", "message", "expected_error"),
    (
        (
            cast(CompanyMetadataWarningKind, "company_name_ignored"),
            COMPANY_NAME_IGNORED_WARNING_MESSAGE,
            TypeError,
        ),
        (
            CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
            "非规范文案",
            ValueError,
        ),
    ),
)
def test_company_metadata_warning_rejects_noncanonical_constructor_values(
    kind: CompanyMetadataWarningKind,
    message: str,
    expected_error: type[Exception],
) -> None:
    """typed warning constructor 必须拒绝非精确 kind 与非规范文案。

    Args:
        kind: 待验证的 runtime kind。
        message: 待验证的 warning 文案。
        expected_error: owner contract 应抛出的异常类型。

    Returns:
        无。

    Raises:
        AssertionError: constructor 接受非法 closed value 时抛出。
    """

    with pytest.raises(expected_error):
        CompanyMetadataWarning(kind=kind, message=message)


@pytest.mark.parametrize(
    ("warnings", "expected_error"),
    (
        (
            (
                CompanyMetadataWarning(
                    kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
                    message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
                ),
                CompanyMetadataWarning(
                    kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
                    message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
                ),
            ),
            ValueError,
        ),
        ((cast(CompanyMetadataWarning, "invalid warning"),), TypeError),
    ),
)
def test_company_metadata_warning_json_projection_rejects_invalid_collections(
    warnings: tuple[CompanyMetadataWarning, ...],
    expected_error: type[Exception],
) -> None:
    """warning JSON projection 必须拒绝超限 collection 与非精确元素。

    Args:
        warnings: 待序列化的 runtime warning collection。
        expected_error: owner contract 应抛出的异常类型。

    Returns:
        无。

    Raises:
        AssertionError: serializer 接受非法 collection 时抛出。
    """

    with pytest.raises(expected_error):
        company_metadata_warnings_to_json(warnings)


@pytest.mark.parametrize(
    "ignored_change",
    (cast(CompanyNameIgnoredChange, {"requested": "Apple Holdings"}),),
)
def test_company_name_ignored_warning_projection_rejects_nonexact_domain_fact(
    ignored_change: CompanyNameIgnoredChange,
) -> None:
    """公开 warning projection 必须拒绝非精确 domain fact。

    Args:
        ignored_change: 待投影的 runtime domain fact。

    Returns:
        无。

    Raises:
        AssertionError: projection 接受非精确 owner fact 时抛出。
    """

    with pytest.raises(TypeError, match="CompanyNameIgnoredChange"):
        project_company_name_ignored_warning(ignored_change)


@pytest.mark.parametrize(
    ("requested_company_name", "aliases", "ignored_change", "expected_warning"),
    (
        (
            "Apple Holdings",
            (),
            CompanyNameIgnoredChange(
                requested_company_name="Apple Holdings",
                published_company_name="Apple Inc.",
            ),
            (
                CompanyMetadataWarning(
                    kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
                    message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
                ),
            ),
        ),
        (" apple inc. ", ("APPL",), None, ()),
    ),
)
def test_metadata_only_skip_transfers_capability_and_projects_exact_outcome(
    tmp_path: Path,
    requested_company_name: str,
    aliases: tuple[str, ...],
    ignored_change: CompanyNameIgnoredChange | None,
    expected_warning: tuple[CompanyMetadataWarning, ...],
) -> None:
    """name-only 与 alias-only skip 均应 stage→commit，且只投影 final fact。

    Args:
        tmp_path: 临时 filesystem 根。
        requested_company_name: 当前 fresh request 名称。
        aliases: 当前 fresh request aliases。
        ignored_change: storage final outcome 携带的名称未采用事实。
        expected_warning: shared owner 应返回的规范 warning tuple。

    Returns:
        无。

    Raises:
        AssertionError: capability、outcome 或 warning 同源 contract 漂移时抛出。
    """

    final_meta = replace(
        _fresh_company_meta(),
        ticker_identity=build_company_ticker_identity("AAPL", aliases),
    )
    commit_outcome = CompanyMetaCommitOutcome(
        company_meta=final_meta,
        ignored_company_name=ignored_change,
    )
    events: list[str] = []
    batching = _PublicationBatchRecorder(
        commit_outcome=commit_outcome,
        events=events,
        forbid_rollback_after_commit=True,
    )
    company = _MetadataStageRecorder(events=events)

    outcome = _execute_metadata_only_skip_fixture(
        workspace_root=tmp_path,
        requested_company_name=requested_company_name,
        ticker_aliases=aliases,
        batching=batching,
        company_repository=company,
    )

    assert events == ["stage", "commit"]
    assert batching.commit_tokens == batching.begin_tokens
    assert batching.rollback_tokens == []
    assert company.stage_tokens == batching.begin_tokens
    assert outcome.result.status == "skipped"
    assert outcome.result.company_meta_commit_outcome is commit_outcome
    assert outcome.warnings == expected_warning


def test_metadata_only_skip_commit_failure_never_rolls_back_consumed_capability(
    tmp_path: Path,
) -> None:
    """metadata commit 消费 capability 后失败时不得由 outer finally 二次 rollback。

    Args:
        tmp_path: 临时 filesystem 根。

    Returns:
        无。

    Raises:
        AssertionError: 主异常、顺序或 rollback count 漂移时抛出。
    """

    events: list[str] = []
    batching = _PublicationBatchRecorder(
        commit_outcome=CompanyMetaCommitOutcome(
            company_meta=_fresh_company_meta(),
            ignored_company_name=None,
        ),
        commit_error=OSError("metadata commit failed"),
        events=events,
        forbid_rollback_after_commit=True,
    )
    company = _MetadataStageRecorder(events=events)

    with pytest.raises(OSError, match="metadata commit failed"):
        _execute_metadata_only_skip_fixture(
            workspace_root=tmp_path,
            requested_company_name="Apple Holdings",
            ticker_aliases=(),
            batching=batching,
            company_repository=company,
        )

    assert events == ["stage", "commit"]
    assert batching.commit_tokens == batching.begin_tokens
    assert batching.rollback_tokens == []


def test_metadata_only_skip_stage_failure_rolls_back_once_before_capability_transfer(
    tmp_path: Path,
) -> None:
    """metadata stage 在 capability transfer 前失败时 caller 必须恰好回滚一次。

    Args:
        tmp_path: 临时 filesystem 根。

    Returns:
        无。

    Raises:
        AssertionError: stage failure、commit 或 rollback boundary 漂移时抛出。
    """

    events: list[str] = []
    batching = _PublicationBatchRecorder(
        commit_outcome=CompanyMetaCommitOutcome(
            company_meta=_fresh_company_meta(),
            ignored_company_name=None,
        ),
        events=events,
    )
    company = _MetadataStageRecorder(
        stage_error=OSError("metadata stage failed"),
        events=events,
    )

    with pytest.raises(OSError, match="metadata stage failed"):
        _execute_metadata_only_skip_fixture(
            workspace_root=tmp_path,
            requested_company_name="Apple Holdings",
            ticker_aliases=(),
            batching=batching,
            company_repository=company,
        )

    assert events == ["stage", "rollback"]
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
