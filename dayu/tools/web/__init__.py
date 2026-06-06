"""Web tools provider 包入口。

本包只暴露当前 ``ToolsDiscovery`` provider callable，不迁移 OLD Web UI。
"""

from __future__ import annotations

from .provider import discover_tools

__all__ = ["discover_tools"]
