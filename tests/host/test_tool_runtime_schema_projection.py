"""ToolRuntime schema projection helper 直接测试。"""

from __future__ import annotations

from collections.abc import Mapping

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
from dayu.host.tool_runtime_schema_projection import (
    business_bundle_digest,
    definitions_by_name,
    tool_schemas_digest,
    tool_schema_json,
    validate_reserved_name_conflicts,
)
from dayu.host.tooling import FrameworkToolName, default_framework_tool_policy_view


async def _noop_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用工具 callable。

    :param call: 工具调用请求。
    :param context: 执行上下文。
    :returns: 取消 outcome。
    """

    del call, context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="tool disabled in test",
        hint=None,
        meta=None,
    )


def _parameters() -> ToolParametersSchema:
    """构造测试用参数 schema。

    :returns: 工具参数 schema。
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
        callable=_noop_tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=(),
    )


def test_valid_projection_indexes_definitions_and_digests_schema() -> None:
    """有效工具声明可稳定投影为 name index 与 schema digest。"""

    first = _definition("alpha")
    second = _definition("beta")
    bundle = ToolBundle(definitions=(first, second))

    by_name = definitions_by_name([first, second])
    bundle_digest = business_bundle_digest(bundle)
    schema_digest = tool_schemas_digest(bundle.to_tool_schemas())

    assert by_name == {"alpha": first, "beta": second}
    assert bundle_digest.startswith("sha256:")
    assert schema_digest.startswith("sha256:")
    schema_json = tool_schema_json(first.schema)
    assert isinstance(schema_json, Mapping)
    function_json = schema_json["function"]
    assert isinstance(function_json, Mapping)
    assert function_json["name"] == "alpha"


def test_definitions_by_name_rejects_duplicate_names() -> None:
    """effective definitions name index 拒绝重复工具名。"""

    first = _definition("duplicate")
    second = _definition("duplicate")

    with pytest.raises(ValueError, match="duplicate effective tool name"):
        definitions_by_name([first, second])


def test_reserved_name_conflict_rejects_framework_tool_name() -> None:
    """业务工具不得占用 framework reserved name。"""

    bundle = ToolBundle(
        definitions=(_definition(FrameworkToolName.FETCH_MORE.value),)
    )

    with pytest.raises(ValueError, match="reserved framework tool name"):
        validate_reserved_name_conflicts(
            bundle,
            default_framework_tool_policy_view(),
        )
