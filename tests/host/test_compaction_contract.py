"""Host Context Governance fresh compact v3 contract owner tests。"""

from __future__ import annotations

import json
from dataclasses import MISSING, fields, replace
from collections.abc import Callable
from typing import Literal, cast

import pytest

from dayu.host import compaction as compaction_module
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.compaction import (
    COMPACT_INPUT_SCHEMA_V3,
    COMPACT_OUTPUT_SCHEMA_V3,
    MAX_COMPACT_REPAIR_FEEDBACK_CHARS,
    CompactAcceptedTruthV3,
    CompactAnswerAnchorV3,
    CompactCandidateV3,
    CompactCurrentInputV3,
    CompactEvidenceFactV3,
    CompactForwardIntentStatusV3,
    CompactForwardIntentV3,
    CompactInputV3,
    CompactOmittedCoverageV3,
    CompactOutputCapsV3,
    CompactPolicyUsageAuditV3,
    CompactReferenceContinuityV3,
    CompactRepresentedCoverageV3,
    CompactRepresentedSourceV3,
    CompactSemanticSectionV3,
    CompactSessionSummaryV3,
    CompactSourceBoundaryEntryV3,
    CompactSourceKindV3,
    CompactValidationIssueCodeV3,
    CompactValidationReportV3,
    compact_policy_usage_measurement_rules_v3,
    compact_text_size_units_v3,
    derive_compact_policy_usage_actuals_v3,
    derive_compact_represented_sections_v3,
    validate_compact_policy_usage_audit_candidate_binding_v3,
    validate_compact_represented_coverage_candidate_binding_v3,
)
from dayu.host.compact_structure import (
    compact_output_json_schema_digest_v3,
    compact_output_json_schema_v3,
    compact_output_prompt_rules_v3,
    compact_output_template_v3,
    parse_compact_candidate_v3,
)
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.context_events import (
    CompactorProposalManifestReference,
    build_context_compacted_payload,
)
from dayu.host.context_governance import (
    accept_compact_candidate_v3,
    build_compact_repair_feedback_v3,
    compact_output_caps_v3_from_memory_policy,
)
from dayu.host.llm_compaction import _repair_feedback_prompt_json_vnext
from dayu.host.memory import (
    MemoryProjectionPolicy,
    default_memory_projection_policy,
    estimate_memory_size_units,
)

_REQUEST_DIGEST = "sha256:" + ("d" * 64)
_SOURCE_BOUNDARY_DIGEST = "sha256:" + ("e" * 64)


def test_fresh_v3_contract_uses_exact_schema_literals() -> None:
    """fresh contract 只接受当前 strict schema literal。

    :returns: ``None``。
    """

    assert COMPACT_INPUT_SCHEMA_V3 == "dayu.context_compaction.input.v3"
    assert COMPACT_OUTPUT_SCHEMA_V3 == "dayu.context_compaction.output.v3"


def test_cross_module_coverage_validator_is_in_public_surface() -> None:
    """跨模块复用的 coverage binding validator 必须进入模块公共面。

    :returns: ``None``。
    """

    assert (
        "validate_compact_represented_coverage_candidate_binding_v3"
        in compaction_module.__all__
    )


def test_output_caps_v3_has_exact_required_fields_without_defaults() -> None:
    """output caps DTO 只镜像 Memory policy 的九个必填字段。

    :returns: ``None``。
    """

    cap_fields = fields(CompactOutputCapsV3)
    assert tuple(field.name for field in cap_fields) == (
        "session_summary_char_cap",
        "evidence_fact_item_cap",
        "evidence_fact_char_cap",
        "answer_anchor_item_cap",
        "answer_anchor_char_cap",
        "forward_intent_item_cap",
        "forward_intent_char_cap",
        "reference_continuity_item_cap",
        "reference_continuity_char_cap",
    )
    assert all(field.default is MISSING for field in cap_fields)
    assert all(field.default_factory is MISSING for field in cap_fields)


def test_compact_structure_owner_projects_template_schema_rules_and_parser() -> None:
    """template、简明规则、formal schema 与 parser 共用 exact v3 shape。

    :returns: ``None``。
    """

    root_keys = (
        "schema",
        "session_summary",
        "evidence_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity",
    )
    template = compact_output_template_v3()
    schema = compact_output_json_schema_v3()
    rules = compact_output_prompt_rules_v3()
    assert tuple(template) == root_keys
    assert schema["required"] == list(root_keys)
    assert rules["required_fields"] == list(root_keys)
    assert parse_compact_candidate_v3(
        json.dumps(template, ensure_ascii=False)
    ).to_json() == template
    serialized_rules = json.dumps(rules, ensure_ascii=False, sort_keys=True)
    schema_properties = schema["properties"]
    assert isinstance(schema_properties, dict)
    assert "additionalProperties" not in serialized_rules
    assert '"type": "object"' not in serialized_rules
    for removed in ("diagnostics", "explicitly_dropped_sources"):
        assert removed not in template
        assert removed not in schema_properties
        assert removed not in serialized_rules


def test_compact_structure_projections_are_fresh_and_digest_is_stable() -> None:
    """调用方修改投影不得反向修改 immutable structure owner。

    :returns: ``None``。
    """

    digest = compact_output_json_schema_digest_v3()
    schema = compact_output_json_schema_v3()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    properties["tampered"] = {"type": "string"}
    template = compact_output_template_v3()
    assert isinstance(template, dict)
    template["tampered"] = "value"

    fresh_properties = compact_output_json_schema_v3()["properties"]
    assert isinstance(fresh_properties, dict)
    assert "tampered" not in fresh_properties
    assert "tampered" not in compact_output_template_v3()
    assert compact_output_json_schema_digest_v3() == digest


def test_input_json_separates_current_input_and_source_boundary() -> None:
    """current input 不分配 label，canonical refs 不进入 LLM-facing JSON。

    :returns: ``None``。
    """

    compact_input = _input()
    assert compact_input.source_labels == ("S1", "E1", "T1")
    assert compact_input.source_kind("E1") is CompactSourceKindV3.EVIDENCE_MATERIAL
    assert compact_input.source_kind("missing") is None
    assert compact_input.to_json() == {
        "schema": COMPACT_INPUT_SCHEMA_V3,
        "current_input": {"readable_text": "分析本期结果"},
        "source_boundary": [
            {
                "source_label": "S1",
                "source_kind": "previous_session_summary",
                "readable_text": "上一轮摘要",
            },
            {
                "source_label": "E1",
                "source_kind": "evidence_material",
                "readable_text": "收入增长 10%",
            },
            {
                "source_label": "T1",
                "source_kind": "trace_material",
                "readable_text": "用户追问利润率",
            },
        ],
        "output_caps": compact_output_caps_v3_from_memory_policy(
            default_memory_projection_policy()
        ).to_json(),
    }


def test_accept_owner_derives_exact_coverage_and_canonical_label_order() -> None:
    """Host 从业务区派生 coverage，并按 boundary 顺序 canonicalize labels。

    :returns: ``None``。
    """

    result = accept_compact_candidate_v3(
        _input(),
        _candidate(summary_labels=("T1", "S1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(result, CompactAcceptedTruthV3)
    assert result.candidate.session_summary is not None
    assert result.candidate.session_summary.source_labels == ("S1", "T1")
    assert result.represented_coverage.source_labels == ("S1", "E1", "T1")
    assert result.omitted_coverage.source_labels == ()
    assert result.covered_source_refs == (
        "event:compact-1",
        "event:tool-result-1",
        "event:user-1",
    )
    assert result.current_input_ref == "event:current"


def test_accepted_truth_rejects_represented_coverage_out_of_boundary_order() -> None:
    """accepted truth owner 拒绝未遵循 root boundary 顺序的 represented coverage。

    :returns: ``None``。
    :raises AssertionError: 乱序 represented coverage 未在 accepted truth 边界失败时抛出。
    """

    accepted = accept_compact_candidate_v3(
        _input(),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV3)
    reordered = CompactRepresentedCoverageV3(
        sources=tuple(reversed(accepted.represented_coverage.sources)),
    )

    with pytest.raises(
        ValueError,
        match="represented coverage must preserve source boundary order",
    ):
        replace(accepted, represented_coverage=reordered)


def test_accept_owner_derives_omitted_complement_for_committed_round_trip() -> None:
    """omitted coverage 由 Host 对 root boundary 求补集并持久化。

    :returns: ``None``。
    :raises AssertionError: accepted truth 或 durable payload 补集顺序漂移时抛出。
    """

    operation_id = "operation-omitted"
    engine_run_id = "compactor-run-omitted"
    candidate = replace(
        _candidate(summary_labels=("S1",), fact_labels=("E1",)),
        evidence_facts=(),
    )

    accepted = accept_compact_candidate_v3(
        _input(),
        candidate,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV3)
    expected_omitted_labels = ("E1", "T1")
    assert accepted.omitted_coverage.source_labels == expected_omitted_labels
    payload = build_context_compacted_payload(
        operation_id=operation_id,
        accepted_attempt_number=1,
        compact_artifact_ref="compact-artifact:omitted",
        compact_artifact_digest=(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        accepted_truth=accepted,
        budget_after_compact=64,
        prompt_local_label_mapping_refs=("prompt-label:S1",),
        accepted_evidence_mapping_refs=(),
        projection_signal="conversation_memory_projection_catchup",
        successful_response_identity=SuccessfulRunnerResponseIdentity(
            effective_provider="test-compactor",
            effective_model="test-compactor-model",
            runner_request_identity=build_runner_request_identity(
                run_id=engine_run_id,
                attempt_id=None,
                execution_id=None,
                iteration_id="omitted-iteration",
                iteration_index=0,
                runner_call_index=1,
            ),
            provider_request_id_availability=(
                ProviderRequestIdAvailability.UNAVAILABLE
            ),
            provider_request_id=None,
        ),
        accepted_proposal_manifest_reference=(
            CompactorProposalManifestReference(
                manifest_event_id="manifest-event-omitted",
                manifest_payload_ref="manifest-payload-omitted",
                manifest_digest=(
                    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
                compactor_input_projection_ref="projection-omitted",
                compactor_input_projection_digest=(
                    "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
                ),
                compaction_operation_id=operation_id,
                compaction_attempt_number=1,
                compactor_engine_run_id=engine_run_id,
            )
        ),
    )
    parsed = parse_context_compacted_semantic_payload(payload)
    assert parsed.omitted_coverage.source_labels == expected_omitted_labels


@pytest.mark.parametrize(
    ("candidate_factory", "expected_code"),
    (
        (
            lambda: _candidate(summary_labels=("UNKNOWN",), fact_labels=("E1",)),
            CompactValidationIssueCodeV3.UNKNOWN_SOURCE_LABEL,
        ),
        (
            lambda: _candidate(summary_labels=("S1",), fact_labels=("T1",)),
            CompactValidationIssueCodeV3.SOURCE_KIND_MISMATCH,
        ),
        (
            lambda: _empty_candidate(),
            CompactValidationIssueCodeV3.EMPTY_SEMANTIC_OUTPUT,
        ),
    ),
)
def test_accept_owner_rejects_deterministic_invalid_matrix(
    candidate_factory: Callable[[], CompactCandidateV3],
    expected_code: CompactValidationIssueCodeV3,
) -> None:
    """label、kind 与 information floor 的 invalid matrix 均由同一 owner 拒绝。

    :param candidate_factory: 待验收 candidate factory。
    :param expected_code: 期望问题码。
    :returns: ``None``。
    """

    result = accept_compact_candidate_v3(
        _input(),
        candidate_factory(),
        default_memory_projection_policy(),
    )
    assert isinstance(result, CompactValidationReportV3)
    assert expected_code in tuple(issue.code for issue in result.issues)


def test_duplicate_and_schema_provable_contradiction_are_rejected() -> None:
    """精确 duplicate 与 intent status contradiction 被稳定拒绝。

    :returns: ``None``。
    """

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    candidate = replace(
        candidate,
        forward_intents=(
            CompactForwardIntentV3(
                intent_type="next_step_note",
                text="继续 分析",
                status=CompactForwardIntentStatusV3.OPEN,
                source_labels=("T1",),
            ),
            CompactForwardIntentV3(
                intent_type="next_step_note",
                text="继续  分析",
                status=CompactForwardIntentStatusV3.BLOCKED,
                source_labels=("T1",),
            ),
        ),
    )
    result = accept_compact_candidate_v3(_input(), candidate, default_memory_projection_policy())
    assert isinstance(result, CompactValidationReportV3)
    codes = tuple(issue.code for issue in result.issues)
    assert CompactValidationIssueCodeV3.DUPLICATE_SEMANTIC_ITEM in codes
    assert CompactValidationIssueCodeV3.CONTRADICTORY_SEMANTIC_ITEM in codes


def test_similar_but_not_equal_text_is_not_fuzzy_deduplicated() -> None:
    """自然语言相似但不相等的文本不由 deterministic validator 猜测。

    :returns: ``None``。
    """

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    candidate = replace(
        candidate,
        reference_continuity=(
            CompactReferenceContinuityV3(text="第一家公司", reason="local_reference", source_labels=("T1",)),
            CompactReferenceContinuityV3(text="首家公司", reason="local_reference", source_labels=("T1",)),
        ),
    )
    result = accept_compact_candidate_v3(_input(), candidate, default_memory_projection_policy())
    assert isinstance(result, CompactAcceptedTruthV3)


def test_memory_policy_item_and_size_caps_use_same_policy_owner() -> None:
    """Context Governance 直接使用 Memory policy 的边界值。

    :returns: ``None``。
    """

    policy = replace(
        default_memory_projection_policy(),
        evidence_fact_item_cap=1,
        evidence_fact_char_cap=len("收入增长 10%"),
    )
    accepted = accept_compact_candidate_v3(
        _input(policy),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        policy,
    )
    assert isinstance(accepted, CompactAcceptedTruthV3)
    too_large = replace(
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        evidence_facts=(
            CompactEvidenceFactV3(
                claim="收入增长 10%+",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )
    rejected = accept_compact_candidate_v3(_input(policy), too_large, policy)
    assert isinstance(rejected, CompactValidationReportV3)
    assert CompactValidationIssueCodeV3.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


def test_policy_usage_audit_derivation_and_validation_fail_closed() -> None:
    """audit derivation 复用单一 estimator，并拒绝类型、actual 与 cap 漂移。

    :returns: ``None``。
    """

    accepted = accept_compact_candidate_v3(
        _input(),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV3)
    candidate = accepted.candidate
    audit = accepted.policy_usage_audit
    actuals = derive_compact_policy_usage_actuals_v3(candidate)
    assert actuals.session_summary_char_actual == estimate_memory_size_units(
        candidate.session_summary.text if candidate.session_summary is not None else ""
    ).units
    validate_compact_policy_usage_audit_candidate_binding_v3(candidate, audit)

    with pytest.raises(ValueError, match="text must be str"):
        compact_text_size_units_v3(cast(str, 1))
    with pytest.raises(TypeError, match="candidate must be CompactCandidateV3"):
        derive_compact_policy_usage_actuals_v3(cast(CompactCandidateV3, "bad"))
    with pytest.raises(TypeError, match="audit must be CompactPolicyUsageAuditV3"):
        validate_compact_policy_usage_audit_candidate_binding_v3(
            candidate,
            cast(CompactPolicyUsageAuditV3, "bad"),
        )
    with pytest.raises(
        ValueError,
        match="policy_usage_audit actuals must equal candidate-derived usage",
    ):
        validate_compact_policy_usage_audit_candidate_binding_v3(
            candidate,
            replace(
                audit,
                evidence_fact_char_actual=audit.evidence_fact_char_actual - 1,
            ),
        )
    with pytest.raises(
        ValueError,
        match="policy_usage_audit actual must not exceed cap",
    ):
        validate_compact_policy_usage_audit_candidate_binding_v3(
            candidate,
            replace(
                audit,
                evidence_fact_char_cap=audit.evidence_fact_char_actual - 1,
            ),
        )


def test_policy_usage_measurement_rules_match_exact_candidate_derivation() -> None:
    """业务可读计量规则与唯一 candidate actual 派生保持精确一致。

    :returns: ``None``。
    """

    rules = compact_policy_usage_measurement_rules_v3()
    assert dict(rules) == {
        "session_summary": "text 的字符数",
        "evidence_facts": "各项 claim 的字符数之和",
        "answer_anchors": "各项 title + 一个换行符 + detail 的字符数之和",
        "forward_intents": "各项 text 的字符数之和",
        "reference_continuity": "各项 text 的字符数之和；reason 不计入",
    }
    candidate = _all_section_cap_candidate()
    actuals = derive_compact_policy_usage_actuals_v3(candidate)
    assert candidate.session_summary is not None
    assert actuals.session_summary_char_actual == len(candidate.session_summary.text)
    assert actuals.evidence_fact_char_actual == sum(
        len(item.claim) for item in candidate.evidence_facts
    )
    assert actuals.answer_anchor_char_actual == sum(
        len(f"{item.title}\n{item.detail}") for item in candidate.answer_anchors
    )
    assert actuals.forward_intent_char_actual == sum(
        len(item.text) for item in candidate.forward_intents
    )
    assert actuals.reference_continuity_char_actual == sum(
        len(item.text) for item in candidate.reference_continuity
    )


def test_v3_typed_contract_rejects_invalid_nested_types_and_bindings() -> None:
    """fresh v3 typed owner 对非法 nested type、partition 与 input binding fail closed。

    :returns: ``None``。
    """

    compact_input = _input()
    caps = compact_input.output_caps
    with pytest.raises(ValueError, match="CompactInputV3.schema is invalid"):
        replace(compact_input, schema=cast(Literal["dayu.context_compaction.input.v3"], "bad"))
    with pytest.raises(TypeError, match="CompactInputV3.current_input is invalid"):
        replace(compact_input, current_input=cast(CompactCurrentInputV3, "bad"))
    with pytest.raises(TypeError, match="CompactInputV3.source_boundary item is invalid"):
        replace(
            compact_input,
            source_boundary=cast(tuple[CompactSourceBoundaryEntryV3, ...], ("bad",)),
        )
    with pytest.raises(TypeError, match="CompactInputV3.output_caps is invalid"):
        replace(compact_input, output_caps=cast(CompactOutputCapsV3, "bad"))

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    with pytest.raises(ValueError, match="CompactCandidateV3.schema is invalid"):
        replace(candidate, schema=cast(Literal["dayu.context_compaction.output.v3"], "bad"))
    with pytest.raises(TypeError, match="CompactCandidateV3.session_summary is invalid"):
        replace(candidate, session_summary=cast(CompactSessionSummaryV3, "bad"))
    with pytest.raises(TypeError, match="evidence_facts items are invalid"):
        replace(candidate, evidence_facts=cast(tuple[CompactEvidenceFactV3, ...], ("bad",)))
    with pytest.raises(TypeError, match="CompactForwardIntentV3.status is invalid"):
        CompactForwardIntentV3(
            intent_type="next_step",
            text="继续分析",
            status=cast(CompactForwardIntentStatusV3, "bad"),
            source_labels=("T1",),
        )

    with pytest.raises(TypeError, match="sections item is invalid"):
        CompactRepresentedSourceV3(
            source_label="S1",
            sections=cast(tuple[CompactSemanticSectionV3, ...], ("bad",)),
        )
    with pytest.raises(ValueError, match="sections must not be empty"):
        CompactRepresentedSourceV3(source_label="S1", sections=())
    with pytest.raises(ValueError, match="sections must be unique and ordered"):
        CompactRepresentedSourceV3(
            source_label="S1",
            sections=(
                CompactSemanticSectionV3.EVIDENCE_FACTS,
                CompactSemanticSectionV3.SESSION_SUMMARY,
            ),
        )

    accepted = accept_compact_candidate_v3(
        compact_input,
        candidate,
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV3)
    assert dict(derive_compact_represented_sections_v3(accepted.candidate)) == {
        source.source_label: source.sections
        for source in accepted.represented_coverage.sources
    }
    validate_compact_represented_coverage_candidate_binding_v3(
        accepted.candidate,
        accepted.represented_coverage,
    )
    with pytest.raises(TypeError, match="candidate must be CompactCandidateV3"):
        derive_compact_represented_sections_v3(
            cast(CompactCandidateV3, "bad")
        )
    with pytest.raises(TypeError, match="represented_coverage must be"):
        validate_compact_represented_coverage_candidate_binding_v3(
            accepted.candidate,
            cast(CompactRepresentedCoverageV3, "bad"),
        )
    with pytest.raises(ValueError, match="represented and omitted coverage must be disjoint"):
        replace(
            accepted,
            omitted_coverage=CompactOmittedCoverageV3(
                source_labels=(accepted.represented_coverage.source_labels[0],)
            ),
        )
    with pytest.raises(ValueError, match="accepted coverage must exactly partition"):
        replace(
            accepted,
            represented_coverage=CompactRepresentedCoverageV3(sources=()),
            omitted_coverage=CompactOmittedCoverageV3(source_labels=()),
        )
    with pytest.raises(TypeError, match="compact_input must be CompactInputV3"):
        accepted.validate_input_binding(cast(CompactInputV3, "bad"))
    with pytest.raises(ValueError, match="current input binding mismatch"):
        replace(accepted, current_input_ref="event:other").validate_input_binding(
            compact_input
        )
    changed_boundary = (
        replace(compact_input.source_boundary[0], readable_text="changed"),
        *compact_input.source_boundary[1:],
    )
    with pytest.raises(ValueError, match="source boundary binding mismatch"):
        accepted.validate_input_binding(
            replace(compact_input, source_boundary=changed_boundary)
        )
    with pytest.raises(ValueError, match="output caps binding mismatch"):
        replace(
            accepted,
            policy_usage_audit=replace(
                accepted.policy_usage_audit,
                session_summary_char_cap=caps.session_summary_char_cap + 1,
            ),
        ).validate_input_binding(compact_input)


_CapSection = Literal[
    "evidence_facts",
    "answer_anchors",
    "forward_intents",
    "reference_continuity",
]


@pytest.mark.parametrize(
    "section",
    (
        "evidence_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity",
    ),
)
def test_each_memory_section_item_cap_accepts_equal_and_rejects_plus_one(
    section: _CapSection,
) -> None:
    """每个 Memory item cap 的边界值与 +1 使用同一 owner。

    :param section: 待验证 candidate section。
    """

    policy = _cap_policy(section, item_cap=1, char_cap=65536)
    accepted = accept_compact_candidate_v3(
        _cap_input(policy),
        _cap_candidate(section, ("first",)),
        policy,
    )
    rejected = accept_compact_candidate_v3(
        _cap_input(policy),
        _cap_candidate(section, ("first", "second")),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV3)
    assert isinstance(rejected, CompactValidationReportV3)
    assert CompactValidationIssueCodeV3.POLICY_ITEM_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


@pytest.mark.parametrize(
    "section",
    (
        "evidence_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity",
    ),
)
def test_each_memory_section_size_cap_accepts_equal_and_rejects_plus_one(
    section: _CapSection,
) -> None:
    """每个 Memory size cap 复用 estimator 并验证 ==/+1。

    :param section: 待验证 candidate section。
    """

    accepted_candidate = _cap_candidate(section, ("abcd",))
    accepted_text = _cap_projection_text(section, "abcd")
    size_cap = estimate_memory_size_units(accepted_text).units
    policy = _cap_policy(section, item_cap=8, char_cap=size_cap)
    accepted = accept_compact_candidate_v3(
        _cap_input(policy),
        accepted_candidate,
        policy,
    )
    rejected = accept_compact_candidate_v3(
        _cap_input(policy),
        _cap_candidate(section, ("abcde",)),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV3)
    assert isinstance(rejected, CompactValidationReportV3)
    assert CompactValidationIssueCodeV3.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


def test_session_summary_size_cap_accepts_equal_and_rejects_plus_one() -> None:
    """session summary 使用同一 estimator 验证 == cap 与 +1。"""

    candidate = _cap_candidate("evidence_facts", ("fact",))
    accepted_candidate = replace(
        candidate,
        session_summary=CompactSessionSummaryV3(
            text="abcd",
            source_labels=("E1", "A1", "T1"),
        ),
    )
    policy = replace(
        default_memory_projection_policy(),
        session_summary_char_cap=estimate_memory_size_units("abcd").units,
    )
    accepted = accept_compact_candidate_v3(
        _cap_input(policy),
        accepted_candidate,
        policy,
    )
    rejected = accept_compact_candidate_v3(
        _cap_input(policy),
        replace(
            accepted_candidate,
            session_summary=CompactSessionSummaryV3(
                text="abcde",
                source_labels=("E1", "A1", "T1"),
            ),
        ),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV3)
    assert isinstance(rejected, CompactValidationReportV3)
    assert CompactValidationIssueCodeV3.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


def test_all_section_cap_violations_preserve_nine_exact_actionable_issues() -> None:
    """五个 section 同时越界时保留全部九条同源、可操作的 cap issues。

    :returns: ``None``。
    :raises AssertionError: owner 数值、计量说明、动作或 projector 完整性漂移时抛出。
    """

    item_cap = 1
    char_cap = 1
    candidate = _all_section_cap_candidate()
    policy = replace(
        default_memory_projection_policy(),
        session_summary_char_cap=char_cap,
        evidence_fact_item_cap=item_cap,
        evidence_fact_char_cap=char_cap,
        answer_anchor_item_cap=item_cap,
        answer_anchor_char_cap=char_cap,
        forward_intent_item_cap=item_cap,
        forward_intent_char_cap=char_cap,
        reference_continuity_item_cap=item_cap,
        reference_continuity_char_cap=char_cap,
    )

    rejected = accept_compact_candidate_v3(_cap_input(policy), candidate, policy)

    assert isinstance(rejected, CompactValidationReportV3)
    assert len(rejected.issues) == 9
    feedback = build_compact_repair_feedback_v3(
        rejected,
        request_digest=_REQUEST_DIGEST,
        source_boundary_digest=_SOURCE_BOUNDARY_DIGEST,
        previous_attempt_number=1,
    )
    assert feedback.request_digest == _REQUEST_DIGEST
    assert feedback.source_boundary_digest == _SOURCE_BOUNDARY_DIGEST
    assert len(feedback.issues) == 9
    assert feedback.additional_issue_count == 0
    evidence_texts = tuple(item.claim for item in candidate.evidence_facts)
    answer_texts = tuple(f"{item.title}\n{item.detail}" for item in candidate.answer_anchors)
    forward_texts = tuple(item.text for item in candidate.forward_intents)
    reference_texts = tuple(item.text for item in candidate.reference_continuity)
    assert candidate.session_summary is not None
    summary_size = estimate_memory_size_units(candidate.session_summary.text).units
    section_expectations: tuple[
        tuple[_CapSection, tuple[str, ...], str],
        ...,
    ] = (
        ("evidence_facts", evidence_texts, "各项 claim 的字符数之和"),
        (
            "answer_anchors",
            answer_texts,
            "各项 title + 一个换行符 + detail 的字符数之和",
        ),
        ("forward_intents", forward_texts, "各项 text 的字符数之和"),
        (
            "reference_continuity",
            reference_texts,
            "各项 text 的字符数之和；reason 不计入",
        ),
    )
    expected_messages: dict[
        tuple[CompactValidationIssueCodeV3, str],
        str,
    ] = {
        (
            CompactValidationIssueCodeV3.POLICY_SIZE_CAP_EXCEEDED,
            '$["session_summary"]["text"]',
        ): (
            f"session_summary.text 当前为 {summary_size} 个字符，上限 {char_cap} 个字符；"
            f"请缩减 session_summary.text 到不超过 {char_cap} 个字符。"
        ),
    }
    for section, texts, measurement in section_expectations:
        path = f'$["{section}"]'
        total = sum(estimate_memory_size_units(text).units for text in texts)
        expected_messages[
            (CompactValidationIssueCodeV3.POLICY_ITEM_CAP_EXCEEDED, path)
        ] = (
            f"{section} 当前为 {len(texts)} 项，上限 {item_cap} 项；"
            f"请删减或合并 {section}，只保留不超过 {item_cap} 项。"
        )
        expected_messages[
            (CompactValidationIssueCodeV3.POLICY_SIZE_CAP_EXCEEDED, path)
        ] = (
            f"{section} 的{measurement}当前为 {total} 个字符，上限 {char_cap} 个字符；"
            f"请缩减 {section} 的文本总量到不超过 {char_cap} 个字符。"
        )
    actual_messages = {
        (issue.code, issue.json_path): issue.message
        for issue in feedback.issues
    }
    assert actual_messages == expected_messages

    projected = _repair_feedback_prompt_json_vnext(feedback)
    assert projected == {
        "required_action": feedback.required_action,
        "issues": [
            {
                "code": issue.code.value,
                "json_path": issue.json_path,
                "message": issue.message,
                "source_labels": list(issue.source_labels),
            }
            for issue in feedback.issues
        ],
    }
    projected_issues = projected["issues"]
    assert isinstance(projected_issues, list)
    assert len(projected_issues) == 9
    assert (
        len(json.dumps(projected, ensure_ascii=False, sort_keys=True))
        <= MAX_COMPACT_REPAIR_FEEDBACK_CHARS
    )


def _cap_input(policy: MemoryProjectionPolicy) -> CompactInputV3:
    """构造覆盖四个 Memory section source-kind 的 input。

    :param policy: 与验收调用同源的 Memory policy。
    :returns: deterministic cap test input。
    """

    return CompactInputV3(
        schema=COMPACT_INPUT_SCHEMA_V3,
        current_input=CompactCurrentInputV3(
            source_ref="event:current-cap",
            readable_text="继续分析",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV3(
                source_label="E1",
                source_kind=CompactSourceKindV3.EVIDENCE_MATERIAL,
                source_refs=("event:evidence-cap",),
                readable_text="evidence",
            ),
            CompactSourceBoundaryEntryV3(
                source_label="A1",
                source_kind=CompactSourceKindV3.ANSWER_MATERIAL,
                source_refs=("event:answer-cap",),
                readable_text="answer",
            ),
            CompactSourceBoundaryEntryV3(
                source_label="T1",
                source_kind=CompactSourceKindV3.TRACE_MATERIAL,
                source_refs=("event:trace-cap",),
                readable_text="trace",
            ),
        ),
        output_caps=compact_output_caps_v3_from_memory_policy(policy),
    )


def _cap_candidate(
    section: _CapSection,
    texts: tuple[str, ...],
) -> CompactCandidateV3:
    """构造仅改变一个被测 section item 数量/文本的完整 candidate。

    :param section: 被测 semantic section。
    :param texts: 被测 section 的业务文本。
    :returns: exact coverage candidate。
    """

    return CompactCandidateV3(
        schema=COMPACT_OUTPUT_SCHEMA_V3,
        session_summary=CompactSessionSummaryV3(
            text="baseline",
            source_labels=("E1", "A1", "T1"),
        ),
        evidence_facts=(
            tuple(
                CompactEvidenceFactV3(
                    claim=text,
                    support_labels=("E1",),
                )
                for text in texts
            )
            if section == "evidence_facts"
            else ()
        ),
        answer_anchors=(
            tuple(
                CompactAnswerAnchorV3(
                    title="title",
                    detail=text,
                    source_labels=("A1",),
                )
                for text in texts
            )
            if section == "answer_anchors"
            else ()
        ),
        forward_intents=(
            tuple(
                CompactForwardIntentV3(
                    intent_type="next_step_note",
                    text=text,
                    status=CompactForwardIntentStatusV3.OPEN,
                    source_labels=("T1",),
                )
                for text in texts
            )
            if section == "forward_intents"
            else ()
        ),
        reference_continuity=(
            tuple(
                CompactReferenceContinuityV3(
                    text=text,
                    reason="recent_state",
                    source_labels=("T1",),
                )
                for text in texts
            )
            if section == "reference_continuity"
            else ()
        ),
    )


def _all_section_cap_candidate() -> CompactCandidateV3:
    """构造 summary 与四个可计量 section 同时超过最小 cap 的 candidate。

    :returns: exact coverage 且只产生九条 policy cap issues 的 candidate。
    :raises Exception: 不主动抛出异常。
    """

    return CompactCandidateV3(
        schema=COMPACT_OUTPUT_SCHEMA_V3,
        session_summary=CompactSessionSummaryV3(
            text="summary-over-cap",
            source_labels=("E1", "A1", "T1"),
        ),
        evidence_facts=(
            CompactEvidenceFactV3(claim="evidence-one", support_labels=("E1",)),
            CompactEvidenceFactV3(claim="evidence-two", support_labels=("E1",)),
        ),
        answer_anchors=(
            CompactAnswerAnchorV3(
                title="title-one",
                detail="detail-one",
                source_labels=("A1",),
            ),
            CompactAnswerAnchorV3(
                title="title-two",
                detail="detail-two",
                source_labels=("A1",),
            ),
        ),
        forward_intents=(
            CompactForwardIntentV3(
                intent_type="next_step",
                text="forward-one",
                status=CompactForwardIntentStatusV3.OPEN,
                source_labels=("T1",),
            ),
            CompactForwardIntentV3(
                intent_type="next_step",
                text="forward-two",
                status=CompactForwardIntentStatusV3.OPEN,
                source_labels=("T1",),
            ),
        ),
        reference_continuity=(
            CompactReferenceContinuityV3(
                text="reference-one",
                reason="继续保留第一个指代",
                source_labels=("T1",),
            ),
            CompactReferenceContinuityV3(
                text="reference-two",
                reason="继续保留第二个指代",
                source_labels=("T1",),
            ),
        ),
    )


def _cap_projection_text(section: _CapSection, text: str) -> str:
    """返回 Memory policy 对被测 item 使用的同源文本投影。

    :param section: 被测 semantic section。
    :param text: candidate item 的可变业务文本。
    :returns: Memory estimator 输入文本。
    """

    if section == "answer_anchors":
        return f"title\n{text}"
    return text


def _cap_policy(
    section: _CapSection,
    *,
    item_cap: int,
    char_cap: int,
) -> MemoryProjectionPolicy:
    """只收紧被测 section 的 Memory owner policy。

    :param section: 被测 semantic section。
    :param item_cap: section item cap。
    :param char_cap: section aggregate size cap。
    :returns: typed MemoryProjectionPolicy。
    """

    policy = default_memory_projection_policy()
    if section == "evidence_facts":
        return replace(
            policy,
            evidence_fact_item_cap=item_cap,
            evidence_fact_char_cap=char_cap,
        )
    if section == "answer_anchors":
        return replace(
            policy,
            answer_anchor_item_cap=item_cap,
            answer_anchor_char_cap=char_cap,
        )
    if section == "forward_intents":
        return replace(
            policy,
            forward_intent_item_cap=item_cap,
            forward_intent_char_cap=char_cap,
        )
    return replace(
        policy,
        reference_continuity_item_cap=item_cap,
        reference_continuity_char_cap=char_cap,
    )


def _input(
    policy: MemoryProjectionPolicy | None = None,
) -> CompactInputV3:
    """构造 deterministic v3 input。

    :param policy: 与验收调用同源的 Memory policy；省略时使用默认 policy。
    :returns: v3 input。
    """

    effective_policy = (
        default_memory_projection_policy() if policy is None else policy
    )
    return CompactInputV3(
        schema=COMPACT_INPUT_SCHEMA_V3,
        current_input=CompactCurrentInputV3(
            source_ref="event:current",
            readable_text="分析本期结果",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV3(
                source_label="S1",
                source_kind=CompactSourceKindV3.PREVIOUS_SESSION_SUMMARY,
                source_refs=("event:compact-1",),
                readable_text="上一轮摘要",
            ),
            CompactSourceBoundaryEntryV3(
                source_label="E1",
                source_kind=CompactSourceKindV3.EVIDENCE_MATERIAL,
                source_refs=("event:tool-result-1",),
                readable_text="收入增长 10%",
            ),
            CompactSourceBoundaryEntryV3(
                source_label="T1",
                source_kind=CompactSourceKindV3.TRACE_MATERIAL,
                source_refs=("event:user-1",),
                readable_text="用户追问利润率",
            ),
        ),
        output_caps=compact_output_caps_v3_from_memory_policy(effective_policy),
    )


def _candidate(
    *,
    summary_labels: tuple[str, ...],
    fact_labels: tuple[str, ...],
) -> CompactCandidateV3:
    """构造可定制 coverage 的 candidate。

    :param summary_labels: summary labels。
    :param fact_labels: fact support labels。
    :returns: v3 candidate。
    """

    return CompactCandidateV3(
        schema=COMPACT_OUTPUT_SCHEMA_V3,
        session_summary=CompactSessionSummaryV3(
            text="保留会话背景",
            source_labels=summary_labels,
        ),
        evidence_facts=(
            CompactEvidenceFactV3(
                claim="收入增长 10%",
                support_labels=fact_labels,
                context_labels=(),
            ),
        ),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )


def _empty_candidate() -> CompactCandidateV3:
    """构造无业务语义 candidate。

    :returns: v3 candidate。
    """

    return CompactCandidateV3(
        schema=COMPACT_OUTPUT_SCHEMA_V3,
        session_summary=None,
        evidence_facts=(),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )
