"""异步 Runner 协议。

:class:`AsyncRunner` 是 Engine 调用 LLM provider 的**唯一**抽象。
Runner 的职责是「LLM 协议归一」：把 provider 流式协议归一为
:class:`RunnerEvent` 序列；**不**执行工具，**不**直接依赖
:class:`ToolExecutor`，**不**承载 Agent 多轮迭代逻辑。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from dayu.engine.contracts.messages import AgentMessage
from dayu.engine.contracts.runner_events import RunnerEvent
from dayu.engine.contracts.runner_identity import RunnerRequestIdentity
from dayu.engine.contracts.runner_spec import RunnerCallOptions
from dayu.engine.contracts.structured_output import StructuredOutputRequest
from dayu.contracts.tool_schema import ToolSchema


@runtime_checkable
class AsyncRunner(Protocol):
    """异步 Runner 协议。"""

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        structured_output: StructuredOutputRequest | None,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """发起一次 LLM 调用并返回 :class:`RunnerEvent` 异步流。

        :param messages: Agent 消息序列。
        :param options: 单次调用参数。
        :param tools: 本次调用暴露给 LLM 的工具 schema 序列。
        :param structured_output: 本次调用的显式 structured-output 请求；
            ``None`` 表示不请求 structured-output transport。
        :param request_identity: 本次逻辑 Runner 调用的请求身份；直接
            Runner 调用或非普通 Agent attempt 路径可显式传入 ``None``。
        :returns: :class:`RunnerEvent` 异步迭代器。

        实现必须协作式观察由 Engine / Runner 调用边界注入的
        :class:`CancellationToken`（run/request 粒度，归 Agent 请求所有）；
        取消的**公共终态**由 Agent / Engine 入口收口为
        :class:`RunCancelledData` / :class:`EngineRunOutcomeCancelled`，
        不在本协议公共 ``:raises:`` 中暴露任何取消异常。Runner 不观察
        工具执行上下文，也不参与工具批式握手。
        """
        ...

    def is_supports_tool_calling(self) -> bool:
        """返回 Runner 是否支持工具调用。

        :returns: 支持返回 ``True``，否则 ``False``。
        """
        ...

    async def close(self) -> None:
        """关闭 Runner 并释放底层连接。

        :returns: 无返回值。
        """
        ...


__all__ = ["AsyncRunner"]
