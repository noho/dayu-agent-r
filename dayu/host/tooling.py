"""Host 工具装配输入边界。

本模块只定义 Host construction / composition root 接收业务
``ToolBundle`` 时使用的 typed options。它不实现工具发现、业务工具扫描、
ToolRuntime factory、framework tool 注入、policy provider 解析或 durable
tool snapshot。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from dayu.contracts.tool_declaration import ToolBundle
from dayu.contracts.tool_source import ToolBundleSourceRef
from dayu.host.tool_duplicate_governance import DuplicateGovernancePolicy

if TYPE_CHECKING:
    from dayu.host.wait_adapter import (
        WaitActivationRegistry,
        WaitAdapterRegistry,
        WaitPollAdapterRegistry,
    )


class FrameworkToolName(StrEnum):
    """Host / ToolRuntime 预留的 framework tool 名称。"""

    FETCH_MORE = "fetch_more"


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

        if not self.enabled_framework_tools.issubset(self.reserved_framework_tool_names):
            raise ValueError(
                "FrameworkToolPolicyView.enabled_framework_tools must be a" " subset of reserved_framework_tool_names"
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
    :param wait_adapter_registry: 可选等待 adapter registry；仅用于本地
        ToolRuntime awaiting production wiring，不进入 durable row 或 per-run request。
    :param wait_activation_registry: 可选 accepted wait activation registry；仅用于
        ToolRuntime 在 Host durable accept ack 后触发 provider 内部 activation。
    :param wait_poll_adapter_registry: 可选 wait poll adapter registry；仅用于
        ``open_host`` production wait poller runtime，不进入 durable row 或 per-run request。
    :param duplicate_governance_policy: ToolRuntime duplicate governance typed
        policy；生产 dispatch 会传入每个 Attempt 的 ToolRuntime。
    """

    business_tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    framework_tool_policy: FrameworkToolPolicyView = field(default_factory=default_framework_tool_policy_view)
    wait_adapter_registry: WaitAdapterRegistry | None = None
    wait_activation_registry: WaitActivationRegistry | None = None
    wait_poll_adapter_registry: WaitPollAdapterRegistry | None = None
    duplicate_governance_policy: DuplicateGovernancePolicy = field(
        default_factory=DuplicateGovernancePolicy
    )

    def __post_init__(self) -> None:
        """校验 Host 工具输入选项。

        :returns: 无返回值。
        :raises ValueError: ``source_refs`` 为空，或业务工具名占用预留
            framework tool 名称，或 duplicate governance policy 类型非法时抛出。
        """

        if not self.source_refs:
            raise ValueError("HostToolingOptions.source_refs must be non-empty")
        if not isinstance(
            self.duplicate_governance_policy, DuplicateGovernancePolicy
        ):
            raise ValueError(
                "HostToolingOptions.duplicate_governance_policy must be "
                "DuplicateGovernancePolicy"
            )
        reserved_names = frozenset(
            tool_name.value for tool_name in self.framework_tool_policy.reserved_framework_tool_names
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
    "default_framework_tool_policy_view",
]
