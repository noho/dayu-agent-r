"""层中立同步文件锁 wrapper。

本模块统一封装第三方 ``filelock.FileLock``，只用于普通文件访问互斥。
它不表达 Host durable truth、EventLog ordering、Run / Attempt owner、
lease / fencing 或 recovery 判断，也不提供 async wrapper。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Final

from filelock import FileLock, Timeout

_THIRD_PARTY_DEFAULT_TIMEOUT_SECONDS: Final[float] = -1.0


class RuntimeFileLockError(Exception):
    """runtime file lock 基础异常。

    调用方可捕获本异常处理路径非法、parent directory 创建失败、acquire
    失败或 release 失败等 runtime file lock 语义错误。
    """


class RuntimeFileLockTimeoutError(RuntimeFileLockError):
    """runtime file lock acquire timeout 异常。

    第三方 ``filelock.Timeout`` 会被包装为本异常，避免上层直接依赖第三方
    exception 类型。
    """


@dataclass(frozen=True, slots=True)
class RuntimeFileLockOptions:
    """同步文件锁配置。

    :param lock_path: 显式 lock file 路径；调用方不得传业务文件路径并期待
        wrapper 自动派生。
    :param timeout_seconds: 默认 acquire timeout；``None`` 表示使用第三方
        ``FileLock`` 默认等待语义。
    :param create_parent_dirs: parent directory 缺失时是否创建。
    :raises RuntimeFileLockError: 路径或 timeout 配置非法时抛出。
    """

    lock_path: Path
    timeout_seconds: float | None = None
    create_parent_dirs: bool = True

    def __post_init__(self) -> None:
        """校验文件锁配置。

        :returns: ``None``。
        :raises RuntimeFileLockError: ``lock_path`` 或 timeout 非法时抛出。
        """

        _require_valid_lock_path(self.lock_path)
        _validate_timeout_seconds(self.timeout_seconds)


@dataclass(slots=True, init=False)
class RuntimeFileLockToken:
    """已获取同步文件锁的 token。

    :param lock_path: 已获取的 lock file 路径。
    :param third_party_lock: 内部第三方 lock 实例。
    """

    lock_path: Path
    released: bool
    _third_party_lock: FileLock = field(repr=False, compare=False)

    def __init__(self, *, lock_path: Path, third_party_lock: FileLock) -> None:
        """初始化文件锁 token。

        :param lock_path: 已获取的 lock file 路径。
        :param third_party_lock: 内部第三方 lock 实例。
        :returns: ``None``。
        :raises RuntimeFileLockError: ``lock_path`` 非法时抛出。
        """

        _require_valid_lock_path(lock_path)
        self.lock_path = lock_path
        self.released = False
        self._third_party_lock = third_party_lock

    def release(self) -> None:
        """释放文件锁；重复调用保持幂等。

        :returns: ``None``。
        :raises RuntimeFileLockError: 第三方 release 失败时抛出。
        """

        if self.released:
            return

        try:
            self._third_party_lock.release()
        except Exception as exc:
            raise RuntimeFileLockError("释放 runtime file lock 失败") from exc
        self.released = True

        try:
            _ensure_lock_file_marker_exists(self.lock_path)
        except Exception:
            pass


class RuntimeFileLock:
    """同步 runtime 文件锁。

    :param options: 文件锁配置。
    :raises RuntimeFileLockError: 配置非法时抛出。
    """

    __slots__ = ("_active_token", "_third_party_lock", "options")

    options: RuntimeFileLockOptions
    _third_party_lock: FileLock
    _active_token: RuntimeFileLockToken | None

    def __init__(self, options: RuntimeFileLockOptions) -> None:
        """初始化同步 runtime 文件锁。

        :param options: 文件锁配置。
        :returns: ``None``。
        :raises RuntimeFileLockError: 创建第三方 lock 失败时抛出。
        """

        self.options = options
        self._active_token = None
        try:
            self._third_party_lock = FileLock(str(options.lock_path))
        except Exception as exc:
            raise RuntimeFileLockError("创建 runtime file lock 失败") from exc

    def acquire(self, timeout_seconds: float | None = None) -> RuntimeFileLockToken:
        """同步获取文件锁。

        :param timeout_seconds: 本次 acquire timeout；``None`` 时使用
            ``RuntimeFileLockOptions.timeout_seconds``，若后者也是 ``None`` 则
            使用第三方 ``FileLock`` 默认等待语义。
        :returns: 已获取锁的 token。
        :raises RuntimeFileLockTimeoutError: non-blocking 或限时 acquire 超时时
            抛出。
        :raises RuntimeFileLockError: parent directory、路径或 acquire 失败时抛出。
        """

        effective_timeout = _effective_timeout_seconds(
            timeout_seconds=timeout_seconds,
            default_timeout_seconds=self.options.timeout_seconds,
        )
        _prepare_parent_directory(self.options)

        try:
            self._third_party_lock.acquire(timeout=effective_timeout)
        except Timeout as exc:
            raise RuntimeFileLockTimeoutError("获取 runtime file lock 超时") from exc
        except Exception as exc:
            raise RuntimeFileLockError("获取 runtime file lock 失败") from exc

        return RuntimeFileLockToken(
            lock_path=self.options.lock_path,
            third_party_lock=self._third_party_lock,
        )

    def __enter__(self) -> RuntimeFileLockToken:
        """进入同步 context manager 并获取文件锁。

        :returns: 已获取锁的 token。
        :raises RuntimeFileLockError: 获取锁失败时抛出。
        """

        token = self.acquire()
        self._active_token = token
        return token

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出同步 context manager 并释放文件锁。

        :param exc_type: context manager 内抛出的异常类型。
        :param exc: context manager 内抛出的异常实例。
        :param tb: context manager 内抛出的异常 traceback。
        :returns: ``None``。
        :raises RuntimeFileLockError: 释放锁失败时抛出。
        """

        token = self._active_token
        self._active_token = None
        if token is not None:
            token.release()


def file_lock(
    lock_path: str | Path,
    *,
    timeout_seconds: float | None = None,
    create_parent_dirs: bool = True,
) -> RuntimeFileLock:
    """构造同步 runtime 文件锁。

    :param lock_path: 显式 lock file 路径。
    :param timeout_seconds: 默认 acquire timeout；``None`` 表示使用第三方
        ``FileLock`` 默认等待语义。
    :param create_parent_dirs: parent directory 缺失时是否创建。
    :returns: 同步 runtime 文件锁。
    :raises RuntimeFileLockError: 配置非法或创建第三方 lock 失败时抛出。
    """

    return RuntimeFileLock(
        RuntimeFileLockOptions(
            lock_path=Path(lock_path),
            timeout_seconds=timeout_seconds,
            create_parent_dirs=create_parent_dirs,
        )
    )


def _effective_timeout_seconds(
    *,
    timeout_seconds: float | None,
    default_timeout_seconds: float | None,
) -> float:
    """计算传给第三方 FileLock 的 timeout。

    :param timeout_seconds: 本次 acquire timeout。
    :param default_timeout_seconds: wrapper 默认 timeout。
    :returns: 第三方 FileLock timeout；``-1`` 表示使用其默认无限等待语义。
    :raises RuntimeFileLockError: timeout 为负数时抛出。
    """

    selected = timeout_seconds if timeout_seconds is not None else default_timeout_seconds
    _validate_timeout_seconds(selected)
    if selected is None:
        return _THIRD_PARTY_DEFAULT_TIMEOUT_SECONDS
    return selected


def _prepare_parent_directory(options: RuntimeFileLockOptions) -> None:
    """按配置准备 lock file parent directory。

    :param options: 文件锁配置。
    :returns: ``None``。
    :raises RuntimeFileLockError: parent directory 缺失且不允许创建，或创建失败
        时抛出。
    """

    parent = options.lock_path.parent
    if parent.exists():
        if not parent.is_dir():
            raise RuntimeFileLockError("runtime file lock parent 不是目录")
        return

    if not options.create_parent_dirs:
        raise RuntimeFileLockError("runtime file lock parent directory 不存在")

    try:
        parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise RuntimeFileLockError("创建 runtime file lock parent directory 失败") from exc


def _require_valid_lock_path(lock_path: Path) -> None:
    """校验 lock file 路径。

    :param lock_path: lock file 路径。
    :returns: ``None``。
    :raises RuntimeFileLockError: 路径为空或不含文件名时抛出。
    """

    if str(lock_path).strip() == "" or lock_path.name.strip() == "":
        raise RuntimeFileLockError("runtime file lock 路径必须包含文件名")


def _ensure_lock_file_marker_exists(lock_path: Path) -> None:
    """确保 release 后 lock marker 文件仍存在。

    :param lock_path: lock file 路径。
    :returns: ``None``。
    :raises RuntimeFileLockError: 恢复 lock marker 文件失败时抛出。
    """

    try:
        lock_path.touch(exist_ok=True)
    except Exception as exc:
        raise RuntimeFileLockError("恢复 runtime file lock marker 文件失败") from exc


def _validate_timeout_seconds(timeout_seconds: float | None) -> None:
    """校验 timeout 秒数。

    :param timeout_seconds: timeout 秒数；``None`` 表示使用默认等待语义。
    :returns: ``None``。
    :raises RuntimeFileLockError: timeout 为负数时抛出。
    """

    if timeout_seconds is not None and timeout_seconds < 0:
        raise RuntimeFileLockError("runtime file lock timeout_seconds 不能为负数")


__all__ = [
    "RuntimeFileLock",
    "RuntimeFileLockError",
    "RuntimeFileLockOptions",
    "RuntimeFileLockTimeoutError",
    "RuntimeFileLockToken",
    "file_lock",
]
