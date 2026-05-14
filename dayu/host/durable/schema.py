"""Host durable SQLite schema bootstrap 与版本校验。

本模块是 Phase 2 durable foundation schema convention 的唯一 DDL 真源。它只
创建 EventLog、idempotency、payload descriptor / sqlite payload 与 host
instance foundation tables，不创建 Session / Run / Attempt、wait、projection、
outbox、memory 或 purge 相关表。
"""

from __future__ import annotations

import sqlite3

from dayu.host.durable.errors import HostSchemaMismatchError

HOST_SCHEMA_VERSION = 1
"""当前 Host durable SQLite schema version。"""

TABLE_EVENT_LOG = "event_log"
TABLE_IDEMPOTENCY_RECORDS = "idempotency_records"
TABLE_SQLITE_PAYLOADS = "host_sqlite_payloads"
TABLE_PAYLOAD_DESCRIPTORS = "payload_descriptors"
TABLE_HOST_INSTANCES = "host_instances"

FOUNDATION_TABLES: tuple[str, ...] = (
    TABLE_EVENT_LOG,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_SQLITE_PAYLOADS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_HOST_INSTANCES,
)
"""Phase 2 foundation table 名称集合。"""

_SQLITE_PAYLOADS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_SQLITE_PAYLOADS} (
  payload_id TEXT PRIMARY KEY,
  payload_format TEXT NOT NULL CHECK (
    payload_format IN ('canonical_json', 'bytes')
  ),
  payload_json TEXT NULL,
  payload_bytes BLOB NULL,
  payload_size_bytes INTEGER NOT NULL CHECK (payload_size_bytes >= 0),
  payload_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK (
    (payload_format = 'canonical_json'
      AND payload_json IS NOT NULL
      AND payload_bytes IS NULL)
    OR
    (payload_format = 'bytes'
      AND payload_bytes IS NOT NULL
      AND payload_json IS NULL)
  )
)
"""

_PAYLOAD_DESCRIPTORS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_PAYLOAD_DESCRIPTORS} (
  payload_ref TEXT PRIMARY KEY,
  payload_kind TEXT NOT NULL CHECK (
    payload_kind IN ('sqlite_payload', 'artifact_ref')
  ),
  payload_digest TEXT NOT NULL,
  payload_size_bytes INTEGER NOT NULL CHECK (payload_size_bytes >= 0),
  media_type TEXT NULL,
  sqlite_payload_id TEXT NULL,
  artifact_relative_path TEXT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(sqlite_payload_id) REFERENCES {TABLE_SQLITE_PAYLOADS}(payload_id),
  CHECK (
    (payload_kind = 'sqlite_payload'
      AND sqlite_payload_id IS NOT NULL
      AND artifact_relative_path IS NULL)
    OR
    (payload_kind = 'artifact_ref'
      AND artifact_relative_path IS NOT NULL
      AND sqlite_payload_id IS NULL)
  )
)
"""

_EVENT_LOG_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_EVENT_LOG} (
  event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  event_body_digest TEXT NOT NULL,
  event_class TEXT NOT NULL CHECK (
    event_class IN (
      'canonical_fact',
      'preview',
      'diagnostic',
      'projection_signal'
    )
  ),
  session_id TEXT NOT NULL,
  run_id TEXT NULL,
  attempt_id TEXT NULL,
  execution_id TEXT NULL,
  event_type TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  actor TEXT NULL,
  source TEXT NULL,
  client_request_id TEXT NULL,
  idempotency_key TEXT NULL,
  policy_decision_json TEXT NULL,
  reason_json TEXT NULL,
  payload_json TEXT NOT NULL,
  payload_ref TEXT NULL,
  payload_digest TEXT NULL,
  appended_at TEXT NOT NULL,
  FOREIGN KEY(payload_ref) REFERENCES {TABLE_PAYLOAD_DESCRIPTORS}(payload_ref),
  CHECK (payload_ref IS NULL OR payload_digest IS NOT NULL)
)
"""

_IDEMPOTENCY_RECORDS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_IDEMPOTENCY_RECORDS} (
  scope_kind TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  semantic_input_digest TEXT NOT NULL,
  result_kind TEXT NOT NULL,
  result_ref TEXT NOT NULL,
  created_event_id TEXT NULL,
  created_event_sequence INTEGER NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(scope_kind, scope_id, idempotency_key),
  FOREIGN KEY(created_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(created_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence)
)
"""

_HOST_INSTANCES_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_INSTANCES} (
  host_instance_id TEXT PRIMARY KEY,
  pid INTEGER NOT NULL CHECK (pid > 0),
  process_start_token TEXT NOT NULL,
  boot_id TEXT NULL,
  created_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN ('running', 'stopping', 'stopped', 'crashed_suspected')
  )
)
"""

FOUNDATION_DDL: tuple[str, ...] = (
    _SQLITE_PAYLOADS_DDL,
    _PAYLOAD_DESCRIPTORS_DDL,
    _EVENT_LOG_DDL,
    _IDEMPOTENCY_RECORDS_DDL,
    _HOST_INSTANCES_DDL,
)
"""按外键依赖顺序排列的 Phase 2 foundation DDL。"""


def bootstrap_host_durable_store(connection: sqlite3.Connection) -> None:
    """初始化 fresh Host durable SQLite schema 并校验版本。

    ``user_version`` 为 ``0`` 的 DB 被视为 fresh DB；函数会创建 foundation
    tables 并设置 ``PRAGMA user_version = 1``。``user_version`` 为当前版本
    时函数幂等执行 DDL。其它版本一律结构化失败，不做兼容读取或迁移。

    :param connection: 已完成 PRAGMA setup 的 SQLite connection。
    :returns: ``None``。
    :raises HostSchemaMismatchError: DB schema version 不匹配时抛出。
    :raises sqlite3.Error: SQLite DDL 或 PRAGMA 执行失败时抛出。
    """

    current_version = _read_user_version(connection)
    if current_version not in (0, HOST_SCHEMA_VERSION):
        raise HostSchemaMismatchError(
            "Host durable schema version mismatch: "
            f"expected {HOST_SCHEMA_VERSION}, got {current_version}"
        )
    for statement in FOUNDATION_DDL:
        connection.execute(statement)
    connection.execute(f"PRAGMA user_version={HOST_SCHEMA_VERSION}")
    connection.commit()
    validate_host_schema_version(connection)


def validate_host_schema_version(connection: sqlite3.Connection) -> None:
    """校验 Host durable SQLite ``user_version``。

    :param connection: SQLite connection。
    :returns: ``None``。
    :raises HostSchemaMismatchError: ``user_version`` 不是当前版本时抛出。
    :raises sqlite3.Error: PRAGMA 查询失败时抛出。
    """

    current_version = _read_user_version(connection)
    if current_version != HOST_SCHEMA_VERSION:
        raise HostSchemaMismatchError(
            "Host durable schema version mismatch: "
            f"expected {HOST_SCHEMA_VERSION}, got {current_version}"
        )


def _read_user_version(connection: sqlite3.Connection) -> int:
    """读取 SQLite ``PRAGMA user_version``。

    :param connection: SQLite connection。
    :returns: 当前 ``user_version``。
    :raises HostSchemaMismatchError: SQLite 未返回版本行时抛出。
    :raises sqlite3.Error: PRAGMA 查询失败时抛出。
    """

    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise HostSchemaMismatchError("Host durable schema version is unreadable")
    return int(row[0])
