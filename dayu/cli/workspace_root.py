"""普通 CLI workspace 参数的文本与目标目录校验。"""

from __future__ import annotations

import stat
from collections.abc import Callable
from pathlib import Path
from typing import Final

_BASE_OPTION_NAME: Final[str] = "--base"
_NON_DIRECTORY_MESSAGE: Final[str] = (
    "--base must point to a directory; choose a directory path"
)


def resolve_workspace_root(
    value: str,
    *,
    error_factory: Callable[[str], ValueError],
) -> Path:
    """解析普通 CLI workspace 参数并拒绝现存非目录目标。

    Args:
        value: argparse 解析到的 workspace 参数文本。
        error_factory: 构造当前命令用法错误的工厂。

    Returns:
        裁剪并规范化后的绝对目标路径；目标尚不存在时也返回该路径。

    Raises:
        ValueError: 文本为空或现存目标不是目录时由工厂构造并抛出。
        OSError: 其它路径解析或目标状态读取失败时透传。
        RuntimeError: 路径规范化失败时透传。
    """

    stripped = value.strip()
    if not stripped:
        raise error_factory(f"{_BASE_OPTION_NAME} must not be empty")
    resolved = Path(stripped).expanduser().resolve(strict=False)
    try:
        mode = resolved.stat().st_mode
    except FileNotFoundError:
        return resolved
    if not stat.S_ISDIR(mode):
        raise error_factory(_NON_DIRECTORY_MESSAGE)
    return resolved
