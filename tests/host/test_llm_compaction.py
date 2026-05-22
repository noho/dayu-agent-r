"""Host-owned LLM context compactor tests。"""

from __future__ import annotations

import asyncio
import inspect
import json
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
from dayu.host.compaction import (
    CompactionRequest,
    CurrentMessageSummary,
    MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS,
    MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
)
import dayu.host.llm_compaction as llm_compaction_module
from dayu.host.llm_compaction import (
    LLMCompactionProposalError,
    LLMContextCompactor,
)

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_llm_context_compactor_does_not_use_thread_bridge() -> None:
    """LLM compactor 不再使用线程桥、join timeout 或嵌套 asyncio.run。"""

    source = inspect.getsource(llm_compaction_module)

    assert "threading" not in source
    assert "thread.join(" not in source
    assert "asyncio.run" not in source


@pytest.mark.asyncio
async def test_llm_context_compactor_builds_tool_disabled_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM compactor 构造禁用工具的 Engine public request。"""

    seen: list[AgentRunRequest] = []

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        seen.append(request)
        return _final(_proposal_json())

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _fake_run)
    runner_spec = _runner_spec(max_retries=3)
    runner_options = _runner_options()

    await LLMContextCompactor(
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
    """LLM strict JSON final answer 映射为完整 structured candidate。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json())),
    )

    candidate = await LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request())

    assert candidate.episode_summary_candidate.goal == "keep the current user request"
    assert candidate.pinned_state_patch_candidate.current_goal.value == (
        "keep the current user request"
    )
    assert len(candidate.evidence_backed_fact_candidates) == 1
    assert candidate.evidence_backed_fact_candidates[0].claim_text == (
        "Accepted evidence shows revenue growth."
    )
    assert candidate.evidence_backed_fact_candidates[0].evidence_refs == (
        "evidence:accepted-1",
    )
    assert len(candidate.minimum_preserve_item_candidates) == 1
    assert candidate.minimum_preserve_item_candidates[0].text == (
        "Current user asked to keep the financial analysis context."
    )
    assert candidate.retained_current_user_input_ref == "input-1"
    assert candidate.preserved_input_event_refs == ("input-1", "input-2")
    assert candidate.preserved_accepted_evidence_refs == ("evidence:accepted-1",)
    assert candidate.preserved_evidence_backed_fact_refs == ("fact-1",)
    assert candidate.budget_after_compact > 8


@pytest.mark.asyncio
async def test_llm_context_compactor_budget_counts_preserved_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compact 后预算必须覆盖 summary 以外的保留上下文。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json())),
    )

    candidate = await LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request())

    assert candidate.budget_after_compact >= 80


@pytest.mark.asyncio
async def test_llm_context_compactor_budget_counts_structured_output_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预算估算必须随 fact 与 minimum preserve 文本增长。"""

    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(
                _proposal_json(
                    claim_text="short fact",
                    minimum_preserve_text="short preserve",
                )
            )
        ),
    )
    short_candidate = await compactor.compact(_request())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(
                _proposal_json(
                    claim_text="material fact " * 120,
                    minimum_preserve_text="continuity item " * 70,
                )
            )
        ),
    )
    long_candidate = await compactor.compact(_request())

    assert long_candidate.episode_summary_candidate.goal == (
        short_candidate.episode_summary_candidate.goal
    )
    assert long_candidate.budget_after_compact > short_candidate.budget_after_compact


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_empty_plain_text_or_non_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空、纯文本 final answer 或非 final outcome 不会被映射为 candidate。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("   ")),
    )
    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    with pytest.raises(LLMCompactionProposalError, match="proposal is empty"):
        await compactor.compact(_request())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("plain text summary")),
    )
    with pytest.raises(LLMCompactionProposalError, match="not valid JSON"):
        await compactor.compact(_request())

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
    with pytest.raises(LLMCompactionProposalError, match="runner failed"):
        await compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_malformed_and_schema_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """坏 JSON 与 schema-invalid JSON 必须拒绝。"""

    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final('{"episode_summary_candidate": ')),
    )
    with pytest.raises(LLMCompactionProposalError, match="not valid JSON"):
        await compactor.compact(_request())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(json.dumps({"episode_summary_candidate": {}}, sort_keys=True))
        ),
    )
    with pytest.raises(LLMCompactionProposalError, match="missing required key"):
        await compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_overlong_structured_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_text 与 minimum preserve text 上限复用 shared constants。"""

    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(
                _proposal_json(
                    claim_text="x"
                    * (MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS + 1)
                )
            )
        ),
    )
    with pytest.raises(LLMCompactionProposalError, match="claim_text"):
        await compactor.compact(_request())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(
                _proposal_json(
                    minimum_preserve_text="x"
                    * (MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS + 1)
                )
            )
        ),
    )
    with pytest.raises(
        LLMCompactionProposalError,
        match="MinimumPreserveItemCandidate.text",
    ):
        await compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_non_accepted_evidence_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fact candidate evidence_refs 只能引用 request.accepted_evidence_refs。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(_proposal_json(fact_evidence_refs=("evidence:not-accepted",)))
        ),
    )
    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError, match="unknown ref"):
        await compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_truncated_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compactor final answer 若被 length 截断，必须作为脏 proposal 拒绝。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("partial summary", finish_reason=FinishReason.LENGTH)),
    )
    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError, match="truncated"):
        await compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_applies_runner_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compactor 单次 runner 调用必须受 RunnerSpec timeout 边界约束。"""

    async def _hanging_run(request: AgentRunRequest) -> AgentRunResult:
        """模拟不返回的 Engine public runner。

        :param request: Engine run request。
        :returns: 不会正常返回。
        :raises TimeoutError: 外层 ``asyncio.wait_for`` 超时时取消本协程。
        """

        del request
        await asyncio.sleep(10.0)
        return _final("unreachable")

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _hanging_run)
    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(default_timeout_seconds=0.01),
        runner_options=_runner_options(),
    )

    with pytest.raises(TimeoutError):
        await compactor.compact(_request())


@pytest.mark.asyncio
async def test_llm_context_compactor_sanitizes_failed_runner_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner failed outcome 的错误摘要不泄漏敏感字段。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 错误摘要缺少诊断或泄漏敏感字段时抛出。
    """

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            EngineRunOutcomeFailed(
                session_id="session-1",
                run_id="run-1",
                error_code="api_key=error-secret",
                message=(
                    "http 503 Authorization: Bearer deepsecret "
                    "api_key=plainsecret transient unavailable"
                ),
                provider_request_id="provider-request-1",
                recoverable=True,
            )
        ),
    )
    compactor = LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError) as exc_info:
        await compactor.compact(_request())

    message = str(exc_info.value)
    assert "error_code=unknown_error" in message
    assert "recoverable=True" in message
    assert "503" in message
    assert "transient unavailable" in message
    assert "error-secret" not in message
    assert "deepsecret" not in message
    assert "plainsecret" not in message
    assert "provider-request-1" not in message


@pytest.mark.asyncio
async def test_llm_context_compactor_preserves_host_owned_refs_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """candidate evidence 与 pinned patch ref 由 Host-owned mapper 生成。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json())),
    )

    candidate = await LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request())

    evidence = candidate.preservation_evidence[0]
    assert evidence.input_event_refs == ("input-1", "input-2")
    assert evidence.accepted_evidence_refs == ("evidence:accepted-1",)
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
        await compactor.compact(_request())

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
        accepted_evidence_envelopes=(_accepted_evidence_envelope(),),
        evidence_backed_fact_refs=("fact-1",),
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


def _proposal_json(
    *,
    claim_text: str = "Accepted evidence shows revenue growth.",
    minimum_preserve_text: str = (
        "Current user asked to keep the financial analysis context."
    ),
    fact_evidence_refs: tuple[str, ...] = ("evidence:accepted-1",),
) -> str:
    """构造 LLM structured JSON proposal。

    :param claim_text: fact candidate claim_text。
    :param minimum_preserve_text: minimum preserve item text。
    :param fact_evidence_refs: fact candidate evidence refs。
    :returns: JSON 文本。
    """

    return json.dumps(
        {
            "episode_summary_candidate": {
                "episode_title": "Context compact summary",
                "goal": "keep the current user request",
                "completed_actions": ["reviewed current financial context"],
                "confirmed_fact_refs": ["fact-1"],
                "confirmed_fact_summaries": ["fact-1 remains relevant"],
                "user_constraints": ["keep-current-input:input-1"],
                "open_questions": ["continue-current-run"],
                "next_step": "continue with the current user input",
                "tool_finding_refs": ["evidence:accepted-1"],
            },
            "pinned_state_patch_candidate": {
                "current_goal": {
                    "operation": "replace",
                    "value": "keep the current user request",
                },
                "confirmed_subjects": {
                    "operation": "replace",
                    "value": ["subject:fact-1"],
                },
                "user_constraints": {
                    "operation": "replace",
                    "value": ["keep-current-input:input-1"],
                },
                "open_questions": {
                    "operation": "replace",
                    "value": ["continue-current-run"],
                },
            },
            "evidence_backed_fact_candidates": [
                {
                    "candidate_id": "fact-candidate-1",
                    "claim_text": claim_text,
                    "evidence_kind": "observed_value",
                    "evidence_refs": list(fact_evidence_refs),
                    "attributes": {},
                }
            ],
            "minimum_preserve_item_candidates": [
                {
                    "item_id": "preserve-current-input",
                    "label": "current input",
                    "text": minimum_preserve_text,
                    "source_refs": ["input-1"],
                    "preserve_reason": "needed_for_recent_reference",
                }
            ],
            "retained_current_user_input_ref": "input-1",
            "preserved_input_event_refs": ["input-1", "input-2"],
            "preserved_accepted_evidence_refs": ["evidence:accepted-1"],
            "preserved_evidence_backed_fact_refs": ["fact-1"],
            "dropped_ranges": [],
            "summarized_ranges": [
                {
                    "range_ref": "range-older-raw-turns",
                    "start_input_ref": "input-2",
                    "end_input_ref": "input-2",
                }
            ],
        },
        sort_keys=True,
    )


def _accepted_evidence_envelope() -> AcceptedEvidenceEnvelope:
    """构造测试用 accepted evidence envelope。

    :returns: accepted evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id="evidence:accepted-1",
        producer_event_ref="event-tool-result-1",
        tool_name="fins.search",
        tool_call_id="tool-call-1",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref="event-tool-call-1",
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref="payload:1",
            payload_digest=_DIGEST,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _final(
    content: str, *, finish_reason: FinishReason = FinishReason.STOP
) -> EngineRunOutcomeFinalAnswer:
    """构造 final answer outcome。

    :param content: final answer 文本。
    :param finish_reason: final answer finish reason。
    :returns: EngineRunOutcomeFinalAnswer。
    """

    return EngineRunOutcomeFinalAnswer(
        session_id="session-1",
        run_id="run-1",
        content=content,
        filtered=False,
        degraded=False,
        finish_reason=finish_reason,
    )


def _runner_spec(
    max_retries: int = 0, default_timeout_seconds: float = 1.0
) -> RunnerSpec:
    """构造 RunnerSpec。

    :param max_retries: runner retry 上限。
    :param default_timeout_seconds: runner 单次默认超时秒数。
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
        default_timeout_seconds=default_timeout_seconds,
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
