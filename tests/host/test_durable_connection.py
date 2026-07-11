"""Host durable connection lifecycle 测试。"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import _close_connection_best_effort
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.maintenance import (
    HostWalCheckpointMode,
    run_host_wal_checkpoint,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransaction, configure_connection_pragmas

_USER_INPUT_ACCEPTED_TYPE = "USER_INPUT_ACCEPTED"
_TEST_ACTOR = "durable-test"
_TEST_SOURCE = "durable-test"
_COUNT_COLUMN = "event_count"
_ORIGINAL_PATH_STAT = Path.stat


class _FailingCloseConnection(sqlite3.Connection):
    """用于模拟 close 失败的 SQLite connection。"""

    def close(self) -> None:
        """模拟初始化失败清理阶段的 close 异常。

        :returns: 永不返回。
        :raises sqlite3.OperationalError: 始终抛出。
        """

        raise sqlite3.OperationalError("close failed")


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    :raises ValueError: option dataclass 校验失败时由构造函数抛出。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _event_request(event_id: str) -> EventLogAppendRequest:
    """构造测试用 EventLog append 请求。

    :param event_id: 全局事件标识。
    :returns: EventLog append 请求。
    :raises ValueError: datetime 构造失败时由标准库抛出。
    """

    payload: JsonValue = {"event_id": event_id}
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-wal",
        run_id="run-wal",
        attempt_id=None,
        execution_id=None,
        event_type=_USER_INPUT_ACCEPTED_TYPE,
        occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
        actor=_TEST_ACTOR,
        source=_TEST_SOURCE,
        client_request_id=event_id,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _append_event(transaction: HostTransaction, event_id: str) -> None:
    """在当前 transaction 内追加测试 EventLog row。

    :param transaction: Host durable transaction。
    :param event_id: 全局事件标识。
    :returns: ``None``。
    :raises HostDurableError: EventLog append 失败时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    EventLogStore().append_event(transaction, _event_request(event_id))


def _count_event_log_rows(transaction: HostTransaction) -> int:
    """统计当前 transaction 可见的 EventLog row 数量。

    :param transaction: Host durable transaction。
    :returns: 当前可见 EventLog row 数量。
    :raises AssertionError: SQLite 未返回 count row 时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    row = transaction.fetchone(
        f"SELECT COUNT(*) AS {_COUNT_COLUMN} FROM {TABLE_EVENT_LOG}"
    )
    assert row is not None
    count_value = row.get(_COUNT_COLUMN)
    assert isinstance(count_value, int)
    return count_value


def test_close_connection_best_effort_suppresses_close_failure() -> None:
    """初始化失败清理时 close 失败不能掩盖原始初始化错误。"""

    connection = sqlite3.connect(":memory:", factory=_FailingCloseConnection)
    try:
        _close_connection_best_effort(connection)
    finally:
        sqlite3.Connection.close(connection)


def test_configure_connection_pragmas_sets_wal_autocheckpoint() -> None:
    """SQLite 连接初始化必须显式启用 WAL auto-checkpoint 管理。"""

    connection = sqlite3.connect(":memory:")
    try:
        configure_connection_pragmas(connection, HostSQLiteStoragePolicy())
        rows = connection.execute("PRAGMA wal_autocheckpoint").fetchall()
        assert rows == [(256,)]
    finally:
        connection.close()


def test_wal_checkpoint_passive_result_fields_are_observable(
    tmp_path: Path,
) -> None:
    """PASSIVE WAL checkpoint 必须返回可观测诊断字段。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def append_event(transaction: HostTransaction) -> None:
            """写入用于生成 WAL 诊断的测试 EventLog row。

            :param transaction: Host durable transaction。
            :returns: ``None``。
            """

            _append_event(transaction, "event-wal-fields")

        store.transaction_runner.run_write(append_event)
        connection = store.connect()
        try:
            result = run_host_wal_checkpoint(connection, db_path=options.db_path)
            assert result.mode is HostWalCheckpointMode.PASSIVE
            assert result.busy_pages >= 0
            assert result.log_pages >= 0
            assert result.checkpointed_pages >= 0
            assert result.wal_size_bytes >= 0
        finally:
            connection.close()


def test_wal_checkpoint_rejects_mismatched_connection_and_db_path(
    tmp_path: Path,
) -> None:
    """WAL checkpoint 必须拒绝 connection 与 db_path 不同源的调用。"""

    first_options = _options(tmp_path / "first")
    second_options = _options(tmp_path / "second")
    with open_host_durable_store(first_options) as first_store:
        with open_host_durable_store(second_options):
            connection = first_store.connect()
            try:
                with pytest.raises(
                    HostDurableError,
                    match="Host durable WAL checkpoint connection does not match db_path",
                ):
                    run_host_wal_checkpoint(
                        connection,
                        db_path=second_options.db_path,
                    )
            finally:
                connection.close()


def test_wal_checkpoint_closed_connection_failure_is_structured(
    tmp_path: Path,
) -> None:
    """已关闭 connection 上执行 checkpoint 必须转为 Host durable 结构化错误。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        connection.close()

        with pytest.raises(
            HostDurableError,
            match="Host durable WAL checkpoint failed to inspect connection database",
        ):
            run_host_wal_checkpoint(connection, db_path=options.db_path)


def test_wal_checkpoint_wal_size_stat_failure_has_precise_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WAL 文件 stat 失败必须返回精确诊断消息。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        wal_file_name = options.db_path.name + "-wal"

        def fail_wal_stat(
            path: Path,
            *,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            """只让目标 WAL 文件 stat 失败。

            :param path: 被读取 metadata 的路径。
            :param follow_symlinks: 是否跟随符号链接。
            :returns: 非目标路径的真实 stat 结果。
            :raises PermissionError: 目标 WAL 文件 stat 始终失败。
            :raises OSError: 非目标路径真实 stat 失败时由标准库抛出。
            """

            if path.name == wal_file_name:
                raise PermissionError("wal stat denied")
            return _ORIGINAL_PATH_STAT(path, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(Path, "stat", fail_wal_stat)
        try:
            with pytest.raises(
                HostDurableError,
                match="Host durable WAL checkpoint failed to read WAL file size",
            ):
                run_host_wal_checkpoint(connection, db_path=options.db_path)
        finally:
            connection.close()


def test_wal_checkpoint_diagnostic_does_not_change_event_log_truth(
    tmp_path: Path,
) -> None:
    """WAL checkpoint 诊断不能改变 EventLog committed truth。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def append_before_checkpoint(transaction: HostTransaction) -> None:
            """checkpoint 前写入 committed EventLog row。

            :param transaction: Host durable transaction。
            :returns: ``None``。
            """

            _append_event(transaction, "event-before-checkpoint")

        def append_after_checkpoint(transaction: HostTransaction) -> None:
            """checkpoint 后写入 committed EventLog row。

            :param transaction: Host durable transaction。
            :returns: ``None``。
            """

            _append_event(transaction, "event-after-checkpoint")

        store.transaction_runner.run_write(append_before_checkpoint)
        assert store.transaction_runner.run_read(_count_event_log_rows) == 1

        connection = store.connect()
        try:
            result = run_host_wal_checkpoint(
                connection,
                db_path=options.db_path,
                mode=HostWalCheckpointMode.PASSIVE,
            )
            assert result.mode is HostWalCheckpointMode.PASSIVE
        finally:
            connection.close()

        assert store.transaction_runner.run_read(_count_event_log_rows) == 1
        store.transaction_runner.run_write(append_after_checkpoint)
        assert store.transaction_runner.run_read(_count_event_log_rows) == 2
