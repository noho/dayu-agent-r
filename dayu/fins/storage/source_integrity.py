"""源文档 publication 完整性、repair 阻断与跨 provider 预检 typed contract。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypeAlias

from dayu.fins.domain.document_models import SourceDocumentRevision
from dayu.fins.domain.enums import SourceKind


class SourceIntegrityStatus(str, Enum):
    """源文档目标的封闭完整性状态。"""

    MISSING = "missing"
    COMPLETE = "complete"
    REPAIR_REQUIRED = "repair_required"
    UNSAFE = "unsafe"


class SourceIntegrityReason(str, Enum):
    """source publication 完整性分类的封闭原因。"""

    ORIGINAL_FILE_MISSING = "original_file_missing"
    PRIMARY_DOCLING_FILE_MISSING = "primary_docling_file_missing"
    DECLARED_FILE_MISSING = "declared_file_missing"
    SIZE_MISMATCH = "size_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    PRIMARY_PROJECTION_MISMATCH = "primary_projection_mismatch"
    DERIVED_PROJECTION_MISMATCH = "derived_projection_mismatch"
    SOURCE_MANIFEST_MISSING = "source_manifest_missing"
    SOURCE_MANIFEST_PROJECTION_MISMATCH = "source_manifest_projection_mismatch"
    IDENTITY_UNTRUSTED = "identity_untrusted"
    META_UNTRUSTED = "meta_untrusted"
    REVISION_UNTRUSTED = "revision_untrusted"
    PROVENANCE_UNTRUSTED = "provenance_untrusted"
    FILE_DECLARATION_UNTRUSTED = "file_declaration_untrusted"
    UNDECLARED_BUSINESS_FILE = "undeclared_business_file"
    UNSAFE_FILESYSTEM_ENTRY = "unsafe_filesystem_entry"
    SOURCE_MANIFEST_UNTRUSTED = "source_manifest_untrusted"
    CROSS_SOURCE_INCONSISTENCY = "cross_source_inconsistency"


_REPAIRABLE_REASONS: frozenset[SourceIntegrityReason] = frozenset(
    {
        SourceIntegrityReason.ORIGINAL_FILE_MISSING,
        SourceIntegrityReason.PRIMARY_DOCLING_FILE_MISSING,
        SourceIntegrityReason.DECLARED_FILE_MISSING,
        SourceIntegrityReason.SIZE_MISMATCH,
        SourceIntegrityReason.DIGEST_MISMATCH,
        SourceIntegrityReason.PRIMARY_PROJECTION_MISMATCH,
        SourceIntegrityReason.DERIVED_PROJECTION_MISMATCH,
        SourceIntegrityReason.SOURCE_MANIFEST_MISSING,
        SourceIntegrityReason.SOURCE_MANIFEST_PROJECTION_MISMATCH,
    }
)
_UNSAFE_REASONS: frozenset[SourceIntegrityReason] = frozenset(
    {
        SourceIntegrityReason.IDENTITY_UNTRUSTED,
        SourceIntegrityReason.META_UNTRUSTED,
        SourceIntegrityReason.REVISION_UNTRUSTED,
        SourceIntegrityReason.PROVENANCE_UNTRUSTED,
        SourceIntegrityReason.FILE_DECLARATION_UNTRUSTED,
        SourceIntegrityReason.UNDECLARED_BUSINESS_FILE,
        SourceIntegrityReason.UNSAFE_FILESYSTEM_ENTRY,
        SourceIntegrityReason.SOURCE_MANIFEST_UNTRUSTED,
        SourceIntegrityReason.CROSS_SOURCE_INCONSISTENCY,
    }
)


@dataclass(frozen=True, slots=True)
class SourceIntegrityClassification:
    """单个 published 或 staged source 的可比较完整性身份。

    Attributes:
        ticker: exact external ticker。
        source_kind: filing 或 material。
        document_id: exact external document ID。
        revision: 已存在 source 的 opaque revision；目标不存在时为 ``None``。
        status: 封闭完整性状态。
        reasons: 按 enum 顺序去重的 repairable 或 unsafe 原因。
    """

    ticker: str
    source_kind: SourceKind
    document_id: str
    revision: SourceDocumentRevision | None
    status: SourceIntegrityStatus
    reasons: tuple[SourceIntegrityReason, ...]

    def __post_init__(self) -> None:
        """校验状态、revision 与 reasons 的互斥不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: typed classification 内部状态不封闭时抛出。
        """

        if not isinstance(self.source_kind, SourceKind):
            raise ValueError("source_kind 必须是 SourceKind")
        if not isinstance(self.status, SourceIntegrityStatus):
            raise ValueError("status 必须是 SourceIntegrityStatus")
        if self.revision is not None and not isinstance(self.revision, SourceDocumentRevision):
            raise ValueError("revision 必须是 SourceDocumentRevision 或 None")
        if any(not isinstance(reason, SourceIntegrityReason) for reason in self.reasons):
            raise ValueError("reasons 必须只包含 SourceIntegrityReason")
        ordered_reasons = tuple(reason for reason in SourceIntegrityReason if reason in set(self.reasons))
        if self.reasons != ordered_reasons:
            raise ValueError("reasons 必须按 enum 顺序去重")

        if self.status is SourceIntegrityStatus.MISSING:
            if self.revision is not None or self.reasons:
                raise ValueError("MISSING classification 不得携带 revision 或 reasons")
            return
        if self.status is SourceIntegrityStatus.COMPLETE:
            if self.revision is None or self.reasons:
                raise ValueError("COMPLETE classification 必须携带 revision 且不得携带 reasons")
            return
        if self.status is SourceIntegrityStatus.REPAIR_REQUIRED:
            if self.revision is None or not self.reasons:
                raise ValueError("REPAIR_REQUIRED classification 必须携带 revision 与 reasons")
            if any(reason not in _REPAIRABLE_REASONS for reason in self.reasons):
                raise ValueError("REPAIR_REQUIRED classification 只能携带 repairable reasons")
            return
        if self.status is not SourceIntegrityStatus.UNSAFE:
            raise ValueError("status 必须是封闭四态")
        if self.revision is not None or not self.reasons:
            raise ValueError("UNSAFE classification 不得携带 revision 且必须携带 reasons")
        if any(reason not in _UNSAFE_REASONS for reason in self.reasons):
            raise ValueError("UNSAFE classification 只能携带 unsafe reasons")


@dataclass(frozen=True, slots=True)
class NoSourceRepairRequired:
    """完整 ticker inventory 无待修复 source。"""

    kind: Literal["clean"] = "clean"


@dataclass(frozen=True, slots=True)
class SelectedSourceRepairRequired:
    """唯一待修复 source 是 workflow 已接受的 filing target。

    Attributes:
        target: 必须优先修复的 source classification。
        kind: typed discriminator。
    """

    target: SourceIntegrityClassification
    kind: Literal["repair_selected"] = "repair_selected"

    def __post_init__(self) -> None:
        """校验 repair target 确为 filing corruption。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: target 不是待修复 filing 时抛出。
        """

        if (
            self.target.source_kind is not SourceKind.FILING
            or self.target.status is not SourceIntegrityStatus.REPAIR_REQUIRED
        ):
            raise ValueError("selected repair target 必须是 REPAIR_REQUIRED filing")


SourceIntegrityPreflightDisposition: TypeAlias = NoSourceRepairRequired | SelectedSourceRepairRequired


class SourceIntegrityPreflightReason(str, Enum):
    """完整 ticker preflight 的封闭失败原因。"""

    MULTIPLE_REPAIR_REQUIRED = "multiple_repair_required"
    UNSELECTED_REPAIR_REQUIRED = "unselected_repair_required"
    SELECTED_REJECTED_REPAIR_REQUIRED = "selected_rejected_repair_required"
    UNSAFE_PUBLICATION = "unsafe_publication"


class SourceIntegrityPreflightError(RuntimeError):
    """完整 ticker integrity 无法由本次请求安全修复。"""

    def __init__(self, reason: SourceIntegrityPreflightReason) -> None:
        """构造不泄漏路径或 raw meta 的 typed preflight error。

        Args:
            reason: 封闭失败原因。

        Returns:
            无。

        Raises:
            无。
        """

        self.reason = reason
        super().__init__(f"source integrity preflight 失败: {reason.value}")


class SourceIntegrityRevisionConflictError(RuntimeError):
    """Phase A 与真实 staged target 的 publication identity 不再匹配。"""

    def __init__(self) -> None:
        """构造不泄漏 revision 或路径的冲突异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("source publication identity 已变化，无法安全应用预取结果")


class SourceIntegrityRepairBlockedReason(str, Enum):
    """target identity 仍匹配时阻断 staged repair 的封闭原因。"""

    NON_TARGET_SOURCE_INCOMPLETE = "non_target_source_incomplete"
    CROSS_SOURCE_PUBLICATION_UNSAFE = "cross_source_publication_unsafe"
    CANONICAL_MANIFEST_UNAVAILABLE = "canonical_manifest_unavailable"


class SourceIntegrityRepairBlockedError(RuntimeError):
    """其它 source 或 canonical manifest 状态阻断本次 staged repair。"""

    reason: SourceIntegrityRepairBlockedReason

    def __init__(self, reason: SourceIntegrityRepairBlockedReason) -> None:
        """构造不携带 target、revision、路径或 raw reason 的 typed error。

        Args:
            reason: 封闭 repair-blocked 原因。

        Returns:
            无。

        Raises:
            ValueError: reason 不是封闭 enum 时抛出。
        """

        if not isinstance(reason, SourceIntegrityRepairBlockedReason):
            raise ValueError("reason 必须是 SourceIntegrityRepairBlockedReason")
        self.reason = reason
        super().__init__("source repair 被其它 publication 完整性状态阻断")


def has_same_source_publication_identity(
    first: SourceIntegrityClassification,
    second: SourceIntegrityClassification,
) -> bool:
    """比较两次 classification 的 target presence 与 opaque revision。

    Args:
        first: 第一阶段 classification。
        second: 第二阶段 classification。

    Returns:
        target identity 与 presence 相同返回 ``True``。

    Raises:
        ValueError: 两个 classification 不是同一 target 时抛出。
    """

    if first.status is SourceIntegrityStatus.UNSAFE or second.status is SourceIntegrityStatus.UNSAFE:
        raise ValueError("UNSAFE source classification 不得比较 publication identity")
    if (
        first.ticker != second.ticker
        or first.source_kind is not second.source_kind
        or first.document_id != second.document_id
    ):
        raise ValueError("只能比较同一 source target 的 publication identity")
    return first.revision == second.revision


def classify_source_integrity_preflight(
    inventory: tuple[SourceIntegrityClassification, ...],
    *,
    accepted_filing_ids: frozenset[str],
    rejected_filing_ids: frozenset[str],
) -> SourceIntegrityPreflightDisposition:
    """从完整 inventory 与最终 selection 纯计算 repair disposition。

    Args:
        inventory: 同一 publication guard 下取得的完整 ticker inventory。
        accepted_filing_ids: workflow 最终接受的 filing ID 集合。
        rejected_filing_ids: workflow 已知不会发布的 filing ID 集合。

    Returns:
        clean 或唯一 selected repair target。

    Raises:
        SourceIntegrityPreflightError: corruption 无法由本次请求唯一、安全修复时抛出。
    """

    if any(item.status is SourceIntegrityStatus.UNSAFE for item in inventory):
        raise SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSAFE_PUBLICATION)
    repair_targets = tuple(item for item in inventory if item.status is SourceIntegrityStatus.REPAIR_REQUIRED)
    if len(repair_targets) > 1:
        raise SourceIntegrityPreflightError(SourceIntegrityPreflightReason.MULTIPLE_REPAIR_REQUIRED)
    if not repair_targets:
        return NoSourceRepairRequired()

    target = repair_targets[0]
    if target.source_kind is not SourceKind.FILING or (
        target.document_id not in accepted_filing_ids and target.document_id not in rejected_filing_ids
    ):
        raise SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED)
    if target.document_id in rejected_filing_ids:
        raise SourceIntegrityPreflightError(SourceIntegrityPreflightReason.SELECTED_REJECTED_REPAIR_REQUIRED)
    return SelectedSourceRepairRequired(target=target)
