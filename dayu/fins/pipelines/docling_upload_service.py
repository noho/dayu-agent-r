"""Docling 上传服务。

该模块封装 filing/material 的通用上传流程，保留 OLD 文件校验、Docling
转换、文件事件、create/update/delete/skip/overwrite 与 source document
upsert 语义；仓储读写统一经 ``dayu.fins.storage`` 协议完成。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from dayu.contracts.json_value import JsonValue
from dayu.documents.docling_runtime import (
    DoclingRuntimeInitializationError,
    convert_pdf_bytes_with_docling,
)
from dayu.fins._log import Log
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
from dayu.fins.storage import DocumentBlobRepositoryProtocol, SourceDocumentRepositoryProtocol
from dayu.fins.ticker_normalization import try_normalize_ticker

JsonObject: TypeAlias = dict[str, JsonValue]
DoclingUploadConverter: TypeAlias = Callable[[bytes, str], JsonObject]
UploadCancellationChecker: TypeAlias = Callable[[], bool]

SUPPORTED_UPLOAD_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".htm",
        ".html",
        ".txt",
        ".md",
    }
)
UPLOAD_ACTIONS: Final[frozenset[str]] = frozenset({"create", "update", "delete"})
DOCLING_FILE_SUFFIX: Final[str] = "_docling.json"

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
        file_events: 文件级事件。
        payload: 结果负载。
    """

    status: str
    document_id: str | None
    internal_document_id: str | None
    file_events: list[UploadFileEventPayload]
    payload: JsonObject


@dataclass(frozen=True)
class _PendingFileAsset:
    """待落盘文件资产。"""

    name: str
    data: bytes
    content_type: str | None
    sha256: str
    size: int
    source: str


class DoclingUploadService:
    """Docling 上传服务。"""

    MODULE: Final[str] = "FINS.DOCLING_UPLOAD"

    def __init__(
        self,
        source_repository: SourceDocumentRepositoryProtocol,
        blob_repository: DocumentBlobRepositoryProtocol,
        *,
        convert_with_docling: DoclingUploadConverter | None = None,
    ) -> None:
        """初始化服务。

        Args:
            source_repository: 源文档仓储实现。
            blob_repository: 文档文件对象仓储实现。
            convert_with_docling: 可选 Docling 转换函数。

        Returns:
            无。

        Raises:
            ValueError: 仓储为空时抛出。
        """

        if source_repository is None:
            raise ValueError("source_repository 不能为空")
        if blob_repository is None:
            raise ValueError("blob_repository 不能为空")
        self._source_repository = source_repository
        self._blob_repository = blob_repository
        self._convert_with_docling = convert_with_docling or _convert_bytes_with_docling

    def execute_upload(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        action: str,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        files: list[Path],
        overwrite: bool,
        meta: Mapping[str, JsonValue],
        cancellation_checker: UploadCancellationChecker | None = None,
    ) -> UploadOperationResult:
        """执行上传操作。

        Args:
            ticker: 股票代码。
            source_kind: 文档类型。
            action: 动作类型。
            document_id: 文档 ID。
            internal_document_id: 内部文档 ID。
            form_type: 文档 form type。
            files: 上传文件列表。
            overwrite: 是否强制覆盖。
            meta: 业务元数据字段。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            上传结果对象。

        Raises:
            ValueError: 参数非法时抛出。
            FileNotFoundError: 需要的文件或文档不存在时抛出。
            FileExistsError: create 目标已存在且不可覆盖时抛出。
            RuntimeError: 上传失败时抛出。
            OSError: 仓储读写失败时抛出。
        """

        normalized_action = action.strip().lower()
        if normalized_action not in UPLOAD_ACTIONS:
            raise ValueError(f"不支持的 action: {action}")
        normalized_ticker = _normalize_ticker(ticker)
        if not document_id.strip():
            raise ValueError("document_id 不能为空")
        if not internal_document_id.strip():
            raise ValueError("internal_document_id 不能为空")
        if not form_type.strip():
            raise ValueError("form_type 不能为空")
        if _is_cancelled(cancellation_checker):
            return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)

        if normalized_action == "delete":
            self._delete_source_document(
                ticker=normalized_ticker,
                source_kind=source_kind,
                document_id=document_id,
            )
            return UploadOperationResult(
                status="deleted",
                document_id=document_id,
                internal_document_id=internal_document_id,
                file_events=[],
                payload={
                    "document_id": document_id,
                    "internal_document_id": internal_document_id,
                    "deleted": True,
                },
            )

        validated_files = _validate_source_files(files)
        previous_meta = self._safe_get_document_meta(normalized_ticker, document_id, source_kind)
        if normalized_action == "update" and previous_meta is None and not overwrite:
            raise FileNotFoundError(f"Document not found for update: {document_id}")
        if _is_cancelled(cancellation_checker):
            return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)

        original_assets = self._build_original_assets(validated_files)
        source_fingerprint = _build_upload_source_fingerprint(original_assets)
        if _can_skip_upload(previous_meta, source_fingerprint, overwrite):
            Log.info(
                f"文档已存在且未变更，跳过上传: ticker={normalized_ticker} document_id={document_id}",
                module=self.MODULE,
            )
            skipped_events = _build_skipped_file_events(validated_files)
            return UploadOperationResult(
                status="skipped",
                document_id=document_id,
                internal_document_id=internal_document_id,
                file_events=skipped_events,
                payload={
                    "document_id": document_id,
                    "internal_document_id": internal_document_id,
                    "skip_reason": "already_uploaded",
                },
            )

        pending_assets, conversion_events = self._build_pending_assets(
            validated_files,
            original_assets,
            cancellation_checker=cancellation_checker,
        )
        if _is_cancelled(cancellation_checker):
            return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)
        current_version = _resolve_document_version(previous_meta, source_fingerprint)
        staging_meta = self._build_upsert_meta(
            previous_meta=previous_meta,
            source_fingerprint=source_fingerprint,
            document_version=current_version,
            base_meta=meta,
        )
        result = self._store_upload_assets(
            ticker=normalized_ticker,
            source_kind=source_kind,
            action=normalized_action,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            overwrite=overwrite,
            pending_assets=pending_assets,
            conversion_events=conversion_events,
            previous_meta=previous_meta,
            meta=staging_meta,
            source_fingerprint=source_fingerprint,
            document_version=current_version,
            cancellation_checker=cancellation_checker,
        )
        if result.status == "uploaded":
            Log.verbose(
                (
                    f"Docling 转换与源文档落盘完成: ticker={normalized_ticker} "
                    f"document_id={document_id} files={result.payload.get('uploaded_files')}"
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
        previous_meta: JsonObject | None,
        meta: JsonObject,
        source_fingerprint: str,
        document_version: str,
        cancellation_checker: UploadCancellationChecker | None,
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
            previous_meta: 旧 source meta。
            meta: 本次写入的 source meta。
            source_fingerprint: 本次上传源指纹。
            document_version: 本次文档版本。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            上传操作结果。

        Raises:
            RuntimeError: 未生成主 Docling 文件时抛出。
            OSError: 仓储写入失败时抛出。
        """

        replace_existing = overwrite and previous_meta is not None and action in {"create", "update"}
        token: BatchToken | None = None
        if replace_existing:
            token = self._source_repository.begin_batch(ticker)
        try:
            effective_previous_meta = previous_meta
            upsert_mode = _resolve_upsert_mode(
                action=action,
                previous_meta=previous_meta,
                overwrite=overwrite,
            )
            if replace_existing:
                self._source_repository.reset_source_document(
                    ticker=ticker,
                    document_id=document_id,
                    source_kind=source_kind,
                )
                effective_previous_meta = None
                upsert_mode = "create"

            stored_entries: list[JsonObject] = []
            file_events: list[UploadFileEventPayload] = list(conversion_events)
            handle = self._acknowledge_source_before_blob_write(
                ticker=ticker,
                source_kind=source_kind,
                document_id=document_id,
                internal_document_id=internal_document_id,
                form_type=form_type,
                previous_meta=effective_previous_meta,
                meta=meta,
            )
            for asset in pending_assets:
                if _is_cancelled(cancellation_checker):
                    if token is not None:
                        self._source_repository.rollback_batch(token)
                        token = None
                    return _build_cancelled_result(document_id=document_id, internal_document_id=internal_document_id)
                file_meta = self._blob_repository.store_file(
                    handle=handle,
                    filename=asset.name,
                    data=BytesIO(asset.data),
                    content_type=asset.content_type,
                )
                stored_entries.append(_build_stored_file_entry(asset=asset, file_meta=file_meta))
                file_events.append(
                    UploadFileEventPayload(
                        event_type="file_uploaded",
                        name=asset.name,
                        payload={
                            "source": asset.source,
                            "size": file_meta.size,
                            "content_type": file_meta.content_type,
                        },
                    )
                )

            primary_document = _pick_primary_docling_file(stored_entries)
            if primary_document is None:
                raise RuntimeError("未生成 docling 主文件，无法写入 primary_document")
            self._upsert_source_document(
                upsert_mode=upsert_mode,
                source_kind=source_kind,
                ticker=ticker,
                document_id=document_id,
                internal_document_id=internal_document_id,
                form_type=form_type,
                primary_document=primary_document,
                file_entries=stored_entries,
                meta=meta,
            )
            if token is not None:
                commit_token = token
                token = None
                self._source_repository.commit_batch(commit_token)
            return UploadOperationResult(
                status="uploaded",
                document_id=document_id,
                internal_document_id=internal_document_id,
                file_events=file_events,
                payload={
                    "document_id": document_id,
                    "internal_document_id": internal_document_id,
                    "primary_document": primary_document,
                    "uploaded_files": len(stored_entries),
                    "source_fingerprint": source_fingerprint,
                    "document_version": document_version,
                },
            )
        except Exception:
            if token is not None:
                self._source_repository.rollback_batch(token)
            raise

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

        normalized_ticker = _normalize_ticker(ticker)
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
    ) -> None:
        """删除源文档。

        Args:
            ticker: 股票代码。
            source_kind: 文档来源类型。
            document_id: 文档 ID。

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
            )
        )

    def _acknowledge_source_before_blob_write(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        previous_meta: JsonObject | None,
        meta: JsonObject,
    ) -> SourceHandle:
        """在上传 blob 写入前确认 source repository 已承认该 source。

        Args:
            ticker: 已规范化股票代码。
            source_kind: 文档来源类型。
            document_id: 文档 ID。
            internal_document_id: 内部文档 ID。
            form_type: 文档 form type。
            previous_meta: 旧 source meta；不存在或未完成时必须通过 staging 校验。
            meta: 本次上传 source meta 事实。

        Returns:
            可用于 blob repository 的 source handle。

        Raises:
            FileExistsError: 既有 staging 与本次 source 稳定字段冲突时抛出。
            KeyError: meta 缺少必需溯源字段时抛出。
            ValueError: meta 溯源字段非法时抛出。
            OSError: 仓储写入失败时抛出。
        """

        if previous_meta is None or not bool(previous_meta.get("ingest_complete", False)):
            staging_meta = dict(meta)
            staging_meta["ingest_complete"] = False
            return self._source_repository.stage_source_document(
                SourceDocumentUpsertRequest(
                    ticker=ticker,
                    document_id=document_id,
                    internal_document_id=internal_document_id,
                    form_type=form_type,
                    primary_document=None,
                    file_entries=[],
                    meta=staging_meta,
                ),
                source_kind=source_kind,
            )
        return SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind.value,
        )

    def _build_original_assets(self, files: list[Path]) -> list[_PendingFileAsset]:
        """构建原始上传文件资产列表。

        Args:
            files: 源文件列表。

        Returns:
            仅包含原始上传文件的资产列表。

        Raises:
            FileNotFoundError: 源文件不存在时抛出。
            OSError: 源文件读取失败时抛出。
        """

        assets: list[_PendingFileAsset] = []
        for file_path in files:
            raw_data = file_path.read_bytes()
            raw_sha256 = hashlib.sha256(raw_data).hexdigest()
            raw_content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            assets.append(
                _PendingFileAsset(
                    name=file_path.name,
                    data=raw_data,
                    content_type=raw_content_type,
                    sha256=raw_sha256,
                    size=len(raw_data),
                    source="original",
                )
            )
        return assets

    def _build_pending_assets(
        self,
        files: list[Path],
        original_assets: list[_PendingFileAsset],
        *,
        cancellation_checker: UploadCancellationChecker | None,
    ) -> tuple[list[_PendingFileAsset], list[UploadFileEventPayload]]:
        """构建待上传资产列表与转换阶段事件。

        Args:
            files: 源文件列表。
            original_assets: 已读取完成的原始文件资产列表。
            cancellation_checker: 可选协作式取消检查器。

        Returns:
            待上传资产列表与转换阶段事件列表。

        Raises:
            RuntimeError: Docling 转换失败时抛出。
            ValueError: ``files`` 与 ``original_assets`` 长度不一致时抛出。
        """

        if len(files) != len(original_assets):
            raise ValueError("files 与 original_assets 数量不一致")

        assets = list(original_assets)
        conversion_events: list[UploadFileEventPayload] = []
        for file_path, original_asset in zip(files, original_assets):
            if _is_cancelled(cancellation_checker):
                break
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
            docling_payload = self._convert_with_docling(original_asset.data, file_path.name)
            docling_data = json.dumps(docling_payload, ensure_ascii=False, indent=2).encode("utf-8")
            docling_name = f"{file_path.stem}{DOCLING_FILE_SUFFIX}"
            docling_sha256 = hashlib.sha256(docling_data).hexdigest()
            assets.append(
                _PendingFileAsset(
                    name=docling_name,
                    data=docling_data,
                    content_type="application/json",
                    sha256=docling_sha256,
                    size=len(docling_data),
                    source="docling",
                )
            )
        return assets, conversion_events

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
        merged = dict(base_meta)
        merged["updated_at"] = now
        merged["first_ingested_at"] = previous_first_ingested_at or now
        merged["document_version"] = document_version
        merged["source_fingerprint"] = source_fingerprint
        merged["ingest_complete"] = True
        merged["source_provider"] = FinsSourceProvider.USER_UPLOAD.to_storage_value()
        merged["is_deleted"] = False
        merged["deleted_at"] = None
        return merged

    def _upsert_source_document(
        self,
        *,
        upsert_mode: str,
        source_kind: SourceKind,
        ticker: str,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        primary_document: str,
        file_entries: list[JsonObject],
        meta: JsonObject,
    ) -> None:
        """执行仓储 upsert。

        Args:
            upsert_mode: 写入模式。
            source_kind: 来源类型。
            ticker: 股票代码。
            document_id: 文档 ID。
            internal_document_id: 内部文档 ID。
            form_type: 表单类型。
            primary_document: 主文件名。
            file_entries: 文件条目列表。
            meta: 元数据字典。

        Returns:
            无。

        Raises:
            RuntimeError: upsert 失败时抛出。
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
        if upsert_mode == "create":
            self._source_repository.create_source_document(
                request,
                source_kind=source_kind,
            )
            return
        self._source_repository.update_source_document(
            request,
            source_kind=source_kind,
        )


def _convert_bytes_with_docling(raw_data: bytes, stream_name: str) -> JsonObject:
    """使用 Docling 将字节流转换为结构化 JSON。

    Args:
        raw_data: 文件原始字节内容。
        stream_name: 流名称。

    Returns:
        Docling 导出的结构化字典。

    Raises:
        DoclingRuntimeInitializationError: Docling 装配失败时抛出。
        RuntimeError: Docling 转换失败或导出结构非法时抛出。
    """

    try:
        result = convert_pdf_bytes_with_docling(
            raw_data,
            stream_name=stream_name,
            do_ocr=True,
            do_table_structure=True,
            table_mode="accurate",
            do_cell_matching=True,
        )
    except DoclingRuntimeInitializationError:
        raise
    except Exception as exc:  # pragma: no cover - 第三方转换异常兜底
        raise RuntimeError(f"Docling 转换失败: {stream_name}") from exc
    payload = cast(JsonValue, result.document.export_to_dict())
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Docling 导出结果非法: {stream_name}")
    return dict(payload)


def _validate_source_files(files: list[Path]) -> list[Path]:
    """校验上传文件列表。

    Args:
        files: 原始文件列表。

    Returns:
        标准化后的文件路径列表。

    Raises:
        ValueError: 文件列表为空或扩展名不支持时抛出。
        FileNotFoundError: 文件不存在时抛出。
    """

    if not files:
        raise ValueError("上传文件不能为空")
    normalized: list[Path] = []
    for file_path in files:
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"上传文件不存在: {file_path}")
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise ValueError(f"不支持的文件类型: {file_path.name}")
        normalized.append(file_path)
    return normalized


def _pick_primary_docling_file(file_entries: list[JsonObject]) -> str | None:
    """从文件条目中选择主 Docling 文件。

    Args:
        file_entries: 文件条目列表。

    Returns:
        主文件名；不存在返回 ``None``。

    Raises:
        无。
    """

    for entry in file_entries:
        name = str(entry.get("name", "")).strip()
        if name.endswith(DOCLING_FILE_SUFFIX):
            return name
    return None


def _can_skip_upload(
    previous_meta: Mapping[str, JsonValue] | None,
    source_fingerprint: str,
    overwrite: bool,
) -> bool:
    """判断是否可跳过上传。

    Args:
        previous_meta: 旧元数据。
        source_fingerprint: 本次源指纹。
        overwrite: 是否覆盖。

    Returns:
        满足跳过条件时返回 ``True``。

    Raises:
        无。
    """

    if overwrite or previous_meta is None:
        return False
    if not bool(previous_meta.get("ingest_complete", False)):
        return False
    previous_fingerprint = _text_meta(previous_meta, "source_fingerprint")
    return bool(previous_fingerprint) and previous_fingerprint == source_fingerprint


def _build_upload_source_fingerprint(assets: list[_PendingFileAsset]) -> str:
    """构建上传源指纹。

    Args:
        assets: 待上传资产列表。

    Returns:
        指纹字符串。

    Raises:
        无。
    """

    payload: list[JsonObject] = [
        {
            "name": asset.name,
            "sha256": asset.sha256,
            "size": asset.size,
            "source": asset.source,
        }
        for asset in sorted(assets, key=lambda item: item.name)
    ]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _resolve_document_version(previous_meta: Mapping[str, JsonValue] | None, source_fingerprint: str) -> str:
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
    previous_fingerprint = _text_meta(previous_meta, "source_fingerprint")
    if previous_fingerprint and previous_fingerprint != source_fingerprint:
        return _increment_document_version(previous_version)
    return previous_version


def _resolve_upsert_mode(
    action: str,
    previous_meta: Mapping[str, JsonValue] | None,
    overwrite: bool,
) -> str:
    """解析写入模式。

    Args:
        action: 上传动作。
        previous_meta: 旧元数据；不存在时为 ``None``。
        overwrite: 是否启用覆盖。

    Returns:
        ``"create"`` 或 ``"update"``。

    Raises:
        FileNotFoundError: update 目标不存在且未启用覆盖时抛出。
        FileExistsError: create 目标已存在且未启用覆盖时抛出。
    """

    if action == "update":
        if previous_meta is None:
            if overwrite:
                return "create"
            raise FileNotFoundError("更新目标不存在")
        return "update"
    if previous_meta is None:
        return "create"
    if overwrite:
        return "update"
    raise FileExistsError("创建目标已存在")


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


def _normalize_ticker(ticker: str) -> str:
    """标准化 ticker。

    Args:
        ticker: 原始 ticker。

    Returns:
        标准化 ticker。

    Raises:
        ValueError: ticker 为空时抛出。
    """

    normalized_source = try_normalize_ticker(ticker)
    if normalized_source is not None:
        return normalized_source.canonical
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("ticker 不能为空")
    return normalized


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


def _build_stored_file_entry(*, asset: _PendingFileAsset, file_meta: FileObjectMeta) -> JsonObject:
    """构建已落盘文件条目。

    Args:
        asset: 上传资产。
        file_meta: blob 仓储返回的文件元数据。

    Returns:
        source meta files 条目。

    Raises:
        无。
    """

    return {
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
        file_events=[],
        payload={
            "document_id": document_id,
            "internal_document_id": internal_document_id,
            "skip_reason": "cancelled",
        },
    )


def _is_cancelled(cancellation_checker: UploadCancellationChecker | None) -> bool:
    """读取协作式取消状态。

    Args:
        cancellation_checker: 可选取消检查器。

    Returns:
        已取消返回 ``True``，否则返回 ``False``。

    Raises:
        OSError: 取消检查读取失败时由具体实现抛出。
    """

    return bool(cancellation_checker is not None and cancellation_checker())


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
    "DoclingUploadConverter",
    "DoclingUploadService",
    "SUPPORTED_UPLOAD_SUFFIXES",
    "UPLOAD_ACTIONS",
    "UploadFileEventPayload",
    "UploadFileEventType",
    "UploadOperationResult",
    "build_cn_filing_ids",
    "build_material_ids",
    "build_sec_filing_ids",
    "derive_report_kind",
    "normalize_cn_fiscal_period",
    "resolve_upload_action",
    "validate_material_upload_ids",
]
