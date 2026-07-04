"""工具执行能力声明契约。

本模块定义工具声明中的运行期执行形态。该能力只供 Host / ToolRuntime
选择治理边界使用，不进入 LLM-facing tool schema，也不得被解释为财报
事实、业务事实或模型可见结论。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallRequest


@dataclass(frozen=True, slots=True)
class ProcessBackedToolContext:
    """子进程工具目标构造所需的可序列化上下文。

    本类型由 Host 从批式工具执行上下文投影而来，只包含
    multiprocessing spawn 可序列化的标量字段。它不包含
    cancellation_token、lock、runtime、repository、session 或 Host 内部
    对象。

    :param run_id: Agent run 唯一 id。
    :param session_id: 会话 id。
    :param iteration_id: 当前 LLM 迭代 id。
    :param timeout_seconds: 当前工具批次剩余超时预算；``None`` 表示调用方
        未提供。
    :param correlation_id: 批级中性关联标识；``None`` 表示调用方未提供。
    """

    run_id: str
    session_id: str
    iteration_id: str
    timeout_seconds: float | None
    correlation_id: str | None


class ToolExecutionMode(StrEnum):
    """工具运行时执行形态。

    枚举值进入稳定 digest 的 ``execution.mode`` 字段；它不进入
    LLM-facing tool schema，也不是业务事实。
    """

    ASYNC_DIRECT = "async_direct"
    THREAD_BACKED = "thread_backed"
    PROCESS_BACKED = "process_backed"


class ProcessBackedToolTarget(Protocol):
    """可在独立子进程内执行的工具目标。

    实现必须可被 multiprocessing spawn 序列化，不得捕获 repository、
    runtime、session、provider lock 或 Host 内部对象。
    """

    def __call__(self) -> JsonValue:
        """执行子进程工具目标并返回 JSON 信封。

        :returns: JSON 信封，合法形态仅为
            ``{"status": "completed", "value": JsonValue}`` 或
            ``{"status": "failed", "error_type": str, "message": str}``。
            子进程不得返回 awaiting、cancelled、timeout 或 host_cancelled
            语义；等待、取消和超时只能由 Host / Engine 治理层产生。
        :raises Exception: 未捕获异常由 process capsule 转为结构化工具失败。
        """

        ...


class ProcessBackedToolTargetFactory(Protocol):
    """根据工具调用构造 process-backed 目标。

    factory 本身与返回目标都必须可序列化，不得捕获 repository、runtime、
    session、provider lock 或 Host 内部对象。
    """

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> ProcessBackedToolTarget:
        """构造可序列化子进程目标。

        :param call: 单次工具调用请求。
        :param context: 已从批式执行上下文投影出的可序列化上下文；不包含
            cancellation_token、lock、runtime、repository、session 或 Host
            internals。
        :returns: 可被 multiprocessing spawn 序列化的目标。
        :raises Exception: 目标无法构造时抛出，ToolRuntime 转为工具失败。
        """

        ...


@dataclass(frozen=True, slots=True)
class AsyncDirectToolExecutionCapability:
    """直接 async 执行能力声明。

    :param request_abort_capable: 取消 async task 时，工具实现是否能关闭底层
        request / stream / client 等资源。该字段进入稳定 digest，不进入
        LLM-facing schema，也不得作为业务事实或财报事实使用。
    """

    request_abort_capable: bool = False


@dataclass(frozen=True, slots=True)
class ThreadBackedToolExecutionCapability:
    """线程托管执行能力声明。

    该模式只表示可取消 wrapper awaitable，不承诺停止 OS thread。

    :param production_safe_non_cooperative_cancel: 永远为 ``False`` 的显式
        guard 字段。该字段进入稳定 digest，不进入 LLM-facing schema；它
        用于证明 thread_backed 不能作为生产非协作 blocking cancel
        closeout 证据。
    """

    production_safe_non_cooperative_cancel: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ProcessBackedToolExecutionCapability:
    """子进程托管执行能力声明。

    :param target_factory: 根据工具调用构造可序列化 process target 的
        factory。该对象身份不进入稳定 digest，不进入 LLM-facing schema，
        也不是业务事实；digest 只记录 ``process_backed`` mode。
    """

    target_factory: ProcessBackedToolTargetFactory


ToolExecutionCapability: TypeAlias = (
    AsyncDirectToolExecutionCapability
    | ThreadBackedToolExecutionCapability
    | ProcessBackedToolExecutionCapability
)
"""工具运行时执行能力封闭联合。

联合成员只用于 ToolRuntime 选择执行边界；不进入 LLM-facing schema，也
不得投影为模型可见业务信息。
"""


__all__ = [
    "AsyncDirectToolExecutionCapability",
    "ProcessBackedToolContext",
    "ProcessBackedToolExecutionCapability",
    "ProcessBackedToolTarget",
    "ProcessBackedToolTargetFactory",
    "ThreadBackedToolExecutionCapability",
    "ToolExecutionCapability",
    "ToolExecutionMode",
]
