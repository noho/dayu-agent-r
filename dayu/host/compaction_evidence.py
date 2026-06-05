"""Compaction request material 输入读取 helper。

本模块只负责按 compact material selection 中的 canonical refs 读取
Host-neutral evidence / history material 与已存在 evidence-backed fact refs，
供 proactive dispatch 与 reactive engine ingest 构造同语义
``CompactionRequest``。它不解析财报 source / locator 语义，不写 EventLog，
不更新 memory。
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
from dayu.host.payload_resolution import event_payload_object_for_result_ref
from dayu.host.terminal_summary_payload import (
    PayloadSummaryTextPolicy,
    assistant_summary_from_payload,
)

_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_PAYLOAD_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"
_PAYLOAD_FIELD_RESULT_PREVIEW = "result_preview"
_MEMORY_ITEM_EVIDENCE_BACKED_FACT_PREFIX = "memory-item:evidence_backed_fact"
_PAYLOAD_REF_PREFIX = "payload"
_LOCATOR_REF_SEPARATOR = ", "
_READABLE_SOURCE_EMPTY = "accepted tool evidence"


@dataclass(frozen=True, slots=True)
class SelectedEvidenceBlockRef:
    """Selected compact evidence block 到 canonical tool result 的引用。

    :param block_id: compact material selection 中的稳定 block id。
    :param tool_result_event_ref: 对应 ``TOOL_RESULT_ACCEPTED`` event id。
    """

    block_id: str
    tool_result_event_ref: str

    def __post_init__(self) -> None:
        """校验 selected evidence block ref。

        :returns: ``None``。
        :raises ValueError: 字段为空时抛出。
        """

        _require_non_empty_text(self.block_id, "SelectedEvidenceBlockRef.block_id")
        _require_non_empty_text(
            self.tool_result_event_ref,
            "SelectedEvidenceBlockRef.tool_result_event_ref",
        )


@dataclass(frozen=True, slots=True)
class CompactionRequestEvidenceInputs:
    """Compaction request 的 material 输入视图。

    :param history_materials: selected history material。
    :param evidence_materials: selected evidence material。
    :param evidence_backed_fact_refs: selected 既有 stable fact refs。
    """

    history_materials: tuple[InitialHistoryMaterial, ...]
    evidence_materials: tuple[InitialEvidenceMaterial, ...]
    evidence_backed_fact_refs: tuple[str, ...]


def collect_selected_compaction_request_evidence_inputs(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    selected_evidence_block_refs: tuple[SelectedEvidenceBlockRef, ...],
    selected_history_event_refs: tuple[str, ...] = (),
    selected_fact_event_refs: tuple[str, ...] = (),
) -> CompactionRequestEvidenceInputs:
    """按 selected material refs 构造 compaction evidence 输入。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param session_id: 目标 Session id。
    :param selected_evidence_block_refs: selected evidence block refs。
    :param selected_history_event_refs: selected history event refs。
    :param selected_fact_event_refs: selected compacted fact event refs。
    :returns: compaction request material 输入。
    :raises HostDurableError: refs 指向的事件缺失、跨 Session、类型错误、
        payload 缺失、descriptor digest mismatch 或 raw evidence 不可读时抛出。
    """

    _require_selected_evidence_block_refs(selected_evidence_block_refs)
    _require_string_tuple(selected_history_event_refs, "selected_history_event_refs")
    _require_string_tuple(selected_fact_event_refs, "selected_fact_event_refs")
    evidence_materials: list[InitialEvidenceMaterial] = []
    for block_ref in selected_evidence_block_refs:
        row = _required_event_row(
            transaction,
            event_log_store,
            event_id=block_ref.tool_result_event_ref,
            session_id=session_id,
            expected_event_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
        )
        envelopes = _accepted_evidence_envelope_from_event(transaction, row)
        evidence_materials.extend(
            _tool_result_evidence_materials(transaction, row, envelopes)
        )
    history_materials: list[InitialHistoryMaterial] = []
    for event_ref in selected_history_event_refs:
        row = _required_event_row(
            transaction,
            event_log_store,
            event_id=event_ref,
            session_id=session_id,
            expected_event_type=_EVENT_TYPE_RUN_SUCCEEDED,
        )
        history_materials.extend(_assistant_history_materials(transaction, row))
    fact_refs: list[str] = []
    for event_ref in selected_fact_event_refs:
        row = _required_event_row(
            transaction,
            event_log_store,
            event_id=event_ref,
            session_id=session_id,
            expected_event_type=CONTEXT_COMPACTED,
        )
        fact_refs.extend(_evidence_backed_fact_refs_from_compacted_event(transaction, row))
    return CompactionRequestEvidenceInputs(
        history_materials=tuple(history_materials),
        evidence_materials=_deduplicate_evidence_materials(evidence_materials),
        evidence_backed_fact_refs=_deduplicate_texts(fact_refs),
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
    payload = _accepted_tool_result_payload(transaction, row, envelopes[0])
    _reject_result_preview(payload)
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
                readable_query_text=_readable_query_text(envelope),
                raw_result_text=raw_text,
                readable_source_text=_readable_source_text(envelope),
                payload_refs=_payload_refs(row),
                source_locator_refs=envelope.locator_refs,
            )
        )
    return tuple(materials)


def _accepted_tool_result_payload(
    transaction: HostTransaction,
    row: EventLogRow,
    envelope: AcceptedEvidenceEnvelope,
) -> Mapping[str, JsonValue]:
    """按 accepted envelope result ref 读取工具结果 payload。

    :param transaction: 当前 Host transaction。
    :param row: TOOL_RESULT_ACCEPTED EventLog row。
    :param envelope: accepted evidence envelope。
    :returns: digest-checked payload object。
    :raises HostDurableError: payload ref / digest mismatch 或 payload 非 object 时抛出。
    """

    return event_payload_object_for_result_ref(
        transaction,
        row,
        expected_payload_ref=envelope.result_ref.payload_ref,
        expected_payload_digest=envelope.result_ref.payload_digest,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )


def _reject_result_preview(payload: Mapping[str, JsonValue]) -> None:
    """拒绝旧 ``result_preview`` evidence content 字段。

    :param payload: TOOL_RESULT_ACCEPTED payload。
    :returns: ``None``。
    :raises HostDurableError: payload 中出现 result_preview 时抛出。
    """

    if _PAYLOAD_FIELD_RESULT_PREVIEW in payload:
        raise HostDurableError("TOOL_RESULT_ACCEPTED result_preview is not allowed")


def _readable_query_text(envelope: AcceptedEvidenceEnvelope) -> str:
    """从 envelope metadata 构造可读 query 描述。

    :param envelope: accepted evidence envelope。
    :returns: 不含 result content 的可读 query metadata。
    """

    return f"tool_call_id={envelope.tool_call_id}"


def _readable_source_text(envelope: AcceptedEvidenceEnvelope) -> str:
    """从 opaque source / locator refs 构造可读 source 描述。

    :param envelope: accepted evidence envelope。
    :returns: 不含 result content 的可读 source / locator metadata。
    """

    refs: list[str] = []
    for ref in (*envelope.source_refs, *envelope.locator_refs):
        refs.append(f"{ref.ref_kind}:{ref.ref_id}")
    if len(refs) == 0:
        return _READABLE_SOURCE_EMPTY
    return _LOCATOR_REF_SEPARATOR.join(refs)


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
            kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
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
    candidate = _required_mapping(
        payload,
        _PAYLOAD_FIELD_ACCEPTED_CANDIDATE,
        payload_label=CONTEXT_COMPACTED,
    )
    facts = _required_mapping_list(
        candidate,
        _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS,
        payload_label=CONTEXT_COMPACTED,
    )
    refs: list[str] = []
    for index, _fact in enumerate(facts):
        refs.append(_derived_evidence_backed_fact_ref(row, f"vnext-fact-{index + 1}"))
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

    if row.payload_ref is not None:
        return (row.payload_ref,)
    return (f"{_PAYLOAD_REF_PREFIX}:{row.event_id}",)


def _required_event_row(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    event_id: str,
    session_id: str,
    expected_event_type: str,
) -> EventLogRow:
    """读取并校验 selected ref 指向的 EventLog row。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param event_id: selected event id。
    :param session_id: 目标 Session id。
    :param expected_event_type: 期望 event type。
    :returns: EventLog row。
    :raises HostDurableError: 事件缺失、跨 Session、非 canonical fact 或类型不匹配时抛出。
    """

    _require_non_empty_text(event_id, "event_id")
    row = event_log_store.read_event_by_id(transaction, event_id)
    if row is None:
        raise HostDurableError("selected evidence event is missing")
    if row.session_id != session_id:
        raise HostDurableError("selected evidence event session mismatch")
    if row.event_class is not EventClass.CANONICAL_FACT:
        raise HostDurableError("selected evidence event is not canonical fact")
    if row.event_type != expected_event_type:
        raise HostDurableError("selected evidence event type mismatch")
    return row


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


def _required_mapping(
    mapping: Mapping[str, JsonValue], field_name: str, *, payload_label: str
) -> Mapping[str, JsonValue]:
    """读取 JSON object 中的必填 object 字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: JSON object。
    :raises HostDurableError: 字段缺失或结构非法时抛出。
    """

    value = mapping.get(field_name)
    if not isinstance(value, Mapping):
        raise HostDurableError(f"{payload_label} {field_name} must be object")
    return value


def _required_mapping_list(
    mapping: Mapping[str, JsonValue], field_name: str, *, payload_label: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 JSON object 中的必填 object array 字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: JSON object tuple。
    :raises HostDurableError: 字段缺失或结构非法时抛出。
    """

    value = mapping.get(field_name)
    if not isinstance(value, list):
        raise HostDurableError(f"{payload_label} {field_name} must be list")
    result: list[Mapping[str, JsonValue]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise HostDurableError(
                f"{payload_label} {field_name}[{index}] must be object"
            )
        result.append(item)
    return tuple(result)


def _require_selected_evidence_block_refs(
    value: tuple[SelectedEvidenceBlockRef, ...],
) -> None:
    """校验 selected evidence block refs tuple。

    :param value: 待校验 refs。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError("selected_evidence_block_refs must be tuple")
    for item in value:
        if not isinstance(item, SelectedEvidenceBlockRef):
            raise TypeError(
                "selected_evidence_block_refs items must be SelectedEvidenceBlockRef"
            )


def _require_string_tuple(value: tuple[str, ...], field_name: str) -> None:
    """校验字符串 tuple。

    :param value: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 字符串为空时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        _require_non_empty_text(item, field_name)


def _require_non_empty_text(value: str, field_name: str) -> None:
    """校验非空字符串。

    :param value: 待校验字符串。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字符串为空时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


__all__ = [
    "CompactionRequestEvidenceInputs",
    "SelectedEvidenceBlockRef",
    "collect_selected_compaction_request_evidence_inputs",
]
