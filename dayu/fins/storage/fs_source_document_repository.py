"""文件系统源文档仓储实现。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional

from dayu.documents.processors.source import Source
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    DocumentMeta,
    FilingCreateRequest,
    FilingDeleteRequest,
    FilingRestoreRequest,
    FilingUpdateRequest,
    FileObjectMeta,
    MaterialCreateRequest,
    MaterialDeleteRequest,
    MaterialRestoreRequest,
    MaterialUpdateRequest,
    SourceDocumentProvenance,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import SourceDocumentRepositoryProtocol, SourceSnapshotProtocol


def _build_source_handle(ticker: str, document_id: str, source_kind: SourceKind) -> SourceHandle:
    """构造源文档句柄。

    Args:
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 源文档类型。

    Returns:
        源文档句柄。

    Raises:
        无。
    """

    return SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=source_kind.value,
    )


def _build_filing_create_request(req: SourceDocumentUpsertRequest) -> FilingCreateRequest:
    """将通用写入请求收敛为 filing 创建请求。

    Args:
        req: 通用源文档写入请求。

    Returns:
        filing 创建请求。

    Raises:
        无。
    """

    return FilingCreateRequest(
        ticker=req.ticker,
        document_id=req.document_id,
        internal_document_id=req.internal_document_id,
        form_type=req.form_type,
        primary_document=req.primary_document,
        meta=req.meta,
        files=req.files,
        file_entries=req.file_entries,
    )


def _build_material_create_request(req: SourceDocumentUpsertRequest) -> MaterialCreateRequest:
    """将通用写入请求收敛为 material 创建请求。

    Args:
        req: 通用源文档写入请求。

    Returns:
        material 创建请求。

    Raises:
        无。
    """

    return MaterialCreateRequest(
        ticker=req.ticker,
        document_id=req.document_id,
        internal_document_id=req.internal_document_id,
        form_type=req.form_type,
        primary_document=req.primary_document,
        meta=req.meta,
        files=req.files,
        file_entries=req.file_entries,
    )


def _build_filing_update_request(req: SourceDocumentUpsertRequest) -> FilingUpdateRequest:
    """将通用写入请求收敛为 filing 更新请求。

    Args:
        req: 通用源文档写入请求。

    Returns:
        filing 更新请求。

    Raises:
        无。
    """

    return FilingUpdateRequest(
        ticker=req.ticker,
        document_id=req.document_id,
        internal_document_id=req.internal_document_id,
        form_type=req.form_type,
        primary_document=req.primary_document,
        meta=req.meta,
        files=req.files,
        file_entries=req.file_entries,
    )


def _build_material_update_request(req: SourceDocumentUpsertRequest) -> MaterialUpdateRequest:
    """将通用写入请求收敛为 material 更新请求。

    Args:
        req: 通用源文档写入请求。

    Returns:
        material 更新请求。

    Raises:
        无。
    """

    return MaterialUpdateRequest(
        ticker=req.ticker,
        document_id=req.document_id,
        internal_document_id=req.internal_document_id,
        form_type=req.form_type,
        primary_document=req.primary_document,
        meta=req.meta,
        files=req.files,
        file_entries=req.file_entries,
    )


def _build_filing_delete_request(req: SourceDocumentStateChangeRequest) -> FilingDeleteRequest:
    """将通用状态变更请求收敛为 filing 删除请求。

    Args:
        req: 通用源文档状态变更请求。

    Returns:
        filing 删除请求。

    Raises:
        无。
    """

    return FilingDeleteRequest(ticker=req.ticker, document_id=req.document_id)


def _build_material_delete_request(req: SourceDocumentStateChangeRequest) -> MaterialDeleteRequest:
    """将通用状态变更请求收敛为 material 删除请求。

    Args:
        req: 通用源文档状态变更请求。

    Returns:
        material 删除请求。

    Raises:
        无。
    """

    return MaterialDeleteRequest(ticker=req.ticker, document_id=req.document_id)


def _build_filing_restore_request(req: SourceDocumentStateChangeRequest) -> FilingRestoreRequest:
    """将通用状态变更请求收敛为 filing 恢复请求。

    Args:
        req: 通用源文档状态变更请求。

    Returns:
        filing 恢复请求。

    Raises:
        无。
    """

    return FilingRestoreRequest(ticker=req.ticker, document_id=req.document_id)


def _build_material_restore_request(req: SourceDocumentStateChangeRequest) -> MaterialRestoreRequest:
    """将通用状态变更请求收敛为 material 恢复请求。

    Args:
        req: 通用源文档状态变更请求。

    Returns:
        material 恢复请求。

    Raises:
        无。
    """

    return MaterialRestoreRequest(ticker=req.ticker, document_id=req.document_id)


class FsSourceDocumentRepository(SourceDocumentRepositoryProtocol):
    """基于文件系统的源文档仓储实现。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
        create_directories: bool = True,
    ) -> None:
        """初始化源文档仓储。

        Args:
            workspace_root: 工作区根目录。
            file_store: 可选文件存储实现。
            repository_set: 可选共享仓储 core 集合。
            create_directories: 是否在初始化时创建仓储根目录。

        Returns:
            无。

        Raises:
            OSError: 底层仓储初始化失败时抛出。
        """

        self._repository_set = build_fs_repository_set(
            workspace_root=workspace_root,
            file_store=file_store,
            repository_set=repository_set,
            create_directories=create_directories,
        )

    def has_source_storage_root(self, ticker: str, source_kind: SourceKind) -> bool:
        """判断 published tree 中某类源文档根目录是否存在。

        Args:
            ticker: 股票代码。
            source_kind: filing 或 material 来源类型。

        Returns:
            published 根目录存在且为目录时返回 ``True``。

        Raises:
            NotADirectoryError: published 根路径存在但不是目录时抛出。
            ValueError: ticker 或 source kind 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.has_source_storage_root(ticker, source_kind)

    def has_filing_xbrl_instance(self, ticker: str, document_id: str) -> bool:
        """判断 published filing 中是否存在 XBRL instance。

        Args:
            ticker: 股票代码。
            document_id: filing 文档 ID。

        Returns:
            published filing 中存在 XBRL instance 时返回 ``True``。

        Raises:
            FileNotFoundError: published filing 目录不存在时抛出。
            NotADirectoryError: published filing 路径不是目录时抛出。
            ValueError: ticker 或 document ID 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.has_filing_xbrl_instance(ticker, document_id)

    def has_staged_filing_xbrl_instance(
        self,
        ticker: str,
        document_id: str,
        *,
        batch: BatchToken,
    ) -> bool:
        """显式读取指定 open transaction staging 中的 filing XBRL instance。

        Args:
            ticker: 股票代码。
            document_id: filing 文档 ID。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            staging filing 中存在 XBRL instance 时返回 ``True``。

        Raises:
            FileNotFoundError: staging filing 目录不存在时抛出。
            NotADirectoryError: staging filing 路径不是目录时抛出。
            ValueError: capability、ticker 或 document ID 非法时抛出。
            OSError: staging I/O 失败时抛出。
        """

        return self._repository_set.core.has_staged_filing_xbrl_instance(
            ticker,
            document_id,
            batch=batch,
        )

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """在显式 transaction staging 中创建 filing 或 material 文档。

        Args:
            req: 通用源文档创建请求。
            source_kind: filing 或 material 来源类型。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            新建源文档句柄。

        Raises:
            FileExistsError: staging 文档已存在时抛出。
            FileNotFoundError: 请求引用的输入文件不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        if source_kind == SourceKind.FILING:
            return self._repository_set.core.create_filing(
                _build_filing_create_request(req),
                batch=batch,
            )
        return self._repository_set.core.create_material(
            _build_material_create_request(req),
            batch=batch,
        )

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """在显式 transaction staging 中更新 filing 或 material 文档。

        Args:
            req: 通用源文档更新请求。
            source_kind: filing 或 material 来源类型。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            更新后的源文档句柄。

        Raises:
            FileNotFoundError: staging 文档或请求引用文件不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """

        if source_kind == SourceKind.FILING:
            return self._repository_set.core.update_filing(
                _build_filing_update_request(req),
                batch=batch,
            )
        return self._repository_set.core.update_material(
            _build_material_update_request(req),
            batch=batch,
        )

    def delete_source_document(
        self,
        req: SourceDocumentStateChangeRequest,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中逻辑删除源文档。

        Args:
            req: 包含 ticker、document ID 与 source kind 的状态变更请求。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging meta 或 manifest 写入失败时抛出。
        """

        source_kind = SourceKind(str(req.source_kind))
        if source_kind == SourceKind.FILING:
            self._repository_set.core.delete_filing(
                _build_filing_delete_request(req),
                batch=batch,
            )
            return
        self._repository_set.core.delete_material(
            _build_material_delete_request(req),
            batch=batch,
        )

    def reset_source_document(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> None:
        """重置单个源文档的完整存储。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker、document ID 或 source kind 非法时抛出。
            OSError: 重置底层存储失败时抛出。
        """

        self._repository_set.core.reset_source_document(
            ticker,
            document_id,
            source_kind,
            batch=batch,
        )

    def restore_source_document(
        self,
        req: SourceDocumentStateChangeRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """在显式 transaction staging 中恢复逻辑删除的源文档。

        Args:
            req: 包含 ticker、document ID 与 source kind 的状态变更请求。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            恢复后的源文档句柄。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging meta 或 manifest 写入失败时抛出。
        """

        source_kind = SourceKind(str(req.source_kind))
        if source_kind == SourceKind.FILING:
            return self._repository_set.core.restore_filing(
                _build_filing_restore_request(req),
                batch=batch,
            )
        return self._repository_set.core.restore_material(
            _build_material_restore_request(req),
            batch=batch,
        )

    def get_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """从 published tree 读取源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            published source meta。

        Raises:
            FileNotFoundError: published source meta 不存在时抛出。
            ValueError: ticker、document ID、source kind 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.get_source_meta(ticker, document_id, source_kind)

    def get_source_document_locator(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> PurePosixPath:
        """返回 published source 文档目录的 workspace-relative locator。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            storage owner 校验后的相对 POSIX locator。

        Raises:
            FileNotFoundError: published source meta 不存在时抛出。
            ValueError: identity、source kind 或 meta 不一致时抛出。
            RuntimeError: publication guard 获取或释放失败时抛出。
            OSError: published tree 读取失败时抛出。
        """

        return self._repository_set.core.get_source_document_locator(
            ticker,
            document_id,
            source_kind,
        )

    def read_source_snapshot(
        self,
        ticker: str,
        document_id: str,
        source_kind: Optional[SourceKind] = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """读取同一 published revision 的 typed source snapshot。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: 可选显式 source kind；缺省时由 storage 同 guard 解析。
            materialize_files: 是否复制全部业务文件到 snapshot 私有临时树。

        Returns:
            同时拥有 meta、provenance、revision、files 与 primary 的资源。

        Raises:
            FileNotFoundError: source 不存在、已删除或 reset 后抛出。
            ValueError: source kind 歧义、descriptor、meta 或文件完整性非法时抛出。
            SourceSnapshotConsistencyError: publication 持续变化时抛出。
            RuntimeError: publication guard 操作失败时抛出。
            OSError: published 或临时文件系统访问失败时抛出。
        """

        return self._repository_set.core.read_source_snapshot(
            ticker,
            document_id,
            source_kind,
            materialize_files=materialize_files,
        )

    def get_source_document_provenance(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        meta: DocumentMeta | None = None,
    ) -> SourceDocumentProvenance:
        """从 published meta 或显式输入 meta 投影源文档溯源事实。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。
            meta: 可选、由调用方已读取的 published meta；未提供时由 storage 读取。

        Returns:
            storage owner 校验后的源文档溯源事实。

        Raises:
            FileNotFoundError: 未传 meta 且 published source meta 不存在时抛出。
            KeyError: meta 缺少必需溯源字段时抛出。
            ValueError: ticker、document ID、source kind 或溯源字段非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.get_source_document_provenance(
            ticker,
            document_id,
            source_kind,
            meta=meta,
        )

    def replace_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        meta: DocumentMeta,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中整体替换源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。
            meta: 完整替换元数据。
            batch: 同一 shared core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging source meta 不存在时抛出。
            ValueError: capability、source kind、ticker 或 document ID 非法时抛出。
            OSError: staging meta 或 manifest 写入失败时抛出。
        """

        self._repository_set.core.replace_source_meta(
            ticker,
            document_id,
            source_kind,
            meta,
            batch=batch,
        )

    def list_source_document_ids(self, ticker: str, source_kind: SourceKind) -> list[str]:
        """从 published tree 按来源列出源文档 ID。

        Args:
            ticker: 股票代码。
            source_kind: filing 或 material 来源类型。

        Returns:
            published 文档 ID 排序列表。

        Raises:
            ValueError: ticker 或 source kind 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        return self._repository_set.core.list_document_ids(ticker, source_kind)

    def get_source_handle(self, ticker: str, document_id: str, source_kind: SourceKind) -> SourceHandle:
        """从 published tree 校验并构造源文档句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            published source handle。

        Raises:
            FileNotFoundError: published source meta 不存在时抛出。
            ValueError: ticker、document ID 或 source kind 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        return self._repository_set.core.get_source_handle(ticker, document_id, source_kind)

    def get_primary_file(self, ticker: str, document_id: str, source_kind: SourceKind) -> FileObjectMeta:
        """从 published tree 读取源文档主文件对象元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            published 主文件对象元数据。

        Raises:
            FileNotFoundError: published source 或主文件不存在时抛出。
            ValueError: ticker、document ID、source kind 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        handle = _build_source_handle(ticker, document_id, source_kind)
        return self._repository_set.core.get_primary_file(handle)

    def get_source(self, ticker: str, document_id: str, source_kind: SourceKind, filename: str) -> Source:
        """从 published tree 构造指定文件的 delayed-open Source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。
            filename: published source 文件名。

        Returns:
            文件描述符打开阶段重新获取 publication guard 的 Source。

        Raises:
            FileNotFoundError: published 文档、meta 或目标文件不存在时抛出。
            ValueError: ticker、document ID、source kind、filename 或 URI 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 或 Source 构造失败时抛出。
        """

        handle = _build_source_handle(ticker, document_id, source_kind)
        return self._repository_set.core.get_source_by_filename(handle, filename)

    def get_primary_source(self, ticker: str, document_id: str, source_kind: SourceKind) -> Source:
        """从 published tree 构造主文件的 delayed-open Source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            文件描述符打开阶段重新获取 publication guard 的 Source。

        Raises:
            FileNotFoundError: published source 或主文件不存在时抛出。
            ValueError: ticker、document ID、source kind、meta 或 URI 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 或 Source 构造失败时抛出。
        """

        return self._repository_set.core.get_primary_source(ticker, document_id, source_kind)
