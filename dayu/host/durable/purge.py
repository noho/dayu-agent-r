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
from dayu.host.durable.transaction import HostRow, HostTransaction

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
    "PurgePreconditionSnapshot",
    "PurgeReplayDecision",
    "PurgeReplayDecisionKind",
    "PurgeTombstoneRow",
    "build_deleted_counts_digest",
    "build_purge_semantic_digest",
    "insert_purge_tombstone",
    "read_purge_tombstone_by_id",
    "read_purge_tombstone_by_session_id",
    "record_or_read_purge_idempotency",
]
