"""workspace 本地路径公共契约。

本模块只从调用方已解析的 workspace root 派生 Dayu 运行期路径。它不读取
配置文件、不创建目录、不依赖 Host / Engine / Service / Fins / UI 任一业务层。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

WORKSPACE_CONFIG_DIR_NAME: Final[str] = "config"
DAYU_DIR_NAME: Final[str] = ".dayu"
HOST_DIR_NAME: Final[str] = "host"
ARTIFACTS_DIR_NAME: Final[str] = "artifacts"
RUNTIME_DIR_NAME: Final[str] = "runtime"
CLI_DIR_NAME: Final[str] = "cli"
WEB_TOOLS_STORAGE_STATES_DIR_NAME: Final[str] = "web_tools_storage_states"
HOST_SQLITE_FILE_NAME: Final[str] = "dayu_host.sqlite3"
RUNTIME_LANES_SQLITE_FILE_NAME: Final[str] = "runtime_lanes.sqlite3"
CLI_TERMINAL_CURSOR_FILE_NAME: Final[str] = "terminal_cursors.json"


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """从 workspace root 派生的 Dayu 本地路径集合。

    :param workspace_root: 已由调用方解析的 workspace 根目录。
    """

    workspace_root: Path

    @property
    def config_dir(self) -> Path:
        """返回 workspace 覆盖配置目录。

        :returns: ``<workspace_root>/config``。
        :raises Exception: 不主动抛出异常。
        """

        return self.workspace_root / WORKSPACE_CONFIG_DIR_NAME

    @property
    def dayu_dir(self) -> Path:
        """返回 Dayu workspace-local 隐藏目录。

        :returns: ``<workspace_root>/.dayu``。
        :raises Exception: 不主动抛出异常。
        """

        return self.workspace_root / DAYU_DIR_NAME

    @property
    def host_dir(self) -> Path:
        """返回 Host durable store 默认目录。

        :returns: ``<workspace_root>/.dayu/host``。
        :raises Exception: 不主动抛出异常。
        """

        return self.dayu_dir / HOST_DIR_NAME

    @property
    def artifact_root(self) -> Path:
        """返回 Host artifact 默认目录。

        :returns: ``<workspace_root>/.dayu/artifacts``。
        :raises Exception: 不主动抛出异常。
        """

        return self.dayu_dir / ARTIFACTS_DIR_NAME

    @property
    def runtime_dir(self) -> Path:
        """返回 runtime 基础设施默认目录。

        :returns: ``<workspace_root>/.dayu/runtime``。
        :raises Exception: 不主动抛出异常。
        """

        return self.dayu_dir / RUNTIME_DIR_NAME

    @property
    def runtime_lanes_db_path(self) -> Path:
        """返回 runtime lane coordinator 默认 SQLite 路径。

        :returns: ``<workspace_root>/.dayu/runtime/runtime_lanes.sqlite3``。
        :raises Exception: 不主动抛出异常。
        """

        return self.runtime_dir / RUNTIME_LANES_SQLITE_FILE_NAME

    @property
    def host_sqlite_path(self) -> Path:
        """返回 Host 默认 SQLite 路径。

        :returns: ``<workspace_root>/.dayu/host/dayu_host.sqlite3``。
        :raises Exception: 不主动抛出异常。
        """

        return self.host_dir / HOST_SQLITE_FILE_NAME

    @property
    def web_tools_storage_state_dir(self) -> Path:
        """返回 Web tools Playwright storage state 默认目录。

        :returns: ``<workspace_root>/.dayu/web_tools_storage_states``。
        :raises Exception: 不主动抛出异常。
        """

        return self.dayu_dir / WEB_TOOLS_STORAGE_STATES_DIR_NAME

    @property
    def cli_dir(self) -> Path:
        """返回 CLI workspace-local 状态目录。

        :returns: ``<workspace_root>/.dayu/cli``。
        :raises Exception: 不主动抛出异常。
        """

        return self.dayu_dir / CLI_DIR_NAME

    @property
    def cli_terminal_cursor_file(self) -> Path:
        """返回 CLI terminal cursor JSON 文件路径。

        :returns: ``<workspace_root>/.dayu/cli/terminal_cursors.json``。
        :raises Exception: 不主动抛出异常。
        """

        return self.cli_dir / CLI_TERMINAL_CURSOR_FILE_NAME


def workspace_paths(workspace_root: Path) -> WorkspacePaths:
    """创建 workspace 路径集合。

    :param workspace_root: 已解析的 workspace 根目录。
    :returns: workspace 路径集合。
    :raises Exception: 不主动抛出异常。
    """

    return WorkspacePaths(workspace_root=workspace_root)


def get_config_path(workspace_root: Path) -> Path:
    """返回 workspace 覆盖配置目录。

    :param workspace_root: 已解析的 workspace 根目录。
    :returns: ``<workspace_root>/config``。
    :raises Exception: 不主动抛出异常。
    """

    return workspace_paths(workspace_root).config_dir


def resolve_workspace_path(workspace_root: Path, configured_path: str) -> Path:
    """把配置路径解析为 workspace-root 相对路径或绝对路径。

    :param workspace_root: 已解析的 workspace 根目录。
    :param configured_path: 配置中的路径字符串；相对路径必须留在 workspace
        root 内。
    :returns: 解析后的路径。
    :raises ValueError: 配置路径为空或相对路径逃逸 workspace root 时抛出。
    """

    stripped = configured_path.strip()
    if stripped == "":
        raise ValueError("configured workspace path must be non-empty")
    path = Path(stripped).expanduser()
    if path.is_absolute():
        return path.resolve(strict=False)
    resolved_root = workspace_root.expanduser().resolve(strict=False)
    resolved_path = (resolved_root / path).resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("configured workspace path escapes workspace root") from exc
    return resolved_path


__all__: tuple[str, ...] = (
    "WorkspacePaths",
    "get_config_path",
    "resolve_workspace_path",
    "workspace_paths",
)
