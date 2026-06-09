"""Fins 上传工具的独立 ToolsDiscovery provider。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.provider import parse_fins_workspace_root_config
from dayu.fins.tools.upload_tools import build_fins_upload_tool
from dayu.runtime.tools_discovery import (
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

_PROVIDER_ID: Final[str] = "financial-upload-tools"
_VERSION_REF: Final[str] = "fins-upload-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.fins.tools.upload_provider"
_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD: Final[str] = "allowed_upload_roots"


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Fins 上传 awaiting tool。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出，包含上传 start 工具定义。

    Raises:
        ValueError: provider config 缺少绝对 ``workspace_root`` 或
            ``allowed_upload_roots`` 非空绝对路径集合时抛出。
        OSError: Fins runtime 仓储初始化失败时抛出。
    """

    workspace_root = parse_fins_workspace_root_config(spec.config)
    allowed_upload_roots = parse_allowed_upload_roots_config(spec.config)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion_runtime = runtime.get_ingestion_runtime()
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(_source_ref(),),
        definitions=(
            build_fins_upload_tool(
                ingestion_runtime,
                allowed_upload_roots=allowed_upload_roots,
            ),
        ),
    )


def parse_allowed_upload_roots_config(config: Mapping[str, JsonValue]) -> tuple[Path, ...]:
    """解析 Fins upload provider 的上传文件 allowlist 根目录。

    Args:
        config: provider 自有 JSON 配置。

    Returns:
        已 resolve 的绝对 allowlist 根目录元组。

    Raises:
        ValueError: 字段缺失、不是非空数组，或数组元素不是绝对路径字符串时抛出。
    """

    value = config.get(_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD)
    if not isinstance(value, list) or not value:
        raise ValueError("fins upload provider config.allowed_upload_roots must be a non-empty array")
    roots: list[Path] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError(
                "fins upload provider config.allowed_upload_roots must contain only non-empty absolute paths"
            )
        path = Path(item).expanduser()
        if not path.is_absolute():
            raise ValueError("fins upload provider config.allowed_upload_roots must contain only absolute paths")
        roots.append(path.resolve(strict=False))
    return tuple(roots)


def _source_ref() -> ToolBundleSourceRef:
    """构造 Fins 上传 provider 来源引用。

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


__all__ = ["discover_tools", "parse_allowed_upload_roots_config"]
