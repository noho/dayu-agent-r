"""Web tools 的当前 ToolsDiscovery provider。

本模块只负责把迁移后的 OLD Web 工具声明收集并适配为当前
``ToolDefinition``。URL 安全策略通过 provider config 显式传入迁移工具
闭包；参数校验、响应投影和并发序列化由当前 adapter 边界完成。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.runtime.tools_discovery import (
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)
from dayu.tools._legacy_adapter.definition_adapter import (
    LegacyToolConcurrencyPolicy,
    adapt_collected_tools,
)
from dayu.tools._legacy_adapter.registry_collector import (
    CollectedLegacyTool,
    LegacyToolDeclarationCollector,
)

from .web_tools import register_web_tools

_PROVIDER_ID: Final[str] = "web-tools"
_VERSION_REF: Final[str] = "web-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.tools.web"
_CONFIG_PROVIDER_FIELD: Final[str] = "provider"
_CONFIG_REQUEST_TIMEOUT_SECONDS_FIELD: Final[str] = "request_timeout_seconds"
_CONFIG_MAX_SEARCH_RESULTS_FIELD: Final[str] = "max_search_results"
_CONFIG_FETCH_TRUNCATE_CHARS_FIELD: Final[str] = "fetch_truncate_chars"
_CONFIG_ALLOW_PRIVATE_NETWORK_URL_FIELD: Final[str] = "allow_private_network_url"
_CONFIG_PLAYWRIGHT_CHANNEL_FIELD: Final[str] = "playwright_channel"
_CONFIG_PLAYWRIGHT_STORAGE_STATE_DIR_FIELD: Final[str] = "playwright_storage_state_dir"
_WEB_TOOL_NAMES: Final[tuple[str, ...]] = ("search_web", "fetch_web_page")


@dataclass(frozen=True, slots=True)
class WebToolsConfig:
    """Web 工具 provider 配置。

    :param provider: 搜索 provider 策略。
    :param request_timeout_seconds: HTTP 请求超时秒数。
    :param max_search_results: 搜索最大返回条数。
    :param fetch_truncate_chars: 抓取正文截断声明字符数。
    :param allow_private_network_url: 是否允许内网 / 本地 URL。
    :param playwright_channel: Playwright fallback 使用的浏览器 channel。
    :param playwright_storage_state_dir: Playwright storage state 目录。
    """

    provider: str = "auto"
    request_timeout_seconds: float = 12.0
    max_search_results: int = 20
    fetch_truncate_chars: int = 80_000
    allow_private_network_url: bool = False
    playwright_channel: str | None = "chrome"
    playwright_storage_state_dir: str = ""


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Web tools。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出，包含 ``search_web`` 与 ``fetch_web_page``。

    Raises:
        ValueError: provider config 非法，或 OLD 声明集合不符合本 slice
            预期时抛出。
    """

    config = _parse_config(spec.config)
    collector = LegacyToolDeclarationCollector()
    register_web_tools(
        collector,
        provider=config.provider,
        request_timeout_seconds=config.request_timeout_seconds,
        max_search_results=config.max_search_results,
        fetch_truncate_chars=config.fetch_truncate_chars,
        allow_private_network_url=config.allow_private_network_url,
        playwright_channel=config.playwright_channel,
        playwright_storage_state_dir=config.playwright_storage_state_dir,
        timeout_budget=None,
    )
    declarations = collector.collected_tools()
    _validate_web_declarations(declarations)
    source_ref = _source_ref()
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=_adapt_web_declarations(declarations),
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

    defaults = WebToolsConfig()
    return WebToolsConfig(
        provider=_parse_provider(config, defaults.provider),
        request_timeout_seconds=_positive_float(
            config,
            _CONFIG_REQUEST_TIMEOUT_SECONDS_FIELD,
            defaults.request_timeout_seconds,
        ),
        max_search_results=_positive_int(
            config,
            _CONFIG_MAX_SEARCH_RESULTS_FIELD,
            defaults.max_search_results,
        ),
        fetch_truncate_chars=_positive_int(
            config,
            _CONFIG_FETCH_TRUNCATE_CHARS_FIELD,
            defaults.fetch_truncate_chars,
        ),
        allow_private_network_url=_bool_default(
            config,
            _CONFIG_ALLOW_PRIVATE_NETWORK_URL_FIELD,
            default=defaults.allow_private_network_url,
        ),
        playwright_channel=_optional_text_default(
            config,
            _CONFIG_PLAYWRIGHT_CHANNEL_FIELD,
            defaults.playwright_channel,
        ),
        playwright_storage_state_dir=_text_default(
            config,
            _CONFIG_PLAYWRIGHT_STORAGE_STATE_DIR_FIELD,
            defaults.playwright_storage_state_dir,
        ),
    )


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

    value = config.get(field_name)
    if value is None:
        return default
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


def _validate_web_declarations(declarations: tuple[CollectedLegacyTool, ...]) -> None:
    """校验迁移 Web tool 声明集合。

    Args:
        declarations: collector 收集到的迁移声明。

    Returns:
        无。

    Raises:
        ValueError: 工具名集合或标签不符合 S5 预期时抛出。
    """

    names = tuple(declaration.name for declaration in declarations)
    if names != _WEB_TOOL_NAMES:
        raise ValueError(f"web provider expected tools {_WEB_TOOL_NAMES}, got {names}")
    for declaration in declarations:
        if "web" not in declaration.tags:
            raise ValueError(f"web tool {declaration.name} must declare web tag")


def _adapt_web_declarations(
    declarations: tuple[CollectedLegacyTool, ...],
) -> tuple[ToolDefinition, ...]:
    """把 Web 声明适配为当前 ToolDefinition。

    Args:
        declarations: 迁移工具声明。

    Returns:
        current 工具定义元组。

    Raises:
        Exception: adapter 构造失败时透出。
    """

    concurrency_policy_by_tool: dict[str, LegacyToolConcurrencyPolicy] = {}
    for declaration in declarations:
        concurrency_policy_by_tool[declaration.name] = (
            LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER
        )
    return adapt_collected_tools(
        declarations,
        path_policy_by_tool={},
        concurrency_policy_by_tool=concurrency_policy_by_tool,
    )


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


__all__ = ["WebToolsConfig", "discover_tools"]
