"""Host public Run / follow-up / cancel facade 测试。"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.host import (
    AuthorizationClaim,
    AttemptStatus,
    CancelMode,
    CancelRunRequest,
    CloseSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    OperationContext,
    PurgeSessionRequest,
    ReplayRunRequest,
    RetryRunRequest,
    RunStatus,
    SubmitFollowupRequest,
    cancel_run,
    close_session,
    ensure_session,
    get_run,
    purge_session,
    replay_run,
    retry_run,
    submit_followup,
)
from dayu.host.api import HostInput
from dayu.host.api import EnsureSessionRequest, HostCommandHandleOptions, StartRunRequest
from dayu.host.command import HostCommandHandle, create_host_command_handle, start_run
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.state import (
    RunRow,
    TERMINAL_RUN_STATUSES,
    deserialize_attempt_status,
    run_snapshot_from_row,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.queue_policy import RunQueuePolicy

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
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _open_handle(tmp_path: Path) -> HostCommandHandle:
    """创建测试用 Host command handle。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle。
    """

    return create_host_command_handle(_options(tmp_path))


def _durable_run_row(status: RunStatus) -> RunRow:
    """构造 RunSnapshot mapping 测试用 durable Run row。

    :param status: durable Run status。
    :returns: Run row。
    """

    return RunRow(
        run_id="run-mapping",
        session_id="session-mapping",
        status=status,
        client_request_id="request-mapping",
        input_event_id="event-input",
        input_event_sequence=1,
        accepted_event_id="event-accepted",
        accepted_event_sequence=2,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        cancel_request_event_id=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target="local",
        queue_policy=RunQueuePolicy.QUEUE,
        created_at="2026-05-16T00:00:00.000000Z",
        updated_at="2026-05-16T00:00:00.000000Z",
        terminal_at=None,
    )


class _UnknownRunStatusReader:
    """get_run monkeypatch 用 Run reader。"""

    def __call__(
        self, transaction: HostTransaction, run_id: str
    ) -> RunRow | None:
        """返回带未知 status 的 durable Run row。

        :param transaction: Host transaction。
        :param run_id: Run id。
        :returns: Run row。
        """

        return _durable_run_row(cast(RunStatus, "future_run_status"))


def test_run_snapshot_mapping_covers_current_run_statuses() -> None:
    """durable Run status 到 public RunSnapshot status 的映射覆盖当前枚举。"""

    for status in RunStatus:
        snapshot = run_snapshot_from_row(_durable_run_row(status))
        assert snapshot.status is status
        if status in TERMINAL_RUN_STATUSES:
            assert snapshot.terminal_result_summary is not None
            assert snapshot.terminal_result_summary.status is status
        else:
            assert snapshot.terminal_result_summary is None


def test_run_snapshot_mapping_rejects_unknown_run_status() -> None:
    """RunSnapshot mapping 对未知 durable Run status fail closed。"""

    with pytest.raises(HostDurableError):
        run_snapshot_from_row(
            _durable_run_row(cast(RunStatus, "future_run_status"))
        )


def test_attempt_status_mapping_covers_current_attempt_statuses() -> None:
    """durable Attempt status 文本映射覆盖当前 AttemptStatus 枚举。"""

    for status in AttemptStatus:
        assert deserialize_attempt_status(status.value) is status


def test_attempt_status_mapping_rejects_unknown_attempt_status() -> None:
    """Attempt status mapping 对未知 durable status fail closed。"""

    with pytest.raises(HostDurableError):
        deserialize_attempt_status("future_attempt_status")


def test_get_run_unknown_durable_status_returns_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """public get_run 把 durable status mapping 失败转为 HostApiError。"""

    host = _open_handle(tmp_path)
    try:
        monkeypatch.setattr(
            "dayu.host.read_api.read_run_by_id", _UnknownRunStatusReader()
        )

        with pytest.raises(HostApiError) as exc_info:
            get_run(host, "run-mapping")

        assert exc_info.value.code == HostApiErrorCode.INTERNAL_ERROR
        assert exc_info.value.retryable is False
    finally:
        host.close()


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
        system_prompt=None,
        user_prompt=f"follow-{client_request_id}",
        tool_names=None,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
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


def _close_request(client_request_id: str) -> CloseSessionRequest:
    """构造 close_session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: close session 请求。
    """

    return CloseSessionRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="public_run_api_close",
    )


def _purge_request(client_request_id: str) -> PurgeSessionRequest:
    """构造 purge_session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: purge session 请求。
    """

    return PurgeSessionRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="public_run_api_purge",
    )


def _retry_request(client_request_id: str) -> RetryRunRequest:
    """构造 retry_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: retry run 请求。
    """

    return RetryRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="public_run_api_retry",
    )


def _replay_request(client_request_id: str) -> ReplayRunRequest:
    """构造 replay_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: replay run 请求。
    """

    return ReplayRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="public_run_api_replay",
        repair_instruction="repair structure",
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


def _idempotency_count(db_path: Path) -> int:
    """统计 idempotency record 数。

    :param db_path: SQLite DB 路径。
    :returns: idempotency record 数。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM idempotency_records"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _delete_minimal_read_model_rows(db_path: Path) -> None:
    """删除 minimal read model rows，模拟 projection 缺失。

    :param db_path: SQLite DB 路径。
    :returns: ``None``。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM host_session_timeline_items")
        connection.execute("DELETE FROM host_run_results")
        connection.commit()


def _known_run_event_cursor(db_path: Path, run_id: str) -> int:
    """按 Run row 已知事件序列计算 public event cursor。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :returns: Run row 上 input/accepted/queued/started/terminal 的最大非空序列。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
              input_event_sequence,
              accepted_event_sequence,
              queued_event_sequence,
              started_event_sequence,
              terminal_event_sequence
            FROM host_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    assert row is not None
    sequences = tuple(int(value) for value in row if value is not None)
    return max(sequences)


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


def test_start_run_accepts_and_attach_active_returns_unstarted_run(
    tmp_path: Path,
) -> None:
    """public attach_active 可附着 ACCEPTED active Run 且不写新事件。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        accepted = start_run(host, _start_request(session_id, "start-1"))
        before_attach = _event_count(options.db_path)

        attached = start_run(
            host,
            _start_request(
                session_id,
                "attach-1",
                queue_policy="attach_active",
            )
        )

        assert accepted.status == RunStatus.ACCEPTED
        assert accepted.current_attempt_id is None
        assert attached.run_id == accepted.run_id
        assert attached.status == RunStatus.ACCEPTED
        assert attached.current_attempt_id is None
        assert _event_count(options.db_path) == before_attach
    finally:
        host.close()


def test_get_run_missing_returns_not_found(tmp_path: Path) -> None:
    """get_run 读取不存在 Run 时返回 NOT_FOUND。"""

    host = _open_handle(tmp_path)
    try:
        with pytest.raises(HostApiError) as exc_info:
            get_run(host, "missing-run")

        assert exc_info.value.code == HostApiErrorCode.NOT_FOUND
        assert exc_info.value.retryable is False
    finally:
        host.close()


def test_get_run_returns_durable_status_and_cursor(
    tmp_path: Path,
) -> None:
    """get_run 返回 accepted、queued、cancelled Run 的 durable truth。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        accepted = start_run(host, _start_request(session_id, "start-accepted"))
        queued = start_run(
            host,
            _start_request(session_id, "start-queued", queue_policy="queue"),
        )
        queued_read = get_run(host, queued.run_id)
        queued_cursor_before_cancel = _known_run_event_cursor(
            options.db_path, queued.run_id
        )
        cancelled = cancel_run(
            host, queued.run_id, _cancel_request("cancel-queued")
        )

        accepted_read = get_run(host, accepted.run_id)
        cancelled_read = get_run(host, cancelled.run_id)

        assert accepted_read.status == RunStatus.ACCEPTED
        assert accepted_read.current_attempt_id is None
        assert accepted_read.event_cursor.event_sequence == _known_run_event_cursor(
            options.db_path, accepted.run_id
        )
        assert queued_read.status == RunStatus.QUEUED
        assert queued_read.current_attempt_id is None
        assert queued_read.event_cursor.event_sequence == queued_cursor_before_cancel
        assert cancelled.terminal_result_summary is not None
        assert cancelled.terminal_result_summary.status == RunStatus.CANCELLED
        assert cancelled.terminal_result_summary.summary_ref is None
        assert cancelled.terminal_result_summary.summary_digest is None
        assert cancelled_read.status == RunStatus.CANCELLED
        assert cancelled_read.current_attempt_id is None
        assert cancelled_read.terminal_result_summary is not None
        assert (
            cancelled_read.terminal_result_summary
            == cancelled.terminal_result_summary
        )
        assert cancelled_read.terminal_result_summary.status == RunStatus.CANCELLED
        assert cancelled_read.terminal_result_summary.summary_ref is None
        assert cancelled_read.terminal_result_summary.summary_digest is None
        assert (
            cancelled_read.event_cursor.event_sequence
            == _known_run_event_cursor(options.db_path, cancelled.run_id)
        )
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
        before_idempotency = _idempotency_count(options.db_path)
        replay = start_run(host, request)

        assert cancelled.status == RunStatus.CANCELLED
        assert cancelled.terminal_result_summary is not None
        assert cancelled.terminal_result_summary.status == RunStatus.CANCELLED
        assert replay.run_id == first.run_id
        assert replay.status == RunStatus.CANCELLED
        assert replay.terminal_result_summary is not None
        assert replay.terminal_result_summary == cancelled.terminal_result_summary
        assert _event_count(options.db_path) == before_replay
        assert _idempotency_count(options.db_path) == before_idempotency
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


def test_submit_followup_queue_requires_opener_baseline(tmp_path: Path) -> None:
    """低层 command handle 无 opener baseline 时 submit_followup fail closed。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        start_run(host, _start_request(session_id, "start-1"))
        before_followup = _event_count(options.db_path)

        with pytest.raises(HostApiError) as exc_info:
            submit_followup(
                host, session_id, _followup_request(session_id, "follow-queued")
            )

        assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
        assert _event_count(options.db_path) == before_followup
    finally:
        host.close()


def test_submit_followup_steer_rejects_unstarted_target_without_event_append(
    tmp_path: Path,
) -> None:
    """submit_followup(steer) 对未启动 target 返回 invalid state 且不追加 EventLog。"""

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
        assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
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


def test_get_run_uses_durable_status_when_minimal_read_model_is_missing(
    tmp_path: Path,
) -> None:
    """minimal RunResult 缺失不改变 public RunSnapshot durable truth。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start-1"))
        before = get_run(host, run.run_id)
        _delete_minimal_read_model_rows(options.db_path)
        after = get_run(host, run.run_id)

        assert after.status == before.status
        assert after.event_cursor == before.event_cursor
        assert after.terminal_result_summary == before.terminal_result_summary
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


def test_retry_replay_reject_non_terminal_and_purge_rejects_open_session(
    tmp_path: Path,
) -> None:
    """retry/replay 对非目标源状态 fail closed；purge 拒绝未关闭 Session。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start-1"))
        before_events = _event_count(options.db_path)
        before_idempotency = _idempotency_count(options.db_path)

        with pytest.raises(HostApiError) as retry_exc:
            retry_run(
                host,
                run.run_id,
                RetryRunRequest(
                    context=_context(),
                    client_request_id="retry-1",
                    reason="retry_test",
                ),
            )
        with pytest.raises(HostApiError) as replay_exc:
            replay_run(
                host,
                run.run_id,
                ReplayRunRequest(
                    context=_context(),
                    client_request_id="replay-1",
                    reason="replay_test",
                    repair_instruction="repair structure",
                ),
            )
        with pytest.raises(HostApiError) as purge_exc:
            purge_session(host, session_id, _purge_request("purge-open"))

        for exc_info in (retry_exc, replay_exc):
            assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
            assert exc_info.value.retryable is False
            assert exc_info.value.detail is None
        assert purge_exc.value.code == HostApiErrorCode.INVALID_STATE
        assert purge_exc.value.retryable is False
        assert purge_exc.value.detail is None
        for exc_info in (retry_exc, replay_exc, purge_exc):
            assert exc_info.value.retryable is False
            assert exc_info.value.detail is None
        assert _event_count(options.db_path) == before_events
        assert _idempotency_count(options.db_path) == before_idempotency
    finally:
        host.close()


def test_purge_session_deletes_run_truth_and_retry_replay_fail_not_found(
    tmp_path: Path,
) -> None:
    """purge 后 Run read/retry/replay 都按缺失事实 fail closed。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start-purge"))
        cancelled = cancel_run(host, run.run_id, _cancel_request("cancel-purge"))
        close_session(host, session_id, _close_request("close-purge"))

        first = purge_session(host, session_id, _purge_request("purge-1"))
        replay = purge_session(host, session_id, _purge_request("purge-1"))

        assert cancelled.status == RunStatus.CANCELLED
        assert first.session_id == session_id
        assert first.purged is True
        assert first.purge_tombstone_ref is not None
        assert first.deleted_counts_digest is not None
        assert replay == first

        with pytest.raises(HostApiError) as get_run_exc:
            get_run(host, run.run_id)
        with pytest.raises(HostApiError) as retry_exc:
            retry_run(host, run.run_id, _retry_request("retry-after-purge"))
        with pytest.raises(HostApiError) as replay_exc:
            replay_run(host, run.run_id, _replay_request("replay-after-purge"))
        with pytest.raises(HostApiError) as different_purge_exc:
            purge_session(host, session_id, _purge_request("purge-2"))

        for exc_info in (get_run_exc, retry_exc, replay_exc):
            assert exc_info.value.code == HostApiErrorCode.NOT_FOUND
            assert exc_info.value.retryable is False
        assert different_purge_exc.value.code == HostApiErrorCode.CONFLICT
        assert different_purge_exc.value.retryable is False
    finally:
        host.close()
