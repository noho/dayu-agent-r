"""工具执行 outcome 封闭联合契约。

工具执行的终态有四种：

- :class:`ToolCompletedOutcome`：成功，封装 :class:`ToolResultSuccess`。
- :class:`ToolFailedOutcome`：失败，封装 :class:`ToolResultFailure`。
- :class:`ToolAwaitingOutcome`：进入长事务等待，封装等待规约与可选快照。
- :class:`ToolCancelledOutcome`：工具级取消（区别于 run 级取消，亦不是失败）。

:data:`ToolExecutionOutcome` 是上述四种的封闭联合，作为
:class:`BatchToolExecutionRecord.outcome` 的取值范围。穷尽匹配由
pyright 通过 ``typing.assert_never`` 守护。

本模块同时定义批式执行的 record / outcome 容器：

- :class:`BatchToolExecutionRecord`：单次工具调用对应的输出记录。
- :class:`BatchToolExecutionOutcome`：批式握手的整体返回，承载与输入
  ``calls`` 一一对应的 record 序列。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from dayu.contracts.tool_await import ToolAwaitSnapshot, ToolAwaitSpec
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
)


TOOL_CANCELLED_REASON_APPROVAL_DENIED: str = "approval_denied"
"""工具级取消原因常量：审批被拒。"""

TOOL_CANCELLED_REASON_HOST_CANCELLED: str = "host_cancelled"
"""工具级取消原因常量：Host 治理决策取消该工具。"""

TOOL_CANCELLED_REASON_TIMEOUT: str = "timeout"
"""工具级取消原因常量：工具自身超时取消。"""

ALLOWED_TOOL_CANCELLED_REASONS: frozenset[str] = frozenset(
    {
        TOOL_CANCELLED_REASON_APPROVAL_DENIED,
        TOOL_CANCELLED_REASON_HOST_CANCELLED,
        TOOL_CANCELLED_REASON_TIMEOUT,
    }
)
""":class:`ToolCancelledOutcome.reason` 允许的常量集合。"""


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


@dataclass(frozen=True, slots=True)
class ToolCancelledOutcome:
    """工具级取消终态。

    区别于 run 级取消：run 级取消由调用方主动撤回整个运行；工具级取消
    是单次工具调用在工具自身边界内被取消（如工具内部超时、上层治理决策
    放弃单个工具），不连带影响其它工具调用与整个 run。

    语义上取消不等同于失败：取消终态不计入连续失败工具批次计数，由消费侧
    自行解释。本契约层不感知任何 Engine 内部计数器或字段名。

    :param reason: 取消原因机器码，必须取自
        :data:`ALLOWED_TOOL_CANCELLED_REASONS`。
    :param message: 面向 LLM 的人类可读说明；不允许空字符串或纯空白。
    :param hint: 可选恢复提示，注入 LLM 时合并到投影体里。
    :param meta: 中性元信息（如 tool_name / started_at / finished_at），
        与其它 outcome 保持一致；无元信息时为 ``None``。
    """

    reason: str
    message: str
    hint: str | None
    meta: ToolResultMeta | None

    def __post_init__(self) -> None:
        """构造期校验取消语义最小完整性。

        :returns: 无返回值。
        :raises ValueError: ``reason`` 不在
            :data:`ALLOWED_TOOL_CANCELLED_REASONS` 内或 ``message``
            为空 / 纯空白时抛出。
        """

        if self.reason not in ALLOWED_TOOL_CANCELLED_REASONS:
            raise ValueError(
                "ToolCancelledOutcome.reason must be one of"
                f" {sorted(ALLOWED_TOOL_CANCELLED_REASONS)}, got {self.reason!r}"
            )
        if self.message.strip() == "":
            raise ValueError("ToolCancelledOutcome.message must be non-empty")


ToolExecutionOutcome: TypeAlias = (
    ToolCompletedOutcome
    | ToolFailedOutcome
    | ToolAwaitingOutcome
    | ToolCancelledOutcome
)
"""工具执行 outcome 封闭联合。"""


@dataclass(frozen=True, slots=True)
class BatchToolExecutionRecord:
    """批式执行返回的单条记录。

    :param tool_call_id: 与输入 ``ToolCallRequest.tool_call_id`` 严格对应。
    :param outcome: 该次工具调用的终态。
    """

    tool_call_id: str
    outcome: ToolExecutionOutcome


@dataclass(frozen=True, slots=True)
class BatchToolExecutionOutcome:
    """批式工具执行整体返回。

    与输入 :class:`BatchToolExecutionRequest.calls` 形成严格双射：

    - ``len(records) == len(calls)``；
    - 每个 ``tool_call_id`` 在 ``records`` 中恰好出现一次；
    - 不得含输入中不存在的 ``tool_call_id``。

    任何违反双射的输出由 Engine 转为 ``tool_batch_outcome_mismatch``
    终态失败。

    :param records: 与输入 ``calls`` 一一对应的记录序列。
    """

    records: tuple[BatchToolExecutionRecord, ...]


__all__ = [
    "ALLOWED_TOOL_CANCELLED_REASONS",
    "BatchToolExecutionOutcome",
    "BatchToolExecutionRecord",
    "TOOL_CANCELLED_REASON_APPROVAL_DENIED",
    "TOOL_CANCELLED_REASON_HOST_CANCELLED",
    "TOOL_CANCELLED_REASON_TIMEOUT",
    "ToolAwaitingOutcome",
    "ToolCancelledOutcome",
    "ToolCompletedOutcome",
    "ToolExecutionOutcome",
    "ToolFailedOutcome",
]
