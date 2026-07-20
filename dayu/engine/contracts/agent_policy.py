"""Agent 策略契约。

本模块承载 Engine Agent loop 的中性运行策略。Phase 3 起，策略显式表达
工具调用轮次耗尽与连续失败工具批次后的 fallback 行为，避免用魔法字符串
或 metadata 传递关键状态机事实。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from dayu.contracts.agent_policy import AgentFallbackMode


_DEFAULT_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES: int = 2


@dataclass(frozen=True, slots=True)
class AgentPolicy:
    """Agent 运行策略。

    :param max_iterations: 单次 Agent run 内最大 LLM 迭代次数。
    :param continuation_max_attempts: 同一迭代内 continuation 最大尝试
        次数。
    :param allow_tool_calls: 是否允许工具调用。
    :param tool_execution_timeout_seconds: Engine 等待
        ``ToolExecutor.execute`` 完成握手的超时秒数真源，必须为有限正数。
    :param fallback_mode: 普通工具轮次耗尽或连续失败工具批次达到阈值后的
        收口模式。
    :param fallback_prompt: force-answer 时追加给 Runner 的用户消息。
    :param continuation_prompt: ``finish_reason=length`` 续写时追加给
        Runner 的用户消息。
    :param max_consecutive_failed_tool_batches: 连续全失败工具批次阈值。
    """

    max_iterations: int
    continuation_max_attempts: int
    allow_tool_calls: bool
    tool_execution_timeout_seconds: float
    fallback_prompt: str
    continuation_prompt: str
    fallback_mode: AgentFallbackMode = AgentFallbackMode.FORCE_ANSWER
    max_consecutive_failed_tool_batches: int = (
        _DEFAULT_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES
    )

    def __post_init__(self) -> None:
        """校验 Agent 策略边界。

        :returns: ``None``。
        :raises TypeError: ``fallback_mode`` 不是 AgentFallbackMode 时抛出。
        :raises ValueError: ``max_iterations`` 小于 1、timeout 非正数、
            continuation 次数小于 0、continuation prompt 为空、
            fallback prompt 为空或连续失败工具批次阈值小于 1 时抛出。
        """

        if not isinstance(self.fallback_mode, AgentFallbackMode):
            raise TypeError("AgentPolicy.fallback_mode must be AgentFallbackMode")
        if self.max_iterations < 1:
            raise ValueError("AgentPolicy.max_iterations must be >= 1")
        if (
            not math.isfinite(self.tool_execution_timeout_seconds)
            or self.tool_execution_timeout_seconds <= 0
        ):
            raise ValueError(
                "AgentPolicy.tool_execution_timeout_seconds must be finite and > 0"
            )
        if self.continuation_max_attempts < 0:
            raise ValueError(
                "AgentPolicy.continuation_max_attempts must be >= 0"
            )
        if self.continuation_prompt.strip() == "":
            raise ValueError("AgentPolicy.continuation_prompt must not be empty")
        if self.fallback_prompt.strip() == "":
            raise ValueError("AgentPolicy.fallback_prompt must not be empty")
        if self.max_consecutive_failed_tool_batches < 1:
            raise ValueError(
                "AgentPolicy.max_consecutive_failed_tool_batches must be >= 1"
            )


__all__ = ["AgentFallbackMode", "AgentPolicy"]
