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
_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_RUNNER_CALL_TRACE_EVENT_TYPE = "event_type"
_RUNNER_CALL_TRACE_RUNNER_CALL_INDEX = "runner_call_index"
_RUNNER_CALL_TRACE_RUNNER_CALL_KIND = "runner_call_kind"
_RUNNER_CALL_TRACE_RUNNER_CALL_TRIGGER_REASON = "runner_call_trigger_reason"
_RUNNER_CALL_TRACE_ITERATION_ID = "iteration_id"
_RUNNER_CALL_TRACE_MANIFEST_REF = "manifest_ref"
_RUNNER_CALL_TRACE_MANIFEST_DIGEST = "manifest_digest"
_RUNNER_CALL_TRACE_MESSAGE_COUNT = "message_count"
_RUNNER_CALL_TRACE_ROLE_SEQUENCE_DIGEST = "role_sequence_digest"
_RUNNER_CALL_TRACE_INPUT_PROJECTION_DIGEST = "input_projection_digest"
_RUNNER_CALL_TRACE_PROJECTOR_METADATA_SUMMARY = "projector_metadata_summary"
_RUNNER_CALL_TRACE_DIAGNOSTIC = "diagnostic"
_RUNNER_CALL_PROJECTOR_METADATA_ID = "projector_metadata_id"
_RUNNER_CALL_PROJECTOR_ID = "projector_id"
_RUNNER_CALL_PROJECTOR_SCHEMA_VERSION = "projector_schema_version"
_RUNNER_CALL_PROJECTOR_DIGEST = "projector_digest"
_RUNNER_CALL_PROJECTOR_PURPOSE = "purpose"


class RunnerCallReconstructionStatus(StrEnum):
    """Runner-call reconstruction signal 状态。"""

    COMPLETE = "complete"
    LIMITED_SIGNAL = "limited_signal"
    MISMATCH = "mismatch"


class RunnerCallReconstructionDiagnosticReason(StrEnum):
    """Runner-call reconstruction diagnostic reason 封闭枚举。"""

    MISSING_RUNNER_CALL_MANIFEST = "missing_runner_call_manifest"
    MISSING_PROJECTION_ARTIFACT = "missing_projection_artifact"
    MISSING_TOOL_CALL_ARGUMENTS_ATOM = "missing_tool_call_arguments_atom"
    MISSING_SEMANTIC_QUERY_ATOM = "missing_semantic_query_atom"
    MISSING_COMPACTOR_MANIFEST = "missing_compactor_manifest"
    MISSING_MEMORY_SNAPSHOT_BODY = "missing_memory_snapshot_body"
    UNSUPPORTED_PROJECTOR_VERSION = "unsupported_projector_version"
    MESSAGE_COUNT_MISMATCH = "message_count_mismatch"
    ROLE_SEQUENCE_DIGEST_MISMATCH = "role_sequence_digest_mismatch"
    INPUT_PROJECTION_DIGEST_MISMATCH = "input_projection_digest_mismatch"
    PAYLOAD_DIGEST_MISMATCH = "payload_digest_mismatch"
    UNRESOLVABLE_REF = "unresolvable_ref"
    PROVIDER_SPECIFIC_ATOM_DEFERRED = "provider_specific_atom_deferred"


class RunnerCallReconstructionMissingAtomKind(StrEnum):
    """Runner-call reconstruction 缺失 durable atom kind。"""

    TOOL_CALL_ARGUMENTS = "tool_call_arguments"
    SEMANTIC_QUERY = "semantic_query"
    RUNNER_CALL_MANIFEST = "runner_call_manifest"
    COMPACTOR_MANIFEST = "compactor_manifest"
    PROJECTION_ARTIFACT = "projection_artifact"
    MEMORY_SNAPSHOT_BODY = "memory_snapshot_body"


class RunnerCallReconstructionMissingRefKind(StrEnum):
    """Runner-call reconstruction 缺失 ref kind。"""

    PAYLOAD_REF = "payload_ref"
    ARTIFACT_REF = "artifact_ref"
    EVENT_REF = "event_ref"
    CURSOR_REF = "cursor_ref"


class RunnerCallReconstructionConsumerBoundary(StrEnum):
    """Runner-call reconstruction diagnostic consumer boundary。"""

    TOOL_TRACE_QUERY = "tool_trace_query"
    ANALYZER_FIXTURE = "analyzer_fixture"
    COMPACT_EVIDENCE_PROJECTION = "compact_evidence_projection"
    PUBLIC_SMOKE = "public_smoke"


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


@dataclass(frozen=True, slots=True)
class ProjectorMetadataSummary:
    """Runner-call projector metadata read-model 摘要。

    :param projector_metadata_id: manifest 内 projector metadata 引用 id。
    :param projector_id: projector 稳定逻辑 id。
    :param projector_schema_version: projector 输出契约版本。
    :param projector_digest: projector contract / configuration digest。
    :param purpose: projector 业务目的摘要。
    """

    projector_metadata_id: str
    projector_id: str
    projector_schema_version: str
    projector_digest: str
    purpose: str


@dataclass(frozen=True, slots=True)
class RunnerCallReconstructionDiagnostic:
    """Runner-call reconstruction typed diagnostic。

    :param status: reconstruction 状态。
    :param reason: 非 complete 状态下的封闭原因。
    :param missing_atom_kind: 可选缺失 durable atom kind。
    :param missing_ref_kind: 可选缺失 ref kind。
    :param missing_ref: 可选缺失 ref 标签。
    :param observed_count: mismatch 或 limited signal 观察到的数量。
    :param expected_count: mismatch 期望数量。
    :param observed_digest: mismatch 或 limited signal 观察到的 digest。
    :param expected_digest: mismatch 期望 digest。
    :param consumer_boundary: diagnostic 消费边界。
    """

    status: RunnerCallReconstructionStatus
    reason: RunnerCallReconstructionDiagnosticReason | None
    missing_atom_kind: RunnerCallReconstructionMissingAtomKind | None
    missing_ref_kind: RunnerCallReconstructionMissingRefKind | None
    missing_ref: str | None
    observed_count: int | None
    expected_count: int | None
    observed_digest: str | None
    expected_digest: str | None
    consumer_boundary: RunnerCallReconstructionConsumerBoundary


@dataclass(frozen=True, slots=True)
class RunnerCallReconstructionSignal:
    """Tool Trace runner-call reconstruction read-model signal。

    :param event_id: source EventLog id。
    :param event_sequence: source EventLog sequence。
    :param session_id: source Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param runner_call_index: Host runner-call index。
    :param runner_call_kind: runner-call kind。
    :param runner_call_trigger_reason: runner-call trigger reason。
    :param iteration_id: 可选 Engine iteration id。
    :param manifest_ref: runner-call manifest descriptor ref。
    :param manifest_digest: runner-call manifest digest。
    :param message_count: runner-call message count summary。
    :param role_sequence_digest: runner-call role sequence digest。
    :param input_projection_digest: runner-call source summary digest。
    :param projector_metadata_summary: projector metadata summary 元组。
    :param diagnostic: typed reconstruction diagnostic。
    """

    event_id: str
    event_sequence: int
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    runner_call_index: int | None
    runner_call_kind: str | None
    runner_call_trigger_reason: str | None
    iteration_id: str | None
    manifest_ref: str | None
    manifest_digest: str | None
    message_count: int | None
    role_sequence_digest: str | None
    input_projection_digest: str | None
    projector_metadata_summary: tuple[ProjectorMetadataSummary, ...]
    diagnostic: RunnerCallReconstructionDiagnostic


@dataclass(frozen=True, slots=True)
class RunnerCallReconstructionSignalPage:
    """Runner-call reconstruction signal 分页结果。

    :param signals: 当前页 signal。
    :param next_event_sequence: 下一次查询可使用的 event sequence cursor。
    :param has_more: 是否存在下一页。
    """

    signals: tuple[RunnerCallReconstructionSignal, ...]
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


def read_runner_call_reconstruction_signals_by_run(
    transaction: HostTransaction,
    run_id: str,
    after_event_sequence: int,
    limit: int,
) -> RunnerCallReconstructionSignalPage:
    """按 Run id 读取 runner-call reconstruction signals。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: Run id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回 signal 数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的 runner-call signal 页。
    :raises HostDurableError: 输入非法或 Tool Trace projection JSON 类型不符合契约时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    page = _query_page(
        transaction,
        where_sql="run_id = ? AND event_type = ?",
        parameters=(run_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )
    return RunnerCallReconstructionSignalPage(
        signals=tuple(_runner_call_signal_from_hot_row(row) for row in page.rows),
        next_event_sequence=page.next_event_sequence,
        has_more=page.has_more,
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


def _runner_call_signal_from_hot_row(
    row: ToolTraceHotRow,
) -> RunnerCallReconstructionSignal:
    """把 hot row 转换为 typed runner-call reconstruction signal。

    :param row: Tool Trace hot row。
    :returns: typed runner-call reconstruction signal。
    :raises HostDurableError: row 不是 runner-call signal 或 summary 类型非法时抛出。
    """

    summary = row.trace_summary
    event_type = _summary_required_text(
        summary, _RUNNER_CALL_TRACE_EVENT_TYPE
    )
    if event_type != _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED:
        raise HostDurableError("tool trace row is not runner-call signal")
    return RunnerCallReconstructionSignal(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        runner_call_index=_summary_optional_int(
            summary, _RUNNER_CALL_TRACE_RUNNER_CALL_INDEX
        ),
        runner_call_kind=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_RUNNER_CALL_KIND
        ),
        runner_call_trigger_reason=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_RUNNER_CALL_TRIGGER_REASON
        ),
        iteration_id=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_ITERATION_ID
        ),
        manifest_ref=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_MANIFEST_REF
        ),
        manifest_digest=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_MANIFEST_DIGEST
        ),
        message_count=_summary_optional_int(
            summary, _RUNNER_CALL_TRACE_MESSAGE_COUNT
        ),
        role_sequence_digest=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_ROLE_SEQUENCE_DIGEST
        ),
        input_projection_digest=_summary_optional_text(
            summary, _RUNNER_CALL_TRACE_INPUT_PROJECTION_DIGEST
        ),
        projector_metadata_summary=_projector_metadata_summary_from_trace(summary),
        diagnostic=_runner_call_diagnostic_from_trace(summary),
    )


def _projector_metadata_summary_from_trace(
    summary: Mapping[str, JsonValue],
) -> tuple[ProjectorMetadataSummary, ...]:
    """从 trace summary 读取 projector metadata summary。

    :param summary: runner-call trace summary。
    :returns: typed projector metadata summary 元组。
    :raises HostDurableError: projector metadata summary 类型非法时抛出。
    """

    value = summary.get(_RUNNER_CALL_TRACE_PROJECTOR_METADATA_SUMMARY)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise HostDurableError(
            "tool trace runner-call projector_metadata_summary must be array"
        )
    items: list[ProjectorMetadataSummary] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError(
                "tool trace runner-call projector metadata item must be object"
            )
        item_mapping = cast(Mapping[str, JsonValue], item)
        items.append(
            ProjectorMetadataSummary(
                projector_metadata_id=_summary_required_text(
                    item_mapping, _RUNNER_CALL_PROJECTOR_METADATA_ID
                ),
                projector_id=_summary_required_text(
                    item_mapping, _RUNNER_CALL_PROJECTOR_ID
                ),
                projector_schema_version=_summary_required_text(
                    item_mapping, _RUNNER_CALL_PROJECTOR_SCHEMA_VERSION
                ),
                projector_digest=_summary_required_text(
                    item_mapping, _RUNNER_CALL_PROJECTOR_DIGEST
                ),
                purpose=_summary_required_text(
                    item_mapping, _RUNNER_CALL_PROJECTOR_PURPOSE
                ),
            )
        )
    return tuple(items)


def _runner_call_diagnostic_from_trace(
    summary: Mapping[str, JsonValue],
) -> RunnerCallReconstructionDiagnostic:
    """从 trace summary 读取 typed runner-call diagnostic。

    :param summary: runner-call trace summary。
    :returns: typed runner-call diagnostic。
    :raises HostDurableError: diagnostic 缺失、类型非法或 enum 值非法时抛出。
    """

    value = summary.get(_RUNNER_CALL_TRACE_DIAGNOSTIC)
    if not isinstance(value, Mapping):
        raise HostDurableError("tool trace runner-call diagnostic must be object")
    diagnostic = cast(Mapping[str, JsonValue], value)
    status = _runner_call_status_from_text(
        _summary_required_text(diagnostic, "status"),
        field_name="diagnostic.status",
    )
    reason_text = _summary_optional_text(diagnostic, "reason")
    missing_atom_text = _summary_optional_text(diagnostic, "missing_atom_kind")
    missing_ref_text = _summary_optional_text(diagnostic, "missing_ref_kind")
    if status is RunnerCallReconstructionStatus.COMPLETE and reason_text is not None:
        raise HostDurableError("complete runner-call diagnostic reason must be absent")
    if status is not RunnerCallReconstructionStatus.COMPLETE and reason_text is None:
        raise HostDurableError("non-complete runner-call diagnostic reason is required")
    return RunnerCallReconstructionDiagnostic(
        status=status,
        reason=_optional_runner_call_reason_from_text(
            reason_text,
            field_name="diagnostic.reason",
        ),
        missing_atom_kind=_optional_runner_call_missing_atom_kind_from_text(
            missing_atom_text,
            field_name="diagnostic.missing_atom_kind",
        ),
        missing_ref_kind=_optional_runner_call_missing_ref_kind_from_text(
            missing_ref_text,
            field_name="diagnostic.missing_ref_kind",
        ),
        missing_ref=_summary_optional_text(diagnostic, "missing_ref"),
        observed_count=_summary_optional_int(diagnostic, "observed_count"),
        expected_count=_summary_optional_int(diagnostic, "expected_count"),
        observed_digest=_summary_optional_text(diagnostic, "observed_digest"),
        expected_digest=_summary_optional_text(diagnostic, "expected_digest"),
        consumer_boundary=_runner_call_consumer_boundary_from_text(
            _summary_required_text(diagnostic, "consumer_boundary"),
            field_name="diagnostic.consumer_boundary",
        ),
    )


def _summary_required_text(
    summary: Mapping[str, JsonValue], field_name: str
) -> str:
    """读取 summary 中的必填非空文本。

    :param summary: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = summary.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace summary field {field_name} must be text")


def _summary_optional_text(
    summary: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 summary 中的可选非空文本。

    :param summary: JSON object。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    value = summary.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace summary field {field_name} must be text")


def _summary_optional_int(
    summary: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取 summary 中的可选非负整数。

    :param summary: JSON object。
    :param field_name: 字段名。
    :returns: 整数或 ``None``。
    :raises HostDurableError: 字段存在但不是非负整数时抛出。
    """

    value = summary.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(
            f"tool trace summary field {field_name} must be non-negative integer"
        )
    return value


def _runner_call_status_from_text(
    value: str, *, field_name: str
) -> RunnerCallReconstructionStatus:
    """把必填文本转换为 runner-call reconstruction status。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: status enum 成员。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    try:
        return RunnerCallReconstructionStatus(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _runner_call_consumer_boundary_from_text(
    value: str, *, field_name: str
) -> RunnerCallReconstructionConsumerBoundary:
    """把必填文本转换为 runner-call reconstruction consumer boundary。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: consumer boundary enum 成员。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    try:
        return RunnerCallReconstructionConsumerBoundary(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _optional_runner_call_reason_from_text(
    value: str | None,
    *,
    field_name: str,
) -> RunnerCallReconstructionDiagnosticReason | None:
    """把可选文本转换为 runner-call reconstruction reason。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: reason enum 成员或 ``None``。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    if value is None:
        return None
    try:
        return RunnerCallReconstructionDiagnosticReason(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _optional_runner_call_missing_atom_kind_from_text(
    value: str | None,
    *,
    field_name: str,
) -> RunnerCallReconstructionMissingAtomKind | None:
    """把可选文本转换为 runner-call reconstruction missing atom kind。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: missing atom kind enum 成员或 ``None``。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    if value is None:
        return None
    try:
        return RunnerCallReconstructionMissingAtomKind(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _optional_runner_call_missing_ref_kind_from_text(
    value: str | None,
    *,
    field_name: str,
) -> RunnerCallReconstructionMissingRefKind | None:
    """把可选文本转换为 runner-call reconstruction missing ref kind。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: missing ref kind enum 成员或 ``None``。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    if value is None:
        return None
    try:
        return RunnerCallReconstructionMissingRefKind(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


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
    "ProjectorMetadataSummary",
    "RunnerCallReconstructionConsumerBoundary",
    "RunnerCallReconstructionDiagnostic",
    "RunnerCallReconstructionDiagnosticReason",
    "RunnerCallReconstructionMissingAtomKind",
    "RunnerCallReconstructionMissingRefKind",
    "RunnerCallReconstructionSignal",
    "RunnerCallReconstructionSignalPage",
    "RunnerCallReconstructionStatus",
    "ToolTraceHotRow",
    "ToolTraceHotRowWriteResult",
    "ToolTraceHotRowWriteStatus",
    "ToolTraceQueryPage",
    "find_tool_trace_by_diagnostic_ref",
    "find_tool_trace_by_provider_request_id",
    "find_tool_trace_by_tool_call_id",
    "insert_tool_trace_hot_row_if_absent",
    "read_runner_call_reconstruction_signals_by_run",
    "read_tool_trace_by_run",
    "read_tool_trace_hot_row",
]
