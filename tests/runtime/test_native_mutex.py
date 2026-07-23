"""严格 native 非阻塞 mutex 的资源与错误契约测试。

本模块覆盖 POSIX 真实互斥、子进程退出释放、Windows backend 机械路径、
busy 白名单、unsupported / unexpected 错误 fail-closed、partial fd cleanup
以及 handle close 幂等语义。
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

import dayu.runtime.native_mutex as native_mutex_module
from dayu.runtime.native_mutex import (
    StrictNativeMutexHandle,
    StrictNativeMutexUnavailableError,
    try_acquire_strict_native_mutex,
)

_CHILD_SCRIPT = """
import os
import sys
from pathlib import Path
from dayu.runtime.native_mutex import try_acquire_strict_native_mutex

handle = try_acquire_strict_native_mutex(Path(sys.argv[1]))
if handle is None:
    raise RuntimeError("child failed to acquire mutex")
print("READY", flush=True)
action = sys.argv[2]
if action == "exit":
    os._exit(0)
sys.stdin.readline()
handle.close()
print("CLOSED", flush=True)
"""


class _BusyPosixLocking:
    """始终报告明确 busy errno 的 POSIX flock fake。"""

    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 4

    def flock(self, file_descriptor: int, operation: int) -> None:
        """模拟 POSIX flock busy。

        :param file_descriptor: 待锁定文件描述符。
        :param operation: flock 操作标志。
        :returns: ``None``。
        :raises OSError: 始终抛出 ``EAGAIN``。
        """

        del file_descriptor, operation
        raise OSError(errno.EAGAIN, "busy")


class _UnexpectedPosixLocking:
    """始终报告非 busy errno 的 POSIX flock fake。"""

    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 4

    def __init__(self) -> None:
        """初始化可按 identity 断言的 native lock 错误。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.error = OSError(errno.EIO, "io failure")

    def flock(self, file_descriptor: int, operation: int) -> None:
        """模拟 POSIX flock 非预期失败。

        :param file_descriptor: 待锁定文件描述符。
        :param operation: flock 操作标志。
        :returns: ``None``。
        :raises OSError: 始终抛出 ``EIO``。
        """

        del file_descriptor, operation
        raise self.error


class _UnlockFailingPosixLocking:
    """acquire 成功但 release 失败的 POSIX flock fake。"""

    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 4

    def flock(self, file_descriptor: int, operation: int) -> None:
        """仅在 unlock 时模拟非预期失败。

        :param file_descriptor: 待操作文件描述符。
        :param operation: flock 操作标志。
        :returns: ``None``。
        :raises OSError: ``operation`` 为 unlock 时抛出 ``EIO``。
        """

        del file_descriptor
        if operation == self.LOCK_UN:
            raise OSError(errno.EIO, "unlock failure")


class _RecordingWindowsLocking:
    """记录 Windows locking 调用并允许成功的 fake。"""

    LK_NBLCK = 10
    LK_UNLCK = 11

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls: list[tuple[int, int, int]] = []

    def locking(self, file_descriptor: int, mode: int, byte_count: int) -> None:
        """记录一次 Windows locking 调用。

        :param file_descriptor: 待操作文件描述符。
        :param mode: lock 或 unlock 模式。
        :param byte_count: 锁定字节数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append((file_descriptor, mode, byte_count))


class _BusyWindowsLocking:
    """始终报告明确 lock contention 的 Windows locking fake。"""

    LK_NBLCK = 20
    LK_UNLCK = 21

    def locking(self, file_descriptor: int, mode: int, byte_count: int) -> None:
        """模拟 Windows lock violation。

        :param file_descriptor: 待操作文件描述符。
        :param mode: lock 或 unlock 模式。
        :param byte_count: 锁定字节数。
        :returns: ``None``。
        :raises OSError: acquire 时始终抛出 ``EACCES``。
        """

        del file_descriptor, mode, byte_count
        raise OSError(errno.EACCES, "lock violation")


class _CloseAfterFailure:
    """真实关闭 fd 后再报告 cleanup 失败的 callable。"""

    def __init__(self) -> None:
        """保存原始 ``os.close`` 并初始化调用记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.file_descriptors: list[int] = []
        self._real_close = os.close
        self.error = OSError(errno.EIO, "close failure")

    def __call__(self, file_descriptor: int) -> None:
        """关闭 fd 后模拟 cleanup 系统调用失败。

        :param file_descriptor: 待关闭文件描述符。
        :returns: ``None``。
        :raises OSError: 真实关闭后始终抛出 ``EIO``。
        """

        self.file_descriptors.append(file_descriptor)
        self._real_close(file_descriptor)
        raise self.error


def _unsupported_platform_name() -> str:
    """返回测试用 unsupported 平台名。

    :returns: unsupported 平台名。
    :raises Exception: 不主动抛出异常。
    """

    return "unsupported"


def _windows_platform_name() -> str:
    """返回测试用 Windows 平台名。

    :returns: Windows 对应的 ``os.name`` 值。
    :raises Exception: 不主动抛出异常。
    """

    return "nt"


def _posix_platform_name() -> str:
    """返回测试用 POSIX 平台名。

    :returns: POSIX 对应的 ``os.name`` 值。
    :raises Exception: 不主动抛出异常。
    """

    return "posix"


def _raise_open_error(path: Path) -> int:
    """模拟 lock file open 失败。

    :param path: 待打开 lock path。
    :returns: 不会正常返回。
    :raises OSError: 始终抛出 ``EACCES``。
    """

    del path
    raise OSError(errno.EACCES, "open failure")


def _raise_truncate_error(file_descriptor: int) -> None:
    """模拟 Windows lock byte 准备失败。

    :param file_descriptor: 已打开文件描述符。
    :returns: ``None``。
    :raises OSError: 始终抛出 ``EIO``。
    """

    del file_descriptor
    raise OSError(errno.EIO, "truncate failure")


def _fail_if_open_called(path: Path) -> int:
    """断言 unsupported backend 不得尝试打开文件。

    :param path: 不应被消费的 lock path。
    :returns: 不会正常返回。
    :raises AssertionError: 一旦被调用即抛出。
    """

    raise AssertionError(f"unexpected open: {path}")


def _start_lock_holder(lock_path: Path, *, action: str) -> subprocess.Popen[str]:
    """启动持有真实 native mutex 的子进程。

    :param lock_path: 子进程锁路径。
    :param action: ``wait`` 表示等待 stdin，``exit`` 表示直接进程退出。
    :returns: 已报告 ``READY`` 的子进程。
    :raises AssertionError: 子进程未成功持锁时抛出。
    """

    process = subprocess.Popen(
        [sys.executable, "-c", _CHILD_SCRIPT, str(lock_path), action],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "READY"
    return process


def _assert_fresh_acquire(lock_path: Path) -> None:
    """断言指定 key 当前可由 fresh handle 获取。

    :param lock_path: 待验证 lock path。
    :returns: ``None``。
    :raises AssertionError: mutex 仍 busy 时抛出。
    :raises StrictNativeMutexUnavailableError: native backend 失败时透传。
    """

    handle = try_acquire_strict_native_mutex(lock_path)
    assert isinstance(handle, StrictNativeMutexHandle)
    handle.close()


def test_same_key_busy_close_reacquire_and_different_key_parallel(tmp_path: Path) -> None:
    """同 key 必须互斥，不同 key 可并行，close 后可 fresh acquire。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一互斥或释放不变量不成立时抛出。
    """

    first_path = tmp_path / "first.lock"
    second_path = tmp_path / "second.lock"
    first = try_acquire_strict_native_mutex(first_path)
    assert isinstance(first, StrictNativeMutexHandle)
    assert try_acquire_strict_native_mutex(first_path) is None

    different = try_acquire_strict_native_mutex(second_path)
    assert isinstance(different, StrictNativeMutexHandle)
    different.close()

    first.close()
    first.close()
    assert first_path.exists()
    _assert_fresh_acquire(first_path)


def test_subprocess_normal_close_releases_mutex(tmp_path: Path) -> None:
    """子进程显式 close 后父进程必须可重新获取同 key。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 子进程未持锁或 close 后仍 busy 时抛出。
    """

    lock_path = tmp_path / "normal-close.lock"
    process = _start_lock_holder(lock_path, action="wait")
    assert try_acquire_strict_native_mutex(lock_path) is None
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write("close\n")
    process.stdin.flush()
    assert process.stdout.readline().strip() == "CLOSED"
    assert process.wait(timeout=10) == 0
    _assert_fresh_acquire(lock_path)


@pytest.mark.parametrize("termination", ["exit", "kill"])
def test_subprocess_exit_or_kill_releases_mutex(
    tmp_path: Path,
    termination: str,
) -> None:
    """进程正常退出或被 kill 后 OS 必须释放 mutex。

    :param tmp_path: pytest 临时目录。
    :param termination: ``exit`` 或 ``kill`` 终止方式。
    :returns: ``None``。
    :raises AssertionError: 进程退出后 mutex 仍不可获取时抛出。
    """

    lock_path = tmp_path / f"process-{termination}.lock"
    action = "exit" if termination == "exit" else "wait"
    process = _start_lock_holder(lock_path, action=action)
    if termination == "kill":
        assert try_acquire_strict_native_mutex(lock_path) is None
        process.kill()
    process.wait(timeout=10)
    _assert_fresh_acquire(lock_path)
    assert lock_path.exists()


def test_posix_busy_errno_is_only_busy_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSIX ``EAGAIN`` 必须返回 ``None`` 且关闭 partial fd。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: busy 被误报 unavailable 或 fd 泄漏时抛出。
    """

    monkeypatch.setattr(native_mutex_module, "_POSIX_LOCKING", _BusyPosixLocking())
    lock_path = tmp_path / "busy.lock"
    assert try_acquire_strict_native_mutex(lock_path) is None
    monkeypatch.undo()
    _assert_fresh_acquire(lock_path)


def test_unexpected_posix_errno_fails_closed_and_cleans_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 busy POSIX errno 必须 fail closed 且不泄漏 fd。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 错误被吞掉或 cleanup 后仍 busy 时抛出。
    """

    monkeypatch.setattr(
        native_mutex_module,
        "_POSIX_LOCKING",
        _UnexpectedPosixLocking(),
    )
    lock_path = tmp_path / "unexpected.lock"
    with pytest.raises(StrictNativeMutexUnavailableError, match="获取"):
        try_acquire_strict_native_mutex(lock_path)
    monkeypatch.undo()
    _assert_fresh_acquire(lock_path)


def test_partial_fd_cleanup_failure_overrides_busy_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """busy 后 fd cleanup 失败必须 fail closed，不能返回 ``None``。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: cleanup 失败被误报为普通 busy 时抛出。
    """

    closer = _CloseAfterFailure()
    monkeypatch.setattr(native_mutex_module, "_POSIX_LOCKING", _BusyPosixLocking())
    monkeypatch.setattr(native_mutex_module, "_close_file_descriptor", closer)
    with pytest.raises(StrictNativeMutexUnavailableError, match="关闭"):
        try_acquire_strict_native_mutex(tmp_path / "cleanup-failure.lock")
    assert len(closer.file_descriptors) == 1


def test_native_lock_and_partial_close_failures_preserve_structured_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """non-busy native lock 与 cleanup 双失败必须保留两个原始异常链。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 外层类型、结构化 cause、异常 identity 或 traceback 丢失时抛出。
    """

    locking = _UnexpectedPosixLocking()
    closer = _CloseAfterFailure()
    monkeypatch.setattr(native_mutex_module, "_POSIX_LOCKING", locking)
    monkeypatch.setattr(native_mutex_module, "_close_file_descriptor", closer)

    with pytest.raises(StrictNativeMutexUnavailableError, match="关闭") as raised:
        try_acquire_strict_native_mutex(tmp_path / "native-and-cleanup-failure.lock")

    combined_error = raised.value.__cause__
    assert isinstance(combined_error, ExceptionGroup)
    assert len(combined_error.exceptions) == 2
    prior_error, close_error = combined_error.exceptions
    assert isinstance(prior_error, StrictNativeMutexUnavailableError)
    assert prior_error.__cause__ is locking.error
    assert close_error is closer.error
    assert prior_error.__traceback__ is not None
    assert locking.error.__traceback__ is not None
    assert close_error.__traceback__ is not None
    assert len(closer.file_descriptors) == 1


def test_unsupported_backend_fails_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unsupported backend 必须在分配 fd 前 fail closed。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: unsupported backend 尝试 soft fallback 时抛出。
    """

    monkeypatch.setattr(
        native_mutex_module,
        "_native_platform_name",
        _unsupported_platform_name,
    )
    monkeypatch.setattr(native_mutex_module, "_open_lock_file", _fail_if_open_called)
    with pytest.raises(StrictNativeMutexUnavailableError, match="不支持"):
        try_acquire_strict_native_mutex(tmp_path / "unsupported.lock")


def test_supported_platform_without_stdlib_backend_fails_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """平台名受支持但 stdlib backend 缺失时也必须 fail closed。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: backend 缺失时仍尝试打开或降级时抛出。
    """

    monkeypatch.setattr(native_mutex_module, "_POSIX_LOCKING", None)
    monkeypatch.setattr(
        native_mutex_module,
        "_native_platform_name",
        _posix_platform_name,
    )
    monkeypatch.setattr(native_mutex_module, "_open_lock_file", _fail_if_open_called)
    with pytest.raises(StrictNativeMutexUnavailableError, match="不支持"):
        try_acquire_strict_native_mutex(tmp_path / "missing-backend.lock")


def test_open_failure_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """lock file open 失败必须包装为 unavailable。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: open 错误未被包装时抛出。
    """

    monkeypatch.setattr(native_mutex_module, "_open_lock_file", _raise_open_error)
    with pytest.raises(StrictNativeMutexUnavailableError, match="打开"):
        try_acquire_strict_native_mutex(tmp_path / "open-failure.lock")


def test_windows_backend_prepares_one_byte_and_unlocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows backend 必须锁定首字节并在 close 时 native unlock。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: Windows lock byte 或调用序列错误时抛出。
    """

    locking = _RecordingWindowsLocking()
    monkeypatch.setattr(native_mutex_module, "_native_platform_name", _windows_platform_name)
    monkeypatch.setattr(native_mutex_module, "_WINDOWS_LOCKING", locking)
    lock_path = tmp_path / "windows.lock"
    handle = try_acquire_strict_native_mutex(lock_path)
    assert isinstance(handle, StrictNativeMutexHandle)
    assert lock_path.stat().st_size >= 1
    handle.close()
    assert [call[1] for call in locking.calls] == [locking.LK_NBLCK, locking.LK_UNLCK]
    assert all(call[2] == 1 for call in locking.calls)


def test_windows_busy_and_truncate_failure_are_distinct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows lock violation 返回 busy，而 truncate 失败必须 unavailable。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 两类 closed outcome 被混淆时抛出。
    """

    monkeypatch.setattr(native_mutex_module, "_native_platform_name", _windows_platform_name)
    monkeypatch.setattr(native_mutex_module, "_WINDOWS_LOCKING", _BusyWindowsLocking())
    assert try_acquire_strict_native_mutex(tmp_path / "windows-busy.lock") is None

    monkeypatch.setattr(
        native_mutex_module,
        "_prepare_windows_lock_file",
        _raise_truncate_error,
    )
    with pytest.raises(StrictNativeMutexUnavailableError, match="准备"):
        try_acquire_strict_native_mutex(tmp_path / "windows-truncate.lock")


def test_release_error_is_cached_without_second_native_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native release 错误必须稳定 fail closed，重复 close 不重复 syscall。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: release 错误被吞掉或重复 close 改变结果时抛出。
    """

    locking = _UnlockFailingPosixLocking()
    monkeypatch.setattr(native_mutex_module, "_POSIX_LOCKING", locking)
    handle = try_acquire_strict_native_mutex(tmp_path / "release-error.lock")
    assert isinstance(handle, StrictNativeMutexHandle)
    with pytest.raises(StrictNativeMutexUnavailableError, match="释放") as first:
        handle.close()
    with pytest.raises(StrictNativeMutexUnavailableError) as repeated:
        handle.close()
    assert repeated.value is first.value


def test_descriptor_close_error_is_cached_after_native_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native unlock 后 descriptor close 错误必须稳定缓存且不重试 fd。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: close error 被吞掉或重复操作 descriptor 时抛出。
    """

    locking = _RecordingWindowsLocking()
    closer = _CloseAfterFailure()
    monkeypatch.setattr(
        native_mutex_module,
        "_native_platform_name",
        _windows_platform_name,
    )
    monkeypatch.setattr(native_mutex_module, "_WINDOWS_LOCKING", locking)
    handle = try_acquire_strict_native_mutex(tmp_path / "descriptor-close-error.lock")
    assert isinstance(handle, StrictNativeMutexHandle)
    monkeypatch.setattr(native_mutex_module, "_close_file_descriptor", closer)

    with pytest.raises(StrictNativeMutexUnavailableError, match="关闭") as first:
        handle.close()
    with pytest.raises(StrictNativeMutexUnavailableError) as repeated:
        handle.close()
    assert repeated.value is first.value
    assert len(closer.file_descriptors) == 1
