"""``aiohttp.ClientSession`` 持有与幂等关闭。

本模块封装一个细粒度的 HTTP session 持有者：

- 懒初始化 :class:`aiohttp.ClientSession`，复用底层连接池。
- 提供 :meth:`close` 幂等关闭；二次调用安全。
- 不在 close 路径观察 cancellation token——关闭是清理动作，不应被
  取消打断。

实际的 HTTP 阶段（建连 / 读流）取消由 Runner 顶层结合
:func:`~dayu.runtime.cancellation.await_or_cancel`
驱动；本模块只承担 session 生命周期。
"""

from __future__ import annotations

import contextlib
import logging
from types import TracebackType
from typing import Self

import aiohttp

_LOGGER: logging.Logger = logging.getLogger(__name__)


class HTTPClient:
    """``aiohttp.ClientSession`` 持有者。"""

    def __init__(self, *, timeout_seconds: float) -> None:
        """构造 HTTP client。

        :param timeout_seconds: 单次请求超时秒数。
        """

        self._timeout_seconds: float = timeout_seconds
        self._session: aiohttp.ClientSession | None = None
        self._closed: bool = False

    @property
    def is_closed(self) -> bool:
        """返回是否已关闭。"""

        return self._closed

    def session(self) -> aiohttp.ClientSession:
        """获取（或惰性创建）底层 session。

        :returns: :class:`aiohttp.ClientSession` 实例。

        :raises RuntimeError: 已关闭后再次取用时抛出。
        """

        if self._closed:
            raise RuntimeError("HTTPClient already closed")
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """幂等关闭底层 session。

        :returns: 无返回值。

        二次调用安全；底层抛出的 :class:`RuntimeError` /
        :class:`ConnectionResetError` / :class:`OSError` 均被吞掉以
        保证清理路径稳定。
        """

        if self._closed:
            return
        self._closed = True
        if self._session is None:
            _LOGGER.debug("http_client.close session_was_lazy=true")
            return
        _LOGGER.debug("http_client.close session_was_lazy=false")
        with contextlib.suppress(
            RuntimeError, ConnectionResetError, OSError
        ):
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> Self:
        """支持 ``async with`` 语义。"""

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出 ``async with`` 时关闭。"""

        await self.close()


__all__ = ["HTTPClient"]
