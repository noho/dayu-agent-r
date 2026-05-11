"""Host 内部 EngineWorker wrapper。

本模块是 Host 到 Engine 函数式入口的内部装配层，不属于 public API。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from dayu.contracts import CancellationToken, ToolExecutor
from dayu.engine import AgentRunRequest, EngineEvent, run_agent_messages
from dayu.host._engine_tool_schema_provider import EngineToolSchemaProvider
from dayu.host.contracts import StartRunRequest
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EngineWorker:
    """Host 内部 EngineWorker capability。

    :param tool_executor: Host 内部代持的工具执行器。
    :param schema_provider: Host 内部 framework schema provider；只返回
        Engine-visible ``ToolSchema``。
    """

    tool_executor: ToolExecutor
    schema_provider: EngineToolSchemaProvider | None = None

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

        tool_schemas = request.options.tool_schemas
        if self.schema_provider is not None:
            tool_schemas = self.schema_provider.engine_visible_tool_schemas(
                tool_schemas
            )
        engine_request = AgentRunRequest(
            run_id=request.run_id,
            session_id=request.session_id,
            messages=request.input.messages,
            stream=request.options.stream,
            disable_tools=request.options.disable_tools,
            runner_spec=request.options.runner_spec,
            runner_options=request.options.runner_options,
            agent_policy=request.options.agent_policy,
            tool_schemas=tool_schemas,
            tool_executor=self.tool_executor,
            cancellation_token=cancellation_token,
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.engine_worker.run_agent_messages session_id=%s run_id=%s "
            "messages=%s tools=%s stream=%s disable_tools=%s",
            engine_request.session_id,
            engine_request.run_id,
            len(engine_request.messages),
            len(engine_request.tool_schemas),
            engine_request.stream,
            engine_request.disable_tools,
        )
        return run_agent_messages(engine_request)


__all__ = ["EngineWorker"]
