"""filing batch publication 的封闭裁决与 shared lifecycle owner。

纯裁决函数保持无 I/O；shared publication route 在 writer-owned batch view 上完成
fresh validation、双取消 checkpoint、裁决、company stage 与既有 commit/rollback 交接。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Final, NoReturn

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.domain.document_models import BatchToken
from dayu.fins.ingestion_runtime import (
    FinsUploadUsageCode,
    FinsUploadUsageError,
    ValidatedFinsUploadFilingRequest,
    validate_fins_upload_filing_request,
)
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    FilingInitialSkipDisposition,
    PreparedDoclingUpload,
    UploadOperationResult,
    _PreparedFilingAssetMutation,
    _build_cancelled_result,
    build_prepared_filing_skip_result,
    commit_prepared_upload_batch,
    describe_prepared_filing_publication,
    read_prepared_filing_initial_skip_disposition,
    rebase_prepared_filing_create_overwrite,
    rollback_prepared_upload_batch,
)
from dayu.fins.pipelines.upload_company_meta import stage_upload_company_meta_decision
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    CompanyTickerIdentityCorruptionError,
    FilingUploadPublishedState,
    FilingUploadStateRepositoryProtocol,
    FilingUploadPublicationIdentity,
    SourceIntegrityStatus,
    has_same_source_publication_identity,
)
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureError,
    FinsUploadFailureReason,
    FinsUploadPrevalidationError,
    fins_upload_prevalidation_corruption_failure,
    fins_upload_prevalidation_io_failure,
    fins_upload_source_publication_conflict_failure,
    fins_upload_source_revision_stale_failure,
)
from dayu.fins.upload_repair_contract import (
    ExistingSourceAutoRepair,
    NoExistingSourceRepair,
)
from dayu.runtime.filelock import RuntimeFileLockError

_STATE_DEPENDENT_USAGE_CODES: Final[frozenset[FinsUploadUsageCode]] = frozenset(
    {
        FinsUploadUsageCode.CREATE_TARGET_EXISTS,
        FinsUploadUsageCode.UPDATE_TARGET_MISSING,
        FinsUploadUsageCode.EXISTING_SOURCE_REPAIR_REQUIRES_AUTO,
        FinsUploadUsageCode.COMPANY_NAME_REQUIRED,
    }
)
_PUBLICATION_COMPLETION_STATUSES: Final[frozenset[str]] = frozenset({"uploaded", "skipped", "cancelled"})


class FilingUploadPublicationDisposition(str, Enum):
    """batch fresh state 上的封闭 publication 裁决。"""

    PUBLISH = "publish"
    SKIP = "skip"
    CONFLICT = "conflict"


class FilingUploadPublishMode(str, Enum):
    """PUBLISH 裁决采用原 candidate 或 fresh create-overwrite rebase。"""

    PREPARED = "prepared"
    REBASE_CREATE_OVERWRITE = "rebase_create_overwrite"


@dataclass(frozen=True, slots=True)
class FilingUploadPublicationOutcome:
    """shared publication owner 返回的 authoritative request 与完成结果。

    Attributes:
        authoritative_request: writer-owned fresh view 验证产生的最终请求；batch 前取消时
            使用 initial request。
        result: uploaded、skipped 或 cancelled 完成结果。
    """

    authoritative_request: ValidatedFinsUploadFilingRequest
    result: UploadOperationResult

    def __post_init__(self) -> None:
        """校验 outcome 只承载 closed typed completion。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: request 或 result 不是精确 typed contract 时抛出。
            ValueError: result 是失败之外的未知状态时抛出。
        """

        if not isinstance(
            self.authoritative_request,
            ValidatedFinsUploadFilingRequest,
        ):
            raise TypeError("publication outcome 必须携带 validated filing request")
        if not isinstance(self.result, UploadOperationResult):
            raise TypeError("publication outcome 必须携带 UploadOperationResult")
        if self.result.status not in _PUBLICATION_COMPLETION_STATUSES:
            raise ValueError("publication outcome 只允许 uploaded/skipped/cancelled")


@dataclass(frozen=True, slots=True)
class FilingUploadPublicationDecision:
    """pure arbitration 产生的 typed closed decision。

    Attributes:
        disposition: publish、skip 或 conflict。
        publish_mode: publish 时的唯一 candidate 处理模式。
        failure_reason: conflict 时的 path-free typed reason。
    """

    disposition: FilingUploadPublicationDisposition
    publish_mode: FilingUploadPublishMode | None
    failure_reason: FinsUploadFailureReason | None

    def __post_init__(self) -> None:
        """校验 disposition、publish mode 与 failure 的封闭对应关系。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: enum 或 failure 类型不精确时抛出。
            ValueError: disposition 与附属字段组合不合法时抛出。
        """

        if type(self.disposition) is not FilingUploadPublicationDisposition:
            raise TypeError("publication disposition 必须是 closed enum")
        if self.disposition is FilingUploadPublicationDisposition.PUBLISH:
            if type(self.publish_mode) is not FilingUploadPublishMode:
                raise TypeError("PUBLISH decision 必须携带 publish mode")
            if self.failure_reason is not None:
                raise ValueError("PUBLISH decision 不得携带 failure")
            return
        if self.publish_mode is not None:
            raise ValueError("非 PUBLISH decision 不得携带 publish mode")
        if self.disposition is FilingUploadPublicationDisposition.SKIP:
            if self.failure_reason is not None:
                raise ValueError("SKIP decision 不得携带 failure")
            return
        if not isinstance(self.failure_reason, FinsUploadFailureReason):
            raise TypeError("CONFLICT decision 必须携带 typed failure")
        if self.failure_reason.code not in {
            FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT,
            FinsUploadFailureCode.SOURCE_REVISION_STALE,
        }:
            raise ValueError("CONFLICT decision 只允许 publication conflict 或 revision stale")


def _publish_decision(
    mode: FilingUploadPublishMode = FilingUploadPublishMode.PREPARED,
) -> FilingUploadPublicationDecision:
    """构造无 failure 的 publish decision。

    Args:
        mode: 复用 prepared candidate 或执行 create-overwrite rebase。

    Returns:
        typed publish decision。

    Raises:
        TypeError: mode 不是 closed enum 时由 decision contract 抛出。
    """

    return FilingUploadPublicationDecision(
        disposition=FilingUploadPublicationDisposition.PUBLISH,
        publish_mode=mode,
        failure_reason=None,
    )


def _skip_decision() -> FilingUploadPublicationDecision:
    """构造无 durable mutation 的 canonical skip decision。

    Args:
        无。

    Returns:
        typed skip decision。

    Raises:
        无。
    """

    return FilingUploadPublicationDecision(
        disposition=FilingUploadPublicationDisposition.SKIP,
        publish_mode=None,
        failure_reason=None,
    )


def _conflict_decision(
    failure_reason: FinsUploadFailureReason,
) -> FilingUploadPublicationDecision:
    """构造 fail-closed conflict decision。

    Args:
        failure_reason: publication conflict 或 repair revision stale reason。

    Returns:
        typed conflict decision。

    Raises:
        TypeError: failure 不是 typed reason 时由 decision contract 抛出。
        ValueError: failure code 不属于本裁决 owner 时由 decision contract 抛出。
    """

    return FilingUploadPublicationDecision(
        disposition=FilingUploadPublicationDisposition.CONFLICT,
        publish_mode=None,
        failure_reason=failure_reason,
    )


def _require_same_request_and_target(
    initial_request: ValidatedFinsUploadFilingRequest,
    fresh_request: ValidatedFinsUploadFilingRequest,
    prepared_identity: FilingUploadPublicationIdentity,
) -> None:
    """要求两次 validated observation 与 prepared identity 属于同一请求目标。

    Args:
        initial_request: preparation 使用的 initial validated request。
        fresh_request: batch staging view 上重新验证的 request。
        prepared_identity: preparation owner 产生的 candidate identity。

    Returns:
        所有身份一致时返回 ``None``。

    Raises:
        TypeError: 输入不是精确 typed contract 时抛出。
        ValueError: raw request、ticker、document 或 internal identity 不一致时抛出。
    """

    if not isinstance(initial_request, ValidatedFinsUploadFilingRequest):
        raise TypeError("initial_request 必须是 validated filing request")
    if not isinstance(fresh_request, ValidatedFinsUploadFilingRequest):
        raise TypeError("fresh_request 必须是 validated filing request")
    if not isinstance(prepared_identity, FilingUploadPublicationIdentity):
        raise TypeError("prepared_identity 必须是 filing publication identity")
    if initial_request.request != fresh_request.request:
        raise ValueError("batch arbitration 必须复用同一不可变 raw request")
    expected_target = (
        initial_request.normalized_ticker.canonical,
        initial_request.document_id,
        initial_request.internal_document_id,
    )
    if expected_target != (
        fresh_request.normalized_ticker.canonical,
        fresh_request.document_id,
        fresh_request.internal_document_id,
    ) or expected_target != (
        prepared_identity.ticker,
        prepared_identity.document_id,
        prepared_identity.internal_document_id,
    ):
        raise ValueError("batch arbitration request/prepared target identity 不一致")


def _source_observation_is_stable(
    initial_request: ValidatedFinsUploadFilingRequest,
    fresh_request: ValidatedFinsUploadFilingRequest,
) -> bool:
    """比较 initial/fresh exact source status 与 opaque publication identity。

    Args:
        initial_request: preparation 使用的 initial validated request。
        fresh_request: batch staging view 上重新验证的 request。

    Returns:
        MISSING/MISSING，或同状态 COMPLETE/REPAIR_REQUIRED 且 revision 相同返回 ``True``。

    Raises:
        ValueError: 任一 observation 为 UNSAFE，或 target identity 不一致时抛出。
    """

    initial = initial_request.published_state.source_integrity
    fresh = fresh_request.published_state.source_integrity
    if initial.status is not fresh.status:
        return False
    if initial.status is SourceIntegrityStatus.MISSING:
        return has_same_source_publication_identity(initial, fresh)
    if initial.status in {
        SourceIntegrityStatus.COMPLETE,
        SourceIntegrityStatus.REPAIR_REQUIRED,
    }:
        return has_same_source_publication_identity(initial, fresh)
    raise ValueError("UNSAFE source observation 不得进入 publication arbitration")


def _require_stable_action_contract(
    initial_request: ValidatedFinsUploadFilingRequest,
    fresh_request: ValidatedFinsUploadFilingRequest,
) -> None:
    """校验 stable observation 下 action 与 repair authorization 未漂移。

    Args:
        initial_request: preparation 使用的 initial validated request。
        fresh_request: batch staging view 上重新验证的 request。

    Returns:
        stable action/repair contract 一致时返回 ``None``。

    Raises:
        ValueError: resolved action 或 repair authorization 违反 stable invariant 时抛出。
    """

    status = initial_request.published_state.source_integrity.status
    if initial_request.resolved_action != fresh_request.resolved_action:
        raise ValueError("stable source observation 的 resolved action 必须一致")
    if status is SourceIntegrityStatus.MISSING:
        if (
            initial_request.resolved_action != "create"
            or not isinstance(initial_request.repair_disposition, NoExistingSourceRepair)
            or not isinstance(fresh_request.repair_disposition, NoExistingSourceRepair)
        ):
            raise ValueError("stable MISSING observation 必须保持 create/no-repair")
        return
    if status is SourceIntegrityStatus.COMPLETE:
        if not isinstance(initial_request.repair_disposition, NoExistingSourceRepair) or not isinstance(
            fresh_request.repair_disposition, NoExistingSourceRepair
        ):
            raise ValueError("stable COMPLETE observation 不得携带 repair authorization")
        return
    if (
        status is not SourceIntegrityStatus.REPAIR_REQUIRED
        or fresh_request.resolved_action != "update"
        or not isinstance(initial_request.repair_disposition, ExistingSourceAutoRepair)
        or not isinstance(fresh_request.repair_disposition, ExistingSourceAutoRepair)
        or initial_request.repair_disposition.expected_integrity != fresh_request.repair_disposition.expected_integrity
    ):
        raise ValueError("stable REPAIR_REQUIRED observation 必须保持同一 update repair authorization")


def _canonical_skip_requirements_are_met(
    fresh_request: ValidatedFinsUploadFilingRequest,
    prepared_identity: FilingUploadPublicationIdentity,
) -> bool:
    """判断 fresh durable publication 与 prepared candidate 是否满足 skip 共用条件。

    Args:
        fresh_request: batch staging view 上重新验证的 request。
        prepared_identity: preparation owner 产生的 candidate identity。

    Returns:
        fresh COMPLETE、company keep/no-intent 且 durable/prepared identity exact equal时
        返回 ``True``。

    Raises:
        无。
    """

    fresh_state = fresh_request.published_state
    decision = fresh_request.company_meta_decision
    return (
        fresh_state.source_integrity.status is SourceIntegrityStatus.COMPLETE
        and decision.disposition == "keep"
        and decision.company_meta_intent is None
        and fresh_state.publication_identity is not None
        and fresh_state.publication_identity == prepared_identity
    )


def arbitrate_filing_upload_publication(
    *,
    initial_request: ValidatedFinsUploadFilingRequest,
    fresh_request: ValidatedFinsUploadFilingRequest,
    prepared_identity: FilingUploadPublicationIdentity,
    initial_skip_disposition: FilingInitialSkipDisposition,
) -> FilingUploadPublicationDecision:
    """在无 I/O 边界按 frozen state table 裁决 publish、skip 或 conflict。

    Args:
        initial_request: preparation 使用的 initial validated request。
        fresh_request: batch staging view 上对同一 raw request 的 fresh validation。
        prepared_identity: preparation owner 产生的 exact candidate identity。
        initial_skip_disposition: preparation owner 与既有 identical-skip 同源产生的事实。

    Returns:
        唯一 closed decision；repair observation 漂移以 ``CONFLICT`` 携带既有
        ``SOURCE_REVISION_STALE`` reason。

    Raises:
        TypeError: 任一 typed input 不符合 contract 时抛出。
        ValueError: 请求/target identity、UNSAFE state 或 stable action invariant 违约时抛出。
    """

    _require_same_request_and_target(initial_request, fresh_request, prepared_identity)
    if type(initial_skip_disposition) is not FilingInitialSkipDisposition:
        raise TypeError("initial_skip_disposition 必须是 FilingInitialSkipDisposition")
    initial_status = initial_request.published_state.source_integrity.status
    fresh_status = fresh_request.published_state.source_integrity.status
    if initial_status is SourceIntegrityStatus.UNSAFE or fresh_status is SourceIntegrityStatus.UNSAFE:
        raise ValueError("UNSAFE source observation 不得进入 pure arbitration")

    stable = _source_observation_is_stable(initial_request, fresh_request)
    if stable:
        _require_stable_action_contract(initial_request, fresh_request)
        if (
            fresh_status is SourceIntegrityStatus.COMPLETE
            and initial_skip_disposition is FilingInitialSkipDisposition.IDENTICAL_PUBLICATION
            and _canonical_skip_requirements_are_met(fresh_request, prepared_identity)
        ):
            return _skip_decision()
        return _publish_decision()

    raw_action = initial_request.request.action.strip().lower()
    overwrite = initial_request.request.overwrite
    if initial_status is SourceIntegrityStatus.MISSING and fresh_status is SourceIntegrityStatus.COMPLETE:
        if (
            raw_action == "auto"
            and overwrite is False
            and initial_request.resolved_action == "create"
            and fresh_request.resolved_action == "update"
            and _canonical_skip_requirements_are_met(fresh_request, prepared_identity)
        ):
            return _skip_decision()
        if (
            raw_action == "create"
            and overwrite is True
            and initial_request.resolved_action == "create"
            and fresh_request.resolved_action == "create"
        ):
            return _publish_decision(FilingUploadPublishMode.REBASE_CREATE_OVERWRITE)
        return _conflict_decision(fins_upload_source_publication_conflict_failure())
    if initial_status is SourceIntegrityStatus.REPAIR_REQUIRED:
        return _conflict_decision(fins_upload_source_revision_stale_failure())
    return _conflict_decision(fins_upload_source_publication_conflict_failure())


def _is_cancelled(cancellation: CancellationToken | None) -> bool:
    """读取 shared publication checkpoint 的协作式取消状态。

    Args:
        cancellation: 公共取消 token；``None`` 表示无取消源。

    Returns:
        已取消返回 ``True``。

    Raises:
        OSError: token 读取失败时原样传播。
    """

    return bool(cancellation is not None and cancellation.is_cancelled())


def _rollback_without_business_terminal(
    *,
    batching_repository: BatchingRepositoryProtocol,
    batch: BatchToken,
) -> None:
    """为 cancel/skip 回滚 batch，并把 rollback failure 投影为 typed storage failure。

    Args:
        batching_repository: batch 生命周期仓储。
        batch: caller-owned batch capability。

    Returns:
        rollback 成功时返回 ``None``。

    Raises:
        FinsUploadFailureError: rollback 失败时抛出 path-free STORAGE_IO。
        KeyboardInterrupt: rollback 收到中断信号时原样传播。
        SystemExit: rollback 收到退出信号时原样传播。
    """

    try:
        batching_repository.rollback_batch(batch)
    except (OSError, RuntimeFileLockError, ValueError) as rollback_error:
        raise FinsUploadFailureError(fins_upload_prevalidation_io_failure()) from rollback_error


def _raise_failure_after_rollback(
    *,
    batching_repository: BatchingRepositoryProtocol,
    batch: BatchToken,
    failure_reason: FinsUploadFailureReason,
) -> NoReturn:
    """以 typed failure 为 primary 回滚 batch 后抛出。

    Args:
        batching_repository: batch 生命周期仓储。
        batch: caller-owned batch capability。
        failure_reason: 已封闭裁决的 public failure reason。

    Returns:
        不返回。

    Raises:
        FinsUploadFailureError: 始终抛出；rollback 失败时仍保留该 typed primary。
    """

    error = FinsUploadFailureError(failure_reason)
    rollback_prepared_upload_batch(
        batching_repository=batching_repository,
        batch=batch,
        operation_error=error,
    )
    raise error


def _read_fresh_state_or_raise(
    *,
    repository: FilingUploadStateRepositoryProtocol,
    batch: BatchToken,
    document_id: str,
) -> FilingUploadPublishedState:
    """从 writer-owned batch 读取 fresh state并封闭映射读取异常。

    Args:
        repository: filing state 唯一仓储。
        batch: caller-owned batch capability。
        document_id: exact filing document ID。

    Returns:
        storage owner 产生的 typed filing state。

    Raises:
        FinsUploadFailureError: I/O/lock 或 corruption 读取失败时抛出 typed STORAGE_IO。
    """

    try:
        return repository.read_filing_upload_state_in_batch(batch, document_id)
    except CompanyTickerIdentityCorruptionError as error:
        raise FinsUploadFailureError(fins_upload_prevalidation_corruption_failure()) from error
    except ValueError as error:
        raise FinsUploadFailureError(fins_upload_prevalidation_corruption_failure()) from error
    except (OSError, RuntimeFileLockError, RuntimeError) as error:
        raise FinsUploadFailureError(fins_upload_prevalidation_io_failure()) from error


def _begin_publication_batch_or_raise(
    *,
    batching_repository: BatchingRepositoryProtocol,
    ticker: str,
) -> BatchToken:
    """取得 ticker writer batch，并封闭映射 acquire operational failure。

    Args:
        batching_repository: batch 生命周期仓储。
        ticker: canonical ticker。

    Returns:
        新取得的 caller-owned batch capability。

    Raises:
        FinsUploadFailureError: acquire 的 I/O/lock/corruption 失败时抛出 typed STORAGE_IO。
    """

    try:
        return batching_repository.begin_batch(ticker)
    except CompanyTickerIdentityCorruptionError as error:
        raise FinsUploadFailureError(fins_upload_prevalidation_corruption_failure()) from error
    except (OSError, RuntimeFileLockError, RuntimeError) as error:
        raise FinsUploadFailureError(fins_upload_prevalidation_io_failure()) from error


def execute_prepared_filing_publication(
    *,
    request: ValidatedFinsUploadFilingRequest,
    prepared: PreparedDoclingUpload,
    filing_state_repository: FilingUploadStateRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    batching_repository: BatchingRepositoryProtocol,
    upload_service: DoclingUploadService,
    cancellation: CancellationToken | None,
) -> FilingUploadPublicationOutcome:
    """在 writer-owned fresh view 上执行 filing 的唯一 publication lifecycle。

    Args:
        request: preparation 使用的 initial authoritative request。
        prepared: 已完成 filing conversion 的 typed candidate。
        filing_state_repository: batch fresh state 仓储。
        company_repository: fresh company decision 的 staging 仓储。
        batching_repository: per-ticker batch lifecycle 仓储。
        upload_service: staged source mutation 服务。
        cancellation: 公共取消 token；``None`` 表示无取消源。

    Returns:
        携带 fresh authoritative request 的 uploaded/skipped outcome，或第一/第二 checkpoint
        取消时始终携带 initial request 的 cancelled outcome。

    Raises:
        FinsUploadFailureError: conflict、unsafe、storage I/O/corruption 或 rollback failure。
        FinsUploadUsageError: 非 state-dependent fresh usage invariant breach 原样传播。
        TypeError: prepared candidate 或 closed contract 非法时抛出。
        ValueError: arbitration 或 rebase programming invariant 违约时抛出。
        BaseException: existing publish/commit owner 的 primary/secondary error 原样传播。
    """

    if not isinstance(request, ValidatedFinsUploadFilingRequest):
        raise TypeError("request 必须是 validated filing request")
    if not isinstance(prepared, _PreparedFilingAssetMutation):
        raise TypeError("prepared 必须是 filing prepared mutation")
    prepared_identity = describe_prepared_filing_publication(prepared)
    initial_disposition = read_prepared_filing_initial_skip_disposition(prepared)
    batch = _begin_publication_batch_or_raise(
        batching_repository=batching_repository,
        ticker=request.normalized_ticker.canonical,
    )
    batch_terminal_started = False
    try:
        if _is_cancelled(cancellation):
            batch_terminal_started = True
            _rollback_without_business_terminal(
                batching_repository=batching_repository,
                batch=batch,
            )
            return FilingUploadPublicationOutcome(
                authoritative_request=request,
                result=_build_cancelled_result(
                    document_id=request.document_id,
                    internal_document_id=request.internal_document_id,
                ),
            )

        fresh_state = _read_fresh_state_or_raise(
            repository=filing_state_repository,
            batch=batch,
            document_id=request.document_id,
        )
        validation_failure: FinsUploadFailureReason | None = None
        try:
            fresh_request = validate_fins_upload_filing_request(
                request.request,
                published_state=fresh_state,
            )
        except FinsUploadUsageError as error:
            if error.failure.code not in _STATE_DEPENDENT_USAGE_CODES:
                raise
            validation_failure = fins_upload_source_publication_conflict_failure()
            fresh_request = None
        except FinsUploadPrevalidationError as error:
            validation_failure = error.failure
            fresh_request = None
        except ValueError:
            validation_failure = fins_upload_prevalidation_corruption_failure()
            fresh_request = None

        decision: FilingUploadPublicationDecision | None = None
        if validation_failure is None:
            if fresh_request is None:
                raise AssertionError("fresh validation success 必须产生 validated request")
            decision = arbitrate_filing_upload_publication(
                initial_request=request,
                fresh_request=fresh_request,
                prepared_identity=prepared_identity,
                initial_skip_disposition=initial_disposition,
            )

        if _is_cancelled(cancellation):
            batch_terminal_started = True
            _rollback_without_business_terminal(
                batching_repository=batching_repository,
                batch=batch,
            )
            return FilingUploadPublicationOutcome(
                authoritative_request=request,
                result=_build_cancelled_result(
                    document_id=request.document_id,
                    internal_document_id=request.internal_document_id,
                ),
            )

        if validation_failure is not None:
            batch_terminal_started = True
            _raise_failure_after_rollback(
                batching_repository=batching_repository,
                batch=batch,
                failure_reason=validation_failure,
            )
        if decision is None or fresh_request is None:
            raise AssertionError("closed arbitration 必须产生 decision 与 fresh request")

        if decision.disposition is FilingUploadPublicationDisposition.SKIP:
            batch_terminal_started = True
            _rollback_without_business_terminal(
                batching_repository=batching_repository,
                batch=batch,
            )
            return FilingUploadPublicationOutcome(
                authoritative_request=fresh_request,
                result=build_prepared_filing_skip_result(prepared),
            )
        if decision.disposition is FilingUploadPublicationDisposition.CONFLICT:
            if decision.failure_reason is None:
                raise AssertionError("CONFLICT decision 必须携带 failure")
            batch_terminal_started = True
            _raise_failure_after_rollback(
                batching_repository=batching_repository,
                batch=batch,
                failure_reason=decision.failure_reason,
            )

        publication_candidate: _PreparedFilingAssetMutation = prepared
        if decision.publish_mode is FilingUploadPublishMode.REBASE_CREATE_OVERWRITE:
            if fresh_request.published_state.source_meta is None:
                raise ValueError("fresh create-overwrite rebase 必须携带 source meta")
            rebased_candidate = rebase_prepared_filing_create_overwrite(
                prepared,
                fresh_previous_meta=dict(fresh_request.published_state.source_meta),
            )
            if not isinstance(rebased_candidate, _PreparedFilingAssetMutation):
                raise AssertionError("fresh rebase 必须保持 filing prepared subtype")
            publication_candidate = rebased_candidate
        elif decision.publish_mode is not FilingUploadPublishMode.PREPARED:
            raise AssertionError("PUBLISH decision 必须携带 closed publish mode")

        stage_upload_company_meta_decision(
            repository=company_repository,
            decision=fresh_request.company_meta_decision,
            batch=batch,
        )
        # capability 转交 existing commit owner；从此由其负责 publish/cancel/rollback/commit。
        batch_terminal_started = True
        result = commit_prepared_upload_batch(
            service=upload_service,
            batching_repository=batching_repository,
            batch=batch,
            prepared=publication_candidate,
            cancellation=cancellation,
        )
        return FilingUploadPublicationOutcome(
            authoritative_request=fresh_request,
            result=result,
        )
    finally:
        if not batch_terminal_started:
            rollback_prepared_upload_batch(
                batching_repository=batching_repository,
                batch=batch,
                operation_error=sys.exception(),
            )


__all__ = [
    "FilingUploadPublicationDecision",
    "FilingUploadPublicationDisposition",
    "FilingUploadPublicationOutcome",
    "FilingUploadPublishMode",
    "arbitrate_filing_upload_publication",
    "execute_prepared_filing_publication",
]
