"""Host public cancel_session_runs facade 测试。"""

from __future__ import annotations

import os
import sqlite3
from functools import partial
from datetime import UTC, datetime
from pathlib import Path

from dayu.host import (
    AttemptStatus,
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    HostCallContext,
    OperationContext,
    RunStatus,
    cancel_run,
    cancel_session_runs,
    ensure_session,
)
from dayu.host.api import HostInput
from dayu.host.api import EnsureSessionRequest, HostCommandHandleOptions, StartRunRequest
from dayu.host.command import HostCommandHandle, start_run
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
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    StartGovernedRunInput,
    accept_worker_running_in_transaction,
    start_governed_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.state import (
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.memory import default_memory_projection_policy
from tests.host.execution_handle_support import (
    create_execution_command_handle,
    deterministic_ordinary_run_baseline,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_LANE_NAME = "llm"
_EVENT_COUNT_READ_LIMIT = 1000
_EVENT_TYPE_CANCEL_REQUESTED = "CANCEL_REQUESTED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
_create_execution_handle = partial(
    create_execution_command_handle,
    ordinary_run_baseline=deterministic_ordinary_run_baseline(
        "public-cancel-session-runs"
    ),
    memory_projection_policy=default_memory_projection_policy(),
    tooling_options=None,
    context_budget_policy=None,
    enable_truncation_manager=False,
)


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
        context_window_size=8192,
        reserved_output_tokens=1024,
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


def _cancel_run_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: cancel run 请求。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop_one",
        mode=CancelMode.GRACEFUL,
    )


def _event_count(host: HostCommandHandle) -> int:
    """统计当前测试 command handle 可见的 EventLog row 数。

    :param host: Host command handle。
    :returns: EventLog row 数。
    """

    return host._transaction_runner().run_read(
        lambda transaction: len(
            EventLogStore().read_events_after(
                transaction, 0, limit=_EVENT_COUNT_READ_LIMIT
            )
        )
    )


def _event_types_for_run(db_path: Path, run_id: str) -> tuple[str, ...]:
    """读取目标 Run 的 canonical event type 列表。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :returns: 该 Run 的 event type 元组。
    """

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT event_type
            FROM {TABLE_EVENT_LOG}
            WHERE run_id = ?
            ORDER BY event_sequence
            """,
            (run_id,),
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


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


def _attempt_status(db_path: Path, attempt_id: str) -> AttemptStatus:
    """从 durable Attempt table 读取当前 Attempt 状态。

    :param db_path: SQLite DB 路径。
    :param attempt_id: Attempt id。
    :returns: Attempt 当前状态。
    :raises AssertionError: Attempt 不存在时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM host_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
    assert row is not None
    return AttemptStatus(str(row[0]))


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


def _start_governed_run(
    transaction_runner: HostTransactionRunner,
    *,
    run_id: str,
    expected_status: RunStatus,
    id_suffix: str,
) -> str:
    """把已接受的 Run 启动为 STARTING Attempt 并返回 Attempt id。

    :param transaction_runner: Host transaction runner。
    :param run_id: 目标 Run id。
    :param expected_status: Run 启动前期望状态。
    :param id_suffix: 测试生成 id 后缀。
    :returns: 新建 Attempt id。
    :raises AssertionError: transition 未更新时抛出。
    """

    attempt_id = f"attempt-{id_suffix}"

    def _operation(transaction: HostTransaction) -> None:
        """执行 governed start transition。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        started = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            StartGovernedRunInput(
                run_id=run_id,
                expected_status=expected_status,
                run_started_event_id=f"event-run-started-{id_suffix}",
                attempt_started_event_id=f"event-attempt-started-{id_suffix}",
                attempt_id=attempt_id,
                execution_id=f"execution-{id_suffix}",
                dispatch_record_id=f"dispatch-{id_suffix}",
                occurred_at=_NOW,
                actor="host.dispatch",
                source="pytest",
                start_reason=(
                    RunStartReason.INITIAL
                    if expected_status is RunStatus.ACCEPTED
                    else RunStartReason.QUEUE_PROMOTION
                ),
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
            ),
        )
        assert started.status == StateMutationStatus.UPDATED

    transaction_runner.run_write(_operation)
    return attempt_id


def _mark_run_status(db_path: Path, run_id: str, status: RunStatus) -> None:
    """直接更新 Run status 以构造 deferred non-terminal 状态。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :param status: 目标 Run status。
    :returns: 无返回值。
    """

    with sqlite3.connect(db_path) as connection:
        if status in {
            RunStatus.RUNNING,
            RunStatus.WAITING,
            RunStatus.CANCELLING,
            RunStatus.RECOVERING,
        }:
            event_id = f"event-direct-started-{run_id}-{status.value}"
            connection.execute(
                f"""
                INSERT INTO {TABLE_EVENT_LOG} (
                  event_id,
                  event_body_digest,
                  event_class,
                  session_id,
                  run_id,
                  attempt_id,
                  execution_id,
                  event_type,
                  occurred_at,
                  actor,
                  source,
                  client_request_id,
                  idempotency_key,
                  policy_decision_json,
                  reason_json,
                  payload_json,
                  payload_ref,
                  payload_digest,
                  appended_at
                )
                SELECT
                  ?,
                  ?,
                  'canonical_fact',
                  session_id,
                  run_id,
                  NULL,
                  NULL,
                  'RUN_STARTED',
                  ?,
                  'pytest',
                  'pytest',
                  ?,
                  ?,
                  NULL,
                  NULL,
                  '{{}}',
                  NULL,
                  NULL,
                  ?
                FROM host_runs
                WHERE run_id = ?
                """,
                (
                    event_id,
                    "f" * 64,
                    _NOW.isoformat().replace("+00:00", "Z"),
                    f"client-direct-started-{run_id}-{status.value}",
                    f"idem-direct-started-{run_id}-{status.value}",
                    _NOW.isoformat().replace("+00:00", "Z"),
                    run_id,
                ),
            )
            row = connection.execute(
                f"SELECT event_sequence FROM {TABLE_EVENT_LOG} WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            assert row is not None
            connection.execute(
                """
                UPDATE host_runs
                SET status = ?,
                    started_event_id = COALESCE(started_event_id, ?),
                    started_event_sequence = COALESCE(started_event_sequence, ?)
                WHERE run_id = ?
                """,
                (status.value, event_id, int(row[0]), run_id),
            )
            return
        connection.execute(
            "UPDATE host_runs SET status = ? WHERE run_id = ?",
            (status.value, run_id),
        )


def test_cancel_session_runs_cancels_queued_and_predispatch_subset(
    tmp_path: Path,
) -> None:
    """cancel_session_runs 一次取消同 Session 多个 queued 与 pre-dispatch active。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
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
        assert _run_status(options.db_path, other.run_id) == RunStatus.ACCEPTED
    finally:
        host.close()


def test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run(
    tmp_path: Path,
) -> None:
    """同 key 重放不取消首次操作后新接受的 Run。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        request = _cancel_request("cancel-session")
        first = cancel_session_runs(host, session_id, request)
        new_run = start_run(host, _start_request(session_id, "new-run"))
        replay = cancel_session_runs(host, session_id, request)

        assert first.active_run_id is None
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLED
        assert replay.active_run_id == new_run.run_id
        assert _run_status(options.db_path, new_run.run_id) == RunStatus.ACCEPTED
    finally:
        host.close()


def test_cancel_run_recovering_appends_no_attempt_terminal(
    tmp_path: Path,
) -> None:
    """cancel_run 取消 RECOVERING Run 时不追加 Attempt terminal fact。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        run = start_run(host, _start_request(session_id, "start-recovering"))
        attempt_id = "attempt-not-created"
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            attempt_id = _start_governed_run(
                store.transaction_runner,
                run_id=run.run_id,
                expected_status=RunStatus.ACCEPTED,
                id_suffix="recovering-single",
            )
        _mark_run_status(options.db_path, run.run_id, RunStatus.RECOVERING)

        snapshot = cancel_run(
            host, run.run_id, _cancel_run_request("cancel-recovering")
        )
        event_types = _event_types_for_run(options.db_path, run.run_id)

        assert snapshot.status == RunStatus.CANCELLED
        assert _run_status(options.db_path, run.run_id) == RunStatus.CANCELLED
        assert _attempt_status(options.db_path, attempt_id) == AttemptStatus.STARTING
        assert event_types[-2:] == (
            _EVENT_TYPE_CANCEL_REQUESTED,
            _EVENT_TYPE_RUN_CANCELLED,
        )
        assert _EVENT_TYPE_ATTEMPT_CANCELLED not in event_types
    finally:
        host.close()


def test_cancel_run_recovering_replay_is_idempotent_per_run_id(
    tmp_path: Path,
) -> None:
    """cancel_run 取消 RECOVERING Run 时按 run_id 隔离幂等重放。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        peer_session_id = _session_id(host, "slot-b")
        recovering = start_run(
            host, _start_request(session_id, "start-recovering-idempotent")
        )
        peer_recovering = start_run(
            host, _start_request(peer_session_id, "start-recovering-peer")
        )
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            _start_governed_run(
                store.transaction_runner,
                run_id=recovering.run_id,
                expected_status=RunStatus.ACCEPTED,
                id_suffix="recovering-idempotent",
            )
            _start_governed_run(
                store.transaction_runner,
                run_id=peer_recovering.run_id,
                expected_status=RunStatus.ACCEPTED,
                id_suffix="recovering-peer",
            )
        _mark_run_status(options.db_path, recovering.run_id, RunStatus.RECOVERING)
        _mark_run_status(options.db_path, peer_recovering.run_id, RunStatus.RECOVERING)
        request = _cancel_run_request("cancel-recovering-idempotent")

        first = cancel_run(host, recovering.run_id, request)
        after_first_events = _event_types_for_run(options.db_path, recovering.run_id)
        replay = cancel_run(host, recovering.run_id, request)
        after_replay_events = _event_types_for_run(options.db_path, recovering.run_id)
        peer = cancel_run(host, peer_recovering.run_id, request)
        peer_events = _event_types_for_run(options.db_path, peer_recovering.run_id)

        assert first == replay
        assert first.run_id == recovering.run_id
        assert replay.run_id == recovering.run_id
        assert peer.run_id == peer_recovering.run_id
        assert after_replay_events == after_first_events
        assert after_replay_events.count(_EVENT_TYPE_CANCEL_REQUESTED) == 1
        assert after_replay_events.count(_EVENT_TYPE_RUN_CANCELLED) == 1
        assert peer_events.count(_EVENT_TYPE_CANCEL_REQUESTED) == 1
        assert peer_events.count(_EVENT_TYPE_RUN_CANCELLED) == 1
    finally:
        host.close()


def test_cancel_session_runs_includes_recovering_without_fail_closed(
    tmp_path: Path,
) -> None:
    """session-scope cancel 覆盖 RECOVERING 且不会阻断同批 queued Run。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        recovering = start_run(host, _start_request(session_id, "start-active"))
        queued = start_run(host, _start_request(session_id, "start-queued"))
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            _start_governed_run(
                store.transaction_runner,
                run_id=recovering.run_id,
                expected_status=RunStatus.ACCEPTED,
                id_suffix="recovering-cancel-session",
            )
        _mark_run_status(options.db_path, recovering.run_id, RunStatus.RECOVERING)

        snapshot = cancel_session_runs(
            host, session_id, _cancel_request("cancel-session")
        )

        assert snapshot.active_run_id is None
        assert snapshot.queued_run_ids == ()
        assert _run_status(options.db_path, recovering.run_id) == RunStatus.CANCELLED
        assert _run_status(options.db_path, queued.run_id) == RunStatus.CANCELLED
    finally:
        host.close()


def test_cancel_session_runs_cancels_queued_and_active_worker(
    tmp_path: Path,
) -> None:
    """cancel_session_runs 支持 queued 与 active worker 子集。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        queued = start_run(host, _start_request(session_id, "start-queued"))
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            attempt_id = _start_governed_run(
                store.transaction_runner,
                run_id=active.run_id,
                expected_status=RunStatus.ACCEPTED,
                id_suffix="active",
            )
            _accept_active_worker(
                store.transaction_runner,
                run_id=active.run_id,
                attempt_id=attempt_id,
            )

        snapshot = cancel_session_runs(
            host, session_id, _cancel_request("cancel-session-active")
        )

        assert snapshot.active_run_id == active.run_id
        assert snapshot.queued_run_ids == ()
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLING
        assert _run_status(options.db_path, queued.run_id) == RunStatus.CANCELLED
    finally:
        host.close()


def test_cancel_session_runs_active_replay_does_not_append_facts(
    tmp_path: Path,
) -> None:
    """active session cancel replay 不重复追加 CANCEL_REQUESTED / RUN_CANCELLING。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        active = start_run(host, _start_request(session_id, "start-active"))
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            attempt_id = _start_governed_run(
                store.transaction_runner,
                run_id=active.run_id,
                expected_status=RunStatus.ACCEPTED,
                id_suffix="active-replay",
            )
            _accept_active_worker(
                store.transaction_runner,
                run_id=active.run_id,
                attempt_id=attempt_id,
            )
        request = _cancel_request("cancel-session-active")

        first = cancel_session_runs(host, session_id, request)
        after_first_events = _event_count(host)
        replay = cancel_session_runs(host, session_id, request)

        assert first == replay
        assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLING
        assert _event_count(host) == after_first_events
    finally:
        host.close()


def test_cancel_session_runs_no_supported_run_records_idempotency_without_event(
    tmp_path: Path,
) -> None:
    """没有 supported non-terminal Run 时只记录幂等结果，不追加 cancel fact。"""

    options = _options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host, "slot-a")
        before_cancel = _event_count(host)
        request = _cancel_request("cancel-empty")

        first = cancel_session_runs(host, session_id, request)
        second = cancel_session_runs(host, session_id, request)

        assert first == second
        assert first.active_run_id is None
        assert first.queued_run_ids == ()
        assert _event_count(host) == before_cancel
    finally:
        host.close()
