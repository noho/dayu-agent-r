"""Web 工具取消文案常量。"""

from __future__ import annotations

from typing import Final

WEB_CANCELLED_HINT: Final[str] = "当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"
"""Web 工具取消后投影给 LLM 的业务可读恢复提示。"""
