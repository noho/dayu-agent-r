"""Compaction request material 输入读取 helper。

本模块只负责从 bounded EventLog range 中读取 Host-neutral evidence /
history material 与已存在 evidence-backed fact refs，供 proactive dispatch
与 reactive engine ingest 构造同语义 ``CompactionRequest``。它不解析财报
source / locator 语义，不写 EventLog，不更新 memory。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host.compact_material import InitialEvidenceMaterial, InitialHistoryMaterial
from dayu.host.compaction import CompactMaterialBlockKind
from dayu.host.context_events import CONTEXT_COMPACTED
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, EventLogStore
from dayu.host.durable.transaction import HostTransaction
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    accepted_evidence_envelope_from_json_value,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.terminal_summary_payload import (
    PayloadSummaryTextPolicy,
    assistant_summary_from_payload,
)

_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES = "evidence_backed_fact_candidates"
_PAYLOAD_FIELD_PRESERVED_FACT_REFS = "preserved_fact_refs"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS = "evidence_backed_fact_refs"
_PAYLOAD_FIELD_CANDIDATE_ID = "candidate_id"
_PAYLOAD_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"
_MEMORY_ITEM_EVIDENCE_BACKED_FACT_PREFIX = "memory-item:evidence_backed_fact"
_READABLE_QUERY_TEXT = "accepted tool query"
_READABLE_SOURCE_TEXT = "accepted tool evidence"
_PAYLOAD_REF_PREFIX = "payload"


@dataclass(frozen=True, slots=True)
class CompactionRequestEvidenceInputs:
    """Compaction request 的 material 输入视图。

    :param history_materials: compact input range 内 history material。
    :param evidence_materials: compact input range 内 evidence material。
    :param evidence_backed_fact_refs: compact input range 内既有 stable fact refs。
    """

    history_materials: tuple[InitialHistoryMaterial, ...]
    evidence_materials: tuple[InitialEvidenceMaterial, ...]
    evidence_backed_fact_refs: tuple[str, ...]


def collect_compaction_request_evidence_inputs(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    start_event_sequence: int,
    end_event_sequence: int,
) -> CompactionRequestEvidenceInputs:
    """从 bounded EventLog range 构造 compaction material 输入。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param session_id: 目标 Session id。
    :param start_event_sequence: compact input 起始 event sequence，闭区间。
    :param end_event_sequence: compact input 结束 event sequence，闭区间。
    :returns: compaction request material 输入。
    :raises HostDurableError: range 非法或 payload 结构损坏时抛出。
    """

    if start_event_sequence <= 0:
        raise HostDurableError("compact input start_event_sequence must be positive")
    if end_event_sequence < start_event_sequence:
        raise HostDurableError("compact input event range is invalid")
    rows = event_log_store.read_events_after(
        transaction,
        start_event_sequence - 1,
        limit=end_event_sequence - start_event_sequence + 1,
    )
    history_materials: list[InitialHistoryMaterial] = []
    evidence_materials: list[InitialEvidenceMaterial] = []
    evidence_backed_fact_refs: list[str] = []
    for row in rows:
        if row.event_sequence > end_event_sequence:
            break
        if row.session_id != session_id:
            continue
        if row.event_class is not EventClass.CANONICAL_FACT:
            continue
        if row.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
            envelopes = _accepted_evidence_envelope_from_event(transaction, row)
            evidence_materials.extend(
                _tool_result_evidence_materials(transaction, row, envelopes)
            )
        elif row.event_type == CONTEXT_COMPACTED:
            evidence_backed_fact_refs.extend(
                _evidence_backed_fact_refs_from_compacted_event(transaction, row)
            )
        elif row.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
            history_materials.extend(_assistant_history_materials(transaction, row))
    return CompactionRequestEvidenceInputs(
        history_materials=tuple(history_materials),
        evidence_materials=_deduplicate_evidence_materials(evidence_materials),
        evidence_backed_fact_refs=_deduplicate_texts(evidence_backed_fact_refs),
    )


def _accepted_evidence_envelope_from_event(
    transaction: HostTransaction, row: EventLogRow
) -> tuple[AcceptedEvidenceEnvelope, ...]:
    """读取单个 ``TOOL_RESULT_ACCEPTED`` 的 accepted evidence envelope。

    :param transaction: 当前 Host transaction。
    :param row: TOOL_RESULT_ACCEPTED EventLog row。
    :returns: 解析出的 envelope tuple；payload 无 envelope 时为空。
    :raises HostDurableError: envelope JSON 结构非法时抛出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    envelope_value = payload.get(_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE)
    if envelope_value is None:
        return ()
    try:
        envelope = accepted_evidence_envelope_from_json_value(envelope_value)
    except ValueError as exc:
        raise HostDurableError("canonical evidence envelope is invalid") from exc
    if envelope.producer_event_ref != row.event_id:
        raise HostDurableError("accepted evidence producer_event_ref mismatch")
    return (envelope,)


def _tool_result_evidence_materials(
    transaction: HostTransaction,
    row: EventLogRow,
    envelopes: tuple[AcceptedEvidenceEnvelope, ...],
) -> tuple[InitialEvidenceMaterial, ...]:
    """读取 ``TOOL_RESULT_ACCEPTED`` raw 工具结果 material。

    :param transaction: 当前 Host transaction。
    :param row: TOOL_RESULT_ACCEPTED EventLog row。
    :param envelopes: 该事件携带的 accepted evidence envelopes。
    :returns: evidence material tuple；无 envelope 时为空。
    :raises HostDurableError: raw 工具结果缺失或结构非法时抛出。
    """

    if len(envelopes) == 0:
        return ()
    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    raw_outcome = payload.get(_PAYLOAD_FIELD_RAW_TOOL_OUTCOME)
    if raw_outcome is None:
        raise HostDurableError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")
    raw_text = canonical_json_dumps(raw_outcome)
    materials: list[InitialEvidenceMaterial] = []
    for envelope in envelopes:
        materials.append(
            InitialEvidenceMaterial(
                canonical_source_ref=envelope.evidence_id,
                accepted_evidence_id=envelope.evidence_id,
                tool_result_event_ref=row.event_id,
                tool_call_event_ref=(
                    envelope.tool_query.tool_call_requested_event_ref or row.event_id
                ),
                readable_tool_name=envelope.tool_name,
                readable_query_text=_READABLE_QUERY_TEXT,
                raw_result_text=raw_text,
                readable_source_text=_READABLE_SOURCE_TEXT,
                payload_refs=_payload_refs(row),
            )
        )
    return tuple(materials)


def _assistant_history_materials(
    transaction: HostTransaction, row: EventLogRow
) -> tuple[InitialHistoryMaterial, ...]:
    """读取 ``RUN_SUCCEEDED`` assistant conclusion history material。

    :param transaction: 当前 Host transaction。
    :param row: RUN_SUCCEEDED EventLog row。
    :returns: history material tuple；无可显示摘要时为空。
    :raises HostDurableError: strict 文本字段非法时抛出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_RUN_SUCCEEDED,
    )
    summary = assistant_summary_from_payload(
        payload,
        text_policy=PayloadSummaryTextPolicy.STRICT_NON_EMPTY,
    )
    if summary is None:
        return ()
    return (
        InitialHistoryMaterial(
            canonical_source_ref=row.event_id,
            text=summary,
            kind=CompactMaterialBlockKind.RAW_ASSISTANT_TURN,
        ),
    )


def _evidence_backed_fact_refs_from_compacted_event(
    transaction: HostTransaction, row: EventLogRow
) -> tuple[str, ...]:
    """读取单个 ``CONTEXT_COMPACTED`` 中已存在 stable fact refs。

    :param transaction: 当前 Host transaction。
    :param row: CONTEXT_COMPACTED EventLog row。
    :returns: evidence-backed fact refs。
    :raises HostDurableError: payload 中相关字段结构非法时抛出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label=CONTEXT_COMPACTED,
    )
    refs: list[str] = []
    preserved = payload.get(_PAYLOAD_FIELD_PRESERVED_FACT_REFS)
    if preserved is not None:
        if not isinstance(preserved, Mapping):
            raise HostDurableError("CONTEXT_COMPACTED preserved_fact_refs is invalid")
        refs.extend(
            _required_text_list(
                preserved,
                _PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS,
                payload_label=CONTEXT_COMPACTED,
            )
        )
    candidates = payload.get(_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES)
    if candidates is None:
        return tuple(refs)
    if not isinstance(candidates, list):
        raise HostDurableError(
            "CONTEXT_COMPACTED evidence_backed_fact_candidates must be list"
        )
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise HostDurableError(
                "CONTEXT_COMPACTED evidence_backed_fact_candidate must be object"
            )
        candidate_id = candidate.get(_PAYLOAD_FIELD_CANDIDATE_ID)
        if not isinstance(candidate_id, str) or candidate_id.strip() == "":
            raise HostDurableError(
                "CONTEXT_COMPACTED evidence_backed_fact candidate_id is invalid"
            )
        refs.append(_derived_evidence_backed_fact_ref(row, candidate_id))
    return tuple(refs)


def _derived_evidence_backed_fact_ref(row: EventLogRow, candidate_id: str) -> str:
    """从 compact event 与 candidate id 派生 stable memory fact ref。

    :param row: CONTEXT_COMPACTED EventLog row。
    :param candidate_id: fact candidate id。
    :returns: 与 memory item id shape 对齐的 stable fact ref。
    """

    return f"{_MEMORY_ITEM_EVIDENCE_BACKED_FACT_PREFIX}:{candidate_id}:{row.event_id}"


def _payload_refs(row: EventLogRow) -> tuple[str, ...]:
    """构造内部 payload refs。

    :param row: EventLog row。
    :returns: payload ref tuple。
    """

    return (f"{_PAYLOAD_REF_PREFIX}:{row.event_id}",)


def _deduplicate_texts(values: list[str]) -> tuple[str, ...]:
    """对字符串列表去重并保持顺序。

    :param values: 原始字符串列表。
    :returns: 去重后的字符串 tuple。
    """

    return tuple(dict.fromkeys(values))


def _deduplicate_evidence_materials(
    values: list[InitialEvidenceMaterial],
) -> tuple[InitialEvidenceMaterial, ...]:
    """按 accepted evidence id 对 evidence material 去重并保持顺序。

    :param values: 原始 evidence materials。
    :returns: 去重后的 evidence materials。
    """

    seen: set[str] = set()
    result: list[InitialEvidenceMaterial] = []
    for value in values:
        if value.accepted_evidence_id in seen:
            continue
        seen.add(value.accepted_evidence_id)
        result.append(value)
    return tuple(result)


def _required_text_list(
    mapping: Mapping[str, JsonValue], field_name: str, *, payload_label: str
) -> tuple[str, ...]:
    """读取 JSON object 中的字符串列表字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: 字符串 tuple。
    :raises HostDurableError: 字段缺失或结构非法时抛出。
    """

    value = mapping.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise HostDurableError(f"{payload_label} {field_name} must be list")
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"{payload_label} {field_name} item is invalid")
        refs.append(item)
    return tuple(refs)


__all__ = [
    "CompactionRequestEvidenceInputs",
    "collect_compaction_request_evidence_inputs",
]
