"""Host Context Governance fresh compact v4 contract owner tests。"""

from __future__ import annotations

import json
from dataclasses import MISSING, FrozenInstanceError, fields, replace
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
    COMPACT_INPUT_SCHEMA_V4,
    COMPACT_OUTPUT_SCHEMA_V4,
    MAX_COMPACT_REPAIR_FEEDBACK_CHARS,
    CompactAcceptedTruthV4,
    CompactAcceptedReplacementV4,
    CompactAnswerAnchorV4,
    CompactCandidateV4,
    CompactCurrentInputV4,
    CompactEvidenceFactV4,
    CompactForwardIntentStatusV4,
    CompactForwardIntentV4,
    CompactInputV4,
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactOmittedCoverageV4,
    CompactOutputCapsV4,
    CompactPolicyUsageAuditV4,
    PromptLocalProvenanceEntry,
    CompactReferenceContinuityV4,
    CompactRepresentedCoverageV4,
    CompactRepresentedSourceV4,
    CompactSemanticSectionV4,
    CompactSessionSummaryV4,
    CompactSourceBoundaryEntryV4,
    CompactSourceKindV4,
    CompactValidationIssueCodeV4,
    CompactValidationReportV4,
    compact_policy_usage_measurement_rules_v4,
    compact_text_size_units_v4,
    derive_compact_replacement_policy_usage_actuals_v4,
    derive_compact_replacement_represented_sections_v4,
    validate_compact_policy_usage_audit_replacement_binding_v4,
    validate_compact_represented_coverage_replacement_binding_v4,
)
from dayu.host.compact_structure import (
    CompactStructureParseError,
    compact_output_json_schema_digest_v4,
    compact_output_json_schema_v4,
    compact_output_prompt_rules_v4,
    compact_output_template_v4,
    parse_compact_candidate_v4,
)
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.context_events import (
    CompactorProposalManifestReference,
    build_context_compacted_payload,
)
from dayu.host.context_governance import (
    accept_compact_candidate_v4,
    build_compact_repair_feedback_v4,
    compact_output_caps_v4_from_memory_policy,
)
from dayu.host.llm_compaction import _repair_feedback_prompt_json_vnext
from dayu.host.memory import (
    MemoryProjectionPolicy,
    default_memory_projection_policy,
    estimate_memory_size_units,
)

_REQUEST_DIGEST = "sha256:" + ("d" * 64)
_SOURCE_BOUNDARY_DIGEST = "sha256:" + ("e" * 64)


def test_fresh_v4_contract_uses_exact_schema_literals() -> None:
    """fresh contract 只接受当前 strict schema literal。

    :returns: ``None``。
    """

    assert COMPACT_INPUT_SCHEMA_V4 == "dayu.context_compaction.input.v4"
    assert COMPACT_OUTPUT_SCHEMA_V4 == "dayu.context_compaction.output.v4"


def test_cross_module_coverage_validator_is_in_public_surface() -> None:
    """跨模块复用的 coverage binding validator 必须进入模块公共面。

    :returns: ``None``。
    """

    assert (
        "validate_compact_represented_coverage_replacement_binding_v4"
        in compaction_module.__all__
    )


def test_output_caps_v4_has_exact_required_fields_without_defaults() -> None:
    """output caps DTO 只镜像 Memory policy 的九个必填字段。

    :returns: ``None``。
    """

    cap_fields = fields(CompactOutputCapsV4)
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


def test_prompt_local_provenance_entry_has_exact_required_fields_without_defaults() -> None:
    """PromptLocal provenance DTO 必须 frozen/slots 且所有字段显式必填。

    :returns: ``None``。
    """

    provenance_fields = fields(PromptLocalProvenanceEntry)
    assert tuple(field.name for field in provenance_fields) == (
        "label",
        "section",
        "kind",
        "canonical_source_refs",
        "source_event_refs",
        "content_digest",
        "canonical_evidence_refs",
        "tool_result_event_ref",
        "tool_call_event_ref",
        "payload_refs",
        "artifact_refs",
        "source_locator_refs",
        "chunk_parent_label",
        "chunk_ordinal",
    )
    assert all(field.default is MISSING for field in provenance_fields)
    assert all(field.default_factory is MISSING for field in provenance_fields)
    assert "__slots__" in PromptLocalProvenanceEntry.__dict__
    entry = PromptLocalProvenanceEntry(
        label="T1",
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
        canonical_source_refs=("event:user-1",),
        source_event_refs=("event:user-1",),
        content_digest="sha256:prompt-local-provenance-entry",
        canonical_evidence_refs=(),
        tool_result_event_ref=None,
        tool_call_event_ref=None,
        payload_refs=(),
        artifact_refs=(),
        source_locator_refs=(),
        chunk_parent_label=None,
        chunk_ordinal=None,
    )
    with pytest.raises(FrozenInstanceError):
        entry.__setattr__("label", "T2")


def test_compact_candidate_v4_has_exact_required_seven_fields_without_defaults() -> None:
    """七字段 proposal DTO 不得用 selector 默认值隐藏构造遗漏。

    :returns: ``None``。
    """

    proposal_fields = fields(CompactCandidateV4)
    assert tuple(field.name for field in proposal_fields) == (
        "schema",
        "session_summary",
        "retained_previous_evidence_fact_labels",
        "evidence_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity",
    )
    assert all(field.default is MISSING for field in proposal_fields)
    assert all(field.default_factory is MISSING for field in proposal_fields)


def test_compact_structure_owner_projects_template_schema_rules_and_parser() -> None:
    """template、简明规则、formal schema 与 parser 共用 exact v4 shape。

    :returns: ``None``。
    """

    root_keys = (
        "schema",
        "session_summary",
        "retained_previous_evidence_fact_labels",
        "evidence_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity",
    )
    template = compact_output_template_v4()
    schema = compact_output_json_schema_v4()
    rules = compact_output_prompt_rules_v4()
    assert tuple(template) == root_keys
    assert tuple(item.value for item in CompactSemanticSectionV4) == (
        "session_summary",
        "evidence_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity",
    )
    assert schema["required"] == list(root_keys)
    assert rules["required_fields"] == list(root_keys)
    assert parse_compact_candidate_v4(
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


def test_compact_structure_parser_raises_typed_failure_with_owner_code_and_path() -> None:
    """strict structure owner 直接产生稳定 issue code 与 JSON path。

    :returns: ``None``。
    :raises AssertionError: parser 退化为仅含字符串语义的异常时抛出。
    """

    invalid = dict(compact_output_template_v4())
    invalid["forward_intents"] = [
        {
            "intent_type": "next_step",
            "text": "继续分析",
            "status": "not-allowed",
            "source_labels": ["S1"],
        }
    ]

    with pytest.raises(CompactStructureParseError) as captured:
        parse_compact_candidate_v4(json.dumps(invalid, ensure_ascii=False))

    assert captured.value.code is CompactValidationIssueCodeV4.INVALID_ENUM_VALUE
    assert captured.value.json_path == "$.forward_intents[0].status"
    assert captured.value.message == (
        "invalid_enum_value: $.forward_intents[0].status"
    )


def test_compact_structure_projections_are_fresh_and_digest_is_stable() -> None:
    """调用方修改投影不得反向修改 immutable structure owner。

    :returns: ``None``。
    """

    digest = compact_output_json_schema_digest_v4()
    schema = compact_output_json_schema_v4()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    properties["tampered"] = {"type": "string"}
    template = compact_output_template_v4()
    assert isinstance(template, dict)
    template["tampered"] = "value"

    fresh_properties = compact_output_json_schema_v4()["properties"]
    assert isinstance(fresh_properties, dict)
    assert "tampered" not in fresh_properties
    assert "tampered" not in compact_output_template_v4()
    assert compact_output_json_schema_digest_v4() == digest


def test_input_json_separates_current_input_and_source_boundary() -> None:
    """current input 不分配 label，canonical refs 不进入 LLM-facing JSON。

    :returns: ``None``。
    """

    compact_input = _input()
    assert compact_input.source_labels == ("S1", "E1", "T1")
    assert compact_input.source_kind("E1") is CompactSourceKindV4.EVIDENCE_MATERIAL
    assert compact_input.source_kind("missing") is None
    assert compact_input.to_json() == {
        "schema": COMPACT_INPUT_SCHEMA_V4,
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
        "output_caps": compact_output_caps_v4_from_memory_policy(
            default_memory_projection_policy()
        ).to_json(),
    }


def test_accept_owner_rejects_noncanonical_labels_and_derives_exact_coverage() -> None:
    """Host 拒绝非 boundary 顺序 labels，并从 canonical proposal 派生 coverage。

    :returns: ``None``。
    """

    rejected = accept_compact_candidate_v4(
        _input(),
        _candidate(summary_labels=("T1", "S1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(rejected, CompactValidationReportV4)
    assert rejected.issues[0].code is (
        CompactValidationIssueCodeV4.NON_CANONICAL_SOURCE_LABEL_ORDER
    )
    result = accept_compact_candidate_v4(
        _input(),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(result, CompactAcceptedTruthV4)
    assert result.proposal.session_summary is not None
    assert result.proposal.session_summary.source_labels == ("S1", "T1")
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

    accepted = accept_compact_candidate_v4(
        _input(),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV4)
    reordered = CompactRepresentedCoverageV4(
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

    accepted = accept_compact_candidate_v4(
        _input(),
        candidate,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
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


def test_retain_only_copies_previous_fact_atom_and_omits_unselected_sources() -> None:
    """retain-only 必须复制旧 claim/refs，且 coverage 只表示被选择的旧 atom。

    :returns: ``None``。
    :raises AssertionError: combined replacement、coverage 或 audit 仍按 new facts 派生时抛出。
    """

    compact_input = _evidence_provenance_input()
    proposal = replace(
        _empty_candidate(),
        retained_previous_evidence_fact_labels=("P1",),
    )

    accepted = accept_compact_candidate_v4(
        compact_input,
        proposal,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    assert tuple(fact.to_json() for fact in accepted.replacement.evidence_facts) == (
        {
            "claim": "上一轮已核验毛利率为 20%",
            "selection_labels": ["P1"],
            "context_labels": [],
            "canonical_evidence_refs": ["evidence:previous-a", "evidence:previous-b"],
        },
    )
    assert accepted.represented_coverage.source_labels == ("P1",)
    assert accepted.omitted_coverage.source_labels == ("E1", "E2", "T1")
    assert accepted.policy_usage_audit.evidence_fact_item_actual == 1
    assert accepted.policy_usage_audit.evidence_fact_char_actual == len(
        "上一轮已核验毛利率为 20%"
    )


def test_previous_fact_label_cannot_support_a_new_fact_claim() -> None:
    """previous fact 只能走 retain selector，不能借旧 provenance 改写 claim。

    :returns: ``None``。
    """

    proposal = replace(
        _empty_candidate(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="把旧事实改写成不相关结论",
                support_labels=("P1",),
                context_labels=(),
            ),
        ),
    )

    rejected = accept_compact_candidate_v4(
        _evidence_provenance_input(),
        proposal,
        default_memory_projection_policy(),
    )

    assert isinstance(rejected, CompactValidationReportV4)
    assert rejected.issues[0].code is CompactValidationIssueCodeV4.SOURCE_KIND_MISMATCH
    assert rejected.issues[0].json_path == '$["evidence_facts"][0]["support_labels"]'


def test_current_evidence_fact_uses_boundary_ordered_per_entry_refs_union() -> None:
    """多 source 新事实按 support entry 顺序完整合并自身 evidence refs。

    :returns: ``None``。
    :raises AssertionError: refs 丢项、共享无关 aggregate 或顺序漂移时抛出。
    """

    proposal = replace(
        _empty_candidate(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="收入和利润率均改善",
                support_labels=("E1", "E2"),
                context_labels=("T1",),
            ),
        ),
    )

    accepted = accept_compact_candidate_v4(
        _evidence_provenance_input(),
        proposal,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    fact = accepted.replacement.evidence_facts[0]
    assert fact.selection_labels == ("E1", "E2")
    assert fact.context_labels == ("T1",)
    assert fact.canonical_evidence_refs == (
        "evidence:current-a",
        "evidence:shared",
        "evidence:current-b",
    )
    assert accepted.replacement.canonical_evidence_refs == fact.canonical_evidence_refs


def test_retained_plus_two_source_new_fact_has_exact_per_fact_and_aggregate_refs() -> None:
    """手工复算 retained atom 与 two-source new atom 的逐 fact/aggregate refs。

    :returns: ``None``。
    :raises AssertionError: retained/new provenance 串线或 aggregate union 漂移时抛出。
    """

    proposal = replace(
        _empty_candidate(),
        retained_previous_evidence_fact_labels=("P1",),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="收入和利润率均改善",
                support_labels=("E1", "E2"),
                context_labels=("T1",),
            ),
        ),
    )

    accepted = accept_compact_candidate_v4(
        _evidence_provenance_input(),
        proposal,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    retained, current = accepted.replacement.evidence_facts
    assert retained.canonical_evidence_refs == (
        "evidence:previous-a",
        "evidence:previous-b",
    )
    assert current.canonical_evidence_refs == (
        "evidence:current-a",
        "evidence:shared",
        "evidence:current-b",
    )
    assert accepted.replacement.canonical_evidence_refs == (
        "evidence:previous-a",
        "evidence:previous-b",
        "evidence:current-a",
        "evidence:shared",
        "evidence:current-b",
    )


def test_non_evidence_sources_cannot_create_evidence_fact() -> None:
    """只有 user/assistant/trace material 时不得伪造新 EvidenceFact。

    :returns: ``None``。
    """

    compact_input = CompactInputV4(
        schema=COMPACT_INPUT_SCHEMA_V4,
        current_input=CompactCurrentInputV4(
            source_ref="event:current-no-evidence",
            readable_text="纠正上一条回答",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV4(
                source_label="T1",
                source_kind=CompactSourceKindV4.TRACE_MATERIAL,
                source_refs=("event:user-correction",),
                canonical_evidence_refs=(),
                readable_text="用户指出年份写错",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="A1",
                source_kind=CompactSourceKindV4.ANSWER_MATERIAL,
                source_refs=("event:assistant-answer",),
                canonical_evidence_refs=(),
                readable_text="此前回答",
            ),
        ),
        output_caps=compact_output_caps_v4_from_memory_policy(
            default_memory_projection_policy()
        ),
    )
    proposal = replace(
        _empty_candidate(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="伪造的核验事实",
                support_labels=("T1",),
                context_labels=("A1",),
            ),
        ),
    )

    rejected = accept_compact_candidate_v4(
        compact_input,
        proposal,
        default_memory_projection_policy(),
    )

    assert isinstance(rejected, CompactValidationReportV4)
    assert CompactValidationIssueCodeV4.SOURCE_KIND_MISMATCH in tuple(
        issue.code for issue in rejected.issues
    )


def test_combined_retained_and_new_facts_enforce_duplicate_and_caps() -> None:
    """duplicate、item cap 与 char cap 必须对 retained+new combined facts 生效。

    :returns: ``None``。
    """

    duplicate_proposal = replace(
        _empty_candidate(),
        retained_previous_evidence_fact_labels=("P1",),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="上一轮已核验毛利率为 20%",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )
    duplicate = accept_compact_candidate_v4(
        _evidence_provenance_input(),
        duplicate_proposal,
        default_memory_projection_policy(),
    )
    assert isinstance(duplicate, CompactValidationReportV4)
    assert CompactValidationIssueCodeV4.DUPLICATE_SEMANTIC_ITEM in tuple(
        issue.code for issue in duplicate.issues
    )

    cap_policy = replace(
        default_memory_projection_policy(),
        evidence_fact_item_cap=1,
        evidence_fact_char_cap=len("上一轮已核验毛利率为 20%") + len("收入增长 10%") - 1,
    )
    cap_proposal = replace(
        duplicate_proposal,
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="收入增长 10%",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )
    capped = accept_compact_candidate_v4(
        _evidence_provenance_input(cap_policy),
        cap_proposal,
        cap_policy,
    )
    assert isinstance(capped, CompactValidationReportV4)
    cap_codes = tuple(issue.code for issue in capped.issues)
    assert CompactValidationIssueCodeV4.POLICY_ITEM_CAP_EXCEEDED in cap_codes
    assert CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED in cap_codes


def test_omitted_previous_claim_can_be_recreated_from_current_evidence() -> None:
    """omit 旧 fact 后，相同 claim 可由 current evidence 以新 provenance 接受。

    :returns: ``None``。
    """

    proposal = replace(
        _empty_candidate(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="上一轮已核验毛利率为 20%",
                support_labels=("E2",),
                context_labels=(),
            ),
        ),
    )

    accepted = accept_compact_candidate_v4(
        _evidence_provenance_input(),
        proposal,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    assert accepted.replacement.evidence_facts[0].canonical_evidence_refs == (
        "evidence:shared",
        "evidence:current-b",
    )
    assert "P1" in accepted.omitted_coverage.source_labels


@pytest.mark.parametrize(
    "source_kind",
    (
        CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,
        CompactSourceKindV4.EVIDENCE_MATERIAL,
    ),
)
def test_evidence_boundary_entry_rejects_empty_canonical_refs(
    source_kind: CompactSourceKindV4,
) -> None:
    """previous/current evidence boundary 缺 canonical refs 时 typed fail closed。

    :param source_kind: 被测 evidence source kind。
    :returns: ``None``。
    """

    with pytest.raises(
        ValueError,
        match="canonical_evidence_refs must be non-empty",
    ):
        CompactSourceBoundaryEntryV4(
            source_label="E-empty",
            source_kind=source_kind,
            source_refs=("event:evidence-empty",),
            canonical_evidence_refs=(),
            readable_text="缺 provenance 的事实",
        )


@pytest.mark.parametrize(
    ("candidate_factory", "expected_code"),
    (
        (
            lambda: _candidate(summary_labels=("UNKNOWN",), fact_labels=("E1",)),
            CompactValidationIssueCodeV4.UNKNOWN_SOURCE_LABEL,
        ),
        (
            lambda: _candidate(summary_labels=("S1",), fact_labels=("T1",)),
            CompactValidationIssueCodeV4.SOURCE_KIND_MISMATCH,
        ),
        (
            lambda: _empty_candidate(),
            CompactValidationIssueCodeV4.EMPTY_SEMANTIC_OUTPUT,
        ),
    ),
)
def test_accept_owner_rejects_deterministic_invalid_matrix(
    candidate_factory: Callable[[], CompactCandidateV4],
    expected_code: CompactValidationIssueCodeV4,
) -> None:
    """label、kind 与 information floor 的 invalid matrix 均由同一 owner 拒绝。

    :param candidate_factory: 待验收 candidate factory。
    :param expected_code: 期望问题码。
    :returns: ``None``。
    """

    result = accept_compact_candidate_v4(
        _input(),
        candidate_factory(),
        default_memory_projection_policy(),
    )
    assert isinstance(result, CompactValidationReportV4)
    assert expected_code in tuple(issue.code for issue in result.issues)


def test_duplicate_and_schema_provable_contradiction_are_rejected() -> None:
    """精确 duplicate 与 intent status contradiction 被稳定拒绝。

    :returns: ``None``。
    """

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    candidate = replace(
        candidate,
        forward_intents=(
            CompactForwardIntentV4(
                intent_type="next_step_note",
                text="继续 分析",
                status=CompactForwardIntentStatusV4.OPEN,
                source_labels=("T1",),
            ),
            CompactForwardIntentV4(
                intent_type="next_step_note",
                text="继续  分析",
                status=CompactForwardIntentStatusV4.BLOCKED,
                source_labels=("T1",),
            ),
        ),
    )
    result = accept_compact_candidate_v4(_input(), candidate, default_memory_projection_policy())
    assert isinstance(result, CompactValidationReportV4)
    codes = tuple(issue.code for issue in result.issues)
    assert CompactValidationIssueCodeV4.DUPLICATE_SEMANTIC_ITEM in codes
    assert CompactValidationIssueCodeV4.CONTRADICTORY_SEMANTIC_ITEM in codes


def test_similar_but_not_equal_text_is_not_fuzzy_deduplicated() -> None:
    """自然语言相似但不相等的文本不由 deterministic validator 猜测。

    :returns: ``None``。
    """

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    candidate = replace(
        candidate,
        reference_continuity=(
            CompactReferenceContinuityV4(text="第一家公司", reason="local_reference", source_labels=("T1",)),
            CompactReferenceContinuityV4(text="首家公司", reason="local_reference", source_labels=("T1",)),
        ),
    )
    result = accept_compact_candidate_v4(_input(), candidate, default_memory_projection_policy())
    assert isinstance(result, CompactAcceptedTruthV4)


def test_memory_policy_item_and_size_caps_use_same_policy_owner() -> None:
    """Context Governance 直接使用 Memory policy 的边界值。

    :returns: ``None``。
    """

    policy = replace(
        default_memory_projection_policy(),
        evidence_fact_item_cap=1,
        evidence_fact_char_cap=len("收入增长 10%"),
    )
    accepted = accept_compact_candidate_v4(
        _input(policy),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        policy,
    )
    assert isinstance(accepted, CompactAcceptedTruthV4)
    too_large = replace(
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="收入增长 10%+",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )
    rejected = accept_compact_candidate_v4(_input(policy), too_large, policy)
    assert isinstance(rejected, CompactValidationReportV4)
    assert CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


def test_policy_usage_audit_derivation_and_validation_fail_closed() -> None:
    """audit derivation 复用单一 estimator，并拒绝类型、actual 与 cap 漂移。

    :returns: ``None``。
    """

    accepted = accept_compact_candidate_v4(
        _input(),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV4)
    replacement = accepted.replacement
    audit = accepted.policy_usage_audit
    actuals = derive_compact_replacement_policy_usage_actuals_v4(replacement)
    assert actuals.session_summary_char_actual == estimate_memory_size_units(
        replacement.session_summary.text
        if replacement.session_summary is not None
        else ""
    ).units
    validate_compact_policy_usage_audit_replacement_binding_v4(
        replacement,
        audit,
    )

    with pytest.raises(ValueError, match="text must be str"):
        compact_text_size_units_v4(cast(str, 1))
    with pytest.raises(
        TypeError,
        match="replacement must be CompactAcceptedReplacementV4",
    ):
        derive_compact_replacement_policy_usage_actuals_v4(
            cast(CompactAcceptedReplacementV4, "bad")
        )
    with pytest.raises(TypeError, match="audit must be CompactPolicyUsageAuditV4"):
        validate_compact_policy_usage_audit_replacement_binding_v4(
            replacement,
            cast(CompactPolicyUsageAuditV4, "bad"),
        )
    with pytest.raises(
        ValueError,
        match="policy_usage_audit actuals must equal replacement-derived usage",
    ):
        validate_compact_policy_usage_audit_replacement_binding_v4(
            replacement,
            replace(
                audit,
                evidence_fact_char_actual=audit.evidence_fact_char_actual - 1,
            ),
        )
    with pytest.raises(
        ValueError,
        match="policy_usage_audit actual must not exceed cap",
    ):
        validate_compact_policy_usage_audit_replacement_binding_v4(
            replacement,
            replace(
                audit,
                evidence_fact_char_cap=audit.evidence_fact_char_actual - 1,
            ),
        )


def test_policy_usage_measurement_rules_match_exact_replacement_derivation() -> None:
    """业务可读计量规则与唯一 replacement actual 派生保持精确一致。

    :returns: ``None``。
    """

    rules = compact_policy_usage_measurement_rules_v4()
    assert dict(rules) == {
        "session_summary": "text 的字符数",
        "evidence_facts": "各项 claim 的字符数之和",
        "answer_anchors": "各项 title + 一个换行符 + detail 的字符数之和",
        "forward_intents": "各项 text 的字符数之和",
        "reference_continuity": "各项 text 的字符数之和；reason 不计入",
    }
    proposal = _all_section_cap_candidate()
    accepted = accept_compact_candidate_v4(
        _cap_input(default_memory_projection_policy()),
        proposal,
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV4)
    replacement = accepted.replacement
    actuals = derive_compact_replacement_policy_usage_actuals_v4(replacement)
    assert replacement.session_summary is not None
    assert actuals.session_summary_char_actual == len(
        replacement.session_summary.text
    )
    assert actuals.evidence_fact_char_actual == sum(
        len(item.claim) for item in replacement.evidence_facts
    )
    assert actuals.answer_anchor_char_actual == sum(
        len(f"{item.title}\n{item.detail}")
        for item in replacement.answer_anchors
    )
    assert actuals.forward_intent_char_actual == sum(
        len(item.text) for item in replacement.forward_intents
    )
    assert actuals.reference_continuity_char_actual == sum(
        len(item.text) for item in replacement.reference_continuity
    )


def test_v4_typed_contract_rejects_invalid_nested_types_and_bindings() -> None:
    """fresh v4 typed owner 对非法 nested type、partition 与 input binding fail closed。

    :returns: ``None``。
    """

    compact_input = _input()
    caps = compact_input.output_caps
    with pytest.raises(ValueError, match="CompactInputV4.schema is invalid"):
        replace(compact_input, schema=cast(Literal["dayu.context_compaction.input.v4"], "bad"))
    with pytest.raises(TypeError, match="CompactInputV4.current_input is invalid"):
        replace(compact_input, current_input=cast(CompactCurrentInputV4, "bad"))
    with pytest.raises(TypeError, match="CompactInputV4.source_boundary item is invalid"):
        replace(
            compact_input,
            source_boundary=cast(tuple[CompactSourceBoundaryEntryV4, ...], ("bad",)),
        )
    with pytest.raises(TypeError, match="CompactInputV4.output_caps is invalid"):
        replace(compact_input, output_caps=cast(CompactOutputCapsV4, "bad"))

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    with pytest.raises(ValueError, match="CompactCandidateV4.schema is invalid"):
        replace(candidate, schema=cast(Literal["dayu.context_compaction.output.v4"], "bad"))
    with pytest.raises(TypeError, match="CompactCandidateV4.session_summary is invalid"):
        replace(candidate, session_summary=cast(CompactSessionSummaryV4, "bad"))
    with pytest.raises(TypeError, match="evidence_facts items are invalid"):
        replace(candidate, evidence_facts=cast(tuple[CompactEvidenceFactV4, ...], ("bad",)))
    with pytest.raises(TypeError, match="CompactForwardIntentV4.status is invalid"):
        CompactForwardIntentV4(
            intent_type="next_step",
            text="继续分析",
            status=cast(CompactForwardIntentStatusV4, "bad"),
            source_labels=("T1",),
        )

    with pytest.raises(TypeError, match="sections item is invalid"):
        CompactRepresentedSourceV4(
            source_label="S1",
            sections=cast(tuple[CompactSemanticSectionV4, ...], ("bad",)),
        )
    with pytest.raises(ValueError, match="sections must not be empty"):
        CompactRepresentedSourceV4(source_label="S1", sections=())
    with pytest.raises(ValueError, match="sections must be unique and ordered"):
        CompactRepresentedSourceV4(
            source_label="S1",
            sections=(
                CompactSemanticSectionV4.EVIDENCE_FACTS,
                CompactSemanticSectionV4.SESSION_SUMMARY,
            ),
        )

    accepted = accept_compact_candidate_v4(
        compact_input,
        candidate,
        default_memory_projection_policy(),
    )
    assert isinstance(accepted, CompactAcceptedTruthV4)
    assert dict(
        derive_compact_replacement_represented_sections_v4(
            accepted.replacement
        )
    ) == {
        source.source_label: source.sections
        for source in accepted.represented_coverage.sources
    }
    validate_compact_represented_coverage_replacement_binding_v4(
        accepted.replacement,
        accepted.represented_coverage,
    )
    with pytest.raises(
        TypeError,
        match="replacement must be CompactAcceptedReplacementV4",
    ):
        derive_compact_replacement_represented_sections_v4(
            cast(CompactAcceptedReplacementV4, "bad")
        )
    with pytest.raises(TypeError, match="represented_coverage must be"):
        validate_compact_represented_coverage_replacement_binding_v4(
            accepted.replacement,
            cast(CompactRepresentedCoverageV4, "bad"),
        )
    with pytest.raises(ValueError, match="represented and omitted coverage must be disjoint"):
        replace(
            accepted,
            omitted_coverage=CompactOmittedCoverageV4(
                source_labels=(accepted.represented_coverage.source_labels[0],)
            ),
        )
    with pytest.raises(ValueError, match="accepted coverage must exactly partition"):
        replace(
            accepted,
            represented_coverage=CompactRepresentedCoverageV4(sources=()),
            omitted_coverage=CompactOmittedCoverageV4(source_labels=()),
        )
    with pytest.raises(TypeError, match="compact_input must be CompactInputV4"):
        accepted.validate_input_binding(cast(CompactInputV4, "bad"))
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
    accepted = accept_compact_candidate_v4(
        _cap_input(policy),
        _cap_candidate(section, ("first",)),
        policy,
    )
    rejected = accept_compact_candidate_v4(
        _cap_input(policy),
        _cap_candidate(section, ("first", "second")),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    assert isinstance(rejected, CompactValidationReportV4)
    assert CompactValidationIssueCodeV4.POLICY_ITEM_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


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

    accepted_proposal = _cap_candidate(section, ("abcd",))
    accepted_text = _cap_projection_text(section, "abcd")
    size_cap = estimate_memory_size_units(accepted_text).units
    policy = _cap_policy(section, item_cap=8, char_cap=size_cap)
    accepted = accept_compact_candidate_v4(
        _cap_input(policy),
        accepted_proposal,
        policy,
    )
    rejected = accept_compact_candidate_v4(
        _cap_input(policy),
        _cap_candidate(section, ("abcde",)),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    assert isinstance(rejected, CompactValidationReportV4)
    assert CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


def test_session_summary_size_cap_accepts_equal_and_rejects_plus_one() -> None:
    """session summary 使用同一 estimator 验证 == cap 与 +1。"""

    candidate = _cap_candidate("evidence_facts", ("fact",))
    accepted_proposal = replace(
        candidate,
        session_summary=CompactSessionSummaryV4(
            text="abcd",
            source_labels=("E1", "A1", "T1"),
        ),
    )
    policy = replace(
        default_memory_projection_policy(),
        session_summary_char_cap=estimate_memory_size_units("abcd").units,
    )
    accepted = accept_compact_candidate_v4(
        _cap_input(policy),
        accepted_proposal,
        policy,
    )
    rejected = accept_compact_candidate_v4(
        _cap_input(policy),
        replace(
            accepted_proposal,
            session_summary=CompactSessionSummaryV4(
                text="abcde",
                source_labels=("E1", "A1", "T1"),
            ),
        ),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV4)
    assert isinstance(rejected, CompactValidationReportV4)
    assert CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


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

    rejected = accept_compact_candidate_v4(_cap_input(policy), candidate, policy)

    assert isinstance(rejected, CompactValidationReportV4)
    assert len(rejected.issues) == 9
    feedback = build_compact_repair_feedback_v4(
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
        tuple[CompactValidationIssueCodeV4, str],
        str,
    ] = {
        (
            CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED,
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
            (CompactValidationIssueCodeV4.POLICY_ITEM_CAP_EXCEEDED, path)
        ] = (
            f"{section} 当前为 {len(texts)} 项，上限 {item_cap} 项；"
            f"请删减或合并 {section}，只保留不超过 {item_cap} 项。"
        )
        expected_messages[
            (CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED, path)
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


def _cap_input(policy: MemoryProjectionPolicy) -> CompactInputV4:
    """构造覆盖四个 Memory section source-kind 的 input。

    :param policy: 与验收调用同源的 Memory policy。
    :returns: deterministic cap test input。
    """

    return CompactInputV4(
        schema=COMPACT_INPUT_SCHEMA_V4,
        current_input=CompactCurrentInputV4(
            source_ref="event:current-cap",
            readable_text="继续分析",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV4(
                source_label="E1",
                source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                source_refs=("event:evidence-cap",),
                canonical_evidence_refs=("evidence:evidence-cap",),
                readable_text="evidence",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="A1",
                source_kind=CompactSourceKindV4.ANSWER_MATERIAL,
                source_refs=("event:answer-cap",),
                canonical_evidence_refs=(),
                readable_text="answer",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="T1",
                source_kind=CompactSourceKindV4.TRACE_MATERIAL,
                source_refs=("event:trace-cap",),
                canonical_evidence_refs=(),
                readable_text="trace",
            ),
        ),
        output_caps=compact_output_caps_v4_from_memory_policy(policy),
    )


def _cap_candidate(
    section: _CapSection,
    texts: tuple[str, ...],
) -> CompactCandidateV4:
    """构造仅改变一个被测 section item 数量/文本的完整 candidate。

    :param section: 被测 semantic section。
    :param texts: 被测 section 的业务文本。
    :returns: exact coverage candidate。
    """

    return CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=CompactSessionSummaryV4(
            text="baseline",
            source_labels=("E1", "A1", "T1"),
        ),
        retained_previous_evidence_fact_labels=(),
        evidence_facts=(
            tuple(
                CompactEvidenceFactV4(
                    claim=text,
                    support_labels=("E1",),
                    context_labels=(),
                )
                for text in texts
            )
            if section == "evidence_facts"
            else ()
        ),
        answer_anchors=(
            tuple(
                CompactAnswerAnchorV4(
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
                CompactForwardIntentV4(
                    intent_type="next_step_note",
                    text=text,
                    status=CompactForwardIntentStatusV4.OPEN,
                    source_labels=("T1",),
                )
                for text in texts
            )
            if section == "forward_intents"
            else ()
        ),
        reference_continuity=(
            tuple(
                CompactReferenceContinuityV4(
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


def _all_section_cap_candidate() -> CompactCandidateV4:
    """构造 summary 与四个可计量 section 同时超过最小 cap 的 candidate。

    :returns: exact coverage 且只产生九条 policy cap issues 的 candidate。
    :raises Exception: 不主动抛出异常。
    """

    return CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=CompactSessionSummaryV4(
            text="summary-over-cap",
            source_labels=("E1", "A1", "T1"),
        ),
        retained_previous_evidence_fact_labels=(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="evidence-one",
                support_labels=("E1",),
                context_labels=(),
            ),
            CompactEvidenceFactV4(
                claim="evidence-two",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
        answer_anchors=(
            CompactAnswerAnchorV4(
                title="title-one",
                detail="detail-one",
                source_labels=("A1",),
            ),
            CompactAnswerAnchorV4(
                title="title-two",
                detail="detail-two",
                source_labels=("A1",),
            ),
        ),
        forward_intents=(
            CompactForwardIntentV4(
                intent_type="next_step",
                text="forward-one",
                status=CompactForwardIntentStatusV4.OPEN,
                source_labels=("T1",),
            ),
            CompactForwardIntentV4(
                intent_type="next_step",
                text="forward-two",
                status=CompactForwardIntentStatusV4.OPEN,
                source_labels=("T1",),
            ),
        ),
        reference_continuity=(
            CompactReferenceContinuityV4(
                text="reference-one",
                reason="继续保留第一个指代",
                source_labels=("T1",),
            ),
            CompactReferenceContinuityV4(
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
) -> CompactInputV4:
    """构造 deterministic v4 input。

    :param policy: 与验收调用同源的 Memory policy；省略时使用默认 policy。
    :returns: v4 input。
    """

    effective_policy = (
        default_memory_projection_policy() if policy is None else policy
    )
    return CompactInputV4(
        schema=COMPACT_INPUT_SCHEMA_V4,
        current_input=CompactCurrentInputV4(
            source_ref="event:current",
            readable_text="分析本期结果",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV4(
                source_label="S1",
                source_kind=CompactSourceKindV4.PREVIOUS_SESSION_SUMMARY,
                source_refs=("event:compact-1",),
                canonical_evidence_refs=(),
                readable_text="上一轮摘要",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="E1",
                source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                source_refs=("event:tool-result-1",),
                canonical_evidence_refs=("evidence:tool-result-1",),
                readable_text="收入增长 10%",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="T1",
                source_kind=CompactSourceKindV4.TRACE_MATERIAL,
                source_refs=("event:user-1",),
                canonical_evidence_refs=(),
                readable_text="用户追问利润率",
            ),
        ),
        output_caps=compact_output_caps_v4_from_memory_policy(effective_policy),
    )


def _evidence_provenance_input(
    policy: MemoryProjectionPolicy | None = None,
) -> CompactInputV4:
    """构造同时含 previous/current evidence 与非 evidence context 的输入。

    :param policy: 与验收调用同源的 Memory policy；省略时使用默认 policy。
    :returns: 可覆盖 retain、union、omit 与 combined caps 的 v4 input。
    """

    effective_policy = (
        default_memory_projection_policy() if policy is None else policy
    )
    return CompactInputV4(
        schema=COMPACT_INPUT_SCHEMA_V4,
        current_input=CompactCurrentInputV4(
            source_ref="event:current-provenance",
            readable_text="继续核验收入与利润率",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV4(
                source_label="P1",
                source_kind=CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,
                source_refs=("event:previous-compact",),
                canonical_evidence_refs=(
                    "evidence:previous-a",
                    "evidence:previous-b",
                ),
                readable_text="上一轮已核验毛利率为 20%",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="E1",
                source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                source_refs=("event:tool-current-a",),
                canonical_evidence_refs=(
                    "evidence:current-a",
                    "evidence:shared",
                ),
                readable_text="本期收入增长 10%",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="E2",
                source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                source_refs=("event:tool-current-b",),
                canonical_evidence_refs=(
                    "evidence:shared",
                    "evidence:current-b",
                ),
                readable_text="本期毛利率改善",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="T1",
                source_kind=CompactSourceKindV4.TRACE_MATERIAL,
                source_refs=("event:user-context",),
                canonical_evidence_refs=(),
                readable_text="用户要求对比两个指标",
            ),
        ),
        output_caps=compact_output_caps_v4_from_memory_policy(effective_policy),
    )


def _candidate(
    *,
    summary_labels: tuple[str, ...],
    fact_labels: tuple[str, ...],
) -> CompactCandidateV4:
    """构造可定制 coverage 的 candidate。

    :param summary_labels: summary labels。
    :param fact_labels: fact support labels。
    :returns: v4 candidate。
    """

    return CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=CompactSessionSummaryV4(
            text="保留会话背景",
            source_labels=summary_labels,
        ),
        retained_previous_evidence_fact_labels=(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="收入增长 10%",
                support_labels=fact_labels,
                context_labels=(),
            ),
        ),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )


def _empty_candidate() -> CompactCandidateV4:
    """构造无业务语义 candidate。

    :returns: v4 candidate。
    """

    return CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=None,
        retained_previous_evidence_fact_labels=(),
        evidence_facts=(),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )
