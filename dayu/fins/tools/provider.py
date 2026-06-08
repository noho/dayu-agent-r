"""Fins read tools 的当前 ToolsDiscovery provider。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
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

from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.fins_limits import FinsToolLimits
from dayu.fins.tools.fins_tools import register_fins_read_tools

_PROVIDER_ID: Final[str] = "financial-read-tools"
_VERSION_REF: Final[str] = "fins-read-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.fins.tools.provider"
_CONFIG_WORKSPACE_ROOT_FIELD: Final[str] = "workspace_root"
_CONFIG_LIMITS_FIELD: Final[str] = "limits"
_CONFIG_INCLUDE_READ_TOOLS_FIELD: Final[str] = "include_read_tools"
_FINS_READ_TOOL_NAMES: Final[tuple[str, ...]] = (
    "list_documents",
    "get_document_sections",
    "read_section",
    "search_document",
    "list_tables",
    "get_table",
    "get_page_content",
    "get_financial_statement",
    "query_xbrl_facts",
)


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Fins read tools。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出；read tools 关闭时返回空工具集。

    Raises:
        ValueError: provider config 非法时抛出。
    """

    include_read_tools = _parse_bool_default(
        spec.config,
        _CONFIG_INCLUDE_READ_TOOLS_FIELD,
        default=True,
    )
    source_ref = _source_ref()
    if not include_read_tools:
        return ToolsDiscoveryProviderOutput(
            provider_id=_PROVIDER_ID,
            version_ref=_VERSION_REF,
            source_refs=(source_ref,),
            definitions=(),
        )

    limits = _parse_limits(spec.config)
    workspace_root = parse_fins_workspace_root_config(spec.config)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    read_runtime = runtime.get_read_runtime(
        processor_cache_max_entries=limits.processor_cache_max_entries
    )
    collector = LegacyToolDeclarationCollector()
    register_fins_read_tools(
        collector,
        read_runtime=read_runtime,
        limits=limits,
        timeout_budget=None,
    )
    declarations = collector.collected_tools()
    _validate_fins_declarations(declarations)
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=_adapt_fins_declarations(declarations),
    )


def parse_fins_workspace_root_config(config: Mapping[str, JsonValue]) -> Path:
    """解析 Fins provider 显式配置的 workspace root。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        绝对 Fins workspace root。

    Raises:
        ValueError: 字段缺失、不是非空字符串，或不是绝对路径时抛出。
    """

    value = config.get(_CONFIG_WORKSPACE_ROOT_FIELD)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError("fins provider config.workspace_root must be a non-empty absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("fins provider config.workspace_root must be absolute; no cwd/env fallback is allowed")
    return path.resolve(strict=False)


def _parse_limits(config: Mapping[str, JsonValue]) -> FinsToolLimits:
    """从 provider config 解析 FinsToolLimits。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        Fins 工具限制配置。

    Raises:
        ValueError: ``limits`` 不是 JSON object 或字段不是正整数时抛出。
    """

    limits_value = config.get(_CONFIG_LIMITS_FIELD)
    defaults = FinsToolLimits()
    if limits_value is None:
        return defaults
    if not isinstance(limits_value, Mapping):
        raise ValueError("fins provider config.limits must be a JSON object")
    return FinsToolLimits(
        processor_cache_max_entries=_positive_int(
            limits_value,
            "processor_cache_max_entries",
            defaults.processor_cache_max_entries,
        ),
        list_documents_max_items=_positive_int(
            limits_value,
            "list_documents_max_items",
            defaults.list_documents_max_items,
        ),
        get_document_sections_max_items=_positive_int(
            limits_value,
            "get_document_sections_max_items",
            defaults.get_document_sections_max_items,
        ),
        search_document_max_items=_positive_int(
            limits_value,
            "search_document_max_items",
            defaults.search_document_max_items,
        ),
        list_tables_max_items=_positive_int(
            limits_value,
            "list_tables_max_items",
            defaults.list_tables_max_items,
        ),
        read_section_max_chars=_positive_int(
            limits_value,
            "read_section_max_chars",
            defaults.read_section_max_chars,
        ),
        get_page_content_max_chars=_positive_int(
            limits_value,
            "get_page_content_max_chars",
            defaults.get_page_content_max_chars,
        ),
        get_table_max_items=_positive_int(
            limits_value,
            "get_table_max_items",
            defaults.get_table_max_items,
        ),
        get_financial_statement_max_items=_positive_int(
            limits_value,
            "get_financial_statement_max_items",
            defaults.get_financial_statement_max_items,
        ),
        query_xbrl_facts_max_items=_positive_int(
            limits_value,
            "query_xbrl_facts_max_items",
            defaults.query_xbrl_facts_max_items,
        ),
    )


def _positive_int(
    payload: Mapping[str, JsonValue],
    field_name: str,
    default: int,
) -> int:
    """读取正整数 limit 字段。

    Args:
        payload: limits JSON object。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        正整数配置值。

    Raises:
        ValueError: 字段存在但不是正整数时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"fins provider limits.{field_name} must be a positive integer")
    return value


def _parse_bool_default(
    config: Mapping[str, JsonValue],
    field_name: str,
    *,
    default: bool,
) -> bool:
    """解析可选布尔配置。

    Args:
        config: provider 自有 JSON 配置。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        解析后的布尔值。

    Raises:
        ValueError: 字段存在但不是布尔值时抛出。
    """

    value = config.get(field_name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"fins provider config.{field_name} must be boolean")
    return value


def _validate_fins_declarations(
    declarations: tuple[CollectedLegacyTool, ...],
) -> None:
    """校验迁移 Fins read tool 声明集合。

    Args:
        declarations: collector 收集到的迁移声明。

    Returns:
        无。

    Raises:
        ValueError: 工具名集合不符合 S4 预期时抛出。
    """

    names = tuple(declaration.name for declaration in declarations)
    if names != _FINS_READ_TOOL_NAMES:
        raise ValueError(f"fins provider expected tools {_FINS_READ_TOOL_NAMES}, got {names}")
    for declaration in declarations:
        if "fins" not in declaration.tags:
            raise ValueError(f"fins tool {declaration.name} must declare fins tag")


def _adapt_fins_declarations(
    declarations: tuple[CollectedLegacyTool, ...],
) -> tuple[ToolDefinition, ...]:
    """把 Fins 声明适配为当前 ToolDefinition。

    Args:
        declarations: 迁移工具声明。

    Returns:
        current 工具定义元组。

    Raises:
        Exception: adapter 构造失败时透出。
    """

    return adapt_collected_tools(
        declarations,
        path_policy_by_tool={},
        concurrency_policy_by_tool={
            declaration.name: LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER
            for declaration in declarations
        },
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造 Fins provider 来源引用。

    Args:
        无。

    Returns:
        工具来源引用。

    Raises:
        无。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=_SOURCE_ID,
        version_ref=_VERSION_REF,
        content_digest=None,
    )
