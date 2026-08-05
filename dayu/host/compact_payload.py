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
    CompactOmittedCoverageV3,
    CompactPolicyUsageAuditV3,
    CompactRepresentedCoverageV3,
    CompactRepresentedSourceV3,
    CompactSemanticSectionV3,
    CompactSourceBoundaryEntryV3,
    CompactSourceKindV3,
    CompactAcceptedTruthV3,
    CompactionRequest,
    CompactCandidateV3,
    validate_compact_policy_usage_audit_candidate_binding_v3,
    validate_compact_represented_coverage_candidate_binding_v3,
)
from dayu.host.compact_structure import parse_compact_candidate_v3
from dayu.host.durable.codec import canonical_json_dumps, is_sha256_digest

COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT = "application/vnd.dayu.context-compact+json"
COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"
COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 4
COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP = "conversation_memory_projection_catchup"
_COMPACT_ARTIFACT_REF_PREFIX = "compact-artifact:"
_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_FIELD_ACCEPTED_CANDIDATE_DIGEST = "accepted_candidate_digest"
_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_FIELD_SOURCE_BOUNDARY_REFS = "source_boundary_refs"
_FIELD_SOURCE_BOUNDARY = "source_boundary"
_FIELD_REPRESENTED_COVERAGE = "represented_coverage"
_FIELD_OMITTED_COVERAGE = "omitted_coverage"
_FIELD_POLICY_USAGE_AUDIT = "policy_usage_audit"
_SHA256_PREFIX = "sha256:"


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
    :param omitted_coverage: Host 派生的 omitted exact complement。
    :param policy_usage_audit: Host 派生的 policy actual/cap audit。
    """

    accepted_candidate: CompactCandidateV3
    accepted_candidate_digest: str
    accepted_evidence_mapping_refs: tuple[str, ...]
    compact_artifact_ref: str
    current_input_ref: str
    source_boundary: tuple[CompactSourceBoundaryEntryV3, ...]
    represented_coverage: CompactRepresentedCoverageV3
    omitted_coverage: CompactOmittedCoverageV3
    policy_usage_audit: CompactPolicyUsageAuditV3

    def __post_init__(self) -> None:
        """校验 typed semantic view 的内部一致性。

        :returns: ``None``。
        :raises TypeError: candidate、refs、source boundary 或 coverage 类型非法时抛出。
        :raises ValueError: digest、ref 或 candidate digest 不一致时抛出。
        """

        if not isinstance(self.accepted_candidate, CompactCandidateV3):
            raise TypeError("accepted_candidate must be CompactCandidateV3")
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
        if not isinstance(self.source_boundary, tuple):
            raise TypeError("source_boundary must be tuple")
        for entry in self.source_boundary:
            if not isinstance(entry, CompactSourceBoundaryEntryV3):
                raise TypeError(
                    "source_boundary item must be CompactSourceBoundaryEntryV3"
                )
        if not isinstance(self.represented_coverage, CompactRepresentedCoverageV3):
            raise TypeError(
                "represented_coverage must be CompactRepresentedCoverageV3"
            )
        if not isinstance(self.omitted_coverage, CompactOmittedCoverageV3):
            raise TypeError("omitted_coverage must be CompactOmittedCoverageV3")
        if not isinstance(self.policy_usage_audit, CompactPolicyUsageAuditV3):
            raise TypeError("policy_usage_audit must be CompactPolicyUsageAuditV3")
        _require_runtime_text(
            self.policy_usage_audit.policy_ref,
            field_name="policy_usage_audit.policy_ref",
        )
        if not is_sha256_digest(self.policy_usage_audit.policy_digest):
            raise ValueError("policy_usage_audit.policy_digest must be sha256 digest")
        validate_compact_policy_usage_audit_candidate_binding_v3(
            self.accepted_candidate,
            self.policy_usage_audit,
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
                *self.omitted_coverage.source_labels,
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
        omitted_coverage=_parse_omitted_coverage(payload),
        policy_usage_audit=_parse_policy_usage_audit(payload),
    )
    if source_refs != (semantics.current_input_ref, *semantics.compacted_source_refs):
        raise ValueError("source_boundary_refs must equal committed derived coverage")
    return semantics


def accepted_compact_business_texts(
    candidate: CompactCandidateV3,
) -> tuple[str, ...]:
    """返回 accepted compact 后普通 dispatch 会消费的业务文本。

    :param candidate: typed accepted compact candidate。
    :returns: 按 memory / ordinary RunInput 业务投影顺序排列的文本 tuple。
    :raises TypeError: candidate 类型非法时抛出。
    """

    if not isinstance(candidate, CompactCandidateV3):
        raise TypeError("candidate must be CompactCandidateV3")
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
) -> tuple[CompactSourceBoundaryEntryV3, ...]:
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
    result: list[CompactSourceBoundaryEntryV3] = []
    for index, item in enumerate(items):
        path = f"{_FIELD_SOURCE_BOUNDARY}[{index}]"
        _require_exact_fields(
            item,
            frozenset(("source_label", "source_kind", "source_refs", "readable_text")),
            path=path,
        )
        result.append(
            CompactSourceBoundaryEntryV3(
                source_label=_required_text(item, "source_label"),
                source_kind=CompactSourceKindV3(_required_text(item, "source_kind")),
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
) -> CompactRepresentedCoverageV3:
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
    result: list[CompactRepresentedSourceV3] = []
    for index, item in enumerate(sources):
        path = f"{_FIELD_REPRESENTED_COVERAGE}.sources[{index}]"
        _require_exact_fields(
            item,
            frozenset(("source_label", "sections")),
            path=path,
        )
        result.append(
            CompactRepresentedSourceV3(
                source_label=_required_text(item, "source_label"),
                sections=tuple(
                    CompactSemanticSectionV3(value)
                    for value in _required_unique_text_list(
                        item,
                        "sections",
                        path=f"{path}.sections",
                    )
                ),
            )
        )
    return CompactRepresentedCoverageV3(sources=tuple(result))


def _parse_omitted_coverage(
    payload: Mapping[str, JsonValue],
) -> CompactOmittedCoverageV3:
    """严格恢复 committed omitted coverage。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: 不携带主观原因的 typed omitted coverage。
    :raises ValueError: shape 或 label 非法时抛出。
    """

    coverage = _required_mapping(payload, _FIELD_OMITTED_COVERAGE)
    _require_exact_fields(
        coverage,
        frozenset(("source_labels",)),
        path=_FIELD_OMITTED_COVERAGE,
    )
    return CompactOmittedCoverageV3(
        source_labels=_required_unique_text_list(
            coverage,
            "source_labels",
            path=f"{_FIELD_OMITTED_COVERAGE}.source_labels",
            allow_empty=True,
        )
    )


def _parse_policy_usage_audit(
    payload: Mapping[str, JsonValue],
) -> CompactPolicyUsageAuditV3:
    """严格恢复 Host-derived policy usage audit。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: typed policy identity 与 section actual/cap audit。
    :raises ValueError: exact fields、文本或非负整数非法时抛出。
    """

    audit = _required_mapping(payload, _FIELD_POLICY_USAGE_AUDIT)
    fields = frozenset(
        (
            "policy_ref",
            "policy_digest",
            "session_summary_char_actual",
            "session_summary_char_cap",
            "evidence_fact_item_actual",
            "evidence_fact_item_cap",
            "evidence_fact_char_actual",
            "evidence_fact_char_cap",
            "answer_anchor_item_actual",
            "answer_anchor_item_cap",
            "answer_anchor_char_actual",
            "answer_anchor_char_cap",
            "forward_intent_item_actual",
            "forward_intent_item_cap",
            "forward_intent_char_actual",
            "forward_intent_char_cap",
            "reference_continuity_item_actual",
            "reference_continuity_item_cap",
            "reference_continuity_char_actual",
            "reference_continuity_char_cap",
        )
    )
    _require_exact_fields(audit, fields, path=_FIELD_POLICY_USAGE_AUDIT)
    return CompactPolicyUsageAuditV3(
        policy_ref=_required_text(audit, "policy_ref"),
        policy_digest=_required_text(audit, "policy_digest"),
        session_summary_char_actual=_required_non_negative_int(
            audit, "session_summary_char_actual"
        ),
        session_summary_char_cap=_required_non_negative_int(
            audit, "session_summary_char_cap"
        ),
        evidence_fact_item_actual=_required_non_negative_int(
            audit, "evidence_fact_item_actual"
        ),
        evidence_fact_item_cap=_required_non_negative_int(
            audit, "evidence_fact_item_cap"
        ),
        evidence_fact_char_actual=_required_non_negative_int(
            audit, "evidence_fact_char_actual"
        ),
        evidence_fact_char_cap=_required_non_negative_int(
            audit, "evidence_fact_char_cap"
        ),
        answer_anchor_item_actual=_required_non_negative_int(
            audit, "answer_anchor_item_actual"
        ),
        answer_anchor_item_cap=_required_non_negative_int(
            audit, "answer_anchor_item_cap"
        ),
        answer_anchor_char_actual=_required_non_negative_int(
            audit, "answer_anchor_char_actual"
        ),
        answer_anchor_char_cap=_required_non_negative_int(
            audit, "answer_anchor_char_cap"
        ),
        forward_intent_item_actual=_required_non_negative_int(
            audit, "forward_intent_item_actual"
        ),
        forward_intent_item_cap=_required_non_negative_int(
            audit, "forward_intent_item_cap"
        ),
        forward_intent_char_actual=_required_non_negative_int(
            audit, "forward_intent_char_actual"
        ),
        forward_intent_char_cap=_required_non_negative_int(
            audit, "forward_intent_char_cap"
        ),
        reference_continuity_item_actual=_required_non_negative_int(
            audit, "reference_continuity_item_actual"
        ),
        reference_continuity_item_cap=_required_non_negative_int(
            audit, "reference_continuity_item_cap"
        ),
        reference_continuity_char_actual=_required_non_negative_int(
            audit, "reference_continuity_char_actual"
        ),
        reference_continuity_char_cap=_required_non_negative_int(
            audit, "reference_continuity_char_cap"
        ),
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
    omitted = semantics.omitted_coverage.source_labels
    if represented != tuple(label for label in boundary_labels if label in represented):
        raise ValueError("represented coverage must follow root boundary order")
    if omitted != tuple(label for label in boundary_labels if label in omitted):
        raise ValueError("omitted coverage must follow root boundary order")
    if set(represented).intersection(omitted):
        raise ValueError("represented and omitted coverage must be disjoint")
    if set(represented).union(omitted) != set(boundary_labels):
        raise ValueError("coverage must exactly partition source_boundary")
    validate_compact_represented_coverage_candidate_binding_v3(
        semantics.accepted_candidate,
        semantics.represented_coverage,
    )
    if semantics.current_input_ref in semantics.compacted_source_refs:
        raise ValueError("current input must not enter compacted source coverage")


def _parse_persisted_candidate(
    candidate: Mapping[str, JsonValue],
) -> CompactCandidateV3:
    """从 current persisted shape 恢复 typed candidate。

    :param candidate: ``accepted_candidate`` JSON object。
    :returns: typed accepted candidate。
    :raises ValueError: candidate 字段、shape 或 enum 非法时抛出。
    """

    return parse_compact_candidate_v3(canonical_json_dumps(candidate))


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
    accepted_truth: CompactAcceptedTruthV3,
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
        "omitted_coverage": accepted_truth.omitted_coverage.to_json(),
        "policy_usage_audit": accepted_truth.policy_usage_audit.to_json(),
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
    accepted_truth: CompactAcceptedTruthV3,
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
    candidate: CompactCandidateV3,
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


def _required_non_negative_int(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取必填 non-negative integer 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises ValueError: 字段缺失、不是 integer、为 bool 或为负数时抛出。
    """

    value = _required_value(payload, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer")
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
