"""协作式取消等待 / race helper。

本模块为 Dayu 各层（Engine Runner、未来 Host / Service / UI）提供层中立
的协作式取消等待与三方 race 能力，统一以下语义：

- 公共 :class:`~dayu.contracts.cancellation.CancellationToken` 仅暴露
  **轮询**面（``is_cancelled()``）。本模块用一个轻量轮询任务监听
  ``is_cancelled``，与目标 awaitable / pending task 用
  ``asyncio.wait`` 同步竞速。
- **不**新增公共取消异常：cancellation 与 timeout 通过封闭联合结果分支
  表达，调用方按分支翻译为各自层内部信号。
- cancellation 优先：cancellation 与 timeout 同时命中时返回
  :class:`WaitCancelled`，不返回 :class:`WaitTimedOut`。
- ``asyncio.CancelledError`` 必须**透传**：若 helper 自身正在等待时被
  外层 ``Task.cancel()``，异常向上抛出，runtime helper 不吞，确保上层
  ``Task.cancel()`` 在调用栈任意位置仍生效。

这些 helper 的 task ownership 不同：

- :func:`await_or_cancel` / :func:`await_or_cancel_or_timeout` **拥有**
  awaitable：内部 ``ensure_future`` 包成 target task；token 或 timeout
  命中时**必须** ``target.cancel()`` 并 ``await`` 直至 done，**禁止**
  留下后台运行的 target task。awaitable 抛异常时同样保证 target task
  已 done。
- :func:`wait_for_or_cancel` **不拥有** ``pending`` task：调用方（Runner
  idle wait 中要跨循环复用 readany task）保留所有权，helper 仅 race，
  不取消 ``pending``；调用方按返回的 :data:`WaitOutcome` 自行决定下一步
  是否取消 ``pending``。

这些 helper 在退出前都会清理自己创建的内部 watcher / poller task，覆盖
所有路径（awaitable / pending 完成、token 命中、awaitable 抛异常、
timeout、外层 cancel），不留泄漏。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass
from typing import Final, Generic, TypeAlias, TypeVar

from dayu.contracts.cancellation import CancellationToken

_DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 0.05

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WaitCompleted(Generic[T]):
    """awaitable / pending 正常完成。

    :param value: 完成值。
    """

    value: T


@dataclass(frozen=True, slots=True)
class WaitCancelled:
    """cancellation token 命中。

    :param reason: 取消原因（来自 ``token.cancel_reason()``，可能为 ``None``）。
    """

    reason: str | None


@dataclass(frozen=True, slots=True)
class WaitTimedOut:
    """timeout 命中。

    :param elapsed_seconds: 自 helper 开始等待到 timeout 命中的秒数。
    """

    elapsed_seconds: float


WaitOutcome: TypeAlias = WaitCompleted[T] | WaitCancelled | WaitTimedOut
"""三方 race 的封闭联合结果。"""


async def await_or_cancel(
    awaitable: Awaitable[T],
    *,
    token: CancellationToken,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> WaitCompleted[T] | WaitCancelled:
    """等待 ``awaitable``，token 取消先到时立即中止并取消 awaitable。

    helper 拥有 awaitable 的所有权：

    - 若 ``awaitable`` 先完成，返回 :class:`WaitCompleted`。
    - 若 token 在 awaitable 完成前命中，helper **必须**
      ``target.cancel()`` 并 ``await`` 直至 target task done（吞掉
      ``asyncio.CancelledError``），再返回 :class:`WaitCancelled`，
      **禁止**留下后台运行的 target task。
    - awaitable 抛异常时透传，target task 已 done。
    - helper 自身被外层 ``Task.cancel()`` 取消时，先取消并等待
      target task 收口，避免后台孤儿协程泄漏，再重新抛出
      ``asyncio.CancelledError``。

    :param awaitable: 需要等待的 awaitable / coroutine。
    :param token: 取消观察 token。
    :param poll_interval_seconds: 轮询 token 的间隔秒数。
    :returns: :class:`WaitCompleted` 或 :class:`WaitCancelled`。

    :raises Exception: 透传 ``awaitable`` 自身的异常。
    :raises asyncio.CancelledError: helper 所在 task 被外层取消时透传，
        target task 已被取消并收口。
    """

    if token.is_cancelled():
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
            return WaitCancelled(reason=token.cancel_reason())
        target_task: asyncio.Task[T] = asyncio.ensure_future(awaitable)
        await _cancel_task_and_wait(target_task)
        return WaitCancelled(reason=token.cancel_reason())

    target_task: asyncio.Task[T] = asyncio.ensure_future(awaitable)
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
            return WaitCancelled(reason=token.cancel_reason())
        # target_task 完成（或异常）；watcher 还在跑则清理。
        return WaitCompleted(value=await target_task)
    except asyncio.CancelledError:
        # helper 自身被外层 ``Task.cancel()`` 取消：取消并等待 target task
        # 收口，避免后台孤儿协程泄漏，然后重新抛出 ``CancelledError``。
        await _cancel_task_and_wait(target_task)
        raise
    finally:
        if not cancel_watcher.done():
            await _cancel_task_and_wait(cancel_watcher)


async def wait_for_or_cancel(
    pending: asyncio.Task[T],
    *,
    token: CancellationToken,
    timeout_seconds: float | None,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> WaitOutcome[T]:
    """对 ``pending`` task 做「pending vs cancellation vs timeout」三方 race。

    helper **不拥有** ``pending`` task；调用方保留所有权，并按返回的
    :data:`WaitOutcome` 自行决定下一步是否取消 ``pending`` 或继续复用。

    语义优先级：

    - cancellation 与 timeout 同时命中时返回 :class:`WaitCancelled`。
    - ``timeout_seconds=None`` 表示无 timeout，仅做 pending vs cancel 的
      二方 race；不会返回 :class:`WaitTimedOut`。
    - ``pending`` 命中时返回 :class:`WaitCompleted`，``pending`` 仍由调用
      方持有（可能仍有未消费完的内部状态）。

    :param pending: 调用方持有的 pending task。
    :param token: 取消观察 token。
    :param timeout_seconds: 单次等待 timeout 秒数；``None`` 表示无 timeout。
    :param poll_interval_seconds: 轮询 token 的间隔秒数。
    :returns: 封闭联合 :data:`WaitOutcome`。

    :raises Exception: 透传 ``pending`` 自身的异常；``pending`` 完成分支会
        读取 ``pending.result()``，因此 pending task 中抛出的异常会从本
        helper 直接传播给调用方。
    """

    started_at = time.monotonic()
    if token.is_cancelled():
        return WaitCancelled(reason=token.cancel_reason())

    cancel_watcher: asyncio.Task[None] = asyncio.ensure_future(
        _poll_cancellation(token, interval_seconds=poll_interval_seconds)
    )
    try:
        done, _ = await asyncio.wait(
            {pending, cancel_watcher},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        # cancellation 优先：watcher 命中 + token 已取消，无论 pending
        # 是否同时完成或 timeout 是否同时命中。
        if cancel_watcher in done and token.is_cancelled():
            return WaitCancelled(reason=token.cancel_reason())
        if pending in done:
            return WaitCompleted(value=pending.result())
        elapsed = time.monotonic() - started_at
        return WaitTimedOut(elapsed_seconds=elapsed)
    finally:
        if not cancel_watcher.done():
            await _cancel_task_and_wait(cancel_watcher)


async def await_or_cancel_or_timeout(
    awaitable: Awaitable[T],
    *,
    token: CancellationToken,
    timeout_seconds: float,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> WaitCompleted[T] | WaitCancelled | WaitTimedOut:
    """等待 ``awaitable``，并同时监听 token 取消与 timeout。

    helper 拥有 awaitable 的所有权：

    - 若 ``awaitable`` 先完成，返回 :class:`WaitCompleted`。
    - 若 token 在 awaitable 完成前命中，取消并等待 target task 收口，
      返回 :class:`WaitCancelled`。
    - 若 timeout 在 awaitable 完成前命中，取消并等待 target task 收口，
      返回 :class:`WaitTimedOut`。
    - cancellation 与 timeout 竞争时 cancellation 优先。
    - helper 自身被外层 ``Task.cancel()`` 取消时，取消并等待 target task
      收口，然后重新抛出 ``asyncio.CancelledError``。

    :param awaitable: 需要等待的 awaitable / coroutine。
    :param token: 取消观察 token。
    :param timeout_seconds: timeout 秒数。
    :param poll_interval_seconds: 轮询 token 的间隔秒数。
    :returns: :class:`WaitCompleted`、:class:`WaitCancelled` 或
        :class:`WaitTimedOut`。

    :raises Exception: 透传 ``awaitable`` 自身的异常。
    :raises asyncio.CancelledError: helper 所在 task 被外层取消，或
        ``awaitable`` 自身抛出 ``asyncio.CancelledError`` 时透传。
    """

    if token.is_cancelled():
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
            return WaitCancelled(reason=token.cancel_reason())
        target_task: asyncio.Task[T] = asyncio.ensure_future(awaitable)
        await _cancel_task_and_wait(target_task)
        return WaitCancelled(reason=token.cancel_reason())

    started_at = time.monotonic()
    target_task: asyncio.Task[T] = asyncio.ensure_future(awaitable)
    cancel_watcher: asyncio.Task[None] = asyncio.ensure_future(
        _poll_cancellation(token, interval_seconds=poll_interval_seconds)
    )
    try:
        done, _ = await asyncio.wait(
            {target_task, cancel_watcher},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_watcher in done and token.is_cancelled():
            await _cancel_task_and_wait(target_task)
            return WaitCancelled(reason=token.cancel_reason())
        if target_task in done:
            return WaitCompleted(value=await target_task)
        if token.is_cancelled():
            await _cancel_task_and_wait(target_task)
            return WaitCancelled(reason=token.cancel_reason())
        await _cancel_task_and_wait(target_task)
        return WaitTimedOut(elapsed_seconds=time.monotonic() - started_at)
    except asyncio.CancelledError:
        await _cancel_task_and_wait(target_task)
        raise
    finally:
        if not cancel_watcher.done():
            await _cancel_task_and_wait(cancel_watcher)


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


_AnyTaskResult = TypeVar("_AnyTaskResult")


async def _cancel_task_and_wait(
    task: asyncio.Task[_AnyTaskResult],
) -> None:
    """取消并等待任务收口。

    :param task: 需要取消的任务（任意结果类型）。
    :returns: 无返回值；吞掉 ``asyncio.CancelledError`` 与任务自身异常。
    """

    if task.done():
        # 已完成的 task 仍读一次结果以避免 "Task exception was never retrieved"
        with suppress(asyncio.CancelledError, Exception):
            task.result()
        return
    task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


__all__ = [
    "WaitCompleted",
    "WaitCancelled",
    "WaitTimedOut",
    "WaitOutcome",
    "await_or_cancel",
    "await_or_cancel_or_timeout",
    "wait_for_or_cancel",
]
