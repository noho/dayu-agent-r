"""文件系统 filing 上传 published-state 只读仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import BatchToken

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import (
    FilingUploadPublishedState,
    FilingUploadStateRepositoryProtocol,
)


class FsFilingUploadStateRepository(FilingUploadStateRepositoryProtocol):
    """基于文件系统的 filing 上传校验状态仓储。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
        create_directories: bool = False,
    ) -> None:
        """初始化只读 filing 上传状态仓储。

        Args:
            workspace_root: Fins 工作区根目录。
            file_store: 可选文件存储实现。
            repository_set: 可选共享仓储 core 集合。
            create_directories: 是否在独立构造时创建 storage 目录；默认关闭。

        Returns:
            无。

        Raises:
            OSError: storage core 初始化失败时抛出。
        """

        self._repository_set = build_fs_repository_set(
            workspace_root=workspace_root,
            file_store=file_store,
            repository_set=repository_set,
            create_directories=create_directories,
        )

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """读取同一 publication guard 下的上传校验状态。

        Args:
            ticker: 待校验的公司代码。
            document_id: 待校验的 filing 文档 ID。

        Returns:
            company/source 的同版 published state。

        Raises:
            CompanyTickerIdentityCorruptionError: published ticker durable identity 损坏时抛出。
            ValueError: ticker 或 document identity 非法时抛出；可归属 filing target 的
                source descriptor/meta 结构损坏返回 ``UNSAFE`` typed state。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published state 读取失败时抛出。
        """

        return self._repository_set.core.read_filing_upload_state(ticker, document_id)

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """读取 open batch writer-owned staging 中的上传校验状态。

        Args:
            batch: 同一共享 core、ticker 且仍 open 的 batch capability。
            document_id: 待校验的 exact filing 文档 ID。

        Returns:
            staging company/source 的同版 state。

        Raises:
            CompanyTickerIdentityCorruptionError: staging ticker durable identity 损坏时抛出。
            ValueError: capability、ticker 或 document identity 非法时抛出。
            OSError: staging state 读取失败时抛出。
            RuntimeError: exact inspector payload 不完整时抛出。
        """

        return self._repository_set.core.read_filing_upload_state_in_batch(
            batch,
            document_id,
        )
