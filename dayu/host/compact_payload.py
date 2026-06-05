"""Host vNext compact payload 解析辅助。

本模块集中承载 ``CONTEXT_COMPACTED`` vNext payload 中稳定字段的严格读取
逻辑，供 dispatch governance 复用，避免 operation path 继续解释旧
preserved refs payload。
"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    CompactionRequest,
    ConversationCompactOutputVNext,
)

COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT = "application/vnd.dayu.context-compact+json"
COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"
COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 3
COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP = "conversation_memory_projection_catchup"
_COMPACT_ARTIFACT_REF_PREFIX = "compact-artifact:"
_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_FIELD_EVIDENCE_LABELS = "evidence_labels"
_SHA256_PREFIX = "sha256:"


def accepted_evidence_mapping_refs(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 vNext compact payload 中已接受的 evidence mapping refs。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :returns: accepted evidence mapping refs。
    :raises ValueError: 字段缺失或非法时抛出。
    """

    return _required_text_list(payload, _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS)


def accepted_candidate_fact_evidence_labels(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 vNext accepted candidate 中 fact 引用的 evidence labels。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :returns: 去重后的 evidence labels。
    :raises ValueError: accepted candidate 结构非法时抛出。
    """

    candidate = _required_mapping(payload, _FIELD_ACCEPTED_CANDIDATE)
    facts = _required_mapping_list(candidate, _FIELD_EVIDENCE_BACKED_FACTS)
    labels: list[str] = []
    for fact in facts:
        labels.extend(_required_text_list(fact, _FIELD_EVIDENCE_LABELS))
    return tuple(dict.fromkeys(labels))


def compact_artifact_json_vnext(
    *,
    request: CompactionRequest,
    candidate: ConversationCompactOutputVNext,
    quality: CompactQualityCheckResultVNext,
    policy_digest: str,
    budget_after_compact: int,
) -> JsonValue:
    """构造 vNext compact artifact canonical JSON。

    :param request: compaction request。
    :param candidate: accepted vNext candidate。
    :param quality: accepted vNext quality result。
    :param policy_digest: policy digest。
    :param budget_after_compact: Host 估算的 compact 后预算。
    :returns: artifact JSON object。
    """

    return {
        "artifact_kind": COMPACT_ARTIFACT_KIND_VNEXT,
        "schema_version": COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT,
        "compaction_request_digest": request.digest(),
        "accepted_candidate_digest": candidate.digest(),
        "accepted_candidate": candidate.to_json(),
        "quality_result": quality.to_json(),
        "budget_before_compact": _budget_before_compact_json(request),
        "budget_after_compact": budget_after_compact,
        "input_snapshot_refs": _input_snapshot_refs_json_vnext(request),
        "prompt_local_label_mapping_refs": list(
            prompt_local_label_mapping_refs(request)
        ),
        "source_boundary_refs": list(source_boundary_refs(request)),
        "accepted_evidence_mapping_refs": list(
            accepted_evidence_mapping_refs_for_candidate(request, candidate)
        ),
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
    candidate: ConversationCompactOutputVNext,
    artifact_digest: str,
    policy_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 vNext compact artifact descriptor metadata。

    :param request: compaction request。
    :param candidate: accepted vNext candidate。
    :param artifact_digest: artifact digest。
    :param policy_digest: policy digest。
    :returns: metadata JSON object。
    """

    return {
        "artifact_kind": COMPACT_ARTIFACT_KIND_VNEXT,
        "schema_version": COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT,
        "artifact_digest": artifact_digest,
        "compaction_request_digest": request.digest(),
        "accepted_candidate_digest": candidate.digest(),
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
    candidate: ConversationCompactOutputVNext,
) -> tuple[str, ...]:
    """返回 accepted vNext fact candidate 绑定的 canonical evidence refs。

    :param request: compaction request。
    :param candidate: accepted vNext candidate。
    :returns: canonical evidence refs。
    """

    evidence_labels: list[str] = []
    for fact in candidate.evidence_backed_facts:
        evidence_labels.extend(fact.evidence_labels)
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
        "overage_reason": (
            None if estimate.overage_reason is None else estimate.overage_reason.value
        ),
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


def _required_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
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


def _required_mapping_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    :raises ValueError: 字段缺失、不是 list 或元素不是 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    result: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name} item must be mapping")
        result.append(item)
    return tuple(result)


def _required_text_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填非空文本 list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple。
    :raises ValueError: 字段缺失、不是 list 或元素非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError(f"{field_name} item must be non-empty text")
        result.append(item)
    return tuple(result)
