"""Host accepted tool result 的统一可读投影契约。

本模块只消费 Host EventLog 中已经提交的 ``TOOL_RESULT_ACCEPTED`` durable
truth，把 envelope、request atom、raw outcome、query、status 与 source
投影成下游消费者共享的 typed view。它不写回 EventLog，不改变工具事实，
也不把 wait / poll / runtime 治理状态伪装成业务事实。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, read_event_by_id
from dayu.host.durable.transaction import HostTransaction
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    accepted_evidence_envelope_from_payload,
    accepted_tool_raw_outcome_text_from_payload,
    derive_accepted_evidence_id,
)
from dayu.host.evidence import (
    ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT as _ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
)
from dayu.host.evidence import (
    AcceptedEvidenceProducerEventRefMismatchError as _AcceptedEvidenceProducerEventRefMismatchError,
)
from dayu.host.evidence import (
    AcceptedToolEvidenceLLMMaterial as _AcceptedToolEvidenceLLMMaterial,
)
from dayu.host.payload_resolution import (
    ToolCallRequestAtoms,
    event_payload_object,
    event_payload_object_for_result_ref,
    tool_call_request_atoms,
)

_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_FIELD_TOOL_NAME = "tool_name"
_FIELD_TOOL_CALL_ID = "tool_call_id"
_FIELD_NORMALIZED_ARGUMENTS_DIGEST = "normalized_arguments_digest"
_FIELD_RESOLUTION_KIND = "resolution_kind"
_FIELD_TOOL_FACT_KIND = "tool_fact_kind"
_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"
_DIAGNOSTIC_ACCEPTED_STATUS_UNAVAILABLE = "accepted_status_unavailable"
_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE = "result_payload_unavailable"
_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE = "event_payload_unavailable"
_ARGUMENTS_SUMMARY_MAX_CHARS = 1200
_RESULT_DETAILS_MAX_CHARS = 1200
_TRUNCATED_SUFFIX = "...[truncated]"


class AcceptedToolResultStatus(StrEnum):
    """Accepted tool result 可读投影状态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    GOVERNED_ERROR = "governed_error"
    LOST = "lost"
    UNKNOWN = "unknown"


class AcceptedToolResultQueryState(StrEnum):
    """Accepted tool result query 投影来源。"""

    SEMANTIC_QUERY = "semantic_query"
    ARGUMENTS_SUMMARY = "arguments_summary"


class AcceptedToolResultSourceState(StrEnum):
    """Accepted tool result source 投影状态。"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AcceptedToolResultQueryProjection:
    """Accepted tool result 的 query 可读投影。

    :param text: LLM-facing query 文本。
    :param state: query 文本来源。
    :param diagnostic_reason: query 来源说明或降级原因。
    """

    text: str
    state: AcceptedToolResultQueryState
    diagnostic_reason: str | None


@dataclass(frozen=True, slots=True)
class AcceptedToolResultSourceProjection:
    """Accepted tool result 的 source 可读投影。

    :param text: LLM-facing source 文本；无业务 source 时为业务中性不可用文案。
    :param state: source 投影状态。
    :param diagnostic_reason: source 被过滤或缺失的原因。
    """

    text: str
    state: AcceptedToolResultSourceState
    diagnostic_reason: str | None


@dataclass(frozen=True, slots=True)
class AcceptedToolResultProjection:
    """Accepted tool result 的共享可读投影。

    :param event_id: ``TOOL_RESULT_ACCEPTED`` event id。
    :param evidence_id: accepted evidence id。
    :param envelope_available: durable payload 是否携带 accepted evidence envelope。
    :param tool_name: 工具名。
    :param tool_call_id: 工具调用 id。
    :param tool_call_requested_event_ref: 可选 ``TOOL_CALL_REQUESTED`` event ref。
    :param query: query 可读投影。
    :param request_arguments_json: 已校验的 exact canonical request 参数 JSON。
    :param status: 统一工具结果状态。
    :param raw_outcome: raw outcome JSON；不可用时为 ``None``。
    :param result_text: canonical raw outcome 文本；不可用时为 ``None``。
    :param result_details_text: 从 raw outcome 抽取的短业务摘要。
    :param source: source 可读投影。
    :param llm_material: 可直接渲染给 LLM 的 typed evidence material。
    :param payload_refs: 可诊断 payload refs，不进入 LLM-facing source。
    :param diagnostic_reasons: projection 降级或损坏原因。
    """

    event_id: str
    evidence_id: str
    envelope_available: bool
    tool_name: str | None
    tool_call_id: str | None
    tool_call_requested_event_ref: str | None
    query: AcceptedToolResultQueryProjection
    request_arguments_json: Mapping[str, JsonValue] | None
    status: AcceptedToolResultStatus
    raw_outcome: JsonValue | None
    result_text: str | None
    result_details_text: str | None
    source: AcceptedToolResultSourceProjection
    llm_material: _AcceptedToolEvidenceLLMMaterial | None
    payload_refs: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]


def project_accepted_tool_result(
    transaction: HostTransaction,
    result_row: EventLogRow,
    *,
    resolved_payload: Mapping[str, JsonValue] | None = None,
) -> AcceptedToolResultProjection:
    """把 ``TOOL_RESULT_ACCEPTED`` row 投影为共享 accepted-result view。

    :param transaction: 当前 Host transaction。
    :param result_row: ``TOOL_RESULT_ACCEPTED`` EventLog row。
    :param resolved_payload: 调用方已 digest-check 的 payload view。
    :returns: typed accepted-result projection。
    :raises HostDurableError: row 不是 accepted result，或 envelope schema 损坏时抛出。
    """

    if result_row.event_type != _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
        raise HostDurableError("accepted result projection event type mismatch")
    payload, payload_diagnostics = _result_event_payload(
        transaction,
        result_row,
        resolved_payload=resolved_payload,
    )
    envelope = _accepted_envelope(payload, result_row.event_id)
    result_payload, result_diagnostics = _result_payload(
        transaction,
        result_row,
        envelope,
        payload,
    )
    diagnostics = [*payload_diagnostics, *result_diagnostics]
    tool_name = _projection_tool_name(payload, envelope)
    tool_call_id = _projection_tool_call_id(payload, envelope)
    raw_outcome = result_payload.get(_FIELD_RAW_TOOL_OUTCOME) if result_payload is not None else None
    result_text = _raw_outcome_text(result_payload)
    result_details_text = _result_details_text(raw_outcome)
    status, status_diagnostics = _accepted_status(payload, tuple(diagnostics))
    diagnostics.extend(status_diagnostics)
    request_atoms = _request_atoms_projection(
        transaction,
        result_row,
        envelope,
    )
    query = _query_projection(request_atoms)
    source = _source_projection(raw_outcome, diagnostics)
    llm_material = _llm_material(
        tool_name=tool_name,
        query=query,
        source=source,
        result_text=result_text,
    )
    return AcceptedToolResultProjection(
        event_id=result_row.event_id,
        evidence_id=(
            envelope.evidence_id
            if envelope is not None
            else derive_accepted_evidence_id(result_row.event_id)
        ),
        envelope_available=envelope is not None,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_call_requested_event_ref=(
            None
            if envelope is None
            else envelope.tool_query.tool_call_requested_event_ref
        ),
        query=query,
        request_arguments_json=request_atoms.arguments_json,
        status=status,
        raw_outcome=raw_outcome,
        result_text=result_text,
        result_details_text=result_details_text,
        source=source,
        llm_material=llm_material,
        payload_refs=_payload_refs(result_row, envelope),
        diagnostic_reasons=tuple(diagnostics),
    )


def _result_event_payload(
    transaction: HostTransaction,
    result_row: EventLogRow,
    *,
    resolved_payload: Mapping[str, JsonValue] | None,
) -> tuple[Mapping[str, JsonValue], tuple[str, ...]]:
    """读取 accepted result EventLog payload。

    :param transaction: 当前 Host transaction。
    :param result_row: accepted result row。
    :param resolved_payload: 调用方已解析 payload。
    :returns: payload 与读取诊断。
    """

    if resolved_payload is not None:
        return resolved_payload, ()
    try:
        return (
            event_payload_object(
                transaction,
                result_row,
                payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            ),
            (),
        )
    except HostDurableError:
        return ({}, (_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE,))


def _accepted_envelope(
    payload: Mapping[str, JsonValue], event_id: str
) -> AcceptedEvidenceEnvelope | None:
    """读取并校验 accepted evidence envelope。

    :param payload: accepted result payload。
    :param event_id: producer event id。
    :returns: envelope；缺失时为 ``None``。
    :raises HostDurableError: envelope 结构损坏或 producer ref 不一致时抛出。
    """

    try:
        return accepted_evidence_envelope_from_payload(
            payload,
            producer_event_ref=event_id,
        )
    except _AcceptedEvidenceProducerEventRefMismatchError as exc:
        raise HostDurableError("accepted evidence producer_event_ref mismatch") from exc
    except ValueError as exc:
        raise HostDurableError("accepted result envelope is invalid") from exc


def _result_payload(
    transaction: HostTransaction,
    result_row: EventLogRow,
    envelope: AcceptedEvidenceEnvelope | None,
    fallback_payload: Mapping[str, JsonValue],
) -> tuple[Mapping[str, JsonValue] | None, tuple[str, ...]]:
    """读取 envelope 指向的 digest-checked result payload。

    :param transaction: 当前 Host transaction。
    :param result_row: accepted result row。
    :param envelope: accepted evidence envelope。
    :param fallback_payload: EventLog payload。
    :returns: result payload 与读取诊断。
    """

    if fallback_payload.get(_FIELD_RAW_TOOL_OUTCOME) is not None:
        return fallback_payload, ()
    if envelope is None:
        return fallback_payload, ("accepted_evidence_envelope_missing",)
    try:
        return (
            event_payload_object_for_result_ref(
                transaction,
                result_row,
                expected_payload_ref=envelope.result_ref.payload_ref,
                expected_payload_digest=envelope.result_ref.payload_digest,
                payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            ),
            (),
        )
    except HostDurableError:
        return (None, (_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE,))


def _projection_tool_name(
    payload: Mapping[str, JsonValue], envelope: AcceptedEvidenceEnvelope | None
) -> str | None:
    """读取 projection 使用的工具名。

    :param payload: accepted result payload。
    :param envelope: accepted evidence envelope。
    :returns: 工具名；不可读时为 ``None``。
    """

    if envelope is not None:
        return envelope.tool_name
    return _optional_payload_text(payload, _FIELD_TOOL_NAME)


def _projection_tool_call_id(
    payload: Mapping[str, JsonValue], envelope: AcceptedEvidenceEnvelope | None
) -> str | None:
    """读取 projection 使用的工具调用 id。

    :param payload: accepted result payload。
    :param envelope: accepted evidence envelope。
    :returns: tool call id；不可读时为 ``None``。
    """

    if envelope is not None:
        return envelope.tool_call_id
    return _optional_payload_text(payload, _FIELD_TOOL_CALL_ID)


def _raw_outcome_text(payload: Mapping[str, JsonValue] | None) -> str | None:
    """读取 canonical raw outcome 文本。

    :param payload: digest-checked accepted result payload。
    :returns: canonical JSON 文本；不可用时为 ``None``。
    :raises HostDurableError: 旧 result preview 字段仍存在时抛出。
    """

    if payload is None:
        return None
    try:
        return accepted_tool_raw_outcome_text_from_payload(payload)
    except ValueError as exc:
        raise HostDurableError("TOOL_RESULT_ACCEPTED result_preview is not allowed") from exc


def _accepted_status(
    payload: Mapping[str, JsonValue],
    diagnostics: tuple[str, ...],
) -> tuple[AcceptedToolResultStatus, tuple[str, ...]]:
    """归一 accepted tool result status。

    :param payload: accepted result payload。
    :param diagnostics: projection 读取诊断。
    :returns: 封闭状态枚举与状态诊断。
    """

    if (
        _DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE in diagnostics
        or _DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE in diagnostics
    ):
        return (AcceptedToolResultStatus.LOST, ())
    resolution_kind = _payload_status_text(payload, _FIELD_RESOLUTION_KIND)
    if resolution_kind is not None:
        status = _status_from_text(resolution_kind)
        return _status_with_unknown_diagnostic(status)
    tool_fact_kind = _payload_status_text(payload, _FIELD_TOOL_FACT_KIND)
    if tool_fact_kind is not None:
        status = _status_from_text(tool_fact_kind)
        return _status_with_unknown_diagnostic(status)
    return (
        AcceptedToolResultStatus.UNKNOWN,
        (_DIAGNOSTIC_ACCEPTED_STATUS_UNAVAILABLE,),
    )


def _status_from_text(value: str) -> AcceptedToolResultStatus:
    """把 durable status 字段映射为封闭状态。

    :param value: durable status 文本。
    :returns: 封闭状态；未知值映射为 ``UNKNOWN``。
    """

    if value == "completed":
        return AcceptedToolResultStatus.COMPLETED
    if value == "failed":
        return AcceptedToolResultStatus.FAILED
    if value == "cancelled":
        return AcceptedToolResultStatus.CANCELLED
    if value == "governed_error":
        return AcceptedToolResultStatus.GOVERNED_ERROR
    if value == "lost":
        return AcceptedToolResultStatus.LOST
    return AcceptedToolResultStatus.UNKNOWN


def _payload_status_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取 accepted-result payload 中的 typed status 文本。

    状态 owner 是 accept barrier 写入的 typed payload 字段。字段缺失、空白或
    非字符串均视为 status unavailable，不从 raw outcome 重建状态。

    :param payload: accepted result payload。
    :param field_name: typed status 字段名。
    :returns: 去除首尾空白后的状态文本；不可用时为 ``None``。
    """

    value = payload.get(field_name)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text == "":
        return None
    return text


def _status_with_unknown_diagnostic(
    status: AcceptedToolResultStatus,
) -> tuple[AcceptedToolResultStatus, tuple[str, ...]]:
    """给 unknown typed status 附加投影诊断。

    :param status: typed status 字段映射出的封闭状态。
    :returns: 状态与可选诊断。
    """

    if status is AcceptedToolResultStatus.UNKNOWN:
        return (status, (_DIAGNOSTIC_ACCEPTED_STATUS_UNAVAILABLE,))
    return (status, ())


def _request_atoms_projection(
    transaction: HostTransaction,
    result_row: EventLogRow,
    envelope: AcceptedEvidenceEnvelope | None,
) -> ToolCallRequestAtoms:
    """读取并校验 accepted result 指向的 request atom。

    :param transaction: 当前 Host transaction。
    :param result_row: accepted result row。
    :param envelope: accepted evidence envelope。
    :returns: 已严格校验的 request atom。
    :raises HostDurableError: envelope、request link、row、identity 或 atom 正文
        缺失/损坏时抛出。
    """

    if envelope is None:
        raise HostDurableError("accepted result evidence envelope is missing")
    requested_event_ref = envelope.tool_query.tool_call_requested_event_ref
    if requested_event_ref is None:
        raise HostDurableError("tool_call_requested_event_ref is missing")
    request_row = read_event_by_id(transaction, requested_event_ref)
    if request_row is None:
        raise HostDurableError("accepted result request atom is missing")
    if not _request_row_matches_result(request_row, result_row):
        raise HostDurableError("accepted result request atom identity mismatch")
    atoms = tool_call_request_atoms(transaction, request_row)
    if not _request_atoms_match_envelope(atoms, envelope):
        raise HostDurableError("accepted result request atom envelope mismatch")
    return atoms


def _query_projection(
    atoms: ToolCallRequestAtoms,
) -> AcceptedToolResultQueryProjection:
    """构造 query 可读投影。

    :param atoms: 已校验 request atom。
    :returns: query projection。
    """

    if atoms.semantic_query_text is not None:
        return AcceptedToolResultQueryProjection(
            text=atoms.semantic_query_text,
            state=AcceptedToolResultQueryState.SEMANTIC_QUERY,
            diagnostic_reason=None,
        )
    return AcceptedToolResultQueryProjection(
        text=_bounded_text(
            f"参数：{canonical_json_dumps(atoms.arguments_json)}",
            max_chars=_ARGUMENTS_SUMMARY_MAX_CHARS,
        ),
        state=AcceptedToolResultQueryState.ARGUMENTS_SUMMARY,
        diagnostic_reason="semantic_query_missing",
    )


def _request_row_matches_result(
    request_row: EventLogRow, result_row: EventLogRow
) -> bool:
    """校验 request atom 与 accepted result 的 Host 身份边界一致。

    :param request_row: ``TOOL_CALL_REQUESTED`` row。
    :param result_row: ``TOOL_RESULT_ACCEPTED`` row。
    :returns: 同一 session/run/attempt/execution 时返回 ``True``。
    """

    return (
        request_row.event_class is EventClass.CANONICAL_FACT
        and request_row.event_type == _EVENT_TYPE_TOOL_CALL_REQUESTED
        and request_row.session_id == result_row.session_id
        and request_row.run_id == result_row.run_id
        and request_row.attempt_id == result_row.attempt_id
        and request_row.execution_id == result_row.execution_id
    )


def _request_atoms_match_envelope(
    atoms: ToolCallRequestAtoms, envelope: AcceptedEvidenceEnvelope
) -> bool:
    """校验 request atom 与 envelope 的工具调用身份一致。

    :param atoms: request atom。
    :param envelope: accepted evidence envelope。
    :returns: 身份一致时返回 ``True``。
    """

    return (
        atoms.tool_call_id == envelope.tool_call_id
        and atoms.tool_name == envelope.tool_name
        and atoms.normalized_arguments_digest
        == envelope.tool_query.normalized_arguments_digest
        and atoms.semantic_input_digest
        == envelope.tool_query.semantic_input_digest
    )


def _source_projection(
    raw_outcome: JsonValue | None,
    diagnostics: list[str],
) -> AcceptedToolResultSourceProjection:
    """构造 source 可读投影。

    只有 accepted completed-success outcome 的 ``result.value.citation`` object
    属于 producer 显式业务来源。Host 机械渲染整个 citation object，不解释或
    筛选业务字段，也不从 opaque provenance refs 猜测来源。

    :param raw_outcome: 已完成 payload/digest 校验的 canonical raw outcome。
    :param diagnostics: projection 诊断列表，可追加 source 降级原因。
    :returns: source projection。
    """

    citation = _explicit_citation(raw_outcome)
    if citation is not None:
        return AcceptedToolResultSourceProjection(
            text=canonical_json_dumps(citation),
            state=AcceptedToolResultSourceState.AVAILABLE,
            diagnostic_reason=None,
        )
    diagnostics.append("business_source_unavailable")
    return AcceptedToolResultSourceProjection(
        text=_ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
        state=AcceptedToolResultSourceState.UNAVAILABLE,
        diagnostic_reason="business_source_unavailable",
    )


def _explicit_citation(raw_outcome: JsonValue | None) -> Mapping[str, JsonValue] | None:
    """读取 producer-owned 显式 citation object。

    :param raw_outcome: accepted outcome canonical JSON atom。
    :returns: 完整 citation object；shape 不匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(raw_outcome, Mapping) or raw_outcome.get("kind") != "completed":
        return None
    result = raw_outcome.get("result")
    if not isinstance(result, Mapping) or result.get("ok") is not True:
        return None
    value = result.get("value")
    if not isinstance(value, Mapping):
        return None
    citation = value.get("citation")
    if not isinstance(citation, Mapping):
        return None
    return citation


def _payload_refs(
    result_row: EventLogRow, envelope: AcceptedEvidenceEnvelope | None
) -> tuple[str, ...]:
    """收集 projection 诊断用 payload refs。

    :param result_row: accepted result row。
    :param envelope: accepted evidence envelope。
    :returns: payload ref tuple。
    """

    refs: list[str] = []
    if result_row.payload_ref is not None:
        refs.append(result_row.payload_ref)
    if envelope is not None and envelope.result_ref.payload_ref is not None:
        refs.append(envelope.result_ref.payload_ref)
    return tuple(dict.fromkeys(refs))


def _llm_material(
    *,
    tool_name: str | None,
    query: AcceptedToolResultQueryProjection,
    source: AcceptedToolResultSourceProjection,
    result_text: str | None,
) -> _AcceptedToolEvidenceLLMMaterial | None:
    """从已校验 projection 字段构造 LLM material。

    :param tool_name: 工具名。
    :param query: query projection。
    :param source: source projection。
    :param result_text: canonical 工具结果文本。
    :returns: 字段完整时返回 material，否则返回 ``None``。
    """

    if tool_name is None or result_text is None:
        return None
    return _AcceptedToolEvidenceLLMMaterial(
        tool_name=tool_name,
        query_text=query.text,
        source_text=source.text,
        result_text=result_text,
    )


def _result_details_text(value: JsonValue | None) -> str | None:
    """从 raw outcome 中抽取短业务摘要。

    :param value: raw outcome JSON。
    :returns: details / summary 文本；找不到时为 ``None``。
    """

    if isinstance(value, Mapping):
        for key in ("details", "summary", "message", "error"):
            item = value.get(key)
            if isinstance(item, str) and item.strip() != "":
                return _bounded_text(item, max_chars=_RESULT_DETAILS_MAX_CHARS)
            details_text = _structured_details_text(item)
            if details_text is not None:
                return details_text
        for key in ("value", "result", "data"):
            nested = value.get(key)
            nested_text = _result_details_text(nested)
            if nested_text is not None:
                return nested_text
    if isinstance(value, list):
        for item in value:
            nested_text = _result_details_text(item)
            if nested_text is not None:
                return nested_text
    return None


def _structured_details_text(value: JsonValue) -> str | None:
    """把结构化 details JSON 转成短业务摘要。

    :param value: details / summary 字段值。
    :returns: 短摘要文本；不可投影时为 ``None``。
    """

    if isinstance(value, Mapping):
        label = value.get("label")
        detail_value = value.get("value")
        if isinstance(label, str) and label.strip() != "":
            return f"{label}={_detail_scalar_text(detail_value)}"
        return None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            item_text = _structured_details_text(item)
            if item_text is not None:
                parts.append(item_text)
        if len(parts) > 0:
            return _bounded_text(
                ", ".join(parts),
                max_chars=_RESULT_DETAILS_MAX_CHARS,
            )
    return None


def _detail_scalar_text(value: JsonValue) -> str:
    """把单个 detail value 格式化为短文本。

    :param value: JSON detail value。
    :returns: 短文本。
    """

    if (
        isinstance(value, str)
        or isinstance(value, int)
        or isinstance(value, float)
        or isinstance(value, bool)
        or value is None
    ):
        return str(value)
    return _bounded_text(canonical_json_dumps(value), max_chars=160)


def _bounded_text(text: str, *, max_chars: int) -> str:
    """按字符数截断可读文本。

    :param text: 原始文本。
    :param max_chars: 最大字符数。
    :returns: 截断后的文本。
    """

    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX


def _optional_payload_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取 accepted-result payload 中的可选非空文本字段。

    字段缺失或显式为 ``null`` 时返回 ``None``；字段存在但不是非空文本时
    fail closed，避免把 malformed optional 字段误当缺失字段继续投影。

    :param payload: accepted result payload。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段存在但类型错误或空白时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"payload field {field_name} must be non-empty text")


def projection_result_digest(projection: AcceptedToolResultProjection) -> str | None:
    """计算 projection result_text 的 digest。

    :param projection: accepted tool result projection。
    :returns: result_text JSON digest；无 result_text 时为 ``None``。
    """

    if projection.result_text is None:
        return None
    return sha256_digest_json(projection.result_text)


__all__ = [
    "AcceptedToolResultProjection",
    "AcceptedToolResultQueryProjection",
    "AcceptedToolResultQueryState",
    "AcceptedToolResultSourceProjection",
    "AcceptedToolResultSourceState",
    "AcceptedToolResultStatus",
    "project_accepted_tool_result",
]
