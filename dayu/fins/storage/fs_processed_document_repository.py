"""文件系统 processed 文档仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import (
    DocumentHandle,
    DocumentMeta,
    DocumentQuery,
    DocumentSummary,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedHandle,
    ProcessedUpdateRequest,
)

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import ProcessedDocumentRepositoryProtocol


class FsProcessedDocumentRepository(ProcessedDocumentRepositoryProtocol):
    """基于文件系统的 processed 文档仓储实现。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
    ) -> None:
        """初始化 processed 文档仓储。

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

    def create_processed(self, req: ProcessedCreateRequest) -> DocumentHandle:
        """创建 processed 文档。"""

        return self._repository_set.core.create_processed(req)

    def update_processed(self, req: ProcessedUpdateRequest) -> DocumentHandle:
        """更新 processed 文档。"""

        return self._repository_set.core.update_processed(req)

    def delete_processed(self, req: ProcessedDeleteRequest) -> None:
        """删除 processed 文档。"""

        self._repository_set.core.delete_processed(req)

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """构造 processed 句柄。"""

        return self._repository_set.core.get_processed_handle(ticker, document_id)

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """读取 processed meta。"""

        return self._repository_set.core.get_processed_meta(ticker, document_id)

    def list_processed_documents(self, ticker: str, query: DocumentQuery) -> list[DocumentSummary]:
        """按查询条件列出 processed 文档摘要。"""

        return self._repository_set.core.list_documents(ticker, query)

    def clear_processed_documents(self, ticker: str) -> None:
        """清空某个 ticker 的全部 processed 产物。"""

        self._repository_set.core.clear_processed_documents(ticker)

    def mark_processed_reprocess_required(self, ticker: str, document_id: str, required: bool) -> None:
        """标记 processed 文档是否需要重处理。"""

        if not required:
            return
        self._repository_set.core.mark_processed_reprocess_required(ticker, document_id)
