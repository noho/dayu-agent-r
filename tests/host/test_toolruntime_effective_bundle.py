"""Host ToolRuntime effective bundle 装配测试。"""

from __future__ import annotations

from dataclasses import is_dataclass

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
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
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    FetchMoreToolCallable,
    ToolRuntimeHandle,
    ToolRuntimeBuildRequest,
    ToolRuntimeUnsupportedExecutor,
)
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    default_framework_tool_policy_view,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_POLICY_DIGEST = "sha256:1111111111111111111111111111111111111111111111111111111111111111"


async def _lookup_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用业务工具 callable。

    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 测试用取消 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call, context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="test callable was not expected to execute",
        hint=None,
        meta=None,
    )


def test_business_bundle_projects_schema_and_callable_from_same_bundle() -> None:
    """普通业务工具 schema 与 callable 必须来自同一个 effective bundle。"""

    definition = _definition("lookup_filing")
    factory = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())

    handle = factory.create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=(definition,)),
                source_refs=(_source_ref(),),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=_POLICY_DIGEST,
            )
        )
    )

    assert is_dataclass(handle.effective_bundle)
    assert handle.tool_schemas == handle.effective_bundle.tool_schemas
    assert handle.tool_schemas[0].function.name == "lookup_filing"
    assert (
        handle.effective_bundle.definitions_by_name["lookup_filing"].callable
        is _lookup_tool
    )
    assert isinstance(handle.tool_executor, ToolRuntimeUnsupportedExecutor)
    assert handle.tool_executor.effective_bundle is handle.effective_bundle
    assert handle.effective_bundle.business_bundle_digest.startswith("sha256:")
    assert handle.effective_bundle.effective_schema_digest.startswith("sha256:")
    assert handle.effective_bundle.policy_snapshot_digest == _POLICY_DIGEST


def test_business_bundle_defining_fetch_more_is_rejected() -> None:
    """业务 ToolBundle 定义 ``fetch_more`` 时 builder 必须拒绝。"""

    builder = EffectiveToolBundleBuilder()

    with pytest.raises(ValueError, match="fetch_more"):
        builder.build(
            EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition(FrameworkToolName.FETCH_MORE.value),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=None,
            )
        )


def test_disabled_framework_tools_do_not_inject_fetch_more() -> None:
    """未启用 framework tool 时不会注入 ``fetch_more``。"""

    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition("lookup_filing"),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=FrameworkToolPolicyView(
                    reserved_framework_tool_names=frozenset(
                        {FrameworkToolName.FETCH_MORE}
                    ),
                    enabled_framework_tools=frozenset(),
                ),
                policy_snapshot_digest=None,
            )
        )
    )

    assert FrameworkToolName.FETCH_MORE not in (
        handle.effective_bundle.injected_framework_tool_names
    )
    assert "fetch_more" not in handle.effective_bundle.definitions_by_name
    assert tuple(schema.function.name for schema in handle.tool_schemas) == (
        "lookup_filing",
    )


def test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled() -> None:
    """启用 truncation manager 时 ``fetch_more`` schema 与 callable 同源注入。"""

    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition("lookup_filing"),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=FrameworkToolPolicyView(
                    reserved_framework_tool_names=frozenset(
                        {FrameworkToolName.FETCH_MORE}
                    ),
                    enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
                ),
                policy_snapshot_digest=None,
                enable_truncation_manager=True,
            )
        )
    )

    assert FrameworkToolName.FETCH_MORE in (
        handle.effective_bundle.injected_framework_tool_names
    )
    assert tuple(schema.function.name for schema in handle.tool_schemas) == (
        "lookup_filing",
        "fetch_more",
    )
    fetch_more = handle.effective_bundle.definitions_by_name["fetch_more"]
    assert fetch_more.schema is handle.tool_schemas[1]
    assert isinstance(fetch_more.callable, FetchMoreToolCallable)
    assert fetch_more.callable is handle.effective_bundle.fetch_more_callable


def test_enabled_fetch_more_policy_without_truncation_does_not_inject() -> None:
    """未启用 truncation manager 时即使 policy 启用也不注入 ``fetch_more``。"""

    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition("lookup_filing"),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=FrameworkToolPolicyView(
                    reserved_framework_tool_names=frozenset(
                        {FrameworkToolName.FETCH_MORE}
                    ),
                    enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
                ),
                policy_snapshot_digest=None,
                enable_truncation_manager=False,
            )
        )
    )

    assert FrameworkToolName.FETCH_MORE not in (
        handle.effective_bundle.injected_framework_tool_names
    )
    assert "fetch_more" not in handle.effective_bundle.definitions_by_name


def test_factory_creates_attempt_local_fetch_more_callable() -> None:
    """factory 每次构造 attempt-local effective bundle 与 fetch_more callable。

    :returns: ``None``。
    :raises AssertionError: ``fetch_more`` callable 被跨 attempt 复用或污染
        business bundle 时抛出。
    """

    first_handle = _fetch_more_enabled_handle()
    second_handle = _fetch_more_enabled_handle()

    assert first_handle.effective_bundle is not second_handle.effective_bundle
    assert (
        first_handle.effective_bundle.fetch_more_callable
        is not second_handle.effective_bundle.fetch_more_callable
    )
    assert first_handle.effective_bundle.fetch_more_callable is (
        first_handle.effective_bundle.definitions_by_name["fetch_more"].callable
    )
    assert second_handle.effective_bundle.fetch_more_callable is (
        second_handle.effective_bundle.definitions_by_name["fetch_more"].callable
    )
    assert first_handle.effective_bundle.business_bundle is not (
        second_handle.effective_bundle.business_bundle
    )
    assert "fetch_more" not in {
        definition.name
        for definition in first_handle.effective_bundle.business_bundle.definitions
    }
    assert "fetch_more" not in {
        definition.name
        for definition in second_handle.effective_bundle.business_bundle.definitions
    }


def _fetch_more_enabled_handle() -> ToolRuntimeHandle:
    """构造启用 ``fetch_more`` 的 attempt-local ToolRuntime handle。

    :returns: 启用截断 manager 与 ``fetch_more`` framework tool 的 handle。
    :raises Exception: ToolRuntime 构造过程透传异常。
    """

    return DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition("lookup_filing"),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=FrameworkToolPolicyView(
                    reserved_framework_tool_names=frozenset(
                        {FrameworkToolName.FETCH_MORE}
                    ),
                    enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
                ),
                policy_snapshot_digest=None,
                enable_truncation_manager=True,
            )
        )
    )


def _parameters() -> ToolParametersSchema:
    """构造测试用参数 schema。

    :returns: 工具参数 schema。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {"type": "string"},
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _definition(name: str) -> ToolDefinition:
    """构造测试用工具声明。

    :param name: 工具名。
    :returns: 工具声明。
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
        callable=_lookup_tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=("test",),
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造测试用来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="test-provider",
    )
