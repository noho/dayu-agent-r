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
    ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH,
    AcceptedEvidenceEnvelope,
    OpaqueEvidenceRef,
    accepted_evidence_envelope_from_payload,
    accepted_tool_raw_outcome_text_from_payload,
    derive_accepted_evidence_id,
)
from dayu.host.payload_resolution import (
    ToolCallRequestAtoms,
    event_payload_object,
    event_payload_object_for_result_ref,
    tool_call_request_atoms,
)

ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT = "查询语义不可用；参数未安全展开。"
"""Accepted tool result query 不可安全投影时的唯一 LLM-facing 文案。"""

ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = (
    "业务来源不可用；工具结果未提供可安全展示的来源。"
)
"""Accepted tool result source 不可安全投影时的唯一 LLM-facing 文案。"""

_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_FIELD_TOOL_NAME = "tool_name"
_FIELD_TOOL_CALL_ID = "tool_call_id"
_FIELD_NORMALIZED_ARGUMENTS_DIGEST = "normalized_arguments_digest"
_FIELD_RESOLUTION_KIND = "resolution_kind"
_FIELD_TOOL_FACT_KIND = "tool_fact_kind"
_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"
_FIELD_RESULT = "result"
_FIELD_KIND = "kind"
_FIELD_OK = "ok"
_READABLE_SOURCE_SEPARATOR = ", "
_ARGUMENTS_SUMMARY_MAX_CHARS = 1200
_RESULT_DETAILS_MAX_CHARS = 1200
_TRUNCATED_SUFFIX = "...[truncated]"
_INTERNAL_SOURCE_REF_KINDS = frozenset(
    {
        "tool_call_event",
        "tool_result_event",
        "event",
        "eventlog",
        "payload",
        "artifact",
        "digest",
    }
)


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
    LIMITED_SIGNAL = "limited_signal"


class AcceptedToolResultSourceState(StrEnum):
    """Accepted tool result source 投影状态。"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AcceptedToolResultQueryProjection:
    """Accepted tool result 的 query 可读投影。

    :param text: LLM-facing query 文本。
    :param state: query 文本来源。
    :param diagnostic_reason: limited-signal 或降级原因。
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
    :param query: query 可读投影。
    :param request_arguments_json: 已校验的 LLM-safe request 参数 JSON。
    :param status: 统一工具结果状态。
    :param raw_outcome: raw outcome JSON；不可用时为 ``None``。
    :param result_text: canonical raw outcome 文本；不可用时为 ``None``。
    :param result_details_text: 从 raw outcome 抽取的短业务摘要。
    :param source: source 可读投影。
    :param payload_refs: 可诊断 payload refs，不进入 LLM-facing source。
    :param diagnostic_reasons: projection 降级或损坏原因。
    """

    event_id: str
    evidence_id: str
    envelope_available: bool
    tool_name: str | None
    tool_call_id: str | None
    query: AcceptedToolResultQueryProjection
    request_arguments_json: Mapping[str, JsonValue] | None
    status: AcceptedToolResultStatus
    raw_outcome: JsonValue | None
    result_text: str | None
    result_details_text: str | None
    source: AcceptedToolResultSourceProjection
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
        resolved_payload_available=resolved_payload is not None,
    )
    diagnostics = [*payload_diagnostics, *result_diagnostics]
    tool_name = _projection_tool_name(payload, envelope)
    tool_call_id = _projection_tool_call_id(payload, envelope)
    raw_outcome = result_payload.get(_FIELD_RAW_TOOL_OUTCOME) if result_payload is not None else None
    result_text = _raw_outcome_text(result_payload)
    result_details_text = _result_details_text(raw_outcome)
    status = _accepted_status(payload, raw_outcome, tuple(diagnostics))
    request_atoms = _request_atoms_projection(
        transaction,
        result_row,
        envelope,
        diagnostics,
    )
    query = _query_projection(request_atoms, payload, diagnostics)
    source = _source_projection(envelope, diagnostics)
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
        query=query,
        request_arguments_json=(
            request_atoms.arguments_json if request_atoms is not None else None
        ),
        status=status,
        raw_outcome=raw_outcome,
        result_text=result_text,
        result_details_text=result_details_text,
        source=source,
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
        return ({}, ("event_payload_unavailable",))


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
    except ValueError as exc:
        if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH:
            raise HostDurableError(str(exc)) from exc
        raise HostDurableError("accepted result envelope is invalid") from exc


def _result_payload(
    transaction: HostTransaction,
    result_row: EventLogRow,
    envelope: AcceptedEvidenceEnvelope | None,
    fallback_payload: Mapping[str, JsonValue],
    *,
    resolved_payload_available: bool,
) -> tuple[Mapping[str, JsonValue] | None, tuple[str, ...]]:
    """读取 envelope 指向的 digest-checked result payload。

    :param transaction: 当前 Host transaction。
    :param result_row: accepted result row。
    :param envelope: accepted evidence envelope。
    :param fallback_payload: EventLog payload。
    :param resolved_payload_available: fallback payload 是否已由调用方校验。
    :returns: result payload 与读取诊断。
    """

    if resolved_payload_available:
        if envelope is None:
            return fallback_payload, ("accepted_evidence_envelope_missing",)
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
        return (None, ("result_payload_unavailable",))


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
    return _optional_text(payload, _FIELD_TOOL_NAME)


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
    return _optional_text(payload, _FIELD_TOOL_CALL_ID)


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
    raw_outcome: JsonValue | None,
    diagnostics: tuple[str, ...],
) -> AcceptedToolResultStatus:
    """归一 accepted tool result status。

    :param payload: accepted result payload。
    :param raw_outcome: raw outcome JSON。
    :param diagnostics: projection 读取诊断。
    :returns: 封闭状态枚举。
    """

    if "result_payload_unavailable" in diagnostics or "event_payload_unavailable" in diagnostics:
        return AcceptedToolResultStatus.LOST
    resolution_kind = _optional_text(payload, _FIELD_RESOLUTION_KIND)
    if resolution_kind is not None:
        return _status_from_text(resolution_kind)
    tool_fact_kind = _optional_text(payload, _FIELD_TOOL_FACT_KIND)
    if tool_fact_kind is not None:
        return _status_from_text(tool_fact_kind)
    if raw_outcome is None:
        return AcceptedToolResultStatus.LOST
    raw_status = _status_from_raw_outcome(raw_outcome)
    if raw_status is not None:
        return raw_status
    return AcceptedToolResultStatus.UNKNOWN


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


def _status_from_raw_outcome(raw_outcome: JsonValue) -> AcceptedToolResultStatus | None:
    """从 raw outcome 的通用字段降级推断状态。

    :param raw_outcome: raw outcome JSON。
    :returns: 状态；无法判断时为 ``None``。
    """

    if not isinstance(raw_outcome, Mapping):
        return None
    kind = raw_outcome.get(_FIELD_KIND)
    if isinstance(kind, str) and kind.strip() != "":
        return _status_from_text(kind)
    result = raw_outcome.get(_FIELD_RESULT)
    if isinstance(result, Mapping):
        ok = result.get(_FIELD_OK)
        if isinstance(ok, bool):
            return (
                AcceptedToolResultStatus.COMPLETED
                if ok
                else AcceptedToolResultStatus.FAILED
            )
    return None


def _request_atoms_projection(
    transaction: HostTransaction,
    result_row: EventLogRow,
    envelope: AcceptedEvidenceEnvelope | None,
    diagnostics: list[str],
) -> ToolCallRequestAtoms | None:
    """读取并校验 accepted result 指向的 request atom。

    :param transaction: 当前 Host transaction。
    :param result_row: accepted result row。
    :param envelope: accepted evidence envelope。
    :param diagnostics: projection 诊断列表，可追加 request 降级原因。
    :returns: 已校验 request atom；不可用时为 ``None``。
    """

    if envelope is None:
        diagnostics.append("accepted_evidence_envelope_missing")
        return None
    requested_event_ref = envelope.tool_query.tool_call_requested_event_ref
    if requested_event_ref is None:
        diagnostics.append("request_atom_unavailable")
        return None
    request_row = read_event_by_id(transaction, requested_event_ref)
    if request_row is None:
        diagnostics.append("request_atom_unavailable")
        return None
    if not _request_row_matches_result(request_row, result_row):
        diagnostics.append("request_atom_identity_mismatch")
        return None
    try:
        atoms = tool_call_request_atoms(transaction, request_row)
    except HostDurableError:
        diagnostics.append("request_atom_unreadable")
        return None
    if not _request_atoms_match_envelope(atoms, envelope):
        diagnostics.append("request_atom_identity_mismatch")
        return None
    return atoms


def _query_projection(
    atoms: ToolCallRequestAtoms | None,
    payload: Mapping[str, JsonValue],
    diagnostics: list[str],
) -> AcceptedToolResultQueryProjection:
    """构造 query 可读投影。

    :param atoms: 已校验 request atom。
    :param payload: accepted result payload。
    :param diagnostics: projection 诊断列表。
    :returns: query projection。
    """

    if atoms is None:
        reason = diagnostics[-1] if len(diagnostics) > 0 else "request_atom_unavailable"
        return _request_unavailable_query(reason)
    if atoms.semantic_query_text is not None:
        return AcceptedToolResultQueryProjection(
            text=atoms.semantic_query_text,
            state=AcceptedToolResultQueryState.SEMANTIC_QUERY,
            diagnostic_reason=None,
        )
    if _contains_unsafe_argument_key(atoms.arguments_json):
        diagnostics.append("arguments_summary_unsafe")
        return _limited_query("arguments_summary_unsafe")
    return AcceptedToolResultQueryProjection(
        text=_bounded_text(
            f"参数：{canonical_json_dumps(atoms.arguments_json)}",
            max_chars=_ARGUMENTS_SUMMARY_MAX_CHARS,
        ),
        state=AcceptedToolResultQueryState.ARGUMENTS_SUMMARY,
        diagnostic_reason="semantic_query_missing",
    )


def _contains_unsafe_argument_key(value: JsonValue) -> bool:
    """判断参数 JSON 是否含不应进入 LLM-facing query 摘要的字段。

    :param value: 参数 JSON。
    :returns: 含敏感或本地路径类字段时返回 ``True``。
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = key.strip().lower()
            if (
                "api_key" in normalized
                or "token" in normalized
                or "secret" in normalized
                or "password" in normalized
                or normalized.endswith("path")
                or "path_" in normalized
            ):
                return True
            if _contains_unsafe_argument_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_unsafe_argument_key(item) for item in value)
    return False


def _limited_query(reason: str) -> AcceptedToolResultQueryProjection:
    """构造 query limited-signal 投影。

    :param reason: limited-signal 原因。
    :returns: query projection。
    """

    return AcceptedToolResultQueryProjection(
        text=ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT,
        state=AcceptedToolResultQueryState.LIMITED_SIGNAL,
        diagnostic_reason=reason,
    )


def _request_unavailable_query(reason: str) -> AcceptedToolResultQueryProjection:
    """在 request atom 不可用时构造 query 降级投影。

    :param reason: 降级原因。
    :returns: query projection。
    """

    return _limited_query(reason)


def _request_row_matches_result(
    request_row: EventLogRow, result_row: EventLogRow
) -> bool:
    """校验 request atom 与 accepted result 的 Host 身份边界一致。

    :param request_row: ``TOOL_CALL_REQUESTED`` row。
    :param result_row: ``TOOL_RESULT_ACCEPTED`` row。
    :returns: 同一 session/run/attempt 且 execution 兼容时返回 ``True``。
    """

    return (
        request_row.event_class is EventClass.CANONICAL_FACT
        and request_row.event_type == _EVENT_TYPE_TOOL_CALL_REQUESTED
        and request_row.session_id == result_row.session_id
        and request_row.run_id == result_row.run_id
        and request_row.attempt_id == result_row.attempt_id
        and (
            request_row.execution_id == result_row.execution_id
            or result_row.execution_id is None
        )
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
    )


def _source_projection(
    envelope: AcceptedEvidenceEnvelope | None,
    diagnostics: list[str],
) -> AcceptedToolResultSourceProjection:
    """构造 source 可读投影。

    :param envelope: accepted evidence envelope。
    :param diagnostics: projection 诊断列表，可追加 source 降级原因。
    :returns: source projection。
    """

    if envelope is None:
        return AcceptedToolResultSourceProjection(
            text=ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
            state=AcceptedToolResultSourceState.UNAVAILABLE,
            diagnostic_reason="accepted_evidence_envelope_missing",
        )
    visible_ref_items: list[str] = []
    for ref in (*envelope.source_refs, *envelope.locator_refs):
        ref_text = _readable_ref_text(ref)
        if ref_text is not None:
            visible_ref_items.append(ref_text)
    visible_refs = tuple(visible_ref_items)
    if len(visible_refs) == 0:
        diagnostics.append("business_source_unavailable")
        return AcceptedToolResultSourceProjection(
            text=ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
            state=AcceptedToolResultSourceState.UNAVAILABLE,
            diagnostic_reason="business_source_unavailable",
        )
    return AcceptedToolResultSourceProjection(
        text=_READABLE_SOURCE_SEPARATOR.join(visible_refs),
        state=AcceptedToolResultSourceState.AVAILABLE,
        diagnostic_reason=None,
    )


def _readable_ref_text(ref: OpaqueEvidenceRef) -> str | None:
    """把 opaque ref 转成业务 source 文本。

    :param ref: opaque evidence ref。
    :returns: 可读 source 文本；内部 provenance ref 返回 ``None``。
    """

    normalized_kind = ref.ref_kind.strip().lower()
    if normalized_kind in _INTERNAL_SOURCE_REF_KINDS:
        return None
    return f"{ref.ref_kind}:{ref.ref_id}"


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


def _optional_text(mapping: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选非空文本字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 非空字符串；否则为 ``None``。
    """

    value = mapping.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def projection_result_digest(projection: AcceptedToolResultProjection) -> str | None:
    """计算 projection result_text 的 digest。

    :param projection: accepted tool result projection。
    :returns: result_text JSON digest；无 result_text 时为 ``None``。
    """

    if projection.result_text is None:
        return None
    return sha256_digest_json(projection.result_text)


__all__ = [
    "ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT",
    "ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT",
    "AcceptedToolResultProjection",
    "AcceptedToolResultQueryProjection",
    "AcceptedToolResultQueryState",
    "AcceptedToolResultSourceProjection",
    "AcceptedToolResultSourceState",
    "AcceptedToolResultStatus",
    "project_accepted_tool_result",
]
