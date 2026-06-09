"""下载事件模型。

该模块定义 `SecPipeline.download_stream` 对外输出的标准事件结构，
用于 CLI 之外的 GUI/Web 实时消费。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

from dataclasses import dataclass, field
from enum import StrEnum

from dayu.fins.domain.document_models import now_iso8601


class DownloadEventType(StrEnum):
    """下载流水线事件类型。"""

    PIPELINE_STARTED = "pipeline_started"
    COMPANY_RESOLVED = "company_resolved"
    FILING_STARTED = "filing_started"
    FILE_DOWNLOADED = "file_downloaded"
    FILE_SKIPPED = "file_skipped"
    FILE_FAILED = "file_failed"
    FILING_COMPLETED = "filing_completed"
    FILING_FAILED = "filing_failed"
    PIPELINE_COMPLETED = "pipeline_completed"


@dataclass(frozen=True)
class DownloadEvent:
    """下载事件。

    Attributes:
        event_type: 事件类型。
        ticker: 股票代码。
        document_id: 可选文档 ID（文件级或文档级事件会携带）。
        payload: 事件负载（字段按事件类型动态扩展）。
        emitted_at: 事件生成时间（ISO8601）。
    """

    event_type: DownloadEventType
    ticker: str
    document_id: str | None = None
    payload: dict[str, JsonValue] = field(default_factory=dict)
    emitted_at: str = field(default_factory=now_iso8601)
