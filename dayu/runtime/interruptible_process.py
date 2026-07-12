"""层中立 interruptible process helper。

本模块只负责本地子进程启动、结果回收、terminate/kill 与 bounded close。
它不理解 Host Run / Attempt、Engine 协议、工具语义或业务事实。
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import multiprocessing.queues
import os
import queue
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Protocol, TypeAlias, cast

from dayu.contracts.json_value import JsonValue
from dayu.runtime.numeric import is_non_negative_finite_number

_DEFAULT_PROCESS_POLL_INTERVAL_SECONDS = 0.02
_DEFAULT_CLOSE_KILL_GRACE_SECONDS: Final[float] = 0.2
_PROCESS_GROUP_CLEANUP_SUPPORTED: Final[bool] = os.name == "posix"
_LOGGER = logging.getLogger(__name__)


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


class ProcessCleanupHandle(Protocol):
    """可被 runtime cleanup primitive 中断的进程协议。"""

    @property
    def pid(self) -> int | None:
        """返回进程 PID。

        :returns: 进程 PID；未启动时为 ``None``。
        """

        ...

    @property
    def exitcode(self) -> int | None:
        """返回进程退出码。

        :returns: 进程退出码；尚未退出时为 ``None``。
        """

        ...

    def terminate(self) -> None:
        """向进程发送 graceful terminate。

        :returns: ``None``。
        """

        ...

    def kill(self) -> None:
        """向进程发送 hard kill。

        :returns: ``None``。
        """

        ...

    def join(self, timeout: float | None = None) -> None:
        """等待进程退出。

        :param timeout: 最多等待的秒数；``None`` 表示无限等待。
        :returns: ``None``。
        """

        ...

    def is_alive(self) -> bool:
        """判断进程是否仍存活。

        :returns: 仍存活返回 ``True``。
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


class ProcessCleanupSignal(Enum):
    """进程 cleanup 信号类型。"""

    TERMINATE = "terminate"
    KILL = "kill"


class ProcessGroupCleanupReason(Enum):
    """进程组 cleanup 诊断原因。"""

    NOT_REQUESTED = "not_requested"
    GROUP_SIGNALED = "group_signaled"
    UNSUPPORTED = "unsupported"
    CHILD_PID_UNAVAILABLE = "child_pid_unavailable"
    CHILD_ALREADY_EXITED = "child_already_exited"
    PGID_UNAVAILABLE = "pgid_unavailable"
    CURRENT_PGID_UNAVAILABLE = "current_pgid_unavailable"
    PARENT_PGID_UNAVAILABLE = "parent_pgid_unavailable"
    PGID_MATCHES_CURRENT_PROCESS_GROUP = "pgid_matches_current_process_group"
    PGID_MATCHES_PARENT_PROCESS_GROUP = "pgid_matches_parent_process_group"
    GROUP_SIGNAL_FAILED = "group_signal_failed"


@dataclass(frozen=True, slots=True)
class ProcessGroupCleanupResult:
    """进程组 cleanup 诊断结果。

    :param process_group_supported: 当前运行环境是否支持安全进程组 cleanup。
    :param direct_signal_sent: 是否已向直接子进程发送 interrupt signal。
    :param group_signal_sent: 是否已向安全确认过的子进程组发送 interrupt signal。
    :param child_pid: 直接子进程 PID；不可用时为 ``None``。
    :param child_pgid: 直接子进程所属进程组 ID；不可用时为 ``None``。
    :param reason: 进程组 cleanup 的最终诊断原因。
    """

    process_group_supported: bool
    direct_signal_sent: bool
    group_signal_sent: bool
    child_pid: int | None
    child_pgid: int | None
    reason: ProcessGroupCleanupReason


@dataclass(frozen=True, slots=True)
class _SafeProcessGroupLookup:
    """安全子进程组解析结果。

    :param child_pgid: 可安全发送信号的子进程组 ID；不可用或不安全时为
        ``None``。
    :param diagnostic: 对应的 cleanup 诊断基线。
    """

    child_pgid: int | None
    diagnostic: ProcessGroupCleanupResult


def _process_group_cleanup_not_requested() -> ProcessGroupCleanupResult:
    """构造未请求进程组 cleanup 的默认诊断。

    :returns: 默认 cleanup 诊断。
    """

    return ProcessGroupCleanupResult(
        process_group_supported=False,
        direct_signal_sent=False,
        group_signal_sent=False,
        child_pid=None,
        child_pgid=None,
        reason=ProcessGroupCleanupReason.NOT_REQUESTED,
    )


@dataclass(frozen=True, slots=True)
class ProcessInterruptResult:
    """子进程 interrupt 操作结果。

    :param supported: 当前操作是否被 helper 支持。
    :param exited: 操作后进程是否已退出。
    :param exitcode: 子进程退出码。
    :param elapsed_seconds: 本次 interrupt 等待耗时。
    :param cleanup: 本次 direct child / process group cleanup 诊断。
    """

    supported: bool
    exited: bool
    exitcode: int | None
    elapsed_seconds: float
    cleanup: ProcessGroupCleanupResult = field(
        default_factory=_process_group_cleanup_not_requested
    )


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


@dataclass(slots=True)
class _ProcessCleanupProgress:
    """进程 handle 各资源 cleanup checkpoint。

    每个字段只在对应 documented cleanup API 成功返回后置为 ``True``；失败
    后的下一次 close 只补未完成步骤。
    """

    signal_completed: bool = False
    process_join_completed: bool = False
    process_close_completed: bool = False
    queue_close_completed: bool = False
    queue_cancel_join_completed: bool = False
    queue_join_completed: bool = False

    def is_completed(self) -> bool:
        """返回所有 cleanup checkpoint 是否完成。

        :returns: 所有步骤完成时返回 ``True``。
        """

        return (
            self.signal_completed
            and self.process_join_completed
            and self.process_close_completed
            and self.queue_close_completed
            and self.queue_cancel_join_completed
            and self.queue_join_completed
        )


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
        self._start_completed = False
        self._closed = False
        self._cleanup_completed = False
        self._cleanup_progress = _ProcessCleanupProgress()
        self._cleanup_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """启动子进程。

        :returns: ``None``。
        :raises RuntimeError: 重复启动时抛出。
        """

        if self._closed:
            raise RuntimeError("interruptible process has already been closed")
        if self._started:
            raise RuntimeError("interruptible process has already started")
        self._started = True
        self._process.start()
        self._start_completed = True

    async def wait(self, timeout_seconds: float | None) -> ProcessWaitResult:
        """等待子进程完成或 timeout。

        :param timeout_seconds: 等待秒数；``None`` 表示无限等待。
        :returns: 子进程等待结果。
        :raises ValueError: timeout 为负数、NaN 或无穷时抛出。
        """

        _validate_wait_timeout_seconds(timeout_seconds)
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
        return await interrupt_multiprocessing_process(
            self._process,
            signal_kind=ProcessCleanupSignal.TERMINATE,
            grace_seconds=grace_seconds,
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
        return await interrupt_multiprocessing_process(
            self._process,
            signal_kind=ProcessCleanupSignal.KILL,
            grace_seconds=grace_seconds,
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
        :raises RuntimeError: process / queue cleanup 未完成时抛出。
        :raises asyncio.CancelledError: caller 取消等待时透传；private cleanup 继续。
        """

        _validate_grace_seconds(kill_grace_seconds)
        self._closed = True
        async with self._cleanup_lock:
            if self._cleanup_completed:
                return
            cleanup_task = self._cleanup_task
            if cleanup_task is None or cleanup_task.done():
                cleanup_task = asyncio.create_task(
                    self._run_cleanup_attempt(
                        kill_grace_seconds=kill_grace_seconds
                    )
                )
                self._cleanup_task = cleanup_task
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            cleanup_task.add_done_callback(_observe_cancelled_close_cleanup_task)
            raise

    async def _run_cleanup_attempt(self, *, kill_grace_seconds: float) -> None:
        """执行一次可恢复的 resource cleanup attempt。

        process 与 queue checkpoint 相互独立；任一步普通异常都会被记录为首错，
        但不会阻止后续 checkpoint。本 task 不由 public caller 直接取消。

        :param kill_grace_seconds: process signal / join 的有限等待预算。
        :returns: ``None``。
        :raises Exception: cleanup checkpoint 的首个普通异常。
        """

        first_error: Exception | None = None
        try:
            process_may_have_spawned = self._process_may_have_spawned()
        except Exception as exc:
            first_error = exc
            # 无法读取 partial-start 状态时 fail-safe 尝试 documented process
            # cleanup；各步骤自己的异常仍不会阻止 queue cleanup。
            process_may_have_spawned = True

        if not self._cleanup_progress.signal_completed:
            try:
                if process_may_have_spawned and self._process.is_alive():
                    interrupt_result = await interrupt_multiprocessing_process(
                        self._process,
                        signal_kind=ProcessCleanupSignal.KILL,
                        grace_seconds=kill_grace_seconds,
                    )
                    if not interrupt_result.exited:
                        raise RuntimeError(
                            "interruptible process did not exit after cleanup kill"
                        )
                self._cleanup_progress.signal_completed = True
            except Exception as exc:
                first_error = _first_cleanup_error(first_error, exc)

        if (
            self._cleanup_progress.signal_completed
            and not self._cleanup_progress.process_join_completed
        ):
            try:
                if process_may_have_spawned:
                    await asyncio.to_thread(
                        self._process.join,
                        kill_grace_seconds,
                    )
                    if self._process.is_alive():
                        raise RuntimeError(
                            "interruptible process remained alive after cleanup join"
                        )
                self._cleanup_progress.process_join_completed = True
            except Exception as exc:
                first_error = _first_cleanup_error(first_error, exc)

        if (
            self._cleanup_progress.process_join_completed
            and not self._cleanup_progress.process_close_completed
        ):
            try:
                self._process.close()
                self._cleanup_progress.process_close_completed = True
            except Exception as exc:
                first_error = _first_cleanup_error(first_error, exc)

        if not self._cleanup_progress.queue_close_completed:
            try:
                self._result_queue.close()
                self._cleanup_progress.queue_close_completed = True
            except Exception as exc:
                first_error = _first_cleanup_error(first_error, exc)

        if not self._cleanup_progress.queue_cancel_join_completed:
            try:
                # Queue.join_thread() 没有 timeout 参数；先使用 documented
                # cancel-join gate，避免 feeder 异常时产生无界 close 等待。
                self._result_queue.cancel_join_thread()
                self._cleanup_progress.queue_cancel_join_completed = True
            except Exception as exc:
                first_error = _first_cleanup_error(first_error, exc)

        if (
            self._cleanup_progress.queue_cancel_join_completed
            and not self._cleanup_progress.queue_join_completed
        ):
            try:
                await asyncio.to_thread(self._result_queue.join_thread)
                self._cleanup_progress.queue_join_completed = True
            except Exception as exc:
                first_error = _first_cleanup_error(first_error, exc)

        if first_error is not None:
            raise first_error
        if not self._cleanup_progress.is_completed():
            raise RuntimeError("interruptible process cleanup remained incomplete")
        self._cleanup_completed = True

    def _process_may_have_spawned(self) -> bool:
        """判断 process cleanup API 是否需要按已 spawn 路径执行。

        本判断只选择 documented cleanup 操作，绝不恢复同一 handle 的 start
        权限；任何 start exception 后 ``_started`` gate 都保持不变。

        :returns: start 已成功，或失败后仍可观察到 child PID 时返回 ``True``。
        :raises Exception: 非 documented process state 异常原样抛出。
        """

        if self._start_completed:
            return True
        try:
            return self._process.pid is not None
        except (AssertionError, ValueError, OSError):
            return False

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

        if not self._start_completed:
            raise RuntimeError("interruptible process has not started")


def _first_cleanup_error(
    current: Exception | None,
    candidate: Exception,
) -> Exception:
    """保留 cleanup attempt 的首个普通异常。

    :param current: 已记录的首错；尚无错误时为 ``None``。
    :param candidate: 当前 checkpoint 异常。
    :returns: ``current`` 或首次出现的 ``candidate``。
    """

    if current is not None:
        return current
    return candidate


def _observe_cancelled_close_cleanup_task(task: asyncio.Future[None]) -> None:
    """消费 caller cancellation 后 private cleanup task 的最终异常。

    task 仍保存在 handle 上，后续 close 可以读取同一结果或启动补偿 attempt；
    observer 仅避免无人再次 close 时产生未观察异常。

    :param task: caller 已停止等待的 private cleanup task。
    :returns: ``None``。
    """

    if task.cancelled():
        return
    try:
        task.result()
    except Exception as exc:
        _LOGGER.warning(
            "interruptible_process.close_cleanup_failed_after_caller_cancel "
            "error_type=%s",
            exc.__class__.__name__,
            exc_info=exc,
        )


def _run_process_target(
    target: InterruptibleProcessTarget,
    result_queue: multiprocessing.queues.Queue[_ProcessMessage],
) -> None:
    """运行子进程目标并回传结构化结果。

    :param target: 可序列化子进程目标。
    :param result_queue: 父进程读取的结果队列。
    :returns: ``None``。
    """

    enter_new_process_session_if_supported()
    try:
        result_queue.put(_ProcessSucceeded(value=target()))
    except Exception as exc:
        result_queue.put(
            _ProcessFailed(
                error_type=exc.__class__.__name__,
                message=str(exc),
            )
        )


async def interrupt_multiprocessing_process(
    process: ProcessCleanupHandle,
    *,
    signal_kind: ProcessCleanupSignal,
    grace_seconds: float,
) -> ProcessInterruptResult:
    """中断 multiprocessing 子进程并尝试安全清理其子进程组。

    本 helper 是层中立 primitive，可供 ``InterruptibleProcessHandle`` 与
    其它 raw ``multiprocessing.Process`` 调用方复用。它先向直接子进程
    发送 signal，再仅在 POSIX pgid 已确认安全时向子进程组发送同类 signal。
    若调用方需要清理子进程启动的嵌套进程，子进程入口必须在启动嵌套
    进程前调用 ``enter_new_process_session_if_supported()``，或完成等价
    的 POSIX session / process-group setup；否则本 helper 会安全回退为
    直接子进程 cleanup 诊断。

    未启动或 PID 不可用的进程会返回 ``CHILD_PID_UNAVAILABLE`` 诊断，并
    且不会调用 signal 或 join。

    :param process: multiprocessing 子进程 cleanup handle。
    :param signal_kind: cleanup 信号类型。
    :param grace_seconds: signal 后最多等待的秒数。
    :returns: interrupt 结果与 process-group cleanup 诊断。
    :raises TypeError: ``grace_seconds`` 是 bool 或非数值时抛出。
    :raises ValueError: ``grace_seconds`` 为负数、NaN 或无穷时抛出。
    """

    _validate_grace_seconds(grace_seconds)
    started_at = time.monotonic()
    child_pid = _process_pid_or_none(process)
    if child_pid is None:
        return ProcessInterruptResult(
            supported=True,
            exited=not process.is_alive(),
            exitcode=process.exitcode,
            elapsed_seconds=time.monotonic() - started_at,
            cleanup=ProcessGroupCleanupResult(
                process_group_supported=_PROCESS_GROUP_CLEANUP_SUPPORTED,
                direct_signal_sent=False,
                group_signal_sent=False,
                child_pid=None,
                child_pgid=None,
                reason=ProcessGroupCleanupReason.CHILD_PID_UNAVAILABLE,
            ),
        )
    lookup = _resolve_safe_child_process_group(child_pid)
    direct_signal_sent = _signal_direct_process(process, signal_kind)
    cleanup = _cleanup_process_group_after_direct_signal(
        lookup,
        signal_kind=signal_kind,
        direct_signal_sent=direct_signal_sent,
    )
    await asyncio.to_thread(process.join, grace_seconds)
    return ProcessInterruptResult(
        supported=True,
        exited=not process.is_alive(),
        exitcode=process.exitcode,
        elapsed_seconds=time.monotonic() - started_at,
        cleanup=cleanup,
    )


def enter_new_process_session_if_supported() -> bool:
    """在支持的 POSIX 平台让当前子进程进入独立 session / process group。

    :returns: 成功进入独立 session / process group 返回 ``True``；当前平台不
        支持或 OS 拒绝时返回 ``False``。
    """

    if not _PROCESS_GROUP_CLEANUP_SUPPORTED:
        return False
    try:
        os.setsid()
    except OSError:
        return False
    return True


def _process_pid_or_none(process: ProcessCleanupHandle) -> int | None:
    """读取 cleanup handle PID，无法读取时返回 ``None``。

    :param process: 进程 cleanup handle。
    :returns: 进程 PID；未启动或不可用时返回 ``None``。
    """

    try:
        return process.pid
    except (ValueError, OSError):
        return None


def _resolve_safe_child_process_group(
    child_pid: int | None,
) -> _SafeProcessGroupLookup:
    """解析可安全 signal 的子进程组。

    :param child_pid: 直接子进程 PID。
    :returns: 安全 pgid 与诊断基线。
    """

    if not _PROCESS_GROUP_CLEANUP_SUPPORTED:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=None,
            reason=ProcessGroupCleanupReason.UNSUPPORTED,
            process_group_supported=False,
        )
    if child_pid is None:
        return _unsafe_process_group_lookup(
            child_pid=None,
            child_pgid=None,
            reason=ProcessGroupCleanupReason.CHILD_PID_UNAVAILABLE,
            process_group_supported=True,
        )
    try:
        child_pgid = os.getpgid(child_pid)
    except ProcessLookupError:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=None,
            reason=ProcessGroupCleanupReason.CHILD_ALREADY_EXITED,
            process_group_supported=True,
        )
    except OSError:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=None,
            reason=ProcessGroupCleanupReason.PGID_UNAVAILABLE,
            process_group_supported=True,
        )
    try:
        current_pgid = os.getpgrp()
    except OSError:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=child_pgid,
            reason=ProcessGroupCleanupReason.CURRENT_PGID_UNAVAILABLE,
            process_group_supported=True,
        )
    try:
        parent_pgid = os.getpgid(os.getppid())
    except OSError:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=child_pgid,
            reason=ProcessGroupCleanupReason.PARENT_PGID_UNAVAILABLE,
            process_group_supported=True,
        )
    if child_pgid == current_pgid:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=child_pgid,
            reason=ProcessGroupCleanupReason.PGID_MATCHES_CURRENT_PROCESS_GROUP,
            process_group_supported=True,
        )
    if child_pgid == parent_pgid:
        return _unsafe_process_group_lookup(
            child_pid=child_pid,
            child_pgid=child_pgid,
            reason=ProcessGroupCleanupReason.PGID_MATCHES_PARENT_PROCESS_GROUP,
            process_group_supported=True,
        )
    return _SafeProcessGroupLookup(
        child_pgid=child_pgid,
        diagnostic=ProcessGroupCleanupResult(
            process_group_supported=True,
            direct_signal_sent=False,
            group_signal_sent=False,
            child_pid=child_pid,
            child_pgid=child_pgid,
            reason=ProcessGroupCleanupReason.NOT_REQUESTED,
        ),
    )


def _unsafe_process_group_lookup(
    *,
    child_pid: int | None,
    child_pgid: int | None,
    reason: ProcessGroupCleanupReason,
    process_group_supported: bool,
) -> _SafeProcessGroupLookup:
    """构造不可进行进程组 signal 的解析结果。

    :param child_pid: 直接子进程 PID。
    :param child_pgid: 直接子进程进程组 ID。
    :param reason: 不可进行进程组 signal 的原因。
    :param process_group_supported: 当前平台是否支持进程组 cleanup。
    :returns: 解析结果。
    """

    return _SafeProcessGroupLookup(
        child_pgid=None,
        diagnostic=ProcessGroupCleanupResult(
            process_group_supported=process_group_supported,
            direct_signal_sent=False,
            group_signal_sent=False,
            child_pid=child_pid,
            child_pgid=child_pgid,
            reason=reason,
        ),
    )


def _signal_direct_process(
    process: ProcessCleanupHandle,
    signal_kind: ProcessCleanupSignal,
) -> bool:
    """向直接子进程发送 interrupt signal。

    :param process: multiprocessing 子进程。
    :param signal_kind: cleanup 信号类型。
    :returns: 已发送 signal 返回 ``True``；子进程已消失返回 ``False``。
    """

    try:
        if signal_kind is ProcessCleanupSignal.TERMINATE:
            process.terminate()
        else:
            process.kill()
    except (ProcessLookupError, OSError):
        return False
    return True


def _cleanup_process_group_after_direct_signal(
    lookup: _SafeProcessGroupLookup,
    *,
    signal_kind: ProcessCleanupSignal,
    direct_signal_sent: bool,
) -> ProcessGroupCleanupResult:
    """在直接子进程 signal 后尝试安全 signal 子进程组。

    :param lookup: 子进程组安全解析结果。
    :param signal_kind: cleanup 信号类型。
    :param direct_signal_sent: 是否已向直接子进程发送 signal。
    :returns: cleanup 诊断结果。
    """

    if lookup.child_pgid is None:
        return _cleanup_result_with_direct_signal(
            lookup.diagnostic,
            direct_signal_sent=direct_signal_sent,
            group_signal_sent=False,
            reason=lookup.diagnostic.reason,
        )
    try:
        os.killpg(lookup.child_pgid, _signal_number(signal_kind))
    except ProcessLookupError:
        return _cleanup_result_with_direct_signal(
            lookup.diagnostic,
            direct_signal_sent=direct_signal_sent,
            group_signal_sent=False,
            reason=ProcessGroupCleanupReason.CHILD_ALREADY_EXITED,
        )
    except OSError:
        return _cleanup_result_with_direct_signal(
            lookup.diagnostic,
            direct_signal_sent=direct_signal_sent,
            group_signal_sent=False,
            reason=ProcessGroupCleanupReason.GROUP_SIGNAL_FAILED,
        )
    return _cleanup_result_with_direct_signal(
        lookup.diagnostic,
        direct_signal_sent=direct_signal_sent,
        group_signal_sent=True,
        reason=ProcessGroupCleanupReason.GROUP_SIGNALED,
    )


def _cleanup_result_with_direct_signal(
    diagnostic: ProcessGroupCleanupResult,
    *,
    direct_signal_sent: bool,
    group_signal_sent: bool,
    reason: ProcessGroupCleanupReason,
) -> ProcessGroupCleanupResult:
    """补齐 direct signal / group signal 诊断字段。

    :param diagnostic: cleanup 诊断基线。
    :param direct_signal_sent: 是否已向直接子进程发送 signal。
    :param group_signal_sent: 是否已向进程组发送 signal。
    :param reason: 最终诊断原因。
    :returns: 完整 cleanup 诊断。
    """

    return ProcessGroupCleanupResult(
        process_group_supported=diagnostic.process_group_supported,
        direct_signal_sent=direct_signal_sent,
        group_signal_sent=group_signal_sent,
        child_pid=diagnostic.child_pid,
        child_pgid=diagnostic.child_pgid,
        reason=reason,
    )


def _signal_number(signal_kind: ProcessCleanupSignal) -> int:
    """返回 POSIX 进程组 signal number。

    :param signal_kind: cleanup 信号类型。
    :returns: POSIX signal number。
    """

    if signal_kind is ProcessCleanupSignal.TERMINATE:
        return signal.SIGTERM
    return signal.SIGKILL


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
    if not is_non_negative_finite_number(grace_seconds):
        raise ValueError("grace_seconds must be non-negative")


def _validate_wait_timeout_seconds(timeout_seconds: float | None) -> None:
    """校验 process wait timeout 秒数。

    :param timeout_seconds: timeout 秒数；``None`` 表示无限等待。
    :returns: ``None``。
    :raises ValueError: timeout 为负数、NaN 或正负无穷时抛出。
    """

    if timeout_seconds is None:
        return
    if not is_non_negative_finite_number(timeout_seconds):
        raise ValueError("timeout_seconds must be non-negative and finite")


__all__ = [
    "InterruptibleProcessCompleted",
    "InterruptibleProcessFailed",
    "InterruptibleProcessHandle",
    "InterruptibleProcessStillRunning",
    "InterruptibleProcessTarget",
    "ProcessCleanupSignal",
    "ProcessCleanupHandle",
    "ProcessGroupCleanupReason",
    "ProcessGroupCleanupResult",
    "ProcessInterruptResult",
    "ProcessWaitResult",
    "enter_new_process_session_if_supported",
    "interrupt_multiprocessing_process",
]
