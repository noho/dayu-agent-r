"""Host EventLog event type 与 lifecycle 状态契约。

本模块是 Host EventLog ``event_type`` 合法集合、Run lifecycle event type、
Attempt lifecycle event type、terminal event set、closeout-supported Attempt
terminal subset 与 public outbox terminal item set 的代码真源。调用方可以传入
EventLog 中的原始 ``event_type`` 字符串，由本模块统一完成解析与分类，避免
durable schema、row decoder、projection、read API、dispatch 或 durable helper
各自复制合法集合。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypeAlias

from dayu.host.api import AttemptStatus, HostTerminalStatus, RunStatus


class HostSessionEventType(StrEnum):
    """Host Session lifecycle EventLog 事件类型。"""

    SESSION_CREATED = "SESSION_CREATED"
    SESSION_CLOSED = "SESSION_CLOSED"


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
    """Host Attempt lifecycle EventLog 事件类型。"""

    ATTEMPT_STARTED = "ATTEMPT_STARTED"
    ATTEMPT_RUNNING = "ATTEMPT_RUNNING"
    ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
    ATTEMPT_FAILED = "ATTEMPT_FAILED"
    ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
    ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
    ATTEMPT_STEERED = "ATTEMPT_STEERED"
    ATTEMPT_LOST = "ATTEMPT_LOST"


class HostAdmissionCommandEventType(StrEnum):
    """Host admission 与 command request EventLog 事件类型。"""

    USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
    STEER_REQUESTED = "STEER_REQUESTED"
    RETRY_REQUESTED = "RETRY_REQUESTED"
    REPLAY_REQUESTED = "REPLAY_REQUESTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RESUME_REQUESTED = "RESUME_REQUESTED"


class HostToolWaitEventType(StrEnum):
    """Host tool runtime 与 wait governance EventLog 事件类型。"""

    TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
    TOOL_CALL_GOVERNED = "TOOL_CALL_GOVERNED"
    TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
    TOOL_AWAITING = "TOOL_AWAITING"
    TOOL_CALLS_BATCH_READY = "TOOL_CALLS_BATCH_READY"
    TOOL_CALLS_BATCH_DONE = "TOOL_CALLS_BATCH_DONE"
    WAIT_LATE_RESULT_REJECTED = "WAIT_LATE_RESULT_REJECTED"


class HostContextGovernanceEventType(StrEnum):
    """Host context governance EventLog 事件类型。"""

    CONTEXT_COMPACTION_REQUESTED = "CONTEXT_COMPACTION_REQUESTED"
    CONTEXT_COMPACTED = "CONTEXT_COMPACTED"
    CONTEXT_COMPACTION_FAILED = "CONTEXT_COMPACTION_FAILED"
    CONTEXT_COMPACTION_ATTEMPT_REJECTED = "CONTEXT_COMPACTION_ATTEMPT_REJECTED"


class HostRunnerInputEventType(StrEnum):
    """Host runner input 与 usage projection EventLog 事件类型。"""

    RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
    RUNNER_CALL_INPUT_ITERATION_LINKED = "RUNNER_CALL_INPUT_ITERATION_LINKED"
    USAGE_REPORTED = "USAGE_REPORTED"


class HostEngineDiagnosticEventType(StrEnum):
    """Host Engine / provider diagnostic EventLog 事件类型。"""

    ENGINE_EVENT_REJECTED = "ENGINE_EVENT_REJECTED"
    ENGINE_EVENT_DIAGNOSTIC = "ENGINE_EVENT_DIAGNOSTIC"
    HOST_LIFECYCLE_DIAGNOSTIC = "HOST_LIFECYCLE_DIAGNOSTIC"
    PROVIDER_DIAGNOSTIC = "PROVIDER_DIAGNOSTIC"
    PROVIDER_PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"


class HostPreviewEventType(StrEnum):
    """Host preview-only Engine EventLog 事件类型。"""

    ITERATION_STARTED = "ITERATION_STARTED"
    CONTENT_COMPLETED = "CONTENT_COMPLETED"
    ITERATION_COMPLETED = "ITERATION_COMPLETED"


HostEventType: TypeAlias = (
    HostSessionEventType
    | HostRunEventType
    | HostAttemptEventType
    | HostAdmissionCommandEventType
    | HostToolWaitEventType
    | HostContextGovernanceEventType
    | HostRunnerInputEventType
    | HostEngineDiagnosticEventType
    | HostPreviewEventType
)
"""Host EventLog ``event_type`` 的完整 typed 联合。"""


HOST_SESSION_LIFECYCLE_EVENT_TYPES: tuple[HostSessionEventType, ...] = (
    HostSessionEventType.SESSION_CREATED,
    HostSessionEventType.SESSION_CLOSED,
)
"""Host Session lifecycle canonical fact 事件集合。"""

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

HOST_ATTEMPT_LIFECYCLE_EVENT_TYPES: tuple[HostAttemptEventType, ...] = (
    HostAttemptEventType.ATTEMPT_STARTED,
    HostAttemptEventType.ATTEMPT_RUNNING,
    *HOST_ATTEMPT_TERMINAL_EVENT_TYPES,
)
"""Host Attempt lifecycle 与 terminal canonical fact 事件集合。"""

HOST_ADMISSION_COMMAND_EVENT_TYPES: tuple[HostAdmissionCommandEventType, ...] = (
    HostAdmissionCommandEventType.USER_INPUT_ACCEPTED,
    HostAdmissionCommandEventType.STEER_REQUESTED,
    HostAdmissionCommandEventType.RETRY_REQUESTED,
    HostAdmissionCommandEventType.REPLAY_REQUESTED,
    HostAdmissionCommandEventType.CANCEL_REQUESTED,
    HostAdmissionCommandEventType.RESUME_REQUESTED,
)
"""Host admission 与 command request 事件集合。"""

HOST_TOOL_WAIT_EVENT_TYPES: tuple[HostToolWaitEventType, ...] = (
    HostToolWaitEventType.TOOL_CALL_REQUESTED,
    HostToolWaitEventType.TOOL_CALL_GOVERNED,
    HostToolWaitEventType.TOOL_RESULT_ACCEPTED,
    HostToolWaitEventType.TOOL_AWAITING,
    HostToolWaitEventType.TOOL_CALLS_BATCH_READY,
    HostToolWaitEventType.TOOL_CALLS_BATCH_DONE,
    HostToolWaitEventType.WAIT_LATE_RESULT_REJECTED,
)
"""Host tool runtime 与 wait governance 事件集合。"""

HOST_CONTEXT_GOVERNANCE_EVENT_TYPES: tuple[HostContextGovernanceEventType, ...] = (
    HostContextGovernanceEventType.CONTEXT_COMPACTION_REQUESTED,
    HostContextGovernanceEventType.CONTEXT_COMPACTED,
    HostContextGovernanceEventType.CONTEXT_COMPACTION_FAILED,
    HostContextGovernanceEventType.CONTEXT_COMPACTION_ATTEMPT_REJECTED,
)
"""Host context governance 事件集合。"""

HOST_RUNNER_INPUT_EVENT_TYPES: tuple[HostRunnerInputEventType, ...] = (
    HostRunnerInputEventType.RUNNER_CALL_INPUT_ASSEMBLED,
    HostRunnerInputEventType.RUNNER_CALL_INPUT_ITERATION_LINKED,
    HostRunnerInputEventType.USAGE_REPORTED,
)
"""Host runner input 与 usage 事件集合。"""

HOST_ENGINE_DIAGNOSTIC_EVENT_TYPES: tuple[HostEngineDiagnosticEventType, ...] = (
    HostEngineDiagnosticEventType.ENGINE_EVENT_REJECTED,
    HostEngineDiagnosticEventType.ENGINE_EVENT_DIAGNOSTIC,
    HostEngineDiagnosticEventType.HOST_LIFECYCLE_DIAGNOSTIC,
    HostEngineDiagnosticEventType.PROVIDER_DIAGNOSTIC,
    HostEngineDiagnosticEventType.PROVIDER_PROTOCOL_ERROR,
)
"""Host Engine / provider diagnostic 事件集合。"""

HOST_PREVIEW_EVENT_TYPES: tuple[HostPreviewEventType, ...] = (
    HostPreviewEventType.ITERATION_STARTED,
    HostPreviewEventType.CONTENT_COMPLETED,
    HostPreviewEventType.ITERATION_COMPLETED,
)
"""Host preview-only Engine 事件集合。"""

HOST_EVENT_TYPE_CATEGORIES: tuple[tuple[HostEventType, ...], ...] = (
    HOST_SESSION_LIFECYCLE_EVENT_TYPES,
    HOST_RUN_LIFECYCLE_EVENT_TYPES,
    HOST_ATTEMPT_LIFECYCLE_EVENT_TYPES,
    HOST_ADMISSION_COMMAND_EVENT_TYPES,
    HOST_TOOL_WAIT_EVENT_TYPES,
    HOST_CONTEXT_GOVERNANCE_EVENT_TYPES,
    HOST_RUNNER_INPUT_EVENT_TYPES,
    HOST_ENGINE_DIAGNOSTIC_EVENT_TYPES,
    HOST_PREVIEW_EVENT_TYPES,
)
"""Host EventLog event type 分类集合，顺序用于 DDL 和测试稳定断言。"""

_HOST_EVENT_TYPE_BY_VALUE: dict[str, HostEventType] = {
    event_type.value: event_type
    for category in HOST_EVENT_TYPE_CATEGORIES
    for event_type in category
}

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


def parse_host_event_type(event_type: str) -> HostEventType | None:
    """解析 Host EventLog event type 字符串。

    :param event_type: EventLog row 或 append request 中的原始 ``event_type``。
    :returns: 识别到的 Host EventLog event type；未知值返回 ``None``。
    :raises: 无主动抛出。
    """

    return _HOST_EVENT_TYPE_BY_VALUE.get(event_type)


def serialize_host_event_type(event_type: HostEventType) -> str:
    """把 Host EventLog event type 序列化为 durable 文本。

    :param event_type: typed Host EventLog event type。
    :returns: 可写入 SQLite ``event_log.event_type`` 的稳定文本。
    :raises ValueError: 输入不是 Host EventLog event type 时抛出。
    """

    if parse_host_event_type(event_type.value) is event_type:
        return event_type.value
    raise ValueError("unsupported Host EventLog event type")


def all_host_event_type_values() -> tuple[str, ...]:
    """返回 Host EventLog event type 的完整合法文本集合。

    :returns: 按分类稳定排序的所有合法 ``event_type`` 文本。
    :raises: 无主动抛出。
    """

    return tuple(
        event_type.value
        for category in HOST_EVENT_TYPE_CATEGORIES
        for event_type in category
    )


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


def host_event_type_values(event_types: tuple[HostEventType, ...]) -> tuple[str, ...]:
    """把 typed Host EventLog event type 集合转换为 EventLog 字符串集合。

    :param event_types: typed Host EventLog event type tuple。
    :returns: 可供 SQL ``IN`` 参数、DDL 或 projection filter 使用的字符串 tuple。
    :raises: 无主动抛出。
    """

    return tuple(event_type.value for event_type in event_types)
