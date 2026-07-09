"""Host durable SQLite schema bootstrap 与结构校验。

本模块是 Host durable schema convention 的唯一 DDL 真源。它创建 Phase 2
foundation tables、Phase 3 Session / Run / Attempt durable state tables，
Phase 8 projection / read model tables、Phase 9 memory projection tables、
Phase 13 audit / tool trace / outbox projection-owned tables，以及 Phase 15
purge tombstone governance table；不承载 command、admission 或删除矩阵逻辑。
"""

from __future__ import annotations

import re
import sqlite3

from dayu.host.durable._row_rules import (
    TERMINAL_ATTEMPT_STATUS_VALUES,
    TERMINAL_RUN_STATUS_VALUES,
    terminal_event_refs_required_check_sql,
    terminal_event_refs_unset_check_sql,
    wait_terminal_at_check_sql,
)
from dayu.host.api import (
    HOST_WAIT_ADAPTER_KEY_MAX_LENGTH,
    HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH,
    HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    HOST_WAIT_ID_MAX_LENGTH,
    HOST_WAIT_RESUME_TOKEN_MAX_LENGTH,
    HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH,
    HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH,
    HOST_WAIT_TOOL_NAME_MAX_LENGTH,
)
from dayu.host.durable.errors import HostSchemaMismatchError

HOST_SCHEMA_VERSION = 20
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
TABLE_HOST_WAIT_RECORDS = "host_wait_records"
TABLE_HOST_PROJECTION_CHECKPOINTS = "host_projection_checkpoints"
TABLE_HOST_PROJECTION_FAILURES = "host_projection_failures"
TABLE_HOST_RUN_RESULTS = "host_run_results"
TABLE_HOST_SESSION_TIMELINE_ITEMS = "host_session_timeline_items"
TABLE_HOST_MEMORY_SNAPSHOTS = "host_memory_snapshots"
TABLE_HOST_MEMORY_ITEMS = "host_memory_items"
TABLE_HOST_MEMORY_DIAGNOSTICS = "host_memory_diagnostics"
TABLE_HOST_AUDIT_SINK_MARKERS = "host_audit_sink_markers"
TABLE_HOST_TOOL_TRACE_HOT = "host_tool_trace_hot"
TABLE_HOST_OUTBOX_TERMINAL_ITEMS = "host_outbox_terminal_items"
TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY = "host_outbox_drain_idempotency"
TABLE_HOST_PURGE_TOMBSTONES = "host_purge_tombstones"

INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION = "host_runs_one_active_per_session"
INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION = "host_runs_one_accepted_per_session"
INDEX_HOST_RUNS_QUEUE_FIFO = "host_runs_queue_fifo"
INDEX_HOST_RUNS_SESSION_STATUS = "host_runs_session_status"
INDEX_HOST_RUNS_STATUS_SEQUENCE = "host_runs_status_sequence"
INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN = "host_wait_records_one_active_per_run"
INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL = "host_wait_records_active_poll"
INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB = "host_wait_records_external_job"
INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE = "host_run_results_session_terminal_sequence"
INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE = "host_session_timeline_items_session_sequence"
INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE = "host_session_timeline_items_run_sequence"
INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR = "host_memory_snapshots_session_cursor"
INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE = "host_memory_items_session_sequence"
INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON = "host_memory_diagnostics_session_reason"
INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE = "event_log_run_type_sequence"
INDEX_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE = "host_tool_trace_hot_run_sequence"
INDEX_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE = "host_tool_trace_hot_tool_sequence"
INDEX_HOST_TOOL_TRACE_HOT_TOOL_CALL = "host_tool_trace_hot_tool_call"
INDEX_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST = "host_tool_trace_hot_provider_request"
INDEX_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF = "host_tool_trace_hot_diagnostic_ref"
INDEX_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE = "host_outbox_terminal_items_session_sequence"
INDEX_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE = "host_outbox_terminal_items_state_sequence"
INDEX_HOST_OUTBOX_TERMINAL_ITEMS_RUN = "host_outbox_terminal_items_run"
INDEX_HOST_PURGE_TOMBSTONES_SESSION = "host_purge_tombstones_session"
INDEX_HOST_INSTANCES_STATUS_HEARTBEAT = "host_instances_status_heartbeat"
INDEX_EVENT_LOG_SESSION_SEQUENCE = "event_log_session_sequence"

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
    TABLE_HOST_WAIT_RECORDS,
)
"""Phase 3 Session / Run / Attempt durable state table 名称集合。"""

PROJECTION_TABLES: tuple[str, ...] = (
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
)
"""Phase 8 projection checkpoint / failure / read model table 名称集合。"""

MEMORY_PROJECTION_TABLES: tuple[str, ...] = (
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
)
"""Phase 9 memory projection-owned table 名称集合。"""

AUDIT_PROJECTION_TABLES: tuple[str, ...] = (TABLE_HOST_AUDIT_SINK_MARKERS,)
"""Phase 13 audit sink-local marker table 名称集合。"""

TOOL_TRACE_PROJECTION_TABLES: tuple[str, ...] = (TABLE_HOST_TOOL_TRACE_HOT,)
"""Phase 13 tool trace projection-owned table 名称集合。"""

OUTBOX_PROJECTION_TABLES: tuple[str, ...] = (
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
)
"""Phase 13 outbox projection-owned table 名称集合。"""

PURGE_GOVERNANCE_TABLES: tuple[str, ...] = (TABLE_HOST_PURGE_TOMBSTONES,)
"""Phase 15 purge tombstone governance table 名称集合。"""

HOST_DURABLE_TABLES: tuple[str, ...] = (
    FOUNDATION_TABLES
    + PHASE3_STATE_TABLES
    + PROJECTION_TABLES
    + MEMORY_PROJECTION_TABLES
    + AUDIT_PROJECTION_TABLES
    + TOOL_TRACE_PROJECTION_TABLES
    + OUTBOX_PROJECTION_TABLES
    + PURGE_GOVERNANCE_TABLES
)
"""当前 fresh bootstrap 应创建的 Host durable table 名称集合。"""

HOST_DURABLE_INDEXES: tuple[str, ...] = (
    INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION,
    INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION,
    INDEX_HOST_RUNS_QUEUE_FIFO,
    INDEX_HOST_RUNS_SESSION_STATUS,
    INDEX_HOST_RUNS_STATUS_SEQUENCE,
    INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN,
    INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL,
    INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB,
    INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE,
    INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE,
    INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE,
    INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR,
    INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE,
    INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON,
    INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE,
    INDEX_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE,
    INDEX_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE,
    INDEX_HOST_TOOL_TRACE_HOT_TOOL_CALL,
    INDEX_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST,
    INDEX_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF,
    INDEX_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE,
    INDEX_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE,
    INDEX_HOST_OUTBOX_TERMINAL_ITEMS_RUN,
    INDEX_HOST_PURGE_TOMBSTONES_SESSION,
    INDEX_HOST_INSTANCES_STATUS_HEARTBEAT,
    INDEX_EVENT_LOG_SESSION_SEQUENCE,
)
"""当前 Host durable schema 必须存在的 index 名称集合。"""

_HOST_RUN_TERMINAL_REFS_REQUIRED_CHECK_SQL = terminal_event_refs_required_check_sql(
    status_column="status",
    terminal_status_values=TERMINAL_RUN_STATUS_VALUES,
)
"""Run 终态必须携带 terminal refs 的 CHECK 表达式。"""

_HOST_RUN_TERMINAL_REFS_UNSET_CHECK_SQL = terminal_event_refs_unset_check_sql(
    status_column="status",
    terminal_status_values=TERMINAL_RUN_STATUS_VALUES,
)
"""Run 非终态必须清空 terminal refs 的 CHECK 表达式。"""

_HOST_ATTEMPT_TERMINAL_REFS_REQUIRED_CHECK_SQL = terminal_event_refs_required_check_sql(
    status_column="status",
    terminal_status_values=TERMINAL_ATTEMPT_STATUS_VALUES,
)
"""Attempt 终态必须携带 terminal refs 的 CHECK 表达式。"""

_HOST_ATTEMPT_TERMINAL_REFS_UNSET_CHECK_SQL = terminal_event_refs_unset_check_sql(
    status_column="status",
    terminal_status_values=TERMINAL_ATTEMPT_STATUS_VALUES,
)
"""Attempt 非终态必须清空 terminal refs 的 CHECK 表达式。"""

_HOST_WAIT_TERMINAL_AT_CHECK_SQL = wait_terminal_at_check_sql(status_column="status")
"""WaitRecord status 与 terminal_at 形状 CHECK 表达式。"""

TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND = "tool_call_arguments_json"
"""TOOL_CALL_REQUESTED accepted arguments payload descriptor kind。"""

TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND = "tool_call_semantic_query_text"
"""TOOL_CALL_REQUESTED readable semantic query payload descriptor kind。"""

TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON = "inline_json"
"""TOOL_CALL_REQUESTED accepted arguments 以内联 JSON 存储。"""

TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR = "payload_descriptor"
"""TOOL_CALL_REQUESTED accepted arguments 以 payload descriptor 存储。"""

TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT = "absent"
"""TOOL_CALL_REQUESTED readable semantic query 缺失。"""

TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT = "inline_text"
"""TOOL_CALL_REQUESTED readable semantic query 以内联文本存储。"""

TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR = "payload_descriptor"
"""TOOL_CALL_REQUESTED readable semantic query 以 payload descriptor 存储。"""

RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND = "runner_call_input_manifest"
"""RUNNER_CALL_INPUT_ASSEMBLED manifest body payload descriptor kind。"""

RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION = "runner_call_input_manifest.v1"
"""RUNNER_CALL_INPUT_ASSEMBLED manifest body schema version。"""

RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE = (
    "application/vnd.dayu.runner-call-manifest+json"
)
"""RUNNER_CALL_INPUT_ASSEMBLED manifest body media type。"""

RUNNER_CALL_INPUT_PROJECTION_DESCRIPTOR_KIND = "runner_call_input_projection"
"""RUNNER_CALL_INPUT_ASSEMBLED LLM-facing input projection descriptor kind。"""

RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION = "runner_call_input_projection.v1"
"""RUNNER_CALL_INPUT_ASSEMBLED LLM-facing input projection schema version。"""

RUNNER_CALL_INPUT_PROJECTION_MEDIA_TYPE = (
    "application/vnd.dayu.runner-call-input-projection+json"
)
"""RUNNER_CALL_INPUT_ASSEMBLED LLM-facing input projection media type。"""

SELECTED_TOOL_SCHEMA_SNAPSHOT_DESCRIPTOR_KIND = "selected_tool_schema_snapshot"
"""Runner-call selected tool schema full JSON snapshot descriptor kind。"""

SELECTED_TOOL_SCHEMA_SNAPSHOT_SCHEMA_VERSION = "selected_tool_schema_snapshot.v1"
"""Runner-call selected tool schema full JSON snapshot schema version。"""

SELECTED_TOOL_SCHEMA_SNAPSHOT_MEDIA_TYPE = (
    "application/vnd.dayu.selected-tool-schema-snapshot+json"
)
"""Runner-call selected tool schema full JSON snapshot media type。"""

COMPACTOR_INPUT_PROJECTION_DESCRIPTOR_KIND = "compactor_input_projection"
"""compactor proposal input projection payload descriptor kind。"""

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
  CHECK (
    (payload_ref IS NULL AND payload_digest IS NULL)
    OR
    (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
  )
)
"""

_EVENT_LOG_RUN_TYPE_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}
ON {TABLE_EVENT_LOG}(run_id, event_type, event_sequence)
WHERE run_id IS NOT NULL
"""

_EVENT_LOG_SESSION_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_EVENT_LOG_SESSION_SEQUENCE}
ON {TABLE_EVENT_LOG}(session_id, event_sequence)
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
  FOREIGN KEY(created_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (created_event_id IS NULL AND created_event_sequence IS NULL)
    OR
    (created_event_id IS NOT NULL AND created_event_sequence IS NOT NULL)
  ),
  CHECK (
    created_event_sequence IS NULL OR created_event_sequence > 0
  )
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

_HOST_INSTANCES_STATUS_HEARTBEAT_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_INSTANCES_STATUS_HEARTBEAT}
ON {TABLE_HOST_INSTANCES}(status, heartbeat_at)
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
      'accepted',
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
    status != 'accepted'
    OR
    (queued_event_id IS NULL
      AND queued_event_sequence IS NULL
      AND started_event_id IS NULL
      AND started_event_sequence IS NULL
      AND current_attempt_id IS NULL)
  ),
  CHECK (
    status != 'queued'
    OR
    (queued_event_id IS NOT NULL
      AND queued_event_sequence IS NOT NULL
      AND current_attempt_id IS NULL)
  ),
  CHECK (
    status NOT IN ('running', 'waiting', 'cancelling', 'recovering')
    OR
    (started_event_id IS NOT NULL
      AND started_event_sequence IS NOT NULL)
  ),
  CHECK (
    {_HOST_RUN_TERMINAL_REFS_REQUIRED_CHECK_SQL}
  ),
  CHECK (
    {_HOST_RUN_TERMINAL_REFS_UNSET_CHECK_SQL}
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
    {_HOST_ATTEMPT_TERMINAL_REFS_REQUIRED_CHECK_SQL}
  ),
  CHECK (
    {_HOST_ATTEMPT_TERMINAL_REFS_UNSET_CHECK_SQL}
  )
)
"""

_HOST_ATTEMPT_DISPATCH_RECORDS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
  dispatch_record_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL UNIQUE,
  execution_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (
    status IN ('pending', 'waiting_for_lane', 'dispatching', 'cancelled')
  ),
  worker_kind TEXT NOT NULL CHECK (worker_kind IN ('local', 'remote')),
  execution_target TEXT NOT NULL,
  owner_host_instance_id TEXT NULL,
  created_event_id TEXT NOT NULL,
  created_event_sequence INTEGER NOT NULL,
  waiting_for_lane_at TEXT NULL,
  lane_name TEXT NULL,
  lane_claim_id TEXT NULL,
  lane_owner_id TEXT NULL,
  lane_acquired_at TEXT NULL,
  dispatching_at TEXT NULL,
  worker_accepted_at TEXT NULL,
  worker_accept_event_id TEXT NULL,
  worker_accept_event_sequence INTEGER NULL,
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
  FOREIGN KEY(worker_accept_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(worker_accept_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(cancelled_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(cancelled_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (status = 'pending'
      AND waiting_for_lane_at IS NULL
      AND lane_name IS NULL
      AND lane_claim_id IS NULL
      AND lane_owner_id IS NULL
      AND lane_acquired_at IS NULL
      AND dispatching_at IS NULL
      AND worker_accepted_at IS NULL
      AND worker_accept_event_id IS NULL
      AND worker_accept_event_sequence IS NULL
      AND cancelled_event_id IS NULL
      AND cancelled_event_sequence IS NULL
      AND cancelled_at IS NULL)
    OR
    (status = 'waiting_for_lane'
      AND waiting_for_lane_at IS NOT NULL
      AND lane_name IS NOT NULL
      AND owner_host_instance_id IS NOT NULL
      AND lane_claim_id IS NULL
      AND lane_owner_id IS NULL
      AND lane_acquired_at IS NULL
      AND dispatching_at IS NULL
      AND worker_accepted_at IS NULL
      AND worker_accept_event_id IS NULL
      AND worker_accept_event_sequence IS NULL
      AND cancelled_event_id IS NULL
      AND cancelled_event_sequence IS NULL
      AND cancelled_at IS NULL)
    OR
    (status = 'dispatching'
      AND waiting_for_lane_at IS NOT NULL
      AND lane_name IS NOT NULL
      AND owner_host_instance_id IS NOT NULL
      AND lane_claim_id IS NOT NULL
      AND lane_owner_id IS NOT NULL
      AND lane_acquired_at IS NOT NULL
      AND dispatching_at IS NOT NULL
      AND cancelled_event_id IS NULL
      AND cancelled_event_sequence IS NULL
      AND cancelled_at IS NULL
      AND (
        (worker_accepted_at IS NULL
          AND worker_accept_event_id IS NULL
          AND worker_accept_event_sequence IS NULL)
        OR
        (worker_accepted_at IS NOT NULL
          AND worker_accept_event_id IS NOT NULL
          AND worker_accept_event_sequence IS NOT NULL)
      ))
    OR
    (status = 'cancelled'
      AND cancelled_event_id IS NOT NULL
      AND cancelled_event_sequence IS NOT NULL
      AND cancelled_at IS NOT NULL
      AND worker_accepted_at IS NULL
      AND worker_accept_event_id IS NULL
      AND worker_accept_event_sequence IS NULL)
  )
)
"""

_HOST_WAIT_RECORDS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_WAIT_RECORDS} (
  wait_id TEXT PRIMARY KEY CHECK (
    length(wait_id) BETWEEN 1 AND {HOST_WAIT_ID_MAX_LENGTH}
  ),
  session_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  tool_call_id TEXT NOT NULL CHECK (
    length(tool_call_id) BETWEEN 1 AND {HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH}
  ),
  tool_name TEXT NOT NULL CHECK (
    length(tool_name) BETWEEN 1 AND {HOST_WAIT_TOOL_NAME_MAX_LENGTH}
  ),
  adapter_key TEXT NOT NULL CHECK (
    length(adapter_key) BETWEEN 1 AND {HOST_WAIT_ADAPTER_KEY_MAX_LENGTH}
  ),
  await_kind TEXT NOT NULL,
  resume_policy TEXT NOT NULL CHECK (
    resume_policy IN ('poll', 'callback', 'manual')
  ),
  resume_token TEXT NOT NULL CHECK (
    length(resume_token) BETWEEN 1 AND {HOST_WAIT_RESUME_TOKEN_MAX_LENGTH}
  ),
  snapshot_ref TEXT NULL CHECK (
    snapshot_ref IS NULL
      OR length(snapshot_ref) BETWEEN 1 AND {HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH}
  ),
  snapshot_captured_at TEXT NULL,
  snapshot_digest TEXT NULL,
  external_job_id TEXT NULL CHECK (
    external_job_id IS NULL
      OR length(external_job_id) BETWEEN 1 AND {HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH}
  ),
  accept_idempotency_key TEXT NOT NULL CHECK (
    length(accept_idempotency_key)
      BETWEEN 1 AND {HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH}
  ),
  resolve_idempotency_key TEXT NULL CHECK (
    resolve_idempotency_key IS NULL
      OR length(resolve_idempotency_key)
        BETWEEN 1 AND {HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH}
  ),
  resolve_semantic_digest TEXT NULL,
  deadline_at TEXT NULL,
  expires_at TEXT NULL,
  poll_claim_id TEXT NULL CHECK (
    poll_claim_id IS NULL
      OR length(poll_claim_id) BETWEEN 1 AND {HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH}
  ),
  poll_claim_owner_id TEXT NULL CHECK (
    poll_claim_owner_id IS NULL
      OR length(poll_claim_owner_id) BETWEEN 1 AND {HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH}
  ),
  poll_claimed_at TEXT NULL,
  poll_claim_expires_at TEXT NULL,
  poll_next_observe_at TEXT NULL,
  poll_backoff_attempt INTEGER NOT NULL DEFAULT 0 CHECK (poll_backoff_attempt >= 0),
  poll_last_outcome TEXT NULL CHECK (
    poll_last_outcome IS NULL
      OR poll_last_outcome IN (
        'not_ready',
        'adapter_error',
        'missing_adapter',
        'resolve_error',
        'abandon_error',
        'shutdown_skipped',
        'abandoned',
        'abandon_unsupported',
        'abandon_noop'
      )
  ),
  poll_last_error_code TEXT NULL,
  poll_last_error_message TEXT NULL,
  poll_abandoned_at TEXT NULL,
  status TEXT NOT NULL CHECK (
    status IN ('waiting', 'resolved', 'failed', 'cancelled', 'lost')
  ),
  created_event_id TEXT NOT NULL,
  created_event_sequence INTEGER NOT NULL,
  updated_event_id TEXT NOT NULL,
  updated_event_sequence INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  terminal_at TEXT NULL,
  FOREIGN KEY(session_id) REFERENCES {TABLE_HOST_SESSIONS}(session_id),
  FOREIGN KEY(run_id) REFERENCES {TABLE_HOST_RUNS}(run_id),
  FOREIGN KEY(attempt_id) REFERENCES {TABLE_HOST_ATTEMPTS}(attempt_id),
  FOREIGN KEY(execution_id) REFERENCES {TABLE_HOST_ATTEMPTS}(execution_id),
  FOREIGN KEY(created_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(created_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  FOREIGN KEY(updated_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(updated_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (snapshot_ref IS NULL
      AND snapshot_captured_at IS NULL
      AND snapshot_digest IS NULL)
    OR
    (snapshot_ref IS NOT NULL
      AND snapshot_captured_at IS NOT NULL
      AND snapshot_digest IS NOT NULL)
  ),
  CHECK (
    {_HOST_WAIT_TERMINAL_AT_CHECK_SQL}
  ),
  CHECK (
    (resolve_idempotency_key IS NULL AND resolve_semantic_digest IS NULL)
    OR
    (resolve_idempotency_key IS NOT NULL AND resolve_semantic_digest IS NOT NULL)
  ),
  CHECK (
    (poll_claim_id IS NULL
      AND poll_claim_owner_id IS NULL
      AND poll_claimed_at IS NULL
      AND poll_claim_expires_at IS NULL)
    OR
    (poll_claim_id IS NOT NULL
      AND poll_claim_owner_id IS NOT NULL
      AND poll_claimed_at IS NOT NULL
      AND poll_claim_expires_at IS NOT NULL)
  ),
  CHECK (
    poll_abandoned_at IS NULL OR status = 'cancelled'
  )
)
"""

_HOST_PROJECTION_CHECKPOINTS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_PROJECTION_CHECKPOINTS} (
  consumer_id TEXT PRIMARY KEY,
  checkpoint_event_sequence INTEGER NOT NULL CHECK (
    checkpoint_event_sequence >= 0
  ),
  checkpoint_event_id TEXT NULL,
  last_success_at TEXT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(checkpoint_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  CHECK (
    (checkpoint_event_sequence = 0 AND checkpoint_event_id IS NULL)
    OR
    (checkpoint_event_sequence > 0 AND checkpoint_event_id IS NOT NULL)
  )
)
"""

_HOST_PROJECTION_FAILURES_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_PROJECTION_FAILURES} (
  consumer_id TEXT PRIMARY KEY,
  failed_event_sequence INTEGER NOT NULL CHECK (failed_event_sequence > 0),
  failed_event_id TEXT NOT NULL,
  failure_count INTEGER NOT NULL CHECK (failure_count > 0),
  last_error_code TEXT NOT NULL,
  last_error_message TEXT NOT NULL,
  first_failed_at TEXT NOT NULL,
  last_failed_at TEXT NOT NULL,
  retry_after TEXT NULL,
  FOREIGN KEY(failed_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id)
)
"""

_HOST_RUN_RESULTS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_RUN_RESULTS} (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  terminal_status TEXT NOT NULL CHECK (
    terminal_status IN ('succeeded', 'failed', 'cancelled', 'lost')
  ),
  terminal_event_id TEXT NOT NULL UNIQUE,
  terminal_event_sequence INTEGER NOT NULL,
  result_ref TEXT NULL,
  result_digest TEXT NULL,
  summary_ref TEXT NULL,
  summary_digest TEXT NULL,
  projected_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES {TABLE_HOST_RUNS}(run_id),
  FOREIGN KEY(session_id) REFERENCES {TABLE_HOST_SESSIONS}(session_id),
  FOREIGN KEY(terminal_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(terminal_event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (result_ref IS NULL AND result_digest IS NULL)
    OR
    (result_ref IS NOT NULL AND result_digest IS NOT NULL)
  ),
  CHECK (
    (summary_ref IS NULL AND summary_digest IS NULL)
    OR
    (summary_ref IS NOT NULL AND summary_digest IS NOT NULL)
  )
)
"""

_HOST_SESSION_TIMELINE_ITEMS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_SESSION_TIMELINE_ITEMS} (
  timeline_item_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT NULL,
  event_id TEXT NOT NULL UNIQUE,
  event_sequence INTEGER NOT NULL,
  item_kind TEXT NOT NULL,
  event_type TEXT NOT NULL,
  display_text TEXT NULL,
  payload_ref TEXT NULL,
  payload_digest TEXT NULL,
  projected_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES {TABLE_HOST_SESSIONS}(session_id),
  FOREIGN KEY(run_id) REFERENCES {TABLE_HOST_RUNS}(run_id),
  FOREIGN KEY(event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (payload_ref IS NULL AND payload_digest IS NULL)
    OR
    (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
  )
)
"""

_HOST_MEMORY_SNAPSHOTS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_MEMORY_SNAPSHOTS} (
  snapshot_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  consumer_id TEXT NOT NULL,
  checkpoint_event_sequence INTEGER NOT NULL CHECK (
    checkpoint_event_sequence >= 0
  ),
  checkpoint_event_id TEXT NULL,
  policy_digest TEXT NOT NULL,
  snapshot_digest TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  built_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(checkpoint_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  CHECK (
    (checkpoint_event_sequence = 0 AND checkpoint_event_id IS NULL)
    OR
    (checkpoint_event_sequence > 0 AND checkpoint_event_id IS NOT NULL)
  )
)
"""

_HOST_MEMORY_ITEMS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_MEMORY_ITEMS} (
  item_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
    item_kind TEXT NOT NULL CHECK (
    item_kind IN (
      'evidence_backed_fact',
      'selected_recent_window',
      'reference_continuity',
      'answer_anchor',
      'forward_intent',
      'session_summary'
    )
  ),
  claim_status TEXT NOT NULL CHECK (
    claim_status IN (
      'evidence_backed',
      'assumption',
      'candidate',
      'conflicted',
      'stale',
      'superseded'
    )
  ),
  event_id TEXT NOT NULL,
  event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
  producer_kind TEXT NOT NULL CHECK (
    producer_kind IN ('tool', 'user', 'assistant', 'host_projection')
  ),
  producer_name TEXT NOT NULL,
  payload_ref TEXT NULL,
  payload_digest TEXT NULL,
  item_json TEXT NOT NULL,
  included_reason TEXT NULL,
  excluded_reason TEXT NULL,
  FOREIGN KEY(snapshot_id) REFERENCES {TABLE_HOST_MEMORY_SNAPSHOTS}(snapshot_id)
    ON DELETE CASCADE,
  FOREIGN KEY(event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (payload_ref IS NULL AND payload_digest IS NULL)
    OR
    (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
  ),
  CHECK (included_reason IS NULL OR excluded_reason IS NULL)
)
"""

_HOST_MEMORY_DIAGNOSTICS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_MEMORY_DIAGNOSTICS} (
  diagnostic_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  snapshot_id TEXT NULL,
  reason TEXT NOT NULL CHECK (
    reason IN (
      'evidence_backed_fact_candidate_invalid',
      'accepted_evidence_without_fact_candidate',
      'inline_delta_repair_included',
      'snapshot_missing',
      'snapshot_damaged',
      'unsupported_event_type',
      'snapshot_lag_over_threshold',
      'budget_limit_reached',
      'empty_event_log_snapshot',
      'evidence_backed_fact_superseded'
    )
  ),
  event_sequence INTEGER NULL CHECK (
    event_sequence IS NULL OR event_sequence > 0
  ),
  policy_digest TEXT NULL,
  diagnostic_json TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  FOREIGN KEY(snapshot_id) REFERENCES {TABLE_HOST_MEMORY_SNAPSHOTS}(snapshot_id)
    ON DELETE CASCADE
)
"""

_HOST_AUDIT_SINK_MARKERS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_AUDIT_SINK_MARKERS} (
  event_id TEXT PRIMARY KEY,
  event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
  line_digest TEXT NOT NULL,
  written_at TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence)
)
"""

_HOST_TOOL_TRACE_HOT_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_TOOL_TRACE_HOT} (
  trace_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
  event_type TEXT NOT NULL,
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
  tool_call_id TEXT NULL,
  tool_name TEXT NULL,
  provider_request_id TEXT NULL,
  diagnostic_ref TEXT NULL,
  normalized_arguments_digest TEXT NULL,
  semantic_input_digest TEXT NULL,
  result_digest TEXT NULL,
  payload_ref TEXT NULL,
  payload_digest TEXT NULL,
  policy_decision_json TEXT NULL,
  trace_summary_json TEXT NOT NULL,
  cold_trace_ref TEXT NULL,
  cold_trace_digest TEXT NULL,
  projected_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (payload_ref IS NULL AND payload_digest IS NULL)
    OR
    (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
  ),
  CHECK (
    (cold_trace_ref IS NULL AND cold_trace_digest IS NULL)
    OR
    (cold_trace_ref IS NOT NULL AND cold_trace_digest IS NOT NULL)
  )
)
"""

_HOST_OUTBOX_TERMINAL_ITEMS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_OUTBOX_TERMINAL_ITEMS} (
  item_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  terminal_event_id TEXT NOT NULL UNIQUE,
  event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
  session_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  terminal_status TEXT NOT NULL CHECK (
    terminal_status IN ('succeeded', 'failed', 'cancelled')
  ),
  dedupe_key TEXT NOT NULL,
  final_answer_json TEXT NULL,
  error_message TEXT NULL,
  cancel_reason TEXT NULL,
  result_ref TEXT NULL,
  result_digest TEXT NULL,
  terminal_summary_ref TEXT NULL,
  terminal_summary_digest TEXT NULL,
  item_state TEXT NOT NULL CHECK (item_state IN ('pending', 'drained')),
  projected_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  drained_at TEXT NULL,
  last_drain_request_id TEXT NULL,
  FOREIGN KEY(terminal_event_id) REFERENCES {TABLE_EVENT_LOG}(event_id),
  FOREIGN KEY(event_sequence) REFERENCES {TABLE_EVENT_LOG}(event_sequence),
  CHECK (
    (result_ref IS NULL AND result_digest IS NULL)
    OR
    (result_ref IS NOT NULL AND result_digest IS NOT NULL)
  ),
  CHECK (
    (terminal_summary_ref IS NULL AND terminal_summary_digest IS NULL)
    OR
    (terminal_summary_ref IS NOT NULL AND terminal_summary_digest IS NOT NULL)
  ),
  CHECK (
    (item_state = 'pending'
      AND drained_at IS NULL
      AND last_drain_request_id IS NULL)
    OR
    (item_state = 'drained'
      AND drained_at IS NOT NULL
      AND last_drain_request_id IS NOT NULL)
  )
)
"""

_HOST_OUTBOX_DRAIN_IDEMPOTENCY_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY} (
  session_id TEXT NOT NULL,
  drain_request_id TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  batch_item_ids_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(session_id, drain_request_id)
)
"""

_HOST_PURGE_TOMBSTONES_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_HOST_PURGE_TOMBSTONES} (
  tombstone_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  client_request_id TEXT NOT NULL,
  semantic_request_digest TEXT NOT NULL,
  actor TEXT NULL,
  source TEXT NULL,
  operation_context_digest TEXT NULL,
  operation_context_refs_json TEXT NOT NULL,
  reason TEXT NOT NULL,
  purged_at TEXT NOT NULL,
  precondition_digest TEXT NOT NULL,
  deleted_counts_json TEXT NOT NULL,
  deleted_counts_digest TEXT NOT NULL,
  deleted_refs_digest TEXT NOT NULL,
  audit_record_ref TEXT NOT NULL,
  audit_record_digest TEXT NOT NULL,
  request_context_json TEXT NOT NULL
)
"""

# ``recovering`` 由 Phase 11 recovery owner 写入；当前 P9 transition
# 代码尚不写入该状态，schema 与 active Run 单例约束先保留识别能力。
_HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION}
ON {TABLE_HOST_RUNS}(session_id)
WHERE status IN ('accepted', 'running', 'waiting', 'cancelling', 'recovering')
"""

_HOST_RUNS_ONE_ACCEPTED_PER_SESSION_INDEX_DDL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION}
ON {TABLE_HOST_RUNS}(session_id)
WHERE status = 'accepted'
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

_HOST_RUNS_STATUS_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_STATUS_SEQUENCE}
ON {TABLE_HOST_RUNS}(status, accepted_event_sequence, run_id)
"""

_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN_INDEX_DDL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN}
ON {TABLE_HOST_WAIT_RECORDS}(run_id)
WHERE status = 'waiting'
"""

_HOST_WAIT_RECORDS_ACTIVE_POLL_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL}
ON {TABLE_HOST_WAIT_RECORDS}(
  resume_policy,
  status,
  poll_next_observe_at,
  poll_claim_expires_at,
  created_event_sequence,
  wait_id
)
"""

_HOST_WAIT_RECORDS_EXTERNAL_JOB_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB}
ON {TABLE_HOST_WAIT_RECORDS}(adapter_key, external_job_id)
WHERE external_job_id IS NOT NULL
"""

_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE}
ON {TABLE_HOST_RUN_RESULTS}(session_id, terminal_event_sequence)
"""

_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE}
ON {TABLE_HOST_SESSION_TIMELINE_ITEMS}(session_id, event_sequence)
"""

_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE}
ON {TABLE_HOST_SESSION_TIMELINE_ITEMS}(run_id, event_sequence)
WHERE run_id IS NOT NULL
"""

_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR}
ON {TABLE_HOST_MEMORY_SNAPSHOTS}(
  session_id,
  consumer_id,
  policy_digest,
  checkpoint_event_sequence
)
"""

_HOST_MEMORY_ITEMS_SESSION_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE}
ON {TABLE_HOST_MEMORY_ITEMS}(session_id, event_sequence, item_kind)
"""

_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON}
ON {TABLE_HOST_MEMORY_DIAGNOSTICS}(session_id, reason, recorded_at)
"""

_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE}
ON {TABLE_HOST_TOOL_TRACE_HOT}(run_id, event_sequence)
WHERE run_id IS NOT NULL
"""

_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE}
ON {TABLE_HOST_TOOL_TRACE_HOT}(tool_name, event_sequence)
WHERE tool_name IS NOT NULL
"""

_HOST_TOOL_TRACE_HOT_TOOL_CALL_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_TOOL_TRACE_HOT_TOOL_CALL}
ON {TABLE_HOST_TOOL_TRACE_HOT}(tool_call_id)
WHERE tool_call_id IS NOT NULL
"""

_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST}
ON {TABLE_HOST_TOOL_TRACE_HOT}(provider_request_id)
WHERE provider_request_id IS NOT NULL
"""

_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF}
ON {TABLE_HOST_TOOL_TRACE_HOT}(diagnostic_ref)
WHERE diagnostic_ref IS NOT NULL
"""

_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE}
ON {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}(session_id, event_sequence)
"""

_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE}
ON {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}(item_state, event_sequence)
"""

_HOST_OUTBOX_TERMINAL_ITEMS_RUN_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_OUTBOX_TERMINAL_ITEMS_RUN}
ON {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}(run_id)
"""

_HOST_PURGE_TOMBSTONES_SESSION_INDEX_DDL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_PURGE_TOMBSTONES_SESSION}
ON {TABLE_HOST_PURGE_TOMBSTONES}(session_id)
"""

FOUNDATION_DDL: tuple[str, ...] = (
    _SQLITE_PAYLOADS_DDL,
    _PAYLOAD_DESCRIPTORS_DDL,
    _EVENT_LOG_DDL,
    _IDEMPOTENCY_RECORDS_DDL,
    _HOST_INSTANCES_DDL,
)
"""按外键依赖顺序排列的 Phase 2 foundation DDL。"""

FOUNDATION_INDEX_DDL: tuple[str, ...] = (
    _EVENT_LOG_RUN_TYPE_SEQUENCE_INDEX_DDL,
    _EVENT_LOG_SESSION_SEQUENCE_INDEX_DDL,
    _HOST_INSTANCES_STATUS_HEARTBEAT_INDEX_DDL,
)
"""Phase 2 foundation table index DDL。"""

PHASE3_STATE_DDL: tuple[str, ...] = (
    _HOST_SESSIONS_DDL,
    _HOST_SESSION_SLOTS_DDL,
    _HOST_RUNS_DDL,
    _HOST_ATTEMPTS_DDL,
    _HOST_ATTEMPT_DISPATCH_RECORDS_DDL,
    _HOST_WAIT_RECORDS_DDL,
)
"""按外键依赖顺序排列的 Phase 3 state table DDL。"""

PHASE3_INDEX_DDL: tuple[str, ...] = (
    _HOST_RUNS_ONE_ACTIVE_PER_SESSION_INDEX_DDL,
    _HOST_RUNS_ONE_ACCEPTED_PER_SESSION_INDEX_DDL,
    _HOST_RUNS_QUEUE_FIFO_INDEX_DDL,
    _HOST_RUNS_SESSION_STATUS_INDEX_DDL,
    _HOST_RUNS_STATUS_SEQUENCE_INDEX_DDL,
    _HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN_INDEX_DDL,
    _HOST_WAIT_RECORDS_ACTIVE_POLL_INDEX_DDL,
    _HOST_WAIT_RECORDS_EXTERNAL_JOB_INDEX_DDL,
)
"""Phase 3 state table index DDL。"""

PROJECTION_DDL: tuple[str, ...] = (
    _HOST_PROJECTION_CHECKPOINTS_DDL,
    _HOST_PROJECTION_FAILURES_DDL,
    _HOST_RUN_RESULTS_DDL,
    _HOST_SESSION_TIMELINE_ITEMS_DDL,
)
"""按外键依赖顺序排列的 Phase 8 projection / read model table DDL。"""

MEMORY_PROJECTION_DDL: tuple[str, ...] = (
    _HOST_MEMORY_SNAPSHOTS_DDL,
    _HOST_MEMORY_ITEMS_DDL,
    _HOST_MEMORY_DIAGNOSTICS_DDL,
)
"""按外键依赖顺序排列的 Phase 9 memory projection table DDL。"""

AUDIT_PROJECTION_DDL: tuple[str, ...] = (_HOST_AUDIT_SINK_MARKERS_DDL,)
"""按外键依赖顺序排列的 Phase 13 audit sink-local marker DDL。"""

TOOL_TRACE_PROJECTION_DDL: tuple[str, ...] = (_HOST_TOOL_TRACE_HOT_DDL,)
"""按外键依赖顺序排列的 Phase 13 tool trace projection DDL。"""

OUTBOX_PROJECTION_DDL: tuple[str, ...] = (
    _HOST_OUTBOX_TERMINAL_ITEMS_DDL,
    _HOST_OUTBOX_DRAIN_IDEMPOTENCY_DDL,
)
"""按外键依赖顺序排列的 Phase 13 outbox projection DDL。"""

PURGE_GOVERNANCE_DDL: tuple[str, ...] = (_HOST_PURGE_TOMBSTONES_DDL,)
"""按外键依赖顺序排列的 Phase 15 purge tombstone governance DDL。"""

PROJECTION_INDEX_DDL: tuple[str, ...] = (
    _HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE_INDEX_DDL,
    _HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE_INDEX_DDL,
    _HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE_INDEX_DDL,
)
"""Phase 8 projection / read model index DDL。"""

MEMORY_PROJECTION_INDEX_DDL: tuple[str, ...] = (
    _HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR_INDEX_DDL,
    _HOST_MEMORY_ITEMS_SESSION_SEQUENCE_INDEX_DDL,
    _HOST_MEMORY_DIAGNOSTICS_SESSION_REASON_INDEX_DDL,
)
"""Phase 9 memory projection index DDL。"""

TOOL_TRACE_PROJECTION_INDEX_DDL: tuple[str, ...] = (
    _HOST_TOOL_TRACE_HOT_RUN_SEQUENCE_INDEX_DDL,
    _HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE_INDEX_DDL,
    _HOST_TOOL_TRACE_HOT_TOOL_CALL_INDEX_DDL,
    _HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST_INDEX_DDL,
    _HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF_INDEX_DDL,
)
"""Phase 13 tool trace projection index DDL。"""

OUTBOX_PROJECTION_INDEX_DDL: tuple[str, ...] = (
    _HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE_INDEX_DDL,
    _HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE_INDEX_DDL,
    _HOST_OUTBOX_TERMINAL_ITEMS_RUN_INDEX_DDL,
)
"""Phase 13 outbox projection index DDL。"""

PURGE_GOVERNANCE_INDEX_DDL: tuple[str, ...] = (_HOST_PURGE_TOMBSTONES_SESSION_INDEX_DDL,)
"""Phase 15 purge tombstone governance index DDL。"""

HOST_DURABLE_DDL: tuple[str, ...] = (
    FOUNDATION_DDL
    + PHASE3_STATE_DDL
    + PROJECTION_DDL
    + MEMORY_PROJECTION_DDL
    + AUDIT_PROJECTION_DDL
    + TOOL_TRACE_PROJECTION_DDL
    + OUTBOX_PROJECTION_DDL
    + PURGE_GOVERNANCE_DDL
    + FOUNDATION_INDEX_DDL
    + PHASE3_INDEX_DDL
    + PROJECTION_INDEX_DDL
    + MEMORY_PROJECTION_INDEX_DDL
    + TOOL_TRACE_PROJECTION_INDEX_DDL
    + OUTBOX_PROJECTION_INDEX_DDL
    + PURGE_GOVERNANCE_INDEX_DDL
)
"""当前 Host durable fresh bootstrap 全量 DDL。"""

_SCHEMA_OBJECT_TYPE_TABLE = "table"
"""SQLite catalog 中 table object type 名称。"""

_SCHEMA_OBJECT_TYPE_INDEX = "index"
"""SQLite catalog 中 index object type 名称。"""

_SQLITE_MASTER_SQL_QUERY_TEMPLATE = """
SELECT type, name, sql
FROM sqlite_master
WHERE (type = ? AND name IN ({table_placeholders}))
OR (type = ? AND name IN ({index_placeholders}))
"""
"""读取 required table / index SQLite catalog SQL 的查询模板。"""

_WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
"""schema SQL 最小归一化使用的连续空白匹配模式。"""

_SchemaObjectKey = tuple[str, str]
"""SQLite schema object key，格式为 ``(object_type, object_name)``。"""

_MISSING_REQUIRED_OBJECTS_SEPARATOR = "; "
"""批量缺失 schema object 诊断片段分隔符。"""


def bootstrap_host_durable_store(connection: sqlite3.Connection) -> None:
    """初始化 fresh Host durable SQLite schema 或校验当前 schema。

    ``user_version`` 为 ``0`` 的 DB 被视为 fresh DB；函数会在显式事务中创建
    全量 Host durable schema 并设置当前 ``PRAGMA user_version``。``user_version``
    为当前版本时只执行结构校验，不执行 DDL，不修复缺失对象。其它版本一律
    结构化失败，不做兼容读取或迁移。

    :param connection: 已完成 PRAGMA setup 的 SQLite connection。
    :returns: ``None``。
    :raises HostSchemaMismatchError: DB schema version 不匹配或当前 schema
        缺少 required table / index 时抛出。
    :raises sqlite3.Error: SQLite DDL 或 PRAGMA 执行失败时抛出。
    """

    current_version = _read_user_version(connection)
    if current_version == 0:
        _bootstrap_fresh_schema(connection)
        validate_host_durable_schema(connection)
        return
    if current_version == HOST_SCHEMA_VERSION:
        validate_host_durable_schema(connection)
        return
    raise HostSchemaMismatchError(
        "Host durable schema version mismatch: "
        f"expected fresh schema {HOST_SCHEMA_VERSION}, got {current_version}; "
        "recreate the durable database for this version"
    )


def validate_host_durable_schema(connection: sqlite3.Connection) -> None:
    """校验 Host durable SQLite 当前 schema 结构。

    校验范围包括 ``PRAGMA user_version``、required tables、required indexes，
    以及 required table / index 的 SQLite catalog SQL 定义。本函数不执行 DDL，
    不尝试迁移或修复缺失对象。

    :param connection: SQLite connection。
    :returns: ``None``。
    :raises HostSchemaMismatchError: ``user_version`` 不是当前版本，缺少
        required table / index，或 required object 定义不匹配时抛出。
    :raises sqlite3.Error: PRAGMA 或 sqlite_master 查询失败时抛出。
    """

    current_version = _read_user_version(connection)
    if current_version != HOST_SCHEMA_VERSION:
        raise HostSchemaMismatchError(
            "Host durable schema version mismatch: "
            f"expected fresh schema {HOST_SCHEMA_VERSION}, got {current_version}; "
            "recreate the durable database for this version"
        )
    _validate_required_objects_exist(connection)
    _validate_required_object_definitions(connection)


def _bootstrap_fresh_schema(connection: sqlite3.Connection) -> None:
    """在一个显式 SQLite 事务中创建 fresh Host durable schema。

    :param connection: 已完成 PRAGMA setup 且处于 autocommit 模式
        （``isolation_level=None``）的 SQLite connection；本函数会自行开启
        ``BEGIN IMMEDIATE`` 显式事务。
    :returns: ``None``。
    :raises sqlite3.Error: BEGIN、DDL、user_version 设置、COMMIT 或 ROLLBACK
        执行失败时抛出原始 SQLite 异常；ROLLBACK 失败只做 best-effort 清理。
    """

    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in HOST_DURABLE_DDL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version={HOST_SCHEMA_VERSION}")
        connection.execute("COMMIT")
    except sqlite3.Error:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def _validate_required_objects_exist(connection: sqlite3.Connection) -> None:
    """校验当前 DB 包含所有 Host durable required schema objects。

    :param connection: SQLite connection。
    :returns: ``None``。
    :raises HostSchemaMismatchError: 缺少 required table / index 时抛出，并在
        多个对象缺失时批量报告。
    :raises sqlite3.Error: sqlite_master 查询失败时抛出。
    """

    missing_tables = _missing_required_tables(connection)
    missing_indexes = _missing_required_indexes(connection)
    if missing_tables or missing_indexes:
        raise HostSchemaMismatchError(
            _missing_required_objects_message(
                missing_tables=missing_tables,
                missing_indexes=missing_indexes,
            )
        )


def _missing_required_tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    """返回当前 DB 缺失的 Host durable required tables。

    :param connection: SQLite connection。
    :returns: 按 ``HOST_DURABLE_TABLES`` 顺序排列的缺失 table 名称。
    :raises sqlite3.Error: sqlite_master 查询失败时抛出。
    """

    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    existing_tables = frozenset(str(row[0]) for row in rows)
    return tuple(
        table_name
        for table_name in HOST_DURABLE_TABLES
        if table_name not in existing_tables
    )


def _missing_required_indexes(connection: sqlite3.Connection) -> tuple[str, ...]:
    """返回当前 DB 缺失的 Host durable required indexes。

    :param connection: SQLite connection。
    :returns: 按 ``HOST_DURABLE_INDEXES`` 顺序排列的缺失 index 名称。
    :raises sqlite3.Error: sqlite_master 查询失败时抛出。
    """

    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    existing_indexes = frozenset(str(row[0]) for row in rows)
    return tuple(
        index_name
        for index_name in HOST_DURABLE_INDEXES
        if index_name not in existing_indexes
    )


def _missing_required_objects_message(
    *,
    missing_tables: tuple[str, ...],
    missing_indexes: tuple[str, ...],
) -> str:
    """构造 required schema object 缺失诊断消息。

    单个 table 或 index 缺失时保留精确单对象消息；多个对象缺失时批量列出，
    方便一次定位 schema 损坏范围。

    :param missing_tables: 缺失的 required table 名称。
    :param missing_indexes: 缺失的 required index 名称。
    :returns: Host schema mismatch 诊断消息。
    :raises HostSchemaMismatchError: 本函数不主动抛出。
    """

    if len(missing_tables) == 1 and not missing_indexes:
        return f"Host durable schema missing required table: {missing_tables[0]}"
    if len(missing_indexes) == 1 and not missing_tables:
        return f"Host durable schema missing required index: {missing_indexes[0]}"

    message_parts: list[str] = []
    if missing_tables:
        message_parts.append("tables: " + ", ".join(missing_tables))
    if missing_indexes:
        message_parts.append("indexes: " + ", ".join(missing_indexes))
    return (
        "Host durable schema missing required objects: "
        + _MISSING_REQUIRED_OBJECTS_SEPARATOR.join(message_parts)
    )


def _validate_required_object_definitions(connection: sqlite3.Connection) -> None:
    """校验 required table / index 的 SQLite catalog SQL 定义。

    expected 定义由当前 ``HOST_DURABLE_DDL`` 在内存 fresh DB 中生成，确保 DDL
    真源仍只有一份；目标 DB 只比较 ``HOST_DURABLE_TABLES`` 与
    ``HOST_DURABLE_INDEXES`` 指定的对象，忽略 SQLite 内部对象。

    :param connection: SQLite connection。
    :returns: ``None``。
    :raises HostSchemaMismatchError: required object 定义缺失或不匹配时抛出。
    :raises sqlite3.Error: sqlite_master 查询或内存 DDL 执行失败时抛出。
    """

    expected_sql_by_name = _expected_schema_sql_by_name()
    actual_sql_by_name = _read_schema_sql_by_name(connection)
    for object_type, object_name in _required_schema_object_keys():
        expected_sql = expected_sql_by_name.get((object_type, object_name))
        actual_sql = actual_sql_by_name.get((object_type, object_name))
        if expected_sql is None or actual_sql is None or actual_sql != expected_sql:
            raise HostSchemaMismatchError(
                "Host durable schema definition mismatch: "
                f"{object_type} {object_name}"
            )


def _expected_schema_sql_by_name() -> dict[_SchemaObjectKey, str]:
    """从当前 DDL 真源生成 expected SQLite catalog SQL。

    本函数创建内存 SQLite fresh DB，执行 ``HOST_DURABLE_DDL``，再读取 required
    table / index 的 ``sqlite_master.sql``，避免维护第二份手写 expected DDL。

    :returns: 以 ``(object_type, object_name)`` 为 key 的归一化 catalog SQL。
    :raises HostSchemaMismatchError: DDL 执行后 required object 未出现在 catalog
        中时抛出。
    :raises sqlite3.Error: 内存 DDL 执行或 sqlite_master 查询失败时抛出。
    """

    connection = sqlite3.connect(":memory:")
    try:
        for statement in HOST_DURABLE_DDL:
            connection.execute(statement)
        sql_by_name = _read_schema_sql_by_name(connection)
    finally:
        connection.close()

    for object_type, object_name in _required_schema_object_keys():
        if (object_type, object_name) not in sql_by_name:
            raise HostSchemaMismatchError(
                "Host durable schema definition mismatch: "
                f"{object_type} {object_name}"
            )
    return sql_by_name


def _read_schema_sql_by_name(connection: sqlite3.Connection) -> dict[_SchemaObjectKey, str]:
    """读取 required table / index 的 SQLite catalog SQL。

    :param connection: SQLite connection。
    :returns: 以 ``(object_type, object_name)`` 为 key 的归一化 catalog SQL。
    :raises sqlite3.Error: sqlite_master 查询失败时抛出。
    """

    table_placeholders = _sqlite_placeholders(len(HOST_DURABLE_TABLES))
    index_placeholders = _sqlite_placeholders(len(HOST_DURABLE_INDEXES))
    rows = connection.execute(
        _SQLITE_MASTER_SQL_QUERY_TEMPLATE.format(
            table_placeholders=table_placeholders,
            index_placeholders=index_placeholders,
        ),
        (
            _SCHEMA_OBJECT_TYPE_TABLE,
            *HOST_DURABLE_TABLES,
            _SCHEMA_OBJECT_TYPE_INDEX,
            *HOST_DURABLE_INDEXES,
        ),
    ).fetchall()
    sql_by_name: dict[_SchemaObjectKey, str] = {}
    for row in rows:
        object_type = str(row[0])
        object_name = str(row[1])
        schema_sql_value = row[2]
        if schema_sql_value is not None:
            sql_by_name[(object_type, object_name)] = _normalize_schema_sql(str(schema_sql_value))
    return sql_by_name


def _required_schema_object_keys() -> tuple[_SchemaObjectKey, ...]:
    """返回需要比较 SQLite catalog SQL 的 required object key。

    :returns: required table / index key 元组。
    :raises HostSchemaMismatchError: 本函数不主动抛出。
    """

    return tuple(
        (_SCHEMA_OBJECT_TYPE_TABLE, table_name) for table_name in HOST_DURABLE_TABLES
    ) + tuple(
        (_SCHEMA_OBJECT_TYPE_INDEX, index_name) for index_name in HOST_DURABLE_INDEXES
    )


def _normalize_schema_sql(sql: str) -> str:
    """按最小规则归一化 SQLite catalog SQL。

    归一化只去除首尾空白，并把任意连续空白折叠为单个 ASCII space。函数保持
    大小写、identifier quoting、标点和 SQL clause 顺序，不解析 SQL。

    :param sql: SQLite catalog SQL。
    :returns: 最小 whitespace 归一化后的 SQL。
    :raises HostSchemaMismatchError: 本函数不主动抛出。
    """

    return _WHITESPACE_RUN_PATTERN.sub(" ", sql.strip())


def _sqlite_placeholders(value_count: int) -> str:
    """生成 SQLite 参数占位符列表。

    :param value_count: 需要生成的占位符数量。
    :returns: 逗号分隔的 ``?`` 占位符字符串。
    :raises HostSchemaMismatchError: 占位符数量不是正整数时抛出。
    """

    if value_count <= 0:
        raise HostSchemaMismatchError(
            "Host durable schema definition mismatch: required object set is empty"
        )
    return ",".join("?" for _index in range(value_count))


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
