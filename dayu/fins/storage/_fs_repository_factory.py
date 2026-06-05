"""文件系统窄仓储共享 core 构造辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ._fs_storage_core import FsStorageCore
from .file_store import FileStore


@dataclass(frozen=True)
class _FsRepositorySet:
    """共享文件系统仓储 core 集合。

    该对象仅用于具体实现装配阶段，避免多个窄仓储各自创建独立的
    私有文件系统存储 core，从而破坏同一工作区内的 batch/cache 共享语义。
    """

    core: FsStorageCore


def build_fs_repository_set(
    *,
    workspace_root: Path,
    file_store: Optional[FileStore] = None,
    repository_set: Optional[_FsRepositorySet] = None,
    create_directories: bool = True,
) -> _FsRepositorySet:
    """构建共享文件系统仓储 core 集合。

    Args:
        workspace_root: 工作区根目录。
        file_store: 可选文件存储实现。
        repository_set: 可选已存在的共享集合；传入时直接复用。
        create_directories: 是否在初始化时创建仓储根目录。

    Returns:
        共享文件系统仓储 core 集合。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    if repository_set is not None:
        return repository_set
    core = FsStorageCore(
        workspace_root=workspace_root,
        file_store=file_store,
        create_directories=create_directories,
    )
    if create_directories:
        core.ensure_batch_recovery()
    return _FsRepositorySet(
        core=core,
    )
