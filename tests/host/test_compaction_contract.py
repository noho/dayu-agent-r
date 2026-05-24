"""Phase 10 Slice 2 compaction contract 测试。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactInputRange,
    CompactMaterialBlockKind,
    CompactMaterialPack,
    CompactQualityCheckResult,
    CompactQualityIssue,
    CompactSegmentTrigger,
    CompactionRequest,
    EvidenceBackedFactCandidate,
    EvidenceBackedFactKind,
    MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS,
    MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS,
    MinimumPreserveItemCandidate,
    MinimumPreserveReason,
    PinnedPatchOperation,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_governance import check_compaction_candidate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
)
from tests.host.fake_cancellation import StubCancellationToken
from tests.host.fake_compaction import FakeContextCompactor


@pytest.mark.asyncio
async def test_fake_compactor_produces_typed_candidates_and_evidence() -> None:
    """Fake compactor 产生 summary、pinned patch 与 preservation evidence。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    result = check_compaction_candidate(request, candidate)

    assert candidate.episode_summary_candidate.candidate_id == "fake-summary:run-1"
    assert candidate.pinned_state_patch_candidate.current_goal.operation is (
        PinnedPatchOperation.REPLACE
    )
    assert len(candidate.preservation_evidence) == 1
    assert result.accepted is True


@pytest.mark.asyncio
async def test_fake_compactor_observes_cancellation_token() -> None:
    """Fake compactor 观察测试 cancellation token，避免测试吞掉取消语义。

    :returns: ``None``。
    """

    with pytest.raises(RuntimeError, match="compaction cancelled"):
        await FakeContextCompactor().compact(
            _request(), StubCancellationToken("cancelled-by-test")
        )


@pytest.mark.asyncio
async def test_fact_candidates_can_reference_evidence_materials() -> None:
    """Fact candidates 可以引用 request 中的 evidence material。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    result = check_compaction_candidate(request, candidate)

    assert result.accepted is True
    assert request.material_pack.evidence_labels == ("E1", "E2")
    assert request.canonical_evidence_refs == (
        "evidence:accepted-1",
        "evidence:accepted-2",
    )
    assert tuple(
        fact.evidence_refs for fact in candidate.evidence_backed_fact_candidates
    ) == (("evidence:accepted-1",), ("evidence:accepted-2",))
    assert tuple(
        fact.claim_text for fact in candidate.evidence_backed_fact_candidates
    ) == (
        "Canonical evidence material: canonical evidence raw content accepted-1",
        "Canonical evidence material: canonical evidence raw content accepted-2",
    )


@pytest.mark.asyncio
async def test_fake_compactor_caps_budget_below_hard_threshold_when_preserved_refs_dominate() -> None:
    """Fake compactor 保持 accepted candidate 位于 hard threshold 内。

    :returns: ``None``。
    """

    request = _request()
    budget = replace(
        request.budget_before_compact,
        estimated_input_tokens=2000,
        hard_threshold_tokens=950,
    )
    request = replace(request, budget_before_compact=budget)

    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())

    assert candidate.budget_after_compact == budget.hard_threshold_tokens - 1


@pytest.mark.asyncio
async def test_quality_rejects_missing_current_user_input() -> None:
    """Quality check 拒绝丢失当前用户输入。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request, StubCancellationToken()),
        retained_current_user_input_ref=None,
    )

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.CURRENT_USER_INPUT_MISSING in result.rejection_reasons


@pytest.mark.asyncio
async def test_quality_rejects_missing_canonical_evidence_refs() -> None:
    """Quality check 拒绝丢失 canonical evidence refs。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request, StubCancellationToken()),
        preserved_canonical_evidence_refs=("evidence:accepted-1",),
    )

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.ACCEPTED_EVIDENCE_REFS_MISSING in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_missing_preservation_evidence() -> None:
    """Quality check 拒绝缺失 preservation evidence。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request, StubCancellationToken()),
        preservation_evidence=(),
    )

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.PRESERVATION_EVIDENCE_MISSING in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_missing_evidence_anchor_retention() -> None:
    """Quality check 拒绝 evidence 未保留当前输入 anchor。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    evidence = replace(
        candidate.preservation_evidence[0],
        material_source_refs=("event-old",),
    )
    candidate = replace(candidate, preservation_evidence=(evidence,))

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.EVIDENCE_ANCHOR_NOT_RETAINED in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_invalid_pinned_patch_tri_state() -> None:
    """Quality check 拒绝非法 pinned patch 三态。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_patch = replace(
        candidate.pinned_state_patch_candidate,
        current_goal=PinnedTextFieldPatch(
            operation=PinnedPatchOperation.REPLACE,
            value=None,
            evidence_refs=("fake-evidence:run-1:primary",),
        ),
    )
    candidate = replace(candidate, pinned_state_patch_candidate=invalid_patch)

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.PINNED_PATCH_TRI_STATE_INVALID in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_pinned_patch_unknown_evidence_ref() -> None:
    """Quality check 拒绝 patch 引用不存在的 input evidence。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_patch = replace(
        candidate.pinned_state_patch_candidate,
        open_questions=PinnedStringTupleFieldPatch(
            operation=PinnedPatchOperation.REPLACE,
            value=("continue-current-run",),
            evidence_refs=("missing-evidence",),
        ),
    )
    candidate = replace(candidate, pinned_state_patch_candidate=invalid_patch)

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.PINNED_PATCH_EVIDENCE_REF_MISSING in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_marks_open_questions_lost_when_clear_without_summary_questions() -> None:
    """CLEAR 且 summary 未保留 open questions 时不得误报 retained。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    summary = replace(candidate.episode_summary_candidate, open_questions=())
    pinned_patch = replace(
        candidate.pinned_state_patch_candidate,
        open_questions=PinnedStringTupleFieldPatch(
            operation=PinnedPatchOperation.CLEAR,
            value=None,
            evidence_refs=(
                candidate.pinned_state_patch_candidate.open_questions.evidence_refs
            ),
        ),
    )
    candidate = replace(
        candidate,
        episode_summary_candidate=summary,
        pinned_state_patch_candidate=pinned_patch,
    )

    result = check_compaction_candidate(request, candidate)

    assert result.open_questions_retained is False
    assert result.accepted is False
    assert CompactQualityIssue.OPEN_QUESTIONS_MISSING in result.rejection_reasons


@pytest.mark.asyncio
async def test_quality_rejects_summary_pretending_to_create_evidence_backed_fact() -> None:
    """Quality check 拒绝 episode summary 伪造 evidence-backed fact。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_summary = replace(
        candidate.episode_summary_candidate,
        proposed_evidence_backed_fact_refs=("summary-made-fact",),
    )
    candidate = replace(candidate, episode_summary_candidate=invalid_summary)

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_summary_confirmed_fact_ref_to_accepted_evidence() -> None:
    """Summary confirmed_fact_refs 不能把 canonical evidence id 当 stable fact ref。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_summary = replace(
        candidate.episode_summary_candidate,
        confirmed_fact_refs=("evidence:accepted-1",),
    )
    candidate = replace(candidate, episode_summary_candidate=invalid_summary)

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_fact_candidate_referencing_non_evidence_ref() -> None:
    """Fact candidate 不能引用 user / assistant / summary 等非 evidence refs。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_fact = replace(
        candidate.evidence_backed_fact_candidates[0],
        evidence_refs=("event-current",),
    )
    candidate = replace(candidate, evidence_backed_fact_candidates=(invalid_fact,))

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_missing_fact_candidate_for_accepted_evidence() -> None:
    """Canonical evidence 没有有效 fact candidate 时只产生诊断拒绝。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request, StubCancellationToken()),
        evidence_backed_fact_candidates=(),
    )

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.ACCEPTED_EVIDENCE_FACT_CANDIDATE_MISSING in (
        result.rejection_reasons
    )


def test_fact_candidate_rejects_empty_claim_text() -> None:
    """Fact candidate 拒绝空 claim_text。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="claim_text"):
        EvidenceBackedFactCandidate(
            candidate_id="fact-1",
            claim_text=" ",
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=("evidence:accepted-1",),
            attributes={},
        )


def test_fact_candidate_rejects_overlong_claim_text() -> None:
    """Fact candidate 拒绝过长 claim_text。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="claim_text"):
        EvidenceBackedFactCandidate(
            candidate_id="fact-1",
            claim_text="x" * (MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS + 1),
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=("evidence:accepted-1",),
            attributes={},
        )


def test_fact_candidate_rejects_missing_evidence_refs() -> None:
    """Fact candidate 拒绝空 evidence_refs。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="evidence_refs"):
        EvidenceBackedFactCandidate(
            candidate_id="fact-1",
            claim_text="Revenue was reported.",
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=(),
            attributes={},
        )


def test_minimum_preserve_item_rejects_overlong_text() -> None:
    """Minimum preserve item 拒绝过长 text。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="text"):
        MinimumPreserveItemCandidate(
            item_id="preserve-1",
            label="current input",
            text="x" * (MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS + 1),
            source_refs=("event-current",),
            preserve_reason=MinimumPreserveReason.NEEDED_FOR_RECENT_REFERENCE,
        )


@pytest.mark.asyncio
async def test_quality_rejects_minimum_preserve_source_outside_compact_input() -> None:
    """Minimum preserve item source_refs 必须来自 compact input。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_item = replace(
        candidate.minimum_preserve_item_candidates[0],
        source_refs=("unknown-material-source",),
    )
    candidate = replace(candidate, minimum_preserve_item_candidates=(invalid_item,))

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.MINIMUM_PRESERVE_ITEM_CANDIDATE_INVALID in (
        result.rejection_reasons
    )


@pytest.mark.asyncio
async def test_quality_rejects_compact_range_outside_request() -> None:
    """Quality check 拒绝不属于 older raw turns 的 compact range 声明。"""

    request = _request()
    candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
    invalid_range = CompactInputRange(
        range_ref="range-outside",
        start_input_ref="event-current",
        end_input_ref="event-current",
    )
    candidate = replace(candidate, summarized_ranges=(invalid_range,))

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.COMPACT_RANGE_OUTSIDE_REQUEST in (
        result.rejection_reasons
    )


def test_compaction_request_rejects_wrong_material_pack_type() -> None:
    """CompactionRequest 对非法 material pack 类型抛出 TypeError。

    :returns: ``None``。
    """

    with pytest.raises(TypeError, match="material_pack"):
        _request(material_pack=cast(CompactMaterialPack, _request().segment_selection))


def test_reactive_compaction_request_requires_attempt_and_execution_refs() -> None:
    """Reactive compaction request 必须携带 attempt 与 execution ref。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="attempt_id"):
        _request(
            trigger_source=ContextCompactionTriggerSource.REACTIVE,
            attempt_id=None,
            execution_id="execution-1",
        )

    with pytest.raises(ValueError, match="execution_id"):
        _request(
            trigger_source=ContextCompactionTriggerSource.REACTIVE,
            attempt_id="attempt-1",
            execution_id=None,
        )

    with pytest.raises(ValueError, match="attempt_id"):
        _request(
            trigger_source=ContextCompactionTriggerSource.REACTIVE,
            attempt_id="",
            execution_id="execution-1",
        )

    with pytest.raises(ValueError, match="execution_id"):
        _request(
            trigger_source=ContextCompactionTriggerSource.REACTIVE,
            attempt_id="attempt-1",
            execution_id="",
        )


def test_compact_quality_result_rejects_accepted_with_rejection_reasons() -> None:
    """Accepted quality result 不得携带拒绝原因。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="Accepted quality result"):
        CompactQualityCheckResult(
            accepted=True,
            rejection_reasons=(CompactQualityIssue.CURRENT_USER_INPUT_MISSING,),
            current_user_input_retained=True,
            canonical_evidence_refs_retained=True,
            evidence_backed_fact_candidates_accepted=True,
            minimum_preserve_items_accepted=True,
            evidence_anchors_retained=True,
            open_questions_retained=True,
            retained_canonical_evidence_refs=(),
            dropped_ranges=(),
            summarized_ranges=(),
        )


def test_compact_quality_result_rejects_rejected_without_rejection_reasons() -> None:
    """Rejected quality result 必须携带至少一个拒绝原因。

    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="Rejected quality result"):
        CompactQualityCheckResult(
            accepted=False,
            rejection_reasons=(),
            current_user_input_retained=False,
            canonical_evidence_refs_retained=True,
            evidence_backed_fact_candidates_accepted=True,
            minimum_preserve_items_accepted=True,
            evidence_anchors_retained=True,
            open_questions_retained=True,
            retained_canonical_evidence_refs=(),
            dropped_ranges=(),
            summarized_ranges=(),
        )


def _request(
    *,
    trigger_source: ContextCompactionTriggerSource = (
        ContextCompactionTriggerSource.PROACTIVE
    ),
    attempt_id: str | None = None,
    execution_id: str | None = None,
    material_pack: CompactMaterialPack | None = None,
) -> CompactionRequest:
    """构造标准 compaction request。

    :param trigger_source: compaction 触发来源。
    :param attempt_id: reactive compaction 对应 Attempt id。
    :param execution_id: reactive compaction 对应 execution id。
    :param material_pack: material pack；为 ``None`` 时使用默认 pack。
    :returns: compaction request。
    """

    resolved_material_pack = material_pack
    if resolved_material_pack is None:
        resolved_material_pack = _material_pack()
    segment_selection = initial_segment_selection(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=2,
        material_pack=_material_pack(),
    )
    if material_pack is None:
        segment_selection = initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=2,
            material_pack=resolved_material_pack,
        )

    return CompactionRequest(
        trigger_source=trigger_source,
        session_id="session-1",
        run_id="run-1",
        attempt_id=attempt_id,
        execution_id=execution_id,
        memory_snapshot_cursor=7,
        material_pack=resolved_material_pack,
        segment_selection=segment_selection,
        evidence_backed_fact_refs=("fact-existing-1",),
        recent_raw_turn_refs=("event-current",),
        older_raw_turn_refs=("event-old",),
        existing_episode_summary_refs=("summary-prev",),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=900,
            input_budget_tokens=1000,
            soft_threshold_tokens=800,
            hard_threshold_tokens=950,
            safety_margin_tokens=200,
            estimator_digest="estimate-digest",
            overage_reason=None,
        ),
    )


def _material_pack():
    """构造标准 material pack。

    :returns: material pack。
    """

    return build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="分析 A 公司 2025 年年报",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-old",
                text="上一轮回答摘要",
                kind=CompactMaterialBlockKind.RAW_ASSISTANT_TURN,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-1",
                accepted_evidence_id="evidence:accepted-1",
                tool_result_event_ref="event-tool-result-accepted-1",
                tool_call_event_ref="event-tool-call-accepted-1",
                readable_tool_name="fins.search",
                readable_query_text="accepted tool query",
                raw_result_text="canonical evidence raw content accepted-1",
                readable_source_text="accepted tool evidence",
                payload_refs=("payload:accepted-1",),
            ),
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-2",
                accepted_evidence_id="evidence:accepted-2",
                tool_result_event_ref="event-tool-result-accepted-2",
                tool_call_event_ref="event-tool-call-accepted-2",
                readable_tool_name="fins.search",
                readable_query_text="accepted tool query",
                raw_result_text="canonical evidence raw content accepted-2",
                readable_source_text="accepted tool evidence",
                payload_refs=("payload:accepted-2",),
            ),
        ),
    )


def _accepted_evidence_envelope(suffix: str) -> AcceptedEvidenceEnvelope:
    """构造测试用 canonical evidence envelope。

    :param suffix: evidence 与 producer ref 后缀。
    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{suffix}",
        producer_event_ref=f"event-tool-result-{suffix}",
        tool_name="fins.search",
        tool_call_id=f"tool-call-{suffix}",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=f"event-tool-call-{suffix}",
            normalized_arguments_digest=(
                "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            semantic_input_digest=(
                "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            ),
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=f"payload:{suffix}",
            payload_digest=(
                "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
            ),
            outcome_digest=(
                "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
            ),
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )
