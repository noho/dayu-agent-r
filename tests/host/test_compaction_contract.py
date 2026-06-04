"""vNext compact public contract 测试。"""

from __future__ import annotations

import pytest

import dayu.host.compaction as compaction_module
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    conversation_compact_input_vnext_from_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CompactMaterialBlockKind,
    CompactQualityIssueVNext,
    CompactSegmentTrigger,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
    EvidenceBackedFactCandidateVNext,
    FactEvidenceKindVNext,
    SessionSummaryCandidateVNext,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_governance import check_conversation_compact_output_vnext
from dayu.host.context_policy import ContextCompactionTriggerSource
from tests.host.fake_cancellation import StubCancellationToken
from tests.host.fake_compaction import FakeContextCompactor


@pytest.mark.asyncio
async def test_context_compactor_single_public_compact_returns_vnext_output() -> None:
    """ContextCompactor 只通过 compact() 返回 vNext output。"""

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())

    assert isinstance(candidate, ConversationCompactOutputVNext)
    assert candidate.schema_version == CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT
    assert len(candidate.evidence_backed_facts) == 1
    assert candidate.evidence_backed_facts[0].evidence_labels == ("E1",)
    assert len(candidate.answer_anchors) == 1
    assert candidate.answer_anchors[0].answer_source_labels == ("A1",)
    instance_methods = set(dir(FakeContextCompactor()))
    assert "compact_request_vnext" not in instance_methods
    assert "compact_vnext" not in instance_methods


def test_material_pack_json_and_llm_json_use_vnext_fields_only() -> None:
    """CompactMaterialPack JSON 不再输出旧 stable/history/evidence input 字段。"""

    pack = _request().material_pack

    for payload in (pack.to_json(), pack.llm_json()):
        assert isinstance(payload, dict)
        assert "previous_compacted_view" in payload
        assert "trace_material" in payload
        assert "evidence_material" in payload
        assert "answer_material" in payload
        assert "stable_input" not in payload
        assert "history_input" not in payload
        assert "evidence_input" not in payload


@pytest.mark.asyncio
async def test_vnext_quality_checker_accepts_fake_candidate() -> None:
    """vNext accept barrier 接受引用合法 section label 的 candidate。"""

    request = _request()
    compact_input = conversation_compact_input_vnext_from_material_pack(
        request.material_pack
    )
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())

    result = check_conversation_compact_output_vnext(compact_input, candidate)

    assert result.accepted is True
    assert result.rejection_reasons == ()


def test_vnext_quality_checker_rejects_current_input_anchor_citation() -> None:
    """vNext accept barrier 禁止 candidate 引用 current input anchor。"""

    compact_input = _compact_input()
    candidate = _minimal_candidate(
        session_summary=SessionSummaryCandidateVNext(
            summary_text="引用当前输入必须被拒绝",
            source_labels=("C1",),
        )
    )

    result = check_conversation_compact_output_vnext(compact_input, candidate)

    assert result.accepted is False
    assert CompactQualityIssueVNext.CURRENT_INPUT_ANCHOR_CITED in result.rejection_reasons


def test_vnext_quality_checker_rejects_unknown_and_stale_labels() -> None:
    """vNext accept barrier 区分未知 label 与旧 material label。"""

    compact_input = _compact_input()
    unknown = _minimal_candidate(
        session_summary=SessionSummaryCandidateVNext(
            summary_text="未知 label",
            source_labels=("Z1",),
        )
    )
    stale = _minimal_candidate(
        session_summary=SessionSummaryCandidateVNext(
            summary_text="旧 history label",
            source_labels=("H99",),
        )
    )

    unknown_result = check_conversation_compact_output_vnext(compact_input, unknown)
    stale_result = check_conversation_compact_output_vnext(compact_input, stale)

    assert CompactQualityIssueVNext.UNKNOWN_SOURCE_LABEL in unknown_result.rejection_reasons
    assert CompactQualityIssueVNext.STALE_SOURCE_LABEL in stale_result.rejection_reasons


def test_vnext_quality_checker_rejects_cross_section_label() -> None:
    """vNext accept barrier 禁止 answer anchor 引用 evidence material label。"""

    compact_input = _compact_input()
    candidate = _minimal_candidate(
        answer_anchors=(
            AnswerAnchorCandidateVNext(
                anchor_title="上一轮答案",
                anchor_items=(AnswerAnchorChildVNext(display_text="answer"),),
                answer_source_labels=("E1",),
            ),
        )
    )

    result = check_conversation_compact_output_vnext(compact_input, candidate)

    assert result.accepted is False
    assert CompactQualityIssueVNext.CROSS_SECTION_LABEL in result.rejection_reasons


def test_vnext_candidate_schema_rejects_missing_required_source_label() -> None:
    """vNext candidate typed 边界拒绝必需 source label 缺失。"""

    with pytest.raises(ValueError, match="source_labels must be non-empty"):
        SessionSummaryCandidateVNext(
            summary_text="缺失 source label 的摘要",
            source_labels=(),
        )


def test_vnext_quality_result_requires_reason_for_rejection() -> None:
    """vNext quality result 拒绝态必须给出拒绝原因。"""

    from dayu.host.compaction import CompactQualityCheckResultVNext

    with pytest.raises(ValueError, match="Rejected vNext quality result"):
        CompactQualityCheckResultVNext(accepted=False, rejection_reasons=())


def test_compaction_public_exports_do_not_include_old_compact_contract() -> None:
    """compaction public exports 不再暴露旧 candidate contract。"""

    old_names = {
        "CompactionCandidate",
        "EpisodeSummaryCandidate",
        "PinnedStatePatchCandidate",
        "PinnedPatchOperation",
        "PreservationEvidence",
        "EvidenceBackedFactCandidate",
        "MinimumPreserveItemCandidate",
        "CompactQualityIssue",
        "CompactQualityCheckResult",
        "ContextCompactorVNext",
    }

    exported = set(compaction_module.__all__)

    assert old_names.isdisjoint(exported)


def test_vnext_candidate_digest_is_canonical() -> None:
    """ConversationCompactOutputVNext digest 随 canonical JSON 稳定生成。"""

    candidate = _minimal_candidate()
    payload = candidate.to_json()
    assert isinstance(payload, dict)

    assert candidate.digest().startswith("sha256:")
    assert payload["schema_version"] == CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT


def test_initial_segment_selection_diagnostics_do_not_expose_slice_name() -> None:
    """初始 material 诊断值不泄漏历史 implementation slice 名称。"""

    selection = initial_segment_selection(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=3,
        material_pack=_request().material_pack,
    )

    diagnostic_values = (
        selection.policy_digest,
        *selection.deterministic_reason_codes,
    )
    assert not any("slice1" in value for value in diagnostic_values)


def _compact_input() -> ConversationCompactInputVNext:
    """构造 vNext compact input。

    :returns: vNext compact input。
    """

    return conversation_compact_input_vnext_from_material_pack(_request().material_pack)


def _minimal_candidate(
    *,
    session_summary: SessionSummaryCandidateVNext | None = None,
    answer_anchors: tuple[AnswerAnchorCandidateVNext, ...] = (),
) -> ConversationCompactOutputVNext:
    """构造最小 vNext candidate。

    :param session_summary: session summary candidate。
    :param answer_anchors: answer anchor candidates。
    :returns: vNext compact output。
    """

    return ConversationCompactOutputVNext(
        schema_version=CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
        session_summary=session_summary,
        evidence_backed_facts=(
            EvidenceBackedFactCandidateVNext(
                claim_text="Fact from accepted evidence",
                evidence_labels=("E1",),
                evidence_kind=FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL,
                source_labels=("E1",),
            ),
        ),
        answer_anchors=answer_anchors,
        forward_intents=(),
        reference_continuity_items=(),
        diagnostics=(),
    )


def _request() -> CompactionRequest:
    """构造标准 compaction request。

    :returns: compaction request。
    """

    material_pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="分析公司现金流",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-user-old",
                text="上一轮用户问题",
                kind=CompactMaterialBlockKind.USER_INPUT,
            ),
            InitialHistoryMaterial(
                canonical_source_ref="event-answer-old",
                text="上一轮助手答案",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-1",
                accepted_evidence_id="evidence:accepted-1",
                tool_result_event_ref="event-tool-result-1",
                tool_call_event_ref="event-tool-call-1",
                readable_tool_name="fins.search",
                readable_query_text="cash flow",
                raw_result_text="经营现金流同比增长",
                readable_source_text="2025 年年报现金流量表",
                payload_refs=("payload:evidence-1",),
            ),
        ),
    )
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-contract",
        run_id="run-contract",
        attempt_id=None,
        execution_id=None,
        memory_snapshot_cursor=None,
        material_pack=material_pack,
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=3,
            material_pack=material_pack,
        ),
        evidence_backed_fact_refs=(),
        recent_raw_turn_refs=("event-current",),
        older_raw_turn_refs=("event-user-old", "event-answer-old"),
        existing_episode_summary_refs=(),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=900,
            input_budget_tokens=4096,
            soft_threshold_tokens=3200,
            hard_threshold_tokens=3900,
            safety_margin_tokens=200,
            estimator_digest="estimate-digest",
            overage_reason=None,
        ),
    )
