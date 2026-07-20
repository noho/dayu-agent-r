"""Host public durable command 的单线程 actor 边界。

本模块让一个 ``HostCommandHandle``、其 durable store 与 SQLite connection
从创建、使用到关闭始终归属于同一个专用 worker thread。async public handle
只向 actor 提交 typed operation；调用方取消不会取消已经开始的 durable
operation，避免事务或 after-commit wake 停在半途。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TypeVar

from dayu.host.api import HostClosedError
from dayu.host.command import HostCommandHandle

T = TypeVar("T")

_ACTOR_MAX_WORKERS = 1


def _actor_barrier() -> None:
    """作为 executor FIFO 尾部屏障等待此前 operation 收口。

    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """


def _close_command_handle(command_handle: HostCommandHandle) -> None:
    """在 actor worker thread 关闭 command handle。

    :param command_handle: actor 独占的 command handle。
    :returns: ``None``。
    :raises Exception: command handle 关闭失败时透传。
    """

    command_handle.close()


class DurableActor:
    """单线程串行执行 Host durable operation 的 actor。

    :param loop: actor 所属 opener event loop。
    :param executor: actor 独占的单 worker executor。
    :param command_handle: 在 executor worker thread 创建的 command handle。
    """

    __slots__ = (
        "_command_handle",
        "_drain_future",
        "_executor",
        "_handle_close_future",
        "_loop",
        "_shutdown",
        "_stopped",
    )

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        executor: ThreadPoolExecutor,
        command_handle: HostCommandHandle,
    ) -> None:
        """初始化已经打开的 durable actor。

        构造仅由 ``open_durable_actor`` 调用；command handle 必须已在
        ``executor`` 的唯一 worker thread 内创建。

        :param loop: actor 所属 opener event loop。
        :param executor: actor 独占的单 worker executor。
        :param command_handle: actor 独占 command handle。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._loop = loop
        self._executor = executor
        self._command_handle = command_handle
        self._stopped = False
        self._shutdown = False
        self._drain_future: Future[None] | None = None
        self._handle_close_future: Future[None] | None = None

    async def call(
        self,
        operation: Callable[[HostCommandHandle], T],
    ) -> T:
        """按提交顺序在 actor thread 执行一个 durable operation。

        ``asyncio.shield`` 只隔离 caller cancellation，不隐藏 operation 的成功
        或异常。caller 被取消后，底层 ``Future`` 仍会继续完成事务与
        after-commit wake，后续 actor call 仍可排队执行。

        :param operation: 接收 actor 私有 ``HostCommandHandle`` 的 typed callable。
        :returns: operation 返回值。
        :raises HostClosedError: actor 已停止接收新 operation 时抛出。
        :raises Exception: operation 异常原样透传。
        """

        return await asyncio.shield(self.submit(operation))

    def submit(
        self,
        operation: Callable[[HostCommandHandle], T],
    ) -> asyncio.Future[T]:
        """同步排队 operation，并返回 opener-loop awaitable future。

        该入口用于 ``watch_session_events`` 这类同步创建 async iterator 的
        public contract：watch 调用发生时立即把 cursor attach 排在后续 submit
        command 之前，同时不在 event loop 执行 SQLite。

        :param operation: 接收 actor 私有 command handle 的 typed callable。
        :returns: 绑定 opener loop 的 asyncio future。
        :raises HostClosedError: actor 已停止接收新 operation 时抛出。
        """

        self._require_opener_loop()
        if self._stopped:
            raise HostClosedError("Host durable actor is closed")
        future = self._executor.submit(operation, self._command_handle)
        return asyncio.wrap_future(future, loop=self._loop)

    async def stop_and_drain(self) -> None:
        """关闭新提交入口并等待此前 actor operation 全部收口。

        :returns: ``None``。
        :raises Exception: 排队 operation 的 bridge 失败时由其 caller 观察；
            drain barrier 本身不吞掉 executor failure。
        """

        self._require_opener_loop()
        if self._drain_future is None:
            self._stopped = True
            self._drain_future = self._executor.submit(_actor_barrier)
        await asyncio.shield(
            asyncio.wrap_future(self._drain_future, loop=self._loop)
        )

    async def close_handle(self) -> None:
        """在 actor thread 关闭 command handle 与其 durable store。

        调用方必须先完成 ``stop_and_drain``，确保 scheduler bridge 已收口。

        :returns: ``None``。
        :raises RuntimeError: 未先 drain actor 时抛出。
        :raises Exception: command handle 关闭失败时透传。
        """

        self._require_opener_loop()
        if self._drain_future is None:
            raise RuntimeError("DurableActor must drain before closing its handle")
        await asyncio.shield(
            asyncio.wrap_future(self._drain_future, loop=self._loop)
        )
        if self._handle_close_future is None:
            self._handle_close_future = self._executor.submit(
                _close_command_handle,
                self._command_handle,
            )
        await asyncio.shield(
            asyncio.wrap_future(self._handle_close_future, loop=self._loop)
        )

    def shutdown_executor(self) -> None:
        """回收 actor executor 与唯一 worker thread。

        :returns: ``None``。
        :raises RuntimeError: command handle 尚未关闭时抛出。
        """

        self._require_opener_loop()
        if self._shutdown:
            return
        if self._handle_close_future is None or not self._handle_close_future.done():
            raise RuntimeError(
                "DurableActor command handle must close before executor shutdown"
            )
        self._executor.shutdown(wait=True, cancel_futures=False)
        self._shutdown = True

    async def close(self) -> None:
        """按 drain、handle、executor 顺序幂等关闭 actor chain。

        :returns: ``None``。
        :raises Exception: drain 或 handle 关闭失败时透传。
        """

        if self._shutdown:
            return
        await self.stop_and_drain()
        await self.close_handle()
        self.shutdown_executor()

    def _require_opener_loop(self) -> None:
        """校验 actor 只由创建它的 opener event loop 使用。

        :returns: ``None``。
        :raises RuntimeError: 当前不在 opener event loop 时抛出。
        """

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError("DurableActor requires a running event loop") from exc
        if current_loop is not self._loop:
            raise RuntimeError("DurableActor cannot cross its opener event loop")


async def open_durable_actor(
    handle_factory: Callable[[], HostCommandHandle],
    *,
    thread_name_prefix: str,
) -> DurableActor:
    """在单 worker executor 中创建并返回 durable actor。

    :param handle_factory: 必须在 actor thread 创建 command handle/store/connection
        的同步 factory。
    :param thread_name_prefix: actor worker thread 名称前缀。
    :returns: 已打开 durable actor。
    :raises ValueError: thread 名称前缀为空时抛出。
    :raises Exception: command handle 创建失败时透传。
    """

    if thread_name_prefix.strip() == "":
        raise ValueError("thread_name_prefix must be non-empty")
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(
        max_workers=_ACTOR_MAX_WORKERS,
        thread_name_prefix=thread_name_prefix,
    )
    future = executor.submit(handle_factory)
    try:
        command_handle = await asyncio.shield(
            asyncio.wrap_future(future, loop=loop)
        )
    except BaseException:
        executor.shutdown(wait=True, cancel_futures=False)
        raise
    return DurableActor(
        loop=loop,
        executor=executor,
        command_handle=command_handle,
    )


__all__ = ["DurableActor", "open_durable_actor"]
