"""Compaction operation 唯一 terminal commit 的事务内 owner。

本模块只理解 ``CONTEXT_COMPACTION_REQUESTED`` 与两类 terminal canonical
fact。调用方必须在计划写入 terminal 的同一 write transaction 内取得 permit；
permit 不可跨 transaction 或 ``await`` 保存。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host._event_payload import payload_object
from dayu.host.context_event_payload import resolve_context_compacted_payload
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    validate_context_compaction_failed_payload,
    validate_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, EventLogStore
from dayu.host.durable.transaction import HostTransaction

_READ_PAGE_SIZE = 64
_TERMINAL_EVENT_TYPES = (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_FAILED,
)
COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR = (
    "compaction operation has multiple canonical terminals"
)


class CompactionOperationTerminalDisposition(StrEnum):
    """单个 compaction operation 的封闭 terminal disposition。"""

    OPEN = "open"
    COMPACTED = "compacted"
    FAILED = "failed"
    INVALID_MULTIPLE = "invalid_multiple"


@dataclass(frozen=True, slots=True)
class CompactionTerminalCommitPermit:
    """允许当前 transaction 提交唯一 terminal 的 typed permit。

    :param operation_id: 已严格验证的 compaction operation id。
    :param trigger_source: request 中已严格验证的 trigger source。
    :param request_event_sequence: request canonical event sequence。
    """

    operation_id: str
    trigger_source: ContextCompactionTriggerSource
    request_event_sequence: int


@dataclass(frozen=True, slots=True)
class CompactionTerminalClosed:
    """operation 已关闭或历史含多个 terminal 的 typed 结果。

    :param operation_id: 已严格验证的 compaction operation id。
    :param trigger_source: request 中已严格验证的 trigger source。
    :param request_event_sequence: request canonical event sequence。
    :param disposition: ``COMPACTED``、``FAILED`` 或 ``INVALID_MULTIPLE``。
    :param first_terminal_event_sequence: 首个 terminal canonical sequence。
    :param first_terminal_event_type: 首个 terminal canonical event type。
    """

    operation_id: str
    trigger_source: ContextCompactionTriggerSource
    request_event_sequence: int
    disposition: CompactionOperationTerminalDisposition
    first_terminal_event_sequence: int
    first_terminal_event_type: str

    def __post_init__(self) -> None:
        """校验 closed 结果不携带 ``OPEN`` disposition。

        :returns: ``None``。
        :raises ValueError: disposition 或首个 terminal type 非法时抛出。
        """

        if self.disposition not in (
            CompactionOperationTerminalDisposition.COMPACTED,
            CompactionOperationTerminalDisposition.FAILED,
            CompactionOperationTerminalDisposition.INVALID_MULTIPLE,
        ):
            raise ValueError("closed compaction terminal disposition is invalid")
        if self.first_terminal_event_type not in _TERMINAL_EVENT_TYPES:
            raise ValueError("first compaction terminal event type is invalid")


def begin_compaction_terminal_commit_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    operation_id: str,
    expected_trigger_source: ContextCompactionTriggerSource,
) -> CompactionTerminalCommitPermit | CompactionTerminalClosed:
    """在当前 write transaction 内判定 operation terminal commit 资格。

    ``operation_id`` 同时是 request event id。函数严格校验 request payload、
    trigger 与同一 operation 的全部 terminal payload，并把 transaction 内 fresh
    read 作为唯一线性化点。

    :param transaction: 即将写 terminal 的当前 Host write transaction。
    :param event_log_store: EventLog strict 读取 primitive。
    :param operation_id: request event id 同源的 operation id。
    :param expected_trigger_source: 当前 writer 唯一允许的 trigger source。
    :returns: operation 尚开放时返回 permit，否则返回 closed typed 结果。
    :raises TypeError: trigger source 类型非法时抛出。
    :raises ValueError: operation id 为空时抛出。
    :raises HostDurableError: request/terminal canonical fact 损坏、缺失或 trigger
        不匹配时 fail closed。
    """

    if operation_id.strip() == "":
        raise ValueError("operation_id must be non-empty")
    if not isinstance(expected_trigger_source, ContextCompactionTriggerSource):
        raise TypeError(
            "expected_trigger_source must be ContextCompactionTriggerSource"
        )
    request = event_log_store.read_event_by_id(transaction, operation_id)
    if request is None:
        raise HostDurableError("compaction terminal owner request is missing")
    if (
        request.event_class is not EventClass.CANONICAL_FACT
        or request.event_type != CONTEXT_COMPACTION_REQUESTED
        or request.event_id != operation_id
        or request.run_id is None
        or request.run_id.strip() == ""
    ):
        raise HostDurableError("compaction terminal owner request identity is invalid")
    request_payload = _strict_request_payload(request)
    if _required_text(request_payload, "operation_id") != operation_id:
        raise HostDurableError("compaction request operation id does not match event id")
    try:
        trigger_source = ContextCompactionTriggerSource(
            _required_text(request_payload, "trigger_source")
        )
    except ValueError as exc:
        raise HostDurableError("compaction request trigger source is invalid") from exc
    if trigger_source is not expected_trigger_source:
        raise HostDurableError("compaction request trigger source does not match writer")

    terminal_rows = _read_operation_terminal_rows(
        transaction,
        event_log_store,
        request=request,
        operation_id=operation_id,
    )
    if len(terminal_rows) == 0:
        return CompactionTerminalCommitPermit(
            operation_id=operation_id,
            trigger_source=trigger_source,
            request_event_sequence=request.event_sequence,
        )
    first = terminal_rows[0]
    if len(terminal_rows) > 1:
        disposition = CompactionOperationTerminalDisposition.INVALID_MULTIPLE
    elif first.event_type == CONTEXT_COMPACTED:
        disposition = CompactionOperationTerminalDisposition.COMPACTED
    else:
        disposition = CompactionOperationTerminalDisposition.FAILED
    return CompactionTerminalClosed(
        operation_id=operation_id,
        trigger_source=trigger_source,
        request_event_sequence=request.event_sequence,
        disposition=disposition,
        first_terminal_event_sequence=first.event_sequence,
        first_terminal_event_type=first.event_type,
    )


def _read_operation_terminal_rows(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    request: EventLogRow,
    operation_id: str,
) -> tuple[EventLogRow, ...]:
    """读取并严格校验目标 operation 的 terminal rows。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog strict 读取 primitive。
    :param request: 已验证 request row。
    :param operation_id: 已验证 operation id。
    :returns: 目标 operation 的 terminal rows，按 sequence 升序排列。
    :raises HostDurableError: terminal payload 或 canonical identity 损坏时抛出。
    """

    run_id = request.run_id
    if run_id is None:
        raise HostDurableError("compaction request run id is missing")
    cursor = 0
    matching: list[EventLogRow] = []
    while True:
        page = event_log_store.read_run_events_by_types_page(
            transaction,
            run_id=run_id,
            event_types=_TERMINAL_EVENT_TYPES,
            after_event_sequence=cursor,
            limit=_READ_PAGE_SIZE,
        )
        for row in page:
            if row.event_class is not EventClass.CANONICAL_FACT:
                raise HostDurableError(
                    "compaction terminal event class is not canonical fact"
                )
            payload = _strict_terminal_payload(transaction, row)
            row_operation_id = _required_text(payload, "operation_id")
            if row_operation_id != operation_id:
                continue
            if (
                row.session_id != request.session_id
                or row.run_id != run_id
                or row.event_sequence <= request.event_sequence
            ):
                raise HostDurableError(
                    "compaction terminal canonical identity is invalid"
                )
            matching.append(row)
        if len(page) < _READ_PAGE_SIZE:
            return tuple(matching)
        cursor = page[-1].event_sequence


def _strict_request_payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析并严格校验 request inline payload。

    :param row: request EventLog row。
    :returns: 已严格校验的 request payload。
    :raises HostDurableError: payload 不是合法 request contract 时抛出。
    """

    try:
        payload = payload_object(row)
        validate_context_compaction_requested_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("compaction request payload is invalid") from exc
    return payload


def _strict_terminal_payload(
    transaction: HostTransaction,
    row: EventLogRow,
) -> Mapping[str, JsonValue]:
    """解析并严格校验 compacted/failed terminal payload。

    :param transaction: 当前 Host transaction。
    :param row: terminal EventLog row。
    :returns: 已严格校验的 terminal payload。
    :raises HostDurableError: event type 或 payload contract 非法时抛出。
    """

    try:
        if row.event_type == CONTEXT_COMPACTED:
            return resolve_context_compacted_payload(transaction, row)
        elif row.event_type == CONTEXT_COMPACTION_FAILED:
            payload = payload_object(row)
            validate_context_compaction_failed_payload(payload)
        else:
            raise ValueError("unsupported compaction terminal event type")
    except (TypeError, ValueError) as exc:
        raise HostDurableError("compaction terminal payload is invalid") from exc
    return payload


def _required_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取严格非空文本字段。

    :param payload: 已解析 JSON object。
    :param field_name: 必填字段名。
    :returns: 非空文本字段值。
    :raises HostDurableError: 字段缺失、类型错误或为空时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return value


__all__ = [
    "COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR",
    "CompactionOperationTerminalDisposition",
    "CompactionTerminalClosed",
    "CompactionTerminalCommitPermit",
    "begin_compaction_terminal_commit_in_transaction",
]
