"""Agent 策略契约。

Phase 0 仅落地三个最小策略字段；其它策略（fallback / final answer
filter / context budget limits / continuation 策略等）留给消费它的
Phase 引入。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentPolicy:
    """Agent 运行策略。

    :param max_iterations: 单次 Agent run 内最大 LLM 迭代次数。
    :param continuation_max_attempts: 同一迭代内 continuation 最大尝试
        次数。
    :param allow_tool_calls: 是否允许工具调用。
    """

    max_iterations: int
    continuation_max_attempts: int
    allow_tool_calls: bool


__all__ = ["AgentPolicy"]
