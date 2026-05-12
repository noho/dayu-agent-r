"""工具执行器协议契约。

本协议是 Engine / Agent 调用工具的**唯一**接口；调用形态是批式握手：
Engine 在一轮 LLM 输出后把所有 tool_calls 打包成
:class:`BatchToolExecutionRequest`，对 :meth:`ToolExecutor.execute`
仅调用一次，由实现方一次性返回与输入严格双射的
:class:`BatchToolExecutionOutcome`。

Engine 不感知工具注册、schema 校验、并发治理、审批、限流、单 tool
取消等具体策略——这些都属于 Host ToolRuntime / ToolRegistry。Engine
仅基于 outcome 的封闭联合做下一步状态机决策。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome


@runtime_checkable
class ToolExecutor(Protocol):
    """工具执行器协议。

    Engine 仅依赖 :meth:`execute` 一个方法；其它工具治理（schema 暴露、
    工具集合枚举、display info 等）一律不属于本协议公共表面。
    """

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """执行一次批式工具握手。

        :param request: 批式工具执行请求（含 ``calls`` 与共享
            :class:`BatchToolExecutionContext`）。
        :returns: 与 ``request.calls`` 严格双射的批式工具执行 outcome。

        实现必须协作式观察 ``request.context.cancellation_token``，并允
        许承载本次批握手的 ``asyncio.Task`` 被取消；取消的**公共终态**
        由 Agent / Engine 入口收口为 ``run_cancelled``，不在本协议公共
        ``:raises:`` 中暴露任何取消异常。

        ``request.context.timeout_seconds`` 表示 Engine 等待本次批握手
        返回 outcome 的整体超时预算；若实现无法在该预算内返回，被取消
        后的下游长事务清理属于 ToolExecutor / ToolRuntime 职责。
        """
        ...


__all__ = ["ToolExecutor"]
