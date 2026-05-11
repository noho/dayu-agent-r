"""run-scoped Agent 主链路实现。

本模块承载 Engine 内部 Agent 状态机：

- 公共调用方通过 :func:`run_agent_messages` /
  :func:`run_agent_and_wait` 使用函数式入口。
- 私有 :class:`_AsyncAgent` 负责单次 run 内的 RunnerEvent 消费、
  EngineEvent 提升、普通 tool calling 闭环、length continuation、
  终态收口与 Runner close。
- Engine 只消费 ToolExecutor protocol；不注册工具、不发现工具、不持有
  ToolRegistry，也不理解 ToolExecutor 的真实部署位置。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias, assert_never

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)
from dayu.contracts.tool_schema import ToolSchema
from dayu.engine.contracts.agent_policy import AgentFallbackMode
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    ContextBudgetSnapshot,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    ContentCompleteData,
    ContentDeltaData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    IterationStartedData,
    ProviderProtocolErrorData,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunnerDoneEngineData,
    RunnerUsageData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    AssistantToolCall,
    ToolMessage,
    UserMessage,
)
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner
from dayu.runtime.cancellation import WaitCancelled, WaitCompleted, await_or_cancel
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER: logging.Logger = logging.getLogger(__name__)

_FIRST_ITERATION_INDEX: int = 0
_FIRST_ITERATION_ORDINAL: int = 1
_DEFAULT_CANCEL_REASON: str = "cancelled"
_ERROR_MAX_ITERATIONS_EXCEEDED: str = "max_iterations_exceeded"
_ERROR_RUNNER_EXCEPTION: str = "runner_exception"
_ERROR_RUNNER_ABNORMAL_STOP: str = "runner_abnormal_stop"
_ERROR_RUNNER_ERROR_DONE_WITHOUT_DETAIL: str = (
    "runner_error_done_without_detail"
)
_ERROR_CONTEXT_COMPACTION_REQUIRED: str = "context_compaction_required"
_ERROR_TOOL_CALL_NOT_ENABLED: str = "tool_call_not_enabled"
_ERROR_MISSING_TERMINAL: str = "missing_terminal"
_ERROR_UNEXPECTED_SUSPENDED: str = "unexpected_suspended_in_phase3"
_ERROR_RUNNER_TOOL_CALLS_MISSING: str = "runner_tool_calls_missing"
_ERROR_RUNNER_TOOL_CALLS_FINISH_REASON_MISMATCH: str = (
    "runner_tool_calls_finish_reason_mismatch"
)
_ERROR_TOOL_AWAITING_NOT_SUPPORTED: str = "tool_awaiting_not_supported_in_phase3"
_ERROR_DUPLICATE_TOOL_CALL_ID: str = "duplicate_tool_call_id"
_ERROR_TOOL_EXECUTOR_EXCEPTION: str = "tool_executor_exception"
_ERROR_FORCE_ANSWER_EMPTY: str = "force_answer_empty"
_ERROR_CONSECUTIVE_FAILED_TOOL_BATCHES: str = (
    "consecutive_failed_tool_batches"
)
_ERROR_CONTINUATION_TOOL_CALL_NOT_ALLOWED: str = (
    "continuation_tool_call_not_allowed"
)
_RUNNER_ERROR_WITHOUT_DETAIL_MESSAGE: str = (
    "runner finished with error without detail"
)
_CONTEXT_COMPACTION_REQUIRED_MESSAGE: str = (
    "provider context overflow requires Host compaction"
)
_RUNNER_ABNORMAL_STOP_MESSAGE: str = "runner stopped without done event"
_MAX_ITERATIONS_EXCEEDED_MESSAGE: str = (
    "agent policy max_iterations must be at least 1"
)
_TOOL_CALL_NOT_ENABLED_MESSAGE: str = (
    "runner produced tool calls while tools were disabled or unavailable"
)
_MISSING_TERMINAL_MESSAGE: str = "agent event stream ended without terminal"
_FORCE_ANSWER_EMPTY_MESSAGE: str = (
    "force-answer runner did not produce final content"
)
_MAX_ITERATIONS_EXHAUSTED_MESSAGE: str = (
    "agent policy max_iterations exhausted"
)
_CONSECUTIVE_FAILED_TOOL_BATCHES_MESSAGE: str = (
    "consecutive failed tool batches threshold reached"
)
_CONTINUATION_TOOL_CALL_NOT_ALLOWED_MESSAGE: str = (
    "continuation runner call produced tool calls while tools were disabled"
)
_EXCEPTION_MESSAGE_REDACTED: str = "exception message redacted"
_EXCEPTION_MESSAGE_MAX_LENGTH: int = 240
_SENSITIVE_EXCEPTION_MARKERS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "authorization",
    "bearer ",
    "header",
    "password",
    "secret",
    "token",
)

_PlainJsonValue: TypeAlias = (
    None | bool | int | float | str | list["_PlainJsonValue"] | dict[str, "_PlainJsonValue"]
)

def _utc_now() -> datetime:
    """返回当前 UTC 时间。

    :returns: 带 ``timezone.utc`` 的当前时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _exception_diagnostic_message(exc: Exception) -> str:
    """构造可进入 run_failed 的异常诊断消息。

    :param exc: 捕获到的异常。
    :returns: 包含异常类型和安全摘要的诊断消息。
    :raises Exception: 不主动抛出异常。
    """

    exc_type = type(exc).__name__
    raw_message = str(exc)
    if not raw_message:
        return exc_type
    lowered_message = raw_message.lower()
    if any(marker in lowered_message for marker in _SENSITIVE_EXCEPTION_MARKERS):
        return f"{exc_type}: {_EXCEPTION_MESSAGE_REDACTED}"
    if len(raw_message) > _EXCEPTION_MESSAGE_MAX_LENGTH:
        raw_message = raw_message[:_EXCEPTION_MESSAGE_MAX_LENGTH]
    return f"{exc_type}: {raw_message}"


def _fallback_error_message(error_code: str) -> str:
    """返回 fallback RAISE_ERROR 模式下的人类可读失败消息。

    :param error_code: fallback 触发原因错误码。
    :returns: 面向诊断和上层展示的失败消息。
    :raises Exception: 不主动抛出异常。
    """

    if error_code == _ERROR_MAX_ITERATIONS_EXCEEDED:
        return _MAX_ITERATIONS_EXHAUSTED_MESSAGE
    if error_code == _ERROR_CONSECUTIVE_FAILED_TOOL_BATCHES:
        return _CONSECUTIVE_FAILED_TOOL_BATCHES_MESSAGE
    return f"agent fallback raised error: {error_code}"


def _build_runner(request: AgentRunRequest) -> AsyncRunner:
    """根据请求构造当前内置 Runner。

    当前只装配 OpenAI-compatible Runner；后续如果需要其它 Runner，必须先
    新增明确的 runner 选择契约，而不是在本函数塞入开放插件机制。

    :param request: Agent run 请求。
    :returns: 新建的 Runner 实例。
    :raises Exception: Runner 构造失败时透传底层异常。
    """

    return AsyncOpenAIRunner(
        spec=request.runner_spec,
        cancellation_token=request.cancellation_token,
    )


def _plain_json_value(value: JsonValue) -> _PlainJsonValue:
    """把严格 JSON 值转换为 ``json.dumps`` 可直接处理的内建容器。

    :param value: 严格 JSON 值。
    :returns: 仅由内建 ``dict`` / ``list`` / 标量组成的 JSON 值。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, Mapping):
        return {key: _plain_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_json_value(item) for item in value]
    return value


def _project_tool_success_for_llm(
    result: ToolResultSuccess,
) -> dict[str, _PlainJsonValue]:
    """将成功工具结果投影为 LLM-facing JSON object。

    :param result: 内部成功结果信封。
    :returns: 可注入 ``ToolMessage.content`` 的 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    value = result.value
    if isinstance(value, Mapping):
        projected = {
            key: _plain_json_value(item) for key, item in value.items()
        }
    else:
        projected = {"content": _plain_json_value(value)}
    return projected


def _project_tool_failure_for_llm(
    result: ToolResultFailure,
) -> dict[str, _PlainJsonValue]:
    """将失败工具结果投影为 LLM-facing JSON object。

    :param result: 内部失败结果信封。
    :returns: 可注入 ``ToolMessage.content`` 的 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    projected: dict[str, _PlainJsonValue] = {
        "error": result.error,
        "message": result.message,
    }
    if result.hint is not None:
        projected["hint"] = result.hint
    return projected


def _project_tool_outcome_for_llm(
    outcome: ToolCompletedOutcome | ToolFailedOutcome,
) -> str:
    """把工具 outcome 投影为 LLM-facing JSON 字符串。

    :param outcome: completed / failed 工具 outcome。
    :returns: JSON 字符串；内容始终非空，保证 tool message 配对完整。
    :raises TypeError: JSON 序列化失败时抛出。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        projected = _project_tool_success_for_llm(outcome.result)
    elif isinstance(outcome, ToolFailedOutcome):
        projected = _project_tool_failure_for_llm(outcome.result)
    else:
        assert_never(outcome)
    return json.dumps(projected, ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class _IterationState:
    """单次 Runner 调用的消费状态。"""

    content_chunks: list[str]
    reasoning_chunks: list[str]
    completed_content: str | None
    completed_reasoning_content: str | None
    finish_reason: FinishReason | None
    failure_candidate: RunFailedData | None
    done_seen: bool
    tool_call_signal_seen: bool
    tool_calls: tuple[ToolCallRequest, ...] | None
    tool_calls_content: str | None
    tool_calls_reasoning_content: str | None


@dataclass(frozen=True, slots=True)
class _FinalDecision:
    """普通最终回答决策。"""

    content: str
    filtered: bool
    degraded: bool
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class _ToolCallsDecision:
    """进入工具执行阶段的决策。"""

    iteration_id: str
    iteration_index: int
    content: str | None
    reasoning_content: str | None
    tool_calls: tuple[ToolCallRequest, ...]


_IterationDecision: TypeAlias = _FinalDecision | _ToolCallsDecision | RunFailedData


@dataclass(frozen=True, slots=True)
class _ToolOutcomeRecord:
    """单个工具调用执行后的 accepted outcome 记录。"""

    call: ToolCallRequest
    outcome: ToolCompletedOutcome | ToolFailedOutcome


def _tool_outcome_name(
    outcome: ToolCompletedOutcome | ToolFailedOutcome,
) -> str:
    """返回工具 outcome 的日志安全分类名。

    :param outcome: 已接受的工具 outcome。
    :returns: ``completed`` 或 ``failed``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return "completed"
    if isinstance(outcome, ToolFailedOutcome):
        return "failed"
    assert_never(outcome)


def _count_completed_tool_records(records: Sequence[_ToolOutcomeRecord]) -> int:
    """统计 completed 工具 outcome 数量。

    :param records: 工具 outcome 记录序列。
    :returns: completed 数量。
    :raises Exception: 不主动抛出异常。
    """

    return sum(
        1 for record in records
        if isinstance(record.outcome, ToolCompletedOutcome)
    )


def _count_failed_tool_records(records: Sequence[_ToolOutcomeRecord]) -> int:
    """统计 failed 工具 outcome 数量。

    :param records: 工具 outcome 记录序列。
    :returns: failed 数量。
    :raises Exception: 不主动抛出异常。
    """

    return sum(
        1 for record in records
        if isinstance(record.outcome, ToolFailedOutcome)
    )


def _tool_call_count(tool_calls: tuple[ToolCallRequest, ...] | None) -> int:
    """返回工具调用数量。

    :param tool_calls: 可选工具调用元组。
    :returns: ``None`` 时返回 0，否则返回元组长度。
    :raises Exception: 不主动抛出异常。
    """

    if tool_calls is None:
        return 0
    return len(tool_calls)


@dataclass(frozen=True, slots=True)
class _ToolBatchCompleted:
    """一批工具调用执行完成。"""

    records: tuple[_ToolOutcomeRecord, ...]


_ToolBatchResult: TypeAlias = _ToolBatchCompleted | RunFailedData


class _AsyncAgent:
    """单次 run 私有 Agent 状态机。

    :param request: Agent run 请求。
    :param runner: 本次 run 独占的 Runner。
    """

    def __init__(self, *, request: AgentRunRequest, runner: AsyncRunner) -> None:
        """初始化私有 Agent。

        :param request: Agent run 请求。
        :param runner: 本次 run 独占 Runner。
        :raises Exception: 不主动抛出异常。
        """

        self._request: AgentRunRequest = request
        self._runner: AsyncRunner = runner
        self._active_run_id: str | None = None
        self._run_guard_lock: threading.Lock = threading.Lock()
        self._next_sequence: int = 0
        self._terminal_seen: bool = False
        self._closed: bool = False
        self._last_iteration_state: _IterationState | None = None
        self._last_tool_batch_result: _ToolBatchResult | None = None
        self._executed_tool_call_ids: set[str] = set()
        self._consecutive_failed_tool_batches: int = 0

    async def run_messages(self) -> AsyncGenerator[EngineEvent, None]:
        """运行 Agent 并产出 EngineEvent 流。

        :returns: EngineEvent 异步流。
        :raises RuntimeError: 同一 Agent 实例并发运行时抛出。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        self._acquire_run_slot()
        try:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "engine.agent.run_start session_id=%s run_id=%s "
                "message_count=%s max_iterations=%s tool_schema_count=%s "
                "disable_tools=%s",
                self._request.session_id,
                self._request.run_id,
                len(self._request.messages),
                self._request.agent_policy.max_iterations,
                len(self._request.tool_schemas),
                self._request.disable_tools,
            )
            if self._is_cancelled():
                yield await self._make_cancelled_terminal_with_close()
                return
            if self._request.agent_policy.max_iterations < 1:
                yield await self._make_failed_or_cancelled_terminal_with_close(
                    RunFailedData(
                        error_code=_ERROR_MAX_ITERATIONS_EXCEEDED,
                        message=_MAX_ITERATIONS_EXCEEDED_MESSAGE,
                        recoverable=False,
                    )
                )
                return

            messages: list[AgentMessage] = list(self._request.messages)
            ordinary_iterations = self._request.agent_policy.max_iterations
            continuation_content_parts: list[str] = []
            continuation_attempts = 0
            continuation_active = False

            for iteration_index in range(ordinary_iterations):
                iteration_id = self._iteration_id(iteration_index)
                effective_tools = (
                    () if continuation_active else self._effective_tools()
                )
                tool_calls_enabled = len(effective_tools) > 0
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "engine.agent.iteration_start session_id=%s run_id=%s "
                    "iteration_id=%s iteration_index=%s tool_count=%s "
                    "continuation=%s",
                    self._request.session_id,
                    self._request.run_id,
                    iteration_id,
                    iteration_index,
                    len(effective_tools),
                    continuation_active,
                )

                if self._is_cancelled():
                    yield await self._make_cancelled_terminal_with_close()
                    return
                async for event in self._run_runner_iteration(
                    messages=messages,
                    iteration_id=iteration_id,
                    iteration_index=iteration_index,
                    tools=effective_tools,
                ):
                    yield event
                    if self._is_terminal(event):
                        return

                state = self._last_iteration_state
                if state is None:
                    _LOGGER.critical(
                        "engine.agent.missing_iteration_state session_id=%s "
                        "run_id=%s iteration_id=%s iteration_index=%s",
                        self._request.session_id,
                        self._request.run_id,
                        iteration_id,
                        iteration_index,
                    )
                    yield await self._make_failed_or_cancelled_terminal_with_close(
                        RunFailedData(
                            error_code=_ERROR_MISSING_TERMINAL,
                            message=_MISSING_TERMINAL_MESSAGE,
                            recoverable=False,
                        )
                    )
                    return
                if self._is_cancelled():
                    yield await self._make_cancelled_terminal_with_close()
                    return

                if continuation_active:
                    continuation_failure = self._continuation_tool_call_failure(
                        state
                    )
                    if continuation_failure is not None:
                        yield await self._make_failed_or_cancelled_terminal_with_close(
                            continuation_failure
                        )
                        return

                decision = self._classify_iteration(
                    state=state,
                    iteration_id=iteration_id,
                    iteration_index=iteration_index,
                    tool_calls_enabled=tool_calls_enabled,
                    degraded=False,
                )
                self._log_iteration_decision(
                    decision=decision,
                    iteration_id=iteration_id,
                    iteration_index=iteration_index,
                )
                if isinstance(decision, _FinalDecision):
                    continuation_decision = self._handle_final_decision(
                        messages=messages,
                        decision=decision,
                        iteration_index=iteration_index,
                        continuation_content_parts=continuation_content_parts,
                        continuation_attempts=continuation_attempts,
                        continuation_active=continuation_active,
                    )
                    if isinstance(continuation_decision, _FinalDecision):
                        _LOGGER.log(
                            VERBOSE_LOG_LEVEL,
                            "engine.agent.final_ready "
                            "session_id=%s run_id=%s iteration_id=%s "
                            "iteration_index=%s continuation=%s degraded=%s",
                            self._request.session_id,
                            self._request.run_id,
                            iteration_id,
                            iteration_index,
                            continuation_active or bool(continuation_content_parts),
                            continuation_decision.degraded,
                        )
                        yield await self._make_final_or_cancelled_after_close(
                            continuation_decision
                        )
                        return
                    if continuation_decision is None:
                        _LOGGER.log(
                            VERBOSE_LOG_LEVEL,
                            "engine.agent.continuation_scheduled "
                            "session_id=%s run_id=%s iteration_id=%s "
                            "iteration_index=%s continuation_attempt=%s",
                            self._request.session_id,
                            self._request.run_id,
                            iteration_id,
                            iteration_index,
                            continuation_attempts + 1,
                        )
                        continuation_attempts += 1
                        continuation_active = True
                        continue
                    yield await self._make_final_or_cancelled_after_close(decision)
                    return
                if isinstance(decision, RunFailedData):
                    yield await self._make_failed_or_cancelled_terminal_with_close(
                        decision
                    )
                    return

                continuation_active = False
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "engine.agent.tool_loop_start session_id=%s run_id=%s "
                    "iteration_id=%s iteration_index=%s tool_call_count=%s",
                    self._request.session_id,
                    self._request.run_id,
                    decision.iteration_id,
                    decision.iteration_index,
                    len(decision.tool_calls),
                )
                async for event in self._execute_tool_batch(decision):
                    yield event
                    if self._is_terminal(event):
                        return

                batch_result = self._last_tool_batch_result
                if batch_result is None:
                    _LOGGER.critical(
                        "engine.agent.tool_batch_missing_result "
                        "session_id=%s run_id=%s iteration_id=%s "
                        "iteration_index=%s",
                        self._request.session_id,
                        self._request.run_id,
                        decision.iteration_id,
                        decision.iteration_index,
                    )
                    yield await self._make_failed_or_cancelled_terminal_with_close(
                        RunFailedData(
                            error_code=_ERROR_MISSING_TERMINAL,
                            message="tool batch ended without result",
                            recoverable=False,
                        )
                    )
                    return
                if isinstance(batch_result, RunFailedData):
                    yield await self._make_failed_or_cancelled_terminal_with_close(
                        batch_result
                    )
                    return

                self._inject_tool_messages(
                    messages=messages,
                    decision=decision,
                    records=batch_result.records,
                )
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "engine.agent.tool_messages_injected session_id=%s "
                    "run_id=%s iteration_id=%s iteration_index=%s "
                    "message_count=%s tool_message_count=%s",
                    self._request.session_id,
                    self._request.run_id,
                    decision.iteration_id,
                    decision.iteration_index,
                    len(messages),
                    len(batch_result.records),
                )

                if self._is_cancelled():
                    yield await self._make_cancelled_terminal_with_close()
                    return

                if self._all_records_failed(batch_result.records):
                    self._consecutive_failed_tool_batches += 1
                else:
                    self._consecutive_failed_tool_batches = 0

                if self._consecutive_failed_tool_batches >= (
                    self._request.agent_policy.max_consecutive_failed_tool_batches
                ):
                    async for event in self._fallback_after_tools(
                        messages=messages,
                        next_iteration_index=iteration_index + 1,
                        error_code=_ERROR_CONSECUTIVE_FAILED_TOOL_BATCHES,
                    ):
                        yield event
                    return

                if iteration_index + 1 >= ordinary_iterations:
                    async for event in self._fallback_after_tools(
                        messages=messages,
                        next_iteration_index=iteration_index + 1,
                        error_code=_ERROR_MAX_ITERATIONS_EXCEEDED,
                    ):
                        yield event
                    return
        finally:
            await self._close_runner_once()
            self._release_run_slot()

    def _handle_final_decision(
        self,
        *,
        messages: list[AgentMessage],
        decision: _FinalDecision,
        iteration_index: int,
        continuation_content_parts: list[str],
        continuation_attempts: int,
        continuation_active: bool,
    ) -> _FinalDecision | None:
        """处理普通 final decision 与 length continuation。

        :param messages: 可追加的 run-local 消息列表。
        :param decision: 当前 Runner 调用得到的 final decision。
        :param iteration_index: 当前迭代序号。
        :param continuation_content_parts: 已累积的 continuation 内容片段。
        :param continuation_attempts: 已发起的 continuation 次数。
        :param continuation_active: 当前 Runner 调用是否为 continuation。
        :returns: 返回 final decision 表示应终止；返回 ``None`` 表示已准备
            下一轮 continuation。
        :raises Exception: 不主动抛出异常。
        """

        if decision.finish_reason is FinishReason.LENGTH:
            return self._handle_length_final_decision(
                messages=messages,
                decision=decision,
                iteration_index=iteration_index,
                continuation_content_parts=continuation_content_parts,
                continuation_attempts=continuation_attempts,
            )
        if continuation_content_parts or continuation_active:
            return _FinalDecision(
                content="".join(
                    [*continuation_content_parts, decision.content]
                ),
                filtered=decision.filtered,
                degraded=True,
                finish_reason=decision.finish_reason,
            )
        return decision

    def _handle_length_final_decision(
        self,
        *,
        messages: list[AgentMessage],
        decision: _FinalDecision,
        iteration_index: int,
        continuation_content_parts: list[str],
        continuation_attempts: int,
    ) -> _FinalDecision | None:
        """处理 ``finish_reason=length`` 的续写状态转移。

        :param messages: 可追加的 run-local 消息列表。
        :param decision: 当前 length final decision。
        :param iteration_index: 当前迭代序号。
        :param continuation_content_parts: 已累积的 continuation 内容片段。
        :param continuation_attempts: 已发起的 continuation 次数。
        :returns: 返回 final decision 表示达到边界后终止；返回 ``None``
            表示已注入 continuation prompt，调用方应进入下一轮 Runner。
        :raises Exception: 不主动抛出异常。
        """

        continuation_content_parts.append(decision.content)
        can_continue = continuation_attempts < (
            self._request.agent_policy.continuation_max_attempts
        )
        has_iteration_budget = (
            iteration_index + 1 < self._request.agent_policy.max_iterations
        )
        if not can_continue or not has_iteration_budget:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "engine.agent.continuation_exhausted session_id=%s run_id=%s "
                "iteration_index=%s continuation_attempts=%s "
                "has_iteration_budget=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_index,
                continuation_attempts,
                has_iteration_budget,
            )
            return _FinalDecision(
                content="".join(continuation_content_parts),
                filtered=decision.filtered,
                degraded=True,
                finish_reason=decision.finish_reason,
            )

        if decision.content:
            messages.append(
                AssistantMessage(
                    role=AgentMessageRole.ASSISTANT,
                    content=decision.content,
                    reasoning_content=None,
                    tool_calls=(),
                )
            )
        messages.append(
            UserMessage(
                role=AgentMessageRole.USER,
                content=self._request.agent_policy.continuation_prompt,
            )
        )
        return None

    def _continuation_tool_call_failure(
        self, state: _IterationState
    ) -> RunFailedData | None:
        """识别 continuation 轮非法工具调用。

        :param state: 当前 Runner 调用消费状态。
        :returns: 非法工具调用失败 data；未发现时返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if (
            state.tool_calls is not None
            or state.tool_call_signal_seen
            or state.finish_reason is FinishReason.TOOL_CALLS
        ):
            return RunFailedData(
                error_code=_ERROR_CONTINUATION_TOOL_CALL_NOT_ALLOWED,
                message=_CONTINUATION_TOOL_CALL_NOT_ALLOWED_MESSAGE,
                recoverable=False,
            )
        return None

    def _acquire_run_slot(self) -> None:
        """申请运行槽位。

        :returns: 无返回值。
        :raises RuntimeError: 当前实例已有运行中的 run 时抛出。
        """

        with self._run_guard_lock:
            if self._active_run_id is not None:
                raise RuntimeError(
                    "AsyncAgent instance does not support concurrent runs: "
                    f"active_run_id={self._active_run_id}, "
                    f"incoming_run_id={self._request.run_id}"
                )
            self._active_run_id = self._request.run_id

    def _release_run_slot(self) -> None:
        """释放运行槽位。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        with self._run_guard_lock:
            if self._active_run_id == self._request.run_id:
                self._active_run_id = None

    async def _run_runner_iteration(
        self,
        *,
        messages: Sequence[AgentMessage],
        iteration_id: str,
        iteration_index: int,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[EngineEvent]:
        """执行一次 Runner 调用并流式提升 RunnerEvent。

        :param messages: 本轮 Runner 输入消息。
        :param iteration_id: 当前迭代 id。
        :param iteration_index: 当前迭代序号。
        :param tools: 本轮暴露给 Runner 的工具 schema。
        :returns: EngineEvent 异步流。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        self._last_iteration_state = _IterationState(
            content_chunks=[],
            reasoning_chunks=[],
            completed_content=None,
            completed_reasoning_content=None,
            finish_reason=None,
            failure_candidate=None,
            done_seen=False,
            tool_call_signal_seen=False,
            tool_calls=None,
            tool_calls_content=None,
            tool_calls_reasoning_content=None,
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "engine.agent.runner_call_start session_id=%s run_id=%s "
            "iteration_id=%s iteration_index=%s message_count=%s "
            "tool_count=%s",
            self._request.session_id,
            self._request.run_id,
            iteration_id,
            iteration_index,
            len(messages),
            len(tools),
        )
        yield self._make_event(
            event_type=EngineEventType.ITERATION_STARTED,
            data=IterationStartedData(
                iteration_id=iteration_id,
                iteration_index=iteration_index,
                message_count=len(messages),
            ),
            occurred_at=_utc_now(),
        )

        if self._is_cancelled():
            yield await self._make_cancelled_terminal_with_close()
            return

        try:
            async for runner_event in self._runner.call(
                messages,
                self._request.runner_options,
                tools,
            ):
                engine_event = self._consume_runner_event(
                    runner_event=runner_event,
                    iteration_id=iteration_id,
                )
                if engine_event is not None:
                    yield engine_event
            runner_call_completed_failure = self._log_runner_call_completed(
                iteration_id=iteration_id,
                iteration_index=iteration_index,
            )
            if runner_call_completed_failure is not None:
                yield await self._make_failed_or_cancelled_terminal_with_close(
                    runner_call_completed_failure
                )
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.warning(
                "agent.runner_exception run_id=%s iteration_id=%s exc_type=%s",
                self._request.run_id,
                iteration_id,
                type(exc).__name__,
                exc_info=True,
            )
            state = self._last_iteration_state
            if state is None:
                _LOGGER.critical(
                    "engine.agent.missing_iteration_state session_id=%s "
                    "run_id=%s iteration_id=%s iteration_index=%s "
                    "runner_exception=true exc_type=%s",
                    self._request.session_id,
                    self._request.run_id,
                    iteration_id,
                    iteration_index,
                    type(exc).__name__,
                )
                yield await self._make_failed_or_cancelled_terminal_with_close(
                    RunFailedData(
                        error_code=_ERROR_MISSING_TERMINAL,
                        message=_MISSING_TERMINAL_MESSAGE,
                        recoverable=False,
                    )
                )
                return
            state.failure_candidate = RunFailedData(
                error_code=_ERROR_RUNNER_EXCEPTION,
                message=_exception_diagnostic_message(exc),
                recoverable=False,
            )

    def _consume_runner_event(
        self, *, runner_event: RunnerEvent, iteration_id: str
    ) -> EngineEvent | None:
        """消费单个 RunnerEvent 并按需提升为 EngineEvent。

        :param runner_event: Runner 产出的事件。
        :param iteration_id: 当前迭代 id。
        :returns: 需要向 Host 暴露的 EngineEvent；HTTP error 与 tool call
            delta 仅记录状态，返回 ``None``。
        :raises RuntimeError: 内部迭代状态缺失时抛出。
        """

        state = self._last_iteration_state
        if state is None:
            raise RuntimeError("iteration state is not initialized")

        data = runner_event.data
        if isinstance(data, RunnerContentDeltaData):
            state.content_chunks.append(data.delta)
            return self._make_event(
                event_type=EngineEventType.RUNNER_CONTENT_DELTA,
                data=ContentDeltaData(
                    iteration_id=iteration_id, delta=data.delta
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerReasoningDeltaData):
            state.reasoning_chunks.append(data.delta)
            return self._make_event(
                event_type=EngineEventType.RUNNER_REASONING_DELTA,
                data=ReasoningDeltaData(
                    iteration_id=iteration_id, delta=data.delta
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerContentCompletedData):
            state.completed_content = data.content
            state.completed_reasoning_content = data.reasoning_content
            state.finish_reason = data.finish_reason
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s finish_reason=%s "
                "has_content=%s has_reasoning=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
                data.finish_reason.value,
                data.content is not None,
                data.reasoning_content is not None,
            )
            return self._make_event(
                event_type=EngineEventType.RUNNER_CONTENT_COMPLETED,
                data=ContentCompleteData(
                    iteration_id=iteration_id,
                    content=data.content,
                    reasoning_content=data.reasoning_content,
                    finish_reason=data.finish_reason,
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerUsageRecordedData):
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s "
                "prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
                data.prompt_tokens,
                data.completion_tokens,
                data.total_tokens,
            )
            return self._make_event(
                event_type=EngineEventType.RUNNER_USAGE_RECORDED,
                data=RunnerUsageData(
                    iteration_id=iteration_id,
                    prompt_tokens=data.prompt_tokens,
                    completion_tokens=data.completion_tokens,
                    total_tokens=data.total_tokens,
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerProtocolErrorData):
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s error_code=%s "
                "provider_request_id=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
                data.error_code,
                data.provider_request_id,
            )
            state.failure_candidate = RunFailedData(
                error_code=data.error_code,
                message=data.message,
                recoverable=False,
            )
            return self._make_event(
                event_type=EngineEventType.PROVIDER_PROTOCOL_ERROR,
                data=ProviderProtocolErrorData(
                    iteration_id=iteration_id,
                    error_code=data.error_code,
                    message=data.message,
                    provider_request_id=data.provider_request_id,
                    raw_payload=data.raw_payload,
                    partial_tool_calls=data.partial_tool_calls,
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerHTTPErrorData):
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s error_code=%s "
                "http_status=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
                data.error_code.value,
                data.http_status,
            )
            if data.error_code is RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED:
                state.failure_candidate = RunFailedData(
                    error_code=_ERROR_CONTEXT_COMPACTION_REQUIRED,
                    message=_CONTEXT_COMPACTION_REQUIRED_MESSAGE,
                    recoverable=True,
                )
                return self._make_event(
                    event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                    data=ContextCompactionRequestedData(
                        iteration_id=iteration_id,
                        budget_state=ContextBudgetSnapshot(
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                        ),
                        reason=_ERROR_CONTEXT_COMPACTION_REQUIRED,
                    ),
                    occurred_at=runner_event.occurred_at,
                )
            state.failure_candidate = RunFailedData(
                error_code=data.error_code.value,
                message=data.message,
                recoverable=False,
            )
            return None
        if isinstance(data, RunnerDoneData):
            state.done_seen = True
            state.finish_reason = data.finish_reason
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s finish_reason=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
                data.finish_reason.value,
            )
            return self._make_event(
                event_type=EngineEventType.RUNNER_DONE,
                data=RunnerDoneEngineData(
                    iteration_id=iteration_id,
                    finish_reason=data.finish_reason,
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerToolCallDeltaData):
            state.tool_call_signal_seen = True
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
            )
            return None
        if isinstance(data, RunnerToolCallsCompletedData):
            state.tool_call_signal_seen = True
            state.tool_calls = data.tool_calls
            state.tool_calls_content = data.content
            state.tool_calls_reasoning_content = data.reasoning_content
            _LOGGER.debug(
                "engine.agent.runner_event_classified session_id=%s "
                "run_id=%s iteration_id=%s event_type=%s tool_call_count=%s "
                "has_content=%s has_reasoning=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                runner_event.type.value,
                len(data.tool_calls),
                data.content is not None,
                data.reasoning_content is not None,
            )
            return None
        state.failure_candidate = RunFailedData(
            error_code=_ERROR_RUNNER_EXCEPTION,
            message="runner event data did not match supported union",
            recoverable=False,
        )
        return None

    def _classify_iteration(
        self,
        *,
        state: _IterationState,
        iteration_id: str,
        iteration_index: int,
        tool_calls_enabled: bool,
        degraded: bool,
    ) -> _IterationDecision:
        """根据 Runner 消费状态分类下一步动作。

        :param state: 本轮 Runner 消费状态。
        :param iteration_id: 当前迭代 id。
        :param iteration_index: 当前迭代序号。
        :param tool_calls_enabled: 本轮是否允许工具调用。
        :param degraded: 产出 final answer 时是否标记为降级。
        :returns: final / tool calls / failed 三类决策之一。
        :raises Exception: 不主动抛出异常。
        """

        if not state.done_seen:
            if state.failure_candidate is not None:
                return state.failure_candidate
            return RunFailedData(
                error_code=_ERROR_RUNNER_ABNORMAL_STOP,
                message=_RUNNER_ABNORMAL_STOP_MESSAGE,
                recoverable=False,
            )

        finish_reason = state.finish_reason or FinishReason.STOP
        if finish_reason is FinishReason.ERROR:
            return state.failure_candidate or RunFailedData(
                error_code=_ERROR_RUNNER_ERROR_DONE_WITHOUT_DETAIL,
                message=_RUNNER_ERROR_WITHOUT_DETAIL_MESSAGE,
                recoverable=False,
            )

        if state.tool_calls is not None:
            if finish_reason is not FinishReason.TOOL_CALLS:
                return RunFailedData(
                    error_code=_ERROR_RUNNER_TOOL_CALLS_FINISH_REASON_MISMATCH,
                    message="runner completed tool calls with non-tool finish reason",
                    recoverable=False,
                )
            if not tool_calls_enabled:
                return RunFailedData(
                    error_code=_ERROR_TOOL_CALL_NOT_ENABLED,
                    message=_TOOL_CALL_NOT_ENABLED_MESSAGE,
                    recoverable=False,
                )
            if len(state.tool_calls) == 0:
                return RunFailedData(
                    error_code=_ERROR_RUNNER_TOOL_CALLS_MISSING,
                    message="runner done with empty tool calls",
                    recoverable=False,
                )
            content = state.tool_calls_content
            if content is None:
                content = state.completed_content
            if content is None and state.content_chunks:
                content = "".join(state.content_chunks)
            if content == "":
                content = None
            reasoning = state.tool_calls_reasoning_content
            if reasoning is None:
                reasoning = state.completed_reasoning_content
            if reasoning is None and state.reasoning_chunks:
                reasoning = "".join(state.reasoning_chunks)
            return _ToolCallsDecision(
                iteration_id=iteration_id,
                iteration_index=iteration_index,
                content=content,
                reasoning_content=reasoning,
                tool_calls=tuple(
                    sorted(
                        state.tool_calls,
                        key=lambda call: call.index_in_iteration,
                    )
                ),
            )

        if finish_reason is FinishReason.TOOL_CALLS or state.tool_call_signal_seen:
            return RunFailedData(
                error_code=_ERROR_RUNNER_TOOL_CALLS_MISSING,
                message="runner requested tool calls without completed tool call data",
                recoverable=False,
            )

        content = state.completed_content
        if content is None:
            content = "".join(state.content_chunks)
        filtered = finish_reason is FinishReason.CONTENT_FILTER
        return _FinalDecision(
            content=content,
            filtered=filtered,
            degraded=degraded or filtered,
            finish_reason=finish_reason,
        )

    async def _execute_tool_batch(
        self, decision: _ToolCallsDecision
    ) -> AsyncIterator[EngineEvent]:
        """串行执行一批工具调用并产出工具事件。

        :param decision: 工具调用决策。
        :returns: EngineEvent 异步流。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        self._last_tool_batch_result = None
        records: list[_ToolOutcomeRecord] = []
        for call in decision.tool_calls:
            if self._is_cancelled():
                yield await self._make_cancelled_terminal_with_close()
                return
            if call.tool_call_id in self._executed_tool_call_ids:
                self._last_tool_batch_result = RunFailedData(
                    error_code=_ERROR_DUPLICATE_TOOL_CALL_ID,
                    message="duplicate tool_call_id in run",
                    recoverable=False,
                )
                return

            yield self._make_event(
                event_type=EngineEventType.TOOL_CALL_REQUESTED,
                data=ToolCallRequestedData(
                    iteration_id=decision.iteration_id,
                    tool_call_id=call.tool_call_id,
                    name=call.name,
                    arguments=call.arguments,
                    index_in_iteration=call.index_in_iteration,
                    provider_state=call.provider_state,
                ),
                occurred_at=_utc_now(),
            )
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "engine.agent.tool_call_requested session_id=%s run_id=%s "
                "iteration_id=%s iteration_index=%s tool_name=%s "
                "tool_call_id=%s index_in_iteration=%s",
                self._request.session_id,
                self._request.run_id,
                decision.iteration_id,
                decision.iteration_index,
                call.name,
                call.tool_call_id,
                call.index_in_iteration,
            )

            self._executed_tool_call_ids.add(call.tool_call_id)
            tool_request = ToolExecutionRequest(
                call=call,
                context=ToolExecutionContext(
                    run_id=self._request.run_id,
                    session_id=self._request.session_id,
                    iteration_id=decision.iteration_id,
                    tool_call_id=call.tool_call_id,
                    index_in_iteration=call.index_in_iteration,
                    timeout_seconds=None,
                    cancellation_token=self._request.cancellation_token,
                    correlation_id=self._correlation_id(
                        iteration_id=decision.iteration_id,
                        tool_call_id=call.tool_call_id,
                    ),
                ),
            )

            outcome = await self._execute_one_tool(tool_request)
            if isinstance(outcome, WaitCancelled):
                yield await self._make_cancelled_terminal_with_close()
                return
            completed_outcome = outcome.value

            if self._is_cancelled():
                yield await self._make_cancelled_terminal_with_close()
                return
            if isinstance(completed_outcome, ToolAwaitingOutcome):
                self._last_tool_batch_result = RunFailedData(
                    error_code=_ERROR_TOOL_AWAITING_NOT_SUPPORTED,
                    message="ToolAwaitingOutcome is not supported in phase3",
                    recoverable=False,
                )
                return
            if isinstance(completed_outcome, ToolCompletedOutcome) or isinstance(
                completed_outcome, ToolFailedOutcome
            ):
                yield self._make_event(
                    event_type=EngineEventType.TOOL_RESULT_ACCEPTED,
                    data=ToolResultAcceptedData(
                        iteration_id=decision.iteration_id,
                        tool_call_id=call.tool_call_id,
                        name=call.name,
                        index_in_iteration=call.index_in_iteration,
                        outcome=completed_outcome,
                    ),
                    occurred_at=_utc_now(),
                )
                records.append(
                    _ToolOutcomeRecord(call=call, outcome=completed_outcome)
                )
                _LOGGER.debug(
                    "engine.agent.tool_result_accepted session_id=%s "
                    "run_id=%s iteration_id=%s iteration_index=%s "
                    "tool_name=%s tool_call_id=%s outcome=%s",
                    self._request.session_id,
                    self._request.run_id,
                    decision.iteration_id,
                    decision.iteration_index,
                    call.name,
                    call.tool_call_id,
                    _tool_outcome_name(completed_outcome),
                )
            else:
                assert_never(completed_outcome)
        self._last_tool_batch_result = _ToolBatchCompleted(records=tuple(records))
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "engine.agent.tool_batch_completed session_id=%s run_id=%s "
            "iteration_id=%s iteration_index=%s tool_call_count=%s "
            "completed_count=%s failed_count=%s",
            self._request.session_id,
            self._request.run_id,
            decision.iteration_id,
            decision.iteration_index,
            len(records),
            _count_completed_tool_records(records),
            _count_failed_tool_records(records),
        )

    async def _execute_one_tool(
        self, tool_request: ToolExecutionRequest
    ) -> WaitCompleted[ToolExecutionOutcome] | WaitCancelled:
        """执行单个工具调用并处理取消与普通异常。

        :param tool_request: 工具执行请求。
        :returns: ``WaitCompleted`` 包裹的 outcome，或 ``WaitCancelled``。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        try:
            return await await_or_cancel(
                self._request.tool_executor.execute(tool_request),
                token=self._request.cancellation_token,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return WaitCompleted(
                value=ToolFailedOutcome(
                    result=ToolResultFailure(
                        ok=False,
                        error=_ERROR_TOOL_EXECUTOR_EXCEPTION,
                        message=type(exc).__name__,
                        hint=None,
                        meta=None,
                    )
                )
            )

    def _inject_tool_messages(
        self,
        *,
        messages: list[AgentMessage],
        decision: _ToolCallsDecision,
        records: tuple[_ToolOutcomeRecord, ...],
    ) -> None:
        """向下一轮 Runner 输入注入 assistant tool_calls 与 tool messages。

        :param messages: 可追加的 run-local 消息列表。
        :param decision: 工具调用决策。
        :param records: 已接受的工具 outcome 记录。
        :returns: 无返回值。
        :raises TypeError: 工具结果 JSON 投影失败时抛出。
        """

        messages.append(
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content=decision.content,
                reasoning_content=decision.reasoning_content,
                tool_calls=tuple(
                    AssistantToolCall(
                        id=record.call.tool_call_id,
                        name=record.call.name,
                        arguments=record.call.arguments,
                        provider_state=record.call.provider_state,
                    )
                    for record in records
                ),
            )
        )
        for record in records:
            messages.append(
                ToolMessage(
                    role=AgentMessageRole.TOOL,
                    tool_call_id=record.call.tool_call_id,
                    content=_project_tool_outcome_for_llm(record.outcome),
                )
            )

    async def _fallback_after_tools(
        self,
        *,
        messages: list[AgentMessage],
        next_iteration_index: int,
        error_code: str,
    ) -> AsyncIterator[EngineEvent]:
        """工具批次后按策略执行 force-answer 或 raise-error。

        :param messages: 可追加的 run-local 消息列表。
        :param next_iteration_index: fallback Runner 使用的迭代序号。
        :param error_code: ``RAISE_ERROR`` 模式下使用的错误码。
        :returns: EngineEvent 异步流。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        mode = self._request.agent_policy.fallback_mode
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "engine.agent.fallback_start session_id=%s run_id=%s "
            "next_iteration_index=%s error_code=%s mode=%s",
            self._request.session_id,
            self._request.run_id,
            next_iteration_index,
            error_code,
            mode.value,
        )
        if mode is AgentFallbackMode.RAISE_ERROR:
            yield await self._make_failed_or_cancelled_terminal_with_close(
                RunFailedData(
                    error_code=error_code,
                    message=_fallback_error_message(error_code),
                    recoverable=False,
                )
            )
            return
        if mode is AgentFallbackMode.FORCE_ANSWER:
            messages.append(
                UserMessage(
                    role=AgentMessageRole.USER,
                    content=self._request.agent_policy.fallback_prompt,
                )
            )
            async for event in self._run_force_answer(
                messages=messages,
                iteration_index=next_iteration_index,
            ):
                yield event
            return
        assert_never(mode)

    async def _run_force_answer(
        self,
        *,
        messages: Sequence[AgentMessage],
        iteration_index: int,
    ) -> AsyncIterator[EngineEvent]:
        """禁用工具执行一次 force-answer Runner 调用。

        :param messages: 已追加 fallback prompt 的消息序列。
        :param iteration_index: fallback 迭代序号。
        :returns: EngineEvent 异步流。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        if self._is_cancelled():
            yield await self._make_cancelled_terminal_with_close()
            return
        iteration_id = self._iteration_id(iteration_index)
        async for event in self._run_runner_iteration(
            messages=messages,
            iteration_id=iteration_id,
            iteration_index=iteration_index,
            tools=(),
        ):
            yield event
            if self._is_terminal(event):
                return

        state = self._last_iteration_state
        if state is None:
            _LOGGER.critical(
                "engine.agent.missing_iteration_state session_id=%s run_id=%s "
                "iteration_id=%s iteration_index=%s fallback=force_answer",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                iteration_index,
            )
            yield await self._make_failed_or_cancelled_terminal_with_close(
                RunFailedData(
                    error_code=_ERROR_MISSING_TERMINAL,
                    message=_MISSING_TERMINAL_MESSAGE,
                    recoverable=False,
                )
            )
            return
        if self._is_cancelled():
            yield await self._make_cancelled_terminal_with_close()
            return
        decision = self._classify_iteration(
            state=state,
            iteration_id=iteration_id,
            iteration_index=iteration_index,
            tool_calls_enabled=False,
            degraded=True,
        )
        if isinstance(decision, _ToolCallsDecision):
            yield await self._make_failed_or_cancelled_terminal_with_close(
                RunFailedData(
                    error_code=_ERROR_TOOL_CALL_NOT_ENABLED,
                    message=_TOOL_CALL_NOT_ENABLED_MESSAGE,
                    recoverable=False,
                )
            )
            return
        if isinstance(decision, RunFailedData):
            yield await self._make_failed_or_cancelled_terminal_with_close(
                decision
            )
            return
        if decision.content == "":
            yield await self._make_failed_or_cancelled_terminal_with_close(
                RunFailedData(
                    error_code=_ERROR_FORCE_ANSWER_EMPTY,
                    message=_FORCE_ANSWER_EMPTY_MESSAGE,
                    recoverable=False,
                )
            )
            return
        yield await self._make_final_or_cancelled_after_close(decision)

    async def _make_final_or_cancelled_after_close(
        self, decision: _FinalDecision
    ) -> EngineEvent:
        """构造最终回答或取消终态。

        :param decision: final answer 决策。
        :returns: terminal EngineEvent。
        :raises Exception: 不主动抛出异常。
        """

        if self._is_cancelled():
            return await self._make_cancelled_terminal_with_close()
        return self._make_terminal_final(
            FinalAnswerData(
                content=decision.content,
                filtered=decision.filtered,
                degraded=decision.degraded,
                finish_reason=decision.finish_reason,
            )
        )

    async def _make_failed_or_cancelled_terminal_with_close(
        self, failure: RunFailedData
    ) -> EngineEvent:
        """按取消优先级构造失败终态。

        :param failure: 候选失败 data。
        :returns: ``RUN_CANCELLED`` 或 ``RUN_FAILED`` terminal。
        :raises Exception: 不主动抛出异常；Runner close 异常会被吞掉并记日志。
        """

        if self._is_cancelled():
            return await self._make_cancelled_terminal_with_close()
        return self._make_terminal_failed(failure)

    async def _make_cancelled_terminal_with_close(self) -> EngineEvent:
        """关闭 Runner 后构造取消终态。

        :returns: ``RUN_CANCELLED`` terminal。
        :raises Exception: 不主动抛出异常；Runner close 异常会被吞掉并记日志。
        """

        accepted_at = _utc_now()
        requested_at = self._request.cancellation_token.requested_at()
        if requested_at is None:
            requested_at = accepted_at
        reason = (
            self._request.cancellation_token.cancel_reason()
            or _DEFAULT_CANCEL_REASON
        )
        await self._close_runner_once()
        return self._make_terminal_cancelled(
            RunCancelledData(
                reason=reason,
                requested_at=requested_at,
                accepted_at=accepted_at,
                finished_at=_utc_now(),
            )
        )

    def _make_terminal_final(self, data: FinalAnswerData) -> EngineEvent:
        """构造唯一 final answer 终态。

        :param data: final answer data。
        :returns: terminal EngineEvent。
        :raises RuntimeError: terminal 已产出时抛出。
        """

        return self._make_terminal_event(
            event_type=EngineEventType.FINAL_ANSWER,
            data=data,
        )

    def _make_terminal_failed(self, data: RunFailedData) -> EngineEvent:
        """构造唯一 failed 终态。

        :param data: run failed data。
        :returns: terminal EngineEvent。
        :raises RuntimeError: terminal 已产出时抛出。
        """

        return self._make_terminal_event(
            event_type=EngineEventType.RUN_FAILED,
            data=data,
        )

    def _make_terminal_cancelled(self, data: RunCancelledData) -> EngineEvent:
        """构造唯一 cancelled 终态。

        :param data: run cancelled data。
        :returns: terminal EngineEvent。
        :raises RuntimeError: terminal 已产出时抛出。
        """

        return self._make_terminal_event(
            event_type=EngineEventType.RUN_CANCELLED,
            data=data,
        )

    def _make_terminal_event(
        self,
        *,
        event_type: EngineEventType,
        data: FinalAnswerData | RunFailedData | RunCancelledData,
    ) -> EngineEvent:
        """构造 terminal EngineEvent 并锁定终态。

        :param event_type: terminal 事件类型。
        :param data: terminal data。
        :returns: terminal EngineEvent。
        :raises RuntimeError: terminal 已产出时抛出。
        """

        if self._terminal_seen:
            _LOGGER.critical(
                "engine.agent.terminal_duplicate session_id=%s run_id=%s "
                "terminal_type=%s",
                self._request.session_id,
                self._request.run_id,
                event_type.value,
            )
            raise RuntimeError("terminal event already emitted")
        self._terminal_seen = True
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "engine.agent.terminal session_id=%s run_id=%s terminal_type=%s",
            self._request.session_id,
            self._request.run_id,
            event_type.value,
        )
        return self._make_event(
            event_type=event_type,
            data=data,
            occurred_at=_utc_now(),
        )

    def _make_event(
        self,
        *,
        event_type: EngineEventType,
        data: EngineEventData,
        occurred_at: datetime,
    ) -> EngineEvent:
        """构造普通 EngineEvent 并推进 sequence。

        :param event_type: Engine 事件类型。
        :param data: Engine 事件 data。
        :param occurred_at: 事件发生时间。
        :returns: EngineEvent。
        :raises Exception: 不主动抛出异常。
        """

        sequence = self._next_sequence
        self._next_sequence += 1
        return EngineEvent(
            event_id=f"{self._request.run_id}:{sequence}",
            sequence=sequence,
            occurred_at=occurred_at,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=event_type,
            data=data,
            metadata=None,
        )

    def _iteration_id(self, iteration_index: int) -> str:
        """返回指定迭代的 iteration id。

        :param iteration_index: 从 0 起的迭代序号。
        :returns: 当前 run 内稳定 iteration id。
        :raises Exception: 不主动抛出异常。
        """

        return (
            f"{self._request.run_id}_iteration_"
            f"{iteration_index + _FIRST_ITERATION_ORDINAL}"
        )

    def _correlation_id(self, *, iteration_id: str, tool_call_id: str) -> str:
        """构造工具执行中性关联 id。

        :param iteration_id: 当前迭代 id。
        :param tool_call_id: 工具调用 id。
        :returns: 中性 correlation id。
        :raises Exception: 不主动抛出异常。
        """

        return f"{self._request.run_id}:{iteration_id}:{tool_call_id}"

    def _effective_tools(self) -> Sequence[ToolSchema]:
        """返回本轮暴露给 Runner 的工具 schema。

        :returns: 启用工具时返回 request 中的 schema 快照，否则返回空元组。
        :raises Exception: 不主动抛出异常。
        """

        if self._request.disable_tools:
            return ()
        if not self._request.agent_policy.allow_tool_calls:
            return ()
        if not self._runner.is_supports_tool_calling():
            return ()
        return self._request.tool_schemas

    def _all_records_failed(self, records: tuple[_ToolOutcomeRecord, ...]) -> bool:
        """判断工具批次是否全失败。

        :param records: 本批工具 outcome 记录。
        :returns: 全部为 failed outcome 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(isinstance(record.outcome, ToolFailedOutcome) for record in records)

    def _is_terminal(self, event: EngineEvent) -> bool:
        """判断事件是否为 terminal。

        :param event: EngineEvent。
        :returns: terminal 返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return event.type in {
            EngineEventType.FINAL_ANSWER,
            EngineEventType.RUN_FAILED,
            EngineEventType.RUN_CANCELLED,
            EngineEventType.RUN_SUSPENDED,
        }

    def _is_cancelled(self) -> bool:
        """返回 Host cancellation token 是否已取消。

        :returns: 已取消返回 ``True``，否则 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return self._request.cancellation_token.is_cancelled()

    async def _close_runner_once(self) -> None:
        """幂等关闭 Runner。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常；close 失败只记录 warning。
        """

        if self._closed:
            return
        self._closed = True
        try:
            await self._runner.close()
        except Exception as exc:
            _LOGGER.warning(
                "agent.runner_close_failed run_id=%s exc_type=%s",
                self._request.run_id,
                type(exc).__name__,
            )

    def _log_iteration_decision(
        self,
        *,
        decision: _IterationDecision,
        iteration_id: str,
        iteration_index: int,
    ) -> None:
        """记录当前 iteration 分类后的主路径决策。

        :param decision: 分类结果。
        :param iteration_id: 当前迭代 id。
        :param iteration_index: 当前迭代序号。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if isinstance(decision, _FinalDecision):
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "engine.agent.iteration_decision session_id=%s run_id=%s "
                "iteration_id=%s iteration_index=%s decision=final "
                "finish_reason=%s filtered=%s degraded=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                iteration_index,
                decision.finish_reason.value,
                decision.filtered,
                decision.degraded,
            )
            return
        if isinstance(decision, _ToolCallsDecision):
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "engine.agent.iteration_decision session_id=%s run_id=%s "
                "iteration_id=%s iteration_index=%s decision=tool_calls "
                "tool_call_count=%s",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                iteration_index,
                len(decision.tool_calls),
            )
            return
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "engine.agent.iteration_decision session_id=%s run_id=%s "
            "iteration_id=%s iteration_index=%s decision=failed "
            "error_code=%s recoverable=%s",
            self._request.session_id,
            self._request.run_id,
            iteration_id,
            iteration_index,
            decision.error_code,
            decision.recoverable,
        )

    def _log_runner_call_completed(
        self,
        *,
        iteration_id: str,
        iteration_index: int,
    ) -> RunFailedData | None:
        """记录 Runner 调用完成边界。

        :param iteration_id: 当前迭代 id。
        :param iteration_index: 当前迭代序号。
        :returns: 状态缺失时返回受控失败 data，否则返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        state = self._last_iteration_state
        if state is None:
            _LOGGER.critical(
                "engine.agent.missing_iteration_state session_id=%s "
                "run_id=%s iteration_id=%s iteration_index=%s "
                "runner_call_completed=true",
                self._request.session_id,
                self._request.run_id,
                iteration_id,
                iteration_index,
            )
            return RunFailedData(
                error_code=_ERROR_MISSING_TERMINAL,
                message=_MISSING_TERMINAL_MESSAGE,
                recoverable=False,
            )
        finish_reason = (
            state.finish_reason.value
            if state.finish_reason is not None
            else None
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "engine.agent.runner_call_completed session_id=%s run_id=%s "
            "iteration_id=%s iteration_index=%s done_seen=%s "
            "finish_reason=%s tool_call_signal_seen=%s tool_call_count=%s "
            "has_failure_candidate=%s",
            self._request.session_id,
            self._request.run_id,
            iteration_id,
            iteration_index,
            state.done_seen,
            finish_reason,
            state.tool_call_signal_seen,
            _tool_call_count(state.tool_calls),
            state.failure_candidate is not None,
        )
        return None


async def run_agent_messages(
    request: AgentRunRequest,
) -> AsyncGenerator[EngineEvent, None]:
    """运行 Agent 并流式返回 EngineEvent。

    :param request: Agent run 请求。
    :returns: EngineEvent 异步生成器。调用方必须迭代至生成器结束；若
        提前停止消费，必须显式调用 ``aclose()``，以触发 Runner 关闭
        与 run-scoped 资源收尾。:func:`run_agent_and_wait` 会完整消费
        本生成器。
    :raises asyncio.CancelledError: 外层 task 被取消时透传。
    :raises Exception: Runner 构造失败时透传。
    """

    runner = _build_runner(request)
    agent = _AsyncAgent(request=request, runner=runner)
    events = agent.run_messages()
    try:
        async for event in events:
            yield event
    finally:
        await events.aclose()


async def run_agent_and_wait(request: AgentRunRequest) -> AgentRunResult:
    """运行 Agent 并等待终态结果。

    :param request: Agent run 请求。
    :returns: Agent run 终态 outcome。
    :raises asyncio.CancelledError: 外层 task 被取消时透传。
    :raises Exception: Runner 构造失败时透传。
    """

    terminal: EngineEvent | None = None
    async for event in run_agent_messages(request):
        if event.type in {
            EngineEventType.FINAL_ANSWER,
            EngineEventType.RUN_FAILED,
            EngineEventType.RUN_CANCELLED,
            EngineEventType.RUN_SUSPENDED,
        }:
            terminal = event

    if terminal is None:
        _LOGGER.critical(
            "engine.agent.missing_terminal session_id=%s run_id=%s",
            request.session_id,
            request.run_id,
        )
        return EngineRunOutcomeFailed(
            session_id=request.session_id,
            run_id=request.run_id,
            error_code=_ERROR_MISSING_TERMINAL,
            message=_MISSING_TERMINAL_MESSAGE,
            recoverable=False,
        )

    data = terminal.data
    if terminal.type is EngineEventType.FINAL_ANSWER and isinstance(
        data, FinalAnswerData
    ):
        return EngineRunOutcomeFinalAnswer(
            session_id=terminal.session_id,
            run_id=terminal.run_id,
            content=data.content,
            filtered=data.filtered,
            degraded=data.degraded,
            finish_reason=data.finish_reason,
        )
    if terminal.type is EngineEventType.RUN_FAILED and isinstance(
        data, RunFailedData
    ):
        return EngineRunOutcomeFailed(
            session_id=terminal.session_id,
            run_id=terminal.run_id,
            error_code=data.error_code,
            message=data.message,
            recoverable=data.recoverable,
        )
    if terminal.type is EngineEventType.RUN_CANCELLED and isinstance(
        data, RunCancelledData
    ):
        return EngineRunOutcomeCancelled(
            session_id=terminal.session_id,
            run_id=terminal.run_id,
            reason=data.reason,
            requested_at=data.requested_at,
            accepted_at=data.accepted_at,
            finished_at=data.finished_at,
        )
    return EngineRunOutcomeFailed(
        session_id=request.session_id,
        run_id=request.run_id,
        error_code=_ERROR_UNEXPECTED_SUSPENDED,
        message="run_suspended is not supported by phase3 agent run loop",
        recoverable=False,
    )


__all__ = ["run_agent_messages", "run_agent_and_wait"]
