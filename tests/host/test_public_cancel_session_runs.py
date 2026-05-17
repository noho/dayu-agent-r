"""Host public cancel_session_runs facade 测试。"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
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
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    accept_worker_running_in_transaction,
)
from dayu.host.durable.state import (
    StateMutationStatus,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_LANE_NAME = "llm"


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


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=1.0,
            write_busy_retry_count=8,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.02,
        ),
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


def _event_type_count(db_path: Path, event_type: str) -> int:
    """统计指定 EventLog 类型数量。

    :param db_path: SQLite DB 路径。
    :param event_type: event type。
    :returns: 指定类型 row 数。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
            (event_type,),
        ).fetchone()
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


def _accept_active_worker(
    transaction_runner: HostTransactionRunner, *, run_id: str, attempt_id: str
) -> None:
    """用 durable transition helper 构造 active worker accepted 状态。

    :param transaction_runner: Host transaction runner。
    :param run_id: 目标 Run id。
    :param attempt_id: Attempt id。
    :returns: 无返回值。
    """

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-cancel-session-api",
                pid=os.getpid(),
                process_start_token="public-cancel-session-api",
                boot_id=None,
            ),
        )
        waiting_result = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-cancel-session-api",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        assert waiting_result.status == StateMutationStatus.UPDATED
        dispatching_result = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-cancel-session-api",
            lane_name=_LANE_NAME,
            lane_claim_id=f"claim-{attempt_id}",
            lane_owner_id="owner-cancel-session-api",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        assert dispatching_result.status == StateMutationStatus.UPDATED
        accepted = accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=run_id,
                attempt_id=attempt_id,
                attempt_running_event_id=f"event-attempt-running-{attempt_id}",
                occurred_at=_NOW,
                actor="host.dispatch",
                source="host.dispatch",
                worker_accept_reason="local_worker_accepted",
                local_worker_id=f"local-worker-{attempt_id}",
            ),
        )
        assert accepted.status == StateMutationStatus.UPDATED

    transaction_runner.run_write(_operation)


def _mark_run_status(db_path: Path, run_id: str, status: RunStatus) -> None:
    """直接更新 Run status 以构造 deferred non-terminal 状态。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :param status: 目标 Run status。
    :returns: 无返回值。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE host_runs SET status = ? WHERE run_id = ?",
            (status.value, run_id),
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
    """存在 WAITING non-terminal 时返回 unsupported 且不部分取消 queued Run。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        queued = start_run(host, _start_request(session_id, "start-queued"))
        # 这里仅构造 WAITING 分类测试所需的 deferred 状态，不模拟生产
        # transition；该用例只验证 unsupported 分类不会产生 partial mutation。
        _mark_run_status(options.db_path, active.run_id, RunStatus.WAITING)
        before_cancel = _event_count(options.db_path)

        with pytest.raises(HostApiError) as exc_info:
            cancel_session_runs(
                host, session_id, _cancel_request("cancel-session")
            )

        assert exc_info.value.code == HostApiErrorCode.UNSUPPORTED_OPERATION
        assert _event_count(options.db_path) == before_cancel
        assert _run_status(options.db_path, active.run_id) == RunStatus.WAITING
        assert _run_status(options.db_path, queued.run_id) == RunStatus.QUEUED
    finally:
        host.close()


def test_cancel_session_runs_cancels_queued_and_active_worker(
    tmp_path: Path,
) -> None:
    """cancel_session_runs 支持 queued 与 active worker 子集。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        assert active.current_attempt_id is not None
        queued = start_run(host, _start_request(session_id, "start-queued"))
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            _accept_active_worker(
                store.transaction_runner,
                run_id=active.run_id,
                attempt_id=active.current_attempt_id,
            )

        snapshot = cancel_session_runs(
            host, session_id, _cancel_request("cancel-session-active")
        )

        assert snapshot.active_run_id == active.run_id
        assert snapshot.queued_run_ids == ()
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLING
        assert _run_status(options.db_path, queued.run_id) == RunStatus.CANCELLED
        assert _event_type_count(options.db_path, "RUN_CANCELLING") == 1
    finally:
        host.close()


def test_cancel_session_runs_active_replay_does_not_append_facts(
    tmp_path: Path,
) -> None:
    """active session cancel replay 不重复追加 CANCEL_REQUESTED / RUN_CANCELLING。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        assert active.current_attempt_id is not None
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            _accept_active_worker(
                store.transaction_runner,
                run_id=active.run_id,
                attempt_id=active.current_attempt_id,
            )
        request = _cancel_request("cancel-session-active")

        first = cancel_session_runs(host, session_id, request)
        after_first_events = _event_count(options.db_path)
        replay = cancel_session_runs(host, session_id, request)

        assert first == replay
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLING
        assert _event_count(options.db_path) == after_first_events
        assert _event_type_count(options.db_path, "CANCEL_REQUESTED") == 1
        assert _event_type_count(options.db_path, "RUN_CANCELLING") == 1
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
