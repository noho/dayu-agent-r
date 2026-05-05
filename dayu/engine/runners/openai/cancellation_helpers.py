"""协作式取消辅助。

本模块提供 :func:`await_or_cancel` 与私有异常 :class:`_RunnerInterrupted`，
用于把 :class:`~dayu.contracts.cancellation.CancellationToken` 的取消事实
观察并入 Runner 的阻塞边界（HTTP 建连、SSE chunk 等待、retry sleep 等）。

设计说明：

- 公共 :class:`CancellationToken` 协议只暴露**轮询**面（``is_cancelled``），
  不暴露 ``on_cancel`` 注册。本实现使用一个轻量轮询任务监听
  ``is_cancelled``，与目标 awaitable 用 ``asyncio.wait`` 同步竞速。
- 取消命中时抛出私有 :class:`_RunnerInterrupted`，仅在 Runner 内部传递；
  调用方在生成器顶层捕获后**直接退出**生成器，不再 yield 任何事件
  （取消例外，见 phase1-plan.md §6.4.1 / §7）。
- :class:`_RunnerInterrupted` 不是 :class:`asyncio.CancelledError` 的子类，
  避免被外部 ``except asyncio.CancelledError`` 误吞或导致任务被错误取消。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from typing import TypeVar

from dayu.contracts.cancellation import CancellationToken

_AwaitableResult = TypeVar("_AwaitableResult")

_DEFAULT_POLL_INTERVAL_SECONDS: float = 0.05


class _RunnerInterrupted(Exception):
    """Runner 内部协作式取消信号。

    仅在 :mod:`dayu.engine.runners.openai` 实现内部传递；**不**暴露
    在公共 ``__all__``，**不**写入任何公共方法的 ``:raises:`` 文档。
    """


async def _poll_cancellation(
    token: CancellationToken, *, interval_seconds: float
) -> None:
    """轮询 ``token``，命中后立即返回。

    :param token: 取消观察 token。
    :param interval_seconds: 轮询间隔秒数。
    :returns: 无返回值；token 命中时函数退出。
    """

    while not token.is_cancelled():
        await asyncio.sleep(interval_seconds)


_TaskResult = TypeVar("_TaskResult")


async def _cancel_task_and_wait(task: asyncio.Task[_TaskResult]) -> None:
    """取消并等待任务收口。

    :param task: 需要取消的任务。
    :returns: 无返回值。
    """

    if task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


async def await_or_cancel(
    awaitable: Awaitable[_AwaitableResult],
    *,
    token: CancellationToken,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> _AwaitableResult:
    """等待 ``awaitable``，token 取消先到时立即中止。

    :param awaitable: 需要等待的 awaitable / coroutine。
    :param token: 取消观察 token。
    :param poll_interval_seconds: 轮询 token 的间隔秒数。
    :returns: ``awaitable`` 的返回结果。

    :raises _RunnerInterrupted: 当 ``token.is_cancelled()`` 在 awaitable
        完成前先成立时抛出，由 Runner 顶层捕获。
    :raises Exception: 透传 ``awaitable`` 自身的异常。
    """

    if token.is_cancelled():
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise _RunnerInterrupted("cancelled before await")

    target_task: asyncio.Task[_AwaitableResult] = asyncio.ensure_future(
        awaitable
    )
    cancel_watcher: asyncio.Task[None] = asyncio.ensure_future(
        _poll_cancellation(token, interval_seconds=poll_interval_seconds)
    )
    try:
        done, _ = await asyncio.wait(
            {target_task, cancel_watcher},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_watcher in done and token.is_cancelled():
            await _cancel_task_and_wait(target_task)
            raise _RunnerInterrupted("cancelled during await")
        await _cancel_task_and_wait(cancel_watcher)
        return await target_task
    finally:
        if not cancel_watcher.done():
            await _cancel_task_and_wait(cancel_watcher)


__all__ = ["await_or_cancel"]
