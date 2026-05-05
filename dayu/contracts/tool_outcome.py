"""工具执行 outcome 封闭联合契约。

工具执行只有三种终态：

- :class:`ToolCompletedOutcome`：成功，封装 :class:`ToolResultSuccess`。
- :class:`ToolFailedOutcome`：失败，封装 :class:`ToolResultFailure`。
- :class:`ToolAwaitingOutcome`：进入长事务等待，封装等待规约与可选快照。

:data:`ToolExecutionOutcome` 是上述三种的封闭联合，作为
:meth:`ToolExecutor.execute` 的唯一返回类型。穷尽匹配由 pyright 通过
``typing.assert_never`` 守护。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from dayu.contracts.tool_await import ToolAwaitSnapshot, ToolAwaitSpec
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess


@dataclass(frozen=True, slots=True)
class ToolCompletedOutcome:
    """工具执行成功终态。

    :param result: 强类型成功结果。
    """

    result: ToolResultSuccess


@dataclass(frozen=True, slots=True)
class ToolFailedOutcome:
    """工具执行失败终态。

    :param result: 强类型失败结果。
    """

    result: ToolResultFailure


@dataclass(frozen=True, slots=True)
class ToolAwaitingOutcome:
    """工具进入长事务等待终态。

    :param await_spec: 等待规约。
    :param snapshot: 可选快照；为 ``None`` 表示无快照。
    """

    await_spec: ToolAwaitSpec
    snapshot: ToolAwaitSnapshot | None


ToolExecutionOutcome: TypeAlias = (
    ToolCompletedOutcome | ToolFailedOutcome | ToolAwaitingOutcome
)
"""工具执行 outcome 封闭联合。"""

__all__ = [
    "ToolCompletedOutcome",
    "ToolFailedOutcome",
    "ToolAwaitingOutcome",
    "ToolExecutionOutcome",
]
