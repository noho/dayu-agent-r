"""Host memory projection durable read/write primitive。

本模块只操作 memory projection-owned tables，并复用 projection checkpoint
primitive 保证 snapshot content 与 checkpoint 可由调用方放入同一个 Host
durable transaction 提交。它不启动 transaction，不读取或修改 Run /
Attempt / wait / dispatch 等治理真源。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable._validation import (
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
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationContinuityItem,
    ConversationMemorySnapshot,
    MemoryClaimStatus,
    MemoryDiagnostic,
    MemoryExcludedReason,
    MemoryIncludedReason,
    MemoryProjectionEvent,
    MemoryProducerKind,
    MemoryProjectionPolicy,
    EvidenceBackedFactView,
    WorkingAssumptionView,
    calculate_memory_snapshot_digest,
    conversation_memory_snapshot_from_json_value,
    conversation_memory_snapshot_to_json_value,
    digest_memory_projection_policy,
    memory_diagnostic_from_json_value,
    memory_diagnostic_to_json_value,
    project_conversation_memory_event,
)
from dayu.host.payload_resolution import (
    sqlite_payload_object,
)
from dayu.host.terminal_summary_payload import (
    PayloadSummaryTextPolicy,
    assistant_summary_from_payload,
)
from dayu.host.projection import (
    ProjectionApplyResult,
    ProjectionApplyStatus,
    ProjectionConsumerId,
    ProjectionEventClassFilter,
    ProjectionEventFilter,
    ProjectionEventView,
)
from dayu.host.durable.event_log import EventClass

_ZERO_CURSOR_SEQUENCE = 0
_ITEM_KIND_EVIDENCE_BACKED_FACT = "evidence_backed_fact"
_ITEM_KIND_WORKING_ASSUMPTION = "working_assumption"
_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_EVENT_TYPE_FILTER = (
    _EVENT_TYPE_USER_INPUT_ACCEPTED,
    _EVENT_TYPE_RUN_SUCCEEDED,
    _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    CONTEXT_COMPACTED,
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
        self._event_filter = ProjectionEventFilter(
            (
                ProjectionEventClassFilter(
                    event_class=EventClass.CANONICAL_FACT,
                    event_types=_EVENT_TYPE_FILTER,
                ),
            )
        )

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

    payload = _payload_with_terminal_summary(transaction, event)
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
        payload=payload,
    )


def _payload_with_terminal_summary(
    transaction: HostTransaction, event: ProjectionEventView
) -> Mapping[str, JsonValue]:
    """必要时把 terminal summary 摘要合并进 RUN_SUCCEEDED payload。

    :param transaction: Host transaction。
    :param event: projection runner event view。
    :returns: memory projection 消费的 payload。
    :raises HostDurableError: terminal summary descriptor 损坏时抛出。
    """

    if event.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
        return event.payload
    if (
        assistant_summary_from_payload(
            event.payload,
            text_policy=PayloadSummaryTextPolicy.STRICT_ALLOW_EMPTY,
        )
        is not None
    ):
        return event.payload
    terminal_summary_ref = _optional_str(
        event.payload, _PAYLOAD_FIELD_TERMINAL_SUMMARY_REF
    )
    terminal_summary_digest = _optional_str(
        event.payload, _PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST
    )
    if terminal_summary_ref is None or terminal_summary_digest is None:
        return event.payload
    terminal_summary = sqlite_payload_object(
        transaction,
        payload_ref=terminal_summary_ref,
        payload_digest=terminal_summary_digest,
        payload_label="terminal summary",
    )
    summary = assistant_summary_from_payload(
        terminal_summary,
        text_policy=PayloadSummaryTextPolicy.STRICT_ALLOW_EMPTY,
    )
    if summary is None:
        return event.payload
    merged: dict[str, JsonValue] = dict(event.payload)
    merged[_PAYLOAD_FIELD_CONTENT] = summary
    return merged


def _optional_str(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选字符串字段。

    :param payload: JSON payload mapping。
    :param field_name: 字段名。
    :returns: 字段缺失或为 ``None`` 时返回 ``None``。
    :raises HostDurableError: 字段存在但不是字符串时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HostDurableError(f"{field_name} must be string")
    return value


@dataclass(frozen=True, slots=True)
class MemorySnapshotRow:
    """Memory snapshot durable row。

    :param snapshot: typed memory snapshot。
    :param updated_at: row 最近更新时间。
    """

    snapshot: ConversationMemorySnapshot
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
    return _snapshot_row_from_host_row(row)


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
    return _snapshot_row_from_host_row(row)


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
    return _snapshot_row_from_host_row(row)


def write_memory_snapshot(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshot,
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
    snapshot: ConversationMemorySnapshot,
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
    transaction: HostTransaction, snapshot: ConversationMemorySnapshot
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
    for item in snapshot.evidence_backed_facts:
        _insert_evidence_backed_fact_item(transaction, snapshot, item)
    for item in snapshot.working_assumptions:
        _insert_working_assumption_item(transaction, snapshot, item)
    for item in snapshot.conversation_continuity.items:
        _insert_continuity_item(transaction, snapshot, item)


def _replace_snapshot_diagnostics(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshot,
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
    snapshot: ConversationMemorySnapshot,
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
        claim_status=item.claim_status,
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
    if item.evidence_anchor is not None and item.evidence_anchor.digest is not None:
        return item.evidence_anchor.digest
    return item.provenance.digest_ref


def _insert_working_assumption_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshot,
    item: WorkingAssumptionView,
) -> None:
    """插入 working assumption item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: working assumption item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_WORKING_ASSUMPTION,
        claim_status=item.claim_status,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        producer_kind=item.producer_kind,
        producer_name=item.producer_kind.value,
        payload_ref=None,
        payload_digest=None,
        item_json=canonical_json_dumps(_working_assumption_item_json_value(item)),
        included_reason=item.included_reason,
        excluded_reason=item.excluded_reason,
    )


def _insert_continuity_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshot,
    item: ConversationContinuityItem,
) -> None:
    """插入 continuity item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: continuity item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=item.item_kind.value,
        claim_status=item.claim_status,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        producer_kind=item.producer_kind,
        producer_name=item.producer_kind.value,
        payload_ref=item.payload_ref,
        payload_digest=item.payload_digest,
        item_json=canonical_json_dumps(_continuity_item_json_value(item)),
        included_reason=item.included_reason,
        excluded_reason=item.excluded_reason,
    )


def _insert_item(
    transaction: HostTransaction,
    *,
    snapshot: ConversationMemorySnapshot,
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


def _snapshot_row_from_host_row(row: HostRow) -> MemorySnapshotRow:
    """把 durable row 转换为 typed snapshot row。

    :param row: Host durable row。
    :returns: typed snapshot row。
    :raises HostDurableError: JSON 无法解析或 digest 不匹配时抛出。
    """

    snapshot_json = _require_text(row.get("snapshot_json"), field_name="snapshot_json")
    updated_at = _require_text(row.get("updated_at"), field_name="updated_at")
    snapshot = _snapshot_from_json_text(snapshot_json)
    _validate_snapshot_digest(snapshot)
    return MemorySnapshotRow(snapshot=snapshot, updated_at=updated_at)


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


def _snapshot_from_json_text(value: str) -> ConversationMemorySnapshot:
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


def _validate_snapshot_digest(snapshot: ConversationMemorySnapshot) -> None:
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
        "fact_summary": item.fact_summary,
        "item_id": item.item_id,
        "size_units": item.size_units.units,
    }


def _working_assumption_item_json_value(item: WorkingAssumptionView) -> JsonValue:
    """生成 working assumption item table JSON。

    :param item: working assumption item。
    :returns: JSON 值。
    """

    return {
        "assumption_summary": item.assumption_summary,
        "item_id": item.item_id,
        "size_units": item.size_units.units,
    }


def _continuity_item_json_value(item: ConversationContinuityItem) -> JsonValue:
    """生成 continuity item table JSON。

    :param item: continuity item。
    :returns: JSON 值。
    """

    return {
        "item_id": item.item_id,
        "item_kind": item.item_kind.value,
        "size_units": item.size_units.units,
        "summary_text": item.summary_text,
    }
