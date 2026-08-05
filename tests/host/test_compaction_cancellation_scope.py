"""Compaction proposal attempt cancellation 与 pre-call recheck 测试。"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import StructuredOutputCapability

import asyncio
from collections.abc import Mapping
from typing import cast

import pytest

import dayu.host.llm_compaction as llm_compaction
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactionRequest,
)
from dayu.host.compaction_operation import (
    CompactorProposalRunInput,
    run_compaction_operation,
)
from dayu.host.context_events import CompactorProposalManifestReference
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.memory import default_memory_projection_policy
from dayu.host.context_governance import compact_output_caps_v3_from_memory_policy
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import fake_compaction_proposal_from_material_json

_TIMEOUT_REASON = "compactor_proposal_timeout"
_PARENT_REASON = "run_cancelled"


class _CancellingManifestRecorder:
    """写完 manifest 后同步取消 parent 的确定性 recorder。"""

    def __init__(self, parent: ControllableCancellationToken) -> None:
        """初始化 recorder。

        :param parent: 待取消的 parent token。
        :returns: ``None``。
        """

        self._parent = parent
        self.reference: CompactorProposalManifestReference | None = None

    def record_compactor_proposal_manifest(
        self,
        *,
        request: CompactionRequest,
        prepared_input: CompactorProposalRunInput,
        compaction_operation_id: str,
        compaction_attempt_number: int,
    ) -> CompactorProposalManifestReference:
        """返回 manifest ref，并在返回前让 parent 失效。

        :param request: Host compaction request。
        :param prepared_input: 已准备的 provider input。
        :param compaction_operation_id: compaction operation id。
        :param compaction_attempt_number: attempt 序号。
        :returns: deterministic manifest ref。
        """

        self.reference = CompactorProposalManifestReference(
            manifest_event_id=f"manifest-event-{compaction_attempt_number}",
            manifest_payload_ref=f"manifest:{compaction_operation_id}",
            manifest_digest=prepared_input.role_sequence_digest,
            compactor_input_projection_ref=f"projection:{request.run_id}",
            compactor_input_projection_digest=(prepared_input.compactor_input_projection_digest),
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
            compactor_engine_run_id=prepared_input.compactor_engine_run_id,
        )
        self._parent.request_cancel(_PARENT_REASON)
        return self.reference


@pytest.mark.asyncio
async def test_attempt_timeout_does_not_cancel_parent_or_next_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次 timeout 只取消 attempt child，第二次使用全新 child 并成功。

    :param monkeypatch: pytest monkeypatch fixture。
    """

    request = _request()
    parent = ControllableCancellationToken()
    observed_tokens: list[CancellationToken] = []

    async def fake_run_agent_request(
        agent_request: AgentRunRequest,
        *,
        timeout_seconds: float,
    ) -> AgentRunResult:
        """首次抛 timeout，第二次返回合法 proposal。

        :param agent_request: compactor Engine request。
        :param timeout_seconds: 单次 provider timeout。
        :returns: 第二次调用的 final answer。
        :raises TimeoutError: 首次调用时抛出。
        """

        assert timeout_seconds == 1.0
        observed_tokens.append(agent_request.cancellation_token)
        if len(observed_tokens) == 1:
            raise TimeoutError("attempt one timeout")
        assert agent_request.cancellation_token.is_cancelled() is False
        return _valid_final_answer(
            request=request,
            agent_request=agent_request,
        )

    monkeypatch.setattr(
        llm_compaction,
        "_run_agent_request",
        fake_run_agent_request,
    )

    result = await run_compaction_operation(
        request=request,
        compactor=_compactor(),
        first_attempt_number=1,
        max_attempt_number=2,
        cancellation_token=parent,
        memory_policy=default_memory_projection_policy(),
    )

    assert result.accepted_truth is not None
    assert result.failure_reason is None
    assert len(observed_tokens) == 2
    assert observed_tokens[0] is not observed_tokens[1]
    assert observed_tokens[0].cancel_reason() == _TIMEOUT_REASON
    assert observed_tokens[1].is_cancelled() is False
    assert parent.is_cancelled() is False


@pytest.mark.asyncio
async def test_parent_cancel_after_timeout_wins_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """attempt timeout 后 parent 取消优先，repair provider 不得启动。

    :param monkeypatch: pytest monkeypatch fixture。
    """

    request = _request()
    parent = ControllableCancellationToken()
    provider_calls = 0
    first_child: CancellationToken | None = None
    original_signal = llm_compaction._signal_timeout_cancellation

    async def timeout_runner(
        agent_request: AgentRunRequest,
        *,
        timeout_seconds: float,
    ) -> AgentRunResult:
        """记录第一次 child 并触发 deterministic timeout。

        :param agent_request: compactor Engine request。
        :param timeout_seconds: 单次 provider timeout。
        :returns: 不会返回。
        :raises TimeoutError: 始终抛出。
        """

        nonlocal provider_calls, first_child
        assert timeout_seconds == 1.0
        provider_calls += 1
        first_child = agent_request.cancellation_token
        raise TimeoutError("attempt timeout")

    def signal_then_cancel_parent(token: CancellationToken) -> None:
        """先写 attempt timeout，再在 retry 前取消 parent。

        :param token: 当前 attempt child。
        :returns: ``None``。
        """

        original_signal(token)
        parent.request_cancel(_PARENT_REASON)

    monkeypatch.setattr(llm_compaction, "_run_agent_request", timeout_runner)
    monkeypatch.setattr(
        llm_compaction,
        "_signal_timeout_cancellation",
        signal_then_cancel_parent,
    )

    result = await run_compaction_operation(
        request=request,
        compactor=_compactor(),
        first_attempt_number=1,
        max_attempt_number=2,
        cancellation_token=parent,
        memory_policy=default_memory_projection_policy(),
    )

    assert provider_calls == 1
    assert first_child is not None
    assert first_child.cancel_reason() == _PARENT_REASON
    assert first_child.requested_at() == parent.requested_at()
    assert result.accepted_truth is None
    assert result.failure_reason == "cancellation_requested"
    assert _PARENT_REASON in result.rejected_attempts[-1].diagnostic_refs[0]


@pytest.mark.asyncio
async def test_parent_cancel_is_visible_to_running_attempt_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider 运行中 parent cancel 会由 linked child 立即观察。

    :param monkeypatch: pytest monkeypatch fixture。
    """

    parent = ControllableCancellationToken()
    provider_started = asyncio.Event()
    inspect_child = asyncio.Event()
    observed_child: CancellationToken | None = None

    async def blocked_runner(
        agent_request: AgentRunRequest,
        *,
        timeout_seconds: float,
    ) -> AgentRunResult:
        """阻塞 provider，直到测试写入 parent cancellation。

        :param agent_request: compactor Engine request。
        :param timeout_seconds: 单次 provider timeout。
        :returns: 不会返回。
        :raises asyncio.CancelledError: child 观察 parent 后抛出。
        """

        nonlocal observed_child
        assert timeout_seconds == 1.0
        observed_child = agent_request.cancellation_token
        provider_started.set()
        await inspect_child.wait()
        assert observed_child.is_cancelled() is True
        assert observed_child.cancel_reason() == _PARENT_REASON
        assert observed_child.requested_at() == parent.requested_at()
        raise asyncio.CancelledError()

    monkeypatch.setattr(llm_compaction, "_run_agent_request", blocked_runner)
    operation_task = asyncio.create_task(
        run_compaction_operation(
            request=_request(),
            compactor=_compactor(),
            first_attempt_number=1,
            max_attempt_number=2,
            cancellation_token=parent,
            memory_policy=default_memory_projection_policy(),
        )
    )
    await provider_started.wait()

    parent.request_cancel(_PARENT_REASON)
    assert observed_child is not None
    assert observed_child.is_cancelled() is True
    assert observed_child.cancel_reason() == _PARENT_REASON
    assert observed_child.requested_at() == parent.requested_at()
    inspect_child.set()
    result = await operation_task

    assert result.failure_reason == "cancellation_requested"
    assert len(result.rejected_attempts) == 1


@pytest.mark.asyncio
async def test_outer_task_cancellation_is_not_reclassified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """caller task cancellation 仍透传，不伪装成 Host cancellation result。

    :param monkeypatch: pytest monkeypatch fixture。
    """

    parent = ControllableCancellationToken()
    provider_started = asyncio.Event()

    async def blocked_runner(
        agent_request: AgentRunRequest,
        *,
        timeout_seconds: float,
    ) -> AgentRunResult:
        """保持 provider 调用挂起，供 caller 取消 operation task。

        :param agent_request: compactor Engine request。
        :param timeout_seconds: 单次 provider timeout。
        :returns: 不会返回。
        :raises asyncio.CancelledError: caller 取消 task 时由 await 传播。
        """

        del agent_request
        assert timeout_seconds == 1.0
        provider_started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(llm_compaction, "_run_agent_request", blocked_runner)
    operation_task = asyncio.create_task(
        run_compaction_operation(
            request=_request(),
            compactor=_compactor(),
            first_attempt_number=1,
            max_attempt_number=1,
            cancellation_token=parent,
            memory_policy=default_memory_projection_policy(),
        )
    )
    await provider_started.wait()
    operation_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await operation_task
    assert parent.is_cancelled() is False


@pytest.mark.asyncio
async def test_manifest_post_write_recheck_blocks_provider_and_keeps_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """manifest hook 让 parent 失效后，pre-call recheck 阻止 provider。

    :param monkeypatch: pytest monkeypatch fixture。
    """

    parent = ControllableCancellationToken()
    recorder = _CancellingManifestRecorder(parent)
    provider_calls = 0

    async def forbidden_runner(
        agent_request: AgentRunRequest,
        *,
        timeout_seconds: float,
    ) -> AgentRunResult:
        """记录不应发生的 provider 调用。

        :param agent_request: compactor Engine request。
        :param timeout_seconds: 单次 provider timeout。
        :returns: 合法 final answer。
        """

        nonlocal provider_calls
        del timeout_seconds
        provider_calls += 1
        return _valid_final_answer(
            request=_request(),
            agent_request=agent_request,
        )

    monkeypatch.setattr(llm_compaction, "_run_agent_request", forbidden_runner)
    result = await run_compaction_operation(
        request=_request(),
        compactor=_compactor(),
        first_attempt_number=1,
        max_attempt_number=1,
        cancellation_token=parent,
        compaction_operation_id="operation-pre-call-recheck",
        proposal_manifest_recorder=recorder,
        memory_policy=default_memory_projection_policy(),
    )

    assert provider_calls == 0
    assert recorder.reference is not None
    assert result.failure_reason == "cancellation_requested"
    assert result.rejected_attempts[0].proposal_manifest_reference is not None
    assert (
        result.rejected_attempts[0].proposal_manifest_reference.manifest_payload_ref
        == recorder.reference.manifest_payload_ref
    )


def _compactor() -> LLMContextCompactor:
    """构造 attempt cancellation 测试用 LLM compactor。

    :returns: LLM compactor。
    """

    return LLMContextCompactor(
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid",
            api_key_ref="secret:test",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            structured_output_capability=StructuredOutputCapability.NONE,
            default_timeout_seconds=1.0,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="test fallback",
            continuation_prompt="test continuation",
        ),
        system_prompt="Compact the supplied material.",
        user_prompt_template=(
            "Material: <<compaction_request>>\n"
            "Rules: <<compact_output_rules>>\n"
            "Template: <<compact_output_template>>"
        ),
    )


def _request() -> CompactionRequest:
    """构造稳定的 proactive compaction request。

    :returns: compaction request。
    """

    material_pack = build_initial_material_pack(
        current_input_ref="input-current",
        current_input_text="current user text",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="input-old",
                text="previous assistant answer",
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
                raw_result_text="cash flow increased",
                readable_source_text="annual report cash flow statement",
                payload_refs=("payload:evidence-1",),
            ),
        ),
    )
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-cancellation-scope",
        run_id="run-cancellation-scope",
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
        recent_raw_turn_refs=("input-current",),
        older_raw_turn_refs=("input-old",),
        existing_episode_summary_refs=(),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=4096,
            soft_threshold_tokens=3200,
            hard_threshold_tokens=3900,
            safety_margin_tokens=200,
            estimator_digest="estimate-digest",
            overage_reason=None,
        ),
        output_caps=compact_output_caps_v3_from_memory_policy(
            default_memory_projection_policy()
        ),
    )


def _valid_final_answer(
    *,
    request: CompactionRequest,
    agent_request: AgentRunRequest,
) -> EngineRunOutcomeFinalAnswer:
    """从 request 构造合法 deterministic compactor final answer。

    :param request: compaction request。
    :param agent_request: 产出该 final 的同一次 compactor Engine request。
    :returns: Engine final answer。
    """

    compact_input = request.compact_input
    material_json = cast(Mapping[str, JsonValue], compact_input.to_json())
    return EngineRunOutcomeFinalAnswer(
        session_id=agent_request.session_id,
        run_id=agent_request.run_id,
        content=fake_compaction_proposal_from_material_json(material_json),
        filtered=False,
        degraded=False,
        finish_reason=FinishReason.STOP,
        response_identity=SuccessfulRunnerResponseIdentity(
            effective_provider=agent_request.runner_spec.provider,
            effective_model=agent_request.runner_spec.model,
            runner_request_identity=build_runner_request_identity(
                run_id=agent_request.run_id,
                attempt_id=agent_request.attempt_id,
                execution_id=agent_request.execution_id,
                iteration_id=f"{agent_request.run_id}:compactor-final",
                iteration_index=0,
                runner_call_index=1,
            ),
            provider_request_id_availability=(ProviderRequestIdAvailability.UNAVAILABLE),
            provider_request_id=None,
        ),
    )
