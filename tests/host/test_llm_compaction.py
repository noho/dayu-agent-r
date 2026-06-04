"""Host-owned LLM vNext context compactor tests。"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    conversation_compact_input_vnext_from_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
import dayu.host.llm_compaction as llm_compaction_module
from dayu.host.llm_compaction import (
    LLMCompactionProposalError,
    LLMContextCompactor,
    parse_conversation_compact_output_vnext,
)
from tests.host.fake_cancellation import StubCancellationToken
from tests.host.fake_compaction import fake_compaction_proposal_from_material_json

_TEST_SYSTEM_PROMPT = "test compactor system prompt"
_TEST_USER_PROMPT_TEMPLATE = "test compactor user prompt\n\n<<compaction_request>>\n\nreturn strict json"
_TEST_AGENT_POLICY = AgentPolicy(
    max_iterations=1,
    continuation_max_attempts=0,
    allow_tool_calls=False,
    tool_execution_timeout_seconds=1.0,
)
_PROMPT_TEMPLATE_PATH = Path("dayu/config/prompts/scenes/conversation_compaction_user.md")


def test_llm_context_compactor_does_not_use_thread_bridge() -> None:
    """LLM compactor 不再使用线程桥、join timeout 或嵌套 asyncio.run。"""

    source = inspect.getsource(llm_compaction_module)

    assert "threading" not in source
    assert "thread.join(" not in source
    assert "asyncio.run" not in source


@pytest.mark.parametrize(
    ("raw_message", "secret_value"),
    (
        ("provider failed Authorization: Bearer bearer-secret tail", "bearer-secret"),
        ("provider failed api_key=api-key-secret tail", "api-key-secret"),
        ("provider failed token=token-secret tail", "token-secret"),
        ("provider failed secret=secret-value tail", "secret-value"),
        ("provider failed authorization=authorization-secret tail", "authorization-secret"),
        ("provider failed password=password-secret tail", "password-secret"),
        ("provider failed api key spaced-secret tail", "spaced-secret"),
        ("provider failed apikey=apikey-secret tail", "apikey-secret"),
        ("provider failed api-key:colon-secret tail", "colon-secret"),
        ("provider failed api-key: spaced-colon-secret tail", "spaced-colon-secret"),
    ),
)
def test_safe_outcome_text_redacts_sensitive_diagnostic_values(
    raw_message: str,
    secret_value: str,
) -> None:
    """_safe_outcome_text 脱敏 runner outcome 中的敏感值。

    :param raw_message: 包含敏感值写法的原始 outcome 文本。
    :param secret_value: 不允许出现在脱敏结果中的明文值。
    """

    safe_message = llm_compaction_module._safe_outcome_text(raw_message)

    assert secret_value not in safe_message
    assert "<redacted>" in safe_message
    assert "provider failed" in safe_message
    assert "tail" in safe_message


def test_safe_outcome_text_does_not_redact_plain_token_diagnostic() -> None:
    """_safe_outcome_text 不误脱敏普通 token 诊断句。"""

    message = "JWT token has expired"

    assert llm_compaction_module._safe_outcome_text(message) == message


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


def test_parse_conversation_compact_output_vnext_accepts_design_schema() -> None:
    """vNext parser 接受设计 schema 并返回 ConversationCompactOutputVNext。"""

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    candidate = parse_conversation_compact_output_vnext(
        compact_input,
        fake_compaction_proposal_from_material_json(
            cast(Mapping[str, JsonValue], compact_input.to_json())
        ),
    )

    assert isinstance(candidate, ConversationCompactOutputVNext)
    assert candidate.evidence_backed_facts[0].evidence_labels == ("E1",)
    assert candidate.answer_anchors[0].answer_source_labels == ("A1",)


def test_prompt_forward_intent_enum_values_match_parser_vnext() -> None:
    """prompt forward intent enum 示例值必须能被 vNext parser enum 接受。"""

    intent_type_values = _prompt_schema_pipe_values("intent_type")
    status_values = _prompt_schema_pipe_values("status")

    parsed_intent_types = tuple(
        ForwardIntentTypeVNext(value) for value in intent_type_values
    )
    parsed_statuses = tuple(
        ForwardIntentStatusVNext(value) for value in status_values
    )

    assert len(parsed_intent_types) == len(intent_type_values)
    assert len(parsed_statuses) == len(status_values)


def test_parse_conversation_compact_output_vnext_fails_closed_for_old_schema() -> None:
    """vNext parser 对旧 candidate schema fail closed。"""

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    old_schema = {
        "candidate_id": "old-candidate",
        "episode_summary_candidate": {"summary_text": "old"},
        "pinned_state_patch_candidate": {"current_goal": {"operation": "replace"}},
    }

    with pytest.raises(LLMCompactionProposalError, match="missing required key"):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(old_schema, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_rejects_current_anchor_label() -> None:
    """vNext parser 禁止 LLM candidate 引用 current input anchor。"""

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["session_summary"] = {
        "summary_text": "bad citation",
        "source_labels": ["C1"],
    }

    with pytest.raises(LLMCompactionProposalError, match="current input anchor"):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


@pytest.mark.asyncio
async def test_llm_context_compactor_compact_uses_vnext_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMContextCompactor.compact 渲染 vNext input 并返回 vNext output。"""

    calls: list[AgentRunRequest] = []

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回 deterministic vNext final answer。

        :param request: Engine run request。
        :returns: Engine final answer。
        """

        calls.append(request)
        compact_input = conversation_compact_input_vnext_from_material_pack(
            _request().material_pack
        )
        return _final(
            fake_compaction_proposal_from_material_json(
                cast(Mapping[str, JsonValue], compact_input.to_json())
            )
        )

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    candidate = await _llm_compactor().compact(_request(), StubCancellationToken())

    assert isinstance(candidate, ConversationCompactOutputVNext)
    assert len(calls) == 1
    request = calls[0]
    assert request.disable_tools is True
    assert request.tool_schemas == ()
    prompt = request.messages[1].content
    assert isinstance(prompt, str)
    assert '"previous_compacted_view"' in prompt
    assert '"trace_material"' in prompt
    assert '"evidence_material"' in prompt
    assert '"answer_material"' in prompt
    assert '"stable_input"' not in prompt
    assert '"history_input"' not in prompt
    assert '"candidate_id"' not in prompt


@pytest.mark.asyncio
async def test_llm_context_compactor_rejects_non_final_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMContextCompactor.compact 拒绝非 final answer outcome。"""

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回失败 outcome。

        :param request: Engine run request。
        :returns: Engine failed outcome。
        """

        del request
        return EngineRunOutcomeFailed(
            session_id="session-1",
            run_id="run-1",
            error_code="provider_error",
            message="provider failed api_key=secret",
            provider_request_id=None,
            client_correlation_id=None,
            recoverable=False,
        )

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    with pytest.raises(LLMCompactionProposalError, match="<redacted>"):
        await _llm_compactor().compact(_request(), StubCancellationToken())


def _proposal_json(compact_input: ConversationCompactInputVNext) -> dict[str, JsonValue]:
    """构造可变 vNext proposal JSON。

    :param compact_input: vNext compact input。
    :returns: vNext proposal dict。
    :raises TypeError: fake proposal 不是 JSON object 时抛出。
    """

    raw = fake_compaction_proposal_from_material_json(
        cast(Mapping[str, JsonValue], compact_input.to_json())
    )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError("proposal must be object")
    return cast(dict[str, JsonValue], parsed)


def _prompt_schema_pipe_values(field_name: str) -> tuple[str, ...]:
    """读取 prompt schema 示例中以竖线分隔的字段候选值。

    :param field_name: JSON schema 示例字段名。
    :returns: 字段候选值元组。
    :raises AssertionError: 模板中缺少字段或字段值为空时抛出。
    """

    field_prefix = f'"{field_name}": "'
    for line in _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(field_prefix):
            raw_values = stripped.removeprefix(field_prefix).split('"', 1)[0]
            values = tuple(value for value in raw_values.split("|") if value != "")
            assert len(values) > 0
            return values
    raise AssertionError(f"missing prompt schema field: {field_name}")


def _llm_compactor() -> LLMContextCompactor:
    """构造测试用 LLM compactor。

    :returns: 测试 compactor。
    """

    return LLMContextCompactor(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
        agent_policy=_TEST_AGENT_POLICY,
        system_prompt=_TEST_SYSTEM_PROMPT,
        user_prompt_template=_TEST_USER_PROMPT_TEMPLATE,
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
        session_id="session-llm",
        run_id="run-llm",
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


def _final(content: str, *, finish_reason: FinishReason = FinishReason.STOP) -> EngineRunOutcomeFinalAnswer:
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


def _runner_spec() -> RunnerSpec:
    """构造 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
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
