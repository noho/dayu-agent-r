"""工具 schema 强类型契约。

本模块用于在 Engine 公共契约层描述 LLM 可见的工具 schema 形态。
schema 内的字段值（``type``、``function``）是 OpenAI 风格协议字面量，
本契约通过 :class:`Literal` 收窄；参数 schema 内部子节点遵循
:data:`JsonValue`，由具体工具发布方提供合法 JSON Schema。

设计要点：

- ``ToolParametersSchema`` 仅承诺三个稳定字段：``type``、``properties``、
  ``required``，外加可选的 ``additional_properties``。本模块不实现完整
  JSON Schema runtime validator；调用方仍必须保证 ``required`` 中的字段名
  都来自 ``properties``，否则该 schema 不是合法的 LLM-facing 参数契约。
- ``ToolSchema`` / ``ToolFunctionSchema`` 严格遵循 OpenAI Function-call
  格式以利 Runner 直接传递；其它 provider 适配由 Phase 1+ 处理。
- ``ToolTruncateSpec`` 是 Host ToolRuntime 使用的显式截断声明，不进入
  LLM-facing schema projection。
- ``binary_bytes`` 策略在 Host ToolRuntime public 结果中返回 base64 ASCII
  字符串，因为 ``JsonValue`` 不能承载原始 ``bytes``；它不是 OLD LLM
  projection 的 ``content_base64`` 包装对象。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from dayu.contracts.json_value import JsonValue

_TEXT_CHARS_LIMIT_KEY = "max_chars"
_TEXT_LINES_LIMIT_KEY = "max_lines"
_LIST_ITEMS_LIMIT_KEY = "max_items"
_BINARY_BYTES_LIMIT_KEY = "max_bytes"


@dataclass(frozen=True, slots=True)
class ToolParametersSchema:
    """工具参数 JSON Schema 顶层结构。

    :param type: 顶层 schema 类型，固定为 ``"object"``。
    :param properties: 顶层属性 schema 映射。
    :param required: 必填字段名元组。
    :param additional_properties: ``additionalProperties`` 字段；为
        ``None`` 表示不显式声明。
    """

    type: Literal["object"]
    properties: Mapping[str, JsonValue]
    required: tuple[str, ...]
    additional_properties: bool | None


@dataclass(frozen=True, slots=True)
class ToolFunctionSchema:
    """工具函数定义。

    :param name: 工具名（同一 Agent run 内必须唯一）。
    :param description: 工具描述，供 LLM 理解。
    :param parameters: 工具参数 schema。
    """

    name: str
    description: str
    parameters: ToolParametersSchema


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """工具 schema 顶层包装。

    :param type: schema 类型，固定为 ``"function"``。
    :param function: 工具函数定义。
    """

    type: Literal["function"]
    function: ToolFunctionSchema


class ToolTruncationStrategy(StrEnum):
    """工具结果截断策略。"""

    TEXT_CHARS = "text_chars"
    TEXT_LINES = "text_lines"
    LIST_ITEMS = "list_items"
    BINARY_BYTES = "binary_bytes"


_TRUNCATE_LIMIT_KEYS_BY_STRATEGY = {
    ToolTruncationStrategy.TEXT_CHARS: _TEXT_CHARS_LIMIT_KEY,
    ToolTruncationStrategy.TEXT_LINES: _TEXT_LINES_LIMIT_KEY,
    ToolTruncationStrategy.LIST_ITEMS: _LIST_ITEMS_LIMIT_KEY,
    ToolTruncationStrategy.BINARY_BYTES: _BINARY_BYTES_LIMIT_KEY,
}


@dataclass(frozen=True, slots=True)
class ToolTruncateSpec:
    """工具结果截断显式声明。

    P2 只把该声明作为 Host ToolRuntime 的显式触发条件；无声明或未启用
    由 ToolRuntime 解释为不截断。启用截断时，声明可以省略策略对应
    limit 与 TTL，由 runtime-neutral assembly helper 按 policy default 补齐
    effective spec；声明内已给出的 limit 仍在构造期校验。
    ``strategy=ToolTruncationStrategy.BINARY_BYTES`` 时，截断结果与补读结果的
    ``value`` 都是 base64 ASCII 字符串，``unit="bytes"`` 与 value summary
    表示原始字节大小。

    :param enabled: 是否启用截断。
    :param strategy: 截断策略。
    :param limits: 策略对应 limit 映射。
    :param target_field: wrapper dict 的顶层目标字段。
    :param field_path: wrapper dict 的嵌套目标路径。
    :param ttl_seconds: cursor 生存秒数；``None`` 表示使用 Host 默认值。
    :raises TypeError: ``strategy`` 不是 ``ToolTruncationStrategy``、``limits``
        值不是整数或 ``ttl_seconds`` 类型非法时抛出。
    :raises ValueError: ``enabled`` / ``strategy`` / ``limits`` / target 组合不一致时抛出。
    """

    enabled: bool
    strategy: ToolTruncationStrategy | None
    limits: Mapping[str, int]
    target_field: str | None
    field_path: tuple[str, ...] | None
    ttl_seconds: int | None

    def __post_init__(self) -> None:
        """校验截断声明字段组合。

        :returns: ``None``。
        :raises TypeError: ``strategy`` 不是枚举、``limits`` 值不是整数或
            ``ttl_seconds`` 类型非法时抛出。
        :raises ValueError: ``enabled`` / ``strategy`` / ``limits`` / target
            组合不一致时抛出。
        """

        if self.strategy is not None and not isinstance(
            self.strategy, ToolTruncationStrategy
        ):
            raise TypeError("ToolTruncateSpec.strategy must be ToolTruncationStrategy")
        if self.target_field is not None and self.field_path is not None:
            raise ValueError(
                "ToolTruncateSpec must not define both target_field and field_path"
            )
        if self.target_field is not None and self.target_field.strip() == "":
            raise ValueError("ToolTruncateSpec.target_field must be non-empty")
        if self.field_path is not None:
            if len(self.field_path) < 1:
                raise ValueError("ToolTruncateSpec.field_path must be non-empty")
            for item in self.field_path:
                if item.strip() == "":
                    raise ValueError("ToolTruncateSpec.field_path items must be non-empty")
        if self.ttl_seconds is not None:
            if isinstance(self.ttl_seconds, bool) or not isinstance(
                self.ttl_seconds, int
            ):
                raise TypeError("ToolTruncateSpec.ttl_seconds must be int")
            if self.ttl_seconds < 0:
                raise ValueError("ToolTruncateSpec.ttl_seconds must be non-negative")
        if not self.enabled:
            if self.strategy is not None:
                raise ValueError("disabled ToolTruncateSpec must not define strategy")
            if self.limits:
                raise ValueError("disabled ToolTruncateSpec must not define limits")
            return
        if self.strategy is None:
            raise ValueError("enabled ToolTruncateSpec requires strategy")
        expected_limit_key = _TRUNCATE_LIMIT_KEYS_BY_STRATEGY[self.strategy]
        if not set(self.limits.keys()).issubset({expected_limit_key}):
            raise ValueError(
                "enabled ToolTruncateSpec limits must match truncation strategy"
            )
        limit = self.limits.get(expected_limit_key)
        if limit is None:
            return
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("ToolTruncateSpec limits must contain integer values")
        if limit < 1:
            raise ValueError("ToolTruncateSpec limits must be positive")


def truncate_limit_key_for_strategy(strategy: ToolTruncationStrategy) -> str:
    """返回截断策略对应的 limit key。

    :param strategy: 截断策略。
    :returns: 该策略在 ``ToolTruncateSpec.limits`` 中使用的 limit key。
    :raises TypeError: ``strategy`` 不是 ``ToolTruncationStrategy`` 时抛出。
    """

    if not isinstance(strategy, ToolTruncationStrategy):
        raise TypeError("strategy must be ToolTruncationStrategy")
    return _TRUNCATE_LIMIT_KEYS_BY_STRATEGY[strategy]


__all__ = [
    "ToolSchema",
    "ToolFunctionSchema",
    "ToolParametersSchema",
    "ToolTruncateSpec",
    "ToolTruncationStrategy",
    "truncate_limit_key_for_strategy",
]
