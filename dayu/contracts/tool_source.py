"""工具 bundle 来源引用公共契约。

本模块承载跨 Host、runtime assembly、diagnostic、audit 与后续 snapshot
refs 共享的工具来源引用类型。来源引用只解释业务 ``ToolBundle`` 的来源、
版本与内容摘要；它不携带 callable、provider adapter、权限、lease、
fencing 或 Host truth。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dayu.contracts._validation import (
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
)


class ToolBundleSourceKind(StrEnum):
    """业务工具 bundle 来源类别。

    枚举值只描述工具 bundle 的可解释来源，不携带 provider、callable 或
    具体业务模块对象。
    """

    EXPLICIT_PROVIDER = "explicit_provider"
    CONFIG_BINDING = "config_binding"
    PACKAGE_ENTRYPOINT = "package_entrypoint"
    SERVICE_COMPOSITION = "service_composition"


@dataclass(frozen=True, slots=True)
class ToolBundleSourceRef:
    """业务 ``ToolBundle`` 的来源引用。

    :param source_kind: 来源类别。
    :param source_id: 来源标识，例如 provider id、配置绑定名或入口点名。
    :param version_ref: 可选版本引用；无版本时为 ``None``。
    :param content_digest: 可选内容摘要；无摘要时为 ``None``。
    """

    source_kind: ToolBundleSourceKind
    source_id: str
    version_ref: str | None = None
    content_digest: str | None = None

    def __post_init__(self) -> None:
        """校验来源引用的最小完整性。

        :returns: 无返回值。
        :raises TypeError: ``source_kind`` 类型非法时抛出。
        :raises ValueError: ``source_id`` 为空，或可选字符串存在但为空时抛出。
        """

        if not isinstance(self.source_kind, ToolBundleSourceKind):
            raise TypeError(
                "ToolBundleSourceRef.source_kind must be ToolBundleSourceKind"
            )
        _require_non_empty_text(self.source_id, field_name="ToolBundleSourceRef.source_id")
        _require_optional_non_empty_text(self.version_ref, field_name="ToolBundleSourceRef.version_ref")
        _require_optional_non_empty_text(
            self.content_digest,
            field_name="ToolBundleSourceRef.content_digest",
        )

__all__ = ["ToolBundleSourceKind", "ToolBundleSourceRef"]
