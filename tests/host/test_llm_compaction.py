"""Host-owned LLM context compactor tests。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.compaction import CompactionRequest
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.compaction import CurrentMessageSummary
from dayu.host.llm_compaction import (
    LLMCompactionProposalError,
    LLMContextCompactor,
)

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.mark.asyncio
async def test_llm_context_compactor_builds_tool_disabled_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM compactor 构造禁用工具的 Engine public request。"""

    seen: list[AgentRunRequest] = []

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        seen.append(request)
        return _final("summary")

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _fake_run)
    runner_spec = _runner_spec(max_retries=3)
    runner_options = _runner_options()

    LLMContextCompactor(
        runner_spec=runner_spec,
        runner_options=runner_options,
    ).compact(_request())

    assert len(seen) == 1
    assert seen[0].runner_spec is runner_spec
    assert seen[0].runner_options is runner_options
    assert seen[0].disable_tools is True
    assert seen[0].tool_schemas == ()
    assert seen[0].agent_policy.allow_tool_calls is False


@pytest.mark.asyncio
async def test_llm_context_compactor_maps_final_answer_to_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM final answer 的文本只作为 summary，refs 由 Host 构造。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("keep the current user request")),
    )

    candidate = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request())

    assert candidate.episode_summary_candidate.goal == "keep the current user request"
    assert candidate.retained_current_user_input_ref == "input-1"
    assert candidate.preserved_input_event_refs == ("input-1", "input-2")
    assert candidate.preserved_tool_fact_refs == ("tool-fact-1",)
    assert candidate.preserved_verified_fact_refs == ("verified-1",)
    assert candidate.budget_after_compact == 50


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_empty_or_non_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 final answer 或非 final outcome 不会被映射为 candidate。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("   ")),
    )
    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    with pytest.raises(LLMCompactionProposalError, match="summary is empty"):
        compactor.compact(_request())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            EngineRunOutcomeFailed(
                session_id="session-1",
                run_id="run-1",
                error_code="failed",
                message="failed",
                provider_request_id=None,
                recoverable=False,
            )
        ),
    )
    with pytest.raises(LLMCompactionProposalError, match="did not return final"):
        compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_preserves_host_owned_refs_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """candidate evidence 与 pinned patch ref 由 Host-owned mapper 生成。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("summary")),
    )

    candidate = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request())

    evidence = candidate.preservation_evidence[0]
    assert evidence.input_event_refs == ("input-1", "input-2")
    assert evidence.tool_fact_refs == ("tool-fact-1",)
    assert candidate.episode_summary_candidate.evidence_refs == (
        evidence.evidence_id,
    )
    assert candidate.pinned_state_patch_candidate.current_goal.evidence_refs == (
        evidence.evidence_id,
    )


@pytest.mark.asyncio
async def test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compactor 透传 RunnerSpec.max_retries，runner failure 不在内部 repair loop。"""

    calls: list[AgentRunRequest] = []

    async def _raising_run(request: AgentRunRequest) -> AgentRunResult:
        calls.append(request)
        raise RuntimeError("runner failed")

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _raising_run)
    runner_spec = _runner_spec(max_retries=5)
    compactor = LLMContextCompactor(
        runner_spec=runner_spec,
        runner_options=_runner_options(),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        compactor.compact(_request())

    assert len(calls) == 1
    assert calls[0].runner_spec.max_retries == 5


def _fake_run_factory(
    outcome: AgentRunResult,
) -> Callable[[AgentRunRequest], Awaitable[AgentRunResult]]:
    """构造 async run_agent_and_wait 替身。

    :param outcome: 固定 Engine outcome。
    :returns: async fake runner。
    """

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        del request
        return outcome

    return _fake_run


def _request() -> CompactionRequest:
    """构造 compaction request。

    :returns: CompactionRequest。
    """

    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-1",
        run_id="run-1",
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


def _final(content: str) -> EngineRunOutcomeFinalAnswer:
    """构造 final answer outcome。

    :param content: final answer 文本。
    :returns: EngineRunOutcomeFinalAnswer。
    """

    return EngineRunOutcomeFinalAnswer(
        session_id="session-1",
        run_id="run-1",
        content=content,
        filtered=False,
        degraded=False,
        finish_reason=FinishReason.STOP,
    )


def _runner_spec(max_retries: int = 0) -> RunnerSpec:
    """构造 RunnerSpec。

    :param max_retries: runner retry 上限。
    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=max_retries,
        provider_request=None,
    )


def _runner_options() -> RunnerCallOptions:
    """构造 RunnerCallOptions。

    :returns: RunnerCallOptions。
    """

    return RunnerCallOptions(
        temperature=None,
        max_tokens=None,
        top_p=None,
        stream=False,
    )
