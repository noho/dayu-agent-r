"""文件系统仓储 — Blob / 文件条目操作 mixin。"""

from __future__ import annotations

import shutil
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentEntry,
    FileObjectMeta,
    ProcessedHandle,
    SourceHandle,
)

from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_storage_utils import _normalize_filename, _normalize_ticker


class _FsBlobMixin(_FsStorageInfra):
    """Blob / 文件条目操作 mixin。"""

    def list_entries(self, handle: SourceHandle | ProcessedHandle) -> list[DocumentEntry]:
        """从 published tree 列出文档目录下的直系条目。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            直系条目列表；目录不存在时返回空列表。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取目录失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._list_entries_unguarded(handle)
        finally:
            self._release_lock_token(guard_token)

    def _list_entries_unguarded(
        self,
        handle: SourceHandle | ProcessedHandle,
    ) -> list[DocumentEntry]:
        """在 caller 已持 publication guard 时列出直系条目。

        Args:
            handle: 源文档或 processed 句柄。

        Returns:
            直系条目列表；目录不存在时返回空列表。

        Raises:
            OSError: 读取目录失败时抛出。
        """

        directory = self._handle_dir_path(handle)
        if not directory.exists() or not directory.is_dir():
            return []
        return [
            DocumentEntry(name=child.name, is_file=child.is_file())
            for child in sorted(directory.iterdir(), key=lambda item: item.name)
        ]

    def read_file_bytes(self, handle: SourceHandle | ProcessedHandle, filename: str) -> bytes:
        """从 published tree 读取文档目录下的单个文件内容。

        Args:
            handle: 源文档/解析产物句柄。
            filename: 直系文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标为目录时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._read_file_bytes_unguarded(handle, filename)
        finally:
            self._release_lock_token(guard_token)

    def _read_file_bytes_unguarded(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
    ) -> bytes:
        """在 caller 已持 publication guard 时读取文件字节。

        Args:
            handle: 源文档或 processed 句柄。
            filename: 直系文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标为目录时抛出。
            OSError: 读取失败时抛出。
        """

        path = self._resolve_handle_child_path(handle, filename)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"目标是目录，无法按文件读取: {path}")
        return path.read_bytes()

    def delete_entry(
        self,
        handle: SourceHandle | ProcessedHandle,
        name: str,
        *,
        batch: BatchToken,
    ) -> None:
        """删除文档目录下的单个直系条目。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            FileNotFoundError: 条目不存在时抛出。
            ValueError: capability、handle 或条目名非法时抛出。
            OSError: 删除失败时抛出。
        """

        state = self._resolve_active_batch(batch, handle.ticker)
        self._delete_entry_impl(handle, name, state)

    def _delete_entry_impl(
        self,
        handle: SourceHandle | ProcessedHandle,
        name: str,
        state: _ActiveBatchState,
    ) -> None:
        """执行单个直系条目删除（内部实现）。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            FileNotFoundError: 条目不存在时抛出。
            OSError: 删除失败时抛出。
        """

        path = self._resolve_handle_child_path_for_state(handle, name, state)
        if not path.exists():
            raise FileNotFoundError(f"条目不存在: {path}")
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink()

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
        """存储文件并返回文件元数据。

        Args:
            handle: 源文档/解析产物句柄。
            filename: 文件名。
            data: 文件二进制流。
            batch: 显式 transaction capability。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            文件对象元数据。

        Raises:
            FileNotFoundError: processed handle 对应 meta 不存在时抛出。
            ValueError: capability、handle、文件名或 staging containment 非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, handle.ticker)
        normalized_filename = _normalize_filename(filename)
        handle_dir = self._handle_dir_path_for_state(handle, state)
        self._require_contained_path(
            handle_dir,
            state.staging_ticker_dir,
            label="blob staging handle directory",
        )
        if handle_dir.is_symlink():
            raise ValueError("blob staging handle directory 禁止 symlink")
        self._resolve_handle_child_path_for_state(handle, normalized_filename, state)
        if isinstance(handle, ProcessedHandle):
            self._get_handle_meta_for_state(handle, state)
        normalized_ticker = _normalize_ticker(handle.ticker)
        key = self._build_store_key_from_normalized_filename(handle, normalized_filename)
        file_store = self._build_file_store(normalized_ticker, state)
        return file_store.put_object(
            key,
            data,
            content_type=content_type,
            metadata=metadata,
        )

    def list_files(self, handle: SourceHandle | ProcessedHandle) -> list[FileObjectMeta]:
        """从 published tree 列出文档关联的文件元数据列表。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            文件元数据列表。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: 元数据格式非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._list_files_unguarded(handle)
        finally:
            self._release_lock_token(guard_token)

    def _list_files_unguarded(
        self,
        handle: SourceHandle | ProcessedHandle,
    ) -> list[FileObjectMeta]:
        """在 caller 已持 publication guard 时读取文件元数据列表。

        Args:
            handle: 源文档或 processed 句柄。

        Returns:
            文件元数据列表。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: 元数据格式非法时抛出。
        """

        return self._list_handle_files_unguarded(handle)
