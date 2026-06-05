"""文件系统公司元数据仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import CompanyMeta, CompanyMetaInventoryEntry

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
        """扫描公司目录并返回元数据盘点结果。"""

        return self._repository_set.core.scan_company_meta_inventory()

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """读取公司级元数据。"""

        return self._repository_set.core.get_company_meta(ticker)

    def upsert_company_meta(self, meta: CompanyMeta) -> None:
        """写入公司级元数据。"""

        self._repository_set.core.upsert_company_meta(meta)

    def resolve_existing_ticker(self, ticker_candidates: list[str]) -> Optional[str]:
        """在候选 ticker 中解析工作区内已存在的规范 ticker。"""

        return self._repository_set.core.resolve_existing_ticker(ticker_candidates)
