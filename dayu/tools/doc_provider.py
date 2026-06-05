"""Doc tools 的当前 ToolsDiscovery provider。

本模块只负责把迁移后的 OLD Doc 工具声明收集并适配为当前
``ToolDefinition``。路径白名单、参数投影和响应投影都在 provider /
adapter 边界完成；Doc 工具函数体本身不拥有路径安全机制。
"""

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

from ._legacy_adapter.definition_adapter import (
    LegacyToolConcurrencyPolicy,
    ToolPathValidationPolicy,
    adapt_collected_tools,
)
from ._legacy_adapter.registry_collector import (
    CollectedLegacyTool,
    LegacyToolDeclarationCollector,
)
from .doc_tools import DocToolLimits, register_doc_tools

_PROVIDER_ID: Final[str] = "doc-tools"
_VERSION_REF: Final[str] = "doc-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.tools.doc_provider"
_CONFIG_LIMITS_FIELD: Final[str] = "limits"
_CONFIG_ALLOWED_PATHS_FIELD: Final[str] = "allowed_paths"
_DOC_TOOL_NAMES: Final[tuple[str, ...]] = (
    "list_files",
    "get_file_sections",
    "search_files",
    "read_file",
    "read_file_section",
)


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Doc 工具声明。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出；当 provider 启用但未配置显式路径白名单时返回空工具集。

    Raises:
        ValueError: provider config 字段类型非法，或 OLD 声明集合不符合本
            provider 预期时抛出。
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

    collector = LegacyToolDeclarationCollector()
    register_doc_tools(
        collector,
        limits=limits,
        allowed_paths=None,
        allow_file_write=False,
        allowed_write_paths=None,
        timeout_budget=None,
    )
    declarations = collector.collected_tools()
    _validate_doc_declarations(declarations)
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=_adapt_doc_declarations(
            declarations=declarations,
            allowed_roots=allowed_roots,
        ),
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


def _validate_doc_declarations(
    declarations: tuple[CollectedLegacyTool, ...],
) -> None:
    """校验迁移 Doc 声明集合。

    Args:
        declarations: collector 收集到的迁移声明。

    Returns:
        无。

    Raises:
        ValueError: 工具名集合或路径参数 metadata 不符合 S3 预期时抛出。
    """

    names = tuple(declaration.name for declaration in declarations)
    if names != _DOC_TOOL_NAMES:
        raise ValueError(f"doc provider expected tools {_DOC_TOOL_NAMES}, got {names}")
    for declaration in declarations:
        if not declaration.file_path_params:
            raise ValueError(f"doc tool {declaration.name} must declare file_path_params")


def _adapt_doc_declarations(
    *,
    declarations: tuple[CollectedLegacyTool, ...],
    allowed_roots: tuple[Path, ...],
) -> tuple[ToolDefinition, ...]:
    """把 Doc 声明适配为当前 ToolDefinition。

    Args:
        declarations: 迁移工具声明。
        allowed_roots: provider 显式白名单根路径。

    Returns:
        current 工具定义元组。

    Raises:
        Exception: adapter 构造失败时透出。
    """

    path_policy_by_tool: dict[str, ToolPathValidationPolicy] = {}
    concurrency_policy_by_tool: dict[str, LegacyToolConcurrencyPolicy] = {}
    for declaration in declarations:
        path_policy_by_tool[declaration.name] = ToolPathValidationPolicy(
            allowed_roots=allowed_roots,
            file_path_params=declaration.file_path_params,
            must_exist=True,
        )
        concurrency_policy_by_tool[declaration.name] = (
            LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER
        )
    return adapt_collected_tools(
        declarations,
        path_policy_by_tool=path_policy_by_tool,
        concurrency_policy_by_tool=concurrency_policy_by_tool,
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造 Doc provider 来源引用。

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
