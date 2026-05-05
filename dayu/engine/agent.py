"""Phase 2 run-scoped Agent 主链路实现。

本模块只承载 Engine 内部的无工具 Agent run loop：

- 公共调用方通过 :func:`run_agent_messages` /
  :func:`run_agent_and_wait` 使用函数式入口。
- 私有 :class:`_AsyncAgent` 负责单次 run 内的 RunnerEvent 消费、
  EngineEvent 提升、终态收口与 Runner close。
- Phase 2 不执行工具、不写 trace、不做 transcript / memory /
  continuation。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timezone

from dayu.contracts.tool_schema import ToolSchema
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.engine_events import (
    ContentCompleteData,
    ContentDeltaData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    IterationStartedData,
    ProviderProtocolErrorData,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunnerDoneEngineData,
    RunnerUsageData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

_LOGGER: logging.Logger = logging.getLogger(__name__)

_FIRST_ITERATION_INDEX: int = 0
_FIRST_ITERATION_ORDINAL: int = 1
_DEFAULT_CANCEL_REASON: str = "cancelled"
_ERROR_MAX_ITERATIONS_EXCEEDED: str = "max_iterations_exceeded"
_ERROR_RUNNER_EXCEPTION: str = "runner_exception"
_ERROR_PROTOCOL_ERROR_ABNORMAL_STOP: str = "protocol_error_abnormal_stop"
_ERROR_RUNNER_ABNORMAL_STOP: str = "runner_abnormal_stop"
_ERROR_RUNNER_ERROR_DONE_WITHOUT_DETAIL: str = (
    "runner_error_done_without_detail"
)
_ERROR_TOOL_CALL_NOT_SUPPORTED: str = "tool_call_not_supported_in_phase2"
_ERROR_MISSING_TERMINAL: str = "missing_terminal"
_ERROR_UNEXPECTED_SUSPENDED: str = "unexpected_suspended_in_phase2"
_RUNNER_ERROR_WITHOUT_DETAIL_MESSAGE: str = (
    "runner finished with error without detail"
)
_RUNNER_ABNORMAL_STOP_MESSAGE: str = "runner stopped without done event"
_MAX_ITERATIONS_EXCEEDED_MESSAGE: str = (
    "agent policy max_iterations must be at least 1 in phase2"
)
_TOOL_CALL_NOT_SUPPORTED_MESSAGE: str = (
    "tool calling is not supported by phase2 agent run loop"
)
_MISSING_TERMINAL_MESSAGE: str = "agent event stream ended without terminal"


def _utc_now() -> datetime:
    """返回当前 UTC 时间。

    :returns: 带 ``timezone.utc`` 的当前时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _build_runner(request: AgentRunRequest) -> AsyncRunner:
    """根据请求构造当前 Phase 2 Runner。

    Phase 2 只装配 OpenAI-compatible Runner；后续如果需要其它 Runner，
    必须先新增明确的 runner 选择契约，而不是在本函数塞入开放插件机制。

    :param request: Agent run 请求。
    :returns: 新建的 Runner 实例。
    :raises Exception: Runner 构造失败时透传底层异常。
    """

    return AsyncOpenAIRunner(
        spec=request.runner_spec,
        cancellation_token=request.cancellation_token,
    )


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
        self._content_chunks: list[str] = []
        self._reasoning_chunks: list[str] = []
        self._completed_content: str | None = None
        self._completed_reasoning_content: str | None = None
        self._last_finish_reason: FinishReason | None = None
        self._failure_candidate: RunFailedData | None = None
        self._runner_done_seen: bool = False
        self._tool_call_seen: bool = False

    async def run_messages(self) -> AsyncIterator[EngineEvent]:
        """运行 Agent 并产出 EngineEvent 流。

        :returns: EngineEvent 异步流。
        :raises RuntimeError: 同一 Agent 实例并发运行时抛出。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        self._acquire_run_slot()
        try:
            if self._is_cancelled():
                yield await self._make_cancelled_terminal_with_close()
                return

            async for event in self._run_once():
                yield event
                if event.type in {
                    EngineEventType.FINAL_ANSWER,
                    EngineEventType.RUN_FAILED,
                    EngineEventType.RUN_CANCELLED,
                }:
                    return

            if not self._terminal_seen:
                if self._is_cancelled():
                    yield await self._make_cancelled_terminal_with_close()
                    return
                yield self._make_terminal_failed(
                    RunFailedData(
                        error_code=_ERROR_MISSING_TERMINAL,
                        message=_MISSING_TERMINAL_MESSAGE,
                        recoverable=False,
                    )
                )
        finally:
            await self._close_runner_once()
            self._release_run_slot()

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

    async def _run_once(self) -> AsyncIterator[EngineEvent]:
        """执行 Phase 2 单轮无工具主链路。

        :returns: EngineEvent 异步流。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        iteration_id = self._iteration_id()
        yield self._make_event(
            event_type=EngineEventType.ITERATION_STARTED,
            data=IterationStartedData(
                iteration_id=iteration_id,
                iteration_index=_FIRST_ITERATION_INDEX,
                message_count=len(self._request.messages),
            ),
            occurred_at=_utc_now(),
        )

        if self._request.agent_policy.max_iterations < 1:
            yield await self._make_failed_or_cancelled_terminal_with_close(
                RunFailedData(
                    error_code=_ERROR_MAX_ITERATIONS_EXCEEDED,
                    message=_MAX_ITERATIONS_EXCEEDED_MESSAGE,
                    recoverable=False,
                )
            )
            return

        if self._is_cancelled():
            yield await self._make_cancelled_terminal_with_close()
            return

        try:
            async for runner_event in self._runner.call(
                self._request.messages,
                self._request.runner_options,
                self._effective_tools(),
            ):
                engine_event = self._consume_runner_event(
                    runner_event=runner_event,
                    iteration_id=iteration_id,
                )
                if engine_event is not None:
                    yield engine_event

                terminal = await self._terminal_after_runner_event(
                    runner_event=runner_event,
                    iteration_id=iteration_id,
                )
                if terminal is not None:
                    yield terminal
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield await self._make_failed_or_cancelled_terminal_with_close(
                RunFailedData(
                    error_code=_ERROR_RUNNER_EXCEPTION,
                    message=type(exc).__name__,
                    recoverable=False,
                )
            )
            return

        if self._is_cancelled():
            yield await self._make_cancelled_terminal_with_close()
            return
        if self._failure_candidate is not None:
            yield await self._make_failed_or_cancelled_terminal_with_close(
                self._failure_candidate
            )
            return
        yield await self._make_failed_or_cancelled_terminal_with_close(
            RunFailedData(
                error_code=_ERROR_RUNNER_ABNORMAL_STOP,
                message=_RUNNER_ABNORMAL_STOP_MESSAGE,
                recoverable=False,
            )
        )

    def _consume_runner_event(
        self, *, runner_event: RunnerEvent, iteration_id: str
    ) -> EngineEvent | None:
        """消费单个 RunnerEvent 并按需提升为 EngineEvent。

        :param runner_event: Runner 产出的事件。
        :param iteration_id: 当前迭代 id。
        :returns: 需要向 Host 暴露的 EngineEvent；HTTP error 仅记录失败
            候选，返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        data = runner_event.data
        if isinstance(data, RunnerContentDeltaData):
            self._content_chunks.append(data.delta)
            return self._make_event(
                event_type=EngineEventType.RUNNER_CONTENT_DELTA,
                data=ContentDeltaData(
                    iteration_id=iteration_id, delta=data.delta
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerReasoningDeltaData):
            self._reasoning_chunks.append(data.delta)
            return self._make_event(
                event_type=EngineEventType.RUNNER_REASONING_DELTA,
                data=ReasoningDeltaData(
                    iteration_id=iteration_id, delta=data.delta
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerContentCompletedData):
            self._completed_content = data.content
            self._completed_reasoning_content = data.reasoning_content
            self._last_finish_reason = data.finish_reason
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
            self._failure_candidate = RunFailedData(
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
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerHTTPErrorData):
            self._failure_candidate = RunFailedData(
                error_code=data.error_code.value,
                message=data.message,
                recoverable=False,
            )
            return None
        if isinstance(data, RunnerDoneData):
            self._runner_done_seen = True
            self._last_finish_reason = data.finish_reason
            return self._make_event(
                event_type=EngineEventType.RUNNER_DONE,
                data=RunnerDoneEngineData(
                    iteration_id=iteration_id,
                    finish_reason=data.finish_reason,
                ),
                occurred_at=runner_event.occurred_at,
            )
        if isinstance(data, RunnerToolCallDeltaData):
            self._tool_call_seen = True
            self._failure_candidate = self._tool_call_failure()
            return None
        if isinstance(data, RunnerToolCallsCompletedData):
            self._tool_call_seen = True
            self._failure_candidate = self._tool_call_failure()
            return None
        self._failure_candidate = RunFailedData(
            error_code=_ERROR_RUNNER_EXCEPTION,
            message=(
                "runner event data did not match phase2 supported union"
            ),
            recoverable=False,
        )
        return None

    async def _terminal_after_runner_event(
        self, *, runner_event: RunnerEvent, iteration_id: str
    ) -> EngineEvent | None:
        """判断当前 RunnerEvent 后是否应收口终态。

        :param runner_event: 刚消费的 RunnerEvent。
        :param iteration_id: 当前迭代 id。
        :returns: 需要立即产出的 terminal；无需终态时返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._tool_call_seen:
            return await self._make_failed_or_cancelled_terminal_with_close(
                self._tool_call_failure()
            )
        if runner_event.type != RunnerEventType.RUNNER_DONE:
            return None

        if self._is_cancelled():
            return await self._make_cancelled_terminal_with_close()

        finish_reason = self._last_finish_reason
        if finish_reason is FinishReason.ERROR:
            return await self._make_failed_or_cancelled_terminal_with_close(
                self._failure_candidate
                or RunFailedData(
                    error_code=_ERROR_RUNNER_ERROR_DONE_WITHOUT_DETAIL,
                    message=_RUNNER_ERROR_WITHOUT_DETAIL_MESSAGE,
                    recoverable=False,
                )
            )
        if finish_reason is FinishReason.TOOL_CALLS:
            return await self._make_failed_or_cancelled_terminal_with_close(
                self._tool_call_failure()
            )
        return await self._make_final_or_cancelled_after_close(
            iteration_id=iteration_id
        )

    async def _make_final_or_cancelled_after_close(
        self, *, iteration_id: str
    ) -> EngineEvent:
        """构造最终回答或取消终态。

        :param iteration_id: 当前迭代 id。
        :returns: terminal EngineEvent。
        :raises Exception: 不主动抛出异常。
        """

        if self._is_cancelled():
            return await self._make_cancelled_terminal_with_close()
        finish_reason = self._last_finish_reason or FinishReason.STOP
        content = self._completed_content
        if content is None:
            content = "".join(self._content_chunks)
        return self._make_terminal_final(
            FinalAnswerData(
                content=content,
                filtered=finish_reason is FinishReason.CONTENT_FILTER,
                finish_reason=finish_reason,
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
            raise RuntimeError("terminal event already emitted")
        self._terminal_seen = True
        return self._make_event(
            event_type=event_type,
            data=data,
            occurred_at=_utc_now(),
        )

    def _make_event(
        self,
        *,
        event_type: EngineEventType,
        data: (
            IterationStartedData
            | ContentDeltaData
            | ReasoningDeltaData
            | ContentCompleteData
            | RunnerUsageData
            | ProviderProtocolErrorData
            | RunnerDoneEngineData
            | FinalAnswerData
            | RunFailedData
            | RunCancelledData
        ),
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

    def _iteration_id(self) -> str:
        """返回 Phase 2 第一轮 iteration id。

        :returns: 当前 run 的第一轮 iteration id。
        :raises Exception: 不主动抛出异常。
        """

        return f"{self._request.run_id}_iteration_{_FIRST_ITERATION_ORDINAL}"

    def _effective_tools(self) -> Sequence[ToolSchema]:
        """返回 Phase 2 暴露给 Runner 的工具 schema。

        Phase 2 无工具主链路始终返回空元组，不把 request.tool_schemas
        暴露给模型。

        :returns: 空工具 schema 序列。
        :raises Exception: 不主动抛出异常。
        """

        return ()

    def _tool_call_failure(self) -> RunFailedData:
        """构造 Phase 2 工具调用 fail-closed 失败 data。

        :returns: ``tool_call_not_supported_in_phase2`` 失败 data。
        :raises Exception: 不主动抛出异常。
        """

        return RunFailedData(
            error_code=_ERROR_TOOL_CALL_NOT_SUPPORTED,
            message=_TOOL_CALL_NOT_SUPPORTED_MESSAGE,
            recoverable=False,
        )

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


async def run_agent_messages(
    request: AgentRunRequest,
) -> AsyncIterator[EngineEvent]:
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
    async for event in agent.run_messages():
        yield event


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
        message="run_suspended is not supported by phase2 agent run loop",
        recoverable=False,
    )


__all__ = ["run_agent_messages", "run_agent_and_wait"]
