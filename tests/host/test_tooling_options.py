"""Host construction 工具输入选项测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from enum import StrEnum
from typing import Protocol, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
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
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    HostToolingOptions,
    ProcessCapsuleInterruptPolicy,
    default_framework_tool_policy_view,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateDecisionKind,
    DuplicateGovernanceMessages,
    DuplicateGovernancePolicy,
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
        execution=AsyncDirectToolExecutionCapability(),
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


def test_framework_tool_name_is_str_enum_with_stable_values() -> None:
    """framework tooling 枚举必须使用 ``StrEnum`` 并保持设计真源取值。"""

    assert issubclass(FrameworkToolName, StrEnum)
    assert FrameworkToolName.FETCH_MORE.value == "fetch_more"


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
            business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
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
    assert isinstance(options.duplicate_governance_policy, DuplicateGovernancePolicy)
    assert isinstance(
        options.process_capsule_interrupt_policy,
        ProcessCapsuleInterruptPolicy,
    )
    assert options.process_capsule_interrupt_policy == ProcessCapsuleInterruptPolicy()
    assert isinstance(
        options.duplicate_governance_policy.messages,
        DuplicateGovernanceMessages,
    )
    assert options.duplicate_governance_policy.messages.reuse.strip() != ""
    assert cast(tuple[str, ...], options.__slots__) != ()


def test_duplicate_governance_policy_zero_config_uses_default_messages() -> None:
    """零配置 duplicate policy 必须通过 default_factory 获得非空消息。"""

    first = DuplicateGovernancePolicy()
    second = DuplicateGovernancePolicy()

    assert first.default_duplicate_decision is DuplicateDecisionKind.HINT
    assert first.messages is not second.messages
    assert first.messages.allow.strip() != ""
    assert first.messages.reuse.strip() != ""
    assert first.messages.hint.strip() != ""
    assert first.messages.require_justification.strip() != ""
    assert first.messages.hard_stop.strip() != ""
    assert first.messages.attempt_scope_diagnostic.strip() != ""
    assert first.messages.prior_accept_missing.strip() != ""


def test_host_tooling_options_accepts_custom_duplicate_messages() -> None:
    """Host tooling options 必须保留调用方传入的 duplicate 消息 policy。"""

    messages = DuplicateGovernanceMessages(
        allow="allow custom duplicate request",
        reuse="reuse custom accepted result",
        hint="hint custom duplicate evidence",
        require_justification="require custom justification",
        hard_stop="hard stop custom duplicate request",
        attempt_scope_diagnostic="attempt custom duplicate diagnostic",
        prior_accept_missing="prior custom accepted result missing",
    )
    policy = DuplicateGovernancePolicy(messages=messages)
    options = HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
        source_refs=(_source_ref(),),
        duplicate_governance_policy=policy,
    )

    assert options.duplicate_governance_policy is policy
    assert options.duplicate_governance_policy.messages.reuse == (
        "reuse custom accepted result"
    )


def test_duplicate_governance_messages_map_all_decision_kinds() -> None:
    """duplicate governance messages 必须显式覆盖所有决策类别。"""

    messages = DuplicateGovernanceMessages(
        allow="allow message",
        reuse="reuse message",
        hint="hint message",
        require_justification="require justification message",
        hard_stop="hard stop message",
        attempt_scope_diagnostic="attempt diagnostic message",
        prior_accept_missing="prior accept missing message",
    )

    assert messages.message_for(DuplicateDecisionKind.ALLOW) == "allow message"
    assert messages.message_for(DuplicateDecisionKind.REUSE) == "reuse message"
    assert messages.message_for(DuplicateDecisionKind.HINT) == "hint message"
    assert (
        messages.message_for(DuplicateDecisionKind.REQUIRE_JUSTIFICATION)
        == "require justification message"
    )
    assert messages.message_for(DuplicateDecisionKind.HARD_STOP) == "hard stop message"
    assert (
        messages.message_for(DuplicateDecisionKind.DURABLE_MISSING)
        == "prior accept missing message"
    )


def test_host_tooling_options_accepts_custom_duplicate_justification_name() -> None:
    """Host tooling options 必须保留 duplicate justification 参数名配置。"""

    policy = DuplicateGovernancePolicy(
        default_duplicate_decision=DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
        justification_argument_names_by_tool_name={
            "lookup_filing": "duplicate_reason"
        },
    )
    options = HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
        source_refs=(_source_ref(),),
        duplicate_governance_policy=policy,
    )

    assert options.duplicate_governance_policy.default_duplicate_decision is (
        DuplicateDecisionKind.REQUIRE_JUSTIFICATION
    )
    assert (
        options.duplicate_governance_policy.justification_argument_names_by_tool_name[
            "lookup_filing"
        ]
        == "duplicate_reason"
    )


def test_duplicate_governance_policy_rejects_empty_messages_and_argument_names() -> None:
    """duplicate policy 必须拒绝空消息和空 justification 参数名。"""

    with pytest.raises(ValueError, match="reuse"):
        DuplicateGovernanceMessages(reuse=" ")
    with pytest.raises(ValueError, match="argument_name"):
        DuplicateGovernancePolicy(
            justification_argument_names_by_tool_name={"lookup_filing": " "}
        )
    with pytest.raises(ValueError, match="tool_name"):
        DuplicateGovernancePolicy(
            justification_argument_names_by_tool_name={" ": "duplicate_reason"}
        )


def test_host_tooling_options_rejects_invalid_duplicate_policy_type() -> None:
    """Host tooling options 必须拒绝非 typed duplicate policy 对象。"""

    with pytest.raises(ValueError, match="duplicate_governance_policy"):
        HostToolingOptions(
            business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
            source_refs=(_source_ref(),),
            duplicate_governance_policy=cast(
                DuplicateGovernancePolicy,
                "invalid-policy",
            ),
        )


def test_process_capsule_interrupt_policy_accepts_zero_and_positive_grace() -> None:
    """process capsule cleanup policy 接受有限非负 grace 数值。"""

    policy = ProcessCapsuleInterruptPolicy(
        terminate_grace_seconds=0.0,
        kill_grace_seconds=1.25,
    )

    assert policy.terminate_grace_seconds == 0.0
    assert policy.kill_grace_seconds == 1.25


def test_host_tooling_options_accepts_custom_process_capsule_policy() -> None:
    """HostToolingOptions 必须保留调用方传入的 process capsule cleanup policy。"""

    policy = ProcessCapsuleInterruptPolicy(
        terminate_grace_seconds=0.3,
        kill_grace_seconds=0.4,
    )
    options = HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
        source_refs=(_source_ref(),),
        process_capsule_interrupt_policy=policy,
    )

    assert options.process_capsule_interrupt_policy is policy


@pytest.mark.parametrize(
    ("value", "expected_error"),
    (
        (cast(float, True), TypeError),
        (-0.1, ValueError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (float("-inf"), ValueError),
    ),
)
def test_process_capsule_interrupt_policy_rejects_invalid_grace(
    value: float,
    expected_error: type[Exception],
) -> None:
    """process capsule cleanup policy 拒绝 bool、负数、NaN 与无穷。"""

    with pytest.raises(expected_error):
        ProcessCapsuleInterruptPolicy(
            terminate_grace_seconds=value,
            kill_grace_seconds=0.2,
        )
    with pytest.raises(expected_error):
        ProcessCapsuleInterruptPolicy(
            terminate_grace_seconds=0.2,
            kill_grace_seconds=value,
        )


def test_host_tooling_options_rejects_invalid_process_capsule_policy_type() -> None:
    """HostToolingOptions 必须拒绝非 typed process capsule cleanup policy。"""

    with pytest.raises(ValueError, match="process_capsule_interrupt_policy"):
        HostToolingOptions(
            business_tool_bundle=ToolBundle(definitions=(_definition("lookup_filing"),)),
            source_refs=(_source_ref(),),
            process_capsule_interrupt_policy=cast(
                ProcessCapsuleInterruptPolicy,
                "invalid-policy",
            ),
        )
