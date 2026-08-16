"""Docling 上传服务。

该模块封装 filing/material 的通用上传流程，保留 OLD 文件校验、Docling
转换、文件事件、create/update/delete/skip/overwrite 与 source document
upsert 语义；仓储读写统一经 ``dayu.fins.storage`` 协议完成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Final, Literal, TypeAlias

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins._log import Log
from dayu.fins.direct_events import canonicalize_fins_public_file_label
from dayu.fins.domain.document_models import (
    BatchToken,
    FinsSourceProvider,
    FileObjectMeta,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_process_converter import (
    DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
    DoclingConversionCancelledError,
    DoclingConversionError,
    DoclingConverter,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    SourceIntegrityRepairBlockedError,
    SourceIntegrityRevisionConflictError,
    SourceDocumentRepositoryProtocol,
    require_source_meta_is_deleted,
)
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.upload_format_contract import (
    FinsUploadFilingFiles,
    FinsUploadMaterialFiles,
)
from dayu.fins.upload_failure import (
    FinsUploadFailureError,
    fins_upload_empty_input_failure,
    fins_upload_failure_from_exception,
    fins_upload_source_repair_blocked_failure,
    fins_upload_source_revision_stale_failure,
)
from dayu.fins.upload_repair_contract import (
    ExistingSourceAutoRepair,
    ExistingSourceRepairDisposition,
    NoExistingSourceRepair,
)

JsonObject: TypeAlias = dict[str, JsonValue]

UPLOAD_ACTIONS: Final[frozenset[str]] = frozenset({"create", "update", "delete"})
DOCLING_FILE_SUFFIX: Final[str] = "_docling.json"
_FILING_ASSET_IDENTITY_NAMESPACE: Final[str] = "fins-upload-asset-v1"
_FILING_ASSET_IDENTITY_SEPARATOR: Final[bytes] = b"\0"
_FILING_ORIGINAL_ASSET_PREFIX: Final[str] = "original-"
_FILING_PRIMARY_ROLE_FINGERPRINT_VERSION: Final[str] = "filing-primary-role-v2"
_AssetSource: TypeAlias = Literal["original", "docling"]
_ASSET_SOURCE_ORIGINAL: Final[_AssetSource] = "original"
_ASSET_SOURCE_DOCLING: Final[_AssetSource] = "docling"
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

UploadFileEventType = Literal[
    "conversion_started",
    "file_uploaded",
    "file_skipped",
    "file_failed",
]


@dataclass(frozen=True)
class UploadFileEventPayload:
    """上传文件级事件载荷。

    Attributes:
        event_type: 文件级事件类型。
        name: 文件名。
        payload: 事件负载。
    """

    event_type: UploadFileEventType
    name: str
    payload: JsonObject


@dataclass(frozen=True)
class UploadOperationResult:
    """上传操作结果。

    Attributes:
        status: 上传状态。
        document_id: 可选业务文档 ID。
        internal_document_id: 可选内部文档 ID。
        stored_file_count: 成功写入 staging 的用户输入 original 数；仅在 commit 成功后对外消费。
        file_events: 文件级事件。
        payload: 结果负载。
    """

    status: str
    document_id: str | None
    internal_document_id: str | None
    stored_file_count: int
    file_events: list[UploadFileEventPayload]
    payload: JsonObject


@dataclass(frozen=True)
class _PendingFileAsset:
    """待落盘文件资产。

    Attributes:
        name: 仓储文件身份。
        original_filename: filing 用户输入 basename；material 为 ``None``。
        derived_from: filing derived 对应的 exact original identity；其余为 ``None``。
        data: 文件内容。
        content_type: 文件内容类型。
        sha256: 文件内容 SHA-256。
        size: 文件字节数。
        source: original 或 Docling 派生来源。
    """

    name: str
    original_filename: str | None
    derived_from: str | None
    data: bytes
    content_type: str | None
    sha256: str
    size: int
    source: _AssetSource


@dataclass(frozen=True, slots=True)
class _UploadSourceFingerprint:
    """上传指纹及 identical-skip 安全性。

    Attributes:
        value: 可持久化到 source meta 的 SHA-256 摘要。
        identical_skip_safe: 当前输入是否可安全按相同摘要提前跳过。
    """

    value: str
    identical_skip_safe: bool


@dataclass(frozen=True)
class _PreparedDeleteMutation:
    """已完成业务校验、等待短事务发布的删除动作。"""

    ticker: str
    source_kind: SourceKind
    document_id: str
    internal_document_id: str


@dataclass(frozen=True)
class _PreparedAssetMutation:
    """已完成文件读取与 Docling 转换、等待短事务发布的上传动作。"""

    ticker: str
    source_kind: SourceKind
    action: str
    document_id: str
    internal_document_id: str
    form_type: str
    overwrite: bool
    pending_assets: tuple[_PendingFileAsset, ...]
    conversion_events: tuple[UploadFileEventPayload, ...]
    primary_document: str
    previous_meta: JsonObject | None
    meta: JsonObject
    source_fingerprint: str
    document_version: str
    repair_disposition: ExistingSourceRepairDisposition


@dataclass(frozen=True)
class _UploadSelectionPreparation:
    """Service 入口已收窄的有序 original 与转换输入。"""

    ordered_files: tuple[Path, ...]
    converter_inputs: tuple[Path, ...]
    filing_primary: Path | None


PreparedDoclingUpload: TypeAlias = UploadOperationResult | _PreparedDeleteMutation | _PreparedAssetMutation
"""Docling 转换完成后交给 top-level publication owner 的 typed plan。"""


class UploadOverwritePrecondition(str, Enum):
    """上传动作与 published source 状态的 closed 前置条件结果。"""

    ALLOWED = "allowed"
    CREATE_TARGET_EXISTS = "create_target_exists"
    UPDATE_TARGET_MISSING = "update_target_missing"


def evaluate_upload_overwrite_precondition(
    *,
    action: str,
    previous_meta: Mapping[str, JsonValue] | None,
    overwrite: bool,
) -> UploadOverwritePrecondition:
    """评估 create/update 对当前 source state 的 closed admission 前置条件。

    Args:
        action: 已解析为 create、update 或 delete 的动作。
        previous_meta: 当前 published source meta；不存在时为 ``None``。
        overwrite: 是否允许 create 覆盖既有目标；不提供 update upsert 权限。

    Returns:
        closed 前置条件 disposition。

    Raises:
        ValueError: action 不在 workflow closed set 时抛出。
    """

    if action not in UPLOAD_ACTIONS:
        raise ValueError("上传动作必须是 create、update 或 delete")
    if action == "create" and previous_meta is not None and not overwrite:
        return UploadOverwritePrecondition.CREATE_TARGET_EXISTS
    if action == "update" and previous_meta is None:
        return UploadOverwritePrecondition.UPDATE_TARGET_MISSING
    return UploadOverwritePrecondition.ALLOWED


class DoclingUploadService:
    """Docling 上传服务。"""

    MODULE: Final[str] = "FINS.DOCLING_UPLOAD"

    def __init__(
        self,
        source_repository: SourceDocumentRepositoryProtocol,
        blob_repository: DocumentBlobRepositoryProtocol,
        *,
        docling_converter: DoclingConverter,
    ) -> None:
        """初始化服务。

        Args:
            source_repository: 源文档仓储实现。
            blob_repository: 文档文件对象仓储实现。
            docling_converter: Fins 共享 Docling 转换器。

        Returns:
            无。

        Raises:
            ValueError: 仓储为空时抛出。
        """

        if source_repository is None:
            raise ValueError("source_repository 不能为空")
        if blob_repository is None:
            raise ValueError("blob_repository 不能为空")
        if docling_converter is None:
            raise ValueError("docling_converter 不能为空")
        self._source_repository = source_repository
        self._blob_repository = blob_repository
        self._docling_converter = docling_converter

    async def prepare_upload(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        action: str,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        selection: FinsUploadFilingFiles | FinsUploadMaterialFiles,
        overwrite: bool,
        previous_meta: Mapping[str, JsonValue] | None,
        meta: Mapping[str, JsonValue],
        repair_disposition: ExistingSourceRepairDisposition,
        cancellation: CancellationToken | None,
    ) -> PreparedDoclingUpload:
        """完成读取与 Docling 转换，生成待发布计划。

        Args:
            ticker: 股票代码。
            source_kind: 文档类型。
            action: 动作类型。
            document_id: 文档 ID。
            internal_document_id: 内部文档 ID。
            form_type: 文档 form type。
            selection: 与 ``source_kind`` 一致的 typed 文件选择。
            overwrite: 是否强制覆盖。
            previous_meta: caller 从当前 state owner 取得的 source meta。
            meta: 业务元数据字段。
            repair_disposition: authoritative validator 产生的既有 source repair 授权。
            cancellation: 公共取消观察 token；``None`` 表示无取消源。

        Returns:
            无需写入时返回最终结果；否则返回等待 caller 短事务发布的 typed plan。

        Raises:
            KeyError: 既有 source meta 缺少 canonical ``is_deleted`` 时抛出。
            ValueError: 参数非法，或既有 source meta 的 ``is_deleted`` 非布尔值时抛出。
            FileNotFoundError: 需要的文件或文档不存在时抛出。
            FileExistsError: create 目标已存在且不可覆盖时抛出。
            FinsUploadFailureError: filing 为空或无法转换时抛出 typed content failure。
            RuntimeError: 上传失败时抛出。
            OSError: 仓储读写失败时抛出。
        """

        selection_preparation = _prepare_upload_selection(
            source_kind=source_kind,
            selection=selection,
        )
        if not isinstance(
            repair_disposition,
            (NoExistingSourceRepair, ExistingSourceAutoRepair),
        ):
            raise ValueError("repair_disposition 必须是封闭 repair contract")
        normalized_action = action.strip().lower()
        if normalized_action not in UPLOAD_ACTIONS:
            raise ValueError(f"不支持的 action: {action}")
        if (
            normalized_action == "delete"
            and isinstance(repair_disposition, ExistingSourceAutoRepair)
        ):
            raise ValueError("delete 上传不得携带 existing source repair 授权")
        is_empty = not selection_preparation.ordered_files
        if normalized_action == "delete" and not is_empty:
            raise ValueError("delete 上传必须使用空文件 selection")
        if normalized_action != "delete" and is_empty:
            raise ValueError("create/update 上传必须使用非空文件 selection")
        normalized_ticker = normalize_ticker(ticker).canonical
        if not document_id.strip():
            raise ValueError("document_id 不能为空")
        if not internal_document_id.strip():
            raise ValueError("internal_document_id 不能为空")
        if not form_type.strip():
            raise ValueError("form_type 不能为空")
        if _is_cancelled(cancellation):
            return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)

        if normalized_action == "delete":
            return _PreparedDeleteMutation(
                ticker=normalized_ticker,
                source_kind=source_kind,
                document_id=document_id,
                internal_document_id=internal_document_id,
            )

        normalized_previous_meta = dict(previous_meta) if previous_meta is not None else None
        validated_files = _validate_source_files(selection_preparation.ordered_files)
        precondition = evaluate_upload_overwrite_precondition(
            action=normalized_action,
            previous_meta=normalized_previous_meta,
            overwrite=overwrite,
        )
        if precondition is UploadOverwritePrecondition.CREATE_TARGET_EXISTS and source_kind is SourceKind.FILING:
            raise FileExistsError(f"Document already exists for create: {document_id}")
        if precondition is UploadOverwritePrecondition.UPDATE_TARGET_MISSING:
            raise FileNotFoundError(f"Document not found for update: {document_id}")
        if _is_cancelled(cancellation):
            return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)

        original_assets = self._build_original_assets(
            validated_files,
            source_kind=source_kind,
        )
        source_fingerprint = _build_upload_source_fingerprint(
            original_assets,
            source_kind=source_kind,
            filing_primary=selection_preparation.filing_primary,
        )
        if _can_skip_upload(
            normalized_previous_meta,
            source_fingerprint,
            overwrite,
            repair_disposition=repair_disposition,
        ):
            Log.info(
                f"文档已存在且未变更，跳过上传: ticker={normalized_ticker} document_id={document_id}",
                module=self.MODULE,
            )
            skipped_events = _build_skipped_file_events(validated_files)
            return UploadOperationResult(
                status="skipped",
                document_id=document_id,
                internal_document_id=internal_document_id,
                stored_file_count=0,
                file_events=skipped_events,
                payload={
                    "document_id": document_id,
                    "internal_document_id": internal_document_id,
                    "skip_reason": "already_uploaded",
                },
            )

        try:
            pending_assets, conversion_events, primary_document = await self._build_pending_assets(
                selection_preparation,
                original_assets,
                source_kind=source_kind,
                cancellation=cancellation,
            )
        except DoclingConversionCancelledError:
            return _build_cancelled_result(
                document_id=document_id,
                internal_document_id=internal_document_id,
            )
        if _is_cancelled(cancellation):
            return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)
        current_version = _resolve_document_version(normalized_previous_meta, source_fingerprint)
        staging_meta = self._build_upsert_meta(
            previous_meta=normalized_previous_meta,
            source_fingerprint=source_fingerprint.value,
            document_version=current_version,
            base_meta=meta,
        )
        return _PreparedAssetMutation(
            ticker=normalized_ticker,
            source_kind=source_kind,
            action=normalized_action,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            overwrite=overwrite,
            pending_assets=tuple(pending_assets),
            conversion_events=tuple(conversion_events),
            primary_document=primary_document,
            previous_meta=normalized_previous_meta,
            meta=staging_meta,
            source_fingerprint=source_fingerprint.value,
            document_version=current_version,
            repair_disposition=repair_disposition,
        )

    def publish_prepared_upload(
        self,
        prepared: PreparedDoclingUpload,
        *,
        batch: BatchToken,
        cancellation: CancellationToken | None,
    ) -> UploadOperationResult:
        """在 caller-owned 短事务内发布已准备的 Docling 计划。

        Args:
            prepared: ``prepare_upload`` 返回的 typed plan。
            batch: caller 显式传入的 batch capability。
            cancellation: 公共取消观察 token；``None`` 表示无取消源。

        Returns:
            上传操作结果；取消结果要求 caller rollback，其他写入结果可 commit。

        Raises:
            FinsUploadFailureError: repair target stale 或被其它 source 阻断时抛出。
            OSError: 仓储写入失败时抛出。
            ValueError: batch 或计划字段非法时抛出。
            RuntimeError: 完整 source 无法构造时抛出。
        """

        if isinstance(prepared, UploadOperationResult):
            return prepared
        if isinstance(prepared, _PreparedDeleteMutation):
            self._delete_source_document(
                ticker=prepared.ticker,
                source_kind=prepared.source_kind,
                document_id=prepared.document_id,
                batch=batch,
            )
            return UploadOperationResult(
                status="deleted",
                document_id=prepared.document_id,
                internal_document_id=prepared.internal_document_id,
                stored_file_count=0,
                file_events=[],
                payload={
                    "document_id": prepared.document_id,
                    "internal_document_id": prepared.internal_document_id,
                    "deleted": True,
                },
            )
        result = self._store_upload_assets(
            ticker=prepared.ticker,
            source_kind=prepared.source_kind,
            action=prepared.action,
            document_id=prepared.document_id,
            internal_document_id=prepared.internal_document_id,
            form_type=prepared.form_type,
            overwrite=prepared.overwrite,
            pending_assets=list(prepared.pending_assets),
            conversion_events=list(prepared.conversion_events),
            primary_document=prepared.primary_document,
            previous_meta=prepared.previous_meta,
            meta=prepared.meta,
            source_fingerprint=prepared.source_fingerprint,
            document_version=prepared.document_version,
            repair_disposition=prepared.repair_disposition,
            cancellation=cancellation,
            batch=batch,
        )
        if result.status == "uploaded":
            Log.verbose(
                (
                    f"Docling 转换与源文档落盘完成: ticker={prepared.ticker} "
                    f"document_id={prepared.document_id} "
                    f"original_files={result.stored_file_count}"
                ),
                module=self.MODULE,
            )
        return result

    def _store_upload_assets(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        action: str,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        overwrite: bool,
        pending_assets: list[_PendingFileAsset],
        conversion_events: list[UploadFileEventPayload],
        primary_document: str,
        previous_meta: JsonObject | None,
        meta: JsonObject,
        source_fingerprint: str,
        document_version: str,
        repair_disposition: ExistingSourceRepairDisposition,
        cancellation: CancellationToken | None,
        batch: BatchToken,
    ) -> UploadOperationResult:
        """在 storage owner 边界写入上传文件和最终 source meta。

        Args:
            ticker: 已规范化股票代码。
            source_kind: 文档来源类型。
            action: 已解析上传动作。
            document_id: 文档 ID。
            internal_document_id: 内部文档 ID。
            form_type: 表单类型。
            overwrite: 是否开启覆盖。
            pending_assets: 已完成转换、等待落盘的文件资产。
            conversion_events: 转换阶段产生的文件事件。
            primary_document: preparation 明确产生的主 Docling 文件名。
            previous_meta: 旧 source meta。
            meta: 本次写入的 source meta。
            source_fingerprint: 本次上传源指纹。
            document_version: 本次文档版本。
            repair_disposition: authoritative validator 产生的既有 source repair 授权。
            cancellation: 公共取消观察 token；``None`` 表示无取消源。
            batch: caller 显式传入的 batch capability。

        Returns:
            上传操作结果。

        Raises:
            FinsUploadFailureError: repair target stale 或被其它 source 阻断时抛出。
            RuntimeError: 未生成主 Docling 文件时抛出。
            OSError: 仓储写入失败时抛出。
        """

        replace_existing = previous_meta is not None and (action == "update" or (action == "create" and overwrite))
        if isinstance(repair_disposition, ExistingSourceAutoRepair):
            try:
                self._source_repository.reset_source_document_for_repair(
                    ticker=ticker,
                    document_id=document_id,
                    source_kind=source_kind,
                    expected_integrity=repair_disposition.expected_integrity,
                    batch=batch,
                )
            except SourceIntegrityRevisionConflictError as exc:
                raise FinsUploadFailureError(
                    fins_upload_source_revision_stale_failure()
                ) from exc
            except SourceIntegrityRepairBlockedError as exc:
                raise FinsUploadFailureError(
                    fins_upload_source_repair_blocked_failure()
                ) from exc
        elif replace_existing:
            # 完整输入的既有目标先在同一 staging batch 删除，再由下方 blob-first + create
            # 一次性重建；reset 前持有的 previous_meta 仍是版本与首次创建时间真源。
            self._source_repository.reset_source_document(
                ticker=ticker,
                document_id=document_id,
                source_kind=source_kind,
                batch=batch,
            )

        stored_entries: list[JsonObject] = []
        stored_original_count = 0
        file_events: list[UploadFileEventPayload] = list(conversion_events)
        handle = SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind.value,
        )
        for asset in pending_assets:
            if _is_cancelled(cancellation):
                return _build_cancelled_result(
                    document_id=document_id,
                    internal_document_id=internal_document_id,
                )
            file_meta = self._blob_repository.store_file(
                handle=handle,
                filename=asset.name,
                data=BytesIO(asset.data),
                batch=batch,
                content_type=asset.content_type,
            )
            if asset.source == _ASSET_SOURCE_ORIGINAL:
                stored_original_count += 1
            stored_entries.append(
                _build_stored_file_entry(
                    asset=asset,
                    file_meta=file_meta,
                    source_kind=source_kind,
                )
            )
            event_name = (
                _require_filing_original_filename(asset)
                if source_kind is SourceKind.FILING
                else asset.name
            )
            file_events.append(
                UploadFileEventPayload(
                    event_type="file_uploaded",
                    name=event_name,
                    payload={
                        "source": asset.source,
                        "size": file_meta.size,
                        "content_type": file_meta.content_type,
                    },
                )
            )

        if _is_cancelled(cancellation):
            return _build_cancelled_result(
                document_id=document_id,
                internal_document_id=internal_document_id,
            )
        self._create_source_document(
            source_kind=source_kind,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            primary_document=primary_document,
            file_entries=stored_entries,
            meta=meta,
            batch=batch,
        )
        if _is_cancelled(cancellation):
            return _build_cancelled_result(
                document_id=document_id,
                internal_document_id=internal_document_id,
            )
        return UploadOperationResult(
            status="uploaded",
            document_id=document_id,
            internal_document_id=internal_document_id,
            stored_file_count=stored_original_count,
            file_events=file_events,
            payload={
                "document_id": document_id,
                "internal_document_id": internal_document_id,
                "primary_document": primary_document,
                "source_fingerprint": source_fingerprint,
                "document_version": document_version,
            },
        )

    def resolve_document_id_by_internal(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        internal_document_id: str,
    ) -> str | None:
        """通过 internal document ID 反查 document ID。

        Args:
            ticker: 股票代码。
            source_kind: 文档来源类型。
            internal_document_id: 内部文档 ID。

        Returns:
            匹配到的 document ID；无匹配返回 ``None``。

        Raises:
            OSError: 读取仓储失败时抛出。
            ValueError: 元数据格式非法时抛出。
        """

        normalized_ticker = normalize_ticker(ticker).canonical
        target_internal_id = internal_document_id.strip()
        for document_id in self._source_repository.list_source_document_ids(normalized_ticker, source_kind):
            meta = self._safe_get_document_meta(normalized_ticker, document_id, source_kind)
            if meta is None:
                continue
            if _text_meta(meta, "internal_document_id") == target_internal_id:
                return document_id
        return None

    def _safe_get_document_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> JsonObject | None:
        """安全读取文档元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 文档来源类型。

        Returns:
            元数据字典；不存在时返回 ``None``。

        Raises:
            ValueError: 元数据格式非法时抛出。
            OSError: 仓储读取失败时抛出。
        """

        try:
            return self._source_repository.get_source_meta(
                ticker=ticker,
                document_id=document_id,
                source_kind=source_kind,
            )
        except FileNotFoundError:
            return None

    def _delete_source_document(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        document_id: str,
        batch: BatchToken,
    ) -> None:
        """删除源文档。

        Args:
            ticker: 股票代码。
            source_kind: 文档来源类型。
            document_id: 文档 ID。
            batch: caller 显式传入的 batch capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            OSError: 删除失败时抛出。
        """

        self._source_repository.delete_source_document(
            SourceDocumentStateChangeRequest(
                ticker=ticker,
                document_id=document_id,
                source_kind=source_kind.value,
            ),
            batch=batch,
        )

    def _build_original_assets(
        self,
        files: list[Path],
        *,
        source_kind: SourceKind,
    ) -> list[_PendingFileAsset]:
        """构建原始上传文件资产列表。

        Args:
            files: 源文件列表。
            source_kind: filing 或 material 文档类型。

        Returns:
            仅包含原始上传文件的资产列表。

        Raises:
            FileNotFoundError: 源文件不存在时抛出。
            FinsUploadFailureError: filing 文件为空时抛出。
            OSError: 源文件读取失败时抛出。
        """

        assets: list[_PendingFileAsset] = []
        for file_path in files:
            raw_data = file_path.read_bytes()
            if source_kind is SourceKind.FILING and raw_data == b"":
                raw_basename = file_path.name
                _LOGGER.error(
                    "Filing upload empty input rejected before publication; raw_basename=%r",
                    raw_basename,
                )
                file_label = canonicalize_fins_public_file_label(raw_basename)
                raise FinsUploadFailureError(fins_upload_empty_input_failure(file_label))
            raw_sha256 = hashlib.sha256(raw_data).hexdigest()
            raw_content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            asset_name = (
                _build_filing_original_asset_identity(file_path)
                if source_kind is SourceKind.FILING
                else file_path.name
            )
            assets.append(
                _PendingFileAsset(
                    name=asset_name,
                    original_filename=file_path.name if source_kind is SourceKind.FILING else None,
                    derived_from=None,
                    data=raw_data,
                    content_type=raw_content_type,
                    sha256=raw_sha256,
                    size=len(raw_data),
                    source=_ASSET_SOURCE_ORIGINAL,
                )
            )
        if source_kind is SourceKind.FILING:
            _require_unique_filing_original_identities(assets)
        return assets

    async def _build_pending_assets(
        self,
        preparation: _UploadSelectionPreparation,
        original_assets: list[_PendingFileAsset],
        *,
        source_kind: SourceKind,
        cancellation: CancellationToken | None,
    ) -> tuple[list[_PendingFileAsset], list[UploadFileEventPayload], str]:
        """构建待上传资产列表与转换阶段事件。

        Args:
            preparation: 入口 typed selection 投影的 ordered/converter inputs。
            original_assets: 已读取完成的原始文件资产列表。
            source_kind: filing 或 material 文档类型。
            cancellation: 公共取消观察 token；``None`` 表示无取消源。

        Returns:
            待上传资产、转换阶段事件与明确的主 Docling 文件名。

        Raises:
            DoclingConversionCancelledError: 转换前或两次转换之间观察到取消时抛出。
            FinsUploadFailureError: filing Docling 转换失败时抛出。
            DoclingConversionError: material Docling 转换失败时原样抛出。
            RuntimeError: 未产生主 Docling 文件时抛出。
            ValueError: preparation 与 ``original_assets`` 不一致时抛出。
        """

        if len(preparation.ordered_files) != len(original_assets):
            raise ValueError("ordered_files 与 original_assets 数量不一致")

        assets = list(original_assets)
        conversion_events: list[UploadFileEventPayload] = []
        primary_document: str | None = None
        for index, file_path in enumerate(preparation.converter_inputs):
            if source_kind is SourceKind.FILING:
                try:
                    original_index = preparation.ordered_files.index(file_path)
                except ValueError as exc:
                    raise ValueError("filing converter input 必须精确命中 original") from exc
            else:
                if preparation.ordered_files[index] != file_path:
                    raise ValueError("material converter_inputs 必须保持 ordered_files 的前缀顺序")
                original_index = index
            original_asset = original_assets[original_index]
            if _is_cancelled(cancellation):
                raise DoclingConversionCancelledError()
            conversion_events.append(
                UploadFileEventPayload(
                    event_type="conversion_started",
                    name=file_path.name,
                    payload={
                        "source": "docling",
                        "message": "正在 convert",
                    },
                )
            )
            try:
                conversion = await self._docling_converter.convert_to_json_bytes(
                    original_asset.data,
                    file_path.name,
                    config=DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
                    cancellation=cancellation,
                )
            except DoclingConversionError as exc:
                if source_kind is not SourceKind.FILING:
                    raise
                raw_basename = file_path.name
                _LOGGER.exception(
                    "Filing upload conversion rejected before publication; raw_basename=%r",
                    raw_basename,
                )
                file_label = canonicalize_fins_public_file_label(raw_basename)
                failure = fins_upload_failure_from_exception(
                    exc,
                    file_label=file_label,
                )
                raise FinsUploadFailureError(failure) from exc
            docling_data = conversion.json_bytes
            if source_kind is SourceKind.FILING:
                docling_name = _build_filing_derived_asset_identity(original_asset.name)
                original_filename = _require_filing_original_filename(original_asset)
                derived_from = original_asset.name
            else:
                docling_name = f"{file_path.stem}{DOCLING_FILE_SUFFIX}"
                original_filename = None
                derived_from = None
            if primary_document is None:
                primary_document = docling_name
            docling_sha256 = conversion.sha256
            assets.append(
                _PendingFileAsset(
                    name=docling_name,
                    original_filename=original_filename,
                    derived_from=derived_from,
                    data=docling_data,
                    content_type="application/json",
                    sha256=docling_sha256,
                    size=len(docling_data),
                    source=_ASSET_SOURCE_DOCLING,
                )
            )
        if primary_document is None:
            raise RuntimeError("未生成 docling 主文件，无法写入 primary_document")
        return assets, conversion_events, primary_document

    def _build_upsert_meta(
        self,
        *,
        previous_meta: JsonObject | None,
        source_fingerprint: str,
        document_version: str,
        base_meta: Mapping[str, JsonValue],
    ) -> JsonObject:
        """构建 upsert 元数据。

        Args:
            previous_meta: 旧元数据。
            source_fingerprint: 本次源指纹。
            document_version: 本次文档版本。
            base_meta: 业务层传入的基础元数据。

        Returns:
            待写入元数据。

        Raises:
            无。
        """

        now = now_iso8601()
        previous_first_ingested_at = (
            _text_meta(previous_meta, "first_ingested_at") if previous_meta is not None else None
        )
        previous_created_at = _text_meta(previous_meta, "created_at") if previous_meta is not None else None
        merged = dict(base_meta)
        merged["updated_at"] = now
        merged["first_ingested_at"] = previous_first_ingested_at or now
        merged["created_at"] = previous_created_at or now
        merged["document_version"] = document_version
        merged["source_fingerprint"] = source_fingerprint
        merged["ingest_complete"] = True
        merged["source_provider"] = FinsSourceProvider.USER_UPLOAD.to_storage_value()
        merged["is_deleted"] = False
        merged["deleted_at"] = None
        return merged

    def _create_source_document(
        self,
        *,
        source_kind: SourceKind,
        ticker: str,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        primary_document: str,
        file_entries: list[JsonObject],
        meta: JsonObject,
        batch: BatchToken,
    ) -> None:
        """在 blob 完整落盘后创建唯一 final source meta。

        Args:
            source_kind: 来源类型。
            ticker: 股票代码。
            document_id: 文档 ID。
            internal_document_id: 内部文档 ID。
            form_type: 表单类型。
            primary_document: 主文件名。
            file_entries: 文件条目列表。
            meta: 元数据字典。
            batch: caller 显式传入的 batch capability。

        Returns:
            无。

        Raises:
            FileExistsError: staging source 未先按 owner contract 清空时抛出。
            OSError: final source meta 或 manifest 写入失败时抛出。
        """

        request = SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            primary_document=primary_document,
            file_entries=file_entries,
            meta=meta,
        )
        self._source_repository.create_source_document(
            request,
            source_kind=source_kind,
            batch=batch,
        )


def commit_prepared_upload_batch(
    *,
    service: DoclingUploadService,
    batching_repository: BatchingRepositoryProtocol,
    batch: BatchToken,
    prepared: _PreparedDeleteMutation | _PreparedAssetMutation,
    cancellation: CancellationToken | None,
) -> UploadOperationResult:
    """发布并提交一个 caller-owned 文档 batch。

    本函数是上传 publication 生命周期的唯一 owner。最终取消检查返回的瞬间
    是 cancel 与 commit 的线性化点；进入 ``commit_batch`` 后 capability 已转交
    storage owner，调用方不再读取消状态，也不再回滚。

    Args:
        service: 只负责向 caller-owned batch 写入 staged mutation 的上传服务。
        batching_repository: batch 生命周期仓储。
        batch: 尚未交给 ``commit_batch`` 的 caller-owned capability。
        prepared: 已完成转换与业务校验的 mutation。
        cancellation: 公共取消观察 token；``None`` 表示无取消源。

    Returns:
        commit 正常返回后的完成结果，或 precommit 取消并回滚后的取消结果。

    Raises:
        BaseException: staged write、最终 checkpoint、rollback 或 commit 失败时抛出；
            commit 已开始后的异常不会触发 caller rollback。
    """

    batch_terminal_started = False
    try:
        result = service.publish_prepared_upload(
            prepared,
            batch=batch,
            cancellation=cancellation,
        )
        if result.status == "cancelled" or _is_cancelled(cancellation):
            batch_terminal_started = True
            batching_repository.rollback_batch(batch)
            return _build_cancelled_result(
                document_id=prepared.document_id,
                internal_document_id=prepared.internal_document_id,
            )
        # 先转移 capability 所有权，再进入 storage commit；从此不再读取取消或回滚。
        batch_terminal_started = True
        batching_repository.commit_batch(batch)
        return result
    finally:
        if not batch_terminal_started:
            rollback_prepared_upload_batch(
                batching_repository=batching_repository,
                batch=batch,
                operation_error=sys.exception(),
            )


def rollback_prepared_upload_batch(
    *,
    batching_repository: BatchingRepositoryProtocol,
    batch: BatchToken,
    operation_error: BaseException | None,
) -> None:
    """恰好一次回滚尚由 caller 持有的上传 batch，并保留主异常证据。

    Args:
        batching_repository: batch 生命周期仓储。
        batch: 尚未进入 commit 的 capability。
        operation_error: 当前正在传播的原始异常；正常路径为 ``None``。

    Returns:
        rollback 成功时返回 ``None``。

    Raises:
        BaseException: rollback 失败时保留原始异常为主异常；没有原始异常时
            原样抛出 rollback 异常。
    """

    try:
        batching_repository.rollback_batch(batch)
    except BaseException as rollback_error:
        if operation_error is not None:
            operation_error.add_note(f"rollback_batch failed; recovery evidence retained: {rollback_error}")
            raise operation_error from rollback_error
        raise


def _prepare_upload_selection(
    *,
    source_kind: SourceKind,
    selection: FinsUploadFilingFiles | FinsUploadMaterialFiles,
) -> _UploadSelectionPreparation:
    """按 source kind 收窄 typed selection 并确定转换输入。

    Args:
        source_kind: filing 或 material 来源类型。
        selection: Fins role owner 产生的 typed selection。

    Returns:
        保序 original 与 converter inputs。

    Raises:
        ValueError: source kind 与 selection 具体类型不一致时抛出。
    """

    if source_kind is SourceKind.FILING:
        if not isinstance(selection, FinsUploadFilingFiles):
            raise ValueError("filing source_kind 必须使用 filing selection")
        ordered_files = selection.ordered_files
        filing_primary = None if selection.is_empty else selection.require_primary()
        converter_inputs = () if filing_primary is None else (filing_primary,)
        return _UploadSelectionPreparation(
            ordered_files=ordered_files,
            converter_inputs=converter_inputs,
            filing_primary=filing_primary,
        )
    if source_kind is SourceKind.MATERIAL:
        if not isinstance(selection, FinsUploadMaterialFiles):
            raise ValueError("material source_kind 必须使用 material selection")
        return _UploadSelectionPreparation(
            ordered_files=selection.files,
            converter_inputs=selection.files,
            filing_primary=None,
        )
    raise ValueError(f"不支持的 source_kind: {source_kind}")


def _build_filing_original_asset_identity(normalized_path: Path) -> str:
    """从已规范化绝对路径构建 filing original 仓储身份。

    Args:
        normalized_path: validated selection 提供的绝对规范路径。

    Returns:
        不含绝对路径明文、使用完整 SHA-256 的稳定文件身份。

    Raises:
        TypeError: 输入不是 ``Path`` 时抛出。
        ValueError: 输入不是 absolute normalized path 时抛出。
    """

    if not isinstance(normalized_path, Path):
        raise TypeError("filing asset identity 输入必须是 Path")
    if not normalized_path.is_absolute() or normalized_path.resolve(strict=False) != normalized_path:
        raise ValueError("filing asset identity 输入必须是 absolute normalized path")
    digest_input = (
        _FILING_ASSET_IDENTITY_NAMESPACE.encode("utf-8")
        + _FILING_ASSET_IDENTITY_SEPARATOR
        + normalized_path.as_posix().encode("utf-8")
    )
    path_digest = hashlib.sha256(digest_input).hexdigest()
    return f"{_FILING_ORIGINAL_ASSET_PREFIX}{path_digest}{normalized_path.suffix.lower()}"


def _build_filing_derived_asset_identity(original_identity: str) -> str:
    """从 exact filing original identity 构建 Docling 派生身份。

    Args:
        original_identity: 同次 preparation 产生的 original 仓储身份。

    Returns:
        直接追加 Docling 后缀的派生身份。

    Raises:
        ValueError: original identity 为空或不属于 filing namespace 时抛出。
    """

    if not original_identity.startswith(_FILING_ORIGINAL_ASSET_PREFIX):
        raise ValueError("filing derived identity 必须来自 exact original identity")
    return f"{original_identity}{DOCLING_FILE_SUFFIX}"


def _require_unique_filing_original_identities(assets: list[_PendingFileAsset]) -> None:
    """断言同次请求产生的 filing original identities 唯一。

    Args:
        assets: 已读取并完成身份投影的 filing originals。

    Returns:
        全部 identity 唯一时返回 ``None``。

    Raises:
        RuntimeError: digest collision 或 identity 实现错误导致重复时抛出。
    """

    identities = [asset.name for asset in assets]
    if len(identities) != len(set(identities)):
        raise RuntimeError("filing original asset identity 必须唯一")


def _require_filing_original_filename(asset: _PendingFileAsset) -> str:
    """读取 filing asset 的用户可读 original filename。

    Args:
        asset: filing original 或 derived 资产。

    Returns:
        非空用户输入 basename。

    Raises:
        ValueError: filing asset 缺少 original filename 时抛出。
    """

    if asset.original_filename is None or not asset.original_filename:
        raise ValueError("filing asset 必须携带 original_filename")
    return asset.original_filename


def _validate_source_files(files: tuple[Path, ...]) -> list[Path]:
    """校验上传文件列表。

    Args:
        files: 原始文件列表。

    Returns:
        标准化后的文件路径列表。

    Raises:
        ValueError: 文件路径类型非法时抛出。
        FileNotFoundError: 文件不存在时抛出。
    """

    normalized: list[Path] = []
    for file_path in files:
        if not isinstance(file_path, Path):
            raise ValueError("上传文件必须是 Path")
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"上传文件不存在: {file_path}")
        normalized.append(file_path)
    return normalized


def _can_skip_upload(
    previous_meta: Mapping[str, JsonValue] | None,
    source_fingerprint: _UploadSourceFingerprint,
    overwrite: bool,
    *,
    repair_disposition: ExistingSourceRepairDisposition,
) -> bool:
    """判断是否可跳过上传。

    Args:
        previous_meta: 旧元数据。
        source_fingerprint: 本次源指纹。
        overwrite: 是否覆盖。
        repair_disposition: authoritative validator 产生的既有 source repair 授权。

    Returns:
        满足跳过条件时返回 ``True``。

    Raises:
        KeyError: 既有 source meta 缺少 ``is_deleted`` 时抛出。
        ValueError: 既有 source meta 的 ``is_deleted`` 不是布尔值时抛出。
    """

    if isinstance(repair_disposition, ExistingSourceAutoRepair):
        return False
    if overwrite or previous_meta is None:
        return False
    if require_source_meta_is_deleted(previous_meta):
        return False
    if not source_fingerprint.identical_skip_safe:
        return False
    previous_fingerprint = _text_meta(previous_meta, "source_fingerprint")
    return bool(previous_fingerprint) and previous_fingerprint == source_fingerprint.value


def _build_upload_source_fingerprint(
    assets: list[_PendingFileAsset],
    *,
    source_kind: SourceKind,
    filing_primary: Path | None,
) -> _UploadSourceFingerprint:
    """构建上传源指纹。

    Args:
        assets: 待上传资产列表。
        source_kind: filing 或 material 来源类型。
        filing_primary: filing selection 的 authoritative primary；material 必须为 ``None``。

    Returns:
        指纹摘要与 identical-skip 安全性的 typed 结果。

    Raises:
        ValueError: filing 缺少 original 或 primary、primary identity 未 exact 命中一次、filing asset
            缺少 ``original_filename``、material 非法携带 filing primary，或 source kind 不受支持时抛出。
    """

    if source_kind is SourceKind.FILING:
        if not assets:
            raise ValueError("filing fingerprint 必须携带非空 originals")
        if filing_primary is None:
            raise ValueError("filing fingerprint 必须携带 authoritative primary")
        primary_identity = _build_filing_original_asset_identity(filing_primary)
        primary_matches = [asset for asset in assets if asset.name == primary_identity]
        if len(primary_matches) != 1:
            raise ValueError("filing primary identity 必须 exact 命中一个 original asset")
        descriptors: list[tuple[_PendingFileAsset, JsonObject]] = [
            (
                asset,
                {
                    "original_filename": _require_filing_original_filename(asset),
                    "sha256": asset.sha256,
                    "size": asset.size,
                    "source": asset.source,
                },
            )
            for asset in assets
        ]
        sorted_descriptors = sorted(
            descriptors,
            key=lambda item: (
                _require_filing_original_filename(item[0]),
                item[0].sha256,
                item[0].size,
                item[0].source,
            ),
        )
        if len(assets) == 1:
            payload: JsonValue = [descriptor for _, descriptor in sorted_descriptors]
            identical_skip_safe = True
        else:
            primary_descriptor = next(
                descriptor
                for asset, descriptor in descriptors
                if asset.name == primary_identity
            )
            companion_descriptors: list[JsonValue] = [
                descriptor
                for asset, descriptor in sorted_descriptors
                if asset.name != primary_identity
            ]
            role_payload: JsonObject = {
                "fingerprint_version": _FILING_PRIMARY_ROLE_FINGERPRINT_VERSION,
                "primary": primary_descriptor,
                "companions": companion_descriptors,
            }
            payload = role_payload
            identical_skip_safe = primary_descriptor not in companion_descriptors
    elif source_kind is SourceKind.MATERIAL:
        if filing_primary is not None:
            raise ValueError("material fingerprint 不得携带 filing primary")
        payload = [
            {
                "name": asset.name,
                "sha256": asset.sha256,
                "size": asset.size,
                "source": asset.source,
            }
            for asset in sorted(assets, key=lambda item: item.name)
        ]
        identical_skip_safe = True
    else:
        raise ValueError(f"不支持的 source_kind: {source_kind}")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _UploadSourceFingerprint(
        value=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        identical_skip_safe=identical_skip_safe,
    )


def _resolve_document_version(
    previous_meta: Mapping[str, JsonValue] | None,
    source_fingerprint: _UploadSourceFingerprint,
) -> str:
    """解析文档版本号。

    Args:
        previous_meta: 旧元数据。
        source_fingerprint: 本次源指纹。

    Returns:
        文档版本号。

    Raises:
        无。
    """

    if previous_meta is None:
        return "v1"
    previous_version = _text_meta(previous_meta, "document_version") or "v1"
    if not source_fingerprint.identical_skip_safe:
        return _increment_document_version(previous_version)
    previous_fingerprint = _text_meta(previous_meta, "source_fingerprint")
    if previous_fingerprint and previous_fingerprint != source_fingerprint.value:
        return _increment_document_version(previous_version)
    return previous_version


def _build_skipped_file_events(files: list[Path]) -> list[UploadFileEventPayload]:
    """构建跳过事件列表。

    Args:
        files: 输入文件列表。

    Returns:
        文件跳过事件列表。

    Raises:
        无。
    """

    events: list[UploadFileEventPayload] = []
    for file_path in files:
        events.append(
            UploadFileEventPayload(
                event_type="file_skipped",
                name=file_path.name,
                payload={"reason": "already_uploaded"},
            )
        )
    return events


def _increment_document_version(previous_version: str) -> str:
    """递增文档版本号。

    Args:
        previous_version: 旧版本号。

    Returns:
        新版本号。

    Raises:
        无。
    """

    matched = previous_version.strip()
    if not matched.startswith("v"):
        return "v2"
    suffix = matched[1:]
    if not suffix.isdigit():
        return "v2"
    return f"v{int(suffix) + 1}"


def build_material_ids(
    *,
    form_type: str,
    material_name: str,
    fiscal_year: int | None,
    fiscal_period: str | None,
) -> tuple[str, str]:
    """生成稳定材料文档 ID 对。

    Args:
        form_type: 材料 form type。
        material_name: 材料名称。
        fiscal_year: 可选财年。
        fiscal_period: 可选财期。

    Returns:
        ``(document_id, internal_document_id)``。

    Raises:
        ValueError: 参数非法时抛出。
    """

    normalized_form_type = form_type.strip().upper()
    normalized_material_name = material_name.strip()
    normalized_period = _normalize_optional_upload_fiscal_period(fiscal_period)
    if not normalized_form_type:
        raise ValueError("form_type 不能为空")
    if not normalized_material_name:
        raise ValueError("material_name 不能为空")
    seed_parts = [normalized_form_type, normalized_material_name]
    if fiscal_year is not None:
        seed_parts.append(str(fiscal_year))
    if normalized_period is not None:
        seed_parts.append(normalized_period)
    digest = hashlib.sha1("|".join(seed_parts).encode("utf-8")).hexdigest()
    material_document_id = f"mat_{digest}"
    return material_document_id, material_document_id


def validate_material_upload_ids(
    *,
    stable_document_id: str,
    stable_internal_document_id: str,
    document_id: str | None,
    internal_document_id: str | None,
) -> tuple[str, str]:
    """校验显式传入的材料文档 ID 与稳定 ID 是否一致。

    Args:
        stable_document_id: 按稳定规则生成的 document ID。
        stable_internal_document_id: 按稳定规则生成的 internal document ID。
        document_id: 外部传入的 document ID。
        internal_document_id: 外部传入的 internal document ID。

    Returns:
        稳定 ID 对。

    Raises:
        ValueError: 显式 ID 与稳定 ID 不一致时抛出。
    """

    normalized_document_id = str(document_id or "").strip()
    normalized_internal_document_id = str(internal_document_id or "").strip()
    if normalized_document_id and normalized_document_id != stable_document_id:
        raise ValueError("显式 document_id 与按 form_type/material_name/fiscal 生成的稳定 document_id 不一致")
    if normalized_internal_document_id and normalized_internal_document_id != stable_internal_document_id:
        raise ValueError(
            "显式 internal_document_id 与按 form_type/material_name/fiscal 生成的稳定 internal_document_id 不一致"
        )
    return stable_document_id, stable_internal_document_id


def resolve_upload_action(
    requested_action: str | None,
    previous_meta: Mapping[str, JsonValue] | None,
) -> str:
    """根据显式动作与现有文档状态解析最终上传动作。

    Args:
        requested_action: 用户显式传入的动作；缺失时为 ``None``。
        previous_meta: 现有源文档 meta；不存在时为 ``None``。

    Returns:
        最终动作字符串，仅可能为 ``create``、``update`` 或 ``delete``。

    Raises:
        ValueError: 显式动作非法时抛出。
    """

    normalized_action = _normalize_optional_upload_action(requested_action)
    if normalized_action is not None:
        return normalized_action
    if previous_meta is None:
        return "create"
    return "update"


def build_cn_filing_ids(
    *,
    ticker: str,
    form_type: str,
    fiscal_year: int,
    fiscal_period: str,
    amended: bool,
) -> tuple[str, str]:
    """生成港 A 股 filing 文档 ID 对。

    Args:
        ticker: 已归一化的 canonical ticker。
        form_type: form type。
        fiscal_year: 财年。
        fiscal_period: 财期。
        amended: 是否修订版。

    Returns:
        ``(document_id, internal_document_id)``。

    Raises:
        ValueError: 参数非法时抛出。
    """

    normalized_ticker = ticker.strip()
    if not normalized_ticker:
        raise ValueError("ticker 不能为空")
    normalized_form = form_type.strip().upper()
    normalized_period = fiscal_period.strip().upper()
    if not normalized_form:
        raise ValueError("form_type 不能为空")
    seed = f"{normalized_ticker}|{normalized_form}|{fiscal_year}|{normalized_period}|{int(amended)}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    internal_document_id = f"cn_{digest}"
    document_id = f"fil_{internal_document_id}"
    return document_id, internal_document_id


def build_sec_filing_ids(
    *,
    ticker: str,
    fiscal_year: int,
    fiscal_period: str,
    amended: bool,
) -> tuple[str, str]:
    """生成美股 filing 文档 ID 对。

    Args:
        ticker: 已归一化的 canonical ticker。
        fiscal_year: 财年。
        fiscal_period: 财期。
        amended: 是否修订版。

    Returns:
        ``(document_id, internal_document_id)``。

    Raises:
        ValueError: 参数非法时抛出。
    """

    normalized_ticker = ticker.strip()
    if not normalized_ticker:
        raise ValueError("ticker 不能为空")
    normalized_period = fiscal_period.strip().upper()
    if not normalized_period:
        raise ValueError("fiscal_period 不能为空")
    seed = f"{normalized_ticker}|{fiscal_year}|{normalized_period}|{int(amended)}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    internal_document_id = f"sec_{digest}"
    document_id = f"fil_{internal_document_id}"
    return document_id, internal_document_id


def normalize_cn_fiscal_period(fiscal_period: str) -> str:
    """标准化港 A 股财期。

    Args:
        fiscal_period: 原始财期。

    Returns:
        标准化财期字符串。

    Raises:
        ValueError: 财期非法时抛出。
    """

    normalized = fiscal_period.strip().upper()
    if normalized not in {"Q1", "Q2", "Q3", "Q4", "FY", "H1"}:
        raise ValueError(f"不支持的 fiscal_period: {fiscal_period}")
    return normalized


def derive_report_kind(fiscal_period: str) -> str:
    """由财期推断报告类型。

    Args:
        fiscal_period: 财期。

    Returns:
        报告类型。

    Raises:
        ValueError: 财期非法时抛出。
    """

    normalized = normalize_cn_fiscal_period(fiscal_period)
    if normalized == "FY":
        return "annual"
    if normalized == "H1":
        return "semi_annual"
    return "quarterly"


def _normalize_optional_upload_action(action: str | None) -> str | None:
    """标准化可选上传动作。

    Args:
        action: 原始动作。

    Returns:
        标准化后的动作；空值返回 ``None``。

    Raises:
        ValueError: 动作不在支持集合时抛出。
    """

    normalized_action = str(action or "").strip().lower()
    if not normalized_action:
        return None
    if normalized_action not in UPLOAD_ACTIONS:
        raise ValueError(f"不支持的 action: {action}")
    return normalized_action


def _normalize_optional_upload_fiscal_period(fiscal_period: str | None) -> str | None:
    """标准化可选上传财期。

    Args:
        fiscal_period: 原始财期。

    Returns:
        去除空白并转大写后的财期；空值返回 ``None``。

    Raises:
        无。
    """

    normalized_period = str(fiscal_period or "").strip().upper()
    if not normalized_period:
        return None
    return normalized_period


def _build_stored_file_entry(
    *,
    asset: _PendingFileAsset,
    file_meta: FileObjectMeta,
    source_kind: SourceKind,
) -> JsonObject:
    """构建已落盘文件条目。

    Args:
        asset: 上传资产。
        file_meta: blob 仓储返回的文件元数据。
        source_kind: filing 或 material 来源类型。

    Returns:
        source meta files 条目。

    Raises:
        ValueError: filing asset 缺少 ``original_filename`` 时抛出。
    """

    entry: JsonObject = {
        "name": asset.name,
        "uri": file_meta.uri,
        "etag": file_meta.etag,
        "last_modified": file_meta.last_modified,
        "size": file_meta.size,
        "content_type": file_meta.content_type,
        "sha256": file_meta.sha256 or asset.sha256,
        "ingested_at": now_iso8601(),
        "source": asset.source,
    }
    if source_kind is SourceKind.FILING:
        entry["original_filename"] = _require_filing_original_filename(asset)
        if asset.derived_from is not None:
            entry["derived_from"] = asset.derived_from
    return entry


def _build_cancelled_result(*, document_id: str, internal_document_id: str) -> UploadOperationResult:
    """构建取消状态上传结果。

    Args:
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。

    Returns:
        取消状态上传结果。

    Raises:
        无。
    """

    return UploadOperationResult(
        status="cancelled",
        document_id=document_id,
        internal_document_id=internal_document_id,
        stored_file_count=0,
        file_events=[],
        payload={
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "skip_reason": "cancelled",
        },
    )


def _is_cancelled(cancellation: CancellationToken | None) -> bool:
    """读取协作式取消状态。

    Args:
        cancellation: 公共取消观察 token；``None`` 表示无取消源。

    Returns:
        已取消返回 ``True``，否则返回 ``False``。

    Raises:
        OSError: 取消检查读取失败时由具体实现抛出。
    """

    return bool(cancellation is not None and cancellation.is_cancelled())


def _text_meta(meta: Mapping[str, JsonValue], key: str) -> str:
    """从 JSON meta 中读取文本字段。

    Args:
        meta: JSON meta。
        key: 字段名。

    Returns:
        去除首尾空白后的文本；非文本返回空字符串。

    Raises:
        无。
    """

    value = meta.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


__all__ = [
    "DOCLING_FILE_SUFFIX",
    "DoclingUploadService",
    "UPLOAD_ACTIONS",
    "UploadFileEventPayload",
    "UploadFileEventType",
    "UploadOperationResult",
    "build_cn_filing_ids",
    "build_material_ids",
    "build_sec_filing_ids",
    "commit_prepared_upload_batch",
    "derive_report_kind",
    "normalize_cn_fiscal_period",
    "resolve_upload_action",
    "rollback_prepared_upload_batch",
    "validate_material_upload_ids",
]
