"""Engine 当前默认 Runner 装配点。

本模块只负责把 :class:`AgentRunRequest` 中的 Runner 规约装配为当前
内置 OpenAI-compatible Runner。它是私有默认实现细节，不是 Runner
factory、registry 或扩展点。
"""

from __future__ import annotations

from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner


def build_default_runner(request: AgentRunRequest) -> AsyncRunner:
    """根据 Agent run 请求构造当前默认 Runner。

    :param request: Agent run 请求，提供 Runner 规约与取消 token。
    :returns: 当前默认 OpenAI-compatible Runner，按 ``AsyncRunner`` 协议返回。
    :raises Exception: Runner 构造失败时透传底层异常。
    """

    return AsyncOpenAIRunner(
        spec=request.runner_spec,
        cancellation_token=request.cancellation_token,
    )


__all__ = ["build_default_runner"]
