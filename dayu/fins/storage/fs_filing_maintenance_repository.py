"""文件系统 filing 维护治理仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import (
    BatchToken,
    DownloadRejectionRegistry,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
)
from dayu.fins.domain.document_models import FileObjectMeta
from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import FilingMaintenanceRepositoryProtocol


class FsFilingMaintenanceRepository(FilingMaintenanceRepositoryProtocol):
    """基于文件系统的 filing 维护治理仓储实现。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
    ) -> None:
        """初始化 filing 维护治理仓储。

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

    def clear_filing_documents(self, ticker: str, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中清空 ticker 的 filing 文档。

        Args:
            ticker: 股票代码。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability 或 ticker 非法时抛出。
            OSError: staging 清理失败时抛出。
        """

        self._repository_set.core.clear_filing_documents(ticker, batch=batch)

    def load_download_rejection_registry(self, ticker: str) -> DownloadRejectionRegistry:
        """从 published tree 读取下载拒绝注册表。

        Args:
            ticker: 股票代码。

        Returns:
            document ID 到拒绝事实的注册表。

        Raises:
            ValueError: ticker 或 registry 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.load_download_rejection_registry(ticker)

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: DownloadRejectionRegistry,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中保存下载拒绝注册表。

        Args:
            ticker: 股票代码。
            registry: document ID 到拒绝事实的注册表。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或 registry 内容非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        self._repository_set.core.save_download_rejection_registry(
            ticker,
            registry,
            batch=batch,
        )

    def store_rejected_filing_file(
        self,
        ticker: str,
        document_id: str,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """在显式 transaction staging 中写入 rejected filing 文件。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。
            filename: 文件名。
            data: 二进制输入流。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。
            content_type: 可选内容类型。
            metadata: 可选字符串元数据。

        Returns:
            文件对象元数据。

        Raises:
            ValueError: capability、ticker、document ID 或 filename 非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        return self._repository_set.core.store_rejected_filing_file(
            ticker=ticker,
            document_id=document_id,
            filename=filename,
            data=data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
        *,
        batch: BatchToken,
    ) -> RejectedFilingArtifact:
        """在显式 transaction staging 中写入 rejected filing artifact。

        Args:
            req: artifact 写入请求。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            storage owner 规范化后的 artifact。

        Raises:
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        return self._repository_set.core.upsert_rejected_filing_artifact(req, batch=batch)

    def get_rejected_filing_artifact(
        self,
        ticker: str,
        document_id: str,
    ) -> RejectedFilingArtifact:
        """从 published tree 读取 rejected filing artifact。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。

        Returns:
            rejected filing artifact。

        Raises:
            FileNotFoundError: published artifact 不存在时抛出。
            ValueError: ticker、document ID 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.get_rejected_filing_artifact(
            ticker=ticker,
            document_id=document_id,
        )

    def list_rejected_filing_artifacts(
        self,
        ticker: str,
    ) -> list[RejectedFilingArtifact]:
        """从 published tree 列出 ticker 的 rejected filing artifacts。

        Args:
            ticker: 股票代码。

        Returns:
            按文档 ID 排序的 rejected filing artifacts。

        Raises:
            ValueError: ticker 或任一 artifact meta 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.list_rejected_filing_artifacts(ticker)

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """从 published tree 读取 rejected filing 文件内容。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。
            filename: 文件名。

        Returns:
            文件字节内容。

        Raises:
            FileNotFoundError: published 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: ticker、document ID 或 filename 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.read_rejected_filing_file_bytes(
            ticker=ticker,
            document_id=document_id,
            filename=filename,
        )

    def cleanup_stale_filing_documents(
        self,
        ticker: str,
        *,
        batch: BatchToken,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """在显式 transaction staging 中清理不再有效的 filing 文档。

        Args:
            ticker: 股票代码。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。
            active_form_types: 本次窗口覆盖的 form type 集合。
            valid_document_ids: 本次窗口仍应保留的文档 ID 集合。

        Returns:
            实际清理的文档数量。

        Raises:
            ValueError: capability、ticker、meta 或 manifest 内容非法时抛出。
            OSError: staging 清理或 manifest 写入失败时抛出。
        """

        return self._repository_set.core.cleanup_stale_filing_documents(
            ticker,
            batch=batch,
            active_form_types=active_form_types,
            valid_document_ids=valid_document_ids,
        )
