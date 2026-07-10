"""Fins direct 执行事件契约。

本模块定义 CLI、Service 与 Fins runtime direct path 共享的业务事件形态。
事件只表达当前财报 direct 操作的进度与终态结果，不表达后台 job、sidecar、
游标、仓储路径或 Host / Engine 治理状态。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final

FINS_RESULT_EXIT_SUCCESS: Final[int] = 0
FINS_RESULT_EXIT_FAILURE: Final[int] = 1
FINS_RESULT_EXIT_CANCELLED: Final[int] = 130

_MAX_MESSAGE_CHARS: Final[int] = 240
_MAX_DETAIL_CHARS: Final[int] = 240
_MAX_TITLE_CHARS: Final[int] = 120
_MAX_STAGE_CHARS: Final[int] = 120
_MAX_DOCUMENT_LABEL_CHARS: Final[int] = 120
_MAX_SHORT_FIELD_CHARS: Final[int] = 80

_FINS_JOB_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bfinsjob_[0-9a-fA-F]{32}\b"
)
_ABSOLUTE_POSIX_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s='\":])/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]+"
)
_ABSOLUTE_WINDOWS_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s='\":])[A-Za-z]:\\"
)
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
            raise TypeError(
                "reason must be FinsDirectStreamProtocolErrorKind"
            )
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
    """

    status: FinsResultStatus
    exit_code: int
    title: str
    details: tuple[FinsEventDetail, ...]
    error_kind: FinsErrorKind | None
    error_message: str | None

    def __post_init__(self) -> None:
        """校验终态摘要字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: exit code 映射错误、标题或详情包含禁止内容时抛出。
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
        if self.error_message is not None:
            _validate_safe_text(
                self.error_message,
                field_name="result.error_message",
                max_chars=_MAX_MESSAGE_CHARS,
                allow_empty=False,
            )


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
    for fragment in _DISALLOWED_TEXT_FRAGMENTS:
        if fragment in lower:
            raise ValueError(f"{field_name} contains disallowed internal text")
    if _FINS_JOB_ID_PATTERN.search(value):
        raise ValueError(f"{field_name} contains a job id")
    if _ABSOLUTE_POSIX_PATH_PATTERN.search(value):
        raise ValueError(f"{field_name} contains an absolute path")
    if _ABSOLUTE_WINDOWS_PATH_PATTERN.search(value):
        raise ValueError(f"{field_name} contains an absolute path")


__all__: tuple[str, ...] = (
    "FINS_RESULT_EXIT_CANCELLED",
    "FINS_RESULT_EXIT_FAILURE",
    "FINS_RESULT_EXIT_SUCCESS",
    "FinsDirectStreamProtocolError",
    "FinsDirectStreamProtocolErrorKind",
    "FinsErrorKind",
    "FinsEvent",
    "FinsEventDetail",
    "FinsEventType",
    "FinsOperationKind",
    "FinsProgress",
    "FinsResultStatus",
    "FinsResultSummary",
)
