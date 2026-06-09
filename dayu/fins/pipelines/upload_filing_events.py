"""上传财报事件模型。

该模块定义 upload filing stream 对外输出的标准事件结构，用于 runtime
和测试观测上传过程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import now_iso8601


class UploadFilingEventType(StrEnum):
    """上传财报事件类型。"""

    UPLOAD_STARTED = "upload_started"
    CONVERSION_STARTED = "conversion_started"
    FILE_UPLOADED = "file_uploaded"
    FILE_SKIPPED = "file_skipped"
    FILE_FAILED = "file_failed"
    UPLOAD_COMPLETED = "upload_completed"
    UPLOAD_FAILED = "upload_failed"


@dataclass(frozen=True)
class UploadFilingEvent:
    """上传财报事件。

    Attributes:
        event_type: 事件类型。
        ticker: 股票代码。
        document_id: 可选文档 ID。
        payload: 事件负载。
        emitted_at: 事件生成时间。
    """

    event_type: UploadFilingEventType
    ticker: str
    document_id: str | None = None
    payload: dict[str, JsonValue] = field(default_factory=dict)
    emitted_at: str = field(default_factory=now_iso8601)


__all__ = ["UploadFilingEvent", "UploadFilingEventType"]
