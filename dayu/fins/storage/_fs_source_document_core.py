"""文件系统仓储 — 源文档操作 mixin。"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from typing import Final, Optional

from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.source import Source
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    DocumentMeta,
    DocumentQuery,
    DocumentSummary,
    FileObjectMeta,
    FilingCreateRequest,
    FilingDeleteRequest,
    FilingManifestItem,
    FilingRestoreRequest,
    FilingUpdateRequest,
    MaterialCreateRequest,
    MaterialDeleteRequest,
    MaterialManifestItem,
    MaterialRestoreRequest,
    MaterialUpdateRequest,
    SourceDocumentProvenance,
    SourceDocumentRevision,
    SourceDocumentUpsertRequest,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.xbrl_file_discovery import has_xbrl_instance

from .local_file_source import LocalFileSource
from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_storage_utils import (
    _SOURCE_META_FILENAME,
    _build_file_payloads,
    _extract_file_payloads,
    _file_object_meta_from_dict,
    _guess_media_type,
    _infer_filename_from_uri,
    _list_directory_names,
    _local_path_from_uri,
    _normalize_document_id,
    _normalize_file_entries,
    _normalize_source_kind,
    _normalize_ticker,
    _read_json_object,
    _resolve_primary_uri,
    _write_json,
)


_SOURCE_REVISION_REQUIRED_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "document_version",
    "source_fingerprint",
)
"""source revision 必须消费且不得为 null 的字符串字段。"""

_SOURCE_REVISION_OPTIONAL_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "form_type",
    "primary_document",
)
"""source revision 中允许缺省为空的字符串字段。"""

_SOURCE_REVISION_FILE_OPTIONAL_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "etag",
    "last_modified",
    "sha256",
    "content_type",
)
"""文件 revision 投影中允许缺省为空的字符串字段。"""


def _read_revision_text_field(
    meta: Mapping[str, JsonValue],
    field_name: str,
    *,
    allow_missing: bool,
    allow_none: bool,
) -> str | None:
    """读取 source revision 使用的可选文本字段。

    Args:
        meta: source meta 或文件条目。
        field_name: 字段名。
        allow_missing: 是否允许字段缺省并规范为 ``None``。
        allow_none: 是否允许显式 JSON null。

    Returns:
        规范化字符串或 ``None``。

    Raises:
        KeyError: 必需字段缺失时抛出。
        ValueError: 字段不是字符串或 ``None`` 时抛出。
    """

    if field_name not in meta:
        if allow_missing:
            return None
        raise KeyError(f"source meta 缺少 revision 字段: {field_name}")
    value = meta[field_name]
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"source revision 字段 {field_name} 不得为 null")
    if not isinstance(value, str):
        raise ValueError(f"source revision 字段 {field_name} 必须为字符串或 null")
    return value


def _build_source_revision_file_payload(raw_file: JsonValue) -> dict[str, str | int | None]:
    """把单个 source file 条目收窄为稳定 revision 载荷。

    Args:
        raw_file: source meta ``files`` 中的原始条目。

    Returns:
        只含文件身份与内容字段的规范化载荷。

    Raises:
        ValueError: 文件条目或字段类型非法时抛出。
        KeyError: 文件条目缺少 ``name`` 或 ``uri`` 时抛出。
    """

    if not isinstance(raw_file, Mapping):
        raise ValueError("source revision files 条目必须为 object")
    name = _read_revision_text_field(raw_file, "name", allow_missing=False, allow_none=False)
    uri = _read_revision_text_field(raw_file, "uri", allow_missing=False, allow_none=False)
    if name is None or not name.strip():
        raise ValueError("source revision file.name 不能为空")
    if uri is None or not uri.strip():
        raise ValueError("source revision file.uri 不能为空")
    size = raw_file.get("size")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
        raise ValueError("source revision file.size 必须为非负整数或 null")
    payload: dict[str, str | int | None] = {
        "name": name,
        "uri": uri,
        "size": size,
    }
    for field_name in _SOURCE_REVISION_FILE_OPTIONAL_TEXT_FIELDS:
        payload[field_name] = _read_revision_text_field(
            raw_file,
            field_name,
            allow_missing=True,
            allow_none=True,
        )
    return payload


def _build_source_revision(meta: Mapping[str, JsonValue]) -> SourceDocumentRevision:
    """从 source meta 计算 processor 输入版本。

    Args:
        meta: storage owner 读取到的 source meta。

    Returns:
        基于 canonical JSON 与 SHA-256 的强类型版本投影。

    Raises:
        KeyError: 必需字段缺失时抛出。
        ValueError: 字段类型或内容非法时抛出。
        TypeError: canonical 载荷无法序列化时抛出。
    """

    revision_payload: dict[str, str | bool | list[dict[str, str | int | None]] | None] = {}
    for field_name in _SOURCE_REVISION_REQUIRED_TEXT_FIELDS:
        revision_payload[field_name] = _read_revision_text_field(
            meta,
            field_name,
            allow_missing=False,
            allow_none=False,
        )
    document_version = revision_payload["document_version"]
    if not isinstance(document_version, str) or not document_version.strip():
        raise ValueError("source revision 字段 document_version 不能为空")
    for field_name in _SOURCE_REVISION_OPTIONAL_TEXT_FIELDS:
        revision_payload[field_name] = _read_revision_text_field(
            meta,
            field_name,
            allow_missing=True,
            allow_none=True,
        )
    for field_name in ("ingest_complete", "is_deleted"):
        if field_name not in meta:
            raise KeyError(f"source meta 缺少 revision 字段: {field_name}")
        value = meta[field_name]
        if not isinstance(value, bool):
            raise ValueError(f"source revision 字段 {field_name} 必须为布尔值")
        revision_payload[field_name] = value
    raw_files = meta.get("files", [])
    if not isinstance(raw_files, list):
        raise ValueError("source revision 字段 files 必须为数组")
    file_payloads = [_build_source_revision_file_payload(raw_file) for raw_file in raw_files]
    file_payloads.sort(
        key=lambda payload: json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    )
    revision_payload["files"] = file_payloads
    canonical_json = json.dumps(
        revision_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return SourceDocumentRevision(digest=f"sha256:{digest}")


class _FsSourceDocumentMixin(_FsStorageInfra):
    """源文档（filing / material）操作 mixin。"""

    # ========== material CRUD ==========

    def create_material(
        self,
        req: MaterialCreateRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """创建材料文档。

        Args:
            req: 材料创建请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 文档已存在时抛出。
            FileNotFoundError: 输入文件不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_source_document(req, SourceKind.MATERIAL, True, state)

    def update_material(
        self,
        req: MaterialUpdateRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """更新材料文档。

        Args:
            req: 材料更新请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 文档或输入文件不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 更新失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_source_document(req, SourceKind.MATERIAL, False, state)

    def delete_material(self, req: MaterialDeleteRequest, *, batch: BatchToken) -> None:
        """逻辑删除材料文档。

        Args:
            req: 材料删除请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        self._toggle_source_deleted(
            req.ticker,
            req.document_id,
            SourceKind.MATERIAL,
            True,
            state,
        )

    def restore_material(
        self,
        req: MaterialRestoreRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """恢复材料文档。

        Args:
            req: 材料恢复请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._toggle_source_deleted(
            req.ticker,
            req.document_id,
            SourceKind.MATERIAL,
            False,
            state,
        )

    # ========== filing CRUD ==========

    def create_filing(
        self,
        req: FilingCreateRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """创建财报文档。

        Args:
            req: 财报创建请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 文档已存在时抛出。
            FileNotFoundError: 输入文件不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_source_document(req, SourceKind.FILING, True, state)

    def update_filing(
        self,
        req: FilingUpdateRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """更新财报文档。

        Args:
            req: 财报更新请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 文档或输入文件不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 更新失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_source_document(req, SourceKind.FILING, False, state)

    def delete_filing(self, req: FilingDeleteRequest, *, batch: BatchToken) -> None:
        """逻辑删除财报文档。

        Args:
            req: 财报删除请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        self._toggle_source_deleted(
            req.ticker,
            req.document_id,
            SourceKind.FILING,
            True,
            state,
        )

    def restore_filing(
        self,
        req: FilingRestoreRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """恢复财报文档。

        Args:
            req: 财报恢复请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._toggle_source_deleted(
            req.ticker,
            req.document_id,
            SourceKind.FILING,
            False,
            state,
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
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker、document ID 或 source kind 非法时抛出。
            OSError: 删除目录或 manifest 失败时抛出。
        """

        state = self._resolve_active_batch(batch, ticker)
        self._reset_source_document_impl(ticker, document_id, source_kind, state)

    # ========== 查询 ==========

    def get_document_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """从 published tree 读取文档元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            文档元数据字典。

        Raises:
            FileNotFoundError: 元数据不存在时抛出。
            ValueError: 元数据文件内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_document_meta_unguarded(normalized_ticker, normalized_document_id)
        finally:
            self._release_lock_token(guard_token)

    def _get_document_meta_unguarded(
        self,
        normalized_ticker: str,
        normalized_document_id: str,
    ) -> DocumentMeta:
        """在 caller 已持 publication guard 时读取任一文档 meta。

        Args:
            normalized_ticker: 已规范化 ticker。
            normalized_document_id: 已规范化文档 ID。

        Returns:
            文档元数据。

        Raises:
            FileNotFoundError: 所有候选 meta 均不存在时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta_candidates = [
            self._source_meta_path_for_read(normalized_ticker, normalized_document_id, SourceKind.FILING),
            self._source_meta_path_for_read(normalized_ticker, normalized_document_id, SourceKind.MATERIAL),
            self._processed_meta_path_for_read(normalized_ticker, normalized_document_id),
        ]
        for meta_path in meta_candidates:
            if meta_path.exists():
                return _read_json_object(meta_path)
        raise FileNotFoundError(f"document_id={normalized_document_id} 的 meta.json 不存在")

    def get_source_meta(self, ticker: str, document_id: str, source_kind: SourceKind) -> DocumentMeta:
        """从 published tree 读取指定来源目录的源文档元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            源文档元数据字典。

        Raises:
            FileNotFoundError: 对应来源目录下的 meta.json 不存在时抛出。
            ValueError: 元数据文件内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_source_meta_unguarded(
                normalized_ticker,
                normalized_document_id,
                normalized_source_kind,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_source_meta_unguarded(
        self,
        normalized_ticker: str,
        normalized_document_id: str,
        normalized_source_kind: SourceKind,
    ) -> DocumentMeta:
        """在 caller 已持 publication guard 时读取 source meta。

        Args:
            normalized_ticker: 已规范化 ticker。
            normalized_document_id: 已规范化文档 ID。
            normalized_source_kind: 已规范化来源类型。

        Returns:
            source meta。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta_path = self._source_meta_path_for_read(normalized_ticker, normalized_document_id, normalized_source_kind)
        if not meta_path.exists():
            raise FileNotFoundError(
                f"document_id={normalized_document_id} 的 {normalized_source_kind.value} meta.json 不存在"
            )
        return _read_json_object(meta_path)

    def get_source_revision(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> SourceDocumentRevision:
        """从 published source meta 读取影响 processor 输入的源文档版本。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            由 canonical source meta 计算的强类型版本投影。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            KeyError: source meta 缺少必需版本字段时抛出。
            ValueError: source meta 版本字段类型或内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 底层文件系统读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            meta = self._get_source_meta_unguarded(
                normalized_ticker,
                normalized_document_id,
                normalized_source_kind,
            )
            return _build_source_revision(meta)
        finally:
            self._release_lock_token(guard_token)

    def get_source_document_provenance(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        meta: DocumentMeta | None = None,
    ) -> SourceDocumentProvenance:
        """从 published meta 或显式输入 meta 读取并校验源文档溯源事实。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            meta: 可选的已读取 source meta；提供时避免重复读取。

        Returns:
            已校验的源文档溯源事实。

        Raises:
            FileNotFoundError: 对应来源目录下的 meta.json 不存在时抛出。
            KeyError: meta 缺少必需溯源字段时抛出。
            ValueError: meta 溯源字段非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            source_meta = meta
            if source_meta is None:
                source_meta = self._get_source_meta_unguarded(
                    normalized_ticker,
                    normalized_document_id,
                    normalized_source_kind,
                )
            return SourceDocumentProvenance.from_meta(source_meta, normalized_source_kind)
        finally:
            self._release_lock_token(guard_token)

    def replace_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        meta: DocumentMeta,
        *,
        batch: BatchToken,
    ) -> None:
        """以精确覆盖方式写回源文档元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            meta: 完整元数据字典。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            FileNotFoundError: 目标源文档不存在时抛出。
            ValueError: capability、ticker、document ID 或 source kind 非法时抛出。
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        state = self._resolve_active_batch(batch, normalized_ticker)
        meta_path = self._source_meta_path(
            normalized_ticker,
            normalized_document_id,
            normalized_source_kind,
            state,
        )
        if not meta_path.exists():
            raise FileNotFoundError(
                f"document_id={document_id} 的 {normalized_source_kind.value} meta.json 不存在"
            )
        normalized_meta = _prepare_complete_source_meta(
            meta,
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            source_kind=normalized_source_kind,
        )
        _write_json(meta_path, normalized_meta)

        if normalized_source_kind == SourceKind.FILING:
            self._upsert_filing_manifest(
                state,
                [FilingManifestItem.from_source_meta(normalized_meta)],
            )
        else:
            self._upsert_material_manifest(
                state,
                [MaterialManifestItem.from_source_meta(normalized_meta)],
            )

    def list_documents(self, ticker: str, query: DocumentQuery) -> list[DocumentSummary]:
        """从 published processed manifest 查询文档摘要。

        Args:
            ticker: 股票代码。
            query: 查询条件。

        Returns:
            文档摘要列表。

        Raises:
            OSError: 读取 manifest 失败时抛出。
            ValueError: manifest 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._list_documents_unguarded(normalized_ticker, query)
        finally:
            self._release_lock_token(guard_token)

    def _list_documents_unguarded(
        self,
        normalized_ticker: str,
        query: DocumentQuery,
    ) -> list[DocumentSummary]:
        """在 caller 已持 publication guard 时查询 processed manifest。

        Args:
            normalized_ticker: 已规范化 ticker。
            query: 查询条件。

        Returns:
            文档摘要列表。

        Raises:
            OSError: manifest 读取失败时抛出。
            ValueError: manifest 内容非法时抛出。
        """

        manifest = self._read_manifest(self._processed_manifest_path_for_read(normalized_ticker), normalized_ticker)
        result: list[DocumentSummary] = []
        for item in manifest["documents"]:
            summary = DocumentSummary.from_dict(item)
            if not query.include_deleted and summary.is_deleted:
                continue
            if query.source_kind and summary.source_kind != query.source_kind:
                continue
            if query.form_type and summary.form_type != query.form_type:
                continue
            if query.fiscal_years and summary.fiscal_year not in query.fiscal_years:
                continue
            if query.fiscal_periods and summary.fiscal_period not in query.fiscal_periods:
                continue
            result.append(summary)
        return result

    def list_document_ids(self, ticker: str, source_kind: Optional[SourceKind] = None) -> list[str]:
        """从 published tree 列出文档 ID。

        Args:
            ticker: 股票代码。
            source_kind: 可选来源类型过滤。

        Returns:
            已排序文档 ID 列表。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取目录失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_source_kind = None if source_kind is None else _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._list_document_ids_unguarded(normalized_ticker, normalized_source_kind)
        finally:
            self._release_lock_token(guard_token)

    def _list_document_ids_unguarded(
        self,
        normalized_ticker: str,
        source_kind: SourceKind | None,
    ) -> list[str]:
        """在 caller 已持 publication guard 时列出 source 文档 ID。

        Args:
            normalized_ticker: 已规范化 ticker。
            source_kind: 可选来源类型。

        Returns:
            已排序文档 ID 列表。

        Raises:
            OSError: 读取目录失败时抛出。
        """

        if source_kind == SourceKind.FILING:
            return _list_directory_names(
                self._source_root_for_read(normalized_ticker, SourceKind.FILING)
            )
        if source_kind == SourceKind.MATERIAL:
            return _list_directory_names(
                self._source_root_for_read(normalized_ticker, SourceKind.MATERIAL)
            )
        filings = _list_directory_names(
            self._source_root_for_read(normalized_ticker, SourceKind.FILING)
        )
        materials = _list_directory_names(
            self._source_root_for_read(normalized_ticker, SourceKind.MATERIAL)
        )
        return sorted(set(filings + materials))

    def has_source_storage_root(self, ticker: str, source_kind: SourceKind) -> bool:
        """判断 published tree 中某类源文档根目录是否存在且为目录。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            若目录存在且为目录则返回 `True`，不存在返回 `False`。

        Raises:
            NotADirectoryError: 根路径存在但不是目录时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            root = self._source_root_for_read(normalized_ticker, normalized_source_kind)
            if not root.exists():
                return False
            if not root.is_dir():
                raise NotADirectoryError(f"source root 不是目录: {root}")
            return True
        finally:
            self._release_lock_token(guard_token)

    def has_filing_xbrl_instance(self, ticker: str, document_id: str) -> bool:
        """判断 published filing 目录下是否已落盘 XBRL instance 文件。

        Args:
            ticker: 股票代码。
            document_id: filing 文档 ID。

        Returns:
            若存在 XBRL instance 文件则返回 `True`，否则返回 `False`。

        Raises:
            FileNotFoundError: filing 目录不存在时抛出。
            NotADirectoryError: filing 路径存在但不是目录时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._has_filing_xbrl_instance_unguarded(
                normalized_ticker,
                normalized_document_id,
            )
        finally:
            self._release_lock_token(guard_token)

    def _has_filing_xbrl_instance_unguarded(
        self,
        normalized_ticker: str,
        normalized_document_id: str,
    ) -> bool:
        """在 caller 已持 publication guard 时检查 filing XBRL instance。

        Args:
            normalized_ticker: 已规范化 ticker。
            normalized_document_id: 已规范化文档 ID。

        Returns:
            是否存在 XBRL instance。

        Raises:
            FileNotFoundError: filing 目录不存在时抛出。
            NotADirectoryError: filing 路径不是目录时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        filing_dir = (
            self._source_root_for_read(normalized_ticker, SourceKind.FILING)
            / normalized_document_id
        )
        if not filing_dir.exists():
            raise FileNotFoundError(f"filing 目录不存在: {filing_dir}")
        if not filing_dir.is_dir():
            raise NotADirectoryError(f"filing 路径不是目录: {filing_dir}")
        return has_xbrl_instance(filing_dir)

    def has_staged_filing_xbrl_instance(
        self,
        ticker: str,
        document_id: str,
        *,
        batch: BatchToken,
    ) -> bool:
        """显式读取 transaction staging 中的 filing XBRL instance。

        Args:
            ticker: 股票代码。
            document_id: filing 文档 ID。
            batch: 显式 transaction capability。

        Returns:
            是否存在 XBRL instance。

        Raises:
            ValueError: batch capability 非法时抛出。
            FileNotFoundError: staging filing 目录不存在时抛出。
            NotADirectoryError: staging filing 路径不是目录时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        state = self._resolve_active_batch(batch, normalized_ticker)
        filing_dir = state.staging_ticker_dir / "filings" / normalized_document_id
        if not filing_dir.exists():
            raise FileNotFoundError(f"staging filing 目录不存在: {filing_dir}")
        if not filing_dir.is_dir():
            raise NotADirectoryError(f"staging filing 路径不是目录: {filing_dir}")
        return has_xbrl_instance(filing_dir)

    def _reset_source_document_impl(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        state: _ActiveBatchState,
    ) -> None:
        """执行单文档重置（内部实现）。

        行为与错误传播：

        - 目标目录存在且为目录：调用 ``shutil.rmtree`` 物理删除整个文档目录。
          若目录下存在无权限的子项或只读文件，``rmtree`` 会抛 ``OSError``。
        - 目标是文件（少数异常路径下出现）：``unlink(missing_ok=True)`` 删除。
        - 随后从对应 manifest 中移除该 document_id 条目。

        设计决策（异常直抛，不做回退）：
            该方法作为 ``overwrite`` 重建路径的第一步，一旦删除失败（例如权限
            受限、文件系统忙），**必须**让异常向上传播；宁可让整个 upload
            流程失败，也不允许仓储侧保留"旧数据残留 + 新 manifest 条目"的
            不一致状态。上传覆盖路径在准备好新材料后，于同一 batch 内调用
            该方法并感知这里抛出的 ``OSError``。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            OSError: 删除目录、文件或 manifest 失败时抛出；调用方有责任感知并
                中止后续写入，以保证仓储一致性。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        document_dir = (
            self._source_root(normalized_ticker, normalized_source_kind, state)
            / normalized_document_id
        )
        if document_dir.exists():
            if document_dir.is_dir():
                shutil.rmtree(document_dir)
            else:
                document_dir.unlink(missing_ok=True)
        if normalized_source_kind == SourceKind.FILING:
            manifest_path = self._filing_manifest_path(normalized_ticker, state)
        else:
            manifest_path = self._material_manifest_path(normalized_ticker, state)
        if manifest_path.exists():
            self._remove_manifest_item(manifest_path, normalized_ticker, normalized_document_id)

    # ========== handle & 文件访问 ==========

    def get_source_handle(self, ticker: str, document_id: str, source_kind: SourceKind) -> SourceHandle:
        """从 published tree 获取源文档句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            源文档句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_source_handle_unguarded(
                normalized_ticker,
                normalized_document_id,
                normalized_source_kind,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_source_handle_unguarded(
        self,
        normalized_ticker: str,
        normalized_document_id: str,
        normalized_source_kind: SourceKind,
    ) -> SourceHandle:
        """在 caller 已持 publication guard 时构造 source handle。

        Args:
            normalized_ticker: 已规范化 ticker。
            normalized_document_id: 已规范化文档 ID。
            normalized_source_kind: 已规范化来源类型。

        Returns:
            source handle。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
        """

        meta_path = self._source_meta_path_for_read(normalized_ticker, normalized_document_id, normalized_source_kind)
        if not meta_path.exists():
            raise FileNotFoundError(
                f"document_id={normalized_document_id} 不存在于 {normalized_source_kind}"
            )
        return SourceHandle(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            source_kind=normalized_source_kind.value,
        )

    def get_primary_file(self, handle: SourceHandle) -> FileObjectMeta:
        """从 published tree 获取源文档主文件元数据。

        Args:
            handle: 源文档句柄。

        Returns:
            主文件元数据。

        Raises:
            FileNotFoundError: 主文件无法定位时抛出。
            ValueError: 元数据格式非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_primary_file_unguarded(handle)
        finally:
            self._release_lock_token(guard_token)

    def _get_primary_file_unguarded(self, handle: SourceHandle) -> FileObjectMeta:
        """在 caller 已持 publication guard 时读取主文件元数据。

        Args:
            handle: source handle。

        Returns:
            主文件元数据。

        Raises:
            FileNotFoundError: source 或主文件无法定位时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta = self._get_handle_meta(handle)
        files = meta.get("files", [])
        if not isinstance(files, list):
            raise ValueError("meta.files 必须为 list")
        if not files:
            raise FileNotFoundError("源文档未绑定文件，无法定位主文件")
        primary_name = str(meta.get("primary_document", "")).strip()
        if not primary_name:
            raise FileNotFoundError("源文档 primary_document 不能为空")
        for item in files:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or _infer_filename_from_uri(item.get("uri", ""))).strip()
            if name == primary_name:
                return _file_object_meta_from_dict(item)
        raise FileNotFoundError("源文档 primary_document 未命中 files")

    def get_source(self, handle: SourceHandle, file_meta: FileObjectMeta) -> Source:
        """根据 published 文件元数据构造 delayed-open Source。

        Args:
            handle: 源文档句柄。
            file_meta: 文件元数据。

        Returns:
            Source 抽象。

        Raises:
            ValueError: 文件元数据非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 构建 Source 失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_source_unguarded(handle, file_meta)
        finally:
            self._release_lock_token(guard_token)

    def _get_source_unguarded(
        self,
        handle: SourceHandle,
        file_meta: FileObjectMeta,
    ) -> Source:
        """在 caller 已持 publication guard 时构造延迟 guarded Source。

        Args:
            handle: source handle。
            file_meta: 文件元数据。

        Returns:
            带 storage-owned delayed opener 的 Source。

        Raises:
            ValueError: 文件 URI 非法或越界时抛出。
            OSError: 路径解析失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        uri = str(file_meta.uri or "").strip()
        if not uri:
            raise ValueError("file_meta.uri 不能为空")
        path = _local_path_from_uri(self.portfolio_root, uri)
        media_type = file_meta.content_type or _guess_media_type(path)
        return LocalFileSource(
            path=path,
            uri=uri,
            media_type=media_type,
            content_length=file_meta.size,
            etag=file_meta.etag,
            opener=self._publication_guarded_binary_opener(normalized_ticker),
        )

    def get_source_by_filename(self, handle: SourceHandle, filename: str) -> Source:
        """按文件名读取 source，并只获取一次 publication guard。

        Args:
            handle: source handle。
            filename: 目标文件名。

        Returns:
            带 storage-owned delayed opener 的 Source。

        Raises:
            FileNotFoundError: source 或目标文件不存在时抛出。
            ValueError: meta、URI 或 filename 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        normalized_filename = filename.strip()
        if not normalized_filename:
            raise FileNotFoundError("filename 不能为空")
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            file_metas = self._list_handle_files_unguarded(handle)
            for file_meta in file_metas:
                if _infer_filename_from_uri(file_meta.uri) == normalized_filename:
                    return self._get_source_unguarded(handle, file_meta)
            raise FileNotFoundError(f"未找到文件: {normalized_filename}")
        finally:
            self._release_lock_token(guard_token)

    def get_primary_source(self, ticker: str, document_id: str, source_kind: SourceKind) -> Source:
        """从 published tree 获取源文档主文件的 delayed-open Source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            Source 抽象。

        Raises:
            FileNotFoundError: 文档或主文件不存在时抛出。
            ValueError: 文件元数据非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 构建 Source 失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            handle = self._get_source_handle_unguarded(
                normalized_ticker,
                normalized_document_id,
                normalized_source_kind,
            )
            primary_file = self._get_primary_file_unguarded(handle)
            return self._get_source_unguarded(handle, primary_file)
        finally:
            self._release_lock_token(guard_token)

    # ========== 内部实现 ==========

    def _upsert_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        is_create: bool,
        state: _ActiveBatchState,
    ) -> DocumentHandle:
        """创建或更新源文档。

        Args:
            req: 源文档写入请求。
            source_kind: 文档来源类型。
            is_create: 是否创建流程。
            state: 已解析的内部 transaction state。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 创建时文档已存在。
            FileNotFoundError: 更新时文档不存在或拷贝文件不存在。
            OSError: 写入失败。
        """

        ticker = _normalize_ticker(req.ticker)
        normalized_document_id = _normalize_document_id(req.document_id)
        source_root = self._source_root(ticker, source_kind, state)
        source_root.mkdir(parents=True, exist_ok=True)
        document_dir = source_root / normalized_document_id
        meta_path = document_dir / _SOURCE_META_FILENAME

        meta_exists = meta_path.exists()
        if is_create and meta_exists:
            raise FileExistsError(f"文档已存在: {meta_path}")
        if not is_create and not meta_exists:
            raise FileNotFoundError(f"文档不存在: {meta_path}")

        document_dir.mkdir(parents=True, exist_ok=True)
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}

        previous_files = _extract_file_payloads(previous_meta)
        if req.file_entries is not None:
            file_payloads = _normalize_file_entries(req.file_entries)
        elif req.files:
            file_payloads = _build_file_payloads(req.files)
        else:
            file_payloads = previous_files
        now = now_iso8601()

        merged_meta = dict(previous_meta)
        merged_meta.update(req.meta)
        merged_meta["ticker"] = ticker
        merged_meta["document_id"] = normalized_document_id
        merged_meta["source_kind"] = source_kind.value
        merged_meta["internal_document_id"] = req.internal_document_id
        merged_meta["form_type"] = req.form_type or merged_meta.get("form_type")
        merged_meta["updated_at"] = now
        merged_meta.setdefault("created_at", now)
        merged_meta.setdefault("first_ingested_at", now)
        merged_meta.setdefault("is_deleted", False)
        merged_meta.setdefault("deleted_at", None)
        merged_meta.setdefault("document_version", "v1")
        merged_meta.setdefault("source_fingerprint", "")

        selected_primary_document = self._select_primary_document(
            explicit_primary=req.primary_document,
            previous_primary=previous_meta.get("primary_document"),
        )
        if selected_primary_document is not None:
            merged_meta["primary_document"] = selected_primary_document
        else:
            merged_meta.pop("primary_document", None)
        merged_meta["files"] = file_payloads
        merged_meta = _prepare_complete_source_meta(
            merged_meta,
            ticker=ticker,
            document_id=normalized_document_id,
            source_kind=source_kind,
        )

        _write_json(meta_path, merged_meta)

        if source_kind == SourceKind.FILING:
            self._upsert_filing_manifest(
                state,
                [FilingManifestItem.from_source_meta(merged_meta)],
            )
        else:
            self._upsert_material_manifest(
                state,
                [MaterialManifestItem.from_source_meta(merged_meta)],
            )

        primary_file_uri = (
            _resolve_primary_uri(file_payloads, selected_primary_document)
            if selected_primary_document is not None
            else None
        )
        return DocumentHandle(
            ticker=ticker,
            document_id=normalized_document_id,
            form_type=merged_meta.get("form_type"),
            primary_file_uri=primary_file_uri,
            file_uris=[str(item.get("uri")) for item in file_payloads if isinstance(item, dict)],
        )

    def _toggle_source_deleted(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        deleted: bool,
        state: _ActiveBatchState,
    ) -> DocumentHandle:
        """切换源文档逻辑删除状态。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            deleted: 目标删除状态。
            state: 已解析的内部 transaction state。

        Returns:
            更新后的文档句柄。

        Raises:
            FileNotFoundError: 文档不存在。
            OSError: 写入失败。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        meta_path = self._source_meta_path(
            normalized_ticker,
            normalized_document_id,
            source_kind,
            state,
        )
        if not meta_path.exists():
            raise FileNotFoundError(f"文档不存在: {meta_path}")

        meta = _read_json_object(meta_path)
        meta["is_deleted"] = deleted
        meta["deleted_at"] = now_iso8601() if deleted else None
        meta["updated_at"] = now_iso8601()
        meta = _prepare_complete_source_meta(
            meta,
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            source_kind=source_kind,
        )
        _write_json(meta_path, meta)

        if source_kind == SourceKind.FILING:
            self._upsert_filing_manifest(
                state,
                [FilingManifestItem.from_source_meta(meta)],
            )
        else:
            self._upsert_material_manifest(
                state,
                [MaterialManifestItem.from_source_meta(meta)],
            )

        file_payloads = _extract_file_payloads(meta)
        return DocumentHandle(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            form_type=meta.get("form_type"),
            primary_file_uri=_resolve_primary_uri(
                file_payloads,
                str(meta.get("primary_document", "")).strip() or None,
            ),
            file_uris=[str(item.get("uri")) for item in file_payloads if isinstance(item, dict)],
        )


def _prepare_complete_source_meta(
    meta: DocumentMeta,
    *,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> DocumentMeta:
    """在 source mutation owner boundary 规范身份并强制完成态。

    Args:
        meta: producer 提供或现有 source 读取到的完整业务元数据。
        ticker: 已规范化 ticker。
        document_id: 已规范化文档 ID。
        source_kind: 已规范化 source kind。

    Returns:
        身份字段由 storage owner 覆盖、完成态固定为 ``True`` 的新字典。

    Raises:
        KeyError: meta 缺少必需 provenance 字段时抛出。
        ValueError: producer 显式提供非 ``True`` 完成态或 provenance 非法时抛出。
    """

    requested_completion = meta.get("ingest_complete", True)
    if requested_completion is not True:
        raise ValueError("final source ingest_complete 必须为 true")
    normalized = dict(meta)
    normalized["ticker"] = ticker
    normalized["document_id"] = document_id
    normalized["source_kind"] = source_kind.value
    normalized["ingest_complete"] = True
    SourceDocumentProvenance.from_meta(normalized, source_kind)
    return normalized
