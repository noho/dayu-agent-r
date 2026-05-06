"""Host 内部 EngineWorker wrapper。

本模块是 Host 到 Engine 函数式入口的内部装配层，不属于 public API。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from dayu.contracts import CancellationToken, ToolExecutor
from dayu.engine import AgentRunRequest, EngineEvent, run_agent_messages
from dayu.host.contracts import StartRunRequest


@dataclass(frozen=True, slots=True)
class EngineWorker:
    """Host 内部 EngineWorker capability。

    :param tool_executor: Host 内部代持的工具执行器。
    """

    tool_executor: ToolExecutor

    def run_agent_messages(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """调用 Engine 函数式入口并返回 EngineEvent 流。

        :param request: Host P1 start_run 请求。
        :param cancellation_token: Host 注入的取消观察 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 透传 Engine 运行异常。
        """

        engine_request = AgentRunRequest(
            run_id=request.run_id,
            session_id=request.session_id,
            messages=request.input.messages,
            stream=request.options.stream,
            disable_tools=request.options.disable_tools,
            runner_spec=request.options.runner_spec,
            runner_options=request.options.runner_options,
            agent_policy=request.options.agent_policy,
            tool_schemas=request.options.tool_schemas,
            tool_executor=self.tool_executor,
            cancellation_token=cancellation_token,
        )
        return run_agent_messages(engine_request)


__all__ = ["EngineWorker"]
