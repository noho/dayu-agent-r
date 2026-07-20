"""文件系统 processed 文档仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import (
    BatchToken,
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

    def create_processed(self, req: ProcessedCreateRequest, *, batch: BatchToken) -> DocumentHandle:
        """在显式 transaction staging 中创建 processed 文档。

        Args:
            req: processed 创建请求。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            新建 processed 文档句柄。

        Raises:
            FileExistsError: staging 文档已存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        return self._repository_set.core.create_processed(req, batch=batch)

    def update_processed(self, req: ProcessedUpdateRequest, *, batch: BatchToken) -> DocumentHandle:
        """在显式 transaction staging 中更新 processed 文档。

        Args:
            req: processed 更新请求。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            更新后的 processed 文档句柄。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        return self._repository_set.core.update_processed(req, batch=batch)

    def delete_processed(self, req: ProcessedDeleteRequest, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中删除 processed 文档。

        Args:
            req: processed 删除请求。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 删除失败时抛出。
        """

        self._repository_set.core.delete_processed(req, batch=batch)

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """从 published tree 校验并构造 processed 句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            published processed 句柄。

        Raises:
            FileNotFoundError: published processed meta 不存在时抛出。
            ValueError: ticker 或 document ID 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        return self._repository_set.core.get_processed_handle(ticker, document_id)

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """从 published tree 读取 processed meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed 元数据。

        Raises:
            FileNotFoundError: published meta 不存在时抛出。
            ValueError: ticker、document ID 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.get_processed_meta(ticker, document_id)

    def list_processed_documents(self, ticker: str, query: DocumentQuery) -> list[DocumentSummary]:
        """从 published tree 按查询条件列出 processed 文档摘要。

        Args:
            ticker: 股票代码。
            query: 文档过滤条件。

        Returns:
            published processed 文档摘要列表。

        Raises:
            ValueError: ticker、query 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.list_documents(ticker, query)

    def clear_processed_documents(self, ticker: str, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中清空 ticker 的 processed 产物。

        Args:
            ticker: 股票代码。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability 或 ticker 非法时抛出。
            OSError: staging 清理失败时抛出。
        """

        self._repository_set.core.clear_processed_documents(ticker, batch=batch)

    def mark_processed_reprocess_required(
        self,
        ticker: str,
        document_id: str,
        required: bool,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中标记 processed 是否需要重处理。

        Args:
            ticker: 股票代码。
            document_id: processed 文档 ID。
            required: 是否要求重处理；为 ``False`` 时不写入。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或 document ID 非法时抛出。
            OSError: staging meta 读写失败时抛出。
        """

        self._repository_set.core.mark_processed_reprocess_required(
            ticker,
            document_id,
            required,
            batch=batch,
        )
