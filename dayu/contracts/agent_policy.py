"""Agent policy 共享契约。

本模块只承载 Host/Service/runtime/Engine 都需要共同解释的层中立
Agent policy 枚举；不导入 Engine、Host、Service、UI 或 Fins。
"""

from __future__ import annotations

from enum import StrEnum


class AgentFallbackMode(StrEnum):
    """Agent 降级收口模式。

    成员：

    - ``FORCE_ANSWER``：禁用工具再调用一次 Runner，要求模型基于已有上下文
      给出最终回答。
    - ``RAISE_ERROR``：直接收口为 ``run_failed``。
    """

    FORCE_ANSWER = "force_answer"
    RAISE_ERROR = "raise_error"


AGENT_FALLBACK_MODES: frozenset[str] = frozenset(
    mode.value for mode in AgentFallbackMode
)
"""Agent fallback mode wire value 闭集。"""


__all__ = ["AGENT_FALLBACK_MODES", "AgentFallbackMode"]
