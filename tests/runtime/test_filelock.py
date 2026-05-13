"""``dayu.runtime.filelock`` 同步 wrapper 测试。

覆盖 parent directory 策略、context manager release、异常路径 release、
幂等 release、non-blocking timeout 包装，以及第一版不提供 stale takeover /
break lock / async wrapper 的公共边界。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.runtime.filelock import (
    RuntimeFileLock,
    RuntimeFileLockError,
    RuntimeFileLockOptions,
    RuntimeFileLockTimeoutError,
    RuntimeFileLockToken,
    file_lock,
)

_LOCK_FILE_NAME = "artifact.jsonl.lock"


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


def test_release_is_idempotent(tmp_path: Path) -> None:
    """重复 release 不得抛错，也不得删除 lock file。"""

    lock_path = _lock_path(tmp_path)
    token = file_lock(lock_path).acquire(timeout_seconds=0)

    token.release()
    token.release()

    assert token.released
    assert lock_path.exists()


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
