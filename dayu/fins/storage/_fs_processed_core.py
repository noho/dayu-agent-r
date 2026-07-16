"""文件系统仓储 — 解析产物操作 mixin。"""

from __future__ import annotations

from pathlib import Path

from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    DocumentMeta,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedManifestItem,
    ProcessedUpdateRequest,
    ProcessedHandle,
    now_iso8601,
)

from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_identity import (
    _PROCESSED_IDENTITY_NAMESPACE,
    _identity_directory_for_read,
    _read_identity_descriptor,
    _require_external_identity,
)
from ._fs_storage_utils import (
    _PROCESSED_META_FILENAME,
    _list_directory,
    _read_json_array,
    _read_json_object,
    _unlink_path,
    _write_json,
)


class _FsProcessedMixin(_FsStorageInfra):
    """解析产物（processed）操作 mixin。"""

    # ========== processed CRUD ==========

    def create_processed(
        self,
        req: ProcessedCreateRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """创建解析产物。

        Args:
            req: 解析产物创建请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 产物已存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_processed(req, True, state)

    def update_processed(
        self,
        req: ProcessedUpdateRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """更新解析产物。

        Args:
            req: 解析产物更新请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 更新失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_processed(req, False, state)

    def delete_processed(self, req: ProcessedDeleteRequest, *, batch: BatchToken) -> None:
        """删除解析产物。

        Args:
            req: 解析产物删除请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: 删除失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        self._delete_processed_impl(req, state)

    def _delete_processed_impl(
        self,
        req: ProcessedDeleteRequest,
        state: _ActiveBatchState,
    ) -> None:
        """执行解析产物删除（内部实现）。

        Args:
            req: 解析产物删除请求。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            ValueError: identity descriptor 或 processed meta 不一致时抛出。
            OSError: 删除失败时抛出。
        """

        ticker = _require_external_identity(req.ticker, field_name="ticker")
        document_id = _require_external_identity(req.document_id, field_name="document_id")
        processed_dir = self._processed_dir_for_write(ticker, document_id, state)
        meta_path = processed_dir / _PROCESSED_META_FILENAME
        if not meta_path.exists():
            raise FileNotFoundError(
                f"processed 文档不存在: ticker={ticker} document_id={document_id}"
            )
        meta = _read_json_object(meta_path)
        if meta.get("document_id") != document_id:
            raise ValueError("processed meta 与 identity descriptor 不一致")
        self._remove_directory(processed_dir)
        self._remove_manifest_item(
            self._processed_manifest_path(ticker, state),
            ticker,
            document_id,
        )

    # ========== handle & 元数据 ==========

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """从 published tree 获取解析产物句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: ticker、document ID、descriptor 或 meta 不合法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: descriptor 或 meta 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_processed_handle_unguarded(
                external_ticker,
                external_document_id,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_processed_handle_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
    ) -> ProcessedHandle:
        """在 caller 已持 publication guard 时构造 processed 句柄。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。

        Returns:
            processed 句柄。

        Raises:
            FileNotFoundError: processed meta 不存在时抛出。
            ValueError: descriptor 或 processed meta 不一致时抛出。
            OSError: descriptor 或 meta 读取失败时抛出。
        """

        meta_path = self._processed_meta_path_for_read(
            external_ticker,
            external_document_id,
        )
        if not meta_path.exists():
            raise FileNotFoundError(
                "processed 文档不存在: "
                f"ticker={external_ticker} document_id={external_document_id}"
            )
        meta = _read_json_object(meta_path)
        if meta.get("document_id") != external_document_id:
            raise ValueError("processed meta 与 identity descriptor 不一致")
        return ProcessedHandle(ticker=external_ticker, document_id=external_document_id)

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """从 published tree 读取 processed 元数据。

        只读取 published ``tool_snapshot_meta.json``。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed 元数据字典。

        Raises:
            FileNotFoundError: published ``tool_snapshot_meta.json`` 不存在时抛出。
            ValueError: 元数据格式非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_processed_meta_unguarded(
                external_ticker,
                external_document_id,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_processed_meta_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
    ) -> DocumentMeta:
        """在 caller 已持 publication guard 时读取 processed meta。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。

        Returns:
            processed 元数据。

        Raises:
            FileNotFoundError: processed meta 不存在时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta_path = self._processed_meta_path_for_read(
            external_ticker,
            external_document_id,
        )
        if meta_path.exists():
            meta = _read_json_object(meta_path)
            if meta.get("document_id") != external_document_id:
                raise ValueError("processed meta 与 identity descriptor 不一致")
            return meta
        raise FileNotFoundError(
            "processed 元数据不存在: "
            f"ticker={external_ticker} document_id={external_document_id}"
        )

    # ========== reprocess ==========

    def mark_processed_reprocess_required(
        self,
        ticker: str,
        document_id: str,
        required: bool,
        *,
        batch: BatchToken,
    ) -> None:
        """将 processed 文档标记为需要重处理。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            required: 是否需要重处理。
            batch: 显式 transaction capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或 document ID 非法时抛出。
            OSError: 读写失败时抛出。
        """

        state = self._resolve_active_batch(batch, ticker)
        if not required:
            return
        self._mark_processed_reprocess_required_impl(ticker, document_id, state)

    def _mark_processed_reprocess_required_impl(
        self,
        ticker: str,
        document_id: str,
        state: _ActiveBatchState,
    ) -> None:
        """执行重处理标记写入（内部实现）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            ValueError: ticker、document ID、descriptor 或 meta 不合法时抛出。
            OSError: 读写失败时抛出。
        """

        self._require_state_ticker(
            state,
            _require_external_identity(ticker, field_name="ticker"),
        )
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        processed_dir = _identity_directory_for_read(
            state.staging_ticker_dir / "processed",
            _PROCESSED_IDENTITY_NAMESPACE,
            external_document_id,
        )
        processed_meta_path = processed_dir / _PROCESSED_META_FILENAME
        if not processed_meta_path.exists():
            return
        processed_meta = _read_json_object(processed_meta_path)
        if processed_meta.get("document_id") != external_document_id:
            raise ValueError("processed meta 与 identity descriptor 不一致")
        processed_meta["reprocess_required"] = True
        processed_meta["updated_at"] = now_iso8601()
        _write_json(processed_meta_path, processed_meta)

    # ========== 批量清理 ==========

    def _preflight_processed_cleanup(
        self,
        external_ticker: str,
        state: _ActiveBatchState,
    ) -> list[Path]:
        """在任何 processed clear mutation 前验证整棵 staging processed tree。

        Args:
            external_ticker: exact external ticker。
            state: 已解析的内部 transaction state。

        Returns:
            通过完整 preflight 的 processed root 直系条目快照。

        Raises:
            ValueError: root、control file、identity、meta 或 manifest 不一致时抛出。
            OSError: 枚举或读取失败时抛出无物理 locator 的异常。
        """

        processed_root = self._ticker_dir_for_write(external_ticker, state) / "processed"
        if not processed_root.exists():
            return []
        if processed_root.is_symlink() or not processed_root.is_dir():
            raise ValueError("processed root 必须为 non-symlink directory")
        entries = _list_directory(
            processed_root,
            action="枚举 processed cleanup entries",
        )
        descriptor_document_ids: list[str] = []
        for child in entries:
            if child.name == "manifest.json":
                if child.is_symlink() or not child.is_file():
                    raise ValueError("processed manifest 必须为 non-symlink regular file")
                continue
            if child.is_symlink() or not child.is_dir():
                raise ValueError("processed root 存在非法条目")
            external_document_id = _read_identity_descriptor(
                child,
                _PROCESSED_IDENTITY_NAMESPACE,
            )
            meta_path = child / _PROCESSED_META_FILENAME
            if meta_path.is_symlink() or not meta_path.is_file():
                raise ValueError("processed meta 必须为 non-symlink regular file")
            meta = _read_json_object(meta_path)
            if meta.get("document_id") != external_document_id:
                raise ValueError("processed meta 与 identity descriptor 不一致")
            for document_entry in _list_directory(
                child,
                action="枚举 processed document entries",
            ):
                if document_entry.is_symlink() or not document_entry.is_file():
                    raise ValueError("processed document 存在非法文件条目")
            descriptor_document_ids.append(external_document_id)

        manifest = self._read_manifest(
            self._processed_manifest_path(external_ticker, state),
            external_ticker,
        )
        raw_documents = manifest.get("documents")
        if not isinstance(raw_documents, list):
            raise ValueError("processed manifest documents 必须为数组")
        manifest_document_ids: list[str] = []
        for raw_document in raw_documents:
            if not isinstance(raw_document, dict):
                raise ValueError("processed manifest document 必须为 object")
            raw_document_id = raw_document.get("document_id")
            if not isinstance(raw_document_id, str):
                raise ValueError("processed manifest document_id 必须为字符串")
            external_document_id = _require_external_identity(
                raw_document_id,
                field_name="processed manifest document_id",
            )
            if external_document_id in manifest_document_ids:
                raise ValueError("processed manifest document_id 重复")
            manifest_document_ids.append(external_document_id)
        if sorted(manifest_document_ids) != sorted(descriptor_document_ids):
            raise ValueError("processed manifest 与 identity descriptors 不双向一致")
        return entries

    def clear_processed_documents(self, ticker: str, *, batch: BatchToken) -> None:
        """清空某个 ticker 下的 processed 目录内容。

        Args:
            ticker: 股票代码。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            ValueError: capability 或 ticker 非法时抛出。
            OSError: 清理失败时抛出。
        """

        state = self._resolve_active_batch(batch, ticker)
        self._clear_processed_documents_impl(ticker, state)

    def _clear_processed_documents_impl(self, ticker: str, state: _ActiveBatchState) -> None:
        """执行 processed 目录清理（内部实现）。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            ValueError: ticker、document ID 或 identity directory 不合法时抛出。
            OSError: 清理失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        processed_dir = self._ticker_dir_for_write(external_ticker, state) / "processed"
        if not processed_dir.exists():
            return
        cleanup_entries = self._preflight_processed_cleanup(external_ticker, state)
        for child in cleanup_entries:
            if child.is_dir():
                self._remove_directory(child)
                continue
            _unlink_path(
                child,
                missing_ok=True,
                action="删除 processed cleanup control file",
            )

    # ========== 内部实现 ==========

    def _upsert_processed(
        self,
        req: ProcessedCreateRequest | ProcessedUpdateRequest,
        is_create: bool,
        state: _ActiveBatchState,
    ) -> DocumentHandle:
        """创建或更新解析产物。

        Args:
            req: 解析产物请求。
            is_create: 是否创建流程。
            state: 已解析的内部 transaction state。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 创建时已存在。
            FileNotFoundError: 更新时不存在。
            ValueError: identity descriptor 或 processed meta 不一致时抛出。
            OSError: 写入失败。
        """

        ticker = _require_external_identity(req.ticker, field_name="ticker")
        document_id = _require_external_identity(req.document_id, field_name="document_id")
        processed_dir = self._processed_dir_for_write(ticker, document_id, state)
        meta_path = processed_dir / _PROCESSED_META_FILENAME

        exists = meta_path.exists()
        if is_create and exists:
            raise FileExistsError(
                f"processed 文档已存在: ticker={ticker} document_id={document_id}"
            )
        if not is_create and not exists:
            raise FileNotFoundError(
                f"processed 文档不存在: ticker={ticker} document_id={document_id}"
            )

        processed_dir.mkdir(parents=True, exist_ok=True)
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}
        if previous_meta and previous_meta.get("document_id") != document_id:
            raise ValueError("processed meta 与 identity descriptor 不一致")
        financials_path = processed_dir / "financials.json"

        if req.sections is not None:
            _write_json(processed_dir / "sections.json", req.sections)
        if req.tables is not None:
            _write_json(processed_dir / "tables.json", req.tables)
        if req.financials is not None:
            _write_json(financials_path, req.financials)
        elif financials_path.exists():
            # 显式移除旧 financials，避免 has_xbrl 被历史产物污染。
            _unlink_path(
                financials_path,
                missing_ok=False,
                action="删除旧 processed financials",
            )

        sections_path = processed_dir / "sections.json"
        tables_path = processed_dir / "tables.json"

        section_count = len(_read_json_array(sections_path)) if sections_path.exists() else 0
        table_count = len(_read_json_array(tables_path)) if tables_path.exists() else 0
        has_xbrl = financials_path.exists()

        merged_meta = dict(previous_meta)
        merged_meta.update(req.meta)
        merged_meta["document_id"] = document_id
        merged_meta["internal_document_id"] = req.internal_document_id
        merged_meta["source_kind"] = req.source_kind
        merged_meta.setdefault("source_document_version", "v1")
        merged_meta.setdefault("schema_version", "v1")
        merged_meta.setdefault("parser_version", "v1")
        merged_meta.setdefault("source_fingerprint", "")
        merged_meta.setdefault("reprocess_required", False)
        merged_meta["section_count"] = section_count
        merged_meta["table_count"] = table_count
        merged_meta["has_xbrl"] = has_xbrl
        merged_meta["processed_at"] = now_iso8601()

        _write_json(meta_path, merged_meta)

        self._upsert_processed_manifest(
            state,
            [
                ProcessedManifestItem(
                    document_id=document_id,
                    internal_document_id=req.internal_document_id,
                    source_kind=req.source_kind,
                    form_type=req.form_type,
                    material_name=merged_meta.get("material_name"),
                    fiscal_year=merged_meta.get("fiscal_year"),
                    fiscal_period=merged_meta.get("fiscal_period"),
                    report_date=merged_meta.get("report_date"),
                    filing_date=merged_meta.get("filing_date"),
                    amended=bool(merged_meta.get("amended", False)),
                    is_deleted=bool(merged_meta.get("is_deleted", False)),
                    document_version=str(merged_meta.get("source_document_version", "v1")),
                    quality=str(merged_meta.get("quality", "full")),
                    has_financials=has_xbrl,
                    section_count=section_count,
                    table_count=table_count,
                )
            ],
        )

        return DocumentHandle(
            ticker=ticker,
            document_id=document_id,
            form_type=req.form_type,
        )
