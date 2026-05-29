"""Host durable EventLog 多进程 append smoke 测试。"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from multiprocessing import Process
from pathlib import Path

import pytest

from dayu.host.durable import event_log as event_log_module
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.errors import HostEventIdentityConflictError
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
_STRESS_PROCESS_COUNT = 8
_STRESS_ROUNDS = 20
_STRESS_START_DELAY_SECONDS = 0.2
_STRESS_WAIT_INTERVAL_SECONDS = 0.001
_STRESS_RESULT_SEPARATOR = ":"
_STRESS_RESULT_INSERTED = "inserted"
_STRESS_RESULT_CONFLICT = "conflict"
_STRESS_EVENT_ID_PREFIX = "event-stress"
_STRESS_RESULT_FILE_PREFIX = "worker"


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


def _fixed_event_request(event_id: str, payload_value: str) -> EventLogAppendRequest:
    """构造指定 event_id 的测试事件。

    :param event_id: EventLog event id。
    :param payload_value: inline payload 差异值。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-race",
        run_id="run-race",
        attempt_id=None,
        execution_id=None,
        event_type="host.race",
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, tzinfo=UTC),
        actor="host",
        source="race-test",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"value": payload_value},
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


def _same_event_id_stress_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    worker_index: int,
    round_count: int,
    start_at: float,
) -> None:
    """子进程 worker：真实并发写入同一批 ``event_id``。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 子进程结果目录文本。
    :param worker_index: worker 序号。
    :param round_count: 压测轮数。
    :param start_at: 基于 ``time.monotonic()`` 的统一启动时间。
    :returns: ``None``。
    :raises Exception: 非预期 durable 错误会向子进程外抛出，使父进程通过
        exit code 失败。
    """

    while time.monotonic() < start_at:
        time.sleep(_STRESS_WAIT_INTERVAL_SECONDS)

    options = _options(Path(db_path_text), Path(artifact_root_text))
    results: list[str] = []
    with open_host_durable_store(options) as store:
        for round_index in range(round_count):
            event_id = f"{_STRESS_EVENT_ID_PREFIX}-{round_index}"
            payload_value = f"worker-{worker_index}-round-{round_index}"

            def operation(transaction: HostTransaction) -> None:
                """追加当前压测轮次的同 ``event_id`` 异体事件。

                :param transaction: Host transaction。
                :returns: ``None``。
                """

                append_event(
                    transaction,
                    _fixed_event_request(event_id, payload_value),
                )

            try:
                store.transaction_runner.run_write(operation)
            except HostEventIdentityConflictError:
                result = _STRESS_RESULT_CONFLICT
            else:
                result = _STRESS_RESULT_INSERTED
            results.append(
                _STRESS_RESULT_SEPARATOR.join((str(round_index), result))
            )

    result_path = (
        Path(result_dir_text) / f"{_STRESS_RESULT_FILE_PREFIX}-{worker_index}.txt"
    )
    result_path.write_text("\n".join(results), encoding="utf-8")


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


def test_multiprocess_same_event_id_stress_classifies_conflicts(
    tmp_path: Path,
) -> None:
    """真实多进程并发写同 ``event_id`` 时每轮只允许一个成功写入。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 子进程失败、结果缺失或冲突分类不符合预期时抛出。
    """

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "stress-results"
    result_dir.mkdir()
    with open_host_durable_store(_options(db_path, artifact_root)):
        pass

    start_at = time.monotonic() + _STRESS_START_DELAY_SECONDS
    processes = tuple(
        Process(
            target=_same_event_id_stress_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                worker_index,
                _STRESS_ROUNDS,
                start_at,
            ),
        )
        for worker_index in range(_STRESS_PROCESS_COUNT)
    )
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0

    inserted_by_round = [0 for _ in range(_STRESS_ROUNDS)]
    conflict_by_round = [0 for _ in range(_STRESS_ROUNDS)]
    for worker_index in range(_STRESS_PROCESS_COUNT):
        result_path = (
            result_dir / f"{_STRESS_RESULT_FILE_PREFIX}-{worker_index}.txt"
        )
        result_lines = result_path.read_text(encoding="utf-8").splitlines()
        assert len(result_lines) == _STRESS_ROUNDS
        for line in result_lines:
            round_text, result = line.split(_STRESS_RESULT_SEPARATOR)
            round_index = int(round_text)
            if result == _STRESS_RESULT_INSERTED:
                inserted_by_round[round_index] += 1
            elif result == _STRESS_RESULT_CONFLICT:
                conflict_by_round[round_index] += 1
            else:
                raise AssertionError(f"unexpected stress result: {result}")

    for round_index in range(_STRESS_ROUNDS):
        assert inserted_by_round[round_index] == 1
        assert conflict_by_round[round_index] == _STRESS_PROCESS_COUNT - 1


def test_append_event_reclassifies_insert_unique_race_as_identity_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INSERT 阶段撞上同 event_id 异体 row 时返回领域冲突错误。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    original_read_event_by_id = event_log_module.read_event_by_id
    injected = False

    def racing_read_event_by_id(
        transaction: HostTransaction, event_id: str
    ) -> EventLogRow | None:
        """在首次读取后插入同 event_id 异体 row，模拟 read/insert 交错。

        :param transaction: Host transaction。
        :param event_id: EventLog event id。
        :returns: 首次返回 ``None``，后续走原始读取。
        """

        nonlocal injected
        if not injected:
            injected = True
            append_event(transaction, _fixed_event_request(event_id, "winner"))
            return None
        return original_read_event_by_id(transaction, event_id)

    monkeypatch.setattr(
        event_log_module,
        "read_event_by_id",
        racing_read_event_by_id,
    )
    with open_host_durable_store(_options(db_path, artifact_root)) as store:

        def operation(transaction: HostTransaction) -> None:
            """追加同 event_id 异体事件。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(transaction, _fixed_event_request("event-race", "loser"))

        with pytest.raises(HostEventIdentityConflictError):
            store.transaction_runner.run_write(operation)
