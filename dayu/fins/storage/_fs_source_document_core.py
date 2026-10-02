"""文件系统仓储 — 源文档操作 mixin。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Optional

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
    SourceDocumentUpsertRequest,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.xbrl_file_discovery import has_xbrl_instance

from .local_file_source import LocalFileSource
from .source_manifest_contract import project_filing_manifest_item, project_material_manifest_item
from .source_meta_contract import require_material_source_meta_primary_document, require_source_meta_is_deleted
from ._fs_source_integrity import (
    validate_material_source_primary,
    _SOURCE_REVISION_META_FIELD,
    _SourceKindPublicationInspection,
    _inspect_source_kind_unguarded,
    _source_meta_without_revision,
)
from ._fs_source_snapshot import _read_source_snapshot
from ._fs_storage_infra import (
    _ActiveBatchState,
    _FsStorageInfra,
)
from ._fs_identity import (
    _FILING_IDENTITY_NAMESPACE,
    _MATERIAL_IDENTITY_NAMESPACE,
    _PROCESSED_IDENTITY_NAMESPACE,
    _identity_directory_for_read,
    _list_external_identities,
    _require_external_identity,
)
from ._fs_storage_utils import (
    _build_file_payloads,
    _extract_file_payloads,
    _file_object_meta_from_dict,
    _guess_media_type,
    _infer_filename_from_uri,
    _local_path_from_uri,
    _normalize_file_entries,
    _normalize_filename,
    _normalize_source_kind,
    _project_filesystem_error,
    _raise_path_free_error,
    _read_json_object,
    _resolve_primary_uri,
    _source_dir_name,
    _unlink_path,
    _write_json,
)
from .repository_protocols import SourceSnapshotProtocol
from .source_meta_read import SourceMetaIntegrityReadEntry, SourceMetaReadEntry, SourceMetaReadView
from .source_integrity import (
    SourceIntegrityClassification,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
    SourceIntegrityRepairRequiredError,
    SourceIntegrityRepairBlockedError,
    SourceIntegrityRepairBlockedReason,
    SourceIntegrityRevisionConflictError,
    SourceIntegrityStatus,
    has_same_source_publication_identity,
)


def _canonical_remaining_manifest_items_for_repair(
    inspection: _SourceKindPublicationInspection,
    *,
    target_document_id: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    """从同一次 staged inspection 收集 non-target canonical manifest items。

    Args:
        inspection: exact-target 模式产生的完整 source-kind inspection。
        target_document_id: 本次将被完整重建的 exact target document ID。

    Returns:
        按 canonical document ID 稳定排序的 non-target manifest items。

    Raises:
        SourceIntegrityRepairBlockedError: inspection owner 已判定其它 source 或
            canonical manifest 阻断 repair 时抛出。
        RuntimeError: inspection owner 声称无阻断但 canonical item shape 或唯一性
            不满足 producer invariant 时抛出。
    """

    if inspection.repair_blocked_reason is not None:
        raise SourceIntegrityRepairBlockedError(
            inspection.repair_blocked_reason
        )

    items_by_document_id: dict[str, Mapping[str, JsonValue]] = {}
    for source_inspection in inspection.inventory:
        document_id = source_inspection.classification.document_id
        if document_id == target_document_id:
            continue
        canonical_item = source_inspection.canonical_manifest_item
        if canonical_item is None or canonical_item.get("document_id") != document_id:
            raise RuntimeError(
                "source integrity inspector clean payload 的 canonical item shape 违约"
            )
        if document_id in items_by_document_id:
            raise RuntimeError(
                "source integrity inspector clean payload 的 document identity 唯一性违约"
            )
        items_by_document_id[document_id] = canonical_item
    return tuple(
        items_by_document_id[document_id]
        for document_id in sorted(items_by_document_id)
    )


class _FsSourceDocumentMixin(_FsStorageInfra):
    """源文档（filing / material）操作 mixin。"""

    # ========== material CRUD ==========

    def update_material_amended(self, *, batch: BatchToken, document_id: str, amended: bool) -> None:
        """只修改当前材料修订标记及仓储维护事实。

        Args:
            batch: 已登记材料条件的 writer capability。
            document_id: 与登记目标一致的文档 ID。
            amended: 显式真实 bool。

        Returns:
            无，仍属于 staged mutation。

        Raises:
            ValueError: capability、标记或目标非法。
            SourceIntegrityRevisionConflictError: stage 前事实漂移。
            OSError: 严格读写失败。
        """
        if type(amended) is not bool:
            raise ValueError("材料 amended 必须 bool")
        state = self._resolve_active_batch(batch, batch.ticker)
        if state.material_preconditions is None or state.material_preconditions[0].source_integrity.document_id != document_id:
            raise ValueError("材料 metadata mutation 必须已登记同目标条件")
        expected, company = state.material_preconditions
        fresh = self._read_material_state_unguarded(batch.ticker, document_id, state.staging_ticker_dir)
        self._require_material_state_matches(fresh, expected, company)
        if fresh.source_integrity.status is not SourceIntegrityStatus.COMPLETE or fresh.source_meta is None or require_source_meta_is_deleted(fresh.source_meta):
            raise ValueError("材料 metadata mutation 只允许健康 active")
        # writer 稳定视图中读取同一已校验元数据，保留可序列化 canonical JSON；不从投影重算业务字段。
        meta = _read_json_object(self._source_meta_path(batch.ticker, document_id, SourceKind.MATERIAL, state))
        meta["amended"] = amended
        meta["updated_at"] = now_iso8601()
        self.replace_source_meta(batch.ticker, document_id, SourceKind.MATERIAL, meta, batch=batch)


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

    def reset_source_document_for_repair(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        expected_integrity: SourceIntegrityClassification,
        *,
        batch: BatchToken,
    ) -> None:
        """按 Phase A integrity 对真实 staging target 执行受约束修复重置。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 来源类型。
            expected_integrity: validator 携带的 Phase A repair-required classification。
            batch: 同一 storage core、ticker 且仍 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、identity、source kind 或 expected classification 非法时抛出。
            SourceIntegrityRevisionConflictError: staged target 的 presence、revision 或 repair status
                与 expected classification 不再匹配时抛出。
            SourceIntegrityRepairBlockedError: target 仍匹配但其它 source 或 canonical manifest
                阻断安全 repair 时抛出。
            OSError: staging 文件系统操作失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        if normalized_source_kind is not SourceKind.FILING:
            raise ValueError("existing source auto repair 只允许 filing")
        if not isinstance(expected_integrity, SourceIntegrityClassification):
            raise ValueError("expected_integrity 必须是 SourceIntegrityClassification")
        if (
            expected_integrity.ticker != external_ticker
            or expected_integrity.document_id != external_document_id
            or expected_integrity.source_kind is not normalized_source_kind
            or expected_integrity.status is not SourceIntegrityStatus.REPAIR_REQUIRED
            or expected_integrity.revision is None
        ):
            raise ValueError("expected_integrity 必须精确引用 REPAIR_REQUIRED filing target")

        state = self._resolve_active_batch(batch, external_ticker)
        ticker_dir = state.staging_ticker_dir
        inspection = _inspect_source_kind_unguarded(
            ticker=external_ticker,
            source_kind=normalized_source_kind,
            ticker_dir=ticker_dir,
            source_root=ticker_dir / _source_dir_name(normalized_source_kind),
            requested_document_id=external_document_id,
        )
        target = inspection.target
        if target is None:
            raise SourceIntegrityRevisionConflictError()
        staged_integrity = target.classification
        if (
            staged_integrity.status is SourceIntegrityStatus.UNSAFE
            or staged_integrity.status is not SourceIntegrityStatus.REPAIR_REQUIRED
            or target.content_classification.status
            not in {SourceIntegrityStatus.COMPLETE, SourceIntegrityStatus.REPAIR_REQUIRED}
        ):
            raise SourceIntegrityRevisionConflictError()
        try:
            identity_matches = has_same_source_publication_identity(
                expected_integrity,
                staged_integrity,
            )
        except ValueError as exc:
            raise SourceIntegrityRevisionConflictError() from exc
        if not identity_matches:
            raise SourceIntegrityRevisionConflictError()

        try:
            material_inspection = _inspect_source_kind_unguarded(
                ticker=external_ticker,
                source_kind=SourceKind.MATERIAL,
                ticker_dir=ticker_dir,
                source_root=ticker_dir / _source_dir_name(SourceKind.MATERIAL),
                requested_document_id=None,
            )
        except SourceIntegrityPreflightError as exc:
            raise SourceIntegrityRepairBlockedError(
                SourceIntegrityRepairBlockedReason.CROSS_SOURCE_PUBLICATION_UNSAFE
            ) from exc

        remaining_items = _canonical_remaining_manifest_items_for_repair(
            inspection,
            target_document_id=external_document_id,
        )
        if material_inspection.repair_blocked_reason is not None:
            raise SourceIntegrityRepairBlockedError(
                material_inspection.repair_blocked_reason
            )
        self._reset_source_document_directory_for_repair(
            external_ticker,
            external_document_id,
            normalized_source_kind,
            state,
        )
        self._rewrite_source_manifest_for_repair(
            external_ticker,
            normalized_source_kind,
            remaining_items,
            state,
        )

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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_document_meta_unguarded(
                external_ticker,
                external_document_id,
            )
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
                meta = _read_json_object(meta_path)
                if meta.get("document_id") != normalized_document_id:
                    raise ValueError("document meta 与 identity descriptor 不一致")
                meta_ticker = meta.get("ticker")
                if meta_ticker is not None and meta_ticker != normalized_ticker:
                    raise ValueError("document meta ticker 与 identity descriptor 不一致")
                return meta
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
            CompanyTickerIdentityCorruptionError: published ticker 身份损坏时原样抛出。
            ValueError: 元数据文件内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_source_meta_unguarded(
                external_ticker,
                external_document_id,
                normalized_source_kind,
            )
        finally:
            self._release_lock_token(guard_token)

    def read_source_meta_integrity_view(
        self, ticker: str, source_kind: SourceKind, *, batch: BatchToken | None,
    ) -> tuple[SourceMetaIntegrityReadEntry, ...]:
        """读取同一稳定根内的完整原始元数据和完整性分类。

        参数：ticker 为公司身份；source_kind 为来源；batch 为同 core/ticker 的
            open capability，None 时持短 publication guard。
        返回：完整有序观察，每份独立 JSON 树顶层只读，嵌套值仅供只读消费。
        异常：校验 ValueError、原读取 OSError、完整性异常及锁异常原样传播。
        """
        external_ticker = _require_external_identity(ticker, field_name="ticker")
        kind = _normalize_source_kind(source_kind)
        if batch is not None:
            state = self._resolve_active_batch(batch, external_ticker)
            return self._read_source_meta_integrity_at_root(external_ticker, kind, state.staging_ticker_dir)
        guard = self._acquire_publication_guard(external_ticker)
        try:
            return self._read_source_meta_integrity_at_root(external_ticker, kind, self._target_ticker_dir(external_ticker))
        finally:
            self._release_lock_token(guard)

    def _read_source_meta_integrity_at_root(
        self, ticker: str, kind: SourceKind, ticker_dir: Path,
    ) -> tuple[SourceMetaIntegrityReadEntry, ...]:
        """在调用方已稳定的根内严格读取全部来源事实。

        参数：ticker 为公司外部身份；kind 为来源类型；ticker_dir 为已持锁的发布根或 staging 根。
        返回：有序完整同窗观察，每份原始 JSON 与该根完整性分类绑定。
        异常：原始 JSON、身份、I/O 和完整性检查异常原样传播，不返回成功前缀。"""
        ids = self._list_source_ids_at_root(ticker_dir, kind)
        # 所有 raw 解析先于 inspector，保全 JSON 错误原对象，不能降级为无年度证据。
        metas = tuple(self._get_source_meta_at_root(ticker, doc, kind, ticker_dir) for doc in ids)
        inspection = _inspect_source_kind_unguarded(
            ticker=ticker, source_kind=kind, ticker_dir=ticker_dir,
            source_root=ticker_dir / _source_dir_name(kind), requested_document_id=None,
        )
        classifications = {item.classification.document_id: item.classification for item in inspection.inventory}
        return tuple(
            SourceMetaIntegrityReadEntry(doc, MappingProxyType(meta), classifications[doc])
            for doc, meta in zip(ids, metas, strict=True)
        )

    def _list_source_ids_at_root(self, ticker_dir: Path, kind: SourceKind) -> list[str]:
        """从稳定根枚举来源外部身份。

        参数：ticker_dir 为稳定公司根；kind 为来源类型。
        返回：有序来源文档 ID 列表。
        异常：descriptor 校验 ValueError 和 I/O 异常原样传播。"""
        root = self._storage_subdirectory_for_read(ticker_dir, _source_dir_name(kind))
        namespace = _FILING_IDENTITY_NAMESPACE if kind is SourceKind.FILING else _MATERIAL_IDENTITY_NAMESPACE
        return _list_external_identities(root, namespace)

    def _get_source_meta_at_root(
        self, ticker: str, document_id: str, kind: SourceKind, ticker_dir: Path,
    ) -> dict[str, JsonValue]:
        """从显式稳定根严格读取原始业务元数据。

        参数：ticker 为公司外部身份；document_id 为文档外部身份；kind 为来源类型；
            ticker_dir 为已稳定的公司根。
        返回：本次独立解析的原始业务 JSON 字典。
        异常：JSON/身份校验 ValueError 与 I/O 异常原样传播。"""
        root = self._storage_subdirectory_for_read(ticker_dir, _source_dir_name(kind))
        namespace = _FILING_IDENTITY_NAMESPACE if kind is SourceKind.FILING else _MATERIAL_IDENTITY_NAMESPACE
        meta = _read_json_object(_identity_directory_for_read(root, namespace, document_id) / "meta.json")
        if meta.get("ticker") != ticker or meta.get("document_id") != document_id or meta.get("source_kind") != kind.value:
            raise ValueError("source meta 与 identity descriptor/source kind 不一致")
        return _source_meta_without_revision(meta)

    def read_source_meta_view(
        self, ticker: str, source_kind: SourceKind,
    ) -> SourceMetaReadView:
        """在同一个 publication guard 内按原 list/get 规则读取源元数据。

        Args:
            ticker: exact external ticker。
            source_kind: 必填的 filing 或 material 来源类型。

        Returns:
            完整有序枚举的成功元数据前缀及首个原 ValueError/OSError 对象；
            read_error 为 None 才表示全部读取完成。每份元数据来自本次独立
            JSON 解析，顶层只读；嵌套 JSON 由消费者只读使用，独立于其他
            公开读取与后续发布，不代表完整性或写授权。

        Raises:
            CompanyTickerIdentityCorruptionError: published ticker 身份损坏时在枚举阶段抛出。
            ValueError: 输入或完整枚举不合法时抛出。
            OSError: 完整枚举的 I/O 失败时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            Exception: 非 ValueError/OSError 的元数据读取异常原样传播。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            # 完整枚举先于所有 get；不得将 list 失败变为元数据前缀。
            document_ids = self._list_document_ids_unguarded(external_ticker, normalized_source_kind)
            entries: list[SourceMetaReadEntry] = []
            read_error: ValueError | OSError | None = None
            for document_id in document_ids:
                try:
                    meta = self._get_source_meta_unguarded(
                        external_ticker, document_id, normalized_source_kind,
                    )
                except (ValueError, OSError) as error:
                    read_error = error
                    break
                # getter 每次解析独立 JSON 树并生成业务字典，无其他公开持有者；
                # 直接包装可保全独立观察，避免递归复制新增合法 JSON 的拒绝。
                entries.append(SourceMetaReadEntry(document_id, MappingProxyType(meta)))
            return SourceMetaReadView(
                external_ticker, normalized_source_kind, tuple(entries), read_error,
            )
        finally:
            self._release_lock_token(guard_token)

    def classify_source_integrity(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> SourceIntegrityClassification:
        """在短 publication guard 内分类 published source 完整性。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material。

        Returns:
            不泄漏路径、raw meta 或 bytes 的 typed classification。

        Raises:
            ValueError: identity、meta、文件声明或摘要结构非法时抛出。
            RuntimeError: publication guard 获取或释放失败时抛出。
            OSError: published 文件系统读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            ticker_dir = self._target_ticker_dir(external_ticker)
            inspection = _inspect_source_kind_unguarded(
                ticker=external_ticker,
                source_kind=normalized_source_kind,
                ticker_dir=ticker_dir,
                source_root=ticker_dir / _source_dir_name(normalized_source_kind),
                requested_document_id=external_document_id,
            )
            if inspection.target is None:
                raise RuntimeError("exact-target inspection 缺少 target")
            return inspection.target.classification
        finally:
            self._release_lock_token(guard_token)

    def classify_staged_source_integrity(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> SourceIntegrityClassification:
        """分类真实 open batch staging 内的 source 完整性。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material。
            batch: 同一 core、ticker 且仍 open 的真实 batch capability。

        Returns:
            staging source 的 typed classification。

        Raises:
            ValueError: capability、identity、meta、文件声明或摘要结构非法时抛出。
            OSError: staging 文件系统读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        state = self._resolve_active_batch(batch, external_ticker)
        ticker_dir = state.staging_ticker_dir
        inspection = _inspect_source_kind_unguarded(
            ticker=external_ticker,
            source_kind=normalized_source_kind,
            ticker_dir=ticker_dir,
            source_root=ticker_dir / _source_dir_name(normalized_source_kind),
            requested_document_id=external_document_id,
        )
        if inspection.target is None:
            raise RuntimeError("exact-target inspection 缺少 target")
        return inspection.target.classification

    def list_source_integrity(
        self,
        ticker: str,
    ) -> tuple[SourceIntegrityClassification, ...]:
        """在单一短 publication guard 内返回完整 ticker source inventory。

        Args:
            ticker: exact external ticker。

        Returns:
            按 source kind 与 document ID 排序的 filing+material classification。

        Raises:
            ValueError: identity、manifest、meta 或文件声明结构非法时抛出。
            RuntimeError: publication guard 获取或释放失败时抛出。
            OSError: published 文件系统读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            inventory: list[SourceIntegrityClassification] = []
            ticker_dir = self._target_ticker_dir(external_ticker)
            for source_kind in (SourceKind.FILING, SourceKind.MATERIAL):
                inspection = _inspect_source_kind_unguarded(
                    ticker=external_ticker,
                    source_kind=source_kind,
                    ticker_dir=ticker_dir,
                    source_root=ticker_dir / _source_dir_name(source_kind),
                    requested_document_id=None,
                )
                inventory.extend(
                    item.classification
                    for item in inspection.inventory
                )
            return tuple(inventory)
        finally:
            self._release_lock_token(guard_token)

    def _classify_source_integrity_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        source_kind: SourceKind,
        *,
        ticker_dir: Path,
    ) -> SourceIntegrityClassification:
        """在 caller 已持稳定视图时机械投影 exact-target inspection。

        该窄 seam 保留给同一 storage core 的 caller-held guard 组合读取；实际
        classification、manifest 与 filesystem 语义只由统一 inspector 产生。

        Args:
            external_ticker: 已校验的 exact external ticker。
            external_document_id: 已校验的 exact external document ID。
            source_kind: 已规范化 source kind。
            ticker_dir: caller 稳定视图中的 published ticker 根。

        Returns:
            统一 inspector exact target 的 typed classification。

        Raises:
            RuntimeError: inspector 违反 exact-target payload 不变量时抛出。
            OSError: 文件系统 operational I/O 失败时抛出。
        """

        inspection = _inspect_source_kind_unguarded(
            ticker=external_ticker,
            source_kind=source_kind,
            ticker_dir=ticker_dir,
            source_root=ticker_dir / _source_dir_name(source_kind),
            requested_document_id=external_document_id,
        )
        if inspection.target is None:
            raise RuntimeError("exact-target inspection 缺少 target")
        return inspection.target.classification

    def get_source_document_locator(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> PurePosixPath:
        """返回 published source 文档目录相对 workspace 的 typed locator。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            只用于定位、不承载业务身份的相对 POSIX path。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            ValueError: identity、source kind、meta 或相对关系非法时抛出。
            RuntimeError: publication guard 获取或释放失败时抛出。
            OSError: published tree 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            self._get_persisted_source_meta_unguarded(
                external_ticker,
                external_document_id,
                normalized_source_kind,
            )
            document_dir = self._source_meta_path_for_read(
                external_ticker,
                external_document_id,
                normalized_source_kind,
            ).parent
            relative = document_dir.relative_to(self.workspace_root)
            return PurePosixPath(*relative.parts)
        finally:
            self._release_lock_token(guard_token)

    def _get_source_meta_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        normalized_source_kind: SourceKind,
    ) -> dict[str, JsonValue]:
        """在 caller 已持 publication guard 时读取 source meta。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。
            normalized_source_kind: 已规范化来源类型。

        Returns:
            source meta。

        Raises:
            FileNotFoundError: source meta 不存在时抛出；逻辑删除仍可读取原始元数据。
            CompanyTickerIdentityCorruptionError: published ticker 身份损坏时原样抛出。
            ValueError: 文档 descriptor、source root 或 meta 内容非法时抛出。
            OSError: published tree 读取失败时原样抛出。
        """

        ticker_dir = self._ticker_dir_for_read(external_ticker)
        return self._get_source_meta_at_root(
            external_ticker, external_document_id, normalized_source_kind, ticker_dir,
        )

    def _get_persisted_source_meta_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        normalized_source_kind: SourceKind,
    ) -> DocumentMeta:
        """在 caller 已持 publication guard 时读取 persisted source meta。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。
            normalized_source_kind: 已规范化来源类型。

        Returns:
            包含 storage 私有 publication 字段的 persisted source meta。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            ValueError: meta 与 identity/source kind 不一致时抛出。
            OSError: persisted meta 读取失败时抛出。
        """

        meta_path = self._source_meta_path_for_read(
            external_ticker,
            external_document_id,
            normalized_source_kind,
        )
        if not meta_path.exists():
            raise FileNotFoundError(
                f"document_id={external_document_id} 的 {normalized_source_kind.value} meta.json 不存在"
            )
        meta = _read_json_object(meta_path)
        if (
            meta.get("ticker") != external_ticker
            or meta.get("document_id") != external_document_id
            or meta.get("source_kind") != normalized_source_kind.value
        ):
            raise ValueError("source meta 与 identity descriptor/source kind 不一致")
        return meta

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

        return _read_source_snapshot(
            self,
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            source_meta = meta
            if source_meta is None:
                source_meta = self._get_source_meta_unguarded(
                    external_ticker,
                    external_document_id,
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        state = self._resolve_active_batch(batch, external_ticker)
        meta_path = self._source_meta_path(
            external_ticker,
            external_document_id,
            normalized_source_kind,
            state,
        )
        if not meta_path.exists():
            raise FileNotFoundError(f"document_id={document_id} 的 {normalized_source_kind.value} meta.json 不存在")
        normalized_meta = _prepare_complete_source_meta(
            meta,
            ticker=external_ticker,
            document_id=external_document_id,
            source_kind=normalized_source_kind,
        )
        if normalized_source_kind is SourceKind.MATERIAL:
            validate_material_source_primary(source_meta=normalized_meta, source_directory=meta_path.parent)
        _write_json(meta_path, normalized_meta)

        if normalized_source_kind == SourceKind.FILING:
            self._upsert_filing_manifest(
                state,
                [project_filing_manifest_item(normalized_meta)],
            )
        else:
            self._upsert_material_manifest(
                state,
                [project_material_manifest_item(normalized_meta)],
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._list_documents_unguarded(external_ticker, query)
        finally:
            self._release_lock_token(guard_token)

    def _list_documents_unguarded(
        self,
        external_ticker: str,
        query: DocumentQuery,
    ) -> list[DocumentSummary]:
        """在 caller 已持 publication guard 时查询 processed manifest。

        Args:
            external_ticker: exact external ticker。
            query: 查询条件。

        Returns:
            文档摘要列表。

        Raises:
            OSError: manifest 读取失败时抛出。
            ValueError: manifest 内容非法时抛出。
        """

        manifest = self._read_manifest(
            self._processed_manifest_path_for_read(external_ticker),
            external_ticker,
        )
        ticker_dir = self._ticker_dir_for_read(external_ticker)
        processed_root = self._storage_subdirectory_for_read(ticker_dir, "processed")
        descriptor_document_ids = _list_external_identities(
            processed_root,
            _PROCESSED_IDENTITY_NAMESPACE,
        )
        manifest_document_ids: list[str] = []
        result: list[DocumentSummary] = []
        for item in manifest["documents"]:
            summary = DocumentSummary.from_dict(item)
            external_document_id = _require_external_identity(
                summary.document_id,
                field_name="processed manifest document_id",
            )
            if external_document_id in manifest_document_ids:
                raise ValueError("processed manifest document_id 重复")
            meta = _read_json_object(
                self._processed_meta_path_for_read(
                    external_ticker,
                    external_document_id,
                )
            )
            if meta.get("document_id") != external_document_id:
                raise ValueError("processed meta/manifest 与 identity descriptor 不一致")
            manifest_document_ids.append(external_document_id)
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
        if sorted(manifest_document_ids) != descriptor_document_ids:
            raise ValueError("processed manifest 与 identity descriptors 不双向一致")
        return result

    def list_document_ids(self, ticker: str, source_kind: Optional[SourceKind] = None) -> list[str]:
        """从 published tree 列出文档 ID。

        Args:
            ticker: 股票代码。
            source_kind: 可选来源类型过滤。

        Returns:
            已排序文档 ID 列表。

        Raises:
            CompanyTickerIdentityCorruptionError: published ticker 身份损坏时原样抛出。
            ValueError: ticker、source kind、descriptor 或 source root 不合法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 读取目录失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        normalized_source_kind = None if source_kind is None else _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._list_document_ids_unguarded(external_ticker, normalized_source_kind)
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
            CompanyTickerIdentityCorruptionError: published ticker 身份损坏时原样抛出。
            ValueError: descriptor 或 source root 不合法时抛出。
            OSError: 读取目录失败时抛出。
        """

        ticker_dir = self._ticker_dir_for_read(normalized_ticker)
        if source_kind is not None:
            return self._list_source_ids_at_root(ticker_dir, source_kind)
        filings = self._list_source_ids_at_root(ticker_dir, SourceKind.FILING)
        materials = self._list_source_ids_at_root(ticker_dir, SourceKind.MATERIAL)
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
            ValueError: ticker、source kind、descriptor 或 root 不合法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            root = self._source_root_for_read(external_ticker, normalized_source_kind)
            if not root.exists():
                return False
            if not root.is_dir():
                raise NotADirectoryError(
                    f"source root 不是目录: ticker={external_ticker} source_kind={normalized_source_kind.value}"
                )
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
            ValueError: ticker、document identity 或 descriptor 不合法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._has_filing_xbrl_instance_unguarded(
                external_ticker,
                external_document_id,
            )
        finally:
            self._release_lock_token(guard_token)

    def _has_filing_xbrl_instance_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
    ) -> bool:
        """在 caller 已持 publication guard 时检查 filing XBRL instance。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。

        Returns:
            是否存在 XBRL instance。

        Raises:
            FileNotFoundError: filing 目录不存在时抛出。
            NotADirectoryError: filing 路径不是目录时抛出。
            ValueError: document identity 或 descriptor 不合法时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        filing_dir = _identity_directory_for_read(
            self._source_root_for_read(external_ticker, SourceKind.FILING),
            _FILING_IDENTITY_NAMESPACE,
            external_document_id,
        )
        if not filing_dir.exists():
            raise FileNotFoundError(f"filing 目录不存在: ticker={external_ticker} document_id={external_document_id}")
        if not filing_dir.is_dir():
            raise NotADirectoryError(
                f"filing 路径不是目录: ticker={external_ticker} document_id={external_document_id}"
            )
        try:
            return has_xbrl_instance(filing_dir)
        except OSError as exc:
            _raise_path_free_error(
                _project_filesystem_error(
                    exc,
                    action="检查 published filing XBRL 文件",
                )
            )

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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        state = self._resolve_active_batch(batch, external_ticker)
        filing_dir = self._source_meta_path(
            external_ticker,
            external_document_id,
            SourceKind.FILING,
            state,
        ).parent
        if not filing_dir.exists():
            raise FileNotFoundError(
                f"staging filing 目录不存在: ticker={external_ticker} document_id={external_document_id}"
            )
        if not filing_dir.is_dir():
            raise NotADirectoryError(
                f"staging filing 路径不是目录: ticker={external_ticker} document_id={external_document_id}"
            )
        try:
            return has_xbrl_instance(filing_dir)
        except OSError as exc:
            _raise_path_free_error(
                _project_filesystem_error(
                    exc,
                    action="检查 staging filing XBRL 文件",
                )
            )

    def _reset_source_document_impl(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        state: _ActiveBatchState,
    ) -> None:
        """执行单文档重置（内部实现）。

        行为与错误传播：

        - 目标目录存在且为目录：调用 storage directory owner 物理删除整个文档目录。
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        document_dir = self._source_meta_path(
            external_ticker,
            external_document_id,
            normalized_source_kind,
            state,
        ).parent
        if document_dir.exists():
            if document_dir.is_dir():
                self._remove_directory(document_dir)
            else:
                _unlink_path(
                    document_dir,
                    missing_ok=True,
                    action="删除 source document 异常条目",
                )
        if normalized_source_kind == SourceKind.FILING:
            manifest_path = self._filing_manifest_path(external_ticker, state)
        else:
            manifest_path = self._material_manifest_path(external_ticker, state)
        if manifest_path.exists():
            self._remove_manifest_item(
                manifest_path,
                external_ticker,
                external_document_id,
            )

    def _reset_source_document_directory_for_repair(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        state: _ActiveBatchState,
    ) -> None:
        """删除已由同次 inspection 证明存在的 exact staged target 目录。

        Args:
            ticker: 已校验的 exact external ticker。
            document_id: 已校验的 exact external document ID。
            source_kind: 已校验的 filing source kind。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            ValueError: identity descriptor 与 exact target 不一致时抛出。
            OSError: target 目录读取或删除失败时抛出。
        """

        source_root = self._source_root(ticker, source_kind, state)
        namespace = (
            _FILING_IDENTITY_NAMESPACE
            if source_kind is SourceKind.FILING
            else _MATERIAL_IDENTITY_NAMESPACE
        )
        document_dir = _identity_directory_for_read(
            source_root,
            namespace,
            document_id,
        )
        self._remove_directory(document_dir)

    def _rewrite_source_manifest_for_repair(
        self,
        ticker: str,
        source_kind: SourceKind,
        canonical_items: tuple[Mapping[str, JsonValue], ...],
        state: _ActiveBatchState,
    ) -> None:
        """仅用 non-target inspection 单点投影重写 staged source manifest。

        Args:
            ticker: 已校验的 exact external ticker。
            source_kind: 已校验的 filing source kind。
            canonical_items: 按 document ID 排序的 non-target canonical items。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            OSError: canonical manifest 写入失败时抛出。
        """

        manifest_path = (
            self._filing_manifest_path(ticker, state)
            if source_kind is SourceKind.FILING
            else self._material_manifest_path(ticker, state)
        )
        documents: list[JsonValue] = [dict(item) for item in canonical_items]
        payload: dict[str, JsonValue] = {
            "ticker": ticker,
            "updated_at": now_iso8601(),
            "documents": documents,
        }
        _write_json(manifest_path, payload)

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
            ValueError: ticker、document identity、source kind、descriptor 或 meta 不合法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: descriptor 或 meta 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_source_handle_unguarded(
                external_ticker,
                external_document_id,
                normalized_source_kind,
            )
        finally:
            self._release_lock_token(guard_token)

    def _get_source_handle_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        normalized_source_kind: SourceKind,
    ) -> SourceHandle:
        """在 caller 已持 publication guard 时构造 source handle。

        Args:
            external_ticker: exact external ticker。
            external_document_id: exact external document ID。
            normalized_source_kind: 已规范化来源类型。

        Returns:
            source handle。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
        """

        self._get_source_meta_unguarded(
            external_ticker,
            external_document_id,
            normalized_source_kind,
        )
        return SourceHandle(
            ticker=external_ticker,
            document_id=external_document_id,
            source_kind=normalized_source_kind.value,
        )

    def get_primary_file(self, handle: SourceHandle) -> FileObjectMeta:
        """从 published tree 获取源文档主文件元数据。

        Args:
            handle: 源文档句柄。

        Returns:
            主文件元数据。

        Raises:
            KeyError: material 元数据缺少必填 primary_document 时抛出。
            FileNotFoundError: 主文件无法定位时抛出。
            ValueError: 元数据格式非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
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
            KeyError: material 元数据缺少必填 primary_document 时抛出。
            FileNotFoundError: source 或主文件无法定位时抛出。
            ValueError: meta 内容非法时抛出。
        """

        meta = self._get_handle_meta(handle)
        files = meta.get("files", [])
        if not isinstance(files, list):
            raise ValueError("meta.files 必须为 list")
        if not files:
            raise FileNotFoundError("源文档未绑定文件，无法定位主文件")
        source_kind = _normalize_source_kind(handle.source_kind)
        if source_kind is SourceKind.MATERIAL:
            primary_name = require_material_source_meta_primary_document(meta)
            source_directory = self._source_meta_path_for_read(
                handle.ticker, handle.document_id, source_kind
            ).parent
            validate_material_source_primary(source_meta=meta, source_directory=source_directory)
        else:
            primary_name = str(meta.get("primary_document", "")).strip()
            if not primary_name:
                raise FileNotFoundError("源文档 primary_document 不能为空")
        for item in files:
            if not isinstance(item, dict):
                continue
            name = (item["name"] if source_kind is SourceKind.MATERIAL else
                    str(item.get("name") or _infer_filename_from_uri(item.get("uri", ""))).strip())
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

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
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

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
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
            opener=self._publication_guarded_binary_opener(external_ticker),
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

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
        normalized_filename = filename.strip()
        if not normalized_filename:
            raise FileNotFoundError("filename 不能为空")
        guard_token = self._acquire_publication_guard(external_ticker)
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
            KeyError: material 元数据缺少必填 primary_document 时抛出。
            FileNotFoundError: 文档或主文件不存在时抛出。
            ValueError: 文件元数据非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 构建 Source 失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        normalized_source_kind = _normalize_source_kind(source_kind)
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            handle = self._get_source_handle_unguarded(
                external_ticker,
                external_document_id,
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
            ValueError: ticker、document identity、descriptor 或 source meta 不合法时抛出。
            OSError: 写入失败。
        """

        ticker = _require_external_identity(req.ticker, field_name="ticker")
        document_id = _require_external_identity(
            req.document_id,
            field_name="document_id",
        )
        source_root = self._source_root(ticker, source_kind, state)
        source_root.mkdir(parents=True, exist_ok=True)
        meta_path = self._source_meta_path(
            ticker,
            document_id,
            source_kind,
            state,
        )
        document_dir = meta_path.parent

        meta_exists = meta_path.exists()
        if is_create and meta_exists:
            raise FileExistsError(f"文档已存在: ticker={ticker} document_id={document_id}")
        if not is_create and not meta_exists:
            raise FileNotFoundError(f"文档不存在: ticker={ticker} document_id={document_id}")

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
        merged_meta["document_id"] = document_id
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
            document_id=document_id,
            source_kind=source_kind,
        )

        if source_kind is SourceKind.MATERIAL:
            validate_material_source_primary(source_meta=merged_meta, source_directory=meta_path.parent)
        _write_json(meta_path, merged_meta)

        if source_kind == SourceKind.FILING:
            self._upsert_filing_manifest(
                state,
                [project_filing_manifest_item(merged_meta)],
            )
        else:
            self._upsert_material_manifest(
                state,
                [project_material_manifest_item(merged_meta)],
            )

        primary_file_uri = (
            _resolve_primary_uri(file_payloads, selected_primary_document)
            if selected_primary_document is not None
            else None
        )
        return DocumentHandle(
            ticker=ticker,
            document_id=document_id,
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
            KeyError: 既有源元数据缺少 is_deleted 时抛出。
            FileNotFoundError: 文档不存在。
            ValueError: ticker、document identity、descriptor 或 source meta 不合法时抛出。
            SourceIntegrityRepairRequiredError: 重删目标或其 manifest 仍需修复时抛出。
            SourceIntegrityPreflightError: 重删目标完整性不可信时抛出。
            RuntimeError: exact inspector 未返回目标时抛出。
            OSError: 写入失败。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        meta_path = self._source_meta_path(
            external_ticker,
            external_document_id,
            source_kind,
            state,
        )
        if not meta_path.exists():
            raise FileNotFoundError(f"文档不存在: ticker={external_ticker} document_id={external_document_id}")

        meta = _read_json_object(meta_path)
        current_deleted = require_source_meta_is_deleted(meta)
        if deleted and current_deleted:
            # 同一个 writer view 的完整事实才允许重删 no-op；损坏不能借删除修复。
            inspection = _inspect_source_kind_unguarded(
                ticker=external_ticker,
                source_kind=source_kind,
                ticker_dir=state.staging_ticker_dir,
                source_root=self._source_root(external_ticker, source_kind, state),
                requested_document_id=external_document_id,
            )
            target = inspection.target
            if target is None:
                raise RuntimeError("重删完整性检查缺少 exact target")
            if target.classification.status is SourceIntegrityStatus.REPAIR_REQUIRED:
                raise SourceIntegrityRepairRequiredError()
            if target.classification.status is not SourceIntegrityStatus.COMPLETE:
                raise SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSAFE_PUBLICATION)
        else:
            meta["is_deleted"] = deleted
            meta["deleted_at"] = now_iso8601() if deleted else None
            meta["updated_at"] = now_iso8601()
            meta = _prepare_complete_source_meta(
                meta,
                ticker=external_ticker,
                document_id=external_document_id,
                source_kind=source_kind,
            )
            if source_kind is SourceKind.MATERIAL:
                validate_material_source_primary(source_meta=meta, source_directory=meta_path.parent)
            _write_json(meta_path, meta)

            if source_kind == SourceKind.FILING:
                self._upsert_filing_manifest(
                    state,
                    [project_filing_manifest_item(meta)],
                )
            else:
                self._upsert_material_manifest(
                    state,
                    [project_material_manifest_item(meta)],
                )

        file_payloads = _extract_file_payloads(meta)
        return DocumentHandle(
            ticker=external_ticker,
            document_id=external_document_id,
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
    normalized.pop(_SOURCE_REVISION_META_FIELD, None)
    SourceDocumentProvenance.from_meta(normalized, source_kind)
    normalized[_SOURCE_REVISION_META_FIELD] = uuid.uuid4().hex
    return normalized
