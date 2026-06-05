"""OLD 风格工具声明收集器。

本模块只收集迁移工具通过 decorator 挂载的声明 metadata，并把它们整理成
后续 provider 可消费的 ``CollectedLegacyTool``。它不是 OLD
``ToolRegistry``：不执行工具、不做路径白名单校验、不拥有截断运行时，也
不注册 ``fetch_more``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext
from dayu.contracts.tool_schema import ToolSchema, ToolTruncateSpec

_MetadataValue = str | Sequence[str] | ToolTruncateSpec | None


LegacyToolKeywordValue = JsonValue | BatchToolExecutionContext | None
"""迁移同步工具可接收的关键字参数值。"""


class LegacySyncToolCallable(Protocol):
    """迁移同步工具函数协议。"""

    def __call__(self, **keyword_arguments: LegacyToolKeywordValue) -> JsonValue:
        """执行同步工具函数。

        :param keyword_arguments: adapter 投影后的关键字参数。
        :returns: JSON 兼容工具返回值。
        :raises Exception: 工具函数可抛出业务异常，由 adapter 投影为 current
            ``ToolFailedOutcome``。
        """

        ...


@dataclass(frozen=True, slots=True)
class CollectedLegacyTool:
    """收集到的 OLD 风格工具声明。

    :param name: 工具名。
    :param callable: 同步工具函数。
    :param schema: current LLM-facing 工具 schema。
    :param tags: 工具标签。
    :param truncate: current 截断声明。
    :param file_path_params: 需要外部路径策略验证的参数名。
    :param execution_context_param_name: 需要注入 batch context 的参数名。
    :param display_name: 展示名。
    :param summary_params: 摘要参数名。
    """

    name: str
    callable: LegacySyncToolCallable
    schema: ToolSchema
    tags: tuple[str, ...]
    truncate: ToolTruncateSpec | None
    file_path_params: tuple[str, ...]
    execution_context_param_name: str | None
    display_name: str | None
    summary_params: tuple[str, ...] | None


class LegacyToolDeclarationCollector:
    """OLD 注册函数可调用的声明收集器。

    该 collector 只实现迁移声明收集所需的窄接口。``register_allowed_paths``
    仅记录调用事实，不产生可信白名单，也不被 adapter 当作路径安全证据。
    """

    def __init__(self) -> None:
        """初始化空 collector。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._tools: list[CollectedLegacyTool] = []
        self._allowed_path_calls: list[tuple[Path, ...]] = []

    def register(
        self,
        name: str,
        func: LegacySyncToolCallable,
        schema: ToolSchema,
    ) -> None:
        """登记一个迁移工具声明。

        :param name: 工具名。
        :param func: 同步工具函数。
        :param schema: current 工具 schema。
        :returns: ``None``。
        :raises ValueError: 工具名、schema 名称或重复注册非法时抛出。
        """

        if name.strip() == "":
            raise ValueError("legacy tool name must be non-empty")
        if schema.function.name != name:
            raise ValueError("legacy tool schema name must match registered name")
        if any(tool.name == name for tool in self._tools):
            raise ValueError(f"duplicate legacy tool name: {name}")
        self._tools.append(
            CollectedLegacyTool(
                name=name,
                callable=func,
                schema=schema,
                tags=_read_string_tuple(func, "__tool_tags__"),
                truncate=cast(ToolTruncateSpec | None, _read_optional(func, "__tool_truncate__")),
                file_path_params=_read_string_tuple(func, "__tool_file_path_params__"),
                execution_context_param_name=_read_optional_text(
                    func,
                    "__tool_execution_context_param_name__",
                ),
                display_name=_read_optional_text(func, "__tool_display_name__"),
                summary_params=_read_optional_string_tuple(
                    func,
                    "__tool_summary_params__",
                ),
            )
        )

    def register_allowed_paths(self, paths: Sequence[Path]) -> None:
        """记录 OLD 注册函数传入的路径列表。

        该方法不解析、不校验、不归一化路径，也不把记录值暴露为可信白名单。
        provider 必须通过 ``ToolPathValidationPolicy`` 显式传入真实路径策略。

        :param paths: OLD 注册函数传入的路径序列。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._allowed_path_calls.append(tuple(paths))

    def collected_tools(self) -> tuple[CollectedLegacyTool, ...]:
        """返回已收集的工具声明。

        :returns: 工具声明元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._tools)


def _read_optional(
    func: LegacySyncToolCallable,
    attribute_name: str,
) -> _MetadataValue:
    """读取 decorator 动态 metadata。

    迁移 decorator 必须把 OLD 声明 metadata 挂在函数对象上；这里集中使用
    ``getattr`` 是为了跨旧函数签名读取这些动态属性，不用它绕过业务边界。

    :param func: 迁移工具函数。
    :param attribute_name: metadata 属性名。
    :returns: 属性值或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    return cast(_MetadataValue, getattr(func, attribute_name, None))


def _read_optional_text(
    func: LegacySyncToolCallable,
    attribute_name: str,
) -> str | None:
    """读取可选文本 metadata。

    :param func: 迁移工具函数。
    :param attribute_name: metadata 属性名。
    :returns: 非空字符串或 ``None``。
    :raises TypeError: metadata 类型非法时抛出。
    """

    value = _read_optional(func, attribute_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{attribute_name} must be str")
    normalized = value.strip()
    return normalized if normalized else None


def _read_string_tuple(
    func: LegacySyncToolCallable,
    attribute_name: str,
) -> tuple[str, ...]:
    """读取字符串序列 metadata。

    :param func: 迁移工具函数。
    :param attribute_name: metadata 属性名。
    :returns: 字符串元组。
    :raises TypeError: metadata 类型非法时抛出。
    """

    value = _read_optional(func, attribute_name)
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{attribute_name} must be a string sequence")
    if not isinstance(value, Sequence):
        raise TypeError(f"{attribute_name} must be a string sequence")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{attribute_name} items must be str")
        normalized = item.strip()
        if normalized:
            items.append(normalized)
    return tuple(items)


def _read_optional_string_tuple(
    func: LegacySyncToolCallable,
    attribute_name: str,
) -> tuple[str, ...] | None:
    """读取可选字符串序列 metadata。

    :param func: 迁移工具函数。
    :param attribute_name: metadata 属性名。
    :returns: 字符串元组或 ``None``。
    :raises TypeError: metadata 类型非法时抛出。
    """

    value = _read_optional(func, attribute_name)
    if value is None:
        return None
    if isinstance(value, str):
        raise TypeError(f"{attribute_name} must be a string sequence")
    if not isinstance(value, Sequence):
        raise TypeError(f"{attribute_name} must be a string sequence")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{attribute_name} items must be str")
        normalized = item.strip()
        if normalized:
            items.append(normalized)
    return tuple(items)


def schema_parameters_json(schema: ToolSchema) -> Mapping[str, JsonValue]:
    """返回工具参数 schema 的 JSON object 视图。

    :param schema: current 工具 schema。
    :returns: 参数 schema JSON mapping。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "type": schema.function.parameters.type,
        "properties": schema.function.parameters.properties,
        "required": list(schema.function.parameters.required),
        "additionalProperties": schema.function.parameters.additional_properties,
    }
