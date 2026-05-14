"""Host public EventLog stream facade 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dayu.host import (
    AuthorizationClaim,
    EnsureSessionRequest,
    HOST_EVENT_STREAM_DEFAULT_LIMIT,
    HOST_EVENT_STREAM_MAX_LIMIT,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandle,
    HostCommandHandleOptions,
    HostInput,
    HostStreamCursor,
    OperationContext,
    StartRunRequest,
    create_host_command_handle,
    ensure_session,
    start_run,
    stream_run_events,
)


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
    )


def _open_handle(tmp_path: Path) -> HostCommandHandle:
    """创建测试用 Host command handle。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle。
    """

    return create_host_command_handle(_options(tmp_path))


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
        for index in range(26):
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
