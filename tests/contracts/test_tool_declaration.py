"""P5 工具声明契约测试。"""

from __future__ import annotations

from dayu.contracts import (
    FunctionToolExecutor,
    ToolBundle,
    ToolCompletedOutcome,
    ToolExecutionRequest,
    ToolDefinition,
    ToolDisplayInfo,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolResultSuccess,
    ToolSchema,
    ToolTruncateSpec,
    tool,
)
from dayu.contracts.tool_outcome import ToolExecutionOutcome


async def _echo_tool(
    request: ToolExecutionRequest,
) -> ToolExecutionOutcome:
    """测试工具函数。

    :param request: 工具执行请求。
    :returns: 成功 outcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value={"name": request.call.name},
            meta=None,
        )
    )


def _parameters() -> ToolParametersSchema:
    """构造测试参数 schema。

    :returns: 参数 schema。
    :raises Exception: 不主动抛出异常。
    """

    return ToolParametersSchema(
        type="object",
        properties={"text": {"type": "string"}},
        required=("text",),
        additional_properties=False,
    )


def _truncate_spec() -> ToolTruncateSpec:
    """构造测试截断声明。

    :returns: 截断声明。
    :raises Exception: 不主动抛出异常。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy="text_chars",
        limits={"max_chars": 8},
        target_field=None,
        field_path=None,
        ttl_seconds=60,
    )


def test_tool_declaration_keeps_schema_runtime_and_display_metadata_separate() -> None:
    """``@tool`` 同源声明，但投影给 Engine 时只剩 ``ToolSchema``。"""

    definition = tool(
        name="huge_echo",
        description="return a large echo",
        parameters=_parameters(),
        truncate=_truncate_spec(),
        display_name="Huge Echo",
        tags=("smoke", "phase5"),
    )(_echo_tool)
    bundle = ToolBundle(definitions=(definition,))

    projected = definition.to_tool_schema()
    bundle_projected = bundle.to_tool_schemas()
    truncate_specs = bundle.truncate_specs()

    assert definition.name == "huge_echo"
    assert definition.callable is _echo_tool
    assert definition.truncate == _truncate_spec()
    assert definition.display == ToolDisplayInfo(name="Huge Echo")
    assert not hasattr(definition, "display_name")
    assert definition.tags == ("smoke", "phase5")
    assert isinstance(projected, ToolSchema)
    assert bundle_projected == (projected,)
    assert truncate_specs == {"huge_echo": _truncate_spec()}
    assert projected.function.name == "huge_echo"
    assert projected.function.description == "return a large echo"
    assert projected.function.parameters == _parameters()
    assert not hasattr(projected, "truncate")
    assert not hasattr(projected, "display")
    assert not hasattr(projected, "display_name")
    assert not hasattr(projected, "tags")
    assert "fetch_more" not in projected.function.parameters.properties


def test_tool_definition_rejects_name_schema_mismatch() -> None:
    """手动构造声明时，工具名必须与 LLM-facing schema 同源。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="schema_name",
            description="schema tool",
            parameters=_parameters(),
        ),
    )

    try:
        ToolDefinition(
            name="runtime_name",
            callable=_echo_tool,
            executor=FunctionToolExecutor(_echo_tool),
            schema=schema,
            truncate=_truncate_spec(),
            display=None,
            tags=(),
        )
    except ValueError as exc:
        assert str(exc) == "ToolDefinition name must match schema.function.name"
    else:
        raise AssertionError("mismatched tool definition was accepted")


def test_tool_bundle_rejects_duplicate_tool_name() -> None:
    """bundle 拒绝重复工具名，避免截断声明静默覆盖。"""

    first = tool(
        name="duplicated",
        description="first",
        parameters=_parameters(),
        truncate=_truncate_spec(),
    )(_echo_tool)
    second = tool(
        name="duplicated",
        description="second",
        parameters=_parameters(),
        truncate=None,
    )(_echo_tool)

    try:
        ToolBundle(definitions=(first, second))
    except ValueError as exc:
        assert str(exc) == "duplicate tool name: duplicated"
    else:
        raise AssertionError("duplicate tool bundle was accepted")
