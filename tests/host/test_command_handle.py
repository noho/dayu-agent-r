"""Host public command handle factory 与 lifecycle 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.host as host_package
import pytest

from dayu.host import (
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCommandHandle,
    HostCommandHandleOptions,
    create_host_command_handle,
    ensure_session,
)

_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.fins",
    "dayu.service",
    "dayu.ui",
)


def _options(tmp_path: Path, host_handle_id: str | None = "host-test") -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :param host_handle_id: 可选 public handle id。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id=host_handle_id,
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.01,
        payload_inline_threshold_bytes=4096,
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造测试用 ensure session 请求。

    :returns: ensure session 请求。
    """

    return EnsureSessionRequest(scope="workspace", slot_key="slot-a", metadata=())


def _host_root() -> Path:
    """返回 Host 包源码根目录。

    :returns: ``dayu/host`` 源码目录。
    :raises AssertionError: Host 包缺少 ``__file__`` 时抛出。
    """

    package_file = host_package.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _imported_module_names(source: str) -> list[str]:
    """读取 Python 源码中的绝对 import 模块名。

    :param source: Python 源码。
    :returns: 模块名列表。
    """

    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.append(node.module)
    return names


def _matches_forbidden_prefix(module: str) -> bool:
    """判断模块名是否命中 Host 禁止依赖层。

    :param module: 模块名。
    :returns: 命中返回 ``True``。
    """

    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def test_factory_opens_fresh_database_and_returns_public_handle(
    tmp_path: Path,
) -> None:
    """factory 能创建 fresh DB，并返回稳定 public handle。"""

    options = _options(tmp_path, host_handle_id="stable-host")
    command_handle = create_host_command_handle(options)
    try:
        assert isinstance(command_handle, HostCommandHandle)
        assert command_handle.host_handle_id == "stable-host"
        assert options.db_path.exists()
        assert ensure_session(command_handle, _ensure_request()).session_id
    finally:
        command_handle.close()


def test_generated_handle_id_is_stable_for_handle_lifetime(
    tmp_path: Path,
) -> None:
    """未显式提供 handle id 时，factory 生成生命周期内稳定的 public id。"""

    command_handle = create_host_command_handle(
        _options(tmp_path, host_handle_id=None)
    )
    try:
        first_id = command_handle.host_handle_id
        assert first_id.startswith("host-command-")
        assert command_handle.host_handle_id == first_id
    finally:
        command_handle.close()


def test_public_handle_does_not_expose_internal_mutable_dependencies(
    tmp_path: Path,
) -> None:
    """public handle 不暴露 store、transaction runner 或 admission service。"""

    command_handle = create_host_command_handle(_options(tmp_path))
    try:
        public_names = {
            name for name in dir(command_handle) if not name.startswith("_")
        }
        assert "host_handle_id" in public_names
        assert "close" in public_names
        assert "transaction_runner" not in public_names
        assert "durable_store" not in public_names
        assert "admission_service" not in public_names
        assert "store_connection" not in public_names
    finally:
        command_handle.close()


def test_handle_close_is_idempotent_and_facade_fails_after_close(
    tmp_path: Path,
) -> None:
    """handle close 可重复调用；关闭后 public facade 返回稳定错误。"""

    command_handle = create_host_command_handle(_options(tmp_path))
    ensure_session(command_handle, _ensure_request())

    command_handle.close()
    command_handle.close()

    with pytest.raises(HostApiError) as exc_info:
        ensure_session(command_handle, _ensure_request())
    assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
    assert exc_info.value.retryable is False


def test_host_import_boundary_still_excludes_upper_layers() -> None:
    """Host public command path 不能引入 Engine / Fins / Service / UI 依赖。"""

    violations: list[tuple[str, str]] = []
    for file_path in sorted(_host_root().rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_forbidden_prefix(module):
                violations.append((str(file_path), module))
    assert not violations
