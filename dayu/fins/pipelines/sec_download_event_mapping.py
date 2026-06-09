"""SEC 下载事件映射工具集。

将下载器事件转换为 pipeline 级事件结构、汇总文件级失败原因等。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

from typing import Optional, TypeAlias

from dayu.fins.domain.document_models import FileObjectMeta
from dayu.fins.downloaders.sec_downloader import DownloaderEvent
from dayu.fins.pipelines.download_events import DownloadEventType
from dayu.fins.pipelines.sec_form_utils import first_non_empty_text

DownloadFileResultValue: TypeAlias = JsonValue | FileObjectMeta
"""文件下载阶段结果值。

下载阶段内部结果会临时携带 ``FileObjectMeta``，落 source meta 前需要它的
结构化字段；对外事件 payload 通过 ``build_download_file_event_payload``
转成严格 JSON。
"""

DownloadFileResult: TypeAlias = dict[str, DownloadFileResultValue]
"""文件下载阶段内部结果。"""


def map_file_status_to_event_type(status: str) -> DownloadEventType:
    """将文件下载状态映射到事件类型。

    Args:
        status: 文件状态（downloaded/skipped/failed）。

    Returns:
        下载事件类型枚举。

    Raises:
        ValueError: 状态未知时抛出。
    """

    mapping: dict[str, DownloadEventType] = {
        "downloaded": DownloadEventType.FILE_DOWNLOADED,
        "skipped": DownloadEventType.FILE_SKIPPED,
        "failed": DownloadEventType.FILE_FAILED,
    }
    event_type = mapping.get(status)
    if event_type is None:
        raise ValueError(f"未知文件状态: {status}")
    return event_type


def build_download_filing_event_payload(filing_result: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """构建 filing 级下载事件负载。

    Args:
        filing_result: 规范化后的 filing 结果。

    Returns:
        同时包含顶层扁平字段与 ``filing_result`` 嵌套字段的事件负载。

    Raises:
        无。
    """

    normalized_result = dict(filing_result)
    payload = dict(normalized_result)
    payload["filing_result"] = normalized_result
    return payload


def summarize_failed_download_file_reasons(failed_files: list[DownloadFileResult]) -> str:
    """汇总文件级失败原因，生成 filing 级极简说明。

    Args:
        failed_files: 失败文件结果列表。

    Returns:
        面向 CLI 与 job 状态摘要的简短失败说明。

    Raises:
        无。
    """

    messages: list[str] = []
    for item in failed_files:
        if not isinstance(item, dict):
            continue
        message = first_non_empty_text(
            _json_result_value(item, "reason_message"),
            _json_result_value(item, "message"),
            _json_result_value(item, "error"),
        )
        if message is None or message in messages:
            continue
        messages.append(message)
    if not messages:
        return "存在文件下载失败"
    if len(messages) == 1:
        return messages[0]
    preview = "；".join(messages[:2])
    if len(messages) <= 2:
        return preview
    return f"{preview} 等{len(messages)}项"


def normalize_download_file_result(file_result: DownloadFileResult) -> DownloadFileResult:
    """标准化文件级下载结果中的原因字段。

    Args:
        file_result: 原始文件结果。

    Returns:
        补齐 ``reason_code/reason_message`` 后的结果字典。

    Raises:
        无。
    """

    normalized = dict(file_result)
    status = str(normalized.get("status", "")).strip().lower()
    if status == "skipped":
        reason_code = first_non_empty_text(
            _json_result_value(normalized, "reason_code"),
            _json_result_value(normalized, "skip_reason"),
            _json_result_value(normalized, "reason"),
        )
        reason_message = first_non_empty_text(
            _json_result_value(normalized, "reason_message"),
            _json_result_value(normalized, "message"),
        )
        if reason_message is None and reason_code == "not_modified":
            reason_message = "远端文件未修改，跳过重新下载"
        if reason_code is not None:
            normalized["reason_code"] = reason_code
        if reason_message is not None:
            normalized["reason_message"] = reason_message
        return normalized
    if status == "failed":
        reason_code = first_non_empty_text(
            _json_result_value(normalized, "reason_code"),
            _json_result_value(normalized, "reason"),
        )
        if reason_code is None and first_non_empty_text(_json_result_value(normalized, "error")) is not None:
            reason_code = "download_error"
        reason_message = first_non_empty_text(
            _json_result_value(normalized, "reason_message"),
            _json_result_value(normalized, "message"),
            _json_result_value(normalized, "error"),
        )
        if reason_code is not None:
            normalized["reason_code"] = reason_code
        if reason_message is not None:
            normalized["reason_message"] = reason_message
        return normalized
    return normalized


def build_file_result_from_downloader_event(event: DownloaderEvent) -> DownloadFileResult:
    """将下载器事件转换为 pipeline 文件结果结构。

    Args:
        event: 下载器文件级事件。

    Returns:
        与历史 ``download_files`` 结果兼容的字典。

    Raises:
        ValueError: 事件类型不支持时抛出。
    """

    if event.event_type == "file_downloaded":
        return {
            "name": event.name,
            "status": "downloaded",
            "file_meta": event.file_meta,
            "source_url": event.source_url,
            "http_etag": event.http_etag,
            "http_last_modified": event.http_last_modified,
            "http_status": event.http_status,
        }
    if event.event_type == "file_skipped":
        return normalize_download_file_result(
            {
                "name": event.name,
                "status": "skipped",
                "source_url": event.source_url,
                "http_etag": event.http_etag,
                "http_last_modified": event.http_last_modified,
                "http_status": event.http_status,
                "reason_code": event.reason_code,
                "reason_message": event.reason_message,
            }
        )
    if event.event_type == "file_failed":
        return normalize_download_file_result(
            {
                "name": event.name,
                "status": "failed",
                "source_url": event.source_url,
                "http_etag": event.http_etag,
                "http_last_modified": event.http_last_modified,
                "http_status": event.http_status,
                "reason_code": event.reason_code,
                "reason_message": event.reason_message,
                "error": event.error,
            }
        )
    raise ValueError(f"不支持的下载器事件类型: {event.event_type}")


def build_download_file_event_payload(file_result: DownloadFileResult) -> dict[str, JsonValue]:
    """将内部文件结果转换为下载事件 JSON payload。

    Args:
        file_result: 内部文件下载结果。

    Returns:
        可安全放入 ``DownloadEvent.payload`` 的 JSON 字典。

    Raises:
        无。
    """

    payload: dict[str, JsonValue] = {}
    for key, value in file_result.items():
        if isinstance(value, FileObjectMeta):
            payload[key] = {
                "uri": value.uri,
                "etag": value.etag,
                "last_modified": value.last_modified,
                "size": value.size,
                "content_type": value.content_type,
                "sha256": value.sha256,
            }
            continue
        payload[key] = value
    return payload


def _json_result_value(file_result: DownloadFileResult, key: str) -> JsonValue:
    """读取文件结果中的 JSON 字段。

    Args:
        file_result: 文件下载结果。
        key: 字段名。

    Returns:
        JSON 字段值；字段不存在或为内部 ``FileObjectMeta`` 时返回 ``None``。

    Raises:
        无。
    """

    value = file_result.get(key)
    if isinstance(value, FileObjectMeta):
        return None
    return value
