"""Runner 诊断日志测试（Phase 1.5）。

覆盖 :class:`~dayu.engine.runners.openai.runner.AsyncOpenAIRunner`
在关键阶段（attempt 起点 / 重试 / 终态错误 / 取消）输出 ``dayu.*``
namespace 下的诊断日志，且不污染 RunnerEvent 流。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Mapping
from types import TracebackType
from typing import Protocol, cast

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import RunnerEvent, RunnerEventType
from dayu.engine.contracts.runner_identity import build_runner_request_identity
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner
from dayu.runtime.log_levels import STREAM_DEBUG_LOG_LEVEL

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeContent,
    FakeResponse,
    FakeResponseSpec,
    FakeSession,
)


def _attach_caplog_to_dayu(
    caplog: pytest.LogCaptureFixture,
) -> logging.Logger:
    """把 caplog handler 显式挂到 dayu logger 并返回。"""

    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    return namespace_logger


async def _never_finishing_readany() -> bytes:
    """模拟永不自然返回的 ``readany``。

    :returns: 不会返回。
    :raises asyncio.CancelledError: task 被取消时由 ``asyncio.sleep`` 抛出。
    """

    await asyncio.sleep(3600.0)
    return b""


async def _readany_raises_runtime_error_on_cancel() -> bytes:
    """模拟 ``readany`` 在取消清理阶段抛出普通异常。

    :returns: 不会返回。
    :raises RuntimeError: task 被取消后抛出。
    """

    try:
        await asyncio.sleep(3600.0)
    except asyncio.CancelledError as exc:
        raise RuntimeError("read cleanup failed") from exc
    return b""


async def _readany_raises_runtime_error_immediately() -> bytes:
    """模拟 ``readany`` 已完成但携带未消费异常。

    :returns: 不会返回。
    :raises RuntimeError: 始终抛出，用于验证 done task 异常消费。
    """

    raise RuntimeError("read failed before cleanup")


class _DelayedContent(FakeContent):
    """在 ``readany`` 前等待固定时间再产出下一个字节切片。"""

    def __init__(
        self,
        chunks: list[bytes],
        *,
        delay_seconds: float,
    ) -> None:
        """构造延迟字节流。

        :param chunks: 待产出的字节切片。
        :param delay_seconds: 每次 ``readany`` 前等待的秒数。
        """

        super().__init__(chunks=deque(chunks))
        self._delay_seconds: float = delay_seconds

    async def readany(self) -> bytes:
        """等待后返回下一个字节切片。

        :returns: 下一个字节切片；耗尽时返回 ``b""``。
        """

        await asyncio.sleep(self._delay_seconds)
        if not self.chunks:
            return b""
        return self.chunks.popleft()


class _DelayedResponse(FakeResponse):
    """带延迟 ``content.readany`` 的 fake response。"""

    def __init__(
        self,
        spec: FakeResponseSpec,
        *,
        delay_seconds: float,
    ) -> None:
        """构造延迟响应。

        :param spec: 响应脚本。
        :param delay_seconds: 每次 ``readany`` 前等待的秒数。
        """

        super().__init__(spec)
        self.content = _DelayedContent(
            list(spec.body_chunks), delay_seconds=delay_seconds
        )


class _DelayedRequestContext:
    """``post`` 返回的 async context manager。"""

    def __init__(self, response: _DelayedResponse) -> None:
        """构造 context manager。

        :param response: 进入上下文时返回的 fake response。
        """

        self._response: _DelayedResponse = response

    async def __aenter__(self) -> _DelayedResponse:
        """进入上下文。

        :returns: fake response。
        """

        return self._response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出上下文并释放响应。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: ``None``。
        """

        self._response.release()


class _DelayedSession:
    """单响应、可控延迟的 fake session。"""

    def __init__(
        self,
        *,
        spec: FakeResponseSpec,
        delay_seconds: float,
    ) -> None:
        """构造 fake session。

        :param spec: 响应脚本。
        :param delay_seconds: 每次 ``readany`` 前等待的秒数。
        """

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
        """返回延迟 response context。

        :param url: 请求 URL。
        :param data: 请求体字节。
        :param headers: 请求头。
        :returns: 延迟 response context。
        """

        del url, data, headers
        return _DelayedRequestContext(self._response)

    async def close(self) -> None:
        """关闭 fake session。

        :returns: ``None``。
        """

        self.closed = True


class _DelayedSessionClient:
    """供 stream 诊断测试注入延迟 fake session 的 HTTP client。"""

    def __init__(self, session: _DelayedSession) -> None:
        """构造测试 HTTP client。

        :param session: 本次 Runner 调用使用的延迟 fake session。
        """

        self._session: _DelayedSession = session

    def session(self) -> _DelayedSession:
        """返回延迟 fake session。

        :returns: 延迟 fake session。
        """

        return self._session

    async def close(self) -> None:
        """关闭延迟 fake session。

        :returns: ``None``。
        """

        await self._session.close()


class _RunnerWithDelayedSessionClient(Protocol):
    """描述测试需要替换的 Runner HTTP client 槽位。"""

    _http_client: _DelayedSessionClient


@pytest.mark.asyncio
async def test_attempt_start_diagnostic_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """成功路径应至少输出一条 attempt.start 诊断日志。"""

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
            events: list[RunnerEvent] = []
            async for event in runner.call(
                structured_output=None,
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                events.append(event)
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert any(
        "runner.attempt.start" in r.getMessage() for r in caplog.records
    )
    assert events[-1].type is RunnerEventType.RUNNER_DONE


@pytest.mark.asyncio
async def test_response_log_includes_client_correlation_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """既有 response 日志行同时携带 provider 与客户端关联 header。"""

    identity = build_runner_request_identity(
        run_id="run-log-correlation",
        attempt_id="attempt-log-correlation",
        execution_id="execution-log-correlation",
        iteration_id="iteration-log-correlation",
        iteration_index=0,
        runner_call_index=1,
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "application/json",
                "x-request-id": "req-log-correlation",
            },
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"hi"},"finish_reason":"stop"}]}'
            ],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(
            client_correlation_policy=(
                ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
            )
        ),
        cancellation_token=ControllableCancellationToken(),
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    with caplog.at_level(
        logging.DEBUG,
        logger="dayu.engine.runners.openai.runner",
    ):
        events: list[RunnerEvent] = []
        async for event in runner.call(
            structured_output=None,
            messages=[UserMessage(role=AgentMessageRole.USER, content="hi")],
            options=make_options(stream=False),
            tools=[],
            request_identity=identity,
        ):
            events.append(event)

    response_records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("runner.http.response status=")
    ]
    assert len(response_records) == 1
    assert response_records[0].levelno == logging.DEBUG
    response_message = response_records[0].getMessage()
    assert "x-request-id=req-log-correlation" in response_message
    assert "x-ds-trace-id" not in response_message
    assert (
        f"X-Client-Request-Id={identity.client_correlation_id}"
        in response_message
    )
    assert events[-1].type is RunnerEventType.RUNNER_DONE


@pytest.mark.asyncio
async def test_stream_diagnostics_require_stream_debug_log_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """stream heartbeat 与 SSE done 诊断只在 STREAM_DEBUG 阈值下出现。"""

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        debug_events = await _collect_stream_diagnostic_events(
            caplog=caplog,
            log_level=logging.DEBUG,
        )
        debug_messages = [record.getMessage() for record in caplog.records]
        assert debug_events[-1].type is RunnerEventType.RUNNER_DONE
        assert any("runner.attempt.start" in msg for msg in debug_messages)
        assert any("runner.http.post" in msg for msg in debug_messages)
        assert any("runner.http.response" in msg for msg in debug_messages)
        assert not any(
            "runner.stream_idle.heartbeat" in msg
            for msg in debug_messages
        )
        assert not any("sse.done_token received" in msg for msg in debug_messages)

        caplog.clear()
        stream_debug_events = await _collect_stream_diagnostic_events(
            caplog=caplog,
            log_level=STREAM_DEBUG_LOG_LEVEL,
        )
        stream_debug_messages = [
            record.getMessage() for record in caplog.records
        ]
        assert stream_debug_events[-1].type is RunnerEventType.RUNNER_DONE
        assert any(
            "runner.stream_idle.heartbeat" in msg
            for msg in stream_debug_messages
        )
        assert any(
            "sse.done_token received provider_request_id=req-stream-1" in msg
            for msg in stream_debug_messages
        )
    finally:
        namespace_logger.removeHandler(caplog.handler)


@pytest.mark.asyncio
async def test_cancelled_diagnostic_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """token 已取消时应输出 runner.cancelled 诊断日志。"""

    token = ControllableCancellationToken()
    token.request_cancel("test-cancel")
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"{}"],
        )
    )
    runner = AsyncOpenAIRunner(spec=make_spec(), cancellation_token=token)
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                structured_output=None,
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert any(
        "runner.cancelled" in r.getMessage() for r in caplog.records
    )


@pytest.mark.asyncio
async def test_cancel_pending_readany_cancelled_error_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """pending readany 正常响应取消时不写 warning。"""

    task = asyncio.create_task(_never_finishing_readany())
    await asyncio.sleep(0)

    with caplog.at_level(
        logging.WARNING, logger="dayu.engine.runners.openai.runner"
    ):
        await AsyncOpenAIRunner._cancel_pending_readany(task)

    assert task.cancelled()
    assert "runner.pending_readany_cancel_failed" not in caplog.text


@pytest.mark.asyncio
async def test_cancel_pending_readany_exception_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """pending readany 取消清理抛普通异常时记录 warning 与异常类型。"""

    task = asyncio.create_task(_readany_raises_runtime_error_on_cancel())
    await asyncio.sleep(0)

    with caplog.at_level(
        logging.WARNING, logger="dayu.engine.runners.openai.runner"
    ):
        await AsyncOpenAIRunner._cancel_pending_readany(task)

    assert "runner.pending_readany_cancel_failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_cancel_pending_readany_consumes_done_task_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """readany task 已完成且带异常时也必须消费异常。"""

    task = asyncio.create_task(_readany_raises_runtime_error_immediately())
    await asyncio.sleep(0)
    assert task.done()

    with caplog.at_level(
        logging.WARNING, logger="dayu.engine.runners.openai.runner"
    ):
        await AsyncOpenAIRunner._cancel_pending_readany(task)

    assert "runner.pending_readany_cancel_failed" not in caplog.text


@pytest.mark.asyncio
async def test_terminal_error_logged_at_warning_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """终态 HTTP 错误必须以 WARNING 级别记录 runner.attempt.terminal。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=400,
            headers={"Content-Type": "application/json"},
            body_chunks=[b'{"error":"bad"}'],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=0),
        cancellation_token=ControllableCancellationToken(),
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                structured_output=None,
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    terminal_records = [
        r for r in caplog.records
        if "runner.attempt.terminal" in r.getMessage()
    ]
    assert terminal_records
    assert all(r.levelno >= logging.WARNING for r in terminal_records)


@pytest.mark.asyncio
async def test_runner_logs_use_dayu_namespace_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runner 日志必须在 ``dayu.*`` namespace，不污染 root。"""

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
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    runner_records = [
        r for r in caplog.records if r.name.startswith("dayu.")
    ]
    assert runner_records
    for record in caplog.records:
        # 任何 caplog 抓到的日志都应来自 dayu namespace；root 不该被污染。
        assert record.name == "dayu" or record.name.startswith("dayu.")


async def _collect_stream_diagnostic_events(
    *,
    caplog: pytest.LogCaptureFixture,
    log_level: int,
) -> list[RunnerEvent]:
    """按指定日志阈值执行一次会触发 stream 诊断的调用。

    :param caplog: pytest 日志捕获夹具。
    :param log_level: ``dayu`` logger 使用的日志阈值。
    :returns: Runner 事件列表。
    """

    session = _DelayedSession(
        spec=FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "x-request-id": "req-stream-1",
            },
            body_chunks=[
                b"data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\n",
                b"data: [DONE]\n\n",
            ],
        ),
        delay_seconds=0.06,
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(
            max_retries=0,
            stream_idle_timeout_seconds=0.5,
            stream_idle_heartbeat_seconds=0.02,
        ),
        cancellation_token=ControllableCancellationToken(),
    )
    runner_with_client = cast(_RunnerWithDelayedSessionClient, runner)
    runner_with_client._http_client = _DelayedSessionClient(session)

    with caplog.at_level(log_level, logger="dayu"):
        msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
        events: list[RunnerEvent] = []
        async for event in runner.call(
            structured_output=None,
            messages=msgs, options=make_options(stream=True), tools=[]
        ):
            events.append(event)
    return events
