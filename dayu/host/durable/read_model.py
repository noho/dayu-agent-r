"""Host minimal read model durable store。

本模块只提供 Phase 8 minimal RunResult 与 Session timeline 投影表的
transaction-scoped row codec 与写入 primitive。它不启动事务、不读取 public
command facade，也不把 read model 作为 Host governance truth。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dayu.host.api import RunStatus
from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import (
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
)
from dayu.host.durable.state import is_terminal_run_status
from dayu.host.durable.transaction import HostRow, HostTransaction


class ReadModelWriteStatus(StrEnum):
    """minimal read model 写入结果状态。"""

    INSERTED = "inserted"
    DUPLICATE = "duplicate"


_TIMELINE_ITEM_KINDS = frozenset(("user_input", "run_lifecycle", "run_terminal"))


@dataclass(frozen=True, slots=True)
class RunResultRow:
    """minimal RunResult row。

    :param run_id: Run id。
    :param session_id: Session id。
    :param terminal_status: terminal Run status schema 文本。
    :param terminal_event_id: terminal canonical EventLog id。
    :param terminal_event_sequence: terminal canonical EventLog sequence。
    :param result_ref: 可选 terminal result payload 引用。
    :param result_digest: 可选 terminal result payload digest。
    :param summary_ref: 可选 terminal summary 引用。
    :param summary_digest: 可选 terminal summary digest。
    :param projected_at: 首次投影时间。
    :param updated_at: 最近更新时间。
    """

    run_id: str
    session_id: str
    terminal_status: str
    terminal_event_id: str
    terminal_event_sequence: int
    result_ref: str | None
    result_digest: str | None
    summary_ref: str | None
    summary_digest: str | None
    projected_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SessionTimelineItemRow:
    """minimal Session timeline item row。

    :param timeline_item_id: timeline item id，当前等于 source event id。
    :param session_id: Session id。
    :param run_id: 可选 Run id。
    :param event_id: source EventLog id。
    :param event_sequence: source EventLog sequence。
    :param item_kind: item 类型。
    :param event_type: source EventLog type。
    :param display_text: 可选用户展示文本；缺失时为 ``None``。
    :param payload_ref: 可选 payload descriptor 引用。
    :param payload_digest: 可选 payload digest。
    :param projected_at: 首次投影时间。
    """

    timeline_item_id: str
    session_id: str
    run_id: str | None
    event_id: str
    event_sequence: int
    item_kind: str
    event_type: str
    display_text: str | None
    payload_ref: str | None
    payload_digest: str | None
    projected_at: str


def read_run_result(
    transaction: HostTransaction, run_id: str
) -> RunResultRow | None:
    """按 Run id 读取 minimal RunResult row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: 目标 Run id。
    :returns: 存在时返回 RunResult row，否则返回 ``None``。
    :raises HostDurableError: 输入为空或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    row = transaction.fetchone(
        f"""
        SELECT
          run_id,
          session_id,
          terminal_status,
          terminal_event_id,
          terminal_event_sequence,
          result_ref,
          result_digest,
          summary_ref,
          summary_digest,
          projected_at,
          updated_at
        FROM {TABLE_HOST_RUN_RESULTS}
        WHERE run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        return None
    return _run_result_from_host_row(row)


def insert_run_result_if_absent(
    transaction: HostTransaction, row: RunResultRow
) -> ReadModelWriteStatus:
    """插入 minimal RunResult，重复 terminal event 返回 duplicate。

    该函数故意不使用 ``INSERT OR REPLACE`` 或会覆盖 terminal identity 的
    ``ON CONFLICT(run_id) DO UPDATE``；同一 Run 出现不同 terminal event 会被视为
    EventLog / projection 不变量破坏并抛出错误。

    :param transaction: 调用方提供的 Host durable transaction。
    :param row: 待写入 RunResult row。
    :returns: 插入或重复状态。
    :raises HostDurableError: 输入非法或既有 terminal identity 冲突时抛出。
    """

    _validate_run_result(row)
    existing = read_run_result(transaction, row.run_id)
    if existing is not None:
        if (
            existing.terminal_event_id == row.terminal_event_id
            and existing.terminal_event_sequence == row.terminal_event_sequence
        ):
            return ReadModelWriteStatus.DUPLICATE
        raise HostDurableError("RunResult terminal event identity conflicts")
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_RUN_RESULTS} (
          run_id,
          session_id,
          terminal_status,
          terminal_event_id,
          terminal_event_sequence,
          result_ref,
          result_digest,
          summary_ref,
          summary_digest,
          projected_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.run_id,
            row.session_id,
            row.terminal_status,
            row.terminal_event_id,
            row.terminal_event_sequence,
            row.result_ref,
            row.result_digest,
            row.summary_ref,
            row.summary_digest,
            row.projected_at,
            row.updated_at,
        ),
    )
    return ReadModelWriteStatus.INSERTED


def read_session_timeline_items(
    transaction: HostTransaction, session_id: str
) -> tuple[SessionTimelineItemRow, ...]:
    """读取指定 Session 的 minimal timeline items。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: 目标 Session id。
    :returns: 按 EventLog sequence 升序排列的 timeline items。
    :raises HostDurableError: 输入为空或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    rows = transaction.fetchall(
        f"""
        SELECT
          timeline_item_id,
          session_id,
          run_id,
          event_id,
          event_sequence,
          item_kind,
          event_type,
          display_text,
          payload_ref,
          payload_digest,
          projected_at
        FROM {TABLE_HOST_SESSION_TIMELINE_ITEMS}
        WHERE session_id = ?
        ORDER BY event_sequence ASC
        """,
        (session_id,),
    )
    return tuple(_timeline_item_from_host_row(row) for row in rows)


def insert_session_timeline_item_if_absent(
    transaction: HostTransaction, row: SessionTimelineItemRow
) -> ReadModelWriteStatus:
    """插入 minimal Session timeline item，重复 source event 返回 duplicate。

    :param transaction: 调用方提供的 Host durable transaction。
    :param row: 待写入 timeline item row。
    :returns: 插入或重复状态。
    :raises HostDurableError: 输入非法时抛出。
    """

    _validate_timeline_item(row)
    existing = transaction.fetchone(
        f"""
        SELECT timeline_item_id
        FROM {TABLE_HOST_SESSION_TIMELINE_ITEMS}
        WHERE timeline_item_id = ?
        """,
        (row.timeline_item_id,),
    )
    if existing is not None:
        return ReadModelWriteStatus.DUPLICATE
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSION_TIMELINE_ITEMS} (
          timeline_item_id,
          session_id,
          run_id,
          event_id,
          event_sequence,
          item_kind,
          event_type,
          display_text,
          payload_ref,
          payload_digest,
          projected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.timeline_item_id,
            row.session_id,
            row.run_id,
            row.event_id,
            row.event_sequence,
            row.item_kind,
            row.event_type,
            row.display_text,
            row.payload_ref,
            row.payload_digest,
            row.projected_at,
        ),
    )
    return ReadModelWriteStatus.INSERTED


def reset_minimal_read_model_projection(
    transaction: HostTransaction, *, consumer_id: str
) -> None:
    """清空 minimal read model rows 及其 projection cursor/failure。

    ``host_run_results`` 与 ``host_session_timeline_items`` 由固定
    ``host.minimal-read-model`` consumer 独占。repair 时允许清空这两张表，
    再从 committed EventLog replay 重建；它们不是 Host governance truth。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: minimal read model consumer id。
    :returns: ``None``。
    :raises HostDurableError: consumer id 为空时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    transaction.execute(f"DELETE FROM {TABLE_HOST_SESSION_TIMELINE_ITEMS}")
    transaction.execute(f"DELETE FROM {TABLE_HOST_RUN_RESULTS}")
    transaction.execute(
        f"DELETE FROM {TABLE_HOST_PROJECTION_FAILURES} WHERE consumer_id = ?",
        (consumer_id,),
    )
    transaction.execute(
        f"DELETE FROM {TABLE_HOST_PROJECTION_CHECKPOINTS} WHERE consumer_id = ?",
        (consumer_id,),
    )


def _validate_run_result(row: RunResultRow) -> None:
    """校验 RunResult row 输入。

    :param row: 待校验 RunResult row。
    :returns: ``None``。
    :raises HostDurableError: 字段非法时抛出。
    """

    _require_non_empty_text(row.run_id, field_name="run_id")
    _require_non_empty_text(row.session_id, field_name="session_id")
    _terminal_status_from_text(row.terminal_status)
    if row.terminal_event_sequence <= 0:
        raise HostDurableError("terminal_event_sequence must be positive")
    _require_non_empty_text(row.terminal_event_id, field_name="terminal_event_id")
    _require_non_empty_text(row.projected_at, field_name="projected_at")
    _require_non_empty_text(row.updated_at, field_name="updated_at")
    _validate_optional_pair(
        row.result_ref,
        row.result_digest,
        ref_name="result_ref",
        digest_name="result_digest",
    )
    _validate_optional_pair(
        row.summary_ref,
        row.summary_digest,
        ref_name="summary_ref",
        digest_name="summary_digest",
    )


def _validate_timeline_item(row: SessionTimelineItemRow) -> None:
    """校验 Session timeline item 输入。

    :param row: 待校验 timeline item row。
    :returns: ``None``。
    :raises HostDurableError: 字段非法时抛出。
    """

    _require_non_empty_text(row.timeline_item_id, field_name="timeline_item_id")
    _require_non_empty_text(row.session_id, field_name="session_id")
    _require_optional_non_empty_text(row.run_id, field_name="run_id")
    _require_non_empty_text(row.event_id, field_name="event_id")
    if row.event_sequence <= 0:
        raise HostDurableError("event_sequence must be positive")
    _validate_timeline_item_kind(row.item_kind)
    _require_non_empty_text(row.event_type, field_name="event_type")
    _require_optional_non_empty_text(row.display_text, field_name="display_text")
    _require_non_empty_text(row.projected_at, field_name="projected_at")
    _validate_optional_pair(
        row.payload_ref,
        row.payload_digest,
        ref_name="payload_ref",
        digest_name="payload_digest",
    )


def _validate_optional_pair(
    ref_value: str | None,
    digest_value: str | None,
    *,
    ref_name: str,
    digest_name: str,
) -> None:
    """校验引用 / digest 成对出现。

    :param ref_value: 可选引用。
    :param digest_value: 可选 digest。
    :param ref_name: 引用字段名。
    :param digest_name: digest 字段名。
    :returns: ``None``。
    :raises HostDurableError: 只有单边存在或字段为空时抛出。
    """

    _require_optional_non_empty_text(ref_value, field_name=ref_name)
    _require_optional_non_empty_text(digest_value, field_name=digest_name)
    if (ref_value is None) != (digest_value is None):
        raise HostDurableError(f"{ref_name} and {digest_name} must appear together")


def _run_result_from_host_row(row: HostRow) -> RunResultRow:
    """把通用 HostRow 转换为 RunResultRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: RunResult row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return RunResultRow(
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        terminal_status=_terminal_status_from_text(
            _require_text(row.get("terminal_status"), field_name="terminal_status")
        ).value,
        terminal_event_id=_require_text(
            row.get("terminal_event_id"), field_name="terminal_event_id"
        ),
        terminal_event_sequence=_require_int(
            row.get("terminal_event_sequence"), field_name="terminal_event_sequence"
        ),
        result_ref=_optional_text(row.get("result_ref"), field_name="result_ref"),
        result_digest=_optional_text(
            row.get("result_digest"), field_name="result_digest"
        ),
        summary_ref=_optional_text(row.get("summary_ref"), field_name="summary_ref"),
        summary_digest=_optional_text(
            row.get("summary_digest"), field_name="summary_digest"
        ),
        projected_at=_require_text(row.get("projected_at"), field_name="projected_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
    )


def _timeline_item_from_host_row(row: HostRow) -> SessionTimelineItemRow:
    """把通用 HostRow 转换为 SessionTimelineItemRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: timeline item row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return SessionTimelineItemRow(
        timeline_item_id=_require_text(
            row.get("timeline_item_id"), field_name="timeline_item_id"
        ),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        run_id=_optional_text(row.get("run_id"), field_name="run_id"),
        event_id=_require_text(row.get("event_id"), field_name="event_id"),
        event_sequence=_require_int(row.get("event_sequence"), field_name="event_sequence"),
        item_kind=_validated_timeline_item_kind_text(
            _require_text(row.get("item_kind"), field_name="item_kind")
        ),
        event_type=_require_text(row.get("event_type"), field_name="event_type"),
        display_text=_optional_text(row.get("display_text"), field_name="display_text"),
        payload_ref=_optional_text(row.get("payload_ref"), field_name="payload_ref"),
        payload_digest=_optional_text(
            row.get("payload_digest"), field_name="payload_digest"
        ),
        projected_at=_require_text(row.get("projected_at"), field_name="projected_at"),
    )


def _terminal_status_from_text(value: str) -> RunStatus:
    """把 minimal RunResult terminal_status 文本映射为当前 RunStatus。

    :param value: RunResult row 中的 terminal status 文本。
    :returns: 当前 public RunStatus 终态成员。
    :raises HostDurableError: 文本为空、不是 RunStatus 或不是终态时抛出。
    """

    _require_non_empty_text(value, field_name="terminal_status")
    try:
        status = RunStatus(value)
    except ValueError as exc:
        raise HostDurableError("RunResult terminal_status is invalid") from exc
    if not is_terminal_run_status(status):
        raise HostDurableError("RunResult terminal_status is not terminal")
    return status


def _validate_timeline_item_kind(value: str) -> None:
    """校验 minimal timeline item kind 属于当前封闭集合。

    :param value: timeline item kind 文本。
    :returns: ``None``。
    :raises HostDurableError: 文本为空或不属于当前集合时抛出。
    """

    _validated_timeline_item_kind_text(value)


def _validated_timeline_item_kind_text(value: str) -> str:
    """返回已校验的 minimal timeline item kind 文本。

    :param value: timeline item kind 文本。
    :returns: 原始文本。
    :raises HostDurableError: 文本为空或不属于当前集合时抛出。
    """

    _require_non_empty_text(value, field_name="item_kind")
    if value not in _TIMELINE_ITEM_KINDS:
        raise HostDurableError("SessionTimeline item_kind is invalid")
    return value
