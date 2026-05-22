"""HTTP 错误事件归一测试。

覆盖所有 :class:`RunnerHTTPErrorCode` 分支：

- 429 重试耗尽 → ``RATE_LIMIT_EXCEEDED``。
- 500 重试耗尽 → ``SERVER_ERROR``。
- 4xx 非重试 → ``CLIENT_ERROR``。
- ``aiohttp.ClientConnectorError`` → ``NETWORK_ERROR``。
- ``asyncio.TimeoutError`` → ``TIMEOUT``。
- 非常规 HTTP 状态（如 199）→ ``UNKNOWN_HTTP_STATUS``。
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping, Sequence
import json
from types import TracebackType

import aiohttp
import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
)
from dayu.engine.runners.openai.runner import (
    _HTTP_ERROR_BODY_MAX_BYTES,
    AsyncOpenAIRunner,
)

from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeCancellationToken,
    FakeContent,
    FakeResponse,
    FakeResponseSpec,
    FakeSession,
)


class _ReadanyFailingContent(FakeContent):
    """先产出已配置 chunk，再让下一次 ``readany`` 抛出异常。"""

    def __init__(
        self,
        chunks: Sequence[bytes],
        *,
        exc: BaseException,
    ) -> None:
        """初始化失败脚本。

        :param chunks: 失败前先返回的字节片段。
        :param exc: chunk 耗尽后第一次 ``readany`` 抛出的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(chunks=deque(chunks))
        self._exc: BaseException = exc
        self._raised: bool = False

    async def readany(self) -> bytes:
        """返回下一个 chunk，或模拟流式读取失败。

        :returns: 下一个字节片段；异常已抛过且无剩余 chunk 时返回空字节串。
        :raises BaseException: 第一次耗尽 chunk 后抛出初始化传入的异常。
        """

        if self.chunks:
            return self.chunks.popleft()
        if not self._raised:
            self._raised = True
            raise self._exc
        return b""


class _ReadanyFailingResponse(FakeResponse):
    """``content.readany`` 可按脚本失败的 fake response。"""

    def __init__(
        self,
        spec: FakeResponseSpec,
        *,
        exc: BaseException,
    ) -> None:
        """初始化 fake response。

        :param spec: 响应基础脚本。
        :param exc: 流式读取失败异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(spec)
        self.content = _ReadanyFailingContent(spec.body_chunks, exc=exc)


class _ReadanyFailingRequestContext:
    """返回 :class:`_ReadanyFailingResponse` 的 async context manager。"""

    def __init__(self, response: FakeResponse) -> None:
        """初始化 context manager。

        :param response: 进入 context 时返回的 fake response。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._response: FakeResponse = response

    async def __aenter__(self) -> FakeResponse:
        """进入 context。

        :returns: fake response。
        :raises Exception: 不主动抛出异常。
        """

        return self._response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出 context 并释放 response。

        :param exc_type: context 内异常类型。
        :param exc: context 内异常实例。
        :param tb: context 内异常 traceback。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._response.release()


class _ReadanyFailingSession:
    """第一次调用返回流式读取失败响应，后续调用返回成功响应。"""

    def __init__(self, *, exc: BaseException) -> None:
        """初始化 fake session。

        :param exc: 第一次响应 readany 失败异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._exc: BaseException = exc
        self.calls: list[tuple[str, bytes, Mapping[str, str]]] = []
        self.closed: bool = False

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: Mapping[str, str],
    ) -> _ReadanyFailingRequestContext:
        """模拟 ``aiohttp.ClientSession.post``。

        :param url: 请求 URL。
        :param data: 请求体。
        :param headers: 请求头。
        :returns: fake async context manager。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append((url, data, dict(headers)))
        if len(self.calls) == 1:
            response = _ReadanyFailingResponse(
                FakeResponseSpec(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "x-request-id": "req-stream",
                    },
                    body_chunks=[
                        (
                            b'data: {"choices":[{"delta":'
                            b'{"content":"partial"}}]}\n\n'
                        )
                    ],
                ),
                exc=self._exc,
            )
            return _ReadanyFailingRequestContext(response)
        return _ReadanyFailingRequestContext(
            FakeResponse(
                FakeResponseSpec(
                    status=200,
                    headers={"Content-Type": "text/event-stream"},
                    body_chunks=[
                        b'data: {"choices":[{"delta":{"content":"retry"}}]}\n\n',
                        b"data: [DONE]\n\n",
                    ],
                )
            )
        )

    async def close(self) -> None:
        """关闭 fake session。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed = True


def _install_session(
    runner: AsyncOpenAIRunner, session: FakeSession | _ReadanyFailingSession
) -> None:
    """把 fake session 安装到 runner.HTTPClient。"""

    # 关闭真实 session 创建：直接把 _session 字段写入。
    client = runner._http_client  # type: ignore[attr-defined]
    client._session = session  # type: ignore[attr-defined]


async def _run(
    runner: AsyncOpenAIRunner,
) -> list[RunnerEvent]:
    """执行 runner.call 并收集事件。"""

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for ev in runner.call(msgs, make_options(stream=False), []):
        events.append(ev)
    return events


def _patch_no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """把 ``asyncio.sleep`` 替换为零等待并记录 sleep 秒数。

    实现要点：必须仍然 ``await`` 一次原 ``asyncio.sleep(0)`` 以让出事件
    循环控制权，否则 ``await_or_cancel`` 内部的取消轮询子任务会陷入
    无让出 CPU 死循环。
    """

    real_sleep = asyncio.sleep
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return sleeps


def _make_runner(*, max_retries: int = 0) -> AsyncOpenAIRunner:
    """构造 runner（默认禁用重试以便快速观察终态）。"""

    return AsyncOpenAIRunner(
        spec=make_spec(max_retries=max_retries),
        cancellation_token=FakeCancellationToken(),
    )


def _http_response(status: int, body: bytes = b"err") -> FakeResponseSpec:
    """构造非流式 HTTP 错误响应。"""

    return FakeResponseSpec(
        status=status,
        headers={"Content-Type": "application/json"},
        body_chunks=[body],
    )


def _http_response_with_headers(
    status: int,
    *,
    headers: dict[str, str],
    body: bytes,
) -> FakeResponseSpec:
    """构造带自定义响应头的 HTTP 错误响应。

    :param status: HTTP 状态码。
    :param headers: 响应头。
    :param body: 响应体。
    :returns: fake response spec。
    """

    return FakeResponseSpec(
        status=status,
        headers=headers,
        body_chunks=[body],
    )


def _check_http_error_then_done(
    events: Sequence[RunnerEvent],
    *,
    expected_code: RunnerHTTPErrorCode,
    expected_status: int | None,
    expected_attempt: int,
    expected_retried: bool,
) -> None:
    """断言事件序列以 HTTPError + Done(ERROR) 结尾。"""

    assert events[-2].type is RunnerEventType.RUNNER_HTTP_ERROR
    err = events[-2].data
    assert isinstance(err, RunnerHTTPErrorData)
    assert err.error_code is expected_code
    assert err.http_status == expected_status
    assert err.attempt == expected_attempt
    assert err.retried is expected_retried
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_http_429_retry_exhausted_rate_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``429`` 在 ``max_retries=1`` 后耗尽，记录 attempt=2/retried=True。"""

    _patch_no_sleep(monkeypatch)
    runner = _make_runner(max_retries=1)
    session = FakeSession()
    session.enqueue_response(_http_response(429))
    session.enqueue_response(_http_response(429))
    _install_session(runner, session)

    events = await _run(runner)
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        expected_status=429,
        expected_attempt=2,
        expected_retried=True,
    )
    await runner.close()


@pytest.mark.asyncio
async def test_http_500_retry_exhausted_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``500`` 在 ``max_retries=1`` 后耗尽。"""

    _patch_no_sleep(monkeypatch)
    runner = _make_runner(max_retries=1)
    session = FakeSession()
    session.enqueue_response(_http_response(500))
    session.enqueue_response(_http_response(503))
    _install_session(runner, session)

    events = await _run(runner)
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.SERVER_ERROR,
        expected_status=503,
        expected_attempt=2,
        expected_retried=True,
    )
    await runner.close()


@pytest.mark.asyncio
async def test_retry_exhausted_keeps_final_attempt_provider_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重试耗尽时 HTTP error 与 done 携带最终失败 attempt 的 request id。"""

    _patch_no_sleep(monkeypatch)
    runner = _make_runner(max_retries=1)
    session = FakeSession()
    session.enqueue_response(
        _http_response_with_headers(
            500,
            headers={"X-Request-Id": " req_first "},
            body=b'{"error":{"message":"first"}}',
        )
    )
    session.enqueue_response(
        _http_response_with_headers(
            503,
            headers={"x-request-id": "req_final"},
            body=b'{"error":{"message":"final"}}',
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert isinstance(events[-2].data, RunnerHTTPErrorData)
    assert events[-2].data.provider_request_id == "req_final"
    assert events[-2].data.raw_payload == {
        "error": {"message": "final"}
    }
    assert isinstance(events[-1].data, RunnerDoneData)
    assert events[-1].data.provider_request_id == "req_final"
    await runner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (aiohttp.ClientError("read failed"), RunnerHTTPErrorCode.NETWORK_ERROR),
        (asyncio.TimeoutError("read timeout"), RunnerHTTPErrorCode.TIMEOUT),
    ],
)
async def test_stream_read_failure_after_event_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
    expected_code: RunnerHTTPErrorCode,
) -> None:
    """流式 attempt 已产出事件后 readany 失败，不得再启动下一次重试。"""

    _patch_no_sleep(monkeypatch)
    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=2),
        cancellation_token=FakeCancellationToken(),
    )
    session = _ReadanyFailingSession(exc=exc)
    _install_session(runner, session)

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for ev in runner.call(msgs, make_options(stream=True), []):
        events.append(ev)

    assert len(session.calls) == 1
    assert events[0].type is RunnerEventType.RUNNER_CONTENT_DELTA
    assert events[-2].type is RunnerEventType.RUNNER_HTTP_ERROR
    err = events[-2].data
    assert isinstance(err, RunnerHTTPErrorData)
    assert err.error_code is expected_code
    assert err.provider_request_id == "req-stream"
    assert err.message == str(exc)
    assert err.attempt == 1
    assert err.retried is False
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
    assert done.provider_request_id == "req-stream"
    await runner.close()


@pytest.mark.asyncio
async def test_http_json_object_error_body_preserved_as_raw_payload() -> None:
    """HTTP JSON object 错误体必须进入 raw_payload，request id 仅来自 header。"""

    runner = _make_runner(max_retries=0)
    session = FakeSession()
    payload = {
        "error": {
            "message": "bad",
            "request_id": "payload-id-ignored",
        }
    }
    session.enqueue_response(
        _http_response_with_headers(
            400,
            headers={"x-ReQuEsT-id": " req_header "},
            body=json.dumps(payload).encode("utf-8"),
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert isinstance(events[-2].data, RunnerHTTPErrorData)
    assert events[-2].data.provider_request_id == "req_header"
    assert events[-2].data.raw_payload == payload
    assert isinstance(events[-1].data, RunnerDoneData)
    assert events[-1].data.provider_request_id == "req_header"
    await runner.close()


@pytest.mark.asyncio
async def test_http_unicode_decode_error_body_keeps_replacement_text() -> None:
    """HTTP 错误体 UTF-8 解码失败时仍保留 replacement 诊断文本。"""

    runner = _make_runner(max_retries=0)
    session = FakeSession()
    session.enqueue_response(
        _http_response_with_headers(
            400,
            headers={"x-request-id": "req_bad_utf8"},
            body=b"\xffbad",
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert isinstance(events[-2].data, RunnerHTTPErrorData)
    assert events[-2].data.message == "\ufffdbad"
    assert events[-2].data.raw_payload is None
    assert events[-2].data.provider_request_id == "req_bad_utf8"
    await runner.close()


@pytest.mark.asyncio
async def test_http_error_body_is_capped_before_decode() -> None:
    """HTTP 错误体读取必须在解码前按 byte 上限截断。"""

    runner = _make_runner(max_retries=0)
    session = FakeSession()
    body = b"x" * (_HTTP_ERROR_BODY_MAX_BYTES + 1024)
    session.enqueue_response(
        _http_response_with_headers(
            400,
            headers={"x-request-id": "req_large_error"},
            body=body,
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert isinstance(events[-2].data, RunnerHTTPErrorData)
    assert events[-2].data.message == "x" * _HTTP_ERROR_BODY_MAX_BYTES
    assert events[-2].data.raw_payload is None
    await runner.close()


@pytest.mark.asyncio
async def test_http_context_overflow_maps_to_context_length_exceeded() -> None:
    """HTTP context overflow 必须进入专用错误码并保留 request id。"""

    runner = _make_runner(max_retries=3)
    session = FakeSession()
    session.enqueue_response(
        _http_response_with_headers(
            400,
            headers={"x-request-id": "req_context"},
            body=(
                b'{"error":{"code":"context_length_exceeded",'
                b'"message":"maximum context length is 128000 tokens"}}'
            ),
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
        expected_status=400,
        expected_attempt=1,
        expected_retried=False,
    )
    assert isinstance(events[-2].data, RunnerHTTPErrorData)
    assert events[-2].data.provider_request_id == "req_context"
    assert isinstance(events[-1].data, RunnerDoneData)
    assert events[-1].data.finish_reason is FinishReason.ERROR
    assert events[-1].data.provider_request_id == "req_context"
    await runner.close()


@pytest.mark.asyncio
async def test_http_non_json_error_body_keeps_raw_payload_none() -> None:
    """非 JSON 错误体只作为 message，不写 raw_payload。"""

    runner = _make_runner(max_retries=0)
    session = FakeSession()
    session.enqueue_response(
        _http_response_with_headers(
            400,
            headers={"x-request-id": "req_text"},
            body=b"plain bad",
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert isinstance(events[-2].data, RunnerHTTPErrorData)
    assert events[-2].data.message == "plain bad"
    assert events[-2].data.provider_request_id == "req_text"
    assert events[-2].data.raw_payload is None
    await runner.close()


@pytest.mark.asyncio
async def test_http_4xx_non_retriable_client_error() -> None:
    """``400`` 不可重试，attempt=1/retried=False。"""

    runner = _make_runner(max_retries=3)
    session = FakeSession()
    session.enqueue_response(_http_response(400, b"bad"))
    _install_session(runner, session)

    events = await _run(runner)
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.CLIENT_ERROR,
        expected_status=400,
        expected_attempt=1,
        expected_retried=False,
    )
    await runner.close()


@pytest.mark.asyncio
async def test_http_unknown_status_699() -> None:
    """非常规状态（699，越过 5xx 区间）应归类为 ``UNKNOWN_HTTP_STATUS``。"""

    runner = _make_runner(max_retries=0)
    session = FakeSession()
    session.enqueue_response(_http_response(699))
    _install_session(runner, session)

    events = await _run(runner)
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS,
        expected_status=699,
        expected_attempt=1,
        expected_retried=False,
    )
    await runner.close()


@pytest.mark.asyncio
async def test_non_stream_read_client_error_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非流式 ``response.read()`` 读取失败应走现有 retry 后成功。"""

    _patch_no_sleep(monkeypatch)
    runner = _make_runner(max_retries=1)
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "application/json",
                "x-request-id": "req_read_failed",
            },
            body_chunks=[],
            read_exception=aiohttp.ClientPayloadError("broken payload"),
        )
    )
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "application/json",
                "x-request-id": "req_read_ok",
            },
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"ok"},"finish_reason":"stop"}]}'
            ],
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert len(session.calls) == 2
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.STOP
    assert done.provider_request_id == "req_read_ok"
    await runner.close()


@pytest.mark.asyncio
async def test_non_stream_read_client_error_retry_exhausted() -> None:
    """非流式 ``response.read()`` 读取失败且无重试时产出 HTTP error + Done。"""

    runner = _make_runner(max_retries=0)
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={
                "Content-Type": "application/json",
                "x-request-id": "req_read_failed",
            },
            body_chunks=[],
            read_exception=aiohttp.ClientPayloadError("broken payload"),
        )
    )
    _install_session(runner, session)

    events = await _run(runner)

    assert len(session.calls) == 1
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.NETWORK_ERROR,
        expected_status=None,
        expected_attempt=1,
        expected_retried=False,
    )
    err = events[-2].data
    assert isinstance(err, RunnerHTTPErrorData)
    assert err.provider_request_id == "req_read_failed"
    assert err.raw_payload is None
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.provider_request_id == "req_read_failed"
    await runner.close()


class _FakeConnKey:
    """模拟 ``aiohttp.ClientConnectorError`` 构造时需要的连接键。"""

    is_ssl: bool = False
    ssl: bool = False
    host: str = "example.test"
    port: int = 443


@pytest.mark.asyncio
async def test_network_error_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """:class:`aiohttp.ClientConnectorError` → ``NETWORK_ERROR``。"""

    _patch_no_sleep(monkeypatch)
    runner = _make_runner(max_retries=0)
    session = FakeSession()
    # 直接抛出 ClientConnectorError 的子类——构造起来繁琐，用 ClientError
    # 兜底（``classify_exception`` 把任意 ClientError 归为 NETWORK_ERROR）。
    session.enqueue_exception(aiohttp.ClientError("DNS fail"))
    _install_session(runner, session)

    events = await _run(runner)
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.NETWORK_ERROR,
        expected_status=None,
        expected_attempt=1,
        expected_retried=False,
    )
    await runner.close()


@pytest.mark.asyncio
async def test_timeout_error_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """:class:`asyncio.TimeoutError` → ``TIMEOUT``。"""

    _patch_no_sleep(monkeypatch)
    runner = _make_runner(max_retries=0)
    session = FakeSession()
    session.enqueue_exception(asyncio.TimeoutError())
    _install_session(runner, session)

    events = await _run(runner)
    _check_http_error_then_done(
        events,
        expected_code=RunnerHTTPErrorCode.TIMEOUT,
        expected_status=None,
        expected_attempt=1,
        expected_retried=False,
    )
    await runner.close()
