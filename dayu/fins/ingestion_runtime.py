"""Fins 下载、预处理与上传运行时基础能力。

本模块只承载 Fins 自有 ingestion job 的 typed 请求、结果摘要、持久化
job record、文件系统 job store、download / preprocess / upload job foundation
与运行时入口。它不实现真实网络下载、真实 upload workflow、Host wait
adapter、tool provider 或 CLI。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import uuid
from collections.abc import AsyncGenerator, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Lock, Thread
from typing import Final, Protocol, assert_never, cast, get_args

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.base import DocumentProcessor
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins import ticker_normalization
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_FAILURE,
    FINS_RESULT_EXIT_SUCCESS,
    FinsDownloadPublicDocument,
    FinsDownloadPublicSummary,
    FinsErrorKind,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsOperationKind,
    FinsProgress,
    FinsPublicFailure,
    FinsPublicFailureKind,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.direct_events import ValidatedFinsEventStream
from dayu.fins.download_contract import (
    FINS_DOWNLOAD_PUBLIC_MAX_DOCUMENT_ROWS,
    FinsDownloadDateRange,
    FinsDownloadDocumentDisposition,
    FinsDownloadDocumentResult,
    FinsDownloadEffectiveFilters,
    FinsDownloadProviderError,
    FinsDownloadRequest,
    FinsDownloadResultSummary as _FinsDownloadResultSummary,
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
    FinsDownloadTransportCategory,
)
from dayu.fins.direct_event_text import (
    direct_download_no_source_documents_message,
    direct_failure_message,
    direct_preprocess_no_requested_documents_message,
    direct_progress_message,
    direct_result_title,
    direct_upload_failed_status_message,
    direct_upload_runtime_unavailable_message,
)
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentMeta,
    DownloadRejectionEntry,
    FinsIngestMethod,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedHandle,
    ProcessedUpdateRequest,
    RejectedFilingArtifactUpsertRequest,
    SourceDocumentUpsertRequest,
    SourceFileEntry,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_events import (
    FinsIngestionJobEventAppend,
    FinsIngestionJobEventRecord,
    FinsIngestionJobEventType,
    validate_bounded_job_event_payload,
)
from dayu.fins.ingestion.observation_handle import (
    FINS_OBSERVATION_HANDLE_ID_PREFIX,
    FinsObservationHandle,
    FinsObservationSnapshot,
    FinsObservationStatus,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.ticker_normalization import Exchange as NormalizedTickerExchange
from dayu.fins.ticker_normalization import Market as NormalizedTickerMarket
from dayu.fins.ticker_normalization import NormalizedTicker
from dayu.runtime.filelock import file_lock

_DOWNLOAD_INGEST_METHOD: Final[FinsIngestMethod] = FinsIngestMethod.DOWNLOAD
_DOWNLOAD_REJECTION_CLASSIFICATION_VERSION: Final[str] = "fins-download-runtime-v1"
_JOB_ID_PREFIX: Final[str] = "finsjob_"
_JOB_EVENT_FILE_SUFFIX: Final[str] = ".events.jsonl"
_JOB_FILE_SUFFIX: Final[str] = ".json"
_LOCK_FILE_NAME: Final[str] = ".store.lock"
_JOBS_DIR_PARTS: Final[tuple[str, str, str]] = (".dayu", "fins_ingestion", "jobs")
_JOB_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^finsjob_[0-9a-f]{32}$")
_MAX_SUMMARY_JSON_CHARS: Final[int] = 4096
_MAX_TEXT_CHARS: Final[int] = 240
_MAX_TUPLE_ITEMS: Final[int] = 100
_MAX_PREPROCESS_DOCUMENTS: Final[int] = 50
_EMPTY_SUMMARY: Final[dict[str, JsonValue]] = {}
_ROLLBACK_FAILURE_NOTE_PREFIX: Final[str] = "rollback_batch failed; recovery evidence retained"
_NORMALIZED_MARKET_VALUES: Final[frozenset[NormalizedTickerMarket]] = frozenset(
    cast(tuple[NormalizedTickerMarket, ...], get_args(NormalizedTickerMarket))
)
_NORMALIZED_EXCHANGE_VALUES: Final[frozenset[NormalizedTickerExchange]] = frozenset(
    cast(tuple[NormalizedTickerExchange, ...], get_args(NormalizedTickerExchange))
)
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_KEY_JOB_ID: Final[str] = "job_id"
_KEY_OPERATION_KIND: Final[str] = "operation_kind"
_KEY_NORMALIZED_TICKER: Final[str] = "normalized_ticker"
_KEY_MARKET: Final[str] = "market"
_KEY_EXCHANGE: Final[str] = "exchange"
_KEY_SOURCE: Final[str] = "source"
_KEY_SOURCE_KIND: Final[str] = "source_kind"
_KEY_STATUS: Final[str] = "status"
_KEY_CREATED_AT: Final[str] = "created_at"
_KEY_UPDATED_AT: Final[str] = "updated_at"
_KEY_STARTED_AT: Final[str] = "started_at"
_KEY_FINISHED_AT: Final[str] = "finished_at"
_KEY_REQUEST_SUMMARY: Final[str] = "request_summary"
_KEY_RESULT_SUMMARY: Final[str] = "result_summary"
_KEY_FAILURE_SUMMARY: Final[str] = "failure_summary"
_KEY_CANCELLATION_REQUESTED: Final[str] = "cancellation_requested"
_KEY_SEQUENCE: Final[str] = "sequence"
_KEY_EVENT_TYPE: Final[str] = "event_type"
_KEY_SOURCE_EVENT_TYPE: Final[str] = "source_event_type"
_KEY_DOCUMENT_ID: Final[str] = "document_id"
_KEY_MESSAGE: Final[str] = "message"
_KEY_PAYLOAD: Final[str] = "payload"
_KEY_EMITTED_AT: Final[str] = "emitted_at"


def _rollback_batch_before_commit(
    batching_repository: BatchingRepositoryProtocol,
    batch: BatchToken,
) -> None:
    """回滚 commit 前 batch，并在双失败时保留 operation 主异常。

    Args:
        batching_repository: batch lifecycle 唯一仓储。
        batch: 尚未进入 commit 的 open batch capability。

    Returns:
        rollback 成功时不返回业务值。

    Raises:
        BaseException: rollback 失败且已有 operation/cancellation 异常时，重新抛出
            原异常并把 rollback 异常设为 cause；没有原异常时抛出 rollback 异常。
    """

    operation_error = sys.exception()
    try:
        batching_repository.rollback_batch(batch)
    except BaseException as rollback_error:
        if operation_error is not None:
            operation_error.add_note(f"{_ROLLBACK_FAILURE_NOTE_PREFIX}: {rollback_error}")
            raise operation_error from rollback_error
        raise


_JOB_EVENT_SIDECAR_KIND: Final[str] = "fins_ingestion_job_event"
_JOB_EVENT_SIDECAR_ROW_SKIPPED_LOG_EVENT: Final[str] = "fins.ingestion.job_event_sidecar_row_skipped"
_JOB_EVENT_SIDECAR_ROW_SKIPPED_SUMMARY: Final[str] = "malformed_or_invalid_event_row"
_DEFAULT_JOB_EVENT_READ_LIMIT: Final[int] = 100
_MAX_JOB_EVENT_READ_LIMIT: Final[int] = 1000
_OBSERVATION_RETRY_AFTER_SECONDS: Final[float] = 1.0
_PROGRESS_DOWNLOAD_STARTED: Final[str] = "download.started"
_PROGRESS_DOWNLOAD_PREPARING: Final[str] = "download.preparing"
_PROGRESS_DOWNLOAD_FILE_STARTED: Final[str] = "download.file_started"
_PROGRESS_DOWNLOAD_FILE_COMPLETED: Final[str] = "download.file_completed"
_PROGRESS_DOWNLOAD_FILE_SKIPPED: Final[str] = "download.file_skipped"
_PROGRESS_DOWNLOAD_FILE_FAILED: Final[str] = "download.file_failed"
_PROGRESS_DOWNLOAD_CONVERSION_STARTED: Final[str] = "download.conversion_started"
_PROGRESS_DOWNLOAD_COMPLETED: Final[str] = "download.completed"
_PROGRESS_DOWNLOAD_COMPLETED_WITH_FAILURES: Final[str] = "download.completed_with_failures"
_PROGRESS_UPLOAD_PREPARING: Final[str] = "upload.preparing"
_PROGRESS_UPLOAD_STARTED: Final[str] = "upload.started"
_PROGRESS_UPLOAD_COMPLETED: Final[str] = "upload.completed"
_PROGRESS_UPLOAD_COMPLETED_WITH_FAILURES: Final[str] = "upload.completed_with_failures"
_PROGRESS_PREPROCESS_PREPARING: Final[str] = "preprocess.preparing"
_PROGRESS_PREPROCESS_SELECTED: Final[str] = "preprocess.selected"
_PROGRESS_PREPROCESS_DOCUMENT_STARTED: Final[str] = "preprocess.document_started"
_PROGRESS_PREPROCESS_DOCUMENT_PROCESSED: Final[str] = "preprocess.document_processed"
_PROGRESS_PREPROCESS_DOCUMENT_SKIPPED: Final[str] = "preprocess.document_skipped"
_PROGRESS_PREPROCESS_DOCUMENT_FAILED: Final[str] = "preprocess.document_failed"
_PROGRESS_PREPROCESS_DOCUMENT_NOT_SUPPORTED: Final[str] = "preprocess.document_not_supported"
_PROGRESS_PREPROCESS_COMPLETED: Final[str] = "preprocess.completed"
_PAYLOAD_TICKER: Final[str] = "ticker"
_PAYLOAD_MARKET: Final[str] = "market"
_PAYLOAD_SOURCE: Final[str] = "source"
_PAYLOAD_SOURCE_KIND: Final[str] = "source_kind"
_PAYLOAD_FORM_TYPES: Final[str] = "form_types"
_PAYLOAD_ACTION: Final[str] = "action"
_PAYLOAD_FILE_COUNT: Final[str] = "file_count"
_PAYLOAD_SELECTED_COUNT: Final[str] = "selected_count"
_PAYLOAD_PROCESSED_COUNT: Final[str] = "processed_count"
_PAYLOAD_SKIPPED_COUNT: Final[str] = "skipped_count"
_PAYLOAD_FAILED_COUNT: Final[str] = "failed_count"
_PAYLOAD_DISCOVERED_COUNT: Final[str] = "discovered_count"
_PAYLOAD_DOWNLOADED_COUNT: Final[str] = "downloaded_count"
_PAYLOAD_REJECTED_COUNT: Final[str] = "rejected_count"
_PAYLOAD_WRITTEN_DOCUMENT_COUNT: Final[str] = "written_document_count"
_PAYLOAD_NOT_SUPPORTED_COUNT: Final[str] = "not_supported_count"
_PAYLOAD_DOCUMENT_INDEX: Final[str] = "document_index"
_PAYLOAD_DOCUMENT_TOTAL: Final[str] = "document_total"
_PAYLOAD_UPLOAD_STATUS: Final[str] = "upload_status"
_PAYLOAD_FILE_NAME: Final[str] = "file_name"
_DIRECT_EVENT_QUEUE_MAX_SIZE: Final[int] = 32
_DIRECT_QUEUE_GET_TIMEOUT_SECONDS: Final[float] = 0.05
_DIRECT_QUEUE_PUT_TIMEOUT_SECONDS: Final[float] = 0.05


class FinsIngestionOperationKind(str, Enum):
    """Fins ingestion job 操作类型。"""

    DOWNLOAD = "download"
    PREPROCESS = "preprocess"
    UPLOAD = "upload"


class FinsIngestionJobStatus(str, Enum):
    """Fins ingestion job 状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FinsPreprocessResultStatus(str, Enum):
    """预处理结果的业务状态。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


_TERMINAL_STATUSES = frozenset(
    {
        FinsIngestionJobStatus.SUCCEEDED,
        FinsIngestionJobStatus.FAILED,
        FinsIngestionJobStatus.CANCELLED,
    }
)

_TERMINAL_OBSERVATION_STATUSES: Final[frozenset[FinsObservationStatus]] = frozenset(
    {
        FinsObservationStatus.SUCCEEDED,
        FinsObservationStatus.FAILED,
        FinsObservationStatus.CANCELLED,
        FinsObservationStatus.LOST,
    }
)


class _PreprocessNotSupportedError(RuntimeError):
    """源文档没有可用预处理器。"""


class _UnsupportedDownloadSourceError(RuntimeError):
    """没有可用下载 adapter。"""


class FinsIngestionStartCancelledError(RuntimeError):
    """启动 ingestion job 前观察到调用方取消。"""


@dataclass(frozen=True)
class FinsDownloadedFile:
    """下载 adapter 返回的单个业务文件。

    Attributes:
        filename: 文件名，不含路径。
        content: 文件字节内容；只用于落盘，不进入 job record。
        content_type: 可选 MIME 类型。
        metadata: 文件级业务元数据。
    """

    filename: str
    content: bytes
    content_type: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FinsDownloadedSourceDocument:
    """下载 adapter 返回的可进入 source 仓储的文档。

    Attributes:
        source_kind: 源文档类别。
        document_id: 业务文档 ID。
        internal_document_id: 来源系统内部文档 ID。
        form_type: 表单类型。
        primary_document: 主文件名。
        meta: 业务元数据，不含 provider raw payload。
        files: 需要落盘的文件列表。
    """

    source_kind: SourceKind
    document_id: str
    internal_document_id: str
    form_type: str | None
    primary_document: str
    meta: dict[str, JsonValue]
    files: tuple[FinsDownloadedFile, ...]


@dataclass(frozen=True)
class FinsRejectedFilingDownloadArtifact:
    """下载 adapter 返回的 rejected filing artifact。

    Attributes:
        document_id: rejected artifact 文档 ID。
        internal_document_id: 来源系统内部文档 ID。
        accession_number: filing accession number 或等价来源编号。
        company_id: 公司业务 ID。
        form_type: 表单类型。
        filing_date: 披露日期。
        report_date: 报告期日期。
        primary_document: 来源主文件名。
        selected_primary_document: 被策略选中的主文件名。
        rejection_reason: 拒绝原因。
        rejection_category: 拒绝分类。
        source_fingerprint: 来源指纹。
        files: 需要作为 rejected artifact 保存的文件。
        fiscal_year: 可选会计年度。
        fiscal_period: 可选会计期间。
        report_kind: 可选报告类型。
        amended: 是否修正文件。
        has_xbrl: 是否包含 XBRL。
    """

    document_id: str
    internal_document_id: str
    accession_number: str
    company_id: str
    form_type: str
    filing_date: str
    report_date: str | None
    primary_document: str
    selected_primary_document: str
    rejection_reason: str
    rejection_category: str
    source_fingerprint: str
    files: tuple[FinsDownloadedFile, ...] = ()
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    report_kind: str | None = None
    amended: bool = False
    has_xbrl: bool | None = None


@dataclass(frozen=True)
class FinsDownloadProgressEvent:
    """source-specific 下载 adapter 回传给 runtime 的业务进度。

    Attributes:
        stage: runtime 可直接投影的下载阶段标签。
        message: 用户可读进度说明。
        document_id: 可选业务文档 ID。
        file_name: 可选文件名；存在时优先作为 CLI 文档短标签展示。
        payload: 额外有界业务摘要，不得包含本地路径或 provider raw payload。
    """

    stage: str
    message: str
    document_id: str | None = None
    file_name: str | None = None
    payload: dict[str, JsonValue] = field(default_factory=dict)


FinsDownloadProgressSink = Callable[[FinsDownloadProgressEvent], None]
"""下载 adapter 到 runtime 的同步进度回调。"""


@dataclass(frozen=True)
class FinsSourceDownloadAdapterRequest:
    """传给 source-specific 下载 adapter 的请求。

    Attributes:
        normalized_ticker: 已由公共 API 归一化的 ticker。
        source: 由 ticker 市场解析的来源。
        form_types: 表单过滤条件。
        date_range: 已展开的 inclusive 日期边界与显式性。
        overwrite_existing: 是否允许覆盖已存在源文档。
        rebuild_local_artifacts: 是否只基于本地 source 重建下载产物。
        cancellation_checker: runtime 提供的协作式取消检查器。
        progress_sink: 可选同步进度回调；adapter 仅用它上报业务进度，不负责 CLI 渲染。
    """

    normalized_ticker: NormalizedTicker
    source: FinsDownloadSource
    form_types: tuple[str, ...]
    date_range: FinsDownloadDateRange
    overwrite_existing: bool
    rebuild_local_artifacts: bool
    cancellation_checker: FinsJobCancellationChecker
    progress_sink: FinsDownloadProgressSink | None = None


@dataclass(frozen=True)
class FinsSourceDownloadAdapterResult:
    """source-specific 下载 adapter 返回值。

    Attributes:
        discovered_count: 来源侧发现的候选文档数量。
        documents: 可写入 source 仓储的文档。
        rejected_artifacts: 需要保存为 rejected filing artifact 的文档。
        failed_count: 来源侧业务失败候选数量。
        persisted_summary: adapter 已通过仓储完成持久化时返回的下载摘要；返回该
            字段表示 adapter 对 source 文件、rejected artifact 以及必要的
            processed reprocess 标记等仓储副作用负责，runtime 只记录摘要。
    """

    discovered_count: int
    documents: tuple[FinsDownloadedSourceDocument, ...] = ()
    rejected_artifacts: tuple[FinsRejectedFilingDownloadArtifact, ...] = ()
    failed_count: int = 0
    persisted_summary: _FinsDownloadResultSummary | None = None


class FinsSourceDownloadAdapter(Protocol):
    """Fins source-specific 下载 adapter 协议。"""

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """下载指定来源的源文档。

        Args:
            request: 已归一化的下载请求。

        Returns:
            业务可读的下载结果；不得包含 provider raw payload。

        Raises:
            RuntimeError: 来源侧下载失败时抛出。
            ValueError: adapter 返回业务字段非法时抛出。
        """
        ...


@dataclass(frozen=True)
class FinsPreprocessRequest:
    """预处理任务请求。

    Attributes:
        ticker: 用户提供的 ticker 文本，运行时会先调用公共 ticker 归一化 API。
        source_kind: 要处理的源文档类型。
        document_ids: 可选源文档 ID 列表；空元组表示由后续 pipeline 选择。
        form_types: 可选财报表单过滤条件。
        rebuild_processed: 是否允许重建已有 processed 产物。
    """

    ticker: str
    source_kind: SourceKind = SourceKind.FILING
    document_ids: tuple[str, ...] = ()
    form_types: tuple[str, ...] = ()
    rebuild_processed: bool = False


_UPLOAD_ACTION_AUTO: Final[str] = "auto"
_UPLOAD_ACTION_CREATE: Final[str] = "create"
_UPLOAD_ACTION_UPDATE: Final[str] = "update"
_UPLOAD_ACTION_DELETE: Final[str] = "delete"
_UPLOAD_ACTION_VALUES: Final[frozenset[str]] = frozenset(
    {
        _UPLOAD_ACTION_AUTO,
        _UPLOAD_ACTION_CREATE,
        _UPLOAD_ACTION_UPDATE,
        _UPLOAD_ACTION_DELETE,
    }
)
_UPLOAD_RESULT_STATUS_FAILED: Final[str] = "failed"
_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE: Final[str] = (
    "不支持的上传运行时 (unsupported upload runtime): production upload runner 尚未装配"
)


@dataclass(frozen=True)
class FinsUploadFilingRequest:
    """财报 filing 上传任务请求。

    Attributes:
        ticker: 用户提供的 ticker 文本，运行时会先调用公共 ticker 归一化 API。
        source_kind: 源文档类别；filing 上传必须为 ``SourceKind.FILING``。
        action: 上传动作，允许 ``auto``、``create``、``update`` 或 ``delete``。
        files: 待上传文件路径；Slice 1 只保存文件数量摘要，不读取文件。
        fiscal_year: 可选会计年度。
        fiscal_period: 可选会计期间。
        amended: 是否为修正 filing。
        filing_date: 可选披露日期。
        report_date: 可选报告期日期。
        company_name: 可选公司名称。
        ticker_aliases: 可选 ticker 别名。
        overwrite: 是否覆盖已有 source document。
    """

    ticker: str
    source_kind: SourceKind = SourceKind.FILING
    action: str = _UPLOAD_ACTION_AUTO
    files: tuple[Path, ...] = ()
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    amended: bool = False
    filing_date: str | None = None
    report_date: str | None = None
    company_name: str | None = None
    ticker_aliases: tuple[str, ...] = ()
    overwrite: bool = False


@dataclass(frozen=True)
class FinsUploadMaterialRequest:
    """财报 material 上传任务请求。

    Attributes:
        ticker: 用户提供的 ticker 文本，运行时会先调用公共 ticker 归一化 API。
        source_kind: 源文档类别；material 上传必须为 ``SourceKind.MATERIAL``。
        action: 上传动作，允许 ``auto``、``create``、``update`` 或 ``delete``。
        files: 待上传文件路径；Slice 1 只保存文件数量摘要，不读取文件。
        form_type: 可选材料表单类型。
        material_name: 可选材料名称。
        document_id: 可选业务文档 ID。
        internal_document_id: 可选来源内部文档 ID。
        fiscal_year: 可选会计年度。
        fiscal_period: 可选会计期间。
        amended: 是否为修正材料。
        filing_date: 可选披露日期。
        report_date: 可选报告期日期。
        company_name: 可选公司名称。
        ticker_aliases: 可选 ticker 别名。
        overwrite: 是否覆盖已有 source document。
    """

    ticker: str
    source_kind: SourceKind = SourceKind.MATERIAL
    action: str = _UPLOAD_ACTION_AUTO
    files: tuple[Path, ...] = ()
    form_type: str | None = None
    material_name: str | None = None
    document_id: str | None = None
    internal_document_id: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    amended: bool = False
    filing_date: str | None = None
    report_date: str | None = None
    company_name: str | None = None
    ticker_aliases: tuple[str, ...] = ()
    overwrite: bool = False


FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest


@dataclass(frozen=True)
class FinsPreprocessResultSummary:
    """预处理任务结果摘要。

    Attributes:
        selected_count: 被选择处理的源文档数量。
        processed_count: 处理成功数量。
        skipped_count: 跳过数量。
        not_supported_count: 无可用处理器数量。
        failed_count: 失败数量。
        processed_document_ids: 已写入的 processed 文档 ID。
        skipped_document_ids: 因已有产物等原因跳过的源文档 ID。
        failed_document_ids: 处理失败的源文档 ID。
        not_supported_document_ids: 没有可用处理器的源文档 ID。
    """

    selected_count: int = 0
    processed_count: int = 0
    skipped_count: int = 0
    not_supported_count: int = 0
    failed_count: int = 0
    processed_document_ids: tuple[str, ...] = ()
    skipped_document_ids: tuple[str, ...] = ()
    failed_document_ids: tuple[str, ...] = ()
    not_supported_document_ids: tuple[str, ...] = ()

    def result_status(self) -> FinsPreprocessResultStatus:
        """返回预处理摘要对应的业务状态。

        Args:
            无。

        Returns:
            预处理成功或失败状态。

        Raises:
            ValueError: 计数字段为负数、分类计数超过选择数量或明细数量与计数不一致时抛出。
        """

        _bounded_preprocess_summary(self)
        if self.processed_count > 0:
            return FinsPreprocessResultStatus.SUCCEEDED
        if self.selected_count == 0 or self.failed_count > 0 or self.not_supported_count > 0:
            return FinsPreprocessResultStatus.FAILED
        if self.skipped_count > 0:
            return FinsPreprocessResultStatus.SUCCEEDED
        return FinsPreprocessResultStatus.SUCCEEDED

    def to_json_summary(self) -> dict[str, JsonValue]:
        """转换为 JSON-compatible 摘要。

        Args:
            无。

        Returns:
            只包含计数和 processed 文档 ID 的 JSON-compatible 字典。

        Raises:
            ValueError: 文档 ID 数量或长度超过 job record 边界时抛出。
        """

        bounded = _bounded_preprocess_summary(self)
        return {
            "selected_count": bounded.selected_count,
            "processed_count": bounded.processed_count,
            "skipped_count": bounded.skipped_count,
            "not_supported_count": bounded.not_supported_count,
            "failed_count": bounded.failed_count,
            "processed_document_ids": list(
                _bounded_text_tuple(
                    bounded.processed_document_ids,
                    "processed_document_ids",
                    reject_path_separators=False,
                )
            ),
            "skipped_document_ids": list(
                _bounded_text_tuple(
                    bounded.skipped_document_ids,
                    "skipped_document_ids",
                    reject_path_separators=False,
                )
            ),
            "failed_document_ids": list(
                _bounded_text_tuple(
                    bounded.failed_document_ids,
                    "failed_document_ids",
                    reject_path_separators=False,
                )
            ),
            "not_supported_document_ids": list(
                _bounded_text_tuple(
                    bounded.not_supported_document_ids,
                    "not_supported_document_ids",
                    reject_path_separators=False,
                )
            ),
        }


@dataclass(frozen=True)
class FinsUploadPipelineResult:
    """production upload pipeline 返回给 runtime 的 typed 结果。

    Attributes:
        status: 上传业务状态，pipeline 必须显式提供。
        document_id: 可选业务文档 ID。
        internal_document_id: 可选来源内部文档 ID。
        primary_document: 可选主文件名。
        deleted: 可选删除动作结果；缺失表示 pipeline 未声明。
        skip_reason: 可选跳过原因。
        document_version: 可选文档版本。
        source_fingerprint: 可选来源指纹。
    """

    status: str
    document_id: str | None = None
    internal_document_id: str | None = None
    primary_document: str | None = None
    deleted: bool | None = None
    skip_reason: str | None = None
    document_version: str | None = None
    source_fingerprint: str | None = None

    @classmethod
    def from_pipeline_json(cls, result: Mapping[str, JsonValue]) -> "FinsUploadPipelineResult":
        """从 pipeline JSON 结果构造 typed upload result。

        Args:
            result: pipeline 上传完成事件中的 JSON result。

        Returns:
            已校验的 typed upload result。

        Raises:
            ValueError: 必填字段缺失、字段类型非法或文本字段为空时抛出。
        """

        return cls(
            status=_required_upload_result_text(result, "status"),
            document_id=_optional_upload_result_text(result, "document_id"),
            internal_document_id=_optional_upload_result_text(result, "internal_document_id"),
            primary_document=_optional_upload_result_text(result, "primary_document"),
            deleted=_optional_upload_result_bool(result, "deleted"),
            skip_reason=_optional_upload_result_text(result, "skip_reason"),
            document_version=_optional_upload_result_text(result, "document_version"),
            source_fingerprint=_optional_upload_result_text(result, "source_fingerprint"),
        )


@dataclass(frozen=True)
class FinsUploadResultSummary:
    """上传任务结果摘要。

    Attributes:
        source_kind: 源文档类别，使用已有 ``SourceKind`` 区分 filing/material。
        document_id: 可选业务文档 ID。
        internal_document_id: 可选来源内部文档 ID。
        status: 上传业务状态摘要。
        uploaded_files: 已写入或处理的文件名摘要；不得包含路径。
        primary_document: 可选主文件名。
        deleted: 是否执行了删除动作；``None`` 表示 pipeline 未声明。
        skip_reason: 可选跳过原因。
        document_version: 可选文档版本。
        source_fingerprint: 可选来源指纹。
    """

    source_kind: SourceKind
    status: str
    document_id: str | None = None
    internal_document_id: str | None = None
    uploaded_files: tuple[str, ...] = ()
    primary_document: str | None = None
    deleted: bool | None = None
    skip_reason: str | None = None
    document_version: str | None = None
    source_fingerprint: str | None = None

    def to_json_summary(self) -> dict[str, JsonValue]:
        """转换为 JSON-compatible 摘要。

        Args:
            无。

        Returns:
            只包含上传业务结果摘要字段的 JSON-compatible 字典。

        Raises:
            ValueError: 文档 ID、文件名或摘要大小超过 job record 边界时抛出。
        """

        return {
            "source_kind": self.source_kind.value,
            "document_id": _optional_bounded_text(
                self.document_id,
                "upload_document_id",
                reject_path_separators=False,
            ),
            "internal_document_id": _optional_bounded_text(
                self.internal_document_id,
                "upload_internal_document_id",
                reject_path_separators=False,
            ),
            "status": _bounded_text(self.status, "upload_status", reject_path_separators=False),
            "uploaded_files": list(_bounded_text_tuple(self.uploaded_files, "uploaded_files")),
            "primary_document": _optional_bounded_text(self.primary_document, "primary_document"),
            "deleted": self.deleted,
            "skip_reason": _optional_bounded_text(
                self.skip_reason,
                "skip_reason",
                reject_path_separators=False,
            ),
            "document_version": _optional_bounded_text(
                self.document_version,
                "document_version",
                reject_path_separators=False,
            ),
            "source_fingerprint": _optional_bounded_text(
                self.source_fingerprint,
                "source_fingerprint",
                reject_path_separators=False,
            ),
        }


class FinsJobCancellationChecker(Protocol):
    """Fins 后台 job 协作式取消检查协议。"""

    def __call__(self) -> bool:
        """返回当前 Fins job 是否已被请求取消。

        Args:
            无。

        Returns:
            已请求取消时返回 ``True``，否则返回 ``False``。

        Raises:
            OSError: job store 读取失败时可由具体实现抛出。
            ValueError: job record 非法时可由具体实现抛出。
        """
        ...


class FinsUploadRunner(Protocol):
    """Fins 上传业务 runner 协议。"""

    def run_upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """执行上传业务逻辑。

        Args:
            request: 已通过 runtime 启动边界校验的上传请求。
            cancellation_checker: runtime 提供的协作式取消检查器。

        Returns:
            有界上传结果摘要。

        Raises:
            RuntimeError: 上传业务失败时抛出。
            ValueError: 请求字段或结果字段非法时抛出。
            OSError: 上传过程中仓储读写失败时抛出。
        """
        ...


@dataclass(frozen=True)
class FinsIngestionJobRecord:
    """Fins ingestion 持久化 job record。

    Attributes:
        job_id: ASCII opaque job id。
        operation_kind: 下载、预处理或上传。
        normalized_ticker: 标准化后的 ticker 裸码。
        market: 标准化市场。
        exchange: 标准化交易所；美股无明确交易所时为 ``None``。
        source: 下载来源标识；预处理与上传任务为 ``None``。
        source_kind: 源文档类型；预处理与上传任务用于区分 filing/material，下载任务为 ``None``。
        status: 当前 job 状态。
        created_at: 创建时间。
        updated_at: 最后更新时间。
        started_at: 开始执行时间；S1 不启动 pipeline，通常为 ``None``。
        finished_at: 完成时间；非终态为 ``None``。
        request_summary: 有界、JSON-compatible 请求摘要。
        result_summary: 有界、JSON-compatible 结果摘要。
        failure_summary: 有界、JSON-compatible 失败摘要。
        cancellation_requested: 是否已请求取消。
    """

    job_id: str
    operation_kind: FinsIngestionOperationKind
    normalized_ticker: str
    market: NormalizedTickerMarket
    exchange: NormalizedTickerExchange | None
    source: str | None
    source_kind: SourceKind | None
    status: FinsIngestionJobStatus
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    request_summary: dict[str, JsonValue]
    result_summary: dict[str, JsonValue]
    failure_summary: dict[str, JsonValue]
    cancellation_requested: bool


@dataclass(frozen=True)
class FinsIngestionJobStart:
    """job start 返回值。

    Attributes:
        job_id: 已持久化的 job id。
        status: 创建后的初始状态。
        record: 已持久化的完整 job record。
    """

    job_id: str
    status: FinsIngestionJobStatus
    record: FinsIngestionJobRecord


class FinsIngestionJobStore(Protocol):
    """Fins ingestion job record 存储协议。"""

    def create_job(self, record: FinsIngestionJobRecord) -> FinsIngestionJobRecord:
        """创建 job record。

        Args:
            record: 待创建的 job record。

        Returns:
            已持久化的 job record。

        Raises:
            FileExistsError: job id 已存在时抛出。
            OSError: 文件系统写入失败时抛出。
            ValueError: record 字段非法时抛出。
        """
        ...

    def save_job(self, record: FinsIngestionJobRecord) -> FinsIngestionJobRecord:
        """保存完整 job record。

        Args:
            record: 待保存的 job record。

        Returns:
            已持久化的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统写入失败时抛出。
            ValueError: record 字段非法时抛出。
        """
        ...

    def save_succeeded_or_cancelled(
        self,
        job_id: str,
        *,
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> FinsIngestionJobRecord:
        """按当前取消状态原子保存 succeeded 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            result_summary: succeeded 终态的有界业务结果摘要。
            finished_at: 本次终态写入时间。

        Returns:
            已持久化的终态 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统写入失败时抛出。
            ValueError: record 或摘要字段非法时抛出。
        """
        ...

    def save_cancelled_if_active(
        self,
        job_id: str,
        *,
        finished_at: str,
    ) -> FinsIngestionJobRecord:
        """仅当当前 job 非终态时原子保存 cancelled 终态。

        Args:
            job_id: opaque job id。
            finished_at: 本次 cancelled 终态写入时间。

        Returns:
            已持久化的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id 或 record 字段非法时抛出。
        """
        ...

    def save_failed_or_cancelled_if_active(
        self,
        job_id: str,
        *,
        failure_summary: dict[str, JsonValue],
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> FinsIngestionJobRecord:
        """按当前状态原子保存 failed 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            failure_summary: failed 终态的有界失败摘要。
            result_summary: failed 终态的有界业务结果摘要。
            finished_at: 本次终态写入时间。

        Returns:
            已持久化的 job record；若当前已是终态则原样返回；若当前已请求取消则返回
            cancelled 终态，否则返回 failed 终态。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、record 或摘要字段非法时抛出。
        """
        ...

    def claim_running_or_cancelled(
        self,
        job_id: str,
        *,
        started_at: str,
        updated_at: str,
    ) -> FinsIngestionJobRecord:
        """按当前取消状态原子 claim running 或 cancelled。

        Args:
            job_id: opaque job id。
            started_at: 进入 running 时使用的开始时间。
            updated_at: 本次状态更新时间；取消收口时也作为 finished_at。

        Returns:
            已持久化的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、record 或时间字段非法时抛出。
        """
        ...

    def read_job(self, job_id: str) -> FinsIngestionJobRecord:
        """读取 job record。

        Args:
            job_id: opaque job id。

        Returns:
            持久化 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读取失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """
        ...

    def request_cancel(self, job_id: str, *, updated_at: str) -> FinsIngestionJobRecord:
        """标记 job 取消请求。

        Args:
            job_id: opaque job id。
            updated_at: 本次状态更新时间。

        Returns:
            更新后的 job record；终态 job 原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """
        ...

    def append_job_event(
        self,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """追加 job event 并分配单调递增 sequence。

        Args:
            job_id: opaque job id。
            event: 无 sequence 的事件追加输入。

        Returns:
            已持久化且包含 sequence 的事件 record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、event 字段或 payload 非法时抛出。
        """
        ...

    def read_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[FinsIngestionJobEventRecord, ...]:
        """按 sequence 游标读取 job event。

        Args:
            job_id: opaque job id。
            after_sequence: 只返回 sequence 大于该值的事件；``0`` 表示读取全部。
            limit: 本次最多返回事件数量。

        Returns:
            按 sequence 升序排列的事件元组。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读取失败时抛出。
            ValueError: job id、游标、limit 或 event 内容非法时抛出。
        """
        ...


class FinsIngestionExecutor(Protocol):
    """Fins ingestion 后台执行器协议。"""

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """提交后台 job。

        Args:
            job_id: opaque job id，仅用于执行器诊断。
            operation: 无参数、无返回值的 job 执行函数。

        Returns:
            无。

        Raises:
            RuntimeError: 执行器无法接受任务时抛出。
        """
        ...


@dataclass(frozen=True)
class FinsIngestionThreadExecutor:
    """基于 daemon thread 的最小 Fins ingestion 执行器。"""

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """提交后台 job。

        Args:
            job_id: opaque job id，仅用于线程命名。
            operation: 无参数、无返回值的 job 执行函数。

        Returns:
            无。

        Raises:
            RuntimeError: 线程启动失败时抛出。
        """

        thread = Thread(
            target=operation,
            name=f"fins-ingestion-{job_id}",
            daemon=True,
        )
        thread.start()


@dataclass(frozen=True)
class _RuntimeJobCancellationChecker:
    """基于 job store 的 Fins job 取消检查器。"""

    job_store: FinsIngestionJobStore
    job_id: str

    def __call__(self) -> bool:
        """返回当前 job 是否已请求取消。

        Args:
            无。

        Returns:
            job 已处于 cancelling 或 cancelled 时返回 ``True``。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: job store 读取失败时抛出。
            ValueError: job record 非法时抛出。
        """

        record = self.job_store.read_job(self.job_id)
        return record.cancellation_requested or record.status in {
            FinsIngestionJobStatus.CANCELLING,
            FinsIngestionJobStatus.CANCELLED,
        }


@dataclass
class _DirectStreamCancellationState:
    """direct stream 单次执行的取消与终态仲裁状态。"""

    _lock: Lock
    _cancellation_requested: bool = False
    _consumer_aborted: bool = False
    _terminal_status: FinsResultStatus | None = None

    @classmethod
    def create(cls) -> "_DirectStreamCancellationState":
        """创建取消状态。

        Args:
            无。

        Returns:
            direct stream 本地取消状态。

        Raises:
            无。
        """

        return cls(_lock=Lock())

    def request_cancel(self) -> bool:
        """请求取消当前 direct stream。

        Args:
            无。

        Returns:
            取消在终态提交前首次生效时返回 ``True``。

        Raises:
            无。
        """

        with self._lock:
            if self._consumer_aborted or self._terminal_status is not None or self._cancellation_requested:
                return False
            self._cancellation_requested = True
            return True

    def request_consumer_abort(self) -> None:
        """标记 consumer 已放弃读取并请求 producer 停止。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with self._lock:
            self._consumer_aborted = True

    def is_cancelled(self) -> bool:
        """读取当前是否已请求取消。

        Args:
            无。

        Returns:
            已请求取消时返回 ``True``。

        Raises:
            无。
        """

        with self._lock:
            return self._cancellation_requested or self._consumer_aborted

    def is_consumer_aborted(self) -> bool:
        """读取 consumer 是否已放弃当前 stream。

        Args:
            无。

        Returns:
            consumer 已放弃读取时返回 ``True``。

        Raises:
            无。
        """

        with self._lock:
            return self._consumer_aborted

    def claim_terminal(self, requested_status: FinsResultStatus) -> FinsResultStatus | None:
        """原子提交唯一终态，并使已生效取消优先。

        Args:
            requested_status: producer 请求提交的终态。

        Returns:
            实际获得的终态；已有终态或 consumer 已 abort 时
            返回 ``None``。

        Raises:
            无。
        """

        with self._lock:
            if self._consumer_aborted or self._terminal_status is not None:
                return None
            resolved_status = FinsResultStatus.CANCELLED if self._cancellation_requested else requested_status
            self._terminal_status = resolved_status
            return resolved_status


@dataclass(frozen=True)
class _DirectCancellationChecker:
    """operation-scoped direct stream 取消检查器。"""

    cancellation_token: CancellationToken | None
    cancellation_state: _DirectStreamCancellationState

    def __call__(self) -> bool:
        """检查 direct stream 是否已取消。

        Args:
            无。

        Returns:
            本地 stream 被关闭或外部 token 已取消时返回 ``True``。

        Raises:
            无。
        """

        if self.cancellation_token is not None and self.cancellation_token.is_cancelled():
            self.cancellation_state.request_cancel()
        return self.cancellation_state.is_cancelled()


@dataclass(frozen=True)
class _DirectStreamProducerDone:
    """direct stream producer 完成哨兵。"""


_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone


@dataclass
class _FinsObservedOperationRecord:
    """process-local awaiting observation record。

    该对象是 registry 内部可变快照；除创建阶段外，所有字段读取和变更都
    必须在所属 runtime 的 ``_observation_lock`` 保护下完成。

    Attributes:
        handle: tool awaiting 使用的轻量 observation handle。
        queue: 后台 producer 投递 direct progress/result 的本地队列。
        context: 复用 direct stream producer 的执行上下文。
        producer: 复用 direct path 的同步业务 producer。
        cancellation_state: operation-scoped best-effort 取消状态。
        status: 最近一次已归纳的 observation 状态。
        result: 终态业务摘要；未终态时为空。
        message: 最近一次业务可读 observation 消息。
        submitted: 是否已经提交后台 executor。
    """

    handle: FinsObservationHandle
    queue: Queue[_DirectStreamQueueItem]
    context: _FinsIngestionExecutionContext
    producer: Callable[[_FinsIngestionExecutionContext], None]
    cancellation_state: _DirectStreamCancellationState
    status: FinsObservationStatus
    result: FinsResultSummary | None
    message: str
    submitted: bool = False


@dataclass(frozen=True)
class _FinsIngestionExecutionContext:
    """单次 ingestion 业务执行上下文。

    ``job_record`` 非空时表示 legacy awaiting job path；``direct_queue`` 非空时
    表示当前进程内 direct stream path。二者共享业务 helper，但事件与取消真源
    分别收口，避免 direct path 依赖 durable job store。
    """

    operation_kind: FinsIngestionOperationKind
    direct_operation_kind: FinsOperationKind
    normalized_ticker: str
    market: NormalizedTickerMarket
    exchange: NormalizedTickerExchange | None
    source: str | None
    source_kind: SourceKind | None
    download_request: FinsDownloadRequest | None
    cancellation_checker: FinsJobCancellationChecker
    job_record: FinsIngestionJobRecord | None
    direct_queue: Queue[_DirectStreamQueueItem] | None
    cancellation_state: _DirectStreamCancellationState | None


@dataclass(frozen=True)
class _DownloadProgressEmitter:
    """把 adapter 进度回调绑定到一次 runtime 执行上下文。"""

    runtime: FinsIngestionRuntime
    context: _FinsIngestionExecutionContext

    def __call__(self, event: FinsDownloadProgressEvent) -> None:
        """投递 adapter 下载进度。

        Args:
            event: source-specific adapter 产出的业务进度。

        Returns:
            无。

        Raises:
            ValueError: event 文本或 payload 不满足 bounded contract 时抛出。
        """

        self.runtime._emit_download_adapter_progress(self.context, event)


@dataclass(frozen=True)
class _DirectDownloadProducer:
    """direct download producer 绑定参数。"""

    runtime: "FinsIngestionRuntime"
    normalized: NormalizedTicker
    request: FinsDownloadRequest

    def __call__(self, context: _FinsIngestionExecutionContext) -> None:
        """执行 direct download producer。

        Args:
            context: direct stream 执行上下文。

        Returns:
            无。

        Raises:
            _UnsupportedDownloadSourceError: 没有匹配下载 adapter 时抛出。
            ValueError: adapter 返回字段非法时抛出。
            OSError: 仓储读写失败时抛出。
        """

        self.runtime._produce_direct_download(
            context=context,
            normalized=self.normalized,
            request=self.request,
        )


@dataclass(frozen=True)
class _DirectPreprocessProducer:
    """direct preprocess producer 绑定参数。"""

    runtime: "FinsIngestionRuntime"
    request: FinsPreprocessRequest

    def __call__(self, context: _FinsIngestionExecutionContext) -> None:
        """执行 direct preprocess producer。

        Args:
            context: direct stream 执行上下文。

        Returns:
            无。

        Raises:
            FileNotFoundError: ticker 或源文档不存在时抛出。
            ValueError: 请求或处理结果非法时抛出。
            OSError: 仓储读写失败时抛出。
        """

        self.runtime._produce_direct_preprocess(
            context=context,
            request=self.request,
        )


@dataclass(frozen=True)
class _DirectUploadProducer:
    """direct upload producer 绑定参数。"""

    runtime: "FinsIngestionRuntime"
    request: FinsUploadRequest

    def __call__(self, context: _FinsIngestionExecutionContext) -> None:
        """执行 direct upload producer。

        Args:
            context: direct stream 执行上下文。

        Returns:
            无。

        Raises:
            RuntimeError: 上传 runner 失败时抛出。
            ValueError: 请求字段或结果字段非法时抛出。
            OSError: 仓储读写失败时抛出。
        """

        self.runtime._produce_direct_upload(
            context=context,
            request=self.request,
        )


@dataclass(frozen=True)
class FsFinsIngestionJobStore:
    """文件系统 Fins ingestion job record 存储。"""

    root_dir: Path

    def __post_init__(self) -> None:
        """确保 job store 根目录存在。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self.root_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_workspace_root(cls, workspace_root: Path) -> "FsFinsIngestionJobStore":
        """由 Fins workspace root 派生 job store。

        Args:
            workspace_root: Fins 工作区根目录。

        Returns:
            文件系统 job store。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        root_dir = workspace_root
        for part in _JOBS_DIR_PARTS:
            root_dir = root_dir / part
        return cls(root_dir=root_dir)

    def create_job(self, record: FinsIngestionJobRecord) -> FinsIngestionJobRecord:
        """创建 job record。

        Args:
            record: 待创建的 job record。

        Returns:
            已持久化的 job record。

        Raises:
            FileExistsError: job id 已存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统写入失败时抛出。
            ValueError: record 字段非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            path = self._job_path(record.job_id)
            if path.exists():
                raise FileExistsError(f"Fins ingestion job 已存在: {record.job_id}")
            self._write_record_locked(record)
            return record

    def save_job(self, record: FinsIngestionJobRecord) -> FinsIngestionJobRecord:
        """保存完整 job record。

        Args:
            record: 待保存的 job record。

        Returns:
            已持久化的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统写入失败时抛出。
            ValueError: record 字段非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            path = self._job_path(record.job_id)
            if not path.exists():
                raise FileNotFoundError(f"Fins ingestion job 不存在: {record.job_id}")
            self._write_record_locked(record)
            return record

    def save_succeeded_or_cancelled(
        self,
        job_id: str,
        *,
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> FinsIngestionJobRecord:
        """按当前取消状态原子保存 succeeded 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            result_summary: succeeded 终态的有界业务结果摘要。
            finished_at: 本次终态写入时间。

        Returns:
            已持久化的终态 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、record 或摘要字段非法时抛出。
        """

        _assert_bounded_summary(result_summary, "result_summary")
        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            record = self._read_record_locked(job_id)
            if record.status in _TERMINAL_STATUSES:
                return record
            if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
                cancelled = replace(
                    record,
                    status=FinsIngestionJobStatus.CANCELLED,
                    updated_at=finished_at,
                    finished_at=finished_at,
                    cancellation_requested=True,
                )
                self._write_record_locked(cancelled)
                return cancelled
            succeeded = replace(
                record,
                status=FinsIngestionJobStatus.SUCCEEDED,
                updated_at=finished_at,
                finished_at=finished_at,
                result_summary=result_summary,
                failure_summary=dict(_EMPTY_SUMMARY),
            )
            self._write_record_locked(succeeded)
            return succeeded

    def save_cancelled_if_active(
        self,
        job_id: str,
        *,
        finished_at: str,
    ) -> FinsIngestionJobRecord:
        """仅当当前 job 非终态时原子保存 cancelled 终态。

        Args:
            job_id: opaque job id。
            finished_at: 本次 cancelled 终态写入时间。

        Returns:
            已持久化的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id 或 record 字段非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            record = self._read_record_locked(job_id)
            if record.status in _TERMINAL_STATUSES:
                return record
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=finished_at,
                finished_at=finished_at,
                cancellation_requested=True,
            )
            self._write_record_locked(cancelled)
            return cancelled

    def save_failed_or_cancelled_if_active(
        self,
        job_id: str,
        *,
        failure_summary: dict[str, JsonValue],
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> FinsIngestionJobRecord:
        """按当前状态原子保存 failed 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            failure_summary: failed 终态的有界失败摘要。
            result_summary: failed 终态的有界业务结果摘要。
            finished_at: 本次终态写入时间。

        Returns:
            已持久化的 job record；若当前已是终态则原样返回；若当前已请求取消则返回
            cancelled 终态，否则返回 failed 终态。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、record 或摘要字段非法时抛出。
        """

        _assert_bounded_summary(failure_summary, "failure_summary")
        _assert_bounded_summary(result_summary, "result_summary")
        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            record = self._read_record_locked(job_id)
            if record.status in _TERMINAL_STATUSES:
                return record
            if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
                cancelled = replace(
                    record,
                    status=FinsIngestionJobStatus.CANCELLED,
                    updated_at=finished_at,
                    finished_at=finished_at,
                    cancellation_requested=True,
                )
                self._write_record_locked(cancelled)
                return cancelled
            failed = replace(
                record,
                status=FinsIngestionJobStatus.FAILED,
                updated_at=finished_at,
                finished_at=finished_at,
                result_summary=result_summary,
                failure_summary=failure_summary,
            )
            self._write_record_locked(failed)
            return failed

    def claim_running_or_cancelled(
        self,
        job_id: str,
        *,
        started_at: str,
        updated_at: str,
    ) -> FinsIngestionJobRecord:
        """按当前取消状态原子 claim running 或 cancelled。

        Args:
            job_id: opaque job id。
            started_at: 进入 running 时使用的开始时间。
            updated_at: 本次状态更新时间；取消收口时也作为 finished_at。

        Returns:
            已持久化的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、record 或时间字段非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            record = self._read_record_locked(job_id)
            if record.status in _TERMINAL_STATUSES:
                return record
            if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
                cancelled = replace(
                    record,
                    status=FinsIngestionJobStatus.CANCELLED,
                    updated_at=updated_at,
                    finished_at=updated_at,
                    cancellation_requested=True,
                )
                self._write_record_locked(cancelled)
                return cancelled
            running = replace(
                record,
                status=FinsIngestionJobStatus.RUNNING,
                started_at=record.started_at or started_at,
                updated_at=updated_at,
            )
            self._write_record_locked(running)
            return running

    def read_job(self, job_id: str) -> FinsIngestionJobRecord:
        """读取 job record。

        Args:
            job_id: opaque job id。

        Returns:
            持久化 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读取失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            return self._read_record_locked(job_id)

    def request_cancel(self, job_id: str, *, updated_at: str) -> FinsIngestionJobRecord:
        """标记 job 取消请求。

        Args:
            job_id: opaque job id。
            updated_at: 本次状态更新时间。

        Returns:
            更新后的 job record；终态 job 原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            record = self._read_record_locked(job_id)
            if record.status in _TERMINAL_STATUSES:
                return record
            updated = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLING,
                updated_at=updated_at,
                cancellation_requested=True,
            )
            self._write_record_locked(updated)
            return updated

    def append_job_event(
        self,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """追加 job event 并分配单调递增 sequence。

        Args:
            job_id: opaque job id。
            event: 无 sequence 的事件追加输入。

        Returns:
            已持久化且包含 sequence 的事件 record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读写失败时抛出。
            ValueError: job id、event 字段或 payload 非法时抛出。
        """

        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            self._read_record_locked(job_id)
            event_path = self._job_events_path(job_id)
            sequence = self._last_event_sequence_locked(event_path) + 1
            record = FinsIngestionJobEventRecord(
                job_id=job_id,
                sequence=sequence,
                operation_kind=event.operation_kind,
                status=event.status,
                event_type=event.event_type,
                source_event_type=event.source_event_type,
                source_kind=event.source_kind,
                document_id=event.document_id,
                message=event.message,
                payload=event.payload,
                emitted_at=event.emitted_at,
            )
            payload = _event_record_to_json(record)
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            with event_path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_directory(self.root_dir)
            return record

    def read_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[FinsIngestionJobEventRecord, ...]:
        """按 sequence 游标读取 job event。

        Args:
            job_id: opaque job id。
            after_sequence: 只返回 sequence 大于该值的事件；``0`` 表示读取全部。
            limit: 本次最多返回事件数量。

        Returns:
            按 sequence 升序排列的事件元组。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            RuntimeFileLockError: 文件锁获取失败时抛出。
            OSError: 文件系统读取失败时抛出。
            ValueError: job id、游标、limit 或 event 内容非法时抛出。
        """

        _validate_event_read_window(after_sequence=after_sequence, limit=limit)
        with file_lock(self.root_dir / _LOCK_FILE_NAME):
            self._read_record_locked(job_id)
            event_path = self._job_events_path(job_id)
            if not event_path.exists():
                return ()
            events: list[FinsIngestionJobEventRecord] = []
            for record in self._iter_event_records_locked(event_path):
                if record.sequence <= after_sequence:
                    continue
                events.append(record)
                if len(events) >= limit:
                    break
            return tuple(events)

    def _job_path(self, job_id: str) -> Path:
        """构造单个 job record 路径。

        Args:
            job_id: opaque job id。

        Returns:
            job record JSON 路径。

        Raises:
            ValueError: job id 非法时抛出。
        """

        _validate_job_id(job_id)
        return self.root_dir / f"{job_id}{_JOB_FILE_SUFFIX}"

    def _job_events_path(self, job_id: str) -> Path:
        """构造单个 job event sidecar 路径。

        Args:
            job_id: opaque job id。

        Returns:
            job event JSONL 路径。

        Raises:
            ValueError: job id 非法时抛出。
        """

        _validate_job_id(job_id)
        return self.root_dir / f"{job_id}{_JOB_EVENT_FILE_SUFFIX}"

    def _last_event_sequence_locked(self, event_path: Path) -> int:
        """在持锁状态读取 event sidecar 最后一条 sequence。

        Args:
            event_path: job event JSONL 路径。

        Returns:
            最后一条事件 sequence；sidecar 不存在时返回 ``0``。

        Raises:
            OSError: 文件读取失败时抛出。
            ValueError: event sidecar 内容非法时抛出。
        """

        last_sequence = 0
        if not event_path.exists():
            return last_sequence
        for record in self._iter_event_records_locked(event_path):
            if record.sequence <= last_sequence:
                raise ValueError("Fins ingestion job event sequence 未递增")
            last_sequence = record.sequence
        return last_sequence

    def _iter_event_records_locked(self, event_path: Path) -> tuple[FinsIngestionJobEventRecord, ...]:
        """在持锁状态读取 event sidecar 全部事件。

        Args:
            event_path: job event JSONL 路径。

        Returns:
            event record 元组。

        Raises:
            OSError: 文件读取失败时抛出。
            ValueError: 有效 event record 的 sequence 非单调递增时抛出。
        """

        records: list[FinsIngestionJobEventRecord] = []
        last_sequence = 0
        with event_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = cast(JsonValue, json.loads(stripped))
                except json.JSONDecodeError as exc:
                    _warn_malformed_event_sidecar_row(
                        line_number=line_number,
                        error_type=type(exc).__name__,
                    )
                    continue
                if not isinstance(payload, Mapping):
                    _warn_malformed_event_sidecar_row(
                        line_number=line_number,
                        error_type=type(payload).__name__,
                    )
                    continue
                try:
                    record = _event_record_from_json(cast(Mapping[str, JsonValue], payload))
                except ValueError as exc:
                    _warn_malformed_event_sidecar_row(
                        line_number=line_number,
                        error_type=type(exc).__name__,
                    )
                    continue
                if record.sequence <= last_sequence:
                    raise ValueError("Fins ingestion job event sequence 未递增")
                records.append(record)
                last_sequence = record.sequence
        return tuple(records)

    def _read_record_locked(self, job_id: str) -> FinsIngestionJobRecord:
        """在持锁状态读取 job record。

        Args:
            job_id: opaque job id。

        Returns:
            持久化 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读取失败时抛出。
            ValueError: record 内容非法时抛出。
        """

        path = self._job_path(job_id)
        with path.open("r", encoding="utf-8") as stream:
            payload = cast(JsonValue, json.load(stream))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Fins ingestion job record 不是 JSON 映射: {job_id}")
        return _record_from_json(cast(Mapping[str, JsonValue], payload))

    def _write_record_locked(self, record: FinsIngestionJobRecord) -> None:
        """在持锁状态写入 job record。

        Args:
            record: 待写入的 job record。

        Returns:
            无。

        Raises:
            OSError: 文件系统写入失败时抛出。
            ValueError: record 内容非法时抛出。
        """

        payload = _record_to_json(record)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        if len(encoded) > _MAX_SUMMARY_JSON_CHARS * 2:
            raise ValueError("Fins ingestion job record 超出大小上限")
        path = self._job_path(record.job_id)
        tmp_path = self.root_dir / f".{record.job_id}.{uuid.uuid4().hex}.tmp"
        try:
            with tmp_path.open("w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_path, path)
            _fsync_directory(self.root_dir)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise


@dataclass
class FinsIngestionRuntime:
    """Fins 下载、预处理与上传 job 运行时基础入口。"""

    batching_repository: BatchingRepositoryProtocol
    source_repository: SourceDocumentRepositoryProtocol
    blob_repository: DocumentBlobRepositoryProtocol
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    processor_registry: ProcessorRegistry
    job_store: FinsIngestionJobStore
    executor: FinsIngestionExecutor
    download_adapters: Mapping[tuple[str, NormalizedTickerMarket], FinsSourceDownloadAdapter]
    upload_runner: FinsUploadRunner | None
    _start_lock: Lock
    _observation_lock: Lock
    _observations: dict[str, _FinsObservedOperationRecord]

    @classmethod
    def create(
        cls,
        *,
        batching_repository: BatchingRepositoryProtocol,
        source_repository: SourceDocumentRepositoryProtocol,
        blob_repository: DocumentBlobRepositoryProtocol,
        filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
        processed_repository: ProcessedDocumentRepositoryProtocol,
        processor_registry: ProcessorRegistry,
        job_store: FinsIngestionJobStore,
        executor: FinsIngestionExecutor | None = None,
        download_adapters: Mapping[tuple[str, NormalizedTickerMarket], FinsSourceDownloadAdapter] | None = None,
        upload_runner: FinsUploadRunner | None = None,
    ) -> "FinsIngestionRuntime":
        """创建 ingestion runtime。

        Args:
            batching_repository: batch lifecycle 唯一仓储协议实现。
            source_repository: 源文档仓储协议实现。
            blob_repository: 文档文件对象仓储协议实现。
            filing_maintenance_repository: filing 维护治理仓储协议实现。
            processed_repository: processed 文档仓储协议实现。
            processor_registry: 文档处理器注册表。
            job_store: Fins ingestion job record 存储。
            executor: 可选后台执行器；不传入时使用最小 daemon thread 执行器。
            download_adapters: 可选 source/market 下载 adapter 映射。
            upload_runner: 可选上传业务 runner；不传入时上传 job 会失败为不支持。

        Returns:
            Fins ingestion runtime。

        Raises:
            无。
        """

        return cls(
            batching_repository=batching_repository,
            source_repository=source_repository,
            blob_repository=blob_repository,
            filing_maintenance_repository=filing_maintenance_repository,
            processed_repository=processed_repository,
            processor_registry=processor_registry,
            job_store=job_store,
            executor=executor or FinsIngestionThreadExecutor(),
            download_adapters=dict(download_adapters or {}),
            upload_runner=upload_runner,
            _start_lock=Lock(),
            _observation_lock=Lock(),
            _observations={},
        )

    def download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行下载 direct stream。

        Args:
            request: 下载请求。
            cancellation_token: 可选 operation-scoped 取消 token。

        Returns:
            Fins 唯一 owner 校验后的 direct 事件流。

        Raises:
            ValueError: ticker、来源或请求字段非法时抛出。
            OSError: 仓储读写失败时由底层实现抛出。
        """

        normalized = request.normalized_ticker
        source = request.source.value
        return ValidatedFinsEventStream(
            self._run_direct_stream(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                direct_operation_kind=FinsOperationKind.DOWNLOAD,
                normalized=normalized,
                source=source,
                source_kind=None,
                download_request=request,
                cancellation_token=cancellation_token,
                producer=_DirectDownloadProducer(
                    runtime=self,
                    normalized=normalized,
                    request=request,
                ),
            ),
            operation_kind=FinsOperationKind.DOWNLOAD,
        )

    def preprocess(
        self,
        request: FinsPreprocessRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行预处理 direct stream。

        Args:
            request: 预处理请求。
            cancellation_token: 可选 operation-scoped 取消 token。

        Returns:
            Fins 唯一 owner 校验后的 direct 事件流。

        Raises:
            FileNotFoundError: ticker 或源文档不存在时抛出。
            ValueError: ticker 或请求字段非法时抛出。
            OSError: 仓储读写失败时由底层实现抛出。
        """

        normalized = ticker_normalization.normalize_ticker(request.ticker)
        return ValidatedFinsEventStream(
            self._run_direct_stream(
                operation_kind=FinsIngestionOperationKind.PREPROCESS,
                direct_operation_kind=FinsOperationKind.PREPROCESS,
                normalized=normalized,
                source=None,
                source_kind=request.source_kind,
                download_request=None,
                cancellation_token=cancellation_token,
                producer=_DirectPreprocessProducer(
                    runtime=self,
                    request=request,
                ),
            ),
            operation_kind=FinsOperationKind.PREPROCESS,
        )

    def upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ValidatedFinsEventStream:
        """执行上传 direct stream。

        Args:
            request: 上传请求。
            cancellation_token: 可选 operation-scoped 取消 token。

        Returns:
            Fins 唯一 owner 校验后的 direct 事件流。

        Raises:
            ValueError: ticker、source_kind、action 或上传请求字段非法时抛出。
            OSError: 仓储读写失败时由底层实现抛出。
        """

        normalized = ticker_normalization.normalize_ticker(request.ticker)
        normalized_request = _normalize_upload_request(request)
        direct_operation_kind = _direct_upload_operation_kind(normalized_request)
        return ValidatedFinsEventStream(
            self._run_direct_stream(
                operation_kind=FinsIngestionOperationKind.UPLOAD,
                direct_operation_kind=direct_operation_kind,
                normalized=normalized,
                source=None,
                source_kind=normalized_request.source_kind,
                download_request=None,
                cancellation_token=cancellation_token,
                producer=_DirectUploadProducer(
                    runtime=self,
                    request=normalized_request,
                ),
            ),
            operation_kind=direct_operation_kind,
        )

    def start_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动 process-local 可观察下载 operation。

        Args:
            request: 下载请求。
            cancellation_token: operation-scoped 取消 token。

        Returns:
            只供 Host wait adapter 后续观察 completion 的 lightweight handle。

        Raises:
            FinsIngestionStartCancelledError: 启动前观察到取消时抛出。
            ValueError: ticker、来源或请求字段非法时抛出。
            RuntimeError: 后台执行器无法启动 operation 时抛出。
        """

        handle = self.prepare_observed_download(
            request=request,
            cancellation_token=cancellation_token,
        )
        self.activate_observation(handle)
        return handle

    def prepare_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记 process-local 可观察下载 operation，但不提交执行器。

        Args:
            request: 下载请求。
            cancellation_token: operation-scoped 取消 token。

        Returns:
            只供 Host wait adapter 后续观察 completion 的 lightweight handle。

        Raises:
            FinsIngestionStartCancelledError: prepare 前观察到取消时抛出。
            ValueError: ticker、来源或请求字段非法时抛出。
        """

        _raise_if_start_cancelled(cancellation_token)
        normalized = request.normalized_ticker
        source = request.source.value
        return self._prepare_observed_stream(
            direct_operation_kind=FinsOperationKind.DOWNLOAD,
            operation_kind=FinsIngestionOperationKind.DOWNLOAD,
            normalized=normalized,
            source=source,
            source_kind=None,
            download_request=request,
            cancellation_token=cancellation_token,
            producer=_DirectDownloadProducer(
                runtime=self,
                normalized=normalized,
                request=request,
            ),
        )

    def start_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动 process-local 可观察预处理 operation。

        Args:
            request: 预处理请求。
            cancellation_token: operation-scoped 取消 token。

        Returns:
            只供 Host wait adapter 后续观察 completion 的 lightweight handle。

        Raises:
            FinsIngestionStartCancelledError: 启动前观察到取消时抛出。
            ValueError: ticker 或请求字段非法时抛出。
            RuntimeError: 后台执行器无法启动 operation 时抛出。
        """

        handle = self.prepare_observed_preprocess(
            request=request,
            cancellation_token=cancellation_token,
        )
        self.activate_observation(handle)
        return handle

    def prepare_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记 process-local 可观察预处理 operation，但不提交执行器。

        Args:
            request: 预处理请求。
            cancellation_token: operation-scoped 取消 token。

        Returns:
            只供 Host wait adapter 后续观察 completion 的 lightweight handle。

        Raises:
            FinsIngestionStartCancelledError: prepare 前观察到取消时抛出。
            ValueError: ticker 或请求字段非法时抛出。
        """

        _raise_if_start_cancelled(cancellation_token)
        normalized = ticker_normalization.normalize_ticker(request.ticker)
        return self._prepare_observed_stream(
            direct_operation_kind=FinsOperationKind.PREPROCESS,
            operation_kind=FinsIngestionOperationKind.PREPROCESS,
            normalized=normalized,
            source=None,
            source_kind=request.source_kind,
            download_request=None,
            cancellation_token=cancellation_token,
            producer=_DirectPreprocessProducer(runtime=self, request=request),
        )

    def start_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动 process-local 可观察上传 operation。

        Args:
            request: 上传请求。
            cancellation_token: operation-scoped 取消 token。

        Returns:
            只供 Host wait adapter 后续观察 completion 的 lightweight handle。

        Raises:
            FinsIngestionStartCancelledError: 启动前观察到取消时抛出。
            ValueError: ticker、source_kind、action 或上传字段非法时抛出。
            RuntimeError: 后台执行器无法启动 operation 时抛出。
        """

        handle = self.prepare_observed_upload(
            request=request,
            cancellation_token=cancellation_token,
        )
        self.activate_observation(handle)
        return handle

    def prepare_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记 process-local 可观察上传 operation，但不提交执行器。

        Args:
            request: 上传请求。
            cancellation_token: operation-scoped 取消 token。

        Returns:
            只供 Host wait adapter 后续观察 completion 的 lightweight handle。

        Raises:
            FinsIngestionStartCancelledError: prepare 前观察到取消时抛出。
            ValueError: ticker、source_kind、action 或上传字段非法时抛出。
        """

        _raise_if_start_cancelled(cancellation_token)
        normalized = ticker_normalization.normalize_ticker(request.ticker)
        normalized_request = _normalize_upload_request(request)
        return self._prepare_observed_stream(
            direct_operation_kind=_direct_upload_operation_kind(normalized_request),
            operation_kind=FinsIngestionOperationKind.UPLOAD,
            normalized=normalized,
            source=None,
            source_kind=normalized_request.source_kind,
            download_request=None,
            cancellation_token=cancellation_token,
            producer=_DirectUploadProducer(runtime=self, request=normalized_request),
        )

    async def poll_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """读取 process-local observation 当前快照。

        Args:
            handle: lightweight observation handle。

        Returns:
            当前 observation snapshot；当前进程找不到 handle 时返回 LOST。

        Raises:
            无。process-local registry 缺失按 LOST 收口。
        """

        return self._observation_snapshot(handle)

    async def cancel_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """请求取消 observed operation。

        Args:
            handle: lightweight observation handle。

        Returns:
            取消请求后的 observation snapshot；找不到 handle 时返回 LOST。

        Raises:
            无。取消是 best-effort，不承诺中断不可取消的 blocking call。
        """

        with self._observation_lock:
            record = self._observations.get(handle.handle_id)
            if record is None:
                return _lost_observation_snapshot(handle)
            if record.status not in _TERMINAL_OBSERVATION_STATUSES:
                record.cancellation_state.request_cancel()
                if record.submitted:
                    record.message = "Cancellation requested for this operation."
                else:
                    record.status = FinsObservationStatus.CANCELLED
                    record.message = "Observation was cancelled before activation."
                    record.result = _observation_cancelled_result(
                        operation_kind=record.handle.operation_kind,
                        download_request=record.context.download_request,
                    )
            return self._observation_snapshot_locked(record)

    async def abandon_observation(self, handle: FinsObservationHandle) -> None:
        """释放 process-local observation record。

        Args:
            handle: lightweight observation handle。

        Returns:
            无。

        Raises:
            无。abandon 只清理本地 observation 记录并 best-effort 请求取消，
            不删除已经写入 Fins storage 的业务产物。
        """

        with self._observation_lock:
            record = self._observations.pop(handle.handle_id, None)
            if record is not None:
                record.cancellation_state.request_consumer_abort()

    def activate_observation(self, handle: FinsObservationHandle) -> None:
        """激活已登记的 process-local observation 并提交后台执行器。

        Args:
            handle: lightweight observation handle。

        Returns:
            无。

        Raises:
            Exception: executor submit 或 activation 内部异常会在 observation
                被收口为 failed 后按原异常抛出。
        """

        context: _FinsIngestionExecutionContext
        producer: Callable[[_FinsIngestionExecutionContext], None]
        try:
            with self._observation_lock:
                record = self._observations.get(handle.handle_id)
                if record is None:
                    return
                self._drain_observation_queue(record)
                if (
                    record.submitted
                    or record.cancellation_state.is_cancelled()
                    or record.status in _TERMINAL_OBSERVATION_STATUSES
                ):
                    return
                record.submitted = True
                context = record.context
                producer = record.producer
            self.executor.submit(
                handle.handle_id,
                lambda: self._run_direct_stream_producer(context, producer),
            )
        except Exception:
            with self._observation_lock:
                failed_record = self._observations.get(handle.handle_id)
                if failed_record is not None:
                    _mark_observation_failed(
                        failed_record,
                        "Observation activation failed.",
                        FinsErrorKind.EXECUTION,
                    )
            raise

    def _prepare_observed_stream(
        self,
        *,
        direct_operation_kind: FinsOperationKind,
        operation_kind: FinsIngestionOperationKind,
        normalized: NormalizedTicker,
        source: str | None,
        source_kind: SourceKind | None,
        download_request: FinsDownloadRequest | None,
        cancellation_token: CancellationToken,
        producer: Callable[[_FinsIngestionExecutionContext], None],
    ) -> FinsObservationHandle:
        """注册 process-local observation，但不启动 observed stream producer。

        Args:
            direct_operation_kind: 用户可读 operation kind。
            operation_kind: runtime 内部 operation kind。
            normalized: 已归一化 ticker。
            source: 可选下载来源。
            source_kind: 可选源文档类型。
            download_request: download 操作的 typed request；其它操作为 ``None``。
            cancellation_token: operation-scoped 取消 token。
            producer: 复用 direct path 的同步业务 producer。

        Returns:
            lightweight observation handle。

        Raises:
            无。
        """

        handle = _new_observation_handle(direct_operation_kind)
        queue: Queue[_DirectStreamQueueItem] = Queue(maxsize=_DIRECT_EVENT_QUEUE_MAX_SIZE)
        cancellation_state = _DirectStreamCancellationState.create()
        context = _FinsIngestionExecutionContext(
            operation_kind=operation_kind,
            direct_operation_kind=direct_operation_kind,
            normalized_ticker=normalized.canonical,
            market=normalized.market,
            exchange=normalized.exchange,
            source=source,
            source_kind=source_kind,
            download_request=download_request,
            cancellation_checker=_DirectCancellationChecker(
                cancellation_token=cancellation_token,
                cancellation_state=cancellation_state,
            ),
            job_record=None,
            direct_queue=queue,
            cancellation_state=cancellation_state,
        )
        record = _FinsObservedOperationRecord(
            handle=handle,
            queue=queue,
            context=context,
            producer=producer,
            cancellation_state=cancellation_state,
            status=FinsObservationStatus.PENDING,
            result=None,
            message="Observation is pending.",
        )
        with self._observation_lock:
            self._observations[handle.handle_id] = record
        return handle

    def _observation_snapshot(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """读取并刷新 observation snapshot。

        Args:
            handle: lightweight observation handle。

        Returns:
            当前 observation snapshot。

        Raises:
            无。
        """

        with self._observation_lock:
            record = self._observations.get(handle.handle_id)
            if record is None:
                return _lost_observation_snapshot(handle)
            return self._observation_snapshot_locked(record)

    def _observation_snapshot_locked(
        self,
        record: _FinsObservedOperationRecord,
    ) -> FinsObservationSnapshot:
        """在持有 observation lock 时刷新并返回 snapshot。

        Args:
            record: process-local observation record。

        Returns:
            当前 observation snapshot。

        Raises:
            无。
        """

        self._drain_observation_queue(record)
        return FinsObservationSnapshot(
            handle=record.handle,
            status=record.status,
            message=record.message,
            result=record.result,
            error_kind=_observation_error_kind(record.status, record.result),
            retry_after_seconds=_observation_retry_after(record.status),
        )

    def _drain_observation_queue(self, record: _FinsObservedOperationRecord) -> None:
        """归纳 observed producer 已投递的 direct events。

        Args:
            record: process-local observation record。

        Returns:
            无。

        Raises:
            无。
        """

        while True:
            try:
                item = record.queue.get_nowait()
            except Empty:
                break
            if isinstance(item, _DirectStreamProducerDone):
                if record.result is None and record.status not in _TERMINAL_OBSERVATION_STATUSES:
                    record.status = FinsObservationStatus.FAILED
                    record.message = "Observation finished without a result."
                    record.result = _observation_failure_result(
                        operation_kind=record.handle.operation_kind,
                        download_request=record.context.download_request,
                    )
                continue
            if item.event_type is FinsEventType.PROGRESS:
                if record.result is None:
                    record.status = FinsObservationStatus.RUNNING
                    record.message = _safe_observation_message(item.message)
                continue
            if item.result is not None:
                record.result = item.result
                record.status = _observation_status_from_result(item.result.status)
                record.message = _safe_observation_message(item.message)

    async def _run_direct_stream(
        self,
        *,
        operation_kind: FinsIngestionOperationKind,
        direct_operation_kind: FinsOperationKind,
        normalized: NormalizedTicker,
        source: str | None,
        source_kind: SourceKind | None,
        download_request: FinsDownloadRequest | None,
        cancellation_token: CancellationToken | None,
        producer: Callable[[_FinsIngestionExecutionContext], None],
    ) -> AsyncGenerator[FinsEvent, None]:
        """在线程桥中执行同步 ingestion helper 并产出 direct events。

        Args:
            operation_kind: runtime 内部操作类型。
            direct_operation_kind: 用户可见 direct 操作类型。
            normalized: 已归一化 ticker。
            source: 可选下载来源。
            source_kind: 可选源文档类型。
            download_request: download 操作的 typed request；其它操作为 ``None``。
            cancellation_token: operation-scoped 取消 token。
            producer: 同步业务 producer。

        Returns:
            未解释 terminal 协议的 raw Fins direct 事件 async generator。

        Raises:
            Exception: producer 异常转换失败时由底层构造或 queue 操作抛出。
        """

        cancellation_state = _DirectStreamCancellationState.create()
        output_queue: asyncio.Queue[_DirectStreamQueueItem] = asyncio.Queue()
        operation_task = asyncio.create_task(
            self._run_direct_stream_operation(
                operation_kind=operation_kind,
                direct_operation_kind=direct_operation_kind,
                normalized=normalized,
                source=source,
                source_kind=source_kind,
                download_request=download_request,
                cancellation_token=cancellation_token,
                cancellation_state=cancellation_state,
                producer=producer,
                output_queue=output_queue,
            )
        )
        try:
            while True:
                item = await output_queue.get()
                if isinstance(item, _DirectStreamProducerDone):
                    break
                yield item
        finally:
            if not operation_task.done():
                cancellation_state.request_consumer_abort()
            await asyncio.shield(operation_task)

    async def _run_direct_stream_operation(
        self,
        *,
        operation_kind: FinsIngestionOperationKind,
        direct_operation_kind: FinsOperationKind,
        normalized: NormalizedTicker,
        source: str | None,
        source_kind: SourceKind | None,
        download_request: FinsDownloadRequest | None,
        cancellation_token: CancellationToken | None,
        cancellation_state: _DirectStreamCancellationState,
        producer: Callable[[_FinsIngestionExecutionContext], None],
        output_queue: asyncio.Queue[_DirectStreamQueueItem],
    ) -> None:
        """唯一拥有 direct producer 线程并把有界队列泵到 async 流。

        Args:
            operation_kind: runtime 内部操作类型。
            direct_operation_kind: 用户可见 direct 操作类型。
            normalized: 已归一化 ticker。
            source: 可选下载来源。
            source_kind: 可选源文档类型。
            download_request: download 操作的 typed request。
            cancellation_token: operation-scoped 取消 token。
            cancellation_state: 取消、consumer abort 与终态仲裁真源。
            producer: 同步业务 producer。
            output_queue: 仅向 async generator 交付事件的本地队列。

        Returns:
            无。

        Raises:
            Exception: 线程启动、queue pump 或线程 join 失败时抛出。
        """

        queue: Queue[_DirectStreamQueueItem] = Queue(maxsize=_DIRECT_EVENT_QUEUE_MAX_SIZE)
        context = _FinsIngestionExecutionContext(
            operation_kind=operation_kind,
            direct_operation_kind=direct_operation_kind,
            normalized_ticker=normalized.canonical,
            market=normalized.market,
            exchange=normalized.exchange,
            source=source,
            source_kind=source_kind,
            download_request=download_request,
            cancellation_checker=_DirectCancellationChecker(
                cancellation_token=cancellation_token,
                cancellation_state=cancellation_state,
            ),
            job_record=None,
            direct_queue=queue,
            cancellation_state=cancellation_state,
        )
        thread = Thread(
            target=self._run_direct_stream_producer,
            name=f"fins-direct-{operation_kind.value}",
            args=(context, producer),
            daemon=False,
        )
        thread_started = False
        try:
            thread.start()
            thread_started = True
            while True:
                item = await asyncio.to_thread(_direct_queue_get, queue, thread)
                if item is None:
                    continue
                if isinstance(item, _DirectStreamProducerDone):
                    break
                await output_queue.put(item)
        finally:
            if thread_started:
                await asyncio.to_thread(thread.join)
            await output_queue.put(_DirectStreamProducerDone())

    def _run_direct_stream_producer(
        self,
        context: _FinsIngestionExecutionContext,
        producer: Callable[[_FinsIngestionExecutionContext], None],
    ) -> None:
        """执行 direct stream 同步 producer。

        Args:
            context: 单次 direct stream 执行上下文。
            producer: 同步业务 producer。

        Returns:
            无。

        Raises:
            无。异常会转成失败 RESULT。
        """

        try:
            producer(context)
        except Exception as exc:
            error_kind = _classify_direct_error(
                exc,
                operation_kind=context.direct_operation_kind,
            )
            download_summary = (
                None
                if context.download_request is None
                else _public_download_summary(
                    _empty_download_summary_from_request(
                        context.download_request,
                        terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
                    )
                )
            )
            public_failure = (
                None
                if context.download_request is None
                else _download_public_failure_from_exception(
                    exc,
                    request=context.download_request,
                )
            )
            self._emit_direct_result(
                context,
                status=FinsResultStatus.FAILURE,
                details=(),
                error_kind=error_kind,
                error_message=(
                    public_failure.safe_message
                    if public_failure is not None
                    else _safe_direct_error_message(exc, error_kind=error_kind)
                ),
                download=download_summary,
                failure=public_failure,
            )
        finally:
            _put_direct_queue(context, _DirectStreamProducerDone())

    def _produce_direct_download(
        self,
        *,
        context: _FinsIngestionExecutionContext,
        normalized: NormalizedTicker,
        request: FinsDownloadRequest,
    ) -> None:
        """执行 direct download producer。

        Args:
            context: direct 执行上下文。
            normalized: 已归一化 ticker。
            request: 已规范化 source 的下载请求。

        Returns:
            无。

        Raises:
            _UnsupportedDownloadSourceError: 没有匹配下载 adapter 时抛出。
            ValueError: adapter 返回字段非法时抛出。
            OSError: 仓储读写失败时抛出。
        """

        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_DOWNLOAD_PREPARING,
            message=direct_progress_message(stage=_PROGRESS_DOWNLOAD_PREPARING),
            document_id=None,
            payload={
                _PAYLOAD_TICKER: context.normalized_ticker,
                _PAYLOAD_MARKET: context.market,
                _PAYLOAD_SOURCE: request.source.value,
            },
        )
        if context.cancellation_checker():
            self._emit_direct_cancelled_result(context)
            return
        summary = self._execute_download_request(context, normalized, request)
        if context.cancellation_checker():
            self._emit_direct_cancelled_result(context)
            return
        if summary.failed_count > 0 and summary.downloaded_count == 0 and summary.rejected_count == 0:
            failure = FinsPublicFailure(
                kind=FinsPublicFailureKind.EXECUTION,
                source=summary.source,
                transport_category=None,
                safe_message=direct_download_no_source_documents_message(),
                retry_hint="请检查文档失败分类后重试；若持续失败，请检查运行日志中的脱敏分类。",
            )
            self._emit_direct_result(
                context,
                status=FinsResultStatus.FAILURE,
                details=(),
                error_kind=FinsErrorKind.EXECUTION,
                error_message=failure.safe_message,
                download=_public_download_summary(summary),
                failure=failure,
            )
            return
        self._emit_direct_result(
            context,
            status=FinsResultStatus.SUCCESS,
            details=(),
            error_kind=None,
            error_message=None,
            download=_public_download_summary(summary),
            failure=None,
        )

    def _produce_direct_preprocess(
        self,
        *,
        context: _FinsIngestionExecutionContext,
        request: FinsPreprocessRequest,
    ) -> None:
        """执行 direct preprocess producer。

        Args:
            context: direct 执行上下文。
            request: 预处理请求。

        Returns:
            无。

        Raises:
            FileNotFoundError: ticker 或源文档不存在时抛出。
            ValueError: 请求或处理结果非法时抛出。
            OSError: 仓储读写失败时抛出。
        """

        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_PREPROCESS_PREPARING,
            message=direct_progress_message(stage=_PROGRESS_PREPROCESS_PREPARING),
            document_id=None,
            payload={
                _PAYLOAD_TICKER: context.normalized_ticker,
                _PAYLOAD_MARKET: context.market,
                _PAYLOAD_SOURCE_KIND: request.source_kind.value,
            },
        )
        if context.cancellation_checker():
            self._emit_direct_cancelled_result(context)
            return
        summary = self._execute_preprocess_request(context, request)
        if context.cancellation_checker():
            self._emit_direct_cancelled_result(context)
            return
        if summary.result_status() is FinsPreprocessResultStatus.FAILED:
            self._emit_direct_result(
                context,
                status=FinsResultStatus.FAILURE,
                details=_preprocess_result_details(summary),
                error_kind=FinsErrorKind.EXECUTION,
                error_message=direct_preprocess_no_requested_documents_message(),
            )
            return
        self._emit_direct_result(
            context,
            status=FinsResultStatus.SUCCESS,
            details=_preprocess_result_details(summary),
            error_kind=None,
            error_message=None,
        )

    def _produce_direct_upload(
        self,
        *,
        context: _FinsIngestionExecutionContext,
        request: FinsUploadRequest,
    ) -> None:
        """执行 direct upload producer。

        Args:
            context: direct 执行上下文。
            request: 已归一化上传请求。

        Returns:
            无。

        Raises:
            RuntimeError: 上传 runner 失败时抛出。
            ValueError: 请求字段或结果字段非法时抛出。
            OSError: 仓储读写失败时抛出。
        """

        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_UPLOAD_PREPARING,
            message=direct_progress_message(stage=_PROGRESS_UPLOAD_PREPARING),
            document_id=_upload_request_document_id(request),
            payload=_upload_context_request_progress_payload(context, request),
        )
        if context.cancellation_checker():
            self._emit_direct_cancelled_result(context)
            return
        if self.upload_runner is None:
            self._emit_direct_result(
                context,
                status=FinsResultStatus.FAILURE,
                details=_upload_result_details(
                    FinsUploadResultSummary(
                        source_kind=request.source_kind,
                        status=_UPLOAD_RESULT_STATUS_FAILED,
                    )
                ),
                error_kind=FinsErrorKind.EXECUTION,
                error_message=direct_upload_runtime_unavailable_message(),
            )
            return
        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_UPLOAD_STARTED,
            message=direct_progress_message(stage=_PROGRESS_UPLOAD_STARTED),
            document_id=_upload_request_document_id(request),
            payload=_upload_context_request_progress_payload(context, request),
        )
        summary = self.upload_runner.run_upload(
            request,
            cancellation_checker=context.cancellation_checker,
        )
        self._emit_context_progress(
            context,
            source_event_type=_upload_completed_progress_type(summary),
            message=direct_progress_message(stage=_upload_completed_progress_type(summary)),
            document_id=summary.document_id or _upload_request_document_id(request),
            payload=_upload_context_summary_progress_payload(context, request, summary),
        )
        if context.cancellation_checker():
            self._emit_direct_cancelled_result(context)
            return
        if summary.status.strip().lower() == _UPLOAD_RESULT_STATUS_FAILED:
            self._emit_direct_result(
                context,
                status=FinsResultStatus.FAILURE,
                details=_upload_result_details(summary),
                error_kind=FinsErrorKind.EXECUTION,
                error_message=direct_upload_failed_status_message(),
            )
            return
        self._emit_direct_result(
            context,
            status=FinsResultStatus.SUCCESS,
            details=_upload_result_details(summary),
            error_kind=None,
            error_message=None,
        )

    def start_download(
        self,
        request: FinsDownloadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """启动下载 job。

        本方法先创建 durable ``queued`` record，再提交后台下载 pipeline。
        下载 pipeline 只通过 Fins 仓储协议写入 source/blob/rejected artifact。

        Args:
            request: 下载请求。
            cancellation_token: 可选调用方取消观察 token；只用于启动边界，
                后台 job 提交后不再作为 Fins job cancel 真源。

        Returns:
            已持久化 job 的启动结果。

        Raises:
            FinsIngestionStartCancelledError: durable job 创建前观察到取消时抛出。
            ValueError: ticker、来源或请求摘要字段非法时抛出。
            OSError: job record 持久化失败，或 create 后取消桥接落盘失败时抛出。
        """

        normalized = request.normalized_ticker
        source = request.source.value
        request_summary: dict[str, JsonValue] = {
            "form_types": list(_bounded_text_tuple(request.form_types, "form_types", reject_path_separators=False)),
            "filed_after": request.date_range.start_text,
            "filed_before": request.date_range.end_text,
            "overwrite_existing": request.overwrite_existing,
            "rebuild_local_artifacts": request.rebuild_local_artifacts,
        }
        _raise_if_start_cancelled(cancellation_token)
        with self._start_lock:
            start = self._create_queued_record_with_start_lock(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                normalized=normalized,
                source=source,
                source_kind=None,
                request_summary=request_summary,
            )
            if _is_start_cancelled(cancellation_token):
                return _job_start_from_record(self._save_cancelled(start.record))
            self.executor.submit(
                start.job_id,
                lambda: self._run_download_job(
                    job_id=start.job_id,
                    normalized=normalized,
                    request=request,
                ),
            )
            return start

    def start_preprocess(
        self,
        request: FinsPreprocessRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """启动预处理 job。

        本方法先创建 durable ``queued`` record，再提交后台 pipeline。后台
        pipeline 只通过 Fins 仓储协议读取 source、写入 processed。

        Args:
            request: 预处理请求。
            cancellation_token: 可选调用方取消观察 token；只用于启动边界，
                后台 job 提交后不再作为 Fins job cancel 真源。

        Returns:
            已持久化 job 的启动结果。

        Raises:
            FinsIngestionStartCancelledError: durable job 创建前观察到取消时抛出。
            ValueError: ticker 或请求摘要字段非法时抛出。
            OSError: job record 持久化失败，或 create 后取消桥接落盘失败时抛出。
        """

        normalized = ticker_normalization.normalize_ticker(request.ticker)
        request_summary: dict[str, JsonValue] = {
            "source_kind": request.source_kind.value,
            "document_ids": list(
                _bounded_text_tuple(request.document_ids, "document_ids", reject_path_separators=False)
            ),
            "form_types": list(_bounded_text_tuple(request.form_types, "form_types", reject_path_separators=False)),
            "rebuild_processed": request.rebuild_processed,
        }
        _raise_if_start_cancelled(cancellation_token)
        with self._start_lock:
            start = self._create_queued_record_with_start_lock(
                operation_kind=FinsIngestionOperationKind.PREPROCESS,
                normalized=normalized,
                source=None,
                source_kind=request.source_kind,
                request_summary=request_summary,
            )
            if _is_start_cancelled(cancellation_token):
                return _job_start_from_record(self._save_cancelled(start.record))
            self.executor.submit(
                start.job_id,
                lambda: self._run_preprocess_job(
                    job_id=start.job_id,
                    request=request,
                ),
            )
            return start

    def start_upload(
        self,
        request: FinsUploadRequest,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> FinsIngestionJobStart:
        """启动上传 job。

        本方法只负责创建 durable ``queued`` record 并提交上传 runner 边界。
        直接创建的 runtime 若未传入 runner 仍会以不支持结束；通过
        ``DefaultFinsRuntime`` 装配的 runtime 已提供 production SEC/CN/HK
        upload runner。process、CLI、Host、tool/provider 装配不在 Slice 4 内。

        Args:
            request: 上传请求。
            cancellation_token: 可选调用方取消观察 token；只用于启动边界，
                后台 job 提交后不再作为 Fins job cancel 真源。

        Returns:
            已持久化 job 的启动结果。

        Raises:
            FinsIngestionStartCancelledError: durable job 创建前观察到取消时抛出。
            ValueError: ticker、source_kind 或请求摘要字段非法时抛出。
            OSError: job record 持久化失败，或 create 后取消桥接落盘失败时抛出。
        """

        normalized = ticker_normalization.normalize_ticker(request.ticker)
        normalized_request = _normalize_upload_request(request)
        request_summary = _upload_request_summary(normalized_request)
        _raise_if_start_cancelled(cancellation_token)
        with self._start_lock:
            start = self._create_queued_record_with_start_lock(
                operation_kind=FinsIngestionOperationKind.UPLOAD,
                normalized=normalized,
                source=None,
                source_kind=normalized_request.source_kind,
                request_summary=request_summary,
            )
            if _is_start_cancelled(cancellation_token):
                return _job_start_from_record(self._save_cancelled(start.record))
            self.executor.submit(
                start.job_id,
                lambda: self._run_upload_job(
                    job_id=start.job_id,
                    request=normalized_request,
                ),
            )
            return start

    def read_job(self, job_id: str) -> FinsIngestionJobRecord:
        """读取 ingestion job。

        Args:
            job_id: opaque job id。

        Returns:
            持久化 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: job store 读取失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """

        return self.job_store.read_job(job_id)

    def read_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int = 0,
        limit: int = _DEFAULT_JOB_EVENT_READ_LIMIT,
    ) -> tuple[FinsIngestionJobEventRecord, ...]:
        """按 sequence 游标读取 ingestion job events。

        Args:
            job_id: opaque job id。
            after_sequence: 只返回 sequence 大于该值的事件；``0`` 表示读取全部。
            limit: 本次最多返回事件数量。

        Returns:
            按 sequence 升序排列的事件元组。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: job store 读取失败时抛出。
            ValueError: job id、游标、limit 或 event 内容非法时抛出。
        """

        return self.job_store.read_job_events(
            job_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    def request_cancel(self, job_id: str) -> FinsIngestionJobRecord:
        """请求取消 ingestion job。

        Args:
            job_id: opaque job id。

        Returns:
            更新后的 job record；终态 job 原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: job store 读写失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """

        record = self.job_store.request_cancel(job_id, updated_at=_utc_now())
        if record.status is FinsIngestionJobStatus.CANCELLING and record.cancellation_requested:
            self._append_job_event_warn(
                record,
                event_type=FinsIngestionJobEventType.CANCEL_REQUESTED,
                message="已记录取消请求",
                payload={},
            )
        return record

    def _create_queued_record_with_start_lock(
        self,
        *,
        operation_kind: FinsIngestionOperationKind,
        normalized: NormalizedTicker,
        source: str | None,
        source_kind: SourceKind | None,
        request_summary: dict[str, JsonValue],
    ) -> FinsIngestionJobStart:
        """在调用方持有启动锁时创建 queued job record。

        Args:
            operation_kind: job 操作类型。
            normalized: 标准化 ticker。
            source: 下载来源标识。
            source_kind: 源文档类型。
            request_summary: 有界请求摘要。

        Returns:
            job start 结果。

        Raises:
            OSError: job record 持久化失败时抛出。
            ValueError: job record 字段非法时抛出。
        """

        _assert_bounded_summary(request_summary, "request_summary")
        job_id = _new_job_id()
        now = _utc_now()
        record = FinsIngestionJobRecord(
            job_id=job_id,
            operation_kind=operation_kind,
            normalized_ticker=normalized.canonical,
            market=normalized.market,
            exchange=normalized.exchange,
            source=source,
            source_kind=source_kind,
            status=FinsIngestionJobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            started_at=None,
            finished_at=None,
            request_summary=request_summary,
            result_summary=dict(_EMPTY_SUMMARY),
            failure_summary=dict(_EMPTY_SUMMARY),
            cancellation_requested=False,
        )
        persisted = self.job_store.create_job(record)
        self._append_job_event_warn(
            persisted,
            event_type=FinsIngestionJobEventType.JOB_QUEUED,
            message="job 已进入队列",
            payload={},
        )
        return _job_start_from_record(persisted)

    def _run_preprocess_job(self, *, job_id: str, request: FinsPreprocessRequest) -> None:
        """执行预处理后台 job，并把异常收口到 job store。

        Args:
            job_id: opaque job id。
            request: 原始预处理请求。

        Returns:
            无。

        Raises:
            无。所有业务与运行时异常都会转换为 failed terminal record。
        """

        try:
            record = self._mark_job_running_or_cancelled(job_id)
            if record.status in _TERMINAL_STATUSES:
                return
            context = self._job_execution_context(
                record,
                direct_operation_kind=FinsOperationKind.PREPROCESS,
            )
            summary = self._execute_preprocess_request(context, request)
            latest = self.job_store.read_job(job_id)
            if latest.cancellation_requested or latest.status is FinsIngestionJobStatus.CANCELLING:
                self._save_cancelled(latest)
                return
            if summary.result_status() is FinsPreprocessResultStatus.FAILED:
                self._save_failed(
                    latest,
                    message=direct_preprocess_no_requested_documents_message(),
                    result_summary=summary.to_json_summary(),
                )
                return
            self._save_succeeded(latest, summary.to_json_summary())
        except Exception as exc:
            self._save_failed_from_exception(job_id, exc)

    def _run_download_job(
        self,
        *,
        job_id: str,
        normalized: NormalizedTicker,
        request: FinsDownloadRequest,
    ) -> None:
        """执行下载后台 job，并把异常收口到 job store。

        Args:
            job_id: opaque job id。
            normalized: 已归一化 ticker。
            request: 已规范化 source 字段的原始下载请求。

        Returns:
            无。

        Raises:
            无。所有业务与运行时异常都会转换为 terminal job record。
        """

        try:
            record = self._mark_job_running_or_cancelled(job_id)
            if record.status in _TERMINAL_STATUSES:
                return
            context = self._job_execution_context(
                record,
                direct_operation_kind=FinsOperationKind.DOWNLOAD,
            )
            summary = self._execute_download_request(context, normalized, request)
            latest = self.job_store.read_job(job_id)
            if latest.cancellation_requested or latest.status is FinsIngestionJobStatus.CANCELLING:
                self._save_cancelled(latest)
                return
            if summary.failed_count > 0 and summary.downloaded_count == 0 and summary.rejected_count == 0:
                self._save_failed(
                    latest,
                    message=direct_download_no_source_documents_message(),
                    result_summary=summary.to_json_summary(),
                )
                return
            self._save_succeeded(latest, summary.to_json_summary())
        except _UnsupportedDownloadSourceError as exc:
            self._save_download_unsupported(job_id, request=request, message=str(exc))
        except Exception as exc:
            self._save_failed_from_exception(job_id, exc)

    def _run_upload_job(
        self,
        *,
        job_id: str,
        request: FinsUploadRequest,
    ) -> None:
        """执行上传后台 job，并把异常收口到 job store。

        Args:
            job_id: opaque job id。
            request: 已通过 runtime 启动边界校验的上传请求。

        Returns:
            无。

        Raises:
            无。所有业务与运行时异常都会转换为 terminal job record。
        """

        try:
            record = self._mark_job_running_or_cancelled(job_id)
            if record.status in _TERMINAL_STATUSES:
                return
            if self.upload_runner is None:
                self._save_failed(
                    record,
                    message=_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE,
                    result_summary=FinsUploadResultSummary(
                        source_kind=request.source_kind,
                        status=_UPLOAD_RESULT_STATUS_FAILED,
                    ).to_json_summary(),
                )
                return
            context = self._job_execution_context(
                record,
                direct_operation_kind=_direct_upload_operation_kind(request),
            )
            self._emit_context_progress(
                context,
                source_event_type=_PROGRESS_UPLOAD_STARTED,
                message=direct_progress_message(stage=_PROGRESS_UPLOAD_STARTED),
                document_id=_upload_request_document_id(request),
                payload=_upload_context_request_progress_payload(context, request),
            )
            summary = self.upload_runner.run_upload(
                request,
                cancellation_checker=context.cancellation_checker,
            )
            self._emit_context_progress(
                context,
                source_event_type=_upload_completed_progress_type(summary),
                message=direct_progress_message(stage=_upload_completed_progress_type(summary)),
                document_id=summary.document_id or _upload_request_document_id(request),
                payload=_upload_context_summary_progress_payload(context, request, summary),
            )
            latest = self.job_store.read_job(job_id)
            if latest.cancellation_requested or latest.status is FinsIngestionJobStatus.CANCELLING:
                self._save_cancelled(latest)
                return
            self._save_succeeded(latest, summary.to_json_summary())
        except Exception as exc:
            self._save_failed_from_exception(job_id, exc)

    def _mark_job_running_or_cancelled(self, job_id: str) -> FinsIngestionJobRecord:
        """把 queued job 标记为 running，或按取消请求收口为 cancelled。

        Args:
            job_id: opaque job id。

        Returns:
            更新后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: job store 读写失败时抛出。
            ValueError: job record 非法时抛出。
        """

        now = _utc_now()
        record = self.job_store.claim_running_or_cancelled(
            job_id,
            started_at=now,
            updated_at=now,
        )
        if record.status is FinsIngestionJobStatus.RUNNING:
            self._append_job_event_warn(
                record,
                event_type=FinsIngestionJobEventType.JOB_RUNNING,
                message="job 已开始执行",
                payload={},
            )
        elif record.status is FinsIngestionJobStatus.CANCELLED:
            self._append_job_event_warn(
                record,
                event_type=FinsIngestionJobEventType.JOB_CANCELLED,
                message="job 已取消",
                payload={},
            )
        return record

    def _job_execution_context(
        self,
        record: FinsIngestionJobRecord,
        *,
        direct_operation_kind: FinsOperationKind,
    ) -> _FinsIngestionExecutionContext:
        """由 legacy job record 构造共享业务执行上下文。

        Args:
            record: 已进入 running 的 job record。
            direct_operation_kind: 对应 direct 业务操作类型，仅用于共享 helper 语义。

        Returns:
            绑定 job-store 取消检查与 sidecar progress sink 的执行上下文。

        Raises:
            无。
        """

        return _FinsIngestionExecutionContext(
            operation_kind=record.operation_kind,
            direct_operation_kind=direct_operation_kind,
            normalized_ticker=record.normalized_ticker,
            market=record.market,
            exchange=record.exchange,
            source=record.source,
            source_kind=record.source_kind,
            download_request=None,
            cancellation_checker=_RuntimeJobCancellationChecker(
                job_store=self.job_store,
                job_id=record.job_id,
            ),
            job_record=record,
            direct_queue=None,
            cancellation_state=None,
        )

    def _execute_preprocess_request(
        self,
        context: _FinsIngestionExecutionContext,
        request: FinsPreprocessRequest,
    ) -> FinsPreprocessResultSummary:
        """执行单个预处理请求。

        Args:
            context: 单次业务执行上下文。
            request: 原始预处理请求。

        Returns:
            预处理结果摘要。

        Raises:
            FileNotFoundError: ticker 或显式文档不存在时抛出。
            ValueError: 选择数量超过上限或请求字段非法时抛出。
            OSError: 仓储读取或写入失败时抛出。
        """

        ticker = context.normalized_ticker
        document_ids = self._select_preprocess_documents(
            ticker=ticker,
            source_kind=request.source_kind,
            document_ids=request.document_ids,
            form_types=request.form_types,
        )
        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_PREPROCESS_SELECTED,
            message=direct_progress_message(stage=_PROGRESS_PREPROCESS_SELECTED),
            document_id=None,
            payload=_preprocess_selected_progress_payload(
                context,
                request,
                selected_count=len(document_ids),
            ),
        )
        processed_ids: list[str] = []
        skipped_ids: list[str] = []
        failed_ids: list[str] = []
        not_supported_ids: list[str] = []

        for document_index, document_id in enumerate(document_ids, start=1):
            if context.cancellation_checker():
                break
            self._emit_context_progress(
                context,
                source_event_type=_PROGRESS_PREPROCESS_DOCUMENT_STARTED,
                message=direct_progress_message(stage=_PROGRESS_PREPROCESS_DOCUMENT_STARTED),
                document_id=document_id,
                payload=_preprocess_document_progress_payload(
                    context,
                    request,
                    document_index=document_index,
                    document_total=len(document_ids),
                ),
            )
            try:
                outcome = self._preprocess_one_document(
                    ticker=ticker,
                    document_id=document_id,
                    source_kind=request.source_kind,
                    rebuild_processed=request.rebuild_processed,
                )
            except _PreprocessNotSupportedError:
                not_supported_ids.append(document_id)
                self._emit_context_progress(
                    context,
                    source_event_type=_PROGRESS_PREPROCESS_DOCUMENT_NOT_SUPPORTED,
                    message=direct_progress_message(stage=_PROGRESS_PREPROCESS_DOCUMENT_NOT_SUPPORTED),
                    document_id=document_id,
                    payload=_preprocess_document_progress_payload(
                        context,
                        request,
                        document_index=document_index,
                        document_total=len(document_ids),
                    ),
                )
                continue
            except Exception:
                failed_ids.append(document_id)
                self._emit_context_progress(
                    context,
                    source_event_type=_PROGRESS_PREPROCESS_DOCUMENT_FAILED,
                    message=direct_progress_message(stage=_PROGRESS_PREPROCESS_DOCUMENT_FAILED),
                    document_id=document_id,
                    payload=_preprocess_document_progress_payload(
                        context,
                        request,
                        document_index=document_index,
                        document_total=len(document_ids),
                    ),
                )
                continue
            if outcome == "processed":
                processed_ids.append(document_id)
                self._emit_context_progress(
                    context,
                    source_event_type=_PROGRESS_PREPROCESS_DOCUMENT_PROCESSED,
                    message=direct_progress_message(stage=_PROGRESS_PREPROCESS_DOCUMENT_PROCESSED),
                    document_id=document_id,
                    payload=_preprocess_document_progress_payload(
                        context,
                        request,
                        document_index=document_index,
                        document_total=len(document_ids),
                    ),
                )
            else:
                skipped_ids.append(document_id)
                self._emit_context_progress(
                    context,
                    source_event_type=_PROGRESS_PREPROCESS_DOCUMENT_SKIPPED,
                    message=direct_progress_message(stage=_PROGRESS_PREPROCESS_DOCUMENT_SKIPPED),
                    document_id=document_id,
                    payload=_preprocess_document_progress_payload(
                        context,
                        request,
                        document_index=document_index,
                        document_total=len(document_ids),
                    ),
                )

        summary = FinsPreprocessResultSummary(
            selected_count=len(document_ids),
            processed_count=len(processed_ids),
            skipped_count=len(skipped_ids),
            not_supported_count=len(not_supported_ids),
            failed_count=len(failed_ids),
            processed_document_ids=tuple(processed_ids),
            skipped_document_ids=tuple(skipped_ids),
            failed_document_ids=tuple(failed_ids),
            not_supported_document_ids=tuple(not_supported_ids),
        )
        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_PREPROCESS_COMPLETED,
            message=direct_progress_message(stage=_PROGRESS_PREPROCESS_COMPLETED),
            document_id=None,
            payload=_preprocess_summary_progress_payload(context, request, summary),
        )
        return summary

    def _execute_download_request(
        self,
        context: _FinsIngestionExecutionContext,
        normalized: NormalizedTicker,
        request: FinsDownloadRequest,
    ) -> _FinsDownloadResultSummary:
        """执行单个下载请求。

        Args:
            record: 已进入 running 的 job record。
            normalized: 已归一化 ticker。
            request: 下载请求。

        Returns:
            下载结果摘要。

        Raises:
            _UnsupportedDownloadSourceError: 没有匹配 adapter 时抛出。
            ValueError: adapter 返回字段非法时抛出。
            OSError: 仓储读取或写入失败时抛出。
        """

        adapter = self._select_download_adapter(source=request.source.value, market=normalized.market)
        adapter_request = FinsSourceDownloadAdapterRequest(
            normalized_ticker=normalized,
            source=request.source,
            form_types=_bounded_text_tuple(request.form_types, "form_types", reject_path_separators=False),
            date_range=request.date_range,
            overwrite_existing=request.overwrite_existing,
            rebuild_local_artifacts=request.rebuild_local_artifacts,
            cancellation_checker=context.cancellation_checker,
            progress_sink=_DownloadProgressEmitter(self, context),
        )
        self._emit_context_progress(
            context,
            source_event_type=_PROGRESS_DOWNLOAD_STARTED,
            message=direct_progress_message(stage=_PROGRESS_DOWNLOAD_STARTED),
            document_id=None,
            payload=_download_context_request_progress_payload(context, adapter_request),
        )
        adapter_result = adapter.download(adapter_request)
        if adapter_result.persisted_summary is not None:
            if adapter_result.documents or adapter_result.rejected_artifacts:
                raise ValueError("adapter persisted_summary 不得与 documents/rejected_artifacts 同时返回")
            summary = _bounded_download_summary(adapter_result.persisted_summary)
            _validate_download_summary_request_identity(
                summary,
                request=request,
            )
            self._emit_context_progress(
                context,
                source_event_type=_download_completed_progress_type(summary),
                message=direct_progress_message(stage=_download_completed_progress_type(summary)),
                document_id=None,
                payload=_download_context_summary_progress_payload(context, adapter_request, summary),
            )
            return summary
        document_rows: list[FinsDownloadDocumentResult] = []

        for document in adapter_result.documents:
            if context.cancellation_checker():
                break
            stored = self._store_downloaded_document(
                ticker=normalized.canonical,
                document=document,
                overwrite_existing=request.overwrite_existing,
            )
            if stored:
                disposition = FinsDownloadDocumentDisposition.DOWNLOADED
                reason_category = None
                reason_message = None
                locator = self.source_repository.get_source_document_locator(
                    normalized.canonical,
                    document.document_id,
                    document.source_kind,
                )
            else:
                disposition = FinsDownloadDocumentDisposition.SKIPPED
                reason_category = "already_exists"
                reason_message = "本地已有完整下载结果，跳过重新下载"
                locator = None
            document_rows.append(
                FinsDownloadDocumentResult(
                    document_id=document.document_id,
                    form_or_period=document.form_type,
                    filing_date=_optional_download_meta_text(document.meta, "filing_date"),
                    report_date=_optional_download_meta_text(document.meta, "report_date"),
                    disposition=disposition,
                    reason_category=reason_category,
                    reason_message=reason_message,
                    artifact_locator=locator,
                )
            )

        for artifact in adapter_result.rejected_artifacts:
            if context.cancellation_checker():
                break
            self._store_rejected_filing_artifact(
                ticker=normalized.canonical,
                artifact=artifact,
            )
            document_rows.append(
                FinsDownloadDocumentResult(
                    document_id=artifact.document_id,
                    form_or_period=artifact.form_type,
                    filing_date=artifact.filing_date,
                    report_date=artifact.report_date,
                    disposition=FinsDownloadDocumentDisposition.REJECTED,
                    reason_category=artifact.rejection_category,
                    reason_message=artifact.rejection_reason,
                    artifact_locator=None,
                )
            )

        failed_count = _non_negative_count(adapter_result.failed_count, "failed_count")
        if failed_count != 0:
            raise ValueError("非 persisted adapter 不得返回缺少 typed document rows 的 failed_count")
        discovered_count = _non_negative_count(
            adapter_result.discovered_count,
            "discovered_count",
        )
        if discovered_count != len(document_rows):
            raise ValueError("adapter discovered_count 必须与 typed document rows 数量一致")
        rows = tuple(document_rows)

        summary = _FinsDownloadResultSummary.from_document_rows(
            source=request.source,
            canonical_ticker=normalized.canonical,
            effective_filters=FinsDownloadEffectiveFilters(
                form_types=request.form_types,
                start_date=request.date_range.start_text,
                end_date=request.date_range.end_text,
                overwrite_existing=request.overwrite_existing,
                rebuild_local_artifacts=request.rebuild_local_artifacts,
            ),
            document_rows=rows,
            missing_periods=(),
        )
        self._emit_context_progress(
            context,
            source_event_type=_download_completed_progress_type(summary),
            message=direct_progress_message(stage=_download_completed_progress_type(summary)),
            document_id=None,
            payload=_download_context_summary_progress_payload(context, adapter_request, summary),
        )
        return summary

    def _select_download_adapter(
        self,
        *,
        source: str,
        market: NormalizedTickerMarket,
    ) -> FinsSourceDownloadAdapter:
        """按来源与市场选择下载 adapter。

        Args:
            source: 已归一化来源标识。
            market: 已归一化市场。

        Returns:
            匹配的下载 adapter。

        Raises:
            _UnsupportedDownloadSourceError: 没有匹配 adapter 时抛出。
        """

        adapter = self.download_adapters.get((source, market))
        if adapter is None:
            raise _UnsupportedDownloadSourceError(f"不支持的下载来源: source={source}, market={market}")
        return adapter

    def _store_downloaded_document(
        self,
        *,
        ticker: str,
        document: FinsDownloadedSourceDocument,
        overwrite_existing: bool,
    ) -> bool:
        """保存单个下载文档。

        Args:
            ticker: 标准化 ticker。
            document: adapter 返回的源文档。
            overwrite_existing: 是否覆盖已有源文档。

        Returns:
            写入时返回 ``True``；已有且不覆盖时返回 ``False``。

        Raises:
            ValueError: 文档字段非法时抛出。
            OSError: 仓储写入失败时抛出。
        """

        document_id = _bounded_text(document.document_id, "document_id", reject_path_separators=False)
        source_exists = _source_document_exists(self.source_repository, ticker, document_id, document.source_kind)
        if source_exists:
            if not overwrite_existing:
                return False

        primary_document = _bounded_text(document.primary_document, "primary_document")
        create_request = SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=_bounded_text(
                document.internal_document_id,
                "internal_document_id",
                reject_path_separators=False,
            ),
            form_type=_optional_bounded_text(document.form_type, "form_type", reject_path_separators=False),
            primary_document=primary_document,
            meta=_download_document_meta(document.meta),
        )
        token = self.batching_repository.begin_batch(ticker)
        commit_started = False
        try:
            if source_exists:
                self.source_repository.reset_source_document(
                    ticker,
                    document_id,
                    document.source_kind,
                    batch=token,
                )
            handle = SourceHandle(
                ticker=ticker,
                document_id=document_id,
                source_kind=document.source_kind.value,
            )
            file_metas = tuple(
                self._store_downloaded_file(
                    handle=handle,
                    downloaded_file=downloaded_file,
                    batch=token,
                )
                for downloaded_file in document.files
            )
            self.source_repository.create_source_document(
                replace(create_request, files=list(file_metas)),
                document.source_kind,
                batch=token,
            )
            # commit_batch 调用开始即由 storage owner 消费 token；提交失败后
            # caller 不得尝试二次 rollback。
            commit_started = True
            self.batching_repository.commit_batch(token)
        finally:
            if not commit_started:
                _rollback_batch_before_commit(self.batching_repository, token)
        return True

    def _store_downloaded_file(
        self,
        *,
        handle: SourceHandle | ProcessedHandle,
        downloaded_file: FinsDownloadedFile,
        batch: BatchToken,
    ) -> FileObjectMeta:
        """通过 blob 仓储保存单个下载文件。

        Args:
            handle: source 或 processed 文档句柄。
            downloaded_file: adapter 返回的文件。
            batch: caller 显式传入的 batch capability。

        Returns:
            文件对象元数据。

        Raises:
            ValueError: 文件名或元数据非法时抛出。
            OSError: 仓储写入失败时抛出。
        """

        return self.blob_repository.store_file(
            handle,
            _bounded_text(downloaded_file.filename, "filename"),
            BytesIO(downloaded_file.content),
            batch=batch,
            content_type=_optional_bounded_text(
                downloaded_file.content_type, "content_type", reject_path_separators=False
            ),
            metadata=_bounded_metadata(downloaded_file.metadata),
        )

    def _store_rejected_filing_artifact(
        self,
        *,
        ticker: str,
        artifact: FinsRejectedFilingDownloadArtifact,
    ) -> None:
        """保存 rejected filing artifact。

        Args:
            ticker: 标准化 ticker。
            artifact: adapter 返回的 rejected filing artifact。

        Returns:
            无。

        Raises:
            ValueError: artifact 字段非法时抛出。
            OSError: 仓储写入失败时抛出。
        """

        document_id = _bounded_text(artifact.document_id, "rejected_document_id", reject_path_separators=False)
        batch = self.batching_repository.begin_batch(ticker)
        commit_started = False
        try:
            file_entries = tuple(
                self._store_rejected_file_entry(
                    ticker=ticker,
                    document_id=document_id,
                    downloaded_file=downloaded_file,
                    batch=batch,
                )
                for downloaded_file in artifact.files
            )
            self.filing_maintenance_repository.upsert_rejected_filing_artifact(
                RejectedFilingArtifactUpsertRequest(
                    ticker=ticker,
                    document_id=document_id,
                    internal_document_id=_bounded_text(
                        artifact.internal_document_id,
                        "rejected_internal_document_id",
                        reject_path_separators=False,
                    ),
                    accession_number=_bounded_text(
                        artifact.accession_number,
                        "accession_number",
                        reject_path_separators=False,
                    ),
                    company_id=_bounded_text(artifact.company_id, "company_id", reject_path_separators=False),
                    form_type=_bounded_text(artifact.form_type, "rejected_form_type", reject_path_separators=False),
                    filing_date=_bounded_text(artifact.filing_date, "filing_date", reject_path_separators=False),
                    report_date=_optional_bounded_text(
                        artifact.report_date, "report_date", reject_path_separators=False
                    ),
                    primary_document=_bounded_text(artifact.primary_document, "rejected_primary_document"),
                    selected_primary_document=_bounded_text(
                        artifact.selected_primary_document,
                        "selected_primary_document",
                    ),
                    rejection_reason=_bounded_text(
                        artifact.rejection_reason,
                        "rejection_reason",
                        reject_path_separators=False,
                    ),
                    rejection_category=_bounded_text(
                        artifact.rejection_category,
                        "rejection_category",
                        reject_path_separators=False,
                    ),
                    classification_version=_DOWNLOAD_REJECTION_CLASSIFICATION_VERSION,
                    source_fingerprint=_bounded_text(
                        artifact.source_fingerprint,
                        "source_fingerprint",
                        reject_path_separators=False,
                    ),
                    files=list(file_entries),
                    fiscal_year=artifact.fiscal_year,
                    fiscal_period=_optional_bounded_text(artifact.fiscal_period, "fiscal_period"),
                    report_kind=_optional_bounded_text(artifact.report_kind, "report_kind"),
                    amended=artifact.amended,
                    has_xbrl=artifact.has_xbrl,
                    ingest_method=_DOWNLOAD_INGEST_METHOD,
                ),
                batch=batch,
            )
            registry = self.filing_maintenance_repository.load_download_rejection_registry(ticker)
            registry[document_id] = DownloadRejectionEntry(
                document_id=document_id,
                reason=artifact.rejection_reason,
                category=artifact.rejection_category,
                form_type=artifact.form_type,
                filing_date=artifact.filing_date,
                download_version=_DOWNLOAD_REJECTION_CLASSIFICATION_VERSION,
            )
            self.filing_maintenance_repository.save_download_rejection_registry(
                ticker,
                registry,
                batch=batch,
            )
            commit_started = True
            self.batching_repository.commit_batch(batch)
        finally:
            if not commit_started:
                _rollback_batch_before_commit(self.batching_repository, batch)

    def _store_rejected_file_entry(
        self,
        *,
        ticker: str,
        document_id: str,
        downloaded_file: FinsDownloadedFile,
        batch: BatchToken,
    ) -> SourceFileEntry:
        """保存 rejected artifact 文件并转换为 SourceFileEntry。

        Args:
            ticker: 标准化 ticker。
            document_id: rejected artifact 文档 ID。
            downloaded_file: adapter 返回的文件。
            batch: caller 显式传入的 batch capability。

        Returns:
            rejected artifact 元数据中的文件条目。

        Raises:
            ValueError: 文件字段非法时抛出。
            OSError: 仓储写入失败时抛出。
        """

        filename = _bounded_text(downloaded_file.filename, "rejected_filename")
        file_meta = self.filing_maintenance_repository.store_rejected_filing_file(
            ticker,
            document_id,
            filename,
            BytesIO(downloaded_file.content),
            batch=batch,
            content_type=_optional_bounded_text(
                downloaded_file.content_type, "content_type", reject_path_separators=False
            ),
            metadata=_bounded_metadata(downloaded_file.metadata),
        )
        return SourceFileEntry(
            name=filename,
            uri=file_meta.uri,
            etag=file_meta.etag,
            last_modified=file_meta.last_modified,
            size=file_meta.size,
            content_type=file_meta.content_type,
            sha256=file_meta.sha256,
            ingested_at=_utc_now(),
        )

    def _select_preprocess_documents(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        document_ids: tuple[str, ...],
        form_types: tuple[str, ...],
    ) -> tuple[str, ...]:
        """按请求选择待预处理源文档。

        Args:
            ticker: 标准化 ticker。
            source_kind: 源文档类型。
            document_ids: 显式源文档 ID；为空时按 ticker 全量选择。
            form_types: 可选表单过滤。

        Returns:
            有界文档 ID 元组。

        Raises:
            FileNotFoundError: ticker 或显式文档不存在时抛出。
            ValueError: 选择数量超过上限时抛出。
        """

        requested_ids = _bounded_text_tuple(document_ids, "document_ids", reject_path_separators=False)
        requested_forms = _normalize_form_filter(form_types)
        available_ids = tuple(self.source_repository.list_source_document_ids(ticker, source_kind))
        if not available_ids:
            raise FileNotFoundError(f"未找到 ticker={ticker} 的 {source_kind.value} 源文档")
        selected_ids = requested_ids or available_ids

        missing_ids = tuple(document_id for document_id in selected_ids if document_id not in available_ids)
        if missing_ids:
            missing_text = ", ".join(missing_ids[:3])
            raise FileNotFoundError(f"源文档不存在: {missing_text}")

        filtered_ids: list[str] = []
        for document_id in selected_ids:
            meta = self.source_repository.get_source_meta(ticker, document_id, source_kind)
            if bool(meta.get("is_deleted", False)):
                continue
            if meta.get("ingest_complete") is not True:
                continue
            form_type = _optional_bounded_text(_optional_text_from_meta(meta, "form_type"), "form_type")
            if requested_forms and _normalize_form_value(form_type) not in requested_forms:
                continue
            filtered_ids.append(document_id)
        if not filtered_ids:
            raise FileNotFoundError("没有源文档匹配预处理选择条件")
        if len(filtered_ids) > _MAX_PREPROCESS_DOCUMENTS:
            raise ValueError(f"预处理文档数量超过上限: {_MAX_PREPROCESS_DOCUMENTS}")
        return tuple(filtered_ids)

    def _preprocess_one_document(
        self,
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        rebuild_processed: bool,
    ) -> str:
        """处理单个源文档并写入 processed 仓储。

        Args:
            ticker: 标准化 ticker。
            document_id: 源文档 ID。
            source_kind: 源文档类型。
            rebuild_processed: 是否允许覆盖已有 processed 产物。

        Returns:
            ``"processed"`` 或 ``"skipped"``。

        Raises:
            ValueError: 没有可用处理器时抛出。
            FileNotFoundError: 源文档或 processed 更新目标不存在时抛出。
            OSError: 仓储读取或写入失败时抛出。
            RuntimeError: 处理器执行失败时抛出。
        """

        if not rebuild_processed and _processed_exists(self.processed_repository, ticker, document_id):
            return "skipped"

        batch = self.batching_repository.begin_batch(ticker)
        commit_started = False
        try:
            with self.source_repository.read_source_snapshot(
                ticker,
                document_id,
                source_kind,
                materialize_files=True,
            ) as snapshot:
                source_meta = dict(snapshot.source_meta)
                source = snapshot.get_primary_source()
                form_type = _optional_bounded_text(
                    _optional_text_from_meta(source_meta, "form_type"),
                    "form_type",
                )
                try:
                    processor = self.processor_registry.create_with_fallback(
                        source=source,
                        form_type=form_type,
                        media_type=source.media_type,
                    )
                except ValueError as exc:
                    raise _PreprocessNotSupportedError(str(exc)) from exc
                sections = _build_processed_sections(processor)
                tables = _build_processed_tables(processor)
                processed_meta = _build_processed_meta(
                    source_meta=source_meta,
                    parser_version=processor.get_parser_version(),
                )
                if _processed_exists(self.processed_repository, ticker, document_id):
                    self.processed_repository.update_processed(
                        ProcessedUpdateRequest(
                            ticker=ticker,
                            document_id=document_id,
                            internal_document_id=_internal_document_id(source_meta, document_id),
                            source_kind=source_kind.value,
                            form_type=form_type,
                            meta=processed_meta,
                            sections=sections,
                            tables=tables,
                            financials=None,
                        ),
                        batch=batch,
                    )
                else:
                    self.processed_repository.create_processed(
                        ProcessedCreateRequest(
                            ticker=ticker,
                            document_id=document_id,
                            internal_document_id=_internal_document_id(source_meta, document_id),
                            source_kind=source_kind.value,
                            form_type=form_type,
                            meta=processed_meta,
                            sections=sections,
                            tables=tables,
                            financials=None,
                        ),
                        batch=batch,
                    )
            commit_started = True
            self.batching_repository.commit_batch(batch)
        finally:
            if not commit_started:
                _rollback_batch_before_commit(self.batching_repository, batch)
        return "processed"

    def _save_succeeded(
        self,
        record: FinsIngestionJobRecord,
        result_summary: dict[str, JsonValue],
    ) -> FinsIngestionJobRecord:
        """保存 succeeded 终态。

        Args:
            record: 当前 job record。
            result_summary: 有界业务结果摘要。

        Returns:
            更新后的 job record。

        Raises:
            OSError: job store 写入失败时抛出。
            ValueError: 摘要非法时抛出。
        """

        _assert_bounded_summary(result_summary, "result_summary")
        now = _utc_now()
        saved = self.job_store.save_succeeded_or_cancelled(
            record.job_id,
            result_summary=result_summary,
            finished_at=now,
        )
        self._append_terminal_job_event_warn(saved)
        return saved

    def _save_cancelled(self, record: FinsIngestionJobRecord) -> FinsIngestionJobRecord:
        """保存 cancelled 终态。

        Args:
            record: 当前 job record。

        Returns:
            更新后的 job record。

        Raises:
            OSError: job store 写入失败时抛出。
        """

        now = _utc_now()
        saved = self.job_store.save_cancelled_if_active(record.job_id, finished_at=now)
        self._append_terminal_job_event_warn(saved)
        return saved

    def _save_failed(
        self,
        record: FinsIngestionJobRecord,
        *,
        message: str,
        result_summary: dict[str, JsonValue] | None = None,
    ) -> FinsIngestionJobRecord:
        """保存 failed 终态。

        Args:
            record: 当前 job record。
            message: 有界失败说明。
            result_summary: 可选业务结果摘要。

        Returns:
            更新后的 job record。

        Raises:
            OSError: job store 写入失败时抛出。
            ValueError: 摘要非法时抛出。
        """

        failure_summary: dict[str, JsonValue] = {
            "message": _bounded_text(
                message,
                "failure_message",
                reject_path_separators=False,
            )
        }
        _assert_bounded_summary(failure_summary, "failure_summary")
        final_result = result_summary or dict(_EMPTY_SUMMARY)
        _assert_bounded_summary(final_result, "result_summary")
        now = _utc_now()
        saved = self.job_store.save_failed_or_cancelled_if_active(
            record.job_id,
            failure_summary=failure_summary,
            result_summary=final_result,
            finished_at=now,
        )
        self._append_terminal_job_event_warn(saved)
        return saved

    def _save_download_unsupported(
        self,
        job_id: str,
        *,
        request: FinsDownloadRequest,
        message: str,
    ) -> None:
        """把 unsupported-source 下载结果保存为 failed 终态。

        Args:
            job_id: opaque job id。
            request: owner 已校验的下载请求。
            message: 有界失败说明。

        Returns:
            无。

        Raises:
            无。二次落盘失败只记录诊断。
        """

        try:
            record = self.job_store.read_job(job_id)
            if record.status in _TERMINAL_STATUSES:
                return
            self._save_failed(
                record,
                message=message,
                result_summary=_empty_download_summary_from_request(
                    request,
                    terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
                ).to_json_summary(),
            )
        except Exception as terminal_exc:
            _LOGGER.warning(
                "fins.ingestion.download_unsupported_terminalization_failed job_id=%s error_type=%s",
                job_id,
                type(terminal_exc).__name__,
                exc_info=True,
            )
            return

    def _save_failed_from_exception(self, job_id: str, exc: Exception) -> None:
        """把后台异常转换为 failed job record。

        Args:
            job_id: opaque job id。
            exc: 后台执行异常。

        Returns:
            无。

        Raises:
            无。
        """

        try:
            record = self.job_store.read_job(job_id)
            if record.status in _TERMINAL_STATUSES:
                return
            self._save_failed(record, message=str(exc) or type(exc).__name__)
        except Exception as terminal_exc:
            _LOGGER.warning(
                "fins.ingestion.failed_terminalization_failed job_id=%s error_type=%s original_error_type=%s",
                job_id,
                type(terminal_exc).__name__,
                type(exc).__name__,
                exc_info=True,
            )
            return

    def _append_terminal_job_event_warn(self, record: FinsIngestionJobRecord) -> None:
        """为 terminal job record 追加 terminal event，失败只记录 WARN。

        Args:
            record: 已保存的 job record。

        Returns:
            无。

        Raises:
            无。
        """

        event_type = _terminal_event_type_from_status(record.status)
        if event_type is None:
            return
        self._append_job_event_warn(
            record,
            event_type=event_type,
            message=_terminal_event_message(record.status),
            payload={},
        )

    def _emit_progress_event(
        self,
        record: FinsIngestionJobRecord,
        *,
        source_event_type: str,
        message: str,
        document_id: str | None,
        payload: dict[str, JsonValue],
    ) -> None:
        """追加 runtime-owned progress event，失败时记录 bounded WARN 并继续。

        Args:
            record: 事件对应的 running job record 快照。
            source_event_type: runtime 内部进度标签，只用于消费方展示分类。
            message: 有界进度说明。
            document_id: 可选业务文档 ID；不得放本地文件路径。
            payload: 有界 JSON-compatible 业务摘要。

        Returns:
            无。

        Raises:
            无。
        """

        try:
            self.job_store.append_job_event(
                record.job_id,
                FinsIngestionJobEventAppend(
                    operation_kind=record.operation_kind,
                    status=record.status,
                    event_type=FinsIngestionJobEventType.PROGRESS,
                    source_event_type=source_event_type,
                    source_kind=record.source_kind,
                    document_id=document_id,
                    message=message,
                    payload=payload,
                    emitted_at=_utc_now(),
                ),
            )
        except Exception as exc:
            payload_keys = ",".join(sorted(payload.keys()))
            _LOGGER.warning(
                "fins.ingestion.job_event_append_failed "
                "job_id=%s operation_kind=%s event_type=%s source_event_type=%s "
                "payload_key_count=%s payload_keys=%s error_type=%s error_summary=%s",
                record.job_id,
                record.operation_kind.value,
                FinsIngestionJobEventType.PROGRESS.value,
                _bounded_log_text(source_event_type),
                len(payload),
                _bounded_log_text(payload_keys),
                type(exc).__name__,
                "event_append_failed",
            )

    def _emit_context_progress(
        self,
        context: _FinsIngestionExecutionContext,
        *,
        source_event_type: str,
        message: str,
        document_id: str | None,
        payload: dict[str, JsonValue],
    ) -> None:
        """按执行上下文投递 progress。

        Args:
            context: legacy job 或 direct stream 执行上下文。
            source_event_type: runtime 内部进度标签。
            message: 用户可读进度说明。
            document_id: 可选业务文档 ID。
            payload: 有界业务摘要。

        Returns:
            无。

        Raises:
            无。legacy sidecar 失败只记录 WARN；direct queue 关闭时停止投递。
        """

        if context.job_record is not None:
            self._emit_progress_event(
                context.job_record,
                source_event_type=source_event_type,
                message=message,
                document_id=document_id,
                payload=payload,
            )
            return
        event = _direct_progress_event(
            context=context,
            source_event_type=source_event_type,
            message=message,
            document_id=document_id,
            payload=payload,
        )
        _put_direct_queue(context, event)

    def _emit_download_adapter_progress(
        self,
        context: _FinsIngestionExecutionContext,
        event: FinsDownloadProgressEvent,
    ) -> None:
        """投递 source-specific adapter 下载进度。

        Args:
            context: 当前 ingestion 执行上下文。
            event: adapter 回传的下载进度。

        Returns:
            无。

        Raises:
            ValueError: stage、message、document_id、file_name 或 payload 非法时抛出。
        """

        payload = dict(event.payload)
        display_document = event.file_name or event.document_id
        if event.file_name is not None:
            payload[_PAYLOAD_FILE_NAME] = _bounded_text(
                event.file_name,
                _PAYLOAD_FILE_NAME,
                reject_path_separators=False,
            )
        bounded_payload = validate_bounded_job_event_payload(payload, "download_progress_payload")
        self._emit_context_progress(
            context,
            source_event_type=_bounded_text(event.stage, "download_progress_stage"),
            message=_bounded_text(event.message, "download_progress_message", reject_path_separators=False),
            document_id=display_document,
            payload=bounded_payload,
        )

    def _emit_direct_result(
        self,
        context: _FinsIngestionExecutionContext,
        *,
        status: FinsResultStatus,
        details: tuple[FinsEventDetail, ...],
        error_kind: FinsErrorKind | None,
        error_message: str | None,
        download: FinsDownloadPublicSummary | None = None,
        failure: FinsPublicFailure | None = None,
    ) -> None:
        """向 direct stream 投递唯一终态 RESULT。

        Args:
            context: direct stream 执行上下文。
            status: 终态状态。
            details: 有界业务摘要详情。
            error_kind: 可选失败分类。
            error_message: 可选失败说明。
            download: download 操作的 bounded public summary。
            failure: download 失败的 closed public failure。

        Returns:
            无。

        Raises:
            无。legacy job context 不投递 direct RESULT。
        """

        if context.direct_queue is None:
            return
        cancellation_state = context.cancellation_state
        if cancellation_state is not None:
            context.cancellation_checker()
        resolved_status = status if cancellation_state is None else cancellation_state.claim_terminal(status)
        if resolved_status is None:
            return
        status = resolved_status
        if status is FinsResultStatus.CANCELLED:
            details = ()
            error_kind = FinsErrorKind.CANCELLED
            error_message = direct_failure_message(
                error_kind=FinsErrorKind.CANCELLED,
                fallback_message=None,
            )
            download = (
                None
                if context.download_request is None
                else _public_download_summary(
                    _empty_download_summary_from_request(
                        context.download_request,
                        terminal_disposition=FinsDownloadTerminalDisposition.CANCELLED,
                    )
                )
            )
            failure = None
        exit_code = _direct_exit_code(status)
        title = direct_result_title(
            operation_kind=context.direct_operation_kind,
            status=status,
        )
        event = FinsEvent(
            event_type=FinsEventType.RESULT,
            operation_kind=context.direct_operation_kind,
            message=title,
            emitted_at=datetime.now(timezone.utc),
            ticker=context.normalized_ticker,
            filing_kind=_direct_filing_kind(context.source_kind),
            document_label=None,
            progress=None,
            result=FinsResultSummary(
                status=status,
                exit_code=exit_code,
                title=title,
                details=details,
                error_kind=error_kind,
                error_message=error_message,
                download=download,
                failure=failure,
            ),
        )
        _put_direct_queue(context, event)

    def _emit_direct_cancelled_result(self, context: _FinsIngestionExecutionContext) -> None:
        """向 direct stream 投递取消 RESULT。

        Args:
            context: direct stream 执行上下文。

        Returns:
            无。

        Raises:
            无。
        """

        self._emit_direct_result(
            context,
            status=FinsResultStatus.CANCELLED,
            details=(),
            error_kind=FinsErrorKind.CANCELLED,
            error_message=direct_failure_message(
                error_kind=FinsErrorKind.CANCELLED,
                fallback_message=None,
            ),
            download=(
                None
                if context.download_request is None
                else _public_download_summary(
                    _empty_download_summary_from_request(
                        context.download_request,
                        terminal_disposition=FinsDownloadTerminalDisposition.CANCELLED,
                    )
                )
            ),
            failure=None,
        )

    def _append_job_event_warn(
        self,
        record: FinsIngestionJobRecord,
        *,
        event_type: FinsIngestionJobEventType,
        message: str,
        payload: dict[str, JsonValue],
    ) -> None:
        """追加 job event，失败时记录 bounded WARN 并保持 job record 不变。

        Args:
            record: 事件对应的 job record 快照。
            event_type: 事件类型。
            message: 有界事件说明。
            payload: 有界 JSON-compatible 事件摘要。

        Returns:
            无。

        Raises:
            无。
        """

        try:
            self.job_store.append_job_event(
                record.job_id,
                FinsIngestionJobEventAppend(
                    operation_kind=record.operation_kind,
                    status=record.status,
                    event_type=event_type,
                    source_event_type=None,
                    source_kind=record.source_kind,
                    document_id=None,
                    message=message,
                    payload=payload,
                    emitted_at=_utc_now(),
                ),
            )
        except Exception as exc:
            payload_keys = ",".join(sorted(payload.keys()))
            _LOGGER.warning(
                "fins.ingestion.job_event_append_failed "
                "job_id=%s operation_kind=%s event_type=%s payload_key_count=%s "
                "payload_keys=%s error_type=%s error_summary=%s",
                record.job_id,
                record.operation_kind.value,
                event_type.value,
                len(payload),
                _bounded_log_text(payload_keys),
                type(exc).__name__,
                "event_append_failed",
            )


def _direct_queue_get(
    queue: Queue[_DirectStreamQueueItem],
    thread: Thread,
) -> _DirectStreamQueueItem | None:
    """从 direct stream queue 读取一项。

    Args:
        queue: direct stream producer queue。
        thread: producer 线程。

    Returns:
        queue item；超时但 producer 仍存活时返回 ``None``；producer 退出且
        queue 空时返回完成哨兵。

    Raises:
        无。
    """

    try:
        return queue.get(timeout=_DIRECT_QUEUE_GET_TIMEOUT_SECONDS)
    except Empty:
        if thread.is_alive():
            return None
        return _DirectStreamProducerDone()


def _put_direct_queue(
    context: _FinsIngestionExecutionContext,
    item: _DirectStreamQueueItem,
) -> bool:
    """向 direct stream queue 投递事件。

    Args:
        context: direct stream 执行上下文。
        item: 待投递 queue item。

    Returns:
        成功投递返回 ``True``；stream 已关闭或没有 direct queue 时返回 ``False``。

    Raises:
        无。
    """

    queue = context.direct_queue
    if queue is None:
        return False
    while True:
        cancellation_state = context.cancellation_state
        if cancellation_state is not None and cancellation_state.is_consumer_aborted():
            # consumer 已结束时丢弃后续事件，避免同步 producer 卡在无人读取的队列上。
            return False
        try:
            queue.put(item, timeout=_DIRECT_QUEUE_PUT_TIMEOUT_SECONDS)
            return True
        except Full:
            continue


def _direct_progress_event(
    *,
    context: _FinsIngestionExecutionContext,
    source_event_type: str,
    message: str,
    document_id: str | None,
    payload: Mapping[str, JsonValue],
) -> FinsEvent:
    """构造用户可见 direct progress event。

    Args:
        context: direct stream 执行上下文。
        source_event_type: runtime 进度阶段。
        message: 用户可读进度说明。
        document_id: 可选业务文档 ID。
        payload: 有界业务摘要。

    Returns:
        Fins direct progress event。

    Raises:
        ValueError: 投影文本不满足 direct event 泄漏保护时抛出。
    """

    completed_units, total_units = _direct_progress_units(source_event_type, payload)
    return FinsEvent(
        event_type=FinsEventType.PROGRESS,
        operation_kind=context.direct_operation_kind,
        message=message,
        emitted_at=datetime.now(timezone.utc),
        ticker=context.normalized_ticker,
        filing_kind=_direct_filing_kind(context.source_kind),
        document_label=_direct_document_label(document_id),
        progress=FinsProgress(
            stage=source_event_type,
            completed_units=completed_units,
            total_units=total_units,
        ),
        result=None,
    )


def _direct_progress_units(
    source_event_type: str,
    payload: Mapping[str, JsonValue],
) -> tuple[int | None, int | None]:
    """从 progress payload 提取用户可见工作单元计数。

    Args:
        source_event_type: runtime 进度阶段。
        payload: 有界业务摘要。

    Returns:
        ``(completed_units, total_units)``。

    Raises:
        无。
    """

    if source_event_type == _PROGRESS_PREPROCESS_SELECTED:
        selected = _optional_payload_int(payload, _PAYLOAD_SELECTED_COUNT)
        return (0, selected)
    if source_event_type in {
        _PROGRESS_PREPROCESS_DOCUMENT_STARTED,
        _PROGRESS_PREPROCESS_DOCUMENT_PROCESSED,
        _PROGRESS_PREPROCESS_DOCUMENT_SKIPPED,
        _PROGRESS_PREPROCESS_DOCUMENT_FAILED,
        _PROGRESS_PREPROCESS_DOCUMENT_NOT_SUPPORTED,
    }:
        index = _optional_payload_int(payload, _PAYLOAD_DOCUMENT_INDEX)
        total = _optional_payload_int(payload, _PAYLOAD_DOCUMENT_TOTAL)
        return (index, total)
    if source_event_type == _PROGRESS_PREPROCESS_COMPLETED:
        processed = _optional_payload_int(payload, _PAYLOAD_PROCESSED_COUNT)
        selected = _optional_payload_int(payload, _PAYLOAD_SELECTED_COUNT)
        return (processed, selected)
    if source_event_type in {
        _PROGRESS_DOWNLOAD_COMPLETED,
        _PROGRESS_DOWNLOAD_COMPLETED_WITH_FAILURES,
    }:
        downloaded = _optional_payload_int(payload, _PAYLOAD_DOWNLOADED_COUNT)
        discovered = _optional_payload_int(payload, _PAYLOAD_DISCOVERED_COUNT)
        return (downloaded, discovered)
    if source_event_type in {
        _PROGRESS_UPLOAD_COMPLETED,
        _PROGRESS_UPLOAD_COMPLETED_WITH_FAILURES,
    }:
        return (1, 1)
    return (None, None)


def _optional_payload_int(payload: Mapping[str, JsonValue], key: str) -> int | None:
    """从 payload 读取可选整数。

    Args:
        payload: JSON-compatible payload。
        key: 字段名。

    Returns:
        整数值或 ``None``。

    Raises:
        无。
    """

    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _direct_document_label(document_id: str | None) -> str | None:
    """构造 direct event 的文档短标签。

    Args:
        document_id: 可选业务文档 ID。

    Returns:
        文档短标签；为空时返回 ``None``。

    Raises:
        ValueError: 文档 ID 非法时抛出。
    """

    if document_id is None:
        return None
    return _bounded_text(document_id, "direct_document_label", reject_path_separators=False)


def _direct_filing_kind(source_kind: SourceKind | None) -> str | None:
    """把 source kind 投影为 direct event 短标签。

    Args:
        source_kind: 可选源文档类别。

    Returns:
        用户可理解的短标签。

    Raises:
        无。
    """

    if source_kind is None:
        return None
    return source_kind.value


def _direct_upload_operation_kind(request: FinsUploadRequest) -> FinsOperationKind:
    """按上传请求类型选择 direct operation kind。

    Args:
        request: 上传请求。

    Returns:
        filing 或 material 上传操作类型。

    Raises:
        无。
    """

    if isinstance(request, FinsUploadFilingRequest):
        return FinsOperationKind.UPLOAD_FILING
    if isinstance(request, FinsUploadMaterialRequest):
        return FinsOperationKind.UPLOAD_MATERIAL
    assert_never(request)


def _direct_exit_code(status: FinsResultStatus) -> int:
    """返回 direct result status 对应退出码。

    Args:
        status: direct 终态状态。

    Returns:
        固定退出码。

    Raises:
        无。
    """

    if status is FinsResultStatus.SUCCESS:
        return FINS_RESULT_EXIT_SUCCESS
    if status is FinsResultStatus.FAILURE:
        return FINS_RESULT_EXIT_FAILURE
    if status is FinsResultStatus.CANCELLED:
        return FINS_RESULT_EXIT_CANCELLED
    assert_never(status)


def _public_download_summary(
    summary: _FinsDownloadResultSummary,
) -> FinsDownloadPublicSummary:
    """从 operation-local typed rows 构造唯一 bounded public summary。

    Args:
        summary: source adapter 返回的完整 typed summary。

    Returns:
        CLI 与 wait adapter 共享的 bounded public object。

    Raises:
        ValueError: public summary 不变量失败时由 contract 抛出。
    """

    public_rows = tuple(
        FinsDownloadPublicDocument(
            document_id=row.document_id,
            form_or_period=row.form_or_period,
            filing_date=row.filing_date,
            report_date=row.report_date,
            disposition=row.disposition,
            reason_category=row.reason_category,
            reason_message=row.reason_message,
            artifact_locator=(None if row.artifact_locator is None else row.artifact_locator.as_posix()),
        )
        for row in summary.document_rows[:FINS_DOWNLOAD_PUBLIC_MAX_DOCUMENT_ROWS]
    )
    omitted_count = summary.discovered_count - len(public_rows)
    return FinsDownloadPublicSummary(
        source=summary.source,
        canonical_ticker=summary.canonical_ticker,
        effective_filters=summary.effective_filters,
        discovered_count=summary.discovered_count,
        downloaded_count=summary.downloaded_count,
        skipped_count=summary.skipped_count,
        rejected_count=summary.rejected_count,
        failed_count=summary.failed_count,
        document_rows=public_rows,
        missing_periods=summary.missing_periods,
        omitted_count=omitted_count,
        terminal_disposition=summary.terminal_disposition,
    )


def _empty_download_summary_from_request(
    request: FinsDownloadRequest,
    *,
    terminal_disposition: FinsDownloadTerminalDisposition,
) -> _FinsDownloadResultSummary:
    """为 adapter 完成前的失败/取消构造同源空下载摘要。

    Args:
        request: 已完成静态校验的 download request。
        terminal_disposition: adapter 完成前由 runtime owner 确定的失败或取消终态。

    Returns:
        只承诺 request 已知 filters、零 candidate 的 typed summary。

    Raises:
        ValueError: contract 不变量失败时抛出。
    """

    return _FinsDownloadResultSummary(
        source=request.source,
        canonical_ticker=request.normalized_ticker.canonical,
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=request.form_types,
            start_date=request.date_range.start_text,
            end_date=request.date_range.end_text,
            overwrite_existing=request.overwrite_existing,
            rebuild_local_artifacts=request.rebuild_local_artifacts,
        ),
        discovered_count=0,
        downloaded_count=0,
        skipped_count=0,
        rejected_count=0,
        failed_count=0,
        document_rows=(),
        terminal_disposition=terminal_disposition,
        missing_periods=(),
    )


def _download_public_failure_from_exception(
    exc: Exception,
    *,
    request: FinsDownloadRequest,
) -> FinsPublicFailure:
    """把 download owner exception 映射为 closed public failure。

    Args:
        exc: source adapter/runtime owner 抛出的异常。
        request: 当前 typed request。

    Returns:
        不复制 raw exception、URL、路径或 provider payload 的 public failure。

    Raises:
        ValueError: public failure contract 校验失败时抛出。
    """

    if isinstance(exc, FinsDownloadProviderError):
        kind = (
            FinsPublicFailureKind.CONFIGURATION
            if exc.transport_category is FinsDownloadTransportCategory.UNCONFIGURED
            else FinsPublicFailureKind.PROVIDER_TRANSPORT
        )
        retry_hint = (
            "请检查来源身份配置后重新发起下载。"
            if kind is FinsPublicFailureKind.CONFIGURATION
            else (
                "请稍后重试；若持续失败，请检查来源服务状态。"
                if exc.retryable
                else "请检查请求筛选条件或来源响应状态后重试。"
            )
        )
        return FinsPublicFailure(
            kind=kind,
            source=exc.source,
            transport_category=exc.transport_category,
            safe_message=exc.safe_message,
            retry_hint=retry_hint,
        )
    if isinstance(exc, OSError):
        return FinsPublicFailure(
            kind=FinsPublicFailureKind.STORAGE,
            source=request.source,
            transport_category=None,
            safe_message="下载产物读写失败",
            retry_hint="请确认工作区可读写后重新发起下载。",
        )
    return FinsPublicFailure(
        kind=FinsPublicFailureKind.EXECUTION,
        source=request.source,
        transport_category=None,
        safe_message="下载执行失败",
        retry_hint="请重新发起下载；若持续失败，请检查运行日志中的脱敏分类。",
    )


def _preprocess_result_details(summary: FinsPreprocessResultSummary) -> tuple[FinsEventDetail, ...]:
    """构造预处理 direct result 详情。

    Args:
        summary: 预处理结果摘要。

    Returns:
        有界业务可读详情。

    Raises:
        ValueError: 摘要字段非法时抛出。
    """

    json_summary = summary.to_json_summary()
    return (
        FinsEventDetail("selected", str(json_summary["selected_count"])),
        FinsEventDetail("processed", str(json_summary["processed_count"])),
        FinsEventDetail("skipped", str(json_summary["skipped_count"])),
        FinsEventDetail("failed", str(json_summary["failed_count"])),
        FinsEventDetail("not supported", str(json_summary["not_supported_count"])),
    )


def _upload_result_details(summary: FinsUploadResultSummary) -> tuple[FinsEventDetail, ...]:
    """构造上传 direct result 详情。

    Args:
        summary: 上传结果摘要。

    Returns:
        有界业务可读详情。

    Raises:
        ValueError: 摘要字段非法时抛出。
    """

    json_summary = summary.to_json_summary()
    details = [
        FinsEventDetail("source kind", str(json_summary["source_kind"])),
        FinsEventDetail("status", str(json_summary["status"])),
    ]
    document_id = json_summary.get("document_id")
    if isinstance(document_id, str) and document_id:
        details.append(FinsEventDetail("document", document_id))
    uploaded_files = json_summary.get("uploaded_files")
    if isinstance(uploaded_files, list):
        details.append(FinsEventDetail("uploaded files", str(len(uploaded_files))))
    return tuple(details)


def _required_upload_result_text(result: Mapping[str, JsonValue], key: str) -> str:
    """从 upload pipeline result 读取必填文本字段。

    Args:
        result: pipeline 上传结果。
        key: 字段名。

    Returns:
        非空文本字段。

    Raises:
        ValueError: 字段缺失、类型不是字符串或字符串为空时抛出。
    """

    value = result.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"upload pipeline result 缺少必填文本字段: {key}")


def _optional_upload_result_text(result: Mapping[str, JsonValue], key: str) -> str | None:
    """从 upload pipeline result 读取可选文本字段。

    Args:
        result: pipeline 上传结果。
        key: 字段名。

    Returns:
        非空文本字段；缺失时返回 ``None``。

    Raises:
        ValueError: 字段存在但不是字符串或为空字符串时抛出。
    """

    value = result.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"upload pipeline result 字段必须是非空文本: {key}")


def _optional_upload_result_bool(result: Mapping[str, JsonValue], key: str) -> bool | None:
    """从 upload pipeline result 读取可选布尔字段。

    Args:
        result: pipeline 上传结果。
        key: 字段名。

    Returns:
        布尔字段；缺失时返回 ``None``。

    Raises:
        ValueError: 字段存在但不是布尔值时抛出。
    """

    value = result.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"upload pipeline result 字段必须是布尔值: {key}")


def _classify_direct_error(
    exc: Exception,
    *,
    operation_kind: FinsOperationKind,
) -> FinsErrorKind:
    """把 runtime 异常归类为 direct error kind。

    Args:
        exc: runtime 异常。
        operation_kind: 当前 direct operation。

    Returns:
        direct 失败分类。

    Raises:
        无。
    """

    if isinstance(exc, FinsDownloadProviderError):
        return FinsErrorKind.PROVIDER
    if operation_kind is FinsOperationKind.DOWNLOAD:
        if isinstance(exc, OSError):
            return FinsErrorKind.STORAGE
        return FinsErrorKind.EXECUTION
    if isinstance(exc, _UnsupportedDownloadSourceError | ValueError | FileNotFoundError):
        return FinsErrorKind.USER_INPUT
    if isinstance(exc, OSError):
        return FinsErrorKind.STORAGE
    if isinstance(exc, RuntimeError):
        return FinsErrorKind.EXECUTION
    return FinsErrorKind.UNKNOWN


def _safe_direct_error_message(exc: Exception, *, error_kind: FinsErrorKind) -> str:
    """构造不会泄漏路径、job id 或 raw payload 的 direct 错误说明。

    Args:
        exc: runtime 异常。
        error_kind: runtime 异常分类。

    Returns:
        有界错误说明。

    Raises:
        无。
    """

    message = " ".join((str(exc) or type(exc).__name__).split())
    lowered = message.lower()
    if (
        not message
        or "/" in message
        or "\\" in message
        or "finsjob_" in message
        or "job_id" in lowered
        or "cursor" in lowered
        or "raw payload" in lowered
        or "provider payload" in lowered
    ):
        return direct_failure_message(error_kind=error_kind, fallback_message=None)
    if len(message) > _MAX_TEXT_CHARS:
        message = message[:_MAX_TEXT_CHARS]
    return direct_failure_message(error_kind=error_kind, fallback_message=message)


def _new_job_id() -> str:
    """生成新的 opaque job id。

    Args:
        无。

    Returns:
        ASCII job id。

    Raises:
        无。
    """

    return f"{_JOB_ID_PREFIX}{uuid.uuid4().hex}"


def _new_observation_handle(operation_kind: FinsOperationKind) -> FinsObservationHandle:
    """生成新的 process-local observation handle。

    Args:
        operation_kind: Fins 业务操作类型。

    Returns:
        lightweight observation handle。

    Raises:
        ValueError: handle 字段非法时由契约构造抛出。
    """

    return FinsObservationHandle(
        handle_id=f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}{uuid.uuid4().hex}",
        operation_kind=operation_kind,
        created_at=datetime.now(timezone.utc),
    )


def _lost_observation_snapshot(handle: FinsObservationHandle) -> FinsObservationSnapshot:
    """构造 process-local observation 丢失快照。

    Args:
        handle: Host wait record 中保存的 lightweight handle。

    Returns:
        LOST observation snapshot。

    Raises:
        ValueError: snapshot 字段非法时由契约构造抛出。
    """

    return FinsObservationSnapshot(
        handle=handle,
        status=FinsObservationStatus.LOST,
        message="Observation is no longer available.",
        result=None,
        error_kind=FinsErrorKind.UNKNOWN,
        retry_after_seconds=None,
    )


def _observation_status_from_result(status: FinsResultStatus) -> FinsObservationStatus:
    """把 direct result status 映射为 observation status。

    Args:
        status: Fins direct result status。

    Returns:
        observation terminal status。

    Raises:
        AssertionError: status 枚举出现未覆盖值时抛出。
    """

    if status is FinsResultStatus.SUCCESS:
        return FinsObservationStatus.SUCCEEDED
    if status is FinsResultStatus.FAILURE:
        return FinsObservationStatus.FAILED
    if status is FinsResultStatus.CANCELLED:
        return FinsObservationStatus.CANCELLED
    assert_never(status)


def _observation_retry_after(status: FinsObservationStatus) -> float | None:
    """返回 observation 非终态重试建议。

    Args:
        status: observation 状态。

    Returns:
        非终态返回正有限秒数，终态返回 ``None``。

    Raises:
        无。
    """

    if status in {FinsObservationStatus.PENDING, FinsObservationStatus.RUNNING}:
        return _OBSERVATION_RETRY_AFTER_SECONDS
    return None


def _observation_error_kind(
    status: FinsObservationStatus,
    result: FinsResultSummary | None,
) -> FinsErrorKind | None:
    """返回 observation snapshot 的错误分类。

    Args:
        status: observation 状态。
        result: 可选 terminal result。

    Returns:
        失败、取消或 lost 的错误分类；其他状态返回 ``None``。

    Raises:
        无。
    """

    if result is not None and result.error_kind is not None:
        return result.error_kind
    if status is FinsObservationStatus.CANCELLED:
        return FinsErrorKind.CANCELLED
    if status in {FinsObservationStatus.FAILED, FinsObservationStatus.LOST}:
        return FinsErrorKind.UNKNOWN
    return None


def _observation_failure_result(
    *,
    operation_kind: FinsOperationKind,
    download_request: FinsDownloadRequest | None,
) -> FinsResultSummary:
    """构造 observation producer 异常收口失败摘要。

    Args:
        operation_kind: observation 对应的 direct 业务操作类型。
        download_request: download typed request；其它 operation 为 ``None``。

    Returns:
        Fins result summary。

    Raises:
        ValueError: result 字段非法时由契约构造抛出。
    """

    return FinsResultSummary(
        status=FinsResultStatus.FAILURE,
        exit_code=FINS_RESULT_EXIT_FAILURE,
        title=direct_result_title(
            operation_kind=operation_kind,
            status=FinsResultStatus.FAILURE,
        ),
        details=(),
        error_kind=FinsErrorKind.EXECUTION,
        error_message=direct_failure_message(
            error_kind=FinsErrorKind.EXECUTION,
            fallback_message=None,
        ),
        download=(
            None
            if download_request is None
            else _public_download_summary(
                _empty_download_summary_from_request(
                    download_request,
                    terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
                )
            )
        ),
        failure=(
            None
            if download_request is None
            else FinsPublicFailure(
                kind=FinsPublicFailureKind.EXECUTION,
                source=download_request.source,
                transport_category=None,
                safe_message="下载执行未产生完整终态结果",
                retry_hint="请重新发起下载；若持续失败，请检查运行环境。",
            )
        ),
    )


def _observation_cancelled_result(
    *,
    operation_kind: FinsOperationKind,
    download_request: FinsDownloadRequest | None,
) -> FinsResultSummary:
    """构造 observation prepare 阶段取消摘要。

    Args:
        operation_kind: observation 对应的 direct 业务操作类型。
        download_request: download typed request；其它 operation 为 ``None``。

    Returns:
        Fins result summary。

    Raises:
        ValueError: result 字段非法时由契约构造抛出。
    """

    return FinsResultSummary(
        status=FinsResultStatus.CANCELLED,
        exit_code=FINS_RESULT_EXIT_CANCELLED,
        title=direct_result_title(
            operation_kind=operation_kind,
            status=FinsResultStatus.CANCELLED,
        ),
        details=(),
        error_kind=FinsErrorKind.CANCELLED,
        error_message=direct_failure_message(
            error_kind=FinsErrorKind.CANCELLED,
            fallback_message=None,
        ),
        download=(
            None
            if download_request is None
            else _public_download_summary(
                _empty_download_summary_from_request(
                    download_request,
                    terminal_disposition=FinsDownloadTerminalDisposition.CANCELLED,
                )
            )
        ),
        failure=None,
    )


def _mark_observation_failed(
    record: _FinsObservedOperationRecord,
    message: str,
    error_kind: FinsErrorKind,
) -> None:
    """把 observation record 原地收口为 FAILED。

    Args:
        record: 已在 observation lock 内找到的记录。
        message: 有界失败说明。
        error_kind: 失败分类。

    Returns:
        无。

    Raises:
        ValueError: result 字段非法时由契约构造抛出。
    """

    safe_message = _safe_observation_message(message)
    record.status = FinsObservationStatus.FAILED
    record.message = safe_message
    record.result = FinsResultSummary(
        status=FinsResultStatus.FAILURE,
        exit_code=FINS_RESULT_EXIT_FAILURE,
        title=direct_result_title(
            operation_kind=record.handle.operation_kind,
            status=FinsResultStatus.FAILURE,
        ),
        details=(),
        error_kind=error_kind,
        error_message=direct_failure_message(
            error_kind=error_kind,
            fallback_message=None,
        ),
    )


def _safe_observation_message(message: str) -> str:
    """构造 observation snapshot 使用的安全短消息。

    Args:
        message: runtime event 原始消息。

    Returns:
        不包含路径、job/cursor/token 等片段的短消息。

    Raises:
        无。
    """

    normalized = " ".join(message.split())
    lowered = normalized.lower()
    if (
        normalized == ""
        or "/" in normalized
        or "\\" in normalized
        or "job" in lowered
        or "sequence" in lowered
        or "cursor" in lowered
        or "resume" in lowered
        or "token" in lowered
        or "tool_call" in lowered
        or "storage" in lowered
        or ".dayu" in lowered
    ):
        return "Observation status updated."
    if len(normalized) > _MAX_TEXT_CHARS:
        return normalized[:_MAX_TEXT_CHARS]
    return normalized


def _validate_job_id(job_id: str) -> None:
    """校验 job id。

    Args:
        job_id: opaque job id。

    Returns:
        无。

    Raises:
        ValueError: job id 非法时抛出。
    """

    if _JOB_ID_PATTERN.fullmatch(job_id) is None:
        raise ValueError(f"非法 Fins ingestion job id: {job_id!r}")


def _utc_now() -> str:
    """返回 UTC ISO8601 时间戳。

    Args:
        无。

    Returns:
        UTC ISO8601 字符串。

    Raises:
        无。
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_text(value: str, field_name: str, *, reject_path_separators: bool = True) -> str:
    """校验有界文本字段。

    Args:
        value: 待校验文本。
        field_name: 字段名。
        reject_path_separators: 是否拒绝路径分隔符。

    Returns:
        原文本。

    Raises:
        ValueError: 文本为空、过长或在禁止路径分隔符时包含路径分隔符时抛出。
    """

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} 不能为空")
    if len(text) > _MAX_TEXT_CHARS:
        raise ValueError(f"{field_name} 超出长度上限")
    if reject_path_separators and ("/" in text or "\\" in text):
        raise ValueError(f"{field_name} 不得包含路径分隔符")
    return text


def _optional_bounded_text(
    value: str | None,
    field_name: str,
    *,
    reject_path_separators: bool = True,
) -> str | None:
    """校验可空有界文本字段。

    Args:
        value: 待校验文本或 ``None``。
        field_name: 字段名。
        reject_path_separators: 是否拒绝路径分隔符。

    Returns:
        ``None`` 或原文本。

    Raises:
        ValueError: 文本为空、过长或在禁止路径分隔符时包含路径分隔符时抛出。
    """

    if value is None:
        return None
    return _bounded_text(value, field_name, reject_path_separators=reject_path_separators)


def _bounded_text_tuple(
    values: tuple[str, ...],
    field_name: str,
    *,
    reject_path_separators: bool = True,
) -> tuple[str, ...]:
    """校验有界文本元组。

    Args:
        values: 待校验文本元组。
        field_name: 字段名。
        reject_path_separators: 是否拒绝路径分隔符。

    Returns:
        原文本元组。

    Raises:
        ValueError: 元素数量、元素内容非法时抛出。
    """

    if len(values) > _MAX_TUPLE_ITEMS:
        raise ValueError(f"{field_name} 元素数量超出上限")
    return tuple(_bounded_text(value, field_name, reject_path_separators=reject_path_separators) for value in values)


def _normalize_form_filter(values: tuple[str, ...]) -> frozenset[str]:
    """归一化表单过滤条件。

    Args:
        values: 原始表单类型元组。

    Returns:
        大写后的表单类型集合。

    Raises:
        ValueError: 元素数量、元素内容非法时抛出。
    """

    return frozenset(
        _normalize_form_value(value)
        for value in _bounded_text_tuple(values, "form_types", reject_path_separators=False)
    )


def _normalize_form_value(value: str | None) -> str:
    """归一化单个表单类型。

    Args:
        value: 表单类型或 ``None``。

    Returns:
        大写表单类型；空值返回空字符串。

    Raises:
        无。
    """

    if value is None:
        return ""
    return value.strip().upper()


def _optional_text_from_meta(meta: DocumentMeta, field_name: str) -> str | None:
    """从元数据中读取可选文本字段。

    Args:
        meta: 源文档元数据。
        field_name: 字段名。

    Returns:
        文本字段或 ``None``。

    Raises:
        无。
    """

    value = meta.get(field_name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_download_meta_text(
    meta: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """严格读取 generic download document meta 的可选文本。

    Args:
        meta: typed adapter document 携带的业务 meta。
        field_name: 可选字段名。

    Returns:
        缺失或 ``None`` 返回 ``None``；否则返回非空文本。

    Raises:
        ValueError: 字段存在但不是非空文本时抛出。
    """

    if field_name not in meta or meta[field_name] is None:
        return None
    value = meta[field_name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"download document meta {field_name} 必须是非空文本")
    return value.strip()


def _processed_exists(
    repository: ProcessedDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
) -> bool:
    """判断 processed 文档是否存在。

    Args:
        repository: processed 仓储协议。
        ticker: 标准化 ticker。
        document_id: 文档 ID。

    Returns:
        存在时返回 ``True``，否则返回 ``False``。

    Raises:
        OSError: 底层仓储读取失败时抛出。
        ValueError: 元数据格式非法时抛出。
    """

    try:
        repository.get_processed_meta(ticker, document_id)
    except FileNotFoundError:
        return False
    return True


def _source_document_exists(
    repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> bool:
    """判断源文档是否已存在。

    Args:
        repository: 源文档仓储协议。
        ticker: 标准化 ticker。
        document_id: 源文档 ID。
        source_kind: 源文档类别。

    Returns:
        存在时返回 ``True``，否则返回 ``False``。

    Raises:
        OSError: 底层仓储读取失败时抛出。
        ValueError: 元数据格式非法时抛出。
    """

    try:
        repository.get_source_meta(ticker, document_id, source_kind)
    except FileNotFoundError:
        return False
    return True


def _download_document_meta(meta: Mapping[str, JsonValue]) -> DocumentMeta:
    """构建下载源文档 meta。

    Args:
        meta: adapter 返回的业务元数据。

    Returns:
        可交给 source 仓储写入的元数据。

    Raises:
        ValueError: meta 摘要超过 job 边界上限时抛出。
    """

    _assert_bounded_summary(meta, "download_document_meta")
    result: DocumentMeta = dict(meta)
    result["ingest_method"] = _DOWNLOAD_INGEST_METHOD.to_storage_value()
    result["ingest_complete"] = True
    return result


def _normalize_upload_request(request: FinsUploadRequest) -> FinsUploadRequest:
    """校验并归一化上传请求。

    Args:
        request: 原始上传请求。

    Returns:
        已归一化 action 字段的上传请求。

    Raises:
        ValueError: source_kind、action 或有界字段非法时抛出。
    """

    action = _normalize_upload_action(request.action)
    _validate_upload_source_kind(request)
    if isinstance(request, FinsUploadFilingRequest):
        return replace(request, action=action)
    if isinstance(request, FinsUploadMaterialRequest):
        return replace(request, action=action)
    assert_never(request)


def _normalize_upload_action(action: str) -> str:
    """归一化上传动作字段。

    Args:
        action: 原始上传动作。

    Returns:
        小写上传动作。

    Raises:
        ValueError: 上传动作为空、过长或不在允许集合内时抛出。
    """

    normalized = _bounded_text(action, "upload_action", reject_path_separators=False).lower()
    if normalized not in _UPLOAD_ACTION_VALUES:
        allowed = ", ".join(sorted(_UPLOAD_ACTION_VALUES))
        raise ValueError(f"upload_action 非法: {normalized}; allowed={allowed}")
    return normalized


def _validate_upload_source_kind(request: FinsUploadRequest) -> None:
    """校验上传请求类型与 SourceKind 一致。

    Args:
        request: 上传请求。

    Returns:
        无。

    Raises:
        ValueError: filing/material 请求使用了错误的 ``SourceKind`` 时抛出。
    """

    if isinstance(request, FinsUploadFilingRequest):
        if request.source_kind is not SourceKind.FILING:
            raise ValueError("filing 上传请求必须使用 source_kind=filing")
        return
    if isinstance(request, FinsUploadMaterialRequest):
        if request.source_kind is not SourceKind.MATERIAL:
            raise ValueError("material 上传请求必须使用 source_kind=material")
        return
    assert_never(request)


def _upload_request_summary(request: FinsUploadRequest) -> dict[str, JsonValue]:
    """构建有界上传请求摘要。

    Args:
        request: 已归一化上传请求。

    Returns:
        可进入 job record 的 JSON-compatible 请求摘要；不包含本地文件路径。

    Raises:
        ValueError: 请求字段超出摘要边界时抛出。
    """

    _validate_upload_file_count(request.files)
    summary: dict[str, JsonValue] = {
        "source_kind": request.source_kind.value,
        "action": request.action,
        "file_count": len(request.files),
        "overwrite": request.overwrite,
        "fiscal_year": _optional_non_negative_int(request.fiscal_year, "fiscal_year"),
        "fiscal_period": _optional_bounded_text(
            request.fiscal_period,
            "fiscal_period",
            reject_path_separators=False,
        ),
        "amended": request.amended,
        "filing_date": _optional_bounded_text(
            request.filing_date,
            "filing_date",
            reject_path_separators=False,
        ),
        "report_date": _optional_bounded_text(
            request.report_date,
            "report_date",
            reject_path_separators=False,
        ),
        "company_name": _optional_bounded_text(
            request.company_name,
            "company_name",
            reject_path_separators=False,
        ),
        "ticker_aliases": list(
            _bounded_text_tuple(request.ticker_aliases, "ticker_aliases", reject_path_separators=False)
        ),
    }
    if isinstance(request, FinsUploadMaterialRequest):
        summary.update(
            {
                "form_type": _optional_bounded_text(
                    request.form_type,
                    "form_type",
                    reject_path_separators=False,
                ),
                "material_name": _optional_bounded_text(
                    request.material_name,
                    "material_name",
                    reject_path_separators=False,
                ),
                "document_id": _optional_bounded_text(
                    request.document_id,
                    "document_id",
                    reject_path_separators=False,
                ),
                "internal_document_id": _optional_bounded_text(
                    request.internal_document_id,
                    "internal_document_id",
                    reject_path_separators=False,
                ),
            }
        )
    _assert_bounded_summary(summary, "upload_request_summary")
    return summary


def _validate_upload_file_count(files: tuple[Path, ...]) -> None:
    """校验上传文件数量。

    Args:
        files: 上传请求携带的本地文件路径元组。

    Returns:
        无。

    Raises:
        ValueError: 文件数量超过 job 摘要边界时抛出。
    """

    if len(files) > _MAX_TUPLE_ITEMS:
        raise ValueError("upload_files 元素数量超出上限")


def _optional_non_negative_int(value: int | None, field_name: str) -> int | None:
    """校验可空非负整数。

    Args:
        value: 待校验整数或 ``None``。
        field_name: 字段名。

    Returns:
        原整数或 ``None``。

    Raises:
        ValueError: 数值为负时抛出。
    """

    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{field_name} 不能为负数")
    return value


def _bounded_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
    """校验文件级元数据。

    Args:
        metadata: 文件级元数据。

    Returns:
        有界元数据字典。

    Raises:
        ValueError: 键或值非法时抛出。
    """

    if len(metadata) > _MAX_TUPLE_ITEMS:
        raise ValueError("metadata 元素数量超出上限")
    result: dict[str, str] = {}
    for key, value in metadata.items():
        result[_bounded_text(key, "metadata_key", reject_path_separators=False)] = _bounded_text(
            value, "metadata_value", reject_path_separators=False
        )
    return result


def _non_negative_count(value: int, field_name: str) -> int:
    """校验非负计数字段。

    Args:
        value: 待校验数值。
        field_name: 字段名。

    Returns:
        原数值。

    Raises:
        ValueError: 数值为负时抛出。
    """

    if value < 0:
        raise ValueError(f"{field_name} 不能为负数")
    return value


def _bounded_download_summary(
    summary: _FinsDownloadResultSummary,
) -> _FinsDownloadResultSummary:
    """确认 adapter 已返回 download contract owner 的 typed 摘要。

    Args:
        summary: adapter 返回的下载摘要。

    Returns:
        原 typed 摘要实例。

    Raises:
        TypeError: adapter 返回值不是下载结果 contract 时抛出。
    """

    if not isinstance(summary, _FinsDownloadResultSummary):
        raise TypeError("persisted_summary must use the download result contract")
    return summary


def _validate_download_summary_request_identity(
    summary: _FinsDownloadResultSummary,
    *,
    request: FinsDownloadRequest,
) -> None:
    """校验 adapter summary 没有漂移 typed request 身份与 mutation flags。

    Args:
        summary: source adapter typed summary。
        request: runtime 传入 adapter 的 typed request。

    Returns:
        无。

    Raises:
        ValueError: source、ticker、显式 filters 或 mutation flags 不一致时抛出。
    """

    if summary.source is not request.source:
        raise ValueError("download summary source 与 typed request 不一致")
    if summary.canonical_ticker != request.normalized_ticker.canonical:
        raise ValueError("download summary ticker 与 typed request 不一致")
    filters = summary.effective_filters
    if filters.overwrite_existing is not request.overwrite_existing:
        raise ValueError("download summary overwrite 与 typed request 不一致")
    if filters.rebuild_local_artifacts is not request.rebuild_local_artifacts:
        raise ValueError("download summary rebuild 与 typed request 不一致")
    if request.form_types and frozenset(filters.form_types) != frozenset(request.form_types):
        raise ValueError("download summary forms 与 typed request 不一致")
    if request.date_range.start_is_explicit and (filters.start_date != request.date_range.start_text):
        raise ValueError("download summary explicit start 与 typed request 不一致")
    if request.date_range.end_is_explicit and filters.end_date != request.date_range.end_text:
        raise ValueError("download summary explicit end 与 typed request 不一致")


def _bounded_preprocess_summary(summary: FinsPreprocessResultSummary) -> FinsPreprocessResultSummary:
    """校验预处理结果摘要。

    Args:
        summary: 预处理结果摘要。

    Returns:
        字段已校验的预处理摘要。

    Raises:
        ValueError: 计数为负、分类计数超过选择数量、计数与明细不一致或文档 ID 越界时抛出。
    """

    processed_ids = _bounded_text_tuple(
        summary.processed_document_ids,
        "processed_document_ids",
        reject_path_separators=False,
    )
    skipped_ids = _bounded_text_tuple(
        summary.skipped_document_ids,
        "skipped_document_ids",
        reject_path_separators=False,
    )
    failed_ids = _bounded_text_tuple(
        summary.failed_document_ids,
        "failed_document_ids",
        reject_path_separators=False,
    )
    not_supported_ids = _bounded_text_tuple(
        summary.not_supported_document_ids,
        "not_supported_document_ids",
        reject_path_separators=False,
    )
    bounded = FinsPreprocessResultSummary(
        selected_count=_non_negative_count(summary.selected_count, "selected_count"),
        processed_count=_non_negative_count(summary.processed_count, "processed_count"),
        skipped_count=_non_negative_count(summary.skipped_count, "skipped_count"),
        not_supported_count=_non_negative_count(
            summary.not_supported_count,
            "not_supported_count",
        ),
        failed_count=_non_negative_count(summary.failed_count, "failed_count"),
        processed_document_ids=processed_ids,
        skipped_document_ids=skipped_ids,
        failed_document_ids=failed_ids,
        not_supported_document_ids=not_supported_ids,
    )
    if bounded.processed_count != len(processed_ids):
        raise ValueError("processed_count 必须等于 processed_document_ids 数量")
    if bounded.skipped_count != len(skipped_ids):
        raise ValueError("skipped_count 必须等于 skipped_document_ids 数量")
    if bounded.failed_count != len(failed_ids):
        raise ValueError("failed_count 必须等于 failed_document_ids 数量")
    if bounded.not_supported_count != len(not_supported_ids):
        raise ValueError("not_supported_count 必须等于 not_supported_document_ids 数量")
    categorized_count = (
        bounded.processed_count + bounded.skipped_count + bounded.failed_count + bounded.not_supported_count
    )
    if categorized_count > bounded.selected_count:
        raise ValueError("预处理分类计数总和不得超过 selected_count")
    return bounded


def _download_context_request_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsSourceDownloadAdapterRequest,
) -> dict[str, JsonValue]:
    """构建下载 started progress payload。

    Args:
        context: 单次业务执行上下文。
        request: 传给同步下载 adapter 的请求。

    Returns:
        有界、业务可读且不含路径或正文的 progress payload。

    Raises:
        ValueError: 字段越界时抛出。
    """

    return {
        _PAYLOAD_TICKER: context.normalized_ticker,
        _PAYLOAD_MARKET: context.market,
        _PAYLOAD_SOURCE: request.source.value,
        _PAYLOAD_FORM_TYPES: list(
            _bounded_text_tuple(
                request.form_types,
                _PAYLOAD_FORM_TYPES,
                reject_path_separators=False,
            )
        ),
    }


def _download_context_summary_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsSourceDownloadAdapterRequest,
    summary: _FinsDownloadResultSummary,
) -> dict[str, JsonValue]:
    """构建下载 completed progress payload。

    Args:
        record: 当前 job record。
        request: 传给同步下载 adapter 的请求。
        summary: 有界下载结果摘要。

    Returns:
        只包含 ticker、source、form 与计数的 progress payload。

    Raises:
        ValueError: 摘要字段越界时抛出。
    """

    bounded = _bounded_download_summary(summary)
    payload = _download_context_request_progress_payload(context, request)
    payload.update(
        {
            _PAYLOAD_DISCOVERED_COUNT: bounded.discovered_count,
            _PAYLOAD_DOWNLOADED_COUNT: bounded.downloaded_count,
            _PAYLOAD_SKIPPED_COUNT: bounded.skipped_count,
            _PAYLOAD_REJECTED_COUNT: bounded.rejected_count,
            _PAYLOAD_FAILED_COUNT: bounded.failed_count,
            _PAYLOAD_WRITTEN_DOCUMENT_COUNT: len(bounded.written_document_ids),
        }
    )
    return payload


def _download_completed_progress_type(summary: _FinsDownloadResultSummary) -> str:
    """根据下载摘要选择 completed progress 标签。

    Args:
        summary: 下载结果摘要。

    Returns:
        有失败计数时返回 completed_with_failures，否则返回 completed。

    Raises:
        无。
    """

    if summary.failed_count > 0:
        return _PROGRESS_DOWNLOAD_COMPLETED_WITH_FAILURES
    return _PROGRESS_DOWNLOAD_COMPLETED


def _upload_request_document_id(request: FinsUploadRequest) -> str | None:
    """从上传请求提取可用于 progress 的业务文档 ID。

    Args:
        request: 上传请求。

    Returns:
        material 请求中的显式 document_id；filing 请求返回 ``None``。

    Raises:
        ValueError: 文档 ID 越界时抛出。
    """

    if isinstance(request, FinsUploadMaterialRequest):
        return _optional_bounded_text(
            request.document_id,
            "upload_document_id",
            reject_path_separators=False,
        )
    if isinstance(request, FinsUploadFilingRequest):
        return None
    assert_never(request)


def _upload_context_request_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsUploadRequest,
) -> dict[str, JsonValue]:
    """构建 upload started progress payload。

    Args:
        context: 单次业务执行上下文。
        request: 上传请求。

    Returns:
        只包含 ticker、source_kind、action 与文件数量的 payload。

    Raises:
        ValueError: 请求字段越界时抛出。
    """

    _validate_upload_file_count(request.files)
    return {
        _PAYLOAD_TICKER: context.normalized_ticker,
        _PAYLOAD_MARKET: context.market,
        _PAYLOAD_SOURCE_KIND: request.source_kind.value,
        _PAYLOAD_ACTION: _normalize_upload_action(request.action),
        _PAYLOAD_FILE_COUNT: len(request.files),
    }


def _upload_context_summary_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsUploadRequest,
    summary: FinsUploadResultSummary,
) -> dict[str, JsonValue]:
    """构建 upload completed progress payload。

    Args:
        context: 单次业务执行上下文。
        request: 上传请求。
        summary: 上传结果摘要。

    Returns:
        有界上传 progress payload，不包含本地文件名或路径。

    Raises:
        ValueError: 请求或结果字段越界时抛出。
    """

    payload = _upload_context_request_progress_payload(context, request)
    payload[_PAYLOAD_UPLOAD_STATUS] = _bounded_text(
        summary.status,
        _PAYLOAD_UPLOAD_STATUS,
        reject_path_separators=False,
    )
    if summary.document_id is not None:
        payload[_KEY_DOCUMENT_ID] = _bounded_text(
            summary.document_id,
            _KEY_DOCUMENT_ID,
            reject_path_separators=False,
        )
    return payload


def _upload_completed_progress_type(summary: FinsUploadResultSummary) -> str:
    """根据上传摘要选择 completed progress 标签。

    Args:
        summary: 上传结果摘要。

    Returns:
        failed 状态返回 completed_with_failures，否则返回 completed。

    Raises:
        无。
    """

    if summary.status.strip().lower() == _UPLOAD_RESULT_STATUS_FAILED:
        return _PROGRESS_UPLOAD_COMPLETED_WITH_FAILURES
    return _PROGRESS_UPLOAD_COMPLETED


def _preprocess_selected_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsPreprocessRequest,
    *,
    selected_count: int,
) -> dict[str, JsonValue]:
    """构建 preprocess selected progress payload。

    Args:
        context: 单次业务执行上下文。
        request: 预处理请求。
        selected_count: 已选择文档数量。

    Returns:
        有界 progress payload。

    Raises:
        ValueError: 请求字段或计数字段非法时抛出。
    """

    return {
        _PAYLOAD_TICKER: context.normalized_ticker,
        _PAYLOAD_MARKET: context.market,
        _PAYLOAD_SOURCE_KIND: request.source_kind.value,
        _PAYLOAD_FORM_TYPES: list(
            _bounded_text_tuple(
                request.form_types,
                _PAYLOAD_FORM_TYPES,
                reject_path_separators=False,
            )
        ),
        _PAYLOAD_SELECTED_COUNT: _non_negative_count(selected_count, _PAYLOAD_SELECTED_COUNT),
    }


def _preprocess_document_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsPreprocessRequest,
    *,
    document_index: int,
    document_total: int,
) -> dict[str, JsonValue]:
    """构建单文档 preprocess progress payload。

    Args:
        context: 单次业务执行上下文。
        request: 预处理请求。
        document_index: 当前文档从 1 开始的序号。
        document_total: 总文档数量。

    Returns:
        有界 progress payload。

    Raises:
        ValueError: 计数字段非法时抛出。
    """

    payload = _preprocess_selected_progress_payload(
        context,
        request,
        selected_count=document_total,
    )
    payload[_PAYLOAD_DOCUMENT_INDEX] = _non_negative_count(document_index, _PAYLOAD_DOCUMENT_INDEX)
    payload[_PAYLOAD_DOCUMENT_TOTAL] = _non_negative_count(document_total, _PAYLOAD_DOCUMENT_TOTAL)
    return payload


def _preprocess_summary_progress_payload(
    context: _FinsIngestionExecutionContext,
    request: FinsPreprocessRequest,
    summary: FinsPreprocessResultSummary,
) -> dict[str, JsonValue]:
    """构建 preprocess completed progress payload。

    Args:
        context: 单次业务执行上下文。
        request: 预处理请求。
        summary: 预处理结果摘要。

    Returns:
        只包含选择信息和计数的 progress payload。

    Raises:
        ValueError: 摘要字段非法时抛出。
    """

    payload = _preprocess_selected_progress_payload(
        context,
        request,
        selected_count=summary.selected_count,
    )
    payload.update(
        {
            _PAYLOAD_PROCESSED_COUNT: _non_negative_count(
                summary.processed_count,
                _PAYLOAD_PROCESSED_COUNT,
            ),
            _PAYLOAD_SKIPPED_COUNT: _non_negative_count(
                summary.skipped_count,
                _PAYLOAD_SKIPPED_COUNT,
            ),
            _PAYLOAD_FAILED_COUNT: _non_negative_count(
                summary.failed_count,
                _PAYLOAD_FAILED_COUNT,
            ),
            _PAYLOAD_NOT_SUPPORTED_COUNT: _non_negative_count(
                summary.not_supported_count,
                _PAYLOAD_NOT_SUPPORTED_COUNT,
            ),
        }
    )
    return payload


def _build_processed_sections(processor: DocumentProcessor) -> list[dict[str, JsonValue]]:
    """构建 processed sections payload。

    Args:
        processor: 已创建的文档处理器。

    Returns:
        可交给 processed 仓储写入的章节列表。

    Raises:
        RuntimeError: 处理器读取章节失败时抛出。
    """

    sections: list[dict[str, JsonValue]] = []
    for summary in processor.list_sections():
        ref = str(summary["ref"])
        payload = cast(dict[str, JsonValue], dict(processor.read_section(ref)))
        payload.setdefault("summary", cast(JsonValue, dict(summary)))
        sections.append(payload)
    return sections


def _build_processed_tables(processor: DocumentProcessor) -> list[dict[str, JsonValue]]:
    """构建 processed tables payload。

    Args:
        processor: 已创建的文档处理器。

    Returns:
        可交给 processed 仓储写入的表格列表。

    Raises:
        RuntimeError: 处理器读取表格失败时抛出。
    """

    tables: list[dict[str, JsonValue]] = []
    for summary in processor.list_tables():
        table_ref = str(summary["table_ref"])
        payload = cast(dict[str, JsonValue], dict(processor.read_table(table_ref)))
        payload.setdefault("summary", cast(JsonValue, dict(summary)))
        tables.append(payload)
    return tables


def _build_processed_meta(
    *,
    source_meta: DocumentMeta,
    parser_version: str,
) -> DocumentMeta:
    """构建 processed meta。

    Args:
        source_meta: 源文档元数据。
        parser_version: 处理器 parser version。

    Returns:
        processed meta 字典。

    Raises:
        无。
    """

    meta = dict(source_meta)
    meta["parser_version"] = parser_version
    meta["source_document_version"] = str(source_meta.get("document_version", "v1"))
    meta["schema_version"] = "v1"
    meta["reprocess_required"] = False
    return meta


def _internal_document_id(meta: DocumentMeta, document_id: str) -> str:
    """解析内部文档 ID。

    Args:
        meta: 源文档元数据。
        document_id: 源文档 ID。

    Returns:
        内部文档 ID；缺失时回退到源文档 ID。

    Raises:
        无。
    """

    value = meta.get("internal_document_id")
    if value is None:
        return document_id
    text = str(value).strip()
    return text or document_id


def _assert_bounded_summary(summary: Mapping[str, JsonValue], field_name: str) -> None:
    """校验 JSON 摘要大小。

    Args:
        summary: 待校验摘要。
        field_name: 字段名。

    Returns:
        无。

    Raises:
        ValueError: 摘要无法编码或超出大小上限时抛出。
    """

    encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    if len(encoded) > _MAX_SUMMARY_JSON_CHARS:
        raise ValueError(f"{field_name} 超出大小上限")


def _warn_malformed_event_sidecar_row(*, line_number: int, error_type: str) -> None:
    """记录 event sidecar 单行坏数据被跳过的有界 warning。

    Args:
        line_number: sidecar 文件中的行号。
        error_type: 解析或校验失败类型名；不得包含 payload 值。

    Returns:
        无。

    Raises:
        无。
    """

    _LOGGER.warning(
        "%s sidecar_kind=%s sidecar_suffix=%s line_number=%s error_type=%s error_summary=%s",
        _JOB_EVENT_SIDECAR_ROW_SKIPPED_LOG_EVENT,
        _JOB_EVENT_SIDECAR_KIND,
        _JOB_EVENT_FILE_SUFFIX,
        line_number,
        error_type,
        _JOB_EVENT_SIDECAR_ROW_SKIPPED_SUMMARY,
    )


def _event_record_to_json(record: FinsIngestionJobEventRecord) -> dict[str, JsonValue]:
    """把 job event record 转换为 JSON-compatible 字典。

    Args:
        record: job event record。

    Returns:
        JSON-compatible 字典。

    Raises:
        ValueError: record 字段非法时抛出。
    """

    _validate_job_id(record.job_id)
    _validate_event_sequence(record.sequence)
    payload = validate_bounded_job_event_payload(record.payload, _KEY_PAYLOAD)
    return {
        _KEY_JOB_ID: record.job_id,
        _KEY_SEQUENCE: record.sequence,
        _KEY_OPERATION_KIND: record.operation_kind.value,
        _KEY_STATUS: record.status.value if record.status is not None else None,
        _KEY_EVENT_TYPE: record.event_type.value,
        _KEY_SOURCE_EVENT_TYPE: _optional_bounded_text(
            record.source_event_type,
            _KEY_SOURCE_EVENT_TYPE,
            reject_path_separators=False,
        ),
        _KEY_SOURCE_KIND: record.source_kind.value if record.source_kind is not None else None,
        _KEY_DOCUMENT_ID: _optional_bounded_text(
            record.document_id,
            _KEY_DOCUMENT_ID,
            reject_path_separators=False,
        ),
        _KEY_MESSAGE: _bounded_text(record.message, _KEY_MESSAGE, reject_path_separators=False),
        _KEY_PAYLOAD: payload,
        _KEY_EMITTED_AT: _bounded_text(record.emitted_at, _KEY_EMITTED_AT, reject_path_separators=False),
    }


def _event_record_from_json(payload: Mapping[str, JsonValue]) -> FinsIngestionJobEventRecord:
    """从 JSON-compatible 字典恢复 job event record。

    Args:
        payload: JSON-compatible 字典。

    Returns:
        job event record。

    Raises:
        ValueError: 字段缺失或类型非法时抛出。
    """

    job_id = _required_str(payload, _KEY_JOB_ID)
    _validate_job_id(job_id)
    sequence = _required_int(payload, _KEY_SEQUENCE)
    _validate_event_sequence(sequence)
    source_kind_text = _optional_str(payload, _KEY_SOURCE_KIND)
    status_text = _optional_str(payload, _KEY_STATUS)
    record = FinsIngestionJobEventRecord(
        job_id=job_id,
        sequence=sequence,
        operation_kind=FinsIngestionOperationKind(_required_str(payload, _KEY_OPERATION_KIND)),
        status=FinsIngestionJobStatus(status_text) if status_text is not None else None,
        event_type=FinsIngestionJobEventType(_required_str(payload, _KEY_EVENT_TYPE)),
        source_event_type=_optional_str(payload, _KEY_SOURCE_EVENT_TYPE),
        source_kind=SourceKind(source_kind_text) if source_kind_text is not None else None,
        document_id=_optional_str(payload, _KEY_DOCUMENT_ID),
        message=_required_str(payload, _KEY_MESSAGE),
        payload=_required_json_object(payload, _KEY_PAYLOAD),
        emitted_at=_required_str(payload, _KEY_EMITTED_AT),
    )
    _event_record_to_json(record)
    return record


def _validate_event_sequence(sequence: int) -> None:
    """校验事件 sequence。

    Args:
        sequence: 待校验 sequence。

    Returns:
        无。

    Raises:
        ValueError: sequence 小于 1 时抛出。
    """

    if sequence < 1:
        raise ValueError("Fins ingestion job event sequence 必须从 1 开始")


def _validate_event_read_window(*, after_sequence: int, limit: int) -> None:
    """校验 event 读取窗口。

    Args:
        after_sequence: 读取游标。
        limit: 本次最多返回事件数量。

    Returns:
        无。

    Raises:
        ValueError: 游标或 limit 非法时抛出。
    """

    if after_sequence < 0:
        raise ValueError("after_sequence 不能为负数")
    if limit < 1:
        raise ValueError("limit 必须为正数")
    if limit > _MAX_JOB_EVENT_READ_LIMIT:
        raise ValueError("limit 超出 Fins ingestion job event 读取上限")


def _record_to_json(record: FinsIngestionJobRecord) -> dict[str, JsonValue]:
    """把 job record 转换为 JSON-compatible 字典。

    Args:
        record: job record。

    Returns:
        JSON-compatible 字典。

    Raises:
        ValueError: record 字段非法时抛出。
    """

    _validate_job_id(record.job_id)
    _validate_record_operation_fields(record)
    _assert_bounded_summary(record.request_summary, _KEY_REQUEST_SUMMARY)
    _assert_bounded_summary(record.result_summary, _KEY_RESULT_SUMMARY)
    _assert_bounded_summary(record.failure_summary, _KEY_FAILURE_SUMMARY)
    return {
        _KEY_JOB_ID: record.job_id,
        _KEY_OPERATION_KIND: record.operation_kind.value,
        _KEY_NORMALIZED_TICKER: record.normalized_ticker,
        _KEY_MARKET: record.market,
        _KEY_EXCHANGE: record.exchange,
        _KEY_SOURCE: record.source,
        _KEY_SOURCE_KIND: record.source_kind.value if record.source_kind is not None else None,
        _KEY_STATUS: record.status.value,
        _KEY_CREATED_AT: record.created_at,
        _KEY_UPDATED_AT: record.updated_at,
        _KEY_STARTED_AT: record.started_at,
        _KEY_FINISHED_AT: record.finished_at,
        _KEY_REQUEST_SUMMARY: record.request_summary,
        _KEY_RESULT_SUMMARY: record.result_summary,
        _KEY_FAILURE_SUMMARY: record.failure_summary,
        _KEY_CANCELLATION_REQUESTED: record.cancellation_requested,
    }


def _record_from_json(payload: Mapping[str, JsonValue]) -> FinsIngestionJobRecord:
    """从 JSON-compatible 字典恢复 job record。

    Args:
        payload: JSON-compatible 字典。

    Returns:
        job record。

    Raises:
        ValueError: 字段缺失或类型非法时抛出。
    """

    job_id = _required_str(payload, _KEY_JOB_ID)
    _validate_job_id(job_id)
    source_kind_text = _optional_str(payload, _KEY_SOURCE_KIND)
    record = FinsIngestionJobRecord(
        job_id=job_id,
        operation_kind=FinsIngestionOperationKind(_required_str(payload, _KEY_OPERATION_KIND)),
        normalized_ticker=_required_str(payload, _KEY_NORMALIZED_TICKER),
        market=_market_from_text(_required_str(payload, _KEY_MARKET)),
        exchange=_exchange_from_optional_text(_optional_str(payload, _KEY_EXCHANGE)),
        source=_optional_str(payload, _KEY_SOURCE),
        source_kind=SourceKind(source_kind_text) if source_kind_text is not None else None,
        status=FinsIngestionJobStatus(_required_str(payload, _KEY_STATUS)),
        created_at=_required_str(payload, _KEY_CREATED_AT),
        updated_at=_required_str(payload, _KEY_UPDATED_AT),
        started_at=_optional_str(payload, _KEY_STARTED_AT),
        finished_at=_optional_str(payload, _KEY_FINISHED_AT),
        request_summary=_required_json_object(payload, _KEY_REQUEST_SUMMARY),
        result_summary=_required_json_object(payload, _KEY_RESULT_SUMMARY),
        failure_summary=_required_json_object(payload, _KEY_FAILURE_SUMMARY),
        cancellation_requested=_required_bool(payload, _KEY_CANCELLATION_REQUESTED),
    )
    _record_to_json(record)
    return record


def _validate_record_operation_fields(record: FinsIngestionJobRecord) -> None:
    """校验 job 操作类型与 source/source_kind 字段组合。

    Args:
        record: 待校验 job record。

    Returns:
        无。

    Raises:
        ValueError: 操作类型与 source 或 source_kind 字段组合不一致时抛出。
    """

    if record.operation_kind is FinsIngestionOperationKind.DOWNLOAD:
        if record.source is None:
            raise ValueError("download job record 必须包含 source")
        if record.source_kind is not None:
            raise ValueError("download job record 不得包含 source_kind")
        return
    if record.operation_kind is FinsIngestionOperationKind.PREPROCESS:
        if record.source is not None:
            raise ValueError("preprocess job record 不得包含 source")
        if record.source_kind is None:
            raise ValueError("preprocess job record 必须包含 source_kind")
        return
    if record.source is not None:
        raise ValueError("upload job record 不得包含 source")
    if record.source_kind is None:
        raise ValueError("upload job record 必须包含 source_kind")


def _required_str(payload: Mapping[str, JsonValue], key: str) -> str:
    """读取必填字符串字段。

    Args:
        payload: JSON-compatible 字典。
        key: 字段名。

    Returns:
        字符串字段值。

    Raises:
        ValueError: 字段缺失或类型错误时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Fins ingestion job record 字段 {key} 不是字符串")
    return value


def _optional_str(payload: Mapping[str, JsonValue], key: str) -> str | None:
    """读取可空字符串字段。

    Args:
        payload: JSON-compatible 字典。
        key: 字段名。

    Returns:
        字符串字段值或 ``None``。

    Raises:
        ValueError: 字段类型错误时抛出。
    """

    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Fins ingestion job record 字段 {key} 不是字符串")
    return value


def _required_bool(payload: Mapping[str, JsonValue], key: str) -> bool:
    """读取必填布尔字段。

    Args:
        payload: JSON-compatible 字典。
        key: 字段名。

    Returns:
        布尔字段值。

    Raises:
        ValueError: 字段缺失或类型错误时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Fins ingestion job record 字段 {key} 不是布尔值")
    return value


def _required_int(payload: Mapping[str, JsonValue], key: str) -> int:
    """读取必填整数字段。

    Args:
        payload: JSON-compatible 字典。
        key: 字段名。

    Returns:
        整数字段值。

    Raises:
        ValueError: 字段缺失或类型错误时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Fins ingestion job record 字段 {key} 不是整数")
    return value


def _required_json_object(payload: Mapping[str, JsonValue], key: str) -> dict[str, JsonValue]:
    """读取必填 JSON 映射字段。

    Args:
        payload: JSON-compatible 字典。
        key: 字段名。

    Returns:
        JSON-compatible 字典。

    Raises:
        ValueError: 字段缺失或类型错误时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Fins ingestion job record 字段 {key} 不是 JSON 映射")
    return dict(cast(Mapping[str, JsonValue], value))


def _terminal_event_type_from_status(
    status: FinsIngestionJobStatus,
) -> FinsIngestionJobEventType | None:
    """把 terminal job status 映射为 terminal event type。

    Args:
        status: job record 状态。

    Returns:
        terminal 状态对应的事件类型；非 terminal 状态返回 ``None``。

    Raises:
        无。
    """

    if status is FinsIngestionJobStatus.SUCCEEDED:
        return FinsIngestionJobEventType.JOB_SUCCEEDED
    if status is FinsIngestionJobStatus.FAILED:
        return FinsIngestionJobEventType.JOB_FAILED
    if status is FinsIngestionJobStatus.CANCELLED:
        return FinsIngestionJobEventType.JOB_CANCELLED
    return None


def _terminal_event_message(status: FinsIngestionJobStatus) -> str:
    """返回 terminal event 的用户可读说明。

    Args:
        status: job record 状态。

    Returns:
        有界说明文本。

    Raises:
        无。
    """

    if status is FinsIngestionJobStatus.SUCCEEDED:
        return "job 已成功完成"
    if status is FinsIngestionJobStatus.FAILED:
        return "job 已失败"
    if status is FinsIngestionJobStatus.CANCELLED:
        return "job 已取消"
    return "job 状态未终结"


def _bounded_log_text(value: str) -> str:
    """返回适合 WARN 日志的一行有界文本。

    Args:
        value: 原始文本。

    Returns:
        移除换行并截断后的文本。

    Raises:
        无。
    """

    normalized = " ".join(value.split())
    if len(normalized) <= _MAX_TEXT_CHARS:
        return normalized
    return normalized[:_MAX_TEXT_CHARS]


def _market_from_text(value: str) -> NormalizedTickerMarket:
    """恢复 ticker market 字段。

    Args:
        value: market 文本。

    Returns:
        标准化 market。

    Raises:
        ValueError: market 非法时抛出。
    """

    if value in _NORMALIZED_MARKET_VALUES:
        return cast(NormalizedTickerMarket, value)
    raise ValueError(f"非法 Fins ingestion market: {value!r}")


def _exchange_from_optional_text(value: str | None) -> NormalizedTickerExchange | None:
    """恢复 ticker exchange 字段。

    Args:
        value: exchange 文本或 ``None``。

    Returns:
        标准化 exchange 或 ``None``。

    Raises:
        ValueError: exchange 非法时抛出。
    """

    if value is None:
        return None
    if value in _NORMALIZED_EXCHANGE_VALUES:
        return cast(NormalizedTickerExchange, value)
    raise ValueError(f"非法 Fins ingestion exchange: {value!r}")


def _fsync_directory(path: Path) -> None:
    """fsync 目录，确保 atomic replace 元数据落盘。

    Args:
        path: 目录路径。

    Returns:
        无。

    Raises:
        OSError: 目录打开或 fsync 失败时抛出。
    """

    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _is_start_cancelled(cancellation_token: CancellationToken | None) -> bool:
    """判断启动边界是否已观察到取消。

    Args:
        cancellation_token: 可选取消观察 token。

    Returns:
        token 已取消返回 ``True``；无 token 或未取消返回 ``False``。

    Raises:
        无。
    """

    return cancellation_token is not None and cancellation_token.is_cancelled()


def _raise_if_start_cancelled(cancellation_token: CancellationToken | None) -> None:
    """在 durable job 创建前执行取消 checkpoint。

    Args:
        cancellation_token: 可选取消观察 token。

    Returns:
        无。

    Raises:
        FinsIngestionStartCancelledError: token 已取消时抛出。
    """

    if _is_start_cancelled(cancellation_token):
        raise FinsIngestionStartCancelledError("Fins ingestion start cancelled before durable job creation")


def _job_start_from_record(record: FinsIngestionJobRecord) -> FinsIngestionJobStart:
    """从 durable job record 构造启动结果。

    Args:
        record: 已持久化 job record。

    Returns:
        与 record 状态一致的启动结果。

    Raises:
        无。
    """

    return FinsIngestionJobStart(
        job_id=record.job_id,
        status=record.status,
        record=record,
    )


__all__ = [
    "FinsDownloadedFile",
    "FinsDownloadedSourceDocument",
    "FinsDownloadProgressEvent",
    "FinsDownloadProgressSink",
    "FinsJobCancellationChecker",
    "FinsIngestionJobRecord",
    "FinsIngestionJobStart",
    "FinsIngestionJobStatus",
    "FinsIngestionJobStore",
    "FinsIngestionOperationKind",
    "FinsIngestionRuntime",
    "FinsIngestionStartCancelledError",
    "FinsRejectedFilingDownloadArtifact",
    "FinsPreprocessRequest",
    "FinsPreprocessResultSummary",
    "FinsPreprocessResultStatus",
    "FinsSourceDownloadAdapter",
    "FinsSourceDownloadAdapterRequest",
    "FinsSourceDownloadAdapterResult",
    "FinsUploadFilingRequest",
    "FinsUploadMaterialRequest",
    "FinsUploadPipelineResult",
    "FinsUploadRequest",
    "FinsUploadResultSummary",
    "FinsUploadRunner",
    "FsFinsIngestionJobStore",
]
