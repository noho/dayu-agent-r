"""Host durable transaction runner 与 codec 测试。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timezone, timedelta
from pathlib import Path

import pytest

from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    parse_utc_timestamp,
    sha256_digest_bytes,
    sha256_digest_json,
)
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import (
    HostAfterCommitError,
    HostDurableError,
    HostForeignKeyError,
    HostSchemaMismatchError,
    HostTransactionRetryExhaustedError,
    HostUniqueConstraintError,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner


def _options(
    tmp_path: Path,
    *,
    busy_timeout_seconds: float = 0.01,
    retry_count: int = 2,
) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :param busy_timeout_seconds: SQLite busy timeout 秒数。
    :param retry_count: busy / locked 额外重试次数。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts"
        ),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=busy_timeout_seconds,
            write_busy_retry_count=retry_count,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.0,
            write_retry_max_delay_seconds=0.001,
        ),
    )


def _create_notes_table(connection: sqlite3.Connection) -> None:
    """创建 transaction 测试用表。

    :param connection: SQLite connection。
    :returns: ``None``。
    """

    connection.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
    connection.commit()


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    """读取指定表的 row count。

    :param connection: SQLite connection。
    :param table_name: 表名。
    :returns: row count。
    :raises AssertionError: SQLite 未返回 count row 时抛出。
    """

    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    assert row is not None
    return int(row[0])


def test_successful_transaction_commits_then_runs_after_commit(
    tmp_path: Path,
) -> None:
    """成功 transaction 先 commit durable row，再执行 after-commit callback。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            _create_notes_table(setup_connection)
        finally:
            setup_connection.close()
        callback_events: list[str] = []

        def operation(transaction: HostTransaction) -> str:
            """写入测试 row。

            :param transaction: Host transaction。
            :returns: 写入结果标记。
            """

            transaction.execute(
                "INSERT INTO notes (id, body) VALUES (?, ?)",
                ("n1", "hello"),
            )
            return "done"

        def after_commit() -> None:
            """记录 after-commit 已执行。

            :returns: ``None``。
            """

            callback_events.append("after")

        assert store.transaction_runner.run_write(
            operation, after_commit=(after_commit,)
        ) == "done"
        assert callback_events == ["after"]
        check_connection = store.connect()
        try:
            assert _count_rows(check_connection, "notes") == 1
        finally:
            check_connection.close()


def test_transaction_body_exception_rolls_back_without_after_commit(
    tmp_path: Path,
) -> None:
    """transaction body 失败会 rollback 且不触发 after-commit。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            _create_notes_table(setup_connection)
        finally:
            setup_connection.close()
        callback_events: list[str] = []

        def operation(transaction: HostTransaction) -> str:
            """写入后主动失败。

            :param transaction: Host transaction。
            :returns: 永不返回。
            :raises RuntimeError: 始终抛出，用于验证 rollback。
            """

            transaction.execute(
                "INSERT INTO notes (id, body) VALUES (?, ?)",
                ("n1", "hello"),
            )
            raise RuntimeError("boom")

        def after_commit() -> None:
            """记录 after-commit 误触发。

            :returns: ``None``。
            """

            callback_events.append("after")

        with pytest.raises(RuntimeError):
            store.transaction_runner.run_write(
                operation, after_commit=(after_commit,)
            )
        assert callback_events == []
        check_connection = store.connect()
        try:
            assert _count_rows(check_connection, "notes") == 0
        finally:
            check_connection.close()


def test_after_commit_failure_preserves_durable_commit(tmp_path: Path) -> None:
    """after-commit 失败只影响调用结果，不回滚已提交 durable row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            _create_notes_table(setup_connection)
        finally:
            setup_connection.close()

        def operation(transaction: HostTransaction) -> None:
            """写入 durable row。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                "INSERT INTO notes (id, body) VALUES (?, ?)",
                ("n1", "hello"),
            )

        def failing_after_commit() -> None:
            """模拟 wakeup callback 失败。

            :returns: ``None``。
            :raises RuntimeError: 始终抛出。
            """

            raise RuntimeError("callback failed")

        with pytest.raises(HostAfterCommitError) as error_info:
            store.transaction_runner.run_write(
                operation, after_commit=(failing_after_commit,)
            )
        assert error_info.value.callback_index == 0
        check_connection = store.connect()
        try:
            assert _count_rows(check_connection, "notes") == 1
        finally:
            check_connection.close()


def test_busy_locked_retries_are_finite_and_do_not_run_after_commit(
    tmp_path: Path,
) -> None:
    """busy / locked 只有限重试，失败时不执行 transaction body 或 callback。"""

    options = _options(tmp_path, busy_timeout_seconds=0.001, retry_count=2)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            _create_notes_table(setup_connection)
        finally:
            setup_connection.close()
        lock_connection = store.connect()
        callback_events: list[str] = []
        operation_calls: list[str] = []

        def operation(transaction: HostTransaction) -> None:
            """记录不应被执行的 transaction body。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            operation_calls.append("called")
            transaction.execute(
                "INSERT INTO notes (id, body) VALUES (?, ?)",
                ("n1", "hello"),
            )

        def after_commit() -> None:
            """记录不应被执行的 after-commit callback。

            :returns: ``None``。
            """

            callback_events.append("after")

        try:
            lock_connection.execute("BEGIN IMMEDIATE")
            with pytest.raises(HostTransactionRetryExhaustedError) as error_info:
                store.transaction_runner.run_write(
                    operation, after_commit=(after_commit,)
                )
            assert error_info.value.attempts == 3
        finally:
            lock_connection.execute("ROLLBACK")
            lock_connection.close()
        assert operation_calls == []
        assert callback_events == []


def test_unique_and_foreign_key_errors_are_not_retried(tmp_path: Path) -> None:
    """constraint failure 会结构化抛出且不进入 busy retry。"""

    options = _options(tmp_path, retry_count=5)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            setup_connection.execute("CREATE TABLE parents (id TEXT PRIMARY KEY)")
            setup_connection.execute(
                "CREATE TABLE children ("
                "id TEXT PRIMARY KEY, "
                "parent_id TEXT NOT NULL REFERENCES parents(id)"
                ")"
            )
            setup_connection.execute("INSERT INTO parents (id) VALUES ('p1')")
            setup_connection.commit()
        finally:
            setup_connection.close()

        unique_calls: list[str] = []
        foreign_key_calls: list[str] = []

        def duplicate_parent(transaction: HostTransaction) -> None:
            """触发 unique constraint。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            unique_calls.append("called")
            transaction.execute("INSERT INTO parents (id) VALUES (?)", ("p1",))

        def missing_parent(transaction: HostTransaction) -> None:
            """触发 foreign-key constraint。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            foreign_key_calls.append("called")
            transaction.execute(
                "INSERT INTO children (id, parent_id) VALUES (?, ?)",
                ("c1", "missing"),
            )

        with pytest.raises(HostUniqueConstraintError):
            store.transaction_runner.run_write(duplicate_parent)
        with pytest.raises(HostForeignKeyError):
            store.transaction_runner.run_write(missing_parent)
        assert unique_calls == ["called"]
        assert foreign_key_calls == ["called"]


def test_check_constraint_error_is_classified_explicitly(tmp_path: Path) -> None:
    """CHECK constraint failure 会保留明确诊断消息。"""

    options = _options(tmp_path, retry_count=5)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            setup_connection.execute(
                "CREATE TABLE statuses ("
                "id TEXT PRIMARY KEY, "
                "status TEXT NOT NULL CHECK(status IN ('running'))"
                ")"
            )
            setup_connection.commit()
        finally:
            setup_connection.close()
        calls: list[str] = []

        def invalid_status(transaction: HostTransaction) -> None:
            """触发 CHECK constraint。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            calls.append("called")
            transaction.execute(
                "INSERT INTO statuses (id, status) VALUES (?, ?)",
                ("s1", "stopped"),
            )

        with pytest.raises(HostDurableError) as error_info:
            store.transaction_runner.run_write(invalid_status)
        assert str(error_info.value) == "Host durable CHECK constraint failed"
        assert calls == ["called"]


def test_schema_and_domain_errors_are_not_retried(tmp_path: Path) -> None:
    """schema / domain 结构化错误不被当成 busy / locked retry。"""

    options = _options(tmp_path, retry_count=5)
    with open_host_durable_store(options) as store:
        missing_table_calls: list[str] = []
        schema_mismatch_calls: list[str] = []

        def missing_table(transaction: HostTransaction) -> None:
            """触发 SQLite schema 类错误。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            missing_table_calls.append("called")
            transaction.execute("INSERT INTO missing_table (id) VALUES (?)", ("x",))

        def schema_mismatch(transaction: HostTransaction) -> None:
            """触发 durable schema mismatch domain error。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostSchemaMismatchError: 始终抛出。
            """

            schema_mismatch_calls.append("called")
            raise HostSchemaMismatchError("bad schema")

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(missing_table)
        with pytest.raises(HostSchemaMismatchError):
            store.transaction_runner.run_write(schema_mismatch)
        assert missing_table_calls == ["called"]
        assert schema_mismatch_calls == ["called"]


def test_host_transaction_fetch_helpers_return_typed_rows(tmp_path: Path) -> None:
    """HostTransaction 查询 helper 返回 HostRow typed view。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        setup_connection = store.connect()
        try:
            _create_notes_table(setup_connection)
        finally:
            setup_connection.close()

        def operation(transaction: HostTransaction) -> tuple[str, str, int]:
            """写入并读取测试 row。

            :param transaction: Host transaction。
            :returns: 单行值、列名与总行数。
            """

            execute_result = transaction.execute(
                "INSERT INTO notes (id, body) VALUES (?, ?)",
                ("n1", "hello"),
            )
            row = transaction.fetchone(
                "SELECT id, body FROM notes WHERE id = ?",
                ("n1",),
            )
            rows = transaction.fetchall("SELECT id FROM notes")
            assert row is not None
            assert execute_result.rowcount == 1
            return str(row.get("body")), row.columns[0], len(rows)

        assert store.transaction_runner.run_write(operation) == ("hello", "id", 1)


def test_codec_canonical_json_timestamp_and_digest() -> None:
    """codec helper 满足 deterministic JSON、UTC timestamp 与 digest 约束。"""

    left = {"b": 2, "a": [1, {"c": None}]}
    right = {"a": [1, {"c": None}], "b": 2}
    assert canonical_json_dumps(left) == canonical_json_dumps(right)
    assert canonical_json_dumps(left) == '{"a":[1,{"c":null}],"b":2}'
    with pytest.raises(ValueError):
        canonical_json_dumps({"bad": float("inf")})

    local_time = datetime(
        2026,
        5,
        14,
        9,
        2,
        3,
        123456,
        tzinfo=timezone(timedelta(hours=8)),
    )
    formatted = format_utc_timestamp(local_time)
    assert formatted == "2026-05-14T01:02:03.123456Z"
    assert parse_utc_timestamp(formatted) == datetime(
        2026, 5, 14, 1, 2, 3, 123456, tzinfo=UTC
    )
    with pytest.raises(ValueError):
        parse_utc_timestamp("2026-05-14T01:02:03Z")
    with pytest.raises(ValueError):
        parse_utc_timestamp("2026-05-14T01:02:03.123Z")
    with pytest.raises(ValueError):
        parse_utc_timestamp("2026-05-14T09:02:03.123456+08:00")
    with pytest.raises(ValueError):
        format_utc_timestamp(datetime(2026, 5, 14, 1, 2, 3, 123456))

    assert sha256_digest_bytes(b"abc") == (
        "sha256:ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert sha256_digest_json(right) == sha256_digest_json(left)


def test_runner_can_be_constructed_with_independent_connection(
    tmp_path: Path,
) -> None:
    """HostTransactionRunner 可绑定独立 connection 运行短写事务。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            _create_notes_table(connection)
            runner = HostTransactionRunner(connection, options.sqlite_policy)

            def operation(transaction: HostTransaction) -> None:
                """写入测试 row。

                :param transaction: Host transaction。
                :returns: ``None``。
                """

                transaction.execute(
                    "INSERT INTO notes (id, body) VALUES (?, ?)",
                    ("n1", "hello"),
                )

            runner.run_write(operation)
            assert _count_rows(connection, "notes") == 1
        finally:
            connection.close()
