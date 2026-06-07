"""Fins 下载与预处理运行时基础能力。

本模块只承载 Fins 自有 ingestion job 的 typed 请求、结果摘要、持久化
job record、文件系统 job store 与运行时入口。它不实现真实下载、
Host wait adapter、tool provider 或 CLI。
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock, Thread
from types import TracebackType
from typing import Final, Protocol, TextIO, cast, get_args

import fcntl

from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.base import DocumentProcessor
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins import ticker_normalization
from dayu.fins.domain.document_models import (
    DocumentMeta,
    ProcessedCreateRequest,
    ProcessedUpdateRequest,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.ticker_normalization import Exchange as NormalizedTickerExchange
from dayu.fins.ticker_normalization import Market as NormalizedTickerMarket
from dayu.fins.ticker_normalization import NormalizedTicker

_DEFAULT_DOWNLOAD_SOURCE: Final[str] = "auto"
_JOB_ID_PREFIX: Final[str] = "finsjob_"
_JOB_FILE_SUFFIX: Final[str] = ".json"
_LOCK_FILE_NAME: Final[str] = ".store.lock"
_JOBS_DIR_PARTS: Final[tuple[str, str, str]] = (".dayu", "fins_ingestion", "jobs")
_JOB_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^finsjob_[0-9a-f]{32}$")
_MAX_SUMMARY_JSON_CHARS: Final[int] = 4096
_MAX_TEXT_CHARS: Final[int] = 240
_MAX_TUPLE_ITEMS: Final[int] = 100
_MAX_PREPROCESS_DOCUMENTS: Final[int] = 50
_EMPTY_SUMMARY: Final[dict[str, JsonValue]] = {}
_NORMALIZED_MARKET_VALUES: Final[frozenset[NormalizedTickerMarket]] = frozenset(
    cast(tuple[NormalizedTickerMarket, ...], get_args(NormalizedTickerMarket))
)
_NORMALIZED_EXCHANGE_VALUES: Final[frozenset[NormalizedTickerExchange]] = frozenset(
    cast(tuple[NormalizedTickerExchange, ...], get_args(NormalizedTickerExchange))
)
_LOGGER: logging.Logger = logging.getLogger(__name__)

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


class FinsIngestionOperationKind(str, Enum):
    """Fins ingestion job 操作类型。"""

    DOWNLOAD = "download"
    PREPROCESS = "preprocess"


class FinsIngestionJobStatus(str, Enum):
    """Fins ingestion job 状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {
        FinsIngestionJobStatus.SUCCEEDED,
        FinsIngestionJobStatus.FAILED,
        FinsIngestionJobStatus.CANCELLED,
    }
)


class _PreprocessNotSupportedError(RuntimeError):
    """源文档没有可用预处理器。"""


@dataclass(frozen=True)
class FinsDownloadRequest:
    """下载任务请求。

    Attributes:
        ticker: 用户提供的 ticker 文本，运行时会先调用公共 ticker 归一化 API。
        source: 下载来源标识；S1 仅持久化摘要，不选择真实 adapter。
        form_types: 可选财报表单过滤条件。
        filed_after: 可选起始披露日期字符串。
        filed_before: 可选结束披露日期字符串。
        overwrite_existing: 是否允许覆盖已存在源文档。
        rebuild_processed: 下载后是否要求后续重建 processed 产物。
    """

    ticker: str
    source: str = _DEFAULT_DOWNLOAD_SOURCE
    form_types: tuple[str, ...] = ()
    filed_after: str | None = None
    filed_before: str | None = None
    overwrite_existing: bool = False
    rebuild_processed: bool = False


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


@dataclass(frozen=True)
class FinsDownloadResultSummary:
    """下载任务结果摘要。

    Attributes:
        discovered_count: 发现的候选文档数量。
        downloaded_count: 下载成功数量。
        skipped_count: 跳过数量。
        rejected_count: 拒绝数量。
        failed_count: 失败数量。
        written_document_ids: 已写入的源文档 ID。
    """

    discovered_count: int = 0
    downloaded_count: int = 0
    skipped_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
    written_document_ids: tuple[str, ...] = ()

    def to_json_summary(self) -> dict[str, JsonValue]:
        """转换为 JSON-compatible 摘要。

        Args:
            无。

        Returns:
            只包含计数和源文档 ID 的 JSON-compatible 字典。

        Raises:
            ValueError: 文档 ID 数量或长度超过 job record 边界时抛出。
        """

        return {
            "discovered_count": self.discovered_count,
            "downloaded_count": self.downloaded_count,
            "skipped_count": self.skipped_count,
            "rejected_count": self.rejected_count,
            "failed_count": self.failed_count,
            "written_document_ids": list(
                _bounded_text_tuple(
                    self.written_document_ids,
                    "written_document_ids",
                    reject_path_separators=False,
                )
            ),
        }


@dataclass(frozen=True)
class FinsPreprocessResultSummary:
    """预处理任务结果摘要。

    Attributes:
        selected_count: 被选择处理的源文档数量。
        processed_count: 处理成功数量。
        skipped_count: 跳过数量。
        failed_count: 失败数量。
        processed_document_ids: 已写入的 processed 文档 ID。
        skipped_document_ids: 因已有产物等原因跳过的源文档 ID。
        failed_document_ids: 处理失败的源文档 ID。
        not_supported_document_ids: 没有可用处理器的源文档 ID。
    """

    selected_count: int = 0
    processed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    processed_document_ids: tuple[str, ...] = ()
    skipped_document_ids: tuple[str, ...] = ()
    failed_document_ids: tuple[str, ...] = ()
    not_supported_document_ids: tuple[str, ...] = ()

    def to_json_summary(self) -> dict[str, JsonValue]:
        """转换为 JSON-compatible 摘要。

        Args:
            无。

        Returns:
            只包含计数和 processed 文档 ID 的 JSON-compatible 字典。

        Raises:
            ValueError: 文档 ID 数量或长度超过 job record 边界时抛出。
        """

        return {
            "selected_count": self.selected_count,
            "processed_count": self.processed_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "processed_document_ids": list(
                _bounded_text_tuple(
                    self.processed_document_ids,
                    "processed_document_ids",
                    reject_path_separators=False,
                )
            ),
            "skipped_document_ids": list(
                _bounded_text_tuple(
                    self.skipped_document_ids,
                    "skipped_document_ids",
                    reject_path_separators=False,
                )
            ),
            "failed_document_ids": list(
                _bounded_text_tuple(
                    self.failed_document_ids,
                    "failed_document_ids",
                    reject_path_separators=False,
                )
            ),
            "not_supported_document_ids": list(
                _bounded_text_tuple(
                    self.not_supported_document_ids,
                    "not_supported_document_ids",
                    reject_path_separators=False,
                )
            ),
        }


@dataclass(frozen=True)
class FinsIngestionJobRecord:
    """Fins ingestion 持久化 job record。

    Attributes:
        job_id: ASCII opaque job id。
        operation_kind: 下载或预处理。
        normalized_ticker: 标准化后的 ticker 裸码。
        market: 标准化市场。
        exchange: 标准化交易所；美股无明确交易所时为 ``None``。
        source: 下载来源标识；预处理任务可为 ``None``。
        source_kind: 源文档类型；下载任务可为 ``None``。
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
            OSError: 文件系统写入失败时抛出。
            ValueError: record 字段非法时抛出。
        """

        with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):
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
            OSError: 文件系统写入失败时抛出。
            ValueError: record 字段非法时抛出。
        """

        with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):
            path = self._job_path(record.job_id)
            if not path.exists():
                raise FileNotFoundError(f"Fins ingestion job 不存在: {record.job_id}")
            self._write_record_locked(record)
            return record

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

        with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):
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
            OSError: 文件系统读写失败时抛出。
            ValueError: job id 或 record 内容非法时抛出。
        """

        with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):
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
    """Fins 下载与预处理运行时基础入口。"""

    source_repository: SourceDocumentRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    processor_registry: ProcessorRegistry
    job_store: FinsIngestionJobStore
    executor: FinsIngestionExecutor
    _start_lock: Lock

    @classmethod
    def create(
        cls,
        *,
        source_repository: SourceDocumentRepositoryProtocol,
        processed_repository: ProcessedDocumentRepositoryProtocol,
        processor_registry: ProcessorRegistry,
        job_store: FinsIngestionJobStore,
        executor: FinsIngestionExecutor | None = None,
    ) -> "FinsIngestionRuntime":
        """创建 ingestion runtime。

        Args:
            source_repository: 源文档仓储协议实现。
            processed_repository: processed 文档仓储协议实现。
            processor_registry: 文档处理器注册表。
            job_store: Fins ingestion job record 存储。
            executor: 可选后台执行器；不传入时使用最小 daemon thread 执行器。

        Returns:
            Fins ingestion runtime。

        Raises:
            无。
        """

        return cls(
            source_repository=source_repository,
            processed_repository=processed_repository,
            processor_registry=processor_registry,
            job_store=job_store,
            executor=executor or FinsIngestionThreadExecutor(),
            _start_lock=Lock(),
        )

    def start_download(self, request: FinsDownloadRequest) -> FinsIngestionJobStart:
        """启动下载 job。

        S1 只创建 durable ``queued`` record，不启动真实下载 pipeline。

        Args:
            request: 下载请求。

        Returns:
            已持久化 job 的启动结果。

        Raises:
            ValueError: ticker、来源或请求摘要字段非法时抛出。
            OSError: job record 持久化失败时抛出。
        """

        normalized = ticker_normalization.normalize_ticker(request.ticker)
        source = _bounded_text(request.source, "source")
        request_summary: dict[str, JsonValue] = {
            "form_types": list(
                _bounded_text_tuple(request.form_types, "form_types", reject_path_separators=False)
            ),
            "filed_after": _optional_bounded_text(request.filed_after, "filed_after"),
            "filed_before": _optional_bounded_text(request.filed_before, "filed_before"),
            "overwrite_existing": request.overwrite_existing,
            "rebuild_processed": request.rebuild_processed,
        }
        return self._create_queued_job(
            operation_kind=FinsIngestionOperationKind.DOWNLOAD,
            normalized=normalized,
            source=source,
            source_kind=None,
            request_summary=request_summary,
        )

    def start_preprocess(self, request: FinsPreprocessRequest) -> FinsIngestionJobStart:
        """启动预处理 job。

        本方法先创建 durable ``queued`` record，再提交后台 pipeline。后台
        pipeline 只通过 Fins 仓储协议读取 source、写入 processed。

        Args:
            request: 预处理请求。

        Returns:
            已持久化 job 的启动结果。

        Raises:
            ValueError: ticker 或请求摘要字段非法时抛出。
            OSError: job record 持久化失败时抛出。
        """

        normalized = ticker_normalization.normalize_ticker(request.ticker)
        request_summary: dict[str, JsonValue] = {
            "source_kind": request.source_kind.value,
            "document_ids": list(
                _bounded_text_tuple(request.document_ids, "document_ids", reject_path_separators=False)
            ),
            "form_types": list(
                _bounded_text_tuple(request.form_types, "form_types", reject_path_separators=False)
            ),
            "rebuild_processed": request.rebuild_processed,
        }
        start = self._create_queued_job(
            operation_kind=FinsIngestionOperationKind.PREPROCESS,
            normalized=normalized,
            source=None,
            source_kind=request.source_kind,
            request_summary=request_summary,
        )
        self.executor.submit(
            start.job_id,
            lambda: self._run_preprocess_job(
                job_id=start.job_id,
                request=request,
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

        return self.job_store.request_cancel(job_id, updated_at=_utc_now())

    def _create_queued_job(
        self,
        *,
        operation_kind: FinsIngestionOperationKind,
        normalized: NormalizedTicker,
        source: str | None,
        source_kind: SourceKind | None,
        request_summary: dict[str, JsonValue],
    ) -> FinsIngestionJobStart:
        """创建 queued job record。

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
        with self._start_lock:
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
        return FinsIngestionJobStart(
            job_id=persisted.job_id,
            status=persisted.status,
            record=persisted,
        )

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
            if record.status is FinsIngestionJobStatus.CANCELLED:
                return
            summary = self._execute_preprocess_request(record, request)
            latest = self.job_store.read_job(job_id)
            if latest.cancellation_requested or latest.status is FinsIngestionJobStatus.CANCELLING:
                self._save_cancelled(latest)
                return
            if (
                summary.processed_count == 0
                and (
                    summary.selected_count == 0
                    or summary.failed_count > 0
                    or len(summary.not_supported_document_ids) > 0
                )
            ):
                self._save_failed(
                    latest,
                    message="没有任何请求文档完成预处理",
                    result_summary=summary.to_json_summary(),
                )
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

        record = self.job_store.read_job(job_id)
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            return self._save_cancelled(record)
        if record.status in _TERMINAL_STATUSES:
            return record
        now = _utc_now()
        return self.job_store.save_job(
            replace(
                record,
                status=FinsIngestionJobStatus.RUNNING,
                started_at=record.started_at or now,
                updated_at=now,
            )
        )

    def _execute_preprocess_request(
        self,
        record: FinsIngestionJobRecord,
        request: FinsPreprocessRequest,
    ) -> FinsPreprocessResultSummary:
        """执行单个预处理请求。

        Args:
            record: 已进入 running 的 job record。
            request: 原始预处理请求。

        Returns:
            预处理结果摘要。

        Raises:
            FileNotFoundError: ticker 或显式文档不存在时抛出。
            ValueError: 选择数量超过上限或请求字段非法时抛出。
            OSError: 仓储读取或写入失败时抛出。
        """

        ticker = record.normalized_ticker
        document_ids = self._select_preprocess_documents(
            ticker=ticker,
            source_kind=request.source_kind,
            document_ids=request.document_ids,
            form_types=request.form_types,
        )
        processed_ids: list[str] = []
        skipped_ids: list[str] = []
        failed_ids: list[str] = []
        not_supported_ids: list[str] = []

        for document_id in document_ids:
            latest = self.job_store.read_job(record.job_id)
            if latest.cancellation_requested or latest.status is FinsIngestionJobStatus.CANCELLING:
                break
            try:
                outcome = self._preprocess_one_document(
                    ticker=ticker,
                    document_id=document_id,
                    source_kind=request.source_kind,
                    rebuild_processed=request.rebuild_processed,
                )
            except _PreprocessNotSupportedError:
                not_supported_ids.append(document_id)
                continue
            except Exception:
                failed_ids.append(document_id)
                continue
            if outcome == "processed":
                processed_ids.append(document_id)
            else:
                skipped_ids.append(document_id)

        return FinsPreprocessResultSummary(
            selected_count=len(document_ids),
            processed_count=len(processed_ids),
            skipped_count=len(skipped_ids) + len(not_supported_ids),
            failed_count=len(failed_ids),
            processed_document_ids=tuple(processed_ids),
            skipped_document_ids=tuple(skipped_ids),
            failed_document_ids=tuple(failed_ids),
            not_supported_document_ids=tuple(not_supported_ids),
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
            if not bool(meta.get("ingest_complete", True)):
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

        source_meta = self.source_repository.get_source_meta(ticker, document_id, source_kind)
        source = self.source_repository.get_primary_source(ticker, document_id, source_kind)
        form_type = _optional_bounded_text(_optional_text_from_meta(source_meta, "form_type"), "form_type")
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
                )
            )
            return "processed"
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
            )
        )
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
        return self.job_store.save_job(
            replace(
                record,
                status=FinsIngestionJobStatus.SUCCEEDED,
                updated_at=now,
                finished_at=now,
                result_summary=result_summary,
                failure_summary=dict(_EMPTY_SUMMARY),
            )
        )

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
        return self.job_store.save_job(
            replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=now,
                finished_at=now,
                cancellation_requested=True,
            )
        )

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
        return self.job_store.save_job(
            replace(
                record,
                status=FinsIngestionJobStatus.FAILED,
                updated_at=now,
                finished_at=now,
                result_summary=final_result,
                failure_summary=failure_summary,
            )
        )

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
                "fins.ingestion.failed_terminalization_failed "
                "job_id=%s error_type=%s original_error_type=%s",
                job_id,
                type(terminal_exc).__name__,
                type(exc).__name__,
                exc_info=True,
            )
            return


class _StoreFileLock:
    """进程间文件锁。"""

    def __init__(self, path: Path) -> None:
        """初始化文件锁。

        Args:
            path: 锁文件路径。

        Returns:
            无。

        Raises:
            无。
        """

        self._path = path
        self._stream: TextIO | None = None

    def __enter__(self) -> None:
        """获取独占文件锁。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 锁文件打开或加锁失败时抛出。
        """

        self._path.parent.mkdir(parents=True, exist_ok=True)
        stream = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        except BaseException:
            stream.close()
            raise
        self._stream = stream

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """释放独占文件锁。

        Args:
            exc_type: 异常类型。
            exc: 异常实例。
            traceback: 异常 traceback。

        Returns:
            无。

        Raises:
            OSError: 解锁或关闭失败时抛出。
        """

        stream = self._stream
        if stream is None:
            return
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
            self._stream = None


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


__all__ = [
    "FinsDownloadRequest",
    "FinsDownloadResultSummary",
    "FinsIngestionJobRecord",
    "FinsIngestionJobStart",
    "FinsIngestionJobStatus",
    "FinsIngestionJobStore",
    "FinsIngestionOperationKind",
    "FinsIngestionRuntime",
    "FinsPreprocessRequest",
    "FinsPreprocessResultSummary",
    "FsFinsIngestionJobStore",
]
