"""OLD 声明 metadata 到 current 工具契约的内部辅助。

本模块只引用当前 ``dayu.contracts.tool_schema`` 的截断契约。它不定义、
复制或导出 OLD ``ToolTruncateSpec`` 运行时合同。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_schema import (
    ToolTruncateSpec,
    ToolTruncationStrategy,
    truncate_limit_key_for_strategy,
)

from .exceptions import ConfigError

_TRUNCATION_STRATEGIES_BY_VALUE: Mapping[str, ToolTruncationStrategy] = {
    ToolTruncationStrategy.TEXT_CHARS.value: ToolTruncationStrategy.TEXT_CHARS,
    ToolTruncationStrategy.TEXT_LINES.value: ToolTruncationStrategy.TEXT_LINES,
    ToolTruncationStrategy.LIST_ITEMS.value: ToolTruncationStrategy.LIST_ITEMS,
    ToolTruncationStrategy.BINARY_BYTES.value: ToolTruncationStrategy.BINARY_BYTES,
}


@dataclass(slots=True)
class DupCallSpec:
    """OLD 重复调用声明 metadata。

    S2 只收集该声明以便后续 slice 能分类导入闭包；当前 adapter 不把它投影
    到 ToolRuntime，也不改变 current duplicate governance。

    :param mode: 重复调用模式。
    :param status_path: 状态字段路径。
    :param terminal_values: 终态值集合。
    """

    mode: str
    status_path: str | None = None
    terminal_values: list[str] | None = None

    def __post_init__(self) -> None:
        """校验重复调用 metadata 的最小结构。

        :returns: ``None``。
        :raises ConfigError: 字段为空或取值非法时抛出。
        """

        normalized_mode = self.mode.strip()
        if normalized_mode != "poll_until_terminal":
            raise ConfigError("tool_schema", None, f"unsupported dup_call.mode: {self.mode}")
        if self.status_path is None or self.status_path.strip() == "":
            raise ConfigError(
                "tool_schema",
                None,
                "dup_call.status_path is required when mode=poll_until_terminal",
            )
        if self.terminal_values is None or not self.terminal_values:
            raise ConfigError(
                "tool_schema",
                None,
                "dup_call.terminal_values must be a non-empty list",
            )
        normalized_values = [value.strip() for value in self.terminal_values]
        if any(value == "" for value in normalized_values):
            raise ConfigError(
                "tool_schema",
                None,
                "dup_call.terminal_values cannot contain blank values",
            )
        self.mode = normalized_mode
        self.status_path = self.status_path.strip()
        self.terminal_values = normalized_values


def normalize_truncate_spec(
    truncate: ToolTruncateSpec | Mapping[str, JsonValue] | None,
) -> ToolTruncateSpec | None:
    """把 OLD 风格截断声明转换为 current 截断声明。

    :param truncate: current ``ToolTruncateSpec``、OLD 风格 JSON mapping 或
        ``None``。
    :returns: current ``ToolTruncateSpec``；禁用或缺失时返回 ``None``。
    :raises ConfigError: OLD mapping 字段组合非法时抛出。
    """

    if truncate is None:
        return None
    if isinstance(truncate, ToolTruncateSpec):
        return truncate if truncate.enabled else None

    enabled_value = truncate.get("enabled")
    if enabled_value is not True:
        return None
    strategy_value = truncate.get("strategy")
    if not isinstance(strategy_value, str):
        raise ConfigError("tool_schema", None, "truncate.strategy is required")
    strategy = _TRUNCATION_STRATEGIES_BY_VALUE.get(strategy_value)
    if strategy is None:
        raise ConfigError(
            "tool_schema",
            None,
            f"unsupported truncate.strategy: {strategy_value}",
        )
    limits_value = truncate.get("limits")
    limits = _normalize_limits(
        strategy=strategy,
        limits_value=limits_value,
    )
    target_field_value = truncate.get("target_field")
    target_field = _optional_text(target_field_value, field_name="truncate.target_field")
    field_path_value = truncate.get("field_path")
    field_path = _optional_field_path(field_path_value)
    return ToolTruncateSpec(
        enabled=True,
        strategy=strategy,
        limits=limits,
        target_field=target_field,
        field_path=field_path,
        ttl_seconds=None,
    )


def _normalize_limits(
    *,
    strategy: ToolTruncationStrategy,
    limits_value: JsonValue,
) -> Mapping[str, int]:
    """校验并归一化 OLD limits mapping。

    :param strategy: current 截断策略。
    :param limits_value: OLD limits JSON 值。
    :returns: current limits mapping。
    :raises ConfigError: limits 缺失或与策略不匹配时抛出。
    """

    if not isinstance(limits_value, Mapping):
        raise ConfigError("tool_schema", None, "truncate.limits must be an object")
    limit_key = truncate_limit_key_for_strategy(strategy)
    if set(limits_value.keys()) != {limit_key}:
        raise ConfigError(
            "tool_schema",
            None,
            f"truncate.limits must contain only {limit_key!r}",
        )
    limit_value = limits_value[limit_key]
    if isinstance(limit_value, bool) or not isinstance(limit_value, int) or limit_value < 1:
        raise ConfigError(
            "tool_schema",
            None,
            f"truncate.limits.{limit_key} must be a positive integer",
        )
    return {limit_key: limit_value}


def _optional_text(value: JsonValue, *, field_name: str) -> str | None:
    """读取可选非空文本字段。

    :param value: JSON 字段值。
    :param field_name: 错误消息字段名。
    :returns: 去空白后的文本或 ``None``。
    :raises ConfigError: 字段不是字符串或为空白时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("tool_schema", None, f"{field_name} must be a string")
    normalized = value.strip()
    if normalized == "":
        raise ConfigError("tool_schema", None, f"{field_name} must be non-empty")
    return normalized


def _optional_field_path(value: JsonValue) -> tuple[str, ...] | None:
    """读取 current field_path 字段。

    :param value: JSON 字段值。
    :returns: 字段路径元组或 ``None``。
    :raises ConfigError: 字段路径非法时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, list):
        raise ConfigError("tool_schema", None, "truncate.field_path must be an array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ConfigError(
                "tool_schema",
                None,
                "truncate.field_path items must be non-empty strings",
            )
        items.append(item.strip())
    return tuple(items)


__all__ = [
    "DupCallSpec",
    "ToolTruncateSpec",
    "ToolTruncationStrategy",
    "normalize_truncate_spec",
]
