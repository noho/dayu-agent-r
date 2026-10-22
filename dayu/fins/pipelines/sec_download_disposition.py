"""SEC 已确认下载行到互斥文档结果分类的唯一投影。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.download_contract import FinsDownloadDocumentDisposition

_REASON_6K_FILTERED: Final[str] = "6k_filtered"


def project_sec_filing_disposition(
    item: Mapping[str, JsonValue],
) -> FinsDownloadDocumentDisposition:
    """从确认行的状态与拒绝原因投影唯一文档分类。

    Args:
        item: SEC 工作流已确认的原始文档行；不会修改其字段。
            skipped 至少提供一个非空原因；两字段均有值时，去首尾空白后必须相同。

    Returns:
        现有四类结果；过滤拒绝的 skipped 行归为 REJECTED。

    Raises:
        ValueError: status 缺失、非法或不属于四类状态，或 skipped 原因非法、全缺失或互相冲突。
    """

    raw_status = item.get("status")
    if not isinstance(raw_status, str) or not raw_status.strip():
        raise ValueError("SEC 下载结果缺少必填文本字段: status")
    status = raw_status.strip()
    try:
        disposition = FinsDownloadDocumentDisposition(status)
    except ValueError as exc:
        raise ValueError(f"SEC 下载结果 status 未封闭: {status}") from exc
    if disposition is not FinsDownloadDocumentDisposition.SKIPPED:
        return disposition
    skip_reason = _optional_reason(item, "skip_reason")
    reason_code = _optional_reason(item, "reason_code")
    if skip_reason is None and reason_code is None:
        raise ValueError("SEC skipped 下载结果至少需要一个非空原因字段")
    if skip_reason is not None and reason_code is not None and skip_reason != reason_code:
        raise ValueError("SEC skipped 下载结果的 skip_reason 与 reason_code 不一致")
    if skip_reason == _REASON_6K_FILTERED or reason_code == _REASON_6K_FILTERED:
        return FinsDownloadDocumentDisposition.REJECTED
    return disposition


def _optional_reason(item: Mapping[str, JsonValue], key: str) -> str | None:
    """严格读取参与分类的可选原因文本。

    Args:
        item: 已确认文档行。
        key: 原因字段名。

    Returns:
        缺失或 null 返回 None，其余返回去首尾空白的非空文本。

    Raises:
        ValueError: 字段存在但不是非空文本。
    """

    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"SEC 下载结果缺少必填文本字段: {key}")
    return value.strip()
