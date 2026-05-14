"""Host durable EventLog 多进程 append smoke 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from multiprocessing import Process
from pathlib import Path

from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransaction

_PROCESS_COUNT = 4
_EVENTS_PER_PROCESS = 12
_EXPECTED_TOTAL_EVENTS = _PROCESS_COUNT * _EVENTS_PER_PROCESS


def _options(db_path: Path, artifact_root: Path) -> HostDurableStoreOptions:
    """构造多进程测试用 Host durable store options。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=1.0,
            write_busy_retry_count=20,
            write_retry_initial_delay_seconds=0.005,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.02,
        ),
    )


def _request(worker_index: int, event_index: int) -> EventLogAppendRequest:
    """构造多进程 append 请求。

    :param worker_index: worker 序号。
    :param event_index: worker 内事件序号。
    :returns: EventLog append 请求。
    """

    event_id = f"event-{worker_index}-{event_index}"
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=f"session-{worker_index}",
        run_id=f"run-{worker_index}",
        attempt_id=None,
        execution_id=None,
        event_type="host.multiprocess",
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, event_index, tzinfo=UTC),
        actor="host",
        source="multiprocess-test",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"worker": worker_index, "event": event_index},
        payload_ref=None,
        payload_digest=None,
    )


def _append_worker(
    db_path_text: str,
    artifact_root_text: str,
    worker_index: int,
    event_count: int,
) -> None:
    """子进程 worker：打开独立 connection 并追加事件。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param worker_index: worker 序号。
    :param event_count: 追加事件数量。
    :returns: ``None``。
    """

    options = _options(Path(db_path_text), Path(artifact_root_text))
    with open_host_durable_store(options) as store:
        for event_index in range(event_count):

            def operation(transaction: HostTransaction) -> None:
                """追加 worker 当前事件。

                :param transaction: Host transaction。
                :returns: ``None``。
                """

                append_event(transaction, _request(worker_index, event_index))

            store.transaction_runner.run_write(operation)


def test_multiprocess_append_allocates_unique_global_sequences(
    tmp_path: Path,
) -> None:
    """多进程 append 后 row count 正确且 event_sequence 全局唯一递增。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    with open_host_durable_store(_options(db_path, artifact_root)):
        pass

    processes = tuple(
        Process(
            target=_append_worker,
            args=(
                str(db_path),
                str(artifact_root),
                worker_index,
                _EVENTS_PER_PROCESS,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0

    rows: list[tuple[int, str]] = []
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        connection = store.connect()
        try:
            rows = connection.execute(
                f"""
                SELECT event_sequence, event_id
                FROM {TABLE_EVENT_LOG}
                ORDER BY event_sequence ASC
                """
            ).fetchall()
        finally:
            connection.close()

    sequences = tuple(int(row[0]) for row in rows)
    event_ids = tuple(str(row[1]) for row in rows)
    assert len(rows) == _EXPECTED_TOTAL_EVENTS
    assert len(frozenset(sequences)) == _EXPECTED_TOTAL_EVENTS
    assert len(frozenset(event_ids)) == _EXPECTED_TOTAL_EVENTS
    assert sequences == tuple(sorted(sequences))
