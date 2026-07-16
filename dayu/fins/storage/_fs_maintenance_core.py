"""文件系统仓储 — 拒绝注册表与清理操作 mixin。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO, Optional, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import (
    BatchToken,
    DownloadRejectionEntry,
    DownloadRejectionRegistry,
    FileObjectMeta,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind

from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_identity import (
    _IDENTITY_DESCRIPTOR_FILENAME,
    _REJECTED_FILING_IDENTITY_NAMESPACE,
    _list_external_identities,
    _read_identity_descriptor,
    _require_external_identity,
)
from ._fs_storage_utils import (
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _list_directory,
    _normalize_filename,
    _read_file_bytes,
    _read_json_object,
    _unlink_path,
    _write_json,
)


def _read_download_rejection_registry_file(path: Path) -> DownloadRejectionRegistry:
    """读取并验证单个 download rejection registry control file。

    Args:
        path: staging 或 published registry 路径。

    Returns:
        exact external document ID 到 typed rejection entry 的映射。

    Raises:
        ValueError: registry JSON、键或 typed entry 不合法时抛出。
        OSError: registry 读取失败时抛出无物理 locator 的异常。
    """

    if not path.exists():
        return {}
    data = _read_json_object(path)
    result: DownloadRejectionRegistry = {}
    for document_id, payload in data.items():
        if not isinstance(document_id, str) or not isinstance(payload, dict):
            raise ValueError("download rejection registry 条目必须是 document_id 到对象的映射")
        external_document_id = _require_external_identity(
            document_id,
            field_name="download rejection document_id",
        )
        try:
            entry = DownloadRejectionEntry.from_dict(
                cast(Mapping[str, JsonValue], payload),
                expected_document_id=external_document_id,
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("download rejection registry typed entry 不合法") from exc
        result[external_document_id] = entry
    return result


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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._load_download_rejection_registry_unguarded(external_ticker)
        finally:
            self._release_lock_token(guard_token)

    def _load_download_rejection_registry_unguarded(
        self,
        external_ticker: str,
    ) -> DownloadRejectionRegistry:
        """在 caller 已持 publication guard 时读取拒绝注册表。

        Args:
            external_ticker: exact external ticker。

        Returns:
            下载拒绝注册表。

        Raises:
            OSError: 文件读取失败时抛出。
            ValueError: registry 内容非法时抛出。
        """

        path = self._download_rejections_path_for_read(external_ticker)
        return _read_download_rejection_registry_file(path)

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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        path = self._download_rejections_path(external_ticker, state)
        payload: dict[str, dict[str, str]] = {}
        for document_id, entry in registry.items():
            external_document_id = _require_external_identity(
                document_id,
                field_name="download rejection document_id",
            )
            entry_document_id = _require_external_identity(
                entry.document_id,
                field_name="download rejection entry document_id",
            )
            if external_document_id != entry_document_id:
                raise ValueError("download rejection registry key 与条目 document_id 不一致")
            entry_payload = entry.to_dict()
            entry_payload["document_id"] = external_document_id
            payload[external_document_id] = entry_payload
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
            ValueError: ticker、document ID、descriptor 或既有 meta 不合法时抛出。
            OSError: 写入失败时抛出。
            ValueError: 文件名为空时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        state = self._resolve_active_batch(batch, external_ticker)
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_filename = _normalize_filename(filename)
        rejected_dir = self._rejected_filing_dir(
            external_ticker,
            external_document_id,
            state,
        )
        file_store = self._build_file_store(external_ticker, state)
        return file_store.put_object(
            f"{state.staging_ticker_dir.name}/filings/{_REJECTED_FILINGS_DIRNAME}/"
            f"{rejected_dir.name}/{normalized_filename}",
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

        external_ticker = _require_external_identity(req.ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            req.document_id,
            field_name="document_id",
        )
        meta_path = self._rejected_filing_meta_path(
            external_ticker,
            external_document_id,
            state,
        )
        now = now_iso8601()
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}
        if previous_meta:
            previous_artifact = RejectedFilingArtifact.from_meta_dict(previous_meta)
            if (
                previous_artifact.ticker != external_ticker
                or previous_artifact.document_id != external_document_id
            ):
                raise ValueError("rejected filing meta 与 identity descriptor 不一致")
        artifact = RejectedFilingArtifact(
            ticker=external_ticker,
            document_id=external_document_id,
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_rejected_filing_artifact_unguarded(
                external_ticker,
                external_document_id,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_rejected_filing_artifact_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
    ) -> RejectedFilingArtifact:
        """在 caller 已持 publication guard 时读取 rejected artifact。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。

        Returns:
            rejected filing artifact。

        Raises:
            FileNotFoundError: meta 不存在时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta = _read_json_object(
            self._rejected_filing_meta_path_for_read(
                external_ticker,
                external_document_id,
            )
        )
        artifact = RejectedFilingArtifact.from_meta_dict(meta)
        if (
            artifact.ticker != external_ticker
            or artifact.document_id != external_document_id
        ):
            raise ValueError("rejected filing meta 与 identity descriptor 不一致")
        return artifact

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
            ValueError: descriptor 或 artifact meta 不一致时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取目录失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            result: list[RejectedFilingArtifact] = []
            for document_id in _list_external_identities(
                self._rejected_filings_root_for_read(external_ticker),
                _REJECTED_FILING_IDENTITY_NAMESPACE,
            ):
                result.append(
                    self._get_rejected_filing_artifact_unguarded(
                        external_ticker,
                        document_id,
                    )
                )
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._read_rejected_filing_file_bytes_unguarded(
                external_ticker,
                external_document_id,
                filename,
            )
        finally:
            self._release_lock_token(guard_token)

    def _read_rejected_filing_file_bytes_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        filename: str,
    ) -> bytes:
        """在 caller 已持 publication guard 时读取 rejected filing 文件内容。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。
            filename: 待校验并读取的文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: 文件名非法或路径越界时抛出。
            OSError: 路径解析或文件读取失败时抛出。
        """

        normalized_filename = _normalize_filename(filename)
        path = self._rejected_filing_file_path_for_read(
            external_ticker,
            external_document_id,
            normalized_filename,
        )
        if not path.exists():
            raise FileNotFoundError(
                "rejected filing 文件不存在: "
                f"ticker={external_ticker} document_id={external_document_id} "
                f"filename={normalized_filename}"
            )
        if path.is_dir():
            raise IsADirectoryError(
                "目标是目录，无法按文件读取: "
                f"ticker={external_ticker} document_id={external_document_id} "
                f"filename={normalized_filename}"
            )
        return _read_file_bytes(path, action="读取 rejected filing 文件")

    # ========== filing 目录清理 ==========

    def _preflight_rejected_filing_tree(
        self,
        external_ticker: str,
        state: _ActiveBatchState,
    ) -> None:
        """在 destructive filing cleanup 前验证完整 rejected-artifact 子树。

        Args:
            external_ticker: exact external ticker。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            ValueError: container、identity、meta 或业务文件集不一致时抛出。
            OSError: 枚举或读取失败时抛出无物理 locator 的异常。
        """

        rejected_root = self._rejected_filings_root(external_ticker, state)
        if not rejected_root.exists():
            return
        if rejected_root.is_symlink() or not rejected_root.is_dir():
            raise ValueError("rejected filings control entry 必须为 non-symlink directory")
        for artifact_dir in _list_directory(
            rejected_root,
            action="枚举 rejected filing artifacts",
        ):
            if artifact_dir.is_symlink() or not artifact_dir.is_dir():
                raise ValueError("rejected filings container 存在非法条目")
            external_document_id = _read_identity_descriptor(
                artifact_dir,
                _REJECTED_FILING_IDENTITY_NAMESPACE,
            )
            meta_path = artifact_dir / _SOURCE_META_FILENAME
            if meta_path.is_symlink() or not meta_path.is_file():
                raise ValueError("rejected filing meta 必须为 non-symlink regular file")
            try:
                artifact = RejectedFilingArtifact.from_meta_dict(
                    _read_json_object(meta_path)
                )
            except (KeyError, TypeError) as exc:
                raise ValueError("rejected filing meta 字段不合法") from exc
            if (
                artifact.ticker != external_ticker
                or artifact.document_id != external_document_id
            ):
                raise ValueError("rejected filing meta 与 identity descriptor 不一致")

            expected_files: set[str] = set()
            for file_entry in artifact.files:
                normalized_name = _normalize_filename(file_entry.name)
                if normalized_name != file_entry.name or normalized_name in expected_files:
                    raise ValueError("rejected filing meta.files 文件名不合法")
                expected_files.add(normalized_name)
            physical_files: set[str] = set()
            for child in _list_directory(
                artifact_dir,
                action="枚举 rejected filing artifact 文件",
            ):
                if child.name in {
                    _IDENTITY_DESCRIPTOR_FILENAME,
                    _SOURCE_META_FILENAME,
                }:
                    continue
                if child.is_symlink() or not child.is_file():
                    raise ValueError("rejected filing artifact 存在非法文件条目")
                normalized_name = _normalize_filename(child.name)
                if normalized_name != child.name:
                    raise ValueError("rejected filing artifact 物理文件名不合法")
                physical_files.add(normalized_name)
            if physical_files != expected_files:
                raise ValueError("rejected filing meta.files 与物理文件不双向一致")

    def _preflight_filing_cleanup(
        self,
        external_ticker: str,
        state: _ActiveBatchState,
    ) -> dict[str, dict[str, JsonValue]]:
        """在任何 filing cleanup mutation 前验证整棵 staging filing tree。

        Args:
            external_ticker: exact external ticker。
            state: 已解析的内部 transaction state。

        Returns:
            以 exact external document ID 为键的 complete filing meta。

        Raises:
            ValueError: source、manifest、registry 或 rejected subtree 不合法时抛出。
            OSError: 枚举或读取失败时抛出无物理 locator 的异常。
        """

        validated_meta = self._validate_complete_source_kind_tree(
            state,
            SourceKind.FILING,
        )
        _read_download_rejection_registry_file(
            self._download_rejections_path(external_ticker, state)
        )
        self._preflight_rejected_filing_tree(external_ticker, state)
        return validated_meta

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
            ValueError: ticker、capability 或 descriptor 不合法时抛出。
            OSError: 清理失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        filings_dir = self._ticker_dir_for_write(external_ticker, state) / "filings"
        if not filings_dir.exists():
            return
        self._preflight_filing_cleanup(external_ticker, state)
        cleanup_entries = _list_directory(
            filings_dir,
            action="枚举 filing cleanup entries",
        )
        for child in cleanup_entries:
            if child.is_dir():
                self._remove_directory(child)
                continue
            _unlink_path(
                child,
                missing_ok=True,
                action="删除 filing cleanup control file",
            )

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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_valid_document_ids = {
            _require_external_identity(document_id, field_name="document_id")
            for document_id in valid_document_ids
        }
        filings_dir = self._ticker_dir_for_write(external_ticker, state) / "filings"
        if not filings_dir.exists() or not active_form_types:
            return 0

        validated_meta = self._preflight_filing_cleanup(external_ticker, state)
        stale_document_ids: list[str] = []
        for external_document_id, meta in validated_meta.items():
            if not external_document_id.startswith("fil_"):
                continue
            form_type = str(meta.get("form_type", "")).strip()
            if form_type not in active_form_types:
                continue
            if external_document_id in external_valid_document_ids:
                continue
            stale_document_ids.append(external_document_id)

        if not stale_document_ids:
            return 0

        stale_document_ids.sort()
        self._remove_manifest_items(
            self._filing_manifest_path(external_ticker, state),
            external_ticker,
            stale_document_ids,
        )
        for document_id in stale_document_ids:
            document_dir = self._source_meta_path(
                external_ticker,
                document_id,
                SourceKind.FILING,
                state,
            ).parent
            self._remove_directory(document_dir)
        return len(stale_document_ids)
