"""P10.5 Slice 6 public real-compactor smoke。"""

from __future__ import annotations

import asyncio
import pathlib
import threading
from dataclasses import replace
from datetime import datetime

import pytest

from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine import AgentPolicy, AgentRunRequest, EngineRunOutcomeFinalAnswer
from dayu.engine import run_agent_and_wait
from dayu.engine.contracts.messages import AgentMessageRole, SystemMessage, UserMessage
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import CompactorExecutionBaseline, HostEventKind, open_host
from dayu.host.compaction import (
    CompactInputRange,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    EpisodeSummaryCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)
from dayu.host.context_policy import default_context_budget_policy
from tests.host.public_smoke_support import (
    PROVIDER_CASES,
    FinalAnswerWorkerFactory,
    api_key_or_skip,
    ensure_request,
    followup_request,
    next_terminal_for_run,
    open_host_options,
    runner_spec_for_case,
    skip_if_provider_exception,
    skip_if_provider_terminal_failed,
)

_SOFT_CONTEXT_WINDOW_SIZE = 110
_SOFT_RESERVED_OUTPUT_TOKENS = 10
_SOFT_HARD_THRESHOLD_TOKENS = 95
_SOFT_SAFETY_MARGIN_RATIO = 0.2
_SOFT_THRESHOLD_PROMPT_CHAR_COUNT = 220
_COMPACTOR_TIMEOUT_SECONDS = 90.0


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否取消。

        :returns: 始终为 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _RejectingToolExecutor:
    """compactor LLM 不应调用工具的 executor。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回工具误调用失败结果。

        :param request: 批式工具请求。
        :returns: 与输入 calls 对应的失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return BatchToolExecutionOutcome(
            records=tuple(
                BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=ToolFailedOutcome(
                        result=ToolResultFailure(
                            ok=False,
                            error="compact_tool_call_forbidden",
                            message="compactor smoke does not expose tools",
                            hint=None,
                            meta=None,
                        )
                    ),
                )
                for call in request.calls
            )
        )


class _RealLLMContextCompactor(ContextCompactor):
    """显式真实 LLM compactor adapter。

    :param runner_spec: compactor 独立 RunnerSpec。
    :param runner_options: compactor RunnerCallOptions。
    """

    def __init__(
        self, runner_spec: RunnerSpec, runner_options: RunnerCallOptions
    ) -> None:
        """初始化 adapter。

        :param runner_spec: compactor 独立 RunnerSpec。
        :param runner_options: compactor RunnerCallOptions。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._runner_spec = runner_spec
        self._runner_options = runner_options
        self.call_count = 0
        self.last_summary: str | None = None

    def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """调用真实 LLM 生成摘要，再映射为 Host typed candidate。

        :param request: Host compaction request。
        :returns: compaction candidate。
        :raises RuntimeError: compactor LLM 失败或超时时抛出。
        """

        self.call_count += 1
        summary = self._run_llm_summary(request)
        self.last_summary = summary
        return _candidate_from_summary(request, summary)

    def _run_llm_summary(self, request: CompactionRequest) -> str:
        """在线程中执行异步 Engine runner 并返回摘要。

        :param request: Host compaction request。
        :returns: LLM 摘要文本。
        :raises RuntimeError: LLM 执行失败或超时时抛出。
        """

        result_box: list[str] = []
        error_box: list[BaseException] = []

        def target() -> None:
            """线程入口。

            :returns: ``None``。
            :raises Exception: 线程内异常记录到 ``error_box``。
            """

            try:
                result_box.append(
                    asyncio.run(self._run_llm_summary_async(request))
                )
            except BaseException as exc:
                error_box.append(exc)

        thread = threading.Thread(target=target, name="slice6-real-compactor")
        thread.start()
        thread.join(timeout=_COMPACTOR_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise RuntimeError("compactor LLM timed out")
        if error_box:
            raise RuntimeError(f"compactor LLM failed: {error_box[0]}")
        if not result_box:
            raise RuntimeError("compactor LLM returned no summary")
        return result_box[0]

    async def _run_llm_summary_async(self, request: CompactionRequest) -> str:
        """异步调用真实 Engine runner 生成摘要。

        :param request: Host compaction request。
        :returns: LLM 摘要文本。
        :raises RuntimeError: LLM 未返回 final answer 时抛出。
        """

        outcome = await run_agent_and_wait(
            AgentRunRequest(
                run_id=f"compact-{request.run_id}",
                session_id=request.session_id,
                messages=(
                    SystemMessage(
                        role=AgentMessageRole.SYSTEM,
                        content=(
                            "你是上下文压缩器。只输出一段不超过 30 字的中文摘要。"
                        ),
                    ),
                    UserMessage(
                        role=AgentMessageRole.USER,
                        content=(
                            "当前输入摘要："
                            f"{request.current_message_summary.summary_text}"
                        ),
                    ),
                ),
                disable_tools=True,
                runner_spec=self._runner_spec,
                runner_options=self._runner_options,
                agent_policy=AgentPolicy(
                    max_iterations=1,
                    continuation_max_attempts=0,
                    allow_tool_calls=False,
                    tool_execution_timeout_seconds=5.0,
                ),
                tool_schemas=(),
                tool_executor=_RejectingToolExecutor(),
                cancellation_token=_NeverCancelledToken(),
            )
        )
        if not isinstance(outcome, EngineRunOutcomeFinalAnswer):
            raise RuntimeError("compactor LLM did not return final answer")
        if outcome.content.strip() == "":
            raise RuntimeError("compactor LLM returned empty summary")
        return outcome.content.strip()


@pytest.mark.asyncio
async def test_real_compactor_public_opener_compacts_and_preserves_continuity(
    tmp_path: pathlib.Path,
) -> None:
    """public opener 触发真实 compactor，并在后续 run 保持连续性。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: compact 未触发或 terminal 不成功时抛出。
    """

    case = PROVIDER_CASES[1]
    api_key = api_key_or_skip(case)
    runner_spec = runner_spec_for_case(case, api_key)
    compactor_runner_spec = replace(runner_spec, provider_request=None)
    runner_options = RunnerCallOptions(
        temperature=0.0,
        max_tokens=512,
        top_p=None,
        stream=True,
    )
    compactor = _RealLLMContextCompactor(compactor_runner_spec, runner_options)
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
    options = replace(
        base_options,
        context_budget_policy=default_context_budget_policy(
            context_window_size=_SOFT_CONTEXT_WINDOW_SIZE,
            reserved_output_tokens=_SOFT_RESERVED_OUTPUT_TOKENS,
            hard_threshold_tokens=_SOFT_HARD_THRESHOLD_TOKENS,
            safety_margin_ratio=_SOFT_SAFETY_MARGIN_RATIO,
            minimum_protection_tokens=1,
            policy_ref="slice6-real-compact-policy",
        ),
        compactor_baseline=CompactorExecutionBaseline(
            context_compactor=compactor,
            compactor_runner_spec=compactor_runner_spec,
            compactor_runner_options=runner_options,
            compactor_policy_ref="slice6-real-llm-compactor",
            compact_artifact_root=tmp_path / "compact-artifacts",
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
                    "x" * _SOFT_THRESHOLD_PROMPT_CHAR_COUNT,
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
    assert compactor.call_count >= 1
    assert compactor.last_summary is not None
    assert first_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.final_answer is not None
    assert second_terminal.final_answer.content.strip() != ""


def _candidate_from_summary(
    request: CompactionRequest, summary: str
) -> CompactionCandidate:
    """把真实 LLM 摘要映射为 Host 可校验 candidate。

    :param request: compaction request。
    :param summary: LLM 生成的摘要文本。
    :returns: CompactionCandidate。
    :raises ValueError: candidate 字段非法时由底层抛出。
    """

    evidence = _preservation_evidence(request)
    evidence_refs = tuple(item.evidence_id for item in evidence)
    return CompactionCandidate(
        candidate_id=f"real-compact:{request.run_id}",
        episode_summary_candidate=EpisodeSummaryCandidate(
            candidate_id=f"real-summary:{request.run_id}",
            episode_title="Real compactor smoke summary",
            goal=summary,
            completed_actions=("real LLM summary produced",),
            confirmed_fact_refs=request.verified_fact_refs,
            confirmed_fact_summaries=_confirmed_fact_summaries(request),
            user_constraints=("preserve current input",),
            open_questions=("continue-current-run",),
            next_step="continue after compact",
            tool_finding_refs=request.tool_fact_refs,
            source_event_refs=request.input_event_refs,
            evidence_refs=evidence_refs,
        ),
        pinned_state_patch_candidate=PinnedStatePatchCandidate(
            candidate_id=f"real-pinned:{request.run_id}",
            current_goal=PinnedTextFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=summary,
                evidence_refs=evidence_refs,
            ),
            confirmed_subjects=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=(
                    "subject:"
                    f"{request.current_message_summary.current_user_input_ref}",
                ),
                evidence_refs=evidence_refs,
            ),
            user_constraints=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("preserve-current-input",),
                evidence_refs=evidence_refs,
            ),
            open_questions=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("continue-current-run",),
                evidence_refs=evidence_refs,
            ),
        ),
        preservation_evidence=evidence,
        retained_current_user_input_ref=(
            request.current_message_summary.current_user_input_ref
        ),
        preserved_input_event_refs=request.input_event_refs,
        preserved_tool_fact_refs=request.tool_fact_refs,
        preserved_verified_fact_refs=request.verified_fact_refs,
        dropped_ranges=(),
        summarized_ranges=_summarized_ranges(request),
        budget_after_compact=max(
            0, request.budget_before_compact.estimated_input_tokens // 2
        ),
    )


def _preservation_evidence(
    request: CompactionRequest,
) -> tuple[PreservationEvidence, ...]:
    """构造 preservation evidence。

    :param request: compaction request。
    :returns: preservation evidence tuple。
    :raises ValueError: evidence 字段非法时由底层抛出。
    """

    return (
        PreservationEvidence(
            evidence_id=f"real-evidence:{request.run_id}",
            input_event_refs=request.input_event_refs,
            tool_fact_refs=request.tool_fact_refs,
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=_range_for_request(request),
        ),
    )


def _range_for_request(request: CompactionRequest) -> CompactInputRange | None:
    """根据输入 refs 构造 compact range。

    :param request: compaction request。
    :returns: compact range；无输入时为 ``None``。
    :raises ValueError: range 字段非法时由底层抛出。
    """

    if len(request.input_event_refs) == 0:
        return None
    return CompactInputRange(
        range_ref=f"real-range:{request.run_id}:inputs",
        start_input_ref=request.input_event_refs[0],
        end_input_ref=request.input_event_refs[-1],
    )


def _summarized_ranges(request: CompactionRequest) -> tuple[CompactInputRange, ...]:
    """构造 summarized ranges。

    :param request: compaction request。
    :returns: summarized ranges。
    :raises ValueError: range 字段非法时由底层抛出。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ()
    return (
        CompactInputRange(
            range_ref=f"real-range:{request.run_id}:older",
            start_input_ref=request.older_raw_turn_refs[0],
            end_input_ref=request.older_raw_turn_refs[-1],
        ),
    )


def _confirmed_fact_summaries(request: CompactionRequest) -> tuple[str, ...]:
    """构造 confirmed fact summaries。

    :param request: compaction request。
    :returns: fact summaries。
    :raises Exception: 不主动抛出异常。
    """

    if len(request.verified_fact_refs) == 0:
        return ("no verified facts in compact input",)
    return tuple(f"verified:{fact_ref}" for fact_ref in request.verified_fact_refs)
