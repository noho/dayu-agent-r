"""Host public read facade。

本模块提供只读 public facade，从 durable Session / Run / EventLog truth
构造 snapshot 与事件补读结果。读取路径不使用 projection checkpoint、
内存订阅位置、outbox state 或 session-local cursor。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.api import (
    HOST_EVENT_STREAM_DEFAULT_LIMIT,
    HOST_EVENT_STREAM_MAX_LIMIT,
    HostApiError,
    HostApiErrorCode,
    HostEventClass,
    HostEvent,
    HostEventKind,
    HostEventStream,
    HostEventView,
    HostFinalAnswerView,
    HostStreamCursor,
    HostTerminalStatus,
    RunSnapshot,
    SessionSnapshot,
)
from dayu.host.command import HostCommandHandle
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, read_events_after
from dayu.host.durable.payload import PayloadKind, read_payload_descriptor
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.state import (
    read_run_by_id,
    read_session_by_id,
    read_session_slot_by_session_id,
    run_snapshot_from_row,
    session_snapshot_from_rows,
)
from dayu.host.durable.transaction import HostTransaction

_SESSION_WATCH_BATCH_LIMIT = 64
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_PAYLOAD_FIELD_SUMMARY = "summary"
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_FINISH_REASON = "finish_reason"
_PAYLOAD_FIELD_FILTERED = "filtered"
_PAYLOAD_FIELD_DEGRADED = "degraded"
_PAYLOAD_FIELD_MESSAGE = "message"
_PAYLOAD_FIELD_REASON = "reason"


def get_session(host: HostCommandHandle, session_id: str) -> SessionSnapshot:
    """读取 Session durable truth，并返回 Session snapshot。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :returns: durable truth 生成的 Session snapshot，包含 active Run 与 queued Run 索引。
    :raises HostApiError: handle 已关闭或 Session 不存在时抛出。
    """

    return host._run_read(_GetSessionOperation(session_id=session_id))


def get_run(host: HostCommandHandle, run_id: str) -> RunSnapshot:
    """读取 Run durable truth，并返回 Run snapshot。

    :param host: Host command handle。
    :param run_id: 目标 Run id。
    :returns: durable Run row 生成的 Run snapshot。
    :raises HostApiError: handle 已关闭或 Run 不存在时抛出。
    """

    return host._run_read(_GetRunOperation(run_id=run_id))


def session_live_event_start_cursor(
    host: HostCommandHandle, session_id: str
) -> int:
    """读取 Session live watch 起始 cursor。

    本函数只校验 Session 存在并返回当前 EventLog 最新序号；调用方随后只
    观察该 cursor 之后的新事件，不执行离线补读。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :returns: 当前 EventLog 最新全局序号。
    :raises HostApiError: Session 不存在时抛出。
    """

    return host._run_read(
        _SessionLiveEventStartCursorOperation(session_id=session_id)
    )


def read_session_host_events_after(
    host: HostCommandHandle, session_id: str, cursor: int
) -> "_SessionHostEventBatch":
    """读取 Session live watch cursor 之后的 HostEvent 投影。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param cursor: 已消费的全局 EventLog 序号。
    :returns: 本批 Host-owned typed event 与推进后的 cursor。
    :raises HostApiError: Session 不存在时抛出。
    :raises HostDurableError: EventLog 或 terminal summary payload 损坏时抛出。
    """

    return host._run_read(
        _ReadSessionHostEventsAfterOperation(
            session_id=session_id,
            cursor=cursor,
        )
    )


def stream_run_events(
    host: HostCommandHandle,
    run_id: str,
    cursor: HostStreamCursor,
    limit: int | None = None,
) -> HostEventStream:
    """按全局 EventLog cursor 补读指定 Run 的事件视图。

    ``limit`` 是本次最多扫描的全局 EventLog row 数，也是返回事件数量上限。
    与目标 Run 无关的 row 会被扫描并推进 ``next_cursor``，但不会进入
    ``events``。

    :param host: Host command handle。
    :param run_id: 目标 Run id。
    :param cursor: 调用方最后已消费的全局 EventLog cursor。
    :param limit: 最大扫描 row 数；``None`` 使用 public 默认值。
    :returns: 过滤后的目标 Run 事件与下一次补读 cursor。
    :raises HostApiError: Run 不存在，或 limit 不在 public 允许范围内时抛出。
    """

    return host._run_read(
        _StreamRunEventsOperation(
            run_id=run_id,
            cursor=cursor,
            limit=limit,
        )
    )


@dataclass(frozen=True, slots=True)
class _GetSessionOperation:
    """get_session read transaction body。"""

    session_id: str

    def __call__(self, transaction: HostTransaction) -> SessionSnapshot:
        """执行 get_session 只读事务。

        :param transaction: 当前 Host transaction。
        :returns: Session snapshot。
        :raises HostApiError: Session 不存在时抛出。
        """

        session = read_session_by_id(transaction, self.session_id)
        if session is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="Session not found",
                retryable=False,
            )
        return session_snapshot_from_rows(
            transaction,
            session,
            read_session_slot_by_session_id(transaction, self.session_id),
        )


@dataclass(frozen=True, slots=True)
class _GetRunOperation:
    """get_run read transaction body。"""

    run_id: str

    def __call__(self, transaction: HostTransaction) -> RunSnapshot:
        """执行 get_run 只读事务。

        :param transaction: 当前 Host transaction。
        :returns: Run snapshot。
        :raises HostApiError: Run 不存在时抛出。
        """

        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="Run not found",
                retryable=False,
            )
        return run_snapshot_from_row(run)


@dataclass(frozen=True, slots=True)
class _SessionHostEventBatch:
    """Session live HostEvent 读取批次。

    :param events: 本批映射出的 public HostEvent。
    :param next_cursor: 下一轮读取使用的全局 EventLog cursor。
    """

    events: tuple[HostEvent, ...]
    next_cursor: int


@dataclass(frozen=True, slots=True)
class _SessionLiveEventStartCursorOperation:
    """session live watch 起始 cursor read transaction body。"""

    session_id: str

    def __call__(self, transaction: HostTransaction) -> int:
        """执行起始 cursor 读取。

        :param transaction: 当前 Host transaction。
        :returns: 当前 EventLog 最大全局序号。
        :raises HostApiError: Session 不存在时抛出。
        """

        _require_session_exists(transaction, self.session_id)
        return _latest_event_sequence(transaction)


@dataclass(frozen=True, slots=True)
class _ReadSessionHostEventsAfterOperation:
    """session live HostEvent batch read transaction body。"""

    session_id: str
    cursor: int

    def __call__(self, transaction: HostTransaction) -> _SessionHostEventBatch:
        """执行 Session HostEvent 投影读取。

        :param transaction: 当前 Host transaction。
        :returns: HostEvent 批次。
        :raises HostApiError: Session 不存在时抛出。
        :raises HostDurableError: cursor 非法或 payload 损坏时抛出。
        """

        _require_session_exists(transaction, self.session_id)
        scanned = read_events_after(
            transaction,
            self.cursor,
            limit=_SESSION_WATCH_BATCH_LIMIT,
        )
        next_cursor = self.cursor if len(scanned) == 0 else scanned[-1].event_sequence
        return _SessionHostEventBatch(
            events=tuple(
                _host_event_from_row(transaction, row)
                for row in scanned
                if row.session_id == self.session_id
            ),
            next_cursor=next_cursor,
        )


@dataclass(frozen=True, slots=True)
class _StreamRunEventsOperation:
    """stream_run_events read transaction body。"""

    run_id: str
    cursor: HostStreamCursor
    limit: int | None

    def __call__(self, transaction: HostTransaction) -> HostEventStream:
        """执行 EventLog-backed stream 补读。

        :param transaction: 当前 Host transaction。
        :returns: Host event stream。
        :raises HostApiError: Run 不存在或 limit 非法时抛出。
        """

        if read_run_by_id(transaction, self.run_id) is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="Run not found",
                retryable=False,
            )
        resolved_limit = _resolve_stream_limit(self.limit)
        scanned = read_events_after(
            transaction,
            self.cursor.event_sequence,
            limit=resolved_limit,
        )
        if len(scanned) == 0:
            next_cursor = self.cursor
        else:
            next_cursor = HostStreamCursor(
                event_sequence=scanned[-1].event_sequence
            )
        return HostEventStream(
            events=tuple(
                _event_view_from_row(row)
                for row in scanned
                if row.run_id == self.run_id
            ),
            next_cursor=next_cursor,
        )


def _resolve_stream_limit(limit: int | None) -> int:
    """解析并校验 public stream limit。

    :param limit: 调用方传入的 limit；``None`` 表示 public 默认值。
    :returns: 解析后的正整数 limit。
    :raises HostApiError: limit 小于等于零或超过最大值时抛出。
    """

    resolved = HOST_EVENT_STREAM_DEFAULT_LIMIT if limit is None else limit
    if resolved <= 0 or resolved > HOST_EVENT_STREAM_MAX_LIMIT:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="Host event stream limit is out of range",
            retryable=False,
        )
    return resolved


def _event_view_from_row(row: EventLogRow) -> HostEventView:
    """把 EventLog row 映射为 public HostEventView。

    :param row: EventLog durable row。
    :returns: 不包含 policy decision、reason 或 inline payload 的事件视图。
    :raises HostDurableError: EventLog class 不是当前 public event class 时抛出。
    """

    return HostEventView(
        event_sequence=row.event_sequence,
        event_id=row.event_id,
        event_class=_public_event_class_from_durable(row.event_class),
        event_type=row.event_type,
        session_id=row.session_id,
        run_id=row.run_id,
        payload_ref=row.payload_ref,
        payload_digest=row.payload_digest,
    )


def _public_event_class_from_durable(event_class: EventClass) -> HostEventClass:
    """把 durable EventLog class 映射为 public HostEventClass。

    :param event_class: durable EventLog row 的事件分类。
    :returns: public event class。
    :raises HostDurableError: 事件分类不是当前 public enum 成员时抛出。
    """

    if not isinstance(event_class, EventClass):
        raise HostDurableError("EventLog event_class is invalid")
    try:
        return HostEventClass(event_class.value)
    except ValueError as exc:
        raise HostDurableError("EventLog event_class is not public") from exc


def _require_session_exists(
    transaction: HostTransaction, session_id: str
) -> None:
    """校验 Session 存在。

    :param transaction: 当前 Host transaction。
    :param session_id: 目标 Session id。
    :returns: ``None``。
    :raises HostApiError: Session 不存在时抛出。
    """

    if read_session_by_id(transaction, session_id) is None:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Session not found",
            retryable=False,
        )


def _latest_event_sequence(transaction: HostTransaction) -> int:
    """读取当前 EventLog 最新全局序号。

    :param transaction: 当前 Host transaction。
    :returns: 最新 ``event_sequence``；无事件时为 ``0``。
    :raises HostDurableError: schema 中序号类型非法时抛出。
    """

    row = transaction.fetchone(
        f"SELECT COALESCE(MAX(event_sequence), 0) AS latest FROM {TABLE_EVENT_LOG}"
    )
    if row is None:
        return 0
    latest = row.get("latest")
    if not isinstance(latest, int):
        raise HostDurableError("latest EventLog sequence is invalid")
    return latest


def _host_event_from_row(
    transaction: HostTransaction, row: EventLogRow
) -> HostEvent:
    """把 EventLog row 投影为 Service-facing HostEvent。

    :param transaction: 当前 Host transaction。
    :param row: EventLog durable row。
    :returns: Host-owned typed event。
    :raises HostDurableError: terminal payload 损坏时抛出。
    """

    if row.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
        return _succeeded_host_event(transaction, row)
    if row.event_type == _EVENT_TYPE_RUN_FAILED:
        return _failed_host_event(row)
    if row.event_type == _EVENT_TYPE_RUN_CANCELLED:
        return _cancelled_host_event(row)
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        kind=HostEventKind.PROGRESS,
        dedupe_key=row.event_id,
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
    )


def _succeeded_host_event(
    transaction: HostTransaction, row: EventLogRow
) -> HostEvent:
    """把 ``RUN_SUCCEEDED`` row 投影为带 final answer 的 HostEvent。

    :param transaction: 当前 Host transaction。
    :param row: ``RUN_SUCCEEDED`` EventLog row。
    :returns: 成功终态 HostEvent。
    :raises HostDurableError: terminal summary payload 缺失或字段非法时抛出。
    """

    payload = _payload_object(row)
    summary_ref = _required_payload_text(
        payload,
        field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF,
        row=row,
    )
    summary_digest = _required_payload_text(
        payload,
        field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST,
        row=row,
    )
    terminal_summary = _terminal_summary_object(
        transaction,
        payload_ref=summary_ref,
        payload_digest=summary_digest,
        row=row,
    )
    final_answer = HostFinalAnswerView(
        content=_required_payload_text(
            terminal_summary,
            field_name=_PAYLOAD_FIELD_CONTENT,
            row=row,
        ),
        filtered=_required_payload_bool(
            terminal_summary,
            field_name=_PAYLOAD_FIELD_FILTERED,
            row=row,
        ),
        degraded=_required_payload_bool(
            terminal_summary,
            field_name=_PAYLOAD_FIELD_DEGRADED,
            row=row,
        ),
        finish_reason=_optional_payload_text(
            terminal_summary,
            field_name=_PAYLOAD_FIELD_FINISH_REASON,
            row=row,
        ),
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        kind=HostEventKind.SUCCEEDED,
        dedupe_key=row.event_id,
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=final_answer,
        error_message=None,
        cancel_reason=None,
    )


def _failed_host_event(row: EventLogRow) -> HostEvent:
    """把 ``RUN_FAILED`` row 投影为失败终态 HostEvent。

    :param row: ``RUN_FAILED`` EventLog row。
    :returns: 失败终态 HostEvent。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    payload = _payload_object(row)
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        kind=HostEventKind.FAILED,
        dedupe_key=row.event_id,
        terminal_status=HostTerminalStatus.FAILED,
        final_answer=None,
        error_message=_optional_payload_text(
            payload,
            field_name=_PAYLOAD_FIELD_MESSAGE,
            row=row,
        ),
        cancel_reason=None,
    )


def _cancelled_host_event(row: EventLogRow) -> HostEvent:
    """把 ``RUN_CANCELLED`` row 投影为取消终态 HostEvent。

    :param row: ``RUN_CANCELLED`` EventLog row。
    :returns: 取消终态 HostEvent。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    payload = _payload_object(row)
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        kind=HostEventKind.CANCELLED,
        dedupe_key=row.event_id,
        terminal_status=HostTerminalStatus.CANCELLED,
        final_answer=None,
        error_message=None,
        cancel_reason=_optional_payload_text(
            payload,
            field_name=_PAYLOAD_FIELD_REASON,
            row=row,
        ),
    )


def _terminal_summary_object(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_digest: str,
    row: EventLogRow,
) -> Mapping[str, JsonValue]:
    """读取 terminal summary descriptor 并返回 summary object。

    :param transaction: 当前 Host transaction。
    :param payload_ref: terminal summary payload ref。
    :param payload_digest: terminal summary payload digest。
    :param row: 关联 terminal EventLog row，用于错误上下文。
    :returns: terminal summary JSON object。
    :raises HostDurableError: descriptor、digest 或 summary 字段非法时抛出。
    """

    payload = _sqlite_payload_object(
        transaction,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        row=row,
    )
    summary = payload.get(_PAYLOAD_FIELD_SUMMARY)
    if not isinstance(summary, Mapping):
        raise HostDurableError("terminal summary payload is missing summary object")
    return cast(Mapping[str, JsonValue], summary)


def _sqlite_payload_object(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_digest: str,
    row: EventLogRow,
) -> Mapping[str, JsonValue]:
    """读取 SQLite payload descriptor 对应的 JSON object。

    :param transaction: 当前 Host transaction。
    :param payload_ref: payload descriptor 引用。
    :param payload_digest: 期望 payload digest。
    :param row: 关联 EventLog row，用于错误上下文。
    :returns: payload JSON object。
    :raises HostDurableError: descriptor 缺失、类型非法或 JSON 不是 object 时抛出。
    """

    descriptor = read_payload_descriptor(transaction, payload_ref)
    if descriptor is None:
        raise HostDurableError("terminal summary payload descriptor is missing")
    if descriptor.payload_kind is not PayloadKind.SQLITE_PAYLOAD:
        raise HostDurableError("terminal summary payload must be sqlite payload")
    if descriptor.payload_digest != payload_digest:
        raise HostDurableError("terminal summary payload digest mismatch")
    if descriptor.sqlite_payload_id is None:
        raise HostDurableError("terminal summary sqlite payload id is missing")
    payload_row = transaction.fetchone(
        f"""
        SELECT payload_json
        FROM {TABLE_SQLITE_PAYLOADS}
        WHERE payload_id = ?
        """,
        (descriptor.sqlite_payload_id,),
    )
    if payload_row is None:
        raise HostDurableError("terminal summary sqlite payload row is missing")
    payload_json = payload_row.get("payload_json")
    if not isinstance(payload_json, str):
        raise HostDurableError("terminal summary sqlite payload JSON is invalid")
    return _json_object(payload_json, row=row)


def _payload_object(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog inline payload object。

    :param row: EventLog row。
    :returns: payload JSON object。
    :raises HostDurableError: payload JSON 非法或不是 object 时抛出。
    """

    return _json_object(row.payload_json, row=row)


def _json_object(payload_json: str, *, row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 JSON 文本并校验为 object。

    :param payload_json: canonical JSON 文本。
    :param row: 关联 EventLog row，用于错误上下文。
    :returns: JSON object。
    :raises HostDurableError: JSON 无法解析或不是 object 时抛出。
    """

    try:
        payload = cast(JsonValue, json.loads(payload_json))
    except json.JSONDecodeError as exc:
        raise HostDurableError("EventLog payload JSON is invalid") from exc
    if not isinstance(payload, Mapping):
        raise HostDurableError(
            f"EventLog payload for {row.event_id} must be a JSON object"
        )
    return cast(Mapping[str, JsonValue], payload)


def _required_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str, row: EventLogRow
) -> str:
    """读取必填文本 payload 字段。

    :param payload: payload JSON object。
    :param field_name: 字段名。
    :param row: 关联 EventLog row，用于错误上下文。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失、非文本或为空时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(
            f"EventLog payload field {field_name} for {row.event_id} must be text"
        )
    return value


def _optional_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str, row: EventLogRow
) -> str | None:
    """读取可选文本 payload 字段。

    :param payload: payload JSON object。
    :param field_name: 字段名。
    :param row: 关联 EventLog row，用于错误上下文。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但非文本或为空时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(
            f"EventLog payload field {field_name} for {row.event_id} must be text"
        )
    return value


def _required_payload_bool(
    payload: Mapping[str, JsonValue], *, field_name: str, row: EventLogRow
) -> bool:
    """读取必填布尔 payload 字段。

    :param payload: payload JSON object。
    :param field_name: 字段名。
    :param row: 关联 EventLog row，用于错误上下文。
    :returns: 布尔值。
    :raises HostDurableError: 字段缺失或非布尔时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise HostDurableError(
            f"EventLog payload field {field_name} for {row.event_id} must be bool"
        )
    return value


__all__ = ["get_run", "get_session", "stream_run_events"]
