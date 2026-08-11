"""源文档物理完整性与跨 provider 预检的 typed contract。"""

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


class SourceIntegrityReason(str, Enum):
    """结构合法 source 需要修复的物理原因。"""

    PHYSICAL_FILE_MISSING = "physical_file_missing"
    SIZE_MISMATCH = "size_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"


@dataclass(frozen=True, slots=True)
class SourceIntegrityClassification:
    """单个 published 或 staged source 的可比较完整性身份。

    Attributes:
        ticker: exact external ticker。
        source_kind: filing 或 material。
        document_id: exact external document ID。
        revision: 已存在 source 的 opaque revision；目标不存在时为 ``None``。
        status: 封闭完整性状态。
        reasons: 需要修复时的去重、有序物理原因。
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

        if self.status is SourceIntegrityStatus.MISSING:
            if self.revision is not None or self.reasons:
                raise ValueError("MISSING classification 不得携带 revision 或 repair reasons")
            return
        if self.revision is None:
            raise ValueError("已存在 source classification 必须携带 revision")
        if self.status is SourceIntegrityStatus.COMPLETE:
            if self.reasons:
                raise ValueError("COMPLETE classification 不得携带 repair reasons")
            return
        if not self.reasons:
            raise ValueError("REPAIR_REQUIRED classification 必须携带 repair reasons")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("repair reasons 不得重复")


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
    """目标 publication identity 连续变化超过允许轮次。"""

    def __init__(self) -> None:
        """构造不泄漏 revision 或路径的冲突异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("source publication identity 连续变化，无法安全应用预取结果")


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
