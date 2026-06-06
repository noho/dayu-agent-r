"""文件系统 filing 维护治理仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import (
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

    def clear_filing_documents(self, ticker: str) -> None:
        """清空某个 ticker 下的全部 filing 文档。"""

        self._repository_set.core.clear_filing_documents(ticker)

    def load_download_rejection_registry(self, ticker: str) -> dict[str, dict[str, str]]:
        """读取下载拒绝注册表。"""

        return self._repository_set.core.load_download_rejection_registry(ticker)

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: dict[str, dict[str, str]],
    ) -> None:
        """保存下载拒绝注册表。"""

        self._repository_set.core.save_download_rejection_registry(ticker, registry)

    def store_rejected_filing_file(
        self,
        ticker: str,
        document_id: str,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """写入 rejected filing 文件对象。"""

        return self._repository_set.core.store_rejected_filing_file(
            ticker=ticker,
            document_id=document_id,
            filename=filename,
            data=data,
            content_type=content_type,
            metadata=metadata,
        )

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
    ) -> RejectedFilingArtifact:
        """写入或更新 rejected filing artifact。"""

        return self._repository_set.core.upsert_rejected_filing_artifact(req)

    def get_rejected_filing_artifact(
        self,
        ticker: str,
        document_id: str,
    ) -> RejectedFilingArtifact:
        """读取 rejected filing artifact。"""

        return self._repository_set.core.get_rejected_filing_artifact(
            ticker=ticker,
            document_id=document_id,
        )

    def list_rejected_filing_artifacts(
        self,
        ticker: str,
    ) -> list[RejectedFilingArtifact]:
        """列出某个 ticker 下的 rejected filing artifacts。"""

        return self._repository_set.core.list_rejected_filing_artifacts(ticker)

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """读取 rejected filing 文件内容。"""

        return self._repository_set.core.read_rejected_filing_file_bytes(
            ticker=ticker,
            document_id=document_id,
            filename=filename,
        )

    def cleanup_stale_filing_documents(
        self,
        ticker: str,
        *,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """清理不在有效集合中的 filing 文档。"""

        return self._repository_set.core.cleanup_stale_filing_documents(
            ticker,
            active_form_types=active_form_types,
            valid_document_ids=valid_document_ids,
        )
