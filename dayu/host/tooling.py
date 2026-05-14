"""Host 工具装配输入边界。

本模块只定义 Host construction / composition root 接收业务
``ToolBundle`` 时使用的 typed options。它不实现工具发现、业务工具扫描、
ToolRuntime factory、framework tool 注入、policy provider 解析或 durable
tool snapshot。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from dayu.contracts.tool_declaration import ToolBundle


def _require_non_empty(value: str, *, field_name: str) -> None:
    """校验必填字符串字段非空。

    :param value: 待校验的字符串值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: 字符串为空或仅包含空白字符时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(
    value: str | None, *, field_name: str
) -> None:
    """校验可选字符串字段在存在时非空。

    :param value: 待校验的可选字符串值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: 字符串存在但为空或仅包含空白字符时抛出。
    """

    if value is not None:
        _require_non_empty(value, field_name=field_name)


class ToolBundleSourceKind(StrEnum):
    """业务工具 bundle 来源类别。

    枚举值只描述 Host construction 输入的可解释来源，不携带 provider、
    callable 或具体业务模块对象。
    """

    EXPLICIT_PROVIDER = "explicit_provider"
    CONFIG_BINDING = "config_binding"
    PACKAGE_ENTRYPOINT = "package_entrypoint"
    SERVICE_COMPOSITION = "service_composition"


class FrameworkToolName(StrEnum):
    """Host / ToolRuntime 预留的 framework tool 名称。"""

    FETCH_MORE = "fetch_more"


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
        :raises ValueError: ``source_id`` 为空，或可选字符串存在但为空时抛出。
        """

        _require_non_empty(
            self.source_id, field_name="ToolBundleSourceRef.source_id"
        )
        _require_optional_non_empty(
            self.version_ref, field_name="ToolBundleSourceRef.version_ref"
        )
        _require_optional_non_empty(
            self.content_digest,
            field_name="ToolBundleSourceRef.content_digest",
        )


@dataclass(frozen=True, slots=True)
class FrameworkToolPolicyView:
    """Host construction 期的 framework tool policy view。

    :param reserved_framework_tool_names: Host / ToolRuntime 预留名称集合。
    :param enabled_framework_tools: 当前 construction 允许后续注入的
        framework tool 集合；Phase 1 默认为空。
    """

    reserved_framework_tool_names: frozenset[FrameworkToolName]
    enabled_framework_tools: frozenset[FrameworkToolName]

    def __post_init__(self) -> None:
        """校验 framework tool policy view。

        :returns: 无返回值。
        :raises ValueError: 启用集合不是预留集合子集时抛出。
        """

        if not self.enabled_framework_tools.issubset(
            self.reserved_framework_tool_names
        ):
            raise ValueError(
                "FrameworkToolPolicyView.enabled_framework_tools must be a"
                " subset of reserved_framework_tool_names"
            )


def default_framework_tool_policy_view() -> FrameworkToolPolicyView:
    """返回默认 framework tool policy view。

    默认预留 ``fetch_more``，但不启用任何 framework tool。每次调用都返回
    新的 frozen view 实例，不暴露可变共享状态。

    :returns: 默认 ``FrameworkToolPolicyView``。
    :raises ValueError: 默认集合违反 policy view 校验时抛出。
    """

    return FrameworkToolPolicyView(
        reserved_framework_tool_names=frozenset({FrameworkToolName.FETCH_MORE}),
        enabled_framework_tools=frozenset(),
    )


@dataclass(frozen=True, slots=True)
class HostToolingOptions:
    """Host construction 的业务工具输入选项。

    :param business_tool_bundle: 外部装配好的业务 ``ToolBundle``。
    :param source_refs: 解释业务工具来源的引用集合，必须非空。
    :param framework_tool_policy: framework tool 预留名与启用集合视图。
    """

    business_tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    framework_tool_policy: FrameworkToolPolicyView = field(
        default_factory=default_framework_tool_policy_view
    )

    def __post_init__(self) -> None:
        """校验 Host 工具输入选项。

        :returns: 无返回值。
        :raises ValueError: ``source_refs`` 为空，或业务工具名占用预留
            framework tool 名称时抛出。
        """

        if not self.source_refs:
            raise ValueError("HostToolingOptions.source_refs must be non-empty")
        reserved_names = frozenset(
            tool_name.value
            for tool_name in self.framework_tool_policy.reserved_framework_tool_names
        )
        for definition in self.business_tool_bundle.definitions:
            if definition.name in reserved_names:
                raise ValueError(
                    "HostToolingOptions.business_tool_bundle contains reserved"
                    f" framework tool name: {definition.name}"
                )


__all__ = [
    "FrameworkToolName",
    "FrameworkToolPolicyView",
    "HostToolingOptions",
    "ToolBundleSourceKind",
    "ToolBundleSourceRef",
    "default_framework_tool_policy_view",
]
