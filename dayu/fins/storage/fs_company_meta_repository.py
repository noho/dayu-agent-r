"""文件系统公司元数据仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.company_meta_contract import CompanyMetaCommitIntent
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

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction state 中记录公司元数据提交意图。

        Args:
            intent: commit-time authoritative merge 使用的提交意图。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker、意图不匹配或重复 stage 时抛出。
        """

        self._repository_set.core.stage_company_meta_intent(intent, batch=batch)

    def resolve_company_ticker(self, ticker: str) -> str | None:
        """按唯一 published identity index 解析 canonical corpus ticker。

        Args:
            ticker: 单个 canonical 或 accepted alias 查询值。

        Returns:
            唯一 canonical corpus ticker；非法或未命中时返回 ``None``。

        Raises:
            CompanyTickerIdentityCorruptionError: published identity durable state 损坏时抛出。
            RuntimeFileLockError: identity/publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.resolve_company_ticker(ticker)
