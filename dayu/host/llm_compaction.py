"""Host-owned LLM context compactor。

本模块把 Host ``CompactionRequest`` 映射为一次禁用工具的 Engine public
runner 调用，并把 LLM final answer 的摘要文本转换为 Host-owned
``CompactionCandidate``。它不写 EventLog、不写 artifact、不做 semantic
repair loop，也不向 Service 暴露 prompt、candidate builder 或 policy seam。
"""

from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.engine import run_agent_and_wait
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
    EngineRunOutcomeSuspended,
)
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
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

_COMPACTOR_RUN_ID_PREFIX = "context-compactor"
_COMPACTOR_MAX_ITERATIONS = 1
_COMPACTOR_TOOL_TIMEOUT_SECONDS = 1.0
_MIN_SUMMARY_LENGTH = 1
_MAX_SAFE_OUTCOME_MESSAGE_CHARS = 240
_TRUNCATED_SUFFIX = "..."
_REDACTED_SECRET = "<redacted>"
_BEARER_SECRET_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT_SECRET_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|authorization)\s*[:=]\s*)[^,\s}\]]+"
)
_SYSTEM_PROMPT = (
    "You are a host-owned context compaction component. Summarize the provided "
    "Host context refs into a concise episode summary. Do not claim new "
    "verified facts, do not invent evidence refs, do not request tools, and "
    "return only the summary text."
)


class LLMCompactionProposalError(RuntimeError):
    """LLM compaction 单次 proposal 失败。

    :param message: 中性失败描述。
    """


@dataclass(slots=True)
class _ThreadRunState:
    """跨线程运行 async Engine 调用的最小状态。

    :param result: Engine run 终态；线程完成前为 ``None``。
    :param error: Engine 调用抛出的异常；无异常时为 ``None``。
    """

    result: AgentRunResult | None = None
    error: BaseException | None = None


class _NeverCancelledToken(CancellationToken):
    """compactor proposal 使用的不可取消 token。"""

    def is_cancelled(self) -> bool:
        """返回取消状态。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


class _RejectingToolExecutor(ToolExecutor):
    """禁用工具 compactor 的 rejecting executor。

    Engine request 同时设置 ``disable_tools=True`` 与空 tool schema；若未来
    上游错误地发起工具握手，本 executor 返回空批次，让 Engine 的双射校验
    将其收口为协议失败。
    """

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """拒绝 compactor 工具握手。

        :param request: Engine 发起的工具批式请求。
        :returns: 空批次 outcome。
        """

        del request
        return BatchToolExecutionOutcome(records=())


class LLMContextCompactor(ContextCompactor):
    """Host-owned LLM context compactor。

    :param runner_spec: compactor 独立 Runner 规约。
    :param runner_options: compactor 独立 Runner 调用参数。
    """

    def __init__(
        self,
        *,
        runner_spec: RunnerSpec,
        runner_options: RunnerCallOptions,
    ) -> None:
        """初始化 Host-owned compactor。

        :param runner_spec: compactor 独立 Runner 规约。
        :param runner_options: compactor 独立 Runner 调用参数。
        :returns: ``None``。
        :raises TypeError: runner 参数类型非法时抛出。
        """

        if not isinstance(runner_spec, RunnerSpec):
            raise TypeError("runner_spec must be RunnerSpec")
        if not isinstance(runner_options, RunnerCallOptions):
            raise TypeError("runner_options must be RunnerCallOptions")
        self._runner_spec = runner_spec
        self._runner_options = runner_options

    def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """执行一次 LLM compaction proposal。

        :param request: Host 构造的 immutable compaction request。
        :returns: Host-owned candidate。
        :raises TypeError: request 类型非法时抛出。
        :raises LLMCompactionProposalError: LLM 没有返回可用 final summary 时抛出。
        :raises Exception: Engine runner / provider 调用失败时透传。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        outcome = _run_agent_request_sync(
            _agent_request(request, self._runner_spec, self._runner_options)
        )
        if not isinstance(outcome, EngineRunOutcomeFinalAnswer):
            raise LLMCompactionProposalError(_non_final_outcome_message(outcome))
        summary = outcome.content.strip()
        if len(summary) < _MIN_SUMMARY_LENGTH:
            raise LLMCompactionProposalError("compactor summary is empty")
        return _candidate_from_summary(request, summary)


def _agent_request(
    request: CompactionRequest,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
) -> AgentRunRequest:
    """构造禁用工具的 Engine public run request。

    :param request: Host compaction request。
    :param runner_spec: compactor Runner 规约。
    :param runner_options: compactor Runner 调用参数。
    :returns: Engine AgentRunRequest。
    """

    return AgentRunRequest(
        run_id=f"{_COMPACTOR_RUN_ID_PREFIX}-{request.run_id}-{uuid4().hex}",
        session_id=request.session_id,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
            UserMessage(role=AgentMessageRole.USER, content=_user_prompt(request)),
        ),
        disable_tools=True,
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=AgentPolicy(
            max_iterations=_COMPACTOR_MAX_ITERATIONS,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=_COMPACTOR_TOOL_TIMEOUT_SECONDS,
        ),
        tool_schemas=(),
        tool_executor=_RejectingToolExecutor(),
        cancellation_token=_NeverCancelledToken(),
    )


def _run_agent_request_sync(request: AgentRunRequest) -> AgentRunResult:
    """同步运行 Engine async public runner。

    :param request: Engine AgentRunRequest。
    :returns: AgentRunResult。
    :raises BaseException: Engine async 调用抛出的异常会原样透传。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_agent_and_wait(request))
    state = _ThreadRunState()
    thread = threading.Thread(
        target=_run_agent_request_in_thread,
        args=(request, state),
        name="dayu-host-llm-compactor",
        daemon=True,
    )
    thread.start()
    thread.join()
    if state.error is not None:
        raise state.error
    if state.result is None:
        raise LLMCompactionProposalError("compactor runner thread returned no result")
    return state.result


def _non_final_outcome_message(outcome: AgentRunResult) -> str:
    """构造非 final outcome 的脱敏 proposal 失败描述。

    :param outcome: Engine public runner 返回的非 final outcome。
    :returns: 不含密钥、headers 与完整 provider payload 的中性错误描述。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(outcome, EngineRunOutcomeFailed):
        return (
            "compactor runner failed "
            f"error_code={outcome.error_code} "
            f"recoverable={outcome.recoverable} "
            f"message={_safe_outcome_text(outcome.message)}"
        )
    if isinstance(outcome, EngineRunOutcomeCancelled):
        return "compactor runner was cancelled"
    if isinstance(outcome, EngineRunOutcomeSuspended):
        return f"compactor runner suspended reason={_safe_outcome_text(outcome.reason)}"
    return "compactor runner did not return final answer"


def _safe_outcome_text(text: str) -> str:
    """脱敏并截断 provider / runner 错误摘要。

    :param text: 原始错误摘要。
    :returns: 可进入异常消息的短文本。
    :raises Exception: 不主动抛出异常。
    """

    redacted = _BEARER_SECRET_PATTERN.sub(
        f"Bearer {_REDACTED_SECRET}", text
    )
    redacted = _ASSIGNMENT_SECRET_PATTERN.sub(
        rf"\1{_REDACTED_SECRET}", redacted
    )
    if len(redacted) <= _MAX_SAFE_OUTCOME_MESSAGE_CHARS:
        return redacted
    return redacted[:_MAX_SAFE_OUTCOME_MESSAGE_CHARS] + _TRUNCATED_SUFFIX


def _run_agent_request_in_thread(
    request: AgentRunRequest, state: _ThreadRunState
) -> None:
    """在线程中运行 Engine async runner。

    :param request: Engine AgentRunRequest。
    :param state: 跨线程结果容器。
    :returns: ``None``。
    """

    try:
        state.result = asyncio.run(run_agent_and_wait(request))
    except BaseException as exc:
        state.error = exc


def _user_prompt(request: CompactionRequest) -> str:
    """构造 Host-owned compactor user prompt。

    :param request: Host compaction request。
    :returns: 用户消息文本。
    """

    lines = [
        f"trigger_source: {request.trigger_source.value}",
        f"session_id: {request.session_id}",
        f"run_id: {request.run_id}",
        f"current_user_input_ref: {request.current_message_summary.current_user_input_ref}",
        f"current_user_input_summary: {request.current_message_summary.summary_text}",
        f"input_event_refs: {_refs_text(request.input_event_refs)}",
        f"tool_fact_refs: {_refs_text(request.tool_fact_refs)}",
        f"verified_fact_refs: {_refs_text(request.verified_fact_refs)}",
        f"recent_raw_turn_refs: {_refs_text(request.recent_raw_turn_refs)}",
        f"older_raw_turn_refs: {_refs_text(request.older_raw_turn_refs)}",
        f"existing_episode_summary_refs: {_refs_text(request.existing_episode_summary_refs)}",
        "Return a concise summary in plain text only.",
    ]
    return "\n".join(lines)


def _refs_text(refs: tuple[str, ...]) -> str:
    """格式化 ref tuple。

    :param refs: Host opaque refs。
    :returns: 逗号分隔文本；为空时返回 ``none``。
    """

    if len(refs) == 0:
        return "none"
    return ", ".join(refs)


def _candidate_from_summary(
    request: CompactionRequest, summary: str
) -> CompactionCandidate:
    """把 LLM summary 映射为 Host-owned candidate。

    :param request: Host compaction request。
    :param summary: LLM 返回的摘要文本。
    :returns: CompactionCandidate。
    """

    evidence = _preservation_evidence(request)
    evidence_refs = tuple(item.evidence_id for item in evidence)
    summarized_ranges = _summarized_ranges(request)
    return CompactionCandidate(
        candidate_id=f"llm-compact:{request.run_id}",
        episode_summary_candidate=EpisodeSummaryCandidate(
            candidate_id=f"llm-summary:{request.run_id}",
            episode_title="Context compact summary",
            goal=summary,
            completed_actions=(summary,),
            confirmed_fact_refs=request.verified_fact_refs,
            confirmed_fact_summaries=_confirmed_fact_summaries(request),
            user_constraints=(
                f"keep-current-input:{request.current_message_summary.current_user_input_ref}",
            ),
            open_questions=("continue-current-run",),
            next_step="continue with the current user input",
            tool_finding_refs=request.tool_fact_refs,
            source_event_refs=request.input_event_refs,
            evidence_refs=evidence_refs,
        ),
        pinned_state_patch_candidate=PinnedStatePatchCandidate(
            candidate_id=f"llm-pinned-patch:{request.run_id}",
            current_goal=PinnedTextFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=summary,
                evidence_refs=evidence_refs,
            ),
            confirmed_subjects=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=_confirmed_subjects(request),
                evidence_refs=evidence_refs,
            ),
            user_constraints=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=(
                    f"keep-current-input:{request.current_message_summary.current_user_input_ref}",
                ),
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
        summarized_ranges=summarized_ranges,
        budget_after_compact=_budget_after_compact(request),
    )


def _preservation_evidence(
    request: CompactionRequest,
) -> tuple[PreservationEvidence, ...]:
    """构造 Host-owned preservation evidence。

    :param request: Host compaction request。
    :returns: preservation evidence tuple。
    """

    return (
        PreservationEvidence(
            evidence_id=f"llm-evidence:{request.run_id}:primary",
            input_event_refs=request.input_event_refs,
            tool_fact_refs=request.tool_fact_refs,
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=_input_range(request),
        ),
    )


def _input_range(request: CompactionRequest) -> CompactInputRange | None:
    """根据 request 输入 refs 构造 compact range。

    :param request: Host compaction request。
    :returns: compact input range；无输入时为 ``None``。
    """

    if len(request.input_event_refs) == 0:
        return None
    return CompactInputRange(
        range_ref=f"llm-range:{request.run_id}:input",
        start_input_ref=request.input_event_refs[0],
        end_input_ref=request.input_event_refs[-1],
    )


def _summarized_ranges(request: CompactionRequest) -> tuple[CompactInputRange, ...]:
    """构造 summarized ranges。

    :param request: Host compaction request。
    :returns: summarized range tuple。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ()
    return (
        CompactInputRange(
            range_ref=f"llm-range:{request.run_id}:older-raw-turns",
            start_input_ref=request.older_raw_turn_refs[0],
            end_input_ref=request.older_raw_turn_refs[-1],
        ),
    )


def _confirmed_fact_summaries(request: CompactionRequest) -> tuple[str, ...]:
    """构造 confirmed fact summaries。

    :param request: Host compaction request。
    :returns: confirmed fact summary tuple。
    """

    return tuple(f"verified:{fact_ref}" for fact_ref in request.verified_fact_refs)


def _confirmed_subjects(request: CompactionRequest) -> tuple[str, ...]:
    """构造 pinned confirmed subjects。

    :param request: Host compaction request。
    :returns: opaque subject refs。
    """

    if len(request.verified_fact_refs) > 0:
        return tuple(f"subject:{fact_ref}" for fact_ref in request.verified_fact_refs)
    return (f"subject:{request.current_message_summary.current_user_input_ref}",)


def _budget_after_compact(request: CompactionRequest) -> int:
    """保守估算 compact 后预算。

    :param request: Host compaction request。
    :returns: 非负 token 估算。
    """

    estimate = request.budget_before_compact
    half_estimate = max(0, estimate.estimated_input_tokens // 2)
    return min(half_estimate, estimate.hard_threshold_tokens - 1)


__all__ = ["LLMCompactionProposalError", "LLMContextCompactor"]
