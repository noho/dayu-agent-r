"""Host public cancel_session_runs facade 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dayu.host import (
    AuthorizationClaim,
    CancelMode,
    CancelSessionRunsRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandle,
    HostCommandHandleOptions,
    HostInput,
    OperationContext,
    RunStatus,
    StartRunRequest,
    SubmitFollowupRequest,
    cancel_session_runs,
    create_host_command_handle,
    ensure_session,
    start_run,
    submit_followup,
)
from dayu.host.api import EnsureSessionRequest


def _options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-cancel-session-api",
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


def _context() -> HostCallContext:
    """构造测试用 Host call context。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="trace-cancel-session",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="public_cancel_session_runs",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase4",
            correlation_id="corr-cancel-session",
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
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"start-{client_request_id}"),
        execution_target="public-target",
        queue_policy="queue",
    )


def _followup_request(
    session_id: str, client_request_id: str
) -> SubmitFollowupRequest:
    """构造 submit_followup(queue) 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :returns: submit follow-up 请求。
    """

    return SubmitFollowupRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"follow-{client_request_id}"),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _cancel_request(client_request_id: str) -> CancelSessionRunsRequest:
    """构造 cancel_session_runs 请求。

    :param client_request_id: 幂等请求 id。
    :returns: cancel session runs 请求。
    """

    return CancelSessionRunsRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop_all",
        mode=CancelMode.GRACEFUL,
    )


def _event_count(db_path: Path) -> int:
    """统计 EventLog row 数。

    :param db_path: SQLite DB 路径。
    :returns: EventLog row 数。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM event_log").fetchone()
    assert row is not None
    return int(row[0])


def _run_status(db_path: Path, run_id: str) -> RunStatus:
    """从 durable Run table 读取当前 Run 状态。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :returns: Run 当前状态。
    :raises AssertionError: Run 不存在时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM host_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    assert row is not None
    return RunStatus(str(row[0]))


def _mark_attempt_running(db_path: Path, attempt_id: str) -> None:
    """把 Attempt 直接改成 RUNNING 以模拟 Phase 5 active worker 状态。

    :param db_path: SQLite DB 路径。
    :param attempt_id: Attempt id。
    :returns: 无返回值。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE host_attempts SET status = ? WHERE attempt_id = ?",
            ("running", attempt_id),
        )


def test_cancel_session_runs_cancels_queued_and_predispatch_subset(
    tmp_path: Path,
) -> None:
    """cancel_session_runs 一次取消同 Session 多个 queued 与 pre-dispatch active。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        other_session_id = _session_id(host, "slot-b")
        active = start_run(host, _start_request(session_id, "start-active"))
        queued_one = start_run(host, _start_request(session_id, "start-q1"))
        queued_two = start_run(host, _start_request(session_id, "start-q2"))
        other = start_run(host, _start_request(other_session_id, "other-active"))

        snapshot = cancel_session_runs(
            host, session_id, _cancel_request("cancel-session")
        )

        assert snapshot.active_run_id is None
        assert snapshot.queued_run_ids == ()
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLED
        assert _run_status(options.db_path, queued_one.run_id) == RunStatus.CANCELLED
        assert _run_status(options.db_path, queued_two.run_id) == RunStatus.CANCELLED
        assert _run_status(options.db_path, other.run_id) == RunStatus.RUNNING
    finally:
        host.close()


def test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run(
    tmp_path: Path,
) -> None:
    """同 key 重放不取消首次操作后新接受的 Run。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        request = _cancel_request("cancel-session")
        first = cancel_session_runs(host, session_id, request)
        new_followup = submit_followup(
            host, session_id, _followup_request(session_id, "new-run")
        )
        replay = cancel_session_runs(host, session_id, request)

        assert first.active_run_id is None
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLED
        assert replay.active_run_id == new_followup.accepted_run_id
        assert (
            _run_status(options.db_path, new_followup.accepted_run_id)
            == RunStatus.RUNNING
        )
    finally:
        host.close()


def test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation(
    tmp_path: Path,
) -> None:
    """存在 unsupported non-terminal 时返回 unsupported 且不部分取消 queued Run。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        assert active.current_attempt_id is not None
        queued = start_run(host, _start_request(session_id, "start-queued"))
        _mark_attempt_running(options.db_path, active.current_attempt_id)
        before_cancel = _event_count(options.db_path)

        with pytest.raises(HostApiError) as exc_info:
            cancel_session_runs(
                host, session_id, _cancel_request("cancel-session")
            )

        assert exc_info.value.code == HostApiErrorCode.UNSUPPORTED_OPERATION
        assert _event_count(options.db_path) == before_cancel
        assert _run_status(options.db_path, active.run_id) == RunStatus.RUNNING
        assert _run_status(options.db_path, queued.run_id) == RunStatus.QUEUED
    finally:
        host.close()


def test_cancel_session_runs_no_supported_run_records_idempotency_without_event(
    tmp_path: Path,
) -> None:
    """没有 supported non-terminal Run 时只记录幂等结果，不追加 cancel fact。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        before_cancel = _event_count(options.db_path)
        request = _cancel_request("cancel-empty")

        first = cancel_session_runs(host, session_id, request)
        second = cancel_session_runs(host, session_id, request)

        assert first == second
        assert first.active_run_id is None
        assert first.queued_run_ids == ()
        assert _event_count(options.db_path) == before_cancel
    finally:
        host.close()
