"""文件系统仓储 — 解析产物操作 mixin。"""

from __future__ import annotations

import shutil
from typing import Optional

from dayu.fins.domain.document_models import (
    DocumentHandle,
    DocumentMeta,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedManifestItem,
    ProcessedUpdateRequest,
    ProcessedHandle,
    now_iso8601,
)

from ._fs_storage_infra import _FsStorageInfra
from ._fs_storage_utils import (
    _PROCESSED_META_FILENAME,
    _normalize_ticker,
    _read_json_array,
    _read_json_object,
    _write_json,
)


class _FsProcessedMixin(_FsStorageInfra):
    """解析产物（processed）操作 mixin。"""

    # ========== processed CRUD ==========

    def create_processed(self, req: ProcessedCreateRequest) -> DocumentHandle:
        """创建解析产物。

        Args:
            req: 解析产物创建请求。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 产物已存在时抛出。
            OSError: 写入失败时抛出。
        """

        return self._execute_with_auto_batch(
            req.ticker,
            self._upsert_processed,
            req,
            True,
        )

    def update_processed(self, req: ProcessedUpdateRequest) -> DocumentHandle:
        """更新解析产物。

        Args:
            req: 解析产物更新请求。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            OSError: 更新失败时抛出。
        """

        return self._execute_with_auto_batch(
            req.ticker,
            self._upsert_processed,
            req,
            False,
        )

    def delete_processed(self, req: ProcessedDeleteRequest) -> None:
        """删除解析产物。

        Args:
            req: 解析产物删除请求。

        Returns:
            无。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            OSError: 删除失败时抛出。
        """

        self._execute_with_auto_batch(
            req.ticker,
            self._delete_processed_impl,
            req,
        )

    def _delete_processed_impl(self, req: ProcessedDeleteRequest) -> None:
        """执行解析产物删除（内部实现）。

        Args:
            req: 解析产物删除请求。

        Returns:
            无。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            OSError: 删除失败时抛出。
        """

        ticker = _normalize_ticker(req.ticker)
        processed_dir = self._processed_dir_for_write(ticker, req.document_id)
        if not processed_dir.exists():
            raise FileNotFoundError(f"processed 文档不存在: {processed_dir}")
        shutil.rmtree(processed_dir)
        self._remove_manifest_item(self._processed_manifest_path(ticker), ticker, req.document_id)

    # ========== handle & 元数据 ==========

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """获取解析产物句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        meta_path = self._processed_meta_path_for_read(normalized_ticker, document_id)
        if not meta_path.exists():
            raise FileNotFoundError(f"processed 文档不存在: {meta_path}")
        return ProcessedHandle(
            ticker=normalized_ticker,
            document_id=document_id,
        )

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """读取 processed 元数据。

        优先读取 ``meta.json``；若不存在则回退到 ``tool_snapshot_meta.json``
        （CI 管线产物）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed 元数据字典。

        Raises:
            FileNotFoundError: 两种元数据文件均不存在时抛出。
            ValueError: 元数据格式非法时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        meta_path = self._processed_meta_path_for_read(normalized_ticker, document_id)
        if meta_path.exists():
            return _read_json_object(meta_path)
        raise FileNotFoundError(f"processed 元数据不存在: {meta_path}")

    # ========== reprocess ==========

    def mark_processed_reprocess_required(self, ticker: str, document_id: str) -> bool:
        """将 processed 文档标记为需要重处理。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            是否成功标记。

        Raises:
            OSError: 读写失败时抛出。
        """

        return self._execute_with_auto_batch(
            ticker,
            self._mark_processed_reprocess_required_impl,
            ticker,
            document_id,
        )

    def _mark_processed_reprocess_required_impl(self, ticker: str, document_id: str) -> bool:
        """执行重处理标记写入（内部实现）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            是否成功标记。

        Raises:
            OSError: 读写失败时抛出。
        """

        processed_meta_path = self._processed_meta_path(_normalize_ticker(ticker), document_id)
        if not processed_meta_path.exists():
            return False
        processed_meta = _read_json_object(processed_meta_path)
        processed_meta["reprocess_required"] = True
        processed_meta["updated_at"] = now_iso8601()
        _write_json(processed_meta_path, processed_meta)
        return True

    # ========== 批量清理 ==========

    def clear_processed_documents(self, ticker: str) -> None:
        """清空某个 ticker 下的 processed 目录内容。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._clear_processed_documents_impl,
            ticker,
        )

    def _clear_processed_documents_impl(self, ticker: str) -> None:
        """执行 processed 目录清理（内部实现）。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        processed_dir = self._ticker_dir_for_write(normalized_ticker) / "processed"
        if not processed_dir.exists():
            return
        for child in processed_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                continue
            child.unlink(missing_ok=True)

    # ========== 内部实现 ==========

    def _upsert_processed(self, req: ProcessedCreateRequest | ProcessedUpdateRequest, is_create: bool) -> DocumentHandle:
        """创建或更新解析产物。

        Args:
            req: 解析产物请求。
            is_create: 是否创建流程。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 创建时已存在。
            FileNotFoundError: 更新时不存在。
            OSError: 写入失败。
        """

        ticker = _normalize_ticker(req.ticker)
        processed_dir = self._processed_dir_for_write(ticker, req.document_id)
        meta_path = processed_dir / _PROCESSED_META_FILENAME

        exists = processed_dir.exists()
        if is_create and exists:
            raise FileExistsError(f"processed 文档已存在: {processed_dir}")
        if not is_create and not exists:
            raise FileNotFoundError(f"processed 文档不存在: {processed_dir}")

        processed_dir.mkdir(parents=True, exist_ok=True)
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}
        financials_path = processed_dir / "financials.json"

        if req.sections is not None:
            _write_json(processed_dir / "sections.json", req.sections)
        if req.tables is not None:
            _write_json(processed_dir / "tables.json", req.tables)
        if req.financials is not None:
            _write_json(financials_path, req.financials)
        elif financials_path.exists():
            # 显式移除旧 financials，避免 has_xbrl 被历史产物污染。
            financials_path.unlink()

        sections_path = processed_dir / "sections.json"
        tables_path = processed_dir / "tables.json"

        section_count = len(_read_json_array(sections_path)) if sections_path.exists() else 0
        table_count = len(_read_json_array(tables_path)) if tables_path.exists() else 0
        has_xbrl = financials_path.exists()

        merged_meta = dict(previous_meta)
        merged_meta.update(req.meta)
        merged_meta["document_id"] = req.document_id
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

        self.upsert_processed_manifest(
            ticker,
            [
                ProcessedManifestItem(
                    document_id=req.document_id,
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
            document_id=req.document_id,
            form_type=req.form_type,
        )
