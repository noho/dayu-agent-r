"""``dayu.runtime.filelock`` 同步 wrapper 测试。

覆盖 parent directory 策略、context manager release、异常路径 release、
幂等 release、non-blocking timeout 包装，以及第一版不提供 stale takeover /
break lock / async wrapper 的公共边界。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from filelock import FileLock

import dayu.runtime.filelock as filelock_module
from dayu.runtime.filelock import (
    RuntimeFileLock,
    RuntimeFileLockError,
    RuntimeFileLockOptions,
    RuntimeFileLockTimeoutError,
    RuntimeFileLockToken,
    file_lock,
)

_LOCK_FILE_NAME = "artifact.jsonl.lock"


class _CountingThirdPartyLock:
    """测试用第三方 lock 替身。"""

    def __init__(self) -> None:
        """初始化 release 调用计数。"""

        self.release_calls = 0

    def release(self) -> None:
        """记录底层 release 调用。

        :returns: ``None``。
        """

        self.release_calls += 1


def _raise_marker_restore_error(_lock_path: Path) -> None:
    """模拟 marker 恢复失败。

    :param _lock_path: lock file 路径，本测试不使用。
    :returns: 不返回；始终抛出 ``OSError``。
    :raises OSError: 始终抛出，用于模拟 touch 失败。
    """

    raise OSError("marker restore failed")


def _lock_path(tmp_path: Path) -> Path:
    """返回测试 lock file 路径。

    :param tmp_path: pytest 临时目录。
    :returns: lock file 路径。
    """

    return tmp_path / "locks" / _LOCK_FILE_NAME


def test_parent_directory_created_by_default(tmp_path: Path) -> None:
    """默认配置必须在 acquire 前创建 parent directory。"""

    lock_path = _lock_path(tmp_path)
    lock = file_lock(lock_path)

    token = lock.acquire(timeout_seconds=0)
    try:
        assert lock_path.parent.is_dir()
        assert lock_path.exists()
    finally:
        token.release()


def test_missing_parent_without_creation_raises_runtime_error(tmp_path: Path) -> None:
    """禁用 parent 创建且 parent 缺失时必须抛 wrapper 结构化异常。"""

    lock = file_lock(_lock_path(tmp_path), create_parent_dirs=False)

    with pytest.raises(RuntimeFileLockError):
        lock.acquire(timeout_seconds=0)


def test_context_manager_releases_on_normal_path(tmp_path: Path) -> None:
    """context manager 正常退出必须 release token。"""

    lock = file_lock(_lock_path(tmp_path))

    with lock as token:
        assert isinstance(token, RuntimeFileLockToken)
        assert not token.released

    assert token.released


def test_context_manager_releases_on_exception_path(tmp_path: Path) -> None:
    """context manager 异常退出也必须 release token。"""

    lock = file_lock(_lock_path(tmp_path))
    token: RuntimeFileLockToken | None = None

    with pytest.raises(ValueError, match="boom"):
        with lock as acquired_token:
            token = acquired_token
            raise ValueError("boom")

    assert token is not None
    assert token.released


def test_nested_context_manager_on_same_instance_fails_fast(tmp_path: Path) -> None:
    """同一 lock 实例嵌套 context 必须拒绝，避免覆盖 active token。"""

    lock = file_lock(_lock_path(tmp_path))

    with lock as outer_token:
        with pytest.raises(RuntimeFileLockError, match="already active"):
            with lock:
                raise AssertionError("nested context must not enter")

    assert outer_token.released


def test_manual_acquire_inside_context_fails_fast(tmp_path: Path) -> None:
    """context 持有 token 时同实例手动 acquire 必须拒绝。"""

    lock = file_lock(_lock_path(tmp_path))

    with lock as token:
        with pytest.raises(RuntimeFileLockError, match="already active"):
            lock.acquire(timeout_seconds=0)

    assert token.released


def test_context_enter_after_manual_acquire_fails_fast(tmp_path: Path) -> None:
    """手动 acquire 未释放时，同实例 context enter 必须拒绝。"""

    lock = file_lock(_lock_path(tmp_path))
    token = lock.acquire(timeout_seconds=0)
    try:
        with pytest.raises(RuntimeFileLockError, match="already active"):
            with lock:
                raise AssertionError("context must not enter")
    finally:
        token.release()


def test_manual_release_allows_same_instance_reacquire(tmp_path: Path) -> None:
    """手动 token release 后，同一 lock 实例必须允许再次 acquire。"""

    lock = file_lock(_lock_path(tmp_path))
    first_token = lock.acquire(timeout_seconds=0)
    first_token.release()

    second_token = lock.acquire(timeout_seconds=0)
    try:
        assert second_token is not first_token
        assert not second_token.released
    finally:
        second_token.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    """重复 release 不得抛错，也不得删除 lock file。"""

    lock_path = _lock_path(tmp_path)
    token = file_lock(lock_path).acquire(timeout_seconds=0)

    token.release()
    token.release()

    assert token.released
    assert lock_path.exists()


def test_release_marks_released_after_underlying_release_before_marker_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """底层 release 成功后 marker 恢复失败不得向调用方抛错。"""

    lock_path = _lock_path(tmp_path)
    third_party_lock = _CountingThirdPartyLock()

    monkeypatch.setattr(
        filelock_module,
        "_ensure_lock_file_marker_exists",
        _raise_marker_restore_error,
    )
    token = RuntimeFileLockToken(
        lock_path=lock_path,
        third_party_lock=cast(FileLock, third_party_lock),
    )

    token.release()

    assert token.released is True
    assert third_party_lock.release_calls == 1
    token.release()
    assert third_party_lock.release_calls == 1


def test_non_blocking_timeout_is_wrapped(tmp_path: Path) -> None:
    """底层 timeout 必须包装为 RuntimeFileLockTimeoutError。"""

    lock_path = _lock_path(tmp_path)
    first_token = file_lock(lock_path).acquire(timeout_seconds=0)
    try:
        second_lock = file_lock(lock_path)
        with pytest.raises(RuntimeFileLockTimeoutError):
            second_lock.acquire(timeout_seconds=0)
    finally:
        first_token.release()


def test_public_api_shape_and_non_goals_are_explicit(tmp_path: Path) -> None:
    """公共 API 只暴露同步 wrapper，不承诺 stale takeover 或 reentrant helper。"""

    options = RuntimeFileLockOptions(lock_path=_lock_path(tmp_path))
    lock = RuntimeFileLock(options)

    assert lock.options == options
    assert "force_release" not in vars(RuntimeFileLock)
    assert "break_lock" not in vars(RuntimeFileLock)
    assert "__aenter__" not in vars(RuntimeFileLock)
    assert "__aexit__" not in vars(RuntimeFileLock)
