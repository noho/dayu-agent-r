"""文件系统仓储 — 拒绝注册表与清理操作 mixin。"""

from __future__ import annotations

import shutil
from typing import BinaryIO, Optional

from dayu.fins._log import Log

from dayu.fins.domain.document_models import (
    FileObjectMeta,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
    now_iso8601,
)

from ._fs_storage_infra import _FsStorageInfra
from ._fs_storage_utils import (
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _list_directory_names,
    _normalize_ticker,
    _read_json_object,
    _write_json,
)


class _FsMaintenanceMixin(_FsStorageInfra):
    """拒绝注册表与清理操作 mixin。"""

    # ========== 下载拒绝注册表 ==========

    def load_download_rejection_registry(self, ticker: str) -> dict[str, dict[str, str]]:
        """读取下载拒绝注册表。

        Args:
            ticker: 股票代码。

        Returns:
            `document_id -> rejection payload` 映射；不存在或内容非法时返回空字典。

        Raises:
            OSError: 底层读取失败时抛出。
        """

        path = self._download_rejections_path_for_read(_normalize_ticker(ticker))
        if not path.exists():
            return {}
        try:
            data = _read_json_object(path)
        except (ValueError, OSError):
            return {}
        result: dict[str, dict[str, str]] = {}
        for document_id, payload in data.items():
            if not isinstance(document_id, str) or not isinstance(payload, dict):
                continue
            normalized_payload: dict[str, str] = {}
            for key, value in payload.items():
                if not isinstance(key, str):
                    continue
                normalized_payload[key] = str(value)
            result[document_id] = normalized_payload
        return result

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: dict[str, dict[str, str]],
    ) -> None:
        """保存下载拒绝注册表。

        Args:
            ticker: 股票代码。
            registry: `document_id -> rejection payload` 映射。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._save_download_rejection_registry_impl,
            ticker,
            registry,
        )

    def _save_download_rejection_registry_impl(
        self,
        ticker: str,
        registry: dict[str, dict[str, str]],
    ) -> None:
        """执行下载拒绝注册表持久化（内部实现）。

        Args:
            ticker: 股票代码。
            registry: `document_id -> rejection payload` 映射。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        path = self._download_rejections_path(normalized_ticker)
        _write_json(path, registry)

    # ========== rejected filing artifact ==========

    def store_rejected_filing_file(
        self,
        ticker: str,
        document_id: str,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """写入 rejected filing 的文件对象。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。
            filename: 文件名。
            data: 文件字节流。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            文件对象元数据。

        Raises:
            OSError: 写入失败时抛出。
            ValueError: 文件名为空时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_filename = str(filename).strip()
        if not normalized_filename:
            raise ValueError("filename 不能为空")
        file_store = self._build_file_store(normalized_ticker)
        return file_store.put_object(
            f"{normalized_ticker}/filings/{_REJECTED_FILINGS_DIRNAME}/{document_id}/{normalized_filename}",
            data,
            content_type=content_type,
            metadata=metadata,
        )

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
    ) -> RejectedFilingArtifact:
        """写入或更新 rejected filing artifact。

        Args:
            req: artifact 写入请求。

        Returns:
            写回后的 artifact。

        Raises:
            OSError: 写入失败时抛出。
        """

        return self._execute_with_auto_batch(
            req.ticker,
            self._upsert_rejected_filing_artifact_impl,
            req,
        )

    def _upsert_rejected_filing_artifact_impl(
        self,
        req: RejectedFilingArtifactUpsertRequest,
    ) -> RejectedFilingArtifact:
        """执行 rejected filing artifact 写入。

        Args:
            req: artifact 写入请求。

        Returns:
            写回后的 artifact。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(req.ticker)
        meta_path = self._rejected_filing_meta_path(normalized_ticker, req.document_id)
        now = now_iso8601()
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}
        artifact = RejectedFilingArtifact(
            ticker=normalized_ticker,
            document_id=req.document_id,
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
        """读取 rejected filing artifact。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            artifact 对象。

        Raises:
            FileNotFoundError: meta 不存在时抛出。
            ValueError: meta 内容非法时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        meta = _read_json_object(self._rejected_filing_meta_path_for_read(normalized_ticker, document_id))
        return RejectedFilingArtifact.from_meta_dict(meta)

    def list_rejected_filing_artifacts(
        self,
        ticker: str,
    ) -> list[RejectedFilingArtifact]:
        """列出某个 ticker 下的 rejected filing artifacts。

        Args:
            ticker: 股票代码。

        Returns:
            artifact 列表，按 document_id 升序。

        Raises:
            OSError: 读取目录失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        result: list[RejectedFilingArtifact] = []
        for document_id in _list_directory_names(self._rejected_filings_root_for_read(normalized_ticker)):
            try:
                result.append(self.get_rejected_filing_artifact(normalized_ticker, document_id))
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

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """读取 rejected filing 的文件内容。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            filename: 文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            OSError: 读取失败时抛出。
        """

        path = self._rejected_filing_file_path_for_read(_normalize_ticker(ticker), document_id, filename)
        if not path.exists():
            raise FileNotFoundError(f"rejected filing 文件不存在: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"目标是目录，无法按文件读取: {path}")
        return path.read_bytes()

    # ========== filing 目录清理 ==========

    def clear_filing_documents(self, ticker: str) -> None:
        """清空某个 ticker 下的 filings 目录内容。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._clear_filing_documents_impl,
            ticker,
        )

    def _clear_filing_documents_impl(self, ticker: str) -> None:
        """执行 filings 目录清理（内部实现）。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        filings_dir = self._ticker_dir_for_write(normalized_ticker) / "filings"
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
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """清理窗口内已过期的 filing 文档与 manifest 条目。

        Args:
            ticker: 股票代码。
            active_form_types: 本轮下载窗口覆盖的 form_type 集合。
            valid_document_ids: 本轮仍应保留的 document_id 集合。

        Returns:
            实际清理的文档数量。

        Raises:
            OSError: 清理或 manifest 更新失败时抛出。
            ValueError: 元数据或 manifest 内容非法时抛出。
        """

        return self._execute_with_auto_batch(
            ticker,
            self._cleanup_stale_filing_documents_impl,
            ticker,
            active_form_types,
            valid_document_ids,
        )

    def _cleanup_stale_filing_documents_impl(
        self,
        ticker: str,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """执行窗口内过期 filing 清理（内部实现）。

        Args:
            ticker: 股票代码。
            active_form_types: 本轮下载窗口覆盖的 form_type 集合。
            valid_document_ids: 本轮仍应保留的 document_id 集合。

        Returns:
            实际清理的文档数量。

        Raises:
            OSError: 清理或 manifest 更新失败时抛出。
            ValueError: 元数据或 manifest 内容非法时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        filings_dir = self._ticker_dir_for_write(normalized_ticker) / "filings"
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
            if child.name in valid_document_ids:
                continue
            stale_document_ids.append(child.name)

        if not stale_document_ids:
            return 0

        stale_document_ids.sort()
        self._remove_manifest_items(
            self._filing_manifest_path(normalized_ticker),
            normalized_ticker,
            stale_document_ids,
        )
        for document_id in stale_document_ids:
            shutil.rmtree(filings_dir / document_id)
        return len(stale_document_ids)
