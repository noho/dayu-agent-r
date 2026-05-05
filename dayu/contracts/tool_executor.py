"""工具执行器协议契约。

本协议是 Engine / Agent 调用工具的**唯一**接口。Engine 不感知工具
注册、schema 校验、路径白名单、并发治理等具体职责——这些都属于 Host
ToolRuntime / ToolRegistry。Engine 通过 :class:`ToolExecutor.execute`
拿到 :data:`ToolExecutionOutcome` 后即完成本轮工具调用闭环。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome


@runtime_checkable
class ToolExecutor(Protocol):
    """工具执行器协议。

    Engine 仅依赖 :meth:`execute` 一个方法；其它工具治理（schema 暴露、
    工具集合枚举、display info 等）一律不属于本协议表面。
    """

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionOutcome:
        """执行一次工具调用。

        :param request: 工具执行请求（含 :class:`ToolCallRequest` 与
            :class:`ToolExecutionContext`）。
        :returns: 工具执行 outcome 封闭联合的某个具体成员。

        实现必须协作式观察 ``request.context.cancellation_token``；取消的
        **公共终态**由 Agent / Engine 入口收口为
        :class:`RunCancelledData` / :class:`EngineRunOutcomeCancelled`，
        不在本协议公共 ``:raises:`` 中暴露任何取消异常。
        """
        ...


__all__ = ["ToolExecutor"]
