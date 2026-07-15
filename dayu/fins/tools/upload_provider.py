"""Fins 上传工具的独立 ToolsDiscovery provider。"""

from __future__ import annotations

from typing import Final

from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools._ingestion_tool_helpers import parse_awaiting_resolution_mode
from dayu.fins.tools.provider import parse_fins_workspace_root_config
from dayu.fins.tools.upload_tools import build_fins_upload_tool
from dayu.runtime.tools_discovery import (
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

_PROVIDER_ID: Final[str] = "financial-upload-tools"
_VERSION_REF: Final[str] = "fins-upload-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.fins.tools.upload_provider"


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现 Fins 上传 awaiting tool。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置。

    Returns:
        provider 输出，包含上传 start 工具定义。

    Raises:
        ValueError: 注册上传工具时 provider config 缺少绝对 ``workspace_root`` 时抛出。
        OSError: Fins runtime 仓储初始化失败时抛出。
    """

    parse_awaiting_resolution_mode(spec.config)
    source_ref = _source_ref()
    workspace_root = parse_fins_workspace_root_config(spec.config)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion_runtime = runtime.get_ingestion_runtime()
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=(
            build_fins_upload_tool(ingestion_runtime),
        ),
    )


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


__all__ = ["discover_tools"]
