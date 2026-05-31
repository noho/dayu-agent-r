"""``dayu.runtime.filelock`` 同步 wrapper 测试。

覆盖 parent directory 策略、context manager release、异常路径 release、
幂等 release、non-blocking timeout 包装，以及第一版不提供 stale takeover /
break lock / async wrapper 的公共边界。
"""

from __future__ import annotations

from dataclasses import fields
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


class _FailingThirdPartyLock:
    """测试用 release 失败第三方 lock 替身。"""

    def __init__(self) -> None:
        """初始化 release 调用计数。"""

        self.release_calls = 0

    def release(self) -> None:
        """记录调用后抛出底层 release 错误。

        :returns: 不会返回。
        :raises OSError: 始终抛出测试错误。
        """

        self.release_calls += 1
        raise OSError("release failed")


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
    """context manager 正常退出后独立 lock 必须可再次获取。"""

    lock_path = _lock_path(tmp_path)
    lock = file_lock(lock_path)

    with lock as token:
        assert isinstance(token, RuntimeFileLockToken)

    second_token = file_lock(lock_path).acquire(timeout_seconds=0)
    try:
        assert isinstance(second_token, RuntimeFileLockToken)
    finally:
        second_token.release()


def test_context_manager_releases_on_exception_path(tmp_path: Path) -> None:
    """context manager 异常退出后独立 lock 必须可再次获取。"""

    lock_path = _lock_path(tmp_path)
    lock = file_lock(lock_path)
    token: RuntimeFileLockToken | None = None

    with pytest.raises(ValueError, match="boom"):
        with lock as acquired_token:
            token = acquired_token
            raise ValueError("boom")

    assert token is not None
    second_token = file_lock(lock_path).acquire(timeout_seconds=0)
    try:
        assert isinstance(second_token, RuntimeFileLockToken)
    finally:
        second_token.release()


def test_nested_context_manager_on_same_instance_fails_fast_without_leak(
    tmp_path: Path,
) -> None:
    """同一实例嵌套 context 必须拒绝且不得泄漏外层 token。"""

    lock_path = _lock_path(tmp_path)
    lock = file_lock(lock_path)

    with lock:
        with pytest.raises(RuntimeFileLockError, match="不支持嵌套"):
            with lock:
                raise AssertionError("nested context must not enter")

    second_token = file_lock(lock_path).acquire(timeout_seconds=0)
    try:
        assert isinstance(second_token, RuntimeFileLockToken)
    finally:
        second_token.release()


def test_context_manager_release_failure_clears_context_token(
    tmp_path: Path,
) -> None:
    """context manager release 失败时也必须清理 context cleanup 引用。"""

    lock_path = _lock_path(tmp_path)
    third_party_lock = _FailingThirdPartyLock()
    lock = file_lock(lock_path)
    lock._context_token = RuntimeFileLockToken(
        lock_path=lock_path,
        third_party_lock=cast(FileLock, third_party_lock),
    )

    with pytest.raises(RuntimeFileLockError, match="释放 runtime file lock 失败"):
        lock.__exit__(None, None, None)

    assert lock._context_token is None
    assert third_party_lock.release_calls == 1


def test_manual_release_allows_same_instance_reacquire(tmp_path: Path) -> None:
    """手动 token release 后，同一 lock 实例可按底层语义再次 acquire。"""

    lock = file_lock(_lock_path(tmp_path))
    first_token = lock.acquire(timeout_seconds=0)
    first_token.release()

    second_token = lock.acquire(timeout_seconds=0)
    try:
        assert second_token is not first_token
    finally:
        second_token.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    """重复 release 不得抛错，也不得删除 lock file。"""

    lock_path = _lock_path(tmp_path)
    token = file_lock(lock_path).acquire(timeout_seconds=0)

    token.release()
    token.release()

    assert lock_path.exists()


def test_release_success_before_marker_failure_remains_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """底层 release 成功后 marker 恢复失败不得破坏 release 幂等。"""

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

    assert third_party_lock.release_calls == 1
    token.release()
    assert third_party_lock.release_calls == 1


def test_release_failure_does_not_complete_and_allows_retry(
    tmp_path: Path,
) -> None:
    """底层 release 失败不得进入成功态，再次 release 必须重试底层 release。"""

    lock_path = _lock_path(tmp_path)
    third_party_lock = _FailingThirdPartyLock()
    token = RuntimeFileLockToken(
        lock_path=lock_path,
        third_party_lock=cast(FileLock, third_party_lock),
    )

    with pytest.raises(RuntimeFileLockError, match="释放 runtime file lock 失败"):
        token.release()

    with pytest.raises(RuntimeFileLockError, match="释放 runtime file lock 失败"):
        token.release()

    assert third_party_lock.release_calls == 2


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
    token_field_names = {field.name for field in fields(RuntimeFileLockToken)}
    public_token_field_names = {
        field.name
        for field in fields(RuntimeFileLockToken)
        if not field.name.startswith("_")
    }

    assert lock.options == options
    assert public_token_field_names == {"lock_path"}
    assert "released" not in token_field_names
    assert "_context_token" not in token_field_names
    assert "_active_token" not in RuntimeFileLock.__slots__
    assert "_context_token" in RuntimeFileLock.__slots__
    assert "_context_token" not in filelock_module.__all__
    assert "force_release" not in vars(RuntimeFileLock)
    assert "break_lock" not in vars(RuntimeFileLock)
    assert "__aenter__" not in vars(RuntimeFileLock)
    assert "__aexit__" not in vars(RuntimeFileLock)
