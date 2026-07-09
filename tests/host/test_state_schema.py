"""Host Phase 3 durable state schema 与 row codec 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dayu.host.api import AttemptStatus, RunStatus, SessionStatus
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.errors import HostDurableError, HostRowDecodeError, HostUniqueConstraintError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import (
    INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
    INDEX_HOST_RUNS_QUEUE_FIFO,
    INDEX_HOST_RUNS_STATUS_SEQUENCE,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSIONS,
)
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunStartReason,
    WorkerKind,
    attempt_row_from_host_row,
    deserialize_dispatch_record_status,
    deserialize_run_status,
    deserialize_run_start_reason,
    deserialize_worker_kind,
    dispatch_record_row_from_host_row,
    read_cancelling_runs,
    run_row_from_host_row,
    serialize_attempt_status,
    serialize_dispatch_record_status,
    serialize_run_status,
    serialize_run_start_reason,
    serialize_session_status,
    serialize_worker_kind,
    session_row_from_host_row,
)
from dayu.host.durable.transaction import HostRow, HostTransaction

_TIMESTAMP = "2026-05-14T00:00:00Z"
_EVENT_DIGEST = "0" * 64
_TERMINAL_RUN_STATUSES = (
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.LOST,
)
_STARTED_RUN_STATUSES = (
    RunStatus.RUNNING,
    RunStatus.WAITING,
    RunStatus.CANCELLING,
    RunStatus.RECOVERING,
)


def _options(
    tmp_path: Path,
    *,
    busy_timeout_seconds: float = 0.25,
) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :param busy_timeout_seconds: SQLite busy timeout 秒数。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=busy_timeout_seconds),
    )


def test_active_run_partial_unique_index_shape(tmp_path: Path) -> None:
    """active Run partial unique index 使用计划指定的列和 active 状态集合。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            index_rows = connection.execute(f"PRAGMA index_list({TABLE_HOST_RUNS})").fetchall()
            matching = [row for row in index_rows if str(row[1]) == INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION]
            assert len(matching) == 1
            assert int(matching[0][2]) == 1
            assert int(matching[0][4]) == 1

            column_rows = connection.execute(f"PRAGMA index_info({INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION})").fetchall()
            assert tuple(str(row[2]) for row in column_rows) == ("session_id",)

            create_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                (INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,),
            ).fetchone()
            assert create_sql_row is not None
            normalized_sql = " ".join(str(create_sql_row[0]).lower().split())
            assert "unique index" in normalized_sql
            assert "where status in" in normalized_sql
            for status in ("running", "waiting", "cancelling", "recovering"):
                assert f"'{status}'" in normalized_sql
        finally:
            connection.close()


def test_run_status_sequence_index_supports_status_ordered_scan(tmp_path: Path) -> None:
    """Run status sequence index 支持按状态扫描并保持 accepted 顺序。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            index_rows = connection.execute(f"PRAGMA index_list({TABLE_HOST_RUNS})").fetchall()
            matching = [row for row in index_rows if str(row[1]) == INDEX_HOST_RUNS_STATUS_SEQUENCE]
            assert len(matching) == 1

            column_rows = connection.execute(f"PRAGMA index_info({INDEX_HOST_RUNS_STATUS_SEQUENCE})").fetchall()
            assert tuple(str(row[2]) for row in column_rows) == (
                "status",
                "accepted_event_sequence",
                "run_id",
            )
        finally:
            connection.close()


def test_run_start_reason_resume_codec_round_trips() -> None:
    """RunStartReason 增加 resume 且 codec 保持封闭 enum。"""

    assert serialize_run_start_reason(RunStartReason.RESUME) == "resume"
    assert deserialize_run_start_reason("resume") == RunStartReason.RESUME
    assert {item.name: item.value for item in RunStartReason} == {
        "INITIAL": "initial",
        "QUEUE_PROMOTION": "queue_promotion",
        "RECOVERY": "recovery",
        "RESUME": "resume",
        "STEER": "steer",
    }


def test_queue_fifo_index_shape(tmp_path: Path) -> None:
    """queued Run FIFO index 使用 session、accepted event sequence 与 run_id。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            index_rows = connection.execute(f"PRAGMA index_list({TABLE_HOST_RUNS})").fetchall()
            matching = [row for row in index_rows if str(row[1]) == INDEX_HOST_RUNS_QUEUE_FIFO]
            assert len(matching) == 1
            assert int(matching[0][2]) == 0
            assert int(matching[0][4]) == 1

            column_rows = connection.execute(f"PRAGMA index_info({INDEX_HOST_RUNS_QUEUE_FIFO})").fetchall()
            assert tuple(str(row[2]) for row in column_rows) == (
                "session_id",
                "accepted_event_sequence",
                "run_id",
            )
        finally:
            connection.close()


def test_two_active_runs_for_one_session_fail_structurally(tmp_path: Path) -> None:
    """同一 Session 第二个 active Run 被 partial unique index 结构化拒绝。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> None:
            """写入一个 open Session 和一个 active Run。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )

        def duplicate_active(transaction: HostTransaction) -> None:
            """尝试写入第二个 active Run。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_run_tx(
                transaction,
                run_id="run-2",
                session_id="session-1",
                status=RunStatus.WAITING,
                client_request_id="request-2",
            )

        store.transaction_runner.run_write(seed)
        with pytest.raises(HostUniqueConstraintError):
            store.transaction_runner.run_write(duplicate_active)


def test_active_runs_for_different_sessions_succeed(tmp_path: Path) -> None:
    """不同 Session 可以同时拥有 active Run。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> int:
            """写入两个不同 Session 的 active Run。

            :param transaction: Host transaction。
            :returns: active Run 总数。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_session_tx(transaction, session_id="session-2")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )
            _insert_run_tx(
                transaction,
                run_id="run-2",
                session_id="session-2",
                status=RunStatus.RECOVERING,
                client_request_id="request-2",
            )
            row = transaction.fetchone(f"SELECT COUNT(*) AS count FROM {TABLE_HOST_RUNS}")
            assert row is not None
            return _required_row_int(row, column="count")

        assert store.transaction_runner.run_write(operation) == 2


@pytest.mark.parametrize("status", _STARTED_RUN_STATUSES)
def test_started_run_status_requires_started_event_columns(tmp_path: Path, status: RunStatus) -> None:
    """active / recovering Run 缺 started event 时必须被 schema CHECK 拒绝。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入缺 started event 的非法 Run row。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=status,
                client_request_id="request-1",
                include_started_event=False,
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


@pytest.mark.parametrize("terminal_status", _TERMINAL_RUN_STATUSES)
def test_same_session_active_and_terminal_runs_succeed(tmp_path: Path, terminal_status: RunStatus) -> None:
    """同一 Session 可同时保存一个 active Run 与一个 terminal Run。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> int:
            """写入同一 Session 的 active Run 与 terminal Run。

            :param transaction: Host transaction。
            :returns: 该 Session 下的 Run 总数。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-active",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-active",
            )
            _insert_run_tx(
                transaction,
                run_id=f"run-terminal-{terminal_status.value}",
                session_id="session-1",
                status=terminal_status,
                client_request_id=f"request-terminal-{terminal_status.value}",
            )
            row = transaction.fetchone(
                f"SELECT COUNT(*) AS count FROM {TABLE_HOST_RUNS} " "WHERE session_id = ?",
                ("session-1",),
            )
            assert row is not None
            return _required_row_int(row, column="count")

        assert store.transaction_runner.run_write(operation) == 2


@pytest.mark.parametrize("terminal_status", _TERMINAL_RUN_STATUSES)
def test_run_terminal_shape_check_rejects_terminal_missing_ref(
    tmp_path: Path,
    terminal_status: RunStatus,
) -> None:
    """Run DDL CHECK 拒绝终态 Run 缺少任一 terminal ref。

    :param tmp_path: pytest 临时目录。
    :param terminal_status: 待验证的 Run 终态。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入合法终态 Run 后清空 terminal_at 以触发 DDL CHECK。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-terminal",
                session_id="session-1",
                status=terminal_status,
                client_request_id="request-terminal",
            )
            transaction.execute(
                f"UPDATE {TABLE_HOST_RUNS} SET terminal_at = NULL WHERE run_id = ?",
                ("run-terminal",),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


@pytest.mark.parametrize("status", _STARTED_RUN_STATUSES)
def test_run_terminal_shape_check_rejects_non_terminal_ref(
    tmp_path: Path,
    status: RunStatus,
) -> None:
    """Run DDL CHECK 拒绝非终态 Run 携带任一 terminal ref。

    :param tmp_path: pytest 临时目录。
    :param status: 待验证的非终态 Run 状态。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入非终态 Run 后补入 terminal_at 以触发 DDL CHECK。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-active",
                session_id="session-1",
                status=status,
                client_request_id="request-active",
            )
            transaction.execute(
                f"UPDATE {TABLE_HOST_RUNS} SET terminal_at = ? WHERE run_id = ?",
                (_TIMESTAMP, "run-active"),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


@pytest.mark.parametrize("status", (RunStatus.CANCELLING, RunStatus.CANCELLED))
def test_cancel_acceptance_status_requires_cancel_request_event_id(
    tmp_path: Path,
    status: RunStatus,
) -> None:
    """Run DDL CHECK 拒绝 cancelling / cancelled 缺 typed cancel link。

    :param tmp_path: pytest 临时目录。
    :param status: 待验证的 accepted cancel 状态。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入合法 Run 后清空 cancel_request_event_id 以触发 DDL CHECK。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-cancel-link")
            _insert_run_tx(
                transaction,
                run_id=f"run-{status.value}",
                session_id="session-cancel-link",
                status=status,
                client_request_id=f"request-{status.value}",
            )
            transaction.execute(
                f"UPDATE {TABLE_HOST_RUNS} SET cancel_request_event_id = NULL WHERE run_id = ?",
                (f"run-{status.value}",),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_attempt_terminal_shape_check_rejects_terminal_missing_ref(
    tmp_path: Path,
) -> None:
    """Attempt DDL CHECK 拒绝终态 Attempt 缺少任一 terminal ref。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入 Attempt 并尝试设为缺 terminal_at 的终态。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-1",
                run_id="run-1",
                execution_id="execution-1",
            )
            terminal_sequence = _insert_event_tx(
                transaction,
                event_id="event-attempt-terminal",
                session_id="session-1",
                run_id="run-1",
                attempt_id="attempt-1",
                execution_id="execution-1",
            )
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_ATTEMPTS}
                SET status = ?,
                    terminal_event_id = ?,
                    terminal_event_sequence = ?,
                    terminal_at = NULL
                WHERE attempt_id = ?
                """,
                (
                    serialize_attempt_status(AttemptStatus.SUCCEEDED),
                    "event-attempt-terminal",
                    terminal_sequence,
                    "attempt-1",
                ),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_attempt_terminal_shape_check_rejects_non_terminal_ref(
    tmp_path: Path,
) -> None:
    """Attempt DDL CHECK 拒绝非终态 Attempt 携带任一 terminal ref。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入 STARTING Attempt 后补入 terminal_at 以触发 DDL CHECK。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-1",
                run_id="run-1",
                execution_id="execution-1",
            )
            transaction.execute(
                f"UPDATE {TABLE_HOST_ATTEMPTS} SET terminal_at = ? WHERE attempt_id = ?",
                (_TIMESTAMP, "attempt-1"),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_multiple_queued_runs_for_one_session_succeed(tmp_path: Path) -> None:
    """同一 Session 可以 durable 保存多个 queued Run。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> int:
            """写入同一 Session 的多个 queued Run。

            :param transaction: Host transaction。
            :returns: queued Run 总数。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.QUEUED,
                client_request_id="request-1",
            )
            _insert_run_tx(
                transaction,
                run_id="run-2",
                session_id="session-1",
                status=RunStatus.QUEUED,
                client_request_id="request-2",
            )
            row = transaction.fetchone(
                f"SELECT COUNT(*) AS count FROM {TABLE_HOST_RUNS} WHERE status = ?",
                (serialize_run_status(RunStatus.QUEUED),),
            )
            assert row is not None
            return _required_row_int(row, column="count")

        assert store.transaction_runner.run_write(operation) == 2


def test_read_cancelling_runs_returns_only_cancelling_rows(tmp_path: Path) -> None:
    """cancelling Run 专用查询只返回 watchdog 需要的状态。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> tuple[str, ...]:
            """写入多种非终态 Run 后读取 cancelling Run。

            :param transaction: Host transaction。
            :returns: cancelling Run id 序列。
            """

            _insert_session_tx(transaction, session_id="session-running")
            _insert_run_tx(
                transaction,
                run_id="run-running",
                session_id="session-running",
                status=RunStatus.RUNNING,
                client_request_id="request-running",
            )
            _insert_session_tx(transaction, session_id="session-waiting")
            _insert_run_tx(
                transaction,
                run_id="run-waiting",
                session_id="session-waiting",
                status=RunStatus.WAITING,
                client_request_id="request-waiting",
            )
            _insert_session_tx(transaction, session_id="session-cancelling-1")
            _insert_run_tx(
                transaction,
                run_id="run-cancelling-1",
                session_id="session-cancelling-1",
                status=RunStatus.CANCELLING,
                client_request_id="request-cancelling-1",
            )
            _insert_session_tx(transaction, session_id="session-cancelling-2")
            _insert_run_tx(
                transaction,
                run_id="run-cancelling-2",
                session_id="session-cancelling-2",
                status=RunStatus.CANCELLING,
                client_request_id="request-cancelling-2",
            )
            return tuple(row.run_id for row in read_cancelling_runs(transaction))

        assert store.transaction_runner.run_write(operation) == (
            "run-cancelling-1",
            "run-cancelling-2",
        )


def test_dispatch_record_status_check_allows_phase5_statuses(
    tmp_path: Path,
) -> None:
    """dispatch record status check 接受 Phase 5 四种状态。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def allowed_statuses(transaction: HostTransaction) -> tuple[int, tuple[str, ...]]:
            """写入四种合法 dispatch record。

            :param transaction: Host transaction。
            :returns: dispatch record 总数与状态序列。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-pending",
                run_id="run-1",
                execution_id="execution-pending",
            )
            _insert_dispatch_record_tx(
                transaction,
                dispatch_record_id="dispatch-pending",
                run_id="run-1",
                attempt_id="attempt-pending",
                execution_id="execution-pending",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-cancelled",
                run_id="run-1",
                execution_id="execution-cancelled",
            )
            _insert_cancelled_dispatch_record_tx(
                transaction,
                dispatch_record_id="dispatch-cancelled",
                run_id="run-1",
                attempt_id="attempt-cancelled",
                execution_id="execution-cancelled",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-waiting",
                run_id="run-1",
                execution_id="execution-waiting",
            )
            _insert_waiting_dispatch_record_tx(
                transaction,
                dispatch_record_id="dispatch-waiting",
                run_id="run-1",
                attempt_id="attempt-waiting",
                execution_id="execution-waiting",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-dispatching",
                run_id="run-1",
                execution_id="execution-dispatching",
            )
            _insert_dispatching_dispatch_record_tx(
                transaction,
                dispatch_record_id="dispatch-dispatching",
                run_id="run-1",
                attempt_id="attempt-dispatching",
                execution_id="execution-dispatching",
            )
            row = transaction.fetchone(f"SELECT COUNT(*) AS count FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}")
            assert row is not None
            rows = transaction.fetchall(f"""
                SELECT status
                FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
                ORDER BY status ASC
                """)
            return (
                _required_row_int(row, column="count"),
                tuple(_required_row_text(status_row, column="status") for status_row in rows),
            )

        def operation(transaction: HostTransaction) -> None:
            """尝试写入非法 dispatch status。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-invalid")
            _insert_run_tx(
                transaction,
                run_id="run-invalid",
                session_id="session-invalid",
                status=RunStatus.RUNNING,
                client_request_id="request-invalid",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-invalid",
                run_id="run-invalid",
                execution_id="execution-invalid",
            )
            created_sequence = _insert_event_tx(
                transaction,
                event_id="event-dispatch-created",
                session_id="session-invalid",
                run_id="run-invalid",
                attempt_id="attempt-invalid",
                execution_id="execution-invalid",
            )
            transaction.execute(
                f"""
                INSERT INTO {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
                  dispatch_record_id,
                  run_id,
                  attempt_id,
                  execution_id,
                  status,
                  worker_kind,
                  execution_target,
                  owner_host_instance_id,
                  created_event_id,
                  created_event_sequence,
                  waiting_for_lane_at,
                  lane_name,
                  lane_claim_id,
                  lane_owner_id,
                  lane_acquired_at,
                  dispatching_at,
                  worker_accepted_at,
                  worker_accept_event_id,
                  worker_accept_event_sequence,
                  cancelled_event_id,
                  cancelled_event_sequence,
                  created_at,
                  updated_at,
                  cancelled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dispatch-1",
                    "run-invalid",
                    "attempt-invalid",
                    "execution-invalid",
                    "accepted",
                    serialize_worker_kind(WorkerKind.LOCAL),
                    "local-default",
                    None,
                    "event-dispatch-created",
                    created_sequence,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    _TIMESTAMP,
                    _TIMESTAMP,
                    None,
                ),
            )

        assert store.transaction_runner.run_write(allowed_statuses) == (
            4,
            ("cancelled", "dispatching", "pending", "waiting_for_lane"),
        )
        with pytest.raises(HostDurableError) as error_info:
            store.transaction_runner.run_write(operation)
        assert str(error_info.value) == "Host durable CHECK constraint failed"


def test_state_row_codecs_round_trip_from_host_rows(tmp_path: Path) -> None:
    """state.py row conversion helpers 从 HostRow 还原强类型 row dataclass。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> tuple[str, str, str, str]:
            """写入并读取 Session、Run、Attempt、Dispatch row。

            :param transaction: Host transaction。
            :returns: 四类 row 的关键状态文本。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-1",
                run_id="run-1",
                execution_id="execution-1",
            )
            _insert_dispatch_record_tx(
                transaction,
                dispatch_record_id="dispatch-1",
                run_id="run-1",
                attempt_id="attempt-1",
                execution_id="execution-1",
            )

            session_host_row = transaction.fetchone(
                f"SELECT * FROM {TABLE_HOST_SESSIONS} WHERE session_id = ?",
                ("session-1",),
            )
            run_host_row = transaction.fetchone(
                f"SELECT * FROM {TABLE_HOST_RUNS} WHERE run_id = ?",
                ("run-1",),
            )
            attempt_host_row = transaction.fetchone(
                f"SELECT * FROM {TABLE_HOST_ATTEMPTS} WHERE attempt_id = ?",
                ("attempt-1",),
            )
            dispatch_host_row = transaction.fetchone(
                f"""
                SELECT * FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
                WHERE dispatch_record_id = ?
                """,
                ("dispatch-1",),
            )
            assert session_host_row is not None
            assert run_host_row is not None
            assert attempt_host_row is not None
            assert dispatch_host_row is not None

            session_row = session_row_from_host_row(session_host_row)
            run_row = run_row_from_host_row(run_host_row)
            attempt_row = attempt_row_from_host_row(attempt_host_row)
            dispatch_row = dispatch_record_row_from_host_row(dispatch_host_row)

            return (
                serialize_session_status(session_row.status),
                serialize_run_status(run_row.status),
                serialize_attempt_status(attempt_row.status),
                serialize_dispatch_record_status(dispatch_row.status),
            )

        assert store.transaction_runner.run_write(operation) == (
            "open",
            "running",
            "starting",
            "pending",
        )


def test_run_row_decode_missing_status_column_raises_row_decode_error() -> None:
    """Run row decode 缺少 status 列时抛出稳定 row decode 错误。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError) as error_info:
        run_row_from_host_row(_run_host_row(include_status_column=False))

    _assert_host_row_decode_error(
        error_info.value,
        row_name=TABLE_HOST_RUNS,
        field_name="status",
    )


def test_run_row_decode_integer_status_raises_row_decode_error() -> None:
    """Run row decode 读取到整数 status 时抛出稳定 row decode 错误。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError) as error_info:
        run_row_from_host_row(_run_host_row(status=1))

    _assert_host_row_decode_error(
        error_info.value,
        row_name=TABLE_HOST_RUNS,
        field_name="status",
    )


def test_run_row_decode_terminal_missing_terminal_at_raises_row_decode_error() -> None:
    """Run row decode 终态缺少 terminal_at 时抛出稳定 row decode 错误。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError) as error_info:
        run_row_from_host_row(
            _run_host_row(
                status=serialize_run_status(RunStatus.SUCCEEDED),
                terminal_event_id="event-terminal-run-1",
                terminal_event_sequence=3,
                terminal_at=None,
            )
        )

    _assert_host_row_decode_error(
        error_info.value,
        row_name=TABLE_HOST_RUNS,
        field_name=None,
    )


def test_attempt_row_decode_terminal_missing_refs_raises_row_decode_error() -> None:
    """Attempt row decode 终态缺少 terminal refs 时抛出稳定 row decode 错误。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError) as error_info:
        attempt_row_from_host_row(
            _attempt_host_row(
                status=serialize_attempt_status(AttemptStatus.SUCCEEDED),
                terminal_event_id=None,
                terminal_event_sequence=None,
                terminal_at=None,
            )
        )

    _assert_host_row_decode_error(
        error_info.value,
        row_name=TABLE_HOST_ATTEMPTS,
        field_name=None,
    )


def test_dispatch_record_nullability_rules_reject_invalid_shapes(
    tmp_path: Path,
) -> None:
    """dispatch record fresh schema 拒绝不符合状态 nullability 的字段组合。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """尝试写入缺少 owner 的 waiting_for_lane dispatch。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _insert_session_tx(transaction, session_id="session-1")
            _insert_run_tx(
                transaction,
                run_id="run-1",
                session_id="session-1",
                status=RunStatus.RUNNING,
                client_request_id="request-1",
            )
            _insert_attempt_tx(
                transaction,
                attempt_id="attempt-invalid-waiting",
                run_id="run-1",
                execution_id="execution-invalid-waiting",
            )
            _insert_waiting_dispatch_record_tx(
                transaction,
                dispatch_record_id="dispatch-invalid-waiting",
                run_id="run-1",
                attempt_id="attempt-invalid-waiting",
                execution_id="execution-invalid-waiting",
                owner_host_instance_id=None,
            )

        with pytest.raises(HostDurableError) as error_info:
            store.transaction_runner.run_write(operation)
        assert str(error_info.value) == "Host durable CHECK constraint failed"


def test_dispatch_record_nullability_rules_reject_each_status_invalid_shape(
    tmp_path: Path,
) -> None:
    """dispatch record 四个状态各自拒绝越界诊断字段组合。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _assert_invalid_dispatch_shape(
            store,
            attempt_id="attempt-invalid-pending",
            status=DispatchRecordStatus.PENDING,
            owner_host_instance_id=None,
            waiting_for_lane_at=_TIMESTAMP,
            lane_name=None,
            lane_claim_id=None,
            lane_owner_id=None,
            lane_acquired_at=None,
            dispatching_at=None,
            cancelled_event_id=None,
            cancelled_event_sequence=None,
            cancelled_at=None,
        )
        _assert_invalid_dispatch_shape(
            store,
            attempt_id="attempt-invalid-waiting",
            status=DispatchRecordStatus.WAITING_FOR_LANE,
            owner_host_instance_id="host-instance-1",
            waiting_for_lane_at=_TIMESTAMP,
            lane_name=None,
            lane_claim_id=None,
            lane_owner_id=None,
            lane_acquired_at=None,
            dispatching_at=None,
            cancelled_event_id=None,
            cancelled_event_sequence=None,
            cancelled_at=None,
        )
        _assert_invalid_dispatch_shape(
            store,
            attempt_id="attempt-invalid-dispatching",
            status=DispatchRecordStatus.DISPATCHING,
            owner_host_instance_id="host-instance-1",
            waiting_for_lane_at=_TIMESTAMP,
            lane_name="llm",
            lane_claim_id=None,
            lane_owner_id="lane-owner-1",
            lane_acquired_at=_TIMESTAMP,
            dispatching_at=_TIMESTAMP,
            cancelled_event_id=None,
            cancelled_event_sequence=None,
            cancelled_at=None,
        )
        _assert_invalid_dispatch_shape(
            store,
            attempt_id="attempt-invalid-cancelled",
            status=DispatchRecordStatus.CANCELLED,
            owner_host_instance_id=None,
            waiting_for_lane_at=None,
            lane_name=None,
            lane_claim_id=None,
            lane_owner_id=None,
            lane_acquired_at=None,
            dispatching_at=None,
            cancelled_event_id="event-cancelled-missing-sequence",
            cancelled_event_sequence=None,
            cancelled_at=_TIMESTAMP,
        )


def test_status_deserializers_reject_unknown_values() -> None:
    """状态反序列化 helper 对未知值结构化失败。"""

    with pytest.raises(HostDurableError):
        deserialize_run_status("active")
    with pytest.raises(HostDurableError):
        deserialize_dispatch_record_status("accepted")
    with pytest.raises(HostDurableError):
        deserialize_worker_kind("thread")


def _assert_host_row_decode_error(
    error: HostDurableError,
    *,
    row_name: str,
    field_name: str | None,
) -> None:
    """断言错误保持 durable row decode 边界属性。

    :param error: 捕获到的 durable 错误。
    :param row_name: 期望的 row 名称。
    :param field_name: 期望的字段名；row 级形状错误时为 ``None``。
    :returns: ``None``。
    :raises AssertionError: 错误类型、属性或消息不符合预期时抛出。
    """

    assert isinstance(error, HostDurableError)
    assert isinstance(error, HostRowDecodeError)
    assert error.row_name == row_name
    assert error.field_name == field_name
    assert row_name in str(error)
    if field_name is not None:
        assert field_name in str(error)


def _run_host_row(
    *,
    status: str | int = "running",
    terminal_event_id: str | None = None,
    terminal_event_sequence: int | None = None,
    terminal_at: str | None = None,
    include_status_column: bool = True,
) -> HostRow:
    """构造 Run row codec 测试用 HostRow。

    :param status: status 列的原始 SQLite 值。
    :param terminal_event_id: terminal EventLog id。
    :param terminal_event_sequence: terminal EventLog sequence。
    :param terminal_at: terminal timestamp。
    :param include_status_column: 是否包含 status 列。
    :returns: ``HostRow``。
    :raises AssertionError: 本 helper 不主动触发断言。
    """

    if include_status_column:
        return HostRow(
            columns=(
                "run_id",
                "session_id",
                "status",
                "client_request_id",
                "input_event_id",
                "input_event_sequence",
                "accepted_event_id",
                "accepted_event_sequence",
                "queued_event_id",
                "queued_event_sequence",
                "started_event_id",
                "started_event_sequence",
                "terminal_event_id",
                "terminal_event_sequence",
                "cancel_request_event_id",
                "current_attempt_id",
                "source_run_id",
                "source_run_relation",
                "execution_target",
                "queue_policy",
                "created_at",
                "updated_at",
                "terminal_at",
            ),
            values=(
                "run-1",
                "session-1",
                status,
                "request-1",
                "event-input-run-1",
                1,
                "event-accepted-run-1",
                2,
                None,
                None,
                "event-started-run-1",
                3,
                terminal_event_id,
                terminal_event_sequence,
                None,
                None,
                None,
                None,
                "local-default",
                "queue",
                _TIMESTAMP,
                _TIMESTAMP,
                terminal_at,
            ),
        )
    return HostRow(
        columns=(
            "run_id",
            "session_id",
            "client_request_id",
            "input_event_id",
            "input_event_sequence",
            "accepted_event_id",
            "accepted_event_sequence",
            "queued_event_id",
            "queued_event_sequence",
            "started_event_id",
            "started_event_sequence",
            "terminal_event_id",
            "terminal_event_sequence",
            "cancel_request_event_id",
            "current_attempt_id",
            "source_run_id",
            "source_run_relation",
            "execution_target",
            "queue_policy",
            "created_at",
            "updated_at",
            "terminal_at",
        ),
        values=(
            "run-1",
            "session-1",
            "request-1",
            "event-input-run-1",
            1,
            "event-accepted-run-1",
            2,
            None,
            None,
            "event-started-run-1",
            3,
            terminal_event_id,
            terminal_event_sequence,
            None,
            None,
            None,
            None,
            "local-default",
            "queue",
            _TIMESTAMP,
            _TIMESTAMP,
            terminal_at,
        ),
    )


def _attempt_host_row(
    *,
    status: str = "starting",
    terminal_event_id: str | None = None,
    terminal_event_sequence: int | None = None,
    terminal_at: str | None = None,
) -> HostRow:
    """构造 Attempt row codec 测试用 HostRow。

    :param status: status 列文本。
    :param terminal_event_id: terminal EventLog id。
    :param terminal_event_sequence: terminal EventLog sequence。
    :param terminal_at: terminal timestamp。
    :returns: ``HostRow``。
    :raises AssertionError: 本 helper 不主动触发断言。
    """

    return HostRow(
        columns=(
            "attempt_id",
            "run_id",
            "execution_id",
            "status",
            "started_event_id",
            "started_event_sequence",
            "terminal_event_id",
            "terminal_event_sequence",
            "created_at",
            "updated_at",
            "terminal_at",
        ),
        values=(
            "attempt-1",
            "run-1",
            "execution-1",
            status,
            "event-attempt-started-attempt-1",
            1,
            terminal_event_id,
            terminal_event_sequence,
            _TIMESTAMP,
            _TIMESTAMP,
            terminal_at,
        ),
    )


def _insert_event_tx(
    transaction: HostTransaction,
    *,
    event_id: str,
    session_id: str,
    event_type: str = "TEST_EVENT",
    run_id: str | None = None,
    attempt_id: str | None = None,
    execution_id: str | None = None,
) -> int:
    """插入测试用 EventLog row 并返回 sequence。

    :param transaction: Host transaction。
    :param event_id: EventLog event id。
    :param session_id: 事件所属 Session。
    :param event_type: EventLog event type。
    :param run_id: 事件所属 Run。
    :param attempt_id: 事件所属 Attempt。
    :param execution_id: execution id。
    :returns: 插入事件的 ``event_sequence``。
    """

    result = transaction.execute(
        """
        INSERT INTO event_log (
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            _EVENT_DIGEST,
            "canonical_fact",
            session_id,
            run_id,
            attempt_id,
            execution_id,
            event_type,
            _TIMESTAMP,
            None,
            None,
            None,
            None,
            None,
            None,
            "{}",
            None,
            None,
            _TIMESTAMP,
        ),
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _required_row_int(row: HostRow, *, column: str) -> int:
    """从 HostRow 中读取必填整数列。

    :param row: Host transaction 查询返回的 row。
    :param column: 目标列名。
    :returns: 整数列值。
    :raises AssertionError: 列值不是整数时抛出。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value


def _required_row_text(row: HostRow, *, column: str) -> str:
    """从 HostRow 中读取必填字符串列。

    :param row: Host transaction 查询返回的 row。
    :param column: 目标列名。
    :returns: 字符串列值。
    :raises AssertionError: 列值不是字符串时抛出。
    """

    value = row.get(column)
    assert isinstance(value, str)
    return value


def _assert_invalid_dispatch_shape(
    store: HostDurableStore,
    *,
    attempt_id: str,
    status: DispatchRecordStatus,
    owner_host_instance_id: str | None,
    waiting_for_lane_at: str | None,
    lane_name: str | None,
    lane_claim_id: str | None,
    lane_owner_id: str | None,
    lane_acquired_at: str | None,
    dispatching_at: str | None,
    cancelled_event_id: str | None,
    cancelled_event_sequence: int | None,
    cancelled_at: str | None,
) -> None:
    """断言一组 dispatch record 诊断字段组合被 schema 拒绝。

    :param store: Host durable store。
    :param attempt_id: 测试 Attempt id。
    :param status: dispatch record 状态。
    :param owner_host_instance_id: owner Host instance id。
    :param waiting_for_lane_at: lane 等待时间。
    :param lane_name: lane 名称。
    :param lane_claim_id: lane claim id。
    :param lane_owner_id: lane owner id。
    :param lane_acquired_at: lane 获取时间。
    :param dispatching_at: dispatching 时间。
    :param cancelled_event_id: cancel event id。
    :param cancelled_event_sequence: cancel event sequence。
    :param cancelled_at: cancel 时间。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """写入非法 dispatch record。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _insert_session_tx(transaction, session_id="session-1")
        _insert_run_tx(
            transaction,
            run_id=f"run-{attempt_id}",
            session_id="session-1",
            status=RunStatus.RUNNING,
            client_request_id=f"request-{attempt_id}",
        )
        _insert_attempt_tx(
            transaction,
            attempt_id=attempt_id,
            run_id=f"run-{attempt_id}",
            execution_id=f"execution-{attempt_id}",
        )
        if owner_host_instance_id is not None:
            _ensure_host_instance_tx(
                transaction,
                host_instance_id=owner_host_instance_id,
            )
        _insert_dispatch_record_with_diagnostics_tx(
            transaction,
            dispatch_record_id=f"dispatch-{attempt_id}",
            run_id=f"run-{attempt_id}",
            attempt_id=attempt_id,
            execution_id=f"execution-{attempt_id}",
            status=status,
            owner_host_instance_id=owner_host_instance_id,
            waiting_for_lane_at=waiting_for_lane_at,
            lane_name=lane_name,
            lane_claim_id=lane_claim_id,
            lane_owner_id=lane_owner_id,
            lane_acquired_at=lane_acquired_at,
            dispatching_at=dispatching_at,
            worker_accepted_at=None,
            worker_accept_event_id=None,
            worker_accept_event_sequence=None,
            cancelled_event_id=cancelled_event_id,
            cancelled_event_sequence=cancelled_event_sequence,
            cancelled_at=cancelled_at,
        )

    with pytest.raises(HostDurableError) as error_info:
        store.transaction_runner.run_write(operation)
    assert str(error_info.value) == "Host durable CHECK constraint failed"


def _insert_session_tx(transaction: HostTransaction, *, session_id: str) -> None:
    """插入测试用 open Session。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :returns: ``None``。
    """

    event_id = f"event-session-created-{session_id}"
    created_sequence = _insert_event_tx(transaction, event_id=event_id, session_id=session_id)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSIONS} (
          session_id,
          status,
          metadata_json,
          created_event_id,
          created_event_sequence,
          closed_event_id,
          closed_event_sequence,
          created_at,
          closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            serialize_session_status(SessionStatus.OPEN),
            "{}",
            event_id,
            created_sequence,
            None,
            None,
            _TIMESTAMP,
            None,
        ),
    )


def _insert_run_tx(
    transaction: HostTransaction,
    *,
    run_id: str,
    session_id: str,
    status: RunStatus,
    client_request_id: str,
    include_started_event: bool = True,
) -> None:
    """插入测试用 Run row。

    :param transaction: Host transaction。
    :param run_id: Run id。
    :param session_id: Session id。
    :param status: Run 状态。
    :param client_request_id: client request id。
    :param include_started_event: active / recovering 状态是否写入 started event。
    :returns: ``None``。
    """

    input_event_id = f"event-input-{run_id}"
    accepted_event_id = f"event-accepted-{run_id}"
    input_sequence = _insert_event_tx(
        transaction,
        event_id=input_event_id,
        session_id=session_id,
        run_id=run_id,
    )
    accepted_sequence = _insert_event_tx(
        transaction,
        event_id=accepted_event_id,
        session_id=session_id,
        run_id=run_id,
    )
    queued_event_id: str | None = None
    queued_sequence: int | None = None
    started_event_id: str | None = None
    started_sequence: int | None = None
    terminal_event_id: str | None = None
    terminal_sequence: int | None = None
    cancel_request_event_id: str | None = None
    terminal_at: str | None = None
    if status == RunStatus.QUEUED:
        queued_event_id = f"event-queued-{run_id}"
        queued_sequence = _insert_event_tx(
            transaction,
            event_id=queued_event_id,
            session_id=session_id,
            run_id=run_id,
        )
    if include_started_event and status in _STARTED_RUN_STATUSES:
        started_event_id = f"event-started-{run_id}"
        started_sequence = _insert_event_tx(
            transaction,
            event_id=started_event_id,
            session_id=session_id,
            run_id=run_id,
        )
    if status in _TERMINAL_RUN_STATUSES:
        terminal_event_id = f"event-terminal-{run_id}"
        terminal_sequence = _insert_event_tx(
            transaction,
            event_id=terminal_event_id,
            session_id=session_id,
            run_id=run_id,
        )
        terminal_at = _TIMESTAMP
    if status in (RunStatus.CANCELLING, RunStatus.CANCELLED):
        cancel_request_event_id = f"event-cancel-requested-{run_id}"
        _insert_event_tx(
            transaction,
            event_id=cancel_request_event_id,
            session_id=session_id,
            event_type="CANCEL_REQUESTED",
            run_id=run_id,
        )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_RUNS} (
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          cancel_request_event_id,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            session_id,
            serialize_run_status(status),
            client_request_id,
            input_event_id,
            input_sequence,
            accepted_event_id,
            accepted_sequence,
            queued_event_id,
            queued_sequence,
            started_event_id,
            started_sequence,
            terminal_event_id,
            terminal_sequence,
            cancel_request_event_id,
            None,
            None,
            None,
            "local-default",
            "queue",
            _TIMESTAMP,
            _TIMESTAMP,
            terminal_at,
        ),
    )


def _insert_attempt_tx(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    run_id: str,
    execution_id: str,
) -> None:
    """插入测试用 starting Attempt。

    :param transaction: Host transaction。
    :param attempt_id: Attempt id。
    :param run_id: Run id。
    :param execution_id: execution id。
    :returns: ``None``。
    """

    started_event_id = f"event-attempt-started-{attempt_id}"
    started_sequence = _insert_event_tx(
        transaction,
        event_id=started_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPTS} (
          attempt_id,
          run_id,
          execution_id,
          status,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            run_id,
            execution_id,
            serialize_attempt_status(AttemptStatus.STARTING),
            started_event_id,
            started_sequence,
            None,
            None,
            _TIMESTAMP,
            _TIMESTAMP,
            None,
        ),
    )


def _insert_dispatch_record_tx(
    transaction: HostTransaction,
    *,
    dispatch_record_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> None:
    """插入测试用 pending dispatch record。

    :param transaction: Host transaction。
    :param dispatch_record_id: dispatch record id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: ``None``。
    """

    created_event_id = f"event-dispatch-created-{dispatch_record_id}"
    created_sequence = _insert_event_tx(
        transaction,
        event_id=created_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dispatch_record_id,
            run_id,
            attempt_id,
            execution_id,
            serialize_dispatch_record_status(DispatchRecordStatus.PENDING),
            serialize_worker_kind(WorkerKind.LOCAL),
            "local-default",
            None,
            created_event_id,
            created_sequence,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            _TIMESTAMP,
            _TIMESTAMP,
            None,
        ),
    )


def _insert_cancelled_dispatch_record_tx(
    transaction: HostTransaction,
    *,
    dispatch_record_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> None:
    """插入测试用 cancelled dispatch record。

    :param transaction: Host transaction。
    :param dispatch_record_id: dispatch record id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: ``None``。
    """

    created_event_id = f"event-dispatch-created-{dispatch_record_id}"
    cancelled_event_id = f"event-dispatch-cancelled-{dispatch_record_id}"
    created_sequence = _insert_event_tx(
        transaction,
        event_id=created_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    cancelled_sequence = _insert_event_tx(
        transaction,
        event_id=cancelled_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dispatch_record_id,
            run_id,
            attempt_id,
            execution_id,
            serialize_dispatch_record_status(DispatchRecordStatus.CANCELLED),
            serialize_worker_kind(WorkerKind.LOCAL),
            "local-default",
            None,
            created_event_id,
            created_sequence,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            cancelled_event_id,
            cancelled_sequence,
            _TIMESTAMP,
            _TIMESTAMP,
            _TIMESTAMP,
        ),
    )


def _insert_waiting_dispatch_record_tx(
    transaction: HostTransaction,
    *,
    dispatch_record_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    owner_host_instance_id: str | None = "host-instance-1",
) -> None:
    """插入测试用 waiting_for_lane dispatch record。

    :param transaction: Host transaction。
    :param dispatch_record_id: dispatch record id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param owner_host_instance_id: owner Host instance id。
    :returns: ``None``。
    """

    _ensure_host_instance_tx(transaction, host_instance_id="host-instance-1")
    _insert_dispatch_record_with_diagnostics_tx(
        transaction,
        dispatch_record_id=dispatch_record_id,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        status=DispatchRecordStatus.WAITING_FOR_LANE,
        owner_host_instance_id=owner_host_instance_id,
        waiting_for_lane_at=_TIMESTAMP,
        lane_name="llm",
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        cancelled_at=None,
    )


def _insert_dispatching_dispatch_record_tx(
    transaction: HostTransaction,
    *,
    dispatch_record_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> None:
    """插入测试用 pre-accept dispatching dispatch record。

    :param transaction: Host transaction。
    :param dispatch_record_id: dispatch record id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: ``None``。
    """

    _ensure_host_instance_tx(transaction, host_instance_id="host-instance-1")
    _insert_dispatch_record_with_diagnostics_tx(
        transaction,
        dispatch_record_id=dispatch_record_id,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        status=DispatchRecordStatus.DISPATCHING,
        owner_host_instance_id="host-instance-1",
        waiting_for_lane_at=_TIMESTAMP,
        lane_name="llm",
        lane_claim_id="lane-claim-1",
        lane_owner_id="lane-owner-1",
        lane_acquired_at=_TIMESTAMP,
        dispatching_at=_TIMESTAMP,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        cancelled_at=None,
    )


def _insert_dispatch_record_with_diagnostics_tx(
    transaction: HostTransaction,
    *,
    dispatch_record_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    status: DispatchRecordStatus,
    owner_host_instance_id: str | None,
    waiting_for_lane_at: str | None,
    lane_name: str | None,
    lane_claim_id: str | None,
    lane_owner_id: str | None,
    lane_acquired_at: str | None,
    dispatching_at: str | None,
    worker_accepted_at: str | None,
    worker_accept_event_id: str | None,
    worker_accept_event_sequence: int | None,
    cancelled_event_id: str | None,
    cancelled_event_sequence: int | None,
    cancelled_at: str | None,
) -> None:
    """插入带 Phase 5 诊断字段的 dispatch record。

    :param transaction: Host transaction。
    :param dispatch_record_id: dispatch record id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param status: dispatch record 状态。
    :param owner_host_instance_id: owner Host instance id。
    :param waiting_for_lane_at: lane 等待时间。
    :param lane_name: lane 名称。
    :param lane_claim_id: lane claim id。
    :param lane_owner_id: lane owner id。
    :param lane_acquired_at: lane 获取时间。
    :param dispatching_at: dispatching 时间。
    :param worker_accepted_at: worker accept 时间。
    :param worker_accept_event_id: ``ATTEMPT_RUNNING`` event id。
    :param worker_accept_event_sequence: ``ATTEMPT_RUNNING`` event sequence。
    :param cancelled_event_id: cancel event id。
    :param cancelled_event_sequence: cancel event sequence。
    :param cancelled_at: cancel 时间。
    :returns: ``None``。
    """

    created_event_id = f"event-dispatch-created-{dispatch_record_id}"
    created_sequence = _insert_event_tx(
        transaction,
        event_id=created_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dispatch_record_id,
            run_id,
            attempt_id,
            execution_id,
            serialize_dispatch_record_status(status),
            serialize_worker_kind(WorkerKind.LOCAL),
            "local-default",
            owner_host_instance_id,
            created_event_id,
            created_sequence,
            waiting_for_lane_at,
            lane_name,
            lane_claim_id,
            lane_owner_id,
            lane_acquired_at,
            dispatching_at,
            worker_accepted_at,
            worker_accept_event_id,
            worker_accept_event_sequence,
            cancelled_event_id,
            cancelled_event_sequence,
            _TIMESTAMP,
            _TIMESTAMP,
            cancelled_at,
        ),
    )


def _ensure_host_instance_tx(transaction: HostTransaction, *, host_instance_id: str) -> None:
    """写入测试用 Host instance row。

    :param transaction: Host transaction。
    :param host_instance_id: Host instance id。
    :returns: ``None``。
    """

    transaction.execute(
        """
        INSERT OR IGNORE INTO host_instances (
          host_instance_id,
          pid,
          process_start_token,
          boot_id,
          created_at,
          heartbeat_at,
          status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            host_instance_id,
            1,
            "process-start-token",
            None,
            _TIMESTAMP,
            _TIMESTAMP,
            "running",
        ),
    )
