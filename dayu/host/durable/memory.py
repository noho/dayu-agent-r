"""Host memory projection durable read/write primitive。

本模块只操作 memory projection-owned tables，并复用 projection checkpoint
primitive 保证 snapshot content 与 checkpoint 可由调用方放入同一个 Host
durable transaction 提交。它不启动 transaction，不读取或修改 Run /
Attempt / wait / dispatch 等治理真源。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable._validation import (
    require_int as _require_int,
    optional_text as _optional_text,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.projection import (
    advance_projection_checkpoint,
    ensure_projection_checkpoint,
)
from dayu.host.durable.schema import (
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.context_events import CONTEXT_COMPACTED
from dayu.host.compact_payload import (
    ContextCompactedSemanticPayload,
    parse_context_compacted_semantic_payload,
)
from dayu.host.accepted_result_projection import project_accepted_tool_result
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    AnswerAnchor,
    ConversationMemorySnapshotVNext,
    ForwardIntent,
    MemoryClaimStatus,
    MemoryDiagnostic,
    MemoryExcludedReason,
    MemoryIncludedReason,
    MemoryProjectionEvent,
    MemoryProjectionPolicy,
    MemoryProducerKind,
    ReferenceContinuityItem,
    SelectedRecentWindowItem,
    EvidenceBackedFactView,
    calculate_memory_snapshot_digest,
    conversation_memory_snapshot_from_json_value,
    conversation_memory_snapshot_to_json_value,
    digest_memory_projection_policy,
    memory_diagnostic_from_json_value,
    memory_diagnostic_to_json_value,
    project_conversation_memory_event,
)
from dayu.host._terminal_answer import assistant_final_answer_continuity_text
from dayu.host.terminal_payload import PayloadTextReadPolicy
from dayu.host.evidence import accepted_evidence_envelope_from_payload
from dayu.host.payload_resolution import (
    event_payload_object_for_result_ref,
)
from dayu.host.projection import (
    ProjectionApplyResult,
    ProjectionApplyStatus,
    ProjectionConsumerId,
    ProjectionEventClassFilter,
    ProjectionEventFilter,
    ProjectionEventView,
)
from dayu.host.durable.event_log import EventClass, EventLogRow

_ZERO_CURSOR_SEQUENCE = 0
_ITEM_KIND_EVIDENCE_BACKED_FACT = "evidence_backed_fact"
_ITEM_KIND_OLD_VERIFIED_FACT = "verified_fact"
_ITEM_KIND_SELECTED_RECENT_WINDOW = "selected_recent_window"
_ITEM_KIND_REFERENCE_CONTINUITY = "reference_continuity"
_ITEM_KIND_ANSWER_ANCHOR = "answer_anchor"
_ITEM_KIND_FORWARD_INTENT = "forward_intent"
_ITEM_KIND_SESSION_SUMMARY = "session_summary"
_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_PROJECTION_EVENT_ROW_BODY_DIGEST_PLACEHOLDER = "memory-projection-view"
_EMPTY_PAYLOAD_JSON = "{}"
_EVENT_TYPE_FILTER = (
    _EVENT_TYPE_USER_INPUT_ACCEPTED,
    _EVENT_TYPE_RUN_SUCCEEDED,
    _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    CONTEXT_COMPACTED,
)


@dataclass(frozen=True, slots=True)
class _MemoryProjectionPayloadView:
    """Memory projection event payload 与附加 LLM-safe typed material。

    :param payload: memory projection 消费的 payload。
    :param assistant_final_answer_text: 可选 LLM-facing assistant answer
        continuity 文本，不回写 EventLog payload。
    :param evidence_query_text: 可选 LLM-safe request / query 文本。
    :param evidence_tool_name: 可选工具名。
    :param evidence_result_text: 可选 LLM-safe 工具结果文本。
    :param evidence_source_text: 可选业务可读 source 文本；accepted result 正常路径由
        统一 projection owner 提供非空 source 文本。
    :param compacted_semantics: compact event 的严格 typed semantic view。
    """

    payload: Mapping[str, JsonValue]
    assistant_final_answer_text: str | None
    evidence_query_text: str | None
    evidence_tool_name: str | None
    evidence_result_text: str | None
    evidence_source_text: str | None
    compacted_semantics: ContextCompactedSemanticPayload | None


class MemorySnapshotIntegrityFailureKind(StrEnum):
    """Memory snapshot durable row 损坏分类。

    这些分类只服务 operator-facing integrity report，不改变 snapshot 读路径的
    fail-closed 行为，也不触发 rebuild / overwrite。
    """

    INVALID_JSON = "invalid_json"
    SCHEMA_MISMATCH = "schema_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    UNSUPPORTED_ITEM_KIND = "unsupported_item_kind"
    STORAGE_READ_FAILED = "storage_read_failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class MemorySnapshotIntegrityIssue:
    """Memory snapshot integrity 只读诊断。

    :param failure_kind: 损坏分类。
    :param message: operator 可读的短错误摘要。
    :param snapshot_id: 可选 snapshot id；扫描级错误可能没有具体 row。
    :param session_id: 可选 session id。
    :param consumer_id: 可选 projection consumer id。
    :param policy_digest: 可选 memory policy digest。
    :param checkpoint_event_sequence: 可选 snapshot cursor sequence。
    :raises TypeError: ``failure_kind`` 类型不正确时抛出。
    :raises ValueError: 文本字段为空或 cursor 为负时抛出。
    """

    failure_kind: MemorySnapshotIntegrityFailureKind
    message: str
    snapshot_id: str | None
    session_id: str | None
    consumer_id: str | None
    policy_digest: str | None
    checkpoint_event_sequence: int | None

    def __post_init__(self) -> None:
        """校验诊断字段。

        :returns: ``None``。
        :raises TypeError: ``failure_kind`` 类型不正确时抛出。
        :raises ValueError: 文本字段为空或 cursor 为负时抛出。
        """

        if not isinstance(self.failure_kind, MemorySnapshotIntegrityFailureKind):
            raise TypeError(
                "MemorySnapshotIntegrityIssue.failure_kind must be "
                "MemorySnapshotIntegrityFailureKind"
            )
        _require_non_empty_text(
            self.message,
            field_name="MemorySnapshotIntegrityIssue.message",
        )
        _require_optional_non_empty_text(
            self.snapshot_id,
            field_name="MemorySnapshotIntegrityIssue.snapshot_id",
        )
        _require_optional_non_empty_text(
            self.session_id,
            field_name="MemorySnapshotIntegrityIssue.session_id",
        )
        _require_optional_non_empty_text(
            self.consumer_id,
            field_name="MemorySnapshotIntegrityIssue.consumer_id",
        )
        _require_optional_non_empty_text(
            self.policy_digest,
            field_name="MemorySnapshotIntegrityIssue.policy_digest",
        )
        if (
            self.checkpoint_event_sequence is not None
            and self.checkpoint_event_sequence < _ZERO_CURSOR_SEQUENCE
        ):
            raise ValueError(
                "MemorySnapshotIntegrityIssue.checkpoint_event_sequence "
                "must be non-negative"
            )

    def json_value(self) -> JsonValue:
        """返回 operator-facing 自解释 JSON object。

        :returns: 包含损坏分类、row identity 和短错误摘要的 JSON object。
        """

        return {
            "failure_kind": self.failure_kind.value,
            "message": self.message,
            "snapshot_id": self.snapshot_id,
            "session_id": self.session_id,
            "consumer_id": self.consumer_id,
            "policy_digest": self.policy_digest,
            "checkpoint_event_sequence": self.checkpoint_event_sequence,
        }


@dataclass(frozen=True, slots=True)
class _MemorySnapshotIntegrityRowIdentity:
    """Memory snapshot integrity 扫描中的 row identity。

    :param snapshot_id: snapshot id。
    :param session_id: session id。
    :param consumer_id: projection consumer id。
    :param policy_digest: memory policy digest。
    :param checkpoint_event_sequence: snapshot cursor sequence。
    """

    snapshot_id: str
    session_id: str
    consumer_id: str
    policy_digest: str
    checkpoint_event_sequence: int


def conversation_memory_projection_event_filter() -> ProjectionEventFilter:
    """返回 Conversation Memory projection 的唯一 EventLog filter 真源。

    :returns: 只覆盖 conversation memory 可消费 canonical facts 的 projection filter。
    :raises HostDurableError: filter 构造失败时抛出。
    """

    return ProjectionEventFilter(
        (
            ProjectionEventClassFilter(
                event_class=EventClass.CANONICAL_FACT,
                event_types=_EVENT_TYPE_FILTER,
            ),
        )
    )


class ConversationMemoryProjectionConsumer:
    """Conversation memory projection consumer。

    本 consumer 只消费已提交 canonical EventLog facts，并在当前 projection
    transaction 内写 memory-owned snapshot / item / diagnostic tables；Run /
    Attempt 状态与 EventLog 均不由本 consumer 修改。

    :param policy: memory projection policy。
    :param consumer_id: 可选稳定 consumer id；默认使用 P9 memory consumer id。
    """

    def __init__(
        self,
        policy: MemoryProjectionPolicy,
        *,
        consumer_id: str = CONVERSATION_MEMORY_CONSUMER_ID,
    ) -> None:
        """初始化 consumer。

        :param policy: memory projection policy。
        :param consumer_id: 稳定 projection consumer id。
        :returns: ``None``。
        """

        self._policy = policy
        self._policy_digest = digest_memory_projection_policy(policy)
        self._consumer_id = ProjectionConsumerId(consumer_id)
        self._event_filter = conversation_memory_projection_event_filter()

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回稳定 projection consumer id。

        :returns: projection consumer id。
        """

        return self._consumer_id

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回 memory projection event filter。

        :returns: 只消费 canonical memory 相关 event type 的 filter。
        """

        return self._event_filter

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """在当前 transaction 内投影单个 EventLog event。

        :param transaction: Host durable transaction。
        :param event: projection runner 构造的 typed event view。
        :returns: projection apply result。
        :raises HostDurableError: snapshot 读取、投影或写入失败时抛出。
        """

        latest = read_latest_memory_snapshot(
            transaction,
            session_id=event.session_id,
            consumer_id=self._consumer_id.value,
            policy_digest=self._policy_digest,
        )
        previous_snapshot = None if latest is None else latest.snapshot
        if (
            previous_snapshot is not None
            and previous_snapshot.cursor.checkpoint_event_sequence
            >= event.event_sequence
        ):
            return ProjectionApplyResult(ProjectionApplyStatus.DUPLICATE)
        snapshot = project_conversation_memory_event(
            previous_snapshot=previous_snapshot,
            event=_memory_projection_event_from_view(transaction, event),
            policy=self._policy,
            built_at=event.occurred_at,
            consumer_id=self._consumer_id.value,
        )
        write_memory_snapshot(transaction, snapshot, updated_at=event.occurred_at)
        return ProjectionApplyResult(ProjectionApplyStatus.APPLIED)


def _memory_projection_event_from_view(
    transaction: HostTransaction,
    event: ProjectionEventView,
) -> MemoryProjectionEvent:
    """把 projection runner event view 转换为 memory projection event。

    :param transaction: Host transaction。
    :param event: projection runner event view。
    :returns: memory projection event。
    """

    payload_view = _memory_projection_payload_view(transaction, event)
    return MemoryProjectionEvent(
        event_sequence=event.event_sequence,
        event_id=event.event_id,
        event_class=event.event_class.value,
        event_type=event.event_type,
        session_id=event.session_id,
        run_id=event.run_id,
        attempt_id=event.attempt_id,
        execution_id=event.execution_id,
        occurred_at=event.occurred_at,
        payload_ref=event.payload_ref,
        payload_digest=event.payload_digest,
        payload=payload_view.payload,
        compacted_semantics=payload_view.compacted_semantics,
        assistant_final_answer_text=payload_view.assistant_final_answer_text,
        evidence_query_text=payload_view.evidence_query_text,
        evidence_tool_name=payload_view.evidence_tool_name,
        evidence_result_text=payload_view.evidence_result_text,
        evidence_source_text=payload_view.evidence_source_text,
    )


def _memory_projection_payload_view(
    transaction: HostTransaction, event: ProjectionEventView
) -> _MemoryProjectionPayloadView:
    """构造 memory projection 需要的 payload view 与 typed material。

    :param transaction: Host transaction。
    :param event: projection runner event view。
    :returns: memory projection 消费的 payload view。
    :raises HostDurableError: terminal artifact descriptor 或工具 payload 损坏时抛出。
    :raises ValueError: persisted compact semantic payload 非法时抛出。
    """

    if event.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
        return _tool_result_memory_payload_view(transaction, event)
    if event.event_type == CONTEXT_COMPACTED:
        return _MemoryProjectionPayloadView(
            payload=event.payload,
            assistant_final_answer_text=None,
            evidence_query_text=None,
            evidence_tool_name=None,
            evidence_result_text=None,
            evidence_source_text=None,
            compacted_semantics=parse_context_compacted_semantic_payload(
                event.payload
            ),
        )
    if event.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
        return _MemoryProjectionPayloadView(
            payload=event.payload,
            assistant_final_answer_text=None,
            evidence_query_text=None,
            evidence_tool_name=None,
            evidence_result_text=None,
            evidence_source_text=None,
            compacted_semantics=None,
        )
    final_answer = assistant_final_answer_continuity_text(
        transaction,
        event.payload,
        text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
    )
    return _MemoryProjectionPayloadView(
        payload=event.payload,
        assistant_final_answer_text=final_answer,
        evidence_query_text=None,
        evidence_tool_name=None,
        evidence_result_text=None,
        evidence_source_text=None,
        compacted_semantics=None,
    )


def _tool_result_memory_payload_view(
    transaction: HostTransaction,
    event: ProjectionEventView,
) -> _MemoryProjectionPayloadView:
    """读取 memory projection 使用的完整 accepted tool result payload。

    :param transaction: Host transaction。
    :param event: ``TOOL_RESULT_ACCEPTED`` projection event view。
    :returns: digest-checked 工具结果 payload view。
    :raises HostDurableError: envelope 或 payload descriptor 损坏时抛出。
    """

    result_row = _event_row_from_projection_event(event)
    projection = project_accepted_tool_result(
        transaction,
        result_row,
        resolved_payload=event.payload,
    )
    if not projection.envelope_available:
        return _MemoryProjectionPayloadView(
            payload=event.payload,
            assistant_final_answer_text=None,
            evidence_query_text=projection.query.text,
            evidence_tool_name=projection.tool_name,
            evidence_result_text=projection.result_text,
            evidence_source_text=projection.source.text,
            compacted_semantics=None,
        )
    envelope = accepted_evidence_envelope_from_payload(
        event.payload,
        producer_event_ref=event.event_id,
    )
    if envelope is None:
        raise HostDurableError("canonical evidence envelope is missing")
    payload = event_payload_object_for_result_ref(
        transaction,
        result_row,
        expected_payload_ref=envelope.result_ref.payload_ref,
        expected_payload_digest=envelope.result_ref.payload_digest,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    return _MemoryProjectionPayloadView(
        payload=payload,
        assistant_final_answer_text=None,
        evidence_query_text=projection.query.text,
        evidence_tool_name=projection.tool_name,
        evidence_result_text=projection.result_text,
        evidence_source_text=projection.source.text,
        compacted_semantics=None,
    )


def _event_row_from_projection_event(event: ProjectionEventView) -> EventLogRow:
    """把 projection event view 转成只读 payload resolution 所需 EventLog row。

    :param event: projection event view。
    :returns: EventLog row view。
    """

    return EventLogRow(
        event_sequence=event.event_sequence,
        event_id=event.event_id,
        event_body_digest=_PROJECTION_EVENT_ROW_BODY_DIGEST_PLACEHOLDER,
        event_class=event.event_class,
        session_id=event.session_id,
        run_id=event.run_id,
        attempt_id=event.attempt_id,
        execution_id=event.execution_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        actor=None,
        source=None,
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=_EMPTY_PAYLOAD_JSON,
        payload_ref=event.payload_ref,
        payload_digest=event.payload_digest,
        appended_at=event.occurred_at,
    )


@dataclass(frozen=True, slots=True)
class MemorySnapshotRow:
    """Memory snapshot durable row。

    :param snapshot: typed memory snapshot。
    :param updated_at: row 最近更新时间。
    """

    snapshot: ConversationMemorySnapshotVNext
    updated_at: str


@dataclass(frozen=True, slots=True)
class MemoryDiagnosticRow:
    """Memory diagnostic durable row。

    :param session_id: diagnostic 所属 session id。
    :param snapshot_id: 可选 snapshot id。
    :param diagnostic: typed memory diagnostic。
    :param recorded_at: durable row 记录时间。
    """

    session_id: str
    snapshot_id: str | None
    diagnostic: MemoryDiagnostic
    recorded_at: str


def read_memory_snapshot(
    transaction: HostTransaction, snapshot_id: str
) -> MemorySnapshotRow | None:
    """按 snapshot id 读取 memory snapshot。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot_id: snapshot id。
    :returns: 存在时返回 snapshot row，否则返回 ``None``。
    :raises HostDurableError: 输入无效、durable row 类型不符合预期或 digest 校验失败时抛出。
    """

    _require_non_empty_text(snapshot_id, field_name="snapshot_id")
    row = transaction.fetchone(
        f"""
        SELECT snapshot_json, updated_at
        FROM {TABLE_HOST_MEMORY_SNAPSHOTS}
        WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    )
    if row is None:
        return None
    return _snapshot_row_from_host_row(transaction, row)


def read_latest_memory_snapshot(
    transaction: HostTransaction,
    *,
    session_id: str,
    consumer_id: str,
    policy_digest: str,
) -> MemorySnapshotRow | None:
    """读取指定 session / consumer / policy 下最新 memory snapshot。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: session id。
    :param consumer_id: memory projection consumer id。
    :param policy_digest: memory policy digest。
    :returns: 存在时返回最新 snapshot row，否则返回 ``None``。
    :raises HostDurableError: 输入无效、durable row 类型不符合预期或 digest 校验失败时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(consumer_id, field_name="consumer_id")
    _require_non_empty_text(policy_digest, field_name="policy_digest")
    row = transaction.fetchone(
        f"""
        SELECT snapshot_json, updated_at
        FROM {TABLE_HOST_MEMORY_SNAPSHOTS}
        WHERE session_id = ?
          AND consumer_id = ?
          AND policy_digest = ?
        ORDER BY checkpoint_event_sequence DESC, updated_at DESC, snapshot_id DESC
        LIMIT 1
        """,
        (session_id, consumer_id, policy_digest),
    )
    if row is None:
        return None
    return _snapshot_row_from_host_row(transaction, row)


def read_latest_memory_snapshot_at_or_before(
    transaction: HostTransaction,
    *,
    session_id: str,
    consumer_id: str,
    policy_digest: str,
    max_checkpoint_event_sequence: int,
) -> MemorySnapshotRow | None:
    """读取不超过指定 cursor 的最新 memory snapshot。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: session id。
    :param consumer_id: memory projection consumer id。
    :param policy_digest: memory policy digest。
    :param max_checkpoint_event_sequence: 最大允许 checkpoint event sequence。
    :returns: 存在时返回最新 snapshot row，否则返回 ``None``。
    :raises HostDurableError: 输入无效、cursor 为负、durable row 类型不符合预期或 digest 校验失败时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(consumer_id, field_name="consumer_id")
    _require_non_empty_text(policy_digest, field_name="policy_digest")
    if max_checkpoint_event_sequence < _ZERO_CURSOR_SEQUENCE:
        raise HostDurableError("max_checkpoint_event_sequence must be non-negative")
    row = transaction.fetchone(
        f"""
        SELECT snapshot_json, updated_at
        FROM {TABLE_HOST_MEMORY_SNAPSHOTS}
        WHERE session_id = ?
          AND consumer_id = ?
          AND policy_digest = ?
          AND checkpoint_event_sequence <= ?
        ORDER BY checkpoint_event_sequence DESC, updated_at DESC, snapshot_id DESC
        LIMIT 1
        """,
        (
            session_id,
            consumer_id,
            policy_digest,
            max_checkpoint_event_sequence,
        ),
    )
    if row is None:
        return None
    return _snapshot_row_from_host_row(transaction, row)


def inspect_memory_snapshot_integrity(
    transaction: HostTransaction,
) -> tuple[MemorySnapshotIntegrityIssue, ...]:
    """扫描 memory snapshot durable rows 并返回损坏分类。

    本函数是 operator-facing maintenance report 使用的只读 classifier。它不
    修改 SQLite row，不触发 rebuild / overwrite，也不改变现有
    ``read_memory_snapshot`` fail-closed 语义。手工 SQL 修改导致的损坏会被
    JSON、schema、digest、item kind 或 storage read 分类捕获。

    :param transaction: 调用方提供的 Host durable transaction。
    :returns: 按 snapshot id 排序的 integrity issue tuple；无损坏时为空。
    """

    try:
        rows = _memory_snapshot_integrity_rows(transaction)
    except sqlite3.Error as exc:
        return (
            _memory_snapshot_integrity_issue(
                failure_kind=MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED,
                message=f"memory snapshot integrity scan failed: {exc}",
                identity=None,
            ),
        )
    issues: list[MemorySnapshotIntegrityIssue] = []
    for row in rows:
        issues.extend(_memory_snapshot_integrity_issues_for_row(transaction, row))
    return tuple(issues)


def write_memory_snapshot(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    *,
    updated_at: str,
) -> MemorySnapshotRow:
    """写入 memory snapshot content 与可索引 item / diagnostic rows。

    本函数只写 memory-owned tables，不推进 projection checkpoint。需要同事务
    提交 checkpoint 时调用 :func:`write_memory_snapshot_with_checkpoint`。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param updated_at: durable row 更新时间。
    :returns: 写入后的 snapshot row。
    :raises HostDurableError: 输入无效、digest 不匹配或写入后无法读回时抛出。
    """

    _require_non_empty_text(updated_at, field_name="updated_at")
    _validate_snapshot_digest(snapshot)
    snapshot_json = canonical_json_dumps(
        conversation_memory_snapshot_to_json_value(snapshot)
    )
    transaction.execute(
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_id) DO UPDATE SET
          session_id = excluded.session_id,
          consumer_id = excluded.consumer_id,
          checkpoint_event_sequence = excluded.checkpoint_event_sequence,
          checkpoint_event_id = excluded.checkpoint_event_id,
          policy_digest = excluded.policy_digest,
          snapshot_digest = excluded.snapshot_digest,
          snapshot_json = excluded.snapshot_json,
          built_at = excluded.built_at,
          updated_at = excluded.updated_at
        """,
        (
            snapshot.snapshot_id,
            snapshot.session_id,
            snapshot.cursor.consumer_id,
            snapshot.cursor.checkpoint_event_sequence,
            snapshot.cursor.checkpoint_event_id,
            snapshot.policy_digest,
            snapshot.snapshot_digest,
            snapshot_json,
            snapshot.built_at,
            updated_at,
        ),
    )
    _replace_memory_items(transaction, snapshot)
    _replace_snapshot_diagnostics(transaction, snapshot, recorded_at=updated_at)
    written = read_memory_snapshot(transaction, snapshot.snapshot_id)
    if written is None:
        raise HostDurableError("memory snapshot write failed")
    return written


def write_memory_snapshot_with_checkpoint(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    *,
    now: str,
) -> MemorySnapshotRow:
    """同一 transaction 内写入 memory snapshot 并推进 projection checkpoint。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param now: durable row 更新时间与 checkpoint 更新时间。
    :returns: 写入后的 snapshot row。
    :raises HostDurableError: 输入无效、snapshot 写入失败或 checkpoint 推进失败时抛出。
    """

    written = write_memory_snapshot(transaction, snapshot, updated_at=now)
    if snapshot.cursor.checkpoint_event_sequence == _ZERO_CURSOR_SEQUENCE:
        ensure_projection_checkpoint(
            transaction,
            snapshot.cursor.consumer_id,
            now=now,
        )
    else:
        checkpoint_event_id = snapshot.cursor.checkpoint_event_id
        if checkpoint_event_id is None:
            raise HostDurableError("positive memory cursor requires event id")
        advance_projection_checkpoint(
            transaction,
            snapshot.cursor.consumer_id,
            event_sequence=snapshot.cursor.checkpoint_event_sequence,
            event_id=checkpoint_event_id,
            now=now,
        )
    return written


def write_memory_diagnostic(
    transaction: HostTransaction,
    *,
    session_id: str,
    snapshot_id: str | None,
    diagnostic: MemoryDiagnostic,
    recorded_at: str,
) -> MemoryDiagnosticRow:
    """写入独立 memory diagnostic row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: diagnostic 所属 session id。
    :param snapshot_id: 可选 snapshot id。
    :param diagnostic: typed memory diagnostic。
    :param recorded_at: durable row 记录时间。
    :returns: 写入后的 diagnostic row。
    :raises HostDurableError: 输入无效或写入后无法读回时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_optional_non_empty_text(snapshot_id, field_name="snapshot_id")
    _require_non_empty_text(recorded_at, field_name="recorded_at")
    _insert_memory_diagnostic(
        transaction,
        session_id=session_id,
        snapshot_id=snapshot_id,
        diagnostic=diagnostic,
        recorded_at=recorded_at,
    )
    written = read_memory_diagnostic(transaction, diagnostic.diagnostic_id)
    if written is None:
        raise HostDurableError("memory diagnostic write failed")
    return written


def reset_conversation_memory_projection(
    transaction: HostTransaction, *, consumer_id: str
) -> None:
    """清空目标 conversation memory projection rows 及其 cursor / failure。

    projection checkpoint / failure 当前是 ``consumer_id`` 粒度，因此 reset
    必须清理该 consumer 的全部 snapshot 及其关联 item / diagnostic rows，
    避免同 consumer 其它 policy snapshot 与新 checkpoint 脱节。其它 consumer
    的 memory rows 不受影响；``snapshot_id`` 为空的独立 diagnostic 不属于某个
    snapshot，不能在这里无条件删除。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: memory projection consumer id。
    :returns: ``None``。
    :raises HostDurableError: ``consumer_id`` 为空时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    snapshot_filter = (
        f"SELECT snapshot_id FROM {TABLE_HOST_MEMORY_SNAPSHOTS} "
        "WHERE consumer_id = ?"
    )
    transaction.execute(
        f"""
        DELETE FROM {TABLE_HOST_MEMORY_DIAGNOSTICS}
        WHERE snapshot_id IN ({snapshot_filter})
        """,
        (consumer_id,),
    )
    transaction.execute(
        f"""
        DELETE FROM {TABLE_HOST_MEMORY_ITEMS}
        WHERE snapshot_id IN ({snapshot_filter})
        """,
        (consumer_id,),
    )
    transaction.execute(
        f"""
        DELETE FROM {TABLE_HOST_MEMORY_SNAPSHOTS}
        WHERE consumer_id = ?
        """,
        (consumer_id,),
    )
    transaction.execute(
        f"DELETE FROM {TABLE_HOST_PROJECTION_FAILURES} WHERE consumer_id = ?",
        (consumer_id,),
    )
    transaction.execute(
        f"DELETE FROM {TABLE_HOST_PROJECTION_CHECKPOINTS} WHERE consumer_id = ?",
        (consumer_id,),
    )


def read_memory_diagnostic(
    transaction: HostTransaction, diagnostic_id: str
) -> MemoryDiagnosticRow | None:
    """读取 memory diagnostic row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param diagnostic_id: diagnostic id。
    :returns: 存在时返回 diagnostic row，否则返回 ``None``。
    :raises HostDurableError: 输入无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(diagnostic_id, field_name="diagnostic_id")
    row = transaction.fetchone(
        f"""
        SELECT
          session_id,
          snapshot_id,
          diagnostic_json,
          recorded_at
        FROM {TABLE_HOST_MEMORY_DIAGNOSTICS}
        WHERE diagnostic_id = ?
        """,
        (diagnostic_id,),
    )
    if row is None:
        return None
    return _diagnostic_row_from_host_row(row)


def _replace_memory_items(
    transaction: HostTransaction, snapshot: ConversationMemorySnapshotVNext
) -> None:
    """替换 snapshot 对应的 item rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :returns: ``None``。
    """

    transaction.execute(
        f"DELETE FROM {TABLE_HOST_MEMORY_ITEMS} WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    )
    for item in snapshot.trace_memory.selected_recent_window:
        _insert_selected_recent_window_item(transaction, snapshot, item)
    for item in snapshot.evidence_fact_memory.evidence_backed_facts:
        _insert_evidence_backed_fact_item(transaction, snapshot, item)
    if snapshot.session_summary_memory.summary_text is not None:
        _insert_session_summary_item(transaction, snapshot)
    for item in snapshot.answer_anchor_memory.anchors:
        _insert_answer_anchor_item(transaction, snapshot, item)
    for item in snapshot.forward_intent_memory.intents:
        _insert_forward_intent_item(transaction, snapshot, item)
    for item in snapshot.trace_memory.reference_continuity_items:
        _insert_reference_continuity_item(transaction, snapshot, item)


def _replace_snapshot_diagnostics(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    *,
    recorded_at: str,
) -> None:
    """替换 snapshot 内嵌 diagnostic rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param recorded_at: durable row 记录时间。
    :returns: ``None``。
    """

    transaction.execute(
        f"DELETE FROM {TABLE_HOST_MEMORY_DIAGNOSTICS} WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    )
    for diagnostic in snapshot.diagnostics:
        _insert_memory_diagnostic(
            transaction,
            session_id=snapshot.session_id,
            snapshot_id=snapshot.snapshot_id,
            diagnostic=diagnostic,
            recorded_at=recorded_at,
        )


def _insert_evidence_backed_fact_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item: EvidenceBackedFactView,
) -> None:
    """插入 evidence-backed fact item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: evidence-backed fact item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_EVIDENCE_BACKED_FACT,
        claim_status=MemoryClaimStatus.EVIDENCE_BACKED,
        event_id=item.provenance.event_id,
        event_sequence=item.provenance.event_sequence,
        producer_kind=item.provenance.producer_kind,
        producer_name=item.provenance.producer_name,
        payload_ref=item.provenance.payload_ref,
        payload_digest=_payload_digest_for_evidence_backed_fact(item),
        item_json=canonical_json_dumps(_evidence_backed_fact_item_json_value(item)),
        included_reason=item.included_reason,
        excluded_reason=item.excluded_reason,
    )


def _payload_digest_for_evidence_backed_fact(item: EvidenceBackedFactView) -> str | None:
    """返回 evidence-backed fact item row 的 payload digest 列值。

    item row 的 ``payload_ref`` / ``payload_digest`` 列只表示 payload
    descriptor 成对索引；工具 outcome digest 等非 payload digest 保留在
    item JSON 的 provenance 中，不能写入该列破坏 schema CHECK。

    :param item: evidence-backed fact item。
    :returns: payload ref 存在时返回 payload digest 列值，否则返回 ``None``。
    """

    if item.provenance.payload_ref is None:
        return None
    return item.provenance.digest_ref


def _insert_selected_recent_window_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item: SelectedRecentWindowItem,
) -> None:
    """插入 selected recent window item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: selected recent window item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_SELECTED_RECENT_WINDOW,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name=MemoryProducerKind.HOST_PROJECTION.value,
        payload_ref=None,
        payload_digest=None,
        item_json=canonical_json_dumps(_selected_recent_item_json_value(item)),
        included_reason=item.included_reason,
        excluded_reason=item.excluded_reason,
    )


def _insert_session_summary_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
) -> None:
    """插入 session summary item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :returns: ``None``。
    :raises HostDurableError: summary 字段不完整时抛出。
    """

    summary = snapshot.session_summary_memory
    if (
        summary.summary_text is None
        or summary.event_id is None
        or summary.event_sequence is None
    ):
        raise HostDurableError("session summary memory item is incomplete")
    item_id = f"{snapshot.snapshot_id}:session_summary"
    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item_id,
        item_kind=_ITEM_KIND_SESSION_SUMMARY,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=summary.event_id,
        event_sequence=summary.event_sequence,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name=MemoryProducerKind.HOST_PROJECTION.value,
        payload_ref=None,
        payload_digest=None,
        item_json=canonical_json_dumps(
            {
                "item_id": item_id,
                "size_units": summary.size_units.units,
                "source_refs": list(summary.source_refs),
                "summary_text": summary.summary_text,
            }
        ),
        included_reason=MemoryIncludedReason.SESSION_SUMMARY,
        excluded_reason=None,
    )


def _insert_answer_anchor_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item: AnswerAnchor,
) -> None:
    """插入 answer anchor item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: answer anchor item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_ANSWER_ANCHOR,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name=MemoryProducerKind.HOST_PROJECTION.value,
        payload_ref=None,
        payload_digest=None,
        item_json=canonical_json_dumps(_answer_anchor_item_json_value(item)),
        included_reason=MemoryIncludedReason.ANSWER_ANCHOR,
        excluded_reason=None,
    )


def _insert_forward_intent_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item: ForwardIntent,
) -> None:
    """插入 forward intent item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: forward intent item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_FORWARD_INTENT,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name=MemoryProducerKind.HOST_PROJECTION.value,
        payload_ref=None,
        payload_digest=None,
        item_json=canonical_json_dumps(_forward_intent_item_json_value(item)),
        included_reason=MemoryIncludedReason.FORWARD_INTENT,
        excluded_reason=None,
    )


def _insert_reference_continuity_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item: ReferenceContinuityItem,
) -> None:
    """插入 reference continuity item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: reference continuity item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_REFERENCE_CONTINUITY,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name=MemoryProducerKind.HOST_PROJECTION.value,
        payload_ref=None,
        payload_digest=None,
        item_json=canonical_json_dumps(_reference_continuity_item_json_value(item)),
        included_reason=MemoryIncludedReason.REFERENCE_CONTINUITY,
        excluded_reason=None,
    )


def _insert_item(
    transaction: HostTransaction,
    *,
    snapshot: ConversationMemorySnapshotVNext,
    item_id: str,
    item_kind: str,
    claim_status: MemoryClaimStatus,
    event_id: str,
    event_sequence: int,
    producer_kind: MemoryProducerKind,
    producer_name: str,
    payload_ref: str | None,
    payload_digest: str | None,
    item_json: str,
    included_reason: MemoryIncludedReason | None,
    excluded_reason: MemoryExcludedReason | None,
) -> None:
    """插入 memory item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item_id: item id。
    :param item_kind: item kind。
    :param claim_status: claim status。
    :param event_id: EventLog id。
    :param event_sequence: EventLog sequence。
    :param producer_kind: producer kind。
    :param producer_name: producer name。
    :param payload_ref: optional payload ref。
    :param payload_digest: optional payload digest。
    :param item_json: item JSON 文本。
    :param included_reason: optional included reason。
    :param excluded_reason: optional excluded reason。
    :returns: ``None``。
    """

    transaction.execute(
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
          payload_ref,
          payload_digest,
          item_json,
          included_reason,
          excluded_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            snapshot.snapshot_id,
            snapshot.session_id,
            item_kind,
            claim_status.value,
            event_id,
            event_sequence,
            producer_kind.value,
            producer_name,
            payload_ref,
            payload_digest,
            item_json,
            None if included_reason is None else included_reason.value,
            None if excluded_reason is None else excluded_reason.value,
        ),
    )


def _insert_memory_diagnostic(
    transaction: HostTransaction,
    *,
    session_id: str,
    snapshot_id: str | None,
    diagnostic: MemoryDiagnostic,
    recorded_at: str,
) -> None:
    """插入或替换 memory diagnostic row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: session id。
    :param snapshot_id: 可选 snapshot id。
    :param diagnostic: typed memory diagnostic。
    :param recorded_at: durable row 记录时间。
    :returns: ``None``。
    """

    diagnostic_json = canonical_json_dumps(
        memory_diagnostic_to_json_value(diagnostic)
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_MEMORY_DIAGNOSTICS} (
          diagnostic_id,
          session_id,
          snapshot_id,
          reason,
          event_sequence,
          policy_digest,
          diagnostic_json,
          recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(diagnostic_id) DO UPDATE SET
          session_id = excluded.session_id,
          snapshot_id = excluded.snapshot_id,
          reason = excluded.reason,
          event_sequence = excluded.event_sequence,
          policy_digest = excluded.policy_digest,
          diagnostic_json = excluded.diagnostic_json,
          recorded_at = excluded.recorded_at
        """,
        (
            diagnostic.diagnostic_id,
            session_id,
            snapshot_id,
            diagnostic.reason.value,
            diagnostic.event_sequence,
            diagnostic.policy_digest,
            diagnostic_json,
            recorded_at,
        ),
    )


def _snapshot_row_from_host_row(
    transaction: HostTransaction, row: HostRow
) -> MemorySnapshotRow:
    """把 durable row 转换为 typed snapshot row。

    :param transaction: Host durable transaction。
    :param row: Host durable row。
    :returns: typed snapshot row。
    :raises HostDurableError: JSON 无法解析或 digest 不匹配时抛出。
    """

    snapshot_json = _require_text(row.get("snapshot_json"), field_name="snapshot_json")
    updated_at = _require_text(row.get("updated_at"), field_name="updated_at")
    snapshot = _snapshot_from_json_text(snapshot_json)
    _validate_snapshot_digest(snapshot)
    _validate_snapshot_item_kinds(transaction, snapshot.snapshot_id)
    return MemorySnapshotRow(snapshot=snapshot, updated_at=updated_at)


def _memory_snapshot_integrity_rows(
    transaction: HostTransaction,
) -> tuple[HostRow, ...]:
    """读取 memory snapshot integrity scan 需要的 row。

    :param transaction: Host durable transaction。
    :returns: snapshot row 元组。
    :raises sqlite3.Error: SQLite 查询失败时抛出。
    """

    return transaction.fetchall(
        f"""
        SELECT
          snapshot_id,
          session_id,
          consumer_id,
          checkpoint_event_sequence,
          policy_digest,
          snapshot_digest,
          snapshot_json
        FROM {TABLE_HOST_MEMORY_SNAPSHOTS}
        ORDER BY snapshot_id
        """
    )


def _memory_snapshot_integrity_issues_for_row(
    transaction: HostTransaction,
    row: HostRow,
) -> tuple[MemorySnapshotIntegrityIssue, ...]:
    """返回单个 snapshot row 的 integrity issues。

    :param transaction: Host durable transaction。
    :param row: snapshot durable row。
    :returns: 当前 row 的 issue tuple。
    """

    try:
        identity = _memory_snapshot_integrity_row_identity(row)
        snapshot_json = _require_text(
            row.get("snapshot_json"),
            field_name="snapshot_json",
        )
        row_snapshot_digest = _require_text(
            row.get("snapshot_digest"),
            field_name="snapshot_digest",
        )
    except (HostDurableError, KeyError) as exc:
        return (
            _memory_snapshot_integrity_issue(
                failure_kind=MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED,
                message=f"memory snapshot row identity read failed: {exc}",
                identity=None,
            ),
        )
    snapshot_issue = _memory_snapshot_json_integrity_issue(
        snapshot_json,
        row_snapshot_digest=row_snapshot_digest,
        identity=identity,
    )
    if snapshot_issue is not None:
        return (snapshot_issue,)
    return _memory_snapshot_item_kind_integrity_issues(transaction, identity)


def _memory_snapshot_integrity_row_identity(
    row: HostRow,
) -> _MemorySnapshotIntegrityRowIdentity:
    """从 snapshot scan row 读取 identity 字段。

    :param row: snapshot durable row。
    :returns: row identity。
    :raises HostDurableError: 字段类型不符合预期时抛出。
    :raises KeyError: 缺少字段时抛出。
    """

    return _MemorySnapshotIntegrityRowIdentity(
        snapshot_id=_require_text(row.get("snapshot_id"), field_name="snapshot_id"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        consumer_id=_require_text(row.get("consumer_id"), field_name="consumer_id"),
        policy_digest=_require_text(
            row.get("policy_digest"),
            field_name="policy_digest",
        ),
        checkpoint_event_sequence=_require_int(
            row.get("checkpoint_event_sequence"),
            field_name="checkpoint_event_sequence",
        ),
    )


def _memory_snapshot_json_integrity_issue(
    snapshot_json: str,
    *,
    row_snapshot_digest: str,
    identity: _MemorySnapshotIntegrityRowIdentity,
) -> MemorySnapshotIntegrityIssue | None:
    """检查 snapshot JSON、typed shape 与 digest。

    :param snapshot_json: durable row 中的 snapshot JSON 文本。
    :param row_snapshot_digest: durable row 中的 snapshot digest 列值。
    :param identity: snapshot row identity。
    :returns: 发现损坏时返回 issue，否则返回 ``None``。
    """

    try:
        json_value = cast(JsonValue, json.loads(snapshot_json))
    except json.JSONDecodeError as exc:
        return _memory_snapshot_integrity_issue(
            failure_kind=MemorySnapshotIntegrityFailureKind.INVALID_JSON,
            message=f"memory snapshot JSON is invalid: {exc.msg}",
            identity=identity,
        )
    try:
        snapshot = conversation_memory_snapshot_from_json_value(json_value)
    except (TypeError, ValueError) as exc:
        return _memory_snapshot_integrity_issue(
            failure_kind=MemorySnapshotIntegrityFailureKind.SCHEMA_MISMATCH,
            message=f"memory snapshot JSON schema mismatch: {exc}",
            identity=identity,
        )
    expected_digest = calculate_memory_snapshot_digest(snapshot)
    if snapshot.snapshot_digest != expected_digest:
        return _memory_snapshot_integrity_issue(
            failure_kind=MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH,
            message="memory snapshot digest does not match canonical content",
            identity=identity,
        )
    if row_snapshot_digest != snapshot.snapshot_digest:
        return _memory_snapshot_integrity_issue(
            failure_kind=MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH,
            message="memory snapshot row digest does not match snapshot content",
            identity=identity,
        )
    return None


def _memory_snapshot_item_kind_integrity_issues(
    transaction: HostTransaction,
    identity: _MemorySnapshotIntegrityRowIdentity,
) -> tuple[MemorySnapshotIntegrityIssue, ...]:
    """检查 snapshot 关联 item rows 的 kind 是否仍受支持。

    :param transaction: Host durable transaction。
    :param identity: snapshot row identity。
    :returns: item kind issue tuple。
    """

    try:
        rows = transaction.fetchall(
            f"""
            SELECT item_kind
            FROM {TABLE_HOST_MEMORY_ITEMS}
            WHERE snapshot_id = ?
            ORDER BY item_kind
            """,
            (identity.snapshot_id,),
        )
    except sqlite3.Error as exc:
        return (
            _memory_snapshot_integrity_issue(
                failure_kind=MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED,
                message=f"memory snapshot item kind scan failed: {exc}",
                identity=identity,
            ),
        )
    allowed_kinds = (
        _ITEM_KIND_EVIDENCE_BACKED_FACT,
        _ITEM_KIND_SELECTED_RECENT_WINDOW,
        _ITEM_KIND_REFERENCE_CONTINUITY,
        _ITEM_KIND_ANSWER_ANCHOR,
        _ITEM_KIND_FORWARD_INTENT,
        _ITEM_KIND_SESSION_SUMMARY,
    )
    issues: list[MemorySnapshotIntegrityIssue] = []
    for row in rows:
        try:
            item_kind = _require_text(row.get("item_kind"), field_name="item_kind")
        except (HostDurableError, KeyError) as exc:
            issues.append(
                _memory_snapshot_integrity_issue(
                    failure_kind=MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED,
                    message=f"memory snapshot item kind read failed: {exc}",
                    identity=identity,
                )
            )
            continue
        if item_kind == _ITEM_KIND_OLD_VERIFIED_FACT:
            issues.append(
                _memory_snapshot_integrity_issue(
                    failure_kind=(
                        MemorySnapshotIntegrityFailureKind.UNSUPPORTED_ITEM_KIND
                    ),
                    message="old durable memory item kind verified_fact is not supported",
                    identity=identity,
                )
            )
            continue
        if item_kind not in allowed_kinds:
            issues.append(
                _memory_snapshot_integrity_issue(
                    failure_kind=(
                        MemorySnapshotIntegrityFailureKind.UNSUPPORTED_ITEM_KIND
                    ),
                    message=f"unsupported durable memory item kind: {item_kind}",
                    identity=identity,
                )
            )
    return tuple(issues)


def _memory_snapshot_integrity_issue(
    *,
    failure_kind: MemorySnapshotIntegrityFailureKind,
    message: str,
    identity: _MemorySnapshotIntegrityRowIdentity | None,
) -> MemorySnapshotIntegrityIssue:
    """构造 memory snapshot integrity issue。

    :param failure_kind: 损坏分类。
    :param message: operator 可读短错误摘要。
    :param identity: snapshot row identity；扫描级错误为 ``None``。
    :returns: integrity issue。
    """

    if identity is None:
        return MemorySnapshotIntegrityIssue(
            failure_kind=failure_kind,
            message=message,
            snapshot_id=None,
            session_id=None,
            consumer_id=None,
            policy_digest=None,
            checkpoint_event_sequence=None,
        )
    return MemorySnapshotIntegrityIssue(
        failure_kind=failure_kind,
        message=message,
        snapshot_id=identity.snapshot_id,
        session_id=identity.session_id,
        consumer_id=identity.consumer_id,
        policy_digest=identity.policy_digest,
        checkpoint_event_sequence=identity.checkpoint_event_sequence,
    )


def _validate_snapshot_item_kinds(
    transaction: HostTransaction, snapshot_id: str
) -> None:
    """校验 snapshot item rows 没有旧 kind 或未知 kind。

    :param transaction: Host durable transaction。
    :param snapshot_id: snapshot id。
    :returns: ``None``。
    :raises HostDurableError: 存在旧 ``verified_fact`` 或未知 item kind 时抛出。
    """

    allowed_kinds = {
        _ITEM_KIND_EVIDENCE_BACKED_FACT,
        _ITEM_KIND_SELECTED_RECENT_WINDOW,
        _ITEM_KIND_REFERENCE_CONTINUITY,
        _ITEM_KIND_ANSWER_ANCHOR,
        _ITEM_KIND_FORWARD_INTENT,
        _ITEM_KIND_SESSION_SUMMARY,
    }
    rows = transaction.fetchall(
        f"""
        SELECT item_kind
        FROM {TABLE_HOST_MEMORY_ITEMS}
        WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    )
    for row in rows:
        item_kind = _require_text(row.get("item_kind"), field_name="item_kind")
        if item_kind == _ITEM_KIND_OLD_VERIFIED_FACT:
            raise HostDurableError(
                "old durable memory item kind verified_fact is not supported"
            )
        if item_kind not in allowed_kinds:
            raise HostDurableError(f"unsupported durable memory item kind: {item_kind}")


def _diagnostic_row_from_host_row(row: HostRow) -> MemoryDiagnosticRow:
    """把 durable row 转换为 typed diagnostic row。

    :param row: Host durable row。
    :returns: typed diagnostic row。
    :raises HostDurableError: JSON 无法解析或字段类型不符合预期时抛出。
    """

    session_id = _require_text(row.get("session_id"), field_name="session_id")
    snapshot_id = _optional_text(row.get("snapshot_id"), field_name="snapshot_id")
    diagnostic_json = _require_text(
        row.get("diagnostic_json"), field_name="diagnostic_json"
    )
    recorded_at = _require_text(row.get("recorded_at"), field_name="recorded_at")
    diagnostic = _diagnostic_from_json_text(diagnostic_json)
    return MemoryDiagnosticRow(
        session_id=session_id,
        snapshot_id=snapshot_id,
        diagnostic=diagnostic,
        recorded_at=recorded_at,
    )


def _snapshot_from_json_text(value: str) -> ConversationMemorySnapshotVNext:
    """从 JSON 文本恢复 snapshot。

    :param value: snapshot JSON 文本。
    :returns: typed memory snapshot。
    :raises HostDurableError: JSON 解析或 shape 校验失败时抛出。
    """

    try:
        json_value = cast(JsonValue, json.loads(value))
        return conversation_memory_snapshot_from_json_value(json_value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HostDurableError("memory snapshot JSON is invalid") from exc


def _diagnostic_from_json_text(value: str) -> MemoryDiagnostic:
    """从 JSON 文本恢复 diagnostic。

    :param value: diagnostic JSON 文本。
    :returns: typed memory diagnostic。
    :raises HostDurableError: JSON 解析或 shape 校验失败时抛出。
    """

    try:
        json_value = cast(JsonValue, json.loads(value))
        return memory_diagnostic_from_json_value(json_value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HostDurableError("memory diagnostic JSON is invalid") from exc


def _validate_snapshot_digest(snapshot: ConversationMemorySnapshotVNext) -> None:
    """校验 snapshot digest 与 canonical content 匹配。

    :param snapshot: typed memory snapshot。
    :returns: ``None``。
    :raises HostDurableError: digest 不匹配时抛出。
    """

    expected = calculate_memory_snapshot_digest(snapshot)
    if snapshot.snapshot_digest != expected:
        raise HostDurableError("memory snapshot digest mismatch")


def _evidence_backed_fact_item_json_value(item: EvidenceBackedFactView) -> JsonValue:
    """生成 evidence-backed fact item table JSON。

    :param item: evidence-backed fact item。
    :returns: JSON 值。
    """

    return {
        "claim_text": item.claim_text,
        "evidence_refs": list(item.evidence_refs),
        "item_id": item.item_id,
        "size_units": item.size_units.units,
    }


def _selected_recent_item_json_value(item: SelectedRecentWindowItem) -> JsonValue:
    """生成 selected recent window item table JSON。

    :param item: selected recent window item。
    :returns: JSON 值。
    """

    return {
        "event_sequence": item.event_sequence,
        "item_id": item.item_id,
        "role": item.role.value,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
        "text": item.text,
    }


def _answer_anchor_item_json_value(item: AnswerAnchor) -> JsonValue:
    """生成 answer anchor item table JSON。

    :param item: answer anchor item。
    :returns: JSON 值。
    """

    return {
        "anchor_title": item.anchor_title,
        "item_id": item.item_id,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
    }


def _forward_intent_item_json_value(item: ForwardIntent) -> JsonValue:
    """生成 forward intent item table JSON。

    :param item: forward intent item。
    :returns: JSON 值。
    """

    return {
        "intent_type": item.intent_type.value,
        "item_id": item.item_id,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
        "status": item.status.value,
        "text": item.text,
    }


def _reference_continuity_item_json_value(
    item: ReferenceContinuityItem,
) -> JsonValue:
    """生成 reference continuity item table JSON。

    :param item: reference continuity item。
    :returns: JSON 值。
    """

    return {
        "item_id": item.item_id,
        "reason": item.reason.value,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
        "text": item.text,
    }
