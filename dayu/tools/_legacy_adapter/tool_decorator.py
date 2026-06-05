"""OLD 风格 ``@tool`` 声明装饰器。

该装饰器只构造 current ``ToolSchema`` 并把声明 metadata 挂到函数对象上，
供 ``LegacyToolDeclarationCollector`` 收集。它不会注册 executor、不会执行
工具、不会建立路径白名单，也不会创建 OLD registry。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import ParamSpec, Protocol, cast

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
)

from .registry_collector import LegacySyncToolCallable, LegacyToolDeclarationCollector
from .tool_contracts import DupCallSpec, normalize_truncate_spec

P = ParamSpec("P")


class _DecoratedToolReturn(Protocol):
    """被 legacy decorator 接受但不在声明阶段检查的工具返回值标记。"""


def build_tool_schema(
    *,
    name: str,
    description: str,
    parameters: Mapping[str, JsonValue],
    enums: Mapping[str, Sequence[JsonValue]] | None = None,
) -> ToolSchema:
    """构造 current ``ToolSchema``。

    :param name: 工具名。
    :param description: 工具描述。
    :param parameters: OLD 风格 JSON Schema object。
    :param enums: 可选枚举注入，字段名到枚举值序列。
    :returns: current 工具 schema。
    :raises ValueError: 参数 schema 结构非法时抛出。
    """

    properties_value = parameters.get("properties")
    if not isinstance(properties_value, Mapping):
        raise ValueError("tool parameters.properties must be an object")
    properties: dict[str, JsonValue] = {}
    for field_name, field_schema in properties_value.items():
        if not isinstance(field_name, str) or field_name.strip() == "":
            raise ValueError("tool parameter property names must be non-empty strings")
        if not isinstance(field_schema, Mapping):
            raise ValueError(f"tool parameter {field_name} schema must be an object")
        mutable_schema: dict[str, JsonValue] = dict(field_schema)
        if enums is not None and field_name in enums:
            mutable_schema["enum"] = list(enums[field_name])
        properties[field_name] = mutable_schema

    required_value = parameters.get("required")
    required = _normalize_required(required_value)
    additional_properties_value = parameters.get("additionalProperties")
    additional_properties = _normalize_additional_properties(
        additional_properties_value
    )
    return ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name=name,
            description=description,
            parameters=ToolParametersSchema(
                type="object",
                properties=properties,
                required=required,
                additional_properties=additional_properties,
            ),
        ),
    )


def tool(
    registry: LegacyToolDeclarationCollector,
    *,
    name: str,
    description: str,
    parameters: Mapping[str, JsonValue],
    enums: Mapping[str, Sequence[JsonValue]] | None = None,
    tags: Sequence[str] | None = None,
    truncate: ToolTruncateSpec | Mapping[str, JsonValue] | None = None,
    dup_call: DupCallSpec | Mapping[str, JsonValue] | None = None,
    file_path_params: Sequence[str] | None = None,
    execution_context_param_name: str | None = None,
    display_name: str | None = None,
    summary_params: Sequence[str] | None = None,
) -> Callable[[Callable[P, _DecoratedToolReturn]], LegacySyncToolCallable]:
    """声明一个 OLD 风格同步工具。

    :param registry: OLD 注册函数传入的 collector；本装饰器只把它用于保持
        OLD 调用形状，不从中读取路径安全事实。
    :param name: 工具名。
    :param description: 工具描述。
    :param parameters: 参数 JSON Schema。
    :param enums: 可选枚举注入。
    :param tags: 工具标签。
    :param truncate: current 或 OLD 风格截断声明。
    :param dup_call: OLD 重复调用 metadata；仅内部保存，不投影到 current
        runtime。
    :param file_path_params: 需要外部路径策略验证的参数名。
    :param execution_context_param_name: execution context 注入参数名。
    :param display_name: 展示名。
    :param summary_params: 摘要参数名。
    :returns: 装饰器。
    :raises ValueError: schema 或 metadata 非法时抛出。
    """

    del registry
    schema = build_tool_schema(
        name=name,
        description=description,
        parameters=parameters,
        enums=enums,
    )
    truncate_spec = normalize_truncate_spec(truncate)
    dup_call_spec = _normalize_dup_call(dup_call)
    normalized_context_param = _optional_text(execution_context_param_name)
    normalized_display_name = _optional_text(display_name)
    normalized_summary_params = _normalize_text_sequence(summary_params)
    normalized_file_path_params = _normalize_text_sequence(file_path_params)
    normalized_tags = _normalize_text_sequence(tags)

    def wrap(func: Callable[P, _DecoratedToolReturn]) -> LegacySyncToolCallable:
        """把声明 metadata 挂到函数对象。

        :param func: 被装饰的同步工具函数。
        :returns: 带 metadata 的同步工具函数。
        :raises Exception: 不主动抛出异常。
        """

        decorated = cast(LegacySyncToolCallable, func)
        # OLD 声明 metadata 是函数对象动态属性；集中写入这些属性是为了让
        # collector 在不迁移 OLD ToolRegistry 的情况下收集声明事实。
        setattr(decorated, "__tool_name__", name)
        setattr(decorated, "__tool_schema__", schema)
        setattr(decorated, "__tool_tags__", normalized_tags)
        setattr(decorated, "__tool_truncate__", truncate_spec)
        setattr(decorated, "__tool_dup_call__", dup_call_spec)
        setattr(decorated, "__tool_file_path_params__", normalized_file_path_params)
        setattr(decorated, "__tool_execution_context_param_name__", normalized_context_param)
        setattr(decorated, "__tool_display_name__", normalized_display_name)
        setattr(decorated, "__tool_summary_params__", normalized_summary_params)
        return decorated

    return wrap


def _normalize_required(value: JsonValue) -> tuple[str, ...]:
    """归一化 required 字段。

    :param value: JSON 字段值。
    :returns: required 字段名元组。
    :raises ValueError: 字段类型非法时抛出。
    """

    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("tool parameters.required must be an array")
    required: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError("tool parameters.required items must be non-empty strings")
        required.append(item.strip())
    return tuple(required)


def _normalize_additional_properties(value: JsonValue) -> bool | None:
    """归一化 additionalProperties 字段。

    :param value: JSON 字段值。
    :returns: 布尔值或 ``None``。
    :raises ValueError: 字段类型非法时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("tool parameters.additionalProperties must be boolean")
    return value


def _normalize_dup_call(
    value: DupCallSpec | Mapping[str, JsonValue] | None,
) -> DupCallSpec | None:
    """归一化 OLD 重复调用 metadata。

    :param value: ``DupCallSpec``、JSON mapping 或 ``None``。
    :returns: ``DupCallSpec`` 或 ``None``。
    :raises ValueError: mapping 字段非法时抛出。
    """

    if value is None or isinstance(value, DupCallSpec):
        return value
    mode_value = value.get("mode")
    status_path_value = value.get("status_path")
    terminal_values_value = value.get("terminal_values")
    if not isinstance(mode_value, str):
        raise ValueError("dup_call.mode must be a string")
    if status_path_value is not None and not isinstance(status_path_value, str):
        raise ValueError("dup_call.status_path must be a string")
    if not isinstance(terminal_values_value, list):
        raise ValueError("dup_call.terminal_values must be an array")
    terminal_values: list[str] = []
    for item in terminal_values_value:
        if not isinstance(item, str):
            raise ValueError("dup_call.terminal_values items must be strings")
        terminal_values.append(item)
    return DupCallSpec(
        mode=mode_value,
        status_path=status_path_value,
        terminal_values=terminal_values,
    )


def _optional_text(value: str | None) -> str | None:
    """归一化可选文本。

    :param value: 原始文本。
    :returns: 去空白文本或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_text_sequence(value: Sequence[str] | None) -> tuple[str, ...]:
    """归一化字符串序列。

    :param value: 原始字符串序列。
    :returns: 去空白后的字符串元组。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return ()
    return tuple(item.strip() for item in value if item.strip() != "")


__all__ = ["build_tool_schema", "tool"]
