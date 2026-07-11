"""Host 测试专用 deterministic vNext context compactor。

本模块位于 tests 包下，只允许测试显式注入一个稳定 compactor。生产代码
不得导入 tests helper；真实生产装配必须显式提供 ``ContextCompactor``。
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.host.compact_material import conversation_compact_input_vnext_from_material_pack
from dayu.host.compaction import (
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    CompactCandidateDiagnosticVNext,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
    ContextCompactor,
    EvidenceBackedFactCandidateVNext,
    EvidenceReadableItemVNext,
    ForwardIntentCandidateVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    ReferenceContinuityCandidateVNext,
    ReferenceContinuityReasonVNext,
    SessionSummaryCandidateVNext,
)

_FAKE_COMPACTION_SYSTEM_PROMPT = "Deterministic fake context compactor."


class FakeContextCompactor(ContextCompactor):
    """Deterministic vNext context compactor。

    该实现只根据 typed request 构造稳定 vNext candidate，不调用 LLM，不访问
    外部状态，不应作为生产默认 compactor。
    """

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """生成 deterministic vNext compaction output。

        :param request: Host 构造的 compaction 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: deterministic vNext compact output。
        :raises TypeError: ``request`` 类型非法时抛出。
        :raises RuntimeError: token 已取消时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        compact_input = conversation_compact_input_vnext_from_material_pack(
            request.material_pack
        )
        return await FakeConversationCompactorVNext().compact(
            compact_input,
            cancellation_token,
        )


class FakeConversationCompactorVNext:
    """测试专用 deterministic vNext context compactor。"""

    async def compact(
        self,
        request: ConversationCompactInputVNext,
        cancellation_token: CancellationToken,
    ) -> ConversationCompactOutputVNext:
        """生成 deterministic vNext compact output。

        :param request: vNext compactor input。
        :param cancellation_token: Host 注入的取消 token。
        :returns: deterministic vNext compact output。
        :raises TypeError: request 类型非法时抛出。
        :raises RuntimeError: token 已取消时抛出。
        """

        if not isinstance(request, ConversationCompactInputVNext):
            raise TypeError("request must be ConversationCompactInputVNext")
        if cancellation_token.is_cancelled():
            raise RuntimeError("compaction cancelled")
        return ConversationCompactOutputVNext(
            schema_version=CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
            session_summary=_fake_session_summary_vnext(request),
            evidence_backed_facts=_fake_fact_candidates_vnext(request),
            answer_anchors=_fake_answer_anchors_vnext(request),
            forward_intents=_fake_forward_intents_vnext(request),
            reference_continuity_items=_fake_reference_items_vnext(request),
            diagnostics=_fake_diagnostics_vnext(request),
        )


def fake_compaction_proposal_from_material_json(material_json: Mapping[str, JsonValue]) -> str:
    """从 vNext material JSON 生成 deterministic LLM strict JSON proposal。

    :param material_json: vNext compact input JSON。
    :returns: vNext compact output strict JSON 文本。
    :raises TypeError: material_json 结构非法时抛出。
    """

    evidence_items = _evidence_items(material_json)
    answer_items = _answer_items(material_json)
    trace_labels = _source_labels(material_json, "trace_material")
    previous_labels = _previous_labels(material_json)
    answer_labels = tuple(item.source_label for item in answer_items)
    summary_labels = trace_labels + tuple(
        item.source_label for item in evidence_items
    ) + answer_labels
    continuity_labels = previous_labels + trace_labels + answer_labels
    if len(summary_labels) == 0:
        summary_json: JsonValue = None
    else:
        summary_json = {
            "summary_text": "Deterministic compact summary.",
            "source_labels": list(summary_labels),
        }
    proposal = {
        "schema_version": CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
        "session_summary": summary_json,
        "evidence_backed_facts": [
            {
                "claim_text": f"Canonical evidence material: {item.response_text}",
                "evidence_labels": [item.source_label],
                "source_labels": [item.source_label],
            }
            for item in evidence_items
        ],
        "answer_anchors": [
            {
                "anchor_title": "Previous answer",
                "anchor_items": [{"display_text": item.answer_text, "ordinal": None}],
                "answer_source_labels": [item.source_label],
            }
            for item in answer_items
        ],
        "forward_intents": [
            {
                "intent_type": ForwardIntentTypeVNext.NEXT_STEP_NOTE.value,
                "text": "Continue current user-visible analysis.",
                "status": ForwardIntentStatusVNext.OPEN.value,
                "source_labels": [continuity_labels[0]],
            }
        ]
        if len(continuity_labels) > 0
        else [],
        "reference_continuity_items": [
            {
                "text": "Keep the nearest prior context for local references.",
                "reason": ReferenceContinuityReasonVNext.LOCAL_REFERENCE.value,
                "source_labels": [continuity_labels[0]],
            }
        ]
        if len(continuity_labels) > 0
        else [],
        "diagnostics": [],
    }
    return json.dumps(proposal, ensure_ascii=False, sort_keys=True)


def _fake_session_summary_vnext(request: ConversationCompactInputVNext) -> SessionSummaryCandidateVNext | None:
    """构造 fake vNext session summary。

    :param request: vNext compactor input。
    :returns: session summary；无可引用 material 时返回 ``None``。
    """

    labels = _summary_labels_vnext(request)
    if len(labels) == 0:
        return None
    return SessionSummaryCandidateVNext(
        summary_text=f"Deterministic compact summary for {request.current_input_anchor.text}",
        source_labels=labels,
    )


def _fake_fact_candidates_vnext(
    request: ConversationCompactInputVNext,
) -> tuple[EvidenceBackedFactCandidateVNext, ...]:
    """构造 fake vNext fact candidates。

    :param request: vNext compactor input。
    :returns: fact candidate tuple。
    """

    candidates: list[EvidenceBackedFactCandidateVNext] = []
    for item in request.evidence_material:
        candidates.append(
            EvidenceBackedFactCandidateVNext(
                claim_text=f"Canonical evidence material: {item.response_text}",
                evidence_labels=(item.source_label,),
                source_labels=(item.source_label,),
            )
        )
    return tuple(candidates)


def _fake_answer_anchors_vnext(
    request: ConversationCompactInputVNext,
) -> tuple[AnswerAnchorCandidateVNext, ...]:
    """构造 fake vNext answer anchors。

    :param request: vNext compactor input。
    :returns: answer anchor tuple。
    """

    anchors: list[AnswerAnchorCandidateVNext] = []
    for item in request.answer_material:
        anchors.append(
            AnswerAnchorCandidateVNext(
                anchor_title="Previous answer",
                anchor_items=(AnswerAnchorChildVNext(display_text=item.answer_text),),
                answer_source_labels=(item.source_label,),
            )
        )
    return tuple(anchors)


def _fake_forward_intents_vnext(
    request: ConversationCompactInputVNext,
) -> tuple[ForwardIntentCandidateVNext, ...]:
    """构造 fake vNext forward intents。

    :param request: vNext compactor input。
    :returns: forward intent tuple。
    """

    labels = _continuity_labels_vnext(request)
    if len(labels) == 0:
        return ()
    return (
        ForwardIntentCandidateVNext(
            intent_type=ForwardIntentTypeVNext.NEXT_STEP_NOTE,
            text="Continue current user-visible analysis.",
            status=ForwardIntentStatusVNext.OPEN,
            source_labels=(labels[0],),
        ),
    )


def _fake_reference_items_vnext(
    request: ConversationCompactInputVNext,
) -> tuple[ReferenceContinuityCandidateVNext, ...]:
    """构造 fake vNext reference continuity items。

    :param request: vNext compactor input。
    :returns: reference continuity tuple。
    """

    labels = _continuity_labels_vnext(request)
    if len(labels) == 0:
        return ()
    return (
        ReferenceContinuityCandidateVNext(
            text="Keep the nearest prior context for local references.",
            reason=ReferenceContinuityReasonVNext.LOCAL_REFERENCE,
            source_labels=(labels[0],),
        ),
    )


def _fake_diagnostics_vnext(
    request: ConversationCompactInputVNext,
) -> tuple[CompactCandidateDiagnosticVNext, ...]:
    """构造 fake vNext diagnostics。

    :param request: vNext compactor input。
    :returns: diagnostics tuple。
    """

    del request
    return ()


def _summary_labels_vnext(request: ConversationCompactInputVNext) -> tuple[str, ...]:
    """返回 fake vNext 可用于 summary 的 labels。

    :param request: vNext compactor input。
    :returns: 本次新材料的 prompt-local labels。
    """

    labels: list[str] = []
    labels.extend(item.source_label for item in request.trace_material)
    labels.extend(item.source_label for item in request.evidence_material)
    labels.extend(item.source_label for item in request.answer_material)
    return tuple(labels)


def _continuity_labels_vnext(request: ConversationCompactInputVNext) -> tuple[str, ...]:
    """返回 fake vNext 可用于 forward / reference continuity 的 labels。

    :param request: vNext compactor input。
    :returns: prompt-local labels。
    """

    labels: list[str] = []
    if request.previous_compacted_view is not None:
        labels.extend(item.source_label for item in request.previous_compacted_view.evidence_backed_facts)
        labels.extend(item.source_label for item in request.previous_compacted_view.answer_anchors)
        labels.extend(item.source_label for item in request.previous_compacted_view.forward_intents)
        labels.extend(item.source_label for item in request.previous_compacted_view.reference_continuity_items)
    labels.extend(item.source_label for item in request.trace_material)
    labels.extend(item.source_label for item in request.answer_material)
    return tuple(labels)


def _evidence_items(material_json: Mapping[str, JsonValue]) -> tuple[EvidenceReadableItemVNext, ...]:
    """从 vNext material JSON 读取 evidence material。

    :param material_json: vNext material JSON。
    :returns: evidence readable items。
    :raises TypeError: 字段结构非法时抛出。
    """

    values = _json_list_or_empty(material_json, "evidence_material")
    items: list[EvidenceReadableItemVNext] = []
    for index, item in enumerate(values):
        data = _json_object(item, field_name=f"evidence_material[{index}]")
        items.append(
            EvidenceReadableItemVNext(
                source_label=_json_label(data),
                tool_name=_json_string(data, "tool_name"),
                query_text=_json_optional_string(data, "query_text"),
                response_text=_json_string_alias(data, "response_text", "result_text"),
                source_note=_json_optional_string_alias(data, "source_note", "source_text"),
            )
        )
    return tuple(items)


def _answer_items(material_json: Mapping[str, JsonValue]) -> tuple[_AnswerProposalItem, ...]:
    """从 vNext material JSON 读取 answer material。

    :param material_json: vNext material JSON。
    :returns: answer proposal items。
    :raises TypeError: 字段结构非法时抛出。
    """

    values = _json_list_or_empty(material_json, "answer_material")
    items: list[_AnswerProposalItem] = []
    for index, item in enumerate(values):
        data = _json_object(item, field_name=f"answer_material[{index}]")
        items.append(
            _AnswerProposalItem(
                source_label=_json_label(data),
                answer_text=_json_string(data, "answer_text"),
            )
        )
    return tuple(items)


def _source_labels(material_json: Mapping[str, JsonValue], field_name: str) -> tuple[str, ...]:
    """读取 vNext material section source labels。

    :param material_json: vNext material JSON。
    :param field_name: section 字段名。
    :returns: source label tuple。
    """

    labels: list[str] = []
    for index, item in enumerate(_json_list(material_json, field_name)):
        data = _json_object(item, field_name=f"{field_name}[{index}]")
        labels.append(_json_string(data, "source_label"))
    return tuple(labels)


def _previous_labels(material_json: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """读取 previous compacted view 中的 source labels。

    :param material_json: vNext material JSON。
    :returns: source label tuple。
    """

    value = material_json.get("previous_compacted_view")
    if value is None:
        return ()
    if isinstance(value, list) and len(value) == 0:
        return ()
    data = _json_object(value, field_name="previous_compacted_view")
    labels: list[str] = []
    for section_name in (
        "evidence_backed_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity_items",
    ):
        labels.extend(_source_labels(data, section_name))
    return tuple(labels)


class _AnswerProposalItem:
    """fake answer proposal item。"""

    def __init__(self, *, source_label: str, answer_text: str) -> None:
        """初始化 answer proposal item。

        :param source_label: prompt-local source label。
        :param answer_text: answer material 文本。
        :returns: ``None``。
        """

        self.source_label = source_label
        self.answer_text = answer_text


def _json_list(source: Mapping[str, JsonValue], field_name: str) -> list[JsonValue]:
    """读取 JSON array 字段。

    :param source: JSON object。
    :param field_name: 字段名。
    :returns: JSON array。
    :raises TypeError: 字段不是 array 时抛出。
    """

    value = source.get(field_name)
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be list")
    return value


def _json_list_or_empty(
    source: Mapping[str, JsonValue], field_name: str
) -> list[JsonValue]:
    """读取可省略 JSON array 字段。

    :param source: JSON object。
    :param field_name: 字段名。
    :returns: JSON array；字段不存在时返回空列表。
    :raises TypeError: 字段存在但不是 array 时抛出。
    """

    if field_name not in source:
        return []
    return _json_list(source, field_name)


def _json_object(value: JsonValue, *, field_name: str) -> Mapping[str, JsonValue]:
    """校验 JSON object。

    :param value: JSON value。
    :param field_name: 字段名。
    :returns: 已完成 key / value 校验的 JSON object。
    :raises TypeError: value 不是 object，或 object 内存在非 JSON 值时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be object")
    return _validated_json_object(value, field_name=field_name)


def _validated_json_object(
    value: Mapping[str, JsonValue], *, field_name: str
) -> Mapping[str, JsonValue]:
    """递归校验 JSON object 的 key 与 value。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 复制后的 JSON object。
    :raises TypeError: key 不是字符串，或 value 不是 JSON 值时抛出。
    """

    validated: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} key must be string")
        validated[key] = _validated_json_value(item, field_name=f"{field_name}.{key}")
    return validated


def _validated_json_value(value: JsonValue, *, field_name: str) -> JsonValue:
    """递归校验 JSON value。

    :param value: JSON value。
    :param field_name: 字段名。
    :returns: 已校验的 JSON value。
    :raises TypeError: value 不是 JSON 标量、数组或对象时抛出。
    """

    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [
            _validated_json_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        return _validated_json_object(value, field_name=field_name)
    raise TypeError(f"{field_name} must be JSON value")


def _json_string(source: Mapping[str, JsonValue], field_name: str) -> str:
    """读取非空 JSON string 字段。

    :param source: JSON object。
    :param field_name: 字段名。
    :returns: 字符串。
    :raises TypeError: 字段不是 string 时抛出。
    """

    value = source.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise TypeError(f"{field_name} must be non-empty string")
    return value


def _json_label(source: Mapping[str, JsonValue]) -> str:
    """读取 typed 或 LLM-facing material label。

    :param source: JSON object。
    :returns: prompt-local label。
    :raises TypeError: label 字段不存在或非法时抛出。
    """

    value = source.get("source_label")
    if isinstance(value, str) and value.strip() != "":
        return value
    return _json_string(source, "label")


def _json_string_alias(
    source: Mapping[str, JsonValue], first_field_name: str, second_field_name: str
) -> str:
    """按优先级读取两个可能字段名下的非空 JSON string。

    :param source: JSON object。
    :param first_field_name: 首选字段名。
    :param second_field_name: 备选字段名。
    :returns: 字符串。
    :raises TypeError: 两个字段都不存在或非法时抛出。
    """

    value = source.get(first_field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return _json_string(source, second_field_name)


def _json_optional_string_alias(
    source: Mapping[str, JsonValue], first_field_name: str, second_field_name: str
) -> str | None:
    """按优先级读取两个可能字段名下的 optional JSON string。

    :param source: JSON object。
    :param first_field_name: 首选字段名。
    :param second_field_name: 备选字段名。
    :returns: 字符串或 ``None``。
    :raises TypeError: 字段存在但非法时抛出。
    """

    value = source.get(first_field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return _json_optional_string(source, second_field_name)


def _json_optional_string(source: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选 JSON string 字段。

    :param source: JSON object。
    :param field_name: 字段名。
    :returns: 字符串或 ``None``。
    :raises TypeError: 字段不是 string / null 时抛出。
    """

    value = source.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise TypeError(f"{field_name} must be non-empty string or null")
    return value


__all__ = ["FakeContextCompactor", "FakeConversationCompactorVNext", "fake_compaction_proposal_from_material_json"]
