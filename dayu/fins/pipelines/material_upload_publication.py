"""材料独立公司阶段与条件发布 owner，复用 D 的一次 capability 生命周期。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from enum import Enum

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.domain.company_meta_contract import CompanyMetaConcurrentUpdateError
from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import FINS_UPLOAD_ACTION_AUTO, ValidatedFinsUploadMaterialRequest
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    PreparedDoclingUpload,
    UploadOperationResult,
    _PreparedDeleteMutation,
    build_prepared_material_skip_candidate,
    commit_prepared_upload_batch,
    describe_prepared_material_publication,
    rollback_prepared_upload_batch,
)
from dayu.fins.pipelines.upload_company_meta import stage_upload_company_meta_decision
from dayu.fins.storage.repository_protocols import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    MaterialUploadPublicationIdentity,
    MaterialUploadPublishedState,
    MaterialUploadStateRepositoryProtocol,
)
from dayu.fins.storage.source_integrity import SourceIntegrityRevisionConflictError, SourceIntegrityStatus
from dayu.fins.upload_failure import (
    FinsUploadFailureError,
    FinsUploadFailureReason,
    fins_upload_source_publication_conflict_failure,
)


class MaterialUploadPublicationDisposition(str, Enum):
    """纯材料裁决的封闭分支。"""

    PUBLISH = "publish"
    IDENTICAL_SKIP = "identical_skip"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class MaterialUploadPublicationDecision:
    """裁决与唯一失败原因。"""

    disposition: MaterialUploadPublicationDisposition
    failure: FinsUploadFailureReason | None

    def __post_init__(self) -> None:
        """参数：无；返回：无；异常：类型或失败互斥合同违约。"""
        if type(self.disposition) is not MaterialUploadPublicationDisposition or (
            self.disposition is MaterialUploadPublicationDisposition.CONFLICT
        ) != (self.failure is not None):
            raise ValueError("材料裁决与失败不一致")


@dataclass(frozen=True, slots=True)
class MaterialUploadPublicationOutcome:
    """D 原样传递的该次材料 final 与操作结果。"""

    published_state: MaterialUploadPublishedState | None
    result: UploadOperationResult

    def __post_init__(self) -> None:
        """参数：无；返回：无；异常：取消或材料正常结果缺同次完整状态。"""
        if (
            self.result.source_kind is not SourceKind.MATERIAL
            or self.result.material_published_state is not self.published_state
        ):
            raise ValueError("材料 outcome 必须复用 result 同一个 final")
        if self.result.status == "cancelled":
            if self.published_state is not None or self.result.published_amended is not None:
                raise ValueError("取消不得携带成功状态")
        elif (
            self.published_state is None
            or self.published_state.source_integrity.status is not SourceIntegrityStatus.COMPLETE
            or self.result.document_id != self.published_state.source_integrity.document_id
        ):
            raise ValueError("材料正常结果必须携带同目标完整 final")


def _source_matches(left: MaterialUploadPublishedState, right: MaterialUploadPublishedState) -> bool:
    """参数：两份同源状态；返回：源事实是否精确一致；异常：无；公司另行比较。"""
    return (
        left.source_integrity == right.source_integrity
        and left.source_meta == right.source_meta
        and left.publication_identity == right.publication_identity
    )


def arbitrate_material_upload_publication(
    *,
    request: ValidatedFinsUploadMaterialRequest,
    fresh_state: MaterialUploadPublishedState,
    candidate: MaterialUploadPublicationIdentity,
    expected_company_meta: CompanyMeta | None,
) -> MaterialUploadPublicationDecision:
    """参数：受理、writer view、候选及公司 final；返回：纯三分支裁决；异常：无，不接触 I/O。"""
    if fresh_state.company_meta == expected_company_meta:
        if _source_matches(fresh_state, request.state_admission.observed_state):
            return MaterialUploadPublicationDecision(MaterialUploadPublicationDisposition.PUBLISH, None)
        published = fresh_state.publication_identity
        # 文档版本属于内容 owner；同原件候选可能按旧 MISSING 准备 v1，不拿治理版本猜相同。
        if (
            request.action_decision.requested_action == FINS_UPLOAD_ACTION_AUTO
            and not request.request.overwrite
            and fresh_state.source_integrity.status is SourceIntegrityStatus.COMPLETE
            and published is not None
            and not published.is_deleted
            and published == replace(candidate, document_version=published.document_version)
        ):
            return MaterialUploadPublicationDecision(MaterialUploadPublicationDisposition.IDENTICAL_SKIP, None)
    return MaterialUploadPublicationDecision(
        MaterialUploadPublicationDisposition.CONFLICT,
        fins_upload_source_publication_conflict_failure(source_kind=SourceKind.MATERIAL),
    )


def execute_material_upload_company_stage(
    *,
    request: ValidatedFinsUploadMaterialRequest,
    state_repository: MaterialUploadStateRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    batching_repository: BatchingRepositoryProtocol,
    cancellation: CancellationToken | None,
) -> CompanyMeta | None:
    """执行独立公司阶段，把受控 auto 的材料竞争留给材料 writer。

    Args:
        request: 同次受理的材料请求与公司快照。
        state_repository: 校验公司、alias 及显式源条件的仓储。
        company_repository: 公司意图暂存仓储。
        batching_repository: 独立公司 batch 的生命周期仓储。
        cancellation: 可选取消源。
    Returns:
        独立提交的公司 final；取消时返回受理时公司。
    Raises:
        FinsUploadFailureError: 公司或非竞争材料条件漂移。
        CompanyTickerAliasConflictError: alias 占用，原样透传。
        OSError: 真实读写、锁或释放失败，原样透传。
    """
    observed = request.state_admission.observed_state
    if cancellation is not None and cancellation.is_cancelled():
        return observed.company_meta
    decision = request.state_admission.company_decision
    try:
        competing_auto = request.action_decision.requested_action == FINS_UPLOAD_ACTION_AUTO and not request.request.overwrite
        # None 只免除此公司 guard 的源条件；材料 writer/登记/最终 guard 仍严格校验完整状态。
        source_expected = None if competing_auto else observed
        if decision.disposition != "stage":
            state_repository.validate_material_upload_state(
                ticker=observed.source_integrity.ticker,
                document_id=observed.source_integrity.document_id,
                expected_source_state=source_expected,
                expected_company_meta=observed.company_meta,
            )
            return observed.company_meta
        # initial None 的唯一例外由公司 commit owner 检查同意图无增量；已有观察值先严格 guard。
        if observed.company_meta is not None:
            state_repository.validate_material_upload_state(
                ticker=observed.source_integrity.ticker,
                document_id=observed.source_integrity.document_id,
                expected_source_state=source_expected,
                expected_company_meta=observed.company_meta,
            )
        batch = batching_repository.begin_batch(observed.source_integrity.ticker)
        transferred = False
        try:
            stage_upload_company_meta_decision(repository=company_repository, decision=decision, batch=batch)
            if cancellation is not None and cancellation.is_cancelled():
                return observed.company_meta
            transferred = True
            return state_repository.commit_material_upload_company_batch(batch).company_meta
        finally:
            if not transferred:
                rollback_prepared_upload_batch(
                    batching_repository=batching_repository, batch=batch, operation_error=sys.exception()
                )
    except (SourceIntegrityRevisionConflictError, CompanyMetaConcurrentUpdateError) as error:
        raise FinsUploadFailureError(
            fins_upload_source_publication_conflict_failure(source_kind=SourceKind.MATERIAL)
        ) from error


def execute_prepared_material_publication(
    *,
    request: ValidatedFinsUploadMaterialRequest,
    prepared: PreparedDoclingUpload,
    expected_company_meta: CompanyMeta | None,
    state_repository: MaterialUploadStateRepositoryProtocol,
    batching_repository: BatchingRepositoryProtocol,
    upload_service: DoclingUploadService,
    cancellation: CancellationToken | None,
) -> MaterialUploadPublicationOutcome:
    """参数：同次受理、准备、公司 final 与仓储；返回：同次 actual final；异常：漂移 typed conflict，真实 I/O 透传；提交后无重读或重试。"""
    if isinstance(prepared, UploadOperationResult):
        return MaterialUploadPublicationOutcome(prepared.material_published_state, prepared)
    observed = request.state_admission.observed_state
    batch = batching_repository.begin_batch(observed.source_integrity.ticker)
    transferred = False
    try:
        fresh = state_repository.read_material_upload_state_in_batch(batch, request.identity.document_id)
        expected = observed
        if not isinstance(prepared, _PreparedDeleteMutation):
            decision = arbitrate_material_upload_publication(
                request=request,
                fresh_state=fresh,
                candidate=describe_prepared_material_publication(prepared),
                expected_company_meta=expected_company_meta,
            )
            if decision.disposition is MaterialUploadPublicationDisposition.CONFLICT:
                if decision.failure is None:
                    raise AssertionError("冲突缺失败原因")
                raise FinsUploadFailureError(decision.failure)
            if decision.disposition is MaterialUploadPublicationDisposition.IDENTICAL_SKIP:
                expected = fresh
                prepared = build_prepared_material_skip_candidate(prepared)
        state_repository.register_material_upload_preconditions(
            batch=batch, expected_source_state=expected, expected_company_meta=expected_company_meta
        )
        # D 从这里独占取消、rollback、commit 及 COMMITTED 后失败边界。
        transferred = True
        result = commit_prepared_upload_batch(
            service=upload_service,
            batching_repository=batching_repository,
            batch=batch,
            prepared=prepared,
            cancellation=cancellation,
            material_state_repository=state_repository,
        )
        return MaterialUploadPublicationOutcome(result.material_published_state, result)
    except (SourceIntegrityRevisionConflictError, CompanyMetaConcurrentUpdateError) as error:
        raise FinsUploadFailureError(
            fins_upload_source_publication_conflict_failure(source_kind=SourceKind.MATERIAL)
        ) from error
    finally:
        if not transferred:
            rollback_prepared_upload_batch(
                batching_repository=batching_repository, batch=batch, operation_error=sys.exception()
            )
