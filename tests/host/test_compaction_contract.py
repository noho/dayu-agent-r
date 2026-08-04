"""Host Context Governance v2 contract owner tests。"""

from __future__ import annotations

import json
from dataclasses import replace
from collections.abc import Callable
from typing import Literal

import pytest

from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.compaction import (
    COMPACT_INPUT_SCHEMA_V2,
    COMPACT_OUTPUT_SCHEMA_V2,
    MAX_COMPACT_REPAIR_FEEDBACK_CHARS,
    CompactAcceptedTruthV2,
    CompactAnswerAnchorV2,
    CompactCandidateDiagnosticV2,
    CompactCandidateV2,
    CompactCurrentInputV2,
    CompactDropReasonV2,
    CompactEvidenceFactV2,
    CompactExplicitDropV2,
    CompactForwardIntentStatusV2,
    CompactForwardIntentV2,
    CompactInputV2,
    CompactReferenceContinuityV2,
    CompactSessionSummaryV2,
    CompactSourceBoundaryEntryV2,
    CompactSourceKindV2,
    CompactValidationIssueCodeV2,
    CompactValidationReportV2,
)
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.context_events import (
    CompactorProposalManifestReference,
    build_context_compacted_payload,
)
from dayu.host.context_governance import (
    accept_compact_candidate_v2,
    build_compact_repair_feedback_v2,
)
from dayu.host.llm_compaction import _repair_feedback_prompt_json_vnext
from dayu.host.memory import (
    MemoryProjectionPolicy,
    default_memory_projection_policy,
    estimate_memory_size_units,
)

_REQUEST_DIGEST = "sha256:" + ("d" * 64)
_SOURCE_BOUNDARY_DIGEST = "sha256:" + ("e" * 64)


def test_fresh_v2_contract_uses_exact_schema_literals() -> None:
    """fresh contract 只接受当前 strict schema literal。

    :returns: ``None``。
    """

    assert COMPACT_INPUT_SCHEMA_V2 == "dayu.context_compaction.input.v2"
    assert COMPACT_OUTPUT_SCHEMA_V2 == "dayu.context_compaction.output.v2"


def test_input_json_separates_current_input_and_source_boundary() -> None:
    """current input 不分配 label，canonical refs 不进入 LLM-facing JSON。

    :returns: ``None``。
    """

    compact_input = _input()
    assert compact_input.source_labels == ("S1", "E1", "T1")
    assert compact_input.source_kind("E1") is CompactSourceKindV2.EVIDENCE_MATERIAL
    assert compact_input.source_kind("missing") is None
    assert compact_input.to_json() == {
        "schema": COMPACT_INPUT_SCHEMA_V2,
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
    }


def test_accept_owner_derives_exact_coverage_and_canonical_label_order() -> None:
    """Host 从业务区派生 coverage，并按 boundary 顺序 canonicalize labels。

    :returns: ``None``。
    """

    result = accept_compact_candidate_v2(
        _input(),
        _candidate(summary_labels=("T1", "S1"), fact_labels=("E1",)),
        default_memory_projection_policy(),
    )
    assert isinstance(result, CompactAcceptedTruthV2)
    assert result.candidate.session_summary is not None
    assert result.candidate.session_summary.source_labels == ("S1", "T1")
    assert result.represented_coverage.source_labels == ("S1", "E1", "T1")
    assert result.explicitly_dropped_coverage.source_labels == ()
    assert result.covered_source_refs == (
        "event:compact-1",
        "event:tool-result-1",
        "event:user-1",
    )
    assert result.current_input_ref == "event:current"


def test_accept_owner_canonicalizes_reverse_drops_for_committed_round_trip() -> None:
    """逆序 multi-drop 经 accept 与 committed parse 后仍按 root boundary 同源。

    :returns: ``None``。
    :raises AssertionError: accepted truth 或 durable payload drop 顺序漂移时抛出。
    """

    operation_id = "operation-drop-order"
    engine_run_id = "compactor-run-drop-order"
    candidate = replace(
        _candidate(
            summary_labels=("S1",),
            fact_labels=("E1",),
        ),
        evidence_facts=(),
        explicitly_dropped_sources=(
            CompactExplicitDropV2(
                source_label="T1",
                reason=CompactDropReasonV2.OUT_OF_SCOPE,
            ),
            CompactExplicitDropV2(
                source_label="E1",
                reason=CompactDropReasonV2.OUT_OF_SCOPE,
            ),
        ),
    )

    accepted = accept_compact_candidate_v2(
        _input(),
        candidate,
        default_memory_projection_policy(),
    )

    assert isinstance(accepted, CompactAcceptedTruthV2)
    expected_drop_labels = ("E1", "T1")
    assert tuple(
        drop.source_label
        for drop in accepted.candidate.explicitly_dropped_sources
    ) == expected_drop_labels
    assert (
        accepted.explicitly_dropped_coverage.source_labels
        == expected_drop_labels
    )
    payload = build_context_compacted_payload(
        operation_id=operation_id,
        accepted_attempt_number=1,
        compact_artifact_ref="compact-artifact:drop-order",
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
                iteration_id="drop-order-iteration",
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
                manifest_event_id="manifest-event-drop-order",
                manifest_payload_ref="manifest-payload-drop-order",
                manifest_digest=(
                    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
                compactor_input_projection_ref="projection-drop-order",
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
    assert tuple(
        drop.source_label
        for drop in parsed.accepted_candidate.explicitly_dropped_sources
    ) == expected_drop_labels
    assert (
        parsed.explicitly_dropped_coverage.source_labels
        == expected_drop_labels
    )


@pytest.mark.parametrize(
    ("candidate_factory", "expected_code"),
    (
        (
            lambda: _candidate(summary_labels=("UNKNOWN",), fact_labels=("E1",), drops=("S1", "T1")),
            CompactValidationIssueCodeV2.UNKNOWN_SOURCE_LABEL,
        ),
        (
            lambda: _candidate(summary_labels=("S1",), fact_labels=("T1",), drops=("E1",)),
            CompactValidationIssueCodeV2.SOURCE_KIND_MISMATCH,
        ),
        (
            lambda: _candidate(summary_labels=("S1",), fact_labels=("E1",)),
            CompactValidationIssueCodeV2.UNCOVERED_SOURCE,
        ),
        (
            lambda: _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",), drops=("E1",)),
            CompactValidationIssueCodeV2.REPRESENTED_AND_DROPPED,
        ),
        (
            lambda: _empty_candidate(diagnostics=False),
            CompactValidationIssueCodeV2.EMPTY_SEMANTIC_OUTPUT,
        ),
        (
            lambda: _empty_candidate(diagnostics=True),
            CompactValidationIssueCodeV2.DIAGNOSTICS_ONLY_OUTPUT,
        ),
        (
            lambda: _empty_candidate(diagnostics=False, drops=("S1", "E1", "T1")),
            CompactValidationIssueCodeV2.LOW_INFORMATION_OUTPUT,
        ),
    ),
)
def test_accept_owner_rejects_deterministic_invalid_matrix(
    candidate_factory: Callable[[], CompactCandidateV2],
    expected_code: CompactValidationIssueCodeV2,
) -> None:
    """coverage 与 information floor 的 invalid matrix 均由同一 owner 拒绝。

    :param candidate_factory: 待验收 candidate factory。
    :param expected_code: 期望问题码。
    :returns: ``None``。
    """

    result = accept_compact_candidate_v2(
        _input(),
        candidate_factory(),
        default_memory_projection_policy(),
    )
    assert isinstance(result, CompactValidationReportV2)
    assert expected_code in tuple(issue.code for issue in result.issues)


def test_duplicate_and_schema_provable_contradiction_are_rejected() -> None:
    """精确 duplicate 与 intent status contradiction 被稳定拒绝。

    :returns: ``None``。
    """

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    candidate = replace(
        candidate,
        forward_intents=(
            CompactForwardIntentV2(
                intent_type="next_step_note",
                text="继续 分析",
                status=CompactForwardIntentStatusV2.OPEN,
                source_labels=("T1",),
            ),
            CompactForwardIntentV2(
                intent_type="next_step_note",
                text="继续  分析",
                status=CompactForwardIntentStatusV2.BLOCKED,
                source_labels=("T1",),
            ),
        ),
    )
    result = accept_compact_candidate_v2(_input(), candidate, default_memory_projection_policy())
    assert isinstance(result, CompactValidationReportV2)
    codes = tuple(issue.code for issue in result.issues)
    assert CompactValidationIssueCodeV2.DUPLICATE_SEMANTIC_ITEM in codes
    assert CompactValidationIssueCodeV2.CONTRADICTORY_SEMANTIC_ITEM in codes


def test_similar_but_not_equal_text_is_not_fuzzy_deduplicated() -> None:
    """自然语言相似但不相等的文本不由 deterministic validator 猜测。

    :returns: ``None``。
    """

    candidate = _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",))
    candidate = replace(
        candidate,
        reference_continuity=(
            CompactReferenceContinuityV2(text="第一家公司", reason="local_reference", source_labels=("T1",)),
            CompactReferenceContinuityV2(text="首家公司", reason="local_reference", source_labels=("T1",)),
        ),
    )
    result = accept_compact_candidate_v2(_input(), candidate, default_memory_projection_policy())
    assert isinstance(result, CompactAcceptedTruthV2)


def test_memory_policy_item_and_size_caps_use_same_policy_owner() -> None:
    """Context Governance 直接使用 Memory policy 的边界值。

    :returns: ``None``。
    """

    policy = replace(
        default_memory_projection_policy(),
        evidence_fact_item_cap=1,
        evidence_fact_char_cap=len("收入增长 10%"),
    )
    accepted = accept_compact_candidate_v2(
        _input(),
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        policy,
    )
    assert isinstance(accepted, CompactAcceptedTruthV2)
    too_large = replace(
        _candidate(summary_labels=("S1", "T1"), fact_labels=("E1",)),
        evidence_facts=(
            CompactEvidenceFactV2(
                claim="收入增长 10%+",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )
    rejected = accept_compact_candidate_v2(_input(), too_large, policy)
    assert isinstance(rejected, CompactValidationReportV2)
    assert CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


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
    accepted = accept_compact_candidate_v2(
        _cap_input(),
        _cap_candidate(section, ("first",)),
        policy,
    )
    rejected = accept_compact_candidate_v2(
        _cap_input(),
        _cap_candidate(section, ("first", "second")),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV2)
    assert isinstance(rejected, CompactValidationReportV2)
    assert CompactValidationIssueCodeV2.POLICY_ITEM_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


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
    accepted = accept_compact_candidate_v2(
        _cap_input(),
        accepted_candidate,
        policy,
    )
    rejected = accept_compact_candidate_v2(
        _cap_input(),
        _cap_candidate(section, ("abcde",)),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV2)
    assert isinstance(rejected, CompactValidationReportV2)
    assert CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


def test_session_summary_size_cap_accepts_equal_and_rejects_plus_one() -> None:
    """session summary 使用同一 estimator 验证 == cap 与 +1。"""

    candidate = _cap_candidate("evidence_facts", ("fact",))
    accepted_candidate = replace(
        candidate,
        session_summary=CompactSessionSummaryV2(
            text="abcd",
            source_labels=("E1", "A1", "T1"),
        ),
    )
    policy = replace(
        default_memory_projection_policy(),
        session_summary_char_cap=estimate_memory_size_units("abcd").units,
    )
    accepted = accept_compact_candidate_v2(
        _cap_input(),
        accepted_candidate,
        policy,
    )
    rejected = accept_compact_candidate_v2(
        _cap_input(),
        replace(
            accepted_candidate,
            session_summary=CompactSessionSummaryV2(
                text="abcde",
                source_labels=("E1", "A1", "T1"),
            ),
        ),
        policy,
    )

    assert isinstance(accepted, CompactAcceptedTruthV2)
    assert isinstance(rejected, CompactValidationReportV2)
    assert CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED in tuple(issue.code for issue in rejected.issues)


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

    rejected = accept_compact_candidate_v2(_cap_input(), candidate, policy)

    assert isinstance(rejected, CompactValidationReportV2)
    assert len(rejected.issues) == 9
    feedback = build_compact_repair_feedback_v2(
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
        ("evidence_facts", evidence_texts, "各 claim 字符数之和"),
        (
            "answer_anchors",
            answer_texts,
            "每项 title、一个换行符和 detail 的字符数之和",
        ),
        ("forward_intents", forward_texts, "各 text 字符数之和"),
        ("reference_continuity", reference_texts, "各 text 字符数之和"),
    )
    expected_messages: dict[
        tuple[CompactValidationIssueCodeV2, str],
        str,
    ] = {
        (
            CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED,
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
            (CompactValidationIssueCodeV2.POLICY_ITEM_CAP_EXCEEDED, path)
        ] = (
            f"{section} 当前为 {len(texts)} 项，上限 {item_cap} 项；"
            f"请删减或合并 {section}，只保留不超过 {item_cap} 项。"
        )
        expected_messages[
            (CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED, path)
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


def _cap_input() -> CompactInputV2:
    """构造覆盖四个 Memory section source-kind 的 input。

    :returns: deterministic cap test input。
    """

    return CompactInputV2(
        schema=COMPACT_INPUT_SCHEMA_V2,
        current_input=CompactCurrentInputV2(
            source_ref="event:current-cap",
            readable_text="继续分析",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV2(
                source_label="E1",
                source_kind=CompactSourceKindV2.EVIDENCE_MATERIAL,
                source_refs=("event:evidence-cap",),
                readable_text="evidence",
            ),
            CompactSourceBoundaryEntryV2(
                source_label="A1",
                source_kind=CompactSourceKindV2.ANSWER_MATERIAL,
                source_refs=("event:answer-cap",),
                readable_text="answer",
            ),
            CompactSourceBoundaryEntryV2(
                source_label="T1",
                source_kind=CompactSourceKindV2.TRACE_MATERIAL,
                source_refs=("event:trace-cap",),
                readable_text="trace",
            ),
        ),
    )


def _cap_candidate(
    section: _CapSection,
    texts: tuple[str, ...],
) -> CompactCandidateV2:
    """构造仅改变一个被测 section item 数量/文本的完整 candidate。

    :param section: 被测 semantic section。
    :param texts: 被测 section 的业务文本。
    :returns: exact coverage candidate。
    """

    return CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=CompactSessionSummaryV2(
            text="baseline",
            source_labels=("E1", "A1", "T1"),
        ),
        evidence_facts=(
            tuple(
                CompactEvidenceFactV2(
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
                CompactAnswerAnchorV2(
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
                CompactForwardIntentV2(
                    intent_type="next_step_note",
                    text=text,
                    status=CompactForwardIntentStatusV2.OPEN,
                    source_labels=("T1",),
                )
                for text in texts
            )
            if section == "forward_intents"
            else ()
        ),
        reference_continuity=(
            tuple(
                CompactReferenceContinuityV2(
                    text=text,
                    reason="recent_state",
                    source_labels=("T1",),
                )
                for text in texts
            )
            if section == "reference_continuity"
            else ()
        ),
        diagnostics=(),
        explicitly_dropped_sources=(),
    )


def _all_section_cap_candidate() -> CompactCandidateV2:
    """构造 summary 与四个可计量 section 同时超过最小 cap 的 candidate。

    :returns: exact coverage 且只产生九条 policy cap issues 的 candidate。
    :raises Exception: 不主动抛出异常。
    """

    return CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=CompactSessionSummaryV2(
            text="summary-over-cap",
            source_labels=("E1", "A1", "T1"),
        ),
        evidence_facts=(
            CompactEvidenceFactV2(claim="evidence-one", support_labels=("E1",)),
            CompactEvidenceFactV2(claim="evidence-two", support_labels=("E1",)),
        ),
        answer_anchors=(
            CompactAnswerAnchorV2(
                title="title-one",
                detail="detail-one",
                source_labels=("A1",),
            ),
            CompactAnswerAnchorV2(
                title="title-two",
                detail="detail-two",
                source_labels=("A1",),
            ),
        ),
        forward_intents=(
            CompactForwardIntentV2(
                intent_type="next_step",
                text="forward-one",
                status=CompactForwardIntentStatusV2.OPEN,
                source_labels=("T1",),
            ),
            CompactForwardIntentV2(
                intent_type="next_step",
                text="forward-two",
                status=CompactForwardIntentStatusV2.OPEN,
                source_labels=("T1",),
            ),
        ),
        reference_continuity=(
            CompactReferenceContinuityV2(
                text="reference-one",
                reason="继续保留第一个指代",
                source_labels=("T1",),
            ),
            CompactReferenceContinuityV2(
                text="reference-two",
                reason="继续保留第二个指代",
                source_labels=("T1",),
            ),
        ),
        diagnostics=(),
        explicitly_dropped_sources=(),
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


def _input() -> CompactInputV2:
    """构造 deterministic v2 input。

    :returns: v2 input。
    """

    return CompactInputV2(
        schema=COMPACT_INPUT_SCHEMA_V2,
        current_input=CompactCurrentInputV2(
            source_ref="event:current",
            readable_text="分析本期结果",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV2(
                source_label="S1",
                source_kind=CompactSourceKindV2.PREVIOUS_SESSION_SUMMARY,
                source_refs=("event:compact-1",),
                readable_text="上一轮摘要",
            ),
            CompactSourceBoundaryEntryV2(
                source_label="E1",
                source_kind=CompactSourceKindV2.EVIDENCE_MATERIAL,
                source_refs=("event:tool-result-1",),
                readable_text="收入增长 10%",
            ),
            CompactSourceBoundaryEntryV2(
                source_label="T1",
                source_kind=CompactSourceKindV2.TRACE_MATERIAL,
                source_refs=("event:user-1",),
                readable_text="用户追问利润率",
            ),
        ),
    )


def _candidate(
    *,
    summary_labels: tuple[str, ...],
    fact_labels: tuple[str, ...],
    drops: tuple[str, ...] = (),
) -> CompactCandidateV2:
    """构造可定制 coverage 的 candidate。

    :param summary_labels: summary labels。
    :param fact_labels: fact support labels。
    :param drops: explicit drop labels。
    :returns: v2 candidate。
    """

    return CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=CompactSessionSummaryV2(
            text="保留会话背景",
            source_labels=summary_labels,
        ),
        evidence_facts=(
            CompactEvidenceFactV2(
                claim="收入增长 10%",
                support_labels=fact_labels,
                context_labels=(),
            ),
        ),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
        diagnostics=(),
        explicitly_dropped_sources=tuple(
            CompactExplicitDropV2(
                source_label=label,
                reason=CompactDropReasonV2.OUT_OF_SCOPE,
            )
            for label in drops
        ),
    )


def _empty_candidate(
    *,
    diagnostics: bool,
    drops: tuple[str, ...] = (),
) -> CompactCandidateV2:
    """构造无业务语义 candidate。

    :param diagnostics: 是否带 diagnostic。
    :param drops: explicit drop labels。
    :returns: v2 candidate。
    """

    return CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=None,
        evidence_facts=(),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
        diagnostics=(
            (CompactCandidateDiagnosticV2(code="insufficient", message="缺少业务语义", source_labels=()),)
            if diagnostics
            else ()
        ),
        explicitly_dropped_sources=tuple(
            CompactExplicitDropV2(source_label=label, reason=CompactDropReasonV2.OUT_OF_SCOPE) for label in drops
        ),
    )
