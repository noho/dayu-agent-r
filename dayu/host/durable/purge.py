"""Host purge tombstone durable primitive。

本模块只负责 purge tombstone row codec、稳定 digest 与 purge command 的
durable 幂等 replay 判定。它不实现 public ``purge_session``，不删除
Session / EventLog facts，也不写 audit JSONL。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_optional_sha256_digest as _require_optional_sha256_digest,
    require_sha256_digest as _require_sha256_digest,
    require_text as _require_text,
)
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError, HostIdempotencyConflictError
from dayu.host.durable.idempotency import (
    IdempotencyRecord,
    IdempotencyResultRef,
    IdempotencyScope,
    IdempotencyStore,
)
from dayu.host.durable.schema import TABLE_HOST_PURGE_TOMBSTONES
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_AUDIT_SINK_MARKERS,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_TOOL_TRACE_HOT,
    TABLE_HOST_WAIT_RECORDS,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, SQLiteScalar

PURGE_IDEMPOTENCY_SCOPE_KIND = "purge_session"
"""purge command 幂等记录的 scope kind。"""

PURGE_IDEMPOTENCY_RESULT_KIND = "purge_tombstone"
"""purge command 幂等记录的 result kind。"""

_PURGE_OPERATION = "purge_session"
_DECISION_MESSAGE_REPLAY = "purge tombstone replay"
_DECISION_MESSAGE_PROCEED = "purge may proceed"
_DECISION_MESSAGE_IDEMPOTENCY_CONFLICT = "purge idempotency conflict"
_DECISION_MESSAGE_ALREADY_PURGED = "session has already been purged"
_DECISION_MESSAGE_DURABLE_INCONSISTENCY = "purge durable replay is inconsistent"

_JSON_OPERATION = "operation"
_JSON_SESSION_ID = "session_id"
_JSON_REASON = "reason"
_JSON_OPERATION_CONTEXT_DIGEST = "operation_context_digest"
_JSON_OPERATION_CONTEXT_REFS = "operation_context_refs"
_JSON_REQUEST_CONTEXT = "request_context"

_COUNT_EVENT_LOG_ROWS = "event_log_rows"
_COUNT_IDEMPOTENCY_RECORDS = "idempotency_records"
_COUNT_PAYLOAD_DESCRIPTORS = "payload_descriptors"
_COUNT_SQLITE_PAYLOADS = "sqlite_payloads"
_COUNT_HOST_SESSION_SLOTS = "host_session_slots"
_COUNT_HOST_SESSIONS = "host_sessions"
_COUNT_HOST_RUNS = "host_runs"
_COUNT_HOST_ATTEMPTS = "host_attempts"
_COUNT_HOST_ATTEMPT_DISPATCH_RECORDS = "host_attempt_dispatch_records"
_COUNT_HOST_WAIT_RECORDS = "host_wait_records"
_COUNT_HOST_RUN_RESULTS = "host_run_results"
_COUNT_HOST_SESSION_TIMELINE_ITEMS = "host_session_timeline_items"
_COUNT_HOST_MEMORY_SNAPSHOTS = "host_memory_snapshots"
_COUNT_HOST_MEMORY_ITEMS = "host_memory_items"
_COUNT_HOST_MEMORY_DIAGNOSTICS = "host_memory_diagnostics"
_COUNT_HOST_AUDIT_SINK_MARKERS = "host_audit_sink_markers"
_COUNT_HOST_TOOL_TRACE_HOT = "host_tool_trace_hot"
_COUNT_HOST_OUTBOX_TERMINAL_ITEMS = "host_outbox_terminal_items"
_COUNT_HOST_OUTBOX_DRAIN_IDEMPOTENCY = "host_outbox_drain_idempotency"
_COUNT_HOST_PROJECTION_CHECKPOINTS = "host_projection_checkpoints"
_COUNT_HOST_PROJECTION_FAILURES = "host_projection_failures"

_SESSION_STATUS_CLOSED = "closed"
_RUN_STATUS_ACCEPTED = "accepted"
_RUN_STATUS_QUEUED = "queued"
_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_WAITING = "waiting"
_RUN_STATUS_CANCELLING = "cancelling"
_RUN_STATUS_RECOVERING = "recovering"
_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_FAILED = "failed"
_RUN_STATUS_CANCELLED = "cancelled"
_RUN_STATUS_LOST = "lost"
_WAIT_STATUS_WAITING = "waiting"
_PAYLOAD_KIND_SQLITE = "sqlite_payload"
_TOMBSTONE_ID_PREFIX = "purge-tombstone-"

_NON_TERMINAL_RUN_STATUSES = (
    _RUN_STATUS_ACCEPTED,
    _RUN_STATUS_QUEUED,
    _RUN_STATUS_RUNNING,
    _RUN_STATUS_WAITING,
    _RUN_STATUS_CANCELLING,
    _RUN_STATUS_RECOVERING,
)
_TERMINAL_RUN_STATUSES = (
    _RUN_STATUS_SUCCEEDED,
    _RUN_STATUS_FAILED,
    _RUN_STATUS_CANCELLED,
    _RUN_STATUS_LOST,
)
_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS = (
    "host.minimal-read-model",
    "host.memory.session.v1",
    "host.audit-log-jsonl",
    "host.tool-trace",
    "host.outbox-terminal",
)
_SESSION_FACT_SCOPE_KINDS = (
    "ensure_session",
    "create_session",
    "close_session",
    "start_run",
    "submit_followup_queue",
    "submit_followup_steer",
    "retry_run",
    "replay_run",
    "cancel_run",
    "cancel_session_runs",
)

_REFS_EVENT_IDS = "event_ids"
_REFS_EVENT_SEQUENCES = "event_sequences"
_REFS_RUN_IDS = "run_ids"
_REFS_ATTEMPT_IDS = "attempt_ids"
_REFS_PAYLOAD_REFS = "payload_refs"
_REFS_DELETED_PAYLOAD_REFS = "deleted_payload_refs"
_REFS_DELETED_SQLITE_PAYLOAD_IDS = "deleted_sqlite_payload_ids"
_REFS_ARTIFACT_RELATIVE_PATHS = "artifact_relative_paths"

_PRECONDITION_OPERATION = "operation"
_PRECONDITION_SESSION = "session"
_PRECONDITION_SLOTS = "slots"
_PRECONDITION_RUNS = "runs"
_PRECONDITION_ATTEMPTS = "attempts"
_PRECONDITION_WAITS = "waits"
_PRECONDITION_EVENT_LOG = "event_log"
_PRECONDITION_COUNTS = "counts"


@dataclass(frozen=True, slots=True)
class PurgeDeleteCounts:
    """purge 删除矩阵的分项计数。

    :param event_log_rows: 删除的 EventLog row 数量。
    :param idempotency_records: 删除的旧 command idempotency row 数量。
    :param payload_descriptors: 删除的 payload descriptor 数量。
    :param sqlite_payloads: 删除的 SQLite payload 数量。
    :param host_session_slots: 删除的 Session slot row 数量。
    :param host_sessions: 删除的 Session row 数量。
    :param host_runs: 删除的 Run row 数量。
    :param host_attempts: 删除的 Attempt row 数量。
    :param host_attempt_dispatch_records: 删除的 dispatch record 数量。
    :param host_wait_records: 删除的 wait record 数量。
    :param host_run_results: 删除的 run result projection 数量。
    :param host_session_timeline_items: 删除的 timeline projection 数量。
    :param host_memory_snapshots: 删除的 memory snapshot 数量。
    :param host_memory_items: 删除的 memory item 数量。
    :param host_memory_diagnostics: 删除的 memory diagnostic 数量。
    :param host_audit_sink_markers: 删除的 audit sink marker 数量。
    :param host_tool_trace_hot: 删除的 tool trace hot row 数量。
    :param host_outbox_terminal_items: 删除的 outbox terminal item 数量。
    :param host_outbox_drain_idempotency: 删除的 outbox drain 幂等 row 数量。
    :param host_projection_checkpoints: 删除的 projection checkpoint 数量。
    :param host_projection_failures: 删除的 projection failure 数量。
    """

    event_log_rows: int
    idempotency_records: int
    payload_descriptors: int
    sqlite_payloads: int
    host_session_slots: int
    host_sessions: int
    host_runs: int
    host_attempts: int
    host_attempt_dispatch_records: int
    host_wait_records: int
    host_run_results: int
    host_session_timeline_items: int
    host_memory_snapshots: int
    host_memory_items: int
    host_memory_diagnostics: int
    host_audit_sink_markers: int
    host_tool_trace_hot: int
    host_outbox_terminal_items: int
    host_outbox_drain_idempotency: int
    host_projection_checkpoints: int
    host_projection_failures: int

    def json_value(self) -> JsonValue:
        """序列化为 stable JSON object。

        :returns: 可用于 canonical JSON digest 的 JSON object。
        :raises HostDurableError: 任一计数为负数时抛出。
        """

        _validate_delete_counts(self)
        value: dict[str, JsonValue] = {
            _COUNT_EVENT_LOG_ROWS: self.event_log_rows,
            _COUNT_IDEMPOTENCY_RECORDS: self.idempotency_records,
            _COUNT_PAYLOAD_DESCRIPTORS: self.payload_descriptors,
            _COUNT_SQLITE_PAYLOADS: self.sqlite_payloads,
            _COUNT_HOST_SESSION_SLOTS: self.host_session_slots,
            _COUNT_HOST_SESSIONS: self.host_sessions,
            _COUNT_HOST_RUNS: self.host_runs,
            _COUNT_HOST_ATTEMPTS: self.host_attempts,
            _COUNT_HOST_ATTEMPT_DISPATCH_RECORDS: (
                self.host_attempt_dispatch_records
            ),
            _COUNT_HOST_WAIT_RECORDS: self.host_wait_records,
            _COUNT_HOST_RUN_RESULTS: self.host_run_results,
            _COUNT_HOST_SESSION_TIMELINE_ITEMS: (
                self.host_session_timeline_items
            ),
            _COUNT_HOST_MEMORY_SNAPSHOTS: self.host_memory_snapshots,
            _COUNT_HOST_MEMORY_ITEMS: self.host_memory_items,
            _COUNT_HOST_MEMORY_DIAGNOSTICS: self.host_memory_diagnostics,
            _COUNT_HOST_AUDIT_SINK_MARKERS: self.host_audit_sink_markers,
            _COUNT_HOST_TOOL_TRACE_HOT: self.host_tool_trace_hot,
            _COUNT_HOST_OUTBOX_TERMINAL_ITEMS: (
                self.host_outbox_terminal_items
            ),
            _COUNT_HOST_OUTBOX_DRAIN_IDEMPOTENCY: (
                self.host_outbox_drain_idempotency
            ),
            _COUNT_HOST_PROJECTION_CHECKPOINTS: (
                self.host_projection_checkpoints
            ),
            _COUNT_HOST_PROJECTION_FAILURES: self.host_projection_failures,
        }
        return value


@dataclass(frozen=True, slots=True)
class PurgePreconditionSnapshot:
    """purge 前置条件摘要输入的已冻结快照。

    :param session_id: 目标 Session id。
    :param session_status: purge 前 Session 状态。
    :param session_created_event_id: Session 创建事件 id。
    :param session_created_event_sequence: Session 创建事件 sequence。
    :param session_closed_event_id: Session 关闭事件 id。
    :param session_closed_event_sequence: Session 关闭事件 sequence。
    :param slot_count: 目标 Session slot row 数量。
    :param run_count: 目标 Session Run row 数量。
    :param attempt_count: 目标 Session Attempt row 数量。
    :param wait_record_count: 目标 Session wait record row 数量。
    :param event_log_min_sequence: 目标 EventLog 最小 sequence。
    :param event_log_max_sequence: 目标 EventLog 最大 sequence。
    :param event_log_count: 目标 EventLog row 数量。
    :param payload_ref_count: 目标 durable payload ref 数量。
    :param command_idempotency_count: 目标旧 command 幂等 row 数量。
    :param projection_row_count: 目标 projection row 数量。
    :param memory_row_count: 目标 memory row 数量。
    :param outbox_row_count: 目标 outbox row 数量。
    :param tool_trace_hot_row_count: 目标 tool trace hot row 数量。
    """

    session_id: str
    session_status: str
    session_created_event_id: str
    session_created_event_sequence: int
    session_closed_event_id: str
    session_closed_event_sequence: int
    slot_count: int
    run_count: int
    attempt_count: int
    wait_record_count: int
    event_log_min_sequence: int | None
    event_log_max_sequence: int | None
    event_log_count: int
    payload_ref_count: int
    command_idempotency_count: int
    projection_row_count: int
    memory_row_count: int
    outbox_row_count: int
    tool_trace_hot_row_count: int


@dataclass(frozen=True, slots=True)
class PurgeTombstoneRow:
    """已持久化 purge tombstone row。

    :param tombstone_id: tombstone 主键。
    :param session_id: 被 purge 的 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :param actor: 发起方标识。
    :param source: 来源标识。
    :param operation_context_digest: 操作上下文 refs digest。
    :param operation_context_refs: 操作上下文 refs JSON object。
    :param reason: purge 原因。
    :param purged_at: purge timestamp，固定 UTC 文本。
    :param precondition_digest: purge 前置条件 digest。
    :param deleted_counts: 删除矩阵分项计数。
    :param deleted_counts_digest: 删除计数 digest。
    :param deleted_refs_digest: 删除对象 refs digest。
    :param audit_record_ref: purge audit record 引用。
    :param audit_record_digest: purge audit record digest。
    :param request_context: 请求上下文 refs JSON object。
    """

    tombstone_id: str
    session_id: str
    client_request_id: str
    semantic_request_digest: str
    actor: str | None
    source: str | None
    operation_context_digest: str | None
    operation_context_refs: Mapping[str, JsonValue]
    reason: str
    purged_at: str
    precondition_digest: str
    deleted_counts: PurgeDeleteCounts
    deleted_counts_digest: str
    deleted_refs_digest: str
    audit_record_ref: str | None
    audit_record_digest: str | None
    request_context: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PurgeSessionDeleteRequest:
    """Session purge 删除事务请求。

    :param session_id: 目标 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :param actor: 发起方标识。
    :param source: 来源标识。
    :param operation_context_digest: 操作上下文 refs digest。
    :param operation_context_refs: 操作上下文 refs JSON object。
    :param reason: purge 原因。
    :param purged_at: purge timestamp，调用方提供的 UTC 文本。
    :param audit_record_ref: purge audit record 引用；P15-S2 未写 JSONL 时为 ``None``。
    :param audit_record_digest: purge audit record digest；P15-S2 未写 JSONL 时为 ``None``。
    :param request_context: 请求上下文 refs JSON object。
    """

    session_id: str
    client_request_id: str
    semantic_request_digest: str
    actor: str | None
    source: str | None
    operation_context_digest: str | None
    operation_context_refs: Mapping[str, JsonValue]
    reason: str
    purged_at: str
    audit_record_ref: str | None
    audit_record_digest: str | None
    request_context: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PurgeCommitCleanupRefs:
    """purge commit 后可做慢文件清理的引用集合。

    :param artifact_relative_paths: 事务中已确认 descriptor 不再被引用的本地
        artifact 相对路径；调用方必须在 SQLite commit 后再做文件 IO。
    """

    artifact_relative_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PurgeSessionDeleteResult:
    """Session purge 删除事务结果。

    :param deleted_counts: 删除矩阵分项计数。
    :param tombstone: 插入或 replay 的 purge tombstone row。
    :param cleanup_refs: commit 后慢文件清理引用。
    :param idempotent_replay: 本次是否从既有 tombstone replay。
    """

    deleted_counts: PurgeDeleteCounts
    tombstone: PurgeTombstoneRow
    cleanup_refs: PurgeCommitCleanupRefs
    idempotent_replay: bool


class PurgeSessionNotFoundError(HostDurableError):
    """目标 Session 不存在且没有 purge tombstone。"""


class PurgeSessionInvalidStateError(HostDurableError):
    """目标 Session 不满足 purge 前置条件。"""


class PurgeSessionAlreadyPurgedError(HostDurableError):
    """目标 Session 已由不同 purge 请求清理。"""


@dataclass(frozen=True, slots=True)
class _EventLogDeleteRef:
    """目标 EventLog 删除引用。"""

    event_id: str
    event_sequence: int
    payload_ref: str | None


@dataclass(frozen=True, slots=True)
class _PayloadDescriptorDeleteRef:
    """可删除 payload descriptor 引用。"""

    payload_ref: str
    payload_kind: str
    sqlite_payload_id: str | None
    artifact_relative_path: str | None


class PurgeReplayDecisionKind(StrEnum):
    """purge durable replay 判定的封闭结果类型。"""

    PROCEED_TO_PURGE = "proceed_to_purge"
    REPLAY_TOMBSTONE = "replay_tombstone"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    ALREADY_PURGED_CONFLICT = "already_purged_conflict"
    DURABLE_INCONSISTENCY = "durable_inconsistency"


@dataclass(frozen=True, slots=True)
class PurgeReplayDecision:
    """purge durable replay 判定结果。

    :param kind: 封闭判定类型。
    :param tombstone: 可用于 replay 的 tombstone row。
    :param idempotency_record: 已读取或补写的 purge 幂等记录。
    :param message: 稳定诊断消息。
    """

    kind: PurgeReplayDecisionKind
    tombstone: PurgeTombstoneRow | None
    idempotency_record: IdempotencyRecord | None
    message: str


def read_purge_tombstone_by_session_id(
    transaction: HostTransaction, session_id: str
) -> PurgeTombstoneRow | None:
    """按 Session id 读取 purge tombstone。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: 目标 Session id。
    :returns: 找到时返回 tombstone row，否则返回 ``None``。
    :raises HostDurableError: 输入或 durable row 无效时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    row = transaction.fetchone(
        _select_tombstone_sql("session_id = ?"),
        (session_id,),
    )
    return _optional_tombstone_from_row(row)


def read_purge_tombstone_by_id(
    transaction: HostTransaction, tombstone_id: str
) -> PurgeTombstoneRow | None:
    """按 tombstone id 读取 purge tombstone。

    :param transaction: 调用方提供的 Host durable transaction。
    :param tombstone_id: 目标 tombstone id。
    :returns: 找到时返回 tombstone row，否则返回 ``None``。
    :raises HostDurableError: 输入或 durable row 无效时抛出。
    """

    _require_non_empty_text(tombstone_id, field_name="tombstone_id")
    row = transaction.fetchone(
        _select_tombstone_sql("tombstone_id = ?"),
        (tombstone_id,),
    )
    return _optional_tombstone_from_row(row)


def insert_purge_tombstone(
    transaction: HostTransaction, tombstone: PurgeTombstoneRow
) -> PurgeTombstoneRow:
    """插入 purge tombstone row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param tombstone: 待插入的 tombstone row。
    :returns: 插入后从 durable store 读回的 tombstone row。
    :raises HostDurableError: 输入无效或插入后无法读回时抛出。
    :raises sqlite3.Error: SQLite 约束失败时由 transaction runner 结构化转换。
    """

    _validate_tombstone(tombstone)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_PURGE_TOMBSTONES} (
          tombstone_id,
          session_id,
          client_request_id,
          semantic_request_digest,
          actor,
          source,
          operation_context_digest,
          operation_context_refs_json,
          reason,
          purged_at,
          precondition_digest,
          deleted_counts_json,
          deleted_counts_digest,
          deleted_refs_digest,
          audit_record_ref,
          audit_record_digest,
          request_context_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tombstone.tombstone_id,
            tombstone.session_id,
            tombstone.client_request_id,
            tombstone.semantic_request_digest,
            tombstone.actor,
            tombstone.source,
            tombstone.operation_context_digest,
            canonical_json_dumps(tombstone.operation_context_refs),
            tombstone.reason,
            tombstone.purged_at,
            tombstone.precondition_digest,
            canonical_json_dumps(tombstone.deleted_counts.json_value()),
            tombstone.deleted_counts_digest,
            tombstone.deleted_refs_digest,
            tombstone.audit_record_ref,
            tombstone.audit_record_digest,
            canonical_json_dumps(tombstone.request_context),
        ),
    )
    inserted = read_purge_tombstone_by_id(transaction, tombstone.tombstone_id)
    if inserted is None:
        raise HostDurableError("Purge tombstone insert did not return row")
    return inserted


def build_purge_semantic_digest(
    *,
    session_id: str,
    reason: str,
    operation_context_digest: str | None,
    operation_context_refs: Mapping[str, JsonValue],
    request_context: Mapping[str, JsonValue],
) -> str:
    """构造 purge 请求 semantic digest。

    :param session_id: 目标 Session id。
    :param reason: purge 原因。
    :param operation_context_digest: 操作上下文 refs digest。
    :param operation_context_refs: 操作上下文 refs JSON object。
    :param request_context: 请求上下文 refs JSON object。
    :returns: ``sha256:`` semantic digest。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises TypeError: JSON 值不可序列化时抛出。
    :raises ValueError: JSON 值包含非有限浮点数时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(reason, field_name="reason")
    _require_optional_sha256_digest(
        operation_context_digest, field_name="operation_context_digest"
    )
    value: dict[str, JsonValue] = {
        _JSON_OPERATION: _PURGE_OPERATION,
        _JSON_SESSION_ID: session_id,
        _JSON_REASON: reason,
        _JSON_OPERATION_CONTEXT_DIGEST: operation_context_digest,
        _JSON_OPERATION_CONTEXT_REFS: operation_context_refs,
        _JSON_REQUEST_CONTEXT: request_context,
    }
    return sha256_digest_json(value)


def build_deleted_counts_digest(counts: PurgeDeleteCounts) -> str:
    """构造 deleted counts digest。

    :param counts: purge 删除矩阵分项计数。
    :returns: ``sha256:`` deleted counts digest。
    :raises HostDurableError: 任一计数为负数时抛出。
    """

    return sha256_digest_json(counts.json_value())


def record_or_read_purge_idempotency(
    transaction: HostTransaction,
    *,
    session_id: str,
    client_request_id: str,
    semantic_request_digest: str,
) -> PurgeReplayDecision:
    """读取或补写 purge tombstone 幂等记录并返回 replay 判定。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: 目标 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :returns: replay / conflict / proceed 判定。
    :raises HostDurableError: 输入字段无效或 durable row 无效时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(client_request_id, field_name="client_request_id")
    _require_sha256_digest(
        semantic_request_digest, field_name="semantic_request_digest"
    )
    scope = _purge_idempotency_scope(session_id, client_request_id)
    tombstone = read_purge_tombstone_by_session_id(transaction, session_id)
    if tombstone is not None:
        return _decision_for_existing_tombstone(
            transaction,
            scope,
            tombstone,
            semantic_request_digest,
        )

    record = IdempotencyStore().read_idempotency_record(transaction, scope)
    if record is None:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.PROCEED_TO_PURGE,
            tombstone=None,
            idempotency_record=None,
            message=_DECISION_MESSAGE_PROCEED,
        )
    if record.semantic_input_digest != semantic_request_digest:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT,
            tombstone=None,
            idempotency_record=record,
            message=_DECISION_MESSAGE_IDEMPOTENCY_CONFLICT,
        )
    if record.result_kind != PURGE_IDEMPOTENCY_RESULT_KIND:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY,
            tombstone=None,
            idempotency_record=record,
            message=_DECISION_MESSAGE_DURABLE_INCONSISTENCY,
        )
    replay_tombstone = read_purge_tombstone_by_id(transaction, record.result_ref)
    if replay_tombstone is None:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY,
            tombstone=None,
            idempotency_record=record,
            message=_DECISION_MESSAGE_DURABLE_INCONSISTENCY,
        )
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.REPLAY_TOMBSTONE,
        tombstone=replay_tombstone,
        idempotency_record=record,
        message=_DECISION_MESSAGE_REPLAY,
    )


def purge_session_durable(
    transaction: HostTransaction, request: PurgeSessionDeleteRequest
) -> PurgeSessionDeleteResult:
    """在调用方 write transaction 内执行 Session purge 删除矩阵。

    本 helper 只使用 Session / Run / Attempt / EventLog governance truth 判定
    purge 前置条件，并在同一事务内删除目标 Session 的可恢复事实、写入
    tombstone 与 ``purge_session`` 幂等记录。它不写 public command result、
    不写 audit JSONL，也不执行慢文件 IO。

    :param transaction: 调用方提供的 Host durable write transaction。
    :param request: purge 删除事务请求。
    :returns: 删除计数、tombstone 与 commit 后文件清理引用。
    :raises PurgeSessionNotFoundError: Session 不存在且无 tombstone 时抛出。
    :raises PurgeSessionInvalidStateError: Session 未关闭、Run 未终态或存在
        active wait 时抛出。
    :raises PurgeSessionAlreadyPurgedError: 目标 Session 已由不同请求 purge 时抛出。
    :raises HostIdempotencyConflictError: 同 key semantic digest 不一致时抛出。
    :raises HostDurableError: durable row 损坏、FK/ref 不一致或 tombstone 写入失败时抛出。
    """

    _validate_purge_delete_request(request)
    replay_decision = record_or_read_purge_idempotency(
        transaction,
        session_id=request.session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
    )
    replay = _result_for_replay_decision(replay_decision)
    if replay is not None:
        return replay

    session_row = _read_session_row(transaction, request.session_id)
    if session_row is None:
        raise PurgeSessionNotFoundError("purge target Session not found")
    _enforce_session_closed(session_row)
    _enforce_no_non_terminal_runs(transaction, request.session_id)
    _enforce_no_active_waits(transaction, request.session_id)

    event_refs = _read_target_event_refs(transaction, request.session_id)
    if len(event_refs) == 0:
        raise HostDurableError("purge target Session has no EventLog facts")
    event_ids = tuple(ref.event_id for ref in event_refs)
    event_sequences = tuple(ref.event_sequence for ref in event_refs)
    run_ids = _read_target_run_ids(transaction, request.session_id)
    attempt_ids = _read_target_attempt_ids(transaction, run_ids)
    payload_refs = _read_target_payload_refs(transaction, request.session_id)
    precondition_digest = _build_purge_precondition_digest(
        transaction,
        session_row=session_row,
        session_id=request.session_id,
        event_refs=event_refs,
        payload_refs=payload_refs,
    )
    matrix_counts = _delete_session_matrix(
        transaction,
        session_id=request.session_id,
        event_ids=event_ids,
        event_sequences=event_sequences,
        run_ids=run_ids,
        payload_refs=payload_refs,
    )
    descriptor_refs = _delete_unreferenced_payload_descriptors(
        transaction,
        payload_refs,
    )
    sqlite_payload_ids = _delete_unreferenced_sqlite_payloads(
        transaction,
        descriptor_refs,
    )
    cleanup_refs = PurgeCommitCleanupRefs(
        artifact_relative_paths=tuple(
            sorted(
                ref.artifact_relative_path
                for ref in descriptor_refs
                if ref.artifact_relative_path is not None
            )
        )
    )
    deleted_counts = _counts_with_payload_cleanup(
        matrix_counts,
        payload_descriptor_count=len(descriptor_refs),
        sqlite_payload_count=len(sqlite_payload_ids),
    )
    tombstone = _insert_tombstone_and_idempotency(
        transaction,
        request=request,
        deleted_counts=deleted_counts,
        precondition_digest=precondition_digest,
        deleted_refs_digest=_build_deleted_refs_digest(
            event_refs=event_refs,
            run_ids=run_ids,
            attempt_ids=attempt_ids,
            payload_refs=payload_refs,
            deleted_payload_refs=tuple(ref.payload_ref for ref in descriptor_refs),
            deleted_sqlite_payload_ids=sqlite_payload_ids,
            artifact_relative_paths=cleanup_refs.artifact_relative_paths,
        ),
    )
    return PurgeSessionDeleteResult(
        deleted_counts=deleted_counts,
        tombstone=tombstone,
        cleanup_refs=cleanup_refs,
        idempotent_replay=False,
    )


def _validate_purge_delete_request(request: PurgeSessionDeleteRequest) -> None:
    """校验 purge 删除事务请求。

    :param request: purge 删除事务请求。
    :returns: ``None``。
    :raises HostDurableError: 任一字段不符合 durable 约束时抛出。
    """

    _require_non_empty_text(request.session_id, field_name="session_id")
    _require_non_empty_text(
        request.client_request_id,
        field_name="client_request_id",
    )
    _require_sha256_digest(
        request.semantic_request_digest,
        field_name="semantic_request_digest",
    )
    _require_optional_non_empty_text(request.actor, field_name="actor")
    _require_optional_non_empty_text(request.source, field_name="source")
    _require_optional_sha256_digest(
        request.operation_context_digest,
        field_name="operation_context_digest",
    )
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(request.purged_at, field_name="purged_at")
    _require_optional_non_empty_text(
        request.audit_record_ref,
        field_name="audit_record_ref",
    )
    _require_optional_sha256_digest(
        request.audit_record_digest,
        field_name="audit_record_digest",
    )
    if (request.audit_record_ref is None) != (request.audit_record_digest is None):
        raise HostDurableError(
            "audit_record_ref and audit_record_digest must be both set or both unset"
        )


def _result_for_replay_decision(
    decision: PurgeReplayDecision,
) -> PurgeSessionDeleteResult | None:
    """把 S1 replay 判定映射为 S2 删除 helper 结果或异常。

    :param decision: purge replay 判定。
    :returns: replay 结果；需要继续执行 purge 时返回 ``None``。
    :raises HostIdempotencyConflictError: 同 key digest 冲突时抛出。
    :raises PurgeSessionAlreadyPurgedError: 不同 key 访问已 purge Session 时抛出。
    :raises HostDurableError: durable replay 不一致时抛出。
    """

    if decision.kind is PurgeReplayDecisionKind.PROCEED_TO_PURGE:
        return None
    if decision.kind is PurgeReplayDecisionKind.REPLAY_TOMBSTONE:
        if decision.tombstone is None:
            raise HostDurableError("purge replay tombstone is missing")
        return PurgeSessionDeleteResult(
            deleted_counts=decision.tombstone.deleted_counts,
            tombstone=decision.tombstone,
            cleanup_refs=PurgeCommitCleanupRefs(artifact_relative_paths=()),
            idempotent_replay=True,
        )
    if decision.kind is PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT:
        raise HostIdempotencyConflictError(decision.message)
    if decision.kind is PurgeReplayDecisionKind.ALREADY_PURGED_CONFLICT:
        raise PurgeSessionAlreadyPurgedError(decision.message)
    raise HostDurableError(decision.message)


def _read_session_row(
    transaction: HostTransaction, session_id: str
) -> HostRow | None:
    """读取目标 Session row。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: Session row；不存在时为 ``None``。
    """

    return transaction.fetchone(
        f"""
        SELECT
          session_id,
          status,
          created_event_id,
          created_event_sequence,
          closed_event_id,
          closed_event_sequence
        FROM {TABLE_HOST_SESSIONS}
        WHERE session_id = ?
        """,
        (session_id,),
    )


def _enforce_session_closed(session_row: HostRow) -> None:
    """校验 Session 已关闭。

    :param session_row: durable Session row。
    :returns: ``None``。
    :raises PurgeSessionInvalidStateError: Session 不是 closed 时抛出。
    """

    status = _require_text(session_row.get("status"), field_name="session.status")
    if status != _SESSION_STATUS_CLOSED:
        raise PurgeSessionInvalidStateError("purge requires closed Session")


def _enforce_no_non_terminal_runs(
    transaction: HostTransaction, session_id: str
) -> None:
    """校验目标 Session 下所有 Run 均为终态。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: ``None``。
    :raises PurgeSessionInvalidStateError: 存在 active/queued/waiting/cancelling/recovering
        Run 或未知状态时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT run_id, status
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
        ORDER BY run_id ASC
        """,
        (session_id,),
    )
    for row in rows:
        status = _require_text(row.get("status"), field_name="run.status")
        if status in _NON_TERMINAL_RUN_STATUSES:
            raise PurgeSessionInvalidStateError(
                "purge requires every Run to be terminal"
            )
        if status not in _TERMINAL_RUN_STATUSES:
            raise HostDurableError("Run row status is invalid")


def _enforce_no_active_waits(transaction: HostTransaction, session_id: str) -> None:
    """校验目标 Session 不存在 active wait。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: ``None``。
    :raises PurgeSessionInvalidStateError: 存在 waiting wait record 时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT wait_id
        FROM {TABLE_HOST_WAIT_RECORDS}
        WHERE session_id = ? AND status = ?
        LIMIT 1
        """,
        (session_id, _WAIT_STATUS_WAITING),
    )
    if row is not None:
        raise PurgeSessionInvalidStateError("purge requires no active wait records")


def _read_target_event_refs(
    transaction: HostTransaction, session_id: str
) -> tuple[_EventLogDeleteRef, ...]:
    """读取目标 Session 的 EventLog 删除引用。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: EventLog 删除引用，按 sequence 升序排列。
    :raises HostDurableError: row 类型不符合 schema 预期时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id, event_sequence, payload_ref
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
        ORDER BY event_sequence ASC
        """,
        (session_id,),
    )
    return tuple(
        _EventLogDeleteRef(
            event_id=_require_text(row.get("event_id"), field_name="event_id"),
            event_sequence=_require_int(
                row.get("event_sequence"),
                field_name="event_sequence",
            ),
            payload_ref=_optional_text(row.get("payload_ref"), field_name="payload_ref"),
        )
        for row in rows
    )


def _read_target_run_ids(
    transaction: HostTransaction, session_id: str
) -> tuple[str, ...]:
    """读取目标 Session 的 Run ids。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: 按 run id 排序的 Run id 元组。
    """

    return _read_texts(
        transaction,
        f"""
        SELECT run_id
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
        ORDER BY run_id ASC
        """,
        "run_id",
        (session_id,),
    )


def _read_target_attempt_ids(
    transaction: HostTransaction, run_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """读取目标 Run ids 下的 Attempt ids。

    :param transaction: Host transaction。
    :param run_ids: 目标 Run ids。
    :returns: 按 attempt id 排序的 Attempt id 元组。
    """

    if len(run_ids) == 0:
        return ()
    return _read_texts(
        transaction,
        f"""
        SELECT attempt_id
        FROM {TABLE_HOST_ATTEMPTS}
        WHERE {_in_clause("run_id", run_ids)}
        ORDER BY attempt_id ASC
        """,
        "attempt_id",
        run_ids,
    )


def _read_target_payload_refs(
    transaction: HostTransaction, session_id: str
) -> tuple[str, ...]:
    """收集目标 Session 删除范围内出现过的 payload descriptor refs。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: 去重排序后的 payload refs。
    """

    refs: set[str] = set()
    for sql, column_name in _target_payload_ref_queries(session_id):
        rows = transaction.fetchall(sql, (session_id,))
        for row in rows:
            ref = _optional_text(row.get(column_name), field_name=column_name)
            if ref is not None:
                refs.add(ref)
    return tuple(sorted(refs))


def _target_payload_ref_queries(
    session_id: str,
) -> tuple[tuple[str, str], ...]:
    """生成目标 payload ref 查询 SQL。

    :param session_id: 目标 Session id；只用于说明查询归属。
    :returns: ``(sql, column_name)`` 元组集合。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    return (
        (
            f"SELECT payload_ref FROM {TABLE_EVENT_LOG} WHERE session_id = ?",
            "payload_ref",
        ),
        (
            f"""
            SELECT payload_ref
            FROM {TABLE_HOST_SESSION_TIMELINE_ITEMS}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
        (
            f"""
            SELECT result_ref AS payload_ref
            FROM {TABLE_HOST_RUN_RESULTS}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
        (
            f"""
            SELECT summary_ref AS payload_ref
            FROM {TABLE_HOST_RUN_RESULTS}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
        (
            f"""
            SELECT payload_ref
            FROM {TABLE_HOST_MEMORY_ITEMS}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
        (
            f"""
            SELECT payload_ref
            FROM {TABLE_HOST_TOOL_TRACE_HOT}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
        (
            f"""
            SELECT result_ref AS payload_ref
            FROM {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
        (
            f"""
            SELECT terminal_summary_ref AS payload_ref
            FROM {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
            WHERE session_id = ?
            """,
            "payload_ref",
        ),
    )


def _build_purge_precondition_digest(
    transaction: HostTransaction,
    *,
    session_row: HostRow,
    session_id: str,
    event_refs: tuple[_EventLogDeleteRef, ...],
    payload_refs: tuple[str, ...],
) -> str:
    """构造 purge 前置条件 digest。

    :param transaction: Host transaction。
    :param session_row: 目标 Session row。
    :param session_id: 目标 Session id。
    :param event_refs: 目标 EventLog refs。
    :param payload_refs: 目标 payload refs。
    :returns: ``sha256:`` precondition digest。
    """

    run_ids = _read_target_run_ids(transaction, session_id)
    event_sequences = tuple(ref.event_sequence for ref in event_refs)
    counts: dict[str, JsonValue] = {
        _COUNT_EVENT_LOG_ROWS: len(event_refs),
        _COUNT_IDEMPOTENCY_RECORDS: _count_old_idempotency_records(
            transaction,
            session_id=session_id,
            event_ids=tuple(ref.event_id for ref in event_refs),
            event_sequences=event_sequences,
        ),
        _COUNT_HOST_SESSION_SLOTS: _count_by_session(
            transaction,
            TABLE_HOST_SESSION_SLOTS,
            session_id,
        ),
        _COUNT_HOST_RUNS: _count_by_session(transaction, TABLE_HOST_RUNS, session_id),
        _COUNT_HOST_ATTEMPTS: _count_attempts_by_session(transaction, session_id),
        _COUNT_HOST_WAIT_RECORDS: _count_by_session(
            transaction,
            TABLE_HOST_WAIT_RECORDS,
            session_id,
        ),
        _COUNT_HOST_RUN_RESULTS: _count_by_session(
            transaction,
            TABLE_HOST_RUN_RESULTS,
            session_id,
        ),
        _COUNT_HOST_SESSION_TIMELINE_ITEMS: _count_by_session(
            transaction,
            TABLE_HOST_SESSION_TIMELINE_ITEMS,
            session_id,
        ),
        _COUNT_HOST_MEMORY_SNAPSHOTS: _count_by_session(
            transaction,
            TABLE_HOST_MEMORY_SNAPSHOTS,
            session_id,
        ),
        _COUNT_HOST_MEMORY_ITEMS: _count_by_session(
            transaction,
            TABLE_HOST_MEMORY_ITEMS,
            session_id,
        ),
        _COUNT_HOST_MEMORY_DIAGNOSTICS: _count_by_session(
            transaction,
            TABLE_HOST_MEMORY_DIAGNOSTICS,
            session_id,
        ),
        _COUNT_HOST_TOOL_TRACE_HOT: _count_by_session(
            transaction,
            TABLE_HOST_TOOL_TRACE_HOT,
            session_id,
        ),
        _COUNT_HOST_OUTBOX_TERMINAL_ITEMS: _count_by_session(
            transaction,
            TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
            session_id,
        ),
        _COUNT_HOST_OUTBOX_DRAIN_IDEMPOTENCY: _count_by_session(
            transaction,
            TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
            session_id,
        ),
    }
    value: dict[str, JsonValue] = {
        _PRECONDITION_OPERATION: _PURGE_OPERATION,
        _PRECONDITION_SESSION: _session_precondition_json(session_row),
        _PRECONDITION_SLOTS: _rows_json(
            transaction,
            f"""
            SELECT scope, slot_key, bound_event_id, bound_event_sequence
            FROM {TABLE_HOST_SESSION_SLOTS}
            WHERE session_id = ?
            ORDER BY scope ASC, slot_key ASC
            """,
            (session_id,),
        ),
        _PRECONDITION_RUNS: _rows_json(
            transaction,
            f"""
            SELECT
              run_id,
              status,
              accepted_event_id,
              accepted_event_sequence,
              queued_event_id,
              queued_event_sequence,
              started_event_id,
              started_event_sequence,
              terminal_event_id,
              terminal_event_sequence,
              current_attempt_id,
              source_run_id,
              source_run_relation
            FROM {TABLE_HOST_RUNS}
            WHERE session_id = ?
            ORDER BY run_id ASC
            """,
            (session_id,),
        ),
        _PRECONDITION_ATTEMPTS: (
            _rows_json(
                transaction,
                f"""
                SELECT
                  attempt_id,
                  run_id,
                  execution_id,
                  status,
                  started_event_id,
                  started_event_sequence,
                  terminal_event_id,
                  terminal_event_sequence
                FROM {TABLE_HOST_ATTEMPTS}
                WHERE {_in_clause("run_id", run_ids)}
                ORDER BY attempt_id ASC
                """,
                run_ids,
            )
            if run_ids
            else []
        ),
        _PRECONDITION_WAITS: _rows_json(
            transaction,
            f"""
            SELECT
              wait_id,
              run_id,
              attempt_id,
              execution_id,
              status,
              created_event_id,
              created_event_sequence,
              updated_event_id,
              updated_event_sequence
            FROM {TABLE_HOST_WAIT_RECORDS}
            WHERE session_id = ?
            ORDER BY wait_id ASC
            """,
            (session_id,),
        ),
        _PRECONDITION_EVENT_LOG: {
            "min_sequence": min(event_sequences) if event_sequences else None,
            "max_sequence": max(event_sequences) if event_sequences else None,
            "count": len(event_refs),
            "payload_ref_count": len(payload_refs),
        },
        _PRECONDITION_COUNTS: counts,
    }
    return sha256_digest_json(value)


def _session_precondition_json(session_row: HostRow) -> Mapping[str, JsonValue]:
    """把 Session row 转成 precondition JSON object。

    :param session_row: 目标 Session row。
    :returns: precondition JSON object。
    """

    return {
        "session_id": _require_text(
            session_row.get("session_id"),
            field_name="session_id",
        ),
        "status": _require_text(session_row.get("status"), field_name="status"),
        "created_event_id": _require_text(
            session_row.get("created_event_id"),
            field_name="created_event_id",
        ),
        "created_event_sequence": _require_int(
            session_row.get("created_event_sequence"),
            field_name="created_event_sequence",
        ),
        "closed_event_id": _require_text(
            session_row.get("closed_event_id"),
            field_name="closed_event_id",
        ),
        "closed_event_sequence": _require_int(
            session_row.get("closed_event_sequence"),
            field_name="closed_event_sequence",
        ),
    }


def _delete_session_matrix(
    transaction: HostTransaction,
    *,
    session_id: str,
    event_ids: tuple[str, ...],
    event_sequences: tuple[int, ...],
    run_ids: tuple[str, ...],
    payload_refs: tuple[str, ...],
) -> PurgeDeleteCounts:
    """按 FK-safe 顺序删除目标 Session 可恢复事实与 projection rows。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :param event_ids: 目标 EventLog ids。
    :param event_sequences: 目标 EventLog sequences。
    :param run_ids: 目标 Run ids。
    :param payload_refs: 删除前收集的 payload refs。
    :returns: 不含 payload cleanup 的删除计数。
    :raises HostDurableError: rowcount 与预期不一致时抛出。
    """

    audit_markers = _delete_by_event_ids(
        transaction,
        TABLE_HOST_AUDIT_SINK_MARKERS,
        "event_id",
        event_ids,
    )
    outbox_drain = _delete_by_session(
        transaction,
        TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
        session_id,
    )
    outbox_items = _delete_by_session(
        transaction,
        TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
        session_id,
    )
    tool_trace_hot = _delete_by_session(
        transaction,
        TABLE_HOST_TOOL_TRACE_HOT,
        session_id,
    )
    memory_diagnostics = _delete_by_session(
        transaction,
        TABLE_HOST_MEMORY_DIAGNOSTICS,
        session_id,
    )
    memory_items = _delete_by_session(
        transaction,
        TABLE_HOST_MEMORY_ITEMS,
        session_id,
    )
    memory_snapshots = _delete_by_session(
        transaction,
        TABLE_HOST_MEMORY_SNAPSHOTS,
        session_id,
    )
    run_results = _delete_by_session(
        transaction,
        TABLE_HOST_RUN_RESULTS,
        session_id,
    )
    timeline_items = _delete_by_session(
        transaction,
        TABLE_HOST_SESSION_TIMELINE_ITEMS,
        session_id,
    )
    _raise_for_unsupported_projection_reset_refs(
        transaction,
        TABLE_HOST_PROJECTION_CHECKPOINTS,
        "checkpoint_event_id",
        event_ids,
    )
    _raise_for_unsupported_projection_reset_refs(
        transaction,
        TABLE_HOST_PROJECTION_FAILURES,
        "failed_event_id",
        event_ids,
    )
    projection_checkpoints = _delete_allowed_projection_reset_refs(
        transaction,
        TABLE_HOST_PROJECTION_CHECKPOINTS,
        "checkpoint_event_id",
        event_ids,
    )
    projection_failures = _delete_allowed_projection_reset_refs(
        transaction,
        TABLE_HOST_PROJECTION_FAILURES,
        "failed_event_id",
        event_ids,
    )
    idempotency_records = _delete_old_idempotency_records(
        transaction,
        session_id=session_id,
        event_ids=event_ids,
        event_sequences=event_sequences,
    )
    wait_records = _delete_by_session(
        transaction,
        TABLE_HOST_WAIT_RECORDS,
        session_id,
    )
    dispatch_records = _delete_dispatch_records(
        transaction,
        run_ids,
    )
    attempts = _delete_attempts(transaction, run_ids)
    runs = _delete_runs_child_before_parent(transaction, session_id)
    slots = _delete_by_session(transaction, TABLE_HOST_SESSION_SLOTS, session_id)
    sessions = _delete_by_pk(
        transaction,
        TABLE_HOST_SESSIONS,
        "session_id",
        session_id,
    )
    event_log_rows = _delete_by_session(transaction, TABLE_EVENT_LOG, session_id)
    _assert_deleted("event_log", event_log_rows, len(event_ids))
    return PurgeDeleteCounts(
        event_log_rows=event_log_rows,
        idempotency_records=idempotency_records,
        payload_descriptors=len(payload_refs),
        sqlite_payloads=0,
        host_session_slots=slots,
        host_sessions=sessions,
        host_runs=runs,
        host_attempts=attempts,
        host_attempt_dispatch_records=dispatch_records,
        host_wait_records=wait_records,
        host_run_results=run_results,
        host_session_timeline_items=timeline_items,
        host_memory_snapshots=memory_snapshots,
        host_memory_items=memory_items,
        host_memory_diagnostics=memory_diagnostics,
        host_audit_sink_markers=audit_markers,
        host_tool_trace_hot=tool_trace_hot,
        host_outbox_terminal_items=outbox_items,
        host_outbox_drain_idempotency=outbox_drain,
        host_projection_checkpoints=projection_checkpoints,
        host_projection_failures=projection_failures,
    )


def _delete_unreferenced_payload_descriptors(
    transaction: HostTransaction, payload_refs: tuple[str, ...]
) -> tuple[_PayloadDescriptorDeleteRef, ...]:
    """删除目标 refs 中已经没有 durable 引用的 payload descriptors。

    :param transaction: Host transaction。
    :param payload_refs: 删除前收集的 payload refs。
    :returns: 已删除 descriptor refs。
    :raises HostDurableError: descriptor row 类型不符合预期时抛出。
    """

    deleted: list[_PayloadDescriptorDeleteRef] = []
    for payload_ref in payload_refs:
        descriptor = _read_payload_descriptor_delete_ref(transaction, payload_ref)
        if descriptor is None or _payload_ref_is_still_referenced(
            transaction,
            payload_ref,
        ):
            continue
        rows = transaction.execute(
            f"""
            DELETE FROM {TABLE_PAYLOAD_DESCRIPTORS}
            WHERE payload_ref = ?
            """,
            (payload_ref,),
        ).rowcount
        _assert_deleted("payload descriptor", rows, 1)
        deleted.append(descriptor)
    return tuple(deleted)


def _delete_unreferenced_sqlite_payloads(
    transaction: HostTransaction,
    deleted_descriptors: tuple[_PayloadDescriptorDeleteRef, ...],
) -> tuple[str, ...]:
    """删除不再被 descriptor 引用的 SQLite payload rows。

    :param transaction: Host transaction。
    :param deleted_descriptors: 已删除 descriptor refs。
    :returns: 已删除 SQLite payload ids。
    """

    deleted_payload_ids: list[str] = []
    for descriptor in deleted_descriptors:
        if (
            descriptor.payload_kind != _PAYLOAD_KIND_SQLITE
            or descriptor.sqlite_payload_id is None
            or _sqlite_payload_is_still_referenced(
                transaction,
                descriptor.sqlite_payload_id,
            )
        ):
            continue
        rows = transaction.execute(
            f"""
            DELETE FROM {TABLE_SQLITE_PAYLOADS}
            WHERE payload_id = ?
            """,
            (descriptor.sqlite_payload_id,),
        ).rowcount
        _assert_deleted("sqlite payload", rows, 1)
        deleted_payload_ids.append(descriptor.sqlite_payload_id)
    return tuple(sorted(deleted_payload_ids))


def _insert_tombstone_and_idempotency(
    transaction: HostTransaction,
    *,
    request: PurgeSessionDeleteRequest,
    deleted_counts: PurgeDeleteCounts,
    precondition_digest: str,
    deleted_refs_digest: str,
) -> PurgeTombstoneRow:
    """写入 purge tombstone 与 NULL EventLog refs 的 purge 幂等记录。

    :param transaction: Host transaction。
    :param request: purge 删除事务请求。
    :param deleted_counts: 删除矩阵计数。
    :param precondition_digest: 前置条件 digest。
    :param deleted_refs_digest: 删除对象 refs digest。
    :returns: 插入后的 tombstone row。
    :raises HostDurableError: tombstone 或 idempotency 写入失败时抛出。
    """

    tombstone_id = _build_tombstone_id(
        session_id=request.session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
    )
    tombstone = insert_purge_tombstone(
        transaction,
        PurgeTombstoneRow(
            tombstone_id=tombstone_id,
            session_id=request.session_id,
            client_request_id=request.client_request_id,
            semantic_request_digest=request.semantic_request_digest,
            actor=request.actor,
            source=request.source,
            operation_context_digest=request.operation_context_digest,
            operation_context_refs=request.operation_context_refs,
            reason=request.reason,
            purged_at=request.purged_at,
            precondition_digest=precondition_digest,
            deleted_counts=deleted_counts,
            deleted_counts_digest=build_deleted_counts_digest(deleted_counts),
            deleted_refs_digest=deleted_refs_digest,
            audit_record_ref=request.audit_record_ref,
            audit_record_digest=request.audit_record_digest,
            request_context=request.request_context,
        ),
    )
    IdempotencyStore().record_idempotent_result(
        transaction,
        _purge_idempotency_scope(request.session_id, request.client_request_id),
        request.semantic_request_digest,
        IdempotencyResultRef(
            result_kind=PURGE_IDEMPOTENCY_RESULT_KIND,
            result_ref=tombstone.tombstone_id,
            created_event_id=None,
            created_event_sequence=None,
        ),
    )
    return tombstone


def _build_tombstone_id(
    *, session_id: str, client_request_id: str, semantic_request_digest: str
) -> str:
    """构造稳定 tombstone id。

    :param session_id: 目标 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge semantic digest。
    :returns: 稳定 tombstone id。
    """

    digest = sha256_digest_json(
        {
            _JSON_OPERATION: _PURGE_OPERATION,
            _JSON_SESSION_ID: session_id,
            "client_request_id": client_request_id,
            "semantic_request_digest": semantic_request_digest,
        }
    )
    return f"{_TOMBSTONE_ID_PREFIX}{digest.removeprefix('sha256:')}"


def _counts_with_payload_cleanup(
    counts: PurgeDeleteCounts,
    *,
    payload_descriptor_count: int,
    sqlite_payload_count: int,
) -> PurgeDeleteCounts:
    """替换删除计数中的 payload cleanup 分项。

    :param counts: 删除矩阵基础计数。
    :param payload_descriptor_count: 已删除 descriptor 数量。
    :param sqlite_payload_count: 已删除 SQLite payload 数量。
    :returns: 更新后的删除计数。
    """

    return PurgeDeleteCounts(
        event_log_rows=counts.event_log_rows,
        idempotency_records=counts.idempotency_records,
        payload_descriptors=payload_descriptor_count,
        sqlite_payloads=sqlite_payload_count,
        host_session_slots=counts.host_session_slots,
        host_sessions=counts.host_sessions,
        host_runs=counts.host_runs,
        host_attempts=counts.host_attempts,
        host_attempt_dispatch_records=counts.host_attempt_dispatch_records,
        host_wait_records=counts.host_wait_records,
        host_run_results=counts.host_run_results,
        host_session_timeline_items=counts.host_session_timeline_items,
        host_memory_snapshots=counts.host_memory_snapshots,
        host_memory_items=counts.host_memory_items,
        host_memory_diagnostics=counts.host_memory_diagnostics,
        host_audit_sink_markers=counts.host_audit_sink_markers,
        host_tool_trace_hot=counts.host_tool_trace_hot,
        host_outbox_terminal_items=counts.host_outbox_terminal_items,
        host_outbox_drain_idempotency=counts.host_outbox_drain_idempotency,
        host_projection_checkpoints=counts.host_projection_checkpoints,
        host_projection_failures=counts.host_projection_failures,
    )


def _decision_for_existing_tombstone(
    transaction: HostTransaction,
    scope: IdempotencyScope,
    tombstone: PurgeTombstoneRow,
    semantic_request_digest: str,
) -> PurgeReplayDecision:
    """根据已存在 tombstone 生成 replay 判定。

    :param transaction: 调用方提供的 Host durable transaction。
    :param scope: purge 幂等作用域。
    :param tombstone: 已存在 tombstone row。
    :param semantic_request_digest: 当前请求 semantic digest。
    :returns: replay 或 conflict 判定。
    :raises HostDurableError: durable row 无效时抛出。
    """

    if scope.idempotency_key != tombstone.client_request_id:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.ALREADY_PURGED_CONFLICT,
            tombstone=tombstone,
            idempotency_record=None,
            message=_DECISION_MESSAGE_ALREADY_PURGED,
        )
    if semantic_request_digest != tombstone.semantic_request_digest:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT,
            tombstone=tombstone,
            idempotency_record=None,
            message=_DECISION_MESSAGE_IDEMPOTENCY_CONFLICT,
        )
    result = IdempotencyResultRef(
        result_kind=PURGE_IDEMPOTENCY_RESULT_KIND,
        result_ref=tombstone.tombstone_id,
        created_event_id=None,
        created_event_sequence=None,
    )
    try:
        record = IdempotencyStore().record_idempotent_result(
            transaction,
            scope,
            semantic_request_digest,
            result,
        )
    except HostIdempotencyConflictError:
        return PurgeReplayDecision(
            kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY,
            tombstone=tombstone,
            idempotency_record=None,
            message=_DECISION_MESSAGE_DURABLE_INCONSISTENCY,
        )
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.REPLAY_TOMBSTONE,
        tombstone=tombstone,
        idempotency_record=record,
        message=_DECISION_MESSAGE_REPLAY,
    )


def _delete_old_idempotency_records(
    transaction: HostTransaction,
    *,
    session_id: str,
    event_ids: tuple[str, ...],
    event_sequences: tuple[int, ...],
) -> int:
    """删除指向目标 EventLog 或目标 Session facts 的旧 command 幂等 rows。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :param event_ids: 目标 EventLog ids。
    :param event_sequences: 目标 EventLog sequences。
    :returns: 删除 row 数量。
    """

    event_id_clause = _in_clause("created_event_id", event_ids)
    event_sequence_clause = _in_clause("created_event_sequence", event_sequences)
    scope_clause = _in_clause("scope_kind", _SESSION_FACT_SCOPE_KINDS)
    return transaction.execute(
        f"""
        DELETE FROM {TABLE_IDEMPOTENCY_RECORDS}
        WHERE {event_id_clause}
           OR {event_sequence_clause}
           OR (scope_id = ? AND {scope_clause})
        """,
        event_ids + event_sequences + (session_id,) + _SESSION_FACT_SCOPE_KINDS,
    ).rowcount


def _raise_for_unsupported_projection_reset_refs(
    transaction: HostTransaction,
    table_name: str,
    event_id_column_name: str,
    event_ids: tuple[str, ...],
) -> None:
    """检查 target EventLog 上是否存在不可 reset 的 projection consumer row。

    :param transaction: Host transaction。
    :param table_name: projection checkpoint/failure 表名。
    :param event_id_column_name: 指向 EventLog id 的列名。
    :param event_ids: 目标 EventLog ids。
    :returns: ``None``。
    :raises HostDurableError: 非白名单 consumer 引用目标 EventLog 时抛出。
    """

    if len(event_ids) == 0:
        return
    row = transaction.fetchone(
        f"""
        SELECT consumer_id
        FROM {table_name}
        WHERE {_in_clause(event_id_column_name, event_ids)}
          AND consumer_id NOT IN (
            {_placeholders(_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS)}
          )
        LIMIT 1
        """,
        event_ids + _PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS,
    )
    if row is not None:
        consumer_id = _require_text(row.get("consumer_id"), field_name="consumer_id")
        raise HostDurableError(
            f"projection consumer cannot be reset during purge: {consumer_id}"
        )


def _delete_allowed_projection_reset_refs(
    transaction: HostTransaction,
    table_name: str,
    event_id_column_name: str,
    event_ids: tuple[str, ...],
) -> int:
    """删除白名单 consumer 且引用目标 EventLog 的 projection reset rows。

    :param transaction: Host transaction。
    :param table_name: projection checkpoint/failure 表名。
    :param event_id_column_name: 指向 EventLog id 的列名。
    :param event_ids: 目标 EventLog ids。
    :returns: 删除 row 数量。
    """

    if len(event_ids) == 0:
        return 0
    return transaction.execute(
        f"""
        DELETE FROM {table_name}
        WHERE {_in_clause(event_id_column_name, event_ids)}
          AND consumer_id IN (
            {_placeholders(_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS)}
          )
        """,
        event_ids + _PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS,
    ).rowcount


def _count_old_idempotency_records(
    transaction: HostTransaction,
    *,
    session_id: str,
    event_ids: tuple[str, ...],
    event_sequences: tuple[int, ...],
) -> int:
    """统计将被 purge 删除的旧 command 幂等 rows。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :param event_ids: 目标 EventLog ids。
    :param event_sequences: 目标 EventLog sequences。
    :returns: row 数量。
    """

    event_id_clause = _in_clause("created_event_id", event_ids)
    event_sequence_clause = _in_clause("created_event_sequence", event_sequences)
    scope_clause = _in_clause("scope_kind", _SESSION_FACT_SCOPE_KINDS)
    return _count_sql(
        transaction,
        f"""
        SELECT COUNT(*) AS count
        FROM {TABLE_IDEMPOTENCY_RECORDS}
        WHERE {event_id_clause}
           OR {event_sequence_clause}
           OR (scope_id = ? AND {scope_clause})
        """,
        event_ids + event_sequences + (session_id,) + _SESSION_FACT_SCOPE_KINDS,
    )


def _delete_dispatch_records(
    transaction: HostTransaction, run_ids: tuple[str, ...]
) -> int:
    """删除目标 Run ids 对应 dispatch records。

    :param transaction: Host transaction。
    :param run_ids: 目标 Run ids。
    :returns: 删除 row 数量。
    """

    if len(run_ids) == 0:
        return 0
    return transaction.execute(
        f"""
        DELETE FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        WHERE {_in_clause("run_id", run_ids)}
        """,
        run_ids,
    ).rowcount


def _delete_attempts(transaction: HostTransaction, run_ids: tuple[str, ...]) -> int:
    """删除目标 Run ids 对应 attempts。

    :param transaction: Host transaction。
    :param run_ids: 目标 Run ids。
    :returns: 删除 row 数量。
    """

    if len(run_ids) == 0:
        return 0
    return transaction.execute(
        f"""
        DELETE FROM {TABLE_HOST_ATTEMPTS}
        WHERE {_in_clause("run_id", run_ids)}
        """,
        run_ids,
    ).rowcount


def _delete_runs_child_before_parent(
    transaction: HostTransaction, session_id: str
) -> int:
    """按 source_run_id 子先父顺序删除目标 Session Runs。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: 删除 Run row 数量。
    :raises HostDurableError: 无法在有限轮次内删除全部 Run 时抛出。
    """

    deleted = 0
    remaining = _count_by_session(transaction, TABLE_HOST_RUNS, session_id)
    while remaining > 0:
        rows = transaction.execute(
            f"""
            DELETE FROM {TABLE_HOST_RUNS}
            WHERE session_id = ?
              AND run_id NOT IN (
                SELECT source_run_id
                FROM {TABLE_HOST_RUNS}
                WHERE session_id = ?
                  AND source_run_id IS NOT NULL
              )
            """,
            (session_id, session_id),
        ).rowcount
        if rows <= 0:
            raise HostDurableError("purge could not delete Run source dependency graph")
        deleted += rows
        remaining = _count_by_session(transaction, TABLE_HOST_RUNS, session_id)
    return deleted


def _delete_by_event_ids(
    transaction: HostTransaction,
    table_name: str,
    column_name: str,
    event_ids: tuple[str, ...],
) -> int:
    """按 EventLog id 集合删除 rows。

    :param transaction: Host transaction。
    :param table_name: 目标表名，必须来自 schema 常量。
    :param column_name: EventLog id FK 列名，必须是模块内固定调用点。
    :param event_ids: EventLog ids。
    :returns: 删除 row 数量。
    """

    if len(event_ids) == 0:
        return 0
    return transaction.execute(
        f"""
        DELETE FROM {table_name}
        WHERE {_in_clause(column_name, event_ids)}
        """,
        event_ids,
    ).rowcount


def _delete_by_session(
    transaction: HostTransaction, table_name: str, session_id: str
) -> int:
    """按 session_id 删除 rows。

    :param transaction: Host transaction。
    :param table_name: 目标表名，必须来自 schema 常量。
    :param session_id: 目标 Session id。
    :returns: 删除 row 数量。
    """

    return transaction.execute(
        f"""
        DELETE FROM {table_name}
        WHERE session_id = ?
        """,
        (session_id,),
    ).rowcount


def _delete_by_pk(
    transaction: HostTransaction,
    table_name: str,
    column_name: str,
    value: str,
) -> int:
    """按单列主键删除 row。

    :param transaction: Host transaction。
    :param table_name: 目标表名，必须来自 schema 常量。
    :param column_name: 主键列名，必须是模块内固定调用点。
    :param value: 主键值。
    :returns: 删除 row 数量。
    """

    return transaction.execute(
        f"""
        DELETE FROM {table_name}
        WHERE {column_name} = ?
        """,
        (value,),
    ).rowcount


def _read_payload_descriptor_delete_ref(
    transaction: HostTransaction, payload_ref: str
) -> _PayloadDescriptorDeleteRef | None:
    """读取 payload descriptor 的删除信息。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :returns: descriptor 删除信息；不存在时为 ``None``。
    :raises HostDurableError: descriptor row 类型不符合预期时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT
          payload_ref,
          payload_kind,
          sqlite_payload_id,
          artifact_relative_path
        FROM {TABLE_PAYLOAD_DESCRIPTORS}
        WHERE payload_ref = ?
        """,
        (payload_ref,),
    )
    if row is None:
        return None
    return _PayloadDescriptorDeleteRef(
        payload_ref=_require_text(row.get("payload_ref"), field_name="payload_ref"),
        payload_kind=_require_text(row.get("payload_kind"), field_name="payload_kind"),
        sqlite_payload_id=_optional_text(
            row.get("sqlite_payload_id"),
            field_name="sqlite_payload_id",
        ),
        artifact_relative_path=_optional_text(
            row.get("artifact_relative_path"),
            field_name="artifact_relative_path",
        ),
    )


def _payload_ref_is_still_referenced(
    transaction: HostTransaction, payload_ref: str
) -> bool:
    """判断 payload ref 是否仍被 durable rows 引用。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :returns: 仍有引用时为 ``True``。
    """

    for table_name, column_name in _payload_reference_columns():
        row = transaction.fetchone(
            f"""
            SELECT 1 AS found
            FROM {table_name}
            WHERE {column_name} = ?
            LIMIT 1
            """,
            (payload_ref,),
        )
        if row is not None:
            return True
    return False


def _sqlite_payload_is_still_referenced(
    transaction: HostTransaction, sqlite_payload_id: str
) -> bool:
    """判断 SQLite payload row 是否仍被 descriptor 引用。

    :param transaction: Host transaction。
    :param sqlite_payload_id: SQLite payload id。
    :returns: 仍有 descriptor 引用时为 ``True``。
    """

    row = transaction.fetchone(
        f"""
        SELECT 1 AS found
        FROM {TABLE_PAYLOAD_DESCRIPTORS}
        WHERE sqlite_payload_id = ?
        LIMIT 1
        """,
        (sqlite_payload_id,),
    )
    return row is not None


def _payload_reference_columns() -> tuple[tuple[str, str], ...]:
    """返回所有 durable payload ref 引用列。

    :returns: ``(table_name, column_name)`` 元组集合。
    """

    return (
        (TABLE_EVENT_LOG, "payload_ref"),
        (TABLE_HOST_SESSION_TIMELINE_ITEMS, "payload_ref"),
        (TABLE_HOST_RUN_RESULTS, "result_ref"),
        (TABLE_HOST_RUN_RESULTS, "summary_ref"),
        (TABLE_HOST_MEMORY_ITEMS, "payload_ref"),
        (TABLE_HOST_TOOL_TRACE_HOT, "payload_ref"),
        (TABLE_HOST_OUTBOX_TERMINAL_ITEMS, "result_ref"),
        (TABLE_HOST_OUTBOX_TERMINAL_ITEMS, "terminal_summary_ref"),
    )


def _build_deleted_refs_digest(
    *,
    event_refs: tuple[_EventLogDeleteRef, ...],
    run_ids: tuple[str, ...],
    attempt_ids: tuple[str, ...],
    payload_refs: tuple[str, ...],
    deleted_payload_refs: tuple[str, ...],
    deleted_sqlite_payload_ids: tuple[str, ...],
    artifact_relative_paths: tuple[str, ...],
) -> str:
    """构造删除对象 refs digest。

    :param event_refs: 删除前收集的 EventLog refs。
    :param run_ids: 删除前收集的 Run ids。
    :param attempt_ids: 删除前收集的 Attempt ids。
    :param payload_refs: 删除前收集的 payload refs。
    :param deleted_payload_refs: 实际删除的 payload descriptor refs。
    :param deleted_sqlite_payload_ids: 实际删除的 SQLite payload ids。
    :param artifact_relative_paths: commit 后可清理 artifact 相对路径。
    :returns: ``sha256:`` refs digest。
    """

    value: dict[str, JsonValue] = {
        _REFS_EVENT_IDS: _json_text_list(tuple(ref.event_id for ref in event_refs)),
        _REFS_EVENT_SEQUENCES: _json_int_list(
            tuple(ref.event_sequence for ref in event_refs)
        ),
        _REFS_RUN_IDS: _json_text_list(run_ids),
        _REFS_ATTEMPT_IDS: _json_text_list(attempt_ids),
        _REFS_PAYLOAD_REFS: _json_text_list(payload_refs),
        _REFS_DELETED_PAYLOAD_REFS: _json_text_list(
            tuple(sorted(deleted_payload_refs))
        ),
        _REFS_DELETED_SQLITE_PAYLOAD_IDS: _json_text_list(
            tuple(sorted(deleted_sqlite_payload_ids))
        ),
        _REFS_ARTIFACT_RELATIVE_PATHS: _json_text_list(
            tuple(sorted(artifact_relative_paths))
        ),
    }
    return sha256_digest_json(value)


def _json_text_list(values: tuple[str, ...]) -> list[JsonValue]:
    """把文本元组转换为 JSON array。

    :param values: 文本值。
    :returns: JSON array。
    """

    result: list[JsonValue] = []
    result.extend(values)
    return result


def _json_int_list(values: tuple[int, ...]) -> list[JsonValue]:
    """把整数元组转换为 JSON array。

    :param values: 整数值。
    :returns: JSON array。
    """

    result: list[JsonValue] = []
    result.extend(values)
    return result


def _rows_json(
    transaction: HostTransaction,
    sql: str,
    parameters: tuple[str | int, ...],
) -> list[JsonValue]:
    """把查询结果转换为 canonical digest 使用的 JSON rows。

    :param transaction: Host transaction。
    :param sql: SELECT SQL。
    :param parameters: SQLite 参数。
    :returns: JSON object 列表。
    :raises HostDurableError: 查询 row 包含不可表达为 JSON 的类型时抛出。
    """

    rows = transaction.fetchall(sql, parameters)
    result: list[JsonValue] = []
    for row in rows:
        item: dict[str, JsonValue] = {}
        for index, column in enumerate(row.columns):
            item[column] = _sqlite_scalar_to_json(row.values[index])
        result.append(item)
    return result


def _sqlite_scalar_to_json(value: SQLiteScalar) -> JsonValue:
    """把 SQLite scalar 转成 JSON 值。

    :param value: SQLite scalar。
    :returns: JSON 值。
    :raises HostDurableError: ``bytes`` 等非 JSON 类型出现时抛出。
    """

    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise HostDurableError("durable row contains non-JSON scalar")


def _read_texts(
    transaction: HostTransaction,
    sql: str,
    column_name: str,
    parameters: tuple[str | int, ...],
) -> tuple[str, ...]:
    """读取单列文本查询结果。

    :param transaction: Host transaction。
    :param sql: SELECT SQL。
    :param column_name: 文本列名。
    :param parameters: SQLite 参数。
    :returns: 文本元组。
    :raises HostDurableError: row 类型不符合预期时抛出。
    """

    rows = transaction.fetchall(sql, parameters)
    return tuple(
        _require_text(row.get(column_name), field_name=column_name) for row in rows
    )


def _count_by_session(
    transaction: HostTransaction, table_name: str, session_id: str
) -> int:
    """按 session_id 统计 rows。

    :param transaction: Host transaction。
    :param table_name: 目标表名，必须来自 schema 常量。
    :param session_id: 目标 Session id。
    :returns: row 数量。
    """

    return _count_sql(
        transaction,
        f"""
        SELECT COUNT(*) AS count
        FROM {table_name}
        WHERE session_id = ?
        """,
        (session_id,),
    )


def _count_attempts_by_session(
    transaction: HostTransaction, session_id: str
) -> int:
    """统计目标 Session 的 Attempt rows。

    :param transaction: Host transaction。
    :param session_id: 目标 Session id。
    :returns: Attempt row 数量。
    """

    return _count_sql(
        transaction,
        f"""
        SELECT COUNT(*) AS count
        FROM {TABLE_HOST_ATTEMPTS} AS attempts
        JOIN {TABLE_HOST_RUNS} AS runs ON runs.run_id = attempts.run_id
        WHERE runs.session_id = ?
        """,
        (session_id,),
    )


def _count_sql(
    transaction: HostTransaction,
    sql: str,
    parameters: tuple[str | int, ...],
) -> int:
    """执行 COUNT 查询。

    :param transaction: Host transaction。
    :param sql: SELECT COUNT SQL。
    :param parameters: SQLite 参数。
    :returns: 非负 row 数量。
    :raises HostDurableError: 查询没有返回 count row 时抛出。
    """

    row = transaction.fetchone(sql, parameters)
    if row is None:
        raise HostDurableError("COUNT query returned no row")
    count = _require_int(row.get("count"), field_name="count")
    if count < 0:
        raise HostDurableError("COUNT query returned negative value")
    return count


def _in_clause(column_name: str, values: tuple[str | int, ...]) -> str:
    """构造固定列名的 SQL IN clause。

    :param column_name: SQL 列名，必须来自模块内固定调用点。
    :param values: IN 参数值。
    :returns: SQL IN clause。
    :raises HostDurableError: ``values`` 为空时抛出。
    """

    if len(values) == 0:
        raise HostDurableError("IN clause requires at least one value")
    placeholders = ", ".join("?" for _ in values)
    return f"{column_name} IN ({placeholders})"


def _placeholders(values: tuple[str | int, ...]) -> str:
    """构造 SQL 参数占位符列表。

    :param values: 参数值元组。
    :returns: 逗号分隔的 ``?`` 占位符。
    :raises HostDurableError: ``values`` 为空时抛出。
    """

    if len(values) == 0:
        raise HostDurableError("placeholder list requires at least one value")
    return ", ".join("?" for _ in values)


def _assert_deleted(label: str, actual: int, expected: int) -> None:
    """校验关键删除 rowcount。

    :param label: 诊断标签。
    :param actual: 实际删除数量。
    :param expected: 预期删除数量。
    :returns: ``None``。
    :raises HostDurableError: 数量不一致时抛出。
    """

    if actual != expected:
        raise HostDurableError(f"{label} delete count mismatch")


def _purge_idempotency_scope(
    session_id: str, client_request_id: str
) -> IdempotencyScope:
    """构造 purge 幂等作用域。

    :param session_id: 目标 Session id。
    :param client_request_id: purge 请求幂等 key。
    :returns: 幂等作用域。
    """

    return IdempotencyScope(
        scope_kind=PURGE_IDEMPOTENCY_SCOPE_KIND,
        scope_id=session_id,
        idempotency_key=client_request_id,
    )


def _optional_tombstone_from_row(row: HostRow | None) -> PurgeTombstoneRow | None:
    """把 optional HostRow 转换为 optional PurgeTombstoneRow。

    :param row: 查询返回的 HostRow。
    :returns: tombstone row 或 ``None``。
    :raises HostDurableError: durable row 类型不符合 schema 预期时抛出。
    """

    if row is None:
        return None
    return _tombstone_from_row(row)


def _tombstone_from_row(row: HostRow) -> PurgeTombstoneRow:
    """把 HostRow 转换为 PurgeTombstoneRow。

    :param row: 查询返回的 HostRow。
    :returns: tombstone row。
    :raises HostDurableError: durable row 类型不符合 schema 预期时抛出。
    """

    tombstone = PurgeTombstoneRow(
        tombstone_id=_require_text(row.get("tombstone_id"), field_name="tombstone_id"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        client_request_id=_require_text(
            row.get("client_request_id"),
            field_name="client_request_id",
        ),
        semantic_request_digest=_require_text(
            row.get("semantic_request_digest"),
            field_name="semantic_request_digest",
        ),
        actor=_optional_text(row.get("actor"), field_name="actor"),
        source=_optional_text(row.get("source"), field_name="source"),
        operation_context_digest=_optional_text(
            row.get("operation_context_digest"),
            field_name="operation_context_digest",
        ),
        operation_context_refs=_json_mapping_from_text(
            _require_text(
                row.get("operation_context_refs_json"),
                field_name="operation_context_refs_json",
            ),
            field_name="operation_context_refs_json",
        ),
        reason=_require_text(row.get("reason"), field_name="reason"),
        purged_at=_require_text(row.get("purged_at"), field_name="purged_at"),
        precondition_digest=_require_text(
            row.get("precondition_digest"),
            field_name="precondition_digest",
        ),
        deleted_counts=_deleted_counts_from_json(
            _require_text(
                row.get("deleted_counts_json"),
                field_name="deleted_counts_json",
            )
        ),
        deleted_counts_digest=_require_text(
            row.get("deleted_counts_digest"),
            field_name="deleted_counts_digest",
        ),
        deleted_refs_digest=_require_text(
            row.get("deleted_refs_digest"),
            field_name="deleted_refs_digest",
        ),
        audit_record_ref=_optional_text(
            row.get("audit_record_ref"),
            field_name="audit_record_ref",
        ),
        audit_record_digest=_optional_text(
            row.get("audit_record_digest"),
            field_name="audit_record_digest",
        ),
        request_context=_json_mapping_from_text(
            _require_text(
                row.get("request_context_json"),
                field_name="request_context_json",
            ),
            field_name="request_context_json",
        ),
    )
    _validate_tombstone(tombstone)
    return tombstone


def _select_tombstone_sql(predicate_sql: str) -> str:
    """生成 tombstone 查询 SQL。

    :param predicate_sql: ``WHERE`` 后的安全谓词 SQL。
    :returns: 完整 SELECT SQL。
    """

    return f"""
    SELECT
      tombstone_id,
      session_id,
      client_request_id,
      semantic_request_digest,
      actor,
      source,
      operation_context_digest,
      operation_context_refs_json,
      reason,
      purged_at,
      precondition_digest,
      deleted_counts_json,
      deleted_counts_digest,
      deleted_refs_digest,
      audit_record_ref,
      audit_record_digest,
      request_context_json
    FROM {TABLE_HOST_PURGE_TOMBSTONES}
    WHERE {predicate_sql}
    """


def _json_mapping_from_text(value: str, *, field_name: str) -> Mapping[str, JsonValue]:
    """解析 durable JSON object 文本。

    :param value: durable JSON 文本。
    :param field_name: 错误消息中的字段名。
    :returns: JSON object。
    :raises HostDurableError: JSON 非法或不是 object 时抛出。
    """

    try:
        parsed = cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HostDurableError(f"{field_name} JSON is invalid") from exc
    if not isinstance(parsed, Mapping):
        raise HostDurableError(f"{field_name} must be JSON object")
    for key in parsed:
        if not isinstance(key, str):
            raise HostDurableError(f"{field_name} keys must be text")
    return parsed


def _deleted_counts_from_json(value: str) -> PurgeDeleteCounts:
    """解析 deleted counts durable JSON 文本。

    :param value: durable JSON 文本。
    :returns: 删除矩阵分项计数。
    :raises HostDurableError: JSON 非法或字段类型非法时抛出。
    """

    parsed = _json_mapping_from_text(value, field_name="deleted_counts_json")
    return PurgeDeleteCounts(
        event_log_rows=_required_count(parsed, _COUNT_EVENT_LOG_ROWS),
        idempotency_records=_required_count(parsed, _COUNT_IDEMPOTENCY_RECORDS),
        payload_descriptors=_required_count(parsed, _COUNT_PAYLOAD_DESCRIPTORS),
        sqlite_payloads=_required_count(parsed, _COUNT_SQLITE_PAYLOADS),
        host_session_slots=_required_count(parsed, _COUNT_HOST_SESSION_SLOTS),
        host_sessions=_required_count(parsed, _COUNT_HOST_SESSIONS),
        host_runs=_required_count(parsed, _COUNT_HOST_RUNS),
        host_attempts=_required_count(parsed, _COUNT_HOST_ATTEMPTS),
        host_attempt_dispatch_records=_required_count(
            parsed,
            _COUNT_HOST_ATTEMPT_DISPATCH_RECORDS,
        ),
        host_wait_records=_required_count(parsed, _COUNT_HOST_WAIT_RECORDS),
        host_run_results=_required_count(parsed, _COUNT_HOST_RUN_RESULTS),
        host_session_timeline_items=_required_count(
            parsed,
            _COUNT_HOST_SESSION_TIMELINE_ITEMS,
        ),
        host_memory_snapshots=_required_count(
            parsed,
            _COUNT_HOST_MEMORY_SNAPSHOTS,
        ),
        host_memory_items=_required_count(parsed, _COUNT_HOST_MEMORY_ITEMS),
        host_memory_diagnostics=_required_count(
            parsed,
            _COUNT_HOST_MEMORY_DIAGNOSTICS,
        ),
        host_audit_sink_markers=_required_count(
            parsed,
            _COUNT_HOST_AUDIT_SINK_MARKERS,
        ),
        host_tool_trace_hot=_required_count(parsed, _COUNT_HOST_TOOL_TRACE_HOT),
        host_outbox_terminal_items=_required_count(
            parsed,
            _COUNT_HOST_OUTBOX_TERMINAL_ITEMS,
        ),
        host_outbox_drain_idempotency=_required_count(
            parsed,
            _COUNT_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
        ),
        host_projection_checkpoints=_required_count(
            parsed,
            _COUNT_HOST_PROJECTION_CHECKPOINTS,
        ),
        host_projection_failures=_required_count(
            parsed,
            _COUNT_HOST_PROJECTION_FAILURES,
        ),
    )


def _required_count(source: Mapping[str, JsonValue], field_name: str) -> int:
    """读取 JSON object 中的非负整数计数。

    :param source: JSON object。
    :param field_name: 目标字段名。
    :returns: 非负整数。
    :raises HostDurableError: 字段缺失或不是非负整数时抛出。
    """

    value = source.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")
    return value


def _validate_delete_counts(counts: PurgeDeleteCounts) -> None:
    """校验 deleted counts 全部为非负整数。

    :param counts: 删除矩阵分项计数。
    :returns: ``None``。
    :raises HostDurableError: 任一计数为负数时抛出。
    """

    values = (
        counts.event_log_rows,
        counts.idempotency_records,
        counts.payload_descriptors,
        counts.sqlite_payloads,
        counts.host_session_slots,
        counts.host_sessions,
        counts.host_runs,
        counts.host_attempts,
        counts.host_attempt_dispatch_records,
        counts.host_wait_records,
        counts.host_run_results,
        counts.host_session_timeline_items,
        counts.host_memory_snapshots,
        counts.host_memory_items,
        counts.host_memory_diagnostics,
        counts.host_audit_sink_markers,
        counts.host_tool_trace_hot,
        counts.host_outbox_terminal_items,
        counts.host_outbox_drain_idempotency,
        counts.host_projection_checkpoints,
        counts.host_projection_failures,
    )
    for value in values:
        if value < 0:
            raise HostDurableError("purge delete counts must be non-negative")


def _validate_tombstone(tombstone: PurgeTombstoneRow) -> None:
    """校验 tombstone row 字段。

    :param tombstone: 待校验 tombstone row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段不符合 durable 约束时抛出。
    """

    _require_non_empty_text(tombstone.tombstone_id, field_name="tombstone_id")
    _require_non_empty_text(tombstone.session_id, field_name="session_id")
    _require_non_empty_text(
        tombstone.client_request_id,
        field_name="client_request_id",
    )
    _require_sha256_digest(
        tombstone.semantic_request_digest,
        field_name="semantic_request_digest",
    )
    _require_optional_non_empty_text(tombstone.actor, field_name="actor")
    _require_optional_non_empty_text(tombstone.source, field_name="source")
    _require_optional_sha256_digest(
        tombstone.operation_context_digest,
        field_name="operation_context_digest",
    )
    _require_non_empty_text(tombstone.reason, field_name="reason")
    _require_non_empty_text(tombstone.purged_at, field_name="purged_at")
    _require_sha256_digest(
        tombstone.precondition_digest,
        field_name="precondition_digest",
    )
    expected_deleted_counts_digest = build_deleted_counts_digest(
        tombstone.deleted_counts
    )
    if tombstone.deleted_counts_digest != expected_deleted_counts_digest:
        raise HostDurableError("deleted_counts_digest does not match counts")
    _require_sha256_digest(
        tombstone.deleted_refs_digest,
        field_name="deleted_refs_digest",
    )
    _require_optional_non_empty_text(
        tombstone.audit_record_ref,
        field_name="audit_record_ref",
    )
    _require_optional_sha256_digest(
        tombstone.audit_record_digest,
        field_name="audit_record_digest",
    )
    if (tombstone.audit_record_ref is None) != (
        tombstone.audit_record_digest is None
    ):
        raise HostDurableError(
            "audit_record_ref and audit_record_digest must be both set or both unset"
        )


__all__ = [
    "PURGE_IDEMPOTENCY_RESULT_KIND",
    "PURGE_IDEMPOTENCY_SCOPE_KIND",
    "PurgeDeleteCounts",
    "PurgeCommitCleanupRefs",
    "PurgePreconditionSnapshot",
    "PurgeReplayDecision",
    "PurgeReplayDecisionKind",
    "PurgeSessionAlreadyPurgedError",
    "PurgeSessionDeleteRequest",
    "PurgeSessionDeleteResult",
    "PurgeSessionInvalidStateError",
    "PurgeSessionNotFoundError",
    "PurgeTombstoneRow",
    "build_deleted_counts_digest",
    "build_purge_semantic_digest",
    "insert_purge_tombstone",
    "purge_session_durable",
    "read_purge_tombstone_by_id",
    "read_purge_tombstone_by_session_id",
    "record_or_read_purge_idempotency",
]
