"""Host Tool Trace hot projection durable helper。

本模块只维护 ``ToolTraceProjectionConsumer`` 的 hot JSON projection 行与内部
诊断查询。Tool Trace 是 committed EventLog 的派生 projection，不是 Host
恢复、resume、memory 或 Run 状态迁移真源。
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
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import TABLE_HOST_TOOL_TRACE_HOT
from dayu.host.durable.transaction import HostRow, HostTransaction, SQLiteScalar

TOOL_TRACE_QUERY_MAX_LIMIT = 500
"""Tool Trace 内部查询单页最大行数。"""

_MIN_QUERY_LIMIT = 1
_MIN_EVENT_CURSOR = 0
_JSON_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"


class ToolTraceHotRowWriteStatus(StrEnum):
    """Tool Trace hot row 写入结果。"""

    INSERTED = "inserted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class ToolTraceHotRow:
    """Tool Trace hot projection row。

    :param trace_id: projection row 主键，当前等于 source ``event_id``。
    :param event_id: source EventLog id。
    :param event_sequence: source EventLog sequence。
    :param event_type: source EventLog event type。
    :param event_class: source EventLog event class。
    :param session_id: source Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param tool_call_id: 可选工具调用 id。
    :param tool_name: 可选工具名。
    :param provider_request_id: 可选 provider request id。
    :param diagnostic_ref: 可选主诊断 ref。
    :param normalized_arguments_digest: 可选 normalized arguments digest。
    :param semantic_input_digest: 可选 semantic input digest。
    :param result_digest: 可选结果 digest。
    :param payload_ref: 可选 source payload ref。
    :param payload_digest: 可选 source payload digest。
    :param policy_decision_json: 可选 policy decision canonical JSON 文本。
    :param trace_summary: hot summary JSON object。
    :param cold_trace_ref: 可选 cold JSONL line ref。
    :param cold_trace_digest: 可选 cold JSONL line digest。
    :param projected_at: 投影写入 UTC timestamp 文本。
    :param updated_at: 投影更新时间 UTC timestamp 文本。
    """

    trace_id: str
    event_id: str
    event_sequence: int
    event_type: str
    event_class: str
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    tool_call_id: str | None
    tool_name: str | None
    provider_request_id: str | None
    diagnostic_ref: str | None
    normalized_arguments_digest: str | None
    semantic_input_digest: str | None
    result_digest: str | None
    payload_ref: str | None
    payload_digest: str | None
    policy_decision_json: str | None
    trace_summary: Mapping[str, JsonValue]
    cold_trace_ref: str | None
    cold_trace_digest: str | None
    projected_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ToolTraceHotRowWriteResult:
    """Tool Trace hot row 写入结果。

    :param status: 写入状态。
    :param row: 新写入或已存在的 hot row。
    """

    status: ToolTraceHotRowWriteStatus
    row: ToolTraceHotRow


@dataclass(frozen=True, slots=True)
class ToolTraceQueryPage:
    """Tool Trace 内部查询分页结果。

    :param rows: 当前页 hot rows。
    :param next_event_sequence: 下一次查询可使用的 event sequence cursor。
    :param has_more: 是否存在下一页。
    """

    rows: tuple[ToolTraceHotRow, ...]
    next_event_sequence: int
    has_more: bool


def read_tool_trace_hot_row(
    transaction: HostTransaction, event_id: str
) -> ToolTraceHotRow | None:
    """按 source EventLog id 读取 Tool Trace hot row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_id: source EventLog id。
    :returns: 存在时返回 hot row，否则返回 ``None``。
    :raises HostDurableError: ``event_id`` 无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(event_id, field_name="event_id")
    row = transaction.fetchone(
        f"""
        SELECT
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        FROM {TABLE_HOST_TOOL_TRACE_HOT}
        WHERE event_id = ?
        """,
        (event_id,),
    )
    if row is None:
        return None
    return _hot_row_from_host_row(row)


def insert_tool_trace_hot_row_if_absent(
    transaction: HostTransaction, row: ToolTraceHotRow
) -> ToolTraceHotRowWriteResult:
    """写入 Tool Trace hot row；已存在时按 EventLog logical duplicate 处理。

    :param transaction: 调用方提供的 Host durable transaction。
    :param row: 待写入 hot row。
    :returns: 写入结果。
    :raises HostDurableError: 输入无效、既有 row 与 source identity 冲突或写入后无法读回时抛出。
    """

    _validate_hot_row(row)
    existing = read_tool_trace_hot_row(transaction, row.event_id)
    if existing is not None:
        if existing.event_sequence != row.event_sequence:
            raise HostDurableError("tool trace hot row conflicts with EventLog row")
        return ToolTraceHotRowWriteResult(
            status=ToolTraceHotRowWriteStatus.DUPLICATE,
            row=existing,
        )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_TOOL_TRACE_HOT} (
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.trace_id,
            row.event_id,
            row.event_sequence,
            row.event_type,
            row.event_class,
            row.session_id,
            row.run_id,
            row.attempt_id,
            row.execution_id,
            row.tool_call_id,
            row.tool_name,
            row.provider_request_id,
            row.diagnostic_ref,
            row.normalized_arguments_digest,
            row.semantic_input_digest,
            row.result_digest,
            row.payload_ref,
            row.payload_digest,
            row.policy_decision_json,
            canonical_json_dumps(row.trace_summary),
            row.cold_trace_ref,
            row.cold_trace_digest,
            row.projected_at,
            row.updated_at,
        ),
    )
    inserted = read_tool_trace_hot_row(transaction, row.event_id)
    if inserted is None:
        raise HostDurableError("tool trace hot row write failed")
    return ToolTraceHotRowWriteResult(
        status=ToolTraceHotRowWriteStatus.INSERTED,
        row=inserted,
    )


def read_tool_trace_by_run(
    transaction: HostTransaction,
    run_id: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 Run id 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: Run id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    return _query_page(
        transaction,
        where_sql="run_id = ?",
        parameters=(run_id,),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def find_tool_trace_by_tool_call_id(
    transaction: HostTransaction,
    tool_call_id: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 tool call id 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param tool_call_id: 工具调用 id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(tool_call_id, field_name="tool_call_id")
    return _query_page(
        transaction,
        where_sql="tool_call_id = ?",
        parameters=(tool_call_id,),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def find_tool_trace_by_provider_request_id(
    transaction: HostTransaction,
    provider_request_id: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 provider request id 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param provider_request_id: provider request id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(provider_request_id, field_name="provider_request_id")
    return _query_page(
        transaction,
        where_sql="provider_request_id = ?",
        parameters=(provider_request_id,),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def find_tool_trace_by_diagnostic_ref(
    transaction: HostTransaction,
    diagnostic_ref: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 diagnostic ref 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param diagnostic_ref: 诊断引用。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(diagnostic_ref, field_name="diagnostic_ref")
    return _query_page(
        transaction,
        where_sql=(
            "diagnostic_ref = ? OR EXISTS ("
            "SELECT 1 FROM json_each(trace_summary_json, '$."
            + _JSON_FIELD_DIAGNOSTIC_REFS
            + "') WHERE json_each.value = ?)"
        ),
        parameters=(diagnostic_ref, diagnostic_ref),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def _query_page(
    transaction: HostTransaction,
    *,
    where_sql: str,
    parameters: tuple[SQLiteScalar, ...],
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """执行 Tool Trace hot row 分页查询。

    :param transaction: 调用方提供的 Host durable transaction。
    :param where_sql: 不含 cursor 的 SQL WHERE 条件。
    :param parameters: WHERE 条件参数。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限。
    :returns: 查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _validate_query_page_input(after_event_sequence, limit)
    fetch_limit = limit + 1
    rows = transaction.fetchall(
        f"""
        SELECT
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        FROM {TABLE_HOST_TOOL_TRACE_HOT}
        WHERE event_sequence > ?
          AND ({where_sql})
        ORDER BY event_sequence ASC
        LIMIT ?
        """,
        (after_event_sequence, *parameters, fetch_limit),
    )
    page_rows = tuple(_hot_row_from_host_row(row) for row in rows[:limit])
    next_event_sequence = (
        page_rows[-1].event_sequence
        if len(page_rows) > 0
        else after_event_sequence
    )
    return ToolTraceQueryPage(
        rows=page_rows,
        next_event_sequence=next_event_sequence,
        has_more=len(rows) > limit,
    )


def _validate_query_page_input(after_event_sequence: int, limit: int) -> None:
    """校验 Tool Trace 查询分页输入。

    :param after_event_sequence: EventLog cursor。
    :param limit: 返回行数上限。
    :returns: ``None``。
    :raises HostDurableError: cursor 或 limit 非法时抛出。
    """

    if after_event_sequence < _MIN_EVENT_CURSOR:
        raise HostDurableError("tool trace after_event_sequence is invalid")
    if limit < _MIN_QUERY_LIMIT or limit > TOOL_TRACE_QUERY_MAX_LIMIT:
        raise HostDurableError("tool trace query limit is invalid")


def _validate_hot_row(row: ToolTraceHotRow) -> None:
    """校验 Tool Trace hot row 写入输入。

    :param row: 待写入 hot row。
    :returns: ``None``。
    :raises HostDurableError: row 字段非法时抛出。
    """

    _require_non_empty_text(row.trace_id, field_name="trace_id")
    _require_non_empty_text(row.event_id, field_name="event_id")
    if row.event_sequence <= _MIN_EVENT_CURSOR:
        raise HostDurableError("tool trace event_sequence must be positive")
    _require_non_empty_text(row.event_type, field_name="event_type")
    _require_non_empty_text(row.event_class, field_name="event_class")
    _require_non_empty_text(row.session_id, field_name="session_id")
    _require_optional_non_empty_text(row.run_id, field_name="run_id")
    _require_optional_non_empty_text(row.attempt_id, field_name="attempt_id")
    _require_optional_non_empty_text(row.execution_id, field_name="execution_id")
    _require_optional_non_empty_text(row.tool_call_id, field_name="tool_call_id")
    _require_optional_non_empty_text(row.tool_name, field_name="tool_name")
    _require_optional_non_empty_text(
        row.provider_request_id, field_name="provider_request_id"
    )
    _require_optional_non_empty_text(row.diagnostic_ref, field_name="diagnostic_ref")
    _require_optional_non_empty_text(
        row.normalized_arguments_digest,
        field_name="normalized_arguments_digest",
    )
    _require_optional_non_empty_text(
        row.semantic_input_digest,
        field_name="semantic_input_digest",
    )
    _require_optional_non_empty_text(row.result_digest, field_name="result_digest")
    _require_optional_non_empty_text(row.payload_ref, field_name="payload_ref")
    _require_optional_non_empty_text(row.payload_digest, field_name="payload_digest")
    _require_optional_non_empty_text(
        row.policy_decision_json, field_name="policy_decision_json"
    )
    _require_optional_non_empty_text(row.cold_trace_ref, field_name="cold_trace_ref")
    _require_optional_non_empty_text(
        row.cold_trace_digest, field_name="cold_trace_digest"
    )
    _require_non_empty_text(row.projected_at, field_name="projected_at")
    _require_non_empty_text(row.updated_at, field_name="updated_at")
    canonical_json_dumps(row.trace_summary)


def _hot_row_from_host_row(row: HostRow) -> ToolTraceHotRow:
    """把通用 HostRow 转换为 ToolTraceHotRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: Tool Trace hot row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return ToolTraceHotRow(
        trace_id=_require_text(row.get("trace_id"), field_name="trace_id"),
        event_id=_require_text(row.get("event_id"), field_name="event_id"),
        event_sequence=_require_int(
            row.get("event_sequence"), field_name="event_sequence"
        ),
        event_type=_require_text(row.get("event_type"), field_name="event_type"),
        event_class=_require_text(row.get("event_class"), field_name="event_class"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        run_id=_optional_text(row.get("run_id"), field_name="run_id"),
        attempt_id=_optional_text(row.get("attempt_id"), field_name="attempt_id"),
        execution_id=_optional_text(
            row.get("execution_id"), field_name="execution_id"
        ),
        tool_call_id=_optional_text(
            row.get("tool_call_id"), field_name="tool_call_id"
        ),
        tool_name=_optional_text(row.get("tool_name"), field_name="tool_name"),
        provider_request_id=_optional_text(
            row.get("provider_request_id"), field_name="provider_request_id"
        ),
        diagnostic_ref=_optional_text(
            row.get("diagnostic_ref"), field_name="diagnostic_ref"
        ),
        normalized_arguments_digest=_optional_text(
            row.get("normalized_arguments_digest"),
            field_name="normalized_arguments_digest",
        ),
        semantic_input_digest=_optional_text(
            row.get("semantic_input_digest"),
            field_name="semantic_input_digest",
        ),
        result_digest=_optional_text(
            row.get("result_digest"), field_name="result_digest"
        ),
        payload_ref=_optional_text(row.get("payload_ref"), field_name="payload_ref"),
        payload_digest=_optional_text(
            row.get("payload_digest"), field_name="payload_digest"
        ),
        policy_decision_json=_optional_text(
            row.get("policy_decision_json"), field_name="policy_decision_json"
        ),
        trace_summary=_json_object_from_text(
            _require_text(row.get("trace_summary_json"), field_name="trace_summary_json")
        ),
        cold_trace_ref=_optional_text(
            row.get("cold_trace_ref"), field_name="cold_trace_ref"
        ),
        cold_trace_digest=_optional_text(
            row.get("cold_trace_digest"), field_name="cold_trace_digest"
        ),
        projected_at=_require_text(row.get("projected_at"), field_name="projected_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
    )


def _json_object_from_text(value: str) -> Mapping[str, JsonValue]:
    """解析 durable JSON object 文本。

    :param value: JSON object 文本。
    :returns: JSON object。
    :raises HostDurableError: JSON 非法或不是 object 时抛出。
    """

    try:
        parsed = cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HostDurableError("tool trace summary JSON is invalid") from exc
    if not isinstance(parsed, Mapping):
        raise HostDurableError("tool trace summary JSON must be object")
    return cast(Mapping[str, JsonValue], parsed)


__all__ = [
    "TOOL_TRACE_QUERY_MAX_LIMIT",
    "ToolTraceHotRow",
    "ToolTraceHotRowWriteResult",
    "ToolTraceHotRowWriteStatus",
    "ToolTraceQueryPage",
    "find_tool_trace_by_diagnostic_ref",
    "find_tool_trace_by_provider_request_id",
    "find_tool_trace_by_tool_call_id",
    "insert_tool_trace_hot_row_if_absent",
    "read_tool_trace_by_run",
    "read_tool_trace_hot_row",
]
