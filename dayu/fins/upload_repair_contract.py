"""既有 filing source 自动修复的共享 immutable contract。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage.source_integrity import (
    SourceIntegrityClassification,
    SourceIntegrityStatus,
)


@dataclass(frozen=True, slots=True)
class NoExistingSourceRepair:
    """本次 filing 上传不需要修复既有 source。"""

    kind: Literal["not_required"] = "not_required"


@dataclass(frozen=True, slots=True)
class ExistingSourceAutoRepair:
    """validator 授权的既有 filing source 自动修复。

    Attributes:
        expected_integrity: Phase A 读取的 exact repair-required filing 状态。
        kind: immutable union discriminator。
    """

    expected_integrity: SourceIntegrityClassification
    kind: Literal["existing_source_auto_repair"] = "existing_source_auto_repair"

    def __post_init__(self) -> None:
        """校验 expected integrity 可作为 filing repair authority。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: expected integrity 不是携带可信 revision 的待修复 filing 时抛出。
        """

        if (
            self.expected_integrity.source_kind is not SourceKind.FILING
            or self.expected_integrity.status is not SourceIntegrityStatus.REPAIR_REQUIRED
            or self.expected_integrity.revision is None
        ):
            raise ValueError("existing source auto repair 必须引用 REPAIR_REQUIRED filing")


ExistingSourceRepairDisposition: TypeAlias = NoExistingSourceRepair | ExistingSourceAutoRepair
"""既有 source repair disposition 的封闭联合。"""


__all__ = [
    "ExistingSourceAutoRepair",
    "ExistingSourceRepairDisposition",
    "NoExistingSourceRepair",
]
