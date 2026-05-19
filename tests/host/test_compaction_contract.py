"""Phase 10 Slice 2 compaction contract 测试。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from dayu.host.compaction import (
    CompactQualityCheckResult,
    CompactQualityIssue,
    CompactionRequest,
    CurrentMessageSummary,
    PinnedPatchOperation,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_governance import check_compaction_candidate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.fake_compaction import FakeContextCompactor


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
async def test_quality_rejects_missing_tool_fact_refs() -> None:
    """Quality check 拒绝丢失 accepted tool fact refs。

    :returns: ``None``。
    """

    request = _request()
    candidate = replace(
        await FakeContextCompactor().compact(request),
        preserved_tool_fact_refs=("tool-fact-1",),
    )

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.TOOL_FACT_REFS_MISSING in result.rejection_reasons


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
async def test_quality_rejects_summary_pretending_to_create_verified_fact() -> None:
    """Quality check 拒绝 episode summary 伪造 verified fact。

    :returns: ``None``。
    """

    request = _request()
    candidate = await FakeContextCompactor().compact(request)
    invalid_summary = replace(
        candidate.episode_summary_candidate,
        proposed_verified_fact_refs=("summary-made-fact",),
    )
    candidate = replace(candidate, episode_summary_candidate=invalid_summary)

    result = check_compaction_candidate(request, candidate)

    assert result.accepted is False
    assert CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT in (
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
            accepted_tool_fact_refs_retained=True,
            evidence_anchors_retained=True,
            open_questions_retained=True,
            retained_evidence_refs=(),
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
            accepted_tool_fact_refs_retained=True,
            evidence_anchors_retained=True,
            open_questions_retained=True,
            retained_evidence_refs=(),
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
        tool_fact_refs=("tool-fact-1", "tool-fact-2"),
        verified_fact_refs=("tool-fact-1",),
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
