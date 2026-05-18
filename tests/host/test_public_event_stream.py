"""Host public EventLog stream facade 测试。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.host import (
    AuthorizationClaim,
    EnsureSessionRequest,
    HOST_EVENT_STREAM_DEFAULT_LIMIT,
    HOST_EVENT_STREAM_MAX_LIMIT,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostEventClass,
    HostInput,
    HostStreamCursor,
    OperationContext,
    ensure_session,
)
from dayu.host.api import HostCommandHandleOptions, HostEventView, StartRunRequest
from dayu.host.command import HostCommandHandle, create_host_command_handle, start_run
from dayu.host.read_api import stream_run_events
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import HostTransaction
from dayu.host.read_api import _event_view_from_row

_PROJECTION_CONSUMER_ID = "phase8-stream-boundary"
_PROJECTION_TEST_NOW = "2026-05-16T00:00:00Z"


def _options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-event-stream-api",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _open_handle(tmp_path: Path) -> HostCommandHandle:
    """创建测试用 Host command handle。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle。
    """

    return create_host_command_handle(_options(tmp_path))


def test_event_view_mapping_covers_current_event_classes() -> None:
    """EventLog class 到 public event class 的映射覆盖当前枚举。"""

    for event_class in EventClass:
        view = _event_view_from_row(_event_log_row(event_class))
        assert view.event_class == HostEventClass(event_class.value)


def test_event_view_mapping_rejects_unknown_event_class() -> None:
    """EventLog class mapping 对未知 durable enum fail closed。"""

    with pytest.raises(HostDurableError):
        _event_view_from_row(
            _event_log_row(cast(EventClass, "future_event_class"))
        )


def test_stream_run_events_unknown_event_class_returns_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """public stream facade 把 EventLog class mapping 失败转为 HostApiError。"""

    host = _open_handle(tmp_path)
    try:
        session_id = _session_id(host, "slot-unknown-class")
        run = start_run(host, _start_request(session_id, "start-run"))

        monkeypatch.setattr(
            "dayu.host.read_api.read_events_after",
            _UnknownEventClassReader(run_id=run.run_id, session_id=run.session_id),
        )

        with pytest.raises(HostApiError) as exc_info:
            stream_run_events(
                host, run.run_id, HostStreamCursor(event_sequence=0), limit=1
            )

        assert exc_info.value.code == HostApiErrorCode.INTERNAL_ERROR
        assert exc_info.value.retryable is False
    finally:
        host.close()


def _context(request_id: str = "trace-stream") -> HostCallContext:
    """构造测试用 Host call context。

    :param request_id: trace request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="public_event_stream",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase4",
            correlation_id="corr-stream",
        ),
    )


def _event_log_row(
    event_class: EventClass,
    *,
    run_id: str | None = "run-1",
    session_id: str = "session-1",
) -> EventLogRow:
    """构造 event view mapping 测试用 EventLog row。

    :param event_class: durable EventLog class。
    :param run_id: 可选 Run id。
    :param session_id: Session id。
    :returns: EventLog row。
    """

    return EventLogRow(
        event_sequence=1,
        event_id="event-1",
        event_body_digest="digest",
        event_class=event_class,
        session_id=session_id,
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        event_type="TYPE_A",
        occurred_at="2026-05-16T00:00:00.000000Z",
        actor=None,
        source=None,
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json="{}",
        payload_ref=None,
        payload_digest=None,
        appended_at="2026-05-16T00:00:00.000000Z",
    )


@dataclass(frozen=True, slots=True)
class _UnknownEventClassReader:
    """stream_run_events monkeypatch 用 EventLog reader。"""

    run_id: str
    session_id: str

    def __call__(
        self, transaction: HostTransaction, cursor: int, *, limit: int
    ) -> tuple[EventLogRow, ...]:
        """返回带未知 event_class 的 EventLog row。

        :param transaction: Host transaction。
        :param cursor: 调用方 cursor。
        :param limit: 调用方 scan limit。
        :returns: EventLog row 元组。
        """

        return (
            _event_log_row(
                cast(EventClass, "future_event_class"),
                run_id=self.run_id,
                session_id=self.session_id,
            ),
        )


def _input(display_text: str) -> HostInput:
    """构造 Host 输入。

    :param display_text: 展示文本。
    :returns: Host input。
    """

    return HostInput(
        display_text=display_text,
        payload_ref=None,
        payload_digest=None,
    )


def _session_id(host: HostCommandHandle, slot_key: str) -> str:
    """创建或读取测试 Session id。

    :param host: Host command handle。
    :param slot_key: slot key。
    :returns: Session id。
    """

    return ensure_session(
        host,
        EnsureSessionRequest(scope="workspace", slot_key=slot_key, metadata=()),
    ).session_id


def _start_request(session_id: str, client_request_id: str) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :returns: start run 请求。
    """

    return StartRunRequest(
        context=_context(request_id=f"trace-{client_request_id}"),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"input-{client_request_id}"),
        execution_target="public-target",
        queue_policy="queue",
    )


def _max_event_sequence(db_path: Path) -> int:
    """读取 EventLog 当前最大全局 event sequence。

    :param db_path: SQLite DB 路径。
    :returns: 最大 event sequence；无 row 时返回零。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(event_sequence), 0) FROM event_log"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _max_scanned_event_sequence(
    db_path: Path, cursor: HostStreamCursor, limit: int
) -> int:
    """按 EventLog scan-window contract 读取本次应推进到的 cursor。

    :param db_path: SQLite DB 路径。
    :param cursor: 输入 Host stream cursor。
    :param limit: 最大扫描 row 数。
    :returns: 扫描窗口内最后一个 event sequence；无 row 时返回输入 cursor。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT event_sequence
            FROM event_log
            WHERE event_sequence > ?
            ORDER BY event_sequence ASC
            LIMIT 1 OFFSET ?
            """,
            (cursor.event_sequence, limit - 1),
        ).fetchone()
        if row is not None:
            return int(row[0])
        row = connection.execute(
            """
            SELECT COALESCE(MAX(event_sequence), ?)
            FROM event_log
            WHERE event_sequence > ?
            """,
            (cursor.event_sequence, cursor.event_sequence),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _event_id_for_sequence(db_path: Path, event_sequence: int) -> str:
    """读取指定 EventLog sequence 对应的 event id。

    :param db_path: SQLite DB 路径。
    :param event_sequence: 目标全局 event sequence。
    :returns: EventLog event id。
    :raises AssertionError: 指定 sequence 不存在时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"""
            SELECT event_id
            FROM {TABLE_EVENT_LOG}
            WHERE event_sequence = ?
            """,
            (event_sequence,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _delete_minimal_read_model_rows(db_path: Path) -> None:
    """删除 minimal read model rows，模拟 projection 缺失。

    :param db_path: SQLite DB 路径。
    :returns: ``None``。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM host_session_timeline_items")
        connection.execute("DELETE FROM host_run_results")
        connection.commit()


def _first_event_sequence(db_path: Path) -> int:
    """读取 EventLog 第一条全局 event sequence。

    :param db_path: SQLite DB 路径。
    :returns: 最小 event sequence。
    :raises AssertionError: EventLog 为空时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT MIN(event_sequence) FROM {TABLE_EVENT_LOG}"
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    return int(row[0])


def _event_views_for_run_after(
    db_path: Path, run_id: str, cursor: HostStreamCursor, limit: int
) -> tuple[tuple[int, str, str], ...]:
    """按 stream scan-window contract 从 EventLog 读取目标 Run 事件视图。

    :param db_path: SQLite DB 路径。
    :param run_id: 目标 Run id。
    :param cursor: 输入 Host stream cursor。
    :param limit: 最大扫描 row 数。
    :returns: 目标 Run 的 ``(event_sequence, event_id, event_type)`` 元组。
    """

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            f"""
            WITH scanned AS (
              SELECT event_sequence, event_id, event_type, run_id
              FROM {TABLE_EVENT_LOG}
              WHERE event_sequence > ?
              ORDER BY event_sequence ASC
              LIMIT ?
            )
            SELECT event_sequence, event_id, event_type
            FROM scanned
            WHERE run_id = ?
            ORDER BY event_sequence ASC
            """,
            (cursor.event_sequence, limit, run_id),
        ).fetchall()
    return tuple((int(row[0]), str(row[1]), str(row[2])) for row in rows)


def _stream_event_views(
    stream_events: tuple[HostEventView, ...],
) -> tuple[tuple[int, str, str], ...]:
    """提取 public stream event 的稳定断言字段。

    :param stream_events: public stream event 元组。
    :returns: ``(event_sequence, event_id, event_type)`` 元组。
    """

    return tuple(
        (event.event_sequence, event.event_id, event.event_type)
        for event in stream_events
    )


def _write_projection_checkpoint(
    db_path: Path, consumer_id: str, event_sequence: int
) -> None:
    """直接写入 projection checkpoint 干扰 row。

    :param db_path: SQLite DB 路径。
    :param consumer_id: projection consumer id。
    :param event_sequence: checkpoint EventLog sequence。
    :returns: ``None``。
    """

    event_id = _event_id_for_sequence(db_path, event_sequence)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"""
            INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              last_success_at,
              updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(consumer_id) DO UPDATE SET
              checkpoint_event_sequence = excluded.checkpoint_event_sequence,
              checkpoint_event_id = excluded.checkpoint_event_id,
              last_success_at = excluded.last_success_at,
              updated_at = excluded.updated_at
            """,
            (
                consumer_id,
                event_sequence,
                event_id,
                _PROJECTION_TEST_NOW,
                _PROJECTION_TEST_NOW,
            ),
        )
        connection.commit()


def _write_projection_failure(
    db_path: Path, consumer_id: str, event_sequence: int
) -> None:
    """直接写入 projection failure 干扰 row。

    :param db_path: SQLite DB 路径。
    :param consumer_id: projection consumer id。
    :param event_sequence: 失败 EventLog sequence。
    :returns: ``None``。
    """

    event_id = _event_id_for_sequence(db_path, event_sequence)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"""
            INSERT INTO {TABLE_HOST_PROJECTION_FAILURES} (
              consumer_id,
              failed_event_sequence,
              failed_event_id,
              failure_count,
              last_error_code,
              last_error_message,
              first_failed_at,
              last_failed_at,
              retry_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(consumer_id) DO UPDATE SET
              failed_event_sequence = excluded.failed_event_sequence,
              failed_event_id = excluded.failed_event_id,
              failure_count = excluded.failure_count,
              last_error_code = excluded.last_error_code,
              last_error_message = excluded.last_error_message,
              last_failed_at = excluded.last_failed_at,
              retry_after = excluded.retry_after
            """,
            (
                consumer_id,
                event_sequence,
                event_id,
                1,
                "ProjectionError",
                "stream boundary test failure",
                _PROJECTION_TEST_NOW,
                _PROJECTION_TEST_NOW,
            ),
        )
        connection.commit()


def _projection_checkpoint_rows(
    db_path: Path,
) -> tuple[tuple[str, int, str | None, str | None, str], ...]:
    """读取 projection checkpoint rows 作为副作用断言基线。

    :param db_path: SQLite DB 路径。
    :returns: checkpoint row 字段元组。
    """

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              last_success_at,
              updated_at
            FROM {TABLE_HOST_PROJECTION_CHECKPOINTS}
            ORDER BY consumer_id ASC
            """
        ).fetchall()
    return tuple(
        (
            str(row[0]),
            int(row[1]),
            None if row[2] is None else str(row[2]),
            None if row[3] is None else str(row[3]),
            str(row[4]),
        )
        for row in rows
    )


def _projection_failure_rows(
    db_path: Path,
) -> tuple[tuple[str, int, str, int, str, str, str, str, str | None], ...]:
    """读取 projection failure rows 作为副作用断言基线。

    :param db_path: SQLite DB 路径。
    :returns: failure row 字段元组。
    """

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
              consumer_id,
              failed_event_sequence,
              failed_event_id,
              failure_count,
              last_error_code,
              last_error_message,
              first_failed_at,
              last_failed_at,
              retry_after
            FROM {TABLE_HOST_PROJECTION_FAILURES}
            ORDER BY consumer_id ASC
            """
        ).fetchall()
    return tuple(
        (
            str(row[0]),
            int(row[1]),
            str(row[2]),
            int(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
            str(row[7]),
            None if row[8] is None else str(row[8]),
        )
        for row in rows
    )


def test_stream_run_events_returns_only_target_run_events(
    tmp_path: Path,
) -> None:
    """stream_run_events 只返回目标 Run 的 EventLog rows。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        target_session_id = _session_id(host, "target")
        other_session_id = _session_id(host, "other")
        target = start_run(host, _start_request(target_session_id, "target-run"))
        other = start_run(host, _start_request(other_session_id, "other-run"))

        stream = stream_run_events(
            host,
            target.run_id,
            HostStreamCursor(event_sequence=0),
            limit=HOST_EVENT_STREAM_MAX_LIMIT,
        )

        assert stream.events != ()
        assert all(event.run_id == target.run_id for event in stream.events)
        assert other.run_id not in tuple(event.run_id for event in stream.events)
        assert stream.next_cursor.event_sequence == _max_event_sequence(
            options.db_path
        )
    finally:
        host.close()


def test_stream_run_events_exposes_event_class_for_preview_rows(
    tmp_path: Path,
) -> None:
    """stream_run_events 必须暴露 EventLog row 的 public event class。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "target")
        target = start_run(host, _start_request(session_id, "target-run"))

        def append_preview(transaction: HostTransaction) -> None:
            """追加同一 Run 的 preview EventLog row。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            EventLogStore().append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-preview-content-delta",
                    event_class=EventClass.PREVIEW,
                    session_id=session_id,
                    run_id=target.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="CONTENT_DELTA",
                    occurred_at=datetime(2026, 5, 16, 1, 2, 3, tzinfo=UTC),
                    actor="engine",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key="preview-content-delta",
                    policy_decision=None,
                    reason=None,
                    payload_json={"text": "delta"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            )

        host._transaction_runner().run_write(append_preview)

        stream = stream_run_events(
            host,
            target.run_id,
            HostStreamCursor(event_sequence=0),
            limit=HOST_EVENT_STREAM_MAX_LIMIT,
        )

        event_classes = tuple(event.event_class for event in stream.events)
        assert HostEventClass.CANONICAL_FACT in event_classes
        assert HostEventClass.PREVIEW in event_classes
        assert stream.events[-1].event_class is HostEventClass.PREVIEW
        assert stream.events[-1].event_type == "CONTENT_DELTA"
    finally:
        host.close()


def test_stream_run_events_ignores_projection_checkpoint_lag(
    tmp_path: Path,
) -> None:
    """projection checkpoint 落后 EventLog 时 stream 仍按 EventLog cursor 补读。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        target_session_id = _session_id(host, "target")
        other_session_id = _session_id(host, "other")
        target = start_run(host, _start_request(target_session_id, "target-run"))
        start_run(host, _start_request(other_session_id, "other-run"))
        cursor = HostStreamCursor(event_sequence=0)
        lagged_checkpoint = _first_event_sequence(options.db_path)
        assert lagged_checkpoint < _max_event_sequence(options.db_path)
        _write_projection_checkpoint(
            options.db_path, _PROJECTION_CONSUMER_ID, lagged_checkpoint
        )

        stream = stream_run_events(
            host,
            target.run_id,
            cursor,
            limit=HOST_EVENT_STREAM_MAX_LIMIT,
        )

        assert _stream_event_views(stream.events) == _event_views_for_run_after(
            options.db_path,
            target.run_id,
            cursor,
            HOST_EVENT_STREAM_MAX_LIMIT,
        )
        assert stream.next_cursor.event_sequence == _max_event_sequence(
            options.db_path
        )
    finally:
        host.close()


def test_stream_run_events_ignores_projection_failure_row(
    tmp_path: Path,
) -> None:
    """projection failure row 存在时 stream 仍返回 EventLog rows 与正确 cursor。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        target_session_id = _session_id(host, "target")
        other_session_id = _session_id(host, "other")
        target = start_run(host, _start_request(target_session_id, "target-run"))
        start_run(host, _start_request(other_session_id, "other-run"))
        cursor = HostStreamCursor(event_sequence=0)
        limit = 3
        _write_projection_failure(
            options.db_path,
            _PROJECTION_CONSUMER_ID,
            _first_event_sequence(options.db_path),
        )

        stream = stream_run_events(host, target.run_id, cursor, limit=limit)

        assert _stream_event_views(stream.events) == _event_views_for_run_after(
            options.db_path,
            target.run_id,
            cursor,
            limit,
        )
        assert stream.next_cursor.event_sequence == _max_scanned_event_sequence(
            options.db_path, cursor, limit
        )
    finally:
        host.close()


def test_stream_run_events_ignores_missing_minimal_read_model(
    tmp_path: Path,
) -> None:
    """minimal read model 缺失时 stream 仍只读取 EventLog truth。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "target")
        target = start_run(host, _start_request(session_id, "target-run"))
        cursor = HostStreamCursor(event_sequence=0)
        _delete_minimal_read_model_rows(options.db_path)

        stream = stream_run_events(
            host,
            target.run_id,
            cursor,
            limit=HOST_EVENT_STREAM_MAX_LIMIT,
        )

        assert _stream_event_views(stream.events) == _event_views_for_run_after(
            options.db_path,
            target.run_id,
            cursor,
            HOST_EVENT_STREAM_MAX_LIMIT,
        )
    finally:
        host.close()


def test_stream_run_events_does_not_write_projection_tables(
    tmp_path: Path,
) -> None:
    """stream_run_events 不推进 checkpoint、不修复 failure、不写 projection 表。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "target")
        target = start_run(host, _start_request(session_id, "target-run"))
        first_sequence = _first_event_sequence(options.db_path)
        _write_projection_checkpoint(
            options.db_path, _PROJECTION_CONSUMER_ID, first_sequence
        )
        _write_projection_failure(
            options.db_path, _PROJECTION_CONSUMER_ID, first_sequence
        )
        checkpoint_rows_before = _projection_checkpoint_rows(options.db_path)
        failure_rows_before = _projection_failure_rows(options.db_path)

        stream = stream_run_events(
            host,
            target.run_id,
            HostStreamCursor(event_sequence=0),
            limit=HOST_EVENT_STREAM_MAX_LIMIT,
        )

        assert stream.events != ()
        assert _projection_checkpoint_rows(options.db_path) == checkpoint_rows_before
        assert _projection_failure_rows(options.db_path) == failure_rows_before
    finally:
        host.close()


def test_stream_run_events_advances_cursor_for_unrelated_scanned_rows(
    tmp_path: Path,
) -> None:
    """扫描窗口只有无关事件时返回空 events 但推进 next_cursor。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        target_session_id = _session_id(host, "target")
        other_session_id = _session_id(host, "other")
        target = start_run(host, _start_request(target_session_id, "target-run"))
        cursor = HostStreamCursor(
            event_sequence=_max_event_sequence(options.db_path)
        )
        start_run(host, _start_request(other_session_id, "other-run"))

        stream = stream_run_events(host, target.run_id, cursor, limit=10)

        assert stream.events == ()
        assert stream.next_cursor.event_sequence == _max_event_sequence(
            options.db_path
        )
        assert stream.next_cursor.event_sequence > cursor.event_sequence
    finally:
        host.close()


def test_stream_run_events_no_scanned_rows_returns_input_cursor(
    tmp_path: Path,
) -> None:
    """没有 EventLog row 被扫描时 next_cursor 等于输入 cursor。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "target")
        target = start_run(host, _start_request(session_id, "target-run"))
        cursor = HostStreamCursor(
            event_sequence=_max_event_sequence(options.db_path)
        )

        stream = stream_run_events(host, target.run_id, cursor, limit=10)

        assert stream.events == ()
        assert stream.next_cursor == cursor
    finally:
        host.close()


def test_stream_run_events_rejects_invalid_limits(tmp_path: Path) -> None:
    """已有 Run 时 stream_run_events 拒绝非法 limit。"""

    host = _open_handle(tmp_path)
    try:
        session_id = _session_id(host, "target")
        target = start_run(host, _start_request(session_id, "target-run"))
        cursor = HostStreamCursor(event_sequence=0)

        with pytest.raises(HostApiError) as zero_exc:
            stream_run_events(host, target.run_id, cursor, limit=0)
        with pytest.raises(HostApiError) as max_exc:
            stream_run_events(
                host,
                target.run_id,
                cursor,
                limit=HOST_EVENT_STREAM_MAX_LIMIT + 1,
            )

        assert zero_exc.value.code == HostApiErrorCode.INVALID_STATE
        assert max_exc.value.code == HostApiErrorCode.INVALID_STATE
    finally:
        host.close()


def test_stream_run_events_missing_run_invalid_limit_returns_not_found(
    tmp_path: Path,
) -> None:
    """缺失 Run 与非法 limit 同时存在时优先返回 NOT_FOUND。"""

    host = _open_handle(tmp_path)
    try:
        cursor = HostStreamCursor(event_sequence=0)

        with pytest.raises(HostApiError) as zero_exc:
            stream_run_events(host, "missing-run", cursor, limit=0)
        with pytest.raises(HostApiError) as negative_exc:
            stream_run_events(host, "missing-run", cursor, limit=-1)
        with pytest.raises(HostApiError) as max_exc:
            stream_run_events(
                host,
                "missing-run",
                cursor,
                limit=HOST_EVENT_STREAM_MAX_LIMIT + 1,
            )

        assert zero_exc.value.code == HostApiErrorCode.NOT_FOUND
        assert negative_exc.value.code == HostApiErrorCode.NOT_FOUND
        assert max_exc.value.code == HostApiErrorCode.NOT_FOUND
    finally:
        host.close()


def test_stream_run_events_default_limit_is_scan_window(
    tmp_path: Path,
) -> None:
    """limit=None 使用 HOST_EVENT_STREAM_DEFAULT_LIMIT 作为扫描窗口。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        target_session_id = _session_id(host, "target")
        target = start_run(host, _start_request(target_session_id, "target-run"))
        cursor = HostStreamCursor(
            event_sequence=_max_event_sequence(options.db_path)
        )
        unrelated_run_count = (HOST_EVENT_STREAM_DEFAULT_LIMIT // 3) + 2
        for index in range(unrelated_run_count):
            session_id = _session_id(host, f"other-{index}")
            start_run(host, _start_request(session_id, f"other-run-{index}"))

        stream = stream_run_events(host, target.run_id, cursor)

        assert stream.events == ()
        assert stream.next_cursor.event_sequence == _max_scanned_event_sequence(
            options.db_path,
            cursor,
            HOST_EVENT_STREAM_DEFAULT_LIMIT,
        )
        assert stream.next_cursor.event_sequence < _max_event_sequence(
            options.db_path
        )
    finally:
        host.close()


def test_stream_run_events_missing_run_returns_not_found(
    tmp_path: Path,
) -> None:
    """stream_run_events 会先校验目标 Run 存在。"""

    host = _open_handle(tmp_path)
    try:
        with pytest.raises(HostApiError) as exc_info:
            stream_run_events(
                host,
                "missing-run",
                HostStreamCursor(event_sequence=0),
                limit=10,
            )

        assert exc_info.value.code == HostApiErrorCode.NOT_FOUND
    finally:
        host.close()
