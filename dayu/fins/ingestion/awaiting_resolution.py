"""Fins awaiting provider 恢复模式公共契约。

本模块是 awaiting resolution 配置字段、closed typed 模式与严格解析规则的
唯一 owner。Tool provider 与 Service composition 只消费这里产生的语义。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from dayu.contracts.json_value import JsonValue

AWAITING_RESOLUTION_MODE_CONFIG_FIELD: Final[str] = "awaiting_resolution_mode"
"""Fins awaiting provider 恢复模式的配置字段名。"""


class AwaitingResolutionMode(StrEnum):
    """Fins awaiting provider 支持的恢复模式。"""

    POLL = "poll"
    CALLBACK = "callback"
    MANUAL = "manual"


def parse_awaiting_resolution_mode(
    config: Mapping[str, JsonValue],
) -> AwaitingResolutionMode:
    """严格解析 Fins awaiting provider 的恢复模式。

    Args:
        config: provider 自有的 JSON 配置。

    Returns:
        已校验的 closed typed 恢复模式。

    Raises:
        ValueError: 字段缺失、不是字符串或不属于受支持闭集时抛出。
    """

    if AWAITING_RESOLUTION_MODE_CONFIG_FIELD not in config:
        raise ValueError(
            "Fins awaiting provider config.awaiting_resolution_mode is required"
        )
    value = config[AWAITING_RESOLUTION_MODE_CONFIG_FIELD]
    if not isinstance(value, str):
        raise ValueError(
            "Fins awaiting provider config.awaiting_resolution_mode must be a string"
        )
    try:
        return AwaitingResolutionMode(value)
    except ValueError as exc:
        raise ValueError(
            "Fins awaiting provider config.awaiting_resolution_mode must be one of: "
            "poll, callback, manual"
        ) from exc


__all__: tuple[str, ...] = (
    "AWAITING_RESOLUTION_MODE_CONFIG_FIELD",
    "AwaitingResolutionMode",
    "parse_awaiting_resolution_mode",
)
