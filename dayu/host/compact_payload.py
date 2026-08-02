"""Host vNext compact payload 解析辅助。

本模块集中承载 ``CONTEXT_COMPACTED`` vNext payload 中稳定字段的严格读取
逻辑，供 dispatch governance 复用，避免 operation path 继续解释旧
preserved refs payload。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    COMPACT_OUTPUT_SCHEMA_V2,
    CompactAnswerAnchorV2,
    CompactCandidateDiagnosticV2,
    CompactDropReasonV2,
    CompactExplicitDropV2,
    CompactExplicitlyDroppedCoverageV2,
    CompactRepresentedCoverageV2,
    CompactRepresentedSourceV2,
    CompactSemanticSectionV2,
    CompactSourceBoundaryEntryV2,
    CompactSourceKindV2,
    CompactAcceptedTruthV2,
    CompactionRequest,
    CompactCandidateV2,
    CompactEvidenceFactV2,
    CompactForwardIntentV2,
    CompactForwardIntentStatusV2,
    CompactReferenceContinuityV2,
    CompactSessionSummaryV2,
)
from dayu.host.durable.codec import is_sha256_digest

COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT = "application/vnd.dayu.context-compact+json"
COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"
COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 3
COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP = "conversation_memory_projection_catchup"
_COMPACT_ARTIFACT_REF_PREFIX = "compact-artifact:"
_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_FIELD_ACCEPTED_CANDIDATE_DIGEST = "accepted_candidate_digest"
_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_FIELD_SOURCE_BOUNDARY_REFS = "source_boundary_refs"
_FIELD_SOURCE_BOUNDARY = "source_boundary"
_FIELD_REPRESENTED_COVERAGE = "represented_coverage"
_FIELD_EXPLICITLY_DROPPED_COVERAGE = "explicitly_dropped_coverage"
_FIELD_SCHEMA = "schema"
_FIELD_SESSION_SUMMARY = "session_summary"
_FIELD_SUMMARY_TEXT = "text"
_FIELD_SOURCE_LABELS = "source_labels"
_FIELD_EVIDENCE_FACTS = "evidence_facts"
_FIELD_CLAIM = "claim"
_FIELD_SUPPORT_LABELS = "support_labels"
_FIELD_CONTEXT_LABELS = "context_labels"
_FIELD_ANSWER_ANCHORS = "answer_anchors"
_FIELD_TITLE = "title"
_FIELD_DETAIL = "detail"
_FIELD_FORWARD_INTENTS = "forward_intents"
_FIELD_INTENT_TYPE = "intent_type"
_FIELD_TEXT = "text"
_FIELD_STATUS = "status"
_FIELD_REFERENCE_CONTINUITY = "reference_continuity"
_FIELD_REASON = "reason"
_FIELD_DIAGNOSTICS = "diagnostics"
_FIELD_CODE = "code"
_FIELD_MESSAGE = "message"
_FIELD_EXPLICITLY_DROPPED_SOURCES = "explicitly_dropped_sources"
_FIELD_SOURCE_LABEL = "source_label"
_SHA256_PREFIX = "sha256:"

_CANDIDATE_FIELDS = frozenset(
    (
        _FIELD_SCHEMA,
        _FIELD_SESSION_SUMMARY,
        _FIELD_EVIDENCE_FACTS,
        _FIELD_ANSWER_ANCHORS,
        _FIELD_FORWARD_INTENTS,
        _FIELD_REFERENCE_CONTINUITY,
        _FIELD_DIAGNOSTICS,
        _FIELD_EXPLICITLY_DROPPED_SOURCES,
    )
)
_SUMMARY_FIELDS = frozenset((_FIELD_SUMMARY_TEXT, _FIELD_SOURCE_LABELS))
_FACT_FIELDS = frozenset(
    (
        _FIELD_CLAIM,
        _FIELD_SUPPORT_LABELS,
        _FIELD_CONTEXT_LABELS,
    )
)
_ANCHOR_FIELDS = frozenset((_FIELD_TITLE, _FIELD_DETAIL, _FIELD_SOURCE_LABELS))
_FORWARD_INTENT_FIELDS = frozenset((_FIELD_INTENT_TYPE, _FIELD_TEXT, _FIELD_STATUS, _FIELD_SOURCE_LABELS))
_REFERENCE_FIELDS = frozenset((_FIELD_TEXT, _FIELD_REASON, _FIELD_SOURCE_LABELS))
_DIAGNOSTIC_FIELDS = frozenset((_FIELD_CODE, _FIELD_MESSAGE, _FIELD_SOURCE_LABELS))
_DROP_FIELDS = frozenset((_FIELD_SOURCE_LABEL, _FIELD_REASON))


@dataclass(frozen=True, slots=True)
class ContextCompactedSemanticPayload:
    """已持久化 ``CONTEXT_COMPACTED`` 的窄 typed semantic view。

    :param accepted_candidate: 严格恢复的 accepted candidate。
    :param accepted_candidate_digest: candidate canonical digest。
    :param accepted_evidence_mapping_refs: candidate 绑定的 accepted evidence refs。
    :param compact_artifact_ref: compact artifact ref。
    :param current_input_ref: 本次 compact 所属 current input ref。
    :param source_boundary: committed root typed source boundary。
    :param represented_coverage: Host 派生的 represented coverage。
    :param explicitly_dropped_coverage: Host 验证的 drop coverage。
    """

    accepted_candidate: CompactCandidateV2
    accepted_candidate_digest: str
    accepted_evidence_mapping_refs: tuple[str, ...]
    compact_artifact_ref: str
    current_input_ref: str
    source_boundary: tuple[CompactSourceBoundaryEntryV2, ...]
    represented_coverage: CompactRepresentedCoverageV2
    explicitly_dropped_coverage: CompactExplicitlyDroppedCoverageV2

    def __post_init__(self) -> None:
        """校验 typed semantic view 的内部一致性。

        :returns: ``None``。
        :raises TypeError: candidate 或 refs tuple 类型非法时抛出。
        :raises ValueError: digest、ref 或 candidate digest 不一致时抛出。
        """

        if not isinstance(self.accepted_candidate, CompactCandidateV2):
            raise TypeError("accepted_candidate must be CompactCandidateV2")
        if not is_sha256_digest(self.accepted_candidate_digest):
            raise ValueError("accepted_candidate_digest must be sha256 digest")
        if self.accepted_candidate_digest != self.accepted_candidate.digest():
            raise ValueError("accepted_candidate_digest mismatch")
        _require_runtime_text_tuple(
            self.accepted_evidence_mapping_refs,
            field_name=_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
        )
        _require_runtime_text(
            self.compact_artifact_ref,
            field_name=_FIELD_COMPACT_ARTIFACT_REF,
        )
        _require_runtime_text(
            self.current_input_ref,
            field_name="current_input_ref",
        )
        _validate_committed_coverage(self)

    @property
    def compacted_source_refs(self) -> tuple[str, ...]:
        """从 committed typed boundary 与 coverage 派生 canonical refs。

        :returns: 按 root boundary 顺序去重的 covered source refs。
        """

        covered_labels = frozenset(
            (
                *self.represented_coverage.source_labels,
                *self.explicitly_dropped_coverage.source_labels,
            )
        )
        return tuple(
            dict.fromkeys(
                source_ref
                for entry in self.source_boundary
                if entry.source_label in covered_labels
                for source_ref in entry.source_refs
            )
        )


def parse_context_compacted_semantic_payload(
    payload: Mapping[str, JsonValue],
) -> ContextCompactedSemanticPayload:
    """严格解析已持久化 ``CONTEXT_COMPACTED`` semantic payload。

    :param payload: 当前 schema 的 canonical compacted payload。
    :returns: 唯一 typed semantic view。
    :raises ValueError: shape、enum、文本、ordinal、digest 或 ref 非法时抛出。
    """

    candidate_mapping = _required_mapping(payload, _FIELD_ACCEPTED_CANDIDATE)
    candidate = _parse_persisted_candidate(candidate_mapping)
    candidate_digest = _required_text(payload, _FIELD_ACCEPTED_CANDIDATE_DIGEST)
    source_refs = _required_unique_text_list(
        payload,
        _FIELD_SOURCE_BOUNDARY_REFS,
        path=_FIELD_SOURCE_BOUNDARY_REFS,
    )
    if len(source_refs) == 0:
        raise ValueError("source_boundary_refs must include current_input_ref")
    semantics = ContextCompactedSemanticPayload(
        accepted_candidate=candidate,
        accepted_candidate_digest=candidate_digest,
        accepted_evidence_mapping_refs=_required_text_list(
            payload,
            _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
            path=_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
        ),
        compact_artifact_ref=_required_text(payload, _FIELD_COMPACT_ARTIFACT_REF),
        current_input_ref=source_refs[0],
        source_boundary=_parse_source_boundary(payload),
        represented_coverage=_parse_represented_coverage(payload),
        explicitly_dropped_coverage=_parse_dropped_coverage(payload),
    )
    if source_refs != (semantics.current_input_ref, *semantics.compacted_source_refs):
        raise ValueError("source_boundary_refs must equal committed derived coverage")
    return semantics


def accepted_compact_business_texts(
    candidate: CompactCandidateV2,
) -> tuple[str, ...]:
    """返回 accepted compact 后普通 dispatch 会消费的业务文本。

    :param candidate: typed accepted compact candidate。
    :returns: 按 memory / ordinary RunInput 业务投影顺序排列的文本 tuple。
    :raises TypeError: candidate 类型非法时抛出。
    """

    if not isinstance(candidate, CompactCandidateV2):
        raise TypeError("candidate must be CompactCandidateV2")
    texts: list[str] = []
    if candidate.session_summary is not None:
        texts.append(candidate.session_summary.text)
    texts.extend(fact.claim for fact in candidate.evidence_facts)
    for anchor in candidate.answer_anchors:
        texts.append(anchor.title)
        texts.append(anchor.detail)
    texts.extend(intent.text for intent in candidate.forward_intents)
    texts.extend(item.text for item in candidate.reference_continuity)
    return tuple(texts)


def _parse_source_boundary(
    payload: Mapping[str, JsonValue],
) -> tuple[CompactSourceBoundaryEntryV2, ...]:
    """严格恢复 committed root source boundary。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: typed boundary tuple。
    :raises ValueError: shape、kind、label 或 refs 非法时抛出。
    """

    items = _required_mapping_list(
        payload,
        _FIELD_SOURCE_BOUNDARY,
        path=_FIELD_SOURCE_BOUNDARY,
    )
    result: list[CompactSourceBoundaryEntryV2] = []
    for index, item in enumerate(items):
        path = f"{_FIELD_SOURCE_BOUNDARY}[{index}]"
        _require_exact_fields(
            item,
            frozenset(("source_label", "source_kind", "source_refs", "readable_text")),
            path=path,
        )
        result.append(
            CompactSourceBoundaryEntryV2(
                source_label=_required_text(item, "source_label"),
                source_kind=CompactSourceKindV2(_required_text(item, "source_kind")),
                source_refs=_required_unique_text_list(
                    item,
                    "source_refs",
                    path=f"{path}.source_refs",
                ),
                readable_text=_required_text(item, "readable_text"),
            )
        )
    labels = tuple(entry.source_label for entry in result)
    if len(set(labels)) != len(labels):
        raise ValueError("source_boundary labels must be unique")
    return tuple(result)


def _parse_represented_coverage(
    payload: Mapping[str, JsonValue],
) -> CompactRepresentedCoverageV2:
    """严格恢复 committed represented coverage。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: typed represented coverage。
    :raises ValueError: shape、section 或 label 非法时抛出。
    """

    coverage = _required_mapping(payload, _FIELD_REPRESENTED_COVERAGE)
    _require_exact_fields(
        coverage,
        frozenset(("sources",)),
        path=_FIELD_REPRESENTED_COVERAGE,
    )
    sources = _required_mapping_list(
        coverage,
        "sources",
        path=f"{_FIELD_REPRESENTED_COVERAGE}.sources",
    )
    result: list[CompactRepresentedSourceV2] = []
    for index, item in enumerate(sources):
        path = f"{_FIELD_REPRESENTED_COVERAGE}.sources[{index}]"
        _require_exact_fields(
            item,
            frozenset(("source_label", "sections")),
            path=path,
        )
        result.append(
            CompactRepresentedSourceV2(
                source_label=_required_text(item, "source_label"),
                sections=tuple(
                    CompactSemanticSectionV2(value)
                    for value in _required_unique_text_list(
                        item,
                        "sections",
                        path=f"{path}.sections",
                    )
                ),
            )
        )
    return CompactRepresentedCoverageV2(sources=tuple(result))


def _parse_dropped_coverage(
    payload: Mapping[str, JsonValue],
) -> CompactExplicitlyDroppedCoverageV2:
    """严格恢复 committed explicitly dropped coverage。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: typed dropped coverage。
    :raises ValueError: shape、reason 或 label 非法时抛出。
    """

    coverage = _required_mapping(payload, _FIELD_EXPLICITLY_DROPPED_COVERAGE)
    _require_exact_fields(
        coverage,
        frozenset(("drops",)),
        path=_FIELD_EXPLICITLY_DROPPED_COVERAGE,
    )
    drops = _required_mapping_list(
        coverage,
        "drops",
        path=f"{_FIELD_EXPLICITLY_DROPPED_COVERAGE}.drops",
    )
    return CompactExplicitlyDroppedCoverageV2(
        drops=tuple(_parse_drop(item, index=index) for index, item in enumerate(drops))
    )


def _validate_committed_coverage(
    semantics: ContextCompactedSemanticPayload,
) -> None:
    """重验 committed candidate/boundary/coverage 单一真源等式。

    :param semantics: 待校验 committed semantic view。
    :returns: ``None``。
    :raises ValueError: coverage 顺序、partition 或 candidate 派生值不一致时抛出。
    """

    boundary_labels = tuple(entry.source_label for entry in semantics.source_boundary)
    represented = semantics.represented_coverage.source_labels
    dropped = semantics.explicitly_dropped_coverage.source_labels
    if represented != tuple(label for label in boundary_labels if label in represented):
        raise ValueError("represented coverage must follow root boundary order")
    if dropped != tuple(label for label in boundary_labels if label in dropped):
        raise ValueError("dropped coverage must follow root boundary order")
    if set(represented).intersection(dropped):
        raise ValueError("represented and dropped coverage must be disjoint")
    if set(represented).union(dropped) != set(boundary_labels):
        raise ValueError("coverage must exactly partition source_boundary")
    expected_sections = _candidate_represented_sections(semantics.accepted_candidate)
    actual_sections = {source.source_label: source.sections for source in semantics.represented_coverage.sources}
    if actual_sections != expected_sections:
        raise ValueError("represented coverage must equal candidate-derived sections")
    if semantics.explicitly_dropped_coverage.drops != semantics.accepted_candidate.explicitly_dropped_sources:
        raise ValueError("dropped coverage must equal accepted candidate drops")
    if semantics.current_input_ref in semantics.compacted_source_refs:
        raise ValueError("current input must not enter compacted source coverage")


def _candidate_represented_sections(
    candidate: CompactCandidateV2,
) -> dict[str, tuple[CompactSemanticSectionV2, ...]]:
    """从 committed candidate 派生 label→semantic sections。

    :param candidate: strict v2 candidate。
    :returns: 每个 represented label 的固定顺序 sections。
    """

    sections: dict[str, set[CompactSemanticSectionV2]] = {}
    if candidate.session_summary is not None:
        _add_candidate_sections(
            sections,
            candidate.session_summary.source_labels,
            CompactSemanticSectionV2.SESSION_SUMMARY,
        )
    for fact in candidate.evidence_facts:
        _add_candidate_sections(
            sections,
            (*fact.support_labels, *fact.context_labels),
            CompactSemanticSectionV2.EVIDENCE_FACTS,
        )
    for anchor in candidate.answer_anchors:
        _add_candidate_sections(
            sections,
            anchor.source_labels,
            CompactSemanticSectionV2.ANSWER_ANCHORS,
        )
    for intent in candidate.forward_intents:
        _add_candidate_sections(
            sections,
            intent.source_labels,
            CompactSemanticSectionV2.FORWARD_INTENTS,
        )
    for item in candidate.reference_continuity:
        _add_candidate_sections(
            sections,
            item.source_labels,
            CompactSemanticSectionV2.REFERENCE_CONTINUITY,
        )
    order = tuple(CompactSemanticSectionV2)
    return {
        label: tuple(section for section in order if section in label_sections)
        for label, label_sections in sections.items()
    }


def _add_candidate_sections(
    sections: dict[str, set[CompactSemanticSectionV2]],
    labels: tuple[str, ...],
    section: CompactSemanticSectionV2,
) -> None:
    """向 candidate represented section accumulator 写入 labels。

    :param sections: label→section set accumulator。
    :param labels: candidate source labels。
    :param section: 当前业务 section。
    :returns: ``None``。
    """

    for label in labels:
        sections.setdefault(label, set()).add(section)


def _parse_persisted_candidate(
    candidate: Mapping[str, JsonValue],
) -> CompactCandidateV2:
    """从 current persisted shape 恢复 typed candidate。

    :param candidate: ``accepted_candidate`` JSON object。
    :returns: typed accepted candidate。
    :raises ValueError: candidate 字段、shape 或 enum 非法时抛出。
    """

    _require_exact_fields(candidate, _CANDIDATE_FIELDS, path=_FIELD_ACCEPTED_CANDIDATE)
    schema = _required_text(candidate, _FIELD_SCHEMA)
    if schema != COMPACT_OUTPUT_SCHEMA_V2:
        raise ValueError("accepted_candidate.schema is invalid")
    return CompactCandidateV2(
        schema=schema,
        session_summary=_parse_session_summary(candidate),
        evidence_facts=tuple(
            _parse_fact(item, index=index)
            for index, item in enumerate(
                _required_mapping_list(
                    candidate,
                    _FIELD_EVIDENCE_FACTS,
                    path=(f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_EVIDENCE_FACTS}"),
                )
            )
        ),
        answer_anchors=tuple(
            _parse_answer_anchor(item, index=index)
            for index, item in enumerate(
                _required_mapping_list(
                    candidate,
                    _FIELD_ANSWER_ANCHORS,
                    path=f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_ANSWER_ANCHORS}",
                )
            )
        ),
        forward_intents=tuple(
            _parse_forward_intent(item, index=index)
            for index, item in enumerate(
                _required_mapping_list(
                    candidate,
                    _FIELD_FORWARD_INTENTS,
                    path=f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_FORWARD_INTENTS}",
                )
            )
        ),
        reference_continuity=tuple(
            _parse_reference(item, index=index)
            for index, item in enumerate(
                _required_mapping_list(
                    candidate,
                    _FIELD_REFERENCE_CONTINUITY,
                    path=(f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_REFERENCE_CONTINUITY}"),
                )
            )
        ),
        diagnostics=tuple(
            _parse_diagnostic(item, index=index)
            for index, item in enumerate(
                _required_mapping_list(
                    candidate,
                    _FIELD_DIAGNOSTICS,
                    path=f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_DIAGNOSTICS}",
                )
            )
        ),
        explicitly_dropped_sources=tuple(
            _parse_drop(item, index=index)
            for index, item in enumerate(
                _required_mapping_list(
                    candidate,
                    _FIELD_EXPLICITLY_DROPPED_SOURCES,
                    path=f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_EXPLICITLY_DROPPED_SOURCES}",
                )
            )
        ),
    )


def _parse_session_summary(
    candidate: Mapping[str, JsonValue],
) -> CompactSessionSummaryV2 | None:
    """恢复 nullable session summary。

    :param candidate: accepted candidate JSON object。
    :returns: typed summary；持久化值为 ``null`` 时返回 ``None``。
    :raises ValueError: summary shape 或字段非法时抛出。
    """

    value = _required_value(candidate, _FIELD_SESSION_SUMMARY)
    if value is None:
        return None
    summary = _mapping_value(value, path=_FIELD_SESSION_SUMMARY)
    _require_exact_fields(summary, _SUMMARY_FIELDS, path=_FIELD_SESSION_SUMMARY)
    return CompactSessionSummaryV2(
        text=_required_text(summary, _FIELD_SUMMARY_TEXT),
        source_labels=_required_unique_text_list(
            summary,
            _FIELD_SOURCE_LABELS,
            path=f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_SESSION_SUMMARY}.{_FIELD_SOURCE_LABELS}",
        ),
    )


def _parse_fact(
    fact: Mapping[str, JsonValue],
    *,
    index: int,
) -> CompactEvidenceFactV2:
    """恢复单个 persisted evidence-backed fact。

    :param fact: fact JSON object。
    :param index: fact ordinal。
    :returns: typed fact candidate。
    :raises ValueError: fact shape、未知字段、文本或 labels 非法时抛出。
    """

    path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_EVIDENCE_FACTS}[{index}]"
    _require_exact_fields(fact, _FACT_FIELDS, path=path)
    return CompactEvidenceFactV2(
        claim=_required_text(fact, _FIELD_CLAIM),
        support_labels=_required_unique_text_list(
            fact,
            _FIELD_SUPPORT_LABELS,
            path=f"{path}.{_FIELD_SUPPORT_LABELS}",
        ),
        context_labels=_required_unique_text_list(
            fact,
            _FIELD_CONTEXT_LABELS,
            path=f"{path}.{_FIELD_CONTEXT_LABELS}",
            allow_empty=True,
        ),
    )


def _parse_answer_anchor(
    anchor: Mapping[str, JsonValue],
    *,
    index: int,
) -> CompactAnswerAnchorV2:
    """恢复单个 persisted answer anchor。

    :param anchor: answer anchor JSON object。
    :param index: anchor ordinal。
    :returns: typed answer anchor candidate。
    :raises ValueError: anchor 或 child shape、文本、ordinal、labels 非法时抛出。
    """

    path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_ANSWER_ANCHORS}[{index}]"
    _require_exact_fields(anchor, _ANCHOR_FIELDS, path=path)
    return CompactAnswerAnchorV2(
        title=_required_text(anchor, _FIELD_TITLE),
        detail=_required_text(anchor, _FIELD_DETAIL),
        source_labels=_required_unique_text_list(
            anchor,
            _FIELD_SOURCE_LABELS,
            path=f"{path}.{_FIELD_SOURCE_LABELS}",
        ),
    )


def _parse_forward_intent(
    intent: Mapping[str, JsonValue],
    *,
    index: int,
) -> CompactForwardIntentV2:
    """恢复单个 persisted forward intent。

    :param intent: forward intent JSON object。
    :param index: intent ordinal。
    :returns: typed forward intent candidate。
    :raises ValueError: shape、enum、文本或 labels 非法时抛出。
    """

    path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_FORWARD_INTENTS}[{index}]"
    _require_exact_fields(intent, _FORWARD_INTENT_FIELDS, path=path)
    return CompactForwardIntentV2(
        intent_type=_required_text(intent, _FIELD_INTENT_TYPE),
        text=_required_text(intent, _FIELD_TEXT),
        status=CompactForwardIntentStatusV2(_required_text(intent, _FIELD_STATUS)),
        source_labels=_required_unique_text_list(
            intent,
            _FIELD_SOURCE_LABELS,
            path=f"{path}.{_FIELD_SOURCE_LABELS}",
        ),
    )


def _parse_reference(
    reference: Mapping[str, JsonValue],
    *,
    index: int,
) -> CompactReferenceContinuityV2:
    """恢复单个 persisted reference continuity item。

    :param reference: reference item JSON object。
    :param index: item ordinal。
    :returns: typed reference continuity candidate。
    :raises ValueError: shape、reason、文本或 labels 非法时抛出。
    """

    path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_REFERENCE_CONTINUITY}[{index}]"
    _require_exact_fields(reference, _REFERENCE_FIELDS, path=path)
    return CompactReferenceContinuityV2(
        text=_required_text(reference, _FIELD_TEXT),
        reason=_required_text(reference, _FIELD_REASON),
        source_labels=_required_unique_text_list(
            reference,
            _FIELD_SOURCE_LABELS,
            path=f"{path}.{_FIELD_SOURCE_LABELS}",
        ),
    )


def _parse_diagnostic(
    diagnostic: Mapping[str, JsonValue],
    *,
    index: int,
) -> CompactCandidateDiagnosticV2:
    """恢复单个 persisted compact diagnostic。

    :param diagnostic: diagnostic JSON object。
    :param index: diagnostic ordinal。
    :returns: typed diagnostic candidate。
    :raises ValueError: shape、文本或 labels 非法时抛出。
    """

    path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_DIAGNOSTICS}[{index}]"
    _require_exact_fields(diagnostic, _DIAGNOSTIC_FIELDS, path=path)
    return CompactCandidateDiagnosticV2(
        code=_required_text(diagnostic, _FIELD_CODE),
        message=_required_text(diagnostic, _FIELD_MESSAGE),
        source_labels=_required_unique_text_list(
            diagnostic,
            _FIELD_SOURCE_LABELS,
            path=f"{path}.{_FIELD_SOURCE_LABELS}",
            allow_empty=True,
        ),
    )


def _parse_drop(
    drop: Mapping[str, JsonValue],
    *,
    index: int,
) -> CompactExplicitDropV2:
    """恢复单个 persisted explicit drop。

    :param drop: drop JSON object。
    :param index: drop ordinal。
    :returns: typed drop。
    :raises ValueError: shape、label 或 reason 非法时抛出。
    """

    path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_EXPLICITLY_DROPPED_SOURCES}[{index}]"
    _require_exact_fields(drop, _DROP_FIELDS, path=path)
    return CompactExplicitDropV2(
        source_label=_required_text(drop, _FIELD_SOURCE_LABEL),
        reason=CompactDropReasonV2(_required_text(drop, _FIELD_REASON)),
    )


def accepted_evidence_mapping_refs(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 vNext compact payload 中已接受的 evidence mapping refs。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :returns: accepted evidence mapping refs。
    :raises ValueError: 字段缺失或非法时抛出。
    """

    return _required_text_list(
        payload,
        _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
        path=_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
    )


def accepted_candidate_fact_evidence_labels(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 vNext accepted candidate 中 fact 引用的 evidence labels。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :returns: 去重后的 evidence labels。
    :raises ValueError: accepted candidate 结构非法时抛出。
    """

    candidate = parse_context_compacted_semantic_payload(payload).accepted_candidate
    labels: list[str] = []
    for fact in candidate.evidence_facts:
        labels.extend(fact.support_labels)
    return tuple(dict.fromkeys(labels))


def compact_artifact_json_vnext(
    *,
    request: CompactionRequest,
    accepted_truth: CompactAcceptedTruthV2,
    policy_digest: str,
    budget_after_compact: int,
) -> JsonValue:
    """构造 vNext compact artifact canonical JSON。

    :param request: compaction request。
    :param accepted_truth: Context Governance final accepted truth。
    :param policy_digest: policy digest。
    :param budget_after_compact: Host 估算的 compact 后预算。
    :returns: artifact JSON object。
    """

    candidate = accepted_truth.candidate
    return {
        "artifact_kind": COMPACT_ARTIFACT_KIND_VNEXT,
        "schema_version": COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT,
        "compaction_request_digest": request.digest(),
        "accepted_candidate_digest": candidate.digest(),
        "accepted_candidate": candidate.to_json(),
        "source_boundary": [
            {
                "source_label": entry.source_label,
                "source_kind": entry.source_kind.value,
                "source_refs": list(entry.source_refs),
                "readable_text": entry.readable_text,
            }
            for entry in accepted_truth.source_boundary
        ],
        "represented_coverage": accepted_truth.represented_coverage.to_json(),
        "explicitly_dropped_coverage": (accepted_truth.explicitly_dropped_coverage.to_json()),
        "budget_before_compact": _budget_before_compact_json(request),
        "budget_after_compact": budget_after_compact,
        "input_snapshot_refs": _input_snapshot_refs_json_vnext(request),
        "prompt_local_label_mapping_refs": list(prompt_local_label_mapping_refs(request)),
        "source_boundary_refs": [
            accepted_truth.current_input_ref,
            *accepted_truth.covered_source_refs,
        ],
        "accepted_evidence_mapping_refs": list(accepted_evidence_mapping_refs_for_candidate(request, candidate)),
        "policy_digest": policy_digest,
    }


def compact_artifact_payload_ref(artifact_digest: str) -> str:
    """根据 artifact digest 派生 compact payload ref。

    :param artifact_digest: artifact digest。
    :returns: payload descriptor ref。
    :raises ValueError: digest 前缀非法时抛出。
    """

    if not artifact_digest.startswith(_SHA256_PREFIX):
        raise ValueError("artifact_digest must be sha256 digest")
    return _COMPACT_ARTIFACT_REF_PREFIX + artifact_digest.removeprefix(_SHA256_PREFIX)


def compact_artifact_descriptor_metadata_vnext(
    *,
    request: CompactionRequest,
    accepted_truth: CompactAcceptedTruthV2,
    artifact_digest: str,
    policy_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 vNext compact artifact descriptor metadata。

    :param request: compaction request。
    :param accepted_truth: Context Governance final accepted truth。
    :param artifact_digest: artifact digest。
    :param policy_digest: policy digest。
    :returns: metadata JSON object。
    """

    return {
        "artifact_kind": COMPACT_ARTIFACT_KIND_VNEXT,
        "schema_version": COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT,
        "artifact_digest": artifact_digest,
        "compaction_request_digest": request.digest(),
        "accepted_candidate_digest": accepted_truth.candidate.digest(),
        "policy_digest": policy_digest,
    }


def prompt_local_label_mapping_refs(request: CompactionRequest) -> tuple[str, ...]:
    """返回 prompt-local label mapping refs。

    :param request: compaction request。
    :returns: label mapping refs。
    """

    refs: list[str] = []
    for label in request.material_pack.all_labels:
        refs.append(f"prompt-label:{label}")
    return tuple(refs)


def source_boundary_refs(request: CompactionRequest) -> tuple[str, ...]:
    """返回 compact source boundary refs。

    :param request: compaction request。
    :returns: source boundary refs。
    """

    return tuple(
        dict.fromkeys(
            (
                request.current_input_ref,
                *request.material_source_refs,
                *request.canonical_evidence_refs,
                *request.evidence_backed_fact_refs,
            )
        )
    )


def accepted_evidence_mapping_refs_for_candidate(
    request: CompactionRequest,
    candidate: CompactCandidateV2,
) -> tuple[str, ...]:
    """返回 accepted vNext fact candidate 绑定的 canonical evidence refs。

    :param request: compaction request。
    :param candidate: accepted vNext candidate。
    :returns: canonical evidence refs。
    """

    evidence_labels: list[str] = []
    for fact in candidate.evidence_facts:
        evidence_labels.extend(fact.support_labels)
    refs: list[str] = []
    for label in dict.fromkeys(evidence_labels):
        entry = request.material_pack.provenance_map[label]
        if entry.accepted_evidence_id is not None:
            refs.append(entry.accepted_evidence_id)
    return tuple(dict.fromkeys(refs))


def _budget_before_compact_json(request: CompactionRequest) -> JsonValue:
    """构造 compact 前预算 JSON。

    :param request: compaction request。
    :returns: budget JSON object。
    """

    estimate = request.budget_before_compact
    return {
        "estimated_input_tokens": estimate.estimated_input_tokens,
        "input_budget_tokens": estimate.input_budget_tokens,
        "soft_threshold_tokens": estimate.soft_threshold_tokens,
        "hard_threshold_tokens": estimate.hard_threshold_tokens,
        "safety_margin_tokens": estimate.safety_margin_tokens,
        "estimator_digest": estimate.estimator_digest,
        "overage_reason": (None if estimate.overage_reason is None else estimate.overage_reason.value),
    }


def _input_snapshot_refs_json_vnext(request: CompactionRequest) -> JsonValue:
    """构造 vNext compact input snapshot refs。

    :param request: compaction request。
    :returns: snapshot refs JSON object。
    """

    return {
        "material_source_refs": list(request.material_source_refs),
        "memory_snapshot_cursor": request.memory_snapshot_cursor,
        "current_input_ref": request.current_input_ref,
        "segment_selection_digest": request.segment_selection.selection_digest,
        "canonical_evidence_refs": list(request.canonical_evidence_refs),
        "evidence_backed_fact_refs": list(request.evidence_backed_fact_refs),
        "recent_raw_turn_refs": list(request.recent_raw_turn_refs),
        "older_raw_turn_refs": list(request.older_raw_turn_refs),
        "existing_episode_summary_refs": list(request.existing_episode_summary_refs),
    }


def _required_mapping(payload: Mapping[str, JsonValue], field_name: str) -> Mapping[str, JsonValue]:
    """读取必填 JSON object 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises ValueError: 字段缺失或不是 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be mapping")
    return value


def _mapping_value(value: JsonValue, *, path: str) -> Mapping[str, JsonValue]:
    """把 JSON value 严格读取为 object。

    :param value: JSON value。
    :param path: 错误字段路径。
    :returns: JSON object。
    :raises ValueError: value 不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be mapping")
    return value


def _required_value(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> JsonValue:
    """读取必填 JSON value，并区分缺字段与显式 ``null``。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 字段 JSON value。
    :raises ValueError: 字段缺失时抛出。
    """

    if field_name not in payload:
        raise ValueError(f"{field_name} is required")
    return payload[field_name]


def _required_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> str:
    """读取必填非空文本字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises ValueError: 字段缺失、类型非法或为空时抛出。
    """

    value = _required_value(payload, field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _required_optional_non_negative_int(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> int | None:
    """读取必填 nullable non-negative integer 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非负整数或 ``None``。
    :raises ValueError: 字段缺失、不是 nullable integer、为 bool 或为负数时抛出。
    """

    value = _required_value(payload, field_name)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer or null")
    return value


def _require_exact_fields(
    payload: Mapping[str, JsonValue],
    expected_fields: frozenset[str],
    *,
    path: str,
) -> None:
    """要求 persisted JSON object 与 current schema 字段集合严格一致。

    :param payload: JSON object。
    :param expected_fields: current schema 精确字段集合。
    :param path: 错误字段路径。
    :returns: ``None``。
    :raises ValueError: 缺字段或出现未知字段时抛出。
    """

    actual_fields = frozenset(payload.keys())
    missing = expected_fields - actual_fields
    if missing:
        raise ValueError(f"{path}.{sorted(missing)[0]} is required")
    unknown = actual_fields - expected_fields
    if unknown:
        raise ValueError(f"{path}.{sorted(unknown)[0]} is not supported")


def _require_runtime_text(value: str, *, field_name: str) -> None:
    """校验 runtime typed contract 的非空文本。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: value 不是字符串时抛出。
    :raises ValueError: value 为空时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty text")


def _require_runtime_text_tuple(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    """校验 runtime typed contract 的文本 tuple。

    :param values: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: values 不是 tuple 或元素不是字符串时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for value in values:
        _require_runtime_text(value, field_name=field_name)


def _required_mapping_list(
    payload: Mapping[str, JsonValue],
    field_name: str,
    *,
    path: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :param path: 错误字段路径。
    :returns: JSON object tuple。
    :raises ValueError: 字段缺失、不是 list 或元素不是 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{path} must be list")
    result: list[Mapping[str, JsonValue]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"{path}[{index}] must be mapping")
        result.append(item)
    return tuple(result)


def _required_text_list(
    payload: Mapping[str, JsonValue],
    field_name: str,
    *,
    path: str,
) -> tuple[str, ...]:
    """读取必填非空文本 list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :param path: 错误字段路径。
    :returns: 文本 tuple。
    :raises ValueError: 字段缺失、不是 list 或元素非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{path} must be list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError(f"{path}[{index}] must be non-empty text")
        result.append(item)
    return tuple(result)


def _required_unique_text_list(
    payload: Mapping[str, JsonValue],
    field_name: str,
    *,
    path: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    """读取必填、元素非空且唯一的文本 list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :param path: 错误字段路径。
    :param allow_empty: 是否允许空 list。
    :returns: 唯一文本 tuple。
    :raises ValueError: 字段缺失、不是 list、元素非法或重复时抛出。
    """

    labels = _required_text_list(payload, field_name, path=path)
    if not allow_empty and len(labels) == 0:
        raise ValueError(f"{path} must be non-empty list")
    seen: set[str] = set()
    for index, label in enumerate(labels):
        if label in seen:
            raise ValueError(f"{path}[{index}] must be unique")
        seen.add(label)
    return labels
