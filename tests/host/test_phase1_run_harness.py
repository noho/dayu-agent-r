"""Host P1 最小 Run harness 行为测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

import dayu.engine.agent as agent_module
from dayu.contracts.tool_call import ToolCallRequest, ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    AgentMessage,
    AgentMessageRole,
    AgentPolicy,
    AgentRunRequest,
    FinishReason,
    GeminiToolCallState,
    RunFailedData,
    RunnerCallOptions,
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerSpec,
    RunnerToolCallsCompletedData,
    ToolFunctionSchema,
    ToolMessage,
    ToolParametersSchema,
    ToolResultAcceptedData,
    ToolSchema,
    UserMessage,
)
from dayu.host import (
    RunEventKind,
    RunEventSource,
    RunEvent,
    RunEventCursor,
    RunEventType,
    RunInput,
    RunOptions,
    RunState,
    StartRunRequest,
    get_run_result,
    start_run,
)
from dayu.host._event_translation import terminal_result_from_event
from dayu.host._proxy import LocalProxy
from dayu.host._run_harness import LocalRunHarness
from dayu.host._worker import EngineWorker
from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore

_BACKGROUND_START_SPIN_LIMIT: int = 20
_BACKGROUND_START_SLEEP_SECONDS: float = 0.0


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _ScriptedRunner:
    """按调用次数产出 RunnerEvent 的 fake Runner。"""

    scripts: tuple[tuple[RunnerEvent, ...], ...]
    supports_tools: bool = True
    call_count: int = 0
    close_count: int = 0
    tools_seen: list[tuple[ToolSchema, ...]] = field(default_factory=list)
    messages_seen: list[tuple[AgentMessage, ...]] = field(default_factory=list)
    release_after_first_event: _AsyncReleaseGate | None = None

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用参数。
        :param tools: 本轮工具 schema。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.messages_seen.append(tuple(messages))
        self.tools_seen.append(tuple(tools))
        script_index = self.call_count
        self.call_count += 1
        if script_index >= len(self.scripts):
            return self._iter_events(())
        return self._iter_events(self.scripts[script_index])

    def is_supports_tool_calling(self) -> bool:
        """返回是否支持工具调用。

        :returns: 支持返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.supports_tools

    async def close(self) -> None:
        """记录 close 调用。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1

    async def _iter_events(
        self, events: tuple[RunnerEvent, ...]
    ) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :param events: RunnerEvent 元组。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for index, event in enumerate(events):
            yield event
            if index == 0 and isinstance(
                self.release_after_first_event, _AsyncReleaseGate
            ):
                await self.release_after_first_event.wait()


@dataclass(slots=True)
class _AsyncReleaseGate:
    """测试用异步释放门。"""

    event: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait(self) -> None:
        """等待释放。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        await self.event.wait()

    def release(self) -> None:
        """释放等待方。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.event.set()


@dataclass(slots=True)
class _RecordingToolExecutor:
    """记录请求并返回成功 outcome 的 fake ToolExecutor。"""

    requests: list[ToolExecutionRequest] = field(default_factory=list)

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行 fake add_numbers 工具。

        :param request: 工具执行请求。
        :returns: 成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"sum": 5},
                truncation=None,
                meta=None,
            )
        )


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


def _final_script(content: str) -> tuple[RunnerEvent, ...]:
    """构造最终回答脚本。

    :param content: 最终回答正文。
    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=content,
                reasoning_content=None,
                finish_reason=FinishReason.STOP,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.STOP),
        ),
    )


def _tool_script() -> tuple[RunnerEvent, ...]:
    """构造工具调用脚本。

    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content="reason",
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(tool_calls=(_tool_call(),)),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS),
        ),
    )


def _tool_call() -> ToolCallRequest:
    """构造 add_numbers 工具调用请求。

    :returns: ToolCallRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id="tc_1",
        name="add_numbers",
        arguments={"a": 2, "b": 3},
        index_in_iteration=0,
        provider_state=GeminiToolCallState(thought_signature="sig"),
    )


def _schema() -> ToolSchema:
    """构造 add_numbers 工具 schema。

    :returns: ToolSchema。
    :raises Exception: 不主动抛出异常。
    """

    return ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="add_numbers",
            description="add two numbers",
            parameters=ToolParametersSchema(
                type="object",
                properties={},
                required=(),
                additional_properties=False,
            ),
        ),
    )


def _request(
    *,
    run_id: str = "host_run",
    disable_tools: bool = True,
    tool_schemas: tuple[ToolSchema, ...] = (),
) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param run_id: Run id。
    :param disable_tools: 是否禁用工具。
    :param tool_schemas: 工具 schema 元组。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="host_session",
        run_id=run_id,
        input=RunInput(
            messages=(
                UserMessage(
                    role=AgentMessageRole.USER,
                    content="hello",
                ),
            )
        ),
        options=RunOptions(
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
                max_iterations=3,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=disable_tools,
            tool_schemas=tool_schemas,
        ),
    )


async def _collect(stream_events: AsyncIterator[RunEvent]) -> list[RunEvent]:
    """收集 Host RunEvent。

    :param stream_events: RunEvent 异步流。
    :returns: RunEvent 列表。
    :raises Exception: 透传事件流异常。
    """

    events: list[RunEvent] = []
    async for event in stream_events:
        events.append(event)
    return events


async def _wait_for_runner_call(runner: _ScriptedRunner) -> None:
    """等待后台 task 触发 Runner call。

    :param runner: fake runner。
    :returns: 无返回值。
    :raises AssertionError: 等待后仍未触发时抛出。
    """

    for _ in range(_BACKGROUND_START_SPIN_LIMIT):
        if runner.call_count > 0:
            return
        await asyncio.sleep(_BACKGROUND_START_SLEEP_SECONDS)
    raise AssertionError("runner call was not started")


@pytest.mark.asyncio
async def test_public_start_run_streams_translated_engine_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public start_run 经 Host 入口调用 Engine 并翻译事件。"""

    runner = _ScriptedRunner(scripts=(_final_script("你好"),))

    def fake_build_runner(request: AgentRunRequest) -> _ScriptedRunner:
        """返回 fake runner。

        :param request: Engine AgentRunRequest；测试不读取该对象。
        :returns: fake runner。
        :raises Exception: 不主动抛出异常。
        """

        return runner

    monkeypatch.setattr(agent_module, "_build_runner", fake_build_runner)

    stream = await start_run(_request(run_id="host_run_public_stream"))
    events = await _collect(stream.events)

    assert stream.handle.state is RunState.RUNNING
    assert stream.handle.event_cursor.sequence == -1
    assert [event.cursor.sequence for event in events] == list(range(len(events)))
    assert events[-1].type is RunEventType.FINAL_ANSWER
    result = terminal_result_from_event(events[-1])
    assert result is not None
    assert result.run_id == "host_run_public_stream"
    assert result.session_id == "host_session"
    stored_result = await get_run_result("host_run_public_stream")
    assert stored_result == result
    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_start_run_eagerly_starts_before_event_stream_is_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """await start_run 返回后即启动后台执行，不能等 async for 才启动。"""

    gate = _AsyncReleaseGate()
    runner = _ScriptedRunner(
        scripts=(_final_script("你好"),),
        release_after_first_event=gate,
    )

    def fake_build_runner(request: AgentRunRequest) -> _ScriptedRunner:
        """返回 fake runner。

        :param request: Engine AgentRunRequest；测试不读取该对象。
        :returns: fake runner。
        :raises Exception: 不主动抛出异常。
        """

        return runner

    monkeypatch.setattr(agent_module, "_build_runner", fake_build_runner)

    stream = await start_run(_request(run_id="host_run_eager_start"))
    await _wait_for_runner_call(runner)

    assert runner.call_count == 1
    gate.release()
    events = await _collect(stream.events)
    assert events[-1].type is RunEventType.FINAL_ANSWER


@pytest.mark.asyncio
async def test_local_harness_supports_tool_call_fake_executor_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """内部 harness 覆盖普通 tool-call fake executor smoke。"""

    runner = _ScriptedRunner(scripts=(_tool_script(), _final_script("5")))

    def fake_build_runner(request: AgentRunRequest) -> _ScriptedRunner:
        """返回 fake runner。

        :param request: Engine AgentRunRequest；测试不读取该对象。
        :returns: fake runner。
        :raises Exception: 不主动抛出异常。
        """

        return runner

    monkeypatch.setattr(agent_module, "_build_runner", fake_build_runner)
    executor = _RecordingToolExecutor()
    harness = LocalRunHarness(
        proxy=LocalProxy(worker=EngineWorker(tool_executor=executor)),
        memory_store=FakeInMemoryConversationMemoryStore(),
    )

    stream = await harness.start_run(
        _request(disable_tools=False, tool_schemas=(_schema(),))
    )
    events = await _collect(stream.events)

    assert RunEventType.TOOL_CALL_REQUESTED in {event.type for event in events}
    assert RunEventType.TOOL_RESULT_ACCEPTED in {event.type for event in events}
    assert events[-1].type is RunEventType.FINAL_ANSWER
    assert len(executor.requests) == 1
    assert executor.requests[0].context.run_id == "host_run"
    assert executor.requests[0].context.session_id == "host_session"
    assert runner.tools_seen[0] == (_schema(),)
    accepted = [
        event for event in events if event.type is RunEventType.TOOL_RESULT_ACCEPTED
    ]
    assert len(accepted) == 1
    assert isinstance(accepted[0].data, ToolResultAcceptedData)
    assert isinstance(runner.messages_seen[1][-1], ToolMessage)
    assert json.loads(runner.messages_seen[1][-1].content) == {"sum": 5}


def test_terminal_result_maps_failed_cancelled_and_suspended() -> None:
    """终态翻译 helper 覆盖非成功终态。"""

    failed = RunEvent(
        run_id="run",
        session_id="session",
        cursor=RunEventCursor(sequence=1),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_FAILED,
        occurred_at=_utc_now(),
        data=RunFailedData(
            error_code="failed",
            message="failed",
            recoverable=False,
        ),
        source_engine_event_id="engine_failed",
    )

    assert terminal_result_from_event(failed) is not None


def test_terminal_result_rejects_mismatched_terminal_data() -> None:
    """终态翻译 helper 对类型不匹配的 data 抛出明确异常。"""

    event = RunEvent(
        run_id="run",
        session_id="session",
        cursor=RunEventCursor(sequence=1),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc_now(),
        data=RunFailedData(
            error_code="failed",
            message="failed",
            recoverable=False,
        ),
        source_engine_event_id="engine_failed",
    )

    with pytest.raises(TypeError, match="FinalAnswerData"):
        terminal_result_from_event(event)
