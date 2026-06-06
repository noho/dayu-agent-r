"""文件系统文档文件对象仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import DocumentEntry, FileObjectMeta, ProcessedHandle, SourceHandle

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import DocumentBlobRepositoryProtocol


class FsDocumentBlobRepository(DocumentBlobRepositoryProtocol):
    """基于文件系统的文档文件对象仓储实现。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
    ) -> None:
        """初始化文档文件对象仓储。

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

    def list_entries(self, handle: SourceHandle | ProcessedHandle) -> list[DocumentEntry]:
        """列出文档目录直系条目。"""

        return self._repository_set.core.list_entries(handle)

    def read_file_bytes(self, handle: SourceHandle | ProcessedHandle, name: str) -> bytes:
        """读取文件字节内容。"""

        return self._repository_set.core.read_file_bytes(handle, name)

    def delete_entry(self, handle: SourceHandle | ProcessedHandle, name: str) -> None:
        """删除直系条目。"""

        self._repository_set.core.delete_entry(handle, name)

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """写入文件对象。"""

        return self._repository_set.core.store_file(
            handle=handle,
            filename=filename,
            data=data,
            content_type=content_type,
            metadata=metadata,
        )

    def list_files(self, handle: SourceHandle | ProcessedHandle) -> list[FileObjectMeta]:
        """列出目录中的文件对象元数据。"""

        return self._repository_set.core.list_files(handle)
