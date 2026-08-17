"""Fins direct 执行事件与已验证事件流公共契约。

本模块定义 CLI、Service 与 Fins runtime direct path 共享的业务事件形态。
事件只表达当前财报 direct 操作的进度与终态结果，不表达后台 job、sidecar、
游标、仓储路径或 Host / Engine 治理状态；同时独占 direct stream 恰好包含
一个且最后一个 ``RESULT`` 的判定与 raw async generator 关闭生命周期。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Final, NoReturn

from dayu.contracts.json_value import JsonValue
from dayu.fins.company_metadata_warning import CompanyMetadataWarning
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadEffectiveFilters,
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
    FinsDownloadTransportCategory,
)
from dayu.fins.domain.filing_semantics import FISCAL_PERIODS

FINS_RESULT_EXIT_SUCCESS: Final[int] = 0
FINS_RESULT_EXIT_FAILURE: Final[int] = 1
FINS_RESULT_EXIT_CANCELLED: Final[int] = 130

_MAX_MESSAGE_CHARS: Final[int] = 240
_MAX_DETAIL_CHARS: Final[int] = 240
_MAX_TITLE_CHARS: Final[int] = 120
_MAX_STAGE_CHARS: Final[int] = 120
_MAX_DOCUMENT_LABEL_CHARS: Final[int] = 120
_MAX_SHORT_FIELD_CHARS: Final[int] = 80
_MAX_PUBLIC_FILE_LABEL_CHARS: Final[int] = 240
_HIDDEN_PUBLIC_FILE_LABEL: Final[str] = "输入文件（文件名已隐藏）"

_FINS_JOB_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bfinsjob_[0-9a-fA-F]{32}\b")
_ABSOLUTE_POSIX_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s='\":])/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]+"
)
_ABSOLUTE_WINDOWS_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:^|[\s='\":])[A-Za-z]:\\")
_DISALLOWED_TEXT_FRAGMENTS: Final[tuple[str, ...]] = (
    "job_id",
    "job id",
    "event sequence",
    "sequence=",
    "sequence:",
    "cursor",
    "resume token",
    "resume_token",
    "tool_call_id",
    "storage path",
    "raw payload",
    "provider payload",
    ".dayu/fins_ingestion",
    "财报正文",
)
_MISSING_RESULT_MESSAGE: Final[str] = "Fins direct stream ended without RESULT"
_DUPLICATE_RESULT_MESSAGE: Final[str] = "Fins direct stream produced multiple RESULT events"
_EVENT_AFTER_RESULT_MESSAGE: Final[str] = "Fins direct stream produced an event after RESULT"
_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE: Final[str] = (
    "Fins direct terminal result is not available before clean stream exhaustion"
)


class FinsEventType(str, Enum):
    """Fins direct 事件类型。"""

    PROGRESS = "progress"
    RESULT = "result"


class FinsResultStatus(str, Enum):
    """Fins direct 终态结果状态。"""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class FinsOperationKind(str, Enum):
    """Fins direct 业务操作类型。"""

    DOWNLOAD = "download"
    PREPROCESS = "preprocess"
    UPLOAD = "upload"
    UPLOAD_FILING = "upload_filing"
    UPLOAD_MATERIAL = "upload_material"
    PROCESS_FILING = "process_filing"
    PROCESS_MATERIAL = "process_material"


class FinsDirectStreamProtocolErrorKind(str, Enum):
    """Fins direct stream 协议错误分类。"""

    MISSING_RESULT = "missing_result"
    DUPLICATE_RESULT = "duplicate_result"
    EVENT_AFTER_RESULT = "event_after_result"


class FinsDirectStreamProtocolError(ValueError):
    """Fins direct stream 协议错误。

    Attributes:
        reason: 协议错误分类。
        operation_kind: 发生错误的 direct 操作类型。
        message: 用户可读且非空的错误说明。
    """

    reason: FinsDirectStreamProtocolErrorKind
    operation_kind: FinsOperationKind
    message: str

    def __init__(
        self,
        reason: FinsDirectStreamProtocolErrorKind,
        operation_kind: FinsOperationKind,
        message: str,
    ) -> None:
        """初始化 Fins direct stream 协议错误。

        Args:
            reason: 协议错误分类。
            operation_kind: 发生错误的 direct 操作类型。
            message: 用户可读且非空的错误说明。

        Returns:
            无。

        Raises:
            TypeError: reason 或 operation_kind 类型非法时抛出。
            ValueError: message 为空时抛出。
        """

        if not isinstance(reason, FinsDirectStreamProtocolErrorKind):
            raise TypeError("reason must be FinsDirectStreamProtocolErrorKind")
        if not isinstance(operation_kind, FinsOperationKind):
            raise TypeError("operation_kind must be FinsOperationKind")
        if not message.strip():
            raise ValueError("message must not be empty")
        self.reason = reason
        self.operation_kind = operation_kind
        self.message = message
        super().__init__(message)


class FinsErrorKind(str, Enum):
    """Fins direct 失败分类。"""

    USER_INPUT = "user_input"
    STORAGE = "storage"
    PROVIDER = "provider"
    EXECUTION = "execution"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class FinsPublicFailureKind(str, Enum):
    """下载 public terminal 的封闭失败分类。"""

    CONFIGURATION = "configuration"
    PROVIDER_TRANSPORT = "provider_transport"
    STORAGE = "storage"
    EXECUTION = "execution"


@dataclass(frozen=True, slots=True)
class FinsPublicFailure:
    """下载 terminal 对 CLI 与 LLM 共享的脱敏失败对象。

    Attributes:
        kind: 封闭失败分类。
        source: resolved 下载来源。
        transport_category: provider/configuration 失败的 transport 分类。
        safe_message: 不含敏感 transport 内容的用户可读说明。
        retry_hint: 用户可读恢复建议。
    """

    kind: FinsPublicFailureKind
    source: FinsDownloadSource
    transport_category: FinsDownloadTransportCategory | None
    safe_message: str
    retry_hint: str

    def __post_init__(self) -> None:
        """校验 public failure 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: enum 字段类型非法时抛出。
            ValueError: 文本不安全或 transport 分类组合非法时抛出。
        """

        if not isinstance(self.kind, FinsPublicFailureKind):
            raise TypeError("kind must be FinsPublicFailureKind")
        if not isinstance(self.source, FinsDownloadSource):
            raise TypeError("source must be FinsDownloadSource")
        if self.transport_category is not None and not isinstance(
            self.transport_category,
            FinsDownloadTransportCategory,
        ):
            raise TypeError("transport_category must be FinsDownloadTransportCategory")
        if (
            self.kind
            in {
                FinsPublicFailureKind.CONFIGURATION,
                FinsPublicFailureKind.PROVIDER_TRANSPORT,
            }
            and self.transport_category is None
        ):
            raise ValueError("provider/configuration failure requires transport_category")
        if self.kind in {FinsPublicFailureKind.STORAGE, FinsPublicFailureKind.EXECUTION} and (
            self.transport_category is not None
        ):
            raise ValueError("storage/execution failure must not contain transport_category")
        _validate_safe_text(
            self.safe_message,
            field_name="failure.safe_message",
            max_chars=_MAX_MESSAGE_CHARS,
            allow_empty=False,
        )
        _validate_safe_text(
            self.retry_hint,
            field_name="failure.retry_hint",
            max_chars=_MAX_MESSAGE_CHARS,
            allow_empty=False,
        )

    def to_json_value(self) -> dict[str, JsonValue]:
        """转换为 CLI/wait 可共享的 JSON-compatible 业务字段。

        Returns:
            自解释 failure JSON 对象。

        Raises:
            无。
        """

        return {
            "classification": self.kind.value,
            "source": self.source.value,
            "transport_category": (None if self.transport_category is None else self.transport_category.value),
            "message": self.safe_message,
            "retry_hint": self.retry_hint,
        }


@dataclass(frozen=True, slots=True)
class FinsDownloadPublicDocument:
    """public terminal 中的单个有界下载文档行。

    Attributes:
        document_id: provider candidate 的业务文档 ID。
        form_or_period: canonical form 或身份财期。
        filing_date: 可选披露日期。
        report_date: 可选报告期日期。
        covered_fiscal_periods: 上游 typed contract 原样投影的覆盖财期。
        disposition: 互斥结果分类。
        reason_category: 可选稳定原因分类。
        reason_message: 可选脱敏原因说明。
        artifact_locator: 可选 workspace-relative source locator。
    """

    document_id: str
    form_or_period: str | None
    filing_date: str | None
    report_date: str | None
    covered_fiscal_periods: tuple[str, ...]
    disposition: FinsDownloadDocumentDisposition
    reason_category: str | None
    reason_message: str | None
    artifact_locator: str | None

    def __post_init__(self) -> None:
        """校验 public 文档行。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: disposition 类型非法时抛出。
            ValueError: 文本或 locator 不安全时抛出。
        """

        _validate_safe_text(
            self.document_id,
            field_name="download.row.document_id",
            max_chars=_MAX_DOCUMENT_LABEL_CHARS,
            allow_empty=False,
        )
        _validate_optional_safe_text(self.form_or_period, "download.row.form_or_period")
        _validate_optional_safe_text(self.filing_date, "download.row.filing_date")
        _validate_optional_safe_text(self.report_date, "download.row.report_date")
        if not isinstance(self.covered_fiscal_periods, tuple):
            raise TypeError("covered_fiscal_periods must be tuple")
        if any(not isinstance(period, str) or period not in FISCAL_PERIODS for period in self.covered_fiscal_periods):
            raise ValueError("covered_fiscal_periods must contain canonical fiscal periods")
        if len(set(self.covered_fiscal_periods)) != len(self.covered_fiscal_periods):
            raise ValueError("covered_fiscal_periods must not contain duplicates")
        if not isinstance(self.disposition, FinsDownloadDocumentDisposition):
            raise TypeError("disposition must be FinsDownloadDocumentDisposition")
        _validate_optional_safe_text(self.reason_category, "download.row.reason_category")
        _validate_optional_safe_text(self.reason_message, "download.row.reason_message")
        if (self.reason_category is None) is not (self.reason_message is None):
            raise ValueError("reason_category and reason_message must be provided together")
        if (
            self.disposition
            in {
                FinsDownloadDocumentDisposition.SKIPPED,
                FinsDownloadDocumentDisposition.REJECTED,
                FinsDownloadDocumentDisposition.FAILED,
            }
            and self.reason_category is None
        ):
            raise ValueError("non-downloaded public row must contain a reason")
        if self.artifact_locator is not None:
            _validate_safe_text(
                self.artifact_locator,
                field_name="download.row.artifact_locator",
                max_chars=_MAX_DETAIL_CHARS,
                allow_empty=False,
            )
            locator = PurePosixPath(self.artifact_locator)
            if locator.is_absolute() or ".." in locator.parts:
                raise ValueError("artifact_locator must be workspace-relative")
            if self.disposition is not FinsDownloadDocumentDisposition.DOWNLOADED:
                raise ValueError("only downloaded public rows may contain artifact_locator")
        if self.disposition is FinsDownloadDocumentDisposition.DOWNLOADED and self.artifact_locator is None:
            raise ValueError("downloaded public row requires artifact_locator")

    def to_json_value(self) -> dict[str, JsonValue]:
        """转换为自解释 JSON-compatible 文档行。

        Returns:
            public 文档行 JSON 对象。

        Raises:
            无。
        """

        return {
            "document_id": self.document_id,
            "form_or_period": self.form_or_period,
            "filing_date": self.filing_date,
            "report_date": self.report_date,
            "covered_fiscal_periods": list(self.covered_fiscal_periods),
            "disposition": self.disposition.value,
            "reason_category": self.reason_category,
            "reason_message": self.reason_message,
            "artifact_locator": self.artifact_locator,
        }


@dataclass(frozen=True, slots=True)
class FinsDownloadPublicSummary:
    """CLI 与 wait adapter 共享的 bounded 下载 terminal 真源。"""

    source: FinsDownloadSource
    canonical_ticker: str
    effective_filters: FinsDownloadEffectiveFilters
    discovered_count: int
    downloaded_count: int
    skipped_count: int
    rejected_count: int
    failed_count: int
    document_rows: tuple[FinsDownloadPublicDocument, ...]
    missing_periods: tuple[str, ...]
    omitted_count: int
    terminal_disposition: FinsDownloadTerminalDisposition

    def __post_init__(self) -> None:
        """校验 public summary 的计数与省略不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: typed 字段非法时抛出。
            ValueError: 计数、row、missing period 或 omitted 不守恒时抛出。
        """

        if not isinstance(self.source, FinsDownloadSource):
            raise TypeError("source must be FinsDownloadSource")
        if not isinstance(self.effective_filters, FinsDownloadEffectiveFilters):
            raise TypeError("effective_filters must be FinsDownloadEffectiveFilters")
        if not isinstance(self.terminal_disposition, FinsDownloadTerminalDisposition):
            raise TypeError("terminal_disposition must be FinsDownloadTerminalDisposition")
        _validate_safe_text(
            self.canonical_ticker,
            field_name="download.canonical_ticker",
            max_chars=_MAX_SHORT_FIELD_CHARS,
            allow_empty=False,
        )
        counts = (
            self.discovered_count,
            self.downloaded_count,
            self.skipped_count,
            self.rejected_count,
            self.failed_count,
            self.omitted_count,
        )
        if any(count < 0 for count in counts):
            raise ValueError("download public counts must be non-negative")
        if self.discovered_count != sum(counts[1:5]):
            raise ValueError("public discovered_count must equal disposition counts")
        if len(self.document_rows) + self.omitted_count != self.discovered_count:
            raise ValueError("document_rows plus omitted_count must equal discovered_count")
        for row in self.document_rows:
            if not isinstance(row, FinsDownloadPublicDocument):
                raise TypeError("document_rows must contain FinsDownloadPublicDocument")
        visible_counts = {
            disposition: sum(row.disposition is disposition for row in self.document_rows)
            for disposition in FinsDownloadDocumentDisposition
        }
        total_counts = {
            FinsDownloadDocumentDisposition.DOWNLOADED: self.downloaded_count,
            FinsDownloadDocumentDisposition.SKIPPED: self.skipped_count,
            FinsDownloadDocumentDisposition.REJECTED: self.rejected_count,
            FinsDownloadDocumentDisposition.FAILED: self.failed_count,
        }
        if any(
            visible_counts[disposition] > total_counts[disposition] for disposition in FinsDownloadDocumentDisposition
        ):
            raise ValueError("visible document disposition count exceeds total count")
        expected_terminal = _download_terminal_disposition(
            downloaded_count=self.downloaded_count,
            rejected_count=self.rejected_count,
            failed_count=self.failed_count,
        )
        # 公开对象只允许表达 adapter 启动前的零候选失败/取消，不接受伪造的 partial。
        empty_terminal_override = self.discovered_count == 0 and self.terminal_disposition in {
            FinsDownloadTerminalDisposition.FAILED,
            FinsDownloadTerminalDisposition.CANCELLED,
        }
        if self.terminal_disposition is not expected_terminal and not empty_terminal_override:
            raise ValueError("terminal_disposition does not match public counts")
        for period in self.missing_periods:
            _validate_safe_text(
                period,
                field_name="download.missing_period",
                max_chars=_MAX_SHORT_FIELD_CHARS,
                allow_empty=False,
            )

    def to_json_value(self) -> dict[str, JsonValue]:
        """转换为 CLI/wait 共用的自解释 JSON-compatible 对象。

        Returns:
            nested download 业务对象。

        Raises:
            无。
        """

        return {
            "source": self.source.value,
            "ticker": self.canonical_ticker,
            "filters": {
                "forms": list(self.effective_filters.form_types),
                "start_date": self.effective_filters.start_date,
                "end_date": self.effective_filters.end_date,
                "overwrite": self.effective_filters.overwrite_existing,
                "rebuild": self.effective_filters.rebuild_local_artifacts,
            },
            "counts": {
                "discovered": self.discovered_count,
                "downloaded": self.downloaded_count,
                "skipped": self.skipped_count,
                "rejected": self.rejected_count,
                "failed": self.failed_count,
            },
            "documents": [row.to_json_value() for row in self.document_rows],
            "missing_periods": list(self.missing_periods),
            "omitted_count": self.omitted_count,
            "terminal_disposition": self.terminal_disposition.value,
        }


class _ValidatedStreamState(str, Enum):
    """已验证 direct stream 的私有状态。"""

    OPEN = "open"
    RESULT_BUFFERED = "result_buffered"
    RESULT_YIELDED = "result_yielded"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class FinsEventDetail:
    """Fins direct 事件中的业务可读详情。

    Attributes:
        label: 用户可理解的详情名称。
        value: 用户可理解的详情值，不包含内部治理标识、路径或正文。
    """

    label: str
    value: str

    def __post_init__(self) -> None:
        """校验详情字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: label 或 value 为空、过长或包含禁止投影的内容时抛出。
        """

        _validate_safe_text(
            self.label,
            field_name="detail.label",
            max_chars=_MAX_DETAIL_CHARS,
            allow_empty=False,
        )
        _validate_safe_text(
            self.value,
            field_name="detail.value",
            max_chars=_MAX_DETAIL_CHARS,
            allow_empty=False,
        )


@dataclass(frozen=True, slots=True)
class FinsProgress:
    """Fins direct 运行中进度。

    Attributes:
        stage: 当前业务阶段短标签。
        completed_units: 已完成工作单元数；未知时为 ``None``。
        total_units: 总工作单元数；未知时为 ``None``。
    """

    stage: str
    completed_units: int | None
    total_units: int | None

    def __post_init__(self) -> None:
        """校验进度字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: stage 为空或工作单元计数非法时抛出。
        """

        _validate_safe_text(
            self.stage,
            field_name="progress.stage",
            max_chars=_MAX_STAGE_CHARS,
            allow_empty=False,
        )
        _validate_optional_non_negative_int(self.completed_units, "completed_units")
        _validate_optional_non_negative_int(self.total_units, "total_units")
        if (
            self.completed_units is not None
            and self.total_units is not None
            and self.completed_units > self.total_units
        ):
            raise ValueError("completed_units must not exceed total_units")


@dataclass(frozen=True, slots=True)
class FinsResultSummary:
    """Fins direct 终态业务摘要。

    Attributes:
        status: 终态状态。
        exit_code: product entrypoint 应使用的退出码。
        title: 用户可读结果标题。
        details: 有界、业务可读详情列表。
        error_kind: 失败分类；成功时通常为 ``None``。
        error_message: 用户可读失败说明；成功时通常为 ``None``。
        download: download 操作的 bounded public 业务对象。
        failure: download 失败的 closed public failure。
        warnings: publication-final typed 公司元数据警告，当前最多一个。
    """

    status: FinsResultStatus
    exit_code: int
    title: str
    details: tuple[FinsEventDetail, ...]
    error_kind: FinsErrorKind | None
    error_message: str | None
    download: FinsDownloadPublicSummary | None = None
    failure: FinsPublicFailure | None = None
    warnings: tuple[CompanyMetadataWarning, ...] = ()

    def __post_init__(self) -> None:
        """校验终态摘要字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: warning 元素不是精确 typed contract 时抛出。
            ValueError: exit code、标题、详情或 warning 组合不符合契约时抛出。
        """

        _validate_result_exit_code(self.status, self.exit_code)
        _validate_safe_text(
            self.title,
            field_name="result.title",
            max_chars=_MAX_TITLE_CHARS,
            allow_empty=False,
        )
        for detail in self.details:
            _validate_detail_instance(detail)
        if len(self.warnings) > 1:
            raise ValueError("Fins result 最多允许一个 warning")
        if any(type(warning) is not CompanyMetadataWarning for warning in self.warnings):
            raise TypeError("Fins result warning 必须是精确 typed contract")
        if self.warnings and self.status is not FinsResultStatus.SUCCESS:
            raise ValueError("只有 SUCCESS Fins result 可携带 warning")
        if self.error_message is not None:
            _validate_safe_text(
                self.error_message,
                field_name="result.error_message",
                max_chars=_MAX_MESSAGE_CHARS,
                allow_empty=False,
            )
        if self.download is not None and not isinstance(
            self.download,
            FinsDownloadPublicSummary,
        ):
            raise TypeError("download must be FinsDownloadPublicSummary")
        if self.failure is not None:
            if not isinstance(self.failure, FinsPublicFailure):
                raise TypeError("failure must be FinsPublicFailure")
            if self.status is not FinsResultStatus.FAILURE:
                raise ValueError("public failure is only valid for FAILURE result")
        if self.download is not None:
            if self.status is FinsResultStatus.FAILURE:
                if self.failure is None:
                    raise ValueError("failed download result requires public failure")
                if self.download.terminal_disposition is not FinsDownloadTerminalDisposition.FAILED:
                    raise ValueError("failed download result requires failed disposition")
            elif self.status is FinsResultStatus.CANCELLED:
                if self.download.terminal_disposition is not FinsDownloadTerminalDisposition.CANCELLED:
                    raise ValueError("cancelled download result requires cancelled disposition")
            elif self.download.terminal_disposition in {
                FinsDownloadTerminalDisposition.FAILED,
                FinsDownloadTerminalDisposition.CANCELLED,
            }:
                raise ValueError("successful download result has incompatible disposition")


@dataclass(frozen=True, slots=True)
class FinsEvent:
    """Fins direct 流式事件。

    Attributes:
        event_type: ``PROGRESS`` 或 ``RESULT``。
        operation_kind: 当前 direct 业务操作。
        message: 用户可读、有界事件说明。
        emitted_at: 事件产生时间，必须是带时区的 ``datetime``。
        ticker: 可选 ticker 文本。
        filing_kind: 可选财报类型或材料类型短标签。
        document_label: 可选用户可理解文档短标签，不是仓储路径。
        progress: progress 事件必填，result 事件必须为空。
        result: result 事件必填，progress 事件必须为空。
    """

    event_type: FinsEventType
    operation_kind: FinsOperationKind
    message: str
    emitted_at: datetime
    ticker: str | None
    filing_kind: str | None
    document_label: str | None
    progress: FinsProgress | None
    result: FinsResultSummary | None

    def __post_init__(self) -> None:
        """校验事件字段与 progress/result 互斥规则。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 事件字段组合非法或包含禁止投影内容时抛出。
        """

        _validate_aware_datetime(self.emitted_at)
        _validate_safe_text(
            self.message,
            field_name="event.message",
            max_chars=_MAX_MESSAGE_CHARS,
            allow_empty=False,
        )
        _validate_optional_short_text(self.ticker, "ticker")
        _validate_optional_short_text(self.filing_kind, "filing_kind")
        if self.document_label is not None:
            _validate_safe_text(
                self.document_label,
                field_name="document_label",
                max_chars=_MAX_DOCUMENT_LABEL_CHARS,
                allow_empty=False,
            )
        if self.event_type is FinsEventType.PROGRESS:
            if self.progress is None or self.result is not None:
                raise ValueError("PROGRESS event must have progress and no result")
        elif self.event_type is FinsEventType.RESULT:
            if self.result is None or self.progress is not None:
                raise ValueError("RESULT event must have result and no progress")
        else:
            raise ValueError(f"unsupported Fins event type: {self.event_type.value}")


class ValidatedFinsEventStream(AsyncIterator[FinsEvent]):
    """校验 Fins direct stream 终态协议并拥有 raw source 生命周期。

    Args:
        source: Fins runtime 创建的 raw 事件 async generator。
        operation_kind: 当前 direct 操作类型，用于 typed 协议错误来源。

    Raises:
        TypeError: operation_kind 类型非法时抛出。
    """

    def __init__(
        self,
        source: AsyncGenerator[FinsEvent, None],
        *,
        operation_kind: FinsOperationKind,
    ) -> None:
        """初始化唯一 direct stream validator。

        Args:
            source: Fins runtime 创建的 raw 事件 async generator。
            operation_kind: 当前 direct 操作类型。

        Returns:
            无。

        Raises:
            TypeError: operation_kind 类型非法时抛出。
        """

        if not isinstance(operation_kind, FinsOperationKind):
            raise TypeError("operation_kind must be FinsOperationKind")
        self._source = source
        self._operation_kind = operation_kind
        self._state = _ValidatedStreamState.OPEN
        self._buffered_result_event: FinsEvent | None = None
        self._terminal_result_value: FinsResultSummary | None = None
        self._clean_exhaustion = False
        self._source_close_attempted = False

    def __aiter__(self) -> ValidatedFinsEventStream:
        """返回当前已验证事件流。

        Args:
            无。

        Returns:
            当前已验证事件流实例。

        Raises:
            无。
        """

        return self

    async def __anext__(self) -> FinsEvent:
        """返回下一个已验证事件。

        首个 ``RESULT`` 会被缓存，只有 raw source clean exhaustion 后才会
        返回；其后的任意事件都会由本 owner 产生 typed 协议错误。

        Args:
            无。

        Returns:
            下一个 progress 事件或已证明唯一且最后的 result 事件。

        Raises:
            StopAsyncIteration: 已验证事件流耗尽时抛出。
            FinsDirectStreamProtocolError: 缺少、重复或 RESULT 后仍有事件时抛出。
            BaseException: raw source 的原始异常或取消以同一对象传播。
        """

        while True:
            if self._state is _ValidatedStreamState.CLOSED:
                raise StopAsyncIteration
            if self._state is _ValidatedStreamState.RESULT_YIELDED:
                self._state = _ValidatedStreamState.CLOSED
                raise StopAsyncIteration

            try:
                event = await self._source.__anext__()
            except StopAsyncIteration:
                return self._finish_clean_exhaustion()
            except BaseException as primary_error:
                await self._raise_primary_after_close(primary_error)

            if self._state is _ValidatedStreamState.OPEN:
                if event.event_type is FinsEventType.RESULT:
                    result = event.result
                    assert result is not None
                    self._buffered_result_event = event
                    self._terminal_result_value = result
                    self._state = _ValidatedStreamState.RESULT_BUFFERED
                    continue
                return event

            if event.event_type is FinsEventType.RESULT:
                protocol_error = FinsDirectStreamProtocolError(
                    FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT,
                    self._operation_kind,
                    _DUPLICATE_RESULT_MESSAGE,
                )
            else:
                protocol_error = FinsDirectStreamProtocolError(
                    FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT,
                    self._operation_kind,
                    _EVENT_AFTER_RESULT_MESSAGE,
                )
            await self._raise_primary_after_close(protocol_error)

    async def aclose(self) -> None:
        """中止消费并关闭 raw source，底层关闭最多尝试一次。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: 没有既存语义错误时，raw source 关闭失败以同一对象传播。
        """

        if self._state is _ValidatedStreamState.CLOSED:
            return
        self._state = _ValidatedStreamState.CLOSED
        if not self._clean_exhaustion:
            self._buffered_result_event = None
            self._terminal_result_value = None
        await self._close_source_once()

    @property
    def terminal_result(self) -> FinsResultSummary:
        """返回 clean exhaustion 已证明的同一终态结果实例。

        Args:
            无。

        Returns:
            已证明唯一且最后的 ``FinsResultSummary`` 实例。

        Raises:
            RuntimeError: stream 尚未 clean exhaustion 或已中止时抛出。
        """

        if not self._clean_exhaustion or self._terminal_result_value is None:
            raise RuntimeError(_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE)
        return self._terminal_result_value

    def _finish_clean_exhaustion(self) -> FinsEvent:
        """在 raw source clean exhaustion 时完成 terminal 判定。

        Args:
            无。

        Returns:
            已缓存且证明唯一、最后的 result 事件。

        Raises:
            FinsDirectStreamProtocolError: raw source 未产生 RESULT 时抛出。
        """

        if self._state is _ValidatedStreamState.OPEN:
            self._state = _ValidatedStreamState.CLOSED
            raise FinsDirectStreamProtocolError(
                FinsDirectStreamProtocolErrorKind.MISSING_RESULT,
                self._operation_kind,
                _MISSING_RESULT_MESSAGE,
            )
        buffered_event = self._buffered_result_event
        assert buffered_event is not None
        self._clean_exhaustion = True
        self._state = _ValidatedStreamState.RESULT_YIELDED
        return buffered_event

    async def _raise_primary_after_close(self, primary_error: BaseException) -> NoReturn:
        """关闭 raw source 后保持 primary semantic error 身份并重抛。

        Args:
            primary_error: upstream/cancellation 原异常或 validator typed 协议错误。

        Returns:
            不返回。

        Raises:
            BaseException: 始终重抛同一个 primary_error；关闭失败作为显式 cause。
        """

        self._state = _ValidatedStreamState.CLOSED
        self._buffered_result_event = None
        self._terminal_result_value = None
        try:
            await self._close_source_once()
        except BaseException as close_error:
            raise primary_error from close_error
        raise primary_error

    async def _close_source_once(self) -> None:
        """至多一次调用 raw source 的 ``aclose``。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: raw source 关闭失败时原样传播。
        """

        if self._source_close_attempted:
            return
        self._source_close_attempted = True
        await self._source.aclose()


def _validate_result_exit_code(status: FinsResultStatus, exit_code: int) -> None:
    """校验终态状态到退出码的固定映射。

    Args:
        status: 终态状态。
        exit_code: 待校验退出码。

    Returns:
        无。

    Raises:
        ValueError: 映射不符合 direct contract 时抛出。
    """

    if status is FinsResultStatus.SUCCESS and exit_code != FINS_RESULT_EXIT_SUCCESS:
        raise ValueError("SUCCESS result must use exit code 0")
    if status is FinsResultStatus.FAILURE and exit_code != FINS_RESULT_EXIT_FAILURE:
        raise ValueError("FAILURE result must use exit code 1")
    if status is FinsResultStatus.CANCELLED and exit_code != FINS_RESULT_EXIT_CANCELLED:
        raise ValueError("CANCELLED result must use exit code 130")


def _validate_detail_instance(detail: FinsEventDetail) -> None:
    """校验详情对象类型。

    Args:
        detail: 待校验详情。

    Returns:
        无。

    Raises:
        TypeError: detail 不是 ``FinsEventDetail`` 时抛出。
    """

    if not isinstance(detail, FinsEventDetail):
        raise TypeError("details must contain FinsEventDetail values")


def _validate_optional_non_negative_int(value: int | None, field_name: str) -> None:
    """校验可选非负整数。

    Args:
        value: 待校验值。
        field_name: 字段名。

    Returns:
        无。

    Raises:
        ValueError: 数值为负时抛出。
    """

    if value is not None and value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validate_aware_datetime(value: datetime) -> None:
    """校验事件时间带有时区。

    Args:
        value: 待校验时间。

    Returns:
        无。

    Raises:
        ValueError: 时间缺少时区信息时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("emitted_at must be timezone-aware")


def _validate_optional_short_text(value: str | None, field_name: str) -> None:
    """校验可选短文本字段。

    Args:
        value: 待校验文本。
        field_name: 字段名。

    Returns:
        无。

    Raises:
        ValueError: 文本过长或包含禁止投影内容时抛出。
    """

    if value is None:
        return
    _validate_safe_text(
        value,
        field_name=field_name,
        max_chars=_MAX_SHORT_FIELD_CHARS,
        allow_empty=False,
    )


def _validate_optional_safe_text(value: str | None, field_name: str) -> None:
    """校验 public download row 中的可选文本。

    Args:
        value: 可选文本。
        field_name: 错误说明使用的字段名。

    Returns:
        无。

    Raises:
        ValueError: 文本为空、过长或包含禁止内容时抛出。
    """

    if value is None:
        return
    _validate_safe_text(
        value,
        field_name=field_name,
        max_chars=_MAX_DETAIL_CHARS,
        allow_empty=False,
    )


def canonicalize_fins_public_file_label(raw_basename: str) -> str:
    """把单个原始 basename 投影为唯一 canonical public file label。

    Args:
        raw_basename: producer 从 ``Path.name`` 取得的原始文件 basename。

    Returns:
        可安全公开的原始 basename，或固定的文件名隐藏标签。

    Raises:
        TypeError: 输入不是字符串时抛出。
        ValueError: 输入为空、是 dot segment 或包含路径分隔符时抛出。
    """

    _validate_public_file_basename_shape(raw_basename)
    if _public_file_label_requires_hiding(raw_basename):
        return _HIDDEN_PUBLIC_FILE_LABEL
    return raw_basename


def validate_fins_public_file_label(value: str) -> None:
    """校验值属于 canonical public file label 的唯一接受集。

    Args:
        value: failure reason 或 direct projection 携带的 public file label。

    Returns:
        无。

    Raises:
        TypeError: 输入不是字符串时抛出。
        ValueError: 输入不是 canonicalizer 可产生的安全 label 时抛出。
    """

    _validate_public_file_basename_shape(value)
    if value == _HIDDEN_PUBLIC_FILE_LABEL:
        return
    if _public_file_label_requires_hiding(value):
        raise ValueError("public file label 必须先经过 canonicalizer")


def _validate_public_file_basename_shape(value: str) -> None:
    """校验 public file label 输入是单个非空 basename。

    Args:
        value: canonicalizer 或 validator 的输入。

    Returns:
        无。

    Raises:
        TypeError: 输入不是字符串时抛出。
        ValueError: 输入为空、是 dot segment 或包含路径分隔符时抛出。
    """

    if not isinstance(value, str):
        raise TypeError("public file label 必须是字符串")
    if value == "" or value in {".", ".."}:
        raise ValueError("public file label 必须是非空 basename")
    if "/" in value or "\\" in value:
        raise ValueError("public file label 禁止路径分隔符")


def _public_file_label_requires_hiding(value: str) -> bool:
    """判断合法 basename 是否必须投影为固定隐藏标签。

    Args:
        value: 已通过 basename shape 校验的文件名。

    Returns:
        命中长度、Unicode control/format 或既有 public guard 时返回 ``True``。

    Raises:
        无。
    """

    if len(value) > _MAX_PUBLIC_FILE_LABEL_CHARS:
        return True
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        return True
    try:
        _validate_safe_text(
            value,
            field_name="public file label",
            max_chars=_MAX_PUBLIC_FILE_LABEL_CHARS,
            allow_empty=False,
        )
    except ValueError:
        return True
    return False


def _validate_safe_text(
    value: str,
    *,
    field_name: str,
    max_chars: int,
    allow_empty: bool,
) -> None:
    """校验 direct event 用户可读文本不会泄漏内部或大块材料。

    Args:
        value: 待校验文本。
        field_name: 字段名，用于错误说明。
        max_chars: 最大字符数。
        allow_empty: 是否允许空字符串。

    Returns:
        无。

    Raises:
        ValueError: 文本为空、过长或命中泄漏守卫时抛出。
    """

    if not allow_empty and not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > max_chars:
        raise ValueError(f"{field_name} exceeds {max_chars} characters")
    lower = value.lower()
    if "://" in lower:
        raise ValueError(f"{field_name} contains a URL")
    for fragment in _DISALLOWED_TEXT_FRAGMENTS:
        if fragment in lower:
            raise ValueError(f"{field_name} contains disallowed internal text")
    if _FINS_JOB_ID_PATTERN.search(value):
        raise ValueError(f"{field_name} contains a job id")
    if _ABSOLUTE_POSIX_PATH_PATTERN.search(value):
        raise ValueError(f"{field_name} contains an absolute path")
    if _ABSOLUTE_WINDOWS_PATH_PATTERN.search(value):
        raise ValueError(f"{field_name} contains an absolute path")


def _download_terminal_disposition(
    *,
    downloaded_count: int,
    rejected_count: int,
    failed_count: int,
) -> FinsDownloadTerminalDisposition:
    """从 public counts 机械派生下载终态。

    Args:
        downloaded_count: 下载成功数。
        rejected_count: 业务拒绝数。
        failed_count: 下载失败数。

    Returns:
        与 owner-level summary 相同规则的终态分类。

    Raises:
        无。
    """

    if failed_count == 0:
        return FinsDownloadTerminalDisposition.SUCCEEDED
    if downloaded_count == 0 and rejected_count == 0:
        return FinsDownloadTerminalDisposition.FAILED
    return FinsDownloadTerminalDisposition.PARTIAL_FAILURE


__all__: tuple[str, ...] = (
    "FINS_RESULT_EXIT_CANCELLED",
    "FINS_RESULT_EXIT_FAILURE",
    "FINS_RESULT_EXIT_SUCCESS",
    "FinsDirectStreamProtocolError",
    "FinsDirectStreamProtocolErrorKind",
    "FinsDownloadPublicDocument",
    "FinsDownloadPublicSummary",
    "FinsErrorKind",
    "FinsEvent",
    "FinsEventDetail",
    "FinsEventType",
    "FinsOperationKind",
    "FinsProgress",
    "FinsPublicFailure",
    "FinsPublicFailureKind",
    "FinsResultStatus",
    "FinsResultSummary",
    "ValidatedFinsEventStream",
    "canonicalize_fins_public_file_label",
    "validate_fins_public_file_label",
)
