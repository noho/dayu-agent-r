"""Host P8 attempt 终态映射 helper。

本模块提供 Host internal 的单一真源映射函数, 把 terminal
:class:`RunEventType` 推导为对应的 :class:`AttemptState`。该映射在
``_attempt_supervisor`` 与 ``_run_harness`` 两处都会使用; 为避免重复定
义、避免循环依赖, 抽到本独立小模块, 仅依赖 Host internal 契约。

属于 Host attempt 语义, 不进入 ``dayu.runtime`` 公共运行时基础设施;
也不属于 ``dayu.host`` 的 public ``__all__``。
"""

from __future__ import annotations

from dayu.host._internal_contracts import AttemptState
from dayu.host.contracts import RunEventType

_ERROR_NON_TERMINAL_RUN_EVENT_FOR_ATTEMPT: str = (
    "attempt state mapping requires a terminal RunEvent"
)


def attempt_state_from_terminal_event_type(
    event_type: RunEventType,
) -> AttemptState:
    """把 terminal :class:`RunEventType` 映射为对应的 :class:`AttemptState`。

    映射关系:

    - ``FINAL_ANSWER`` -> ``SUCCEEDED``
    - ``RUN_FAILED``   -> ``FAILED``
    - ``RUN_CANCELLED``-> ``CANCELLED``
    - ``RUN_SUSPENDED``-> ``SUSPENDED``

    本函数只接受 RunEventType 枚举, 不接受已构造的 RunEvent, 让
    supervisor 在 append 之前即可推导 :class:`AttemptTerminalLink` 中
    的 ``terminal_state`` 与 ``close_terminal`` 的 ``state`` 参数。

    :param event_type: terminal RunEvent 类型。
    :returns: 对应 :class:`AttemptState`。
    :raises ValueError: 入参非 terminal RunEvent 类型时抛出。
    """

    match event_type:
        case RunEventType.FINAL_ANSWER:
            return AttemptState.SUCCEEDED
        case RunEventType.RUN_FAILED:
            return AttemptState.FAILED
        case RunEventType.RUN_CANCELLED:
            return AttemptState.CANCELLED
        case RunEventType.RUN_SUSPENDED:
            return AttemptState.SUSPENDED
        case _:
            raise ValueError(_ERROR_NON_TERMINAL_RUN_EVENT_FOR_ATTEMPT)


__all__ = ["attempt_state_from_terminal_event_type"]
