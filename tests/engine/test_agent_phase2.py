"""Phase 2 Agent run loop 行为测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

import dayu.engine.agent as agent_module
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine.agent import _AsyncAgent
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    TERMINAL_ENGINE_EVENT_TYPES,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    UserMessage,
)
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.contracts.tool_call import ToolCallRequest
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _Token:
    """测试用 cancellation token。"""

    cancelled: bool = False
    reason: str | None = None
    requested: datetime | None = None

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已取消返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因或 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self.reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 请求时间或 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self.requested

    def trigger(self, reason: str = "test_cancelled") -> None:
        """触发取消。

        :param reason: 取消原因。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.cancelled = True
        self.reason = reason
        self.requested = _utc_now()


class _NoopToolExecutor:
    """测试用 no-op ToolExecutor。"""

    async def execute(
        self, request: ToolExecutionRequest
    ) -> ToolExecutionOutcome:
        """返回失败 outcome，防止 Phase 2 误执行工具。

        :param request: 工具执行请求。
        :returns: 失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="unexpected_tool_execution",
                message=request.call.name,
                hint=None,
                meta=None,
            )
        )


@dataclass(slots=True)
class _ScriptedRunner:
    """按脚本产出 RunnerEvent 的 fake Runner。"""

    events: tuple[RunnerEvent, ...]
    token_to_cancel_after_event_index: int | None = None
    token: _Token | None = None
    raise_on_call: bool = False
    raise_on_close: bool = False
    block_after_first_event: bool = False
    close_count: int = 0
    call_count: int = 0
    close_completed_at: datetime | None = None
    tools_seen: tuple[ToolSchema, ...] = ()
    release_event: asyncio.Event = field(default_factory=asyncio.Event)

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用选项。
        :param tools: 暴露给模型的工具 schema。
        :returns: RunnerEvent 异步流。
        :raises RuntimeError: 配置 ``raise_on_call`` 时抛出。
        """

        self.call_count += 1
        self.tools_seen = tuple(tools)
        return self._iter_events()

    def is_supports_tool_calling(self) -> bool:
        """声明支持工具调用。

        :returns: ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """记录 close 调用。

        :returns: 无返回值。
        :raises RuntimeError: 配置 ``raise_on_close`` 时抛出。
        """

        self.close_count += 1
        self.close_completed_at = _utc_now()
        if self.raise_on_close:
            raise RuntimeError("close failed")

    async def _iter_events(self) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :returns: RunnerEvent 异步流。
        :raises RuntimeError: 配置 ``raise_on_call`` 时抛出。
        """

        if self.raise_on_call:
            raise RuntimeError("runner exploded")
        for index, event in enumerate(self.events):
            yield event
            if (
                self.token_to_cancel_after_event_index is not None
                and self.token is not None
                and index == self.token_to_cancel_after_event_index
            ):
                self.token.trigger()
            if index == 0 and self.block_after_first_event:
                await self.release_event.wait()


def _event(event_type: RunnerEventType, data: RunnerEventData) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: RunnerEventType。
    :param data: RunnerEvent data。
    :returns: RunnerEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerEvent(
        type=event_type,
        data=data,
        occurred_at=_utc_now(),
    )


def _request(
    *,
    token: _Token | None = None,
    max_iterations: int = 1,
    tool_schemas: tuple[ToolSchema, ...] = (),
) -> AgentRunRequest:
    """构造 AgentRunRequest。

    :param token: cancellation token。
    :param max_iterations: 最大迭代次数。
    :param tool_schemas: 工具 schema。
    :returns: AgentRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    actual_token = token or _Token()
    return AgentRunRequest(
        run_id="run_phase2",
        session_id="session_phase2",
        messages=(
            UserMessage(role=AgentMessageRole.USER, content="hello"),
        ),
        stream=True,
        disable_tools=True,
        runner_spec=RunnerSpec(
            provider="openai",
            model="model",
            endpoint="https://example.test/v1/chat/completions",
            api_key_ref="TEST_KEY",
            headers={},
            supports_tool_calling=True,
            supports_streaming=True,
            supports_stream_usage=False,
            default_timeout_seconds=30.0,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=True,
        ),
        agent_policy=AgentPolicy(
            max_iterations=max_iterations,
            continuation_max_attempts=3,
            allow_tool_calls=True,
        ),
        tool_schemas=tool_schemas,
        tool_executor=_NoopToolExecutor(),
        cancellation_token=actual_token,
    )


async def _collect(agent: _AsyncAgent) -> list[EngineEvent]:
    """收集 Agent 事件流。

    :param agent: 私有 Agent。
    :returns: EngineEvent 列表。
    :raises Exception: 透传 Agent 运行异常。
    """

    events: list[EngineEvent] = []
    async for event in agent.run_messages():
        events.append(event)
    return events


def _final_event(events: Sequence[EngineEvent]) -> EngineEvent:
    """返回最后一个事件。

    :param events: EngineEvent 序列。
    :returns: 最后一个事件。
    :raises AssertionError: 事件列表为空时抛出。
    """

    assert events
    return events[-1]


def _assert_single_terminal_at_end(events: Sequence[EngineEvent]) -> None:
    """断言 EngineEvent 流只有一个终态事件且终态位于最后。

    :param events: 完整收集到的 EngineEvent 序列。
    :returns: 无返回值。
    :raises AssertionError: 事件流为空、终态数量不为一或终态不是最后一个时抛出。
    """

    assert events
    terminal_events = [
        event for event in events if event.type in TERMINAL_ENGINE_EVENT_TYPES
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0] is events[-1]


@pytest.mark.asyncio
async def test_success_run_lifts_runner_events_and_agent_final() -> None:
    """无工具成功 run 会提升 RunnerEvent 并由 Agent 产出 final_answer。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="你"),
            ),
            _event(
                RunnerEventType.RUNNER_REASONING_DELTA,
                RunnerReasoningDeltaData(delta="想"),
            ),
            _event(
                RunnerEventType.RUNNER_USAGE_RECORDED,
                RunnerUsageRecordedData(
                    prompt_tokens=1,
                    completion_tokens=2,
                    total_tokens=3,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="你好",
                    reasoning_content="想",
                    finish_reason=FinishReason.STOP,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.sequence for event in events] == list(range(len(events)))
    assert len({event.event_id for event in events}) == len(events)
    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.RUNNER_CONTENT_DELTA,
        EngineEventType.RUNNER_REASONING_DELTA,
        EngineEventType.RUNNER_USAGE_RECORDED,
        EngineEventType.RUNNER_CONTENT_COMPLETED,
        EngineEventType.RUNNER_DONE,
        EngineEventType.FINAL_ANSWER,
    ]
    final = _final_event(events)
    assert isinstance(final.data, FinalAnswerData)
    assert final.data.content == "你好"
    assert final.data.degraded is False
    assert runner.close_count == 1
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_phase2_passes_empty_tools_even_when_request_has_schema() -> None:
    """Phase 2 不把 request.tool_schemas 暴露给 Runner。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="lookup",
            description="lookup",
            parameters=ToolParametersSchema(
                type="object",
                properties={},
                required=(),
                additional_properties=False,
            ),
        ),
    )
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                    finish_reason=FinishReason.STOP,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP),
            ),
        )
    )

    await _collect(
        _AsyncAgent(
            request=_request(tool_schemas=(schema,)),
            runner=runner,
        )
    )

    assert runner.tools_seen == ()


@pytest.mark.asyncio
async def test_protocol_error_and_error_done_maps_to_run_failed() -> None:
    """provider protocol error 会提升协议错误并收口 run_failed。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.PROVIDER_PROTOCOL_ERROR,
                RunnerProtocolErrorData(
                    error_code="bad_sse",
                    message="bad stream",
                    provider_request_id="req_1",
                    raw_payload={"type": "bad"},
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert events[-2].type is EngineEventType.RUNNER_DONE
    terminal = _final_event(events)
    assert terminal.type is EngineEventType.RUN_FAILED
    assert isinstance(terminal.data, RunFailedData)
    assert terminal.data.error_code == "bad_sse"
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_http_error_maps_to_run_failed_without_extra_engine_event() -> None:
    """HTTP error 记录失败候选，经 runner_done 收口 run_failed。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
                    http_status=429,
                    message="rate limited",
                    provider_request_id=None,
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.RUNNER_DONE,
        EngineEventType.RUN_FAILED,
    ]
    assert isinstance(events[-1].data, RunFailedData)
    assert events[-1].data.error_code == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_bare_error_done_maps_to_specific_run_failed() -> None:
    """裸 RunnerDone(ERROR) 不能落入 final_answer。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    terminal = _final_event(events)
    assert terminal.type is EngineEventType.RUN_FAILED
    assert isinstance(terminal.data, RunFailedData)
    assert terminal.data.error_code == "runner_error_done_without_detail"


@pytest.mark.asyncio
async def test_runner_exception_maps_to_run_failed_and_closes() -> None:
    """Runner 普通异常映射 run_failed 且 close Runner。"""

    runner = _ScriptedRunner(events=(), raise_on_call=True)
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert _final_event(events).type is EngineEventType.RUN_FAILED
    assert isinstance(events[-1].data, RunFailedData)
    assert events[-1].data.error_code == "runner_exception"
    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_cancelled_before_run_closes_then_emits_cancelled() -> None:
    """入口已取消时不调用 Runner，但先 close 再产出 run_cancelled。"""

    token = _Token()
    token.trigger()
    runner = _ScriptedRunner(events=())
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    terminal = _final_event(events)
    assert terminal.type is EngineEventType.RUN_CANCELLED
    assert isinstance(terminal.data, RunCancelledData)
    assert runner.call_count == 0
    assert runner.close_count == 1
    assert runner.close_completed_at is not None
    assert terminal.data.finished_at >= runner.close_completed_at
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_runner_cancelled_naturally_without_done_maps_cancelled() -> None:
    """Runner 因取消自然结束且无 done 时由 Agent 收口 run_cancelled。"""

    token = _Token()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="partial"),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED
    assert EngineEventType.FINAL_ANSWER not in {event.type for event in events}


@pytest.mark.asyncio
async def test_cancel_before_final_answer_wins_over_final() -> None:
    """final_answer 前取消优先于最终回答。"""

    token = _Token()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="should not final",
                    reasoning_content=None,
                    finish_reason=FinishReason.STOP,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED
    assert EngineEventType.FINAL_ANSWER not in {event.type for event in events}


@pytest.mark.asyncio
async def test_provider_error_and_cancel_same_run_cancel_wins() -> None:
    """provider error 与取消同时出现时取消优先于 failure terminal。"""

    token = _Token()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.PROVIDER_PROTOCOL_ERROR,
                RunnerProtocolErrorData(
                    error_code="bad",
                    message="bad",
                    provider_request_id=None,
                    raw_payload=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED


@pytest.mark.asyncio
async def test_http_error_and_cancel_same_run_cancel_wins() -> None:
    """HTTP error 后若取消同时到达，取消优先于 failure terminal。"""

    token = _Token()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.SERVER_ERROR,
                    http_status=503,
                    message="server busy",
                    provider_request_id=None,
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED


@pytest.mark.asyncio
async def test_close_error_does_not_override_terminal() -> None:
    """Runner close 失败不覆盖已确定 terminal。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                    finish_reason=FinishReason.STOP,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP),
            ),
        ),
        raise_on_close=True,
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert _final_event(events).type is EngineEventType.FINAL_ANSWER
    assert runner.close_count == 1
    assert _terminal_count(events) == 1


@pytest.mark.asyncio
async def test_tool_call_delta_and_completed_fail_closed() -> None:
    """Phase 2 收到工具调用事件会 fail closed，不产出 ToolCallRequested。"""

    completed_runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
                RunnerToolCallsCompletedData(
                    tool_calls=(
                        ToolCallRequest(
                            tool_call_id="tc_1",
                            name="lookup",
                            arguments={},
                            index_in_iteration=0,
                            provider_state=None,
                        ),
                    )
                ),
            ),
        )
    )
    delta_runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_TOOL_CALL_DELTA,
                RunnerToolCallDeltaData(
                    tool_call_index=0,
                    tool_call_id="tc_1",
                    name_delta="lookup",
                    arguments_delta="{}",
                ),
            ),
        )
    )

    for runner in (completed_runner, delta_runner):
        events = await _collect(_AsyncAgent(request=_request(), runner=runner))
        assert _final_event(events).type is EngineEventType.RUN_FAILED
        assert isinstance(events[-1].data, RunFailedData)
        assert events[-1].data.error_code == "runner_abnormal_stop"
        assert EngineEventType.TOOL_CALL_REQUESTED not in {
            event.type for event in events
        }


@pytest.mark.asyncio
async def test_length_and_content_filter_final_boundaries() -> None:
    """LENGTH 无续写预算时降级 final；CONTENT_FILTER 不消费 continuation。"""

    for finish_reason in (FinishReason.LENGTH, FinishReason.CONTENT_FILTER):
        runner = _ScriptedRunner(
            events=(
                _event(
                    RunnerEventType.RUNNER_CONTENT_COMPLETED,
                    RunnerContentCompletedData(
                        content="partial",
                        reasoning_content=None,
                        finish_reason=finish_reason,
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=finish_reason),
                ),
            )
        )
        events = await _collect(_AsyncAgent(request=_request(), runner=runner))
        assert _final_event(events).type is EngineEventType.FINAL_ANSWER
        assert isinstance(events[-1].data, FinalAnswerData)
        assert events[-1].data.finish_reason is finish_reason
        assert events[-1].data.filtered is (
            finish_reason is FinishReason.CONTENT_FILTER
        )
        assert events[-1].data.degraded is True
        assert runner.call_count == 1


@pytest.mark.asyncio
async def test_abnormal_stop_and_max_iterations_fail() -> None:
    """无 done 异常结束与 max_iterations<1 都收口 run_failed。"""

    abnormal = await _collect(
        _AsyncAgent(
            request=_request(),
            runner=_ScriptedRunner(
                events=(
                    _event(
                        RunnerEventType.RUNNER_CONTENT_DELTA,
                        RunnerContentDeltaData(delta="partial"),
                    ),
                )
            ),
        )
    )
    assert isinstance(abnormal[-1].data, RunFailedData)
    assert abnormal[-1].data.error_code == "runner_abnormal_stop"

    exceeded = await _collect(
        _AsyncAgent(
            request=_request(max_iterations=0),
            runner=_ScriptedRunner(events=()),
        )
    )
    assert isinstance(exceeded[-1].data, RunFailedData)
    assert exceeded[-1].data.error_code == "max_iterations_exceeded"


@pytest.mark.asyncio
async def test_private_agent_concurrent_run_fail_fast() -> None:
    """同一私有 Agent 实例并发运行 fail-fast。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="hold"),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP),
            ),
        ),
        block_after_first_event=True,
    )
    agent = _AsyncAgent(request=_request(), runner=runner)
    first_event_seen = asyncio.Event()

    async def consume_first_run() -> None:
        """消费第一次运行。

        :returns: 无返回值。
        :raises Exception: 透传 Agent 运行异常。
        """

        async for event in agent.run_messages():
            if event.type is EngineEventType.RUNNER_CONTENT_DELTA:
                first_event_seen.set()

    task = asyncio.create_task(consume_first_run())
    await first_event_seen.wait()
    with pytest.raises(RuntimeError):
        async for _event_item in agent.run_messages():
            pass
    runner.release_event.set()
    await task


@pytest.mark.asyncio
async def test_outer_asyncio_cancelled_error_propagates_and_closes() -> None:
    """外层 task cancel 必须透传 asyncio.CancelledError，并关闭 Runner。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="hold"),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP),
            ),
        ),
        block_after_first_event=True,
    )
    agent = _AsyncAgent(request=_request(), runner=runner)
    first_event_seen = asyncio.Event()

    async def consume_until_cancelled() -> None:
        """消费事件流，直到外层 task 取消。

        :returns: 无返回值。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        async for event in agent.run_messages():
            if event.type is EngineEventType.RUNNER_CONTENT_DELTA:
                first_event_seen.set()

    task = asyncio.create_task(consume_until_cancelled())
    await first_event_seen.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_run_agent_and_wait_maps_final_failed_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_agent_and_wait 映射 final / failed / cancelled 三类终态。"""

    request = _request()
    runners = [
        _ScriptedRunner(
            events=(
                _event(
                    RunnerEventType.RUNNER_CONTENT_COMPLETED,
                    RunnerContentCompletedData(
                        content="ok",
                        reasoning_content=None,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=FinishReason.STOP),
                ),
            )
        ),
        _ScriptedRunner(
            events=(
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=FinishReason.ERROR),
                ),
            )
        ),
        _ScriptedRunner(events=()),
    ]
    token = _Token(cancelled=True, reason="stop", requested=_utc_now())
    requests = [request, request, _request(token=token)]

    for runner, current_request, expected_type in zip(
        runners,
        requests,
        (
            EngineRunOutcomeFinalAnswer,
            EngineRunOutcomeFailed,
            EngineRunOutcomeCancelled,
        ),
        strict=True,
    ):
        monkeypatch.setattr(
            agent_module,
            "_build_runner",
            lambda ignored_request, selected_runner=runner: selected_runner,
        )
        result = await agent_module.run_agent_and_wait(current_request)
        assert isinstance(result, expected_type)


@pytest.mark.asyncio
async def test_run_agent_and_wait_rejects_unexpected_suspended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUN_SUSPENDED 不是 Phase 2 可用能力，wait 入口防御性失败。"""

    async def fake_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """产出意外 suspended terminal。

        :param request: Agent run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            event_id="run_phase2:0",
            sequence=0,
            occurred_at=_utc_now(),
            session_id=request.session_id,
            run_id=request.run_id,
            type=EngineEventType.RUN_SUSPENDED,
            data=RunSuspendedData(reason="awaiting", resume_hint=None),
            metadata=None,
        )

    monkeypatch.setattr(agent_module, "run_agent_messages", fake_messages)
    result = await agent_module.run_agent_and_wait(_request())

    assert isinstance(result, EngineRunOutcomeFailed)
    assert result.error_code == "unexpected_suspended_in_phase3"


def _terminal_count(events: Sequence[EngineEvent]) -> int:
    """统计 terminal 事件数。

    :param events: EngineEvent 序列。
    :returns: terminal 数量。
    :raises Exception: 不主动抛出异常。
    """

    return sum(1 for event in events if event.type in TERMINAL_ENGINE_EVENT_TYPES)
