"""既有 filing source 自动修复授权的共享不可变契约。"""

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
    """声明本次上传不包含既有 source 自动修复授权。

    Attributes:
        kind: 稳定 typed discriminator。
    """

    kind: Literal["not_required"] = "not_required"

    def __post_init__(self) -> None:
        """校验 no-repair discriminator。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: discriminator 不是唯一允许值时抛出。
        """

        if self.kind != "not_required":
            raise ValueError("no-repair kind 必须是 not_required")


@dataclass(frozen=True, slots=True)
class ExistingSourceAutoRepair:
    """授权修复一个已有且具有可信 revision 的 filing source。

    Attributes:
        expected_integrity: validator 读取的 exact published target 完整性事实。
        kind: 稳定 typed discriminator。
    """

    expected_integrity: SourceIntegrityClassification
    kind: Literal["existing_source_auto_repair"] = "existing_source_auto_repair"

    def __post_init__(self) -> None:
        """校验授权目标是可比较的既有 filing repair target。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: expected integrity 类型不符合契约时抛出。
            ValueError: discriminator、source kind、状态或 revision 不符合契约时抛出。
        """

        if not isinstance(self.expected_integrity, SourceIntegrityClassification):
            raise TypeError("expected_integrity 必须是 SourceIntegrityClassification")
        if self.kind != "existing_source_auto_repair":
            raise ValueError("auto-repair kind 必须是 existing_source_auto_repair")
        if (
            self.expected_integrity.source_kind is not SourceKind.FILING
            or self.expected_integrity.status is not SourceIntegrityStatus.REPAIR_REQUIRED
            or self.expected_integrity.revision is None
        ):
            raise ValueError("existing source auto repair 必须引用 REPAIR_REQUIRED filing")


ExistingSourceRepairDisposition: TypeAlias = (
    NoExistingSourceRepair | ExistingSourceAutoRepair
)
"""既有 source repair disposition 的封闭联合。"""


__all__ = [
    "ExistingSourceAutoRepair",
    "ExistingSourceRepairDisposition",
    "NoExistingSourceRepair",
]
