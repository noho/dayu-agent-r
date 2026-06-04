"""Host durable schema bootstrap 测试。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

import dayu.host.durable.schema as durable_schema
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostSchemaMismatchError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import (
    AUDIT_PROJECTION_TABLES,
    HOST_DURABLE_DDL,
    HOST_DURABLE_INDEXES,
    HOST_DURABLE_TABLES,
    HOST_SCHEMA_VERSION,
    INDEX_EVENT_LOG_SESSION_SEQUENCE,
    INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE,
    INDEX_HOST_INSTANCES_STATUS_HEARTBEAT,
    INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
    INDEX_HOST_OUTBOX_TERMINAL_ITEMS_RUN,
    INDEX_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE,
    INDEX_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE,
    INDEX_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF,
    INDEX_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST,
    INDEX_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE,
    INDEX_HOST_TOOL_TRACE_HOT_TOOL_CALL,
    INDEX_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE,
    MEMORY_PROJECTION_TABLES,
    OUTBOX_PROJECTION_TABLES,
    PHASE3_STATE_TABLES,
    PROJECTION_TABLES,
    PURGE_GOVERNANCE_TABLES,
    TOOL_TRACE_PROJECTION_TABLES,
    INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON,
    INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE,
    INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR,
    INDEX_HOST_PURGE_TOMBSTONES_SESSION,
    INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE,
    INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE,
    INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE,
    TABLE_EVENT_LOG,
    TABLE_HOST_AUDIT_SINK_MARKERS,
    TABLE_HOST_INSTANCES,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_PURGE_TOMBSTONES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
    TABLE_HOST_TOOL_TRACE_HOT,
    TABLE_HOST_WAIT_RECORDS,
    INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL,
    INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB,
    INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
    bootstrap_host_durable_store,
)

_CREATE_INDEX_NAME_PATTERN = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)",
    re.IGNORECASE,
)
"""从 Host durable DDL 中抽取 index 名称的测试正则。"""

_CREATE_TABLE_NAME_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)",
    re.IGNORECASE,
)
"""从 Host durable DDL 中抽取 table 名称的测试正则。"""

_SQLITE_OBJECT_TYPE_INDEX = "index"
"""SQLite catalog 中 index object type 名称。"""

_SQLITE_OBJECT_TYPE_TABLE = "table"
"""SQLite catalog 中 table object type 名称。"""


def _ddl_table_names(statements: tuple[str, ...]) -> frozenset[str]:
    """从 DDL 语句中抽取 ``CREATE TABLE`` 表名集合。

    :param statements: DDL 语句序列。
    :returns: DDL 中声明的 table 名称集合。
    :raises AssertionError: 本 helper 不主动抛出；调用方负责断言集合语义。
    """

    return frozenset(
        match.group(1)
        for statement in statements
        for match in _CREATE_TABLE_NAME_PATTERN.finditer(statement)
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


def _table_names(connection: sqlite3.Connection) -> frozenset[str]:
    """读取当前 SQLite DB 的用户表名集合。

    :param connection: SQLite connection。
    :returns: 用户表名集合。
    """

    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
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


def _index_exists(connection: sqlite3.Connection, index_name: str) -> bool:
    """判断 SQLite index 是否存在。

    :param connection: SQLite connection。
    :param index_name: 目标 index 名称。
    :returns: 存在则返回 ``True``。
    """

    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name = ?",
        (index_name,),
    ).fetchone()
    return row is not None


def _schema_sql(connection: sqlite3.Connection, object_type: str, object_name: str) -> str:
    """读取 SQLite catalog 中指定 object 的 SQL 定义。

    :param connection: SQLite connection。
    :param object_type: SQLite object type。
    :param object_name: SQLite object name。
    :returns: SQLite catalog SQL。
    :raises AssertionError: 指定 object 不存在或 catalog SQL 为空时抛出。
    """

    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, object_name),
    ).fetchone()
    assert row is not None
    assert row[0] is not None
    return str(row[0])


def _schema_sql_from_db_path(db_path: Path, object_type: str, object_name: str) -> str:
    """从 SQLite DB 文件读取指定 object 的 SQL 定义。

    :param db_path: SQLite DB 文件路径。
    :param object_type: SQLite object type。
    :param object_name: SQLite object name。
    :returns: SQLite catalog SQL。
    :raises AssertionError: 指定 object 不存在或 catalog SQL 为空时抛出。
    :raises sqlite3.Error: 打开 DB 或读取 catalog 失败时由 SQLite 抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        return _schema_sql(connection, object_type, object_name)
    finally:
        connection.close()


def _mutate_schema_sql(
    db_path: Path,
    *,
    object_type: str,
    object_name: str,
    mutated_sql: str,
) -> None:
    """直接篡改 SQLite catalog 中指定 object 的 SQL 定义。

    :param db_path: SQLite DB 文件路径。
    :param object_type: SQLite object type。
    :param object_name: SQLite object name。
    :param mutated_sql: 写入 ``sqlite_master.sql`` 的变异 SQL。
    :returns: ``None``。
    :raises sqlite3.Error: 打开 DB 或更新 catalog 失败时由 SQLite 抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql = ? WHERE type = ? AND name = ?",
            (mutated_sql, object_type, object_name),
        )
        connection.execute("PRAGMA writable_schema=OFF")
        connection.commit()
    finally:
        connection.close()


def _replace_index_with_wrong_definition(db_path: Path, index_name: str) -> None:
    """用同名但定义错误的 index 替换 required index。

    :param db_path: SQLite DB 文件路径。
    :param index_name: 目标 index 名称。
    :returns: ``None``。
    :raises sqlite3.Error: 打开 DB 或执行 DDL 失败时由 SQLite 抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(f"DROP INDEX {index_name}")
        connection.execute(
            f"CREATE INDEX {index_name} ON {TABLE_HOST_RUNS}(session_id)"
        )
        connection.commit()
    finally:
        connection.close()


def _drop_table(db_path: Path, table_name: str) -> None:
    """从测试 DB 中删除指定 table。

    :param db_path: SQLite DB 文件路径。
    :param table_name: 目标 table 名称。
    :returns: ``None``。
    :raises sqlite3.Error: 打开 DB 或执行 DDL 失败时由 SQLite 抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(f"DROP TABLE {table_name}")
        connection.commit()
    finally:
        connection.close()


def _drop_index(db_path: Path, index_name: str) -> None:
    """从测试 DB 中删除指定 index。

    :param db_path: SQLite DB 文件路径。
    :param index_name: 目标 index 名称。
    :returns: ``None``。
    :raises sqlite3.Error: 打开 DB 或执行 DDL 失败时由 SQLite 抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(f"DROP INDEX {index_name}")
        connection.commit()
    finally:
        connection.close()


def _insert_event_log_probe(connection: sqlite3.Connection, event_id: str) -> None:
    """插入 schema 约束测试用 EventLog row。

    :param connection: SQLite connection。
    :param event_id: EventLog id。
    :returns: 无。
    :raises sqlite3.Error: 插入失败时由 SQLite 抛出。
    """

    connection.execute(
        f"""
        INSERT INTO {TABLE_EVENT_LOG} (
          event_id,
          event_body_digest,
          event_class,
          session_id,
          event_type,
          occurred_at,
          payload_json,
          appended_at
        ) VALUES (
          ?,
          'digest',
          'canonical_fact',
          'session-1',
          'TYPE_A',
          '2026-05-16T00:00:00.000000Z',
          '{{}}',
          '2026-05-16T00:00:00.000000Z'
        )
        """,
        (event_id,),
    )


def _insert_payload_descriptor_probe(connection: sqlite3.Connection, payload_ref: str) -> None:
    """插入 schema 约束测试用 payload descriptor row。

    :param connection: SQLite connection。
    :param payload_ref: payload descriptor 引用。
    :returns: 无。
    :raises sqlite3.Error: 插入失败时由 SQLite 抛出。
    """

    connection.execute(f"""
        INSERT INTO {TABLE_SQLITE_PAYLOADS} (
          payload_id,
          payload_format,
          payload_json,
          payload_size_bytes,
          payload_digest,
          created_at
        ) VALUES (
          'payload-1',
          'canonical_json',
          '{{}}',
          2,
          'sha256:0000000000000000000000000000000000000000000000000000000000000000',
          '2026-05-16T00:00:00.000000Z'
        )
        """)
    connection.execute(
        f"""
        INSERT INTO {TABLE_PAYLOAD_DESCRIPTORS} (
          payload_ref,
          payload_kind,
          payload_digest,
          payload_size_bytes,
          sqlite_payload_id,
          metadata_json,
          created_at
        ) VALUES (
          ?,
          'sqlite_payload',
          'sha256:0000000000000000000000000000000000000000000000000000000000000000',
          2,
          'payload-1',
          '{{}}',
          '2026-05-16T00:00:00.000000Z'
        )
        """,
        (payload_ref,),
    )


def test_fresh_db_creates_foundation_phase8_and_memory_tables(
    tmp_path: Path,
) -> None:
    """fresh DB bootstrap 创建全部 Host durable tables。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert _table_names(connection) == frozenset(HOST_DURABLE_TABLES)
            assert set(PHASE3_STATE_TABLES).issubset(_table_names(connection))
            assert set(PROJECTION_TABLES).issubset(_table_names(connection))
            assert set(MEMORY_PROJECTION_TABLES).issubset(_table_names(connection))
            assert set(AUDIT_PROJECTION_TABLES).issubset(_table_names(connection))
            assert set(TOOL_TRACE_PROJECTION_TABLES).issubset(_table_names(connection))
            assert set(OUTBOX_PROJECTION_TABLES).issubset(_table_names(connection))
            assert set(PURGE_GOVERNANCE_TABLES).issubset(_table_names(connection))
            assert _pragma_int(connection, "PRAGMA user_version") == (HOST_SCHEMA_VERSION)
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


def test_fresh_bootstrap_rolls_back_when_ddl_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fresh DDL 中途失败时不留下 partial user tables 或 current version。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: rollback 后残留用户表或 current version 时抛出。
    """

    db_path = tmp_path / "durable.sqlite3"
    broken_ddl = (
        HOST_DURABLE_DDL[0],
        "CREATE TABLE broken_schema_probe (",
        HOST_DURABLE_DDL[1],
    )
    monkeypatch.setattr(durable_schema, "HOST_DURABLE_DDL", broken_ddl)

    connection = sqlite3.connect(db_path, isolation_level=None)
    try:
        with pytest.raises(sqlite3.Error):
            bootstrap_host_durable_store(connection)
        assert _table_names(connection) == frozenset()
        assert _pragma_int(connection, "PRAGMA user_version") == 0
    finally:
        connection.close()


def test_current_schema_missing_table_opener_raises_without_repair(
    tmp_path: Path,
) -> None:
    """current user_version 缺 required table 时 opener fail closed 且不建表。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: opener 未抛错或静默创建缺失表时抛出。
    """

    options = _options(tmp_path)
    options.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(options.db_path)
    try:
        connection.execute(f"PRAGMA user_version={HOST_SCHEMA_VERSION}")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        HostSchemaMismatchError,
        match="missing required objects",
    ) as exc_info:
        open_host_durable_store(options)
    error_message = str(exc_info.value)
    assert f"tables: {TABLE_EVENT_LOG}" in error_message
    assert INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE in error_message

    verify_connection = sqlite3.connect(options.db_path)
    try:
        assert TABLE_EVENT_LOG not in _table_names(verify_connection)
    finally:
        verify_connection.close()


def test_current_schema_missing_index_opener_raises_without_repair(
    tmp_path: Path,
) -> None:
    """current user_version 缺 required index 时 opener fail closed 且不重建索引。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: opener 未抛错或静默重建缺失索引时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    _drop_index(options.db_path, INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE)

    with pytest.raises(
        HostSchemaMismatchError,
        match=f"missing required index: {INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}",
    ):
        open_host_durable_store(options)

    verify_connection = sqlite3.connect(options.db_path)
    try:
        assert not _index_exists(verify_connection, INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE)
    finally:
        verify_connection.close()


def test_current_schema_multiple_missing_objects_are_reported_together(
    tmp_path: Path,
) -> None:
    """current user_version 多个对象缺失时 schema validation 必须批量诊断。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 诊断未同时列出缺失 table 与 index 时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    _drop_table(options.db_path, TABLE_HOST_MEMORY_DIAGNOSTICS)
    _drop_index(options.db_path, INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE)

    with pytest.raises(
        HostSchemaMismatchError,
        match="missing required objects",
    ) as exc_info:
        open_host_durable_store(options)

    error_message = str(exc_info.value)
    assert f"tables: {TABLE_HOST_MEMORY_DIAGNOSTICS}" in error_message
    assert (
        f"indexes: {INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON}, "
        f"{INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}"
    ) in error_message


def test_current_schema_wrong_index_definition_opener_raises_without_repair(
    tmp_path: Path,
) -> None:
    """current user_version 下同名 required index 定义错误时 opener fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: opener 未抛错或静默修复错误 index 定义时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    _replace_index_with_wrong_definition(
        options.db_path,
        INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
    )

    with pytest.raises(
        HostSchemaMismatchError,
        match=(
            "definition mismatch: "
            f"{_SQLITE_OBJECT_TYPE_INDEX} {INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION}"
        ),
    ):
        open_host_durable_store(options)

    verify_connection = sqlite3.connect(options.db_path)
    try:
        wrong_sql = _schema_sql(
            verify_connection,
            _SQLITE_OBJECT_TYPE_INDEX,
            INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
        )
        assert "CREATE INDEX" in wrong_sql
        assert "WHERE status IN" not in wrong_sql
    finally:
        verify_connection.close()


def test_current_schema_mutated_table_definition_opener_raises_without_repair(
    tmp_path: Path,
) -> None:
    """current user_version 下同名 table catalog SQL 变异时 opener fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: opener 未抛错或静默修复错误 table 定义时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options):
        pass
    original_sql = _schema_sql_from_db_path(
        options.db_path,
        _SQLITE_OBJECT_TYPE_TABLE,
        TABLE_HOST_RUNS,
    )
    mutated_sql = original_sql.replace("execution_target TEXT NOT NULL", "execution_target TEXT NULL", 1)
    assert mutated_sql != original_sql
    _mutate_schema_sql(
        options.db_path,
        object_type=_SQLITE_OBJECT_TYPE_TABLE,
        object_name=TABLE_HOST_RUNS,
        mutated_sql=mutated_sql,
    )

    with pytest.raises(
        HostSchemaMismatchError,
        match=f"definition mismatch: {_SQLITE_OBJECT_TYPE_TABLE} {TABLE_HOST_RUNS}",
    ):
        open_host_durable_store(options)

    verify_connection = sqlite3.connect(options.db_path)
    try:
        assert (
            _schema_sql(verify_connection, _SQLITE_OBJECT_TYPE_TABLE, TABLE_HOST_RUNS)
            == mutated_sql
        )
    finally:
        verify_connection.close()


def test_secondary_connection_missing_table_raises_without_repair(
    tmp_path: Path,
) -> None:
    """store.connect secondary path 缺 required table 时只校验不 bootstrap。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: secondary path 未抛错或静默重建缺失表时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _drop_table(options.db_path, TABLE_HOST_MEMORY_DIAGNOSTICS)
        with pytest.raises(
            HostSchemaMismatchError,
            match="missing required objects",
        ) as exc_info:
            store.connect()
        error_message = str(exc_info.value)
        assert f"tables: {TABLE_HOST_MEMORY_DIAGNOSTICS}" in error_message
        assert f"indexes: {INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON}" in error_message

    verify_connection = sqlite3.connect(options.db_path)
    try:
        assert TABLE_HOST_MEMORY_DIAGNOSTICS not in _table_names(verify_connection)
    finally:
        verify_connection.close()


def test_secondary_connection_missing_index_raises_without_repair(
    tmp_path: Path,
) -> None:
    """store.connect secondary path 缺 required index 时只校验不 bootstrap。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: secondary path 未抛错或静默重建缺失索引时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _drop_index(options.db_path, INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE)
        with pytest.raises(
            HostSchemaMismatchError,
            match=f"missing required index: {INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}",
        ):
            store.connect()

    verify_connection = sqlite3.connect(options.db_path)
    try:
        assert not _index_exists(verify_connection, INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE)
    finally:
        verify_connection.close()


def test_secondary_connection_definition_mismatch_raises_without_repair(
    tmp_path: Path,
) -> None:
    """store.connect secondary path 遇到 definition mismatch 时只校验不修复。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: secondary path 未抛错或静默修复错误定义时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _replace_index_with_wrong_definition(
            options.db_path,
            INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
        )
        with pytest.raises(
            HostSchemaMismatchError,
            match=(
                "definition mismatch: "
                f"{_SQLITE_OBJECT_TYPE_INDEX} {INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION}"
            ),
        ):
            store.connect()

    verify_connection = sqlite3.connect(options.db_path)
    try:
        wrong_sql = _schema_sql(
            verify_connection,
            _SQLITE_OBJECT_TYPE_INDEX,
            INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
        )
        assert "CREATE INDEX" in wrong_sql
        assert "WHERE status IN" not in wrong_sql
    finally:
        verify_connection.close()


def test_host_durable_indexes_match_create_index_ddl() -> None:
    """HOST_DURABLE_INDEXES 与 HOST_DURABLE_DDL 中的 index DDL 保持同源。

    :returns: ``None``。
    :raises AssertionError: required index 常量集合与 DDL 中 index 名称不一致时抛出。
    """

    ddl_index_names = {
        match.group(1)
        for statement in HOST_DURABLE_DDL
        for match in _CREATE_INDEX_NAME_PATTERN.finditer(statement)
    }
    assert ddl_index_names == set(HOST_DURABLE_INDEXES)


def test_host_durable_tables_match_create_table_ddl() -> None:
    """HOST_DURABLE_TABLES 与 HOST_DURABLE_DDL 中的 table DDL 保持同源。

    :returns: ``None``。
    :raises AssertionError: required table 常量集合与 DDL 中 table 名称不一致时抛出。
    """

    assert _ddl_table_names(HOST_DURABLE_DDL) == set(HOST_DURABLE_TABLES)


def test_fresh_bootstrapped_schema_matches_generated_expected_sql(
    tmp_path: Path,
) -> None:
    """fresh bootstrap 后 catalog SQL 与当前 DDL 生成的 expected SQL 一致。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: fresh DB schema definition validation false positive 时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            durable_schema.validate_host_durable_schema(connection)
            assert (
                durable_schema._read_schema_sql_by_name(connection)
                == durable_schema._expected_schema_sql_by_name()
            )
        finally:
            connection.close()


def test_normalize_schema_sql_only_strips_and_collapses_whitespace() -> None:
    """schema SQL 归一化只处理首尾空白和连续空白。

    :returns: ``None``。
    :raises AssertionError: 大小写、quote、clause 或标点变化被错误归一化时抛出。
    """

    base_sql = 'CREATE TABLE "host_runs" (run_id TEXT, status TEXT)'
    normalized_base = durable_schema._normalize_schema_sql(base_sql)

    assert (
        durable_schema._normalize_schema_sql(
            '\n\tCREATE   TABLE   "host_runs"   (run_id   TEXT,   status   TEXT)  '
        )
        == normalized_base
    )
    assert (
        durable_schema._normalize_schema_sql(
            'create TABLE "host_runs" (run_id TEXT, status TEXT)'
        )
        != normalized_base
    )
    assert (
        durable_schema._normalize_schema_sql(
            "CREATE TABLE host_runs (run_id TEXT, status TEXT)"
        )
        != normalized_base
    )
    assert (
        durable_schema._normalize_schema_sql(
            'CREATE TABLE "host_runs" (run_id TEXT, status TEXT) WITHOUT ROWID'
        )
        != normalized_base
    )
    assert (
        durable_schema._normalize_schema_sql(
            'CREATE TABLE "host_runs"(run_id TEXT, status TEXT)'
        )
        != normalized_base
    )


def test_host_schema_version_is_query_index_version() -> None:
    """当前 committed Host schema version 是 durable query index fresh schema 16。"""

    assert HOST_SCHEMA_VERSION == 16


def test_foundation_query_indexes_are_created(tmp_path: Path) -> None:
    """fresh schema 创建 host liveness 与 session EventLog 查询索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            host_instance_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_INSTANCES})"
            ).fetchall()
            event_log_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_EVENT_LOG})"
            ).fetchall()
            assert INDEX_HOST_INSTANCES_STATUS_HEARTBEAT in {
                str(row[1]) for row in host_instance_indexes
            }
            assert INDEX_EVENT_LOG_SESSION_SEQUENCE in {
                str(row[1]) for row in event_log_indexes
            }
            host_instance_columns = connection.execute(
                f"PRAGMA index_info({INDEX_HOST_INSTANCES_STATUS_HEARTBEAT})"
            ).fetchall()
            event_log_columns = connection.execute(
                f"PRAGMA index_info({INDEX_EVENT_LOG_SESSION_SEQUENCE})"
            ).fetchall()
            assert tuple(str(row[2]) for row in host_instance_columns) == (
                "status",
                "heartbeat_at",
            )
            assert tuple(str(row[2]) for row in event_log_columns) == (
                "session_id",
                "event_sequence",
            )
        finally:
            connection.close()


def test_purge_tombstone_table_has_no_session_or_event_log_fk(
    tmp_path: Path,
) -> None:
    """purge tombstone table 不外键引用会被删除的 Session / EventLog facts。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_PURGE_TOMBSTONES in _table_names(connection)
            assert _primary_key_columns(
                connection,
                TABLE_HOST_PURGE_TOMBSTONES,
            ) == ("tombstone_id",)
            table_info = connection.execute(f"PRAGMA table_info({TABLE_HOST_PURGE_TOMBSTONES})").fetchall()
            not_null_columns = {str(row[1]) for row in table_info if int(row[3]) == 1}
            assert "audit_record_ref" in not_null_columns
            assert "audit_record_digest" in not_null_columns

            tombstone_fks = connection.execute(f"PRAGMA foreign_key_list({TABLE_HOST_PURGE_TOMBSTONES})").fetchall()
            fk_targets = {str(row[2]) for row in tombstone_fks}
            assert TABLE_EVENT_LOG not in fk_targets
            assert TABLE_HOST_SESSIONS not in fk_targets

            tombstone_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_PURGE_TOMBSTONES})").fetchall()
            tombstone_index_names = {str(row[1]) for row in tombstone_indexes}
            assert INDEX_HOST_PURGE_TOMBSTONES_SESSION in tombstone_index_names
            session_index = next(row for row in tombstone_indexes if str(row[1]) == INDEX_HOST_PURGE_TOMBSTONES_SESSION)
            assert int(session_index[2]) == 1
        finally:
            connection.close()


def test_wait_record_snapshot_columns_are_all_or_none(tmp_path: Path) -> None:
    """wait snapshot 三元组必须同时存在或同时为空。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_WAIT_RECORDS} (
                      wait_id,
                      session_id,
                      run_id,
                      attempt_id,
                      execution_id,
                      tool_call_id,
                      tool_name,
                      adapter_key,
                      await_kind,
                      resume_policy,
                      resume_token,
                      snapshot_ref,
                      snapshot_captured_at,
                      snapshot_digest,
                      external_job_id,
                      accept_idempotency_key,
                      resolve_idempotency_key,
                      resolve_semantic_digest,
                      deadline_at,
                      expires_at,
                      status,
                      created_event_id,
                      created_event_sequence,
                      updated_event_id,
                      updated_event_sequence,
                      created_at,
                      updated_at,
                      terminal_at
                    ) VALUES (
                      'wait-invalid-snapshot',
                      'session-1',
                      'run-1',
                      'attempt-1',
                      'execution-1',
                      'tool-call-1',
                      'lookup',
                      'adapter',
                      'external_job',
                      'poll',
                      'resume-token',
                      'snapshot-1',
                      '2026-05-19T00:00:00.000000Z',
                      NULL,
                      NULL,
                      'accept-key',
                      NULL,
                      NULL,
                      NULL,
                      NULL,
                      'waiting',
                      'event-created',
                      1,
                      'event-updated',
                      2,
                      '2026-05-19T00:00:00.000000Z',
                      '2026-05-19T00:00:00.000000Z',
                      NULL
                    )
                    """)
        finally:
            connection.close()


def test_wal_persists_on_second_independent_connection(tmp_path: Path) -> None:
    """第二条独立 connection 也能观察到 WAL journal mode。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        second_connection = store.connect()
        try:
            assert _pragma_text(second_connection, "PRAGMA journal_mode").lower() == "wal"
            assert _pragma_int(second_connection, "PRAGMA foreign_keys") == 1
        finally:
            second_connection.close()


def test_schema_constraints_are_explicit(tmp_path: Path) -> None:
    """foundation tables 包含计划要求的 PK、unique 与 FK 约束。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            event_columns = connection.execute(f"PRAGMA table_info({TABLE_EVENT_LOG})").fetchall()
            event_sequence = next(row for row in event_columns if str(row[1]) == "event_sequence")
            assert str(event_sequence[2]).upper() == "INTEGER"
            assert int(event_sequence[5]) == 1

            create_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (TABLE_EVENT_LOG,),
            ).fetchone()
            assert create_sql_row is not None
            assert "AUTOINCREMENT" in str(create_sql_row[0]).upper()

            event_indexes = connection.execute(f"PRAGMA index_list({TABLE_EVENT_LOG})").fetchall()
            assert any(int(row[2]) == 1 for row in event_indexes)

            event_fks = connection.execute(f"PRAGMA foreign_key_list({TABLE_EVENT_LOG})").fetchall()
            assert any(str(row[2]) == TABLE_PAYLOAD_DESCRIPTORS for row in event_fks)

            assert _primary_key_columns(connection, TABLE_IDEMPOTENCY_RECORDS) == (
                "scope_kind",
                "scope_id",
                "idempotency_key",
            )
            assert _primary_key_columns(connection, TABLE_PAYLOAD_DESCRIPTORS) == ("payload_ref",)
            assert _primary_key_columns(connection, TABLE_SQLITE_PAYLOADS) == ("payload_id",)
            assert _primary_key_columns(connection, TABLE_HOST_INSTANCES) == ("host_instance_id",)
        finally:
            connection.close()


def test_event_log_schema_rejects_unpaired_payload_reference(
    tmp_path: Path,
) -> None:
    """EventLog payload_ref / payload_digest DDL 约束拒绝单边引用。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            _insert_payload_descriptor_probe(connection, "payload-ref-1")
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_EVENT_LOG} (
                      event_id,
                      event_body_digest,
                      event_class,
                      session_id,
                      event_type,
                      occurred_at,
                      payload_json,
                      payload_ref,
                      appended_at
                    ) VALUES (
                      'event-payload-ref-only',
                      'digest',
                      'canonical_fact',
                      'session-1',
                      'TYPE_A',
                      '2026-05-16T00:00:00.000000Z',
                      '{{}}',
                      'payload-ref-1',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_EVENT_LOG} (
                      event_id,
                      event_body_digest,
                      event_class,
                      session_id,
                      event_type,
                      occurred_at,
                      payload_json,
                      payload_digest,
                      appended_at
                    ) VALUES (
                      'event-payload-digest-only',
                      'digest',
                      'canonical_fact',
                      'session-1',
                      'TYPE_A',
                      '2026-05-16T00:00:00.000000Z',
                      '{{}}',
                      'sha256:0000000000000000000000000000000000000000000000000000000000000000',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
        finally:
            connection.close()


def test_idempotency_schema_rejects_unpaired_event_reference(
    tmp_path: Path,
) -> None:
    """Idempotency result event DDL 约束拒绝单边引用与非正序号。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            _insert_event_log_probe(connection, "event-1")
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_IDEMPOTENCY_RECORDS} (
                      scope_kind,
                      scope_id,
                      idempotency_key,
                      semantic_input_digest,
                      result_kind,
                      result_ref,
                      created_event_id,
                      created_at
                    ) VALUES (
                      'scope',
                      'scope-1',
                      'key-id-only',
                      'digest',
                      'result',
                      'result-1',
                      'event-1',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_IDEMPOTENCY_RECORDS} (
                      scope_kind,
                      scope_id,
                      idempotency_key,
                      semantic_input_digest,
                      result_kind,
                      result_ref,
                      created_event_sequence,
                      created_at
                    ) VALUES (
                      'scope',
                      'scope-1',
                      'key-sequence-only',
                      'digest',
                      'result',
                      'result-1',
                      1,
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_IDEMPOTENCY_RECORDS} (
                      scope_kind,
                      scope_id,
                      idempotency_key,
                      semantic_input_digest,
                      result_kind,
                      result_ref,
                      created_event_id,
                      created_event_sequence,
                      created_at
                    ) VALUES (
                      'scope',
                      'scope-1',
                      'key-zero-sequence',
                      'digest',
                      'result',
                      'result-1',
                      'event-1',
                      0,
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
        finally:
            connection.close()


def test_wait_record_table_and_indexes_are_created(tmp_path: Path) -> None:
    """fresh schema 创建 wait record table 与 Phase 7 指定索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_WAIT_RECORDS in _table_names(connection)
            wait_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_WAIT_RECORDS})").fetchall()
            wait_index_names = {str(row[1]) for row in wait_indexes}
            assert INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN in wait_index_names
            assert INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL in wait_index_names
            assert INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB in wait_index_names

            active_index_row = next(
                row for row in wait_indexes if str(row[1]) == INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN
            )
            assert int(active_index_row[2]) == 1
            assert int(active_index_row[4]) == 1
        finally:
            connection.close()


def test_projection_checkpoint_and_failure_tables_are_created(
    tmp_path: Path,
) -> None:
    """fresh schema 创建 projection checkpoint / failure tables。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_PROJECTION_CHECKPOINTS in _table_names(connection)
            assert TABLE_HOST_PROJECTION_FAILURES in _table_names(connection)
            assert TABLE_HOST_RUN_RESULTS in _table_names(connection)
            assert TABLE_HOST_SESSION_TIMELINE_ITEMS in _table_names(connection)
            assert _primary_key_columns(connection, TABLE_HOST_PROJECTION_CHECKPOINTS) == ("consumer_id",)
            assert _primary_key_columns(connection, TABLE_HOST_PROJECTION_FAILURES) == ("consumer_id",)
            assert _primary_key_columns(connection, TABLE_HOST_RUN_RESULTS) == ("run_id",)
            assert _primary_key_columns(connection, TABLE_HOST_SESSION_TIMELINE_ITEMS) == ("timeline_item_id",)
            run_result_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_RUN_RESULTS})").fetchall()
            timeline_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_SESSION_TIMELINE_ITEMS})").fetchall()
            assert INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE in {str(row[1]) for row in run_result_indexes}
            assert {
                INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE,
                INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE,
            }.issubset({str(row[1]) for row in timeline_indexes})
        finally:
            connection.close()


def test_memory_projection_tables_and_indexes_are_created(
    tmp_path: Path,
) -> None:
    """fresh schema 创建 memory projection tables 与索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_MEMORY_SNAPSHOTS in _table_names(connection)
            assert TABLE_HOST_MEMORY_ITEMS in _table_names(connection)
            assert TABLE_HOST_MEMORY_DIAGNOSTICS in _table_names(connection)
            assert _primary_key_columns(connection, TABLE_HOST_MEMORY_SNAPSHOTS) == ("snapshot_id",)
            assert _primary_key_columns(connection, TABLE_HOST_MEMORY_ITEMS) == ("item_id",)
            assert _primary_key_columns(connection, TABLE_HOST_MEMORY_DIAGNOSTICS) == ("diagnostic_id",)

            snapshot_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_MEMORY_SNAPSHOTS})").fetchall()
            item_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_MEMORY_ITEMS})").fetchall()
            diagnostic_indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_MEMORY_DIAGNOSTICS})").fetchall()
            assert INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR in {str(row[1]) for row in snapshot_indexes}
            assert INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE in {str(row[1]) for row in item_indexes}
            assert INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON in {str(row[1]) for row in diagnostic_indexes}
        finally:
            connection.close()


def test_audit_sink_marker_table_is_created(tmp_path: Path) -> None:
    """fresh schema 创建 audit sink-local marker table。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_AUDIT_SINK_MARKERS in _table_names(connection)
            assert _primary_key_columns(connection, TABLE_HOST_AUDIT_SINK_MARKERS) == ("event_id",)
        finally:
            connection.close()


def test_tool_trace_hot_table_and_indexes_are_created(tmp_path: Path) -> None:
    """fresh schema 创建 Tool Trace hot projection table 与查询索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_TOOL_TRACE_HOT in _table_names(connection)
            assert _primary_key_columns(connection, TABLE_HOST_TOOL_TRACE_HOT) == ("trace_id",)
            indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_TOOL_TRACE_HOT})").fetchall()
            index_names = {str(row[1]) for row in indexes}
            assert {
                INDEX_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE,
                INDEX_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE,
                INDEX_HOST_TOOL_TRACE_HOT_TOOL_CALL,
                INDEX_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST,
                INDEX_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF,
            }.issubset(index_names)
        finally:
            connection.close()


def test_outbox_tables_and_indexes_are_created(tmp_path: Path) -> None:
    """fresh schema 创建 Outbox terminal item / drain idempotency tables 与索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_OUTBOX_TERMINAL_ITEMS in _table_names(connection)
            assert TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY in _table_names(connection)
            assert _primary_key_columns(
                connection,
                TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
            ) == ("item_id",)
            assert _primary_key_columns(
                connection,
                TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
            ) == ("session_id", "drain_request_id")
            indexes = connection.execute(f"PRAGMA index_list({TABLE_HOST_OUTBOX_TERMINAL_ITEMS})").fetchall()
            index_names = {str(row[1]) for row in indexes}
            assert {
                INDEX_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE,
                INDEX_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE,
                INDEX_HOST_OUTBOX_TERMINAL_ITEMS_RUN,
            }.issubset(index_names)
        finally:
            connection.close()


def test_projection_schema_constraints_reject_invalid_rows(
    tmp_path: Path,
) -> None:
    """projection schema CHECK / FK 约束拒绝非法 checkpoint 与 failure row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            _insert_event_log_probe(connection, "event-1")
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
                      consumer_id,
                      checkpoint_event_sequence,
                      checkpoint_event_id,
                      updated_at
                    ) VALUES ('consumer', -1, NULL, '2026-05-16T00:00:00.000000Z')
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_PROJECTION_FAILURES} (
                      consumer_id,
                      failed_event_sequence,
                      failed_event_id,
                      failure_count,
                      last_error_code,
                      last_error_message,
                      first_failed_at,
                      last_failed_at
                    ) VALUES (
                      'consumer',
                      1,
                      'missing-event',
                      0,
                      'ProjectionError',
                      'failed',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
                      consumer_id,
                      checkpoint_event_sequence,
                      checkpoint_event_id,
                      updated_at
                    ) VALUES (
                      'consumer-zero-with-event',
                      0,
                      'event-1',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
                      consumer_id,
                      checkpoint_event_sequence,
                      checkpoint_event_id,
                      updated_at
                    ) VALUES (
                      'consumer-positive-without-event',
                      1,
                      NULL,
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
                      consumer_id,
                      checkpoint_event_sequence,
                      checkpoint_event_id,
                      updated_at
                    ) VALUES (
                      'consumer',
                      1,
                      'missing-event',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_RUN_RESULTS} (
                      run_id,
                      session_id,
                      terminal_status,
                      terminal_event_id,
                      terminal_event_sequence,
                      result_ref,
                      result_digest,
                      projected_at,
                      updated_at
                    ) VALUES (
                      'run-1',
                      'session-1',
                      'running',
                      'event-1',
                      1,
                      'result-ref',
                      NULL,
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_SESSION_TIMELINE_ITEMS} (
                      timeline_item_id,
                      session_id,
                      event_id,
                      event_sequence,
                      item_kind,
                      event_type,
                      payload_ref,
                      payload_digest,
                      projected_at
                    ) VALUES (
                      'event-1',
                      'session-1',
                      'event-1',
                      1,
                      'user_input',
                      'USER_INPUT_ACCEPTED',
                      'payload-ref',
                      NULL,
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            connection.execute(f"""
                INSERT INTO {TABLE_HOST_MEMORY_DIAGNOSTICS} (
                  diagnostic_id,
                  session_id,
                  reason,
                  diagnostic_json,
                  recorded_at
                ) VALUES (
                  'diagnostic-unsupported',
                  'session-1',
                  'unsupported_event_type',
                  '{{}}',
                  '2026-05-16T00:00:00.000000Z'
                )
                """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_AUDIT_SINK_MARKERS} (
                      event_id,
                      event_sequence,
                      line_digest,
                      written_at
                    ) VALUES (
                      'event-1',
                      0,
                      'sha256:1111111111111111111111111111111111111111111111111111111111111111',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_AUDIT_SINK_MARKERS} (
                      event_id,
                      event_sequence,
                      line_digest,
                      written_at
                    ) VALUES (
                      'missing-event',
                      1,
                      'sha256:1111111111111111111111111111111111111111111111111111111111111111',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_TOOL_TRACE_HOT} (
                      trace_id,
                      event_id,
                      event_sequence,
                      event_type,
                      event_class,
                      session_id,
                      trace_summary_json,
                      cold_trace_ref,
                      projected_at,
                      updated_at
                    ) VALUES (
                      'trace-invalid-cold-ref',
                      'event-1',
                      1,
                      'TOOL_RESULT_ACCEPTED',
                      'canonical_fact',
                      'session-1',
                      '{{}}',
                      'cold-ref',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_TOOL_TRACE_HOT} (
                      trace_id,
                      event_id,
                      event_sequence,
                      event_type,
                      event_class,
                      session_id,
                      trace_summary_json,
                      projected_at,
                      updated_at
                    ) VALUES (
                      'trace-missing-event',
                      'missing-event',
                      1,
                      'TOOL_RESULT_ACCEPTED',
                      'canonical_fact',
                      'session-1',
                      '{{}}',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_OUTBOX_TERMINAL_ITEMS} (
                      item_id,
                      idempotency_key,
                      terminal_event_id,
                      event_sequence,
                      session_id,
                      run_id,
                      terminal_status,
                      dedupe_key,
                      result_ref,
                      result_digest,
                      item_state,
                      projected_at,
                      updated_at
                    ) VALUES (
                      'outbox-invalid-status',
                      'sha256:2222222222222222222222222222222222222222222222222222222222222222',
                      'event-1',
                      1,
                      'session-1',
                      'run-1',
                      'lost',
                      'event-1',
                      'result-ref',
                      NULL,
                      'pending',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_OUTBOX_TERMINAL_ITEMS} (
                      item_id,
                      idempotency_key,
                      terminal_event_id,
                      event_sequence,
                      session_id,
                      run_id,
                      terminal_status,
                      dedupe_key,
                      item_state,
                      projected_at,
                      updated_at,
                      drained_at
                    ) VALUES (
                      'outbox-invalid-drain-state',
                      'sha256:3333333333333333333333333333333333333333333333333333333333333333',
                      'event-1',
                      1,
                      'session-1',
                      'run-1',
                      'succeeded',
                      'event-1',
                      'pending',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
        finally:
            connection.close()


def test_event_sequence_is_sqlite_foreign_key_parent_key(
    tmp_path: Path,
) -> None:
    """event_log(event_sequence) 是 SQLite FK 可引用的 primary key。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            event_columns = connection.execute(f"PRAGMA table_info({TABLE_EVENT_LOG})").fetchall()
            event_sequence = next(row for row in event_columns if str(row[1]) == "event_sequence")
            assert int(event_sequence[5]) == 1
            connection.execute("""
                CREATE TABLE projection_fk_probe (
                  event_sequence INTEGER NOT NULL,
                  FOREIGN KEY(event_sequence) REFERENCES event_log(event_sequence)
                )
                """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO projection_fk_probe (event_sequence) VALUES (999)")
        finally:
            connection.close()


def test_event_log_run_type_sequence_index_exists(tmp_path: Path) -> None:
    """EventLog 支持按 Run 与 event type 读取最近事件的索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert _index_exists(connection, INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE)
        finally:
            connection.close()


def test_memory_schema_constraints_reject_invalid_rows(
    tmp_path: Path,
) -> None:
    """memory schema CHECK / FK 约束拒绝非法 snapshot、item 与 diagnostic row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_MEMORY_SNAPSHOTS} (
                      snapshot_id,
                      session_id,
                      consumer_id,
                      checkpoint_event_sequence,
                      checkpoint_event_id,
                      policy_digest,
                      snapshot_digest,
                      snapshot_json,
                      built_at,
                      updated_at
                    ) VALUES (
                      'snapshot-invalid',
                      'session-1',
                      'host.memory.session.v1',
                      -1,
                      NULL,
                      'policy-digest',
                      'snapshot-digest',
                      '{{}}',
                      '2026-05-16T00:00:00.000000Z',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
            connection.execute(f"""
                INSERT INTO {TABLE_HOST_MEMORY_SNAPSHOTS} (
                  snapshot_id,
                  session_id,
                  consumer_id,
                  checkpoint_event_sequence,
                  checkpoint_event_id,
                  policy_digest,
                  snapshot_digest,
                  snapshot_json,
                  built_at,
                  updated_at
                ) VALUES (
                  'snapshot-1',
                  'session-1',
                  'host.memory.session.v1',
                  0,
                  NULL,
                  'policy-digest',
                  'snapshot-digest',
                  '{{}}',
                  '2026-05-16T00:00:00.000000Z',
                  '2026-05-16T00:00:00.000000Z'
                )
                """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_MEMORY_ITEMS} (
                      item_id,
                      snapshot_id,
                      session_id,
                      item_kind,
                      claim_status,
                      event_id,
                      event_sequence,
                      producer_kind,
                      producer_name,
                      item_json
                    ) VALUES (
                      'item-1',
                      'snapshot-1',
                      'session-1',
                      'company',
                      'tool_verified',
                      'event-1',
                      1,
                      'tool',
                      'tool-a',
                      '{{}}'
                    )
                    """)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"""
                    INSERT INTO {TABLE_HOST_MEMORY_DIAGNOSTICS} (
                      diagnostic_id,
                      session_id,
                      reason,
                      diagnostic_json,
                      recorded_at
                    ) VALUES (
                      'diagnostic-1',
                      'session-1',
                      'projection_exception',
                      '{{}}',
                      '2026-05-16T00:00:00.000000Z'
                    )
                    """)
        finally:
            connection.close()


def test_schema_creates_only_owned_purge_tombstone_table(
    tmp_path: Path,
) -> None:
    """Phase 15 bootstrap 只创建已归属的 purge tombstone table。"""

    forbidden_fragments = ("purge",)
    options = _options(tmp_path)
    purge_tables: set[str] = set()
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            table_names = _table_names(connection)
            purge_tables = {
                table for table in table_names if any(fragment in table for fragment in forbidden_fragments)
            }
        finally:
            connection.close()
    assert purge_tables == {TABLE_HOST_PURGE_TOMBSTONES}


def _primary_key_columns(connection: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
    """读取表的 primary key 列名顺序。

    :param connection: SQLite connection。
    :param table_name: 表名。
    :returns: primary key 列名元组。
    """

    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    pk_rows = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    return tuple(name for _position, name in pk_rows)
