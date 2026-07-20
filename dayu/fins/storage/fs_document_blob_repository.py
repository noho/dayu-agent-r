"""文件系统文档文件对象仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentEntry,
    FileObjectMeta,
    ProcessedHandle,
    SourceHandle,
)

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
        """从 published tree 列出文档目录直系条目。

        Args:
            handle: source 或 processed 文档句柄。

        Returns:
            直系条目元数据列表。

        Raises:
            FileNotFoundError: published 文档目录不存在时抛出。
            ValueError: handle 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.list_entries(handle)

    def read_file_bytes(self, handle: SourceHandle | ProcessedHandle, name: str) -> bytes:
        """从 published tree 读取文件字节内容。

        Args:
            handle: source 或 processed 文档句柄。
            name: 文档目录下的直系文件名。

        Returns:
            文件字节内容。

        Raises:
            FileNotFoundError: published 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: handle 或文件名非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.read_file_bytes(handle, name)

    def delete_entry(
        self,
        handle: SourceHandle | ProcessedHandle,
        name: str,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中删除直系条目。

        Args:
            handle: source 或 processed 文档句柄。
            name: 待删除的直系条目名。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 条目不存在时抛出。
            ValueError: capability、handle 或条目名非法时抛出。
            OSError: staging 删除失败时抛出。
        """

        self._repository_set.core.delete_entry(handle, name, batch=batch)

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """在显式 transaction staging 中写入文件对象。

        Args:
            handle: source 或 processed 文档句柄。
            filename: 文件名。
            data: 二进制输入流。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。
            content_type: 可选内容类型。
            metadata: 可选字符串元数据。

        Returns:
            已写入文件的对象元数据。

        Raises:
            FileNotFoundError: processed handle 对应 staging meta 不存在时抛出。
            ValueError: capability、handle、文件名或 staging containment 非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        return self._repository_set.core.store_file(
            handle=handle,
            filename=filename,
            data=data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )

    def list_files(self, handle: SourceHandle | ProcessedHandle) -> list[FileObjectMeta]:
        """从 published tree 列出目录中的文件对象元数据。

        Args:
            handle: source 或 processed 文档句柄。

        Returns:
            文件对象元数据列表。

        Raises:
            FileNotFoundError: published 文档 meta 不存在时抛出。
            ValueError: handle 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.list_files(handle)
