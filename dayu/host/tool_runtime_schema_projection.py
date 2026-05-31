"""ToolRuntime effective schema 投影与诊断摘要 helper。

本私有模块只承载 ToolRuntime effective bundle 构造时使用的 schema 投影、
工具声明索引和诊断摘要计算。它不拥有 ToolRuntime accept barrier、
truncation cursor、duplicate governance、diagnostic emitter 或 factory
生命周期。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.tooling import FrameworkToolPolicyView


def validate_reserved_name_conflicts(
    bundle: ToolBundle, policy: FrameworkToolPolicyView
) -> None:
    """校验业务工具没有占用 framework 预留名。

    :param bundle: 业务工具集合。
    :param policy: framework tool policy view。
    :returns: ``None``。
    :raises ValueError: 业务工具名占用预留名时抛出。
    """

    reserved = frozenset(
        tool_name.value for tool_name in policy.reserved_framework_tool_names
    )
    for definition in bundle.definitions:
        if definition.name in reserved:
            raise ValueError(
                "business ToolBundle contains reserved framework tool name:"
                f" {definition.name}"
            )


def definitions_by_name(
    definitions: list[ToolDefinition],
) -> dict[str, ToolDefinition]:
    """按工具名索引工具声明并拒绝重复名称。

    :param definitions: effective 工具声明列表。
    :returns: 按名称索引的声明字典。
    :raises ValueError: 出现重复工具名时抛出。
    """

    result: dict[str, ToolDefinition] = {}
    for definition in definitions:
        if definition.name in result:
            raise ValueError(f"duplicate effective tool name: {definition.name}")
        result[definition.name] = definition
    return result


def business_bundle_digest(bundle: ToolBundle) -> str:
    """计算业务工具 bundle 的稳定诊断摘要。

    :param bundle: 业务工具集合。
    :returns: ``sha256:`` 前缀摘要。
    """

    return tool_definitions_digest(bundle.definitions)


def tool_definitions_digest(definitions: tuple[ToolDefinition, ...]) -> str:
    """计算业务工具定义元组的稳定诊断摘要。

    :param definitions: 业务工具定义元组；空元组表示 no-tool 模式。
    :returns: ``sha256:`` 前缀摘要。
    """

    return sha256_digest_json(
        {
            "definitions": [
                tool_definition_digest_json(definition)
                for definition in definitions
            ]
        }
    )


def tool_schemas_digest(tool_schemas: tuple[ToolSchema, ...]) -> str:
    """计算 Engine 可见 tool schemas 的稳定诊断摘要。

    :param tool_schemas: Engine 可见工具 schema 元组。
    :returns: ``sha256:`` 前缀摘要。
    """

    return sha256_digest_json(
        {"tool_schemas": [tool_schema_json(schema) for schema in tool_schemas]}
    )


def tool_definition_digest_json(definition: ToolDefinition) -> JsonValue:
    """把工具声明投影为可参与摘要计算的 JSON 值。

    :param definition: 工具声明。
    :returns: 摘要输入 JSON mapping。
    """

    return {
        "name": definition.name,
        "schema": tool_schema_json(definition.schema),
        "truncate": truncate_spec_json(definition.truncate),
        "tags": list(definition.tags),
    }


def tool_schema_json(schema: ToolSchema) -> JsonValue:
    """把工具 schema 投影为 JSON 值。

    :param schema: 工具 schema。
    :returns: schema JSON mapping。
    """

    return {
        "type": schema.type,
        "function": {
            "name": schema.function.name,
            "description": schema.function.description,
            "parameters": parameters_json(schema.function.parameters),
        },
    }


def parameters_json(parameters: ToolParametersSchema) -> JsonValue:
    """把工具参数 schema 投影为 JSON 值。

    :param parameters: 工具参数 schema。
    :returns: 参数 schema JSON mapping。
    """

    result: dict[str, JsonValue] = {
        "type": parameters.type,
        "properties": parameters.properties,
        "required": list(parameters.required),
    }
    if parameters.additional_properties is not None:
        result["additionalProperties"] = parameters.additional_properties
    return result


def truncate_spec_json(spec: ToolTruncateSpec | None) -> JsonValue:
    """把截断声明投影为 JSON 值。

    :param spec: 截断声明；无声明时为 ``None``。
    :returns: 截断声明 JSON mapping 或 ``None``。
    """

    if spec is None:
        return None
    return {
        "enabled": spec.enabled,
        "strategy": spec.strategy,
        "limits": spec.limits,
        "target_field": spec.target_field,
        "field_path": list(spec.field_path) if spec.field_path is not None else None,
        "ttl_seconds": spec.ttl_seconds,
    }
