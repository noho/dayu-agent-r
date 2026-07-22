"""层中立 strict-native 非阻塞进程 mutex。

本模块只拥有给定文件路径上的机械互斥与 OS handle 生命周期，不理解 Host、
Session、Run、durable truth、lease、recovery 或业务 key。POSIX 使用
``fcntl.flock``，Windows 使用 ``msvcrt.locking``；backend 不支持或任一非
busy 系统调用失败时严格 fail closed，不降级为 marker、soft lock 或 TTL。
"""

from __future__ import annotations

import errno
import os
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast


class _PosixLocking(Protocol):
    """POSIX ``fcntl`` 模块所需的最小强类型契约。"""

    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, file_descriptor: int, operation: int) -> None:
        """执行 native flock 操作。

        :param file_descriptor: 待操作文件描述符。
        :param operation: flock 操作标志。
        :returns: ``None``。
        :raises OSError: native flock 失败时抛出。
        """

        ...


class _WindowsLocking(Protocol):
    """Windows ``msvcrt`` 模块所需的最小强类型契约。"""

    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, file_descriptor: int, mode: int, byte_count: int) -> None:
        """执行 Windows native locking 操作。

        :param file_descriptor: 待操作文件描述符。
        :param mode: lock 或 unlock 模式。
        :param byte_count: 从当前文件位置开始锁定的字节数。
        :returns: ``None``。
        :raises OSError: native locking 失败时抛出。
        """

        ...


if os.name == "posix":
    import fcntl as _posix_locking_impl

    # typeshed 将 stdlib module 函数建模为 positional-only；本地最小协议只约束
    # 实际消费的常量与调用 shape，因此在 module boundary 做一次显式收窄。
    _POSIX_LOCKING: _PosixLocking | None = cast(
        _PosixLocking,
        _posix_locking_impl,
    )
else:
    _POSIX_LOCKING = None

if os.name == "nt":
    import msvcrt as _windows_locking_impl

    _WINDOWS_LOCKING: _WindowsLocking | None = cast(
        _WindowsLocking,
        _windows_locking_impl,
    )
else:
    _WINDOWS_LOCKING = None


class StrictNativeMutexUnavailableError(RuntimeError):
    """strict-native mutex backend、分配、acquire 或 release 不可用异常。"""


class _NativeMutexBackend(StrEnum):
    """当前支持的 strict-native backend 封闭集合。"""

    POSIX_FLOCK = "posix_flock"
    WINDOWS_LOCKING = "windows_locking"


class StrictNativeMutexHandle:
    """持有唯一 native file descriptor 的 mutex handle。

    handle 成功构造后独占其文件描述符。``close()`` 首次调用会尝试 native
    unlock 并无条件消费文件描述符；成功后重复调用无操作，失败后重复调用
    稳定重抛同一 unavailable 错误且不会重复操作已消费的 descriptor。

    :param file_descriptor: 已成功持锁且由本 handle 独占的文件描述符。
    :param backend: 获取该锁时使用的 native backend。
    """

    __slots__ = ("_backend", "_close_error", "_file_descriptor")

    def __init__(
        self,
        *,
        file_descriptor: int,
        backend: _NativeMutexBackend,
    ) -> None:
        """初始化已持锁 handle。

        :param file_descriptor: 已成功持锁的文件描述符。
        :param backend: 获取该锁时使用的 native backend。
        :returns: ``None``。
        :raises ValueError: 文件描述符为负数时抛出。
        """

        if file_descriptor < 0:
            raise ValueError("strict-native mutex file descriptor 必须非负")
        self._file_descriptor: int | None = file_descriptor
        self._backend = backend
        self._close_error: StrictNativeMutexUnavailableError | None = None

    def close(self) -> None:
        """释放 native mutex 并关闭 descriptor，重复调用保持幂等。

        :returns: ``None``。
        :raises StrictNativeMutexUnavailableError: native unlock 或 descriptor close
            失败时抛出；descriptor 仍被消费，不执行不安全的 close retry。
        """

        if self._file_descriptor is None:
            if self._close_error is not None:
                raise self._close_error
            return

        file_descriptor = self._file_descriptor
        # 先消费 capability，避免 close 结果不确定时重试并误关已复用的 fd。
        self._file_descriptor = None
        first_error: StrictNativeMutexUnavailableError | None = None
        try:
            _unlock_file_descriptor(file_descriptor, self._backend)
        except Exception as exc:
            first_error = StrictNativeMutexUnavailableError("释放 strict-native mutex 失败")
            first_error.__cause__ = exc

        try:
            _close_file_descriptor(file_descriptor)
        except Exception as exc:
            close_error = StrictNativeMutexUnavailableError("关闭 strict-native mutex file descriptor 失败")
            close_error.__cause__ = exc
            if first_error is None:
                first_error = close_error
            else:
                first_error.add_note(str(close_error))

        if first_error is not None:
            self._close_error = first_error
            raise first_error


def try_acquire_strict_native_mutex(path: Path) -> StrictNativeMutexHandle | None:
    """non-blocking 获取给定路径对应的 strict-native mutex。

    调用方拥有 key/path 派生与 parent directory 准备责任；本函数只打开给定
    lock file，并把明确 native contention 映射为 ``None``。文件是否已经存在
    不参与 owner 判断。

    :param path: 已由上层派生的 lock file 路径。
    :returns: 获取成功时返回独占 handle，明确 busy 时返回 ``None``。
    :raises StrictNativeMutexUnavailableError: backend 不支持，或 open、Windows
        lock byte 准备、native lock、partial cleanup 失败时抛出。
    """

    backend = _select_native_backend(_native_platform_name())
    try:
        file_descriptor = _open_lock_file(path)
    except Exception as exc:
        raise StrictNativeMutexUnavailableError("打开 strict-native mutex file 失败") from exc

    if backend is _NativeMutexBackend.WINDOWS_LOCKING:
        try:
            _prepare_windows_lock_file(file_descriptor)
        except Exception as exc:
            _close_partial_file_descriptor(file_descriptor, prior_error=exc)
            raise StrictNativeMutexUnavailableError("准备 Windows strict-native mutex lock byte 失败") from exc

    try:
        acquired = _lock_file_descriptor(file_descriptor, backend)
    except StrictNativeMutexUnavailableError as exc:
        _close_partial_file_descriptor(file_descriptor, prior_error=exc)
        raise
    except Exception as exc:
        _close_partial_file_descriptor(file_descriptor, prior_error=exc)
        raise StrictNativeMutexUnavailableError("获取 strict-native mutex 失败") from exc

    if not acquired:
        _close_partial_file_descriptor(file_descriptor, prior_error=None)
        return None

    return StrictNativeMutexHandle(
        file_descriptor=file_descriptor,
        backend=backend,
    )


def _native_platform_name() -> str:
    """返回当前 native backend 选择使用的平台名。

    :returns: 当前 ``os.name``。
    :raises Exception: 不主动抛出异常。
    """

    return os.name


def _select_native_backend(platform_name: str) -> _NativeMutexBackend:
    """选择当前严格支持的 native backend。

    :param platform_name: ``os.name`` 风格的平台名。
    :returns: 对应 native backend。
    :raises StrictNativeMutexUnavailableError: 平台或 stdlib backend 不可用时抛出。
    """

    if platform_name == "posix" and _POSIX_LOCKING is not None:
        return _NativeMutexBackend.POSIX_FLOCK
    if platform_name == "nt" and _WINDOWS_LOCKING is not None:
        return _NativeMutexBackend.WINDOWS_LOCKING
    raise StrictNativeMutexUnavailableError("当前平台不支持 strict-native mutex")


def _open_lock_file(path: Path) -> int:
    """打开或创建 lock file 并返回独立 descriptor。

    :param path: lock file 路径。
    :returns: 新打开的独立文件描述符。
    :raises OSError: native open 失败时抛出。
    """

    return os.open(path, os.O_RDWR | os.O_CREAT, 0o600)


def _prepare_windows_lock_file(file_descriptor: int) -> None:
    """确保 Windows locking 可锁定首字节并重置文件位置。

    :param file_descriptor: 已打开 lock file descriptor。
    :returns: ``None``。
    :raises OSError: fstat、truncate 或 seek 失败时抛出。
    """

    if os.fstat(file_descriptor).st_size < 1:
        os.ftruncate(file_descriptor, 1)
    os.lseek(file_descriptor, 0, os.SEEK_SET)


def _lock_file_descriptor(
    file_descriptor: int,
    backend: _NativeMutexBackend,
) -> bool:
    """尝试 non-blocking native lock 并只映射白名单 busy errno。

    :param file_descriptor: 已打开 lock file descriptor。
    :param backend: 当前 native backend。
    :returns: 获取成功返回 ``True``，明确 busy 返回 ``False``。
    :raises StrictNativeMutexUnavailableError: backend 消失或非 busy 错误时抛出。
    """

    try:
        if backend is _NativeMutexBackend.POSIX_FLOCK:
            locking = _POSIX_LOCKING
            if locking is None:
                raise StrictNativeMutexUnavailableError("POSIX strict-native mutex backend 不可用")
            locking.flock(file_descriptor, locking.LOCK_EX | locking.LOCK_NB)
            return True

        locking_windows = _WINDOWS_LOCKING
        if locking_windows is None:
            raise StrictNativeMutexUnavailableError("Windows strict-native mutex backend 不可用")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        locking_windows.locking(file_descriptor, locking_windows.LK_NBLCK, 1)
        return True
    except OSError as exc:
        if _is_busy_error(exc, backend):
            return False
        raise StrictNativeMutexUnavailableError("获取 strict-native mutex 失败") from exc


def _is_busy_error(error: OSError, backend: _NativeMutexBackend) -> bool:
    """判断 native lock 错误是否属于明确 contention 白名单。

    :param error: native lock 抛出的 ``OSError``。
    :param backend: 当前 native backend。
    :returns: 仅明确 would-block / lock-violation errno 返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if backend is _NativeMutexBackend.POSIX_FLOCK:
        return error.errno in {errno.EACCES, errno.EAGAIN}
    return error.errno in {errno.EACCES, errno.EDEADLK}


def _unlock_file_descriptor(
    file_descriptor: int,
    backend: _NativeMutexBackend,
) -> None:
    """释放 descriptor 上的 native mutex。

    :param file_descriptor: 当前 handle 独占的文件描述符。
    :param backend: 获取时使用的 native backend。
    :returns: ``None``。
    :raises StrictNativeMutexUnavailableError: backend 在 release 时不可用时抛出。
    :raises OSError: native unlock 或 seek 失败时抛出。
    """

    if backend is _NativeMutexBackend.POSIX_FLOCK:
        locking = _POSIX_LOCKING
        if locking is None:
            raise StrictNativeMutexUnavailableError("POSIX strict-native mutex backend 在 release 时不可用")
        locking.flock(file_descriptor, locking.LOCK_UN)
        return

    locking_windows = _WINDOWS_LOCKING
    if locking_windows is None:
        raise StrictNativeMutexUnavailableError("Windows strict-native mutex backend 在 release 时不可用")
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    locking_windows.locking(file_descriptor, locking_windows.LK_UNLCK, 1)


def _close_file_descriptor(file_descriptor: int) -> None:
    """关闭 mutex file descriptor。

    :param file_descriptor: 待关闭文件描述符。
    :returns: ``None``。
    :raises OSError: native close 失败时抛出。
    """

    os.close(file_descriptor)


def _close_partial_file_descriptor(
    file_descriptor: int,
    *,
    prior_error: Exception | None,
) -> None:
    """关闭未转移给 handle 的 partial descriptor。

    :param file_descriptor: partial allocation 文件描述符。
    :param prior_error: 触发 cleanup 的原错误；普通 busy 时为 ``None``。
    :returns: ``None``。
    :raises StrictNativeMutexUnavailableError: descriptor close 失败时抛出。
    """

    try:
        _close_file_descriptor(file_descriptor)
    except Exception as exc:
        cleanup_error = StrictNativeMutexUnavailableError("关闭 partial strict-native mutex file descriptor 失败")
        if prior_error is None:
            raise cleanup_error from exc

        # acquire 与 cleanup 是两个独立失败事实；用结构化 cause 同时保留原异常对象及 traceback。
        combined_error = ExceptionGroup(
            "strict-native mutex native 操作与 partial descriptor cleanup 均失败",
            [prior_error, exc],
        )
        raise cleanup_error from combined_error
