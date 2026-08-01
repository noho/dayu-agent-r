"""Host-owned LLM vNext context compactor tests。"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TypeGuard

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.engine_events import runner_role_sequence_digest
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.error_codes import adapter_error_code
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
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
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import fake_compaction_proposal_from_material_json

_TEST_SYSTEM_PROMPT = "test compactor system prompt"
_TEST_USER_PROMPT_TEMPLATE = "test compactor user prompt\n\n<<compaction_request>>\n\nreturn strict json"
_TEST_AGENT_POLICY = AgentPolicy(
    max_iterations=1,
    continuation_max_attempts=0,
    allow_tool_calls=False,
    tool_execution_timeout_seconds=1.0,
    fallback_prompt="test fallback prompt",
    continuation_prompt="test continuation prompt",
)
_PROMPT_TEMPLATE_PATH = Path("dayu/config/prompts/scenes/conversation_compaction_user.md")
_UNTRUSTED_COMPACTION_MATERIAL_BEGIN = "UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN"
_UNTRUSTED_COMPACTION_MATERIAL_END = "UNTRUSTED_COMPACTION_MATERIAL_JSON_END"
_LLM_FACING_OUTPUT_CONTRACT_IDENTIFIER = "conversation_compact_output_v1"
_INTERNAL_COMPACT_OUTPUT_TYPE_NAME = "ConversationCompactOutputVNext"
_INTERNAL_COMPACT_INPUT_TYPE_NAME = "ConversationCompactInputVNext"
_LARGE_COMPACT_FACT_COUNT = 80
_LARGE_ANSWER_ANCHOR_CHILD_COUNT = 40


def test_llm_context_compactor_does_not_use_thread_bridge() -> None:
    """LLM compactor 不再使用线程桥、join timeout 或嵌套 asyncio.run。"""

    source = inspect.getsource(llm_compaction_module)

    assert "threading" not in source
    assert "thread.join(" not in source
    assert "asyncio.run" not in source


def test_llm_compaction_dead_post_compact_budget_constants_removed() -> None:
    """post-compact budget 常量归 context_budget owner，llm_compaction 不再定义副本。"""

    source = inspect.getsource(llm_compaction_module)
    removed_constants = (
        "_POST_COMPACT_" + "SYSTEM_PROMPT_ESTIMATE",
        "_POST_COMPACT_" + "BASE_MESSAGE_COUNT",
        "_POST_COMPACT_" + "TOOL_SCHEMA_OVERHEAD_COUNT",
    )

    for constant_name in removed_constants:
        assert constant_name not in source


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


def test_llm_context_compactor_prepares_same_source_runner_input() -> None:
    """prepared proposal input 与真实 Engine request messages 同源。"""

    compaction_request = _request_with_long_input_material()
    prepared = _llm_compactor().prepare_compactor_proposal_run_input(
        compaction_request,
        ControllableCancellationToken(),
        compaction_operation_id="event-context-compact-requested-test",
        compaction_attempt_number=2,
    )
    request = prepared.agent_request
    roles = tuple(message.role.value for message in request.messages)

    assert prepared.compactor_engine_run_id == request.run_id
    assert prepared.message_count == len(request.messages) == 2
    assert prepared.role_sequence_digest == runner_role_sequence_digest(roles)
    assert roles == ("system", "user")
    assert prepared.compaction_request_digest == compaction_request.digest()
    assert prepared.compactor_input_projection_digest == llm_compaction_module.sha256_digest_json(
        prepared.compactor_input_projection
    )
    projection_text = json.dumps(
        prepared.compactor_input_projection,
        ensure_ascii=False,
        sort_keys=True,
    )
    assert _TEST_SYSTEM_PROMPT not in projection_text
    assert _TEST_USER_PROMPT_TEMPLATE not in projection_text
    user_prompt = request.messages[1].content
    assert isinstance(user_prompt, str)
    material_json = _material_json_from_compactor_prompt(user_prompt)
    current_anchor = _required_mapping(
        material_json["current_input_anchor"],
        field_name="current_input_anchor",
    )
    evidence_items = _required_list(
        material_json["evidence_material"],
        field_name="evidence_material",
    )
    evidence_item = _required_mapping(evidence_items[0], field_name="evidence_item")
    assert current_anchor["text"] == "current " + ("input " * 300)
    assert evidence_item["source_label"] == "E1"
    assert evidence_item["response_text"] == "evidence " + ("detail " * 700)


def test_parse_conversation_compact_output_vnext_accepts_design_schema() -> None:
    """vNext parser 接受设计 schema 并返回 ConversationCompactOutputVNext。"""

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    candidate = parse_conversation_compact_output_vnext(
        compact_input,
        fake_compaction_proposal_from_material_json(
            _compact_input_json(compact_input)
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


def test_compaction_prompt_does_not_expose_internal_evidence_or_run_state_terms() -> None:
    """compaction prompt 不暴露 Host run-state 或 evidence pipeline 内部枚举。"""

    prompt = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "user_visible_run_state" not in prompt
    assert "tool_source_text" not in prompt
    assert "accepted_evidence_material" not in prompt
    assert "evidence_kind" not in prompt


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


def test_parse_conversation_compact_output_vnext_rejects_malformed_json() -> None:
    """vNext parser 对 malformed JSON fail closed。

    :returns: ``None``。
    :raises AssertionError: parser 未返回预期 proposal 失败诊断时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )

    with pytest.raises(LLMCompactionProposalError, match="not valid JSON"):
        parse_conversation_compact_output_vnext(compact_input, "{bad")


def test_parse_conversation_compact_output_vnext_rejects_top_level_non_object() -> None:
    """vNext parser 对 top-level 非 object proposal fail closed。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 top-level proposal object 诊断时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )

    with pytest.raises(LLMCompactionProposalError, match="proposal must be object"):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps([], sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_missing_required_key_path() -> None:
    """vNext parser 对缺失必需顶层字段返回字段路径。

    :returns: ``None``。
    :raises AssertionError: parser 未返回缺失字段诊断时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    del proposal["diagnostics"]

    with pytest.raises(
        LLMCompactionProposalError,
        match="missing required key: diagnostics",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_field_type_path() -> None:
    """vNext parser 对普通字段类型错误返回完整字段路径。

    :returns: ``None``。
    :raises AssertionError: parser 未返回字段类型错误路径时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["session_summary"] = {
        "summary_text": 1,
        "source_labels": ["T1"],
    }

    with pytest.raises(
        LLMCompactionProposalError,
        match="session_summary.summary_text",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_nested_array_type_path() -> None:
    """vNext parser 对嵌套数组类型错误返回完整字段路径。

    :returns: ``None``。
    :raises AssertionError: parser 未返回嵌套数组路径时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["answer_anchors"] = [
        {
            "anchor_title": "现金流结论",
            "anchor_items": "bad",
            "answer_source_labels": ["A1"],
        }
    ]

    with pytest.raises(
        LLMCompactionProposalError,
        match=r"answer_anchors\[0\]\.anchor_items",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_array_item_type_path() -> None:
    """vNext parser 对数组元素类型错误返回完整元素路径。

    :returns: ``None``。
    :raises AssertionError: parser 未返回数组元素路径时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["diagnostics"] = [
        {
            "code": "invalid_source",
            "text": "诊断说明",
            "source_labels": [1],
        }
    ]

    with pytest.raises(
        LLMCompactionProposalError,
        match=r"diagnostics\[0\]\.source_labels\[0\]",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_accepts_large_top_level_array() -> None:
    """vNext parser 接受较大的顶层 compact material 数组。

    :returns: ``None``。
    :raises AssertionError: parser 错误拒绝较大的顶层数组时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    facts: list[JsonValue] = []
    for _ in range(_LARGE_COMPACT_FACT_COUNT):
        facts.append(_fact_json())
    proposal["evidence_backed_facts"] = facts

    parsed = parse_conversation_compact_output_vnext(
        compact_input,
        json.dumps(proposal, sort_keys=True),
    )

    assert len(parsed.evidence_backed_facts) == _LARGE_COMPACT_FACT_COUNT


def test_parse_conversation_compact_output_vnext_accepts_large_nested_array() -> None:
    """vNext parser 接受较大的嵌套 compact material 数组。

    :returns: ``None``。
    :raises AssertionError: parser 错误拒绝较大的嵌套数组时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    anchor_items: list[JsonValue] = []
    for index in range(_LARGE_ANSWER_ANCHOR_CHILD_COUNT):
        anchor_items.append(
            {
                "display_text": f"锚点 {index}",
                "ordinal": index,
            }
        )
    proposal["answer_anchors"] = [
        {
            "anchor_title": "现金流结论",
            "anchor_items": anchor_items,
            "answer_source_labels": ["A1"],
        }
    ]

    parsed = parse_conversation_compact_output_vnext(
        compact_input,
        json.dumps(proposal, sort_keys=True),
    )

    assert len(parsed.answer_anchors) == 1
    assert len(parsed.answer_anchors[0].anchor_items) == _LARGE_ANSWER_ANCHOR_CHILD_COUNT


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


def test_parse_conversation_compact_output_vnext_does_not_accept_fact_evidence_kind() -> None:
    """vNext parser 不要求也不保留 unsupported fact evidence kind。

    :returns: ``None``。
    :raises AssertionError: parser 错误保留 unsupported 字段时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["evidence_backed_facts"] = [
        {
            "claim_text": "经营现金流同比增长",
            "evidence_labels": ["E1"],
            "evidence_kind": "tool_result",
            "source_labels": [],
        }
    ]

    parsed = parse_conversation_compact_output_vnext(
        compact_input,
        json.dumps(proposal, sort_keys=True),
    )

    assert parsed.evidence_backed_facts[0].to_json() == {
        "claim_text": "经营现金流同比增长",
        "evidence_labels": ["E1"],
        "source_labels": [],
    }


def test_parse_conversation_compact_output_vnext_reports_forward_intent_type_enum_value() -> None:
    """vNext parser 对 forward_intents.intent_type 返回完整路径与非法值。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 intent_type 路径和非法枚举值时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["forward_intents"] = [
        {
            "intent_type": "bad_intent_type",
            "text": "继续分析",
            "status": "pending",
            "source_labels": ["T1"],
        }
    ]

    with pytest.raises(
        LLMCompactionProposalError,
        match=r"forward_intents\[0\]\.intent_type.*bad_intent_type",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_forward_status_enum_value() -> None:
    """vNext parser 对 forward_intents.status 返回完整路径与非法值。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 status 路径和非法枚举值时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["forward_intents"] = [
        {
            "intent_type": "next_step_note",
            "text": "继续分析",
            "status": "bad_status",
            "source_labels": ["T1"],
        }
    ]

    with pytest.raises(
        LLMCompactionProposalError,
        match=r"forward_intents\[0\]\.status.*bad_status",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_reference_reason_enum_value() -> None:
    """vNext parser 对 reference_continuity_items.reason 返回完整路径与非法值。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 reason 路径和非法枚举值时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["reference_continuity_items"] = [
        {
            "text": "保留本地引用",
            "reason": "bad_reason",
            "source_labels": ["T1"],
        }
    ]

    with pytest.raises(
        LLMCompactionProposalError,
        match=r"reference_continuity_items\[0\]\.reason.*bad_reason",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_rejects_unknown_label() -> None:
    """vNext parser 拒绝语法合理但当前 input 不存在的 source label。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 unknown source label 诊断时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["diagnostics"] = [
        {
            "code": "unknown_label",
            "text": "未知标签",
            "source_labels": ["Z99"],
        }
    ]

    with pytest.raises(LLMCompactionProposalError, match="unknown source label"):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_rejects_stale_label() -> None:
    """vNext parser 拒绝形似历史 prompt-local label 的 stale source label。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 stale source label 诊断时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["diagnostics"] = [
        {
            "code": "stale_label",
            "text": "过期标签",
            "source_labels": ["E99"],
        }
    ]

    with pytest.raises(LLMCompactionProposalError, match="stale source label"):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_rejects_cross_section_label() -> None:
    """vNext parser 拒绝跨 section 的 source label 引用。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 cross-section label 诊断时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["evidence_backed_facts"] = [
        {
            "claim_text": "经营现金流同比增长",
            "evidence_labels": ["A1"],
            "source_labels": [],
        }
    ]

    with pytest.raises(LLMCompactionProposalError, match="cross-section label"):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_reports_anchor_ordinal_path() -> None:
    """vNext parser 对 answer anchor 子项 ordinal 返回完整嵌套字段路径。

    :returns: ``None``。
    :raises AssertionError: parser 未返回 ordinal 完整路径时抛出。
    """

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["answer_anchors"] = [
        {
            "anchor_title": "现金流结论",
            "anchor_items": [
                {"display_text": "经营现金流同比增长", "ordinal": 0},
                {"display_text": "第二条锚点", "ordinal": -1},
            ],
            "answer_source_labels": ["A1"],
        }
    ]

    with pytest.raises(
        LLMCompactionProposalError,
        match=r"answer_anchors\[0\]\.anchor_items\[1\]\.ordinal",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


def test_parse_conversation_compact_output_vnext_wraps_candidate_safety_net() -> None:
    """vNext parser 将 candidate safety-net 拒绝包装为公开 proposal 失败类型。"""

    compact_input = conversation_compact_input_vnext_from_material_pack(
        _request().material_pack
    )
    proposal = _proposal_json(compact_input)
    proposal["session_summary"] = {
        "summary_text": "缺少支撑标签的摘要",
        "source_labels": [],
    }

    with pytest.raises(
        LLMCompactionProposalError,
        match="compactor vNext proposal schema invalid",
    ):
        parse_conversation_compact_output_vnext(
            compact_input,
            json.dumps(proposal, sort_keys=True),
        )


@pytest.mark.asyncio
async def test_llm_context_compactor_compact_uses_vnext_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMContextCompactor.compact 渲染 vNext input 并返回 vNext output。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: runner request 或渲染 material contract 不符合预期时抛出。
    """

    calls: list[AgentRunRequest] = []
    returned_identities: list[SuccessfulRunnerResponseIdentity] = []

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回 deterministic vNext final answer。

        :param request: Engine run request。
        :returns: Engine final answer。
        """

        calls.append(request)
        compact_input = conversation_compact_input_vnext_from_material_pack(
            _request().material_pack
        )
        outcome = _final(
            request=request,
            content=fake_compaction_proposal_from_material_json(
                _compact_input_json(compact_input)
            ),
            finish_reason=FinishReason.STOP,
            provider_request_id="provider-request-compactor",
        )
        returned_identities.append(outcome.response_identity)
        return outcome

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    proposal = await _llm_compactor().compact(
        _request(),
        ControllableCancellationToken(),
    )

    assert isinstance(proposal.candidate, ConversationCompactOutputVNext)
    assert proposal.successful_response_identity == returned_identities[0]
    assert (
        proposal.successful_response_identity.runner_request_identity.run_id
        == calls[0].run_id
    )
    assert (
        proposal.successful_response_identity.provider_request_id
        == "provider-request-compactor"
    )
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
    assert f'"output_schema_name": "{_LLM_FACING_OUTPUT_CONTRACT_IDENTIFIER}"' in prompt
    assert _INTERNAL_COMPACT_OUTPUT_TYPE_NAME not in prompt
    assert _INTERNAL_COMPACT_INPUT_TYPE_NAME not in prompt
    assert '"stable_input"' not in prompt
    assert '"history_input"' not in prompt
    assert '"candidate_id"' not in prompt
    material_json = _material_json_from_compactor_prompt(prompt)
    instruction = _required_mapping(material_json["instruction"], field_name="instruction")
    assert (
        instruction["output_schema_name"]
        == _LLM_FACING_OUTPUT_CONTRACT_IDENTIFIER
    )


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
            error_code=adapter_error_code("provider_error"),
            message="provider failed api_key=secret",
            provider_request_id=None,
            client_correlation_id=None,
            recoverable=False,
        )

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    with pytest.raises(LLMCompactionProposalError, match="<redacted>") as exc_info:
        await _llm_compactor().compact(_request(), ControllableCancellationToken())
    assert exc_info.value.successful_response_identity is None
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mismatch_kind", "expected_message"),
    [
        ("run_id", "Engine run identity mismatch"),
        ("ordinary_identity", "must not use ordinary attempt identity"),
        ("provider", "effective provider mismatch"),
        ("model", "effective model mismatch"),
    ],
)
async def test_llm_context_compactor_rejects_cross_wired_success_identity(
    monkeypatch: pytest.MonkeyPatch,
    mismatch_kind: str,
    expected_message: str,
) -> None:
    """prepared request 与 final response identity 串线时 fail-closed。

    :param monkeypatch: pytest monkeypatch fixture。
    :param mismatch_kind: 待注入的串线字段类别。
    :param expected_message: 对应 owner-level 拒绝消息。
    :returns: ``None``。
    :raises AssertionError: Host 接受串线 identity 或丢失失败 identity 时抛出。
    """

    returned_identities: list[SuccessfulRunnerResponseIdentity] = []

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回 identity 与 prepared request 不匹配的成功 final。

        :param request: 当前 prepared Engine request。
        :returns: 携带指定串线 identity 的 final outcome。
        :raises ValueError: 测试 identity 构造非法时抛出。
        """

        compact_input = conversation_compact_input_vnext_from_material_pack(
            _request().material_pack
        )
        outcome = _final(
            request=request,
            content=fake_compaction_proposal_from_material_json(
                _compact_input_json(compact_input)
            ),
            finish_reason=FinishReason.STOP,
            provider_request_id="provider-request-mismatch",
        )
        identity = outcome.response_identity
        request_identity = identity.runner_request_identity
        if mismatch_kind == "run_id":
            request_identity = build_runner_request_identity(
                run_id=f"{request.run_id}-cross-wired",
                attempt_id=None,
                execution_id=None,
                iteration_id=request_identity.iteration_id,
                iteration_index=request_identity.iteration_index,
                runner_call_index=request_identity.runner_call_index,
            )
            identity = replace(
                identity,
                runner_request_identity=request_identity,
            )
        elif mismatch_kind == "ordinary_identity":
            request_identity = build_runner_request_identity(
                run_id=request.run_id,
                attempt_id="ordinary-attempt",
                execution_id="ordinary-execution",
                iteration_id=request_identity.iteration_id,
                iteration_index=request_identity.iteration_index,
                runner_call_index=request_identity.runner_call_index,
            )
            identity = replace(
                identity,
                runner_request_identity=request_identity,
            )
        elif mismatch_kind == "provider":
            identity = replace(identity, effective_provider="cross-wired-provider")
        elif mismatch_kind == "model":
            identity = replace(identity, effective_model="cross-wired-model")
        else:
            raise AssertionError("unsupported mismatch kind")
        returned_identities.append(identity)
        return replace(outcome, response_identity=identity)

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    with pytest.raises(
        LLMCompactionProposalError,
        match=expected_message,
    ) as exc_info:
        await _llm_compactor().compact(
            _request(),
            ControllableCancellationToken(),
        )

    assert exc_info.value.successful_response_identity == returned_identities[0]


@pytest.mark.asyncio
async def test_llm_context_compactor_length_error_keeps_success_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LENGTH 已成功 final 的 proposal error 保留同一次 response identity。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: LENGTH 错误丢失成功 response identity 时抛出。
    """

    returned_identities: list[SuccessfulRunnerResponseIdentity] = []

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回带 provider request id 的 LENGTH final。

        :param request: 当前 prepared Engine request。
        :returns: LENGTH final outcome。
        """

        outcome = _final(
            request=request,
            content="truncated proposal",
            finish_reason=FinishReason.LENGTH,
            provider_request_id="provider-request-length",
        )
        returned_identities.append(outcome.response_identity)
        return outcome

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    with pytest.raises(
        LLMCompactionProposalError,
        match="finish_reason=length",
    ) as exc_info:
        await _llm_compactor().compact(
            _request(),
            ControllableCancellationToken(),
        )

    assert exc_info.value.successful_response_identity == returned_identities[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("not-json", "not valid JSON"),
        ("{}", "schema invalid"),
    ],
)
async def test_llm_context_compactor_parse_errors_keep_success_identity(
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    expected_message: str,
) -> None:
    """成功 final 后的 parse/schema rejection 保留同源 identity。

    :param monkeypatch: pytest monkeypatch fixture。
    :param content: 触发 parse 或 schema rejection 的 final 文本。
    :param expected_message: 对应解析失败消息。
    :returns: ``None``。
    :raises AssertionError: parse/schema 错误丢失成功 identity 时抛出。
    """

    returned_identities: list[SuccessfulRunnerResponseIdentity] = []

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回带 provider request id 的非法 proposal final。

        :param request: 当前 prepared Engine request。
        :returns: 内容非法但 Engine 成功的 final outcome。
        """

        outcome = _final(
            request=request,
            content=content,
            finish_reason=FinishReason.STOP,
            provider_request_id="provider-request-invalid-proposal",
        )
        returned_identities.append(outcome.response_identity)
        return outcome

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    with pytest.raises(
        LLMCompactionProposalError,
        match=expected_message,
    ) as exc_info:
        await _llm_compactor().compact(
            _request(),
            ControllableCancellationToken(),
        )

    assert exc_info.value.successful_response_identity == returned_identities[0]


@pytest.mark.asyncio
async def test_llm_context_compactor_unavailable_provider_id_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider request id 不可用时仍返回显式 UNAVAILABLE identity。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: Host 以缺省值代替显式不可用状态时抛出。
    """

    async def fake_run(request: AgentRunRequest) -> AgentRunResult:
        """返回 provider request id 不可用的合法 final。

        :param request: 当前 prepared Engine request。
        :returns: 合法 final outcome。
        """

        compact_input = conversation_compact_input_vnext_from_material_pack(
            _request().material_pack
        )
        return _final(
            request=request,
            content=fake_compaction_proposal_from_material_json(
                _compact_input_json(compact_input)
            ),
            finish_reason=FinishReason.STOP,
            provider_request_id=None,
        )

    monkeypatch.setattr("dayu.host.llm_compaction.run_agent_and_wait", fake_run)

    proposal = await _llm_compactor().compact(
        _request(),
        ControllableCancellationToken(),
    )

    assert proposal.successful_response_identity.provider_request_id_availability is (
        ProviderRequestIdAvailability.UNAVAILABLE
    )
    assert proposal.successful_response_identity.provider_request_id is None


@pytest.mark.asyncio
async def test_llm_context_compactor_timeout_has_no_success_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功 final 前 timeout 必须为 null identity 并通知 Host token。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: timeout 被伪造成成功 response identity 时抛出。
    """

    async def fake_run(
        request: AgentRunRequest,
        *,
        timeout_seconds: float,
    ) -> AgentRunResult:
        """模拟 Engine public runner timeout。

        :param request: 当前 prepared Engine request。
        :param timeout_seconds: Host 传入的 proposal timeout。
        :returns: 不会返回。
        :raises TimeoutError: 始终抛出。
        """

        del request, timeout_seconds
        raise TimeoutError("provider timeout api_key=secret")

    monkeypatch.setattr(llm_compaction_module, "_run_agent_request", fake_run)
    token = ControllableCancellationToken()

    with pytest.raises(
        LLMCompactionProposalError,
        match="compactor proposal timed out",
    ) as exc_info:
        await _llm_compactor().compact(_request(), token)

    assert exc_info.value.successful_response_identity is None
    assert token.is_cancelled()
    assert token.cancel_reason() == "compactor_proposal_timeout"
    assert "secret" not in str(exc_info.value)


def _proposal_json(compact_input: ConversationCompactInputVNext) -> dict[str, JsonValue]:
    """构造可变 vNext proposal JSON。

    :param compact_input: vNext compact input。
    :returns: vNext proposal dict。
    :raises json.JSONDecodeError: fake proposal 不是合法 JSON 时抛出。
    :raises AssertionError: fake proposal 不是 JSON object 时抛出。
    """

    raw = fake_compaction_proposal_from_material_json(
        _compact_input_json(compact_input)
    )
    parsed: JsonValue = json.loads(raw)
    return dict(_required_mapping(parsed, field_name="proposal"))


def _compact_input_json(
    compact_input: ConversationCompactInputVNext,
) -> Mapping[str, JsonValue]:
    """返回 vNext compact input 的 JSON object 视图。

    :param compact_input: vNext compact input。
    :returns: compact input JSON object。
    :raises AssertionError: compact input 序列化结果不是 JSON object 时抛出。
    """

    return _required_mapping(compact_input.to_json(), field_name="compact_input")


def _fact_json() -> dict[str, JsonValue]:
    """构造测试用最小合法 fact proposal JSON。

    :returns: 最小合法 fact proposal JSON object。
    """

    return {
        "claim_text": "经营现金流同比增长",
        "evidence_labels": ["E1"],
        "source_labels": ["E1"],
    }


def _material_json_from_compactor_prompt(prompt: str) -> Mapping[str, JsonValue]:
    """从 compactor user prompt 提取 LLM-facing material JSON。

    :param prompt: compactor user prompt。
    :returns: material JSON object。
    :raises AssertionError: prompt 中 material JSON 不是 object 时抛出。
    :raises json.JSONDecodeError: prompt 中 material JSON 非法时抛出。
    """

    parsed: JsonValue = json.loads(_material_json_text_from_prompt(prompt))
    return _required_mapping(parsed, field_name="material_json")


def _material_json_text_from_prompt(prompt: str) -> str:
    """从 compactor user prompt 中读取 material JSON 文本。

    :param prompt: compactor user prompt。
    :returns: untrusted delimiter 中的 JSON 文本。
    :raises AssertionError: prompt 缺少 material delimiter 时抛出。
    """

    begin_index = prompt.find(_UNTRUSTED_COMPACTION_MATERIAL_BEGIN)
    end_index = prompt.find(_UNTRUSTED_COMPACTION_MATERIAL_END)
    assert begin_index >= 0
    assert end_index > begin_index
    json_start = begin_index + len(_UNTRUSTED_COMPACTION_MATERIAL_BEGIN)
    return prompt[json_start:end_index].strip()


def _required_mapping(value: JsonValue, *, field_name: str) -> Mapping[str, JsonValue]:
    """校验并返回 JSON object。

    :param value: 待校验 JSON value。
    :param field_name: 错误定位字段名。
    :returns: JSON object。
    :raises AssertionError: value 不是 JSON object 时抛出。
    """

    assert _is_json_mapping(value), field_name
    return value


def _required_list(value: JsonValue, *, field_name: str) -> list[JsonValue]:
    """校验并返回 JSON array。

    :param value: 待校验 JSON value。
    :param field_name: 错误定位字段名。
    :returns: JSON array。
    :raises AssertionError: value 不是 JSON array 时抛出。
    """

    assert _is_json_list(value), field_name
    return value


def _is_json_mapping(value: JsonValue) -> TypeGuard[Mapping[str, JsonValue]]:
    """判断 JSON value 是否为 JSON object。

    :param value: 待判断 JSON value。
    :returns: ``value`` 是 JSON object 时返回 ``True``，否则返回 ``False``。
    """

    return isinstance(value, Mapping)


def _is_json_list(value: JsonValue) -> TypeGuard[list[JsonValue]]:
    """判断 JSON value 是否为 JSON array。

    :param value: 待判断 JSON value。
    :returns: ``value`` 是 JSON array 时返回 ``True``，否则返回 ``False``。
    """

    return isinstance(value, list)


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


def _request_with_long_input_material() -> CompactionRequest:
    """构造包含长 current input 与长 evidence 的 compaction request。

    :returns: compaction request。
    """

    material_pack = build_initial_material_pack(
        current_input_ref="event-current-long",
        current_input_text="current " + ("input " * 300),
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-user-old",
                text="上一轮用户问题",
                kind=CompactMaterialBlockKind.USER_INPUT,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-long",
                accepted_evidence_id="evidence:accepted-long",
                tool_result_event_ref="event-tool-result-long",
                tool_call_event_ref="event-tool-call-long",
                readable_tool_name="fins.search",
                readable_query_text="cash flow",
                raw_result_text="evidence " + ("detail " * 700),
                readable_source_text="2025 年年报现金流量表",
                payload_refs=("payload:evidence-long",),
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
        recent_raw_turn_refs=("event-current-long",),
        older_raw_turn_refs=("event-user-old",),
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


def _final(
    content: str,
    *,
    request: AgentRunRequest,
    finish_reason: FinishReason,
    provider_request_id: str | None,
) -> EngineRunOutcomeFinalAnswer:
    """构造 final answer outcome。

    :param content: final answer 文本。
    :param request: 产出该 final 的同一次 Engine request。
    :param finish_reason: final answer finish reason。
    :param provider_request_id: provider 返回的 request id；不可用时为
        ``None``。
    :returns: EngineRunOutcomeFinalAnswer。
    :raises ValueError: request identity 或 provider id 配对非法时抛出。
    """

    request_identity = build_runner_request_identity(
        run_id=request.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        iteration_id=f"{request.run_id}-iteration-1",
        iteration_index=0,
        runner_call_index=1,
    )
    return EngineRunOutcomeFinalAnswer(
        session_id=request.session_id,
        run_id=request.run_id,
        content=content,
        filtered=False,
        degraded=False,
        finish_reason=finish_reason,
        response_identity=SuccessfulRunnerResponseIdentity(
            effective_provider=request.runner_spec.provider,
            effective_model=request.runner_spec.model,
            runner_request_identity=request_identity,
            provider_request_id_availability=(
                ProviderRequestIdAvailability.UNAVAILABLE
                if provider_request_id is None
                else ProviderRequestIdAvailability.PRESENT
            ),
            provider_request_id=provider_request_id,
        ),
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
