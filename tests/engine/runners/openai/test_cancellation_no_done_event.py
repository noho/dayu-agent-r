"""取消时不发 :class:`RunnerDoneData` 事件的不变量测试。"""

from __future__ import annotations

import asyncio

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import RunnerEvent, RunnerEventType
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    AsyncByteIter,
    FakeCancellationToken,
)


class _ChunkedFakeContent:
    """一个把字节 chunk 顺序吐出、最后一个 chunk 之前永远等待的 content。

    用于精确控制何时让 SSEParser 完成第一个 chunk、再触发取消。
    """

    def __init__(self, chunks: list[bytes], cancel_after: int) -> None:
        self._chunks = chunks
        self._index = 0
        self._cancel_after = cancel_after
        self._token: FakeCancellationToken | None = None

    def attach_token(self, token: FakeCancellationToken) -> None:
        """绑定 token 以便在指定 chunk 后触发取消。"""

        self._token = token

    async def readany(self) -> bytes:
        if self._index < len(self._chunks):
            chunk = self._chunks[self._index]
            self._index += 1
            return chunk
        # 所有 chunk 已吐完，第一次进入这里才触发取消，
        # 这样能保证 SSEParser 已完整消费首个 chunk 并 yield delta。
        if self._token is not None and not self._token.is_cancelled():
            self._token.trigger("after stream drained")
        await asyncio.sleep(10.0)
        return b""


class _StreamingResponse:
    def __init__(self, content: _ChunkedFakeContent) -> None:
        self.status = 200
        self.headers = {"Content-Type": "text/event-stream"}
        self.content = content
        self.released = False

    async def read(self) -> bytes:
        return b""

    async def text(self) -> str:
        return ""

    def release(self) -> None:
        self.released = True


class _StreamingCtx:
    def __init__(self, response: _StreamingResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _StreamingResponse:
        return self._response

    async def __aexit__(self, *_: object) -> None:
        return None


class _StreamingSession:
    def __init__(self, response: _StreamingResponse) -> None:
        self._response = response

    def post(self, url: str, *, data: bytes, headers: object) -> _StreamingCtx:
        return _StreamingCtx(self._response)

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_cancel_mid_stream_no_done_event() -> None:
    """流中触发取消后，事件序列**不**包含 :class:`RunnerDoneData`。"""

    token = FakeCancellationToken()
    chunks = [
        b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
    ]
    content = _ChunkedFakeContent(chunks, cancel_after=1)
    content.attach_token(token)
    response = _StreamingResponse(content)
    session = _StreamingSession(response)

    runner = AsyncOpenAIRunner(
        spec=make_spec(supports_streaming=True),
        cancellation_token=token,
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for ev in runner.call(msgs, make_options(stream=True), []):
        events.append(ev)
    await runner.close()

    # 至少有 content delta 事件
    assert any(
        e.type is RunnerEventType.RUNNER_CONTENT_DELTA for e in events
    )
    # 不应包含 Done
    assert all(
        e.type is not RunnerEventType.RUNNER_DONE for e in events
    )
    # 不应包含 HTTP 错误事件
    assert all(
        e.type is not RunnerEventType.RUNNER_HTTP_ERROR for e in events
    )


_ = AsyncByteIter  # 保持被引用以避免被静态分析视为未使用导入
