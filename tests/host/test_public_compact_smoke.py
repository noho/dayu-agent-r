"""P10.5 Slice 5 public real-compactor smoke。"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.engine_events import runner_role_sequence_digest
from dayu.engine.contracts.agent_policy import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage, AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    CompactorRunnerBaseline,
    HostEventKind,
    HostToolingOptions,
    LocalEngineWorkerFactory,
    OpenHostOptions,
    open_host,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host.context_policy import context_budget_policy_from_threshold_tokens
from dayu.host.durable.schema import RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION
from dayu.runtime.config_loader import ConfigLoader
from dayu.runtime.scene_prepare import (
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from tests.host.public_smoke_support import (
    PROVIDER_CASES,
    FinalAnswerWorkerFactory,
    ToolCallingWorkerFactory,
    api_key_or_skip,
    assert_at_most_one_system_message,
    deterministic_runner_spec,
    ensure_request,
    followup_request,
    next_terminal_for_run,
    open_host_options,
    runner_spec_for_case,
    skip_if_provider_exception,
    skip_if_provider_terminal_failed,
)
from tests.host.fake_compaction import fake_compaction_proposal_from_material_json

_SOFT_CONTEXT_WINDOW_SIZE = 2400
_SOFT_HARD_THRESHOLD_TOKENS = 300
_SOFT_THRESHOLD_TOKENS = 70
_SOFT_THRESHOLD_PROMPT_REPEAT_COUNT = 7
_SOFT_THRESHOLD_PROMPT_SENTENCE = "请保留标记 DAYU_COMPACT_OK，并继续等待下一步。"
_COMPACTOR_PROVIDER_MAX_RETRIES = 1
_COMPACTOR_MAX_ATTEMPTS_PER_OPERATION = 2
_LLM_FACING_OUTPUT_CONTRACT_IDENTIFIER = "conversation_compact_output_v1"
_INTERNAL_COMPACT_OUTPUT_TYPE_NAME = "ConversationCompactOutputVNext"
_INTERNAL_COMPACT_INPUT_TYPE_NAME = "ConversationCompactInputVNext"
_COMPACT_ARTIFACT_KIND_FIELD = "artifact_kind"
_COMPACT_ARTIFACT_KIND = "context_compaction"
_ACCEPTED_CANDIDATE_FIELD = "accepted_candidate"
_CANDIDATE_ID_FIELD = "candidate_id"
_INPUT_SNAPSHOT_REFS_FIELD = "input_snapshot_refs"
_CURRENT_USER_INPUT_REF_FIELD = "current_user_input_ref"
_UNTRUSTED_COMPACTION_MATERIAL_BEGIN = "UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN"
_UNTRUSTED_COMPACTION_MATERIAL_END = "UNTRUSTED_COMPACTION_MATERIAL_JSON_END"
_FAKE_COMPACT_CONTEXT_WINDOW_SIZE = 12000
_FAKE_COMPACT_SOFT_THRESHOLD_TOKENS = 90
_FAKE_COMPACT_HARD_THRESHOLD_TOKENS = 9000
_FAKE_COMPACTOR_MAX_PROMPT_CHARS = 9000
_FAKE_PUBLIC_MEMORY_MAX_CHARS = 16000
_FAKE_COMPACT_PAYLOAD_INLINE_THRESHOLD_BYTES = 65536
_LONG_CHAPTER_MARKER = "DAYU_LONG_CHAPTER_RAW_EVIDENCE_OPERATING_MARGIN_42"
_SECOND_FACTOR_MARKER = "第二个因素=库存周转率"
_DUPLICATE_PROMPT_SENTENCE = "DAYU_DUPLICATE_PROMPT_COMPACT_SEGMENT。"
_RUN_REAL_COMPACTOR_SMOKE_ENV = "DAYU_RUN_REAL_COMPACTOR_SMOKE"
_PACKAGE_CONFIG_ROOT = (
    pathlib.Path(__file__).resolve().parents[2] / "dayu" / "config"
)
_COMPACTOR_PROFILE_ID = "standard-256k"
_FORBIDDEN_COMPACTOR_PROMPT_TERMS = (
    "Host-owned context compaction",
    _INTERNAL_COMPACT_OUTPUT_TYPE_NAME,
    _INTERNAL_COMPACT_INPUT_TYPE_NAME,
    "vNext",
    "migration",
    "candidate_id",
    "episode_summary_candidate",
    "pinned_state_patch_candidate",
    "minimum_preserve_item_candidates",
    "preservation_evidence",
    "stable_input",
    "history_input",
    "evidence_input",
    "EventLog",
    "payload ref",
    "payload refs",
    "payload_refs",
    "digest",
    "cursor",
    "policy",
)
_FORBIDDEN_COMPACTOR_MATERIAL_TERMS = (
    _INTERNAL_COMPACT_OUTPUT_TYPE_NAME,
    _INTERNAL_COMPACT_INPUT_TYPE_NAME,
    "ConversationCompactOutput",
    "ConversationCompactInput",
    "EventLog",
    "payload ref",
    "payload_refs",
    "tool_call_id=",
    "vNext",
)
_COMPACTOR_MATERIAL_TOP_LEVEL_KEYS = (
    "schema_version",
    "previous_compacted_view",
    "trace_material",
    "evidence_material",
    "answer_material",
    "current_input_anchor",
    "instruction",
)
_COMPACTOR_MATERIAL_LIST_SECTION_KEYS = (
    "trace_material",
    "evidence_material",
    "answer_material",
)
_STALE_COMPACTOR_MATERIAL_SECTION_KEYS = (
    "stable_input",
    "history_input",
    "evidence_input",
)


def test_default_compactor_prompt_is_llm_facing_and_self_contained() -> None:
    """默认 compactor prompt 不暴露内部实现术语，并自足说明输入输出。

    :returns: ``None``。
    :raises AssertionError: prompt 文本缺少必要语义或包含内部术语时抛出。
    """

    system_prompt, user_prompt_template, _ = _compactor_baseline_inputs()
    prompt_text = f"{system_prompt}\n{user_prompt_template}"

    for forbidden_term in _FORBIDDEN_COMPACTOR_PROMPT_TERMS:
        assert forbidden_term not in prompt_text

    assert "<<compaction_request>>" in user_prompt_template
    assert "输入 JSON 说明" in user_prompt_template
    assert "输出 JSON 字段" in user_prompt_template
    assert "输出 JSON 最小示例" in user_prompt_template
    assert "label 是本次请求内的引用标签" in user_prompt_template
    assert "label 本身不是业务事实、财报事实或结论" in system_prompt
    assert "唯一允许值为 `conversation_compact_output_v1`" in user_prompt_template
    assert (
        "必须为每个确实需要保留的 evidence label 产出至少一个 "
        "evidence_backed_facts 条目；不得合成无证据事实。"
        in user_prompt_template
    )
    assert "应为每个确实需要保留的 evidence label" not in user_prompt_template
    for required_field in (
        "schema_version",
        "session_summary",
        "evidence_backed_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity_items",
        "diagnostics",
    ):
        assert required_field in user_prompt_template


def test_compactor_material_assertion_helpers_accept_valid_material() -> None:
    """Public compact material assertion helpers 接受有效 material / proposal。

    :returns: ``None``。
    :raises AssertionError: helper 拒绝有效 material 或 proposal 时抛出。
    """

    material_json = _valid_compactor_material_json()
    _assert_compactor_material_instruction_contract(material_json)
    _assert_material_evidence_contains_marker(
        material_json, marker=_LONG_CHAPTER_MARKER
    )
    proposal = _required_mapping(
        cast(
            JsonValue,
            json.loads(fake_compaction_proposal_from_material_json(material_json)),
        ),
        field_name="fake proposal",
    )
    _assert_label_only_fake_proposal(proposal, marker=_LONG_CHAPTER_MARKER)


def test_compactor_material_section_shape_rejects_stale_legacy_key() -> None:
    """Material section helper 拒绝 stale legacy section key。

    :returns: ``None``。
    :raises AssertionError: helper 未拒绝 stale key 时抛出。
    """

    material_json = _valid_compactor_material_json()
    stale_value: list[JsonValue] = []
    material_json["stable_input"] = stale_value

    with pytest.raises(AssertionError, match="material pack / labels boundary"):
        _assert_compactor_material_section_shape(material_json)


def test_compactor_material_forbidden_terms_rejects_internal_text() -> None:
    """Forbidden-term helper 拒绝 LLM-facing material 内部术语泄漏。

    :returns: ``None``。
    :raises AssertionError: helper 未拒绝内部术语时抛出。
    """

    material_json = _valid_compactor_material_json()
    anchor = dict(
        _required_mapping(
            material_json["current_input_anchor"], field_name="current_input_anchor"
        )
    )
    anchor["text"] = "EventLog should never be LLM-facing material."
    material_json["current_input_anchor"] = anchor

    with pytest.raises(AssertionError, match="LLM-facing material boundary"):
        _assert_no_forbidden_compactor_material_terms(material_json)


def test_compactor_material_evidence_marker_rejects_missing_marker() -> None:
    """Evidence marker helper 拒绝缺少期望 marker 的 material。

    :returns: ``None``。
    :raises AssertionError: helper 未拒绝缺失 marker 时抛出。
    """

    material_json = _valid_compactor_material_json(include_marker=False)

    with pytest.raises(AssertionError, match="evidence material marker boundary"):
        _assert_material_evidence_contains_marker(
            material_json, marker=_LONG_CHAPTER_MARKER
        )


def test_label_only_fake_proposal_rejects_canonical_ref_leakage() -> None:
    """Fake proposal helper 拒绝 canonical ref 泄漏。

    :returns: ``None``。
    :raises AssertionError: helper 未拒绝 canonical ref 泄漏时抛出。
    """

    proposal: dict[str, JsonValue] = {
        "evidence_backed_facts": [
            {
                "evidence_labels": ["E1"],
                "claim_text": (
                    f"{_LONG_CHAPTER_MARKER} payload:event-tool-result-accepted"
                ),
            }
        ]
    }

    with pytest.raises(AssertionError, match="compactor proposal boundary"):
        _assert_label_only_fake_proposal(proposal, marker=_LONG_CHAPTER_MARKER)


@pytest.mark.asyncio
async def test_no_compaction_recent_raw_turns_continuity(
    tmp_path: pathlib.Path,
) -> None:
    """未触发 compact 时，public follow-up 仍保留近期 raw turn 连续性。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 第二轮 Engine request 缺少第一轮用户输入时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with open_host(
        open_host_options(
            tmp_path,
            runner_spec=deterministic_runner_spec("p12-6-no-compact"),
            worker_factory=factory,
            allow_tool_calls=False,
        )
    ) as host:
        session = await host.ensure_session(ensure_request("p12-6-no-compact"))
        watcher = host.watch_session_events(session.session_id)
        first = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-no-compact-first",
                "第一轮原始问题：请记住营收增长来自价格因素。",
            ),
        )
        await next_terminal_for_run(watcher, first.accepted_run_id)
        second = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-no-compact-second",
                "第二轮追问：刚才说的增长来源是什么？",
            ),
        )
        second_terminal = await next_terminal_for_run(
            watcher, second.accepted_run_id
        )

    assert second_terminal.kind is HostEventKind.SUCCEEDED
    second_request = factory.requests[1]
    for index, request in enumerate(factory.requests):
        assert_at_most_one_system_message(
            request.messages, label=f"no compact request {index}"
        )
    joined = _joined_message_content(second_request.messages)
    assert "第一轮原始问题：请记住营收增长来自价格因素。" in joined
    assert "Session Summary Memory:" not in joined


@pytest.mark.asyncio
async def test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """public opener compact 后能从 raw accepted tool evidence 生成 stable fact。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: public material 缺 evidence_material 或后续 request 未复用 fact 时抛出。
    """

    fake_compactor = FakeCompactorRunAgent()
    monkeypatch.setattr(
        "dayu.host.llm_compaction._run_agent_request",
        fake_compactor,
    )
    factory = ToolCallingWorkerFactory()
    async with open_host(
        _fake_compact_open_options(
            tmp_path,
            worker_factory=factory,
            allow_tool_calls=True,
            tooling_options=_long_chapter_tooling_options(),
            policy_ref="p12-6-public-tool-evidence",
        )
    ) as host:
        session = await host.ensure_session(ensure_request("p12-6-tool-evidence"))
        watcher = host.watch_session_events(session.session_id)
        first = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-tool-evidence-first",
                "先调用 mock 财报工具读取长章节证据。",
            ),
        )
        first_terminal = await next_terminal_for_run(watcher, first.accepted_run_id)
        second = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-tool-evidence-compact",
                _soft_threshold_prompt(),
            ),
        )
        second_terminal = await next_terminal_for_run(watcher, second.accepted_run_id)
        third = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-tool-evidence-reuse",
                "复用刚才工具证据里的经营利润率事实。",
            ),
        )
        third_terminal = await next_terminal_for_run(watcher, third.accepted_run_id)

    assert first_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.kind is HostEventKind.SUCCEEDED
    assert third_terminal.kind is HostEventKind.SUCCEEDED
    assert len(fake_compactor.material_jsons) >= 1
    material_json = _first_material_json_with_evidence(fake_compactor.material_jsons)
    _assert_compactor_material_instruction_contract(material_json)
    _assert_material_evidence_contains_marker(
        material_json, marker=_LONG_CHAPTER_MARKER
    )
    material_text = json.dumps(material_json, ensure_ascii=False, sort_keys=True)
    assert "result_preview" not in material_text
    assert "payload:" not in material_text
    assert "event-tool-result" not in material_text
    assert len(factory.requests) >= 3
    for index, request in enumerate(factory.requests):
        assert_at_most_one_system_message(
            request.messages, label=f"tool evidence request {index}"
        )
    joined = _joined_message_content(factory.requests[-1].messages)
    assert "## Verified Evidence and Facts" in joined
    assert _LONG_CHAPTER_MARKER in joined

    # helper-level 补充：fake proposal 只使用 prompt-local E label，不读取 canonical refs。
    proposal = _required_mapping(
        cast(
            JsonValue,
            json.loads(
                fake_compaction_proposal_from_material_json(
                    _llm_material_with_long_tool_evidence()
                )
            ),
        ),
        field_name="fake proposal",
    )
    _assert_label_only_fake_proposal(proposal, marker=_LONG_CHAPTER_MARKER)


@pytest.mark.asyncio
async def test_long_user_input_second_factor_survives_reference_continuity(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """长输入 compact 后，下一轮仍可通过 vNext continuity 看到第二个因素。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 后续 public RunInput 缺少第二因素文本时抛出。
    """

    fake_compactor = FakeCompactorRunAgent()
    monkeypatch.setattr(
        "dayu.host.llm_compaction._run_agent_request",
        fake_compactor,
    )
    factory = FinalAnswerWorkerFactory()
    async with open_host(
        _fake_compact_open_options(
            tmp_path,
            worker_factory=factory,
            allow_tool_calls=False,
            tooling_options=None,
            policy_ref="p12-6-public-minimum-preserve",
        )
    ) as host:
        session = await host.ensure_session(ensure_request("p12-6-min-preserve"))
        watcher = host.watch_session_events(session.session_id)
        first = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-min-preserve-first",
                _long_user_input_with_second_factor(),
            ),
        )
        await next_terminal_for_run(watcher, first.accepted_run_id)
        second = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-min-preserve-second",
                "刚才长输入中的第二个因素是什么？",
            ),
        )
        terminal = await next_terminal_for_run(watcher, second.accepted_run_id)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert len(fake_compactor.prompt_lengths) >= 1
    for index, request in enumerate(factory.requests):
        assert_at_most_one_system_message(
            request.messages, label=f"minimum preserve request {index}"
        )
    joined = _joined_message_content(factory.requests[1].messages)
    assert _SECOND_FACTOR_MARKER in joined


@pytest.mark.asyncio
async def test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """长会话多次 compact 后，compactor prompt 与后续 memory 输入保持有界。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: prompt 或后续 RunInput 明显随历史无界增长时抛出。
    """

    fake_compactor = FakeCompactorRunAgent()
    monkeypatch.setattr(
        "dayu.host.llm_compaction._run_agent_request",
        fake_compactor,
    )
    factory = FinalAnswerWorkerFactory()
    async with open_host(
        _fake_compact_open_options(
            tmp_path,
            worker_factory=factory,
            allow_tool_calls=False,
            tooling_options=None,
            policy_ref="p12-6-public-multi-compact",
        )
    ) as host:
        session = await host.ensure_session(ensure_request("p12-6-multi-compact"))
        watcher = host.watch_session_events(session.session_id)
        for index in range(4):
            followup = await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    f"p12-6-multi-compact-{index}",
                    f"{_soft_threshold_prompt()} multi-compact-marker-{index}",
                ),
            )
            await next_terminal_for_run(watcher, followup.accepted_run_id)
        final = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-multi-compact-final",
                "检查多次 compact 后的有界 memory。",
            ),
        )
        terminal = await next_terminal_for_run(watcher, final.accepted_run_id)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert len(fake_compactor.prompt_lengths) >= 2
    for index, request in enumerate(factory.requests):
        assert_at_most_one_system_message(
            request.messages, label=f"multi compact request {index}"
        )
    assert max(fake_compactor.prompt_lengths) <= _FAKE_COMPACTOR_MAX_PROMPT_CHARS
    assert len(_joined_message_content(factory.requests[-1].messages)) <= (
        _FAKE_PUBLIC_MEMORY_MAX_CHARS
    )


@pytest.mark.asyncio
async def test_proactive_compact_long_current_input_reaches_compactor_without_lossy_anchor(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超长 current input 完整进入 compactor current_input_anchor。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: Run 失败、未调用 compactor 或 current input 被截断。
    """

    long_prompt = _DUPLICATE_PROMPT_SENTENCE * 500
    fake_compactor = FakeCompactorRunAgent()
    monkeypatch.setattr(
        "dayu.host.llm_compaction._run_agent_request",
        fake_compactor,
    )
    factory = FinalAnswerWorkerFactory()
    async with open_host(
        _fake_compact_open_options(
            tmp_path,
            worker_factory=factory,
            allow_tool_calls=False,
            tooling_options=None,
            policy_ref="p12-6-public-duplicate-prompt",
        )
    ) as host:
        session = await host.ensure_session(ensure_request("p12-6-duplicate"))
        watcher = host.watch_session_events(session.session_id)
        followup = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "p12-6-duplicate-first",
                long_prompt,
            ),
        )
        terminal = await next_terminal_for_run(watcher, followup.accepted_run_id)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert len(fake_compactor.prompt_lengths) == 1
    assert len(fake_compactor.material_jsons) == 1
    material_json = fake_compactor.material_jsons[0]
    current_anchor = _required_mapping(
        material_json["current_input_anchor"],
        field_name="current_input_anchor",
    )
    assert current_anchor["anchor_label"] == "C1"
    assert current_anchor["text"] == long_prompt
    assert material_json["previous_compacted_view"] is None
    assert material_json["trace_material"] == []
    assert material_json["evidence_material"] == []
    assert material_json["answer_material"] == []
    material_text = json.dumps(material_json, ensure_ascii=False, sort_keys=True)
    assert "truncated" not in material_text
    assert "preview" not in material_text
    assert "summary" not in material_text
    assert len(_compact_artifact_files(tmp_path / "compact-artifacts")) >= 1


@pytest.mark.asyncio
async def test_real_compactor_public_opener_compacts_and_preserves_continuity(
    tmp_path: pathlib.Path,
) -> None:
    """public opener 触发真实 compactor，并在后续 run 保持连续性。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: compact 未触发或 terminal 不成功时抛出。
    """

    if os.environ.get(_RUN_REAL_COMPACTOR_SMOKE_ENV) != "1":
        pytest.skip(
            f"set {_RUN_REAL_COMPACTOR_SMOKE_ENV}=1 to run optional real compactor smoke"
        )
    case = PROVIDER_CASES[1]
    api_key = api_key_or_skip(case)
    runner_spec = runner_spec_for_case(case, api_key)
    compactor_runner_spec = replace(
        runner_spec,
        provider_request=None,
        max_retries=_COMPACTOR_PROVIDER_MAX_RETRIES,
    )
    runner_options = RunnerCallOptions(
        temperature=0.0,
        max_tokens=512,
        top_p=None,
        stream=True,
    )
    compactor_runner_options = _compactor_runner_options(case.model)
    compact_artifact_root = tmp_path / "compact-artifacts"
    artifact_files_before = _compact_artifact_files(compact_artifact_root)
    worker_factory = FinalAnswerWorkerFactory()
    base_options = open_host_options(
        tmp_path,
        runner_spec=compactor_runner_spec,
        worker_factory=worker_factory,
        allow_tool_calls=False,
        max_tokens=512,
    )
    base_options = replace(
        base_options,
        ordinary_run_baseline=replace(
            base_options.ordinary_run_baseline,
            runner_options=runner_options,
        ),
    )
    (
        compactor_system_prompt,
        compactor_user_prompt_template,
        compactor_agent_policy,
    ) = _compactor_baseline_inputs()
    options = replace(
        base_options,
        context_budget_policy=context_budget_policy_from_threshold_tokens(
            context_window_size=_SOFT_CONTEXT_WINDOW_SIZE,
            soft_threshold_tokens=_SOFT_THRESHOLD_TOKENS,
            hard_threshold_tokens=_SOFT_HARD_THRESHOLD_TOKENS,
            max_compaction_attempts_per_operation=(
                _COMPACTOR_MAX_ATTEMPTS_PER_OPERATION
            ),
            policy_ref="slice5-real-compact-policy",
        ),
        compactor_runner_baseline=CompactorRunnerBaseline(
            compactor_runner_spec=compactor_runner_spec,
            compactor_runner_options=compactor_runner_options,
            compactor_agent_policy=compactor_agent_policy,
            compactor_system_prompt=compactor_system_prompt,
            compactor_user_prompt_template=compactor_user_prompt_template,
            compact_artifact_root=compact_artifact_root,
            compact_artifact_create_parent_dirs=True,
        ),
    )

    try:
        async with open_host(options) as host:
            session = await host.ensure_session(ensure_request("real-compact"))
            watcher = host.watch_session_events(session.session_id)
            compacted = await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "compact-first",
                    _soft_threshold_prompt(),
                ),
            )
            first_terminal = await next_terminal_for_run(
                watcher, compacted.accepted_run_id
            )
            skip_if_provider_terminal_failed(case, first_terminal)
            followup = await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "compact-second",
                    "基于已经压缩的上下文，只输出 DAYU_COMPACT_OK。",
                ),
            )
            second_terminal = await next_terminal_for_run(
                watcher, followup.accepted_run_id
            )
    except RuntimeError as exc:
        skip_if_provider_exception(case, exc)
        raise

    skip_if_provider_terminal_failed(case, second_terminal)
    assert first_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.kind is HostEventKind.SUCCEEDED
    assert first_terminal.session_id == session.session_id
    assert second_terminal.session_id == session.session_id
    assert first_terminal.run_id == compacted.accepted_run_id
    assert second_terminal.run_id == followup.accepted_run_id
    assert second_terminal.final_answer is not None
    assert second_terminal.final_answer.content.strip() != ""
    artifact_files_after = _compact_artifact_files(compact_artifact_root)
    new_artifacts = tuple(
        path for path in artifact_files_after if path not in artifact_files_before
    )
    assert len(new_artifacts) > 0
    artifact = _compact_artifact_for_run(new_artifacts, compacted.accepted_run_id)
    input_snapshot = _required_mapping(
        artifact[_INPUT_SNAPSHOT_REFS_FIELD],
        field_name=_INPUT_SNAPSHOT_REFS_FIELD,
    )
    current_user_input_ref = input_snapshot[_CURRENT_USER_INPUT_REF_FIELD]
    assert isinstance(current_user_input_ref, str)
    assert current_user_input_ref.strip() != ""


@dataclass(slots=True)
class FakeCompactorRunAgent:
    """记录 compactor request，并返回 label-only deterministic proposal。

    :param prompt_lengths: 每次 compactor user prompt 字符数。
    :param prompts: 每次 compactor user prompt 原文。
    :param material_jsons: 每次 compactor request 的 LLM-facing material JSON。
    """

    prompt_lengths: list[int] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    material_jsons: list[Mapping[str, JsonValue]] = field(default_factory=list)

    async def __call__(
        self, request: AgentRunRequest, *, timeout_seconds: float
    ) -> AgentRunResult:
        """模拟 ``LLMContextCompactor`` 的 Engine runner 返回。

        :param request: compactor 构造的 Engine request。
        :param timeout_seconds: 单次 compactor runner timeout；fake 不使用。
        :returns: strict JSON final answer outcome。
        :raises AssertionError: request 不是单 user material JSON 时抛出。
        """

        del timeout_seconds
        assert_at_most_one_system_message(
            request.messages, label="fake compactor request"
        )
        material_json = _material_json_from_compactor_request(request)
        _assert_compactor_material_instruction_contract(material_json)
        user_prompt = _compactor_user_prompt(request)
        self.material_jsons.append(material_json)
        self.prompts.append(user_prompt)
        self.prompt_lengths.append(len(user_prompt))
        return EngineRunOutcomeFinalAnswer(
            session_id=request.session_id,
            run_id=request.run_id,
            content=fake_compaction_proposal_from_material_json(material_json),
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        )


def _fake_compact_open_options(
    tmp_path: pathlib.Path,
    *,
    worker_factory: LocalEngineWorkerFactory,
    allow_tool_calls: bool,
    tooling_options: HostToolingOptions | None,
    policy_ref: str,
    soft_threshold_tokens: int = _FAKE_COMPACT_SOFT_THRESHOLD_TOKENS,
) -> OpenHostOptions:
    """构造带 deterministic compactor baseline 的 public ``OpenHostOptions``。

    :param tmp_path: pytest 临时目录。
    :param worker_factory: ordinary Run worker factory。
    :param allow_tool_calls: ordinary AgentPolicy 是否允许工具。
    :param tooling_options: 可选工具装配。
    :param policy_ref: context policy ref。
    :param soft_threshold_tokens: proactive compact soft threshold。
    :returns: public OpenHostOptions。
    :raises ValueError: typed options 字段非法时由底层抛出。
    """

    base_options = open_host_options(
        tmp_path,
        runner_spec=deterministic_runner_spec("p12-6-public-compact"),
        worker_factory=worker_factory,
        allow_tool_calls=allow_tool_calls,
        tooling_options=tooling_options,
        max_tokens=128,
    )
    return replace(
        base_options,
        payload_inline_threshold_bytes=_FAKE_COMPACT_PAYLOAD_INLINE_THRESHOLD_BYTES,
        context_budget_policy=context_budget_policy_from_threshold_tokens(
            context_window_size=_FAKE_COMPACT_CONTEXT_WINDOW_SIZE,
            soft_threshold_tokens=soft_threshold_tokens,
            hard_threshold_tokens=_FAKE_COMPACT_HARD_THRESHOLD_TOKENS,
            policy_ref=policy_ref,
        ),
        compactor_runner_baseline=_fake_compactor_baseline(tmp_path),
    )


def _fake_compactor_baseline(tmp_path: pathlib.Path) -> CompactorRunnerBaseline:
    """构造不会访问真实 provider 的 compactor baseline。

    :param tmp_path: pytest 临时目录。
    :returns: CompactorRunnerBaseline。
    :raises ValueError: typed baseline 字段非法时由底层抛出。
    """

    return CompactorRunnerBaseline(
        compactor_runner_spec=deterministic_runner_spec("p12-6-fake-compactor"),
        compactor_runner_options=RunnerCallOptions(
            temperature=0.0,
            max_tokens=1024,
            top_p=None,
            stream=False,
        ),
        compactor_agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
        ),
        compactor_system_prompt="Deterministic P12.6 fake compactor.",
        compactor_user_prompt_template="<<compaction_request>>",
        compact_artifact_root=tmp_path / "compact-artifacts",
        compact_artifact_create_parent_dirs=True,
    )


def _material_json_from_compactor_request(
    request: AgentRunRequest,
) -> Mapping[str, JsonValue]:
    """从 compactor Engine request 中读取 LLM-facing material JSON。

    :param request: compactor Engine request。
    :returns: material JSON object。
    :raises AssertionError: compactor request message 形状非法时抛出。
    :raises json.JSONDecodeError: user prompt 不是 JSON 时抛出。
    """

    prompt = _compactor_user_prompt(request)
    parsed = cast(JsonValue, json.loads(_material_json_text_from_prompt(prompt)))
    assert isinstance(parsed, Mapping)
    return cast(Mapping[str, JsonValue], parsed)


def _assert_compactor_material_instruction_contract(
    material_json: Mapping[str, JsonValue],
) -> None:
    """校验 public compactor runtime material 的 instruction contract。

    :param material_json: compactor request 中投影给 LLM 的 material JSON。
    :returns: ``None``。
    :raises AssertionError: material shape 或 instruction contract 非法时抛出。
    """

    _assert_compactor_material_section_shape(material_json)
    _assert_no_forbidden_compactor_material_terms(material_json)
    instruction_value = material_json["instruction"]
    assert isinstance(instruction_value, Mapping)
    instruction = cast(Mapping[str, JsonValue], instruction_value)
    assert (
        instruction["output_schema_name"]
        == _LLM_FACING_OUTPUT_CONTRACT_IDENTIFIER
    )


def _assert_compactor_material_section_shape(
    material_json: Mapping[str, JsonValue],
) -> None:
    """校验 public compactor material 顶层 section shape。

    :param material_json: compactor request 中投影给 LLM 的 material JSON。
    :returns: ``None``。
    :raises AssertionError: 顶层 section key 或 section 类型不符合预期时抛出。
    """

    for key in _COMPACTOR_MATERIAL_TOP_LEVEL_KEYS:
        assert (
            key in material_json
        ), f"material pack / labels boundary missing top-level key: {key}"
    for key in _STALE_COMPACTOR_MATERIAL_SECTION_KEYS:
        assert (
            key not in material_json
        ), f"material pack / labels boundary leaked stale section key: {key}"
    for key in _COMPACTOR_MATERIAL_LIST_SECTION_KEYS:
        section_value = material_json[key]
        assert isinstance(
            section_value, list
        ), f"material pack / labels boundary expected list section: {key}"
    assert isinstance(
        material_json["current_input_anchor"], Mapping
    ), "material pack / labels boundary expected current_input_anchor object"
    assert isinstance(
        material_json["instruction"], Mapping
    ), "material pack / labels boundary expected instruction object"


def _assert_no_forbidden_compactor_material_terms(
    material_json: Mapping[str, JsonValue],
) -> None:
    """校验 LLM-facing material 未泄漏内部术语。

    :param material_json: compactor request 中投影给 LLM 的 material JSON。
    :returns: ``None``。
    :raises AssertionError: material 文本包含内部术语时抛出。
    """

    material_text = json.dumps(material_json, ensure_ascii=False, sort_keys=True)
    for forbidden_term in _FORBIDDEN_COMPACTOR_MATERIAL_TERMS:
        assert (
            forbidden_term not in material_text
        ), f"LLM-facing material boundary leaked forbidden term: {forbidden_term}"


def _assert_material_evidence_contains_marker(
    material_json: Mapping[str, JsonValue], *, marker: str
) -> None:
    """校验 public compactor material 的 evidence section 保留 marker。

    :param material_json: compactor request 中投影给 LLM 的 material JSON。
    :param marker: 期望出现在 evidence material 中的 marker。
    :returns: ``None``。
    :raises AssertionError: evidence material 缺失 marker 时抛出。
    """

    evidence_material = material_json["evidence_material"]
    assert isinstance(
        evidence_material, list
    ), "evidence material marker boundary expected evidence_material list"
    assert len(evidence_material) >= 1
    evidence_text = json.dumps(evidence_material, ensure_ascii=False, sort_keys=True)
    assert (
        marker in evidence_text
    ), f"evidence material marker boundary missing marker: {marker}"


def _assert_label_only_fake_proposal(
    proposal: Mapping[str, JsonValue], *, marker: str
) -> None:
    """校验 fake compactor proposal 只使用 prompt-local label。

    :param proposal: fake compactor proposal JSON object。
    :param marker: 期望保留在 claim text 中的 marker。
    :returns: ``None``。
    :raises AssertionError: proposal 缺少 fact、marker 或泄漏 canonical ref 时抛出。
    """

    fact_candidates = proposal["evidence_backed_facts"]
    assert isinstance(fact_candidates, list)
    assert len(fact_candidates) == 1
    fact = _required_mapping(fact_candidates[0], field_name="fact")
    assert fact["evidence_labels"] == [
        "E1"
    ], "compactor proposal boundary must use prompt-local E label"
    claim_text = fact["claim_text"]
    assert isinstance(claim_text, str)
    assert marker in claim_text, "compactor proposal boundary lost evidence marker"
    proposal_text = json.dumps(proposal, ensure_ascii=False, sort_keys=True)
    assert (
        "result_preview" not in proposal_text
    ), "compactor proposal boundary leaked result_preview"
    assert (
        "event-tool-result-accepted" not in proposal_text
    ), "compactor proposal boundary leaked canonical event ref"
    assert (
        "payload:" not in proposal_text
    ), "compactor proposal boundary leaked payload ref"


def _assert_runner_call_manifest_messages(
    manifest: Mapping[str, JsonValue],
    *,
    expected_roles: tuple[AgentMessageRole, ...],
) -> None:
    """校验 runner-call manifest 的 message_count、dump item 与 role digest 同源。

    :param manifest: runner-call input assembly manifest JSON。
    :param expected_roles: 期望的 message role 序列。
    :returns: ``None``。
    :raises AssertionError: manifest 数量、条目或 digest 不一致时抛出。
    """

    message_count = manifest["message_count"]
    assert isinstance(message_count, int)
    assert message_count == len(expected_roles)
    message_entries_value = manifest["message_entries"]
    assert isinstance(message_entries_value, list)
    assert len(message_entries_value) == message_count
    observed_roles: list[str] = []
    for index, entry_value in enumerate(message_entries_value):
        entry = _required_mapping(entry_value, field_name=f"message_entries[{index}]")
        assert entry["index"] == index
        role = entry["role"]
        assert isinstance(role, str)
        observed_roles.append(role)
    expected_role_values = tuple(role.value for role in expected_roles)
    assert tuple(observed_roles) == expected_role_values
    assert manifest["role_sequence_digest"] == runner_role_sequence_digest(
        expected_role_values
    )


def _material_json_text_from_prompt(prompt: str) -> str:
    """从 fake compactor prompt 中提取 material JSON 文本。

    :param prompt: compactor user prompt。
    :returns: untrusted delimiter 中间的 JSON 文本。
    :raises AssertionError: prompt 缺少 material delimiter 时抛出。
    """

    begin_index = prompt.find(_UNTRUSTED_COMPACTION_MATERIAL_BEGIN)
    end_index = prompt.find(_UNTRUSTED_COMPACTION_MATERIAL_END)
    assert begin_index >= 0
    assert end_index > begin_index
    json_start = begin_index + len(_UNTRUSTED_COMPACTION_MATERIAL_BEGIN)
    return prompt[json_start:end_index].strip()


def _first_material_json_with_evidence(
    values: list[Mapping[str, JsonValue]],
) -> Mapping[str, JsonValue]:
    """返回首个包含 evidence_material 的 compactor material JSON。

    :param values: fake compactor 记录的 material JSON 列表。
    :returns: 首个包含 evidence_material 项的 material JSON。
    :raises AssertionError: 所有 public compactor material 都缺 evidence_material 时抛出。
    """

    for value in values:
        evidence_material = value["evidence_material"]
        assert isinstance(evidence_material, list)
        if len(evidence_material) > 0:
            return value
    raise AssertionError("public compactor material evidence_material is empty")


def _compactor_user_prompt(request: AgentRunRequest) -> str:
    """读取 compactor user prompt。

    :param request: compactor Engine request。
    :returns: user prompt 文本。
    :raises AssertionError: request 不含单个 user material prompt 时抛出。
    """

    user_messages = tuple(
        message for message in request.messages if isinstance(message, UserMessage)
    )
    assert len(user_messages) == 1
    return user_messages[0].content


def _valid_compactor_material_json(
    *, include_marker: bool = True
) -> dict[str, JsonValue]:
    """构造 helper 自测用有效 public compactor material JSON。

    :param include_marker: 是否在 evidence material 中包含长章节 marker。
    :returns: public compactor material JSON。
    """

    result_text = (
        _long_chapter_tool_result()
        if include_marker
        else "accepted raw tool evidence without marker"
    )
    evidence_item: dict[str, JsonValue] = {
        "label": "E1",
        "kind": "accepted_tool_evidence",
        "tool_name": "lookup_mock_fact",
        "query_text": "读取长章节工具证据",
        "result_text": result_text,
        "source_text": "accepted raw tool evidence",
    }
    current_anchor: dict[str, JsonValue] = {
        "label": "C1",
        "kind": "current_input_anchor",
        "text": "复用 raw evidence fact。",
        "truncated": False,
    }
    instruction: dict[str, JsonValue] = {
        "output_schema_name": _LLM_FACING_OUTPUT_CONTRACT_IDENTIFIER,
        "compact_goal": "保留可复用证据。",
    }
    return {
        "schema_version": "conversation_compact_input_v1",
        "previous_compacted_view": None,
        "trace_material": [],
        "evidence_material": [evidence_item],
        "answer_material": [],
        "current_input_anchor": current_anchor,
        "instruction": instruction,
    }


def _llm_material_with_long_tool_evidence() -> Mapping[str, JsonValue]:
    """构造只含 prompt-local label 的 LLM-facing raw evidence material。

    :returns: LLM-facing material JSON。
    """

    return _valid_compactor_material_json()


class _LongChapterMockTool:
    """返回长章节 raw evidence 的 mock business tool。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 mock 工具并返回长章节结果。

        :param call: 工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 成功工具 outcome。
        """

        del call, context
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "chapter": _long_chapter_tool_result(),
                },
                meta=None,
            )
        )


def _long_chapter_tooling_options() -> HostToolingOptions:
    """构造返回长章节结果的 mock business tool options。

    :returns: HostToolingOptions。
    :raises ValueError: 工具声明字段非法时由底层抛出。
    """

    properties: Mapping[str, JsonValue] = {
        "ticker": {
            "type": "string",
            "description": "ticker symbol",
        }
    }
    return HostToolingOptions(
        business_tool_bundle=ToolBundle(
            definitions=(
                ToolDefinition(
                    name="lookup_mock_fact",
                    schema=ToolSchema(
                        type="function",
                        function=ToolFunctionSchema(
                            name="lookup_mock_fact",
                            description="Return deterministic long filing chapter.",
                            parameters=ToolParametersSchema(
                                type="object",
                                properties=properties,
                                required=("ticker",),
                                additional_properties=False,
                            ),
                        ),
                    ),
                    callable=_LongChapterMockTool(),
                    truncate=None,
                    display=None,
                    tags=("slice7",),
                ),
            )
        ),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="slice7-long-chapter-tool",
            ),
        ),
    )


def _joined_message_content(messages: tuple[AgentMessage, ...]) -> str:
    """拼接 Engine request messages 的文本内容。

    :param messages: Engine messages。
    :returns: 文本拼接结果。
    """

    return "\n\n".join(
        message.content if message.content is not None else "" for message in messages
    )


def _long_compaction_prompt(marker: str) -> str:
    """构造会触发 proactive compact 的长用户输入。

    :param marker: 本轮唯一标记。
    :returns: 长 prompt。
    """

    return (
        f"{marker}：请保留这段财报分析上下文。"
        + "营收、毛利率、现金流和库存周转的讨论。" * 160
    )


def _long_user_input_with_second_factor() -> str:
    """构造包含第二因素标记的长用户输入。

    :returns: 长 prompt。
    """

    return (
        "请分析三个因素：第一个因素=收入增速；"
        f"{_SECOND_FACTOR_MARKER}；第三个因素=经营现金流。"
        + "补充背景：管理层讨论、分部披露、季节性和费用率变化。" * 180
    )


def _long_chapter_tool_result() -> str:
    """构造长章节 raw tool result。

    :returns: 工具结果文本。
    """

    return (
        "财报章节原文："
        + "管理层讨论显示收入结构变化和费用率改善。" * 35
        + f" 关键结论：{_LONG_CHAPTER_MARKER}。"
    )


def _soft_threshold_prompt() -> str:
    """返回语义可压缩且会触发 soft threshold 的真实 compactor smoke prompt。

    :returns: 测试 prompt。
    """

    return _SOFT_THRESHOLD_PROMPT_SENTENCE * _SOFT_THRESHOLD_PROMPT_REPEAT_COUNT


def _compactor_baseline_inputs() -> tuple[str, str, AgentPolicy]:
    """通过默认 compactor baseline 装配 compactor prompt 与 AgentPolicy。

    :returns: system prompt、user prompt template 与 AgentPolicy。
    :raises AssertionError: scene 或 prompt asset 不符合 compactor 约定时抛出。
    :raises OSError: user prompt template 读取失败时抛出。
    """

    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=None
    )
    compactor_baseline = config.execution_profiles.execution_profiles[
        _COMPACTOR_PROFILE_ID
    ].compactor_baseline
    scene = prepare_scene(
        ScenePrepareRequest(
            scene_id=compactor_baseline.scene_id,
            scene_manifest_root=_PACKAGE_CONFIG_ROOT / "prompts" / "manifests",
            prompt_asset_root=_PACKAGE_CONFIG_ROOT / "prompts",
            context_slot_values={},
            available_tools=SceneToolCatalog(tools=()),
        )
    )
    assert len(scene.system_messages) == 1
    user_prompt_template = (
        _PACKAGE_CONFIG_ROOT
        / "prompts"
        / compactor_baseline.user_prompt_template_path
    ).read_text(encoding="utf-8")
    assert "<<compaction_request>>" in user_prompt_template
    override = scene.agent_policy_override
    assert override is not None
    assert override.max_iterations is not None
    assert override.continuation_max_attempts is not None
    assert override.allow_tool_calls is not None
    assert override.tool_execution_timeout_seconds is not None
    assert override.fallback_mode is not None
    assert override.fallback_prompt is not None
    assert override.continuation_prompt is not None
    assert override.max_consecutive_failed_tool_batches is not None
    return (
        scene.system_messages[0],
        user_prompt_template,
        AgentPolicy(
            max_iterations=override.max_iterations,
            continuation_max_attempts=override.continuation_max_attempts,
            allow_tool_calls=override.allow_tool_calls,
            tool_execution_timeout_seconds=override.tool_execution_timeout_seconds,
            fallback_mode=AgentFallbackMode(override.fallback_mode.value),
            fallback_prompt=override.fallback_prompt,
            continuation_prompt=override.continuation_prompt,
            max_consecutive_failed_tool_batches=(
                override.max_consecutive_failed_tool_batches
            ),
        ),
    )


def _compactor_runner_options(model_id: str) -> RunnerCallOptions:
    """从默认模型配置读取 compactor runner option hint。

    :param model_id: provider smoke case 使用的模型 id。
    :returns: ``conversation_compaction`` hint 映射出的 RunnerCallOptions。
    :raises KeyError: 默认配置缺少模型或 compactor hint 时抛出。
    :raises ValueError: RunnerCallOptions 字段非法时由底层抛出。
    """

    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=None
    )
    compactor_baseline = config.execution_profiles.execution_profiles[
        _COMPACTOR_PROFILE_ID
    ].compactor_baseline
    hint = config.models.models[
        model_id
    ].runtime_hints.runner_option_hints[compactor_baseline.runner_option_hint_id]
    return RunnerCallOptions(
        temperature=hint.temperature,
        max_tokens=None,
        top_p=hint.top_p,
        stream=hint.stream,
    )


def _compact_artifact_files(root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """返回 compact artifact 根目录下的已发布文件。

    :param root: compact artifact 根目录。
    :returns: 按路径排序的文件 tuple。
    :raises Exception: 不主动抛出异常。
    """

    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def _compact_artifact_for_run(
    paths: tuple[pathlib.Path, ...], run_id: str
) -> Mapping[str, JsonValue]:
    """从 artifact 文件集合中找出匹配指定 Run 的 compact artifact。

    :param paths: 候选 artifact 文件路径。
    :param run_id: 本次 compact 关联的 Host Run id。
    :returns: artifact JSON object。
    :raises AssertionError: 没有找到匹配 artifact 时抛出。
    """

    expected_candidate_id = f"llm-compact:{run_id}"
    for path in paths:
        artifact = _required_mapping(_read_json(path), field_name=str(path))
        if artifact.get(_COMPACT_ARTIFACT_KIND_FIELD) != _COMPACT_ARTIFACT_KIND:
            continue
        candidate = _required_mapping(
            artifact[_ACCEPTED_CANDIDATE_FIELD],
            field_name=_ACCEPTED_CANDIDATE_FIELD,
        )
        if candidate.get(_CANDIDATE_ID_FIELD) == expected_candidate_id:
            return artifact
    raise AssertionError(f"compact artifact for run {run_id} was not found")


def _runner_call_manifest_for_run(
    paths: tuple[pathlib.Path, ...], run_id: str
) -> Mapping[str, JsonValue]:
    """从 artifact 文件集合中找出指定 Run 的 runner-call manifest。

    :param paths: 候选 artifact 文件路径。
    :param run_id: Host Run id。
    :returns: runner-call manifest JSON object。
    :raises AssertionError: 没有找到匹配 manifest 时抛出。
    """

    for path in paths:
        artifact = _required_mapping(_read_json(path), field_name=str(path))
        if artifact.get("schema_version") != RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION:
            continue
        if artifact.get("host_run_id") != run_id:
            continue
        if artifact.get("runner_call_kind") != "compactor_proposal":
            continue
        return artifact
    raise AssertionError(f"runner-call manifest for run {run_id} was not found")


def _read_json(path: pathlib.Path) -> JsonValue:
    """读取 JSON artifact。

    :param path: artifact 文件路径。
    :returns: JSON 值。
    :raises OSError: 文件读取失败时抛出。
    :raises json.JSONDecodeError: JSON 解析失败时抛出。
    """

    return cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))


def _required_mapping(
    value: JsonValue, *, field_name: str
) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: 待校验 JSON 值。
    :param field_name: 错误字段名。
    :returns: JSON object。
    :raises AssertionError: 值不是 object 时抛出。
    """

    assert isinstance(value, Mapping), f"{field_name} must be JSON object"
    return value
