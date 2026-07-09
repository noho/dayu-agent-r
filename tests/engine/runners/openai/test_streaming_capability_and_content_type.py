"""流式 capability 降级与 HTTP 200 Content-Type 分流测试。"""

from __future__ import annotations

import json

from collections.abc import Sequence

import pytest

from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine.agent import _AsyncAgent
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.engine.runners.openai.runner import (
    AsyncOpenAIRunner,
    _extract_provider_request_id,
    _format_provider_request_id_headers_for_log,
    _is_sse_response,
)

from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeCancellationToken,
    FakeResponseSpec,
    FakeSession,
)


_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 5.0
_CONTINUATION_MAX_ATTEMPTS: int = 3


class _NoopToolExecutor:
    """Agent 集成测试用 no-op ToolExecutor。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回失败 outcome 批次，防止无工具路径误执行工具。

        :param request: 批式工具执行请求。
        :returns: 与输入 ``calls`` 一一对应的失败 outcome 批次。
        :raises Exception: 不主动抛出异常。
        """

        records = tuple(
            BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=ToolFailedOutcome(
                    result=ToolResultFailure(
                        ok=False,
                        error="unexpected_tool_execution",
                        message=call.name,
                        hint=None,
                        meta=None,
                    )
                ),
            )
            for call in request.calls
        )
        return BatchToolExecutionOutcome(records=records)


def _install_session(
    runner: AsyncOpenAIRunner, session: FakeSession
) -> None:
    """把 fake session 安装到 runner.HTTPClient。

    :param runner: 待安装 fake session 的 runner。
    :param session: fake HTTP session。
    :returns: 无返回值。
    """

    runner._http_client._session = session  # type: ignore[attr-defined]


def _agent_request(
    *,
    spec: RunnerSpec,
    token: FakeCancellationToken,
    stream: bool,
) -> AgentRunRequest:
    """构造 OpenAI Runner 到 Agent 的集成测试请求。

    :param spec: Runner 规格。
    :param token: cancellation token。
    :param stream: RunnerCallOptions.stream 值。
    :returns: AgentRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return AgentRunRequest(
        run_id="run_openai_provider_request_id",
        session_id="session_openai_provider_request_id",
        messages=(UserMessage(role=AgentMessageRole.USER, content="hi"),),
        disable_tools=True,
        runner_spec=spec,
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=stream,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=_CONTINUATION_MAX_ATTEMPTS,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        tool_schemas=(),
        tool_executor=_NoopToolExecutor(),
        cancellation_token=token,
    )


async def _collect(runner: AsyncOpenAIRunner) -> list[RunnerEvent]:
    """执行一次最小 runner call 并收集事件。

    :param runner: 待调用的 runner。
    :returns: RunnerEvent 列表。
    """

    messages = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for event in runner.call(
        messages=messages,
        options=make_options(stream=True),
        tools=[],
    ):
        events.append(event)
    return events


async def _collect_agent_events(
    *,
    runner: AsyncOpenAIRunner,
    spec: RunnerSpec,
    token: FakeCancellationToken,
    stream: bool,
) -> list[EngineEvent]:
    """通过 Agent 执行 OpenAI Runner 并收集 EngineEvent。

    :param runner: 已装配 fake session 的 OpenAI Runner。
    :param spec: Runner 规格。
    :param token: cancellation token。
    :param stream: RunnerCallOptions.stream 值。
    :returns: EngineEvent 列表。
    :raises Exception: 透传 Agent 运行异常。
    """

    events: list[EngineEvent] = []
    agent = _AsyncAgent(
        request=_agent_request(spec=spec, token=token, stream=stream),
        runner=runner,
    )
    async for event in agent.run_messages():
        events.append(event)
    return events


def _iteration_completed_data(
    events: Sequence[EngineEvent],
) -> IterationCompletedData:
    """从 EngineEvent 序列中取出唯一 iteration_completed data。

    :param events: EngineEvent 序列。
    :returns: iteration_completed data。
    :raises AssertionError: 找不到唯一 iteration_completed 事件时抛出。
    """

    completed_events = [
        event for event in events
        if event.type is EngineEventType.ITERATION_COMPLETED
    ]
    assert len(completed_events) == 1
    data = completed_events[0].data
    assert isinstance(data, IterationCompletedData)
    return data


def _final_answer_data(events: Sequence[EngineEvent]) -> FinalAnswerData:
    """从 EngineEvent 序列中取出最终回答 data。

    :param events: EngineEvent 序列。
    :returns: final_answer data。
    :raises AssertionError: 最后事件不是 final_answer 时抛出。
    """

    assert events[-1].type is EngineEventType.FINAL_ANSWER
    data = events[-1].data
    assert isinstance(data, FinalAnswerData)
    return data


@pytest.mark.asyncio
async def test_supports_streaming_false_downgrades_payload_to_non_stream() -> None:
    """不支持流式时，Runner 内部把 stream=True 降级为非流式请求。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(supports_streaming=False, supports_stream_usage=True),
        cancellation_token=FakeCancellationToken(),
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"ok"},"finish_reason":"stop"}]}'
            ],
        )
    )
    _install_session(runner, session)

    events = await _collect(runner)

    assert len(session.calls) == 1
    request_payload = json.loads(session.calls[0][1].decode("utf-8"))
    assert request_payload["stream"] is False
    assert "stream_options" not in request_payload
    assert isinstance(events[-1].data, RunnerDoneData)
    assert events[-1].data.finish_reason is FinishReason.STOP
    await runner.close()


def test_stream_true_unknown_content_type_is_not_sse() -> None:
    """stream=True 但非 SSE Content-Type 不再按 SSE 解析。"""

    assert _is_sse_response(content_type="text/plain", stream=True) is False
    assert (
        _is_sse_response(content_type="application/octet-stream", stream=True)
        is False
    )
    assert (
        _is_sse_response(
            content_type="Text/Event-Stream; charset=utf-8",
            stream=True,
        )
        is True
    )


def test_provider_request_id_extraction_ignores_infrastructure_headers() -> None:
    """provider_request_id 不映射基础设施 tracing header。"""

    assert (
        _extract_provider_request_id(
            (
                ("x-trace-id", "trace-id"),
                ("x-correlation-id", "correlation-id"),
                ("cf-ray", "cf-ray-id"),
                ("traceparent", "00-trace-parent"),
            )
        )
        is None
    )
    assert (
        _extract_provider_request_id(
            (
                ("x-trace-id", "trace-id"),
                ("X-Request-Id", " req-provider "),
            )
        )
        == "req-provider"
    )
    assert (
        _extract_provider_request_id(
            (
                ("x-trace-id", "trace-id"),
                ("x-ds-trace-id", " ds-trace-provider "),
            )
        )
        == "ds-trace-provider"
    )
    assert (
        _extract_provider_request_id(
            (
                ("x-ds-trace-id", "ds-trace-provider"),
                ("x-request-id", "req-provider"),
            )
        )
        == "req-provider"
    )


def test_provider_request_id_log_fields_only_include_present_headers() -> None:
    """response 日志只输出实际存在的 provider request id headers。"""

    assert (
        _format_provider_request_id_headers_for_log(
            (("x-ds-trace-id", " ds-trace-provider "),)
        )
        == "x-ds-trace-id=ds-trace-provider"
    )
    assert (
        _format_provider_request_id_headers_for_log(
            (
                ("x-ds-trace-id", "ds-trace-provider"),
                ("x-request-id", "req-provider"),
            )
        )
        == "x-request-id=req-provider x-ds-trace-id=ds-trace-provider"
    )
    assert (
        _format_provider_request_id_headers_for_log(
            (
                ("x-trace-id", "trace-id"),
                ("x-request-id", " "),
            )
        )
        == "x-request-id=None"
    )


@pytest.mark.asyncio
async def test_sse_success_provider_request_id_reaches_agent_iteration_completed() -> None:
    """SSE 正常成功响应的 request id 会传到 Agent iteration_completed。"""

    spec = make_spec(supports_streaming=True)
    token = FakeCancellationToken()
    runner = AsyncOpenAIRunner(spec=spec, cancellation_token=token)
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "x-request-id": "req_agent_sse",
            },
            body_chunks=[
                b'data: {"choices":[{"delta":{"content":"hi"},'
                b'"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ],
        )
    )
    _install_session(runner, session)

    events = await _collect_agent_events(
        runner=runner,
        spec=spec,
        token=token,
        stream=True,
    )

    request_payload = json.loads(session.calls[0][1].decode("utf-8"))
    assert request_payload["stream"] is True
    assert _iteration_completed_data(events).provider_request_id == "req_agent_sse"
    assert _final_answer_data(events).content == "hi"


@pytest.mark.asyncio
async def test_stream_true_json_content_type_uses_non_stream_parser() -> None:
    """stream=True 但 Content-Type 含 JSON 时仍按非流式 JSON 解析。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(supports_streaming=True),
        cancellation_token=FakeCancellationToken(),
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "application/json",
                "x-request-id": "req_json",
            },
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"json"},"finish_reason":"stop"}]}'
            ],
        )
    )
    _install_session(runner, session)

    events = await _collect(runner)

    assert [event.type for event in events] == [
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_DONE,
    ]
    assert isinstance(events[0].data, RunnerContentCompletedData)
    assert events[0].data.content == "json"
    assert isinstance(events[1].data, RunnerDoneData)
    assert events[1].data.provider_request_id == "req_json"
    await runner.close()


@pytest.mark.asyncio
async def test_stream_true_missing_content_type_falls_back_to_sse(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """stream=True 但缺 Content-Type 时按 SSE 尝试并记录诊断。"""

    caplog.set_level(
        "WARNING", logger="dayu.engine.runners.openai.runner"
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(supports_streaming=True),
        cancellation_token=FakeCancellationToken(),
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"x-request-id": "req_missing_content_type"},
            body_chunks=[
                b'data: {"choices":[{"delta":{"content":"hi"},'
                b'"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ],
        )
    )
    _install_session(runner, session)

    events = await _collect(runner)

    assert [event.type for event in events] == [
        RunnerEventType.RUNNER_CONTENT_DELTA,
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_DONE,
    ]
    assert isinstance(events[1].data, RunnerContentCompletedData)
    assert events[1].data.content == "hi"
    assert isinstance(events[2].data, RunnerDoneData)
    assert events[2].data.provider_request_id == "req_missing_content_type"
    assert "runner.http.missing_content_type" in caplog.text
    await runner.close()


@pytest.mark.asyncio
async def test_non_stream_success_provider_request_id_reaches_agent_iteration_completed() -> None:
    """非流式正常成功响应的 request id 会传到 Agent iteration_completed。"""

    spec = make_spec(supports_streaming=True)
    token = FakeCancellationToken()
    runner = AsyncOpenAIRunner(spec=spec, cancellation_token=token)
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "application/json",
                "x-request-id": "req_agent_json",
            },
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"json"},"finish_reason":"stop"}]}'
            ],
        )
    )
    _install_session(runner, session)

    events = await _collect_agent_events(
        runner=runner,
        spec=spec,
        token=token,
        stream=False,
    )

    request_payload = json.loads(session.calls[0][1].decode("utf-8"))
    assert request_payload["stream"] is False
    assert (
        _iteration_completed_data(events).provider_request_id
        == "req_agent_json"
    )
    assert _final_answer_data(events).content == "json"
