"""``dayu.runtime.workspace_paths`` 公共路径契约测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.runtime.workspace_paths import (
    get_config_path,
    resolve_workspace_path,
    workspace_paths,
)


def test_workspace_paths_derive_common_runtime_locations(tmp_path: Path) -> None:
    """公共路径契约必须只从 workspace root 派生 Dayu 运行期路径。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 任一路径派生结果不符合契约时抛出。
    """

    paths = workspace_paths(tmp_path)

    assert paths.config_dir == tmp_path / "config"
    assert paths.dayu_dir == tmp_path / ".dayu"
    assert paths.host_dir == tmp_path / ".dayu" / "host"
    assert paths.artifact_root == tmp_path / ".dayu" / "artifacts"
    assert paths.runtime_lanes_db_path == (
        tmp_path / ".dayu" / "runtime" / "runtime_lanes.sqlite3"
    )
    assert paths.web_tools_storage_state_dir == (
        tmp_path / ".dayu" / "web_tools_storage_states"
    )
    assert paths.cli_terminal_cursor_file == (
        tmp_path / ".dayu" / "cli" / "terminal_cursors.json"
    )
    assert get_config_path(tmp_path) == tmp_path / "config"


def test_resolve_workspace_path_rejects_relative_escape(tmp_path: Path) -> None:
    """相对配置路径不得逃逸 workspace root。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 未拒绝逃逸路径时抛出。
    """

    with pytest.raises(ValueError, match="escapes workspace root"):
        resolve_workspace_path(tmp_path, "../outside")


def test_resolve_workspace_path_resolves_relative_to_workspace_root(
    tmp_path: Path,
) -> None:
    """相对配置路径必须按 workspace root 解析。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 相对路径未按 workspace root 解析时抛出。
    """

    assert resolve_workspace_path(tmp_path, ".dayu/host/dayu.sqlite3") == (
        tmp_path / ".dayu" / "host" / "dayu.sqlite3"
    ).resolve(strict=False)
