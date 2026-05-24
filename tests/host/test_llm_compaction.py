"""Host-owned LLM context compactor tests。"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace

import pytest

from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    initial_segment_selection,
)
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.compaction import (
    CompactMaterialPack,
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactionRequest,
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
from tests.host.fake_cancellation import StubCancellationToken

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_TEST_SYSTEM_PROMPT = "test compactor system prompt"
_TEST_USER_PROMPT_TEMPLATE = (
    "test compactor user prompt\n\n<<compaction_request>>\n\nreturn strict json"
)
_TEST_AGENT_POLICY = AgentPolicy(
    max_iterations=1,
    continuation_max_attempts=0,
    allow_tool_calls=False,
    tool_execution_timeout_seconds=1.0,
)


def test_llm_context_compactor_does_not_use_thread_bridge() -> None:
    """LLM compactor 不再使用线程桥、join timeout 或嵌套 asyncio.run。"""

    source = inspect.getsource(llm_compaction_module)

    assert "threading" not in source
    assert "thread.join(" not in source
    assert "asyncio.run" not in source


def _llm_compactor(
    *,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
) -> LLMContextCompactor:
    """构造测试用 LLM compactor。

    :param runner_spec: compactor runner spec。
    :param runner_options: compactor runner options。
    :returns: 测试 compactor。
    """

    return LLMContextCompactor(
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=_TEST_AGENT_POLICY,
        system_prompt=_TEST_SYSTEM_PROMPT,
        user_prompt_template=_TEST_USER_PROMPT_TEMPLATE,
    )


def test_llm_context_compactor_requires_scene_prompt_template() -> None:
    """LLM compactor 要求调用方传入 scene / baseline 装配的 prompt。"""

    with pytest.raises(ValueError, match="system_prompt"):
        LLMContextCompactor(
            runner_spec=_runner_spec(),
            runner_options=_runner_options(),
            agent_policy=_TEST_AGENT_POLICY,
            system_prompt="",
            user_prompt_template=_TEST_USER_PROMPT_TEMPLATE,
        )
    with pytest.raises(ValueError, match="compaction_request"):
        LLMContextCompactor(
            runner_spec=_runner_spec(),
            runner_options=_runner_options(),
            agent_policy=_TEST_AGENT_POLICY,
            system_prompt=_TEST_SYSTEM_PROMPT,
            user_prompt_template="missing placeholder",
        )


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
    cancellation_token = StubCancellationToken()

    await _llm_compactor(
        runner_spec=runner_spec,
        runner_options=runner_options,
    ).compact(_request(), cancellation_token)

    assert len(seen) == 1
    assert seen[0].runner_spec is runner_spec
    assert seen[0].runner_options is runner_options
    assert seen[0].agent_policy is _TEST_AGENT_POLICY
    assert seen[0].cancellation_token is cancellation_token
    assert seen[0].messages[0].content == _TEST_SYSTEM_PROMPT
    assert seen[0].messages[1].content is not None
    assert seen[0].messages[1].content.startswith("test compactor user prompt")
    assert seen[0].disable_tools is True
    assert seen[0].tool_schemas == ()


@pytest.mark.asyncio
async def test_prompt_renders_material_pack_without_ledger_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt 只渲染四个 material pack section 且不倾倒账本字段。"""

    seen: list[AgentRunRequest] = []

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        seen.append(request)
        return _final(_proposal_json())

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _fake_run)

    await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(), StubCancellationToken())

    assert len(seen) == 1
    user_message = seen[0].messages[1]
    prompt = user_message.content
    assert prompt is not None
    assert '"stable_input":' in prompt
    assert '"history_input":' in prompt
    assert '"evidence_input":' in prompt
    assert '"current_input_anchor":' in prompt
    assert "material_pack:" not in prompt
    assert "trigger_source:" not in prompt
    assert '"label": "E1"' in prompt
    assert '"tool_name": "fins.search"' in prompt
    assert "accepted_evidence_envelopes:" not in prompt
    assert "compact_raw_context:" not in prompt
    assert "input_event_refs:" not in prompt
    assert "payload_digest" not in prompt
    assert "payload_ref" not in prompt
    assert "payload:accepted-1" not in prompt
    assert "event-tool-result-1" not in prompt
    assert "event-tool-call-1" not in prompt
    assert "memory_snapshot_cursor" not in prompt
    assert "policy_snapshot" not in prompt
    assert "outcome_digest" not in prompt
    assert "canonical_source_refs" not in prompt
    assert "Revenue grew 12% year over year." in prompt


@pytest.mark.asyncio
async def test_prompt_does_not_render_accepted_evidence_envelope_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt 不暴露 accepted evidence envelope 的内部 metadata。"""

    seen: list[AgentRunRequest] = []

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        seen.append(request)
        return _final(_proposal_json())

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _fake_run)

    await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(), StubCancellationToken())

    assert len(seen) == 1
    prompt = seen[0].messages[1].content
    assert prompt is not None
    envelope = _accepted_evidence_envelope()
    assert envelope.producer_event_ref not in prompt
    assert envelope.tool_call_id not in prompt
    assert envelope.tool_query.normalized_arguments_digest not in prompt
    assert envelope.tool_query.semantic_input_digest not in prompt
    payload_ref = envelope.result_ref.payload_ref
    payload_digest = envelope.result_ref.payload_digest
    outcome_digest = envelope.result_ref.outcome_digest
    assert payload_ref is not None
    assert payload_digest is not None
    assert outcome_digest is not None
    assert payload_ref not in prompt
    assert payload_digest not in prompt
    assert outcome_digest not in prompt


@pytest.mark.asyncio
async def test_llm_context_compactor_prompt_keeps_long_raw_evidence_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """长 raw evidence 内容的末尾仍进入 compactor prompt。"""

    long_prefix = "A" * 1300
    tail_marker = "MD&A section says backlog conversion improved in Q4."
    raw_content = f"{long_prefix}{tail_marker}"
    seen: list[AgentRunRequest] = []

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        seen.append(request)
        return _final(_proposal_json())

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _fake_run)

    await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(raw_tool_content=raw_content), StubCancellationToken())

    assert len(seen) == 1
    prompt = seen[0].messages[1].content
    assert prompt is not None
    assert tail_marker in prompt


@pytest.mark.asyncio
async def test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """raw evidence 内容旁边只标注 prompt-local evidence label。"""

    seen: list[AgentRunRequest] = []

    async def _fake_run(request: AgentRunRequest) -> AgentRunResult:
        seen.append(request)
        return _final(_proposal_json())

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", _fake_run)

    await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(), StubCancellationToken())

    assert len(seen) == 1
    prompt = seen[0].messages[1].content
    assert prompt is not None
    material_index = prompt.index('"evidence_input"')
    evidence_ref_index = prompt.index('"label": "E1"', material_index)
    raw_content_index = prompt.index(
        "Revenue grew 12% year over year.",
        material_index,
    )
    assert material_index < evidence_ref_index < raw_content_index


@pytest.mark.asyncio
async def test_parser_maps_prompt_local_evidence_label_to_canonical_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parser 先把 prompt-local evidence label 映射为 canonical ref。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json())),
    )

    candidate = await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(), StubCancellationToken())

    assert candidate.episode_summary_candidate.goal == "keep the current user request"
    assert candidate.pinned_state_patch_candidate.current_goal.value == (
        "keep the current user request"
    )
    assert len(candidate.evidence_backed_fact_candidates) == 1
    assert candidate.evidence_backed_fact_candidates[0].claim_text == (
        "Canonical evidence shows revenue growth."
    )
    assert candidate.evidence_backed_fact_candidates[0].evidence_refs == (
        "evidence:accepted-1",
    )
    assert candidate.episode_summary_candidate.tool_finding_refs == (
        "evidence:accepted-1",
    )
    assert len(candidate.minimum_preserve_item_candidates) == 1
    assert candidate.minimum_preserve_item_candidates[0].text == (
        "Current user asked to keep the financial analysis context."
    )
    assert candidate.retained_current_user_input_ref == "input-1"
    assert candidate.preserved_material_source_refs == ("input-1", "input-2")
    assert candidate.preserved_canonical_evidence_refs == ("evidence:accepted-1",)
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

    candidate = await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(), StubCancellationToken())

    assert candidate.budget_after_compact >= 80


@pytest.mark.asyncio
async def test_llm_context_compactor_budget_counts_structured_output_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预算估算必须随 fact 与 minimum preserve 文本增长。"""

    compactor = _llm_compactor(
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
    short_candidate = await compactor.compact(_request(), StubCancellationToken())

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
    long_candidate = await compactor.compact(_request(), StubCancellationToken())

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
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    with pytest.raises(LLMCompactionProposalError, match="proposal is empty"):
        await compactor.compact(_request(), StubCancellationToken())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("plain text summary")),
    )
    with pytest.raises(LLMCompactionProposalError, match="not valid JSON"):
        await compactor.compact(_request(), StubCancellationToken())

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
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_malformed_and_schema_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """坏 JSON 与 schema-invalid JSON 必须拒绝。"""

    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final('{"episode_summary_candidate": ')),
    )
    with pytest.raises(LLMCompactionProposalError, match="not valid JSON"):
        await compactor.compact(_request(), StubCancellationToken())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(json.dumps({"episode_summary_candidate": {}}, sort_keys=True))
        ),
    )
    with pytest.raises(LLMCompactionProposalError, match="missing required key"):
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_overlong_structured_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_text 与 minimum preserve text 上限复用 shared constants。"""

    compactor = _llm_compactor(
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
        await compactor.compact(_request(), StubCancellationToken())

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
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_non_canonical_evidence_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fact candidate evidence_refs 只能引用 request.canonical_evidence_refs。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(_proposal_json(fact_evidence_refs=("evidence:not-accepted",)))
        ),
    )
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError, match="unknown label"):
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_parser_rejects_unknown_or_cross_section_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parser 对未知 label 与跨 section label fail closed。"""

    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(_proposal_json(preserved_material_labels=("C1", "missing-label")))
        ),
    )
    with pytest.raises(LLMCompactionProposalError, match="unknown label"):
        await compactor.compact(_request(), StubCancellationToken())

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json(fact_evidence_refs=("H1",)))),
    )
    with pytest.raises(LLMCompactionProposalError, match="section mismatch"):
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_fact_candidate_without_evidence_label_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fact candidate 缺少 evidence label 时 parser 必须拒绝。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json(fact_evidence_refs=()))),
    )
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError, match="evidence label"):
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_minimum_preserve_source_refs_must_be_material_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minimum preserve source refs 必须是当前 material pack labels。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(
            _final(
                _proposal_json(
                    minimum_preserve_source_labels=("payload:accepted-1",)
                )
            )
        ),
    )
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError, match="unknown label"):
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_empty_canonical_source_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt-local label 映射为空 canonical source refs 时返回明确 schema 错误。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json(preserved_material_labels=("C1",)))),
    )
    request = _request()
    material_pack = request.material_pack
    provenance_map = dict(material_pack.provenance_map)
    provenance_map["H1"] = replace(
        provenance_map["H1"],
        canonical_source_refs=(),
    )
    invalid_pack = CompactMaterialPack(
        stable_input=material_pack.stable_input,
        history_input=material_pack.history_input,
        evidence_input=material_pack.evidence_input,
        current_input_anchor=material_pack.current_input_anchor,
        provenance_map=provenance_map,
    )
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(
        LLMCompactionProposalError,
        match="has no canonical source refs",
    ):
        await compactor.compact(
            replace(request, material_pack=invalid_pack),
            StubCancellationToken(),
        )


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_truncated_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compactor final answer 若被 length 截断，必须作为脏 proposal 拒绝。"""

    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final("partial summary", finish_reason=FinishReason.LENGTH)),
    )
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError, match="truncated"):
        await compactor.compact(_request(), StubCancellationToken())


@pytest.mark.asyncio
async def test_llm_context_compactor_applies_runner_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compactor timeout 必须转为稳定 proposal error 并写入取消 token。"""

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
    compactor = _llm_compactor(
        runner_spec=_runner_spec(default_timeout_seconds=0.01),
        runner_options=_runner_options(),
    )
    cancellation_token = StubCancellationToken()

    with pytest.raises(LLMCompactionProposalError, match="proposal timed out"):
        await compactor.compact(_request(), cancellation_token)

    assert cancellation_token.is_cancelled() is True
    assert cancellation_token.cancel_reason() == "compactor_proposal_timeout"


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
                    "api_key=plainsecret token=tokensecret "
                    "secret=secretvalue transient unavailable"
                ),
                provider_request_id="provider-request-1",
                recoverable=True,
            )
        ),
    )
    compactor = _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    )

    with pytest.raises(LLMCompactionProposalError) as exc_info:
        await compactor.compact(_request(), StubCancellationToken())

    message = str(exc_info.value)
    assert "error_code=unknown_error" in message
    assert "recoverable=True" in message
    assert "503" in message
    assert "transient unavailable" in message
    assert "error-secret" not in message
    assert "deepsecret" not in message
    assert "plainsecret" not in message
    assert "tokensecret" not in message
    assert "secretvalue" not in message
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

    candidate = await _llm_compactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
    ).compact(_request(), StubCancellationToken())

    evidence = candidate.preservation_evidence[0]
    assert evidence.material_source_refs == (
        "input-1",
        "input-2",
    )
    assert evidence.canonical_evidence_refs == ("evidence:accepted-1",)
    assert candidate.episode_summary_candidate.evidence_refs == (
        evidence.evidence_id,
    )
    assert candidate.pinned_state_patch_candidate.current_goal.evidence_refs == (
        evidence.evidence_id,
    )


@pytest.mark.asyncio
async def test_range_endpoint_label_with_multiple_refs_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Range endpoint label 映射多个 canonical refs 时必须 fail closed。"""

    request = _request()
    material_pack = _material_pack_with_history_refs(("input-2", "input-2b"))
    request = replace(request, material_pack=material_pack)
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json())),
    )

    with pytest.raises(LLMCompactionProposalError, match="exactly one"):
        await _llm_compactor(
            runner_spec=_runner_spec(),
            runner_options=_runner_options(),
        ).compact(request, StubCancellationToken())


@pytest.mark.asyncio
async def test_range_endpoint_label_without_ref_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Range endpoint label 没有 canonical ref 时必须 fail closed。"""

    request = _request()
    material_pack = _material_pack_with_history_refs(())
    request = replace(request, material_pack=material_pack)
    monkeypatch.setattr(
        "dayu.host.llm_compaction.run_agent_and_wait",
        _fake_run_factory(_final(_proposal_json())),
    )

    with pytest.raises(LLMCompactionProposalError, match="no canonical source refs"):
        await _llm_compactor(
            runner_spec=_runner_spec(),
            runner_options=_runner_options(),
        ).compact(request, StubCancellationToken())


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
    compactor = _llm_compactor(
        runner_spec=runner_spec,
        runner_options=_runner_options(),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        await compactor.compact(_request(), StubCancellationToken())

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


def _request(
    *,
    raw_tool_content: str = "Revenue grew 12% year over year.",
) -> CompactionRequest:
    """构造 compaction request。

    :param raw_tool_content: accepted 工具结果 raw 内容。
    :returns: CompactionRequest。
    """

    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-1",
        run_id="run-1",
        attempt_id=None,
        execution_id=None,
        memory_snapshot_cursor=7,
        material_pack=_material_pack(raw_tool_content),
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=2,
            material_pack=_material_pack(raw_tool_content),
        ),
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


def _material_pack(raw_tool_content: str) -> CompactMaterialPack:
    """构造测试 material pack。

    :param raw_tool_content: raw evidence 文本。
    :returns: material pack。
    """

    return build_initial_material_pack(
        current_input_ref="input-1",
        current_input_text="current user text",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="input-2",
                text="previous assistant turn",
                kind=CompactMaterialBlockKind.RAW_ASSISTANT_TURN,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-1",
                accepted_evidence_id="evidence:accepted-1",
                tool_result_event_ref="event-tool-result-1",
                tool_call_event_ref="event-tool-call-1",
                readable_tool_name="fins.search",
                readable_query_text="accepted tool query",
                raw_result_text=raw_tool_content,
                readable_source_text="accepted tool evidence",
                payload_refs=("payload:accepted-1",),
            ),
        ),
    )


def _material_pack_with_history_refs(
    canonical_source_refs: tuple[str, ...],
) -> CompactMaterialPack:
    """构造替换 H1 provenance refs 的 material pack。

    :param canonical_source_refs: H1 对应 canonical source refs。
    :returns: compact material pack。
    """

    pack = _material_pack("Revenue grew 12% year over year.")
    provenance = dict(pack.provenance_map)
    history_entry = provenance["H1"]
    provenance["H1"] = replace(
        history_entry,
        canonical_source_refs=canonical_source_refs,
        source_event_refs=canonical_source_refs,
    )
    return replace(pack, provenance_map=provenance)


def _proposal_json(
    *,
    claim_text: str = "Canonical evidence shows revenue growth.",
    minimum_preserve_text: str = (
        "Current user asked to keep the financial analysis context."
    ),
    fact_evidence_refs: tuple[str, ...] = ("E1",),
    minimum_preserve_source_labels: tuple[str, ...] = ("C1",),
    preserved_material_labels: tuple[str, ...] = ("C1", "H1"),
    preservation_material_labels: tuple[str, ...] = ("C1", "H1"),
    preservation_evidence_labels: tuple[str, ...] = ("E1",),
) -> str:
    """构造 LLM structured JSON proposal。

    :param claim_text: fact candidate claim_text。
    :param minimum_preserve_text: minimum preserve item text。
    :param fact_evidence_refs: fact candidate evidence refs。
    :param minimum_preserve_source_labels: minimum preserve source labels。
    :param preserved_material_labels: preserved material labels。
    :param preservation_material_labels: preservation evidence material labels。
    :param preservation_evidence_labels: preservation evidence labels。
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
                "tool_finding_labels": ["E1"],
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
                    "evidence_labels": list(fact_evidence_refs),
                    "attributes": {},
                }
            ],
            "minimum_preserve_item_candidates": [
                {
                    "item_id": "preserve-current-input",
                    "label": "current input",
                    "text": minimum_preserve_text,
                    "source_labels": list(minimum_preserve_source_labels),
                    "preserve_reason": "needed_for_recent_reference",
                }
            ],
            "preservation_evidence": [
                {
                    "material_labels": list(preservation_material_labels),
                    "evidence_labels": list(preservation_evidence_labels),
                    "compact_range": {
                        "range_ref": "range-older-raw-turns",
                        "start_material_label": "H1",
                        "end_material_label": "H1",
                    },
                }
            ],
            "retained_current_input_label": "C1",
            "preserved_material_labels": list(preserved_material_labels),
            "preserved_evidence_labels": ["E1"],
            "preserved_evidence_backed_fact_refs": ["fact-1"],
            "dropped_ranges": [],
            "summarized_ranges": [
                {
                    "range_ref": "range-older-raw-turns",
                    "start_material_label": "H1",
                    "end_material_label": "H1",
                }
            ],
        },
        sort_keys=True,
    )


def _accepted_evidence_envelope() -> AcceptedEvidenceEnvelope:
    """构造测试用 canonical evidence envelope。

    :returns: canonical evidence envelope。
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
