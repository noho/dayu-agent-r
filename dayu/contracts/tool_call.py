"""工具调用请求与执行上下文契约。

本模块定义工具调用闭环中的强类型输入：

- :class:`ToolCallRequest`：单次工具调用请求载荷。
- :class:`ToolExecutionContext`：执行该调用所需的运行期上下文（运行 id /
  会话 id / 迭代 id / 取消 token / 中性 correlation_id）。
- :class:`ToolExecutionRequest`：将二者打包，作为 :meth:`ToolExecutor.execute`
  的唯一入参。

``correlation_id`` 仅用于跨 Host observer / ToolRuntime 的中性关联，**不**
是 ToolTraceRecorder 私有入口；Engine 不会基于它做任何治理决策。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """单次工具调用请求。

    :param tool_call_id: 工具调用唯一 id，与 LLM 输出一致。
    :param name: 工具名称。
    :param arguments: 调用参数，强类型 JSON 映射。
    :param index_in_iteration: 本工具调用在当前迭代内的序号（从 0 起）。
    """

    tool_call_id: str
    name: str
    arguments: Mapping[str, JsonValue]
    index_in_iteration: int


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """工具执行运行期上下文。

    :param run_id: Agent run 唯一 id。
    :param session_id: 会话 id。
    :param iteration_id: 当前 LLM 迭代 id。
    :param tool_call_id: 当前工具调用 id。
    :param index_in_iteration: 当前工具调用在迭代内的序号。
    :param timeout_seconds: 工具级超时秒数；``None`` 表示由 Host 兜底
        策略决定。
    :param cancellation_token: 取消观察 token。
    :param correlation_id: 中性跨组件关联标识；不得用作 trace recorder
        私有入口。
    """

    run_id: str
    session_id: str
    iteration_id: str
    tool_call_id: str
    index_in_iteration: int
    timeout_seconds: float | None
    cancellation_token: CancellationToken
    correlation_id: str | None


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    """工具执行入参的封装。

    :param call: 工具调用请求。
    :param context: 工具执行运行期上下文。
    """

    call: ToolCallRequest
    context: ToolExecutionContext


__all__ = ["ToolCallRequest", "ToolExecutionContext", "ToolExecutionRequest"]
