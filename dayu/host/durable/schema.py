"""Host durable SQLite schema bootstrap 与版本校验。

本模块是 Host durable schema convention 的唯一 DDL 真源。它创建 Phase 2
foundation tables、Phase 3 Session / Run / Attempt durable state tables，
Phase 8 projection / read model tables，以及 Phase 9 memory projection
tables；不承载 command、admission、outbox 或 purge 相关逻辑。
"""

from __future__ import annotations

import sqlite3

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

HOST_SCHEMA_VERSION = 7
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

INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION = "host_runs_one_active_per_session"
INDEX_HOST_RUNS_QUEUE_FIFO = "host_runs_queue_fifo"
INDEX_HOST_RUNS_SESSION_STATUS = "host_runs_session_status"
INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN = (
    "host_wait_records_one_active_per_run"
)
INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL = "host_wait_records_active_poll"
INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB = "host_wait_records_external_job"
INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE = (
    "host_run_results_session_terminal_sequence"
)
INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE = (
    "host_session_timeline_items_session_sequence"
)
INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE = (
    "host_session_timeline_items_run_sequence"
)
INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR = (
    "host_memory_snapshots_session_cursor"
)
INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE = "host_memory_items_session_sequence"
INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON = (
    "host_memory_diagnostics_session_reason"
)
INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE = "event_log_run_type_sequence"

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

HOST_DURABLE_TABLES: tuple[str, ...] = (
    FOUNDATION_TABLES
    + PHASE3_STATE_TABLES
    + PROJECTION_TABLES
    + MEMORY_PROJECTION_TABLES
)
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

_EVENT_LOG_RUN_TYPE_SEQUENCE_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}
ON {TABLE_EVENT_LOG}(run_id, event_type, event_sequence)
WHERE run_id IS NOT NULL
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
    (snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL)
  ),
  CHECK (
    (status = 'waiting' AND terminal_at IS NULL)
    OR
    (status IN ('resolved', 'failed', 'cancelled', 'lost')
      AND terminal_at IS NOT NULL)
  ),
  CHECK (
    (resolve_idempotency_key IS NULL AND resolve_semantic_digest IS NULL)
    OR
    (resolve_idempotency_key IS NOT NULL AND resolve_semantic_digest IS NOT NULL)
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
      'verified_fact',
      'working_assumption',
      'raw_user_turn',
      'raw_assistant_turn',
      'assistant_conclusion',
      'episode_summary'
    )
  ),
  claim_status TEXT NOT NULL CHECK (
    claim_status IN (
      'tool_verified',
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
      'missing_fact_summary_fallback',
      'inline_delta_repair_included',
      'snapshot_missing',
      'snapshot_damaged',
      'unsupported_event_type',
      'snapshot_lag_over_threshold',
      'budget_limit_reached',
      'empty_event_log_snapshot'
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

# ``recovering`` 由 Phase 11 recovery owner 写入；当前 P9 transition
# 代码尚不写入该状态，schema 与 active Run 单例约束先保留识别能力。
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

_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN_INDEX_DDL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN}
ON {TABLE_HOST_WAIT_RECORDS}(run_id)
WHERE status = 'waiting'
"""

_HOST_WAIT_RECORDS_ACTIVE_POLL_INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL}
ON {TABLE_HOST_WAIT_RECORDS}(resume_policy, status, deadline_at, expires_at)
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
    _HOST_RUNS_QUEUE_FIFO_INDEX_DDL,
    _HOST_RUNS_SESSION_STATUS_INDEX_DDL,
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

HOST_DURABLE_DDL: tuple[str, ...] = (
    FOUNDATION_DDL
    + PHASE3_STATE_DDL
    + PROJECTION_DDL
    + MEMORY_PROJECTION_DDL
    + FOUNDATION_INDEX_DDL
    + PHASE3_INDEX_DDL
    + PROJECTION_INDEX_DDL
    + MEMORY_PROJECTION_INDEX_DDL
)
"""当前 Host durable fresh bootstrap 全量 DDL。"""


def bootstrap_host_durable_store(connection: sqlite3.Connection) -> None:
    """初始化 fresh Host durable SQLite schema 并校验版本。

    ``user_version`` 为 ``0`` 的 DB 被视为 fresh DB；函数会创建 foundation
    与 Phase 3 state tables 并设置当前 ``PRAGMA user_version``。``user_version`` 为当前版本
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
