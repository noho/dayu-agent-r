"""Compaction request evidence 输入读取 helper。

本模块只负责从 bounded EventLog range 中读取 Host-neutral accepted
evidence envelopes 与已存在 evidence-backed fact refs，供 proactive
dispatch 与 reactive engine ingest 构造同语义 ``CompactionRequest``。
它不解析财报 source / locator 语义，不写 EventLog，不更新 memory。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host.context_events import CONTEXT_COMPACTED
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, EventLogStore
from dayu.host.durable.transaction import HostTransaction
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    accepted_evidence_envelope_from_json_value,
)
from dayu.host.payload_resolution import event_payload_object

_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES = "evidence_backed_fact_candidates"
_PAYLOAD_FIELD_PRESERVED_FACT_REFS = "preserved_fact_refs"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS = "evidence_backed_fact_refs"
_PAYLOAD_FIELD_CANDIDATE_ID = "candidate_id"
_MEMORY_ITEM_EVIDENCE_BACKED_FACT_PREFIX = "memory-item:evidence_backed_fact"


@dataclass(frozen=True, slots=True)
class CompactionRequestEvidenceInputs:
    """Compaction request 的 evidence 输入视图。

    :param accepted_evidence_envelopes: compact input range 内 accepted evidence 信封。
    :param evidence_backed_fact_refs: compact input range 内既有 stable fact refs。
    """

    accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]
    evidence_backed_fact_refs: tuple[str, ...]


def collect_compaction_request_evidence_inputs(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    start_event_sequence: int,
    end_event_sequence: int,
) -> CompactionRequestEvidenceInputs:
    """从 bounded EventLog range 构造 compaction evidence 输入。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param session_id: 目标 Session id。
    :param start_event_sequence: compact input 起始 event sequence，闭区间。
    :param end_event_sequence: compact input 结束 event sequence，闭区间。
    :returns: compaction request evidence 输入。
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
    accepted_evidence: list[AcceptedEvidenceEnvelope] = []
    evidence_backed_fact_refs: list[str] = []
    for row in rows:
        if row.event_sequence > end_event_sequence:
            break
        if row.session_id != session_id:
            continue
        if row.event_class is not EventClass.CANONICAL_FACT:
            continue
        if row.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
            accepted_evidence.extend(
                _accepted_evidence_envelope_from_event(transaction, row)
            )
        elif row.event_type == CONTEXT_COMPACTED:
            evidence_backed_fact_refs.extend(
                _evidence_backed_fact_refs_from_compacted_event(transaction, row)
            )
    return CompactionRequestEvidenceInputs(
        accepted_evidence_envelopes=_deduplicate_accepted_evidence(accepted_evidence),
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
        raise HostDurableError("accepted evidence envelope is invalid") from exc
    if envelope.producer_event_ref != row.event_id:
        raise HostDurableError("accepted evidence producer_event_ref mismatch")
    return (envelope,)


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


def _deduplicate_accepted_evidence(
    envelopes: list[AcceptedEvidenceEnvelope],
) -> tuple[AcceptedEvidenceEnvelope, ...]:
    """按 evidence id 对 accepted evidence envelope 去重并保持顺序。

    :param envelopes: 原始 accepted evidence envelopes。
    :returns: 去重后的 envelopes。
    """

    seen: set[str] = set()
    unique: list[AcceptedEvidenceEnvelope] = []
    for envelope in envelopes:
        if envelope.evidence_id in seen:
            continue
        seen.add(envelope.evidence_id)
        unique.append(envelope)
    return tuple(unique)


def _deduplicate_texts(values: list[str]) -> tuple[str, ...]:
    """对字符串列表去重并保持顺序。

    :param values: 原始字符串列表。
    :returns: 去重后的字符串 tuple。
    """

    return tuple(dict.fromkeys(values))


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
