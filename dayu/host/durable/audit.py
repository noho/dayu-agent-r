"""Host audit JSONL sink-local marker durable helper。

本模块只维护 ``LogAuditSink`` 的本地幂等 marker，用于避免普通 retry
重复写同一个 logical audit event。marker 不是 audit event store，不是
Host governance truth，也不提供 audit 查询能力。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dayu.host.durable._validation import (
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import TABLE_HOST_AUDIT_SINK_MARKERS
from dayu.host.durable.transaction import HostRow, HostTransaction


class AuditSinkMarkerWriteStatus(StrEnum):
    """audit sink-local marker 写入结果。"""

    INSERTED = "inserted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class AuditSinkMarkerRow:
    """audit sink-local marker row。

    :param event_id: 已写入 JSONL 的 EventLog id。
    :param event_sequence: 已写入 JSONL 的 EventLog sequence。
    :param line_digest: 已写入 JSONL 行的 canonical digest。
    :param written_at: marker 写入 UTC timestamp 文本。
    """

    event_id: str
    event_sequence: int
    line_digest: str
    written_at: str


@dataclass(frozen=True, slots=True)
class AuditSinkMarkerWriteResult:
    """audit sink-local marker 写入结果。

    :param status: marker 写入状态。
    :param row: 写入或已存在的 marker row。
    """

    status: AuditSinkMarkerWriteStatus
    row: AuditSinkMarkerRow


def read_audit_sink_marker(
    transaction: HostTransaction, event_id: str
) -> AuditSinkMarkerRow | None:
    """按 EventLog id 读取 audit sink-local marker。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_id: EventLog id。
    :returns: 存在时返回 marker row，否则返回 ``None``。
    :raises HostDurableError: ``event_id`` 无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(event_id, field_name="event_id")
    row = transaction.fetchone(
        f"""
        SELECT event_id, event_sequence, line_digest, written_at
        FROM {TABLE_HOST_AUDIT_SINK_MARKERS}
        WHERE event_id = ?
        """,
        (event_id,),
    )
    if row is None:
        return None
    return _marker_row_from_host_row(row)


def insert_audit_sink_marker_if_absent(
    transaction: HostTransaction,
    *,
    event_id: str,
    event_sequence: int,
    line_digest: str,
    written_at: str,
) -> AuditSinkMarkerWriteResult:
    """写入 audit sink-local marker；已存在时按 logical duplicate 处理。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_id: EventLog id。
    :param event_sequence: EventLog sequence。
    :param line_digest: audit JSONL 行 digest。
    :param written_at: marker 写入 UTC timestamp 文本。
    :returns: marker 写入结果。
    :raises HostDurableError: 输入无效、既有 marker digest 冲突或写入后无法读回时抛出。
    """

    _validate_marker_input(
        event_id=event_id,
        event_sequence=event_sequence,
        line_digest=line_digest,
        written_at=written_at,
    )
    existing = read_audit_sink_marker(transaction, event_id)
    if existing is not None:
        if (
            existing.event_sequence != event_sequence
            or existing.line_digest != line_digest
        ):
            raise HostDurableError("audit sink marker conflicts with audit line")
        return AuditSinkMarkerWriteResult(
            status=AuditSinkMarkerWriteStatus.DUPLICATE,
            row=existing,
        )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_AUDIT_SINK_MARKERS} (
          event_id,
          event_sequence,
          line_digest,
          written_at
        ) VALUES (?, ?, ?, ?)
        """,
        (event_id, event_sequence, line_digest, written_at),
    )
    inserted = read_audit_sink_marker(transaction, event_id)
    if inserted is None:
        raise HostDurableError("audit sink marker write failed")
    return AuditSinkMarkerWriteResult(
        status=AuditSinkMarkerWriteStatus.INSERTED,
        row=inserted,
    )


def _validate_marker_input(
    *,
    event_id: str,
    event_sequence: int,
    line_digest: str,
    written_at: str,
) -> None:
    """校验 audit marker 写入输入。

    :param event_id: EventLog id。
    :param event_sequence: EventLog sequence。
    :param line_digest: audit JSONL 行 digest。
    :param written_at: marker 写入 UTC timestamp 文本。
    :returns: ``None``。
    :raises HostDurableError: 输入无效时抛出。
    """

    _require_non_empty_text(event_id, field_name="event_id")
    _require_non_empty_text(line_digest, field_name="line_digest")
    _require_non_empty_text(written_at, field_name="written_at")
    if event_sequence <= 0:
        raise HostDurableError("audit sink marker event_sequence must be positive")


def _marker_row_from_host_row(row: HostRow) -> AuditSinkMarkerRow:
    """把通用 HostRow 转换为 AuditSinkMarkerRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: marker row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return AuditSinkMarkerRow(
        event_id=_require_text(row.get("event_id"), field_name="event_id"),
        event_sequence=_require_int(
            row.get("event_sequence"), field_name="event_sequence"
        ),
        line_digest=_require_text(row.get("line_digest"), field_name="line_digest"),
        written_at=_require_text(row.get("written_at"), field_name="written_at"),
    )


__all__ = [
    "AuditSinkMarkerRow",
    "AuditSinkMarkerWriteResult",
    "AuditSinkMarkerWriteStatus",
    "insert_audit_sink_marker_if_absent",
    "read_audit_sink_marker",
]
