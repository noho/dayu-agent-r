"""Host durable schema bootstrap 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostSchemaMismatchError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import (
    HOST_DURABLE_TABLES,
    HOST_SCHEMA_VERSION,
    PHASE3_STATE_TABLES,
    TABLE_EVENT_LOG,
    TABLE_HOST_INSTANCES,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
    bootstrap_host_durable_store,
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
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts"
        ),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=busy_timeout_seconds
        ),
    )


def _table_names(connection: sqlite3.Connection) -> frozenset[str]:
    """读取当前 SQLite DB 的用户表名集合。

    :param connection: SQLite connection。
    :returns: 用户表名集合。
    """

    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return frozenset(str(row[0]) for row in rows if str(row[0]) != "sqlite_sequence")


def _pragma_int(connection: sqlite3.Connection, sql: str) -> int:
    """读取单值 integer PRAGMA。

    :param connection: SQLite connection。
    :param sql: PRAGMA SQL。
    :returns: PRAGMA 返回的整数。
    :raises AssertionError: SQLite 未返回 row 时抛出。
    """

    row = connection.execute(sql).fetchone()
    assert row is not None
    return int(row[0])


def _pragma_text(connection: sqlite3.Connection, sql: str) -> str:
    """读取单值 text PRAGMA。

    :param connection: SQLite connection。
    :param sql: PRAGMA SQL。
    :returns: PRAGMA 返回的文本。
    :raises AssertionError: SQLite 未返回 row 时抛出。
    """

    row = connection.execute(sql).fetchone()
    assert row is not None
    return str(row[0])


def test_fresh_db_creates_foundation_and_phase5_tables(tmp_path: Path) -> None:
    """fresh DB bootstrap 创建 foundation 与 Phase 5 state tables 并设置 PRAGMA。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert _table_names(connection) == frozenset(HOST_DURABLE_TABLES)
            assert set(PHASE3_STATE_TABLES).issubset(_table_names(connection))
            assert _pragma_int(connection, "PRAGMA user_version") == 3
            assert HOST_SCHEMA_VERSION == 3
            assert _pragma_int(connection, "PRAGMA foreign_keys") == 1
            assert _pragma_text(connection, "PRAGMA journal_mode").lower() == "wal"
            assert _pragma_int(connection, "PRAGMA busy_timeout") == 250
        finally:
            connection.close()


def test_bootstrap_is_idempotent_for_matching_schema(tmp_path: Path) -> None:
    """匹配 schema version 的既有 DB bootstrap 可重复执行。"""

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert _table_names(connection) == frozenset(HOST_DURABLE_TABLES)
            assert _pragma_int(connection, "PRAGMA user_version") == HOST_SCHEMA_VERSION
        finally:
            connection.close()


def test_schema_mismatch_raises_structured_error(tmp_path: Path) -> None:
    """非当前 schema version 的 DB 不做兼容读取或迁移。"""

    db_path = tmp_path / "durable.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA user_version=1")
        connection.commit()
        with pytest.raises(HostSchemaMismatchError):
            bootstrap_host_durable_store(connection)
    finally:
        connection.close()


def test_wal_persists_on_second_independent_connection(tmp_path: Path) -> None:
    """第二条独立 connection 也能观察到 WAL journal mode。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        second_connection = store.connect()
        try:
            assert (
                _pragma_text(second_connection, "PRAGMA journal_mode").lower()
                == "wal"
            )
            assert _pragma_int(second_connection, "PRAGMA foreign_keys") == 1
        finally:
            second_connection.close()


def test_schema_constraints_are_explicit(tmp_path: Path) -> None:
    """foundation tables 包含计划要求的 PK、unique 与 FK 约束。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            event_columns = connection.execute(
                f"PRAGMA table_info({TABLE_EVENT_LOG})"
            ).fetchall()
            event_sequence = next(
                row for row in event_columns if str(row[1]) == "event_sequence"
            )
            assert str(event_sequence[2]).upper() == "INTEGER"
            assert int(event_sequence[5]) == 1

            create_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (TABLE_EVENT_LOG,),
            ).fetchone()
            assert create_sql_row is not None
            assert "AUTOINCREMENT" in str(create_sql_row[0]).upper()

            event_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_EVENT_LOG})"
            ).fetchall()
            assert any(int(row[2]) == 1 for row in event_indexes)

            event_fks = connection.execute(
                f"PRAGMA foreign_key_list({TABLE_EVENT_LOG})"
            ).fetchall()
            assert any(str(row[2]) == TABLE_PAYLOAD_DESCRIPTORS for row in event_fks)

            assert _primary_key_columns(connection, TABLE_IDEMPOTENCY_RECORDS) == (
                "scope_kind",
                "scope_id",
                "idempotency_key",
            )
            assert _primary_key_columns(connection, TABLE_PAYLOAD_DESCRIPTORS) == (
                "payload_ref",
            )
            assert _primary_key_columns(connection, TABLE_SQLITE_PAYLOADS) == (
                "payload_id",
            )
            assert _primary_key_columns(connection, TABLE_HOST_INSTANCES) == (
                "host_instance_id",
            )
        finally:
            connection.close()


def test_schema_does_not_create_future_phase_tables(tmp_path: Path) -> None:
    """Slice 1 bootstrap 不得预创建 Phase 3 之外的 future tables。"""

    forbidden_fragments = (
        "wait",
        "projection",
        "outbox",
        "memory",
        "purge",
    )
    options = _options(tmp_path)
    unexpected: set[str] = set()
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            table_names = _table_names(connection)
            unexpected = {
                table
                for table in table_names
                if any(fragment in table for fragment in forbidden_fragments)
            }
        finally:
            connection.close()
    assert not unexpected


def _primary_key_columns(
    connection: sqlite3.Connection, table_name: str
) -> tuple[str, ...]:
    """读取表的 primary key 列名顺序。

    :param connection: SQLite connection。
    :param table_name: 表名。
    :returns: primary key 列名元组。
    """

    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    pk_rows = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    return tuple(name for _position, name in pk_rows)
