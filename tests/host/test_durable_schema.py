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
    INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE,
    MEMORY_PROJECTION_TABLES,
    PHASE3_STATE_TABLES,
    PROJECTION_TABLES,
    INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON,
    INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE,
    INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR,
    INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE,
    INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE,
    INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE,
    TABLE_EVENT_LOG,
    TABLE_HOST_INSTANCES,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
    TABLE_HOST_WAIT_RECORDS,
    INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL,
    INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB,
    INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN,
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


def _insert_payload_descriptor_probe(
    connection: sqlite3.Connection, payload_ref: str
) -> None:
    """插入 schema 约束测试用 payload descriptor row。

    :param connection: SQLite connection。
    :param payload_ref: payload descriptor 引用。
    :returns: 无。
    :raises sqlite3.Error: 插入失败时由 SQLite 抛出。
    """

    connection.execute(
        f"""
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
        """
    )
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
    """fresh DB bootstrap 创建 foundation、state、projection 与 memory tables。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert _table_names(connection) == frozenset(HOST_DURABLE_TABLES)
            assert set(PHASE3_STATE_TABLES).issubset(_table_names(connection))
            assert set(PROJECTION_TABLES).issubset(_table_names(connection))
            assert set(MEMORY_PROJECTION_TABLES).issubset(
                _table_names(connection)
            )
            assert _pragma_int(connection, "PRAGMA user_version") == (
                HOST_SCHEMA_VERSION
            )
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
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
                    """
                )
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
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
        finally:
            connection.close()


def test_wait_record_table_and_indexes_are_created(tmp_path: Path) -> None:
    """fresh schema 创建 wait record table 与 Phase 7 指定索引。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        connection = store.connect()
        try:
            assert TABLE_HOST_WAIT_RECORDS in _table_names(connection)
            wait_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_WAIT_RECORDS})"
            ).fetchall()
            wait_index_names = {str(row[1]) for row in wait_indexes}
            assert INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN in wait_index_names
            assert INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL in wait_index_names
            assert INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB in wait_index_names

            active_index_row = next(
                row
                for row in wait_indexes
                if str(row[1]) == INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN
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
            assert _primary_key_columns(
                connection, TABLE_HOST_PROJECTION_CHECKPOINTS
            ) == ("consumer_id",)
            assert _primary_key_columns(
                connection, TABLE_HOST_PROJECTION_FAILURES
            ) == ("consumer_id",)
            assert _primary_key_columns(connection, TABLE_HOST_RUN_RESULTS) == (
                "run_id",
            )
            assert _primary_key_columns(
                connection, TABLE_HOST_SESSION_TIMELINE_ITEMS
            ) == ("timeline_item_id",)
            run_result_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_RUN_RESULTS})"
            ).fetchall()
            timeline_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_SESSION_TIMELINE_ITEMS})"
            ).fetchall()
            assert INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE in {
                str(row[1]) for row in run_result_indexes
            }
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
            assert _primary_key_columns(connection, TABLE_HOST_MEMORY_SNAPSHOTS) == (
                "snapshot_id",
            )
            assert _primary_key_columns(connection, TABLE_HOST_MEMORY_ITEMS) == (
                "item_id",
            )
            assert _primary_key_columns(
                connection, TABLE_HOST_MEMORY_DIAGNOSTICS
            ) == ("diagnostic_id",)

            snapshot_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_MEMORY_SNAPSHOTS})"
            ).fetchall()
            item_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_MEMORY_ITEMS})"
            ).fetchall()
            diagnostic_indexes = connection.execute(
                f"PRAGMA index_list({TABLE_HOST_MEMORY_DIAGNOSTICS})"
            ).fetchall()
            assert INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR in {
                str(row[1]) for row in snapshot_indexes
            }
            assert INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE in {
                str(row[1]) for row in item_indexes
            }
            assert INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON in {
                str(row[1]) for row in diagnostic_indexes
            }
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
                connection.execute(
                    f"""
                    INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
                      consumer_id,
                      checkpoint_event_sequence,
                      checkpoint_event_id,
                      updated_at
                    ) VALUES ('consumer', -1, NULL, '2026-05-16T00:00:00.000000Z')
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            connection.execute(
                f"""
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
                """
            )
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
            event_columns = connection.execute(
                f"PRAGMA table_info({TABLE_EVENT_LOG})"
            ).fetchall()
            event_sequence = next(
                row for row in event_columns if str(row[1]) == "event_sequence"
            )
            assert int(event_sequence[5]) == 1
            connection.execute(
                """
                CREATE TABLE projection_fk_probe (
                  event_sequence INTEGER NOT NULL,
                  FOREIGN KEY(event_sequence) REFERENCES event_log(event_sequence)
                )
                """
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO projection_fk_probe (event_sequence) VALUES (999)"
                )
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
                connection.execute(
                    f"""
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
                    """
                )
            connection.execute(
                f"""
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
                """
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"""
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
                    """
                )
        finally:
            connection.close()


def test_schema_does_not_create_unowned_future_sink_tables(
    tmp_path: Path,
) -> None:
    """Phase 9 bootstrap 不得预创建未归属的 future sink tables。"""

    forbidden_fragments = (
        "outbox",
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
