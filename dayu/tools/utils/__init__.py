"""通用工具 provider 包入口。

本包只暴露当前 ``ToolsDiscovery`` provider callable，工具定义本身位于
``dayu.tools.utils.provider``。
"""

from __future__ import annotations

from .provider import discover_tools

__all__ = ["discover_tools"]
