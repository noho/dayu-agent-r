"""Host durable SQLite schema bootstrap 与版本校验。

本模块是 Host durable schema convention 的唯一 DDL 真源。它创建 Phase 2
foundation tables，以及 Phase 3 Session / Run / Attempt durable state tables；
不承载 command、admission、projection、outbox、memory 或 purge 相关逻辑。
"""

from __future__ import annotations

import sqlite3

from dayu.host.durable.errors import HostSchemaMismatchError

HOST_SCHEMA_VERSION = 2
"""当前 Host durable SQLite schema version。"""

TABLE_EVENT_LOG = "event_log"
TABLE_IDEMPOTENCY_RECORDS = "idempotency_records"
TABLE_SQLITE_PAYLOADS = "host_sqlite_payloads"
TABLE_PAYLOAD_DESCRIPTORS = "payload_descriptors"
TABLE_HOST_INSTANCES = "host_instances"
TABLE_HOST_SESSIONS = "host_sessions"
TABLE_HOST_SESSION_SLOTS = "host_session_slots"
TABLE_HOST_RUNS = "host_runs"
TABLE_HOST_ATTEMPTS = "host_attempts"
TABLE_HOST_ATTEMPT_DISPATCH_RECORDS = "host_attempt_dispatch_records"

INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION = "host_runs_one_active_per_session"
INDEX_HOST_RUNS_QUEUE_FIFO = "host_runs_queue_fifo"
INDEX_HOST_RUNS_SESSION_STATUS = "host_runs_session_status"

FOUNDATION_TABLES: tuple[str, ...] = (
    TABLE_EVENT_LOG,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_SQLITE_PAYLOADS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_HOST_INSTANCES,
)
"""Phase 2 foundation table 名称集合。"""

PHASE3_STATE_TABLES: tuple[str, ...] = (
    TABLE_HOST_SESSIONS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
)
"""Phase 3 Session / Run / Attempt durable state table 名称集合。"""

HOST_DURABLE_TABLES: tuple[str, ...] = FOUNDATION_TABLES + PHASE3_STATE_TABLES
"""当前 fresh bootstrap 应创建的 Host durable table 名称集合。"""

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

_HOST_SESSIONS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_SESSIONS} (
  session_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
  metadata_json TEXT NOT NULL,
  created_event_id TEXT NOT NULL,
  created_event_sequence INTEGER NOT NULL,
  closed_event_id TEXT NULL,
  closed_event_sequence INTEGER NULL,
  created_at TEXT NOT NULL,
  closed_at TEXT NULL,
  FOREIGN KEY(created_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(created_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(closed_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(closed_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (closed_event_id IS NULL AND closed_event_sequence IS NULL)
    OR
    (closed_event_id IS NOT NULL AND closed_event_sequence IS NOT NULL)
  ),
  CHECK (
    (status = 'open'
      AND closed_event_id IS NULL
      AND closed_event_sequence IS NULL
      AND closed_at IS NULL)
    OR
    (status = 'closed'
      AND closed_event_id IS NOT NULL
      AND closed_event_sequence IS NOT NULL
      AND closed_at IS NOT NULL)
  )
)
"""

_HOST_SESSION_SLOTS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_SESSION_SLOTS} (
  scope TEXT NOT NULL,
  slot_key TEXT NOT NULL,
  session_id TEXT NOT NULL,
  bound_event_id TEXT NOT NULL,
  bound_event_sequence INTEGER NOT NULL,
  metadata_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(scope, slot_key),
  FOREIGN KEY(session_id) REFERENCES {TABLE_HOST_SESSIONS}(session_id),
  FOREIGN KEY(bound_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(bound_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence)
)
"""

_HOST_RUNS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_RUNS} (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN (
      'queued',
      'running',
      'waiting',
      'cancelling',
      'recovering',
      'succeeded',
      'failed',
      'cancelled',
      'lost'
    )
  ),
  client_request_id TEXT NOT NULL,
  input_event_id TEXT NOT NULL,
  input_event_sequence INTEGER NOT NULL,
  accepted_event_id TEXT NOT NULL,
  accepted_event_sequence INTEGER NOT NULL,
  queued_event_id TEXT NULL,
  queued_event_sequence INTEGER NULL,
  started_event_id TEXT NULL,
  started_event_sequence INTEGER NULL,
  terminal_event_id TEXT NULL,
  terminal_event_sequence INTEGER NULL,
  current_attempt_id TEXT NULL,
  source_run_id TEXT NULL,
  source_run_relation TEXT NULL CHECK (
    source_run_relation IN ('retry', 'replay') OR source_run_relation IS NULL
  ),
  execution_target TEXT NOT NULL,
  queue_policy TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  terminal_at TEXT NULL,
  FOREIGN KEY(session_id) REFERENCES {TABLE_HOST_SESSIONS}(session_id),
  FOREIGN KEY(input_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(input_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(accepted_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(accepted_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(queued_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(queued_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(started_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(started_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(terminal_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(terminal_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(source_run_id) REFERENCES {TABLE_HOST_RUNS}(run_id),
  CHECK (
    status != 'queued'
    OR
    (queued_event_id IS NOT NULL
      AND queued_event_sequence IS NOT NULL
      AND current_attempt_id IS NULL)
  ),
  CHECK (
    status NOT IN ('succeeded', 'failed', 'cancelled', 'lost')
    OR
    (terminal_event_id IS NOT NULL
      AND terminal_event_sequence IS NOT NULL
      AND terminal_at IS NOT NULL)
  ),
  CHECK (
    status IN ('succeeded', 'failed', 'cancelled', 'lost')
    OR
    (terminal_event_id IS NULL
      AND terminal_event_sequence IS NULL
      AND terminal_at IS NULL)
  ),
  CHECK (
    (source_run_id IS NULL AND source_run_relation IS NULL)
    OR
    (source_run_id IS NOT NULL AND source_run_relation IS NOT NULL)
  )
)
"""

_HOST_ATTEMPTS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_ATTEMPTS} (
  attempt_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  execution_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (
    status IN (
      'starting',
      'running',
      'succeeded',
      'failed',
      'cancelled',
      'suspended',
      'steered',
      'lost'
    )
  ),
  started_event_id TEXT NOT NULL,
  started_event_sequence INTEGER NOT NULL,
  terminal_event_id TEXT NULL,
  terminal_event_sequence INTEGER NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  terminal_at TEXT NULL,
  FOREIGN KEY(run_id) REFERENCES {TABLE_HOST_RUNS}(run_id),
  FOREIGN KEY(started_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(started_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(terminal_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(terminal_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    status NOT IN ('succeeded', 'failed', 'cancelled', 'suspended', 'steered', 'lost')
    OR
    (terminal_event_id IS NOT NULL
      AND terminal_event_sequence IS NOT NULL
      AND terminal_at IS NOT NULL)
  ),
  CHECK (
    status IN ('succeeded', 'failed', 'cancelled', 'suspended', 'steered', 'lost')
    OR
    (terminal_event_id IS NULL
      AND terminal_event_sequence IS NULL
      AND terminal_at IS NULL)
  )
)
"""

_HOST_ATTEMPT_DISPATCH_RECORDS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
  dispatch_record_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL UNIQUE,
  execution_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('pending', 'cancelled')),
  worker_kind TEXT NOT NULL CHECK (worker_kind IN ('local', 'remote')),
  execution_target TEXT NOT NULL,
  owner_host_instance_id TEXT NULL,
  created_event_id TEXT NOT NULL,
  created_event_sequence INTEGER NOT NULL,
  cancelled_event_id TEXT NULL,
  cancelled_event_sequence INTEGER NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  cancelled_at TEXT NULL,
  FOREIGN KEY(run_id) REFERENCES {TABLE_HOST_RUNS}(run_id),
  FOREIGN KEY(attempt_id) REFERENCES {TABLE_HOST_ATTEMPTS}(attempt_id),
  FOREIGN KEY(execution_id) REFERENCES {TABLE_HOST_ATTEMPTS}(execution_id),
  FOREIGN KEY(owner_host_instance_id) REFERENCES {TABLE_HOST_INSTANCES}(host_instance_id),
  FOREIGN KEY(created_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(created_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(cancelled_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(cancelled_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (status = 'pending'
      AND cancelled_event_id IS NULL
      AND cancelled_event_sequence IS NULL
      AND cancelled_at IS NULL)
    OR
    (status = 'cancelled'
      AND cancelled_event_id IS NOT NULL
      AND cancelled_event_sequence IS NOT NULL
      AND cancelled_at IS NOT NULL)
  )
)
"""

_HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION}
ON {TABLE_HOST_RUNS}(session_id)
WHERE status IN ('running', 'waiting', 'cancelling', 'recovering')
"""

_HOST_RUNS_QUEUE_FIFO_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_QUEUE_FIFO}
ON {TABLE_HOST_RUNS}(session_id, accepted_event_sequence, run_id)
WHERE status = 'queued'
"""

_HOST_RUNS_SESSION_STATUS_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_SESSION_STATUS}
ON {TABLE_HOST_RUNS}(session_id, status, accepted_event_sequence)
"""

FOUNDATION_DDL: tuple[str, ...] = (
    _SQLITE_PAYLOADS_DDL,
    _PAYLOAD_DESCRIPTORS_DDL,
    _EVENT_LOG_DDL,
    _IDEMPOTENCY_RECORDS_DDL,
    _HOST_INSTANCES_DDL,
)
"""按外键依赖顺序排列的 Phase 2 foundation DDL。"""

PHASE3_STATE_DDL: tuple[str, ...] = (
    _HOST_SESSIONS_DDL,
    _HOST_SESSION_SLOTS_DDL,
    _HOST_RUNS_DDL,
    _HOST_ATTEMPTS_DDL,
    _HOST_ATTEMPT_DISPATCH_RECORDS_DDL,
)
"""按外键依赖顺序排列的 Phase 3 state table DDL。"""

PHASE3_INDEX_DDL: tuple[str, ...] = (
    _HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL,
    _HOST_RUNS_QUEUE_FIFO_INDEX_DDL,
    _HOST_RUNS_SESSION_STATUS_INDEX_DDL,
)
"""Phase 3 state table index DDL。"""

HOST_DURABLE_DDL: tuple[str, ...] = (
    FOUNDATION_DDL + PHASE3_STATE_DDL + PHASE3_INDEX_DDL
)
"""当前 Host durable fresh bootstrap 全量 DDL。"""


def bootstrap_host_durable_store(connection: sqlite3.Connection) -> None:
    """初始化 fresh Host durable SQLite schema 并校验版本。

    ``user_version`` 为 ``0`` 的 DB 被视为 fresh DB；函数会创建 foundation
    与 Phase 3 state tables 并设置 ``PRAGMA user_version = 2``。``user_version`` 为当前版本
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
    for statement in HOST_DURABLE_DDL:
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
