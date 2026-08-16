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
        """开启 ticker 级批处理事务并取得唯一 writer capability。

        Args:
            ticker: 要绑定的股票代码。

        Returns:
            当前 shared storage core 登记的显式 batch capability。

        Raises:
            ValueError: ticker 非法时抛出。
            RuntimeError: 同 ticker 已存在活动 writer 时抛出。
            RuntimeFileLockError: writer lock 获取失败时抛出。
            OSError: staging 或 journal 初始化失败时抛出。
        """

        return self._repository_set.core.begin_batch(ticker)

    def commit_batch(self, batch: BatchToken) -> None:
        """提交事务并在成功或失败后终态消费 capability。

        Args:
            batch: 当前 shared storage core 登记且仍为 open 的 batch capability。

        Returns:
            无；正常返回表示 ``COMMITTED`` 已成为 durable 提交事实。

        Raises:
            ValueError: capability 未登记、已终态或 ticker/core 不匹配时抛出。
            SourceIntegrityPreflightError: whole-tree inspection 遇到无法归属到
                单一 source target 的结构损坏时抛出。
            OSError: physical swap、journal 或 pre-commit restore 失败时抛出。
            RuntimeFileLockError: 没有更早 operation error 且 publication/writer lock
                获取或释放失败时抛出；``COMMITTED`` 后 publication release failure
                作为 post-commit 主异常抛出且不回滚 durable tree，后续 cleanup/writer
                release failure 仅附着为诊断。
        """

        self._repository_set.core.commit_batch(batch)

    def rollback_batch(self, batch: BatchToken) -> None:
        """回滚 open 事务并终态消费 capability。

        Args:
            batch: 当前 shared storage core 登记且仍为 open 的 batch capability。

        Returns:
            无。

        Raises:
            ValueError: capability 未登记、已终态或 ticker/core 不匹配时抛出。
            OSError: rollback journal 写入失败时抛出；staging 仍会清理且 capability
                仍会消费。
            RuntimeFileLockError: 没有更早 rollback error 且 writer lock 释放失败时
                抛出；已有主异常时 release failure 仅附着为诊断。
        """

        self._repository_set.core.rollback_batch(batch)

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """恢复合法 orphan，并 fail-closed 保留 malformed recovery evidence。

        Args:
            dry_run: 是否只返回拟执行 action 而不修改 filesystem。

        Returns:
            按扫描顺序记录的 restore/delete/cleanup/skip/preserve action。

        Raises:
            RuntimeFileLockError: recovery、writer 或 publication lock 操作失败时抛出。
            OSError: evidence 枚举、读取或 physical restore 失败时抛出。
        """

        return self._repository_set.core.recover_orphan_batches(dry_run=dry_run)
