"""Host public read facade。

本模块提供只读 public facade，从 durable Session / Run / EventLog truth
构造 snapshot 与事件补读结果。读取路径不使用 projection checkpoint、
内存订阅位置、outbox state 或 session-local cursor。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.host.api import (
    HOST_EVENT_STREAM_DEFAULT_LIMIT,
    HOST_EVENT_STREAM_MAX_LIMIT,
    HostApiError,
    HostApiErrorCode,
    HostEventStream,
    HostEventView,
    HostStreamCursor,
    RunSnapshot,
    SessionSnapshot,
)
from dayu.host.command import HostCommandHandle
from dayu.host.durable.event_log import EventLogRow, read_events_after
from dayu.host.durable.state import (
    read_run_by_id,
    read_session_by_id,
    read_session_slot_by_session_id,
    run_snapshot_from_row,
    session_snapshot_from_rows,
)
from dayu.host.durable.transaction import HostTransaction


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
    """

    return HostEventView(
        event_sequence=row.event_sequence,
        event_id=row.event_id,
        event_type=row.event_type,
        session_id=row.session_id,
        run_id=row.run_id,
        payload_ref=row.payload_ref,
        payload_digest=row.payload_digest,
    )


__all__ = ["get_run", "get_session", "stream_run_events"]
