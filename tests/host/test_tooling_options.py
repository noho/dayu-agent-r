"""Host construction 工具输入选项测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from enum import StrEnum
from typing import Protocol, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts import (
    ToolBundleSourceKind as ContractToolBundleSourceKind,
)
from dayu.contracts import (
    ToolBundleSourceRef as ContractToolBundleSourceRef,
)
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    HostToolingOptions,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    default_framework_tool_policy_view,
)


class _DataclassParams(Protocol):
    """测试中读取 dataclass 参数所需的最小协议。"""

    frozen: bool


class _FrozenDataclassClass(Protocol):
    """测试中读取 frozen dataclass 类属性所需的最小协议。"""

    __dataclass_params__: _DataclassParams


async def _noop_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用单工具 callable。

    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 一个不会实际执行业务逻辑的取消 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call
    del context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="tool disabled in test",
        hint=None,
        meta=None,
    )


def _parameters() -> ToolParametersSchema:
    """构造测试用空参数 schema。

    :returns: 工具参数 schema。
    :raises Exception: 不主动抛出异常。
    """

    properties: dict[str, JsonValue] = {}
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=(),
        additional_properties=False,
    )


def _definition(name: str) -> ToolDefinition:
    """构造测试用工具声明。

    :param name: 工具名。
    :returns: 对应 ``ToolDefinition``。
    :raises ValueError: 工具声明名称与 schema 名称不一致时抛出。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} test tool",
                parameters=_parameters(),
            ),
        ),
        callable=_noop_tool,
        truncate=None,
        display=None,
        tags=(),
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造测试用工具来源引用。

    :returns: ``ToolBundleSourceRef``。
    :raises ValueError: 来源引用字段为空时抛出。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="test-provider",
    )


def test_tooling_enums_are_str_enum_with_stable_values() -> None:
    """tooling 枚举必须使用 ``StrEnum`` 并保持设计真源取值。"""

    assert issubclass(ToolBundleSourceKind, StrEnum)
    assert issubclass(FrameworkToolName, StrEnum)
    assert {item.name: item.value for item in ToolBundleSourceKind} == {
        "EXPLICIT_PROVIDER": "explicit_provider",
        "CONFIG_BINDING": "config_binding",
        "PACKAGE_ENTRYPOINT": "package_entrypoint",
        "SERVICE_COMPOSITION": "service_composition",
    }
    assert FrameworkToolName.FETCH_MORE.value == "fetch_more"


def test_host_source_ref_exports_are_canonical_contracts() -> None:
    """Host 包根导出的 source ref 类型必须直接来自 ``dayu.contracts``。"""

    assert ToolBundleSourceKind is ContractToolBundleSourceKind
    assert ToolBundleSourceRef is ContractToolBundleSourceRef


def test_default_framework_tool_policy_view_reserves_fetch_more_only() -> None:
    """默认 policy view 预留 ``fetch_more``，但默认不启用 framework tool。"""

    first = default_framework_tool_policy_view()
    second = default_framework_tool_policy_view()

    assert first is not second
    assert first.reserved_framework_tool_names == frozenset({FrameworkToolName.FETCH_MORE})
    assert first.enabled_framework_tools == frozenset()
    assert first.reserved_framework_tool_names is not second.reserved_framework_tool_names
    assert first.enabled_framework_tools is not second.enabled_framework_tools


def test_framework_tool_policy_view_is_frozen_and_uses_frozensets() -> None:
    """framework tool policy view 必须 frozen，字段值必须是 frozenset。"""

    policy = default_framework_tool_policy_view()
    policy_view_type = cast(_FrozenDataclassClass, FrameworkToolPolicyView)

    assert is_dataclass(FrameworkToolPolicyView)
    assert policy_view_type.__dataclass_params__.frozen is True
    assert isinstance(policy.reserved_framework_tool_names, frozenset)
    assert isinstance(policy.enabled_framework_tools, frozenset)
    with pytest.raises(FrozenInstanceError):
        policy.__setattr__("enabled_framework_tools", frozenset())


def test_enabled_framework_tools_must_be_reserved_subset() -> None:
    """启用的 framework tool 必须属于预留名称集合。"""

    with pytest.raises(ValueError, match="enabled_framework_tools"):
        FrameworkToolPolicyView(
            reserved_framework_tool_names=frozenset(),
            enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
        )


def test_tool_bundle_source_ref_rejects_empty_strings() -> None:
    """来源引用必须拒绝空 source id 与空 optional 字符串。"""

    with pytest.raises(ValueError, match="source_id"):
        ToolBundleSourceRef(
            source_kind=ToolBundleSourceKind.CONFIG_BINDING,
            source_id=" ",
        )
    with pytest.raises(ValueError, match="version_ref"):
        ToolBundleSourceRef(
            source_kind=ToolBundleSourceKind.CONFIG_BINDING,
            source_id="config-1",
            version_ref=" ",
        )
    with pytest.raises(ValueError, match="content_digest"):
        ToolBundleSourceRef(
            source_kind=ToolBundleSourceKind.CONFIG_BINDING,
            source_id="config-1",
            content_digest=" ",
        )


def test_host_tooling_options_requires_source_refs() -> None:
    """Host tooling options 必须携带至少一个来源引用。"""

    with pytest.raises(ValueError, match="source_refs"):
        HostToolingOptions(
            business_tool_bundle=ToolBundle(definitions=()),
            source_refs=(),
        )


def test_host_tooling_options_rejects_reserved_framework_tool_name() -> None:
    """业务 ``ToolBundle`` 不得占用预留 framework tool 名称。"""

    with pytest.raises(ValueError, match="fetch_more"):
        HostToolingOptions(
            business_tool_bundle=ToolBundle(definitions=(_definition(FrameworkToolName.FETCH_MORE.value),)),
            source_refs=(_source_ref(),),
        )


def test_host_tooling_options_accepts_normal_business_bundle() -> None:
    """普通业务 ``ToolBundle`` 可以作为 Host construction typed input。"""

    options = HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
        source_refs=(_source_ref(),),
    )

    assert options.business_tool_bundle.to_tool_schemas()[0].function.name == ("lookup_filing")
    assert options.source_refs == (_source_ref(),)
    assert options.framework_tool_policy == default_framework_tool_policy_view()
    assert cast(tuple[str, ...], options.__slots__) != ()
