"""文件系统公司元数据仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import BatchToken, CompanyMeta, CompanyMetaInventoryEntry

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import CompanyMetaRepositoryProtocol


class FsCompanyMetaRepository(CompanyMetaRepositoryProtocol):
    """基于文件系统的公司元数据仓储实现。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
    ) -> None:
        """初始化公司元数据仓储。

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

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """按 ticker publication guard 扫描 published 公司目录。

        Args:
            无。

        Returns:
            按目录名排序的公司元数据盘点结果。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published tree 访问失败时抛出。
        """

        return self._repository_set.core.scan_company_meta_inventory()

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """从 published tree 读取公司级元数据。

        Args:
            ticker: 股票代码。

        Returns:
            公司级元数据对象。

        Raises:
            FileNotFoundError: published 元数据不存在时抛出。
            ValueError: ticker 或元数据内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.get_company_meta(ticker)

    def upsert_company_meta(self, meta: CompanyMeta, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中写入公司级元数据。

        Args:
            meta: 待写入的公司级元数据。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或元数据路径字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        self._repository_set.core.upsert_company_meta(meta, batch=batch)

    def resolve_existing_ticker(self, ticker_candidates: list[str]) -> Optional[str]:
        """只基于 published 公司目录与 alias 解析首个既有 ticker。

        Args:
            ticker_candidates: 按优先级排列的候选 ticker。

        Returns:
            首个命中的规范 ticker；没有命中时返回 ``None``。

        Raises:
            ValueError: ticker 非法或一个 alias 对应多个 published 公司时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.resolve_existing_ticker(ticker_candidates)
