"""Fins ingestion job 事件契约。

本模块只定义 Fins 自有 durable job event 的 typed record、append 输入与
payload 校验。事件用于 Service / UI 观察 Fins direct job 进展，不属于 Host
EventLog、Engine stream 或 provider 原始事件。
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind

if TYPE_CHECKING:
    from dayu.fins.ingestion_runtime import FinsIngestionJobStatus, FinsIngestionOperationKind

_MAX_EVENT_PAYLOAD_JSON_CHARS: Final[int] = 4096


class FinsIngestionJobEventType(str, Enum):
    """Fins ingestion job 事件类型。

    事件分为两类：

    - 状态转换事件：``JOB_QUEUED``、``JOB_RUNNING``、``JOB_SUCCEEDED``、
      ``JOB_FAILED``、``JOB_CANCELLED``。它们只表示 job record 已经由
      runtime/store 保存到对应状态；job record 仍是状态真源。
    - 观察 / 进度事件：``PROGRESS``、``CANCEL_REQUESTED``。它们只表达
      用户可见进度或取消请求观察信号，不能被当作 job state transition；
      ``CANCEL_REQUESTED`` 不等于 job 已进入 terminal cancelled。
    """

    JOB_QUEUED = "job_queued"
    JOB_RUNNING = "job_running"
    PROGRESS = "progress"
    CANCEL_REQUESTED = "cancel_requested"
    JOB_SUCCEEDED = "job_succeeded"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"


@dataclass(frozen=True)
class FinsIngestionJobEventAppend:
    """追加 Fins ingestion job event 时的输入。

    Attributes:
        operation_kind: job 操作类型；用于消费方不用回读 job record 即可理解事件。
        status: 事件发生时对应的 job record 状态；观察 / 进度事件可以为空。
        event_type: Fins job event 类型。
        source_event_type: 可选来源事件类型；只作为观察标签，不是业务事实。
        source_kind: 可选源文档类型。
        document_id: 可选业务文档 ID；允许业务合法斜杠，不得放文件路径。
        message: 有界、用户可读的简短事件说明。
        payload: 有界 JSON-compatible 业务摘要，不得包含绝对路径、财报正文或
            provider raw payload。
        emitted_at: UTC ISO8601 事件产生时间。
    """

    operation_kind: FinsIngestionOperationKind
    status: FinsIngestionJobStatus | None
    event_type: FinsIngestionJobEventType
    source_event_type: str | None
    source_kind: SourceKind | None
    document_id: str | None
    message: str
    payload: dict[str, JsonValue]
    emitted_at: str


@dataclass(frozen=True)
class FinsIngestionJobEventRecord:
    """已持久化的 Fins ingestion job event record。

    Attributes:
        job_id: opaque job id。
        sequence: 当前 job 内从 1 开始递增的事件游标；它只是读取游标，不是业务事实。
        operation_kind: job 操作类型。
        status: 事件发生时对应的 job record 状态；观察 / 进度事件可以为空。
        event_type: Fins job event 类型。
        source_event_type: 可选来源事件类型；只作为观察标签，不是业务事实。
        source_kind: 可选源文档类型。
        document_id: 可选业务文档 ID。
        message: 有界、用户可读的简短事件说明。
        payload: 有界 JSON-compatible 业务摘要。
        emitted_at: UTC ISO8601 事件产生时间。
    """

    job_id: str
    sequence: int
    operation_kind: FinsIngestionOperationKind
    status: FinsIngestionJobStatus | None
    event_type: FinsIngestionJobEventType
    source_event_type: str | None
    source_kind: SourceKind | None
    document_id: str | None
    message: str
    payload: dict[str, JsonValue]
    emitted_at: str


def is_status_transition_job_event(event_type: FinsIngestionJobEventType) -> bool:
    """判断事件类型是否是 job record 状态转换观察。

    Args:
        event_type: 待判断事件类型。

    Returns:
        ``JOB_QUEUED``、``JOB_RUNNING``、``JOB_SUCCEEDED``、``JOB_FAILED``、
        ``JOB_CANCELLED`` 返回 ``True``；``PROGRESS`` 与
        ``CANCEL_REQUESTED`` 返回 ``False``。

    Raises:
        无。
    """

    return event_type in {
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
        FinsIngestionJobEventType.JOB_FAILED,
        FinsIngestionJobEventType.JOB_CANCELLED,
    }


def is_observation_job_event(event_type: FinsIngestionJobEventType) -> bool:
    """判断事件类型是否是观察 / 进度信号。

    Args:
        event_type: 待判断事件类型。

    Returns:
        ``PROGRESS`` 与 ``CANCEL_REQUESTED`` 返回 ``True``；状态转换事件返回
        ``False``。

    Raises:
        无。
    """

    return event_type in {
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.CANCEL_REQUESTED,
    }


def validate_bounded_job_event_payload(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> dict[str, JsonValue]:
    """校验 Fins job event payload 是有界 JSON-compatible 映射。

    Args:
        payload: 待进入 event sidecar 的业务摘要。
        field_name: 用于错误信息的字段名。

    Returns:
        payload 的浅拷贝。

    Raises:
        ValueError: payload 不是严格 JSON-compatible、包含非字符串 key、包含非
            有限浮点数或 JSON 编码后超出大小上限时抛出。
    """

    copied = dict(payload)
    _validate_json_mapping(copied, field_name)
    try:
        encoded = json.dumps(copied, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 不是 JSON-compatible payload") from exc
    if len(encoded) > _MAX_EVENT_PAYLOAD_JSON_CHARS:
        raise ValueError(f"{field_name} 超出大小上限")
    return copied


def _validate_json_mapping(payload: Mapping[str, JsonValue], field_name: str) -> None:
    """递归校验 JSON 映射。

    Args:
        payload: 待校验映射。
        field_name: 当前字段路径。

    Returns:
        无。

    Raises:
        ValueError: key 或 value 不符合 JSON-compatible 约束时抛出。
    """

    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} 包含非字符串 key")
        _validate_json_value(value, f"{field_name}.{key}")


def _validate_json_value(value: JsonValue, field_name: str) -> None:
    """递归校验单个 JSON 值。

    Args:
        value: 待校验值。
        field_name: 当前字段路径。

    Returns:
        无。

    Raises:
        ValueError: 值不符合 JSON-compatible 约束时抛出。
    """

    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} 包含非有限浮点数")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{field_name}[{index}]")
        return
    if isinstance(value, Mapping):
        _validate_json_mapping(value, field_name)
        return
    raise ValueError(f"{field_name} 不是 JSON-compatible 值")


__all__ = [
    "FinsIngestionJobEventAppend",
    "FinsIngestionJobEventRecord",
    "FinsIngestionJobEventType",
    "is_observation_job_event",
    "is_status_transition_job_event",
    "validate_bounded_job_event_payload",
]
