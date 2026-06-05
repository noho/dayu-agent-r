"""迁移工具参数投影与校验。

本模块实现 adapter 侧的窄 JSON Schema 校验能力，只覆盖 OLD Doc/Fins/Web
声明实际使用的一层 object 参数、标量、数组、枚举、默认值与数值边界。它不
解释业务语义，也不把显式工具参数塞入额外 payload。
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallRequest
from dayu.contracts.tool_schema import ToolParametersSchema

from .registry_collector import CollectedLegacyTool

_SUPPORTED_JSON_SCHEMA_TYPES: frozenset[str] = frozenset(
    {"string", "integer", "number", "boolean", "array", "object"}
)


@dataclass(frozen=True, slots=True)
class ArgumentValidationSuccess:
    """参数校验成功结果。

    :param arguments: 可传给迁移函数的 JSON keyword arguments。
    :param direct_pass_through: 是否可直接复用原始 ``ToolCallRequest.arguments``。
    """

    arguments: Mapping[str, JsonValue]
    direct_pass_through: bool


@dataclass(frozen=True, slots=True)
class ArgumentValidationFailure:
    """参数校验失败结果。

    :param error: current failure 错误码。
    :param message: 面向 LLM 的错误说明。
    :param hint: 可选恢复提示。
    """

    error: str
    message: str
    hint: str | None


ArgumentValidationResult: TypeAlias = ArgumentValidationSuccess | ArgumentValidationFailure
"""参数校验结果联合。"""


@dataclass(frozen=True, slots=True)
class _FieldProjection:
    """单字段投影结果。

    :param value: 投影后的 JSON 值。
    :param changed: 是否发生默认值填充或类型转换。
    """

    value: JsonValue
    changed: bool


_FieldProjectionResult: TypeAlias = _FieldProjection | ArgumentValidationFailure


def validate_tool_arguments(
    declaration: CollectedLegacyTool,
    call: ToolCallRequest,
) -> ArgumentValidationResult:
    """按工具 schema 与同步函数签名校验调用参数。

    :param declaration: 收集到的迁移工具声明。
    :param call: current 工具调用请求。
    :returns: 成功时返回投影 keyword arguments，失败时返回错误说明。
    :raises Exception: 不主动抛出异常。
    """

    if call.name != declaration.name:
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Tool call name {call.name!r} does not match {declaration.name!r}.",
            hint="Retry with the tool name from the current tool schema.",
        )
    parameters = declaration.schema.function.parameters
    signature_result = _keyword_parameter_names(
        declaration=declaration,
        parameters=parameters,
    )
    if isinstance(signature_result, ArgumentValidationFailure):
        return signature_result
    allowed_parameter_names = signature_result

    unknown_fields = tuple(
        sorted(field_name for field_name in call.arguments if field_name not in parameters.properties)
    )
    if unknown_fields:
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Unsupported tool argument fields: {', '.join(unknown_fields)}.",
            hint=(
                "Remove unsupported fields and retry. Allowed fields: "
                f"{', '.join(sorted(parameters.properties.keys()))}."
            ),
        )

    missing_required = tuple(
        field_name for field_name in parameters.required if field_name not in call.arguments
    )
    if missing_required:
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Missing required tool arguments: {', '.join(missing_required)}.",
            hint=f"Add required fields and retry: {', '.join(missing_required)}.",
        )

    projected: dict[str, JsonValue] = {}
    changed = False
    for field_name, field_schema_value in parameters.properties.items():
        if field_name not in allowed_parameter_names:
            return ArgumentValidationFailure(
                error="invalid_argument",
                message=f"Tool schema field {field_name!r} is not accepted by the migrated function.",
                hint="Use a provider adapter projection that matches the migrated function signature.",
            )
        if field_name in call.arguments:
            projection = _project_field(
                field_name=field_name,
                value=call.arguments[field_name],
                field_schema_value=field_schema_value,
            )
            if isinstance(projection, ArgumentValidationFailure):
                return projection
            projected[field_name] = projection.value
            changed = changed or projection.changed
            continue
        default_projection = _default_field(
            field_name=field_name,
            field_schema_value=field_schema_value,
        )
        if isinstance(default_projection, ArgumentValidationFailure):
            return default_projection
        if default_projection is not None:
            projected[field_name] = default_projection.value
            changed = True

    if not changed and _can_direct_pass_through(
        declaration=declaration,
        call=call,
    ):
        return ArgumentValidationSuccess(
            arguments=call.arguments,
            direct_pass_through=True,
        )
    return ArgumentValidationSuccess(
        arguments=projected,
        direct_pass_through=False,
    )


def _keyword_parameter_names(
    *,
    declaration: CollectedLegacyTool,
    parameters: ToolParametersSchema,
) -> tuple[str, ...] | ArgumentValidationFailure:
    """读取同步函数可接收的关键字参数名。

    :param declaration: 迁移工具声明。
    :param parameters: 工具参数 schema。
    :returns: 参数名元组，或校验失败。
    :raises Exception: 不主动抛出异常。
    """

    signature = inspect.signature(declaration.callable)
    names: list[str] = []
    has_var_keyword = False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            names.append(parameter.name)
    if declaration.execution_context_param_name is not None:
        names.append(declaration.execution_context_param_name)
    if has_var_keyword:
        return tuple(parameters.properties.keys())
    missing_from_function = tuple(
        sorted(field_name for field_name in parameters.properties if field_name not in names)
    )
    if missing_from_function:
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=(
                "Tool schema fields are not accepted by the migrated function: "
                f"{', '.join(missing_from_function)}."
            ),
            hint="Fix the provider projection before exposing this tool.",
        )
    return tuple(names)


def _project_field(
    *,
    field_name: str,
    value: JsonValue,
    field_schema_value: JsonValue,
) -> _FieldProjectionResult:
    """投影单个字段。

    :param field_name: 字段名。
    :param value: 原始 JSON 值。
    :param field_schema_value: 字段 JSON Schema。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(field_schema_value, Mapping):
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Tool schema for {field_name!r} must be an object.",
            hint="Fix the provider tool schema before retrying.",
        )
    type_value = field_schema_value.get("type")
    if not isinstance(type_value, str) or type_value not in _SUPPORTED_JSON_SCHEMA_TYPES:
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Tool argument {field_name!r} uses unsupported schema type.",
            hint="Fix the provider tool schema before retrying.",
        )
    enum_failure = _validate_enum(
        field_name=field_name,
        value=value,
        field_schema=field_schema_value,
    )
    if enum_failure is not None:
        return enum_failure
    if type_value == "string":
        return _project_string(field_name=field_name, value=value, field_schema=field_schema_value)
    if type_value == "integer":
        return _project_integer(field_name=field_name, value=value, field_schema=field_schema_value)
    if type_value == "number":
        return _project_number(field_name=field_name, value=value, field_schema=field_schema_value)
    if type_value == "boolean":
        return _project_boolean(field_name=field_name, value=value)
    if type_value == "array":
        return _project_array(field_name=field_name, value=value, field_schema=field_schema_value)
    return _project_object(field_name=field_name, value=value)


def _default_field(
    *,
    field_name: str,
    field_schema_value: JsonValue,
) -> _FieldProjectionResult | None:
    """读取并校验 schema 默认值。

    :param field_name: 字段名。
    :param field_schema_value: 字段 JSON Schema。
    :returns: 默认值投影、失败或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(field_schema_value, Mapping) or "default" not in field_schema_value:
        return None
    return _project_field(
        field_name=field_name,
        value=field_schema_value["default"],
        field_schema_value=field_schema_value,
    )


def _validate_enum(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> ArgumentValidationFailure | None:
    """校验枚举值。

    :param field_name: 字段名。
    :param value: 字段值。
    :param field_schema: 字段 JSON Schema。
    :returns: 失败结果或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    enum_value = field_schema.get("enum")
    if enum_value is None:
        return None
    if not isinstance(enum_value, list):
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Tool schema enum for {field_name!r} must be an array.",
            hint="Fix the provider tool schema before retrying.",
        )
    if value not in enum_value:
        allowed = ", ".join(str(item) for item in enum_value)
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Tool argument {field_name!r} must be one of: {allowed}.",
            hint=f"Set {field_name} to one of: {allowed}.",
        )
    return None


def _project_string(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> _FieldProjectionResult:
    """投影字符串字段。

    :param field_name: 字段名。
    :param value: 原始值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, str):
        return _type_failure(field_name=field_name, expected="string")
    min_length = field_schema.get("minLength")
    max_length = field_schema.get("maxLength")
    if isinstance(min_length, int) and len(value) < min_length:
        return _range_failure(field_name=field_name, detail=f"at least {min_length} characters")
    if isinstance(max_length, int) and len(value) > max_length:
        return _range_failure(field_name=field_name, detail=f"at most {max_length} characters")
    return _FieldProjection(value=value, changed=False)


def _project_integer(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> _FieldProjectionResult:
    """投影整数字段。

    :param field_name: 字段名。
    :param value: 原始值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    changed = False
    if isinstance(value, bool):
        return _type_failure(field_name=field_name, expected="integer")
    if isinstance(value, int):
        integer_value = value
    elif isinstance(value, float) and value.is_integer():
        integer_value = int(value)
        changed = True
    else:
        return _type_failure(field_name=field_name, expected="integer")
    range_failure = _validate_numeric_range(
        field_name=field_name,
        value=float(integer_value),
        field_schema=field_schema,
    )
    if range_failure is not None:
        return range_failure
    return _FieldProjection(value=integer_value, changed=changed)


def _project_number(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> _FieldProjectionResult:
    """投影数值字段。

    :param field_name: 字段名。
    :param value: 原始值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _type_failure(field_name=field_name, expected="number")
    range_failure = _validate_numeric_range(
        field_name=field_name,
        value=float(value),
        field_schema=field_schema,
    )
    if range_failure is not None:
        return range_failure
    return _FieldProjection(value=value, changed=False)


def _project_boolean(
    *,
    field_name: str,
    value: JsonValue,
) -> _FieldProjectionResult:
    """投影布尔字段。

    :param field_name: 字段名。
    :param value: 原始值。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, bool):
        return _type_failure(field_name=field_name, expected="boolean")
    return _FieldProjection(value=value, changed=False)


def _project_array(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> _FieldProjectionResult:
    """投影数组字段。

    :param field_name: 字段名。
    :param value: 原始值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, list):
        return _type_failure(field_name=field_name, expected="array")
    min_items = field_schema.get("minItems")
    max_items = field_schema.get("maxItems")
    if isinstance(min_items, int) and len(value) < min_items:
        return _range_failure(field_name=field_name, detail=f"at least {min_items} items")
    if isinstance(max_items, int) and len(value) > max_items:
        return _range_failure(field_name=field_name, detail=f"at most {max_items} items")
    item_schema = field_schema.get("items")
    if item_schema is None:
        return _FieldProjection(value=value, changed=False)
    if not isinstance(item_schema, Mapping):
        return ArgumentValidationFailure(
            error="invalid_argument",
            message=f"Tool schema items for {field_name!r} must be an object.",
            hint="Fix the provider tool schema before retrying.",
        )
    projected_items: list[JsonValue] = []
    changed = False
    for index, item in enumerate(value):
        projection = _project_field(
            field_name=f"{field_name}[{index}]",
            value=item,
            field_schema_value=item_schema,
        )
        if isinstance(projection, ArgumentValidationFailure):
            return projection
        projected_items.append(projection.value)
        changed = changed or projection.changed
    return _FieldProjection(value=projected_items, changed=changed)


def _project_object(
    *,
    field_name: str,
    value: JsonValue,
) -> _FieldProjectionResult:
    """投影对象字段。

    :param field_name: 字段名。
    :param value: 原始值。
    :returns: 字段投影结果或失败。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, Mapping):
        return _type_failure(field_name=field_name, expected="object")
    return _FieldProjection(value=value, changed=False)


def _validate_numeric_range(
    *,
    field_name: str,
    value: float,
    field_schema: Mapping[str, JsonValue],
) -> ArgumentValidationFailure | None:
    """校验数值边界。

    :param field_name: 字段名。
    :param value: 数值。
    :param field_schema: 字段 JSON Schema。
    :returns: 失败结果或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    minimum = field_schema.get("minimum")
    maximum = field_schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < float(minimum):
        return _range_failure(field_name=field_name, detail=f">= {minimum}")
    if isinstance(maximum, (int, float)) and value > float(maximum):
        return _range_failure(field_name=field_name, detail=f"<= {maximum}")
    return None


def _type_failure(*, field_name: str, expected: str) -> ArgumentValidationFailure:
    """构造类型错误。

    :param field_name: 字段名。
    :param expected: 期望类型。
    :returns: 参数失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return ArgumentValidationFailure(
        error="invalid_argument",
        message=f"Tool argument {field_name!r} must be {expected}.",
        hint=f"Set {field_name} to {expected} and retry.",
    )


def _range_failure(*, field_name: str, detail: str) -> ArgumentValidationFailure:
    """构造边界错误。

    :param field_name: 字段名。
    :param detail: 边界说明。
    :returns: 参数失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return ArgumentValidationFailure(
        error="invalid_argument",
        message=f"Tool argument {field_name!r} must be {detail}.",
        hint=f"Adjust {field_name} to {detail} and retry.",
    )


def _can_direct_pass_through(
    *,
    declaration: CollectedLegacyTool,
    call: ToolCallRequest,
) -> bool:
    """判断本次调用是否满足直接透传条件。

    :param declaration: 迁移工具声明。
    :param call: 工具调用请求。
    :returns: 满足直接透传条件时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if declaration.file_path_params or declaration.execution_context_param_name is not None:
        return False
    parameters = declaration.schema.function.parameters
    if any(
        isinstance(field_schema, Mapping) and "default" in field_schema
        for field_schema in parameters.properties.values()
        if isinstance(field_schema, Mapping)
    ):
        return False
    return set(call.arguments.keys()).issubset(set(parameters.properties.keys()))
