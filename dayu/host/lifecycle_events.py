"""Host Run lifecycle event type 与 terminal status 契约。

本模块是 Host Run lifecycle event type、terminal event set 与 public outbox
terminal item set 的代码真源。调用方可以传入 EventLog 中的原始 ``event_type``
字符串，由本模块统一完成解析与分类，避免 projection、read API、dispatch 或
durable helper 各自复制 terminal 集合。
"""

from __future__ import annotations

from enum import StrEnum

from dayu.host.api import HostTerminalStatus, RunStatus


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


HOST_RUN_TERMINAL_EVENT_TYPES: tuple[HostRunEventType, ...] = (
    HostRunEventType.RUN_SUCCEEDED,
    HostRunEventType.RUN_FAILED,
    HostRunEventType.RUN_CANCELLED,
    HostRunEventType.RUN_LOST,
)
"""Host Run terminal canonical fact 事件集合，包含 ``RUN_LOST``。"""

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
