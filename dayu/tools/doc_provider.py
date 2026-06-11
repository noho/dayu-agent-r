"""Doc tools 的当前 ToolsDiscovery provider。

本模块只负责解析 provider 配置、维护 provider id / version / source refs，
并把 Doc 原生 ``ToolDefinition`` 集合交给 ``ToolsDiscovery``。路径白名单
为空时 fail closed，返回空工具集合。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.runtime.tools_discovery import (
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

from .doc_tools import DocToolLimits, build_doc_tool_definitions

_PROVIDER_ID: Final[str] = "doc-tools"
_VERSION_REF: Final[str] = "doc-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.tools.doc_provider"
_CONFIG_LIMITS_FIELD: Final[str] = "limits"
_CONFIG_ALLOWED_PATHS_FIELD: Final[str] = "allowed_paths"


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Doc 工具声明。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出；当 provider 启用但未配置显式路径白名单时返回空工具集。

    Raises:
        ValueError: provider config 字段类型非法时抛出。
    """

    limits = _parse_limits(spec.config)
    allowed_roots = _parse_allowed_paths(spec.config)
    source_ref = _source_ref()
    if not allowed_roots:
        return ToolsDiscoveryProviderOutput(
            provider_id=_PROVIDER_ID,
            version_ref=_VERSION_REF,
            source_refs=(source_ref,),
            definitions=(),
        )

    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=build_doc_tool_definitions(limits, allowed_roots),
    )


def _parse_limits(config: Mapping[str, JsonValue]) -> DocToolLimits:
    """从 provider config 解析 DocToolLimits。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        文档工具限制配置。

    Raises:
        ValueError: ``limits`` 字段不是 JSON object 或 limit 字段不是正整数时抛出。
    """

    limits_value = config.get(_CONFIG_LIMITS_FIELD)
    defaults = DocToolLimits()
    if limits_value is None:
        return defaults
    if not isinstance(limits_value, Mapping):
        raise ValueError("doc provider config.limits must be a JSON object")
    return DocToolLimits(
        list_files_max=_positive_int(
            limits_value,
            "list_files_max",
            defaults.list_files_max,
        ),
        get_sections_max=_positive_int(
            limits_value,
            "get_sections_max",
            defaults.get_sections_max,
        ),
        search_files_max_results=_positive_int(
            limits_value,
            "search_files_max_results",
            defaults.search_files_max_results,
        ),
        read_file_max_chars=_positive_int(
            limits_value,
            "read_file_max_chars",
            defaults.read_file_max_chars,
        ),
        read_file_section_max_chars=_positive_int(
            limits_value,
            "read_file_section_max_chars",
            defaults.read_file_section_max_chars,
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
        raise ValueError(f"doc provider limits.{field_name} must be a positive integer")
    return value


def _parse_allowed_paths(config: Mapping[str, JsonValue]) -> tuple[Path, ...]:
    """从 provider config 解析显式路径白名单。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        归一化后的绝对路径根元组；缺失或空列表返回空元组。

    Raises:
        ValueError: ``allowed_paths`` 字段不是字符串数组，或包含空白字符串时抛出。
    """

    value = config.get(_CONFIG_ALLOWED_PATHS_FIELD)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("doc provider config.allowed_paths must be a string array")
    paths: list[Path] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError("doc provider config.allowed_paths items must be non-empty strings")
        paths.append(Path(item).expanduser().resolve(strict=False))
    return tuple(paths)


def _source_ref() -> ToolBundleSourceRef:
    """构造 Doc provider 来源引用。

    Args:
        无。

    Returns:
        provider 来源引用。

    Raises:
        Exception: ``ToolBundleSourceRef`` 契约校验失败时透出。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=_SOURCE_ID,
        version_ref=_VERSION_REF,
    )
