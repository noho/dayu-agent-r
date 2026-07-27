"""Host durable connection lifecycle 测试。"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import (
    HostDurableReadStore,
    _close_connection_best_effort,
    open_host_durable_read_store,
    open_host_durable_store,
)
from dayu.host.durable.errors import HostDurableConfigError, HostDurableError
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
from dayu.host.durable.transaction import (
    HostTransaction,
    configure_connection_pragmas,
    configure_read_only_connection_pragmas,
)

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


@pytest.mark.parametrize(
    "policy",
    (
        HostSQLiteStoragePolicy(),
        HostSQLiteStoragePolicy(busy_timeout_seconds=0.123),
    ),
)
def test_configure_read_only_pragmas_sets_only_read_contract(
    policy: HostSQLiteStoragePolicy,
) -> None:
    """只读 PRAGMA helper 必须设置 busy/foreign-key/query-only 且不切 WAL。"""

    connection = sqlite3.connect(":memory:")
    try:
        configure_read_only_connection_pragmas(connection, policy)
        expected_timeout_ms = int(policy.busy_timeout_seconds * 1000)
        assert connection.execute("PRAGMA busy_timeout").fetchall() == [(expected_timeout_ms,)]
        assert connection.execute("PRAGMA foreign_keys").fetchall() == [(1,)]
        assert connection.execute("PRAGMA query_only").fetchall() == [(1,)]
        assert connection.execute("PRAGMA journal_mode").fetchall() == [("memory",)]
        assert connection.execute("PRAGMA wal_autocheckpoint").fetchall() == [(1000,)]
    finally:
        connection.close()


def test_read_only_store_is_physical_ro_and_does_not_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只读 opener 不得调用写侧 PRAGMA/bootstrap，关闭 query_only 后仍不可写。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        store.transaction_runner.run_write(lambda transaction: _append_event(transaction, "event-read-only"))
    before_stat = options.db_path.stat()

    def reject_write_helper(
        connection: sqlite3.Connection,
        sqlite_policy: HostSQLiteStoragePolicy,
    ) -> None:
        """若只读 opener 错调写侧 helper 则立即失败。

        :param connection: SQLite connection。
        :param sqlite_policy: SQLite policy。
        :returns: 永不返回。
        :raises AssertionError: 始终抛出。
        """

        raise AssertionError("write helper must not be called")

    monkeypatch.setattr(
        "dayu.host.durable.connection.configure_connection_pragmas",
        reject_write_helper,
    )
    with open_host_durable_read_store(
        db_path=options.db_path,
        artifact_root=options.payload_policy.artifact_root,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.321,
            write_busy_retry_count=9,
            write_retry_initial_delay_seconds=9.0,
            write_retry_backoff_multiplier=9.0,
            write_retry_max_delay_seconds=9.0,
        ),
    ) as read_store:
        assert read_store.run_read(_count_event_log_rows) == 1

        def attempt_write(transaction: HostTransaction) -> None:
            """关闭 query_only 后尝试写入，证明底层 URI 仍是物理只读。

            :param transaction: 只读 transaction。
            :returns: ``None``。
            :raises sqlite3.Error: 物理只读 connection 拒绝写入时抛出。
            """

            transaction.execute("PRAGMA query_only=OFF")
            transaction.execute(
                f"DELETE FROM {TABLE_EVENT_LOG} WHERE event_id = ?",
                ("event-read-only",),
            )

        with pytest.raises(
            HostDurableError,
            match="read-only transaction failed",
        ):
            read_store.run_read(attempt_write)

    after_stat = options.db_path.stat()
    assert after_stat.st_size == before_stat.st_size
    assert _read_event_count_from_path(options.db_path) == 1


def test_read_only_store_missing_path_does_not_create_database(
    tmp_path: Path,
) -> None:
    """只读 opener 对缺失路径必须 fail closed 且不创建 DB 或 parent。"""

    db_path = (tmp_path / "missing" / "host.sqlite3").absolute()
    with pytest.raises(HostDurableError, match="must exist"):
        open_host_durable_read_store(
            db_path=db_path,
            artifact_root=(tmp_path / "artifacts").absolute(),
            sqlite_policy=HostSQLiteStoragePolicy(),
        )
    assert not db_path.exists()
    assert not db_path.parent.exists()


def test_read_only_store_rejects_invalid_paths_and_corrupt_database(
    tmp_path: Path,
) -> None:
    """只读 opener 必须拒绝相对路径、目录及既存损坏数据库。"""

    with pytest.raises(HostDurableConfigError, match="must be absolute"):
        open_host_durable_read_store(
            db_path=Path("relative.sqlite3"),
            artifact_root=tmp_path.absolute(),
            sqlite_policy=HostSQLiteStoragePolicy(),
        )

    with pytest.raises(HostDurableConfigError, match="regular file"):
        open_host_durable_read_store(
            db_path=tmp_path.absolute(),
            artifact_root=tmp_path.absolute(),
            sqlite_policy=HostSQLiteStoragePolicy(),
        )

    corrupt_path = (tmp_path / "corrupt.sqlite3").absolute()
    corrupt_path.write_bytes(b"not-a-sqlite-database")
    with pytest.raises(HostDurableError, match="read-only SQLite setup failed"):
        open_host_durable_read_store(
            db_path=corrupt_path,
            artifact_root=tmp_path.absolute(),
            sqlite_policy=HostSQLiteStoragePolicy(),
        )


def test_read_only_store_validates_lifecycle_and_non_sqlite_failures(
    tmp_path: Path,
) -> None:
    """只读 store 必须拒绝嵌套读取、透传业务异常并拒绝关闭后复用。"""

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    read_store = open_host_durable_read_store(
        db_path=options.db_path,
        artifact_root=options.payload_policy.artifact_root,
        sqlite_policy=HostSQLiteStoragePolicy(),
    )

    def nested_read(transaction: HostTransaction) -> int:
        """在活跃 read transaction 内发起第二次读取。

        :param transaction: 外层只读 transaction。
        :returns: 永不返回。
        :raises HostDurableError: 嵌套读取被只读 store 拒绝时抛出。
        """

        del transaction
        return read_store.run_read(_count_event_log_rows)

    with pytest.raises(HostDurableError, match="does not allow nesting"):
        read_store.run_read(nested_read)

    def raise_business_error(transaction: HostTransaction) -> int:
        """在只读 transaction 内模拟非 SQLite 业务异常。

        :param transaction: 当前只读 transaction。
        :returns: 永不返回。
        :raises RuntimeError: 始终抛出。
        """

        del transaction
        raise RuntimeError("read operation failed")

    with pytest.raises(RuntimeError, match="read operation failed"):
        read_store.run_read(raise_business_error)

    def close_during_read(transaction: HostTransaction) -> int:
        """在活跃 read transaction 内尝试关闭 store。

        :param transaction: 当前只读 transaction。
        :returns: 永不返回。
        :raises HostDurableError: 活跃读取期间关闭被拒绝时抛出。
        """

        del transaction
        read_store.close()
        return 0

    with pytest.raises(HostDurableError, match="active transaction"):
        read_store.run_read(close_during_read)

    read_store.close()
    read_store.close()
    with pytest.raises(HostDurableError, match="read store is closed"):
        read_store.run_read(_count_event_log_rows)


def test_read_only_store_constructor_rejects_invalid_types(tmp_path: Path) -> None:
    """只读 store 内部句柄必须在 owner boundary 拒绝错误参数类型。"""

    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(TypeError, match="db_path must be Path"):
            HostDurableReadStore(
                db_path=cast(Path, "invalid-db-path"),
                artifact_root=tmp_path.absolute(),
                connection=connection,
            )
        with pytest.raises(TypeError, match="artifact_root must be Path"):
            HostDurableReadStore(
                db_path=tmp_path.absolute(),
                artifact_root=cast(Path, "invalid-artifact-root"),
                connection=connection,
            )
        with pytest.raises(TypeError, match="connection must be sqlite3.Connection"):
            HostDurableReadStore(
                db_path=tmp_path.absolute(),
                artifact_root=tmp_path.absolute(),
                connection=cast(sqlite3.Connection, "invalid-connection"),
            )
    finally:
        connection.close()


def test_read_only_store_rejects_relative_artifact_root(tmp_path: Path) -> None:
    """只读 opener 必须拒绝相对 artifact root。"""

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    with pytest.raises(HostDurableConfigError, match="artifact_root must be absolute"):
        open_host_durable_read_store(
            db_path=options.db_path,
            artifact_root=Path("relative-artifacts"),
            sqlite_policy=HostSQLiteStoragePolicy(),
        )


def _read_event_count_from_path(db_path: Path) -> int:
    """使用独立 SQLite connection 读取 EventLog 行数。

    :param db_path: Host DB 路径。
    :returns: EventLog 行数。
    :raises sqlite3.Error: DB 无法打开或查询时抛出。
    :raises AssertionError: count row 类型错误时抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG}").fetchone()
        assert row is not None
        value = row[0]
        assert isinstance(value, int)
        return value
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
