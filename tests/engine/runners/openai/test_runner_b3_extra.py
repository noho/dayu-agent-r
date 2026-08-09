"""Phase 1.5 code review B3 补充测试。

覆盖 :class:`~dayu.engine.runners.openai.runner.AsyncOpenAIRunner` 在
review 中识别的边界场景：

- SSE idle pending readany task 在 aclose / 外层 cancel / idle 硬超时
  时无泄漏（B1 lock-in）。
- cancellation 优先于 timeout（cancel-wins-over-timeout）。
- ``timeout_seconds`` 启用、未启用 heartbeat 时旧路径仍工作。
- 终态 4xx 错误体为空时 ``message_text`` 走 fallback ``HTTP <code>``。
- RunnerEvent 数据流不被诊断日志污染（事件迭代器只输出 RunnerEvent）。
- ``http_client.close`` debug 日志路径。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import cast

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import (
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
)
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeResponseSpec,
    FakeSession,
)
from tests.engine.runners.openai.test_stream_idle import (
    _DelayedSession,
    _sse_headers,
)


def _attach_caplog_to_dayu(
    caplog: pytest.LogCaptureFixture,
) -> logging.Logger:
    """把 caplog handler 显式挂到 dayu logger。"""

    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    return namespace_logger


@pytest.mark.asyncio
async def test_sse_idle_aclose_does_not_leak_pending_task() -> None:
    """生成器 ``aclose()`` 后 pending readany task 必须收口。"""

    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[b"data: x\n\n"],
        ),
        delay_seconds=10.0,
    )
    spec = make_spec(
        max_retries=0,
        stream_idle_timeout_seconds=5.0,
        stream_idle_heartbeat_seconds=0.05,
    )
    runner = AsyncOpenAIRunner(
        spec=spec, cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    iterator = cast(
        AsyncGenerator[RunnerEvent, None],
        runner._call_impl(  # type: ignore[attr-defined]
            msgs,
            make_options(stream=True),
            [],
            structured_output=None,
            request_identity=None,
        ),
    )

    async def _drain_one() -> RunnerEvent:
        return await iterator.__anext__()

    # 让生成器进入 readany pending 等待。
    drain_task: asyncio.Task[RunnerEvent] = asyncio.create_task(
        _drain_one()
    )
    await asyncio.sleep(0.1)
    # 先取消 drain（这会向生成器内部注入 CancelledError，触发 finally
    # 收口 pending readany），等收口完成后再 aclose。
    drain_task.cancel()
    try:
        await drain_task
    except (asyncio.CancelledError, StopAsyncIteration, BaseException):
        pass
    # 现在生成器已退出 anext，aclose 应该是 no-op，但仍要可调用。
    await iterator.aclose()
    # 验证：当前 event loop 中没有任何运行中的 task 在 readany 上。
    pending_tasks = [
        t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()
    ]
    assert not pending_tasks, (
        f"expected no leaked pending tasks, got {pending_tasks}"
    )


@pytest.mark.asyncio
async def test_sse_idle_outer_cancel_does_not_leak_pending_task() -> None:
    """外层 ``Task.cancel()`` 时 pending readany 必须被回收。"""

    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[b"data: x\n\n"],
        ),
        delay_seconds=10.0,
    )
    spec = make_spec(
        max_retries=0,
        stream_idle_timeout_seconds=5.0,
        stream_idle_heartbeat_seconds=0.05,
    )
    runner = AsyncOpenAIRunner(
        spec=spec, cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    async def _drive() -> list[RunnerEvent]:
        msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
        events: list[RunnerEvent] = []
        async for event in runner.call(
            structured_output=None,
            messages=msgs, options=make_options(stream=True), tools=[]
        ):
            events.append(event)
        return events

    task = asyncio.create_task(_drive())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pending_tasks = [
        t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()
    ]
    assert not pending_tasks


@pytest.mark.asyncio
async def test_sse_idle_cancel_wins_over_timeout() -> None:
    """cancel 与 idle timeout 并发命中时优先返回取消（不发 HTTP_ERROR）。"""

    token = ControllableCancellationToken()
    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[b"data: x\n\n"],
        ),
        delay_seconds=10.0,
    )
    spec = make_spec(
        max_retries=0,
        stream_idle_timeout_seconds=2.0,
    )
    runner = AsyncOpenAIRunner(spec=spec, cancellation_token=token)
    runner._http_client._session = session  # type: ignore[attr-defined]

    async def _drive() -> list[RunnerEvent]:
        msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
        events: list[RunnerEvent] = []
        async for event in runner.call(
            structured_output=None,
            messages=msgs, options=make_options(stream=True), tools=[]
        ):
            events.append(event)
        return events

    task = asyncio.create_task(_drive())
    # 在 idle timeout 命中前抢先取消。
    await asyncio.sleep(0.01)
    token.request_cancel("user-cancel")
    events = await task
    # 取消语义：生成器自然终止，不补 RunnerDoneData，也不发 HTTP_ERROR。
    assert not any(
        e.type is RunnerEventType.RUNNER_HTTP_ERROR for e in events
    )
    assert not any(
        e.type is RunnerEventType.RUNNER_DONE for e in events
    )


@pytest.mark.asyncio
async def test_terminal_error_with_empty_body_falls_back_to_status() -> None:
    """4xx 终态错误响应体为空时 message 应 fallback 到 ``HTTP <code>``。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=400,
            headers={"Content-Type": "application/json"},
            body_chunks=[b""],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=0),
        cancellation_token=ControllableCancellationToken(),
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for event in runner.call(
        structured_output=None,
        messages=msgs, options=make_options(stream=False), tools=[]
    ):
        events.append(event)

    http_errors = [
        e for e in events if e.type is RunnerEventType.RUNNER_HTTP_ERROR
    ]
    assert len(http_errors) == 1
    data = http_errors[0].data
    assert isinstance(data, RunnerHTTPErrorData)
    assert data.message == "HTTP 400"
    assert data.http_status == 400
    assert data.error_code is RunnerHTTPErrorCode.CLIENT_ERROR


@pytest.mark.asyncio
async def test_runner_event_stream_does_not_yield_log_records() -> None:
    """RunnerEvent 流不应混入诊断日志（仅 RunnerEvent 类型）。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"hi"},"finish_reason":"stop"}]}'
            ],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for event in runner.call(
        structured_output=None,
        messages=msgs, options=make_options(stream=False), tools=[]
    ):
        events.append(event)

    for event in events:
        assert isinstance(event, RunnerEvent), (
            f"non-RunnerEvent leaked into stream: {event!r}"
        )
    assert events[-1].type is RunnerEventType.RUNNER_DONE


@pytest.mark.asyncio
async def test_http_client_close_emits_debug_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``HTTPClient.close`` 应输出 debug 诊断（lazy session 路径）。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            await runner.close()
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert any(
        "http_client.close" in r.getMessage() for r in caplog.records
    )


@pytest.mark.asyncio
async def test_idle_timeout_only_no_heartbeat_still_works() -> None:
    """仅启用 ``stream_idle_timeout_seconds`` 时不报心跳日志、按 timeout 收口。"""

    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[b"data: x\n\n"],
        ),
        delay_seconds=2.0,
    )
    spec = make_spec(
        max_retries=0,
        stream_idle_timeout_seconds=0.05,
    )
    runner = AsyncOpenAIRunner(
        spec=spec, cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for event in runner.call(
        structured_output=None,
        messages=msgs, options=make_options(stream=True), tools=[]
    ):
        events.append(event)

    http_errors = [
        e for e in events if e.type is RunnerEventType.RUNNER_HTTP_ERROR
    ]
    assert len(http_errors) == 1
    err = http_errors[0].data
    assert isinstance(err, RunnerHTTPErrorData)
    assert err.error_code is RunnerHTTPErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_protocol_error_emits_warning_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """非流式 invalid JSON 协议错误应输出 WARNING 日志。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"not json"],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                structured_output=None,
                messages=msgs,
                options=make_options(stream=False),
                tools=[],
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    proto_records = [
        r for r in caplog.records
        if "non_stream.protocol_error" in r.getMessage()
    ]
    assert proto_records
    assert all(r.levelno >= logging.WARNING for r in proto_records)


@pytest.mark.asyncio
async def test_http_post_and_response_debug_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """成功路径应输出 ``runner.http.post`` 与 ``runner.http.response`` debug 日志。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"hi"},"finish_reason":"stop"}]}'
            ],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                structured_output=None,
                messages=msgs,
                options=make_options(stream=False),
                tools=[],
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records]
    assert any("runner.http.post" in m for m in messages)
    assert any("runner.http.response" in m for m in messages)
