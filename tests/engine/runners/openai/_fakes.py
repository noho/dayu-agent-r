"""测试用 fake aiohttp session / response。

本模块提供 :class:`FakeSession` 与 :class:`FakeResponse`，模拟
``aiohttp.ClientSession.post(...)`` 与 ``aiohttp.ClientResponse``
的最小子集，覆盖
:class:`~dayu.engine.runners.openai.runner.AsyncOpenAIRunner` 实际依赖
的接口面：

- ``session.post(url, data, headers)`` 返回 ``async with`` 上下文管理器，
  其 ``__aenter__`` 产出 :class:`FakeResponse`。
- :class:`FakeResponse.status`、``.headers``、``.read()``、``.text()``、
  ``.release()``、``.content.readany()``。

亦支持配置 ``session.post`` 直接抛出 :class:`aiohttp.ClientError` /
:class:`asyncio.TimeoutError` 模拟连接失败 / 超时。

仅供本目录下测试使用。
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self


@dataclass(slots=True)
class FakeResponseSpec:
    """单次响应的脚本配置。

    :param status: HTTP 状态码。
    :param headers: 响应头映射。
    :param body_chunks: 响应体字节切片序列；流式由多个 chunk 表达，
        非流式合并为单个 chunk。
    :param read_exception: ``read()`` 抛出的异常；为 ``None`` 时正常返回
        ``body_chunks`` 拼接结果。
    """

    status: int
    headers: Mapping[str, str]
    body_chunks: Sequence[bytes]
    read_exception: BaseException | None = None


@dataclass(slots=True)
class FakeContent:
    """模拟 ``aiohttp.ClientResponse.content``。

    :param chunks: 待产出的字节切片队列；耗尽后 ``readany`` 返回 ``b""``。
    """

    chunks: "deque[bytes]" = field(default_factory=deque)

    async def readany(self) -> bytes:
        """返回下一个字节切片；耗尽时返回 ``b""``。"""

        if not self.chunks:
            return b""
        return self.chunks.popleft()

    async def read(self, size: int = -1) -> bytes:
        """最多读取指定字节数。

        :param size: 最大读取字节数；负数表示读取剩余全部。
        :returns: 读取到的字节串；耗尽时返回 ``b""``。
        """

        if not self.chunks:
            return b""
        if size < 0:
            chunks = tuple(self.chunks)
            self.chunks.clear()
            return b"".join(chunks)
        if size == 0:
            return b""
        collected: list[bytes] = []
        remaining = size
        while self.chunks and remaining > 0:
            chunk = self.chunks.popleft()
            if len(chunk) <= remaining:
                collected.append(chunk)
                remaining -= len(chunk)
                continue
            collected.append(chunk[:remaining])
            self.chunks.appendleft(chunk[remaining:])
            remaining = 0
        return b"".join(collected)


class FakeResponse:
    """模拟 ``aiohttp.ClientResponse`` 的最小子集。

    :param spec: 响应脚本配置。
    """

    def __init__(self, spec: FakeResponseSpec) -> None:
        """构造 fake response。"""

        self.status: int = spec.status
        self.headers: Mapping[str, str] = dict(spec.headers)
        self._body_chunks: list[bytes] = list(spec.body_chunks)
        self._read_exception: BaseException | None = spec.read_exception
        self.content: FakeContent = FakeContent(deque(self._body_chunks))
        self.released: bool = False

    async def read(self) -> bytes:
        """返回完整响应体字节串。

        :returns: 拼接后的字节串。
        :raises BaseException: ``FakeResponseSpec.read_exception`` 存在时抛出。
        """

        if self._read_exception is not None:
            raise self._read_exception
        return b"".join(self._body_chunks)

    async def text(self) -> str:
        """返回响应体的 UTF-8 文本。

        :returns: 解码后的字符串；失败时回退到 ``errors='replace'``。
        :raises UnicodeDecodeError: 当响应体不是合法 UTF-8 时；与
            真实 ``aiohttp.ClientResponse.text()`` 行为一致。
        """

        return b"".join(self._body_chunks).decode("utf-8")

    def release(self) -> None:
        """同步释放响应，与 ``aiohttp`` 一致。"""

        self.released = True


class _FakeRequestContext:
    """``session.post(...)`` 返回的 async context manager。

    :param response: 进入上下文时返回的 :class:`FakeResponse`。
    """

    def __init__(self, response: FakeResponse) -> None:
        self._response: FakeResponse = response

    async def __aenter__(self) -> FakeResponse:
        """进入上下文。"""

        return self._response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出上下文，释放响应。"""

        self._response.release()


@dataclass(slots=True)
class _ScheduledExc:
    """脚本中的下一次响应位是异常。"""

    exc: BaseException


class FakeSession:
    """模拟 ``aiohttp.ClientSession``。

    通过 :meth:`enqueue_response` / :meth:`enqueue_exception` 预先排队
    响应或异常；调用 ``post`` 时按顺序消耗。
    """

    def __init__(self) -> None:
        """构造 fake session。"""

        self._scheduled: deque[FakeResponseSpec | _ScheduledExc] = deque()
        self.calls: list[tuple[str, bytes, Mapping[str, str]]] = []
        self.closed: bool = False

    def enqueue_response(self, spec: FakeResponseSpec) -> None:
        """排队下一次响应。

        :param spec: 响应脚本。
        :returns: 无返回值。
        """

        self._scheduled.append(spec)

    def enqueue_exception(self, exc: BaseException) -> None:
        """排队下一次 ``post`` 抛出的异常。

        :param exc: 待抛出的异常实例。
        :returns: 无返回值。
        """

        self._scheduled.append(_ScheduledExc(exc=exc))

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: Mapping[str, str],
    ) -> _FakeRequestContext:
        """模拟 ``aiohttp.ClientSession.post``。

        :param url: 请求 URL。
        :param data: 请求体字节。
        :param headers: 请求头。
        :returns: async context manager，其 ``__aenter__`` 返回响应；
            若脚本顶为异常项，则在调用 ``post`` 时立即抛出。
        :raises BaseException: 当脚本顶部为预排异常时。
        """

        self.calls.append((url, data, dict(headers)))
        if not self._scheduled:
            raise AssertionError(
                "FakeSession received unexpected post() call (queue empty)"
            )
        item = self._scheduled.popleft()
        if isinstance(item, _ScheduledExc):
            raise item.exc
        response = FakeResponse(item)
        return _FakeRequestContext(response)

    async def close(self) -> None:
        """关闭 session。"""

        self.closed = True

    async def __aenter__(self) -> Self:
        """支持 ``async with``。"""

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出 ``async with`` 时关闭。"""

        await self.close()


@dataclass(slots=True)
class FakeCancellationToken:
    """简易 :class:`CancellationToken` 实现。

    :param cancelled: 是否已取消。
    :param reason: 取消原因。
    :param requested: 请求时间戳。
    """

    cancelled: bool = False
    reason: str | None = None
    requested: datetime | None = None

    def is_cancelled(self) -> bool:
        """返回是否已取消。"""

        return self.cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。"""

        return self.reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间戳。"""

        return self.requested

    def trigger(self, reason: str = "test") -> None:
        """触发取消。

        :param reason: 取消原因。
        :returns: 无返回值。
        """

        self.cancelled = True
        self.reason = reason
        self.requested = datetime.now()


def make_async_iter(chunks: Sequence[bytes]) -> "AsyncByteIter":
    """构造异步字节迭代器。

    :param chunks: 字节切片序列。
    :returns: 异步迭代器对象。
    """

    return AsyncByteIter(list(chunks))


class AsyncByteIter:
    """字节切片异步迭代器，仅供 SSEParser 测试输入用。

    :param chunks: 字节切片序列。
    """

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks: list[bytes] = chunks
        self._index: int = 0

    def __aiter__(self) -> Self:
        """返回自身。"""

        return self

    async def __anext__(self) -> bytes:
        """返回下一个字节切片。"""

        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        # 让出控制权一次，模拟真实 IO。
        await asyncio.sleep(0)
        return chunk


__all__ = [
    "FakeResponseSpec",
    "FakeContent",
    "FakeResponse",
    "FakeSession",
    "FakeCancellationToken",
    "AsyncByteIter",
    "make_async_iter",
]
