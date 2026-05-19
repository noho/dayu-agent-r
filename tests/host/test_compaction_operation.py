"""Host compaction operation async retry tests。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from dayu.host.compaction import (
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    CurrentMessageSummary,
)
from dayu.host.compaction_operation import run_compaction_operation
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.fake_compaction import FakeContextCompactor

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class _FailOnceCompactor(ContextCompactor):
    """首次 proposal 失败，第二次返回 fake candidate。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """执行可重试 proposal。

        :param request: compaction request。
        :returns: fake compaction candidate。
        :raises RuntimeError: 首次调用时模拟 proposal failure。
        """

        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("proposal failed once")
        return await self._fake.compact(request)


class _AlwaysFailingCompactor(ContextCompactor):
    """始终 proposal 失败的 compactor。"""

    async def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """模拟 proposal failure。

        :param request: compaction request。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 proposal failure。
        """

        del request
        raise RuntimeError("proposal failed")


class _QualityRejectOnceCompactor(ContextCompactor):
    """首次返回 quality reject candidate，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """返回可修复 quality rejection 后的成功 candidate。

        :param request: compaction request。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request)
        if self.calls == 1:
            return replace(candidate, retained_current_user_input_ref="wrong-input")
        return candidate


class _HardThresholdOnceCompactor(ContextCompactor):
    """首次 compact 后仍越过 hard threshold，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """返回 hard-threshold rejection 后的成功 candidate。

        :param request: compaction request。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request)
        if self.calls == 1:
            return replace(
                candidate,
                budget_after_compact=(
                    request.budget_before_compact.hard_threshold_tokens
                ),
            )
        return candidate


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_async_proposal_failure() -> None:
    """operation await async compactor，并保留 proposal failure 后 retry 行为。"""

    compactor = _FailOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert result.quality_result is not None
    assert result.quality_result.accepted is True
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_quality_rejection() -> None:
    """quality_check_rejected 后 retry，并接受第二次 candidate。"""

    compactor = _QualityRejectOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].failure_category == "quality_check_rejected"
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_hard_threshold_after_compact() -> None:
    """hard_threshold_after_compact 后 retry，并接受第二次 candidate。"""

    compactor = _HardThresholdOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert len(result.rejected_attempts) == 1
    assert (
        result.rejected_attempts[0].failure_category
        == "hard_threshold_after_compact"
    )
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_fails_after_async_attempt_budget() -> None:
    """operation await async compactor，并在 proposal attempts 耗尽后失败。"""

    result = await run_compaction_operation(
        request=_request(),
        compactor=_AlwaysFailingCompactor(),
        max_attempts=2,
    )

    assert result.accepted_candidate is None
    assert result.quality_result is None
    assert len(result.rejected_attempts) == 2
    assert result.rejected_attempts[0].repairable is True
    assert result.rejected_attempts[1].repairable is False
    assert "proposal failed" in result.rejected_attempts[0].diagnostic_refs[0]
    assert result.failure_reason is not None


def _request() -> CompactionRequest:
    """构造标准 compaction request。

    :returns: compaction request。
    """

    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-operation",
        run_id="run-operation",
        attempt_id=None,
        execution_id=None,
        input_event_refs=("input-1", "input-2"),
        memory_snapshot_cursor=7,
        current_message_summary=CurrentMessageSummary(
            current_user_input_ref="input-1",
            summary_text="current user text",
            source_event_refs=("input-1",),
        ),
        tool_fact_refs=("tool-fact-1",),
        verified_fact_refs=("verified-1",),
        recent_raw_turn_refs=("input-1",),
        older_raw_turn_refs=("input-2",),
        existing_episode_summary_refs=("summary-1",),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=200,
            soft_threshold_tokens=120,
            hard_threshold_tokens=80,
            safety_margin_tokens=20,
            estimator_digest=_DIGEST,
            overage_reason=None,
        ),
    )
