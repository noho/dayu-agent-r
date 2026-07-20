"""Web tools 的当前 ToolsDiscovery provider。

本模块只负责解析 Web provider 配置，并通过原生 ``ToolDefinition`` 暴露
``search_web`` 与 ``fetch_web_page``。URL 安全策略、请求超时、搜索结果
上限、正文截断和 Playwright 配置都通过 provider config 显式闭包投影给
工具 callable。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.runtime.tools_discovery import (
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

from .web_http_session import WebHttpTransportPolicy
from .web_resource_budget import WebResourceBudgets, web_resource_budgets_from_json
from .web_tools import WebToolsConfig, build_web_tool_definitions

_PROVIDER_ID: Final[str] = "web-tools"
_VERSION_REF: Final[str] = "web-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.tools.web"
_CONFIG_PROVIDER_FIELD: Final[str] = "provider"
_CONFIG_REQUEST_TIMEOUT_SECONDS_FIELD: Final[str] = "request_timeout_seconds"
_CONFIG_MAX_SEARCH_RESULTS_FIELD: Final[str] = "max_search_results"
_CONFIG_FETCH_TRUNCATE_CHARS_FIELD: Final[str] = "fetch_truncate_chars"
_CONFIG_ALLOW_PRIVATE_NETWORK_URL_FIELD: Final[str] = "allow_private_network_url"
_CONFIG_ALLOW_CUSTOM_PORT_URL_FIELD: Final[str] = "allow_custom_port_url"
_CONFIG_DNS_PEER_PROOF_ENABLED_FIELD: Final[str] = "dns_peer_proof_enabled"
_CONFIG_ALLOW_ENVIRONMENT_PROXY_FIELD: Final[str] = "allow_environment_proxy"
_CONFIG_BROWSER_ENABLED_FIELD: Final[str] = "browser_enabled"
_CONFIG_PLAYWRIGHT_CHANNEL_FIELD: Final[str] = "playwright_channel"
_CONFIG_PLAYWRIGHT_STORAGE_STATE_DIR_FIELD: Final[str] = "playwright_storage_state_dir"
_CONFIG_RESOURCE_BUDGET_FIELD: Final[str] = "resource_budget"
_CONFIG_FIELDS: Final[frozenset[str]] = frozenset(
    {
        _CONFIG_PROVIDER_FIELD,
        _CONFIG_REQUEST_TIMEOUT_SECONDS_FIELD,
        _CONFIG_MAX_SEARCH_RESULTS_FIELD,
        _CONFIG_FETCH_TRUNCATE_CHARS_FIELD,
        _CONFIG_ALLOW_PRIVATE_NETWORK_URL_FIELD,
        _CONFIG_ALLOW_CUSTOM_PORT_URL_FIELD,
        _CONFIG_DNS_PEER_PROOF_ENABLED_FIELD,
        _CONFIG_ALLOW_ENVIRONMENT_PROXY_FIELD,
        _CONFIG_BROWSER_ENABLED_FIELD,
        _CONFIG_PLAYWRIGHT_CHANNEL_FIELD,
        _CONFIG_PLAYWRIGHT_STORAGE_STATE_DIR_FIELD,
        _CONFIG_RESOURCE_BUDGET_FIELD,
    }
)
_WEB_TOOL_NAMES: Final[tuple[str, ...]] = ("search_web", "fetch_web_page")
_DEFAULT_PROVIDER: Final[str] = "auto"
_DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0
_DEFAULT_MAX_SEARCH_RESULTS: Final[int] = 8
_DEFAULT_FETCH_TRUNCATE_CHARS: Final[int] = 80_000
_DEFAULT_ALLOW_PRIVATE_NETWORK_URL: Final[bool] = True
_DEFAULT_ALLOW_CUSTOM_PORT_URL: Final[bool] = True
_DEFAULT_DNS_PEER_PROOF_ENABLED: Final[bool] = False
_DEFAULT_ALLOW_ENVIRONMENT_PROXY: Final[bool] = True
_DEFAULT_BROWSER_ENABLED: Final[bool] = True
_DEFAULT_PLAYWRIGHT_CHANNEL: Final[str] = "chrome"
_DEFAULT_PLAYWRIGHT_STORAGE_STATE_DIR: Final[str] = ".dayu/web_tools_storage_states"


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Web tools。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出，包含 ``search_web`` 与 ``fetch_web_page``。

    Raises:
        ValueError: provider config 非法，或 native 定义集合不符合本 slice
            预期时抛出。
    """

    definitions = build_web_tool_definitions(_parse_config(spec.config))
    _validate_web_definitions(definitions)
    source_ref = _source_ref()
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=definitions,
    )


def _parse_config(config: Mapping[str, JsonValue]) -> WebToolsConfig:
    """从 provider config 解析 WebToolsConfig。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        Web 工具配置。

    Raises:
        ValueError: 字段类型或取值非法时抛出。
    """

    unknown_fields = set(config) - _CONFIG_FIELDS
    if unknown_fields:
        unknown_field = min(unknown_fields)
        raise ValueError(
            f"web provider config.{unknown_field} is not a supported field"
        )

    allow_private_network_url = _bool_default(
        config,
        _CONFIG_ALLOW_PRIVATE_NETWORK_URL_FIELD,
        default=_DEFAULT_ALLOW_PRIVATE_NETWORK_URL,
    )
    allow_custom_port_url = _bool_default(
        config,
        _CONFIG_ALLOW_CUSTOM_PORT_URL_FIELD,
        default=_DEFAULT_ALLOW_CUSTOM_PORT_URL,
    )
    dns_peer_proof_enabled = _bool_default(
        config,
        _CONFIG_DNS_PEER_PROOF_ENABLED_FIELD,
        default=_DEFAULT_DNS_PEER_PROOF_ENABLED,
    )
    allow_environment_proxy = _bool_default(
        config,
        _CONFIG_ALLOW_ENVIRONMENT_PROXY_FIELD,
        default=_DEFAULT_ALLOW_ENVIRONMENT_PROXY,
    )
    browser_enabled = _bool_default(
        config,
        _CONFIG_BROWSER_ENABLED_FIELD,
        default=_DEFAULT_BROWSER_ENABLED,
    )
    return WebToolsConfig(
        allow_private_network_url=allow_private_network_url,
        allow_custom_port_url=allow_custom_port_url,
        browser_enabled=browser_enabled,
        transport_policy=WebHttpTransportPolicy(
            dns_peer_proof_enabled=dns_peer_proof_enabled,
            allow_environment_proxy=allow_environment_proxy,
        ),
        resource_budgets=_resource_budgets_default(config),
        provider=_parse_provider(config, _DEFAULT_PROVIDER),
        request_timeout_seconds=_positive_float(
            config,
            _CONFIG_REQUEST_TIMEOUT_SECONDS_FIELD,
            _DEFAULT_REQUEST_TIMEOUT_SECONDS,
        ),
        max_search_results=_positive_int(
            config,
            _CONFIG_MAX_SEARCH_RESULTS_FIELD,
            _DEFAULT_MAX_SEARCH_RESULTS,
        ),
        fetch_truncate_chars=_positive_int(
            config,
            _CONFIG_FETCH_TRUNCATE_CHARS_FIELD,
            _DEFAULT_FETCH_TRUNCATE_CHARS,
        ),
        playwright_channel=_optional_text_default(
            config,
            _CONFIG_PLAYWRIGHT_CHANNEL_FIELD,
            _DEFAULT_PLAYWRIGHT_CHANNEL,
        ),
        playwright_storage_state_dir=_text_default(
            config,
            _CONFIG_PLAYWRIGHT_STORAGE_STATE_DIR_FIELD,
            _DEFAULT_PLAYWRIGHT_STORAGE_STATE_DIR,
        ),
    )


def _resource_budgets_default(
    config: Mapping[str, JsonValue],
) -> WebResourceBudgets:
    """读取 nested Web 资源预算并按 child owner 局部补默认。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        已校验的三个 child budget 纯组合。

    Raises:
        ValueError: ``resource_budget`` 或其 group/field 非法时抛出。
    """

    if _CONFIG_RESOURCE_BUDGET_FIELD not in config:
        return web_resource_budgets_from_json({})
    return web_resource_budgets_from_json(config[_CONFIG_RESOURCE_BUDGET_FIELD])


def _parse_provider(config: Mapping[str, JsonValue], default: str) -> str:
    """解析搜索 provider 策略。

    Args:
        config: provider 自有 JSON 配置。
        default: 缺省 provider。

    Returns:
        规范化 provider 字符串。

    Raises:
        ValueError: provider 字段不是字符串或不在允许集合时抛出。
    """

    value = config.get(_CONFIG_PROVIDER_FIELD)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError("web provider config.provider must be a string")
    normalized = value.strip().lower()
    if normalized not in {"auto", "tavily", "serper", "duckduckgo"}:
        raise ValueError("web provider config.provider must be auto/tavily/serper/duckduckgo")
    return normalized


def _positive_float(
    config: Mapping[str, JsonValue],
    field_name: str,
    default: float,
) -> float:
    """读取正数配置。

    Args:
        config: provider 自有 JSON 配置。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        正浮点数。

    Raises:
        ValueError: 字段存在但不是正数时抛出。
    """

    if field_name not in config:
        return default
    value = config.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"web provider config.{field_name} must be a positive number")
    return float(value)


def _positive_int(
    config: Mapping[str, JsonValue],
    field_name: str,
    default: int,
) -> int:
    """读取正整数配置。

    Args:
        config: provider 自有 JSON 配置。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        正整数。

    Raises:
        ValueError: 字段存在但不是正整数时抛出。
    """

    if field_name not in config:
        return default
    value = config.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"web provider config.{field_name} must be a positive integer")
    return value


def _bool_default(
    config: Mapping[str, JsonValue],
    field_name: str,
    *,
    default: bool,
) -> bool:
    """读取布尔配置。

    Args:
        config: provider 自有 JSON 配置。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        布尔配置值。

    Raises:
        ValueError: 字段存在但不是布尔值时抛出。
    """

    if field_name not in config:
        return default
    value = config[field_name]
    if not isinstance(value, bool):
        raise ValueError(f"web provider config.{field_name} must be boolean")
    return value


def _optional_text_default(
    config: Mapping[str, JsonValue],
    field_name: str,
    default: str | None,
) -> str | None:
    """读取可选文本配置。

    Args:
        config: provider 自有 JSON 配置。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        文本、空值或 ``None``。

    Raises:
        ValueError: 字段存在但不是字符串或 null 时抛出。
    """

    value = config.get(field_name)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"web provider config.{field_name} must be string or null")
    normalized = value.strip()
    return normalized if normalized else None


def _text_default(
    config: Mapping[str, JsonValue],
    field_name: str,
    default: str,
) -> str:
    """读取文本配置。

    Args:
        config: provider 自有 JSON 配置。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        文本配置值。

    Raises:
        ValueError: 字段存在但不是字符串时抛出。
    """

    value = config.get(field_name)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"web provider config.{field_name} must be string")
    return value.strip()


def _validate_web_definitions(definitions: tuple[ToolDefinition, ...]) -> None:
    """校验 Web tool 定义集合。

    Args:
        definitions: native builder 返回的工具定义。

    Returns:
        无。

    Raises:
        ValueError: 工具名集合或标签不符合 S5 预期时抛出。
    """

    names = tuple(definition.name for definition in definitions)
    if names != _WEB_TOOL_NAMES:
        raise ValueError(f"web provider expected tools {_WEB_TOOL_NAMES}, got {names}")
    for definition in definitions:
        if "web" not in definition.tags:
            raise ValueError(f"web tool {definition.name} must declare web tag")


def _source_ref() -> ToolBundleSourceRef:
    """构造 Web provider 来源引用。

    Args:
        无。

    Returns:
        工具来源引用。

    Raises:
        ValueError: 来源引用字段非法时由契约对象抛出。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=_SOURCE_ID,
        version_ref=_VERSION_REF,
        content_digest=None,
    )


__all__ = ["discover_tools"]
