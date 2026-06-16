"""Fins ingestion awaiting tools 的私有共享辅助函数。

本模块只承载 download/preprocess/upload 工具适配层共用的 outcome 构造和
JSON 参数读取逻辑；具体请求对象仍由各工具模块自行构造。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSnapshot, ToolAwaitSpec
from dayu.contracts.tool_outcome import ToolAwaitingOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultMeta
from dayu.fins.ingestion.observation_handle import (
    FinsObservationHandle,
    observation_handle_id_to_resume_token,
)


def _awaiting_outcome_from_observation_handle(
    handle: FinsObservationHandle,
) -> ToolAwaitingOutcome:
    """把 lightweight observation handle 转换为等待 outcome。

    Args:
        handle: runtime 返回的 process-local observation handle。

    Returns:
        外部等待 outcome。

    Raises:
        ValueError: handle token 非法时由等待契约抛出。
    """

    captured_at = datetime.now(timezone.utc)
    resume_token = observation_handle_id_to_resume_token(handle)
    return ToolAwaitingOutcome(
        await_spec=ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token=resume_token,
        ),
        snapshot=ToolAwaitSnapshot(
            snapshot_id=(
                "fins-observation-start-"
                f"{handle.operation_kind.value}-"
                f"{captured_at.strftime('%Y%m%dT%H%M%S%fZ')}"
            ),
            captured_at=captured_at,
        ),
    )


def _failed_outcome(
    *,
    tool_name: str,
    started_at: datetime,
    error: str,
    message: str,
    hint: str,
) -> ToolFailedOutcome:
    """构造工具失败 outcome。

    Args:
        tool_name: 工具名。
        started_at: 工具开始时间。
        error: 错误码。
        message: 面向模型的错误说明。
        hint: 面向模型的恢复提示。

    Returns:
        工具失败 outcome。

    Raises:
        ValueError: 失败结果字段为空时由契约构造抛出。
    """

    finished_at = datetime.now(timezone.utc)
    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=error,
            message=message,
            hint=hint,
            meta=ToolResultMeta(
                tool_name=tool_name,
                started_at=started_at,
                finished_at=finished_at,
            ),
        )
    )


def _required_text(arguments: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填非空字符串参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。

    Returns:
        去除两端空白后的字符串。

    Raises:
        ValueError: 字段缺失、不是字符串或为空时抛出。
    """

    value = arguments.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(arguments: Mapping[str, JsonValue], field_name: str, *, default: str) -> str:
    """读取可选字符串参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        去除两端空白后的字符串，字段缺失时返回缺省值。

    Raises:
        ValueError: 字段存在但不是非空字符串时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return default
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be a non-empty string when provided")
    return value.strip()


def _optional_nullable_text(arguments: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选 nullable 字符串参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。

    Returns:
        字段缺失或为 null 时返回 ``None``，否则返回去空白字符串。

    Raises:
        ValueError: 字段存在但不是非空字符串或 null 时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be a non-empty string or null")
    return value.strip()


def _optional_text_tuple(arguments: Mapping[str, JsonValue], field_name: str) -> tuple[str, ...]:
    """读取可选字符串数组参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。

    Returns:
        字符串元组；字段缺失时为空元组。

    Raises:
        ValueError: 字段存在但不是字符串数组或含空字符串时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise ValueError(f"{field_name} must contain only non-empty strings")
        items.append(item.strip())
    return tuple(items)


def _optional_bool(arguments: Mapping[str, JsonValue], field_name: str, *, default: bool) -> bool:
    """读取可选布尔参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。
        default: 缺省值。

    Returns:
        布尔值。

    Raises:
        ValueError: 字段存在但不是布尔值时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean")
    return value


def _optional_int(arguments: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取可选整数参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。

    Returns:
        字段缺失或为 null 时返回 ``None``，否则返回整数。

    Raises:
        ValueError: 字段存在但不是整数时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be integer or null")
    return value


def _required_int(arguments: Mapping[str, JsonValue], field_name: str) -> int:
    """读取必填整数参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。

    Returns:
        整数值。

    Raises:
        ValueError: 字段缺失、为 null 或不是整数时抛出。
    """

    value = _optional_int(arguments, field_name)
    if value is None:
        raise ValueError(f"{field_name} must be an integer")
    return value
