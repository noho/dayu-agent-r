"""SSE 字节迭代器空闲心跳 / timeout 测试（Phase 1.5）。

覆盖 :class:`~dayu.engine.runners.openai.runner.AsyncOpenAIRunner`
``_iter_response_bytes_with_idle`` 路径：

- 启用 ``stream_idle_timeout_seconds`` 时 idle timeout 应映射为
  retriable :class:`RunnerHTTPErrorCode.TIMEOUT`。
- 启用 ``stream_idle_heartbeat_seconds`` 时心跳到点应输出 stream debug
  日志，且不打断 readany pending（不丢字节）。
- 未启用时走旧的 ``_iter_response_bytes_no_idle``，无心跳日志。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Mapping
from types import TracebackType

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import (
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
)
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner
from dayu.runtime.log_levels import STREAM_DEBUG_LOG_LEVEL

from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeCancellationToken,
    FakeContent,
    FakeResponse,
    FakeResponseSpec,
    FakeSession,
)


class _DelayedContent(FakeContent):
    """在 ``readany`` 前等候若干秒，再返回下一个 chunk。"""

    def __init__(
        self,
        chunks: list[bytes],
        *,
        delay_seconds: float,
    ) -> None:
        super().__init__(chunks=deque(chunks))
        self._delay_seconds: float = delay_seconds

    async def readany(self) -> bytes:
        """sleep ``delay_seconds`` 后再返回。"""

        await asyncio.sleep(self._delay_seconds)
        if not self.chunks:
            return b""
        return self.chunks.popleft()


class _DelayedResponse(FakeResponse):
    """带 :class:`_DelayedContent` 的响应。"""

    def __init__(
        self,
        spec: FakeResponseSpec,
        *,
        delay_seconds: float,
    ) -> None:
        super().__init__(spec)
        self.content = _DelayedContent(
            list(spec.body_chunks), delay_seconds=delay_seconds
        )


class _DelayedRequestContext:
    """``post`` 返回值；``__aenter__`` 给出 :class:`_DelayedResponse`。"""

    def __init__(self, response: _DelayedResponse) -> None:
        self._response: _DelayedResponse = response

    async def __aenter__(self) -> _DelayedResponse:
        """进入上下文。"""

        return self._response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出上下文。"""

        self._response.release()


class _DelayedSession:
    """单响应、可控延时的 fake session。"""

    def __init__(
        self,
        *,
        spec: FakeResponseSpec,
        delay_seconds: float,
    ) -> None:
        self._response: _DelayedResponse = _DelayedResponse(
            spec, delay_seconds=delay_seconds
        )
        self.closed: bool = False

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: Mapping[str, str],
    ) -> _DelayedRequestContext:
        """返回 delayed context。"""

        del url, data, headers
        return _DelayedRequestContext(self._response)

    async def close(self) -> None:
        """关闭 session。"""

        self.closed = True


def _sse_headers() -> dict[str, str]:
    """SSE 响应头。"""

    return {"Content-Type": "text/event-stream"}


def _heartbeat_runner() -> AsyncOpenAIRunner:
    """构造会在 SSE byte read 空闲期间产生 heartbeat 的 runner。

    参数：无。
    返回值：使用 delayed fake session 的 OpenAI runner。
    异常：本 helper 不主动转换异常；fake session 或 runner 构造异常会透传。
    """

    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[
                b"data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\n",
                b"data: [DONE]\n\n",
            ],
        ),
        delay_seconds=0.06,
    )
    spec = make_spec(
        max_retries=0,
        stream_idle_timeout_seconds=0.5,
        stream_idle_heartbeat_seconds=0.02,
    )
    runner = AsyncOpenAIRunner(
        spec=spec, cancellation_token=FakeCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]
    return runner


@pytest.mark.asyncio
async def test_idle_timeout_emits_retriable_timeout() -> None:
    """idle 超时应映射为 retriable TIMEOUT 错误事件 + Done(ERROR)。"""

    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[b"data: x\n\n"],
        ),
        delay_seconds=5.0,  # 远大于 idle timeout
    )
    spec = make_spec(
        max_retries=0,
        stream_idle_timeout_seconds=0.05,
    )
    runner = AsyncOpenAIRunner(
        spec=spec, cancellation_token=FakeCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for event in runner.call(
        messages=msgs, options=make_options(stream=True), tools=[]
    ):
        events.append(event)

    http_errors = [
        e for e in events if e.type is RunnerEventType.RUNNER_HTTP_ERROR
    ]
    assert len(http_errors) == 1
    data = http_errors[0].data
    assert isinstance(data, RunnerHTTPErrorData)
    assert data.error_code is RunnerHTTPErrorCode.TIMEOUT
    assert events[-1].type is RunnerEventType.RUNNER_DONE


@pytest.mark.asyncio
async def test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """心跳到点输出 stream debug 日志，不丢 chunk，最终成功完成。

    参数：
        caplog: pytest 日志捕获 fixture。
    返回值：``None``。
    异常：断言失败时由 pytest 报告。
    """

    runner = _heartbeat_runner()

    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(STREAM_DEBUG_LOG_LEVEL, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            events: list[RunnerEvent] = []
            async for event in runner.call(
                messages=msgs, options=make_options(stream=True), tools=[]
            ):
                events.append(event)
    finally:
        namespace_logger.removeHandler(caplog.handler)

    # 不应出现 HTTP_ERROR；最终事件是 DONE。
    assert not any(
        e.type is RunnerEventType.RUNNER_HTTP_ERROR for e in events
    )
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    heartbeat_messages = [
        r.getMessage() for r in caplog.records
        if "stream_idle.heartbeat" in r.getMessage()
    ]
    assert heartbeat_messages, (
        "expected at least one heartbeat debug log, got "
        f"{[r.getMessage() for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_idle_heartbeat_is_not_captured_at_normal_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """等价 idle 条件下，普通 DEBUG 不捕获 stream heartbeat。

    参数：
        caplog: pytest 日志捕获 fixture。
    返回值：``None``。
    异常：断言失败时由 pytest 报告。
    """

    runner = _heartbeat_runner()

    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            events: list[RunnerEvent] = []
            async for event in runner.call(
                messages=msgs, options=make_options(stream=True), tools=[]
            ):
                events.append(event)
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert not any(
        e.type is RunnerEventType.RUNNER_HTTP_ERROR for e in events
    )
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    assert not any(
        "stream_idle.heartbeat" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_idle_disabled_does_not_emit_heartbeat_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """未启用 idle 时不输出 stream_idle.heartbeat 日志。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers=_sse_headers(),
            body_chunks=[
                b"data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\n",
                b"data: [DONE]\n\n",
            ],
        )
    )
    spec = make_spec(max_retries=0)  # 不启用 idle
    runner = AsyncOpenAIRunner(
        spec=spec, cancellation_token=FakeCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                messages=msgs, options=make_options(stream=True), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert not any(
        "stream_idle.heartbeat" in r.getMessage()
        for r in caplog.records
    )
