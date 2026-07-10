"""Host public read facade。

本模块提供只读 public facade，从 durable Session / Run / EventLog truth
构造 snapshot 与事件补读结果。读取路径不使用 projection checkpoint、
内存订阅位置、outbox state 或 session-local cursor。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.api import (
    HOST_EVENT_STREAM_DEFAULT_LIMIT,
    HOST_EVENT_STREAM_MAX_LIMIT,
    DrainOutboxTerminalItemsRequest,
    HostApiError,
    HostApiErrorCode,
    HostActivityCounts,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostActivityView,
    HostEventClass,
    HostEvent,
    HostEventKind,
    HostEventStream,
    HostEventView,
    HostFinalAnswerView,
    HostStreamCursor,
    HostTerminalStatus,
    HostThinkingView,
    ListSessionsResult,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    OutboxTerminalItemsBatch,
    OutboxTerminalItemState,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    SessionListItem,
    SessionSnapshot,
)
from dayu.host._terminal_diagnostics import _append_terminal_diagnostic_suffix
from dayu.host._terminal_answer import (
    required_assistant_final_answer_continuity_text,
)
from dayu.host.accepted_result_projection import (
    AcceptedToolResultStatus,
    project_accepted_tool_result,
)
from dayu.host.command import HostCommandHandle
from dayu.host.durable.codec import format_utc_timestamp, parse_utc_timestamp
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogRow,
    EventLogStore,
    read_events_after,
)
from dayu.host.durable.outbox import (
    OutboxTerminalItemRow,
    OutboxTerminalItemsPage,
    OutboxTerminalProjectionCatchupError,
    OutboxTerminalProjectionReadState,
    OutboxTerminalProjectionStatus,
    drain_outbox_terminal_items as _drain_outbox_terminal_items,
    read_outbox_terminal_items_after as _read_outbox_terminal_items_after,
    read_outbox_terminal_projection_state as _read_outbox_terminal_projection_state,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.state import (
    SessionWithSlotRows,
    read_all_sessions_with_slots,
    read_run_by_id,
    read_session_by_id,
    read_session_slot_by_session_id,
    run_snapshot_from_row,
    session_snapshot_from_rows,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.lifecycle_events import (
    HostRunEventType,
    parse_host_run_event_type,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.outbox import (
    OUTBOX_TERMINAL_CONSUMER_ID,
    catch_up_outbox_terminal_projection,
)

_SESSION_WATCH_BATCH_LIMIT = 64
_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_QUEUED = "RUN_QUEUED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_ATTEMPT_STARTED = "ATTEMPT_STARTED"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_TOOL_CALLS_BATCH_DONE = "TOOL_CALLS_BATCH_DONE"
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_CONTEXT_COMPACTION_REQUESTED = "CONTEXT_COMPACTION_REQUESTED"
_EVENT_TYPE_CONTEXT_COMPACTED = "CONTEXT_COMPACTED"
_EVENT_TYPE_CONTEXT_COMPACTION_FAILED = "CONTEXT_COMPACTION_FAILED"
_EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED = "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"
_EVENT_TYPE_REASONING_DELTA = "REASONING_DELTA"
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_FINISH_REASON = "finish_reason"
_PAYLOAD_FIELD_FILTERED = "filtered"
_PAYLOAD_FIELD_DEGRADED = "degraded"
_PAYLOAD_FIELD_MESSAGE = "message"
_PAYLOAD_FIELD_REASON = "reason"
_PAYLOAD_FIELD_PROVIDER_REQUEST_ID = "provider_request_id"
_PAYLOAD_FIELD_CLIENT_CORRELATION_ID = "client_correlation_id"
_PAYLOAD_FIELD_TERMINAL_STATUS = "terminal_status"
_PAYLOAD_FIELD_DELTA = "delta"
_PAYLOAD_FIELD_EFFECTIVE_TOOL_SET = "effective_tool_set"
_PAYLOAD_FIELD_EFFECTIVE_TOOL_DISPLAY_NAMES = "effective_tool_display_names"
_PAYLOAD_FIELD_TOOL_NAME = "tool_name"
_PAYLOAD_FIELD_TOOL_CALL_COUNT = "tool_call_count"
_PAYLOAD_FIELD_COMPLETED_COUNT = "completed_count"
_PAYLOAD_FIELD_FAILED_COUNT = "failed_count"
_PAYLOAD_FIELD_CANCELLED_COUNT = "cancelled_count"
_PAYLOAD_FIELD_ARGUMENT_KEY_COUNT = "argument_key_count"
_PAYLOAD_FIELD_OUTCOME_KIND = "outcome_kind"
_PAYLOAD_FIELD_ERROR_CODE = "error_code"
_PAYLOAD_FIELD_PROVIDER_ERROR_CODE = "provider_error_code"
_PAYLOAD_FIELD_FAILURE_METADATA = "failure_metadata"
_PAYLOAD_FIELD_WAIT_ID = "wait_id"
_PAYLOAD_FIELD_RETRYABLE = "retryable"
_PAYLOAD_FIELD_FAILURE_REASON = "failure_reason"
_ACTIVITY_SUMMARY_MAX_CHARS = 180

# EventLogStore 是无状态 durable primitive 方法容器；read projection 复用同一私有实例。
_EVENT_LOG_STORE = EventLogStore()


def get_session(host: HostCommandHandle, session_id: str) -> SessionSnapshot:
    """读取 Session durable truth，并返回 Session snapshot。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :returns: durable truth 生成的 Session snapshot，包含 active Run 与 queued Run 索引。
    :raises HostApiError: handle 已关闭或 Session 不存在时抛出。
    """

    return host._run_read(_GetSessionOperation(session_id=session_id))


def list_sessions(host: HostCommandHandle) -> ListSessionsResult:
    """读取全部未 purge Session 的 public 列表摘要。

    :param host: Host command handle。
    :returns: durable truth 生成的 Session 列表结果。
    :raises HostApiError: handle 已关闭或 durable 读取失败时抛出。
    """

    return host._run_read(_ListSessionsOperation())


def get_run(host: HostCommandHandle, run_id: str) -> RunSnapshot:
    """读取 Run durable truth，并返回 Run snapshot。

    :param host: Host command handle。
    :param run_id: 目标 Run id。
    :returns: durable Run row 生成的 Run snapshot。
    :raises HostApiError: handle 已关闭或 Run 不存在时抛出。
    """

    return host._run_read(_GetRunOperation(run_id=run_id))


def session_live_event_start_cursor(host: HostCommandHandle, session_id: str) -> int:
    """读取 Session live watch 起始 cursor。

    本函数只校验 Session 存在并返回当前 EventLog 最新序号；调用方随后只
    观察该 cursor 之后的新事件，不执行离线补读。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :returns: 当前 EventLog 最新全局序号。
    :raises HostApiError: Session 不存在时抛出。
    """

    return host._run_read(_SessionLiveEventStartCursorOperation(session_id=session_id))


def read_session_host_events_after(
    host: HostCommandHandle, session_id: str, cursor: int
) -> "_SessionHostEventBatch":
    """读取 Session live watch cursor 之后的 HostEvent 投影。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param cursor: 已消费的全局 EventLog 序号。
    :returns: 本批 Host-owned typed event 与推进后的 cursor。
    :raises HostApiError: Session 不存在时抛出。
    :raises HostDurableError: EventLog 或 terminal payload 损坏时抛出。
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


def read_outbox_terminal_items(
    host: HostCommandHandle,
    session_id: str,
    request: ReadOutboxTerminalItemsRequest,
) -> OutboxTerminalItemsBatch:
    """读取 public Outbox terminal items。

    本函数只接入 projection-owned outbox helper：先校验 Session 存在，再
    best-effort 追平 OutboxSink，最后从 durable outbox projection rows 读取
    batch。它不写 EventLog，不改变 Run / Attempt 状态，也不改变 item drain
    state。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param request: Outbox terminal read 请求。
    :returns: Outbox terminal item 批次。
    :raises HostApiError: handle 已关闭、Session 不存在或 durable 读取失败时抛出。
    """

    host._run_read(_RequireSessionExistsOperation(session_id=session_id))
    catchup_error = _catch_up_outbox_terminal_projection_best_effort(host)
    return host._run_read(
        _ReadOutboxTerminalItemsOperation(
            session_id=session_id,
            request=request,
            catchup_error=catchup_error,
        )
    )


def drain_outbox_terminal_items(
    host: HostCommandHandle,
    session_id: str,
    request: DrainOutboxTerminalItemsRequest,
) -> OutboxTerminalItemsBatch:
    """幂等 drain public Outbox terminal items。

    本函数只更新 Outbox projection queue state 与 drain idempotency row。drain
    不表达 channel 投递成功，不写 EventLog，不更新 Run / Attempt。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param request: Outbox terminal drain 请求。
    :returns: Outbox terminal item 批次。
    :raises HostApiError: handle 已关闭、Session 不存在、幂等冲突或 durable 写入失败时抛出。
    """

    host._run_read(_RequireSessionExistsOperation(session_id=session_id))
    catchup_error = _catch_up_outbox_terminal_projection_best_effort(host)
    return host._run_write(
        _DrainOutboxTerminalItemsOperation(
            session_id=session_id,
            request=request,
            catchup_error=catchup_error,
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
class _ListSessionsOperation:
    """list_sessions read transaction body。"""

    def __call__(self, transaction: HostTransaction) -> ListSessionsResult:
        """执行 list_sessions 只读事务。

        :param transaction: 当前 Host transaction。
        :returns: Session 列表结果。
        :raises HostDurableError: durable timestamp 或 row 字段无效时抛出。
        """

        rows = read_all_sessions_with_slots(transaction)
        return ListSessionsResult(
            sessions=tuple(
                _session_list_item_from_rows(transaction, row) for row in rows
            )
        )


def _session_list_item_from_rows(
    transaction: HostTransaction,
    rows: SessionWithSlotRows,
) -> SessionListItem:
    """把 durable Session/slot rows 转换为 public list item。

    :param transaction: 当前 Host transaction。
    :param rows: Session row 与当前 slot row。
    :returns: public Session list item。
    :raises HostDurableError: durable timestamp 或 row 字段无效时抛出。
    """

    snapshot = session_snapshot_from_rows(transaction, rows.session, rows.slot)
    return SessionListItem(
        session_id=snapshot.session_id,
        status=snapshot.status,
        slot=snapshot.slot,
        active_run_id=snapshot.active_run_id,
        queued_run_ids=snapshot.queued_run_ids,
        timeline_cursor=snapshot.timeline_cursor,
        created_at=_parse_session_row_timestamp(
            rows.session.created_at,
            field_name="created_at",
        ),
        closed_at=_parse_optional_session_row_timestamp(
            rows.session.closed_at,
            field_name="closed_at",
        ),
    )


def _parse_session_row_timestamp(value: str, *, field_name: str) -> datetime:
    """解析 Session row timestamp。

    :param value: durable 固定 UTC timestamp 文本。
    :param field_name: timestamp 字段名。
    :returns: timezone-aware UTC ``datetime``。
    :raises HostDurableError: timestamp 格式或日期值非法时抛出。
    """

    try:
        return parse_utc_timestamp(value)
    except ValueError as exc:
        raise HostDurableError(
            f"session row timestamp is invalid: {field_name}"
        ) from exc


def _parse_optional_session_row_timestamp(
    value: str | None, *, field_name: str
) -> datetime | None:
    """解析 optional Session row timestamp。

    :param value: durable 固定 UTC timestamp 文本；缺失时为 ``None``。
    :param field_name: timestamp 字段名。
    :returns: timezone-aware UTC ``datetime`` 或 ``None``。
    :raises HostDurableError: timestamp 格式或日期值非法时抛出。
    """

    if value is None:
        return None
    return _parse_session_row_timestamp(value, field_name=field_name)


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
            next_cursor = HostStreamCursor(event_sequence=scanned[-1].event_sequence)
        return HostEventStream(
            events=tuple(
                _event_view_from_row(row)
                for row in scanned
                if row.run_id == self.run_id
            ),
            next_cursor=next_cursor,
        )


@dataclass(frozen=True, slots=True)
class _RequireSessionExistsOperation:
    """Outbox public API 进入 projection catch-up 前的 Session 校验。"""

    session_id: str

    def __call__(self, transaction: HostTransaction) -> None:
        """执行 Session 存在性校验。

        :param transaction: 当前 Host transaction。
        :returns: ``None``。
        :raises HostApiError: Session 不存在时抛出。
        """

        _require_session_exists(transaction, self.session_id)


@dataclass(frozen=True, slots=True)
class _ReadOutboxTerminalItemsOperation:
    """read_outbox_terminal_items read transaction body。"""

    session_id: str
    request: ReadOutboxTerminalItemsRequest
    catchup_error: OutboxTerminalProjectionCatchupError | None

    def __call__(self, transaction: HostTransaction) -> OutboxTerminalItemsBatch:
        """读取 Outbox terminal item batch。

        :param transaction: 当前 Host transaction。
        :returns: Outbox terminal item 批次。
        :raises HostApiError: Session 不存在时抛出。
        :raises HostDurableError: durable outbox row 或 projection row 非法时抛出。
        """

        _require_session_exists(transaction, self.session_id)
        page = _read_outbox_terminal_items_after(
            transaction,
            self.session_id,
            after_event_sequence=self.request.after.event_sequence,
            seen_terminal_event_ids=self.request.seen_terminal_event_ids,
            limit=self.request.limit,
        )
        projection_state = _read_outbox_terminal_projection_state(
            transaction,
            OUTBOX_TERMINAL_CONSUMER_ID.value,
            catchup_error=self.catchup_error,
        )
        return _outbox_batch_from_page(page, projection_state)


@dataclass(frozen=True, slots=True)
class _DrainOutboxTerminalItemsOperation:
    """drain_outbox_terminal_items write transaction body。"""

    session_id: str
    request: DrainOutboxTerminalItemsRequest
    catchup_error: OutboxTerminalProjectionCatchupError | None

    def __call__(self, transaction: HostTransaction) -> OutboxTerminalItemsBatch:
        """执行 Outbox terminal item drain。

        :param transaction: 当前 Host transaction。
        :returns: Outbox terminal item 批次。
        :raises HostApiError: Session 不存在时抛出。
        :raises HostIdempotencyConflictError: drain request id 复用但语义不同
            时由 durable helper 抛出，外层 command handle 会映射为 public error。
        :raises HostDurableError: durable outbox row 或 projection row 非法时抛出。
        """

        _require_session_exists(transaction, self.session_id)
        page = _drain_outbox_terminal_items(
            transaction,
            self.session_id,
            after_event_sequence=self.request.after.event_sequence,
            seen_terminal_event_ids=self.request.seen_terminal_event_ids,
            limit=self.request.limit,
            drain_request_id=self.request.drain_request_id,
            drained_at=format_utc_timestamp(datetime.now(UTC)),
        )
        projection_state = _read_outbox_terminal_projection_state(
            transaction,
            OUTBOX_TERMINAL_CONSUMER_ID.value,
            catchup_error=self.catchup_error,
        )
        return _outbox_batch_from_page(page, projection_state)


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


def _require_session_exists(transaction: HostTransaction, session_id: str) -> None:
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


def _catch_up_outbox_terminal_projection_best_effort(
    host: HostCommandHandle,
) -> OutboxTerminalProjectionCatchupError | None:
    """best-effort 追平 Outbox terminal projection。

    :param host: Host command handle。
    :returns: catch-up 抛出未处理异常时返回摘要；成功或 runner 记录 failure row
        时返回 ``None``。
    """

    try:
        catch_up_outbox_terminal_projection(host._transaction_runner())
    except Exception as exc:
        return OutboxTerminalProjectionCatchupError(
            error_code=exc.__class__.__name__,
            error_message=str(exc) or "<empty outbox catch-up error>",
        )
    return None


def _outbox_batch_from_page(
    page: OutboxTerminalItemsPage,
    projection_state: OutboxTerminalProjectionReadState,
) -> OutboxTerminalItemsBatch:
    """把 durable outbox page 映射为 public batch。

    :param page: durable outbox page。
    :param projection_state: projection 状态。
    :returns: public Outbox terminal batch。
    :raises HostDurableError: row 字段无法映射为 public 类型时抛出。
    """

    return OutboxTerminalItemsBatch(
        items=tuple(_outbox_item_from_row(row) for row in page.rows),
        next_cursor=OutboxTerminalCursor(
            event_sequence=page.next_event_sequence,
        ),
        scanned_watermark=OutboxTerminalCursor(
            event_sequence=page.scanned_watermark,
        ),
        projection_checkpoint=OutboxTerminalCursor(
            event_sequence=projection_state.checkpoint_event_sequence,
        ),
        projection_status=_outbox_projection_status_from_durable(
            projection_state.status
        ),
        projection_error_code=projection_state.error_code,
        projection_error_message=projection_state.error_message,
        has_more=page.has_more,
    )


def _outbox_projection_status_from_durable(
    status: OutboxTerminalProjectionStatus,
) -> OutboxProjectionStatus:
    """把 durable Outbox projection 状态映射为 public enum。

    :param status: durable outbox helper 返回的 projection 状态。
    :returns: public Outbox projection 状态。
    :raises HostDurableError: durable 状态无法映射为 public enum 时抛出。
    """

    try:
        return OutboxProjectionStatus(status.value)
    except ValueError as exc:
        raise HostDurableError("outbox projection status is invalid") from exc


def _outbox_item_from_row(row: OutboxTerminalItemRow) -> OutboxTerminalItem:
    """把 durable outbox item row 映射为 public item。

    :param row: durable outbox terminal item row。
    :returns: public Outbox terminal item。
    :raises HostDurableError: durable row 字段不是 public enum 或 timestamp 非法时抛出。
    """

    try:
        terminal_status = HostTerminalStatus(row.terminal_status)
        item_state = OutboxTerminalItemState(row.item_state)
        projected_at = parse_utc_timestamp(row.projected_at)
    except ValueError as exc:
        raise HostDurableError("outbox terminal item row is invalid") from exc
    return OutboxTerminalItem(
        item_id=row.item_id,
        idempotency_key=row.idempotency_key,
        terminal_event_id=row.terminal_event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        terminal_status=terminal_status,
        dedupe_key=row.dedupe_key,
        final_answer=_final_answer_from_outbox_json(row.final_answer_json),
        error_message=row.error_message,
        cancel_reason=row.cancel_reason,
        result_ref=row.result_ref,
        result_digest=row.result_digest,
        terminal_summary_ref=row.terminal_summary_ref,
        terminal_summary_digest=row.terminal_summary_digest,
        projected_at=projected_at,
        item_state=item_state,
    )


def _final_answer_from_outbox_json(value: str | None) -> HostFinalAnswerView | None:
    """解析 Outbox row 中的 final answer JSON。

    :param value: durable outbox final answer JSON 文本；无 final answer 时为
        ``None``。
    :returns: public final answer view 或 ``None``。
    :raises HostDurableError: JSON 非法或字段类型/语义非法时抛出。
    """

    if value is None:
        return None
    try:
        parsed = cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HostDurableError("outbox final answer JSON is invalid") from exc
    if not isinstance(parsed, dict):
        raise HostDurableError("outbox final answer JSON must be object")
    content = parsed.get(_PAYLOAD_FIELD_CONTENT)
    filtered = parsed.get(_PAYLOAD_FIELD_FILTERED)
    degraded = parsed.get(_PAYLOAD_FIELD_DEGRADED)
    finish_reason = parsed.get(_PAYLOAD_FIELD_FINISH_REASON)
    terminal_status = parsed.get(_PAYLOAD_FIELD_TERMINAL_STATUS)
    if not isinstance(content, str):
        raise HostDurableError("outbox final answer content is invalid")
    if content.strip() == "":
        raise HostDurableError(
            "Outbox final answer field content must be non-empty text"
        )
    if not isinstance(filtered, bool):
        raise HostDurableError("outbox final answer filtered is invalid")
    if not isinstance(degraded, bool):
        raise HostDurableError("outbox final answer degraded is invalid")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise HostDurableError("outbox final answer finish_reason is invalid")
    if terminal_status != HostTerminalStatus.SUCCEEDED.value:
        raise HostDurableError("outbox final answer terminal_status is invalid")
    return HostFinalAnswerView(
        content=content,
        filtered=filtered,
        degraded=degraded,
        finish_reason=finish_reason,
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )


def _host_event_from_row(transaction: HostTransaction, row: EventLogRow) -> HostEvent:
    """把 EventLog row 投影为 Service-facing HostEvent。

    :param transaction: 当前 Host transaction。
    :param row: EventLog durable row。
    :returns: Host-owned typed event。
    :raises HostDurableError: terminal payload 损坏时抛出。
    """

    run_event_type = parse_host_run_event_type(row.event_type)
    if run_event_type is HostRunEventType.RUN_SUCCEEDED:
        return _succeeded_host_event(transaction, row)
    if run_event_type is HostRunEventType.RUN_FAILED:
        return _failed_host_event(row)
    if run_event_type is HostRunEventType.RUN_CANCELLED:
        return _cancelled_host_event(row)
    if run_event_type is HostRunEventType.RUN_LOST:
        return _lost_host_event(row)
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        event_class=_public_event_class_from_durable(row.event_class),
        event_type=row.event_type,
        kind=HostEventKind.PROGRESS,
        activity=_activity_from_row(transaction, row),
        thinking=_thinking_from_row(row),
        dedupe_key=row.event_id,
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
    )


def _succeeded_host_event(transaction: HostTransaction, row: EventLogRow) -> HostEvent:
    """把 ``RUN_SUCCEEDED`` row 投影为带 final answer 的 HostEvent。

    :param transaction: 当前 Host transaction。
    :param row: ``RUN_SUCCEEDED`` EventLog row。
    :returns: 成功终态 HostEvent。
    :raises HostDurableError: terminal payload 缺失或字段非法时抛出。
    """

    payload = _payload_object(row)
    final_answer = HostFinalAnswerView(
        content=required_assistant_final_answer_continuity_text(
            transaction,
            payload,
        ),
        filtered=_required_payload_bool(
            payload,
            field_name=_PAYLOAD_FIELD_FILTERED,
            row=row,
        ),
        degraded=_required_payload_bool(
            payload,
            field_name=_PAYLOAD_FIELD_DEGRADED,
            row=row,
        ),
        finish_reason=_optional_payload_text(
            payload,
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
        event_class=_public_event_class_from_durable(row.event_class),
        event_type=row.event_type,
        kind=HostEventKind.SUCCEEDED,
        activity=_run_lifecycle_activity(row),
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
    error_message = _optional_payload_text(
        payload,
        field_name=_PAYLOAD_FIELD_MESSAGE,
        row=row,
    )
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        event_class=_public_event_class_from_durable(row.event_class),
        event_type=row.event_type,
        kind=HostEventKind.FAILED,
        activity=_run_lifecycle_activity(row),
        dedupe_key=row.event_id,
        terminal_status=HostTerminalStatus.FAILED,
        final_answer=None,
        error_message=_append_terminal_diagnostic_suffix(
            error_message,
            provider_request_id=_optional_payload_text(
                payload,
                field_name=_PAYLOAD_FIELD_PROVIDER_REQUEST_ID,
                row=row,
            ),
            client_correlation_id=_optional_payload_text(
                payload,
                field_name=_PAYLOAD_FIELD_CLIENT_CORRELATION_ID,
                row=row,
            ),
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
        event_class=_public_event_class_from_durable(row.event_class),
        event_type=row.event_type,
        kind=HostEventKind.CANCELLED,
        activity=_run_lifecycle_activity(row),
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


def _lost_host_event(row: EventLogRow) -> HostEvent:
    """把 ``RUN_LOST`` row 投影为 lost 终态 HostEvent。

    :param row: ``RUN_LOST`` EventLog row。
    :returns: lost 终态 HostEvent。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    payload = _payload_object(row)
    return HostEvent(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        event_class=_public_event_class_from_durable(row.event_class),
        event_type=row.event_type,
        kind=HostEventKind.LOST,
        activity=_run_lifecycle_activity(row),
        dedupe_key=row.event_id,
        terminal_status=HostTerminalStatus.LOST,
        final_answer=None,
        error_message=_optional_payload_text(
            payload,
            field_name=_PAYLOAD_FIELD_MESSAGE,
            row=row,
        ),
        cancel_reason=None,
    )


def _activity_from_row(
    transaction: HostTransaction, row: EventLogRow
) -> HostActivityView | None:
    """按 allowlist 把 EventLog row 投影为安全 activity。

    :param transaction: 当前 Host transaction。
    :param row: EventLog durable row。
    :returns: 安全 activity view；未知或不适合展示时返回 ``None``。
    :raises: 无主动抛出。
    """

    if row.event_type in (
        _EVENT_TYPE_RUN_ACCEPTED,
        _EVENT_TYPE_RUN_QUEUED,
        _EVENT_TYPE_RUN_STARTED,
        _EVENT_TYPE_RUN_RECOVERING,
    ):
        return _run_lifecycle_activity(row)
    if row.event_type == _EVENT_TYPE_TOOL_CALL_REQUESTED:
        return _tool_call_requested_activity(transaction, row)
    if row.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
        return _tool_result_accepted_activity(transaction, row)
    if row.event_type == _EVENT_TYPE_TOOL_CALLS_BATCH_DONE:
        return _tool_calls_batch_done_activity(row)
    if row.event_type == _EVENT_TYPE_TOOL_AWAITING:
        return _tool_awaiting_activity(transaction, row)
    if row.event_type in (
        _EVENT_TYPE_CONTEXT_COMPACTION_REQUESTED,
        _EVENT_TYPE_CONTEXT_COMPACTED,
        _EVENT_TYPE_CONTEXT_COMPACTION_FAILED,
        _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    ):
        return _context_compaction_activity(row)
    if row.event_type == _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR:
        return _provider_protocol_error_activity(row)
    return None


def _thinking_from_row(row: EventLogRow) -> HostThinkingView | None:
    """把 reasoning delta row 投影为运行态 thinking 展示视图。

    :param row: EventLog durable row。
    :returns: thinking 展示视图；非 reasoning delta 或 payload 非法时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if row.event_type != _EVENT_TYPE_REASONING_DELTA:
        return None
    payload = _activity_payload_without_descriptor(row)
    delta = payload.get(_PAYLOAD_FIELD_DELTA)
    if not isinstance(delta, str) or delta.strip() == "":
        return None
    return HostThinkingView(text_delta=delta)


def _run_lifecycle_activity(row: EventLogRow) -> HostActivityView | None:
    """把必要 Run lifecycle event 投影为 activity。

    :param row: EventLog durable row。
    :returns: lifecycle activity；未知 lifecycle 类型返回 ``None``。
    :raises: 无主动抛出。
    """

    if row.event_type in (_EVENT_TYPE_RUN_ACCEPTED, _EVENT_TYPE_RUN_QUEUED):
        status = HostActivityStatus.STARTED
        title = "运行已接受"
    elif row.event_type == _EVENT_TYPE_RUN_STARTED:
        status = HostActivityStatus.IN_PROGRESS
        title = "运行已开始"
    elif row.event_type == _EVENT_TYPE_RUN_RECOVERING:
        status = HostActivityStatus.IN_PROGRESS
        title = "运行恢复中"
    elif row.event_type == HostRunEventType.RUN_SUCCEEDED.value:
        status = HostActivityStatus.COMPLETED
        title = "运行已完成"
    elif row.event_type == HostRunEventType.RUN_FAILED.value:
        status = HostActivityStatus.FAILED
        title = "运行失败"
    elif row.event_type == HostRunEventType.RUN_CANCELLED.value:
        status = HostActivityStatus.CANCELLED
        title = "运行已取消"
    elif row.event_type == HostRunEventType.RUN_LOST.value:
        status = HostActivityStatus.FAILED
        title = "运行已丢失"
    else:
        return None
    severity = (
        HostActivitySeverity.ERROR
        if status == HostActivityStatus.FAILED
        else (
            HostActivitySeverity.WARNING
            if status == HostActivityStatus.CANCELLED
            else HostActivitySeverity.INFO
        )
    )
    return HostActivityView(
        kind=HostActivityKind.RUN_LIFECYCLE,
        status=status,
        title=title,
        summary=None,
        severity=severity,
        tool_name=None,
        tool_display_name=None,
        counts=None,
    )


def _tool_call_requested_activity(
    transaction: HostTransaction, row: EventLogRow
) -> HostActivityView | None:
    """投影 preview ``TOOL_CALL_REQUESTED`` activity。

    :param transaction: 当前 Host transaction。
    :param row: TOOL_CALL_REQUESTED EventLog row。
    :returns: 工具调用开始 activity；canonical request atom 或 payload 缺关键字段时返回 ``None``。
    :raises: 无主动抛出。
    """

    if row.event_class is not EventClass.PREVIEW:
        return None
    payload = _activity_payload(transaction, row)
    if payload is None:
        return None
    tool_name = _payload_text(payload, _PAYLOAD_FIELD_TOOL_NAME)
    if tool_name is None:
        return None
    display_name = _tool_display_name(transaction, row, tool_name)
    argument_count = _payload_non_negative_int(
        payload, _PAYLOAD_FIELD_ARGUMENT_KEY_COUNT
    )
    summary = f"参数字段数：{argument_count}" if argument_count is not None else None
    return HostActivityView(
        kind=HostActivityKind.TOOL_CALL,
        status=HostActivityStatus.STARTED,
        title=f"调用工具：{display_name}",
        summary=summary,
        severity=HostActivitySeverity.INFO,
        tool_name=tool_name,
        tool_display_name=display_name,
        counts=None,
    )


def _tool_result_accepted_activity(
    transaction: HostTransaction, row: EventLogRow
) -> HostActivityView | None:
    """投影 ``TOOL_RESULT_ACCEPTED`` activity。

    :param transaction: 当前 Host transaction。
    :param row: TOOL_RESULT_ACCEPTED EventLog row。
    :returns: 工具结果 activity；payload 缺关键字段时返回 ``None``。
    :raises: 无主动抛出。
    """

    if row.event_class is EventClass.CANONICAL_FACT:
        return _canonical_tool_result_accepted_activity(transaction, row)
    if row.event_class is not EventClass.PREVIEW:
        return None
    return _preview_tool_result_accepted_activity(transaction, row)


def _canonical_tool_result_accepted_activity(
    transaction: HostTransaction, row: EventLogRow
) -> HostActivityView | None:
    """投影 canonical ``TOOL_RESULT_ACCEPTED`` activity。

    :param transaction: 当前 Host transaction。
    :param row: canonical accepted result row。
    :returns: 工具结果 activity；缺工具名时返回 ``None``。
    """

    projection = project_accepted_tool_result(transaction, row)
    if projection.tool_name is None:
        return None
    display_name = _tool_display_name(transaction, row, projection.tool_name)
    status, severity = _accepted_result_activity_state(projection.status)
    return HostActivityView(
        kind=HostActivityKind.TOOL_RESULT,
        status=status,
        title=f"工具返回：{display_name}",
        summary=f"结果状态：{projection.status.value}",
        severity=severity,
        tool_name=projection.tool_name,
        tool_display_name=display_name,
        counts=None,
    )


def _preview_tool_result_accepted_activity(
    transaction: HostTransaction, row: EventLogRow
) -> HostActivityView | None:
    """投影 preview ``TOOL_RESULT_ACCEPTED`` activity。

    :param transaction: 当前 Host transaction。
    :param row: preview accepted result row。
    :returns: 工具结果 activity；payload 缺关键字段时返回 ``None``。
    """

    payload = _activity_payload(transaction, row)
    if payload is None:
        return None
    tool_name = _payload_text(payload, _PAYLOAD_FIELD_TOOL_NAME)
    outcome_kind = _payload_text(payload, _PAYLOAD_FIELD_OUTCOME_KIND)
    if tool_name is None or outcome_kind is None:
        return None
    display_name = _tool_display_name(transaction, row, tool_name)
    status, severity = _tool_outcome_activity_state(outcome_kind)
    return HostActivityView(
        kind=HostActivityKind.TOOL_RESULT,
        status=status,
        title=f"工具返回：{display_name}",
        summary=f"结果状态：{outcome_kind}",
        severity=severity,
        tool_name=tool_name,
        tool_display_name=display_name,
        counts=None,
    )


def _accepted_result_activity_state(
    status: AcceptedToolResultStatus,
) -> tuple[HostActivityStatus, HostActivitySeverity]:
    """把 accepted-result projection status 映射为 activity 状态。

    :param status: accepted result projection status。
    :returns: activity status 与 severity。
    """

    if status is AcceptedToolResultStatus.COMPLETED:
        return HostActivityStatus.COMPLETED, HostActivitySeverity.INFO
    if status is AcceptedToolResultStatus.CANCELLED:
        return HostActivityStatus.CANCELLED, HostActivitySeverity.WARNING
    return HostActivityStatus.FAILED, HostActivitySeverity.ERROR


def _tool_calls_batch_done_activity(row: EventLogRow) -> HostActivityView | None:
    """投影 ``TOOL_CALLS_BATCH_DONE`` activity。

    :param row: TOOL_CALLS_BATCH_DONE EventLog row。
    :returns: 工具批次 activity；计数字段非法时返回 ``None``。
    :raises: 无主动抛出。
    """

    payload = _activity_payload_without_descriptor(row)
    total = _payload_non_negative_int(payload, _PAYLOAD_FIELD_TOOL_CALL_COUNT)
    completed = _payload_non_negative_int(payload, _PAYLOAD_FIELD_COMPLETED_COUNT)
    failed = _payload_non_negative_int(payload, _PAYLOAD_FIELD_FAILED_COUNT)
    cancelled = _payload_non_negative_int(payload, _PAYLOAD_FIELD_CANCELLED_COUNT)
    if total is None or completed is None or failed is None or cancelled is None:
        return None
    if failed > 0:
        status = HostActivityStatus.FAILED
        severity = HostActivitySeverity.ERROR
    elif cancelled > 0:
        status = HostActivityStatus.CANCELLED
        severity = HostActivitySeverity.WARNING
    else:
        status = HostActivityStatus.COMPLETED
        severity = HostActivitySeverity.INFO
    return HostActivityView(
        kind=HostActivityKind.TOOL_BATCH,
        status=status,
        title="工具批次完成",
        summary=None,
        severity=severity,
        tool_name=None,
        tool_display_name=None,
        counts=HostActivityCounts(
            total=total,
            completed=completed,
            failed=failed,
            cancelled=cancelled,
        ),
    )


def _tool_awaiting_activity(
    transaction: HostTransaction, row: EventLogRow
) -> HostActivityView | None:
    """投影工具等待 activity。

    :param transaction: 当前 Host transaction。
    :param row: TOOL_AWAITING EventLog row。
    :returns: 等待 activity；未知工具 payload 时返回通用等待 activity。
    :raises: 无主动抛出。
    """

    payload = _activity_payload(transaction, row)
    tool_name = (
        None if payload is None else _payload_text(payload, _PAYLOAD_FIELD_TOOL_NAME)
    )
    display_name = (
        None if tool_name is None else _tool_display_name(transaction, row, tool_name)
    )
    title = "等待工具完成" if display_name is None else f"等待工具完成：{display_name}"
    return HostActivityView(
        kind=HostActivityKind.TOOL_AWAITING,
        status=HostActivityStatus.WAITING,
        title=title,
        summary="外部工具仍在执行",
        severity=HostActivitySeverity.INFO,
        tool_name=tool_name,
        tool_display_name=display_name,
        counts=None,
    )


def _context_compaction_activity(row: EventLogRow) -> HostActivityView | None:
    """投影 context compaction activity。

    :param row: context compaction EventLog row。
    :returns: compact activity。
    :raises: 无主动抛出。
    """

    payload = _activity_payload_without_descriptor(row)
    if row.event_type == _EVENT_TYPE_CONTEXT_COMPACTION_REQUESTED:
        status = HostActivityStatus.STARTED
        severity = HostActivitySeverity.INFO
        title = "上下文压缩开始"
    elif row.event_type == _EVENT_TYPE_CONTEXT_COMPACTED:
        status = HostActivityStatus.COMPLETED
        severity = HostActivitySeverity.INFO
        title = "上下文压缩完成"
    elif row.event_type == _EVENT_TYPE_CONTEXT_COMPACTION_FAILED:
        status = HostActivityStatus.FAILED
        severity = HostActivitySeverity.ERROR
        title = "上下文压缩失败"
    elif row.event_type == _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED:
        status = HostActivityStatus.FAILED
        severity = HostActivitySeverity.WARNING
        title = "上下文压缩未接受"
    else:
        return None
    summary = _bounded_summary(_payload_text(payload, _PAYLOAD_FIELD_FAILURE_REASON))
    return HostActivityView(
        kind=HostActivityKind.CONTEXT_COMPACTION,
        status=status,
        title=title,
        summary=summary,
        severity=severity,
        tool_name=None,
        tool_display_name=None,
        counts=None,
    )


def _provider_protocol_error_activity(row: EventLogRow) -> HostActivityView | None:
    """投影 provider protocol diagnostic activity。

    :param row: PROVIDER_PROTOCOL_ERROR EventLog row。
    :returns: provider diagnostic activity。
    :raises: 无主动抛出。
    """

    payload = _activity_payload_without_descriptor(row)
    failure_metadata = payload.get(_PAYLOAD_FIELD_FAILURE_METADATA)
    provider_error_code = None
    if isinstance(failure_metadata, Mapping):
        provider_error_code = _payload_text(
            cast(Mapping[str, JsonValue], failure_metadata),
            _PAYLOAD_FIELD_PROVIDER_ERROR_CODE,
        )
    error_code = (
        _payload_text(payload, _PAYLOAD_FIELD_ERROR_CODE) or provider_error_code
    )
    message = _bounded_summary(_payload_text(payload, _PAYLOAD_FIELD_MESSAGE))
    summary = _join_summary_parts(error_code, message)
    return HostActivityView(
        kind=HostActivityKind.PROVIDER_DIAGNOSTIC,
        status=HostActivityStatus.FAILED,
        title="模型协议诊断",
        summary=summary,
        severity=HostActivitySeverity.WARNING,
        tool_name=None,
        tool_display_name=None,
        counts=None,
    )


def _tool_outcome_activity_state(
    outcome_kind: str,
) -> tuple[HostActivityStatus, HostActivitySeverity]:
    """把工具 outcome 文本映射为 activity 状态。

    :param outcome_kind: Host preview payload 中的 outcome kind。
    :returns: activity status 与 severity。
    :raises: 无主动抛出。
    """

    if outcome_kind == "completed":
        return HostActivityStatus.COMPLETED, HostActivitySeverity.INFO
    if outcome_kind == "cancelled":
        return HostActivityStatus.CANCELLED, HostActivitySeverity.WARNING
    return HostActivityStatus.FAILED, HostActivitySeverity.ERROR


def _activity_payload(
    transaction: HostTransaction, row: EventLogRow
) -> Mapping[str, JsonValue] | None:
    """读取 activity 所需 payload，允许跟随 descriptor。

    :param transaction: 当前 Host transaction。
    :param row: EventLog durable row。
    :returns: payload object；无法读取时返回 ``None``。
    :raises: 无主动抛出。
    """

    try:
        return event_payload_object(
            transaction, row, payload_label=f"{row.event_type} activity"
        )
    except HostDurableError:
        return None


def _activity_payload_without_descriptor(row: EventLogRow) -> Mapping[str, JsonValue]:
    """读取 inline activity payload，失败时返回空 mapping。

    :param row: EventLog durable row。
    :returns: payload object；无法读取时返回空 mapping。
    :raises: 无主动抛出。
    """

    try:
        return _payload_object(row)
    except HostDurableError:
        return {}


def _tool_display_name(
    transaction: HostTransaction, row: EventLogRow, tool_name: str
) -> str:
    """从 Host-owned effective tool snapshot 读取工具展示名。

    :param transaction: 当前 Host transaction。
    :param row: 当前工具 activity row。
    :param tool_name: 稳定工具名。
    :returns: 展示名；snapshot 缺失时 fallback 稳定工具名。
    :raises: 无主动抛出。
    """

    if row.run_id is None:
        return tool_name
    run = read_run_by_id(transaction, row.run_id)
    if run is None:
        return tool_name
    input_event = _EVENT_LOG_STORE.read_event_by_id(transaction, run.input_event_id)
    if input_event is None:
        return tool_name
    try:
        input_payload = event_payload_object(
            transaction, input_event, payload_label="USER_INPUT_ACCEPTED"
        )
    except HostDurableError:
        return tool_name
    tool_set = input_payload.get(_PAYLOAD_FIELD_EFFECTIVE_TOOL_SET)
    if not isinstance(tool_set, Mapping):
        return tool_name
    display_names = cast(Mapping[str, JsonValue], tool_set).get(
        _PAYLOAD_FIELD_EFFECTIVE_TOOL_DISPLAY_NAMES
    )
    if not isinstance(display_names, Mapping):
        return tool_name
    display_name = cast(Mapping[str, JsonValue], display_names).get(tool_name)
    if isinstance(display_name, str) and display_name.strip() != "":
        return display_name
    return tool_name


def _payload_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """从 payload 读取可展示文本字段。

    :param payload: payload JSON object。
    :param field_name: 字段名。
    :returns: 非空文本；缺失或非法时返回 ``None``。
    :raises: 无主动抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _payload_non_negative_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """从 payload 读取非负整数字段。

    :param payload: payload JSON object。
    :param field_name: 字段名。
    :returns: 非负整数；缺失或非法时返回 ``None``。
    :raises: 无主动抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    return value


def _bounded_summary(value: str | None) -> str | None:
    """生成有界 activity summary。

    :param value: 原始摘要文本。
    :returns: 有界摘要；无可展示文本时返回 ``None``。
    :raises: 无主动抛出。
    """

    if value is None:
        return None
    normalized = " ".join(value.split())
    if normalized == "":
        return None
    if len(normalized) <= _ACTIVITY_SUMMARY_MAX_CHARS:
        return normalized
    return normalized[: _ACTIVITY_SUMMARY_MAX_CHARS - 1] + "…"


def _join_summary_parts(first: str | None, second: str | None) -> str | None:
    """拼接两个可选 activity summary 片段。

    :param first: 第一个片段。
    :param second: 第二个片段。
    :returns: 有界摘要；两个片段都缺失时返回 ``None``。
    :raises: 无主动抛出。
    """

    parts = tuple(part for part in (first, second) if part is not None)
    if len(parts) == 0:
        return None
    return _bounded_summary("；".join(parts))


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


__all__ = ["get_run", "get_session", "list_sessions"]
