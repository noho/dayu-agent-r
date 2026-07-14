"""Web 工具分 owner 资源预算契约。

本模块分别拥有 HTTP、浏览器与诊断资源上限的 typed value、默认常量和
nested JSON parser。下游执行器只能接收自己消费的 child budget；聚合值
只用于 ``WebToolsConfig`` 的不可变配置快照。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from dayu.contracts.json_value import JsonValue

_MEBI_UNIT: Final[int] = 1_024 * 1_024
_HTTP_GROUP: Final[str] = "http"
_BROWSER_GROUP: Final[str] = "browser"
_DIAGNOSTICS_GROUP: Final[str] = "diagnostics"
_RESOURCE_BUDGET_GROUPS: Final[frozenset[str]] = frozenset(
    {_HTTP_GROUP, _BROWSER_GROUP, _DIAGNOSTICS_GROUP}
)


def _validate_positive_integer(*, field_path: str, value: int) -> None:
    """校验一个 budget owner 字段是非 bool 正整数。

    Args:
        field_path: 用于异常定位的完整字段路径。
        value: 待校验字段值。

    Returns:
        无。

    Raises:
        ValueError: 值不是非 bool 正整数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_path} must be a positive integer")


@dataclass(frozen=True, slots=True)
class HttpResourceBudget:
    """单次 HTTP response materialization 预算。

    Args:
        wire_body_bytes: 实读 wire bytes 上限。
        decoded_body_bytes: 每层解码结果及最终 body 字节上限。

    Returns:
        不可变 HTTP 资源预算。

    Raises:
        ValueError: 任一字段不是非 bool 正整数时抛出。
    """

    wire_body_bytes: int
    decoded_body_bytes: int

    def __post_init__(self) -> None:
        """校验 HTTP owner 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 任一字段不是非 bool 正整数时抛出。
        """

        _validate_positive_integer(
            field_path="web resource budget.http.wire_body_bytes",
            value=self.wire_body_bytes,
        )
        _validate_positive_integer(
            field_path="web resource budget.http.decoded_body_bytes",
            value=self.decoded_body_bytes,
        )


@dataclass(frozen=True, slots=True)
class BrowserResourceBudget:
    """单次浏览器 warmup 与页面投影预算。

    Args:
        warmup_body_bytes: warmup 最多消费的 wire bytes。
        dom_chars: 浏览器 DOM 保守序列化字符上限。
        text_chars: 浏览器完整文本与 Markdown 字符上限。

    Returns:
        不可变浏览器资源预算。

    Raises:
        ValueError: 任一字段不是非 bool 正整数时抛出。
    """

    warmup_body_bytes: int
    dom_chars: int
    text_chars: int

    def __post_init__(self) -> None:
        """校验浏览器 owner 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 任一字段不是非 bool 正整数时抛出。
        """

        _validate_positive_integer(
            field_path="web resource budget.browser.warmup_body_bytes",
            value=self.warmup_body_bytes,
        )
        _validate_positive_integer(
            field_path="web resource budget.browser.dom_chars",
            value=self.dom_chars,
        )
        _validate_positive_integer(
            field_path="web resource budget.browser.text_chars",
            value=self.text_chars,
        )


@dataclass(frozen=True, slots=True)
class DiagnosticResourceBudget:
    """单次 Web diagnostics 投影预算。

    Args:
        error_chars: 脱敏后错误文本字符上限。
        events: 单个诊断 artifact 的事件数量上限。

    Returns:
        不可变诊断资源预算。

    Raises:
        ValueError: 任一字段不是非 bool 正整数时抛出。
    """

    error_chars: int
    events: int

    def __post_init__(self) -> None:
        """校验诊断 owner 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 任一字段不是非 bool 正整数时抛出。
        """

        _validate_positive_integer(
            field_path="web resource budget.diagnostics.error_chars",
            value=self.error_chars,
        )
        _validate_positive_integer(
            field_path="web resource budget.diagnostics.events",
            value=self.events,
        )


@dataclass(frozen=True, slots=True)
class WebResourceBudgets:
    """Web 配置快照中的三个 child budget 纯组合。

    Args:
        http: HTTP response materialization 预算。
        browser: 浏览器 warmup 与页面投影预算。
        diagnostics: diagnostics 投影预算。

    Returns:
        不可变纯组合；不执行跨 owner 校验。

    Raises:
        无。
    """

    http: HttpResourceBudget
    browser: BrowserResourceBudget
    diagnostics: DiagnosticResourceBudget


DEFAULT_HTTP_RESOURCE_BUDGET: Final[HttpResourceBudget] = HttpResourceBudget(
    wire_body_bytes=128 * _MEBI_UNIT,
    decoded_body_bytes=256 * _MEBI_UNIT,
)
DEFAULT_BROWSER_RESOURCE_BUDGET: Final[BrowserResourceBudget] = BrowserResourceBudget(
    warmup_body_bytes=1 * _MEBI_UNIT,
    dom_chars=16 * _MEBI_UNIT,
    text_chars=8 * _MEBI_UNIT,
)
DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET: Final[DiagnosticResourceBudget] = (
    DiagnosticResourceBudget(
        error_chars=8_192,
        events=512,
    )
)


def _parse_group(
    value: JsonValue,
    *,
    group_name: str,
    allowed_fields: frozenset[str],
) -> Mapping[str, JsonValue]:
    """校验一个 nested budget group 的 object shape。

    Args:
        value: group 的原始 JSON 值。
        group_name: group 名称。
        allowed_fields: 当前 owner 允许的字段集合。

    Returns:
        已确认 object shape 且无未知字段的映射。

    Raises:
        ValueError: group 不是 object 或包含未知字段时抛出。
    """

    field_path = f"web provider config.resource_budget.{group_name}"
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_path} must be an object")
    actual_fields = frozenset(str(key) for key in value.keys())
    unknown_fields = sorted(actual_fields - allowed_fields)
    if unknown_fields:
        raise ValueError(
            f"{field_path} has unknown fields: {', '.join(unknown_fields)}"
        )
    return value


def _parse_positive_integer_field(
    group: Mapping[str, JsonValue],
    *,
    group_name: str,
    field_name: str,
    default: int,
) -> int:
    """读取一个可局部缺失的正整数 budget 字段。

    Args:
        group: 已校验 object shape 的 owner group。
        group_name: group 名称。
        field_name: 字段名称。
        default: 字段缺失时使用的 child owner typed default。

    Returns:
        已校验的正整数，或对应 typed default。

    Raises:
        ValueError: 已存在字段不是非 bool 正整数时抛出。
    """

    if field_name not in group:
        return default
    value = group[field_name]
    field_path = f"web provider config.resource_budget.{group_name}.{field_name}"
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_path} must be a positive integer")
    return value


def web_resource_budgets_from_json(value: JsonValue) -> WebResourceBudgets:
    """从 nested JSON object 构造三个 owner budget。

    缺失 group 或字段只补对应 child owner 的 typed default；已提供 sibling
    保持不变。unknown group/field、错误 object 类型和非法数值均精确失败。

    Args:
        value: provider ``resource_budget`` 字段的原始 JSON 值。

    Returns:
        无 default 的 ``WebResourceBudgets`` 纯组合。

    Raises:
        ValueError: object、group、field 或字段值不符合契约时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError("web provider config.resource_budget must be an object")
    actual_groups = frozenset(str(key) for key in value.keys())
    unknown_groups = sorted(actual_groups - _RESOURCE_BUDGET_GROUPS)
    if unknown_groups:
        raise ValueError(
            "web provider config.resource_budget has unknown groups: "
            + ", ".join(unknown_groups)
        )

    http_group = _parse_group(
        value.get(_HTTP_GROUP, {}),
        group_name=_HTTP_GROUP,
        allowed_fields=frozenset({"wire_body_bytes", "decoded_body_bytes"}),
    )
    browser_group = _parse_group(
        value.get(_BROWSER_GROUP, {}),
        group_name=_BROWSER_GROUP,
        allowed_fields=frozenset({"warmup_body_bytes", "dom_chars", "text_chars"}),
    )
    diagnostics_group = _parse_group(
        value.get(_DIAGNOSTICS_GROUP, {}),
        group_name=_DIAGNOSTICS_GROUP,
        allowed_fields=frozenset({"error_chars", "events"}),
    )

    return WebResourceBudgets(
        http=HttpResourceBudget(
            wire_body_bytes=_parse_positive_integer_field(
                http_group,
                group_name=_HTTP_GROUP,
                field_name="wire_body_bytes",
                default=DEFAULT_HTTP_RESOURCE_BUDGET.wire_body_bytes,
            ),
            decoded_body_bytes=_parse_positive_integer_field(
                http_group,
                group_name=_HTTP_GROUP,
                field_name="decoded_body_bytes",
                default=DEFAULT_HTTP_RESOURCE_BUDGET.decoded_body_bytes,
            ),
        ),
        browser=BrowserResourceBudget(
            warmup_body_bytes=_parse_positive_integer_field(
                browser_group,
                group_name=_BROWSER_GROUP,
                field_name="warmup_body_bytes",
                default=DEFAULT_BROWSER_RESOURCE_BUDGET.warmup_body_bytes,
            ),
            dom_chars=_parse_positive_integer_field(
                browser_group,
                group_name=_BROWSER_GROUP,
                field_name="dom_chars",
                default=DEFAULT_BROWSER_RESOURCE_BUDGET.dom_chars,
            ),
            text_chars=_parse_positive_integer_field(
                browser_group,
                group_name=_BROWSER_GROUP,
                field_name="text_chars",
                default=DEFAULT_BROWSER_RESOURCE_BUDGET.text_chars,
            ),
        ),
        diagnostics=DiagnosticResourceBudget(
            error_chars=_parse_positive_integer_field(
                diagnostics_group,
                group_name=_DIAGNOSTICS_GROUP,
                field_name="error_chars",
                default=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET.error_chars,
            ),
            events=_parse_positive_integer_field(
                diagnostics_group,
                group_name=_DIAGNOSTICS_GROUP,
                field_name="events",
                default=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET.events,
            ),
        ),
    )
