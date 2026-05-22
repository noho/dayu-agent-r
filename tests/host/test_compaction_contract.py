"""Phase 10 Slice 2 compaction contract 测试。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from dayu.host.compaction import (
    CompactInputRange,
    CompactQualityCheckResult,
    CompactQualityIssue,
    CompactionRequest,
    CurrentMessageSummary,
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
from tests.host.fake_compaction import FakeContextCompactor


@pytest.mark.asyncio
async def test_fake_compactor_produces_typed_candidates_and_evidence() -> None:
    """Fake compactor 产生 summary、pinned patch 与 preservation evidence。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request)
    result = check_compaction_candidate(request, candidate)

    assert candidate.episode_summary_candidate.candidate_id == "fake-summary:run-1"
    assert candidate.pinned_state_patch_candidate.current_goal.operation is (
        PinnedPatchOperation.REPLACE
    )
    assert len(candidate.preservation_evidence) == 1
    assert result.accepted is True


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

    candidate = await FakeContextCompactor().compact(request)

    assert candidate.budget_after_compact == budget.hard_threshold_tokens - 1


@pytest.mark.asyncio
async def test_quality_rejects_missing_current_user_input() -> None:
    """Quality check 拒绝丢失当前用户输入。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request),
        retained_current_user_input_ref=None,
    )

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.CURRENT_USER_INPUT_MISSING in result.rejection_reasons


@pytest.mark.asyncio
async def test_quality_rejects_missing_accepted_evidence_refs() -> None:
    """Quality check 拒绝丢失 accepted evidence refs。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request),
        preserved_accepted_evidence_refs=("evidence:accepted-1",),
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
        await FakeContextCompactor().compact(request),
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
    candidate = await FakeContextCompactor().compact(request)
    evidence = replace(
        candidate.preservation_evidence[0],
        input_event_refs=("event-old",),
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
    candidate = await FakeContextCompactor().compact(request)
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
    candidate = await FakeContextCompactor().compact(request)
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
    candidate = await FakeContextCompactor().compact(request)
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


@pytest.mark.asyncio
async def test_quality_rejects_summary_pretending_to_create_evidence_backed_fact() -> None:
    """Quality check 拒绝 episode summary 伪造 evidence-backed fact。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request)
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
    """Summary confirmed_fact_refs 不能把 accepted evidence id 当 stable fact ref。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request)
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
    candidate = await FakeContextCompactor().compact(request)
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
    """Accepted evidence 没有有效 fact candidate 时只产生诊断拒绝。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request),
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
    candidate = await FakeContextCompactor().compact(request)
    invalid_item = replace(
        candidate.minimum_preserve_item_candidates[0],
        source_refs=("evidence:accepted-1",),
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
    candidate = await FakeContextCompactor().compact(request)
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


def test_compaction_request_rejects_wrong_current_message_summary_type() -> None:
    """CompactionRequest 对非法当前消息摘要类型抛出 TypeError。

    :returns: ``None``。
    """

    invalid_summary = cast(CurrentMessageSummary, "not-current-message-summary")

    with pytest.raises(TypeError, match="current_message_summary"):
        _request(current_message_summary=invalid_summary)


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
            accepted_evidence_refs_retained=True,
            evidence_backed_fact_candidates_accepted=True,
            minimum_preserve_items_accepted=True,
            evidence_anchors_retained=True,
            open_questions_retained=True,
            retained_accepted_evidence_refs=(),
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
            accepted_evidence_refs_retained=True,
            evidence_backed_fact_candidates_accepted=True,
            minimum_preserve_items_accepted=True,
            evidence_anchors_retained=True,
            open_questions_retained=True,
            retained_accepted_evidence_refs=(),
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
    current_message_summary: CurrentMessageSummary | None = None,
) -> CompactionRequest:
    """构造标准 compaction request。

    :param trigger_source: compaction 触发来源。
    :param attempt_id: reactive compaction 对应 Attempt id。
    :param execution_id: reactive compaction 对应 execution id。
    :param current_message_summary: 当前消息摘要；为 ``None`` 时使用默认摘要。
    :returns: compaction request。
    """

    resolved_current_message_summary = current_message_summary
    if resolved_current_message_summary is None:
        resolved_current_message_summary = CurrentMessageSummary(
            current_user_input_ref="event-current",
            summary_text="分析 A 公司 2025 年年报",
            source_event_refs=("event-current",),
        )

    return CompactionRequest(
        trigger_source=trigger_source,
        session_id="session-1",
        run_id="run-1",
        attempt_id=attempt_id,
        execution_id=execution_id,
        input_event_refs=("event-old", "event-current"),
        memory_snapshot_cursor=7,
        current_message_summary=resolved_current_message_summary,
        accepted_evidence_envelopes=(
            _accepted_evidence_envelope("accepted-1"),
            _accepted_evidence_envelope("accepted-2"),
        ),
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


def _accepted_evidence_envelope(suffix: str) -> AcceptedEvidenceEnvelope:
    """构造测试用 accepted evidence envelope。

    :param suffix: evidence 与 producer ref 后缀。
    :returns: accepted evidence envelope。
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
