"""文件系统批处理事务仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import BatchToken

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import BatchingRepositoryProtocol


class FsBatchingRepository(BatchingRepositoryProtocol):
    """基于文件系统的批处理事务仓储实现。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
    ) -> None:
        """初始化批处理事务仓储。

        Args:
            workspace_root: 工作区根目录。
            file_store: 可选文件存储实现。
            repository_set: 可选共享仓储 core 集合。

        Returns:
            无。

        Raises:
            OSError: 底层仓储初始化失败时抛出。
        """

        self._repository_set = build_fs_repository_set(
            workspace_root=workspace_root,
            file_store=file_store,
            repository_set=repository_set,
        )

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启批处理事务。"""

        return self._repository_set.core.begin_batch(ticker)

    def commit_batch(self, token: BatchToken) -> None:
        """提交批处理事务。"""

        self._repository_set.core.commit_batch(token)

    def rollback_batch(self, token: BatchToken) -> None:
        """回滚批处理事务。"""

        self._repository_set.core.rollback_batch(token)

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """恢复异常退出后遗留的孤儿 batch/backup。"""

        return self._repository_set.core.recover_orphan_batches(dry_run=dry_run)
