"""current 工具 callable 的参数投影与 outcome 构造 helper。

本模块只服务原生 ``ToolCallable`` 迁移入口的共同薄层能力：

- 按当前 ``ToolParametersSchema`` 的窄 JSON Schema 子集校验
  ``ToolCallRequest.arguments``，并应用字段默认值。
- 构造 completed / failed / host-cancelled outcome，保证三类终态使用一致
  的 ``ToolResultMeta``。

本模块是层中立 runtime helper，只依赖标准库与 ``dayu.contracts``；
不观察 Host cancellation token，不导入 Doc / Web / Fins 业务实现，也不暴露
run / session / correlation 等 Host 治理字段。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypeAlias, cast

from dayu.contracts import (
    JsonValue,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCallRequest,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
    ToolParametersSchema,
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
)

INVALID_ARGUMENT_ERROR: Final[Literal["invalid_argument"]] = "invalid_argument"
"""工具参数校验失败的固定错误码。"""

_DEFAULT_HOST_CANCELLED_MESSAGE: Final[str] = "工具调用已被宿主取消。"
_DEFAULT_HOST_CANCELLED_HINT: Final[str] = "不要把本次取消视为业务失败；如仍需要结果，请在后续步骤重新发起请求。"
_DEFAULT_EXECUTION_ERROR: Final[str] = "execution_error"
_DEFAULT_FAILURE_MESSAGE: Final[str] = "Tool execution failed."

_SUPPORTED_JSON_SCHEMA_TYPES: Final[frozenset[str]] = frozenset(
    {"string", "integer", "number", "boolean", "array", "object"}
)
_SUPPORTED_ARRAY_ITEM_TYPES: Final[frozenset[str]] = frozenset({"string", "integer", "number", "boolean"})
_SUPPORTED_FIELD_SCHEMA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "default",
        "description",
        "enum",
        "items",
        "maximum",
        "maxItems",
        "maxLength",
        "minimum",
        "minItems",
        "minLength",
        "type",
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedToolArguments:
    """工具参数校验成功结果。

    :param arguments: 已按 schema 默认值投影后的工具参数。该映射只包含
        schema 声明字段；若 schema 显式允许 additional properties，则保留
        调用方传入的额外 JSON 字段。
    :returns: dataclass 实例本身。
    :raises Exception: 构造期不主动抛出异常。
    """

    arguments: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolArgumentValidationFailure:
    """工具参数校验失败结果。

    :param error: 失败错误码，固定为 ``invalid_argument``。
    :param field_name: 触发失败的字段名；非字段级错误为 ``None``。
    :param message: 面向 LLM 的可读错误说明。
    :param hint: 可选恢复提示。
    :returns: dataclass 实例本身。
    :raises Exception: 构造期不主动抛出异常。
    """

    error: Literal["invalid_argument"]
    field_name: str | None
    message: str
    hint: str | None


@dataclass(frozen=True, slots=True)
class ToolBusinessFailure:
    """工具业务失败的 callable 内部传递结果。

    该类型只表达业务 helper 到原生 callable 边界的失败语义；它不是异常，
    也不携带 Host 治理字段。

    :param error: 业务错误码。
    :param message: 面向 LLM 的可读错误说明。
    :param hint: 可选恢复提示。
    :returns: dataclass 实例本身。
    :raises Exception: 构造期不主动抛出异常。
    """

    error: str
    message: str
    hint: str | None


@dataclass(frozen=True, slots=True)
class ToolBusinessCancelled:
    """工具业务 helper 观察到语义取消时的内部传递结果。

    该类型只用于后续 callable slice 在自身边界内表达“应返回取消 outcome”；
    它不观察 cancellation token，也不承载 Host governance 字段。

    :param message: 可选取消说明；为空时由 ``host_cancelled_outcome`` 填充默认说明。
    :param hint: 可选恢复提示；为空时由 ``host_cancelled_outcome`` 填充默认提示。
    :returns: dataclass 实例本身。
    :raises Exception: 构造期不主动抛出异常。
    """

    message: str | None
    hint: str | None


ToolArgumentValidationResult: TypeAlias = ValidatedToolArguments | ToolArgumentValidationFailure
"""工具参数校验结果联合。"""


@dataclass(frozen=True, slots=True)
class _FieldProjection:
    """单字段投影结果。

    :param value: 投影后的 JSON 值。
    :param changed: 字段是否因默认值或整数转换而变化。
    :returns: dataclass 实例本身。
    :raises Exception: 构造期不主动抛出异常。
    """

    value: JsonValue
    changed: bool


_FieldProjectionResult: TypeAlias = _FieldProjection | ToolArgumentValidationFailure


def validate_and_project_arguments(
    call: ToolCallRequest,
    tool_name: str,
    schema: ToolParametersSchema,
) -> ToolArgumentValidationResult:
    """校验并投影 current 工具调用参数。

    :param call: 单次工具调用请求。
    :param tool_name: 当前 callable 对应的工具名。
    :param schema: 当前工具声明的参数 schema。
    :returns: 成功时返回 ``ValidatedToolArguments``；失败时返回
        ``ToolArgumentValidationFailure``，错误码固定为 ``invalid_argument``。
    :raises Exception: 不主动抛出异常。
    """

    if call.name != tool_name:
        return _failure(
            field_name=None,
            message=f"Tool call name {call.name!r} does not match {tool_name!r}.",
            hint="Retry with the tool name from the current tool schema.",
        )

    unknown_fields = tuple(sorted(field_name for field_name in call.arguments if field_name not in schema.properties))
    if unknown_fields and schema.additional_properties is not True:
        return _failure(
            field_name=unknown_fields[0],
            message=f"Unsupported tool argument fields: {', '.join(unknown_fields)}.",
            hint=(
                "Remove unsupported fields and retry. Allowed fields: "
                f"{', '.join(sorted(schema.properties.keys()))}."
            ),
        )

    missing_required = tuple(field_name for field_name in schema.required if field_name not in call.arguments)
    if missing_required:
        return _failure(
            field_name=missing_required[0],
            message=f"Missing required tool arguments: {', '.join(missing_required)}.",
            hint=f"Add required fields and retry: {', '.join(missing_required)}.",
        )

    projected: dict[str, JsonValue] = {}
    if schema.additional_properties is True:
        projected.update(call.arguments)

    for field_name, field_schema_value in schema.properties.items():
        if field_name in call.arguments:
            projection = _project_field(
                field_name=field_name,
                value=call.arguments[field_name],
                field_schema_value=field_schema_value,
                allow_array_items=True,
            )
            if isinstance(projection, ToolArgumentValidationFailure):
                return projection
            projected[field_name] = projection.value
            continue

        default_projection = _default_field(
            field_name=field_name,
            field_schema_value=field_schema_value,
        )
        if isinstance(default_projection, ToolArgumentValidationFailure):
            return default_projection
        if default_projection is not None:
            projected[field_name] = default_projection.value

    return ValidatedToolArguments(arguments=projected)


def completed_outcome(
    *,
    tool_name: str,
    value: JsonValue,
    started_at: datetime,
    finished_at: datetime,
) -> ToolCompletedOutcome:
    """构造工具成功 outcome。

    :param tool_name: 工具名。
    :param value: JSON 兼容成功载荷。
    :param started_at: 工具执行开始时间。
    :param finished_at: 工具执行结束时间。
    :returns: ``ToolCompletedOutcome``。
    :raises Exception: ``ToolResultMeta`` 或 ``ToolResultSuccess`` 契约构造失败时透出。
    """

    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value=value,
            meta=_meta(
                tool_name=tool_name,
                started_at=started_at,
                finished_at=finished_at,
            ),
        )
    )


def failed_outcome(
    *,
    tool_name: str,
    error: str,
    message: str,
    hint: str | None,
    started_at: datetime,
    finished_at: datetime,
) -> ToolFailedOutcome:
    """构造工具失败 outcome。

    :param tool_name: 工具名。
    :param error: 失败错误码；空白时归一为 ``execution_error``。
    :param message: 面向 LLM 的错误说明；空白时归一为通用失败说明。
    :param hint: 可选恢复提示；空白时归一为 ``None``。
    :param started_at: 工具执行开始时间。
    :param finished_at: 工具执行结束时间。
    :returns: ``ToolFailedOutcome``。
    :raises Exception: ``ToolResultMeta`` 或 ``ToolResultFailure`` 契约构造失败时透出。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=_blank_to_default(error, _DEFAULT_EXECUTION_ERROR),
            message=_blank_to_default(message, _DEFAULT_FAILURE_MESSAGE),
            hint=_blank_to_none(hint),
            meta=_meta(
                tool_name=tool_name,
                started_at=started_at,
                finished_at=finished_at,
            ),
        )
    )


def host_cancelled_outcome(
    *,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
    message: str | None = None,
    hint: str | None = None,
) -> ToolCancelledOutcome:
    """构造 Host 语义取消 outcome。

    :param tool_name: 工具名。
    :param started_at: 工具执行开始时间。
    :param finished_at: 工具执行结束时间。
    :param message: 可选取消说明；为 ``None`` 或空白时使用非空默认说明。
    :param hint: 可选恢复提示；为 ``None`` 或空白时使用非空默认提示。
    :returns: ``ToolCancelledOutcome``，reason 固定为
        ``TOOL_CANCELLED_REASON_HOST_CANCELLED``。
    :raises Exception: ``ToolResultMeta`` 或 ``ToolCancelledOutcome`` 契约构造失败时透出。
    """

    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message=_blank_to_default_optional(message, _DEFAULT_HOST_CANCELLED_MESSAGE),
        hint=_blank_to_default_optional(hint, _DEFAULT_HOST_CANCELLED_HINT),
        meta=_meta(
            tool_name=tool_name,
            started_at=started_at,
            finished_at=finished_at,
        ),
    )


def _default_field(
    *,
    field_name: str,
    field_schema_value: JsonValue,
) -> _FieldProjectionResult | None:
    """读取并校验字段默认值。

    :param field_name: 字段名。
    :param field_schema_value: 字段 JSON Schema。
    :returns: 默认值投影、失败结果或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(field_schema_value, Mapping):
        return None
    field_schema = cast(Mapping[str, JsonValue], field_schema_value)
    if "default" not in field_schema:
        return None
    return _project_field(
        field_name=field_name,
        value=field_schema["default"],
        field_schema_value=field_schema,
        allow_array_items=True,
    )


def _project_field(
    *,
    field_name: str,
    value: JsonValue,
    field_schema_value: JsonValue,
    allow_array_items: bool,
) -> _FieldProjectionResult:
    """按字段 schema 投影单个参数值。

    :param field_name: 字段名。
    :param value: 原始 JSON 值。
    :param field_schema_value: 字段 JSON Schema。
    :param allow_array_items: 是否允许当前字段作为数组 items schema 使用。
    :returns: 字段投影结果或失败结果。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(field_schema_value, Mapping):
        return _failure(
            field_name=field_name,
            message=f"Tool schema for {field_name!r} must be an object.",
            hint="Fix the provider tool schema before retrying.",
        )
    field_schema = cast(Mapping[str, JsonValue], field_schema_value)
    unsupported_key = _first_unsupported_schema_key(field_schema)
    if unsupported_key is not None:
        return _failure(
            field_name=field_name,
            message=(f"Tool schema for {field_name!r} uses unsupported keyword " f"{unsupported_key!r}."),
            hint="Fix the provider tool schema before retrying.",
        )

    type_value = field_schema.get("type")
    if not isinstance(type_value, str) or type_value not in _SUPPORTED_JSON_SCHEMA_TYPES:
        return _failure(
            field_name=field_name,
            message=f"Tool argument {field_name!r} uses unsupported schema type.",
            hint="Fix the provider tool schema before retrying.",
        )
    if not allow_array_items and type_value not in _SUPPORTED_ARRAY_ITEM_TYPES:
        return _failure(
            field_name=field_name,
            message=f"Tool array item {field_name!r} uses unsupported schema type.",
            hint="Use scalar array items in the provider tool schema.",
        )

    if type_value == "string":
        projection = _project_string(
            field_name=field_name,
            value=value,
            field_schema=field_schema,
        )
    elif type_value == "integer":
        projection = _project_integer(
            field_name=field_name,
            value=value,
            field_schema=field_schema,
        )
    elif type_value == "number":
        projection = _project_number(
            field_name=field_name,
            value=value,
            field_schema=field_schema,
        )
    elif type_value == "boolean":
        projection = _project_boolean(field_name=field_name, value=value)
    elif type_value == "array":
        projection = _project_array(
            field_name=field_name,
            value=value,
            field_schema=field_schema,
        )
    else:
        projection = _project_object(field_name=field_name, value=value)

    if isinstance(projection, ToolArgumentValidationFailure):
        return projection
    enum_failure = _validate_enum(
        field_name=field_name,
        value=projection.value,
        field_schema=field_schema,
    )
    if enum_failure is not None:
        return enum_failure
    return projection


def _project_string(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> _FieldProjectionResult:
    """投影字符串字段。

    :param field_name: 字段名。
    :param value: 原始 JSON 值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败结果。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, str):
        return _type_failure(field_name=field_name, expected="string")
    min_length = field_schema.get("minLength")
    if min_length is not None:
        if isinstance(min_length, bool) or not isinstance(min_length, int):
            return _schema_bound_failure(field_name=field_name, bound_name="minLength")
        if len(value) < min_length:
            return _range_failure(
                field_name=field_name,
                detail=f"at least {min_length} characters",
            )
    max_length = field_schema.get("maxLength")
    if max_length is not None:
        if isinstance(max_length, bool) or not isinstance(max_length, int):
            return _schema_bound_failure(field_name=field_name, bound_name="maxLength")
        if len(value) > max_length:
            return _range_failure(
                field_name=field_name,
                detail=f"at most {max_length} characters",
            )
    return _FieldProjection(value=value, changed=False)


def _project_integer(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> _FieldProjectionResult:
    """投影整数字段。

    :param field_name: 字段名。
    :param value: 原始 JSON 值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败结果。
    :raises Exception: 不主动抛出异常。
    """

    changed = False
    if isinstance(value, bool):
        return _type_failure(field_name=field_name, expected="integer")
    if isinstance(value, int):
        integer_value = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        integer_value = int(value)
        changed = True
    else:
        return _type_failure(field_name=field_name, expected="integer")
    range_failure = _validate_numeric_range(
        field_name=field_name,
        value=integer_value,
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
    :param value: 原始 JSON 值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败结果。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _type_failure(field_name=field_name, expected="number")
    if isinstance(value, float) and not math.isfinite(value):
        return _range_failure(field_name=field_name, detail="a finite number")
    range_failure = _validate_numeric_range(
        field_name=field_name,
        value=value,
        field_schema=field_schema,
    )
    if range_failure is not None:
        return range_failure
    return _FieldProjection(value=value, changed=False)


def _project_boolean(*, field_name: str, value: JsonValue) -> _FieldProjectionResult:
    """投影布尔字段。

    :param field_name: 字段名。
    :param value: 原始 JSON 值。
    :returns: 字段投影结果或失败结果。
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
    :param value: 原始 JSON 值。
    :param field_schema: 字段 JSON Schema。
    :returns: 字段投影结果或失败结果。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, list):
        return _type_failure(field_name=field_name, expected="array")
    min_items = field_schema.get("minItems")
    if min_items is not None:
        if isinstance(min_items, bool) or not isinstance(min_items, int):
            return _schema_bound_failure(field_name=field_name, bound_name="minItems")
        if len(value) < min_items:
            return _range_failure(
                field_name=field_name,
                detail=f"at least {min_items} items",
            )
    max_items = field_schema.get("maxItems")
    if max_items is not None:
        if isinstance(max_items, bool) or not isinstance(max_items, int):
            return _schema_bound_failure(field_name=field_name, bound_name="maxItems")
        if len(value) > max_items:
            return _range_failure(
                field_name=field_name,
                detail=f"at most {max_items} items",
            )

    item_schema = field_schema.get("items")
    if item_schema is None:
        return _FieldProjection(value=value, changed=False)
    if not isinstance(item_schema, Mapping):
        return _failure(
            field_name=field_name,
            message=f"Tool schema items for {field_name!r} must be an object.",
            hint="Fix the provider tool schema before retrying.",
        )

    projected_items: list[JsonValue] = []
    changed = False
    for index, item in enumerate(value):
        projection = _project_field(
            field_name=f"{field_name}[{index}]",
            value=item,
            field_schema_value=cast(Mapping[str, JsonValue], item_schema),
            allow_array_items=False,
        )
        if isinstance(projection, ToolArgumentValidationFailure):
            return projection
        projected_items.append(projection.value)
        changed = changed or projection.changed
    return _FieldProjection(value=projected_items, changed=changed)


def _project_object(*, field_name: str, value: JsonValue) -> _FieldProjectionResult:
    """投影对象字段。

    :param field_name: 字段名。
    :param value: 原始 JSON 值。
    :returns: 字段投影结果或失败结果。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, Mapping):
        return _type_failure(field_name=field_name, expected="object")
    return _FieldProjection(value=value, changed=False)


def _validate_enum(
    *,
    field_name: str,
    value: JsonValue,
    field_schema: Mapping[str, JsonValue],
) -> ToolArgumentValidationFailure | None:
    """校验字段枚举。

    :param field_name: 字段名。
    :param value: 已完成类型投影的字段值。
    :param field_schema: 字段 JSON Schema。
    :returns: 失败结果或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    enum_value = field_schema.get("enum")
    if enum_value is None:
        return None
    if not isinstance(enum_value, list):
        return _failure(
            field_name=field_name,
            message=f"Tool schema enum for {field_name!r} must be an array.",
            hint="Fix the provider tool schema before retrying.",
        )
    if value not in enum_value:
        allowed = ", ".join(str(item) for item in enum_value)
        return _failure(
            field_name=field_name,
            message=f"Tool argument {field_name!r} must be one of: {allowed}.",
            hint=f"Set {field_name} to one of: {allowed}.",
        )
    return None


def _validate_numeric_range(
    *,
    field_name: str,
    value: int | float,
    field_schema: Mapping[str, JsonValue],
) -> ToolArgumentValidationFailure | None:
    """校验数值边界。

    :param field_name: 字段名。
    :param value: 已完成类型投影的数值。
    :param field_schema: 字段 JSON Schema。
    :returns: 失败结果或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    minimum = field_schema.get("minimum")
    if minimum is not None:
        if _is_invalid_number_bound(minimum):
            return _schema_bound_failure(field_name=field_name, bound_name="minimum")
        if value < cast(int | float, minimum):
            return _range_failure(field_name=field_name, detail=f">= {minimum}")

    maximum = field_schema.get("maximum")
    if maximum is not None:
        if _is_invalid_number_bound(maximum):
            return _schema_bound_failure(field_name=field_name, bound_name="maximum")
        if value > cast(int | float, maximum):
            return _range_failure(field_name=field_name, detail=f"<= {maximum}")

    return None


def _is_invalid_number_bound(value: JsonValue) -> bool:
    """判断 numeric bound 是否非法。

    :param value: schema 中的边界值。
    :returns: 非有限数值、布尔值或非数值返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    return isinstance(value, float) and not math.isfinite(value)


def _first_unsupported_schema_key(
    field_schema: Mapping[str, JsonValue],
) -> str | None:
    """返回第一个未支持的字段 schema 关键字。

    :param field_schema: 字段 JSON Schema。
    :returns: 未支持关键字；全部支持时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for key in sorted(field_schema.keys()):
        if key not in _SUPPORTED_FIELD_SCHEMA_KEYS:
            return key
    return None


def _type_failure(*, field_name: str, expected: str) -> ToolArgumentValidationFailure:
    """构造类型错误。

    :param field_name: 字段名。
    :param expected: 期望类型说明。
    :returns: 参数校验失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return _failure(
        field_name=field_name,
        message=f"Tool argument {field_name!r} must be {expected}.",
        hint=f"Set {field_name} to {expected} and retry.",
    )


def _range_failure(*, field_name: str, detail: str) -> ToolArgumentValidationFailure:
    """构造边界错误。

    :param field_name: 字段名。
    :param detail: 边界说明。
    :returns: 参数校验失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return _failure(
        field_name=field_name,
        message=f"Tool argument {field_name!r} must be {detail}.",
        hint=f"Adjust {field_name} to {detail} and retry.",
    )


def _schema_bound_failure(*, field_name: str, bound_name: str) -> ToolArgumentValidationFailure:
    """构造 provider schema 边界声明错误。

    :param field_name: 字段名。
    :param bound_name: 非法边界关键字。
    :returns: 参数校验失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return _failure(
        field_name=field_name,
        message=f"Tool schema bound {bound_name!r} for {field_name!r} is invalid.",
        hint="Fix the provider tool schema before retrying.",
    )


def _failure(
    *,
    field_name: str | None,
    message: str,
    hint: str | None,
) -> ToolArgumentValidationFailure:
    """构造固定 ``invalid_argument`` 参数失败结果。

    :param field_name: 触发失败的字段名；非字段级错误为 ``None``。
    :param message: 失败说明。
    :param hint: 可选恢复提示。
    :returns: 参数校验失败结果。
    :raises Exception: 不主动抛出异常。
    """

    return ToolArgumentValidationFailure(
        error=INVALID_ARGUMENT_ERROR,
        field_name=field_name,
        message=message,
        hint=_blank_to_none(hint),
    )


def _meta(
    *,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
) -> ToolResultMeta:
    """构造工具结果中性元信息。

    :param tool_name: 工具名。
    :param started_at: 工具执行开始时间。
    :param finished_at: 工具执行结束时间。
    :returns: ``ToolResultMeta``。
    :raises Exception: ``ToolResultMeta`` 契约构造失败时透出。
    """

    return ToolResultMeta(
        tool_name=tool_name,
        started_at=started_at,
        finished_at=finished_at,
    )


def _blank_to_default(value: str, default: str) -> str:
    """把空白字符串替换为默认值。

    :param value: 原始文本。
    :param default: 默认文本。
    :returns: 非空文本。
    :raises Exception: 不主动抛出异常。
    """

    return value if value.strip() != "" else default


def _blank_to_default_optional(value: str | None, default: str) -> str:
    """把可选空白字符串替换为默认值。

    :param value: 原始可选文本。
    :param default: 默认文本。
    :returns: 非空文本。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return default
    normalized = value.strip()
    return normalized if normalized else default


def _blank_to_none(value: str | None) -> str | None:
    """把可选空白字符串归一为 ``None``。

    :param value: 原始可选文本。
    :returns: 非空文本或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


__all__ = [
    "INVALID_ARGUMENT_ERROR",
    "ToolArgumentValidationFailure",
    "ToolArgumentValidationResult",
    "ToolBusinessCancelled",
    "ToolBusinessFailure",
    "ValidatedToolArguments",
    "completed_outcome",
    "failed_outcome",
    "host_cancelled_outcome",
    "validate_and_project_arguments",
]
