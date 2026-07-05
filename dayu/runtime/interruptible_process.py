"""层中立 interruptible process helper。

本模块只负责本地子进程启动、结果回收、terminate/kill 与 bounded close。
它不理解 Host Run / Attempt、Engine 协议、工具语义或业务事实。
"""

from __future__ import annotations

import asyncio
import math
import multiprocessing
import multiprocessing.queues
import queue
import time
from dataclasses import dataclass
from typing import Final, Protocol, TypeAlias, cast

from dayu.contracts.json_value import JsonValue

_DEFAULT_PROCESS_POLL_INTERVAL_SECONDS = 0.02
_DEFAULT_CLOSE_KILL_GRACE_SECONDS: Final[float] = 0.2


class InterruptibleProcessTarget(Protocol):
    """子进程可执行目标协议。

    目标必须可被 ``multiprocessing`` 序列化，并返回 JSON-like 结果。
    """

    def __call__(self) -> JsonValue:
        """执行子进程工作。

        :returns: JSON-like 结果。
        :raises Exception: 业务异常会被 worker 捕获并转为失败消息。
        """

        ...


@dataclass(frozen=True, slots=True)
class InterruptibleProcessCompleted:
    """子进程正常返回结果。

    :param value: 子进程返回的 JSON-like 值。
    :param exitcode: 子进程退出码。
    """

    value: JsonValue
    exitcode: int | None


@dataclass(frozen=True, slots=True)
class InterruptibleProcessFailed:
    """子进程以异常或异常退出收口。

    :param error_type: 异常类型或退出错误码。
    :param message: 诊断说明。
    :param exitcode: 子进程退出码。
    """

    error_type: str
    message: str
    exitcode: int | None


@dataclass(frozen=True, slots=True)
class InterruptibleProcessStillRunning:
    """子进程仍在运行。

    :param elapsed_seconds: 等待耗时秒数。
    """

    elapsed_seconds: float


ProcessWaitResult: TypeAlias = (
    InterruptibleProcessCompleted
    | InterruptibleProcessFailed
    | InterruptibleProcessStillRunning
)
"""子进程等待结果封闭联合。"""


@dataclass(frozen=True, slots=True)
class ProcessInterruptResult:
    """子进程 interrupt 操作结果。

    :param supported: 当前操作是否被 helper 支持。
    :param exited: 操作后进程是否已退出。
    :param exitcode: 子进程退出码。
    :param elapsed_seconds: 本次 interrupt 等待耗时。
    """

    supported: bool
    exited: bool
    exitcode: int | None
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class _ProcessSucceeded:
    """worker 回传成功值。"""

    value: JsonValue


@dataclass(frozen=True, slots=True)
class _ProcessFailed:
    """worker 回传失败值。"""

    error_type: str
    message: str


_ProcessMessage: TypeAlias = _ProcessSucceeded | _ProcessFailed


class InterruptibleProcessHandle:
    """可 interrupt 的本地子进程 handle。"""

    def __init__(self, target: InterruptibleProcessTarget) -> None:
        """初始化子进程 handle。

        :param target: 可序列化子进程目标。
        :returns: ``None``。
        """

        self._context = multiprocessing.get_context("spawn")
        self._result_queue = cast(
            "multiprocessing.queues.Queue[_ProcessMessage]",
            self._context.Queue(maxsize=1),
        )
        self._process = self._context.Process(
            target=_run_process_target,
            args=(target, self._result_queue),
        )
        self._started = False
        self._closed = False

    def start(self) -> None:
        """启动子进程。

        :returns: ``None``。
        :raises RuntimeError: 重复启动时抛出。
        """

        if self._started:
            raise RuntimeError("interruptible process has already started")
        self._started = True
        self._process.start()

    async def wait(self, timeout_seconds: float | None) -> ProcessWaitResult:
        """等待子进程完成或 timeout。

        :param timeout_seconds: 等待秒数；``None`` 表示无限等待。
        :returns: 子进程等待结果。
        """

        self._require_started()
        started_at = time.monotonic()
        while True:
            message = self._read_message()
            if message is not None:
                await asyncio.to_thread(self._process.join, 0)
                return _wait_result_from_message(message, self._process.exitcode)
            if not self._process.is_alive():
                await asyncio.to_thread(self._process.join, 0)
                message = self._read_message()
                if message is not None:
                    return _wait_result_from_message(message, self._process.exitcode)
                return InterruptibleProcessFailed(
                    error_type="process_exited_without_result",
                    message="interruptible process exited without a result message",
                    exitcode=self._process.exitcode,
                )
            if timeout_seconds is not None:
                elapsed = time.monotonic() - started_at
                if elapsed >= timeout_seconds:
                    return InterruptibleProcessStillRunning(
                        elapsed_seconds=elapsed
                    )
            await asyncio.sleep(_DEFAULT_PROCESS_POLL_INTERVAL_SECONDS)

    async def terminate(self, grace_seconds: float) -> ProcessInterruptResult:
        """请求子进程 graceful terminate 并 bounded join。

        :param grace_seconds: terminate 后最多等待的秒数。
        :returns: interrupt 操作结果。
        :raises TypeError: ``grace_seconds`` 是 bool 或非数值时抛出。
        :raises ValueError: ``grace_seconds`` 为负数、NaN 或无穷时抛出。
        """

        _validate_grace_seconds(grace_seconds)
        self._require_started()
        if not self._process.is_alive():
            return ProcessInterruptResult(
                supported=True,
                exited=True,
                exitcode=self._process.exitcode,
                elapsed_seconds=0.0,
            )
        started_at = time.monotonic()
        self._process.terminate()
        await asyncio.to_thread(self._process.join, grace_seconds)
        return ProcessInterruptResult(
            supported=True,
            exited=not self._process.is_alive(),
            exitcode=self._process.exitcode,
            elapsed_seconds=time.monotonic() - started_at,
        )

    async def kill(self, grace_seconds: float) -> ProcessInterruptResult:
        """请求子进程 hard kill 并 bounded join。

        :param grace_seconds: kill 后最多等待的秒数。
        :returns: interrupt 操作结果。
        :raises TypeError: ``grace_seconds`` 是 bool 或非数值时抛出。
        :raises ValueError: ``grace_seconds`` 为负数、NaN 或无穷时抛出。
        """

        _validate_grace_seconds(grace_seconds)
        self._require_started()
        if not self._process.is_alive():
            return ProcessInterruptResult(
                supported=True,
                exited=True,
                exitcode=self._process.exitcode,
                elapsed_seconds=0.0,
            )
        started_at = time.monotonic()
        self._process.kill()
        await asyncio.to_thread(self._process.join, grace_seconds)
        return ProcessInterruptResult(
            supported=True,
            exited=not self._process.is_alive(),
            exitcode=self._process.exitcode,
            elapsed_seconds=time.monotonic() - started_at,
        )

    async def close(
        self,
        *,
        kill_grace_seconds: float = _DEFAULT_CLOSE_KILL_GRACE_SECONDS,
    ) -> None:
        """关闭本地进程 handle 与队列资源。

        若进程仍存活，本方法会先 best-effort kill；调用方不应把这个结果解释
        为业务事实。

        :param kill_grace_seconds: best-effort kill 后最多等待的秒数。
        :returns: ``None``。
        :raises TypeError: ``kill_grace_seconds`` 是 bool 或非数值时抛出。
        :raises ValueError: ``kill_grace_seconds`` 为负数、NaN 或无穷时抛出。
        """

        _validate_grace_seconds(kill_grace_seconds)
        if self._closed:
            return
        self._closed = True
        if self._started and self._process.is_alive():
            await self.kill(grace_seconds=kill_grace_seconds)
        if self._started:
            await asyncio.to_thread(self._process.join, 0)
            self._process.close()
        self._result_queue.close()
        await asyncio.to_thread(self._result_queue.join_thread)

    def _read_message(self) -> _ProcessMessage | None:
        """读取单条 worker 消息。

        :returns: 成功 / 失败消息；队列为空时返回 ``None``。
        """

        try:
            return self._result_queue.get_nowait()
        except queue.Empty:
            return None

    def _require_started(self) -> None:
        """校验子进程已启动。

        :returns: ``None``。
        :raises RuntimeError: 子进程尚未启动时抛出。
        """

        if not self._started:
            raise RuntimeError("interruptible process has not started")


def _run_process_target(
    target: InterruptibleProcessTarget,
    result_queue: multiprocessing.queues.Queue[_ProcessMessage],
) -> None:
    """运行子进程目标并回传结构化结果。

    :param target: 可序列化子进程目标。
    :param result_queue: 父进程读取的结果队列。
    :returns: ``None``。
    """

    try:
        result_queue.put(_ProcessSucceeded(value=target()))
    except Exception as exc:
        result_queue.put(
            _ProcessFailed(
                error_type=exc.__class__.__name__,
                message=str(exc),
            )
        )


def _wait_result_from_message(
    message: _ProcessMessage, exitcode: int | None
) -> InterruptibleProcessCompleted | InterruptibleProcessFailed:
    """把 worker 消息转换为等待结果。

    :param message: worker 回传消息。
    :param exitcode: 子进程退出码。
    :returns: 完成或失败等待结果。
    """

    if isinstance(message, _ProcessSucceeded):
        return InterruptibleProcessCompleted(value=message.value, exitcode=exitcode)
    return InterruptibleProcessFailed(
        error_type=message.error_type,
        message=message.message,
        exitcode=exitcode,
    )


def _validate_grace_seconds(grace_seconds: float) -> None:
    """校验 cleanup grace 秒数。

    :param grace_seconds: grace 秒数。
    :returns: ``None``。
    :raises TypeError: ``grace_seconds`` 是 bool 或非数值时抛出。
    :raises ValueError: 非有限非负数时抛出。
    """

    if isinstance(grace_seconds, bool) or not isinstance(grace_seconds, int | float):
        raise TypeError("grace_seconds must be a finite number")
    if not math.isfinite(grace_seconds):
        raise ValueError("grace_seconds must be finite")
    if grace_seconds < 0:
        raise ValueError("grace_seconds must be non-negative")


__all__ = [
    "InterruptibleProcessCompleted",
    "InterruptibleProcessFailed",
    "InterruptibleProcessHandle",
    "InterruptibleProcessStillRunning",
    "InterruptibleProcessTarget",
    "ProcessInterruptResult",
    "ProcessWaitResult",
]
