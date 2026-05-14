"""Host durable state row codec。

本模块只负责 Phase 3 durable state tables 的 row dataclass、状态枚举编解码
与 ``HostRow`` 转换。它不追加 EventLog、不打开 transaction，也不实现
Session lifecycle、admission、promotion、cancel 或 command path 语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from dayu.host.api import (
    AttemptStatus,
    RunStatus,
    SessionStatus,
    SourceRunRelation,
)
from dayu.host.durable._validation import (
    optional_int as _optional_int,
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import HostRow

_StatusT = TypeVar("_StatusT", bound=StrEnum)


class DispatchRecordStatus(StrEnum):
    """Attempt dispatch record 状态。

    ``PENDING`` 表示 Host 已创建 pre-dispatch durable truth，但尚未进入真实
    scheduler / WorkerProxy；``CANCELLED`` 表示 pending dispatch 在派发前取消。
    """

    PENDING = "pending"
    CANCELLED = "cancelled"


class WorkerKind(StrEnum):
    """dispatch record 指向的 worker 类型。"""

    LOCAL = "local"
    REMOTE = "remote"


class RunStartReason(StrEnum):
    """Run 从 queued 或 accepted 状态进入 running 的原因。"""

    INITIAL = "initial"
    QUEUE_PROMOTION = "queue_promotion"


@dataclass(frozen=True, slots=True)
class SessionRow:
    """``host_sessions`` durable row。

    字段保存 Session lifecycle 的 durable truth；事件字段引用 EventLog canonical
    facts，关闭字段只在 ``status`` 为 ``CLOSED`` 时存在。
    """

    session_id: str
    status: SessionStatus
    metadata_json: str
    created_event_id: str
    created_event_sequence: int
    closed_event_id: str | None
    closed_event_sequence: int | None
    created_at: str
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class SessionSlotRow:
    """``host_session_slots`` durable row。

    字段保存 ``(scope, slot_key)`` 到当前 Session 的 durable binding。
    """

    scope: str
    slot_key: str
    session_id: str
    bound_event_id: str
    bound_event_sequence: int
    metadata_json: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RunRow:
    """``host_runs`` durable row。

    字段保存 Run lifecycle、queue FIFO 游标、active attempt 指针与 terminal refs。
    Phase 3 不在此 dataclass 中承载 command 行为。
    """

    run_id: str
    session_id: str
    status: RunStatus
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    accepted_event_id: str
    accepted_event_sequence: int
    queued_event_id: str | None
    queued_event_sequence: int | None
    started_event_id: str | None
    started_event_sequence: int | None
    terminal_event_id: str | None
    terminal_event_sequence: int | None
    current_attempt_id: str | None
    source_run_id: str | None
    source_run_relation: SourceRunRelation | None
    execution_target: str
    queue_policy: str
    created_at: str
    updated_at: str
    terminal_at: str | None


@dataclass(frozen=True, slots=True)
class AttemptRow:
    """``host_attempts`` durable row。

    字段保存一次 execution attempt 的状态、execution id 和 terminal refs。
    """

    attempt_id: str
    run_id: str
    execution_id: str
    status: AttemptStatus
    started_event_id: str
    started_event_sequence: int
    terminal_event_id: str | None
    terminal_event_sequence: int | None
    created_at: str
    updated_at: str
    terminal_at: str | None


@dataclass(frozen=True, slots=True)
class DispatchRecordRow:
    """``host_attempt_dispatch_records`` durable row。

    字段保存 Attempt pre-dispatch startup truth；Phase 3 只允许 pending/cancelled。
    """

    dispatch_record_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    status: DispatchRecordStatus
    worker_kind: WorkerKind
    execution_target: str
    owner_host_instance_id: str | None
    created_event_id: str
    created_event_sequence: int
    cancelled_event_id: str | None
    cancelled_event_sequence: int | None
    created_at: str
    updated_at: str
    cancelled_at: str | None


def serialize_session_status(status: SessionStatus) -> str:
    """序列化公共 Session 状态。

    :param status: 公共 Session status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``SessionStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="SessionStatus")


def deserialize_session_status(value: str) -> SessionStatus:
    """反序列化公共 Session 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``SessionStatus``。
    :raises HostDurableError: 文本为空或不属于 ``SessionStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=SessionStatus, enum_name="SessionStatus"
    )


def serialize_run_status(status: RunStatus) -> str:
    """序列化公共 Run 状态。

    :param status: 公共 Run status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``RunStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="RunStatus")


def deserialize_run_status(value: str) -> RunStatus:
    """反序列化公共 Run 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``RunStatus``。
    :raises HostDurableError: 文本为空或不属于 ``RunStatus`` 时抛出。
    """

    return _deserialize_str_enum(value, enum_type=RunStatus, enum_name="RunStatus")


def serialize_attempt_status(status: AttemptStatus) -> str:
    """序列化公共 Attempt 状态。

    :param status: 公共 Attempt status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``AttemptStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="AttemptStatus")


def deserialize_attempt_status(value: str) -> AttemptStatus:
    """反序列化公共 Attempt 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``AttemptStatus``。
    :raises HostDurableError: 文本为空或不属于 ``AttemptStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=AttemptStatus, enum_name="AttemptStatus"
    )


def serialize_dispatch_record_status(status: DispatchRecordStatus) -> str:
    """序列化 dispatch record 状态。

    :param status: dispatch record status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``DispatchRecordStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="DispatchRecordStatus")


def deserialize_dispatch_record_status(value: str) -> DispatchRecordStatus:
    """反序列化 dispatch record 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``DispatchRecordStatus``。
    :raises HostDurableError: 文本为空或不属于 ``DispatchRecordStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value,
        enum_type=DispatchRecordStatus,
        enum_name="DispatchRecordStatus",
    )


def serialize_worker_kind(worker_kind: WorkerKind) -> str:
    """序列化 worker kind。

    :param worker_kind: worker kind enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``worker_kind`` 不是合法 ``WorkerKind`` 时抛出。
    """

    return _serialize_str_enum(worker_kind, enum_name="WorkerKind")


def deserialize_worker_kind(value: str) -> WorkerKind:
    """反序列化 worker kind。

    :param value: SQLite row 中读取的 worker kind 文本。
    :returns: ``WorkerKind``。
    :raises HostDurableError: 文本为空或不属于 ``WorkerKind`` 时抛出。
    """

    return _deserialize_str_enum(value, enum_type=WorkerKind, enum_name="WorkerKind")


def serialize_run_start_reason(reason: RunStartReason) -> str:
    """序列化 Run start reason。

    :param reason: Run start reason enum。
    :returns: canonical event payload 中使用的文本值。
    :raises HostDurableError: ``reason`` 不是合法 ``RunStartReason`` 时抛出。
    """

    return _serialize_str_enum(reason, enum_name="RunStartReason")


def deserialize_run_start_reason(value: str) -> RunStartReason:
    """反序列化 Run start reason。

    :param value: canonical event payload 中读取的 reason 文本。
    :returns: ``RunStartReason``。
    :raises HostDurableError: 文本为空或不属于 ``RunStartReason`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=RunStartReason, enum_name="RunStartReason"
    )


def session_row_from_host_row(row: HostRow) -> SessionRow:
    """把通用 HostRow 转换为 SessionRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``SessionRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    return SessionRow(
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        status=deserialize_session_status(
            _require_text(row.get("status"), field_name="status")
        ),
        metadata_json=_require_text(row.get("metadata_json"), field_name="metadata_json"),
        created_event_id=_require_text(
            row.get("created_event_id"), field_name="created_event_id"
        ),
        created_event_sequence=_require_int(
            row.get("created_event_sequence"), field_name="created_event_sequence"
        ),
        closed_event_id=_optional_text(
            row.get("closed_event_id"), field_name="closed_event_id"
        ),
        closed_event_sequence=_optional_int(
            row.get("closed_event_sequence"), field_name="closed_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        closed_at=_optional_text(row.get("closed_at"), field_name="closed_at"),
    )


def session_slot_row_from_host_row(row: HostRow) -> SessionSlotRow:
    """把通用 HostRow 转换为 SessionSlotRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``SessionSlotRow``。
    :raises HostDurableError: row 字段类型无效时抛出。
    """

    return SessionSlotRow(
        scope=_require_text(row.get("scope"), field_name="scope"),
        slot_key=_require_text(row.get("slot_key"), field_name="slot_key"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        bound_event_id=_require_text(
            row.get("bound_event_id"), field_name="bound_event_id"
        ),
        bound_event_sequence=_require_int(
            row.get("bound_event_sequence"), field_name="bound_event_sequence"
        ),
        metadata_json=_require_text(row.get("metadata_json"), field_name="metadata_json"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
    )


def run_row_from_host_row(row: HostRow) -> RunRow:
    """把通用 HostRow 转换为 RunRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``RunRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    source_relation_text = _optional_text(
        row.get("source_run_relation"), field_name="source_run_relation"
    )
    return RunRow(
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        status=deserialize_run_status(
            _require_text(row.get("status"), field_name="status")
        ),
        client_request_id=_require_text(
            row.get("client_request_id"), field_name="client_request_id"
        ),
        input_event_id=_require_text(
            row.get("input_event_id"), field_name="input_event_id"
        ),
        input_event_sequence=_require_int(
            row.get("input_event_sequence"), field_name="input_event_sequence"
        ),
        accepted_event_id=_require_text(
            row.get("accepted_event_id"), field_name="accepted_event_id"
        ),
        accepted_event_sequence=_require_int(
            row.get("accepted_event_sequence"), field_name="accepted_event_sequence"
        ),
        queued_event_id=_optional_text(
            row.get("queued_event_id"), field_name="queued_event_id"
        ),
        queued_event_sequence=_optional_int(
            row.get("queued_event_sequence"), field_name="queued_event_sequence"
        ),
        started_event_id=_optional_text(
            row.get("started_event_id"), field_name="started_event_id"
        ),
        started_event_sequence=_optional_int(
            row.get("started_event_sequence"), field_name="started_event_sequence"
        ),
        terminal_event_id=_optional_text(
            row.get("terminal_event_id"), field_name="terminal_event_id"
        ),
        terminal_event_sequence=_optional_int(
            row.get("terminal_event_sequence"), field_name="terminal_event_sequence"
        ),
        current_attempt_id=_optional_text(
            row.get("current_attempt_id"), field_name="current_attempt_id"
        ),
        source_run_id=_optional_text(
            row.get("source_run_id"), field_name="source_run_id"
        ),
        source_run_relation=_optional_source_run_relation(source_relation_text),
        execution_target=_require_text(
            row.get("execution_target"), field_name="execution_target"
        ),
        queue_policy=_require_text(row.get("queue_policy"), field_name="queue_policy"),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        terminal_at=_optional_text(row.get("terminal_at"), field_name="terminal_at"),
    )


def attempt_row_from_host_row(row: HostRow) -> AttemptRow:
    """把通用 HostRow 转换为 AttemptRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``AttemptRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    return AttemptRow(
        attempt_id=_require_text(row.get("attempt_id"), field_name="attempt_id"),
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        execution_id=_require_text(row.get("execution_id"), field_name="execution_id"),
        status=deserialize_attempt_status(
            _require_text(row.get("status"), field_name="status")
        ),
        started_event_id=_require_text(
            row.get("started_event_id"), field_name="started_event_id"
        ),
        started_event_sequence=_require_int(
            row.get("started_event_sequence"), field_name="started_event_sequence"
        ),
        terminal_event_id=_optional_text(
            row.get("terminal_event_id"), field_name="terminal_event_id"
        ),
        terminal_event_sequence=_optional_int(
            row.get("terminal_event_sequence"), field_name="terminal_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        terminal_at=_optional_text(row.get("terminal_at"), field_name="terminal_at"),
    )


def dispatch_record_row_from_host_row(row: HostRow) -> DispatchRecordRow:
    """把通用 HostRow 转换为 DispatchRecordRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``DispatchRecordRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    return DispatchRecordRow(
        dispatch_record_id=_require_text(
            row.get("dispatch_record_id"), field_name="dispatch_record_id"
        ),
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        attempt_id=_require_text(row.get("attempt_id"), field_name="attempt_id"),
        execution_id=_require_text(row.get("execution_id"), field_name="execution_id"),
        status=deserialize_dispatch_record_status(
            _require_text(row.get("status"), field_name="status")
        ),
        worker_kind=deserialize_worker_kind(
            _require_text(row.get("worker_kind"), field_name="worker_kind")
        ),
        execution_target=_require_text(
            row.get("execution_target"), field_name="execution_target"
        ),
        owner_host_instance_id=_optional_text(
            row.get("owner_host_instance_id"), field_name="owner_host_instance_id"
        ),
        created_event_id=_require_text(
            row.get("created_event_id"), field_name="created_event_id"
        ),
        created_event_sequence=_require_int(
            row.get("created_event_sequence"), field_name="created_event_sequence"
        ),
        cancelled_event_id=_optional_text(
            row.get("cancelled_event_id"), field_name="cancelled_event_id"
        ),
        cancelled_event_sequence=_optional_int(
            row.get("cancelled_event_sequence"), field_name="cancelled_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        cancelled_at=_optional_text(row.get("cancelled_at"), field_name="cancelled_at"),
    )


def _serialize_str_enum(value: StrEnum, *, enum_name: str) -> str:
    """序列化 StrEnum。

    :param value: 待序列化 enum。
    :param enum_name: 错误消息中使用的 enum 名称。
    :returns: enum 的 schema 文本值。
    :raises HostDurableError: enum 值为空或类型无效时抛出。
    """

    if not isinstance(value, StrEnum):
        raise HostDurableError(f"{enum_name} is invalid")
    _require_non_empty_text(value.value, field_name=enum_name)
    return value.value


def _deserialize_str_enum(
    value: str, *, enum_type: type[_StatusT], enum_name: str
) -> _StatusT:
    """反序列化 StrEnum。

    :param value: SQLite 或 payload 中的文本值。
    :param enum_type: 目标 enum 类型。
    :param enum_name: 错误消息中使用的 enum 名称。
    :returns: enum 值。
    :raises HostDurableError: 文本为空或不属于目标 enum 时抛出。
    """

    _require_non_empty_text(value, field_name=enum_name)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise HostDurableError(f"{enum_name} is invalid") from exc


def _optional_source_run_relation(value: str | None) -> SourceRunRelation | None:
    """反序列化 optional SourceRunRelation。

    :param value: SQLite row 中读取的 source relation 文本。
    :returns: ``SourceRunRelation`` 或 ``None``。
    :raises HostDurableError: 文本不属于 ``SourceRunRelation`` 时抛出。
    """

    if value is None:
        return None
    try:
        return SourceRunRelation(value)
    except ValueError as exc:
        raise HostDurableError("SourceRunRelation is invalid") from exc
