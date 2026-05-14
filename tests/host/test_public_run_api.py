"""Host public Run / follow-up / cancel facade 测试。"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dayu.host import (
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
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
    cancel_run,
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
        host_handle_id="host-run-api",
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


def _context(
    actor: str = "analyst", request_id: str = "trace-run"
) -> HostCallContext:
    """构造测试用 Host call context。

    :param actor: 调用主体。
    :param request_id: trace request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor=actor,
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="public_run_api",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase4",
            correlation_id="corr-run",
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


def _start_request(
    session_id: str,
    client_request_id: str,
    *,
    queue_policy: str = "queue",
    actor: str = "analyst",
) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param queue_policy: admission queue policy。
    :param actor: 调用主体。
    :returns: start run 请求。
    """

    return StartRunRequest(
        context=_context(actor=actor),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"input-{client_request_id}"),
        execution_target="public-target",
        queue_policy=queue_policy,
    )


def _followup_request(
    session_id: str,
    client_request_id: str,
    *,
    behavior: FollowupBehavior = FollowupBehavior.QUEUE,
    target_run_id: str | None = None,
) -> SubmitFollowupRequest:
    """构造 submit_followup 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param behavior: follow-up 行为。
    :param target_run_id: steer 目标 Run id。
    :returns: submit follow-up 请求。
    """

    return SubmitFollowupRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"follow-{client_request_id}"),
        behavior=behavior,
        target_run_id=target_run_id,
    )


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: cancel run 请求。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop",
        mode=CancelMode.GRACEFUL,
    )


def _session_id(host: HostCommandHandle) -> str:
    """创建或读取测试 Session id。

    :param host: Host command handle。
    :returns: Session id。
    """

    return ensure_session(
        host,
        EnsureSessionRequest(scope="workspace", slot_key="slot-a", metadata=()),
    ).session_id


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


def test_start_run_direct_running_and_attach_active(tmp_path: Path) -> None:
    """public start_run 支持 direct running 与 attach_active。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        running = start_run(host, _start_request(session_id, "start-1"))
        before_attach = _event_count(options.db_path)
        attached = start_run(
            host,
            _start_request(
                session_id,
                "attach-1",
                queue_policy="attach_active",
            ),
        )

        assert running.status == RunStatus.RUNNING
        assert running.current_attempt_id is not None
        assert attached.run_id == running.run_id
        assert attached.status == RunStatus.RUNNING
        assert _event_count(options.db_path) == before_attach
    finally:
        host.close()


def test_start_run_idempotent_replay_returns_latest_snapshot_without_events(
    tmp_path: Path,
) -> None:
    """start_run 幂等重放返回当前 Run snapshot，且不追加重复事实。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        request = _start_request(session_id, "start-1")
        first = start_run(host, request)
        cancelled = cancel_run(host, first.run_id, _cancel_request("cancel-1"))
        before_replay = _event_count(options.db_path)
        replay = start_run(host, request)

        assert cancelled.status == RunStatus.CANCELLED
        assert replay.run_id == first.run_id
        assert replay.status == RunStatus.CANCELLED
        assert _event_count(options.db_path) == before_replay
    finally:
        host.close()


def test_start_run_same_key_different_digest_conflicts(tmp_path: Path) -> None:
    """start_run 同幂等 key 携带不同 semantic digest 时冲突。"""

    host = _open_handle(tmp_path)
    try:
        session_id = _session_id(host)
        start_run(host, _start_request(session_id, "start-1"))

        with pytest.raises(HostApiError) as exc_info:
            start_run(
                host,
                _start_request(session_id, "start-1", actor="different"),
            )
        assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT
    finally:
        host.close()


def test_submit_followup_queue_active_and_no_active(tmp_path: Path) -> None:
    """submit_followup(queue) 在 active 存在时排队，无 active 时直接 running。"""

    host = _open_handle(tmp_path)
    try:
        session_id = _session_id(host)
        start_run(host, _start_request(session_id, "start-1"))

        queued = submit_followup(
            host, session_id, _followup_request(session_id, "follow-queued")
        )
        assert queued.accepted_run_status == RunStatus.QUEUED
        assert queued.queued_run_id == queued.accepted_run_id

        other_session_id = ensure_session(
            host,
            EnsureSessionRequest(
                scope="workspace", slot_key="slot-b", metadata=()
            ),
        ).session_id
        direct = submit_followup(
            host,
            other_session_id,
            _followup_request(other_session_id, "follow-direct"),
        )
        assert direct.accepted_run_status == RunStatus.RUNNING
        assert direct.queued_run_id is None
    finally:
        host.close()


def test_submit_followup_steer_is_unsupported_without_event_append(
    tmp_path: Path,
) -> None:
    """submit_followup(steer) 返回 unsupported，且不追加 EventLog。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        active = start_run(host, _start_request(session_id, "start-1"))
        before_steer = _event_count(options.db_path)

        with pytest.raises(HostApiError) as exc_info:
            submit_followup(
                host,
                session_id,
                _followup_request(
                    session_id,
                    "steer-1",
                    behavior=FollowupBehavior.STEER,
                    target_run_id=active.run_id,
                ),
            )
        assert exc_info.value.code == HostApiErrorCode.UNSUPPORTED_OPERATION
        assert exc_info.value.retryable is False
        assert _event_count(options.db_path) == before_steer
    finally:
        host.close()


def test_cancel_run_queued_and_predispatch_starting(tmp_path: Path) -> None:
    """public cancel_run 支持 queued 与 pre-dispatch STARTING。"""

    host = _open_handle(tmp_path)
    try:
        session_id = _session_id(host)
        active = start_run(host, _start_request(session_id, "start-1"))
        queued = start_run(
            host, _start_request(session_id, "start-queued", queue_policy="queue")
        )

        cancelled_queued = cancel_run(
            host, queued.run_id, _cancel_request("cancel-queued")
        )
        cancelled_active = cancel_run(
            host, active.run_id, _cancel_request("cancel-active")
        )

        assert cancelled_queued.status == RunStatus.CANCELLED
        assert cancelled_active.status == RunStatus.CANCELLED
    finally:
        host.close()


def test_public_cancel_and_promotion_race_preserves_run_invariants(
    tmp_path: Path,
) -> None:
    """public queued cancel 与 active cancel/promotion 竞争时保持 first-committer-wins。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        active = start_run(host, _start_request(session_id, "start-1"))
        queued = start_run(
            host, _start_request(session_id, "start-queued", queue_policy="queue")
        )
    finally:
        host.close()

    def _cancel_active() -> RunStatus:
        """在线程内取消 active Run。

        :returns: cancel 后状态。
        """

        worker = create_host_command_handle(options)
        try:
            return cancel_run(
                worker, active.run_id, _cancel_request("cancel-active")
            ).status
        finally:
            worker.close()

    def _cancel_queued() -> RunStatus:
        """在线程内取消 queued Run。

        :returns: cancel 后状态。
        """

        worker = create_host_command_handle(options)
        try:
            return cancel_run(
                worker, queued.run_id, _cancel_request("cancel-queued")
            ).status
        finally:
            worker.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = tuple(
            future.result()
            for future in (
                executor.submit(_cancel_active),
                executor.submit(_cancel_queued),
            )
        )

    latest_active_status = _run_status(options.db_path, active.run_id)
    latest_queued_status = _run_status(options.db_path, queued.run_id)
    assert statuses == (RunStatus.CANCELLED, RunStatus.CANCELLED)
    assert latest_active_status == RunStatus.CANCELLED
    assert latest_queued_status == RunStatus.CANCELLED
