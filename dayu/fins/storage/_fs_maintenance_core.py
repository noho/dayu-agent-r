"""文件系统仓储 — 拒绝注册表与清理操作 mixin。"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from typing import BinaryIO, Optional, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins._log import Log

from dayu.fins.domain.document_models import (
    BatchToken,
    DownloadRejectionEntry,
    DownloadRejectionRegistry,
    FileObjectMeta,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
    now_iso8601,
)

from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_storage_utils import (
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _list_directory_names,
    _normalize_document_id,
    _normalize_ticker,
    _read_json_object,
    _write_json,
)


class _FsMaintenanceMixin(_FsStorageInfra):
    """拒绝注册表与清理操作 mixin。"""

    # ========== 下载拒绝注册表 ==========

    def load_download_rejection_registry(self, ticker: str) -> DownloadRejectionRegistry:
        """从 published tree 读取下载拒绝注册表。

        Args:
            ticker: 股票代码。

        Returns:
            `document_id -> DownloadRejectionEntry` 映射；不存在时返回空字典。

        Raises:
            OSError: 底层读取失败时抛出。
            ValueError: registry JSON 或条目字段非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._load_download_rejection_registry_unguarded(normalized_ticker)
        finally:
            self._release_lock_token(guard_token)

    def _load_download_rejection_registry_unguarded(
        self,
        normalized_ticker: str,
    ) -> DownloadRejectionRegistry:
        """在 caller 已持 publication guard 时读取拒绝注册表。

        Args:
            normalized_ticker: 已规范化 ticker。

        Returns:
            下载拒绝注册表。

        Raises:
            OSError: 文件读取失败时抛出。
            ValueError: registry 内容非法时抛出。
        """

        path = self._download_rejections_path_for_read(normalized_ticker)
        if not path.exists():
            return {}
        data = _read_json_object(path)
        result: DownloadRejectionRegistry = {}
        for document_id, payload in data.items():
            if not isinstance(document_id, str) or not isinstance(payload, dict):
                raise ValueError("download rejection registry 条目必须是 document_id 到对象的映射")
            normalized_document_id = _normalize_document_id(document_id)
            entry = DownloadRejectionEntry.from_dict(
                cast(Mapping[str, JsonValue], payload),
                expected_document_id=normalized_document_id,
            )
            result[normalized_document_id] = entry
        return result

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: DownloadRejectionRegistry,
        *,
        batch: BatchToken,
    ) -> None:
        """保存下载拒绝注册表。

        Args:
            ticker: 股票代码。
            registry: `document_id -> DownloadRejectionEntry` 映射。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或 registry 内容非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, ticker)
        self._save_download_rejection_registry_impl(ticker, registry, state)

    def _save_download_rejection_registry_impl(
        self,
        ticker: str,
        registry: DownloadRejectionRegistry,
        state: _ActiveBatchState,
    ) -> None:
        """执行下载拒绝注册表持久化（内部实现）。

        Args:
            ticker: 股票代码。
            registry: `document_id -> DownloadRejectionEntry` 映射。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        path = self._download_rejections_path(normalized_ticker, state)
        payload: dict[str, dict[str, str]] = {}
        for document_id, entry in registry.items():
            normalized_document_id = _normalize_document_id(document_id)
            if normalized_document_id != _normalize_document_id(entry.document_id):
                raise ValueError("download rejection registry key 与条目 document_id 不一致")
            entry_payload = entry.to_dict()
            entry_payload["document_id"] = normalized_document_id
            payload[normalized_document_id] = entry_payload
        _write_json(path, payload)

    # ========== rejected filing artifact ==========

    def store_rejected_filing_file(
        self,
        ticker: str,
        document_id: str,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """写入 rejected filing 的文件对象。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。
            filename: 文件名。
            data: 文件字节流。
            batch: 显式 transaction capability。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            文件对象元数据。

        Raises:
            OSError: 写入失败时抛出。
            ValueError: 文件名为空时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        state = self._resolve_active_batch(batch, normalized_ticker)
        normalized_document_id = _normalize_document_id(document_id)
        normalized_filename = str(filename).strip()
        if not normalized_filename:
            raise ValueError("filename 不能为空")
        file_store = self._build_file_store(normalized_ticker, state)
        return file_store.put_object(
            f"{normalized_ticker}/filings/{_REJECTED_FILINGS_DIRNAME}/{normalized_document_id}/{normalized_filename}",
            data,
            content_type=content_type,
            metadata=metadata,
        )

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
        *,
        batch: BatchToken,
    ) -> RejectedFilingArtifact:
        """写入或更新 rejected filing artifact。

        Args:
            req: artifact 写入请求。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。

        Returns:
            写回后的 artifact。

        Raises:
            ValueError: capability 或请求字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, req.ticker)
        return self._upsert_rejected_filing_artifact_impl(req, state)

    def _upsert_rejected_filing_artifact_impl(
        self,
        req: RejectedFilingArtifactUpsertRequest,
        state: _ActiveBatchState,
    ) -> RejectedFilingArtifact:
        """执行 rejected filing artifact 写入。

        Args:
            req: artifact 写入请求。
            state: 已解析的内部 transaction state。

        Returns:
            写回后的 artifact。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(req.ticker)
        normalized_document_id = _normalize_document_id(req.document_id)
        meta_path = self._rejected_filing_meta_path(
            normalized_ticker,
            normalized_document_id,
            state,
        )
        now = now_iso8601()
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}
        artifact = RejectedFilingArtifact(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            internal_document_id=req.internal_document_id,
            accession_number=req.accession_number,
            company_id=req.company_id,
            form_type=req.form_type,
            filing_date=req.filing_date,
            report_date=req.report_date,
            primary_document=req.primary_document,
            selected_primary_document=req.selected_primary_document,
            rejection_reason=req.rejection_reason,
            rejection_category=req.rejection_category,
            classification_version=req.classification_version,
            source_fingerprint=req.source_fingerprint,
            files=req.files,
            fiscal_year=req.fiscal_year,
            fiscal_period=req.fiscal_period,
            report_kind=req.report_kind,
            amended=req.amended,
            has_xbrl=req.has_xbrl,
            ingest_method=req.ingest_method,
            rejected_at=str(previous_meta.get("rejected_at", "")).strip() or now,
            created_at=str(previous_meta.get("created_at", "")).strip() or now,
            updated_at=now,
        )
        _write_json(meta_path, artifact.to_meta_dict())
        return artifact

    def get_rejected_filing_artifact(
        self,
        ticker: str,
        document_id: str,
    ) -> RejectedFilingArtifact:
        """从 published tree 读取 rejected filing artifact。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            artifact 对象。

        Raises:
            FileNotFoundError: meta 不存在时抛出。
            ValueError: meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_rejected_filing_artifact_unguarded(
                normalized_ticker,
                normalized_document_id,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_rejected_filing_artifact_unguarded(
        self,
        normalized_ticker: str,
        normalized_document_id: str,
    ) -> RejectedFilingArtifact:
        """在 caller 已持 publication guard 时读取 rejected artifact。

        Args:
            normalized_ticker: 已规范化 ticker。
            normalized_document_id: 已规范化文档 ID。

        Returns:
            rejected filing artifact。

        Raises:
            FileNotFoundError: meta 不存在时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta = _read_json_object(
            self._rejected_filing_meta_path_for_read(normalized_ticker, normalized_document_id)
        )
        return RejectedFilingArtifact.from_meta_dict(meta)

    def list_rejected_filing_artifacts(
        self,
        ticker: str,
    ) -> list[RejectedFilingArtifact]:
        """从 published tree 列出某个 ticker 的 rejected filing artifacts。

        Args:
            ticker: 股票代码。

        Returns:
            artifact 列表，按 document_id 升序。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取目录失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            result: list[RejectedFilingArtifact] = []
            for document_id in _list_directory_names(
                self._rejected_filings_root_for_read(normalized_ticker)
            ):
                try:
                    result.append(
                        self._get_rejected_filing_artifact_unguarded(
                            normalized_ticker,
                            document_id,
                        )
                    )
                except (FileNotFoundError, ValueError) as exc:
                    Log.warn(
                        (
                            "跳过损坏的 rejected filing artifact: "
                            f"ticker={normalized_ticker} document_id={document_id} error={exc}"
                        ),
                        module=self.MODULE,
                    )
                    continue
            return result
        finally:
            self._release_lock_token(guard_token)

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """从 published tree 读取 rejected filing 文件内容。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            filename: 文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: ticker、document ID 或文件名非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._read_rejected_filing_file_bytes_unguarded(
                normalized_ticker,
                normalized_document_id,
                filename,
            )
        finally:
            self._release_lock_token(guard_token)

    def _read_rejected_filing_file_bytes_unguarded(
        self,
        normalized_ticker: str,
        normalized_document_id: str,
        filename: str,
    ) -> bytes:
        """在 caller 已持 publication guard 时读取 rejected filing 文件内容。

        Args:
            normalized_ticker: 已规范化 ticker。
            normalized_document_id: 已规范化文档 ID。
            filename: 待校验并读取的文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: 文件名非法或路径越界时抛出。
            OSError: 路径解析或文件读取失败时抛出。
        """

        path = self._rejected_filing_file_path_for_read(
            normalized_ticker,
            normalized_document_id,
            filename,
        )
        if not path.exists():
            raise FileNotFoundError(f"rejected filing 文件不存在: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"目标是目录，无法按文件读取: {path}")
        return path.read_bytes()

    # ========== filing 目录清理 ==========

    def clear_filing_documents(self, ticker: str, *, batch: BatchToken) -> None:
        """清空某个 ticker 下的 filings 目录内容。

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
        self._clear_filing_documents_impl(ticker, state)

    def _clear_filing_documents_impl(self, ticker: str, state: _ActiveBatchState) -> None:
        """执行 filings 目录清理（内部实现）。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        filings_dir = self._ticker_dir_for_write(normalized_ticker, state) / "filings"
        if not filings_dir.exists():
            return
        for child in filings_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                continue
            child.unlink(missing_ok=True)

    def cleanup_stale_filing_documents(
        self,
        ticker: str,
        *,
        batch: BatchToken,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """清理窗口内已过期的 filing 文档与 manifest 条目。

        Args:
            ticker: 股票代码。
            batch: 显式 transaction capability；必须属于同一 core、ticker 且仍为 open。
            active_form_types: 本轮下载窗口覆盖的 form_type 集合。
            valid_document_ids: 本轮仍应保留的 document_id 集合。

        Returns:
            实际清理的文档数量。

        Raises:
            OSError: 清理或 manifest 更新失败时抛出。
            ValueError: 元数据或 manifest 内容非法时抛出。
        """

        state = self._resolve_active_batch(batch, ticker)
        return self._cleanup_stale_filing_documents_impl(
            ticker,
            active_form_types,
            valid_document_ids,
            state,
        )

    def _cleanup_stale_filing_documents_impl(
        self,
        ticker: str,
        active_form_types: set[str],
        valid_document_ids: set[str],
        state: _ActiveBatchState,
    ) -> int:
        """执行窗口内过期 filing 清理（内部实现）。

        Args:
            ticker: 股票代码。
            active_form_types: 本轮下载窗口覆盖的 form_type 集合。
            valid_document_ids: 本轮仍应保留的 document_id 集合。
            state: 已解析的内部 transaction state。

        Returns:
            实际清理的文档数量。

        Raises:
            OSError: 清理或 manifest 更新失败时抛出。
            ValueError: 元数据或 manifest 内容非法时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_valid_document_ids = {
            _normalize_document_id(document_id) for document_id in valid_document_ids
        }
        filings_dir = self._ticker_dir_for_write(normalized_ticker, state) / "filings"
        if not filings_dir.exists() or not active_form_types:
            return 0

        stale_document_ids: list[str] = []
        for child in filings_dir.iterdir():
            if not child.is_dir() or not child.name.startswith("fil_"):
                continue
            meta_path = child / _SOURCE_META_FILENAME
            if not meta_path.exists():
                continue
            try:
                meta = _read_json_object(meta_path)
            except (ValueError, OSError):
                continue
            form_type = str(meta.get("form_type", "")).strip()
            if form_type not in active_form_types:
                continue
            if child.name in normalized_valid_document_ids:
                continue
            stale_document_ids.append(child.name)

        if not stale_document_ids:
            return 0

        stale_document_ids.sort()
        self._remove_manifest_items(
            self._filing_manifest_path(normalized_ticker, state),
            normalized_ticker,
            stale_document_ids,
        )
        for document_id in stale_document_ids:
            shutil.rmtree(filings_dir / document_id)
        return len(stale_document_ids)
