"""Host Run lifecycle event type、Attempt terminal event type 与状态契约。

本模块是 Host Run lifecycle event type、Host Attempt terminal event type、
terminal event set、closeout-supported Attempt terminal subset 与 public
outbox terminal item set 的代码真源。调用方可以传入 EventLog 中的原始
``event_type`` 字符串，由本模块统一完成解析与分类，避免 projection、read
API、dispatch 或 durable helper 各自复制 terminal 集合。
"""

from __future__ import annotations

from enum import StrEnum

from dayu.host.api import AttemptStatus, HostTerminalStatus, RunStatus


class HostRunEventType(StrEnum):
    """Host Run lifecycle EventLog 事件类型。"""

    RUN_ACCEPTED = "RUN_ACCEPTED"
    RUN_QUEUED = "RUN_QUEUED"
    RUN_STARTED = "RUN_STARTED"
    RUN_WAITING = "RUN_WAITING"
    RUN_CANCELLING = "RUN_CANCELLING"
    RUN_RECOVERING = "RUN_RECOVERING"
    RUN_SUCCEEDED = "RUN_SUCCEEDED"
    RUN_FAILED = "RUN_FAILED"
    RUN_CANCELLED = "RUN_CANCELLED"
    RUN_LOST = "RUN_LOST"


class HostAttemptEventType(StrEnum):
    """Host Attempt terminal EventLog 事件类型。

    当前 P3-A 只定义 terminal 成员；非终态 Attempt event type 不属于本轮
    terminal closeout owner 收敛范围。
    """

    ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
    ATTEMPT_FAILED = "ATTEMPT_FAILED"
    ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
    ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
    ATTEMPT_STEERED = "ATTEMPT_STEERED"
    ATTEMPT_LOST = "ATTEMPT_LOST"


HOST_RUN_TERMINAL_EVENT_TYPES: tuple[HostRunEventType, ...] = (
    HostRunEventType.RUN_SUCCEEDED,
    HostRunEventType.RUN_FAILED,
    HostRunEventType.RUN_CANCELLED,
    HostRunEventType.RUN_LOST,
)
"""Host Run terminal canonical fact 事件集合，包含 ``RUN_LOST``。"""

HOST_ATTEMPT_TERMINAL_EVENT_TYPES: tuple[HostAttemptEventType, ...] = (
    HostAttemptEventType.ATTEMPT_SUCCEEDED,
    HostAttemptEventType.ATTEMPT_FAILED,
    HostAttemptEventType.ATTEMPT_CANCELLED,
    HostAttemptEventType.ATTEMPT_SUSPENDED,
    HostAttemptEventType.ATTEMPT_STEERED,
    HostAttemptEventType.ATTEMPT_LOST,
)
"""Host Attempt durable terminal canonical fact 事件集合。

``ATTEMPT_SUSPENDED`` 与 ``ATTEMPT_STEERED`` 是 durable Attempt 终态事件，
但不属于 Run / Attempt 联合 terminal closeout 支持的子集。
"""

CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES: tuple[HostAttemptEventType, ...] = (
    HostAttemptEventType.ATTEMPT_SUCCEEDED,
    HostAttemptEventType.ATTEMPT_FAILED,
    HostAttemptEventType.ATTEMPT_CANCELLED,
    HostAttemptEventType.ATTEMPT_LOST,
)
"""Run / Attempt 联合 terminal closeout 支持的 Attempt terminal 事件子集。"""

PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES: tuple[HostRunEventType, ...] = (
    HostRunEventType.RUN_SUCCEEDED,
    HostRunEventType.RUN_FAILED,
    HostRunEventType.RUN_CANCELLED,
)
"""会生成 public Outbox terminal item 的事件集合，不包含 ``RUN_LOST``。"""

HOST_RUN_LIFECYCLE_EVENT_TYPES: tuple[HostRunEventType, ...] = (
    HostRunEventType.RUN_ACCEPTED,
    HostRunEventType.RUN_QUEUED,
    HostRunEventType.RUN_STARTED,
    HostRunEventType.RUN_WAITING,
    HostRunEventType.RUN_CANCELLING,
    HostRunEventType.RUN_RECOVERING,
    *HOST_RUN_TERMINAL_EVENT_TYPES,
)
"""Host Run lifecycle 与 terminal canonical fact 事件集合。"""

_RUN_STATUS_BY_TERMINAL_EVENT_TYPE: dict[HostRunEventType, RunStatus] = {
    HostRunEventType.RUN_SUCCEEDED: RunStatus.SUCCEEDED,
    HostRunEventType.RUN_FAILED: RunStatus.FAILED,
    HostRunEventType.RUN_CANCELLED: RunStatus.CANCELLED,
    HostRunEventType.RUN_LOST: RunStatus.LOST,
}

_TERMINAL_EVENT_TYPE_BY_RUN_STATUS: dict[RunStatus, HostRunEventType] = {
    RunStatus.SUCCEEDED: HostRunEventType.RUN_SUCCEEDED,
    RunStatus.FAILED: HostRunEventType.RUN_FAILED,
    RunStatus.CANCELLED: HostRunEventType.RUN_CANCELLED,
    RunStatus.LOST: HostRunEventType.RUN_LOST,
}

_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS: dict[
    AttemptStatus, HostAttemptEventType
] = {
    AttemptStatus.SUCCEEDED: HostAttemptEventType.ATTEMPT_SUCCEEDED,
    AttemptStatus.FAILED: HostAttemptEventType.ATTEMPT_FAILED,
    AttemptStatus.CANCELLED: HostAttemptEventType.ATTEMPT_CANCELLED,
    AttemptStatus.SUSPENDED: HostAttemptEventType.ATTEMPT_SUSPENDED,
    AttemptStatus.STEERED: HostAttemptEventType.ATTEMPT_STEERED,
    AttemptStatus.LOST: HostAttemptEventType.ATTEMPT_LOST,
}

_CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS: dict[
    AttemptStatus, HostAttemptEventType
] = {
    AttemptStatus.SUCCEEDED: HostAttemptEventType.ATTEMPT_SUCCEEDED,
    AttemptStatus.FAILED: HostAttemptEventType.ATTEMPT_FAILED,
    AttemptStatus.CANCELLED: HostAttemptEventType.ATTEMPT_CANCELLED,
    AttemptStatus.LOST: HostAttemptEventType.ATTEMPT_LOST,
}

_HOST_TERMINAL_STATUS_BY_EVENT_TYPE: dict[HostRunEventType, HostTerminalStatus] = {
    HostRunEventType.RUN_SUCCEEDED: HostTerminalStatus.SUCCEEDED,
    HostRunEventType.RUN_FAILED: HostTerminalStatus.FAILED,
    HostRunEventType.RUN_CANCELLED: HostTerminalStatus.CANCELLED,
    HostRunEventType.RUN_LOST: HostTerminalStatus.LOST,
}


def parse_host_run_event_type(event_type: str) -> HostRunEventType | None:
    """解析 EventLog 原始 event type 字符串。

    :param event_type: EventLog row 中的原始 ``event_type``。
    :returns: 识别到的 Host Run event type；未知或非 Run event 时返回 ``None``。
    :raises: 无主动抛出。
    """

    try:
        return HostRunEventType(event_type)
    except ValueError:
        return None


def run_status_for_terminal_event(event_type: str) -> RunStatus | None:
    """把 Host terminal event type 映射为 durable Run status。

    :param event_type: EventLog row 中的原始 ``event_type``。
    :returns: 对应 ``RunStatus``；非 terminal Run event 时返回 ``None``。
    :raises: 无主动抛出。
    """

    parsed = parse_host_run_event_type(event_type)
    if parsed is None:
        return None
    return _RUN_STATUS_BY_TERMINAL_EVENT_TYPE.get(parsed)


def host_terminal_status_for_terminal_event(
    event_type: str,
) -> HostTerminalStatus | None:
    """把 Host terminal event type 映射为 public terminal status。

    :param event_type: EventLog row 中的原始 ``event_type``。
    :returns: 对应 ``HostTerminalStatus``；非 terminal Run event 时返回 ``None``。
    :raises: 无主动抛出。
    """

    parsed = parse_host_run_event_type(event_type)
    if parsed is None:
        return None
    return _HOST_TERMINAL_STATUS_BY_EVENT_TYPE.get(parsed)


def run_terminal_event_type_for_status(status: RunStatus) -> HostRunEventType:
    """把 Run terminal status 映射为 Host Run terminal event type。

    :param status: Run 状态。
    :returns: 对应的 Host Run terminal event type。
    :raises ValueError: ``status`` 不是当前支持的 Run terminal status 时抛出。
    """

    event_type = _TERMINAL_EVENT_TYPE_BY_RUN_STATUS.get(status)
    if event_type is None:
        raise ValueError(f"unsupported Run terminal status: {status.value}")
    return event_type


def attempt_terminal_event_type_for_status(
    status: AttemptStatus,
) -> HostAttemptEventType:
    """把 durable Attempt terminal status 映射为 Host Attempt terminal event type。

    ``SUSPENDED`` 与 ``STEERED`` 是 durable Attempt 终态，本 helper 会返回对应
    event type；它们不属于 Run / Attempt 联合 terminal closeout 支持的子集。
    closeout path 必须使用 ``closeout_attempt_terminal_event_type_for_status``。

    :param status: Attempt 状态。
    :returns: 对应的 Host Attempt terminal event type。
    :raises ValueError: ``status`` 不是当前支持的 Attempt terminal status 时抛出。
    """

    event_type = _TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS.get(status)
    if event_type is None:
        raise ValueError(f"unsupported Attempt terminal status: {status.value}")
    return event_type


def closeout_attempt_terminal_event_type_for_status(
    status: AttemptStatus,
) -> HostAttemptEventType:
    """把 closeout-supported Attempt terminal status 映射为 event type。

    :param status: Attempt 状态。
    :returns: 可进入 Run / Attempt 联合 terminal closeout 的 Attempt event type。
    :raises ValueError: ``status`` 不是 closeout-supported Attempt terminal status
        时抛出；其中 ``SUSPENDED`` 与 ``STEERED`` 是 durable terminal，但不属于
        closeout-supported subset。
    """

    event_type = _CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS.get(status)
    if event_type is None:
        raise ValueError(
            f"unsupported closeout Attempt terminal status: {status.value}"
        )
    return event_type


def is_host_run_terminal_event(event_type: str) -> bool:
    """判断事件是否为 Host Run terminal canonical fact。

    :param event_type: EventLog row 中的原始 ``event_type``。
    :returns: 属于 Host Run terminal event set 时返回 ``True``。
    :raises: 无主动抛出。
    """

    return run_status_for_terminal_event(event_type) is not None


def is_public_outbox_terminal_item_event(event_type: str) -> bool:
    """判断事件是否应生成 public Outbox terminal item。

    :param event_type: EventLog row 中的原始 ``event_type``。
    :returns: 属于 public Outbox terminal item set 时返回 ``True``。
    :raises: 无主动抛出。
    """

    parsed = parse_host_run_event_type(event_type)
    return parsed in PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES


def event_type_values(event_types: tuple[HostRunEventType, ...]) -> tuple[str, ...]:
    """把 typed Host Run event type 集合转换为 EventLog 字符串集合。

    :param event_types: typed Host Run event type tuple。
    :returns: 可供 SQL ``IN`` 参数或 projection filter 使用的字符串 tuple。
    :raises: 无主动抛出。
    """

    return tuple(event_type.value for event_type in event_types)


def attempt_event_type_values(
    event_types: tuple[HostAttemptEventType, ...],
) -> tuple[str, ...]:
    """把 typed Host Attempt event type 集合转换为 EventLog 字符串集合。

    :param event_types: typed Host Attempt event type tuple。
    :returns: 可供 SQL ``IN`` 参数或 projection filter 使用的字符串 tuple。
    :raises: 无主动抛出。
    """

    return tuple(event_type.value for event_type in event_types)
