"""Host Outbox terminal projection durable helper。

本模块只维护 ``OutboxTerminalProjectionConsumer`` 的 projection-owned
terminal delivery queue 与 drain 幂等记录。Outbox 是 committed EventLog 的
派生 work queue，不是 Host truth，不记录 channel 投递成功，也不更新 Run /
Attempt 状态。
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
    require_text as _require_text,
)
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError, HostIdempotencyConflictError
from dayu.host.durable.projection import (
    read_projection_checkpoint,
    read_projection_failure,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.lifecycle_events import (
    PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES,
    event_type_values,
)

OUTBOX_TERMINAL_READ_MAX_LIMIT = 500
"""Outbox terminal read / drain 单次返回 item 数上限。"""

OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT = 1000
"""Outbox terminal read / drain 单次 seen terminal id 数量上限。"""

_MIN_EVENT_CURSOR = 0
_MIN_EVENT_SEQUENCE = 1
_MIN_LIMIT = 1
_EVENT_CLASS_CANONICAL_FACT = "canonical_fact"
_TERMINAL_STATUS_SUCCEEDED = "succeeded"
_TERMINAL_STATUS_FAILED = "failed"
_TERMINAL_STATUS_CANCELLED = "cancelled"
_ITEM_STATE_PENDING = "pending"
_ITEM_STATE_DRAINED = "drained"
_DIGEST_FIELD_SESSION_ID = "session_id"
_DIGEST_FIELD_AFTER_EVENT_SEQUENCE = "after_event_sequence"
_DIGEST_FIELD_SEEN_TERMINAL_EVENT_IDS = "seen_terminal_event_ids"
_DIGEST_FIELD_LIMIT = "limit"
_JSON_BATCH_ITEM_IDS = "batch_item_ids"

_TERMINAL_STATUSES = frozenset(
    (
        _TERMINAL_STATUS_SUCCEEDED,
        _TERMINAL_STATUS_FAILED,
        _TERMINAL_STATUS_CANCELLED,
    )
)
_ITEM_STATES = frozenset((_ITEM_STATE_PENDING, _ITEM_STATE_DRAINED))
_PUBLIC_TERMINAL_EVENT_TYPE_VALUES = event_type_values(
    PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES
)


class OutboxTerminalItemWriteStatus(StrEnum):
    """Outbox terminal item 写入结果。"""

    INSERTED = "inserted"
    DUPLICATE = "duplicate"


class OutboxTerminalProjectionStatus(StrEnum):
    """Outbox terminal projection 读取状态。"""

    CAUGHT_UP = "caught_up"
    LAGGED = "lagged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OutboxTerminalItemRow:
    """Outbox terminal delivery item row。

    :param item_id: Outbox item 主键。
    :param idempotency_key: terminal projection 幂等键。
    :param terminal_event_id: source terminal EventLog id。
    :param event_sequence: source terminal EventLog sequence。
    :param session_id: source Session id。
    :param run_id: source Run id。
    :param terminal_status: public terminal 状态文本。
    :param dedupe_key: 与 live HostEvent 对齐的去重键。
    :param final_answer_json: succeeded 必需的 final answer JSON 文本；其它终态为
        ``None``。
    :param error_message: 可选失败展示消息。
    :param cancel_reason: 可选取消原因。
    :param result_ref: 可选结果 payload 引用。
    :param result_digest: 可选结果 payload digest。
    :param terminal_summary_ref: 可选 terminal summary 引用。
    :param terminal_summary_digest: 可选 terminal summary digest。
    :param item_state: queue item 状态，只表达 outbox drain 状态。
    :param projected_at: 首次投影 UTC timestamp 文本。
    :param updated_at: 最近更新时间 UTC timestamp 文本。
    :param drained_at: 可选 drain UTC timestamp 文本。
    :param last_drain_request_id: 可选最近 drain request id。
    """

    item_id: str
    idempotency_key: str
    terminal_event_id: str
    event_sequence: int
    session_id: str
    run_id: str
    terminal_status: str
    dedupe_key: str
    final_answer_json: str | None
    error_message: str | None
    cancel_reason: str | None
    result_ref: str | None
    result_digest: str | None
    terminal_summary_ref: str | None
    terminal_summary_digest: str | None
    item_state: str
    projected_at: str
    updated_at: str
    drained_at: str | None
    last_drain_request_id: str | None


@dataclass(frozen=True, slots=True)
class OutboxTerminalItemsPage:
    """Outbox terminal item 分页结果。

    :param rows: 当前页返回 rows。
    :param next_event_sequence: 下一次读取推荐 cursor。
    :param scanned_watermark: 本次查询实际扫描到的最高 terminal sequence。
    :param has_more: scanned watermark 之后是否仍存在同 session terminal item。
    """

    rows: tuple[OutboxTerminalItemRow, ...]
    next_event_sequence: int
    scanned_watermark: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class OutboxTerminalProjectionCatchupError:
    """Outbox terminal projection catch-up 运行时失败摘要。

    :param error_code: catch-up 异常类型名。
    :param error_message: catch-up 异常消息。
    """

    error_code: str
    error_message: str


@dataclass(frozen=True, slots=True)
class OutboxTerminalProjectionReadState:
    """Outbox terminal projection checkpoint / failure 读取结果。

    :param checkpoint_event_sequence: projection 已确认消费的 EventLog sequence。
    :param status: projection 当前追平状态。
    :param error_code: 失败码；无失败时为 ``None``。
    :param error_message: 失败消息；无失败时为 ``None``。
    """

    checkpoint_event_sequence: int
    status: OutboxTerminalProjectionStatus
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class OutboxTerminalItemWriteResult:
    """Outbox terminal item 写入结果。

    :param status: 写入状态。
    :param row: 新写入或已存在的 item row。
    """

    status: OutboxTerminalItemWriteStatus
    row: OutboxTerminalItemRow


def read_outbox_terminal_item_by_event_id(
    transaction: HostTransaction, terminal_event_id: str
) -> OutboxTerminalItemRow | None:
    """按 source terminal EventLog id 读取 Outbox terminal item。

    :param transaction: 调用方提供的 Host durable transaction。
    :param terminal_event_id: source terminal EventLog id。
    :returns: 存在时返回 item row，否则返回 ``None``。
    :raises HostDurableError: 输入无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(terminal_event_id, field_name="terminal_event_id")
    row = transaction.fetchone(
        _OUTBOX_TERMINAL_ITEM_SELECT_SQL
        + f"""
        WHERE terminal_event_id = ?
        """,
        (terminal_event_id,),
    )
    if row is None:
        return None
    return _item_row_from_host_row(row)


def read_outbox_terminal_item_by_id(
    transaction: HostTransaction, item_id: str
) -> OutboxTerminalItemRow | None:
    """按 Outbox item id 读取 terminal item。

    :param transaction: 调用方提供的 Host durable transaction。
    :param item_id: Outbox item id。
    :returns: 存在时返回 item row，否则返回 ``None``。
    :raises HostDurableError: 输入无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(item_id, field_name="item_id")
    row = transaction.fetchone(
        _OUTBOX_TERMINAL_ITEM_SELECT_SQL
        + f"""
        WHERE item_id = ?
        """,
        (item_id,),
    )
    if row is None:
        return None
    return _item_row_from_host_row(row)


def insert_outbox_terminal_item_if_absent(
    transaction: HostTransaction, row: OutboxTerminalItemRow
) -> OutboxTerminalItemWriteResult:
    """写入 Outbox terminal item；同一 terminal event 重放返回 duplicate。

    :param transaction: 调用方提供的 Host durable transaction。
    :param row: 待写入 item row。
    :returns: 写入结果。
    :raises HostDurableError: 输入非法、既有 terminal identity 冲突或写入后无法读回时抛出。
    """

    _validate_item_row(row)
    existing = read_outbox_terminal_item_by_event_id(
        transaction, row.terminal_event_id
    )
    if existing is not None:
        if (
            existing.item_id == row.item_id
            and existing.idempotency_key == row.idempotency_key
            and existing.event_sequence == row.event_sequence
            and existing.run_id == row.run_id
        ):
            return OutboxTerminalItemWriteResult(
                status=OutboxTerminalItemWriteStatus.DUPLICATE,
                row=existing,
            )
        raise HostDurableError("outbox terminal item identity conflicts")
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_OUTBOX_TERMINAL_ITEMS} (
          item_id,
          idempotency_key,
          terminal_event_id,
          event_sequence,
          session_id,
          run_id,
          terminal_status,
          dedupe_key,
          final_answer_json,
          error_message,
          cancel_reason,
          result_ref,
          result_digest,
          terminal_summary_ref,
          terminal_summary_digest,
          item_state,
          projected_at,
          updated_at,
          drained_at,
          last_drain_request_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _item_row_parameters(row),
    )
    inserted = read_outbox_terminal_item_by_event_id(
        transaction, row.terminal_event_id
    )
    if inserted is None:
        raise HostDurableError("outbox terminal item write failed")
    return OutboxTerminalItemWriteResult(
        status=OutboxTerminalItemWriteStatus.INSERTED,
        row=inserted,
    )


def read_outbox_terminal_items_after(
    transaction: HostTransaction,
    session_id: str,
    *,
    after_event_sequence: int,
    seen_terminal_event_ids: tuple[str, ...],
    limit: int,
) -> OutboxTerminalItemsPage:
    """读取指定 Session cursor 之后的 Outbox terminal items。

    查询会按 ``event_sequence ASC`` 扫描，并按 ``seen_terminal_event_ids`` 过滤
    已由 live watch 展示过的 terminal event。``scanned_watermark`` 包含被
    seen 集合过滤掉的 rows，允许调用方保存 overlap watermark。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: Session id。
    :param after_event_sequence: 严格大于该 cursor 的 terminal sequence。
    :param seen_terminal_event_ids: 调用方已展示的 terminal event ids。
    :param limit: 返回 item 上限，必须为正数且不超过模块上限。
    :returns: Outbox terminal item 分页结果。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    seen_ids = _validate_page_input(
        session_id,
        after_event_sequence=after_event_sequence,
        seen_terminal_event_ids=seen_terminal_event_ids,
        limit=limit,
    )
    scan_limit = limit + len(seen_ids)
    candidate_rows = transaction.fetchall(
        _OUTBOX_TERMINAL_ITEM_SELECT_SQL
        + f"""
        WHERE session_id = ?
          AND event_sequence > ?
        ORDER BY event_sequence ASC
        LIMIT ?
        """,
        (session_id, after_event_sequence, scan_limit),
    )
    returned_rows: list[OutboxTerminalItemRow] = []
    scanned_watermark = after_event_sequence
    for candidate_row in candidate_rows:
        item = _item_row_from_host_row(candidate_row)
        scanned_watermark = item.event_sequence
        if item.terminal_event_id in seen_ids:
            continue
        returned_rows.append(item)
        if len(returned_rows) >= limit:
            break
    rows = tuple(returned_rows)
    has_more = _has_terminal_item_after(
        transaction,
        session_id=session_id,
        event_sequence=scanned_watermark,
    )
    return OutboxTerminalItemsPage(
        rows=rows,
        next_event_sequence=scanned_watermark,
        scanned_watermark=scanned_watermark,
        has_more=has_more,
    )


def read_outbox_terminal_projection_state(
    transaction: HostTransaction,
    consumer_id: str,
    *,
    catchup_error: OutboxTerminalProjectionCatchupError | None,
) -> OutboxTerminalProjectionReadState:
    """读取 Outbox terminal projection checkpoint / failure 状态。

    本 helper 是 public outbox read / drain API 访问 projection checkpoint 与
    failure row 的唯一 durable 入口。它只读取 projection-owned 状态与
    Outbox terminal canonical fact 最新水位，不读取或修改 Run / Attempt truth。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: Outbox terminal projection consumer id。
    :param catchup_error: 调用层捕获到的 catch-up 运行时失败摘要。
    :returns: Outbox terminal projection 状态。
    :raises HostDurableError: consumer id 无效或 durable row 类型非法时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    checkpoint = read_projection_checkpoint(transaction, consumer_id)
    checkpoint_event_sequence = (
        0 if checkpoint is None else checkpoint.checkpoint_event_sequence
    )
    if catchup_error is not None:
        return OutboxTerminalProjectionReadState(
            checkpoint_event_sequence=checkpoint_event_sequence,
            status=OutboxTerminalProjectionStatus.FAILED,
            error_code=catchup_error.error_code,
            error_message=catchup_error.error_message,
        )
    failure = read_projection_failure(transaction, consumer_id)
    if failure is not None:
        return OutboxTerminalProjectionReadState(
            checkpoint_event_sequence=checkpoint_event_sequence,
            status=OutboxTerminalProjectionStatus.FAILED,
            error_code=failure.last_error_code,
            error_message=failure.last_error_message,
        )
    if checkpoint_event_sequence < _latest_outbox_terminal_event_sequence(transaction):
        return OutboxTerminalProjectionReadState(
            checkpoint_event_sequence=checkpoint_event_sequence,
            status=OutboxTerminalProjectionStatus.LAGGED,
            error_code=None,
            error_message=None,
        )
    return OutboxTerminalProjectionReadState(
        checkpoint_event_sequence=checkpoint_event_sequence,
        status=OutboxTerminalProjectionStatus.CAUGHT_UP,
        error_code=None,
        error_message=None,
    )


def drain_outbox_terminal_items(
    transaction: HostTransaction,
    session_id: str,
    *,
    after_event_sequence: int,
    seen_terminal_event_ids: tuple[str, ...],
    limit: int,
    drain_request_id: str,
    drained_at: str,
) -> OutboxTerminalItemsPage:
    """幂等 drain 指定 Session 的 Outbox terminal items。

    首次调用按 read 语义选出 item 后仅更新 outbox projection queue state，并
    写入 ``(session_id, drain_request_id)`` 幂等记录。重复同一 request digest
    返回同一 item id 集合；同一 request id 携带不同语义输入时抛出幂等冲突。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: Session id。
    :param after_event_sequence: 严格大于该 cursor 的 terminal sequence。
    :param seen_terminal_event_ids: 调用方已展示的 terminal event ids。
    :param limit: 返回 item 上限。
    :param drain_request_id: drain 请求幂等 id。
    :param drained_at: 本次 drain UTC timestamp 文本。
    :returns: drain 的 Outbox terminal item 分页结果。
    :raises HostIdempotencyConflictError: request id 复用但 digest 不一致时抛出。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(drain_request_id, field_name="drain_request_id")
    _require_non_empty_text(drained_at, field_name="drained_at")
    seen_ids = _validate_page_input(
        session_id,
        after_event_sequence=after_event_sequence,
        seen_terminal_event_ids=seen_terminal_event_ids,
        limit=limit,
    )
    request_digest = _drain_request_digest(
        session_id=session_id,
        after_event_sequence=after_event_sequence,
        seen_terminal_event_ids=seen_ids,
        limit=limit,
    )
    existing = _read_drain_idempotency(
        transaction, session_id=session_id, drain_request_id=drain_request_id
    )
    if existing is not None:
        existing_digest, item_ids = existing
        if existing_digest != request_digest:
            raise HostIdempotencyConflictError(
                "outbox drain request idempotency conflict"
            )
        return _page_for_drained_item_ids(
            transaction,
            session_id=session_id,
            item_ids=item_ids,
            after_event_sequence=after_event_sequence,
        )
    page = read_outbox_terminal_items_after(
        transaction,
        session_id,
        after_event_sequence=after_event_sequence,
        seen_terminal_event_ids=seen_terminal_event_ids,
        limit=limit,
    )
    item_ids = tuple(row.item_id for row in page.rows)
    _insert_drain_idempotency(
        transaction,
        session_id=session_id,
        drain_request_id=drain_request_id,
        request_digest=request_digest,
        item_ids=item_ids,
        created_at=drained_at,
    )
    for item_id in item_ids:
        result = transaction.execute(
            f"""
            UPDATE {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
            SET item_state = ?,
                drained_at = ?,
                last_drain_request_id = ?,
                updated_at = ?
            WHERE item_id = ?
              AND item_state = ?
            """,
            (
                _ITEM_STATE_DRAINED,
                drained_at,
                drain_request_id,
                drained_at,
                item_id,
                _ITEM_STATE_PENDING,
            ),
        )
        if result.rowcount != 1:
            raise HostDurableError("outbox drain item pending CAS failed")
    return _page_for_drained_item_ids(
        transaction,
        session_id=session_id,
        item_ids=item_ids,
        after_event_sequence=page.scanned_watermark,
    )


def outbox_terminal_drain_request_digest(
    *,
    session_id: str,
    after_event_sequence: int,
    seen_terminal_event_ids: tuple[str, ...],
    limit: int,
) -> str:
    """计算 Outbox drain 请求语义 digest。

    :param session_id: Session id。
    :param after_event_sequence: terminal cursor。
    :param seen_terminal_event_ids: seen terminal event ids。
    :param limit: read / drain limit。
    :returns: Host 标准 sha256 digest。
    :raises HostDurableError: 输入非法时抛出。
    """

    seen_ids = _validate_page_input(
        session_id,
        after_event_sequence=after_event_sequence,
        seen_terminal_event_ids=seen_terminal_event_ids,
        limit=limit,
    )
    return _drain_request_digest(
        session_id=session_id,
        after_event_sequence=after_event_sequence,
        seen_terminal_event_ids=seen_ids,
        limit=limit,
    )


_OUTBOX_TERMINAL_ITEM_SELECT_SQL = f"""
SELECT
  item_id,
  idempotency_key,
  terminal_event_id,
  event_sequence,
  session_id,
  run_id,
  terminal_status,
  dedupe_key,
  final_answer_json,
  error_message,
  cancel_reason,
  result_ref,
  result_digest,
  terminal_summary_ref,
  terminal_summary_digest,
  item_state,
  projected_at,
  updated_at,
  drained_at,
  last_drain_request_id
FROM {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
"""


def _page_for_drained_item_ids(
    transaction: HostTransaction,
    *,
    session_id: str,
    item_ids: tuple[str, ...],
    after_event_sequence: int,
) -> OutboxTerminalItemsPage:
    """按 idempotency row 中的 item id 集合重建 drain page。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: Session id。
    :param item_ids: 首次 drain 返回的 item ids。
    :param after_event_sequence: 空结果时使用的 cursor。
    :returns: Outbox terminal item 分页结果。
    :raises HostDurableError: item row 缺失或 session identity 不一致时抛出。
    """

    rows: list[OutboxTerminalItemRow] = []
    for item_id in item_ids:
        row = read_outbox_terminal_item_by_id(transaction, item_id)
        if row is None:
            raise HostDurableError("outbox drained item row is missing")
        if row.session_id != session_id:
            raise HostDurableError("outbox drained item session conflicts")
        rows.append(row)
    page_rows = tuple(rows)
    scanned_watermark = (
        max(row.event_sequence for row in page_rows)
        if len(page_rows) > 0
        else after_event_sequence
    )
    return OutboxTerminalItemsPage(
        rows=page_rows,
        next_event_sequence=scanned_watermark,
        scanned_watermark=scanned_watermark,
        has_more=_has_terminal_item_after(
            transaction,
            session_id=session_id,
            event_sequence=scanned_watermark,
        ),
    )


def _read_drain_idempotency(
    transaction: HostTransaction,
    *,
    session_id: str,
    drain_request_id: str,
) -> tuple[str, tuple[str, ...]] | None:
    """读取 drain idempotency row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: Session id。
    :param drain_request_id: drain request id。
    :returns: 存在时返回 request digest 与 item ids，否则返回 ``None``。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT request_digest, batch_item_ids_json
        FROM {TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY}
        WHERE session_id = ?
          AND drain_request_id = ?
        """,
        (session_id, drain_request_id),
    )
    if row is None:
        return None
    return (
        _require_text(row.get("request_digest"), field_name="request_digest"),
        _batch_item_ids_from_json(
            _require_text(
                row.get("batch_item_ids_json"),
                field_name="batch_item_ids_json",
            )
        ),
    )


def _insert_drain_idempotency(
    transaction: HostTransaction,
    *,
    session_id: str,
    drain_request_id: str,
    request_digest: str,
    item_ids: tuple[str, ...],
    created_at: str,
) -> None:
    """写入 drain idempotency row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: Session id。
    :param drain_request_id: drain request id。
    :param request_digest: 请求语义 digest。
    :param item_ids: 首次 drain 返回 item ids。
    :param created_at: 写入时间。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY} (
          session_id,
          drain_request_id,
          request_digest,
          batch_item_ids_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            session_id,
            drain_request_id,
            request_digest,
            canonical_json_dumps({_JSON_BATCH_ITEM_IDS: list(item_ids)}),
            created_at,
        ),
    )


def _has_terminal_item_after(
    transaction: HostTransaction,
    *,
    session_id: str,
    event_sequence: int,
) -> bool:
    """判断指定 cursor 后是否仍存在同 Session item。

    :param transaction: 调用方提供的 Host durable transaction。
    :param session_id: Session id。
    :param event_sequence: terminal cursor。
    :returns: 存在后续 row 时返回 ``True``。
    """

    row = transaction.fetchone(
        f"""
        SELECT item_id
        FROM {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
        WHERE session_id = ?
          AND event_sequence > ?
        ORDER BY event_sequence ASC
        LIMIT 1
        """,
        (session_id, event_sequence),
    )
    return row is not None


def _latest_outbox_terminal_event_sequence(transaction: HostTransaction) -> int:
    """读取当前最新 Outbox terminal canonical fact 序号。

    :param transaction: 调用方提供的 Host durable transaction。
    :returns: 最新 terminal ``event_sequence``；无事件时为 ``0``。
    :raises HostDurableError: schema 中序号类型非法时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT COALESCE(MAX(event_sequence), 0) AS latest
        FROM {TABLE_EVENT_LOG}
        WHERE event_class = ?
          AND event_type IN (?, ?, ?)
        """,
        (_EVENT_CLASS_CANONICAL_FACT, *_PUBLIC_TERMINAL_EVENT_TYPE_VALUES),
    )
    if row is None:
        return 0
    latest = row.get("latest")
    if not isinstance(latest, int):
        raise HostDurableError("latest EventLog sequence is invalid")
    return latest


def _drain_request_digest(
    *,
    session_id: str,
    after_event_sequence: int,
    seen_terminal_event_ids: frozenset[str],
    limit: int,
) -> str:
    """按语义输入计算 drain request digest。

    :param session_id: Session id。
    :param after_event_sequence: cursor。
    :param seen_terminal_event_ids: 已校验 seen ids。
    :param limit: 返回上限。
    :returns: Host 标准 sha256 digest。
    """

    seen_ids_json: list[JsonValue] = list(sorted(seen_terminal_event_ids))
    digest_input: Mapping[str, JsonValue] = {
        _DIGEST_FIELD_SESSION_ID: session_id,
        _DIGEST_FIELD_AFTER_EVENT_SEQUENCE: after_event_sequence,
        _DIGEST_FIELD_SEEN_TERMINAL_EVENT_IDS: seen_ids_json,
        _DIGEST_FIELD_LIMIT: limit,
    }
    return sha256_digest_json(digest_input)


def _validate_page_input(
    session_id: str,
    *,
    after_event_sequence: int,
    seen_terminal_event_ids: tuple[str, ...],
    limit: int,
) -> frozenset[str]:
    """校验 read / drain page 输入。

    :param session_id: Session id。
    :param after_event_sequence: cursor。
    :param seen_terminal_event_ids: seen terminal event ids。
    :param limit: 返回上限。
    :returns: 去重后的 seen ids。
    :raises HostDurableError: 输入非法时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    if after_event_sequence < _MIN_EVENT_CURSOR:
        raise HostDurableError("outbox after_event_sequence is invalid")
    if limit < _MIN_LIMIT or limit > OUTBOX_TERMINAL_READ_MAX_LIMIT:
        raise HostDurableError("outbox terminal read limit is invalid")
    if len(seen_terminal_event_ids) > OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT:
        raise HostDurableError("outbox seen terminal ids exceed limit")
    seen: set[str] = set()
    for terminal_event_id in seen_terminal_event_ids:
        _require_non_empty_text(
            terminal_event_id,
            field_name="seen_terminal_event_ids",
        )
        if terminal_event_id in seen:
            raise HostDurableError("outbox seen terminal ids are duplicated")
        seen.add(terminal_event_id)
    return frozenset(seen)


def _validate_item_row(row: OutboxTerminalItemRow) -> None:
    """校验 Outbox terminal item row。

    :param row: 待校验 row。
    :returns: ``None``。
    :raises HostDurableError: 字段非法时抛出。
    """

    _require_non_empty_text(row.item_id, field_name="item_id")
    _require_non_empty_text(row.idempotency_key, field_name="idempotency_key")
    _require_non_empty_text(row.terminal_event_id, field_name="terminal_event_id")
    if row.event_sequence < _MIN_EVENT_SEQUENCE:
        raise HostDurableError("outbox event_sequence must be positive")
    _require_non_empty_text(row.session_id, field_name="session_id")
    _require_non_empty_text(row.run_id, field_name="run_id")
    if row.terminal_status not in _TERMINAL_STATUSES:
        raise HostDurableError("outbox terminal_status is invalid")
    _require_non_empty_text(row.dedupe_key, field_name="dedupe_key")
    if row.dedupe_key != row.terminal_event_id:
        raise HostDurableError("outbox dedupe_key must equal terminal_event_id")
    _require_optional_non_empty_text(row.final_answer_json, field_name="final_answer_json")
    if row.terminal_status == _TERMINAL_STATUS_SUCCEEDED:
        if row.final_answer_json is None:
            raise HostDurableError(
                "succeeded outbox item requires final_answer_json"
            )
    elif row.final_answer_json is not None:
        raise HostDurableError(
            "non-success outbox item must not carry final_answer_json"
        )
    _require_optional_non_empty_text(row.error_message, field_name="error_message")
    _require_optional_non_empty_text(row.cancel_reason, field_name="cancel_reason")
    _require_optional_non_empty_text(row.result_ref, field_name="result_ref")
    _require_optional_non_empty_text(row.result_digest, field_name="result_digest")
    _require_optional_non_empty_text(
        row.terminal_summary_ref,
        field_name="terminal_summary_ref",
    )
    _require_optional_non_empty_text(
        row.terminal_summary_digest,
        field_name="terminal_summary_digest",
    )
    if (row.result_ref is None) != (row.result_digest is None):
        raise HostDurableError("outbox result ref and digest must pair")
    if (row.terminal_summary_ref is None) != (row.terminal_summary_digest is None):
        raise HostDurableError("outbox summary ref and digest must pair")
    if row.item_state not in _ITEM_STATES:
        raise HostDurableError("outbox item_state is invalid")
    _require_non_empty_text(row.projected_at, field_name="projected_at")
    _require_non_empty_text(row.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(row.drained_at, field_name="drained_at")
    _require_optional_non_empty_text(
        row.last_drain_request_id,
        field_name="last_drain_request_id",
    )
    if row.item_state == _ITEM_STATE_PENDING:
        if row.drained_at is not None or row.last_drain_request_id is not None:
            raise HostDurableError("pending outbox item cannot carry drain marker")
    if row.item_state == _ITEM_STATE_DRAINED:
        if row.drained_at is None or row.last_drain_request_id is None:
            raise HostDurableError("drained outbox item requires drain marker")


def _item_row_parameters(row: OutboxTerminalItemRow) -> tuple[str | int | None, ...]:
    """把 item row 转换为 SQLite 参数。

    :param row: Outbox terminal item row。
    :returns: 参数元组。
    """

    return (
        row.item_id,
        row.idempotency_key,
        row.terminal_event_id,
        row.event_sequence,
        row.session_id,
        row.run_id,
        row.terminal_status,
        row.dedupe_key,
        row.final_answer_json,
        row.error_message,
        row.cancel_reason,
        row.result_ref,
        row.result_digest,
        row.terminal_summary_ref,
        row.terminal_summary_digest,
        row.item_state,
        row.projected_at,
        row.updated_at,
        row.drained_at,
        row.last_drain_request_id,
    )


def _item_row_from_host_row(row: HostRow) -> OutboxTerminalItemRow:
    """把通用 HostRow 转换为 OutboxTerminalItemRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: Outbox terminal item row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    item_row = OutboxTerminalItemRow(
        item_id=_require_text(row.get("item_id"), field_name="item_id"),
        idempotency_key=_require_text(
            row.get("idempotency_key"),
            field_name="idempotency_key",
        ),
        terminal_event_id=_require_text(
            row.get("terminal_event_id"),
            field_name="terminal_event_id",
        ),
        event_sequence=_require_int(
            row.get("event_sequence"),
            field_name="event_sequence",
        ),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        terminal_status=_require_text(
            row.get("terminal_status"),
            field_name="terminal_status",
        ),
        dedupe_key=_require_text(row.get("dedupe_key"), field_name="dedupe_key"),
        final_answer_json=_optional_text(
            row.get("final_answer_json"),
            field_name="final_answer_json",
        ),
        error_message=_optional_text(
            row.get("error_message"),
            field_name="error_message",
        ),
        cancel_reason=_optional_text(
            row.get("cancel_reason"),
            field_name="cancel_reason",
        ),
        result_ref=_optional_text(row.get("result_ref"), field_name="result_ref"),
        result_digest=_optional_text(
            row.get("result_digest"),
            field_name="result_digest",
        ),
        terminal_summary_ref=_optional_text(
            row.get("terminal_summary_ref"),
            field_name="terminal_summary_ref",
        ),
        terminal_summary_digest=_optional_text(
            row.get("terminal_summary_digest"),
            field_name="terminal_summary_digest",
        ),
        item_state=_require_text(row.get("item_state"), field_name="item_state"),
        projected_at=_require_text(row.get("projected_at"), field_name="projected_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        drained_at=_optional_text(row.get("drained_at"), field_name="drained_at"),
        last_drain_request_id=_optional_text(
            row.get("last_drain_request_id"),
            field_name="last_drain_request_id",
        ),
    )
    _validate_item_row(item_row)
    return item_row


def _batch_item_ids_from_json(value: str) -> tuple[str, ...]:
    """解析 drain idempotency 的 item id JSON。

    :param value: durable JSON 文本。
    :returns: item id 元组。
    :raises HostDurableError: JSON 非法或字段类型非法时抛出。
    """

    try:
        parsed = cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HostDurableError("outbox drain item ids JSON is invalid") from exc
    if not isinstance(parsed, dict):
        raise HostDurableError("outbox drain item ids JSON must be object")
    batch_value = parsed.get(_JSON_BATCH_ITEM_IDS)
    if not isinstance(batch_value, list):
        raise HostDurableError("outbox drain item ids must be list")
    item_ids: list[str] = []
    for item_id_value in batch_value:
        if not isinstance(item_id_value, str) or item_id_value.strip() == "":
            raise HostDurableError("outbox drain item id must be non-empty text")
        item_ids.append(item_id_value)
    return tuple(item_ids)


__all__ = [
    "OUTBOX_TERMINAL_READ_MAX_LIMIT",
    "OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT",
    "OutboxTerminalItemRow",
    "OutboxTerminalItemWriteResult",
    "OutboxTerminalItemWriteStatus",
    "OutboxTerminalItemsPage",
    "OutboxTerminalProjectionCatchupError",
    "OutboxTerminalProjectionReadState",
    "OutboxTerminalProjectionStatus",
    "drain_outbox_terminal_items",
    "insert_outbox_terminal_item_if_absent",
    "outbox_terminal_drain_request_digest",
    "read_outbox_terminal_projection_state",
    "read_outbox_terminal_item_by_event_id",
    "read_outbox_terminal_item_by_id",
    "read_outbox_terminal_items_after",
]
