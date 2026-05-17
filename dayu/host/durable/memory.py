"""Host memory projection durable read/write primitive。

本模块只操作 memory projection-owned tables，并复用 projection checkpoint
primitive 保证 snapshot content 与 checkpoint 可由调用方放入同一个 Host
durable transaction 提交。它不启动 transaction，不读取或修改 Run /
Attempt / wait / dispatch 等治理真源。
"""

from __future__ import annotations

import json
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
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.memory import (
    ConversationContinuityItem,
    ConversationMemorySnapshot,
    MemoryClaimStatus,
    MemoryDiagnostic,
    MemoryExcludedReason,
    MemoryIncludedReason,
    MemoryProducerKind,
    VerifiedFactView,
    WorkingAssumptionView,
    calculate_memory_snapshot_digest,
    conversation_memory_snapshot_from_json_value,
    conversation_memory_snapshot_to_json_value,
    memory_diagnostic_from_json_value,
    memory_diagnostic_to_json_value,
)

_ZERO_CURSOR_SEQUENCE = 0
_ITEM_KIND_VERIFIED_FACT = "verified_fact"
_ITEM_KIND_WORKING_ASSUMPTION = "working_assumption"


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
    for item in snapshot.verified_facts:
        _insert_verified_fact_item(transaction, snapshot, item)
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


def _insert_verified_fact_item(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshot,
    item: VerifiedFactView,
) -> None:
    """插入 verified fact item row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param snapshot: typed memory snapshot。
    :param item: verified fact item。
    :returns: ``None``。
    """

    _insert_item(
        transaction,
        snapshot=snapshot,
        item_id=item.item_id,
        item_kind=_ITEM_KIND_VERIFIED_FACT,
        claim_status=item.claim_status,
        event_id=item.provenance.event_id,
        event_sequence=item.provenance.event_sequence,
        producer_kind=item.provenance.producer_kind,
        producer_name=item.provenance.producer_name,
        payload_ref=item.provenance.payload_ref,
        payload_digest=item.provenance.digest_ref,
        item_json=canonical_json_dumps(_verified_fact_item_json_value(item)),
        included_reason=item.included_reason,
        excluded_reason=item.excluded_reason,
    )


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


def _verified_fact_item_json_value(item: VerifiedFactView) -> JsonValue:
    """生成 verified fact item table JSON。

    :param item: verified fact item。
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
