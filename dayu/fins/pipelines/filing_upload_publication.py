"""filing batch publication 的无 I/O 封闭裁决 owner。

S1 只定义 typed decision 与纯函数；本模块不打开 batch、不读仓储、不 stage、
不 commit/rollback，也不被 SEC/CN/HK workflow 调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dayu.fins.ingestion_runtime import ValidatedFinsUploadFilingRequest
from dayu.fins.pipelines.docling_upload_service import FilingInitialSkipDisposition
from dayu.fins.storage import (
    FilingUploadPublicationIdentity,
    SourceIntegrityStatus,
    has_same_source_publication_identity,
)
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureReason,
    fins_upload_source_publication_conflict_failure,
    fins_upload_source_revision_stale_failure,
)
from dayu.fins.upload_repair_contract import (
    ExistingSourceAutoRepair,
    NoExistingSourceRepair,
)


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
    if (
        expected_target
        != (
            fresh_request.normalized_ticker.canonical,
            fresh_request.document_id,
            fresh_request.internal_document_id,
        )
        or expected_target
        != (
            prepared_identity.ticker,
            prepared_identity.document_id,
            prepared_identity.internal_document_id,
        )
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
        if (
            not isinstance(initial_request.repair_disposition, NoExistingSourceRepair)
            or not isinstance(fresh_request.repair_disposition, NoExistingSourceRepair)
        ):
            raise ValueError("stable COMPLETE observation 不得携带 repair authorization")
        return
    if (
        status is not SourceIntegrityStatus.REPAIR_REQUIRED
        or fresh_request.resolved_action != "update"
        or not isinstance(initial_request.repair_disposition, ExistingSourceAutoRepair)
        or not isinstance(fresh_request.repair_disposition, ExistingSourceAutoRepair)
        or initial_request.repair_disposition.expected_integrity
        != fresh_request.repair_disposition.expected_integrity
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
            and initial_skip_disposition
            is FilingInitialSkipDisposition.IDENTICAL_PUBLICATION
            and _canonical_skip_requirements_are_met(fresh_request, prepared_identity)
        ):
            return _skip_decision()
        return _publish_decision()

    raw_action = initial_request.request.action.strip().lower()
    overwrite = initial_request.request.overwrite
    if (
        initial_status is SourceIntegrityStatus.MISSING
        and fresh_status is SourceIntegrityStatus.COMPLETE
    ):
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


__all__ = [
    "FilingUploadPublicationDecision",
    "FilingUploadPublicationDisposition",
    "FilingUploadPublishMode",
    "arbitrate_filing_upload_publication",
]
