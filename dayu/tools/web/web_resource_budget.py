"""Web 工具资源预算契约。

本模块是 Web HTTP、浏览器与诊断资源上限的唯一 typed 真源。调用方只能
传递完整的 :class:`WebResourceBudget`，不得在各消费路径重复定义上限。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from dayu.contracts.json_value import JsonValue

_MEBIBYTE_BYTES: Final[int] = 1024 * 1024


@dataclass(frozen=True, slots=True)
class WebResourceBudget:
    """Web 工具单次资源预算。

    Args:
        wire_body_bytes: 单次 HTTP response 实读 wire bytes 上限。
        decoded_body_bytes: 每一内容编码解码层及最终 body 上限。
        warmup_body_bytes: warmup 最多消费的 wire bytes。
        browser_dom_chars: 浏览器 DOM 保守序列化字符上限。
        browser_text_chars: 浏览器完整文本投影字符上限。
        diagnostic_error_chars: 脱敏后诊断错误文本字符上限。
        diagnostic_events: 单个诊断 artifact 的事件数量上限。

    Returns:
        不可变资源预算实例。

    Raises:
        ValueError: 任一字段不是非 bool 正整数时抛出。
    """

    wire_body_bytes: int = 25 * _MEBIBYTE_BYTES
    decoded_body_bytes: int = 50 * _MEBIBYTE_BYTES
    warmup_body_bytes: int = 64 * 1024
    browser_dom_chars: int = 5_000_000
    browser_text_chars: int = 1_000_000
    diagnostic_error_chars: int = 1_024
    diagnostic_events: int = 80

    def __post_init__(self) -> None:
        """校验所有预算字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 任一字段不是非 bool 正整数时抛出。
        """

        budget_values = (
            ("wire_body_bytes", self.wire_body_bytes),
            ("decoded_body_bytes", self.decoded_body_bytes),
            ("warmup_body_bytes", self.warmup_body_bytes),
            ("browser_dom_chars", self.browser_dom_chars),
            ("browser_text_chars", self.browser_text_chars),
            ("diagnostic_error_chars", self.diagnostic_error_chars),
            ("diagnostic_events", self.diagnostic_events),
        )
        for field_name, value in budget_values:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(
                    f"web resource budget.{field_name} must be a positive integer"
                )


_RESOURCE_BUDGET_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "wire_body_bytes",
        "decoded_body_bytes",
        "warmup_body_bytes",
        "browser_dom_chars",
        "browser_text_chars",
        "diagnostic_error_chars",
        "diagnostic_events",
    }
)


def web_resource_budget_from_json(value: JsonValue) -> WebResourceBudget:
    """从完整 JSON object 构造资源预算。

    Args:
        value: provider ``resource_budget`` 字段的原始 JSON 值。

    Returns:
        完整、已校验的资源预算。

    Raises:
        ValueError: 值不是 object、字段集合不完整、含未知字段，或任一值
            不是非 bool 正整数时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError("web provider config.resource_budget must be an object")
    actual_fields = frozenset(str(key) for key in value.keys())
    missing_fields = sorted(_RESOURCE_BUDGET_FIELDS - actual_fields)
    unknown_fields = sorted(actual_fields - _RESOURCE_BUDGET_FIELDS)
    if missing_fields or unknown_fields:
        details: list[str] = []
        if missing_fields:
            details.append(f"missing fields: {', '.join(missing_fields)}")
        if unknown_fields:
            details.append(f"unknown fields: {', '.join(unknown_fields)}")
        raise ValueError(
            "web provider config.resource_budget must be a complete object ("
            + "; ".join(details)
            + ")"
        )

    parsed: dict[str, int] = {}
    for field_name in sorted(_RESOURCE_BUDGET_FIELDS):
        field_value = value[field_name]
        if (
            isinstance(field_value, bool)
            or not isinstance(field_value, int)
            or field_value <= 0
        ):
            raise ValueError(
                f"web provider config.resource_budget.{field_name} must be a positive integer"
            )
        parsed[field_name] = field_value
    return WebResourceBudget(
        wire_body_bytes=parsed["wire_body_bytes"],
        decoded_body_bytes=parsed["decoded_body_bytes"],
        warmup_body_bytes=parsed["warmup_body_bytes"],
        browser_dom_chars=parsed["browser_dom_chars"],
        browser_text_chars=parsed["browser_text_chars"],
        diagnostic_error_chars=parsed["diagnostic_error_chars"],
        diagnostic_events=parsed["diagnostic_events"],
    )
