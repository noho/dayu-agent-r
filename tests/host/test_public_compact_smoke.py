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
from dayu.engine.contracts.agent_policy import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage, UserMessage
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
    joined = _joined_message_content(second_request.messages)
    assert "第一轮原始问题：请记住营收增长来自价格因素。" in joined
    assert "Memory episode summaries:" not in joined


@pytest.mark.asyncio
async def test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """public opener compact 后能从 raw accepted tool evidence 生成 stable fact。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: public material 缺 evidence_input 或后续 request 未复用 fact 时抛出。
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
                _long_compaction_prompt("tool-evidence-compact-trigger"),
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
    evidence_input = material_json["evidence_material"]
    assert isinstance(evidence_input, list)
    assert len(evidence_input) >= 1
    material_text = json.dumps(material_json, ensure_ascii=False, sort_keys=True)
    assert _LONG_CHAPTER_MARKER in material_text
    assert "result_preview" not in material_text
    assert "payload:" not in material_text
    assert "event-tool-result" not in material_text
    assert len(factory.requests) >= 3
    joined = _joined_message_content(factory.requests[-1].messages)
    assert "Memory evidence-backed facts:" in joined
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
    fact_candidates = proposal["evidence_backed_facts"]
    assert isinstance(fact_candidates, list)
    assert len(fact_candidates) == 1
    fact = _required_mapping(fact_candidates[0], field_name="fact")
    assert fact["evidence_labels"] == ["E1"]
    claim_text = fact["claim_text"]
    assert isinstance(claim_text, str)
    assert _LONG_CHAPTER_MARKER in claim_text
    proposal_text = json.dumps(proposal, ensure_ascii=False, sort_keys=True)
    assert "result_preview" not in proposal_text
    assert "event-tool-result-accepted" not in proposal_text
    assert "payload:" not in proposal_text


@pytest.mark.asyncio
async def test_long_user_input_second_factor_survives_minimum_preserve(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """长输入 compact 后，下一轮仍可通过 minimum preserve 看到第二个因素。

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
    joined = _joined_message_content(factory.requests[1].messages)
    assert _SECOND_FACTOR_MARKER in joined
    assert "Memory episode summaries:" in joined


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
                    _long_compaction_prompt(f"multi-compact-marker-{index}"),
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
    assert max(fake_compactor.prompt_lengths) <= _FAKE_COMPACTOR_MAX_PROMPT_CHARS
    assert len(_joined_message_content(factory.requests[-1].messages)) <= (
        _FAKE_PUBLIC_MEMORY_MAX_CHARS
    )


@pytest.mark.asyncio
async def test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重复长 prompt 触发 proactive compact 时不会因 compactor 输入重复超窗失败。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: compact 未触发、Run 失败或 compactor prompt 过大时抛出。
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
                _DUPLICATE_PROMPT_SENTENCE * 500,
            ),
        )
        terminal = await next_terminal_for_run(watcher, followup.accepted_run_id)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert len(fake_compactor.prompt_lengths) == 1
    assert fake_compactor.prompt_lengths[0] <= _FAKE_COMPACTOR_MAX_PROMPT_CHARS


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
        material_json = _material_json_from_compactor_request(request)
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
    """返回首个包含 evidence_input 的 compactor material JSON。

    :param values: fake compactor 记录的 material JSON 列表。
    :returns: 首个包含 evidence_input 项的 material JSON。
    :raises AssertionError: 所有 public compactor material 都缺 evidence_input 时抛出。
    """

    for value in values:
        evidence_input = value["evidence_material"]
        assert isinstance(evidence_input, list)
        if len(evidence_input) > 0:
            return value
    raise AssertionError("public compactor material evidence_input is empty")


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


def _llm_material_with_long_tool_evidence() -> Mapping[str, JsonValue]:
    """构造只含 prompt-local label 的 LLM-facing raw evidence material。

    :returns: LLM-facing material JSON。
    """

    return {
        "previous_compacted_view": [],
        "trace_material": [],
        "evidence_material": [
            {
                "label": "E1",
                "kind": "accepted_tool_evidence",
                "tool_name": "lookup_mock_fact",
                "query_text": "读取长章节工具证据",
                "result_text": _long_chapter_tool_result(),
                "source_text": "accepted raw tool evidence",
            }
        ],
        "current_input_anchor": {
            "label": "C1",
            "kind": "current_input_anchor",
            "text": "复用 raw evidence fact。",
            "truncated": False,
        },
    }


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
